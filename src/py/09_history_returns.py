# ═══════════════════════════════ история стоимости и доходность ═══════════════════════════════

def build_history(client, ops, names, actual_total):
    ops = sorted([o for o in ops if o.get("date")], key=lambda o: o["date"])
    if not ops:
        return None
    start = ops[0]["date"][:10]
    today = date.today().isoformat()
    by_day = defaultdict(list)
    held, qty = {}, defaultdict(int)
    for o in ops:
        d = o["date"][:10]
        by_day[d].append(o)
        k = classify(o.get("type"))
        uid = o.get("instrumentUid") or o.get("figi")
        if not uid:
            continue
        q = op_qty(o)
        if k in ("buy", "sec_in"):
            qty[uid] += q
        elif k in ("sell", "sec_out"):
            qty[uid] -= q
        elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL":
            qty[uid] = 0
        else:
            continue
        rng = held.setdefault(uid, [d, d])
        rng[1] = today if qty[uid] else d
    for uid in held:
        if qty[uid]:
            held[uid][1] = today

    def itype(uid):
        info = names.get(uid) or {}
        if info.get("type"):
            return info["type"]
        for o in ops:
            if (o.get("instrumentUid") or o.get("figi")) == uid and o.get("instrumentKind"):
                return TYPE_FROM_KIND.get(o["instrumentKind"], "")
        return ""

    types = {u: itype(u) for u in held}
    real = [u for u in held if not u.startswith("imp:") and types[u] not in ("futures", "option")]
    bonds = dict(zip([u for u in real if types[u] == "bond"],
                     pool_map(lambda u: bond_info(client, u), [u for u in real if types[u] == "bond"])))
    inst_cur = {u: (names.get(u) or {}).get("cur") or "rub" for u in held}
    for u in held:
        if types[u] == "currency":
            inst_cur[u] = "rub"
    curs = {c for c in inst_cur.values()} | {cur_of(o.get("payment")) for o in ops}
    fxu = {c: fx_uid(client, c) for c in curs if c != "rub"}
    for u in held:  # валютные инструменты в портфеле — тоже источник курса
        if types[u] == "currency":
            iso = ((names.get(u) or {}).get("ticker") or "")[:3].lower()
            if iso and iso != "rub" and not fxu.get(iso):
                fxu[iso] = u
    jobs = [(u, held[u][0], held[u][1]) for u in real] + [(u, start, today) for u in fxu.values() if u and u not in held]
    bench = {}
    for t in ("LQDT", "TMOS"):
        u = benchmark_uid(client, t) if client.ready else None
        if u:
            bench[t] = u
            if u not in held:
                jobs.append((u, start, today))
    series = dict(zip([j[0] for j in jobs], pool_map(lambda j: candle_series(client, *j), jobs)))
    closes = {u: dict(rows) for u, rows in series.items()}

    last_close, fallback, cash = {}, {}, defaultdict(float)
    qty = defaultdict(int)
    out_days, vals, inv, rets = [], [], [], []
    bench_vals = {t: [] for t in bench}
    v_prev, invested, glitches = 0.0, 0.0, 0
    d = datetime.strptime(start, "%Y-%m-%d").date()
    end = date.today()

    def fx(c):
        if c == "rub":
            return 1.0
        u = fxu.get(c)
        return last_close.get(u) if u else None

    def unit(u, day):
        c = last_close.get(u)
        t = types.get(u)
        if c is None:
            return fallback.get(u, 0.0)
        if t == "bond":
            b = bonds.get(u)
            if not b:
                return fallback.get(u, c * 10.0)
            return c / 100.0 * (b.get("nominal") or 1000.0) + nkd_at(b, day)
        r = fx(inst_cur.get(u, "rub"))
        return c * (r if r is not None else 1.0)

    while d <= end:
        ds = d.isoformat()
        for u, cl in closes.items():
            if ds in cl:
                last_close[u] = cl[ds]
        flow = 0.0
        for o in by_day.get(ds, ()):
            pay, c = qf(o.get("payment")), cur_of(o.get("payment"))
            cash[c] += pay
            k = classify(o.get("type"))
            uid = o.get("instrumentUid") or o.get("figi")
            q = op_qty(o)
            if uid and q and k in ("buy", "sell") and pay:
                r = fx(c) or 1.0
                fallback[uid] = abs(pay) / q * r
            if k in ("buy", "sec_in") and uid:
                qty[uid] += q
            elif k in ("sell", "sec_out") and uid:
                qty[uid] -= q
            elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL" and uid:
                qty[uid] = 0
            if k in ("deposits", "withdrawals"):
                flow += pay * (fx(c) or 0.0)
            elif k in ("sec_in", "sec_out") and uid and q:
                flow += (q if k == "sec_in" else -q) * unit(uid, ds)
        v = sum(a * (fx(c) or 0.0) for c, a in cash.items())
        for u, q in qty.items():
            if q and types.get(u) not in ("futures", "option"):
                v += q * unit(u, ds)
        invested += flow
        base = v_prev + max(flow, 0.0)
        r = (v - flow - v_prev) / base if base > 100 else 0.0
        if abs(r) > 0.3:
            glitches += 1
            r = 0.0
        out_days.append(ds)
        vals.append(round(v, 2))
        inv.append(round(invested, 2))
        rets.append(r)
        for t, u in bench.items():
            bench_vals[t].append(last_close.get(u))
        v_prev = v
        d += timedelta(days=1)

    monthly = defaultdict(lambda: 1.0)
    for ds, r in zip(out_days, rets):
        monthly[ds[:7]] *= 1 + r
    twr, acc = [], 1.0
    for r in rets:
        acc *= 1 + r
        twr.append(round(acc, 6))
    return {"days": out_days, "value": vals, "invested": inv, "twr": twr,
            "bench": {t: v for t, v in bench_vals.items() if any(x is not None for x in v)},
            "monthly": {m: round(x - 1, 6) for m, x in monthly.items()},
            "recon": {"calc": vals[-1] if vals else 0, "actual": actual_total}, "glitches": glitches}


