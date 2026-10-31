"""Janela principal do Vorticis PDF Editor."""
from __future__ import annotations

import os
from pathlib import Path

import pymupdf
from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QSlider, QSpinBox, QSplitter, QToolBar, QVBoxLayout, QWidget,
)

from . import APP_NAME
from . import converters as conv
from . import shell_integration as shell
from . import viewer as V
from .config import now_str, resource_path
from .dialogs import (
    ALL_SUPPORTED, PDF_FILTER, ConvertDialog, HistoryDialog, PagePreviewDialog,
    PropertiesDialog, SaveInfoDialog, SplitDialog, TextDialog, about, run_task,
)
from .document import PdfDocument, split_document
from .printing import print_document
from .thumbnails import ThumbList

MAX_RECENT = 12


class MainWindow(QMainWindow):
    def __init__(self, controller, pdoc: PdfDocument | None = None):
        super().__init__()
        self.ctrl = controller
        self.pdoc: PdfDocument | None = None
        self.save_password: str | None = None
        self.search_index = 0
        self.settings = QSettings("Vorticis", "PDFEditor")
        self.setWindowIcon(QIcon(resource_path("icon.ico")))
        self.setAcceptDrops(True)
        self.resize(1320, 880)

        self.view = V.PdfView()
        self.thumbs = ThumbList()
        self._build_thumb_panel()
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.thumb_panel)
        self.splitter.addWidget(self.view)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([230, 1090])
        self.setCentralWidget(self.splitter)

        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_status()
        self._connect()
        self.set_document(pdoc)
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)

    # ================================================================== construção da UI
    def _build_thumb_panel(self):
        self.thumb_panel = QWidget()
        lay = QVBoxLayout(self.thumb_panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget()
        bar.setStyleSheet("background:#24272b;color:#ddd")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 4, 8, 4)
        self.thumb_title = QLabel("Páginas")
        h.addWidget(self.thumb_title)
        h.addStretch()
        h.addWidget(QLabel("🔍"))
        self.thumb_slider = QSlider(Qt.Horizontal, minimum=70, maximum=420, value=self.thumbs.thumb)
        self.thumb_slider.setFixedWidth(110)
        self.thumb_slider.setToolTip("Tamanho das miniaturas (Ctrl + roda do mouse)")
        h.addWidget(self.thumb_slider)
        lay.addWidget(bar)
        lay.addWidget(self.thumbs, 1)

    def _act(self, text, slot, shortcut=None, icon=None, tip=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if icon:
            a.setIconText(icon + " " + text)
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        return a

    def _build_actions(self):
        A = self._act
        self.a_open = A("Abrir...", self.open_dialog, QKeySequence.Open, "📂", "Abrir PDF ou outro arquivo")
        self.a_save = A("Salvar", self.save, QKeySequence.Save, "💾", "Salvar alterações (Ctrl+S)")
        self.a_save_as = A("Salvar como...", self.save_as, QKeySequence.SaveAs, "💾")
        self.a_print = A("Imprimir...", lambda: self.print_pages(None), QKeySequence.Print, "🖨",
                         "Imprimir na ordem atual das páginas, com pré-visualização")
        self.a_props = A("Propriedades e fontes...", self.properties, "Ctrl+I", "ℹ")
        self.a_history = A("Histórico de salvamentos...", lambda: HistoryDialog(self).exec())
        self.a_close = A("Fechar", self.close, QKeySequence.Close)
        self.a_quit = A("Sair", self.ctrl.quit, QKeySequence.Quit)
        self.a_new_win = A("Nova janela", lambda: self.ctrl.new_window(), "Ctrl+N")

        self.a_undo = A("Desfazer", self.undo, QKeySequence.Undo, "↶")
        self.a_redo = A("Refazer", self.redo, QKeySequence.Redo, "↷")
        self.a_copy = A("Copiar texto selecionado", self.copy, QKeySequence.Copy)
        self.a_find = A("Localizar...", lambda: (self.search_box.setFocus(), self.search_box.selectAll()),
                        QKeySequence.Find)

        self.a_zoom_in = A("Aumentar zoom", self.view.zoom_in, QKeySequence.ZoomIn, "➕")
        self.a_zoom_out = A("Diminuir zoom", self.view.zoom_out, QKeySequence.ZoomOut, "➖")
        self.a_fit_w = A("Ajustar à largura", lambda: self.view.set_fit("width"), "Ctrl+2", "↔")
        self.a_fit_p = A("Página inteira", lambda: self.view.set_fit("page"), "Ctrl+0", "⛶")
        self.a_zoom100 = A("Tamanho real (100%)", lambda: self.view.set_zoom(1.0), "Ctrl+1")
        self.a_organize = A("Organizar páginas", self.toggle_organize, "F6", "▦",
                            "Modo organizar: miniaturas grandes, arraste para reordenar", checkable=True)
        self.a_thumbs = A("Painel de miniaturas", self.toggle_thumbs, "F4", checkable=True)
        self.a_thumbs.setChecked(True)

        self.a_rot_r = A("Girar à direita", lambda: self.page_action("rot_r"), "Ctrl+R", "↻")
        self.a_rot_l = A("Girar à esquerda", lambda: self.page_action("rot_l"), "Ctrl+Shift+R", "↺")
        self.a_del = A("Excluir páginas", lambda: self.page_action("delete"), None, "🗑")
        self.a_dup = A("Duplicar páginas", lambda: self.page_action("duplicate"), "Ctrl+D")
        self.a_blank = A("Inserir página em branco", lambda: self.page_action("blank"))
        self.a_ins = A("Inserir arquivo...", lambda: self.page_action("insert_file"), "Ctrl+Shift+I")
        self.a_extract = A("Extrair páginas selecionadas...", lambda: self.page_action("extract"), "Ctrl+E")
        self.a_split = A("Separar documento...", self.split_current, None, "✂")
        self.a_reverse = A("Inverter ordem de todas as páginas", self.reverse_all)

        self.a_merge = A("Unir PDFs...", lambda: self.ctrl.merge([]), "Ctrl+M", "⧉",
                         "Unir vários arquivos em um único PDF")
        self.a_split_files = A("Separar arquivos PDF...", lambda: self.ctrl.split([]))
        self.a_convert = A("Converter arquivos...", lambda: self.ctrl.convert([]), "Ctrl+Shift+C", "⇄",
                           "Converter Word, Excel, PowerPoint, imagens ↔ PDF")
        self.a_export = A("Exportar este PDF para...", self.export_current)
        self.a_shell_on = A("Adicionar ao menu do botão direito do Windows", self.shell_register)
        self.a_shell_off = A("Remover do menu do botão direito", self.shell_unregister)
        self.a_about = A("Sobre o Vorticis PDF Editor", lambda: about(self))

        # ferramentas (exclusivas)
        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for key, text, icon, sc, tip in (
            (V.SELECT, "Selecionar", "⌶", "S", "Selecionar e copiar texto (arraste)"),
            (V.PAN, "Mão", "✋", "H", "Arrastar a página"),
            (V.EDIT_TEXT, "Editar texto", "✎", "E", "Clique em um texto para editá-lo (fonte reconhecida automaticamente)"),
            (V.ADD_TEXT, "Adicionar texto", "T", "T", "Clique onde deseja inserir texto"),
            (V.HIGHLIGHT, "Destacar", "🖍", "M", "Arraste sobre o texto para destacar"),
            (V.RECT, "Retângulo", "▭", "R", "Desenhar um retângulo"),
            (V.WHITEOUT, "Apagar área", "⌫", "W", "Remove definitivamente o conteúdo da área"),
            (V.NOTE, "Nota", "🗨", "N", "Adicionar comentário"),
            (V.IMAGE, "Imagem", "🖼", "I", "Arraste a área e escolha a imagem"),
            (V.CROP, "Recortar", "⌗", "C", "Arraste a área visível da página"),
        ):
            a = A(text, lambda _c=False, k=key: self.set_tool(k), sc, icon, tip, checkable=True)
            self.tool_group.addAction(a)
            self.tool_actions[key] = a
        self.tool_actions[V.SELECT].setChecked(True)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&Arquivo")
        m.addActions([self.a_open, self.a_new_win])
        self.recent_menu = m.addMenu("Abrir recentes")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        m.addSeparator()
        m.addActions([self.a_save, self.a_save_as, self.a_export])
        m.addSeparator()
        m.addActions([self.a_print, self.a_props, self.a_history])
        m.addSeparator()
        m.addActions([self.a_close, self.a_quit])
        m = mb.addMenu("&Editar")
        m.addActions([self.a_undo, self.a_redo])
        m.addSeparator()
        m.addActions([self.a_copy, self.a_find])
        m.addSeparator()
        m.addActions(list(self.tool_actions.values()))
        m = mb.addMenu("E&xibir")
        m.addActions([self.a_zoom_in, self.a_zoom_out, self.a_zoom100, self.a_fit_w, self.a_fit_p])
        m.addSeparator()
        m.addActions([self.a_organize, self.a_thumbs])
        m = mb.addMenu("&Páginas")
        m.addActions([self.a_rot_r, self.a_rot_l, self.a_dup, self.a_blank, self.a_ins])
        m.addSeparator()
        m.addActions([self.a_extract, self.a_split, self.a_reverse, self.a_del])
        m = mb.addMenu("&Ferramentas")
        m.addActions([self.a_merge, self.a_split_files, self.a_convert])
        m.addSeparator()
        m.addActions([self.a_shell_on, self.a_shell_off])
        m = mb.addMenu("Aj&uda")
        m.addAction(self.a_about)

    def _build_toolbars(self):
        tb = QToolBar("Principal")
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tb)
        tb.addActions([self.a_open, self.a_save, self.a_print])
        tb.addSeparator()
        tb.addActions([self.a_undo, self.a_redo])
        tb.addSeparator()
        tb.addAction(self.a_zoom_out)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setFixedWidth(92)
        for z in (25, 50, 75, 100, 125, 150, 200, 300, 400):
            self.zoom_combo.addItem(f"{z}%")
        self.zoom_combo.addItems(["Largura", "Página"])
        tb.addWidget(self.zoom_combo)
        tb.addAction(self.a_zoom_in)
        tb.addAction(self.a_fit_w)
        tb.addAction(self.a_fit_p)
        tb.addSeparator()
        self.page_spin = QSpinBox(minimum=1, maximum=1)
        self.page_spin.setFixedWidth(70)
        self.page_spin.setKeyboardTracking(False)
        tb.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0 ")
        tb.addWidget(self.page_total)
        tb.addSeparator()
        tb.addActions([self.a_organize, self.a_rot_l, self.a_rot_r, self.a_merge, self.a_split,
                       self.a_convert])
        tb.addSeparator()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔎 Localizar (Enter = próximo)")
        self.search_box.setFixedWidth(220)
        self.search_box.setClearButtonEnabled(True)
        tb.addWidget(self.search_box)
        self.search_lbl = QLabel("")
        tb.addWidget(self.search_lbl)

        tools = QToolBar("Ferramentas de edição")
        tools.setObjectName("tools")
        tools.setMovable(False)
        tools.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBarBreak()
        self.addToolBar(tools)
        tools.addWidget(QLabel("  Ferramentas: "))
        tools.addActions(list(self.tool_actions.values()))
        self.setStyleSheet("""
            QToolBar{spacing:3px;padding:3px;background:#f4f5f7;border-bottom:1px solid #ddd}
            QToolButton{padding:4px 7px;border-radius:5px}
            QToolButton:hover{background:#e3e6ea}
            QToolButton:checked{background:#d6232d;color:white}
            QStatusBar{background:#f4f5f7}""")

    def _build_status(self):
        sb = self.statusBar()
        self.st_page = QLabel()
        self.st_zoom = QLabel()
        self.st_saved = QLabel()
        self.st_saved.setStyleSheet("color:#1b8a3a")
        sb.addWidget(self.st_page)
        sb.addWidget(self.st_zoom)
        sb.addPermanentWidget(self.st_saved)

    def _connect(self):
        self.view.zoomChanged.connect(self._on_zoom)
        self.view.pageChanged.connect(self._on_page)
        self.view.editTextRequested.connect(self.edit_text)
        self.view.addTextRequested.connect(self.add_text)
        self.view.noteRequested.connect(self.add_note)
        self.view.areaSelected.connect(self.area_tool)
        self.thumbs.pageActivated.connect(lambda i: (self.view.set_current_page(i)) if not self.a_organize.isChecked() else None)
        self.thumbs.pagesMoved.connect(self.move_pages)
        self.thumbs.filesDropped.connect(self.insert_files_at)
        self.thumbs.action.connect(self.thumb_action)
        self.thumbs.itemDoubleClicked.connect(self._thumb_double)
        self.thumbs.thumbSizeChanged.connect(lambda v: (self.thumb_slider.blockSignals(True),
                                                        self.thumb_slider.setValue(v),
                                                        self.thumb_slider.blockSignals(False)))
        self.thumb_slider.valueChanged.connect(self.thumbs.set_thumb_size)
        self.page_spin.valueChanged.connect(lambda v: self.view.set_current_page(v - 1))
        self.zoom_combo.activated.connect(self._zoom_combo)
        self.zoom_combo.lineEdit().returnPressed.connect(self._zoom_combo)
        self.search_box.returnPressed.connect(self.search_next)
        self.search_box.textChanged.connect(lambda _t: setattr(self, "_search_dirty", True))
        self._search_dirty = True

    # ================================================================== documento
    def set_document(self, pdoc: PdfDocument | None):
        self.pdoc = pdoc
        doc = pdoc.doc if pdoc else None
        self.view.set_document(doc, keep_position=False)
        self.thumbs.set_document(doc, invalidate_all=True)
        has = pdoc is not None
        for a in (self.a_save, self.a_save_as, self.a_print, self.a_props, self.a_export,
                  self.a_rot_r, self.a_rot_l, self.a_del, self.a_dup, self.a_blank, self.a_ins,
                  self.a_extract, self.a_split, self.a_reverse, self.a_organize):
            a.setEnabled(has)
        self.st_saved.setText("")
        self._update_state()
        if pdoc and pdoc.path:
            self._add_recent(pdoc.path)

    def is_empty(self):
        return self.pdoc is None

    def load(self, path: str, organize=False):
        try:
            pdoc = PdfDocument(path)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível abrir:\n{path}\n\n{e}")
            return False
        if pdoc.doc.needs_pass:
            pw, ok = QInputDialog.getText(self, APP_NAME, f"Senha de '{Path(path).name}':",
                                          QLineEdit.Password)
            if not ok or not pdoc.doc.authenticate(pw):
                QMessageBox.warning(self, APP_NAME, "Senha incorreta.")
                return False
        if not pdoc.is_native_pdf():
            # arquivo convertido (imagem, XPS, EPUB...): salvar pede um novo nome .pdf
            pdoc.edits.append(f"Convertido de {Path(path).suffix.upper()[1:]} para PDF")
            pdoc.path = None
            pdoc.modified = True
            self._converted_name = str(Path(path).with_suffix(".pdf"))
        self.set_document(pdoc)
        if organize:
            self.a_organize.setChecked(True)
            self.toggle_organize()
        return True

    def refresh(self, structural=False, pages=None):
        doc = self.pdoc.doc
        if structural:
            self.view.set_document(doc)
            self.thumbs.set_document(doc)
        else:
            self.view.invalidate(pages)
            self.thumbs.invalidate(pages if pages is not None else range(doc.page_count))
        self._update_state()

    def _update_state(self):
        p = self.pdoc
        if p is None:
            self.setWindowTitle(APP_NAME)
            self.page_total.setText(" / 0 ")
            self.page_spin.setMaximum(1)
            self.st_page.setText("Abra um arquivo (Ctrl+O) ou arraste-o para a janela")
            self.a_undo.setEnabled(False)
            self.a_redo.setEnabled(False)
            return
        self.setWindowTitle(f"{'● ' if p.modified else ''}{p.title} — {APP_NAME}")
        self.page_spin.setMaximum(max(1, p.page_count))
        self.page_total.setText(f" / {p.page_count} ")
        self.thumb_title.setText(f"Páginas ({p.page_count})")
        self.a_undo.setEnabled(p.can_undo())
        self.a_redo.setEnabled(p.can_redo())
        self.a_undo.setToolTip("Desfazer: " + (p._undo[-1][1] if p._undo else ""))
        self._on_page(self.view.current)
        if p.modified:
            self.st_saved.setStyleSheet("color:#b26a00")
            self.st_saved.setText(f"● {len(p.edits)} alteração(ões) não salva(s)")

    def _on_zoom(self, z):
        self.st_zoom.setText(f"Zoom: {z * 100:.0f}%")
        self.zoom_combo.setEditText(f"{z * 100:.0f}%")

    def _on_page(self, i):
        if not self.pdoc:
            return
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(i + 1)
        self.page_spin.blockSignals(False)
        page = self.pdoc.doc[min(i, self.pdoc.page_count - 1)]
        w, h = page.rect.width * 25.4 / 72, page.rect.height * 25.4 / 72
        self.st_page.setText(f"Página {i + 1} de {self.pdoc.page_count}   •   {w:.0f} × {h:.0f} mm")
        if not self.a_organize.isChecked() and 0 <= i < self.thumbs.count():
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(i)
            self.thumbs.scrollToItem(self.thumbs.item(i))
            self.thumbs.blockSignals(False)

    def _zoom_combo(self, *_):
        t = self.zoom_combo.currentText().strip().replace("%", "")
        if t.lower().startswith("larg"):
            self.view.set_fit("width")
        elif t.lower().startswith("pág") or t.lower().startswith("pag"):
            self.view.set_fit("page")
        else:
            try:
                self.view.set_zoom(float(t.replace(",", ".")) / 100)
            except ValueError:
                pass

    # ================================================================== arquivos
    def open_dialog(self):
        last = self.settings.value("last_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, "Abrir", last,
                                                PDF_FILTER + ";;" + ALL_SUPPORTED + ";;Todos (*.*)")
        if files:
            self.settings.setValue("last_dir", str(Path(files[0]).parent))
            self.ctrl.open_files(files, self)

    def maybe_save(self) -> bool:
        if not self.pdoc or not self.pdoc.modified:
            return True
        r = QMessageBox.question(
            self, APP_NAME, f"Salvar as alterações em '{self.pdoc.title}'?\n\n"
            + "\n".join("• " + e for e in self.pdoc.edits[-8:]),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def save(self) -> bool:
        if not self.pdoc:
            return False
        if not self.pdoc.path:
            return self.save_as()
        return self._do_save(self.pdoc.path)

    def save_as(self) -> bool:
        if not self.pdoc:
            return False
        suggestion = self.pdoc.path or getattr(self, "_converted_name", "") or \
            str(Path(self.settings.value("last_dir", str(Path.home()))) / "documento.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Salvar como", suggestion, PDF_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        return self._do_save(path)

    def _do_save(self, path) -> bool:
        try:
            info = self.pdoc.save(path, self.save_password)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Erro ao salvar:\n{e}")
            return False
        self._add_recent(path)
        self.st_saved.setStyleSheet("color:#1b8a3a")
        self.st_saved.setText(f"✔ Salvo às {now_str()[-8:]} — {info['tamanho_atual']} — {path}")
        self._update_state()
        if self.settings.value("show_save_info", True, type=bool):
            SaveInfoDialog(self, info).exec()
        return True

    def export_current(self):
        if not self.pdoc:
            return
        if self.pdoc.modified or not self.pdoc.path:
            QMessageBox.information(self, APP_NAME, "Salve o documento antes de exportar.")
            if not self.save():
                return
        ConvertDialog(self, [self.pdoc.path], to_pdf=False).exec()

    def _add_recent(self, path):
        rec = [p for p in (self.settings.value("recent", []) or []) if p != path]
        rec.insert(0, path)
        self.settings.setValue("recent", rec[:MAX_RECENT])

    def _fill_recent(self):
        self.recent_menu.clear()
        rec = self.settings.value("recent", []) or []
        if isinstance(rec, str):
            rec = [rec]
        for p in rec:
            if os.path.exists(p):
                self.recent_menu.addAction(p, lambda p=p: self.ctrl.open_files([p], self))
        if not self.recent_menu.actions():
            self.recent_menu.addAction("(vazio)").setEnabled(False)

    def properties(self):
        dlg = PropertiesDialog(self, self.pdoc)
        if dlg.exec():
            meta = dlg.metadata()
            old = self.pdoc.doc.metadata or {}
            if any((old.get(k) or "") != v for k, v in meta.items()):
                self.pdoc.set_metadata(meta)
            pw = dlg.password.text()
            if pw:
                self.save_password = pw
                self.pdoc.edits.append("Proteção por senha (AES-256)")
                self.pdoc.modified = True
            self._update_state()

    def print_pages(self, rows):
        if not self.pdoc:
            return
        print_document(self, self.pdoc.doc, rows)

    # ================================================================== editar
    def undo(self):
        if self.pdoc and (d := self.pdoc.undo()):
            self.refresh(structural=True)
            self.thumbs.set_document(self.pdoc.doc, invalidate_all=True)
            self.statusBar().showMessage(f"Desfeito: {d}", 3000)

    def redo(self):
        if self.pdoc and (d := self.pdoc.redo()):
            self.refresh(structural=True)
            self.thumbs.set_document(self.pdoc.doc, invalidate_all=True)
            self.statusBar().showMessage(f"Refeito: {d}", 3000)

    def copy(self):
        if self.view.copy_selection():
            self.statusBar().showMessage("Texto copiado", 2000)

    def set_tool(self, key):
        self.tool_actions[key].setChecked(True)
        self.view.set_tool(key)
        if self.a_organize.isChecked() and key != V.SELECT:
            self.a_organize.setChecked(False)
            self.toggle_organize()

    def edit_text(self, page_no, span):
        dlg = TextDialog(self, self.pdoc.doc, page_no, span)
        if not dlg.exec():
            return
        text, font, size, color = dlg.values()
        try:
            self.pdoc.replace_text(page_no, span["bbox"], span["origin"], text, font, size, color,
                                   span.get("dir", (1, 0)))
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível editar o texto:\n{e}")
            return
        self.refresh(pages=[page_no])
        self.statusBar().showMessage(f"Texto editado com a fonte: {font.label}", 4000)

    def add_text(self, page_no, pt):
        dlg = TextDialog(self, self.pdoc.doc, page_no, None)
        if dlg.exec():
            text, font, size, color = dlg.values()
            if text.strip():
                self.pdoc.add_text(page_no, (pt[0], pt[1] + size * 0.8), text, font, size, color)
                self.refresh(pages=[page_no])

    def add_note(self, page_no, pt):
        text, ok = QInputDialog.getMultiLineText(self, "Nota", "Comentário:")
        if ok and text.strip():
            self.pdoc.add_note(page_no, pymupdf.Point(pt), text)
            self.refresh(pages=[page_no])

    def area_tool(self, tool, page_no, rect):
        r = pymupdf.Rect(rect)
        if tool == V.HIGHLIGHT:
            self.pdoc.highlight(page_no, r)
        elif tool == V.RECT:
            self.pdoc.add_rect(page_no, r)
        elif tool == V.WHITEOUT:
            if QMessageBox.question(self, APP_NAME, "Apagar definitivamente o conteúdo desta área?") \
                    != QMessageBox.Yes:
                return
            self.pdoc.whiteout(page_no, r)
        elif tool == V.IMAGE:
            f, _ = QFileDialog.getOpenFileName(self, "Escolher imagem", "",
                                               "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)")
            if not f:
                return
            self.pdoc.add_image(page_no, r, f)
        elif tool == V.CROP:
            all_pages = QMessageBox.question(self, APP_NAME, "Aplicar o recorte em todas as páginas?",
                                             QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if all_pages == QMessageBox.Cancel:
                return
            rows = list(range(self.pdoc.page_count)) if all_pages == QMessageBox.Yes else [page_no]
            self.pdoc.crop(rows, r)
            self.refresh(structural=True)
            return
        self.refresh(pages=[page_no])

    # ================================================================== busca
    def search_next(self):
        if not self.pdoc:
            return
        if self._search_dirty:
            n = self.view.search(self.search_box.text())
            self._search_dirty = False
            self.search_index = 0
            self.search_lbl.setText(f" {n} resultado(s) " if self.search_box.text() else "")
            if not n:
                return
        else:
            self.search_index += 1
        i = self.view.goto_hit(self.search_index)
        if i is not None:
            self.search_lbl.setText(f" {i + 1} de {len(self.view.search_hits)} ")

    # ================================================================== páginas
    def selected_or_current(self):
        rows = self.thumbs.selected_rows()
        return rows or [self.view.current]

    def page_action(self, name):
        self.thumb_action(name, self.selected_or_current())

    def move_pages(self, rows, target):
        new_rows = self.pdoc.move_pages(rows, target)
        if new_rows is not None:
            self.refresh(structural=True)
            self.thumbs.select_rows(new_rows)

    def thumb_action(self, name, rows):
        if not self.pdoc:
            return
        n = self.pdoc.page_count
        if name == "preview":
            PagePreviewDialog(self, self.pdoc.doc, rows[0]).exec()
            return
        if name in ("rot_r", "rot_l", "rot_180"):
            self.pdoc.rotate(rows, {"rot_r": 90, "rot_l": -90, "rot_180": 180}[name])
            self.refresh(structural=True)
            self.thumbs.select_rows(rows)
        elif name == "move_first":
            self.move_pages(rows, 0)
        elif name == "move_last":
            self.move_pages(rows, n)
        elif name == "duplicate":
            self.pdoc.duplicate(rows)
            self.refresh(structural=True)
        elif name == "blank":
            at = (rows[-1] + 1) if rows else n
            self.pdoc.insert_blank(at)
            self.refresh(structural=True)
            self.thumbs.select_rows([at])
        elif name == "insert_file":
            files, _ = QFileDialog.getOpenFileNames(self, "Inserir arquivo(s)", "", ALL_SUPPORTED)
            if files:
                self.insert_files_at(files, (rows[-1] + 1) if rows else n)
        elif name == "extract":
            self.extract_pages(rows)
        elif name == "split_here":
            self.split_at(rows[0])
        elif name == "print_sel":
            self.print_pages(rows)
        elif name == "reverse":
            order = list(range(n))
            rev = list(reversed(rows))
            for r, src in zip(rows, rev):
                order[r] = src
            self.pdoc.set_order(order, f"Inverteu a ordem de {len(rows)} página(s)")
            self.refresh(structural=True)
        elif name == "select_all":
            self.thumbs.selectAll()
        elif name in ("select_odd", "select_even"):
            start = 0 if name == "select_odd" else 1
            self.thumbs.select_rows(list(range(start, n, 2)))
        elif name == "delete":
            if len(rows) >= n:
                QMessageBox.warning(self, APP_NAME, "Não é possível excluir todas as páginas.")
                return
            if QMessageBox.question(self, APP_NAME, f"Excluir {len(rows)} página(s)?") != QMessageBox.Yes:
                return
            self.pdoc.delete(rows)
            self.refresh(structural=True)

    def reverse_all(self):
        self.pdoc.set_order(list(reversed(range(self.pdoc.page_count))), "Inverteu a ordem das páginas")
        self.refresh(structural=True)

    def insert_files_at(self, files, at):
        ok = [f for f in files if Path(f).suffix.lower() in conv.TO_PDF_EXTS]
        if not ok:
            return
        if not self.pdoc:
            self.ctrl.open_files(ok, self)
            return

        def work():
            out = []
            for f in ok:
                if Path(f).suffix.lower() in conv.OFFICE_TO_PDF:
                    import tempfile
                    tmp = os.path.join(tempfile.mkdtemp(), Path(f).stem + ".pdf")
                    conv.to_pdf(f, tmp)
                    out.append(tmp)
                else:
                    out.append(f)
            return out

        def done(paths):
            pos = at
            for p in paths:
                before = self.pdoc.page_count
                self.pdoc.insert_file(p, pos)
                pos += self.pdoc.page_count - before
            self.refresh(structural=True)
            self.thumbs.select_rows(list(range(at, pos)))

        run_task(self, "Preparando arquivos...", work, on_done=done)

    def extract_pages(self, rows):
        base = Path(self.pdoc.path or "documento.pdf")
        label = f"{rows[0] + 1}" if len(rows) == 1 else f"{rows[0] + 1}-{rows[-1] + 1}"
        path, _ = QFileDialog.getSaveFileName(self, "Extrair páginas",
                                              str(base.with_name(f"{base.stem}_pag{label}.pdf")), PDF_FILTER)
        if not path:
            return
        out = PdfDocument(doc=self.pdoc.extract(rows))
        out.edits = [f"Extraiu {len(rows)} página(s) de {self.pdoc.title}"]
        SaveInfoDialog(self, out.save(path), "Páginas extraídas").exec()

    def split_at(self, row):
        if row == 0:
            QMessageBox.information(self, APP_NAME, "Escolha uma página depois da primeira.")
            return
        base = Path(self.pdoc.path or "documento.pdf")
        d = QFileDialog.getExistingDirectory(self, "Pasta para salvar as duas partes", str(base.parent))
        if not d:
            return
        n = self.pdoc.page_count
        files = split_document(self.pdoc.doc, [list(range(row)), list(range(row, n))], d, base.stem)
        QMessageBox.information(self, APP_NAME, "Criados:\n" + "\n".join(files))

    def split_current(self):
        if not self.pdoc:
            return
        dlg = SplitDialog(self, doc=self.pdoc.doc, name=Path(self.pdoc.title).stem)
        if self.pdoc.path:
            dlg.out_dir.setText(str(Path(self.pdoc.path).parent))
        dlg.exec()

    # ================================================================== modos de exibição
    def toggle_organize(self):
        on = self.a_organize.isChecked()
        self.view.setVisible(not on)
        self.thumb_panel.setVisible(True)
        self.a_thumbs.setChecked(True)
        if on:
            self._saved_sizes = self.splitter.sizes()
            self._saved_thumb = self.thumbs.thumb
            self.thumbs.set_thumb_size(max(200, self.thumbs.thumb))
            self.thumb_title.setText(f"Organizar — arraste para reordenar, botão direito para opções "
                                     f"({self.pdoc.page_count if self.pdoc else 0} páginas)")
        else:
            self.thumbs.set_thumb_size(getattr(self, "_saved_thumb", 130))
            if getattr(self, "_saved_sizes", None):
                self.splitter.setSizes(self._saved_sizes)
            if self.view.fit_mode:
                QTimer.singleShot(0, lambda: self.view.set_fit(self.view.fit_mode))
            self._update_state()

    def toggle_thumbs(self):
        self.thumb_panel.setVisible(self.a_thumbs.isChecked() or self.a_organize.isChecked())

    def _thumb_double(self, item):
        if self.a_organize.isChecked():
            PagePreviewDialog(self, self.pdoc.doc, self.thumbs.row(item)).exec()

    # ================================================================== integração Windows
    def shell_register(self):
        try:
            QMessageBox.information(self, APP_NAME, shell.register())
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, str(e))

    def shell_unregister(self):
        try:
            QMessageBox.information(self, APP_NAME, shell.unregister())
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, str(e))

    # ================================================================== eventos
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        files = [f for f in files if Path(f).suffix.lower() in conv.TO_PDF_EXTS]
        if not files:
            return
        if self.pdoc is None:
            self.ctrl.open_files(files, self)
            return
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText(f"{len(files)} arquivo(s) solto(s). O que deseja fazer?")
        b_ins = box.addButton("Inserir no fim deste documento", QMessageBox.AcceptRole)
        b_open = box.addButton("Abrir em nova janela", QMessageBox.ActionRole)
        b_merge = box.addButton("Unir...", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        if box.clickedButton() is b_ins:
            self.insert_files_at(files, self.pdoc.page_count)
        elif box.clickedButton() is b_open:
            self.ctrl.open_files(files, None)
        elif box.clickedButton() is b_merge:
            self.ctrl.merge(([self.pdoc.path] if self.pdoc.path else []) + files)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.set_tool(V.SELECT)
        elif e.key() in (Qt.Key_PageDown,) and self.pdoc:
            self.view.set_current_page(min(self.view.current + 1, self.pdoc.page_count - 1))
        elif e.key() in (Qt.Key_PageUp,) and self.pdoc:
            self.view.set_current_page(max(self.view.current - 1, 0))
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        if not self.maybe_save():
            e.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.ctrl.window_closed(self)
        e.accept()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, lambda: self.view.set_fit(self.view.fit_mode) if self.view.fit_mode else None)
