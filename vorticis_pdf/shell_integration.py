"""Integração com o Windows Explorer (menu do botão direito e 'Enviar para').

Tudo é gravado em HKEY_CURRENT_USER — não precisa de administrador.
Menu criado para arquivos .pdf:
    Vorticis PDF  ▸  Abrir no Vorticis | Unir PDFs selecionados | Separar PDF |
                     Organizar páginas | Imprimir | Converter para...
Para documentos do Office/imagens:
    Vorticis PDF  ▸  Converter para PDF | Unir como PDF
No Windows 11 os itens aparecem em "Mostrar mais opções" (ou Shift+F10).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


from .converters import OFFICE_TO_PDF, NATIVE_TO_PDF

PROGID = "VorticisPDF.Document"
MENU_KEY = "VorticisPDF"

PDF_VERBS = [
    ("1open", "Abrir no Vorticis", "--open"),
    ("2merge", "Unir PDFs selecionados", "--merge"),
    ("3split", "Separar PDF", "--split"),
    ("4organize", "Organizar páginas", "--organize"),
    ("5print", "Imprimir", "--print"),
    ("6convert", "Converter PDF para...", "--convert"),
]
OTHER_VERBS = [
    ("1topdf", "Converter para PDF", "--to-pdf"),
    ("2merge", "Unir como um único PDF", "--merge"),
    ("3open", "Abrir no Vorticis", "--open"),
]


def exe_command() -> str:
    """Linha de comando que inicia o programa (exe empacotado ou python -m)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = pyw if pyw.exists() else Path(sys.executable)
    return f'"{py}" -m vorticis_pdf'


def icon_path() -> str:
    if getattr(sys, "frozen", False):
        return f"{sys.executable},0"
    from .config import resource_path
    return resource_path("icon.ico")


def _set(winreg, path, values: dict):
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE)
    for name, val in values.items():
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, val)
    winreg.CloseKey(key)


def _delete_tree(winreg, path):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return
    while True:
        try:
            sub = winreg.EnumKey(key, 0)
        except OSError:
            break
        _delete_tree(winreg, path + "\\" + sub)
    winreg.CloseKey(key)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


def _menu(winreg, ext, verbs):
    base = rf"Software\Classes\SystemFileAssociations\{ext}\shell\{MENU_KEY}"
    _set(winreg, base, {"MUIVerb": "Vorticis PDF", "Icon": icon_path(), "SubCommands": "",
                        "MultiSelectModel": "Player"})
    cmd = exe_command()
    for key, label, flag in verbs:
        _set(winreg, rf"{base}\shell\{key}", {"MUIVerb": label, "MultiSelectModel": "Player"})
        _set(winreg, rf"{base}\shell\{key}\command", {"": f'{cmd} {flag} "%1"'})


def _sendto_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "SendTo"


def _make_shortcut(lnk: Path, args: str, desc: str):
    """Cria atalho .lnk via PowerShell (sem dependências)."""
    import subprocess
    cmd = exe_command()
    target, _, extra = cmd.partition('" ')
    target = target.strip('"')
    arguments = (extra + " " + args).strip()
    icon = icon_path().split(",")[0]
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
          f"$s.TargetPath='{target}';$s.Arguments='{arguments}';"
          f"$s.IconLocation='{icon}';$s.Description='{desc}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, creationflags=0x08000000)


def register() -> str:
    if not sys.platform.startswith("win"):
        raise OSError("A integração com o Explorer só existe no Windows.")
    import winreg
    cmd = exe_command()
    # ProgID (para "Abrir com")
    _set(winreg, rf"Software\Classes\{PROGID}", {"": "Documento PDF (Vorticis)"})
    _set(winreg, rf"Software\Classes\{PROGID}\DefaultIcon", {"": icon_path()})
    _set(winreg, rf"Software\Classes\{PROGID}\shell\open\command", {"": f'{cmd} "%1"'})
    _set(winreg, r"Software\Classes\.pdf\OpenWithProgids", {PROGID: ""})
    _set(winreg, r"Software\Classes\Applications\VorticisPDF.exe\shell\open\command",
         {"": f'{cmd} "%1"'})

    _menu(winreg, ".pdf", PDF_VERBS)
    for ext in sorted(OFFICE_TO_PDF | NATIVE_TO_PDF):
        _menu(winreg, ext, OTHER_VERBS)

    # "Enviar para" recebe TODOS os arquivos selecionados de uma vez
    sd = _sendto_dir()
    if sd.is_dir():
        _make_shortcut(sd / "Vorticis - Unir em PDF.lnk", "--merge", "Unir arquivos em um PDF")
        _make_shortcut(sd / "Vorticis - Organizar páginas.lnk", "--organize",
                       "Organizar páginas dos arquivos")
    _notify_shell()
    return "Menu de contexto instalado. No Windows 11, use 'Mostrar mais opções'."


def unregister() -> str:
    if not sys.platform.startswith("win"):
        raise OSError("A integração com o Explorer só existe no Windows.")
    import winreg
    _delete_tree(winreg, rf"Software\Classes\{PROGID}")
    _delete_tree(winreg, r"Software\Classes\Applications\VorticisPDF.exe")
    for ext in sorted(OFFICE_TO_PDF | NATIVE_TO_PDF | {".pdf"}):
        _delete_tree(winreg, rf"Software\Classes\SystemFileAssociations\{ext}\shell\{MENU_KEY}")
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.pdf\OpenWithProgids",
                           0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(k, PROGID)
        winreg.CloseKey(k)
    except OSError:
        pass
    for name in ("Vorticis - Unir em PDF.lnk", "Vorticis - Organizar páginas.lnk"):
        try:
            (_sendto_dir() / name).unlink()
        except OSError:
            pass
    _notify_shell()
    return "Integração removida."


def is_registered() -> bool:
    if not sys.platform.startswith("win"):
        return False
    import winreg
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       rf"Software\Classes\SystemFileAssociations\.pdf\shell\{MENU_KEY}").Close()
        return True
    except OSError:
        return False


def _notify_shell():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass
