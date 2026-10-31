"""Modelo de documento: operações de páginas, edição, desfazer/refazer e salvamento."""
from __future__ import annotations

import datetime as dt
import os
import tempfile
import zlib
from pathlib import Path

import pymupdf

from . import APP_NAME, __version__
from .config import human_size, log_save, now_str
from .fonts import ResolvedFont

MAX_UNDO = 20


def parse_ranges(text: str, page_count: int) -> list[list[int]]:
    """'1-3, 5, 8-' -> [[0,1,2],[4],[7..n-1]] (índices base 0)."""
    groups = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a.strip() else 1
            b = int(b) if b.strip() else page_count
        else:
            a = b = int(part)
        if not (1 <= a <= page_count and 1 <= b <= page_count):
            raise ValueError(f"Intervalo fora do documento: {part}")
        step = 1 if b >= a else -1
        groups.append(list(range(a - 1, b - 1 + step, step)))
    if not groups:
        raise ValueError("Nenhum intervalo informado")
    return groups


def open_any(path: str) -> pymupdf.Document:
    """Abre PDF (sem travar o arquivo no Windows) ou converte formatos suportados nativamente
    (imagens, XPS, EPUB, CBZ, FB2, SVG, TXT) em PDF na memória."""
    data = Path(path).read_bytes()
    ext = Path(path).suffix.lower().lstrip(".")
    doc = pymupdf.open(stream=data, filetype=ext or "pdf")
    if not doc.is_pdf:
        pdf = pymupdf.open("pdf", doc.convert_to_pdf())
        doc.close()
        doc = pdf
    return doc


class PdfDocument:
    def __init__(self, path: str | None = None, doc: pymupdf.Document | None = None):
        self.path = path
        self.doc = doc if doc is not None else (open_any(path) if path else pymupdf.open())
        self.modified = False
        self.edits: list[str] = []       # descrição das alterações desde o último salvamento
        self._undo: list[tuple[bytes, str]] = []
        self._redo: list[tuple[bytes, str]] = []
        self.password_needed = self.doc.needs_pass
        self.original_size = os.path.getsize(path) if path and os.path.exists(path) else 0

    # ---------------- info ----------------
    @property
    def page_count(self):
        return self.doc.page_count

    @property
    def title(self):
        return Path(self.path).name if self.path else "Sem título.pdf"

    def is_native_pdf(self):
        return bool(self.path) and self.path.lower().endswith(".pdf")

    # ---------------- histórico ----------------
    def checkpoint(self, description: str):
        """Chame ANTES de alterar o documento."""
        self._undo.append((self.doc.tobytes(), description))
        if len(self._undo) > MAX_UNDO:
            self._undo.pop(0)
        self._redo.clear()
        self.edits.append(description)
        self.modified = True

    def _restore(self, data: bytes):
        self.doc.close()
        self.doc = pymupdf.open("pdf", data)

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if not self._undo:
            return None
        data, desc = self._undo.pop()
        self._redo.append((self.doc.tobytes(), desc))
        self._restore(data)
        if self.edits:
            self.edits.pop()
        self.modified = True
        return desc

    def redo(self):
        if not self._redo:
            return None
        data, desc = self._redo.pop()
        self._undo.append((self.doc.tobytes(), desc))
        self._restore(data)
        self.edits.append(desc)
        self.modified = True
        return desc

    # ---------------- páginas ----------------
    def move_pages(self, rows: list[int], target: int):
        """Move as páginas 'rows' para antes da posição 'target' (base 0)."""
        rows = sorted(set(rows))
        order = list(range(self.page_count))
        moving = [order[r] for r in rows]
        rest = [p for p in order if p not in moving]
        insert_at = target - sum(1 for r in rows if r < target)
        new_order = rest[:insert_at] + moving + rest[insert_at:]
        if new_order == order:
            return None
        self.checkpoint(f"Reorganizou {len(rows)} página(s)")
        self.doc.select(new_order)
        return list(range(insert_at, insert_at + len(moving)))

    def set_order(self, new_order: list[int], description="Reorganizou páginas"):
        self.checkpoint(description)
        self.doc.select(new_order)

    def rotate(self, rows: list[int], angle: int):
        self.checkpoint(f"Girou {len(rows)} página(s) em {angle}°")
        for r in rows:
            p = self.doc[r]
            p.set_rotation((p.rotation + angle) % 360)

    def delete(self, rows: list[int]):
        if len(rows) >= self.page_count:
            raise ValueError("Não é possível excluir todas as páginas.")
        self.checkpoint(f"Excluiu {len(rows)} página(s)")
        self.doc.delete_pages(sorted(rows))

    def duplicate(self, rows: list[int]):
        self.checkpoint(f"Duplicou {len(rows)} página(s)")
        for r in sorted(rows, reverse=True):
            self.doc.fullcopy_page(r, r + 1)

    def insert_blank(self, at: int):
        self.checkpoint("Inseriu página em branco")
        ref = self.doc[min(at, self.page_count - 1)] if self.page_count else None
        w, h = (ref.rect.width, ref.rect.height) if ref else pymupdf.paper_size("a4")
        self.doc.new_page(at, width=w, height=h)

    def insert_file(self, path: str, at: int, pages: list[int] | None = None):
        src = open_any(path)
        self.checkpoint(f"Inseriu {Path(path).name}")
        if pages is None:
            self.doc.insert_pdf(src, start_at=at)
        else:
            for i, p in enumerate(pages):
                self.doc.insert_pdf(src, from_page=p, to_page=p, start_at=at + i)
        src.close()

    def extract(self, rows: list[int]) -> pymupdf.Document:
        out = pymupdf.open()
        for r in rows:
            out.insert_pdf(self.doc, from_page=r, to_page=r)
        return out

    def crop(self, rows, rect: pymupdf.Rect):
        self.checkpoint("Recortou página(s)")
        for r in rows:
            self.doc[r].set_cropbox(rect & self.doc[r].mediabox)

    # ---------------- conteúdo ----------------
    @staticmethod
    def _text_band(span) -> pymupdf.Rect:
        """Faixa central do trecho (entre a linha de base e a altura do 'x').

        Remover só essa faixa apaga os caracteres do trecho sem atingir as linhas de
        texto vizinhas (cujas caixas costumam se sobrepor) nem linhas e marcações."""
        bbox = pymupdf.Rect(span["bbox"])
        d = span.get("dir", (1, 0))
        if round(d[0]) == 1 and round(d[1]) == 0:
            oy, size = span["origin"][1], span["size"]
            return pymupdf.Rect(bbox.x0 + 0.4, oy - size * 0.55, bbox.x1 - 0.4, oy - size * 0.12)
        w, h = bbox.width * 0.2, bbox.height * 0.2
        return pymupdf.Rect(bbox.x0 + w, bbox.y0 + h, bbox.x1 - w, bbox.y1 - h)

    def available_width(self, page_no: int, span) -> float:
        """Largura livre a partir do início do trecho até o próximo obstáculo à direita:
        outro texto na mesma linha, borda de tabela/retângulo, linha vertical ou margem."""
        page = self.doc[page_no]
        bbox = pymupdf.Rect(span["bbox"])
        band = self._text_band(span)
        x0 = bbox.x0
        limit = page.rect.width - 2 if page.rotation in (0, 180) else page.rect.height - 2
        limit = min(limit, page.mediabox.x1 - 2)
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    r = pymupdf.Rect(s["bbox"])
                    if not s["text"].strip() or r == bbox:
                        continue
                    if r.x0 > bbox.x0 + 1 and r.y0 < band.y1 and r.y1 > band.y0:
                        limit = min(limit, r.x0)
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []
        for dr in drawings:
            for it in dr.get("items", []):
                if it[0] == "l":
                    p1, p2 = it[1], it[2]
                    if abs(p1.x - p2.x) < 1.5 and min(p1.y, p2.y) <= band.y1 and max(p1.y, p2.y) >= band.y0:
                        if p1.x > x0 + 1:
                            limit = min(limit, p1.x)
                elif it[0] in ("re", "qu"):
                    r = pymupdf.Rect(it[1].rect if it[0] == "qu" else it[1])
                    if r.y0 <= band.y1 and r.y1 >= band.y0:
                        for edge in (r.x0, r.x1):
                            if edge > x0 + 1:
                                limit = min(limit, edge)
        return max(bbox.width, limit - x0 - 1.5)

    @staticmethod
    def text_width(font: ResolvedFont, text: str, size: float) -> float:
        try:
            return font.pymupdf_font().text_length(text, fontsize=size)
        except Exception:
            return len(text) * size * 0.5

    def fit_size(self, page_no, span, text, font, size) -> tuple[float, float, float]:
        """(tamanho ajustado, largura necessária, largura disponível)."""
        need = self.text_width(font, text, size)
        avail = self.available_width(page_no, span)
        if need <= avail or need <= 0:
            return size, need, avail
        return max(2.0, round(size * avail / need, 1)), need, avail

    def collisions(self, page_no: int, rect) -> int:
        """Quantos textos/desenhos existentes ficariam sob o retângulo informado."""
        page = self.doc[page_no]
        rect = pymupdf.Rect(rect)
        n = sum(1 for w in page.get_text("words") if pymupdf.Rect(w[:4]).intersects(rect))
        try:
            n += sum(1 for d in page.get_drawings() if pymupdf.Rect(d["rect"]).intersects(rect)
                     and pymupdf.Rect(d["rect"]).get_area() < rect.get_area() * 4)
        except Exception:
            pass
        return n

    def replace_text(self, page_no: int, span: dict, new_text: str, font: ResolvedFont,
                     size: float, color, fit=True) -> float:
        """Remove o trecho original e escreve o novo com a fonte reconhecida, sem apagar
        linhas, tabelas, marcações ou textos vizinhos. Retorna o tamanho de fonte usado."""
        new_text = " ".join(new_text.split("\n")).rstrip()
        if fit:
            size = self.fit_size(page_no, span, new_text, font, size)[0]
        self.checkpoint(f"Editou texto na página {page_no + 1}")
        page = self.doc[page_no]
        page.add_redact_annot(self._text_band(span), fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        if new_text:
            self._write_text(page, span["origin"], new_text, font, size, color, span.get("dir", (1, 0)))
        return size

    def add_text(self, page_no: int, origin, text: str, font: ResolvedFont, size: float, color):
        self.checkpoint(f"Adicionou texto na página {page_no + 1}")
        self._write_text(self.doc[page_no], origin, text, font, size, color)

    def text_rect(self, origin, text, font, size) -> pymupdf.Rect:
        lines = text.split("\n") or [""]
        w = max(self.text_width(font, ln, size) for ln in lines)
        x, y = origin
        return pymupdf.Rect(x, y - size * 0.9, x + w, y + size * 1.2 * (len(lines) - 1) + size * 0.25)

    @staticmethod
    def _write_text(page, origin, text, font: ResolvedFont, size, color, direction=(1, 0)):
        rotate = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}.get(
            (round(direction[0]), round(direction[1])), 0)
        kw = dict(fontsize=size, color=color, rotate=rotate)
        if font.fontbuffer or font.fontfile:
            # nome estável por fonte (o hash() do Python muda a cada execução)
            data = font.fontbuffer or font.fontfile.encode()
            name = "Vt" + format(zlib.crc32(data[:65536]) & 0xFFFFFFFF, "x")
            page.insert_font(fontname=name, fontbuffer=font.fontbuffer, fontfile=font.fontfile)
            kw["fontname"] = name
        else:
            kw["fontname"] = font.base14 or "helv"
        page.insert_text(pymupdf.Point(origin), text, **kw)

    def highlight(self, page_no, rect, color=(1, 0.9, 0)):
        self.checkpoint(f"Destacou trecho na página {page_no + 1}")
        page = self.doc[page_no]
        words = [pymupdf.Rect(w[:4]) for w in page.get_text("words") if pymupdf.Rect(w[:4]).intersects(rect)]
        annot = page.add_highlight_annot(words if words else rect)
        annot.set_colors(stroke=color)
        annot.update()

    def add_rect(self, page_no, rect, stroke=(0.85, 0.1, 0.15), fill=None, width=1.5):
        self.checkpoint(f"Desenhou retângulo na página {page_no + 1}")
        page = self.doc[page_no]
        page.draw_rect(rect, color=stroke, fill=fill, width=width)

    def whiteout(self, page_no, rect):
        """Apaga definitivamente o conteúdo da área (redação com fundo branco)."""
        self.checkpoint(f"Apagou área na página {page_no + 1}")
        page = self.doc[page_no]
        page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)

    def add_note(self, page_no, point, text):
        self.checkpoint(f"Adicionou nota na página {page_no + 1}")
        a = self.doc[page_no].add_text_annot(point, text)
        a.set_info(title=os.environ.get("USERNAME") or os.environ.get("USER") or APP_NAME)
        a.update()

    def add_image(self, page_no, rect, image_path):
        self.checkpoint(f"Inseriu imagem na página {page_no + 1}")
        self.doc[page_no].insert_image(rect, filename=image_path, keep_proportion=True)

    def set_metadata(self, meta: dict):
        self.checkpoint("Alterou propriedades do documento")
        m = dict(self.doc.metadata or {})
        m.update(meta)
        self.doc.set_metadata(m)

    # ---------------- salvamento ----------------
    def save(self, path: str | None = None, password: str | None = None) -> dict:
        """Salva (atomicamente) e devolve um resumo do salvamento."""
        path = path or self.path
        if not path:
            raise ValueError("Caminho não informado")
        meta = dict(self.doc.metadata or {})
        now = "D:" + dt.datetime.now().strftime("%Y%m%d%H%M%S")
        meta["modDate"] = now
        meta["producer"] = f"{APP_NAME} {__version__}"
        if not meta.get("creationDate"):
            meta["creationDate"] = now
        if not meta.get("creator"):
            meta["creator"] = APP_NAME
        self.doc.set_metadata(meta)

        try:
            self.doc.subset_fonts()  # embute só os glifos usados (arquivo menor)
        except Exception:
            pass
        opts = dict(garbage=3, deflate=True, clean=False)
        if password:
            opts.update(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
        folder = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=folder)
        os.close(fd)
        try:
            self.doc.save(tmp, **opts)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

        new_size = os.path.getsize(path)
        info = {
            "arquivo": os.path.abspath(path),
            "data_hora": now_str(),
            "paginas": self.page_count,
            "tamanho_anterior": human_size(self.original_size) if self.original_size else "—",
            "tamanho_atual": human_size(new_size),
            "alteracoes": list(self.edits) or ["Nenhuma alteração (salvo novamente)"],
            "protegido_senha": bool(password),
            "produtor": meta["producer"],
        }
        log_save(info)
        self.path = path
        self.original_size = new_size
        self.modified = False
        self.edits.clear()
        return info


def merge_files(paths: list[str], out_path: str, ranges: dict[str, str] | None = None,
                bookmarks=True) -> dict:
    """Une vários arquivos (PDF ou formatos abertos pelo PyMuPDF) em um único PDF."""
    out = pymupdf.open()
    toc = []
    for p in paths:
        src = open_any(p)
        start = out.page_count
        sel = None
        if ranges and ranges.get(p):
            sel = [i for g in parse_ranges(ranges[p], src.page_count) for i in g]
        if sel is None:
            out.insert_pdf(src)
        else:
            for i in sel:
                out.insert_pdf(src, from_page=i, to_page=i)
        if bookmarks:
            toc.append([1, Path(p).stem, start + 1])
        src.close()
    if bookmarks and toc:
        out.set_toc(toc)
    doc = PdfDocument(doc=out)
    doc.edits = [f"Uniu {len(paths)} arquivo(s): " + ", ".join(Path(p).name for p in paths)]
    return doc.save(out_path)


def split_document(doc: pymupdf.Document, groups: list[list[int]], out_dir: str, base: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    width = len(str(len(groups)))
    for n, g in enumerate(groups, 1):
        part = pymupdf.open()
        for i in g:
            part.insert_pdf(doc, from_page=i, to_page=i)
        label = f"{g[0] + 1}" if len(g) == 1 else f"{g[0] + 1}-{g[-1] + 1}"
        path = os.path.join(out_dir, f"{base}_parte{str(n).zfill(width)}_pag{label}.pdf")
        part.set_metadata({"producer": f"{APP_NAME} {__version__}", "title": f"{base} ({label})"})
        part.save(path, garbage=3, deflate=True)
        part.close()
        written.append(path)
    log_save({"arquivo": out_dir, "data_hora": now_str(), "paginas": doc.page_count,
              "alteracoes": [f"Separou '{base}' em {len(written)} arquivo(s)"]})
    return written


def split_groups(mode: str, page_count: int, value: str = "") -> list[list[int]]:
    if mode == "each":
        return [[i] for i in range(page_count)]
    if mode == "every":
        n = max(1, int(value))
        return [list(range(i, min(i + n, page_count))) for i in range(0, page_count, n)]
    if mode == "ranges":
        return parse_ranges(value, page_count)
    if mode == "half":
        h = (page_count + 1) // 2
        return [list(range(h)), list(range(h, page_count))]
    raise ValueError(mode)
