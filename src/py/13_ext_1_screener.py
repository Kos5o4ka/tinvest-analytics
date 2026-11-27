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


def _interp(pts, years):
    if not pts or years is None:
        return None
    if years <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if years <= x1:
            return y0 + (y1 - y0) * (years - x0) / (x1 - x0)
    return pts[-1][1]


def kbd_at(years):
    return _interp(kbd_curve(), years)


# ── скринер облигаций (Мосбиржа, ISS) ──

_scr = {"t": 0, "rows": []}
SCR_COLS_S = ("SECID,SHORTNAME,SECNAME,ISIN,FACEVALUE,FACEUNIT,COUPONPERCENT,NEXTCOUPON,MATDATE,OFFERDATE,"
              "LISTLEVEL,PREVLEGALCLOSEPRICE,YIELDATPREVWAPRICE,COUPONPERIOD,BONDSUBTYPE,ISSUESIZE,ACCRUEDINT,COUPONVALUE,PREVPRICE,BONDTYPE,COUPON_DETAILS")
SCR_COLS_M = "SECID,LAST,YIELD,WAPRICE,DURATION,VALTODAY,NUMTRADES,ZSPREAD,YIELDATWAPRICE,LASTCHANGEPRCNT"


def _iss_table(j, name):
    t = j[name]
    return [dict(zip(t["columns"], r)) for r in t["data"]]


def bond_cy(coupon_value, period, face, price):
    """Текущая доходность, %: годовой купон / чистая цена. Цена — в % номинала."""
    try:
        if not (coupon_value and period and face and price):
            return None
        return round(float(coupon_value) * (365.0 / float(period)) / float(face) * 100.0 / float(price) * 100.0, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def bond_chg(m, s, price):
    """Изменение цены за день, %: LASTCHANGEPRCNT, иначе LAST к предыдущей цене."""
    v = m.get("LASTCHANGEPRCNT")
    if v:
        return round(float(v), 2)
    prev = s.get("PREVPRICE") or s.get("PREVLEGALCLOSEPRICE")
    last = m.get("LAST")
    if prev and last:
        return round((float(last) / float(prev) - 1) * 100, 2)
    return 0.0


def liq_tiers(rows):
    """L1 — верхние 20% по обороту среди торгуемых, L2 — следующие 40%, L3 — остальные и без оборота."""
    traded = sorted((r["turn"] for r in rows if (r.get("turn") or 0) > 0), reverse=True)
    n = len(traded)
    c1 = traded[max(0, int(n * 0.2 + 0.999999) - 1)] if n else None
    c2 = traded[max(0, int(n * 0.6 + 0.999999) - 1)] if n else None
    for r in rows:
        t = r.get("turn") or 0
        r["liq"] = "L1" if t > 0 and t >= c1 else "L2" if t > 0 and t >= c2 else "L3"
    return rows


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
                "zs": m.get("ZSPREAD"), "cy": bond_cy(s.get("COUPONVALUE"), s.get("COUPONPERIOD"), s.get("FACEVALUE"), m.get("LAST") or price),
                "macdur": round(dur, 2) if dur else None, "chg": bond_chg(m, s, price), "sub": s.get("BONDSUBTYPE"), "size": s.get("ISSUESIZE"), "nkd": s.get("ACCRUEDINT"),
                "btype": s.get("BONDTYPE"), "cpn_det": s.get("COUPON_DETAILS")}
    rows = list(out.values())
    for r in rows:
        k = kbd_at(r["dur"]) if r["dur"] else None
        r["spread"] = round(r["yield"] - k, 2) if k is not None and r["cur"] == "RUB" else None
        r["rating"] = None
    liq_tiers(rows)
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


MKT_HIST2_KEY = "mkt_stats_hist_v2"
_hist_lock = threading.Lock()


def _stats_history(stats):
    st = store()
    hist = st.get(MKT_HIST_KEY) or {}
    ok = [g for g in stats["grid"] if g["all"]["spread"] is not None and g["all"]["n"] >= 3]
    snap = {g["bucket"]: g["all"]["spread"] for g in ok}
    if snap:
        hist[date.today().isoformat()] = snap
        for k in sorted(hist)[:-400]:
            hist.pop(k, None)
        st.put(MKT_HIST_KEY, hist)
        # расширенная история (формат v1 не меняем): спред, доходность и число выпусков по корзинам + точки кривой КБД
        try:
            with _hist_lock:
                h2 = st.get(MKT_HIST2_KEY) or {}
                h2[date.today().isoformat()] = {
                    "sp": snap, "y": {g["bucket"]: g["all"]["yield"] for g in ok}, "n": {g["bucket"]: g["all"]["n"] for g in ok},
                    "k": {str(t): (round(kbd_at(t), 2) if kbd_at(t) is not None else None) for t in (1, 2, 5, 10)}}
                for k in sorted(h2)[:-800]:
                    h2.pop(k, None)
                st.put(MKT_HIST2_KEY, h2)
        except Exception:  # noqa: BLE001
            pass
    return hist


_fl_job = {"running": False}


def fl_spread_job(todo):
    """Фон: для флоатеров скринера без свежего кэша тянет график выплат (moex_bondization, кэш 24 ч) не чаще FL_SPREAD_RPS в секунду
    и кладёт спред в kv fl_spread1:<isin> (30 сут). Скринер читает кэш синхронно и ничего не ждёт."""
    try:
        for r in todo:
            isin = r["isin"]
            fresh = store().get("bondiz2:" + isin, ttl=BC_TTL) is not None
            try:
                bz = moex_bondization(isin)
                fl_spread_put(isin, r.get("full") or r.get("name"), bz, float(r.get("nominal") or 0) or None, r.get("kind"), r.get("cpn_det"))
            except Exception:  # noqa: BLE001
                pass
            if not fresh:
                time.sleep(1.0 / FL_SPREAD_RPS)
    finally:
        _fl_job["running"] = False


def fl_spread_kick(rows, cached):
    """Запускает фоновый расчёт спредов для флоатеров без кэша; одновременно не больше одного задания."""
    todo = [r for r in rows if r.get("floating") and r.get("isin") and r["isin"] not in cached and r.get("cur") == "RUB"]
    if not todo or _fl_job["running"]:
        return False
    _fl_job["running"] = True
    threading.Thread(target=fl_spread_job, args=(todo,), daemon=True, name="fl-spread").start()
    return True


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
        r["rt_links"] = [{"a": x["agency"], "r": x["rating"], "o": x.get("outlook") or "", "d": x.get("date") or "",
                          "u": x.get("url")} for x in (rt.get("all") or [])] if rt and any(x.get("url") for x in rt.get("all") or []) else None
        info = None
        if ti and r.get("isin"):
            try:
                info = ti(r["isin"])
            except Exception:  # noqa: BLE001
                info = None
        r["sector"] = info.get("sector") if info else None
        r["floating"] = info.get("floating") if info else None
        if r["floating"] is None and r.get("btype"):      # без справочника T-Invest — по типу облигации из ISS
            r["floating"] = "плава" in r["btype"].lower()
        r["amort"] = info.get("amort") if info else None
    today_s = date.today().isoformat()
    for r in rows:      # линкер, к чему считается доходность (оферта/погашение), дней до оферты
        try:
            r["linker"] = bool(DBX_LINKER_RE.match(r.get("id") or "")) and r.get("kind") == "ofz"
        except NameError:
            r["linker"] = bool(re.match(r"^SU52\d{3}", r.get("id") or "")) and r.get("kind") == "ofz"
        of = r.get("offer")
        up = bool(of and of >= today_s and (not r.get("mat") or of < r["mat"]))
        r["ytm_kind"] = "offer" if up else "mat"
        try:
            r["days_to_offer"] = (datetime.strptime(of, "%Y-%m-%d").date() - date.today()).days if up else None
        except Exception:  # noqa: BLE001
            r["days_to_offer"] = None
    try:        # спред флоатера к КС из кэша (без ожидания); недостающее считает фоновое задание
        fsp = fl_spread_cached()
        for r in rows:
            r["fl_label"] = fl_label(fsp.get(r.get("isin")), True) if r.get("floating") else None
            r["fl_base"] = (fsp.get(r.get("isin")) or {}).get("base") if r.get("floating") else None
        fl_spread_kick(rows, fsp)
    except Exception:  # noqa: BLE001
        pass
    stats = market_stats(rows)
    try:
        hist = _stats_history(stats)
    except Exception:  # noqa: BLE001
        hist = {}
    try:
        lq = bench_lqdt_yield()
    except Exception:  # noqa: BLE001
        lq = None
    try:        # ожидаемая инфляция (прогноз ЦБ, декабрь к декабрю) для переключателя «реальная доходность»
        ie, isrc = scr_infl_exp()
    except Exception:  # noqa: BLE001
        ie, isrc = None, ""
    return {"rows": rows, "kbd": kbd_curve(), "updated": _scr["t"], "ratings": ratings_status(), "stats": stats, "stats_hist": hist,
            "floor": {"lqdt": lq}, "infl_exp": ie, "infl_src": isrc}


def scr_infl_exp():
    """(ожидаемая инфляция, %; подпись источника). Прогноз ЦБ на текущий год, иначе на ближайший; нет прогноза — (None, '')."""
    fc = inflation_forecast()
    ys = fc.get("yearly") or []
    if not ys:
        return None, ""
    y0 = date.today().year
    pick = next((y for y in ys if y["year"] == y0), ys[0])
    return pick["mid"], "прогноз Банка России на %d г. (%s)" % (pick["year"], fc.get("as_of") or "")


# ── спарклайны цен: последние ~30 торговых дней, кэш на сутки ──
SPARK_URL = ("https://iss.moex.com/iss/history/engines/stock/markets/bonds/securities/%s.json?iss.meta=off&iss.only=history"
             "&marketprice_board=1&history.columns=TRADEDATE,CLOSE,LEGALCLOSEPRICE,BOARDID&from=%s")
SPARK_MAX_IDS, SPARK_DAYS = 60, 30
_spark_cache = {}
_spark_lock = threading.Lock()


def spark_parse(j, n=SPARK_DAYS):
    """Ответ ISS history -> цены закрытия по торговым дням (старые первыми, не больше n). По дню берётся первая площадка с ценой."""
    t = (j or {}).get("history") or {}
    cols = t.get("columns") or []
    by = {}
    for row in t.get("data") or []:
        r = dict(zip(cols, row))
        d = r.get("TRADEDATE")
        px = r.get("CLOSE") or r.get("LEGALCLOSEPRICE")
        if not d or not px or d in by:
            continue
        by[d] = round(float(px), 3)
    return [by[d] for d in sorted(by)][-n:]


def spark_payload(ids, budget=25.0):
    """{isin: [цены]} для списка бумаг. Идёт последовательно, при ошибке источника останавливается и отдаёт, что есть."""
    out, t0 = {}, time.time()
    frm = (date.today() - timedelta(days=60)).isoformat()
    seen = []
    for i in ids:
        i = (i or "").strip().upper()
        if re.match(r"^[A-Z0-9]{5,16}$", i) and i not in seen:
            seen.append(i)
    for i in seen[:SPARK_MAX_IDS]:
        key = (i, date.today())
        with _spark_lock:
            hit = _spark_cache.get(key)
        if hit is not None:
            out[i] = hit
            continue
        if time.time() - t0 > budget:
            break
        try:
            vals = spark_parse(json.loads(http_text(SPARK_URL % (i, frm), timeout=15)))
        except Exception:  # noqa: BLE001
            break
        with _spark_lock:
            for k in [k for k in _spark_cache if k[1] != date.today()]:
                _spark_cache.pop(k, None)
            _spark_cache[key] = vals
        out[i] = vals
    return out


def bond_movers(n=50):
    """Лидеры падения/роста цены за день по облигациям (из тех же данных, что и скринер)."""
    rows = screener_rows()
    mv = [r for r in rows if r.get("chg")]
    br = globals().get("best_rating")

    def item(r):
        rt = r.get("rating")
        if rt is None and br:
            try:
                x = br(r.get("isin"), r["name"])
                rt = x["v"] if x else None
            except Exception:  # noqa: BLE001
                rt = None
        return {"name": r["name"], "isin": r.get("isin") or r["id"], "chg": r["chg"], "price": r["price"],
                "turnover": r["turn"], "trades": r["trades"], "rating": rt}
    down = [item(r) for r in sorted(mv, key=lambda r: r["chg"])[:n]]
    up = [item(r) for r in sorted(mv, key=lambda r: -r["chg"])[:n]]
    return {"down": down, "up": up, "total": len(mv), "n": n, "updated": _scr["t"]}


def _api_movers(cfg, acc, q, force):
    try:
        n = max(5, min(200, int(q.get("n", 50))))
    except (TypeError, ValueError):
        n = 50
    return bond_movers(n)


API_GET["/api/movers"] = _api_movers


