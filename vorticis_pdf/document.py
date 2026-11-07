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
    if not path:
        raise ValueError("Nenhum arquivo informado")
    data = Path(path).read_bytes()
    ext = Path(path).suffix.lower().lstrip(".")
    doc = pymupdf.open(stream=data, filetype=ext or "pdf")
    if not doc.is_pdf:
        pdf = pymupdf.open("pdf", doc.convert_to_pdf())
        doc.close()
        doc = pdf
    return doc


# ====================================================================== formas e anotações
SHAPES = {
    "rect": "Retângulo", "ellipse": "Elipse / círculo", "line": "Linha", "arrow": "Seta",
    "double_arrow": "Seta dupla", "triangle": "Triângulo", "diamond": "Losango", "star": "Estrela",
    "check": "Visto (✓)", "cross": "Xis (✗)",
}
SHAPE_TYPES = {"Square", "Circle", "Line", "Polygon", "PolyLine", "Ink", "FreeText", "Text",
               "Stamp", "Highlight", "Underline", "StrikeOut", "Squiggly", "Caret", "FileAttachment"}
DEFAULT_STYLE = {"stroke": (0.84, 0.14, 0.18), "fill": None, "width": 2.0, "opacity": 1.0, "dashed": False}


def shape_points(kind, p1, p2):
    """Vértices (para polígonos/traços) de uma forma desenhada de p1 até p2."""
    x0, y0 = min(p1[0], p2[0]), min(p1[1], p2[1])
    x1, y1 = max(p1[0], p2[0]), max(p1[1], p2[1])
    w, h = x1 - x0, y1 - y0
    cx, cy = x0 + w / 2, y0 + h / 2
    if kind == "triangle":
        return [(cx, y0), (x1, y1), (x0, y1)]
    if kind == "diamond":
        return [(cx, y0), (x1, cy), (cx, y1), (x0, cy)]
    if kind == "star":
        import math
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            r = 1.0 if i % 2 == 0 else 0.4
            pts.append((cx + r * w / 2 * math.cos(ang), cy + r * h / 2 * math.sin(ang)))
        return pts
    if kind == "check":
        return [[(x0, y0 + h * 0.55), (x0 + w * 0.38, y1), (x1, y0)]]
    if kind == "cross":
        return [[(x0, y0), (x1, y1)], [(x1, y0), (x0, y1)]]
    return [p1, p2]


def _apply_style(annot, style, author=""):
    s = dict(DEFAULT_STYLE, **(style or {}))
    annot.set_border(width=s["width"], dashes=[4, 3] if s["dashed"] else None)
    fill = s["fill"]
    t = annot.type[1]
    if t in ("Line",):  # o "preenchimento" da linha é a cor das pontas da seta
        fill = s["stroke"]
    if t in ("Ink", "PolyLine"):
        annot.set_colors(stroke=s["stroke"])
    else:
        annot.set_colors(stroke=s["stroke"], fill=fill)
    annot.set_opacity(s["opacity"])
    annot.set_info(title=author or os.environ.get("USERNAME") or os.environ.get("USER") or APP_NAME,
                   subject="Forma")
    annot.update()
    return annot


def _annot_style(annot) -> dict:
    colors, border = annot.colors or {}, annot.border or {}
    op = annot.opacity
    return {"stroke": tuple(colors.get("stroke") or (0, 0, 0)),
            "fill": tuple(colors["fill"]) if colors.get("fill") else None,
            "width": border.get("width", 1) if border.get("width", -1) >= 0 else 1,
            "opacity": op if op is not None and op >= 0 else 1.0,
            "dashed": bool(border.get("dashes"))}


def _shift(points, dx, dy):
    if points and isinstance(points[0], (list, tuple)) and points[0] and isinstance(points[0][0], (list, tuple)):
        return [[(x + dx, y + dy) for x, y in stroke] for stroke in points]
    return [(x + dx, y + dy) for x, y in points]


def _find_annot(page, xref):
    for a in page.annots():
        if a.xref == xref:
            return a
    return None


# caracteres que muitas fontes (ex.: Arial) desenham com o mesmo glifo; ao embutir, o PDF
# passava a "ler" o espaço como espaço não separável (e o hífen como hífen invisível),
# quebrando a busca e a cópia do texto editado.
_SAME_GLYPH = ((0x20, (0xA0, 0x2007, 0x202F)), (0x2D, (0xAD, 0x2010, 0x2011)))


def _fix_tounicode(doc, font_xref, font):
    try:
        f = font.pymupdf_font()
        kind, ref = doc.xref_get_key(font_xref, "ToUnicode")
        if kind != "xref":
            return
        tu = int(ref.split()[0])
        cmap = doc.xref_stream(tu).decode("latin-1")
        changed = cmap
        for good, bads in _SAME_GLYPH:
            gid = f.has_glyph(good)
            if not gid:
                continue
            for bad in bads:
                if f.has_glyph(bad) == gid:
                    for g in (f"{gid:04x}", f"{gid:04X}"):
                        for b in (f"{bad:04x}", f"{bad:04X}"):
                            changed = changed.replace(f"<{g}> <{b}>", f"<{g}> <{good:04x}>")
        if changed != cmap:
            doc.update_stream(tu, changed.encode("latin-1"))
    except Exception:
        pass  # nunca impede a edição


class _ShapeOps:
    """Operações de formas/anotações (misturadas em PdfDocument)."""

    def add_shape(self, page_no, kind, p1, p2, style=None):
        self.checkpoint(f"Inseriu forma ({SHAPES.get(kind, kind)}) na página {page_no + 1}")
        page = self.doc[page_no]
        r = pymupdf.Rect(p1, p2)
        r.normalize()
        if kind == "rect":
            a = page.add_rect_annot(r)
        elif kind == "ellipse":
            a = page.add_circle_annot(r)
        elif kind in ("line", "arrow", "double_arrow"):
            a = page.add_line_annot(pymupdf.Point(p1), pymupdf.Point(p2))
            le = pymupdf.PDF_ANNOT_LE_CLOSED_ARROW
            if kind == "arrow":
                a.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, le)
            elif kind == "double_arrow":
                a.set_line_ends(le, le)
        elif kind in ("triangle", "diamond", "star"):
            a = page.add_polygon_annot(shape_points(kind, p1, p2))
        elif kind in ("check", "cross"):
            a = page.add_ink_annot(shape_points(kind, p1, p2))
        else:
            raise ValueError(kind)
        return _apply_style(a, style).xref

    def add_ink(self, page_no, points, style=None):
        self.checkpoint(f"Desenho livre na página {page_no + 1}")
        a = self.doc[page_no].add_ink_annot([[(float(x), float(y)) for x, y in points]])
        return _apply_style(a, style).xref

    def markup_text(self, page_no, rects, kind="highlight", color=None):
        names = {"highlight": "Destacou", "underline": "Sublinhou", "strikeout": "Riscou"}
        self.checkpoint(f"{names[kind]} texto na página {page_no + 1}")
        page = self.doc[page_no]
        rects = [pymupdf.Rect(r) for r in rects]
        fn = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
              "strikeout": page.add_strikeout_annot}[kind]
        a = fn(rects)
        default = {"highlight": (1, 0.9, 0), "underline": (0.1, 0.35, 0.9), "strikeout": (0.85, 0.1, 0.15)}
        a.set_colors(stroke=color or default[kind])
        a.update()
        return a.xref

    def delete_annot(self, page_no, xref):
        page = self.doc[page_no]
        a = _find_annot(page, xref)
        if a is None:
            return
        self.checkpoint(f"Excluiu {a.type[1]} na página {page_no + 1}")
        page.delete_annot(a)

    def move_annot(self, page_no, xref, dx, dy) -> int:
        """Move uma anotação; retorna o xref (pode mudar ao recriar linhas/polígonos)."""
        page = self.doc[page_no]
        a = _find_annot(page, xref)
        if a is None or (abs(dx) < 0.01 and abs(dy) < 0.01):
            return xref
        self.checkpoint(f"Moveu {a.type[1]} na página {page_no + 1}")
        t = a.type[1]
        if t in ("Line", "Polygon", "PolyLine", "Ink"):
            style, ends, info = _annot_style(a), a.line_ends, a.info
            verts = _shift(a.vertices, dx, dy)
            page.delete_annot(a)
            if t == "Line":
                n = page.add_line_annot(pymupdf.Point(verts[0]), pymupdf.Point(verts[1]))
                if ends:
                    n.set_line_ends(*ends)
            elif t == "Polygon":
                n = page.add_polygon_annot(verts)
            elif t == "PolyLine":
                n = page.add_polyline_annot(verts)
            else:
                n = page.add_ink_annot(verts)
            return _apply_style(n, style, info.get("title", "")).xref
        if t in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
            return xref  # marcações de texto ficam presas ao texto
        # o PyMuPDF expande o retângulo em meia espessura de borda: compensamos
        w = (a.border or {}).get("width", 0) / 2 if t in ("Square", "Circle") else 0
        r = a.rect + (dx, dy, dx, dy)
        a.set_rect(r + (w, w, -w, -w) if w and w > 0 else r)
        a.update()
        return xref

    def resize_annot(self, page_no, xref, rect):
        page = self.doc[page_no]
        a = _find_annot(page, xref)
        if a is None or a.type[1] not in ("Square", "Circle", "FreeText", "Stamp"):
            return
        self.checkpoint(f"Redimensionou {a.type[1]} na página {page_no + 1}")
        w = (a.border or {}).get("width", 0) / 2 if a.type[1] in ("Square", "Circle") else 0
        r = pymupdf.Rect(rect)
        r.normalize()
        a.set_rect(r + (w, w, -w, -w) if w and w > 0 else r)
        a.update()

    def restyle_annot(self, page_no, xref, **changes):
        page = self.doc[page_no]
        a = _find_annot(page, xref)
        if a is None:
            return
        self.checkpoint(f"Alterou {a.type[1]} na página {page_no + 1}")
        if a.type[1] in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
            if "stroke" in changes:
                a.set_colors(stroke=changes["stroke"])
            if "opacity" in changes:
                a.set_opacity(changes["opacity"])
            a.update()
            return
        style = _annot_style(a)
        style.update(changes)
        _apply_style(a, style, a.info.get("title", ""))



class PdfDocument(_ShapeOps):
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
        return Path(self.path).name if self.path else (getattr(self, "display_name", "") or "Sem título.pdf")

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
        self.checkpoint(f"Editou texto na página {page_no + 1}")
        return self._replace_span(page_no, span, new_text, font, size, color, fit)

    def replace_texts(self, items: list[dict], fit=True) -> int:
        """Edita vários trechos de uma vez (um único passo de desfazer).
        items: [{'page', 'span', 'text', 'font', 'size', 'color'}]. Retorna quantos mudaram."""
        if not items:
            return 0
        pages = sorted({it["page"] + 1 for it in items})
        where = f"página {pages[0]}" if len(pages) == 1 else f"{len(pages)} páginas"
        self.checkpoint(f"Editou {len(items)} texto(s) simultaneamente ({where})")
        # da direita para a esquerda: cada trecho ainda vê o vizinho original ao se ajustar
        for it in sorted(items, key=lambda i: (i["page"], -i["span"]["bbox"][0])):
            self._replace_span(it["page"], it["span"], it["text"], it["font"], it["size"], it["color"], fit)
        return len(items)

    def _replace_span(self, page_no, span, new_text, font, size, color, fit=True) -> float:
        new_text = " ".join(new_text.split("\n")).rstrip()
        if fit and new_text:
            size = self.fit_size(page_no, span, new_text, font, size)[0]
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
            xref = page.insert_font(fontname=name, fontbuffer=font.fontbuffer, fontfile=font.fontfile)
            _fix_tounicode(page.parent, xref, font)
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




# ====================================================================== novo PDF do zero
PAGE_SIZES = {
    "A4 (210 × 297 mm)": (595.28, 841.89), "A3 (297 × 420 mm)": (841.89, 1190.55),
    "A5 (148 × 210 mm)": (419.53, 595.28), "Carta (216 × 279 mm)": (612, 792),
    "Ofício (216 × 330 mm)": (612.28, 935.43), "Legal (216 × 356 mm)": (612, 1008),
    "Cartão 10 × 15 cm": (283.46, 425.2),
}
BACKGROUNDS = {"blank": "Em branco", "lined": "Pautado (linhas)", "grid": "Quadriculado",
               "dots": "Pontilhado", "margin": "Pautado com margem"}


def create_blank(width, height, pages=1, background="blank", title="") -> PdfDocument:
    doc = pymupdf.open()
    gray, step = (0.78, 0.82, 0.88), 20
    for _ in range(max(1, pages)):
        page = doc.new_page(width=width, height=height)
        if background == "blank":
            continue
        shape = page.new_shape()
        if background in ("lined", "margin"):
            y = 72
            while y < height - 36:
                shape.draw_line((36, y), (width - 36, y))
                y += 22
            if background == "margin":
                shape.finish(color=gray, width=0.5)
                shape.draw_line((72, 36), (72, height - 36))
                shape.finish(color=(0.9, 0.45, 0.45), width=0.8)
        elif background == "grid":
            x = 36
            while x <= width - 36:
                shape.draw_line((x, 36), (x, height - 36))
                x += step
            y = 36
            while y <= height - 36:
                shape.draw_line((36, y), (width - 36, y))
                y += step
        elif background == "dots":
            for xx in range(36, int(width) - 35, step):
                for yy in range(36, int(height) - 35, step):
                    shape.draw_circle((xx, yy), 0.7)
            shape.finish(color=gray, fill=gray, width=0)
            shape.commit()
            continue
        shape.finish(color=gray, width=0.5)
        shape.commit()
    now = "D:" + dt.datetime.now().strftime("%Y%m%d%H%M%S")
    doc.set_metadata({"title": title, "creator": APP_NAME, "producer": f"{APP_NAME} {__version__}",
                      "creationDate": now, "modDate": now})
    pd = PdfDocument(doc=doc)
    pd.display_name = f"{title or 'Novo documento'}.pdf"
    pd.modified = True
    pd.edits.append(f"Novo documento ({pages} página(s), {BACKGROUNDS.get(background, background).lower()})")
    return pd
