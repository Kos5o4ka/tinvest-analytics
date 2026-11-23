#!/usr/bin/env python3
"""Рисует иконку приложения — тот же знак, что в интерфейсе (src/web/shell.html): синяя «Т» со стрелкой роста
на тёмной скруглённой подложке. Нужен Pillow — только для сборки, в самой программе его нет.

    python3 packaging/make_icon.py [папка]   ->  icon.png, icon.ico, icon.icns
"""
import os, sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

SS = 4                                                   # рисуем в 4× и уменьшаем — гладкие края


def vgrad(w, h, c0, c1):
    m = Image.linear_gradient("L").resize((w, h))
    return ImageOps.colorize(m, c0, c1).convert("RGBA")


def dgrad(w, h, c0, c1):
    m = ImageChops.add(Image.linear_gradient("L").resize((w, h)),
                       Image.linear_gradient("L").rotate(90).resize((w, h)), scale=2)
    return ImageOps.colorize(m, c0, c1).convert("RGBA")


def layer(img, fill, mask):
    """Наложить заливку (цвет или картинку) через маску с учётом прозрачности."""
    src = fill if isinstance(fill, Image.Image) else Image.new("RGBA", img.size, fill)
    a = ImageChops.multiply(src.getchannel("A"), mask)
    src = src.copy()
    src.putalpha(a)
    return Image.alpha_composite(img, src)


def mark_masks(N, u, ox, oy, thick):
    """Маски знака в координатах viewBox 32×32 из shell.html (u — пикселей на единицу)."""
    P = lambda x, y: (ox + x * u, oy + y * u)
    body = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(body)
    d.rounded_rectangle([*P(7, 7), *P(25, 11.5)], radius=2 * u, fill=255)           # верхняя перекладина «Т»
    sx = (thick - 1) * 0.5                                                           # на мелких размерах ножка толще
    d.rounded_rectangle([*P(13.5 - sx, 9), *P(18.5 + sx, 25)], radius=2 * u, fill=255)
    arrow = Image.new("L", (N, N), 0)
    a = ImageDraw.Draw(arrow)
    w = 2.2 * u * thick
    for pts in (((18.5, 16), (24.5, 10)), ((20.5, 10), (24.5, 10)), ((24.5, 10), (24.5, 14))):
        (x0, y0), (x1, y1) = P(*pts[0]), P(*pts[1])
        a.line([x0, y0, x1, y1], fill=255, width=int(w))
        for x, y in ((x0, y0), (x1, y1)):
            a.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=255)
    return body, arrow


def draw(size=1024):
    small = size <= 48
    N = size * SS
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    sq = Image.new("L", (N, N), 0)
    ImageDraw.Draw(sq).rounded_rectangle([0, 0, N - 1, N - 1], radius=int(N * 0.225), fill=255)   # как у иконок macOS
    img = layer(img, vgrad(N, N, (17, 24, 39), (6, 8, 14)), sq)                    # #111827 -> #06080e
    if not small:                                                                    # еле заметная внутренняя обводка
        ring = ImageChops.subtract(sq, sq.filter(ImageFilter.MinFilter(2 * SS + 1)))
        img = layer(img, (255, 255, 255, 26), ring)
    # знак занимает ~56% (на мелких — до 70%), по центру
    frac = 0.70 if small else 0.56
    u = N * frac / 18.0
    ox, oy = N / 2 - 16 * u, N / 2 - 16 * u
    body, arrow = mark_masks(N, u, ox, oy, 1.35 if small else 1.0)
    if not small:                                                                    # мягкое свечение под знаком
        glow = ImageChops.lighter(body, arrow).filter(ImageFilter.GaussianBlur(N * 0.035))
        img = layer(img, (37, 99, 235, 60), glow)
    img = layer(img, vgrad(N, N, (96, 165, 250), (37, 99, 235)), body)             # #60a5fa -> #2563eb
    img = layer(img, dgrad(N, N, (191, 219, 254), (56, 189, 248)), arrow)          # стрелка роста светлее
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(out, exist_ok=True)
    big = draw(1024)
    big.save(os.path.join(out, "icon.png"))
    sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = [draw(s) for s in sizes]                    # каждый размер рисуется отдельно, мелкие — упрощённые
    frames[-1].save(os.path.join(out, "icon.ico"), format="ICO", sizes=[(s, s) for s in sizes],
                    append_images=frames[:-1])
    big.save(os.path.join(out, "icon.icns"))            # Pillow умеет ICNS сам, iconutil не нужен
    print("Иконки записаны в", out)
