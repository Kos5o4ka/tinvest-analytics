def tx_last_sale_day(year, holidays=()):
    """Последний день года, когда сделка ещё рассчитается в этом году при T+1: последний торговый день минус один торговый день.
    Торговым считаем будний день, не равный 31 декабря (на практике 31.12 — выходной на бирже) и не из holidays (набор date).
    Точный календарь торгов определяет биржа."""
    hol = set(holidays or ())

    def trading(d):
        return d.weekday() < 5 and not (d.month == 12 and d.day == 31) and d not in hol
    d = date(year, 12, 31)
    while not trading(d):
        d -= timedelta(days=1)
    last = d
    d = last - timedelta(days=1)
    while not trading(d):
        d -= timedelta(days=1)
    return d, last


def tx_forecast(st, settings, pays=None, holidays=()):
    """Прогноз налога на конец года по обычным (не ИИС) счетам и подсказки по сбору убытков. pays — прогноз выплат (как на странице «Выплаты»)."""
    today, cy = st["today"], st["today"].year
    end = date(cy, 12, 31).isoformat()
    sale_day, last_day = tx_last_sale_day(cy, holidays)
    gen = [g for g in st["groups"] if g["kind"] == "gen"]
    iis = [g["name"] for g in st["groups"] if g["kind"] == "iis"]
    out = {"year": cy, "available": bool(gen), "iis_excluded": iis, "sale_day": sale_day.isoformat(), "last_trading_day": last_day.isoformat(),
           "days_to_sale": (sale_day - today).days, "pays_known": pays is not None, "harvest": [], "skipped": [], "harvest_saving": 0.0}
    if not gen:
        return out
    g = gen[0]
    row = next((r for r in g["rows"] if r["year"] == cy), None) or {}
    f = lambda k: float(row.get(k, 0.0) or 0.0)
    ec = ed = 0.0
    n = 0
    for p in pays or []:
        if today.isoformat() < (p.get("date") or "") <= end and p.get("kind") in ("coupon", "dividend") and p.get("amount"):
            if p["kind"] == "coupon":
                ec += p["amount"]
            else:
                ed += p["amount"]
            n += 1
    base = f("base")
    tax_now = tx_ndfl(base, cy)[0]
    tax_end, lo, hi = tx_ndfl(base + ec + ed, cy)
    thr = 5000000.0 if cy < 2025 else 2400000.0
    out["forecast"] = {
        "trade": f("trade"), "ldv_exempt": f("ldv_exempt"), "carry_used": f("carry_used"), "trade_base": f("trade_base"), "dividends": f("dividends"),
        "coupons": f("coupons"), "other": f("overnight") + max(0.0, f("deriv")), "base": base, "tax_now": tax_now, "withheld": f("withheld"),
        "exp_coupons": ec, "exp_dividends": ed, "exp_n": n, "base_end": base + ec + ed, "tax_end": tax_end, "tax13": lo * 0.13, "tax15": hi * 0.15,
        "to_withhold": max(0.0, tax_end - f("withheld")), "refund": max(0.0, f("withheld") - tax_end), "threshold": thr,
        "rate": 0.15 if base + ec + ed > thr else 0.13}
    # сбор убытков: позиции обычных счетов с нереализованным убытком
    fee_rate = st["eng"]["fee_rate"]
    t0, _ = tx_cur_tax(g, [], cy, settings)
    cands, skipped = [], []
    for uid, lots in tx_group_open(st, g).items():
        pr = tx_pos_price(st["pos"].get(uid))
        if not pr or lots[0]["type"] in TAX_SKIP_TYPES:
            continue
        q = sum(l["qty"] for l in lots)
        base_r = {"acc": lots[0]["acc"], "uid": uid, "name": lots[0]["name"], "ticker": lots[0]["ticker"], "type": lots[0]["type"],
                  "bucket": "deriv" if lots[0]["type"] == "option" else "sec", "kind": "sell", "bdate": None}
        rows = tx_fee_sim(lots, q, pr, fee_rate, today, base_r)
        res = sum(r["result"] for r in rows)
        if res >= -50:
            continue
        t1, _ = tx_cur_tax(g, rows, cy, settings)
        # лоты с прибылью, которым скоро исполнится 3 года (ЛДВ): продажа всей позиции лишит их льготы
        soon = None
        if lots[0]["type"] in TAX_LDV_TYPES:
            for l in lots:
                if l.get("blind") or not l["date"] or l["date"] < TAX_LDV_FROM or l["unit"] >= pr:
                    continue
                dd = (tx_add_years(l["date"], 3) + timedelta(days=1) - today).days
                if 0 < dd <= 365 and (soon is None or dd < soon):
                    soon = dd
        c = {"uid": uid, "name": base_r["name"], "ticker": base_r["ticker"], "qty": q, "value": q * pr, "loss": -res, "saving": t0 - t1,
             "cost": q * pr * (fee_rate + TAX_SPREAD), "ldv_days": soon, "rows": rows}
        c["net"] = c["saving"] - c["cost"]
        if soon is not None and soon <= 180:
            c["reason"] = "через %d дн. часть лотов получит ЛДВ, продавать невыгодно" % soon
            skipped.append(c)
        elif c["net"] > 1:
            cands.append(c)
    cands.sort(key=lambda c: -c["saving"])
    extra = []
    for c in cands:        # накопительный эффект: каждая следующая продажа уменьшает налог меньше, когда прибыль уже покрыта
        tp, _ = tx_cur_tax(g, extra, cy, settings)
        extra = extra + c["rows"]
        tn, _ = tx_cur_tax(g, extra, cy, settings)
        c["saving_marginal"] = tp - tn
    for c in cands + skipped:
        c.pop("rows", None)
    out["harvest"], out["skipped"] = cands[:25], skipped[:10]
    out["harvest_saving"] = sum(c["saving_marginal"] for c in cands)
    out["base_tax"] = t0
    return out


def tx_decl_sales(sales, year):
    out = []
    for s in sales:
        if s["bucket"] != "sec" or s["sdate"].year != year:
            continue
        out.append({
            "sdate": s["sdate"].isoformat(),
            "bdate": s["bdate"].isoformat() if s.get("bdate") else "",
            "uid": s["uid"],
            "name": s["name"],
            "ticker": s["ticker"],
            "type": s["type"],
            "kind": s["kind"],
            "qty": s["qty"],
            "proceeds": s["proceeds"],
            "cost": s["cost"],
            "fee": s["fee"],
            "result": s["result"],
            "ldv": bool(s.get("ldv")),
            "yrs": s.get("yrs", 0),
        })
    return sorted(out, key=lambda x: (x["sdate"], x["name"]))


def tx_decl(st):
    decl = {}
    all_pays = st.get("eng", {}).get("payouts") or []
    for g in st["groups"]:
        g_accs = set(g.get("accounts") or [])
        for r in g["rows"]:
            y = r["year"]
            d = decl.setdefault(y, {"year": y, "groups": [], "fx_payouts": [], "loss_carry": {"carry_used": 0.0, "loss_new": 0.0, "pool": []}})
            pays = sorted([dict(p) for p in all_pays if p["acc"] in g_accs and p["year"] == y], key=lambda p: (p["date"], p["name"]))
            fx_pays = [p for p in pays if p["cur"] != "RUB"]
            e = dict(r)
            e.update(key=g["key"], name=g["name"], kind=g["kind"], lines=tx_lines(g["sales"], y),
                     sales=tx_decl_sales(g["sales"], y), payouts=pays, fx_payouts=fx_pays)
            d["groups"].append(e)
            d["fx_payouts"].extend(fx_pays)
            d["loss_carry"]["carry_used"] += r.get("carry_used", 0.0)
            d["loss_carry"]["loss_new"] += r.get("loss_new", 0.0)
            if g["kind"] == "gen":
                d["loss_carry"]["pool"] = list(r.get("carry_pool") or [])
    for d in decl.values():
        d["fx_payouts"].sort(key=lambda p: (p["date"], p["name"]))
    return decl


def tx_iis_table(st, settings):
    out = []
    dr = 0.15 if str((settings or {}).get("ndfl_rate")) in ("15", "0.15") else 0.13
    for g in st["groups"]:
        if g["kind"] != "iis":
            continue
        i = g["iis"]
        ded = i["type"] in ("A", "3")
        ys = []
        for r in g["rows"]:
            if r["deposits"] > 0 or r["withdrawals"] > 0:
                b = min(r["deposits"], TAX_IIS_LIMIT)
                ys.append({"year": r["year"], "deposits": r["deposits"], "withdrawals": r["withdrawals"], "deduct_base": b if ded else 0.0,
                           "deduct": b * dr if ded else 0.0, "over": max(0.0, r["deposits"] - TAX_IIS_LIMIT)})
        e = dict(i)
        e.update(years=ys, deduct_rate=dr, deduct_total=sum(y["deduct"] for y in ys),
                 tax_if_closed=sum(r["tax"] for r in g["rows"]) if not i["exempt"] else 0.0,
                 trade_total=sum(r["trade"] for r in g["rows"]), income_total=sum(r["dividends"] + r["coupons"] for r in g["rows"]))
        out.append(e)
    return out


def tax_payload_from(st, settings, pays=None):
    gen = [g for g in st["groups"] if g["kind"] == "gen"]
    cy = st["today"].year
    up, rd, rate = tx_ldv_tables(st)
    sugg = []
    for g in gen:
        for r in g["rows"]:
            if r["year"] < cy and r["loss_new"] > 0.005 and str(r["year"]) not in settings["loss_carry"]:
                sugg.append({"year": r["year"], "loss": r["loss_new"]})
    ldv_years = {}
    for g in gen:
        for r in g["rows"]:
            if r["ldv_exempt"] > 0 or r["ldv_n"]:
                e = ldv_years.setdefault(r["year"], {"year": r["year"], "exempt": 0.0, "saved": 0.0, "n": 0, "limit": 0.0})
                e["exempt"] += r["ldv_exempt"]
                e["saved"] += r["ldv_saved"]
                e["n"] += r["ldv_n"]
                e["limit"] = max(e["limit"], r["ldv_limit"])
    strip = lambda g: {k: v for k, v in g.items() if k not in ("sales", "inc")}
    return {
        "today": st["today"].isoformat(), "settings": settings,
        "groups": [strip(g) for g in st["groups"]], "years": st["years"],
        "ldv": {"upcoming": up[:80], "ready": rd[:40], "years": [ldv_years[y] for y in sorted(ldv_years)],
                "saved_total": sum(e["saved"] for e in ldv_years.values()), "rate": rate, "limit": TAX_LDV_LIMIT},
        "iis": tx_iis_table(st, settings), "hints": tx_hints(st, settings), "forecast": tx_forecast(st, settings, pays), "decl": tx_decl(st),
        "carry_suggest": sugg, "warnings": st["eng"]["warnings"], "conversions": st.get("conversions") or [],
        "assumptions": [
            "Счета без ИИС объединены в одну налоговую базу (сальдирование прибылей и убытков между счетами одного налогоплательщика); каждый ИИС считается отдельно.",
            "Налог по годам сравнивается с удержанным по дате операции удержания; брокер часто удерживает налог за год в декабре или в январе следующего года.",
            "Ставка: 13 % и 15 % с части базы свыше 5 млн ₽ (2021–2024) или свыше 2,4 млн ₽ (с 2025 года). Заработная плата и другие доходы в порог не входят.",
            "ЛДВ применяется к акциям, облигациям и фондам, купленным с 2014 года и проданным после трёх лет владения; бумаги, полученные переводом, не учитываются.",
            "НКД, уплаченный при покупке, уменьшает купонный доход (остаток переносится), НКД при продаже входит в купонный доход.",
            "Фьючерсы и опционы: отдельная база по вариационной марже; валюта и ЦФА в расчёт не входят."]}


def tax_state(cfg, acc, force=False):
    settings = tax_settings()
    key = ("taxst", token_key(cfg), acc, json.dumps(settings, sort_keys=True))
    hit = None if force else mem_get(key, 120)
    if hit:
        return hit, settings
    with key_lock(key):
        hit = None if force else mem_get(key, 120)
        if hit:
            return hit, settings
        client = TInvest(cfg)
        accs, sel, data = selection(cfg, acc, force)
        ops = sorted([o for d in data for o in d["ops"]], key=lambda o: o.get("date") or "")
        keys = {(o.get("instrumentUid"), o.get("figi")) for o in ops
                if (o.get("instrumentUid") or o.get("figi")) and not str(o.get("instrumentUid") or "").startswith("imp:")}
        names = instruments(client, keys)
        positions = build_summary(cfg, acc, "all", force)["portfolio"]["positions"]
        st = tax_compute(ops, names, positions, sel, settings, tax_cbr_rate,
                         resolve=lambda t: benchmark_uid(client, t) if client.ready else None)
        return mem_put(key, st), settings


def tax_get(cfg, acc, q, force):
    st, settings = tax_state(cfg, acc, force)
    pays = None
    if cfg.get("token"):
        try:
            pays = build_bonds(cfg, acc).get("payments") or []
        except Exception:  # noqa: BLE001
            pays = None
    return tax_payload_from(st, settings, pays)


def tax_post_settings(cfg, body):
    return {"settings": tax_settings_save(cfg, body or {})}


def tax_reb_plan(st, settings, sells):
    """sells: {класс: сумма продажи, ₽}. Для каждого класса сравниваем «продать пропорционально» и «сначала убыточные и с ЛДВ»."""
    today, cy = st["today"], st["today"].year
    fee_rate = st["eng"]["fee_rate"]
    out = []
    for cls_, amount in sells.items():
        cands = []
        for g in st["groups"]:
            for uid, lots in tx_group_open(st, g).items():
                if lots[0]["type"] != cls_:
                    continue
                pr = tx_pos_price(st["pos"].get(uid))
                if not pr:
                    continue
                q = sum(l["qty"] for l in lots)
                base = {"acc": lots[0]["acc"], "uid": uid, "name": lots[0]["name"], "ticker": lots[0]["ticker"], "type": cls_,
                        "bucket": "deriv" if cls_ == "option" else "sec", "kind": "sell", "bdate": None}
                rows = tx_fee_sim(lots, q, pr, fee_rate, today, base)
                t0, _ = tx_cur_tax(g, [], cy, settings)
                t1, _ = tx_cur_tax(g, rows, cy, settings)
                value = q * pr
                cands.append({"g": g, "uid": uid, "lots": lots, "price": pr, "qty": q, "value": value, "base": base,
                              "rate": (t1 - t0) / value if value else 0.0})
        if not cands:
            out.append({"cls": cls_, "amount": amount, "plan": [], "tax_plan": None, "tax_naive": None, "note": "Нет данных о лотах по этому классу"})
            continue

        def run(pick):
            per_g, items = defaultdict(list), []
            for c, qq in pick:
                rows = tx_fee_sim(c["lots"], qq, c["price"], fee_rate, today, c["base"])
                per_g[c["g"]["key"]].extend(rows)
                res = sum(r["result"] for r in rows)
                soon = [l for l in c["lots"] if l["date"] and not l.get("blind") and 0 < (tx_add_years(l["date"], 3) + timedelta(days=1) - today).days <= 180]
                why = "убыток" if res < 0 else ("прибыль освобождена по ЛДВ" if rows and all(r["ldv"] for r in rows) and res > 0 else "есть налог")
                items.append({"uid": c["uid"], "name": c["base"]["name"], "ticker": c["base"]["ticker"], "gname": c["g"]["name"], "qty": qq,
                              "sell_rub": qq * c["price"], "result": res, "why": why, "ldv_soon": bool(soon and res > 0)})
            tot = 0.0
            for c in {id(x[0]["g"]): x[0] for x in pick}.values():
                g = c["g"]
                t0, _ = tx_cur_tax(g, [], cy, settings)
                t1, _ = tx_cur_tax(g, per_g[g["key"]], cy, settings)
                tot += t1 - t0
            return tot, items
        total_v = sum(c["value"] for c in cands)
        amt = min(amount, total_v)
        naive = []
        for c in cands:
            qq = int(c["qty"] * amt / total_v)
            if qq > 0:
                naive.append((c, qq))
        tax_naive, items_naive = run(naive) if naive else (0.0, [])
        plan, rem = [], amt
        for c in sorted(cands, key=lambda c: c["rate"]):
            if rem < c["price"]:
                break
            qq = int(min(c["qty"], rem / c["price"]))
            if qq <= 0:
                continue
            plan.append((c, qq))
            rem -= qq * c["price"]
        tax_plan, items = run(plan) if plan else (0.0, [])
        if tax_plan > tax_naive:
            tax_plan, items = tax_naive, items_naive
        out.append({"cls": cls_, "amount": amount, "covered": amt, "tax_plan": tax_plan, "tax_naive": tax_naive,
                    "saving": max(0.0, tax_naive - tax_plan), "plan": items})
    return out


def tax_reb_get(cfg, acc, q, force):
    sells = {}
    for part in (q.get("sells") or "").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            try:
                if float(v) > 0:
                    sells[k] = float(v)
            except ValueError:
                pass
    st, settings = tax_state(cfg, acc, force)
    return {"items": tax_reb_plan(st, settings, sells), "warnings": st["eng"]["warnings"]}


def tax_decl_csv(decl, year):
    """Формирует UTF-8 BOM CSV (разделитель ';') для 3-НДФЛ по выбранному году."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Раздел", "Группа", "Дата", "Дата покупки", "Бумага", "Тикер", "Операция", "Кол-во",
                "Валюта", "Сумма в валюте", "Курс ЦБ", "Сумма / Выручка, ₽", "Расход, ₽", "Комиссия, ₽",
                "Результат, ₽", "ЛДВ", "Налог удержан, ₽", "Примечание"])
    n = lambda x, d=2: "" if x is None else str(round(float(x), d)).replace(".", ",")
    kinds = {"sell": "Продажа", "repay": "Погашение", "amort": "Амортизация", "writeoff": "Списание", "short": "Шорт"}
    d = decl.get(year) or {"year": year, "groups": []}
    for g in d["groups"]:
        gn = g["name"]
        w.writerow(["Итог", gn, str(year), "", "Сделки с ценными бумагами", "", "Итог", "", "RUB", "", "",
                    n(g["proceeds"]), n(g["cost"]), n(g["fees"]), n(g["trade"]),
                    n(g["ldv_exempt"]) if g.get("ldv_exempt", 0) > 0.005 else "",
                    n(g["withheld"]),
                    "База: %s; Налог: %s; Зачёт убытков: %s; Убыток к переносу: %s" % (
                        n(g["base"]), n(g["tax"]), n(g["carry_used"]), n(g["loss_new"]))])
        for s in g.get("sales") or []:
            w.writerow(["Сделка", gn, s["sdate"], s.get("bdate") or "", s["name"], s["ticker"],
                        kinds.get(s["kind"], s["kind"]), n(s["qty"], 6), "RUB", "", "",
                        n(s["proceeds"]), n(s["cost"]), n(s["fee"]), n(s["result"]),
                        "Да (%d г.)" % s["yrs"] if s.get("ldv") else "Нет", "", ""])
        for p in g.get("fx_payouts") or []:
            note = p.get("source") or ""
            if p.get("tax_orig", 0) > 0.005:
                note = ("%s; налог в валюте: %s %s" % (note, n(p["tax_orig"]), p["cur"])).strip("; ")
            w.writerow(["Валютная выплата", gn, p["date"], "", p["name"], p["ticker"],
                        "Дивиденд" if p["kind"] == "div" else "Купон", "",
                        p["cur"], n(p["amount"]), n(p["rate"], 4), n(p["amount_rub"]),
                        "", "", "", "", n(p["tax_rub"]), note])
        for lp in g.get("carry_pool") or []:
            w.writerow(["Перенос убытков", gn, str(lp["year"]), "", "Остаток убытка к переносу", "", "", "",
                        "RUB", "", "", "", "", "", n(lp["amount"]), "", "", "Год возникновения убытка: %s" % lp["year"]])
    return buf.getvalue().encode("utf-8-sig")


def tax_decl_csv_get(cfg, acc, q, force):
    raw_y = (q.get("year") or "").strip()
    year = None
    if raw_y:
        try:
            year = int(raw_y)
        except ValueError:
            raise ApiError("Некорректный год", 400)
    st, _ = tax_state(cfg, acc, force)
    decl = tx_decl(st)
    if year is None:
        year = max(decl) if decl else st["today"].year
    return (200, tax_decl_csv(decl, year), "text/csv; charset=utf-8",
            {"Content-Disposition": 'attachment; filename="3ndfl_%d.csv"' % year})


API_GET["/api/tax"] = tax_get
API_GET["/api/tax/reb"] = tax_reb_get
API_GET["/api/tax/decl.csv"] = tax_decl_csv_get
API_POST["/api/tax/settings"] = tax_post_settings
