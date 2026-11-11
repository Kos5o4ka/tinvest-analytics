#!/usr/bin/env python3
"""Рисует иконку приложения (нужен Pillow — только для сборки, в самой программе его нет).

    python3 packaging/make_icon.py [папка]   ->  icon.png, icon.ico, icon.icns
"""
import os, sys
from PIL import Image, ImageDraw


def draw(size=1024):
    k = size / 1024.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(230 * k), fill=(27, 38, 59, 255))
    bars = [(230, 560), (400, 440), (570, 330), (740, 210)]            # растущие столбики портфеля
    for i, (x, top) in enumerate(bars):
        d.rounded_rectangle([x * k, top * k, (x + 110) * k, 800 * k], radius=int(26 * k),
                            fill=(255, 221, 45, 255) if i == len(bars) - 1 else (88, 166, 255, 255))
    return img


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out, exist_ok=True)
    img = draw()
    img.save(os.path.join(out, "icon.png"))
    img.save(os.path.join(out, "icon.ico"), sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
    img.save(os.path.join(out, "icon.icns"))            # Pillow умеет ICNS сам, iconutil не нужен
    print("Иконки записаны в", out)
