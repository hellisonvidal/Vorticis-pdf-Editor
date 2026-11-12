"""Gera o ícone do Vorticis PDF Editor (vórtice + página PDF).

Uso:  python tools/make_icon.py
Saída: vorticis_pdf/resources/icon.png, icon.ico e logo.png
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "vorticis_pdf" / "resources"
S = 1024  # desenha grande e reduz (antialias)

RED = (214, 35, 45)
RED_DARK = (150, 16, 28)
ORANGE = (255, 120, 40)
NAVY = (22, 30, 60)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def find_font(size):
    for name in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
                 "LiberationSans-Bold.ttf", "FreeSansBold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    for p in Path("/usr/share/fonts").rglob("*Bold*.ttf"):
        return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def build():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # sombra da página
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((170, 90, 880, 990), 70, fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    img.alpha_composite(shadow)

    # página com canto dobrado
    page = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    pd = ImageDraw.Draw(page)
    fold = 210
    left, top, right, bottom = 150, 60, 860, 960
    pd.rounded_rectangle((left, top, right, bottom), 60, fill=(250, 250, 252, 255))
    # recorta o canto
    pd.polygon([(right - fold, top - 2), (right + 2, top - 2), (right + 2, top + fold)],
               fill=(0, 0, 0, 0))
    pd.polygon([(right - fold, top), (right - fold, top + fold - 30),
                (right - fold + 30, top + fold), (right, top + fold)],
               fill=(205, 210, 222, 255))
    img.alpha_composite(page)

    # faixa vermelha inferior com "PDF"
    band = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(690, 900):
        t = (y - 690) / 210
        bd.line([(80, y), (940, y)], fill=lerp(RED, RED_DARK, t) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((80, 690, 940, 900), 50, fill=255)
    img.paste(band, (0, 0), mask)
    d = ImageDraw.Draw(img)
    font = find_font(190)
    text = "PDF"
    w = d.textlength(text, font=font)
    d.text(((S - w) / 2, 695), text, font=font, fill=(255, 255, 255, 255))

    # vórtice (espiral de braços) na parte superior da página
    cx, cy = 480, 390
    vortex = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vortex)
    arms = 3
    for arm in range(arms):
        base = arm * 2 * math.pi / arms
        pts = []
        steps = 220
        for i in range(steps):
            t = i / steps
            ang = base + t * 2.6 * math.pi
            r = 18 + 250 * t
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        for i in range(len(pts) - 1):
            t = i / len(pts)
            width = int(10 + 46 * t)
            col = lerp(NAVY, RED, min(1, t * 1.3)) if arm != 1 else lerp(NAVY, ORANGE, min(1, t * 1.3))
            vd.line([pts[i], pts[i + 1]], fill=col + (255,), width=width)
            vd.ellipse((pts[i][0] - width / 2, pts[i][1] - width / 2,
                        pts[i][0] + width / 2, pts[i][1] + width / 2), fill=col + (255,))
    vd.ellipse((cx - 34, cy - 34, cx + 34, cy + 34), fill=NAVY + (255,))
    # limita o vórtice à área da página
    vmask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(vmask).rounded_rectangle((left, top, right, 690), 60, fill=255)
    ImageDraw.Draw(vmask).polygon([(right - fold, top - 2), (right + 2, top - 2),
                                   (right + 2, top + fold)], fill=0)
    img.paste(vortex, (0, 0), Image.composite(vortex, Image.new("RGBA", (S, S)), vmask).split()[3])
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    img = build()
    img.resize((512, 512), Image.LANCZOS).save(OUT / "logo.png")
    img.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    # imagens BMP (não PNG) dentro do .ico: a barra de tarefas, o Explorer e o Qt do Windows
    # leem esse formato em qualquer versão; cada tamanho é reduzido do desenho grande
    sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(OUT / "icon.ico", sizes=sizes, bitmap_format="bmp")
    for s in (16, 24, 32, 48, 64, 128):
        img.resize((s, s), Image.LANCZOS).save(OUT / f"icon_{s}.png")
    print("Ícones gerados em", OUT)


if __name__ == "__main__":
    main()
