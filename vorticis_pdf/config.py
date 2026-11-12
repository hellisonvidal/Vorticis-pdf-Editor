"""Caminhos, configurações, recursos, registro de erros e histórico de salvamentos.

Modo portátil: se existir o arquivo 'portable.txt' ao lado do executável, todas as
configurações, histórico e cache ficam na pasta 'dados' ao lado do programa (nada é
gravado no computador). A versão portátil já vem com esse arquivo.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path

from . import APP_NAME


def exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_portable() -> bool:
    return (exe_dir() / "portable.txt").exists()


def app_data_dir() -> Path:
    if is_portable():
        d = exe_dir() / "dados"
    elif sys.platform.startswith("win"):
        d = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    else:
        d = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:  # pasta somente leitura (ex.: pendrive protegido): usa a pasta temporária
        import tempfile
        d = Path(tempfile.gettempdir()) / APP_NAME
        d.mkdir(parents=True, exist_ok=True)
    return d


def settings():
    from PySide6.QtCore import QSettings
    if is_portable():
        return QSettings(str(app_data_dir() / "configuracoes.ini"), QSettings.IniFormat)
    return QSettings("Vorticis", "PDFEditor")


def resource_path(name: str) -> str:
    """Funciona tanto rodando do código-fonte quanto empacotado com PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    p = base / "vorticis_pdf" / "resources" / name
    if not p.exists():
        p = Path(__file__).resolve().parent / "resources" / name
    return str(p)


# ------------------------------------------------------------------ registro de erros
LOG_FILE = "vorticis_erros.log"
_fault_file = None


def log_path() -> Path:
    return app_data_dir() / LOG_FILE


def log_error(title: str, details: str = ""):
    try:
        p = log_path()
        if p.exists() and p.stat().st_size > 2_000_000:
            p.write_text("", "utf-8")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"\n[{now_str()}] {title}\n{details}\n")
    except OSError:
        pass


def install_crash_handlers():
    """Grava falhas (inclusive falhas nativas do Qt/MuPDF) em vorticis_erros.log e mostra
    uma mensagem em vez de fechar o programa silenciosamente."""
    global _fault_file
    # no executável sem console, stdout/stderr são None: bibliotecas que imprimem quebrariam
    if sys.stdout is None or sys.stderr is None:
        sink = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or sink
        sys.stderr = sys.stderr or sink
    try:
        import faulthandler
        _fault_file = open(log_path(), "a", encoding="utf-8")
        faulthandler.enable(_fault_file, all_threads=True)
    except Exception:
        pass

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log_error("Erro não tratado", text)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(None, APP_NAME,
                                     f"Ocorreu um erro inesperado, mas o programa continua aberto.\n\n"
                                     f"{exc}\n\nDetalhes gravados em:\n{log_path()}")
        except Exception:
            pass

    sys.excepthook = hook

    import threading

    def thook(args):
        hook(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = thook


# ------------------------------------------------------------------ histórico
HISTORY_FILE = "historico_salvamentos.jsonl"


def log_save(info: dict):
    """Acrescenta um registro ao histórico de salvamentos (um JSON por linha)."""
    try:
        with open(app_data_dir() / HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(info, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_history(limit: int = 200) -> list[dict]:
    try:
        lines = (app_data_dir() / HISTORY_FILE).read_text("utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return list(reversed(out))


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def now_str() -> str:
    return dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def documents_dir() -> Path:
    """Pasta Documentos do usuário (onde vão os PDFs novos que ainda não têm arquivo)."""
    try:
        from PySide6.QtCore import QStandardPaths
        d = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if d:
            return Path(d)
    except Exception:
        pass
    return Path.home()


def unique_path(path) -> str:
    """Caminho livre: 'nome.pdf', 'nome (2).pdf', 'nome (3).pdf'... (nunca apaga um arquivo existente)."""
    p = Path(path)
    if not p.exists():
        return str(p)
    n = 2
    while True:
        cand = p.with_name(f"{p.stem} ({n}){p.suffix}")
        if not cand.exists():
            return str(cand)
        n += 1


def app_icon():
    """Ícone da janela/barra de tarefas: o .ico e também PNGs em vários tamanhos (PNG não
    depende do plug-in de imagens .ico do Qt, então o ícone aparece mesmo se ele faltar)."""
    from PySide6.QtGui import QIcon
    ic = QIcon(resource_path("icon.ico"))
    for s in (16, 24, 32, 48, 64, 128):
        p = resource_path(f"icon_{s}.png")
        if os.path.exists(p):
            ic.addFile(p)
    ic.addFile(resource_path("icon.png"))
    return ic
