"""Janela principal do Vorticis PDF Editor."""
from __future__ import annotations

import os
from pathlib import Path

import pymupdf
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSizePolicy, QSlider,
    QSpinBox, QSplitter, QStackedWidget, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from . import APP_NAME
from . import converters as conv
from . import shell_integration as shell
from . import viewer as V
from .config import log_path, now_str, resource_path, settings
from .dialogs import (
    ALL_SUPPORTED, PDF_FILTER, ConvertDialog, HistoryDialog, PagePreviewDialog,
    PropertiesDialog, SplitDialog, about, open_folder,
)
from . import ocr
from . import signature as sig
from . import translate as tr
from .document import PdfDocument, split_document
from .features import OcrDialog, SignDialog, TextResultDialog, TranslateDialog, VerifyDialog
from .fonts import catalog, strip_subset
from .icons import icon, on_retheme
from .theme import c, is_dark
from .printing import print_document
from .tasks import run_task
from .thumbnails import ThumbList

MAX_RECENT = 12


def _sep():
    w = QWidget()
    w.setObjectName("Sep")
    w.setFixedWidth(1)
    w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    return w


class MainWindow(QMainWindow):
    def __init__(self, controller, pdoc: PdfDocument | None = None):
        super().__init__()
        self.ctrl = controller
        self.pdoc: PdfDocument | None = None
        self.save_password: str | None = None
        self.search_index = 0
        self.settings = settings()
        from .config import app_icon
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.resize(1360, 900)

        self.view = V.PdfView()
        self.thumbs = ThumbList()
        self._build_thumb_panel()
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.addWidget(self.thumb_panel)
        self.splitter.addWidget(self.view)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([240, 1100])

        self.stack = QStackedWidget()
        self.welcome = self._build_welcome()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.splitter)
        self.setCentralWidget(self.stack)

        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_status()
        self._connect()
        self._retheme()
        on_retheme(self._retheme)
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
        bar.setObjectName("ThumbHeader")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 8, 12, 8)
        self.thumb_title = QLabel("Páginas")
        h.addWidget(self.thumb_title)
        h.addStretch()
        self._thumb_zoom_lbl = QLabel()
        h.addWidget(self._thumb_zoom_lbl)
        self.thumb_slider = QSlider(Qt.Horizontal, minimum=70, maximum=420, value=self.thumbs.thumb)
        self.thumb_slider.setFixedWidth(100)
        self.thumb_slider.setToolTip("Tamanho das miniaturas (Ctrl + roda do mouse)")
        h.addWidget(self.thumb_slider)
        lay.addWidget(bar)
        lay.addWidget(self.thumbs, 1)

    def _build_welcome(self):
        page = QWidget()
        page.setObjectName("Welcome")
        page.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(page)
        outer.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        card = QWidget()
        card.setObjectName("WelcomeCard")
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setMaximumWidth(860)
        cl = QGridLayout(card)
        cl.setContentsMargins(36, 32, 36, 32)
        cl.setHorizontalSpacing(28)
        cl.setVerticalSpacing(10)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(resource_path("logo.png")).scaled(72, 72, Qt.KeepAspectRatio,
                                                                  Qt.SmoothTransformation))
        head.addWidget(logo)
        tl = QVBoxLayout()
        t = QLabel(APP_NAME)
        t.setObjectName("WelcomeTitle")
        s = QLabel("Visualize, edite, organize e converta PDFs — gratuito, sempre.")
        s.setObjectName("WelcomeSub")
        tl.addWidget(t)
        tl.addWidget(s)
        head.addLayout(tl)
        head.addStretch()
        cl.addLayout(head, 0, 0, 1, 2)

        actions = QVBoxLayout()
        actions.setSpacing(8)
        for ic, text, sub, fn in (
            ("open", "Abrir PDF", "ou arraste um arquivo para esta janela", self.open_dialog),
            ("new_file", "Novo PDF", "crie um documento do zero", self.new_pdf),
            ("merge", "Unir PDFs", "junte vários arquivos em um só", lambda: self.ctrl.merge([])),
            ("split", "Separar PDF", "por páginas, intervalos ou a cada N", lambda: self.ctrl.split([])),
            ("organize", "Organizar páginas", "reordene, gire e exclua visualmente", self._organize_from_welcome),
            ("convert", "Converter arquivos", "Word, Excel, PowerPoint, imagens ↔ PDF", lambda: self.ctrl.convert([])),
        ):
            b = QPushButton(f"  {text}\n  {sub}")
            b.setProperty("vicon", ic)
            b.setObjectName("BigAction")
            b.setIconSize(QSize(26, 26))
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(330)
            b.clicked.connect(fn)
            actions.addWidget(b)
        actions.addStretch()
        cl.addLayout(actions, 1, 0)

        rl = QVBoxLayout()
        rt = QLabel("<b>Recentes</b>")
        rl.addWidget(rt)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("RecentList")
        self.recent_list.setMinimumWidth(360)
        self.recent_list.itemActivated.connect(self._open_recent_item)
        self.recent_list.itemClicked.connect(self._open_recent_item)
        rl.addWidget(self.recent_list, 1)
        badge = QLabel("🤖 Feito integralmente com IA  •  💚 Sempre gratuito")
        badge.setObjectName("Badge")
        badge.setAlignment(Qt.AlignCenter)
        rl.addWidget(badge)
        cl.addLayout(rl, 1, 1)
        row.addWidget(card, 1)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()
        return page

    def _retheme(self):
        """Reaplica ícones e cores ao trocar entre tema claro e escuro."""
        for a in self.findChildren(QAction):
            name = a.property("vicon")
            if name:
                a.setIcon(icon(name))
        for b in self.findChildren(QPushButton):
            name = b.property("vicon")
            if name:
                b.setIcon(icon(name, c("accent")))
                b.setIconSize(QSize(26, 26))
        for b in self.findChildren(QToolButton):
            name = b.property("vicon_btn")
            if name:
                b.setIcon(icon(name))
        if hasattr(self, "sel_edit_btn"):
            self.sel_edit_btn.setIcon(icon("edit_text", "#ffffff"))
        if hasattr(self, "merge_btn"):
            self.merge_btn.setIcon(icon("merge", "#ffffff"))
        if hasattr(self, "_search_icon"):
            self._search_icon.setIcon(icon("search", c("muted")))
        self._thumb_zoom_lbl.setPixmap(icon("zoom_in", "#aeb4bd").pixmap(16, 16))
        if hasattr(self, "a_theme"):
            self.a_theme.setIcon(icon("sun" if is_dark() else "moon"))
        if hasattr(self, "st_saved") and self.st_saved.text():
            self._set_saved_badge(self.st_saved.text(), self.st_saved.objectName() == "DirtyBadge")
        if self.pdoc is None and hasattr(self, "recent_list"):
            self._fill_recent_list()
        self.view.apply_theme()
        self.thumbs.apply_theme()

    def set_theme(self, mode):
        from PySide6.QtWidgets import QApplication
        from . import theme
        theme.apply(QApplication.instance(), mode)
        for key, a in self.theme_actions.items():
            a.setChecked(key == mode)

    def toggle_theme(self):
        self.set_theme("light" if is_dark() else "dark")

    def _fill_recent_list(self):
        self.recent_list.clear()
        rec = self.settings.value("recent", []) or []
        if isinstance(rec, str):
            rec = [rec]
        for p in rec:
            if os.path.isfile(p):
                parent = str(Path(p).parent)
                if len(parent) > 48:
                    parent = "…" + parent[-47:]
                it = QListWidgetItem(icon("pages", c("muted")), f"{Path(p).name}\n{parent}")
                it.setData(Qt.UserRole, p)
                it.setToolTip(p)
                self.recent_list.addItem(it)
        if not self.recent_list.count():
            it = QListWidgetItem("Nenhum arquivo aberto recentemente")
            it.setFlags(Qt.NoItemFlags)
            self.recent_list.addItem(it)

    def _open_recent_item(self, item):
        path = item.data(Qt.UserRole) if item is not None else None
        if path:  # o item "Nenhum arquivo..." não tem caminho
            self.ctrl.open_files([path], self)

    def _organize_from_welcome(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Escolha os arquivos para organizar", "",
                                                PDF_FILTER + ";;" + ALL_SUPPORTED)
        if files:
            self.ctrl.organize(files)

    def _act(self, text, slot, shortcut=None, ic=None, tip=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if ic:
            a.setIcon(icon(ic))
            a.setProperty("vicon", ic)
        sc = a.shortcut().toString(QKeySequence.NativeText)
        a.setToolTip(f"<b>{text.rstrip('.')}</b>" + (f"  <span style='color:#aab'>({sc})</span>" if sc else "")
                     + (f"<br>{tip}" if tip else ""))
        if tip:
            a.setStatusTip(tip)
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        return a

    def _build_actions(self):
        A = self._act
        self.a_open = A("Abrir...", self.open_dialog, QKeySequence.Open, "open", "Abrir PDF ou outro arquivo")
        self.a_save = A("Salvar", self.save, QKeySequence.Save, "save", "Salvar as alterações")
        self.a_save_as = A("Salvar como...", self.save_as, QKeySequence.SaveAs, "save_as")
        self.a_print = A("Imprimir...", lambda: self.print_pages(None), QKeySequence.Print, "print",
                         "Imprimir na ordem atual das páginas (impressora, cópias, papel, orientação, páginas por folha...)")
        self.a_props = A("Propriedades e fontes...", self.properties, "Ctrl+I", "info",
                         "Metadados, fontes do documento e senha")
        self.a_history = A("Histórico de salvamentos...", lambda: HistoryDialog(self).exec(), None, "history")
        self.a_close = A("Fechar", self.close, QKeySequence.Close)
        self.a_quit = A("Sair", self.ctrl.quit, QKeySequence.Quit)
        self.a_new_win = A("Nova janela", lambda: self.ctrl.new_window(), "Ctrl+Shift+N")
        self.a_new_pdf = A("Novo PDF...", self.new_pdf, "Ctrl+N", "new_file",
                           "Criar um PDF do zero (em branco, pautado, quadriculado...)")

        self.a_undo = A("Desfazer", self.undo, QKeySequence.Undo, "undo")
        self.a_redo = A("Refazer", self.redo, QKeySequence.Redo, "redo")
        self.a_copy = A("Copiar texto selecionado", self.copy, QKeySequence.Copy)
        self.a_find = A("Localizar...", lambda: (self.search_box.setFocus(), self.search_box.selectAll()),
                        QKeySequence.Find, "search")

        self.a_zoom_in = A("Aumentar zoom", self.view.zoom_in, QKeySequence.ZoomIn, "zoom_in")
        self.a_zoom_out = A("Diminuir zoom", self.view.zoom_out, QKeySequence.ZoomOut, "zoom_out")
        self.a_fit_w = A("Ajustar à largura", lambda: self.view.set_fit("width"), "Ctrl+2", "fit_width")
        self.a_fit_p = A("Página inteira", lambda: self.view.set_fit("page"), "Ctrl+0", "fit_page")
        self.a_zoom100 = A("Tamanho real (100%)", lambda: self.view.set_zoom(1.0), "Ctrl+1")
        self.a_organize = A("Organizar páginas", self.toggle_organize, "F6", "organize",
                            "Miniaturas grandes: arraste para reordenar, botão direito para opções",
                            checkable=True)
        self.a_thumbs = A("Painel de miniaturas", self.toggle_thumbs, "F4", "pages", checkable=True)
        self.a_thumbs.setChecked(True)

        self.a_rot_r = A("Girar à direita", lambda: self.page_action("rot_r"), "Ctrl+R", "rotate_right")
        self.a_rot_l = A("Girar à esquerda", lambda: self.page_action("rot_l"), "Ctrl+Shift+R", "rotate_left")
        self.a_del = A("Excluir páginas", lambda: self.page_action("delete"), None, "trash")
        self.a_dup = A("Duplicar páginas", lambda: self.page_action("duplicate"), "Ctrl+D")
        self.a_blank = A("Inserir página em branco", lambda: self.page_action("blank"))
        self.a_ins = A("Inserir arquivo...", lambda: self.page_action("insert_file"), "Ctrl+Shift+I")
        self.a_extract = A("Extrair páginas selecionadas...", lambda: self.page_action("extract"), "Ctrl+E")
        self.a_split = A("Separar documento...", self.split_current, None, "split",
                         "Dividir este PDF em vários arquivos")
        self.a_reverse = A("Inverter ordem de todas as páginas", self.reverse_all)

        self.a_merge = A("Unir PDFs...", lambda: self.ctrl.merge([]), "Ctrl+M", "merge",
                         "Unir vários arquivos em um único PDF")
        self.a_split_files = A("Separar arquivos PDF...", lambda: self.ctrl.split([]), None, "split")
        self.a_convert = A("Converter arquivos...", lambda: self.ctrl.convert([]), "Ctrl+Shift+C", "convert",
                           "Converter Word, Excel, PowerPoint, imagens ↔ PDF")
        self.a_export = A("Exportar este PDF para...", self.export_current, None, "convert")
        self.a_ocr = A("Reconhecer texto (OCR)...", self.ocr_dialog, "Ctrl+Shift+O", "ocr",
                       "Reconhece o texto de páginas digitalizadas: torna o PDF pesquisável ou extrai o texto")
        self.a_translate = A("Traduzir documento...", self.translate_dialog, "Ctrl+Shift+L", "translate",
                             "Traduz o PDF mantendo o layout, ou só o texto (requer internet)")
        self.a_sign_inv = A("Assinar digitalmente (invisível)...", lambda: self.sign_document(None, None),
                            None, "signature", "Assina com certificado A1/A3 sem carimbo visível")
        self.a_verify = A("Verificar assinaturas digitais...", self.verify_signatures, None, "shield",
                          "Confere signatário, data e se o PDF foi alterado depois de assinado")
        self.a_shell_on = A("Adicionar ao menu do botão direito do Windows", self.shell_register)
        self.a_shell_off = A("Remover do menu do botão direito", self.shell_unregister)
        self.a_full_menu = A("Windows 11: mostrar as opções direto no botão direito", self.toggle_full_menu,
                             None, None, "Dispensa o “Mostrar mais opções” do Windows 11", checkable=True)
        self.a_full_menu.setChecked(shell.full_menu_enabled())
        self.a_full_menu.setVisible(shell.is_windows11())
        self.a_log = A("Abrir registro de erros", lambda: open_folder(str(log_path())))
        self.a_about = A("Sobre o Vorticis PDF Editor", lambda: about(self), "F1", "info")
        self.a_theme = A("Alternar tema claro/escuro", self.toggle_theme, "Ctrl+Shift+T", "moon")
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        current_mode = self.settings.value("theme", "system")
        for key, label in (("system", "Seguir o Windows"), ("light", "Claro"), ("dark", "Escuro")):
            ta = QAction(label, self, checkable=True)
            ta.setChecked(key == current_mode)
            ta.triggered.connect(lambda _c=False, k=key: self.set_theme(k))
            self.theme_group.addAction(ta)
            self.theme_actions[key] = ta

        # ferramentas: no máximo uma ativa; clicar de novo na ativa a desliga. Sem ferramenta
        # ativa, arrastar sobre o texto seleciona o texto (e fora dele move a página).
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        self.tool_actions = {}
        for key, text, ic, sc, tip in (
            (V.SELECT, "Seleção por retângulos", "select", "S",
             "Desenhe um ou mais retângulos para selecionar vários textos e editá-los de uma vez "
             "(clique num texto para incluir/retirar; Enter ou clique duplo para editar). "
             "Sem esta ferramenta, basta arrastar o mouse sobre o texto para selecioná-lo."),
            (V.PAN, "Mão", "pan", "H", "Arrastar a página"),
            (V.EDIT_TEXT, "Editar texto", "edit_text", "E",
             "Passe o mouse para ver a fonte; clique para editar mantendo a fonte original"),
            (V.ADD_TEXT, "Adicionar texto", "add_text", "T", "Clique onde deseja inserir texto"),
            (V.HIGHLIGHT, "Destacar", "highlight", "M", "Arraste sobre o texto para destacar"),
            (V.SHAPE, "Formas", "shapes", "F",
             "Retângulo, elipse, linha, seta, triângulo, estrela, visto, xis... (Shift = proporção)"),
            (V.INK, "Desenho livre", "pen", "D", "Desenhe à mão livre com o mouse"),
            (V.WHITEOUT, "Apagar área", "whiteout", "W", "Cobre e remove o conteúdo da área"),
            (V.NOTE, "Nota", "note", "N", "Adicionar comentário"),
            (V.IMAGE, "Imagem", "image", "I", "Arraste a área e escolha a imagem"),
            (V.CROP, "Recortar", "crop", "C", "Arraste a área visível da página"),
            (V.SIGN, "Assinar com certificado digital", "signature", "G",
             "Arraste a área onde o carimbo da assinatura digital (A1/A3, ICP-Brasil) deve aparecer"),
        ):
            a = A(text, lambda checked=False, k=key: self.set_tool(k if checked else V.BROWSE),
                  sc, ic, tip, checkable=True)
            a.setIcon(icon(ic))
            self.tool_group.addAction(a)
            self.tool_actions[key] = a

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("&Arquivo")
        m.addActions([self.a_new_pdf, self.a_open, self.a_new_win])
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
        m.addSeparator()
        tm = m.addMenu("Tema")
        tm.addActions(list(self.theme_actions.values()))
        tm.addSeparator()
        tm.addAction(self.a_theme)
        m = mb.addMenu("&Páginas")
        m.addActions([self.a_rot_r, self.a_rot_l, self.a_dup, self.a_blank, self.a_ins])
        m.addSeparator()
        m.addActions([self.a_extract, self.a_split, self.a_reverse, self.a_del])
        m = mb.addMenu("&Ferramentas")
        m.addActions([self.a_merge, self.a_split_files, self.a_convert])
        m.addSeparator()
        m.addActions([self.a_ocr, self.a_translate])
        m.addSeparator()
        m.addAction(self.tool_actions[V.SIGN])
        m.addActions([self.a_sign_inv, self.a_verify])
        m.addSeparator()
        m.addActions([self.a_shell_on, self.a_shell_off, self.a_full_menu])
        m = mb.addMenu("Aj&uda")
        m.addActions([self.a_about, self.a_log])

    def _build_toolbars(self):
        tb = QToolBar("Principal")
        tb.setObjectName("HeaderBar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonIconOnly)
        tb.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.TopToolBarArea, tb)
        tb.addActions([self.a_new_pdf, self.a_open, self.a_save, self.a_print])
        tb.addWidget(_sep())
        tb.addActions([self.a_undo, self.a_redo])
        tb.addWidget(_sep())
        tb.addAction(self.a_zoom_out)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setFixedWidth(96)
        for z in (25, 50, 75, 100, 125, 150, 200, 300, 400):
            self.zoom_combo.addItem(f"{z}%")
        self.zoom_combo.addItems(["Largura", "Página"])
        self.zoom_combo.setToolTip("Zoom (Ctrl + roda do mouse)")
        tb.addWidget(self.zoom_combo)
        tb.addActions([self.a_zoom_in, self.a_fit_w, self.a_fit_p])
        tb.addWidget(_sep())
        self.page_spin = QSpinBox(minimum=1, maximum=1)
        self.page_spin.setFixedWidth(78)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.setToolTip("Ir para a página")
        tb.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0 ")
        self.page_total.setObjectName("Muted")
        tb.addWidget(self.page_total)
        tb.addWidget(_sep())
        tb.addActions([self.a_organize, self.a_rot_l, self.a_rot_r])
        tb.addWidget(_sep())
        tb.addActions([self.a_split, self.a_convert, self.a_ocr, self.a_translate, self.a_verify])
        merge_btn = QToolButton()
        merge_btn.setObjectName("Primary")
        merge_btn.setDefaultAction(self.a_merge)
        self.merge_btn = merge_btn
        merge_btn.setText("Unir PDFs")
        merge_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        tb.addWidget(merge_btn)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText("Localizar no documento…")
        self._search_icon = self.search_box.addAction(icon("search"), QLineEdit.LeadingPosition)
        self.search_box.setFixedWidth(240)
        self.search_box.setClearButtonEnabled(True)
        tb.addWidget(self.search_box)
        self.search_lbl = QLabel("")
        self.search_lbl.setObjectName("Muted")
        tb.addWidget(self.search_lbl)
        tb.addAction(self.a_theme)
        tb.addAction(self.a_about)

        self._build_shape_bar()
        self._build_sel_bar()
        from .inline_edit import TextEditBar
        self.text_bar = TextEditBar(self)
        self.addToolBar(Qt.TopToolBarArea, self.text_bar)
        self.text_bar.applyRequested.connect(self.finish_inline)
        self.text_bar.cancelRequested.connect(lambda: self.view.inline and self.view.inline.cancel())

        rail = QToolBar("Ferramentas")
        rail.setObjectName("ToolRail")
        rail.setMovable(False)
        rail.setFloatable(False)
        rail.setOrientation(Qt.Vertical)
        rail.setIconSize(QSize(22, 22))
        rail.setToolButtonStyle(Qt.ToolButtonIconOnly)
        rail.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.LeftToolBarArea, rail)
        for key, a in self.tool_actions.items():
            rail.addAction(a)
            if key in (V.PAN, V.ADD_TEXT, V.INK, V.NOTE, V.CROP):
                rail.addWidget(self._rail_sep())
        self.rail = rail

    def _build_shape_bar(self):
        from .dialogs import ColorButton
        from .document import SHAPES
        bar = QToolBar("Opções da forma")
        bar.setObjectName("HeaderBar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.addToolBar(Qt.TopToolBarArea, bar)
        st = self.view.shape_style
        self.shape_kind = QComboBox()
        for k, label in SHAPES.items():
            self.shape_kind.addItem(label, k)
        self.shape_kind.currentIndexChanged.connect(
            lambda _i: setattr(self.view, "shape_kind", self.shape_kind.currentData()))
        self.shape_kind_lbl = QLabel("  Forma: ")
        self.shape_kind_act = [bar.addWidget(self.shape_kind_lbl), bar.addWidget(self.shape_kind)]
        bar.addWidget(QLabel("   Contorno: "))
        self.stroke_btn = ColorButton(st["stroke"])
        self.stroke_btn.setFixedWidth(92)
        self.stroke_btn.changed = lambda: st.__setitem__("stroke", self.stroke_btn.rgb)
        bar.addWidget(self.stroke_btn)
        self.fill_chk = QCheckBox("  Preenchimento: ")
        bar.addWidget(self.fill_chk)
        self.fill_btn = ColorButton((0.99, 0.91, 0.91))
        self.fill_btn.setFixedWidth(92)
        self.fill_btn.setEnabled(False)

        def fill_changed(*_a):
            self.fill_btn.setEnabled(self.fill_chk.isChecked())
            st["fill"] = self.fill_btn.rgb if self.fill_chk.isChecked() else None
        self.fill_chk.toggled.connect(fill_changed)
        self.fill_btn.changed = fill_changed
        bar.addWidget(self.fill_btn)
        bar.addWidget(QLabel("   Espessura: "))
        from PySide6.QtWidgets import QDoubleSpinBox
        self.width_spin = QDoubleSpinBox(minimum=0.5, maximum=20, value=st["width"], singleStep=0.5, suffix=" pt")
        self.width_spin.setFixedWidth(96)
        self.width_spin.valueChanged.connect(lambda v: st.__setitem__("width", v))
        bar.addWidget(self.width_spin)
        bar.addWidget(QLabel("   Opacidade: "))
        self.op_spin = QSpinBox(minimum=10, maximum=100, value=100, singleStep=10, suffix=" %")
        self.op_spin.setFixedWidth(86)
        self.op_spin.valueChanged.connect(lambda v: st.__setitem__("opacity", v / 100))
        bar.addWidget(self.op_spin)
        self.dash_chk = QCheckBox("  Tracejado")
        self.dash_chk.toggled.connect(lambda on: st.__setitem__("dashed", on))
        bar.addWidget(self.dash_chk)
        hint = QLabel("    Shift = proporção perfeita • clique na forma para mover • Delete para excluir")
        hint.setObjectName("Muted")
        bar.addWidget(hint)
        bar.hide()
        self.shape_bar = bar

    def _build_sel_bar(self):
        bar = QToolBar("Seleção")
        bar.setObjectName("HeaderBar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.TopToolBarArea, bar)
        self.sel_count = QLabel("  Nenhum texto selecionado  ")
        self.sel_count.setStyleSheet("font-weight:600")
        bar.addWidget(self.sel_count)
        self.sel_edit_btn = QPushButton(icon("edit_text", "#ffffff"), "  Editar textos selecionados")
        self.sel_edit_btn.setObjectName("Primary")
        self.sel_edit_btn.clicked.connect(self.edit_selected_texts)
        bar.addWidget(self.sel_edit_btn)
        self.sel_actions = []
        for ic, label, fn in (("copy", "Copiar", self.copy),
                              ("highlight", "Destacar", lambda: self.markup_rect_selection("highlight")),
                              (None, "Sublinhar", lambda: self.markup_rect_selection("underline")),
                              ("trash", "Excluir textos", self.delete_selected_texts),
                              (None, "Limpar seleção", self.view.clear_rect_selection)):
            b = QToolButton()
            b.setText(label)
            if ic:
                b.setIcon(icon(ic))
                b.setProperty("vicon_btn", ic)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.clicked.connect(fn)
            bar.addWidget(b)
            self.sel_actions.append(b)
        hint = QLabel("    Arraste para adicionar retângulos • clique num texto para incluir/retirar • "
                      "Ctrl+A = página inteira • Enter = editar")
        hint.setObjectName("Muted")
        bar.addWidget(hint)
        bar.hide()
        self.sel_bar = bar

    def _update_sel_bar(self, n):
        if not hasattr(self, "sel_count"):
            return
        self.sel_count.setText(f"  {n} texto(s) selecionado(s)  " if n else
                               "  Desenhe retângulos sobre os textos  ")
        self.sel_edit_btn.setEnabled(n > 0)
        for b in self.sel_actions[:-1]:
            b.setEnabled(n > 0)

    @staticmethod
    def _rail_sep():
        w = QWidget()
        w.setFixedHeight(9)
        w.setObjectName("RailSep")
        w.setAttribute(Qt.WA_StyledBackground, True)
        return w

    def _build_status(self):
        sb = self.statusBar()
        sb.setSizeGripEnabled(False)
        self.st_page = QLabel()
        self.st_zoom = QLabel()
        self.st_font = QLabel()
        self.st_font.setObjectName("FontBadge")
        self.st_font.hide()
        self.st_saved = QLabel()
        self.st_saved.setObjectName("SavedBadge")
        sb.addWidget(self.st_page)
        sb.addWidget(self.st_zoom)
        sb.addWidget(self.st_font)
        sb.addPermanentWidget(self.st_saved)

    def _set_saved_badge(self, text, dirty=False):
        self.st_saved.setObjectName("DirtyBadge" if dirty else "SavedBadge")
        self.st_saved.setStyleSheet(f"color:{c('warn') if dirty else c('ok')}")
        self.st_saved.setText(text)

    def _connect(self):
        self.view.zoomChanged.connect(self._on_zoom)
        self.view.pageChanged.connect(self._on_page)
        self.view.editTextRequested.connect(self.edit_text)
        self.view.addTextRequested.connect(self.add_text)
        self.view.noteRequested.connect(self.add_note)
        self.view.areaSelected.connect(self.area_tool)
        self.view.spanHovered.connect(self._show_hover_font)
        self.view.shapeDrawn.connect(self.on_shape)
        self.view.inkDrawn.connect(self.on_ink)
        self.view.annotMoved.connect(self.on_annot_moved)
        self.view.annotResized.connect(self.on_annot_resized)
        self.view.annotDeleteRequested.connect(self.on_annot_delete)
        self.view.annotMenuRequested.connect(self.annot_menu)
        self.view.pageMenuRequested.connect(self.page_menu)
        self.view.markupRequested.connect(self.markup_selection)
        self.view.rectSelectionChanged.connect(self._update_sel_bar)
        self.view.editSelectedRequested.connect(self.edit_selected_texts)
        self.view.deleteSelectedRequested.connect(self.delete_selected_texts)
        self.thumbs.pageActivated.connect(
            lambda i: self.view.set_current_page(i) if not self.a_organize.isChecked() else None)
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

    def _show_hover_font(self, page_no, span):
        """Mostra na barra de status a fonte do texto sob o cursor (ferramenta Editar texto)."""
        if not span:
            self.st_font.hide()
            return
        name = strip_subset(span["font"])
        sf, exact = catalog.match(span["font"], bool(span["flags"] & 16), bool(span["flags"] & 2))
        if sf and exact:
            status = "instalada ✔"
        elif sf:
            status = f"equivalente: {sf.label}"
        else:
            status = "embutida no PDF" if any(strip_subset(f[3]) == name and f[1] not in ("n/a", "")
                                              for f in self.pdoc.doc[page_no].get_fonts(full=True)) \
                else "usará fonte padrão"
        self.st_font.setText(f"Aa  {name} • {span['size']:.1f} pt • {status}")
        self.st_font.show()

    # ================================================================== documento
    def set_document(self, pdoc: PdfDocument | None):
        self.pdoc = pdoc
        doc = pdoc.doc if pdoc else None
        self.view.set_document(doc, keep_position=False)
        self.thumbs.set_document(doc, invalidate_all=True)
        has = pdoc is not None
        for a in (self.a_save, self.a_save_as, self.a_print, self.a_props, self.a_export,
                  self.a_rot_r, self.a_rot_l, self.a_del, self.a_dup, self.a_blank, self.a_ins,
                  self.a_extract, self.a_split, self.a_reverse, self.a_organize, self.a_ocr,
                  self.a_translate, self.a_sign_inv, self.a_verify):
            a.setEnabled(has)
        self.st_saved.setText("")
        self.stack.setCurrentIndex(1 if has else 0)
        for w in (self.rail,):
            w.setVisible(has)
        if not has:
            self._fill_recent_list()
        self._update_state()
        if pdoc and pdoc.path:
            self._add_recent(pdoc.path)

    def is_empty(self):
        return self.pdoc is None

    def load(self, path: str, organize=False):
        if not path:
            return False
        if not os.path.isfile(path):
            QMessageBox.warning(self, APP_NAME, f"Arquivo não encontrado:\n{path}")
            return False
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
        if pdoc.is_native_pdf() and sig.has_signatures(path):
            self.statusBar().showMessage("🔏 Documento assinado digitalmente — Ferramentas › Verificar "
                                         "assinaturas digitais", 12000)
        elif pdoc.page_count and not any(pdoc.doc[i].get_text().strip() for i in range(min(3, pdoc.page_count))):
            self.statusBar().showMessage("Este PDF parece digitalizado (sem texto). Use “Reconhecer texto "
                                         "(OCR)” para pesquisar, copiar e traduzir.", 12000)
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
            self._set_saved_badge(f"● {len(p.edits)} alteração(ões) não salva(s)", dirty=True)

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
        self.finish_inline()
        if not self.pdoc.path:
            # documento novo/convertido: grava direto (sem janela) ao lado do original ou em Documentos
            return self._do_save(self._auto_save_path())
        return self._do_save(self.pdoc.path)

    def _doc_folder(self) -> Path:
        from .config import documents_dir
        if self.pdoc and self.pdoc.path:
            return Path(self.pdoc.path).parent
        conv_name = getattr(self, "_converted_name", "")
        if conv_name and Path(conv_name).parent.is_dir() and str(Path(conv_name).parent) not in ("", "."):
            return Path(conv_name).parent
        return documents_dir()

    def _auto_save_path(self) -> str:
        from .config import unique_path
        conv_name = getattr(self, "_converted_name", "")
        name = Path(conv_name).name if conv_name else ""
        if not name:
            stem = Path(self.pdoc.title).stem if self.pdoc and self.pdoc.title else ""
            name = (stem if stem and stem.lower() not in ("sem título", "sem titulo") else "Novo documento") + ".pdf"
        if not name.lower().endswith(".pdf"):
            name = Path(name).stem + ".pdf"
        folder = self._doc_folder()
        folder.mkdir(parents=True, exist_ok=True)
        return unique_path(folder / name)

    def save_as(self) -> bool:
        if not self.pdoc:
            return False
        self.finish_inline()
        suggestion = self.pdoc.path or getattr(self, "_converted_name", "") or \
            str(Path(self.settings.value("last_dir", str(Path.home()))) / "documento.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Salvar como", suggestion, PDF_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        return self._do_save(path)

    def _do_save(self, path) -> bool:
        """Grava sem nenhuma janela ou mensagem: só a barra de status mostra que foi salvo
        (o histórico de salvamentos continua registrando tudo)."""
        same_file = bool(self.pdoc.path) and os.path.abspath(path) == os.path.abspath(self.pdoc.path)
        had_signature = same_file and sig.has_signatures(path)
        try:
            info = self.pdoc.save(path, self.save_password)
        except Exception as e:
            from .i18n import friendly
            QMessageBox.critical(self, APP_NAME, f"Erro ao salvar:\n{friendly(e)}")
            return False
        self._add_recent(path)
        badge = f"✔ Salvo às {now_str()[-8:]} • {info['tamanho_atual']} • {path}"
        if had_signature:
            badge += " • as assinaturas digitais anteriores deixaram de valer"
        self._set_saved_badge(badge)
        self._update_state()
        return True

    def export_current(self):
        if not self.pdoc:
            return
        if (self.pdoc.modified or not self.pdoc.path) and not self.save():
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
            if os.path.isfile(p):
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
        self.finish_inline()
        if rows is None:
            rows = self.thumbs.selected_rows()
        try:
            print_document(self, self.pdoc.doc, rows, current=self.view.current)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível imprimir:\n{e}")

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
        """key = V.BROWSE desliga todas as ferramentas (modo padrão)."""
        self.finish_inline()
        if key in self.tool_actions:
            self.tool_actions[key].setChecked(True)
        else:
            for a in self.tool_actions.values():
                a.setChecked(False)
        self.view.set_tool(key)
        self.shape_bar.setVisible(key in (V.SHAPE, V.INK))
        for a in self.shape_kind_act:
            a.setVisible(key == V.SHAPE)
        self.sel_bar.setVisible(key == V.SELECT)
        self._update_sel_bar(len(self.view.sel_items))
        if self.a_organize.isChecked() and key != V.BROWSE:
            self.a_organize.setChecked(False)
            self.toggle_organize()

    # ---------- edição de texto direto na página ----------
    def start_inline(self, items=None, add_at=None):
        """Abre caixas de edição sobre os textos (ou no ponto clicado, para texto novo)."""
        from .inline_edit import InlineSession
        if not self.pdoc:
            return
        self.finish_inline()
        s = InlineSession(self.view, self.pdoc, items, add_at,
                          default_size=float(self.settings.value("add_text_size", 12)))
        if not s.fields:
            return
        self.view.inline = s
        s.finished.connect(self._inline_finished)
        # a barra de formatação ocupa o lugar das barras da seleção/formas enquanto edita
        self._bars_before = [b for b in (self.sel_bar, self.shape_bar) if b.isVisible()]
        for b in self._bars_before:
            b.hide()
        self.text_bar.bind(s)

    def finish_inline(self):
        """Aplica a edição em andamento (antes de salvar, imprimir, trocar de ferramenta...)."""
        if self.view.inline is not None and not self.view.inline.done:
            self.view.inline.commit()

    def _inline_finished(self, changes, _apply):
        self.text_bar.unbind()
        self.view.inline = None
        for b in getattr(self, "_bars_before", []):
            b.setVisible(True)
        self._bars_before = []
        if not changes or not self.pdoc:
            return
        edits = [c for c in changes if c["span"] is not None]
        adds = [c for c in changes if c["span"] is None]
        fit = self.text_bar.fit.isChecked()
        pages = sorted({c["page"] for c in changes})
        try:
            if len(edits) == 1:
                c = edits[0]
                used = self.pdoc.replace_text(c["page"], c["span"], c["text"], c["font"], c["size"],
                                              c["color"], fit=fit)
                extra = f" (ajustado para {used:.1f} pt)" if used < c["size"] - 0.05 else ""
                msg = f"Texto editado com a fonte {c['font'].label}{extra}"
            elif edits:
                n = self.pdoc.replace_texts(edits, fit=fit)
                msg = f"{n} texto(s) editado(s) de uma só vez"
            for c in adds:
                self.pdoc.add_text(c["page"], (c["origin"][0], c["origin"][1] + c["size"] * 0.8),
                                   c["text"], c["font"], c["size"], c["color"])
                self.settings.setValue("add_text_size", c["size"])
                msg = f"Texto adicionado com a fonte {c['font'].label}"
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Não foi possível editar o texto:\n{e}")
            return
        if self.view.tool == V.SELECT:
            self.view.clear_rect_selection()
        self.refresh(pages=pages)
        self.statusBar().showMessage(msg, 5000)

    # ---------- vários textos (ferramenta Seleção por retângulos) ----------
    def edit_selected_texts(self):
        items = list(self.view.sel_items)
        if items:
            self.start_inline(items)

    def delete_selected_texts(self):
        items = list(self.view.sel_items)
        if not items:
            return
        from .fonts import ResolvedFont
        changes = [{"page": pg, "span": sp, "text": "", "font": ResolvedFont("Helvetica", "padrão", base14="helv"),
                    "size": sp["size"], "color": (0, 0, 0)} for pg, sp in items]
        self.pdoc.replace_texts(changes, fit=False)
        self.pdoc.edits[-1] = f"Excluiu {len(items)} texto(s)"
        self.view.clear_rect_selection()
        self.refresh(pages=sorted({pg for pg, _sp in items}))

    def markup_rect_selection(self, kind):
        by_page = {}
        for pg, sp in self.view.sel_items:
            by_page.setdefault(pg, []).append(pymupdf.Rect(sp["bbox"]))
        for pg, rects in by_page.items():
            self.pdoc.markup_text(pg, rects, kind)
        self.view.clear_rect_selection()
        self.refresh(pages=list(by_page))

    def edit_text(self, page_no, span):
        self.start_inline([(page_no, span)])

    def add_text(self, page_no, pt):
        self.start_inline(None, add_at=(page_no, pt))

    def add_note(self, page_no, pt):
        text, ok = QInputDialog.getMultiLineText(self, "Nota", "Comentário:")
        if ok and text.strip():
            self.pdoc.add_note(page_no, pymupdf.Point(pt), text)
            self.refresh(pages=[page_no])

    def area_tool(self, tool, page_no, rect):
        r = pymupdf.Rect(rect)
        if tool == V.SIGN:
            self.sign_document(page_no, r)
            return
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
        from .config import unique_path
        stem = Path(self.pdoc.title).stem
        label = f"{rows[0] + 1}" if len(rows) == 1 else f"{rows[0] + 1}-{rows[-1] + 1}"
        path = unique_path(self._doc_folder() / f"{stem}_pag{label}.pdf")
        out = PdfDocument(doc=self.pdoc.extract(rows))
        out.edits = [f"Extraiu {len(rows)} página(s) de {self.pdoc.title}"]
        out.save(path)
        self.statusBar().showMessage(f"✔ Páginas extraídas para {path}", 8000)

    def split_at(self, row):
        if row == 0:
            QMessageBox.information(self, APP_NAME, "Escolha uma página depois da primeira.")
            return
        n = self.pdoc.page_count
        files = split_document(self.pdoc.doc, [list(range(row)), list(range(row, n))],
                               str(self._doc_folder()), Path(self.pdoc.title).stem)
        self.statusBar().showMessage("✔ Separado em: " + " • ".join(Path(f).name for f in files), 8000)

    def split_current(self):
        if not self.pdoc:
            return
        dlg = SplitDialog(self, doc=self.pdoc.doc, name=Path(self.pdoc.title).stem)
        if self.pdoc.path:
            dlg.out_dir.setText(str(Path(self.pdoc.path).parent))
        dlg.exec()

    # ================================================================== novo PDF
    def new_pdf(self):
        from .document import create_blank
        from .features import NewPdfDialog
        dlg = NewPdfDialog(self)
        if not dlg.exec():
            return
        v = dlg.values()
        pd = create_blank(v["width"], v["height"], v["pages"], v["background"], v["title"])
        w = self if self.is_empty() else self.ctrl.new_window()
        w.set_document(pd)
        w._converted_name = str(Path(w.settings.value("last_dir", str(Path.home()))) /
                                f"{v['title'] or 'Novo documento'}.pdf")
        w.set_tool(V.ADD_TEXT)
        w.statusBar().showMessage("Documento criado. Clique na página para escrever, ou use Formas, "
                                  "Imagem e Desenho livre na barra lateral.", 10000)

    # ================================================================== formas e marcações
    def on_shape(self, page_no, kind, p1, p2):
        xref = self.pdoc.add_shape(page_no, kind, p1, p2, dict(self.view.shape_style))
        self.refresh(pages=[page_no])
        self._select_xref(page_no, xref)

    def on_ink(self, page_no, points):
        xref = self.pdoc.add_ink(page_no, points, dict(self.view.shape_style))
        self.refresh(pages=[page_no])
        self._select_xref(page_no, xref)

    def _select_xref(self, page_no, xref):
        page = self.pdoc.doc[page_no]  # mantém a página viva enquanto lê as anotações
        for a in page.annots():
            if a.xref == xref:
                self.view.select_annot(page_no, (xref, a.type[1], pymupdf.Rect(a.rect)))
                break

    def on_annot_moved(self, page_no, xref, dx, dy):
        new = self.pdoc.move_annot(page_no, xref, dx, dy)
        self.refresh(pages=[page_no])
        self._select_xref(page_no, new)

    def on_annot_resized(self, page_no, xref, rect):
        self.pdoc.resize_annot(page_no, xref, rect)
        self.refresh(pages=[page_no])
        self._select_xref(page_no, xref)

    def on_annot_delete(self, page_no, xref):
        self.pdoc.delete_annot(page_no, xref)
        self.refresh(pages=[page_no])

    def annot_menu(self, page_no, xref, gpos):
        from PySide6.QtWidgets import QColorDialog, QMenu
        m = QMenu(self)
        m.addAction(icon("trash"), "Excluir   (Delete)", lambda: self.on_annot_delete(page_no, xref))
        m.addSeparator()

        def pick(key, title):
            c = QColorDialog.getColor(parent=self, title=title)
            if c.isValid():
                self.pdoc.restyle_annot(page_no, xref, **{key: (c.redF(), c.greenF(), c.blueF())})
                self.refresh(pages=[page_no])
                self._select_xref(page_no, xref)
        m.addAction("Cor do contorno...", lambda: pick("stroke", "Cor do contorno"))
        m.addAction("Cor de preenchimento...", lambda: pick("fill", "Cor de preenchimento"))

        def restyle(**kw):
            self.pdoc.restyle_annot(page_no, xref, **kw)
            self.refresh(pages=[page_no])
            self._select_xref(page_no, xref)
        m.addAction("Sem preenchimento", lambda: restyle(fill=None))
        wm = m.addMenu("Espessura")
        for w in (0.5, 1, 2, 3, 4, 6, 8):
            wm.addAction(f"{w:g} pt", lambda w=w: restyle(width=float(w)))
        om = m.addMenu("Opacidade")
        for o in (100, 75, 50, 25):
            om.addAction(f"{o}%", lambda o=o: restyle(opacity=o / 100))
        m.addAction("Contorno tracejado / contínuo", lambda: restyle(dashed=not self._annot_dashed(page_no, xref)))
        m.exec(gpos)

    def _annot_dashed(self, page_no, xref):
        page = self.pdoc.doc[page_no]
        for a in page.annots():
            if a.xref == xref:
                return bool((a.border or {}).get("dashes"))
        return False

    def markup_selection(self, kind):
        v = self.view
        if not v.text_sel or not v.selection_rects:
            return
        page_no = v.text_sel[0]
        rects = [r for pg, r in v.selection_rects if pg == page_no]
        self.pdoc.markup_text(page_no, rects, kind)
        v.clear_selection()
        self.refresh(pages=[page_no])

    def translate_selection(self):
        text = self.view.selected_text
        if not text:
            return
        dlg = TextResultDialog(self, "Traduzir seleção", text, Path(self.pdoc.title).stem)
        dlg.folder = self._doc_folder()
        dlg._translate()
        dlg.exec()

    def page_menu(self, page_no, pt, gpos):
        from PySide6.QtWidgets import QMenu
        from .document import SHAPES
        v = self.view
        m = QMenu(self)
        if v.selected_text:
            m.addAction(icon("copy"), "Copiar   (Ctrl+C)", self.copy)
            m.addAction(icon("highlight"), "Destacar", lambda: self.markup_selection("highlight"))
            m.addAction("Sublinhar", lambda: self.markup_selection("underline"))
            m.addAction("Riscar", lambda: self.markup_selection("strikeout"))
            m.addAction(icon("translate"), "Traduzir seleção...", self.translate_selection)
            preview = v.selected_text.replace("\n", " ")[:30]
            m.addAction(icon("search"), f"Localizar “{preview}”",
                        lambda: (self.search_box.setText(v.selected_text.split("\n")[0]), self.search_next()))
            m.addSeparator()
        m.addAction("Selecionar todo o texto da página   (Ctrl+A)", lambda: v.select_all_page(page_no))
        m.addSeparator()
        m.addAction(icon("add_text"), "Adicionar texto aqui", lambda: self.add_text(page_no, pt))
        m.addAction(icon("note"), "Adicionar nota aqui", lambda: self.add_note(page_no, pt))
        sm = m.addMenu(icon("shapes"), "Inserir forma aqui")
        for k, label in SHAPES.items():
            sm.addAction(label, lambda k=k: self.on_shape(
                page_no, k, pt, (pt[0] + 120, pt[1] + (0 if k in ("line", "arrow", "double_arrow") else 80))))
        m.addAction(icon("image"), "Inserir imagem aqui...", lambda: self.area_tool(
            V.IMAGE, page_no, (pt[0], pt[1], pt[0] + 200, pt[1] + 150)))
        m.addSeparator()
        m.addAction(icon("rotate_right"), "Girar esta página", lambda: self.thumb_action("rot_r", [page_no]))
        m.addAction(icon("pages"), "Inserir página em branco depois", lambda: self.thumb_action("blank", [page_no]))
        m.exec(gpos)

    # ================================================================== OCR e tradução
    def _scope_args(self):
        return self.pdoc.page_count, self.view.current, self.thumbs.selected_rows()

    def ocr_dialog(self):
        if not self.pdoc:
            return
        dlg = OcrDialog(self, *self._scope_args())
        if not dlg.exec():
            return
        pages, langs, dpi = dlg.selected_pages, dlg.langs(), dlg.dpi.currentData()
        skip = dlg.skip.isChecked()
        if dlg.mode_search.isChecked():
            self.pdoc.checkpoint(f"Reconheceu texto (OCR) em {len(pages)} página(s)")

            def done(res):
                self.refresh(pages=pages)
                done_pages = res["paginas_ocr"]
                msg = (f"✔ OCR concluído: {len(done_pages)} página(s) agora pesquisáveis "
                       f"({res['palavras']} palavras reconhecidas)")
                if res["paginas_com_texto"]:
                    msg += f" • {len(res['paginas_com_texto'])} já tinham texto e foram mantidas"
                self.statusBar().showMessage(msg, 10000)

            def failed(msg):
                self.pdoc.undo()  # descarta o ponto de restauração criado para o OCR
                self.refresh(structural=True)
                QMessageBox.critical(self, APP_NAME, f"Falha no OCR: {msg}")

            run_task(self, "Reconhecendo texto (OCR)...", ocr.make_searchable, self.pdoc.doc, pages, langs,
                     dpi, skip, on_done=done, on_error=failed, with_progress=True)
        else:
            def done_text(items):
                text = "\n\n".join(f"──── Página {n}{' (OCR)' if was_ocr else ''} ────\n{t.strip()}"
                                    for n, t, was_ocr in items)
                d = TextResultDialog(self, "Texto reconhecido", text, Path(self.pdoc.title).stem)
                d.folder = self._doc_folder()
                d.exec()

            run_task(self, "Reconhecendo texto (OCR)...", ocr.extract_text, self.pdoc.doc, pages, langs,
                     dpi, skip, on_done=done_text, with_progress=True)

    def translate_dialog(self):
        if not self.pdoc:
            return
        dlg = TranslateDialog(self, *self._scope_args())
        if not dlg.exec():
            return
        pages, target, source = dlg.selected_pages, dlg.dst.currentData(), dlg.src.currentData()
        if not any(self.pdoc.doc[p].get_text().strip() for p in pages):
            QMessageBox.information(self, APP_NAME, "As páginas escolhidas não têm texto digital. "
                                    "Use primeiro “Reconhecer texto (OCR)”.")
            return
        stem = Path(self.pdoc.title).stem
        if dlg.as_pdf.isChecked():
            def done(newdoc):
                pd = PdfDocument(doc=newdoc)
                pd.modified = True
                pd.edits.append(f"Traduzido para {tr.LANGS.get(target, target)}")
                w = self.ctrl.new_window(pd)
                w._converted_name = str(Path(self.pdoc.path or stem).with_name(f"{stem}_traduzido_{target}.pdf"))
            run_task(self, "Traduzindo o documento...", tr.translate_pdf, self.pdoc.doc, pages, target,
                     source, on_done=done, with_progress=True)
        else:
            text = "\n\n".join(self.pdoc.doc[p].get_text("text", sort=True).strip() for p in pages)
            dlg2 = TextResultDialog(self, "Tradução", text, stem)
            dlg2.folder = self._doc_folder()
            dlg2.lang.setCurrentIndex(max(0, dlg2.lang.findData(target)))
            run_task(self, "Traduzindo...", tr.translate_text, text, target, source,
                     on_done=lambda t: (dlg2.dst.setPlainText(t), dlg2.exec()), with_progress=True)

    # ================================================================== assinatura digital
    def _require_saved_pdf(self, action="assinar") -> bool:
        if self.pdoc.modified or not self.pdoc.path or not self.pdoc.is_native_pdf():
            if not self.save():  # salva direto, sem perguntar
                return False
        return True

    def sign_document(self, page_no, rect):
        if not self.pdoc or not self._require_saved_pdf():
            return
        dlg = SignDialog(self, self.pdoc.path, visible=rect is not None)
        if not dlg.exec():
            return
        params = dlg.params()
        out = dlg.out_path.text()
        kw = {}
        if rect is not None:
            kw = dict(page_index=page_no, rect=tuple(rect), mediabox=tuple(self.pdoc.doc[page_no].mediabox))

        def done(info):
            doc_id = f"CPF {info['cpf']}" if info.get("cpf") else (f"CNPJ {info['cnpj']}" if info.get("cnpj") else "")
            from .config import log_save
            log_save({"arquivo": out, "data_hora": now_str(), "paginas": self.pdoc.page_count,
                      "alteracoes": [f"Assinado digitalmente por {info['signatario']}"]})
            self.set_tool(V.BROWSE)
            self.load(out)
            self._set_saved_badge(f"✔ Assinado por {info['signatario']}{' — ' + doc_id if doc_id else ''} • {out}")

        run_task(self, "Assinando...", sig.sign_pdf, self.pdoc.path, out, on_done=done, **params, **kw)

    def verify_signatures(self):
        if not self.pdoc:
            return
        if not self.pdoc.path or not self.pdoc.is_native_pdf():
            QMessageBox.information(self, APP_NAME, "Este documento não possui assinaturas digitais.")
            return
        path = self.pdoc.path
        run_task(self, "Verificando assinaturas...", sig.verify_pdf, path,
                 on_done=lambda res: VerifyDialog(self, path, res).exec())

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
            return
        if shell.is_windows11() and not shell.full_menu_enabled():
            self.a_full_menu.setChecked(True)
            self.toggle_full_menu()

    def toggle_full_menu(self):
        on = self.a_full_menu.isChecked()
        text = ("Mostrar as opções do Vorticis direto no menu do botão direito do Windows 11, sem precisar "
                "de “Mostrar mais opções”?\n\nO Windows passará a exibir o menu completo (o mesmo do "
                "“Mostrar mais opções”) para todos os programas. Vale só para o seu usuário, não precisa de "
                "administrador e pode ser desfeito aqui a qualquer momento.\n\nO Explorer será reiniciado "
                "(as janelas de pastas abertas serão fechadas)." if on else
                "Voltar ao menu compacto do Windows 11? As opções do Vorticis voltarão a ficar em "
                "“Mostrar mais opções”.\n\nO Explorer será reiniciado.")
        if QMessageBox.question(self, APP_NAME, text) != QMessageBox.Yes:
            self.a_full_menu.setChecked(not on)
            return
        try:
            msg = shell.enable_full_menu() if on else shell.disable_full_menu()
            QMessageBox.information(self, APP_NAME, msg)
        except Exception as e:
            self.a_full_menu.setChecked(not on)
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
            self.set_tool(V.BROWSE)
        elif e.key() in (Qt.Key_PageDown,) and self.pdoc:
            self.view.set_current_page(min(self.view.current + 1, self.pdoc.page_count - 1))
        elif e.key() in (Qt.Key_PageUp,) and self.pdoc:
            self.view.set_current_page(max(self.view.current - 1, 0))
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        self.finish_inline()
        if not self.maybe_save():
            e.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.ctrl.window_closed(self)
        e.accept()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, lambda: self.view.set_fit(self.view.fit_mode) if self.view.fit_mode else None)
