#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Замок дополнительных библиотек: packaging/vendor.txt -> src/py/02a_vendor_lock.py.

    python3 packaging/vendor_lock.py              # проверить колёса по метаданным PyPI и переписать замок
    python3 packaging/vendor_lock.py --check      # код 1, если замок не соответствует vendor.txt (без сети)
    python3 packaging/vendor_lock.py --download DIR   # скачать колёса в DIR и проверить SHA256 (для загрузки в релиз)

Только стандартная библиотека. Код скачанных колёс здесь не импортируется и не запускается.
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "packaging", "vendor.txt")
OUT = os.path.join(ROOT, "src", "py", "02a_vendor_lock.py")
LINE = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.+\-]+)\s+([0-9a-f]{64})((?:\s+\S+)*)\s*$")
WHEEL = re.compile(r"^[A-Za-z0-9_.]+-[A-Za-z0-9_.+]+-(py3|py2\.py3)-none-any\.whl$")


def ver(s):
    return [int(x) for x in s.split(".")[:2]]


def parse():
    out = []
    for n, raw in enumerate(open(SRC, encoding="utf-8"), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = LINE.match(line)
        if not m:
            sys.exit("vendor.txt:%d: не разобрал строку %r" % (n, raw.rstrip()))
        e = {"name": m.group(1).replace("-", "_").lower(), "version": m.group(2), "sha256": m.group(3), "python": [3, 8], "only_below": None, "requires": []}
        for opt in m.group(4).split():
            k, _, v = opt.partition("=")
            if opt.startswith("python>="):
                e["python"] = ver(opt[len("python>="):])
            elif k == "only_below":
                e["only_below"] = ver(v)
            elif k == "requires":
                e["requires"] = [x.replace("-", "_").lower() for x in v.split(",") if x]
            else:
                sys.exit("vendor.txt:%d: неизвестный параметр %r" % (n, opt))
        out.append(e)
    names = {e["name"] for e in out}
    for e in out:
        for r in e["requires"]:
            if r not in names:
                sys.exit("%s требует %s, но его нет в vendor.txt" % (e["name"], r))
    return out


def resolve(e):
    """Метаданные PyPI: колесо py3-none-any с ровно этим SHA256 -> имя файла, размер, адрес."""
    url = "https://pypi.org/pypi/%s/%s/json" % (e["name"], e["version"])
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "TAnalytic-vendor-lock"}), timeout=30) as r:
        j = json.load(r)
    for f in j.get("urls") or []:
        if f.get("digests", {}).get("sha256") == e["sha256"]:
            if not WHEEL.match(f["filename"]):
                sys.exit("%s: файл с этим хэшем — %s, а нужно колесо py3-none-any (чистый Python)" % (e["name"], f["filename"]))
            return dict(e, file=f["filename"], size=f["size"], url=f["url"])
    sys.exit("%s==%s: на PyPI нет колеса с SHA256 %s" % (e["name"], e["version"], e["sha256"]))


def render(entries):
    lines = ["# ═══════════════ дополнительные библиотеки: замок (сгенерировано packaging/vendor_lock.py из packaging/vendor.txt, руками не править) ═══════════════",
             "# Программа подгрузит колесо, только если его SHA256 совпал с этой таблицей; сама таблица проверяется лаунчером вместе со всем файлом.",
             "VENDOR_LOCK = ["]
    for e in entries:
        lines.append("    " + json.dumps({k: e[k] for k in ("name", "version", "file", "sha256", "size", "url", "python", "only_below", "requires")},
                                         ensure_ascii=False).replace(": null", ": None") + ",")
    lines += ["]", "", ""]
    return "\n".join(lines)


def current_lock():
    try:
        src = open(OUT, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"VENDOR_LOCK = \[(.*?)\n\]", src, re.S)
    if not m:
        return None
    return [json.loads(x.strip().rstrip(",").replace(": None", ": null")) for x in m.group(1).strip().splitlines() if x.strip()]


def main(argv):
    entries = parse()
    if "--check" in argv:
        lock = current_lock() or []
        key = lambda e: (e["name"], e["version"], e["sha256"], e["python"], e["only_below"], e["requires"])
        if [key(e) for e in lock] != [key(e) for e in entries]:
            print("src/py/02a_vendor_lock.py не соответствует packaging/vendor.txt. Запустите: python3 packaging/vendor_lock.py")
            return 1
        print("OK: замок библиотек соответствует vendor.txt")
        return 0
    if "--download" in argv:
        d = argv[argv.index("--download") + 1]
        os.makedirs(d, exist_ok=True)
        for e in current_lock() or []:
            with urllib.request.urlopen(e["url"], timeout=60) as r:
                data = r.read()
            if hashlib.sha256(data).hexdigest() != e["sha256"]:
                sys.exit("%s: SHA256 скачанного колеса не совпал с замком" % e["file"])
            with open(os.path.join(d, e["file"]), "wb") as f:
                f.write(data)
            print("ok %s (%d байт)" % (e["file"], len(data)))
        return 0
    resolved = [resolve(e) for e in entries]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(resolved))
    print("записано %s: %s" % (os.path.relpath(OUT, ROOT), ", ".join("%s %s" % (e["name"], e["version"]) for e in resolved)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
