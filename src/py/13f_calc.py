# ═══════════════════════════════ калькулятор инвестиций: параметры рынка ═══════════════════════════════

CALC_TTL = 3600
CALC_LOSS_GIVEN_DEFAULT = 0.75      # потери при дефолте: 1 − ставка возмещения 25 %
_calc_mem = {}


def _calc_med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _calc_segments(key_rate):
    """Сегменты рынка: ОФЗ, AAA, AA, A, ВДО — текущая медианная доходность и дюрация. Что не нашли — запасной вариант с флагом."""
    pd = RISK_PD_HIST
    loss = lambda *ks: sum(pd[k] for k in ks) / len(ks) / 100.0 * CALC_LOSS_GIVEN_DEFAULT
    # ожидаемые годовые потери: средняя вероятность дефолта по рейтингам сегмента × (1 − 0,25)
    meta = {"ofz": ("ОФЗ", 0.0), "aaa": ("Корпоративные AAA", loss("AAA")),
            "aa": ("Корпоративные AA", loss("AA+", "AA", "AA-")),
            "a": ("Корпоративные A", loss("A+", "A", "A-")),
            "hy": ("ВДО (BB и ниже)", loss("BB+", "BB", "BB-", "B+"))}
    fb = {"ofz": (key_rate - 0.5, 4.0), "aaa": (key_rate + 0.5, 2.5), "aa": (key_rate + 1.5, 2.5),
          "a": (key_rate + 3.0, 2.0), "hy": (key_rate + 8.0, 1.5)}
    got = {}
    try:
        sp = screener_payload()
        rows = sp.get("rows") or []
        buckets = {"aaa": "AAA", "aa": "AA", "a": "A", "hy": "BB и ниже"}
        for k, b in buckets.items():
            sel = [r for r in rows if r.get("kind") == "corp" and r.get("cur") == "RUB" and r.get("rating")
                   and rating_bucket(r["rating"]) == b and 0 < r["yield"] < 60 and (r.get("dur") or 0) > 0.1]
            if len(sel) >= 3:
                got[k] = (_calc_med([r["yield"] for r in sel]), _calc_med([r["dur"] for r in sel]), len(sel))
        sel = [r for r in rows if r.get("kind") == "ofz" and r.get("cur") == "RUB" and 0 < r["yield"] < 60
               and (r.get("dur") or 0) > 0.1 and not r.get("floating") and r.get("sub") != "ofz_floater"]
        if len(sel) >= 3:
            got["ofz"] = (_calc_med([r["yield"] for r in sel]), _calc_med([r["dur"] for r in sel]), len(sel))
    except Exception:  # noqa: BLE001
        pass
    out = {}
    for k, (name, ls) in meta.items():
        g = got.get(k)
        out[k] = {"name": name, "yield": round(g[0] if g else fb[k][0], 2), "dur": round(g[1] if g else fb[k][1], 2),
                  "loss": round(ls * 100, 3), "n": g[2] if g else 0, "estimate": g is None}
    return out


def _calc_portfolio(cfg, acc):
    if not cfg.get("token"):
        return None
    pf = {"value": None, "bonds_value": None, "irr": None, "irr_tax": None, "monthly": None, "coupons_12m": None}
    s = None
    try:
        s = build_summary(cfg, acc, "all")
        pf["value"] = round(s["portfolio"]["total"], 2)
        pf["bonds_value"] = round(s["portfolio"]["bonds"], 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        if s:
            lim = (date.today() - timedelta(days=365)).strftime("%Y-%m")
            net = 0.0
            for m, v in s.get("months") or []:
                if m >= lim:
                    net += (v.get("deposits") or 0.0) - (v.get("withdrawals") or 0.0)
            pf["monthly"] = round(max(net, 0.0) / 12.0, 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        m = build_bonds(cfg, acc).get("metrics") or {}
        irr = m.get("irr") if m.get("irr") is not None else m.get("ytm")
        if irr is not None:
            pf["irr"] = round(irr, 2)
        irt = m.get("irr_tax")
        if irt is not None:
            pf["irr_tax"] = round(irt, 2)
        pf["coupons_12m"] = round(m.get("coupons_12m") or 0.0, 2)
    except Exception:  # noqa: BLE001
        pass
    if all(pf[k] is None for k in ("value", "irr")):
        return None
    return pf


def calc_params(cfg, acc):
    key = (token_key(cfg), acc)
    hit = _calc_mem.get(key)
    if hit and time.time() - hit[0] < CALC_TTL:
        return hit[1]
    res = {"error": None}
    kr, path, kr_src, kr_est = None, [], "", True
    try:
        info = keyrate_forecast_info()
        kr = info.get("key_rate")
        path = [[p[0], p[1]] for p in info.get("path") or []]
        kr_src = info.get("source_name") or ""
        kr_est = info.get("source") == "none"
    except Exception:  # noqa: BLE001
        pass
    if kr is None:
        kr, kr_est = (path[0][1] if path else 16.0), True
        kr_src = kr_src or "нет данных (условное значение)"
    if not path:
        path = [[date.today().isoformat(), kr]]
    res["key_rate"] = {"current": kr, "source": kr_src, "estimate": kr_est, "path": path}
    infl = {"source": "none", "yearly": [], "estimate": True, "default": 4.0}
    try:
        i = inflation_forecast()
        if i.get("source") != "none" and i.get("yearly"):
            infl = {"source": i["source"], "as_of": i.get("as_of"), "yearly": [{"year": y["year"], "mid": y["mid"]} for y in i["yearly"]],
                    "estimate": False, "default": i["yearly"][-1]["mid"]}
    except Exception:  # noqa: BLE001
        pass
    res["inflation"] = infl
    segs = _calc_segments(kr)
    try:
        pf = _calc_portfolio(cfg, acc)
    except Exception:  # noqa: BLE001
        pf = None
    res["segments"] = segs
    ly, lest = None, True
    try:
        f = globals().get("bench_lqdt_yield")
        v = f() if f else None
        if isinstance(v, dict):
            v = v.get("yield")
        if v is not None and 0 < float(v) < 60:
            ly, lest = round(float(v), 2), False
    except Exception:  # noqa: BLE001
        pass
    if ly is None:
        ly = round(kr - 0.7, 2)
    res["lqdt"] = {"yield": ly, "estimate": lest, "spread": 0.7}
    res["deposit"] = {"spread": 1.5, "rate": round(max(kr - 1.5, 0.1), 2)}
    res["portfolio"] = pf
    res["updated"] = datetime.now().strftime("%H:%M")
    _calc_mem[key] = (time.time(), res)
    return res
