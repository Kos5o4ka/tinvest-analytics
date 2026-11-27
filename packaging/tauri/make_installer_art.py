#!/usr/bin/env python3
"""Картинки установщиков Tauri в фирменном стиле TAnalytic (нужен Pillow, только для разработки).

    python3 packaging/tauri/make_installer_art.py [каталог]       (по умолчанию src-tauri/installer)

Создаёт:
  header.bmp   150x57   — шапка страницы мастера NSIS (Windows)
  sidebar.bmp  164x314  — боковая панель мастера NSIS (Windows)
  dmg-background.tiff 660x400 @1x+@2x — фон окна образа диска (macOS), стрелка «перетащите в Программы»
Готовые файлы лежат в репозитории; запускать скрипт нужно только при смене оформления.
Логотип — та же геометрия, что в LOGO_SVG (tinvest.py), viewBox 32x32.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

BG = (7, 9, 13)            # #07090d
CARD = (15, 20, 32)        # #0f1420
ACCENT = (59, 130, 246)    # #3b82f6
ACCENT2 = (37, 99, 235)    # #2563eb
LIGHT = (96, 165, 250)     # #60a5fa
TEXT = (237, 241, 247)
MUTED = (154, 165, 182)
SS = 4                     # суперсэмплинг для сглаживания


def font(size, bold=False):
    try:                                                     # системный шрифт macOS (переменный): вес задаётся вариацией
        f = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", size)
        try:
            f.set_variation_by_name("Semibold" if bold else "Regular")
        except Exception:  # noqa: BLE001
            pass
        return f
    except OSError:
        pass
    names = (
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for p in names:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def draw_logo(size):
    """Значок TAnalytic на тёмной плитке size x size (RGBA)."""
    k = size * SS / 32.0
    img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, 32 * k - 1, 32 * k - 1], radius=9 * k, fill=CARD + (255,), outline=(255, 255, 255, 24))
    d.rounded_rectangle([7 * k, 7 * k, 25 * k, 11.5 * k], radius=2 * k, fill=ACCENT)
    d.rectangle([13.5 * k, 11.5 * k, 18.5 * k, 22 * k], fill=ACCENT2)
    d.rounded_rectangle([13.5 * k, 17 * k, 18.5 * k, 25 * k], radius=2 * k, fill=ACCENT2)
    w = max(1, int(2.2 * k))
    pts = [(18.5 * k, 16 * k), (24.5 * k, 10 * k)]
    d.line(pts, fill=LIGHT, width=w)
    d.line([(24.5 * k, 10 * k), (20.5 * k, 10 * k)], fill=LIGHT, width=w)
    d.line([(24.5 * k, 10 * k), (24.5 * k, 14 * k)], fill=LIGHT, width=w)
    for x, y in ((18.5, 16), (24.5, 10), (20.5, 10), (24.5, 14)):          # скруглённые концы линий
        d.ellipse([x * k - w / 2, y * k - w / 2, x * k + w / 2, y * k + w / 2], fill=LIGHT)
    return img.resize((size, size), Image.LANCZOS)


def glow(img, cx, cy, radius, color, strength=0.35):
    """Мягкое свечение: радиальный градиент поверх фона."""
    ov = Image.new("RGB", img.size, color)
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    steps = 40
    for i in range(steps):
        r = radius * (1 - i / steps)
        a = int(255 * strength * (i / steps) ** 2)
        md.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a)
    return Image.composite(ov, img, mask)


def header():
    w, h = 150, 57
    img = Image.new("RGB", (w, h), BG)
    img = glow(img, w, 0, 90, ACCENT, 0.30)
    logo = draw_logo(40)
    img.paste(logo, (w - 48, (h - 40) // 2), logo)
    return img


def sidebar():
    w, h = 164, 314
    img = Image.new("RGB", (w, h), BG)
    img = glow(img, 0, 0, 260, ACCENT, 0.28)
    img = glow(img, w, h, 200, (56, 189, 248), 0.12)
    logo = draw_logo(72)
    img.paste(logo, ((w - 72) // 2, 54), logo)
    d = ImageDraw.Draw(img)
    f = font(22, True)
    t = "TAnalytic"
    d.text(((w - d.textlength(t, font=f)) / 2, 142), t, fill=TEXT, font=f)
    f2 = font(11)
    t2 = "Аналитика брокерских счетов"
    d.text(((w - d.textlength(t2, font=f2)) / 2, 176), t2, fill=MUTED, font=f2)
    d.line([(32, 214), (w - 32, 214)], fill=(255, 255, 255), width=1)
    img.paste(Image.blend(img.crop((32, 214, w - 32, 215)), Image.new("RGB", (w - 64, 1), ACCENT), 0.5), (32, 214))
    return img


DMG_BG = (246, 247, 250)    # светлый фон: Finder подписывает значки тёмным текстом, на тёмном фоне его не видно
DMG_TEXT = (15, 23, 42)
DMG_MUTED = (91, 101, 119)


def dmg_background(k=1):
    """Фон окна образа диска 660x400 точек; k=2 — та же картинка для экранов Retina (иначе текст мыльный)."""
    w, h = 660 * k, 400 * k
    img = Image.new("RGB", (w, h), DMG_BG)
    img = glow(img, w // 2, -60 * k, 420 * k, ACCENT, 0.10)
    d = ImageDraw.Draw(img)
    f = font(24 * k, True)
    t = "Установка TAnalytic"
    d.text(((w - d.textlength(t, font=f)) / 2, 40 * k), t, fill=DMG_TEXT, font=f)
    f2 = font(14 * k)
    t2 = "Перетащите значок в папку «Программы»"
    d.text(((w - d.textlength(t2, font=f2)) / 2, 78 * k), t2, fill=DMG_MUTED, font=f2)
    y = 200 * k                                              # линия иконок: приложение (180, 200) и «Программы» (480, 200)
    x0, x1 = 262 * k, 398 * k
    d.line([(x0, y), (x1 - 6 * k, y)], fill=ACCENT, width=3 * k)
    d.polygon([(x1 + 8 * k, y), (x1 - 8 * k, y - 10 * k), (x1 - 8 * k, y + 10 * k)], fill=ACCENT)
    return img


def save_dmg_background(out):
    """PNG 1x и 2x и TIFF с обоими размерами (Finder берёт нужный для экрана). TIFF собирает tiffutil (только macOS)."""
    p1, p2 = os.path.join(out, "dmg-background.png"), os.path.join(out, "dmg-background@2x.png")
    dmg_background(1).save(p1)
    dmg_background(2).save(p2)
    tif = os.path.join(out, "dmg-background.tiff")
    if os.system('tiffutil -cathidpicheck "%s" "%s" -out "%s" >/dev/null 2>&1' % (p1, p2, tif)) != 0:
        print("tiffutil недоступен: dmg-background.tiff не обновлён")


def main(out):
    os.makedirs(out, exist_ok=True)
    header().save(os.path.join(out, "header.bmp"), format="BMP")
    sidebar().save(os.path.join(out, "sidebar.bmp"), format="BMP")
    save_dmg_background(out)
    print("готово:", out)


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "src-tauri", "installer"))
