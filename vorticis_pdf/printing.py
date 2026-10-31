"""Impressão com pré-visualização (respeita a ordem atual das páginas)."""
from __future__ import annotations

import pymupdf
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPageLayout, QTransform
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter, QPrintPreviewDialog

from .viewer import pixmap_to_qimage

MAX_DPI = 300


def _paint(printer: QPrinter, doc: pymupdf.Document, pages: list[int]):
    painter = QPainter()
    if not painter.begin(printer):
        return
    dpi = min(printer.resolution(), MAX_DPI)
    try:
        for n, i in enumerate(pages):
            if n:
                printer.newPage()
            page = doc[i]
            area = QRectF(printer.pageLayout().paintRectPixels(printer.resolution()))
            area.moveTo(0, 0)
            img = pixmap_to_qimage(page.get_pixmap(dpi=dpi, alpha=False, annots=True))
            # gira automaticamente páginas paisagem para caber melhor no papel retrato (e vice-versa)
            if (img.width() > img.height()) != (area.width() > area.height()):
                img = img.transformed(QTransform().rotate(90))
            s = min(area.width() / img.width(), area.height() / img.height())
            w, h = img.width() * s, img.height() * s
            target = QRectF(area.x() + (area.width() - w) / 2, area.y() + (area.height() - h) / 2, w, h)
            painter.drawImage(target, img)
    finally:
        painter.end()


def _selected_pages(printer: QPrinter, page_count: int, subset: list[int] | None):
    pages = subset if subset else list(range(page_count))
    if printer.printRange() == QPrinter.PageRange:
        a, b = printer.fromPage(), printer.toPage()
        if a and b:
            pages = pages[a - 1:b]
    copies = []
    for _ in range(max(1, printer.copyCount() if not printer.supportsMultipleCopies() else 1)):
        copies += pages
    return copies


def print_document(parent, doc: pymupdf.Document, subset: list[int] | None = None, preview=True):
    printer = QPrinter(QPrinter.HighResolution)
    printer.setDocName("Vorticis PDF")
    first = doc[subset[0] if subset else 0].rect
    printer.setPageOrientation(QPageLayout.Landscape if first.width > first.height
                               else QPageLayout.Portrait)
    total = len(subset) if subset else doc.page_count
    printer.setFromTo(1, total)

    if preview:
        dlg = QPrintPreviewDialog(printer, parent)
        dlg.setWindowTitle("Pré-visualização de impressão")
        dlg.resize(1000, 800)
        dlg.paintRequested.connect(lambda p: _paint(p, doc, _selected_pages(p, doc.page_count, subset)))
        dlg.exec()
        return
    dlg = QPrintDialog(printer, parent)
    dlg.setOption(QAbstractPrintDialog.PrintPageRange, True)
    dlg.setMinMax(1, total)
    if dlg.exec():
        _paint(printer, doc, _selected_pages(printer, doc.page_count, subset))
