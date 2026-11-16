"""Ponto de entrada: argumentos de linha de comando, instância única e janelas.

Exemplos (os mesmos usados pelo menu do botão direito do Explorer). As ações do menu
executam direto, sem abrir janela; só "Abrir" e "Organizar páginas" abrem o editor:
    VorticisPDF.exe arquivo.pdf
    VorticisPDF.exe --merge a.pdf b.pdf c.docx      -> a_unido.pdf
    VorticisPDF.exe --split=each a.pdf              (each|half|every2|every5|every10|oddeven)
    VorticisPDF.exe --organize a.pdf b.pdf
    VorticisPDF.exe --print a.pdf                   (impressora padrão, sem janela)
    VorticisPDF.exe --convert=xlsx a.pdf            (docx|xlsx|pptx|png|jpg|tiff|txt|html|md|odt|pdfa|pdf)
    VorticisPDF.exe --to-pdf planilha.xlsx
    VorticisPDF.exe --convert a.pdf                 (abre a janela de conversão)
    VorticisPDF.exe --register-shell | --unregister-shell
    VorticisPDF.exe --apply-update=<pasta> --wait-pid=<pid>   (uso interno: atualiza a versão portátil)
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
        if a.startswith(("--apply-update=", "--wait-pid=")):
            special = special if a.startswith("--wait-pid=") else "--apply-update"
        elif a in ACTIONS:
            action = ACTIONS[a]
        elif a.startswith(("--convert=", "--split=")):  # submenus: --convert=xlsx, --split=half
            name, _, value = a[2:].partition("=")
            action = f"{name}:{value}"
        elif a in ("--register-shell", "--unregister-shell", "--selftest", "--full-menu-on",
                   "--full-menu-off"):
            special = a
        elif a and not a.startswith("--") and a != "%1":
            files.append(os.path.abspath(a))
    return action, files, special


class Controller:
    def __init__(self, app):
        from .single_instance import InstanceServer
        self.app = app
        self.windows = []
        self.dialogs = []
        self.jobs = set()
        self.server = InstanceServer()
        self.server.request.connect(self.handle)
        self.update_info = None  # última versão encontrada, se for mais nova

    # ---------------- abas ou janelas ----------------
    def tabs_enabled(self) -> bool:
        """True: arquivos novos abrem em abas na mesma janela (padrão); False: uma janela por arquivo."""
        from .config import settings
        from .updater import _bool
        return _bool(settings().value("open_in_tabs"), True)

    def set_tabs_enabled(self, on: bool):
        from .config import settings
        settings().setValue("open_in_tabs", bool(on))
        for w in self.windows:
            w.tabs_mode_changed(bool(on))

    def window_activated(self, w):
        """A última janela usada fica no fim da lista: é nela que os arquivos novos abrem."""
        if w in self.windows and self.windows[-1] is not w:
            self.windows.remove(w)
            self.windows.append(w)

    def find_open(self, path):
        """(janela, aba) onde o arquivo já está aberto, ou None."""
        norm = os.path.normcase(os.path.abspath(path))
        for w in self.windows:
            i = w.tab_index_of(norm)
            if i is not None:
                return w, i
        return None

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
        from .tasks import wait_all
        wait_all()
        self.app.quit()

    def _target_window(self, prefer=None):
        if prefer is not None and prefer.is_empty():
            return prefer
        if self.tabs_enabled():  # abre como nova aba na janela usada por último
            if prefer is not None and prefer in self.windows:
                return prefer
            return self.windows[-1] if self.windows else self.new_window()
        for w in self.windows:
            if w.is_empty():
                return w
        return self.new_window()

    def open_files(self, files, prefer=None, organize=False):
        for f in [f for f in files if f]:
            found = self.find_open(f)
            if found and not organize:  # já está aberto: só mostra a aba
                w, i = found
                w.activate_tab(i)
            else:
                w = self._target_window(prefer)
                w.load(f, organize=organize, new_tab=not w.is_empty())
            if self.tabs_enabled():
                prefer = w  # os demais arquivos selecionados vão para a mesma janela
            else:
                prefer = None
            w.raise_()
            w.activateWindow()

    def show_document(self, pdoc, prefer=None):
        """Mostra um documento novo (criado, convertido, traduzido...) numa aba ou janela,
        conforme a preferência. Retorna a janela usada."""
        w = self._target_window(prefer)
        if w.is_empty():
            w.set_document(pdoc)
        else:
            w.open_in_new_tab(pdoc)
        w.raise_()
        w.activateWindow()
        return w

    # ---------------- atualizações ----------------
    def check_updates_later(self):
        """Verificação automática (no máximo uma vez por dia), sem atrapalhar o uso."""
        from PySide6.QtCore import QTimer
        from . import updater as up
        QTimer.singleShot(30000, up.cleanup_old)
        if not up.due_for_check():
            return
        from .update_dialog import check_async

        def result(info):
            up.mark_checked()
            if info.newer:
                self.update_available(info)
        QTimer.singleShot(6000, lambda: check_async(result))

    def update_available(self, info):
        self.update_info = info
        for w in self.windows:
            w.show_update_badge(info)

    def install_update(self, kind, prepared):
        """Fecha todas as janelas (oferecendo salvar) e inicia a instalação."""
        from . import updater as up
        for w in list(self.windows):
            if not w.close():
                return False
        from .tasks import wait_all
        wait_all()
        up.launch(kind, prepared)
        self.app.quit()
        return True

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
        self._maybe_quit()

    def _maybe_quit(self):
        if not self.dialogs and not self.windows and not self.jobs:
            self.app.quit()

    # ---------------- ações diretas (sem janela) ----------------
    def run_silent(self, label, fn, *args):
        """Executa em segundo plano, sem janela. Sucesso: nada aparece (só na barra de status,
        se o editor estiver aberto). Erro: mensagem e registro de erros."""
        import threading
        import traceback
        from .tasks import PDF_LOCK
        from .tasks import SilentRelay
        relay = SilentRelay(self, label)
        self.jobs.add(relay)

        def target():
            try:
                with PDF_LOCK:
                    res = fn(*args)
                relay.done.emit(res)
            except Exception as e:
                relay.failed.emit(str(e), traceback.format_exc())

        threading.Thread(target=target, name=f"vorticis-{label}", daemon=False).start()

    def job_finished(self, relay, result, error):
        self.jobs.discard(relay)
        if error:
            from PySide6.QtWidgets import QMessageBox
            from . import APP_NAME
            from .config import log_error
            from .i18n import friendly
            log_error(relay.label, error[1])
            QMessageBox.critical(None, APP_NAME, f"Não foi possível {relay.label}:\n{friendly(error[0])}")
        elif self.windows:
            n = len(result) if isinstance(result, list) else 1
            where = result if isinstance(result, str) else (Path(result[0]).parent if result else "")
            self.windows[-1].statusBar().showMessage(f"✔ {relay.label.capitalize()}: {n} arquivo(s) em {where}",
                                                     10000)
        self._maybe_quit()

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
        files = [f for f in files if f and os.path.isfile(f)]
        if not files:
            return
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
        w = self.show_document(pdoc)
        w._converted_name = str(Path(files[0]).with_name("organizado.pdf"))
        w.a_organize.setChecked(True)
        w.toggle_organize()

    def handle(self, action, files):
        from . import quick_actions as qa
        files = [f for f in files if f]
        name, _, value = action.partition(":")
        if name == "merge" and files:
            self.run_silent("unir os arquivos", qa.merge, files)
        elif name == "merge":
            self.merge(files)
        elif name == "split" and files:
            self.run_silent("separar", qa.split, files, value or "each")
        elif name == "organize":
            self.organize(files)
        elif name == "print" and files:
            self.run_silent("imprimir", qa.print_files, files)
        elif name == "convert" and value and files:
            self.run_silent("converter", qa.convert, files, value)
        elif name == "to_pdf" and files:
            self.run_silent("converter para PDF", qa.convert, files, "pdf")
        elif name == "convert":
            self.convert(files, to_pdf=False)
        elif name == "to_pdf":
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

    from .config import install_crash_handlers
    install_crash_handlers()

    if special == "--apply-update":  # versão portátil nova substituindo a antiga
        from .updater import apply_portable_update
        target = next(a.split("=", 1)[1] for a in argv if a.startswith("--apply-update="))
        pid = next((a.split("=", 1)[1] for a in argv if a.startswith("--wait-pid=")), "0")
        return apply_portable_update(target, int(pid) if pid.isdigit() else 0)
    if special == "--selftest":
        from .selftest import run
        return run()
    if special:
        from . import shell_integration as shell
        try:
            if special == "--register-shell":
                print(shell.register())
            elif special == "--unregister-shell":
                print(shell.unregister())
                print(shell.disable_full_menu(only_if_ours=True, restart=False))
            elif special == "--full-menu-on":
                print(shell.enable_full_menu(restart="--no-restart" not in argv))
            else:
                print(shell.disable_full_menu(restart="--no-restart" not in argv))
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
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME
    from .fonts import catalog
    from .single_instance import send_to_running

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Vorticis")
    from .config import app_icon
    app.setWindowIcon(app_icon())
    from . import i18n, theme
    i18n.install(app)
    theme.apply(app)

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
        ctrl.check_updates_later()
    else:
        ctrl.server.add(action, files)  # aguarda os demais arquivos selecionados chegarem
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
