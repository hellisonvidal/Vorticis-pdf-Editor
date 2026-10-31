"""Painel de miniaturas: reordenar arrastando, seleção múltipla, menu de contexto e zoom."""
from __future__ import annotations

import pymupdf
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem, QMenu

from .tasks import PDF_LOCK
from .viewer import pixmap_to_qimage

THUMB_MIN, THUMB_MAX = 70, 420


class ThumbList(QListWidget):
    pagesMoved = Signal(list, int)        # linhas, posição de destino
    filesDropped = Signal(list, int)      # arquivos externos, posição
    pageActivated = Signal(int)
    action = Signal(str, list)            # nome da ação, linhas selecionadas
    thumbSizeChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: pymupdf.Document | None = None
        self.thumb = 130
        self._cache: dict[tuple, QPixmap] = {}
        self._queue: list[int] = []
        self._drop_row = -1
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Snap)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setSpacing(8)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemDoubleClicked.connect(lambda it: self.pageActivated.emit(self.row(it)))
        self.itemClicked.connect(lambda it: self.pageActivated.emit(self.row(it)))
        self.setStyleSheet("""
            QListWidget{background:#262a31;color:#c9ced6;border:none;border-radius:0}
            QListWidget::item{border-radius:10px;padding:6px;margin:2px}
            QListWidget::item:selected{background:rgba(214,35,45,.85);color:white}
            QListWidget::item:hover:!selected{background:#343a43}""")
        self._timer = QTimer(self, singleShot=True, interval=0)
        self._timer.timeout.connect(self._render_batch)
        self._apply_size()

    # ---------------- conteúdo ----------------
    def set_document(self, doc, invalidate_all=False):
        if invalidate_all:
            self._cache.clear()
        self.doc = doc
        selected = {self.row(i) for i in self.selectedItems()}
        self.clear()
        if doc is None:
            return
        for i in range(doc.page_count):
            it = QListWidgetItem(self._placeholder(i), str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            it.setFlags(it.flags() | Qt.ItemIsDragEnabled)
            self.addItem(it)
            if i in selected:
                it.setSelected(True)
        self._queue = list(range(doc.page_count))
        self._timer.start()

    def select_rows(self, rows):
        self.clearSelection()
        for r in rows:
            if 0 <= r < self.count():
                self.item(r).setSelected(True)
        if rows:
            self.scrollToItem(self.item(rows[0]))

    def invalidate(self, rows):
        if not self.doc:
            return
        for r in rows:
            if 0 <= r < self.doc.page_count:
                self._cache.pop(self._key(r), None)
                if r not in self._queue:
                    self._queue.insert(0, r)
        self._timer.start()

    def _key(self, i):
        page = self.doc[i]
        return (page.xref, page.rotation, self.thumb)

    def _placeholder(self, i):
        key = self._key(i)
        if key in self._cache:
            return QIcon(self._cache[key])
        r = self.doc[i].rect
        s = self.thumb / max(r.width, r.height)
        pm = QPixmap(max(1, int(r.width * s)), max(1, int(r.height * s)))
        pm.fill(QColor("#f0f0f0"))
        return QIcon(pm)

    def _render_batch(self):
        if not self.doc:
            return
        if not PDF_LOCK.acquire(blocking=False):  # tarefa em segundo plano usando o PyMuPDF
            QTimer.singleShot(150, self._timer.start)
            return
        try:
            self._render_batch_locked()
        finally:
            PDF_LOCK.release()

    def _render_batch_locked(self):
        # renderiza primeiro as miniaturas visíveis
        vis = self.viewport().rect()
        self._queue.sort(key=lambda r: 0 if r < self.count() and
                         self.visualItemRect(self.item(r)).intersects(vis) else 1)
        for _ in range(6):
            if not self._queue:
                return
            i = self._queue.pop(0)
            if i >= self.doc.page_count or i >= self.count():
                continue
            key = self._key(i)
            pm = self._cache.get(key)
            if pm is None:
                page = self.doc[i]
                s = self.thumb * self.devicePixelRatioF() / max(page.rect.width, page.rect.height)
                img = pixmap_to_qimage(page.get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False))
                img.setDevicePixelRatio(self.devicePixelRatioF())
                pm = QPixmap.fromImage(img)
                self._cache[key] = pm
            ic = QIcon()
            ic.addPixmap(pm, QIcon.Normal)
            ic.addPixmap(pm, QIcon.Selected)  # sem tingir a página ao selecionar
            self.item(i).setIcon(ic)
        if self._queue:
            self._timer.start()

    # ---------------- tamanho / zoom ----------------
    def _apply_size(self):
        self.setIconSize(QSize(self.thumb, self.thumb))
        self.setGridSize(QSize(self.thumb + 26, self.thumb + 34))
        self.doItemsLayout()

    def set_thumb_size(self, px):
        px = max(THUMB_MIN, min(THUMB_MAX, int(px)))
        if px == self.thumb:
            return
        self.thumb = px
        self._apply_size()
        self.thumbSizeChanged.emit(px)
        if self.doc:
            self._queue = list(range(self.doc.page_count))
            self._timer.start()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.set_thumb_size(self.thumb * (1.12 if e.angleDelta().y() > 0 else 1 / 1.12))
            e.accept()
        else:
            super().wheelEvent(e)
            self._timer.start()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        if self._queue:
            self._timer.start()

    # ---------------- arrastar e soltar ----------------
    def _target_row(self, pos):
        it = self.itemAt(pos)
        if it is None:
            return self.count()
        r = self.visualItemRect(it)
        row = self.row(it)
        horizontal = self.width() > self.gridSize().width() * 1.8
        after = pos.x() > r.center().x() if horizontal else pos.y() > r.center().y()
        return row + 1 if after else row

    def dragEnterEvent(self, e):
        if e.source() is self or e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.source() is self or e.mimeData().hasUrls():
            self._drop_row = self._target_row(e.position().toPoint())
            self.viewport().update()
            e.setDropAction(Qt.MoveAction if e.source() is self else Qt.CopyAction)
            e.accept()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._drop_row = -1
        self.viewport().update()
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        target = self._target_row(e.position().toPoint())
        self._drop_row = -1
        self.viewport().update()
        if e.source() is self:
            rows = sorted(self.row(i) for i in self.selectedItems())
            e.setDropAction(Qt.IgnoreAction)  # nós mesmos aplicamos a mudança
            e.accept()
            if rows:
                self.pagesMoved.emit(rows, target)
        elif e.mimeData().hasUrls():
            files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            e.acceptProposedAction()
            if files:
                self.filesDropped.emit(files, target)

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._drop_row < 0 or not self.count():
            return
        p = QPainter(self.viewport())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ff7828"))
        if self._drop_row < self.count():
            r = self.visualItemRect(self.item(self._drop_row))
            horizontal = self.width() > self.gridSize().width() * 1.8
            bar = (r.adjusted(-5, 0, 0, 0).topLeft(), 4, r.height()) if horizontal else \
                (r.adjusted(0, -5, 0, 0).topLeft(), r.width(), 4)
        else:
            r = self.visualItemRect(self.item(self.count() - 1))
            bar = (r.topRight(), 4, r.height())
        p.drawRect(bar[0].x(), bar[0].y(), bar[1], bar[2])
        p.end()

    # ---------------- menu de contexto ----------------
    def selected_rows(self):
        return sorted(self.row(i) for i in self.selectedItems())

    def _menu(self, pos):
        it = self.itemAt(pos)
        if it is not None and not it.isSelected():
            self.clearSelection()
            it.setSelected(True)
        rows = self.selected_rows()
        m = QMenu(self)
        n = len(rows)

        def add(text, name, shortcut=None, enabled=True):
            a = QAction(text, m)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setEnabled(enabled)
            a.triggered.connect(lambda: self.action.emit(name, self.selected_rows()))
            m.addAction(a)

        has = n > 0
        add("🔍  Visualizar ampliada", "preview", "Space", n == 1)
        m.addSeparator()
        add("↻  Girar à direita", "rot_r", "Ctrl+R", has)
        add("↺  Girar à esquerda", "rot_l", "Ctrl+Shift+R", has)
        add("⇅  Girar 180°", "rot_180", None, has)
        m.addSeparator()
        add("⤒  Mover para o início", "move_first", None, has)
        add("⤓  Mover para o fim", "move_last", None, has)
        add("⧉  Duplicar", "duplicate", "Ctrl+D", has)
        add("□  Inserir página em branco depois", "blank", None, True)
        add("📄  Inserir arquivo aqui...", "insert_file", None, True)
        m.addSeparator()
        add(f"📤  Extrair {n} página(s) para novo PDF...", "extract", None, has)
        add("✂  Separar documento aqui (antes desta)", "split_here", None, n == 1)
        add("🖨  Imprimir seleção...", "print_sel", None, has)
        m.addSeparator()
        add("⇄  Inverter ordem das selecionadas", "reverse", None, n > 1)
        add("☑  Selecionar todas", "select_all", "Ctrl+A", True)
        add("Selecionar páginas ímpares", "select_odd", None, True)
        add("Selecionar páginas pares", "select_even", None, True)
        m.addSeparator()
        add(f"🗑  Excluir {n} página(s)", "delete", "Del", has)
        m.exec(self.viewport().mapToGlobal(pos))

    def keyPressEvent(self, e):
        rows = self.selected_rows()
        if e.key() == Qt.Key_Delete and rows:
            self.action.emit("delete", rows)
        elif e.key() == Qt.Key_Space and len(rows) == 1:
            self.action.emit("preview", rows)
        else:
            super().keyPressEvent(e)
