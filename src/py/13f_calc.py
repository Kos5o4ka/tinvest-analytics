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


# ═══════════════════ цель по пассивному доходу: сколько капитала и какое пополнение нужны ═══════════════════
# Упрощённая модель: весь капитал приносит доход по одной ставке, налог 13 % удерживается с дохода (реинвестируется остаток),
# взносы вносятся в конце каждого месяца и не индексируются. Не прогноз и не рекомендация.

GOAL_TAX = 0.13
GOAL_MAX_YEARS = 50


def goal_calc(monthly, months, yield_pct, value=0.0, infl_pct=0.0, real=False, income_now=None, tax=GOAL_TAX):
    """monthly — желаемый доход в месяц после налога, ₽; months — срок; yield_pct — доходность портфеля до налога, % годовых;
    value — текущий капитал; infl_pct — инфляция, % в год; real=True — цель задана в сегодняшних деньгах (к дате цели её нужно умножить на инфляцию).
    income_now — текущий доход в месяц (купоны и дивиденды) для оценки покрытия. Возвращает словарь с результатами."""
    monthly, value, months = max(0.0, float(monthly)), max(0.0, float(value)), int(months)
    if months < 1 or months > GOAL_MAX_YEARS * 12:
        raise ValueError("срок должен быть от 1 месяца до %d лет" % GOAL_MAX_YEARS)
    if not (0 < yield_pct < 100):
        raise ValueError("доходность должна быть больше 0 и меньше 100 %")
    y_net = yield_pct / 100.0 * (1.0 - tax)
    infl = infl_pct / 100.0 if real else 0.0
    f_inf = (1.0 + infl) ** (months / 12.0)
    goal_end = monthly * f_inf                         # желаемый доход в месяц в рублях на дату цели
    cap_today = monthly * 12.0 / y_net                # капитал, который даёт цель в сегодняшних ценах
    cap_end = goal_end * 12.0 / y_net                 # капитал на дату цели с учётом инфляции цели
    r = (1.0 + y_net) ** (1.0 / 12.0) - 1.0           # месячная ставка после налога с реинвестированием
    g = (1.0 + r) ** months
    grown = value * g
    need = max(0.0, cap_end - grown)
    contrib = need * r / (g - 1.0) if need > 0 else 0.0
    fv = lambda k, c: value * (1.0 + r) ** k + c * (((1.0 + r) ** k - 1.0) / r)
    step = 1 if months <= 60 else 3 if months <= 180 else 6
    ks = list(range(0, months + 1, step))
    if ks[-1] != months:
        ks.append(months)
    today = date.today()
    labels = []
    for k in ks:
        mm = today.month - 1 + k
        labels.append("%04d-%02d" % (today.year + mm // 12, mm % 12 + 1))
    out = {"months": months, "yield_net": round(y_net * 100.0, 3), "capital_today": cap_today, "capital_end": cap_end, "goal_end": goal_end,
           "inflation_factor": f_inf, "value": value, "value_grown": grown, "contribution": contrib, "contribution_total": contrib * months,
           "reached": need <= 0, "gap": need,
           "chart": {"labels": labels, "capital": [fv(k, contrib) for k in ks], "no_contrib": [fv(k, 0.0) for k in ks],
                     "target": [cap_today * (1.0 + infl) ** (k / 12.0) for k in ks]},
           "income_from_value": value * y_net / 12.0}
    if income_now is not None:
        out["coverage"] = {"income": income_now, "pct": (income_now / monthly * 100.0) if monthly > 0 else None}
    return out


def goal_months(q, today=None):
    """Срок в месяцах из параметров: date=ГГГГ-ММ-ДД или years (допустимы дробные)."""
    today = today or date.today()
    d = (q.get("date") or "").strip()
    if d:
        t = datetime.strptime(d, "%Y-%m-%d").date()
        if t <= today:
            raise ValueError("дата цели должна быть в будущем")
        return max(1, int(round((t - today).days / 30.4375)))
    return max(1, int(round(float(q.get("years") or 10) * 12)))


def _goal_float(q, k):
    v = (q.get(k) or "").strip().replace(",", ".")
    return float(v) if v != "" else None


def _goal_infl():
    hit = _calc_mem.get("goal_infl")
    if hit and time.time() - hit[0] < CALC_TTL:
        return hit[1]
    v = {"value": 4.0, "estimate": True, "source": "условное значение"}
    try:
        i = inflation_forecast()
        if i.get("source") != "none" and i.get("yearly"):
            v = {"value": i["yearly"][-1]["mid"], "estimate": False, "source": "прогноз Банка России"}
    except Exception:  # noqa: BLE001
        pass
    _calc_mem["goal_infl"] = (time.time(), v)
    return v


def goal_defaults(cfg, acc):
    """Что известно о портфеле: стоимость, средневзвешенная доходность облигаций, текущий доход в месяц (купоны и дивиденды за 12 мес.)."""
    d = {"value": None, "yield": None, "income_month": None, "income_src": None, "portfolio": False}
    if not cfg.get("token"):
        return d
    key = ("goal_pf", token_key(cfg), acc)
    hit = _calc_mem.get(key)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    try:
        pf = _calc_portfolio(cfg, acc)
    except Exception:  # noqa: BLE001
        pf = None
    if pf:
        d["portfolio"] = True
        d["value"] = pf.get("value")
        d["yield"] = pf.get("irr")
        if pf.get("coupons_12m"):
            d["income_month"], d["income_src"] = round(pf["coupons_12m"] / 12.0, 2), "купоны облигаций за 12 месяцев"
    try:
        end = (date.today() + timedelta(days=365)).isoformat()
        pays = [p for p in (build_bonds(cfg, acc).get("payments") or []) if p.get("kind") in ("coupon", "dividend") and p.get("date", "") <= end]
        if pays:
            d["income_month"], d["income_src"] = round(sum(p["amount"] for p in pays) / 12.0, 2), "купоны и дивиденды по графику на 12 месяцев"
    except Exception:  # noqa: BLE001
        pass
    _calc_mem[key] = (time.time(), d)
    return d


def calc_goal_get(cfg, acc, q, force=False):
    """GET /api/calc/goal?monthly=&years=|date=&yield=&value=&real=1&infl=  Ручные значения важнее данных портфеля; без токена работают только они."""
    out = {"defaults": goal_defaults(cfg, acc), "infl": _goal_infl(), "tax": GOAL_TAX, "result": None, "error": None}
    try:
        monthly = _goal_float(q, "monthly")
        if monthly is None or monthly <= 0:
            return out
        dfl = out["defaults"]
        y = _goal_float(q, "yield")
        y = dfl["yield"] if y is None else y
        if y is None:
            out["error"] = "Укажите ожидаемую доходность портфеля: данных по облигациям портфеля нет."
            return out
        v = _goal_float(q, "value")
        v = (dfl["value"] or 0.0) if v is None else v
        i = _goal_float(q, "infl")
        i = out["infl"]["value"] if i is None else i
        inc = _goal_float(q, "income")
        if inc is None:
            inc = dfl["income_month"] if dfl["income_month"] is not None else (v * y / 100.0 * (1 - GOAL_TAX) / 12.0 if v else None)
        real = (q.get("real") or "1") not in ("0", "false", "")
        out["result"] = goal_calc(monthly, goal_months(q), y, v, i, real, inc)
        out["result"].update(yield_pct=y, infl_pct=i, real=real, monthly=monthly)
    except (ValueError, TypeError) as e:
        out["error"] = str(e)
    return out


API_GET["/api/calc/goal"] = calc_goal_get
