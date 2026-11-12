"""Ações diretas do botão direito do Explorer: executam sem abrir nenhuma janela.

    unir       -> <primeiro>_unido.pdf na mesma pasta
    separar    -> pasta "<nome> - separado" ao lado do arquivo
    converter  -> arquivo(s) no formato escolhido, ao lado do original
    imprimir   -> impressora padrão (ou a última usada), com as opções da última impressão

Nada é sobrescrito: se o nome já existir, usa "nome (2)". Só aparece uma mensagem se algo
der errado (o erro também vai para o registro de erros).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from . import converters as conv
from .config import unique_path

SPLIT_MODES = {
    # chave: (rótulo no menu, modo de split_groups, valor)
    "each": ("Uma página por arquivo", "each", ""),
    "half": ("Ao meio (duas partes)", "half", ""),
    "every2": ("A cada 2 páginas", "every", "2"),
    "every5": ("A cada 5 páginas", "every", "5"),
    "every10": ("A cada 10 páginas", "every", "10"),
    "oddeven": ("Páginas ímpares e pares (dois arquivos)", "oddeven", ""),
}


def _as_pdf(f: str, tmpdir: str) -> str:
    if f.lower().endswith(".pdf"):
        return f
    out = os.path.join(tmpdir, Path(f).stem + ".pdf")
    return conv.to_pdf(f, out)


def merge(files: list[str]) -> str:
    from .document import merge_files
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        raise ValueError("Nenhum arquivo para unir.")
    first = Path(files[0])
    out = unique_path(first.with_name(first.stem + "_unido.pdf"))
    with tempfile.TemporaryDirectory(prefix="vorticis_") as td:
        srcs = [_as_pdf(f, td) for f in files]
        merge_files(srcs, out, bookmarks=True)  # já registra no histórico de salvamentos
    return out


def split(files: list[str], mode: str = "each") -> list[str]:
    import pymupdf
    from .document import split_document, split_groups
    _label, key, value = SPLIT_MODES.get(mode, SPLIT_MODES["each"])
    written = []
    for f in files:
        if not os.path.isfile(f):
            continue
        doc = pymupdf.open(f)
        n = doc.page_count
        if key == "oddeven":
            groups = [list(range(0, n, 2)), list(range(1, n, 2))]
            groups = [g for g in groups if g]
        else:
            groups = split_groups(key, n, value)
        folder = Path(unique_path(Path(f).with_name(f"{Path(f).stem} - separado")))
        folder.mkdir(parents=True, exist_ok=True)
        parts = split_document(doc, groups, str(folder), Path(f).stem)
        doc.close()
        written += parts
    return written


def convert(files: list[str], fmt: str, dpi: int = 150) -> list[str]:
    """fmt = 'pdf' ou uma chave de converters.FROM_PDF."""
    produced = []
    for f in files:
        if not os.path.isfile(f):
            continue
        src = Path(f)
        if fmt == "pdf":
            if src.suffix.lower() == ".pdf":
                continue
            produced.append(conv.to_pdf(f, unique_path(src.with_suffix(".pdf"))))
            continue
        ext = conv.FROM_PDF[fmt][1]
        suffix = "_otimizado" if fmt == "pdfa" else ""
        out = unique_path(src.with_name(src.stem + suffix + ext))
        with tempfile.TemporaryDirectory(prefix="vorticis_") as td:
            produced += conv.from_pdf(_as_pdf(f, td), fmt, out, dpi=dpi)
    return produced


def print_files(files: list[str]) -> int:
    """Imprime direto na impressora padrão (ou na última escolhida), sempre em uma face."""
    from .document import open_any
    from .printing import print_silent
    n = 0
    for f in files:
        if os.path.isfile(f):
            print_silent(open_any(f))
            n += 1
    return n
