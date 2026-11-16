"""Janela "Atualização disponível" e verificação automática em segundo plano."""
from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QProgressBar, QTextBrowser, QVBoxLayout,
)

from . import APP_NAME, __version__
from . import updater as up


class _Relay(QObject):
    """Leva resultados da thread de trabalho para a thread da interface."""
    done = Signal(object)
    failed = Signal(str, str)
    progress = Signal(object, object)


def check_async(on_result, on_error=None):
    """Consulta a última versão sem travar a interface. on_result(UpdateInfo)."""
    relay = _Relay()
    _KEEP.add(relay)  # mantido vivo até o resultado chegar na thread da interface

    def ok(info):
        _KEEP.discard(relay)
        on_result(info)

    def err(msg, _tb):
        _KEEP.discard(relay)
        if on_error:
            on_error(msg)

    relay.done.connect(ok, Qt.QueuedConnection)
    relay.failed.connect(err, Qt.QueuedConnection)

    def target():
        try:
            relay.done.emit(up.fetch_latest())
        except Exception as e:
            relay.failed.emit(str(e), traceback.format_exc())

    threading.Thread(target=target, name="vorticis-update-check", daemon=True).start()


_KEEP: set = set()


class UpdateDialog(QDialog):
    """Mostra a versão nova e as novidades; 'Atualizar agora' baixa, confere e deixa pronto.
    Depois que exec() retorna Accepted, o chamador fecha o programa e chama
    updater.launch(dlg.kind, dlg.prepared)."""

    def __init__(self, parent, info: up.UpdateInfo):
        super().__init__(parent)
        self.info = info
        self.kind = up.install_kind()
        self.prepared = None
        self._cancel = False
        self._busy = False
        self.setWindowTitle(f"{APP_NAME} — atualização")
        self.resize(620, 480)
        lay = QVBoxLayout(self)
        head = QLabel(f"<h3>Versão {info.version} disponível</h3>"
                      f"<span>Você está usando a versão {__version__}.</span>")
        head.setTextFormat(Qt.RichText)
        lay.addWidget(head)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(info.notes or "Sem notas para esta versão.")
        lay.addWidget(notes, 1)
        how = {
            "installer": "O instalador novo é baixado e executado sem perguntas. As configurações e o "
                         "histórico são mantidos e o programa abre de novo ao terminar.",
            "portable": "A versão portátil nova é baixada e copiada por cima desta pasta. A pasta "
                        "'dados' (configurações e histórico) é mantida e o programa abre de novo ao terminar.",
            "source": "Esta cópia não foi instalada pelo instalador nem é a versão portátil, então a "
                      "página de download será aberta no navegador.",
        }[self.kind]
        tip = QLabel(how + ("\n\nAntes de instalar, o programa fecha. Documentos com alterações "
                            "não salvas serão oferecidos para salvar." if self.kind != "source" else ""))
        tip.setWordWrap(True)
        tip.setObjectName("Muted")
        lay.addWidget(tip)
        row = QHBoxLayout()
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.hide()
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        row.addWidget(self.bar, 1)
        row.addWidget(self.status)
        lay.addLayout(row)
        self.buttons = QDialogButtonBox()
        self.go = self.buttons.addButton("Atualizar agora" if self.kind != "source" else "Abrir página de download",
                                         QDialogButtonBox.AcceptRole)
        self.go.setObjectName("Primary")
        self.go.setDefault(True)
        self.later = self.buttons.addButton("Agora não", QDialogButtonBox.RejectRole)
        self.go.clicked.connect(self._start)
        self.later.clicked.connect(self.reject)
        lay.addWidget(self.buttons)

    def _start(self):
        if self.kind == "source":
            up.open_download_page(self.info)
            self.reject()
            return
        if self._busy:
            return
        self._busy, self._cancel = True, False
        self.go.setEnabled(False)
        self.later.setText("Cancelar")
        self.bar.setRange(0, 0)
        self.bar.show()
        self.status.setText("Baixando…")
        relay = _Relay(self)
        relay.progress.connect(self._progress, Qt.QueuedConnection)
        relay.done.connect(self._done, Qt.QueuedConnection)
        relay.failed.connect(self._failed, Qt.QueuedConnection)
        info, kind = self.info, self.kind

        def target():
            try:
                res = up.prepare(info, kind, progress=lambda d, t: relay.progress.emit(d, t),
                                 cancelled=lambda: self._cancel)
                relay.done.emit(res)
            except up.Cancelled:
                relay.failed.emit("", "")
            except Exception as e:
                relay.failed.emit(str(e), traceback.format_exc())

        threading.Thread(target=target, name="vorticis-update-download", daemon=True).start()

    @Slot(object, object)
    def _progress(self, done, total):
        mb = done / 1048576
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
            self.status.setText(f"{mb:.1f} de {total / 1048576:.1f} MB")
        else:
            self.status.setText(f"{mb:.1f} MB")

    @Slot(object)
    def _done(self, path):
        self._busy = False
        self.prepared = path
        self.status.setText("Pronto para instalar")
        self.accept()

    @Slot(str, str)
    def _failed(self, msg, tb):
        self._busy = False
        self.go.setEnabled(True)
        self.later.setText("Agora não")
        self.bar.hide()
        if not msg:  # cancelado
            self.status.setText("Download cancelado")
            return
        from .config import log_error
        log_error("Atualização", tb)
        self.status.setText("")
        from PySide6.QtWidgets import QMessageBox
        from .i18n import friendly
        QMessageBox.warning(self, APP_NAME, f"Não foi possível baixar a atualização:\n{friendly(msg)}\n\n"
                                            "Você também pode baixá-la manualmente na página de versões.")

    def reject(self):
        if self._busy:  # "Cancelar" durante o download
            self._cancel = True
            self.status.setText("Cancelando…")
            return
        super().reject()

    def closeEvent(self, e):
        if self._busy:
            self._cancel = True
            e.ignore()
            return
        super().closeEvent(e)
