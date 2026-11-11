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
              "LISTLEVEL,PREVLEGALCLOSEPRICE,YIELDATPREVWAPRICE,COUPONPERIOD,BONDSUBTYPE,ISSUESIZE,ACCRUEDINT")
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
                "zs": m.get("ZSPREAD"), "sub": s.get("BONDSUBTYPE"), "size": s.get("ISSUESIZE"), "nkd": s.get("ACCRUEDINT")}
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
    try:
        primary_snapshot(rows)
    except Exception:  # noqa: BLE001
        pass
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




# ── снимки объявленных размещений (накопление: позже можно сравнить ориентир и итог) ──

PRI_SNAP_KEY = "pri_snap_v1"
_snap_lock = threading.Lock()


def primary_snapshot(rows):
    """Раз в день сохраняет список объявленных размещений; если состав и статусы не изменились — только отмечает проверку."""
    slim = [{"isin": r.get("isin"), "short": r.get("short"), "desc": r.get("desc"), "start": r.get("start"), "end": r.get("end"),
             "book": r.get("book"), "status": r.get("status"), "rating": (r.get("rating") or {}).get("v")} for r in rows]
    if not slim:
        return
    st = store()
    today = date.today().isoformat()
    with _snap_lock:
        d = st.get(PRI_SNAP_KEY) or {"days": {}}
        days = d.setdefault("days", {})
        last = days[max(days)] if days else None
        if last == slim and d.get("checked") == today:
            return
        if last != slim:
            days[today] = slim
        d["checked"] = today
        for k in sorted(days)[:-400]:
            days.pop(k, None)
        st.put(PRI_SNAP_KEY, d)


# ── первичка против вторички: как торгуются выпуски, размещённые за последние 12 месяцев ──

PRI_ISS_KEY, PRI_H_PREFIX, PRI_MAX, PRI_DAYS = "pri_issue_v1", "prih1:", 700, 365
_pri_h = {"running": False, "phase": "", "done": 0, "total": 0, "fin": 0, "err": None, "memo": (0, None)}
HIST_URL = ("https://iss.moex.com/iss/history/engines/stock/markets/bonds/securities/%s.json?iss.meta=off"
            "&iss.only=history,history.cursor&history.columns=BOARDID,TRADEDATE,VALUE,NUMTRADES,WAPRICE,LEGALCLOSEPRICE,CLOSE,"
            "YIELDCLOSE,YIELDATWAP&from=%s&till=%s&start=%d")


def _pri_dates(secid):
    j = json.loads(http_text("https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description"
                             "&description.columns=name,value" % secid, timeout=25))
    m = {r[0]: r[1] for r in j["description"]["data"]}
    ok = lambda v: v if v and re.match(r"^\d{4}-\d\d-\d\d$", v) and not v.startswith("0000") else ""  # noqa: E731
    return [ok(m.get("ISSUEDATE")), ok(m.get("STARTDATEMOEX"))]


def _day_add(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def _pri_history(secid, d0, today):
    """Цена и доходность в 1-й день торгов, через 7 и 30 дней. Цена — % от номинала (средневзвешенная по основной площадке дня)."""
    till = min(today, _day_add(d0, 50))
    rows, start = [], 0
    while start < 400:
        j = json.loads(http_text(HIST_URL % (secid, d0, till, start), timeout=30))
        t = j["history"]
        part = [dict(zip(t["columns"], r)) for r in t["data"]]
        rows += part
        if len(part) < 100:
            break
        start += 100
    best = {}
    for r in rows:
        px = r.get("WAPRICE") or r.get("LEGALCLOSEPRICE") or r.get("CLOSE")
        if not px or not r.get("TRADEDATE"):
            continue
        cur = best.get(r["TRADEDATE"])
        if cur is None or (r.get("VALUE") or 0) > (cur.get("VALUE") or 0):
            best[r["TRADEDATE"]] = dict(r, px=px)
    days = sorted(best)
    out = {"d0": None, "p0": None, "y0": None, "p7": None, "y7": None, "p30": None, "y30": None, "t": time.time()}
    if days:
        f = days[0]
        if f <= _day_add(d0, 14):
            out.update(d0=f, p0=round(best[f]["px"], 2), y0=best[f].get("YIELDCLOSE") or best[f].get("YIELDATWAP"))
            for k, n in (("7", 7), ("30", 30)):
                lo, hi = _day_add(f, n), _day_add(f, n + 7)
                c = [x for x in days if lo <= x <= hi]
                if c:
                    out["p" + k] = round(best[c[0]]["px"], 2)
                    out["y" + k] = best[c[0]].get("YIELDCLOSE") or best[c[0]].get("YIELDATWAP")
            out["done"] = today >= _day_add(f, 40)
    out["n_days"] = len(days)
    # выпуск без сделок вообще (ещё не торговался) — перепроверим позже
    out["done"] = bool(out.get("done"))
    return out


def _pri_candidates():
    st = store()
    iss = st.get(PRI_ISS_KEY) or {}
    cut = _day_add(date.today().isoformat(), -PRI_DAYS)
    c = []
    for sid, (a, b) in iss.items():
        ref = b or a
        if ref and ref >= cut:
            c.append((ref, sid))
    c.sort(reverse=True)
    return iss, [(sid, ref) for ref, sid in c[:PRI_MAX]]


def _pri_run():
    try:
        st = store()
        st_rows = _scr["rows"] or screener_rows()
        uni = {r["id"]: r for r in st_rows}
        iss = st.get(PRI_ISS_KEY) or {}
        miss = [s for s in uni if s not in iss]
        _pri_h.update(phase="Узнаю даты размещения выпусков", done=0, total=len(miss))
        for k in range(0, len(miss), 200):
            part = miss[k:k + 200]

            def one(s):
                try:
                    return s, _pri_dates(s)
                except Exception:  # noqa: BLE001
                    return s, None
            for s, v in pool_map(one, part, workers=8):
                if v is not None:
                    iss[s] = v
            st.put(PRI_ISS_KEY, iss)
            _pri_h["done"] = min(len(miss), k + 200)
        iss, cand = _pri_candidates()
        cand = [(s, ref) for s, ref in cand if s in uni]
        today = date.today().isoformat()
        todo = []
        for s, ref in cand:
            e = st.get(PRI_H_PREFIX + s)
            if e and (e.get("done") or time.time() - e.get("t", 0) < 12 * 3600):
                continue
            todo.append((s, ref))
        _pri_h.update(phase="Загружаю историю торгов новых выпусков", done=0, total=len(todo))

        def hist(x):
            try:
                return x[0], _pri_history(x[0], x[1], today)
            except Exception:  # noqa: BLE001
                return x[0], None
        for k in range(0, len(todo), 40):
            res = pool_map(hist, todo[k:k + 40], workers=8)
            st.put_many([(PRI_H_PREFIX + s, v) for s, v in res if v is not None])
            _pri_h["done"] = min(len(todo), k + 40)
        _pri_h["fin"] = time.time()
        _pri_h["err"] = None
    except Exception as e:  # noqa: BLE001
        _pri_h["err"] = str(e)[:200]
    finally:
        _pri_h.update(running=False, phase="", memo=(0, None))


def primary_stats_start(force=False):
    with _rt_lock:
        if _pri_h["running"]:
            return
        if not force and time.time() - _pri_h["fin"] < 6 * 3600:
            return
        _pri_h["running"] = True
    threading.Thread(target=_pri_run, daemon=True).start()


def _grp_stats(items):
    p0 = [x["p0"] for x in items if x["p0"] is not None]
    p7 = [x["p7"] for x in items if x["p7"] is not None]
    p30 = [x["p30"] for x in items if x["p30"] is not None]
    dn = [x["now"] - x["p0"] for x in items if x["now"] is not None and x["p0"] is not None]
    return {"n": len(items), "p0": _med(p0), "p7": _med(p7), "p30": _med(p30), "n30": len(p30),
            "below30": round(100.0 * sum(1 for v in p30 if v < 100) / len(p30), 1) if p30 else None,
            "d_now": _med(dn)}


def primary_stats_payload():
    memo = _pri_h["memo"]
    if memo[1] is not None and time.time() - memo[0] < 120 and not _pri_h["running"]:
        return dict(memo[1], loading=False)
    primary_stats_start()
    st = store()
    iss, cand = _pri_candidates()
    uni = {r["id"]: r for r in _scr["rows"]}
    items = []
    for sid, ref in cand:
        e = st.get(PRI_H_PREFIX + sid)
        r = uni.get(sid)
        if not e or not r or e.get("p0") is None:
            continue
        rt, ci = None, None
        try:
            ti = globals().get("tcat_info")
            ci = ti(r.get("isin")) if ti and r.get("isin") else None
            rt = best_rating(r.get("isin"), (ci or {}).get("name") or r["name"]) if r["kind"] == "corp" else None
        except Exception:  # noqa: BLE001
            rt = None
        sector = (ci or {}).get("sector") if r["kind"] == "corp" else None
        sane = lambda v, lo, hi: v if v is not None and lo <= v <= hi else None  # noqa: E731
        now_ok = r.get("price") if (r.get("yield") or 0) > 0 else None       # без доходности цена ненадёжна (индексируемый номинал и т. п.)
        if not (80 <= e["p0"] <= 120):
            continue
        items.append({"secid": sid, "isin": r.get("isin"), "name": r["name"], "kind": r["kind"], "d0": e["d0"], "p0": e["p0"], "y0": e.get("y0"),
                      "p7": sane(e.get("p7"), 50, 150), "p30": sane(e.get("p30"), 50, 150), "y30": e.get("y30"),
                      "now": sane(now_ok, 10, 150), "ynow": r.get("yield"),
                      "rating": rt["v"] if rt else None, "bucket": "ОФЗ" if r["kind"] == "ofz" else rating_bucket(rt["v"] if rt else None),
                      "sector": sector})
    by_b, by_s = {}, {}
    for x in items:
        by_b.setdefault(x["bucket"], []).append(x)
        if x["sector"]:
            by_s.setdefault(x["sector"], []).append(x)
    order = ["ОФЗ"] + MKT_BUCKETS + ["нет рейтинга"]
    buckets = [dict(_grp_stats(by_b[b]), bucket=b) for b in order if b in by_b]
    sectors = sorted((dict(_grp_stats(v), sector=k) for k, v in by_s.items() if len(v) >= 3), key=lambda g: -g["n"])[:12]
    aged = [x for x in items if x["now"] is not None and x["d0"] <= _day_add(date.today().isoformat(), -7)]
    aged.sort(key=lambda x: x["now"] - x["p0"])
    trim = lambda x: dict(x, delta=round(x["now"] - x["p0"], 2))  # noqa: E731
    by_m = {}
    for x in items:
        by_m.setdefault(x["d0"][:7], []).append(x)
    months = [dict(_grp_stats(v), m=k) for k, v in sorted(by_m.items())]
    snaps = (st.get(PRI_SNAP_KEY) or {}).get("days") or {}
    res = {"all": _grp_stats(items), "buckets": buckets, "sectors": sectors, "months": months,
           "worst": [trim(x) for x in aged[:8]], "best": [trim(x) for x in aged[::-1][:8]],
           "universe": len(cand), "ready": len(items), "snap_days": len(snaps), "updated": _pri_h["fin"], "err": _pri_h["err"]}
    if not _pri_h["running"]:
        _pri_h["memo"] = (time.time(), res)
    return dict(res, loading=_pri_h["running"], phase=_pri_h["phase"], done=_pri_h["done"], total=_pri_h["total"])


def _api_primary_stats(cfg, acc, q, force):
    return primary_stats_payload()


API_GET["/api/primary/stats"] = _api_primary_stats


# ── кривая КБД на прошлые даты ──

def kbd_curve_on(d):
    """Кривая КБД на дату d (ISO; при выходном берётся ближайший прошлый торговый день). Кэш для прошлых дат навсегда."""
    st = store()
    key = "kbdc1:" + d
    v = st.get(key)
    if v:
        return v
    if d >= date.today().isoformat():
        return [list(p) for p in kbd_curve()]
    for k in range(0, 6):
        dd = _day_add(d, -k)
        j = json.loads(http_text("https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields&date=" + dd))
        pts = sorted((r[2], r[3]) for r in j["yearyields"]["data"])
        if pts:
            v = [list(p) for p in pts]
            st.put(key, v)
            return v
    return None


CURVE_TERMS = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20]
CURVE_AGO = [(0, "Сегодня"), (30, "1 мес. назад"), (91, "3 мес. назад"), (182, "6 мес. назад"), (365, "12 мес. назад")]


def _term_lab(t):
    return "%d мес" % round(t * 12) if t < 1 else "%d г." % t


def kbd_curves_payload():
    today = date.today().isoformat()
    ds = [(_day_add(today, -n), lab) for n, lab in CURVE_AGO]

    def one(x):
        try:
            return kbd_curve_on(x[0])
        except Exception:  # noqa: BLE001
            return None
    res = pool_map(one, ds, workers=5)
    items = []
    for (d, lab), pts in zip(ds, res):
        if pts:
            items.append({"date": d, "label": lab, "y": [round(_interp(pts, t), 2) for t in CURVE_TERMS]})
    return {"terms": CURVE_TERMS, "labels": [_term_lab(t) for t in CURVE_TERMS], "items": items}


def _fmt_pp(v):
    return ("%.2f" % abs(v)).replace(".", ",")


def _curve_notes(cv):
    out = []
    its = cv.get("items") or []
    if len(its) < 2:
        return out
    now = its[0]
    i2, i10, i1 = CURVE_TERMS.index(2), CURVE_TERMS.index(10), CURVE_TERMS.index(1)
    for it in its[1:]:
        if it["label"] != "3 мес. назад":
            continue
        s0, s1 = it["y"][i10] - it["y"][i2], now["y"][i10] - now["y"][i2]
        if abs(s1 - s0) < 0.15:
            out.append("Форма кривой за 3 месяца почти не изменилась: разница между 10-летними и 2-летними ставками %s п.п." % _fmt_pp(s1))
        else:
            out.append("За 3 месяца кривая КБД стала %s: разница между 10-летними и 2-летними ставками %s с %s до %s п.п." % (
                "круче (длинные ставки выше коротких сильнее)" if s1 > s0 else "положе (длинные и короткие ставки сближаются)",
                "выросла" if s1 > s0 else "сократилась", ("-" if s0 < 0 else "") + _fmt_pp(s0), ("-" if s1 < 0 else "") + _fmt_pp(s1)))
        d1 = now["y"][i1] - it["y"][i1]
        if abs(d1) >= 0.1:
            out.append("Доходность 1-летних гособлигаций %s на %s п.п. (с %s до %s %%)." % (
                "выросла" if d1 > 0 else "снизилась", _fmt_pp(d1), _fmt_pp(it["y"][i1]), _fmt_pp(now["y"][i1])))
    yr = [it for it in its if it["label"] == "12 мес. назад"]
    if yr:
        d2 = now["y"][i2] - yr[0]["y"][i2]
        out.append("За год 2-летняя доходность КБД %s на %s п.п." % ("выросла" if d2 > 0 else "снизилась", _fmt_pp(d2)))
    return out


# ── история медианных спредов к КБД по рейтингам: накопленные снимки + разовое восстановление по истории торгов ──

BF_KEY = "mkt_bf_v1"
_bf = {"running": False, "last": 0}


def _bf_dates():
    t = date.today()
    ds = set()
    for n in [7 * k for k in range(1, 9)] + [91, 119, 147, 182]:
        d = t - timedelta(days=n)
        while d.weekday() > 4:
            d -= timedelta(days=1)
        ds.add(d.isoformat())
    return sorted(ds)


HB_URL = ("https://iss.moex.com/iss/history/engines/stock/markets/bonds/boards/TQCB/securities.json?iss.meta=off&date=%s&start=%d"
          "&iss.only=history,history.cursor&history.columns=SECID,YIELDCLOSE,YIELDATWAP,DURATION,MATDATE,NUMTRADES,VALUE,CURRENCYID")


def _bf_day(d, bucket_of):
    pts = kbd_curve_on(d)
    if not pts:
        return None

    def page(s):
        j = json.loads(http_text(HB_URL % (d, s), timeout=40))
        t = j["history"]
        return [dict(zip(t["columns"], r)) for r in t["data"]], j["history.cursor"]["data"][0][1]
    rows, total = page(0)
    starts = list(range(100, min(total, 6000), 100))
    for part, _ in pool_map(lambda s: _safe_pg(page, s), starts, workers=6):
        rows += part
    by = {}
    for r in rows:
        b = bucket_of.get(r["SECID"])
        y = r.get("YIELDCLOSE") or r.get("YIELDATWAP")
        if not b or not y or not r.get("DURATION") or not (r.get("NUMTRADES") or 0) or r.get("CURRENCYID") not in ("SUR", "RUB", None):
            continue
        if not (0 < y < 60) or not r.get("MATDATE") or r["MATDATE"] <= _day_add(d, 40):
            continue
        by.setdefault(b, []).append(y - _interp(pts, r["DURATION"] / 365.0))
    sp, nn = {}, {}
    for b, v in by.items():
        if len(v) >= 3:
            sp[b], nn[b] = _med(v), len(v)
    return {"sp": sp, "n": nn, "bf": True} if sp else None


def _safe_pg(fn, s):
    try:
        return fn(s)
    except Exception:  # noqa: BLE001
        return [], 0


def _bf_run():
    try:
        rows = _scr["rows"]
        if not rows or not any(r.get("rating") for r in rows):
            screener_payload()
            rows = _scr["rows"]
        bucket_of = {r["id"]: rating_bucket(r["rating"]) for r in rows if r.get("kind") == "corp" and r.get("cur") == "RUB" and r.get("rating")}
        st = store()
        bf = st.get(BF_KEY) or {}
        for d in _bf_dates():
            if d in bf:
                continue
            try:
                v = _bf_day(d, bucket_of)
            except Exception:  # noqa: BLE001
                v = None
            if v:
                bf[d] = v
                st.put(BF_KEY, bf)
        _bf["last"] = time.time()
    except Exception:  # noqa: BLE001
        _bf["last"] = time.time() - 3600 * 5
    finally:
        _bf["running"] = False


def spreads_backfill_start():
    with _rt_lock:
        if _bf["running"] or time.time() - _bf["last"] < 6 * 3600:
            return
        _bf["running"] = True
    threading.Thread(target=_bf_run, daemon=True).start()


def spreads_history_payload():
    st = store()
    live = st.get(MKT_HIST2_KEY) or {}
    old = st.get(MKT_HIST_KEY) or {}
    allh = dict(st.get(BF_KEY) or {})
    for d, sp in old.items():           # v1 (только спреды), если нет v2
        if d not in live:
            allh[d] = {"sp": sp}
    allh.update(live)
    days = sorted(allh)[-400:]
    series = {b: [(allh[d].get("sp") or {}).get(b) for d in days] for b in MKT_BUCKETS}
    series = {b: v for b, v in series.items() if any(x is not None for x in v)}
    return {"dates": days, "series": series, "bf": [d for d in days if allh[d].get("bf")]}


def _spread_notes(h):
    out = []
    ds = h["dates"]
    if len(ds) < 2:
        return ["История спредов накапливается: каждый день работы программы добавляет точку."]
    last = ds[-1]
    for b in ("AAA", "AA", "A", "BBB"):
        v = h["series"].get(b)
        if not v or v[-1] is None:
            continue
        tgt = _day_add(last, -30)
        cand = [i for i, d in enumerate(ds[:-1]) if d <= tgt and v[i] is not None]
        if not cand:
            cand = [i for i, d in enumerate(ds[:-1]) if v[i] is not None and d <= _day_add(last, -7)]
        if not cand:
            continue
        i = cand[-1]
        diff = v[-1] - v[i]
        days = (datetime.strptime(last, "%Y-%m-%d") - datetime.strptime(ds[i], "%Y-%m-%d")).days
        per = "за месяц" if 25 <= days <= 40 else "за %d дн." % days
        if abs(diff) < 0.1:
            out.append("Спред %s почти не изменился %s: %s п.п." % (b, per, _fmt_pp(v[-1])))
        else:
            out.append("Спред %s %s на %s п.п. %s (с %s до %s п.п.)." % (
                b, "расширился" if diff > 0 else "сузился", _fmt_pp(diff), per, _fmt_pp(v[i]), _fmt_pp(v[-1])))
    return out or ["Для вывода о динамике пока мало данных по спредам."]


def rates_extra_payload():
    spreads_backfill_start()
    h = spreads_history_payload()
    cv = kbd_curves_payload()
    return {"spreads": h, "curves": cv, "notes": _curve_notes(cv), "spread_notes": _spread_notes(h), "loading": _bf["running"]}


API_GET["/api/rates/extra"] = lambda cfg, acc, q, force: rates_extra_payload()


# ── ежедневная фоновая работа: снимок размещений и спреды (история копится, даже если разделы не открывали) ──

def _market_daily_loop():
    time.sleep(20)
    while True:
        try:
            primary_payload()
        except Exception:  # noqa: BLE001
            pass
        try:
            h = store().get(MKT_HIST2_KEY) or {}
            if date.today().isoformat() not in h:
                screener_payload()
            spreads_backfill_start()
            # статистика первички (тысячи запросов к ISS при первом расчёте) — только по открытию раздела «Первичка»
        except Exception:  # noqa: BLE001
            pass
        time.sleep(6 * 3600)


def _market_daily_start():
    threading.Thread(target=_market_daily_loop, daemon=True).start()


STARTUP_HOOKS.append(_market_daily_start)
