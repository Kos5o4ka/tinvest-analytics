
# ═══════════════════ сигналы: дороже/дешевле аналогов по всему рынку, история, возможные замены ═══════════════════

SIG_TTL = 900
SIG_HIST_KEY = "sig_hist_v1"
SIG_HIST_DAYS = 120
SIG_EPS = 0.25           # |diff| (п.п.) от которого выпуск считается «дешевле/дороже» аналогов
SIG_OUTLIER = 8.0        # |diff| больше этого, доходность выше SIG_MAX_YIELD или спред < -6: вероятно дефолтный/«битый» выпуск
SIG_MAX_YIELD = 40.0
SIG_MAX_GAIN = 8.0       # разницу доходности больше этого в замены не берём: это уже разница в риске, а не «недооценка»
SIG_MIN_SIGMA = 0.4      # нижняя граница разброса аналогов (п.п.) для z-оценки
_sig = {"t": 0, "rows": [], "meta": {}}
_sig_lock = threading.Lock()
_sig_hist = {"t": 0, "d": None}


def _sig_pool(uni):
    """Выпуски, участвующие в сравнении: рублёвые корпоративные с рейтингом, без флоатеров и бессрочных."""
    out = []
    for e in uni:
        if e["kind"] != "corp" or e["cur"] != "RUB" or not (0 < e["yield"] < 60) or not e.get("dur") or e["dur"] < 0.1:
            continue
        if not e["_rt"] or e.get("spread") is None:
            continue
        ci = e["_ci"] or {}
        if ci.get("floating") or ci.get("perpetual"):
            continue
        out.append(e)
    return out


def _sig_index(pool):
    """Индексы для быстрого перебора кандидатов: по индексу рейтинга, отсортировано по дюрации."""
    by = defaultdict(list)
    for e in pool:
        by[RATING_SCALE.index(e["_rt"]["v"])].append(e)
    idx = {}
    for ri, lst in by.items():
        lst.sort(key=lambda e: e["dur"])
        idx[ri] = (lst, [e["dur"] for e in lst])
    return idx


def _sig_cands(me, ri, idx, rng=2):
    """Кандидаты в аналоги (до применения _bc_cost): рейтинг ±rng ступеней и дюрация в допустимом окне."""
    d = me["dur"]
    lo, hi = d * 0.4, d * 2.5
    for r in range(ri - rng, ri + rng + 1):
        it = idx.get(r)
        if not it:
            continue
        lst, durs = it
        for e in lst[bisect.bisect_left(durs, lo):bisect.bisect_right(durs, hi)]:
            yield e


def _sig_nearest(me, ri, idx, isin_skip=None):
    """Ближайшие аналоги так же, как в карточке: 30 лучших -> отсев выбросов по спреду -> 12 лучших. Возвращает [(cost, e)]."""
    sc = []
    for e in _sig_cands(me, ri, idx):
        if e is me or e["_isin"] == isin_skip:
            continue
        c = _bc_cost(me, e, ri)
        if c is not None:
            sc.append((c, e["_isin"], e))
    sc.sort(key=lambda x: (x[0], x[1]))
    sps = sorted(x[2]["spread"] for x in sc[:30])
    if len(sps) >= 5:
        m0 = sps[len(sps) // 2]
        sc = [x for x in sc if abs(x[2]["spread"] - m0) <= 8]
    return [(c, e) for c, _, e in sc[:12]]


def _sig_median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _sig_row(e, near):
    sp = [a["spread"] for _, a in near]
    med = _sig_median(sp)
    mad = _sig_median([abs(x - med) for x in sp]) * 1.4826
    diff = e["spread"] - med
    ci, rt = e["_ci"] or {}, e["_rt"]
    return {"isin": e["_isin"], "id": e["id"], "name": e["name"], "rating": rt["v"], "rating_approx": bool(rt.get("approx")),
            "sector": ci.get("sector"), "yield": e["yield"], "spread": e["spread"], "dur": e["dur"], "price": e.get("price"),
            "mat": e.get("mat"), "med": round(med, 2), "diff": round(diff, 2), "sigma": round(max(mad, SIG_MIN_SIGMA), 2),
            "z": round(diff / max(mad, SIG_MIN_SIGMA), 2), "n": len(sp), "turn": e.get("turn") or 0, "trades": e.get("trades") or 0,
            "amort": bool(ci.get("amort")), "sub": bool(ci.get("subordinated")),
            "outlier": bool(abs(diff) > SIG_OUTLIER or e["yield"] > SIG_MAX_YIELD or e["spread"] < -6),
            "refs": [{"isin": a["_isin"], "name": a["name"], "spread": a["spread"]} for _, a in near[:3]]}


def _sig_hist_load():
    if _sig_hist["d"] is None or time.time() - _sig_hist["t"] > 60:
        _sig_hist["d"] = store().get(SIG_HIST_KEY) or {}
        _sig_hist["t"] = time.time()
    return _sig_hist["d"]


def _sig_snapshot(rows):
    """Сохраняет сегодняшний снимок diff (по будням; ликвидные выпуски), хранит SIG_HIST_DAYS последних дней."""
    h = _sig_hist_load()
    today = date.today()
    if today.weekday() < 5 and rows:
        h[today.isoformat()] = {r["isin"]: r["diff"] for r in rows if r["turn"] >= 2e5}
        for d in sorted(h)[:-SIG_HIST_DAYS]:
            h.pop(d, None)
        try:
            store().put(SIG_HIST_KEY, h)
        except Exception:  # noqa: BLE001
            pass
    return h


def _sig_streak(h, isin, diff):
    """Сколько последних снимков подряд знак и величина diff те же (дешевле/дороже). Возвращает (streak, series[старые..новые])."""
    days = sorted(h)
    ser = [h[d].get(isin) for d in days]
    sgn = 1 if diff >= SIG_EPS else -1 if diff <= -SIG_EPS else 0
    n = 0
    if sgn:
        for v in reversed(ser):
            if v is not None and v * sgn >= SIG_EPS:
                n += 1
            else:
                break
    return n, ser


def _sig_all(force=False):
    """Полный расчёт сигналов по рынку; кэш 15 минут. Возвращает (rows, meta)."""
    if not force and time.time() - _sig["t"] < SIG_TTL and _sig["rows"]:
        return _sig["rows"], _sig["meta"]
    with _sig_lock:
        if not force and time.time() - _sig["t"] < SIG_TTL and _sig["rows"]:
            return _sig["rows"], _sig["meta"]
        t0 = time.time()
        uni = _bc_universe()
        pool = _sig_pool(uni)
        idx = _sig_index(pool)
        rows = []
        for e in pool:
            near = _sig_nearest(e, RATING_SCALE.index(e["_rt"]["v"]), idx)
            if len(near) >= 5:
                rows.append(_sig_row(e, near))
        h = _sig_snapshot(rows)
        days = sorted(h)
        for r in rows:
            n, ser = _sig_streak(h, r["isin"], r["diff"])
            r["streak"] = n
            vals = [v for v in ser if v is not None]
            r["trend"] = round(r["diff"] - vals[-6], 2) if len(vals) >= 6 else (round(r["diff"] - vals[0], 2) if len(vals) >= 2 else None)
            r["hist"] = vals[-30:] if abs(r["z"]) >= 1 and len(vals) >= 2 else None
        meta = {"pool": len(pool), "scored": len(rows), "hist_days": len(days), "hist_from": days[0] if days else None,
                "calc_s": round(time.time() - t0, 2), "updated": time.time()}
        _sig.update(t=time.time(), rows=rows, meta=meta)
        return rows, meta


def _sig_replacements(cfg, acc, pool_idx, rows_by_isin, fee, thr, min_turn, tax_rate):
    """Для каждой облигации портфеля: возможные замены с большей доходностью (по рыночной доходности) с учётом издержек."""
    try:
        pf = build_bonds(cfg, acc, False)["rows"]
    except Exception:  # noqa: BLE001
        return [], []
    uni = {}
    for e in _bc_universe():
        uni[e["_isin"]] = e
        uni[e["id"]] = e
    pool, idx = pool_idx
    held = {r.get("ticker") for r in pf}
    out, skipped = [], []
    for r in pf:
        isin = r.get("ticker")
        V = r.get("value_rub") or 0
        base = {"isin": isin, "name": r.get("name"), "qty": r.get("qty"), "value": round(V, 2), "rating": (r.get("rating") or {}).get("v")}
        me = uni.get(isin)
        if not me or V <= 0 or r.get("cur") not in (None, "rub", "RUB"):
            skipped.append(dict(base, why="нет рыночных данных или не рублёвая"))
            continue
        if me["kind"] != "corp":
            skipped.append(dict(base, why="ОФЗ: сравнение не применяется"))
            continue
        ci = me["_ci"] or {}
        if ci.get("floating") or r.get("floating"):
            skipped.append(dict(base, why="флоатер: спред к КБД не сопоставим"))
            continue
        if not me["_rt"]:
            skipped.append(dict(base, why="нет рейтинга"))
            continue
        ri = RATING_SCALE.index(me["_rt"]["v"])
        y0 = me["yield"]
        mine_sig = rows_by_isin.get(me["_isin"])
        if not mine_sig or mine_sig["outlier"]:
            skipped.append(dict(base, why="нет надёжного сравнения с аналогами (нет спреда или аномальные данные)"))
            continue
        cands = []
        for t in _sig_cands(me, ri, idx):
            if t is me or t["_isin"] in held or t["yield"] <= y0 or (t.get("turn") or 0) < min_turn:
                continue
            c = _bc_cost(me, t, ri)
            if c is None or c > 2.5 or abs(t["dur"] - me["dur"]) / max(t["dur"], me["dur"], 0.5) > 0.35:
                continue
            cands.append((c, t))
        # потолок доходности: цель не должна быть выбросом относительно собственных аналогов
        price, buy, nom, qty = r.get("price_pct"), r.get("buy_pct"), r.get("nominal") or 1000.0, r.get("qty") or 0
        tax = 0.0
        if price and buy and price > buy:
            tax = tax_rate * (price - buy) / 100.0 * nom * qty
        cost_rub = 2 * fee * V + tax
        opts = []
        for c, t in cands:
            tr = rows_by_isin.get(t["_isin"])
            if tr is None or tr["n"] < 5:
                continue
            if tr["outlier"]:
                continue
            gain = t["yield"] - y0
            if gain > SIG_MAX_GAIN:
                continue
            hz = min(5.0, max(0.5, min(me["dur"], t["dur"])))
            net = gain - cost_rub / V * 100.0 / hz
            rt_i = RATING_SCALE.index(t["_rt"]["v"])
            gain_rub = V * gain / 100.0
            opts.append({"isin": t["_isin"], "name": t["name"], "rating": t["_rt"]["v"], "rating_worse": rt_i > ri,
                         "rating_better": rt_i < ri, "sector": (t["_ci"] or {}).get("sector"), "yield": t["yield"], "dur": t["dur"],
                         "spread": t["spread"], "turn": t.get("turn") or 0, "trades": t.get("trades") or 0, "mat": t.get("mat"),
                         "diff": tr["diff"], "z": tr["z"], "gain_pp": round(gain, 2), "net_pp": round(net, 2),
                         "gain_rub_year": round(gain_rub), "net_rub_year": round(V * net / 100.0),
                         "breakeven_months": round(cost_rub / gain_rub * 12, 1) if gain_rub > 0 else None, "horizon": round(hz, 1)})
        opts = [o for o in opts if o["net_pp"] >= thr]
        opts.sort(key=lambda o: -o["net_pp"])
        better = [o for o in opts if not o["rating_worse"]][:3]
        worse = [o for o in opts if o["rating_worse"]][:2]
        if better or worse:
            out.append(dict(base, yield_=y0, dur=me["dur"], spread=me["spread"], price_pct=price, buy_pct=buy, sector=ci.get("sector"),
                            turn=me.get("turn") or 0, diff=mine_sig["diff"] if mine_sig else None, z=mine_sig["z"] if mine_sig else None,
                            cost_rub=round(cost_rub), commission_rub=round(2 * fee * V), tax_rub=round(tax),
                            cost_pp=round(cost_rub / V * 100, 2), options=better, options_worse=worse))
    out.sort(key=lambda x: -((x["options"] or x["options_worse"])[0]["net_rub_year"]))
    return out, skipped


def signals_payload(cfg, acc, q=None):
    q = q or {}

    def num(k, d, lo, hi):
        try:
            return min(hi, max(lo, float(q.get(k, d))))
        except (TypeError, ValueError):
            return d
    min_turn = num("min_turn", 1e6, 0, 1e10)
    fee = num("fee", 0.3, 0, 5) / 100.0
    thr = num("threshold", 1.0, 0, 20)
    tax_rate = num("tax", 13, 0, 50) / 100.0
    rows, meta = _sig_all(q.get("force") == "1")
    liquid = [r for r in rows if r["turn"] >= min_turn]
    n_out = sum(1 for r in liquid if r["outlier"])
    liquid_ok = [r for r in liquid if not r["outlier"]]
    uni = _bc_universe()
    pool = _sig_pool(uni)
    by = {r["isin"]: r for r in rows}
    repl, skipped = _sig_replacements(cfg, acc, (pool, _sig_index(pool)), by, fee, thr, min_turn, tax_rate)
    cheap = sorted((r for r in liquid_ok if r["diff"] >= SIG_EPS), key=lambda r: -r["z"])
    rich = sorted((r for r in liquid_ok if r["diff"] <= -SIG_EPS), key=lambda r: r["z"])
    outl = [r for r in liquid if r["outlier"]]
    keep = {r["isin"] for r in cheap[:150]} | {r["isin"] for r in rich[:150]} | {r["isin"] for r in outl[:60]}
    return {"rows": [r for r in liquid if r["isin"] in keep],
            "kpis": {"universe": len(liquid), "outliers": n_out, "cheap": len(cheap), "rich": len(rich),
                     "cheap_strong": sum(1 for r in cheap if r["z"] >= 2), "rich_strong": sum(1 for r in rich if r["z"] <= -2),
                     "med_diff": round(_sig_median([r["diff"] for r in liquid_ok]), 2) if liquid_ok else None},
            "meta": meta, "params": {"min_turn": min_turn, "fee": fee * 100, "threshold": thr, "tax": tax_rate * 100},
            "replacements": repl, "skipped": skipped, "eps": SIG_EPS}
