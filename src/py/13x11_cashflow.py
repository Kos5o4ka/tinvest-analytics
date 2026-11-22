
# ── Матрица денежных потоков на 36 месяцев и реинвестиционный симулятор ──

CF36_MONTHS = 36
CF36_DIV_TAX = 0.13          # дивиденды приходят за вычетом НДФЛ; ставка — как в «Дивидендной лаборатории» по умолчанию
CF36_KINDS = ("coupon", "dividend", "amortization", "redemption")


def cf36_month_keys(today=None, n=CF36_MONTHS):
    """n последовательных месяцев «ГГГГ-ММ», начиная с текущего."""
    t = today or date.today()
    y, m = t.year, t.month
    out = []
    for _ in range(n):
        out.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def cf36_horizon_days(today=None, n=CF36_MONTHS):
    """Дней от сегодня до конца n-го месяца (включительно)."""
    t = today or date.today()
    k = t.year * 12 + (t.month - 1) + n
    return (date(k // 12, k % 12 + 1, 1) - t).days - 1


def cf36_bucket(pays, today=None, n=CF36_MONTHS):
    """Выплаты [{date, kind, amount, est, name}] -> n помесячных строк (пустые месяцы — с нулями)."""
    keys = cf36_month_keys(today, n)
    rows = {k: {"ym": k, "total": 0.0, "by": dict((x, 0.0) for x in CF36_KINDS), "est": 0.0, "top": []} for k in keys}
    for p in pays or []:
        r = rows.get((p.get("date") or "")[:7])
        a = p.get("amount") or 0.0
        if r is None or a <= 0:
            continue
        kd = p.get("kind") if p.get("kind") in CF36_KINDS else "coupon"
        r["total"] += a
        r["by"][kd] += a
        if p.get("est"):
            r["est"] += a
        r["top"].append({"name": p.get("name") or p.get("ticker") or "", "kind": kd, "date": p.get("date"),
                         "amount": a, "est": bool(p.get("est"))})
    for r in rows.values():
        r["top"] = sorted(r["top"], key=lambda x: -x["amount"])[:3]
        r["total"] = round(r["total"], 2)
        r["est"] = round(r["est"], 2)
        r["by"] = dict((k, round(v, 2)) for k, v in r["by"].items())
    return [rows[k] for k in keys]


def cf36_est_dividends(shares, announced, cfg, today=None, n=CF36_MONTHS, tax=CF36_DIV_TAX):
    """Оценочные дивиденды сверх объявленных: по истории выплат за последние 12 месяцев (если их не было — за предыдущие 12)
    повторяем те же календарные месяцы каждый год с суммой на выплату x количество, за вычетом НДФЛ. Сбой по бумаге — без оценки."""
    t = today or date.today()
    ti = t.isoformat()
    keys = set(cf36_month_keys(t, n))
    d1, d2, d3 = [(t - timedelta(days=k)).isoformat() for k in (365, 730, 1095)]
    ann = defaultdict(list)
    for p in announced or []:
        if p.get("kind") == "dividend":
            ann[p.get("ticker")].append(p["date"][:7])
    out = []
    for r in shares or []:
        try:
            tk = r.get("ticker")
            dv = stock_dividends(tk, None, r.get("uid"), cfg) or {}
            hist = [x for x in _dl_rub_divs(dv.get("items")) if x.get("record") and d3 < x["record"] <= ti]
            win = [x for x in hist if x["record"] > d1] or [x for x in hist if d2 < x["record"] <= d1]
            if not win:
                continue
            shift = 1 if win[0]["record"] <= d1 else 0
            for x in win:
                pd_ = (x.get("payment") or x["record"])[:10]
                y0, m0, dd = int(pd_[:4]), int(pd_[5:7]), min(int(pd_[8:10] or 1), 28)
                per = float(x["value"])
                for yy in range(y0 + shift, y0 + shift + 4):
                    d = "%04d-%02d-%02d" % (yy, m0, dd)
                    ym = d[:7]
                    if d <= ti or ym not in keys:
                        continue
                    if any(abs((int(a[:4]) - yy) * 12 + int(a[5:7]) - m0) <= 1 for a in ann.get(tk, [])):
                        continue                                    # уже объявленный дивиденд — не дублируем
                    out.append({"date": d, "kind": "dividend", "name": r.get("name"), "ticker": tk,
                                "amount": per * r["qty"] * (1.0 - tax), "est": True, "est_label": "оценка по истории выплат"})
        except Exception:  # noqa: BLE001
            continue
    return out


def cf36_rates():
    """Ставки реинвестирования (годовые, %): LQDT ~ ключевая - 1 п.п., короткие ОФЗ ~ КБД на 1 год. Подписи источников обязательны."""
    kr, src_kr = None, ""
    try:
        i = keyrate_brief()
        if i and i.get("key_rate") is not None:
            kr, src_kr = float(i["key_rate"]), "ключевая ставка ЦБ"
    except Exception:  # noqa: BLE001
        pass
    if kr is None:
        try:
            ser = key_rate_series()
            if ser:
                kr, src_kr = float(ser[-1][1]), "ключевая ставка ЦБ"
        except Exception:  # noqa: BLE001
            pass
    ofz = None
    try:
        v = kbd_at(1)
        ofz = float(v) if v is not None else None
    except Exception:  # noqa: BLE001
        pass
    return {"lqdt": round(kr - 1.0, 2) if kr is not None else None, "lqdt_src": (src_kr + " - 1 п.п. (оценка доходности LQDT)") if kr is not None else "",
            "ofz1y": round(ofz, 2) if ofz is not None else None, "ofz1y_src": "КБД Мосбиржи, 1 год" if ofz is not None else "",
            "key": kr, "src": src_kr}


def cf36_simulate(months, rate_pct, start=0.0, reinvest=True):
    """K(m) = K(m-1)*(1 + r/12) + CF(m) при реинвесте, иначе K(m) = K(m-1) + CF(m). months — суммы или строки с полем total.
    Возвращает капитал по месяцам с реинвестом и без, итоги и разницу (процент, заработанный на реинвестировании)."""
    cfs = [float(m["total"] if isinstance(m, dict) else (m or 0.0)) for m in months]
    k = float(rate_pct or 0.0) / 100.0 / 12.0
    plain, comp = [], []
    kp = kc = float(start or 0.0)
    for c in cfs:
        kp += c
        kc = kc * (1.0 + k) + c
        plain.append(kp)
        comp.append(kc)
    cap = comp if reinvest else plain
    fin, fin_no = (cap[-1] if cap else float(start or 0.0)), (plain[-1] if plain else float(start or 0.0))
    return {"capital": cap, "capital_no": plain, "final": fin, "final_no": fin_no, "interest": fin - fin_no if reinvest else 0.0,
            "diff": fin - fin_no, "reinvest": bool(reinvest), "rate": float(rate_pct or 0.0)}


def cashflow36_payload(cfg, acc, f=False):
    def compute():
        s = build_summary(cfg, acc, "all")
        pos = s["portfolio"]["positions"]
        today = date.today()
        rep = bonds_report(TInvest(cfg), pos, horizon_days=cf36_horizon_days(today))
        pays = list(rep.get("payments") or [])
        shares = [r for r in pos if r.get("type") == "share" and r.get("uid") and (r.get("qty") or 0) > 0]
        est_d = cf36_est_dividends(shares, pays, cfg, today)
        months = cf36_bucket(pays + est_d, today)
        empty = [m["ym"] for m in months if m["total"] <= 0]
        notes = ["Купоны и амортизации — по графикам эмитентов; погашения — остаток номинала. Все суммы до НДФЛ с купонов.",
                 "Купон флоатера, ещё не объявленный, — по прогнозу ключевой ставки ЦБ плюс спред; купон без объявленной суммы — как последний известный (помечено «оценка»).",
                 "Дивиденды сверх объявленных — оценка по истории выплат: те же месяцы и сумма на акцию, что за последние 12 месяцев, за вычетом НДФЛ %d %%. Не гарантированы." % round(CF36_DIV_TAX * 100)]
        if not pos:
            notes.insert(0, "В выбранном счёте нет позиций.")
        return {"ok": True, "months": months, "empty_months": empty, "notes": notes, "rates": cf36_rates(),
                "total": round(sum(m["total"] for m in months), 2), "est_total": round(sum(m["est"] for m in months), 2),
                "est_dividends": len(est_d), "start": cf36_month_keys(today, 1)[0]}
    return cached_result("cf36", cfg, acc, BONDS_TTL, compute, f)


API_GET["/api/cashflow36"] = lambda cfg, acc, q, force: cashflow36_payload(cfg, acc, force)
