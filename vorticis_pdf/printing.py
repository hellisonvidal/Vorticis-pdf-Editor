"""Impressão com janela própria, toda em português (sem pré-visualização própria: o
documento já está na tela).

Opções: impressora, propriedades do driver, páginas (todas/atual/selecionadas/intervalo,
ímpares/pares, ordem inversa), cópias e agrupamento, orientação, papel, escala, páginas
por folha, cor ou tons de cinza, qualidade e anotações. Imprime sempre em uma face só
(frente e verso desativado, mesmo que a impressora tenha sido configurada assim).
"""
from __future__ import annotations

import sys

import pymupdf
from PySide6.QtCore import QRectF, QSettings, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QTransform
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QSpinBox, QVBoxLayout,
)

from .viewer import pixmap_to_qimage

MAX_DPI = 600

# nomes em português dos papéis mais comuns
PAPER_PT = {
    QPageSize.A4: "A4 (210 × 297 mm)", QPageSize.A3: "A3 (297 × 420 mm)",
    QPageSize.A5: "A5 (148 × 210 mm)", QPageSize.A6: "A6 (105 × 148 mm)",
    QPageSize.B5: "B5 (176 × 250 mm)", QPageSize.B4: "B4 (250 × 353 mm)",
    QPageSize.Letter: "Carta (216 × 279 mm)", QPageSize.Legal: "Ofício / Legal (216 × 356 mm)",
    QPageSize.Executive: "Executivo (184 × 267 mm)", QPageSize.Tabloid: "Tabloide (279 × 432 mm)",
    QPageSize.EnvelopeDL: "Envelope DL (110 × 220 mm)", QPageSize.EnvelopeC5: "Envelope C5 (162 × 229 mm)",
    QPageSize.Envelope10: "Envelope nº 10 (105 × 241 mm)", QPageSize.Folio: "Fólio (210 × 330 mm)",
}
COMMON_PAPERS = [QPageSize.A4, QPageSize.Letter, QPageSize.Legal, QPageSize.A3, QPageSize.A5,
                 QPageSize.Executive, QPageSize.B5]
NUP_GRID = {1: (1, 1), 2: (1, 2), 4: (2, 2), 6: (2, 3), 9: (3, 3), 16: (4, 4)}


def paper_name(ps: QPageSize) -> str:
    return PAPER_PT.get(ps.id(), ps.name())


def parse_ranges(text: str, total: int) -> list[int]:
    """'1-3, 5, 8-' -> índices (base 0). Levanta ValueError se inválido."""
    out = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a.strip() else 1
            b = int(b) if b.strip() else total
        else:
            a = b = int(part)
        if not (1 <= a <= total and 1 <= b <= total):
            raise ValueError(f"Página fora do documento (1 a {total}): {part}")
        step = 1 if b >= a else -1
        out += [i - 1 for i in range(a, b + step, step)]
    if not out:
        raise ValueError("Informe as páginas, por exemplo: 1-3, 5")
    return out


# ------------------------------------------------------------------ opções
class PrintOptions:
    """Tudo o que a janela de impressão escolhe (também usado pelo autoteste)."""

    def __init__(self, **kw):
        self.pages: list[int] = kw.get("pages", [])
        self.copies = kw.get("copies", 1)
        self.collate = kw.get("collate", True)
        self.orientation = kw.get("orientation", "auto")   # auto | portrait | landscape
        self.scale = kw.get("scale", "fit")                # fit | shrink | actual | custom
        self.custom = kw.get("custom", 100)
        self.nup = kw.get("nup", 1)
        self.gray = kw.get("gray", False)
        self.dpi = kw.get("dpi", 300)
        self.annots = kw.get("annots", True)
        self.center = kw.get("center", True)

    def sheets(self) -> list[list[int]]:
        """Folhas a imprimir (cada folha = lista de páginas), já com as cópias."""
        n = max(1, self.nup)
        one = [self.pages[i:i + n] for i in range(0, len(self.pages), n)]
        if self.collate:
            return one * max(1, self.copies)
        return [s for s in one for _ in range(max(1, self.copies))]


def _force_single_sided(printer: QPrinter):
    printer.setDuplex(QPrinter.DuplexNone)


def _paint(printer: QPrinter, doc: pymupdf.Document, pages, opts: PrintOptions | None = None):
    """Desenha as folhas na impressora. 'pages' pode ser uma lista de páginas (1 por folha)."""
    if opts is None:
        opts = PrintOptions(pages=list(pages))
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Não foi possível iniciar a impressão nesta impressora.")
    res = printer.resolution()
    dpi = min(res, opts.dpi, MAX_DPI)
    try:
        for n, sheet in enumerate(opts.sheets()):
            if n:
                printer.newPage()
            area = QRectF(printer.pageLayout().paintRectPixels(res))
            area.moveTo(0, 0)  # sem "página inteira", a origem do desenho já é a área imprimível
            cols, rows = NUP_GRID.get(opts.nup, (1, 1))
            if area.width() > area.height():
                cols, rows = rows, cols
            gap = res * 0.08 if opts.nup > 1 else 0
            cw = (area.width() - gap * (cols - 1)) / cols
            ch = (area.height() - gap * (rows - 1)) / rows
            for k, i in enumerate(sheet):
                cell = QRectF(area.x() + (k % cols) * (cw + gap), area.y() + (k // cols) * (ch + gap), cw, ch)
                _draw_page(painter, doc[i], cell, res, dpi, opts)
    finally:
        painter.end()


def _draw_page(painter, page, cell: QRectF, res, dpi, opts: PrintOptions):
    pix = page.get_pixmap(dpi=dpi, alpha=False, annots=opts.annots,
                          colorspace=pymupdf.csGRAY if opts.gray else pymupdf.csRGB)
    if pix.n == 1:
        from PySide6.QtGui import QImage
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_Grayscale8).copy()
    else:
        img = pixmap_to_qimage(pix)
    w_pt, h_pt = page.rect.width, page.rect.height
    # orientação automática: gira a página para aproveitar melhor o papel
    if opts.orientation == "auto" and opts.nup == 1 and (w_pt > h_pt) != (cell.width() > cell.height()):
        img = img.transformed(QTransform().rotate(90))
        w_pt, h_pt = h_pt, w_pt
    natural = res / 72.0  # escala do tamanho real
    fit = min(cell.width() / (w_pt * natural), cell.height() / (h_pt * natural))
    if opts.nup > 1 or opts.scale == "fit":
        s = fit
    elif opts.scale == "shrink":
        s = min(1.0, fit)
    elif opts.scale == "custom":
        s = opts.custom / 100.0
    else:
        s = 1.0
    w, h = w_pt * natural * s, h_pt * natural * s
    if opts.center or opts.nup > 1:
        x, y = cell.x() + (cell.width() - w) / 2, cell.y() + (cell.height() - h) / 2
    else:
        x, y = cell.x(), cell.y()
    painter.save()
    painter.setClipRect(cell)
    painter.drawImage(QRectF(x, y, w, h), img)
    painter.restore()


# ------------------------------------------------------------------ propriedades do driver (Windows)
def driver_properties(hwnd: int, printer_name: str) -> dict | None:
    """Abre as propriedades da impressora do Windows. Devolve o que foi escolhido nela
    (papel, orientação, cor, cópias) para refletir na janela; None se cancelado."""
    if not sys.platform.startswith("win"):
        return None
    import win32con
    import win32print
    h = win32print.OpenPrinter(printer_name)
    try:
        dm = win32print.GetPrinter(h, 2)["pDevMode"]
        r = win32print.DocumentProperties(hwnd, h, printer_name, dm, dm,
                                          win32con.DM_IN_PROMPT | win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER)
        if r != win32con.IDOK:
            return None
        return {"paper": getattr(dm, "PaperSize", 0), "orientation": getattr(dm, "Orientation", 0),
                "color": getattr(dm, "Color", 0), "copies": getattr(dm, "Copies", 0)}
    finally:
        win32print.ClosePrinter(h)


# ------------------------------------------------------------------ janela
class PrintDialog(QDialog):
    def __init__(self, parent, doc: pymupdf.Document, order: list[int] | None = None,
                 current: int = 0, selected: list[int] | None = None):
        super().__init__(parent)
        self.doc = doc
        self.order = order or list(range(doc.page_count))   # ordem atual das páginas
        self.current, self.selected = current, selected or []
        self.st = QSettings()
        self.setWindowTitle("Imprimir")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)

        # impressora
        g = QGroupBox("Impressora")
        gl = QGridLayout(g)
        self.printer_combo = QComboBox()
        names = QPrinterInfo.availablePrinterNames()
        default = QPrinterInfo.defaultPrinterName()
        last = self.st.value("print/printer", "")
        for n in names:
            self.printer_combo.addItem(("★ " if n == default else "") + n, n)
        pick = last if last in names else default
        if pick in names:
            self.printer_combo.setCurrentIndex(names.index(pick))
        if not names:
            self.printer_combo.addItem("Nenhuma impressora instalada", "")
        gl.addWidget(QLabel("Nome:"), 0, 0)
        gl.addWidget(self.printer_combo, 0, 1)
        self.props_btn = QPushButton("Propriedades da impressora...")
        self.props_btn.setToolTip("Abre as configurações do driver da impressora (Windows)")
        self.props_btn.clicked.connect(self._driver_props)
        self.props_btn.setVisible(sys.platform.startswith("win"))
        gl.addWidget(self.props_btn, 0, 2)
        self.printer_state = QLabel()
        self.printer_state.setObjectName("Muted")
        gl.addWidget(self.printer_state, 1, 1, 1, 2)
        gl.setColumnStretch(1, 1)
        lay.addWidget(g)

        row = QHBoxLayout()
        # páginas
        g = QGroupBox("Páginas")
        gl = QGridLayout(g)
        self.r_all = QRadioButton(f"Todas ({len(self.order)})")
        self.r_cur = QRadioButton(f"Página atual ({current + 1})")
        self.r_sel = QRadioButton(f"Páginas selecionadas nas miniaturas ({len(self.selected)})")
        self.r_sel.setEnabled(len(self.selected) > 0)
        self.r_range = QRadioButton("Intervalo:")
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText(f"ex.: 1-3, 5, 8-{len(self.order)}")
        self.range_edit.textEdited.connect(lambda _t: self.r_range.setChecked(True))
        (self.r_sel if len(self.selected) > 1 else self.r_all).setChecked(True)
        gl.addWidget(self.r_all, 0, 0, 1, 2)
        gl.addWidget(self.r_cur, 1, 0, 1, 2)
        gl.addWidget(self.r_sel, 2, 0, 1, 2)
        gl.addWidget(self.r_range, 3, 0)
        gl.addWidget(self.range_edit, 3, 1)
        self.subset = QComboBox()
        self.subset.addItem("Todas as páginas do intervalo", "all")
        self.subset.addItem("Somente as ímpares", "odd")
        self.subset.addItem("Somente as pares", "even")
        gl.addWidget(QLabel("Imprimir:"), 4, 0)
        gl.addWidget(self.subset, 4, 1)
        self.reverse = QCheckBox("Ordem inversa (da última para a primeira)")
        gl.addWidget(self.reverse, 5, 0, 1, 2)
        row.addWidget(g, 1)

        # cópias
        g = QGroupBox("Cópias")
        gl = QGridLayout(g)
        self.copies = QSpinBox(minimum=1, maximum=999)
        gl.addWidget(QLabel("Número de cópias:"), 0, 0)
        gl.addWidget(self.copies, 0, 1)
        self.collate = QCheckBox("Agrupar (1, 2, 3 · 1, 2, 3)")
        self.collate.setChecked(self.st.value("print/collate", True, type=bool))
        gl.addWidget(self.collate, 1, 0, 1, 2)
        duplex = QLabel("Sempre em <b>uma face só</b> (frente e verso desativado)")
        duplex.setWordWrap(True)
        duplex.setObjectName("Muted")
        gl.addWidget(duplex, 2, 0, 1, 2)
        gl.setRowStretch(3, 1)
        row.addWidget(g, 1)
        lay.addLayout(row)

        # layout
        g = QGroupBox("Papel e layout")
        gl = QGridLayout(g)
        self.orient = QComboBox()
        for k, t in (("auto", "Automática (conforme cada página)"), ("portrait", "Retrato (em pé)"),
                     ("landscape", "Paisagem (deitada)")):
            self.orient.addItem(t, k)
        gl.addWidget(QLabel("Orientação:"), 0, 0)
        gl.addWidget(self.orient, 0, 1)
        self.paper = QComboBox()
        gl.addWidget(QLabel("Papel:"), 0, 2)
        gl.addWidget(self.paper, 0, 3)
        self.scale = QComboBox()
        for k, t in (("fit", "Ajustar à página"), ("shrink", "Reduzir só as páginas grandes"),
                     ("actual", "Tamanho real (100%)"), ("custom", "Personalizada")):
            self.scale.addItem(t, k)
        self.custom = QSpinBox(minimum=10, maximum=400, value=100, suffix=" %")
        sc = QHBoxLayout()
        sc.addWidget(self.scale, 1)
        sc.addWidget(self.custom)
        gl.addWidget(QLabel("Escala:"), 1, 0)
        gl.addLayout(sc, 1, 1)
        self.nup = QComboBox()
        for n in NUP_GRID:
            self.nup.addItem(f"{n} página{'s' if n > 1 else ''} por folha", n)
        gl.addWidget(QLabel("Por folha:"), 1, 2)
        gl.addWidget(self.nup, 1, 3)
        self.color = QComboBox()
        self.color.addItem("Colorida", False)
        self.color.addItem("Tons de cinza (economiza tinta colorida)", True)
        gl.addWidget(QLabel("Cor:"), 2, 0)
        gl.addWidget(self.color, 2, 1)
        self.quality = QComboBox()
        for d, t in ((150, "Rascunho (150 dpi, mais rápida)"), (300, "Normal (300 dpi)"),
                     (600, "Alta (600 dpi)")):
            self.quality.addItem(t, d)
        gl.addWidget(QLabel("Qualidade:"), 2, 2)
        gl.addWidget(self.quality, 2, 3)
        self.annots = QCheckBox("Imprimir anotações, formas e comentários")
        self.annots.setChecked(True)
        self.center = QCheckBox("Centralizar na folha")
        self.center.setChecked(True)
        gl.addWidget(self.annots, 3, 0, 1, 2)
        gl.addWidget(self.center, 3, 2, 1, 2)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(3, 1)
        lay.addWidget(g)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_btn = bb.button(QDialogButtonBox.Ok)
        self.ok_btn.setText("Imprimir")
        self.ok_btn.setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._restore()
        self.printer_combo.currentIndexChanged.connect(self._printer_changed)
        for w in (self.r_all, self.r_cur, self.r_sel, self.r_range):
            w.toggled.connect(self._update)
        for w in (self.subset, self.nup, self.scale, self.orient):
            w.currentIndexChanged.connect(self._update)
        self.range_edit.textChanged.connect(self._update)
        self.copies.valueChanged.connect(self._update)
        self.reverse.toggled.connect(self._update)
        self._printer_changed()

    # ---------- estado
    def _set_data(self, combo, value):
        i = combo.findData(value)
        if i >= 0:
            combo.setCurrentIndex(i)

    def _restore(self):
        st = self.st
        self._set_data(self.orient, st.value("print/orientation", "auto"))
        self._set_data(self.scale, st.value("print/scale", "fit"))
        self.custom.setValue(int(st.value("print/custom", 100)))
        self._set_data(self.nup, int(st.value("print/nup", 1)))
        self._set_data(self.color, st.value("print/gray", False, type=bool))
        self._set_data(self.quality, int(st.value("print/dpi", 300)))
        self.annots.setChecked(st.value("print/annots", True, type=bool))
        self.center.setChecked(st.value("print/center", True, type=bool))

    def _save(self):
        st = self.st
        st.setValue("print/printer", self.printer_combo.currentData())
        st.setValue("print/orientation", self.orient.currentData())
        st.setValue("print/scale", self.scale.currentData())
        st.setValue("print/custom", self.custom.value())
        st.setValue("print/nup", self.nup.currentData())
        st.setValue("print/gray", self.color.currentData())
        st.setValue("print/dpi", self.quality.currentData())
        st.setValue("print/annots", self.annots.isChecked())
        st.setValue("print/center", self.center.isChecked())
        st.setValue("print/collate", self.collate.isChecked())
        if self.paper.currentData() is not None:
            st.setValue("print/paper", int(self.paper.currentData()))

    def _printer_changed(self):
        name = self.printer_combo.currentData() or ""
        info = QPrinterInfo.printerInfo(name) if name else QPrinterInfo()
        keep = self.paper.currentData()
        if keep is None:
            keep = int(self.st.value("print/paper", -1))
        self.paper.blockSignals(True)
        self.paper.clear()
        sizes = info.supportedPageSizes() if not info.isNull() else []
        ids = [s.id() for s in sizes]
        shown = set()
        for pid in COMMON_PAPERS:  # os comuns primeiro, se a impressora aceitar
            if not ids or pid in ids:
                self.paper.addItem(paper_name(QPageSize(pid)), int(pid.value))
                shown.add(pid)
        for s in sizes:
            if s.id() not in shown and s.id() != QPageSize.Custom:
                self.paper.addItem(paper_name(s), int(s.id().value))
                shown.add(s.id())
        default = info.defaultPageSize().id() if not info.isNull() else QPageSize.A4
        want = keep if keep not in (None, -1) else int(default.value)
        i = self.paper.findData(int(want))
        self.paper.setCurrentIndex(max(0, i))
        self.paper.blockSignals(False)
        if info.isNull():
            self.printer_state.setText("Nenhuma impressora encontrada. Instale uma impressora no Windows.")
        else:
            bits = [info.description() or "", info.location() or ""]
            if info.isDefault():
                bits.append("impressora padrão")
            self.printer_state.setText(" • ".join(b for b in bits if b))
        self.props_btn.setEnabled(bool(name))
        self.ok_btn.setEnabled(bool(name))
        self._update()

    def _driver_props(self):
        try:
            res = driver_properties(int(self.winId()), self.printer_combo.currentData())
        except Exception as e:  # driver sem suporte: segue com as opções desta janela
            self.printer_state.setText(f"Não foi possível abrir as propriedades da impressora: {e}")
            return
        if not res:
            return
        if res.get("orientation") in (1, 2):
            self._set_data(self.orient, "portrait" if res["orientation"] == 1 else "landscape")
        if res.get("color") in (1, 2):
            self._set_data(self.color, res["color"] == 1)
        if res.get("copies", 0) > 0:
            self.copies.setValue(res["copies"])
        if res.get("paper"):
            pid = QPageSize.id(int(res["paper"]))
            if pid != QPageSize.Custom:
                if self.paper.findData(int(pid.value)) < 0:
                    self.paper.addItem(paper_name(QPageSize(pid)), int(pid.value))
                self._set_data(self.paper, int(pid.value))

    # ---------- páginas
    def chosen_pages(self) -> list[int]:
        """Páginas (índices do documento) na ordem em que serão impressas."""
        total = len(self.order)
        if self.r_cur.isChecked():
            pos = [self.order.index(self.current)] if self.current in self.order else [0]
        elif self.r_sel.isChecked():
            pos = [self.order.index(p) for p in self.selected if p in self.order]
        elif self.r_range.isChecked():
            pos = parse_ranges(self.range_edit.text(), total)
        else:
            pos = list(range(total))
        sub = self.subset.currentData()
        if sub == "odd":
            pos = [p for p in pos if (p + 1) % 2 == 1]
        elif sub == "even":
            pos = [p for p in pos if (p + 1) % 2 == 0]
        if self.reverse.isChecked():
            pos = pos[::-1]
        return [self.order[p] for p in pos]

    def _update(self):
        self.custom.setEnabled(self.scale.currentData() == "custom" and self.nup.currentData() == 1)
        self.scale.setEnabled(self.nup.currentData() == 1)
        try:
            pages = self.chosen_pages()
        except ValueError as e:
            self.summary.setText(f"<span style='color:#d6232d'>⚠ {e}</span>")
            self.ok_btn.setEnabled(False)
            return
        self.ok_btn.setEnabled(bool(pages) and bool(self.printer_combo.currentData()))
        n = self.nup.currentData()
        sheets = -(-len(pages) // n) * self.copies.value()
        self.summary.setText(f"Serão impressas <b>{len(pages)} página(s)</b> em <b>{sheets} folha(s)</b>"
                             f"{f' ({self.copies.value()} cópias)' if self.copies.value() > 1 else ''}, "
                             "na ordem atual do documento.")

    def options(self) -> PrintOptions:
        return PrintOptions(pages=self.chosen_pages(), copies=self.copies.value(),
                            collate=self.collate.isChecked(), orientation=self.orient.currentData(),
                            scale=self.scale.currentData(), custom=self.custom.value(),
                            nup=self.nup.currentData(), gray=self.color.currentData(),
                            dpi=self.quality.currentData(), annots=self.annots.isChecked(),
                            center=self.center.isChecked())

    def configure(self, printer: QPrinter, opts: PrintOptions):
        configure_printer(printer, self.doc, self.printer_combo.currentData(), self.paper.currentData(), opts)

    def _accept(self):
        try:
            self.chosen_pages()
        except ValueError:
            return
        self._save()
        self.accept()


def configure_printer(printer: QPrinter, doc, name: str, paper_id, opts: PrintOptions):
    printer.setPrinterName(name)
    if paper_id is not None:
        printer.setPageSize(QPageSize(QPageSize.PageSizeId(int(paper_id))))
    if opts.orientation == "auto":
        first = doc[opts.pages[0]].rect if opts.pages else pymupdf.Rect(0, 0, 1, 2)
        landscape = first.width > first.height
        if opts.nup == 2:  # duas por folha ficam lado a lado em paisagem
            landscape = not landscape
    else:
        landscape = opts.orientation == "landscape"
    printer.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    printer.setColorMode(QPrinter.GrayScale if opts.gray else QPrinter.Color)
    printer.setCopyCount(1)  # as cópias são feitas aqui (agrupadas ou não)
    printer.setFullPage(False)
    _force_single_sided(printer)


def saved_setup(doc):
    """Impressora e opções da última impressão (ou a impressora padrão do Windows)."""
    st = QSettings()
    names = QPrinterInfo.availablePrinterNames()
    name = st.value("print/printer", "")
    if name not in names:
        name = QPrinterInfo.defaultPrinterName() or (names[0] if names else "")
    paper = st.value("print/paper", None)
    if paper is None and name:
        info = QPrinterInfo.printerInfo(name)
        paper = int(info.defaultPageSize().id().value) if not info.isNull() else None
    opts = PrintOptions(pages=list(range(doc.page_count)),
                        collate=st.value("print/collate", True, type=bool),
                        orientation=st.value("print/orientation", "auto"),
                        scale=st.value("print/scale", "fit"), custom=int(st.value("print/custom", 100)),
                        nup=int(st.value("print/nup", 1)), gray=st.value("print/gray", False, type=bool),
                        dpi=int(st.value("print/dpi", 300)), annots=st.value("print/annots", True, type=bool),
                        center=st.value("print/center", True, type=bool))
    return name, paper, opts


def print_silent(doc: pymupdf.Document, printer_name: str | None = None) -> str:
    """Imprime o documento inteiro sem abrir janela (botão direito › Imprimir)."""
    name, paper, opts = saved_setup(doc)
    name = printer_name or name
    if not name:
        raise RuntimeError("Nenhuma impressora instalada no Windows.")
    printer = QPrinter(QPrinter.HighResolution)
    printer.setDocName("Vorticis PDF")
    configure_printer(printer, doc, name, paper, opts)
    _paint(printer, doc, opts.pages, opts)
    return name


def print_document(parent, doc: pymupdf.Document, subset: list[int] | None = None,
                   current: int = 0, order: list[int] | None = None) -> bool:
    """subset = páginas selecionadas nas miniaturas (opção pré-marcada se houver mais de uma)."""
    dlg = PrintDialog(parent, doc, order, current, subset)
    if not dlg.exec():
        return False
    opts = dlg.options()
    printer = QPrinter(QPrinter.HighResolution)
    printer.setDocName("Vorticis PDF")
    dlg.configure(printer, opts)
    _force_single_sided(printer)  # nunca frente e verso
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        _paint(printer, doc, opts.pages, opts)
    finally:
        QApplication.restoreOverrideCursor()
    return True
