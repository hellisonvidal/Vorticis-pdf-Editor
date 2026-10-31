"""Tradução de textos e documentos (requer internet; serviço gratuito, sem cadastro).

Usa o serviço público do Google Tradutor e, se ele falhar, o MyMemory.
  * translate_text: traduz um texto qualquer (divide textos longos automaticamente).
  * translate_pdf: gera um novo PDF traduzido mantendo o layout: cada bloco de texto é
    substituído pela tradução no mesmo lugar (ajustando o tamanho para caber), sem
    remover imagens, linhas ou tabelas.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

import pymupdf

LANGS = {
    "auto": "Detectar automaticamente", "pt": "Português", "en": "Inglês", "es": "Espanhol",
    "fr": "Francês", "de": "Alemão", "it": "Italiano", "nl": "Holandês", "ru": "Russo",
    "uk": "Ucraniano", "pl": "Polonês", "tr": "Turco", "ar": "Árabe", "he": "Hebraico",
    "hi": "Hindi", "ja": "Japonês", "ko": "Coreano", "zh-CN": "Chinês (simplificado)",
    "zh-TW": "Chinês (tradicional)", "el": "Grego", "sv": "Sueco", "da": "Dinamarquês",
    "no": "Norueguês", "fi": "Finlandês", "cs": "Tcheco", "ro": "Romeno", "hu": "Húngaro",
    "la": "Latim", "ca": "Catalão", "gl": "Galego",
}
MAX_CHARS = 4000
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VorticisPDF"


class TranslationError(Exception):
    pass


def _google(text: str, target: str, source: str = "auto") -> str:
    url = "https://translate.googleapis.com/translate_a/single"
    params = urllib.parse.urlencode({"client": "gtx", "sl": source, "tl": target, "dt": "t"})
    data = urllib.parse.urlencode({"q": text}).encode()
    req = urllib.request.Request(f"{url}?{params}", data=data, headers={
        "User-Agent": _UA, "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    return "".join(seg[0] for seg in payload[0] if seg and seg[0])


def _mymemory(text: str, target: str, source: str = "auto") -> str:
    src = "en" if source == "auto" else source
    out = []
    for piece in _split(text, 450):
        q = urllib.parse.urlencode({"q": piece, "langpair": f"{src}|{target}"})
        req = urllib.request.Request(f"https://api.mymemory.translated.net/get?{q}", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            out.append(json.loads(r.read().decode("utf-8"))["responseData"]["translatedText"])
    return " ".join(out)


BACKENDS = [_google, _mymemory]


def _split(text: str, limit: int) -> list[str]:
    """Divide em pedaços <= limit, preferindo quebras de parágrafo, linha e frase."""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"(\n\n+)", text):
        if len(cur) + len(para) <= limit:
            cur += para
            continue
        if cur:
            parts.append(cur)
            cur = ""
        while len(para) > limit:
            cut = max(para.rfind(". ", 0, limit), para.rfind("\n", 0, limit), para.rfind(" ", 0, limit))
            cut = cut + 1 if cut > 0 else limit
            parts.append(para[:cut])
            para = para[cut:]
        cur = para
    if cur:
        parts.append(cur)
    return parts


def _call(text, target, source):
    errors = []
    for backend in BACKENDS:
        for attempt in range(2):
            try:
                return backend(text, target, source)
            except Exception as e:  # rede, limite de uso, resposta inesperada
                errors.append(f"{backend.__name__.strip('_')}: {e}")
                time.sleep(0.8 * (attempt + 1))
    raise TranslationError("Não foi possível traduzir (verifique a conexão com a internet).\n"
                           + "\n".join(errors[-2:]))


def translate_text(text: str, target: str = "pt", source: str = "auto", progress=None) -> str:
    if not text.strip():
        return text
    chunks = _split(text, MAX_CHARS)
    out = []
    for i, chunk in enumerate(chunks):
        out.append(_call(chunk, target, source) if chunk.strip() else chunk)
        if progress:
            progress(i + 1, len(chunks))
    return "".join(out)


_MARK = "[[#{}]]"
_MARK_RE = re.compile(r"\[\[\s*#\s*(\d+)\s*\]\]")


def translate_blocks(blocks: list[str], target: str, source: str = "auto") -> list[str]:
    """Traduz vários trechos em poucas requisições (marcadores numerados entre eles)."""
    result = list(blocks)
    batch, size = [], 0

    def flush():
        nonlocal batch, size
        if not batch:
            return
        joined = "\n".join(f"{_MARK.format(i)} {blocks[i]}" for i in batch)
        translated = _call(joined, target, source)
        pieces = {int(m.group(1)): None for m in _MARK_RE.finditer(translated)}
        parts = _MARK_RE.split(translated)
        if set(pieces) == set(batch):
            for k in range(1, len(parts), 2):
                result[int(parts[k])] = parts[k + 1].strip()
        else:  # o serviço alterou os marcadores: traduz um a um
            for i in batch:
                result[i] = _call(blocks[i], target, source)
        batch, size = [], 0

    for i, b in enumerate(blocks):
        if not b.strip():
            continue
        if size + len(b) > MAX_CHARS - 200:
            flush()
        batch.append(i)
        size += len(b) + 12
    flush()
    return result


def _block_style(block):
    sizes, colors, bold = [], [], 0
    for line in block.get("lines", []):
        for s in line["spans"]:
            if s["text"].strip():
                sizes.append(s["size"])
                colors.append(s["color"])
                bold += bool(s["flags"] & 16)
    size = sorted(sizes)[len(sizes) // 2] if sizes else 11
    color = max(set(colors), key=colors.count) if colors else 0
    return size, "#%06x" % color, bold > len(sizes) / 2


def translate_pdf(doc: pymupdf.Document, pages: list[int], target: str, source: str = "auto",
                  progress=None) -> pymupdf.Document:
    """Devolve uma cópia do documento com os textos das páginas indicadas traduzidos."""
    out = pymupdf.open("pdf", doc.tobytes())
    for n, pno in enumerate(pages):
        page = out[pno]
        blocks = [b for b in page.get_text("dict")["blocks"] if b.get("type") == 0]
        texts = [" ".join("".join(s["text"] for s in l["spans"]).strip() for l in b["lines"]).strip()
                 for b in blocks]
        keep = [(b, t) for b, t in zip(blocks, texts) if t]
        if keep:
            translated = translate_blocks([t for _b, t in keep], target, source)
            for b, _t in keep:
                r = pymupdf.Rect(b["bbox"])
                page.add_redact_annot(r + (0.5, 0.5, -0.5, -0.5), fill=False)
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                  graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
            for (b, _t), tr in zip(keep, translated):
                size, color, bold = _block_style(b)
                r = pymupdf.Rect(b["bbox"])
                r.x1 = max(r.x1, min(page.rect.x1 - 20, r.x0 + r.width * 1.05))
                css = (f"* {{font-family: sans-serif; font-size: {size:.1f}pt; color: {color}; "
                       f"font-weight: {'bold' if bold else 'normal'}; line-height: 1.15; margin: 0}}")
                html = "<p>" + (tr.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")) + "</p>"
                try:
                    page.insert_htmlbox(r, html, css=css, scale_low=0)
                except Exception:
                    page.insert_textbox(r, tr, fontsize=size * 0.8, fontname="helv")
        if progress:
            progress(n + 1, len(pages))
    return out
