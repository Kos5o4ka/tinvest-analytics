#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сервер данных T-Invest Analytics: общий кэширующий прокси к публичным источникам.

Клиент -> этот сервер -> MOEX ISS, ФНС ГИР БО, ЦБ, smart-lab, рейтинговые агентства.
Сервер ходит к источникам один раз, кэширует ответ в SQLite и отдаёт всем клиентам, соблюдая лимиты запросов.
Токены Т-Инвестиций и портфели сюда не попадают. Только стандартная библиотека, Python 3.8+.

    python3 tinvest_server.py [--host 127.0.0.1] [--port 8780] [--data DIR] [--key KEY] [--keys-db PATH --bot NAME] [--verbose]
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

VERSION = "1.0.0"
MIN, HOUR, DAY = 60, 3600, 86400

# ───────────────────────── разрешённые источники ─────────────────────────
# host -> префикс пути (None = любой). Только публичные данные. Хосты T-Invest API и Telegram Bot API сюда не входят:
# портфель и токены идут напрямую, через сервер не проходят.
ALLOWED_HOSTS = {
    "iss.moex.com": None, "www.moex.com": None,
    "bo.nalog.gov.ru": None,
    "www.cbr.ru": None, "cbr.ru": None,
    "smart-lab.ru": None,
    "raexpert.ru": None, "ratings.ru": None, "investmint.ru": None,
    "invest-brands.cdn-tinkoff.ru": None,
    "t.me": "/s/",                      # публичное зеркало канала с рейтингами (только страницы /s/...)
}

# Окно торгов Мосбиржи по Москве (UTC+3), будни: в это время рыночные данные устаревают быстро.
MSK = timezone(timedelta(hours=3))


def _trading_now(now):
    t = datetime.fromtimestamp(now, MSK)
    return t.weekday() < 5 and 9 <= t.hour < 24


def _moex_market_ttl(now):
    return 5 * MIN if _trading_now(now) else HOUR


# ───────────────────────── правила TTL ─────────────────────────
# Один список: первое совпадение (host, regex пути+запроса) решает. ttl — секунды или функция(now) -> секунды.
# post_ttl — разрешено ли кэшировать POST (только явные правила; ключ = url + хэш тела). 404 кэшируется на NOT_FOUND_TTL.
RULES = [
    # (хост,               регэксп пути+query,                        ttl,                post_ttl)
    ("iss.moex.com",       r"/iss/engines/stock/zcyc",                HOUR,               None),    # кривая КБД: раз в час
    ("iss.moex.com",       r"/iss/engines/.*/securities\.json",       _moex_market_ttl,   None),    # списки/marketdata: 5 мин в торги
    ("iss.moex.com",       r"/iss/history/",                          DAY,                None),    # история торгов
    ("iss.moex.com",       r"/iss/securities/[^/]+/bondization",      3 * DAY,            None),    # график выплат
    ("iss.moex.com",       r"/iss/securities",                        3 * DAY,            None),    # описание/поиск
    ("iss.moex.com",       r"/iss/emitters",                          7 * DAY,            None),    # эмитенты
    ("www.moex.com",       r".*",                                     DAY,                None),
    ("bo.nalog.gov.ru",    r".*",                                     7 * DAY,            None),    # ФНС: отчётность годовая
    ("smart-lab.ru",       r".*",                                     5 * DAY,            None),    # МСФО: страницы обновляются редко
    ("www.cbr.ru",         r"/dkp/|/statistics/|\.pdf",               12 * HOUR,          None),    # прогнозы, календарь, опросы
    ("www.cbr.ru",         r".*",                                     6 * HOUR,           None),    # курсы, ключевая ставка
    ("cbr.ru",             r".*",                                     12 * HOUR,          None),
    ("raexpert.ru",        r"/search/",                               12 * HOUR,          12 * HOUR),   # поиск эмитента (форма POST)
    ("raexpert.ru",        r".*",                                     12 * HOUR,          None),
    ("ratings.ru",         r".*",                                     12 * HOUR,          None),
    ("t.me",               r".*",                                     12 * HOUR,          None),    # канал рейтингов
    ("investmint.ru",      r".*",                                     6 * HOUR,           None),
    ("invest-brands.cdn-tinkoff.ru", r".*",                           30 * DAY,           None),    # логотипы
]
DEFAULT_TTL = HOUR
NOT_FOUND_TTL = 10 * MIN

# Вежливость к источникам: минимальный интервал между запросами к одному хосту (запросов в секунду).
RATES = {"iss.moex.com": 8.0, "www.moex.com": 4.0, "bo.nalog.gov.ru": 2.0, "smart-lab.ru": 1.0}
DEFAULT_RATE = 2.0

# Хосты, где cookie связаны с сессией (CSRF): GET с Set-Cookie не кэшируется, cookie передаются клиенту (X-Set-Cookie).
# Для остальных (например, MOEX ISS ставит служебные cookie) cookie отбрасываются, ответ кэшируется.
SESSION_HOSTS = {"raexpert.ru"}

UA_DEFAULT = "Mozilla/5.0 (compatible; tinvest-analytics)"
UA_BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0 Safari/537.36")
UA_BY_HOST = {"smart-lab.ru": UA_BROWSER, "invest-brands.cdn-tinkoff.ru": "Mozilla/5.0"}
# Заголовки клиента X-Up-<Имя>, которые передаются источнику.
FORWARD_HEADERS = ("Referer", "Cookie", "Accept", "Accept-Language")

MAX_BODY_IN = 1024 * 1024
MAX_BODY_OUT = 25 * 1024 * 1024
UPSTREAM_TIMEOUT = 30


class UpstreamError(Exception):
    pass


# ───────────────────────── авторизация ─────────────────────────
def normalize_key(k):
    return (k or "").strip().upper().replace(" ", "")


def key_hash(k):
    return hashlib.sha256(normalize_key(k).encode("utf-8")).hexdigest()


class KeyStore:
    """Ключи доступа, выданные Telegram-ботом. База принадлежит боту (общий файл SQLite, WAL): здесь она только читается,
    пишется лишь keys.last_used (не чаще раза в минуту на ключ, ошибки блокировки игнорируются).
    Результаты проверки кэшируются в памяти: положительный — на POS_TTL, но не дольше срока действия ключа; отрицательный — на NEG_TTL."""
    POS_TTL, NEG_TTL, USED_EVERY, MAX_CACHE = 60, 10, 60, 10000

    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock
        self._local = threading.local()
        self._lock = threading.Lock()
        self._cache, self._used = {}, {}
        self._warned = False

    def _conn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect("file:%s?mode=rw" % quote(self.path.replace("\\", "/"), safe="/:"),
                                uri=True, timeout=2, isolation_level=None)
            c.execute("PRAGMA busy_timeout=2000")
            self._local.c = c
        return c

    def _warn(self, e):
        if not self._warned:
            self._warned = True
            sys.stderr.write("keys-db: %s: %s (запросы будут отклонены, пока база недоступна)\n" % (type(e).__name__, e))

    def lookup(self, key):
        """-> (статус, инфо). Статус: ok | invalid | expired | banned | error."""
        h = key_hash(key)
        now = self.clock()
        with self._lock:
            hit = self._cache.get(h)
        if hit and hit[0] > now:
            res = hit[1]
        else:
            res = self._query(h, now)
            if res[0] == "error":
                return res
            ttl = self.POS_TTL if res[0] == "ok" else self.NEG_TTL
            until = now + ttl
            if res[0] == "ok":
                until = min(until, res[1]["expires"])
            with self._lock:
                if len(self._cache) > self.MAX_CACHE:
                    self._cache.clear()
                self._cache[h] = (until, res)
        if res[0] == "ok":
            self._touch(h, now)
        return res

    def _query(self, h, now):
        try:
            row = self._conn().execute(
                "SELECT k.tg_id, k.expires, k.revoked, u.banned, u.username, u.plan FROM keys k "
                "LEFT JOIN users u ON u.tg_id = k.tg_id WHERE k.key_hash = ?", (h,)).fetchone()
        except (sqlite3.Error, OSError) as e:
            self._local.c = None
            self._warn(e)
            return "error", None
        if not row:
            return "invalid", None
        tg_id, expires, revoked, banned, username, plan = row
        info = {"tg_id": tg_id, "expires": expires, "username": username or "", "plan": plan or "free"}
        if banned:
            return "banned", info
        if revoked or expires is None or expires <= now:
            return "expired", info
        return "ok", info

    def _touch(self, h, now):
        with self._lock:
            if now - self._used.get(h, 0) < self.USED_EVERY:
                return
            self._used[h] = now
            if len(self._used) > self.MAX_CACHE:
                self._used.clear()
        try:
            self._conn().execute("UPDATE keys SET last_used = ? WHERE key_hash = ?", (now, h))
        except (sqlite3.Error, OSError):
            pass


def auth_mode(server):
    return "keys" if server.keystore else ("key" if server.key else "none")


def authorize_ex(server, headers):
    """-> (client_id | None, причина, инфо). Причина при отказе: invalid | expired | banned.
    Принимается либо общий ключ (--key), либо личный ключ из бота (--keys-db); если не настроено ничего — открытый доступ."""
    if not server.key and not server.keystore:
        return "anon", None, None
    got = headers.get("X-Client-Key") or ""
    if server.key and hmac.compare_digest(got.encode("utf-8"), server.key.encode("utf-8")):
        return "key", None, None
    if server.keystore and got.strip():
        st, info = server.keystore.lookup(got)
        if st == "ok":
            return "tg:%s" % info["tg_id"], None, info
        return None, (st if st in ("expired", "banned") else "invalid"), info
    return None, "invalid", None


def authorize(server, headers):
    """Идентификатор клиента или None."""
    return authorize_ex(server, headers)[0]


# ───────────────────────── уведомления через бота ─────────────────────────
NOTIFY_MAX_CHARS, NOTIFY_PER_HOUR, NOTIFY_PER_DAY = 3500, 30, 200


class NotifyError(Exception):
    def __init__(self, code, error):
        Exception.__init__(self, error)
        self.code, self.error = code, error


class Notifier:
    """Очередь уведомлений: кладёт сообщения пользователя в таблицу outbox общей базы бота, откуда их забирает и
    отправляет бот (после отправки строка удаляется). Текст сообщений нигде не логируется. Лимиты на пользователя
    считаются по таблице notify_log (tg_id, время), поэтому переживают перезапуск сервера."""

    def __init__(self, keystore, clock=time.time, per_hour=NOTIFY_PER_HOUR, per_day=NOTIFY_PER_DAY):
        self.ks, self.clock = keystore, clock
        self.per_hour, self.per_day = per_hour, per_day
        self._lock = threading.Lock()
        self._last_purge = 0.0

    def enqueue(self, tg_id, text):
        """-> id строки outbox. Бросает NotifyError(409 notify_off | 429 rate_limit | 503 unavailable)."""
        now = self.clock()
        with self._lock:
            c = self.ks._conn()
            try:
                c.execute("BEGIN IMMEDIATE")
                try:
                    c.execute("CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER NOT NULL, "
                              "text TEXT NOT NULL, created REAL NOT NULL, tries INTEGER NOT NULL DEFAULT 0)")
                    c.execute("CREATE TABLE IF NOT EXISTS notify_log(tg_id INTEGER NOT NULL, created REAL NOT NULL)")
                    c.execute("CREATE INDEX IF NOT EXISTS notify_log_tg ON notify_log(tg_id, created)")
                    try:
                        row = c.execute("SELECT notify FROM users WHERE tg_id=?", (tg_id,)).fetchone()
                    except sqlite3.OperationalError:         # бот ещё не мигрировал базу: колонки notify нет, значит включено
                        row = c.execute("SELECT 1 FROM users WHERE tg_id=?", (tg_id,)).fetchone()
                    if not row:
                        raise NotifyError(403, "unknown_user")
                    if not row[0]:
                        raise NotifyError(409, "notify_off")
                    h = c.execute("SELECT COUNT(*) FROM notify_log WHERE tg_id=? AND created>?", (tg_id, now - HOUR)).fetchone()[0]
                    d = c.execute("SELECT COUNT(*) FROM notify_log WHERE tg_id=? AND created>?", (tg_id, now - DAY)).fetchone()[0]
                    if h >= self.per_hour or d >= self.per_day:
                        raise NotifyError(429, "rate_limit")
                    cur = c.execute("INSERT INTO outbox(tg_id, text, created) VALUES(?,?,?)", (tg_id, text, now))
                    c.execute("INSERT INTO notify_log(tg_id, created) VALUES(?,?)", (tg_id, now))
                    if now - self._last_purge > HOUR:
                        self._last_purge = now
                        c.execute("DELETE FROM notify_log WHERE created<?", (now - DAY,))
                    c.execute("COMMIT")
                    return cur.lastrowid
                except BaseException:
                    try:
                        c.execute("ROLLBACK")
                    except sqlite3.Error:
                        pass
                    raise
            except (sqlite3.Error, OSError) as e:
                self.ks._local.c = None
                self.ks._warn(e)
                raise NotifyError(503, "unavailable")


# ───────────────────────── кэш (SQLite, WAL) ─────────────────────────
class Cache:
    def __init__(self, path, max_bytes):
        self.max_bytes = max_bytes
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, status INTEGER, ctype TEXT, "
                        "body BLOB, fetched REAL, expires REAL, accessed REAL, size INTEGER)")
        self.db.execute("CREATE INDEX IF NOT EXISTS cache_acc ON cache(accessed)")
        self.total = self.db.execute("SELECT COALESCE(SUM(size),0) FROM cache").fetchone()[0]

    def count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM cache").fetchone()[0]

    def get(self, key, now):
        with self.lock:
            row = self.db.execute("SELECT status, ctype, body, fetched, expires FROM cache WHERE key=?", (key,)).fetchone()
            if row:
                self.db.execute("UPDATE cache SET accessed=? WHERE key=?", (now, key))
        return row

    def put(self, key, status, ctype, body, fetched, expires):
        size = len(body) + 200
        with self.lock:
            old = self.db.execute("SELECT size FROM cache WHERE key=?", (key,)).fetchone()
            self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?,?,?,?,?,?)",
                            (key, status, ctype, sqlite3.Binary(body), fetched, expires, fetched, size))
            self.total += size - (old[0] if old else 0)
            if self.total > self.max_bytes:
                self._evict()

    def _evict(self):
        """Удаляем самые давно использованные записи, пока не станет 90% лимита."""
        goal = int(self.max_bytes * 0.9)
        rows = self.db.execute("SELECT key, size FROM cache ORDER BY accessed ASC").fetchall()
        for key, size in rows:
            if self.total <= goal:
                break
            self.db.execute("DELETE FROM cache WHERE key=?", (key,))
            self.total -= size


# ───────────────────────── ядро ─────────────────────────
class Result:
    __slots__ = ("status", "ctype", "body", "xcache", "age", "cookies", "error")

    def __init__(self, status, ctype, body, xcache="miss", age=0, cookies=(), error=None):
        self.status, self.ctype, self.body, self.xcache, self.age = status, ctype, body, xcache, age
        self.cookies, self.error = list(cookies), error


class _NoRedirectCheck(urllib.request.HTTPRedirectHandler):
    """Редирект разрешён только на разрешённые хосты (защита от SSRF через редиректы)."""
    def __init__(self, check):
        self.check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.check(newurl):
            raise urllib.error.HTTPError(newurl, 403, "redirect to a host that is not allowed", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class DataServer:
    def __init__(self, data_dir, key="", max_mb=1024, clock=time.time, extra_allow=(), rates=None, verbose=False,
                 upstream=None, rules=None, keys_db="", bot="tanalyticbot"):
        os.makedirs(data_dir, exist_ok=True)
        self.key, self.clock, self.verbose = key or "", clock, verbose
        self.bot = (bot or "tanalyticbot").strip().lstrip("@")
        self.keystore = KeyStore(keys_db, clock) if keys_db else None
        self.notifier = Notifier(self.keystore, clock) if self.keystore else None
        self.allowed = dict(ALLOWED_HOSTS)
        for h in extra_allow:                       # для тестов: "127.0.0.1:PORT"
            self.allowed[h] = None
        self.rates = dict(RATES if rates is None else rates)
        self.default_rate = DEFAULT_RATE if rates is None else rates.get("*", DEFAULT_RATE)
        self.rules = [(h, re.compile(p), t, pt) for h, p, t, pt in (RULES if rules is None else rules)]
        self.cache = Cache(os.path.join(data_dir, "cache.sqlite"), int(max_mb * 1024 * 1024))
        self.started = time.time()
        self.upstream = upstream or self._http_upstream
        self._flights, self._flock = {}, threading.Lock()
        self._rate_lock, self._next_slot = threading.Lock(), {}
        self._stats_lock, self._stats = threading.Lock(), {}

    # --- разрешённость URL ---
    def url_allowed(self, url):
        try:
            u = urlparse(url)
            host, port = (u.hostname or "").lower(), u.port
        except ValueError:
            return False
        if u.scheme not in ("http", "https") or not host or u.username or u.password:
            return False
        if u.netloc.lower() in self.allowed:        # запись вида host:port (тесты)
            prefix = self.allowed[u.netloc.lower()]
        elif host in self.allowed and port in (None, 80, 443):
            prefix = self.allowed[host]
        else:
            return False
        return prefix is None or (u.path or "/").startswith(prefix)

    # --- статистика (без IP клиентов) ---
    def _stat(self, host, field):
        with self._stats_lock:
            s = self._stats.setdefault(host, {"requests": 0, "hit": 0, "miss": 0, "stale": 0, "upstream_errors": 0})
            s[field] += 1

    def stats(self):
        with self._stats_lock:
            hosts = {h: dict(v) for h, v in self._stats.items()}
        hit = sum(v["hit"] for v in hosts.values())
        miss = sum(v["miss"] for v in hosts.values())
        return {"hosts": hosts, "hit": hit, "miss": miss, "stale": sum(v["stale"] for v in hosts.values()),
                "hit_ratio": round(hit / (hit + miss), 4) if hit + miss else 0.0,
                "upstream_errors": sum(v["upstream_errors"] for v in hosts.values())}

    # --- TTL ---
    def ttl_for(self, host, url, method, now):
        u = urlparse(url)
        path = u.path + ("?" + u.query if u.query else "")
        netloc = u.netloc.lower()
        for h, rx, ttl, post_ttl in self.rules:
            if h in (host, netloc) and rx.match(path):
                if method == "POST":
                    return post_ttl
                return ttl(now) if callable(ttl) else ttl
        return None if method == "POST" else DEFAULT_TTL

    # --- вежливость к источнику ---
    def _throttle(self, host):
        rate = self.rates.get(host, self.default_rate)
        gap = 1.0 / rate if rate > 0 else 0
        with self._rate_lock:
            t = time.monotonic()
            slot = max(t, self._next_slot.get(host, 0))
            self._next_slot[host] = slot + gap
        if slot > t:
            time.sleep(slot - t)

    def _http_upstream(self, method, url, body, ctype, headers):
        host = (urlparse(url).hostname or "").lower()
        hd = {"User-Agent": UA_BY_HOST.get(host, UA_DEFAULT)}
        hd.update(headers)
        if body is not None and ctype:
            hd["Content-Type"] = ctype
        req = urllib.request.Request(url, data=body, headers=hd, method=method)
        opener = urllib.request.build_opener(_NoRedirectCheck(self.url_allowed))
        try:
            r = opener.open(req, timeout=UPSTREAM_TIMEOUT)
        except urllib.error.HTTPError as e:
            r = e
        try:
            data = r.read(MAX_BODY_OUT + 1)
            if len(data) > MAX_BODY_OUT:
                raise UpstreamError("response too large")
            cookies = r.headers.get_all("Set-Cookie") or []
            return r.status if hasattr(r, "status") else r.code, r.headers.get("Content-Type") or "application/octet-stream", data, cookies
        finally:
            r.close()

    # --- основной запрос ---
    def fetch(self, method, url, body=None, ctype="", headers=None):
        headers = headers or {}
        host = (urlparse(url).netloc.lower() if urlparse(url).netloc.lower() in self.allowed else urlparse(url).hostname)
        self._stat(host, "requests")
        now = self.clock()
        ttl = self.ttl_for(host, url, method, now)
        has_cookie = any(k.lower() == "cookie" for k in headers)
        # GET с куками сессии не кэшируем: ответ зависит от сессии. POST — только по явному правилу.
        cacheable = ttl is not None and (method == "POST" or not has_cookie)
        key = hashlib.sha256((method + " " + url + " " + hashlib.sha256(body or b"").hexdigest()).encode()).hexdigest()
        row = self.cache.get(key, now) if cacheable else None
        if row and row[4] > now:
            self._stat(host, "hit")
            return Result(row[0], row[1], row[2], "hit", int(now - row[3]))
        res = self._single_flight(key, lambda: self._do_upstream(method, url, body, ctype, headers, host, key, ttl, cacheable))
        if res.error and row:                                   # источник недоступен: отдаём устаревшее
            self._stat(host, "stale")
            return Result(row[0], row[1], row[2], "stale", int(now - row[3]))
        if res.error:
            return res
        self._stat(host, "miss")
        return res

    def _single_flight(self, key, fn):
        with self._flock:
            fl = self._flights.get(key)
            leader = fl is None
            if leader:
                fl = self._flights[key] = {"ev": threading.Event(), "res": None}
        if not leader:
            fl["ev"].wait(UPSTREAM_TIMEOUT * 2)
            return fl["res"] or Result(502, "text/plain", b"upstream timeout", error="timeout")
        try:
            fl["res"] = fn()
        except Exception as e:  # noqa: BLE001
            fl["res"] = Result(502, "text/plain", ("upstream error: %s" % type(e).__name__).encode(), error=str(e))
        finally:
            with self._flock:
                self._flights.pop(key, None)
            fl["ev"].set()
        return fl["res"]

    def _do_upstream(self, method, url, body, ctype, headers, host, key, ttl, cacheable):
        self._throttle(host)
        try:
            status, ct, data, cookies = self.upstream(method, url, body, ctype, headers)
        except Exception as e:  # noqa: BLE001
            self._stat(host, "upstream_errors")
            return Result(502, "text/plain", ("upstream error: %s" % type(e).__name__).encode(), error=str(e))
        if status >= 500:
            self._stat(host, "upstream_errors")
            return Result(502, "text/plain", b"upstream status %d" % status, error="status %d" % status)
        if host not in SESSION_HOSTS:
            cookies = []
        if cacheable and not (cookies and method == "GET"):
            now = self.clock()
            if 200 <= status < 300:
                self.cache.put(key, status, ct, data, now, now + ttl)
            elif status == 404:
                self.cache.put(key, status, ct, data, now, now + min(ttl, NOT_FOUND_TTL))
        return Result(status, ct, data, "miss", 0, cookies)


# ───────────────────────── HTTP ─────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "tinvest-data/" + VERSION
    protocol_version = "HTTP/1.1"
    app = None   # DataServer

    def log_message(self, fmt, *args):
        if self.app.verbose:
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _handle(self):
        app = self.app
        u = urlparse(self.path)
        body = b""
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY_IN:
            return self._send(413, {"error": "body too large"})
        if n:
            body = self.rfile.read(n)
        if u.path == "/v1/health":
            return self._send(200, {"ok": True, "version": VERSION, "uptime": int(time.time() - app.started),
                                    "cache_items": app.cache.count(), "auth": auth_mode(app), "bot": app.bot})
        client, reason, info = authorize_ex(app, self.headers)
        if client is None:
            return self._send(401, {"ok": False, "error": reason or "invalid", "bot": app.bot})
        if u.path == "/v1/auth/check":
            return self._send(200, {"ok": True, "expires": info["expires"] if info else None,
                                    "username": info["username"] if info else "", "plan": info["plan"] if info else "",
                                    "bot": app.bot})
        if u.path == "/v1/notify":
            return self._notify(client, info, body)
        if u.path == "/v1/stats":
            return self._send(200, app.stats())
        if u.path == "/v1/fetch":
            url = (parse_qs(u.query).get("url") or [""])[0]
            if not app.url_allowed(url):
                return self._send(403, {"error": "host not allowed"})
            method = "POST" if self.command == "POST" else "GET"
            hdrs = {}
            for name in FORWARD_HEADERS:
                v = self.headers.get("X-Up-" + name)
                if v:
                    hdrs[name] = v
            r = app.fetch(method, url, body if method == "POST" else None, self.headers.get("Content-Type") or "", hdrs)
            if r.error:
                return self._send(502, {"error": "upstream failed"}, extra=[("X-Upstream-Error", "1")])
            extra = [("X-Cache", r.xcache), ("X-Age", str(r.age))] + [("X-Set-Cookie", c) for c in r.cookies]
            return self._send(r.status, r.body, r.ctype, extra)
        self._send(404, {"error": "not found"})

    def _notify(self, client, info, body):
        if self.command != "POST":
            return self._send(405, {"error": "method not allowed"}, extra=[("Allow", "POST")])
        if not self.app.notifier or not info:
            return self._send(403, {"error": "уведомления доступны только по ключу из бота"})
        try:
            text = json.loads(body.decode("utf-8")).get("text")
        except (ValueError, AttributeError, UnicodeDecodeError):
            text = None
        if not isinstance(text, str) or not text.strip():
            return self._send(400, {"error": "empty_text"})
        if len(text) > NOTIFY_MAX_CHARS:
            return self._send(400, {"error": "text_too_long", "max": NOTIFY_MAX_CHARS})
        try:
            qid = self.app.notifier.enqueue(info["tg_id"], text)
        except NotifyError as e:
            return self._send(e.code, {"ok": False, "error": e.error})
        self._send(200, {"ok": True, "queued": qid})

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()


def make_http_server(app, host="127.0.0.1", port=8780):
    handler = type("BoundHandler", (Handler,), {"app": app})
    ThreadingHTTPServer.request_queue_size = 128
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сервер данных T-Invest Analytics")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--data", default=os.path.join(os.path.expanduser("~"), ".tinvest_server"))
    ap.add_argument("--key", default=os.environ.get("TINVEST_SERVER_KEY", ""))
    ap.add_argument("--keys-db", default=os.environ.get("TINVEST_KEYS_DB", ""),
                    help="SQLite-база Telegram-бота с личными ключами (users, keys); включает вход по ключу из бота")
    ap.add_argument("--bot", default=os.environ.get("TINVEST_BOT", "tanalyticbot"), help="имя бота, которое сообщается клиентам")
    ap.add_argument("--max-mb", type=int, default=1024, help="лимит размера кэша, МБ")
    ap.add_argument("--allow", action="append", default=[], help="дополнительный разрешённый host[:port] (для тестов)")
    ap.add_argument("--verbose", action="store_true", help="писать в журнал строки запросов (по умолчанию не пишется)")
    ap.add_argument("--version", action="store_true")
    a = ap.parse_args(argv)
    if a.version:
        print(VERSION)
        return 0
    app = DataServer(a.data, a.key, a.max_mb, extra_allow=a.allow, verbose=a.verbose, keys_db=a.keys_db, bot=a.bot)
    srv = make_http_server(app, a.host, a.port)
    print("tinvest-data %s: http://%s:%d, кэш %s%s" % (VERSION, a.host, a.port, a.data, (", ключ включён" if a.key else "") + (", вход по ключам бота @%s" % app.bot if app.keystore else "")), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
