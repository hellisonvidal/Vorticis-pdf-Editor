"""Visualizador contínuo de páginas com zoom e ferramentas de edição."""
from __future__ import annotations

import pymupdf
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget

from .tasks import PDF_LOCK

ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]
PAGE_GAP = 14

# ferramentas
# BROWSE = nenhuma ferramenta ativa: arrastar sobre o texto seleciona; fora do texto, move a página
BROWSE = "browse"
SELECT, EDIT_TEXT, ADD_TEXT, HIGHLIGHT, RECT, WHITEOUT, NOTE, IMAGE, CROP, PAN, SIGN, SHAPE, INK = (
    "select", "edit_text", "add_text", "highlight", "rect", "whiteout", "note", "image", "crop", "pan",
    "sign", "shape", "ink")
DRAG_TOOLS = {RECT, WHITEOUT, IMAGE, CROP, SIGN, SHAPE, SELECT}  # SELECT = retângulos de seleção
TEXT_FLOW_TOOLS = {BROWSE, HIGHLIGHT}  # arrastar sobre o texto seleciona na ordem de leitura
ANNOT_TOOLS = {BROWSE, SHAPE, INK, PAN}  # nestes modos dá para clicar numa forma e movê-la
# anotações que podem ser selecionadas/movidas com o mouse
MOVABLE = {"Square", "Circle", "Line", "Polygon", "PolyLine", "Ink", "FreeText", "Text", "Stamp"}
SELECTABLE = MOVABLE | {"Highlight", "Underline", "StrikeOut", "Squiggly"}
RESIZABLE = {"Square", "Circle", "FreeText", "Stamp"}
HANDLE = 7


def pixmap_to_qimage(pix: pymupdf.Pixmap) -> QImage:
    fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
    return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()


def render_page(page: pymupdf.Page, zoom: float, dpr: float = 1.0) -> QImage:
    m = pymupdf.Matrix(zoom * dpr, zoom * dpr)
    img = pixmap_to_qimage(page.get_pixmap(matrix=m, alpha=False, annots=True))
    img.setDevicePixelRatio(dpr)
    return img


class PageWidget(QWidget):
    def __init__(self, view: "PdfView", index: int):
        super().__init__()
        self.view = view
        self.index = index
        self.image: QImage | None = None
        self.drag_start: QPointF | None = None
        self.drag_now: QPointF | None = None
        self.hover_rect: QRectF | None = None
        self.mode = None            # 'text' | 'pan' | 'move' | 'resize' | 'area' | 'ink'
        self.anchor = None          # índice de caractere onde a seleção começou
        self.ink_points: list[QPointF] = []
        self._clicks = 0
        self._last_click = 0.0
        self._last_pos: QPointF | None = None
        self.setMouseTracking(True)

    def sizeHint(self):
        return self.size()

    # ---------- coordenadas ----------
    def to_pdf(self, p: QPointF) -> pymupdf.Point:
        page = self.view.doc[self.index]
        z = self.view.zoom
        return pymupdf.Point(p.x() / z, p.y() / z) * page.derotation_matrix

    def rect_to_pdf(self, a: QPointF, b: QPointF) -> pymupdf.Rect:
        r = pymupdf.Rect(self.to_pdf(a), self.to_pdf(b))
        r.normalize()
        return r

    def to_screen(self, r) -> QRectF:
        page = self.view.doc[self.index]
        rr = pymupdf.Rect(r) * page.rotation_matrix * self.view.zoom
        rr.normalize()
        return QRectF(rr.x0, rr.y0, rr.width, rr.height)

    def _constrained(self, a: QPointF, b: QPointF, shift: bool) -> QPointF:
        """Com Shift: quadrado/círculo perfeito ou linha em múltiplos de 45°."""
        if not shift:
            return b
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if self.view.tool == SHAPE and self.view.shape_kind in ("line", "arrow", "double_arrow"):
            import math
            ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            ln = math.hypot(dx, dy)
            return QPointF(a.x() + ln * math.cos(ang), a.y() + ln * math.sin(ang))
        m = max(abs(dx), abs(dy))
        return QPointF(a.x() + m * (1 if dx >= 0 else -1), a.y() + m * (1 if dy >= 0 else -1))

    # ---------- pintura ----------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), Qt.white)
        if self.image is not None:
            p.drawImage(QRectF(self.rect()), self.image)
        else:
            self.view.request_render(self.index)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        for pg, r in self.view.search_hits:
            if pg == self.index:
                p.fillRect(self.to_screen(r), QColor(255, 170, 0, 90))
        if self.view.current_hit is not None and self.view.current_hit[0] == self.index:
            p.setPen(QPen(QColor(230, 80, 0), 2))
            p.drawRect(self.to_screen(self.view.current_hit[1]))
        sel_color = QColor(255, 220, 0, 110) if self.view.tool == HIGHLIGHT else QColor(40, 120, 255, 75)
        for pg, r in self.view.selection_rects:
            if pg == self.index:
                p.fillRect(self.to_screen(r), sel_color)
        if self.hover_rect is not None:
            p.setPen(QPen(QColor(214, 35, 45), 1.5, Qt.DashLine))
            p.fillRect(self.hover_rect, QColor(214, 35, 45, 25))
            p.drawRect(self.hover_rect)
        self._paint_rect_selection(p)
        self._paint_selected_annot(p)
        self._paint_preview(p)
        p.end()

    def _paint_rect_selection(self, p):
        v = self.view
        if not v.rect_sel and not v.sel_items:
            return
        blue = QColor(40, 120, 255)
        for pg, r in v.rect_sel:
            if pg == self.index:
                p.setPen(QPen(blue, 1.2, Qt.DashLine))
                p.setBrush(QColor(40, 120, 255, 18))
                p.drawRect(self.to_screen(r))
        p.setBrush(QColor(40, 120, 255, 55))
        p.setPen(QPen(blue, 1))
        for pg, span in v.sel_items:
            if pg == self.index:
                p.drawRect(self.to_screen(span["bbox"]).adjusted(-1, -1, 1, 1))
        p.setBrush(Qt.NoBrush)

    def _paint_selected_annot(self, p):
        sel = self.view.sel_annot
        if not sel or sel[0] != self.index:
            return
        r = self.to_screen(sel[2])
        if self.mode in ("move", "resize") and self.drag_start is not None:
            d = self.drag_now - self.drag_start
            r = r.translated(d) if self.mode == "move" else QRectF(r.topLeft(), r.bottomRight() + d).normalized()
        p.setPen(QPen(QColor(214, 35, 45), 1.3, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(-3, -3, 3, 3))
        if sel[3] in RESIZABLE:
            p.setPen(QPen(QColor(214, 35, 45), 1))
            p.setBrush(QColor("white"))
            c = r.adjusted(-3, -3, 3, 3).bottomRight()
            p.drawRect(QRectF(c.x() - HANDLE / 2, c.y() - HANDLE / 2, HANDLE, HANDLE))

    def _paint_preview(self, p):
        if self.mode == "ink" and len(self.ink_points) > 1:
            st = self.view.shape_style
            p.setPen(QPen(QColor.fromRgbF(*st["stroke"]), max(1.0, st["width"] * self.view.zoom),
                          Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            from PySide6.QtGui import QPolygonF
            p.drawPolyline(QPolygonF(self.ink_points))
            return
        if self.mode != "area" or self.drag_start is None or self.drag_now is None:
            return
        a, b = self.drag_start, self.drag_now
        r = QRectF(a, b).normalized()
        tool = self.view.tool
        if tool == SHAPE:
            self._paint_shape(p, self.view.shape_kind, a, b)
            return
        colors = {WHITEOUT: QColor(255, 255, 255, 200), RECT: QColor(214, 35, 45, 30),
                  SELECT: QColor(40, 120, 255, 35),
                  CROP: QColor(0, 0, 0, 0), IMAGE: QColor(40, 120, 255, 40), SIGN: QColor(27, 138, 58, 45)}
        p.fillRect(r, colors.get(tool, QColor(0, 0, 0, 30)))
        p.setPen(QPen(QColor(30, 30, 30), 1, Qt.DashLine))
        p.drawRect(r)

    def _paint_shape(self, p, kind, a, b):
        from PySide6.QtGui import QPolygonF
        from .document import shape_points
        st = self.view.shape_style
        pen = QPen(QColor.fromRgbF(*st["stroke"]), max(1.0, st["width"] * self.view.zoom))
        if st["dashed"]:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        fill = st["fill"]
        p.setBrush(QColor.fromRgbF(*fill) if fill and kind in ("rect", "ellipse", "triangle", "diamond", "star")
                   else Qt.NoBrush)
        p.setOpacity(st["opacity"])
        r = QRectF(a, b).normalized()
        if kind == "rect":
            p.drawRect(r)
        elif kind == "ellipse":
            p.drawEllipse(r)
        elif kind in ("line", "arrow", "double_arrow"):
            p.drawLine(a, b)
            import math
            ang = math.atan2(b.y() - a.y(), b.x() - a.x())
            size = 6 + st["width"] * self.view.zoom * 2
            ends = {"arrow": [(b, ang)], "double_arrow": [(b, ang), (a, ang + math.pi)]}.get(kind, [])
            p.setBrush(QColor.fromRgbF(*st["stroke"]))
            for tip, an in ends:
                pts = [tip, QPointF(tip.x() - size * math.cos(an - 0.4), tip.y() - size * math.sin(an - 0.4)),
                       QPointF(tip.x() - size * math.cos(an + 0.4), tip.y() - size * math.sin(an + 0.4))]
                p.drawPolygon(QPolygonF(pts))
        else:
            pts = shape_points(kind, (a.x(), a.y()), (b.x(), b.y()))
            if kind in ("check", "cross"):
                for stroke in pts:
                    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in stroke]))
            else:
                p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        p.setOpacity(1)

    # ---------- mouse ----------
    def _on_handle(self, pos: QPointF) -> bool:
        sel = self.view.sel_annot
        if not sel or sel[0] != self.index or sel[3] not in RESIZABLE:
            return False
        c = self.to_screen(sel[2]).adjusted(-3, -3, 3, 3).bottomRight()
        return abs(pos.x() - c.x()) <= HANDLE and abs(pos.y() - c.y()) <= HANDLE

    def mousePressEvent(self, e):
        view = self.view
        if view.inline is not None and not view.inline.done:
            # clique fora da caixa de edição: aplica o texto digitado
            view.inline.commit()
            if view.tool not in (EDIT_TEXT, ADD_TEXT) or e.button() != Qt.LeftButton:
                return
        if e.button() == Qt.RightButton:
            pt = self.to_pdf(e.position())
            ann = view.annot_at(self.index, pt) if view.tool in ANNOT_TOOLS else None
            if ann:
                view.select_annot(self.index, ann)
                view.annotMenuRequested.emit(self.index, ann[0], e.globalPosition().toPoint())
            else:
                view.pageMenuRequested.emit(self.index, (pt.x, pt.y), e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        view.set_current_page(self.index, scroll=False)
        view.setFocus()
        tool = view.tool
        pos = e.position()
        pt = self.to_pdf(pos)
        # contagem de cliques (duplo = palavra, triplo = linha)
        import time
        now = time.monotonic()
        near = self._last_pos is not None and (pos - self._last_pos).manhattanLength() <= 6
        interval = QApplication.doubleClickInterval() / 1000
        self._clicks = self._clicks + 1 if (near and now - self._last_click < interval) else 1
        if getattr(self, "_dbl", False):  # evento de clique duplo do sistema: no mínimo 2 cliques
            self._clicks = max(self._clicks, 2)
            self._dbl = False
        self._last_click, self._last_pos = now, pos

        if tool in ANNOT_TOOLS and self._on_handle(pos):
            self.mode, self.drag_start, self.drag_now = "resize", pos, pos
            return
        if tool in ANNOT_TOOLS:
            ann = view.annot_at(self.index, pt)
            if ann and (tool == BROWSE or ann[1] in MOVABLE):
                view.select_annot(self.index, ann)
                self.mode = "move" if ann[1] in MOVABLE else None
                self.drag_start = self.drag_now = pos
                return
        view.clear_annot_selection()

        if tool == PAN:
            self.mode = "pan"
            view.start_pan(e.globalPosition().toPoint())
        elif tool in TEXT_FLOW_TOOLS:
            idx = view.char_at(self.index, pt, strict=True)
            if idx is not None:
                self.mode = "text"
                if self._clicks == 2:
                    view.select_word(self.index, idx)
                    self.mode = None
                elif self._clicks >= 3:
                    view.select_line(self.index, idx)
                    self.mode = None
                elif e.modifiers() & Qt.ShiftModifier and view.text_sel and view.text_sel[0] == self.index:
                    self.anchor = view.text_sel[1]
                    view.select_range(self.index, self.anchor, idx)
                else:
                    self.anchor = idx
                    view.select_range(self.index, idx, idx)
            else:  # fora do texto: arrasta a página (mão)
                view.clear_selection()
                self.mode = "pan"
                view.start_pan(e.globalPosition().toPoint())
                self.setCursor(Qt.ClosedHandCursor)
        elif tool == INK:
            self.mode = "ink"
            self.ink_points = [pos]
        elif tool == SELECT and self._clicks >= 2 and view.item_at(self.index, pt) is not None:
            # clique duplo num texto: garante que ele está selecionado e abre a edição
            sp = view.item_at(self.index, pt)
            if not any(pg == self.index and s["bbox"] == sp["bbox"] for pg, s in view.sel_items):
                view.toggle_item(self.index, pt)
            view.editSelectedRequested.emit()
        elif tool in DRAG_TOOLS:
            self.mode = "area"
            self.drag_start = self.drag_now = pos
        elif tool == EDIT_TEXT:
            span = view.span_at(self.index, pt)
            if span:
                view.editTextRequested.emit(self.index, span)
        elif tool in (ADD_TEXT, NOTE):
            (view.addTextRequested if tool == ADD_TEXT else view.noteRequested).emit(self.index, (pt.x, pt.y))

    def mouseDoubleClickEvent(self, e):
        self._dbl = True
        self.mousePressEvent(e)

    def mouseMoveEvent(self, e):
        view = self.view
        pos = e.position()
        if self.mode == "pan" and view.panning:
            view.do_pan(e.globalPosition().toPoint())
            return
        if self.mode == "text":
            idx = view.char_at(self.index, self.to_pdf(pos), strict=False)
            if idx is not None:
                view.select_range(self.index, self.anchor, idx)
            return
        if self.mode == "ink":
            self.ink_points.append(pos)
            self.update()
            return
        if self.mode in ("move", "resize", "area") and self.drag_start is not None:
            self.drag_now = self._constrained(self.drag_start, pos, bool(e.modifiers() & Qt.ShiftModifier)) \
                if self.mode == "area" else pos
            self.update()
            return
        # cursor conforme o que está sob o mouse
        tool = view.tool
        pt = self.to_pdf(pos)
        if tool == EDIT_TEXT:
            span = view.span_at(self.index, pt)
            new = self.to_screen(span["bbox"]) if span else None
            if new != self.hover_rect:
                self.hover_rect = new
                view.spanHovered.emit(self.index, span)
                self.update()
        elif tool == SELECT:
            self.setCursor(Qt.PointingHandCursor if view.item_at(self.index, pt) is not None
                           else Qt.CrossCursor)
        elif tool in (BROWSE, HIGHLIGHT, SHAPE, INK, PAN):
            if self._on_handle(pos):
                self.setCursor(Qt.SizeFDiagCursor)
            elif tool != HIGHLIGHT and view.annot_at(self.index, pt):
                self.setCursor(Qt.SizeAllCursor)
            elif tool in TEXT_FLOW_TOOLS:
                self.setCursor(Qt.IBeamCursor if view.char_at(self.index, pt, strict=True) is not None
                               else Qt.OpenHandCursor)
            else:
                self.setCursor(view.tool_cursor())

    def leaveEvent(self, _e):
        if self.hover_rect is not None:
            self.hover_rect = None
            self.view.spanHovered.emit(self.index, None)
            self.update()

    def mouseReleaseEvent(self, e):
        view = self.view
        mode, self.mode = self.mode, None
        if self._last_pos is not None and (e.position() - self._last_pos).manhattanLength() > 6:
            self._clicks, self._last_pos = 0, None  # foi um arraste, não um clique
        if mode == "pan":
            view.panning = False
            self.setCursor(view.tool_cursor())
            return
        if mode == "text":
            if view.tool == HIGHLIGHT and view.selected_text:
                view.markupRequested.emit("highlight")
            return
        if mode == "ink":
            pts = [self.to_pdf(q) for q in self.ink_points]
            self.ink_points = []
            self.update()
            if len(pts) > 1:
                view.inkDrawn.emit(self.index, [(q.x, q.y) for q in pts])
            return
        if mode in ("move", "resize"):
            a, b = self.drag_start, e.position()
            self.drag_start = self.drag_now = None
            self.update()
            sel = view.sel_annot
            if not sel or (a - b).manhattanLength() < 3:
                return
            z = view.zoom
            page = view.doc[self.index]
            d = pymupdf.Point((b.x() - a.x()) / z, (b.y() - a.y()) / z) * page.derotation_matrix - \
                pymupdf.Point(0, 0) * page.derotation_matrix
            if mode == "move":
                view.annotMoved.emit(self.index, sel[1], d.x, d.y)
            else:
                r = pymupdf.Rect(sel[2])
                view.annotResized.emit(self.index, sel[1], (r.x0, r.y0, r.x1 + d.x, r.y1 + d.y))
            return
        if mode == "area" and self.drag_start is not None:
            a, b = self.drag_start, self.drag_now or e.position()
            self.drag_start = self.drag_now = None
            self.update()
            if view.tool == SELECT:
                if (a - b).manhattanLength() < 4:  # clique simples: liga/desliga o texto clicado
                    view.toggle_item(self.index, self.to_pdf(b))
                else:
                    view.add_select_rect(self.index, self.rect_to_pdf(a, b))
                return
            if (a - b).manhattanLength() < 4:
                return
            if view.tool == SHAPE:
                p1, p2 = self.to_pdf(a), self.to_pdf(b)
                view.shapeDrawn.emit(self.index, view.shape_kind, (p1.x, p1.y), (p2.x, p2.y))
            else:
                view.areaSelected.emit(view.tool, self.index, tuple(self.rect_to_pdf(a, b)))


class PdfView(QScrollArea):
    zoomChanged = Signal(float)
    pageChanged = Signal(int)
    editTextRequested = Signal(int, dict)
    addTextRequested = Signal(int, tuple)
    noteRequested = Signal(int, tuple)
    areaSelected = Signal(str, int, tuple)
    spanHovered = Signal(int, object)  # página, trecho sob o cursor (ou None)
    shapeDrawn = Signal(int, str, tuple, tuple)
    inkDrawn = Signal(int, list)
    annotMoved = Signal(int, int, float, float)
    annotResized = Signal(int, int, tuple)
    annotDeleteRequested = Signal(int, int)
    annotMenuRequested = Signal(int, int, object)
    pageMenuRequested = Signal(int, tuple, object)
    markupRequested = Signal(str)
    selectionChanged = Signal(bool)
    rectSelectionChanged = Signal(int)   # quantos textos estão selecionados pelos retângulos
    editSelectedRequested = Signal()
    deleteSelectedRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: pymupdf.Document | None = None
        self.zoom = 1.0
        self.fit_mode = "width"  # 'width' | 'page' | None
        self.tool = BROWSE
        self.pages: list[PageWidget] = []
        self.rect_sel: list[tuple[int, pymupdf.Rect]] = []   # retângulos desenhados pelo usuário
        self.sel_items: list[tuple[int, dict]] = []          # trechos de texto selecionados
        self.current = 0
        self.search_hits: list[tuple[int, pymupdf.Rect]] = []
        self.current_hit = None
        self.selection_rects: list[tuple[int, pymupdf.Rect]] = []
        self.selected_text = ""
        self.panning = False
        self._pan_last = QPoint()
        self._span_cache: dict[int, list] = {}
        self._char_cache: dict[int, tuple] = {}
        self._render_queue: list[int] = []
        self.text_sel = None      # (página, início, fim) em índices de caractere
        self.sel_annot = None     # (página, xref, retângulo, tipo)
        self.inline = None        # edição de texto na própria página (inline_edit.InlineSession)
        from .document import DEFAULT_STYLE
        self.shape_kind = "rect"
        self.shape_style = dict(DEFAULT_STYLE)
        self.setFocusPolicy(Qt.StrongFocus)

        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignHCenter)
        self.setBackgroundRole(self.backgroundRole())
        self.apply_theme()
        self.container = QWidget()
        self.container.setObjectName("pdfContainer")
        self.layout_ = QVBoxLayout(self.container)
        self.layout_.setSpacing(PAGE_GAP)
        self.layout_.setContentsMargins(PAGE_GAP, PAGE_GAP, PAGE_GAP, PAGE_GAP)
        self.layout_.setAlignment(Qt.AlignHCenter)
        self.setWidget(self.container)

        self._render_timer = QTimer(self, singleShot=True, interval=0)
        self._render_timer.timeout.connect(self._render_next)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def apply_theme(self):
        from .theme import c
        bg = c("canvas")
        self.setStyleSheet(f"QScrollArea{{background:{bg};border:none}} #pdfContainer{{background:{bg}}}")

    # ---------------- documento ----------------
    def set_document(self, doc: pymupdf.Document | None, keep_position=True):
        old_page = self.current if keep_position else 0
        if self.inline is not None:
            self.inline.cancel()
        for w in self.pages:
            w.setParent(None)
            w.deleteLater()
        self.pages = []
        self._span_cache.clear()
        self._char_cache.clear()
        self.search_hits, self.current_hit = [], None
        self.selection_rects = []
        self.text_sel = None
        self.sel_annot = None
        self.rect_sel, self.sel_items = [], []
        self.doc = doc
        if doc is None:
            self.container.resize(10, 10)
            return
        for i in range(doc.page_count):
            w = PageWidget(self, i)
            self.pages.append(w)
            self.layout_.addWidget(w, 0, Qt.AlignHCenter)
        self.apply_fit()
        self._relayout()
        self.set_tool(self.tool)
        self.go_to(min(old_page, doc.page_count - 1))

    def invalidate(self, pages: list[int] | None = None):
        """Força nova renderização (após edição)."""
        targets = range(len(self.pages)) if pages is None else pages
        for i in targets:
            if 0 <= i < len(self.pages):
                self.pages[i].image = None
                self._span_cache.pop(i, None)
                self._char_cache.pop(i, None)
                self.pages[i].update()
        if self.rect_sel or self.sel_items:  # o texto mudou: recalcula a seleção por retângulos
            self._recompute_items()
        if self.sel_annot and (pages is None or self.sel_annot[0] in pages):
            self.sel_annot = None

    # ---------------- zoom ----------------
    def available_width(self):
        return self.viewport().width() - 2 * PAGE_GAP - 4

    def apply_fit(self):
        if not self.doc or not self.doc.page_count or not self.fit_mode or not self.isVisible():
            return
        r = self.doc[self.current if self.current < self.doc.page_count else 0].rect
        zw = self.available_width() / r.width
        if self.fit_mode == "page":
            zh = (self.viewport().height() - 2 * PAGE_GAP) / r.height
            self.zoom = max(0.1, min(zw, zh))
        else:
            self.zoom = max(0.1, zw)
        self.zoomChanged.emit(self.zoom)

    def set_zoom(self, z: float, anchor: QPoint | None = None):
        z = max(0.1, min(8.0, z))
        if abs(z - self.zoom) < 1e-3:
            return
        vbar, hbar = self.verticalScrollBar(), self.horizontalScrollBar()
        anchor = anchor or QPoint(self.viewport().width() // 2, self.viewport().height() // 2)
        fy = (vbar.value() + anchor.y()) / max(1, self.container.height())
        fx = (hbar.value() + anchor.x()) / max(1, self.container.width())
        self.zoom = z
        self.fit_mode = None
        self._relayout()
        vbar.setValue(int(fy * self.container.height() - anchor.y()))
        hbar.setValue(int(fx * self.container.width() - anchor.x()))
        self.zoomChanged.emit(self.zoom)

    def zoom_in(self):
        self.set_zoom(next((s for s in ZOOM_STEPS if s > self.zoom + 0.01), ZOOM_STEPS[-1]))

    def zoom_out(self):
        self.set_zoom(next((s for s in reversed(ZOOM_STEPS) if s < self.zoom - 0.01), ZOOM_STEPS[0]))

    def set_fit(self, mode):
        self.fit_mode = mode
        page = self.current
        self.apply_fit()
        self._relayout()
        self.go_to(page)

    def _relayout(self):
        if not self.doc:
            return
        maxw, total = 0, PAGE_GAP
        for i, w in enumerate(self.pages):
            r = self.doc[i].rect
            size = (max(1, int(r.width * self.zoom)), max(1, int(r.height * self.zoom)))
            if (w.width(), w.height()) != size:
                w.setFixedSize(*size)
                w.image = None
            maxw = max(maxw, size[0])
            total += size[1] + PAGE_GAP
        # tamanho calculado diretamente (não depende do sizeHint ainda não processado)
        self.container.setFixedSize(max(maxw + 2 * PAGE_GAP, self.viewport().width()), total + PAGE_GAP)
        self.layout_.activate()
        if self.inline is not None and not self.inline.done:
            self.inline.place_all()  # o zoom mudou: reposiciona as caixas de edição

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fit_mode and self.doc:
            page = self.current
            self.apply_fit()
            self._relayout()
            self.go_to(page)
        elif self.doc:
            self._relayout()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            pos = e.position().toPoint()
            factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
            self.set_zoom(self.zoom * factor, pos)
            e.accept()
        else:
            super().wheelEvent(e)

    # ---------------- navegação ----------------
    def go_to(self, index: int):
        if not self.pages:
            return
        index = max(0, min(index, len(self.pages) - 1))
        self.verticalScrollBar().setValue(self.pages[index].y() - PAGE_GAP // 2)
        self.set_current_page(index, scroll=False)

    def set_current_page(self, index: int, scroll=True):
        if index != self.current:
            self.current = index
            self.pageChanged.emit(index)
        if scroll:
            self.go_to(index)

    def _on_scroll(self, _v):
        if not self.pages:
            return
        mid = self.verticalScrollBar().value() + self.viewport().height() // 3
        for i, w in enumerate(self.pages):
            if w.y() + w.height() + PAGE_GAP >= mid:
                if i != self.current:
                    self.current = i
                    self.pageChanged.emit(i)
                break

    def start_pan(self, pos):
        self.panning = True
        self._pan_last = pos

    def do_pan(self, pos):
        d = pos - self._pan_last
        self._pan_last = pos
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())

    # ---------------- renderização sob demanda ----------------
    def request_render(self, index):
        if index not in self._render_queue:
            self._render_queue.append(index)
            self._render_timer.start()

    def _render_next(self):
        if not self.doc or not self._render_queue:
            return
        if not PDF_LOCK.acquire(blocking=False):  # tarefa em segundo plano usando o PyMuPDF
            QTimer.singleShot(120, self._render_timer.start)
            return
        try:
            self._render_one()
        finally:
            PDF_LOCK.release()
        if self._render_queue:
            self._render_timer.start()

    def _render_one(self):
        # prioriza páginas visíveis
        top = self.verticalScrollBar().value()
        bottom = top + self.viewport().height()
        self._render_queue.sort(key=lambda i: 0 if i < len(self.pages) and
                                self.pages[i].y() < bottom and self.pages[i].y() + self.pages[i].height() > top else 1)
        i = self._render_queue.pop(0)
        if i < len(self.pages) and i < self.doc.page_count:
            w = self.pages[i]
            visible = w.y() < bottom + 400 and w.y() + w.height() > top - 400
            if visible and w.image is None:
                w.image = render_page(self.doc[i], self.zoom, self.devicePixelRatioF())
                w.update()

    # ---------------- texto ----------------
    def spans(self, index):
        if index not in self._span_cache:
            out = []
            d = self.doc[index].get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
            for b in d["blocks"]:
                for l in b.get("lines", []):
                    for s in l["spans"]:
                        if s["text"].strip():
                            s = dict(s)
                            s["dir"] = l["dir"]
                            s["line_bbox"] = l["bbox"]
                            out.append(s)
            self._span_cache[index] = out
        return self._span_cache[index]

    def span_at(self, index, pt: pymupdf.Point):
        best = None
        for s in self.spans(index):
            r = pymupdf.Rect(s["bbox"])
            if r.contains(pt):
                if best is None or r.get_area() < pymupdf.Rect(best["bbox"]).get_area():
                    best = s
        return best

    # ---------- seleção de texto na ordem de leitura ----------
    def chars(self, index):
        """(lista de (caractere, retângulo, linha), retângulos das linhas, [início,fim) por linha)."""
        if index not in self._char_cache:
            chars, lines, ranges = [], [], []
            d = self.doc[index].get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE |
                                         pymupdf.TEXT_PRESERVE_LIGATURES)
            for b in d["blocks"]:
                for l in b.get("lines", []):
                    start = len(chars)
                    lid = len(lines)
                    for sp in l["spans"]:
                        for ch in sp["chars"]:
                            chars.append((ch["c"], pymupdf.Rect(ch["bbox"]), lid))
                    if len(chars) > start:
                        lines.append(pymupdf.Rect(l["bbox"]))
                        ranges.append((start, len(chars)))
            self._char_cache[index] = (chars, lines, ranges)
        return self._char_cache[index]

    def char_at(self, index, pt: pymupdf.Point, strict=True):
        """Posição (índice de fronteira entre caracteres) mais próxima do ponto.
        strict=True: só quando o ponto está sobre uma linha de texto."""
        chars, lines, ranges = self.chars(index)
        if not chars:
            return None
        tol = 2.5 / max(self.zoom, 0.1)
        best_line = None
        for lid, r in enumerate(lines):
            if r.y0 - tol <= pt.y <= r.y1 + tol and r.x0 - tol * 3 <= pt.x <= r.x1 + tol * 3:
                if best_line is None or r.height < lines[best_line].height:
                    best_line = lid
        if best_line is None:
            if strict:
                return None
            # durante o arraste: linha mais próxima (antes/depois no fluxo)
            best_line = min(range(len(lines)), key=lambda i: (
                0 if lines[i].y0 <= pt.y <= lines[i].y1 else min(abs(pt.y - lines[i].y0), abs(pt.y - lines[i].y1)),
                abs(pt.x - (lines[i].x0 + lines[i].x1) / 2)))
        start, end = ranges[best_line]
        for i in range(start, end):
            r = chars[i][1]
            if pt.x < (r.x0 + r.x1) / 2:
                return i
        return end

    def _sel_rects(self, index, a, b):
        chars, _lines, _ranges = self.chars(index)
        per_line = {}
        for c, r, lid in chars[a:b]:
            if lid in per_line:
                per_line[lid] |= r
            else:
                per_line[lid] = pymupdf.Rect(r)
        return [(index, r) for r in per_line.values() if not r.is_empty]

    def select_range(self, index, a, b):
        a, b = min(a, b), max(a, b)
        self.text_sel = (index, a, b) if b > a else None
        self.selection_rects = self._sel_rects(index, a, b) if b > a else []
        chars = self.chars(index)[0]
        out, last = [], None
        for c, _r, lid in chars[a:b]:
            if last is not None and lid != last:
                out.append("\n")
            out.append(c)
            last = lid
        self.selected_text = "".join(out).strip()
        self.selectionChanged.emit(bool(self.selected_text))
        for w in self.pages:
            w.update()

    def select_word(self, index, idx):
        chars = self.chars(index)[0]
        idx = min(idx, len(chars) - 1)
        a = b = idx
        while a > 0 and not chars[a - 1][0].isspace() and chars[a - 1][2] == chars[idx][2]:
            a -= 1
        while b < len(chars) and not chars[b][0].isspace() and chars[b][2] == chars[idx][2]:
            b += 1
        self.select_range(index, a, b)

    def select_line(self, index, idx):
        chars, _lines, ranges = self.chars(index)
        lid = chars[min(idx, len(chars) - 1)][2]
        self.select_range(index, *ranges[lid])

    def select_all_page(self, index=None):
        index = self.current if index is None else index
        chars = self.chars(index)[0]
        if chars:
            self.select_range(index, 0, len(chars))

    def clear_selection(self):
        if self.text_sel or self.selection_rects:
            self.set_selection([])

    def select_text(self, index, rect: pymupdf.Rect):
        """Seleciona as palavras dentro de um retângulo (compatibilidade)."""
        page = self.doc[index]
        words = [w for w in page.get_text("words") if pymupdf.Rect(w[:4]).intersects(rect)]
        self.selection_rects = [(index, pymupdf.Rect(w[:4])) for w in words]
        self.selected_text = page.get_textbox(rect).strip() if words else ""
        for w in self.pages:
            w.update()

    def set_selection(self, rects):
        self.selection_rects = rects
        self.selected_text = ""
        self.text_sel = None
        self.selectionChanged.emit(False)
        for w in self.pages:
            w.update()

    def copy_selection(self):
        if self.selected_text:
            QApplication.clipboard().setText(self.selected_text)
            return True
        return False

    # ---------- seleção por retângulos (ferramenta Seleção) ----------
    @staticmethod
    def _inside(span_rect: pymupdf.Rect, sel: pymupdf.Rect) -> bool:
        inter = span_rect & sel
        return not inter.is_empty and inter.get_area() >= 0.5 * max(span_rect.get_area(), 1e-6)

    def _recompute_items(self):
        items = []
        for pg, r in self.rect_sel:
            if pg >= (self.doc.page_count if self.doc else 0):
                continue
            for sp in self.spans(pg):
                if self._inside(pymupdf.Rect(sp["bbox"]), r) and \
                        not any(p == pg and s["bbox"] == sp["bbox"] for p, s in items):
                    items.append((pg, sp))
        for pg, sp in getattr(self, "_extra_items", []):
            if not any(p == pg and s["bbox"] == sp["bbox"] for p, s in items):
                items.append((pg, sp))
        items.sort(key=lambda it: (it[0], round(it[1]["bbox"][1]), it[1]["bbox"][0]))
        self.sel_items = items
        self.selected_text = "\n".join(s["text"].strip() for _p, s in items)
        self.rectSelectionChanged.emit(len(items))
        for w in self.pages:
            w.update()

    def add_select_rect(self, index, rect: pymupdf.Rect):
        self.rect_sel.append((index, pymupdf.Rect(rect)))
        self._recompute_items()

    def item_at(self, index, pt):
        for sp in self.spans(index):
            if pymupdf.Rect(sp["bbox"]).contains(pt):
                return sp
        return None

    def toggle_item(self, index, pt):
        """Clique simples com a ferramenta Seleção: inclui/retira o texto clicado; clicar
        fora de qualquer texto limpa toda a seleção."""
        sp = self.item_at(index, pt)
        if sp is None:
            self.clear_rect_selection()
            return
        extra = getattr(self, "_extra_items", [])
        selected = any(p == index and s["bbox"] == sp["bbox"] for p, s in self.sel_items)
        if selected:
            self._extra_items = [(p, s) for p, s in extra if not (p == index and s["bbox"] == sp["bbox"])]
            # retira também dos retângulos que o contêm
            self.rect_sel = [(p, r) for p, r in self.rect_sel
                             if not (p == index and self._inside(pymupdf.Rect(sp["bbox"]), r))]
        else:
            self._extra_items = extra + [(index, sp)]
        self._recompute_items()

    def clear_rect_selection(self):
        if self.rect_sel or self.sel_items or getattr(self, "_extra_items", None):
            self.rect_sel, self.sel_items, self._extra_items = [], [], []
            self.selected_text = ""
            self.rectSelectionChanged.emit(0)
            for w in self.pages:
                w.update()

    # ---------- anotações (formas, notas, marcações) ----------
    def annot_at(self, index, pt: pymupdf.Point):
        """(xref, tipo, retângulo) da anotação sob o ponto (a de cima primeiro)."""
        page = self.doc[index]  # a página precisa continuar viva enquanto usamos as anotações
        tol = 4 / max(self.zoom, 0.1)
        found = None
        for a in page.annots():
            t = a.type[1]
            if t not in SELECTABLE:
                continue
            r = pymupdf.Rect(a.rect)
            if (r + (-tol, -tol, tol, tol)).contains(pt):
                found = (a.xref, t, r)
        return found

    def select_annot(self, index, ann):
        xref, t, r = ann
        self.sel_annot = (index, xref, r, t)
        self.clear_selection()
        for w in self.pages:
            w.update()

    def clear_annot_selection(self):
        if self.sel_annot:
            self.sel_annot = None
            for w in self.pages:
                w.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.sel_annot:
            pg, xref = self.sel_annot[0], self.sel_annot[1]
            self.sel_annot = None
            self.annotDeleteRequested.emit(pg, xref)
            return
        if self.tool == SELECT and self.sel_items:
            if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_F2):
                self.editSelectedRequested.emit()
                return
            if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.deleteSelectedRequested.emit()
                return
        if e.key() == Qt.Key_A and e.modifiers() & Qt.ControlModifier:
            if self.tool == SELECT:  # seleciona todos os textos da página atual
                self.add_select_rect(self.current, pymupdf.Rect(-1e6, -1e6, 1e6, 1e6))
            else:
                self.select_all_page()
            return
        if e.key() == Qt.Key_Escape and (self.sel_annot or self.text_sel or self.sel_items):
            self.clear_annot_selection()
            self.clear_selection()
            self.clear_rect_selection()
            return
        super().keyPressEvent(e)

    # ---------------- busca ----------------
    def search(self, text: str):
        self.search_hits = []
        if self.doc and text:
            for i, page in enumerate(self.doc):
                for r in page.search_for(text):
                    self.search_hits.append((i, r))
        self.current_hit = None
        for w in self.pages:
            w.update()
        return len(self.search_hits)

    def goto_hit(self, n: int):
        if not self.search_hits:
            return
        n %= len(self.search_hits)
        self.current_hit = self.search_hits[n]
        pg, r = self.current_hit
        w = self.pages[pg]
        sr = w.to_screen(r)
        self.ensureVisible(w.x() + int(sr.center().x()), w.y() + int(sr.center().y()), 100, 150)
        self.set_current_page(pg, scroll=False)
        for p in self.pages:
            p.update()
        return n

    # ---------------- ferramenta ----------------
    def tool_cursor(self):
        cursors = {BROWSE: Qt.ArrowCursor, SELECT: Qt.CrossCursor, HIGHLIGHT: Qt.IBeamCursor,
                   EDIT_TEXT: Qt.PointingHandCursor,
                   ADD_TEXT: Qt.CrossCursor, PAN: Qt.OpenHandCursor, NOTE: Qt.CrossCursor}
        return QCursor(cursors.get(self.tool, Qt.CrossCursor))

    def set_tool(self, tool):
        self.tool = tool
        if tool != EDIT_TEXT:
            self.spanHovered.emit(self.current, None)
        if tool not in ANNOT_TOOLS:
            self.clear_annot_selection()
        if tool != SELECT:
            self.clear_rect_selection()
        else:
            self.clear_selection()
        cur = self.tool_cursor()
        for w in self.pages:
            w.setCursor(cur)
            w.hover_rect = None
            w.update()
