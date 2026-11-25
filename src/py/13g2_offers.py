def _of_one(r, bz, offs, today, flags):
    """Оферты одной позиции (все будущие, put и call отдельными записями) -> список записей для страницы."""
    face = r.get("nominal") or 1000.0
    offs = [o for o in offs if o.get("status") != "cancelled"]
    if not offs:
        return []
    fl_ = bool(r.get("floating"))
    bz = bz or {"coupons": [], "amort": [], "offers": []}
    try:
        flows, _k, _e = bond_flows(bz, today, face, mode="maturity", floating=fl_)
    except Exception:  # noqa: BLE001
        flows = None
    cps = sorted((c["coupondate"], c.get("value"), c.get("valueprc")) for c in bz["coupons"] if c.get("coupondate"))
    rt = (r.get("rating") or {})
    rv = rt.get("v")
    me = next((e for e in _bc_universe() if e["_isin"] == r.get("isin")), None) if any(o["kind"] == "put" for o in offs) else None
    outlooks = " ".join((x.get("outlook") or "") for x in rt.get("all") or []).lower()
    risk_notes = []
    if flags.get("default"):
        risk_notes.append("по данным Мосбиржи, у выпуска был дефолт")
    elif flags.get("tech"):
        risk_notes.append("по данным Мосбиржи, у выпуска был технический дефолт")
    if "негатив" in outlooks:
        risk_notes.append("у рейтинга негативный прогноз")
    if "наблюден" in outlooks:
        risk_notes.append("рейтинг взят под наблюдение")
    price_pct = r.get("price_pct")
    out = []
    for o in offs:
        od, kind = o["date"], o["kind"]
        days = _of_days(today, od)
        ps, pe = o.get("period_start"), o.get("period_end")
        price = o.get("price") or 100.0
        status, days_left = "unknown", None
        if ps and pe:
            days_left = _of_days(today, pe)
            status = "open" if ps <= today <= pe else ("upcoming" if today < ps else "closed")
        urgent = kind == "put" and (status == "open" or (status == "upcoming" and days_left is not None and days_left <= 7) or
                                    (status == "unknown" and days <= 7))
        rec = {"isin": r.get("isin"), "uid": r.get("uid"), "name": r["name"], "logo": r.get("logo"), "color": r.get("color"),
               "qty": r.get("qty"), "value_rub": r.get("value_rub"), "rating": rv, "floating": fl_,
               "kind": kind, "source": o.get("source"), "inferred": bool(o.get("inferred")), "date": od, "days": days,
               "period_start": ps, "period_end": pe,
               "period_status": status, "period_days_left": days_left, "urgent": urgent, "offer_price": price,
               "price_known": bool(o.get("price")),
               "price": price_pct, "ytm_now": r.get("ytm"), "to_offer_rub": (r.get("qty") or 0) * face * price / 100.0,
               "risk_notes": risk_notes, "yield_to_offer": None, "coupon_known": False, "coupon_status": None, "new_rate": None,
               "hold_yield": None, "peer_median": None, "peers_n": 0, "threshold": None}
        if kind != "put":
            rec["to_offer_rub"] = None
        after_cut = None
        try:
            if flows:
                cut, remain = _of_cut(bz, flows, face, od, price / 100.0)
                aci_now = _of_aci(bz, flows, today)
                if price_pct:
                    dirty = price_pct / 100.0 * face + aci_now
                    y = cf_ytm(dirty, cut, today)
                    rec["yield_to_offer"] = y * 100 if y is not None else None
                after = [x for x in flows if x[0] > od]
                if after and kind == "put":
                    after_cut = (after, remain, _of_aci(bz, flows, od))
        except Exception:  # noqa: BLE001
            after_cut = None
        if kind != "put":
            rec["hint"] = _of_hint_other(rec)
            out.append(rec)
            continue
        nc = of_new_coupon(bz["coupons"], od, face, fl_)
        known = nc["status"] == "announced"
        rec["coupon_known"], rec["coupon_status"], rec["new_rate"] = known, nc["status"], nc["rate"]
        mac = None
        if after_cut:
            after, remain, aci_od = after_cut
            y2 = cf_ytm(remain + aci_od, after, od)
            if y2 is not None:
                mac, _m, _c = cf_risk(after, od, y2)
                if known:
                    rec["hold_yield"] = y2 * 100          # запасной вариант: если оставить бумагу, а деньги по оферте вложить по номиналу
        if known and flows and price_pct:
            try:                                           # основной: доходность к погашению при ТЕКУЩЕЙ цене с новым купоном
                yn = cf_ytm(price_pct / 100.0 * face + _of_aci(bz, flows, today), flows, today)
                if yn is not None and 0 < yn * 100 < 100:
                    rec["hold_yield"] = yn * 100
            except Exception:  # noqa: BLE001
                pass
        med, n = _of_peers(me, rv, fl_, mac)
        if med is not None:
            rec["peer_median"], rec["peers_n"], rec["threshold"] = med, n, med - OF_MARGIN
        rec["hint"] = _of_hint(rec, risk_notes)
        rec["helper"] = of_helper(rec)
        out.append(rec)
    return out


def _of_hint_other(rec):
    """Подсказка для колл-опциона эмитента и для оферты неуказанного типа."""
    y = rec.get("yield_to_offer")
    if rec["kind"] == "call":
        yt = (" Доходность к этой дате при текущей цене — %s %% годовых (выкуп по %s)." % (
            _of_pct(y), "%s %%" % _of_pct(rec["offer_price"]) if rec.get("price_known") else "номиналу")) if y is not None and y <= 100 else ""
        src = (" Дата получена от брокера, на Мосбирже условия не найдены — уточните их в проспекте выпуска."
               if rec.get("source") == "broker" else "")
        return {"code": "call", "title": "Эмитент может погасить досрочно",
                "text": "Это право эмитента, а не ваше: заявку подавать не нужно. Если ставки к тому времени упадут, эмитент "
                        "может погасить выпуск и вам придётся вкладывать деньги под меньший доход (риск реинвестирования), "
                        "поэтому ориентируйтесь на доходность к этой дате, а не к погашению.%s%s" % (yt, src)}
    if rec.get("source") == "broker":
        return {"code": "unknown", "title": "Тип оферты не указан",
                "text": "Эту дату сообщает брокер, а на Мосбирже оферта по выпуску не опубликована. Чаще всего так выглядит право "
                        "эмитента досрочно погасить выпуск (call) — тогда делать ничего не нужно. Но это может быть и put: "
                        "проверьте условия в решении о выпуске или у брокера, прежде чем полагаться на эту дату."}
    return {"code": "unknown", "title": "Тип оферты не указан",
            "text": "Мосбиржа не сообщает, кто решает: держатель (put) или эмитент (call). Условия приведены "
                    "в документах выпуска и у брокера."}


def _of_hint(rec, risk_notes):
    price, op, med = rec["price"], rec["offer_price"], rec["peer_median"]
    hy, thr = rec["hold_yield"], rec["threshold"]
    how = ("Заявку на выкуп подаёт брокер; обычно он принимает поручения на несколько дней раньше окончания периода "
           "предъявления — уточните сроки у брокера.")
    if rec["period_status"] == "closed":
        return {"code": "closed", "title": "Период предъявления прошёл",
                "text": "Приём заявок на выкуп завершён: бумага остаётся у держателя, условия после оферты определяет эмитент."}
    if price is not None and price > op + OF_PRICE_EPS:
        return {"code": "sell_market", "title": "Биржевая цена выше цены оферты",
                "text": "Рыночная цена (%s %%) выше цены выкупа (%s %%): цена на бирже выше выкупной по оферте." % (_of_pct(price), _of_pct(op))}
    if risk_notes:
        low = (" Рыночная цена (%s %%) заметно ниже цены выкупа: рынок сомневается, что эмитент выкупит бумаги." % _of_pct(price)
               if price is not None and price < op - 10 else "")
        return {"code": "put", "title": "Есть признаки риска эмитента",
                "text": "Есть признаки повышенного риска эмитента: %s. Цена выкупа по оферте — %s %% номинала.%s %s" % ("; ".join(risk_notes), _of_pct(op), low, how)}
    if rec["floating"] and not rec["coupon_known"]:
        return {"code": "hold", "title": "Доходность к погашению не ниже рынка",
                "text": "Купон плавающий и следует за ключевой ставкой, поэтому после оферты он обычно остаётся на уровне рынка."}
    if rec["coupon_known"] and hy is not None:
        code = of_outcome(hy, med)[0]
        if code == "below":
            return {"code": "put", "title": "Есть признаки риска эмитента",
                    "text": "Новый купон (%s %% годовых) даёт доходность %s %% против %s %% у похожих выпусков (%d шт.): ниже "
                            "рынка больше чем на 0,5 п. п. Деньги по оферте (%s %%) можно вложить в бумагу с более высокой "
                            "доходностью. %s" % (_of_pct(rec["new_rate"] or 0), _of_pct(hy), _of_pct(med), rec["peers_n"],
                                                 _of_pct(op), how)}
        if med is None:
            return {"code": "hold", "title": "Доходность к погашению не ниже рынка",
                    "text": "Новый купон известен (%s %% годовых), доходность после оферты %s %%. Сравнить с рынком не с чем: "
                            "подходящих аналогов мало." % (_of_pct(rec["new_rate"] or 0), _of_pct(hy))}
        return {"code": "hold", "title": "Доходность к погашению не ниже рынка",
                "text": "Новый купон (%s %% годовых) даёт доходность %s %% против %s %% у похожих выпусков (%d шт.): %s. "
                        "Предъявлять нет смысла, если деньги не нужны." % (_of_pct(rec["new_rate"] or 0), _of_pct(hy), _of_pct(med),
                                                                            rec["peers_n"], "выше рынка" if code == "above" else "на уровне рынка")}
    t = "Новый купон ещё не объявлен."
    if rec["urgent"]:
        t += " Срок предъявления близко. " + how
    return {"code": "wait", "title": "Ставка ещё не объявлена", "text": t}


def offers_payload(cfg, acc):
    rep = build_bonds(cfg, acc)
    today = date.today().isoformat()
    rows = [r for r in rep["rows"] if r.get("isin") and r.get("qty")]

    def one(r):
        try:
            bz = moex_bondization(r["isin"])
            offs = offer_kinds(bz or {}, moex_bond_options(r["isin"]), r.get("call"), today)
            if not any(o["status"] != "cancelled" for o in offs):
                return [], None
            return _of_one(r, bz, offs, today, _mon_flags(r["isin"])), None
        except Exception as e:  # noqa: BLE001
            return [], "%s: %s" % (r.get("name"), str(e)[:100])
    res = pool_map(one, rows, workers=8)
    items = sorted([x for lst, _ in res for x in lst], key=lambda x: (x["date"], OF_KIND_ORDER[x["kind"]], x["name"]))
    errs = [e for _, e in res if e]
    puts = [x for x in items if x["kind"] == "put"]
    calls = [x for x in items if x["kind"] == "call"]
    by_isin = defaultdict(set)
    for x in items:
        by_isin[x["isin"]].add(x["kind"])
    return {"account": acc, "today": today, "items": items, "count": len(items), "put_count": len(puts),
            "call_count": len(calls), "unknown_count": len(items) - len(puts) - len(calls),
            "both_count": sum(1 for v in by_isin.values() if {"put", "call"} <= v),
            "urgent_count": sum(1 for x in puts if x["urgent"]),
            "value_rub": sum(x["value_rub"] or 0 for x in items), "to_offer_rub": sum(x["to_offer_rub"] or 0 for x in puts),
            "bonds_count": len(rows), "errors": errs,
            "empty_text": "По облигациям портфеля будущих оферт нет: выпуски погашаются по графику.",
            "notes": ["PUT — право держателя предъявить бумагу эмитенту к выкупу по заранее известной цене (обычно 100 % номинала). "
                      "Если вы ничего не делаете, бумага остаётся у вас, но купон после оферты эмитент может изменить.",
                      "CALL — право эмитента досрочно погасить или выкупить выпуск. Решение принимает эмитент, заявку подавать не "
                      "нужно; для вас это риск реинвестирования: деньги вернутся, когда ставки, возможно, уже ниже. Поэтому у такой "
                      "бумаги смотрят доходность к дате колл, а не к погашению.",
                      "У одного выпуска может быть несколько дат и оба типа сразу — каждая показана отдельной строкой. Тип берётся из "
                      "данных Мосбиржи (поля дат put/call и тип записи оферты); если определить его не удалось, строка помечена "
                      "«тип не указан». Дата от брокера без подтверждения Мосбиржи тоже помечена «тип не указан». "
                      "Период предъявления Мосбиржа публикует незадолго до оферты."]}


# ═══════════════════ конструктор лесенки облигаций ═══════════════════

