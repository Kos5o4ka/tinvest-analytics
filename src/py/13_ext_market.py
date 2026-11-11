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



