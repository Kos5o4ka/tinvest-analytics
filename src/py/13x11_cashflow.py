
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


def cf36_keyrate_trajectories(base_rate=None, n=CF36_MONTHS):
    """Три траектории ключевой ставки ЦБ на n месяцев (% годовых): стабильная, снижение, повышение."""
    fallback = False
    if base_rate is None:
        try:
            i = keyrate_brief()
            if i and i.get("key_rate") is not None:
                base_rate = float(i["key_rate"])
        except Exception:  # noqa: BLE001
            base_rate = None
    if base_rate is None:
        try:
            ser = key_rate_series()
            if ser:
                base_rate = float(ser[-1][1])
        except Exception:  # noqa: BLE001
            base_rate = None
    if base_rate is None:
        base_rate = 16.0
        fallback = True
    base = float(base_rate)
    low = max(4.0, base - 6.0)
    high = min(30.0, base + 4.0)
    denom = max(1, n - 1)
    hike_m = max(1, min(18, denom))
    flat = [round(base, 2) for _ in range(n)]
    cut = [round(base + (low - base) * (i / denom), 2) for i in range(n)]
    hike = [round(base + (high - base) * min(1.0, i / hike_m), 2) for i in range(n)]
    return {
        "base": round(base, 2),
        "fallback": fallback,
        "items": {
            "flat": {"id": "flat", "name": "Стабильная КС", "desc": "%.2f %% весь срок" % base, "rates": flat},
            "cut": {"id": "cut", "name": "Снижение КС", "desc": "плавно до %.2f %%" % low, "rates": cut},
            "hike": {"id": "hike", "name": "Повышение КС", "desc": "рост до %.2f %%" % high, "rates": hike},
        },
    }


def cf36_offer_events(rep_bonds, fx_rates=None, today=None, n=CF36_MONTHS, pays=None):
    """Реальные пут- и колл-оферты по облигациям портфеля в окне 36 месяцев (MOEX bondization/options + отчёт брокера)."""
    t = today or date.today()
    ti = t.isoformat()
    horizon = (t + timedelta(days=cf36_horizon_days(t, n))).isoformat()
    fx_rates = fx_rates or {}
    pays_by_key = defaultdict(list)
    for p in pays or []:
        kd = p.get("kind")
        if kd not in ("coupon", "amortization"):
            continue
        amt_p = float(p.get("amount") or 0.0)
        d_p = (p.get("date") or "")[:10]
        if amt_p <= 0 or not d_p:
            continue
        for k_p in (p.get("uid"), p.get("ticker"), p.get("name")):
            if k_p:
                pays_by_key[k_p].append((d_p, kd, amt_p))
    out = []
    for b in rep_bonds or []:
        qty = float(b.get("qty") or 0.0)
        if qty <= 0:
            continue
        isin = (b.get("isin") or "").strip().upper()
        nominal = float(b.get("nominal") or 1000.0)
        fc = (b.get("face_cur") or "rub").lower()
        k_fx = 1.0 if fc == "rub" else float(fx_rates.get(fc) or 1.0)
        mat = (b.get("maturity") or "")[:10]

        bz = None
        opt = None
        if isin:
            try:
                bz = moex_bondization(isin)
            except Exception:  # noqa: BLE001
                bz = None
            try:
                opt = moex_bond_options(isin)
            except Exception:  # noqa: BLE001
                opt = None

        dates_kind = {}
        if b.get("put_date") and ti <= b["put_date"][:10] <= horizon:
            dates_kind[b["put_date"][:10]] = ("offer_put", 100.0)
        for cd in b.get("call_dates") or []:
            cd10 = (cd or "")[:10]
            if cd10 and ti <= cd10 <= horizon and cd10 not in dates_kind:
                dates_kind[cd10] = ("offer_call", 100.0)

        if opt:
            prices = opt.get("prices") or {}
            for d in opt.get("put") or []:
                if ti <= d <= horizon:
                    dates_kind[d] = ("offer_put", float(prices.get(d) or 100.0))
            for d in opt.get("call") or []:
                if ti <= d <= horizon and d not in dates_kind:
                    dates_kind[d] = ("offer_call", float(prices.get(d) or 100.0))

        if bz and bz.get("offers"):
            for of in bz["offers"]:
                od = (of.get("offerdate") or "")[:10]
                if not od or od < ti or od > horizon or od in dates_kind:
                    continue
                otype = (of.get("offertype") or "").lower()
                if "пут" in otype or "put" in otype or "выкуп" in otype:
                    kind = "offer_put"
                elif "колл" in otype or "call" in otype or "досроч" in otype:
                    kind = "offer_call"
                else:
                    continue
                dates_kind[od] = (kind, float(of.get("price") or 100.0))

        if not dates_kind:
            continue

        amorts = []
        if bz and bz.get("amort"):
            for a in bz["amort"]:
                ad = (a.get("amortdate") or "")[:10]
                av = float(a.get("value") or 0.0)
                if ad and av > 0 and ti <= ad and (not mat or ad < mat):
                    amorts.append((ad, av))

        rem_mat = max(0.0, nominal - sum(av for _, av in amorts)) * qty * k_fx
        bond_pays = None
        for bk in (b.get("uid"), b.get("ticker"), b.get("name")):
            if bk and bk in pays_by_key:
                bond_pays = pays_by_key[bk]
                break
        for od, (kind, price_pct) in sorted(dates_kind.items()):
            if mat and od >= mat:
                continue
            rem_nom = max(0.0, nominal - sum(av for ad, av in amorts if ad < od))
            amt = rem_nom * (price_pct / 100.0) * qty * k_fx
            if amt <= 0:
                continue
            post_coupons = defaultdict(float)
            post_amorts = defaultdict(float)
            if bond_pays is not None:
                for d_p, kd_p, amt_p in bond_pays:
                    if od < d_p <= horizon and (not mat or d_p <= mat):
                        if kd_p == "coupon":
                            post_coupons[d_p[:7]] += amt_p
                        else:
                            post_amorts[d_p[:7]] += amt_p
            else:
                for c in (bz or {}).get("coupons") or []:
                    cd = (c.get("coupondate") or "")[:10]
                    cv = float(c.get("value") or 0.0)
                    if cd and cv > 0 and od < cd <= horizon and (not mat or cd <= mat):
                        post_coupons[cd[:7]] += cv * qty * k_fx
                for ad, av in amorts:
                    if od < ad <= horizon and (not mat or ad < mat):
                        post_amorts[ad[:7]] += av * qty * k_fx
            out.append({
                "uid": b.get("uid") or "",
                "isin": isin,
                "ticker": b.get("ticker") or "",
                "name": b.get("name") or b.get("ticker") or "",
                "date": od,
                "ym": od[:7],
                "kind": kind,
                "kind_ru": "Пут-оферта" if kind == "offer_put" else "Колл-оферта",
                "amount": round(amt, 2),
                "price_pct": round(price_pct, 2),
                "maturity": mat,
                "maturity_ym": mat[:7] if (mat and ti <= mat <= horizon) else "",
                "maturity_amount": round(rem_mat, 2),
                "post_coupons": {k: round(v, 2) for k, v in post_coupons.items() if v > 0},
                "post_amorts": {k: round(v, 2) for k, v in post_amorts.items() if v > 0},
            })
    out.sort(key=lambda x: (x["date"], x["name"]))
    return out


def cf36_simulate(months, rate_pct, start=0.0, reinvest=True):
    """K(m) = K(m-1)*(1 + r(m)/12) + CF(m) при реинвесте, иначе K(m) = K(m-1) + CF(m).
    rate_pct — годовая ставка (%) или последовательность помесячных ставок. months — суммы или строки с полем total."""
    cfs = [float(m["total"] if isinstance(m, dict) else (m or 0.0)) for m in months]
    is_seq = isinstance(rate_pct, (list, tuple))
    plain, comp = [], []
    kp = kc = float(start or 0.0)
    for i, c in enumerate(cfs):
        r_i = float(rate_pct[i] if is_seq and i < len(rate_pct) else (rate_pct[-1] if is_seq and rate_pct else (rate_pct or 0.0)))
        k = max(0.0, r_i) / 100.0 / 12.0
        kp += c
        kc = kc * (1.0 + k) + c
        plain.append(kp)
        comp.append(kc)
    cap = comp if reinvest else plain
    fin, fin_no = (cap[-1] if cap else float(start or 0.0)), (plain[-1] if plain else float(start or 0.0))
    avg_r = (sum(float(x) for x in rate_pct[:len(cfs)]) / len(cfs)) if (is_seq and cfs) else float(rate_pct or 0.0)
    return {"capital": cap, "capital_no": plain, "final": fin, "final_no": fin_no, "interest": fin - fin_no if reinvest else 0.0,
            "diff": fin - fin_no, "reinvest": bool(reinvest), "rate": round(avg_r, 2)}


def cf36_simulate_offers(months, rate_pct, start=0.0, reinvest=True, offers=None, offer_kinds=("offer_put",)):
    """Реинвестирование купонов и погашений с учётом досрочного выхода по выбранным офертам (без двойного счёта номинала)."""
    adj = [dict(m, by=dict(m.get("by") or {})) if isinstance(m, dict) else {"total": float(m or 0.0), "by": {}} for m in months]
    by_ym = {m["ym"]: m for m in adj if m.get("ym")}
    seen_bonds = set()
    offer_added = 0.0
    maturity_shifted = 0.0
    offer_count = 0
    for of in sorted(offers or [], key=lambda x: x.get("date") or ""):
        if of.get("kind") not in (offer_kinds or ()):
            continue
        bkey = of.get("uid") or of.get("isin") or of.get("name")
        if bkey in seen_bonds:
            continue
        row = by_ym.get(of.get("ym") or "")
        if row is None:
            continue
        seen_bonds.add(bkey)
        amt = float(of.get("amount") or 0.0)
        row["total"] = round(float(row.get("total") or 0.0) + amt, 2)
        offer_added += amt
        offer_count += 1
        mym = of.get("maturity_ym") or ""
        mamt = float(of.get("maturity_amount") or 0.0)
        if mym and mamt > 0 and mym in by_ym:
            mrow = by_ym[mym]
            red = (mrow.get("by") or {}).get("redemption")
            if red is None:
                red = mrow.get("total")
            red = float(red or 0.0)
            sub = min(mamt, red, float(mrow.get("total") or 0.0))
            mrow["total"] = round(max(0.0, float(mrow.get("total") or 0.0) - sub), 2)
            if "redemption" in (mrow.get("by") or {}):
                mrow["by"]["redemption"] = round(max(0.0, float(mrow["by"]["redemption"] or 0.0) - sub), 2)
            maturity_shifted += sub
        for field, bkey_flow in (("post_coupons", "coupon"), ("post_amorts", "amortization")):
            for pym, pamt in (of.get(field) or {}).items():
                pamt = float(pamt or 0.0)
                if pamt <= 0 or pym not in by_ym:
                    continue
                prow = by_ym[pym]
                cur_f = (prow.get("by") or {}).get(bkey_flow)
                if cur_f is None:
                    cur_f = prow.get("total")
                cur_f = float(cur_f or 0.0)
                sub_f = min(pamt, cur_f, float(prow.get("total") or 0.0))
                prow["total"] = round(max(0.0, float(prow.get("total") or 0.0) - sub_f), 2)
                if bkey_flow in (prow.get("by") or {}):
                    prow["by"][bkey_flow] = round(max(0.0, float(prow["by"][bkey_flow] or 0.0) - sub_f), 2)
    sim = cf36_simulate(adj, rate_pct, start=start, reinvest=reinvest)
    sim.update({
        "offer_added": round(offer_added, 2),
        "maturity_shifted": round(maturity_shifted, 2),
        "offer_count": offer_count,
    })
    return sim


def cashflow36_payload(cfg, acc, f=False):
    def compute():
        s = build_summary(cfg, acc, "all")
        pos = s["portfolio"]["positions"]
        today = date.today()
        client = TInvest(cfg)
        rep = bonds_report(client, pos, horizon_days=cf36_horizon_days(today))
        pays = list(rep.get("payments") or [])
        shares = [r for r in pos if r.get("type") == "share" and r.get("uid") and (r.get("qty") or 0) > 0]
        est_d = cf36_est_dividends(shares, pays, cfg, today)
        months = cf36_bucket(pays + est_d, today)
        empty = [m["ym"] for m in months if m["total"] <= 0]
        rates = cf36_rates()
        rep_rows = rep.get("rows") or []
        fx_curs = {b.get("face_cur") or "rub" for b in rep_rows}
        fx_rates = fx_now(client, fx_curs) if (fx_curs - {"rub"}) else {"rub": 1.0}
        offers = cf36_offer_events(rep_rows, fx_rates, today, pays=pays)
        trajectories = cf36_keyrate_trajectories(rates.get("key"))
        put_offers = [o for o in offers if o["kind"] == "offer_put"]
        call_offers = [o for o in offers if o["kind"] == "offer_call"]
        notes = ["Купоны и амортизации — по графикам эмитентов; погашения — остаток номинала. Все суммы до НДФЛ с купонов.",
                 "Купон флоатера, ещё не объявленный, — по прогнозу ключевой ставки ЦБ плюс спред; купон без объявленной суммы — как последний известный (помечено «оценка»).",
                 "Дивиденды сверх объявленных — оценка по истории выплат: те же месяцы и сумма на акцию, что за последние 12 месяцев, за вычетом НДФЛ %d %%. Не гарантированы." % round(CF36_DIV_TAX * 100),
                 "Калькулятор реинвеста учитывает реальные пут- и колл-оферты (MOEX) и три траектории ключевой ставки ЦБ."]
        if not pos:
            notes.insert(0, "В выбранном счёте нет позиций.")
        return {"ok": True, "months": months, "empty_months": empty, "notes": notes, "rates": rates,
                "offers": offers,
                "offer_summary": {
                    "put_count": len(put_offers), "put_total": round(sum(o["amount"] for o in put_offers), 2),
                    "call_count": len(call_offers), "call_total": round(sum(o["amount"] for o in call_offers), 2),
                },
                "trajectories": trajectories,
                "total": round(sum(m["total"] for m in months), 2), "est_total": round(sum(m["est"] for m in months), 2),
                "est_dividends": len(est_d), "start": cf36_month_keys(today, 1)[0]}
    return cached_result("cf36", cfg, acc, BONDS_TTL, compute, f)


API_GET["/api/cashflow36"] = lambda cfg, acc, q, force: cashflow36_payload(cfg, acc, force)
