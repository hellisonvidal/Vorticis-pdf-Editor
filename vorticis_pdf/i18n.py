"""Tradução para português do Brasil dos componentes padrão do Qt (botões OK/Cancelar,
seletor de arquivos, impressão, menus de copiar/colar, seletor de cores etc.)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

from .config import resource_path

_translators: list[QTranslator] = []

# mensagens de bibliotecas (em inglês) traduzidas para o usuário
LIB_MESSAGES = {
    "cannot open broken document": "o arquivo está corrompido ou não é um PDF válido",
    "no objects found": "o arquivo está vazio ou corrompido",
    "password": "o documento está protegido por senha",
    "Permission denied": "permissão negada (o arquivo pode estar aberto em outro programa)",
    "No such file or directory": "arquivo ou pasta não encontrado",
    "No space left on device": "não há espaço livre no disco",
    "timed out": "tempo esgotado (verifique a conexão com a internet)",
    "Name or service not known": "sem conexão com a internet",
    "getaddrinfo failed": "sem conexão com a internet",
    "Failed to decrypt": "senha do certificado incorreta",
    "Invalid password": "senha incorreta",
    "CKR_PIN_INCORRECT": "PIN do token incorreto",
    "CKR_PIN_LOCKED": "PIN do token bloqueado",
}


def friendly(msg: str) -> str:
    """Troca mensagens técnicas em inglês por explicações em português."""
    text = str(msg)
    for en, pt in LIB_MESSAGES.items():
        if en.lower() in text.lower():
            return f"{pt[0].upper()}{pt[1:]}.\n\n(detalhe técnico: {text})"
    return text


def install(app):
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    candidates = [Path(resource_path("translations")),
                  Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath))]
    for name in ("qtbase_pt_BR",):
        for folder in candidates:
            tr = QTranslator(app)
            if tr.load(name, str(folder)):
                app.installTranslator(tr)
                _translators.append(tr)
                break
