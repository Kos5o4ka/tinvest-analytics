#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборщик сообщений о раскрытии (714-П) для сервера данных TAnalytic. Отдельный долгоживущий процесс, только stdlib, Python 3.8+.

Источник — e-disclosure.azipi.ru (открытое зеркало). e-disclosure.ru НЕ используется (защита от ботов). Универсум эмитентов — ИНН
облигаций, которые сейчас торгуются на MOEX (ISS), обновляется раз в сутки. Разбор текста — функции dc_extract/doc_text из собранного
tinvest_analytics.py (--lib), дублирования парсера нет. Запросы к azipi идут строго по одному, не чаще раза в --pace секунд.

База `<data>/disclosure.sqlite` (WAL):
  universe(inn PK, name, isins JSON, updated)                       — эмитенты торгуемых облигаций
  feed(id PK, day, ts, title, org, inn, event_date, wanted, fetched, tries, err)
                                                                    — все элементы ленты дня (метаданные); wanted=1 — нужен текст
  docs(id PK, inn, title, published, body, sha, fetched_at)         — тексты нужных сообщений
  facts(doc_id, n, isin, inn, kind, event_date, due_date, conf, data JSON, parser_ver, PK(doc_id, n))
  days(day PK, pages, items, status 'done'|'partial', done_at)       — прогресс истории
  meta(k PK, v)                                                     — служебное (конец архива, вчера уже дособрано)

    python3 disclosure_worker.py --data DIR [--lib PATH] [--pace 1.5] [--interval 60] [--since 2015-01-01]
                                 [--no-backfill] [--once --days N] [--reparse] [--stats] [--crowd] [--verbose]

Режим --crowd: страницы azipi не скачиваются самим процессом (с VPS он недоступен), а запрашиваются через очередь заданий crowd.sqlite;
их скачивают и присылают приложения пользователей через сервер данных (server/crowd.py, /v1/crowd/*). Остальная логика (универсум, лента, тексты, разбор) та же.
"""
import argparse
import hashlib
import html as html_mod
import importlib.util
import json
import logging
import os
import re
import signal
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import crowd  # noqa: E402
UA = "TAnalytic-disclosure/1.0 (+https://github.com/Kos5o4ka/tinvest-analytics)"
AZIPI = "https://e-disclosure.azipi.ru"
ISS = "https://iss.moex.com/iss/securities.json?engine=stock&market=bonds&is_trading=1&limit=100&iss.meta=off&start=%d"
MSK = timezone(timedelta(hours=3))
DAY_S = 86400
# Заголовки сообщений, тексты которых нужны (подстроки, без учёта регистра). Факты вида other всё равно сохраняются.
WANTED_TITLES = ("выплаченные доходы", "начисленные доходы", "неисполнение обязательств", "итогах приобретения",
                 "результатах приобретения", "исполнении обязательств по приобретению",
                 "приобретение (наступление оснований для приобретения)", "досрочного погашения", "погашени",
                 "итогах размещения", "завершении размещения", "результатах размещения",
                 "дополнительного выпуска", "реализации приобретенных", "реализации приобретённых")
EMPTY_STOP = 60          # столько календарных дней подряд без сообщений = конец архива
log = logging.getLogger("disclosure")


class FetchError(Exception):
    pass


class Gone(FetchError):
    """Постоянный отказ (404 и прочие 4xx кроме 429): повторять бессмысленно."""


class Stopped(Exception):
    pass


class Pending(FetchError):
    """Режим --crowd: страница ещё не прислана пользователями; адрес стоит в очереди, повторить позже."""


# Приоритеты заданий в очереди (меньше = раньше): живая лента, тексты нужных сообщений (из них получаются факты), вчерашний день целиком,
# история, заглядывание вперёд по дням истории
P_LIVE, P_BODY, P_YDAY, P_HIST, P_AHEAD = 0, 1, 2, 3, 4
LIVE_AGE = 600           # живая лента сегодняшнего дня считается свежей 10 минут (режим --crowd)
AHEAD_DAYS = 3           # на сколько дней истории вперёд заранее просить первую страницу ленты
PURGE_EVERY = 3600


def msk_now():
    return datetime.now(MSK)


def wanted_title(title):
    t = (title or "").lower()
    return any(w in t for w in WANTED_TITLES)


# ───────────────────────── HTTP ─────────────────────────
class Fetcher:
    """Один поток, свой минимальный интервал на хост (azipi — pace, iss.moex.com — 0.3 с). get(url) -> str."""

    def __init__(self, pace=1.5, stop=None, timeout=40, retries=4, max_requests=0):
        self.paces = {"iss.moex.com": 0.3}
        self.pace, self.timeout, self.retries, self.max_requests = pace, timeout, retries, max_requests
        self.stop = stop or threading.Event()
        self.next_slot, self.fails, self.count = {}, 0, 0

    def _sleep(self, sec):
        if self.stop.wait(sec):
            raise Stopped()

    def get(self, url):
        host = urlparse(url).hostname or ""
        delay = 2.0
        for _ in range(self.retries):
            self._sleep(max(0.0, self.next_slot.get(host, 0) - time.monotonic()))
            if self.max_requests and self.count >= self.max_requests:
                raise FetchError("лимит запросов (--max-requests)")
            self.count += 1
            self.next_slot[host] = time.monotonic() + self.paces.get(host, self.pace)
            wait = delay
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data, ctype = r.read(), r.headers.get("Content-Type") or ""
                self.fails = 0
                return self.decode(data, ctype)
            except urllib.error.HTTPError as e:
                if e.code != 429 and e.code < 500:
                    self.fails = 0
                    raise Gone("HTTP %d: %s" % (e.code, url))
                ra = (e.headers.get("Retry-After") or "").strip()
                if ra.isdigit():
                    wait = min(int(ra), 600)
                err = "HTTP %d" % e.code
            except (urllib.error.URLError, OSError, socket.timeout) as e:
                err = str(e)[:100]
            self.fails += 1
            log.warning("ошибка запроса %s: %s (подряд %d)", url, err, self.fails)
            if self.fails >= 5:
                log.warning("5 ошибок подряд, пауза 10 минут")
                self.fails = 0
                self._sleep(600)
            else:
                self._sleep(wait)
            delay = min(delay * 2, 120)
        raise FetchError("не удалось получить " + url)

    @staticmethod
    def decode(data, ctype=""):
        m = re.search(r"charset=([\w-]+)", ctype, re.I)
        for enc in ([m.group(1)] if m else []) + ["utf-8"]:
            try:
                return data.decode(enc)
            except (UnicodeDecodeError, LookupError):
                pass
        return data.decode("cp1251", "replace")


class CrowdFetch:
    """Источник страниц для режима --crowd. Адреса azipi берутся из очереди пользовательских приложений (бросает Pending, пока страницы нет),
    остальное (ISS Мосбиржи) качается напрямую через `direct`."""

    def __init__(self, store, direct, default_prio=P_HIST):
        self.store, self.direct, self.default_prio = store, direct, default_prio

    def __call__(self, url, newer_than=None):
        if not url.startswith(AZIPI + "/"):
            return self.direct(url)
        r = self.store.get(url, newer_than)
        if r is None:
            self.store.want([url], self.default_prio, newer_than=newer_than)
            raise Pending("ждём страницу от пользователей: " + url)
        if r[0] == "failed":
            raise Gone("страницу не удалось получить: " + url)
        if r[0] != 200:
            raise Gone("HTTP %s: %s" % (r[0], url))
        return Fetcher.decode(r[1], r[2])

    def want(self, urls, prio, newer_than=None):
        return self.store.want(urls, prio, newer_than=newer_than)

    def have(self, url, newer_than=None):
        return self.store.has(url, newer_than)


# ───────────────────────── разбор страниц azipi ─────────────────────────
_ITEM = re.compile(r'<div class="item">\s*<div class="date">\s*([\d.: ]+?)\s*</div>.*?<a href="/messages/(\d+)/[^"]*"[^>]*>(.*?)</a>'
                   r'.*?<div class="info">(.*?)</div>', re.S)


def _iso(d):
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", d or "")
    return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else ""


def _b(info, label):
    m = re.search(label + r"[^<]*<b>(.*?)</b>", info, re.S)
    return html_mod.unescape(m.group(1)).strip() if m else ""


def parse_feed(html):
    """Страница ленты дня -> (элементы [{id, ts, title, org, inn, event_date}], номер последней страницы)."""
    items = []
    for ts, mid, title, info in _ITEM.findall(html):
        title = html_mod.unescape(re.sub(r"<[^>]+>", "", title)).strip()
        t = _iso(ts)
        items.append({"id": int(mid), "ts": (t + " " + ts.split()[-1]) if t and " " in ts else t, "title": re.sub(r"\s+", " ", title),
                      "org": _b(info, "Организация"), "inn": re.sub(r"\D", "", _b(info, "ИНН организации")),
                      "event_date": _iso(_b(info, "Дата события"))})
    pages = [int(x) for x in re.findall(r"PAGEN_2=(\d+)", html)]
    return items, max(pages + [1])


_END = re.compile(r"^(?:Настоящее сообщение предоставлено|©\s*20\d\d|Регистрационный код, присвоенный Банком России)", re.M)


def extract_body(html, lib, title=""):
    """Текст сообщения без навигации и подвала сайта: от «1. Общие сведения» (иначе от «Дата раскрытия:» или заголовка) до подвала."""
    text = lib.doc_text(html.encode("utf-8"), "text/html", "m.html")["text"]
    m = re.search(r"^1\.\s*Общие сведения", text, re.M) or re.search(r"^Дата раскрытия:", text, re.M)
    start = m.start() if m else 0
    if not m and title and text.rfind(title) >= 0:
        start = text.rfind(title)
    e = _END.search(text, start)
    return text[start:e.start() if e else len(text)].strip()


# ───────────────────────── база ─────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS universe(inn TEXT PRIMARY KEY, name TEXT, isins TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS feed(id INTEGER PRIMARY KEY, day TEXT, ts TEXT, title TEXT, org TEXT, inn TEXT, event_date TEXT,
  wanted INTEGER, fetched INTEGER DEFAULT 0, tries INTEGER DEFAULT 0, err TEXT);
CREATE INDEX IF NOT EXISTS feed_inn ON feed(inn);
CREATE INDEX IF NOT EXISTS feed_wf ON feed(wanted, fetched);
CREATE INDEX IF NOT EXISTS feed_day ON feed(day);
CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, inn TEXT, title TEXT, published TEXT, body TEXT, sha TEXT, fetched_at REAL);
CREATE TABLE IF NOT EXISTS facts(doc_id INTEGER, n INTEGER, isin TEXT, inn TEXT, kind TEXT, event_date TEXT, due_date TEXT, conf REAL,
  data TEXT, parser_ver TEXT, PRIMARY KEY(doc_id, n));
CREATE INDEX IF NOT EXISTS facts_isin ON facts(isin);
CREATE INDEX IF NOT EXISTS facts_inn ON facts(inn);
CREATE INDEX IF NOT EXISTS facts_kind ON facts(kind);
CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY, pages INTEGER, items INTEGER, status TEXT, done_at REAL);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def open_db(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    db = sqlite3.connect(os.path.join(data_dir, "disclosure.sqlite"), timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def load_lib(path):
    """Собранный tinvest_analytics.py как модуль — как tests/_load.py (изолированная папка данных, сервер данных выключен)."""
    os.environ["TINVEST_HOME"] = tempfile.mkdtemp(prefix="tinvest_disc_")
    os.environ["TINVEST_DATA_SERVER"] = "off"
    spec = importlib.util.spec_from_file_location("tinvest_analytics_lib", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["tinvest_analytics_lib"] = m
    spec.loader.exec_module(m)
    return m


def parser_ver(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:12]
    except OSError:
        return "unknown"


def get_meta(db, k, default=None):
    r = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def set_meta(db, k, v):
    db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, v))
    db.commit()


def stats(db, pace=1.5, since="2015-01-01", today=None):
    """Счётчики и оценка времени до конца истории (общая логика для --stats и /v1/parsed/disclosure/status)."""
    q = lambda s, *a: db.execute(s, a).fetchone()[0]  # noqa: E731
    r = {"universe": q("SELECT COUNT(*) FROM universe"), "feed": q("SELECT COUNT(*) FROM feed"),
         "wanted": q("SELECT COUNT(*) FROM feed WHERE wanted=1"), "fetched": q("SELECT COUNT(*) FROM feed WHERE wanted=1 AND fetched=1"),
         "docs": q("SELECT COUNT(*) FROM docs"), "facts": dict(db.execute("SELECT kind, COUNT(*) FROM facts GROUP BY kind").fetchall()),
         "days_done": q("SELECT COUNT(*) FROM days WHERE status='done'"), "days_partial": q("SELECT COUNT(*) FROM days WHERE status='partial'"),
         "backfill_newest": db.execute("SELECT MAX(day) FROM days WHERE status='done'").fetchone()[0],
         "backfill_oldest": db.execute("SELECT MIN(day) FROM days WHERE status='done'").fetchone()[0],
         "archive_end": get_meta(db, "archive_end")}
    ud = db.execute("SELECT MAX(updated) FROM universe").fetchone()[0]
    r["universe_updated"] = ud
    if r["archive_end"]:
        r["eta_days"], r["eta_sec"] = 0, 0
        return r
    today = today or msk_now().date()
    oldest = date.fromisoformat(r["backfill_oldest"]) if r["backfill_oldest"] else today
    left = max(0, (oldest - date.fromisoformat(since)).days) * 5 / 7.0         # осталось рабочих дней
    row = db.execute("SELECT AVG(pages), COUNT(*) FROM days WHERE status='done' AND items>0").fetchone()
    pages = row[0] or 64.0
    wpd = (q("SELECT COUNT(*) FROM feed WHERE wanted=1 AND day IN (SELECT day FROM days WHERE items>0)") / float(row[1])) if row[1] else 40.0
    r["eta_sec"] = int(left * (pages + wpd) * pace)
    r["eta_days"] = round(r["eta_sec"] / DAY_S, 1)
    return r


# ───────────────────────── сборщик ─────────────────────────
class Worker:
    def __init__(self, db, fetch, lib, pver="", since="2015-01-01", interval=60, body_cap=200, now=msk_now, stop=None, universe_pages=0, clock=time.time):
        self.db, self.fetch, self.lib, self.pver = db, fetch, lib, pver
        self.since, self.interval, self.body_cap, self.now = since, interval, body_cap, now
        self.stop = stop or threading.Event()
        self.universe_pages = universe_pages     # 0 = без ограничения (для отладки)
        self.universe_cache = None
        self.clock = clock
        self.crowd = hasattr(fetch, "want")      # режим --crowd: страницы приходят из очереди, а не из HTTP
        self.pass_new = {}                       # crowd: id, добавленные в текущем (ещё не завершённом) проходе живой ленты дня
        self.last_purge = 0.0

    def get(self, url, newer_than=None):
        return self.fetch(url, newer_than) if self.crowd else self.fetch(url)

    def hint(self, urls, prio, newer_than=None):
        if self.crowd and urls:
            self.fetch.want(urls, prio, newer_than)

    @staticmethod
    def feed_url(day, page=1):
        d = "%02d.%02d.%04d" % (int(day[8:]), int(day[5:7]), int(day[:4]))
        return "%s/messages/list/day-%s/?MESSAGE_BY_DAY=%s&PAGEN_2=%d" % (AZIPI, d, d, page)

    def day_rule(self, day, full):
        """(приоритет, newer_than) для страниц ленты дня в режиме --crowd. Страница ленты дня, принятая до конца этого дня, неполна."""
        today = self.now().date()
        d = date.fromisoformat(day)
        if d >= today and not full:
            return P_LIVE, self.clock() - LIVE_AGE
        end = datetime(d.year, d.month, d.day, tzinfo=MSK) + timedelta(days=1)
        return (P_YDAY if d == today - timedelta(days=1) else P_HIST), end.timestamp()

    # --- универсум ---
    def refresh_universe(self, force=False):
        last = self.db.execute("SELECT MAX(updated) FROM universe").fetchone()[0]
        if not force and last and time.time() - last < DAY_S:
            return
        uni, start, pages = {}, 0, 0
        while True:
            j = json.loads(self.fetch(ISS % start))
            sec = j.get("securities") or {}
            cols, rows = sec.get("columns") or [], sec.get("data") or []
            if not rows:
                break
            ix = {c.lower(): i for i, c in enumerate(cols)}
            for r in rows:
                inn = re.sub(r"\D", "", str(r[ix["emitent_inn"]] or ""))
                if not inn:
                    continue
                u = uni.setdefault(inn, {"name": r[ix["emitent_title"]] or "", "isins": []})
                isin = r[ix["isin"]] or r[ix["secid"]]
                if isin and isin not in u["isins"]:
                    u["isins"].append(isin)
            start += len(rows)
            pages += 1
            if self.universe_pages and pages >= self.universe_pages:
                break
        if not uni:
            log.warning("универсум пуст, оставляю прежний")
            return
        t = time.time()
        with self.db:
            self.db.execute("DELETE FROM universe")
            self.db.executemany("INSERT INTO universe VALUES(?,?,?,?)", [(k, v["name"], json.dumps(v["isins"]), t) for k, v in uni.items()])
        self.universe_cache = None
        # новые эмитенты: пересчитать wanted у ещё не загруженных сообщений
        rows = self.db.execute("SELECT id, title FROM feed WHERE wanted=0 AND fetched=0 AND inn IN (SELECT inn FROM universe)").fetchall()
        with self.db:
            self.db.executemany("UPDATE feed SET wanted=1 WHERE id=?", [(i,) for i, t_ in rows if wanted_title(t_)])
        log.info("универсум: %d эмитентов, %d бумаг", len(uni), sum(len(v["isins"]) for v in uni.values()))

    def universe(self):
        if self.universe_cache is None:
            self.universe_cache = {r[0] for r in self.db.execute("SELECT inn FROM universe")}
        return self.universe_cache

    # --- лента ---
    def ingest_day(self, day, full):
        """Читает страницы ленты дня. full=False (live): остановка на странице, где все id уже известны. -> (страниц, элементов, новых, нужных, полностью?)"""
        uni = self.universe()
        page, last, items_n, new_n, want_n, complete, read = 1, 1, 0, 0, 0, True, 0
        prio, newer = self.day_rule(day, full) if self.crowd else (0, None)
        while page <= last:
            if self.stop.is_set():
                complete = False
                break
            url = self.feed_url(day, page)
            if self.crowd:
                self.hint([url], prio, newer)
            items, last = parse_feed(self.get(url, newer))
            if self.crowd and full and page == 1 and last > 1:
                # лента дня целиком: просим все страницы сразу (параллельно разными пользователями) и берёмся за день, когда все пришли
                rest = [self.feed_url(day, p) for p in range(2, last + 1)]
                self.hint(rest, prio, newer)
                if not all(self.fetch.have(u, newer) for u in rest):
                    raise Pending("лента %s: жду страницы 2..%d" % (day, last))
            if not items:
                break
            known = {r[0] for r in self.db.execute("SELECT id FROM feed WHERE id IN (%s)" % ",".join("?" * len(items)), [i["id"] for i in items])}
            if self.crowd and not full:
                known -= self.pass_new.get(day, set())     # добавленное ранее в этом же проходе (он мог прерваться ожиданием страницы) считаем свежим
            fresh = [i for i in items if i["id"] not in known]
            with self.db:
                for i in fresh:
                    w = int(i["inn"] in uni and wanted_title(i["title"]))
                    want_n += w
                    self.db.execute("INSERT OR IGNORE INTO feed(id, day, ts, title, org, inn, event_date, wanted) VALUES(?,?,?,?,?,?,?,?)",
                                    (i["id"], day, i["ts"], i["title"], i["org"], i["inn"], i["event_date"], w))
            items_n, new_n, read = items_n + len(items), new_n + len(fresh), read + 1
            if self.crowd and not full:
                self.pass_new.setdefault(day, set()).update(i["id"] for i in fresh)
            if not full and not fresh:
                break
            page += 1
        self.pass_new.pop(day, None)
        log.info("день %s: страниц %d, элементов %d, новых %d, нужных %d", day, read, items_n, new_n, want_n)
        return read, items_n, new_n, want_n, complete

    def live_cycle(self):
        today = self.now().date()
        y = (today - timedelta(days=1)).isoformat()

        def yesterday():
            if get_meta(self.db, "live_yday") != y:       # после полуночи по Москве один раз дособрать вчерашний день целиком
                pages, items, _, _, ok = self.ingest_day(y, True)
                self.mark_day(y, pages, items, ok)
                if ok:
                    set_meta(self.db, "live_yday", y)

        steps = (self.refresh_universe, lambda: self.ingest_day(today.isoformat(), False), yesterday, lambda: self.fetch_bodies(self.body_cap))
        for step in steps:
            try:
                step()
            except Pending as e:                           # только --crowd: ждём страницу, остальные шаги цикла выполняем
                log.debug("%s", e)
            except (FetchError, ValueError, KeyError) as e:
                log.warning("live-цикл прерван: %s", e)
                break
        self.housekeeping()

    def housekeeping(self):
        """--crowd: переразбор сообщений, чьи страницы заменены большинством или отозваны (недоверенный ключ); чистка старых страниц очереди."""
        if not self.crowd:
            return
        for url, kind in self.fetch.store.pop_events():
            c = crowd.classify(url)
            if not c:
                continue
            if c[0] == "msg":
                self.db.execute("UPDATE feed SET fetched=0, tries=0 WHERE id=?", (c[1],))
                log.warning("сообщение %d: страница изменилась (%s), загружаю заново", c[1], kind)
            else:
                log.warning("лента %s стр. %d: страница изменилась (%s); уже добавленные элементы остаются", c[1], c[2], kind)
            self.db.commit()
        if self.clock() - self.last_purge > PURGE_EVERY:
            self.last_purge = self.clock()
            self.fetch.store.purge()

    def mark_day(self, day, pages, items, ok):
        self.db.execute("INSERT OR REPLACE INTO days VALUES(?,?,?,?,?)", (day, pages, items, "done" if ok else "partial", time.time()))
        self.db.commit()

    # --- тексты ---
    def fetch_bodies(self, cap, day=None):
        q = "SELECT id, ts, title, org, inn FROM feed WHERE wanted=1 AND fetched=0 AND tries<5" + (" AND day=?" if day else "") + " ORDER BY ts DESC LIMIT ?"
        rows = self.db.execute(q, ((day, cap) if day else (cap,))).fetchall()
        done = 0
        self.hint(["%s/messages/%d/" % (AZIPI, r[0]) for r in rows], P_BODY)       # --crowd: все нужные тексты сразу
        for mid, ts, title, org, inn in rows:
            if self.stop.is_set():
                break
            try:
                html = self.get("%s/messages/%d/" % (AZIPI, mid))
            except Pending:
                continue
            except Gone as e:
                self.db.execute("UPDATE feed SET tries=5, err=? WHERE id=?", (str(e)[:200], mid))
                self.db.commit()
                continue
            except FetchError as e:
                self.db.execute("UPDATE feed SET tries=tries+1, err=? WHERE id=?", (str(e)[:200], mid))
                self.db.commit()
                continue
            self.store_doc(mid, ts, title, org, inn, html)
            done += 1
        if rows:
            log.info("тексты: загружено %d из %d", done, len(rows))

    def store_doc(self, mid, ts, title, org, inn, html):
        try:
            body = extract_body(html, self.lib, title)
        except Exception as e:  # noqa: BLE001
            self.db.execute("UPDATE feed SET tries=tries+1, err=? WHERE id=?", ("extract: %s" % e, mid))
            self.db.commit()
            return
        self.db.execute("INSERT OR REPLACE INTO docs VALUES(?,?,?,?,?,?,?)",
                        (mid, inn, title, ts, body, hashlib.sha1(body.encode("utf-8")).hexdigest(), time.time()))
        self.db.execute("UPDATE feed SET fetched=1, err=NULL WHERE id=?", (mid,))
        self.parse_doc(mid, ts, title, org, inn, body)
        self.db.commit()

    def parse_doc(self, mid, ts, title, org, inn, body):
        """dc_extract -> facts (старые факты документа заменяются). Ошибка парсера пишется в feed.err."""
        self.db.execute("DELETE FROM facts WHERE doc_id=?", (mid,))
        try:
            ex = self.lib.dc_extract(body, title, {"published": ts, "code": str(mid), "company": org, "title": title})
        except Exception as e:  # noqa: BLE001
            self.db.execute("UPDATE feed SET err=? WHERE id=?", ("parse: %s" % e, mid))
            return 0
        for n, f in enumerate(ex.get("facts") or []):
            data = dict(f)
            data["warnings"] = ex.get("warnings") or []
            self.db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (mid, n, f.get("isin"), inn or ex.get("inn"), f.get("kind") or ex.get("kind"), ex.get("event_date"),
                             f.get("due_date"), f.get("conf"), json.dumps(data, ensure_ascii=False), self.pver))
        return len(ex.get("facts") or [])

    def reparse(self):
        rows = self.db.execute("SELECT d.id, d.published, d.title, f.org, d.inn, d.body FROM docs d LEFT JOIN feed f ON f.id=d.id").fetchall()
        n = 0
        for mid, ts, title, org, inn, body in rows:
            n += self.parse_doc(mid, ts, title, org or "", inn, body)
        self.db.commit()
        log.info("переразбор: документов %d, фактов %d", len(rows), n)

    # --- история ---
    def backfill_step(self):
        """Один день истории (от нового к старому). -> 'ok' | 'end' | 'err'."""
        if get_meta(self.db, "archive_end"):
            return "end"
        day, empty = self.now().date() - timedelta(days=1), 0
        while day.isoformat() >= self.since:
            ds = day.isoformat()
            r = self.db.execute("SELECT status, items FROM days WHERE day=?", (ds,)).fetchone()
            if r and r[0] == "done":
                empty = empty + 1 if not r[1] else 0
            else:
                if empty >= EMPTY_STOP:
                    break
                try:
                    if self.crowd:                       # заранее просим первые страницы ближайших дней истории
                        self.hint([self.feed_url((day - timedelta(days=k)).isoformat()) for k in range(1, AHEAD_DAYS + 1)
                                   if (day - timedelta(days=k)).isoformat() >= self.since], P_AHEAD, self.day_rule(ds, True)[1])
                    pages, items, _, _, ok = self.ingest_day(ds, True)
                    self.mark_day(ds, pages, items, ok)
                    if ok:
                        self.fetch_bodies(1000, ds)
                except Pending:
                    return "wait"
                except FetchError as e:
                    log.warning("день %s не дособран: %s", ds, e)
                    self.db.execute("INSERT OR REPLACE INTO days(day, pages, items, status, done_at) VALUES(?,0,0,'partial',?)", (ds, time.time()))
                    self.db.commit()
                    return "err"
                return "ok" if ok else "err"
            if empty >= EMPTY_STOP:
                break
            day -= timedelta(days=1)
        if empty >= EMPTY_STOP:
            set_meta(self.db, "archive_end", day.isoformat())
            log.info("конец архива: %d дней подряд без сообщений (до %s)", EMPTY_STOP, day.isoformat())
        return "end"

    def run(self, backfill=True):
        last_live = 0.0
        while not self.stop.is_set():
            if time.monotonic() - last_live >= self.interval:
                self.live_cycle()
                last_live = time.monotonic()
            st = self.backfill_step() if backfill else "end"
            if st == "ok":
                continue
            self.stop.wait(60 if st == "err" else min(5.0, self.interval) if st == "wait" else max(1.0, self.interval - (time.monotonic() - last_live)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сборщик сообщений о раскрытии для сервера данных TAnalytic")
    ap.add_argument("--data", required=True, help="каталог данных (disclosure.sqlite)")
    ap.add_argument("--lib", default=os.path.join(os.path.dirname(HERE), "tinvest_analytics.py"), help="собранный tinvest_analytics.py (парсер)")
    ap.add_argument("--pace", type=float, default=1.5, help="минимальный интервал между запросами к azipi, с")
    ap.add_argument("--interval", type=float, default=60, help="период live-цикла, с")
    ap.add_argument("--since", default="2015-01-01", help="как далеко назад собирать историю")
    ap.add_argument("--no-backfill", action="store_true")
    ap.add_argument("--once", action="store_true", help="один live-цикл + --days дней истории и выход")
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--reparse", action="store_true", help="заново разобрать все сохранённые тексты")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--max-requests", type=int, default=0, help="жёсткий лимит числа запросов за запуск (отладка)")
    ap.add_argument("--universe-pages", type=int, default=0, help="читать не больше N страниц ISS (отладка)")
    ap.add_argument("--crowd", action="store_true", help="страницы azipi собирают приложения пользователей через очередь crowd.sqlite (с VPS azipi недоступен)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = open_db(a.data)
    if a.stats:
        print(json.dumps(stats(db, a.pace, a.since), ensure_ascii=False, indent=2))
        return 0
    stop = threading.Event()
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stop.set())
    fetch = Fetcher(a.pace, stop, max_requests=a.max_requests).get
    if a.crowd:
        fetch = CrowdFetch(crowd.CrowdStore(os.path.join(a.data, "crowd.sqlite")), fetch)
    w = Worker(db, fetch, load_lib(a.lib), parser_ver(a.lib), a.since, a.interval,
               body_cap=400 if a.crowd else 200, stop=stop, universe_pages=a.universe_pages)
    try:
        if a.reparse:
            w.reparse()
        elif a.once:
            w.live_cycle()
            for _ in range(a.days):
                if w.backfill_step() != "ok":
                    break
        else:
            log.info("старт: данные %s, pace %.1f с, interval %.0f с%s", a.data, a.pace, a.interval, ", режим crowd" if a.crowd else "")
            w.run(not a.no_backfill)
    except Stopped:
        pass
    log.info("остановлен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
