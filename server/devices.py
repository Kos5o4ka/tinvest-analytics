# -*- coding: utf-8 -*-
"""Лимит компьютеров на один аккаунт: один ключ из бота работает не больше чем на MAX_DEVICES компьютерах.

Приложение присылает с каждым запросом к серверу данных только sha256-хэш идентификатора ПК (заголовок X-Hwid, см.
src/py/12e_hwid.py). Сырой id и токен Т-Инвестиций сюда не попадают. Таблица key_devices(tg_id, hwid, ...) лежит в общей
базе бота и считается на аккаунт (tg_id), а не на ключ: перевыпуск ключа не обнуляет список компьютеров.

Новый компьютер занимает место, пока мест меньше лимита; дальше сервер отвечает 401 {"error": "devices"}. Компьютер,
который владелец отвязал в боте (/devices), получает {"error": "device_blocked"}, пока не выпущен новый ключ.
Запросы без заголовка (старые версии приложения) пропускаются как раньше.

Параметры (переменная окружения; то же имя читает бот):
    TINVEST_MAX_DEVICES      компьютеров на аккаунт (по умолчанию 5)
"""
import os
import sqlite3
import threading
import time

SCHEMA = ("CREATE TABLE IF NOT EXISTS key_devices(tg_id INTEGER NOT NULL, hwid TEXT NOT NULL, first_seen REAL NOT NULL, "
          "last_seen REAL NOT NULL, blocked INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tg_id, hwid))")
OK_TTL, SEEN_EVERY, MAX_CACHE = 60, 300, 20000

_lock = threading.Lock()
_ok = {}


def max_devices():
    try:
        v = int(str(os.environ.get("TINVEST_MAX_DEVICES", "")).strip())
        return v if v > 0 else 5
    except ValueError:
        return 5


def reset_cache():
    with _lock:
        _ok.clear()


def check(keystore, tg_id, hwid, now=None):
    """-> "ok" | "devices" | "device_blocked". При ошибке базы — "ok" (лимит не должен ронять вход)."""
    now = time.time() if now is None else now
    k = (tg_id, hwid)
    with _lock:
        hit = _ok.get(k)
    if hit and hit > now:
        return "ok"
    try:
        c = keystore._conn()
        c.execute(SCHEMA)
        row = c.execute("SELECT blocked, last_seen FROM key_devices WHERE tg_id=? AND hwid=?", (tg_id, hwid)).fetchone()
        if row:
            if row[0]:
                return "device_blocked"
            if now - (row[1] or 0) >= SEEN_EVERY:
                c.execute("UPDATE key_devices SET last_seen=? WHERE tg_id=? AND hwid=?", (now, tg_id, hwid))
        else:
            n = c.execute("SELECT COUNT(*) FROM key_devices WHERE tg_id=? AND blocked=0", (tg_id,)).fetchone()[0]
            if n >= max_devices():
                return "devices"
            c.execute("INSERT OR IGNORE INTO key_devices(tg_id, hwid, first_seen, last_seen) VALUES(?,?,?,?)",
                      (tg_id, hwid, now, now))
    except (sqlite3.Error, OSError):
        return "ok"
    with _lock:
        if len(_ok) > MAX_CACHE:
            _ok.clear()
        _ok[k] = now + OK_TTL
    return "ok"
