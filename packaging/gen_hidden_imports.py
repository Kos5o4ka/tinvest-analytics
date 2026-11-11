#!/usr/bin/env python3
"""Список модулей стандартной библиотеки, которые нужны скачанной программе (для PyInstaller).

Собранный лаунчер запускает tinvest_analytics.py внутри себя, а PyInstaller не видит этот файл при сборке,
поэтому модули, которые он импортирует, надо перечислить явно (hiddenimports).

    python3 packaging/gen_hidden_imports.py [путь/к/tinvest_analytics.py] [-o hidden_imports.txt]

Берутся все импорты из программы (в том числе внутри функций) плюс запас на будущие версии.
Нужен Python 3.10+ (sys.stdlib_module_names).
"""
import argparse, ast, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Запас: то, что программа может начать импортировать в следующих версиях, чтобы лаунчер не нужно было пересобирать.
EXTRA = """
sqlite3 ssl socket select selectors http.server http.client http.cookiejar http.cookies
email email.message email.parser email.utils email.mime.text email.mime.multipart email.header
xml.etree.ElementTree xml.dom.minidom zipfile gzip zlib bz2 lzma tarfile csv decimal fractions
concurrent.futures concurrent.futures.thread webbrowser tkinter tkinter.ttk json hashlib hmac secrets uuid
statistics calendar html html.parser urllib.request urllib.parse urllib.error urllib.response
base64 binascii bisect collections datetime difflib functools heapq io itertools math operator os pathlib
platform queue random re shutil string struct subprocess tempfile textwrap threading time traceback typing
unicodedata zoneinfo logging locale ctypes mimetypes ipaddress contextlib dataclasses enum copy pprint
codecs array weakref atexit signal stat glob fnmatch getpass gettext sched shlex smtplib
""".split()


def stdlib_imports(source):
    """Модули стандартной библиотеки, импортируемые в source (включая вложенные импорты)."""
    std = sys.stdlib_module_names
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module] + [node.module + "." + a.name for a in node.names if a.name != "*"]
        else:
            continue
        for n in names:
            if n.split(".")[0] in std:
                found.add(n)
    return found


def hidden_imports(app_path):
    with open(app_path, encoding="utf-8") as f:
        found = stdlib_imports(f.read())
    # «from x import y» даёт и x, и x.y; y не всегда модуль — отбрасываем то, чего нет
    import importlib.util
    ok = set()
    for n in found | set(EXTRA):
        try:
            if importlib.util.find_spec(n) is not None:
                ok.add(n)
        except (ImportError, ValueError, AttributeError):
            pass
    return sorted(ok)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("app", nargs="?", default=os.path.join(ROOT, "tinvest_analytics.py"))
    ap.add_argument("-o", "--output", help="записать в файл (по умолчанию — в stdout)")
    a = ap.parse_args()
    text = "\n".join(hidden_imports(a.app)) + "\n"
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text)
        print("Модулей: %d -> %s" % (text.count("\n"), a.output))
    else:
        sys.stdout.write(text)
