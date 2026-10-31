"""Conversões entre PDF e outros formatos.

Para PDF:
  * Nativo (PyMuPDF): imagens (png, jpg, bmp, gif, tiff, webp...), XPS, EPUB, CBZ, FB2, SVG, TXT
  * Office/LibreOffice: doc, docx, odt, rtf, xls, xlsx, ods, csv, ppt, pptx, odp, html
    - usa o LibreOffice (gratuito) se instalado; senão o Microsoft Office (via COM) no Windows.
A partir do PDF:
  * Word (.docx), Excel (.xlsx), PowerPoint (.pptx), imagens (PNG/JPG/TIFF), texto (.txt),
    HTML, Markdown e formatos ODF (odt/ods) via LibreOffice.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

NATIVE_TO_PDF = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".pnm",
                 ".pgm", ".ppm", ".jxr", ".jpx", ".xps", ".oxps", ".epub", ".cbz", ".fb2",
                 ".svg", ".txt", ".mobi"}
OFFICE_TO_PDF = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".csv",
                 ".ppt", ".pptx", ".odp", ".html", ".htm", ".wpd", ".pub", ".vsd", ".vsdx"}
TO_PDF_EXTS = NATIVE_TO_PDF | OFFICE_TO_PDF | {".pdf"}

# formato de saída -> (descrição, extensão)
FROM_PDF = {
    "docx": ("Word (.docx)", ".docx"),
    "xlsx": ("Excel (.xlsx)", ".xlsx"),
    "pptx": ("PowerPoint (.pptx)", ".pptx"),
    "png": ("Imagem PNG (uma por página)", ".png"),
    "jpg": ("Imagem JPG (uma por página)", ".jpg"),
    "tiff": ("TIFF multipágina", ".tiff"),
    "txt": ("Texto (.txt)", ".txt"),
    "html": ("Página web (.html)", ".html"),
    "md": ("Markdown (.md)", ".md"),
    "odt": ("LibreOffice Writer (.odt)", ".odt"),
    "pdfa": ("PDF compactado / otimizado", ".pdf"),
}


class ConversionError(Exception):
    pass


def _no_window():
    return {"creationflags": 0x08000000} if sys.platform.startswith("win") else {}


# ------------------------------------------------------------------ LibreOffice / Office
def find_libreoffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    if sys.platform.startswith("win"):
        pats = [r"C:\Program Files\LibreOffice*\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice*\program\soffice.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\LibreOffice*\program\soffice.exe")]
        for pat in pats:
            hits = glob.glob(pat)
            if hits:
                return hits[0]
    elif sys.platform == "darwin":
        p = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        if os.path.exists(p):
            return p
    return None


def _libreoffice_convert(src: str, out_dir: str, fmt: str) -> str:
    lo = find_libreoffice()
    if not lo:
        raise ConversionError("LibreOffice não encontrado")
    profile = Path(tempfile.gettempdir()) / "vorticis_lo_profile"
    cmd = [lo, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
           "--convert-to", fmt, "--outdir", out_dir, src]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, **_no_window())
    out = Path(out_dir) / (Path(src).stem + "." + fmt.split(":")[0])
    if not out.exists():
        raise ConversionError(f"LibreOffice falhou: {r.stderr or r.stdout}")
    return str(out)


def _msoffice_to_pdf(src: str, out_pdf: str):
    """Conversão via Microsoft Office instalado (somente Windows)."""
    try:
        import win32com.client  # type: ignore
    except ImportError as e:
        raise ConversionError("pywin32 indisponível") from e
    ext = Path(src).suffix.lower()
    src, out_pdf = os.path.abspath(src), os.path.abspath(out_pdf)
    if ext in (".doc", ".docx", ".odt", ".rtf", ".html", ".htm", ".wpd"):
        app = win32com.client.DispatchEx("Word.Application")
        app.Visible = False
        try:
            d = app.Documents.Open(src, ReadOnly=True)
            d.ExportAsFixedFormat(out_pdf, 17)
            d.Close(False)
        finally:
            app.Quit()
    elif ext in (".xls", ".xlsx", ".ods", ".csv"):
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = False
        app.DisplayAlerts = False
        try:
            wb = app.Workbooks.Open(src, ReadOnly=True)
            wb.ExportAsFixedFormat(0, out_pdf)
            wb.Close(False)
        finally:
            app.Quit()
    elif ext in (".ppt", ".pptx", ".odp"):
        app = win32com.client.DispatchEx("PowerPoint.Application")
        try:
            pres = app.Presentations.Open(src, ReadOnly=True, WithWindow=False)
            pres.SaveAs(out_pdf, 32)
            pres.Close()
        finally:
            app.Quit()
    else:
        raise ConversionError(f"Formato não suportado pelo Office: {ext}")


def office_available() -> str:
    if find_libreoffice():
        return "LibreOffice"
    if sys.platform.startswith("win"):
        try:
            import winreg
            for prog in ("Word.Application", "Excel.Application"):
                winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog).Close()
            return "Microsoft Office"
        except Exception:
            pass
    return ""


# ------------------------------------------------------------------ -> PDF
def to_pdf(src: str, out_pdf: str) -> str:
    ext = Path(src).suffix.lower()
    if ext == ".pdf":
        shutil.copyfile(src, out_pdf)
        return out_pdf
    if ext in NATIVE_TO_PDF:
        if ext == ".txt":
            _txt_to_pdf(src, out_pdf)
        else:
            d = pymupdf.open(src)
            pdf = pymupdf.open("pdf", d.convert_to_pdf())
            pdf.save(out_pdf, garbage=3, deflate=True)
        return out_pdf
    if ext in OFFICE_TO_PDF:
        errors = []
        if find_libreoffice():
            with tempfile.TemporaryDirectory() as td:
                try:
                    produced = _libreoffice_convert(src, td, "pdf")
                    shutil.move(produced, out_pdf)
                    return out_pdf
                except ConversionError as e:
                    errors.append(str(e))
        if sys.platform.startswith("win"):
            try:
                _msoffice_to_pdf(src, out_pdf)
                return out_pdf
            except Exception as e:
                errors.append(f"Microsoft Office: {e}")
        if ext in (".docx", ".xlsx", ".csv", ".html", ".htm"):
            _basic_to_pdf(src, out_pdf)  # conversão simplificada sem Office
            return out_pdf
        raise ConversionError(
            "Para converter arquivos do Office instale o LibreOffice (gratuito): "
            "https://www.libreoffice.org\n" + "\n".join(errors))
    raise ConversionError(f"Formato não suportado: {ext}")


def _txt_to_pdf(src, out_pdf):
    raw = Path(src).read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    _html_to_pdf("<pre style='font-family:monospace;font-size:10pt;white-space:pre-wrap'>"
                 + _esc(text) + "</pre>", out_pdf)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _html_to_pdf(html: str, out_pdf: str):
    story = pymupdf.Story(html=html)
    writer = pymupdf.DocumentWriter(out_pdf)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (40, 40, -40, -40)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()


def _basic_to_pdf(src, out_pdf):
    """Fallback sem Office: docx (texto/tabelas), xlsx/csv (tabelas) e html."""
    ext = Path(src).suffix.lower()
    if ext in (".html", ".htm"):
        _html_to_pdf(Path(src).read_text("utf-8", errors="replace"), out_pdf)
        return
    parts = ["<style>table{border-collapse:collapse}td{border:1px solid #888;padding:2px 4px;"
             "font-size:9pt}</style>"]
    if ext == ".docx":
        import docx  # python-docx
        d = docx.Document(src)
        for p in d.paragraphs:
            tag = "h2" if p.style.name.lower().startswith("heading") else "p"
            parts.append(f"<{tag}>{_esc(p.text)}</{tag}>")
        for t in d.tables:
            parts.append("<table>" + "".join(
                "<tr>" + "".join(f"<td>{_esc(c.text)}</td>" for c in r.cells) + "</tr>"
                for r in t.rows) + "</table><br/>")
    elif ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(src, data_only=True, read_only=True)
        for ws in wb.worksheets:
            parts.append(f"<h3>{_esc(ws.title)}</h3><table>")
            for row in ws.iter_rows(values_only=True):
                parts.append("<tr>" + "".join(
                    f"<td>{_esc('' if v is None else str(v))}</td>" for v in row) + "</tr>")
            parts.append("</table>")
    elif ext == ".csv":
        import csv
        with open(src, newline="", encoding="utf-8", errors="replace") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            parts.append("<table>")
            for row in csv.reader(f, dialect):
                parts.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>")
            parts.append("</table>")
    _html_to_pdf("".join(parts), out_pdf)


# ------------------------------------------------------------------ PDF ->
def from_pdf(src_pdf: str, fmt: str, out_path: str, dpi: int = 150, progress=None) -> list[str]:
    """Converte um PDF para 'fmt'. Retorna a lista de arquivos gerados."""
    doc = pymupdf.open(src_pdf)
    n = doc.page_count

    def tick(i):
        if progress:
            progress(i, n)

    out = Path(out_path)
    if fmt in ("png", "jpg"):
        files = []
        width = len(str(n))
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            f = out.with_name(f"{out.stem}_{str(i + 1).zfill(width)}.{fmt}")
            if fmt == "jpg":
                pix.save(str(f), jpg_quality=90)
            else:
                pix.save(str(f))
            files.append(str(f))
            tick(i + 1)
        return files
    if fmt == "tiff":
        from PIL import Image
        imgs = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            imgs.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
            tick(i + 1)
        imgs[0].save(out, save_all=True, append_images=imgs[1:], compression="tiff_deflate")
        return [str(out)]
    if fmt == "txt":
        with open(out, "w", encoding="utf-8") as f:
            for i, page in enumerate(doc):
                f.write(page.get_text("text", sort=True))
                f.write("\n\f")
                tick(i + 1)
        return [str(out)]
    if fmt == "html":
        body = []
        for i, page in enumerate(doc):
            body.append(page.get_text("xhtml"))
            tick(i + 1)
        out.write_text("<!DOCTYPE html><html><head><meta charset='utf-8'><title>"
                       f"{_esc(Path(src_pdf).stem)}</title></head><body>"
                       + "<hr/>".join(body) + "</body></html>", "utf-8")
        return [str(out)]
    if fmt == "md":
        try:
            import pymupdf4llm  # type: ignore
            md = pymupdf4llm.to_markdown(doc)
        except Exception:
            md = "\n\n---\n\n".join(p.get_text("text", sort=True) for p in doc)
        out.write_text(md, "utf-8")
        tick(n)
        return [str(out)]
    if fmt == "docx":
        doc.close()
        from pdf2docx import Converter
        cv = Converter(src_pdf)
        try:
            cv.convert(str(out), multi_processing=False)
        finally:
            cv.close()
        tick(n)
        return [str(out)]
    if fmt == "odt":
        doc.close()
        with tempfile.TemporaryDirectory() as td:
            tmp_docx = str(Path(td) / (Path(src_pdf).stem + ".docx"))
            from_pdf(src_pdf, "docx", tmp_docx)
            produced = _libreoffice_convert(tmp_docx, td, "odt")
            shutil.move(produced, out)
        return [str(out)]
    if fmt == "xlsx":
        _pdf_to_xlsx(doc, str(out), tick)
        return [str(out)]
    if fmt == "pptx":
        _pdf_to_pptx(doc, str(out), dpi, tick)
        return [str(out)]
    if fmt == "pdfa":
        doc.save(str(out), garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
                 clean=True, use_objstms=1)
        tick(n)
        return [str(out)]
    raise ConversionError(f"Formato de saída não suportado: {fmt}")


def _pdf_to_xlsx(doc, out, tick):
    """Cada página vira uma planilha; tabelas detectadas viram células, o resto vira linhas."""
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for i, page in enumerate(doc):
        ws = wb.create_sheet(f"Página {i + 1}")
        row = 1
        tables = []
        try:
            tables = page.find_tables().tables
        except Exception:
            pass
        table_rects = [pymupdf.Rect(t.bbox) for t in tables]
        # texto fora das tabelas: trechos agrupados por linha (mesma altura) e
        # distribuídos em colunas conforme a posição horizontal
        spans = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    r = pymupdf.Rect(s["bbox"])
                    if s["text"].strip() and not any(r.intersects(tr) for tr in table_rects):
                        spans.append((r, s["text"].strip()))
        spans.sort(key=lambda it: (it[0].y1, it[0].x0))
        lines = []
        for r, txt in spans:
            if lines and abs(lines[-1][0] - r.y1) <= max(2.0, r.height * 0.35):
                lines[-1][1].append((r.x0, txt))
            else:
                lines.append([r.y1, [(r.x0, txt)]])
        items = [(y, "line", sorted(cells)) for y, cells in lines] + \
                [(t.bbox[1], "table", t) for t in tables]
        for _y, kind, obj in sorted(items, key=lambda it: it[0]):
            if kind == "line":
                for col, (_x, txt) in enumerate(obj, 1):
                    ws.cell(row, col, _number(txt))
                row += 1
            else:
                data = obj.extract()
                for r_i, r in enumerate(data):
                    for c_i, v in enumerate(r):
                        cell = ws.cell(row, c_i + 1, _number(v))
                        if r_i == 0:
                            cell.font = Font(bold=True)
                    row += 1
                row += 1
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(60, max(8, width + 2))
        tick(i + 1)
    wb.save(out)


def _number(v):
    if v is None:
        return None
    s = str(v).strip()
    t = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return int(t) if t.isdigit() else float(t)
    except ValueError:
        return s


def _pdf_to_pptx(doc, out, dpi, tick):
    from pptx import Presentation
    from pptx.util import Emu
    prs = Presentation()
    first = doc[0].rect
    prs.slide_width = Emu(int(first.width * 12700))
    prs.slide_height = Emu(int(first.height * 12700))
    blank = prs.slide_layouts[6]
    with tempfile.TemporaryDirectory() as td:
        for i, page in enumerate(doc):
            img = os.path.join(td, f"p{i}.png")
            page.get_pixmap(dpi=dpi, alpha=False).save(img)
            slide = prs.slides.add_slide(blank)
            slide.shapes.add_picture(img, 0, 0, prs.slide_width, prs.slide_height)
            notes = page.get_text("text").strip()
            if notes:
                slide.notes_slide.notes_text_frame.text = notes
            tick(i + 1)
    prs.save(out)
