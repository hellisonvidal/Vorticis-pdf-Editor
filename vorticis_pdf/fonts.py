"""Catálogo de fontes e reconhecimento automático da fonte usada no PDF.

Ordem de resolução ao editar um trecho de texto:
  1. Fonte embutida no próprio PDF (se contiver todos os glifos necessários);
  2. Fonte instalada no sistema com o mesmo nome (PostScript / nome completo / família+estilo);
  3. Fonte do sistema mais parecida (família + negrito/itálico);
  4. Fontes padrão do PDF (Base-14: Helvetica, Times, Courier...) conforme serifa/mono.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, asdict
from pathlib import Path

import pymupdf

from .config import app_data_dir

FONT_EXTS = {".ttf", ".otf", ".ttc", ".otc"}

# Fontes Base-14 do PDF (sempre disponíveis) -> código interno do PyMuPDF
BASE14 = {
    "Helvetica": "helv", "Helvetica-Bold": "hebo", "Helvetica-Oblique": "heit",
    "Helvetica-BoldOblique": "hebi", "Times-Roman": "tiro", "Times-Bold": "tibo",
    "Times-Italic": "tiit", "Times-BoldItalic": "tibi", "Courier": "cour",
    "Courier-Bold": "cobo", "Courier-Oblique": "coit", "Courier-BoldOblique": "cobi",
    "Symbol": "symb", "ZapfDingbats": "zadb",
}
# Fontes CJK embutidas no PyMuPDF
CJK = {"China-Simplificado": "china-s", "China-Tradicional": "china-t",
       "Japonês": "japan", "Coreano": "korea"}

# Substituições métricas comuns quando a fonte original não existe no sistema
ALIASES = {
    "arial": ["arial", "liberationsans", "helvetica", "arimo", "freesans"],
    "helvetica": ["helvetica", "arial", "liberationsans", "arimo", "freesans"],
    "timesnewroman": ["timesnewroman", "times", "liberationserif", "tinos", "freeserif"],
    "times": ["timesnewroman", "liberationserif", "tinos", "freeserif"],
    "couriernew": ["couriernew", "courier", "liberationmono", "cousine", "freemono"],
    "courier": ["couriernew", "liberationmono", "cousine", "freemono"],
    "calibri": ["calibri", "carlito"],
    "cambria": ["cambria", "caladea"],
    "verdana": ["verdana", "dejavusans"],
    "garamond": ["garamond", "ebgaramond"],
}

STYLE_WORDS = ("bold", "italic", "oblique", "black", "light", "medium", "semibold",
               "demibold", "regular", "roman", "book", "condensed", "narrow", "thin",
               "heavy", "extrabold", "extralight", "it", "bd", "mt", "ps", "psmt")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def strip_subset(name: str) -> str:
    """'ABCDEF+Arial-BoldMT' -> 'Arial-BoldMT'"""
    return re.sub(r"^[A-Z]{6}\+", "", name or "")


def split_family_style(name: str):
    """Separa família e estilo: 'Arial-BoldItalicMT' -> ('arial', bold=True, italic=True)."""
    name = strip_subset(name)
    low = name.lower()
    bold = any(w in low for w in ("bold", "black", "heavy", "semibold", "demi", ",bd", "-bd"))
    italic = any(w in low for w in ("italic", "oblique", "-it", ",it"))
    fam = re.split(r"[-,]", name)[0]
    fam = re.sub(r"(PSMT|PS|MT)$", "", fam)
    fam_n = norm(fam)
    for w in sorted(STYLE_WORDS, key=len, reverse=True):
        if fam_n.endswith(w) and len(fam_n) > len(w) + 2:
            fam_n = fam_n[: -len(w)]
    return fam_n, bold, italic


@dataclass
class SysFont:
    path: str
    index: int
    family: str
    style: str
    full: str
    ps: str

    @property
    def bold(self):
        s = self.style.lower()
        return any(w in s for w in ("bold", "black", "heavy", "semibold", "demi"))

    @property
    def italic(self):
        s = self.style.lower()
        return "italic" in s or "oblique" in s

    @property
    def label(self):
        return self.full or f"{self.family} {self.style}".strip()


def font_dirs():
    dirs = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(Path(windir) / "Fonts")
        la = os.environ.get("LOCALAPPDATA")
        if la:
            dirs.append(Path(la) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs += [Path("/System/Library/Fonts"), Path("/Library/Fonts"),
                 Path.home() / "Library" / "Fonts"]
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
                 Path.home() / ".fonts", Path.home() / ".local" / "share" / "fonts"]
    # fontes extras do usuário, colocadas na pasta do aplicativo
    dirs.append(app_data_dir() / "fonts")
    return [d for d in dirs if d.is_dir()]


def _read_names(path: Path):
    """Lê a tabela 'name' de um arquivo de fonte (ttf/otf/ttc)."""
    from fontTools.ttLib import TTFont, TTCollection

    out = []
    try:
        if path.suffix.lower() in (".ttc", ".otc"):
            fonts = TTCollection(str(path), lazy=True).fonts
        else:
            fonts = [TTFont(str(path), lazy=True, fontNumber=0)]
    except Exception:
        return out
    for idx, f in enumerate(fonts):
        try:
            name = f["name"]
            fam = name.getBestFamilyName() or ""
            sub = name.getBestSubFamilyName() or ""
            full = name.getBestFullName() or ""
            ps = name.getDebugName(6) or ""
            out.append(SysFont(str(path), idx, fam, sub, full, ps))
        except Exception:
            pass
        finally:
            try:
                f.close()
            except Exception:
                pass
    return out


class FontCatalog:
    """Varre as fontes instaladas (com cache em disco) e faz o casamento de nomes."""

    def __init__(self):
        self.fonts: list[SysFont] = []
        self.ready = threading.Event()
        self._by_key: dict[str, SysFont] = {}
        self._by_family: dict[str, list[SysFont]] = {}

    # ---------------- varredura ----------------
    def load_async(self):
        threading.Thread(target=self.load, daemon=True).start()

    def load(self):
        cache_file = app_data_dir() / "fontcache.json"
        try:
            cache = json.loads(cache_file.read_text("utf-8"))
        except Exception:
            cache = {}
        new_cache, fonts = {}, []
        for d in font_dirs():
            for p in d.rglob("*"):
                if p.suffix.lower() not in FONT_EXTS:
                    continue
                try:
                    key = f"{p}|{p.stat().st_mtime_ns}"
                except OSError:
                    continue
                entries = cache.get(key)
                if entries is None:
                    entries = [asdict(f) for f in _read_names(p)]
                new_cache[key] = entries
                fonts += [SysFont(**e) for e in entries]
        try:
            cache_file.write_text(json.dumps(new_cache), "utf-8")
        except Exception:
            pass
        fonts.sort(key=lambda f: f.label.lower())
        self.fonts = fonts
        for f in fonts:
            for k in (f.ps, f.full, f.family + f.style, f.family + "-" + f.style):
                self._by_key.setdefault(norm(k), f)
            self._by_family.setdefault(norm(f.family), []).append(f)
        self.ready.set()

    # ---------------- casamento ----------------
    def _pick_style(self, cands, bold, italic):
        def score(f):
            return (f.bold == bold) * 2 + (f.italic == italic) * 2 + \
                (f.style.lower() in ("regular", "normal", "roman", "book")) * 0.5
        return max(cands, key=score) if cands else None

    def match(self, pdf_name: str, bold=False, italic=False):
        """Retorna (SysFont | None, exato: bool)."""
        self.ready.wait(15)
        name = strip_subset(pdf_name)
        n = norm(name)
        if n in self._by_key:
            return self._by_key[n], True
        for suf in ("mt", "psmt", "ps"):
            if n.endswith(suf) and n[: -len(suf)] in self._by_key:
                return self._by_key[n[: -len(suf)]], True
        fam, b2, i2 = split_family_style(name)
        bold, italic = bold or b2, italic or i2
        for alias in ALIASES.get(fam, [fam]):
            if alias in self._by_family:
                return self._pick_style(self._by_family[alias], bold, italic), alias == fam
        close = difflib.get_close_matches(fam, list(self._by_family), n=1, cutoff=0.8)
        if close:
            return self._pick_style(self._by_family[close[0]], bold, italic), False
        return None, False


catalog = FontCatalog()


def base14_for(name: str, flags: int):
    """Escolhe a fonte Base-14 mais próxima (flags do PyMuPDF: 1=sobrescrito, 2=itálico,
    4=serifada, 8=mono, 16=negrito)."""
    fam, b, i = split_family_style(name)
    bold = bool(flags & 16) or b
    italic = bool(flags & 2) or i
    if flags & 8 or "courier" in fam or "mono" in fam:
        base = ["Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"]
    elif flags & 4 or "times" in fam or "serif" in fam and "sans" not in fam:
        base = ["Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"]
    else:
        base = ["Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"]
    return base[(1 if bold else 0) + (2 if italic else 0)]


@dataclass
class ResolvedFont:
    """Fonte pronta para uso em page.insert_text."""
    label: str           # o que mostrar ao usuário
    source: str          # 'embutida' | 'sistema' | 'similar' | 'padrão'
    fontbuffer: bytes | None = None
    fontfile: str | None = None
    base14: str | None = None

    def pymupdf_font(self):
        if self.fontbuffer:
            return pymupdf.Font(fontbuffer=self.fontbuffer)
        if self.fontfile:
            return pymupdf.Font(fontfile=self.fontfile)
        return pymupdf.Font(self.base14 or "helv")


def _embedded_font(doc: pymupdf.Document, page: pymupdf.Page, pdf_name: str, text: str):
    for xref, ext, _type, basefont, *_ in page.get_fonts(full=True):
        if strip_subset(basefont) != strip_subset(pdf_name) or ext in ("n/a", ""):
            continue
        try:
            _n, _e, _t, buf = doc.extract_font(xref)
            if not buf:
                continue
            f = pymupdf.Font(fontbuffer=buf)
            if all(f.has_glyph(ord(c)) for c in text if not c.isspace()):
                return buf
        except Exception:
            continue
    return None


def resolve_font(doc, page, pdf_name: str, flags: int, text: str) -> ResolvedFont:
    clean = strip_subset(pdf_name)
    buf = _embedded_font(doc, page, pdf_name, text)
    if buf:
        return ResolvedFont(f"{clean} (embutida no PDF)", "embutida", fontbuffer=buf)
    sf, exact = catalog.match(pdf_name, bool(flags & 16), bool(flags & 2))
    if sf:
        try:
            data = _font_bytes(sf)
            return ResolvedFont(sf.label, "sistema" if exact else "similar", fontbuffer=data)
        except Exception:
            pass
    b = base14_for(pdf_name, flags)
    return ResolvedFont(b, "padrão", base14=BASE14[b])


def _font_bytes(sf: SysFont) -> bytes:
    """Bytes da fonte; extrai a face correta de coleções .ttc."""
    if sf.path.lower().endswith((".ttc", ".otc")) and sf.index:
        from fontTools.ttLib import TTFont
        import io
        f = TTFont(sf.path, fontNumber=sf.index)
        bio = io.BytesIO()
        f.save(bio)
        return bio.getvalue()
    return Path(sf.path).read_bytes()


def font_from_choice(label: str) -> ResolvedFont:
    """Converte a escolha manual do usuário (combo de fontes) em ResolvedFont."""
    if label in BASE14:
        return ResolvedFont(label, "padrão", base14=BASE14[label])
    if label in CJK:
        return ResolvedFont(label, "padrão", base14=CJK[label])
    for f in catalog.fonts:
        if f.label == label:
            return ResolvedFont(f.label, "sistema", fontbuffer=_font_bytes(f))
    return ResolvedFont("Helvetica", "padrão", base14="helv")


def all_font_labels():
    labels = list(BASE14) + list(CJK)
    seen = set(labels)
    for f in catalog.fonts:
        if f.label not in seen:
            seen.add(f.label)
            labels.append(f.label)
    return labels


# ---------------------------------------------------------------- informações para o usuário
def missing_glyphs(font: ResolvedFont, text: str) -> list[str]:
    """Caracteres do texto que a fonte não possui (seriam trocados por outra fonte)."""
    try:
        f = font.pymupdf_font()
    except Exception:
        return []
    out = []
    for c in dict.fromkeys(text):
        if not c.isspace() and not f.has_glyph(ord(c)):
            out.append(c)
    return out


def describe_span(doc, page, span) -> dict:
    """Dados da fonte original de um trecho, para mostrar ao usuário."""
    name = span.get("font", "")
    flags = span.get("flags", 0)
    fam, b, i = split_family_style(name)
    info = {"nome": strip_subset(name), "subconjunto": bool(re.match(r"^[A-Z]{6}\+", name)),
            "negrito": bool(flags & 16) or b, "italico": bool(flags & 2) or i,
            "serifa": bool(flags & 4), "mono": bool(flags & 8),
            "tamanho": span.get("size", 0), "cor": "#%06x" % span.get("color", 0),
            "tipo": "", "embutida": False}
    for _xref, ext, ftype, basefont, *_ in page.get_fonts(full=True):
        if strip_subset(basefont) == info["nome"]:
            info["tipo"] = ftype
            info["embutida"] = ext not in ("n/a", "")
            break
    return info


_qt_families: dict[str, str] = {}
_BASE14_QT = {"helv": "Arial", "hebo": "Arial", "heit": "Arial", "hebi": "Arial",
              "tiro": "Times New Roman", "tibo": "Times New Roman", "tiit": "Times New Roman",
              "tibi": "Times New Roman", "cour": "Courier New", "cobo": "Courier New",
              "coit": "Courier New", "cobi": "Courier New"}


def qt_family(font: ResolvedFont) -> str:
    """Registra a fonte no Qt (para a prévia ao vivo) e devolve o nome da família."""
    if font.base14:
        return _BASE14_QT.get(font.base14, "Arial")
    if font.label in _qt_families:
        return _qt_families[font.label]
    fam = ""
    try:
        from PySide6.QtCore import QByteArray
        from PySide6.QtGui import QFontDatabase
        data = font.fontbuffer or Path(font.fontfile).read_bytes()
        fid = QFontDatabase.addApplicationFontFromData(QByteArray(data))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        fam = fams[0] if fams else ""
    except Exception:
        pass
    _qt_families[font.label] = fam
    return fam
