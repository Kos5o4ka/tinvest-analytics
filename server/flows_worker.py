#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборщик потоков денег («Кто покупает») для сервера данных TAnalytic. Отдельный долгоживущий процесс, только stdlib, Python 3.8+.

Универсум ликвидных бумаг: акции TQBR + ~150 самых оборотистых облигаций (TQCB/TQOB) + ~40 фондов (TQTF и ETF с TQBR) по обороту
дня из ISS, обновляется каждые 30 минут. Источники сделок:
  * T-Invest GetLastTrades по каждой бумаге (если на сервере есть токен владельца, см. tinvest_md.py): реальное время, направление
    сделки приходит из API; весь список обходится за ~2-5 минут в пределах лимитов;
  * ISS trades.json (весь рынок по курсору TRADENO, поле BUYSELL, задержка ~15 минут) — без токена и как заполнение пропусков.
Сырые сделки НЕ хранятся: только агрегаты по 5-минуткам, крупные сделки (30 дней) и всплески объёма.

База `<data>/flows.sqlite` (WAL):
  instruments(secid PK, isin, uid, cls 'share'|'bond'|'fund', board, sector, name, lot, face, turnover, active, cdl_day, updated)
  agg(secid, bucket, buy, sell, n, nl, ti, PK(secid, bucket))   — bucket = unix//300*300; ti — часть оборота из T-Invest
  large(tid PK, ts, secid, cls, side, price, qty, value, src)    — крупные сделки
  vhist(secid, day, bins JSON, PK(secid, day))                   — лог-гистограммы сумм сделок за 20 дней (скользящий 99-й перцентиль)
  slot(secid, day, slot, value, PK(secid, day, slot))            — 10-минутные обороты прошлых дней (свечи ISS)
  spikes(secid, day, slot, ts, value, median, ratio, PK(secid, day, slot))
  cur(secid, src, ts)  meta(k PK, v)

    python3 flows_worker.py --data DIR [--token-file PATH] [--md-rate 200] [--interval 20] [--once] [--stats] [--verbose]
"""
import argparse
import json
import logging
import math
import os
import re
import signal
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tinvest_md  # noqa: E402

UA = "TAnalytic-flows/1.0 (+https://github.com/Kos5o4ka/tinvest-analytics)"
ISS = "https://iss.moex.com/iss/"
MSK = timezone(timedelta(hours=3))
BUCKET = 300
N_MIN = {"share": 5e6, "bond": 10e6, "fund": 5e6}      # порог крупной сделки, ₽
MIN_SAMPLES = 200                                      # меньше наблюдений — перцентилю не доверяем
SPIKE_RATIO, SPIKE_MIN = 3.0, 1e6
HIST_DAYS, KEEP_AGG, KEEP_LARGE = 20, 45, 30
UNIVERSE = {"bond": 150, "fund": 40}
FUND_RX = re.compile(r"ETF|БПИФ|ПИФ|\bфонд", re.I)
log = logging.getLogger("flows")

# Секторы акций (ISS их не отдаёт): тикер -> сектор. Остальное — «Прочее».
SECTORS = {}
for _s, _t in (
        ("Банки и финансы", "SBER SBERP VTBR T TCSG TRMK BSPB CBOM MBNK SVCB MOEX RENI LEAS SFIN ZAYM DOMRF"),
        ("Нефть и газ", "GAZP LKOH ROSN NVTK SIBN TATN TATNP SNGS SNGSP TRNFP BANE BANEP RNFT TNFT"),
        ("Металлы и добыча", "GMKN NLMK CHMF MAGN PLZL ALRS RUAL MTLR MTLRP SELG UGLD POLY RASP"),
        ("Электроэнергетика", "IRAO HYDR FEES UPRO MSRS MRKC MRKP MRKU MRKV ENPG LSNG MSNG ELFV TGKA"),
        ("Телеком и IT", "MTSS RTKM RTKMP YDEX YNDX OZON VKCO HEAD POSI CIAN ASTR DIAS WUSH SOFL"),
        ("Ритейл и потребление", "MGNT FIVE LENT FESH APTK BELU AQUA HNFG SVAV GCHE MVID DELI"),
        ("Транспорт", "AFLT FLOT NMTP NKHP GLTR"),
        ("Химия и удобрения", "PHOR AKRN KZOS NKNC"),
        ("Строительство и девелопмент", "PIKK SMLT LSRG ETLN SPBE")):
    for _x in _t.split():
        SECTORS[_x] = _s


class Stopped(Exception):
    pass


def msk_day(ts):
    return datetime.fromtimestamp(ts, MSK).strftime("%Y-%m-%d")


def slot_of(ts):
    return ((int(ts) + 10800) % 86400) // 600


def day_start(ts):
    """Unix-время полуночи по Москве для дня, в который попадает ts."""
    return (int(ts) + 10800) // 86400 * 86400 - 10800


def vbin(v):
    return int(math.floor(math.log10(max(v, 1.0)) * 10))


# ───────────────────────── HTTP (ISS) ─────────────────────────
class IssFetcher:
    """Один поток, не чаще раза в pace секунд. get(url) -> текст JSON."""

    def __init__(self, pace=0.3, stop=None, retries=3, timeout=40):
        self.pace, self.stop, self.retries, self.timeout = pace, stop, retries, timeout
        self.last, self.count = 0.0, 0

    def __call__(self, url):
        err = None
        for a in range(self.retries):
            if self.stop is not None and self.stop.is_set():
                raise Stopped()
            gap = self.pace - (time.monotonic() - self.last)
            if gap > 0:
                time.sleep(gap)
            self.last = time.monotonic()
            self.count += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                err = e
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, OSError) as e:
                err = e
            time.sleep(2 * (a + 1))
        raise OSError("ISS: %s" % (err,))


def iss_rows(text, block):
    j = json.loads(text)
    b = j.get(block) or {}
    cols = [c.upper() for c in b.get("columns") or []]
    return [dict(zip(cols, r)) for r in b.get("data") or []]


# ───────────────────────── база ─────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments(secid TEXT PRIMARY KEY, isin TEXT, uid TEXT, cls TEXT, board TEXT, sector TEXT, name TEXT,
  lot INTEGER DEFAULT 1, face REAL DEFAULT 0, turnover REAL DEFAULT 0, active INTEGER DEFAULT 1, cdl_day TEXT, updated REAL);
CREATE INDEX IF NOT EXISTS ix_inst_isin ON instruments(isin);
CREATE TABLE IF NOT EXISTS agg(secid TEXT, bucket INTEGER, buy REAL DEFAULT 0, sell REAL DEFAULT 0, n INTEGER DEFAULT 0,
  nl INTEGER DEFAULT 0, ti REAL DEFAULT 0, PRIMARY KEY(secid, bucket));
CREATE INDEX IF NOT EXISTS ix_agg_b ON agg(bucket);
CREATE TABLE IF NOT EXISTS large(tid TEXT PRIMARY KEY, ts REAL, secid TEXT, cls TEXT, side TEXT, price REAL, qty REAL, value REAL, src TEXT);
CREATE INDEX IF NOT EXISTS ix_large_ts ON large(ts);
CREATE TABLE IF NOT EXISTS vhist(secid TEXT, day TEXT, bins TEXT, PRIMARY KEY(secid, day));
CREATE TABLE IF NOT EXISTS slot(secid TEXT, day TEXT, slot INTEGER, value REAL, PRIMARY KEY(secid, day, slot));
CREATE TABLE IF NOT EXISTS spikes(secid TEXT, day TEXT, slot INTEGER, ts REAL, value REAL, median REAL, ratio REAL,
  PRIMARY KEY(secid, day, slot));
CREATE INDEX IF NOT EXISTS ix_spk_ts ON spikes(ts);
CREATE TABLE IF NOT EXISTS cur(secid TEXT, src TEXT, ts REAL, PRIMARY KEY(secid, src));
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def open_db(path):
    db = sqlite3.connect(path, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    db.commit()
    return db


def meta_get(db, k, default=None):
    r = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def meta_set(db, k, v):
    db.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, str(v)))


# ───────────────────────── движок ─────────────────────────
class Engine:
    def __init__(self, db, iss_get, md=None, now=time.time, stop=None, md_poll_secs=90, candle_batch=40,
                 iss_pages=8, iss_backfill=20000, universe=None):
        self.db, self.iss_get, self.md, self.now = db, iss_get, md, now
        self.stop = stop or threading.Event()
        self.md_poll_secs, self.candle_batch, self.iss_pages, self.iss_backfill = md_poll_secs, candle_batch, iss_pages, iss_backfill
        self.universe = dict(UNIVERSE, **(universe or {}))
        self.inst = {}                    # secid -> dict (активные)
        self.hist = {}                    # secid -> {day: {bin: n}}
        self.hist_dirty = set()
        self.thr = {}                     # secid -> (adds, порог)
        self.adds = {}
        self.cur = {}
        self.sigs = {}                    # secid -> (ts, {подписи}) для сделок на границе курсора T-Invest
        self.touched = set()
        self.rr = 0
        self.md_off_until = 0
        self.counters = {"ti_calls": 0, "ti_errors": 0, "iss_pages": 0, "trades": 0, "large": 0, "spikes": 0}
        self.load_inst()

    # --- универсум ---
    def load_inst(self):
        self.inst = {}
        for r in self.db.execute("SELECT secid,isin,uid,cls,board,sector,name,lot,face,turnover FROM instruments WHERE active=1"):
            self.inst[r[0]] = dict(zip(("secid", "isin", "uid", "cls", "board", "sector", "name", "lot", "face", "turnover"), r))
        for secid, src, ts in self.db.execute("SELECT secid,src,ts FROM cur"):
            self.cur[(secid, src)] = ts

    def universe_refresh(self):
        """Обновляет список бумаг по ISS. Возвращает число бумаг."""
        found = {}

        def board(market, brd):
            url = ("%sengines/stock/markets/%s/boards/%s/securities.json?iss.meta=off&iss.only=securities,marketdata"
                   "&securities.columns=SECID,ISIN,SHORTNAME,LOTSIZE,FACEVALUE&marketdata.columns=SECID,VALTODAY" %
                   (ISS, market, brd))
            t = self.iss_get(url)
            sec, md = iss_rows(t, "securities"), {r["SECID"]: (r.get("VALTODAY") or 0) for r in iss_rows(t, "marketdata")}
            out = []
            for s in sec:
                out.append((s, float(md.get(s["SECID"]) or 0)))
            return out

        shares, funds, bonds = [], [], []
        for s, v in board("shares", "TQBR"):
            (funds if FUND_RX.search(s.get("SHORTNAME") or "") else shares).append((s, v, "TQBR"))
        for s, v in board("shares", "TQTF"):
            funds.append((s, v, "TQTF"))
        for brd in ("TQCB", "TQOB"):
            for s, v in board("bonds", brd):
                bonds.append((s, v, brd))
        total = sum(v for _s, v, _b in shares + funds + bonds)
        if total <= 0 and self.inst:
            return len(self.inst)                    # ночью оборот нулевой: оставляем прежний список
        top = lambda lst, n: sorted(lst, key=lambda x: -x[1])[:n]  # noqa: E731
        for cls, lst in (("share", shares), ("fund", top(funds, self.universe["fund"])), ("bond", top(bonds, self.universe["bond"]))):
            for s, v, brd in lst:
                if cls == "share" and v <= 0 and total > 0:
                    continue
                sector = SECTORS.get(s["SECID"], "Прочее") if cls == "share" else \
                    "Фонды" if cls == "fund" else ("ОФЗ" if brd == "TQOB" else "Корпоративные облигации")
                found[s["SECID"]] = (s.get("ISIN") or "", cls, brd, sector, s.get("SHORTNAME") or s["SECID"],
                                     int(s.get("LOTSIZE") or 1), float(s.get("FACEVALUE") or 0), v)
        t = self.now()
        self.db.execute("UPDATE instruments SET active=0")
        for secid, (isin, cls, brd, sector, name, lot, face, v) in found.items():
            if self.db.execute("UPDATE instruments SET isin=?,cls=?,board=?,sector=?,name=?,lot=?,face=?,turnover=?,active=1,updated=? "
                               "WHERE secid=?", (isin, cls, brd, sector, name, lot, face, v, t, secid)).rowcount == 0:
                self.db.execute("INSERT INTO instruments(secid,isin,cls,board,sector,name,lot,face,turnover,active,updated) "
                                "VALUES(?,?,?,?,?,?,?,?,?,1,?)", (secid, isin, cls, brd, sector, name, lot, face, v, t))
        meta_set(self.db, "universe_ts", t)
        self.db.commit()
        self.load_inst()
        return len(self.inst)

    def map_uids(self):
        """ISIN -> uid/лот/номинал из InstrumentsService (раз в сутки)."""
        if not (self.md and self.md.enabled):
            return 0
        by_isin = {}
        for kind in ("share", "bond", "etf"):
            for i in self.md.instruments(kind):
                if i.get("isin") and i.get("uid") and (i.get("classCode") or "").startswith("TQ"):
                    by_isin.setdefault(i["isin"], i)
        n = 0
        for secid, r in self.inst.items():
            i = by_isin.get(r["isin"])
            if not i:
                continue
            face = tinvest_md.quotation({"units": (i.get("nominal") or {}).get("units"), "nano": (i.get("nominal") or {}).get("nano")}) \
                if r["cls"] == "bond" else None
            lot = int(i.get("lot") or r["lot"] or 1)
            self.db.execute("UPDATE instruments SET uid=?, lot=?, face=COALESCE(?,face) WHERE secid=?", (i["uid"], lot, face or None, secid))
            n += 1
        meta_set(self.db, "uid_day", msk_day(self.now()))
        self.db.commit()
        self.load_inst()
        return n

    # --- перцентиль ---
    def _hist(self, secid):
        h = self.hist.get(secid)
        if h is None:
            h = {}
            for day, bins in self.db.execute("SELECT day,bins FROM vhist WHERE secid=?", (secid,)):
                try:
                    h[day] = {int(k): v for k, v in json.loads(bins).items()}
                except ValueError:
                    pass
            self.hist[secid] = h
        return h

    def p99(self, secid):
        """Скользящий 99-й перцентиль сумм сделок за 20 дней (верхняя граница лог-корзины) или None."""
        a = self.adds.get(secid, 0)
        m = self.thr.get(secid)
        if m and a - m[0] < 200:
            return m[1]
        h = self._hist(secid)
        lo = msk_day(self.now() - HIST_DAYS * 86400)
        tot, agg = 0, {}
        for day, bins in h.items():
            if day >= lo:
                for b, c in bins.items():
                    agg[b] = agg.get(b, 0) + c
                    tot += c
        val = None
        if tot >= MIN_SAMPLES:
            need, acc = tot * 0.99, 0
            for b in sorted(agg):
                acc += agg[b]
                if acc >= need:
                    val = 10 ** ((b + 1) / 10.0)
                    break
        self.thr[secid] = (a, val)
        return val

    def threshold(self, secid, cls):
        p = self.p99(secid)
        return max(N_MIN.get(cls, 5e6), p or 0)

    # --- приём сделок ---
    def ingest(self, batch):
        """batch: [(secid, ts, side, price, qty, value, src, tid)]; суммы уже в рублях. Возвращает число принятых."""
        n = 0
        agg = {}
        for secid, ts, side, price, qty, value, src, tid in batch:
            r = self.inst.get(secid)
            if not r or value <= 0 or side not in ("buy", "sell"):
                continue
            n += 1
            thr = self.threshold(secid, r["cls"])
            b = int(ts) // BUCKET * BUCKET
            a = agg.setdefault((secid, b), [0.0, 0.0, 0, 0, 0.0])
            a[0 if side == "buy" else 1] += value
            a[2] += 1
            if src == "tinvest":
                a[4] += value
            if value >= thr:
                a[3] += 1
                cur = self.db.execute("INSERT OR IGNORE INTO large(tid,ts,secid,cls,side,price,qty,value,src) VALUES(?,?,?,?,?,?,?,?,?)",
                                      (tid, ts, secid, r["cls"], side, price, qty, round(value, 2), src))
                self.counters["large"] += cur.rowcount
            hd = self._hist(secid).setdefault(msk_day(ts), {})
            k = vbin(value)
            hd[k] = hd.get(k, 0) + 1
            self.hist_dirty.add((secid, msk_day(ts)))
            self.adds[secid] = self.adds.get(secid, 0) + 1
            self.touched.add((secid, int(ts) // 600 * 600))
        for (secid, b), (buy, sell, cnt, nl, ti) in agg.items():
            if self.db.execute("UPDATE agg SET buy=buy+?,sell=sell+?,n=n+?,nl=nl+?,ti=ti+? WHERE secid=? AND bucket=?",
                               (buy, sell, cnt, nl, ti, secid, b)).rowcount == 0:
                self.db.execute("INSERT INTO agg(secid,bucket,buy,sell,n,nl,ti) VALUES(?,?,?,?,?,?,?)", (secid, b, buy, sell, cnt, nl, ti))
        for secid, day in self.hist_dirty:
            self.db.execute("INSERT OR REPLACE INTO vhist(secid,day,bins) VALUES(?,?,?)",
                            (secid, day, json.dumps({str(k): v for k, v in self._hist(secid)[day].items()})))
        self.hist_dirty.clear()
        self.counters["trades"] += n
        return n

    def set_cur(self, secid, src, ts):
        self.cur[(secid, src)] = ts
        self.db.execute("INSERT OR REPLACE INTO cur(secid,src,ts) VALUES(?,?,?)", (secid, src, ts))

    # --- T-Invest ---
    def poll_tinvest(self, secs=None):
        """Опрашивает GetLastTrades по кругу, пока не истекло secs секунд или не упёрлись в лимит. Возвращает число запросов."""
        if not (self.md and self.md.enabled) or self.now() < self.md_off_until:
            return 0
        lst = sorted((r for r in self.inst.values() if r.get("uid")), key=lambda r: -(r["turnover"] or 0))
        if not lst:
            return 0
        end = time.monotonic() + (self.md_poll_secs if secs is None else secs)
        calls = 0
        auth_fail = 0
        for _ in range(len(lst)):
            if self.stop.is_set() or time.monotonic() > end:
                break
            r = lst[self.rr % len(lst)]
            self.rr += 1
            now = self.now()
            c = self.cur.get((r["secid"], "tinvest"), 0)
            frm = max(c, now - 3600) if c else now - 1800
            try:
                trades = self.md.last_trades(r["uid"], _rfc(frm), _rfc(now))
            except tinvest_md.RateLimited:
                break
            except tinvest_md.MDError as e:
                self.counters["ti_errors"] += 1
                log.warning("T-Invest %s: %s", r["secid"], e)
                if re.search(r"HTTP (401|403)", str(e)):
                    auth_fail += 1
                    if auth_fail >= 3:
                        self.md_off_until = now + 600
                        log.error("T-Invest отклоняет токен, пауза 10 минут")
                        break
                continue
            calls += 1
            self.counters["ti_calls"] += 1
            self.ingest_ti(r, trades)
        self.db.commit()
        return calls

    def ingest_ti(self, r, trades):
        secid = r["secid"]
        cur_ts = self.cur.get((secid, "tinvest"), 0)
        _t, sigs = self.sigs.get(secid, (0, set()))
        lot = r["lot"] or 1
        k = (r["face"] or 1000.0) / 100.0 if r["cls"] == "bond" else 1.0       # цена облигации — % номинала
        batch, take = [], []
        for t in trades:
            sg = (t["price"], t["qty"], t["side"])
            if t["ts"] < cur_ts or (t["ts"] == cur_ts and sg in sigs):
                continue
            pieces = t["qty"] * lot
            tid = "ti:%s:%d:%s:%s:%s" % (secid, int(t["ts"] * 1000), t["price"], t["qty"], t["side"])
            batch.append((secid, t["ts"], t["side"], t["price"], pieces, t["price"] * pieces * k, "tinvest", tid))
            take.append(t)
        if not batch:
            return
        last = max(t["ts"] for t in take)
        new = set((t["price"], t["qty"], t["side"]) for t in take if t["ts"] == last)
        if last == cur_ts:
            new |= sigs
        self.sigs[secid] = (last, new)
        self.set_cur(secid, "tinvest", last)
        self.ingest(batch)

    # --- ISS: общий поток сделок ---
    def iss_trades(self, market, pages=None):
        key = "iss_cur_" + market
        today = msk_day(self.now())
        try:
            c = json.loads(meta_get(self.db, key) or "{}")
        except ValueError:
            c = {}
        base = "%sengines/stock/markets/%s/trades.json?iss.meta=off&iss.only=trades&trades.columns=TRADENO,BOARDID,SECID,TRADETIME,PRICE,QUANTITY,VALUE,BUYSELL,SYSTIME" % (ISS, market)
        if c.get("day") != today:
            rows = iss_rows(self.iss_get(base + "&reversed=1&limit=1"), "trades")
            if not rows:
                return 0
            c = {"day": today, "no": max(0, int(rows[0]["TRADENO"]) - self.iss_backfill)}
        n = 0
        for _ in range(pages or self.iss_pages):
            if self.stop.is_set():
                break
            rows = iss_rows(self.iss_get("%s&tradeno=%d&next_trade=1&limit=5000" % (base, c["no"])), "trades")
            self.counters["iss_pages"] += 1
            if not rows:
                break
            batch = []
            for r in rows:
                secid = r["SECID"]
                inst = self.inst.get(secid)
                no = int(r["TRADENO"])
                if no > c["no"]:
                    c["no"] = no
                if not inst or r.get("BOARDID") != inst["board"] or r.get("BUYSELL") not in ("B", "S"):
                    continue
                ts = _iss_ts(r.get("SYSTIME"), r.get("TRADETIME"), today)
                if ts is None or ts <= self.cur.get((secid, "tinvest"), 0):
                    continue                      # T-Invest уже видел это время: не считаем дважды
                batch.append((secid, ts, "buy" if r["BUYSELL"] == "B" else "sell", float(r["PRICE"] or 0), float(r["QUANTITY"] or 0),
                              float(r["VALUE"] or 0), "iss", "iss:%d" % no))
            n += self.ingest(batch)
            meta_set(self.db, key, json.dumps(c))
            self.db.commit()
            if len(rows) < 5000:
                break
        return n

    # --- свечи и всплески ---
    def candles_sync(self, limit=None):
        """Подтягивает 10-минутные обороты прошлых дней (раз в сутки на бумагу). Возвращает число обработанных бумаг."""
        today = msk_day(self.now())
        yest = msk_day(self.now() - 86400)
        todo = sorted((r for r in self.inst.values()), key=lambda r: -(r["turnover"] or 0))
        done = 0
        for r in todo:
            if done >= (limit or self.candle_batch) or self.stop.is_set():
                break
            row = self.db.execute("SELECT cdl_day FROM instruments WHERE secid=?", (r["secid"],)).fetchone()
            if row and row[0] == today:
                continue
            last = self.db.execute("SELECT MAX(day) FROM slot WHERE secid=?", (r["secid"],)).fetchone()[0]
            frm = (datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d") if last else \
                msk_day(self.now() - 28 * 86400)
            if frm <= yest:
                market = "bonds" if r["cls"] == "bond" else "shares"
                start = 0
                while True:
                    url = ("%sengines/stock/markets/%s/boards/%s/securities/%s/candles.json?interval=10&from=%s&till=%s&start=%d&iss.meta=off"
                           % (ISS, market, r["board"], quote(r["secid"]), frm, yest, start))
                    try:
                        rows = iss_rows(self.iss_get(url), "candles")
                    except (OSError, ValueError) as e:
                        log.warning("свечи %s: %s", r["secid"], e)
                        rows = None
                        break
                    for c in rows:
                        b = str(c.get("BEGIN") or "")
                        if len(b) >= 16:
                            sl = (int(b[11:13]) * 60 + int(b[14:16])) // 10
                            self.db.execute("INSERT OR REPLACE INTO slot(secid,day,slot,value) VALUES(?,?,?,?)",
                                            (r["secid"], b[:10], sl, float(c.get("VALUE") or 0)))
                    if len(rows) < 500:
                        break
                    start += len(rows)
                if rows is None:
                    continue
            self.db.execute("UPDATE instruments SET cdl_day=? WHERE secid=?", (today, r["secid"]))
            self.db.commit()
            done += 1
        return done

    def spikes_check(self):
        """Для затронутых 10-минуток сравнивает оборот с медианой того же слота за 20 торговых дней."""
        n = 0
        touched, self.touched = self.touched, set()
        today = msk_day(self.now())
        lo = msk_day(self.now() - 30 * 86400)
        for secid, st in touched:
            cur = self.db.execute("SELECT COALESCE(SUM(buy+sell),0) FROM agg WHERE secid=? AND bucket>=? AND bucket<?",
                                  (secid, st, st + 600)).fetchone()[0]
            if cur < SPIKE_MIN:
                continue
            day, sl = msk_day(st), slot_of(st)
            vals = sorted(v for (v,) in self.db.execute(
                "SELECT value FROM slot WHERE secid=? AND slot=? AND day>=? AND day<? ORDER BY day DESC LIMIT ?",
                (secid, sl, lo, day, HIST_DAYS)))
            if len(vals) < 5:
                continue
            med = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2.0
            ratio = cur / max(med, 1.0)
            if ratio >= SPIKE_RATIO:
                self.db.execute("INSERT OR REPLACE INTO spikes(secid,day,slot,ts,value,median,ratio) VALUES(?,?,?,?,?,?,?)",
                                (secid, day, sl, st, round(cur, 2), round(med, 2), round(ratio, 2)))
                n += 1
        self.counters["spikes"] += n
        self.db.commit()
        return n

    def retention(self):
        t = self.now()
        self.db.execute("DELETE FROM agg WHERE bucket<?", (t - KEEP_AGG * 86400,))
        self.db.execute("DELETE FROM large WHERE ts<?", (t - KEEP_LARGE * 86400,))
        self.db.execute("DELETE FROM spikes WHERE ts<?", (t - KEEP_LARGE * 86400,))
        self.db.execute("DELETE FROM vhist WHERE day<?", (msk_day(t - (HIST_DAYS + 5) * 86400),))
        self.db.execute("DELETE FROM slot WHERE day<?", (msk_day(t - 40 * 86400),))
        meta_set(self.db, "retention_day", msk_day(t))
        self.db.commit()
        self.hist.clear()

    # --- один цикл ---
    def cycle(self):
        t = self.now()
        try:
            if t - float(meta_get(self.db, "universe_ts", 0) or 0) > 1800 or not self.inst:
                self.universe_refresh()
        except (OSError, ValueError) as e:
            log.warning("универсум: %s", e)
        try:
            if self.md and self.md.enabled and meta_get(self.db, "uid_day") != msk_day(t):
                self.map_uids()
        except tinvest_md.MDError as e:
            log.warning("справочник T-Invest: %s", e)
        steps = [("T-Invest", self.poll_tinvest)] + [("ISS " + m, (lambda m=m: self.iss_trades(m))) for m in ("shares", "bonds")] + \
                [("свечи", self.candles_sync), ("всплески", self.spikes_check)]
        for name, fn in steps:
            if self.stop.is_set():
                break
            try:
                fn()
            except Stopped:
                break
            except (OSError, ValueError, KeyError, sqlite3.Error, tinvest_md.MDError) as e:
                log.warning("%s: %s", name, tinvest_md.scrub(e))
        if meta_get(self.db, "retention_day") != msk_day(t):
            self.retention()
        self.db.commit()


def _rfc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _iss_ts(systime, tradetime, today):
    try:
        day = (systime or "")[:10] if re.match(r"\d{4}-\d\d-\d\d", systime or "") else today
        d = datetime.strptime(day + " " + tradetime, "%Y-%m-%d %H:%M:%S").replace(tzinfo=MSK)
        return d.timestamp()
    except (TypeError, ValueError):
        return None


# ───────────────────────── чтение (используется сервером; соединение только для чтения) ─────────────────────────
def _asof(db):
    r = db.execute("SELECT MAX(bucket) FROM agg").fetchone()[0]
    return (r + BUCKET) if r else None


def _src(db, since, until):
    r = db.execute("SELECT COALESCE(SUM(ti),0), COALESCE(SUM(buy+sell),0) FROM agg WHERE bucket>=? AND bucket<?", (since, until)).fetchone()
    live = r[1] > 0 and r[0] / r[1] >= 0.5
    return ("tinvest" if live else "iss"), (0 if live else 15)


def period_window(asof, period):
    if period == "5m":
        return asof - 300
    if period == "1h":
        return asof - 3600
    return day_start(asof - 1)


def q_summary(db, period):
    asof = _asof(db)
    if asof is None:
        return {"period": period, "asof": None, "empty": True, "by_class": [], "by_sector": [], "top_buy": [], "top_sell": []}
    since = period_window(asof, period)
    src, delay = _src(db, since, asof)
    cond = "FROM agg a JOIN instruments i ON i.secid=a.secid WHERE a.bucket>=? AND a.bucket<?"
    rnd = lambda x: round(x or 0, 2)  # noqa: E731
    by_cls = [{"cls": c, "buy": rnd(b), "sell": rnd(s), "net": rnd(b - s), "n": n}
              for c, b, s, n in db.execute("SELECT i.cls, SUM(a.buy), SUM(a.sell), SUM(a.n) " + cond + " GROUP BY i.cls", (since, asof))]
    by_sec = [{"sector": c, "buy": rnd(b), "sell": rnd(s), "net": rnd(b - s)}
              for c, b, s in db.execute("SELECT i.sector, SUM(a.buy), SUM(a.sell) " + cond + " GROUP BY i.sector", (since, asof))]
    by_sec.sort(key=lambda x: -(x["buy"] + x["sell"]))
    inst = [{"secid": s, "name": nm, "cls": c, "isin": isn, "buy": rnd(b), "sell": rnd(se), "net": rnd(b - se)}
            for s, nm, c, isn, b, se in db.execute(
                "SELECT a.secid, i.name, i.cls, i.isin, SUM(a.buy), SUM(a.sell) " + cond + " GROUP BY a.secid", (since, asof))]
    return {"period": period, "asof": asof, "since": since, "source": src, "delay_min": delay, "empty": False,
            "by_class": by_cls, "by_sector": by_sec,
            "top_buy": sorted((x for x in inst if x["net"] > 0), key=lambda x: -x["net"])[:20],
            "top_sell": sorted((x for x in inst if x["net"] < 0), key=lambda x: x["net"])[:20]}


def q_instrument(db, secid, period):
    asof = _asof(db)
    r = db.execute("SELECT name, cls, isin FROM instruments WHERE secid=?", (secid,)).fetchone()
    out = {"secid": secid, "period": period, "name": r[0] if r else secid, "cls": r[1] if r else "", "isin": r[2] if r else "",
           "asof": asof, "series": []}
    if asof is None:
        return out
    step, span = {"5m": (300, 3 * 3600), "1h": (3600, 5 * 86400)}.get(period, (86400, 30 * 86400))
    since = asof - span
    rows = {}
    for b, buy, sell, n in db.execute("SELECT bucket, buy, sell, n FROM agg WHERE secid=? AND bucket>=? AND bucket<?", (secid, since, asof)):
        k = (b + 10800) // step * step - 10800 if step == 86400 else b // step * step
        x = rows.setdefault(k, [0.0, 0.0, 0])
        x[0] += buy
        x[1] += sell
        x[2] += n
    out["series"] = [{"ts": k, "buy": round(v[0], 2), "sell": round(v[1], 2), "n": v[2]} for k, v in sorted(rows.items())]
    out["source"], out["delay_min"] = _src(db, since, asof)
    return out


def _since(v, default):
    v = (v or "").strip()
    if re.fullmatch(r"\d{9,11}(\.\d+)?", v):
        return float(v)
    if re.fullmatch(r"\d{4}-\d\d-\d\d", v):
        return datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=MSK).timestamp()
    return default


def q_large(db, since=None, cls="", min_value=0.0, secids=(), isins=(), limit=200, now=None):
    t = now or time.time()
    since = _since(since, t - 3 * 86400)
    sql = ("SELECT l.ts,l.secid,i.name,l.cls,i.isin,l.side,l.price,l.qty,l.value,l.src FROM large l "
           "LEFT JOIN instruments i ON i.secid=l.secid WHERE l.ts>=? AND l.value>=?")
    args = [since, float(min_value or 0)]
    if cls in ("share", "bond", "fund"):
        sql += " AND l.cls=?"
        args.append(cls)
    if secids:
        sql += " AND l.secid IN (%s)" % ",".join("?" * len(secids))
        args += list(secids)
    if isins:
        sql += " AND i.isin IN (%s)" % ",".join("?" * len(isins))
        args += list(isins)
    sql += " ORDER BY l.ts DESC LIMIT ?"
    args.append(max(1, min(int(limit), 500)))
    return [{"ts": ts, "secid": s, "name": nm or s, "cls": c, "isin": isn or "", "side": sd, "price": p, "qty": q, "value": v, "src": src}
            for ts, s, nm, c, isn, sd, p, q, v, src in db.execute(sql, args)]


def q_spikes(db, since=None, secids=(), isins=(), limit=200, now=None):
    t = now or time.time()
    since = _since(since, t - 3 * 86400)
    sql = ("SELECT s.ts,s.secid,i.name,i.cls,i.isin,s.slot,s.value,s.median,s.ratio FROM spikes s "
           "LEFT JOIN instruments i ON i.secid=s.secid WHERE s.ts>=?")
    args = [since]
    if secids:
        sql += " AND s.secid IN (%s)" % ",".join("?" * len(secids))
        args += list(secids)
    if isins:
        sql += " AND i.isin IN (%s)" % ",".join("?" * len(isins))
        args += list(isins)
    sql += " ORDER BY s.ts DESC LIMIT ?"
    args.append(max(1, min(int(limit), 500)))
    return [{"ts": ts, "secid": s, "name": nm or s, "cls": c or "", "isin": isn or "", "slot": sl, "value": v, "median": md, "ratio": r}
            for ts, s, nm, c, isn, sl, v, md, r in db.execute(sql, args)]


def q_instrument_meta(db, secid):
    r = db.execute("SELECT secid,isin,uid,cls,board,name,lot,face FROM instruments WHERE secid=?", (secid,)).fetchone()
    return dict(zip(("secid", "isin", "uid", "cls", "board", "name", "lot", "face"), r)) if r else None


def q_instruments(db, limit=600):
    return [{"secid": s, "name": n, "cls": c, "isin": i} for s, n, c, i in
            db.execute("SELECT secid,name,cls,isin FROM instruments WHERE active=1 ORDER BY turnover DESC LIMIT ?", (limit,))]


def stats(db):
    q = lambda s: db.execute(s).fetchone()[0]  # noqa: E731
    return {"instruments": q("SELECT COUNT(*) FROM instruments WHERE active=1"), "with_uid": q("SELECT COUNT(*) FROM instruments WHERE uid IS NOT NULL AND active=1"),
            "agg_rows": q("SELECT COUNT(*) FROM agg"), "large": q("SELECT COUNT(*) FROM large"), "spikes": q("SELECT COUNT(*) FROM spikes"),
            "last_bucket": q("SELECT MAX(bucket) FROM agg"), "universe_ts": meta_get(db, "universe_ts")}


# ───────────────────────── запуск ─────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="Сборщик потоков денег TAnalytic")
    ap.add_argument("--data", required=True)
    ap.add_argument("--token-file", default="")
    ap.add_argument("--md-rate", type=int, default=200, help="запросов T-Invest MarketData в минуту для сборщика")
    ap.add_argument("--interval", type=float, default=15.0, help="пауза между циклами, с")
    ap.add_argument("--pace", type=float, default=0.3, help="пауза между запросами к ISS, с")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.makedirs(a.data, exist_ok=True)
    db = open_db(os.path.join(a.data, "flows.sqlite"))
    if a.stats:
        print(json.dumps(stats(db), ensure_ascii=False, indent=1))
        return 0
    stop = threading.Event()
    for sg in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sg, lambda *_: stop.set())
    token, how = tinvest_md.load_token(a.token_file)
    md = tinvest_md.MDClient(token, limits={"MarketDataService": a.md_rate}) if token else None
    log.info("T-Invest: %s", ("токен %s (%s)" % (tinvest_md.mask(token), how)) if token else "токена нет, работаю по ISS (задержка ~15 мин)")
    eng = Engine(db, IssFetcher(a.pace, stop), md, stop=stop)
    while not stop.is_set():
        eng.cycle()
        log.info("цикл: %s", eng.counters)
        if a.once:
            break
        stop.wait(a.interval)
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
