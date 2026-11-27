# -*- coding: utf-8 -*-
"""Привязка пробного периода к компьютеру (HWID) и параметры тарифа.

Приложение присылает ТОЛЬКО sha256-хэш идентификатора ПК (заголовок X-Hwid; здесь он нужен при /v1/auth/check,
лимит компьютеров на аккаунт — в devices.py). Сырой id и токен
Т-Инвестиций сюда не попадают. Таблица trial_hwid(hwid, tg_id, t) лежит в общей базе бота: первый tg-аккаунт, у которого
на этом ПК был пробный период, «занимает» хэш. Если на тот же ПК приходит другой аккаунт с действующим пробным периодом,
пробный снимается (тариф Free), а клиенту уходит trial_blocked. Без заголовка (старые версии) поведение прежнее.

Параметры (переменные окружения; те же имена читает бот):
    TINVEST_TRIAL_DAYS       длительность пробного периода, дней (по умолчанию 7)
    TINVEST_PRO_PRICE_STARS  цена Pro в Telegram Stars; 0 = оплата выключена (по умолчанию 0)
"""
import os
import re
import sqlite3
import time

MSG_USED = "Пробный период на этом компьютере уже использован"

SCHEMA = "CREATE TABLE IF NOT EXISTS trial_hwid(hwid TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, t REAL NOT NULL)"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _int_env(name, default):
    try:
        v = int(str(os.environ.get(name, "")).strip())
        return v if v >= 0 else default
    except ValueError:
        return default


def trial_days():
    return _int_env("TINVEST_TRIAL_DAYS", 7) or 7


def price_stars():
    return _int_env("TINVEST_PRO_PRICE_STARS", 0)


def valid_hwid(s):
    return bool(s) and bool(_HEX64.match(str(s).strip().lower()))


def apply(keystore, hwid_raw, info, now=None):
    """-> (info, blocked). Ничего не делает без хэша, без базы ключей или если у аккаунта не было пробного."""
    hwid = str(hwid_raw or "").strip().lower()
    if not info or not keystore or not valid_hwid(hwid):
        return info, False
    now = time.time() if now is None else now
    tg = info.get("tg_id")
    try:
        c = keystore._conn()
        c.execute(SCHEMA)
        row = c.execute("SELECT trial_used, pro_kind, plan_until FROM users WHERE tg_id=?", (tg,)).fetchone()
        if not row or not row[0]:
            return info, False
        c.execute("INSERT OR IGNORE INTO trial_hwid(hwid, tg_id, t) VALUES(?,?,?)", (hwid, tg, now))
        owner = c.execute("SELECT tg_id FROM trial_hwid WHERE hwid=?", (hwid,)).fetchone()[0]
        if owner == tg:
            return info, False
        if row[1] == "trial":
            c.execute("UPDATE users SET plan_until=NULL, plan='free', pro_kind=NULL WHERE tg_id=? AND pro_kind='trial'", (tg,))
            with keystore._lock:
                keystore._cache.clear()
        # ключ в кэше мог быть выдан до снятия: клиенту отдаём уже Free
        if row[1] == "trial":
            return dict(info, plan="free", pro_until=None, trial=False), True
        return info, True
    except (sqlite3.Error, OSError):
        return info, False
