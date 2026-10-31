"""Caminhos, recursos e histórico de salvamentos."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import APP_NAME


def app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_path(name: str) -> str:
    """Funciona tanto rodando do código-fonte quanto empacotado com PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    p = base / "vorticis_pdf" / "resources" / name
    if not p.exists():
        p = Path(__file__).resolve().parent / "resources" / name
    return str(p)


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
