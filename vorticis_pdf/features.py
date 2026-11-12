"""Diálogos de OCR, tradução e assinatura digital."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QRadioButton, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import APP_NAME
from . import ocr
from . import signature as sig
from . import translate as tr
from .config import settings
from .tasks import run_task
from .theme import c as tc


def _page_scope(parent, page_count, current, selected):
    """Grupo 'Páginas: todas / atual / selecionadas / intervalo'."""
    box = QGroupBox("Páginas")
    lay = QGridLayout(box)
    group = QButtonGroup(parent)
    opts = [("all", f"Todas ({page_count})"), ("current", f"Página atual ({current + 1})")]
    if selected and len(selected) > 1:
        opts.append(("selected", f"Selecionadas nas miniaturas ({len(selected)})"))
    opts.append(("range", "Intervalo:"))
    rng = QLineEdit()
    rng.setPlaceholderText("ex.: 1-3, 5")
    for i, (k, t) in enumerate(opts):
        rb = QRadioButton(t)
        rb.setProperty("key", k)
        group.addButton(rb, i)
        lay.addWidget(rb, i, 0)
    lay.addWidget(rng, len(opts) - 1, 1)
    group.button(0).setChecked(True)
    rng.textEdited.connect(lambda _t: group.button(len(opts) - 1).setChecked(True))

    def pages():
        from .document import parse_ranges
        key = group.checkedButton().property("key")
        if key == "current":
            return [current]
        if key == "selected":
            return list(selected)
        if key == "range":
            return [p for g in parse_ranges(rng.text(), page_count) for p in g]
        return list(range(page_count))
    return box, pages


def _lang_combo(include_auto=False, default="pt"):
    cb = QComboBox()
    for code, name in tr.LANGS.items():
        if code == "auto" and not include_auto:
            continue
        cb.addItem(name, code)
    cb.setCurrentIndex(max(0, cb.findData(default)))
    return cb


# ====================================================================== OCR
class OcrDialog(QDialog):
    def __init__(self, parent, page_count, current, selected):
        super().__init__(parent)
        self.setWindowTitle("Reconhecimento de texto (OCR)")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        intro = QLabel("Reconhece o texto de páginas digitalizadas (escaneadas ou fotografadas). "
                       "Funciona sem internet.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        mode = QGroupBox("O que fazer")
        ml = QVBoxLayout(mode)
        self.mode_search = QRadioButton("Tornar o PDF pesquisável — adiciona o texto reconhecido como "
                                        "camada invisível (a aparência da página não muda; permite "
                                        "buscar, selecionar, copiar e converter para Word/Excel)")
        self.mode_extract = QRadioButton("Extrair o texto — mostra o texto reconhecido para copiar, "
                                         "salvar (.txt / .docx) ou traduzir")
        for rb in (self.mode_search, self.mode_extract):
            rb.setStyleSheet("QRadioButton{padding:3px}")
            ml.addWidget(rb)
        self.mode_search.setChecked(True)
        lay.addWidget(mode)

        langs = QGroupBox("Idiomas do documento")
        ll = QVBoxLayout(langs)
        self.lang_list = QListWidget()
        self.lang_list.setMaximumHeight(110)
        ll.addWidget(self.lang_list)
        hb = QHBoxLayout()
        self.dl_combo = QComboBox()
        b = QPushButton("Baixar idioma")
        b.clicked.connect(self._download)
        hb.addWidget(QLabel("Outros idiomas:"))
        hb.addWidget(self.dl_combo, 1)
        hb.addWidget(b)
        ll.addLayout(hb)
        lay.addWidget(langs)
        self._fill_langs(settings().value("ocr_langs", "por,eng").split(","))

        opts = QFormLayout()
        self.dpi = QComboBox()
        for d, label in ((200, "Rápida (200 dpi)"), (300, "Recomendada (300 dpi)"), (400, "Alta precisão (400 dpi)")):
            self.dpi.addItem(label, d)
        self.dpi.setCurrentIndex(1)
        opts.addRow("Qualidade:", self.dpi)
        self.skip = QCheckBox("Ignorar páginas que já possuem texto digital")
        self.skip.setChecked(True)
        opts.addRow(self.skip)
        lay.addLayout(opts)
        scope, self.pages = _page_scope(self, page_count, current, selected)
        lay.addWidget(scope)

        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        bb.addButton("Reconhecer texto", QDialogButtonBox.AcceptRole).setDefault(True)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _fill_langs(self, checked):
        self.lang_list.clear()
        avail = ocr.available_langs()
        for code in avail:
            it = QListWidgetItem(f"{ocr.LANGS.get(code, code)}  ({code})")
            it.setData(Qt.UserRole, code)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if code in checked else Qt.Unchecked)
            self.lang_list.addItem(it)
        self.dl_combo.clear()
        for code, name in ocr.LANGS.items():
            if code not in avail:
                self.dl_combo.addItem(name, code)

    def langs(self):
        out = [self.lang_list.item(i).data(Qt.UserRole) for i in range(self.lang_list.count())
               if self.lang_list.item(i).checkState() == Qt.Checked]
        return out

    def _download(self):
        code = self.dl_combo.currentData()
        if not code:
            return
        checked = self.langs() + [code]

        def done(_p):
            self._fill_langs(checked)
            QMessageBox.information(self, APP_NAME, f"Idioma '{ocr.LANGS[code]}' instalado para o OCR.")
        run_task(self, f"Baixando {ocr.LANGS[code]}...", ocr.download_lang, code, on_done=done,
                 with_progress=True)

    def _accept(self):
        if not self.langs():
            QMessageBox.warning(self, APP_NAME, "Marque pelo menos um idioma.")
            return
        try:
            self.selected_pages = self.pages()
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        settings().setValue("ocr_langs", ",".join(self.langs()))
        self.accept()


# ====================================================================== texto + tradução
class TextResultDialog(QDialog):
    """Mostra um texto (ex.: resultado do OCR), permite copiar, salvar e traduzir."""

    def __init__(self, parent, title, text, base_name="texto"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(980, 640)
        self.base_name = base_name
        self.folder = None  # pasta do documento (definida por quem abre a janela)
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        self.src = QPlainTextEdit(text)
        self.dst = QPlainTextEdit()
        self.dst.setPlaceholderText("A tradução aparecerá aqui.")
        left, right = QWidget(), QWidget()
        l1, l2 = QVBoxLayout(left), QVBoxLayout(right)
        l1.setContentsMargins(0, 0, 4, 0)
        l2.setContentsMargins(4, 0, 0, 0)
        l1.addWidget(QLabel("<b>Texto</b> (pode ser editado)"))
        l1.addWidget(self.src)
        h = QHBoxLayout()
        h.addWidget(QLabel("<b>Tradução</b> para"))
        self.lang = _lang_combo(default=settings().value("translate_to", "pt"))
        h.addWidget(self.lang, 1)
        btn = QPushButton("Traduzir")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._translate)
        h.addWidget(btn)
        l2.addLayout(h)
        l2.addWidget(self.dst)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([500, 480])
        lay.addWidget(split, 1)
        note = QLabel(f"<small style='color:{tc('muted')}'>A tradução usa um serviço on-line gratuito "
                      "(requer internet). O OCR funciona sem internet.</small>")
        lay.addWidget(note)
        self.saved_lbl = QLabel()
        self.saved_lbl.setWordWrap(True)
        self.saved_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.saved_lbl)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        for label, fn in (("Copiar texto", lambda: self._copy(self.src)),
                          ("Copiar tradução", lambda: self._copy(self.dst)),
                          ("Salvar .txt", self._save_txt), ("Salvar .docx", self._save_docx)):
            bb.addButton(label, QDialogButtonBox.ActionRole).clicked.connect(fn)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _copy(self, edit):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(edit.toPlainText())

    def _translate(self):
        target = self.lang.currentData()
        settings().setValue("translate_to", target)
        run_task(self, "Traduzindo...", tr.translate_text, self.src.toPlainText(), target,
                 on_done=self.dst.setPlainText, with_progress=True)

    def _target(self, ext):
        """Salva direto ao lado do documento (sem janela): a tradução, se houver, senão o texto."""
        from .config import documents_dir, unique_path
        translated = bool(self.dst.toPlainText().strip())
        text = self.dst.toPlainText() if translated else self.src.toPlainText()
        folder = Path(self.folder) if self.folder else documents_dir()
        name = f"{self.base_name}_{'traduzido' if translated else 'texto'}{ext}"
        return text, unique_path(folder / name)

    def _saved(self, path):
        self.saved_lbl.setText(f"<span style='color:{tc('ok')}'>✔ Salvo em {path}</span>")

    def _save_txt(self):
        text, path = self._target(".txt")
        Path(path).write_text(text, "utf-8")
        self._saved(path)

    def _save_docx(self):
        import docx
        text, path = self._target(".docx")
        d = docx.Document()
        for para in text.split("\n"):
            d.add_paragraph(para)
        d.save(path)
        self._saved(path)


class TranslateDialog(QDialog):
    def __init__(self, parent, page_count, current, selected):
        super().__init__(parent)
        self.setWindowTitle("Traduzir documento")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.src = _lang_combo(include_auto=True, default="auto")
        self.dst = _lang_combo(default=settings().value("translate_to", "pt"))
        form.addRow("Idioma original:", self.src)
        form.addRow("Traduzir para:", self.dst)
        lay.addLayout(form)
        mode = QGroupBox("Resultado")
        ml = QVBoxLayout(mode)
        self.as_pdf = QRadioButton("Novo PDF traduzido, mantendo o layout (imagens, linhas e tabelas "
                                   "são preservadas; o texto é ajustado ao espaço de cada bloco)")
        self.as_text = QRadioButton("Somente o texto traduzido (para copiar ou salvar)")
        self.as_pdf.setChecked(True)
        ml.addWidget(self.as_pdf)
        ml.addWidget(self.as_text)
        lay.addWidget(mode)
        scope, self.pages = _page_scope(self, page_count, current, selected)
        lay.addWidget(scope)
        tip = QLabel("Dica: em documentos digitalizados, faça o OCR antes de traduzir. "
                     "A tradução requer internet (serviço gratuito).")
        tip.setWordWrap(True)
        tip.setObjectName("Muted")
        lay.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        bb.addButton("Traduzir", QDialogButtonBox.AcceptRole).setDefault(True)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _accept(self):
        try:
            self.selected_pages = self.pages()
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        settings().setValue("translate_to", self.dst.currentData())
        self.accept()


# ====================================================================== assinatura digital
class SignDialog(QDialog):
    def __init__(self, parent, pdf_path, visible: bool):
        super().__init__(parent)
        self.setWindowTitle("Assinar com certificado digital")
        self.setMinimumWidth(600)
        self.pdf_path = pdf_path
        self.cert_ok = False
        self.a3_certs = []
        st = settings()
        lay = QVBoxLayout(self)

        tipo = QGroupBox("Certificado")
        tl = QVBoxLayout(tipo)
        self.rb_a1 = QRadioButton("A1 — arquivo de certificado (.pfx / .p12)")
        self.rb_a3 = QRadioButton("A3 — token USB ou cartão inteligente")
        tl.addWidget(self.rb_a1)
        tl.addWidget(self.rb_a3)
        self.stack = QStackedWidget()
        # A1
        w1 = QWidget()
        f1 = QFormLayout(w1)
        f1.setContentsMargins(20, 0, 0, 0)
        row = QHBoxLayout()
        self.a1_path = QLineEdit(st.value("sign_a1_path", ""))
        b = QPushButton("Procurar...")
        b.clicked.connect(self._browse_a1)
        row.addWidget(self.a1_path, 1)
        row.addWidget(b)
        f1.addRow("Arquivo:", row)
        self.a1_pass = QLineEdit()
        self.a1_pass.setEchoMode(QLineEdit.Password)
        self.a1_pass.setPlaceholderText("senha do certificado")
        f1.addRow("Senha:", self.a1_pass)
        # A3
        w3 = QWidget()
        f3 = QFormLayout(w3)
        f3.setContentsMargins(20, 0, 0, 0)
        row3 = QHBoxLayout()
        self.a3_driver = QComboBox()
        self.a3_driver.setEditable(True)
        for label, path in sig.find_pkcs11_drivers():
            self.a3_driver.addItem(f"{label} — {path}", path)
        if not self.a3_driver.count():
            self.a3_driver.setEditText("")
            self.a3_driver.lineEdit().setPlaceholderText("driver do token não encontrado — clique em Procurar")
        saved = st.value("sign_a3_driver", "")
        if saved:
            i = self.a3_driver.findData(saved)
            if i >= 0:
                self.a3_driver.setCurrentIndex(i)
            else:
                self.a3_driver.setEditText(saved)
        bd = QPushButton("Procurar...")
        bd.clicked.connect(self._browse_driver)
        row3.addWidget(self.a3_driver, 1)
        row3.addWidget(bd)
        f3.addRow("Driver (PKCS#11):", row3)
        self.a3_pin = QLineEdit()
        self.a3_pin.setEchoMode(QLineEdit.Password)
        self.a3_pin.setPlaceholderText("PIN do token/cartão")
        f3.addRow("PIN:", self.a3_pin)
        self.a3_cert = QComboBox()
        f3.addRow("Certificado:", self.a3_cert)
        self.stack.addWidget(w1)
        self.stack.addWidget(w3)
        tl.addWidget(self.stack)
        self.rb_a1.toggled.connect(lambda on: self.stack.setCurrentIndex(0 if on else 1))
        (self.rb_a3 if st.value("sign_type", "a1") == "a3" else self.rb_a1).setChecked(True)
        self.stack.setCurrentIndex(0 if self.rb_a1.isChecked() else 1)
        hb = QHBoxLayout()
        load = QPushButton("Ler certificado")
        load.clicked.connect(self._load_cert)
        hb.addWidget(load)
        hb.addStretch()
        tl.addLayout(hb)
        self.cert_lbl = QLabel("Informe o certificado e clique em “Ler certificado”.")
        self.cert_lbl.setWordWrap(True)
        self.cert_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tl.addWidget(self.cert_lbl)
        lay.addWidget(tipo)

        det = QGroupBox("Detalhes da assinatura")
        fd = QFormLayout(det)
        self.reason = QComboBox()
        self.reason.setEditable(True)
        self.reason.addItems(["Sou o autor deste documento", "Concordo com o conteúdo deste documento",
                              "Aprovado", "Revisado", "Ciente", ""])
        self.reason.setCurrentText(st.value("sign_reason", "Sou o autor deste documento"))
        fd.addRow("Motivo:", self.reason)
        self.location = QLineEdit(st.value("sign_location", ""))
        self.location.setPlaceholderText("cidade / UF")
        fd.addRow("Local:", self.location)
        self.contact = QLineEdit(st.value("sign_contact", ""))
        self.contact.setPlaceholderText("e-mail ou telefone (opcional)")
        fd.addRow("Contato:", self.contact)
        self.use_tsa = QCheckBox("Incluir carimbo do tempo (comprova a data/hora; requer internet)")
        self.use_tsa.setChecked(st.value("sign_tsa", False, type=bool))
        self.tsa = QComboBox()
        self.tsa.setEditable(True)
        for name, url in sig.TSA_SERVERS.items():
            self.tsa.addItem(f"{name} — {url}", url)
        fd.addRow(self.use_tsa)
        fd.addRow("Servidor:", self.tsa)
        lay.addWidget(det)

        out = QHBoxLayout()
        p = Path(pdf_path)
        self.out_path = QLineEdit(str(p.with_name(p.stem + "_assinado.pdf")))
        bo = QPushButton("...")
        bo.clicked.connect(self._browse_out)
        out.addWidget(QLabel("Salvar como:"))
        out.addWidget(self.out_path, 1)
        out.addWidget(bo)
        lay.addLayout(out)
        info = QLabel(("A assinatura <b>visível</b> será colocada na área que você selecionou."
                       if visible else "A assinatura será <b>invisível</b> (sem carimbo na página).")
                      + " O arquivo original não é alterado. Depois de assinado, qualquer edição "
                        "no PDF invalida a assinatura.")
        info.setWordWrap(True)
        info.setObjectName("Muted")
        lay.addWidget(info)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        bb.addButton("Assinar", QDialogButtonBox.AcceptRole).setDefault(True)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _browse_a1(self):
        f, _ = QFileDialog.getOpenFileName(self, "Certificado A1", self.a1_path.text(),
                                           "Certificado (*.pfx *.p12)")
        if f:
            self.a1_path.setText(f)

    def _browse_driver(self):
        f, _ = QFileDialog.getOpenFileName(self, "Driver PKCS#11 do token", r"C:\Windows\System32",
                                           "Biblioteca (*.dll *.so *.dylib)")
        if f:
            self.a3_driver.setEditText(f)

    def _browse_out(self):
        f, _ = QFileDialog.getSaveFileName(self, "Salvar PDF assinado", self.out_path.text(), "PDF (*.pdf)")
        if f:
            self.out_path.setText(f)

    def _driver(self):
        data = self.a3_driver.currentData()
        text = self.a3_driver.currentText()
        return data if data and data in text else text.split(" — ")[-1].strip()

    def _load_cert(self):
        try:
            if self.rb_a1.isChecked():
                _signer, info = sig.load_a1(self.a1_path.text(), self.a1_pass.text())
                self._show_info(info)
            else:
                drv = self._driver()
                if not drv or not os.path.isfile(drv):
                    raise FileNotFoundError("Driver do token não encontrado. Instale o software do "
                                            "fabricante do token ou indique o arquivo .dll.")

                def done(certs):
                    self.a3_certs = certs
                    self.a3_cert.clear()
                    for cinfo in certs:
                        self.a3_cert.addItem(f"{cinfo['info'].nome} ({cinfo['label']})", cinfo)
                    if certs:
                        self._show_info(certs[0]["info"])
                    else:
                        self.cert_lbl.setText("Nenhum certificado encontrado no token.")
                run_task(self, "Lendo o token...", sig.list_a3_certs, drv, self.a3_pin.text(), on_done=done)
        except Exception as e:
            from .i18n import friendly
            self.cert_ok = False
            self.cert_lbl.setText(f"<span style='color:{tc('accent_text')}'>⚠ {friendly(e)}</span>")

    def _show_info(self, info):
        self.cert_ok = not info.vencido
        color = tc("warn") if info.vencido else tc("ok")
        self.cert_lbl.setText(f"<span style='color:{color}'>✔ </span>" + info.resumo().replace("\n", "<br>"))

    def params(self) -> dict:
        p = dict(reason=self.reason.currentText().strip(), location=self.location.text().strip(),
                 contact=self.contact.text().strip(),
                 tsa_url=(self.tsa.currentData() or self.tsa.currentText().split(" — ")[-1].strip())
                 if self.use_tsa.isChecked() else None)
        if self.rb_a1.isChecked():
            p.update(a1_path=self.a1_path.text(), a1_password=self.a1_pass.text())
        else:
            cur = self.a3_cert.currentData() or {}
            p.update(a3_lib=self._driver(), a3_pin=self.a3_pin.text(), a3_token=cur.get("token"),
                     a3_cert_label=cur.get("label"))
        return p

    def _accept(self):
        if self.rb_a1.isChecked() and not self.a1_path.text():
            QMessageBox.warning(self, APP_NAME, "Escolha o arquivo do certificado A1.")
            return
        if self.rb_a3.isChecked() and not self.a3_cert.currentData():
            QMessageBox.warning(self, APP_NAME, "Clique em “Ler certificado” e escolha o certificado do token.")
            return
        if os.path.abspath(self.out_path.text()) == os.path.abspath(self.pdf_path):
            QMessageBox.warning(self, APP_NAME, "Escolha um nome diferente do arquivo original.")
            return
        st = settings()
        st.setValue("sign_type", "a1" if self.rb_a1.isChecked() else "a3")
        st.setValue("sign_a1_path", self.a1_path.text())
        st.setValue("sign_a3_driver", self._driver() if self.rb_a3.isChecked() else st.value("sign_a3_driver", ""))
        st.setValue("sign_reason", self.reason.currentText())
        st.setValue("sign_location", self.location.text())
        st.setValue("sign_contact", self.contact.text())
        st.setValue("sign_tsa", self.use_tsa.isChecked())
        self.accept()


class VerifyDialog(QDialog):
    def __init__(self, parent, path, results: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Assinaturas digitais do documento")
        self.resize(900, 360)
        lay = QVBoxLayout(self)
        if not results:
            lay.addWidget(QLabel("Este documento não possui assinaturas digitais."))
        else:
            lay.addWidget(QLabel(f"<b>{len(results)}</b> assinatura(s) em {Path(path).name}"))
            t = QTableWidget(len(results), 6)
            t.setHorizontalHeaderLabels(["Signatário", "CPF/CNPJ", "Data", "Integridade",
                                         "Documento alterado depois?", "Certificado confiável"])
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            for r, s in enumerate(results):
                integ = "✔ Íntegra e válida" if s["integra"] and s["valida"] else "✖ Inválida/adulterada"
                after = "Não" if s["cobre_documento_todo"] else "Sim — houve alterações após assinar"
                trust = "✔ Sim (cadeia reconhecida)" if s["confiavel"] else "⚠ Não verificado"
                vals = [s["signatario"], s.get("cpf") or s.get("cnpj") or "", s["data"] or "—", integ, after, trust]
                for col, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    if col == 3:
                        it.setForeground(Qt.GlobalColor.darkGreen if "✔" in v else Qt.GlobalColor.red)
                    it.setToolTip(s.get("detalhes", "") + (f"\nEmissor: {s.get('emissor', '')}" if s.get("emissor") else ""))
                    t.setItem(r, col, it)
            t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            t.horizontalHeader().setStretchLastSection(True)
            lay.addWidget(t)
            note = QLabel("“Certificado confiável” usa as autoridades certificadoras instaladas no Windows. "
                          "Para validar a cadeia ICP-Brasil, instale as cadeias do ITI "
                          "(gov.br/iti) ou confira no Verificador oficial: validar.iti.gov.br")
            note.setWordWrap(True)
            note.setObjectName("Muted")
            lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)



# ====================================================================== novo PDF
class NewPdfDialog(QDialog):
    def __init__(self, parent=None):
        from .document import BACKGROUNDS, PAGE_SIZES
        super().__init__(parent)
        self.setWindowTitle("Novo PDF")
        self.setMinimumWidth(460)
        st = settings()
        lay = QVBoxLayout(self)
        intro = QLabel("Crie um documento em branco e depois use as ferramentas para adicionar "
                       "texto, imagens, formas, desenhos e assinaturas.")
        intro.setWordWrap(True)
        intro.setObjectName("Muted")
        lay.addWidget(intro)
        form = QFormLayout()
        self.title = QLineEdit()
        self.title.setPlaceholderText("opcional")
        form.addRow("Título:", self.title)
        self.size = QComboBox()
        for name, wh in PAGE_SIZES.items():
            self.size.addItem(name, wh)
        self.size.addItem("Personalizado (mm)...", None)
        self.size.setCurrentIndex(max(0, self.size.findText(st.value("new_size", "A4 (210 × 297 mm)"))))
        form.addRow("Tamanho:", self.size)
        cust = QHBoxLayout()
        from PySide6.QtWidgets import QDoubleSpinBox
        self.cw = QDoubleSpinBox(minimum=20, maximum=5000, value=210, suffix=" mm", decimals=0)
        self.ch = QDoubleSpinBox(minimum=20, maximum=5000, value=297, suffix=" mm", decimals=0)
        cust.addWidget(self.cw)
        cust.addWidget(QLabel("×"))
        cust.addWidget(self.ch)
        self.cust_w = QWidget()
        self.cust_w.setLayout(cust)
        form.addRow("", self.cust_w)
        self.orient = QComboBox()
        self.orient.addItems(["Retrato", "Paisagem"])
        form.addRow("Orientação:", self.orient)
        from PySide6.QtWidgets import QSpinBox
        self.pages = QSpinBox(minimum=1, maximum=500, value=1)
        form.addRow("Páginas:", self.pages)
        self.bg = QComboBox()
        for key, name in BACKGROUNDS.items():
            self.bg.addItem(name, key)
        form.addRow("Fundo:", self.bg)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        bb.addButton("Criar", QDialogButtonBox.AcceptRole).setDefault(True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.size.currentIndexChanged.connect(lambda _i: self.cust_w.setVisible(self.size.currentData() is None))
        self.cust_w.setVisible(self.size.currentData() is None)

    def values(self):
        wh = self.size.currentData()
        if wh is None:
            wh = (self.cw.value() * 72 / 25.4, self.ch.value() * 72 / 25.4)
        else:
            settings().setValue("new_size", self.size.currentText())
        w, h = min(wh), max(wh)
        if self.orient.currentIndex() == 1:
            w, h = h, w
        return dict(width=w, height=h, pages=self.pages.value(), background=self.bg.currentData(),
                    title=self.title.text().strip())
