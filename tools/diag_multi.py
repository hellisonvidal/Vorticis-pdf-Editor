"""Diagnóstico temporário: edição simultânea com a fonte do sistema (Arial no Windows)."""
import faulthandler
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
faulthandler.dump_traceback_later(90, exit=True)
import pymupdf  # noqa: E402
from vorticis_pdf.document import PdfDocument  # noqa: E402
from vorticis_pdf.fonts import catalog, resolve_font  # noqa: E402

t = time.time()
catalog.load()
print("pymupdf", pymupdf.__version__, "| fontes:", len(catalog.fonts), f"{time.time()-t:.1f}s", flush=True)
d = PdfDocument(doc=pymupdf.open())
p = d.doc.new_page()
for k, txt in enumerate(("Campo A: 1", "Campo B: 2", "Campo C: 3")):
    p.insert_text((72, 100 + k * 30), txt, fontsize=12)
del p
spans = [sp | {"dir": ln["dir"]} for b in d.doc[0].get_text("dict")["blocks"]
         for ln in b.get("lines", []) for sp in ln["spans"]]
for sp in spans:
    t = time.time()
    font = resolve_font(d.doc, d.doc[0], sp["font"], sp["flags"], "x")
    print("resolve", sp["text"], "->", font.label, font.source, len(font.fontbuffer or b""), f"{time.time()-t:.2f}s", flush=True)
    new = sp["text"].replace(":", " =") + "0"
    t = time.time()
    fit = d.fit_size(0, sp, new, font, sp["size"])
    print("  fit", fit, f"{time.time()-t:.2f}s", flush=True)
    t = time.time()
    used = d._replace_span(0, sp, new, font, sp["size"], (0, 0, 0))
    pg = d.doc[0]
    print("  replace usado", used, f"{time.time()-t:.2f}s", "->", [s["text"] for b in pg.get_text("dict")["blocks"]
          for ln in b.get("lines", []) for s in ln["spans"]], "| fontes da página:", pg.get_fonts(), flush=True)
    del pg
print("FIM", flush=True)
