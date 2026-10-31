"""Execução de tarefas demoradas em segundo plano, com segurança.

Regras que evitam travamentos:
  * O resultado e os erros voltam para a thread da interface por sinais *enfileirados*
    (um QObject que vive na thread principal recebe os sinais). Janelas e diálogos
    nunca são criados na thread de trabalho.
  * A thread não pertence ao diálogo que a iniciou: fica registrada em _RUNNING até
    terminar, então fechar/destruir o diálogo não destrói uma QThread em execução.
  * O PyMuPDF não suporta uso simultâneo em várias threads. PDF_LOCK é mantido durante
    toda a tarefa e a renderização da interface (páginas/miniaturas) espera o lock ficar livre.
"""
from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from . import APP_NAME
from .config import log_error

PDF_LOCK = threading.RLock()
_RUNNING: set = set()


class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(str, str)
    progress = Signal(int, int)

    def __init__(self, fn, args, kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs

    @Slot()
    def run(self):
        try:
            if "progress" in self.kwargs:
                self.kwargs["progress"] = lambda i, n: self.progress.emit(i, n)
            with PDF_LOCK:
                result = self.fn(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.failed.emit(str(e), traceback.format_exc())


class _Relay(QObject):
    """Vive na thread principal; os slots rodam sempre na thread da interface."""

    def __init__(self, dlg, on_done, on_error, parent_widget):
        super().__init__()
        self.dlg, self.on_done, self.on_error, self.parent_widget = dlg, on_done, on_error, parent_widget

    @Slot(int, int)
    def progress(self, i, n):
        self.dlg.setMaximum(n)
        self.dlg.setValue(i)

    @Slot(object)
    def done(self, result):
        self.dlg.close()
        if self.on_done:
            try:
                self.on_done(result)
            except Exception as e:
                log_error("Erro ao concluir tarefa", traceback.format_exc())
                QMessageBox.critical(self.parent_widget, APP_NAME, f"Falha: {e}")

    @Slot(str, str)
    def fail(self, msg, tb):
        self.dlg.close()
        log_error("Erro em tarefa", tb)
        if self.on_error:
            self.on_error(msg)
        else:
            QMessageBox.critical(self.parent_widget, APP_NAME, f"Falha: {msg}")


def run_task(parent, label, fn, *args, on_done=None, on_error=None, with_progress=False, **kwargs):
    """Executa fn(*args, **kwargs) em segundo plano; on_done(resultado) roda na interface."""
    app = QApplication.instance()
    dlg = QProgressDialog(label, None, 0, 0, parent)
    dlg.setWindowTitle(APP_NAME)
    dlg.setWindowModality(Qt.ApplicationModal)  # evita outras ações enquanto o PDF é processado
    dlg.setMinimumDuration(250)
    dlg.setCancelButton(None)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    if with_progress:
        kwargs["progress"] = None

    thread = QThread()  # sem pai: não é destruída junto com o diálogo
    worker = _Worker(fn, args, kwargs)
    worker.moveToThread(thread)
    relay = _Relay(dlg, on_done, on_error, parent)
    relay.moveToThread(app.thread())

    worker.progress.connect(relay.progress, Qt.QueuedConnection)
    worker.finished.connect(relay.done, Qt.QueuedConnection)
    worker.failed.connect(relay.fail, Qt.QueuedConnection)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.started.connect(worker.run)

    entry = (thread, worker, relay)
    _RUNNING.add(entry)

    def cleanup():
        _RUNNING.discard(entry)
        worker.deleteLater()
        thread.deleteLater()

    thread.finished.connect(cleanup)
    thread.start()
    return thread


def wait_all(timeout_ms=30000):
    """Aguarda tarefas pendentes (usado ao sair do programa)."""
    for thread, _w, _r in list(_RUNNING):
        thread.wait(timeout_ms)
