"""OCR (reconhecimento óptico de caracteres) com o Tesseract embutido no PyMuPDF.

Não precisa instalar nada: os modelos de idioma (português, inglês e espanhol) já vêm
com o programa. Outros idiomas podem ser baixados uma única vez (Ferramentas › OCR).

  * make_searchable: adiciona uma camada de texto invisível sobre páginas digitalizadas.
    A aparência da página não muda; o texto passa a poder ser pesquisado, selecionado,
    copiado e convertido (Word/Excel).
  * extract_text: devolve o texto reconhecido de cada página.
"""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

import pymupdf

from .config import app_data_dir, resource_path

LANGS = {
    "por": "Português", "eng": "Inglês", "spa": "Espanhol", "fra": "Francês", "deu": "Alemão",
    "ita": "Italiano", "nld": "Holandês", "rus": "Russo", "ukr": "Ucraniano", "pol": "Polonês",
    "tur": "Turco", "ara": "Árabe", "heb": "Hebraico", "hin": "Hindi", "jpn": "Japonês",
    "kor": "Coreano", "chi_sim": "Chinês simplificado", "chi_tra": "Chinês tradicional",
    "lat": "Latim", "grc": "Grego antigo", "ell": "Grego", "cat": "Catalão", "glg": "Galego",
}
DOWNLOAD_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{code}.traineddata"


def bundled_dir() -> Path:
    return Path(resource_path("tessdata"))


def user_dir() -> Path:
    d = app_data_dir() / "tessdata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _langs_in(folder: Path) -> set[str]:
    try:
        return {p.stem for p in folder.glob("*.traineddata")}
    except OSError:
        return set()


def available_langs() -> list[str]:
    found = _langs_in(bundled_dir()) | _langs_in(user_dir())
    main = ["por", "eng", "spa"]
    return sorted(found, key=lambda c: (main.index(c) if c in main else 9, LANGS.get(c, c)))


def tessdata_for(langs: list[str]) -> str:
    """O Tesseract aceita uma única pasta de modelos: escolhe (ou monta) a pasta certa."""
    b, u = bundled_dir(), user_dir()
    if set(langs) <= _langs_in(b):
        return str(b)
    missing = set(langs) - _langs_in(u)
    for code in missing & _langs_in(b):  # copia os modelos embutidos que faltarem
        shutil.copyfile(b / f"{code}.traineddata", u / f"{code}.traineddata")
    still = set(langs) - _langs_in(u)
    if still:
        raise ValueError("Idioma de OCR não instalado: " + ", ".join(LANGS.get(c, c) for c in still))
    return str(u)


def download_lang(code: str, progress=None) -> Path:
    dest = user_dir() / f"{code}.traineddata"
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(DOWNLOAD_URL.format(code=code), headers={"User-Agent": "VorticisPDF"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(65536):
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done, total)
    tmp.replace(dest)
    return dest


def page_has_text(page: pymupdf.Page) -> bool:
    return len(page.get_text("text").strip()) >= 20


def _ocr_textpage(page, langs, dpi):
    return page.get_textpage_ocr(language="+".join(langs), dpi=dpi, full=True,
                                 tessdata=tessdata_for(langs))


_FONT = None
_FALLBACK = None


def _font_for(word):
    global _FONT, _FALLBACK
    if _FONT is None:
        _FONT = pymupdf.Font("helv")
        _FALLBACK = pymupdf.Font("cjk")
    if all(_FONT.has_glyph(ord(ch)) for ch in word):
        return _FONT
    return _FALLBACK


def make_searchable(doc: pymupdf.Document, pages: list[int], langs: list[str], dpi: int = 300,
                    skip_with_text: bool = True, progress=None) -> dict:
    """Adiciona texto invisível (reconhecido por OCR) às páginas. Retorna um resumo."""
    done, skipped, words_total = [], [], 0
    for n, pno in enumerate(pages):
        page = doc[pno]
        if skip_with_text and page_has_text(page):
            skipped.append(pno + 1)
        else:
            tp = _ocr_textpage(page, langs, dpi)
            words = page.get_text("words", textpage=tp)
            tw = pymupdf.TextWriter(page.rect)
            for x0, y0, x1, y1, word, *_ in words:
                w, h = x1 - x0, y1 - y0
                if w <= 0 or h <= 0 or not word.strip():
                    continue
                font = _font_for(word)
                unit = font.text_length(word, fontsize=1) or 1
                size = max(1.0, min(h * 0.95, w / unit))
                try:
                    tw.append((x0, y1 - h * 0.18), word, font=font, fontsize=size)
                except Exception:
                    continue
                words_total += 1
            if tw.text_rect is not None and not tw.text_rect.is_empty:
                tw.write_text(page, render_mode=3)  # 3 = invisível
            done.append(pno + 1)
        if progress:
            progress(n + 1, len(pages))
    return {"paginas_ocr": done, "paginas_com_texto": skipped, "palavras": words_total}


def extract_text(doc: pymupdf.Document, pages: list[int], langs: list[str], dpi: int = 300,
                 use_existing: bool = True, progress=None) -> list[tuple[int, str, bool]]:
    """[(número da página, texto, veio_do_ocr)]"""
    out = []
    for n, pno in enumerate(pages):
        page = doc[pno]
        if use_existing and page_has_text(page):
            out.append((pno + 1, page.get_text("text", sort=True), False))
        else:
            tp = _ocr_textpage(page, langs, dpi)
            out.append((pno + 1, page.get_text("text", textpage=tp, sort=True), True))
        if progress:
            progress(n + 1, len(pages))
    return out
