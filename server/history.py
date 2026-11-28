# -*- coding: utf-8 -*-
"""Архив дневных цен Мосбиржи на сервере: история бумаги собирается один раз и дальше только дописывается.

Мосбиржа (ISS) отдаёт историю страницами по 100 строк: история фонда с 2019 года — около 20 запросов. Раньше их делало каждое
приложение; теперь сервер хранит ряд в <data>/history.sqlite и отдаёт его одним ответом /v1/history.

    GET /v1/history?market=index|shares|bonds&secid=RGBITR&from=YYYY-MM-DD[&till=YYYY-MM-DD]
    -> {"ok": true, "market", "secid", "from", "till", "rows": [[дата, close, value, yield], ...]}

from/till в ответе — окно, которое архив покрывает без пропусков: за всё это окно данные запрошены у ISS целиком. Если догрузить
не удалось, ответ 502 — приложение берёт историю у источника само (как раньше). Для акций, фондов и облигаций на дату
берётся строка с наибольшим оборотом (VALUE) среди режимов торгов — так же, как раньше считало приложение.

Хвост ряда дописывается не чаще TAIL_TTL; ряды, к которым обращались за последние KEEP_DAYS дней, освежает refresh_all()
(поток warm сервера), остальные удаляются.
"""
import os
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

MARKETS = {
    "index": "TRADEDATE,CLOSE",
    "shares": "BOARDID,TRADEDATE,CLOSE,VALUE",
    "bonds": "BOARDID,TRADEDATE,CLOSE,VALUE,YIELDCLOSE",
}
SECID_RX = re.compile(r"^[A-Za-z0-9._-]{1,24}$")
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MIN_FROM = "2010-01-01"
TAIL_TTL = 6 * 3600
TAIL_BACK_DAYS = 5               # хвост перекачивается с запасом: ISS может поправить последние дни
KEEP_DAYS = 45
MAX_PAGES = 200
ISS = ("https://iss.moex.com/iss/history/engines/stock/markets/%s/securities/%s.json?iss.meta=off"
       "&iss.only=history,history.cursor&history.columns=%s&from=%s%s&start=%d")

SCHEMA = """
CREATE TABLE IF NOT EXISTS hist(market TEXT NOT NULL, secid TEXT NOT NULL, d TEXT NOT NULL, close REAL, value REAL, yld REAL,
                                PRIMARY KEY(market, secid, d));
CREATE TABLE IF NOT EXISTS hmeta(market TEXT NOT NULL, secid TEXT NOT NULL, cov_from TEXT NOT NULL, cov_till TEXT NOT NULL,
                                 updated REAL NOT NULL, accessed REAL NOT NULL, PRIMARY KEY(market, secid));
"""


class HistoryError(Exception):
    pass


def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


class HistoryStore:
    def __init__(self, path, fetch_json, clock=time.time, today=None):
        """fetch_json(url) -> dict | None (через кэш и лимиты сервера). today() -> date (для тестов)."""
        self.path, self.fetch_json, self.clock = path, fetch_json, clock
        self.today = today or date.today
        self._local = threading.local()
        self._locks, self._locks_lock = {}, threading.Lock()
        self._conn().executescript(SCHEMA)

    def _conn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=10000")
            self._local.c = c
        return c

    def _lock(self, k):
        with self._locks_lock:
            return self._locks.setdefault(k, threading.Lock())

    def _download(self, market, secid, frm, till):
        """ISS -> {дата: (close, value, yld)} за [frm, till]. Бросает HistoryError, если страница не пришла."""
        cols = MARKETS[market]
        boards = cols.startswith("BOARDID")
        out, start = {}, 0
        for _ in range(MAX_PAGES):
            j = self.fetch_json(ISS % (market, secid, cols, frm, "&till=" + till if till else "", start))
            if not isinstance(j, dict) or "history" not in j:
                raise HistoryError("ISS не ответил")
            rows = (j.get("history") or {}).get("data") or []
            for r in rows:
                if boards:
                    _b, d, c, v = r[0], r[1], r[2], r[3]
                    y = r[4] if len(r) > 4 else None
                else:
                    d, c, v, y = r[0], r[1], None, None
                if c is None:
                    continue
                old = out.get(d)
                if old is None or (v or 0) >= (old[1] or 0):
                    out[d] = (float(c), float(v) if v is not None else None, float(y) if y is not None else None)
            cur = ((j.get("history.cursor") or {}).get("data") or [[0, 0, 100]])[0]
            start = cur[0] + len(rows)
            if not rows or start >= cur[1]:
                return out
        raise HistoryError("слишком длинная история")

    def _store(self, market, secid, rows):
        c = self._conn()
        c.execute("BEGIN")
        try:
            c.executemany("INSERT OR REPLACE INTO hist(market, secid, d, close, value, yld) VALUES(?,?,?,?,?,?)",
                          [(market, secid, d, v[0], v[1], v[2]) for d, v in rows.items()])
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

    def ensure(self, market, secid, frm, force_tail=False):
        """Догружает недостающее начало и (не чаще TAIL_TTL) хвост. -> (cov_from, cov_till)."""
        now, today = self.clock(), self.today().isoformat()
        with self._lock((market, secid)):
            c = self._conn()
            m = c.execute("SELECT cov_from, cov_till, updated FROM hmeta WHERE market=? AND secid=?", (market, secid)).fetchone()
            if not m:
                self._store(market, secid, self._download(market, secid, frm, None))
                c.execute("INSERT OR REPLACE INTO hmeta(market, secid, cov_from, cov_till, updated, accessed) VALUES(?,?,?,?,?,?)",
                          (market, secid, frm, today, now, now))
                return frm, today
            cov_from, cov_till, updated = m
            if frm < cov_from:
                till = (_d(cov_from) + timedelta(days=7)).isoformat()
                self._store(market, secid, self._download(market, secid, frm, till))
                cov_from = frm
            if force_tail or now - updated > TAIL_TTL or cov_till < today and now - updated > 600:
                since = (_d(cov_till) - timedelta(days=TAIL_BACK_DAYS)).isoformat()
                self._store(market, secid, self._download(market, secid, since, None))
                cov_till, updated = today, now
            c.execute("UPDATE hmeta SET cov_from=?, cov_till=?, updated=?, accessed=? WHERE market=? AND secid=?",
                      (cov_from, cov_till, updated, now, market, secid))
            return cov_from, cov_till

    def query(self, market, secid, frm, till=None):
        if market not in MARKETS or not SECID_RX.match(secid or "") or not DATE_RX.match(frm or "") \
                or (till and not DATE_RX.match(till)):
            raise ValueError("bad params")
        secid = secid.upper()
        frm = max(frm, MIN_FROM)
        cov_from, cov_till = self.ensure(market, secid, frm)
        hi = min(till, cov_till) if till else cov_till
        rows = self._conn().execute("SELECT d, close, value, yld FROM hist WHERE market=? AND secid=? AND d>=? AND d<=? ORDER BY d",
                                    (market, secid, frm, hi)).fetchall()
        return {"ok": True, "market": market, "secid": secid, "from": max(frm, cov_from), "till": hi,
                "cov_from": cov_from, "rows": [list(r) for r in rows]}

    def refresh_all(self):
        """Освежить хвосты рядов, которыми пользовались недавно; давно не нужные — удалить. -> (освежено, ошибок, удалено)."""
        now = self.clock()
        c = self._conn()
        old = c.execute("SELECT market, secid FROM hmeta WHERE accessed<?", (now - KEEP_DAYS * 86400,)).fetchall()
        for mk, sid in old:
            c.execute("DELETE FROM hist WHERE market=? AND secid=?", (mk, sid))
            c.execute("DELETE FROM hmeta WHERE market=? AND secid=?", (mk, sid))
        ok = bad = 0
        for mk, sid, frm in c.execute("SELECT market, secid, cov_from FROM hmeta WHERE updated<?", (now - TAIL_TTL,)).fetchall():
            try:
                self.ensure(mk, sid, frm, force_tail=True)
                ok += 1
            except (HistoryError, sqlite3.Error, ValueError):
                bad += 1
        return ok, bad, len(old)
