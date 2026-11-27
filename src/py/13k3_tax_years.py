# ── налоговая база по годам для группы счетов ──

def tx_apply_carry(pool, trade_t, year=9999):
    """Погашает положительный результат убытками прошлых лет (старые — первыми). Возвращает (использовано, остаток базы)."""
    used = 0.0
    if trade_t > 0:
        for p in sorted([p for p in pool if p[0] < year], key=lambda p: p[0]):
            u = min(p[1], trade_t - used)
            if u > 0:
                p[1] -= u
                used += u
    return used, max(0.0, trade_t - used)


def tax_group_years(sales, inc, carry_user=None, iis_exempt=False, extra=None, offset_coupons=False,
                    iis_limit=TAX_IIS3_EXEMPT_LIMIT):
    """sales — строки продаж группы; inc — {год: суммы}; carry_user — {"2023": сумма} убытки прошлых лет из деклараций.
    Возвращает (строки по годам, остатки убытков [[год, сумма]])."""
    sales = list(sales) + list(extra or [])
    carry_user = carry_user or {}
    ys = set(r["sdate"].year for r in sales) | set(inc)
    pool = []
    for k, v in carry_user.items():
        if int(k) not in ys:
            pool.append([int(k), float(v)])
    rows, nkd_pool = [], 0.0
    iis_left = iis_limit
    for y in sorted(ys):
        i = inc.get(y, {})
        sec = [s for s in sales if s["bucket"] == "sec" and s["sdate"].year == y]
        dv = [s for s in sales if s["bucket"] == "deriv" and s["sdate"].year == y]
        trade = sum(s["result"] for s in sec)
        elig = [s for s in sec if s["ldv"]]
        elig_res = sum(s["result"] for s in elig)
        wc = sum(max(s["cost"], 0.0) for s in elig)
        wy = (sum(max(s["cost"], 0.0) * s["yrs"] for s in elig) / wc) if wc > 0 else (sum(s["yrs"] for s in elig) / len(elig) if elig else 0.0)
        limit = TAX_LDV_LIMIT * wy
        exempt = min(max(0.0, elig_res), limit)
        pool = [p for p in pool if y - p[0] <= 10 and p[1] > 0.005]
        pool_before = [list(p) for p in pool]
        div = i.get("div", 0.0)
        cg = i.get("coupon", 0.0) + i.get("nkd_recv", 0.0)
        avail = nkd_pool + i.get("nkd_paid", 0.0)
        un = min(avail, max(0.0, cg))
        coupon_net = cg - un
        nkd_pool = avail - un
        trade_t = trade - exempt
        coff = 0.0
        if offset_coupons and trade_t < 0 and coupon_net > 0:
            coff = min(coupon_net, -trade_t)
            coupon_net -= coff
            trade_t += coff
        used, trade_base = tx_apply_carry(pool, trade_t, y)
        new_loss = -trade_t if trade_t < 0 else 0.0
        if str(y) in carry_user:
            new_loss = float(carry_user[str(y)])
        if new_loss > 0.005:
            pool.append([y, new_loss])
        over = i.get("over", 0.0)
        deriv = sum(s["result"] for s in dv) + i.get("deriv", 0.0) - i.get("deriv_fee", 0.0)
        base = trade_base + div + coupon_net + over + max(0.0, deriv)
        tax, lo, hi = tx_ndfl(base, y)
        iis_used = 0.0
        if iis_exempt:
            # вычет ИИС-Б / ИИС-3 не освобождает дивиденды; лимит 30 млн действует только на ИИС-3
            exempt_base = min(max(0.0, base), max(0.0, trade_base + coupon_net + over + max(0.0, deriv)))
            iis_used = exempt_base if iis_left is None else min(exempt_base, iis_left)
            if iis_left is not None:
                iis_left -= iis_used
            tax, lo, hi = tx_ndfl(base - iis_used, y)
        saved = 0.0
        if exempt > 0.005 and not iis_exempt:
            tb0 = tx_apply_carry(pool_before, trade, y)[1]
            saved = max(0.0, tx_ndfl(tb0 + div + coupon_net + over + max(0.0, deriv), y)[0] - tax)
        withheld = i.get("withheld", 0.0)
        rows.append({
            "year": y, "proceeds": sum(s["proceeds"] for s in sec), "cost": sum(s["cost"] for s in sec), "fees": sum(s["fee"] for s in sec),
            "trade": trade, "ldv_exempt": exempt, "ldv_limit": limit if elig else 0.0, "ldv_saved": saved, "ldv_n": len(elig),
            "carry_used": used, "loss_new": new_loss, "carry_pool": [{"year": p[0], "amount": round(p[1], 2)} for p in sorted(pool, key=lambda x: x[0]) if p[1] > 0.005], "trade_base": trade_base,
            "dividends": div, "coupons": coupon_net, "coupons_gross": i.get("coupon", 0.0), "nkd_adj": i.get("nkd_recv", 0.0) - un, "coupon_offset": coff,
            "overnight": over, "deriv": deriv, "base": base, "iis_exempt_used": iis_used, "tax": tax, "tax13": lo * 0.13, "tax15": hi * 0.15,
            "withheld": withheld, "w": {k[2:]: v for k, v in i.items() if k.startswith("w_")},
            "diff": tax - withheld, "diff_pct": ((tax - withheld) / withheld * 100.0) if withheld > 1 else None,
            "broker_trade": i.get("bk_yield", 0.0), "deposits": i.get("dep", 0.0), "withdrawals": i.get("wd", 0.0)})
    return rows, [[p[0], p[1]] for p in pool if p[1] > 0.005]


# ── состояние: группы счетов, ИИС, ЛДВ, подсказки ──

TAX_SUM_KEYS = ("proceeds", "cost", "fees", "trade", "ldv_exempt", "ldv_saved", "carry_used", "loss_new", "trade_base", "dividends", "coupons",
                "overnight", "deriv", "base", "iis_exempt_used", "tax", "tax13", "tax15", "withheld", "broker_trade", "deposits", "withdrawals")


def tx_gkey(a):
    return "iis:" + a["id"] if a.get("type") == "ИИС" else "gen"


def tx_iis_info(a, setting, first_date, today):
    typ = setting.get("type") or ""
    opened = None
    for s in (setting.get("opened"), (a.get("opened") or "")[:10]):
        if s:
            try:
                opened = datetime.strptime(s[:10], "%Y-%m-%d").date()
                break
            except ValueError:
                pass
    if opened is None:
        opened = first_date
    eff = typ or "A"
    term = tx_add_years(opened, 5 if eff == "3" else 3) if opened else None
    return {"id": a["id"], "name": a["name"], "type": eff, "type_set": bool(typ), "opened": opened.isoformat() if opened else "",
            "term": term.isoformat() if term else "", "term_ok": bool(term and today >= term),
            "exempt": eff in ("B", "3") and bool(term and today >= term)}


def tx_sum_rows(per_group, exempt=None):
    """Итоги по годам. exempt — флаги групп, освобождённых от налога (ИИС с соблюдённым сроком): их база в общую не входит.
    Порог 15 % относится к совокупной базе налогоплательщика, а группы считаются по отдельности, поэтому налог по
    совокупной базе пересчитывается заново; превышение над суммой налогов групп — extra_progressive."""
    tot, comb = {}, defaultdict(float)
    for gi, rows in enumerate(per_group):
        for r in rows:
            if not (exempt and exempt[gi]):
                comb[r["year"]] += r["base"]
            elif r.get("iis_exempt_used") is not None:
                comb[r["year"]] += r["base"] - r["iis_exempt_used"]
            t = tot.setdefault(r["year"], {"year": r["year"], "w": defaultdict(float)})
            for k in TAX_SUM_KEYS:
                t[k] = t.get(k, 0.0) + r[k]
            for k, v in r["w"].items():
                t["w"][k] += v
    out = []
    for y in sorted(tot):
        t = tot[y]
        t["w"] = dict(t["w"])
        extra = tx_ndfl(comb[y], y)[0] - t["tax"]
        t["extra_progressive"] = extra if extra > 0.5 else 0.0
        t["diff"] = t["tax"] - t["withheld"]
        t["diff_pct"] = (t["diff"] / t["withheld"] * 100.0) if t["withheld"] > 1 else None
        out.append(t)
    return out


def tx_lines(sales, year):
    agg = {}
    for s in sales:
        if s["bucket"] != "sec" or s["sdate"].year != year:
            continue
        k = (s["uid"], s["kind"])
        a = agg.setdefault(k, {"name": s["name"], "ticker": s["ticker"], "type": s["type"], "kind": s["kind"], "qty": 0.0, "proceeds": 0.0,
                               "cost": 0.0, "fee": 0.0, "result": 0.0, "ldv_result": 0.0})
        for f in ("qty", "proceeds", "cost", "fee", "result"):
            a[f] += s[f]
        if s["ldv"]:
            a["ldv_result"] += s["result"]
    return sorted(agg.values(), key=lambda a: -abs(a["result"]))[:80]


def tx_pos_price(r):
    if not r or not r.get("qty"):
        return None
    p = r.get("price") or 0.0
    if r.get("value") and r.get("value_rub") is not None:
        p = p * r["value_rub"] / r["value"]
    return p or None


def tx_apply_splits(ops, names, today=None, splits=None, resolve_isin=None):
    """Применяет сплиты/консолидации Мосбиржи к операциям без дублирования уже вставленных пар split:*."""
    if not splits:
        return ops
    today = today or date.today()
    names = names or {}
    existing = set()
    by_key = {}
    dates = []
    for o in ops:
        d = (o.get("date") or "")[:10]
        if d:
            dates.append(d)
        acc = o.get("_acc") or ""
        uid = o.get("instrumentUid") or o.get("figi") or o.get("_ident") or ""
        info = names.get(uid) or names.get(o.get("figi") or "") or {}
        isin = info.get("isin") or o.get("isin") or o.get("_sec") or ""
        if (o.get("_conv") or {}).get("source") == "moex_split" or str(o.get("id") or "").startswith("split:"):
            if uid:
                existing.add((acc, uid, d))
            if isin:
                existing.add((acc, isin, d))
            continue
        k = classify(o.get("type"))
        if k not in ("buy", "sell", "sec_in", "sec_out", "conv_in", "conv_out", "repayments"):
            continue
        pk = pos_key(o)
        if not pk:
            continue
        itype = o.get("instrumentType") or info.get("type") or ""
        itype = {"bonds": "bond", "shares": "share"}.get(itype, itype) or "share"
        if itype in TAX_SKIP_TYPES or itype == "option":
            continue
        g = by_key.setdefault((acc, pk), {"acc": acc, "pk": pk, "ops": [], "uids": set(), "isins": set(), "tickers": set(),
                                          "uid": None, "pos": None, "figi": None, "kind": None, "itype": itype, "name": ""})
        g["ops"].append(o)
        if uid:
            g["uids"].add(uid)
            g["uid"] = uid
        if isin:
            g["isins"].add(isin)
        tk = info.get("ticker") or o.get("ticker") or ""
        if tk:
            g["tickers"].add(tk)
        g["pos"] = g["pos"] or o.get("positionUid")
        g["figi"] = g["figi"] or o.get("figi")
        g["kind"] = g["kind"] or o.get("instrumentKind")
        g["name"] = g["name"] or info.get("name") or o.get("name") or tk
    if not dates or not by_key:
        return ops
    d_from, d_to = min(dates), max(max(dates), today.isoformat())
    rows = [r for r in splits if r.get("date") and d_from <= r["date"] <= d_to and r.get("before") and r.get("after") and r["before"] != r["after"]]
    if not rows:
        return ops
    all_isins = {i for g in by_key.values() for i in g["isins"]}
    all_tickers = {t for g in by_key.values() for t in g["tickers"]}
    sec_isin = {}
    if resolve_isin and all_isins:
        need = sorted({r["secid"] for r in rows if r["secid"] not in all_isins and r["secid"] not in all_tickers and not ISIN_RE.match(r["secid"])})
        for sid in need:
            try:
                res = resolve_isin(sid)
                if res:
                    sec_isin[sid] = res
            except Exception:  # noqa: BLE001
                pass
    out = list(ops)
    zero = to_money(0, "rub")
    qs = lambda x: str(int(x)) if x == int(x) else repr(x)
    for g in by_key.values():
        evs = []
        for r in rows:
            sid = r["secid"]
            if sid in g["isins"] or sid in g["tickers"] or (sec_isin.get(sid) and sec_isin[sid] in g["isins"]):
                evs.append((r["date"], float(r["after"]) / float(r["before"]), float(r["before"]), float(r["after"])))
        if not evs:
            continue
        evs.sort(key=lambda x: x[0])
        gops = sorted(g["ops"], key=lambda o: o.get("date") or "")
        for idx, (day, ratio, before, after) in enumerate(evs):
            if any((g["acc"], u, day) in existing for u in g["uids"] | g["isins"]):
                continue
            qty, ei = 0.0, 0
            for o in gops:
                d = (o.get("date") or "")[:10]
                if d >= day:
                    break
                while ei < idx and evs[ei][0] <= d:
                    qty *= evs[ei][1]
                    ei += 1
                k, q = classify(o.get("type")), op_qty(o)
                if k in ("buy", "sec_in", "conv_in"):
                    qty += q
                elif k in ("sell", "sec_out", "conv_out"):
                    qty -= q
                elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL":
                    qty = 0.0
            while ei < idx:
                qty *= evs[ei][1]
                ei += 1
            if qty <= 1e-6:
                continue
            new_q = qty * ratio
            new_q = int(round(new_q)) if abs(new_q - round(new_q)) < 1e-6 else round(new_q, 6)
            uid = g["uid"]
            cv = {"from_key": uid, "to_key": uid, "ratio": ratio, "label": split_label(before, after), "source": "moex_split",
                  "old_uids": sorted(g["uids"]) or [uid], "new_uid": uid, "old_qty": qty, "new_qty": new_q}
            base = {"date": day + "T00:00:01Z", "state": "OPERATION_STATE_EXECUTED", "payment": dict(zero), "_acc": g["acc"],
                    "_conv": cv, "name": g["name"], "instrumentUid": uid, "positionUid": g["pos"], "figi": g["figi"],
                    "instrumentKind": g["kind"] or "INSTRUMENT_TYPE_SHARE", "instrumentType": g["itype"]}
            cid = "split:%s:%s:%s" % (g["acc"], g["pk"], day)
            out.append(dict(base, id=cid + ":out", type="OPERATION_TYPE_X_CONV_OUT", quantity=qs(qty), quantityDone=qs(qty)))
            out.append(dict(base, id=cid + ":in", date=day + "T00:00:02Z", type="OPERATION_TYPE_X_CONV_IN",
                            quantity=qs(new_q), quantityDone=qs(new_q)))
    out.sort(key=lambda o: o.get("date") or "")
    return out


def tax_compute(ops, names, positions, sel, settings, fx=None, today=None, resolve=None, splits=None, resolve_isin=None):
    """Чистая часть расчёта (без сети): ops + позиции + выбранные счета -> структура состояния."""
    today = today or date.today()
    pos = {}
    for r in positions or []:
        if r.get("type") not in ("currency", "futures") and r.get("uid"):
            pos[r["uid"]] = r
    held = {u: r["qty"] for u, r in pos.items()} if pos else None
    events = find_conversions(ops, names, held, resolve=resolve)
    ops = apply_conversions(ops, events)
    ops = tx_apply_splits(ops, names, today=today, splits=splits, resolve_isin=resolve_isin)
    eng = tax_engine(ops, names, fx, held)
    accs = {a["id"]: a for a in sel}
    groups = {}
    for a in sel:
        g = groups.setdefault(tx_gkey(a), {"key": tx_gkey(a), "accounts": []})
        g["accounts"].append(a["id"])
    first_by_acc = {}
    for o in ops:
        d = parse_dt(o.get("date")).date()
        k = o.get("_acc") or ""
        if k not in first_by_acc or d < first_by_acc[k]:
            first_by_acc[k] = d
    out_groups, per_rows, iis_list, per_exempt = [], [], [], []
    off = settings.get("offset_coupons", False)
    for gk, g in groups.items():
        ids = set(g["accounts"])
        sales = [s for s in eng["sales"] if s["acc"] in ids]
        inc = defaultdict(lambda: defaultdict(float))
        for (acc, y), v in eng["inc"].items():
            if acc in ids:
                for k, x in v.items():
                    inc[y][k] += x
        exempt = False
        iis_limit = TAX_IIS3_EXEMPT_LIMIT
        if gk == "gen":
            g["name"] = "Обычные счета" if len(ids) > 1 else accs[g["accounts"][0]]["name"]
            g["kind"] = "gen"
        else:
            a = accs[g["accounts"][0]]
            iinfo = tx_iis_info(a, settings["iis"].get(a["id"]) or {}, first_by_acc.get(a["id"]), today)
            iis_list.append(iinfo)
            exempt = iinfo["exempt"]
            iis_limit = TAX_IIS3_EXEMPT_LIMIT if iinfo["type"] == "3" else None
            g["name"] = "ИИС: " + a["name"]
            g["kind"] = "iis"
            g["iis"] = iinfo
            sales = [dict(s, ldv=False, yrs=0) for s in sales]
        rows, pool = tax_group_years(sales, inc, settings["loss_carry"] if gk == "gen" else None, exempt, None, off, iis_limit)
        g["rows"], g["pool"], g["sales"], g["inc"] = rows, pool, sales, inc
        per_rows.append(rows)
        per_exempt.append(exempt)
        out_groups.append(g)
    return {"eng": eng, "groups": out_groups, "years": tx_sum_rows(per_rows, per_exempt), "iis": iis_list, "pos": pos, "today": today, "accs": accs,
            "conversions": conversions_view(events)}


def tx_ldv_tables(st):
    """Будущие и уже наступившие ЛДВ по открытым лотам (только обычные счета: на ИИС ЛДВ не применяется)."""
    today = st["today"]
    gen_ids = set(a for g in st["groups"] if g["kind"] == "gen" for a in g["accounts"])
    cy = today.year
    cur_base = 0.0
    for g in st["groups"]:
        if g["kind"] == "gen":
            for r in g["rows"]:
                if r["year"] == cy:
                    cur_base = r["base"]
    rate = 0.15 if cur_base > (2400000.0 if cy >= 2025 else 5000000.0) else 0.13
    groups, ready = {}, {}
    for l in st["eng"]["open"]:
        if l["acc"] not in gen_ids or l["type"] not in TAX_LDV_TYPES or l["blind"] or not l["date"] or l["date"] < TAX_LDV_FROM:
            continue
        pr = tx_pos_price(st["pos"].get(l["uid"]))
        value = l["qty"] * pr if pr else None
        cost = l["qty"] * l["unit"]
        frm = tx_add_years(l["date"], 3) + timedelta(days=1)
        days = (frm - today).days
        tgt = ready if days <= 0 else groups
        k = l["uid"] if days <= 0 else (l["uid"], frm)
        acc_name = ((st.get("accs") or {}).get(l["acc"]) or {}).get("name") or l["acc"]
        e = tgt.setdefault(k, {"uid": l["uid"], "name": l["name"], "ticker": l["ticker"], "type": l["type"], "date": frm.isoformat(), "days": days,
                               "qty": 0.0, "cost": 0.0, "value": 0.0, "gain": 0.0, "known": True, "_accs": set()})
        if acc_name:
            e["_accs"].add(acc_name)
        e["qty"] += l["qty"]
        e["cost"] += cost
        if value is None:
            e["known"] = False
        else:
            e["value"] += value
            e["gain"] += value - cost
    up = sorted(groups.values(), key=lambda e: e["days"])
    for e in up + list(ready.values()):
        e["acc"] = ", ".join(sorted(e.pop("_accs", ())))
        e["tax_now"] = max(0.0, e["gain"]) * rate if e["known"] else None
    return up, sorted(ready.values(), key=lambda e: -e["gain"]), rate


def tx_fee_sim(lots, qty, price, fee_rate, today, base):
    cp = [dict(l) for l in sorted(lots, key=lambda l: l["date"] or date(1970, 1, 1))]
    rows, _ = tx_sell(cp, qty, qty * price, qty * price * fee_rate, today, dict(base, sdate=today))
    return rows


def tx_group_open(st, g):
    ids = set(g["accounts"])
    by = defaultdict(list)
    for l in st["eng"]["open"]:
        if l["acc"] in ids:
            by[l["uid"]].append(l)
    return by


def tx_cur_tax(g, extra, cy, settings):
    """Налог текущего года по группе с дополнительными (гипотетическими) продажами."""
    exempt = g["kind"] == "iis" and g["iis"]["exempt"]
    iis_limit = TAX_IIS3_EXEMPT_LIMIT if g["kind"] == "iis" and g["iis"]["type"] == "3" else None
    rows, _ = tax_group_years(g["sales"], g["inc"], settings["loss_carry"] if g["kind"] == "gen" else None, exempt, extra, settings.get("offset_coupons", False), iis_limit)
    for r in rows:
        if r["year"] == cy:
            return r["tax"], r
    return 0.0, None


def tx_hints(st, settings):
    today, cy = st["today"], st["today"].year
    fee_rate = st["eng"]["fee_rate"]
    up, rd, rate = tx_ldv_tables(st)
    out = {"year": cy, "days_left": (date(cy, 12, 31) - today).days, "harvest": [], "harvest_total": 0.0, "ldv_warn": [], "notes": [],
           "spread": TAX_SPREAD, "fee_rate": fee_rate}
    for e in up:
        if e["days"] <= 365 and e["known"] and e["gain"] > 0 and e["tax_now"] and e["tax_now"] > 50:
            out["ldv_warn"].append(e)
    for g in st["groups"]:
        if g["kind"] == "iis" and g["iis"]["type"] != "A":
            continue
        t0, row0 = tx_cur_tax(g, [], cy, settings)
        if not row0 or t0 <= 1:
            continue
        cands = []
        for uid, lots in tx_group_open(st, g).items():
            pr = tx_pos_price(st["pos"].get(uid))
            if not pr or lots[0]["type"] in TAX_SKIP_TYPES:
                continue
            q = sum(l["qty"] for l in lots)
            base = {"acc": lots[0]["acc"], "uid": uid, "name": lots[0]["name"], "ticker": lots[0]["ticker"], "type": lots[0]["type"],
                    "bucket": "deriv" if lots[0]["type"] == "option" else "sec", "kind": "sell", "bdate": None}
            rows = tx_fee_sim(lots, q, pr, fee_rate, today, base)
            res = sum(r["result"] for r in rows)
            if res >= -50:
                continue
            value = q * pr
            t1, _ = tx_cur_tax(g, rows, cy, settings)
            cost = value * (fee_rate + TAX_SPREAD)
            cands.append({"uid": uid, "name": base["name"], "ticker": base["ticker"], "type": base["type"], "group": g["key"], "gname": g["name"],
                          "qty": q, "value": value, "loss": -res, "saving": t0 - t1, "cost": cost, "net": t0 - t1 - cost, "rows": rows,
                          "ldv_lost": any(r["ldv"] for r in rows) or any(l["date"] and (tx_add_years(l["date"], 3) - today).days < 120 for l in lots if not l.get("blind"))})
        cands.sort(key=lambda c: -c["net"])
        chosen, extra = [], []
        for c in cands:
            if c["net"] <= 1:
                continue
            t_prev, _ = tx_cur_tax(g, extra, cy, settings)
            t_new, _ = tx_cur_tax(g, extra + c["rows"], cy, settings)
            if (t_prev - t_new) - c["cost"] > 1:
                extra = extra + c["rows"]
                chosen.append(c)
        if chosen:
            t_all, _ = tx_cur_tax(g, extra, cy, settings)
            out["harvest_total"] += (t0 - t_all) - sum(c["cost"] for c in chosen)
        for c in cands:
            c.pop("rows", None)
            if c["net"] > 1:
                out["harvest"].append(c)
    out["harvest"].sort(key=lambda c: -c["net"])
    out["harvest"] = out["harvest"][:25]
    if not out["harvest"]:
        out["notes"].append("Позиций с убытком, продажа которых уменьшила бы налог текущего года, не найдено (или налога за этот год пока нет).")
    return out


