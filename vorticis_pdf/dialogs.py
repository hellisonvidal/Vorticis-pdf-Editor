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
    QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog, QComboBox,
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QRadioButton, QScrollArea,
    QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from . import converters as conv
from .config import human_size, read_history
from .document import merge_files, split_document, split_groups
from .fonts import catalog, strip_subset
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




# ====================================================================== histórico de salvamentos
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


def _status(win, text) -> bool:
    """Mostra o resultado na barra de status da janela principal, sem janela de mensagem.
    Devolve False quando não há janela principal (ação aberta pelo botão direito do Explorer)."""
    if win is None or not hasattr(win, "statusBar"):
        return False
    if text:
        win.statusBar().showMessage(text, 10000)
    return True


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
        go = bb.addButton("Unir", QDialogButtonBox.AcceptRole)
        go.setDefault(True)
        bb.accepted.connect(self._merge)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _merge(self):
        files = self.list.files()
        if len(files) < 1:
            QMessageBox.warning(self, APP_NAME, "Adicione pelo menos um arquivo.")
            return
        from .config import unique_path
        first = Path(files[0])
        # salva direto ao lado do primeiro arquivo, sem perguntar (nunca sobrescreve outro arquivo)
        out = unique_path(first.with_name(first.stem + "_unido.pdf"))

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
            _status(self.parent(), f"✔ {len(files)} arquivo(s) unidos em {out}")
            if self.open_after.isChecked():
                self.opened.emit(out)
            elif not _status(self.parent(), None):
                open_folder(out)
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
            if not _status(self.parent(), f"✔ {len(written)} arquivo(s) criado(s) em {out_dir}"):
                open_folder(written[0] if written else out_dir)  # aberto pelo Explorer: mostra a pasta
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
            if errors:  # só avisa quando algo deu errado
                QMessageBox.warning(self, APP_NAME, f"{len(produced)} arquivo(s) gerado(s) em:\n{out_dir}"
                                    "\n\nErros:\n" + "\n".join(errors))
            if produced and not _status(self.parent(), f"✔ {len(produced)} arquivo(s) gerado(s) em {out_dir}"):
                open_folder(produced[-1])
            if produced and not errors:
                self.accept()

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
