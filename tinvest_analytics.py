#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T-Invest Analytics — аналитика брокерских счетов Т-Инвестиций и отчётов других брокеров.

Один файл, только стандартная библиотека Python 3.8+. Запуск:

    python tinvest_analytics.py              # откроется окно приложения
    python tinvest_analytics.py --no-window  # только сервер: http://127.0.0.1:8765

Все данные хранятся локально в ~/.tinvest_analytics (база SQLite data.db, логотипы, настройки).
Токен никуда, кроме API Т-Банка, не отправляется.
"""
import base64
import bisect
import csv
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
import zipfile
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree as ET

APP_NAME = "T-Invest Analytics"
APP_VERSION = "0.12"
APP_DIR = os.environ.get("TINVEST_HOME") or os.path.join(os.path.expanduser("~"), ".tinvest_analytics")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DB_PATH = os.path.join(APP_DIR, "data.db")
LOGO_DIR = os.path.join(APP_DIR, "logos")
CONTRACT = "tinkoff.public.invest.api.contract.v1"
LOGO_CDN = "https://invest-brands.cdn-tinkoff.ru/"
D0 = Decimal(0)
DAY = 86400

# Реестр дополнительных маршрутов: модули регистрируют обработчики, сервер вызывает их.
#   API_GET["/api/x"] = fn(cfg, acc, q, force)  -> dict (JSON) или кортеж (код, тело, content-type, заголовки)
#   API_POST["/api/x"] = fn(cfg, body)           -> dict (JSON) или такой же кортеж
API_GET, API_POST = {}, {}
# Функции без аргументов, которые сервер вызывает один раз при запуске (фоновые потоки модулей).
STARTUP_HOOKS = []
# Ключи настроек, которые никогда не отдаются в интерфейс через /api/config (секреты).
SECRET_KEYS = {"token"}

DEFAULT_CONFIG = {
    "token": "",
    "sandbox": True,
    "hosts_prod": ["https://invest-public-api.tbank.ru/rest", "https://invest-public-api.tinkoff.ru/rest"],
    "hosts_sandbox": ["https://sandbox-invest-public-api.tbank.ru/rest",
                      "https://sandbox-invest-public-api.tinkoff.ru/rest"],
    "verify_ssl": True,
    "ca_file": "",
    "port": 8765,
    "theme": "auto",        # auto | dark | light
    "targets": {},          # целевые доли по классам активов, %: {"share": 50, "bond": 40, ...}
    "notify_days": 7,       # за сколько дней напоминать о выплатах
    "keyrate_mode": "cbr",  # источник прогноза ключевой ставки для флоатеров: cbr | survey | market | flat
    "mon_drop5": 3.0, "mon_drop30": 7.0, "mon_spread30": 2.0, "mon_sell_days": 5.0, "mon_offer_days": 30,   # пороги тревог «Мониторинга»
}

# Корневой сертификат Минцифры (Russian Trusted Root CA, RSA, до 27.02.2032).
# API Т-Банка подписан им, а Python его не знает — поэтому он встроен сюда и добавляется
# к стандартным сертификатам только внутри этой программы. В систему ничего не устанавливается.
# SHA-256: D2:6D:2D:02:31:B7:C3:9F:92:CC:73:85:12:BA:54:10:35:19:E4:40:5D:68:B5:BD:70:3E:97:88:CA:8E:CF:31
RUSSIAN_TRUSTED_ROOT_CA = """
-----BEGIN CERTIFICATE-----
MIIFwjCCA6qgAwIBAgICEAAwDQYJKoZIhvcNAQELBQAwcDELMAkGA1UEBhMCUlUx
PzA9BgNVBAoMNlRoZSBNaW5pc3RyeSBvZiBEaWdpdGFsIERldmVsb3BtZW50IGFu
ZCBDb21tdW5pY2F0aW9uczEgMB4GA1UEAwwXUnVzc2lhbiBUcnVzdGVkIFJvb3Qg
Q0EwHhcNMjIwMzAxMjEwNDE1WhcNMzIwMjI3MjEwNDE1WjBwMQswCQYDVQQGEwJS
VTE/MD0GA1UECgw2VGhlIE1pbmlzdHJ5IG9mIERpZ2l0YWwgRGV2ZWxvcG1lbnQg
YW5kIENvbW11bmljYXRpb25zMSAwHgYDVQQDDBdSdXNzaWFuIFRydXN0ZWQgUm9v
dCBDQTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAMfFOZ8pUAL3+r2n
qqE0Zp52selXsKGFYoG0GM5bwz1bSFtCt+AZQMhkWQheI3poZAToYJu69pHLKS6Q
XBiwBC1cvzYmUYKMYZC7jE5YhEU2bSL0mX7NaMxMDmH2/NwuOVRj8OImVa5s1F4U
zn4Kv3PFlDBjjSjXKVY9kmjUBsXQrIHeaqmUIsPIlNWUnimXS0I0abExqkbdrXbX
YwCOXhOO2pDUx3ckmJlCMUGacUTnylyQW2VsJIyIGA8V0xzdaeUXg0VZ6ZmNUr5Y
Ber/EAOLPb8NYpsAhJe2mXjMB/J9HNsoFMBFJ0lLOT/+dQvjbdRZoOT8eqJpWnVD
U+QL/qEZnz57N88OWM3rabJkRNdU/Z7x5SFIM9FrqtN8xewsiBWBI0K6XFuOBOTD
4V08o4TzJ8+Ccq5XlCUW2L48pZNCYuBDfBh7FxkB7qDgGDiaftEkZZfApRg2E+M9
G8wkNKTPLDc4wH0FDTijhgxR3Y4PiS1HL2Zhw7bD3CbslmEGgfnnZojNkJtcLeBH
BLa52/dSwNU4WWLubaYSiAmA9IUMX1/RpfpxOxd4Ykmhz97oFbUaDJFipIggx5sX
ePAlkTdWnv+RWBxlJwMQ25oEHmRguNYf4Zr/Rxr9cS93Y+mdXIZaBEE0KS2iLRqa
OiWBki9IMQU4phqPOBAaG7A+eP8PAgMBAAGjZjBkMB0GA1UdDgQWBBTh0YHlzlpf
BKrS6badZrHF+qwshzAfBgNVHSMEGDAWgBTh0YHlzlpfBKrS6badZrHF+qwshzAS
BgNVHRMBAf8ECDAGAQH/AgEEMA4GA1UdDwEB/wQEAwIBhjANBgkqhkiG9w0BAQsF
AAOCAgEAALIY1wkilt/urfEVM5vKzr6utOeDWCUczmWX/RX4ljpRdgF+5fAIS4vH
tmXkqpSCOVeWUrJV9QvZn6L227ZwuE15cWi8DCDal3Ue90WgAJJZMfTshN4OI8cq
W9E4EG9wglbEtMnObHlms8F3CHmrw3k6KmUkWGoa+/ENmcVl68u/cMRl1JbW2bM+
/3A+SAg2c6iPDlehczKx2oa95QW0SkPPWGuNA/CE8CpyANIhu9XFrj3RQ3EqeRcS
AQQod1RNuHpfETLU/A2gMmvn/w/sx7TB3W5BPs6rprOA37tutPq9u6FTZOcG1Oqj
C/B7yTqgI7rbyvox7DEXoX7rIiEqyNNUguTk/u3SZ4VXE2kmxdmSh3TQvybfbnXV
4JbCZVaqiZraqc7oZMnRoWrXRG3ztbnbes/9qhRGI7PqXqeKJBztxRTEVj8ONs1d
WN5szTwaPIvhkhO3CO5ErU2rVdUr89wKpNXbBODFKRtgxUT70YpmJ46VVaqdAhOZ
D9EUUn4YaeLaS8AjSF/h7UkjOibNc4qVDiPP+rkehFWM66PVnP1Msh93tc+taIfC
EYVMxjh8zNbFuoc7fzvvrFILLe7ifvEIUqSVIC/AzplM/Jxw7buXFeGP1qVCBEHq
391d/9RAfaZ12zkwFsl+IKwE/OZxW8AHa9i1p4GO0YSNuczzEm4=
-----END CERTIFICATE-----
"""


def make_ssl_context(ca_file="", verify=True):
    ctx = ssl.create_default_context(cafile=ca_file or None)
    if not ctx.cert_store_stats().get("x509_ca"):
        # Python с python.org на macOS часто идёт без списка корневых сертификатов
        try:
            import certifi  # noqa
            ctx.load_verify_locations(cafile=certifi.where())
        except Exception:  # noqa: BLE001
            for path in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
                if os.path.isfile(path):
                    try:
                        ctx.load_verify_locations(cafile=path)
                        break
                    except ssl.SSLError:
                        pass
    ctx.load_verify_locations(cadata=RUSSIAN_TRUSTED_ROOT_CA)
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ═══════════════════════════════ настройки ═══════════════════════════════

_cfg_lock = threading.Lock()


def _private_write(path, data_bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, threading.get_ident())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data_bytes)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    if os.environ.get("TINVEST_TOKEN"):
        cfg["token"] = os.environ["TINVEST_TOKEN"]
    return cfg


def make_backup():
    """Zip с согласованной копией базы и настройками БЕЗ токена и других секретов (SECRET_KEYS)."""
    tmp = os.path.join(APP_DIR, "backup.%d.tmp" % threading.get_ident())
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        cfg = {k: v for k, v in load_config().items() if k not in SECRET_KEYS}     # токен и прочие секреты не входят
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "data.db")
            z.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=2))
            z.writestr("README.txt", "Резервная копия T-Invest Analytics. Токены и пароли в копию не входят.\n"
                       "Восстановление: закройте программу и положите data.db в папку данных (%s).\n" % APP_DIR)
        return buf.getvalue()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def save_config(cfg):
    with _cfg_lock:
        _private_write(CONFIG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"))


def token_key(cfg):
    return ("sb_" if cfg["sandbox"] else "pr_") + hashlib.sha256(cfg["token"].encode()).hexdigest()[:16]


# ═══════════════════════════════ локальная база ═══════════════════════════════

class Store:
    """SQLite в ~/.tinvest_analytics/data.db: операции, свечи, справочники, импорт."""

    def __init__(self, path):
        self.path = path
        self.local = threading.local()
        self.wlock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
        c = self.conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT, t REAL);
            CREATE TABLE IF NOT EXISTS ops(acc TEXT, k TEXT, d TEXT, v TEXT, PRIMARY KEY(acc, k));
            CREATE INDEX IF NOT EXISTS ops_acc_d ON ops(acc, d);
            CREATE TABLE IF NOT EXISTS candles(uid TEXT, d TEXT, c REAL, PRIMARY KEY(uid, d));
            CREATE TABLE IF NOT EXISTS snaps(acc TEXT, d TEXT, total REAL, PRIMARY KEY(acc, d));
        """)
        c.commit()

    def conn(self):
        c = getattr(self.local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=60, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self.local.c = c
        return c

    def write(self, sql, rows=None, many=False):
        with self.wlock:
            c = self.conn()
            if many:
                c.executemany(sql, rows)
            else:
                c.execute(sql, rows or ())
            c.commit()

    def get(self, k, ttl=None):
        r = self.conn().execute("SELECT v, t FROM kv WHERE k=?", (k,)).fetchone()
        if not r or (ttl is not None and time.time() - r[1] > ttl):
            return None
        return json.loads(r[0])

    def put(self, k, v):
        self.write("INSERT OR REPLACE INTO kv(k, v, t) VALUES(?,?,?)", (k, json.dumps(v, ensure_ascii=False), time.time()))

    def put_many(self, items):
        now = time.time()
        self.write("INSERT OR REPLACE INTO kv(k, v, t) VALUES(?,?,?)",
                   [(k, json.dumps(v, ensure_ascii=False), now) for k, v in items], many=True)

    def delete_prefix(self, prefix):
        self.write("DELETE FROM kv WHERE k LIKE ?", (prefix + "%",))

    def ops(self, acc):
        return [json.loads(v) for (v,) in self.conn().execute("SELECT v FROM ops WHERE acc=? ORDER BY d, k", (acc,))]

    def ops_put(self, acc, ops):
        self.write("INSERT OR REPLACE INTO ops(acc, k, d, v) VALUES(?,?,?,?)",
                   [(acc, op_key(o), o.get("date") or "", json.dumps(o, ensure_ascii=False)) for o in ops], many=True)

    def ops_clear(self, acc):
        self.write("DELETE FROM ops WHERE acc=?", (acc,))

    def candles(self, uid):
        return self.conn().execute("SELECT d, c FROM candles WHERE uid=? ORDER BY d", (uid,)).fetchall()

    def candles_put(self, uid, rows):
        if rows:
            self.write("INSERT OR REPLACE INTO candles(uid, d, c) VALUES(?,?,?)", [(uid, d, c) for d, c in rows], many=True)

    def snap(self, acc, total):
        self.write("INSERT OR REPLACE INTO snaps(acc, d, total) VALUES(?,?,?)", (acc, date.today().isoformat(), total))

    def wipe_cache(self):
        with self.wlock:
            c = self.conn()
            c.execute("DELETE FROM kv WHERE k NOT LIKE 'imports%'")
            c.execute("DELETE FROM ops WHERE acc NOT LIKE 'imp-%'")
            c.execute("DELETE FROM candles")
            c.commit()


STORE = None
_klocks, _klocks_lock = {}, threading.Lock()


def key_lock(key):
    """Блокировка на ключ: одинаковую тяжёлую работу (запросы к API) параллельные потоки выполняют по одному разу."""
    with _klocks_lock:
        lk = _klocks.get(key)
        if lk is None:
            lk = _klocks[key] = threading.Lock()
        return lk


def store():
    global STORE
    if STORE is None:
        STORE = Store(DB_PATH)
    return STORE


# ═══════════════════════════════ API-клиент ═══════════════════════════════

class ApiError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def q2d(v):
    """Quotation / MoneyValue -> Decimal (units и nano имеют одинаковый знак)."""
    if not v:
        return D0
    if isinstance(v, (int, float, str)):
        return Decimal(str(v))
    return Decimal(str(v.get("units") or "0")) + Decimal(int(v.get("nano") or 0)) / Decimal(10 ** 9)


def qf(v):
    return float(q2d(v))


def cur_of(v, default="rub"):
    return ((v or {}).get("currency") or default).lower() if isinstance(v, dict) else default


def to_money(amount, currency="rub"):
    amount = Decimal(str(amount))
    units = int(amount)
    return {"currency": currency, "units": str(units), "nano": int((amount - units) * 10 ** 9)}


def iso_date(s):
    """'2026-01-15T00:00:00Z' -> '2026-01-15'; пустые даты API (1970 год) -> None."""
    if not s or str(s).startswith("1970"):
        return None
    return str(s)[:10]


def utc_now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


API_SEM = threading.BoundedSemaphore(10)      # одновременно не больше 10 запросов к API: не устраиваем шторм


class TInvest:
    _good_host = {}
    _ctx_cache = {}

    def __init__(self, cfg):
        self.token = (cfg.get("token") or "").strip()
        self.sandbox = bool(cfg.get("sandbox"))
        self.hosts = [h for h in cfg["hosts_sandbox" if self.sandbox else "hosts_prod"] if h]
        key = (cfg.get("ca_file") or "", bool(cfg.get("verify_ssl", True)))
        if key not in TInvest._ctx_cache:
            TInvest._ctx_cache[key] = make_ssl_context(*key)
        self.ctx = TInvest._ctx_cache[key]

    @property
    def ready(self):
        return bool(self.token)

    def call(self, service, method, body=None, timeout=60):
        if not self.token:
            raise ApiError("Не задан API-токен — откройте «Настройки».", 400)
        payload = json.dumps(body or {}).encode()
        pref = TInvest._good_host.get(self.sandbox)
        hosts = ([pref] if pref in self.hosts else []) + [h for h in self.hosts if h != pref]
        last = None
        for host in hosts:
            url = "%s/%s.%s/%s" % (host.rstrip("/"), CONTRACT, service, method)
            for attempt in range(6):
                req = urllib.request.Request(url, data=payload, method="POST", headers={
                    "Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                    "Accept": "application/json", "x-app-name": "tinvest-analytics"})
                try:
                    with API_SEM:
                        with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
                            TInvest._good_host[self.sandbox] = host
                            return json.loads(r.read().decode("utf-8") or "{}")
                except urllib.error.HTTPError as e:
                    raw = e.read().decode("utf-8", "replace")
                    if (e.code in (429, 503, 504) or (e.code >= 500 and "RESOURCE_EXHAUSTED" in raw)) and attempt < 5:
                        try:
                            wait = float(e.headers.get("x-ratelimit-reset") or 1)
                        except ValueError:
                            wait = 1.0
                        time.sleep(min(wait, 30) + 0.4 * (attempt + 1))
                        continue
                    try:
                        j = json.loads(raw)
                        msg = j.get("message") or j.get("description") or raw
                    except ValueError:
                        msg = raw[:300]
                    hint = {401: "токен недействителен или не подходит к режиму (боевой / песочница)",
                            403: "у токена нет прав на этот метод"}.get(e.code, "")
                    raise ApiError("%s: HTTP %s — %s%s" % (method, e.code, str(msg).strip(), (" (%s)" % hint) if hint else ""),
                                   e.code if e.code in (400, 401, 403, 404) else 502)
                except (urllib.error.URLError, OSError, ssl.SSLError) as e:
                    last = e
                    break
        hint = (" Сертификат сервера не прошёл проверку. Обычно так бывает, когда VPN, прокси или антивирус "
                "подменяет сертификаты: попробуйте отключить их.") if "CERTIFICATE" in str(last).upper() else ""
        raise ApiError("Нет связи с T-Invest API: %s.%s" % (last, hint))

    # — счета и портфель —
    def accounts(self):
        if self.sandbox:
            return self.call("SandboxService", "GetSandboxAccounts").get("accounts", [])
        return self.call("UsersService", "GetAccounts", {"status": "ACCOUNT_STATUS_ALL"}).get("accounts", [])

    def portfolio(self, acc):
        svc, m = ("SandboxService", "GetSandboxPortfolio") if self.sandbox else ("OperationsService", "GetPortfolio")
        return self.call(svc, m, {"accountId": acc, "currency": "RUB"})

    def margin(self, acc):
        if self.sandbox:
            return None
        try:
            return self.call("UsersService", "GetMarginAttributes", {"accountId": acc}, timeout=20)
        except ApiError:
            return None

    def operations(self, acc, dt_from, dt_to):
        svc, m = ("SandboxService", "GetSandboxOperationsByCursor") if self.sandbox else \
            ("OperationsService", "GetOperationsByCursor")
        items, cursor = [], ""
        for _ in range(5000):
            r = self.call(svc, m, {"accountId": acc, "from": dt_from, "to": dt_to, "cursor": cursor, "limit": 1000,
                                   "state": "OPERATION_STATE_EXECUTED", "withoutCommissions": False,
                                   "withoutTrades": False, "withoutOvernights": False}, timeout=120)
            items.extend(r.get("items") or [])
            if not r.get("hasNext") or not r.get("nextCursor") or r.get("nextCursor") == cursor:
                break
            cursor = r["nextCursor"]
        return items

    # — справочники и рыночные данные —
    def instrument(self, uid=None, figi=None):
        body = {"idType": "INSTRUMENT_ID_TYPE_UID", "id": uid} if uid else {"idType": "INSTRUMENT_ID_TYPE_FIGI", "id": figi}
        return self.call("InstrumentsService", "GetInstrumentBy", body, timeout=20).get("instrument") or {}

    def bond_by(self, uid):
        return self.call("InstrumentsService", "BondBy", {"idType": "INSTRUMENT_ID_TYPE_UID", "id": uid},
                         timeout=20).get("instrument") or {}

    def bond_coupons(self, uid, frm, to):
        return self.call("InstrumentsService", "GetBondCoupons",
                         {"instrumentId": uid, "from": frm, "to": to}, timeout=30).get("events") or []

    def dividends(self, uid, frm, to):
        return self.call("InstrumentsService", "GetDividends",
                         {"instrumentId": uid, "from": frm, "to": to}, timeout=20).get("dividends") or []

    def instruments_all(self, kind):
        """Справочник доступных инструментов одним запросом: kind in Bonds / Shares / Etfs (пакетно вместо GetInstrumentBy)."""
        return self.call("InstrumentsService", kind, {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}, timeout=90).get("instruments") or []

    def find(self, query):
        return self.call("InstrumentsService", "FindInstrument", {"query": query}, timeout=20).get("instruments") or []

    def candles(self, uid, frm, to):
        return self.call("MarketDataService", "GetCandles",
                         {"instrumentId": uid, "from": frm, "to": to, "interval": "CANDLE_INTERVAL_DAY"},
                         timeout=30).get("candles") or []

    def last_prices(self, uids):
        out = {}
        for i in range(0, len(uids), 300):
            r = self.call("MarketDataService", "GetLastPrices", {"instrumentId": uids[i:i + 300]}, timeout=30)
            for p in r.get("lastPrices") or []:
                k = p.get("instrumentUid") or p.get("figi")
                if k and p.get("price"):
                    out[k] = qf(p["price"])
        return out


def pool_map(fn, items, workers=8):
    items = list(items)
    if not items:
        return []
    if len(items) == 1:
        return [fn(items[0])]
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        return list(ex.map(fn, items))


# ═══════════════════════════════ справочник инструментов ═══════════════════════════════

TYPE_FROM_KIND = {"INSTRUMENT_TYPE_BOND": "bond", "INSTRUMENT_TYPE_SHARE": "share", "INSTRUMENT_TYPE_ETF": "etf",
                  "INSTRUMENT_TYPE_CURRENCY": "currency", "INSTRUMENT_TYPE_FUTURES": "futures",
                  "INSTRUMENT_TYPE_OPTION": "option", "INSTRUMENT_TYPE_SP": "sp"}


def inst_key(uid, figi):
    return uid or figi or ""


_inst_lock = threading.Lock()
_bulk = {}                        # вид справочника -> (время, {uid|figi: (info, параметры облигации | None)})
_bulk_lock = threading.Lock()
BULK_TTL = 3600


def inst_info_from(i, kind=None):
    b = i.get("brand") or {}
    return {"uid": i.get("uid") or "", "figi": i.get("figi") or "", "ticker": i.get("ticker") or "",
            "isin": i.get("isin") or "", "name": i.get("name") or "", "type": i.get("instrumentType") or kind or "",
            "cur": (i.get("currency") or "rub").lower(), "sector": i.get("sector") or "",
            "logo": b.get("logoName") or "", "color": b.get("logoBaseColor") or "",
            "country": i.get("countryOfRisk") or "", "cls": i.get("classCode") or ""}


def bond_params(r):
    """Параметры облигации из ответа BondBy / Bonds (одинаковая структура)."""
    return {"nominal": qf(r.get("nominal")) or qf(r.get("initialNominal")) or 1000.0,
            "initial": qf(r.get("initialNominal")), "cur": cur_of(r.get("nominal")),
            "maturity": iso_date(r.get("maturityDate")), "call": iso_date(r.get("callDate")),
            "placement": iso_date(r.get("placementDate")), "cpy": int(r.get("couponQuantityPerYear") or 0),
            "aci": qf(r.get("aciValue")), "floating": bool(r.get("floatingCouponFlag")),
            "amort": bool(r.get("amortizationFlag")), "perpetual": bool(r.get("perpetualFlag")),
            "risk": r.get("riskLevel") or "", "sector": r.get("sector") or "", "name": r.get("name") or ""}


def bulk_catalog(client, endpoint, kind):
    """{uid|figi: (info, параметры облигации)} по одному запросу на весь справочник (держим в памяти час)."""
    with _bulk_lock:
        hit = _bulk.get(endpoint)
        if hit and time.time() - hit[0] < BULK_TTL:
            return hit[1]
    with key_lock("bulk:" + endpoint):
        hit = _bulk.get(endpoint)
        if hit and time.time() - hit[0] < BULK_TTL:
            return hit[1]
        d = {}
        try:
            for i in client.instruments_all(endpoint):
                v = (inst_info_from(i, kind), bond_params(i) if kind == "bond" else None)
                if i.get("uid"):
                    d[i["uid"]] = v
                if i.get("figi"):
                    d[i["figi"]] = v
        except ApiError:
            return {}
        with _bulk_lock:
            _bulk[endpoint] = (time.time(), d)
        return d


def instruments(client, keys):
    """keys: [(uid, figi)] -> {uid|figi: info}. Кэш в базе на 30 дней; отсутствующие берутся пакетно из справочников
    Bonds/Shares/Etfs (один запрос на справочник вместо запроса на каждый инструмент), остальное — по одному."""
    st = store()
    out, need = {}, []

    def scan(todo):
        miss = []
        for u, f in set(todo):
            k = inst_key(u, f)
            if not k:
                continue
            v = st.get("inst:" + k, ttl=30 * DAY)
            if v:
                out[k] = v
                if f:
                    out[f] = v
                if v.get("uid"):
                    out[v["uid"]] = v
            elif st.get("instmiss:" + k, ttl=DAY) is None:
                miss.append((u, f))
        return miss
    need = scan(keys)
    if need and client.ready:
        with _inst_lock:                       # параллельные запросы не дублируют работу
            need = scan(need)
            save = []
            if len(need) > 5:
                cats = pool_map(lambda e: bulk_catalog(client, *e), (("Bonds", "bond"), ("Shares", "share"), ("Etfs", "etf")))
                left, bsave = [], []
                for u, f in need:
                    hit = next((c[x] for c in cats for x in (u, f) if x and x in c), None)
                    if not hit:
                        left.append((u, f))
                        continue
                    info, bp = hit
                    for kk in {inst_key(u, f), info["uid"], info["figi"]}:
                        if kk:
                            out[kk] = info
                            save.append(("inst:" + kk, info))
                    if bp and info["uid"] and st.get("bond:" + info["uid"], ttl=12 * 3600) is None:
                        bsave.append(("bond:" + info["uid"], bp))
                if bsave:
                    st.put_many(bsave)
                need = left

            def one(k):
                u, f = k
                try:
                    i = client.instrument(uid=u, figi=None if u else f)
                except ApiError as e:
                    if e.status == 404:          # инструмента нет в справочнике: не спрашиваем повторно сутки
                        st.put("instmiss:" + inst_key(u, f), 1)
                    return k, None
                return k, inst_info_from(dict(i, uid=i.get("uid") or u or "", figi=i.get("figi") or f or ""))
            for k, v in pool_map(one, need[:400]):
                if v:
                    for kk in {inst_key(*k), v["uid"], v["figi"]}:
                        if kk:
                            out[kk] = v
                            save.append(("inst:" + kk, v))
            if save:
                st.put_many(save)
    return out


def bond_info(client, uid):
    """Параметры облигации и купоны; кэш: параметры 12 ч, купоны 3 дня (для погашенных — 60 дней)."""
    st = store()
    b = st.get("bond:" + uid, ttl=12 * 3600)
    if b is None and client.ready and st.get("bondmiss:" + uid, ttl=600) is None \
            and st.get("bondmiss404:" + uid, ttl=DAY) is None:
        with key_lock("bond:" + uid):
            b = st.get("bond:" + uid, ttl=12 * 3600)
            if b is None:
                r = None
                hit = (bulk_catalog(client, "Bonds", "bond") or {}).get(uid)
                if hit:
                    b = hit[1]
                else:
                    try:
                        r = client.bond_by(uid)
                    except ApiError as e:
                        # нет в справочнике — не спрашиваем сутки, API занят/ошибка — 10 минут
                        st.put("bondmiss404:" + uid if e.status == 404 else "bondmiss:" + uid, 1)
                    if r:
                        b = bond_params(r)
                if b:
                    st.put("bond:" + uid, b)
    if not b:
        return None
    matured = b.get("maturity") and b["maturity"] < date.today().isoformat()
    cp = st.get("cpn:" + uid, ttl=(60 if matured else 3) * DAY)
    if cp is None and client.ready:
        frm = (b.get("placement") or (date.today() - timedelta(days=3650)).isoformat()) + "T00:00:00Z"
        end = b.get("maturity") or (date.today() + timedelta(days=365 * 30)).isoformat()
        to = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=40)).strftime("%Y-%m-%dT00:00:00Z")
        try:
            ev = client.bond_coupons(uid, frm, to)
            cp = sorted([[iso_date(e.get("couponDate")), qf(e.get("payOneBond"))] for e in ev if iso_date(e.get("couponDate"))])
            st.put("cpn:" + uid, cp)
        except ApiError:
            cp = None
    b = dict(b)
    b["coupons"] = cp or []
    return b


def nkd_at(b, day):
    """НКД на дату по графику купонов (линейно между выплатами)."""
    cp = b.get("coupons") or []
    if not cp:
        return 0.0
    dates = [c[0] for c in cp]
    i = bisect.bisect_right(dates, day)
    if i >= len(cp):
        return 0.0
    nxt_d, pay = cp[i]
    if not pay:
        known = [c[1] for c in cp[:i] if c[1]]
        pay = known[-1] if known else 0.0
    prev_d = cp[i - 1][0] if i > 0 else b.get("placement")
    if not prev_d:
        return 0.0
    d0, d1, dd = (datetime.strptime(x, "%Y-%m-%d") for x in (prev_d, nxt_d, day))
    span = (d1 - d0).days
    return pay * max(0, (dd - d0).days) / span if span > 0 else 0.0


def bond_metrics(b, price_rub, today=None):
    """Доходность к погашению/оферте (эффективная), дюрация Маколея, купонная доходность."""
    today = today or date.today().isoformat()
    nominal = b.get("nominal") or 1000.0
    cp = b.get("coupons") or []
    known = [p for _, p in cp if p]
    last_pay = known[-1] if known else 0.0
    future = [(d, p) for d, p in cp if d > today]
    nxt = future[0] if future else None
    if nxt and not nxt[1]:
        nxt = (nxt[0], last_pay)
    cpy = b.get("cpy") or (len([1 for d, _ in cp if d[:4] == today[:4]]) or 0)
    annual = (nxt[1] if nxt else last_pay) * cpy if cpy else 0.0
    res = {"next": nxt, "coupon_rate": annual / nominal * 100 if nominal else None,
           "cur_yield": annual / price_rub * 100 if price_rub else None, "ytm": None, "dur": None, "to": None}
    end = b.get("call") if b.get("call") and b["call"] > today else b.get("maturity")
    if not end or b.get("perpetual") or not price_rub or end <= today:
        return res
    res["to"] = "offer" if end == b.get("call") else "maturity"
    t0 = datetime.strptime(today, "%Y-%m-%d")
    flows = []
    for d, p in future:
        if d > end:
            break
        flows.append(((datetime.strptime(d, "%Y-%m-%d") - t0).days / 365.0, p or last_pay))
    flows.append(((datetime.strptime(end, "%Y-%m-%d") - t0).days / 365.0, nominal))
    dirty = price_rub + (b.get("aci") if b.get("aci") is not None else nkd_at(b, today))

    def pv(y):
        return sum(a / (1 + y) ** t for t, a in flows)

    lo, hi = -0.95, 20.0
    if (pv(lo) - dirty) * (pv(hi) - dirty) > 0:
        return res
    for _ in range(120):
        mid = (lo + hi) / 2
        if pv(mid) > dirty:
            lo = mid
        else:
            hi = mid
    y = (lo + hi) / 2
    tot = pv(y)
    res["ytm"] = y * 100
    res["dur"] = sum(t * a / (1 + y) ** t for t, a in flows) / tot if tot else None
    return res


def benchmark_uid(client, ticker):
    st = store()
    v = st.get("bench:" + ticker, ttl=30 * DAY)
    if v:
        return v
    try:
        found = client.find(ticker)
    except ApiError:
        return None
    best = None
    for i in found:
        if (i.get("ticker") or "").upper() == ticker and i.get("uid"):
            if best is None or i.get("classCode") == "TQTF":
                best = i
    if best:
        st.put("bench:" + ticker, best["uid"])
        return best["uid"]
    return None


def candle_series(client, uid, d_from, d_to):
    """Дневные цены закрытия из локальной базы; недостающее догружается из API годовыми кусками."""
    st = store()
    meta = st.get("cs:" + uid) or {}
    need = []
    if not meta:
        need.append((d_from, d_to))
    else:
        if d_from < meta["from"]:
            need.append((d_from, meta["from"]))
        tail_from = min(meta["to"], (date.today() - timedelta(days=4)).isoformat())
        if d_to > tail_from:
            need.append((tail_from, d_to))
    ok = True
    if need and client.ready:
        for a, b in need:
            cur = datetime.strptime(a, "%Y-%m-%d")
            end = datetime.strptime(b, "%Y-%m-%d") + timedelta(days=1)
            while cur < end:
                nxt = min(end, cur + timedelta(days=364))
                try:
                    cs = client.candles(uid, cur.strftime("%Y-%m-%dT00:00:00Z"), nxt.strftime("%Y-%m-%dT00:00:00Z"))
                    st.candles_put(uid, [(c["time"][:10], qf(c.get("close"))) for c in cs if c.get("time") and c.get("close")])
                except ApiError:
                    ok = False
                    break
                cur = nxt
        if ok:
            st.put("cs:" + uid, {"from": min(d_from, meta.get("from", d_from)), "to": max(d_to, meta.get("to", d_to))})
    return st.candles(uid)


# ═══════════════════════════════ классификация операций ═══════════════════════════════

BUY = {"BUY", "BUY_CARD", "BUY_MARGIN", "DELIVERY_BUY"}
SELL = {"SELL", "SELL_CARD", "SELL_MARGIN", "DELIVERY_SELL"}
DIVS = {"DIVIDEND", "DIVIDEND_TRANSFER", "DIV_EXT"}
REPAY = {"BOND_REPAYMENT", "BOND_REPAYMENT_FULL"}
FEE_SERVICE = {"SERVICE_FEE", "CASH_FEE", "ADVICE_FEE"}
FEE_OTHER = {"SUCCESS_FEE", "TRACK_MFEE", "TRACK_PFEE", "OUT_FEE", "OUT_STAMP_DUTY", "OVER_COM", "OUTPUT_PENALTY"}
DEPOSIT = {"INPUT", "INPUT_SWIFT", "INPUT_ACQUIRING", "INP_MULTI"}
WITHDRAW = {"OUTPUT", "OUTPUT_SWIFT", "OUTPUT_ACQUIRING", "OUT_MULTI"}
TAXES = ("tax_trade", "tax_dividend", "tax_coupon", "tax_repo", "tax_other")
FEES = ("fee_broker", "fee_service", "fee_other", "margin_fee")
FLIP = set(TAXES) | set(FEES) | {"withdrawals"}


def op_type(o):
    return (o.get("type") or "").replace("OPERATION_TYPE_", "")


def classify(t):
    t = (t or "").replace("OPERATION_TYPE_", "")
    if t in BUY: return "buy"
    if t in SELL: return "sell"
    if t in DIVS: return "dividends"
    if t == "COUPON": return "coupons"
    if t in REPAY: return "repayments"
    if t in ("OVERNIGHT", "OVER_INCOME"): return "overnight"
    if t == "BROKER_FEE": return "fee_broker"
    if t == "MARGIN_FEE": return "margin_fee"
    if t in FEE_SERVICE: return "fee_service"
    if t in FEE_OTHER: return "fee_other"
    if t in ("ACCRUING_VARMARGIN", "WRITING_OFF_VARMARGIN"): return "varmargin"
    if "TAX" in t:
        if t.startswith("DIVIDEND_TAX"): return "tax_dividend"
        if t.startswith("BOND_TAX") or t == "TAX_CORRECTION_COUPON": return "tax_coupon"
        if t.startswith("TAX_REPO"): return "tax_repo"
        if t in ("TAX", "TAX_PROGRESSIVE", "TAX_CORRECTION", "TAX_CORRECTION_PROGRESSIVE"): return "tax_trade"
        return "tax_other"
    if t in DEPOSIT: return "deposits"
    if t in WITHDRAW: return "withdrawals"
    if t == "INPUT_SECURITIES": return "sec_in"
    if t == "OUTPUT_SECURITIES": return "sec_out"
    return "other"


def op_key(o):
    return o.get("id") or "%s|%s|%s|%s|%s" % (o.get("date"), o.get("type"), (o.get("payment") or {}).get("units"),
                                              (o.get("payment") or {}).get("nano"), o.get("instrumentUid") or o.get("figi"))


def op_qty(o):
    try:
        return int(Decimal(str(o.get("quantityDone") or o.get("quantity") or 0)))
    except Exception:  # noqa: BLE001
        return 0


def parse_dt(s):
    try:
        return datetime.strptime((s or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime((s or "")[:10], "%Y-%m-%d")
        except ValueError:
            return datetime(1970, 1, 1)


def ndfl_estimate(base, year):
    """НДФЛ с инвестиционного дохода: до 2021 — 13 %; 2021–2024 — 15 % свыше 5 млн; с 2025 — 15 % свыше 2,4 млн."""
    base = max(D0, base)
    if year < 2021:
        return base * Decimal("0.13")
    thr = Decimal(5_000_000 if year < 2025 else 2_400_000)
    return min(base, thr) * Decimal("0.13") + max(D0, base - thr) * Decimal("0.15")


def xirr(flows):
    if len(flows) < 2 or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    t0 = min(d for d, _ in flows)
    if (max(d for d, _ in flows) - t0).days < 30:
        return None
    pts = [((d - t0).days / 365.25, float(a)) for d, a in flows]

    def npv(r):
        return sum(a / (1 + r) ** t for t, a in pts)

    lo, hi = -0.99, 10.0
    f_lo = npv(lo)
    if f_lo * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f = npv(mid)
        if abs(f) < 1e-7:
            break
        if f_lo * f < 0:
            hi = mid
        else:
            lo, f_lo = mid, f
    return (lo + hi) / 2


def period_bounds(period, now):
    if period == "1m": return now - timedelta(days=30), None
    if period == "3m": return now - timedelta(days=91), None
    if period == "12m": return now - timedelta(days=365), None
    if period == "ytd": return datetime(now.year, 1, 1), None
    if period == "py": return datetime(now.year - 1, 1, 1), datetime(now.year, 1, 1)
    return None, None


def fifo(ops):
    """Позиции по сделкам методом FIFO: {uid: {qty, cost, last_unit}}, заодно результат продаж (op['_yield'])."""
    pos = defaultdict(lambda: {"lots": [], "last_unit": 0.0})
    for o in ops:
        k = classify(o.get("type"))
        uid = o.get("instrumentUid") or o.get("figi")
        q = op_qty(o)
        if not uid or k not in ("buy", "sell", "sec_in", "sec_out", "repayments") or not q:
            if k == "repayments" and uid and op_type(o) == "BOND_REPAYMENT_FULL":
                pos[uid]["lots"] = []
            continue
        pay = abs(qf(o.get("payment")))
        unit = pay / q if q else 0.0
        p = pos[uid]
        if unit:
            p["last_unit"] = unit
        if k in ("buy", "sec_in"):
            if k == "sec_in" and not unit:
                unit = qf(o.get("price")) or p["last_unit"]
            p["lots"].append([q, unit])
        elif k in ("sell", "sec_out"):
            left, cost = q, 0.0
            while left > 0 and p["lots"]:
                lot = p["lots"][0]
                take = min(left, lot[0])
                cost += take * lot[1]
                lot[0] -= take
                left -= take
                if lot[0] <= 0:
                    p["lots"].pop(0)
            if k == "sell":
                o["_yield"] = pay - cost
        elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL":
            p["lots"] = []
    out = {}
    for uid, p in pos.items():
        qty = sum(l[0] for l in p["lots"])
        if qty:
            out[uid] = {"qty": qty, "cost": sum(l[0] * l[1] for l in p["lots"]), "last_unit": p["last_unit"]}
    return out


# ═══════════════════════════════ аналитика операций ═══════════════════════════════

def info_name(info, o=None):
    return (info or {}).get("name") or (o or {}).get("name") or (info or {}).get("ticker") or ""


def analyze(ops, names, period, portfolio_value):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    p_from, p_to = period_bounds(period, now)
    accs_with_broker_ops = {o.get("_acc") for o in ops if classify(o.get("type")) == "fee_broker"}
    dd = lambda: defaultdict(Decimal)
    totals, life, years, months = defaultdict(dd), dd(), defaultdict(dd), defaultdict(dd)
    flows, rows, by_inst = [], [], defaultdict(lambda: [D0, "", "", "", ""])

    for o in ops:
        kind = classify(o.get("type"))
        dt = parse_dt(o.get("date"))
        pay, cur = q2d(o.get("payment")), cur_of(o.get("payment"))
        comm, ccur = q2d(o.get("commission")), cur_of(o.get("commission"), cur)
        yv = o.get("yield")
        yld = q2d(yv) if yv else Decimal(str(o.get("_yield") or 0))
        ycur = cur_of(yv, cur) if yv else cur
        in_p = (p_from is None or dt >= p_from) and (p_to is None or dt < p_to)

        entries = []
        if kind == "buy":
            entries.append(("buy_turnover", cur, abs(pay)))
        elif kind == "sell":
            entries += [("sell_turnover", cur, abs(pay)), ("realized", ycur, yld)]
        elif kind not in ("other", "sec_in", "sec_out"):
            entries.append((kind, cur, -pay if kind in FLIP else pay))
        if kind in ("buy", "sell") and comm and o.get("_acc") not in accs_with_broker_ops:
            entries.append(("fee_broker", ccur, -comm if comm < 0 else comm))

        for cat, c, amt in entries:
            if c == "rub":
                life[cat] += amt
                years[dt.year][cat] += amt
            if in_p:
                totals[c][cat] += amt
                if c == "rub":
                    months[dt.strftime("%Y-%m")][cat] += amt

        if kind in ("deposits", "withdrawals") and cur == "rub" and pay:
            flows.append((dt, abs(pay) if kind == "withdrawals" else -abs(pay)))
        if not in_p:
            continue
        info = names.get(o.get("instrumentUid") or o.get("figi") or "") or {}
        nm = info_name(info, o) if (o.get("instrumentUid") or o.get("figi")) else (o.get("name") or o.get("description") or "")
        if kind in ("dividends", "coupons") and cur == "rub":
            k = info.get("uid") or nm or "—"
            b = by_inst[k]
            b[0] += pay
            b[1], b[2], b[3], b[4] = nm or "—", info.get("ticker") or "", info.get("logo") or "", info.get("type") or ""
        rows.append([
            (o.get("date") or "")[:16].replace("T", " "), op_type(o), kind, nm, info.get("ticker") or "",
            op_qty(o), float(q2d(o.get("price"))), float(pay), cur, float(comm), float(yld),
            info.get("logo") or "", o.get("_accname") or ""])

    invested = life["deposits"] - life["withdrawals"]
    pv = Decimal(str(portfolio_value or 0))
    rate = xirr(flows + ([(now, pv)] if pv > 0 else []))

    tax_rows = []
    for y in sorted(years):
        r = years[y]
        trade = r["realized"]
        income = r["dividends"] + r["coupons"] + r["overnight"]
        if not (trade or income or any(r[k] for k in TAXES)):
            continue
        est = ndfl_estimate(max(D0, trade) + income, y)
        withheld = sum(r[k] for k in TAXES)
        tax_rows.append({"year": y, "trade": float(trade), "income": float(income), "estimate": float(est),
                         "withheld": float(withheld), "diff": float(est - withheld)})

    f = lambda d: {k: float(v) for k, v in d.items()}
    income_by = sorted(([float(v[0]), v[1], v[2], v[3], v[4]] for v in by_inst.values()), key=lambda r: -r[0])[:15]
    return {
        "totals": {c: f(v) for c, v in totals.items()}, "life": f(life), "invested": float(invested), "xirr": rate,
        "profit": float(pv - invested) if life["deposits"] else None,
        "months": [[m, f(v)] for m, v in sorted(months.items())],
        "tax": tax_rows, "ops": rows[::-1], "income_by": income_by,
        "first_op": ops[0]["date"][:10] if ops else None,
    }


# ═══════════════════════════════ позиции ═══════════════════════════════

def pos_row(info, **kw):
    info = info or {}
    r = {"uid": info.get("uid") or kw.get("uid") or "", "ticker": info.get("ticker") or kw.get("ticker") or "",
         "name": info.get("name") or kw.get("name") or info.get("ticker") or kw.get("ticker") or "",
         "logo": info.get("logo") or "", "color": info.get("color") or "", "sector": info.get("sector") or "",
         "type": kw.get("type") or info.get("type") or "", "qty": 0.0, "avg": 0.0, "price": 0.0, "cur": "rub",
         "value": 0.0, "value_rub": None, "cost_rub": 0.0, "pnl": 0.0, "pnl_rub": None, "pnl_pct": None,
         "daily": None, "blocked": False, "nkd": 0.0}
    r.update({k: v for k, v in kw.items() if k not in ("uid", "ticker", "name") or v})
    return r


CUR_TICKERS = {"usd": "USD000UTSTOM", "eur": "EUR_RUB__TOM", "cny": "CNYRUB_TOM", "hkd": "HKDRUB_TOM",
               "gbp": "GBPRUB_TOM", "chf": "CHFRUB_TOM", "jpy": "JPYRUB_TOM", "try": "TRYRUB_TOM",
               "kzt": "KZTRUB_TOM", "byn": "BYNRUB_TOM", "amd": "AMDRUB_TOM"}


def fx_uid(client, cur):
    st = store()
    v = st.get("fxuid:" + cur, ttl=30 * DAY)
    if v or cur not in CUR_TICKERS or not client.ready:
        return v
    try:
        found = client.find(CUR_TICKERS[cur])
    except ApiError:
        return None
    for i in found:
        if (i.get("ticker") or "").upper() == CUR_TICKERS[cur] and i.get("uid"):
            st.put("fxuid:" + cur, i["uid"])
            return i["uid"]
    return None


def fx_now(client, curs):
    out = {"rub": 1.0}
    need = {c: fx_uid(client, c) for c in curs if c != "rub"}
    uids = [u for u in need.values() if u]
    lp = {}
    if uids and client.ready:
        try:
            lp = client.last_prices(uids)
        except ApiError:
            lp = {}
    for c, u in need.items():
        if u and lp.get(u):
            out[c] = lp[u]
    return out


def tinvest_positions(port, names):
    raw = port.get("positions") or []
    fx = {"rub": 1.0}
    for x in raw:
        if x.get("instrumentType") == "currency":
            info = names.get(x.get("instrumentUid") or x.get("figi")) or {}
            iso = (x.get("ticker") or info.get("ticker") or "")[:3].lower()
            if iso and iso != "rub" and qf(x.get("currentPrice")) > 0:
                fx[iso] = qf(x.get("currentPrice"))
    out = []
    for x in raw:
        info = names.get(x.get("instrumentUid") or x.get("figi")) or {}
        qty = qf(x.get("quantity"))
        avg = qf(x.get("averagePositionPriceFifo")) or qf(x.get("averagePositionPrice"))
        price = qf(x.get("currentPrice"))
        nkd = qf(x.get("currentNkd"))
        cur = cur_of(x.get("currentPrice"))
        itype = x.get("instrumentType") or info.get("type") or ""
        if itype == "futures":
            value, cost = qf(x.get("varMargin")), 0.0
        else:
            value, cost = qty * (price + nkd), qty * avg
        if x.get("expectedYieldFifo") or x.get("expectedYield"):
            pnl = qf(x.get("expectedYieldFifo")) or qf(x.get("expectedYield"))
        else:
            pnl = qty * (price - avg) if avg else 0.0
        rate = fx.get(cur)
        tk = x.get("ticker") or info.get("ticker") or (x.get("figi") or "")[:12]
        if itype == "currency":
            tk = tk[:3].upper()
            info = dict(info, name=CUR_NAMES.get(tk, info.get("name") or tk), ticker=tk)
        out.append(pos_row(info, uid=x.get("instrumentUid") or info.get("uid") or x.get("figi") or "", ticker=tk,
                           type=itype, qty=qty, avg=avg, price=price, cur=cur, nkd=nkd, value=value,
                           value_rub=value * rate if rate is not None else None,
                           cost_rub=cost * rate if rate is not None else 0.0, pnl=pnl,
                           pnl_rub=pnl * rate if rate is not None else None,
                           pnl_pct=pnl / cost * 100 if cost else None,
                           daily=qf(x.get("dailyYield")) if x.get("dailyYield") else None, blocked=bool(x.get("blocked"))))
    return out


CUR_NAMES = {"RUB": "Рубли", "USD": "Доллар США", "EUR": "Евро", "CNY": "Китайский юань", "HKD": "Гонконгский доллар",
             "GBP": "Фунт стерлингов", "CHF": "Швейцарский франк", "KZT": "Тенге", "TRY": "Турецкая лира",
             "AMD": "Армянский драм", "BYN": "Белорусский рубль", "JPY": "Японская иена"}


def imported_positions(client, ops, names):
    f = fifo(ops)
    real = [u for u in f if not u.startswith("imp:")]
    lp = {}
    if real and client.ready:
        try:
            lp = client.last_prices(real)
        except ApiError:
            lp = {}
    curs = {(names.get(u) or {}).get("cur", "rub") for u in f}
    cash = defaultdict(float)
    for o in ops:
        cash[cur_of(o.get("payment"))] += qf(o.get("payment"))
    fx = fx_now(client, curs | set(cash))
    out = []
    for uid, p in f.items():
        info = names.get(uid) or {"name": next((o.get("name") for o in ops if (o.get("instrumentUid") or o.get("figi")) == uid), uid),
                                  "ticker": uid.replace("imp:", "")[:14]}
        itype = info.get("type") or next((TYPE_FROM_KIND.get(o.get("instrumentKind")) for o in ops
                                          if (o.get("instrumentUid") or o.get("figi")) == uid and o.get("instrumentKind")), "") or ""
        qty, cost = p["qty"], p["cost"]
        cur = info.get("cur") or "rub"
        nkd, unit = 0.0, None
        if uid in lp:
            unit = lp[uid]
            if itype == "bond":
                b = bond_info(client, uid)
                nominal = (b or {}).get("nominal") or 1000.0
                unit = unit / 100.0 * nominal
                nkd = (b or {}).get("aci") or 0.0
        if unit is None:
            unit = p["last_unit"]
        value = qty * (unit + nkd)
        rate = fx.get(cur)
        pnl = qty * unit - cost
        out.append(pos_row(info, uid=uid, type=itype, qty=qty, avg=cost / qty if qty else 0.0, price=unit, cur=cur, nkd=nkd,
                           value=value, value_rub=value * rate if rate else None, cost_rub=cost * (rate or 1.0),
                           pnl=pnl, pnl_rub=pnl * rate if rate else None, pnl_pct=pnl / cost * 100 if cost else None))
    for c, v in cash.items():
        if abs(v) >= 0.01:
            rate = fx.get(c)
            iso = c.upper()
            out.append(pos_row({"name": CUR_NAMES.get(iso, iso), "ticker": iso}, uid="cash:" + c, type="currency",
                               qty=v, price=rate or 0.0, avg=0.0, cur="rub", value=v * (rate or 0.0),
                               value_rub=v * rate if rate else None, pnl=0.0, pnl_rub=0.0))
    return out


def merge_positions(lists):
    acc = {}
    for rows in lists:
        for r in rows:
            k = r["uid"] or r["ticker"]
            if r["type"] == "currency":
                k = "cur:" + (r["ticker"] or "")[:3].upper()
            if k not in acc:
                acc[k] = dict(r)
                continue
            a = acc[k]
            for f in ("qty", "value", "cost_rub", "pnl"):
                a[f] = (a.get(f) or 0.0) + (r.get(f) or 0.0)
            for f in ("value_rub", "pnl_rub", "daily"):
                if a.get(f) is not None or r.get(f) is not None:
                    a[f] = (a.get(f) or 0.0) + (r.get(f) or 0.0)
            a["blocked"] = a["blocked"] or r["blocked"]
    out = list(acc.values())
    for r in out:
        if r["type"] != "currency" and r["qty"]:
            if r.get("cost_rub") and r.get("value_rub") is not None and r["cur"] == "rub":
                r["avg"] = r["cost_rub"] / r["qty"]
            if r.get("cost_rub") and r.get("pnl_rub") is not None:
                r["pnl_pct"] = r["pnl_rub"] / r["cost_rub"] * 100
    total = sum((r["value_rub"] or 0) for r in out if r["type"] != "futures") or 1
    for r in out:
        r["share"] = (r["value_rub"] or 0) / total * 100 if r["type"] != "futures" else 0
    out.sort(key=lambda r: -(r["value_rub"] if r["value_rub"] is not None else r["value"]))
    return out


def totals_from_rows(rows):
    t = defaultdict(float)
    for r in rows:
        v = r["value_rub"] or 0.0
        t[{"share": "shares", "bond": "bonds", "etf": "etf", "currency": "currencies", "futures": "futures",
           "option": "options", "sp": "sp"}.get(r["type"], "other")] += v
    t["total"] = sum(v for k, v in t.items() if k != "futures")
    return t


# ═══════════════════════════════ облигации и выплаты ═══════════════════════════════

def _spread(ytm, dur):
    try:
        k = kbd_at(dur) if ytm is not None and dur else None
        return round(ytm - k, 2) if k is not None else None
    except Exception:  # noqa: BLE001
        return None


RISK_RU = {"RISK_LEVEL_LOW": "низкий", "RISK_LEVEL_MODERATE": "средний", "RISK_LEVEL_HIGH": "высокий"}


STRESS_DY = (-3, -2, -1, 1, 2, 3)
YTM_HIGH = 100.0         # доходность выше 100% годовых — «высокий риск дефолта»: только помечается, из расчётов НЕ исключается


def bond_isin(r):
    inst = store().get("inst:" + (r.get("uid") or ""), ttl=30 * DAY) or {}
    return (inst.get("isin") or r.get("ticker") or "").upper()


def portfolio_irr(items, today):
    """Единая доходность облигационного портфеля (IRR): все будущие потоки позиций (потоки на 1 бумагу x количество,
    в рублях по текущему курсу валюты номинала) против суммарной текущей стоимости с НКД. Одно решение cf_ytm.
    irr_tax — то же после НДФЛ: потоки каждой бумаги берутся уже за вычетом налога (net_flows), дальше без налога.
    Бумаги без точных потоков (приближённый расчёт) в IRR не входят: value/count показывают охват.
    Возвращает {irr, irr_tax, value (в рублях, стоимость с НКД), count}; доходности в %."""
    gross, net, dirty = defaultdict(float), defaultdict(float), 0.0
    for ex, qty, fx in items:
        k = qty * fx
        dirty += ex["dirty"] * k
        for d, c, p in ex["flows"]:
            if d > today:
                gross[d] += (c + p) * k
        for d, a in net_flows(ex["flows"], today, ex["basis"]):
            net[d] += a * k
    res = {"irr": None, "irr_tax": None, "value": dirty, "count": len(items)}
    if dirty > 0 and gross:
        y = cf_ytm(dirty, [(d, a, 0.0) for d, a in sorted(gross.items())], today)
        yt = cf_ytm(dirty, [(d, a, 0.0) for d, a in sorted(net.items())], today)
        res["irr"] = y * 100 if y is not None else None
        res["irr_tax"] = yt * 100 if yt is not None else None
    return res


def keyrate_brief():
    """Короткая сводка об использованном прогнозе ключевой ставки для UI (без пути)."""
    try:
        i = keyrate_forecast_info()
        return {"source": i["source"], "name": i["source_name"], "as_of": i["as_of"], "key_rate": i["key_rate"],
                "yearly": i["yearly"], "mode": i["mode"]}
    except Exception:  # noqa: BLE001
        return None


def bond_exact(client, r, b, today, rates):
    """Точный расчёт по потокам MOEX. Возвращает словарь полей строки либо None (тогда — приближение)."""
    if b.get("perpetual") or not b.get("maturity"):
        return None
    isin = bond_isin(r)
    try:
        bz = moex_bondization(isin)
    except Exception:  # noqa: BLE001
        return None
    if not bz:
        return None
    face = b.get("nominal") or 1000.0
    price, avg, aci = bond_price_face(r, b, rates)
    if not price:
        return None
    est = {}
    flows, kind, end = bond_flows(bz, today, face, floating=bool(b.get("floating")), est_out=est)
    if not flows or end <= today:
        return None
    if kind == "maturity" and abs((datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(b["maturity"], "%Y-%m-%d")).days) > 45:
        return None                      # график MOEX не сходится с данными брокера
    dirty = price + aci
    y = cf_ytm(dirty, flows, today)
    if y is None:
        return None
    yt = cf_ytm(dirty, flows, today, tax=True, basis=price)
    mac, mod, conv = cf_risk(flows, today, y)
    st = stress(price / face * 100.0, flows, today, face, aci, STRESS_DY, y)
    return {"isin": isin, "ytm": y * 100, "ytm_tax": yt * 100 if yt is not None else None, "dur": mac, "mdur": mod,
            "convexity": conv, "to": kind, "end": end, "stress_pct": {dy: (p / 100.0 * face + aci) / dirty * 100 - 100
                                                                      for dy, p in st.items()},
            "cf_source": "moex", "est_coupons": len(est), "est_detail": est, "bz": bz, "flows": flows, "basis": price, "dirty": dirty}


def bond_price_face(r, b, rates):
    """(чистая цена, средняя цена покупки, НКД) на одну облигацию в ВАЛЮТЕ НОМИНАЛА. Цена позиции приходит в валюте
    r['cur'] (для валютных облигаций T-Invest отдаёт её в рублях, номинал — в USD/EUR), поэтому конвертируем."""
    fc = (b.get("cur") or "rub").lower()
    k = 1.0
    if r["cur"] != fc:
        rp = 1.0 if r["cur"] == "rub" else (r["value_rub"] / r["value"] if r.get("value") and r.get("value_rub") else rates.get(r["cur"]))
        rf = 1.0 if fc == "rub" else rates.get(fc)
        if not rp or not rf:
            return 0.0, 0.0, 0.0
        k = rp / rf
    aci = b.get("aci")
    return (r["price"] or 0.0) * k, (r["avg"] or 0.0) * k, aci if aci is not None else 0.0


def bonds_report(client, rows):
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=365)).isoformat()
    bonds = [r for r in rows if r["type"] == "bond" and r["uid"] and r["qty"] > 0]
    infos = dict(zip([r["uid"] for r in bonds], pool_map(lambda r: bond_info(client, r["uid"]), bonds)))
    out, pays = [], []
    tot_bonds = sum((r["value_rub"] or 0) for r in bonds) or 0.0
    rates = fx_now(client, {(infos.get(r["uid"]) or {}).get("cur", "rub") for r in bonds} | {r["cur"] for r in bonds})
    exacts = dict(zip([r["uid"] for r in bonds], pool_map(
        lambda r: bond_exact(client, r, infos[r["uid"]], today, rates) if infos.get(r["uid"]) else None, bonds)))
    stress_rub = defaultdict(float)
    high_yield, irr_items = [], []
    w = defaultdict(float)
    ladder, risk = defaultdict(float), defaultdict(float)
    kinds = defaultdict(int)
    for r in bonds:
        b = infos.get(r["uid"])
        v = r["value_rub"] or 0.0
        row = {k: r.get(k) for k in ("uid", "name", "ticker", "logo", "color", "qty", "value_rub", "pnl_rub", "pnl_pct", "cur")}
        row["share"] = v / tot_bonds * 100 if tot_bonds else 0
        if not b:
            out.append(row)
            continue
        nominal = b.get("nominal") or 1000.0
        price, avg, _aci = bond_price_face(r, b, rates)
        m = bond_metrics(b, price, today)
        ex = exacts.get(r["uid"])
        row.update({"buy_pct": avg / nominal * 100 if avg else None, "price_pct": price / nominal * 100 if price else None,
                    "nominal": nominal, "face_cur": b.get("cur") or "rub", "isin": (ex or {}).get("isin") or bond_isin(r),
                    "ytm": m["ytm"], "ytm_tax": None, "dur": m["dur"], "mdur": None, "convexity": None, "to": m["to"],
                    "coupon": m["coupon_rate"], "cur_yield": m["cur_yield"], "next": m["next"], "maturity": b.get("maturity"),
                    "call": b.get("call"), "risk": RISK_RU.get(b.get("risk"), ""), "floating": b.get("floating"),
                    "amort": b.get("amort"), "sector": b.get("sector"), "cf_source": "approx"})
        if ex:
            row.update({k: ex[k] for k in ("ytm", "ytm_tax", "dur", "mdur", "convexity", "to", "cf_source")})
            row["end"] = ex["end"]
            row["est_coupons"] = ex.get("est_coupons") or 0
            fc_ = (b.get("cur") or "rub").lower()
            rf_ = 1.0 if fc_ == "rub" else rates.get(fc_)
            if rf_:
                irr_items.append((ex, r["qty"], rf_))
            sp = ex["stress_pct"]
        else:
            if m["ytm"] is not None and m["dur"]:      # приближение: только дюрация
                row["mdur"] = m["dur"] / (1 + m["ytm"] / 100)
                sp = {dy: -row["mdur"] * dy for dy in STRESS_DY}
            else:
                sp = {}
        row["spread"] = _spread(row["ytm"], row["dur"])
        row["stress"] = {str(dy): {"pct": p, "rub": p / 100.0 * v} for dy, p in sp.items()}
        for dy, p in sp.items():
            stress_rub[dy] += p / 100.0 * v
        m = dict(m, ytm=row["ytm"], dur=row["dur"])
        out.append(row)
        if row["ytm"] is not None and v and row["ytm"] > YTM_HIGH:
            high_yield.append({"ticker": row["ticker"], "name": row["name"], "ytm": row["ytm"], "value": v})
        if row["ytm"] is not None and v:
            w["ytm"] += row["ytm"] * v
            w["ytm_v"] += v
            if row.get("ytm_tax") is not None:
                w["yt"] += row["ytm_tax"] * v
                w["yt_v"] += v
        if row.get("mdur") is not None and v:
            w["md"] += row["mdur"] * v
            w["md_v"] += v
        if m["dur"] is not None and v:
            w["dur"] += m["dur"] * v
            w["dur_v"] += v
        if m["cur_yield"] is not None and v:
            w["cy"] += m["cur_yield"] * v
            w["cy_v"] += v
        end = (b.get("call") if b.get("call") and b["call"] > today else b.get("maturity")) or ""
        ladder[end[:4] or "бессрочные"] += v
        risk[RISK_RU.get(b.get("risk"), "нет данных")] += v
        kinds["Флоатер" if b.get("floating") else "Фиксированный купон"] += 1
        if b.get("amort"):
            kinds["С амортизацией"] += 1
        known = [p for _, p in b.get("coupons") or [] if p]
        fc_ = (b.get("cur") or "rub").lower()
        k_ = 1.0 if fc_ == "rub" else (rates.get(fc_) or 1.0)       # выплаты считаем в рублях по текущему курсу номинала
        fest = (ex or {}).get("est_detail") or {}
        for d, p in b.get("coupons") or []:
            if today < d <= horizon:
                if not p and b.get("floating") and d in fest:
                    amt, est = fest[d]["amt"] * r["qty"] * k_, "forecast"      # прогноз ключевой ставки ЦБ + спред эмитента
                else:
                    amt, est = (p or (known[-1] if known else 0.0)) * r["qty"] * k_, not p
                if amt:
                    pays.append({"date": d, "kind": "coupon", "name": r["name"], "ticker": r["ticker"], "logo": r["logo"],
                                 "amount": amt, "est": est})
        # прогнозные купоны флоатера, которых ещё нет в графике брокера
        have = {d for d, _ in b.get("coupons") or []}
        for d, e in sorted(fest.items()):
            if d not in have and today < d <= horizon and e["amt"]:
                pays.append({"date": d, "kind": "coupon", "name": r["name"], "ticker": r["ticker"], "logo": r["logo"],
                             "amount": e["amt"] * r["qty"] * k_, "est": "forecast"})
        # амортизации (частичное погашение номинала) из графика MOEX; погашение в последний день — остаток номинала
        am_total = 0.0
        if ex and b.get("maturity"):
            for a in sorted((ex.get("bz") or {}).get("amort") or [], key=lambda x: x.get("amortdate") or ""):
                ad, av = a.get("amortdate"), a.get("value")
                if not ad or not av or ad <= today or ad >= b["maturity"]:
                    continue
                am_total += av
                if ad <= horizon:
                    pays.append({"date": ad, "kind": "amortization", "name": r["name"], "ticker": r["ticker"],
                                 "logo": r["logo"], "amount": av * r["qty"] * k_, "est": False})
        if b.get("maturity") and today < b["maturity"] <= horizon:
            pays.append({"date": b["maturity"], "kind": "redemption", "name": r["name"], "ticker": r["ticker"],
                         "logo": r["logo"], "amount": max(nominal - am_total, 0.0) * r["qty"] * k_, "est": False})
    # дивиденды по акциям (объявленные)
    shares = [r for r in rows if r["type"] in ("share",) and r["uid"] and r["qty"] > 0 and not r["uid"].startswith("imp:")]

    def divs(r):
        st = store()
        v = st.get("div:" + r["uid"], ttl=DAY)
        if v is None and client.ready:
            try:
                ds = client.dividends(r["uid"], today + "T00:00:00Z", horizon + "T00:00:00Z")
                v = [[iso_date(d.get("paymentDate")) or iso_date(d.get("recordDate")), qf(d.get("dividendNet"))] for d in ds]
                st.put("div:" + r["uid"], v)
            except ApiError:
                v = []
        return r, v or []

    for r, ds in pool_map(divs, shares):
        for d, per in ds:
            if d and today < d <= horizon and per:
                pays.append({"date": d, "kind": "dividend", "name": r["name"], "ticker": r["ticker"], "logo": r["logo"],
                             "amount": per * r["qty"], "est": False})
    pays.sort(key=lambda p: p["date"])
    irr = portfolio_irr(irr_items, today)
    metrics = {"count": len(bonds), "value": tot_bonds,
               "ytm": w["ytm"] / w["ytm_v"] if w["ytm_v"] else None,
               "ytm_tax": w["yt"] / w["yt_v"] if w["yt_v"] else None,
               "mdur": w["md"] / w["md_v"] if w["md_v"] else None,
               "ytm_value": w["ytm_v"], "high_yield": high_yield, "high_yield_value": sum(o["value"] for o in high_yield),
               "irr": irr["irr"], "irr_tax": irr["irr_tax"], "irr_value": irr["value"], "irr_count": irr["count"],
               "keyrate": keyrate_brief(),
               "approx_count": sum(1 for x in out if x.get("cf_source") == "approx"),
               "stress": {str(dy): {"rub": stress_rub[dy], "pct": stress_rub[dy] / tot_bonds * 100 if tot_bonds else None}
                          for dy in STRESS_DY},
               "dur": w["dur"] / w["dur_v"] if w["dur_v"] else None,
               "cur_yield": w["cy"] / w["cy_v"] if w["cy_v"] else None,
               "coupons_12m": sum(p["amount"] for p in pays if p["kind"] == "coupon"),
               "issuers": len({r["name"].split(" ")[0] for r in bonds})}
    out.sort(key=lambda x: -(x.get("value_rub") or 0))
    return {"rows": out, "metrics": metrics, "ladder": sorted(ladder.items()), "risk": sorted(risk.items(), key=lambda x: -x[1]),
            "kinds": sorted(kinds.items(), key=lambda x: -x[1]), "payments": pays,
            "ratings": apply_ratings(out), "ratings_info": ratings_status()}



# ═══════════════════════════════ точная математика облигаций (потоки MOEX) ═══════════════════════════════
# Потоки считаются на одну облигацию в валюте номинала: список (дата ISO, купон, погашение номинала).

BC_TTL, BC_ERR_TTL, BC_TAX = 24 * 3600, 3600, 0.13
BC_URL = "https://iss.moex.com/iss/securities/%s/bondization.json?iss.meta=off&limit=unlimited"


def _bc_table(d, name):
    t = (d or {}).get(name) or {}
    cols = t.get("columns") or []
    return [dict(zip(cols, row)) for row in t.get("data") or []]


def moex_bondization(isin):
    """Купоны, амортизации и оферты выпуска с MOEX ISS. Кэш 24 ч; ошибки/пустой ответ кэшируются на 1 ч."""
    isin = (isin or "").strip().upper()
    if not isin or not re.match(r"^[A-Z0-9]{4,14}$", isin):
        return None
    st = store()
    key = "bondiz2:" + isin
    v = st.get(key, ttl=BC_TTL)
    if v is not None:
        if v.get("ok"):
            return v
        if time.time() - v.get("ts", 0) < BC_ERR_TTL:
            return None
    try:
        d = json.loads(http_text(BC_URL % isin, 20))
        out = {"ok": True, "ts": time.time(), "coupons": _bc_table(d, "coupons"),
               "amort": _bc_table(d, "amortizations"), "offers": _bc_table(d, "offers")}
        if not out["coupons"] and not out["amort"]:
            raise ValueError("пусто")
        for k in ("coupons", "amort", "offers"):      # оставляем только нужные поля
            keep = {"coupons": ("coupondate", "value", "valueprc", "faceunit"),
                    "amort": ("amortdate", "value", "valueprc", "faceunit"),
                    "offers": ("offerdate", "offerdatestart", "offerdateend", "price", "offertype", "faceunit")}[k]
            out[k] = [{c: r.get(c) for c in keep} for r in out[k]]
    except Exception:  # noqa: BLE001
        out = {"ok": False, "ts": time.time()}
    st.put(key, out)
    return out if out.get("ok") else None


FL_SPREAD_N, FL_SPREAD_RANGE = 4, (-4.0, 25.0)


def fl_estimates(bz, today, face, path=None):
    """Оценка будущих купонов флоатера, ставка которых ещё не объявлена: {дата: {rate, base, spread, amt}}.
    Спред эмитента = ставка известного купона - ключевая ставка на начало его купонного периода (медиана по последним
    FL_SPREAD_N известным купонам). Будущая ставка = ключевая на начало купонного периода (факт из ряда ЦБ, если период
    уже начался, иначе прогноз keyrate_path()) + спред. Сумма = ставка x номинал на начало периода x дни периода / 365.
    Привязка к RUONIA отдельно не выделяется: RUONIA ~ ключевая - 0,2 п.п., и поправка сокращается:
    (K' - 0,2) + (r - (K - 0,2)) = K' + (r - K). Если базу вывести нельзя (нет ряда ставок, нет известных купонов,
    спред вне диапазона) — {}, и вызывающий код оставляет прежнее поведение (последний известный купон)."""
    cps = sorted((c["coupondate"], c.get("value"), c.get("valueprc")) for c in bz["coupons"] if c.get("coupondate"))
    unk = [i for i, (d, v, _) in enumerate(cps) if d > today and not v and i > 0]
    if not unk:
        return {}
    try:
        ser = key_rate_series()
        path = path if path is not None else keyrate_path()
    except Exception:  # noqa: BLE001
        return {}
    if not ser or not path:
        return {}
    am_all = sorted((a["amortdate"], a.get("value")) for a in bz["amort"] if a.get("amortdate") and a.get("value"))

    def face_at(d):
        return face + sum(v for da, v in am_all if d <= da <= today) - sum(v for da, v in am_all if today < da < d)

    def ndays(a, b):
        return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days
    samples = []
    for i, (d, v, vp) in enumerate(cps):
        if not v or i == 0:
            continue
        p0 = cps[i - 1][0]
        k, days = key_rate_on(ser, p0), ndays(p0, d)
        if k is None or days <= 0:
            continue
        samples.append((vp if vp else v / max(face_at(d), 1e-9) * 365.0 / days * 100.0) - k)
    samples = sorted(samples[-FL_SPREAD_N:])
    if not samples:
        return {}
    n = len(samples)
    spread = samples[n // 2] if n % 2 else (samples[n // 2 - 1] + samples[n // 2]) / 2.0
    if not FL_SPREAD_RANGE[0] <= spread <= FL_SPREAD_RANGE[1]:
        return {}
    out = {}
    for i in unk:
        d, p0 = cps[i][0], cps[i - 1][0]
        base = key_rate_on(ser, p0) if p0 <= today else None
        if base is None:
            base = keyrate_at(path, p0)
        rate = max(0.0, base + spread)
        out[d] = {"rate": rate, "base": base, "spread": spread, "amt": rate / 100.0 * face_at(d) * ndays(p0, d) / 365.0}
    return out


def bond_flows(bz, today, face, mode="auto", floating=False, est_out=None):
    """Будущие потоки на одну облигацию: [(дата, купон, номинал)] и признак окончания ('offer'/'maturity').
    face — текущий номинал. Неизвестные купоны флоатера (floating=True) оцениваются по прогнозу ключевой ставки
    (fl_estimates; детали складываются в словарь est_out), если оценить нельзя — равны последнему известному.
    Если есть будущая оферта (покупка по цене offer price) и mode != 'maturity', потоки обрываются на дате оферты.
    Возвращает (flows, end_kind, end_date) либо (None, None, None)."""
    cps = sorted((c["coupondate"], c.get("value")) for c in bz["coupons"] if c.get("coupondate"))
    am_all = sorted((a["amortdate"], a.get("value")) for a in bz["amort"] if a.get("amortdate") and a.get("value"))
    am = [a for a in am_all if a[0] > today]
    fut = [(d, v) for d, v in cps if d > today]
    if not fut and not am:
        return None, None, None

    def face_at(d):       # номинал в начале купонного периода, оканчивающегося в d (амортизация в дату d уже после купона)
        return face + sum(v for da, v in am_all if d <= da <= today) - sum(v for da, v in am_all if today < da < d)

    # ставка последнего известного купона = выплата / номинал, на который она начислена
    rate = None
    for d, v in cps:
        if v and (d <= today or rate is None):
            rate = v / max(face_at(d), 1e-9)
        if d > today and v:
            break
    est = fl_estimates(bz, today, face) if floating else {}
    cpn, last_rate = {}, None
    for d, v in cps:
        if v:
            last_rate = v / max(face_at(d), 1e-9)
            if d > today:
                cpn[d] = v
        elif d > today:
            if d in est:
                cpn[d] = est[d]["amt"]              # флоатер: прогноз ключевой ставки + спред эмитента
                if est_out is not None:
                    est_out[d] = est[d]
                continue
            r_ = last_rate if last_rate is not None else rate
            cpn[d] = (r_ or 0.0) * face_at(d)       # неизвестный купон: последняя ставка на текущий остаток номинала
    prin = defaultdict(float)
    for d, v in am:
        prin[d] += v
    rest = face - sum(prin.values())
    mat = max([d for d, _ in fut] + [d for d in prin] or [""])
    if rest > 0.0001 * face and mat:      # остаток номинала гасится в последний день
        prin[mat] += rest
    elif rest < -0.0001 * face:
        return None, None, None          # данные не сходятся с номиналом
    end_kind, end = "maturity", mat
    if mode != "maturity":
        offs = []
        for o in bz.get("offers") or []:
            t = (o.get("offertype") or "")
            if "оферт" in t.lower() and "состоял" not in t.lower() and (o.get("offerdate") or "") > today:
                offs.append(o)
        if offs:
            o = min(offs, key=lambda x: x["offerdate"])
            if o["offerdate"] < mat or not mat:
                end_kind, end = "offer", o["offerdate"]
                op = (o.get("price") or 100.0) / 100.0
                remain = face - sum(v for d, v in prin.items() if d < end)
                prin = {d: v for d, v in prin.items() if d < end}
                prin[end] = prin.get(end, 0.0) + remain * op
                # покупатель по оферте получает и НКД на дату оферты (линейно внутри купонного периода)
                allc = sorted(cpn)
                nx = [d for d in allc if d > end]
                pv_ = [d for d in allc if d <= end] or [d for d, _ in cps if d <= end][-1:]
                if nx and pv_:
                    d0, d1, de = (datetime.strptime(x, "%Y-%m-%d") for x in (pv_[-1], nx[0], end))
                    if (d1 - d0).days > 0 and end not in cpn:
                        cpn[end] = cpn[nx[0]] * (de - d0).days / (d1 - d0).days
    days = sorted(set(d for d in list(cpn) + list(prin) if d <= end))
    flows = [(d, cpn.get(d, 0.0), prin.get(d, 0.0)) for d in days]
    return flows, end_kind, end


def _bc_t(d, settle):
    return (datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(settle, "%Y-%m-%d")).days / 365.0


def _bc_pv(flows, settle, y, tax=False, basis=0.0):
    tl = [(_bc_t(d, settle), c, p) for d, c, p in flows]
    tot = 0.0
    for i, (t, c, p) in enumerate(tl):
        a = c + p
        if tax:
            a = c * (1 - BC_TAX) + p
            if i == len(tl) - 1:
                a -= BC_TAX * max(0.0, sum(x[2] for x in tl) - basis)
        tot += a / (1 + y) ** t
    return tot


def net_flows(flows, settle, basis=0.0):
    """Потоки после НДФЛ тем же способом, что в _bc_pv(tax=True): [(дата, сумма)]. Налог на разницу погашение - basis
    берётся в дату последнего потока."""
    fl = [f for f in flows if f[0] > settle]
    out = [(d, c * (1 - BC_TAX) + p) for d, c, p in fl]
    if out:
        out[-1] = (out[-1][0], out[-1][1] - BC_TAX * max(0.0, sum(x[2] for x in fl) - basis))
    return out


def cf_ytm(dirty, flows, settle, tax=False, basis=0.0):
    """Эффективная годовая доходность (дробью, 0.12 = 12%) по потокам; None, если корня нет.
    tax=True: после НДФЛ 13% — на купоны и на положительную разницу (погашение - basis) в дату последнего потока."""
    if not flows or not dirty or dirty <= 0:
        return None
    fl = [f for f in flows if f[0] > settle]
    if not fl:
        return None
    f = lambda y: _bc_pv(fl, settle, y, tax, basis) - dirty
    lo, hi = -0.95, 50.0
    flo, fhi = f(lo), f(hi)
    if flo != flo or fhi != fhi or flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
        if hi - lo < 1e-10:
            break
    return (lo + hi) / 2


def cf_risk(flows, settle, y):
    """(дюрация Маколея в годах, модифицированная, выпуклость) при доходности y (дробью)."""
    pvs = [(_bc_t(d, settle), (c + p) / (1 + y) ** _bc_t(d, settle)) for d, c, p in flows if d > settle]
    tot = sum(v for _, v in pvs)
    if not tot:
        return None, None, None
    mac = sum(t * v for t, v in pvs) / tot
    conv = sum(t * (t + 1) * v for t, v in pvs) / tot / (1 + y) ** 2
    return mac, mac / (1 + y), conv


def stress(price, flows, settle, face, aci=0.0, dy_list=(-3, -2, -1, 1, 2, 3), y=None):
    """Полная переоценка: {dy: новая чистая цена, % номинала} при параллельном сдвиге доходности на dy п.п.
    price — чистая цена, % номинала; aci — НКД в валюте номинала."""
    if y is None:
        y = cf_ytm(price / 100.0 * face + aci, flows, settle)
    if y is None:
        return {}
    out = {}
    for dy in dy_list:
        ny = y + dy / 100.0
        if ny <= -0.95:
            continue
        out[dy] = (_bc_pv([f for f in flows if f[0] > settle], settle, ny) - aci) / face * 100.0
    return out
# ═══════════════════ риски и сценарии: рыночная вероятность дефолта, ожидаемая доходность, сценарии ключевой ставки ═══════════════════
# Упрощённая модель, справочная информация. Все допущения перечислены в RISK_NOTES и отдаются в UI.

RISK_RECOVERY = 25.0       # допущение о доле возврата при дефолте, % (по умолчанию)
# Историческая однолетняя вероятность дефолта по рейтингу национальной шкалы, %. Опорные точки:
#  - Московская биржа, «О чём говорят кредитные рейтинги» (частоты дефолтов 2002-2022, горизонт 1 год):
#    AA 0,23; A 0,75; BBB 1,87; BB 3,88;
#  - Эксперт РА, «Матрица дефолтов» (январь 2026, 1 год): BBB 1,57; BB 4,27; B 5,5; CCC 13,64; CC 28,57; C 100.
# Значения по подкатегориям (+/-) интерполированы вручную, AAA и AA+ — экспертная оценка (дефолтов в этих классах практически не было).
RISK_PD_HIST = {"AAA": 0.05, "AA+": 0.10, "AA": 0.20, "AA-": 0.30, "A+": 0.50, "A": 0.75, "A-": 1.10, "BBB+": 1.40,
                "BBB": 1.70, "BBB-": 2.30, "BB+": 3.20, "BB": 4.00, "BB-": 4.80, "B+": 5.20, "B": 5.50, "B-": 8.00,
                "CCC": 13.6, "CC": 28.6, "C": 60.0, "D": 100.0}
RISK_PD_SRC = ("Исследования дефолтов: Московская биржа («О чём говорят кредитные рейтинги», частоты дефолтов 2002-2022) "
               "и Эксперт РА («Матрица дефолтов», 2026). Подкатегории интерполированы; значения приблизительные.")
RISK_REC_SRC = ("Доля возврата для российских корпоративных облигаций в научных оценках (напр. Е. Антонова, НИУ ВШЭ, "
               "«Корпоративные финансы» 2012, данные Cbonds) обычно лежит в диапазоне 20-40 %, зависит от обеспечения и "
               "очереди требований. 25 % — рабочее допущение; меняется параметром.")
RISK_FIX_RATES = (10.0, 18.0)
RISK_BETA = ((1.0, 1.0), (7.0, 0.5))      # (срок, лет; бета): до 1 года 1,0, далее линейно до 0,5 на 7 годах и дальше


def _rexp(x):
    return 2.718281828459045 ** x


def risk_beta(t):
    (t0, b0), (t1, b1) = RISK_BETA
    if t is None or t <= t0:
        return b0
    if t >= t1:
        return b1
    return b0 + (b1 - b0) * (t - t0) / (t1 - t0)


def _risk_path(k0, target, today):
    """Путь ставки: линейно от k0 до target за 12 месяцев, далее ровно. [(дата, %)] помесячно на 4 года."""
    out = []
    t0 = datetime.strptime(today, "%Y-%m-%d")
    for m in range(0, 49):
        d = (t0 + timedelta(days=round(m * 30.4375))).strftime("%Y-%m-%d")
        out.append((d, k0 + (target - k0) * min(m, 12) / 12.0))
    return out


def _risk_unit(b, today, hd, scn_paths, def_path, tax):
    """Результат за 12 месяцев на 1 рубль стоимости по каждому сценарию. b: {flows, y, floating, bz, face, dirty, est, ...}.
    Возвращает {ключ сценария: (купоны, цена+прочее)} в долях от текущей полной стоимости (с НКД)."""
    out = {}
    for key, sc in scn_paths.items():
        flows = b["flows"]
        if b["floating"] and b["est"]:
            e2 = fl_estimates(b["bz"], today, b["face"], sc["path"])
            flows = [(d, e2[d]["amt"] if d in b["est"] and d in e2 else c, p) for d, c, p in flows]
        out[key] = _risk_eval(b, flows, today, hd, sc, def_path, tax)
    return out


def _risk_rem(flows, hd):
    return [f for f in flows if f[0] > hd]


def _risk_eval(b, flows, today, hd, sc, def_path, tax, dy_extra=None):
    y0 = b["y"]
    rem = _risk_rem(flows, hd)
    cash = [f for f in flows if today < f[0] <= hd]
    cpn = sum(c for _, c, _ in cash)
    prin = sum(p for _, _, p in cash)
    if dy_extra is not None:
        dy = dy_extra
    elif not rem:
        dy = 0.0
    elif b["floating"] and b["est"]:
        ds = [d for d, _, _ in rem]
        dy = sum(keyrate_at(sc["path"], d) - keyrate_at(def_path, d) for d in ds) / len(ds) / 100.0
    else:
        mac, _, _ = cf_risk(rem, hd, y0)
        dy = risk_beta(mac) * sc["delta"] / 100.0
    pv = _bc_pv(rem, hd, max(y0 + dy, -0.9)) if rem else 0.0
    price = pv + prin - b["dirty"]
    if tax:
        cpn *= (1 - BC_TAX)
        if price > 0:
            price *= (1 - BC_TAX)
    return cpn / b["dirty"], price / b["dirty"]


def _risk_breakeven(b, flows, today, hd, sc, tax):
    """Рост доходности (п.п.), при котором результат за 12 месяцев (купоны + цена) обнуляется; None, если > 30 п.п."""
    f = lambda dy: sum(_risk_eval(b, flows, today, hd, sc, None, tax, dy_extra=dy))
    if f(0.0) <= 0:
        return 0.0
    if f(0.30) > 0:
        return None
    lo, hi = 0.0, 0.30
    for _ in range(50):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2 * 100.0


def _risk_scenarios(target, today):
    info = keyrate_forecast_info()
    try:
        minfo = keyrate_forecast_info("market")
    except Exception:  # noqa: BLE001
        minfo = None
    k0 = info.get("key_rate")
    if k0 is None and info.get("path"):
        k0 = info["path"][0][1]
    if k0 is None:
        raise ApiError("Нет данных о ключевой ставке.", 502)
    hd = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")
    sc = []

    def add(key, name, path, note=""):
        sc.append({"key": key, "name": name, "path": path, "k12": keyrate_at(path, hd), "note": note})
    if info.get("path"):
        add("cbr", "Прогноз ЦБ", info["path"], info.get("source_name") or "")
    if minfo and minfo.get("path") and minfo.get("source") == "market":
        add("market", "Рынок", minfo["path"], minfo.get("source_name") or "")
    add("hold", "Ставка без изменений", _risk_path(k0, k0, today))
    for r in RISK_FIX_RATES:
        add("fix%d" % r, "Ставка %d %%" % r, _risk_path(k0, r, today))
    if target is not None:
        add("target", "Своя ставка %s %%" % (("%g" % target).replace(".", ",")), _risk_path(k0, target, today))
    for s in sc:
        s["delta"] = s["k12"] - k0
    return k0, hd, sc, (info.get("path") or _risk_path(k0, k0, today))


def _fnum(x, lo, hi, dflt):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return dflt
    return v if lo <= v <= hi else dflt


RISK_INFL_DEFAULT = 4.0       # инфляция по умолчанию, % годовых, если прогноз ЦБ недоступен
RISK_GAP_TOL = 0.5            # допуск дюрационного разрыва, лет


def _risk_infl(years):
    """Средняя годовая инфляция на срок years лет по прогнозу ЦБ (по календарным годам с учётом долей), дробью.
    Года за пределами прогноза берут значение последнего года. Возвращает (инфляция, источник 'cbr'|'estimate', дата прогноза)."""
    try:
        inf = inflation_forecast()
    except Exception:  # noqa: BLE001
        inf = {"source": "none", "yearly": []}
    ys = {x["year"]: x["mid"] for x in inf.get("yearly") or []}
    if inf.get("source") == "none" or not ys:
        return RISK_INFL_DEFAULT / 100.0, "estimate", ""
    years = max(years or 1.0, 0.25)
    t0 = datetime.strptime(date.today().isoformat(), "%Y-%m-%d")
    first, last = min(ys), max(ys)
    fac, t = 1.0, 0.0
    while t < years - 1e-9:
        d = t0 + timedelta(days=t * 365.25)
        end_of_year = datetime(d.year + 1, 1, 1)
        step = min(years - t, max((end_of_year - d).days / 365.25, 1e-3))
        r = ys.get(d.year, ys[first] if d.year < first else ys[last]) / 100.0
        fac *= (1 + r) ** step
        t += step
    return fac ** (1.0 / years) - 1, "cbr", inf.get("as_of") or ""


def _risk_gap_text(gap):
    if gap > RISK_GAP_TOL:
        return ("long", "Деньги понадобятся раньше, чем портфель «вернётся»: при росте ставок к сроку цели он может стоить меньше "
                "(ценовой риск).")
    if gap < -RISK_GAP_TOL:
        return ("short", "Бумаги гасятся раньше цели: деньги придётся вкладывать заново по неизвестной ставке (риск реинвестирования).")
    return ("match", "Сроки совпадают: изменения ставок почти не влияют на итог к сроку цели.")


def build_risk(cfg, acc, q=None):
    q = q or {}
    goal = _fnum(q.get("horizon"), 0.1, 50.0, 3.0)
    rec = _fnum(q.get("recovery"), 0.0, 90.0, RISK_RECOVERY)
    target = _fnum(q.get("target"), 0.0, 60.0, None) if q.get("target") not in (None, "") else None
    tax = q.get("tax") == "1"
    key = ("risk", token_key(cfg), acc, rec, target, tax, goal)
    hit = mem_get(key, 300)
    if hit:
        return hit
    rep = build_bonds(cfg, acc)
    today = date.today().isoformat()
    k0, hd, scs, def_path = _risk_scenarios(target, today)
    R = rec / 100.0
    rows, units = [], []
    for r in rep["rows"]:
        if r.get("ytm") is None or not r.get("value_rub"):
            continue
        v = r["value_rub"]
        isin = r.get("isin") or r.get("ticker") or ""
        end = r.get("end") or r.get("maturity") or ""
        T = max((datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days / 365.0, 0.02) if end else None
        sp = r.get("spread")
        lam = max(sp, 0.0) / 100.0 / (1 - R) if sp is not None else None
        pd1 = 1 - _rexp(-lam * min(1.0, T)) if lam is not None and T else None
        pdT = 1 - _rexp(-lam * T) if lam is not None and T else None
        rt = (r.get("rating") or {}).get("v")
        ph = RISK_PD_HIST.get(rt) / 100.0 if rt in RISK_PD_HIST else None
        ratio = pd1 / ph if pd1 is not None and ph else None
        basis_pd = ph if ph is not None else pd1            # без рейтинга — берём рыночную оценку
        el_pct = (basis_pd or 0.0) * (1 - R) * 100.0
        row = {"isin": isin, "name": r["name"], "ticker": r.get("ticker"), "uid": r.get("uid"), "value_rub": v,
               "share": r.get("share"), "rating": r.get("rating"), "ytm": r["ytm"], "spread": sp, "dur": r.get("dur"),
               "mdur": r.get("mdur"), "floating": bool(r.get("floating")), "years": T,
               "pd_mkt_1y": pd1, "pd_mkt_T": pdT, "pd_hist_1y": ph, "ratio": ratio,
               "ey_hist": r["ytm"] - el_pct, "ey_mkt": r["ytm"] - (pd1 or 0.0) * (1 - R) * 100.0,
               "hist_basis": "rating" if ph is not None else "market", "exact": r.get("cf_source") == "moex", "scn": {}}
        # потоки для переоценки
        flows, est, bz, face = None, {}, None, r.get("nominal") or 1000.0
        if row["exact"]:
            try:
                bz = moex_bondization(isin)
                flows, kind, _e = bond_flows(bz, today, face, floating=bool(r.get("floating")), est_out=est) if bz else (None, None, None)
            except Exception:  # noqa: BLE001
                flows = None
        if flows:
            y0 = r["ytm"] / 100.0
            dirty = _bc_pv([f for f in flows if f[0] > today], today, y0)
            if dirty and dirty > 0:
                b = {"flows": flows, "y": y0, "floating": bool(r.get("floating")), "bz": bz, "face": face, "dirty": dirty, "est": est}
                for k, (c, p) in _risk_unit(b, today, hd, {s["key"]: s for s in scs}, def_path, tax).items():
                    row["scn"][k] = {"coupons": c * v, "price": p * v, "total": (c + p) * v}
                hs = scs[[s["key"] for s in scs].index("hold")]
                be = _risk_breakeven(b, flows, today, hd, hs, tax)
                row["breakeven"] = be
                row["be_gt"] = be is None
        if not row["scn"]:
            # приближение: купоны ~ доходность, цена ~ -mdur x бета x сдвиг
            md = r.get("mdur") or 0.0
            for s in scs:
                dy = 0.0 if r.get("floating") else risk_beta(r.get("dur")) * s["delta"]
                c = v * r["ytm"] / 100.0 * ((1 - BC_TAX) if tax else 1)
                p = -md * dy / 100.0 * v
                row["scn"][s["key"]] = {"coupons": c, "price": p, "total": c + p}
            row["breakeven"] = r["ytm"] / md if md else None
            row["be_gt"] = False
        if "breakeven" not in row or row["breakeven"] is None:
            row.setdefault("breakeven", None)
        row["be_approx"] = r["ytm"] / row["mdur"] if row.get("mdur") else None
        rows.append(row)
    tot = sum(x["value_rub"] for x in rows) or 0.0
    out = {"account": acc, "recovery": rec, "tax": tax, "count": len(rows), "value": tot, "today": today, "horizon": hd,
           "key_rate": k0, "pd_hist_table": RISK_PD_HIST, "sources": {"pd": RISK_PD_SRC, "recovery": RISK_REC_SRC},
           "beta": [list(x) for x in RISK_BETA], "rows": rows,
           "scenarios": [{k: s[k] for k in ("key", "name", "k12", "delta", "note")} for s in scs]}
    if not tot:
        out.update(portfolio=None, scn_total=[], floaters={}, casino=[], duration=None, real=None, goal_years=goal)
        return mem_put(key, out)
    wy = sum(x["ytm"] * x["value_rub"] for x in rows) / tot
    el_h = sum(x["value_rub"] * ((x["pd_hist_1y"] if x["pd_hist_1y"] is not None else (x["pd_mkt_1y"] or 0.0))) * (1 - R) for x in rows)
    el_m = sum(x["value_rub"] * (x["pd_mkt_1y"] or 0.0) * (1 - R) for x in rows)
    nd = [x for x in rows if x["ytm"] <= YTM_HIGH]
    wy_ex = sum(x["ytm"] * x["value_rub"] for x in nd) / sum(x["value_rub"] for x in nd) if nd else None
    out["portfolio"] = {"promised_ex": wy_ex, "distressed_value": tot - sum(x["value_rub"] for x in nd), "promised": wy, "expected": wy - el_h / tot * 100.0, "expected_mkt": wy - el_m / tot * 100.0,
                        "exp_loss_rub": el_h, "exp_loss_mkt_rub": el_m,
                        "unrated_value": sum(x["value_rub"] for x in rows if x["hist_basis"] != "rating"),
                        "approx_count": sum(1 for x in rows if not x["exact"])}
    # итоги по сценариям и группам
    def agg(sel):
        res = {}
        val = sum(x["value_rub"] for x in sel)
        for s in scs:
            c = sum(x["scn"][s["key"]]["coupons"] for x in sel)
            p = sum(x["scn"][s["key"]]["price"] for x in sel)
            res[s["key"]] = {"coupons": c, "price": p, "total": c + p, "pct": (c + p) / val * 100.0 if val else None}
        return res, val
    out["scn_total"], _ = agg(rows)
    fl, fx = [x for x in rows if x["floating"]], [x for x in rows if not x["floating"]]
    fa, fv = agg(fl)
    xa, xv = agg(fx)
    out["floaters"] = {"floating": {"value": fv, "count": len(fl), "scn": fa}, "fixed": {"value": xv, "count": len(fx), "scn": xa}}
    # «казино»: дефолт k самых рискованных эмитентов (по рыночной вероятности дефолта за год)
    base = out["scn_total"]["hold"]["total"]
    groups = {}
    for x in rows:
        g = groups.setdefault(x["name"].split(" ")[0].lower(), {"name": x["name"], "pd": 0.0, "value": 0.0, "ret": 0.0, "n": 0})
        g["pd"] = max(g["pd"], x["pd_mkt_1y"] or 0.0)
        g["value"] += x["value_rub"]
        g["ret"] += x["scn"]["hold"]["total"]
        g["n"] += 1
    ranked = sorted(groups.values(), key=lambda g: (-g["pd"], -g["value"]))
    casino = []
    for k in (1, 2, 3):
        pick = ranked[:k]
        if len(pick) < k:
            break
        res = base - sum(g["ret"] for g in pick) - sum(g["value"] * (1 - R) for g in pick)
        casino.append({"k": k, "issuers": [{"name": g["name"], "value": g["value"], "pd": g["pd"]} for g in pick],
                       "result_rub": res, "result_pct": res / tot * 100.0, "lost_rub": sum(g["value"] * (1 - R) for g in pick)})
    out["casino"] = casino
    out["base_rub"] = base
    out["goal_years"] = goal
    # дюрационный разрыв: дюрация портфеля облигаций (взвешена по стоимости) против горизонта цели
    dv = [(x["dur"], x["value_rub"]) for x in rows if x.get("dur") is not None]
    mv = [(x["mdur"], x["value_rub"]) for x in rows if x.get("mdur") is not None]
    out["duration"] = None
    if dv:
        w = sum(v for _, v in dv)
        mac = sum(d * v for d, v in dv) / w
        mw = sum(v for _, v in mv)
        mod = sum(d * v for d, v in mv) / mw if mw else None
        gap = mac - goal
        kind, text = _risk_gap_text(gap)
        out["duration"] = {"mac": mac, "mod": mod, "goal": goal, "gap": gap, "kind": kind, "text": text, "value": w,
                           "share": w / tot * 100.0}
    # реальная доходность по формуле Фишера: (1 + номинальная) / (1 + инфляция) - 1, инфляция усреднена на срок дюрации
    m = rep.get("metrics") or {}
    out["real"] = None
    if m.get("irr") is not None:
        yrs = (out["duration"] or {}).get("mac") or 1.0
        infl, src, asof = _risk_infl(yrs)
        fish = lambda n: ((1 + n / 100.0) / (1 + infl) - 1) * 100.0      # noqa: E731
        out["real"] = {"irr": m["irr"], "irr_tax": m.get("irr_tax"), "inflation": infl * 100.0, "years": yrs, "source": src,
                       "estimate": src != "cbr", "as_of": asof, "real": fish(m["irr"]),
                       "real_tax": fish(m["irr_tax"]) if m.get("irr_tax") is not None else None,
                       "irr_count": m.get("irr_count"), "irr_value": m.get("irr_value")}
    return mem_put(key, out)
# ═══════════════════════════════ история стоимости и доходность ═══════════════════════════════

def build_history(client, ops, names, actual_total):
    ops = sorted([o for o in ops if o.get("date")], key=lambda o: o["date"])
    if not ops:
        return None
    start = ops[0]["date"][:10]
    today = date.today().isoformat()
    by_day = defaultdict(list)
    held, qty = {}, defaultdict(int)
    for o in ops:
        d = o["date"][:10]
        by_day[d].append(o)
        k = classify(o.get("type"))
        uid = o.get("instrumentUid") or o.get("figi")
        if not uid:
            continue
        q = op_qty(o)
        if k in ("buy", "sec_in"):
            qty[uid] += q
        elif k in ("sell", "sec_out"):
            qty[uid] -= q
        elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL":
            qty[uid] = 0
        else:
            continue
        rng = held.setdefault(uid, [d, d])
        rng[1] = today if qty[uid] else d
    for uid in held:
        if qty[uid]:
            held[uid][1] = today

    def itype(uid):
        info = names.get(uid) or {}
        if info.get("type"):
            return info["type"]
        for o in ops:
            if (o.get("instrumentUid") or o.get("figi")) == uid and o.get("instrumentKind"):
                return TYPE_FROM_KIND.get(o["instrumentKind"], "")
        return ""

    types = {u: itype(u) for u in held}
    real = [u for u in held if not u.startswith("imp:") and types[u] not in ("futures", "option")]
    bonds = dict(zip([u for u in real if types[u] == "bond"],
                     pool_map(lambda u: bond_info(client, u), [u for u in real if types[u] == "bond"])))
    inst_cur = {u: (names.get(u) or {}).get("cur") or "rub" for u in held}
    for u in held:
        if types[u] == "currency":
            inst_cur[u] = "rub"
    curs = {c for c in inst_cur.values()} | {cur_of(o.get("payment")) for o in ops}
    fxu = {c: fx_uid(client, c) for c in curs if c != "rub"}
    for u in held:  # валютные инструменты в портфеле — тоже источник курса
        if types[u] == "currency":
            iso = ((names.get(u) or {}).get("ticker") or "")[:3].lower()
            if iso and iso != "rub" and not fxu.get(iso):
                fxu[iso] = u
    jobs = [(u, held[u][0], held[u][1]) for u in real] + [(u, start, today) for u in fxu.values() if u and u not in held]
    bench = {}
    for t in ("LQDT", "TMOS"):
        u = benchmark_uid(client, t) if client.ready else None
        if u:
            bench[t] = u
            if u not in held:
                jobs.append((u, start, today))
    series = dict(zip([j[0] for j in jobs], pool_map(lambda j: candle_series(client, *j), jobs)))
    closes = {u: dict(rows) for u, rows in series.items()}

    last_close, fallback, cash = {}, {}, defaultdict(float)
    qty = defaultdict(int)
    out_days, vals, inv, rets = [], [], [], []
    bench_vals = {t: [] for t in bench}
    v_prev, invested, glitches = 0.0, 0.0, 0
    d = datetime.strptime(start, "%Y-%m-%d").date()
    end = date.today()

    def fx(c):
        if c == "rub":
            return 1.0
        u = fxu.get(c)
        return last_close.get(u) if u else None

    def unit(u, day):
        c = last_close.get(u)
        t = types.get(u)
        if c is None:
            return fallback.get(u, 0.0)
        if t == "bond":
            b = bonds.get(u)
            if not b:
                return fallback.get(u, c * 10.0)
            return c / 100.0 * (b.get("nominal") or 1000.0) + nkd_at(b, day)
        r = fx(inst_cur.get(u, "rub"))
        return c * (r if r is not None else 1.0)

    while d <= end:
        ds = d.isoformat()
        for u, cl in closes.items():
            if ds in cl:
                last_close[u] = cl[ds]
        flow = 0.0
        for o in by_day.get(ds, ()):
            pay, c = qf(o.get("payment")), cur_of(o.get("payment"))
            cash[c] += pay
            k = classify(o.get("type"))
            uid = o.get("instrumentUid") or o.get("figi")
            q = op_qty(o)
            if uid and q and k in ("buy", "sell") and pay:
                r = fx(c) or 1.0
                fallback[uid] = abs(pay) / q * r
            if k in ("buy", "sec_in") and uid:
                qty[uid] += q
            elif k in ("sell", "sec_out") and uid:
                qty[uid] -= q
            elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL" and uid:
                qty[uid] = 0
            if k in ("deposits", "withdrawals"):
                flow += pay * (fx(c) or 0.0)
            elif k in ("sec_in", "sec_out") and uid and q:
                flow += (q if k == "sec_in" else -q) * unit(uid, ds)
        v = sum(a * (fx(c) or 0.0) for c, a in cash.items())
        for u, q in qty.items():
            if q and types.get(u) not in ("futures", "option"):
                v += q * unit(u, ds)
        invested += flow
        base = v_prev + max(flow, 0.0)
        r = (v - flow - v_prev) / base if base > 100 else 0.0
        if abs(r) > 0.3:
            glitches += 1
            r = 0.0
        out_days.append(ds)
        vals.append(round(v, 2))
        inv.append(round(invested, 2))
        rets.append(r)
        for t, u in bench.items():
            bench_vals[t].append(last_close.get(u))
        v_prev = v
        d += timedelta(days=1)

    monthly = defaultdict(lambda: 1.0)
    for ds, r in zip(out_days, rets):
        monthly[ds[:7]] *= 1 + r
    twr, acc = [], 1.0
    for r in rets:
        acc *= 1 + r
        twr.append(round(acc, 6))
    return {"days": out_days, "value": vals, "invested": inv, "twr": twr,
            "bench": {t: v for t, v in bench_vals.items() if any(x is not None for x in v)},
            "monthly": {m: round(x - 1, 6) for m, x in monthly.items()},
            "recon": {"calc": vals[-1] if vals else 0, "actual": actual_total}, "glitches": glitches}


# ═══════════════════════════════ импорт отчётов брокеров ═══════════════════════════════

ROLES = {
    "date": ["дата и время сделки", "дата заключения", "дата сделки", "дата операции", "дата исполнения", "дата и время",
             "дата/время", "дата", "date", "trade date", "time", "время", "дата расчетов", "дата расчётов"],
    "type": ["тип операции", "вид операции", "тип сделки", "вид сделки", "операция", "направление", "покупка/продажа",
             "тип", "вид", "type", "side", "operation", "action"],
    "isin": ["isin", "код isin", "isin код", "isin ценной бумаги"],
    "ticker": ["тикер", "ticker", "symbol", "код инструмента", "код финансового инструмента", "код бумаги", "код ценной бумаги",
               "код актива"],
    "name": ["наименование ценной бумаги", "наименование инструмента", "наименование", "название", "инструмент",
             "ценная бумага", "бумага", "актив", "эмитент", "name", "instrument", "security", "описание", "комментарий",
             "назначение платежа", "содержание операции"],
    "qty": ["количество", "кол-во", "кол во", "qty", "quantity", "количество, шт", "шт"],
    "price": ["цена сделки", "цена за единицу", "цена", "price", "курс"],
    "amount": ["сумма сделки", "сумма операции", "сумма зачисления/списания", "сумма", "объем сделки", "объём сделки",
               "объем", "объём", "amount", "total", "итого", "стоимость", "сумма, руб", "сумма в валюте"],
    "currency": ["валюта расчетов", "валюта расчётов", "валюта сделки", "валюта цены", "валюта платежа", "валюта", "currency"],
    "commission": ["комиссия брокера", "комиссия", "commission", "fee", "комиссия торговой системы"],
    "nkd": ["нкд", "накопленный купонный доход", "accrued interest", "accrued"],
}
ROLE_RU = {"date": "Дата", "type": "Тип операции", "isin": "ISIN", "ticker": "Тикер", "name": "Название / описание",
           "qty": "Количество", "price": "Цена", "amount": "Сумма", "currency": "Валюта", "commission": "Комиссия",
           "nkd": "НКД"}


def norm_head(s):
    s = str(s or "").lower().replace("ё", "е").replace("\n", " ").replace("\xa0", " ")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^\w/, -]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" ,")


def guess_mapping(header):
    heads = [norm_head(h) for h in header]
    cand = []
    for role, syns in ROLES.items():
        for si, syn in enumerate(syns):
            syn = norm_head(syn)
            for ci, h in enumerate(heads):
                if not h:
                    continue
                if h == syn:
                    score = 0
                elif h.startswith(syn):
                    score = 1
                elif re.search(r"\b" + re.escape(syn) + r"\b", h):
                    score = 2
                else:
                    continue
                cand.append((score, si, role, ci))
    cand.sort()
    mapping, used = {}, set()
    for score, si, role, ci in cand:
        if role in mapping or ci in used:
            continue
        mapping[role] = ci
        used.add(ci)
    return mapping


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell, self.in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.in_cell, self.cell = True, []
            span = dict(attrs).get("colspan")
            self._span = int(span) if span and str(span).isdigit() else 1
        elif tag == "br" and self.in_cell:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None and self.in_cell:
            txt = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            self.row.append(txt)
            for _ in range(getattr(self, "_span", 1) - 1):
                self.row.append("")
            self.in_cell = False
        elif tag == "tr" and self.row is not None and self.tables:
            if any(self.row):
                self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def _xlsx_tables(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("a:si", ns):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["a"])))
    tables = []
    for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
        rows = []
        for row in ET.fromstring(z.read(name)).iter("{%s}row" % ns["a"]):
            vals = {}
            for c in row.findall("a:c", ns):
                ref = c.get("r") or ""
                col = 0
                for ch in re.sub(r"\d", "", ref):
                    col = col * 26 + ord(ch.upper()) - 64
                t = c.get("t")
                v = c.find("a:v", ns)
                if t == "s" and v is not None:
                    val = shared[int(v.text)] if v.text and int(v.text) < len(shared) else ""
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["a"]))
                else:
                    val = v.text if v is not None and v.text is not None else ""
                    s_attr = c.get("s")
                    if val and s_attr is not None and re.fullmatch(r"\d{5}(\.\d+)?", val) and 30000 < float(val) < 80000:
                        val = "@xl" + val  # вероятно, дата в формате Excel — уточним при разборе
                vals[max(col, 1) - 1] = val
            if vals:
                rows.append([vals.get(i, "") for i in range(max(vals) + 1)])
        tables.append(rows)
    return tables


def read_tables(filename, raw):
    fn = (filename or "").lower()
    if fn.endswith((".xlsx", ".xlsm")) or raw[:2] == b"PK":
        return _xlsx_tables(raw)
    text = None
    for enc in ("utf-8-sig", "cp1251", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", "replace")
    if fn.endswith((".html", ".htm", ".xls")) or re.search(r"<\s*table", text[:200000], re.I):
        p = _TableParser()
        p.feed(text)
        return [t for t in p.tables if len(t) > 1]
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = max(";,\t", key=sample.count)
    return [[r for r in csv.reader(io.StringIO(text), delimiter=delim)]]


def find_header(tables):
    best = None
    for ti, t in enumerate(tables):
        for ri, row in enumerate(t[:60]):
            m = guess_mapping(row)
            score = len(m) + (3 if "date" in m else 0) + (2 if ("amount" in m or "qty" in m) else 0)
            if len(m) >= 3 and "date" in m and (best is None or score > best[0]):
                best = (score, ti, ri, m)
    return best


def parse_num(s):
    if s is None:
        return None
    s = str(s).strip().replace("\xa0", "").replace(" ", "").replace("−", "-").replace("–", "-")
    if not s or s in ("-", "—"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = re.sub(r"[^\d,.\-eE+]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(s):
    s = str(s or "").strip()
    if s.startswith("@xl"):
        try:
            return datetime(1899, 12, 30) + timedelta(days=float(s[3:]))
        except ValueError:
            return None
    fmts = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%d.%m.%y")
    for cand in (s, s[:19], s[:16], s[:10], s[:8]):
        cand = cand.strip().replace("Z", "")
        for fmt in fmts:
            try:
                return datetime.strptime(cand, fmt)
            except ValueError:
                continue
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s) or re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        a, b, c = m.groups()
        try:
            return datetime(int(c), int(b), int(a)) if len(a) == 2 else datetime(int(a), int(b), int(c))
        except ValueError:
            return None
    return None


TYPE_WORDS = [
    (("амортиз",), "BOND_REPAYMENT"), (("погашен", "redemption"), "BOND_REPAYMENT_FULL"),
    (("купон", "coupon"), "COUPON"), (("дивиденд", "dividend"), "DIVIDEND"),
    (("ндфл", "налог", "tax"), "TAX"),
    (("маржин", "перенос позиц", "плеч", "заем", "займ"), "MARGIN_FEE"),
    (("обслуж", "тариф", "депозитар"), "SERVICE_FEE"), (("комисс", "commission", "fee"), "BROKER_FEE"),
    (("покуп", "buy", "купля"), "BUY"), (("продаж", "sell"), "SELL"),
    (("пополн", "зачислен", "ввод денеж", "внесен", "deposit", "поступлен"), "INPUT"),
    (("вывод", "списан", "withdraw", "возврат денеж"), "OUTPUT"),
]
CUR_WORDS = {"rub": ("rub", "rur", "руб", "₽"), "usd": ("usd", "доллар", "$"), "eur": ("eur", "евро", "€"),
             "cny": ("cny", "юан", "¥"), "hkd": ("hkd",), "kzt": ("kzt", "тенге"), "gbp": ("gbp",), "chf": ("chf",)}
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def detect_type(text, qty, amount):
    t = (text or "").lower()
    for words, kind in TYPE_WORDS:
        if any(w in t for w in words):
            return kind
    if qty:
        return "BUY" if (amount or 0) < 0 else "SELL" if (amount or 0) > 0 else "BUY"
    if amount:
        return "INPUT" if amount > 0 else "OUTPUT"
    return None


def norm_cur(s):
    t = (s or "").lower()
    for c, words in CUR_WORDS.items():
        if any(w in t for w in words):
            return c
    return "rub"


SIGN = {"BUY": -1, "SELL": 1, "COUPON": 1, "DIVIDEND": 1, "BOND_REPAYMENT": 1, "BOND_REPAYMENT_FULL": 1, "TAX": -1,
        "BROKER_FEE": -1, "SERVICE_FEE": -1, "MARGIN_FEE": -1, "INPUT": 1, "OUTPUT": -1}


def rows_to_ops(rows, mapping, header=None):
    extra_comm = [i for i, h in enumerate(header or []) if "комисс" in norm_head(h) and i != mapping.get("commission")]
    def cell(row, role):
        i = mapping.get(role)
        return row[i] if i is not None and i < len(row) else ""

    ops, skipped = [], 0
    for row in rows:
        dt = parse_date(cell(row, "date"))
        if not dt:
            skipped += 1
            continue
        qty = parse_num(cell(row, "qty"))
        price = parse_num(cell(row, "price"))
        amount = parse_num(cell(row, "amount"))
        comm = parse_num(cell(row, "commission"))
        for ci in extra_comm:
            v = parse_num(row[ci]) if ci < len(row) else None
            if v:
                comm = (comm or 0.0) + abs(v)
        nkd = parse_num(cell(row, "nkd")) or 0.0
        isin = (cell(row, "isin") or "").strip().upper()
        ticker = (cell(row, "ticker") or "").strip().upper()
        name = (cell(row, "name") or "").strip()
        if not isin:
            for v in (ticker, name.upper()):
                if ISIN_RE.match(v):
                    isin = v
        if not isin:
            m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", (name + " " + cell(row, "type")).upper())
            if m and m.group(1)[:2] in ("RU", "US", "XS", "KZ", "DE", "GB", "IE", "LU", "NL", "CH", "CN", "HK", "JE", "CY", "KY", "VG", "BM"):
                isin = m.group(1)
        kind = detect_type(cell(row, "type") + " " + ("" if mapping.get("type") is not None else name), qty, amount)
        if not kind:
            skipped += 1
            continue
        if kind in ("BUY", "SELL") and not qty:
            skipped += 1
            continue
        if amount is None and qty and price is not None:
            amount = abs(qty) * price
        if amount is not None and nkd and kind in ("BUY", "SELL"):
            amount = abs(amount) + abs(nkd)  # в отчётах НКД обычно указан отдельно от суммы сделки
        if not amount and kind not in ("BUY", "SELL"):
            skipped += 1
            continue
        amount = abs(amount or 0.0) * SIGN.get(kind, 1)
        cur = norm_cur(cell(row, "currency"))
        ident = isin or ticker or (name if kind in ("BUY", "SELL", "COUPON", "DIVIDEND", "BOND_REPAYMENT", "BOND_REPAYMENT_FULL") else "")
        o = {"id": "imp-" + uuid.uuid4().hex[:12], "date": dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "type": "OPERATION_TYPE_" + kind,
             "payment": to_money(round(amount, 9), cur), "name": name or ticker or isin, "_ident": ident}
        if qty:
            o["quantity"] = o["quantityDone"] = str(int(abs(qty)))
        if price is not None:
            o["price"] = to_money(abs(price), cur)
        ops.append(o)
        if comm:
            ops.append({"id": "imp-" + uuid.uuid4().hex[:12], "date": o["date"], "type": "OPERATION_TYPE_BROKER_FEE",
                        "payment": to_money(-abs(comm), cur), "name": "Комиссия: " + (o["name"] or ""), "_ident": ident})
    ops.sort(key=lambda o: o["date"])
    return ops, skipped


def resolve_idents(client, idents):
    st = store()
    out = {}

    def one(ident):
        v = st.get("find:" + ident, ttl=30 * DAY)
        if v is not None:
            return ident, v
        v = {}
        if client.ready:
            try:
                found = client.find(ident)
            except ApiError:
                return ident, None
            pref = ("TQBR", "TQCB", "TQOB", "TQTF", "TQIR", "TQPI", "TQOD", "SPBXM", "SPBRU", "CETS")
            best = None
            for i in found:
                ok = (ident == (i.get("isin") or "").upper()) or (ident == (i.get("ticker") or "").upper()) or \
                     (ident.lower() == (i.get("name") or "").lower())
                if not ok:
                    continue
                rank = pref.index(i.get("classCode")) if i.get("classCode") in pref else 99
                if best is None or rank < best[0]:
                    best = (rank, i)
            if best:
                i = best[1]
                v = {"uid": i.get("uid"), "figi": i.get("figi"), "name": i.get("name"), "kind": i.get("instrumentKind") or "",
                     "type": i.get("instrumentType") or ""}
            st.put("find:" + ident, v)
        return ident, v

    for ident, v in pool_map(one, sorted(set(i for i in idents if i)), workers=4):
        out[ident] = v or {}
    return out


def finalize_import(client, ops):
    ids = resolve_idents(client, [o.get("_ident") for o in ops])
    for o in ops:
        ident = o.pop("_ident", "")
        r = ids.get(ident) or {}
        if r.get("uid"):
            o["instrumentUid"], o["figi"] = r["uid"], r.get("figi") or ""
            if r.get("kind"):
                o["instrumentKind"] = r["kind"]
            elif r.get("type"):
                o["instrumentKind"] = "INSTRUMENT_TYPE_" + r["type"].upper()
            if classify(o["type"]) in ("buy", "sell", "coupons", "dividends", "repayments") and r.get("name"):
                o["name"] = r["name"]
        elif ident and classify(o["type"]) in ("buy", "sell", "repayments", "coupons", "dividends"):
            o["instrumentUid"] = "imp:" + ident
    # если в отчёте нет пополнений — досоздаём их, чтобы деньги на счёте не уходили в минус
    if not any(classify(o["type"]) == "deposits" for o in ops):
        cash, extra = defaultdict(float), []
        for o in ops:
            c = cur_of(o["payment"])
            cash[c] += qf(o["payment"])
            if cash[c] < -0.005:
                need = -cash[c]
                extra.append({"id": "imp-" + uuid.uuid4().hex[:12], "date": o["date"], "type": "OPERATION_TYPE_INPUT",
                              "payment": to_money(round(need, 2), c), "name": "Пополнение (досчитано по сделкам)", "_synthetic": True})
                cash[c] += need
        ops = sorted(ops + extra, key=lambda o: (o["date"], 0 if o.get("_synthetic") else 1))
    fifo(ops)
    for o in ops:
        if "_yield" in o:
            o["yield"] = to_money(round(o.pop("_yield"), 9), cur_of(o["payment"]))
    return ops, ids


def import_preview(filename, raw):
    tables = read_tables(filename, raw)
    hit = find_header(tables)
    if not hit:
        raise ApiError("Не нашёл таблицу с операциями: нужна строка заголовков с датой и суммой или количеством.", 400)
    _, ti, ri, mapping = hit
    t = tables[ti]
    header = t[ri]
    body = [r for r in t[ri + 1:] if any(str(c).strip() for c in r)]
    return {"table": ti, "header_row": ri, "header": header, "mapping": mapping, "rows": len(body),
            "sample": body[:12], "tables": len(tables)}


def import_ops(filename, raw, table, header_row, mapping):
    tables = read_tables(filename, raw)
    if table >= len(tables):
        raise ApiError("Таблица не найдена.", 400)
    body = [r for r in tables[table][header_row + 1:] if any(str(c).strip() for c in r)]
    return rows_to_ops(body, {k: int(v) for k, v in mapping.items() if v is not None and str(v) != ""}, tables[table][header_row])


TEMPLATE_CSV = ("Дата;Тип операции;ISIN;Тикер;Название;Количество;Цена;Сумма;Валюта;Комиссия;НКД\n"
                "15.01.2025;Пополнение;;;;;;100000;RUB;;\n"
                "16.01.2025;Покупка;RU0009029540;SBER;Сбербанк;100;270,5;27050;RUB;8,12;\n"
                "20.02.2025;Покупка;RU000A10C6P6;;Авто Финанс Банк БО-001Р-15;10;100,2;10050;RUB;3,01;30\n"
                "15.03.2025;Купон;RU000A10C6P6;;Авто Финанс Банк БО-001Р-15;;;210,5;RUB;;\n"
                "20.07.2025;Дивиденд;RU0009029540;SBER;Сбербанк;;;3480;RUB;;\n"
                "01.08.2025;Продажа;RU0009029540;SBER;Сбербанк;50;310;15500;RUB;4,65;\n"
                "31.12.2025;НДФЛ;;;;;;520;RUB;;\n")


# ═══════════════════════════════ счета и сводка ═══════════════════════════════

_mem, _mem_lock = {}, threading.Lock()


def mem_get(key, ttl):
    with _mem_lock:
        hit = _mem.get(key)
    return hit[1] if hit and time.time() - hit[0] < ttl else None


def mem_put(key, val):
    with _mem_lock:
        _mem[key] = (time.time(), val)
    return val


def mem_clear():
    with _mem_lock:
        _mem.clear()


def imports_list():
    return store().get("imports") or []


def fetch_operations(client, cfg, acc, opened=None, full=False):
    """Инкрементальная загрузка: первый раз — вся история, дальше — только последние ~10 дней."""
    st = store()
    key = token_key(cfg) + ":" + acc
    meta = None if full else st.get("sync:" + key)
    now = datetime.now(timezone.utc)
    if full:
        st.ops_clear(key)
    if meta:
        frm = (datetime.strptime(meta[:19], "%Y-%m-%dT%H:%M:%S") - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        frm = (opened or "2006-01-01T00:00:00Z")[:19] + "Z"
    items = client.operations(acc, frm, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    st.ops_put(key, items)
    st.put("sync:" + key, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return st.ops(key)


def account_data(cfg, a, force=False):
    """(портфель как список строк позиций + итоги, операции, маржа) для одного счёта, с кэшем 90 с."""
    key = ("acc", token_key(cfg), a["id"])
    hit = None if force else mem_get(key, 90)
    if hit:
        return hit
    with key_lock(key):
        hit = None if force else mem_get(key, 90)
        return hit or _account_data(cfg, a, key)


def _account_data(cfg, a, key):
    client = TInvest(cfg)
    if a["kind"] == "import":
        ops = store().ops(a["id"])
        res = {"port": None, "ops": ops, "margin": None}
    else:
        with ThreadPoolExecutor(max_workers=3) as ex:
            fp = ex.submit(client.portfolio, a["id"])
            fo = ex.submit(fetch_operations, client, cfg, a["id"], a.get("opened"))
            fm = ex.submit(client.margin, a["id"])
            res = {"port": fp.result(), "ops": fo.result(), "margin": fm.result()}
    for o in res["ops"]:
        o["_acc"], o["_accname"] = a["id"], a["name"]
    return mem_put(key, res)


def list_accounts(cfg, force=False):
    key = ("accounts", token_key(cfg))
    hit = None if force else mem_get(key, 60)
    if hit:
        return hit
    with key_lock(key):
        hit = None if force else mem_get(key, 60)
        return hit or _list_accounts(cfg, key)


def _list_accounts(cfg, key):
    client = TInvest(cfg)
    accs = []
    if client.ready:
        for x in client.accounts():
            accs.append({"id": x["id"], "name": x.get("name") or x["id"], "kind": "tinvest",
                         "type": {"ACCOUNT_TYPE_TINKOFF_IIS": "ИИС", "ACCOUNT_TYPE_INVEST_BOX": "Копилка"}.get(x.get("type"), ""),
                         "closed": x.get("status") == "ACCOUNT_STATUS_CLOSED", "opened": x.get("openedDate")})

        def tot(a):
            try:
                p = client.portfolio(a["id"])
                return qf(p.get("totalAmountPortfolio")), len(p.get("positions") or [])
            except ApiError:
                return 0.0, 0
        for a, (t, n) in zip(accs, pool_map(tot, accs)):
            a["total"], a["empty"] = t, (t < 0.01 and n == 0)
    for imp in imports_list():
        a = {"id": imp["id"], "name": imp["name"], "kind": "import", "type": imp.get("broker") or "",
             "closed": False, "opened": None}
        try:
            rows = imported_positions(client, store().ops(imp["id"]), instruments(client, []))
            a["total"] = sum((r["value_rub"] or 0) for r in rows)
        except Exception:  # noqa: BLE001
            a["total"] = 0.0
        a["empty"] = a["total"] < 0.01
        accs.append(a)
    if not accs:
        raise ApiError("Нет счетов: добавьте API-токен в «Настройках» или импортируйте отчёт брокера.", 404)
    return mem_put(key, accs)


def selection(cfg, acc, force=False):
    accs = list_accounts(cfg, force)
    if acc == "all":
        sel = [a for a in accs if not a["empty"]] or accs
    else:
        sel = [a for a in accs if a["id"] == acc] or [accs[0]]
    data = pool_map(lambda a: account_data(cfg, a, force), sel, workers=4)
    return accs, sel, data


def build_summary(cfg, acc, period, force=False):
    client = TInvest(cfg)
    accs, sel, data = selection(cfg, acc, force)
    ops = sorted([o for d in data for o in d["ops"]], key=lambda o: o.get("date") or "")
    keys = set()
    for d in data:
        for x in (d["port"] or {}).get("positions") or []:
            keys.add((x.get("instrumentUid"), x.get("figi")))
    keys |= {(o.get("instrumentUid"), o.get("figi")) for o in ops
             if (o.get("instrumentUid") or o.get("figi")) and not str(o.get("instrumentUid") or "").startswith("imp:")}
    names = instruments(client, keys)
    lists, extra = [], {"daily": 0.0, "has_daily": False, "yield_w": 0.0}
    for a, d in zip(sel, data):
        if d["port"] is not None:
            rows = tinvest_positions(d["port"], names)
            p = d["port"]
            if p.get("dailyYield"):
                extra["daily"] += qf(p["dailyYield"])
                extra["has_daily"] = True
            store().snap(token_key(cfg) + ":" + a["id"], qf(p.get("totalAmountPortfolio")))
        else:
            rows = imported_positions(client, d["ops"], names)
        lists.append(rows)
    rows = merge_positions(lists)
    t = totals_from_rows(rows)
    total = sum(qf((d["port"] or {}).get("totalAmountPortfolio")) for d in data if d["port"] is not None) + \
        sum(sum((r["value_rub"] or 0) for r in lst) for lst, d in zip(lists, data) if d["port"] is None)
    res = analyze(ops, names, period, total)
    cost = sum(r.get("cost_rub") or 0 for r in rows if r["type"] not in ("currency", "futures"))
    upnl = sum(r.get("pnl_rub") or 0 for r in rows if r["type"] not in ("currency",))
    res["portfolio"] = {"total": total, "shares": t["shares"], "bonds": t["bonds"], "etf": t["etf"],
                        "currencies": t["currencies"], "futures": t["futures"], "options": t["options"], "sp": t["sp"],
                        "other": t["other"], "upnl": upnl, "yield_pct": upnl / cost * 100 if cost else 0.0,
                        "daily": extra["daily"] if extra["has_daily"] else None,
                        "daily_pct": extra["daily"] / (total - extra["daily"]) * 100 if extra["has_daily"] and total - extra["daily"] else None,
                        "positions": rows}
    if len(sel) == 1 and data[0]["margin"]:
        m = data[0]["margin"]
        res["margin"] = {k: qf(m.get(k)) for k in ("liquidPortfolio", "startingMargin", "minimalMargin",
                                                   "fundsSufficiencyLevel", "amountOfMissingFunds", "correctedMargin")}
    res["accounts"] = accs
    res["account"] = "all" if acc == "all" else sel[0]["id"]
    res["selected"] = [a["id"] for a in sel]
    res["sandbox"] = cfg["sandbox"]
    res["token"] = bool(cfg["token"])
    res["updated"] = datetime.now().strftime("%H:%M")
    return res


BONDS_TTL, HIST_TTL = 600, 900
_bg = set()


def cached_result(kind, cfg, acc, ttl, compute, force=False):
    """Результат тяжёлого отчёта (bonds/hist) по счёту. Свежий — из памяти; иначе последний сохранённый в базе отдаётся
    сразу с признаком stale=True, а пересчёт идёт в фоне (один на ключ). Без сохранённого — считаем и ждём.
    force=True — всегда считаем заново."""
    key = (kind, token_key(cfg), acc)
    skey = "res:%s:%s:%s" % (kind, token_key(cfg), acc)
    if not force:
        hit = mem_get(key, ttl)
        if hit:
            return hit
    st = store()

    def run():
        with key_lock(key):
            if not force:
                hit = mem_get(key, ttl)
                if hit:
                    return hit
            res = compute()
            mem_put(key, res)
            try:
                st.put(skey, {"t": time.time(), "v": res})
            except Exception:  # noqa: BLE001
                pass
            return res
    if not force:
        try:
            saved = st.get(skey)
        except Exception:  # noqa: BLE001
            saved = None
        if saved and saved.get("v") is not None and time.time() - saved.get("t", 0) < ttl:
            return mem_put(key, saved["v"])
        if saved and saved.get("v") is not None:
            if key not in _bg:
                _bg.add(key)

                def bg():
                    try:
                        run()
                    except Exception:  # noqa: BLE001
                        pass
                    finally:
                        _bg.discard(key)
                threading.Thread(target=bg, daemon=True).start()
            v = dict(saved["v"])
            v["stale"] = True
            return v
    return run()


def build_bonds(cfg, acc, force=False):
    ratings_start()          # обновит рейтинги, если данным больше 12 часов
    def compute():
        s = build_summary(cfg, acc, "all")
        rep_ = bonds_report(TInvest(cfg), s["portfolio"]["positions"])
        try:
            expert_start([r["name"] for r in rep_["rows"]])      # дозапросит рейтинги Эксперт РА по эмитентам портфеля
        except Exception:  # noqa: BLE001
            pass
        return rep_
    hit = cached_result("bonds", cfg, acc, BONDS_TTL, compute, force)
    st = ratings_status()
    if hit.get("ratings_info", {}).get("updated") != st["updated"]:
        hit["ratings"] = apply_ratings(hit["rows"])
    hit["ratings_info"] = st
    return hit


def build_history_for(cfg, acc, force=False):
    def compute():
        client = TInvest(cfg)
        accs, sel, data = selection(cfg, acc)
        ops = sorted([o for d in data for o in d["ops"]], key=lambda o: o.get("date") or "")
        keys = {(o.get("instrumentUid"), o.get("figi")) for o in ops
                if (o.get("instrumentUid") or o.get("figi")) and not str(o.get("instrumentUid") or "").startswith("imp:")}
        names = instruments(client, keys)
        total = sum(qf((d["port"] or {}).get("totalAmountPortfolio")) for d in data if d["port"] is not None)
        if any(d["port"] is None for d in data):
            total += sum(sum((r["value_rub"] or 0) for r in imported_positions(client, d["ops"], names)) for d in data if d["port"] is None)
        return build_history(client, ops, names, total) or {"days": []}
    return cached_result("hist", cfg, acc, HIST_TTL, compute, force)


def operations_csv(data):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Дата", "Тип", "Категория", "Название", "Тикер", "Кол-во", "Цена", "Сумма", "Валюта", "Комиссия", "Результат", "Счёт"])
    for r in data["ops"]:
        r = r[:11] + r[12:13]
        w.writerow([("" if not x else str(round(x, 9)).replace(".", ",")) if isinstance(x, (int, float)) else x for x in r])
    return buf.getvalue().encode("utf-8-sig")


# ═══════════════════════════════ логотипы ═══════════════════════════════

_logo_lock = threading.Lock()


def logo_bytes(name):
    base = re.sub(r"[^A-Za-z0-9_.-]", "", name or "").replace(".png", "")
    if not base:
        return None
    path = os.path.join(LOGO_DIR, base + ".png")
    miss = path + ".miss"
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    if os.path.exists(miss) and time.time() - os.path.getmtime(miss) < 3 * DAY:
        return None
    cfg = load_config()
    ctx = TInvest(cfg).ctx
    try:
        req = urllib.request.Request(LOGO_CDN + base + "x160.png", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            data = r.read()
        if not data.startswith(b"\x89PNG"):
            raise OSError("not png")
        with _logo_lock:
            os.makedirs(LOGO_DIR, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        return data
    except Exception:  # noqa: BLE001
        os.makedirs(LOGO_DIR, exist_ok=True)
        open(miss, "w").close()
        return None




def warmup_start():
    """Фоновый прогрев при запуске сервера: сводка, облигации, история (счета all) и каталог облигаций.
    Общие блокировки (key_lock) и кэши не дают дублировать работу с первыми запросами пользователя."""
    def job():
        try:
            cfg = load_config()
            if not (cfg.get("token") or "").strip() and not imports_list():
                return
            for fn in (lambda: build_summary(cfg, "all", "all"), lambda: tcat(),
                       lambda: build_bonds(cfg, "all"), lambda: build_history_for(cfg, "all")):
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=job, daemon=True, name="warmup").start()
# ═══════════════════ внешние данные: кредитные рейтинги, КБД, ключевая ставка ═══════════════════
# Наружу уходят только обезличенные GET-запросы к публичным страницам (t.me, cbr.ru, moex.com):
# ни токен, ни состав портфеля никуда не передаются.

EXT_UA = {"User-Agent": "Mozilla/5.0 (compatible; tinvest-analytics)"}
_ext_ctx = []


def http_text(url, timeout=25):
    if not _ext_ctx:
        _ext_ctx.append(make_ssl_context())
    req = urllib.request.Request(url, headers=EXT_UA)
    with urllib.request.urlopen(req, timeout=timeout, context=_ext_ctx[0]) as r:
        return r.read().decode("utf-8", "replace")


# ── кредитные рейтинги (канал @issuerRatings: АКРА, Эксперт РА, НКР, НРА) ──

RATING_CH = "https://t.me/s/issuerRatings"
RATING_SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
                "B+", "B", "B-", "CCC", "CC", "C", "D"]
RT_KEY, RT_DAYS, RT_MAX_PAGES, RT_TTL, RT_OLD = "ratings_v1", 430, 280, 12 * 3600, 600
_L = "[AАBВCС]"
_NOTLET = "(?<![A-Za-zА-Яа-яЁё])"
_RATING_PATS = [re.compile(p) for p in (
    _NOTLET + "(" + _L + "{1,3})([+\\-−–]?)\\s?(?i:\\(RU\\))",
    _NOTLET + "ru(" + _L + "{1,3})([+\\-−–]?)(?![A-Za-zА-Яа-яЁё])(?!\\.[a-z])",
    _NOTLET + "(" + _L + "{1,3})([+\\-−–]?)\\.ru",
    _NOTLET + "(" + _L + "{1,3})([+\\-−–]?)\\|ru\\|")]
_LAT = str.maketrans({"А": "A", "В": "B", "С": "C"})
_Q_STOP = ("стабильн", "позитивн", "негативн", "развива", "наблюдени", "эксперт", "акра", "нкр", "нра", "рейтинг",
           "подробнее")
_LEGAL = {"пао", "ао", "ооо", "оао", "зао", "мфк", "мкк", "пко", "нко", "гк", "группа", "компания", "холдинг",
          "корпорация", "бо", "бп", "кс", "обл", "серия", "серии", "выпуск", "сфо"}
_rt_state = {"running": False, "progress": "", "error": ""}
_rt_lock = threading.Lock()
_rt_idx = {}


def _rating_token(t):
    best = None
    for p in _RATING_PATS:
        m = p.search(t)
        if m and (best is None or m.start() < best.start()):
            best = m
    if not best:
        return None
    v = (best.group(1) + best.group(2)).translate(_LAT).upper().replace("−", "-").replace("–", "-")
    return v if v in RATING_SCALE else None


def _rating_issuer(t):
    for m in re.finditer(r"[«\"“]([^»\"”]{2,70})[»\"”]", t):
        q = m.group(1).strip()
        ql = q.lower().replace("c", "с")
        if any(w in ql for w in _Q_STOP) or "|" in q or re.fullmatch(r"[A-Za-z0-9 ]{1,3}", q):
            continue
        return q
    m = re.search(r"(?:ПАО|АО|ООО|МФК|МКК|ПКО|НКО|ОАО|ЗАО)\s+([А-ЯЁA-Z][\wЁё\-]+(?:\s+[А-ЯЁA-Z][\wЁё\-]+)?)", t)
    if not m:
        m = re.search(r"рейтинг\w*\s+(?:кредитоспособности\s+|облигаци\w+\s+|выпуск\w*\s+)*"
                      r"([А-ЯЁA-Z][^,.«»\n]{2,55}?)\s+(?:на\s+уровне|до\s+уровня)", t, re.I)
        if not m:
            return None
        c = re.split(r"\s+(?:серии|серий|классов?)\b", m.group(1), flags=re.I)[0].strip()
        return c if c and not re.search(r"\d", c) and len(c.split()) <= 6 else None
    words = []
    for w in m.group(1).split():
        if w.upper() in ("НА", "ДО", "ПО", "И", "С", "В", "ПРОГНОЗ", "СЕРИИ", "СЕРИЯ", "ВЫПУСКА", "ОБЛИГАЦИЙ", "КЛАССА"):
            break
        words.append(w)
    return " ".join(words) or None


def name_tokens(s):
    out = set()
    for i, t in enumerate(re.findall(r"[a-zа-я0-9]+", (s or "").lower().replace("ё", "е"))):
        if t in _LEGAL or (i == 0 and t == "банк") or len(t) < 2 or any(ch.isdigit() for ch in t):
            continue
        out.add(t[:5])
    return frozenset(out)


def parse_rating_post(text):
    low = text.lower()
    head = low[:80]
    agency = next((a for pat, a in ((r"\bакра\b", "АКРА"), (r"эксперт\s+ра", "Эксперт РА"), (r"\bнкр\b", "НКР"),
                                    (r"\bнра\b", "НРА")) if re.search(pat, head)), None)
    if not agency or re.search(r"ожидаем|\.sf|структурир|сфо|\bкласс|esg|\.gq|качеств|надежност|некредитн|\.am", low):
        return None
    issuer = _rating_issuer(text)
    if not issuer:
        return None
    level = "bond" if re.search(r"облигаци|выпуск", low) else "issuer"
    if "отозва" in low:
        return {"agency": agency, "issuer": issuer, "level": level, "withdrawn": True}
    v = _rating_token(re.split(r"(?i)\bранее\b", text)[0])
    if not v:
        return None
    om = re.search(r"прогноз.{0,40}?(стабильн|позитивн|негативн|развивающ)", low)
    return {"agency": agency, "issuer": issuer, "level": level, "rating": v,
            "outlook": {"стабильн": "стабильный", "позитивн": "позитивный", "негативн": "негативный",
                        "развивающ": "развивающийся"}.get(om.group(1), "") if om else ""}


RT_LOG_KEY, RT_LOG_DAYS = "ratings_log_v1", 730        # журнал рейтинговых действий: отдельно от ratings_v1
_RT_D = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:ru\s?D(?![A-Za-zА-Яа-я])|D\s?\(RU\)|D\.ru|RD(?![A-Za-z]))")
_RT_ACTIONS = {"присвоен", "подтверждён", "повышен", "понижен", "отозван", "под наблюдением", "прогноз изменён"}


def _rt_tok_d(t):
    return "D" if _RT_D.search(t or "") else _rating_token(t or "")


def parse_rating_action(text):
    """Рейтинговое действие из поста: {agency, issuer, level, action, rating, prev, outlook, watch, url} или None.
    Шире parse_rating_post: понимает дефолтные уровни (D/RD), «ранее ...», «с X до Y», статус «под наблюдением»."""
    r = parse_rating_post(text)
    low = text.lower()
    head = low[:80]
    if not r:
        agency = next((a for pat, a in ((r"\bакра\b", "АКРА"), (r"эксперт\s+ра", "Эксперт РА"), (r"\bнкр\b", "НКР"),
                                        (r"\bнра\b", "НРА")) if re.search(pat, head)), None)
        if not agency or re.search(r"ожидаем|\.sf|структурир|сфо|\bкласс|esg|\.gq|качеств|надежност|некредитн|\.am", low):
            return None
        issuer = _rating_issuer(text)
        if not issuer or not _RT_D.search(re.split(r"(?i)\bранее\b", text)[0]):
            return None
        r = {"agency": agency, "issuer": issuer, "level": "bond" if re.search(r"облигаци|выпуск", low) else "issuer",
             "rating": "D", "outlook": ""}
    first = re.split(r"\n", text.strip())[0]
    fl = first.lower()
    parts = re.split(r"(?i)\bранее\b", first, maxsplit=1)
    prev = None
    if len(parts) > 1:
        prev = _rt_tok_d(parts[1])
    else:
        m = re.search(r"(?i)\bс\s+(\S+?)\s+до\s+(\S+)", first)
        if m:
            prev = _rt_tok_d(m.group(1))
            r = dict(r, rating=_rt_tok_d(m.group(2)) or r.get("rating"))     # НКР: «с AA.ru до AA-.ru» — новый уровень второй
    watch = ""
    if re.search(r"сн[яя]л\w*\s+статус|снят\w*\s+статус", fl):
        watch = "removed"
    elif re.search(r"статус\w*\s+[«\"“]под наблюдением", fl) and re.search(r"присво|продли|установил|ввел|ввело", fl):
        watch = "set"
    elif "под наблюдением" in fl and "ранее" not in fl.split("под наблюдением")[0]:
        watch = "set"
    if "отозва" in fl:
        act = "отозван"
    elif re.search(r"повысил", fl):
        act = "повышен"
    elif re.search(r"понизил|снизил", fl):
        act = "понижен"
    elif watch == "set" and re.search(r"присво\w+\s+статус|установил\w*\s+статус", fl):
        act = "под наблюдением"
    elif re.search(r"изменил\w*\s+прогноз|изменив\s+прогноз|прогноз\w*\s+(?:по рейтингу\s+)?(?:был\s+)?изменен|пересмотрел\w*\s+прогноз", fl):
        act = "прогноз изменён"
    elif "подтверд" in fl:
        act = "подтверждён"
    elif "присво" in fl:
        act = "присвоен"
    elif watch == "set":
        act = "под наблюдением"
    else:
        return None
    um = re.search(r"https?://\S+", text[len(first):])
    om = re.search(r"прогноз.{0,60}?\bна\s+[«\"“]?(стабильн|позитивн|негативн|развивающ)", fl)
    if om:
        r = dict(r, outlook={"стабильн": "стабильный", "позитивн": "позитивный", "негативн": "негативный",
                             "развивающ": "развивающийся"}[om.group(1)])
    out = {"agency": r["agency"], "issuer": r["issuer"], "level": r["level"], "action": act,
           "rating": r.get("rating"), "prev": prev, "outlook": r.get("outlook") or "", "watch": watch,
           "url": um.group(0).rstrip(".,)") if um else ""}
    if act == "понижен" and out["rating"] and prev and out["rating"] == prev:
        out["action"] = "прогноз изменён"
    return out


def rating_log_add(log, pid, iso, text):
    a = parse_rating_action(text)
    if not a:
        return
    toks = sorted(name_tokens(a["issuer"]))
    if not toks:
        return
    a.update(post=pid, date=iso[:10], tokens=toks)
    log["events"].append(a)


def rating_log_trim(log):
    old = (date.today() - timedelta(days=RT_LOG_DAYS)).isoformat()
    log["events"] = sorted((e for e in log["events"] if e["date"] >= old), key=lambda e: (e["date"], e["post"]))


def tg_page(before=None):
    s = http_text(RATING_CH + ("?before=%d" % before if before else ""))
    ids, posts = [], []
    for blk in s.split("tgme_widget_message_wrap")[1:]:
        m = re.search(r'data-post="issuerRatings/(\d+)"', blk)
        if not m:
            continue
        ids.append(int(m.group(1)))
        t = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', blk, re.S)
        d = re.search(r'<time datetime="([^"]+)"', blk)
        if t and d:
            import html as _html
            txt = _html.unescape(re.sub(r"<br/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", t.group(1))))
            posts.append((int(m.group(1)), d.group(1), txt))
    return ids, posts


def _ratings_run():
    st = store()
    try:
        try:
            sites_refresh(force=True)         # НКР: полный список эмитентов с сайта
        except Exception:  # noqa: BLE001
            pass
        data = st.get(RT_KEY) or {"items": {}, "max_id": 0, "updated": 0}
        rlog = st.get(RT_LOG_KEY) or {"events": [], "max_id": 0}
        base_id = min(data["max_id"], rlog["max_id"])      # пока журнал пуст — догружаем канал до границы RT_DAYS
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RT_DAYS)).isoformat()
        got, before, pages = {}, None, 0
        while pages < RT_MAX_PAGES:
            ids, posts = None, None
            for _ in range(3):
                try:
                    ids, posts = tg_page(before)
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(1.5)
            if ids is None:
                raise OSError("не удалось загрузить канал рейтингов (нет доступа к t.me)")
            if not ids:
                break
            pages += 1
            for p in posts:
                got[p[0]] = p
            _rt_state["progress"] = "загружено страниц: %d" % pages
            mn = min(ids)
            oldest = min((p[1] for p in posts), default="9")
            if base_id and mn <= base_id:
                break
            if not base_id and oldest < cutoff:
                break
            if before is not None and mn >= before:
                break
            before = mn
            time.sleep(0.25)
        items = data["items"]
        for pid in sorted(got):
            if pid > rlog["max_id"]:
                try:
                    rating_log_add(rlog, pid, got[pid][1], got[pid][2])
                except Exception:  # noqa: BLE001
                    pass
            if pid <= data["max_id"]:
                continue
            _, iso, text = got[pid]
            r = parse_rating_post(text)
            if not r:
                continue
            toks = "".join(sorted(name_tokens(r["issuer"])))
            if not toks:
                continue
            key = "%s|%s|%s" % (toks, r["agency"], r["level"])
            if r.get("withdrawn"):
                if r["level"] == "issuer":
                    items.pop(key, None)
                continue
            items[key] = {"issuer": r["issuer"], "agency": r["agency"], "level": r["level"], "rating": r["rating"],
                          "outlook": r["outlook"], "date": iso[:10], "post": pid}
        data["max_id"] = max([data["max_id"]] + list(got))
        data["updated"] = time.time()
        st.put(RT_KEY, data)
        rlog["max_id"] = max([rlog["max_id"]] + list(got))
        rating_log_trim(rlog)
        st.put(RT_LOG_KEY, rlog)
        _rt_state["error"] = ""
        _rt_idx.clear()
    except Exception as e:  # noqa: BLE001
        _rt_state["error"] = str(e)[:200]
    finally:
        _rt_state["running"] = False
        _rt_state["progress"] = ""


def ratings_start(force=False):
    with _rt_lock:
        if _rt_state["running"]:
            return False
        if not force:
            d = store().get(RT_KEY)
            if d and time.time() - d.get("updated", 0) < RT_TTL:
                return False
        _rt_state["running"] = True
    threading.Thread(target=_ratings_run, daemon=True).start()
    return True


def ratings_status():
    d = store().get(RT_KEY) or {}
    return {"updated": d.get("updated"), "count": len(d.get("items") or {}), "running": _rt_state["running"],
            "progress": _rt_state["progress"], "error": _rt_state["error"]}


def _rating_index():
    d = store().get(RT_KEY) or {}
    sd = store().get(SITE_KEY) or {}
    ed = store().get(EXP_KEY) or {}
    stamp = (d.get("updated"), sd.get("updated"), len(ed.get("items") or {}))
    if _rt_idx.get("u") != stamp:
        old = (date.today() - timedelta(days=RT_OLD)).isoformat()
        merged = {}
        for src in (d.get("items") or {}, sd.get("items") or {}, ed.get("items") or {}):
            for k, it in src.items():
                if it["date"] >= old and (k not in merged or it["date"] >= merged[k]["date"]):
                    merged[k] = it
        items = [(it, name_tokens(it["issuer"])) for it in merged.values()]
        exact, inv = {}, {}
        for it, toks in items:
            if not toks:
                continue
            exact.setdefault(toks, []).append(it)
            for t in toks:
                inv.setdefault(t, []).append((it, toks))
        _rt_idx.clear()
        _rt_idx.update(u=stamp, items=items, exact=exact, inv=inv)
    return _rt_idx


def rating_for(name):
    """Рейтинг эмитента по названию облигации. Точное совпадение названий — надёжно, частичное — approx."""
    bt = name_tokens(name)
    if not bt:
        return None
    ix = _rating_index()
    best = {}

    def put(it, sc):
        sc += 0.5 if it["level"] == "issuer" else 0
        cur = best.get(it["agency"])
        if cur is None or sc > cur[0] or (sc == cur[0] and it["date"] > cur[1]["date"]):
            best[it["agency"]] = (sc, it)
    for it in ix.get("exact", {}).get(bt, []):
        put(it, 100.0)
    seen = set()
    for t in bt:
        for it, toks in ix.get("inv", {}).get(t, []):
            if id(it) in seen or toks == bt:
                continue
            seen.add(id(it))
            if not (toks <= bt or bt <= toks):
                continue
            sc = float(sum(len(x) for x in toks & bt))
            if sc < 6 and any(len(x) > 2 for x in (toks | bt) - (toks & bt)):
                continue
            if sc < 5:
                continue
            put(it, sc)
    if not best:
        return None
    allr = [{"agency": a, "rating": it["rating"], "issuer": it["issuer"], "date": it["date"], "outlook": it["outlook"],
             "approx": sc < 100} for a, (sc, it) in best.items()]
    low = max(allr, key=lambda x: RATING_SCALE.index(x["rating"]))     # консервативно: худшая из оценок
    return {"v": low["rating"], "agency": low["agency"], "issuer": low["issuer"], "date": low["date"],
            "approx": low["approx"], "all": allr}


def apply_ratings(rows):
    dist = defaultdict(float)
    for r in rows:
        r["rating"] = best_rating(r.get("isin") or r.get("ticker"), r.get("name") or "")
        dist[rating_bucket(r["rating"]["v"] if r["rating"] else None)] += r.get("value_rub") or 0
    return sorted(dist.items(), key=lambda x: -x[1])


def rating_bucket(v):
    if not v:
        return "нет рейтинга"
    i = RATING_SCALE.index(v)
    return "AAA" if i == 0 else "AA" if i <= 3 else "A" if i <= 6 else "BBB" if i <= 9 else "BB и ниже"


# ── рейтинги напрямую с сайтов агентств (НКР — список эмитентов, Эксперт РА — поиск по эмитенту) ──
# АКРА и НРА с сайтов недоступны программам (у АКРА сервер отдаёт неполную цепочку сертификатов,
# у НРА — таймауты), поэтому их рейтинги идут только из канала @issuerRatings.

SITE_KEY, EXP_KEY = "ratings_site_v1", "ratings_expert_v1"
_exp_state = {"running": False}
_SERIES_WORDS = {"бо", "бп", "кс", "обл", "серия", "серии", "выпуск"}


def _strip(t):
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def nkr_fetch():
    s = http_text("https://ratings.ru/ratings/issuers/", timeout=45)
    items = {}
    for row in re.findall(r'<tr id="bx_[^"]+".*?</tr>', s, re.S):
        td = [_strip(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(td) < 6:
            continue
        v = _rating_token(td[1])
        dm = re.search(r"(\d\d)\.(\d\d)\.(\d{4})", td[5])
        toks = "".join(sorted(name_tokens(td[0])))
        if not v or not dm or not toks:
            continue
        items["%s|НКР|issuer" % toks] = {"issuer": td[0], "agency": "НКР", "level": "issuer", "rating": v,
                                         "outlook": td[2], "date": "%s-%s-%s" % (dm.group(3), dm.group(2), dm.group(1))}
    return items


def sites_refresh(force=False):
    st = store()
    d = st.get(SITE_KEY)
    if d and not force and time.time() - d.get("updated", 0) < RT_TTL:
        return
    items = nkr_fetch()
    if items:
        st.put(SITE_KEY, {"items": items, "updated": time.time()})
        _rt_idx.clear()


def _bond_query(name):
    words = [w for w in re.split(r"\s+", (name or "").strip())
             if w and not any(ch.isdigit() for ch in w) and w.lower().replace("ё", "е") not in _SERIES_WORDS]
    return " ".join(words[:3])


def _expert_session():
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    if not _ext_ctx:
        _ext_ctx.append(make_ssl_context())
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=_ext_ctx[0]))
    op.addheaders = list(EXT_UA.items())
    return op


def expert_lookup(op, query, tokens):
    """Поиск эмитента на raexpert.ru, затем чтение страницы компании. Возвращает dict или None."""
    s = op.open("https://raexpert.ru/", timeout=25).read().decode("utf-8", "replace")
    tok = re.search(r'name="CSRFToken" value="([^"]+)"', s)
    if not tok:
        return None
    req = urllib.request.Request("https://raexpert.ru/search/", urllib.parse.urlencode(
        {"CSRFToken": tok.group(1), "search": query}).encode(), {"Referer": "https://raexpert.ru/"})
    res = op.open(req, timeout=30).read().decode("utf-8", "replace")
    seen, link = set(), None
    for href, name in re.findall(r'href="(/database/companies/[^"?]+?)/?"[^>]*>([^<]+)<', res):
        name = _strip(name)
        if href in seen or not name:
            continue
        seen.add(href)
        if name_tokens(name) == tokens:
            link = (href, name)
            break
    if not link:
        return None
    c = op.open("https://raexpert.ru" + link[0], timeout=30).read().decode("utf-8", "replace")
    m = re.search(r"(ru[^\s,<]+),\s*([А-Яа-я ]+?),\s*<a href=\"/releases/[^\"]+\">(\d\d)\.(\d\d)\.(\d{4})", c)
    if not m:
        return None
    v = _rating_token(m.group(1))
    if not v:
        return None
    return {"issuer": link[1], "agency": "Эксперт РА", "level": "issuer", "rating": v, "outlook": m.group(2).strip().lower(),
            "date": "%s-%s-%s" % (m.group(5), m.group(4), m.group(3))}


def _expert_run(names):
    try:
        st = store()
        d = st.get(EXP_KEY) or {"items": {}, "queried": {}}
        op = None
        now = time.time()
        for name in names:
            q = _bond_query(name)
            tokens = name_tokens(q)
            if not q or not tokens:
                continue
            qk = "".join(sorted(tokens))
            ts = d["queried"].get(qk)
            if ts and now - ts < 3 * 86400:
                continue
            try:
                op = op or _expert_session()
                it = expert_lookup(op, q, tokens)
            except Exception:  # noqa: BLE001
                continue
            d["queried"][qk] = time.time()
            if it:
                d["items"]["%s|Эксперт РА|issuer" % qk] = it
            st.put(EXP_KEY, d)
            _rt_idx.clear()
            time.sleep(0.6)
    finally:
        _exp_state["running"] = False


def expert_start(names):
    with _rt_lock:
        if _exp_state["running"]:
            return
        d = store().get(EXP_KEY) or {"queried": {}}
        now = time.time()
        todo = []
        for n in names:
            qk = "".join(sorted(name_tokens(_bond_query(n))))
            if qk and now - d["queried"].get(qk, 0) > 3 * 86400 and n not in todo:
                todo.append(n)
        if not todo:
            return
        _exp_state["running"] = True
    threading.Thread(target=_expert_run, args=(todo[:80],), daemon=True).start()


# ═══════════════════ каталог облигаций T-Invest (сектор, признаки, рейтинги по ISIN) ═══════════════════
# Только чтение справочника InstrumentsService/Bonds; без токена каталог пуст, а рейтинги берутся по названию.

TCAT_KEY, TCAT_TTL = "tcat_v2", 24 * 3600
_tcat = {"t": 0, "d": {}, "fail": 0, "tk": {}}
_tcat_lock = threading.Lock()


def _tcat_compact(b):
    rts = []
    for r in b.get("ratings") or []:
        rts.append([r.get("agencyName") or "", r.get("ratingLevel") or "", (r.get("ratingDate") or "")[:10],
                    r.get("forecast") or "", bool(r.get("isUnderWatch"))])
    return {"n": b.get("name") or "", "s": b.get("sector") or "", "fl": bool(b.get("floatingCouponFlag")),
            "am": bool(b.get("amortizationFlag")), "sub": bool(b.get("subordinatedFlag")),
            "pp": bool(b.get("perpetualFlag")), "rk": b.get("riskLevel") or "",
            "mat": (b.get("maturityDate") or "")[:10], "cur": (b.get("currency") or "").upper(),
            "tk": b.get("ticker") or "", "br": ((b.get("brand") or {}).get("name") if isinstance(b.get("brand"), dict) else None) or "", "r": rts}


def tcat():
    """dict ISIN -> компактная запись каталога; {} если токена нет или API недоступен."""
    if _tcat["d"] and time.time() - _tcat["t"] < TCAT_TTL:
        return _tcat["d"]
    with _tcat_lock:
        if _tcat["d"] and time.time() - _tcat["t"] < TCAT_TTL:
            return _tcat["d"]
        if not _tcat["d"]:
            try:
                hit = store().get(TCAT_KEY, ttl=TCAT_TTL)
            except Exception:  # noqa: BLE001
                hit = None
            if hit:
                _tcat.update(t=time.time(), d=hit)
                return hit
        if time.time() - _tcat["fail"] < 300:
            return _tcat["d"]
        try:
            cfg = load_config()
            if not (cfg.get("token") or "").strip():
                raise ApiError("нет токена", 400)
            ins = TInvest(cfg).call("InstrumentsService", "Bonds",
                                    {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}, timeout=90).get("instruments") or []
            d = {b["isin"]: _tcat_compact(b) for b in ins if b.get("isin")}
            if d:
                store().put(TCAT_KEY, d)
                _tcat.update(t=time.time(), d=d)
        except Exception:  # noqa: BLE001
            _tcat["fail"] = time.time()
        return _tcat["d"]


def _tcat_get(k):
    """Запись каталога по ISIN или (запасной вариант) по тикеру."""
    d = tcat()
    k = (k or "").strip().upper()
    b = d.get(k)
    if b is None and d:
        if len(_tcat["tk"]) < len(d) // 2:
            _tcat["tk"] = {v["tk"].upper(): v for v in d.values() if v.get("tk")}
        b = _tcat["tk"].get(k)
    return b


def tcat_info(isin):
    b = _tcat_get(isin)
    if not b:
        return None
    return {"sector": b["s"] or None, "floating": b["fl"], "amort": b["am"], "subordinated": b["sub"],
            "perpetual": b["pp"], "risk": b["rk"] or None, "name": b["n"], "maturity": b["mat"] or None,
            "currency": b["cur"] or None}


def _norm_level(s):
    s = (s or "").strip().translate(_LAT).upper().replace("−", "-").replace("–", "-")
    if s in RATING_SCALE:
        return s
    return _rating_token(s)


def best_rating(isin, name):
    """Как rating_for(name), но рейтинги из каталога по ISIN точные; недостающие агентства добавляются по названию."""
    base = rating_for(name or "")
    b = _tcat_get(isin)
    cat = {}
    if b:
        for ag, lv, dt, fc, watch in b["r"]:
            v = _norm_level(lv)
            if not v or not ag:
                continue
            cur = cat.get(ag)
            if cur is None or dt >= cur["date"]:
                cat[ag] = {"agency": ag, "rating": v, "issuer": b["br"] or b["n"], "date": dt,
                           "outlook": (fc or "") + (" · под наблюдением" if watch else ""), "approx": False}
    if not cat:
        return base
    allr = list(cat.values())
    for x in (base or {}).get("all") or []:
        if x["agency"] not in cat and not x.get("approx"):
            allr.append(x)
    low = max(allr, key=lambda x: RATING_SCALE.index(x["rating"]))
    return {"v": low["rating"], "agency": low["agency"], "issuer": low["issuer"], "date": low["date"],
            "approx": low["approx"], "all": allr}
# ── курс КБД сегодня, спред к КБД ──

_kbd_now = {"t": 0, "pts": []}


def kbd_curve():
    if time.time() - _kbd_now["t"] > 1800 or not _kbd_now["pts"]:
        try:
            j = json.loads(http_text("https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields"))
            pts = sorted((r[2], r[3]) for r in j["yearyields"]["data"])
            if pts:
                _kbd_now.update(t=time.time(), pts=pts)
        except Exception:  # noqa: BLE001
            pass
    return _kbd_now["pts"]


def kbd_at(years):
    pts = kbd_curve()
    if not pts or years is None:
        return None
    if years <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if years <= x1:
            return y0 + (y1 - y0) * (years - x0) / (x1 - x0)
    return pts[-1][1]


# ── скринер облигаций (Мосбиржа, ISS) ──

_scr = {"t": 0, "rows": []}
SCR_COLS_S = ("SECID,SHORTNAME,SECNAME,ISIN,FACEVALUE,FACEUNIT,COUPONPERCENT,NEXTCOUPON,MATDATE,OFFERDATE,"
              "LISTLEVEL,PREVLEGALCLOSEPRICE,YIELDATPREVWAPRICE,COUPONPERIOD,BONDSUBTYPE,ISSUESIZE")
SCR_COLS_M = "SECID,LAST,YIELD,WAPRICE,DURATION,VALTODAY,NUMTRADES,ZSPREAD,YIELDATWAPRICE"


def _iss_table(j, name):
    t = j[name]
    return [dict(zip(t["columns"], r)) for r in t["data"]]


def screener_rows():
    if time.time() - _scr["t"] < 600 and _scr["rows"]:
        return _scr["rows"]
    out = {}
    for board, kind in (("TQCB", "corp"), ("TQOB", "ofz")):
        j = json.loads(http_text(
            "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/%s/securities.json?iss.meta=off"
            "&iss.only=securities,marketdata&securities.columns=%s&marketdata.columns=%s" % (board, SCR_COLS_S, SCR_COLS_M),
            timeout=60))
        md = {r["SECID"]: r for r in _iss_table(j, "marketdata")}
        for s in _iss_table(j, "securities"):
            m = md.get(s["SECID"], {})
            price = m.get("WAPRICE") or m.get("LAST") or s.get("PREVLEGALCLOSEPRICE")
            yld = m.get("YIELD") or m.get("YIELDATWAPRICE") or s.get("YIELDATPREVWAPRICE")
            if not price or not yld or not s.get("MATDATE") or s["MATDATE"].startswith("0000"):
                continue
            dur = (m.get("DURATION") or 0) / 365.0 or None
            end = s["MATDATE"]
            of = s.get("OFFERDATE")
            of = of if of and not of.startswith("0000") else None
            out[s["SECID"]] = {
                "id": s["SECID"], "isin": s.get("ISIN"), "name": s.get("SHORTNAME"), "full": s.get("SECNAME"),
                "kind": kind, "cur": (s.get("FACEUNIT") or "SUR").replace("SUR", "RUB"), "nominal": s.get("FACEVALUE"),
                "price": round(price, 3), "yield": round(float(yld), 2), "dur": round(dur, 2) if dur else None,
                "coupon": s.get("COUPONPERCENT"), "next": s.get("NEXTCOUPON"), "mat": end, "offer": of,
                "level": s.get("LISTLEVEL"), "turn": round(m.get("VALTODAY") or 0), "trades": m.get("NUMTRADES") or 0,
                "zs": m.get("ZSPREAD"), "sub": s.get("BONDSUBTYPE"), "size": s.get("ISSUESIZE")}
    rows = list(out.values())
    for r in rows:
        k = kbd_at(r["dur"]) if r["dur"] else None
        r["spread"] = round(r["yield"] - k, 2) if k is not None and r["cur"] == "RUB" else None
        r["rating"] = None
    _scr.update(t=time.time(), rows=rows)
    return rows


MKT_BUCKETS = ["AAA", "AA", "A", "BBB", "BB и ниже"]
MKT_DUR = [(0, 1, "0–1"), (1, 2, "1–2"), (2, 3, "2–3"), (3, 99, "3+")]
MKT_HIST_KEY = "mkt_stats_hist_v1"


def _med(xs):
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)
    return round(xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2, 2)


def _cell(rs):
    return {"n": len(rs), "yield": _med([r["yield"] for r in rs]), "spread": _med([r["spread"] for r in rs if r.get("spread") is not None])}


def market_stats(rows):
    """Медианы доходности и спреда к КБД: рейтинг x дюрация, по секторам. Вселенная: рублёвые корпоративные с рейтингом."""
    now = time.time()
    uni = []
    for r in rows:
        if r.get("kind") != "corp" or r.get("cur") != "RUB" or not r.get("rating"):
            continue
        if not (0 < r["yield"] < 60):
            continue
        try:
            yrs = (datetime.strptime(r["mat"], "%Y-%m-%d").timestamp() - now) / 31557600.0
        except Exception:  # noqa: BLE001
            continue
        if yrs <= 0.1:
            continue
        d = r.get("dur") if r.get("dur") else yrs
        uni.append((rating_bucket(r["rating"]), d, r))
    grid = []
    for bk in MKT_BUCKETS:
        row = {"bucket": bk, "all": _cell([r for b, d, r in uni if b == bk]), "cells": []}
        for lo, hi, lab in MKT_DUR:
            row["cells"].append(dict(_cell([r for b, d, r in uni if b == bk and lo <= d < hi]), dur=lab))
        grid.append(row)
    sectors = {}
    for b, d, r in uni:
        if r.get("sector"):
            sectors.setdefault(r["sector"], []).append(r)
    sec = sorted(({"sector": k, **_cell(v)} for k, v in sectors.items()), key=lambda x: -x["n"])
    return {"grid": grid, "sectors": sec, "dur": [m[2] for m in MKT_DUR], "n": len(uni)}


def _stats_history(stats):
    st = store()
    hist = st.get(MKT_HIST_KEY) or {}
    snap = {g["bucket"]: g["all"]["spread"] for g in stats["grid"] if g["all"]["spread"] is not None and g["all"]["n"] >= 3}
    if snap:
        hist[date.today().isoformat()] = snap
        for k in sorted(hist)[:-400]:
            hist.pop(k, None)
        st.put(MKT_HIST_KEY, hist)
    return hist


def screener_payload():
    rows = screener_rows()
    br, ti = globals().get("best_rating"), globals().get("tcat_info")
    for r in rows:
        rt = None
        if br:
            try:
                ci0 = ti(r.get("isin")) if ti and r.get("isin") else None
                rt = br(r.get("isin"), (ci0 or {}).get("name") or r["name"])
            except Exception:  # noqa: BLE001
                rt = None
        if rt is None and not br:
            rt = rating_for(r["name"])
        r["rating"] = rt["v"] if rt else None
        r["rt_agency"] = rt["agency"] if rt else None
        r["rt_approx"] = bool(rt and rt["approx"])
        info = None
        if ti and r.get("isin"):
            try:
                info = ti(r["isin"])
            except Exception:  # noqa: BLE001
                info = None
        r["sector"] = info.get("sector") if info else None
        r["floating"] = info.get("floating") if info else None
        r["amort"] = info.get("amort") if info else None
    stats = market_stats(rows)
    try:
        hist = _stats_history(stats)
    except Exception:  # noqa: BLE001
        hist = {}
    try:
        lq = bench_lqdt_yield()
    except Exception:  # noqa: BLE001
        lq = None
    return {"rows": rows, "kbd": kbd_curve(), "updated": _scr["t"], "ratings": ratings_status(), "stats": stats, "stats_hist": hist,
            "floor": {"lqdt": lq}}


# ── первичные размещения (по объявлениям Мосбиржи; сводка investmint.ru) ──

_pri = {"t": 0, "rows": []}


def primary_rows():
    if time.time() - _pri["t"] < 1800 and _pri["rows"]:
        return _pri["rows"]
    s = http_text("https://investmint.ru/bond-placements/", timeout=40)
    rows, seen = [], set()
    for tr in re.findall(r"<tr>\s*<td class=\"min-w-56.*?</tr>", s, re.S):
        isin = re.search(r'font-mono text-xs">([A-Z0-9]{12})<', tr)
        issuer = re.search(r'font-medium">(.*?)</div>', tr, re.S)
        desc = re.search(r'text-muted-foreground">(.*?)</div>', tr, re.S)
        start = re.search(r'<time datetime="(\d{4}-\d\d-\d\d)"', tr)
        if not (issuer and start):
            continue
        end = re.search(r"Плановое окончание:\s*([^<]+)<", tr)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        link = re.search(r'href="(https://www\.moex\.com/[^"]+)"', tr)
        key = isin.group(1) if isin else _strip(issuer.group(1)) + start.group(1)
        if key in seen:
            continue
        seen.add(key)
        name = re.sub(r"(?i)\b(общество с ограниченной ответственностью|публичное акционерное общество|акционерное общество)\b", "",
                      _strip(issuer.group(1))).replace('"', "").strip(" ()")
        rows.append({"issuer": _strip(issuer.group(1)), "short": name, "desc": _strip(desc.group(1)) if desc else "",
                     "isin": isin.group(1) if isin else "", "start": start.group(1), "end": _strip(end.group(1)) if end else "",
                     "book": _strip(tds[2]) if len(tds) > 2 else "", "status": _strip(tds[3]) if len(tds) > 3 else "",
                     "link": link.group(1) if link else ""})
    rows.sort(key=lambda r: r["start"])
    _pri.update(t=time.time(), rows=rows)
    return rows


def primary_payload():
    rows = primary_rows()
    for r in rows:
        rt = rating_for(r["short"])
        r["rating"] = rt
    return {"rows": rows, "updated": _pri["t"]}



# ── ключевая ставка ЦБ и КБД Мосбиржи (доходность 2 года) ──

KBD_KEY, KEY_KEY = "kbd2y_v1", "keyrate_v1"
_rates_state = {"running": False}


def key_rate_series():
    st = store()
    hit = st.get(KEY_KEY, ttl=6 * 3600)
    if hit:
        return hit
    frm = (date.today() - timedelta(days=900)).strftime("%d.%m.%Y")
    to = date.today().strftime("%d.%m.%Y")
    s = http_text("https://www.cbr.ru/hd_base/KeyRate/?UniDbQuery.Posted=True&UniDbQuery.From=%s&UniDbQuery.To=%s" % (frm, to))
    rows = []
    for d, v in re.findall(r"<td>(\d\d\.\d\d\.\d{4})</td>\s*<td>([\d,]+)</td>", s):
        rows.append([datetime.strptime(d, "%d.%m.%Y").date().isoformat(), float(v.replace(",", "."))])
    rows.sort()
    if rows:
        st.put(KEY_KEY, rows)
    return rows


def _kbd_one(d):
    j = json.loads(http_text("https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields&date=" + d))
    ys = [r for r in j["yearyields"]["data"] if r[2] == 2.0]
    return d, (ys[0][3] if ys else None)


def _rates_run(days):
    try:
        st = store()
        cache = st.get(KBD_KEY) or {}
        today = date.today()
        need = []
        for i in range(days + 1):
            d = today - timedelta(days=i)
            if d.weekday() < 5 and d.isoformat() not in cache:
                need.append(d.isoformat())
        try:
            key_rate_series()
        except Exception:  # noqa: BLE001
            pass
        for k in range(0, len(need), 40):
            part = need[k:k + 40]
            for d, v in pool_map(lambda x: _safe(_kbd_one, x), part, workers=8):
                if d is None:
                    continue
                if v is not None or d < today.isoformat():
                    cache[d] = v
            st.put(KBD_KEY, cache)
    finally:
        _rates_state["running"] = False


def _safe(fn, x):
    try:
        return fn(x)
    except Exception:  # noqa: BLE001
        return None, None


def rates_start(days):
    with _rt_lock:
        if _rates_state["running"]:
            return
        _rates_state["running"] = True
    threading.Thread(target=_rates_run, args=(days,), daemon=True).start()


def rates_payload(days):
    days = max(30, min(int(days or 365), 900))
    st = store()
    cache = st.get(KBD_KEY) or {}
    today = date.today()
    first = (today - timedelta(days=days)).isoformat()
    miss = sum(1 for i in range(days + 1) if (today - timedelta(days=i)).weekday() < 5
               and (today - timedelta(days=i)).isoformat() not in cache)
    if miss > 0:
        rates_start(days)
    try:
        keys = key_rate_series()
    except Exception:  # noqa: BLE001
        keys = st.get(KEY_KEY) or []
    iso = sorted(d for d, v in cache.items() if v is not None and d >= first)
    kbd, key, ki, last = [], [], 0, None
    for d in iso:
        while ki < len(keys) and keys[ki][0] <= d:
            last = keys[ki][1]
            ki += 1
        kbd.append(round(cache[d], 2))
        key.append(last)
    return {"iso": iso, "labels": [datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y") for d in iso],
            "kbd": kbd, "key": key, "loading": _rates_state["running"] or miss > 0,
            "keys": [k for k in keys if k[0] >= first]}



# ═══════════════════ карточка облигации: описание, история, денежный поток, аналоги ═══════════════════

_bc_univ = {"t": 0, "rows": []}
_bc_lock = threading.Lock()
BC_DESC = ("ISSUENAME", "ISSUEDATE", "MATDATE", "ISSUESIZE", "FACEVALUE", "INITIALFACEVALUE", "COUPONFREQUENCY",
           "COUPONPERCENT", "COUPONVALUE", "COUPONDATE", "BOND_TYPE", "BOND_SUBTYPE", "FACEVALUE_TYPE", "LISTLEVEL",
           "ISQUALIFIEDINVESTORS", "HASDEFAULT", "HASTECHNICALDEFAULT", "REGNUMBER", "TYPENAME", "EMITTER_ID")


def _bc_json(url, timeout=25):
    return json.loads(http_text(url, timeout=timeout))


def _bc_desc(isin):
    j = _bc_json("https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description" % isin)
    d = {r[0]: r[2] for r in j["description"]["data"]}
    out = {k: d[k] for k in BC_DESC if d.get(k) not in (None, "")}
    eid = d.get("EMITTER_ID")
    if eid:
        try:
            e = _bc_json("https://iss.moex.com/iss/emitters/%s.json?iss.meta=off&iss.only=emitter" % eid, timeout=15)
            row = dict(zip(e["emitter"]["columns"], (e["emitter"]["data"] or [[]])[0]))
            out["EMITTER"] = row.get("TITLE") or row.get("title")
            out["EMITTER_INN"] = row.get("INN") or row.get("inn")
        except Exception:  # noqa: BLE001
            pass
    return out


def _bc_history(secid):
    key = "bondhist_v1_" + secid
    hit = store().get(key, ttl=6 * 3600)
    if hit:
        return hit
    frm = (date.today() - timedelta(days=370)).isoformat()
    rows, start = [], 0
    while start < 1500:
        j = _bc_json("https://iss.moex.com/iss/history/engines/stock/markets/bonds/securities/%s.json?iss.meta=off"
                     "&history.columns=BOARDID,TRADEDATE,CLOSE,LEGALCLOSEPRICE,WAPRICE,YIELDCLOSE,YIELDATWAP,VALUE"
                     "&from=%s&start=%d" % (secid, frm, start))
        part = _iss_table(j, "history")
        rows += part
        if len(part) < 100:
            break
        start += 100
    boards = defaultdict(int)
    for r in rows:
        boards[r["BOARDID"]] += 1
    main = next((b for b in ("TQCB", "TQOB") if boards.get(b)), max(boards, key=boards.get) if boards else None)
    out = {"d": [], "p": [], "y": [], "v": []}
    for r in sorted((r for r in rows if r["BOARDID"] == main), key=lambda r: r["TRADEDATE"]):
        p = r.get("LEGALCLOSEPRICE") or r.get("CLOSE") or r.get("WAPRICE")
        y = r.get("YIELDCLOSE") or r.get("YIELDATWAP")
        if p is None:
            continue
        out["d"].append(r["TRADEDATE"])
        out["p"].append(round(p, 3))
        out["y"].append(round(y, 2) if y else None)
        out["v"].append(round(r.get("VALUE") or 0))
    if out["d"]:
        store().put(key, out)
    return out


def _bc_norm_table(t):
    if isinstance(t, dict) and "columns" in t:
        return [dict(zip(t["columns"], r)) for r in t["data"]]
    return [x for x in (t or []) if isinstance(x, dict)]


def _bc_flows(isin):
    j = None
    fn = globals().get("moex_bondization")
    if callable(fn):
        try:
            j = fn(isin)
        except Exception:  # noqa: BLE001
            j = None
    if not isinstance(j, dict) or not any(k in j for k in ("coupons", "amortizations", "offers")):
        j = _bc_json("https://iss.moex.com/iss/securities/%s/bondization.json?iss.meta=off&limit=unlimited"
                     "&iss.only=coupons,amortizations,offers" % isin, timeout=30)
    today = date.today().isoformat()
    ev = []
    for c in _bc_norm_table(j.get("coupons")):
        d = c.get("coupondate")
        if d and d >= today:
            ev.append({"d": d, "t": "coupon", "amt": c.get("value_rub") if c.get("value_rub") is not None else c.get("value"),
                       "pct": c.get("valueprc")})
    for a in _bc_norm_table(j.get("amortizations")):
        d = a.get("amortdate")
        if d and d >= today:
            ev.append({"d": d, "t": "redemption" if a.get("data_source") == "maturity" else "amort",
                       "amt": a.get("value_rub") if a.get("value_rub") is not None else a.get("value"),
                       "pct": a.get("valueprc")})
    for o in _bc_norm_table(j.get("offers")):
        d = o.get("offerdate")
        if d and d >= today:
            ev.append({"d": d, "t": "offer", "amt": o.get("value"), "pct": o.get("price")})
    ev.sort(key=lambda e: e["d"])
    return ev


def _bc_mark_est(flows, isin, floating, face):
    """Купоны флоатера без объявленной ставки: подставляем прогноз (ключевая ставка + спред), помечаем est/base/spread."""
    if not floating or not face or not any(e["t"] == "coupon" and e.get("amt") is None for e in flows):
        return False
    bz = moex_bondization(isin)
    est = fl_estimates(bz, date.today().isoformat(), float(face)) if bz else {}
    done = False
    for e in flows:
        x = est.get(e["d"]) if e["t"] == "coupon" and e.get("amt") is None else None
        if x:
            e.update(amt=x["amt"], pct=x["rate"], est=True, base=round(x["base"], 2), spread=round(x["spread"], 2))
            done = True
    return done


def _bc_issuer_key(r):
    t = name_tokens(_bond_query(r.get("full") or r.get("name") or ""))
    return t


def _bc_universe():
    """screener_rows + рейтинг и данные каталога; кэш 10 минут."""
    if time.time() - _bc_univ["t"] < 600 and _bc_univ["rows"]:
        return _bc_univ["rows"]
    with _bc_lock:
        if time.time() - _bc_univ["t"] < 600 and _bc_univ["rows"]:
            return _bc_univ["rows"]
        src = screener_rows()
        out = []
        for r in src:
            e = dict(r)
            e["_isin"] = r.get("isin") or r["id"]
            e["_ci"] = tcat_info(e["_isin"])
            rt = best_rating(e["_isin"], (e["_ci"] or {}).get("name") or r.get("name") or "")
            e["_rt"] = rt
            e["_iss"] = _bc_issuer_key(r)
            out.append(e)
        _bc_univ.update(t=time.time(), rows=out)
        return out


def _bc_lite(e, base_y):
    rt, ci = e["_rt"], e["_ci"] or {}
    return {"isin": e["_isin"], "id": e["id"], "name": e["name"], "yield": e["yield"], "spread": e.get("spread"),
            "dur": e.get("dur"), "rating": rt["v"] if rt else None, "rating_approx": bool(rt and rt["approx"]),
            "sector": ci.get("sector"), "floating": bool(ci.get("floating")), "amort": bool(ci.get("amort")),
            "turn": e.get("turn"), "price": e.get("price"), "mat": e.get("mat"),
            "dy": round(e["yield"] - base_y, 2) if base_y is not None else None}


def _bc_cost(me, e, ri):
    """Расстояние между выпусками для подбора аналогов (меньше = ближе); None, если не аналог. ri: индекс рейтинга me или None."""
    if e["cur"] != "RUB" or not (0 < e["yield"] < 60) or not e.get("dur") or e["dur"] < 0.1:
        return None
    if e["kind"] != me["kind"]:
        return None
    if me["kind"] == "corp" and me["_iss"] and e["_iss"] and (e["_iss"] == me["_iss"]):
        return None
    ert = e["_rt"]
    d = 0.0
    if ri is not None:
        if not ert:
            return None
        n = abs(RATING_SCALE.index(ert["v"]) - ri)
        if n > 2:
            return None
        d += n * 1.0
    elif ert and me["kind"] == "corp":
        d += 0.5
    ci, eci = me["_ci"] or {}, e["_ci"] or {}
    sec, dur = ci.get("sector"), me.get("dur")
    if sec and eci.get("sector") and sec != eci["sector"]:
        d += 0.7
    if dur:
        rel = abs(e["dur"] - dur) / max(dur, e["dur"], 0.5)
        if rel > 0.6:
            return None
        d += rel * 3
    if bool(eci.get("floating")) != bool(ci.get("floating")):
        d += 1.5
    if bool(eci.get("amort")) != bool(ci.get("amort")):
        d += 0.5
    d -= min(1.0, len(str(int(e.get("turn") or 0))) / 9.0) * 0.6
    return d


def _bc_analogs(me, isin):
    """me: запись из _bc_universe (или None). Возвращает (список аналогов, относительная оценка)."""
    uni = _bc_universe()
    if not me:
        return [], None
    rt = me["_rt"]
    ri = RATING_SCALE.index(rt["v"]) if rt else None
    scored = []
    for e in uni:
        if e["_isin"] == isin:
            continue
        d = _bc_cost(me, e, ri)
        if d is not None:
            scored.append((d, e))
    scored.sort(key=lambda x: x[0])
    sps = sorted(e["spread"] for _, e in scored[:30] if e.get("spread") is not None)
    if len(sps) >= 5:      # отсекаем выбросы (дефолтные выпуски, линкеры) относительно медианы ближайших кандидатов
        m0 = sps[len(sps) // 2]
        scored = [x for x in scored if x[1].get("spread") is None or abs(x[1]["spread"] - m0) <= 8]
    top = [_bc_lite(e, me["yield"]) for _, e in scored[:12]]
    rel = None
    sp = [a["spread"] for a in top if a["spread"] is not None]
    if me.get("spread") is not None and len(sp) >= 3:
        sp.sort()
        med = sp[len(sp) // 2] if len(sp) % 2 else (sp[len(sp) // 2 - 1] + sp[len(sp) // 2]) / 2
        diff = round(me["spread"] - med, 2)
        c2 = lambda x: ("%.2f" % x).replace(".", ",")      # noqa: E731
        txt = ("Доходность в пределах разброса аналогов (спред к КБД %s п.п. против медианы %s п.п.)"
               % (c2(me["spread"]), c2(med))) if abs(diff) < 0.25 else \
            ("Облигация %s аналогов: спред к КБД на %s п.п. %s медианы по %d похожим выпускам" %
             ("дешевле" if diff > 0 else "дороже", c2(abs(diff)), "выше" if diff > 0 else "ниже", len(sp)))
        rel = {"median_spread": round(med, 2), "diff": diff, "n": len(sp), "text": txt}
    return top, rel


def _bc_issuer_curve(me):
    """Все торгуемые выпуски того же эмитента (по ключу названия): дюрация -> доходность, плюс КБД для ориентира."""
    key = me.get("_iss")
    pts = []
    if key and me["kind"] == "corp":
        for e in _bc_universe():
            if e["_iss"] == key and e["cur"] == "RUB" and e.get("dur") and e["yield"] > 0:
                rt = e["_rt"]
                pts.append({"isin": e["_isin"], "name": e["name"], "dur": e["dur"], "yield": e["yield"], "spread": e.get("spread"),
                            "rating": rt["v"] if rt else None, "turn": e.get("turn"), "me": e["_isin"] == me["_isin"],
                            "floating": bool((e["_ci"] or {}).get("floating"))})
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p["dur"])
    lo, hi = max(0.0, pts[0]["dur"] - 0.3), pts[-1]["dur"] + 0.5
    kbd = []
    for i in range(13):
        x = lo + (hi - lo) * i / 12
        k = kbd_at(x)
        if k is not None:
            kbd.append([round(x, 2), round(k, 2)])
    return {"points": pts, "kbd": kbd}


def bond_card(isin):
    isin = (isin or "").strip().upper()
    errors = []
    card = {"isin": isin, "found": False, "errors": errors}
    if not re.fullmatch(r"[A-Z0-9]{6,14}", isin):
        errors.append("некорректный ISIN")
        return card
    me = None
    try:
        uni = _bc_universe()
        me = next((e for e in uni if e["_isin"] == isin or e["id"] == isin), None)
    except Exception as e:  # noqa: BLE001
        errors.append("рынок: %s" % str(e)[:120])
        uni = []
    if me:
        isin = me["_isin"]
        card["isin"] = isin
    secid = me["id"] if me else isin

    def run(fn):
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001
            return None, str(e)[:120]
    (desc, e1), (hist, e2), (flows, e3) = pool_map(
        run, [lambda: _bc_desc(isin), lambda: _bc_history(secid), lambda: _bc_flows(isin)], workers=3)
    for lab, er in (("описание", e1), ("история", e2), ("денежный поток", e3)):
        if er:
            errors.append("%s: %s" % (lab, er))
    ci = tcat_info(isin)
    card["catalog"] = ci
    card["desc"] = desc or {}
    card["history"] = hist or {"d": [], "p": [], "y": [], "v": []}
    card["flows"] = flows or []
    try:
        face = (desc or {}).get("FACEVALUE") or (me or {}).get("nominal")
        if _bc_mark_est(card["flows"], isin, bool((ci or {}).get("floating")), float(face) if face else 0.0):
            info = keyrate_forecast_info()
            card["keyrate"] = {"source": info["source"], "name": info["source_name"], "as_of": info["as_of"]}
    except Exception as e:  # noqa: BLE001
        errors.append("прогноз купонов: %s" % str(e)[:120])
    try:
        rt = (me["_rt"] if me else None) or best_rating(isin, (desc or {}).get("ISSUENAME") or (ci or {}).get("name") or "")
    except Exception as e:  # noqa: BLE001
        rt = None
        errors.append("рейтинг: %s" % str(e)[:120])
    card["rating"] = rt
    if me:
        card["found"] = True
        card["market"] = {k: me.get(k) for k in ("id", "isin", "name", "full", "kind", "cur", "nominal", "price", "yield",
                                                 "dur", "coupon", "next", "mat", "offer", "level", "turn", "trades",
                                                 "zs", "spread", "size")}
        k = kbd_at(me["dur"]) if me.get("dur") else None
        card["kbd"] = round(k, 2) if k is not None else None
        try:
            card["analogs"], card["rel"] = _bc_analogs(me, isin)
        except Exception as e:  # noqa: BLE001
            card["analogs"], card["rel"] = [], None
            errors.append("аналоги: %s" % str(e)[:120])
        try:
            card["issuer_curve"] = _bc_issuer_curve(me)
        except Exception as e:  # noqa: BLE001
            card["issuer_curve"] = None
            errors.append("кривая эмитента: %s" % str(e)[:120])
    else:
        card["market"] = None
        card["analogs"], card["rel"] = [], None
        card["issuer_curve"] = None
        if not errors:
            errors.append("нет торгов на основных режимах Мосбиржи — показаны только справочные данные")
    card["name"] = (me or {}).get("full") or (desc or {}).get("ISSUENAME") or (ci or {}).get("name") or isin
    card["short"] = (me or {}).get("name") or (ci or {}).get("name") or isin
    return card
# ═══════════════════════════════ прогноз ключевой ставки ═══════════════════════════════
# Нужен для флоатеров: будущие купоны = прогноз ключевой ставки + спред эмитента (см. bond_flows в 08a_bondcalc.py).
# Источники по убыванию приоритета (первый сработавший):
#   cbr    — «Среднесрочный прогноз Банка России» (PDF на cbr.ru, строка «Ключевая ставка, в среднем за год»; диапазон -> середина);
#   survey — макроэкономический опрос Банка России (HTML-таблица, медиана «Ключевая ставка ... в среднем за год»);
#   market — форвардные ставки КБД Мосбиржи (приближение, см. _kr_market_path);
#   flat   — текущая ключевая ставка без изменений.

KR_TTL, KR_ERR_TTL = 24 * 3600, 3600
KR_MODES = ("cbr", "survey", "market", "flat")
KR_NAMES = {"cbr": "Среднесрочный прогноз Банка России", "survey": "Макроопрос аналитиков (Банк России)",
            "market": "Рыночные ожидания (форварды КБД)", "flat": "Ключевая ставка без изменений"}
KR_HORIZON_M = 48
_kr_mem = {}
_kr_lock = threading.Lock()


def http_bytes(url, timeout=30):
    if not _ext_ctx:
        _ext_ctx.append(make_ssl_context())
    req = urllib.request.Request(url, headers=EXT_UA)
    with urllib.request.urlopen(req, timeout=timeout, context=_ext_ctx[0]) as r:
        return r.read()


# ── минимальный разбор PDF (stdlib): Flate-потоки, ToUnicode, операторы Tf/Tm/Td/TJ ──

def _pdf_inflate(body):
    head, _, rest = body.partition(b"stream")
    if not rest:
        return b""
    rest = rest[1:] if rest[:1] == b"\n" else (rest[2:] if rest[:2] == b"\r\n" else rest[1:] if rest[:1] == b"\r" else rest)
    rest = rest[:rest.rfind(b"endstream")] if b"endstream" in rest else rest
    if b"FlateDecode" in head:
        return zlib.decompressobj().decompress(rest)
    return rest


def _pdf_objects(d):
    objs = {}
    for m in re.finditer(rb"(?<![0-9])(\d+) 0 obj(.*?)endobj", d, re.S):
        objs[int(m.group(1))] = m.group(2)
    for body in list(objs.values()):
        head = body.partition(b"stream")[0]
        if b"/ObjStm" not in head:
            continue
        n = int(re.search(rb"/N\s+(\d+)", head).group(1))
        first = int(re.search(rb"/First\s+(\d+)", head).group(1))
        data = _pdf_inflate(body)
        nums = [int(x) for x in re.findall(rb"\d+", data[:first])]
        pairs = list(zip(nums[0:2 * n:2], nums[1:2 * n:2]))
        for i, (num, off) in enumerate(pairs):
            end = pairs[i + 1][1] if i + 1 < len(pairs) else len(data) - first
            objs.setdefault(num, data[first + off:first + end])
    return objs


def _pdf_cmap(data):
    s = data.decode("latin-1")
    m = re.search(r"begincodespacerange\s*<([0-9A-Fa-f]+)>", s)
    width = len(m.group(1)) // 2 if m else 1
    mp = {}

    def u(h):
        return bytes.fromhex(h).decode("utf-16-be", "replace")
    for blk in re.findall(r"beginbfchar(.*?)endbfchar", s, re.S):
        for a, b in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            mp[int(a, 16)] = u(b)
    for blk in re.findall(r"beginbfrange(.*?)endbfrange", s, re.S):
        for a, b, c in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])", blk):
            lo, hi = int(a, 16), int(b, 16)
            if c.startswith("["):
                for i, h in enumerate(re.findall(r"<([0-9A-Fa-f]+)>", c)):
                    mp[lo + i] = u(h)
            else:
                base = int(c[1:-1], 16)
                nb = len(c) - 2
                for i in range(hi - lo + 1):
                    mp[lo + i] = u(("%0" + str(nb) + "x") % (base + i))
    return width, mp


def _pdf_tokens(s):
    i, n = 0, len(s)
    out = []
    ws = b" \t\r\n\x00\x0c"
    delim = b"()<>[]/%"
    while i < n:
        c = s[i:i + 1]
        if c in ws:
            i += 1
        elif c == b"%":
            while i < n and s[i:i + 1] not in b"\r\n":
                i += 1
        elif c == b"(":
            depth, j, buf = 1, i + 1, bytearray()
            while j < n and depth:
                ch = s[j:j + 1]
                if ch == b"\\":
                    nx = s[j + 1:j + 2]
                    if nx in b"01234567" and nx:
                        k = j + 1
                        while k < j + 4 and s[k:k + 1] and s[k:k + 1] in b"01234567":
                            k += 1
                        buf.append(int(s[j + 1:k], 8) & 255)
                        j = k
                        continue
                    buf += {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\x0c"}.get(nx, nx)
                    j += 2
                    continue
                if ch == b"(":
                    depth += 1
                elif ch == b")":
                    depth -= 1
                    if not depth:
                        j += 1
                        break
                buf += ch
                j += 1
            out.append(("s", bytes(buf)))
            i = j
        elif c == b"<":
            if s[i + 1:i + 2] == b"<":
                out.append(("op", "<<"))
                i += 2
            else:
                j = s.index(b">", i)
                h = re.sub(rb"\s", b"", s[i + 1:j])
                if len(h) % 2:
                    h += b"0"
                out.append(("s", bytes.fromhex(h.decode())))
                i = j + 1
        elif c == b">":
            out.append(("op", ">>"))
            i += 2 if s[i + 1:i + 2] == b">" else 1
        elif c in b"[]":
            out.append(("op", c.decode()))
            i += 1
        elif c == b"/":
            j = i + 1
            while j < n and s[j:j + 1] not in ws and s[j:j + 1] not in delim:
                j += 1
            out.append(("n", s[i + 1:j].decode("latin-1")))
            i = j
        else:
            j = i
            while j < n and s[j:j + 1] not in ws and s[j:j + 1] not in delim:
                j += 1
            t = s[i:j].decode("latin-1")
            try:
                out.append(("num", float(t)))
            except ValueError:
                out.append(("op", t))
            i = max(j, i + 1)
    return out


def pdf_text_fragments(d):
    """[(x, y, size, text)] из PDF (stdlib: Flate + ToUnicode). Для простых однотипных документов ЦБ."""
    objs = _pdf_objects(d)
    fonts = {}
    for body in objs.values():
        head = body.partition(b"stream")[0]
        for m in re.finditer(rb"/Font\s*(?:<<(.*?)>>|(\d+)\s+0\s+R)", head, re.S):
            blk = m.group(1) if m.group(1) is not None else objs.get(int(m.group(2)), b"")
            for nm, num in re.findall(rb"/([A-Za-z0-9_.+-]+)\s+(\d+)\s+0\s+R", blk):
                fb = objs.get(int(num), b"")
                tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", fb)
                if tu and nm.decode() not in fonts:
                    fonts[nm.decode()] = _pdf_cmap(_pdf_inflate(objs.get(int(tu.group(1)), b"")))
    frags = []
    for body in objs.values():
        head = body.partition(b"stream")[0]
        if b"/Length" not in head or b"/Type" in head and (b"/XObject" in head or b"/ObjStm" in head or b"/XRef" in head):
            continue
        try:
            data = _pdf_inflate(body)
        except Exception:
            continue
        if b"BT" not in data or b" Tf" not in data:
            continue
        stack, font, size = [], None, 10.0
        lm = [0.0, 0.0]
        for kind, v in _pdf_tokens(data):
            if kind != "op" or v in ("[", "]", "<<", ">>"):
                stack.append((kind, v))
                continue
            args = stack
            stack = []
            if v == "Tf":
                nm = [a for a in args if a[0] == "n"]
                nu = [a[1] for a in args if a[0] == "num"]
                font = nm[-1][1] if nm else font
                size = nu[-1] if nu else size
            elif v == "Tm":
                nu = [a[1] for a in args if a[0] == "num"]
                if len(nu) >= 6:
                    lm = [nu[4], nu[5]]
            elif v in ("Td", "TD"):
                nu = [a[1] for a in args if a[0] == "num"]
                if len(nu) >= 2:
                    lm = [lm[0] + nu[-2], lm[1] + nu[-1]]
            elif v in ("TJ", "Tj", "'", '"'):
                width, mp = fonts.get(font, (1, None))
                txt = ""
                for k, a in args:
                    if k != "s":
                        continue
                    if mp is None:
                        txt += a.decode("cp1252", "replace")
                    else:
                        w = width if len(a) % width == 0 else 1
                        for p in range(0, len(a), w):
                            txt += mp.get(int.from_bytes(a[p:p + w], "big"), "")
                if txt:
                    frags.append((lm[0], lm[1], size, txt))
    return frags


# ── источник 1: среднесрочный прогноз Банка России (PDF) ──

KR_CBR_PAGE = "https://www.cbr.ru/dkp/mp_dec/decision_key_rate/"


def _kr_num(s):
    return float(s.replace(",", "."))


def _kr_cells(txt):
    """'19,2 14,6 12,5–13,5 9,0–10,0' -> [(low, high)]. Одиночное значение с двумя знаками (14,61) — сноска, отбрасываем её."""
    toks = re.findall(r"(\d+(?:,\d+)?)(?:\s*[–-]\s*(\d+(?:,\d+)?))?", txt)
    cells = []
    for a, b in toks:
        if not b and re.fullmatch(r"\d+,\d\d", a):
            a = a[:-1]
        cells.append((_kr_num(a), _kr_num(b or a)))
    return cells


def _kr_parse_pdf(data, label="Ключевая ставка", tail=r"годовых(.*)$", need=""):
    """Строка таблицы основных параметров прогноза -> {год: (low, high)}.
    По умолчанию «Ключевая ставка, в среднем за год»; для инфляции — label «Инфляция», need «декабрь», tail r"года(.*)$"."""
    fr = pdf_text_fragments(data)
    big = [f for f in fr if f[2] >= 8]          # мелкий шрифт — сноски и надстрочные индексы

    def row(y, tol=2.5):
        rs = sorted((f for f in big if abs(f[1] - y) <= tol), key=lambda f: f[0])
        return "".join(f[3] for f in rs)
    lab = [f for f in big if f[3].startswith(label) and need in row(f[1])]
    first = [f for f in big if f[3].startswith("Инфляция")]
    if not lab or not first:
        raise ValueError("нет строки таблицы")
    y0 = max(f[1] for f in first)
    m = re.search(tail, row(lab[0][1]))
    cells = _kr_cells(m.group(1) if m else "")
    hdr = "".join(f[3] for f in sorted((f for f in big if y0 + 3 < f[1] < y0 + 45 and f[0] > 150), key=lambda f: (f[0], -f[1])))
    years = sorted({int(y) for y in re.findall(r"20\d\d", hdr)})
    if len(years) != len(cells) or not years:
        raise ValueError("не сошлись годы (%d) и значения (%d)" % (len(years), len(cells)))
    return {y: c for y, c in zip(years, cells)}


def _kr_cbr():
    s = http_text(KR_CBR_PAGE, 30)
    links = re.findall(r'href="(/Content/Document/File/\d+/forecast_(\d\d)(\d\d)(\d\d)\.pdf)"', s)
    if not links:
        raise ValueError("нет ссылки на прогноз")
    path, yy, mm, dd = max(links, key=lambda x: x[1:])
    as_of = "20%s-%s-%s" % (yy, mm, dd)
    st = store()
    ck = "kr_pdf:" + path
    pt = st.get(ck)
    if pt is None:
        yr = _kr_parse_pdf(http_bytes("https://www.cbr.ru" + path, 40))
        pt = {str(k): list(v) for k, v in yr.items()}
        st.put(ck, pt)                     # PDF конкретного заседания не меняется
    years = {int(k): tuple(v) for k, v in pt.items()}
    # в таблице первым идёт последний фактический год: он не прогноз
    return {"as_of": as_of, "url": "https://www.cbr.ru" + path, "years": years}


def inflation_forecast():
    """Прогноз инфляции (декабрь к декабрю) из того же среднесрочного прогноза Банка России.
    {source: 'cbr'|'none', as_of, url, yearly:[{year, low, high, mid}]} — только текущий и будущие годы.
    Кэш 24 часа; при ошибке — source 'none' и пустой yearly (вызывающий код берёт свою оценку, например 4%)."""
    st = store()
    raw = st.get("infl_src", ttl=KR_TTL)
    if raw is None:
        try:
            s = http_text(KR_CBR_PAGE, 30)
            links = re.findall(r'href="(/Content/Document/File/\d+/forecast_(\d\d)(\d\d)(\d\d)\.pdf)"', s)
            if not links:
                raise ValueError("нет ссылки на прогноз")
            path, yy, mm, dd = max(links, key=lambda x: x[1:])
            yr = _kr_parse_pdf(http_bytes("https://www.cbr.ru" + path, 40), "Инфляция", r"года(.*)$", "декабрь")
            raw = {"source": "cbr", "as_of": "20%s-%s-%s" % (yy, mm, dd), "url": "https://www.cbr.ru" + path,
                   "years": {str(k): list(v) for k, v in yr.items()}}
            st.put("infl_src", raw)
        except Exception as e:  # noqa: BLE001
            return {"source": "none", "as_of": "", "url": "", "yearly": [], "error": str(e)[:140]}
    y0 = date.today().year
    yearly = [{"year": int(k), "low": v[0], "high": v[1], "mid": round((v[0] + v[1]) / 2.0, 2)}
              for k, v in sorted(raw["years"].items()) if int(k) >= y0]
    return {"source": raw["source"], "as_of": raw["as_of"], "url": raw["url"], "yearly": yearly}


# ── источник 2: макроопрос Банка России (HTML-таблица) ──

KR_SURVEY_PAGE = "https://cbr.ru/statistics/ddkp/mo_br/"
_MONTHS_RU = ["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]


def _kr_survey():
    s = http_text(KR_SURVEY_PAGE, 30)
    i = s.find("Ключевая ставка")
    j = s.rfind("<table", 0, i)
    k = s.find("</table>", i)
    if i < 0 or j < 0 or k < 0:
        raise ValueError("нет таблицы опроса")
    rows = []
    for r in re.findall(r"<tr.*?</tr>", s[j:k], re.S):
        rows.append([re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).replace("&nbsp;", " ").strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)])
    hdr = next(r for r in rows if sum(bool(re.match(r"20\d\d", c)) for c in r) >= 3)
    kr = next(r for r in rows if r and r[0].startswith("Ключевая ставка"))
    years = {}
    for h, v in zip(hdr, kr):
        m, y = re.match(r"(20\d\d)", h), re.match(r"\s*(\d+,\d+|\d+)", v)
        if m and y and "факт" not in h:
            years[int(m.group(1))] = (_kr_num(y.group(1)),) * 2        # медиана; в скобках — прошлый опрос
    if not years:
        raise ValueError("нет прогнозных значений")
    plain = re.sub(r"<[^>]+>", " ", s)
    m = re.search(r"Результаты опроса:\s*([А-Яа-я]+)\s+(20\d\d)", plain)
    as_of = ""
    if m:
        mo = next((n + 1 for n, p in enumerate(_MONTHS_RU) if m.group(1).lower().startswith(p)), 0)
        as_of = "%s-%02d" % (m.group(2), mo) if mo else m.group(2)
    return {"as_of": as_of, "url": KR_SURVEY_PAGE, "years": years}


# ── фактическая ключевая ставка ──

def key_rate_on(series, d):
    """Ключевая ставка, действовавшая на дату d (ISO), по ряду [[дата, %]]; None, если ряд не покрывает дату."""
    if not series or d < series[0][0]:
        return None
    i = bisect.bisect_right([x[0] for x in series], d) - 1
    return series[i][1]


def _kr_current():
    ser = key_rate_series()
    if not ser:
        raise ValueError("нет ключевой ставки")
    return ser, ser[-1][1]


# ── построение месячного пути ──

def _kr_days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def _kr_add(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def _kr_interp(knots, t):
    if t <= knots[0][0]:
        return knots[0][1]
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if t <= x1:
            return y0 + (y1 - y0) * (t - x0) / ((x1 - x0) or 1)
    return knots[-1][1]


def _kr_month_starts(today, n):
    y, m = int(today[:4]), int(today[5:7])
    out = []
    for _ in range(n):
        m += 1
        if m > 12:
            y, m = y + 1, 1
        out.append("%04d-%02d-01" % (y, m))
    return out


def _kr_path_from_yearly(yearly, k0, today, series):
    """Путь ставки, у которого среднее за год совпадает со срединным значением прогноза.
    Узлы: сегодня = текущая ставка; для текущего года — середина оставшейся части (цель = средняя ставка на остаток года,
    выведенная из годовой средней и уже известной фактической части); для следующих лет — 2 июля.
    Между узлами линейно, после последнего — плоско. Значения узлов подгоняются итерациями так, чтобы дневное среднее
    по году (для текущего — по оставшейся его части) равнялось целевому."""
    cur = int(today[:4])
    spans = []          # [год, t_от, t_до, цель, t_узла] в днях от сегодня
    for y in sorted(yearly):
        if y < cur:
            continue
        lo, hi = yearly[y]
        mid = (lo + hi) / 2.0
        b = _kr_days(today, "%d-12-31" % y)
        if y == cur:
            if b < 20:
                continue
            ny = _kr_days("%d-01-01" % y, "%d-12-31" % y) + 1
            done = _kr_days("%d-01-01" % y, today)
            tot = 0.0
            for i in range(done):
                r = key_rate_on(series, _kr_add("%d-01-01" % y, i))
                if r is None:
                    tot = None
                    break
                tot += r
            if tot is not None and ny > done:
                rest = (mid * ny - tot) / (ny - done)
                if abs(rest - mid) <= 6 and rest > 0.5:
                    mid = rest
            spans.append([y, 0, b, mid, b / 2.0])
        else:
            a = _kr_days(today, "%d-01-01" % y)
            spans.append([y, a, b, mid, float(_kr_days(today, "%d-07-02" % y))])
    if not spans:
        raise ValueError("нет прогнозных лет")
    vals = [s[3] for s in spans]
    for _ in range(40):
        knots = [(0.0, k0)] + [(s[4], v) for s, v in zip(spans, vals)]
        worst = 0.0
        for n_, s in enumerate(spans):
            avg = sum(_kr_interp(knots, t) for t in range(int(s[1]), int(s[2]) + 1)) / (s[2] - s[1] + 1)
            err = s[3] - avg
            worst = max(worst, abs(err))
            vals[n_] = max(0.5, vals[n_] + 0.8 * err)
        if worst < 0.005:
            break
    knots = [(0.0, k0)] + [(s[4], v) for s, v in zip(spans, vals)]
    pts = [(today, round(k0, 3))]
    for d in _kr_month_starts(today, KR_HORIZON_M):
        pts.append((d, round(_kr_interp(knots, _kr_days(today, d)), 3)))
    return pts


def _kr_market_path(k0, today):
    """Путь из форвардных ставок КБД: 3-месячный форвард f(t) на горизонте t (эффективная годовая ставка).
    Ключевая ставка ~ форвард минус срочная премия: премия принята 0,75 п.п. в год горизонта, но не более 1,5 п.п.
    Начало привязано к текущей ставке: сдвиг (k0 - f(0)) затухает линейно за 2 года. Это грубая оценка рыночных
    ожиданий, а не прогноз ЦБ."""
    if not kbd_curve():
        raise ValueError("нет КБД")

    def z(t):
        return (1 + kbd_at(t) / 100.0) ** t

    def fwd(t):
        h = 0.25
        return ((z(t + h) / z(t)) ** (1 / h) - 1) * 100.0
    f0 = fwd(0.0)
    pts = [(today, round(k0, 3))]
    for d in _kr_month_starts(today, KR_HORIZON_M):
        t = _kr_days(today, d) / 365.0
        pts.append((d, round(max(0.5, fwd(t) + (k0 - f0) * max(0.0, 1 - t / 2.0) - min(1.5, 0.75 * t)), 3)))
    return pts


def _kr_flat_path(k0, today):
    return [(today, round(k0, 3))] + [(d, round(k0, 3)) for d in _kr_month_starts(today, KR_HORIZON_M)]


def _kr_yearly_from_path(path):
    by = defaultdict(list)
    for d, v in path:
        by[int(d[:4])].append(v)
    return [{"year": y, "low": round(min(v), 2), "high": round(max(v), 2), "mid": round(sum(v) / len(v), 2)} for y, v in sorted(by.items())]


def _kr_try(src, today):
    """Один источник -> dict с path/yearly/as_of либо исключение."""
    ser, k0 = _kr_current()
    if src in ("cbr", "survey"):
        st = store()
        ck = "kr_src:" + src
        raw = st.get(ck, ttl=KR_TTL)
        if raw is None:
            raw = (_kr_cbr if src == "cbr" else _kr_survey)()
            st.put(ck, {"as_of": raw["as_of"], "url": raw["url"], "years": {str(k): list(v) for k, v in raw["years"].items()}})
        years = {int(k): tuple(v) for k, v in raw["years"].items() if int(k) >= int(today[:4])}     # фактические годы не нужны
        path = _kr_path_from_yearly(years, k0, today, ser)
        yearly = [{"year": y, "low": lo, "high": hi, "mid": round((lo + hi) / 2.0, 2)} for y, (lo, hi) in sorted(years.items())]
        return {"as_of": raw["as_of"], "url": raw["url"], "yearly": yearly, "path": path, "key_rate": k0}
    path = _kr_market_path(k0, today) if src == "market" else _kr_flat_path(k0, today)
    return {"as_of": today, "url": "", "yearly": _kr_yearly_from_path(path), "path": path, "key_rate": k0}


def keyrate_forecast_info(mode=None):
    """{source, source_name, mode, as_of, yearly:[{year, low, high, mid}], path:[(дата, %)], key_rate, tried:{источник: ошибка}}.
    mode — из настройки keyrate_mode; пробуем выбранный источник, затем следующие по цепочке cbr -> survey -> market -> flat.
    Кэш источников 24 часа (в базе), путь на сегодня — в памяти."""
    if mode is None:
        try:
            mode = load_config().get("keyrate_mode")
        except Exception:  # noqa: BLE001
            mode = None
    if mode not in KR_MODES:
        mode = "cbr"
    today = date.today().isoformat()
    ck = (mode, today)
    with _kr_lock:
        hit = _kr_mem.get(ck)
        if hit and time.time() - hit[0] < (KR_TTL if hit[1].get("source") != "none" else KR_ERR_TTL):
            return hit[1]
        tried, res = {}, None
        for src in KR_MODES[KR_MODES.index(mode):]:
            try:
                res = _kr_try(src, today)
                res["source"] = src
                break
            except Exception as e:  # noqa: BLE001
                tried[src] = str(e)[:140] or e.__class__.__name__
        if res is None:
            res = {"source": "none", "as_of": today, "url": "", "yearly": [], "path": [], "key_rate": None}
        res.update(mode=mode, tried=tried, source_name=KR_NAMES.get(res["source"], "нет данных"))
        _kr_mem.clear()
        _kr_mem[ck] = (time.time(), res)
        return res


def keyrate_path():
    """Месячный путь ключевой ставки [(дата ISO, % годовых)] на ~4 года вперёд (первая точка — сегодня).
    Источник — keyrate_forecast_info(); пусто, если ничего не получилось."""
    try:
        return keyrate_forecast_info()["path"]
    except Exception:  # noqa: BLE001
        return []


def keyrate_at(path, d):
    """Прогнозная ставка на дату d (ISO) по пути (линейная интерполяция между месячными точками)."""
    if not path:
        return None
    if d <= path[0][0]:
        return path[0][1]
    ds = [p[0] for p in path]
    i = bisect.bisect_right(ds, d)
    if i >= len(path):
        return path[-1][1]
    (d0, v0), (d1, v1) = path[i - 1], path[i]
    w = _kr_days(d0, d) / float(_kr_days(d0, d1) or 1)
    return v0 + (v1 - v0) * w

# ═══════════════════ сигналы: дороже/дешевле аналогов по всему рынку, история, возможные замены ═══════════════════

SIG_TTL = 900
SIG_HIST_KEY = "sig_hist_v1"
SIG_HIST_DAYS = 120
SIG_EPS = 0.25           # |diff| (п.п.) от которого выпуск считается «дешевле/дороже» аналогов
SIG_OUTLIER = 8.0        # |diff| больше этого, доходность выше SIG_MAX_YIELD или спред < -6: вероятно дефолтный/«битый» выпуск
SIG_MAX_YIELD = 40.0
SIG_MAX_GAIN = 8.0       # разницу доходности больше этого в замены не берём: это уже разница в риске, а не «недооценка»
SIG_MIN_SIGMA = 0.4      # нижняя граница разброса аналогов (п.п.) для z-оценки
_sig = {"t": 0, "rows": [], "meta": {}}
_sig_lock = threading.Lock()
_sig_hist = {"t": 0, "d": None}


def _sig_pool(uni):
    """Выпуски, участвующие в сравнении: рублёвые корпоративные с рейтингом, без флоатеров и бессрочных."""
    out = []
    for e in uni:
        if e["kind"] != "corp" or e["cur"] != "RUB" or not (0 < e["yield"] < 60) or not e.get("dur") or e["dur"] < 0.1:
            continue
        if not e["_rt"] or e.get("spread") is None:
            continue
        ci = e["_ci"] or {}
        if ci.get("floating") or ci.get("perpetual"):
            continue
        out.append(e)
    return out


def _sig_index(pool):
    """Индексы для быстрого перебора кандидатов: по индексу рейтинга, отсортировано по дюрации."""
    by = defaultdict(list)
    for e in pool:
        by[RATING_SCALE.index(e["_rt"]["v"])].append(e)
    idx = {}
    for ri, lst in by.items():
        lst.sort(key=lambda e: e["dur"])
        idx[ri] = (lst, [e["dur"] for e in lst])
    return idx


def _sig_cands(me, ri, idx, rng=2):
    """Кандидаты в аналоги (до применения _bc_cost): рейтинг ±rng ступеней и дюрация в допустимом окне."""
    d = me["dur"]
    lo, hi = d * 0.4, d * 2.5
    for r in range(ri - rng, ri + rng + 1):
        it = idx.get(r)
        if not it:
            continue
        lst, durs = it
        for e in lst[bisect.bisect_left(durs, lo):bisect.bisect_right(durs, hi)]:
            yield e


def _sig_nearest(me, ri, idx, isin_skip=None):
    """Ближайшие аналоги так же, как в карточке: 30 лучших -> отсев выбросов по спреду -> 12 лучших. Возвращает [(cost, e)]."""
    sc = []
    for e in _sig_cands(me, ri, idx):
        if e is me or e["_isin"] == isin_skip:
            continue
        c = _bc_cost(me, e, ri)
        if c is not None:
            sc.append((c, e["_isin"], e))
    sc.sort(key=lambda x: (x[0], x[1]))
    sps = sorted(x[2]["spread"] for x in sc[:30])
    if len(sps) >= 5:
        m0 = sps[len(sps) // 2]
        sc = [x for x in sc if abs(x[2]["spread"] - m0) <= 8]
    return [(c, e) for c, _, e in sc[:12]]


def _sig_median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _sig_row(e, near):
    sp = [a["spread"] for _, a in near]
    med = _sig_median(sp)
    mad = _sig_median([abs(x - med) for x in sp]) * 1.4826
    diff = e["spread"] - med
    ci, rt = e["_ci"] or {}, e["_rt"]
    return {"isin": e["_isin"], "id": e["id"], "name": e["name"], "rating": rt["v"], "rating_approx": bool(rt.get("approx")),
            "sector": ci.get("sector"), "yield": e["yield"], "spread": e["spread"], "dur": e["dur"], "price": e.get("price"),
            "mat": e.get("mat"), "med": round(med, 2), "diff": round(diff, 2), "sigma": round(max(mad, SIG_MIN_SIGMA), 2),
            "z": round(diff / max(mad, SIG_MIN_SIGMA), 2), "n": len(sp), "turn": e.get("turn") or 0, "trades": e.get("trades") or 0,
            "amort": bool(ci.get("amort")), "sub": bool(ci.get("subordinated")),
            "outlier": bool(abs(diff) > SIG_OUTLIER or e["yield"] > SIG_MAX_YIELD or e["spread"] < -6),
            "refs": [{"isin": a["_isin"], "name": a["name"], "spread": a["spread"]} for _, a in near[:3]]}


def _sig_hist_load():
    if _sig_hist["d"] is None or time.time() - _sig_hist["t"] > 60:
        _sig_hist["d"] = store().get(SIG_HIST_KEY) or {}
        _sig_hist["t"] = time.time()
    return _sig_hist["d"]


def _sig_snapshot(rows):
    """Сохраняет сегодняшний снимок diff (по будням; ликвидные выпуски), хранит SIG_HIST_DAYS последних дней."""
    h = _sig_hist_load()
    today = date.today()
    if today.weekday() < 5 and rows:
        h[today.isoformat()] = {r["isin"]: r["diff"] for r in rows if r["turn"] >= 2e5}
        for d in sorted(h)[:-SIG_HIST_DAYS]:
            h.pop(d, None)
        try:
            store().put(SIG_HIST_KEY, h)
        except Exception:  # noqa: BLE001
            pass
    return h


def _sig_streak(h, isin, diff):
    """Сколько последних снимков подряд знак и величина diff те же (дешевле/дороже). Возвращает (streak, series[старые..новые])."""
    days = sorted(h)
    ser = [h[d].get(isin) for d in days]
    sgn = 1 if diff >= SIG_EPS else -1 if diff <= -SIG_EPS else 0
    n = 0
    if sgn:
        for v in reversed(ser):
            if v is not None and v * sgn >= SIG_EPS:
                n += 1
            else:
                break
    return n, ser


def _sig_all(force=False):
    """Полный расчёт сигналов по рынку; кэш 15 минут. Возвращает (rows, meta)."""
    if not force and time.time() - _sig["t"] < SIG_TTL and _sig["rows"]:
        return _sig["rows"], _sig["meta"]
    with _sig_lock:
        if not force and time.time() - _sig["t"] < SIG_TTL and _sig["rows"]:
            return _sig["rows"], _sig["meta"]
        t0 = time.time()
        uni = _bc_universe()
        pool = _sig_pool(uni)
        idx = _sig_index(pool)
        rows = []
        for e in pool:
            near = _sig_nearest(e, RATING_SCALE.index(e["_rt"]["v"]), idx)
            if len(near) >= 5:
                rows.append(_sig_row(e, near))
        h = _sig_snapshot(rows)
        days = sorted(h)
        for r in rows:
            n, ser = _sig_streak(h, r["isin"], r["diff"])
            r["streak"] = n
            vals = [v for v in ser if v is not None]
            r["trend"] = round(r["diff"] - vals[-6], 2) if len(vals) >= 6 else (round(r["diff"] - vals[0], 2) if len(vals) >= 2 else None)
            r["hist"] = vals[-30:] if abs(r["z"]) >= 1 and len(vals) >= 2 else None
        meta = {"pool": len(pool), "scored": len(rows), "hist_days": len(days), "hist_from": days[0] if days else None,
                "calc_s": round(time.time() - t0, 2), "updated": time.time()}
        _sig.update(t=time.time(), rows=rows, meta=meta)
        return rows, meta


def _sig_replacements(cfg, acc, pool_idx, rows_by_isin, fee, thr, min_turn, tax_rate):
    """Для каждой облигации портфеля: возможные замены с большей доходностью (по рыночной доходности) с учётом издержек."""
    try:
        pf = build_bonds(cfg, acc, False)["rows"]
    except Exception:  # noqa: BLE001
        return [], []
    uni = {}
    for e in _bc_universe():
        uni[e["_isin"]] = e
        uni[e["id"]] = e
    pool, idx = pool_idx
    held = {r.get("ticker") for r in pf}
    out, skipped = [], []
    for r in pf:
        isin = r.get("ticker")
        V = r.get("value_rub") or 0
        base = {"isin": isin, "name": r.get("name"), "qty": r.get("qty"), "value": round(V, 2), "rating": (r.get("rating") or {}).get("v")}
        me = uni.get(isin)
        if not me or V <= 0 or r.get("cur") not in (None, "rub", "RUB"):
            skipped.append(dict(base, why="нет рыночных данных или не рублёвая"))
            continue
        if me["kind"] != "corp":
            skipped.append(dict(base, why="ОФЗ: сравнение не применяется"))
            continue
        ci = me["_ci"] or {}
        if ci.get("floating") or r.get("floating"):
            skipped.append(dict(base, why="флоатер: спред к КБД не сопоставим"))
            continue
        if not me["_rt"]:
            skipped.append(dict(base, why="нет рейтинга"))
            continue
        ri = RATING_SCALE.index(me["_rt"]["v"])
        y0 = me["yield"]
        mine_sig = rows_by_isin.get(me["_isin"])
        if not mine_sig or mine_sig["outlier"]:
            skipped.append(dict(base, why="нет надёжного сравнения с аналогами (нет спреда или аномальные данные)"))
            continue
        cands = []
        for t in _sig_cands(me, ri, idx):
            if t is me or t["_isin"] in held or t["yield"] <= y0 or (t.get("turn") or 0) < min_turn:
                continue
            c = _bc_cost(me, t, ri)
            if c is None or c > 2.5 or abs(t["dur"] - me["dur"]) / max(t["dur"], me["dur"], 0.5) > 0.35:
                continue
            cands.append((c, t))
        # потолок доходности: цель не должна быть выбросом относительно собственных аналогов
        price, buy, nom, qty = r.get("price_pct"), r.get("buy_pct"), r.get("nominal") or 1000.0, r.get("qty") or 0
        tax = 0.0
        if price and buy and price > buy:
            tax = tax_rate * (price - buy) / 100.0 * nom * qty
        cost_rub = 2 * fee * V + tax
        opts = []
        for c, t in cands:
            tr = rows_by_isin.get(t["_isin"])
            if tr is None or tr["n"] < 5:
                continue
            if tr["outlier"]:
                continue
            gain = t["yield"] - y0
            if gain > SIG_MAX_GAIN:
                continue
            hz = min(5.0, max(0.5, min(me["dur"], t["dur"])))
            net = gain - cost_rub / V * 100.0 / hz
            rt_i = RATING_SCALE.index(t["_rt"]["v"])
            gain_rub = V * gain / 100.0
            opts.append({"isin": t["_isin"], "name": t["name"], "rating": t["_rt"]["v"], "rating_worse": rt_i > ri,
                         "rating_better": rt_i < ri, "sector": (t["_ci"] or {}).get("sector"), "yield": t["yield"], "dur": t["dur"],
                         "spread": t["spread"], "turn": t.get("turn") or 0, "trades": t.get("trades") or 0, "mat": t.get("mat"),
                         "diff": tr["diff"], "z": tr["z"], "gain_pp": round(gain, 2), "net_pp": round(net, 2),
                         "gain_rub_year": round(gain_rub), "net_rub_year": round(V * net / 100.0),
                         "breakeven_months": round(cost_rub / gain_rub * 12, 1) if gain_rub > 0 else None, "horizon": round(hz, 1)})
        opts = [o for o in opts if o["net_pp"] >= thr]
        opts.sort(key=lambda o: -o["net_pp"])
        better = [o for o in opts if not o["rating_worse"]][:3]
        worse = [o for o in opts if o["rating_worse"]][:2]
        if better or worse:
            out.append(dict(base, yield_=y0, dur=me["dur"], spread=me["spread"], price_pct=price, buy_pct=buy, sector=ci.get("sector"),
                            turn=me.get("turn") or 0, diff=mine_sig["diff"] if mine_sig else None, z=mine_sig["z"] if mine_sig else None,
                            cost_rub=round(cost_rub), commission_rub=round(2 * fee * V), tax_rub=round(tax),
                            cost_pp=round(cost_rub / V * 100, 2), options=better, options_worse=worse))
    out.sort(key=lambda x: -((x["options"] or x["options_worse"])[0]["net_rub_year"]))
    return out, skipped


def signals_payload(cfg, acc, q=None):
    q = q or {}

    def num(k, d, lo, hi):
        try:
            return min(hi, max(lo, float(q.get(k, d))))
        except (TypeError, ValueError):
            return d
    min_turn = num("min_turn", 1e6, 0, 1e10)
    fee = num("fee", 0.3, 0, 5) / 100.0
    thr = num("threshold", 1.0, 0, 20)
    tax_rate = num("tax", 13, 0, 50) / 100.0
    rows, meta = _sig_all(q.get("force") == "1")
    liquid = [r for r in rows if r["turn"] >= min_turn]
    n_out = sum(1 for r in liquid if r["outlier"])
    liquid_ok = [r for r in liquid if not r["outlier"]]
    uni = _bc_universe()
    pool = _sig_pool(uni)
    by = {r["isin"]: r for r in rows}
    repl, skipped = _sig_replacements(cfg, acc, (pool, _sig_index(pool)), by, fee, thr, min_turn, tax_rate)
    cheap = sorted((r for r in liquid_ok if r["diff"] >= SIG_EPS), key=lambda r: -r["z"])
    rich = sorted((r for r in liquid_ok if r["diff"] <= -SIG_EPS), key=lambda r: r["z"])
    outl = [r for r in liquid if r["outlier"]]
    keep = {r["isin"] for r in cheap[:150]} | {r["isin"] for r in rich[:150]} | {r["isin"] for r in outl[:60]}
    return {"rows": [r for r in liquid if r["isin"] in keep],
            "kpis": {"universe": len(liquid), "outliers": n_out, "cheap": len(cheap), "rich": len(rich),
                     "cheap_strong": sum(1 for r in cheap if r["z"] >= 2), "rich_strong": sum(1 for r in rich if r["z"] <= -2),
                     "med_diff": round(_sig_median([r["diff"] for r in liquid_ok]), 2) if liquid_ok else None},
            "meta": meta, "params": {"min_turn": min_turn, "fee": fee * 100, "threshold": thr, "tax": tax_rate * 100},
            "replacements": repl, "skipped": skipped, "eps": SIG_EPS}
# ═══════════════════ мониторинг портфеля: тревоги, ликвидность, история спредов ═══════════════════
# Источники: журнал рейтинговых действий (ratings_log_v1, канал @issuerRatings), рейтинги и статус «под наблюдением»
# из каталога T-Invest, история торгов и описание выпуска на Мосбирже (ISS), кривая КБД по датам.
# Чего программа НЕ видит: факт оплаты купона (ISS его не публикует), поэтому «задержка выплаты» определяется
# только косвенно: флаги дефолта в описании выпуска на Мосбирже, дефолтный рейтинг (D/RD/C), остановка торгов.

MON_DEFAULTS = {"mon_drop5": 3.0, "mon_drop30": 7.0, "mon_spread30": 2.0, "mon_sell_days": 5.0, "mon_offer_days": 30}
MON_SNAP_KEY, MON_CURVE_KEY = "mon_snap_v1", "kbd_curves_v1"
MON_RT_DAYS, MON_SPARK_DAYS, MON_PART = 90, 90, 0.2        # окно рейтинговых событий, окно спарклайна, доля оборота
_mon_lock = threading.Lock()
_SEV = {"high": 0, "medium": 1, "info": 2}


def mon_thresholds(cfg):
    out = {}
    for k, d in MON_DEFAULTS.items():
        try:
            out[k] = float(cfg.get(k, d))
        except (TypeError, ValueError):
            out[k] = d
    return out


def _mon_ymd(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _mon_hist_for(secid):
    """История торгов выпуска (кэш 6 ч в kv) или None."""
    try:
        h = _bc_history(secid)
        return h if h and h.get("d") else None
    except Exception:  # noqa: BLE001
        return None


def _mon_flags(isin):
    """Флаги дефолта из описания выпуска на Мосбирже (кэш 12 ч)."""
    key = "mon_desc_v1_" + isin
    hit = store().get(key, ttl=12 * 3600)
    if hit is not None:
        return hit
    try:
        j = json.loads(http_text("https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description" % isin, timeout=20))
        d = {r[0]: r[2] for r in j["description"]["data"]}
        out = {"default": str(d.get("HASDEFAULT") or "0") == "1", "tech": str(d.get("HASTECHNICALDEFAULT") or "0") == "1",
               "found": bool(d)}
    except Exception:  # noqa: BLE001
        return {"default": False, "tech": False, "found": False}
    store().put(key, out)
    return out


def _mon_curve_one(d):
    j = json.loads(http_text("https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields&date=" + d))
    return d, [[r[2], round(r[3], 3)] for r in sorted(j["yearyields"]["data"], key=lambda r: r[2])]


def _mon_curves(days):
    """Кривые КБД по датам за последние days дней (кэш в kv навсегда; выходные и праздники хранятся пустыми)."""
    st = store()
    cache = st.get(MON_CURVE_KEY) or {}
    need = [_mon_ymd(i) for i in range(1, days + 1) if (date.today() - timedelta(days=i)).weekday() < 5
            and _mon_ymd(i) not in cache]
    if need:
        for d, pts in pool_map(lambda x: _safe(_mon_curve_one, x), need, workers=8):
            if d is not None:
                cache[d] = pts
        keep = _mon_ymd(800)
        cache = {k: v for k, v in cache.items() if k >= keep}
        st.put(MON_CURVE_KEY, cache)
    return cache


def _interp(pts, t):
    if not pts or t is None:
        return None
    if t <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if t <= x1:
            return y0 + (y1 - y0) * (t - x0) / (x1 - x0)
    return pts[-1][1]


def _curve_on(curves, sorted_dates, d):
    """Кривая на дату d: последняя непустая на эту дату или раньше."""
    import bisect
    i = bisect.bisect_right(sorted_dates, d)
    while i > 0:
        i -= 1
        c = curves.get(sorted_dates[i])
        if c:
            return c
    return None


def _at_or_before(ds, target):
    """Индекс последней даты <= target либо None."""
    import bisect
    i = bisect.bisect_right(ds, target) - 1
    return i if i >= 0 else None


def _mon_match(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)           # «ЛК Европлан» ~ «Европлан», но «Золото Селигдара» != «Селигдар»
    return lo <= hi and sum(len(x) for x in lo) >= 5 and all(len(x) <= 2 for x in hi - lo)


def _mon_issuer_keys(row):
    keys = [name_tokens(_bond_query(row.get("name") or ""))]
    b = _tcat_get(row.get("isin") or row.get("ticker"))
    if b:
        for s in (b.get("br"), _bond_query(b.get("n") or "")):
            if s:
                keys.append(name_tokens(s))
    return [k for k in keys if k]


def _mon_rating_state(row, keys, events):
    """Рейтинговое состояние для таблицы: лучший рейтинг, прогноз, флаг «под наблюдением»."""
    rt = row.get("rating")
    watch, outlook, last = False, "", {}
    b = _tcat_get(row.get("isin") or row.get("ticker"))
    if b:
        for ag, lv, dt, fc, w in b["r"]:
            if w:
                watch = True
            if fc and (ag not in last or dt >= last[ag][0]):
                last[ag] = (dt, fc)
    ws = {}
    for e in events:
        if any(_mon_match(set(e["tokens"]), k) for k in keys):
            if e.get("watch") in ("set", "removed"):
                ws[e["agency"]] = e["watch"] == "set"
            if e.get("outlook") and e["agency"] not in last:
                last[e["agency"]] = (e["date"], e["outlook"])
    if any(ws.values()):
        watch = True
    cands = [x for x in (rt or {}).get("all") or []]
    if cands:
        w = max(cands, key=lambda x: RATING_SCALE.index(x["rating"]))
        outlook = (w.get("outlook") or "").split(" · ")[0]
    if not outlook and last:
        outlook = sorted(last.values())[-1][1]
    return {"v": rt["v"] if rt else None, "agency": rt["agency"] if rt else None, "outlook": outlook,
            "watch": watch, "neg": "негатив" in (outlook or "").lower()}


def _mon_rating_alerts(rows_keys, events, cutoff):
    """Тревоги по журналу рейтинговых действий: одно событие -> одна тревога на все бумаги этого эмитента."""
    out = []
    for e in events:
        if e["date"] < cutoff:
            continue
        et = set(e["tokens"])
        hit = [r for r, keys in rows_keys if any(_mon_match(et, k) for k in keys)]
        if not hit:
            continue
        act, rt, prev = e["action"], e.get("rating"), e.get("prev")
        sev, msg = None, None
        who = "%s: " % e["agency"]
        lvl = "облигации" if e["level"] == "bond" else "эмитент"
        if rt in ("D", "C", "CC") or (act == "понижен" and rt in ("CCC",)):
            sev, msg = "high", who + "дефолтный/преддефолтный уровень рейтинга %s (%s)" % (rt, lvl)
        elif act == "понижен":
            sev, msg = "high", who + "рейтинг понижен%s до %s (%s)" % (" с " + prev if prev else "", rt, lvl)
        elif e.get("watch") == "set" or act == "под наблюдением":
            sev, msg = "medium", who + "рейтинг %s взят «под наблюдение» (%s)" % (rt or "", lvl)
        elif act == "прогноз изменён" and (e.get("outlook") or "") == "негативный":
            sev, msg = "medium", who + "прогноз изменён на негативный, рейтинг %s (%s)" % (rt, lvl)
        elif act == "отозван":
            sev = "medium" if e["level"] == "issuer" else "info"
            msg = who + "рейтинг отозван (%s)%s" % (lvl, "; ранее " + prev if prev else "")
        elif act == "повышен":
            sev, msg = "info", who + "рейтинг повышен%s до %s (%s)" % (" с " + prev if prev else "", rt, lvl)
        elif e.get("outlook") == "негативный":
            sev, msg = "info", who + "рейтинг %s %s, прогноз негативный (%s)" % (rt, act, lvl)
        if not sev:
            continue
        out.append({"id": "rt|%s|%s" % (e["agency"], e["post"]), "severity": sev, "kind": "rating", "date": e["date"],
                    "isin": hit[0].get("isin"), "isins": [h.get("isin") for h in hit], "name": e["issuer"],
                    "bonds": [h.get("name") for h in hit], "message": msg, "url": e.get("url") or
                    "https://t.me/issuerRatings/%s" % e["post"]})
    return out


def _mon_snapshots(rows):
    """Ежедневный снимок цены/спреда по ISIN (хранится 400 дней): запасной источник истории спреда."""
    st = store()
    snap = st.get(MON_SNAP_KEY) or {}
    today = date.today().isoformat()
    changed = False
    for r in rows:
        isin = r.get("isin")
        if not isin or r.get("price_pct") is None:
            continue
        d = snap.setdefault(isin, {})
        if today not in d:
            d[today] = [round(r["price_pct"], 3), r.get("spread")]
            changed = True
    keep = _mon_ymd(400)
    if changed:
        for isin in snap:
            snap[isin] = {k: v for k, v in snap[isin].items() if k >= keep}
        st.put(MON_SNAP_KEY, snap)
    return snap


def build_monitor(cfg, acc):
    t0 = time.time()
    th = mon_thresholds(cfg)
    key = ("monitor", token_key(cfg), acc, tuple(sorted(th.items())))
    hit = mem_get(key, 300)
    if hit:
        return hit
    with _mon_lock:
        hit = mem_get(key, 300)
        if hit:
            return hit
        res = _build_monitor(cfg, acc, th, t0)
        mem_put(key, res)
        return res


def _build_monitor(cfg, acc, th, t0):
    tm = {}
    b = build_bonds(cfg, acc)
    tm["bonds"] = round(time.time() - t0, 2)
    rows = [r for r in (b.get("rows") or []) if r.get("isin") and r.get("qty")]
    return _monitor_core(rows, th, t0, tm, [])


def _monitor_core(rows, th, t0, tm, notes, liquidity=True):
    """Проверки мониторинга для произвольного списка бумаг. rows — строки вида build_bonds (isin, name, ticker, value_rub, qty,
    maturity, call, floating, price_pct, dur, spread, ytm, rating). Портфель и список наблюдения идут одним кодом."""
    today = date.today().isoformat()
    # соответствие ISIN -> код на Мосбирже
    t1 = time.time()
    sec = {}
    try:
        for s in screener_rows():
            if s.get("isin"):
                sec[s["isin"]] = s
    except Exception as e:  # noqa: BLE001
        notes.append("Скринер Мосбиржи недоступен: %s" % str(e)[:80])
    tm["screener"] = round(time.time() - t1, 2)
    t1 = time.time()
    secids = {r["isin"]: (sec.get(r["isin"]) or {}).get("id") or r.get("ticker") or r["isin"] for r in rows}
    hists = dict(zip([r["isin"] for r in rows], pool_map(lambda r: _mon_hist_for(secids[r["isin"]]), rows, workers=8)))
    tm["history"] = round(time.time() - t1, 2)
    t1 = time.time()
    flags = dict(zip([r["isin"] for r in rows], pool_map(lambda r: _mon_flags(r["isin"]), rows, workers=8)))
    tm["flags"] = round(time.time() - t1, 2)
    t1 = time.time()
    try:
        curves = _mon_curves(MON_SPARK_DAYS + 40)
    except Exception as e:  # noqa: BLE001
        curves = {}
        notes.append("Кривая КБД по датам недоступна: %s" % str(e)[:80])
    cdates = sorted(curves)
    tm["kbd_curves"] = round(time.time() - t1, 2)
    snap = _mon_snapshots(rows)
    log = store().get(RT_LOG_KEY) or {"events": []}
    events = log.get("events") or []
    if not events:
        notes.append("Журнал рейтинговых действий пока пуст: он наполняется при синхронизации рейтингов (раздел «Облигации» → обновить рейтинги).")
    # окно торгового календаря для среднего оборота
    win_from = _mon_ymd(30)
    cal = set()
    for h in hists.values():
        if h:
            cal.update(d for d in h["d"] if d > win_from)
    ndays = max(len(cal), 15)
    out_rows, alerts = [], []
    rows_keys = []
    for r in rows:
        isin = r["isin"]
        h = hists.get(isin)
        keys = _mon_issuer_keys(r)
        rows_keys.append((r, keys))
        row = {"isin": isin, "name": r.get("name"), "ticker": r.get("ticker"), "value_rub": r.get("value_rub"),
               "qty": r.get("qty"), "maturity": r.get("maturity"), "call": r.get("call"),
               "floating": bool(r.get("floating")), "price_pct": r.get("price_pct"), "flags": []}
        row["rating"] = _mon_rating_state(r, keys, events)
        price = chg5 = chg30 = sp_now = sp_chg = None
        spark = []
        last_d = None
        if h:
            ds, ps, ys, vs = h["d"], h["p"], h["y"], h["v"]
            last_d = ds[-1]
            price = ps[-1]
            for n, nm in ((5, "chg5"), (30, "chg30")):
                i = _at_or_before(ds, _mon_ymd(n))
                if i is not None and ds[i] >= _mon_ymd(n + 10) and ps[i]:
                    v = round((price / ps[i] - 1) * 100, 2)
                    if nm == "chg5":
                        chg5 = v
                    else:
                        chg30 = v
            # спред к КБД по датам: доходность дня минус КБД на дюрации бумаги
            dur = r.get("dur")
            if dur and not r.get("floating") and cdates:
                sp = []
                for d, y in zip(ds, ys):
                    if y is None or d < _mon_ymd(MON_SPARK_DAYS + 35):
                        continue
                    c = _curve_on(curves, cdates, d)
                    k = _interp(c, dur)
                    if k is not None and 0 < y < 80:
                        sp.append((d, round(y - k, 2)))
                if len(sp) >= 5:
                    sd = [x[0] for x in sp]
                    sp_now = sp[-1][1]
                    i = _at_or_before(sd, _mon_ymd(30))
                    if i is not None and sd[i] >= _mon_ymd(40):
                        sp_chg = round(sp_now - sp[i][1], 2)
                    spark = [[d, v] for d, v in sp if d >= _mon_ymd(MON_SPARK_DAYS)]
            tov = sum(v for d, v in zip(ds, vs) if d > win_from)
            avg = tov / ndays
            row["turnover_avg"] = round(avg)
            row["days_to_sell"] = round((r.get("value_rub") or 0) / (MON_PART * avg), 2) if avg > 0 else None
        else:
            row["turnover_avg"] = None
            row["days_to_sell"] = None
        if len(spark) < 5 and isin in snap:        # запасной вариант: накопленные ежедневные снимки
            sp = sorted((d, v[1]) for d, v in snap[isin].items() if v[1] is not None)
            if len(sp) >= 2:
                spark = [[d, v] for d, v in sp if d >= _mon_ymd(MON_SPARK_DAYS)]
                sp_now = sp[-1][1]
        row.update(price=price, chg5=chg5, chg30=chg30, spread=sp_now if sp_now is not None else r.get("spread"),
                   spread_chg30=sp_chg, spark=spark, last_trade=last_d, ytm=r.get("ytm"))
        row["no_history"] = h is None
        base = {"isin": isin, "isins": [isin], "name": r.get("name"), "bonds": [r.get("name")]}
        # --- ценовые тревоги
        parts, sev = [], None
        for chg, lim, lab in ((chg5, th["mon_drop5"], "5 дней"), (chg30, th["mon_drop30"], "30 дней")):
            if chg is not None and chg <= -lim:
                parts.append("%s %% за %s" % (str(chg).replace(".", ","), lab))
                s = "high" if chg <= -2 * lim else "medium"
                sev = s if sev is None or _SEV[s] < _SEV[sev] else sev
        if parts:
            alerts.append(dict(base, id="px|%s|%s" % (isin, today), severity=sev, kind="price", date=last_d or today,
                               message="Цена упала: " + "; ".join(parts) + (" (последняя цена %s %%)" % str(price).replace(".", ",")
                                                                              if price is not None else ""), url=""))
        if sp_chg is not None and sp_chg >= th["mon_spread30"]:
            s = "high" if sp_chg >= 2 * th["mon_spread30"] else "medium"
            alerts.append(dict(base, id="sp|%s|%s" % (isin, today), severity=s, kind="spread", date=last_d or today,
                               message="Спред к КБД вырос на %s п.п. за 30 дней (сейчас %s п.п.)" % (
                                   str(sp_chg).replace(".", ","), str(sp_now).replace(".", ",")), url=""))
        # --- оферта
        cl = r.get("call")
        if cl and today <= cl <= (date.today() + timedelta(days=int(th["mon_offer_days"]))).isoformat():
            left = (datetime.strptime(cl, "%Y-%m-%d").date() - date.today()).days
            alerts.append(dict(base, id="of|%s|%s" % (isin, cl), severity="high" if left <= 7 else "medium", kind="offer",
                               date=cl, message="Оферта %s (через %d дн.): решите, предъявлять ли бумагу к выкупу. Тип оферты (put/call) проверьте в карточке выпуска" % (
                                   cl[8:] + "." + cl[5:7] + "." + cl[:4], left), url=""))
        # --- признаки дефолта
        fl = flags.get(isin) or {}
        if fl.get("default"):
            alerts.append(dict(base, id="df|%s" % isin, severity="high", kind="default", date=today,
                               message="По данным Мосбиржи, по выпуску допущен дефолт", url="https://www.moex.com/ru/issue.aspx?code=" + isin))
            row["flags"].append("дефолт")
        elif fl.get("tech"):
            alerts.append(dict(base, id="td|%s" % isin, severity="high", kind="default", date=today,
                               message="По данным Мосбиржи, по выпуску был допущен технический дефолт (задержка выплаты). Проверьте, погашена ли задолженность", url="https://www.moex.com/ru/issue.aspx?code=" + isin))
            row["flags"].append("тех. дефолт")
        if last_d and last_d < _mon_ymd(10) and not (r.get("maturity") and r["maturity"] < today):
            alerts.append(dict(base, id="nt|%s|%s" % (isin, last_d), severity="medium", kind="halt", date=last_d,
                               message="Нет торгов с %s: возможна остановка торгов, проверьте выпуск" % (
                                   last_d[8:] + "." + last_d[5:7] + "." + last_d[:4]), url=""))
            row["flags"].append("нет торгов")
        rts = row["rating"]
        if rts["v"] in ("D", "C", "CC"):
            alerts.append(dict(base, id="rd|%s" % isin, severity="high", kind="default", date=today,
                               message="Дефолтный/преддефолтный рейтинг %s (%s)" % (rts["v"], rts["agency"]), url=""))
        elif rts["watch"]:
            alerts.append(dict(base, id="wt|%s" % isin, severity="medium", kind="watch", date=today,
                               message="Рейтинг эмитента под наблюдением (по данным каталога T-Invest или журнала агентств)", url=""))
        if rts["neg"] and not rts["watch"]:
            alerts.append(dict(base, id="ng|%s" % isin, severity="info", kind="outlook", date=today,
                               message="Негативный прогноз по рейтингу (%s)" % (rts["agency"] or ""), url=""))
        # --- ликвидность
        dts = row["days_to_sell"]
        if liquidity and h and (dts is None or dts > th["mon_sell_days"]):
            row["flags"].append("неликвид")
            alerts.append(dict(base, id="lq|%s|%s" % (isin, today[:7]), severity="info", kind="liquidity", date=today,
                               message=("Нет оборота за 30 дней: продать позицию быстро не получится" if dts is None else
                                        "Низкая ликвидность: на продажу позиции нужно ~%s дн. (при 20%% дневного оборота)" % str(dts).replace(".", ",")),
                               url=""))
        out_rows.append(row)
    alerts += _mon_rating_alerts(rows_keys, events, _mon_ymd(MON_RT_DAYS))
    # дубль «под наблюдением» из каталога не нужен, если журнал уже сообщил о том же эмитенте
    wt_logged = {i for a in alerts if a["kind"] == "rating" for i in a.get("isins") or []}
    alerts = [a for a in alerts if not (a["kind"] in ("watch", "outlook") and a["isin"] in wt_logged)]
    alerts.sort(key=lambda a: (_SEV[a["severity"]], _neg(a["date"])))
    for a in alerts:
        for r in out_rows:
            if r["isin"] in (a.get("isins") or []):
                r["n_" + a["severity"]] = r.get("n_" + a["severity"], 0) + 1
    out_rows.sort(key=lambda r: (-(r.get("n_high") or 0), -(r.get("n_medium") or 0), -(r.get("value_rub") or 0)))
    tm["total"] = round(time.time() - t0, 2)
    return {"updated": time.time(), "thresholds": th, "alerts": alerts, "rows": out_rows,
            "summary": {s: sum(1 for a in alerts if a["severity"] == s) for s in _SEV}, "timings": tm, "notes": notes,
            "log": {"events": len(events), "since": min((e["date"] for e in events), default=None)},
            "cal_days": ndays}


def _neg(d):
    """Ключ для сортировки дат по убыванию."""
    return tuple(-ord(c) for c in d or "")


def monitor_watch_rows(isins):
    """Строки списка наблюдения в формате build_bonds (из строк скринера Мосбиржи и каталога T-Invest)."""
    sec = {}
    for s in screener_rows():
        if s.get("isin"):
            sec[s["isin"]] = s
    rows = []
    for isin in isins:
        s = sec.get(isin)
        if not s:
            continue
        ci = tcat_info(isin) or {}
        rows.append({"isin": isin, "name": s.get("name"), "ticker": s.get("id"), "value_rub": 0, "qty": 1, "maturity": s.get("mat"),
                     "call": s.get("offer"), "floating": bool(ci.get("floating")), "price_pct": s.get("price"),
                     "dur": s.get("dur"), "spread": s.get("spread"), "ytm": s.get("yield"),
                     "rating": best_rating(isin, ci.get("name") or s.get("name") or "")})
    return rows


def build_monitor_for(cfg, isins):
    """Те же проверки, что в «Мониторинге», для списка ISIN (без позиции в портфеле: ликвидность и стоимость не считаются)."""
    th = mon_thresholds(cfg)
    isins = sorted(set(i for i in isins if i))
    key = ("monitor_for", tuple(isins), tuple(sorted(th.items())))
    hit = mem_get(key, 300)
    if hit:
        return hit
    with _mon_lock:
        hit = mem_get(key, 300)
        if hit:
            return hit
        t0 = time.time()
        notes = []
        try:
            rows = monitor_watch_rows(isins)
        except Exception as e:  # noqa: BLE001
            rows = []
            notes.append("Скринер Мосбиржи недоступен: %s" % str(e)[:80])
        res = _monitor_core(rows, th, t0, {}, notes, liquidity=False)
        mem_put(key, res)
        return res
# ═══════════════════════════════ сравнение с рынком: индексы и фонды Мосбиржи ═══════════════════════════════
# Наружу уходят только обезличенные GET-запросы к iss.moex.com (история индексов и фондов); состав портфеля никуда не передаётся.

BENCH_CATALOG = [
    {"code": "RGBITR", "kind": "index", "group": "Индексы облигаций", "name": "ОФЗ (индекс гособлигаций)",
     "note": "Государственные облигации России с учётом купонов. Почти без кредитного риска, но цена заметно колеблется при смене ставок."},
    {"code": "RUCBTRNS", "kind": "index", "group": "Индексы облигаций", "name": "Корпоративные облигации (индекс)",
     "note": "Широкая корзина облигаций российских компаний с учётом купонов. Главный ориентир для облигационного портфеля."},
    {"code": "RUCBHYTR", "kind": "index", "group": "Индексы облигаций", "name": "Высокодоходные облигации — индекс ВДО",
     "note": "Облигации небольших компаний с повышенным риском (ВДО). Платят больше, но чаще встречаются просадки и дефолты."},
    {"code": "LQDT", "kind": "fund", "group": "Фонды ликвидности", "name": "LQDT — ликвидность (ВИМ)",
     "note": "Фонд денежного рынка: деньги «лежат» под ставку РЕПО, продаются в день сделки. Самый простой безрисковый ориентир."},
    {"code": "TMON", "kind": "fund", "group": "Фонды ликвидности", "name": "TMON — Денежный рынок (Т-Капитал)",
     "note": "Фонд денежного рынка от Т-Капитала. Работает по тому же принципу, что и LQDT."},
    {"code": "SBMM", "kind": "fund", "group": "Фонды ликвидности", "name": "SBMM — Сберегательный (УК «Первая»)",
     "note": "Фонд денежного рынка от УК «Первая»."},
    {"code": "AKMM", "kind": "fund", "group": "Фонды ликвидности", "name": "AKMM — Денежный рынок (Альфа-Капитал)",
     "note": "Фонд денежного рынка от Альфа-Капитала."},
    {"code": "SBRB", "kind": "fund", "group": "Облигационные фонды", "name": "SBRB — Корпоративные облигации (УК «Первая»)",
     "note": "Фонд, который накапливает купоны в цене пая (выплат пайщикам нет). Диверсифицированная корзина облигаций."},
    {"code": "AKMB", "kind": "fund", "group": "Облигационные фонды", "name": "AKMB — Управляемые облигации (Альфа-Капитал)",
     "note": "Облигационный фонд без выплат: доход остаётся в цене пая."},
    {"code": "TBRU", "kind": "fund", "group": "Облигационные фонды", "name": "TBRU — Облигации (Т-Капитал)",
     "note": "Облигационный фонд без выплат: доход остаётся в цене пая."},
]
BENCH_RF = {"code": "RUSFAR", "kind": "index", "group": "Ставка денежного рынка", "name": "Ставка RUSFAR (накопленная)",
            "note": "Ставка однодневного межбанковского кредита. Накопленная — как если бы деньги каждый день размещались под эту ставку."}
BENCH_TTL = 6 * 3600
BENCH_FROM_MIN = "2019-01-01"
_bench_locks, _bench_locks_lock, _bench_fail = {}, threading.Lock(), {}
_bench_rf_memo = {}


def _bench_kind(code):
    for b in BENCH_CATALOG + [BENCH_RF]:
        if b["code"] == code:
            return b["kind"]
    return "index"


def _bench_iss(url):
    last = None
    for i in range(3):
        try:
            return json.loads(http_text(url, 30))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4 * (i + 1))
    raise last


def _bench_fetch(code, frm, to=None):
    """Дневные закрытия с Мосбиржи (ISS отдаёт страницами по 100 строк). Фонд на нескольких досках за день — строка с максимальным оборотом."""
    fund = _bench_kind(code) == "fund"
    mkt = "shares" if fund else "index"
    cols = "BOARDID,TRADEDATE,CLOSE,VALUE" if fund else "TRADEDATE,CLOSE"
    out, best, start = {}, {}, 0
    for _ in range(80):
        url = ("https://iss.moex.com/iss/history/engines/stock/markets/%s/securities/%s.json?from=%s%s&start=%d"
               "&iss.only=history,history.cursor&history.columns=%s") % (mkt, code, frm, "&till=" + to if to else "", start, cols)
        j = _bench_iss(url)
        rows = (j.get("history") or {}).get("data") or []
        for r in rows:
            if fund:
                _, d, c, v = r
                if c is None:
                    continue
                if d not in best or (v or 0) >= best[d]:
                    best[d], out[d] = (v or 0), float(c)
            elif r[1] is not None:
                out[r[0]] = float(r[1])
        cur = ((j.get("history.cursor") or {}).get("data") or [[0, 0, 100]])[0]
        start = cur[0] + len(rows)
        if not rows or start >= cur[1]:
            break
    return out


def bench_history(code, frm=None, force=False):
    """{дата: закрытие}. Кэш в SQLite под ключом bench_v1:{CODE}: дозагружается хвост (с последней даты минус 5 дней)
    не чаще раза в 6 часов, а при запросе более ранней даты — начало. При сбое сети отдаётся прежний кэш."""
    frm = max(frm or BENCH_FROM_MIN, BENCH_FROM_MIN)
    key = "bench_v1:" + code
    with _bench_locks_lock:
        lk = _bench_locks.setdefault(code, threading.Lock())
    with lk:
        c = store().get(key)
        now = time.time()
        failed = now - _bench_fail.get(code, 0) < 300
        try:
            if not c or not c.get("d"):
                if failed:
                    return {}
                c = {"t": now, "from": frm, "d": _bench_fetch(code, frm)}
                store().put(key, c)
            else:
                changed = False
                if frm < c["from"] and not failed:
                    c["d"].update(_bench_fetch(code, frm, (datetime.strptime(c["from"], "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")))
                    c["from"] = frm
                    changed = True
                if (force or now - c["t"] > BENCH_TTL) and not failed:
                    last = max(c["d"])
                    since = (datetime.strptime(last, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
                    c["d"].update(_bench_fetch(code, since))
                    c["t"] = now
                    changed = True
                if changed:
                    store().put(key, c)
        except Exception:  # noqa: BLE001
            _bench_fail[code] = now
            return (c or {}).get("d") or {}
        return c["d"]


def _bench_carry(series, days):
    """Значения ряда на каждый календарный день с переносом последнего известного вперёд (до первой даты — None)."""
    ks = sorted(series)
    out, j, cur = [], 0, None
    for d in days:
        while j < len(ks) and ks[j] <= d:
            cur = series[ks[j]]
            j += 1
        out.append(cur)
    return out


def bench_rusfar_acc(frm=None):
    """RUSFAR — это ставка в % годовых. Накопленный доход: произведение (1 + r/100/365) по календарным дням. {дата: уровень}."""
    rates = bench_history("RUSFAR", frm)
    if not rates:
        return {}
    ks = sorted(rates)
    memo = _bench_rf_memo.get("v")
    if memo and memo[0] == (len(ks), ks[0], ks[-1]):
        return memo[1]
    d0, d1 = datetime.strptime(ks[0], "%Y-%m-%d").date(), date.today()
    lvl, r, out, j, d = 1.0, rates[ks[0]], {}, 0, d0
    while d <= d1:
        ds = d.isoformat()
        while j < len(ks) and ks[j] <= ds:
            r = rates[ks[j]]
            j += 1
        lvl *= 1 + r / 100.0 / 365.0
        out[ds] = lvl
        d += timedelta(days=1)
    _bench_rf_memo["v"] = ((len(ks), ks[0], ks[-1]), out)
    return out


def bench_lqdt_yield():
    """Текущая доходность фонда ликвидности LQDT, % годовых: рост цены пая за последние 30 дней, пересчитанный на год
    ((P_t / P_t-30) ^ (365 / дни) - 1). None при ошибке. Вызывается и из других разделов (калькулятор, скринер)."""
    key = "bench_lqdt_yield_v1"
    try:
        hit = store().get(key, 3 * 3600)
        if hit and hit.get("v") is not None:
            return hit["v"]
        frm = (date.today() - timedelta(days=75)).isoformat()
        h = bench_history("LQDT", frm)
        if len(h) < 5:
            return None
        ks = sorted(h)
        last = ks[-1]
        if (date.today() - datetime.strptime(last, "%Y-%m-%d").date()).days > 10:
            return None
        target = (datetime.strptime(last, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        i = bisect.bisect_right(ks, target) - 1
        if i < 0:
            return None
        days = (datetime.strptime(last, "%Y-%m-%d") - datetime.strptime(ks[i], "%Y-%m-%d")).days
        if days < 20 or h[ks[i]] <= 0:
            return None
        v = ((h[last] / h[ks[i]]) ** (365.0 / days) - 1) * 100
        v = round(v, 2)
        store().put(key, {"v": v, "d": last})
        return v
    except Exception:  # noqa: BLE001
        return None


# ── расчёты ──

def _bn_stats(xs):
    n = len(xs)
    if n < 2:
        return 0.0, 0.0
    m = sum(xs) / n
    return m, (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5


def _bn_risk(idx, lv, rf, pt=None):
    """Риск-метрики по точкам-индексам idx (торговые дни). lv/rf — уровни по календарным дням. pt — доходности портфеля для беты."""
    L = [lv[i] for i in idx]
    if len(L) < 3 or any(x is None or x <= 0 for x in L):
        return None
    r = [L[k] / L[k - 1] - 1 for k in range(1, len(L))]
    ex = []
    for k in range(1, len(idx)):
        a, b = rf[idx[k - 1]], rf[idx[k]]
        ex.append(r[k - 1] - ((b / a - 1) if a and b else 0.0))
    m, sd = _bn_stats(r)
    peak, dd = L[0], 0.0
    for x in L:
        peak = max(peak, x)
        dd = min(dd, x / peak - 1)
    res = {"vol": sd * 252 ** 0.5, "maxdd": dd, "n": len(r),
           "sharpe": (_bn_stats(ex)[0] / sd * 252 ** 0.5) if sd > 1e-9 else None, "ret": r}
    return res


def _bn_cov(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return None, None
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    va = sum((x - ma) ** 2 for x in a) / (n - 1)
    vb = sum((x - mb) ** 2 for x in b) / (n - 1)
    beta = cov / vb if vb > 1e-14 else None
    corr = cov / (va * vb) ** 0.5 if va > 1e-14 and vb > 1e-14 else None
    return beta, corr


def _bn_window(days, period):
    today = date.today()
    last = len(days) - 1
    s = e = None
    if period == "1m":
        s = (today - timedelta(days=30)).isoformat()
    elif period == "3m":
        s = (today - timedelta(days=91)).isoformat()
    elif period == "12m":
        s = (today - timedelta(days=365)).isoformat()
    elif period == "ytd":
        s = "%d-01-01" % today.year
    elif period == "py":
        s, e = "%d-01-01" % (today.year - 1), "%d-12-31" % (today.year - 1)
    i0 = 0
    if s:
        i0 = next((i for i, d in enumerate(days) if d >= s), None)
        if i0 is None:
            return None
        i0 = max(0, i0 - 1)
    i1 = last
    if e:
        while i1 > 0 and days[i1] > e:
            i1 -= 1
    if i1 <= i0:
        return None
    return i0, i1


def _bn_thin(n, k=400):
    if n <= k:
        return list(range(n))
    step = (n - 1) / float(k - 1)
    idx = sorted({int(round(i * step)) for i in range(k)} | {n - 1})
    return idx


def bench_liquidity(cfg, acc, total):
    mon = build_monitor(cfg, acc)
    rows = [r for r in (mon.get("rows") or []) if (r.get("value_rub") or 0) > 0]
    defs = [("d1", "до 1 дня", lambda x: x <= 1), ("d5", "1–5 дней", lambda x: 1 < x <= 5), ("dm", "больше 5 дней", lambda x: x > 5)]
    bv = sum(r["value_rub"] for r in rows)
    out = []
    for k, label, fn in defs:
        sel = [r for r in rows if r.get("days_to_sell") is not None and fn(r["days_to_sell"])]
        out.append({"key": k, "label": label, "value": sum(r["value_rub"] for r in sel), "count": len(sel)})
    sel = [r for r in rows if r.get("days_to_sell") is None]
    out.append({"key": "na", "label": "нет данных", "value": sum(r["value_rub"] for r in sel), "count": len(sel)})
    for b in out:
        b["share"] = b["value"] / bv * 100 if bv else None
        b["share_total"] = b["value"] / total * 100 if total else None
    slow = sorted([r for r in rows if r.get("days_to_sell") is not None], key=lambda r: -r["days_to_sell"])[:8]
    return {"bonds_value": bv, "bonds_count": len(rows), "portfolio_value": total, "buckets": out,
            "slowest": [{"name": r.get("name"), "isin": r.get("isin"), "value_rub": r["value_rub"], "days": r["days_to_sell"],
                         "turnover": r.get("turnover_avg")} for r in slow],
            "part": MON_PART * 100, "fund_days": 0}


def bench_premium(cfg, acc):
    lq = bench_lqdt_yield()
    b = build_bonds(cfg, acc)
    m = b.get("metrics") or {}
    rows = [r for r in (b.get("rows") or []) if r.get("ytm") is not None and (r.get("value_rub") or 0) > 0 and r.get("qty")]
    ok = [r for r in rows if r["ytm"] <= YTM_HIGH]
    wv = sum(r["value_rub"] for r in ok)
    res = {"lqdt": lq, "ytm_ex": sum(r["ytm"] * r["value_rub"] for r in ok) / wv if wv else None, "ytm": m.get("ytm"), "irr": m.get("irr"), "ytm_tax": m.get("ytm_tax"), "bonds_value": m.get("value"),
           "count": m.get("count"), "high_yield_value": m.get("high_yield_value"), "below": [], "below_value": 0.0}
    if lq is not None:
        res["prem_ytm"] = m["ytm"] - lq if m.get("ytm") is not None else None
        res["prem_ytm_ex"] = res["ytm_ex"] - lq if res["ytm_ex"] is not None else None
        res["prem_irr"] = m["irr"] - lq if m.get("irr") is not None else None
        bl = sorted([r for r in rows if r["ytm"] < lq], key=lambda r: r["ytm"] - lq)
        res["below_value"] = sum(r["value_rub"] for r in bl)
        res["below"] = [{"name": r.get("name"), "isin": r.get("isin"), "ytm": r["ytm"], "diff": r["ytm"] - lq, "value_rub": r["value_rub"]} for r in bl[:12]]
        res["below_count"] = len(bl)
    return res


def bench_payload(cfg, acc, q=None):
    q = q or {}
    period = q.get("period") or "all"
    if period not in ("1m", "3m", "ytd", "12m", "py", "all"):
        period = "all"
    want = {c for c in (q.get("codes") or "").replace(";", ",").split(",") if c}
    key = ("bench", token_key(cfg), acc, period, tuple(sorted(want)))
    hit = mem_get(key, 600)
    if hit:
        return hit
    h = build_history_for(cfg, acc)
    days = h.get("days") or []
    if len(days) < 3:
        return {"error": "Нет операций для сравнения: история портфеля пуста."}
    win = _bn_window(days, period)
    if not win:
        return {"error": "За выбранный период нет данных по портфелю. Выберите период длиннее."}
    i0, i1 = win
    notes = []
    frm = (datetime.strptime(days[i0], "%Y-%m-%d") - timedelta(days=12)).strftime("%Y-%m-%d")
    cat = [b for b in BENCH_CATALOG if not want or b["code"] in want]
    jobs = [b["code"] for b in cat] + ["RUSFAR"]
    if not any(b["code"] == "LQDT" for b in cat):
        jobs.append("LQDT")      # календарь торговых дней
    jobs = list(dict.fromkeys(jobs))
    hs = dict(zip(jobs, pool_map(lambda c: bench_history(c, frm), jobs, workers=6)))
    # торговые дни Мосбиржи
    cal_src = hs.get("LQDT") or next((v for v in hs.values() if v), {})
    d_start, d_end = days[i0], days[i1]
    cal = sorted(d for d in cal_src if d_start < d <= d_end)
    didx = {d: i for i, d in enumerate(days)}
    cal_i = [didx[d] for d in cal if d in didx]
    # безрисковая ставка
    acc_rf = bench_rusfar_acc(frm)
    rf = _bench_carry(acc_rf, days) if acc_rf else [None] * len(days)
    if not acc_rf:
        notes.append("Ставка RUSFAR не загрузилась: коэффициент Шарпа посчитан без вычета безрисковой ставки.")
    elif acc_rf and min(acc_rf) > d_start:
        notes.append("Данные RUSFAR начинаются с %s: до этой даты безрисковая ставка принята равной нулю." % min(acc_rf))
    val, inv, twr = h["value"], h["invested"], h["twr"]
    # портфель
    base_t = twr[i0]
    pw = [x / base_t - 1 for x in twr[i0:i1 + 1]]
    years = (datetime.strptime(d_end, "%Y-%m-%d") - datetime.strptime(d_start, "%Y-%m-%d")).days / 365.25
    total = pw[-1]
    ann = (1 + total) ** (1 / years) - 1 if years >= 0.98 and total > -1 else None
    pidx = [i0] + cal_i
    prk = _bn_risk(pidx, twr, rf)
    if prk:
        k = max(range(len(prk["ret"])), key=lambda n: abs(prk["ret"][n]))
        if abs(prk["ret"][k]) > 0.1:
            notes.append("В истории портфеля есть резкий скачок %s%% за один торговый день (%s). Обычно это следствие неполных цен по какой-то бумаге; "
                         "из-за такого скачка волатильность, просадка и бета портфеля за период могут быть завышены." % (
                             ("%+.0f" % (prk["ret"][k] * 100)).replace("-", "−"), days[pidx[k + 1]]))
    flows = [(i, inv[i] - inv[i - 1]) for i in range(i0 + 1, i1 + 1) if abs(inv[i] - inv[i - 1]) > 0.005]
    net_flow = sum(f for _, f in flows)
    dts = [datetime.strptime(d, "%Y-%m-%d").date() for d in days]

    def xr(v_end, series_flows):
        fl = ([(dts[i0], -val[i0])] if val[i0] > 0 else []) + [(dts[i], -f) for i, f in series_flows] + [(dts[i1], v_end)]
        if years < 0.25:       # годовая ставка по коротким отрезкам вводит в заблуждение
            return None
        try:
            return xirr(fl)
        except Exception:  # noqa: BLE001
            return None

    pf = {"ret": total * 100, "ann": ann * 100 if ann is not None else None,
          "vol": prk["vol"] * 100 if prk else None, "maxdd": prk["maxdd"] * 100 if prk else None,
          "sharpe": prk["sharpe"] if prk else None, "xirr": (lambda x: x * 100 if x is not None else None)(xr(val[i1], flows)),
          "value_start": val[i0], "value_end": val[i1], "net_flow": net_flow, "gain": val[i1] - val[i0] - net_flow}
    # график: проредить
    tix = _bn_thin(i1 - i0 + 1)
    sd = [days[i0 + k] for k in tix]
    series = {"dates": sd, "portfolio": [round(pw[k] * 100, 3) for k in tix], "bench": {}}
    out = []
    for b in cat + [BENCH_RF]:
        code = b["code"]
        if code == "RUSFAR":
            if not acc_rf:
                continue
            lv = rf
        else:
            ser = hs.get(code) or {}
            if not ser:
                out.append(dict(b, available=False, reason="Мосбиржа не отдала историю"))
                continue
            lv = _bench_carry(ser, days)
        j = next((i for i in range(i0, i1 + 1) if lv[i]), None)
        if j is None or j > i1 - 5:
            out.append(dict(b, available=False, reason="нет данных за период"))
            continue
        partial = j > i0 + 7
        if partial:
            notes.append("%s: история в выбранном периоде начинается с %s." % (code, days[j]))
        j = max(j, i0)
        b0 = lv[j]
        cum = [None if lv[i] is None or i < j else lv[i] / b0 - 1 for i in range(i0, i1 + 1)]
        series["bench"][code] = [None if cum[k] is None else round(cum[k] * 100, 3) for k in tix]
        tot_b = cum[-1]
        yrs = (datetime.strptime(d_end, "%Y-%m-%d") - datetime.strptime(days[j], "%Y-%m-%d")).days / 365.25
        ann_b = (1 + tot_b) ** (1 / yrs) - 1 if yrs >= 0.98 and tot_b > -1 else None
        idx = [j] + [i for i in cal_i if i > j]
        rk = _bn_risk(idx, lv, rf)
        e = dict(b, available=True, partial=partial, start=days[j], ret=tot_b * 100, ann=ann_b * 100 if ann_b is not None else None,
                 vol=rk["vol"] * 100 if rk else None, maxdd=rk["maxdd"] * 100 if rk else None,
                 sharpe=rk["sharpe"] if (rk and code != "RUSFAR") else None, beta=None, corr=None, same=None)
        if rk and prk and code != "RUSFAR":
            pr = _bn_risk(idx, twr, rf)
            if pr:
                e["beta"], e["corr"] = _bn_cov(pr["ret"], rk["ret"])
        # «те же деньги в тот же день — в бенчмарк»
        if code != "RUSFAR":
            u = val[j] / lv[j] if val[j] > 0 else 0.0
            sf, ok = [], True
            for i in range(j + 1, i1 + 1):
                f = inv[i] - inv[i - 1]
                if abs(f) > 0.005:
                    if not lv[i]:
                        ok = False
                        break
                    u += f / lv[i]
                    sf.append((i, f))
            if ok and u >= 0:
                fin = u * lv[i1]
                nf = sum(f for _, f in sf)
                x = None
                if j == i0:
                    x = xr(fin, sf)
                e["same"] = {"final": fin, "diff": val[i1] - fin, "gain": fin - val[j] - nf, "xirr": x * 100 if x is not None else None}
        out.append(e)
    res = {"period": period, "start": d_start, "end": d_end, "years": years, "series": series, "portfolio": pf,
           "bench": out, "groups": list(dict.fromkeys([b["group"] for b in BENCH_CATALOG] + [BENCH_RF["group"]])),
           "trading_days": len(cal_i), "notes": notes}
    try:
        res["liquidity"] = bench_liquidity(cfg, acc, val[-1])
    except Exception as e:  # noqa: BLE001
        res["liquidity"] = None
        notes.append("Данные о ликвидности недоступны: %s" % str(e)[:100])
    try:
        res["premium"] = bench_premium(cfg, acc)
    except Exception as e:  # noqa: BLE001
        res["premium"] = None
        notes.append("Данные о доходности облигаций недоступны: %s" % str(e)[:100])
    res["lqdt_yield"] = bench_lqdt_yield()
    return mem_put(key, res)
# ═══════════════════════════════ калькулятор инвестиций: параметры рынка ═══════════════════════════════

CALC_TTL = 3600
CALC_LOSS_GIVEN_DEFAULT = 0.75      # потери при дефолте: 1 − ставка возмещения 25 %
_calc_mem = {}


def _calc_med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _calc_segments(key_rate):
    """Сегменты рынка: ОФЗ, AAA, AA, A, ВДО — текущая медианная доходность и дюрация. Что не нашли — запасной вариант с флагом."""
    pd = RISK_PD_HIST
    loss = lambda *ks: sum(pd[k] for k in ks) / len(ks) / 100.0 * CALC_LOSS_GIVEN_DEFAULT
    # ожидаемые годовые потери: средняя вероятность дефолта по рейтингам сегмента × (1 − 0,25)
    meta = {"ofz": ("ОФЗ", 0.0), "aaa": ("Корпоративные AAA", loss("AAA")),
            "aa": ("Корпоративные AA", loss("AA+", "AA", "AA-")),
            "a": ("Корпоративные A", loss("A+", "A", "A-")),
            "hy": ("ВДО (BB и ниже)", loss("BB+", "BB", "BB-", "B+"))}
    fb = {"ofz": (key_rate - 0.5, 4.0), "aaa": (key_rate + 0.5, 2.5), "aa": (key_rate + 1.5, 2.5),
          "a": (key_rate + 3.0, 2.0), "hy": (key_rate + 8.0, 1.5)}
    got = {}
    try:
        sp = screener_payload()
        rows = sp.get("rows") or []
        buckets = {"aaa": "AAA", "aa": "AA", "a": "A", "hy": "BB и ниже"}
        for k, b in buckets.items():
            sel = [r for r in rows if r.get("kind") == "corp" and r.get("cur") == "RUB" and r.get("rating")
                   and rating_bucket(r["rating"]) == b and 0 < r["yield"] < 60 and (r.get("dur") or 0) > 0.1]
            if len(sel) >= 3:
                got[k] = (_calc_med([r["yield"] for r in sel]), _calc_med([r["dur"] for r in sel]), len(sel))
        sel = [r for r in rows if r.get("kind") == "ofz" and r.get("cur") == "RUB" and 0 < r["yield"] < 60
               and (r.get("dur") or 0) > 0.1 and not r.get("floating") and r.get("sub") != "ofz_floater"]
        if len(sel) >= 3:
            got["ofz"] = (_calc_med([r["yield"] for r in sel]), _calc_med([r["dur"] for r in sel]), len(sel))
    except Exception:  # noqa: BLE001
        pass
    out = {}
    for k, (name, ls) in meta.items():
        g = got.get(k)
        out[k] = {"name": name, "yield": round(g[0] if g else fb[k][0], 2), "dur": round(g[1] if g else fb[k][1], 2),
                  "loss": round(ls * 100, 3), "n": g[2] if g else 0, "estimate": g is None}
    return out


def _calc_portfolio(cfg, acc):
    if not cfg.get("token"):
        return None
    pf = {"value": None, "bonds_value": None, "irr": None, "irr_tax": None, "monthly": None, "coupons_12m": None}
    s = None
    try:
        s = build_summary(cfg, acc, "all")
        pf["value"] = round(s["portfolio"]["total"], 2)
        pf["bonds_value"] = round(s["portfolio"]["bonds"], 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        if s:
            lim = (date.today() - timedelta(days=365)).strftime("%Y-%m")
            net = 0.0
            for m, v in s.get("months") or []:
                if m >= lim:
                    net += (v.get("deposits") or 0.0) - (v.get("withdrawals") or 0.0)
            pf["monthly"] = round(max(net, 0.0) / 12.0, 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        m = build_bonds(cfg, acc).get("metrics") or {}
        irr = m.get("irr") if m.get("irr") is not None else m.get("ytm")
        if irr is not None:
            pf["irr"] = round(irr, 2)
        irt = m.get("irr_tax")
        if irt is not None:
            pf["irr_tax"] = round(irt, 2)
        pf["coupons_12m"] = round(m.get("coupons_12m") or 0.0, 2)
    except Exception:  # noqa: BLE001
        pass
    if all(pf[k] is None for k in ("value", "irr")):
        return None
    return pf


def calc_params(cfg, acc):
    key = (token_key(cfg), acc)
    hit = _calc_mem.get(key)
    if hit and time.time() - hit[0] < CALC_TTL:
        return hit[1]
    res = {"error": None}
    kr, path, kr_src, kr_est = None, [], "", True
    try:
        info = keyrate_forecast_info()
        kr = info.get("key_rate")
        path = [[p[0], p[1]] for p in info.get("path") or []]
        kr_src = info.get("source_name") or ""
        kr_est = info.get("source") == "none"
    except Exception:  # noqa: BLE001
        pass
    if kr is None:
        kr, kr_est = (path[0][1] if path else 16.0), True
        kr_src = kr_src or "нет данных (условное значение)"
    if not path:
        path = [[date.today().isoformat(), kr]]
    res["key_rate"] = {"current": kr, "source": kr_src, "estimate": kr_est, "path": path}
    infl = {"source": "none", "yearly": [], "estimate": True, "default": 4.0}
    try:
        i = inflation_forecast()
        if i.get("source") != "none" and i.get("yearly"):
            infl = {"source": i["source"], "as_of": i.get("as_of"), "yearly": [{"year": y["year"], "mid": y["mid"]} for y in i["yearly"]],
                    "estimate": False, "default": i["yearly"][-1]["mid"]}
    except Exception:  # noqa: BLE001
        pass
    res["inflation"] = infl
    segs = _calc_segments(kr)
    try:
        pf = _calc_portfolio(cfg, acc)
    except Exception:  # noqa: BLE001
        pf = None
    res["segments"] = segs
    ly, lest = None, True
    try:
        f = globals().get("bench_lqdt_yield")
        v = f() if f else None
        if isinstance(v, dict):
            v = v.get("yield")
        if v is not None and 0 < float(v) < 60:
            ly, lest = round(float(v), 2), False
    except Exception:  # noqa: BLE001
        pass
    if ly is None:
        ly = round(kr - 0.7, 2)
    res["lqdt"] = {"yield": ly, "estimate": lest, "spread": 0.7}
    res["deposit"] = {"spread": 1.5, "rate": round(max(kr - 1.5, 0.1), 2)}
    res["portfolio"] = pf
    res["updated"] = datetime.now().strftime("%H:%M")
    _calc_mem[key] = (time.time(), res)
    return res
# ═══════════════════════════════ оферты и конструктор лесенки ═══════════════════════════════
# Справочные подсказки на данных Мосбиржи (bondization) и скринера; не индивидуальные инвестиционные рекомендации.

OF_DAYS, OF_PRICE_EPS, OF_MARGIN = 365, 0.1, 0.5      # окно оферт, дней; допуск цены, п. п.; запас до медианы аналогов, п. п.
OF_CALL_WORDS = ("колл", "call", "досроч")            # Мосбиржа обозначает put-оферту просто «Оферта»; колл — по ключевым словам


def _of_days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def _of_med(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)


def _of_date(s):
    return s if s and len(s) == 10 and not s.startswith("0000") else None


def _of_aci(bz, flows, d):
    """НКД на дату d на одну облигацию: линейно внутри купонного периода (по ближайшему будущему купону потоков)."""
    prev = [c["coupondate"] for c in bz["coupons"] if c.get("coupondate") and c["coupondate"] <= d]
    nxt = [(x[0], x[1]) for x in flows if x[0] > d and x[1] > 0]
    if not prev or not nxt:
        return 0.0
    p0, (n0, amt) = max(prev), min(nxt)
    span = _of_days(p0, n0)
    return amt * _of_days(p0, d) / span if span > 0 else 0.0


def _of_cut(bz, flows, face, od, op):
    """Потоки до оферты: покупатель по оферте получает op x остаток номинала и НКД на дату оферты."""
    head = [x for x in flows if x[0] < od]
    remain = face - sum(x[2] for x in head)
    c_od = sum(x[1] for x in flows if x[0] == od)
    acc = 0.0 if c_od else _of_aci(bz, flows, od)
    return head + [(od, c_od + acc, remain * op)], remain


def _of_peers(me, rating, floating, dur):
    """Медиана доходности и число аналогов: тот же рейтинг +/-1 ступень (если мало, +/-2), дюрация близка к dur."""
    if not dur or not rating or rating not in RATING_SCALE:
        return None, 0
    ri = RATING_SCALE.index(rating)
    uni = _bc_universe()
    for width in (1, 2):
        pool = []
        for e in uni:
            rt = e.get("_rt")
            if e["cur"] != "RUB" or not (0 < e["yield"] < 40) or not e.get("dur") or not rt or rt["v"] not in RATING_SCALE:
                continue
            if bool((e["_ci"] or {}).get("floating")) != bool(floating):
                continue
            if abs(RATING_SCALE.index(rt["v"]) - ri) > width or (me and e["_isin"] == me["_isin"]):
                continue
            if me and me.get("_iss") and e["_iss"] and e["_iss"] == me["_iss"]:
                continue
            if abs(e["dur"] - dur) > max(0.4, dur * 0.4):
                continue
            pool.append((abs(e["dur"] - dur) + 0.5 * abs(RATING_SCALE.index(rt["v"]) - ri), e["yield"]))
        if len(pool) >= 3:
            pool.sort()
            return _of_med([y for _, y in pool[:12]]), min(len(pool), 12)
    return None, 0


def _of_pct(x):
    return ("%.1f" % x).replace(".", ",")


def _of_one(r, bz, today, flags):
    """Оферты одной позиции в ближайшие OF_DAYS дней -> список записей."""
    horizon = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=OF_DAYS)).strftime("%Y-%m-%d")
    face = r.get("nominal") or 1000.0
    offs = []
    for o in bz.get("offers") or []:
        t = (o.get("offertype") or "")
        od = _of_date(o.get("offerdate"))
        if not od or "оферт" not in t.lower() or "состоял" in t.lower() or not today < od <= horizon:
            continue
        offs.append((od, o, any(w in t.lower() for w in OF_CALL_WORDS)))
    if not offs:
        return []
    fl_ = bool(r.get("floating"))
    flows, _k, _e = bond_flows(bz, today, face, mode="maturity", floating=fl_)
    cps = sorted((c["coupondate"], c.get("value"), c.get("valueprc")) for c in bz["coupons"] if c.get("coupondate"))
    rt = (r.get("rating") or {})
    rv = rt.get("v")
    me = next((e for e in _bc_universe() if e["_isin"] == r.get("isin")), None)
    outlooks = " ".join((x.get("outlook") or "") for x in rt.get("all") or []).lower()
    risk_notes = []
    if flags.get("default"):
        risk_notes.append("по данным Мосбиржи, у выпуска был дефолт")
    elif flags.get("tech"):
        risk_notes.append("по данным Мосбиржи, у выпуска был технический дефолт")
    if "негатив" in outlooks:
        risk_notes.append("у рейтинга негативный прогноз")
    if "наблюден" in outlooks:
        risk_notes.append("рейтинг взят под наблюдение")
    price_pct = r.get("price_pct")
    out = []
    for od, o, is_call in sorted(offs, key=lambda x: x[0]):
        days = _of_days(today, od)
        ps, pe = _of_date(o.get("offerdatestart")), _of_date(o.get("offerdateend"))
        price = o.get("price") or 100.0
        status, days_left = "unknown", None
        if ps and pe:
            days_left = _of_days(today, pe)
            status = "open" if ps <= today <= pe else ("upcoming" if today < ps else "closed")
        urgent = status == "open" or (status == "upcoming" and days_left is not None and days_left <= 7) or \
            (status == "unknown" and days <= 7)
        rec = {"isin": r.get("isin"), "uid": r.get("uid"), "name": r["name"], "logo": r.get("logo"), "color": r.get("color"),
               "qty": r.get("qty"), "value_rub": r.get("value_rub"), "rating": rv, "floating": fl_,
               "kind": "call" if is_call else "put", "date": od, "days": days, "period_start": ps, "period_end": pe,
               "period_status": status, "period_days_left": days_left, "urgent": urgent, "offer_price": price,
               "price": price_pct, "ytm_now": r.get("ytm"), "to_offer_rub": (r.get("qty") or 0) * face * price / 100.0,
               "risk_notes": risk_notes, "yield_to_offer": None, "coupon_known": False, "new_rate": None,
               "hold_yield": None, "peer_median": None, "peers_n": 0, "threshold": None}
        if is_call:
            rec["hint"] = {"code": "call", "title": "Эмитент может погасить досрочно",
                           "text": "Эмитент вправе выкупить или погасить бумаги досрочно: доходность к этой дате может оказаться "
                                   "единственной, на которую стоит рассчитывать. Заявку подавать не нужно."}
            out.append(rec)
            continue
        after_cut = None
        try:
            if flows:
                cut, remain = _of_cut(bz, flows, face, od, price / 100.0)
                aci_now = _of_aci(bz, flows, today)
                if price_pct:
                    dirty = price_pct / 100.0 * face + aci_now
                    y = cf_ytm(dirty, cut, today)
                    rec["yield_to_offer"] = y * 100 if y is not None else None
                after = [x for x in flows if x[0] > od]
                if after:
                    after_cut = (after, remain, _of_aci(bz, flows, od))
        except Exception:  # noqa: BLE001
            after_cut = None
        nxt = next(((d, v, vp) for d, v, vp in cps if d > od), None)
        known = bool(nxt and (nxt[1] or nxt[2]))
        rec["coupon_known"] = known
        if known:
            nd = nxt[0]
            prev = max([d for d, _, _ in cps if d <= od] or [""])
            rec["new_rate"] = nxt[2] if nxt[2] else (nxt[1] / max(face, 1e-9) * 365.0 / max(_of_days(prev or today, nd), 1) * 100.0)
        mac = None
        if after_cut:
            after, remain, aci_od = after_cut
            y2 = cf_ytm(remain + aci_od, after, od)
            if y2 is not None:
                mac, _m, _c = cf_risk(after, od, y2)
                if known:
                    rec["hold_yield"] = y2 * 100
        med, n = _of_peers(me, rv, fl_, mac)
        if med is not None:
            rec["peer_median"], rec["peers_n"], rec["threshold"] = med, n, med - OF_MARGIN
        rec["hint"] = _of_hint(rec, risk_notes)
        out.append(rec)
    return out


def _of_hint(rec, risk_notes):
    price, op, med = rec["price"], rec["offer_price"], rec["peer_median"]
    hy, thr = rec["hold_yield"], rec["threshold"]
    how = ("Заявку на выкуп подаёт брокер; обычно он принимает поручения на несколько дней раньше окончания периода "
           "предъявления — уточните сроки у брокера.")
    if rec["period_status"] == "closed":
        return {"code": "closed", "title": "Период предъявления закончился",
                "text": "Принимать заявки на выкуп уже поздно: бумага останется у вас, условия после оферты определяет эмитент."}
    if price is not None and price > op + OF_PRICE_EPS:
        return {"code": "sell_market", "title": "Выгоднее продать на бирже",
                "text": "Рыночная цена (%s %%) выше цены выкупа (%s %%): на бирже получите больше, чем по оферте. "
                        "Предъявлять бумаги не нужно." % (_of_pct(price), _of_pct(op))}
    if risk_notes:
        low = (" Рыночная цена (%s %%) заметно ниже цены выкупа: рынок сомневается, что эмитент выкупит бумаги." % _of_pct(price)
               if price is not None and price < op - 10 else "")
        return {"code": "put", "title": "Рассмотрите предъявление",
                "text": "Есть признаки повышенного риска эмитента: %s. Предъявление к выкупу по %s %% вернёт деньги по номиналу "
                        "до того, как условия могут измениться.%s %s" % ("; ".join(risk_notes), _of_pct(op), low, how)}
    if rec["floating"] and not rec["coupon_known"]:
        return {"code": "hold", "title": "Можно держать",
                "text": "Купон плавающий и следует за ключевой ставкой, поэтому после оферты он обычно остаётся на уровне рынка. "
                        "Предъявлять нужно, только если вам нужны деньги."}
    if rec["coupon_known"] and hy is not None:
        if med is not None and hy < med - OF_MARGIN:
            return {"code": "put", "title": "Рассмотрите предъявление",
                    "text": "Новый купон (%s %% годовых) даёт доходность %s %% против %s %% у похожих выпусков (%d шт.): ниже "
                            "рынка больше чем на 0,5 п. п. Деньги по оферте (%s %%) можно вложить в бумагу с более высокой "
                            "доходностью. %s" % (_of_pct(rec["new_rate"] or 0), _of_pct(hy), _of_pct(med), rec["peers_n"],
                                                 _of_pct(op), how)}
        if med is None:
            return {"code": "hold", "title": "Можно держать",
                    "text": "Новый купон известен (%s %% годовых), доходность после оферты %s %%. Сравнить с рынком не с чем: "
                            "подходящих аналогов мало. Оцените ставку сами." % (_of_pct(rec["new_rate"] or 0), _of_pct(hy))}
        return {"code": "hold", "title": "Можно держать",
                "text": "Новый купон (%s %% годовых) даёт доходность %s %% против %s %% у похожих выпусков (%d шт.): на уровне "
                        "рынка. Предъявлять нет смысла, если деньги не нужны." % (_of_pct(rec["new_rate"] or 0), _of_pct(hy),
                                                                                   _of_pct(med), rec["peers_n"])}
    t = "Ставка нового купона ещё не объявлена: дождитесь объявления."
    if thr is not None:
        t += " Если ставка будет ниже ≈%s %% (медиана похожих выпусков %s %% минус 0,5 п. п.), предъявление выглядит разумнее." \
             % (_of_pct(thr), _of_pct(med))
    if rec["urgent"]:
        t += " Срок предъявления близко. " + how
    return {"code": "wait", "title": "Дождитесь объявления ставки", "text": t}


def offers_payload(cfg, acc):
    rep = build_bonds(cfg, acc)
    today = date.today().isoformat()
    rows = [r for r in rep["rows"] if r.get("isin") and r.get("qty")]

    def one(r):
        try:
            bz = moex_bondization(r["isin"])
            if not bz:
                return [], None
            if not any(_of_date(o.get("offerdate")) for o in bz.get("offers") or []):
                return [], None
            flags = _mon_flags(r["isin"])
            return _of_one(r, bz, today, flags), None
        except Exception as e:  # noqa: BLE001
            return [], "%s: %s" % (r.get("name"), str(e)[:100])
    res = pool_map(one, rows, workers=8)
    items = sorted([x for lst, _ in res for x in lst], key=lambda x: (x["date"], x["name"]))
    errs = [e for _, e in res if e]
    # оферты по данным брокера, которых нет в Мосбирже
    have = {x["isin"] for x in items}
    horizon = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=OF_DAYS)).strftime("%Y-%m-%d")
    for r in rows:
        c = r.get("call")
        if c and today < c <= horizon and r["isin"] not in have:
            items.append({"isin": r["isin"], "uid": r.get("uid"), "name": r["name"], "logo": r.get("logo"), "color": r.get("color"),
                          "qty": r.get("qty"), "value_rub": r.get("value_rub"), "rating": (r.get("rating") or {}).get("v"),
                          "floating": bool(r.get("floating")), "kind": "call", "date": c, "days": _of_days(today, c),
                          "period_start": None, "period_end": None, "period_status": "unknown", "period_days_left": None,
                          "urgent": False, "offer_price": None, "price": r.get("price_pct"), "ytm_now": r.get("ytm"),
                          "to_offer_rub": None, "risk_notes": [], "yield_to_offer": None, "coupon_known": False,
                          "new_rate": None, "hold_yield": None, "peer_median": None, "peers_n": 0, "threshold": None,
                          "hint": {"code": "call", "title": "Возможна досрочная дата",
                                   "text": "По данным брокера, у выпуска есть дата досрочного погашения или оферты. На Мосбирже "
                                           "условия не опубликованы — уточните в проспекте выпуска."}})
    items.sort(key=lambda x: (x["date"], x["name"]))
    puts = [x for x in items if x["kind"] == "put"]
    return {"account": acc, "today": today, "items": items, "count": len(items), "put_count": len(puts),
            "urgent_count": sum(1 for x in puts if x["urgent"]),
            "value_rub": sum(x["value_rub"] or 0 for x in items), "to_offer_rub": sum(x["to_offer_rub"] or 0 for x in puts),
            "bonds_count": len(rows), "errors": errs,
            "empty_text": "В ближайшие 12 месяцев по облигациям портфеля оферт нет: выпуски погашаются по графику.",
            "notes": ["Оферта — право держателя продать бумагу эмитенту по заранее известной цене. Если вы ничего не делаете, "
                      "бумага остаётся у вас, но купон после оферты эмитент может изменить.",
                      "Мосбиржа публикует оферты одним типом; право эмитента досрочно погасить (колл) в данных обычно не отдельно "
                      "помечено, поэтому такие даты могут быть не видны."]}


# ═══════════════════ конструктор лесенки облигаций ═══════════════════

LD_MAX_BONDS, LD_YTM_MAX, LD_NOTCH, LD_SPREAD_MAX = 20, 40.0, 0.5, 9.0      # максимум бумаг, предел доходности (аномалии), штраф за ступень рейтинга, п. п.


def _ld_int(v, lo, hi, d):
    try:
        x = int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return d
    return max(lo, min(hi, x))


def _ld_flag(v, d):
    return d if v in (None, "") else str(v).lower() in ("1", "true", "on", "yes")


def _ld_add(d, years):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=round(years * 365.25))).strftime("%Y-%m-%d")


def _ld_months(bz, today):
    """Месяцы (1-12), в которые бумага платит купон (по ближайшим 14 месяцам графика)."""
    lim = _ld_add(today, 14 / 12.0)
    return sorted({int(c["coupondate"][5:7]) for c in bz["coupons"] if c.get("coupondate") and today < c["coupondate"] <= lim})


_LD_IDS = {}


def _ld_bz(isin):
    """Потоки выпуска: по ISIN, а если пусто (так бывает у ОФЗ) — по коду бумаги на Мосбирже."""
    bz = _safe_call(moex_bondization, isin)
    sid = _LD_IDS.get(isin)
    if not bz and sid and sid != isin:
        bz = _safe_call(moex_bondization, sid)
    return bz


def _ld_cands(q_min_rating, floaters, amort, min_turn, today):
    """Вселенная -> кандидаты лесенки: (запись, рейтинг, дата окончания, вид окончания, годы до окончания)."""
    mi = RATING_SCALE.index(q_min_rating)
    out = []
    for e in _bc_universe():
        ci = e.get("_ci") or {}
        if e["cur"] != "RUB" or not (0 < e["yield"] <= LD_YTM_MAX) or not e.get("mat") or e["mat"] <= today:
            continue
        if ci.get("perpetual") or ci.get("subordinated") or e.get("sub") and "суборд" in str(e.get("sub")).lower():
            continue
        if bool(ci.get("floating")) and not floaters or bool(ci.get("amort")) and not amort:
            continue
        if (e.get("turn") or 0) < min_turn:
            continue
        if e.get("spread") is not None and e["spread"] > LD_SPREAD_MAX:      # слишком щедрая доходность — признак ловушки
            continue
        _LD_IDS[e["_isin"]] = e["id"]
        rt = e.get("_rt")
        rv = rt["v"] if rt else ("AAA" if e["kind"] == "ofz" else None)
        if rv not in RATING_SCALE or RATING_SCALE.index(rv) > mi:
            continue
        end, kind = e["mat"], "maturity"
        if e.get("offer") and today < e["offer"] < end:
            end, kind = e["offer"], "offer"
        out.append({"e": e, "rv": rv, "end": end, "kind": kind, "t": _of_days(today, end) / 365.25})
    return out


def ladder_payload(cfg, q=None):
    q = q or {}
    today = date.today().isoformat()
    total = _fnum(q.get("sum"), 1000.0, 1e10, 500000.0)
    years = _ld_int(q.get("years"), 1, 10, 5)
    rungs_n = _ld_int(q.get("rungs"), 1, 12, years) if q.get("rungs") not in (None, "") else years
    mr = (q.get("min_rating") or "A").upper()
    mr = mr if mr in RATING_SCALE else "A"
    floaters, amort = _ld_flag(q.get("floaters"), False), _ld_flag(q.get("amort"), True)
    monthly = _ld_flag(q.get("monthly"), False)
    cap = _fnum(q.get("max_issuer"), 1.0, 100.0, max(5, round(100.0 / rungs_n / 2)))
    min_turn = _fnum(q.get("min_turnover"), 0.0, 1e12, 1000000.0)
    par = {"sum": total, "years": years, "rungs": rungs_n, "min_rating": mr, "floaters": floaters, "amort": amort,
           "max_issuer": cap, "min_turnover": min_turn, "monthly": monthly}
    warnings, notes = [], []
    cands = _ld_cands(mr, floaters, amort, min_turn, today)
    step = years / float(rungs_n)
    per_rung = total / rungs_n
    k_cap = int(-(-100.0 // (rungs_n * cap)))              # сколько бумаг на ступень нужно, чтобы доля эмитента не превысила лимит
    k = max(1, k_cap)
    if rungs_n * k > LD_MAX_BONDS:
        k = max(1, LD_MAX_BONDS // rungs_n)
        warnings.append("Лимит доли эмитента %s %% при таком числе ступеней потребовал бы больше %d бумаг; взято по %d на ступень, "
                        "доля одного эмитента может быть выше лимита." % (("%g" % cap).replace(".", ","), LD_MAX_BONDS, k))
    k = min(k, 3 if rungs_n * 3 <= LD_MAX_BONDS else k)
    if per_rung / k < 3000 and k > 1:
        k = max(1, int(per_rung // 3000))
    if per_rung < 1500:
        warnings.append("Сумма слишком мала для %d ступеней: на ступень приходится около %d ₽, а облигация стоит около 1 000 ₽ "
                        "и больше. Уменьшите число ступеней." % (rungs_n, round(per_rung)))
    win = []
    for i in range(rungs_n):
        mid = step * (i + 1)
        win.append((max(0.25, mid - step / 2.0), mid + step / 2.0 if i < rungs_n - 1 else min(mid + step / 2.0, years + 0.5), mid))
    # кандидаты по окнам; для «ровного дохода» подгружаем график купонов у лучших в каждом окне
    pools = []
    for lo, hi, mid in win:
        pl = [c for c in cands if lo <= c["t"] <= hi]
        for c in pl:
            ri = RATING_SCALE.index(c["rv"])
            c["score"] = c["e"]["yield"] - LD_NOTCH * ri - 0.3 * abs(c["t"] - mid) / max(step / 2.0, 0.25)
        pl.sort(key=lambda c: -c["score"])
        pools.append(pl)
    bzs = {}
    if monthly:
        want = [c["e"]["_isin"] for pl in pools for c in pl[:10]]
        for isin, bz in zip(want, pool_map(lambda x: _ld_bz(x), want, workers=8)):
            bzs[isin] = bz
    chosen = [[] for _ in range(rungs_n)]
    used_iss, iss_share, covered = set(), defaultdict(float), set()

    def iss_key(c):
        e = c["e"]
        return e["_isin"] if e["kind"] == "ofz" or not e.get("_iss") else tuple(sorted(e["_iss"]))
    order = sorted(range(rungs_n), key=lambda i: len(pools[i]))        # сначала ступени с наименьшим выбором
    share = 100.0 / (rungs_n * k)
    for i in order:
        pl = pools[i]
        for strict in (True, False):
            while len(chosen[i]) < k:
                best = None
                for c in pl:
                    ik = iss_key(c)
                    if c in chosen[i] or any(iss_key(x) == ik for x in chosen[i]):
                        continue
                    if strict and ik in used_iss:
                        continue
                    if not strict and iss_share[ik] + share > cap + 1e-9:
                        continue
                    sc = c["score"]
                    if monthly and bzs.get(c["e"]["_isin"]):
                        c["months"] = _ld_months(bzs[c["e"]["_isin"]], today)
                        sc += 0.25 * len(set(c["months"]) - covered) + 0.0
                    if best is None or sc > best[0]:
                        best = (sc, c)
                if not best:
                    break
                c = best[1]
                chosen[i].append(c)
                used_iss.add(iss_key(c))
                iss_share[iss_key(c)] += share
                if monthly and c.get("months"):
                    covered |= set(c["months"])
            if len(chosen[i]) >= k:
                break
    # проверка дефолтных флагов у выбранных; замена на следующих в окне
    flat = [(i, c) for i in range(rungs_n) for c in chosen[i]]
    flg = dict(zip([c["e"]["_isin"] for _, c in flat], pool_map(lambda x: _mon_flags(x[1]["e"]["_isin"]), flat, workers=8)))
    for i in range(rungs_n):
        bad_ = [c for c in chosen[i] if (flg.get(c["e"]["_isin"]) or {}).get("default") or (flg.get(c["e"]["_isin"]) or {}).get("tech")]
        for c in bad_:
            chosen[i].remove(c)
            warnings.append("%s исключена: по данным Мосбиржи у выпуска был дефолт." % c["e"]["name"])
            have = {iss_key(x) for x in chosen[i]}
            for c2 in pools[i]:
                if c2 not in chosen[i] and c2 is not c and iss_key(c2) not in have and iss_key(c2) not in used_iss:
                    f2_ = _mon_flags(c2["e"]["_isin"])
                    if not (f2_.get("default") or f2_.get("tech")):
                        chosen[i].append(c2)
                        used_iss.add(iss_key(c2))
                        break
    sel = [c for i in range(rungs_n) for c in chosen[i]]
    for c in sel:
        if c["e"]["_isin"] not in bzs:
            bzs[c["e"]["_isin"]] = None
    need = [c["e"]["_isin"] for c in sel if bzs.get(c["e"]["_isin"]) is None]
    for isin, bz in zip(need, pool_map(lambda x: _ld_bz(x), need, workers=8)):
        bzs[isin] = bz
    # потоки и цена с НКД; бумаги без потоков отбрасываем, на их место ставим следующих кандидатов окна
    def prep(c):
        e = c["e"]
        bz = bzs.get(e["_isin"])
        if bz is None and e["_isin"] not in bzs:
            bz = bzs[e["_isin"]] = _ld_bz(e["_isin"])
        face = float(e.get("nominal") or 1000.0)
        try:
            fl, kind, end = bond_flows(bz, today, face, floating=bool((e["_ci"] or {}).get("floating"))) if bz else (None, None, None)
        except Exception:  # noqa: BLE001
            fl = None
        if not fl:
            return "%s пропущена: нет данных о графике выплат." % e["name"]
        aci = _of_aci(bz, fl, today)
        dirty = e["price"] / 100.0 * face + aci
        y = cf_ytm(dirty, fl, today)
        if y is not None and y * 100.0 > LD_YTM_MAX:
            return "%s пропущена: расчётная доходность выглядит аномальной." % e["name"]
        c.update(flows=fl, face=face, dirty=dirty, ytm=(y * 100.0 if y is not None else e["yield"]), end=end, kind=kind,
                 months=_ld_months(bz, today))
        return None
    for i in range(rungs_n):
        keep = []
        for c in chosen[i]:
            er = prep(c)
            if er:
                warnings.append(er)
            else:
                keep.append(c)
        if keep and len(keep) < k or (not keep and chosen[i]):
            have = {iss_key(x) for x in keep}
            tried = 0
            for c2 in pools[i]:
                if len(keep) >= k or tried >= 8:
                    break
                if c2 in chosen[i] or iss_key(c2) in have or iss_key(c2) in used_iss:
                    continue
                f2_ = _mon_flags(c2["e"]["_isin"])
                if f2_.get("default") or f2_.get("tech"):
                    continue
                tried += 1
                if not prep(c2):
                    keep.append(c2)
                    have.add(iss_key(c2))
                    used_iss.add(iss_key(c2))
        chosen[i] = keep
    # покупка: целые лоты, остаток — свободные деньги
    free = total
    for i in range(rungs_n):
        if not chosen[i]:
            continue
        tgt = per_rung / len(chosen[i])
        for c in chosen[i]:
            c["target"] = tgt
            c["lots"] = int(tgt // c["dirty"])
            free -= c["lots"] * c["dirty"]
    allc = [c for i in range(rungs_n) for c in chosen[i]]
    while allc:
        opts = [c for c in allc if c["dirty"] <= free + 1e-9 and c["target"] - c["lots"] * c["dirty"] + 0.5 * c["dirty"] > 0]
        if not opts:
            break
        c = max(opts, key=lambda c: c["target"] - c["lots"] * c["dirty"])
        c["lots"] += 1
        free -= c["dirty"]
    for i in range(rungs_n):
        if not chosen[i]:
            warnings.append("На ступень «около %s» не нашлось подходящих бумаг (рейтинг не ниже %s, оборот от %s ₽/день): "
                            "деньги ступени остались свободными. Смягчите рейтинг или ликвидность."
                            % (_ld_when(win[i][2]), mr, "{:,}".format(int(min_turn)).replace(",", " ")))
        elif len(chosen[i]) < k:
            warnings.append("На ступень «около %s» нашлось только %d из %d нужных бумаг." % (_ld_when(win[i][2]), len(chosen[i]), k))
    zero = [c for c in allc if c["lots"] <= 0]
    for c in zero:
        warnings.append("%s не куплена: цена лота выше выделенной суммы." % c["e"]["name"])
    allc = [c for c in allc if c["lots"] > 0]
    invested = sum(c["lots"] * c["dirty"] for c in allc)
    # денежный поток
    mon = defaultdict(lambda: [0.0, 0.0])
    agg = defaultdict(float)
    cp12 = 0.0
    lim12 = _ld_add(today, 1)
    for c in allc:
        for d, cp, pr in c["flows"]:
            mon[d[:7]][0] += cp * c["lots"]
            mon[d[:7]][1] += pr * c["lots"]
            agg[d] += (cp + pr) * c["lots"]
            if d <= lim12:
                cp12 += cp * c["lots"]
    cfm = []
    if mon:
        y0, m0 = int(today[:4]), int(today[5:7])
        last = max(mon)
        ym = "%04d-%02d" % (y0, m0)
        while ym <= last:
            v = mon.get(ym, [0.0, 0.0])
            cfm.append({"month": ym, "coupons": v[0], "principal": v[1]})
            yy, mm = int(ym[:4]), int(ym[5:7])
            ym = "%04d-%02d" % (yy + (mm == 12), mm % 12 + 1)
    yld = dur = None
    if invested > 0 and agg:
        fl_ = [(d, a, 0.0) for d, a in sorted(agg.items())]
        yv = cf_ytm(invested, fl_, today)
        if yv is not None:
            yld = yv * 100.0
            dur = cf_risk(fl_, today, yv)[0]
    rows = []
    for i in range(rungs_n):
        bl = []
        for c in chosen[i]:
            if c["lots"] <= 0:
                continue
            e = c["e"]
            bl.append({"isin": e["_isin"], "name": e["name"], "rating": c["rv"], "ytm": c["ytm"], "end_date": c["end"],
                       "end_kind": c["kind"], "price": e["price"], "price_dirty": c["dirty"], "lots": c["lots"],
                       "cost": c["lots"] * c["dirty"], "coupon_months": c["months"], "floating": bool((e["_ci"] or {}).get("floating")),
                       "amort": bool((e["_ci"] or {}).get("amort")), "share": c["lots"] * c["dirty"] / total * 100.0})
        rows.append({"target_date": _ld_add(today, win[i][2]), "target_years": win[i][2], "window": [_ld_add(today, win[i][0]), _ld_add(today, win[i][1])],
                     "bonds": bl, "cost": sum(b["cost"] for b in bl)})
    issuers = {iss_key(c) for c in allc}
    big = max([(iss_share_ := sum(c["lots"] * c["dirty"] for c in allc if iss_key(c) == ik) / total * 100.0) for ik in issuers] or [0])
    if big > cap + 0.5:
        warnings.append("Доля крупнейшего эмитента %s %% выше лимита %s %%: не хватило разных эмитентов." %
                        (("%.1f" % big).replace(".", ","), ("%g" % cap).replace(".", ",")))
    if any(c["kind"] == "offer" for c in allc):
        notes.append("Если у выпуска есть оферта, срок считается до неё: к этой дате вы предъявляете бумагу эмитенту по цене выкупа "
                     "(обычно 100 %). Заявку подаёт брокер.")
    notes.append("Бумаги гасятся по очереди: деньги возвращаются каждый год, и их можно вложить по новой ставке. Если ставки "
                 "вырастут, вы реинвестируете дороже, если упадут, длинные ступени уже зафиксировали высокую доходность.")
    if monthly:
        notes.append("Включён ровный ежемесячный доход: при выборе бумаг учитывается, в какие месяцы они платят купоны.")
    if any(b["floating"] for r_ in rows for b in r_["bonds"]):
        notes.append("Купоны флоатеров оценены по прогнозу ключевой ставки Банка России: фактические выплаты могут отличаться.")
    if any(b["rating"] == "AAA" and next((c for c in allc if c["e"]["_isin"] == b["isin"]), {}).get("e", {}).get("kind") == "ofz"
           for r_ in rows for b in r_["bonds"]):
        notes.append("ОФЗ рейтинга не имеют; для отбора приравнены к AAA как государственный долг.")
    return {"params": par, "today": today, "rungs": rows,
            "totals": {"invested": invested, "free": total - invested, "ytm": yld, "dur": dur, "bonds": len(allc),
                       "issuers": len(issuers), "rungs_filled": sum(1 for r_ in rows if r_["bonds"]),
                       "coupon_12m": cp12, "monthly_avg": cp12 / 12.0, "max_issuer": big,
                       "months_with_coupon": sum(1 for m in cfm[:12] if m["coupons"] > 0)},
            "cashflow_by_month": cfm, "notes": notes, "warnings": warnings}


def _ld_when(y):
    return ("%.1f" % y).replace(".", ",") + " г."


def _safe_call(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001
        return None
# ═══════════════════════════════ эмитенты: отчётность, скоринг ═══════════════════════════════
# ═══════════════════════════════ календарь событий, первичка против вторички, история спредов ═══════════════════════════════
# ═══════════════════════════════ список наблюдения, заметки, уведомления в Telegram ═══════════════════════════════
# Список наблюдения и дневник хранятся только в локальной базе. Telegram: личный бот пользователя; наружу (на серверы
# Telegram) уходят только тексты уведомлений. Токен бота — секрет (SECRET_KEYS), в журнал и в ответы API не попадает.

WATCH_KEY, NOTES_KEY, TG_SENT_KEY, TG_STATE_KEY = "watch_v1", "notes_v1", "tg_sent_v1", "tg_state_v1"
TG_DEFAULTS = {"tg_chat": "", "tg_on_mon": True, "tg_on_watch": True, "tg_pay_days": 0, "tg_digest": False, "tg_digest_time": "10:00"}
SECRET_KEYS.add("tg_token")
_watch_lock = threading.Lock()
_tg_lock = threading.Lock()


def _isin_ok(s):
    s = str(s or "").strip().upper()
    return s if re.fullmatch(r"[A-Z0-9]{6,16}", s) else ""


def _num(x):
    try:
        v = float(str(x).replace(",", ".").replace(" ", ""))
        return v if v == v and abs(v) < 1e9 else None
    except (TypeError, ValueError):
        return None


def watch_items():
    return [dict(x) for x in (store().get(WATCH_KEY) or []) if isinstance(x, dict) and x.get("isin")]


def watch_isins():
    """ISIN бумаг из списка наблюдения (для других модулей)."""
    return [x["isin"] for x in watch_items()]


def _scr_by_isin():
    out = {}
    try:
        for s in screener_rows():
            out[s.get("isin") or s["id"]] = s
    except Exception:  # noqa: BLE001
        pass
    return out


def _bond_name(isin, sec=None):
    s = (sec or {}).get(isin)
    if s and s.get("name"):
        return s["name"]
    try:
        ci = tcat_info(isin)
        if ci and ci.get("name"):
            return ci["name"]
    except Exception:  # noqa: BLE001
        pass
    return isin


def watch_post(cfg, body):
    act = str(body.get("action") or "")
    isin = _isin_ok(body.get("isin"))
    if not isin:
        raise ApiError("Укажите ISIN бумаги.", 400)
    with _watch_lock:
        items = watch_items()
        cur = next((x for x in items if x["isin"] == isin), None)
        if act == "toggle":
            act = "remove" if cur else "add"
        if act == "add":
            if not cur:
                cur = {"isin": isin, "added": date.today().isoformat()}
                items.append(cur)
        elif act == "remove":
            items = [x for x in items if x["isin"] != isin]
        elif act == "update":
            if not cur:
                raise ApiError("Бумаги нет в списке наблюдения.", 404)
        else:
            raise ApiError("Неизвестное действие.", 400)
        if act in ("add", "update") and cur is not None:
            for k in ("target_yield", "target_price"):
                if k in body:
                    v = _num(body[k]) if str(body[k]).strip() != "" else None
                    if v is not None and v <= 0:
                        v = None
                    if v is None:
                        cur.pop(k, None)
                    else:
                        cur[k] = round(v, 4)
            if "note" in body:
                n = str(body["note"] or "").strip()[:300]
                if n:
                    cur["note"] = n
                else:
                    cur.pop("note", None)
        store().put(WATCH_KEY, items)
    mem_clear_watch()
    return {"ok": True, "isins": [x["isin"] for x in items], "in_watch": any(x["isin"] == isin for x in items)}


def mem_clear_watch():
    with _mem_lock:
        for k in [k for k in _mem if isinstance(k, tuple) and k and k[0] == "monitor_for"]:
            _mem.pop(k, None)


def watch_search(cfg, acc, q, force):
    s = str((q or {}).get("q") or "").strip().lower()
    if len(s) < 2:
        return {"rows": []}
    have = set(watch_isins())
    out = []
    for r in screener_rows():
        isin = r.get("isin") or r["id"]
        if s in (r.get("name") or "").lower() or s in isin.lower() or s in (r.get("full") or "").lower() or s in (r.get("id") or "").lower():
            out.append({"isin": isin, "name": r.get("name"), "yield": r.get("yield"), "mat": r.get("mat"), "in_watch": isin in have,
                        "turn": r.get("turn") or 0})
    out.sort(key=lambda x: (not x["name"].lower().startswith(s) if x["name"] else True, -x["turn"]))
    return {"rows": out[:12]}


# ── дневник ──

def notes_all():
    return [dict(x) for x in (store().get(NOTES_KEY) or []) if isinstance(x, dict) and x.get("id")]


def notes_get(cfg, acc, q, force):
    isin = _isin_ok((q or {}).get("isin"))
    sec = _scr_by_isin()
    rows = [n for n in notes_all() if not isin or n["isin"] == isin]
    for n in rows:
        n["name"] = _bond_name(n["isin"], sec)
    rows.sort(key=lambda n: (n.get("date") or "", n["id"]), reverse=True)
    return {"rows": rows}


def notes_post(cfg, body):
    act = str(body.get("action") or "")
    with _watch_lock:
        items = notes_all()
        if act == "add":
            isin = _isin_ok(body.get("isin"))
            text = str(body.get("text") or "").strip()[:2000]
            if not isin or not text:
                raise ApiError("Укажите бумагу и текст заметки.", 400)
            n = {"id": "n%d%03d" % (int(time.time() * 1000), len(items) % 1000), "isin": isin,
                 "date": date.today().isoformat(), "text": text}
            d = _num(body.get("remind_days"))
            if d is not None and 0 < d <= 3650:
                n["remind_on"] = (date.today() + timedelta(days=int(d))).isoformat()
            items.append(n)
        elif act == "delete":
            items = [x for x in items if x["id"] != body.get("id")]
        elif act == "done":
            for x in items:
                if x["id"] == body.get("id"):
                    x.pop("remind_on", None)
        else:
            raise ApiError("Неизвестное действие.", 400)
        store().put(NOTES_KEY, items)
    mem_clear_watch()
    return {"ok": True}


# ── данные раздела «Наблюдение» и тревоги ──

def watch_payload(cfg, acc=None, q=None, force=False):
    items = watch_items()
    isins = [x["isin"] for x in items]
    sec = _scr_by_isin()
    mon = build_monitor_for(cfg, isins) if isins else {"alerts": [], "rows": [], "notes": []}
    mrow = {r["isin"]: r for r in mon.get("rows") or []}
    today = date.today().isoformat()
    rows, alerts = [], list(mon.get("alerts") or [])
    for it in items:
        isin = it["isin"]
        s = sec.get(isin)
        m = mrow.get(isin) or {}
        try:
            ci = tcat_info(isin) or {}
            rt = best_rating(isin, ci.get("name") or (s or {}).get("name") or "")
        except Exception:  # noqa: BLE001
            ci, rt = {}, None
        row = dict(it, name=_bond_name(isin, sec), in_market=bool(s), rating=rt["v"] if rt else None,
                   sector=ci.get("sector"), price=(s or {}).get("price"), yield_=(s or {}).get("yield"),
                   spread=(s or {}).get("spread"), dur=(s or {}).get("dur"), turn=(s or {}).get("turn"),
                   mat=(s or {}).get("mat") or ci.get("maturity"), offer=(s or {}).get("offer"), cur=(s or {}).get("cur"),
                   coupon=(s or {}).get("coupon"), chg5=m.get("chg5"), chg30=m.get("chg30"), spread_chg30=m.get("spread_chg30"),
                   spark=m.get("spark"), flags=m.get("flags") or [], rating_state=m.get("rating"))
        base = {"isin": isin, "isins": [isin], "name": row["name"], "bonds": [row["name"]]}
        ty, tp = it.get("target_yield"), it.get("target_price")
        if s and ty is not None and s.get("yield") is not None and s["yield"] >= ty:
            alerts.append(dict(base, id="gy|%s|%s" % (isin, ty), severity="medium", kind="goal", date=today,
                               message="Цель достигнута: доходность %s %% (цель — от %s %%)" % (_f2(s["yield"]), _f2(ty)), url=""))
        if s and tp is not None and s.get("price") is not None and s["price"] <= tp:
            alerts.append(dict(base, id="gp|%s|%s" % (isin, tp), severity="medium", kind="goal", date=today,
                               message="Цель достигнута: цена %s %% (цель — не выше %s %%)" % (_f2(s["price"]), _f2(tp)), url=""))
        if not s:
            row["flags"] = row["flags"] + ["нет данных Мосбиржи"]
        rows.append(row)
    for n in notes_all():
        if n.get("remind_on") and n["remind_on"] <= today:
            nm = _bond_name(n["isin"], sec)
            alerts.append({"isin": n["isin"], "isins": [n["isin"]], "name": nm, "bonds": [nm], "id": "rm|" + n["id"], "severity": "medium",
                           "kind": "reminder", "date": n["remind_on"], "note_id": n["id"], "url": "",
                           "message": "Напоминание из дневника от %s: %s" % (n["date"][8:] + "." + n["date"][5:7], n["text"][:160])})
    alerts.sort(key=lambda a: (_SEV[a["severity"]], _neg(a["date"])))
    for a in alerts:
        for r in rows:
            if r["isin"] in (a.get("isins") or []):
                r["n_" + a["severity"]] = r.get("n_" + a["severity"], 0) + 1
    return {"items": rows, "alerts": alerts, "notes": mon.get("notes") or [],
            "summary": {s_: sum(1 for a in alerts if a["severity"] == s_) for s_ in _SEV}, "updated": time.time()}


def _f2(x):
    return ("%.2f" % x).replace(".", ",")


def watch_isins_get(cfg, acc, q, force):
    return {"isins": watch_isins()}


API_GET["/api/watch"] = watch_payload
API_GET["/api/watch/isins"] = watch_isins_get
API_GET["/api/watch/search"] = watch_search
API_GET["/api/notes"] = notes_get
API_POST["/api/watch"] = watch_post
API_POST["/api/notes"] = notes_post


# ═══════════════════════════ Telegram ═══════════════════════════

def _tg_base():
    return (os.environ.get("TINVEST_TG_API") or "https://api.telegram.org").rstrip("/")


def _tg_scrub(msg, token):
    msg = str(msg)
    if token:
        msg = msg.replace(token, "***")
    return re.sub(r"bot\d+:[A-Za-z0-9_\-]+", "bot***", msg)[:200]


def tg_call(token, method, params=None, timeout=15):
    """Вызов Bot API. Любые ошибки превращаются в ApiError без токена в тексте."""
    if not token:
        raise ApiError("Токен бота не задан.", 400)
    url = "%s/bot%s/%s" % (_tg_base(), token, method)
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    ctx = None
    if url.startswith("https://"):
        import ssl
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            j = {}
        if e.code in (401, 404):
            raise ApiError("Telegram не принял токен бота. Проверьте, что он скопирован целиком.", 400)
        raise ApiError("Telegram ответил ошибкой: %s" % _tg_scrub(j.get("description") or e.code, token), 502)
    except Exception as e:  # noqa: BLE001
        raise ApiError("Не удалось связаться с Telegram (%s). Если api.telegram.org недоступен из вашей сети, понадобится VPN или прокси."
                       % _tg_scrub(getattr(e, "reason", e), token), 502)
    if not j.get("ok"):
        raise ApiError("Telegram: %s" % _tg_scrub(j.get("description") or "ошибка", token), 502)
    return j.get("result")


def _tg_esc(s):
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tg_send(cfg, text):
    chat = str(cfg.get("tg_chat") or "").strip()
    if not chat:
        raise ApiError("Не указан chat id.", 400)
    return tg_call(cfg.get("tg_token"), "sendMessage", {"chat_id": chat, "text": text[:4000], "parse_mode": "HTML",
                                                         "disable_web_page_preview": True})


def tg_public(cfg):
    return {k: cfg.get(k, d) for k, d in TG_DEFAULTS.items()}


def tg_save(cfg, body):
    cfg = load_config()
    if body.get("token"):
        tok = "".join(str(body["token"]).split())
        if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_\-]{20,}", tok):
            raise ApiError("Токен бота выглядит неверно: он должен быть вида 123456789:AAH… (его выдаёт @BotFather).", 400)
        cfg["tg_token"] = tok
    if body.get("clear_token"):
        cfg["tg_token"] = ""
    if "chat" in body:
        c = str(body["chat"]).strip()
        if c and not re.fullmatch(r"-?\d{1,20}|@[A-Za-z0-9_]{3,64}", c):
            raise ApiError("Chat id — это число (например 123456789). Нажмите «Найти мой chat id».", 400)
        cfg["tg_chat"] = c
    for k in ("tg_on_mon", "tg_on_watch", "tg_digest"):
        if k in body:
            cfg[k] = bool(body[k])
    if "tg_pay_days" in body:
        d = _num(body["tg_pay_days"])
        cfg["tg_pay_days"] = max(0, min(60, int(d))) if d is not None else 0
    if "tg_digest_time" in body:
        t = str(body["tg_digest_time"]).strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
            raise ApiError("Время сводки — в формате ЧЧ:ММ, например 10:00.", 400)
        cfg["tg_digest_time"] = t
    save_config(cfg)
    return {"ok": True, "token_set": bool(cfg.get("tg_token")), "settings": tg_public(cfg)}


def tg_find_chat(cfg, body):
    cfg = load_config()
    ups = tg_call(cfg.get("tg_token"), "getUpdates", {"limit": 50, "timeout": 0}) or []
    best = None
    for u in ups:
        m = u.get("message") or u.get("edited_message") or u.get("channel_post")
        if m and m.get("chat") and m["chat"].get("id") is not None:
            if m["chat"].get("type", "private") == "private" or best is None:
                best = m["chat"]
    if not best:
        raise ApiError("Сообщений боту пока нет. Откройте своего бота в Telegram, нажмите «Запустить» (/start) или напишите ему любое сообщение и повторите.", 404)
    name = " ".join(x for x in (best.get("first_name"), best.get("last_name")) if x) or best.get("title") or best.get("username") or ""
    cfg["tg_chat"] = str(best["id"])
    save_config(cfg)
    return {"ok": True, "chat": str(best["id"]), "name": name}


def tg_test(cfg, body):
    cfg = load_config()
    tg_send(cfg, "✅ <b>T-Invest Analytics</b>: тестовое сообщение. Уведомления подключены.")
    return {"ok": True}


def tg_run_now(cfg, body):
    n = tg_tick(force_digest=bool(body.get("digest")))
    return {"ok": True, "sent": n}


API_POST["/api/tg/save"] = tg_save
API_POST["/api/tg/find_chat"] = tg_find_chat
API_POST["/api/tg/test"] = tg_test
API_POST["/api/tg/run"] = tg_run_now


_TG_KIND = {"price": "📉", "spread": "📈", "offer": "🔔", "default": "⛔", "rating": "🏷", "watch": "👁", "outlook": "👁",
            "halt": "⏸", "liquidity": "💧", "goal": "🎯", "reminder": "📝"}
_TG_COOL = {"price": 7 * DAY, "spread": 7 * DAY}      # повтор не раньше, чем через неделю; остальные тревоги — один раз


def _tg_key(a):
    k = a["id"]
    if a.get("kind") in _TG_COOL:
        k = "%s|%s|%s" % (a["kind"], a.get("isin"), "")
    return k


def _tg_alert_line(a):
    nm = a.get("name") or ""
    return "%s <b>%s</b>: %s" % (_TG_KIND.get(a.get("kind"), "•"), _tg_esc(nm), _tg_esc(a.get("message")))


def _tg_dispatch(cfg, title, alerts, sent, now):
    """Отправляет ещё не отправленные тревоги одним сообщением (до 10 штук). Возвращает число тревог."""
    fresh = []
    for a in alerts:
        k = _tg_key(a)
        last = sent.get(k)
        if last is not None and now - last < _TG_COOL.get(a.get("kind"), 400 * DAY):
            continue
        fresh.append((k, a))
    if not fresh:
        return 0
    sent_n = 0
    for i in range(0, min(len(fresh), 30), 10):          # до трёх сообщений за проверку; остальное уйдёт в следующий раз
        chunk = fresh[i:i + 10]
        tg_send(cfg, "<b>%s</b>\n\n%s" % (_tg_esc(title), "\n\n".join(_tg_alert_line(a) for k, a in chunk)))
        for k, a in chunk:
            sent[k] = now
        sent_n += len(chunk)
    return sent_n


def _tg_payments(cfg, days):
    b = build_bonds(cfg, "all")
    end = (date.today() + timedelta(days=days)).isoformat()
    today = date.today().isoformat()
    ev = [(p["date"], p.get("kind"), p.get("name"), p.get("amount")) for p in (b.get("payments") or []) if today <= p["date"] <= end]
    ev += [(r["call"], "offer", r.get("name"), None) for r in (b.get("rows") or []) if r.get("call") and today <= r["call"] <= end]
    return sorted(ev, key=lambda x: (x[0], str(x[2])))


_TG_EV = {"coupon": "купон", "dividend": "дивиденд", "redemption": "погашение", "offer": "оферта"}


def _tg_ev_line(e):
    amt = " · %s ₽" % ("{:,.0f}".format(e[3]).replace(",", " ")) if e[3] else ""
    return "%s · %s · %s%s" % (e[0][8:] + "." + e[0][5:7], _TG_EV.get(e[1], e[1] or ""), _tg_esc(e[2]), amt)


def tg_digest_text(cfg):
    parts = ["<b>Сводка T-Invest Analytics · %s</b>" % date.today().strftime("%d.%m.%Y")]
    if cfg.get("token"):
        try:
            s = build_summary(cfg, "all", "all")
            p = s.get("portfolio") or {}
            if p.get("total") is not None:
                d = p.get("daily")
                parts.append("Портфель: %s ₽%s" % ("{:,.0f}".format(p["total"]).replace(",", " "),
                             (" (за день %s%s ₽)" % ("+" if d >= 0 else "−", "{:,.0f}".format(abs(d)).replace(",", " "))) if d is not None else ""))
        except Exception:  # noqa: BLE001
            pass
        try:
            ev = _tg_payments(cfg, 7)
            if ev:
                parts.append("Ближайшие 7 дней:\n" + "\n".join(_tg_ev_line(e) for e in ev[:8]) + ("\n…и ещё %d" % (len(ev) - 8) if len(ev) > 8 else ""))
            else:
                parts.append("Ближайшие 7 дней: выплат нет.")
        except Exception:  # noqa: BLE001
            pass
        try:
            m = build_monitor(cfg, "all")
            parts.append("Мониторинг портфеля: высоких тревог — %d, средних — %d." % (m["summary"]["high"], m["summary"]["medium"]))
        except Exception:  # noqa: BLE001
            pass
    try:
        w = watch_payload(cfg)
        if w["items"]:
            ln = []
            for r in w["items"][:8]:
                ln.append("%s: %s" % (_tg_esc(r["name"]), ("доходность %s %%" % _f2(r["yield_"])) if r.get("yield_") is not None else "нет данных"))
            parts.append("Наблюдение (%d, тревог: %d):\n%s" % (len(w["items"]), len(w["alerts"]), "\n".join(ln)))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)


def tg_tick(force_digest=False):
    """Одна проверка: новые тревоги, выплаты, ежедневная сводка. Возвращает число отправленных пунктов."""
    if not _tg_lock.acquire(False):
        return 0
    try:
        cfg = load_config()
        if not cfg.get("tg_token") or not str(cfg.get("tg_chat") or "").strip():
            return 0
        st = store()
        now = time.time()
        sent = {k: v for k, v in (st.get(TG_SENT_KEY) or {}).items() if now - v < 400 * DAY}
        n = 0
        try:
            if cfg.get("tg_on_mon", True) and cfg.get("token"):
                al = [a for a in build_monitor(cfg, "all")["alerts"] if a["severity"] == "high"]
                n += _tg_dispatch(cfg, "Тревоги по портфелю", al, sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:
            if cfg.get("tg_on_watch", True) and (watch_isins() or notes_all()):
                al = [a for a in watch_payload(cfg)["alerts"] if a["severity"] != "info"]
                n += _tg_dispatch(cfg, "Наблюдение и цели", al, sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:
            days = int(cfg.get("tg_pay_days") or 0)
            if days > 0 and cfg.get("token"):
                ev = [e for e in _tg_payments(cfg, days)]
                fresh = []
                for e in ev:
                    k = "pay|%s|%s|%s" % (e[0], e[1], e[2])
                    if k not in sent:
                        fresh.append((k, e))
                if fresh:
                    tg_send(cfg, "<b>Ближайшие выплаты (%d дн.)</b>\n\n%s" % (days, "\n".join(_tg_ev_line(e) for k, e in fresh[:15])))
                    for k, e in fresh:
                        sent[k] = now
                    n += len(fresh)
        except Exception:  # noqa: BLE001
            pass
        try:
            state = st.get(TG_STATE_KEY) or {}
            hh = str(cfg.get("tg_digest_time") or "10:00")
            nowl = datetime.now()
            due = force_digest or (cfg.get("tg_digest") and state.get("digest") != date.today().isoformat()
                                   and nowl.strftime("%H:%M") >= hh)
            if due:
                tg_send(cfg, tg_digest_text(cfg))
                if not force_digest:
                    state["digest"] = date.today().isoformat()
                    st.put(TG_STATE_KEY, state)
                n += 1
        except Exception:  # noqa: BLE001
            pass
        st.put(TG_SENT_KEY, sent)
        return n
    except Exception:  # noqa: BLE001
        return 0            # сеть/Telegram недоступны — попробуем в следующий раз; детали (с токеном) не пишем
    finally:
        _tg_lock.release()


def _tg_loop():
    time.sleep(90)
    while True:
        try:
            tg_tick()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(int(os.environ.get("TINVEST_TG_PERIOD") or 720))


def tg_start():
    threading.Thread(target=_tg_loop, daemon=True, name="tg-notify").start()


STARTUP_HOOKS.append(tg_start)
# ═══════════════════════════════ налоги по лотам: ЛДВ, ИИС, перенос убытков, подсказки ═══════════════════════════════
# ═══════════════════════════════ зашифрованная резервная копия и экспорт ═══════════════════════════════
# ═══════════════════════════════ HTTP-сервер ═══════════════════════════════

_ping = [0.0]


class Handler(BaseHTTPRequestHandler):
    server_version = "TInvestAnalytics/3.0"

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str).encode()
        elif isinstance(body, str):
            body = body.encode()
        gz = len(body) > 2048 and ctype.startswith(("application/json", "text/")) and \
            "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz:
            body = gzip.compress(body, 5)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=604800" if ctype == "image/png" else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def ok_host(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % port, "localhost:%d" % port)

    def guard(self, fn):
        try:
            fn()
        except ApiError as e:
            self.send(e.status if 400 <= e.status < 600 else 502, {"error": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.send(500, {"error": "%s: %s" % (type(e).__name__, e)})

    def _reply(self, res):
        if isinstance(res, tuple):
            code, body = res[0], res[1]
            ctype = res[2] if len(res) > 2 and res[2] else "application/json; charset=utf-8"
            return self.send(code, body, ctype, res[3] if len(res) > 3 else None)
        return self.send(200, res)

    def do_GET(self):
        if not self.ok_host():
            return self.send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        def run():
            if u.path == "/":
                return self.send(200, PAGE, "text/html; charset=utf-8")
            if u.path.startswith("/logo/"):
                data = logo_bytes(unquote(u.path[6:]))
                return self.send(200, data, "image/png") if data else self.send(404, {"error": "no logo"})
            if u.path == "/api/ping":
                _ping[0] = time.time()
                return self.send(200, {"ok": True})
            cfg = load_config()
            f = q.get("force") == "1"
            acc = q.get("account", "all") or "all"
            if u.path == "/api/config":
                pub = {k: v for k, v in cfg.items() if k not in SECRET_KEYS}
                pub["secret_set"] = {k: bool(cfg.get(k)) for k in SECRET_KEYS if k != "token"}
                pub.update(token_set=bool(cfg["token"]), token_hint=("…" + cfg["token"][-4:]) if cfg["token"] else "",
                           imports=imports_list(), data_dir=APP_DIR, version=APP_VERSION)
                return self.send(200, pub)
            if u.path == "/api/summary":
                return self.send(200, build_summary(cfg, acc, q.get("period", "all"), f))
            if u.path == "/api/bonds":
                return self.send(200, build_bonds(cfg, acc, f))
            if u.path == "/api/history":
                return self.send(200, build_history_for(cfg, acc, f))
            if u.path == "/api/operations.csv":
                data = build_summary(cfg, acc, q.get("period", "all"))
                return self.send(200, operations_csv(data), "text/csv; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="operations.csv"'})
            if u.path == "/api/screener":
                return self.send(200, screener_payload())
            if u.path == "/api/bond":
                return self.send(200, bond_card(q.get("isin", "")))
            if u.path == "/api/primary":
                return self.send(200, primary_payload())
            if u.path == "/api/ratings":
                return self.send(200, ratings_status())
            if u.path == "/api/keyrate":
                return self.send(200, keyrate_brief() or {"source": "none", "name": "", "yearly": []})
            if u.path == "/api/risk":
                return self.send(200, build_risk(cfg, acc, q))
            if u.path == "/api/signals":
                return self.send(200, signals_payload(cfg, acc, q))
            if u.path == "/api/monitor":
                return self.send(200, build_monitor(cfg, acc))
            if u.path == "/api/bench":
                return self.send(200, bench_payload(cfg, acc, q))
            if u.path == "/api/calc":
                return self.send(200, calc_params(cfg, acc))
            if u.path == "/api/offers":
                return self.send(200, offers_payload(cfg, acc))
            if u.path == "/api/ladder":
                return self.send(200, ladder_payload(cfg, q))
            if u.path == "/api/rates":
                return self.send(200, rates_payload(q.get("days", "365")))
            if u.path == "/api/backup":
                return self.send(200, make_backup(), "application/zip",
                                 {"Content-Disposition": 'attachment; filename="tinvest_backup_%s.zip"' % date.today().isoformat()})
            if u.path == "/api/import/template.csv":
                return self.send(200, TEMPLATE_CSV.encode("utf-8-sig"), "text/csv; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="import_template.csv"'})
            fn = API_GET.get(u.path)
            if fn:
                return self._reply(fn(cfg, acc, q, f))
            self.send(404, {"error": "not found"})
        self.guard(run)

    def do_POST(self):
        if not self.ok_host() or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self.send(403, {"error": "forbidden"})
        path = urlparse(self.path).path

        def run():
            n = int(self.headers.get("Content-Length") or 0)
            if n > 80 * 1024 * 1024:
                raise ApiError("Файл слишком большой (больше 60 МБ).", 400)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            cfg = load_config()
            if path == "/api/config":
                if body.get("token"):
                    cfg["token"] = "".join(str(body["token"]).split())
                if body.get("clear_token"):
                    cfg["token"] = ""
                for k in ("sandbox", "verify_ssl"):
                    if k in body:
                        cfg[k] = bool(body[k])
                if "ca_file" in body:
                    cfg["ca_file"] = str(body["ca_file"]).strip()
                if body.get("theme") in ("auto", "dark", "light"):
                    cfg["theme"] = body["theme"]
                if isinstance(body.get("targets"), dict):
                    tg = {}
                    for k, v in body["targets"].items():
                        try:
                            x = float(v)
                        except (TypeError, ValueError):
                            continue
                        if 0 < x <= 100:
                            tg[str(k)[:24]] = round(x, 2)
                    cfg["targets"] = tg
                if body.get("keyrate_mode") in KR_MODES:
                    cfg["keyrate_mode"] = body["keyrate_mode"]
                if "notify_days" in body:
                    try:
                        cfg["notify_days"] = max(0, min(60, int(body["notify_days"])))
                    except (TypeError, ValueError):
                        pass
                for k, lo, hi in (("mon_drop5", 0.1, 50), ("mon_drop30", 0.1, 90), ("mon_spread30", 0.1, 50),
                                  ("mon_sell_days", 0.5, 365), ("mon_offer_days", 1, 365)):
                    if k in body:
                        try:
                            cfg[k] = max(lo, min(hi, float(body[k])))
                        except (TypeError, ValueError):
                            pass
                for k in ("hosts_prod", "hosts_sandbox"):
                    if isinstance(body.get(k), list):
                        hosts = [str(h).strip() for h in body[k] if str(h).strip()]
                        if hosts:
                            cfg[k] = hosts
                if cfg["ca_file"] and not os.path.isfile(cfg["ca_file"]):
                    raise ApiError("Файл сертификата не найден: " + cfg["ca_file"], 400)
                save_config(cfg)
                mem_clear()
                return self.send(200, {"ok": True})
            if path == "/api/ratings/refresh":
                return self.send(200, {"started": ratings_start(force=True), **ratings_status()})
            client = TInvest(cfg)
            if path == "/api/test":
                return self.send(200, {"ok": True, "accounts": len(client.accounts())})
            if path == "/api/cache/clear":
                store().wipe_cache()
                shutil.rmtree(LOGO_DIR, ignore_errors=True)
                mem_clear()
                return self.send(200, {"ok": True})
            if path == "/api/import/preview":
                raw = base64.b64decode(body.get("data") or "")
                return self.send(200, import_preview(body.get("filename") or "", raw))
            if path == "/api/import/parse":
                raw = base64.b64decode(body.get("data") or "")
                ops, skipped = import_ops(body.get("filename") or "", raw, int(body.get("table") or 0),
                                          int(body.get("header_row") or 0), body.get("mapping") or {})
                kinds = defaultdict(int)
                for o in ops:
                    kinds[classify(o["type"])] += 1
                sample = [[o["date"][:10], op_type(o), o.get("name") or "", op_qty(o), qf(o["payment"]), cur_of(o["payment"])]
                          for o in ops[:15]]
                return self.send(200, {"count": len(ops), "skipped": skipped, "kinds": kinds, "sample": sample,
                                       "from": ops[0]["date"][:10] if ops else None, "to": ops[-1]["date"][:10] if ops else None})
            if path == "/api/import/commit":
                raw = base64.b64decode(body.get("data") or "")
                ops, skipped = import_ops(body.get("filename") or "", raw, int(body.get("table") or 0),
                                          int(body.get("header_row") or 0), body.get("mapping") or {})
                if not ops:
                    raise ApiError("В файле не нашлось операций с выбранными колонками.", 400)
                ops, ids = finalize_import(client, ops)
                acc_id = body.get("target") if str(body.get("target") or "").startswith("imp-") else "imp-" + uuid.uuid4().hex[:10]
                lst = imports_list()
                ex = next((x for x in lst if x["id"] == acc_id), None)
                if ex is None:
                    ex = {"id": acc_id, "name": (body.get("name") or "").strip() or "Импорт " + date.today().strftime("%d.%m.%Y"),
                          "broker": (body.get("broker") or "").strip(), "created": utc_now_str(), "files": []}
                    lst.append(ex)
                ex["files"].append({"name": body.get("filename") or "", "count": len(ops), "at": utc_now_str()})
                store().ops_put(acc_id, ops)
                store().put("imports", lst)
                mem_clear()
                found = sum(1 for v in ids.values() if v.get("uid"))
                return self.send(200, {"ok": True, "id": acc_id, "count": len(ops), "skipped": skipped,
                                       "resolved": found, "idents": len(ids)})
            if path == "/api/import/delete":
                lst = [x for x in imports_list() if x["id"] != body.get("id")]
                store().put("imports", lst)
                store().ops_clear(body.get("id") or "")
                mem_clear()
                return self.send(200, {"ok": True})
            if path in ("/api/sandbox/open", "/api/sandbox/payin"):
                if not cfg["sandbox"]:
                    raise ApiError("Доступно только в режиме песочницы.", 400)
                mem_clear()
                if path.endswith("open"):
                    return self.send(200, client.call("SandboxService", "OpenSandboxAccount", {"name": "Analytics"}))
                amount = Decimal(str(body.get("amount") or 0))
                if amount <= 0:
                    raise ApiError("Сумма должна быть больше нуля.", 400)
                acc = body.get("accountId")
                if not acc or acc == "all" or str(acc).startswith("imp-"):
                    raise ApiError("Выберите счёт песочницы в списке слева.", 400)
                return self.send(200, client.call("SandboxService", "SandboxPayIn", {"accountId": acc, "amount": to_money(amount)}))
            fn = API_POST.get(path)
            if fn:
                return self._reply(fn(cfg, body))
            self.send(404, {"error": "not found"})
        self.guard(run)


# ═══════════════════════════════ окно приложения ═══════════════════════════════

def find_app_browser():
    sysname = platform.system()
    cands = []
    if sysname == "Windows":
        for r in filter(None, [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]):
            cands += [os.path.join(r, "Google", "Chrome", "Application", "chrome.exe"),
                      os.path.join(r, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(r, "Yandex", "YandexBrowser", "Application", "browser.exe"),
                      os.path.join(r, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")]
    elif sysname == "Darwin":
        for app, exe in (("Google Chrome", "Google Chrome"), ("Microsoft Edge", "Microsoft Edge"),
                         ("Yandex", "Yandex"), ("Brave Browser", "Brave Browser"), ("Chromium", "Chromium")):
            for base in ("/Applications", os.path.expanduser("~/Applications")):
                cands.append(os.path.join(base, app + ".app", "Contents", "MacOS", exe))
    else:
        for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
                  "yandex-browser", "brave-browser"):
            p = shutil.which(n)
            if p:
                cands.append(p)
    return next((c for c in cands if c and os.path.isfile(c)), None)


def open_window(url):
    exe = find_app_browser()
    if exe:
        try:
            return subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + os.path.join(APP_DIR, "window"),
                                     "--window-size=1480,940", "--no-first-run", "--no-default-browser-check",
                                     "--disable-features=Translate"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
    webbrowser.open(url)
    return None


def main():
    cfg = load_config()
    port = int(os.environ.get("TINVEST_PORT") or cfg["port"])
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    store()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("%s → %s   (Ctrl+C — выход)\nДанные: %s" % (APP_NAME, url, APP_DIR))
    if "--no-window" not in sys.argv:
        proc = open_window(url)
        if proc:
            def watch():
                t0 = time.time()
                proc.wait()
                if time.time() - t0 > 8:
                    return srv.shutdown()
                while True:
                    time.sleep(30)
                    if _ping[0] and time.time() - _ping[0] > 200:
                        return srv.shutdown()
            threading.Thread(target=watch, daemon=True).start()
    try:
        try:
            ratings_start()
        except Exception:  # noqa: BLE001
            pass
        try:
            warmup_start()
        except Exception:  # noqa: BLE001
            pass
        for hook in STARTUP_HOOKS:
            try:
                hook()
            except Exception:  # noqa: BLE001
                pass
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


# ═══════════════════════════════ интерфейс ═══════════════════════════════

PAGE = r'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>T-Invest Analytics</title>
<script>(function(){try{var t=localStorage.getItem('ta_theme')||'auto';document.documentElement.dataset.theme=t==='auto'?(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'):t}catch(e){document.documentElement.dataset.theme='dark'}})()</script>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%23ffdd2d'/%3E%3Cpath d='M8 21l5-6 4 3 7-8' stroke='%23111' stroke-width='3' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<style>
:root{
  --bg:#0b0c0f;--side:#0f1115;--card:#16181d;--card2:#1c1f26;--line:#252932;--line2:#2f3440;
  --tx:#eef0f4;--tx2:#a8aebb;--mu:#6f7686;--ac:#ffdd2d;--ac2:#ffe866;--pos:#3ecf8e;--neg:#ff6b6b;
  --s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;
  --r:14px;color-scheme:dark}
*{box-sizing:border-box;margin:0}
html,body{height:100%}
body{background:var(--bg);color:var(--tx);font:14px/1.45 Inter,"SF Pro Text",-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;
  -webkit-font-smoothing:antialiased;display:flex;overflow:hidden}
.num,td,.v{font-variant-numeric:tabular-nums}
button,input,select,textarea{font:inherit;color:inherit}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:#2a2e38;border-radius:8px;border:2px solid var(--bg)}
::-webkit-scrollbar-track{background:transparent}

aside{width:252px;flex:none;background:var(--side);border-right:1px solid var(--line);display:flex;flex-direction:column;padding:16px 10px 12px;overflow:auto}
.logo{display:flex;gap:10px;align-items:center;padding:2px 8px 16px;font-weight:700;font-size:15px;letter-spacing:-.01em}
.logo i{width:30px;height:30px;border-radius:9px;background:var(--ac);display:grid;place-items:center;flex:none}
.logo small{display:block;font-weight:500;color:var(--mu);font-size:11px}
.nav{display:flex;flex-direction:column;gap:1px}
.nav button{all:unset;cursor:pointer;display:flex;gap:11px;align-items:center;padding:7px 11px;border-radius:9px;color:var(--tx2);font-weight:500;font-size:13.5px;transition:.15s}
.nav button:hover{background:#171a20;color:var(--tx)}
.nav button.on{background:#1d2027;color:var(--tx);box-shadow:inset 3px 0 0 var(--ac)}
.nav svg{width:17px;height:17px;flex:none;opacity:.85}
.nav .sep{height:1px;background:var(--line);margin:8px 6px}
.accs{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}
.acc-h{display:flex;align-items:center;justify-content:space-between;padding:0 8px 8px;color:var(--mu);font-size:11.5px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.msw{display:flex;align-items:center;gap:6px;cursor:pointer;text-transform:none;letter-spacing:0;font-weight:500;font-size:11.5px;color:var(--tx2)}
.msw input{display:none}.msw i{width:26px;height:15px;border-radius:9px;background:#2a2e38;position:relative;transition:.2s}
.msw i:after{content:"";position:absolute;left:2px;top:2px;width:11px;height:11px;border-radius:50%;background:#fff;transition:.2s}
.msw input:checked+i{background:var(--ac)}.msw input:checked+i:after{left:13px;background:#121212}
.acl{display:flex;flex-direction:column;gap:2px}
.acl button{all:unset;cursor:pointer;display:grid;grid-template-columns:1fr auto;gap:2px 8px;padding:7px 10px;border-radius:9px;transition:.15s}
.acl button:hover{background:#171a20}
.acl button.on{background:#1d2027;box-shadow:inset 3px 0 0 var(--ac)}
.acl b{font-weight:550;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.acl span{font-size:12px;color:var(--tx2);text-align:right}
.acl small{grid-column:1/3;font-size:11px;color:var(--mu);display:flex;gap:6px}
.acl small em{font-style:normal;background:#ffffff0d;padding:0 6px;border-radius:5px}
.acl .all b{font-weight:650}
.side-foot{margin-top:auto;padding:12px 8px 0;display:flex;align-items:center;justify-content:space-between}
.ver{all:unset;cursor:pointer;font-size:11.5px;color:var(--mu);padding:2px 8px;border-radius:6px;border:1px solid var(--line)}.ver:hover{color:var(--tx);border-color:var(--line2)}
.cl{display:grid;gap:18px}.cl .vh{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}.cl .vh b{font-size:15px}.cl .vh span{color:var(--mu);font-size:12px}
.cl ul{margin:0;padding-left:18px;color:var(--tx2);font-size:13px;line-height:1.6}.cl li b{color:var(--tx);font-weight:600}
.rm{display:grid;gap:8px}.rm div{display:grid;grid-template-columns:118px 1fr;gap:12px;align-items:start;font-size:13px;padding:8px 10px;border-radius:10px;background:#ffffff04}
.rm em{font-style:normal;font-size:11px;font-weight:600;padding:2px 8px;border-radius:6px;text-align:center}
.rm .s-now{background:#ffdd2d1f;color:var(--ac)}.rm .s-next{background:#3987e51f;color:#9cc3f5}.rm .s-later{background:#ffffff0d;color:var(--tx2)}.rm small{display:block;color:var(--mu);font-size:12px;margin-top:2px}
.badge{display:inline-flex;gap:6px;align-items:center;font-size:12px;color:var(--tx2)}
.badge b{width:7px;height:7px;border-radius:50%;background:var(--pos);box-shadow:0 0 0 3px #3ecf8e22}
.badge.sb b{background:var(--ac);box-shadow:0 0 0 3px #ffdd2d22}

main{flex:1;min-width:0;display:flex;flex-direction:column}
.top{display:flex;align-items:center;gap:14px;padding:14px 28px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.top h1{font-size:20px;font-weight:650;letter-spacing:-.02em;margin-right:auto;display:flex;align-items:baseline;gap:10px}
.top h1 small{font-size:13px;color:var(--mu);font-weight:500}
.seg{display:flex;background:var(--card);border:1px solid var(--line);border-radius:11px;padding:3px;flex-wrap:wrap}
.seg button{all:unset;cursor:pointer;padding:6px 12px;border-radius:8px;color:var(--tx2);font-size:13px;font-weight:500;transition:.15s;white-space:nowrap}
.seg button:hover{color:var(--tx)}.seg button.on{background:#2a2e38;color:var(--tx)}
.btn{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:8px;background:var(--ac);color:#121212;font-weight:600;
  padding:9px 15px;border-radius:10px;font-size:13px;transition:.15s;white-space:nowrap}
.btn:hover{background:var(--ac2)}
.btn.ghost{background:var(--card);color:var(--tx);border:1px solid var(--line2)}.btn.ghost:hover{background:var(--card2)}
.btn.danger{background:transparent;color:var(--neg);border:1px solid #ff6b6b55}
.btn[disabled]{opacity:.5;pointer-events:none}.btn svg{width:15px;height:15px}
.spin svg{animation:sp .9s linear infinite}@keyframes sp{to{transform:rotate(360deg)}}
.upd{color:var(--mu);font-size:12px}
#view{flex:1;overflow:auto;padding:22px 28px 48px}
.wrap{max-width:1500px;margin:0 auto;display:grid;gap:16px}

.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;min-width:0}
.card h2{font-size:13px;font-weight:600;color:var(--tx2);margin-bottom:14px;display:flex;align-items:center;gap:8px}
.card h2 .sp{margin-left:auto;font-weight:500;color:var(--mu);font-size:12px}
.g{display:grid;gap:16px}
.g2{grid-template-columns:repeat(2,minmax(0,1fr))}.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.g4{grid-template-columns:repeat(4,minmax(0,1fr))}.g6{grid-template-columns:repeat(3,minmax(0,1fr))}
@media(min-width:1640px){.g6{grid-template-columns:repeat(6,minmax(0,1fr))}}
.c-1-2{grid-template-columns:minmax(0,1fr) minmax(0,2fr)}.c-2-1{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}
@media(max-width:1180px){.c-1-2,.c-2-1,.g2,.g3{grid-template-columns:1fr}.g4{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:860px){aside{width:200px}.g4,.g6{grid-template-columns:repeat(2,minmax(0,1fr))}}

.hero{display:flex;gap:28px;align-items:flex-end;flex-wrap:wrap;background:linear-gradient(135deg,#1a1c22 0%,#16181d 55%,#1b1a14 100%);position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;right:-80px;top:-120px;width:340px;height:340px;border-radius:50%;background:radial-gradient(circle,#ffdd2d14,transparent 70%);pointer-events:none}
.hero .lbl{color:var(--tx2);font-size:13px;font-weight:500}
.hero .val{font-size:40px;font-weight:700;letter-spacing:-.03em;line-height:1.1;margin-top:6px}
.hero .val small{font-size:24px;color:var(--tx2);font-weight:600}
.pill{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:999px;font-size:12.5px;font-weight:600;background:#ffffff0d}
.pill.pos{color:var(--pos);background:#3ecf8e17}.pill.neg{color:var(--neg);background:#ff6b6b17}
.hero .meta{display:flex;gap:28px;margin-left:auto;flex-wrap:wrap;position:relative;z-index:1}
.hero .meta div span{display:block;color:var(--mu);font-size:12px;margin-bottom:3px}
.hero .meta div b{font-size:17px;font-weight:650}
.kpi{padding:16px 18px}
.kpi .k{color:var(--tx2);font-size:12.5px;font-weight:500;display:flex;gap:7px;align-items:center}
.kpi .k i{width:8px;height:8px;border-radius:3px;flex:none}
.kpi .v{font-size:21px;font-weight:680;letter-spacing:-.02em;margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .s{color:var(--mu);font-size:12px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pos{color:var(--pos)}.neg{color:var(--neg)}.mu{color:var(--mu)}.est{border-bottom:1px dotted var(--mu);cursor:help}.t2{color:var(--tx2)}

.chart{width:100%;position:relative}
.chart svg{display:block;overflow:visible}
.grid-l{stroke:#ffffff0f;stroke-width:1}
.ax{fill:var(--mu);font-size:11px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--tx2);margin-bottom:12px}
.legend span{display:inline-flex;align-items:center;gap:6px}.legend i{width:10px;height:10px;border-radius:3px}
#tip{position:fixed;pointer-events:none;z-index:50;background:#22252dee;backdrop-filter:blur(6px);border:1px solid var(--line2);border-radius:10px;
  padding:9px 11px;font-size:12px;min-width:160px;box-shadow:0 10px 30px #0008;opacity:0;transition:opacity .1s}
#tip b{display:block;margin-bottom:5px;font-size:12.5px}
#tip div{display:flex;align-items:center;gap:7px;margin-top:3px;color:var(--tx2)}
#tip div i{width:8px;height:8px;border-radius:2px;flex:none}#tip div span{margin-left:auto;color:var(--tx);font-variant-numeric:tabular-nums;padding-left:14px}
.donut-wrap{display:flex;gap:22px;align-items:center;flex-wrap:wrap}
.dl{flex:1;min-width:180px;display:grid;gap:9px}
.dl div{display:grid;grid-template-columns:10px 1fr auto auto;gap:9px;align-items:center;font-size:13px}
.dl i{width:10px;height:10px;border-radius:3px}.dl em{font-style:normal;color:var(--mu);font-size:12px;width:46px;text-align:right}
.hb{display:grid;gap:11px}
.hb .r{display:grid;grid-template-columns:110px minmax(40px,1fr) 128px;gap:12px;align-items:center;font-size:13px}
.hb.w .r{grid-template-columns:minmax(120px,240px) minmax(40px,1fr) 128px}
.hb .r .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hb .tr{height:8px;background:#ffffff08;border-radius:4px;overflow:hidden}
.hb .tr b{display:block;height:100%;border-radius:4px}
.hb .r .vv{text-align:right}

.li{display:grid;gap:4px}
.li .it{display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:12px;align-items:center;padding:7px 4px;border-radius:10px}
.li .it:hover{background:#ffffff05}
.li .it b{display:block;font-weight:600;font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.li .it small{display:block;color:var(--mu);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.li .it .rv{text-align:right;font-size:13.5px;font-weight:600}
.li .it .rv small{font-weight:500}
.li .bar{height:4px;border-radius:2px;background:#ffffff0a;margin-top:5px;overflow:hidden}.li .bar i{display:block;height:100%;border-radius:2px}

.av{position:relative;width:30px;height:30px;border-radius:50%;display:grid;place-items:center;font-size:10.5px;font-weight:700;color:#fff;flex:none;overflow:hidden;background:#2a2e38}
.av img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:#fff}
.av b{font-weight:700}

.tbl{overflow:auto;border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{position:sticky;top:0;background:var(--card);color:var(--mu);font-weight:500;font-size:12px;text-align:right;padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap;user-select:none;z-index:1}
th.s{cursor:pointer}th.s:hover{color:var(--tx)}
td{padding:9px 10px;border-bottom:1px solid #ffffff08;text-align:right;white-space:nowrap}
tr:hover td{background:#ffffff04}
th:first-child,td:first-child,.l{text-align:left!important}
.tk{display:flex;align-items:center;gap:10px;min-width:0}
.tk div{min-width:0}
.tk b{display:block;font-weight:600;max-width:300px;overflow:hidden;text-overflow:ellipsis}
.tk small{display:block;color:var(--mu);font-size:11.5px}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:6px;background:#ffffff0c;color:var(--tx2)}
.share{display:flex;align-items:center;gap:8px;justify-content:flex-end}.share i{display:block;height:5px;border-radius:3px;background:var(--s1);opacity:.85}
td.heat{position:relative}
.arr{font-size:11px;margin-right:3px}
.bt td,.bt th{padding:8px 7px;font-size:12.5px}
.hm td{text-align:center;font-size:12.5px;padding:8px 6px;border:2px solid var(--card);border-radius:6px}
.hm th{text-align:center}
.hm td.y{font-weight:650;text-align:left}

.field{display:grid;gap:7px}.field>span{font-size:12.5px;color:var(--tx2);font-weight:500}
.in{width:100%;background:var(--bg);border:1px solid var(--line2);border-radius:10px;padding:10px 12px;outline:0;transition:.15s}
.in:focus{border-color:var(--ac);box-shadow:0 0 0 3px #ffdd2d1f}
select.in{cursor:pointer}
textarea.in{resize:vertical;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px}
.sw{display:flex;align-items:center;gap:12px;cursor:pointer;user-select:none}
.sw input{display:none}.sw i{width:38px;height:22px;border-radius:999px;background:#2a2e38;position:relative;transition:.2s;flex:none}
.sw i:after{content:"";position:absolute;left:3px;top:3px;width:16px;height:16px;border-radius:50%;background:#fff;transition:.2s}
.sw input:checked+i{background:var(--ac)}.sw input:checked+i:after{left:19px;background:#121212}
.sw div b{display:block;font-weight:550}.sw div small{color:var(--mu);font-size:12px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.note{color:var(--mu);font-size:12px;line-height:1.55}
.msg{padding:11px 14px;border-radius:10px;font-size:13px}
.msg.ok{background:#3ecf8e14;color:var(--pos);border:1px solid #3ecf8e33}.msg.err{background:#ff6b6b12;color:#ff9a9a;border:1px solid #ff6b6b33}
.msg.info{background:#3987e514;color:#9cc3f5;border:1px solid #3987e533}
.empty{display:grid;place-items:center;text-align:center;gap:12px;padding:50px 20px;color:var(--tx2)}
.empty svg{width:44px;height:44px;opacity:.5}
.sk{background:linear-gradient(90deg,#16181d 0%,#1d2027 50%,#16181d 100%);background-size:200% 100%;animation:sh 1.3s infinite;border-radius:var(--r);border:1px solid var(--line)}
@keyframes sh{to{background-position:-200% 0}}
.wait{display:flex;align-items:center;gap:10px;color:var(--tx2);font-size:13px;padding:30px;justify-content:center}
.wait:before{content:"";width:14px;height:14px;border-radius:50%;border:2px solid var(--line2);border-top-color:var(--ac);animation:sp .8s linear infinite}
.fade{animation:fd .25s ease}@keyframes fd{from{opacity:0;transform:translateY(4px)}}
.more{display:flex;justify-content:center;padding:14px}
.drop{border:1.5px dashed var(--line2);border-radius:12px;padding:28px;text-align:center;color:var(--tx2);cursor:pointer;transition:.15s}
.drop:hover,.drop.over{border-color:var(--ac);background:#ffdd2d08;color:var(--tx)}
.map{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}

/* ── светлая тема ── */
:root[data-theme=light]{--bg:#f3f4f7;--side:#fff;--card:#fff;--card2:#f0f2f6;--line:#e4e7ed;--line2:#d2d7e0;
  --tx:#15171c;--tx2:#4a515f;--mu:#7a8292;--pos:#0f8f5c;--neg:#d23b3b;color-scheme:light}
[data-theme=light] ::-webkit-scrollbar-thumb{background:#cdd2dc}
[data-theme=light] .nav button:hover,[data-theme=light] .acl button:hover{background:#eff1f5}
[data-theme=light] .nav button.on,[data-theme=light] .acl button.on,[data-theme=light] .seg button.on{background:#eceff4}
[data-theme=light] .msw i,[data-theme=light] .av{background:#cdd2dc}
[data-theme=light] .hero{background:linear-gradient(135deg,#fff 0%,#fff 55%,#fff7cc 100%)}
[data-theme=light] .pill{background:#0000000a}
[data-theme=light] .grid-l{stroke:#0000001a}
[data-theme=light] .hb .tr,[data-theme=light] .li .bar{background:#0000000d}
[data-theme=light] .li .it:hover,[data-theme=light] tr:hover td{background:#00000006}
[data-theme=light] td{border-bottom-color:#0000000d}
[data-theme=light] .tag,[data-theme=light] .acl small em,[data-theme=light] .rm .s-later{background:#0000000d}
[data-theme=light] .rm div{background:#00000005}
[data-theme=light] .rm .s-next{color:#2a6fc4}
[data-theme=light] #tip{background:#fffffff2;box-shadow:0 10px 30px #0002}
[data-theme=light] .btn.ghost{background:#fff}
.rm .s-done{background:#3ecf8e1f;color:var(--pos)}
.pronly{display:none}
.remind{display:flex;gap:12px;align-items:flex-start;border-color:#ffdd2d66;background:linear-gradient(135deg,var(--card),#ffdd2d10)}
.remind b{font-weight:600}.remind small{display:block;color:var(--mu);font-size:12px;margin-top:2px}
.reb-in{width:84px;text-align:right}
.reb-sum{font-size:12.5px;color:var(--tx2)}


.rt{font-weight:600}.rt-AAA,.rt-AA{color:var(--pos)}.rt-A{color:#5aa0f0}.rt-BBB{color:var(--s4)}.rt-BB{color:var(--neg)}
[data-theme=light] .rt-A{color:#2a6fc4}
.rates .legend{justify-content:flex-end;margin-bottom:4px}
.strip{margin-top:14px;padding:12px 16px;border-radius:12px;background:var(--card2);display:flex;gap:22px;flex-wrap:wrap;font-size:14px;color:var(--tx2)}
.strip b{color:var(--tx);font-weight:650}
.axt{font-size:12.5px;font-weight:600;color:var(--tx2);margin:6px 0}
.dwrap{display:flex;align-items:stretch}.dscroll{overflow-x:auto;flex:1;min-width:0}
.lg2{display:flex;gap:10px 22px;flex-wrap:wrap;margin-top:14px;font-size:13px;color:var(--tx)}
.lg2 span{display:inline-flex;align-items:center;gap:8px}.lg2 i{width:14px;height:14px;border-radius:4px;flex:none}
.lg2 em{font-style:normal;font-size:11.5px;font-weight:600;padding:2px 9px;border-radius:999px;background:#c985001f;color:var(--s4);border:1px solid #c9850055}

.ins{display:grid;gap:10px}.ins div{display:grid;grid-template-columns:170px 1fr;gap:14px;font-size:13px;padding:10px 12px;border-radius:10px;background:var(--card2);line-height:1.55}
.ins b{font-weight:600}.ins span{color:var(--tx2)}.ins span b{color:var(--tx)}
.flt{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:14px}.flt .field{min-width:130px}.flt .in{width:100%}
.pnew{background:#ffdd2d18!important}
@media(max-width:760px){.ins div{grid-template-columns:1fr}}
/* ── мобильный вид ── */
@media(max-width:760px){
  html,body{height:auto}
  body{display:block;overflow:auto}
  aside{width:100%;border-right:0;border-bottom:1px solid var(--line);padding:10px 10px 8px;overflow:visible}
  .logo{padding:0 6px 8px}
  .nav{flex-direction:row;overflow-x:auto;gap:4px;padding-bottom:4px}
  .nav button{white-space:nowrap;padding:7px 10px}.nav .sep{display:none}
  .accs{margin-top:8px;padding-top:8px}
  .acl{flex-direction:row;overflow-x:auto;gap:6px;padding-bottom:4px}
  .acl button{min-width:150px;border:1px solid var(--line)}
  .side-foot{padding-top:6px}
  main{display:block}
  #view{overflow:visible;padding:14px 12px 40px}
  .top{padding:12px}
  .top h1{font-size:17px;width:100%}
  .g4,.g6,.g2,.g3,.c-1-2,.c-2-1{grid-template-columns:1fr}
  .hero .val{font-size:30px}.hero .meta{margin-left:0;gap:18px}
  .tbl{max-height:none!important}
}

/* ── печать / PDF ── */
@media print{
  aside,.top .btn,.top .seg,.upd,#tip,.noprint{display:none!important}
  html,body{height:auto;overflow:visible;display:block;background:#fff!important}
  main{display:block}#view{overflow:visible;padding:0}
  .top{padding:0 0 10px;border:0}.pronly{display:block;color:#666;font-size:12px;width:100%}
  .card{break-inside:avoid;box-shadow:none}.tbl{max-height:none!important;overflow:visible!important}
  .wrap{max-width:none}
  @page{margin:12mm}
}
[data-isin]{cursor:pointer}
#bc-ov{position:fixed;inset:0;z-index:40;display:flex;justify-content:flex-end;background:#0009;backdrop-filter:blur(2px)}
#bc-ov .bc-dr{width:min(780px,100%);height:100%;background:var(--bg);border-left:1px solid var(--line2);overflow:auto;padding:18px 20px 32px;
  box-shadow:-14px 0 40px #0006;animation:bcin .18s ease-out}
@keyframes bcin{from{transform:translateX(30px);opacity:0}to{transform:none;opacity:1}}
.bc-bar{display:flex;gap:8px;align-items:center;margin-bottom:14px}
.bc-bar .sp{flex:1}
.bc-bar .btn{padding:7px 12px;font-size:13px}
.bc-h h1{font-size:19px;font-weight:700;letter-spacing:-.01em;line-height:1.3;margin-bottom:6px}
.bc-h .row2{display:flex;flex-wrap:wrap;gap:8px;align-items:center;color:var(--tx2);font-size:12.5px}
.bc-h code{font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--tx2);background:var(--card2);padding:1px 6px;border-radius:5px}
.bc-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}
.bc-kpis .card{padding:12px 14px}
.bc-kpis .k{color:var(--tx2);font-size:12px}
.bc-kpis .v{font-size:19px;font-weight:680;margin-top:5px;letter-spacing:-.02em;white-space:nowrap}
.bc-kpis .s{color:var(--mu);font-size:11.5px;margin-top:2px}
.bc-sec{margin-top:14px}
.bc-sec h2{display:flex;align-items:center}
.bc-par{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 28px}
.bc-par div{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid var(--line);font-size:13px}
.bc-par div span:first-child{color:var(--mu)}
.bc-par div span:last-child{text-align:right;color:var(--tx);min-width:0;overflow-wrap:anywhere}
.bc-rel{padding:11px 14px;border-radius:10px;background:var(--card2);border:1px solid var(--line);font-size:13px;margin-bottom:12px;line-height:1.5}
.bc-rel b.pos{color:var(--pos)}.bc-rel b.neg{color:var(--neg)}
.bc-load{padding:60px 0;text-align:center;color:var(--mu)}
.bc-warn{margin:10px 0;padding:9px 12px;border-radius:10px;border:1px solid #c9850055;background:#c985001a;color:var(--tx2);font-size:12.5px}
.bc-ch{width:100%}
.bc-more{margin-top:8px}
#bc-ov .tbl{max-height:360px}
#bc-ov tr[data-isin]:hover td{background:var(--card2)}
body.bc-open{overflow:hidden}
@media(max-width:760px){
  #bc-ov .bc-dr{width:100%;border-left:0;padding:14px 14px 28px}
  .bc-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  .bc-par{grid-template-columns:1fr}
}
.mp-chips{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 14px}
.mp-chips button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:7px;padding:5px 12px;border-radius:999px;border:1px solid var(--line2);color:var(--mu);font-size:12.5px;font-weight:500;transition:.15s}
.mp-chips button i{width:9px;height:9px;border-radius:50%;opacity:.45}
.mp-chips button.on{color:var(--tx);background:var(--card2);border-color:var(--tx2)}.mp-chips button.on i{opacity:1}
.mp-d{cursor:pointer;stroke-opacity:.95;stroke-width:1}.mp-d:hover{fill-opacity:1;stroke:var(--tx);stroke-width:1.5}
.mp-ring{fill:none;stroke:var(--ac);stroke-width:2}
.mp-kbd{stroke:var(--tx2);stroke-width:1.6;stroke-dasharray:6 4;opacity:.85}
[data-theme=light] .mp-ring{stroke:#c98500}
.legend i.mp-lk{width:16px;height:0;border-top:2px dashed var(--tx2);border-radius:0;background:none}
.legend i.mp-lr{width:10px;height:10px;border-radius:50%;background:none;border:2px solid var(--ac)}
.mp-hm td{text-align:center;padding:8px 6px;border:2px solid var(--card);border-radius:6px;font-size:13px}
.mp-hm td small{display:block;color:var(--mu);font-size:11px;white-space:nowrap}
.mp-hm th{text-align:center}.mp-hm th.l,.mp-hm td.l{text-align:left}
.mp-g{align-items:start}
@media(max-width:760px){.mp-chips button{padding:4px 10px}.mp-hm td small{white-space:normal}}
.mp-fl{stroke:#19a070;stroke-width:1.5;stroke-dasharray:2 4;opacity:.95}
.mp-flt{fill:#19a070;font-size:11.5px}
.legend i.mp-lf{width:16px;height:0;border-top:2px dotted #19a070;border-radius:0;background:none}
.scr-fl{margin:0 0 10px}
tr.scr-low td{opacity:.5}
.rk-ctl{align-items:end}.rk-ctl .in{width:190px}
.rk-g{align-items:start}
.rk-tbl{max-height:640px}
#rk-tab tbody tr{cursor:pointer}
#rk-tab td small.neg{color:var(--neg);font-size:11px;line-height:1.3;display:inline-block;max-width:190px;white-space:normal}
.rk-dur p{margin:0 0 8px}.rk-dur b{color:var(--tx2)}
/* ── Сигналы ── */
.sg-t th,.sg-t td{white-space:nowrap}
.sg-t tbody tr[data-isin]{cursor:pointer}
.sg-t tbody tr[data-isin]:hover td{background:var(--card2)}
.sg-t td.l b{font-weight:600}
.sg-isin{display:block;font-size:11px;font-family:ui-monospace,Menlo,monospace}
.sg-h{margin:6px 0 10px;font-size:14px;font-weight:600}
.sg-h.pos{color:var(--pos)}.sg-h.neg{color:var(--neg)}
.sg-sp{vertical-align:middle;margin-right:2px}
.sg-tr.pos,.sg-tr.neg{font-weight:500}
.sg-more{margin-top:10px}
.sg-pos{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
.sg-pos:first-of-type{border-top:0;padding-top:0}
.sg-ph{cursor:pointer;margin-bottom:8px;display:grid;gap:3px}
.sg-ph .mu{font-size:12.5px;line-height:1.5}
.sg-worse{color:var(--neg);border-color:var(--neg)}
.sg-k{margin-bottom:14px}
.bc-ic svg{width:100%;height:auto;display:block}
.bc-ic .ic-pt{cursor:pointer;stroke:var(--card);stroke-width:1.5}
.bc-ic .ic-pt:hover{stroke:var(--tx)}
.bc-ic .ic-me{stroke:var(--tx);stroke-width:2.5}
.bc-ic .ic-ln{fill:none;stroke:#3987e5;stroke-width:1.5;opacity:.55}
.bc-ic .ic-kbd{fill:none;stroke:var(--tx2);stroke-width:1.5;stroke-dasharray:6 4}
.sg-g2{display:grid;gap:22px}
.mon-al{display:flex;align-items:center;gap:12px;padding:9px 12px;margin:6px 0;border-radius:10px;background:var(--card2);border-left:3px solid var(--mu);cursor:pointer}
.mon-al:hover{filter:brightness(1.06)}
.mon-al.mon-h{border-left-color:var(--neg)}.mon-al.mon-m{border-left-color:var(--s4)}.mon-al.mon-i{border-left-color:var(--s1)}
.mon-sev{flex:none;width:68px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--mu)}
.mon-h .mon-sev{color:var(--neg)}.mon-m .mon-sev{color:var(--s4)}.mon-i .mon-sev{color:var(--s1)}
.mon-d{flex:none;width:62px;font-size:12px;color:var(--mu)}
.mon-b{flex:1;min-width:0;display:grid;gap:1px;font-size:13px}.mon-b b{font-weight:600}.mon-b span{color:var(--tx2);white-space:normal}
.mon-al>a{flex:none;color:var(--tx2);text-decoration:none;font-size:15px;padding:2px 6px}.mon-al>a:hover{color:var(--ac)}
.mon-ok{color:var(--pos);font-size:13px;padding:6px 0}
.mon-card h2{display:flex;align-items:center;gap:10px}
.mon-sp{display:block;margin-left:auto}
.mon-w{color:var(--s4)}
.mon-th{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-top:14px}
#mon-tab tbody tr{cursor:pointer}
[data-theme=light] .mon-al{background:#f0f2f6}
/* сравнение с рынком */
.bn-sel{display:grid;gap:10px;margin:2px 0 14px}
.bn-grp{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.bn-gl{font-size:12px;color:var(--mu);min-width:150px}
.bn-chips{display:flex;gap:8px;flex-wrap:wrap}
.bn-chips button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:7px;padding:5px 12px;border-radius:999px;border:1px solid var(--line2);color:var(--mu);font-size:12.5px;font-weight:500;transition:.15s}
.bn-chips button i{width:9px;height:9px;border-radius:50%;opacity:.45}
.bn-chips button.on{color:var(--tx);background:var(--card2);border-color:var(--tx2)}.bn-chips button.on i{opacity:1}
.bn-chips button:disabled{cursor:default;opacity:.5}
.bn-t th,.bn-t td{white-space:nowrap}
.bn-t tr.bn-me td{background:var(--card2)}
.bn-t tr.bn-gr td{font-size:11.5px;color:var(--mu);text-transform:uppercase;letter-spacing:.04em;padding-top:12px}
.bn-g{align-items:start}
.bn-g tr[data-isin]{cursor:pointer}
.bn-pr{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid var(--line)}
.bn-pr:last-of-type{border-bottom:0}
.bn-pr span{display:grid;gap:2px}.bn-pr small{font-size:11.5px}.bn-pr b{font-size:16px;white-space:nowrap}
.bn-expl p{margin:0 0 10px}.bn-expl p:last-child{margin:0}
@media(max-width:760px){.bn-gl{min-width:100%}.bn-chips button{padding:4px 10px}}
/* ── Калькулятор инвестиций ── */
.cl-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px 16px;align-items:end;margin-bottom:6px}
.cl-grid>*{min-width:0}.cl-grid .sw{align-self:center}
#cl-goalbox{grid-column:1/-1;grid-template-columns:repeat(3,minmax(0,1fr));margin:0}
.cl-sec{font-size:12px;font-weight:600;color:var(--mu);text-transform:uppercase;letter-spacing:.04em;margin:18px 0 10px}
.cl-row{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap;margin:10px 0}
.cl-chips{display:flex;flex-wrap:wrap;gap:8px}
.cl-chip input{display:none}
.cl-chip span{display:inline-flex;align-items:center;gap:8px;padding:7px 13px;border:1px solid var(--line2);border-radius:999px;cursor:pointer;color:var(--tx2);font-size:13px;user-select:none;transition:.15s}
.cl-chip span i,.cl-dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}
.cl-dot{margin-right:8px}
.cl-chip input:checked+span{background:var(--card2);border-color:var(--ac);color:var(--tx)}
#cl-years{width:100%;accent-color:var(--ac)}
.cl-ans{font-size:15px;line-height:1.6}
.cl-goal{border-left:3px solid var(--ac)}
.cl-disc{margin:6px 2px 24px}
#cl-out .tbl td small{font-size:11px}
@media(max-width:1180px){.cl-grid{grid-template-columns:repeat(2,minmax(0,1fr))}#cl-goalbox{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.cl-grid{grid-template-columns:1fr}#cl-goalbox{grid-template-columns:1fr}}
.cl-page{display:grid;gap:16px;min-width:0}.cl-page>*{min-width:0}
#cl-out{display:grid;gap:16px;min-width:0}#cl-out>*{min-width:0}
/* оферты и лесенка */
.of-card{margin-bottom:14px}.of-urgent{border-color:#ff6b6b55}
.of-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;cursor:pointer;margin-bottom:12px}
.of-nm{display:grid;gap:2px;min-width:0;flex:1 1 220px}.of-nm small{font-size:12px}
.of-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;font-size:13px;line-height:1.45}
.of-grid .k{display:block;font-size:11.5px;color:var(--mu);margin-bottom:3px}
.of-hint{display:flex;gap:12px;align-items:flex-start;margin-top:14px;padding:11px 14px;border-radius:10px;border:1px solid var(--line2);font-size:13px}
.of-hint p{margin:3px 0 0;color:var(--tx2);line-height:1.5}
.of-lab{flex:none;font-size:11.5px;font-weight:600;padding:3px 9px;border-radius:6px;white-space:nowrap}
.of-info{background:#3987e514;border-color:#3987e533}.of-info .of-lab{background:#3987e52a;color:#9cc3f5}
.of-ok{background:#3ecf8e12;border-color:#3ecf8e33}.of-ok .of-lab{background:#3ecf8e26;color:var(--pos)}
.of-warn{background:#f2a63a14;border-color:#f2a63a44}.of-warn .of-lab{background:#f2a63a2a;color:#f2b45e}
.of-wait{background:#ffffff08}.of-wait .of-lab{background:#ffffff12;color:var(--tx2)}
.of-t-urg{background:#ff6b6b22;color:var(--neg)}.of-t-call{background:#f2a63a22;color:#f2b45e}
[data-theme=light] .of-info .of-lab{color:#2b6cb0}[data-theme=light] .of-warn .of-lab{color:#a86a0a}
@media(max-width:1180px){.of-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:640px){.of-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.of-hint{flex-direction:column}}
/* лесенка */
.ld-form{align-items:end}.ld-form .in{width:150px}.ld-form select.in{width:120px}
.ld-tbl .ld-rung td{background:#ffffff06;font-weight:600}
.ld-tbl tbody tr[data-isin]{cursor:pointer}
.ld-mon{font-size:11px;color:var(--mu);letter-spacing:.02em}
.ld-notes p{margin:0 0 8px}
/* эмитенты */
/* календарь событий */
/* наблюдение */
.wt-star{background:none;border:0;cursor:pointer;font-size:18px;line-height:1;color:var(--mu);padding:2px 6px;border-radius:6px}
.wt-star:hover{color:var(--s4)}.wt-star.on{color:var(--s4)}
.wt-sth,.wt-std{width:34px;text-align:center;padding-left:4px;padding-right:4px}
.wt-add{position:relative}
.wt-sug{display:grid;gap:4px;margin-top:8px}
.wt-s{display:flex;align-items:center;gap:12px;padding:8px 12px;border-radius:10px;background:var(--card2);cursor:pointer}
.wt-s>div{flex:1;min-width:0}.wt-s:hover{filter:brightness(1.06)}
.wt-sm{padding:4px 12px!important;font-size:12px!important}
.wt-in{min-width:84px;padding:6px 8px;font-size:12.5px}
.wt-in.wt-note{min-width:150px;text-align:left}
.wt-del{padding:2px 10px;font-size:15px}
#wt-tab tbody tr{cursor:pointer}
.wt-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.wt-ta{font-family:inherit;font-size:13.5px}
.wt-note-i{padding:10px 12px;margin:8px 0;border-radius:10px;background:var(--card2);cursor:pointer}
.wt-nh{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.wt-nt{margin-top:6px;white-space:pre-wrap;font-size:13.5px;color:var(--tx2)}
.wt-due{color:var(--s4)}
.tg-steps{margin:0;padding-left:20px;display:grid;gap:6px;font-size:13px;color:var(--tx2)}
.tg-steps code{background:var(--card2);padding:1px 6px;border-radius:6px;font-size:12px}
[data-theme=light] .wt-s,[data-theme=light] .wt-note-i{background:#f0f2f6}
/* налоги */
/* резервная копия */
</style></head>
<body>
<aside>
  <div class="logo"><i><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#111" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16l5-6 4 3 7-8"/></svg></i>
    <div>T-Invest Analytics<small>аналитика портфеля</small></div></div>
  <nav class="nav" id="nav"></nav>
  <div class="accs">
    <div class="acc-h">Счета <label class="msw" title="Скрыть счета без активов"><input type="checkbox" id="hideEmpty"><i></i>скрыть пустые</label></div>
    <div class="acl" id="acl"></div>
  </div>
  <div class="side-foot"><span class="badge" id="mode"></span><button class="ver" id="ver" title="Что нового"></button></div>
</aside>
<main>
  <div class="top">
    <h1 id="title">Обзор</h1>
    <div class="seg" id="period"></div>
    <span class="upd" id="upd"></span>
    <span class="pronly" id="prinfo"></span>
    <button class="btn ghost" id="thm" title="Сменить тему">◐</button>
    <button class="btn ghost" id="pdf" title="Печать / сохранить как PDF">PDF</button>
    <button class="btn ghost" id="refresh"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 4v5h-5"/></svg>Обновить</button>
  </div>
  <div id="view"></div>
</main>
<div id="tip"></div>
<script>
"use strict";
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NF2=new Intl.NumberFormat('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2});
const NF0=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0});
const NFQ=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:6});
const CUR={rub:'₽',usd:'$',eur:'€',cny:'¥',hkd:'HK$',gbp:'£',chf:'₣',jpy:'¥',try:'₺',kzt:'₸',byn:'Br',amd:'֏'};
const sym=c=>CUR[c]||(c||'').toUpperCase();
const bad=n=>n==null||isNaN(n)||!isFinite(n);
const f2=n=>bad(n)?'—':NF2.format(n);
const f0=n=>bad(n)?'—':NF0.format(n);
const M=(n,c='rub',d=2)=>bad(n)?'—':(d?NF2:NF0).format(n)+' '+sym(c);
const SM=(n,c='rub')=>bad(n)?'—':(n>0?'+':'')+M(n,c);
const pct=(n,d=2)=>bad(n)?'—':(n>0?'+':'')+n.toFixed(d).replace('.',',')+' %';
const pctp=(n,d=1)=>bad(n)?'—':n.toFixed(d).replace('.',',')+' %';
const cls=n=>n>0?'pos':n<0?'neg':'';
const short=n=>{if(bad(n))return'—';const a=Math.abs(n),t=(x,s)=>(x.toFixed(x>=100||Number.isInteger(x)?0:1).replace('.',',')+s),sg=n<0?'−':'';
  if(a>=1e9)return sg+t(a/1e9,' млрд');if(a>=1e6)return sg+t(a/1e6,' млн');if(a>=1e3)return sg+t(a/1e3,' тыс');return sg+f0(a)};
const MON=['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];
const MONF=['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
const mlabel=m=>{const[y,mm]=m.split('-');return MON[+mm-1]+' '+y.slice(2)};
const dlabel=d=>{const[y,m,dd]=d.split('-');return +dd+' '+MON[+m-1]+' '+y};
const ddm=d=>{const[y,m,dd]=d.split('-');return dd+'.'+m+'.'+y.slice(2)};
const S1='var(--s1)',S2='var(--s2)',S3='var(--s3)',S4='var(--s4)',S5='var(--s5)',S6='var(--s6)',S7='var(--s7)',S8='var(--s8)';
const PAL=[S1,S2,S3,S4,S5,S6,S7,S8];
const HEX=['#3987e5','#d95926','#199e70','#c98500','#d55181','#008300','#9085e9','#e66767'];

const IC={
 dash:'<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
 ret:'<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
 pos:'<path d="M21 12A9 9 0 1 1 12 3v9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
 bonds:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h6M7 13h10M7 16h4"/>',
 pay:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M8 14h2M14 14h2M8 17h2"/>',
 ops:'<path d="M4 6h16M4 12h16M4 18h10"/>',
 fees:'<path d="M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
 tax:'<path d="M9 14l6-6M9.5 8.5h.01M14.5 13.5h.01"/><path d="M5 3h14v18l-3.5-2-3.5 2-3.5-2L5 21z"/>',
 imp:'<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
 scr:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M8 11h6"/>',
 risk:'<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
 sig:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
 mon:'<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/>',
 map:'<circle cx="7" cy="16" r="2"/><circle cx="12" cy="9" r="2.5"/><circle cx="18" cy="13" r="1.6"/><path d="M3 3v18h18"/>',
 pri:'<path d="M12 2l2.6 6.3 6.9.6-5.2 4.5 1.6 6.7L12 16.4 6.1 20.1l1.6-6.7L2.5 8.9l6.9-.6z"/>',
 mkt:'<path d="M3 4v16h18"/><path d="M7 14l4-4 3 3 5-6"/>',
 reb:'<path d="M12 3v18M5 7h14M5 7l-2 6a3 3 0 0 0 6 0zM19 7l-2 6a3 3 0 0 0 6 0z"/>',
 bench:'<path d="M3 20h18"/><path d="M6 16V9M11 16V5M16 16v-5M20 16v-8"/>',
 calc:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2M12 11h2M16 11h0M8 15h2M12 15h2M8 18h2M12 18h4"/>',
 off:'<path d="M4 12h12M12 7l5 5-5 5"/><path d="M20 4v16"/>',
 lad:'<path d="M7 3v18M17 3v18M7 7h10M7 12h10M7 17h10"/>',
 iss:'<path d="M4 21V8l8-5 8 5v13"/><path d="M9 21v-6h6v6M8 11h.01M12 11h.01M16 11h.01"/>',
 cal:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/><path d="M12 14l1.2 2.4 2.6.4-1.9 1.8.5 2.6-2.4-1.3-2.4 1.3.5-2.6-1.9-1.8 2.6-.4z"/>',
 watch:'<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
 set:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>'};
const svgI=(p,sw=1.8)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const PAGES=[['dash','Обзор'],['ret','Доходность'],['bench','Сравнение с рынком'],['pos','Позиции'],['bonds','Облигации'],['pay','Выплаты'],['off','Оферты'],['ops','Операции'],['fees','Комиссии'],['tax','Налоги'],['reb','Ребалансировка'],['calc','Калькулятор'],['lad','Лесенка облигаций'],['mkt','Ставки'],['scr','Скринер облигаций'],['map','Карта рынка'],['sig','Сигналы'],['risk','Риски и сценарии'],['mon','Мониторинг'],['watch','Наблюдение'],['iss','Эмитенты'],['pri','Первичка'],['cal','Календарь событий'],null,['imp','Импорт отчётов'],['set','Настройки']];
const PERIODS=[['1m','Месяц'],['3m','3 мес'],['ytd','С начала года'],['12m','Год'],['py','Прошлый год'],['all','Всё время']];
const PERIOD_PAGES=['dash','ret','bench','ops','fees'];
function lsGet(k){try{return localStorage.getItem(k)}catch(e){return null}}
let st={};try{st=JSON.parse(lsGet('ta_state')||'{}')||{}}catch(e){}
const S={page:st.page||'dash',period:st.period||'all',account:st.account||'all',hideEmpty:st.hideEmpty!==false,
  data:null,bonds:null,hist:null,cfg:null,loading:false,err:null,accounts:[],
  sort:{k:'value_rub',d:-1},bsort:{k:'value_rub',d:-1},posType:'',opsN:200,opsQ:'',opsK:'',charts:[],imp:null};
function persist(){try{localStorage.setItem('ta_state',JSON.stringify({page:S.page,period:S.period,account:S.account,hideEmpty:S.hideEmpty}))}catch(e){}}

async function api(path,opt){
  const r=await fetch(path,opt);let j={};
  try{j=await r.json()}catch(e){}
  if(!r.ok)throw new Error(j.error||('HTTP '+r.status));
  if(j&&j.stale&&/^\/api\/(bonds|history)\?/.test(path))staleRefresh(path,j);
  return j;
}
/* Сервер отдал прошлый сохранённый результат (stale) и пересчитывает его в фоне: перезапрашиваем, пока не придёт свежий */
const _stl={};
function staleRefresh(path,first){
  const key=path.split('?')[0],isB=key==='/api/bonds',acc=S.account;
  if(_stl[key])return;
  let n=0;_stl[key]=1;
  const tick=async()=>{
    n++;
    try{
      const j=await fetch(path.replace(/&?force=1/,'')).then(r=>r.json());
      if(S.account!==acc){delete _stl[key];return}
      if(j&&j.stale&&n<40){setTimeout(tick,4000);return}
      delete _stl[key];
      if(!j||j.error)return;
      if(isB){S.bonds=j;if(['dash','bonds','pay'].includes(S.page))render()}
      else{S.hist=j;if(['dash','ret'].includes(S.page))render()}
    }catch(e){delete _stl[key]}
  };
  setTimeout(tick,4000);
}
const post=(p,b)=>api(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});

/* ── tooltip ── */
const tip=$('#tip');
function showTip(html,e){tip.innerHTML=html;tip.style.opacity=1;moveTip(e)}
function moveTip(e){const w=tip.offsetWidth,h=tip.offsetHeight;let x=e.clientX+14,y=e.clientY+14;
  if(x+w>innerWidth-8)x=e.clientX-w-14;if(y+h>innerHeight-8)y=e.clientY-h-14;tip.style.left=x+'px';tip.style.top=y+'px'}
function hideTip(){tip.style.opacity=0}
const tipRow=(c,n,v)=>`<div><i style="background:${c}"></i>${esc(n)}<span>${v}</span></div>`;
function bindTip(el,fn){
  el.onmousemove=e=>{const t=e.target.closest('[data-i]');if(!t||!el.contains(t)){hideTip();el._hl&&el._hl(-1);return}
    const i=+t.dataset.i;showTip(fn(i),e);el._hl&&el._hl(i)};
  el.onmouseleave=()=>{hideTip();el._hl&&el._hl(-1)};
}

/* ── charts ── */
function nice(mn,mx,ticks=4){
  if(mx===mn){mx=mn+1}
  const raw=(mx-mn)/ticks,p=Math.pow(10,Math.floor(Math.log10(raw))),m=raw/p;
  const s=(m<=1?1:m<=2?2:m<=2.5?2.5:m<=5?5:10)*p;
  return{lo:Math.floor(mn/s+1e-9)*s,hi:Math.ceil(mx/s-1e-9)*s,step:s};
}
const rtop=(x,y,w,h,r)=>{r=Math.min(r,w/2,h);if(h<=0)return'';return`M${x},${y+h}V${y+r}Q${x},${y} ${x+r},${y}H${x+w-r}Q${x+w},${y} ${x+w},${y+r}V${y+h}Z`};
const rbot=(x,y,w,h,r)=>{r=Math.min(r,w/2,h);if(h<=0)return'';return`M${x},${y}H${x+w}V${y+h-r}Q${x+w},${y+h} ${x+w-r},${y+h}H${x+r}Q${x},${y+h} ${x},${y+h-r}Z`};
const legend=ser=>ser.length>1?`<div class="legend">${ser.map(s=>`<span><i style="background:${s.c}"></i>${esc(s.n)}</span>`).join('')}</div>`:'';
function emptyChart(el,h,t){el.innerHTML=`<div class="empty" style="min-height:${h}px;padding:20px">${svgI('<path d="M3 3v18h18M7 15l4-4 3 3 5-6"/>')}<div>${t||'Нет данных за период'}</div></div>`}

function bars(el,o){
  const W=el.clientWidth,H=o.h||240,pl=58,pr=6,pt=8,pb=26,n=o.labels.length;
  if(!n||W<50)return emptyChart(el,H,o.empty);
  const ser=o.series,k=ser.length,stack=!!o.stack,fa=o.fa||short,ft=o.ft||(v=>M(v));
  let mn=0,mx=0;
  for(let i=0;i<n;i++){if(stack){let p=0,q=0;ser.forEach(s=>{const v=s.v[i]||0;v>0?p+=v:q+=v});mx=Math.max(mx,p);mn=Math.min(mn,q)}
    else ser.forEach(s=>{mx=Math.max(mx,s.v[i]||0);mn=Math.min(mn,s.v[i]||0)})}
  if(mx===0&&mn===0)return emptyChart(el,H,o.empty);
  const{lo,hi,step}=nice(mn,mx),pw=W-pl-pr,ph=H-pt-pb,gw=pw/n,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  const cols=stack?1:k,gap=2,bw=Math.max(2,Math.min(30,(gw*.72-(cols-1)*gap)/cols));
  let s='';
  for(let v=lo;v<=hi+step/2;v+=step){const y=Y(v);s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}"${Math.abs(v)<step/1e6?' style="stroke:#ffffff26"':''}/><text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${fa(Math.abs(v)<step/1e6?0:v)}</text>`}
  const every=Math.max(1,Math.ceil(n/Math.max(1,Math.floor(pw/62))));
  let marks='',hits='';
  for(let i=0;i<n;i++){
    const gx=pl+gw*i,x0=gx+(gw-(cols*bw+(cols-1)*gap))/2;
    if(i%every===0)s+=`<text class="ax" x="${gx+gw/2}" y="${H-6}" text-anchor="middle">${esc(o.labels[i])}</text>`;
    let pp=0,nn=0;const pos=[],neg=[];
    ser.forEach((se,j)=>{const v=se.v[i]||0;if(!v)return;
      if(stack){if(v>0){pos.push([j,pp,pp+v]);pp+=v}else{neg.push([j,nn+v,nn]);nn+=v}}
      else{const x=x0+j*(bw+gap),y=v>0?Y(v):Y(0),h=Math.abs(Y(v)-Y(0)),c=o.colorOf?o.colorOf(v,i):se.c;
        marks+=`<path class="bm" data-g="${i}" d="${v>0?rtop(x,y,bw,h,4):rbot(x,y,bw,h,4)}" fill="${c}"/>`}});
    if(stack){
      pos.forEach(([j,a,b],q)=>{const y1=Y(b),y0=Y(a),h=Math.max(0,y0-y1-(q?gap:0));marks+=`<path class="bm" data-g="${i}" d="${q===pos.length-1?rtop(x0,y1,bw,h,4):`M${x0},${y1}h${bw}v${h}h${-bw}Z`}" fill="${ser[j].c}"/>`});
      neg.forEach(([j,a,b],q)=>{const y0=Y(b),h=Math.max(0,Y(a)-y0-(q?gap:0));marks+=`<path class="bm" data-g="${i}" d="${q===neg.length-1?rbot(x0,y0+(q?gap:0),bw,h,4):`M${x0},${y0+(q?gap:0)}h${bw}v${h}h${-bw}Z`}" fill="${ser[j].c}"/>`});
    }
    if(o.labelsOn){const v=ser[0].v[i];if(v)s+=`<text class="ax num" x="${gx+gw/2}" y="${v>0?Y(v)-5:Y(v)+12}" text-anchor="middle" style="fill:var(--tx2)">${fa(v)}</text>`}
    hits+=`<rect data-i="${i}" x="${gx}" y="${pt}" width="${gw}" height="${ph}" fill="transparent"/>`;
  }
  el.innerHTML=(o.legend===false?'':legend(ser))+`<svg width="${W}" height="${H}">${s}<g>${marks}</g>${hits}</svg>`;
  const mk=el.querySelectorAll('.bm');
  el._hl=i=>mk.forEach(p=>p.style.opacity=i<0||+p.dataset.g===i?1:.35);
  bindTip(el,i=>{let h=`<b>${esc(o.tipLabels?o.tipLabels[i]:o.labels[i])}</b>`;ser.forEach(se=>{const v=se.v[i]||0;if(v||!o.skipZero)h+=tipRow(o.colorOf?o.colorOf(v,i):se.c,se.n,ft(v))});
    if(o.total){const t=ser.reduce((a,se)=>a+(se.v[i]||0),0);h+=`<div style="border-top:1px solid var(--line2);padding-top:5px;margin-top:6px">Итого<span>${ft(t)}</span></div>`}return h});
}

function line(el,o){
  const W=el.clientWidth,H=o.h||240,pl=62,pr=10,pt=10,pb=26;
  let labels=o.labels,ser=o.series,tl=o.tipLabels||labels;
  if(labels.length>420){const k=Math.ceil(labels.length/420),idx=[];for(let i=0;i<labels.length;i+=k)idx.push(i);if(idx[idx.length-1]!==labels.length-1)idx.push(labels.length-1);
    labels=idx.map(i=>labels[i]);tl=idx.map(i=>(o.tipLabels||o.labels)[i]);ser=ser.map(s=>({...s,v:idx.map(i=>s.v[i])}))}
  const n=labels.length;
  if(n<2||W<50)return emptyChart(el,H,o.empty);
  const fa=o.fa||short,ft=o.ft||(v=>M(v));
  let mn=Infinity,mx=-Infinity;
  ser.forEach(s=>s.v.forEach(v=>{if(v==null||isNaN(v))return;mn=Math.min(mn,v);mx=Math.max(mx,v)}));
  if(o.zero!==false)mn=Math.min(mn,0);if(!isFinite(mn)||mx===mn)return emptyChart(el,H,o.empty);
  const{lo,hi,step}=nice(mn,mx),pw=W-pl-pr,ph=H-pt-pb,X=i=>pl+i/(n-1)*pw,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  let s='';
  for(let v=lo;v<=hi+step/2;v+=step){const y=Y(v);s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}"${Math.abs(v)<step/1e6?' style="stroke:#ffffff26"':''}/><text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${fa(Math.abs(v)<step/1e6?0:v)}</text>`}
  const every=Math.max(1,Math.ceil(n/Math.max(1,Math.floor(pw/80))));
  for(let i=0;i<n-every/2;i+=every)s+=`<text class="ax" x="${X(i)}" y="${H-6}" text-anchor="${i===0?'start':'middle'}">${esc(labels[i])}</text>`;
  const gid='g'+Math.random().toString(36).slice(2,8);
  ser.forEach((se,j)=>{
    const segs=[];let cur=[],pv=null;se.v.forEach((v,i)=>{if(v==null||isNaN(v)){if(cur.length)segs.push(cur);cur=[];pv=null}else{if(se.step&&pv!=null)cur.push(X(i).toFixed(1)+','+Y(pv).toFixed(1));cur.push(X(i).toFixed(1)+','+Y(v).toFixed(1));pv=v}});if(cur.length)segs.push(cur);
    if(j===0&&o.area){const base=Y(Math.max(lo,Math.min(0,hi)));s+=`<defs><linearGradient id="${gid}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${se.hex||'#3987e5'}" stop-opacity="${o.area==='neg'?0:.28}"/><stop offset="1" stop-color="${se.hex||'#3987e5'}" stop-opacity="${o.area==='neg'?.28:0}"/></linearGradient></defs>`;
      segs.forEach(sg=>{const f=sg[0].split(','),l=sg[sg.length-1].split(',');s+=`<polygon points="${f[0]},${base} ${sg.join(' ')} ${l[0]},${base}" fill="url(#${gid})"/>`})}
    segs.forEach(sg=>s+=`<polyline points="${sg.join(' ')}" fill="none" stroke="${se.c}" stroke-width="${se.w||2}" stroke-linejoin="round" stroke-linecap="round"${se.dash?' stroke-dasharray="5 4"':''}/>`)});
  let hits='';const cw=pw/(n-1);
  for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${X(i)-cw/2}" y="${pt}" width="${cw}" height="${ph}" fill="transparent"/>`;
  el.innerHTML=legend(ser)+`<svg width="${W}" height="${H}">${s}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{if(i<0){hv.innerHTML='';return}hv.innerHTML=`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph}" stroke="#ffffff40" stroke-dasharray="3 3"/>`+
    ser.filter(se=>se.v[i]!=null&&!isNaN(se.v[i])).map(se=>`<circle cx="${X(i)}" cy="${Y(se.v[i])}" r="4.5" fill="${se.c}" stroke="var(--card)" stroke-width="2"/>`).join('')};
  bindTip(el,i=>{o.hover&&o.hover(i);return`<b>${esc(tl[i])}</b>`+ser.filter(se=>se.v[i]!=null&&!isNaN(se.v[i])).map(se=>tipRow(se.c,se.n,ft(se.v[i]))).join('')});
  if(o.leave){const ol=el.onmouseleave;el.onmouseleave=e=>{ol(e);o.leave()}}
}

function donut(el,o){
  const items=o.items.filter(x=>x.v>0.005),tot=items.reduce((a,x)=>a+x.v,0),D=o.size||180,R=D/2,r=R-22;
  if(!tot)return emptyChart(el,D,'Нет активов');
  let a=-Math.PI/2,arcs='';const g=items.length>1?0.012:0;
  items.forEach((x,i)=>{const da=x.v/tot*Math.PI*2,a0=a+g,a1=a+da-g;a+=da;if(a1<=a0)return;
    const big=a1-a0>Math.PI?1:0,p=(t,rr)=>[R+rr*Math.cos(t),R+rr*Math.sin(t)].map(v=>v.toFixed(2)).join(',');
    const d=items.length===1?`M${R},0A${R},${R} 0 1 1 ${R-0.01},0L${R-0.01},${R-r}A${r},${r} 0 1 0 ${R},${R-r}Z`:
      `M${p(a0,R)}A${R},${R} 0 ${big} 1 ${p(a1,R)}L${p(a1,r)}A${r},${r} 0 ${big} 0 ${p(a0,r)}Z`;
    arcs+=`<path data-i="${i}" class="arc" d="${d}" fill="${x.c}"/>`});
  el.innerHTML=`<div class="donut-wrap"><svg width="${D}" height="${D}" style="flex:none">${arcs}
    <text x="${R}" y="${R-4}" text-anchor="middle" style="fill:var(--mu);font-size:12px">${esc(o.cap||'Всего')}</text>
    <text x="${R}" y="${R+18}" text-anchor="middle" class="num" style="fill:var(--tx);font-size:17px;font-weight:700">${short(tot)}${o.unit===''?'':' ₽'}</text></svg>
    <div class="dl">${items.map((x,i)=>`<div data-i="${i}"><i style="background:${x.c}"></i><span>${esc(x.n)}</span><b class="num" style="font-weight:600">${short(x.v)}</b><em class="num">${(x.v/tot*100).toFixed(1).replace('.',',')}%</em></div>`).join('')}</div></div>`;
  const arcsEl=el.querySelectorAll('.arc');
  el._hl=i=>arcsEl.forEach(p=>p.style.opacity=i<0||+p.dataset.i===i?1:.35);
  bindTip(el,i=>`<b>${esc(items[i].n)}</b>`+tipRow(items[i].c,'Стоимость',M(items[i].v))+tipRow(items[i].c,'Доля',(items[i].v/tot*100).toFixed(1).replace('.',',')+' %'));
}

function hbars(items,color,fmt,wide){
  if(!items.length)return'<div class="empty" style="padding:24px">Нет данных</div>';
  const mx=Math.max(...items.map(x=>Math.abs(x.v)),1);
  return`<div class="hb${wide?' w':''}">${items.map(x=>`<div class="r"><span class="n" title="${esc(x.n)}">${esc(x.n)}</span><div class="tr"><b style="width:${Math.max(1.5,Math.abs(x.v)/mx*100)}%;background:${x.c||color}"></b></div><span class="vv num">${fmt?fmt(x):M(x.v)}${x.s?`<br><small class="${x.sc||'mu'}">${x.s}</small>`:''}</span></div>`).join('')}</div>`;
}
function chart(id,fn,o){S.charts.push([id,fn,o])}
function mountCharts(){S.charts.forEach(([id,fn,o])=>{const el=document.getElementById(id);if(el)try{fn(el,o)}catch(e){console.error(e);el.innerHTML='<div class="empty">Не удалось построить график</div>'}})}
let rT;addEventListener('resize',()=>{clearTimeout(rT);rT=setTimeout(mountCharts,120)});

/* ── logos ── */
const LOGO_BAD=new Set();
function colorFor(t){return HEX[(t||'?').split('').reduce((a,ch)=>a+ch.charCodeAt(0),0)%8]}
function logo(r,size=30){
  const t=(r.ticker&&!/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(r.ticker)&&r.ticker.length<=6?r.ticker:(r.name||r.ticker||'?')).replace(/^(ПАО|АО|ООО|МФК|ПКО|ОФЗ)\s+/i,''),w=t.split(/[\s\-«»"]+/).filter(x=>/[A-Za-zА-Яа-яЁё0-9]/.test(x)),init=esc((w.length>1&&!(r.ticker&&r.ticker.length<=6&&t===r.ticker)?w[0][0]+w[1][0]:(t.replace(/[^A-Za-zА-Яа-яЁё0-9]/g,'')||'?').slice(0,2)).toUpperCase());
  return`<span class="av" style="width:${size}px;height:${size}px;background:${esc(r.color||colorFor(t))};font-size:${Math.round(size*.36)}px"><b>${init}</b>${r.logo&&!LOGO_BAD.has(r.logo)?`<img src="/logo/${encodeURIComponent(r.logo)}" alt="" loading="lazy" data-l="${esc(r.logo)}" onerror="LOGO_BAD.add(this.dataset.l);this.remove()">`:''}</span>`;
}
const ident=(r,sub)=>`<div class="tk">${logo(r)}<div><b title="${esc(r.name)}">${esc(r.name||r.ticker)}</b><small>${esc(sub!=null?sub:(r.ticker&&r.ticker!==r.name?r.ticker:''))}</small></div></div>`;

/* ── shell ── */
function renderNav(){
  $('#nav').innerHTML=PAGES.map(p=>p?`<button class="${p[0]===S.page?'on':''}" data-p="${p[0]}">${svgI(IC[p[0]])}${p[1]}</button>`:'<div class="sep"></div>').join('');
  $('#period').innerHTML=PERIODS.map(([k,t])=>`<button class="${k===S.period?'on':''}" data-k="${k}">${t}</button>`).join('');
  $('#period').style.visibility=PERIOD_PAGES.includes(S.page)?'visible':'hidden';
  const a=S.accounts.find(x=>x.id===S.account);
  $('#title').innerHTML=esc(PAGES.find(p=>p&&p[0]===S.page)[1])+(['imp','set'].includes(S.page)?'':` <small>${esc(S.account==='all'?'все счета':a?a.name:'')}</small>`);
}
function renderAccounts(){
  const accs=S.accounts||[];
  const vis=accs.filter(a=>!S.hideEmpty||!a.empty||a.id===S.account);
  const all=accs.filter(a=>!a.empty).reduce((s,a)=>s+(a.total||0),0);
  $('#hideEmpty').checked=S.hideEmpty;
  $('#acl').innerHTML=(accs.length>1?`<button class="all ${S.account==='all'?'on':''}" data-a="all"><b>Все счета</b><span class="num">${short(all)}</span><small>${accs.filter(a=>!a.empty).length} с активами</small></button>`:'')+
    vis.map(a=>`<button class="${a.id===S.account?'on':''}" data-a="${esc(a.id)}"><b title="${esc(a.name)}">${esc(a.name)}</b><span class="num">${a.empty?'пусто':short(a.total)}</span>
      <small>${a.kind==='import'?'<em>импорт</em>':''}${a.type?`<em>${esc(a.type)}</em>`:''}${a.closed?'<em>закрыт</em>':''}</small></button>`).join('')+
    (S.hideEmpty&&vis.length<accs.length?`<div class="note" style="padding:4px 10px">Скрыто пустых: ${accs.length-vis.length}</div>`:'');
}
$('#nav').onclick=e=>{const b=e.target.closest('[data-p]');if(!b)return;go(b.dataset.p)};
$('#period').onclick=e=>{const b=e.target.closest('[data-k]');if(!b||b.dataset.k===S.period)return;S.period=b.dataset.k;persist();renderNav();load(false,true)};
$('#acl').onclick=e=>{const b=e.target.closest('[data-a]');if(!b||b.dataset.a===S.account)return;S.account=b.dataset.a;S.bonds=S.hist=null;persist();renderAccounts();renderNav();load(false)};
$('#hideEmpty').onchange=e=>{S.hideEmpty=e.target.checked;persist();renderAccounts()};
$('#refresh').onclick=()=>load(true);
function go(p){S.page=p;S.opsN=200;persist();renderNav();render()}

let reqId=0;
async function load(force,periodOnly){
  const my=++reqId;S.loading=true;S.err=null;
  $('#refresh').classList.add('spin');$('#refresh').disabled=true;
  if(!S.data&&!['set','imp'].includes(S.page))skeleton();
  try{
    const p=new URLSearchParams({period:S.period,account:S.account});if(force)p.set('force','1');
    const d=await api('/api/summary?'+p);
    if(my!==reqId)return;
    S.data=d;S.accounts=d.accounts;if(S.account!==d.account){S.account=d.account}persist();
    $('#upd').textContent='обновлено в '+d.updated;
    renderAccounts();renderNav();
    if(!periodOnly||force||!S.bonds||!S.hist)loadExtra(force);
  }catch(e){if(my!==reqId)return;S.err=e.message}
  finally{if(my===reqId){S.loading=false;$('#refresh').classList.remove('spin');$('#refresh').disabled=false}}
  if(my===reqId&&!['set','imp'].includes(S.page))render();
}
function loadExtra(force){
  const acc=S.account,p=new URLSearchParams({account:acc});if(force)p.set('force','1');
  if(force){S.bonds=null;S.hist=null}
  if(!S.bonds)api('/api/bonds?'+p).then(b=>{if(S.account!==acc)return;S.bonds=b;notifyUpcoming();if(['dash','bonds','pay'].includes(S.page))render()}).catch(e=>{if(S.account!==acc)return;S.bonds={error:e.message};if(['bonds','pay'].includes(S.page))render()});
  if(!S.hist)api('/api/history?'+p).then(h=>{if(S.account!==acc)return;S.hist=h;if(['dash','ret'].includes(S.page))render()}).catch(e=>{if(S.account!==acc)return;S.hist={error:e.message,days:[]};if(['dash','ret'].includes(S.page))render()});
}
function skeleton(){
  $('#view').innerHTML=`<div class="wrap"><div class="sk" style="height:130px"></div><div class="g g6">${'<div class="sk" style="height:96px"></div>'.repeat(6)}</div>
  <div class="g c-2-1"><div class="sk" style="height:320px"></div><div class="sk" style="height:320px"></div></div></div>`;
}
function render(){
  S.charts=[];hideTip();prInfo();
  const v=$('#view');
  if(S.page==='set')return renderSettings();
  if(S.page==='imp')return renderImport();
  if(S.err&&!S.data){v.innerHTML=`<div class="wrap"><div class="card empty fade">${svgI('<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>')}
    <div style="max-width:640px">${esc(S.err)}</div><div class="row" style="justify-content:center"><button class="btn" id="retry">Повторить</button>
    <button class="btn ghost" data-go="set">Настройки</button><button class="btn ghost" data-go="imp">Импорт отчёта</button></div></div></div>`;
    $('#retry').onclick=()=>load(true);v.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>go(b.dataset.go));return}
  if(!S.data){if(S.loading)skeleton();return}
  const sc=v.scrollTop;
  v.innerHTML=`<div class="wrap fade">${S.err?`<div class="msg err">${esc(S.err)}</div>`:''}${['dash','pay'].includes(S.page)?remindHtml():''}${({dash:pDash,ret:pRet,pos:pPos,bonds:pBonds,pay:pPay,ops:pOps,fees:pFees,tax:pTax,reb:pReb,mkt:pMkt,scr:pScr,map:pMap,risk:pRisk,sig:pSig,mon:pMon,pri:pPri,bench:pBench,calc:pCalc,off:pOff,lad:pLad,iss:pIss,cal:pCal,watch:pWatch})[S.page]()}</div>`;
  v.scrollTop=sc;
  mountCharts();bindPage();
}

/* ── helpers ── */
const T=()=>S.data.totals.rub||{};
const sumK=(o,ks)=>ks.reduce((a,k)=>a+(o[k]||0),0);
const TAXK=['tax_trade','tax_dividend','tax_coupon','tax_repo','tax_other'];
const FEEK=['fee_broker','fee_service','fee_other','margin_fee'];
const L={tax_trade:'Налог с прибыли по сделкам',tax_dividend:'Налог с дивидендов',tax_coupon:'Налог с купонов',tax_repo:'Налог по РЕПО',tax_other:'Прочие налоги',
  fee_broker:'Комиссия брокера',fee_service:'Обслуживание счёта',fee_other:'Прочие комиссии',margin_fee:'Плата за маржу (шорт / плечо)'};
const TYPES={share:'Акции',bond:'Облигации',etf:'Фонды',currency:'Валюта',futures:'Фьючерсы',option:'Опционы',sp:'Структурные'};
const SECT={financial:'Финансы',it:'IT',telecom:'Телеком',energy:'Энергетика',utilities:'Электроэнергетика',materials:'Сырьё и материалы',industrials:'Промышленность',
  consumer:'Потребительский',health_care:'Здравоохранение',real_estate:'Недвижимость',government:'Государство',municipal:'Муниципальные',ecomaterials:'Экология',
  green_energy:'Зелёная энергетика',green_buildings:'Зелёное строительство',electrocars:'Электромобили',other:'Прочее'};
function kpi(k,v,s,c,dot){return`<div class="card kpi"><div class="k">${dot?`<i style="background:${dot}"></i>`:''}${k}</div><div class="v num ${c||''}">${v}</div><div class="s">${s||'&nbsp;'}</div></div>`}
const periodName=()=>PERIODS.find(p=>p[0]===S.period)[1].toLowerCase();
const waitBox=t=>`<div class="wait">${t||'Считаю…'}</div>`;
function monthsSeries(n=36){
  let ms=S.data.months;if(ms.length>n)ms=ms.slice(-n);
  return{labels:ms.map(m=>mlabel(m[0])),tips:ms.map(m=>{const[y,mm]=m[0].split('-');return MONF[+mm-1]+' '+y}),rows:ms.map(m=>m[1])};
}
function periodStart(){const d=new Date();const iso=x=>x.toISOString().slice(0,10);
  switch(S.period){case'1m':d.setDate(d.getDate()-30);return iso(d);case'3m':d.setDate(d.getDate()-91);return iso(d);
  case'12m':d.setDate(d.getDate()-365);return iso(d);case'ytd':return d.getFullYear()+'-01-01';case'py':return(d.getFullYear()-1)+'-01-01';default:return null}}
function periodEnd(){return S.period==='py'?(new Date().getFullYear()-1)+'-12-31':null}
function histSlice(){
  const h=S.hist;if(!h||!h.days||!h.days.length)return null;
  const s=periodStart(),e=periodEnd();let i0=0,i1=h.days.length-1;
  if(s){i0=h.days.findIndex(d=>d>=s);if(i0<0)return null;i0=Math.max(0,i0-1)}
  if(e){while(i1>0&&h.days[i1]>e)i1--}
  if(i1<=i0)return null;
  const days=h.days.slice(i0,i1+1),base=h.twr[i0],twr=h.twr.slice(i0,i1+1).map(x=>x/base-1);
  const bench={};for(const[k,v]of Object.entries(h.bench||{})){const sl=v.slice(i0,i1+1);const b0=sl.find(x=>x!=null);bench[k]=sl.map(x=>x==null||!b0?null:x/b0-1)}
  let peak=-Infinity;const dd=twr.map(x=>{peak=Math.max(peak,1+x);return(1+x)/peak-1});
  const rets=[];for(let i=1;i<twr.length;i++)rets.push((1+twr[i])/(1+twr[i-1])-1);
  const mean=rets.reduce((a,b)=>a+b,0)/(rets.length||1),vol=Math.sqrt(rets.reduce((a,b)=>a+(b-mean)**2,0)/Math.max(1,rets.length-1))*Math.sqrt(365);
  const years=(new Date(days[days.length-1])-new Date(days[0]))/(365.25*864e5);
  const total=twr[twr.length-1],ann=years>=1?Math.pow(1+total,1/years)-1:null;
  return{days,twr,dd,bench,value:h.value.slice(i0,i1+1),invested:h.invested.slice(i0,i1+1),total,ann,vol,maxdd:Math.min(...dd),years};
}

/* ── Обзор ── */
function pDash(){
  const d=S.data,p=d.portfolio,t=T(),lf=d.life;
  if(!p.total&&!p.positions.length&&!d.ops.length&&!lf.deposits)return`<div class="card empty fade" style="min-height:420px">${svgI('<rect x="3" y="6" width="18" height="14" rx="3"/><path d="M3 10h18M16 15h2"/>')}
    <div style="font-size:17px;color:var(--tx);font-weight:600">Счёт пока пуст</div><div style="max-width:460px">На этом счёте нет активов и операций${d.sandbox?'. В песочнице его можно пополнить виртуальными деньгами в «Настройках».':'.'} Можно выбрать другой счёт слева или импортировать отчёт другого брокера.</div>
    <div class="row" style="justify-content:center"><button class="btn" data-go="imp">Импорт отчёта</button>${d.sandbox?'<button class="btn ghost" data-go="set">Настройки</button>':''}</div></div>`;
  const income=sumK(t,['dividends','coupons','overnight']),taxes=sumK(t,TAXK);
  const profit=d.profit,ppct=d.invested>0&&profit!=null?profit/d.invested*100:null,hs=histSlice();
  const hero=`<div class="card hero"><div style="position:relative;z-index:1"><div class="lbl">Стоимость портфеля</div>
    <div class="val num">${f2(p.total)} <small>₽</small></div>
    <div class="row" style="margin-top:10px">${p.daily!=null?`<span class="pill ${cls(p.daily)}">${SM(p.daily)} · ${pct(p.daily_pct)} за день</span>`:''}
    <span class="pill ${cls(p.upnl)}">${SM(p.upnl)} · ${pct(p.yield_pct)} по открытым позициям</span></div></div>
    <div class="meta"><div><span>Вложено (пополнения − выводы)</span><b class="num">${M(d.invested,'rub',0)}</b></div>
    <div><span>Прибыль за всё время</span><b class="num ${cls(profit)}">${profit==null?'—':SM(profit)}</b>${ppct!=null?` <span class="mu num" style="display:inline">${pct(ppct,1)}</span>`:''}</div>
    <div><span>Доходность за период (TWR)</span><b class="num ${hs?cls(hs.total):''}">${hs?pct(hs.total*100,2):S.hist&&!S.hist.error?'—':'…'}</b></div>
    <div><span>XIRR, % годовых</span><b class="num ${cls(d.xirr)}">${d.xirr==null?'—':pct(d.xirr*100,1)}</b></div></div></div>`;
  const turn=(t.buy_turnover||0)+(t.sell_turnover||0);
  const kpis=`<div class="g g6">
    ${kpi('Реализовано по сделкам',SM(t.realized||0),'фиксированный результат продаж',cls(t.realized),S1)}
    ${kpi('Пассивный доход',M(income),`дивиденды ${short(t.dividends||0)} · купоны ${short(t.coupons||0)}`,income?'pos':'',S3)}
    ${kpi('Комиссии брокера',M(sumK(t,['fee_broker','fee_service','fee_other'])),turn?`${f2((t.fee_broker||0)/turn*100)} % от оборота`:'',null,S2)}
    ${kpi('Плата за маржу',M(t.margin_fee||0),t.varmargin?`вар. маржа ${SM(t.varmargin)}`:'шорт и кредитное плечо',null,S5)}
    ${kpi('Налоги удержано',M(taxes),'подробнее — во вкладке «Налоги»',null,S4)}
    ${kpi('Оборот',M(turn,'rub',0),`покупки ${short(t.buy_turnover||0)} · продажи ${short(t.sell_turnover||0)}`,null,S7)}</div>`;
  const alloc=[['Акции',p.shares,S1],['Облигации',p.bonds,S2],['Фонды',p.etf,S3],['Валюта и деньги',p.currencies,S4],['Фьючерсы',p.futures,S5],['Структурные',p.sp,S6],['Опционы',p.options,S7],['Прочее',p.other,S8]].map(([n,v,c])=>({n,v,c}));
  chart('c-alloc',donut,{items:alloc,cap:'Портфель'});
  let eq=waitBox('Восстанавливаю историю стоимости по ценам закрытия…');
  if(S.hist&&S.hist.error)eq=`<div class="msg err">${esc(S.hist.error)}</div>`;
  else if(S.hist&&!hs)eq='<div class="empty">Недостаточно истории за период</div>';
  else if(hs){eq='<div id="c-eq" class="chart"></div>';
    chart('c-eq',line,{h:290,area:true,zero:false,labels:hs.days.map(x=>{const[y,m]=x.split('-');return MON[+m-1]+' '+y.slice(2)}),tipLabels:hs.days.map(dlabel),
      series:[{n:'Стоимость портфеля',c:S1,hex:'#3987e5',v:hs.value},{n:'Вложено',c:'#8b93a7',v:hs.invested,dash:1,w:1.6}]})}
  let mret=waitBox();
  if(S.hist&&S.hist.monthly){const ms=Object.keys(S.hist.monthly).sort().slice(-12);mret='<div id="c-mret" class="chart"></div>';
    chart('c-mret',bars,{labels:ms.map(mlabel),tipLabels:ms.map(m=>{const[y,mm]=m.split('-');return MONF[+mm-1]+' '+y}),labelsOn:ms.length<=12,
      series:[{n:'Доходность',c:S1,v:ms.map(m=>S.hist.monthly[m]*100)}],colorOf:v=>v>=0?'var(--pos)':'var(--neg)',fa:v=>(Math.round(v*10)/10).toString().replace('.',',')+'%',ft:v=>pct(v)})}
  else if(S.hist&&S.hist.error)mret='<div class="empty">Нет данных</div>';
  let pays=waitBox('Собираю график купонов и дивидендов…');
  if(S.bonds&&S.bonds.payments){const pm=payMonths(S.bonds.payments,6);const tot=S.bonds.payments.reduce((a,x)=>a+x.amount,0);
    pays=`<div class="row" style="justify-content:space-between;margin:-4px 0 10px"><span class="t2" style="font-size:12.5px">За 12 месяцев ожидается</span><b class="num pos">${M(tot)}</b></div><div id="c-pay6" class="chart"></div>`;
    chart('c-pay6',bars,{h:190,labels:pm.labels,tipLabels:pm.tips,stack:true,total:true,skipZero:true,series:pm.series,empty:'Выплат не ожидается'})}
  const top=p.positions.filter(x=>x.type!=='currency'&&x.type!=='futures').slice(0,8);
  const mx=Math.max(1,...top.map(x=>x.value_rub||0));
  const topHtml=top.length?`<div class="li">${top.map(x=>`<div class="it">${logo(x,34)}<div><b>${esc(x.name)}</b><small>${esc(x.ticker)} · ${pctp(x.share)} портфеля</small><div class="bar"><i style="width:${(x.value_rub||0)/mx*100}%;background:${S1}"></i></div></div>
    <div class="rv num">${M(x.value_rub??x.value,'rub',0)}<small class="${cls(x.pnl)}">${x.pnl_rub!=null?SM(x.pnl_rub):''} ${x.pnl_pct!=null?'('+pct(x.pnl_pct,1)+')':''}</small></div></div>`).join('')}</div>`:'<div class="empty">Нет открытых позиций</div>';
  const inc=d.income_by.filter(x=>x[0]>0).slice(0,8),imx=Math.max(1,...inc.map(x=>x[0]));
  const incHtml=inc.length?`<div class="li">${inc.map(x=>`<div class="it">${logo({name:x[1],ticker:x[2],logo:x[3]},34)}<div><b>${esc(x[1])}</b><small>${esc(x[2]||'')}${x[4]?' · '+(TYPES[x[4]]||''):''}</small><div class="bar"><i style="width:${x[0]/imx*100}%;background:${S3}"></i></div></div>
    <div class="rv num pos">${M(x[0])}</div></div>`).join('')}</div>`:'<div class="empty">Выплат за период не было</div>';
  const marg=d.margin?`<div class="card"><h2>Маржинальная торговля</h2><div class="g g6" style="gap:12px">
    ${[['Ликвидный портфель','liquidPortfolio'],['Начальная маржа','startingMargin'],['Минимальная маржа','minimalMargin'],['Скорр. маржа','correctedMargin'],['Не хватает средств','amountOfMissingFunds']]
      .map(([n,k])=>`<div><div class="mu" style="font-size:12px">${n}</div><div class="num" style="font-weight:650;font-size:16px;margin-top:4px">${M(d.margin[k])}</div></div>`).join('')}
    <div><div class="mu" style="font-size:12px">Уровень достаточности</div><div class="num ${d.margin.fundsSufficiencyLevel<1.1&&d.margin.fundsSufficiencyLevel>0?'neg':''}" style="font-weight:650;font-size:16px;margin-top:4px">${f2(d.margin.fundsSufficiencyLevel)}</div></div></div></div>`:'';
  return hero+kpis+monCard()+`<div class="g c-2-1"><div class="card"><h2>Стоимость и вложения<span class="sp">${periodName()}</span></h2>${eq}</div>
    <div class="card"><h2>Структура портфеля</h2><div id="c-alloc" class="chart"></div></div></div>
    <div class="g g2"><div class="card"><h2>Доходность по месяцам<span class="sp">последние 12 мес</span></h2>${mret}</div>
    <div class="card"><h2>Ближайшие выплаты<span class="sp">купоны · дивиденды · погашения</span></h2>${pays}</div></div>
    <div class="g g2"><div class="card"><h2>Крупнейшие позиции<span class="sp">стоимость · P&amp;L</span></h2>${topHtml}</div>
    <div class="card"><h2>Кто платит дивиденды и купоны<span class="sp">${periodName()}</span></h2>${incHtml}</div></div>`+marg;
}

function payMonths(pays,n){
  const now=new Date(),keys=[];for(let i=0;i<n;i++){const d=new Date(now.getFullYear(),now.getMonth()+i,1);keys.push(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0'))}
  const k3={coupon:{},dividend:{},redemption:{},amortization:{}};pays.forEach(p=>{const m=p.date.slice(0,7);if(keys.includes(m))(k3[p.kind]=k3[p.kind]||{})[m]=(k3[p.kind][m]||0)+p.amount});
  return{labels:keys.map(mlabel),tips:keys.map(m=>{const[y,mm]=m.split('-');return MONF[+mm-1]+' '+y}),
    series:[{n:'Купоны',c:S1,v:keys.map(k=>k3.coupon[k]||0)},{n:'Дивиденды',c:S3,v:keys.map(k=>k3.dividend[k]||0)},{n:'Погашения',c:S4,v:keys.map(k=>k3.redemption[k]||0)},{n:'Амортизации',c:S5,v:keys.map(k=>k3.amortization[k]||0)}]};
}

/* ── Доходность ── */
function heatBg(v,mx){if(bad(v))return'';const a=Math.min(1,Math.abs(v)/(mx||1));return`background:${v>=0?'rgba(62,207,142,'+(0.08+a*0.42)+')':'rgba(255,107,107,'+(0.08+a*0.42)+')'}`}
function pRet(){
  const h=S.hist;
  if(!h)return`<div class="card">${waitBox('Восстанавливаю историю стоимости портфеля по дневным ценам закрытия. Первый раз это может занять до минуты — дальше данные берутся из локальной базы.')}</div>`;
  if(h.error)return`<div class="msg err">${esc(h.error)}</div>`;
  if(!h.days.length)return'<div class="card empty">Нет операций для расчёта доходности</div>';
  const hs=histSlice();
  const ms=Object.keys(h.monthly).sort(),years=[...new Set(ms.map(m=>m.slice(0,4)))].sort().reverse();
  const inP=m=>{const s=periodStart(),e=periodEnd();return(!s||m>=s.slice(0,7))&&(!e||m<=e.slice(0,7))};
  const pm=ms.filter(inP).map(m=>[m,h.monthly[m]]);
  const best=pm.length?pm.reduce((a,b)=>b[1]>a[1]?b:a):null,worst=pm.length?pm.reduce((a,b)=>b[1]<a[1]?b:a):null;
  const lab=m=>{const[y,mm]=m.split('-');return MONF[+mm-1].toLowerCase()+' '+y};
  let out=`<div class="g g6">
    ${kpi('Доходность за период',hs?pct(hs.total*100):'—','метод TWR — без влияния пополнений',hs?cls(hs.total):'',S1)}
    ${kpi('В пересчёте на год',hs&&hs.ann!=null?pct(hs.ann*100):'—',hs&&hs.ann==null?'период короче года':'среднегодовая (TWR)',hs&&hs.ann!=null?cls(hs.ann):'',S7)}
    ${kpi('XIRR',S.data.xirr==null?'—':pct(S.data.xirr*100,1),'с учётом сумм и дат пополнений',cls(S.data.xirr),S3)}
    ${kpi('Макс. просадка',hs?pct(hs.maxdd*100):'—','от пика до дна за период',hs&&hs.maxdd<0?'neg':'',S2)}
    ${kpi('Лучший месяц',best?pct(best[1]*100):'—',best?lab(best[0]):'','pos',S3)}
    ${kpi('Худший месяц',worst?pct(worst[1]*100):'—',worst?lab(worst[0]):'',worst&&worst[1]<0?'neg':'',S8)}</div>`;
  if(hs){
    const labs=hs.days.map(x=>{const[y,m]=x.split('-');return MON[+m-1]+' '+y.slice(2)}),tips=hs.days.map(dlabel);
    const ser=[{n:'Мой портфель',c:S1,hex:'#3987e5',v:hs.twr.map(x=>x*100),w:2.4}];
    if(hs.bench.LQDT)ser.push({n:'Денежный рынок (LQDT)',c:S3,v:hs.bench.LQDT.map(x=>x==null?null:x*100),w:1.6});
    if(hs.bench.TMOS)ser.push({n:'Индекс МосБиржи (фонд TMOS)',c:S2,v:hs.bench.TMOS.map(x=>x==null?null:x*100),w:1.6});
    const fp=v=>(Math.round(v*10)/10).toString().replace('.',',')+'%';
    chart('c-twr',line,{h:300,labels:labs,tipLabels:tips,series:ser,fa:fp,ft:v=>pct(v),zero:false});
    chart('c-dd',line,{h:200,area:'neg',labels:labs,tipLabels:tips,series:[{n:'Просадка',c:S8,hex:'#e66767',v:hs.dd.map(x=>x*100)}],fa:fp,ft:v=>pct(v)});
    chart('c-pl',line,{h:200,area:true,labels:labs,tipLabels:tips,series:[{n:'Прибыль (стоимость − вложено)',c:S3,hex:'#199e70',v:hs.value.map((v,i)=>v-hs.invested[i])}]});
    out+=`<div class="card"><h2>Доходность портфеля и бенчмарков, %<span class="sp">${periodName()}</span></h2><div id="c-twr" class="chart"></div></div>
      <div class="g g2"><div class="card"><h2>Просадка от максимума, %</h2><div id="c-dd" class="chart"></div></div>
      <div class="card"><h2>Прибыль в рублях</h2><div id="c-pl" class="chart"></div></div></div>`;
  }
  const mx=Math.max(0.01,...ms.map(m=>Math.abs(h.monthly[m])));
  out+=`<div class="card" style="padding:14px 16px"><h2 style="padding:4px 4px 0">Доходность по месяцам, %</h2><div class="tbl"><table class="hm"><thead><tr><th class="l">Год</th>${MON.map(m=>`<th>${m}</th>`).join('')}<th>За год</th></tr></thead><tbody>`+
    years.map(y=>{let acc=1;const cells=MON.map((_,i)=>{const k=y+'-'+String(i+1).padStart(2,'0'),v=h.monthly[k];if(v==null)return'<td></td>';acc*=1+v;
      return`<td class="num" style="${heatBg(v,mx)}">${(v*100).toFixed(2).replace('.',',')}</td>`}).join('');
      return`<tr><td class="y">${y}</td>${cells}<td class="num" style="${heatBg(acc-1,mx*4)};font-weight:650">${pct((acc-1)*100)}</td></tr>`}).join('')+
    `</tbody></table></div></div>`;
  const rc=h.recon||{},diff=rc.actual?(rc.calc-rc.actual)/rc.actual*100:null;
  out+=`<p class="note">Стоимость портфеля на каждый день восстановлена по операциям и дневным ценам закрытия (облигации — с НКД по графику купонов). Доходность считается по методу TWR — пополнения и выводы на неё не влияют, поэтому её можно сравнивать с бенчмарками.
    ${diff!=null&&Math.abs(diff)>2?`<b>Расчётная стоимость на сегодня (${M(rc.calc,'rub',0)}) отличается от фактической (${M(rc.actual,'rub',0)}) на ${pct(diff,1)}</b> — вероятно, по части бумаг нет истории цен (внебиржевые, заблокированные, фьючерсы) или переводы бумаг между брокерами.`:''}
    ${h.glitches?`Пропущено дней с некорректными ценами: ${h.glitches}.`:''} Бенчмарки — фонды LQDT (денежный рынок) и TMOS (индекс МосБиржи) с учётом их собственной доходности.</p>`;
  return out;
}

/* ── Позиции ── */
function pPos(){
  const all=S.data.portfolio.positions,typesHere=[...new Set(all.map(x=>x.type))].filter(Boolean);
  let ps=all.filter(x=>!S.posType||x.type===S.posType);
  const{k,d}=S.sort;
  ps=ps.slice().sort((a,b)=>{const x=a[k],y=b[k];if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  const nonCur=all.filter(x=>x.type!=='currency');
  const totPnl=nonCur.reduce((a,x)=>a+(x.pnl_rub||0),0),tot=all.reduce((a,x)=>a+(x.value_rub||0),0)||1;
  const top5=nonCur.slice().sort((a,b)=>(b.value_rub||0)-(a.value_rub||0)).slice(0,5).reduce((a,x)=>a+(x.value_rub||0),0)/tot*100;
  const sect={};nonCur.forEach(x=>{const s=SECT[x.sector]||(x.type==='etf'?'Фонды':x.sector?x.sector:'Без сектора');sect[s]=(sect[s]||0)+(x.value_rub||0)});
  const sectItems=Object.entries(sect).sort((a,b)=>b[1]-a[1]);
  const sec8=sectItems.slice(0,7).map(([n,v],i)=>({n,v,c:PAL[i]}));if(sectItems.length>7)sec8.push({n:'Остальные',v:sectItems.slice(7).reduce((a,x)=>a+x[1],0),c:S8});
  chart('c-sect',donut,{items:sec8,cap:'По секторам',size:170});
  const cols=[['name','Инструмент','l'],['type','Тип','l'],['qty','Кол-во'],['avg','Средняя'],['price','Текущая'],['value_rub','Стоимость, ₽'],['share','Доля'],['pnl_rub','P&L, ₽'],['pnl_pct','P&L %']];
  const th=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  const mxs=Math.max(1,...ps.map(x=>x.share||0));
  const rows=ps.map(x=>`<tr><td>${ident(x)}</td>
    <td class="l"><span class="tag">${TYPES[x.type]||esc(x.type)}</span>${x.blocked?' <span class="tag" style="color:var(--neg)">блок</span>':''}</td>
    <td class="num">${NFQ.format(x.qty)}</td><td class="num">${x.avg&&x.type!=='currency'?M(x.avg,x.cur):'—'}</td><td class="num">${M(x.price,x.cur)}</td>
    <td class="num">${x.value_rub!=null?M(x.value_rub):M(x.value,x.cur)}</td>
    <td class="num"><div class="share"><i style="width:${Math.max(1,(x.share||0)/mxs*60)}px"></i>${pctp(x.share)}</div></td>
    <td class="num ${cls(x.pnl)}">${x.type==='currency'?'<span class="mu">—</span>':x.pnl_rub!=null?SM(x.pnl_rub):SM(x.pnl,x.cur)}</td><td class="num ${cls(x.pnl)}">${x.type==='currency'?'':pct(x.pnl_pct)}</td></tr>`).join('');
  return`<div class="g g4">${kpi('Позиций',nonCur.length,'без учёта валюты и денег')}${kpi('Нереализованный P&L',SM(totPnl),'по открытым позициям',cls(totPnl))}
    ${kpi('В прибыли / в убытке',`<span class="pos">${nonCur.filter(x=>x.pnl>0).length}</span> <span class="mu">/</span> <span class="neg">${nonCur.filter(x=>x.pnl<0).length}</span>`,'позиций')}
    ${kpi('Топ-5 позиций',pctp(top5),'доля в портфеле — концентрация',top5>60?'neg':'')}</div>
    <div class="g c-1-2"><div class="card"><h2>Секторы</h2><div id="c-sect" class="chart"></div></div>
    <div class="card"><h2>Крупнейшие доли</h2>${hbars(nonCur.slice().sort((a,b)=>(b.value_rub||0)-(a.value_rub||0)).slice(0,10).map(x=>({n:x.name,v:x.share||0})),S1,x=>pctp(x.v),1)}</div></div>
    <div class="card" style="padding:12px 10px 6px"><div class="row" style="padding:0 6px 10px"><div class="seg" id="ptype"><button class="${!S.posType?'on':''}" data-t="">Все · ${all.length}</button>${typesHere.map(t=>`<button class="${S.posType===t?'on':''}" data-t="${t}">${TYPES[t]||t} · ${all.filter(x=>x.type===t).length}</button>`).join('')}</div></div>
    ${ps.length?`<div class="tbl" style="max-height:calc(100vh - 220px)"><table id="ptab"><thead><tr>${th}</tr></thead><tbody>${rows}</tbody></table></div>`:'<div class="empty">Позиций нет</div>'}</div>
    <p class="note">P&amp;L по счетам Т-Инвестиций — по данным брокера (FIFO), для облигаций без НКД. По импортированным счетам — расчёт по сделкам из отчёта и текущим ценам биржи.</p>`;
}


/* ── кредитные рейтинги ── */
const RSC=['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC','CC','C','D'];
const rBucket=v=>{if(!v)return'нет рейтинга';const i=RSC.indexOf(v);return i===0?'AAA':i<=3?'AA':i<=6?'A':i<=9?'BBB':'BB и ниже'};
function ratingTag(r){
  const t=r.all.map(x=>`${x.agency}: ${x.rating} · ${x.issuer}${x.approx?' (приблизительное совпадение названия)':''} · от ${x.date}${x.outlook?' · '+x.outlook:''}`).join('\n');
  return`<span class="tag rt rt-${rBucket(r.v).split(' ')[0]}" title="${esc(t)}">${r.approx?'≈ ':''}${esc(r.v)}</span>`;
}
function ratingsCard(b){
  const info=b.ratings_info||{},tot=(b.ratings||[]).reduce((a,x)=>a+x[1],0)||1;
  const COL={'AAA':S3,'AA':S3,'A':S1,'BBB':S4,'BB и ниже':S8,'нет рейтинга':'#6f7686'};
  const order=['AAA','AA','A','BBB','BB и ниже','нет рейтинга'],m=Object.fromEntries(b.ratings||[]);
  const items=order.filter(k=>m[k]).map(k=>({n:k==='нет рейтинга'?'Нет данных':k,v:m[k],c:COL[k],s:pctp(m[k]/tot*100)}));
  const st=info.running?`Загружаю рейтинги… ${esc(info.progress||'')}`:info.updated?`Обновлено ${new Date(info.updated*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})} · эмитентов в базе: ${info.count}`:'Рейтинги ещё не загружены';
  if(info.running&&!S._rtTimer)S._rtTimer=setTimeout(async()=>{S._rtTimer=null;if(S.page!=='bonds')return;try{S.bonds=await api('/api/bonds?'+new URLSearchParams({account:S.account}));render()}catch(e){}},5000);
  return`<div class="card"><h2>Кредитные рейтинги эмитентов<span class="sp">${st}</span></h2>
    <div class="g g2"><div>${hbars(items,S1,null,0)}</div>
    <div class="t2" style="font-size:13px;line-height:1.6">Распределение облигаций портфеля по рейтингу по национальной шкале (АКРА, Эксперт РА, НКР, НРА). Если у эмитента несколько оценок, берётся наименьшая.
      Пометка «≈» — название эмитента совпало не полностью, проверьте по подсказке. Нет данных — рейтинг не найден в базе, это не значит, что он низкий.
      <div class="row" style="margin-top:12px"><button class="btn ghost" id="rt-ref" ${info.running?'disabled':''}>Обновить рейтинги</button></div></div></div>
    <p class="note">Источник — публичный канал @issuerRatings (пресс-релизы агентств). Рейтинги обновляются автоматически раз в сутки при открытой программе. Не является инвестиционной рекомендацией.</p></div>`;
}


function bondInsights(b){
  const rows=b.rows.filter(r=>r.value_rub>0),tot=rows.reduce((a,r)=>a+r.value_rub,0)||1,out=[];
  const w=(f)=>rows.filter(f).reduce((a,r)=>a+r.value_rub,0)/tot*100;
  const sp=rows.filter(r=>r.spread!=null),spv=sp.reduce((a,r)=>a+r.value_rub,0);
  if(spv)out.push(['Спред к КБД',`В среднем портфель даёт <b>${(sp.reduce((a,r)=>a+r.spread*r.value_rub,0)/spv).toFixed(2).replace('.',',')} п.п.</b> к безрисковой кривой (КБД) при той же дюрации — это ваша плата за кредитный риск и неликвидность.`]);
  const low=sp.filter(r=>r.spread<0.5).sort((a,c)=>a.spread-c.spread);
  if(low.length)out.push(['Мало платят за риск',`Выше КБД менее чем на 0,5 п.п.: ${low.slice(0,4).map(r=>`${esc(r.name)} (${r.spread>0?'+':''}${r.spread.toFixed(2).replace('.',',')} п.п.)`).join(', ')}${low.length>4?' и ещё '+(low.length-4):''}. Проверьте, оправдан ли риск эмитента или выгоднее ОФЗ.`]);
  const nr=w(r=>!r.rating);if(nr>0.5)out.push(['Без рейтинга',`<b>${nr.toFixed(0)}%</b> облигационной части — выпуски без найденного рейтинга агентств (${rows.filter(r=>!r.rating).slice(0,3).map(r=>esc(r.name)).join(', ')}${rows.filter(r=>!r.rating).length>3?'…':''}). Рейтинга нет в базе — это не значит, что он низкий.`]);
  const weak=rows.filter(r=>r.rating&&RSC.indexOf(r.rating.v)>=7);
  if(weak.length)out.push(['Рейтинг ниже A−',`${weak.map(r=>`${esc(r.name)} (${esc(r.rating.v)})`).join(', ')} — суммарно <b>${w(r=>r.rating&&RSC.indexOf(r.rating.v)>=7).toFixed(0)}%</b> облигаций.`]);
  const hy=sp.filter(r=>r.spread>6);if(hy.length)out.push(['Очень высокая доходность',`Спред больше 6 п.п.: ${hy.map(r=>`${esc(r.name)} (+${r.spread.toFixed(1).replace('.',',')})`).join(', ')}. Рынок закладывает повышенный риск — перепроверьте эмитента.`]);
  const top=rows.slice().sort((a,c)=>c.value_rub-a.value_rub).slice(0,3);
  out.push(['Концентрация',`Три крупнейшие позиции — <b>${(top.reduce((a,r)=>a+r.value_rub,0)/tot*100).toFixed(0)}%</b> облигаций: ${top.map(r=>esc(r.name)).join(', ')}.`]);
  const soon=new Date(Date.now()+90*864e5).toISOString().slice(0,10),today=new Date().toISOString().slice(0,10);
  const ev=rows.filter(r=>(r.call&&r.call>=today&&r.call<=soon)||(r.maturity&&r.maturity>=today&&r.maturity<=soon));
  if(ev.length)out.push(['Ближайшие 90 дней',`Оферта или погашение: ${ev.map(r=>`${esc(r.name)} — ${ddm(r.call&&r.call>=today&&r.call<=soon?r.call:r.maturity)}${r.call&&r.call>=today&&r.call<=soon?' (оферта)':''}`).join('; ')}.`]);
  return out;
}
function insightsCard(b){
  const L=bondInsights(b);if(!L.length)return'';
  return`<div class="card"><h2>Анализ облигаций портфеля</h2><div class="ins">${L.map(([t,h])=>`<div><b>${t}</b><span>${h}</span></div>`).join('')}</div>
    <p class="note">Автоматические наблюдения по данным портфеля, рейтингов и КБД. Это справочная информация, а не инвестиционная рекомендация.</p></div>`;
}

/* ── Облигации ── */
function heatCell(v,mx,rgb,txt){if(bad(v))return'<td class="num mu">—</td>';const a=Math.max(0,Math.min(1,v/(mx||1)));return`<td class="num" style="background:rgba(${rgb},${(0.06+a*0.5).toFixed(3)})">${txt}</td>`}
function pBonds(){
  const b=S.bonds;
  if(!b)return`<div class="card">${waitBox('Загружаю параметры облигаций и графики купонов…')}</div>`;
  if(b.error)return`<div class="msg err">${esc(b.error)}</div>`;
  const m=b.metrics,tot=S.data.portfolio.total||1;
  if(!m.count)return'<div class="card empty">В портфеле нет облигаций</div>';
  let rows=b.rows.slice();rows.forEach(r=>r.rk=r.rating?RSC.indexOf(r.rating.v):null);const{k,d}=S.bsort;
  rows.sort((a,c)=>{const x=a[k],y=c[k];if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  const mxS=Math.max(...rows.map(r=>r.share||0)),mxY=Math.max(1,...rows.map(r=>Math.min(r.ytm||0,60))),mxD=Math.max(...rows.map(r=>r.dur||0));
  const cols=[['name','Облигация','l'],['qty','Кол-во'],['buy_pct','Покупка, %'],['price_pct','Цена, %'],['value_rub','Стоимость'],['pnl_rub','P&L'],['share','Доля'],['ytm','Доходность'],['ytm_tax','После НДФЛ'],['spread','Спред к КБД'],['dur','Дюрация'],['coupon','Купон'],['next','След. купон'],['maturity','Погашение'],['rk','Рейтинг','l'],['risk','Риск','l']];
  const th=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  const body=rows.map(r=>`<tr data-isin="${esc(r.isin||r.ticker||'')}"><td>${ident(r,[r.ticker,r.floating?(r.est_coupons?'флоатер · прогноз купонов':'флоатер'):'',r.amort?'амортизация':''].filter(Boolean).join(' · '))}</td>
    <td class="num">${f0(r.qty)}</td><td class="num">${r.buy_pct!=null?f2(r.buy_pct):'—'}</td><td class="num">${r.price_pct!=null?f2(r.price_pct):'—'}</td>
    <td class="num">${M(r.value_rub,'rub',0)}</td>
    <td class="num ${cls(r.pnl_rub)}"><span class="arr">${r.pnl_rub>0?'▲':r.pnl_rub<0?'▼':''}</span>${r.pnl_pct!=null?pct(r.pnl_pct,1):'—'}</td>
    ${heatCell(r.share,mxS,'201,133,0',pctp(r.share))}
    ${heatCell(r.ytm,mxY,'25,158,112',r.ytm!=null?pctp(r.ytm,2)+(r.to==='offer'?' <small class="mu">оф.</small>':'')+(r.cf_source==='approx'?' <small class="mu" title="Приблизительный расчёт: нет графика выплат MOEX">≈</small>':''):'—')}
    ${heatCell(r.ytm_tax,mxY,'25,158,112',r.ytm_tax!=null?pctp(r.ytm_tax,2):'—')}
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread)+' п.п.':'—'}</td>
    ${heatCell(r.dur,mxD,'213,81,129',r.dur!=null?r.dur.toFixed(2).replace('.',',')+' г':'—')}
    <td class="num">${r.coupon!=null?pctp(r.coupon,2):'—'}</td>
    <td class="num">${r.next?`${ddm(r.next[0])}<br><small class="mu">${M(r.next[1])}</small>`:'—'}</td>
    <td class="num">${r.maturity?ddm(r.maturity):'—'}${r.call?`<br><small class="mu">оферта ${ddm(r.call)}</small>`:''}</td>
    <td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td>
    <td class="l">${r.risk?`<span class="tag" style="${r.risk==='высокий'?'color:var(--neg)':r.risk==='низкий'?'color:var(--pos)':''}">${r.risk}</span>`:''}</td></tr>`).join('');
  const sk=['-3','-2','-1','1','2','3'],st=m.stress||{};
  chart('c-stress',bars,{h:220,labels:sk.map(x=>(x>0?'+':'−')+Math.abs(x)+' п.п.'),series:[{n:'Изменение стоимости',c:S3,v:sk.map(x=>(st[x]||{}).rub||0)}],legend:false,
    colorOf:v=>v>=0?'#19a070':'#d5524a',empty:'Нет данных для стресс-теста'});
  const hy=m.high_yield||[],kr=m.keyrate;
  chart('c-ladder',bars,{h:220,labels:b.ladder.map(x=>x[0]),series:[{n:'Погашается / оферта',c:S1,v:b.ladder.map(x=>x[1])}],legend:false});
  return`<div class="g g4">${kpi('Облигации',M(m.value,'rub',0),`${m.count} выпусков · ${m.issuers} эмитентов · ${pctp(m.value/tot*100)} портфеля`,null,S1)}
    ${kpi('Доходность портфеля (IRR)',pctp(m.irr,2),'что принесёт весь облигационный портфель, если все бумаги заплатят по графику: один IRR по суммарному денежному потоку к текущей стоимости с НКД','pos',S3)}
    ${kpi('IRR после НДФЛ',pctp(m.irr_tax,2),'то же после налога 13% на купоны и разницу к цене; без ЛДВ','pos',S3)}
    ${kpi('Средневзвешенная доходность',pctp(m.ytm,2),`среднее доходностей выпусков по стоимости, включая бумаги с доходностью выше 100%; после НДФЛ ${pctp(m.ytm_tax,2)}`,'pos',S3)}
    ${kpi('Модиф. дюрация',m.mdur!=null?m.mdur.toFixed(2).replace('.',',')+' г':'—','−1% к цене на +1 п.п. ставки ≈ 1 × мод. дюрация',null,S5)}
    ${kpi('Дюрация',m.dur!=null?m.dur.toFixed(2).replace('.',',')+' года':'—','средневзвешенная, по Маколею',null,S5)}
    ${kpi('Текущая купонная доходность',pctp(m.cur_yield,2),'годовой купон / цена',null,S4)}
    ${kpi('Купоны за 12 месяцев',M(m.coupons_12m,'rub',0),'по графику выплат, до налога','pos',S7)}</div>
    <div class="card" style="padding:12px 10px 6px"><div class="tbl" style="max-height:calc(100vh - 200px)"><table id="btab" class="bt"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div></div>
    <div class="g g3"><div class="card"><h2>Лестница погашений и оферт, ₽</h2><div id="c-ladder" class="chart"></div></div>
    <div class="card"><h2>Кредитный риск (оценка брокера)</h2>${hbars(b.risk.map(([n,v])=>({n,v,c:n==='высокий'?S8:n==='низкий'?S3:n==='средний'?S4:'#6f7686',s:pctp(v/(m.value||1)*100)})),S1,null,0)}</div>
    <div class="card"><h2>Тип купона, выпусков</h2>${hbars(b.kinds.map(([n,v],i)=>({n,v,c:PAL[i]})),S1,x=>f0(x.v),1)}</div></div>
    <div class="card"><h2>Стресс-тест ставок: изменение стоимости портфеля облигаций, ₽</h2><div id="c-stress" class="chart"></div>
      <div class="tbl"><table class="bt"><thead><tr><th class="l">Сдвиг ставок</th>${sk.map(x=>`<th>${x>0?'+':'−'}${Math.abs(x)} п.п.</th>`).join('')}</tr></thead><tbody>
      <tr><td class="l">Изменение, ₽</td>${sk.map(x=>`<td class="num ${cls((st[x]||{}).rub)}">${(st[x]||{}).rub!=null?M(st[x].rub,'rub',0):'—'}</td>`).join('')}</tr>
      <tr><td class="l">Изменение, %</td>${sk.map(x=>`<td class="num ${cls((st[x]||{}).pct)}">${(st[x]||{}).pct!=null?pct((st[x]||{}).pct,2):'—'}</td>`).join('')}</tr></tbody></table></div>
      <p class="note">Параллельный сдвиг доходностей всех выпусков с полной переоценкой по графику выплат (для выпусков без данных MOEX, помечены ≈, — по модиф. дюрации). Не учитывает изменения кредитных спредов.</p></div>
    ${ratingsCard(b)}
    ${insightsCard(b)}
    <p class="note">Доходность — эффективная годовая к погашению или к ближайшей оферте (пометка «оф.»), по текущей цене с НКД. Для флоатеров ещё не объявленные купоны оценены как ключевая ставка по прогнозу + спред эмитента (спред взят по последним известным купонам); MOEX считает по неизменному купону, поэтому доходности флоатеров здесь могут отличаться от биржевых. Дюрация — по Маколею, в годах. «После НДФЛ» — упрощённо: 13% с купонов и с положительной разницы между погашением и ценой покупки (без прогрессивной ставки 15% и ЛДВ). Пометка ≈ — график выплат MOEX недоступен, расчёт приблизительный.<br>IRR портфеля — единая ставка дисконтирования всех будущих выплат (купоны, амортизации, погашения и оферты, валютные выпуски по текущему курсу) к стоимости портфеля с НКД; по нему видно, сколько в итоге заработает вся «корзина». Средневзвешенная — просто среднее по выпускам. В обе цифры входят все выпуски без исключений.${hy.length?` Высокий риск дефолта (доходность выше 100%, ${M(m.high_yield_value,'rub',0)}): ${hy.map(o=>esc(o.name)+' '+pctp(o.ytm,0)).join(', ')} — такая ставка показывает цену риска, а не обещанный доход.`:''}${kr&&kr.source!=='none'?`<br>Прогноз ключевой ставки для флоатеров: ${esc(kr.name)}${kr.as_of?`, на ${esc(kr.as_of)}`:''}; сейчас ${kr.key_rate!=null?pctp(kr.key_rate,2):'—'}${(kr.yearly||[]).length?`, средняя по годам: ${kr.yearly.slice(0,4).map(y=>y.year+' — '+pctp(y.mid,1)).join(', ')}`:''}. Источник меняется в «Настройках».`:''}</p>`;
}



/* ── Первичные размещения ── */
S.pri=null;
function loadPri(){api('/api/primary').then(j=>{S.pri=j;if(S.page==='pri')render()}).catch(e=>{S.pri={error:e.message,rows:[]};if(S.page==='pri')render()})}
function pPri(){
  const d=S.pri;
  if(!d){loadPri();return`<div class="card">${waitBox('Загружаю календарь первичных размещений…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="pri-r">Повторить</button></div>`;
  const today=new Date().toISOString().slice(0,10),rows=d.rows;
  const wk=new Date(Date.now()+7*864e5).toISOString().slice(0,10);
  const body=rows.map(r=>`<tr class="${r.start===today?'pnew':''}"${r.isin?` data-isin="${esc(r.isin)}"`:''}><td class="l"><b>${esc(r.short||r.issuer)}</b><br><small class="mu">${esc(r.desc)}</small>${r.isin?`<br><small class="mu num">${esc(r.isin)}</small>`:''}</td>
    <td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td>
    <td class="num">${ddm(r.start)}${r.start===today?'<br><small class="pos">сегодня</small>':''}</td><td class="num">${esc(r.end.replace(' г.',''))}</td>
    <td class="l">${esc(r.book)}</td><td class="l">${r.link?`<a class="blue-link" href="${esc(r.link)}" target="_blank" rel="noopener">объявление Мосбиржи ↗</a>`:''}</td></tr>`).join('');
  return`<div class="g g4">${kpi('Размещений в списке',rows.length,'объявлено Мосбиржей')}${kpi('Сегодня',rows.filter(r=>r.start===today).length,'плановое начало размещения')}
    ${kpi('На этой неделе',rows.filter(r=>r.start>=today&&r.start<=wk).length,'начало в ближайшие 7 дней')}${kpi('С рейтингом',rows.filter(r=>r.rating).length,'эмитент найден в базе рейтингов')}</div>
  <div class="card" style="padding:12px 10px 6px"><div class="row" style="padding:0 6px 10px"><b>Календарь первичных размещений</b><button class="btn ghost" id="pri-r" style="margin-left:auto">Обновить</button></div>
    ${rows.length?`<div class="tbl"><table><thead><tr><th class="l">Эмитент и выпуск</th><th class="l">Рейтинг</th><th>Начало размещения</th><th>Окончание</th><th class="l">Книга заявок</th><th class="l">Источник</th></tr></thead><tbody>${body}</tbody></table></div>`:'<div class="empty">Объявленных размещений нет</div>'}</div>
  <p class="note">Даты начала размещения — по объявлениям Московской биржи (сводка investmint.ru). Ставку купона эмитент обычно объявляет в день сбора заявок: уточняйте её у брокера. Рейтинг сопоставлен с эмитентом по названию. Справочная информация, не инвестиционная рекомендация.</p>`;
}


/* ── Скринер облигаций ── */
S.scr=null;S.sf={q:'',cur:'RUB',kind:'all',sector:'',rmin:'',rated:false,ymin:'',ymax:'60',tmax:'',turn:'',spmin:'',noOffer:false};S.ssort={k:'yield',d:-1};S.sn=150;
function loadScr(){api('/api/screener').then(j=>{const t=Date.now();j.rows.forEach(r=>{r.years=(new Date(r.mat)-t)/315576e5});S.scr=j;if(S.page==='scr'||S.page==='map')render()}).catch(e=>{S.scr={error:e.message,rows:[]};if(S.page==='scr'||S.page==='map')render()})}
function scrRows(){
  const f=S.sf,q=f.q.trim().toLowerCase(),ri=f.rmin?RSC.indexOf(f.rmin):-1;
  const nv=x=>x===''||isNaN(parseFloat(x))?null:parseFloat(String(x).replace(',','.'));
  const ymin=nv(f.ymin),ymax=nv(f.ymax),tmax=nv(f.tmax),turn=nv(f.turn),spmin=nv(f.spmin);
  let rs=S.scr.rows.filter(r=>{
    if(f.cur!=='all'&&r.cur!==f.cur)return false;
    if(f.kind!=='all'&&r.kind!==f.kind)return false;
    if(q&&!((r.name||'').toLowerCase().includes(q)||(r.isin||'').toLowerCase().includes(q)||(r.full||'').toLowerCase().includes(q)))return false;
    if(ri>=0&&!(r.rating&&RSC.indexOf(r.rating)<=ri))return false;
    if(f.sector&&r.sector!==f.sector)return false;
    if(f.rated&&!r.rating)return false;
    if(ymin!=null&&r.yield<ymin)return false;if(ymax!=null&&r.yield>ymax)return false;
    if(tmax!=null&&r.years>tmax)return false;
    if(turn!=null&&r.turn<turn*1e6)return false;
    if(spmin!=null&&!(r.spread!=null&&r.spread>=spmin))return false;
    if(f.noOffer&&r.offer)return false;
    return r.years>0;
  });
  const{k,d}=S.ssort;
  rs.sort((a,b)=>{let x=a[k],y=b[k];if(k==='rating'){x=x?RSC.indexOf(x):null;y=y?RSC.indexOf(y):null;return -d*((x??99)-(y??99))}
    if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  return rs;
}
function drawScr(){
  const rs=scrRows(),n=Math.min(rs.length,S.sn),fl=S.scr.floor&&S.scr.floor.lqdt;
  const cols=[['_w','★','l'],['name','Выпуск','l'],['rating','Рейтинг','l'],['sector','Сектор','l'],['price','Цена, %'],['yield','Доходность'],['spread','Спред к КБД'],['coupon','Купон, %'],['years','До погашения'],['dur','Дюрация'],['turn','Оборот сегодня']];
  const {k,d}=S.ssort;
  $('#scr-head').innerHTML=cols.map(([kk,t,c])=>kk==='_w'?`<th class="wt-sth" title="Список наблюдения">${t}</th>`:`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  $('#scr-body').innerHTML=rs.slice(0,n).map(r=>`<tr${fl>0&&r.yield<fl?' class="scr-low" title="Доходность ниже, чем у фонда ликвидности"':''} data-isin="${esc(r.isin||r.id)}"><td class="wt-std">${watchStar(r.isin||r.id)}</td><td class="l"><b>${esc(r.name)}</b><br><small class="mu num">${esc(r.isin||r.id)}${r.offer?' · оферта '+ddm(r.offer):''}</small></td>
    <td class="l">${r.rating?`<span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}" title="${esc(r.rt_agency||'')}${r.rt_approx?' (приблизительное совпадение названия)':''}">${r.rt_approx?'≈ ':''}${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td>
    <td class="l">${r.sector?esc(SECT[r.sector]||r.sector):'<span class="mu">—</span>'}</td>
    <td class="num">${f2(r.price)}</td><td class="num"><b>${pctp(r.yield,2)}</b></td>
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread):'—'}</td>
    <td class="num">${r.coupon!=null?f2(r.coupon):'—'}</td><td class="num">${ddm(r.mat)}<br><small class="mu">${r.years.toFixed(1).replace('.',',')} г</small></td>
    <td class="num">${r.dur!=null?r.dur.toFixed(2).replace('.',','):'—'}</td><td class="num">${r.turn?short(r.turn):'—'}</td></tr>`).join('');
  $('#scr-cnt').textContent=`Найдено: ${rs.length}${rs.length>n?' · показано '+n:''}`;
  $('#scr-more').style.display=rs.length>n?'':'none';
}
function pScr(){
  const d=S.scr;
  if(!d){loadScr();return`<div class="card">${waitBox('Загружаю торги облигациями с Мосбиржи и сопоставляю рейтинги…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="scr-r">Повторить</button></div>`;
  const f=S.sf,opt=(v,t,cur)=>`<option value="${v}" ${cur===v?'selected':''}>${t}</option>`;
  const fl0=d.floor&&d.floor.lqdt,flN=fl0>0?`<p class="note scr-fl">Фонд ликвидности сейчас даёт ≈ ${f2(fl0)} % годовых — у бумаг ниже этой доходности нет премии за риск (такие строки приглушены). Доходность до налогов; не инвестиционная рекомендация.</p>`:'';
  const rated=d.rows.filter(r=>r.rating).length,sectors=[...new Set(d.rows.map(r=>r.sector).filter(Boolean))].sort((a,b)=>(SECT[a]||a).localeCompare(SECT[b]||b));
  return`<div class="card"><h2>Подбор облигаций<span class="sp" id="scr-cnt"></span></h2>
    <div class="flt">
    <label class="field"><span>Поиск</span><input class="in" id="f-q" value="${esc(f.q)}" placeholder="название или ISIN"></label>
    <label class="field"><span>Валюта</span><select class="in" id="f-cur">${opt('RUB','Рубли',f.cur)}${opt('all','Все',f.cur)}${opt('USD','USD',f.cur)}${opt('CNY','CNY',f.cur)}${opt('EUR','EUR',f.cur)}</select></label>
    <label class="field"><span>Тип</span><select class="in" id="f-kind">${opt('all','Все',f.kind)}${opt('corp','Корпоративные',f.kind)}${opt('ofz','ОФЗ',f.kind)}</select></label>
    ${sectors.length?`<label class="field"><span>Сектор</span><select class="in" id="f-sector"><option value="">любой</option>${sectors.map(x=>opt(x,SECT[x]||x,f.sector)).join('')}</select></label>`:''}
    <label class="field"><span>Рейтинг не ниже</span><select class="in" id="f-rmin"><option value="">любой</option>${RSC.slice(0,10).map(x=>opt(x,x,f.rmin)).join('')}</select></label>
    <label class="field"><span>Доходность от, %</span><input class="in num" id="f-ymin" value="${esc(f.ymin)}" inputmode="decimal"></label>
    <label class="field"><span>Доходность до, %</span><input class="in num" id="f-ymax" value="${esc(f.ymax)}" inputmode="decimal"></label>
    <label class="field"><span>Спред к КБД от, п.п.</span><input class="in num" id="f-spmin" value="${esc(f.spmin)}" inputmode="decimal"></label>
    <label class="field"><span>До погашения, лет не более</span><input class="in num" id="f-tmax" value="${esc(f.tmax)}" inputmode="decimal"></label>
    <label class="field"><span>Оборот за день от, млн ₽</span><input class="in num" id="f-turn" value="${esc(f.turn)}" inputmode="decimal"></label>
    <label class="sw"><input type="checkbox" id="f-noffer" ${f.noOffer?'checked':''}><i></i><div><b>Без оферт</b></div></label>
    <button class="btn ghost" id="f-reset">Сбросить</button></div>
    ${flN}
    <div class="tbl" style="max-height:calc(100vh - 300px)"><table><thead><tr id="scr-head"></tr></thead><tbody id="scr-body"></tbody></table></div>
    <div class="row" style="margin-top:12px"><button class="btn ghost" id="scr-more">Показать ещё</button></div></div>
  <p class="note">Данные — Московская биржа (ISS, режимы торгов Т+ для корпоративных облигаций и ОФЗ; с задержкой, как в бесплатном доступе). Доходность — по цене последних торгов, спред — к кривой КБД при той же дюрации. Рейтинг найден у ${rated} из ${d.rows.length} выпусков: эмитенты без рейтинга в базе не обязательно ненадёжны. По умолчанию скрыты выпуски с доходностью выше 60% (обычно это дефолтные или почти не торгуемые бумаги) — поле «Доходность до» можно очистить. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function bindScr(){
  if(!S.scr||S.scr.error){const b=$('#scr-r');if(b)b.onclick=()=>{S.scr=null;render()};return}
  const map={'f-q':'q','f-cur':'cur','f-kind':'kind','f-sector':'sector','f-rmin':'rmin','f-ymin':'ymin','f-ymax':'ymax','f-spmin':'spmin','f-tmax':'tmax','f-turn':'turn'};
  let to;Object.entries(map).forEach(([id,k])=>{const e=$('#'+id);if(!e)return;e.oninput=e.onchange=()=>{S.sf[k]=e.value;S.sn=150;clearTimeout(to);to=setTimeout(drawScr,150)}});
  $('#f-noffer').onchange=e=>{S.sf.noOffer=e.target.checked;S.sn=150;drawScr()};
  $('#f-reset').onclick=()=>{S.sf={q:'',cur:'RUB',kind:'all',sector:'',rmin:'',rated:false,ymin:'',ymax:'60',tmax:'',turn:'',spmin:'',noOffer:false};render()};
  $('#scr-more').onclick=()=>{S.sn+=200;drawScr()};
  $('#scr-head').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;S.ssort={k,d:S.ssort.k===k?-S.ssort.d:(['name'].includes(k)?1:-1)};drawScr()};
  drawScr();
}

/* ── Выплаты по дням (столбики с разбивкой по выпускам) ── */
const colAt=i=>i<HEX.length?HEX[i]:`hsl(${(i*137.5)%360},55%,52%)`;
function dayBars(el,o){
  const days=o.days,H=o.h||340,pl=64,pt=26,pb=64,step=62,n=days.length;
  if(!n)return emptyChart(el,H,'Выплат в выбранном периоде нет');
  const mx=Math.max(...days.map(d=>d.total)),{lo,hi,step:ys}=nice(0,mx),ph=H-pt-pb,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  let ax='',grid='';
  for(let v=lo;v<=hi+ys/2;v+=ys){const y=Y(v);ax+=`<text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${v===0?'0':short(v)}</text>`;grid+=`<line class="grid-l" x1="0" x2="100000" y1="${y}" y2="${y}"/>`}
  ax+=`<text class="ax" transform="translate(14 ${pt+ph/2}) rotate(-90)" text-anchor="middle">Сумма выплат, ₽</text>`;
  const bw=Math.min(40,step*.62);let marks='',lab='',hits='';
  days.forEach((d,i)=>{const cx=step*i+step/2;let acc=0;
    d.items.forEach((it,k)=>{const y1=Y(acc+it.amount),y0=Y(acc),h=Math.max(0,y0-y1-(k?1:0));
      marks+=`<path class="bm" data-g="${i}" d="${k===d.items.length-1?rtop(cx-bw/2,y1,bw,h,4):`M${cx-bw/2},${y1}h${bw}v${h}h${-bw}Z`}" fill="${it.c}"${it.kind==='dividend'?'':''}/>`;acc+=it.amount});
    lab+=`<text class="ax num" x="${cx}" y="${Y(d.total)-7}" text-anchor="middle" style="fill:var(--tx);font-weight:600">${short(d.total)}</text>`;
    lab+=`<text class="ax" transform="translate(${cx+4} ${H-pb+14}) rotate(-45)" text-anchor="end">${d.label}</text>`;
    hits+=`<rect data-i="${i}" x="${step*i}" y="${pt}" width="${step}" height="${ph}" fill="transparent"/>`});
  const W=Math.max(step*n,el.clientWidth-pl-4);
  el.innerHTML=`<div class="dwrap"><svg width="${pl}" height="${H}" style="flex:none">${ax}</svg><div class="dscroll"><svg width="${W}" height="${H}">${grid}<g>${marks}</g>${lab}${hits}</svg></div></div>
    <div class="lg2">${o.legend.map(l=>`<span><i style="background:${l.c}"></i>${esc(l.n)}${l.tag?` <em>${l.tag}</em>`:''}</span>`).join('')}</div>`;
  const mk=el.querySelectorAll('.bm');el._hl=i=>mk.forEach(p=>p.style.opacity=i<0||+p.dataset.g===i?1:.35);
  bindTip(el,i=>{const d=days[i];return`<b>${esc(d.full)}</b>`+d.items.map(it=>tipRow(it.c,it.name+' · '+it.kl,M(it.amount))).join('')+
    `<div style="border-top:1px solid var(--line2);padding-top:5px;margin-top:6px">Итого<span>${M(d.total)}</span></div>`});
}
function payDays(ps,limit){
  const to=new Date(Date.now()+limit*864e5).toISOString().slice(0,10),from=new Date().toISOString().slice(0,10);
  const f=ps.filter(p=>p.date>=from&&p.date<=to);
  const tot={};f.forEach(p=>tot[p.name]=(tot[p.name]||0)+p.amount);
  const names=Object.keys(tot).sort((a,b)=>tot[b]-tot[a]),col={};names.forEach((n,i)=>col[n]=colAt(i));
  const red=new Set(f.filter(p=>p.kind==='redemption').map(p=>p.name)),amo=new Set(f.filter(p=>p.kind==='amortization').map(p=>p.name));
  const KL={coupon:'купон',dividend:'дивиденд',redemption:'погашение',amortization:'амортизация'},by={};
  f.forEach(p=>(by[p.date]=by[p.date]||[]).push(p));
  const days=Object.keys(by).sort().map(dt=>{const items=by[dt].slice().sort((a,b)=>tot[b.name]-tot[a.name]).map(p=>({name:p.name,amount:p.amount,c:col[p.name],kind:p.kind,kl:KL[p.kind]||p.kind}));
    const [y,m,d]=dt.split('-');return{label:`${d}.${m}.${y}`,full:ddm(dt),total:items.reduce((a,x)=>a+x.amount,0),items}});
  return{days,legend:names.map(n=>({n,c:col[n],tag:[red.has(n)?'погашение':'',amo.has(n)?'амортизация':''].filter(Boolean).join(', ')}))};
}

/* ── Выплаты ── */
function pPay(){
  const b=S.bonds;
  if(!b)return`<div class="card">${waitBox('Собираю графики купонов и объявленные дивиденды…')}</div>`;
  if(b.error)return`<div class="msg err">${esc(b.error)}</div>`;
  const ps=b.payments,now=new Date(),in30=new Date(now.getTime()+30*864e5).toISOString().slice(0,10);
  const sum=f=>ps.filter(f).reduce((a,x)=>a+x.amount,0);
  const pm=payMonths(ps,12);
  const pdd=payDays(ps,S.payDays);chart('c-days',dayBars,{days:pdd.days,legend:pdd.legend,h:340});
  chart('c-pay',bars,{h:260,labels:pm.labels,tipLabels:pm.tips,stack:true,total:true,skipZero:true,series:pm.series,empty:'Выплат не ожидается'});
  const KIND={coupon:['Купон',S1],dividend:['Дивиденд',S3],redemption:['Погашение',S4],amortization:['Амортизация',S5]};
  const byM={};ps.forEach(p=>(byM[p.date.slice(0,7)]=byM[p.date.slice(0,7)]||[]).push(p));
  const list=Object.keys(byM).sort().map(m=>{const[y,mm]=m.split('-');const t=byM[m].reduce((a,x)=>a+x.amount,0);
    return`<div class="card"><h2>${MONF[+mm-1]} ${y}<span class="sp num" style="color:var(--pos);font-size:13px;font-weight:600">${M(t)}</span></h2><div class="li">`+
    byM[m].map(p=>`<div class="it">${logo(p,34)}<div><b>${esc(p.name)}</b><small>${ddm(p.date)} · <span style="color:${KIND[p.kind][1]}">${KIND[p.kind][0]}</span>${p.est==='forecast'?' · прогноз по ключевой ставке':p.est?' · оценка':''}</small></div><div class="rv num">${M(p.amount)}</div></div>`).join('')+`</div></div>`}).join('');
  return`<div class="g g4">${kpi('Ближайшие 30 дней',M(sum(p=>p.date<=in30)),'',null,S1)}${kpi('За 12 месяцев',M(sum(()=>1)),'купоны, дивиденды, амортизации и погашения','pos',S3)}
    ${kpi('Купоны',M(sum(p=>p.kind==='coupon')),ps.filter(p=>p.kind==='coupon').length+' выплат',null,S1)}${kpi('Дивиденды',M(sum(p=>p.kind==='dividend')),'только объявленные, до налога',null,S3)}</div>
    <div class="card"><h2>Календарь выплат по месяцам, ₽</h2><div id="c-pay" class="chart"></div></div>
    <div class="card"><h2>Выплаты по дням<span class="sp"><span class="seg" id="pdays">${[[30,'30 дней'],[90,'90 дней'],[365,'Год']].map(([d,t])=>`<button data-d="${d}" class="${d===S.payDays?'on':''}">${t}</button>`).join('')}</span></span></h2><div id="c-days" class="chart"></div></div>
    ${list?`<div class="g g2">${list}</div>`:'<div class="card empty">Выплат в ближайший год не ожидается</div>'}
    <p class="note">Купоны — по графику эмитента и текущему количеству бумаг (до НДФЛ). Для флоатеров ещё не объявленные купоны — прогноз по ключевой ставке ЦБ плюс спред эмитента (пометка «прогноз по ключевой ставке»). Амортизации — частичное погашение номинала по графику Мосбиржи. Дивиденды — только уже объявленные, сумма до налога.</p>`;
}

/* ── Операции ── */
const KINDS=[['','Все'],['trade','Сделки'],['income','Доходы'],['fees','Комиссии'],['tax','Налоги'],['cash','Пополнения и выводы']];
const KMAP={trade:['buy','sell'],income:['dividends','coupons','repayments','overnight'],fees:['fee_broker','fee_service','fee_other','margin_fee','varmargin'],tax:TAXK,cash:['deposits','withdrawals']};
const OPN={BUY:'Покупка',SELL:'Продажа',BUY_CARD:'Покупка',SELL_CARD:'Продажа',BUY_MARGIN:'Покупка (маржа)',SELL_MARGIN:'Продажа (маржа)',DIVIDEND:'Дивиденды',COUPON:'Купон',
  BOND_REPAYMENT:'Амортизация',BOND_REPAYMENT_FULL:'Погашение',BROKER_FEE:'Комиссия брокера',SERVICE_FEE:'Обслуживание',MARGIN_FEE:'Плата за маржу',TAX:'НДФЛ',
  DIVIDEND_TAX:'Налог с дивидендов',BOND_TAX:'Налог с купона',INPUT:'Пополнение',OUTPUT:'Вывод',INP_MULTI:'Перевод между счетами',OUT_MULTI:'Перевод между счетами',
  OVERNIGHT:'Доход по РЕПО',ACCRUING_VARMARGIN:'Вар. маржа',WRITING_OFF_VARMARGIN:'Вар. маржа',TAX_CORRECTION:'Возврат налога',INPUT_SECURITIES:'Зачисление бумаг',OUTPUT_SECURITIES:'Списание бумаг'};
function opsFiltered(){
  const q=S.opsQ.toLowerCase(),ks=KMAP[S.opsK];
  return S.data.ops.filter(o=>(!ks||ks.includes(o[2]))&&(!q||(o[1]+' '+(OPN[o[1]]||'')+' '+o[3]+' '+o[4]+' '+o[12]).toLowerCase().includes(q)));
}
function pOps(){
  return`<div class="card"><div class="row" style="margin-bottom:14px">
    <input class="in" id="oq" placeholder="Поиск: название, тикер, тип операции…" value="${esc(S.opsQ)}" style="flex:1;min-width:240px">
    <div class="seg" id="ok">${KINDS.map(([k,t])=>`<button class="${k===S.opsK?'on':''}" data-k="${k}">${t}</button>`).join('')}</div>
    <a class="btn ghost" style="text-decoration:none" href="/api/operations.csv?${new URLSearchParams({period:S.period,account:S.account})}">${svgI('<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',2)}CSV</a></div>
    <div id="otab"></div></div>`;
}
function drawOps(){
  const all=opsFiltered(),rows=all.slice(0,S.opsN),el=$('#otab');if(!el)return;
  if(!all.length){el.innerHTML='<div class="empty">Операций не найдено</div>';return}
  const multi=S.account==='all';
  el.innerHTML=`<p class="note" style="margin-bottom:8px">Найдено: ${f0(all.length)}</p><div class="tbl" style="max-height:calc(100vh - 290px)"><table><thead><tr>
    <th>Дата</th><th class="l">Операция</th><th class="l">Инструмент</th>${multi?'<th class="l">Счёт</th>':''}<th>Кол-во</th><th>Цена</th><th>Сумма</th><th>Комиссия</th><th>Результат</th></tr></thead><tbody>`+
    rows.map(o=>`<tr><td class="num t2">${esc(o[0])}</td><td class="l"><span class="tag">${esc(OPN[o[1]]||o[1])}</span></td>
    <td class="l" style="max-width:380px">${o[3]||o[4]?`<div class="tk">${logo({name:o[3],ticker:o[4],logo:o[11]},24)}<div><b style="font-weight:550">${esc(o[3]||o[4])}</b></div></div>`:''}</td>
    ${multi?`<td class="l t2" style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(o[12])}</td>`:''}
    <td class="num">${o[5]||''}</td><td class="num">${o[6]?f2(o[6]):''}</td><td class="num ${cls(o[7])}">${SM(o[7],o[8])}</td><td class="num mu">${o[9]?f2(o[9]):''}</td><td class="num ${cls(o[10])}">${o[10]?SM(o[10],o[8]):''}</td></tr>`).join('')+
    `</tbody></table>${all.length>rows.length?`<div class="more"><button class="btn ghost" id="omore">Показать ещё (${f0(all.length-rows.length)})</button></div>`:''}</div>`;
  const m=$('#omore');if(m)m.onclick=()=>{S.opsN+=500;drawOps()};
}

/* ── Комиссии ── */
function pFees(){
  const d=S.data;let out='';
  const t=T(),total=sumK(t,FEEK),turn=(t.buy_turnover||0)+(t.sell_turnover||0);
  out+=`<div class="g g4">${kpi('Все комиссии и плата за маржу',M(total),periodName(),null,S2)}${kpi('Комиссия брокера',M(t.fee_broker||0),turn?`${f2((t.fee_broker||0)/turn*100)} % от оборота ${short(turn)} ₽`:'',null,S1)}
    ${kpi('Обслуживание + прочее',M((t.fee_service||0)+(t.fee_other||0)),'тариф, вывод, прочие сборы',null,S3)}${kpi('Плата за маржу',M(t.margin_fee||0),'перенос непокрытых позиций',null,S5)}</div>`;
  const items=[['fee_broker',S1],['fee_service',S3],['fee_other',S4],['margin_fee',S5]];
  const ms=monthsSeries();
  chart('c-fees',bars,{labels:ms.labels,tipLabels:ms.tips,stack:true,total:true,skipZero:true,series:items.map(([k,c])=>({n:L[k],c,v:ms.rows.map(r=>r[k]||0)}))});
  out+=`<div class="g c-2-1"><div class="card"><h2>Комиссии по месяцам, ₽<span class="sp">${periodName()}</span></h2><div id="c-fees" class="chart"></div></div>
    <div class="card"><h2>Структура расходов, ₽</h2>${total?hbars(items.filter(([k])=>t[k]).map(([k,c])=>({n:L[k],v:t[k]||0,c,s:pctp((t[k]||0)/total*100)})),S1,null,1):'<div class="empty">Комиссий нет</div>'}
    <p class="note" style="margin-top:16px">Положительная сумма — уплачено, возвраты её уменьшают.</p></div></div>`;
  const other=Object.keys(d.totals).filter(c=>c!=='rub'&&FEEK.some(k=>d.totals[c][k]));
  if(other.length)out+=`<div class="card"><h2>Комиссии в других валютах</h2><table><thead><tr><th>Статья</th>${other.map(c=>`<th>${sym(c)}</th>`).join('')}</tr></thead><tbody>`+
    FEEK.map(k=>`<tr><td>${L[k]}</td>${other.map(c=>`<td class="num">${M(d.totals[c][k]||0,c)}</td>`).join('')}</tr>`).join('')+'</tbody></table></div>';
  return out;
}

/* ── Налоги ── */
function pTax(){
  const d=S.data,lf=d.life,rows=d.tax,cy=new Date().getFullYear(),cur=rows.find(r=>r.year===cy);
  const withheld=sumK(lf,TAXK);
  let out=`<div class="g g4">${kpi('Удержано налогов за всё время',M(withheld),'НДФЛ, удержанный брокером',null,S4)}
    ${kpi(`Оценка НДФЛ за ${cy}`,cur?M(cur.estimate):'—',cur?`база ${short(Math.max(0,cur.trade)+cur.income)} ₽`:'нет дохода',null,S1)}
    ${kpi(`Удержано в ${cy}`,cur?M(cur.withheld):'—','по операциям этого года',null,S3)}
    ${kpi('Ожидается к удержанию',cur?M(Math.max(0,cur.diff)):'—',cur&&cur.diff<0?'удержано больше оценки':'при выводе или в конце года',cur&&cur.diff>0?'neg':'',S2)}</div>`;
  chart('c-tax',bars,{labels:rows.map(r=>String(r.year)),series:[{n:'Оценка НДФЛ',c:S1,v:rows.map(r=>r.estimate)},{n:'Удержано брокером',c:S2,v:rows.map(r=>r.withheld)}]});
  out+=`<div class="g c-1-2"><div class="card"><h2>Удержанные налоги по видам</h2>${withheld?hbars(TAXK.filter(k=>lf[k]).map((k,i)=>({n:L[k],v:lf[k],c:PAL[i]})),S1,null,1):'<div class="empty">Налоги не удерживались</div>'}</div>
    <div class="card"><h2>Оценка и факт по годам, ₽</h2><div id="c-tax" class="chart"></div></div></div>`;
  out+=`<div class="card" style="padding:6px 8px"><div class="tbl"><table><thead><tr><th>Год</th><th>Результат сделок</th><th>Дивиденды, купоны, РЕПО</th><th>Налоговая база</th><th>Оценка НДФЛ</th><th>Удержано</th><th>Разница</th></tr></thead><tbody>`+
    (rows.length?rows.slice().reverse().map(r=>`<tr><td><b>${r.year}</b></td><td class="num ${cls(r.trade)}">${SM(r.trade)}</td><td class="num">${M(r.income)}</td><td class="num">${M(Math.max(0,r.trade)+r.income)}</td>
    <td class="num">${M(r.estimate)}</td><td class="num">${M(r.withheld)}</td><td class="num ${r.diff>0.5?'neg':r.diff<-0.5?'pos':''}">${SM(r.diff)}</td></tr>`).join(''):'<tr><td colspan="7" class="l mu">Нет данных</td></tr>')+
    `</tbody></table></div></div><p class="note"><b>Это оценка, а не декларация.</b> Ставка: 13 %; с 2021 по 2024 — 15 % с части базы свыше 5 млн ₽; с 2025 — 15 % свыше 2,4 млн ₽.
    База: положительный результат продаж + дивиденды + купоны + доход по РЕПО в рублях. Не учтены убытки прошлых лет, льгота долгосрочного владения, ИИС, иностранные дивиденды и курсовые разницы. Точные суммы рассчитывает брокер как налоговый агент.</p>`;
  return out;
}

/* ── Импорт ── */
const ROLE_RU={date:'Дата',type:'Тип операции',isin:'ISIN',ticker:'Тикер',name:'Название / описание',qty:'Количество',price:'Цена',amount:'Сумма',currency:'Валюта',commission:'Комиссия',nkd:'НКД'};
async function renderImport(){
  S.charts=[];
  let cfg;try{cfg=await api('/api/config');S.cfg=cfg}catch(e){$('#view').innerHTML=`<div class="wrap"><div class="msg err">${esc(e.message)}</div></div>`;return}
  const im=S.imp;
  const imps=cfg.imports||[];
  let step='';
  if(im&&im.preview){
    const pv=im.preview,opts=['<option value="">—</option>'].concat(pv.header.map((h,i)=>`<option value="${i}">${esc(h||('Колонка '+(i+1)))}</option>`)).join('');
    step=`<div class="card fade"><h2>2. Проверьте колонки<span class="sp">${esc(im.filename)} · строк: ${f0(pv.rows)}</span></h2>
      <div class="map">${Object.keys(ROLE_RU).map(r=>`<label class="field"><span>${ROLE_RU[r]}${['date','amount'].includes(r)?' *':''}</span><select class="in" data-role="${r}">${opts}</select></label>`).join('')}</div>
      <p class="note" style="margin:10px 0">Обязательны дата и сумма (или количество и цена). Тип операции определяется по словам: «покупка», «продажа», «купон», «дивиденд», «погашение», «комиссия», «НДФЛ», «пополнение», «вывод». Если колонки «Тип» нет — по описанию и знаку суммы.</p>
      <div class="tbl" style="max-height:260px;border:1px solid var(--line)"><table><thead><tr>${pv.header.map(h=>`<th class="l">${esc(h)}</th>`).join('')}</tr></thead><tbody>${pv.sample.slice(0,8).map(r=>`<tr>${pv.header.map((_,i)=>`<td class="l t2">${esc(r[i]??'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <div class="row" style="margin-top:14px"><button class="btn ghost" id="iparse">Проверить разбор</button></div><div id="iresult" style="margin-top:14px"></div></div>`;
  }
  $('#view').innerHTML=`<div class="wrap fade" style="max-width:1100px">
    <div id="imsg"></div>
    <div class="card"><h2>1. Загрузите отчёт другого брокера</h2>
      <div class="drop" id="drop"><input type="file" id="ifile" accept=".csv,.txt,.xlsx,.xlsm,.html,.htm,.xls" style="display:none">
        ${svgI('<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>',1.6).replace('<svg','<svg style="width:34px;height:34px;opacity:.7"')}
        <div style="margin-top:8px;font-weight:600">Перетащите файл сюда или нажмите, чтобы выбрать</div>
        <div class="note" style="margin-top:4px">CSV, Excel (.xlsx) или HTML-отчёт брокера — Сбер, ВТБ, Альфа, БКС, Финам и др.</div></div>
      <div class="g g3" style="margin-top:16px;gap:12px">
        <label class="field"><span>Куда загрузить</span><select class="in" id="itarget"><option value="">Новый счёт</option>${imps.map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('')}</select></label>
        <label class="field"><span>Название счёта</span><input class="in" id="iname" placeholder="Например: Сбер ИИС" value="${esc(im&&im.name||'')}"></label>
        <label class="field"><span>Брокер</span><input class="in" id="ibroker" placeholder="Сбер, ВТБ, БКС…" value="${esc(im&&im.broker||'')}"></label></div>
      <p class="note" style="margin-top:12px">Лучше всего подходит выгрузка всех операций (сделки + движение денег) за всё время. Если формат не распознаётся — заполните <a href="/api/import/template.csv" style="color:var(--ac)">шаблон CSV</a>. Бумаги находятся по ISIN или тикеру через API Т-Инвестиций, чтобы подтянуть текущие цены, названия, логотипы и купоны. Данные сохраняются только в локальной базе.</p></div>
    ${step}
    <div class="card"><h2>Импортированные счета</h2>${imps.length?`<div class="li">${imps.map(x=>`<div class="it">${logo({name:x.name,ticker:x.name},34)}<div><b>${esc(x.name)}</b><small>${esc(x.broker||'')} · файлов: ${x.files.length} · операций: ${f0(x.files.reduce((a,f)=>a+f.count,0))}</small></div>
      <div class="row"><button class="btn ghost" data-open="${esc(x.id)}">Открыть</button><button class="btn danger" data-del="${esc(x.id)}">Удалить</button></div></div>`).join('')}</div>`:'<div class="empty" style="padding:20px">Пока ничего не импортировано</div>'}</div></div>`;
  const msg=(t,k)=>{$('#imsg').innerHTML=t?`<div class="msg ${k||'err'}">${t}</div>`:''};
  const drop=$('#drop'),inp=$('#ifile');
  drop.onclick=()=>inp.click();
  drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};drop.ondragleave=()=>drop.classList.remove('over');
  drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');if(e.dataTransfer.files[0])pick(e.dataTransfer.files[0])};
  inp.onchange=()=>{if(inp.files[0])pick(inp.files[0])};
  async function pick(f){
    if(f.size>60*1024*1024)return msg('Файл больше 60 МБ.');
    msg('Читаю файл…','info');
    const data=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]||'');r.onerror=rej;r.readAsDataURL(f)});
    try{const pv=await post('/api/import/preview',{filename:f.name,data});
      S.imp={filename:f.name,data,preview:pv,mapping:pv.mapping,name:$('#iname').value||f.name.replace(/\.[^.]+$/,''),broker:$('#ibroker').value};msg('');renderImport()}
    catch(e){msg(esc(e.message))}
  }
  if(im&&im.preview){
    document.querySelectorAll('[data-role]').forEach(s=>{const v=im.mapping[s.dataset.role];s.value=v==null?'':String(v);s.onchange=()=>{im.mapping[s.dataset.role]=s.value===''?null:+s.value}});
    const req=()=>({filename:im.filename,data:im.data,table:im.preview.table,header_row:im.preview.header_row,mapping:im.mapping});
    $('#iparse').onclick=async e=>{const b=e.currentTarget;b.disabled=true;
      try{const r=await post('/api/import/parse',req());const K={buy:'покупок',sell:'продаж',coupons:'купонов',dividends:'дивидендов',deposits:'пополнений',withdrawals:'выводов',fee_broker:'комиссий',tax_trade:'налогов',repayments:'погашений',fee_service:'обслуживание',margin_fee:'маржа'};
        $('#iresult').innerHTML=`<div class="msg ${r.count?'ok':'err'}">Распознано операций: <b>${r.count}</b>${r.skipped?`, пропущено строк: ${r.skipped}`:''}${r.from?` · с ${ddm(r.from)} по ${ddm(r.to)}`:''}<br>${Object.entries(r.kinds).map(([k,v])=>`${K[k]||k}: ${v}`).join(' · ')}</div>
          <div class="tbl" style="margin-top:10px;border:1px solid var(--line)"><table><thead><tr><th class="l">Дата</th><th class="l">Тип</th><th class="l">Инструмент</th><th>Кол-во</th><th>Сумма</th></tr></thead><tbody>${r.sample.map(x=>`<tr><td class="l">${ddm(x[0])}</td><td class="l"><span class="tag">${esc(OPN[x[1]]||x[1])}</span></td><td class="l">${esc(x[2])}</td><td class="num">${x[3]||''}</td><td class="num ${cls(x[4])}">${SM(x[4],x[5])}</td></tr>`).join('')}</tbody></table></div>
          ${r.count?'<div class="row" style="margin-top:14px"><button class="btn" id="icommit">Импортировать</button><span class="note">Бумаги будут найдены через API Т-Инвестиций — это займёт несколько секунд.</span></div>':''}`;
        const c=$('#icommit');if(c)c.onclick=async ev=>{const bb=ev.currentTarget;bb.disabled=true;bb.textContent='Импортирую…';
          try{const res=await post('/api/import/commit',{...req(),name:$('#iname').value||im.name,broker:$('#ibroker').value,target:$('#itarget').value});
            S.imp=null;S.account=res.id;S.data=S.bonds=S.hist=null;persist();
            await renderImport();msg(`Импортировано операций: ${res.count}. Бумаг найдено на бирже: ${res.resolved} из ${res.idents}.`,'ok');load(true)}
          catch(err){bb.disabled=false;bb.textContent='Импортировать';msg(esc(err.message))}}}
      catch(err){$('#iresult').innerHTML=`<div class="msg err">${esc(err.message)}</div>`}finally{b.disabled=false}};
  }
  document.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{if(!confirm('Удалить импортированный счёт и его операции из локальной базы?'))return;
    await post('/api/import/delete',{id:b.dataset.del});if(S.account===b.dataset.del)S.account='all';S.data=S.bonds=S.hist=null;persist();renderImport();load(true)});
  document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{S.account=b.dataset.open;S.bonds=S.hist=null;persist();S.page='dash';renderNav();load(false)});
}

/* ── Настройки ── */
async function renderSettings(){
  S.charts=[];
  try{S.cfg=await api('/api/config')}catch(e){$('#view').innerHTML=`<div class="wrap"><div class="msg err">${esc(e.message)}</div></div>`;return}
  const c=S.cfg;
  $('#view').innerHTML=`<div class="wrap fade" style="max-width:820px">
  ${!c.token_set?`<div class="card hero" style="display:block"><div class="val" style="font-size:24px">Добро пожаловать 👋</div><p class="t2" style="margin-top:8px;position:relative;z-index:1">Вставьте API-токен Т-Инвестиций, чтобы увидеть аналитику, или импортируйте отчёт другого брокера. Всё хранится только на этом компьютере.</p></div>`:''}
  <div id="msg"></div>
  <div class="card"><h2>Подключение к Т-Инвестициям</h2><div style="display:grid;gap:18px">
    <label class="field"><span>API-токен ${c.token_set?`<span class="pos">· сохранён (…${esc(c.token_hint.slice(1))}). Оставьте пустым, чтобы не менять</span>`:''}</span>
      <input class="in" type="password" id="tok" placeholder="t.XXXXXXXXXXXXXXXXXXXX" autocomplete="off" spellcheck="false"></label>
    <label class="sw"><input type="checkbox" id="sb" ${c.sandbox?'checked':''}><i></i><div><b>Режим песочницы</b><small>Токен песочницы работает только с этим режимом, боевой — только без него</small></div></label>
    <div class="row"><button class="btn" id="save">Сохранить и подключиться</button><button class="btn ghost" id="test">Проверить</button>
      ${c.token_set?'<button class="btn danger" id="clr">Удалить токен</button>':''}</div>
    <p class="note">Токен выпускается в приложении Т-Инвестиции: Настройки → Токены T-Invest API. Для аналитики достаточно токена «Только для чтения».</p></div></div>
  ${c.sandbox&&c.token_set?`<div class="card"><h2>Песочница</h2><div style="display:grid;gap:14px"><div class="row"><button class="btn ghost" id="sbopen">Открыть новый счёт</button>
    <input class="in num" type="number" id="amt" value="1000000" min="1" step="1000" style="width:160px"><button class="btn ghost" id="sbpay">Пополнить выбранный счёт, ₽</button></div>
    <p class="note">Песочница — виртуальный счёт без реальных данных: сначала он пуст.</p></div></div>`:''}
  <div class="card"><h2>Локальные данные</h2><p class="note" style="margin-bottom:12px">Операции, история цен, справочник бумаг и логотипы хранятся в базе на этом компьютере: <span class="mono">${esc(c.data_dir)}</span>. При обновлении догружаются только новые данные.</p>
    <div class="row"><button class="btn ghost" id="cache">Перезагрузить всё из API</button><a class="btn ghost" href="/api/backup" download>Скачать резервную копию</a></div>
    <p class="note" style="margin-top:10px">Резервная копия — zip с базой и настройками. Токен в неё не входит.</p></div>
  <div class="card"><h2>Оформление и напоминания</h2><div style="display:grid;gap:16px">
    <div class="row"><div class="seg" id="thsel">${[['auto','Авто'],['light','Светлая'],['dark','Тёмная']].map(([k,t])=>`<button data-t="${k}" class="${curTheme()===k?'on':''}">${t}</button>`).join('')}</div></div>
    <div class="row"><label class="field" style="max-width:260px"><span>Напоминать о выплатах за, дней (0 — выключить)</span><input class="in num" id="nd" type="number" min="0" max="60" value="${c.notify_days??7}"></label>
      <button class="btn ghost" id="ndsave" style="align-self:flex-end">Сохранить</button><button class="btn ghost" id="ntf" style="align-self:flex-end">Разрешить системные уведомления</button></div>
    <p class="note">Напоминания показываются на «Обзоре» и «Выплатах», а системные уведомления приходят, пока программа открыта. Печать отчёта: кнопка PDF сверху → «Сохранить как PDF» (печатается текущий раздел и период).</p></div></div>
  <div class="card"><h2>Прогноз ключевой ставки<span class="sp">для флоатеров</span></h2><div style="display:grid;gap:14px">
    <div class="row"><label class="field" style="max-width:420px"><span>Источник прогноза</span><select class="in" id="krmode">${[['cbr','Прогноз Банка России (по умолчанию)'],['survey','Опрос аналитиков Банка России'],['market','Рынок: форварды КБД'],['flat','Без изменений (текущая ставка)']].map(([k,t])=>`<option value="${k}" ${(c.keyrate_mode||'cbr')===k?'selected':''}>${t}</option>`).join('')}</select></label>
      <button class="btn ghost" id="krsave" style="align-self:flex-end">Сохранить</button></div>
    <p class="note" id="krinfo">Загружаю…</p>
    <p class="note">Ставка ещё не объявленных купонов флоатера = ключевая ставка на начало купонного периода + спред эмитента (по последним известным купонам). «Прогноз Банка России» — среднесрочный прогноз ЦБ (середина диапазона средней ставки за год), «Опрос» — медиана макроопроса аналитиков, «КБД» — форвардные ставки кривой за вычетом срочной премии (грубо), «Без изменений» — текущая ставка. Если выбранный источник недоступен, берётся следующий по списку.</p></div></div>
  ${setTgHtml(c)}${setBackupHtml(c)}
  <div class="card" id="whatsnew"><h2>Что нового<span class="sp">версия ${esc(c.version||'')}</span></h2>${changelogHtml()}</div>
  <div class="card"><h2>Роадмап<span class="sp">что планируется</span></h2>${roadmapHtml()}</div>
  <details class="card"><summary style="cursor:pointer;font-weight:600;color:var(--tx2)">Дополнительно</summary><div style="display:grid;gap:18px;margin-top:16px">
    <label class="field"><span>Адреса REST API (боевой), по одному в строке</span><textarea class="in" id="hp" rows="2">${esc(c.hosts_prod.join('\n'))}</textarea></label>
    <label class="field"><span>Адреса REST API (песочница)</span><textarea class="in" id="hs" rows="2">${esc(c.hosts_sandbox.join('\n'))}</textarea></label>
    <label class="field"><span>Дополнительный файл сертификата (обычно не нужен: сертификат Минцифры уже встроен в программу)</span><input class="in" id="ca" value="${esc(c.ca_file)}" placeholder="/path/to/cert.pem"></label>
    <label class="sw"><input type="checkbox" id="vs" ${c.verify_ssl?'checked':''}><i></i><div><b>Проверять SSL-сертификат</b><small>Отключайте только для отладки</small></div></label>
    <div class="row"><button class="btn ghost" id="save2">Сохранить</button></div></div></details></div>`;
  const msg=(t,ok)=>{$('#msg').innerHTML=`<div class="msg ${ok?'ok':'err'}">${esc(t)}</div>`};
  $('#thsel').onclick=e=>{const b=e.target.closest('[data-t]');if(!b)return;applyTheme(b.dataset.t);post('/api/config',{theme:b.dataset.t}).catch(()=>{});$('#thsel').querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b))};
  const krShow=async()=>{try{const k=await api('/api/keyrate');$('#krinfo').innerHTML=k.source==='none'?'Прогноз сейчас недоступен: купоны флоатеров считаются по последней известной ставке.':`Сейчас используется: <b>${esc(k.name)}</b>${k.as_of?`, на ${esc(k.as_of)}`:''}${k.mode!==k.source?` (выбранный источник «${esc(k.mode)}» недоступен)`:''}. Ключевая ставка сейчас ${pctp(k.key_rate,2)}; средняя по годам: ${(k.yearly||[]).slice(0,4).map(y=>y.year+' — '+pctp(y.mid,1)).join(', ')}.`}catch(e){$('#krinfo').textContent='Не удалось получить прогноз: '+e.message}};
  krShow();
  $('#krsave').onclick=async()=>{try{$('#krinfo').textContent='Загружаю…';await post('/api/config',{keyrate_mode:$('#krmode').value});S.cfg.keyrate_mode=$('#krmode').value;S.bonds=null;msg('Сохранено. Доходности облигаций пересчитаются при следующем открытии раздела.',1);krShow()}catch(e){msg(e.message)}};
  $('#ndsave').onclick=async()=>{try{await post('/api/config',{notify_days:$('#nd').value});S.cfg.notify_days=+$('#nd').value;msg('Сохранено',1)}catch(e){msg(e.message)}};
  $('#ntf').onclick=async()=>{try{if(!('Notification' in window))return msg('Браузер не поддерживает уведомления');const r=await Notification.requestPermission();msg(r==='granted'?'Уведомления разрешены':'Уведомления не разрешены',r==='granted')}catch(e){msg(e.message)}};
  try{bindSetTg(c,msg)}catch(e){}
  try{bindSetBackup(c,msg)}catch(e){}
  const body=()=>({token:$('#tok').value,sandbox:$('#sb').checked,verify_ssl:$('#vs').checked,ca_file:$('#ca').value,
    hosts_prod:$('#hp').value.split('\n'),hosts_sandbox:$('#hs').value.split('\n')});
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const reset=()=>{S.data=S.bonds=S.hist=null;S.account='all';persist()};
  $('#save').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());const r=await post('/api/test');reset();
    msg(`Подключено. Счетов: ${r.accounts}.`,1);S.page='dash';persist();renderNav();load(true)});
  $('#save2').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());reset();msg('Сохранено.',1);load(true)});
  $('#test').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());const r=await post('/api/test');msg(`Подключение работает. Счетов: ${r.accounts}.`,1)});
  $('#cache').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/cache/clear');reset();msg('Локальный кэш очищен, данные загрузятся заново.',1);load(true)});
  if($('#clr'))$('#clr').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Удалить сохранённый токен?'))return;await post('/api/config',{clear_token:true});reset();renderSettings()});
  if($('#sbopen'))$('#sbopen').onclick=e=>busy(e.currentTarget,async()=>{const r=await post('/api/sandbox/open');S.account=r.accountId;persist();S.data=null;msg('Открыт счёт '+r.accountId,1);load(true)});
  if($('#sbpay'))$('#sbpay').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/sandbox/payin',{accountId:S.account,amount:$('#amt').value});S.data=S.bonds=S.hist=null;msg('Счёт пополнен на '+M(+$('#amt').value,'rub',0),1);load(true)});
}



/* ── тема, печать ── */
function themeNow(t){return t==='auto'?(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'):t}
function applyTheme(t){try{localStorage.setItem('ta_theme',t)}catch(e){}document.documentElement.dataset.theme=themeNow(t);if(S.cfg)S.cfg.theme=t}
function curTheme(){let t='auto';try{t=localStorage.getItem('ta_theme')||(S.cfg&&S.cfg.theme)||'auto'}catch(e){}return t}
$('#thm').onclick=()=>{const n={auto:'light',light:'dark',dark:'auto'}[curTheme()]||'auto';applyTheme(n);post('/api/config',{theme:n}).catch(()=>{});if(S.data)render()};
$('#pdf').onclick=()=>window.print();
let _prevTheme=null;
window.addEventListener('beforeprint',()=>{_prevTheme=document.documentElement.dataset.theme;document.documentElement.dataset.theme='light'});
window.addEventListener('afterprint',()=>{if(_prevTheme)document.documentElement.dataset.theme=_prevTheme});
function prInfo(){const a=S.accounts.find(x=>x.id===S.account),pg=(PAGES.find(p=>p&&p[0]===S.page)||[])[1]||'';
  const per=PAGES&&PERIOD_PAGES.includes(S.page)?((PERIODS.find(x=>x[0]===S.period)||[])[1]||''):'';
  $('#prinfo').textContent=['T-Invest Analytics',pg,S.account==='all'?'все счета':(a?a.name:''),per,new Date().toLocaleDateString('ru-RU')].filter(Boolean).join(' · ')}

/* ── напоминания о выплатах ── */
function upcoming(){
  const n=S.cfg&&S.cfg.notify_days!=null?+S.cfg.notify_days:7,b=S.bonds;if(!n||!b||b.error)return[];
  const from=new Date().toISOString().slice(0,10),to=new Date(Date.now()+n*864e5).toISOString().slice(0,10);
  const ev=(b.payments||[]).filter(p=>p.date>=from&&p.date<=to).map(p=>({date:p.date,name:p.name,kind:p.kind,amount:p.amount}));
  (b.rows||[]).forEach(r=>{if(r.call&&r.call>=from&&r.call<=to)ev.push({date:r.call,name:r.name,kind:'offer',amount:null})});
  return ev.sort((a,c)=>a.date.localeCompare(c.date));
}
const EVK={coupon:'купон',dividend:'дивиденд',redemption:'погашение',amortization:'амортизация',offer:'оферта'};
function remindHtml(){
  const ev=upcoming();if(!ev.length)return'';
  return`<div class="card remind noprint"><div>${svgI(IC.pay,1.8).replace('<svg','<svg width="22" height="22"')}</div><div><b>Ближайшие события (${ev.length})</b>
    ${ev.slice(0,6).map(e=>`<small>${ddm(e.date)} · ${EVK[e.kind]||e.kind} · ${esc(e.name)}${e.amount!=null?' · '+M(e.amount):''}</small>`).join('')}
    ${ev.length>6?`<small>…и ещё ${ev.length-6}</small>`:''}</div></div>`;
}
function notifyUpcoming(){
  try{monEnsure()}catch(e){}
  try{
    if(!('Notification' in window)||Notification.permission!=='granted')return;
    const seen=new Set(JSON.parse(lsGet('ta_notified')||'[]'));
    upcoming().forEach(e=>{const k=e.date+'|'+e.kind+'|'+e.name;if(seen.has(k))return;seen.add(k);
      new Notification('T-Invest: '+(EVK[e.kind]||e.kind)+' '+ddm(e.date),{body:e.name+(e.amount!=null?' · '+M(e.amount):'')})});
    localStorage.setItem('ta_notified',JSON.stringify([...seen].slice(-300)));
  }catch(e){}
}


function notifyMon(d){
  try{
    if(!('Notification' in window)||Notification.permission!=='granted')return;
    const seen=new Set(JSON.parse(lsGet('ta_notified')||'[]'));
    (d.alerts||[]).filter(a=>a.severity==='high').forEach(a=>{const k='mon|'+a.id;if(seen.has(k))return;seen.add(k);
      new Notification('T-Invest: тревога по '+(a.name||'облигации'),{body:a.message})});
    localStorage.setItem('ta_notified',JSON.stringify([...seen].slice(-300)));
  }catch(e){}
}
/* ── Ставки: КБД и ключевая ставка ── */
S.ratesDays=365;S.rates=null;
const RDAYS=[[90,'3 мес'],[180,'6 мес'],[365,'Год'],[730,'2 года']];
function loadRates(){
  const d=S.ratesDays;
  api('/api/rates?days='+d).then(j=>{if(d!==S.ratesDays)return;S.rates=j;if(S.page==='mkt')render();if(j.loading)setTimeout(()=>{if(S.page==='mkt'&&d===S.ratesDays)loadRates()},3000)})
   .catch(e=>{S.rates={error:e.message,labels:[]};if(S.page==='mkt')render()});
}
const pc1=v=>v==null?'—':(+v).toFixed(2).replace(/0$/,'').replace(/\.0$/,'').replace('.',',')+'%';
function pMkt(){
  const r=S.rates;
  if(!r){loadRates();return`<div class="card">${waitBox('Загружаю кривую доходности и ключевую ставку…')}</div>`}
  if(r.error)return`<div class="msg err">${esc(r.error)}</div>`;
  const n=r.labels.length,i0=n-1;
  const seg=`<div class="seg" id="rdays">${RDAYS.map(([d,t])=>`<button data-d="${d}" class="${d===S.ratesDays?'on':''}">${t}</button>`).join('')}</div>`;
  if(n<2)return`<div class="card">${r.loading?waitBox('Загружаю историю КБД с Мосбиржи — первый раз это занимает до минуты…'):'<div class="empty">Нет данных. Проверьте подключение к интернету.</div>'}</div>`;
  const lastK=r.kbd[i0],lastC=r.key[i0],first=r.kbd[0];
  chart('c-rates',line,{h:360,zero:false,labels:r.labels,fa:v=>(+v).toFixed(1).replace('.',',')+'%',ft:v=>pc1(v),
    series:[{n:'КБД · 2 года',c:'#2f6df6',hex:'#2f6df6',v:r.kbd,w:2.2},{n:'Ключевая ставка',c:'#3f7a4f',hex:'#3f7a4f',v:r.key,w:2.4,step:true}],
    hover:i=>{const e=$('#rstrip');if(e)e.innerHTML=stripHtml(r,i)},leave:()=>{const e=$('#rstrip');if(e)e.innerHTML=stripHtml(r,i0)}});
  return`<div class="g g4">${kpi('КБД · 2 года',pc1(lastK),'доходность гособлигаций, '+r.labels[i0],null,'#2f6df6')}${kpi('Ключевая ставка',pc1(lastC),'Банк России',null,'#3f7a4f')}
    ${kpi('КБД − ключевая',lastC!=null?((lastK-lastC>0?'+':'')+(lastK-lastC).toFixed(2).replace('.',',')+' п.п.'):'—','рынок закладывает '+(lastK>lastC?'повышение / удержание':'снижение')+' ставки',lastK>lastC?'neg':'pos')}
    ${kpi('КБД за период',((lastK-first>0?'+':'')+(lastK-first).toFixed(2).replace('.',',')+' п.п.'),'с '+r.labels[0],lastK-first>0?'neg':'pos')}</div>
  <div class="card rates"><h2>Доходность КБД (2 года) и ключевая ставка<span class="sp">${seg}</span></h2>
    <div class="axt">Ставка, % годовых</div><div id="c-rates" class="chart"></div><div class="axt" style="text-align:center">Дата</div>
    <div class="strip" id="rstrip">${stripHtml(r,i0)}</div>${r.loading?'<p class="note">Догружаю историю…</p>':''}</div>
  <p class="note">КБД — кривая бескупонной доходности ОФЗ Московской биржи (срок 2 года), ключевая ставка — Банка России. Данные берутся с сайтов Мосбиржи и ЦБ при открытой программе и сохраняются локально. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function stripHtml(r,i){return`<b>${r.labels[i]}</b><span>КБД · 2 года: <b>${pc1(r.kbd[i])}</b></span><span>КС: <b>${pc1(r.key[i])}</b></span>`}

/* ── Ребалансировка ── */
S.reb={contrib:'',buyOnly:true,draft:null};S.payDays=90;
function pReb(){
  const ps=S.data.portfolio.positions,tot=ps.reduce((a,x)=>a+(x.value_rub||0),0);
  if(!(tot>0))return'<div class="card empty">В портфеле нет активов для расчёта</div>';
  const cur={};ps.forEach(x=>{const t=x.type||'other';cur[t]=(cur[t]||0)+(x.value_rub||0)});
  if(!S.reb.draft)S.reb.draft=Object.assign({},(S.cfg&&S.cfg.targets)||{});
  const tg=S.reb.draft;
  const keys=[...new Set([...Object.keys(cur),...Object.keys(tg)])].sort((a,b)=>(cur[b]||0)-(cur[a]||0));
  const sumT=keys.reduce((a,k)=>a+(+tg[k]||0),0),has=sumT>0;
  const C=Math.max(0,+S.reb.contrib||0),T2=tot+C,buyOnly=S.reb.buyOnly;
  const w=k=>has?(+tg[k]||0)/sumT:0;
  let act={};
  if(has){
    if(buyOnly){const need={};keys.forEach(k=>{need[k]=Math.max(0,T2*w(k)-(cur[k]||0))});const sp=keys.reduce((a,k)=>a+need[k],0);
      keys.forEach(k=>{act[k]=C>0&&sp>0?need[k]*C/sp:0})}
    else keys.forEach(k=>{act[k]=T2*w(k)-(cur[k]||0)});
  }
  const need0=has?Math.max(0,Math.max(...keys.filter(k=>w(k)>0).map(k=>(cur[k]||0)/w(k)))-tot):0;
  const after=k=>((cur[k]||0)+(act[k]||0))/(buyOnly?T2:T2);
  const rows=keys.map(k=>{const cp=(cur[k]||0)/tot*100,tp=has?w(k)*100:0,dv=cp-tp,a=act[k]||0;
    return`<tr><td class="l"><b>${esc(TYPES[k]||(k==='other'?'Прочее':k))}</b></td><td class="num">${M(cur[k]||0)}</td><td class="num">${pctp(cp)}</td>
      <td class="num"><input class="in num reb-in" data-k="${esc(k)}" type="number" min="0" max="100" step="0.5" value="${tg[k]!=null?tg[k]:''}" placeholder="0"> %</td>
      <td class="num ${has?(Math.abs(dv)<0.5?'mu':dv>0?'neg':'pos'):'mu'}">${has?(dv>0?'+':'')+dv.toFixed(1).replace('.',',')+' п.п.':'—'}</td>
      <td class="num ${a>0.5?'pos':a<-0.5?'neg':'mu'}">${Math.abs(a)<1?'—':(a>0?'Докупить ':'Продать ')+M(Math.abs(a))}</td>
      <td class="num">${has?pctp(after(k)*100):'—'}</td></tr>`}).join('');
  const dev=has?keys.reduce((a,k)=>a+Math.abs((cur[k]||0)/tot-w(k)),0)/2*100:0;
  return`<div class="g g4">${kpi('Стоимость портфеля',M(tot),'по текущим ценам')}${kpi('Сумма целей',`<span class="${!has?'mu':Math.abs(sumT-100)<0.05?'pos':'neg'}">${sumT.toFixed(1).replace('.',',')} %</span>`,!has?'введите целевые доли ниже':Math.abs(sumT-100)<0.05?'цели заданы':'расчёт нормирован к 100%')}
    ${kpi('Отклонение от целей',has?pctp(dev):'—','сколько % портфеля стоит «не там»',has&&dev>5?'neg':'')}${kpi('Без продаж нужно внести',has?M(need0):'—','чтобы выйти на цели одними покупками')}</div>
  <div class="card"><h2>Целевая структура по классам активов</h2>
    <div class="row" style="margin-bottom:14px;gap:18px;flex-wrap:wrap"><label class="field" style="max-width:240px"><span>Новый взнос, ₽ (необязательно)</span><input class="in num" id="rb-c" type="number" min="0" step="1000" value="${S.reb.contrib}" placeholder="0"></label>
      <label class="sw"><input type="checkbox" id="rb-b" ${buyOnly?'checked':''}><i></i><div><b>Только докупать</b><small>Ничего не продавать, распределить взнос</small></div></label></div>
    <div class="tbl"><table><thead><tr><th class="l">Класс</th><th>Сейчас, ₽</th><th>Сейчас</th><th>Цель</th><th>Отклонение</th><th>Действие</th><th>После</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="row" style="margin-top:14px"><button class="btn" id="rb-s">Сохранить цели</button><button class="btn ghost" id="rb-r">Сбросить</button><span class="reb-sum" id="rb-sum"></span></div></div>
  <p class="note">Расчёт по классам активов (акции, облигации, фонды, валюта…) на уровне портфеля, без учёта комиссий, налогов и лотности. Это справочный расчёт, а не инвестиционная рекомендация. Цели сохраняются локально.</p>`;
}
function bindReb(){
  const d=S.reb.draft;
  $('#view').querySelectorAll('.reb-in').forEach(i=>i.onchange=()=>{const v=parseFloat(String(i.value).replace(',','.'));if(v>0)d[i.dataset.k]=Math.min(100,v);else delete d[i.dataset.k];render()});
  $('#rb-c').onchange=e=>{S.reb.contrib=e.target.value;render()};
  $('#rb-b').onchange=e=>{S.reb.buyOnly=e.target.checked;render()};
  $('#rb-r').onclick=()=>{S.reb.draft=null;S.reb.contrib='';render()};
  $('#rb-s').onclick=async e=>{e.currentTarget.disabled=true;try{await post('/api/config',{targets:d});S.cfg.targets=Object.assign({},d);$('#rb-sum').textContent='Сохранено'}catch(x){$('#rb-sum').textContent=x.message}finally{e.currentTarget.disabled=false}};
}

/* ── список обновлений и роадмап ── */
const CHANGELOG=[
 ['0.12','11.11.2026',['<b>«Сравнение с рынком»</b>: портфель против индексов облигаций Мосбиржи (ОФЗ, корпоративные, ВДО), фондов ликвидности и облигационных фондов; «те же деньги в те же дни» в рублях; волатильность, просадка, коэффициент Шарпа, бета; ликвидность позиций и премия к фонду ликвидности','<b>«Калькулятор»</b> инвестиций: пополнения, реинвест купонов с округлением до лотов, налоги 13/15 %, ИИС-А, ИИС-Б, ИИС-3 и ЛДВ, инфляция по прогнозу ЦБ, сценарии ключевой ставки, ожидаемые потери от дефолтов, сравнение стратегий и расчёт цели «пассивный доход в месяц»','<b>«Оферты»</b>: держать, предъявить к выкупу или продать на бирже — с учётом нового купона и доходности аналогов','<b>«Лесенка облигаций»</b>: подбор бумаг под сумму, срок и минимальный рейтинг с графиком выплат','Дюрационный разрыв и <b>реальная доходность</b> (за вычетом инфляции) в «Рисках и сценариях»','Флоатеры и амортизации в <b>календаре выплат</b> — по прогнозу ключевой ставки','Линия фонда ликвидности на карте рынка и в скринере','Быстрый повторный запуск: данные открываются сразу и обновляются в фоне; автотесты расчётов']],
 ['0.11','11.11.2026',['<b>«Риски и сценарии»</b>: вероятность дефолта по рынку и по рейтингу, ожидаемая доходность с учётом дефолтов, «казино» — что если не заплатят 1–3 самых рискованных эмитента, сценарии ключевой ставки на год, флоатеры против фикса, точка безубыточности','<b>«Сигналы»</b>: что на рынке дешевле и дороже аналогов (z-оценка, дни подряд) и возможные замены бумаг портфеля с учётом комиссии и налога','<b>«Мониторинг»</b>: тревоги по понижениям рейтингов, «под наблюдением», техническим дефолтам, падению цены, расширению спреда и офертам; журнал рейтинговых действий; ликвидность позиций; тревоги на «Обзоре» и в уведомлениях','<b>Кривая эмитента</b> в карточке облигации — все выпуски эмитента на одном графике']],
 ['0.10','11.11.2026',['<b>Доходность портфеля (IRR)</b> по всем будущим выплатам всех облигаций — высокорисковые бумаги учитываются, а не исключаются','<b>Флоатеры по прогнозу ключевой ставки</b>: среднесрочный прогноз Банка России (или опрос аналитиков, рынок, текущая ставка — выбор в настройках) плюс спред эмитента']],
 ['0.9','11.11.2026',['<b>Точный расчёт облигаций</b>: денежный поток с Мосбиржи с амортизациями и офертами — доходность совпадает с биржевой; исправлены валютные облигации','<b>Доходность после НДФЛ</b>, модифицированная дюрация, выпуклость и <b>стресс-тест</b> портфеля на ±1–3 п.п.','<b>Карточка облигации</b> по клику: параметры, история цены и доходности, денежный поток, рейтинги и <b>аналоги</b> по рейтингу, отрасли, дюрации и типу купона с оценкой «дешевле/дороже аналогов»','<b>Карта рынка</b>: доходность против дюрации по рейтингам на фоне КБД, медианные спреды по рейтингам, срокам и отраслям','Рейтинги по ISIN из каталога Т-Инвестиций — точнее и для большего числа выпусков; отрасль и фильтр по ней в скринере']],
 ['0.8','10.11.2026',['<b>Скринер облигаций</b> — торги Мосбиржи с фильтрами по рейтингу, доходности, спреду к КБД, сроку и обороту','<b>Первичка</b> — календарь объявленных размещений облигаций с рейтингами эмитентов','<b>Анализ облигаций портфеля</b>: спред к КБД по каждому выпуску, наблюдения по риску, концентрации и ближайшим офертам','Рейтинги теперь берутся ещё и напрямую с сайтов НКР и Эксперт РА (по эмитентам портфеля)']],
 ['0.7','10.11.2026',['<b>Кредитные рейтинги</b> эмитентов (АКРА, Эксперт РА, НКР, НРА) в таблице облигаций и распределение портфеля по рейтингам; данные подтягиваются автоматически из канала @issuerRatings раз в сутки','Раздел <b>«Ставки»</b>: доходность КБД (2 года) и ключевая ставка Банка России на одном графике','<b>«Выплаты по дням»</b>: столбики по датам с разбивкой по выпускам, подписями сумм и прокруткой']],
 ['0.6','10.11.2026',['<b>«Ребалансировка»</b> — целевые доли по классам активов, что докупить или продать, распределение нового взноса','<b>Светлая тема</b> (авто / светлая / тёмная) и <b>мобильный вид</b>','<b>Напоминания</b> о купонах, дивидендах, офертах и погашениях — на «Обзоре» и системными уведомлениями','<b>Отчёт в PDF</b> — кнопка «PDF» печатает текущий раздел и период в светлой теме','<b>Резервная копия</b> базы одним файлом (без токена) в «Настройках»']],
 ['0.5','10.11.2026',['В настройках появились <b>«Что нового»</b> и <b>роадмап</b> — сюда вносятся все изменения','Номер версии внизу боковой панели, по клику открывает список обновлений']],
 ['0.4','10.11.2026',['<b>«Все счета»</b> — сводная аналитика по всем счетам, включая импортированные','Переключатель <b>«скрыть пустые»</b> счета','Везде <b>названия бумаг</b> вместо ISIN и <b>логотипы эмитентов</b> (кэшируются локально)',
   'Раздел <b>«Доходность»</b>: история стоимости по дням, доходность без влияния пополнений, сравнение с LQDT и индексом МосБиржи (TMOS), просадка, таблица «год × месяц»',
   'Раздел <b>«Облигации»</b>: доходность к погашению/оферте, дюрация, купон, доля с цветовой заливкой, лестница погашений, кредитный риск',
   'Раздел <b>«Выплаты»</b>: календарь купонов, дивидендов и погашений на 12 месяцев','В «Позициях» — секторы, концентрация, фильтр по типу бумаг',
   '<b>Импорт отчётов</b> других брокеров: CSV, Excel, HTML, авто-распознавание колонок, шаблон CSV','Все данные — в локальной базе SQLite, из API догружается только новое']],
 ['0.3','10.11.2026',['Встроен корневой сертификат Минцифры — ничего не нужно устанавливать в систему','Python с python.org на Mac работает без доп. настройки сертификатов']],
 ['0.2','10.11.2026',['Всё в <b>одном файле</b>, открывается отдельным окном приложения','Новый тёмный дизайн и графики','Кэш операций на диске, параллельная загрузка','Исправлены ставки НДФЛ с 2025 года и расчёт XIRR при выводах']],
 ['0.1','10.11.2026',['Первая версия: портфель, операции, комиссии, налоги, настройки токена']],
];
const ROADMAP=[
 ['now','Проверка на реальных счетах','Сверка расчётов доходности и налогов с данными брокера'],
 ['next','Готовые форматы брокеров','Пресеты для отчётов Сбера, ВТБ, Альфы, БКС и Финама — без ручной настройки колонок'],
 ['next','Налоги точнее','Перенос убытков прошлых лет, ЛДВ и ИИС по фактическим сделкам, курсовые разницы'],
 ['next','Финансы эмитентов','Долговая нагрузка и покрытие процентов по отчётности — для оценки риска'],
 ['later','Первичка против вторички','Как новые выпуски торгуются после размещения — статистика копится с установки'],
 ['later','Зашифрованная копия в облаке','Автоматическая зашифрованная копия базы'],
 ['done','Сравнение с рынком','Индексы облигаций, фонды ликвидности и облигационные фонды; ликвидность и премия за риск'],
 ['done','Калькулятор инвестиций','Реинвест, налоги и ИИС, инфляция, сценарии ставки, цель по пассивному доходу'],
 ['done','Решение по оферте','Держать или предъявить к выкупу: новый купон против цен аналогов'],
 ['done','Конструктор облигационной лестницы','Подбор бумаг под сумму, срок и рейтинг с графиком выплат'],
 ['done','Реальная доходность и дюрационный разрыв','Доходность за вычетом инфляции по прогнозу ЦБ; совпадение сроков с вашей целью'],
 ['done','Флоатеры в календаре выплат','Купоны флоатеров в «Выплатах» по прогнозу ключевой ставки'],
 ['done','Риски и сценарии','Вероятность дефолта, ожидаемая доходность, сценарии ключевой ставки, флоатеры против фикса'],
 ['done','Сигналы и замены','Дешевле и дороже аналогов по всему рынку, возможные замены в портфеле'],
 ['done','Мониторинг и тревоги','Рейтинговые действия, технические дефолты, падение цены, спред, оферты, ликвидность'],
 ['done','Доходность портфеля и флоатеры','IRR по всем бумагам, купоны флоатеров по прогнозу ЦБ'],
 ['done','Точный расчёт и амортизации','Денежный поток с Мосбиржи, доходность после НДФЛ, стресс-тест ставок'],
 ['done','Карточка облигации и аналоги','Параметры, история, денежный поток и похожие выпуски по рейтингу, отрасли и сроку'],
 ['done','Карта рынка','Доходность против дюрации по рейтингам и медианные спреды к КБД'],
 ['done','Скринер облигаций','Подбор выпусков по рейтингу, доходности, спреду к КБД, сроку и ликвидности'],
 ['done','Первичка','Календарь объявленных размещений облигаций с рейтингами эмитентов'],
 ['done','Анализ облигаций','Спред к КБД, рейтинги, концентрация и ближайшие оферты по портфелю'],
 ['done','Кредитные рейтинги','Рейтинги АКРА, Эксперт РА, НКР и НРА рядом с облигациями, распределение по рейтингам, автообновление'],
 ['done','Ставки','График доходности КБД (2 года) и ключевой ставки'],
 ['done','Выплаты по дням','Столбчатый календарь выплат с разбивкой по выпускам'],
 ['done','Лаунчер с автообновлением','Маленький скрипт сам скачивает свежую версию программы с GitHub и проверяет контрольную сумму'],
 ['done','Целевые доли и ребалансировка','Раздел «Ребалансировка»: целевая структура, что докупить или продать, распределение взноса'],
 ['done','Уведомления','Напоминания о купонах, дивидендах, офертах и погашениях — в приложении и системные'],
 ['done','Отчёт в PDF','Кнопка «PDF»: печать текущего раздела и периода в светлой теме'],
 ['done','Резервная копия базы','Файл-архив с базой и настройками (без токена) в «Настройках»'],
 ['done','Светлая тема и мобильный вид','Авто / светлая / тёмная тема и адаптивная вёрстка для телефона'],
];
function changelogHtml(){return`<div class="cl">${CHANGELOG.map(([v,d,items])=>`<div><div class="vh"><b>Версия ${v}</b><span>${d}</span></div><ul>${items.map(i=>`<li>${i}</li>`).join('')}</ul></div>`).join('')}</div>`}
function roadmapHtml(){const L={now:['s-now','Сейчас'],next:['s-next','Следующее'],later:['s-later','Позже'],done:['s-done','Готово']};
  return`<div class="rm">${ROADMAP.map(([s,t,d])=>`<div><em class="${L[s][0]}">${L[s][1]}</em><span><b style="font-weight:600">${t}</b><small>${d}</small></span></div>`).join('')}</div>`}

function bindPage(){
  if(S.page==='reb')bindReb();
  if(S.page==='scr')bindScr();
  if(S.page==='risk')bindRisk();
  if(S.page==='mon')bindMon();
  if(S.page==='bench')bindBench();
  if(S.page==='calc')bindCalc();
  if(S.page==='off')bindOff();
  if(S.page==='lad')bindLad();
  if(S.page==='iss')bindIss();
  if(S.page==='cal')bindCal();
  if(S.page==='watch')bindWatch();
  if($('#pri-r'))$('#pri-r').onclick=()=>{S.pri=null;render()};
  if($('#pdays'))$('#pdays').onclick=e=>{const b=e.target.closest('[data-d]');if(!b)return;S.payDays=+b.dataset.d;render()};
  if($('#rdays'))$('#rdays').onclick=e=>{const b=e.target.closest('[data-d]');if(!b)return;S.ratesDays=+b.dataset.d;S.rates=null;render()};
  if($('#rt-ref'))$('#rt-ref').onclick=async e=>{e.currentTarget.disabled=true;try{await post('/api/ratings/refresh');S.bonds=await api('/api/bonds?'+new URLSearchParams({account:S.account}));render()}catch(x){}};
  document.querySelectorAll('#view [data-go]').forEach(b=>b.onclick=()=>go(b.dataset.go));
  const sortable=(id,key)=>{const t=$(id);if(t)t.querySelector('thead').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;
    S[key]={k,d:S[key].k===k?-S[key].d:(['name','type','risk','maturity','next'].includes(k)?1:-1)};render()}};
  if(S.page==='pos'){sortable('#ptab','sort');const pt=$('#ptype');if(pt)pt.onclick=e=>{const b=e.target.closest('[data-t]');if(!b)return;S.posType=b.dataset.t;render()}}
  if(S.page==='bonds')sortable('#btab','bsort');
  if(S.page==='ops'){let to;$('#oq').oninput=e=>{clearTimeout(to);to=setTimeout(()=>{S.opsQ=e.target.value;S.opsN=200;drawOps()},150)};
    $('#ok').onclick=e=>{const b=e.target.closest('[data-k]');if(!b)return;S.opsK=b.dataset.k;S.opsN=200;$('#ok').querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));drawOps()};drawOps()}
}

setInterval(()=>{fetch('/api/ping').catch(()=>{})},20000);fetch('/api/ping').catch(()=>{});
(async()=>{
  if(!PAGES.some(p=>p&&p[0]===S.page))S.page='dash';
  if(!PERIODS.some(p=>p[0]===S.period))S.period='all';
  renderNav();
  try{S.cfg=await api('/api/config')}catch(e){}
  const c=S.cfg||{};
  $('#ver').textContent='v'+(c.version||'');$('#ver').onclick=()=>{go('set');setTimeout(()=>{const w=$('#whatsnew');if(w)w.scrollIntoView({behavior:'smooth'})},400)};
  $('#mode').className='badge'+(c.sandbox?' sb':'');$('#mode').innerHTML=c.token_set?'<b></b>'+(c.sandbox?'Песочница':'Боевой режим'):'';
  if(!c.token_set&&!(c.imports||[]).length){S.page='set';renderNav();renderSettings();return}
  if(['set','imp'].includes(S.page)){render();load(false)}else load(false);
})();
// ── карточка облигации (боковая панель): клик по любому элементу с data-isin ──
const BC={stack:[],tok:0,all:false};
const BC_SEC={financial:'Финансы',industrials:'Промышленность',materials:'Сырьё',energy:'Энергетика',consumer:'Потребительский',government:'Государственные',real_estate:'Недвижимость',telecom:'Телеком',municipal:'Муниципальные',utilities:'Коммунальные',it:'IT',health_care:'Здравоохранение',other:'Прочее'};
const BC_EV={coupon:'Купон',amort:'Амортизация',offer:'Оферта',redemption:'Погашение'};
const BC_KR_SRC={cbr:'ключевая ставка по прогнозу ЦБ',survey:'ключевая ставка по опросу аналитиков ЦБ',market:'ключевая ставка по ожиданиям рынка (КБД)',flat:'текущая ключевая ставка'};
const BC_RISK={RISK_LEVEL_LOW:'низкий',RISK_LEVEL_MODERATE:'средний',RISK_LEVEL_HIGH:'высокий'};

document.addEventListener('click',e=>{
  const t=e.target.closest('[data-isin]');
  if(t&&t.dataset.isin&&!e.target.closest('a,button,input,select'))openBond(t.dataset.isin);
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('bc-ov'))closeBond()});

function closeBond(){
  BC.stack=[];BC.tok++;
  const o=document.getElementById('bc-ov');if(o)o.remove();
  document.body.classList.remove('bc-open');
}
function bcMount(){
  let o=document.getElementById('bc-ov');
  if(!o){
    o=document.createElement('div');o.id='bc-ov';
    o.innerHTML='<div class="bc-dr" id="bc-dr" role="dialog" aria-modal="true"></div>';
    o.addEventListener('mousedown',ev=>{if(ev.target===o)closeBond()});
    document.body.appendChild(o);document.body.classList.add('bc-open');
  }
  return document.getElementById('bc-dr');
}
function bcBar(){
  const back=BC.stack.length>1?'<button class="btn ghost" id="bc-back">← Назад</button>':'';
  return`<div class="bc-bar">${back}<span class="sp"></span><button class="btn ghost" id="bc-x" aria-label="Закрыть">✕ Закрыть</button></div>`;
}
function bcBind(dr){
  const x=dr.querySelector('#bc-x');if(x)x.onclick=closeBond;
  const b=dr.querySelector('#bc-back');
  if(b)b.onclick=()=>{BC.stack.pop();const p=BC.stack.pop();openBond(p)};
}
async function openBond(isin){
  isin=String(isin||'').trim();if(!isin)return;
  if(BC.stack[BC.stack.length-1]!==isin)BC.stack.push(isin);
  const tok=++BC.tok,dr=bcMount();
  dr.innerHTML=bcBar()+`<div class="bc-load">Загружаю данные по ${esc(isin)}…</div>`;bcBind(dr);dr.scrollTop=0;
  let c;
  try{c=await api('/api/bond?isin='+encodeURIComponent(isin))}
  catch(e){if(tok!==BC.tok)return;dr.innerHTML=bcBar()+`<div class="bc-warn">Не удалось загрузить карточку: ${esc(e.message||e)}</div>`;bcBind(dr);return}
  if(tok!==BC.tok)return;
  dr.innerHTML=bcBar()+bcBody(c);bcBind(dr);bcCharts(dr,c);
  const mr=dr.querySelector('#bc-more');
  if(mr)mr.onclick=()=>{BC.all=true;dr.innerHTML=bcBar()+bcBody(c);bcBind(dr);bcCharts(dr,c);BC.all=false};
}
const bcN=(v,d=2)=>v==null||isNaN(v)?'—':Number(v).toFixed(d).replace('.',',');
function bcKpi(k,v,s,cls){return`<div class="card"><div class="k">${k}</div><div class="v num ${cls||''}">${v}</div>${s?`<div class="s">${s}</div>`:''}</div>`}
function bcBody(c){
  const m=c.market,ci=c.catalog||{},d=c.desc||{},cur=(m&&m.cur||ci.currency||'RUB').toLowerCase();
  const sec=ci.sector?BC_SEC[ci.sector]||ci.sector:null;
  let h=`<div class="bc-h"><h1>${esc(c.name||c.isin)}</h1><div class="row2"><code>${esc(c.isin)}</code>`
    +(c.rating?ratingTag(c.rating):'<span class="tag">нет рейтинга</span>')
    +(sec?`<span class="tag">${esc(sec)}</span>`:'')
    +(ci.floating?'<span class="tag">флоатер</span>':'')+(ci.amort||(d.AMORTBOND==='1')?'<span class="tag">амортизация</span>':'')
    +(ci.subordinated?'<span class="tag">субординированная</span>':'')+(ci.perpetual?'<span class="tag">бессрочная</span>':'')
    +`<a href="https://www.moex.com/ru/issue.aspx?code=${encodeURIComponent(c.isin)}" target="_blank" rel="noopener" style="margin-left:auto">Страница на Мосбирже ↗</a></div></div>`;
  if(c.errors&&c.errors.length)h+=`<div class="bc-warn">${c.errors.map(esc).join('<br>')}</div>`;
  if(m){
    const sp=m.spread;
    h+=`<div class="bc-kpis">`
      +bcKpi('Цена',bcN(m.price,2)+' %',m.nominal?`номинал ${bcN(m.nominal,0)}`:'')
      +bcKpi('Доходность',bcN(m.yield,2)+' %','к погашению/оферте')
      +bcKpi('Спред к КБД',sp==null?'—':(sp>0?'+':'')+bcN(sp,2)+' п.п.',c.kbd!=null?`КБД ${bcN(c.kbd,2)} % на ${bcN(m.dur,2)} г.`:'',sp==null?'':sp>0?'pos':'neg')
      +bcKpi('Дюрация',m.dur==null?'—':bcN(m.dur,2)+' г.',`оборот ${short(m.turn||0)}`)
      +`</div>`;
  }
  const rows=[];const add=(k,v)=>{if(v!=null&&v!=='')rows.push(`<div><span>${k}</span><span>${v}</span></div>`)};
  add('Эмитент',esc(d.EMITTER||''));
  add('Вид',esc(d.BOND_TYPE||d.TYPENAME||''));
  add('Купон',m&&m.coupon!=null?bcN(m.coupon,2)+' %'+(d.COUPONFREQUENCY?` · ${esc(d.COUPONFREQUENCY)} р/год`:''):(d.COUPONFREQUENCY?`${esc(d.COUPONFREQUENCY)} р/год`:''));
  add('Следующий купон',m&&m.next?ddm(m.next):'');
  add('Погашение',m&&m.mat?ddm(m.mat):(ci.maturity?ddm(ci.maturity):(d.MATDATE?ddm(d.MATDATE):'')));
  add('Оферта',m&&m.offer?ddm(m.offer):'');
  add('Размещена',d.ISSUEDATE?ddm(d.ISSUEDATE):'');
  add('Объём выпуска',d.ISSUESIZE?short(+d.ISSUESIZE)+' шт.':'');
  add('Номинал',d.FACEVALUE?bcN(+d.FACEVALUE,2)+' '+esc(cur.toUpperCase())+(d.INITIALFACEVALUE&&d.INITIALFACEVALUE!==d.FACEVALUE?` (первоначально ${esc(d.INITIALFACEVALUE)})`:''):'');
  add('Уровень листинга',m&&m.level?esc(m.level):esc(d.LISTLEVEL||''));
  add('Уровень риска (T-Invest)',ci.risk?esc(BC_RISK[ci.risk]||ci.risk):'');
  add('Для квалифицированных',d.ISQUALIFIEDINVESTORS==='1'?'да':d.ISQUALIFIEDINVESTORS==='0'?'нет':'');
  add('Дефолт',d.HASDEFAULT==='1'?'<b class="neg">допущен</b>':d.HASTECHNICALDEFAULT==='1'?'<b class="neg">технический</b>':(d.HASDEFAULT==='0'?'нет':''));
  add('Госномер выпуска',esc(d.REGNUMBER||''));
  h+=`<div class="card bc-sec"><h2>Ключевые параметры</h2><div class="bc-par">${rows.join('')||'<span class="mu">Нет данных</span>'}</div></div>`;
  // денежный поток
  const fl=c.flows||[],lim=BC.all?fl.length:12;
  h+=`<div class="card bc-sec"><h2>Денежный поток<span class="sp">ближайшие выплаты на 1 облигацию</span></h2>`;
  if(fl.length){
    h+=`<div class="tbl"><table><thead><tr><th>Дата</th><th>Событие</th><th>Сумма</th><th>% номинала / ставка</th></tr></thead><tbody>`
      +fl.slice(0,lim).map(e=>`<tr><td>${ddm(e.d)}</td><td>${BC_EV[e.t]||esc(e.t)}</td><td class="num">${e.amt==null?'<span class="mu">по ставке</span>':e.est?`<span class="est" title="${esc(BC_KR_SRC[(c.keyrate||{}).source]||'ключевая ставка по прогнозу')} ${bcN(e.base,2)}% + спред ${bcN(e.spread,2)} п.п.">≈ ${M(e.amt,cur)}</span>`:M(e.amt,cur)}</td><td class="num">${e.pct==null?'—':(e.est?'≈ ':'')+bcN(e.pct,2)+' %'}</td></tr>`).join('')
      +`</tbody></table></div>`;
    if(c.keyrate)h+=`<p class="note" style="margin-top:8px">≈ — прогноз: ставка купона флоатера ещё не объявлена, принята равной ключевой ставке на начало купонного периода + спред эмитента к ключевой на прошлых купонах. Прогноз ключевой ставки: ${esc(c.keyrate.name)}${c.keyrate.as_of?`, на ${esc(c.keyrate.as_of)}`:''}.</p>`;
    if(fl.length>lim)h+=`<button class="btn ghost bc-more" id="bc-more">Показать все (${fl.length})</button>`;
  }else h+=`<div class="mu" style="font-size:13px">Данных о будущих выплатах нет.</div>`;
  h+=`</div>`;
  // история
  const hs=c.history||{d:[]};
  h+=`<div class="card bc-sec"><h2>История за год<span class="sp">Мосбиржа, основной режим торгов</span></h2>`;
  if(hs.d&&hs.d.length>1)h+=`<div class="mu" style="font-size:12px;margin-bottom:4px">Цена, % от номинала</div><div class="bc-ch" id="bc-ch-p"></div>
      <div class="mu" style="font-size:12px;margin:12px 0 4px">Доходность, % годовых</div><div class="bc-ch" id="bc-ch-y"></div>`;
  else h+=`<div class="mu" style="font-size:13px">История торгов недоступна.</div>`;
  h+=`</div>`;
  // кривая эмитента
  const ic=c.issuer_curve;
  if(ic&&ic.points&&ic.points.length>1)h+=`<div class="card bc-sec"><h2>Кривая эмитента<span class="sp">${ic.points.length} выпусков в обращении: доходность по сроку</span></h2><div class="bc-ic" id="bc-ic"></div>
    <div class="mu" style="font-size:12px;margin-top:6px"><span style="color:var(--ac)">●</span> этот выпуск · <span style="color:#3987e5">●</span> другие выпуски эмитента · пунктир — кривая бескупонной доходности (КБД). Клик по точке открывает карточку выпуска.</div></div>`;
  // аналоги
  const an=c.analogs||[];
  h+=`<div class="card bc-sec"><h2>Аналоги<span class="sp">похожий рейтинг, срок и тип</span></h2>`;
  if(c.rel&&c.rel.text){const ok=c.rel.diff>=0.25,bad_=c.rel.diff<=-0.25;
    h+=`<div class="bc-rel"><b class="${ok?'pos':bad_?'neg':''}">${esc(c.rel.text)}.</b> Медианный спред аналогов: ${bcN(c.rel.median_spread,2)} п.п. «Дешевле» — выше доходность при сопоставимом риске, но это может отражать и риски, которых нет в рейтинге.</div>`}
  if(an.length){
    h+=`<div class="tbl"><table><thead><tr><th>Выпуск</th><th>Рейтинг</th><th>Сектор</th><th>Дюр., г.</th><th>Доходность</th><th>Спред</th><th>Δ дох.</th><th>Оборот</th></tr></thead><tbody>`
      +an.map(a=>`<tr data-isin="${esc(a.isin)}" title="Открыть карточку"><td class="l">${esc(a.name)}${a.floating?' <span class="tag">флоат</span>':''}${a.amort?' <span class="tag">аморт</span>':''}</td>
        <td>${a.rating?`<span class="tag rt rt-${esc(rBucket(a.rating).split(' ')[0])}">${esc(a.rating)}</span>`:'<span class="mu">—</span>'}</td>
        <td>${esc(BC_SEC[a.sector]||a.sector||'—')}</td><td class="num">${bcN(a.dur,2)}</td><td class="num">${bcN(a.yield,2)} %</td>
        <td class="num">${a.spread==null?'—':(a.spread>0?'+':'')+bcN(a.spread,2)}</td>
        <td class="num ${a.dy>0?'pos':a.dy<0?'neg':''}">${a.dy==null?'—':(a.dy>0?'+':'')+bcN(a.dy,2)}</td><td class="num">${short(a.turn||0)}</td></tr>`).join('')
      +`</tbody></table></div>`;
  }else h+=`<div class="mu" style="font-size:13px">Подходящих аналогов не найдено${m?'':' (нет рыночных данных по выпуску)'}.</div>`;
  h+=`</div><p class="note" style="margin-top:14px">Справочная информация на основе открытых данных Мосбиржи, каталога T-Invest и публичных рейтингов. Не является инвестиционной рекомендацией. Аналоги подобраны автоматически по рейтингу, сроку, сектору и типу выпуска; сравнение спреда не учитывает всех различий в риске и ликвидности.</p>`;
  return h;
}
function bcIssuerCurve(el,ic){
  const W=el.clientWidth||560,H=250,pl=44,pr=14,pt=12,pb=30,P=ic.points,K=ic.kbd||[];
  const xs=P.map(p=>p.dur).concat(K.map(k=>k[0])),ys=P.map(p=>p.yield).concat(K.map(k=>k[1]));
  const x0=0,x1=Math.max(...xs)*1.05||1,ny=nice(Math.min(...ys)*0.9,Math.max(...ys)*1.05,5),y0=ny.lo,y1=ny.hi,pw=W-pl-pr,ph=H-pt-pb;
  const X=v=>pl+(v-x0)/(x1-x0)*pw,Y=v=>pt+ph-(v-y0)/(y1-y0)*ph;
  let g='';
  for(let v=y0;v<=y1+ny.step/2;v+=ny.step)g+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax num" x="${pl-6}" y="${Y(v)+4}" text-anchor="end">${+v.toFixed(1)}%</text>`;
  const nx=Math.max(2,Math.min(8,Math.round(pw/80))),st=x1/nx;
  for(let i=0;i<=nx;i++){const v=i*st;g+=`<text class="ax num" x="${X(v)}" y="${H-8}" text-anchor="middle">${bcN(v,1)} г.</text>`}
  if(K.length>1)g+=`<polyline class="ic-kbd" points="${K.map(k=>X(k[0]).toFixed(1)+','+Y(k[1]).toFixed(1)).join(' ')}"/>`;
  const fl=P.filter(p=>!p.floating);
  if(fl.length>1)g+=`<polyline class="ic-ln" points="${fl.map(p=>X(p.dur).toFixed(1)+','+Y(p.yield).toFixed(1)).join(' ')}"/>`;
  P.slice().sort((a,b)=>a.me-b.me).forEach(p=>{
    g+=`<circle class="ic-pt${p.me?' ic-me':''}" data-isin="${esc(p.isin)}" cx="${X(p.dur)}" cy="${Y(p.yield)}" r="${p.me?7:5}" fill="${p.me?'var(--ac)':'#3987e5'}"><title>${esc(p.name)} · дох. ${bcN(p.yield,2)} % · дюр. ${bcN(p.dur,2)} г.${p.spread==null?'':' · спред '+(p.spread>0?'+':'')+bcN(p.spread,2)}${p.rating?' · '+esc(p.rating):''}${p.floating?' · флоатер':''}</title></circle>`});
  el.innerHTML=`<svg width="${W}" height="${H}">${g}</svg>`;
}
function bcCharts(dr,c){
  const ice=dr.querySelector('#bc-ic');if(ice&&c.issuer_curve)try{bcIssuerCurve(ice,c.issuer_curve)}catch(e){}
  const hs=c.history;if(!hs||!hs.d||hs.d.length<2)return;
  const labels=hs.d.map(ddm),p=document.getElementById('bc-ch-p'),y=document.getElementById('bc-ch-y');
  {
    try{
      if(p)line(p,{h:190,labels,zero:false,fa:v=>bcN(v,1),ft:v=>bcN(v,2)+' %',series:[{n:'Цена',c:'#3987e5',v:hs.p,w:2}]});
      if(y)line(y,{h:190,labels,zero:false,fa:v=>bcN(v,1),ft:v=>bcN(v,2)+' %',series:[{n:'Доходность',c:'#c98500',v:hs.y,w:2}]});
    }catch(e){}
  }
}
/* ── Карта рынка: доходность и дюрация, спреды по рейтингам ── */
const MP_COL={'AAA':'#199e70','AA':'#3ecf8e','A':'#3987e5','BBB':'#e3a21a','BB и ниже':'#ff6b6b','нет рейтинга':'#8a90a0'};
const MP_BK=['AAA','AA','A','BBB','BB и ниже','нет рейтинга'];
S.mp={rb:{'AAA':true,'AA':true,'A':true,'BBB':true,'BB и ниже':true,'нет рейтинга':true},sector:'',dmax:'5',liquid:true,mine:false,all:false};
function mpMine(){const s=new Set();((S.bonds&&S.bonds.rows)||[]).forEach(b=>{if(b.isin)s.add(b.isin);if(b.ticker)s.add(b.ticker)});return s}
function mpRows(){
  const f=S.mp,mine=mpMine(),dm=f.dmax==='all'?1e9:+f.dmax;
  return S.scr.rows.filter(r=>{
    if(r.cur!=='RUB'||r.kind!=='corp'||!(r.yield>0))return false;
    const d=r.dur||r.years;if(!(d>0)||d>dm)return false;
    if(!f.rb[rBucket(r.rating)])return false;
    if(f.sector&&r.sector!==f.sector)return false;
    if(f.liquid&&r.turn<1e6)return false;
    if(f.mine&&!(mine.has(r.isin)||mine.has(r.id)))return false;
    return true;
  });
}
function mpScatter(el){
  const W=el.clientWidth,H=W<560?340:460,pl=W<560?38:46,pr=12,pt=12,pb=30;
  const f=S.mp,mine=mpMine(),dm=f.dmax==='all'?null:+f.dmax;
  let rs=mpRows().map(r=>({r,x:r.dur||r.years}));
  const cap=f.all?Infinity:40,hidden=rs.filter(p=>p.r.yield>cap).length;
  rs=rs.filter(p=>p.r.yield<=cap);
  if(W<50)return;
  if(!rs.length){emptyChart(el,H,'Нет выпусков под выбранные фильтры');return mpCnt(0,hidden)}
  const xmax=dm||nice(0,Math.max(...rs.map(p=>p.x)),6).hi,ymax=f.all?nice(0,Math.max(...rs.map(p=>p.r.yield)),5).hi:40;
  const nx=nice(0,xmax,Math.min(10,Math.max(2,Math.round(W/90)))),ny=nice(0,ymax,5);
  const X0=0,X1=dm||nx.hi,Y1=ny.hi,pw=W-pl-pr,ph=H-pt-pb,X=v=>pl+(v-X0)/(X1-X0)*pw,Y=v=>pt+ph-v/Y1*ph;
  let s='';
  for(let v=0;v<=Y1+ny.step/2;v+=ny.step)s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax num" x="${pl-8}" y="${Y(v)+4}" text-anchor="end">${v}%</text>`;
  for(let v=0;v<=X1+nx.step/2;v+=nx.step){if(v>X1+1e-9)break;s+=`<line class="grid-l" x1="${X(v)}" x2="${X(v)}" y1="${pt}" y2="${pt+ph}"/><text class="ax num" x="${X(v)}" y="${H-8}" text-anchor="middle">${+v.toFixed(2)}</text>`}
  const kb=((S.scr.kbd)||[]).filter(p=>p[0]<=X1+1);
  if(kb.length>1)s+=`<polyline class="mp-kbd" fill="none" points="${kb.map(p=>X(Math.min(p[0],X1)).toFixed(1)+','+Y(Math.min(p[1],Y1)).toFixed(1)).join(' ')}"/>`;
  const fl=S.scr.floor&&S.scr.floor.lqdt;
  if(fl>0&&fl<=Y1)s+=`<line class="mp-fl" x1="${pl}" x2="${W-pr}" y1="${Y(fl).toFixed(1)}" y2="${Y(fl).toFixed(1)}"/><text class="ax mp-flt" x="${W-pr-4}" y="${(Y(fl)-5).toFixed(1)}" text-anchor="end">Фонд ликвидности LQDT ≈ ${f2(fl)} %</text>`;
  const rad=t=>t>0?Math.max(2.5,Math.min(9,2.5+(Math.log10(t)-5)*1.6)):2.5;
  rs.sort((a,b)=>b.r.turn-a.r.turn);
  let dots='',rings='';
  rs.forEach(p=>{const r=p.r,c=MP_COL[rBucket(r.rating)],rd=rad(r.turn),cx=X(p.x).toFixed(1),cy=Y(r.yield).toFixed(1),id=r.isin||r.id;
    dots+=`<circle class="mp-d" data-isin="${esc(id)}" data-k="${esc(r.id)}" cx="${cx}" cy="${cy}" r="${rd.toFixed(1)}" fill="${c}" fill-opacity=".72" stroke="${c}"/>`;
    if(mine.has(r.isin)||mine.has(r.id))rings+=`<circle class="mp-ring" cx="${cx}" cy="${cy}" r="${(rd+4.5).toFixed(1)}"/>`});
  el.innerHTML=`<div class="legend">${MP_BK.map(b=>`<span><i style="background:${MP_COL[b]}"></i>${b}</span>`).join('')}<span><i class="mp-lk"></i>КБД</span>${fl>0?'<span><i class="mp-lf"></i>фонд ликвидности</span>':''}<span class="mu">ось X — дюрация, лет; ось Y — доходность</span>${mine.size?'<span><i class="mp-lr"></i>мой портфель</span>':''}</div><svg width="${W}" height="${H}">${s}<g>${dots}</g><g style="pointer-events:none">${rings}</g></svg>`;
  const byK={};rs.forEach(p=>byK[p.r.id]=p);
  el.onmousemove=e=>{const t=e.target.closest('circle[data-k]');if(!t||!el.contains(t)){hideTip();return}
    const p=byK[t.dataset.k];if(!p)return;const r=p.r,c=MP_COL[rBucket(r.rating)];
    showTip(`<b>${esc(r.name)}</b><div style="color:var(--mu)">${esc(r.isin||r.id)}${r.sector?' · '+esc(SECT[r.sector]||r.sector):''}</div>`+
      tipRow(c,'Рейтинг',esc(r.rating||'нет'))+tipRow(c,'Доходность',pctp(r.yield,2))+tipRow(c,'Спред к КБД',r.spread!=null?(r.spread>0?'+':'')+f2(r.spread)+' п.п.':'—')+
      tipRow(c,'Дюрация',f2(p.x)+' г')+tipRow(c,'Оборот за день',r.turn?short(r.turn)+' ₽':'—')+(mine.has(r.isin)||mine.has(r.id)?'<div style="color:var(--ac)">в вашем портфеле</div>':'')+'<div style="color:var(--mu);margin-top:5px">нажмите — карточка выпуска</div>',e)};
  el.onmouseleave=hideTip;
  mpCnt(rs.length,hidden);
}
function mpCnt(n,h){const e=$('#mp-cnt');if(e)e.textContent=`Выпусков на графике: ${n}`+(h?` · выше 40 % скрыто: ${h}`:'')}
function mpHeat(){
  const st=S.scr.stats;if(!st||!st.grid)return'<div class="empty">Статистика недоступна</div>';
  const vals=[];st.grid.forEach(g=>g.cells.forEach(c=>{if(c.spread!=null)vals.push(Math.abs(c.spread))}));const mx=Math.max(1,...vals);
  const cell=c=>{if(!c||!c.n)return'<td class="mu">—</td>';const a=c.spread==null?0:Math.min(1,Math.abs(c.spread)/mx);
    return`<td style="background:rgba(57,135,229,${(0.06+a*0.42).toFixed(2)})"><b class="num">${c.spread==null?'—':(c.spread>0?'+':'')+f2(c.spread)}</b><small>${c.n} шт · ${pctp(c.yield,1)}</small></td>`};
  return`<div class="tbl"><table class="mp-hm"><thead><tr><th class="l">Рейтинг</th>${st.dur.map(d=>`<th>${d} г</th>`).join('')}<th>Все сроки</th></tr></thead><tbody>${
    st.grid.map(g=>`<tr><td class="l"><span class="tag rt rt-${g.bucket.split(' ')[0]}">${esc(g.bucket)}</span></td>${g.cells.map(cell).join('')}${cell(g.all)}</tr>`).join('')}</tbody></table></div>`;
}
function mpSectors(){
  const sc=(S.scr.stats&&S.scr.stats.sectors)||[];
  if(!sc.length)return'<div class="empty">Сектора выпусков появятся после загрузки каталога T-Invest</div>';
  return`<div class="tbl"><table><thead><tr><th class="l">Сектор</th><th>Выпусков</th><th>Медианная доходность</th><th>Медианный спред к КБД</th></tr></thead><tbody>${
    sc.map(x=>`<tr><td class="l">${esc(SECT[x.sector]||x.sector)}</td><td class="num">${x.n}</td><td class="num">${pctp(x.yield,2)}</td><td class="num">${x.spread==null?'—':(x.spread>0?'+':'')+f2(x.spread)+' п.п.'}</td></tr>`).join('')}</tbody></table></div>`;
}
function mpHist(el){
  const h=S.scr.stats_hist||{},days=Object.keys(h).sort();
  if(days.length<2)return el.innerHTML=`<div class="empty" style="min-height:120px;padding:18px">История копится ежедневно, начиная с дня установки приложения: сейчас накоплено дней — ${days.length}. График появится, когда их будет хотя бы два.</div>`;
  const ser=['AAA','AA','A','BBB','BB и ниже'].map(b=>({n:b,c:MP_COL[b],v:days.map(d=>h[d][b]??null)})).filter(s=>s.v.some(v=>v!=null));
  line(el,{labels:days.map(d=>ddm(d).slice(0,5)+'.'+d.slice(2,4)),tipLabels:days.map(ddm),series:ser,h:260,zero:false,fa:v=>(+v.toFixed(1))+'',ft:v=>f2(v)+' п.п.',empty:'Недостаточно данных'});
}
function pMap(){
  const d=S.scr;
  if(!d){loadScr();return`<div class="card">${waitBox('Загружаю торги облигациями с Мосбиржи…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="scr-r">Повторить</button></div>`;
  const f=S.mp,sectors=[...new Set(d.rows.map(r=>r.sector).filter(Boolean))].sort((a,b)=>(SECT[a]||a).localeCompare(SECT[b]||b));
  const opt=(v,t,cur)=>`<option value="${v}" ${String(cur)===String(v)?'selected':''}>${t}</option>`;
  const hasP=mpMine().size>0;
  chart('map-sc',mpScatter);chart('map-hist',mpHist);chart('map-root',bindMap);
  return`<div id="map-root"><div class="card"><h2>Карта рынка: доходность и дюрация<span class="sp" id="mp-cnt"></span></h2>
    <div class="mp-chips" id="mp-chips">${MP_BK.map(b=>`<button type="button" data-b="${esc(b)}" class="${f.rb[b]?'on':''}"><i style="background:${MP_COL[b]}"></i>${b}</button>`).join('')}</div>
    <div class="flt">
      ${sectors.length?`<label class="field"><span>Сектор</span><select class="in" id="mp-sec"><option value="">любой</option>${sectors.map(x=>opt(x,SECT[x]||x,f.sector)).join('')}</select></label>`:''}
      <label class="field"><span>Дюрация не более</span><select class="in" id="mp-dmax">${[['2','2 лет'],['3','3 лет'],['5','5 лет'],['7','7 лет'],['10','10 лет'],['all','любая']].map(([v,t])=>opt(v,t,f.dmax)).join('')}</select></label>
      <label class="sw"><input type="checkbox" id="mp-liq" ${f.liquid?'checked':''}><i></i><div><b>Скрыть неликвид</b><small>оборот за день &lt; 1 млн ₽</small></div></label>
      <label class="sw"><input type="checkbox" id="mp-mine" ${f.mine?'checked':''} ${hasP?'':'disabled'}><i></i><div><b>Только мой портфель</b><small>${hasP?'выпуски из ваших позиций':'портфель облигаций не загружен'}</small></div></label>
      <label class="sw"><input type="checkbox" id="mp-all" ${f.all?'checked':''}><i></i><div><b>Показать всё</b><small>без отсечки доходности 40 %</small></div></label>
    </div>
    <div class="chart" id="map-sc"></div></div>
  <div class="g c-2-1 mp-g"><div class="card"><h2>Спреды по рейтингам<span class="sp">медиана, п.п. к КБД</span></h2>${mpHeat()}
    <p class="note" style="margin-top:10px">В ячейке: медианный спред к КБД, число выпусков и медианная доходность. Учтены рублёвые корпоративные облигации с известным рейтингом, доходностью до 60 % и сроком более 0,1 года (${(d.stats&&d.stats.n)||0} выпусков).</p></div>
  <div class="card"><h2>По секторам</h2>${mpSectors()}</div></div>
  <div class="card"><h2>История медианных спредов<span class="sp">п.п. к КБД, по рейтингам</span></h2><div class="chart" id="map-hist"></div>
    <p class="note" style="margin-top:8px">История копится ежедневно, начиная с дня установки приложения: снимок сохраняется при открытии скринера или карты.</p></div></div>
  <p class="note">По горизонтали — дюрация (лет), по вертикали — доходность к погашению. Размер точки — дневной оборот, цвет — рейтинг, пунктир — кривая КБД, кольцо — выпуск из вашего портфеля. Рейтинги сопоставлены по названию эмитента, у части выпусков их нет. Рассматриваются рублёвые корпоративные облигации. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function bindMap(){
  const f=S.mp,redraw=()=>{const e=$('#map-sc');if(e)mpScatter(e)};
  $('#mp-chips').onclick=e=>{const b=e.target.closest('[data-b]');if(!b)return;f.rb[b.dataset.b]=!f.rb[b.dataset.b];b.classList.toggle('on',f.rb[b.dataset.b]);redraw()};
  const sec=$('#mp-sec');if(sec)sec.onchange=()=>{f.sector=sec.value;redraw()};
  $('#mp-dmax').onchange=e=>{f.dmax=e.target.value;redraw()};
  $('#mp-liq').onchange=e=>{f.liquid=e.target.checked;redraw()};
  $('#mp-mine').onchange=e=>{f.mine=e.target.checked;redraw()};
  $('#mp-all').onchange=e=>{f.all=e.target.checked;redraw()};
  const r=$('#scr-r');if(r)r.onclick=()=>{S.scr=null;render()};
  if(!window._mpRs){window._mpRs=1;let t;addEventListener('resize',()=>{clearTimeout(t);t=setTimeout(()=>{if(S.page==='map'){const e=$('#map-sc');if(e&&S.scr&&!S.scr.error)mpScatter(e);const h=$('#map-hist');if(h&&S.scr&&!S.scr.error)mpHist(h)}},200)})}
}
/* ── Риски и сценарии: вероятность дефолта, ожидаемая доходность, сценарии ключевой ставки ── */
S.riskQ={rec:'25',target:'',tax:false,hor:'3'};
try{const v=JSON.parse(localStorage.getItem('rk_hor')||'null');if(v&&+v>0)S.riskQ.hor=String(v)}catch(e){}
S.rsort={k:'value_rub',d:-1};
function loadRisk(){
  if(S._riskLoading)return;S._riskLoading=1;const acc=S.account,q=S.riskQ;
  const p=new URLSearchParams({account:acc,recovery:q.rec||'25',horizon:String(q.hor||'3').replace(',','.')});if(q.target!=='')p.set('target',q.target.replace(',','.'));if(q.tax)p.set('tax','1');
  api('/api/risk?'+p).then(j=>{S._riskLoading=0;if(S.account!==acc)return;S.risk=j;S.riskAcc=acc;if(S.page==='risk')render()})
   .catch(e=>{S._riskLoading=0;S.risk={error:e.message};S.riskAcc=acc;if(S.page==='risk')render()});
}
const rkPd=x=>x==null?'—':x*100<0.1?'&lt;0,1 %':pctp(x*100,x*100<10?1:0);
const rkRub=(v,d=0)=>bad(v)?'—':(v>0?'+':v<0?'−':'')+NF0.format(Math.abs(v))+' ₽';
const rkPct=(v,d=1)=>bad(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',')+' %';
function rkScnChart(el){
  const d=S.risk;if(!d||!d.scenarios)return;
  bars(el,{h:260,stack:true,labels:d.scenarios.map(s=>s.name),series:[{n:'Купоны (получено за год)',c:'#3987e5',v:d.scenarios.map(s=>d.scn_total[s.key].coupons)},
    {n:'Изменение цены (переоценка, подтягивание к номиналу)',c:'#19a070',v:d.scenarios.map(s=>d.scn_total[s.key].price)}],total:true,fa:short,ft:v=>rkRub(v),empty:'Нет данных'});
}
function rkFloatText(d){
  const f=d.floaters.floating,x=d.floaters.fixed;
  if(!f.count||!x.count)return f.count?'В портфеле только флоатеры.':'В портфеле нет флоатеров: все выпуски с фиксированным купоном.';
  const fw=[],xw=[];d.scenarios.forEach(s=>{const a=f.scn[s.key].pct,b=x.scn[s.key].pct;(a>=b?fw:xw).push(s.name)});
  let t='';if(fw.length)t+=`Флоатеры выигрывают в сценариях: ${fw.join(', ')}. `;if(xw.length)t+=`Фиксированный купон выигрывает в сценариях: ${xw.join(', ')}. `;
  return t+'Логика: при росте ставки купон флоатера растёт вместе с ней, а цена фиксированных бумаг падает; при снижении ставки фиксированные дорожают, а купон флоатера уменьшается.';
}
function rkRows(d){
  const g={name:r=>r.name,value_rub:r=>r.value_rub,rating:r=>r.rating?RSC.indexOf(r.rating.v):null,ytm:r=>r.ytm,pd_mkt_1y:r=>r.pd_mkt_1y,pd_mkt_T:r=>r.pd_mkt_T,pd_hist_1y:r=>r.pd_hist_1y,
    ratio:r=>r.ratio,ey_hist:r=>r.ey_hist,breakeven:r=>r.breakeven==null&&r.be_gt?99:r.breakeven}[S.rsort.k]||(r=>r.value_rub);
  return d.rows.slice().sort((a,b)=>{const x=g(a),y=g(b);if(typeof x==='string'||typeof y==='string')return S.rsort.d*String(x||'').localeCompare(String(y||''));return S.rsort.d*((x??-Infinity)-(y??-Infinity))});
}
const rkYr=v=>bad(v)?'—':v.toFixed(1).replace('.',',')+' г.';
function rkDurBlock(d){
  const u=d.duration,r=d.real;if(!u&&!r)return'';
  const gk=u?(u.kind==='match'?'':u.kind==='long'?'neg':''):'';
  const gp=u?(u.gap>0?'+':u.gap<0?'−':'')+Math.abs(u.gap).toFixed(1).replace('.',',')+' г.':'';
  const kp=`<div class="g g4">${u?kpi('Дюрация портфеля',rkYr(u.mac),`модифицированная: ${rkYr(u.mod)}`,null,S1):''}
    ${u?kpi('Дюрационный разрыв',gp,`дюрация − горизонт ${rkYr(u.goal)}`,gk,S4):''}
    ${r?kpi('Реальная доходность',pctp(r.real,1),`до налога: ${pctp(r.irr,1)} − инфляция ${pctp(r.inflation,1)}${r.estimate?' (оценка)':''}`,r.real<0?'neg':'',S3):''}
    ${r&&r.real_tax!=null?kpi('Реальная после НДФЛ',pctp(r.real_tax,1),`номинальная после налога: ${pctp(r.irr_tax,1)}`,r.real_tax<0?'neg':'',S2):''}</div>`;
  const tx=u?`<p><b>Срок и ставки.</b> ${esc(u.text)} Дюрация портфеля облигаций — ${rkYr(u.mac)}, горизонт цели — ${rkYr(u.goal)}</p>`:'';
  const rt=r?`<p><b>Реальная доходность</b> — сколько вы зарабатываете сверх роста цен: (1 + доходность) / (1 + инфляция) − 1. Доходность портфеля (IRR) ${pctp(r.irr,1)}, ожидаемая инфляция в среднем за ${rkYr(r.years)} — ${pctp(r.inflation,1)} ${r.estimate?'(прогноз Банка России недоступен, взята оценка 4 %)':'(прогноз Банка России'+(r.as_of?' от '+ddm(r.as_of):'')+')'}.</p>`:'';
  return`<div class="card"><h2>Срок цели и реальная доходность<span class="sp">дюрационный разрыв, инфляция</span></h2>${kp}<div class="note rk-dur" style="margin-top:10px">${tx}${rt}
    <p>Справочная оценка по упрощённой модели, не инвестиционная рекомендация. Доходность выпусков с аномально высокой ставкой завышает общий показатель.</p></div></div>`;
}
function pRisk(){
  if(S.risk&&S.riskAcc!==S.account)S.risk=null;
  if(!S.risk){loadRisk();return`<div class="card">${waitBox('Считаю вероятности дефолта и сценарии ставки (потоки по каждому выпуску)…')}</div>`}
  const d=S.risk,q=S.riskQ;
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="rk-apply">Повторить</button></div>`;
  const ctl=`<div class="card"><h2>Параметры</h2><div class="flt rk-ctl">
    <label class="field"><span>Доля возврата при дефолте, %</span><input class="in" id="rk-rec" type="number" min="0" max="90" step="5" value="${esc(q.rec)}"></label>
    <label class="field"><span>Своя ключевая ставка через 12 мес., %</span><input class="in" id="rk-tgt" type="number" min="0" max="60" step="0.5" placeholder="например 12" value="${esc(q.target)}"></label>
    <label class="field"><span>Горизонт цели, лет</span><input class="in" id="rk-hor" type="number" min="0.5" max="50" step="0.5" value="${esc(q.hor)}"></label>
    <label class="sw"><input type="checkbox" id="rk-tax" ${q.tax?'checked':''}><i></i><div><b>Учесть НДФЛ 13 %</b><small>на купоны и прирост цены</small></div></label>
    <button class="btn" id="rk-apply">Пересчитать</button></div></div>`;
  if(!d.portfolio)return ctl+'<div class="card empty">В портфеле нет облигаций с рассчитанной доходностью</div>';
  const p=d.portfolio,sc=d.scenarios,tt=d.scn_total;
  const worst=sc.reduce((a,s)=>tt[s.key].total<tt[a.key].total?s:a,sc[0]);
  const hasEx=p.promised_ex!=null&&p.distressed_value>0;
  const kp=`<div class="g g4">${kpi('Обещанная доходность',pctp(p.promised,1),hasEx?`без выпусков с доходностью &gt;100 %: ${pctp(p.promised_ex,1)}`:'средневзвешенная к погашению',null,S1)}
    ${kpi('Ожидаемая с учётом дефолтов',pctp(p.expected,1),`по рейтингу: −${f2(p.promised-p.expected)} п.п. · по рынку: ${pctp(p.expected_mkt,1)}`,null,S3)}
    ${kpi('Ожидаемые потери за год',M(-p.exp_loss_rub,'rub',0),`по рынку: ${M(-p.exp_loss_mkt_rub,'rub',0)}`,'neg',S8)}
    ${kpi('Худший сценарий ставки',rkRub(tt[worst.key].total),`${esc(worst.name)} · ${rkPct(tt[worst.key].pct)} за год`,tt[worst.key].total<0?'neg':'',S4)}</div>`;
  const hd=d.horizon?ddm(d.horizon):'';
  const scT=`<div class="tbl"><table><thead><tr><th class="l">Сценарий</th><th>Ставка через 12 мес.</th><th>Δ к текущей</th><th>Купоны</th><th>Цена</th><th>Итого, ₽</th><th>Итого, %</th></tr></thead><tbody>${
    sc.map(s=>{const t=tt[s.key];return`<tr><td class="l">${esc(s.name)}${s.note?`<br><small class="mu">${esc(s.note)}</small>`:''}</td><td class="num">${pctp(s.k12,1)}</td><td class="num ${cls(-s.delta)}">${s.delta>0?'+':s.delta<0?'−':''}${Math.abs(s.delta).toFixed(1).replace('.',',')} п.п.</td>
      <td class="num">${rkRub(t.coupons)}</td><td class="num ${cls(t.price)}">${rkRub(t.price)}</td><td class="num ${cls(t.total)}"><b>${rkRub(t.total)}</b></td><td class="num ${cls(t.pct)}">${rkPct(t.pct)}</td></tr>`}).join('')}</tbody></table></div>`;
  const fl=d.floaters,fT=`<div class="tbl"><table><thead><tr><th class="l">Сценарий</th><th>Флоатеры (${fl.floating.count})</th><th>Фиксированный купон (${fl.fixed.count})</th><th>Победитель</th></tr></thead><tbody>${
    sc.map(s=>{const a=fl.floating.scn[s.key].pct,b=fl.fixed.scn[s.key].pct,w=fl.floating.count&&fl.fixed.count?(a>=b?'флоатеры':'фиксированные'):'—';
      return`<tr><td class="l">${esc(s.name)}</td><td class="num ${cls(a)}">${rkPct(a)}</td><td class="num ${cls(b)}">${rkPct(b)}</td><td class="num">${w}</td></tr>`}).join('')}</tbody></table></div>`;
  const cs=d.casino.length?`<div class="tbl"><table><thead><tr><th class="l">Дефолт k самых рискованных эмитентов</th><th>Потеряно на дефолте</th><th>Итог за год, ₽</th><th>Итог за год, %</th></tr></thead><tbody>${
    d.casino.map(c=>`<tr><td class="l"><b>k = ${c.k}</b><br><small class="mu">${c.issuers.map(i=>esc(i.name)+' ('+M(i.value,'rub',0)+')').join('; ')}</small></td><td class="num neg">${rkRub(-c.lost_rub)}</td>
      <td class="num ${cls(c.result_rub)}"><b>${rkRub(c.result_rub)}</b></td><td class="num ${cls(c.result_pct)}">${rkPct(c.result_pct)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">Недостаточно эмитентов</div>';
  const cols=[['name','Облигация','l'],['value_rub','Стоимость'],['rating','Рейтинг','l'],['ytm','Доходность'],['pd_mkt_1y','PD рынка, 1 год'],['pd_mkt_T','PD рынка, до погашения'],['pd_hist_1y','PD по рейтингу, 1 год'],['ratio','Рынок / рейтинг'],['ey_hist','Ожидаемая доходность'],['breakeven','Запас по росту доходности']];
  const th=cols.map(([k,t,c])=>`<th class="s ${c||''}" data-s="${k}">${t} <span>${S.rsort.k===k?(S.rsort.d>0?'↑':'↓'):''}</span></th>`).join('');
  const body=rkRows(d).map(r=>{
    const flag=r.ratio!=null&&r.ratio>=3?`<br><small class="neg" title="Рыночный спред закладывает вероятность дефолта заметно выше, чем следует из рейтинга: сигнал проблем у эмитента либо возможность">рынок закладывает риск в ${r.ratio>=10?Math.round(r.ratio):f2(r.ratio).replace(',0','')} раз выше рейтинга</small>`:'';
    const be=r.breakeven!=null?f2(r.breakeven)+' п.п.':(r.be_gt?'&gt; 30 п.п.':'—');
    return`<tr data-isin="${esc(r.isin||r.ticker||'')}"><td class="l">${esc(r.name)}<br><small class="mu">${esc(r.isin||'')}${r.floating?' · флоатер':''}${r.exact?'':' · приближённо'}</small></td>
      <td class="num">${M(r.value_rub,'rub',0)}</td><td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td><td class="num">${pctp(r.ytm,1)}</td>
      <td class="num">${rkPd(r.pd_mkt_1y)}</td><td class="num">${rkPd(r.pd_mkt_T)}</td><td class="num">${r.pd_hist_1y!=null?rkPd(r.pd_hist_1y):'<span class="mu">нет рейтинга</span>'}</td>
      <td class="num">${r.ratio!=null?(r.ratio>=10?Math.round(r.ratio):f2(r.ratio))+' ×':'—'}${flag}</td>
      <td class="num ${r.ey_hist<0?'neg':''}">${pctp(r.ey_hist,1)}${r.hist_basis==='market'?' <small class="mu" title="Нет рейтинга: использована рыночная вероятность дефолта">*</small>':''}</td><td class="num" title="${r.be_approx!=null?'Грубая оценка доходность / модифицированная дюрация сегодня: '+f2(r.be_approx)+' п.п. Точный расчёт учитывает, что через год дюрация короче.':''}">${be}</td></tr>`}).join('');
  chart('rk-scn',rkScnChart);
  return ctl+kp+rkDurBlock(d)+`<div class="card"><h2>Сценарии ключевой ставки<span class="sp">доход за 12 месяцев (до ${hd}), без реинвестирования купонов</span></h2><div class="chart" id="rk-scn"></div>${scT}
    <p class="note" style="margin-top:10px">Сдвиг кривой доходности = Δ ключевой ставки × β: β = 1,0 для срока до 1 года и линейно снижается до 0,5 на сроке 7 лет и дольше (длинные ставки реагируют слабее). Кредитные спреды не меняются. Выпуск переоценивается через 12 месяцев: оставшиеся потоки дисконтируются по текущей доходности со сдвигом на дюрации остатка. Купоны флоатеров следуют траектории ставки сценария плюс спред эмитента; ставка идёт линейно к целевой за 12 месяцев. Сценарий «Рынок» доступен, если получен рыночный путь ставки.</p></div>
  <div class="g c-2-1 rk-g"><div class="card"><h2>Флоатеры против фиксированного купона<span class="sp">доходность подпортфелей за 12 месяцев</span></h2>${fT}<p class="note" style="margin-top:10px">${esc(rkFloatText(d))}</p></div>
  <div class="card"><h2>«Казино»: если эмитенты не вернут долг</h2>${cs}<p class="note" style="margin-top:10px">Дефолтят самые рискованные эмитенты по рыночной вероятности. Потеря = (1 − возврат ${d.recovery.toFixed(0)} %) × стоимость позиций эмитента; купоны по ним за год не учитываются. База — сценарий «ставка без изменений» (${rkRub(d.base_rub)}).</p></div></div>
  <div class="card"><h2>Выпуски: риск дефолта и запас прочности<span class="sp">нажмите на строку — карточка выпуска; заголовок — сортировка</span></h2><div class="tbl rk-tbl"><table id="rk-tab"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div>
    <p class="note" style="margin-top:10px">PD рынка: из спреда к КБД s и доли возврата R: λ = s / (1 − R), PD(T) = 1 − e<sup>−λT</sup>. Ожидаемая доходность = доходность − PD по рейтингу (1 год) × (1 − R). Без рейтинга (*) берётся рыночная PD. Запас — на сколько п.п. должна вырасти доходность, чтобы убрать результат года (купоны + переоценка) в ноль; для коротких и плавающих бумаг запас велик.</p></div>
  <div class="card"><h2>Допущения и источники</h2><p class="note">${esc(d.sources.pd)}<br><br>${esc(d.sources.recovery)}<br><br>Таблица PD по рейтингу, % за год: ${Object.entries(d.pd_hist_table).map(([k,v])=>k+' '+String(v).replace('.',',')).join(' · ')}.
    <br><br>Оценки по упрощённой модели, справочная информация, не инвестиционная рекомендация. Рыночная PD включает премию за ликвидность и риск, поэтому её завышенное значение не всегда означает близкий дефолт.</p></div>`;
}
function bindRisk(){
  const a=$('#rk-apply');
  if(a)a.onclick=()=>{const q=S.riskQ;if($('#rk-rec'))q.rec=$('#rk-rec').value||'25';if($('#rk-tgt'))q.target=$('#rk-tgt').value;if($('#rk-tax'))q.tax=$('#rk-tax').checked;if($('#rk-hor')){q.hor=$('#rk-hor').value||'3';try{localStorage.setItem('rk_hor',JSON.stringify(q.hor))}catch(e){}}S.risk=null;render()};
  ['#rk-rec','#rk-tgt','#rk-hor'].forEach(i=>{const e=$(i);if(e)e.onkeydown=ev=>{if(ev.key==='Enter')a.click()}});
  const t=$('#rk-tab');if(t)t.querySelector('thead').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;S.rsort={k,d:S.rsort.k===k?-S.rsort.d:(k==='name'?1:-1)};render()};
}
/* ── Сигналы: дешевле/дороже аналогов, история сигналов, возможные замены в портфеле ── */
S.sig={d:null,key:'',err:null,loading:false,f:{rmin:'',sector:'',dmax:'all',turn:'1000000',sort:'z',outl:false,worse:false,more:{c:false,r:false}},fee:'0.3',thr:'1'};
const SG_NOTE='Сравнение с аналогами не учитывает все риски; справочная информация, не инвестиционная рекомендация.';
function sigKey(){const f=S.sig.f;return[S.account,f.turn,S.sig.fee,S.sig.thr].join('|')}
function loadSig(force){
  const k=sigKey();if(S.sig.loading&&!force)return;
  S.sig.loading=true;S.sig.err=null;
  const p=new URLSearchParams({account:S.account,min_turn:S.sig.f.turn,fee:S.sig.fee,threshold:S.sig.thr});if(force)p.set('force','1');
  api('/api/signals?'+p).then(j=>{S.sig.loading=false;S.sig.d=j;S.sig.key=k;if(S.page==='sig')render()})
    .catch(e=>{S.sig.loading=false;S.sig.err=e.message||String(e);S.sig.key=k;if(S.page==='sig')render()});
}
const sgN=(v,d=2)=>v==null||isNaN(v)?'—':Number(v).toFixed(d).replace('.',',');
const sgS=(v,d=2)=>v==null||isNaN(v)?'—':(v>0?'+':'')+sgN(v,d);
function sgSpark(h){
  if(!h||h.length<2)return'';
  const w=64,hh=18,mn=Math.min(...h),mx=Math.max(...h),r=(mx-mn)||1;
  const pts=h.map((v,i)=>(i/(h.length-1)*w).toFixed(1)+','+(hh-2-(v-mn)/r*(hh-4)).toFixed(1)).join(' ');
  return`<svg class="sg-sp" width="${w}" height="${hh}" viewBox="0 0 ${w} ${hh}"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
}
function sgRows(side){
  const f=S.sig.f,d=S.sig.d,dm=f.dmax==='all'?1e9:+f.dmax,ri=f.rmin?RSC.indexOf(f.rmin):99;
  const rs=d.rows.filter(r=>(side>0?r.diff>=d.eps:r.diff<=-d.eps)&&(f.outl||!r.outlier)&&RSC.indexOf(r.rating)<=ri&&r.dur<=dm&&(!f.sector||r.sector===f.sector)&&r.turn>=+f.turn);
  const k={z:r=>Math.abs(r.z),diff:r=>Math.abs(r.diff),streak:r=>r.streak*1e3+Math.abs(r.z),turn:r=>r.turn}[f.sort]||(r=>Math.abs(r.z));
  return rs.sort((a,b)=>k(b)-k(a));
}
function sgTable(side){
  const rs=sgRows(side),d=S.sig.d,key=side>0?'c':'r',more=S.sig.f.more[key],lim=more?60:15,hasH=d.meta.hist_days>=2;
  if(!rs.length)return`<div class="empty" style="padding:26px">Нет выпусков под выбранные фильтры</div>`;
  return`<div class="tbl"><table class="sg-t"><thead><tr><th class="l">Выпуск</th><th>Рейтинг</th><th class="l">Сектор</th><th>Дюр., г.</th><th>Дох., %</th><th>Спред</th><th>Медиана аналогов</th><th>Δ п.п.</th><th title="Отклонение в единицах разброса аналогов (MAD)">z</th><th>Оборот</th>${hasH?'<th title="Сколько снимков подряд выпуск был дешевле/дороже аналогов (снимок раз в день)">Дней подряд</th><th>Тренд</th>':''}</tr></thead><tbody>`
    +rs.slice(0,lim).map(r=>`<tr data-isin="${esc(r.isin)}" title="Аналоги: ${esc(r.refs.map(a=>a.name).join(', '))}"><td class="l"><b>${esc(r.name)}</b>${r.outlier?' <span class="tag" title="Отклонение или доходность аномально велики: возможен дефолтный выпуск или некорректные данные">выброс</span>':''}${r.amort?' <span class="tag">аморт</span>':''}${r.sub?' <span class="tag">суборд</span>':''}<small class="mu sg-isin">${esc(r.isin)}</small></td>
      <td><span class="tag rt rt-${esc(rBucket(r.rating).split(' ')[0])}">${esc(r.rating)}</span></td><td class="l">${esc(SECT[r.sector]||r.sector||'—')}</td>
      <td class="num">${sgN(r.dur)}</td><td class="num">${sgN(r.yield)}</td><td class="num">${sgS(r.spread)}</td><td class="num">${sgS(r.med)}</td>
      <td class="num ${side>0?'pos':'neg'}"><b>${sgS(r.diff)}</b></td><td class="num">${sgS(r.z,1)}</td><td class="num">${short(r.turn)}</td>
      ${hasH?`<td class="num">${r.streak?r.streak:'—'}</td><td class="num sg-tr ${r.trend==null?'':r.trend>0.05?'pos':r.trend<-0.05?'neg':''}">${r.hist?sgSpark(r.hist):''}${r.trend==null?'':' '+sgS(r.trend,1)}</td>`:''}</tr>`).join('')
    +`</tbody></table></div>`+(rs.length>lim?`<button class="btn ghost sg-more" data-m="${key}">Показать больше (${rs.length-lim})</button>`:'')
    +(more&&rs.length>60?'':'');
}
function sgOpt(o,pos){
  const w=o.rating_worse;
  return`<tr data-isin="${esc(o.isin)}"><td class="l"><b>${esc(o.name)}</b>${w?' <span class="tag sg-worse" title="Рейтинг ниже, чем у текущей бумаги: более высокая доходность во многом плата за риск">рейтинг ниже</span>':''}<small class="mu sg-isin">${esc(o.isin)}</small></td>
    <td><span class="tag rt rt-${esc(rBucket(o.rating).split(' ')[0])}">${esc(o.rating)}</span></td><td class="num">${sgN(o.dur)}</td><td class="num">${sgN(o.yield)}</td>
    <td class="num ${o.diff>=0.25?'pos':o.diff<=-0.25?'neg':''}">${sgS(o.diff)}</td><td class="num">${short(o.turn)}</td>
    <td class="num">${sgS(o.gain_pp)}</td><td class="num pos"><b>${sgS(o.net_pp)}</b></td><td class="num">${M(o.gain_rub_year,'rub')}</td><td class="num">${o.breakeven_months==null?'—':sgN(o.breakeven_months,1)}</td></tr>`;
}
function sgRepl(){
  const d=S.sig.d,f=S.sig.f;let h='';
  const rep=d.replacements.map(p=>({p,o:f.worse?p.options.concat(p.options_worse):p.options})).filter(x=>x.o.length);
  if(!rep.length)return`<div class="empty" style="padding:26px">${(S.bonds&&S.bonds.rows&&S.bonds.rows.length)||d.skipped.length?'При заданных порогах и издержках явных вариантов для изучения нет.':'В выбранном портфеле нет облигаций.'}</div>`;
  rep.forEach(({p,o})=>{
    h+=`<div class="sg-pos"><div class="sg-ph" data-isin="${esc(p.isin)}"><div><b>${esc(p.name)}</b> <span class="tag rt rt-${esc(rBucket(p.rating).split(' ')[0])}">${esc(p.rating||'—')}</span></div>
      <div class="mu">позиция ${M(p.value,'rub')} · доходность ${sgN(p.yield_)} % · дюрация ${sgN(p.dur)} г. · ${p.diff==null?'':`к аналогам ${sgS(p.diff)} п.п. · `}издержки перехода ≈ ${M(p.cost_rub,'rub')} (${sgN(p.cost_pp)} % позиции: комиссии ${M(p.commission_rub,'rub')}${p.tax_rub?`, налог с прибыли ${M(p.tax_rub,'rub')}`:''})</div></div>
      <div class="tbl"><table class="sg-t"><thead><tr><th class="l">Возможная замена для изучения</th><th>Рейтинг</th><th>Дюр., г.</th><th>Дох., %</th><th>Δ к аналогам</th><th>Оборот</th><th title="Разница доходностей, п.п. в год">Разница, п.п.</th><th title="Разница за вычетом издержек, размазанных на срок до погашения более короткой из бумаг (не более 5 лет)">После издержек, п.п./год</th><th>₽ в год на позицию</th><th title="За сколько месяцев разница в доходности покроет издержки перехода">Окупаемость, мес.</th></tr></thead><tbody>${o.map(sgOpt).join('')}</tbody></table></div></div>`});
  return h;
}
function pSig(){
  const s=S.sig,f=s.f;
  if(s.key!==sigKey()&&!s.loading){s.d=null;s.err=null}
  if(!s.d){
    if(!s.loading&&!s.err)loadSig();
    chart('sg-root',bindSig);
    return`<div id="sg-root"><div class="card">${s.err?`<div class="msg err">${esc(s.err)} <button class="btn ghost" id="sg-ref">Повторить</button></div>`:waitBox('Сравниваю выпуски с аналогами (первый расчёт может занять до минуты: загружается рынок)…')}</div></div>`}
  const d=s.d,k=d.kpis,m=d.meta;
  const sectors=[...new Set(d.rows.map(r=>r.sector).filter(Boolean))].sort((a,b)=>(SECT[a]||a).localeCompare(SECT[b]||b));
  const opt=(v,t,c)=>`<option value="${v}" ${String(c)===String(v)?'selected':''}>${t}</option>`;
  const nrep=d.replacements.length;
  chart('sg-root',bindSig);
  return`<div id="sg-root">${s.err?`<div class="msg err">${esc(s.err)}</div>`:''}
  <div class="g g4 sg-k">${kpi('Выпусков сравнено',k.universe,`ликвидных, оборот от ${short(d.params.min_turn)} ₽`)}
    ${kpi('Дешевле аналогов',k.cheap,`из них заметно (z ≥ 2): ${k.cheap_strong}`,'pos')}
    ${kpi('Дороже аналогов',k.rich,`из них заметно (z ≤ −2): ${k.rich_strong}`,'neg')}
    ${kpi('Возможных замен в портфеле',nrep,`пороги: от ${sgN(d.params.threshold,1)} п.п. после издержек`)}</div>
  <div class="card"><h2>Дешевле и дороже аналогов<span class="sp">спред к КБД против медианы 12 похожих выпусков</span></h2>
    <p class="note" style="margin-bottom:12px">Для каждой рублёвой корпоративной облигации с рейтингом (без флоатеров и бессрочных) подбираются ближайшие аналоги: рейтинг в пределах двух ступеней, сопоставимая дюрация, сектор, тип выпуска — так же, как в карточке облигации. «Дешевле» — спред к КБД выше медианы аналогов (доходность выше при сопоставимом риске), «дороже» — ниже. z — отклонение в единицах разброса аналогов (робастная оценка по MAD): чем больше |z|, тем заметнее выпуск выделяется на фоне аналогов. Расхождение часто объясняется рисками, которых нет в рейтинге.</p>
    <div class="flt">
      <label class="field"><span>Рейтинг не ниже</span><select class="in" id="sg-r"><option value="">любой</option>${RSC.slice(0,16).map(x=>opt(x,x,f.rmin)).join('')}</select></label>
      <label class="field"><span>Сектор</span><select class="in" id="sg-s"><option value="">любой</option>${sectors.map(x=>opt(x,SECT[x]||x,f.sector)).join('')}</select></label>
      <label class="field"><span>Дюрация не более</span><select class="in" id="sg-d">${[['1','1 года'],['2','2 лет'],['3','3 лет'],['5','5 лет'],['all','любая']].map(([v,t])=>opt(v,t,f.dmax)).join('')}</select></label>
      <label class="field"><span>Оборот за день от</span><select class="in" id="sg-t">${[['0','любой'],['300000','0,3 млн ₽'],['1000000','1 млн ₽'],['5000000','5 млн ₽'],['20000000','20 млн ₽']].map(([v,t])=>opt(v,t,f.turn)).join('')}</select></label>
      <label class="field"><span>Сортировать по</span><select class="in" id="sg-o">${[['z','z-оценке'],['diff','отклонению, п.п.'],['streak','дням подряд'],['turn','обороту']].map(([v,t])=>opt(v,t,f.sort)).join('')}</select></label>
      <label class="sw"><input type="checkbox" id="sg-x" ${f.outl?'checked':''}><i></i><div><b>Показывать выбросы</b><small>${k.outliers} выпусков с аномалиями</small></div></label>
    </div>
    <div class="sg-g2">
      <div><h3 class="sg-h pos">Дешевле аналогов</h3>${sgTable(1)}</div>
      <div><h3 class="sg-h neg">Дороже аналогов</h3>${sgTable(-1)}</div></div>
    <p class="note" style="margin-top:12px">${m.hist_days>=2?`История сигналов копится ежедневно по будним дням (снимок при расчёте): накоплено дней — ${m.hist_days}, с ${ddm(m.hist_from)}. «Дней подряд» — число последних снимков подряд, в которых выпуск оставался дешевле/дороже аналогов не менее чем на ${sgN(d.eps,2)} п.п.; «Тренд» — изменение отклонения за ≈ 5 снимков.`:`История сигналов копится ежедневно по будним дням, начиная с сегодняшнего дня: сейчас накоплено дней — ${m.hist_days}. Колонки «Дней подряд» и «Тренд» появятся, когда снимков будет хотя бы два.`}
    Расчёт: ${sgN(m.calc_s,1)} с, выпусков в сравнении ${m.pool}. Выбросы (отклонение более 8 п.п., доходность выше 40 % или спред ниже −6 п.п.) скрыты по умолчанию.</p></div>
  <div class="card sg-rep"><h2>Возможные замены в вашем портфеле<span class="sp">для изучения, не рекомендация</span></h2>
    <p class="note" style="margin-bottom:12px">Для каждой рублёвой корпоративной облигации портфеля ищутся похожие выпуски (близкие рейтинг, срок, сектор) с более высокой рыночной доходностью. Учитываются комиссия за продажу и покупку, налог ${sgN(d.params.tax,0)} % с прибыли при продаже выше цены покупки (НКД не учитывается), ликвидность целевого выпуска. Издержки равномерно относятся на срок до погашения более короткой из двух бумаг (не более 5 лет). Показываются варианты, где разница после издержек не меньше порога; выпуски с более низким рейтингом показываются только по отдельному переключателю. Бóльшая доходность обычно отражает бóльший риск, а не недооценку.</p>
    <div class="flt">
      <label class="field"><span>Комиссия за сделку, %</span><input class="in" id="sg-fee" type="number" min="0" max="5" step="0.05" value="${esc(s.fee)}"></label>
      <label class="field"><span>Порог после издержек, п.п./год</span><input class="in" id="sg-thr" type="number" min="0" max="20" step="0.5" value="${esc(s.thr)}"></label>
      <label class="sw"><input type="checkbox" id="sg-w" ${f.worse?'checked':''}><i></i><div><b>Показывать с более низким рейтингом</b><small>помечаются отдельно</small></div></label>
      <button class="btn ghost" id="sg-ref">Пересчитать</button>
    </div>
    ${sgRepl()}
    ${d.skipped.length?`<p class="note" style="margin-top:10px">Не сравнивались: ${d.skipped.map(x=>esc(x.name)+' ('+esc(x.why)+')').join('; ')}.</p>`:''}</div>
  <p class="note">${SG_NOTE} Данные: Мосбиржа (ISS), каталог T-Invest, публичные рейтинги; КБД — кривая бескупонной доходности Мосбиржи.</p></div>`;
}
function bindSig(){
  const f=S.sig.f,again=()=>render();
  const on=(id,fn)=>{const e=$(id);if(e)e.onchange=fn};
  on('#sg-r',e=>{f.rmin=e.target.value;again()});on('#sg-s',e=>{f.sector=e.target.value;again()});on('#sg-d',e=>{f.dmax=e.target.value;again()});
  on('#sg-o',e=>{f.sort=e.target.value;again()});on('#sg-x',e=>{f.outl=e.target.checked;again()});on('#sg-w',e=>{f.worse=e.target.checked;again()});
  on('#sg-t',e=>{f.turn=e.target.value;S.sig.d=null;again()});
  const fee=$('#sg-fee'),thr=$('#sg-thr');
  const apply=()=>{S.sig.fee=fee.value||'0.3';S.sig.thr=thr.value||'1';S.sig.d=null;render()};
  if(fee)fee.onchange=apply;if(thr)thr.onchange=apply;
  const r=$('#sg-ref');if(r)r.onclick=()=>{S.sig.d=null;S.sig.err=null;S.sig.key=sigKey();loadSig(true);render()};
  document.querySelectorAll('#sg-root .sg-more').forEach(b=>b.onclick=()=>{f.more[b.dataset.m]=true;render()});
}
/* ── Мониторинг: тревоги по портфелю, ликвидность, спреды ── */
const MON_SEV={high:['Высокая','mon-h'],medium:['Средняя','mon-m'],info:['Инфо','mon-i']};
function monEnsure(){
  const acc=S.account,m=S.mon;
  if(m&&m.acc===acc&&(m.loading||m.error||(m.data&&Date.now()-m.t<6e5)))return;
  S.mon={acc,loading:true,t:Date.now()};
  api('/api/monitor?'+new URLSearchParams({account:acc})).then(d=>{if(S.account!==acc)return;S.mon={acc,data:d,t:Date.now()};
    try{notifyMon(d)}catch(e){}
    if(['mon','dash'].includes(S.page))render()}).catch(e=>{if(S.account!==acc)return;S.mon={acc,error:e.message,t:Date.now()};if(S.page==='mon')render()});
}
function monSpark(sp,w=96,h=26){
  if(!sp||sp.length<3)return'<span class="mu">—</span>';
  const v=sp.map(p=>p[1]),mn=Math.min(...v),mx=Math.max(...v),r=mx-mn||1;
  const pts=v.map((y,i)=>(i/(v.length-1)*(w-2)+1).toFixed(1)+','+(h-3-(y-mn)/r*(h-6)).toFixed(1)).join(' ');
  const up=v[v.length-1]-v[0],c=up>0.3?'var(--neg)':up<-0.3?'var(--pos)':'var(--tx2)';
  return`<svg class="mon-sp" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><title>Спред к КБД за ${sp.length} торг. дней: ${f2(v[0])} → ${f2(v[v.length-1])} п.п.</title><polyline fill="none" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" points="${pts}"/></svg>`;
}
function monAlertHtml(a){
  const[s,c]=MON_SEV[a.severity]||MON_SEV.info,n=(a.isins||[]).length;
  const nm=a.kind==='rating'?`${esc(a.name)}${n?` <small class="mu">· ${esc((a.bonds||[]).slice(0,2).join(', '))}${n>2?' и ещё '+(n-2):''}</small>`:''}`:esc(a.name||'');
  return`<div class="mon-al ${c}" ${a.isin?`data-isin="${esc(a.isin)}"`:''}><span class="mon-sev">${s}</span><span class="mon-d num">${a.date?ddm(a.date):''}</span>
    <div class="mon-b"><b>${nm}</b><span>${esc(a.message)}</span></div>${a.url?`<a href="${esc(a.url)}" target="_blank" rel="noopener" title="Источник">↗</a>`:''}</div>`;
}
function monCard(){
  if(!(S.bonds&&S.bonds.rows&&S.bonds.rows.length))return'';
  monEnsure();
  const m=S.mon;
  if(!m||m.loading)return`<div class="card mon-card noprint"><h2>Тревоги<span class="sp">загружаю…</span></h2><div class="mu" style="font-size:12.5px">Проверяю рейтинги, цены и спреды облигаций портфеля</div></div>`;
  if(m.error||!m.data)return'';
  const al=m.data.alerts.filter(a=>a.severity!=='info'),top=al.slice(0,3);
  return`<div class="card mon-card noprint"><h2>Тревоги<span class="sp">${m.data.summary.high} высоких · ${m.data.summary.medium} средних</span>
    <button class="btn ghost" data-go="mon" style="margin-left:auto;padding:4px 12px;font-size:12px">Мониторинг</button></h2>
    ${top.length?top.map(monAlertHtml).join('')+(al.length>3?`<div class="mu" style="font-size:12px;margin-top:6px">…и ещё ${al.length-3}</div>`:''):'<div class="mon-ok">Значимых тревог по облигациям портфеля нет</div>'}</div>`;
}
function monRatingTag(r){
  if(!r||!r.v)return'<span class="mu">—</span>';
  return`<span class="tag rt rt-${rBucket(r.v).split(' ')[0]}" title="${esc(r.agency||'')}">${esc(r.v)}</span>`
    +(r.outlook?` <small class="${r.neg?'neg':'mu'}">${esc(r.outlook)}</small>`:'')+(r.watch?' <span class="tag mon-w" title="Рейтинг под наблюдением">набл.</span>':'');
}
function pMon(){
  monEnsure();
  const m=S.mon;
  if(!m||m.loading)return`<div class="card">${waitBox('Собираю рейтинговые события, историю цен и спредов… При первом запуске до минуты.')}</div>`;
  if(m.error)return`<div class="msg err">${esc(m.error)} <button class="btn ghost" id="mon-r">Повторить</button></div>`;
  const d=m.data,th=d.thresholds,sm=d.summary;
  const rows=d.rows.map(r=>`<tr data-isin="${esc(r.isin)}" title="Открыть карточку"><td class="l"><b style="font-weight:600">${esc(r.name)}</b><br><small class="mu">${esc(r.ticker||r.isin)}${r.call?' · оферта '+ddm(r.call):''}</small></td>
    <td class="num">${M(r.value_rub,'rub',0)}</td><td class="l">${monRatingTag(r.rating)}</td>
    <td class="num">${r.price!=null?f2(r.price):'—'}</td>
    <td class="num ${cls(r.chg5)}">${r.chg5!=null?pct(r.chg5,1):'—'}</td><td class="num ${cls(r.chg30)}">${r.chg30!=null?pct(r.chg30,1):'—'}</td>
    <td class="num">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread):'—'}</td>
    <td class="num ${r.spread_chg30>0?'neg':r.spread_chg30<0?'pos':''}">${r.spread_chg30!=null?(r.spread_chg30>0?'+':'')+f2(r.spread_chg30):'—'}</td>
    <td>${r.floating?'<small class="mu">флоатер</small>':monSpark(r.spark)}</td>
    <td class="num">${r.turnover_avg!=null?short(r.turnover_avg)+' ₽':'—'}</td>
    <td class="num ${r.days_to_sell==null?(r.no_history?'mu':'neg'):r.days_to_sell>th.mon_sell_days?'neg':''}">${r.no_history?'—':r.days_to_sell==null?'∞':(r.days_to_sell<0.01?'<0,01':f2(r.days_to_sell))}</td>
    <td class="l">${(r.flags||[]).map(f=>`<span class="tag" style="color:var(--neg)">${esc(f)}</span>`).join(' ')}</td></tr>`).join('');
  const fld=(k,t,min,step)=>`<label class="field"><span>${t}</span><input class="in num" id="mt-${k}" type="number" min="${min}" step="${step}" value="${th[k]}"></label>`;
  return`<div class="g g4">${kpi('Высокие',sm.high,'понижение рейтинга, дефолт, сильное падение','neg',S8)}${kpi('Средние',sm.medium,'наблюдение, оферты, умеренное падение','',S4)}
    ${kpi('Информационные',sm.info,'повышения, неликвидность, прогнозы',null,S1)}${kpi('Журнал рейтингов',d.log.events,d.log.since?'событий с '+ddm(d.log.since):'пока пуст',null,S2)}</div>
  ${(d.notes||[]).map(n=>`<div class="msg">${esc(n)}</div>`).join('')}
  <div class="card"><h2>Тревоги<span class="sp">рейтинги — за 90 дней, рынок — на сегодня</span><button class="btn ghost" id="mon-r" style="margin-left:auto;padding:4px 12px;font-size:12px">Обновить</button></h2>
    ${d.alerts.length?d.alerts.slice(0,S.monAll?999:12).map(monAlertHtml).join('')+(d.alerts.length>12?`<button class="btn ghost" id="mon-all" style="margin-top:6px">${S.monAll?'Свернуть':'Показать все ('+d.alerts.length+')'}</button>`:''):'<div class="mon-ok">Тревог нет</div>'}</div>
  ${watchMonGroup()}
  <div class="card"><h2>Облигации портфеля<span class="sp">цены Мосбиржи, спред — доходность минус КБД на дюрации бумаги</span></h2>
    <div class="tbl"><table id="mon-tab"><thead><tr><th class="l">Облигация</th><th>Стоимость</th><th class="l">Рейтинг · прогноз</th><th>Цена, %</th><th>Δ 5 дн.</th><th>Δ 30 дн.</th>
    <th>Спред, п.п.</th><th>Δ спреда 30 дн.</th><th>Спред 90 дн.</th><th>Оборот в день</th><th title="Стоимость позиции / (20 % среднего дневного оборота за 30 дней)">Дней на продажу</th><th class="l">Признаки</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="note" style="margin-top:10px">Оборот — среднее за 30 дней по торговым дням (${d.cal_days} дн.). «Дней на продажу» — сколько дней потребуется, чтобы продать позицию, забирая не более 20 % дневного оборота. Время расчёта: ${d.timings.total} с.</p></div>
  <details class="card"><summary style="cursor:pointer;font-weight:600;color:var(--tx2)">Пороги тревог</summary><div class="mon-th">
    ${fld('mon_drop5','Падение цены за 5 дней, %',0.1,0.5)}${fld('mon_drop30','Падение цены за 30 дней, %',0.1,0.5)}${fld('mon_spread30','Рост спреда за 30 дней, п.п.',0.1,0.5)}
    ${fld('mon_sell_days','Неликвид: дней на продажу более',0.5,0.5)}${fld('mon_offer_days','Оферта: за сколько дней предупреждать',1,1)}
    <button class="btn" id="mon-save" style="align-self:flex-end">Сохранить</button></div>
    <p class="note" style="margin-top:10px">Вдвое превышенный порог даёт высокую важность. Что программа не видит: факт оплаты купона (биржа его не публикует). Дефолт определяется по флагам Мосбиржи, дефолтному рейтингу (D, C) и остановке торгов.</p></details>`;
}
function bindMon(){
  const r=$('#mon-r');if(r)r.onclick=()=>{S.mon=null;render()};
  const al=$('#mon-all');if(al)al.onclick=()=>{S.monAll=!S.monAll;render()};
  const sv=$('#mon-save');
  if(sv)sv.onclick=async()=>{const b={};['mon_drop5','mon_drop30','mon_spread30','mon_sell_days','mon_offer_days'].forEach(k=>b[k]=$('#mt-'+k).value);
    sv.disabled=true;try{await post('/api/config',b);S.cfg=await api('/api/config')}catch(e){}S.mon=null;render()};
}
/* ── Сравнение с рынком: индексы облигаций, фонды ликвидности и облигационные БПИФ ── */
S.bn={};S.bnSel=new Set(['LQDT','RUCBTRNS']);S.bnLoad=null;
const BN_COL={RGBITR:[S2],RUCBTRNS:[S4],RUCBHYTR:[S8],LQDT:[S3],TMON:[S6],SBMM:[S7],AKMM:[S2,1],SBRB:[S4,1],AKMB:[S5,1],TBRU:[S7,1],RUSFAR:[S6,1]};
const BN_LC={d1:'#19a070',d5:'#e3a21a',dm:'#e66767',na:'#8a90a0'};
const bnRub=v=>bad(v)?'—':(v>0?'+':v<0?'−':'')+NF0.format(Math.abs(v))+' ₽';
const bnPct=(v,d=1)=>bad(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',')+' %';
const bnPp=(v,d=1)=>bad(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',')+' п.п.';
function bnKey(){return S.account+'|'+S.period}
function bnLoadData(){
  const key=bnKey();if(S.bnLoad===key)return;S.bnLoad=key;
  const p=new URLSearchParams({account:S.account,period:S.period});
  api('/api/bench?'+p).then(j=>{if(S.bnLoad===key)S.bnLoad=null;S.bn[key]={d:j,t:Date.now()};if(S.page==='bench'&&bnKey()===key)render()})
   .catch(e=>{if(S.bnLoad===key)S.bnLoad=null;S.bn[key]={d:{error:e.message},t:Date.now(),fail:1};if(S.page==='bench'&&bnKey()===key)render()});
}
function bnCur(){const e=S.bn[bnKey()];return e&&Date.now()-e.t<10*60*1000?e:null}
function bnSeries(d){
  const s=d.series,ser=[{n:'Мой портфель',c:S1,hex:'#3987e5',v:s.portfolio,w:2.6}];
  d.bench.forEach(b=>{if(!b.available||!S.bnSel.has(b.code)||!s.bench[b.code])return;const c=BN_COL[b.code]||[S2];
    ser.push({n:b.name,c:c[0],v:s.bench[b.code],w:1.7,dash:!!c[1]})});
  return ser;
}
function bnChart(el){
  const d=bnCur();if(!d||d.d.error)return;const s=d.d.series,short_=d.d.years<0.6;
  const labs=s.dates.map(x=>{if(short_)return ddm(x).slice(0,5);const[y,m]=x.split('-');return MON[+m-1]+' '+y.slice(2)});
  const fp=v=>(Math.round(v*10)/10).toString().replace('.',',')+'%';
  line(el,{h:320,labels:labs,tipLabels:s.dates.map(dlabel),series:bnSeries(d.d),fa:fp,ft:v=>bnPct(v,2),zero:false});
}
function bnChips(d){
  const by={};d.bench.forEach(b=>{(by[b.group]=by[b.group]||[]).push(b)});
  return d.groups.filter(g=>by[g]).map(g=>`<div class="bn-grp"><span class="bn-gl">${esc(g)}</span><div class="bn-chips">${by[g].map(b=>{
    const c=(BN_COL[b.code]||[S2])[0];
    return b.available?`<button type="button" data-c="${b.code}" class="${S.bnSel.has(b.code)?'on':''}" title="${esc(b.note)}"><i style="background:${c}"></i>${esc(b.name)}</button>`
      :`<button type="button" disabled title="${esc(b.reason||'нет данных')}"><i style="background:${c}"></i>${esc(b.name)} · нет данных</button>`}).join('')}</div></div>`).join('');
}
/* окраска ячейки бенчмарка относительно портфеля: красный — бенчмарк в этом лучше вас, зелёный — хуже */
function bnCmp(b,p,hi){if(bad(b)||bad(p)||Math.abs(b-p)<1e-9)return'';return(hi?b>p:b<p)?'neg':'pos'}
function bnTable(d){
  const p=d.portfolio,f1=(v,s='')=>bad(v)?'—':v.toFixed(1).replace('.',',')+s;
  const row=(b,isP)=>{
    const sm=b.same;
    return`<tr${isP?' class="bn-me"':''}><td class="l">${isP?'<b>Мой портфель</b>':`<b>${esc(b.name)}</b>${b.partial?`<br><small class="mu">данные с ${ddm(b.start)}</small>`:''}`}</td>
      <td class="num ${isP?cls(b.ret):bnCmp(b.ret,p.ret,true)}">${bnPct(b.ret)}</td>
      <td class="num ${isP?'':bnCmp(b.ann,p.ann,true)}">${b.ann==null?'<span class="mu">—</span>':bnPct(b.ann)}</td>
      <td class="num ${isP?'':bnCmp(b.vol,p.vol,false)}">${f1(b.vol,' %')}</td>
      <td class="num ${isP?'':bnCmp(b.maxdd,p.maxdd,true)}">${f1(b.maxdd,' %')}</td>
      <td class="num ${isP?'':bnCmp(b.sharpe,p.sharpe,true)}">${bad(b.sharpe)?'—':f2(b.sharpe)}</td>
      <td class="num">${isP?'1,00':bad(b.beta)?'—':f2(b.beta)}</td><td class="num">${isP?'1,00':bad(b.corr)?'—':f2(b.corr)}</td>
      <td class="num">${isP?M(b.value_end,'rub',0):sm?M(sm.final,'rub',0):'—'}</td>
      <td class="num ${isP?'':sm?cls(sm.diff):''}">${isP?'—':sm?bnRub(sm.diff):'—'}</td></tr>`};
  const by={};d.bench.filter(b=>b.available).forEach(b=>{(by[b.group]=by[b.group]||[]).push(b)});
  let h=row(p,true);
  d.groups.filter(g=>by[g]).forEach(g=>{h+=`<tr class="bn-gr"><td class="l" colspan="10">${esc(g)}</td></tr>`+by[g].map(b=>row(b,false)).join('')});
  return`<div class="tbl"><table class="bn-t"><thead><tr><th class="l">Что сравниваем</th><th>Доходность за период</th><th>В пересчёте на год</th><th>Колебания цены за год</th><th>Макс. просадка</th><th>Шарп</th><th>Бета к портфелю</th><th>Корреляция</th><th>Было бы с теми же деньгами</th><th>Вы заработали больше (меньше)</th></tr></thead><tbody>${h}</tbody></table></div>`;
}
function bnLiquidity(d){
  const l=d.liquidity;
  if(!l)return`<div class="card"><h2>Как быстро можно продать</h2><div class="empty" style="padding:24px">Данные о ликвидности недоступны</div></div>`;
  if(!l.bonds_count)return`<div class="card"><h2>Как быстро можно продать</h2><div class="empty" style="padding:24px">В портфеле нет облигаций для оценки ликвидности</div></div>`;
  const items=l.buckets.map(b=>({n:b.label,v:b.share||0,c:BN_LC[b.key],s:`${b.count} шт · ${M(b.value,'rub',0)}`,raw:b}));
  const cov=l.portfolio_value?l.bonds_value/l.portfolio_value*100:null;
  const slow=l.slowest.length?`<div class="tbl" style="margin-top:10px"><table><thead><tr><th class="l">Самые медленные позиции</th><th>Стоимость</th><th>Дней на продажу</th></tr></thead><tbody>${
    l.slowest.map(r=>`<tr${r.isin?` data-isin="${esc(r.isin)}"`:''}><td class="l">${esc(r.name)}</td><td class="num">${M(r.value_rub,'rub',0)}</td><td class="num ${r.days>5?'neg':r.days>1?'':'pos'}">${r.days>=10?Math.round(r.days):f2(r.days)}</td></tr>`).join('')}</tbody></table></div>`:'';
  return`<div class="card"><h2>Как быстро можно продать<span class="sp">облигации в портфеле${cov!=null?', '+cov.toFixed(0)+' % портфеля':''}</span></h2>
    ${hbars(items,'#3987e5',x=>pctp(x.v,0),true)}
    ${slow}
    <p class="note" style="margin-top:10px">«Дней на продажу» — за сколько дней можно продать позицию целиком, если забирать не более ${f2(l.part)} % среднего дневного оборота выпуска, чтобы не двигать цену. Фонд ликвидности (LQDT) продаётся в день сделки, без скидки к цене. Оценка по облигациям; акции и фонды в расчёт не входят.</p></div>`;
}
function bnPremium(d){
  const p=d.premium;
  if(!p)return`<div class="card"><h2>Плата за риск</h2><div class="empty" style="padding:24px">Данные об облигациях недоступны</div></div>`;
  if(p.lqdt==null)return`<div class="card"><h2>Плата за риск</h2><div class="empty" style="padding:24px">Доходность фонда ликвидности сейчас недоступна</div></div>`;
  const pr=(t,v,c,s)=>`<div class="bn-pr"><span>${t}${s?`<small class="mu">${s}</small>`:''}</span><b class="num ${c||''}">${v}</b></div>`;
  const hy=p.high_yield_value>0?`<br>В расчёт «без экстремальных» не вошли выпуски с доходностью выше 100 % (${M(p.high_yield_value,'rub',0)}): это почти всегда признак серьёзных проблем эмитента.`:'';
  const below=p.below&&p.below.length?`<div class="tbl" style="margin-top:10px"><table><thead><tr><th class="l">Облигации с доходностью ниже фонда ликвидности</th><th>Доходность</th><th>Разница</th><th>Стоимость</th></tr></thead><tbody>${
    p.below.map(r=>`<tr${r.isin?` data-isin="${esc(r.isin)}"`:''}><td class="l">${esc(r.name)}</td><td class="num">${pctp(r.ytm,1)}</td><td class="num neg">${bnPp(r.diff)}</td><td class="num">${M(r.value_rub,'rub',0)}</td></tr>`).join('')}</tbody></table></div>
    <p class="note" style="margin-top:8px">Это ${p.below_count} из ${p.count} облигаций (${M(p.below_value,'rub',0)}). За меньшую доходность вы берёте больший риск и теряете в ликвидности: такие бумаги стоит держать только по особой причине (срок, налог, оферта).</p>`
    :'<p class="note" style="margin-top:10px;color:var(--pos)">Все облигации портфеля обещают доходность выше фонда ликвидности.</p>';
  const mainP=p.prem_ytm_ex!=null?p.prem_ytm_ex:p.prem_ytm;
  return`<div class="card"><h2>Плата за риск<span class="sp">доходность облигаций против фонда ликвидности</span></h2>
    ${pr('Фонд ликвидности LQDT',pctp(p.lqdt,1),'','по росту пая за 30 дней, в пересчёте на год')}
    ${pr('Ваши облигации — доходность к погашению',p.ytm_ex!=null?pctp(p.ytm_ex,1):'—','','средневзвешенная, без выпусков выше 100 %')}
    ${pr('Облигации портфеля — единая доходность (IRR)',p.irr!=null?pctp(p.irr,1):'—','','все будущие выплаты против стоимости сегодня')}
    ${pr('Премия за риск',mainP!=null?bnPp(mainP):'—',mainP!=null?cls(mainP):'','на сколько облигации обещают больше LQDT')}
    ${below}
    <p class="note" style="margin-top:10px">Доходность облигаций — обещанная при условии, что эмитент всё выплатит; она до налогов и не учитывает риск дефолта. Если премия мала, а риск высок, вы почти ничего не получаете сверх безрискового варианта.${hy}</p></div>`;
}
function pBench(){
  const e=bnCur();
  if(!e){bnLoadData();return`<div class="card">${waitBox('Сравниваю портфель с индексами и фондами Мосбиржи. Первый раз это может занять несколько минут (загружается история цен и оценивается ликвидность), потом данные берутся из локального кэша…')}</div>`}
  const d=e.d;
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="bn-retry">Повторить</button></div>`;
  const p=d.portfolio,B=c=>d.bench.find(b=>b.code===c&&b.available),lq=B('LQDT'),cb=B('RUCBTRNS');
  const l=d.liquidity,fast=l&&l.bonds_count?(l.buckets.find(b=>b.key==='d1')||{}).share:null;
  const pr=d.premium,prem=pr&&pr.lqdt!=null?(pr.prem_ytm_ex!=null?pr.prem_ytm_ex:pr.prem_ytm):null;
  const sm=lq&&lq.same;
  chart('bn-chart',bnChart);
  const kp=`<div class="g g6">
    ${kpi('Ваша доходность',bnPct(p.ret,2),`LQDT: ${lq?bnPct(lq.ret,1):'—'} · корп. облигации: ${cb?bnPct(cb.ret,1):'—'}`,cls(p.ret),S1)}
    ${kpi('Те же деньги в LQDT',sm?bnRub(sm.diff):'—',sm?(sm.diff>=0?'вы заработали больше, чем дал бы фонд ликвидности':'фонд ликвидности дал бы больше, чем вы заработали'):'нет данных по LQDT',sm?cls(sm.diff):'',S3)}
    ${kpi('Доходность в годовых (XIRR)',p.xirr==null?'—':bnPct(p.xirr,1),p.xirr==null?'период короче 3 месяцев':`LQDT с теми же вложениями: ${sm&&sm.xirr!=null?bnPct(sm.xirr,1):'—'}`,cls(p.xirr),S7)}
    ${kpi('Коэффициент Шарпа',bad(p.sharpe)?'—':f2(p.sharpe),'доходность сверх безрисковой ставки на единицу риска',p.sharpe>0?'pos':p.sharpe<0?'neg':'',S2)}
    ${kpi('Продаётся за 1 день',fast==null?'—':pctp(fast,0),'доля облигаций, которую можно продать за день',fast!=null&&fast<70?'neg':'',S5)}
    ${kpi('Премия к LQDT',prem==null?'—':bnPp(prem),pr&&pr.lqdt!=null?`LQDT даёт ≈ ${pctp(pr.lqdt,1)} годовых`:'доходность LQDT недоступна',prem==null?'':cls(prem),S4)}</div>`;
  const notes=(d.notes||[]).length?`<div class="msg info" style="margin:0 0 12px">${d.notes.map(esc).join('<br>')}</div>`:'';
  return kp+notes+`<div class="card"><h2>Накопленная доходность<span class="sp">${periodName()}: ${ddm(d.start)} — ${ddm(d.end)}</span></h2>
    <div class="bn-sel" id="bn-sel">${bnChips(d)}</div><div id="bn-chart" class="chart"></div>
    <p class="note" style="margin-top:8px">Показано, на сколько процентов выросли вложения с начала периода. Линия портфеля — по методу TWR: пополнения и выводы не искажают результат.</p></div>
  <div class="card"><h2>Сравнение по показателям<span class="sp">красным выделено то, в чём бенчмарк лучше вашего портфеля, зелёным — где хуже</span></h2>${bnTable(d)}
    <p class="note" style="margin-top:10px">«Колебания цены» — насколько сильно портфель «качается» (годовое стандартное отклонение дневных изменений по торговым дням Мосбиржи). «Макс. просадка» — самое большое падение от пика до дна. «Шарп» — доходность сверх ставки RUSFAR (безрисковая ставка межбанка) на единицу колебаний; для фондов ликвидности он малоинформативен, потому что колебаний почти нет, а для периода короче нескольких месяцев — шумный. «Бета» показывает, на сколько процентов в среднем меняется ваш портфель при изменении бенчмарка на 1 %, «корреляция» — насколько они движутся вместе (от −1 до 1). «Было бы с теми же деньгами» — во что превратились бы стоимость портфеля на начало периода и все ваши пополнения и выводы, если бы в те же дни их вложили в этот бенчмарк.</p></div>
  <div class="g g2 bn-g">${bnLiquidity(d)}${bnPremium(d)}</div>
  <div class="card"><h2>Как читать этот раздел</h2><div class="note bn-expl">
    <p><b>Почему сравнение «те же деньги» честнее.</b> Доходность TWR показывает, насколько хорошо работали сами активы, и не зависит от того, когда вы пополняли счёт. Но вам важнее другое: заработали ли вы больше, чем если бы в те же дни положили те же суммы в фонд ликвидности или индекс. Сравнение «те же деньги» отвечает именно на этот вопрос, а итог показан в рублях.</p>
    <p><b>Комиссии и налоги.</b> Комиссии управляющих фондов уже учтены в цене пая: отдельно их вычитать не нужно. Налоги не учтены ни у портфеля, ни у бенчмарков. У фондов налог платится только при продаже пая, а после 3 лет владения может действовать льгота долгосрочного владения (ЛДВ). Купоны облигаций облагаются налогом сразу.</p>
    <p><b>Что за индексы.</b> Индексы полной доходности учитывают купоны и потому сопоставимы с портфелем. Индекс ВДО — облигации небольших компаний с повышенным риском (высокодоходные облигации): они платят больше, но дефолты и резкие просадки там заметно чаще. Облигационные фонды из списка не выплачивают доход пайщикам, он остаётся в цене пая, поэтому их цена честно отражает доходность. Фонды ликвидности вкладывают деньги в короткие сделки РЕПО, их доходность близка к ключевой ставке.</p>
    <p>Прошлая доходность не гарантирует будущую. Раздел носит справочный характер и не является инвестиционной рекомендацией. Данные индексов и фондов — Московская биржа (ISS), с задержкой в один день.</p></div></div>`;
}
function bindBench(){
  const r=$('#bn-retry');if(r)r.onclick=()=>{delete S.bn[bnKey()];S.bnLoad=null;render()};
  const sel=$('#bn-sel');
  if(sel)sel.onclick=e=>{const b=e.target.closest('button[data-c]');if(!b||b.disabled)return;const c=b.dataset.c;
    if(S.bnSel.has(c))S.bnSel.delete(c);else S.bnSel.add(c);b.classList.toggle('on',S.bnSel.has(c));const el=$('#bn-chart');if(el)bnChart(el)};
}
/* калькулятор инвестиций */
/* ── Чистая часть: модель (без DOM, считается на клиенте) ── */
const CL_BR=[[2.4e6,.13],[5e6,.15],[20e6,.18],[50e6,.20],[Infinity,.22]];   /* шкала НДФЛ: 13 % до 2,4 млн ₽ в год, далее 15/18/20/22 % с части дохода */
const CL_STR=[['dep','Вклад','#8a93a6'],['fund','Фонд ликвидности','#19a070'],['ofz','ОФЗ','#3987e5'],['aaa','Корпоративные AAA','#7ab4f5'],['aa','Корпоративные AA','#9085e9'],
  ['a','Корпоративные A','#c98500'],['hy','ВДО (BB и ниже)','#e66767'],['pf','Мой портфель','#d55181'],['own','Своя ставка','#d95926']];
const CL_BETA={ofz:.6,aaa:.7,aa:.7,a:.7,hy:.7};
const CL_ACC=[['plain','Обычный брокерский счёт'],['iisA','ИИС типа А (вычет с взносов)'],['iisB','ИИС типа Б (доход без налога)'],['iis3','ИИС-3 (вычет и освобождение дохода)']];
function clNdfl(b){if(!(b>0))return 0;let t=0,lo=0;for(const[h,r]of CL_BR){if(b>lo)t+=(Math.min(b,h)-lo)*r;lo=h;if(b<=h)break}return t}
function clTaxInc(inc,x){return clNdfl(inc+x)-clNdfl(inc)}
/* значения рынка по умолчанию, если сервер не ответил */
function clDefaultParams(){
  const k=16;return{key_rate:{current:k,source:'условное значение',estimate:true,path:[]},inflation:{yearly:[],default:4,estimate:true},
    segments:{ofz:{name:'ОФЗ',yield:k-.5,dur:4,loss:0,estimate:true},aaa:{name:'Корпоративные AAA',yield:k+.5,dur:2.5,loss:.04,estimate:true},aa:{name:'Корпоративные AA',yield:k+1.5,dur:2.5,loss:.15,estimate:true},
    a:{name:'Корпоративные A',yield:k+3,dur:2,loss:.6,estimate:true},hy:{name:'ВДО (BB и ниже)',yield:k+8,dur:1.5,loss:3.2,estimate:true}},
    lqdt:{yield:k-.7,estimate:true,spread:.7},deposit:{spread:1.5},portfolio:null,fallback:true};
}
/* окружение: путь ключевой ставки по сценарию, дефлятор, ставка фонда */
function clEnv(P,F,startDate){
  const sd=startDate||new Date(),y0=sd.getFullYear(),m0=sd.getMonth(),M=721;
  const path=(P.key_rate.path||[]).map(x=>+x[1]).filter(x=>isFinite(x)),kr0=+P.key_rate.current||16;
  const base=k=>path.length?path[Math.min(k,path.length-1)]:kr0;
  const key=k=>{const b=base(k);
    if(F.scn==='hard')return b+2;if(F.scn==='soft')return Math.min(b,Math.max(b-2,4));if(F.scn==='own')return +F.ownKey||kr0;return b};
  const iy={};(P.inflation.yearly||[]).forEach(x=>{iy[x.year]=x.mid});
  const iyears=Object.keys(iy).map(Number),last=iyears.length?iy[Math.max(...iyears)]:(P.inflation.default!=null?P.inflation.default:4);
  const D=[1];for(let k=1;k<M;k++){const yr=y0+Math.floor((m0+k-1)/12),i=iy[yr]!=null?iy[yr]:last;D.push(D[k-1]*Math.pow(1+i/100,1/12))}
  const lq=P.lqdt||{yield:kr0-.7,estimate:true,spread:.7};
  const fsp=lq.estimate?(lq.spread!=null?lq.spread:.7):Math.max(0,Math.min(3,kr0-lq.yield));
  const fundRate=k=>(!lq.estimate&&k<2)?lq.yield:Math.max(key(k)-fsp,.1);
  const dsp=F.depSpread!=null?+F.depSpread:(P.deposit?P.deposit.spread:1.5);
  return{key,kr0,D,fundRate,depRate:k=>Math.max(key(k)-dsp,.1),y0,m0,infl:last,iy};
}
function clContrib(p,k){return k===0?p.start:(k<=p.months?p.monthly*Math.pow(1+p.idx/100,Math.floor((k-1)/12)):0)}
function clAccInfo(p){
  const a=p.acct,N=p.months;
  return{ded:a==='iisA'||a==='iis3',exempt:(a==='iisB'&&N>=36)||(a==='iis3'&&N>=60),cap:a==='iis3'?30e6:Infinity,iis:a!=='plain'};
}
/* вычет ИИС: сумма и точка начисления (конец года) */
function clRefunds(p,ai){
  const N=p.months,R=new Array(N+1).fill(0);if(!ai.ded)return R;
  const yc={};for(let k=0;k<=N;k++){const y=k===0?0:Math.floor((k-1)/12);yc[y]=(yc[y]||0)+clContrib(p,k)}
  for(const y in yc){const pt=Math.min(12*(+y+1),N);R[pt]+=Math.min(yc[y],400e3)*.13}
  return R;
}
function clIrr(fl){          /* fl[k] — поток в месяц k; возвращает годовую эффективную доходность, % */
  let lo=-.5,hi=1;const f=r=>{let s=0;for(let k=0;k<fl.length;k++)s+=fl[k]/Math.pow(1+r,k);return s};
  if(!fl.some(x=>x<0)||!fl.some(x=>x>0))return null;
  if(f(lo)*f(hi)>0)return null;
  for(let i=0;i<80;i++){const m=(lo+hi)/2;if(f(lo)*f(m)<=0)hi=m;else lo=m}
  return(Math.pow(1+(lo+hi)/2,12)-1)*100;
}
function clFinish(r,p,env,yEnd,lossEnd){
  const N=p.months,capN=r.cap[N];
  const inc=Math.max(0,capN*(yEnd-lossEnd)/100);
  r.passive=(inc-clNdfl(inc))/12;
  r.passiveReal=r.passive/env.D[N];r.final=capN;r.finalReal=capN/env.D[N];
  r.income=capN-r.deposited-r.deductions;
  const fl=new Array(N+1).fill(0);for(let k=0;k<=N;k++)fl[k]-=clContrib(p,k);fl[N]+=capN;r.xirr=clIrr(fl);
  r.yEnd=yEnd;return r;
}
/* Вклад: ежемесячная капитализация; НДФЛ с процентов сверх необлагаемого порога (1 млн ₽ × макс. ключевая ставка года) */
function clSimDep(p,env){
  const N=p.months;let B=0,dep=0,iy=0,mk=0;const cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[]};
  for(let k=0;k<=N;k++){
    if(k>0){const rt=env.depRate(k-1);const g=B*rt/1200;B+=g;iy+=g;mk=Math.max(mk,env.key(k-1));
      if(k%12===0||k===N){const thr=1e6*mk/100,tx=clNdfl(Math.max(0,iy-thr));B-=tx;r.taxes+=tx;iy=0;mk=0}}
    const c=clContrib(p,k);B+=c;dep+=c;cap.push(B);
  }
  r.deposited=dep;return clFinish(r,p,env,env.depRate(Math.max(N-1,0)),0);
}
/* Фонд ликвидности: накопление пая, налог только при продаже (или ЛДВ / ИИС) */
function clSimFund(p,env){
  const N=p.months,ai=clAccInfo(p),RF=clRefunds(p,ai);const G=[1];
  for(let k=0;k<N;k++)G.push(G[k]*(1+env.fundRate(k)/1200));
  const lots=[],cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[]};let idle=0;
  const saleTax=k=>{
    let gain=0,eg=0,old=Infinity,val=0;
    for(const l of lots){const v=l.amt*G[k]/G[l.k0],g=v-l.amt;gain+=g;if(p.ldv&&!ai.iis&&k-l.k0>=36){eg+=g;old=Math.min(old,l.k0)}}
    let taxable=gain;
    if(ai.iis&&ai.exempt)taxable=Math.max(0,gain-ai.cap);
    else if(p.ldv&&!ai.iis&&eg>0)taxable=Math.max(0,gain-Math.min(eg,3e6*(k-old)/12));
    return clNdfl(taxable);
  };
  for(let k=0;k<=N;k++){
    if(RF[k]>0){if(p.reinvDed)lots.push({k0:k,amt:RF[k]});else idle+=RF[k];r.deductions+=RF[k]}
    const c=clContrib(p,k);if(c>0){lots.push({k0:k,amt:c});r.deposited+=c}
    let v=idle;for(const l of lots)v+=l.amt*G[k]/G[l.k0];
    cap.push(v-saleTax(k));
  }
  r.taxes=saleTax(N);
  return clFinish(r,p,env,env.fundRate(Math.max(N-1,0)),0);
}
/* Облигации с фиксированным купоном (держим до погашения) и «ставка + купонный налог» */
function clSimBond(id,p,env,seg){
  const N=p.months,ai=clAccInfo(p),RF=clRefunds(p,ai),f=p.freq,per=Math.max(1,Math.round(12/f));
  const y0=seg.yield,beta=seg.beta||0,matM=seg.dur>0?Math.max(Math.round(seg.dur*12),per):Infinity,loss=p.defaults?(seg.loss||0):0;
  const ynew=k=>k===0?y0:Math.max(.5,y0+beta*(env.key(k)-env.kr0));
  const tr=[],cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[]},incY={};
  let cashInv=0,idle=0,pot=0,incTot=0;const useLot=p.lot>1;
  for(let k=0;k<=N;k++){
    if(k>0){
      const yi=Math.floor((k-1)/12);incY[yi]=incY[yi]||0;
      if(pot>0){const g=pot*env.fundRate(k-1)/1200,tx=clTaxInc(incY[yi],g);incY[yi]+=g;incTot+=g;r.taxes+=tx;pot+=g-tx}
      let coup=0,prin=0;
      for(let i=tr.length-1;i>=0;i--){const t=tr[i];
        if(loss)t.amt*=1-loss/1200;
        if(k>t.k0&&k<=t.mat&&(k-t.k0)%per===0)coup+=t.amt*t.y/100/f;
        if(k===t.mat){prin+=t.amt;tr.splice(i,1)}}
      const tx=clTaxInc(incY[yi],coup);incY[yi]+=coup;incTot+=coup;r.taxes+=tx;
      if(p.reinvest)cashInv+=coup-tx;else idle+=coup-tx;
      cashInv+=prin;
    }
    if(RF[k]>0){if(p.reinvDed)cashInv+=RF[k];else idle+=RF[k];r.deductions+=RF[k]}
    const c=clContrib(p,k);cashInv+=c;r.deposited+=c;
    const avail=cashInv+pot;
    if(avail>0.005){const amt=useLot?Math.floor(avail/p.lot+1e-9)*p.lot:avail;
      if(amt>0)tr.push({k0:k,amt,y:ynew(k),mat:k+matM});
      const rem=avail-amt;if(p.lotFund){cashInv=0;pot=rem}else{cashInv=rem;pot=0}}
    let v=idle+cashInv+pot;for(const t of tr)v+=t.amt;cap.push(v);
  }
  /* ИИС Б / ИИС-3: налог, удержанный в течение срока, возвращается при закрытии (для ИИС-3 — до 30 млн ₽ дохода) */
  if(ai.iis&&ai.exempt&&r.taxes>0){const share=incTot>ai.cap?ai.cap/incTot:1,rf=r.taxes*share;cap[N]+=rf;r.deductions+=rf}
  return clFinish(r,p,env,ynew(N),loss);
}
function clSegOf(id,P,F){
  if(id==='pf'){const pf=P.portfolio;return{yield:pf&&pf.irr!=null?pf.irr:10,dur:0,beta:0,loss:0}}
  if(id==='own')return{yield:+F.ownRate||0,dur:0,beta:0,loss:0};
  const s=P.segments[id];return{yield:s.yield,dur:s.dur,beta:CL_BETA[id]||.7,loss:s.loss};
}
function clSim(id,p,P,env,F){
  if(id==='dep')return clSimDep(p,env);
  if(id==='fund')return clSimFund(p,env);
  return clSimBond(id,p,env,clSegOf(id,P,F));
}
function clParams(F,months){
  return{start:+F.start||0,monthly:+F.monthly||0,idx:+F.idx||0,months:months||Math.round((+F.years||1)*12),acct:F.acct,reinvest:!!F.reinvest,freq:+F.freq||12,
    lot:+F.lot||0,lotFund:F.lotFund==='fund',reinvDed:!!F.reinvDed,ldv:!!F.ldv,defaults:!!F.defaults};
}
/* Цель: нужное ежемесячное пополнение при заданном сроке или нужный срок при заданном пополнении (бисекция) */
function clGoal(F,P,env,sid){
  const T=+F.goalAmt||0,pas=(months,monthly)=>{const p=clParams(F,months);p.monthly=monthly;return clSim(sid,p,P,env,F).passiveReal};
  if(F.goalMode==='years'){
    const m=clParams(F).monthly;let lo=1,hi=600;
    if(pas(hi,m)<T)return{ok:false};
    if(pas(lo,m)>=T)return{ok:true,months:1};
    while(hi-lo>1){const mid=(lo+hi)>>1;if(pas(mid,m)>=T)hi=mid;else lo=mid}
    return{ok:true,months:hi};
  }
  const N=clParams(F).months;let lo=0,hi=1000;
  if(pas(N,0)>=T)return{ok:true,monthly:0};
  while(pas(N,hi)<T&&hi<1e9)hi*=2;
  if(pas(N,hi)<T)return{ok:false};
  for(let i=0;i<40;i++){const mid=(lo+hi)/2;if(pas(N,mid)>=T)hi=mid;else lo=mid}
  return{ok:true,monthly:hi};
}

/* ── Интерфейс ── */
const CL_DEF={start:500000,monthly:20000,idx:5,years:10,strat:{dep:1,fund:1,ofz:1,aa:1,a:1},ownRate:15,reinvest:true,freq:4,lot:1000,lotFund:'fund',scn:'cbr',ownKey:12,
  acct:'plain',reinvDed:true,ldv:true,defaults:true,real:true,depSpread:1.5,goalOn:false,goalAmt:100000,goalMode:'contrib',goalStrat:'ofz'};
let CL_F=null;
function clLoadF(){
  if(CL_F)return CL_F;
  const F=JSON.parse(JSON.stringify(CL_DEF));
  try{const s=JSON.parse(localStorage.getItem('ta_calc')||'null');
    if(s&&typeof s==='object')for(const k in F){if(s[k]!==undefined&&typeof s[k]===typeof F[k])F[k]=k==='strat'?Object.assign({},s[k]):s[k]}}catch(e){}
  return CL_F=F;
}
function clSave(){try{localStorage.setItem('ta_calc',JSON.stringify(CL_F))}catch(e){}}
function clLoad(){
  if(S._calcLoading)return;S._calcLoading=1;const acc=S.account;
  api('/api/calc?account='+encodeURIComponent(acc)).then(j=>{S._calcLoading=0;S.calcP=j&&!j.error&&j.key_rate?j:null;S.calcErr=S.calcP?null:((j&&j.error)||'нет данных');S.calcAcc=acc;if(S.page==='calc')render()})
   .catch(e=>{S._calcLoading=0;S.calcP=null;S.calcErr=e.message;S.calcAcc=acc;if(S.page==='calc')render()});
}
const clYM=(m)=>{const y=Math.floor(m/12),mm=m%12;return(y?y+' '+(y%10===1&&y!==11?'год':y%10>=2&&y%10<=4&&(y<10||y>20)?'года':'лет'):'')+(y&&mm?' ':'')+(mm?mm+' мес.':'')||'0 мес.'};
const clRub=v=>M(v,'rub',0);
function clAvail(P){return CL_STR.filter(s=>s[0]!=='pf'||(P.portfolio&&P.portfolio.irr!=null))}
function clRun(F,P){
  const env=clEnv(P,F),p=clParams(F),N=p.months,ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  const res=ids.map(id=>{const s=CL_STR.find(x=>x[0]===id),r=clSim(id,p,P,env,F);r.id=id;r.name=s[1];r.color=s[2];return r});
  return{env,p,N,res};
}
function clSegTable(P,F,env){
  const rows=[];
  rows.push(['Ключевая ставка сейчас',pctp(P.key_rate.current,2),P.key_rate.estimate?'оценка':P.key_rate.source]);
  const at=k=>pctp(env.key(k),1);
  rows.push(['Ключевая через 1 / 2 / 3 года (выбранный сценарий)',at(12)+' / '+at(24)+' / '+at(36),'']);
  rows.push(['Инфляция (по годам)',(P.inflation.yearly&&P.inflation.yearly.length?P.inflation.yearly.map(y=>y.year+': '+pctp(y.mid,1)).join('; '):pctp(P.inflation.default,1)+' в год'),P.inflation.estimate?'оценка':'прогноз Банка России']);
  rows.push(['Вклад: ставка',pctp(env.depRate(0),2),'ключевая − '+f2(F.depSpread)+' п.п.']);
  rows.push(['Фонд ликвидности: доходность',pctp(env.fundRate(0),2),P.lqdt.estimate?'оценка: ключевая − '+f2(P.lqdt.spread)+' п.п.':'по данным фонда']);
  ['ofz','aaa','aa','a','hy'].forEach(id=>{const s=P.segments[id];if(!s)return;
    rows.push([s.name+': доходность / срок',pctp(s.yield,2)+' / '+f2(s.dur)+' г.','потери от дефолтов '+f2(s.loss)+' % в год'+(s.estimate?' · оценка':'')])});
  if(P.portfolio&&P.portfolio.irr!=null)rows.push(['Мой портфель: доходность облигаций',pctp(P.portfolio.irr,2),'IRR по потокам облигаций']);
  return`<div class="tbl"><table><thead><tr><th class="l">Параметр</th><th>Значение</th><th class="l">Источник / примечание</th></tr></thead><tbody>${
    rows.map(r=>`<tr><td class="l">${r[0]}</td><td class="num">${r[1]}</td><td class="l mu">${r[2]}</td></tr>`).join('')}</tbody></table></div>`;
}
function clOut(){
  const F=clLoadF(),P=(S.calcAcc===S.account&&S.calcP)||clDefaultParams();
  const ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  if(!ids.length)return`<div class="card empty">Выберите хотя бы одну стратегию для сравнения</div>`;
  const run=clRun(F,P),{env,N,res,p}=run,real=F.real;
  const labels=[],tips=[];
  for(let k=0;k<=N;k++){const d=new Date(env.y0,env.m0+k,1),mm=String(d.getMonth()+1).padStart(2,'0');labels.push(mm+'.'+d.getFullYear());tips.push(mm+'.'+d.getFullYear()+' · '+(k?clYM(k):'сейчас'))}
  const cd=[];let acc=0;for(let k=0;k<=N;k++){acc+=real?clContrib(p,k)/env.D[k]:clContrib(p,k);cd.push(acc)}
  const series=res.map(r=>({n:r.name,c:r.color,v:r.cap.map((v,k)=>real?v/env.D[k]:v)}));
  series.push({n:'Внесено своих денег',c:'#9aa3b5',dash:1,w:1.6,v:cd});
  chart('cl-chart',line,{h:320,series,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных'});
  const best=res.slice().sort((a,b)=>b.finalReal-a.finalReal)[0],dep=res[0].deposited,defl=env.D[N];
  const kp=`<div class="g g4">${kpi('Внесено своих денег',clRub(dep),'за '+clYM(N),null,S1)}
    ${kpi('Лучший итог',clRub(real?best.finalReal:best.final),esc(best.name)+(real?' · в сегодняшних деньгах':' · номинал'),'pos',S3)}
    ${kpi('Пассивный доход в месяц',clRub(real?best.passiveReal:best.passive),'после налога, '+esc(best.name),null,S4)}
    ${kpi('Удорожание цен за срок','×'+f2(defl),'1 ₽ через '+clYM(N)+' ≈ '+f2(1/defl)+' ₽ сегодня',null,S8)}</div>`;
  const th=['Стратегия','Итоговый капитал','Внесено','Получено дохода','Уплачено налогов','Вычеты и возвраты ИИС','Капитал в сегодняшних деньгах','Пассивный доход в месяц (после налога)','Эффективная годовая доходность'];
  const rows=res.map(r=>`<tr><td class="l"><i class="cl-dot" style="background:${r.color}"></i>${esc(r.name)}</td><td class="num"><b>${clRub(r.final)}</b></td><td class="num">${clRub(r.deposited)}</td>
    <td class="num ${cls(r.income)}">${clRub(r.income)}</td><td class="num">${clRub(r.taxes)}</td><td class="num">${r.deductions>0?clRub(r.deductions):'—'}</td><td class="num"><b>${clRub(r.finalReal)}</b></td>
    <td class="num">${clRub(r.passive)}<br><small class="mu">${clRub(r.passiveReal)} сегодня</small></td><td class="num">${r.xirr==null?'—':pctp(r.xirr,1)}</td></tr>`).join('');
  const tbl=`<div class="card"><h2>Сравнение стратегий<span class="sp">через ${clYM(N)}</span></h2><div class="tbl"><table><thead><tr>${th.map((t,i)=>`<th class="${i?'':'l'}">${t}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="note" style="margin-top:10px">«Итоговый капитал» — если закрыть позиции в конце срока: с уже удержанными налогами и (для фонда ликвидности) налогом при продаже. «Эффективная годовая доходность» — XIRR взносов против итога (номинальная, без учёта инфляции). «Получено дохода» = итог − внесено − вычеты.</div></div>`;
  const warn=[];
  if(F.acct!=='plain'){
    if(res.some(r=>r.id==='dep'))warn.push('Вклад лежит в банке, а не на ИИС: вычет и льготы ИИС к нему не применяются, налог считается как на обычном счёте.');
    if((p.start+p.monthly*12)>1e6)warn.push('Взносы на ИИС ограничены 1 млн ₽ в год: калькулятор этот лимит не проверяет, проверьте свои суммы.');
    if(F.acct==='iisB'&&N<36)warn.push('Освобождение дохода на ИИС типа Б действует при сроке от 3 лет: при меньшем сроке налог не возвращается.');
    if(F.acct==='iis3'&&N<60)warn.push('ИИС-3: освобождение дохода (до 30 млн ₽) принято при сроке владения от 5 лет; при меньшем сроке налог не возвращается.');
    if(F.acct==='iis3'&&N>=60)warn.push('Допущение ИИС-3: минимальный срок для освобождения дохода принят равным 5 годам, лимит освобождаемого дохода 30 млн ₽; вычет считается как на ИИС типа А (13 % от взносов до 400 тыс. ₽ в год).');
  }
  if(F.acct==='plain'&&res.some(r=>r.id==='fund')&&F.ldv)warn.push('ЛДВ для фонда ликвидности: рост пая без налога при владении 3 года и более, лимит 3 млн ₽ × число лет. Каждое пополнение учитывается отдельно по сроку владения.');
  if(P.portfolio==null&&F.strat.pf)warn.push('Нет данных о портфеле — «Мой портфель» недоступен.');
  const wn=warn.length?`<div class="note" style="margin-top:12px">${warn.map(w=>'• '+esc(w)).join('<br>')}</div>`:'';
  return`${kp}<div class="card"><h2>Рост капитала<span class="sp">${real?'в сегодняшних деньгах (с поправкой на инфляцию)':'в номинальных рублях'}</span></h2><div id="cl-chart" class="chart"></div>${wn}</div>${tbl}${clGoalHtml(F,P,run)}
    <div class="card"><h2>Что заложено в расчёт</h2>${clSegTable(P,F,env)}</div>`;
}
function clGoalHtml(F,P,run){
  if(!F.goalOn)return'';
  const ids=run.res.map(r=>r.id);if(!ids.length)return'';
  const sid=ids.includes(F.goalStrat)?F.goalStrat:ids[0],s=CL_STR.find(x=>x[0]===sid),g=clGoal(F,P,run.env,sid);
  let t;
  if(!g.ok)t=`Для стратегии «${esc(s[1])}» цель ${clRub(F.goalAmt)} в месяц ${F.goalMode==='years'?'недостижима и за 50 лет при таком пополнении':'недостижима при заданном сроке даже при очень больших пополнениях'}.`;
  else if(F.goalMode==='years')t=g.months<=1?`Цель ${clRub(F.goalAmt)} в месяц достигается сразу: стартовой суммы достаточно.`:
    `Чтобы получать ${clRub(F.goalAmt)} в месяц (в сегодняшних деньгах, после налога) на стратегии «${esc(s[1])}», при пополнении ${clRub(F.monthly)} в месяц понадобится около <b>${clYM(g.months)}</b>.`;
  else t=g.monthly<=0?`Цель ${clRub(F.goalAmt)} в месяц за ${clYM(run.N)} достигается и без ежемесячных пополнений: хватает стартовой суммы.`:
    `Чтобы через ${clYM(run.N)} получать ${clRub(F.goalAmt)} в месяц (в сегодняшних деньгах, после налога) на стратегии «${esc(s[1])}», нужно пополнять примерно <b>${clRub(g.monthly)}</b> в месяц (с ежегодной индексацией ${f2(F.idx)} %).`;
  return`<div class="card cl-goal"><h2>Цель: пассивный доход</h2><div class="cl-ans">${t}</div><div class="note" style="margin-top:8px">Пассивный доход — это проценты или купоны, которые приносит накопленный капитал в год, делённые на 12, после налога. Пересчитывается в сегодняшние деньги по прогнозу инфляции.</div></div>`;
}
function pCalc(){
  const F=clLoadF();
  const ld=S.calcAcc!==S.account;if(ld)clLoad();
  const P=(!ld&&S.calcP)||clDefaultParams(),pf=P.portfolio,fb=!ld&&!S.calcP;
  const num=(id,l,v,o)=>`<label class="field"><span>${l}</span><input class="in" id="cl-${id}" type="number" inputmode="decimal" value="${esc(v)}" ${o||''}></label>`;
  const sw=(id,t,sm,on)=>`<label class="sw"><input type="checkbox" id="cl-${id}" ${on?'checked':''}><i></i><div><b>${t}</b><small>${sm}</small></div></label>`;
  const sel=(id,l,opts,v)=>`<label class="field"><span>${l}</span><select class="in" id="cl-${id}">${opts.map(o=>`<option value="${o[0]}" ${String(o[0])===String(v)?'selected':''}>${o[1]}</option>`).join('')}</select></label>`;
  const seg=(id,opts,v)=>`<div class="seg" id="cl-${id}">${opts.map(o=>`<button data-v="${o[0]}" class="${String(o[0])===String(v)?'on':''}">${o[1]}</button>`).join('')}</div>`;
  const chips=clAvail(P).map(s=>`<label class="cl-chip"><input type="checkbox" data-s="${s[0]}" ${F.strat[s[0]]?'checked':''}><span><i style="background:${s[2]}"></i>${s[1]}</span></label>`).join('');
  const goalOpts=clAvail(P).filter(s=>F.strat[s[0]]).map(s=>[s[0],s[1]]);
  return`<div class="cl-page">${ld?`<div class="card">${waitBox('Загружаю параметры рынка (ставки, доходности, ваш портфель)… пока расчёт идёт на значениях по умолчанию')}</div>`:''}${fb?`<div class="msg err">Не удалось загрузить рыночные данные (${esc(S.calcErr||'нет ответа')}). Использованы значения по умолчанию, расчёт приблизителен.</div>`:''}
  <div class="card"><h2>Параметры<span class="sp">пересчёт мгновенный</span></h2><div id="cl-form">
   <div class="cl-grid">${num('start','Стартовая сумма, ₽',F.start,'min="0" step="10000"')}${num('monthly','Пополнение в месяц, ₽',F.monthly,'min="0" step="1000"')}
    ${num('idx','Ежегодная индексация пополнений, %',F.idx,'min="0" max="50" step="0.5"')}
    <label class="field"><span>Срок: <b id="cl-yv">${F.years}</b> лет</span><input id="cl-years" type="range" min="1" max="30" step="1" value="${F.years}"></label></div>
   ${pf&&pf.value!=null?`<div class="cl-row"><button class="btn ghost" id="cl-pf">Подставить мой портфель</button><span class="note">старт ${clRub(pf.value)}${pf.monthly!=null?`, пополнение ${clRub(pf.monthly)} в месяц (среднее за 12 мес.)`:''}</span></div>`:''}
   <div class="cl-sec">Что сравниваем</div><div class="cl-chips" id="cl-strat">${chips}</div>
   <div class="cl-grid" id="cl-ownbox" style="${F.strat.own?'':'display:none'}">${num('ownRate','Своя ставка, % годовых',F.ownRate,'step="0.5" min="0" max="100"')}</div>
   <div class="cl-sec">Облигации и реинвестирование</div>
   <div class="cl-grid">${sw('reinvest','Реинвестировать купоны','иначе купоны копятся без дохода',F.reinvest)}${sel('freq','Выплаты купонов',[[12,'12 раз в год (раз в месяц)'],[4,'4 раза в год (раз в квартал)'],[2,'2 раза в год (раз в полгода)']],F.freq)}
    ${num('lot','Цена лота (покупаем целыми бумагами), ₽',F.lot,'min="0" step="100"')}${sel('lotFund','Остаток, не хватающий на бумагу',[['fund','лежит в фонде ликвидности'],['wait','ждёт следующей покупки']],F.lotFund)}</div>
   <div class="cl-sec">Ключевая ставка</div>
   <div class="cl-row">${seg('scn',[['cbr','Прогноз ЦБ'],['hard','Жёсткий (+2 п.п.)'],['soft','Мягкий (−2 п.п.)'],['own','Своя постоянная']],F.scn)}
    <label class="field" id="cl-ownkeybox" style="${F.scn==='own'?'':'display:none'}"><span>Ставка, %</span><input class="in" id="cl-ownKey" type="number" step="0.5" min="1" max="50" value="${esc(F.ownKey)}" style="width:110px"></label></div>
   <div class="cl-sec">Налоги и поправки</div>
   <div class="cl-grid">${sel('acct','Тип счёта',CL_ACC,F.acct)}${sw('reinvDed','Реинвестировать вычет ИИС','возвращённый налог снова вкладывается',F.reinvDed)}
    ${sw('ldv','ЛДВ для фонда ликвидности','без налога на рост пая при владении от 3 лет',F.ldv)}${sw('defaults','Учитывать дефолты','вычитаем ожидаемые потери сегмента каждый год',F.defaults)}
    ${num('depSpread','Вклад: ставка = ключевая минус, п.п.',F.depSpread,'step="0.1" min="0" max="10"')}</div>
   <div class="cl-sec">Как показывать</div>
   <div class="cl-row">${seg('real',[['1','В сегодняшних деньгах'],['0','Номинал']],F.real?'1':'0')}</div>
   <div class="cl-sec">Цель</div>
   <div class="cl-grid">${sw('goalOn','Режим цели','«Хочу пассивный доход N ₽ в месяц»',F.goalOn)}
    <div id="cl-goalbox" class="cl-grid" style="${F.goalOn?'':'display:none'}">${num('goalAmt','Желаемый доход в месяц, ₽ (в сегодняшних деньгах)',F.goalAmt,'min="0" step="5000"')}
     ${sel('goalMode','Что найти',[['contrib','нужное пополнение (срок задан)'],['years','нужный срок (пополнение задано)']],F.goalMode)}
     <label class="field"><span>Стратегия</span><select class="in" id="cl-goalStrat">${goalOpts.map(o=>`<option value="${o[0]}" ${o[0]===F.goalStrat?'selected':''}>${o[1]}</option>`).join('')}</select></label></div></div>
  </div></div>
  <div id="cl-out">${clOut()}</div>
  <div class="card"><h2>Как это считается</h2><div class="note">Шаг расчёта — месяц; взносы вносятся в конце месяца. <b>Вклад</b>: ежемесячная капитализация по ставке «ключевая − ${f2(F.depSpread)} п.п.» по пути выбранного сценария; НДФЛ — с процентов сверх необлагаемого порога (1 млн ₽ × максимальная ключевая ставка года).
   <b>Фонд ликвидности</b>: ежедневное начисление приближено месячным по «ключевая − спред к ключевой»; налог только при продаже в конце срока (или ЛДВ / ИИС).
   <b>ОФЗ, корпоративные, ВДО</b>: покупаем по текущей медианной доходности сегмента, держим до погашения (срок ≈ медианная дюрация), купоны по этой доходности; погашенный номинал и купоны вкладываются по будущей доходности ≈ текущая + β × (ключевая в тот момент − ключевая сейчас), β = 0,6 для ОФЗ и 0,7 для остальных. Налог с купонов удерживается при каждой выплате. Переоценка цены облигаций при удержании до погашения не учитывается; на конец срока позиции считаются по номиналу.
   <b>Мой портфель</b>: доходность облигаций портфеля (IRR) используется как ставка; <b>Своя ставка</b> — постоянная ставка с купонным налогом. Налоговый год считается от начала расчёта, шкала НДФЛ: 13 % до 2,4 млн ₽ дохода в год, дальше 15 % (и по шкале 18/20/22 % для более крупных сумм). Инфляция — прогноз Банка России, после его горизонта — последнее значение.</div></div>
  <div class="note cl-disc">Модель упрощённая. Результаты — не прогноз и не индивидуальная инвестиционная рекомендация: реальные ставки, цены, налоги и дефолты будут отличаться.</div></div>`;
}
function clUpdate(){
  S.charts=[];const o=$('#cl-out');if(!o)return;o.innerHTML=clOut();mountCharts();
  const g=$('#cl-goalStrat');if(g){const F=clLoadF(),P=(S.calcAcc===S.account&&S.calcP)||clDefaultParams(),opts=clAvail(P).filter(s=>F.strat[s[0]]);
    g.innerHTML=opts.map(s=>`<option value="${s[0]}" ${s[0]===F.goalStrat?'selected':''}>${s[1]}</option>`).join('')}
}
function bindCalc(){
  const form=$('#cl-form');if(!form)return;const F=clLoadF(),P=(S.calcAcc===S.account&&S.calcP)||clDefaultParams();
  const rn=(id,d,lo,hi)=>{const e=$('#cl-'+id);if(!e)return d;let v=parseFloat(String(e.value).replace(',','.'));if(!isFinite(v))v=d;if(lo!=null)v=Math.max(lo,v);if(hi!=null)v=Math.min(hi,v);return v};
  const read=()=>{
    F.start=rn('start',0,0);F.monthly=rn('monthly',0,0);F.idx=rn('idx',0,0,50);F.years=Math.round(rn('years',10,1,30));F.ownRate=rn('ownRate',15,0,100);
    F.reinvest=$('#cl-reinvest').checked;F.freq=+$('#cl-freq').value;F.lot=rn('lot',0,0);F.lotFund=$('#cl-lotFund').value;F.ownKey=rn('ownKey',12,1,50);
    F.acct=$('#cl-acct').value;F.reinvDed=$('#cl-reinvDed').checked;F.ldv=$('#cl-ldv').checked;F.defaults=$('#cl-defaults').checked;F.depSpread=rn('depSpread',1.5,0,10);
    F.goalOn=$('#cl-goalOn').checked;F.goalAmt=rn('goalAmt',0,0);F.goalMode=$('#cl-goalMode').value;if($('#cl-goalStrat'))F.goalStrat=$('#cl-goalStrat').value;
    form.querySelectorAll('#cl-strat input').forEach(c=>{F.strat[c.dataset.s]=c.checked?1:0});
    $('#cl-yv').textContent=F.years;
    $('#cl-ownbox').style.display=F.strat.own?'':'none';$('#cl-ownkeybox').style.display=F.scn==='own'?'':'none';$('#cl-goalbox').style.display=F.goalOn?'':'none';
    clSave();clUpdate();
  };
  form.addEventListener('input',read);form.addEventListener('change',read);
  [['scn',v=>{F.scn=v}],['real',v=>{F.real=v==='1'}]].forEach(([id,fn])=>{const s=$('#cl-'+id);if(s)s.onclick=e=>{const b=e.target.closest('button');if(!b)return;
    s.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));fn(b.dataset.v);read()}});
  const b=$('#cl-pf');if(b)b.onclick=()=>{const pf=P.portfolio;if(!pf)return;if(pf.value!=null)F.start=Math.round(pf.value);if(pf.monthly!=null)F.monthly=Math.round(pf.monthly);F.strat.pf=1;clSave();render()};
}
/* ── Оферты: держать или предъявить ── */
function loadOff(){
  const acc=S.account,o=S.off;
  if(o&&o.acc===acc&&(o.loading||o.data||o.error))return;
  S.off={acc,loading:true};
  api('/api/offers?'+new URLSearchParams({account:acc})).then(d=>{if(S.account!==acc)return;S.off={acc,data:d};if(S.page==='off')render()})
   .catch(e=>{if(S.account!==acc)return;S.off={acc,error:e.message};if(S.page==='off')render()});
}
const OF_HINT={sell_market:['Продать на бирже','of-info'],put:['Предъявить','of-warn'],hold:['Держать','of-ok'],wait:['Подождать','of-wait'],call:['Предупреждение','of-warn'],closed:['Поздно','of-wait']};
const ofDays=n=>n===0?'сегодня':n===1?'завтра':'через '+n+' '+(n%10===1&&n%100!==11?'день':n%10>=2&&n%10<=4&&(n%100<10||n%100>=20)?'дня':'дней');
function ofPeriod(x){
  if(x.kind==='call')return'<span class="mu">не применяется</span>';
  if(!x.period_start||!x.period_end)return'<span class="mu">не опубликован</span>';
  const t=`${ddm(x.period_start)} – ${ddm(x.period_end)}`;
  return x.period_status==='open'?`<b class="pos">${t}</b><br><small class="${x.urgent?'neg':'mu'}">открыт, до конца ${x.period_days_left===0?'сегодня':ofDays(x.period_days_left).replace('через ','')}</small>`
    :x.period_status==='closed'?`${t}<br><small class="mu">закончился</small>`:`${t}<br><small class="${x.urgent?'neg':'mu'}">${x.period_days_left!=null?'закроется '+ofDays(x.period_days_left):''}</small>`;
}
function ofCard(x){
  const h=x.hint||{},[lab,hc]=OF_HINT[h.code]||['','of-wait'];
  const yo=x.yield_to_offer!=null&&x.yield_to_offer<=100?pctp(x.yield_to_offer,1):x.yield_to_offer!=null?'&gt; 100 %':'—';
  const cpn=x.kind==='call'?'—':x.coupon_known?`<b>${pctp(x.new_rate,1)}</b> годовых<br><small class="mu">доходность ${x.hold_yield!=null?pctp(x.hold_yield,1):'—'}</small>`:'<span class="mu">не объявлен</span>';
  const peers=x.peer_median!=null?`${pctp(x.peer_median,1)}<br><small class="mu">${x.peers_n} похожих выпусков</small>`:'<span class="mu">нет данных</span>';
  return`<div class="card of-card ${x.urgent?'of-urgent':''}">
    <div class="of-head" data-isin="${esc(x.isin||'')}" title="Открыть карточку выпуска">${logo(x,34)}<div class="of-nm"><b>${esc(x.name)}</b><small class="mu">${esc(x.isin||'')}${x.floating?' · флоатер':''} · ${M(x.value_rub,'rub',0)}</small></div>
      ${x.rating?`<span class="tag rt rt-${esc(rBucket(x.rating).split(' ')[0])}">${esc(x.rating)}</span>`:''}
      <span class="tag ${x.kind==='call'?'of-t-call':'of-t-put'}">${x.kind==='call'?'колл / досрочное погашение':'оферта'}</span>${x.urgent?'<span class="tag of-t-urg">срочно</span>':''}</div>
    <div class="of-grid">
      <div><span class="k">Дата оферты</span><b class="num">${ddm(x.date)}</b><br><small class="mu">${ofDays(x.days)}</small></div>
      <div><span class="k">Период предъявления</span>${ofPeriod(x)}</div>
      <div><span class="k">Цена выкупа / сейчас</span><span class="num">${x.offer_price!=null?f2(x.offer_price)+' %':'—'} / ${x.price!=null?f2(x.price)+' %':'—'}</span>${x.kind==='put'&&x.to_offer_rub?`<br><small class="mu">выкуп ≈ ${M(x.to_offer_rub,'rub',0)}</small>`:''}</div>
      <div><span class="k">Доходность к оферте</span><span class="num">${x.kind==='call'?'—':yo}</span></div>
      <div><span class="k">Купон после оферты</span>${cpn}</div>
      <div><span class="k">Аналоги, доходность</span>${x.kind==='call'?'—':peers}</div></div>
    <div class="of-hint ${hc}"><span class="of-lab">${esc(lab)}</span><div><b>${esc(h.title||'')}</b><p>${esc(h.text||'')}</p>${x.risk_notes&&x.risk_notes.length&&h.code!=='put'?`<p class="neg">Обратите внимание: ${esc(x.risk_notes.join('; '))}.</p>`:''}</div></div></div>`;
}
function pOff(){
  loadOff();
  const o=S.off;
  if(!o||o.loading)return`<div class="card">${waitBox('Читаю графики оферт и купонов по облигациям портфеля…')}</div>`;
  if(o.error)return`<div class="msg err">${esc(o.error)} <button class="btn ghost" id="of-r">Повторить</button></div>`;
  const d=o.data;
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="of-r">Повторить</button></div>`;
  const kp=`<div class="g g4">${kpi('Оферт за 12 месяцев',d.count,`по ${d.bonds_count} облигациям портфеля`,null,S1)}${kpi('С правом предъявить',d.put_count,'держатель может продать эмитенту',null,S3)}
    ${kpi('Срочные',d.urgent_count,'период предъявления открыт или заканчивается за 7 дней',d.urgent_count?'neg':'',S8)}${kpi('Выкуп по номиналу',M(d.to_offer_rub,'rub',0),'если предъявить все бумаги',null,S2)}</div>`;
  const list=d.items.length?d.items.map(ofCard).join(''):`<div class="card empty">${esc(d.empty_text)}</div>`;
  return kp+(d.errors&&d.errors.length?`<div class="msg">Не удалось разобрать часть выпусков: ${esc(d.errors.slice(0,3).join('; '))}</div>`:'')+list+
   `<div class="card"><h2>Как это читать</h2><p class="note">${(d.notes||[]).map(esc).join('<br><br>')}<br><br>Правило подсказки: если на бирже бумага стоит дороже цены выкупа — выгоднее продать на бирже; если новый купон известен и доходность после оферты ниже медианы похожих выпусков (тот же рейтинг ±1 ступень, близкий срок) больше чем на 0,5 п. п. — предъявление выглядит разумнее; если купон ещё не объявлен, показан порог ставки, ниже которого предъявление выглядит разумнее. Подсказки справочные, это не индивидуальная инвестиционная рекомендация: условия оферты проверяйте в документах выпуска и у брокера.</p></div>`;
}
function bindOff(){
  const r=$('#of-r');if(r)r.onclick=()=>{S.off=null;render()};
}
/* ── Конструктор облигационной лестницы ── */
S.ladQ={sum:'500000',years:'5',rungs:'',rating:'A',floaters:false,amort:true,monthly:false};
try{const v=JSON.parse(localStorage.getItem('lad_q')||'null');if(v&&typeof v==='object')Object.assign(S.ladQ,v)}catch(e){}
const LAD_RT=['AAA','AA','A','BBB','BB'];
const LAD_MN=['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
function ladRun(){
  const q=S.ladQ;try{localStorage.setItem('lad_q',JSON.stringify(q))}catch(e){}
  const p=new URLSearchParams({sum:String(q.sum||'500000').replace(/\s/g,'').replace(',','.'),years:q.years||'5',min_rating:q.rating||'A',floaters:q.floaters?'1':'0',amort:q.amort?'1':'0',monthly:q.monthly?'1':'0'});
  if(q.rungs)p.set('rungs',q.rungs);
  S.lad={loading:true};render();
  api('/api/ladder?'+p).then(d=>{S.lad={data:d};if(S.page==='lad')render()}).catch(e=>{S.lad={error:e.message};if(S.page==='lad')render()});
}
function ladChart(el){
  const d=S.lad&&S.lad.data;if(!d||!d.cashflow_by_month||!d.cashflow_by_month.length)return emptyChart(el,260,'Нет выплат');
  const cf=d.cashflow_by_month,lb=cf.map(m=>LAD_MN[+m.month.slice(5)-1]+' '+m.month.slice(2,4));
  bars(el,{h:280,stack:true,labels:lb,series:[{n:'Купоны',c:'#3987e5',v:cf.map(m=>m.coupons)},{n:'Погашения и амортизация',c:'#19a070',v:cf.map(m=>m.principal)}],total:true,fa:short,ft:v=>M(v,'rub',0),empty:'Нет выплат'});
}
function ladMonths(a){return a&&a.length?`<span class="ld-mon" title="Месяцы, в которые бумага платит купон">${a.map(m=>LAD_MN[m-1]).join(' ')}</span>`:'<span class="mu">—</span>'}
function ladResult(d){
  const t=d.totals,pr=d.params;
  const kp=`<div class="g g4">${kpi('Вложено',M(t.invested,'rub',0),`${t.bonds} бумаг · ${t.issuers} эмитентов`+(t.free>0?` · свободно ${M(t.free,'rub',0)}`:''),null,S1)}
    ${kpi('Доходность лесенки',t.ytm!=null?pctp(t.ytm,1):'—','средневзвешенная к погашению',null,S3)}
    ${kpi('Дюрация',t.dur!=null?t.dur.toFixed(1).replace('.',',')+' г.':'—','средний срок возврата денег',null,S2)}
    ${kpi('Купоны в месяц',M(t.monthly_avg,'rub',0),`≈ ${M(t.coupon_12m,'rub',0)} за ближайший год`,null,S4)}</div>`;
  const warn=(d.warnings||[]).map(w=>`<div class="msg err">${esc(w)}</div>`).join('');
  let body='';
  d.rungs.forEach((r,i)=>{
    body+=`<tr class="ld-rung"><td class="l" colspan="4">Ступень ${i+1}: срок около ${ddm(r.target_date)}</td><td colspan="2" class="num">${r.bonds.length?M(r.cost,'rub',0):'—'}</td><td colspan="2"></td></tr>`;
    if(!r.bonds.length)body+=`<tr><td class="l mu" colspan="8">Подходящих бумаг не нашлось</td></tr>`;
    r.bonds.forEach(b=>{body+=`<tr data-isin="${esc(b.isin)}" title="Открыть карточку"><td class="l"><b style="font-weight:600">${esc(b.name)}</b>${b.floating?' <span class="tag">флоатер</span>':''}${b.amort?' <span class="tag">аморт</span>':''}<br><small class="mu">${esc(b.isin)}</small></td>
      <td class="l"><span class="tag rt rt-${esc(rBucket(b.rating).split(' ')[0])}">${esc(b.rating)}</span></td><td class="num">${pctp(b.ytm,1)}</td>
      <td class="num">${ddm(b.end_date)}<br><small class="mu">${b.end_kind==='offer'?'оферта':'погашение'}</small></td><td class="num">${b.lots} шт.<br><small class="mu">по ${f2(b.price)} %</small></td><td class="num">${M(b.cost,'rub',0)}<br><small class="mu">${pctp(b.share,1)}</small></td>
      <td class="l">${ladMonths(b.coupon_months)}</td></tr>`});
  });
  chart('ld-cf',ladChart);
  return kp+warn+`<div class="card"><h2>Ступени лесенки<span class="sp">нажмите на строку — карточка выпуска</span></h2><div class="tbl"><table class="ld-tbl"><thead><tr><th class="l">Облигация</th><th class="l">Рейтинг</th><th>Доходность</th><th>Срок</th><th>Куплено</th><th>Стоимость</th><th class="l">Купоны</th></tr></thead><tbody>${body}</tbody></table></div></div>
  <div class="card"><h2>Выплаты по месяцам<span class="sp">купоны и возврат номинала</span></h2><div class="chart" id="ld-cf"></div></div>
  <div class="card ld-notes"><h2>Почему так</h2><div class="note">${d.notes.map(n=>`<p>${esc(n)}</p>`).join('')}<p>Цены и доходности — по данным Мосбиржи на сегодня, расчёт с учётом накопленного купонного дохода и без комиссий; налог не учтён. Состав — справочная подборка, не индивидуальная инвестиционная рекомендация: перед покупкой проверьте эмитентов и условия выпусков.</p></div></div>`;
}
function pLad(){
  const q=S.ladQ,l=S.lad;
  const form=`<div class="card"><h2>Параметры лесенки<span class="sp">деньги делятся по ступеням с разными сроками погашения</span></h2><div class="flt ld-form">
    <label class="field"><span>Сумма, ₽</span><input class="in" id="ld-sum" type="text" inputmode="numeric" value="${esc(q.sum)}"></label>
    <label class="field"><span>Горизонт, лет (1–10)</span><input class="in" id="ld-years" type="number" min="1" max="10" step="1" value="${esc(q.years)}"></label>
    <label class="field"><span>Ступеней</span><input class="in" id="ld-rungs" type="number" min="1" max="12" step="1" placeholder="= лет" value="${esc(q.rungs)}"></label>
    <label class="field"><span>Рейтинг не ниже</span><select class="in" id="ld-rt">${LAD_RT.map(r=>`<option${q.rating===r?' selected':''}>${r}</option>`).join('')}</select></label>
    <label class="sw"><input type="checkbox" id="ld-fl" ${q.floaters?'checked':''}><i></i><div><b>Флоатеры</b><small>купон плавает со ставкой</small></div></label>
    <label class="sw"><input type="checkbox" id="ld-am" ${q.amort?'checked':''}><i></i><div><b>Амортизация</b><small>долг гасится частями</small></div></label>
    <label class="sw"><input type="checkbox" id="ld-mo" ${q.monthly?'checked':''}><i></i><div><b>Ровный доход</b><small>купоны в разные месяцы</small></div></label>
    <button class="btn" id="ld-go">Подобрать</button></div></div>`;
  if(!l)return form+`<div class="card empty">Задайте сумму и горизонт и нажмите «Подобрать»: программа составит набор облигаций, которые гасятся по очереди.</div>`;
  if(l.loading)return form+`<div class="card">${waitBox('Подбираю бумаги и считаю выплаты…')}</div>`;
  if(l.error||l.data.error)return form+`<div class="msg err">${esc(l.error||l.data.error)}</div>`;
  return form+ladResult(l.data);
}
function bindLad(){
  const g=$('#ld-go');if(!g)return;
  g.onclick=()=>{const q=S.ladQ;q.sum=$('#ld-sum').value;q.years=$('#ld-years').value;q.rungs=$('#ld-rungs').value;q.rating=$('#ld-rt').value;
    q.floaters=$('#ld-fl').checked;q.amort=$('#ld-am').checked;q.monthly=$('#ld-mo').checked;ladRun()};
  ['#ld-sum','#ld-years','#ld-rungs'].forEach(i=>{const e=$(i);if(e)e.onkeydown=ev=>{if(ev.key==='Enter')g.click()}});
}
/* ── Эмитенты: отчётность и скоринг ── */
function pIss(){return`<div class="card empty">Раздел в разработке</div>`}
function bindIss(){}
/* ── Календарь событий ── */
function pCal(){return`<div class="card empty">Раздел в разработке</div>`}
function bindCal(){}
/* ── Наблюдение: список бумаг с целями и тревогами, дневник, уведомления в Telegram ── */
S.wset=null;S.watch=null;S.wnotes=null;S.wfilter='';S.wsug=[];
const WT_REMIND=[['','без напоминания'],['7','через 7 дней'],['30','через 30 дней'],['90','через 3 месяца'],['180','через полгода'],['365','через год']];
const WT_TPL=[['Почему купил: ','Почему купил'],['Продать, если: ','Что должно случиться, чтобы продать']];

/* множество ISIN из списка (для звёздочек в скринере и карточке) */
function watchLoadSet(){
  if(S.wset&&S.wset.loading)return;
  const old=S.wset;S.wset=Object.assign(new Set(old||[]),{loading:true});
  api('/api/watch/isins').then(j=>{S.wset=new Set(j.isins||[]);watchRefreshView()}).catch(()=>{S.wset=new Set(old||[])});
}
function watchHas(isin){
  if(!S.wset||!(S.wset instanceof Set))watchLoadSet();
  return !!(S.wset&&S.wset.has(isin));
}
function watchRefreshView(){
  if(S.page==='scr'&&S.scr&&!S.scr.error&&$('#scr-body'))drawScr();
  else if(['watch','mon'].includes(S.page))render();
}
/* добавить/убрать бумагу; вызывается карточкой облигации и скринером */
async function watchToggle(isin){
  if(!isin)return false;
  const r=await post('/api/watch',{action:'toggle',isin});
  S.wset=new Set(r.isins||[]);S.watch=null;
  try{document.dispatchEvent(new CustomEvent('watchchange',{detail:{isin,on:!!r.in_watch}}))}catch(e){}
  watchRefreshView();
  return !!r.in_watch;
}
function watchStar(isin){
  const on=watchHas(isin);
  return`<button class="wt-star${on?' on':''}" data-wstar="${esc(isin)}" title="${on?'Убрать из наблюдения':'Добавить в наблюдение'}" aria-label="Наблюдение">${on?'★':'☆'}</button>`;
}

function watchEnsure(){
  const w=S.watch;
  if(w&&(w.loading||w.error||(w.data&&Date.now()-w.t<3e5)))return;
  S.watch={loading:true,t:Date.now()};
  api('/api/watch').then(d=>{S.watch={data:d,t:Date.now()};S.wset=new Set(d.items.map(x=>x.isin));
    if(['watch','mon'].includes(S.page))render()}).catch(e=>{S.watch={error:e.message,t:Date.now()};if(['watch','mon'].includes(S.page))render()});
}
function notesEnsure(){
  const n=S.wnotes;
  if(n&&(n.loading||n.error||n.data))return;
  S.wnotes={loading:true};
  api('/api/notes').then(d=>{S.wnotes={data:d.rows};if(S.page==='watch')render()}).catch(e=>{S.wnotes={error:e.message};if(S.page==='watch')render()});
}

/* группа «Наблюдение» на странице «Мониторинг» */
function watchMonGroup(){
  if(!S.wset||!(S.wset instanceof Set)){watchLoadSet();return''}
  if(!S.wset.size)return'';
  watchEnsure();
  const w=S.watch;
  if(!w||w.loading)return`<div class="card"><h2>Наблюдение<span class="sp">загружаю…</span></h2></div>`;
  if(w.error||!w.data)return'';
  const al=w.data.alerts;
  return`<div class="card"><h2>Наблюдение<span class="sp">${w.data.items.length} бумаг · ${al.length?al.length+' тревог':'тревог нет'}</span>
    <button class="btn ghost" data-go="watch" style="margin-left:auto;padding:4px 12px;font-size:12px">Открыть список</button></h2>
    ${al.length?al.slice(0,8).map(monAlertHtml).join('')+(al.length>8?`<div class="mu" style="font-size:12px;margin-top:6px">…и ещё ${al.length-8}</div>`:''):'<div class="mon-ok">По бумагам из списка наблюдения тревог нет</div>'}</div>`;
}

function wtRow(r){
  const th=v=>v!=null?String(v).replace('.',','):'';
  const sp=r.spark&&r.spark.length>2?monSpark(r.spark,70,22):'';
  return`<tr data-isin="${esc(r.isin)}" title="Открыть карточку"><td class="l"><b style="font-weight:600">${esc(r.name)}</b>${r.n_high?` <span class="tag" style="color:var(--neg)">!</span>`:''}<br><small class="mu num">${esc(r.isin)}${r.offer?' · оферта '+ddm(r.offer):''}${r.mat?' · до '+ddm(r.mat):''}</small></td>
    <td class="l">${r.rating?`<span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}">${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td>
    <td class="num">${r.price!=null?f2(r.price):'—'}</td><td class="num"><b>${r.yield_!=null?pctp(r.yield_,2):'—'}</b></td>
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread):'—'}</td>
    <td class="num ${cls(r.chg30)}">${r.chg30!=null?pct(r.chg30,1):'—'}</td><td>${sp}</td>
    <td class="num">${r.dur!=null?f2(r.dur):'—'}</td><td class="num">${r.turn?short(r.turn):'—'}</td>
    <td><input class="in num wt-in" data-k="target_yield" data-isin="${esc(r.isin)}" value="${esc(th(r.target_yield))}" placeholder="от, %" inputmode="decimal" title="Сообщить, когда доходность станет не ниже"></td>
    <td><input class="in num wt-in" data-k="target_price" data-isin="${esc(r.isin)}" value="${esc(th(r.target_price))}" placeholder="до, %" inputmode="decimal" title="Сообщить, когда цена станет не выше"></td>
    <td><input class="in wt-in wt-note" data-k="note" data-isin="${esc(r.isin)}" value="${esc(r.note||'')}" placeholder="заметка" maxlength="300"></td>
    <td class="l">${(r.flags||[]).map(f=>`<span class="tag" style="color:var(--neg)">${esc(f)}</span>`).join(' ')}</td>
    <td><button class="btn ghost wt-del" data-wdel="${esc(r.isin)}" title="Убрать из наблюдения">×</button></td></tr>`;
}
function wtNoteHtml(n){
  const due=n.remind_on&&n.remind_on<=new Date().toISOString().slice(0,10);
  return`<div class="wt-note-i" data-isin="${esc(n.isin)}"><div class="wt-nh"><b>${esc(n.name||n.isin)}</b><small class="mu num">${ddm(n.date)}</small>
    ${n.remind_on?`<span class="tag ${due?'wt-due':''}" title="Напоминание">${due?'пора пересмотреть':'напомнить '+ddm(n.remind_on)}</span>`:''}
    <span style="margin-left:auto;display:flex;gap:6px">${n.remind_on?`<button class="btn ghost wt-sm" data-ndone="${esc(n.id)}">Пересмотрено</button>`:''}<button class="btn ghost wt-sm" data-ndel="${esc(n.id)}" title="Удалить заметку">Удалить</button></span></div>
    <div class="wt-nt">${esc(n.text)}</div></div>`;
}
function pWatch(){
  watchEnsure();notesEnsure();
  const w=S.watch,nt=S.wnotes;
  if(!w||w.loading)return`<div class="card">${waitBox('Проверяю бумаги из списка: цены, рейтинги, спреды и цели…')}</div>`;
  if(w.error)return`<div class="msg err">${esc(w.error)} <button class="btn ghost" id="wt-r">Повторить</button></div>`;
  const d=w.data,sm=d.summary,goals=d.alerts.filter(a=>a.kind==='goal').length;
  const hold=(S.bonds&&S.bonds.rows||[]).filter(r=>r.isin).map(r=>[r.isin,r.name,'в портфеле']);
  const opts=[...d.items.map(r=>[r.isin,r.name,'наблюдение']),...hold.filter(h=>!d.items.some(r=>r.isin===h[0]))];
  const notes=((nt&&nt.data)||[]).filter(n=>!S.wfilter||n.isin===S.wfilter);
  const nIsins=[...new Map(((nt&&nt.data)||[]).map(n=>[n.isin,n.name||n.isin])).entries()];
  return`<div class="g g4">${kpi('Бумаг в списке',d.items.length,'облигации, за которыми вы следите',null,S1)}${kpi('Высокие тревоги',sm.high,'дефолт, понижение рейтинга, сильное падение','neg',S8)}
    ${kpi('Средние тревоги',sm.medium,'наблюдение, оферты, напоминания','',S3)}${kpi('Цели достигнуты',goals,'доходность или цена дошли до заданной',goals?'pos':'',S2)}</div>
  ${(d.notes||[]).filter(n=>d.items.length).map(n=>`<div class="msg">${esc(n)}</div>`).join('')}
  <div class="card"><h2>Добавить бумагу<span class="sp">по названию или ISIN, из облигаций Мосбиржи</span></h2>
    <div class="wt-add"><input class="in" id="wt-q" placeholder="например, Самолет или RU000A0JQAM6" autocomplete="off"><div id="wt-sug" class="wt-sug"></div></div>
    <p class="note" style="margin-top:8px">Можно также нажать ☆ в строке скринера или в карточке облигации. Цели задаются прямо в таблице ниже.</p></div>
  ${d.alerts.length?`<div class="card"><h2>Тревоги по списку<span class="sp">рейтинги, цена, спред, оферты, цели и напоминания</span></h2>${d.alerts.slice(0,S.wtAll?999:10).map(monAlertHtml).join('')}${d.alerts.length>10?`<button class="btn ghost" id="wt-all" style="margin-top:6px">${S.wtAll?'Свернуть':'Показать все ('+d.alerts.length+')'}</button>`:''}</div>`:''}
  <div class="card"><h2>Список наблюдения<span class="sp">клик по строке — карточка выпуска</span><button class="btn ghost" id="wt-r" style="margin-left:auto;padding:4px 12px;font-size:12px">Обновить</button></h2>
    ${d.items.length?`<div class="tbl"><table id="wt-tab"><thead><tr><th class="l">Выпуск</th><th class="l">Рейтинг</th><th>Цена, %</th><th>Доходность</th><th>Спред, п.п.</th><th>Δ 30 дн.</th><th>Спред 90 дн.</th><th>Дюрация</th><th>Оборот</th>
      <th title="Тревога, когда доходность станет не ниже этого значения">Цель: доходность ≥</th><th title="Тревога, когда цена станет не выше этого значения">Цель: цена ≤</th><th class="l">Заметка</th><th class="l">Флаги</th><th></th></tr></thead><tbody>${d.items.map(wtRow).join('')}</tbody></table></div>
      <p class="note" style="margin-top:10px">Цены и доходность — по данным Мосбиржи с задержкой. Тревоги считаются теми же правилами и порогами, что и в «Мониторинге» (пороги меняются там). Справочная информация, не инвестиционная рекомендация.</p>`
      :'<div class="empty" style="padding:18px 0">Список пуст. Найдите бумагу выше или нажмите ☆ в скринере.</div>'}</div>
  <div class="card"><h2>Дневник<span class="sp">заметки по любым бумагам, в том числе из портфеля</span></h2>
    <div class="wt-form"><label class="field"><span>Бумага</span><select class="in" id="nt-sel"><option value="">— выберите —</option>${opts.map(o=>`<option value="${esc(o[0])}">${esc(o[1])} · ${o[2]}</option>`).join('')}<option value="_other">другая (ввести ISIN)…</option></select>
      <input class="in" id="nt-isin" placeholder="ISIN" style="display:none;margin-top:6px"></label>
      <label class="field"><span>Напомнить пересмотреть</span><select class="in" id="nt-rem">${WT_REMIND.map(o=>`<option value="${o[0]}">${o[1]}</option>`).join('')}</select></label></div>
    <label class="field" style="margin-top:12px"><span>Заметка</span><textarea class="in wt-ta" id="nt-text" rows="3" maxlength="2000" placeholder="Почему купил, на что рассчитываю, что должно случиться, чтобы продать…"></textarea></label>
    <div class="row" style="margin-top:10px">${WT_TPL.map(t=>`<button class="btn ghost wt-sm" data-tpl="${esc(t[0])}">${t[1]}</button>`).join('')}<button class="btn" id="nt-add" style="margin-left:auto">Добавить заметку</button></div>
    <div id="nt-msg"></div>
    <div class="row" style="margin:18px 0 6px"><label class="field" style="max-width:320px"><span>Показывать</span><select class="in" id="nt-flt"><option value="">все заметки</option>${nIsins.map(([i,n])=>`<option value="${esc(i)}" ${S.wfilter===i?'selected':''}>${esc(n)}</option>`).join('')}</select></label></div>
    ${!nt||nt.loading?waitBox('Загружаю заметки…'):nt.error?`<div class="msg err">${esc(nt.error)}</div>`:notes.length?notes.map(wtNoteHtml).join(''):'<div class="mu" style="font-size:13px;padding:6px 0">Заметок пока нет.</div>'}</div>`;
}
function bindWatch(){
  const rl=()=>{S.watch=null;render()};
  const r=$('#wt-r');if(r)r.onclick=rl;
  const al=$('#wt-all');if(al)al.onclick=()=>{S.wtAll=!S.wtAll;render()};
  let to,seq=0;
  const q=$('#wt-q');
  if(q){
    const draw=()=>{const box=$('#wt-sug');if(!box)return;
      box.innerHTML=S.wsug.length?S.wsug.map(x=>`<div class="wt-s" data-isin="${esc(x.isin)}"><div><b>${esc(x.name)}</b><small class="mu num"> ${esc(x.isin)}${x.mat?' · до '+ddm(x.mat):''}</small></div><span class="num">${x.yield!=null?pctp(x.yield,1):''}</span>
        <button class="btn ${x.in_watch?'ghost':''} wt-sm" data-wadd="${esc(x.isin)}" ${x.in_watch?'disabled':''}>${x.in_watch?'в списке':'Добавить'}</button></div>`).join(''):(q.value.trim().length>=2?'<div class="mu" style="padding:8px 2px;font-size:13px">Ничего не найдено среди облигаций, торгуемых на Мосбирже.</div>':'')};
    draw();
    q.oninput=()=>{clearTimeout(to);const v=q.value.trim(),my=++seq;
      if(v.length<2){S.wsug=[];draw();return}
      to=setTimeout(()=>api('/api/watch/search?'+new URLSearchParams({q:v})).then(j=>{if(my!==seq)return;S.wsug=j.rows||[];draw()}).catch(()=>{}),200)};
    q.onkeydown=e=>{if(e.key==='Enter'&&S.wsug.length){const x=S.wsug.find(s=>!s.in_watch);if(x)watchToggle(x.isin)}};
  }
  const sug=$('#wt-sug');
  if(sug)sug.onclick=async e=>{const b=e.target.closest('[data-wadd]');if(!b)return;e.stopPropagation();b.disabled=true;
    try{await watchToggle(b.dataset.wadd);S.wsug=[]}catch(er){alert(er.message)}};
  const tab=$('#wt-tab');
  if(tab){
    tab.onclick=async e=>{const b=e.target.closest('[data-wdel]');if(!b)return;e.stopPropagation();
      try{await post('/api/watch',{action:'remove',isin:b.dataset.wdel});S.wset.delete(b.dataset.wdel);S.watch=null;render()}catch(er){alert(er.message)}};
    tab.onchange=async e=>{const i=e.target.closest('.wt-in');if(!i)return;
      try{await post('/api/watch',{action:'update',isin:i.dataset.isin,[i.dataset.k]:i.value});if(i.dataset.k!=='note'){S.watch=null;render()}}catch(er){alert(er.message)}};
  }
  const sel=$('#nt-sel');
  if(sel)sel.onchange=()=>{$('#nt-isin').style.display=sel.value==='_other'?'':'none'};
  document.querySelectorAll('[data-tpl]').forEach(b=>b.onclick=()=>{const t=$('#nt-text');t.value=(t.value?t.value+'\n':'')+b.dataset.tpl;t.focus()});
  const add=$('#nt-add');
  if(add)add.onclick=async()=>{
    const m=(t,ok)=>{$('#nt-msg').innerHTML=`<div class="msg ${ok?'ok':'err'}">${esc(t)}</div>`};
    let isin=sel.value==='_other'?$('#nt-isin').value.trim().toUpperCase():sel.value;
    if(!isin)return m('Выберите бумагу или введите ISIN.');
    if(!$('#nt-text').value.trim())return m('Напишите текст заметки.');
    add.disabled=true;
    try{await post('/api/notes',{action:'add',isin,text:$('#nt-text').value,remind_days:$('#nt-rem').value});S.wnotes=null;S.watch=null;render()}
    catch(er){m(er.message);add.disabled=false}};
  const fl=$('#nt-flt');if(fl)fl.onchange=()=>{S.wfilter=fl.value;render()};
  const view=$('#view');
  if(view)view.querySelectorAll('[data-ndel]').forEach(b=>b.onclick=async e=>{e.stopPropagation();if(!confirm('Удалить заметку?'))return;
    try{await post('/api/notes',{action:'delete',id:b.dataset.ndel});S.wnotes=null;S.watch=null;render()}catch(er){alert(er.message)}});
  if(view)view.querySelectorAll('[data-ndone]').forEach(b=>b.onclick=async e=>{e.stopPropagation();
    try{await post('/api/notes',{action:'done',id:b.dataset.ndone});S.wnotes=null;S.watch=null;render()}catch(er){alert(er.message)}});
}
/* звёздочки (скринер, карточка и др.): клик не открывает карточку выпуска */
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-wstar]');if(!b)return;
  e.stopPropagation();b.disabled=true;
  try{await watchToggle(b.dataset.wstar)}catch(er){alert(er.message)}finally{b.disabled=false}
},true);

/* ── Telegram: карточка в «Настройках» ── */
function setTgHtml(c){
  const set=c.secret_set&&c.secret_set.tg_token,on=(k,d)=>c[k]==null?d:!!c[k];
  return`<div class="card" id="tg-card"><h2>Уведомления в Telegram<span class="sp">по желанию, через ваш личный бот</span></h2>
    <div style="display:grid;gap:16px">
    <ol class="tg-steps"><li>В Telegram откройте <b>@BotFather</b>, отправьте <code>/newbot</code> и придумайте имя бота. BotFather пришлёт токен вида <code>123456789:AAH…</code></li>
      <li>Вставьте токен ниже и нажмите «Сохранить».</li><li>Откройте своего бота в Telegram и отправьте ему <code>/start</code>.</li>
      <li>Нажмите «Найти мой chat id», затем «Отправить тестовое сообщение».</li></ol>
    <label class="field"><span>Токен бота ${set?`<span class="pos">· сохранён. Оставьте пустым, чтобы не менять</span>`:''}</span>
      <input class="in" type="password" id="tg-tok" placeholder="123456789:AAH…" autocomplete="off" spellcheck="false"></label>
    <div class="row"><label class="field" style="max-width:260px"><span>Chat id</span><input class="in num" id="tg-chat" value="${esc(c.tg_chat||'')}" placeholder="например, 123456789" inputmode="numeric"></label>
      <button class="btn ghost" id="tg-find" style="align-self:flex-end">Найти мой chat id</button></div>
    <label class="sw"><input type="checkbox" id="tg-mon" ${on('tg_on_mon',true)?'checked':''}><i></i><div><b>Тревоги мониторинга</b><small>Только высокой важности: дефолт, понижение рейтинга, сильное падение цены</small></div></label>
    <label class="sw"><input type="checkbox" id="tg-wat" ${on('tg_on_watch',true)?'checked':''}><i></i><div><b>Наблюдение и цели</b><small>Тревоги по списку наблюдения, достигнутые цели и напоминания из дневника</small></div></label>
    <div class="row"><label class="field" style="max-width:300px"><span>Ближайшие выплаты: за сколько дней сообщать (0 — выключить)</span><input class="in num" id="tg-pay" type="number" min="0" max="60" value="${+c.tg_pay_days||0}"></label></div>
    <div class="row"><label class="sw"><input type="checkbox" id="tg-dg" ${on('tg_digest',false)?'checked':''}><i></i><div><b>Ежедневная сводка</b><small>Портфель, выплаты на неделю, тревоги</small></div></label>
      <label class="field" style="max-width:130px"><span>Время</span><input class="in num" id="tg-time" type="time" value="${esc(c.tg_digest_time||'10:00')}"></label></div>
    <div class="row"><button class="btn" id="tg-save">Сохранить</button><button class="btn ghost" id="tg-test">Отправить тестовое сообщение</button><button class="btn ghost" id="tg-run" title="Проверить тревоги и отправить новые прямо сейчас">Проверить сейчас</button>
      ${set?'<button class="btn danger" id="tg-clr">Удалить токен бота</button>':''}</div>
    <p class="note"><b>Что нужно знать.</b> Сообщения проходят через серверы Telegram и содержат названия бумаг и суммы — отправляйте их только в свой личный чат. Токен бота хранится только на этом компьютере (в файле настроек с ограниченным доступом) и в резервную копию не входит. Уведомления приходят, <b>только пока программа запущена</b>; проверка выполняется раз в 10–15 минут, одна и та же тревога повторно не отправляется. Если Telegram не открывается из вашей сети, понадобится VPN или прокси.</p></div></div>`;
}
function bindSetTg(c,msg){
  const g=id=>document.getElementById(id);if(!g('tg-card'))return;
  const body=()=>({token:g('tg-tok').value,chat:g('tg-chat').value,tg_on_mon:g('tg-mon').checked,tg_on_watch:g('tg-wat').checked,
    tg_pay_days:g('tg-pay').value||0,tg_digest:g('tg-dg').checked,tg_digest_time:g('tg-time').value||'10:00'});
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const save=async()=>{const r=await post('/api/tg/save',body());g('tg-tok').value='';c.secret_set=Object.assign({},c.secret_set,{tg_token:!!r.token_set});Object.assign(c,r.settings);return r};
  g('tg-save').onclick=e=>busy(e.currentTarget,async()=>{await save();msg('Настройки Telegram сохранены.',1);if(!document.getElementById('tg-clr')&&c.secret_set.tg_token)renderSettings()});
  g('tg-find').onclick=e=>busy(e.currentTarget,async()=>{await save();const r=await post('/api/tg/find_chat');g('tg-chat').value=r.chat;c.tg_chat=r.chat;msg('Chat id найден: '+r.chat+(r.name?' ('+r.name+')':'')+'. Теперь отправьте тестовое сообщение.',1)});
  g('tg-test').onclick=e=>busy(e.currentTarget,async()=>{await save();await post('/api/tg/test');msg('Тестовое сообщение отправлено — проверьте Telegram.',1)});
  g('tg-run').onclick=e=>busy(e.currentTarget,async()=>{await save();const r=await post('/api/tg/run');msg(r.sent?'Отправлено новых пунктов: '+r.sent+'.':'Новых тревог для отправки нет.',1)});
  const cl=g('tg-clr');if(cl)cl.onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Удалить токен бота из настроек?'))return;await post('/api/tg/save',{clear_token:true});c.secret_set=Object.assign({},c.secret_set,{tg_token:false});renderSettings()});
}
/* ── Зашифрованная резервная копия и экспорт ── */
function setBackupHtml(c){return''}
function bindSetBackup(c,msg){}
</script></body></html>
'''


if __name__ == "__main__":
    main()
