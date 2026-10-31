"""Instância única: o Explorer abre um processo por arquivo selecionado; os processos
seguintes repassam seus arquivos para o primeiro, que os agrupa por ação e executa uma
única vez (ex.: 'Unir PDFs selecionados' com 10 arquivos abre UMA janela de união)."""
from __future__ import annotations

import getpass
import json

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "VorticisPDFEditor-" + "".join(c for c in getpass.getuser() if c.isalnum())
GATHER_MS = 700


def send_to_running(action: str, files: list[str]) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps({"action": action, "files": files}).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


class InstanceServer(QObject):
    request = Signal(str, list)  # ação, arquivos (já agrupados)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        QLocalServer.removeServer(SERVER_NAME)
        self.server.listen(SERVER_NAME)
        self.server.newConnection.connect(self._on_conn)
        self.pending: dict[str, list[str]] = {}
        self.timer = QTimer(self, singleShot=True, interval=GATHER_MS)
        self.timer.timeout.connect(self._flush)

    def add(self, action: str, files: list[str]):
        lst = self.pending.setdefault(action, [])
        for f in files:
            if f not in lst:
                lst.append(f)
        self.timer.start()

    def _on_conn(self):
        sock = self.server.nextPendingConnection()
        buf = bytearray()

        def read():
            buf.extend(bytes(sock.readAll()))

        def done():
            read()
            try:
                msg = json.loads(buf.decode("utf-8"))
                self.add(msg.get("action", "open"), msg.get("files", []))
            except ValueError:
                pass
            sock.deleteLater()

        sock.readyRead.connect(read)
        sock.disconnected.connect(done)

    def _flush(self):
        pending, self.pending = self.pending, {}
        for action, files in pending.items():
            # arquivos chegam na ordem de inicialização dos processos; ordena por nome
            self.request.emit(action, sorted(files, key=lambda p: p.lower()))
