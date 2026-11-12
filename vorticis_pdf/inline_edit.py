"""Edição de texto direto na página (sem janela separada).

Ao clicar num texto com a ferramenta Editar texto (ou ao editar os textos selecionados por
retângulos), uma caixa de edição aparece exatamente sobre o texto original, com a fonte, o
tamanho e a cor reconhecidos. Uma barra de formatação no topo da janela permite trocar a
fonte, o tamanho e a cor. Enter aplica, Esc cancela, Tab passa para o próximo texto e um
clique fora da caixa também aplica. Todas as alterações viram um único passo de desfazer.
"""
from __future__ import annotations

import re

import pymupdf
from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QTextOption
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDoubleSpinBox, QFrame, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QToolBar, QToolButton,
)

from .fonts import (ResolvedFont, all_font_labels, font_from_choice, missing_glyphs, qt_family,
                    resolve_font, strip_subset)

KEEP = "__keep__"
BOLD_B14 = ("hebo", "tibo", "cobo", "hebi", "tibi", "cobi")
ITALIC_B14 = ("heit", "tiit", "coit", "hebi", "tibi", "cobi")


def int_to_rgb(color: int):
    return (((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255)


def qfont_for(font: ResolvedFont, pixel_size: float, flags: int = 0) -> QFont:
    f = QFont(qt_family(font) or "Arial")
    f.setPixelSize(max(4, round(pixel_size)))
    label = font.label.lower()
    f.setBold(font.base14 in BOLD_B14 or bool(flags & 16) or
              any(w in label for w in ("bold", "negrito", "black", "heavy")))
    f.setItalic(font.base14 in ITALIC_B14 or bool(flags & 2) or
                any(w in label for w in ("italic", "oblique", "itálico")))
    f.setKerning(True)
    return f


class InlineField(QPlainTextEdit):
    """Caixa de edição posicionada sobre o texto, na própria página."""

    def __init__(self, session: "InlineSession", page_widget, page_no: int, span: dict | None,
                 origin=None):
        super().__init__(page_widget)
        self.session, self.pw, self.page_no, self.span, self.origin = session, page_widget, page_no, span, origin
        self.multiline = span is None  # texto novo aceita várias linhas (Shift+Enter)
        self.orig_text = span["text"] if span else ""
        doc = session.pdoc.doc
        page = doc[page_no]
        self.flags = span["flags"] if span else 0
        self.detected = resolve_font(doc, page, span["font"] if span else "Helvetica", self.flags,
                                     self.orig_text or "Aa")
        self.orig_size = span["size"] if span else session.default_size
        self.orig_color = int_to_rgb(span["color"]) if span else (0, 0, 0)
        self.setObjectName("InlineField")
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setWordWrapMode(QTextOption.NoWrap)
        self.document().setDocumentMargin(1)
        self.setTabChangesFocus(False)
        self.setPlainText(self.orig_text)
        self.textChanged.connect(self._changed)
        self.show()

    # ---------- valores
    def text(self) -> str:
        t = self.toPlainText()
        return t if self.multiline else " ".join(t.split("\n"))

    def font_choice(self) -> ResolvedFont:
        s = self.session
        if s.font_choice != KEEP:
            return font_from_choice(s.font_choice)
        font = self.detected
        txt = self.text()
        if self.span and txt and missing_glyphs(font, txt):
            # a fonte embutida (subconjunto) não tem os novos caracteres: busca a mesma fonte instalada
            font = resolve_font(s.pdoc.doc, s.pdoc.doc[self.page_no], self.span["font"], self.flags, txt)
        return font

    def size(self) -> float:
        return self.session.size_override or self.orig_size

    def color(self):
        return self.session.color_override or self.orig_color

    def changed(self) -> bool:
        s = self.session
        return self.text() != self.orig_text or s.font_choice != KEEP or bool(s.size_override) or \
            bool(s.color_override)

    def fitted_size(self) -> tuple[float, float]:
        """(tamanho final, espaço disponível) — reduz para não sobrepor o vizinho."""
        size = self.size()
        if not (self.span and self.session.fit and self.text()):
            return size, 0.0
        fitted, _need, avail = self.session.pdoc.fit_size(self.page_no, self.span, self.text(),
                                                          self.font_choice(), size)
        return fitted, avail

    # ---------- aparência e posição
    def place(self):
        z = self.pw.view.zoom
        size = self.fitted_size()[0]
        qf = qfont_for(self.font_choice(), size * z, self.flags)
        self.setFont(qf)
        col = QColor.fromRgbF(*self.color()).name()
        # a fonte vai no estilo: a folha de estilo do tema definiria outra fonte e outro tamanho
        fam = qf.family().replace("'", "")
        self.setStyleSheet(
            f"#InlineField{{background:#ffffff;color:{col};border:1.5px solid #d6232d;"
            f"border-radius:2px;padding:0;margin:0;selection-background-color:#2f7bff;"
            f"selection-color:white;font-family:'{fam}';font-size:{qf.pixelSize()}px;"
            f"font-weight:{700 if qf.bold() else 400};font-style:{'italic' if qf.italic() else 'normal'}}}")
        fm = QFontMetricsF(qf)
        lines = self.toPlainText().split("\n") or [""]
        text_w = max(fm.horizontalAdvance(ln) for ln in lines) + fm.averageCharWidth() + 6
        text_h = fm.lineSpacing() * max(1, len(lines)) + 6
        if self.span:
            r = self.pw.to_screen(self.span["bbox"])
            x, y = r.x() - 3, r.y() - 3
            w, h = max(r.width() + 6, text_w), max(r.height() + 6, text_h)
            # alinha a linha de base da caixa com a do texto original
            base = self.pw.to_screen(pymupdf.Rect(self.span["origin"], self.span["origin"])).y()
            y = min(y, base - fm.ascent() - 3)
        else:
            r = self.pw.to_screen(pymupdf.Rect(self.origin, self.origin))
            x, y = r.x() - 3, r.y() - 3
            w, h = max(text_w, 12 * fm.averageCharWidth()), text_h
        w = min(w, max(40.0, self.pw.width() - x))
        self.setGeometry(int(x), int(y), int(w) + 2, int(h) + 2)

    def _changed(self):
        self.place()
        self.session.field_changed(self)

    # ---------- teclado
    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            if self.multiline and e.modifiers() & Qt.ShiftModifier:
                return super().keyPressEvent(e)
            self.session.commit()
            return
        if k == Qt.Key_Escape:
            self.session.cancel()
            return
        if k == Qt.Key_Tab:
            self.session.focus_next(1)
            return
        if k == Qt.Key_Backtab:
            self.session.focus_next(-1)
            return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.session.field_focused(self)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.MouseFocusReason, Qt.OtherFocusReason):
            c = self.textCursor()
            c.clearSelection()
            self.setTextCursor(c)


class InlineSession(QObject):
    """Um conjunto de caixas de edição abertas ao mesmo tempo (uma ou várias)."""
    finished = Signal(list, bool)   # alterações, aplicar?
    focusChanged = Signal(object)   # InlineField em foco
    stateChanged = Signal()

    def __init__(self, view, pdoc, items: list[tuple[int, dict]] | None = None, add_at=None,
                 default_size=12.0):
        super().__init__(view)
        self.view, self.pdoc = view, pdoc
        self.default_size = default_size
        self.font_choice = KEEP
        self.size_override = 0.0
        self.color_override = None
        self.fit = True
        self.fields: list[InlineField] = []
        self.current: InlineField | None = None
        self.done = False
        for pg, sp in sorted(items or [], key=lambda it: (it[0], it[1]["bbox"][1], it[1]["bbox"][0])):
            self.fields.append(InlineField(self, view.pages[pg], pg, sp))
        if add_at is not None:
            pg, pt = add_at
            self.fields.append(InlineField(self, view.pages[pg], pg, None, origin=pt))
        self.place_all()
        if self.fields:
            f = self.fields[0]
            view.ensureWidgetVisible(f, 80, 80)
            f.setFocus()
            f.selectAll()

    @property
    def adding(self) -> bool:
        return len(self.fields) == 1 and self.fields[0].span is None

    def place_all(self):
        for f in self.fields:
            f.place()

    def restyle(self):
        self.place_all()
        self.stateChanged.emit()

    def field_changed(self, f):
        if f is self.current:
            self.stateChanged.emit()

    def field_focused(self, f):
        self.current = f
        self.focusChanged.emit(f)
        self.stateChanged.emit()

    def focus_next(self, step):
        if not self.fields:
            return
        i = self.fields.index(self.current) if self.current in self.fields else -1
        f = self.fields[(i + step) % len(self.fields)]
        self.view.ensureWidgetVisible(f, 80, 80)
        f.setFocus()
        f.selectAll()

    def replace_all(self, needle: str, repl: str, case: bool) -> int:
        if not needle:
            return 0
        pat = re.compile(re.escape(needle), 0 if case else re.IGNORECASE)
        n = 0
        for f in self.fields:
            new, k = pat.subn(repl.replace("\\", "\\\\"), f.toPlainText())
            if k:
                f.setPlainText(new)
                n += k
        return n

    def changes(self) -> list[dict]:
        out = []
        for f in self.fields:
            if not f.changed():
                continue
            if f.span is None and not f.text().strip():
                continue
            out.append({"page": f.page_no, "span": f.span, "origin": f.origin, "text": f.text(),
                        "font": f.font_choice(), "size": f.size(), "color": f.color()})
        return out

    def commit(self):
        self._finish(True)

    def cancel(self):
        self._finish(False)

    def _finish(self, apply):
        if self.done:
            return
        self.done = True
        changes = self.changes() if apply else []
        for f in self.fields:
            f.hide()
            f.deleteLater()
        self.fields = []
        self.view.setFocus()
        self.finished.emit(changes, apply)


class TextEditBar(QToolBar):
    """Barra de formatação mostrada enquanto há caixas de edição abertas na página."""
    applyRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent):
        super().__init__("Edição de texto", parent)
        from .dialogs import ColorButton
        from .icons import icon
        self.setObjectName("HeaderBar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setContextMenuPolicy(Qt.PreventContextMenu)
        self.setIconSize(QSize(18, 18))
        self.session: InlineSession | None = None
        self.count = QLabel()
        self.count.setStyleSheet("font-weight:600")
        self.addWidget(self.count)
        self.addWidget(QLabel("  Fonte: "))
        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.setInsertPolicy(QComboBox.NoInsert)
        self.font_combo.setMinimumWidth(200)
        self.font_combo.setMaximumWidth(300)
        self.font_combo.setMaxVisibleItems(18)
        self.font_combo.addItem("★ Fonte original", KEEP)
        self._fonts_loaded = False
        self.font_combo.activated.connect(self._font_picked)
        self.font_combo.lineEdit().returnPressed.connect(self._font_typed)
        self.addWidget(self.font_combo)
        self.addWidget(QLabel("  Tamanho: "))
        self.size = QDoubleSpinBox(minimum=2, maximum=400, decimals=1, suffix=" pt")
        self.size.setFixedWidth(96)
        self.size.setKeyboardTracking(False)
        self.size.valueChanged.connect(self._size_changed)
        self.addWidget(self.size)
        self.addWidget(QLabel("  Cor: "))
        self.color = ColorButton((0, 0, 0))
        self.color.setFixedWidth(92)
        self.color.changed = self._color_changed
        self.addWidget(self.color)
        self.fit = QCheckBox("  Ajustar ao espaço")
        self.fit.setChecked(True)
        self.fit.setToolTip("Reduz o tamanho se o novo texto for maior que o espaço do original, "
                            "para não sobrepor linhas e marcações ao lado")
        self.fit.toggled.connect(self._fit_changed)
        self.fit_act = self.addWidget(self.fit)
        self.addWidget(QLabel("  "))
        self.apply_btn = QPushButton(icon("edit_text", "#ffffff"), "  Aplicar")
        self.apply_btn.setToolTip("Aplicar (Enter) — um clique fora da caixa também aplica")
        self.apply_btn.setObjectName("Primary")
        self.apply_btn.clicked.connect(self.applyRequested)
        self.addWidget(self.apply_btn)
        self.cancel_btn = QToolButton()
        self.cancel_btn.setText("Cancelar")
        self.cancel_btn.setToolTip("Cancelar (Esc)")
        self.cancel_btn.clicked.connect(self.cancelRequested)
        self.addWidget(self.cancel_btn)
        # localizar e substituir (vários textos)
        self.find = QLineEdit()
        self.find.setPlaceholderText("localizar")
        self.find.setFixedWidth(96)
        self.repl = QLineEdit()
        self.repl.setPlaceholderText("substituir por")
        self.repl.setFixedWidth(110)
        self.repl_btn = QToolButton()
        self.repl_btn.setText("Substituir")
        self.repl_btn.setToolTip("Substituir em todos os textos em edição")
        self.repl_btn.clicked.connect(self._replace)
        self.find_acts = [self.addWidget(QLabel("   ")), self.addWidget(self.find), self.addWidget(self.repl),
                          self.addWidget(self.repl_btn)]
        self.hide()

    def _info(self, text):
        """Detalhes da fonte vão para a barra de status (não ocupam espaço na barra)."""
        self._last_info = text
        win = self.parent()
        if hasattr(win, "statusBar"):
            win.statusBar().showMessage(text)

    def _load_fonts(self):
        if self._fonts_loaded:
            return
        self._fonts_loaded = True
        labels = all_font_labels()
        for lbl in labels:
            self.font_combo.addItem(lbl, lbl)
        comp = QCompleter([self.font_combo.itemText(i) for i in range(self.font_combo.count())], self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.font_combo.setCompleter(comp)
        self.font_combo.setToolTip(f"{len(labels)} fontes disponíveis")

    # ---------- ligação com a sessão
    def bind(self, s: InlineSession):
        self._load_fonts()
        self.session = s
        many = len(s.fields) > 1
        self.font_combo.setItemText(0, "★ Fonte original de cada texto" if many else "★ Fonte original")
        self.font_combo.setCurrentIndex(0)
        self.fit.setChecked(True)
        self.fit_act.setVisible(not s.adding)
        for a in self.find_acts:
            a.setVisible(many)
        self.find.clear()
        self.repl.clear()
        f = s.fields[0] if s.fields else None
        self.size.blockSignals(True)
        self.size.setValue(f.orig_size if f else 12)
        self.size.blockSignals(False)
        self.color.changed = lambda: None
        self.color.set_rgb(f.orig_color if f else (0, 0, 0))
        self.color.changed = self._color_changed
        if not s.adding:
            self.font_combo.setItemText(0, "★ Fonte original de cada texto" if many else
                                        f"★ {f.detected.label}  (fonte original)")
        s.stateChanged.connect(self.refresh)
        s.focusChanged.connect(self._focused)
        self.show()
        self.refresh()

    def _focused(self, f):
        if self.session and not self.session.size_override:
            self.size.blockSignals(True)
            self.size.setValue(f.orig_size)
            self.size.blockSignals(False)
        if self.session and not self.session.color_override:
            self.color.changed = lambda: None
            self.color.set_rgb(f.orig_color)
            self.color.changed = self._color_changed
        if self.session and len(self.session.fields) > 1 and self.session.font_choice == KEEP:
            self.font_combo.setItemText(0, f"★ Fonte original ({f.detected.label})")

    def refresh(self):
        s = self.session
        if not s or s.done:
            return
        n = len(s.fields)
        self.count.setText("  Novo texto  " if s.adding else
                           (f"  Editando {n} textos  " if n > 1 else "  Editando texto  "))
        f = s.current or (s.fields[0] if s.fields else None)
        if not f:
            return
        font = f.font_choice()
        bits = []
        if f.span:
            name = strip_subset(f.span["font"])
            bits.append(f"Original: {name} • {f.orig_size:.1f} pt")
            src = {"embutida": "fonte embutida no PDF", "sistema": "mesma fonte, instalada",
                   "similar": "fonte equivalente", "padrão": "fonte padrão (original indisponível)"}
            if s.font_choice == KEEP:
                bits.append(f"usando {font.label} ({src.get(font.source, font.source)})")
            fitted, avail = f.fitted_size()
            if fitted < f.size() - 0.05:
                bits.append(f"ajustado para {fitted:.1f} pt para caber em {avail:.0f} pt")
            elif not s.fit and f.text():
                need = s.pdoc.fit_size(f.page_no, f.span, f.text(), font, f.size())
                if need[0] < f.size() - 0.05:
                    bits.append("⚠ ultrapassa o espaço original")
        if f.span is None and f.text().strip():
            r = s.pdoc.text_rect((f.origin[0], f.origin[1] + f.size() * 0.8), f.text(), font, f.size())
            hits = s.pdoc.collisions(f.page_no, r)
            if hits:
                bits.append(f"⚠ aqui o texto ficará sobre {hits} elemento(s) existente(s)")
        miss = missing_glyphs(font, f.text())
        if miss:
            bits.append("⚠ sem desenho nesta fonte: " + " ".join(miss[:8]))
        if s.adding:
            bits.append("Shift+Enter = nova linha")
        elif n > 1:
            bits.append("Tab = próximo texto")
        self._info(" • ".join(bits))

    def unbind(self):
        if self.session:
            try:
                self.session.stateChanged.disconnect(self.refresh)
                self.session.focusChanged.disconnect(self._focused)
            except (RuntimeError, TypeError):
                pass
        self.session = None
        self.hide()
        win = self.parent()
        if hasattr(win, "statusBar"):
            win.statusBar().clearMessage()

    # ---------- controles
    def _font_picked(self, _i=None):
        if not self.session:
            return
        self.session.font_choice = self.font_combo.currentData() or KEEP
        self.session.restyle()
        self._refocus()

    def _font_typed(self):
        txt = self.font_combo.currentText().replace("★", "").strip()
        idx = self.font_combo.findText(txt, Qt.MatchContains)
        if idx >= 0:
            self.font_combo.setCurrentIndex(idx)
        self._font_picked()

    def _size_changed(self, v):
        if self.session:
            self.session.size_override = v
            self.session.restyle()

    def _color_changed(self):
        if self.session:
            self.session.color_override = self.color.rgb
            self.session.restyle()
            self._refocus()

    def _fit_changed(self, on):
        if self.session:
            self.session.fit = on
            self.session.restyle()

    def _replace(self):
        if not self.session:
            return
        n = self.session.replace_all(self.find.text(), self.repl.text(), False)
        self._info(f"{n} substituição(ões)")

    def _refocus(self):
        s = self.session
        if s and s.current and not s.done:
            s.current.setFocus()

