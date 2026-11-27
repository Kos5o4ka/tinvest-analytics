#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генерирует src/py/02c_font_inter.py из src/web/fonts/InterVariable.woff2.

Шрифт встраивается в монолит base64-строкой, чтобы tinvest_analytics.py оставался одним файлом.
Запуск после замены woff2:  python3 packaging/make_font.py && python3 build.py
Шрифт Inter (SIL Open Font License 1.1), лицензия: src/web/fonts/Inter-LICENSE.txt.
Источник: https://github.com/rsms/inter/releases (v4.1), подмножество: латиница, кириллица, знаки валют и пунктуации.
"""
import base64
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "web", "fonts", "InterVariable.woff2")
OUT = os.path.join(ROOT, "src", "py", "02c_font_inter.py")


def main():
    with open(SRC, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("ascii")
    lines = [b64[i:i + 100] for i in range(0, len(b64), 100)]
    body = "# -*- coding: utf-8 -*-\n# Сгенерировано packaging/make_font.py из src/web/fonts/InterVariable.woff2 — руками не править.\n"
    body += "# Inter 4.1, SIL Open Font License 1.1 (src/web/fonts/Inter-LICENSE.txt).\n"
    body += "FONT_INTER_B64 = (\n" + "\n".join('    "%s"' % ln for ln in lines) + "\n)\n"
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    print("записано %s (%d байт шрифта, %d байт кода)" % (os.path.relpath(OUT, ROOT), len(raw), len(body)))


if __name__ == "__main__":
    main()
