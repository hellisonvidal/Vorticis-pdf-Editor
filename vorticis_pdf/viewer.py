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
SELECT, EDIT_TEXT, ADD_TEXT, HIGHLIGHT, RECT, WHITEOUT, NOTE, IMAGE, CROP, PAN, SIGN = (
    "select", "edit_text", "add_text", "highlight", "rect", "whiteout", "note", "image", "crop", "pan", "sign")
DRAG_TOOLS = {SELECT, HIGHLIGHT, RECT, WHITEOUT, IMAGE, CROP, SIGN}


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

    # ---------- pintura ----------
    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.white)
        if self.image is not None:
            p.drawImage(QRectF(self.rect()), self.image)
        else:
            self.view.request_render(self.index)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        # resultados de busca
        for pg, r in self.view.search_hits:
            if pg == self.index:
                p.fillRect(self.to_screen(r), QColor(255, 170, 0, 90))
        if self.view.current_hit is not None and self.view.current_hit[0] == self.index:
            p.setPen(QPen(QColor(230, 80, 0), 2))
            p.drawRect(self.to_screen(self.view.current_hit[1]))
        # seleção de texto
        for pg, r in self.view.selection_rects:
            if pg == self.index:
                p.fillRect(self.to_screen(r), QColor(40, 120, 255, 70))
        if self.hover_rect is not None:
            p.setPen(QPen(QColor(214, 35, 45), 1.5, Qt.DashLine))
            p.fillRect(self.hover_rect, QColor(214, 35, 45, 25))
            p.drawRect(self.hover_rect)
        if self.drag_start is not None and self.drag_now is not None:
            colors = {HIGHLIGHT: QColor(255, 220, 0, 90), WHITEOUT: QColor(255, 255, 255, 200),
                      RECT: QColor(214, 35, 45, 30), CROP: QColor(0, 0, 0, 0),
                      IMAGE: QColor(40, 120, 255, 40), SELECT: QColor(40, 120, 255, 40),
                      SIGN: QColor(27, 138, 58, 45)}
            r = QRectF(self.drag_start, self.drag_now).normalized()
            p.fillRect(r, colors.get(self.view.tool, QColor(0, 0, 0, 30)))
            p.setPen(QPen(QColor(30, 30, 30), 1, Qt.DashLine))
            p.drawRect(r)
        p.end()

    # ---------- mouse ----------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        self.view.set_current_page(self.index, scroll=False)
        tool = self.view.tool
        if tool == PAN:
            self.view.start_pan(e.globalPosition().toPoint())
        elif tool in DRAG_TOOLS:
            self.drag_start = self.drag_now = e.position()
        elif tool == EDIT_TEXT:
            span = self.view.span_at(self.index, self.to_pdf(e.position()))
            if span:
                self.view.editTextRequested.emit(self.index, span)
        elif tool in (ADD_TEXT, NOTE):
            pt = self.to_pdf(e.position())
            (self.view.addTextRequested if tool == ADD_TEXT else self.view.noteRequested).emit(
                self.index, (pt.x, pt.y))

    def mouseMoveEvent(self, e):
        if self.view.panning:
            self.view.do_pan(e.globalPosition().toPoint())
            return
        if self.drag_start is not None:
            self.drag_now = e.position()
            self.update()
            return
        if self.view.tool == EDIT_TEXT:
            span = self.view.span_at(self.index, self.to_pdf(e.position()))
            new = self.to_screen(span["bbox"]) if span else None
            if new != self.hover_rect:
                self.hover_rect = new
                self.view.spanHovered.emit(self.index, span)
                self.update()

    def leaveEvent(self, _e):
        if self.hover_rect is not None:
            self.hover_rect = None
            self.view.spanHovered.emit(self.index, None)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.view.panning:
            self.view.panning = False
            return
        if self.drag_start is None:
            return
        a, b = self.drag_start, e.position()
        self.drag_start = self.drag_now = None
        self.update()
        if (a - b).manhattanLength() < 4:
            if self.view.tool == SELECT:
                self.view.set_selection([])
            return
        rect = self.rect_to_pdf(a, b)
        if self.view.tool == SELECT:
            self.view.select_text(self.index, rect)
        else:
            self.view.areaSelected.emit(self.view.tool, self.index, tuple(rect))


class PdfView(QScrollArea):
    zoomChanged = Signal(float)
    pageChanged = Signal(int)
    editTextRequested = Signal(int, dict)
    addTextRequested = Signal(int, tuple)
    noteRequested = Signal(int, tuple)
    areaSelected = Signal(str, int, tuple)
    spanHovered = Signal(int, object)  # página, trecho sob o cursor (ou None)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: pymupdf.Document | None = None
        self.zoom = 1.0
        self.fit_mode = "width"  # 'width' | 'page' | None
        self.tool = SELECT
        self.pages: list[PageWidget] = []
        self.current = 0
        self.search_hits: list[tuple[int, pymupdf.Rect]] = []
        self.current_hit = None
        self.selection_rects: list[tuple[int, pymupdf.Rect]] = []
        self.selected_text = ""
        self.panning = False
        self._pan_last = QPoint()
        self._span_cache: dict[int, list] = {}
        self._render_queue: list[int] = []

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
        for w in self.pages:
            w.setParent(None)
            w.deleteLater()
        self.pages = []
        self._span_cache.clear()
        self.search_hits, self.current_hit = [], None
        self.selection_rects = []
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
                self.pages[i].update()

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

    def select_text(self, index, rect: pymupdf.Rect):
        page = self.doc[index]
        words = [w for w in page.get_text("words") if pymupdf.Rect(w[:4]).intersects(rect)]
        self.selection_rects = [(index, pymupdf.Rect(w[:4])) for w in words]
        self.selected_text = page.get_textbox(rect).strip() if words else ""
        for w in self.pages:
            w.update()

    def set_selection(self, rects):
        self.selection_rects = rects
        self.selected_text = ""
        for w in self.pages:
            w.update()

    def copy_selection(self):
        if self.selected_text:
            QApplication.clipboard().setText(self.selected_text)
            return True
        return False

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
    def set_tool(self, tool):
        self.tool = tool
        if tool != EDIT_TEXT:
            self.spanHovered.emit(self.current, None)
        cursors = {SELECT: Qt.IBeamCursor, EDIT_TEXT: Qt.PointingHandCursor,
                   ADD_TEXT: Qt.CrossCursor, PAN: Qt.OpenHandCursor, NOTE: Qt.CrossCursor}
        cur = QCursor(cursors.get(tool, Qt.CrossCursor))
        for w in self.pages:
            w.setCursor(cur)
            w.hover_rect = None
            w.update()
