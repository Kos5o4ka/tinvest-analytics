RATE_TERM_MIN, RATE_TERM_MAX, RATE_TERMS_MAX = 0.25, 30.0, 6
_rates_state = {"running": False, "ended": 0.0}


def kbd_interp(grid, term):
    """Доходность КБД на срок term (лет): линейная интерполяция между соседними точками сетки {срок: доходность}.
    Вне диапазона сетки возвращает None (не экстраполируем и не тянем крайнее значение)."""
    pts = sorted((float(k), v) for k, v in (grid or {}).items() if v is not None)
    if not pts or term is None or term < pts[0][0] - 1e-9 or term > pts[-1][0] + 1e-9:
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if term <= x1 + 1e-9:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (term - x0) / (x1 - x0)
    return pts[-1][1]


def parse_rate_terms(raw):
    """'1,2,5.5' -> [1.0, 2.0, 5.5]: только числа в 0.25..30, без повторов, по возрастанию, не больше 6; по умолчанию [2.0]."""
    out = set()
    for x in str(raw or "").replace(";", ",").split(","):
        try:
            t = round(float(x.strip().replace(",", ".")), 2)
        except ValueError:
            continue
        if RATE_TERM_MIN <= t <= RATE_TERM_MAX:
            out.add(t)
    return sorted(out)[:RATE_TERMS_MAX] or [2.0]


def key_rate_series():
    st = store()
    hit = st.get(KEY_KEY, ttl=6 * 3600)
    if hit:
        return hit
    frm = (date.today() - timedelta(days=900)).strftime("%d.%m.%Y")
    to = date.today().strftime("%d.%m.%Y")
    try:
        s = http_text("https://www.cbr.ru/hd_base/KeyRate/?UniDbQuery.Posted=True&UniDbQuery.From=%s&UniDbQuery.To=%s" % (frm, to))
    except Exception:  # noqa: BLE001
        old = st.get(KEY_KEY)          # сайт ЦБ недоступен — последний сохранённый ряд лучше, чем ошибка на каждом экране
        if old:
            return old
        raise
    rows = []
    for d, v in re.findall(r"<td>(\d\d\.\d\d\.\d{4})</td>\s*<td>([\d,]+)</td>", s):
        rows.append([datetime.strptime(d, "%d.%m.%Y").date().isoformat(), float(v.replace(",", "."))])
    rows.sort()
    if rows:
        st.put(KEY_KEY, rows)
    return rows


def _kbd_one(d):
    j = json.loads(http_text("https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields&date=" + d))
    g = {str(float(r[2])): r[3] for r in j["yearyields"]["data"] if r[3] is not None}
    return d, (g or None)


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
        _rates_state["ended"] = time.time()
        _rates_state["running"] = False


def _safe(fn, x):
    try:
        return fn(x)
    except Exception:  # noqa: BLE001
        return None, None


def rates_start(days):
    with _rt_lock:
        # недокачанные дни (сбой ISS, праздники) повторяем не чаще раза в 10 минут — иначе экран вечно «загружается»
        if _rates_state["running"] or time.time() - _rates_state["ended"] < 600:
            return
        _rates_state["running"] = True
    threading.Thread(target=_rates_run, args=(days,), daemon=True).start()


def rates_payload(days, terms=None):
    days = max(30, min(int(days or 365), 900))
    tl = terms if isinstance(terms, list) else parse_rate_terms(terms)
    st = store()
    cache = st.get(KBD_KEY) or {}
    old = st.get(KBD_OLD_KEY) or {}
    today = date.today()
    first = (today - timedelta(days=days)).isoformat()
    # сегодняшняя КБД появляется только после расчёта биржей — её отсутствие не считаем недокачкой
    miss = sum(1 for i in range(1, days + 1) if (today - timedelta(days=i)).weekday() < 5
               and (today - timedelta(days=i)).isoformat() not in cache)
    if today.weekday() < 5 and today.isoformat() not in cache:
        rates_start(days)
    if miss > 0:
        rates_start(days)
    try:
        keys = key_rate_series()
    except Exception:  # noqa: BLE001
        keys = st.get(KEY_KEY) or []
    grids = {}
    for d in set(cache) | set(old):
        if d < first:
            continue
        g = cache.get(d)
        if g:
            grids[d] = g
        elif d not in cache and old.get(d) is not None:
            grids[d] = {"2.0": old[d]}      # запас до докачки v2: только срок 2 года
    iso = sorted(grids)
    kbd = {("%g" % t): [] for t in tl}
    key, ki, last = [], 0, None
    for d in iso:
        while ki < len(keys) and keys[ki][0] <= d:
            last = keys[ki][1]
            ki += 1
        for t in tl:
            v = kbd_interp(grids[d], t)
            kbd["%g" % t].append(round(v, 2) if v is not None else None)
        key.append(last)
    return {"iso": iso, "labels": [datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y") for d in iso],
            "kbd": kbd, "terms": tl, "key": key, "loading": _rates_state["running"] or (miss > 0 and not _rates_state["ended"]),
            "keys": [k for k in keys if k[0] >= first], "next_cbr": _next_cbr_safe()}


def _next_cbr_safe():
    """Ближайшее заседание ЦБ для экрана «Ставки»; без сети — None (экран не должен падать из-за календаря ЦБ)."""
    fn = globals().get("cbr_next_meeting")
    try:
        return fn(wait=False) if fn else None
    except Exception:  # noqa: BLE001
        return None




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
