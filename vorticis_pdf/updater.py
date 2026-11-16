"""Atualização pelo próprio programa.

Consulta a última versão publicada nas Releases do GitHub, baixa o arquivo certo para
o tipo de instalação, confere a soma SHA-256 publicada junto (SHA256SUMS.txt) e instala:

  * instalado: executa o instalador novo em modo silencioso (/SILENT). O Inno Setup usa
    o mesmo modo da instalação anterior (só para o usuário ou para todos) e abre o
    programa de novo no fim (/RELAUNCH=1);
  * portátil: descompacta a versão nova numa pasta temporária e a executa com
    --apply-update=<pasta do programa>. Ela espera esta janela fechar, copia os próprios
    arquivos por cima da pasta antiga (a pasta 'dados', com configurações e histórico,
    é mantida) e abre o programa atualizado;
  * código-fonte (python vorticis.py) ou fora do Windows: abre a página de download.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

REPO = "hellisonvidal/Vorticis-pdf-Editor"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
TEMP_PREFIX = "VorticisPDF-update-"
EXE_NAME = "VorticisPDF.exe"
CHECK_EVERY_S = 24 * 3600
_UA = f"VorticisPDF/{__version__}"


class UpdateError(Exception):
    pass


class Cancelled(Exception):
    pass


# ------------------------------------------------------------------ versões
def parse_version(text: str) -> tuple[int, ...]:
    """'v1.10.2' -> (1, 10, 2). Partes não numéricas (ex.: '-beta') são ignoradas."""
    nums = re.findall(r"\d+", (text or "").split("-")[0].split("+")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


@dataclass
class UpdateInfo:
    version: str
    notes: str = ""
    page_url: str = RELEASES_PAGE
    assets: dict = field(default_factory=dict)  # nome do arquivo -> url de download

    def asset(self, kind: str) -> tuple[str, str] | None:
        """(nome, url) do instalador ('installer') ou do zip portátil ('portable')."""
        pat = {"installer": r"instalador.*\.exe$|setup.*\.exe$", "portable": r"port[aá]til.*\.zip$|portable.*\.zip$"}[kind]
        for name, url in self.assets.items():
            if re.search(pat, name, re.I):
                return name, url
        return None

    @property
    def newer(self) -> bool:
        return is_newer(self.version)


def _get(url: str, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_latest(timeout=20) -> UpdateInfo:
    try:
        with _get(API_LATEST, timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise UpdateError(f"não foi possível consultar as atualizações (verifique a internet): {e}") from e
    tag = data.get("tag_name") or data.get("name") or ""
    notes = data.get("body") or ""
    # as notas trazem a tabela de downloads e o histórico inteiro: mostra só a versão nova
    m = re.search(r"(##\s*Novidades.*?)(?=\n##\s*Novidades|\Z)", notes, re.S)
    assets = {a.get("name", ""): a.get("browser_download_url", "") for a in data.get("assets", [])}
    return UpdateInfo(version=tag.lstrip("vV"), notes=(m.group(1) if m else notes).strip(),
                      page_url=data.get("html_url") or RELEASES_PAGE, assets=assets)


# ------------------------------------------------------------------ tipo de instalação
def install_kind() -> str:
    """'installer' | 'portable' | 'source'."""
    from .config import exe_dir, is_portable
    if not getattr(sys, "frozen", False) or not sys.platform.startswith("win"):
        return "source"
    if is_portable():
        return "portable" if os.access(exe_dir(), os.W_OK) else "source"
    return "installer"


# ------------------------------------------------------------------ download
def _download(url: str, dest: Path, progress=None, cancelled=lambda: False):
    with _get(url, 60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                if cancelled():
                    raise Cancelled()
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if total and dest.stat().st_size != total:
        raise UpdateError("o download ficou incompleto; tente de novo")


def _expected_sha(info: UpdateInfo, name: str) -> str | None:
    url = info.assets.get("SHA256SUMS.txt")
    if not url:
        return None
    with _get(url, 30) as r:
        text = r.read().decode("utf-8", "replace")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name:
            return parts[0].lower()
    return None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare(info: UpdateInfo, kind: str, progress=None, cancelled=lambda: False) -> Path:
    """Baixa e confere a atualização (roda fora da thread da interface).
    Retorna o instalador (.exe) ou a pasta da versão portátil já descompactada."""
    asset = info.asset(kind)
    if asset is None:
        raise UpdateError("a versão nova não tem arquivo para este tipo de instalação")
    name, url = asset
    work = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
    dest = work / name
    _download(url, dest, progress, cancelled)
    try:
        sha = _expected_sha(info, name)
    except Exception:
        sha = None
    if sha and _sha256(dest) != sha:
        raise UpdateError("o arquivo baixado não confere com a soma SHA-256 publicada; tente de novo")
    if kind == "installer":
        return dest
    out = work / "nova"
    with zipfile.ZipFile(dest) as z:
        z.extractall(out)
    dest.unlink(missing_ok=True)
    exe = next(out.rglob(EXE_NAME), None)
    if exe is None:
        raise UpdateError(f"{EXE_NAME} não encontrado no arquivo baixado")
    return exe.parent


def _detached():
    if sys.platform.startswith("win"):
        return dict(creationflags=0x00000008 | 0x00000200, close_fds=True)  # DETACHED | NEW_GROUP
    return dict(start_new_session=True, close_fds=True)


def launch(kind: str, path: Path):
    """Inicia a instalação; o programa deve fechar logo em seguida."""
    from .config import exe_dir
    if kind == "installer":
        subprocess.Popen([str(path), "/SILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL",
                          "/CLOSEAPPLICATIONS", "/RELAUNCH=1"], cwd=str(path.parent), **_detached())
    else:
        subprocess.Popen([str(path / EXE_NAME), f"--apply-update={exe_dir()}", f"--wait-pid={os.getpid()}"],
                         cwd=str(path), **_detached())


def open_download_page(info: UpdateInfo | None = None):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    QDesktopServices.openUrl(QUrl(info.page_url if info else RELEASES_PAGE))


# ------------------------------------------------------------------ versão portátil
def _wait_pid(pid: int, timeout_s=120):
    if not pid:
        return
    if sys.platform.startswith("win"):
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if h:
            k.WaitForSingleObject(h, int(timeout_s * 1000))
            k.CloseHandle(h)
        return
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.3)


def _retry(fn, *args, tries=20):
    for i in range(tries):
        try:
            return fn(*args)
        except PermissionError:  # antivírus ou o programa antigo ainda liberando arquivos
            if i == tries - 1:
                raise
            time.sleep(0.5)


def copy_over(src: Path, dst: Path):
    """Copia a versão nova por cima da antiga, mantendo 'dados' e removendo arquivos que
    não existem mais na pasta _internal (bibliotecas da versão anterior)."""
    keep = {"dados", "portable.txt"}
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        if rel == Path("."):
            dirs[:] = [d for d in dirs if d not in keep]
            files = [f for f in files if f not in keep]
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            _retry(shutil.copy2, Path(root) / f, dst / rel / f)
    old, new = dst / "_internal", src / "_internal"
    if old.is_dir() and new.is_dir():
        for root, dirs, files in os.walk(old, topdown=False):
            rel = Path(root).relative_to(old)
            for f in files:
                if not (new / rel / f).exists():
                    try:
                        (Path(root) / f).unlink()
                    except OSError:
                        pass
            if not (new / rel).exists():
                shutil.rmtree(root, ignore_errors=True)


def apply_portable_update(target: str, wait_pid: int) -> int:
    """Executado pela versão nova (na pasta temporária): substitui a pasta do programa."""
    from .config import exe_dir, log_error
    import traceback
    _wait_pid(wait_pid)
    time.sleep(0.5)
    dst = Path(target)
    try:
        if not (dst / EXE_NAME).exists():
            raise UpdateError(f"pasta do programa não encontrada: {dst}")
        copy_over(exe_dir(), dst)
    except Exception as e:
        log_error("Atualização da versão portátil", traceback.format_exc())
        _message(f"Não foi possível atualizar o Vorticis PDF Editor:\n{e}\n\n"
                 f"Baixe a versão nova em {RELEASES_PAGE}")
        return 1
    subprocess.Popen([str(dst / EXE_NAME)], cwd=str(dst), **_detached())
    return 0


def _message(text: str):
    if sys.platform.startswith("win"):
        try:
            import ctypes
            from . import APP_NAME
            ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
            return
        except Exception:
            pass
    print(text)


def cleanup_old(max_age_s=3600):
    """Apaga downloads de atualizações anteriores (a pasta temporária não se apaga sozinha)."""
    base = Path(tempfile.gettempdir())
    now = time.time()
    for d in base.glob(TEMP_PREFIX + "*"):
        try:
            if now - d.stat().st_mtime > max_age_s:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


# ------------------------------------------------------------------ configurações
def _bool(v, default=True) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "sim")


def auto_check_enabled() -> bool:
    from .config import settings
    return _bool(settings().value("update_auto_check"), True)


def set_auto_check(on: bool):
    from .config import settings
    settings().setValue("update_auto_check", bool(on))


def due_for_check() -> bool:
    from .config import settings
    try:
        last = float(settings().value("update_last_check", 0) or 0)
    except (TypeError, ValueError):
        last = 0
    return auto_check_enabled() and time.time() - last >= CHECK_EVERY_S


def mark_checked():
    from .config import settings
    settings().setValue("update_last_check", time.time())
