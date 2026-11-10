#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Собирает единый файл tinvest_analytics.py из исходников в src/.

    python3 build.py           # записать tinvest_analytics.py
    python3 build.py --check   # код возврата 1, если файл в репозитории отличается от свежей сборки

Только стандартная библиотека. Фрагменты склеиваются в порядке имён файлов
побайтово, без добавления или удаления символов.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "tinvest_analytics.py")


def read(*parts):
    with open(os.path.join(ROOT, *parts), "rb") as f:
        return f.read()


def concat(pattern):
    files = sorted(glob.glob(os.path.join(ROOT, pattern)))
    if not files:
        sys.exit("build: не найдены файлы " + pattern)
    return b"".join(open(p, "rb").read() for p in files)


def build():
    page = read("src", "web", "shell.html")
    for token, data in ((b"{{CSS}}\n", concat("src/web/css/*.css")),
                        (b"{{JS}}\n", concat("src/web/js/*.js"))):
        if page.count(token) != 1:
            sys.exit("build: в shell.html должен быть ровно один маркер %r" % token)
        page = page.replace(token, data)
    out = concat("src/py/*.py")
    if out.count(b"{{PAGE}}") != 1:
        sys.exit("build: в src/py должен быть ровно один маркер {{PAGE}}")
    return out.replace(b"{{PAGE}}", page)


def main():
    data = build()
    if "--check" in sys.argv[1:]:
        try:
            current = open(OUT, "rb").read()
        except OSError:
            current = None
        if current != data:
            print("tinvest_analytics.py не совпадает со сборкой из src/. Запустите: python3 build.py")
            return 1
        print("OK: tinvest_analytics.py соответствует src/")
        return 0
    with open(OUT, "wb") as f:
        f.write(data)
    print("записано %s (%d байт)" % (os.path.relpath(OUT, ROOT), len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
