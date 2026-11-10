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
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
from xml.etree import ElementTree as ET

APP_NAME = "T-Invest Analytics"
APP_VERSION = "0.8"
APP_DIR = os.environ.get("TINVEST_HOME") or os.path.join(os.path.expanduser("~"), ".tinvest_analytics")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DB_PATH = os.path.join(APP_DIR, "data.db")
LOGO_DIR = os.path.join(APP_DIR, "logos")
CONTRACT = "tinkoff.public.invest.api.contract.v1"
LOGO_CDN = "https://invest-brands.cdn-tinkoff.ru/"
D0 = Decimal(0)
DAY = 86400

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
    """Zip с согласованной копией базы и настройками БЕЗ токена."""
    tmp = os.path.join(APP_DIR, "backup.%d.tmp" % threading.get_ident())
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        cfg = {k: v for k, v in load_config().items() if k != "token"}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "data.db")
            z.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=2))
            z.writestr("README.txt", "Резервная копия T-Invest Analytics. Токен API в копию не входит.\n"
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
                    with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
                        TInvest._good_host[self.sandbox] = host
                        return json.loads(r.read().decode("utf-8") or "{}")
                except urllib.error.HTTPError as e:
                    raw = e.read().decode("utf-8", "replace")
                    if e.code in (429, 503, 504) and attempt < 5:
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


def pool_map(fn, items, workers=6):
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


def instruments(client, keys):
    """keys: [(uid, figi)] -> {uid|figi: info}. Кэш в базе на 30 дней."""
    st = store()
    out, need = {}, []
    for u, f in set(keys):
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
        else:
            need.append((u, f))
    if need and client.ready:
        def one(k):
            u, f = k
            try:
                i = client.instrument(uid=u, figi=None if u else f)
            except ApiError:
                return k, None
            b = i.get("brand") or {}
            return k, {"uid": i.get("uid") or u or "", "figi": i.get("figi") or f or "", "ticker": i.get("ticker") or "",
                       "isin": i.get("isin") or "", "name": i.get("name") or "", "type": i.get("instrumentType") or "",
                       "cur": (i.get("currency") or "rub").lower(), "sector": i.get("sector") or "",
                       "logo": b.get("logoName") or "", "color": b.get("logoBaseColor") or "",
                       "country": i.get("countryOfRisk") or "", "cls": i.get("classCode") or ""}
        save = []
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
    if b is None and client.ready:
        try:
            r = client.bond_by(uid)
        except ApiError:
            r = None
        if r:
            b = {"nominal": qf(r.get("nominal")) or qf(r.get("initialNominal")) or 1000.0,
                 "initial": qf(r.get("initialNominal")), "cur": cur_of(r.get("nominal")),
                 "maturity": iso_date(r.get("maturityDate")), "call": iso_date(r.get("callDate")),
                 "placement": iso_date(r.get("placementDate")), "cpy": int(r.get("couponQuantityPerYear") or 0),
                 "aci": qf(r.get("aciValue")), "floating": bool(r.get("floatingCouponFlag")),
                 "amort": bool(r.get("amortizationFlag")), "perpetual": bool(r.get("perpetualFlag")),
                 "risk": r.get("riskLevel") or "", "sector": r.get("sector") or "", "name": r.get("name") or ""}
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


def bonds_report(client, rows):
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=365)).isoformat()
    bonds = [r for r in rows if r["type"] == "bond" and r["uid"] and r["qty"] > 0]
    infos = dict(zip([r["uid"] for r in bonds], pool_map(lambda r: bond_info(client, r["uid"]), bonds)))
    out, pays = [], []
    tot_bonds = sum((r["value_rub"] or 0) for r in bonds) or 0.0
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
        price = r["price"] if r["price"] else 0.0
        m = bond_metrics(b, price, today)
        row.update({"buy_pct": r["avg"] / nominal * 100 if r["avg"] else None, "price_pct": price / nominal * 100 if price else None,
                    "nominal": nominal, "ytm": m["ytm"], "dur": m["dur"], "to": m["to"], "coupon": m["coupon_rate"],
                    "cur_yield": m["cur_yield"], "next": m["next"], "spread": _spread(m["ytm"], m["dur"]), "maturity": b.get("maturity"), "call": b.get("call"),
                    "risk": RISK_RU.get(b.get("risk"), ""), "floating": b.get("floating"), "amort": b.get("amort"),
                    "sector": b.get("sector")})
        out.append(row)
        if m["ytm"] is not None and v:
            w["ytm"] += m["ytm"] * v
            w["ytm_v"] += v
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
        for d, p in b.get("coupons") or []:
            if today < d <= horizon:
                amt = (p or (known[-1] if known else 0.0)) * r["qty"]
                if amt:
                    pays.append({"date": d, "kind": "coupon", "name": r["name"], "ticker": r["ticker"], "logo": r["logo"],
                                 "amount": amt, "est": not p})
        if b.get("maturity") and today < b["maturity"] <= horizon:
            pays.append({"date": b["maturity"], "kind": "redemption", "name": r["name"], "ticker": r["ticker"],
                         "logo": r["logo"], "amount": nominal * r["qty"], "est": False})
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
    metrics = {"count": len(bonds), "value": tot_bonds,
               "ytm": w["ytm"] / w["ytm_v"] if w["ytm_v"] else None, "dur": w["dur"] / w["dur_v"] if w["dur_v"] else None,
               "cur_yield": w["cy"] / w["cy_v"] if w["cy_v"] else None,
               "coupons_12m": sum(p["amount"] for p in pays if p["kind"] == "coupon"),
               "issuers": len({r["name"].split(" ")[0] for r in bonds})}
    out.sort(key=lambda x: -(x.get("value_rub") or 0))
    return {"rows": out, "metrics": metrics, "ladder": sorted(ladder.items()), "risk": sorted(risk.items(), key=lambda x: -x[1]),
            "kinds": sorted(kinds.items(), key=lambda x: -x[1]), "payments": pays,
            "ratings": apply_ratings(out), "ratings_info": ratings_status()}


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


def build_bonds(cfg, acc, force=False):
    ratings_start()          # обновит рейтинги, если данным больше 12 часов
    key = ("bonds", token_key(cfg), acc)
    hit = None if force else mem_get(key, 600)
    if hit:
        st = ratings_status()
        if hit.get("ratings_info", {}).get("updated") != st["updated"]:
            hit["ratings"] = apply_ratings(hit["rows"])
        hit["ratings_info"] = st
        return hit
    s = build_summary(cfg, acc, "all")
    rep_ = mem_put(key, bonds_report(TInvest(cfg), s["portfolio"]["positions"]))
    try:
        expert_start([r["name"] for r in rep_["rows"]])      # дозапросит рейтинги Эксперт РА по эмитентам портфеля
    except Exception:  # noqa: BLE001
        pass
    return rep_


def build_history_for(cfg, acc, force=False):
    key = ("hist", token_key(cfg), acc)
    hit = None if force else mem_get(key, 900)
    if hit:
        return hit
    client = TInvest(cfg)
    accs, sel, data = selection(cfg, acc)
    ops = sorted([o for d in data for o in d["ops"]], key=lambda o: o.get("date") or "")
    keys = {(o.get("instrumentUid"), o.get("figi")) for o in ops
            if (o.get("instrumentUid") or o.get("figi")) and not str(o.get("instrumentUid") or "").startswith("imp:")}
    names = instruments(client, keys)
    total = sum(qf((d["port"] or {}).get("totalAmountPortfolio")) for d in data if d["port"] is not None)
    if any(d["port"] is None for d in data):
        total += sum(sum((r["value_rub"] or 0) for r in imported_positions(client, d["ops"], names)) for d in data if d["port"] is None)
    h = build_history(client, ops, names, total) or {"days": []}
    return mem_put(key, h)


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
            if data["max_id"] and mn <= data["max_id"]:
                break
            if not data["max_id"] and oldest < cutoff:
                break
            if before is not None and mn >= before:
                break
            before = mn
            time.sleep(0.25)
        items = data["items"]
        for pid in sorted(got):
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
        r["rating"] = rating_for(r.get("name") or "")
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


def screener_payload():
    rows = screener_rows()
    for r in rows:
        rt = rating_for(r["name"])
        r["rating"] = rt["v"] if rt else None
        r["rt_agency"] = rt["agency"] if rt else None
        r["rt_approx"] = bool(rt and rt["approx"])
    return {"rows": rows, "kbd": kbd_curve(), "updated": _scr["t"], "ratings": ratings_status()}


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
                pub = {k: v for k, v in cfg.items() if k != "token"}
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
            if u.path == "/api/primary":
                return self.send(200, primary_payload())
            if u.path == "/api/ratings":
                return self.send(200, ratings_status())
            if u.path == "/api/rates":
                return self.send(200, rates_payload(q.get("days", "365")))
            if u.path == "/api/backup":
                return self.send(200, make_backup(), "application/zip",
                                 {"Content-Disposition": 'attachment; filename="tinvest_backup_%s.zip"' % date.today().isoformat()})
            if u.path == "/api/import/template.csv":
                return self.send(200, TEMPLATE_CSV.encode("utf-8-sig"), "text/csv; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="import_template.csv"'})
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
                if "notify_days" in body:
                    try:
                        cfg["notify_days"] = max(0, min(60, int(body["notify_days"])))
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
.pos{color:var(--pos)}.neg{color:var(--neg)}.mu{color:var(--mu)}.t2{color:var(--tx2)}

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
 pri:'<path d="M12 2l2.6 6.3 6.9.6-5.2 4.5 1.6 6.7L12 16.4 6.1 20.1l1.6-6.7L2.5 8.9l6.9-.6z"/>',
 mkt:'<path d="M3 4v16h18"/><path d="M7 14l4-4 3 3 5-6"/>',
 reb:'<path d="M12 3v18M5 7h14M5 7l-2 6a3 3 0 0 0 6 0zM19 7l-2 6a3 3 0 0 0 6 0z"/>',
 set:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>'};
const svgI=(p,sw=1.8)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const PAGES=[['dash','Обзор'],['ret','Доходность'],['pos','Позиции'],['bonds','Облигации'],['pay','Выплаты'],['ops','Операции'],['fees','Комиссии'],['tax','Налоги'],['reb','Ребалансировка'],['mkt','Ставки'],['scr','Скринер облигаций'],['pri','Первичка'],null,['imp','Импорт отчётов'],['set','Настройки']];
const PERIODS=[['1m','Месяц'],['3m','3 мес'],['ytd','С начала года'],['12m','Год'],['py','Прошлый год'],['all','Всё время']];
const PERIOD_PAGES=['dash','ret','ops','fees'];
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
  return j;
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
  v.innerHTML=`<div class="wrap fade">${S.err?`<div class="msg err">${esc(S.err)}</div>`:''}${['dash','pay'].includes(S.page)?remindHtml():''}${({dash:pDash,ret:pRet,pos:pPos,bonds:pBonds,pay:pPay,ops:pOps,fees:pFees,tax:pTax,reb:pReb,mkt:pMkt,scr:pScr,pri:pPri})[S.page]()}</div>`;
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
  return hero+kpis+`<div class="g c-2-1"><div class="card"><h2>Стоимость и вложения<span class="sp">${periodName()}</span></h2>${eq}</div>
    <div class="card"><h2>Структура портфеля</h2><div id="c-alloc" class="chart"></div></div></div>
    <div class="g g2"><div class="card"><h2>Доходность по месяцам<span class="sp">последние 12 мес</span></h2>${mret}</div>
    <div class="card"><h2>Ближайшие выплаты<span class="sp">купоны · дивиденды · погашения</span></h2>${pays}</div></div>
    <div class="g g2"><div class="card"><h2>Крупнейшие позиции<span class="sp">стоимость · P&amp;L</span></h2>${topHtml}</div>
    <div class="card"><h2>Кто платит дивиденды и купоны<span class="sp">${periodName()}</span></h2>${incHtml}</div></div>`+marg;
}

function payMonths(pays,n){
  const now=new Date(),keys=[];for(let i=0;i<n;i++){const d=new Date(now.getFullYear(),now.getMonth()+i,1);keys.push(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0'))}
  const k3={coupon:{},dividend:{},redemption:{}};pays.forEach(p=>{const m=p.date.slice(0,7);if(keys.includes(m))k3[p.kind][m]=(k3[p.kind][m]||0)+p.amount});
  return{labels:keys.map(mlabel),tips:keys.map(m=>{const[y,mm]=m.split('-');return MONF[+mm-1]+' '+y}),
    series:[{n:'Купоны',c:S1,v:keys.map(k=>k3.coupon[k]||0)},{n:'Дивиденды',c:S3,v:keys.map(k=>k3.dividend[k]||0)},{n:'Погашения',c:S4,v:keys.map(k=>k3.redemption[k]||0)}]};
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
  const mxS=Math.max(...rows.map(r=>r.share||0)),mxY=Math.max(...rows.map(r=>r.ytm||0)),mxD=Math.max(...rows.map(r=>r.dur||0));
  const cols=[['name','Облигация','l'],['qty','Кол-во'],['buy_pct','Покупка, %'],['price_pct','Цена, %'],['value_rub','Стоимость'],['pnl_rub','P&L'],['share','Доля'],['ytm','Доходность'],['spread','Спред к КБД'],['dur','Дюрация'],['coupon','Купон'],['next','След. купон'],['maturity','Погашение'],['rk','Рейтинг','l'],['risk','Риск','l']];
  const th=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  const body=rows.map(r=>`<tr><td>${ident(r,[r.ticker,r.floating?'флоатер':'',r.amort?'амортизация':''].filter(Boolean).join(' · '))}</td>
    <td class="num">${f0(r.qty)}</td><td class="num">${r.buy_pct!=null?f2(r.buy_pct):'—'}</td><td class="num">${r.price_pct!=null?f2(r.price_pct):'—'}</td>
    <td class="num">${M(r.value_rub,'rub',0)}</td>
    <td class="num ${cls(r.pnl_rub)}"><span class="arr">${r.pnl_rub>0?'▲':r.pnl_rub<0?'▼':''}</span>${r.pnl_pct!=null?pct(r.pnl_pct,1):'—'}</td>
    ${heatCell(r.share,mxS,'201,133,0',pctp(r.share))}
    ${heatCell(r.ytm,mxY,'25,158,112',r.ytm!=null?pctp(r.ytm,2)+(r.to==='offer'?' <small class="mu">оф.</small>':''):'—')}
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread)+' п.п.':'—'}</td>
    ${heatCell(r.dur,mxD,'213,81,129',r.dur!=null?r.dur.toFixed(2).replace('.',',')+' г':'—')}
    <td class="num">${r.coupon!=null?pctp(r.coupon,2):'—'}</td>
    <td class="num">${r.next?`${ddm(r.next[0])}<br><small class="mu">${M(r.next[1])}</small>`:'—'}</td>
    <td class="num">${r.maturity?ddm(r.maturity):'—'}${r.call?`<br><small class="mu">оферта ${ddm(r.call)}</small>`:''}</td>
    <td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td>
    <td class="l">${r.risk?`<span class="tag" style="${r.risk==='высокий'?'color:var(--neg)':r.risk==='низкий'?'color:var(--pos)':''}">${r.risk}</span>`:''}</td></tr>`).join('');
  chart('c-ladder',bars,{h:220,labels:b.ladder.map(x=>x[0]),series:[{n:'Погашается / оферта',c:S1,v:b.ladder.map(x=>x[1])}],legend:false});
  return`<div class="g g6">${kpi('Облигации',M(m.value,'rub',0),`${m.count} выпусков · ${pctp(m.value/tot*100)} портфеля`,null,S1)}
    ${kpi('Доходность портфеля',pctp(m.ytm,2),'средневзвешенная к погашению / оферте','pos',S3)}
    ${kpi('Дюрация',m.dur!=null?m.dur.toFixed(2).replace('.',',')+' года':'—','средневзвешенная, по Маколею',null,S5)}
    ${kpi('Текущая купонная доходность',pctp(m.cur_yield,2),'годовой купон / цена',null,S4)}
    ${kpi('Купоны за 12 месяцев',M(m.coupons_12m,'rub',0),'по графику выплат, до налога','pos',S7)}
    ${kpi('Эмитентов',m.issuers,'диверсификация по компаниям',null,S2)}</div>
    <div class="card" style="padding:12px 10px 6px"><div class="tbl" style="max-height:calc(100vh - 200px)"><table id="btab" class="bt"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div></div>
    <div class="g g3"><div class="card"><h2>Лестница погашений и оферт, ₽</h2><div id="c-ladder" class="chart"></div></div>
    <div class="card"><h2>Кредитный риск (оценка брокера)</h2>${hbars(b.risk.map(([n,v])=>({n,v,c:n==='высокий'?S8:n==='низкий'?S3:n==='средний'?S4:'#6f7686',s:pctp(v/(m.value||1)*100)})),S1,null,0)}</div>
    <div class="card"><h2>Тип купона, выпусков</h2>${hbars(b.kinds.map(([n,v],i)=>({n,v,c:PAL[i]})),S1,x=>f0(x.v),1)}</div></div>
    ${ratingsCard(b)}
    ${insightsCard(b)}
    <p class="note">Доходность — эффективная годовая к погашению или к ближайшей оферте (пометка «оф.»), по текущей цене с НКД. Для флоатеров будущие купоны приняты равными последнему известному, для облигаций с амортизацией расчёт приблизительный. Дюрация — по Маколею, в годах.</p>`;
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
  const body=rows.map(r=>`<tr class="${r.start===today?'pnew':''}"><td class="l"><b>${esc(r.short||r.issuer)}</b><br><small class="mu">${esc(r.desc)}</small>${r.isin?`<br><small class="mu num">${esc(r.isin)}</small>`:''}</td>
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
S.scr=null;S.sf={q:'',cur:'RUB',kind:'all',rmin:'',rated:false,ymin:'',ymax:'60',tmax:'',turn:'',spmin:'',noOffer:false};S.ssort={k:'yield',d:-1};S.sn=150;
function loadScr(){api('/api/screener').then(j=>{const t=Date.now();j.rows.forEach(r=>{r.years=(new Date(r.mat)-t)/315576e5});S.scr=j;if(S.page==='scr')render()}).catch(e=>{S.scr={error:e.message,rows:[]};if(S.page==='scr')render()})}
function scrRows(){
  const f=S.sf,q=f.q.trim().toLowerCase(),ri=f.rmin?RSC.indexOf(f.rmin):-1;
  const nv=x=>x===''||isNaN(parseFloat(x))?null:parseFloat(String(x).replace(',','.'));
  const ymin=nv(f.ymin),ymax=nv(f.ymax),tmax=nv(f.tmax),turn=nv(f.turn),spmin=nv(f.spmin);
  let rs=S.scr.rows.filter(r=>{
    if(f.cur!=='all'&&r.cur!==f.cur)return false;
    if(f.kind!=='all'&&r.kind!==f.kind)return false;
    if(q&&!((r.name||'').toLowerCase().includes(q)||(r.isin||'').toLowerCase().includes(q)||(r.full||'').toLowerCase().includes(q)))return false;
    if(ri>=0&&!(r.rating&&RSC.indexOf(r.rating)<=ri))return false;
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
  const rs=scrRows(),n=Math.min(rs.length,S.sn);
  const cols=[['name','Выпуск','l'],['rating','Рейтинг','l'],['price','Цена, %'],['yield','Доходность'],['spread','Спред к КБД'],['coupon','Купон, %'],['years','До погашения'],['dur','Дюрация'],['turn','Оборот сегодня']];
  const {k,d}=S.ssort;
  $('#scr-head').innerHTML=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  $('#scr-body').innerHTML=rs.slice(0,n).map(r=>`<tr><td class="l"><b>${esc(r.name)}</b><br><small class="mu num">${esc(r.isin||r.id)}${r.offer?' · оферта '+ddm(r.offer):''}</small></td>
    <td class="l">${r.rating?`<span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}" title="${esc(r.rt_agency||'')}${r.rt_approx?' (приблизительное совпадение названия)':''}">${r.rt_approx?'≈ ':''}${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td>
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
  const rated=d.rows.filter(r=>r.rating).length;
  return`<div class="card"><h2>Подбор облигаций<span class="sp" id="scr-cnt"></span></h2>
    <div class="flt">
    <label class="field"><span>Поиск</span><input class="in" id="f-q" value="${esc(f.q)}" placeholder="название или ISIN"></label>
    <label class="field"><span>Валюта</span><select class="in" id="f-cur">${opt('RUB','Рубли',f.cur)}${opt('all','Все',f.cur)}${opt('USD','USD',f.cur)}${opt('CNY','CNY',f.cur)}${opt('EUR','EUR',f.cur)}</select></label>
    <label class="field"><span>Тип</span><select class="in" id="f-kind">${opt('all','Все',f.kind)}${opt('corp','Корпоративные',f.kind)}${opt('ofz','ОФЗ',f.kind)}</select></label>
    <label class="field"><span>Рейтинг не ниже</span><select class="in" id="f-rmin"><option value="">любой</option>${RSC.slice(0,10).map(x=>opt(x,x,f.rmin)).join('')}</select></label>
    <label class="field"><span>Доходность от, %</span><input class="in num" id="f-ymin" value="${esc(f.ymin)}" inputmode="decimal"></label>
    <label class="field"><span>Доходность до, %</span><input class="in num" id="f-ymax" value="${esc(f.ymax)}" inputmode="decimal"></label>
    <label class="field"><span>Спред к КБД от, п.п.</span><input class="in num" id="f-spmin" value="${esc(f.spmin)}" inputmode="decimal"></label>
    <label class="field"><span>До погашения, лет не более</span><input class="in num" id="f-tmax" value="${esc(f.tmax)}" inputmode="decimal"></label>
    <label class="field"><span>Оборот за день от, млн ₽</span><input class="in num" id="f-turn" value="${esc(f.turn)}" inputmode="decimal"></label>
    <label class="sw"><input type="checkbox" id="f-noffer" ${f.noOffer?'checked':''}><i></i><div><b>Без оферт</b></div></label>
    <button class="btn ghost" id="f-reset">Сбросить</button></div>
    <div class="tbl" style="max-height:calc(100vh - 300px)"><table><thead><tr id="scr-head"></tr></thead><tbody id="scr-body"></tbody></table></div>
    <div class="row" style="margin-top:12px"><button class="btn ghost" id="scr-more">Показать ещё</button></div></div>
  <p class="note">Данные — Московская биржа (ISS, режимы торгов Т+ для корпоративных облигаций и ОФЗ; с задержкой, как в бесплатном доступе). Доходность — по цене последних торгов, спред — к кривой КБД при той же дюрации. Рейтинг найден у ${rated} из ${d.rows.length} выпусков: эмитенты без рейтинга в базе не обязательно ненадёжны. По умолчанию скрыты выпуски с доходностью выше 60% (обычно это дефолтные или почти не торгуемые бумаги) — поле «Доходность до» можно очистить. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function bindScr(){
  if(!S.scr||S.scr.error){const b=$('#scr-r');if(b)b.onclick=()=>{S.scr=null;render()};return}
  const map={'f-q':'q','f-cur':'cur','f-kind':'kind','f-rmin':'rmin','f-ymin':'ymin','f-ymax':'ymax','f-spmin':'spmin','f-tmax':'tmax','f-turn':'turn'};
  let to;Object.entries(map).forEach(([id,k])=>{const e=$('#'+id);e.oninput=e.onchange=()=>{S.sf[k]=e.value;S.sn=150;clearTimeout(to);to=setTimeout(drawScr,150)}});
  $('#f-noffer').onchange=e=>{S.sf.noOffer=e.target.checked;S.sn=150;drawScr()};
  $('#f-reset').onclick=()=>{S.sf={q:'',cur:'RUB',kind:'all',rmin:'',rated:false,ymin:'',ymax:'60',tmax:'',turn:'',spmin:'',noOffer:false};render()};
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
  const red=new Set(f.filter(p=>p.kind==='redemption').map(p=>p.name));
  const KL={coupon:'купон',dividend:'дивиденд',redemption:'погашение'},by={};
  f.forEach(p=>(by[p.date]=by[p.date]||[]).push(p));
  const days=Object.keys(by).sort().map(dt=>{const items=by[dt].slice().sort((a,b)=>tot[b.name]-tot[a.name]).map(p=>({name:p.name,amount:p.amount,c:col[p.name],kind:p.kind,kl:KL[p.kind]||p.kind}));
    const [y,m,d]=dt.split('-');return{label:`${d}.${m}.${y}`,full:ddm(dt),total:items.reduce((a,x)=>a+x.amount,0),items}});
  return{days,legend:names.map(n=>({n,c:col[n],tag:red.has(n)?'погашение':''}))};
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
  const KIND={coupon:['Купон',S1],dividend:['Дивиденд',S3],redemption:['Погашение',S4]};
  const byM={};ps.forEach(p=>(byM[p.date.slice(0,7)]=byM[p.date.slice(0,7)]||[]).push(p));
  const list=Object.keys(byM).sort().map(m=>{const[y,mm]=m.split('-');const t=byM[m].reduce((a,x)=>a+x.amount,0);
    return`<div class="card"><h2>${MONF[+mm-1]} ${y}<span class="sp num" style="color:var(--pos);font-size:13px;font-weight:600">${M(t)}</span></h2><div class="li">`+
    byM[m].map(p=>`<div class="it">${logo(p,34)}<div><b>${esc(p.name)}</b><small>${ddm(p.date)} · <span style="color:${KIND[p.kind][1]}">${KIND[p.kind][0]}</span>${p.est?' · оценка':''}</small></div><div class="rv num">${M(p.amount)}</div></div>`).join('')+`</div></div>`}).join('');
  return`<div class="g g4">${kpi('Ближайшие 30 дней',M(sum(p=>p.date<=in30)),'',null,S1)}${kpi('За 12 месяцев',M(sum(()=>1)),'купоны, дивиденды и погашения','pos',S3)}
    ${kpi('Купоны',M(sum(p=>p.kind==='coupon')),ps.filter(p=>p.kind==='coupon').length+' выплат',null,S1)}${kpi('Дивиденды',M(sum(p=>p.kind==='dividend')),'только объявленные, до налога',null,S3)}</div>
    <div class="card"><h2>Календарь выплат по месяцам, ₽</h2><div id="c-pay" class="chart"></div></div>
    <div class="card"><h2>Выплаты по дням<span class="sp"><span class="seg" id="pdays">${[[30,'30 дней'],[90,'90 дней'],[365,'Год']].map(([d,t])=>`<button data-d="${d}" class="${d===S.payDays?'on':''}">${t}</button>`).join('')}</span></span></h2><div id="c-days" class="chart"></div></div>
    ${list?`<div class="g g2">${list}</div>`:'<div class="card empty">Выплат в ближайший год не ожидается</div>'}
    <p class="note">Купоны — по графику эмитента и текущему количеству бумаг (до НДФЛ). Для флоатеров будущие купоны — оценка по последнему известному. Дивиденды — только уже объявленные, сумма до налога.</p>`;
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
  $('#ndsave').onclick=async()=>{try{await post('/api/config',{notify_days:$('#nd').value});S.cfg.notify_days=+$('#nd').value;msg('Сохранено',1)}catch(e){msg(e.message)}};
  $('#ntf').onclick=async()=>{try{if(!('Notification' in window))return msg('Браузер не поддерживает уведомления');const r=await Notification.requestPermission();msg(r==='granted'?'Уведомления разрешены':'Уведомления не разрешены',r==='granted')}catch(e){msg(e.message)}};
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
const EVK={coupon:'купон',dividend:'дивиденд',redemption:'погашение',offer:'оферта'};
function remindHtml(){
  const ev=upcoming();if(!ev.length)return'';
  return`<div class="card remind noprint"><div>${svgI(IC.pay,1.8).replace('<svg','<svg width="22" height="22"')}</div><div><b>Ближайшие события (${ev.length})</b>
    ${ev.slice(0,6).map(e=>`<small>${ddm(e.date)} · ${EVK[e.kind]||e.kind} · ${esc(e.name)}${e.amount!=null?' · '+M(e.amount):''}</small>`).join('')}
    ${ev.length>6?`<small>…и ещё ${ev.length-6}</small>`:''}</div></div>`;
}
function notifyUpcoming(){
  try{
    if(!('Notification' in window)||Notification.permission!=='granted')return;
    const seen=new Set(JSON.parse(lsGet('ta_notified')||'[]'));
    upcoming().forEach(e=>{const k=e.date+'|'+e.kind+'|'+e.name;if(seen.has(k))return;seen.add(k);
      new Notification('T-Invest: '+(EVK[e.kind]||e.kind)+' '+ddm(e.date),{body:e.name+(e.amount!=null?' · '+M(e.amount):'')})});
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
 ['next','Точные амортизации облигаций','График амортизаций из API — для точной доходности и календаря выплат'],
 ['next','Налоги точнее','Перенос убытков прошлых лет, льгота долгосрочного владения (ЛДВ), ИИС, курсовые разницы'],
 ['later','Зашифрованная копия в облаке','Автоматическая зашифрованная копия базы'],
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
</script></body></html>
'''


if __name__ == "__main__":
    main()
