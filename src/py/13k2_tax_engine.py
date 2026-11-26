def tax_engine(ops, types=None, fx=None, held=None):
    """ops — операции (с полем _acc). types — {uid: info} (type), fx(cur, iso_day) -> курс или None, held — {uid: кол-во}
    из текущих позиций (для сверки лотов). Возвращает продажи, остатки лотов и денежные потоки по (счёт, год)."""
    types = types or {}
    warns = {}
    fx = fx or (lambda cur, day: 1.0 if cur in ("", "rub", "sur") else None)

    def rate(cur, d):
        if cur in ("", "rub", "sur"):
            return 1.0
        r = fx(cur, d.isoformat())
        if not r:
            warns["fx_" + cur] = "Нет курса ЦБ для %s на часть дат — взят курс 1." % cur.upper()
            return 1.0
        return r

    ops = sorted([o for o in ops if not str(o.get("state") or "").endswith("CANCELED")], key=lambda o: o.get("date") or "")
    fee_parent, fee_key = defaultdict(float), defaultdict(float)

    def fee_k(o):
        return (o.get("_acc") or "", (o.get("date") or "")[:19], o.get("instrumentUid") or o.get("figi") or o.get("_ident") or "")

    for o in ops:
        if classify(o.get("type")) == "fee_broker":
            dt = parse_dt(o.get("date"))
            amt = abs(qf(o.get("payment"))) * rate(cur_of(o.get("payment")), dt.date())
            if o.get("parentOperationId"):
                fee_parent[o["parentOperationId"]] += amt
            else:
                fee_key[fee_k(o)] += amt

    # Без parentOperationId комиссии в одной секунде делятся между сделками без собственной комиссии пропорционально обороту
    fee_trades = defaultdict(list)
    for idx, o in enumerate(ops):
        if classify(o.get("type")) in ("buy", "sell"):
            c = o.get("commission")
            if (c and qf(c)) or (o.get("id") and o["id"] in fee_parent):
                continue
            uid = o.get("instrumentUid") or o.get("figi") or o.get("_ident") or ""
            info = types.get(uid) or {}
            itype = o.get("instrumentType") or info.get("type") or ""
            itype = {"bonds": "bond", "shares": "share"}.get(itype, itype) or "share"
            if itype != "futures" and (itype in TAX_SKIP_TYPES or not uid or not op_qty(o)):
                continue
            k = fee_k(o)
            if k in fee_key:
                dt = parse_dt(o.get("date"))
                fee_trades[k].append((idx, abs(qf(o.get("payment"))) * rate(cur_of(o.get("payment")), dt.date())))

    fee_alloc = {}
    for k, items in fee_trades.items():
        tot_fee = fee_key.get(k, 0.0)
        if not tot_fee or not items:
            continue
        tot_turn = sum(tr for _, tr in items)
        left_fee = tot_fee
        for i, (idx, tr) in enumerate(items):
            if i == len(items) - 1:
                part = left_fee
            elif tot_turn > 0:
                part = min(left_fee, tot_fee * (tr / tot_turn))
            else:
                part = min(left_fee, tot_fee / len(items))
            fee_alloc[idx] = part
            left_fee -= part

    def fee_of(idx, o, dt):
        c = o.get("commission")
        if c and qf(c):
            return abs(qf(c)) * rate(cur_of(c), dt.date())
        if o.get("id") and o["id"] in fee_parent:
            return fee_parent[o["id"]]
        return fee_alloc.pop(idx, 0.0)

    books, sales, meta = {}, [], {}
    moved, convs = {}, []
    inc = defaultdict(tx_inc_new)
    payouts = []
    turn = [0.0, 0.0]

    pay_tax_parent = defaultdict(list)
    pay_tax_key = defaultdict(list)
    for o in ops:
        tk = classify(o.get("type"))
        if tk in ("tax_dividend", "tax_coupon"):
            dt = parse_dt(o.get("date"))
            td = dt.date()
            tcur = cur_of(o.get("payment"))
            tamt = abs(qf(o.get("payment")))
            trub = tamt * rate(tcur, td)
            pkind = "dividends" if tk == "tax_dividend" else "coupons"
            if o.get("parentOperationId"):
                pay_tax_parent[o["parentOperationId"]].append((tcur, tamt, trub))
            else:
                tuid = o.get("instrumentUid") or o.get("figi") or o.get("_ident") or ""
                pay_tax_key[(o.get("_acc") or "", td.isoformat(), tuid, pkind)].append((tcur, tamt, trub))

    for idx, o in enumerate(ops):
        kind = classify(o.get("type"))
        acc = o.get("_acc") or ""
        dt = parse_dt(o.get("date"))
        d = dt.date()
        uid = o.get("instrumentUid") or o.get("figi") or o.get("_ident") or ""
        info = types.get(uid) or {}
        itype = o.get("instrumentType") or info.get("type") or ""
        itype = {"bonds": "bond", "shares": "share"}.get(itype, itype) or "share"
        pay = qf(o.get("payment"))
        cur = cur_of(o.get("payment"))
        raw_fx = 1.0 if cur in ("", "rub", "sur") else fx(cur, d.isoformat())
        r = rate(cur, d)
        I = inc[(acc, d.year)]
        if uid and kind in ("buy", "sell", "sec_in", "repayments") and uid not in meta:
            meta[uid] = {"name": info.get("name") or o.get("name") or o.get("ticker") or uid, "ticker": info.get("ticker") or o.get("ticker") or "", "type": itype}
        if kind in ("dividends", "coupons"):
            if kind == "dividends":
                I["div"] += pay * r
            else:
                I["coupon"] += pay * r
            matched = []
            if o.get("id") and o["id"] in pay_tax_parent:
                matched = pay_tax_parent.pop(o["id"])
            elif pay_tax_key.get((acc, d.isoformat(), uid, kind)):
                matched = [pay_tax_key[(acc, d.isoformat(), uid, kind)].pop(0)]
            tax_orig = sum(a for tc, a, _ in matched if tc == cur)
            tax_rub = sum(tr for _, _, tr in matched)
            src_note = "Рублёвая выплата" if cur in ("", "rub", "sur") else ("ЦБ РФ на дату выплаты" if raw_fx else "Курс ЦБ не найден (взят 1.0)")
            payouts.append({
                "id": o.get("id") or "", "acc": acc, "date": d.isoformat(), "year": d.year, "uid": uid,
                "name": info.get("name") or o.get("name") or o.get("ticker") or uid or "—",
                "ticker": info.get("ticker") or o.get("ticker") or "",
                "kind": "div" if kind == "dividends" else "coupon",
                "cur": (cur or "rub").upper(), "amount": pay, "rate": r, "amount_rub": pay * r,
                "tax_orig": tax_orig, "tax_rub": tax_rub, "source": src_note,
            })
        elif kind == "overnight":
            I["over"] += pay * r
        elif kind in TAXES:
            I["withheld"] += -pay * r
            I["w_" + kind] += -pay * r
        elif kind == "deposits":
            I["dep"] += abs(pay) * r
        elif kind == "withdrawals":
            I["wd"] += abs(pay) * r
        elif kind == "varmargin":
            I["deriv"] += pay * r
        elif kind in ("buy", "sell"):
            q = op_qty(o)
            fee = fee_of(idx, o, dt)
            if itype == "futures":
                I["deriv_fee"] += fee
                continue
            if itype in TAX_SKIP_TYPES or not uid or not q:
                continue
            bucket = "deriv" if itype == "option" else "sec"
            nkd = abs(qf(o.get("accruedInt"))) if o.get("accruedInt") else 0.0
            gross = abs(pay)
            clean = gross - nkd
            if clean < 0:
                clean, nkd = gross, 0.0
            bk = books.setdefault((acc, uid), {"lots": [], "shorts": [], "last_repay": None, "last_unit": 0.0})
            base = {"acc": acc, "uid": uid, "name": meta[uid]["name"], "ticker": meta[uid]["ticker"], "type": itype, "bucket": bucket,
                    "kind": "sell", "sdate": d, "bdate": None}
            turn[0] += gross * r
            turn[1] += fee
            if kind == "buy":
                I["nkd_paid"] += nkd * r
                left = float(q)
                unit_buy = (clean * r + fee) / q
                bk["last_unit"] = unit_buy
                sh = bk["shorts"]
                while left > 1e-9 and sh:
                    s = sh[0]
                    t = min(left, s["qty"])
                    row = dict(base, kind="short", qty=t, bdate=s["date"], sdate=d, proceeds=t * s["up"], cost=t * unit_buy, fee=t * s["uf"], ldv=False, yrs=0)
                    row["result"] = row["proceeds"] - row["cost"] - row["fee"]
                    sales.append(row)
                    s["qty"] -= t
                    left -= t
                    if s["qty"] <= 1e-9:
                        sh.pop(0)
                if left > 1e-9:
                    bk["lots"].append({"qty": left, "unit": unit_buy, "date": d, "cur": cur})
            else:
                I["nkd_recv"] += nkd * r
                yv = o.get("yield")
                if yv and itype != "option":
                    I["bk_yield"] += qf(yv) * rate(cur_of(yv, cur), d)
                rows, left = tx_sell(bk["lots"], q, clean * r, fee, d, base)
                sales.extend(rows)
                if left > 1e-9:
                    warns["short"] = "Есть продажи без покупок в истории (короткие позиции или переводы): учтены упрощённо."
                    bk["shorts"].append({"qty": left, "up": clean * r / q, "uf": fee / q, "date": d})
        elif kind == "sec_in":
            q = op_qty(o)
            if not uid or not q or itype in TAX_SKIP_TYPES:
                continue
            bk = books.setdefault((acc, uid), {"lots": [], "shorts": [], "last_repay": None, "last_unit": 0.0})
            unit = qf(o.get("price")) * rate(cur_of(o.get("price"), cur), d) if o.get("price") and qf(o.get("price")) else (abs(pay) * r / q if pay else bk["last_unit"])
            if not unit:
                warns["unk_cost"] = "У бумаг, зачисленных переводом, нет цены: стоимость принята нулевой (прибыль завышена)."
            bk["lots"].append({"qty": float(q), "unit": unit, "date": d, "cur": cur, "blind": True})
        elif kind == "conv_out":
            # Обмен бумаг (ГДР/АДР на акции российского МКПАО, смена кода и т.п.) не продажа: лоты старой бумаги уходят в «карман» обмена
            cv = o.get("_conv") or {}
            lots, left = [], float(op_qty(o))
            for u in cv.get("old_uids") or [uid]:
                bk = books.get((acc, u))
                while bk and bk["lots"] and left > 1e-9:
                    lot = bk["lots"][0]
                    t = min(left, lot["qty"])
                    lots.append(dict(lot, qty=t))
                    lot["qty"] -= t
                    left -= t
                    if lot["qty"] <= 1e-9:
                        bk["lots"].pop(0)
            lots.sort(key=lambda l: l["date"])
            moved[o.get("id")] = lots
        elif kind == "conv_in":
            # Лоты переходят в новую бумагу: количество × коэффициент, цена за штуку / коэффициент, даты покупки сохраняются.
            # По закону о редомициляции обмен депозитарных расписок на акции не считается реализацией, срок владения для ЛДВ
            # продолжается, поэтому дата покупки не обнуляется.
            cv = o.get("_conv") or {}
            ratio = cv.get("ratio") or 1
            lots = moved.pop((o.get("id") or "")[:-3] + ":out", [])
            left = float(op_qty(o))
            bk = books.setdefault((acc, uid), {"lots": [], "shorts": [], "last_repay": None, "last_unit": 0.0})
            for lot in lots:
                t = min(left, lot["qty"] * ratio)
                if t > 1e-9:
                    bk["lots"].append(dict(lot, qty=t, unit=lot["unit"] / ratio))
                    left -= t
            bk["lots"].sort(key=lambda l: l["date"])
            if uid not in meta:
                meta[uid] = {"name": info.get("name") or cv.get("new_ticker") or uid, "ticker": info.get("ticker") or cv.get("new_ticker") or "", "type": itype}
            convs.append(cv)
        elif kind == "sec_out":
            q = op_qty(o)
            bk = books.get((acc, uid))
            if bk and q:
                tx_sell(bk["lots"], q, 0.0, 0.0, d, {"bucket": "none"})
        elif kind == "repayments":
            bk = books.get((acc, uid))
            amount = abs(pay) * r
            if not bk or not bk["lots"] or itype in TAX_SKIP_TYPES:
                if amount:
                    warns["repay_nolots"] = "Погашение/амортизация по бумаге без покупок в истории — не учтено в расходах."
                continue
            base = {"acc": acc, "uid": uid, "name": meta.get(uid, {}).get("name", ""), "ticker": meta.get(uid, {}).get("ticker", ""),
                    "type": itype, "bucket": "sec", "kind": "repay", "sdate": d, "bdate": None}
            tq = sum(l["qty"] for l in bk["lots"])
            if op_type(o) == "BOND_REPAYMENT_FULL":
                rows, _ = tx_sell(bk["lots"], tq, amount, 0.0, d, base)
                sales.extend(rows)
            else:
                bk["last_repay"] = d
                red = amount / tq if tq else 0.0
                excess = 0.0
                for l in bk["lots"]:
                    if l["unit"] >= red:
                        l["unit"] -= red
                    else:
                        excess += (red - l["unit"]) * l["qty"]
                        l["unit"] = 0.0
                if excess > 0.005:
                    sales.append(dict(base, kind="amort", qty=0.0, proceeds=excess, cost=0.0, fee=0.0, result=excess, ldv=False, yrs=0))
    # сверка с текущими позициями: лишние лоты (проданные/погашенные вне истории) списываются
    if held is not None:
        by_uid = defaultdict(list)
        for (acc, uid), bk in books.items():
            by_uid[uid].append((acc, bk))
        for uid, lst in by_uid.items():
            have = held.get(uid, 0.0)
            tot = sum(l["qty"] for _, bk in lst for l in bk["lots"])
            if tot <= have + 0.5:
                if have - tot > 0.5:
                    warns["more_pos"] = "В позициях бумаг больше, чем в истории покупок: часть бумаг без даты и цены покупки."
                continue
            extra = tot - have
            for acc, bk in lst:
                if extra <= 1e-9:
                    break
                lr = bk["last_repay"]
                if have <= 0.5 and lr is not None and bk["lots"]:
                    cost = sum(l["qty"] * l["unit"] for l in bk["lots"])
                    qq = sum(l["qty"] for l in bk["lots"])
                    mt = meta.get(uid, {})
                    if cost > 0.005:
                        sales.append({"acc": acc, "uid": uid, "name": mt.get("name", ""), "ticker": mt.get("ticker", ""), "type": mt.get("type", "bond"),
                                      "bucket": "sec", "kind": "writeoff", "sdate": lr, "bdate": None, "qty": qq, "proceeds": 0.0, "cost": cost,
                                      "fee": 0.0, "result": -cost, "ldv": False, "yrs": 0})
                    extra -= qq
                    bk["lots"] = []
                else:
                    n = min(extra, sum(l["qty"] for l in bk["lots"]))
                    tx_sell(bk["lots"], n, 0.0, 0.0, date.today(), {"bucket": "none"})
                    extra -= n
                    warns["gap"] = "Часть бумаг исчезла из позиций без операций продажи (например, конвертация или перевод) — лоты списаны без финрезультата."
    opens = []
    for (acc, uid), bk in books.items():
        for l in bk["lots"]:
            if l["qty"] > 1e-9:
                mt = meta.get(uid, {})
                opens.append({"acc": acc, "uid": uid, "name": mt.get("name", ""), "ticker": mt.get("ticker", ""), "type": mt.get("type", "share"),
                              "qty": l["qty"], "unit": l["unit"], "date": l["date"], "blind": bool(l.get("blind")), "cur": l.get("cur", "rub")})
    return {"sales": sales, "open": opens, "inc": dict(inc), "payouts": payouts, "meta": meta, "warnings": sorted(warns.values()),
            "fee_rate": (turn[1] / turn[0]) if turn[0] > 0 else 0.003}


