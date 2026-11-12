"""PDF -> Excel sem perder nem misturar dados.

Para cada página:
  1. Decide de onde vem o texto: do próprio PDF ou de **OCR completo** da página. O OCR é
     usado quando a página é digitalizada, quando quase não tem texto mas é coberta por
     imagens, ou quando o texto do PDF está ilegível (fontes sem mapa de caracteres).
  2. Encontra tabelas pelas linhas da grade: as linhas vetoriais do PDF e, em páginas
     digitalizadas, as linhas desenhadas na imagem (detectadas com OpenCV).
     Cada palavra vai para a célula em que está, então nada se mistura entre células.
  3. O texto fora das tabelas é organizado em colunas pela posição na página: palavras
     próximas ficam na mesma célula; colunas alinhadas (inclusive números alinhados à
     direita) caem sempre na mesma coluna do Excel.
  4. Números no formato brasileiro (1.234,56 · R$ · % · negativos entre parênteses) viram
     números de verdade; códigos com zeros à esquerda (CPF, CEP, matrícula) e números
     longos continuam como texto, sem perder dígitos; datas viram datas.
"""
from __future__ import annotations

import datetime as dt
import re
import statistics

import pymupdf

OCR_DPI = 300


# ------------------------------------------------------------------ origem do texto
def _garbled(text: str) -> bool:
    if not text:
        return False
    bad = sum(1 for ch in text if ch == "�" or (ord(ch) < 32 and ch not in "\n\t\r"))
    return bad / len(text) > 0.08


def needs_ocr(page: pymupdf.Page) -> bool:
    text = page.get_text("text").strip()
    if len(text) < 20 or _garbled(text):
        return True
    area = abs(page.rect)
    covered = 0.0
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if r.is_empty:
            continue
        covered += abs(r)
        # imagem grande (ex.: tabela digitalizada colada no PDF) sem texto digital por cima:
        # o conteúdo dela só é lido com OCR
        if abs(r) / max(area, 1) > 0.05 and len(page.get_textbox(r).strip()) < 15 and _has_ink(page, r):
            return True
    # página tomada por imagem (digitalização) com pouco texto digital: o texto está na imagem
    return covered / max(area, 1) > 0.5 and len(text) < 300


def _has_ink(page, rect) -> bool:
    """A área tem traços escuros suficientes para conter texto (não é foto clara/fundo)?"""
    try:
        pix = page.get_pixmap(clip=rect, dpi=40, colorspace=pymupdf.csGRAY, alpha=False)
        dark = sum(1 for v in pix.samples if v < 110)
        return 0.005 < dark / max(1, len(pix.samples)) < 0.5
    except Exception:
        return True


def _ocr_langs():
    from . import ocr
    have = ocr.available_langs()
    langs = [c for c in ("por", "eng") if c in have]
    return langs or have[:1]


def _grid_masks(gray, dpi):
    """Máscaras das linhas horizontais e verticais desenhadas na imagem (OpenCV)."""
    import cv2
    bw = cv2.adaptiveThreshold(255 - gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)
    h, w = gray.shape
    out = []
    for horizontal in (True, False):
        size = max(int(dpi * 0.4), (w if horizontal else h) // 25)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (size, 1) if horizontal else (1, size))
        out.append(cv2.dilate(cv2.erode(bw, kernel), kernel))
    return out


def _mask_lines(mask, horizontal, scale):
    import cv2
    lines = []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if horizontal:
            yy = (y + h / 2) * scale
            lines.append(((x * scale, yy), ((x + w) * scale, yy)))
        else:
            xx = (x + w / 2) * scale
            lines.append(((xx, y * scale), (xx, (y + h) * scale)))
    return lines


def ocr_page(page: pymupdf.Page, dpi: int = OCR_DPI):
    """OCR completo da página como aparece na tela. As linhas de grade são detectadas e
    apagadas antes do OCR (o Tesseract costuma pular o texto dentro de tabelas com grade).
    Devolve (palavras, linhas de grade), em pontos, no espaço da página exibida."""
    from . import ocr
    langs = _ocr_langs()
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    lines = []
    try:
        import cv2
        import numpy as np
        rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        hmask, vmask = _grid_masks(gray, dpi)
        scale = 72.0 / dpi
        lines = _mask_lines(hmask, True, scale) + _mask_lines(vmask, False, scale)
        if lines:
            erase = cv2.dilate(cv2.bitwise_or(hmask, vmask), np.ones((5, 5), np.uint8))
            rgb[erase > 0] = 255
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix.width, pix.height, rgb.tobytes(), False)
    except Exception:
        lines = []
    pix.set_dpi(dpi, dpi)
    pdf = pymupdf.open("pdf", pix.pdfocr_tobytes(language="+".join(langs), tessdata=ocr.tessdata_for(langs)))
    words = [(w[0], w[1], w[2], w[3], w[4]) for w in pdf[0].get_text("words") if w[4].strip()]
    return words, lines


def page_words(page: pymupdf.Page, force_ocr: bool | None = None):
    """(palavras [(x0, y0, x1, y1, texto)], linhas de grade da imagem, veio do OCR?)."""
    use_ocr = needs_ocr(page) if force_ocr is None else force_ocr
    if use_ocr:
        try:
            words, lines = ocr_page(page)
            return words, lines, True
        except Exception:
            pass
    words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words") if w[4].strip()]
    return words, [], False


# ------------------------------------------------------------------ tabelas
def _vector_segments(page):
    segs = []
    for d in page.get_drawings():
        for it in d.get("items", []):
            if it[0] == "l":
                segs.append((it[1], it[2]))
            elif it[0] == "re":
                r = pymupdf.Rect(it[1])
                segs += [(r.tl, r.tr), (r.bl, r.br), (r.tl, r.bl), (r.tr, r.br)]
            elif it[0] == "qu":
                q = it[1]
                segs += [(q.ul, q.ur), (q.ll, q.lr), (q.ul, q.ll), (q.ur, q.lr)]
    return segs


def _ruled(rect, segs) -> bool:
    """A tabela tem grade de verdade (linhas horizontais e verticais dentro dela)?
    Evita tratar texto em colunas como tabela, o que criaria colunas falsas."""
    rect = pymupdf.Rect(rect)
    box = rect + (-3, -3, 3, 3)
    hor = ver = 0
    for a, b in segs:
        a, b = pymupdf.Point(a), pymupdf.Point(b)
        if not (box.contains(a) and box.contains(b)):
            continue
        if abs(a.y - b.y) < 1.5 and abs(a.x - b.x) > rect.width * 0.3:
            hor += 1
        elif abs(a.x - b.x) < 1.5 and abs(a.y - b.y) > rect.height * 0.3:
            ver += 1
    return hor >= 2 and ver >= 2


def _grids_of(tables, segs):
    grids = []
    for t in tables:
        rows = [[pymupdf.Rect(c) if c else None for c in r.cells] for r in t.rows]
        if len(rows) >= 2 and max(len(r) for r in rows) >= 2 and _ruled(t.bbox, segs):
            grids.append((pymupdf.Rect(t.bbox), rows))
    return grids


def find_grids(page: pymupdf.Page, words, raster_lines):
    """Tabelas com grade: lista de (retângulo, linhas de células [[bbox|None]]).
    PDF digital: linhas vetoriais da própria página. Página digitalizada: monta uma página
    temporária com as linhas detectadas na imagem e as palavras do OCR."""
    try:
        if not raster_lines:
            return _grids_of(page.find_tables(strategy="lines").tables, _vector_segments(page))
        tmp = pymupdf.open()
        tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
        for a, b in raster_lines:
            tp.draw_line(a, b, width=0.8)
        for x0, y0, x1, y1, text in words:
            h = max(2.0, y1 - y0)
            try:
                tp.insert_text((x0, y1 - h * 0.2), text, fontsize=h * 0.8)
            except Exception:
                pass
        return _grids_of(tp.find_tables(strategy="lines").tables, raster_lines)
    except Exception:
        return []


def _center(w):
    return pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)


def _join_words(words) -> str:
    """Texto de uma célula: palavras em ordem de leitura, quebrando linha onde a célula quebra."""
    if not words:
        return ""
    words = sorted(words, key=lambda w: (w[1], w[0]))
    lines, cur, cur_y = [], [], None
    for w in words:
        h = w[3] - w[1]
        cy = (w[1] + w[3]) / 2
        if cur and abs(cy - cur_y) > h * 0.6:
            lines.append(cur)
            cur = []
        cur.append(w)
        cur_y = cy if len(cur) == 1 else cur_y
    lines.append(cur)
    return "\n".join(" ".join(w[4] for w in sorted(ln, key=lambda w: w[0])) for ln in lines)


def grid_values(rows, words):
    """Distribui as palavras nas células (pelo centro de cada palavra)."""
    ncols = max(len(r) for r in rows)
    cells = [[[] for _ in range(ncols)] for _ in rows]
    for w in words:
        c = _center(w)
        for ri, r in enumerate(rows):
            for ci, rect in enumerate(r):
                if rect is not None and rect.contains(c):
                    cells[ri][ci].append(w)
                    break
            else:
                continue
            break
    return [[_join_words(c) for c in row] for row in cells]


# ------------------------------------------------------------------ texto fora das tabelas
def _segments(words):
    """Agrupa palavras em linhas e, dentro da linha, em trechos (espaços grandes separam)."""
    if not words:
        return []
    heights = [w[3] - w[1] for w in words]
    med_h = statistics.median(heights) or 8
    words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows = []
    for w in words:
        cy = (w[1] + w[3]) / 2
        if rows and abs(cy - rows[-1][0]) <= med_h * 0.5:
            rows[-1][1].append(w)
        else:
            rows.append([cy, [w]])
    out = []
    for cy, ws in rows:
        ws.sort(key=lambda w: w[0])
        segs = []
        for w in ws:
            h = w[3] - w[1]
            # espaço entre palavras ~0,3 da altura; entre colunas, bem maior
            if segs and w[0] - segs[-1][-1][2] <= max(h, med_h) * 1.5:
                segs[-1].append(w)
            else:
                segs.append([w])
        out.append((cy, [(s[0][0], s[-1][2], " ".join(x[4] for x in s)) for s in segs]))
    return out


def _cluster(values, tol):
    """[(mediana, quantidade)] de valores próximos."""
    vals = sorted(values)
    groups = []
    for v in vals:
        if groups and v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [(statistics.median(g), len(g)) for g in groups]


NUM_RE = re.compile(r"^[-+(]?\s*(R\$|US\$|€|\$)?\s*[-+]?[\d.,]+\s*%?\)?$")


def _columns(lines, page_width):
    """Colunas comuns a todas as linhas: bordas esquerdas alinhadas e, para números,
    bordas direitas alinhadas. Devolve a função que dá a coluna de cada trecho."""
    tol = max(4.0, page_width * 0.012)
    segs_all = [seg for _y, segs in lines for seg in segs]
    lefts = _cluster([s[0] for s in segs_all if not NUM_RE.match(s[2])], tol)
    rights = _cluster([s[1] for s in segs_all if NUM_RE.match(s[2])], tol)
    anchors = [("L", x) for x, _n in lefts] + [("R", x) for x, _n in rights]
    if not anchors:
        return lambda seg: 0
    left_count = {x: n for x, n in lefts}

    def near(v, clusters):
        return min(clusters, key=lambda c: abs(c[0] - v)) if clusters else None

    def best(seg):
        x0, x1, text = seg
        if NUM_RE.match(text):
            r = near(x1, rights)
            if r and abs(r[0] - x1) <= tol:
                return ("R", r[0])
        else:
            lft = near(x0, lefts)
            r = near(x1, rights)
            # rótulo alinhado à direita sobre uma coluna de números (ex.: "Total" acima dos valores)
            if r and abs(r[0] - x1) <= tol and r[1] >= 2 and (not lft or left_count[lft[0]] <= 1):
                return ("R", r[0])
            if lft and abs(lft[0] - x0) <= tol:
                return ("L", lft[0])
        return min(anchors, key=lambda a: abs((x1 if a[0] == "R" else x0) - a[1]))

    # ordena as colunas pela posição em que seus trechos começam
    start = {}
    for seg in segs_all:
        a = best(seg)
        start[a] = min(start.get(a, seg[0]), seg[0])
    index = {a: i for i, a in enumerate(sorted(start, key=lambda a: (start[a], a[1])))}
    return lambda seg: index[best(seg)]


# ------------------------------------------------------------------ valores
DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")


def cell_value(text):
    """(valor, formato de número do Excel ou None)."""
    if text is None:
        return None, None
    s = str(text).strip()
    if not s:
        return None, None
    m = DATE_RE.match(s)
    if m:
        d, mth, y = (int(g) for g in m.groups())
        if y < 100:
            y += 2000
        try:
            return dt.datetime(y, mth, d), "DD/MM/YYYY"
        except ValueError:
            return s, None
    if not NUM_RE.match(s):
        return s, None
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    cur = "R$" if "R$" in s else ("US$" if "US$" in s else ("€" if "€" in s else ("$" if "$" in s else "")))
    pct = s.endswith("%") or s.endswith("%)")
    digits = re.sub(r"[^\d.,]", "", s)
    if not digits or not any(ch.isdigit() for ch in digits):
        return s, None
    # zeros à esquerda e números longos (CPF, CEP, conta, código de barras): texto, sem perder dígitos
    plain = digits.replace(".", "").replace(",", "")
    if (len(plain) > 1 and plain.startswith("0") and not re.match(r"^0[,.]\d", digits)) or len(plain) > 15:
        return s, None
    if "," in digits and "." in digits:     # o último separador é o decimal
        dec = "," if digits.rfind(",") > digits.rfind(".") else "."
    elif "," in digits:                     # padrão brasileiro: vírgula decimal
        dec = ","
    elif "." in digits:                     # 1.234 / 1.234.567 = milhar; 3.14 = decimal
        dec = "" if re.match(r"^\d{1,3}(\.\d{3})+$", digits) else "."
    else:
        dec = ""
    if dec and digits.count(dec) > 1:
        return s, None
    has_thou = any(ch in (digits.replace(dec, "") if dec else digits) for ch in ".,")
    int_part, _, frac = digits.partition(dec) if dec else (digits, "", "")
    num = re.sub(r"[.,]", "", int_part) + ("." + frac if dec else "")
    try:
        val = float(num) if dec else int(num)
    except ValueError:
        return s, None
    if neg:
        val = -val
    if pct:
        return val / 100, "0.00%" if dec else "0%"
    if cur:
        return val, f'"{cur}" #,##0.00'
    if dec:
        return val, "#,##0." + "0" * max(1, min(len(frac), 6))
    return val, "#,##0" if has_thou else None


# ------------------------------------------------------------------ planilha
def page_rows(page: pymupdf.Page, force_ocr=None):
    """Linhas da planilha para uma página: [(tipo, valores)] com tipo 'texto' | 'cabecalho'
    | 'tabela' | 'vazio'. Também devolve se usou OCR."""
    words, raster_lines, used_ocr = page_words(page, force_ocr)
    grids = find_grids(page, words, raster_lines)
    inside = [set() for _ in grids]
    free = []
    for wi, w in enumerate(words):
        c = _center(w)
        for gi, (rect, _rows) in enumerate(grids):
            if rect.contains(c):
                inside[gi].add(wi)
                break
        else:
            free.append(w)
    blocks = []
    for gi, (rect, rows) in enumerate(grids):
        vals = grid_values(rows, [words[i] for i in inside[gi]])
        vals = [r for r in vals if any(v.strip() for v in r)]
        if vals:
            blocks.append((rect.y0, "grid", vals))
    lines = _segments(free)
    if lines:
        col_of = _columns(lines, page.rect.width)
        for cy, segs in lines:
            row = {}
            for seg in segs:
                c = col_of(seg)
                row[c] = (row[c] + " " + seg[2]) if c in row else seg[2]
            width = max(row) + 1
            blocks.append((cy, "line", [row.get(i, "") for i in range(width)]))
    blocks.sort(key=lambda b: b[0])
    out = []
    for _y, kind, data in blocks:
        if kind == "grid":
            if out and out[-1][0] != "vazio":
                out.append(("vazio", []))
            # título dentro da tabela (só a primeira célula preenchida) fica como texto
            while len(data) > 1 and len(data[0]) > 1 and sum(1 for v in data[0] if v.strip()) == 1:
                out.append(("texto", [v for v in data[0] if v.strip()]))
                data = data[1:]
            out.append(("cabecalho", data[0]))
            out += [("tabela", r) for r in data[1:]]
            out.append(("vazio", []))
        else:
            out.append(("texto", data))
    return out, used_ocr


def pdf_to_xlsx(doc: pymupdf.Document, out: str, tick=None, force_ocr=None) -> dict:
    """Uma planilha por página. Devolve um resumo (páginas com OCR, tabelas)."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    thin = Side(style="thin", color="999999")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="F2F2F2")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    summary = {"paginas_ocr": [], "tabelas": 0}
    for i, page in enumerate(doc):
        ws = wb.create_sheet(f"Página {i + 1}")
        rows, used_ocr = page_rows(page, force_ocr)
        if used_ocr:
            summary["paginas_ocr"].append(i + 1)
        widths = {}
        for r, (kind, values) in enumerate(rows, 1):
            if kind == "cabecalho":
                summary["tabelas"] += 1
            for c, text in enumerate(values, 1):
                val, fmt = cell_value(text) if kind != "cabecalho" else ((text or None), None)
                if val is None:
                    if kind in ("tabela", "cabecalho"):
                        ws.cell(r, c).border = border
                    continue
                cell = ws.cell(r, c, val)
                if fmt:
                    cell.number_format = fmt
                if kind in ("tabela", "cabecalho"):
                    cell.border = border
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                if kind == "cabecalho":
                    cell.font = Font(bold=True)
                    cell.fill = head_fill
                longest = max((len(x) for x in str(text).split("\n")), default=0)
                widths[c] = max(widths.get(c, 8), min(60, longest + 2))
        for c, w in widths.items():
            ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = w
        if tick:
            tick(i + 1)
    wb.save(out)
    return summary
