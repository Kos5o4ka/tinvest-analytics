# ── Реальный журнал выплат и доходность на цену покупки (YOC) ──

PJ_TYPE_RU = {
    "bond": "Облигация",
    "share": "Акция",
    "etf": "Фонд",
    "sp": "Структурная бумага",
    "other": "Прочее",
}


def _pj_fx_rate(cur, iso_day, fx_fallback, warns):
    """Курс валюты к рублю на дату выплаты: сначала ЦБ РФ на дату, затем текущий курс, иначе 1.0."""
    cur = (cur or "rub").lower()
    if cur in ("", "rub"):
        return 1.0
    r = None
    try:
        r = tax_cbr_rate(cur, iso_day)
    except Exception:  # noqa: BLE001
        r = None
    if not r and fx_fallback:
        r = fx_fallback.get(cur)
    if not r:
        warns["fx_" + cur] = "Нет курса ЦБ для %s на часть дат — использован курс 1,0." % cur.upper()
        return 1.0
    return float(r)


def build_pay_journal(ops, names, client=None, today=None):
    """Строит журнал фактических купонов и дивидендов и рассчитывает YOC по FIFO-стоимости."""
    t_today = today or date.today()
    d12m = (t_today - timedelta(days=365)).isoformat()
    today_iso = t_today.isoformat()
    clean_ops = sorted(
        [o for o in (ops or []) if not str(o.get("state") or "").endswith("CANCELED")],
        key=lambda o: o.get("date") or "",
    )
    lots = fifo(clean_ops)

    # Определяем валюту покупки по операциям/инструменту для пересчёта FIFO-стоимости в рубли
    buy_cur = {}
    payout_curs = set()
    for o in clean_ops:
        k = classify(o.get("type"))
        uid = o.get("instrumentUid") or o.get("figi") or ""
        cur = cur_of(o.get("payment"))
        if k in ("buy", "sec_in") and uid and cur:
            buy_cur[uid] = cur
        elif k in ("coupons", "dividends") and cur and cur != "rub":
            payout_curs.add(cur)

    for uid in lots:
        c = buy_cur.get(uid) or ((names.get(uid) or {}).get("cur") or "rub").lower()
        if c and c != "rub":
            payout_curs.add(c)

    fx_fallback = {}
    if payout_curs and client is not None:
        try:
            fx_fallback = fx_now(client, payout_curs) or {}
        except Exception:  # noqa: BLE001
            fx_fallback = {}

    warns = {}
    by_month = defaultdict(lambda: {"ym": "", "coupons_rub": 0.0, "dividends_rub": 0.0, "total_rub": 0.0, "count": 0})
    by_year = defaultdict(lambda: {"year": "", "coupons_rub": 0.0, "dividends_rub": 0.0, "total_rub": 0.0, "count": 0})
    by_sec = {}
    items = []

    def sec_entry(uid, o=None):
        if uid not in by_sec:
            info = names.get(uid) or {}
            itype = (info.get("type") or (o or {}).get("instrumentType") or "other").lower()
            itype = {"bonds": "bond", "shares": "share"}.get(itype, itype) or "other"
            by_sec[uid] = {
                "uid": uid,
                "name": info_name(info, o) or (o or {}).get("ticker") or uid,
                "ticker": info.get("ticker") or (o or {}).get("ticker") or "",
                "type": itype,
                "type_ru": PJ_TYPE_RU.get(itype, "Прочее"),
                "logo": info.get("logo") or "",
                "color": info.get("color") or "",
                "qty": 0.0,
                "coupons_rub": 0.0,
                "dividends_rub": 0.0,
                "total_rub": 0.0,
                "payout_12m_rub": 0.0,
                "cost_rub": 0.0,
                "yoc_pct": None,
                "yoc_total_pct": None,
                "last_date": "",
                "count": 0,
            }
        return by_sec[uid]

    tot_coup = 0.0
    tot_div = 0.0
    tot_12m = 0.0

    for o in clean_ops:
        k = classify(o.get("type"))
        if k not in ("coupons", "dividends"):
            continue
        amt = qf(o.get("payment"))
        if not amt:
            continue
        dt = parse_dt(o.get("date")).date()
        d_iso = dt.isoformat()
        ym = d_iso[:7]
        yr = d_iso[:4]
        cur = cur_of(o.get("payment"))
        rate = _pj_fx_rate(cur, d_iso, fx_fallback, warns)
        amt_rub = amt * rate

        uid = o.get("instrumentUid") or o.get("figi") or (o.get("ticker") or "other")
        sec = sec_entry(uid, o)
        if k == "coupons":
            sec["coupons_rub"] += amt_rub
            by_month[ym]["coupons_rub"] += amt_rub
            by_year[yr]["coupons_rub"] += amt_rub
            tot_coup += amt_rub
        else:
            sec["dividends_rub"] += amt_rub
            by_month[ym]["dividends_rub"] += amt_rub
            by_year[yr]["dividends_rub"] += amt_rub
            tot_div += amt_rub

        sec["total_rub"] += amt_rub
        sec["count"] += 1
        if d_iso > sec["last_date"]:
            sec["last_date"] = d_iso
        if d12m < d_iso <= today_iso:
            sec["payout_12m_rub"] += amt_rub
            tot_12m += amt_rub

        by_month[ym]["ym"] = ym
        by_month[ym]["total_rub"] += amt_rub
        by_month[ym]["count"] += 1

        by_year[yr]["year"] = yr
        by_year[yr]["total_rub"] += amt_rub
        by_year[yr]["count"] += 1

        items.append({
            "date": d_iso,
            "uid": uid,
            "name": sec["name"],
            "ticker": sec["ticker"],
            "kind": "coupon" if k == "coupons" else "dividend",
            "amount": round(amt, 2),
            "cur": cur.upper(),
            "amount_rub": round(amt_rub, 2),
            "rate": round(rate, 4),
        })

    # Привязываем FIFO-стоимость к открытым позициям и считаем YOC
    total_cost_rub = 0.0
    held_12m_rub = 0.0
    for uid, lot in lots.items():
        qty = float(lot.get("qty") or 0.0)
        cost = float(lot.get("cost") or 0.0)
        if qty <= 1e-9:
            continue
        sec = sec_entry(uid)
        cur = buy_cur.get(uid) or ((names.get(uid) or {}).get("cur") or "rub").lower()
        rate = _pj_fx_rate(cur, today_iso, fx_fallback, warns)
        cost_rub = cost * rate
        sec["qty"] = round(qty, 4)
        sec["cost_rub"] = round(cost_rub, 2)
        if cost_rub > 0:
            total_cost_rub += cost_rub
            held_12m_rub += sec["payout_12m_rub"]
            sec["yoc_pct"] = round(sec["payout_12m_rub"] / cost_rub * 100.0, 2)
            sec["yoc_total_pct"] = round(sec["total_rub"] / cost_rub * 100.0, 2)

    months = []
    for ym in sorted(by_month):
        r = by_month[ym]
        months.append({
            "ym": ym,
            "coupons_rub": round(r["coupons_rub"], 2),
            "dividends_rub": round(r["dividends_rub"], 2),
            "total_rub": round(r["total_rub"], 2),
            "count": r["count"],
        })

    years = []
    for yr in sorted(by_year):
        r = by_year[yr]
        years.append({
            "year": yr,
            "coupons_rub": round(r["coupons_rub"], 2),
            "dividends_rub": round(r["dividends_rub"], 2),
            "total_rub": round(r["total_rub"], 2),
            "count": r["count"],
        })

    securities = []
    for sec in by_sec.values():
        if sec["total_rub"] <= 0 and sec["cost_rub"] <= 0:
            continue
        sec["coupons_rub"] = round(sec["coupons_rub"], 2)
        sec["dividends_rub"] = round(sec["dividends_rub"], 2)
        sec["total_rub"] = round(sec["total_rub"], 2)
        sec["payout_12m_rub"] = round(sec["payout_12m_rub"], 2)
        securities.append(sec)
    securities.sort(key=lambda x: (-x["total_rub"], -x["cost_rub"], x["name"]))

    items.sort(key=lambda x: x["date"], reverse=True)
    portfolio_yoc = round(held_12m_rub / total_cost_rub * 100.0, 2) if total_cost_rub > 0 else None

    notes = [
        "YOC (доходность на цену покупки) = фактические выплаты за последние 12 месяцев к текущей стоимости позиции по методу FIFO.",
        "Накопленный YOC = все полученные купоны и дивиденды по бумаге к её текущей FIFO-стоимости.",
        "Валютные выплаты пересчитаны в рубли по курсу ЦБ РФ на дату выплаты.",
    ]
    notes.extend(warns.values())

    return {
        "ok": True,
        "total_rub": round(tot_coup + tot_div, 2),
        "coupons_rub": round(tot_coup, 2),
        "dividends_rub": round(tot_div, 2),
        "total_12m_rub": round(tot_12m, 2),
        "cost_rub": round(total_cost_rub, 2),
        "portfolio_yoc_pct": portfolio_yoc,
        "yoc_label": "YOC (12 мес. / FIFO-стоимость)",
        "months": months,
        "years": years,
        "securities": securities,
        "items": items[:300],
        "notes": notes,
    }


def pay_journal_payload(cfg, acc, force=False):
    """Журнал фактических выплат (купоны/дивиденды) и расчёт YOC по счёту."""
    def compute():
        client = TInvest(cfg)
        _accs, _sel, data = selection(cfg, acc, force)
        ops = sorted([o for d in data for o in d["ops"]], key=lambda o: o.get("date") or "")
        keys = set()
        for d in data:
            for x in (d["port"] or {}).get("positions") or []:
                keys.add((x.get("instrumentUid"), x.get("figi")))
        keys |= _op_inst_keys(ops)
        names = instruments(client, keys)
        return build_pay_journal(ops, names, client=client)

    return cached_result("pay_journal", cfg, acc, BONDS_TTL, compute, force)


API_GET["/api/pay/journal"] = lambda cfg, acc, q, force: pay_journal_payload(cfg, acc, force)
