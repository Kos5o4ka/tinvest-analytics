#!/usr/bin/env python3
"""Лаунчер T-Invest Analytics: проверяет обновления на GitHub, скачивает и запускает программу.

Запуск:  python3 tinvest.py          (--no-update — не проверять обновления)
Токен лаунчер не читает и никуда не отправляет: он лежит только в папке данных на этом компьютере.
"""
import hashlib, json, os, subprocess, sys, urllib.request
from urllib.parse import urlparse

REPO = "Kos5o4ka/tinvest-analytics"                      # TODO: заменить на свой репозиторий GitHub (owner/name)
FILE = "tinvest_analytics.py"            # файл программы в релизе
HOME = os.environ.get("TINVEST_HOME") or os.path.join(os.path.expanduser("~"), ".tinvest_analytics")
APP_DIR = os.path.join(HOME, "app")
APP, VER = os.path.join(APP_DIR, FILE), os.path.join(APP_DIR, "version.txt")
OK_HOSTS = ("api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")


def get(url, limit=20_000_000):
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in OK_HOSTS:     # только HTTPS и только GitHub
        raise ValueError("недопустимый адрес: " + url)
    req = urllib.request.Request(url, headers={"User-Agent": "tinvest-launcher"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("слишком большой файл")
    return data


def update():
    rel = json.loads(get("https://api.github.com/repos/%s/releases/latest" % REPO))
    tag = rel["tag_name"]
    have = open(VER).read().strip() if os.path.exists(VER) and os.path.exists(APP) else ""
    if tag == have:
        return
    urls = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    code, sums = get(urls[FILE]), get(urls["SHA256SUMS"]).decode()
    want = next(l.split()[0] for l in sums.splitlines() if l.split()[-1].lstrip("*") == FILE)
    if hashlib.sha256(code).hexdigest() != want.lower():
        raise ValueError("не совпала контрольная сумма SHA256 — обновление отклонено")
    compile(code, FILE, "exec")                                # хотя бы синтаксически валидный Python
    os.makedirs(APP_DIR, mode=0o700, exist_ok=True)
    if os.path.exists(APP):
        os.replace(APP, APP + ".bak")                          # предыдущая версия остаётся как запасная
    tmp = APP + ".tmp"
    with open(tmp, "wb") as f:
        f.write(code)
    os.replace(tmp, APP)                                       # атомарная подмена
    with open(VER, "w") as f:
        f.write(tag)
    print("Обновлено до", tag)


def main():
    args = [a for a in sys.argv[1:] if a != "--no-update"]
    if "--no-update" not in sys.argv:
        try:
            update()
        except Exception as e:
            print("Обновление пропущено:", e)
    if not os.path.exists(APP):
        sys.exit("Программа ещё не скачана, а обновиться не удалось. Проверьте интернет и REPO в лаунчере.")
    sys.exit(subprocess.call([sys.executable, APP] + args))


if __name__ == "__main__":
    main()
