# ═══════════════════ риски и сценарии: рыночная вероятность дефолта, ожидаемая доходность, сценарии ключевой ставки ═══════════════════
# Упрощённая модель, справочная информация. Все допущения перечислены в RISK_NOTES и отдаются в UI.

RISK_RECOVERY = 25.0       # допущение о доле возврата при дефолте, % (по умолчанию)
# Историческая однолетняя вероятность дефолта по рейтингу национальной шкалы, %. Опорные точки:
#  - Московская биржа, «О чём говорят кредитные рейтинги» (частоты дефолтов 2002-2022, горизонт 1 год):
#    AA 0,23; A 0,75; BBB 1,87; BB 3,88;
#  - Эксперт РА, «Матрица дефолтов» (январь 2026, 1 год): BBB 1,57; BB 4,27; B 5,5; CCC 13,64; CC 28,57; C 100.
# Значения по подкатегориям (+/-) интерполированы вручную, AAA и AA+ — экспертная оценка (дефолтов в этих классах практически не было).
RISK_PD_HIST = {"AAA": 0.05, "AA+": 0.10, "AA": 0.20, "AA-": 0.30, "A+": 0.50, "A": 0.75, "A-": 1.10, "BBB+": 1.40,
                "BBB": 1.70, "BBB-": 2.30, "BB+": 3.20, "BB": 4.00, "BB-": 4.80, "B+": 5.20, "B": 5.50, "B-": 8.00,
                "CCC": 13.6, "CC": 28.6, "C": 60.0, "D": 100.0}
RISK_PD_SRC = ("Исследования дефолтов: Московская биржа («О чём говорят кредитные рейтинги», частоты дефолтов 2002-2022) "
               "и Эксперт РА («Матрица дефолтов», 2026). Подкатегории интерполированы; значения приблизительные.")
RISK_REC_SRC = ("Доля возврата для российских корпоративных облигаций в научных оценках (напр. Е. Антонова, НИУ ВШЭ, "
               "«Корпоративные финансы» 2012, данные Cbonds) обычно лежит в диапазоне 20-40 %, зависит от обеспечения и "
               "очереди требований. 25 % — рабочее допущение; меняется параметром.")
RISK_FIX_RATES = (10.0, 18.0)
RISK_BETA = ((1.0, 1.0), (7.0, 0.5))      # (срок, лет; бета): до 1 года 1,0, далее линейно до 0,5 на 7 годах и дальше


def _rexp(x):
    return 2.718281828459045 ** x


def risk_beta(t):
    (t0, b0), (t1, b1) = RISK_BETA
    if t is None or t <= t0:
        return b0
    if t >= t1:
        return b1
    return b0 + (b1 - b0) * (t - t0) / (t1 - t0)


def _risk_path(k0, target, today):
    """Путь ставки: линейно от k0 до target за 12 месяцев, далее ровно. [(дата, %)] помесячно на 4 года."""
    out = []
    t0 = datetime.strptime(today, "%Y-%m-%d")
    for m in range(0, 49):
        d = (t0 + timedelta(days=round(m * 30.4375))).strftime("%Y-%m-%d")
        out.append((d, k0 + (target - k0) * min(m, 12) / 12.0))
    return out


def _risk_unit(b, today, hd, scn_paths, def_path, tax):
    """Результат за 12 месяцев на 1 рубль стоимости по каждому сценарию. b: {flows, y, floating, bz, face, dirty, est, ...}.
    Возвращает {ключ сценария: (купоны, цена+прочее)} в долях от текущей полной стоимости (с НКД)."""
    out = {}
    for key, sc in scn_paths.items():
        flows = b["flows"]
        if b["floating"] and b["est"]:
            e2 = fl_estimates(b["bz"], today, b["face"], sc["path"])
            flows = [(d, e2[d]["amt"] if d in b["est"] and d in e2 else c, p) for d, c, p in flows]
        out[key] = _risk_eval(b, flows, today, hd, sc, def_path, tax)
    return out


def _risk_rem(flows, hd):
    return [f for f in flows if f[0] > hd]


def _risk_eval(b, flows, today, hd, sc, def_path, tax, dy_extra=None):
    y0 = b["y"]
    rem = _risk_rem(flows, hd)
    cash = [f for f in flows if today < f[0] <= hd]
    cpn = sum(c for _, c, _ in cash)
    prin = sum(p for _, _, p in cash)
    if dy_extra is not None:
        dy = dy_extra
    elif not rem:
        dy = 0.0
    elif b["floating"] and b["est"]:
        ds = [d for d, _, _ in rem]
        dy = sum(keyrate_at(sc["path"], d) - keyrate_at(def_path, d) for d in ds) / len(ds) / 100.0
    else:
        mac, _, _ = cf_risk(rem, hd, y0)
        dy = risk_beta(mac) * sc["delta"] / 100.0
    pv = _bc_pv(rem, hd, max(y0 + dy, -0.9)) if rem else 0.0
    price = pv + prin - b["dirty"]
    if tax:
        cpn *= (1 - BC_TAX)
        if price > 0:
            price *= (1 - BC_TAX)
    return cpn / b["dirty"], price / b["dirty"]


def _risk_breakeven(b, flows, today, hd, sc, tax):
    """Рост доходности (п.п.), при котором результат за 12 месяцев (купоны + цена) обнуляется; None, если > 30 п.п."""
    f = lambda dy: sum(_risk_eval(b, flows, today, hd, sc, None, tax, dy_extra=dy))
    if f(0.0) <= 0:
        return 0.0
    if f(0.30) > 0:
        return None
    lo, hi = 0.0, 0.30
    for _ in range(50):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2 * 100.0


def _risk_scenarios(target, today):
    info = keyrate_forecast_info()
    try:
        minfo = keyrate_forecast_info("market")
    except Exception:  # noqa: BLE001
        minfo = None
    k0 = info.get("key_rate")
    if k0 is None and info.get("path"):
        k0 = info["path"][0][1]
    if k0 is None:
        raise ApiError("Нет данных о ключевой ставке.", 502)
    hd = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")
    sc = []

    def add(key, name, path, note=""):
        sc.append({"key": key, "name": name, "path": path, "k12": keyrate_at(path, hd), "note": note})
    if info.get("path"):
        add("cbr", "Прогноз ЦБ", info["path"], info.get("source_name") or "")
    if minfo and minfo.get("path") and minfo.get("source") == "market":
        add("market", "Рынок", minfo["path"], minfo.get("source_name") or "")
    add("hold", "Ставка без изменений", _risk_path(k0, k0, today))
    for r in RISK_FIX_RATES:
        add("fix%d" % r, "Ставка %d %%" % r, _risk_path(k0, r, today))
    if target is not None:
        add("target", "Своя ставка %s %%" % (("%g" % target).replace(".", ",")), _risk_path(k0, target, today))
    for s in sc:
        s["delta"] = s["k12"] - k0
    return k0, hd, sc, (info.get("path") or _risk_path(k0, k0, today))


def _fnum(x, lo, hi, dflt):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return dflt
    return v if lo <= v <= hi else dflt


def build_risk(cfg, acc, q=None):
    q = q or {}
    rec = _fnum(q.get("recovery"), 0.0, 90.0, RISK_RECOVERY)
    target = _fnum(q.get("target"), 0.0, 60.0, None) if q.get("target") not in (None, "") else None
    tax = q.get("tax") == "1"
    key = ("risk", token_key(cfg), acc, rec, target, tax)
    hit = mem_get(key, 300)
    if hit:
        return hit
    rep = build_bonds(cfg, acc)
    today = date.today().isoformat()
    k0, hd, scs, def_path = _risk_scenarios(target, today)
    R = rec / 100.0
    rows, units = [], []
    for r in rep["rows"]:
        if r.get("ytm") is None or not r.get("value_rub"):
            continue
        v = r["value_rub"]
        isin = r.get("isin") or r.get("ticker") or ""
        end = r.get("end") or r.get("maturity") or ""
        T = max((datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days / 365.0, 0.02) if end else None
        sp = r.get("spread")
        lam = max(sp, 0.0) / 100.0 / (1 - R) if sp is not None else None
        pd1 = 1 - _rexp(-lam * min(1.0, T)) if lam is not None and T else None
        pdT = 1 - _rexp(-lam * T) if lam is not None and T else None
        rt = (r.get("rating") or {}).get("v")
        ph = RISK_PD_HIST.get(rt) / 100.0 if rt in RISK_PD_HIST else None
        ratio = pd1 / ph if pd1 is not None and ph else None
        basis_pd = ph if ph is not None else pd1            # без рейтинга — берём рыночную оценку
        el_pct = (basis_pd or 0.0) * (1 - R) * 100.0
        row = {"isin": isin, "name": r["name"], "ticker": r.get("ticker"), "uid": r.get("uid"), "value_rub": v,
               "share": r.get("share"), "rating": r.get("rating"), "ytm": r["ytm"], "spread": sp, "dur": r.get("dur"),
               "mdur": r.get("mdur"), "floating": bool(r.get("floating")), "years": T,
               "pd_mkt_1y": pd1, "pd_mkt_T": pdT, "pd_hist_1y": ph, "ratio": ratio,
               "ey_hist": r["ytm"] - el_pct, "ey_mkt": r["ytm"] - (pd1 or 0.0) * (1 - R) * 100.0,
               "hist_basis": "rating" if ph is not None else "market", "exact": r.get("cf_source") == "moex", "scn": {}}
        # потоки для переоценки
        flows, est, bz, face = None, {}, None, r.get("nominal") or 1000.0
        if row["exact"]:
            try:
                bz = moex_bondization(isin)
                flows, kind, _e = bond_flows(bz, today, face, floating=bool(r.get("floating")), est_out=est) if bz else (None, None, None)
            except Exception:  # noqa: BLE001
                flows = None
        if flows:
            y0 = r["ytm"] / 100.0
            dirty = _bc_pv([f for f in flows if f[0] > today], today, y0)
            if dirty and dirty > 0:
                b = {"flows": flows, "y": y0, "floating": bool(r.get("floating")), "bz": bz, "face": face, "dirty": dirty, "est": est}
                for k, (c, p) in _risk_unit(b, today, hd, {s["key"]: s for s in scs}, def_path, tax).items():
                    row["scn"][k] = {"coupons": c * v, "price": p * v, "total": (c + p) * v}
                hs = scs[[s["key"] for s in scs].index("hold")]
                be = _risk_breakeven(b, flows, today, hd, hs, tax)
                row["breakeven"] = be
                row["be_gt"] = be is None
        if not row["scn"]:
            # приближение: купоны ~ доходность, цена ~ -mdur x бета x сдвиг
            md = r.get("mdur") or 0.0
            for s in scs:
                dy = 0.0 if r.get("floating") else risk_beta(r.get("dur")) * s["delta"]
                c = v * r["ytm"] / 100.0 * ((1 - BC_TAX) if tax else 1)
                p = -md * dy / 100.0 * v
                row["scn"][s["key"]] = {"coupons": c, "price": p, "total": c + p}
            row["breakeven"] = r["ytm"] / md if md else None
            row["be_gt"] = False
        if "breakeven" not in row or row["breakeven"] is None:
            row.setdefault("breakeven", None)
        row["be_approx"] = r["ytm"] / row["mdur"] if row.get("mdur") else None
        rows.append(row)
    tot = sum(x["value_rub"] for x in rows) or 0.0
    out = {"account": acc, "recovery": rec, "tax": tax, "count": len(rows), "value": tot, "today": today, "horizon": hd,
           "key_rate": k0, "pd_hist_table": RISK_PD_HIST, "sources": {"pd": RISK_PD_SRC, "recovery": RISK_REC_SRC},
           "beta": [list(x) for x in RISK_BETA], "rows": rows,
           "scenarios": [{k: s[k] for k in ("key", "name", "k12", "delta", "note")} for s in scs]}
    if not tot:
        out.update(portfolio=None, scn_total=[], floaters={}, casino=[])
        return mem_put(key, out)
    wy = sum(x["ytm"] * x["value_rub"] for x in rows) / tot
    el_h = sum(x["value_rub"] * ((x["pd_hist_1y"] if x["pd_hist_1y"] is not None else (x["pd_mkt_1y"] or 0.0))) * (1 - R) for x in rows)
    el_m = sum(x["value_rub"] * (x["pd_mkt_1y"] or 0.0) * (1 - R) for x in rows)
    nd = [x for x in rows if x["ytm"] <= YTM_HIGH]
    wy_ex = sum(x["ytm"] * x["value_rub"] for x in nd) / sum(x["value_rub"] for x in nd) if nd else None
    out["portfolio"] = {"promised_ex": wy_ex, "distressed_value": tot - sum(x["value_rub"] for x in nd), "promised": wy, "expected": wy - el_h / tot * 100.0, "expected_mkt": wy - el_m / tot * 100.0,
                        "exp_loss_rub": el_h, "exp_loss_mkt_rub": el_m,
                        "unrated_value": sum(x["value_rub"] for x in rows if x["hist_basis"] != "rating"),
                        "approx_count": sum(1 for x in rows if not x["exact"])}
    # итоги по сценариям и группам
    def agg(sel):
        res = {}
        val = sum(x["value_rub"] for x in sel)
        for s in scs:
            c = sum(x["scn"][s["key"]]["coupons"] for x in sel)
            p = sum(x["scn"][s["key"]]["price"] for x in sel)
            res[s["key"]] = {"coupons": c, "price": p, "total": c + p, "pct": (c + p) / val * 100.0 if val else None}
        return res, val
    out["scn_total"], _ = agg(rows)
    fl, fx = [x for x in rows if x["floating"]], [x for x in rows if not x["floating"]]
    fa, fv = agg(fl)
    xa, xv = agg(fx)
    out["floaters"] = {"floating": {"value": fv, "count": len(fl), "scn": fa}, "fixed": {"value": xv, "count": len(fx), "scn": xa}}
    # «казино»: дефолт k самых рискованных эмитентов (по рыночной вероятности дефолта за год)
    base = out["scn_total"]["hold"]["total"]
    groups = {}
    for x in rows:
        g = groups.setdefault(x["name"].split(" ")[0].lower(), {"name": x["name"], "pd": 0.0, "value": 0.0, "ret": 0.0, "n": 0})
        g["pd"] = max(g["pd"], x["pd_mkt_1y"] or 0.0)
        g["value"] += x["value_rub"]
        g["ret"] += x["scn"]["hold"]["total"]
        g["n"] += 1
    ranked = sorted(groups.values(), key=lambda g: (-g["pd"], -g["value"]))
    casino = []
    for k in (1, 2, 3):
        pick = ranked[:k]
        if len(pick) < k:
            break
        res = base - sum(g["ret"] for g in pick) - sum(g["value"] * (1 - R) for g in pick)
        casino.append({"k": k, "issuers": [{"name": g["name"], "value": g["value"], "pd": g["pd"]} for g in pick],
                       "result_rub": res, "result_pct": res / tot * 100.0, "lost_rub": sum(g["value"] * (1 - R) for g in pick)})
    out["casino"] = casino
    out["base_rub"] = base
    return mem_put(key, out)
