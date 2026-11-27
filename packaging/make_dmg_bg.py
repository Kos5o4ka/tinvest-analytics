#!/usr/bin/env python3
"""Фон окна образа диска: стрелка от приложения к «Программы» и подпись. Нужен Pillow — только для сборки.

    python3 packaging/make_dmg_bg.py out.png     (окно 560x360 точек, файл 2x — для Retina)
"""
import sys
from PIL import Image, ImageDraw, ImageFont

W, H, K = 560, 360, 2


def font(size):
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf",
              "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def main(out):
    img = Image.new("RGB", (W * K, H * K), (245, 246, 250))
    d = ImageDraw.Draw(img)
    col = (120, 130, 150)
    y = 170 * K                                              # линия иконок (см. make_dmg.sh: позиции 150 и 410)
    d.line([(222 * K, y), (326 * K, y)], fill=col, width=5 * K)
    d.polygon([(342 * K, y), (320 * K, y - 15 * K), (320 * K, y + 15 * K)], fill=col)
    text = "Перетащите TAnalytic в «Программы»"
    f = font(15 * K)
    w = d.textlength(text, font=f)
    d.text(((W * K - w) / 2, 40 * K), text, fill=(70, 78, 98), font=f)
    img.save(out, dpi=(72 * K, 72 * K))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dmg_background.png")
