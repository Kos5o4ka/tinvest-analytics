#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Фоновый воркер-агрегатор среза рынка для сервера данных TAnalytic. Только stdlib, Python 3.8+.

Собирает по расписанию (и при старте) готовый срез рынка и складывает в `<data>/market.sqlite` (WAL):
  1. Облигации (TQCB, TQOB, TQOD, TQOY): котировки, доходности, купоны, формулы флоатеров (КС/RUSFAR/RUONIA);
  2. Акции TQBR + индекс IMOEX: цены, обороты, капитализация, динамика chg_d / chg_w / chg_m по свечам ISS;
  3. Готовые агрегаты для тепловой карты (ОФЗ выделены отдельно, квота на бакет ≤BB не теряется, сектора акций).

Сервер данных (tinvest_server.py) отдаёт готовый срез через /v1/market/snapshot и /v1/parsed/market/snapshot.

    python3 market_worker.py --data DIR [--interval 900] [--once] [--stats] [--verbose]
"""
import argparse
import json
import logging
import os
import re
import signal
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

UA = "TAnalytic-market/1.0 (+https://github.com/Kos5o4ka/tinvest-analytics)"
ISS = "https://iss.moex.com/iss/"
MSK = timezone(timedelta(hours=3))
log = logging.getLogger("market")
MAX_WORKERS = 4      # вежливо к MOEX ISS: не больше 4 запросов одновременно

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS snapshots(kind TEXT PRIMARY KEY, updated_at REAL NOT NULL, data_json TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL)",
)

BOND_BOARDS = ("TQCB", "TQOB", "TQOD", "TQOY")
BOND_URL = (
    ISS + "engines/stock/markets/bonds/boards/%s/securities.json?iss.meta=off"
    "&iss.only=securities,marketdata"
    "&securities.columns=SECID,ISIN,SHORTNAME,SECNAME,MATDATE,COUPONPERCENT,COUPONPERIOD,NEXTCOUPON,PREVLEGALCLOSEPRICE,YIELDATPREVWAPRICE,FACEVALUE,CURRENCYID,"
    "FACEUNIT,OFFERDATE,LISTLEVEL,BONDSUBTYPE,ISSUESIZE,ACCRUEDINT,COUPONVALUE,PREVPRICE,BONDTYPE,COUPON_DETAILS"
    "&marketdata.columns=SECID,WAPRICE,LAST,YIELD,YIELDATWAPRICE,DURATION,VALTODAY,VALTODAY_RUR,NUMTRADES,ZSPREAD,LASTCHANGEPRCNT"
)
STOCK_URL = (
    ISS + "engines/stock/markets/shares/boards/TQBR/securities.json?iss.meta=off"
    "&iss.only=securities,marketdata"
    "&securities.columns=SECID,ISIN,SHORTNAME,SECNAME,PREVPRICE,PREVLEGALCLOSEPRICE,ISSUESIZE,LOTSIZE,INSTRID,SECTYPE"
    "&marketdata.columns=SECID,LAST,WAPRICE,OPEN,VALTODAY,VALTODAY_RUR,ISSUECAPITALIZATION,LASTTOPREVPRICE"
)
IMOEX_URL = ISS + "statistics/engines/stock/markets/index/analytics/IMOEX.json?iss.meta=off&limit=100"
CANDLES_URL = (
    ISS + "engines/stock/markets/shares/boards/TQBR/securities/%s/candles.json"
    "?iss.meta=off&interval=24&from=%s&iss.only=candles&candles.columns=begin,close"
)

SECTORS = {}
for _s, _t in (
    ("Банки и финансы", "SBER SBERP VTBR T TCSG BSPB CBOM MBNK SVCB MOEX SPBE RENI LEAS SFIN ZAYM DOMRF"),
    ("Нефть и газ", "GAZP LKOH ROSN NVTK SIBN TATN TATNP SNGS SNGSP TRNFP BANE BANEP RNFT"),
    ("Металлы и добыча", "GMKN NLMK CHMF MAGN PLZL ALRS RUAL TRMK MTLR MTLRP SELG UGLD POLY RASP"),
    ("Электроэнергетика", "IRAO HYDR FEES UPRO MSRS MRKC MRKP MRKU MRKV ENPG LSNG MSNG ELFV TGKA"),
    ("Телеком и IT", "MTSS RTKM RTKMP YDEX YNDX OZON VKCO HEAD POSI CIAN ASTR DIAS WUSH SOFL"),
    ("Ритейл и потребление", "MGNT FIVE X5 LENT APTK BELU AQUA HNFG SVAV GCHE MVID DELI"),
    ("Транспорт", "AFLT FLOT NMTP FESH NKHP GLTR"),
    ("Химия и удобрения", "PHOR AKRN KZOS NKNC"),
    ("Строительство и девелопмент", "PIKK SMLT LSRG ETLN"),
):
    for _x in _t.split():
        SECTORS[_x] = _s

HM_BUCKETS = ("ОФЗ", "AAA", "AA", "A", "BBB", "≤BB", "без рейтинга")
_FLOATER_RX = re.compile(
    r"(КС|ключев(?:ая|ой)\s+ставк[аиеу]?|RUSFAR|RUONIA)\s*([+-])\s*(\d+(?:[.,]\d+)?)\s*(%|п\.?\s*п\.?|б\.?\s*п\.?)?",
    re.I,
)


class Stopped(Exception):
    pass


def _table(j, name):
    t = (j or {}).get(name) or {}
    cols = t.get("columns") or []
    return [dict(zip(cols, r)) for r in t.get("data") or []]


def parse_floater_formula(text):
    """Разбор текста купонной формулы ('КС + 2.5%', 'Ключевая ставка ЦБ РФ + 1,75%', 'RUSFAR + 1.2%')."""
    if not text or not isinstance(text, str):
        return None
    m = _FLOATER_RX.search(text)
    if not m:
        return None
    raw_base, sign, num_s, unit = m.groups()
    up = raw_base.upper()
    if "RUSFAR" in up:
        base = "RUSFAR"
    elif "RUONIA" in up:
        base = "RUONIA"
    else:
        base = "КС"
    val = float(num_s.replace(",", "."))
    if unit and "б" in unit.lower():
        val = val / 100.0
    if sign == "-":
        val = -val
    spread = round(val, 2)
    s_fmt = ("%.2f" % abs(spread)).replace(".", ",")
    op = "+" if spread >= 0 else "-"
    return {"base": base, "spread": spread, "label": "%s %s %s%%" % (base, op, s_fmt)}


def _rating_bucket(rating):
    if not rating or not isinstance(rating, str):
        return "без рейтинга"
    r = rating.strip().upper()
    if r.startswith("AAA"):
        return "AAA"
    if r.startswith("AA"):
        return "AA"
    if r.startswith("A"):
        return "A"
    if r.startswith("BBB"):
        return "BBB"
    if r.startswith(("BB", "B", "CCC", "CC", "C", "D")):
        return "≤BB"
    return "без рейтинга"


def _bond_extra(s, m, price, cpn):  # cpn — COUPONPERCENT без округления
    """Поля для скринера и карты облигаций на клиенте (только добавляются к строке; формат прежних полей не меняется)."""
    def num(x):
        try:
            return None if x is None else float(x)
        except (TypeError, ValueError):
            return None
    dur = m.get("DURATION")
    lastchg = m.get("LASTCHANGEPRCNT")
    prev = s.get("PREVPRICE") or s.get("PREVLEGALCLOSEPRICE")
    last = m.get("LAST")
    if lastchg:
        chg = round(float(lastchg), 2)
    elif prev and last:
        chg = round((float(last) / float(prev) - 1) * 100, 2)
    else:
        chg = 0.0
    cy = None
    try:
        cv, per, face, px = s.get("COUPONVALUE"), s.get("COUPONPERIOD"), s.get("FACEVALUE"), last or price
        if cv and per and face and px:
            cy = round(float(cv) * (365.0 / float(per)) / float(face) * 100.0 / float(px) * 100.0, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        cy = None
    of = s.get("OFFERDATE")
    return {"chg": chg, "level": s.get("LISTLEVEL"), "trades": m.get("NUMTRADES") or 0, "zs": m.get("ZSPREAD"), "cy": cy,
            "sub": s.get("BONDSUBTYPE"), "size": s.get("ISSUESIZE"), "nkd": s.get("ACCRUEDINT"), "btype": s.get("BONDTYPE"),
            "cpn_det": s.get("COUPON_DETAILS"), "offer": of if of and not str(of).startswith("0000") else None,
            "cur": (s.get("FACEUNIT") or "SUR").replace("SUR", "RUB"), "turn": round(num(m.get("VALTODAY")) or 0),
            "macdur": round(float(dur) / 365.0, 2) if dur else None, "coupon_raw": cpn}


def parse_moex_bonds(boards_json):
    """boards_json: dict {board: iss_json} -> список облигаций."""
    out, seen = [], set()
    for board, j in (boards_json or {}).items():
        if not j:
            continue
        md = {r["SECID"]: r for r in _table(j, "marketdata")}
        for s in _table(j, "securities"):
            secid = s.get("SECID")
            mat = s.get("MATDATE")
            if not secid or not mat or str(mat).startswith("0000"):
                continue
            isin = s.get("ISIN") or secid
            if isin in seen:
                continue
            m = md.get(secid, {})
            price = m.get("WAPRICE") or m.get("LAST") or s.get("PREVLEGALCLOSEPRICE")
            if not price:
                continue
            seen.add(isin)
            yld = m.get("YIELD") or m.get("YIELDATWAPRICE") or s.get("YIELDATPREVWAPRICE")
            short = s.get("SHORTNAME") or secid
            name = s.get("SECNAME") or short
            is_ofz = board == "TQOB" or "ОФЗ" in short.upper() or "ОФЗ" in name.upper()
            turn = m.get("VALTODAY_RUR") or m.get("VALTODAY") or 0
            dur = m.get("DURATION")
            cpn = s.get("COUPONPERCENT")
            row = {
                "secid": secid,
                "isin": isin,
                "board": board,
                "name": short,
                "full_name": name,
                "kind": "ofz" if is_ofz else "corp",
                "price": round(float(price), 3),
                "ytm": round(float(yld), 2) if yld is not None else None,
                "coupon_pct": round(float(cpn), 2) if cpn is not None else None,
                "coupon_period": s.get("COUPONPERIOD"),
                "next_coupon": s.get("NEXTCOUPON"),
                "matdate": mat,
                "duration": round(float(dur) / 365.0, 2) if dur else None,
                "turnover": round(float(turn or 0), 0),
                "face": s.get("FACEVALUE"),
                "currency": s.get("CURRENCYID") or "SUR",
                "floater": False,
                "floater_formula": None,
            }
            row.update(_bond_extra(s, m, price, cpn))
            ff = parse_floater_formula(name)
            if ff:
                row["floater"] = True
                row["floater_formula"] = ff
            out.append(row)
    out.sort(key=lambda r: r["turnover"], reverse=True)
    return out


def _pct_change(cur, prev):
    if cur is None or prev is None or prev <= 0:
        return None
    return round((float(cur) / float(prev) - 1.0) * 100.0, 2)


def parse_moex_stocks(tqbr_json, imoex_json=None, candles_by_secid=None):
    """Разбор акций TQBR + веса IMOEX + дневные/недельные/месячные изменения по свечам."""
    imoex_weights = {}
    for r in _table(imoex_json, "analytics"):
        t = r.get("ticker")
        if t:
            imoex_weights[t] = r.get("weight")
    md = {r["SECID"]: r for r in _table(tqbr_json, "marketdata")}
    out = []
    for s in _table(tqbr_json, "securities"):
        secid = s.get("SECID")
        if not secid:
            continue
        m = md.get(secid, {})
        price = m.get("LAST") or m.get("WAPRICE") or s.get("PREVPRICE") or s.get("PREVLEGALCLOSEPRICE")
        if not price:
            continue
        prev = s.get("PREVPRICE") or s.get("PREVLEGALCLOSEPRICE")
        chg_d = m.get("LASTTOPREVPRICE")
        if chg_d is None:
            chg_d = _pct_change(price, prev)
        else:
            chg_d = round(float(chg_d), 2)
        candles = (candles_by_secid or {}).get(secid) or []
        chg_w = _pct_change(price, candles[-6]["close"]) if len(candles) >= 6 else (
            _pct_change(price, candles[0]["close"]) if len(candles) >= 2 else None
        )
        chg_m = _pct_change(price, candles[-22]["close"]) if len(candles) >= 22 else (
            _pct_change(price, candles[0]["close"]) if len(candles) >= 10 else None
        )
        turn = m.get("VALTODAY_RUR") or m.get("VALTODAY") or 0
        cap = m.get("ISSUECAPITALIZATION")
        if not cap and s.get("ISSUESIZE"):
            cap = float(price) * float(s["ISSUESIZE"])
        out.append({
            "secid": secid,
            "isin": s.get("ISIN") or "",
            "name": s.get("SHORTNAME") or secid,
            "full_name": s.get("SECNAME") or s.get("SHORTNAME") or secid,
            "price": round(float(price), 4),
            "prev_price": round(float(prev), 4) if prev else None,
            "chg_d": chg_d,
            "chg_w": chg_w,
            "chg_m": chg_m,
            "turnover": round(float(turn or 0), 0),
            "lot": int(s.get("LOTSIZE") or 1),
            "instrid": s.get("INSTRID") or "",
            "sectype": str(s.get("SECTYPE") or ""),
            "is_fund": str(s.get("INSTRID") or "").startswith("IF"),
            "cap": round(float(cap), 0) if cap else None,
            "sector": SECTORS.get(secid, "Прочее"),
            "imoex": secid in imoex_weights,
            "imoex_weight": imoex_weights.get(secid),
        })
    out.sort(key=lambda r: r["turnover"], reverse=True)
    return out


def build_heatmap_aggregates(bonds, stocks, ratings=None, per_bucket=60):
    """Готовые агрегаты для тепловой карты: ОФЗ отдельно, не теряем <=BB, сектора акций."""
    ratings = ratings or {}
    bond_buckets = {b: [] for b in HM_BUCKETS}
    for r in bonds:
        b = "ОФЗ" if r.get("kind") == "ofz" else _rating_bucket(r.get("rating") or ratings.get(r.get("isin")))
        bond_buckets[b].append({
            "isin": r["isin"],
            "secid": r["secid"],
            "name": r["name"],
            "kind": r["kind"],
            "bucket": b,
            "price": r["price"],
            "ytm": r["ytm"],
            "turnover": r["turnover"],
            "floater": r.get("floater", False),
        })
    bonds_out = []
    for b in HM_BUCKETS:
        items = sorted(bond_buckets[b], key=lambda x: x["turnover"], reverse=True)[:per_bucket]
        bonds_out.extend(items)

    eq_by_sector = {}
    for s in stocks:
        sec = s.get("sector") or "Прочее"
        eq_by_sector.setdefault(sec, []).append({
            "secid": s["secid"],
            "isin": s["isin"],
            "name": s["name"],
            "sector": sec,
            "price": s["price"],
            "chg_d": s["chg_d"],
            "chg_w": s["chg_w"],
            "chg_m": s["chg_m"],
            "turnover": s["turnover"],
            "cap": s["cap"],
            "imoex": s["imoex"],
        })
    return {
        "bonds": bonds_out,
        "bond_buckets": {b: len(bond_buckets[b]) for b in HM_BUCKETS},
        "equities": eq_by_sector,
    }


def open_db(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA busy_timeout=10000")
    for q in SCHEMA:
        db.execute(q)
    return db


def _http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _pmap(fn, items, workers):
    """Параллельный map с сохранением порядка; ошибка отдельного элемента -> (None, исключение)."""
    def one(x):
        try:
            return fn(x), None
        except Exception as e:  # noqa: BLE001
            return None, e
    workers = max(1, min(int(workers or 1), MAX_WORKERS, len(items) or 1))
    if workers == 1:
        return [one(x) for x in items]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="market") as ex:
        return list(ex.map(one, items))


def collect_once(db, fetch_json=_http_json, now=None, fetch_candles=True, candle_limit=100, workers=MAX_WORKERS):
    """Один цикл сбора среза рынка -> {bonds_n, stocks_n, updated_at, build_sec}. Запросы к ISS идут параллельно (<=MAX_WORKERS)."""
    t_start = time.time()
    ts = t_start if now is None else float(now)
    urls = [BOND_URL % b for b in BOND_BOARDS] + [STOCK_URL, IMOEX_URL]
    res = _pmap(fetch_json, urls, workers)
    boards_json = {}
    for b, (j, e) in zip(BOND_BOARDS, res[:len(BOND_BOARDS)]):
        if e:
            log.warning("bonds %s: %s", b, e)
        boards_json[b] = None if e else j
    bonds = parse_moex_bonds(boards_json)

    (tqbr_json, e1), (imoex_json, e2) = res[len(BOND_BOARDS)], res[len(BOND_BOARDS) + 1]
    if e1:
        log.warning("stocks TQBR: %s", e1)
        tqbr_json = None
    if e2:
        log.warning("IMOEX: %s", e2)
        imoex_json = None

    candles_by_secid = {}
    if fetch_candles and tqbr_json:
        since = (datetime.fromtimestamp(ts, MSK) - timedelta(days=45)).strftime("%Y-%m-%d")
        prelim = parse_moex_stocks(tqbr_json, imoex_json)
        targets = [s["secid"] for s in prelim if s["imoex"] or s["turnover"] > 0][:candle_limit]
        for secid, (cj, err) in zip(targets, _pmap(lambda x: fetch_json(CANDLES_URL % (x, since)), targets, workers)):
            if err or cj is None:
                continue
            candles_by_secid[secid] = [
                {"begin": r["begin"], "close": r["close"]}
                for r in _table(cj, "candles") if r.get("close")
            ]

    stocks = parse_moex_stocks(tqbr_json, imoex_json, candles_by_secid)
    heatmap = build_heatmap_aggregates(bonds, stocks)

    db.execute("BEGIN IMMEDIATE")
    try:
        for kind, payload in (("bonds", bonds), ("stocks", stocks), ("heatmap", heatmap)):
            db.execute(
                "INSERT INTO snapshots(kind, updated_at, data_json) VALUES(?,?,?) "
                "ON CONFLICT(kind) DO UPDATE SET updated_at=excluded.updated_at, data_json=excluded.data_json",
                (kind, ts, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
            )
        for k, v in (
            ("last_run", str(ts)),
            ("bonds_n", str(len(bonds))),
            ("stocks_n", str(len(stocks))),
            ("build_sec", "%.2f" % (time.time() - t_start)),
        ):
            db.execute(
                "INSERT INTO meta(k, v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (k, v),
            )
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return {"bonds_n": len(bonds), "stocks_n": len(stocks), "updated_at": ts, "build_sec": round(time.time() - t_start, 2)}


def query_snapshot(db, kind="all"):
    """Чтение среза из market.sqlite (mode=ro). kind: all | bonds | stocks | heatmap | status."""
    if kind == "status":
        return stats(db)
    if kind in ("bonds", "stocks", "heatmap"):
        r = db.execute("SELECT updated_at, data_json FROM snapshots WHERE kind=?", (kind,)).fetchone()
        if not r:
            return {"empty": True, "kind": kind}
        return {"empty": False, "kind": kind, "updated_at": r[0], "data": json.loads(r[1])}
    if kind == "all":
        rows = db.execute("SELECT kind, updated_at, data_json FROM snapshots WHERE kind IN ('bonds','stocks','heatmap')").fetchall()
        if not rows:
            return {"empty": True, "kind": "all"}
        out = {"empty": False, "kind": "all", "updated_at": max(r[1] for r in rows)}
        for k, _t, js in rows:
            out[k] = json.loads(js)
        return out
    raise ValueError("bad kind")


def stats(db):
    meta = dict(db.execute("SELECT k, v FROM meta").fetchall())
    snaps = {k: t for k, t in db.execute("SELECT kind, updated_at FROM snapshots").fetchall()}
    return {
        "last_run": float(meta["last_run"]) if meta.get("last_run") else None,
        "bonds_n": int(meta.get("bonds_n") or 0),
        "stocks_n": int(meta.get("stocks_n") or 0),
        "snapshots": snaps,
    }


def loop(data_dir, interval, stop, once=False, workers=MAX_WORKERS):
    db = open_db(os.path.join(data_dir, "market.sqlite"))
    try:
        while not stop.is_set():
            t0 = time.time()
            try:
                res = collect_once(db, workers=workers)
                log.info("срез собран: %d облигаций, %d акций (%.1f с)", res["bonds_n"], res["stocks_n"], time.time() - t0)
            except Exception as e:  # noqa: BLE001
                log.warning("ошибка сбора среза: %s", e)
            if once:
                return
            stop.wait(interval)
    finally:
        db.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сборщик рыночного среза для сервера данных TAnalytic")
    ap.add_argument("--data", required=True, help="каталог данных (market.sqlite)")
    ap.add_argument("--interval", type=int, default=900, help="пауза между обновлениями, сек")
    ap.add_argument("--loop", action="store_true", help="работать циклом (по умолчанию так и есть; флаг нужен для systemd-юнита)")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS, help="параллельных запросов к ISS (не больше %d)" % MAX_WORKERS)
    ap.add_argument("--once", action="store_true", help="один проход и выход")
    ap.add_argument("--stats", action="store_true", help="показать статистику market.sqlite и выйти")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.stats:
        p = os.path.join(a.data, "market.sqlite")
        if not os.path.exists(p):
            print("{}")
            return 0
        db = sqlite3.connect("file:%s?mode=ro" % quote(p.replace("\\", "/"), safe="/:"), uri=True, timeout=5)
        try:
            print(json.dumps(stats(db), ensure_ascii=False, indent=2))
        finally:
            db.close()
        return 0
    stop = threading.Event()
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stop.set())
    loop(a.data, a.interval, stop, a.once, a.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
