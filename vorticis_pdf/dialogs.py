"""Diálogos do aplicativo."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QCompleter,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QScrollArea,
    QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from . import converters as conv
from .config import human_size, read_history
from .document import merge_files, split_document, split_groups
from .fonts import (all_font_labels, catalog, describe_span, font_from_choice, missing_glyphs,
                    qt_family, resolve_font, strip_subset)
from .tasks import run_task
from .theme import c as tc
from .viewer import render_page

PDF_FILTER = "PDF (*.pdf)"
ALL_SUPPORTED = "Arquivos suportados (" + " ".join("*" + e for e in sorted(conv.TO_PDF_EXTS)) + ")"


def open_folder(path):
    path = os.path.abspath(path)
    if sys.platform.startswith("win"):
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", path])
        else:
            os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R" if os.path.isfile(path) else "", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) if os.path.isfile(path) else path])


# ====================================================================== edição de texto
class ColorButton(QPushButton):
    def __init__(self, rgb=(0, 0, 0)):
        super().__init__()
        self.set_rgb(rgb)
        self.clicked.connect(self._pick)

    def set_rgb(self, rgb):
        self.rgb = tuple(rgb)
        c = QColor.fromRgbF(*self.rgb)
        self.setText(c.name())
        self.setStyleSheet(f"background:{c.name()};color:{'white' if c.lightness() < 128 else 'black'};"
                           "border-radius:8px;padding:6px")
        self.changed()

    def changed(self):
        pass

    def _pick(self):
        c = QColorDialog.getColor(QColor.fromRgbF(*self.rgb), self, "Cor do texto")
        if c.isValid():
            self.set_rgb((c.redF(), c.greenF(), c.blueF()))


def int_to_rgb(color: int):
    return (((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255)


SOURCE_TEXT = {
    "embutida": ("✔ Fonte original do documento (embutida no PDF)", "ok"),
    "sistema": ("✔ Mesma fonte, instalada no computador", "ok"),
    "similar": ("≈ Fonte equivalente instalada (métricas compatíveis)", "warn"),
    "padrão": ("⚠ Fonte original indisponível — usando a fonte padrão mais próxima", "accent_text"),
}


class TextDialog(QDialog):
    """Editar um trecho existente (fonte original reconhecida e exibida) ou adicionar texto."""

    def __init__(self, parent, pdoc, page_no: int, span: dict | None = None, origin=None):
        super().__init__(parent)
        self.pdoc, self.page_no, self.span, self.origin = pdoc, page_no, span, origin
        self.doc = pdoc.doc
        self.page = self.doc[page_no]
        self.setWindowTitle("Editar texto" if span else "Adicionar texto")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        self.pdf_font = span["font"] if span else "Helvetica"
        self.flags = span["flags"] if span else 0
        self.orig_text = span["text"] if span else ""
        self.detected = resolve_font(self.doc, self.page, self.pdf_font, self.flags, self.orig_text or "Aa")

        # ---- cartão com a fonte original
        if span:
            info = describe_span(self.doc, self.page, span)
            style = ", ".join(x for x, on in (("Negrito", info["negrito"]), ("Itálico", info["italico"]),
                                               ("Serifada", info["serifa"]), ("Monoespaçada", info["mono"])) if on) or "Normal"
            emb = ("Sim (subconjunto)" if info["subconjunto"] else "Sim") if info["embutida"] else "Não"
            card = QGroupBox("Fonte detectada no documento")
            g = QGridLayout(card)
            rows = [("Fonte", f"<b>{info['nome']}</b>"), ("Estilo", style),
                    ("Tamanho", f"{info['tamanho']:.1f} pt"),
                    ("Cor", f"<span style='color:{info['cor']}'>■</span> {info['cor']}"),
                    ("Tipo", info["tipo"] or "—"), ("Embutida no PDF", emb)]
            for i, (k, v) in enumerate(rows):
                lk = QLabel(k + ":")
                lk.setObjectName("Muted")
                lv = QLabel(v)
                lv.setTextInteractionFlags(Qt.TextSelectableByMouse)
                g.addWidget(lk, i // 2, (i % 2) * 2)
                g.addWidget(lv, i // 2, (i % 2) * 2 + 1)
            self.source_lbl = QLabel()
            self.source_lbl.setWordWrap(True)
            g.addWidget(self.source_lbl, 3, 0, 1, 4)
            lay.addWidget(card)
        else:
            self.source_lbl = QLabel()
            lay.addWidget(QLabel("O texto será inserido no ponto clicado. Use \u21b5 para várias linhas."))

        hint = QLabel("<b>Texto</b>" + (f"  <span style='color:{tc('muted')}'>— uma linha; ajustado ao espaço "
                                        "disponível para não sobrepor linhas e marcações</span>" if span else ""))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.edit = QPlainTextEdit(self.orig_text)
        self.edit.setFixedHeight(80 if span else 120)
        lay.addWidget(self.edit)

        form = QFormLayout()
        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.setInsertPolicy(QComboBox.NoInsert)
        labels = all_font_labels()
        tag = "fonte original" if span else "padrão"
        self.font_combo.addItem(f"★ {self.detected.label}  ({tag})", "__detected__")
        for lbl in labels:
            self.font_combo.addItem(lbl, lbl)
        comp = QCompleter([self.font_combo.itemText(i) for i in range(self.font_combo.count())], self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.font_combo.setCompleter(comp)
        form.addRow(f"Fonte ({len(labels)} disponíveis):", self.font_combo)
        self.size = QDoubleSpinBox(minimum=2, maximum=400, decimals=1, suffix=" pt")
        self.size.setValue(span["size"] if span else 12)
        form.addRow("Tamanho:", self.size)
        self.color = ColorButton(int_to_rgb(span["color"]) if span else (0, 0, 0))
        form.addRow("Cor:", self.color)
        self.fit = QCheckBox("Ajustar o tamanho automaticamente para não ultrapassar o espaço do texto original")
        self.fit.setChecked(True)
        if span:
            form.addRow(self.fit)
        lay.addLayout(form)

        lay.addWidget(QLabel("<b>Prévia</b>"))
        self.preview = QLabel()
        self.preview.setMinimumHeight(54)
        lay.addWidget(self.preview)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        lay.addWidget(self.warn)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Aplicar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.edit.textChanged.connect(self._update)
        self.font_combo.currentIndexChanged.connect(self._update)
        self.size.valueChanged.connect(self._update)
        self.fit.toggled.connect(self._update)
        self.color.changed = self._update
        self._update()
        self.edit.setFocus()
        self.edit.selectAll()

    def _chosen_font(self, text):
        data = self.font_combo.currentData()
        if data is None:
            txt = self.font_combo.currentText().replace("★", "").strip()
            idx = self.font_combo.findText(txt, Qt.MatchContains)
            data = self.font_combo.itemData(idx) if idx >= 0 else "__detected__"
        if data != "__detected__":
            return font_from_choice(data)
        font = self.detected
        if self.span and missing_glyphs(font, text):
            # a fonte embutida (subconjunto) não tem os novos caracteres: procura a mesma fonte instalada
            font = resolve_font(self.doc, self.page, self.pdf_font, self.flags, text)
        return font

    def _update(self):
        text = self.edit.toPlainText()
        if self.span:
            text = " ".join(text.split("\n"))
        font = self._chosen_font(text or "Aa")
        self._font = font
        msg, color = SOURCE_TEXT.get(font.source, ("", "text"))
        if self.font_combo.currentData() not in ("__detected__", None):
            msg, color = (f"Fonte escolhida manualmente: {font.label}", "text")
        color = tc(color)
        self.source_lbl.setText(f"<span style='color:{color}'><b>Será usada:</b> {font.label} — {msg}</span>")
        size = self.size.value()
        warns = []
        miss = missing_glyphs(font, text)
        if miss:
            warns.append("⚠ Caracteres sem desenho nesta fonte: " + " ".join(miss[:12]))
        self._final_size = size
        if self.span and text:
            fitted, need, avail = self.pdoc.fit_size(self.page_no, self.span, text, font, size)
            if fitted < size:
                if self.fit.isChecked():
                    self._final_size = fitted
                    warns.append(f"ℹ O texto é maior que o espaço disponível ({avail:.0f} pt). "
                                 f"Tamanho ajustado para {fitted:.1f} pt para não sobrepor o conteúdo ao lado.")
                else:
                    warns.append("⚠ O texto ultrapassa o espaço do original e pode sobrepor linhas ou marcações.")
        elif not self.span and text and self.origin is not None:
            r = self.pdoc.text_rect((self.origin[0], self.origin[1] + size * 0.8), text, font, size)
            n = self.pdoc.collisions(self.page_no, r)
            if n:
                warns.append(f"⚠ Neste ponto o texto ficará sobre {n} elemento(s) existente(s) "
                             "(texto, linhas ou marcações). Clique em outro lugar se preferir.")
        self.warn.setText("<br>".join(f"<span style='color:{tc('warn')}'>{w}</span>" for w in warns))
        fam = qt_family(font) or "Arial"
        bold = font.base14 in ("hebo", "tibo", "cobo", "hebi", "tibi", "cobi") or \
            any(w in font.label.lower() for w in ("bold", "negrito", "black", "heavy"))
        italic = font.base14 in ("heit", "tiit", "coit", "hebi", "tibi", "cobi") or \
            any(w in font.label.lower() for w in ("italic", "oblique", "itálico"))
        pt = max(7.0, min(28.0, self._final_size * 1.3))
        # a prévia usa estilo próprio (o tema global definiria outra fonte)
        self.preview.setStyleSheet(
            f"background:white;border:1px solid {tc('border')};border-radius:8px;padding:8px;"
            f"font-family:'{fam}';font-size:{pt:.1f}pt;font-weight:{700 if bold else 400};"
            f"font-style:{'italic' if italic else 'normal'};"
            f"color:{QColor.fromRgbF(*self.color.rgb).name()}")
        self.preview.setText(text.split("\n")[0][:120] or " ")

    def values(self):
        """(texto, fonte, tamanho final, cor, ajustar)."""
        self._update()
        return self.edit.toPlainText(), self._font, self.size.value(), self.color.rgb, self.fit.isChecked()


class MultiTextDialog(QDialog):
    """Edição simultânea de vários textos selecionados com a ferramenta Seleção."""

    COL_PAGE, COL_ORIG, COL_NEW, COL_FONT = range(4)

    def __init__(self, parent, pdoc, items: list[tuple[int, dict]]):
        super().__init__(parent)
        self.pdoc, self.items = pdoc, items
        self.setWindowTitle(f"Editar {len(items)} texto(s) selecionado(s)")
        self.resize(940, 620)
        lay = QVBoxLayout(self)
        intro = QLabel("Edite os textos na coluna <b>Novo texto</b>. Cada texto mantém a sua fonte "
                       "original, e o tamanho é ajustado para não sobrepor linhas e marcações.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        fr = QHBoxLayout()
        self.find = QLineEdit()
        self.find.setPlaceholderText("localizar em todos os textos selecionados")
        self.repl = QLineEdit()
        self.repl.setPlaceholderText("substituir por")
        self.case = QCheckBox("Diferenciar maiúsculas")
        b = QPushButton("Substituir em todos")
        b.clicked.connect(self._replace_all)
        fr.addWidget(QLabel("Localizar:"))
        fr.addWidget(self.find, 2)
        fr.addWidget(QLabel("por:"))
        fr.addWidget(self.repl, 2)
        fr.addWidget(self.case)
        fr.addWidget(b)
        lay.addLayout(fr)

        self.table = QTableWidget(len(items), 4)
        self.table.setHorizontalHeaderLabels(["Pág.", "Texto original", "Novo texto", "Fonte original"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        for r, (pg, sp) in enumerate(items):
            vals = [str(pg + 1), sp["text"], sp["text"],
                    f"{strip_subset(sp['font'])} • {sp['size']:.1f} pt"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c != self.COL_NEW:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    if c == self.COL_ORIG:
                        it.setForeground(QColor(tc("muted")))
                self.table.setItem(r, c, it)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_PAGE, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_ORIG, QHeaderView.Stretch)
        hh.setSectionResizeMode(self.COL_NEW, QHeaderView.Stretch)
        hh.setSectionResizeMode(self.COL_FONT, QHeaderView.ResizeToContents)
        lay.addWidget(self.table, 1)

        box = QGroupBox("Aplicar a todos os textos selecionados")
        g = QGridLayout(box)
        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.setInsertPolicy(QComboBox.NoInsert)
        self.font_combo.addItem("★ Manter a fonte original de cada texto", "__keep__")
        for lbl in all_font_labels():
            self.font_combo.addItem(lbl, lbl)
        comp = QCompleter([self.font_combo.itemText(i) for i in range(self.font_combo.count())], self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.font_combo.setCompleter(comp)
        g.addWidget(QLabel("Fonte:"), 0, 0)
        g.addWidget(self.font_combo, 0, 1, 1, 3)
        self.keep_size = QCheckBox("Manter o tamanho original")
        self.keep_size.setChecked(True)
        self.size = QDoubleSpinBox(minimum=2, maximum=400, decimals=1, suffix=" pt")
        self.size.setValue(items[0][1]["size"] if items else 12)
        self.size.setEnabled(False)
        self.keep_size.toggled.connect(lambda on: self.size.setEnabled(not on))
        g.addWidget(self.keep_size, 1, 0, 1, 2)
        g.addWidget(self.size, 1, 2)
        self.keep_color = QCheckBox("Manter a cor original")
        self.keep_color.setChecked(True)
        self.color = ColorButton(int_to_rgb(items[0][1]["color"]) if items else (0, 0, 0))
        self.color.setEnabled(False)
        self.keep_color.toggled.connect(lambda on: self.color.setEnabled(not on))
        g.addWidget(self.keep_color, 2, 0, 1, 2)
        g.addWidget(self.color, 2, 2)
        self.fit = QCheckBox("Ajustar o tamanho automaticamente para não ultrapassar o espaço de cada texto")
        self.fit.setChecked(True)
        g.addWidget(self.fit, 3, 0, 1, 4)
        lay.addWidget(box)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Aplicar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _replace_all(self):
        import re
        needle = self.find.text()
        if not needle:
            return
        flags = 0 if self.case.isChecked() else re.IGNORECASE
        pat = re.compile(re.escape(needle), flags)
        n = 0
        for r in range(self.table.rowCount()):
            it = self.table.item(r, self.COL_NEW)
            new, k = pat.subn(self.repl.text().replace("\\", "\\\\"), it.text())
            if k:
                it.setText(new)
                n += k
        self.find.setStyleSheet("" if n else f"border:1px solid {tc('accent')}")
        self.setWindowTitle(f"Editar {len(self.items)} texto(s) — {n} substituição(ões)")

    def values(self) -> list[dict]:
        """Itens para PdfDocument.replace_texts (só os que mudam)."""
        doc = self.pdoc.doc
        choice = self.font_combo.currentData()
        if choice is None:  # digitado
            idx = self.font_combo.findText(self.font_combo.currentText().replace("★", "").strip(),
                                           Qt.MatchContains)
            choice = self.font_combo.itemData(idx) if idx >= 0 else "__keep__"
        common_font = None if choice == "__keep__" else font_from_choice(choice)
        out = []
        for r, (pg, sp) in enumerate(self.items):
            text = self.table.item(r, self.COL_NEW).text()
            style_changed = common_font is not None or not self.keep_size.isChecked() or \
                not self.keep_color.isChecked()
            if text == sp["text"] and not style_changed:
                continue
            font = common_font
            if font is None:
                page = doc[pg]
                font = resolve_font(doc, page, sp["font"], sp["flags"], text or "Aa")
            out.append({"page": pg, "span": sp, "text": text, "font": font,
                        "size": sp["size"] if self.keep_size.isChecked() else self.size.value(),
                        "color": int_to_rgb(sp["color"]) if self.keep_color.isChecked() else self.color.rgb})
        return out


# ====================================================================== informações de salvamento
class SaveInfoDialog(QDialog):
    def __init__(self, parent, info: dict, title="Documento salvo com sucesso"):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME + " — Informações de salvamento")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        head = QLabel(f"<h3 style='color:{tc('ok')}'>✔ {title}</h3>")
        lay.addWidget(head)
        rows = [("Arquivo", info.get("arquivo", "")), ("Data/hora", info.get("data_hora", "")),
                ("Páginas", str(info.get("paginas", ""))),
                ("Tamanho anterior", info.get("tamanho_anterior", "—")),
                ("Tamanho atual", info.get("tamanho_atual", "—")),
                ("Protegido por senha", "Sim" if info.get("protegido_senha") else "Não"),
                ("Gravado por", info.get("produtor", f"{APP_NAME} {__version__}"))]
        grid = QFormLayout()
        for k, v in rows:
            lbl = QLabel(v)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lbl.setWordWrap(True)
            grid.addRow(f"<b>{k}:</b>", lbl)
        lay.addLayout(grid)
        lay.addWidget(QLabel("<b>Alterações registradas:</b>"))
        lst = QListWidget()
        lst.addItems(info.get("alteracoes", []))
        lst.setMaximumHeight(160)
        lay.addWidget(lst)
        lay.addWidget(QLabel("<small>Estas informações também ficam no histórico "
                             "(Arquivo ▸ Histórico de salvamentos) e nos metadados do PDF.</small>"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        folder = bb.addButton("Abrir pasta", QDialogButtonBox.ActionRole)
        folder.clicked.connect(lambda: open_folder(info.get("arquivo", "")))
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


class HistoryDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Histórico de salvamentos")
        self.resize(900, 460)
        lay = QVBoxLayout(self)
        hist = read_history()
        t = QTableWidget(len(hist), 5)
        t.setHorizontalHeaderLabels(["Data/hora", "Arquivo", "Páginas", "Tamanho", "Alterações"])
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        for r, h in enumerate(hist):
            vals = [h.get("data_hora", ""), h.get("arquivo", ""), str(h.get("paginas", "")),
                    h.get("tamanho_atual", ""), "; ".join(h.get("alteracoes", []))]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setToolTip(v)
                t.setItem(r, c, item)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        t.cellDoubleClicked.connect(lambda r, _c: open_folder(hist[r].get("arquivo", "")))
        lay.addWidget(QLabel("Dê dois cliques para abrir a pasta do arquivo."))
        lay.addWidget(t)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


# ====================================================================== propriedades / fontes
class PropertiesDialog(QDialog):
    def __init__(self, parent, pdoc):
        super().__init__(parent)
        self.setWindowTitle("Propriedades do documento")
        self.resize(760, 520)
        doc = pdoc.doc
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # --- metadados
        w = QWidget()
        form = QFormLayout(w)
        meta = doc.metadata or {}
        self.fields = {}
        for key, label in (("title", "Título"), ("author", "Autor"), ("subject", "Assunto"),
                           ("keywords", "Palavras-chave"), ("creator", "Aplicativo de origem")):
            e = QLineEdit(meta.get(key, "") or "")
            self.fields[key] = e
            form.addRow(label + ":", e)
        for label, val in (("Produtor", meta.get("producer", "")),
                           ("Criado em", _pdf_date(meta.get("creationDate", ""))),
                           ("Modificado em", _pdf_date(meta.get("modDate", ""))),
                           ("Formato", meta.get("format", "")),
                           ("Páginas", str(doc.page_count)),
                           ("Arquivo", pdoc.path or "(não salvo)"),
                           ("Tamanho", human_size(pdoc.original_size) if pdoc.original_size else "—"),
                           ("Criptografia", meta.get("encryption") or "Nenhuma")):
            form.addRow(label + ":", QLabel(str(val)))
        tabs.addTab(w, "Descrição")

        # --- fontes
        t = QTableWidget(0, 5)
        t.setHorizontalHeaderLabels(["Fonte no PDF", "Tipo", "Embutida", "Páginas",
                                     "Correspondente no sistema"])
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        fonts = {}
        for pno in range(doc.page_count):
            for xref, ext, ftype, basefont, *_ in doc[pno].get_fonts(full=True):
                f = fonts.setdefault(basefont, {"type": ftype, "emb": ext not in ("n/a", ""),
                                                "pages": []})
                if pno + 1 not in f["pages"]:
                    f["pages"].append(pno + 1)
        for name, f in sorted(fonts.items()):
            r = t.rowCount()
            t.insertRow(r)
            sf, exact = catalog.match(name)
            match = (sf.label + ("" if exact else "  (semelhante)")) if sf else "— (usa fonte padrão)"
            pages = f["pages"]
            pages_s = ", ".join(map(str, pages[:8])) + ("..." if len(pages) > 8 else "")
            for c, v in enumerate([strip_subset(name), f["type"], "Sim" if f["emb"] else "Não",
                                   pages_s, match]):
                t.setItem(r, c, QTableWidgetItem(v))
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.addWidget(QLabel(f"{len(fonts)} fonte(s) usada(s) no documento — "
                            f"{len(catalog.fonts)} fonte(s) instalada(s) no sistema."))
        fl.addWidget(t)
        tabs.addTab(fw, "Fontes")

        # --- segurança
        sw = QWidget()
        sl = QFormLayout(sw)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("deixe em branco para não proteger")
        sl.addRow("Senha ao salvar:", self.password)
        sl.addRow(QLabel("<small>A senha é aplicada (AES-256) no próximo salvamento.</small>"))
        tabs.addTab(sw, "Segurança")

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def metadata(self):
        return {k: e.text() for k, e in self.fields.items()}


def _pdf_date(s):
    s = (s or "").replace("D:", "")
    if len(s) >= 14:
        return f"{s[6:8]}/{s[4:6]}/{s[0:4]} {s[8:10]}:{s[10:12]}:{s[12:14]}"
    return s or "—"


# ====================================================================== pré-visualização ampliada
class PagePreviewDialog(QDialog):
    def __init__(self, parent, doc, index):
        super().__init__(parent)
        self.doc, self.index = doc, index
        self.resize(820, 960)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.prev_b = QPushButton("◀")
        self.next_b = QPushButton("▶")
        self.lbl = QLabel()
        self.slider = QSlider(Qt.Horizontal, minimum=25, maximum=400, value=100)
        bar.addWidget(self.prev_b)
        bar.addWidget(self.lbl)
        bar.addWidget(self.next_b)
        bar.addStretch()
        bar.addWidget(QLabel("Zoom:"))
        bar.addWidget(self.slider)
        lay.addLayout(bar)
        self.area = QScrollArea()
        self.area.setAlignment(Qt.AlignCenter)
        self.img = QLabel()
        self.area.setWidget(self.img)
        lay.addWidget(self.area)
        self.prev_b.clicked.connect(lambda: self.show_page(self.index - 1))
        self.next_b.clicked.connect(lambda: self.show_page(self.index + 1))
        self.slider.valueChanged.connect(lambda _v: self.show_page(self.index))
        self.show_page(index)

    def show_page(self, i):
        i = max(0, min(i, self.doc.page_count - 1))
        self.index = i
        z = self.slider.value() / 100 * 1.3
        self.img.setPixmap(QPixmap.fromImage(render_page(self.doc[i], z, self.devicePixelRatioF())))
        self.img.adjustSize()
        self.lbl.setText(f"Página {i + 1} de {self.doc.page_count}")
        self.setWindowTitle(f"Visualizar — página {i + 1}")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Right, Qt.Key_PageDown):
            self.show_page(self.index + 1)
        elif e.key() in (Qt.Key_Left, Qt.Key_PageUp):
            self.show_page(self.index - 1)
        elif e.key() == Qt.Key_Space:
            self.close()
        else:
            super().keyPressEvent(e)


# ====================================================================== lista de arquivos (reutilizável)
class FileList(QListWidget):
    def __init__(self, files=(), exts=None):
        super().__init__()
        self.exts = exts
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setAcceptDrops(True)
        for f in files:
            self.add(f)

    def add(self, path):
        if not path or not os.path.isfile(path):
            return
        if self.exts and Path(path).suffix.lower() not in self.exts:
            return
        if path in self.files():
            return
        it = QListWidgetItem(Path(path).name)
        it.setData(Qt.UserRole, path)
        it.setToolTip(path)
        try:
            if path.lower().endswith(".pdf"):
                with pymupdf.open(path) as d:
                    it.setText(f"{Path(path).name}   ({d.page_count} pág.)")
        except Exception:
            pass
        self.addItem(it)

    def files(self):
        return [p for p in (self.item(i).data(Qt.UserRole) for i in range(self.count())) if p]

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                p = u.toLocalFile()
                if os.path.isdir(p):
                    for f in sorted(os.listdir(p), key=str.lower):
                        self.add(os.path.join(p, f))
                elif p:
                    self.add(p)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


def file_buttons(parent, flist: FileList, filt):
    box = QVBoxLayout()

    def add_files():
        files, _ = QFileDialog.getOpenFileNames(parent, "Adicionar arquivos", "", filt)
        for f in files:
            flist.add(f)

    def add_folder():
        d = QFileDialog.getExistingDirectory(parent, "Adicionar todos os arquivos da pasta")
        if d:
            for f in sorted(os.listdir(d), key=str.lower):
                p = os.path.join(d, f)
                if os.path.isfile(p):
                    flist.add(p)

    def move(delta):
        rows = sorted((flist.row(i) for i in flist.selectedItems()), reverse=delta > 0)
        for r in rows:
            nr = r + delta
            if 0 <= nr < flist.count():
                it = flist.takeItem(r)
                flist.insertItem(nr, it)
                it.setSelected(True)

    def sort_name():
        files = sorted(flist.files(), key=lambda p: Path(p).name.lower())
        flist.clear()
        for f in files:
            flist.add(f)

    for text, fn in (("Adicionar arquivos...", add_files), ("Adicionar pasta...", add_folder),
                     ("▲ Subir", lambda: move(-1)), ("▼ Descer", lambda: move(1)),
                     ("Ordenar por nome", sort_name),
                     ("Remover", lambda: [flist.takeItem(flist.row(i)) for i in flist.selectedItems()]),
                     ("Limpar", flist.clear)):
        b = QPushButton(text)
        b.clicked.connect(fn)
        box.addWidget(b)
    box.addStretch()
    return box


# ====================================================================== unir
class MergeDialog(QDialog):
    opened = Signal(str)

    def __init__(self, parent=None, files=()):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Unir arquivos")
        self.resize(720, 480)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Arraste para definir a ordem. Aceita PDF, Word, Excel, PowerPoint, "
                             "imagens e outros (convertidos automaticamente)."))
        row = QHBoxLayout()
        self.list = FileList(files, conv.TO_PDF_EXTS)
        row.addWidget(self.list, 1)
        row.addLayout(file_buttons(self, self.list, ALL_SUPPORTED))
        lay.addLayout(row)
        self.bookmarks = QCheckBox("Criar marcadores com o nome de cada arquivo")
        self.bookmarks.setChecked(True)
        lay.addWidget(self.bookmarks)
        self.open_after = QCheckBox("Abrir o resultado no editor")
        self.open_after.setChecked(True)
        lay.addWidget(self.open_after)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        go = bb.addButton("Unir e salvar...", QDialogButtonBox.AcceptRole)
        go.setDefault(True)
        bb.accepted.connect(self._merge)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _merge(self):
        files = self.list.files()
        if len(files) < 1:
            QMessageBox.warning(self, APP_NAME, "Adicione pelo menos um arquivo.")
            return
        first = Path(files[0])
        out, _ = QFileDialog.getSaveFileName(self, "Salvar PDF unido",
                                             str(first.with_name(first.stem + "_unido.pdf")), PDF_FILTER)
        if not out:
            return

        bookmarks = self.bookmarks.isChecked()  # lido aqui: widgets só na thread da interface

        def work():
            tmpdir = tempfile.mkdtemp(prefix="vorticis_")
            srcs = []
            for f in files:
                if Path(f).suffix.lower() in conv.OFFICE_TO_PDF:
                    tmp = os.path.join(tmpdir, Path(f).stem + ".pdf")
                    conv.to_pdf(f, tmp)
                    srcs.append(tmp)
                else:
                    srcs.append(f)
            info = merge_files(srcs, out, bookmarks=bookmarks)
            info["alteracoes"] = [f"Uniu {len(files)} arquivo(s)"] + [Path(f).name for f in files]
            return info

        def done(info):
            SaveInfoDialog(self, info, "Arquivos unidos com sucesso").exec()
            if self.open_after.isChecked():
                self.opened.emit(out)
            self.accept()

        run_task(self, "Unindo arquivos...", work, on_done=done)


# ====================================================================== separar
class SplitDialog(QDialog):
    def __init__(self, parent=None, files=(), doc: pymupdf.Document | None = None, name="documento"):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Separar PDF")
        self.resize(640, 460)
        self.doc = doc
        self.name = name
        lay = QVBoxLayout(self)
        if doc is None:
            row = QHBoxLayout()
            self.list = FileList(files, {".pdf"})
            row.addWidget(self.list, 1)
            row.addLayout(file_buttons(self, self.list, PDF_FILTER))
            lay.addLayout(row)
        else:
            self.list = None
            lay.addWidget(QLabel(f"<b>Documento:</b> {name} ({doc.page_count} páginas)"))
        g = QGroupBox("Como separar")
        gl = QGridLayout(g)
        self.mode = QButtonGroup(self)
        self.every = QSpinBox(minimum=1, maximum=10000, value=1)
        self.ranges = QLineEdit()
        self.ranges.setPlaceholderText("ex.: 1-3, 4, 5-10, 11-")
        opts = [("each", "Uma página por arquivo", None),
                ("every", "A cada N páginas:", self.every),
                ("ranges", "Por intervalos (cada intervalo = 1 arquivo):", self.ranges),
                ("half", "Ao meio (duas partes)", None)]
        for r, (key, text, widget) in enumerate(opts):
            rb = QRadioButton(text)
            rb.setProperty("key", key)
            self.mode.addButton(rb, r)
            gl.addWidget(rb, r, 0)
            if widget:
                gl.addWidget(widget, r, 1)
        self.mode.button(0).setChecked(True)
        lay.addWidget(g)
        orow = QHBoxLayout()
        self.out_dir = QLineEdit()
        default_dir = (Path(files[0]).parent if files else Path.home())
        self.out_dir.setText(str(default_dir))
        b = QPushButton("...")
        b.clicked.connect(lambda: self.out_dir.setText(
            QFileDialog.getExistingDirectory(self, "Pasta de saída", self.out_dir.text()) or self.out_dir.text()))
        orow.addWidget(QLabel("Salvar em:"))
        orow.addWidget(self.out_dir, 1)
        orow.addWidget(b)
        lay.addLayout(orow)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        bb.addButton("Separar", QDialogButtonBox.AcceptRole).setDefault(True)
        bb.accepted.connect(self._split)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _split(self):
        key = self.mode.checkedButton().property("key")
        value = str(self.every.value()) if key == "every" else self.ranges.text()
        out_dir = self.out_dir.text()
        jobs = []
        if self.doc is not None:
            # cópia independente: o documento aberto continua livre para a interface
            jobs.append((pymupdf.open("pdf", self.doc.tobytes()), self.name))
        else:
            for f in self.list.files():
                jobs.append((f, Path(f).stem))
        if not jobs:
            QMessageBox.warning(self, APP_NAME, "Adicione pelo menos um PDF.")
            return

        def work():
            written = []
            for src, base in jobs:
                d = pymupdf.open(src) if isinstance(src, str) else src
                groups = split_groups(key, d.page_count, value)
                written += split_document(d, groups, out_dir, base)
            return written

        def done(written):
            QMessageBox.information(self, APP_NAME, f"{len(written)} arquivo(s) criado(s) em:\n{out_dir}")
            open_folder(out_dir)
            self.accept()

        try:
            if self.doc is not None:
                split_groups(key, self.doc.page_count, value)  # valida antes
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        run_task(self, "Separando...", work, on_done=done)


# ====================================================================== converter
class ConvertDialog(QDialog):
    opened = Signal(str)

    def __init__(self, parent=None, files=(), to_pdf=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Converter arquivos")
        self.resize(720, 500)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.list = FileList(files, conv.TO_PDF_EXTS)
        row.addWidget(self.list, 1)
        row.addLayout(file_buttons(self, self.list, ALL_SUPPORTED + ";;Todos (*.*)"))
        lay.addLayout(row)
        g = QGroupBox("Converter para")
        gl = QFormLayout(g)
        self.target = QComboBox()
        self.target.addItem("PDF (de Word, Excel, PowerPoint, imagens, texto, EPUB...)", "pdf")
        for key, (desc, _ext) in conv.FROM_PDF.items():
            self.target.addItem(f"{desc}  — a partir de PDF", key)
        if to_pdf is False:
            self.target.setCurrentIndex(1)
        elif to_pdf is None and files and all(f.lower().endswith(".pdf") for f in files):
            self.target.setCurrentIndex(1)
        gl.addRow("Formato:", self.target)
        self.dpi = QSpinBox(minimum=50, maximum=600, value=150, suffix=" dpi")
        gl.addRow("Resolução (imagens):", self.dpi)
        self.out_dir = QLineEdit(str(Path(files[0]).parent) if files else str(Path.home()))
        b = QPushButton("...")
        b.clicked.connect(lambda: self.out_dir.setText(
            QFileDialog.getExistingDirectory(self, "Pasta de saída", self.out_dir.text()) or self.out_dir.text()))
        h = QHBoxLayout()
        h.addWidget(self.out_dir, 1)
        h.addWidget(b)
        gl.addRow("Salvar em:", h)
        engine = conv.office_available()
        gl.addRow(QLabel(f"<small>Documentos do Office: "
                         f"{'usando ' + engine if engine else 'instale o LibreOffice (gratuito) para conversão fiel; sem ele é usada uma conversão simplificada'}"
                         f".</small>"))
        self.merge_after = QCheckBox("Unir todos os PDFs gerados em um único arquivo")
        gl.addRow(self.merge_after)
        lay.addWidget(g)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.addButton("Converter", QDialogButtonBox.AcceptRole).setDefault(True)
        bb.accepted.connect(self._convert)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _convert(self):
        files = self.list.files()
        if not files:
            QMessageBox.warning(self, APP_NAME, "Adicione arquivos para converter.")
            return
        target = self.target.currentData()
        out_dir = self.out_dir.text()
        dpi = self.dpi.value()
        merge = self.merge_after.isChecked() and target == "pdf"

        def work(progress=None):
            os.makedirs(out_dir, exist_ok=True)
            produced, errors = [], []
            for n, f in enumerate(files):
                stem = Path(f).stem
                try:
                    if target == "pdf":
                        out = os.path.join(out_dir, stem + ".pdf")
                        if os.path.abspath(out) == os.path.abspath(f):
                            continue
                        produced.append(conv.to_pdf(f, out))
                    else:
                        src = f
                        if not f.lower().endswith(".pdf"):
                            src = os.path.join(tempfile.mkdtemp(), stem + ".pdf")
                            conv.to_pdf(f, src)
                        ext = conv.FROM_PDF[target][1]
                        suffix = "_otimizado" if target == "pdfa" else ""
                        out = os.path.join(out_dir, stem + suffix + ext)
                        produced += conv.from_pdf(src, target, out, dpi=dpi)
                except Exception as e:
                    errors.append(f"{Path(f).name}: {e}")
                if progress:
                    progress(n + 1, len(files))
            if merge and len(produced) > 1:
                out = os.path.join(out_dir, "convertidos_unidos.pdf")
                merge_files(produced, out)
                produced.append(out)
            return produced, errors

        def done(res):
            produced, errors = res
            msg = f"{len(produced)} arquivo(s) gerado(s) em:\n{out_dir}"
            if errors:
                msg += "\n\nErros:\n" + "\n".join(errors)
                QMessageBox.warning(self, APP_NAME, msg)
            else:
                QMessageBox.information(self, APP_NAME, msg)
            if produced:
                open_folder(produced[-1])

        run_task(self, "Convertendo...", work, on_done=done, with_progress=True)


# ====================================================================== sobre
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        from .config import is_portable, log_path, resource_path
        super().__init__(parent)
        self.setWindowTitle(f"Sobre o {APP_NAME}")
        self.setFixedWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(resource_path("logo.png")).scaled(
            112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        title = QLabel(f"<div style='font-size:18pt;font-weight:700'>{APP_NAME}</div>"
                       f"<div style='color:{tc('muted')}'>Versão {__version__}"
                       f"{' • edição portátil' if is_portable() else ''}</div>")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        ai = QLabel(f"<div style='font-size:11.5pt;font-weight:700;color:{tc('accent_text')}'>"
                    "🤖 Desenvolvido integralmente com Inteligência Artificial</div>"
                    "<div style='margin-top:4px'>Todo o código, o design e o ícone deste programa "
                    "foram criados por IA, a partir das ideias e orientações do autor.</div>")
        ai.setWordWrap(True)
        ai.setAlignment(Qt.AlignCenter)
        ai.setObjectName("AiBox")
        lay.addWidget(ai)

        free = QLabel(f"<div style='font-size:11.5pt;font-weight:700;color:{tc('ok')}'>"
                      "💚 Gratuito — hoje e sempre</div>"
                      "<div style='margin-top:4px'>Sem anúncios, sem assinatura, sem marca-d'água e sem "
                      "limite de uso. Este software é e <b>sempre será gratuito</b>.</div>")
        free.setWordWrap(True)
        free.setAlignment(Qt.AlignCenter)
        free.setObjectName("FreeBox")
        lay.addWidget(free)

        details = QLabel(
            "Visualizador, editor e conversor de PDF para Windows.<br>"
            f"{len(catalog.fonts)} fontes do sistema disponíveis para edição.<br>"
            f"<small style='color:{tc('muted')}'>Software livre (licença AGPL-3.0) • Qt/PySide6 • PyMuPDF<br>"
            f"Registro de erros: {log_path()}</small>")
        details.setWordWrap(True)
        details.setAlignment(Qt.AlignCenter)
        details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(details)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


def about(parent):
    AboutDialog(parent).exec()
