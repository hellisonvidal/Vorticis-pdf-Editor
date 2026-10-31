"""Ponto de entrada: argumentos de linha de comando, instância única e janelas.

Exemplos (os mesmos usados pelo menu do botão direito do Explorer):
    VorticisPDF.exe arquivo.pdf
    VorticisPDF.exe --merge a.pdf b.pdf c.docx
    VorticisPDF.exe --split a.pdf
    VorticisPDF.exe --organize a.pdf b.pdf
    VorticisPDF.exe --print a.pdf
    VorticisPDF.exe --convert a.pdf        (PDF -> Word/Excel/...)
    VorticisPDF.exe --to-pdf planilha.xlsx (Office/imagens -> PDF)
    VorticisPDF.exe --register-shell | --unregister-shell
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ACTIONS = {"--open": "open", "--merge": "merge", "--split": "split", "--organize": "organize",
           "--print": "print", "--convert": "convert", "--to-pdf": "to_pdf"}


def parse_args(argv):
    action, files, special = "open", [], None
    for a in argv:
        if a in ACTIONS:
            action = ACTIONS[a]
        elif a in ("--register-shell", "--unregister-shell"):
            special = a
        elif not a.startswith("--"):
            files.append(os.path.abspath(a))
    return action, files, special


class Controller:
    def __init__(self, app):
        from .single_instance import InstanceServer
        self.app = app
        self.windows = []
        self.dialogs = []
        self.server = InstanceServer()
        self.server.request.connect(self.handle)

    # ---------------- janelas ----------------
    def new_window(self, pdoc=None):
        from .main_window import MainWindow
        w = MainWindow(self, pdoc)
        if self.windows:
            last = self.windows[-1]
            w.move(last.x() + 30, last.y() + 30)
        self.windows.append(w)
        w.show()
        w.raise_()
        w.activateWindow()
        return w

    def window_closed(self, w):
        if w in self.windows:
            self.windows.remove(w)

    def quit(self):
        for w in list(self.windows):
            if not w.close():
                return
        self.app.quit()

    def _target_window(self, prefer=None):
        if prefer is not None and prefer.is_empty():
            return prefer
        for w in self.windows:
            if w.is_empty():
                return w
        return self.new_window()

    def open_files(self, files, prefer=None, organize=False):
        for f in files:
            w = self._target_window(prefer)
            prefer = None
            w.load(f, organize=organize)
            w.raise_()
            w.activateWindow()

    def _dialog(self, dlg):
        """Diálogos independentes (abertos pelo Explorer sem janela principal)."""
        self.dialogs.append(dlg)
        dlg.finished.connect(lambda _r: self._dialog_done(dlg))
        if hasattr(dlg, "opened"):
            dlg.opened.connect(lambda p: self.open_files([p]))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _dialog_done(self, dlg):
        if dlg in self.dialogs:
            self.dialogs.remove(dlg)
        if not self.dialogs and not self.windows:
            self.app.quit()

    # ---------------- ações ----------------
    def merge(self, files):
        from .dialogs import MergeDialog
        self._dialog(MergeDialog(None, files))

    def split(self, files):
        from .dialogs import SplitDialog
        self._dialog(SplitDialog(None, files))

    def convert(self, files, to_pdf=None):
        from .dialogs import ConvertDialog
        self._dialog(ConvertDialog(None, files, to_pdf))

    def organize(self, files):
        if len(files) <= 1:
            self.open_files(files, organize=True)
            return
        # vários arquivos: junta em memória para organizar as páginas de todos juntos
        from .document import PdfDocument, open_any
        import pymupdf
        out = pymupdf.open()
        toc = []
        for f in files:
            try:
                src = open_any(f)
            except Exception:
                continue
            toc.append([1, Path(f).stem, out.page_count + 1])
            out.insert_pdf(src)
            src.close()
        out.set_toc(toc)
        pdoc = PdfDocument(doc=out)
        pdoc.modified = True
        pdoc.edits.append(f"Combinou {len(files)} arquivos para organizar")
        w = self._target_window()
        w.set_document(pdoc)
        w._converted_name = str(Path(files[0]).with_name("organizado.pdf"))
        w.a_organize.setChecked(True)
        w.toggle_organize()

    def print_files(self, files):
        from .printing import print_document
        from .document import open_any
        for f in files:
            doc = open_any(f)
            print_document(None, doc)
        if not self.windows:
            self.app.quit()

    def handle(self, action, files):
        if action == "merge":
            self.merge(files)
        elif action == "split":
            self.split(files)
        elif action == "organize":
            self.organize(files)
        elif action == "print":
            self.print_files(files)
        elif action == "convert":
            self.convert(files, to_pdf=False)
        elif action == "to_pdf":
            self.convert(files, to_pdf=True)
        else:
            if files:
                self.open_files(files)
            elif not self.windows:
                self.new_window()
            else:
                self.windows[-1].raise_()
                self.windows[-1].activateWindow()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    action, files, special = parse_args(argv)

    if special:
        from . import shell_integration as shell
        try:
            print(shell.register() if special == "--register-shell" else shell.unregister())
            return 0
        except Exception as e:
            print(e)
            return 1

    if sys.platform.startswith("win"):
        try:
            import ctypes
            from . import APP_ID
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME
    from .config import resource_path
    from .fonts import catalog
    from .single_instance import send_to_running

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Vorticis")
    app.setWindowIcon(QIcon(resource_path("icon.ico")))
    app.setStyle("Fusion")

    # já existe uma instância? repassa os arquivos e sai (Explorer abre 1 processo por arquivo)
    if send_to_running(action, files):
        return 0

    catalog.load_async()  # varre as fontes do sistema em segundo plano
    ctrl = Controller(app)
    app.setQuitOnLastWindowClosed(False)
    app.lastWindowClosed.connect(lambda: QTimer.singleShot(
        200, lambda: app.quit() if not ctrl.windows and not ctrl.dialogs else None))
    if action == "open":
        ctrl.handle("open", files)
    else:
        ctrl.server.add(action, files)  # aguarda os demais arquivos selecionados chegarem
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
