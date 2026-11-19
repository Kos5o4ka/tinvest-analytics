#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Краудсорсинг страниц раскрытия: очередь заданий, приём и проверка страниц от приложений пользователей. Только stdlib, Python 3.8+.

Сервер данных стоит там, где e-disclosure.azipi.ru недоступен (VPS блокируется), а у пользователей в России страницы открываются.
Поэтому сборщик (disclosure_worker.py --crowd) не ходит к azipi сам: нужные адреса он кладёт в очередь (`want`), приложения пользователей
берут задания через сервер данных (`lease`), скачивают страницы у себя и присылают их (`submit`), сборщик забирает принятые страницы (`get`).

База `<data>/crowd.sqlite` (WAL) общая для процесса сервера данных и процесса сборщика; все записи идут короткими транзакциями BEGIN IMMEDIATE,
у каждого потока своё соединение, busy_timeout 30 с.

  tasks(id, url UNIQUE, kind, prio, state 'queued'|'leased'|'done'|'failed', gen, lease_key, lease_until, not_before, tries,
        verified, conflict, vkey, vuntil, created)       — очередь; prio меньше = раньше; gen растёт при повторном запросе (обновление живой ленты)
  pages(url PK, gen, status, sha, body gz, ctype, accepted_at, key_id, ver, changed)  — принятая страница (для 404 body пуст)
  subs(url, key_id, gen, status, sha, body gz|NULL, ts)  — последнее присланное каждым ключом; тело хранится, только если sha отличается от принятого
  keys(key_id PK, submits, accepted, rejected, last_submit, day, day_n, distrusted, first_seen, last_seen)
  events(id, url, kind, ts)                              — что сборщику надо переразобрать (страница заменена или принятая отозвана)

Приём: первая прошедшая проверку страница принимается сразу (пользователей может быть очень мало), но запоминается вместе с ключом и sha256 нормализованного
тела. Если другой ключ присылает по тому же адресу и поколению другое содержимое, побеждает большинство разных (не недоверенных) ключей; при равенстве
остаётся принятое, а задание уходит на проверку третьему ключу. Недоверенный ключ (`python3 crowd.py --data DIR distrust ID`) игнорируется, а его принятые
страницы возвращаются в очередь.
"""
import argparse
import base64
import gzip
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import sys
import threading
import time
import zlib
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger("crowd")
MSK = timezone(timedelta(hours=3))
AZIPI = "https://e-disclosure.azipi.ru"

LEASE_SEC = 300              # срок аренды задания
MAX_BODY = 2 * 1024 * 1024   # лимит размера страницы после распаковки
MIN_SUBMIT_GAP = 5.0         # не чаще одной отправки в 5 с на ключ
DAY_CAP = 6000               # отправок в сутки на ключ (при темпе 1 страница в 15 с — не больше 5760)
MAX_TASKS_PER_CALL = 5
MAX_TRIES = 8                # столько неудач подряд — задание 'failed' (сборщик увидит Gone / FetchError)
RETRY_5XX = 600              # пауза перед повтором после 429/5xx у клиента
GONE_RETRY = 3600            # пауза после сообщения «404»
GONE_VOTES = 2               # столько разных ключей должны сообщить 404 (или один — после 3 попыток)
VERIFY_P = 0.04              # доля выдач, когда вместо новой работы отдаётся уже принятая страница на перепроверку другим ключом
KEEP_DAYS = 7                # сколько хранить принятые страницы и задания

_FEED = re.compile(r"^https://e-disclosure\.azipi\.ru/messages/list/day-(\d{2})\.(\d{2})\.(\d{4})/\?MESSAGE_BY_DAY=(\d{2})\.(\d{2})\.(\d{4})&PAGEN_2=(\d{1,3})$")
_MSG = re.compile(r"^https://e-disclosure\.azipi\.ru/messages/(\d{1,10})/$")
_BAD = ("captcha", "recaptcha", "just a moment", "access denied", "attention required", "ddos", "cf-browser-verification", "are you a robot",
        "доступ ограничен", "подтвердите, что вы не робот", "проверка безопасности")


def classify(url):
    """-> ('feed', 'ДД.ММ.ГГГГ', страница) | ('msg', id, 0) | None. Только эти две формы адресов и только azipi."""
    if not isinstance(url, str) or len(url) > 200:
        return None
    m = _FEED.match(url)
    if m:
        d = m.groups()
        if d[:3] != d[3:6] or not 1 <= int(d[6]) <= 500:
            return None
        try:
            date(int(d[2]), int(d[1]), int(d[0]))
        except ValueError:
            return None
        return "feed", "%s.%s.%s" % d[:3], int(d[6])
    m = _MSG.match(url)
    if m:
        return "msg", int(m.group(1)), 0
    return None


def decode_text(data, ctype=""):
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I)
    for enc in ([m.group(1)] if m else []) + ["utf-8"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass
    return data.decode("cp1251", "replace")


def normalize(text):
    """Тело страницы без того, что меняется от запроса к запросу (скрипты, комментарии, сессионные поля, пробелы)."""
    s = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->", "", text, flags=re.S | re.I)
    s = re.sub(r"<input[^>]+type=[\"']?hidden[^>]*>", "", s, flags=re.I)
    s = re.sub(r"(?:bitrix_)?sessid=[0-9a-zA-Z]+", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def body_sha(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def check_page(url, text):
    """Похожа ли страница на ожидаемую страницу azipi. -> None (годится) или причина отказа."""
    c = classify(url)
    if not c:
        return "bad url"
    low = text.lower()
    if any(b in low for b in _BAD):
        return "captcha or error page"
    if c[0] == "feed":
        if c[1] not in text:
            return "feed page without the requested date"
        if 'class="item"' not in text and "/messages/" not in text:
            return "not a feed page"
        return None
    mid = str(c[1])
    if mid not in text or not ("АЗИПИ" in text or "e-disclosure" in low):
        return "message page without the message id"
    return None


def gzip_b64(raw):
    return base64.b64encode(gzip.compress(raw, 6, mtime=0)).decode("ascii")


def gunzip_limited(b64, limit=MAX_BODY):
    """gzip+base64 -> байты; ValueError при мусоре или превышении лимита (защита от «бомбы»)."""
    try:
        gz = base64.b64decode(b64, validate=True)
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = d.decompress(gz, limit + 1)
    except Exception:  # noqa: BLE001
        raise ValueError("bad body")
    if len(raw) > limit or d.unconsumed_tail:
        raise ValueError("too large")
    return raw


class CrowdError(Exception):
    def __init__(self, code, error, **extra):
        Exception.__init__(self, error)
        self.code, self.error, self.extra = code, error, extra


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, kind TEXT, prio INTEGER, state TEXT, gen INTEGER DEFAULT 1,
  lease_key TEXT, lease_until REAL DEFAULT 0, not_before REAL DEFAULT 0, tries INTEGER DEFAULT 0, verified INTEGER DEFAULT 0,
  conflict INTEGER DEFAULT 0, vkey TEXT, vuntil REAL DEFAULT 0, created REAL);
CREATE INDEX IF NOT EXISTS tasks_q ON tasks(state, prio, id);
CREATE TABLE IF NOT EXISTS pages(url TEXT PRIMARY KEY, gen INTEGER, status INTEGER, sha TEXT, body BLOB, ctype TEXT, accepted_at REAL,
  key_id TEXT, ver INTEGER DEFAULT 1, changed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS subs(url TEXT, key_id TEXT, gen INTEGER, status INTEGER, sha TEXT, body BLOB, ts REAL, PRIMARY KEY(url, key_id));
CREATE TABLE IF NOT EXISTS keys(key_id TEXT PRIMARY KEY, submits INTEGER DEFAULT 0, accepted INTEGER DEFAULT 0, rejected INTEGER DEFAULT 0,
  last_submit REAL DEFAULT 0, day TEXT DEFAULT '', day_n INTEGER DEFAULT 0, distrusted INTEGER DEFAULT 0, first_seen REAL, last_seen REAL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, kind TEXT, ts REAL);
"""


class CrowdStore:
    def __init__(self, path, clock=time.time, rng=None):
        self.path, self.clock = path, clock
        self.rng = rng or random.Random()
        self._local = threading.local()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        c = self.conn()
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)

    def conn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            c.execute("PRAGMA busy_timeout=30000")
            self._local.c = c
        return c

    def _tx(self):
        return _Tx(self.conn())

    def close(self):
        c = getattr(self._local, "c", None)
        if c is not None:
            c.close()
            self._local.c = None

    # ───────────── сторона сборщика ─────────────
    def want(self, urls, prio, now=None, newer_than=None):
        """Поставить адреса в очередь (повторный вызов безвреден). Страница, уже принятая и достаточно свежая (accepted_at >= newer_than), пропускается.
        -> число новых/возобновлённых заданий."""
        now = now or self.clock()
        n = 0
        with self._tx() as c:
            for u in urls:
                cl = classify(u)
                if not cl:
                    raise ValueError("url not allowed: %s" % u)
                pg = c.execute("SELECT accepted_at FROM pages WHERE url=?", (u,)).fetchone()
                if pg and (newer_than is None or pg[0] >= newer_than):
                    continue
                t = c.execute("SELECT id, state, prio FROM tasks WHERE url=?", (u,)).fetchone()
                if not t:
                    c.execute("INSERT INTO tasks(url, kind, prio, state, created) VALUES(?,?,?,?,?)", (u, cl[0], prio, "queued", now))
                    n += 1
                elif t[1] in ("done", "failed"):
                    c.execute("UPDATE tasks SET state='queued', gen=gen+1, prio=?, tries=0, lease_key=NULL, lease_until=0, not_before=0, "
                              "verified=0, conflict=0, vkey=NULL, vuntil=0 WHERE id=?", (prio, t[0]))
                    n += 1
                elif prio < t[2]:
                    c.execute("UPDATE tasks SET prio=? WHERE id=?", (prio, t[0]))
        return n

    def has(self, url, newer_than=None):
        r = self.conn().execute("SELECT accepted_at FROM pages WHERE url=?", (url,)).fetchone()
        return bool(r) and (newer_than is None or r[0] >= newer_than)

    def get(self, url, newer_than=None):
        """-> (статус, байты, ctype) принятой страницы, ('failed', ...) для безнадёжного задания либо None (ждать)."""
        c = self.conn()
        r = c.execute("SELECT status, body, ctype, accepted_at FROM pages WHERE url=?", (url,)).fetchone()
        if r and (newer_than is None or r[3] >= newer_than):
            raw = zlib.decompress(r[1], 16 + zlib.MAX_WBITS) if r[1] else b""
            return r[0], raw, r[2] or ""
        t = c.execute("SELECT state FROM tasks WHERE url=?", (url,)).fetchone()
        if t and t[0] == "failed":
            return "failed", b"", ""
        return None

    def pop_events(self):
        """Адреса, содержимое которых изменилось после того, как сборщик мог их забрать (страница заменена большинством, принятая отозвана)."""
        with self._tx() as c:
            rows = c.execute("SELECT id, url, kind FROM events ORDER BY id").fetchall()
            if rows:
                c.execute("DELETE FROM events WHERE id<=?", (rows[-1][0],))
        return [(u, k) for _i, u, k in rows]

    def purge(self, now=None):
        now = now or self.clock()
        lim = now - KEEP_DAYS * 86400
        with self._tx() as c:
            c.execute("DELETE FROM pages WHERE accepted_at<?", (lim,))
            c.execute("DELETE FROM subs WHERE ts<?", (lim,))
            c.execute("DELETE FROM tasks WHERE state IN ('done','failed') AND created<? AND url NOT IN (SELECT url FROM pages)", (lim,))
            c.execute("DELETE FROM events WHERE ts<?", (lim,))

    # ───────────── сторона сервера ─────────────
    def _key(self, c, key_id, now):
        c.execute("INSERT OR IGNORE INTO keys(key_id, first_seen, last_seen) VALUES(?,?,?)", (key_id, now, now))
        return c.execute("SELECT distrusted, last_submit, day, day_n FROM keys WHERE key_id=?", (key_id,)).fetchone()

    def lease(self, key_id, n=2, now=None):
        """Выдать до n заданий ключу. Уже арендованные им и ещё не истёкшие выдаются первыми (повтор запроса идемпотентен)."""
        now = now or self.clock()
        n = max(1, min(int(n), MAX_TASKS_PER_CALL))
        out = []
        with self._tx() as c:
            dis = self._key(c, key_id, now)[0]
            c.execute("UPDATE keys SET last_seen=? WHERE key_id=?", (now, key_id))
            if dis:
                return []
            mine = c.execute("SELECT id, url FROM tasks WHERE state='leased' AND lease_key=? AND lease_until>? ORDER BY prio, id LIMIT ?",
                             (key_id, now, n)).fetchall()
            out += mine
            if len(out) < n:
                rows = c.execute("SELECT id, url FROM tasks WHERE (state='queued' OR (state='leased' AND lease_until<=?)) AND not_before<=? "
                                 "ORDER BY prio, id LIMIT ?", (now, now, n - len(out))).fetchall()
                for tid, url in rows:
                    c.execute("UPDATE tasks SET state='leased', lease_key=?, lease_until=? WHERE id=?", (key_id, now + LEASE_SEC, tid))
                out += rows
            if len(out) < n and (not out or self.rng.random() < VERIFY_P):
                v = self._verify_pick(c, key_id, now)
                if v:
                    c.execute("UPDATE tasks SET vkey=?, vuntil=? WHERE id=?", (key_id, now + LEASE_SEC, v[0]))
                    out.append(v)
        return [{"id": i, "url": u} for i, u in out]

    def _verify_pick(self, c, key_id, now):
        """Уже принятая страница, которую стоит перепроверить другим ключом: сначала спорные, потом неповеренные сообщения (не старше суток)."""
        q = ("SELECT t.id, t.url FROM tasks t JOIN pages p ON p.url=t.url AND p.gen=t.gen WHERE t.state='done' AND t.verified=0 AND p.status=200 "
             "AND p.key_id!=? AND t.vuntil<=? AND p.accepted_at>? AND (t.conflict=1 OR t.kind='msg') "
             "AND NOT EXISTS (SELECT 1 FROM subs s WHERE s.url=t.url AND s.key_id=? AND s.gen=t.gen) ORDER BY t.conflict DESC, t.id LIMIT 1")
        return c.execute(q, (key_id, now, now - 86400, key_id)).fetchone()

    def _release(self, c, tid, delay, tries_inc=1):
        c.execute("UPDATE tasks SET state=CASE WHEN tries+?>=? THEN 'failed' ELSE 'queued' END, tries=tries+?, lease_key=NULL, lease_until=0, not_before=? "
                  "WHERE id=?", (tries_inc, MAX_TRIES, tries_inc, self.clock() + delay, tid))

    def submit(self, key_id, task_id, url, status, body_b64, ctype="", now=None):
        """Принять страницу от ключа. -> {'accepted': bool, ...}; бросает CrowdError (код HTTP, причина).
        Отказ тоже фиксируется в базе (счётчики ключа, возврат задания в очередь), поэтому исключение бросается уже после коммита."""
        res = self._submit(key_id, task_id, url, status, body_b64, ctype, now or self.clock())
        if isinstance(res, CrowdError):
            raise res
        return res

    def _submit(self, key_id, task_id, url, status, body_b64, ctype, now):
        if not isinstance(status, int) or isinstance(status, bool):
            return CrowdError(400, "bad status")
        with self._tx() as c:
            dis, last, day, day_n = self._key(c, key_id, now)
            if dis:                                             # недоверенный ключ: ответ как у обычного, но ничего не сохраняется
                return {"accepted": False, "ignored": True}
            if now - last < MIN_SUBMIT_GAP:
                return CrowdError(429, "too fast", retry_after=int(MIN_SUBMIT_GAP - (now - last)) + 1)
            today = datetime.fromtimestamp(now, MSK).strftime("%Y-%m-%d")
            day_n = (day_n + 1) if day == today else 1
            if day_n > DAY_CAP:
                return CrowdError(429, "daily cap", retry_after=3600)
            c.execute("UPDATE keys SET submits=submits+1, last_submit=?, day=?, day_n=?, last_seen=? WHERE key_id=?", (now, today, day_n, now, key_id))
            t = c.execute("SELECT id, url, state, gen, lease_key, tries, verified, vkey FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not t or t[1] != url:
                c.execute("UPDATE keys SET rejected=rejected+1 WHERE key_id=?", (key_id,))
                return CrowdError(400, "unknown task")
            tid, _u, state, gen, lkey, tries, verified, vkey = t
            if status in (404, 410):
                return self._gone(c, key_id, t, now)
            if status != 200:
                if state == "leased" and lkey == key_id:
                    self._release(c, tid, RETRY_5XX)
                return {"accepted": False, "retry": True}
            try:
                raw = gunzip_limited(body_b64)
            except ValueError as e:
                c.execute("UPDATE keys SET rejected=rejected+1 WHERE key_id=?", (key_id,))
                return CrowdError(413 if str(e) == "too large" else 400, str(e))
            text = decode_text(raw, ctype)
            bad = check_page(url, text)
            if bad:
                c.execute("UPDATE keys SET rejected=rejected+1 WHERE key_id=?", (key_id,))
                if state == "leased" and lkey == key_id:
                    self._release(c, tid, 60)
                return CrowdError(422, bad)
            sha = body_sha(text)
            gz = gzip.compress(raw, 6, mtime=0)
            pg = c.execute("SELECT gen, sha, key_id, ver FROM pages WHERE url=?", (url,)).fetchone()
            if pg is None or pg[0] < gen:                      # первое принятие этого поколения (в том числе обновление живой ленты)
                c.execute("INSERT OR REPLACE INTO pages(url, gen, status, sha, body, ctype, accepted_at, key_id, ver, changed) VALUES(?,?,?,?,?,?,?,?,?,0)",
                          (url, gen, 200, sha, gz, ctype, now, key_id, (pg[3] + 1) if pg else 1))
                c.execute("INSERT OR REPLACE INTO subs(url, key_id, gen, status, sha, body, ts) VALUES(?,?,?,?,?,NULL,?)", (url, key_id, gen, 200, sha, now))
                c.execute("UPDATE tasks SET state='done', lease_key=NULL, lease_until=0, tries=0, verified=0, conflict=0 WHERE id=?", (tid,))
                c.execute("UPDATE keys SET accepted=accepted+1 WHERE key_id=?", (key_id,))
                return {"accepted": True}
            # страница этого поколения уже есть: это перепроверка (или позднее второе скачивание после истёкшей аренды)
            same = pg[1] == sha
            c.execute("INSERT OR REPLACE INTO subs(url, key_id, gen, status, sha, body, ts) VALUES(?,?,?,?,?,?,?)",
                      (url, key_id, gen, 200, sha, None if same else gz, now))
            c.execute("UPDATE tasks SET verified=1, vuntil=0 WHERE id=?", (tid,))
            if state == "leased" and lkey == key_id:
                c.execute("UPDATE tasks SET state='done', lease_key=NULL, lease_until=0 WHERE id=?", (tid,))
            if same:
                if pg[2] != key_id:
                    c.execute("UPDATE keys SET accepted=accepted+1 WHERE key_id=?", (key_id,))
                return {"accepted": True, "verified": True}
            log.warning("расхождение по %s: принято %s (ключ %s), прислано %s", url, pg[1][:10], pg[2], sha[:10])
            self._resolve(c, url, gen, now)
            return {"accepted": True, "conflict": True}

    def _gone(self, c, key_id, t, now):
        tid, url, state, gen, lkey, tries, _v, _vk = t
        c.execute("INSERT OR REPLACE INTO subs(url, key_id, gen, status, sha, body, ts) VALUES(?,?,?,?,?,NULL,?)", (url, key_id, gen, 404, "404", now))
        votes = c.execute("SELECT COUNT(*) FROM subs s JOIN keys k ON k.key_id=s.key_id WHERE s.url=? AND s.gen=? AND s.status=404 AND k.distrusted=0",
                          (url, gen)).fetchone()[0]
        if votes >= GONE_VOTES or (votes >= 1 and tries >= 2):
            c.execute("INSERT OR REPLACE INTO pages(url, gen, status, sha, body, ctype, accepted_at, key_id, ver, changed) VALUES(?,?,?,?,NULL,'',?,?,1,0)",
                      (url, gen, 404, "404", now, key_id))
            c.execute("UPDATE tasks SET state='done', lease_key=NULL, lease_until=0 WHERE id=?", (tid,))
            return {"accepted": True, "gone": True}
        if state == "leased" and lkey == key_id:
            self._release(c, tid, GONE_RETRY)
        return {"accepted": False, "retry": True}

    def _resolve(self, c, url, gen, now):
        """Большинство разных доверенных ключей по sha для этого поколения. Равенство — оставляем принятое и просим третье мнение."""
        pg = c.execute("SELECT sha, key_id, ver FROM pages WHERE url=?", (url,)).fetchone()
        rows = c.execute("SELECT s.sha, s.body, s.key_id FROM subs s JOIN keys k ON k.key_id=s.key_id WHERE s.url=? AND s.gen=? AND s.status=200 AND k.distrusted=0",
                         (url, gen)).fetchall()
        votes = {}
        for sha, _b, _k in rows:
            votes[sha] = votes.get(sha, 0) + 1
        if not votes:
            return
        top = max(votes.values())
        winners = [s for s, v in votes.items() if v == top]
        if pg[0] in winners:
            c.execute("UPDATE tasks SET conflict=?, verified=0 WHERE url=?", (1 if len(votes) > 1 and len(winners) > 1 else 0, url))
            return
        win = winners[0]
        body = next((b for s, b, _k in rows if s == win and b), None)
        if body is None:
            return
        c.execute("UPDATE pages SET sha=?, body=?, key_id=?, ver=ver+1, changed=1, accepted_at=? WHERE url=?",
                  (win, body, next(k for s, _b, k in rows if s == win), now, url))
        c.execute("INSERT INTO events(url, kind, ts) VALUES(?,?,?)", (url, "replaced", now))
        c.execute("UPDATE tasks SET conflict=0 WHERE url=?", (url,))
        log.warning("страница %s заменена версией большинства (%d из %d)", url, top, len(rows))

    # ───────────── недоверие ─────────────
    def distrust(self, key_id, on=True, now=None):
        """Игнорировать ключ. Принятые им страницы возвращаются в очередь, а сборщик получает события на переразбор. -> число возвращённых страниц."""
        now = now or self.clock()
        n = 0
        with self._tx() as c:
            self._key(c, key_id, now)
            c.execute("UPDATE keys SET distrusted=? WHERE key_id=?", (1 if on else 0, key_id))
            if not on:
                return 0
            for url, kind, gen in c.execute("SELECT p.url, t.kind, p.gen FROM pages p JOIN tasks t ON t.url=p.url WHERE p.key_id=?", (key_id,)).fetchall():
                subs = c.execute("SELECT s.sha, s.body FROM subs s JOIN keys k ON k.key_id=s.key_id WHERE s.url=? AND s.gen=? AND s.status=200 "
                                 "AND k.distrusted=0 AND s.key_id!=?", (url, gen, key_id)).fetchall()
                alt = next(((s, b) for s, b in subs if b), None)
                if alt:                                          # другой доверенный ключ присылал иное содержимое: берём его
                    c.execute("UPDATE pages SET sha=?, body=?, key_id=(SELECT key_id FROM subs WHERE url=? AND gen=? AND sha=? LIMIT 1), ver=ver+1, changed=1 WHERE url=?",
                              (alt[0], alt[1], url, gen, alt[0], url))
                    c.execute("INSERT INTO events(url, kind, ts) VALUES(?,?,?)", (url, "replaced", now))
                else:
                    c.execute("DELETE FROM pages WHERE url=?", (url,))
                    c.execute("UPDATE tasks SET state='queued', gen=gen+1, tries=0, lease_key=NULL, lease_until=0, not_before=0, verified=0, conflict=0 WHERE url=?", (url,))
                    c.execute("INSERT INTO events(url, kind, ts) VALUES(?,?,?)", (url, "revoked", now))
                n += 1
            c.execute("DELETE FROM subs WHERE key_id=? AND status=200", (key_id,))
        return n

    # ───────────── статус ─────────────
    def status(self, now=None):
        """Агрегаты без идентификаторов ключей."""
        now = now or self.clock()
        c = self.conn()
        q = lambda s, *a: c.execute(s, a).fetchone()[0]  # noqa: E731
        d0 = datetime.fromtimestamp(now, MSK).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return {"queue": q("SELECT COUNT(*) FROM tasks WHERE state='queued' OR (state='leased' AND lease_until<=?)", now),
                "leased": q("SELECT COUNT(*) FROM tasks WHERE state='leased' AND lease_until>?", now),
                "failed": q("SELECT COUNT(*) FROM tasks WHERE state='failed'"),
                "accepted_today": q("SELECT COUNT(*) FROM pages WHERE accepted_at>=?", d0),
                "contributors_24h": q("SELECT COUNT(*) FROM keys WHERE distrusted=0 AND last_submit>?", now - 86400),
                "oldest_queued_age": int(now - (c.execute("SELECT MIN(created) FROM tasks WHERE state='queued'").fetchone()[0] or now))}


class _Tx:
    def __init__(self, conn):
        self.c = conn

    def __enter__(self):
        self.c.execute("BEGIN IMMEDIATE")
        return self.c

    def __exit__(self, et, ev, tb):
        self.c.execute("COMMIT" if et is None else "ROLLBACK")
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Краудсорсинг раскрытий: управление ключами и статус")
    ap.add_argument("--data", required=True)
    ap.add_argument("cmd", choices=["status", "distrust", "trust", "keys"])
    ap.add_argument("key_id", nargs="?", help="идентификатор из `keys` (например tg:123456)")
    a = ap.parse_args(argv)
    st = CrowdStore(os.path.join(a.data, "crowd.sqlite"))
    if a.cmd == "status":
        print(json.dumps(st.status(), ensure_ascii=False, indent=2))
    elif a.cmd == "keys":
        for r in st.conn().execute("SELECT key_id, submits, accepted, rejected, distrusted FROM keys ORDER BY submits DESC"):
            print("%s\tотправок %d\tпринято %d\tотклонено %d%s" % (r[0], r[1], r[2], r[3], "\tНЕДОВЕРЕННЫЙ" if r[4] else ""))
    elif not a.key_id:
        ap.error("нужен идентификатор ключа")
    elif a.cmd == "distrust":
        print("возвращено в очередь страниц: %d" % st.distrust(a.key_id, True))
    else:
        st.distrust(a.key_id, False)
        print("ключ снова доверенный")
    return 0


if __name__ == "__main__":
    sys.exit(main())
