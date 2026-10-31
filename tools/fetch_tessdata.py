"""Baixa os modelos de idioma do OCR (Tesseract) que acompanham o programa.

Uso: python tools/fetch_tessdata.py
Português e inglês: modelos "best" (maior precisão); espanhol: modelo "fast".
Licença dos modelos: Apache 2.0 (https://github.com/tesseract-ocr).
"""
import sys
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "vorticis_pdf" / "resources" / "tessdata"
MODELS = {
    "por": "tessdata_best", "eng": "tessdata_best", "spa": "tessdata_fast",
}
URL = "https://raw.githubusercontent.com/tesseract-ocr/{repo}/main/{code}.traineddata"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for code, repo in MODELS.items():
        f = DEST / f"{code}.traineddata"
        if f.exists() and f.stat().st_size > 1_000_000:
            print("ok (já existe):", f.name)
            continue
        print("baixando", f.name, "...")
        tmp = f.with_suffix(".part")
        urllib.request.urlretrieve(URL.format(repo=repo, code=code), tmp)
        tmp.replace(f)
    print("Modelos de OCR em", DEST)


if __name__ == "__main__":
    sys.exit(main())
