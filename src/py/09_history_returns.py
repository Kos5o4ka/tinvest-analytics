# ═══════════════════════════════ история стоимости и доходность ═══════════════════════════════

SPLIT_FACTORS = (2, 3, 4, 5, 8, 10, 15, 20, 25, 40, 50, 100, 200, 500, 1000, 5000, 10000)


def pos_key(o):
    """Ключ позиции. Одна бумага в операциях встречается под разными instrumentUid (до/после допуска к торгам,
    другой режим торгов, TCS00/TCS90): покупка под одним, продажа и купоны под другим — по instrumentUid остаётся
    «вечная» длинная позиция и такая же короткая. positionUid у них общий."""
    return o.get("positionUid") or o.get("instrumentUid") or o.get("figi")


def split_scale(ratio):
    """Отношение цены сделки к цене закрытия того же дня. Свечи API пересчитаны на сплиты и консолидации
    (VTBR 5000:1, PLZL, TRNFP 100:1), а количество в операциях — на момент сделки. Возвращает множитель N или 1/N,
    1.0 — цены согласуются, None — разница не похожа на сплит."""
    if 0.6 <= ratio <= 1.7:
        return 1.0
    if ratio <= 0:
        return None
    big = ratio >= 1
    x = ratio if big else 1.0 / ratio
    n = min(SPLIT_FACTORS, key=lambda f: abs(f - x))
    if abs(x / n - 1) > 0.1:
        return None
    return float(n) if big else 1.0 / n


def drop_spikes(rows, limit):
    """Одиночные ошибочные закрытия: цена ушла больше чем на limit и на следующей свече вернулась (в пределах limit/3)."""
    if len(rows) < 3:
        return rows
    out = [rows[0]]
    for i in range(1, len(rows) - 1):
        a, b, c = out[-1][1], rows[i][1], rows[i + 1][1]
        if a > 0 and abs(b / a - 1) > limit and abs(c / a - 1) < limit / 3:
            continue
        out.append(rows[i])
    out.append(rows[-1])
    return out


def amort_events(bz, ops_ev, today):
    """События амортизации [(дата зачисления, сумма на бумагу)]. График MOEX, дата заменяется датой реальной выплаты
    из операций (в пределах недели, сумма +-3%): деньги приходят позже даты графика, и номинал должен снижаться
    в тот же день, когда деньги попали в кэш. События без пары в операциях (до покупки / после продажи) — по графику."""
    ev, used = [], set()
    for r in (bz or {}).get("amort") or []:
        d, v = r.get("amortdate"), r.get("value")
        if not d or not v or d > today:
            continue
        hit = None
        for i, (od, ov) in enumerate(ops_ev):
            if i in used or not ov:
                continue
            if abs((datetime.strptime(od, "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days) <= 7 and abs(ov / v - 1) < 0.03:
                hit = i
                break
        if hit is not None:
            used.add(hit)
            ev.append((ops_ev[hit][0], float(v)))
        else:
            ev.append((d, float(v)))
    if not bz:
        ev = [(d, v) for i, (d, v) in enumerate(ops_ev)]
    return sorted(ev)


def build_history(client, ops, names, actual_total, held_qty=None):
    ops = sorted([o for o in ops if o.get("date")], key=lambda o: o["date"])
    if not ops:
        return None
    # обмены бумаг (ГДР -> акции и т.п.), которых нет в операциях API
    events = find_conversions(ops, names, held_qty, resolve=(lambda t: benchmark_uid(client, t)) if client.ready else None)
    if events:
        ops = apply_conversions(ops, events)
        need = {(e["new_uid"], None) for e in events if e.get("new_uid") and e["new_uid"] not in (names or {})}
        if need and client.ready:
            try:
                names = dict(names, **instruments(client, need))
            except ApiError:
                pass
    start = ops[0]["date"][:10]
    today = date.today().isoformat()
    by_day = defaultdict(list)
    held, qty = {}, defaultdict(int)
    members = {}                      # ключ позиции -> все instrumentUid/figi, под которыми она встречается
    for o in ops:
        d = o["date"][:10]
        by_day[d].append(o)
        k = classify(o.get("type"))
        uid = pos_key(o)
        if not uid:
            continue
        mu = o.get("instrumentUid") or o.get("figi")
        if mu and mu not in members.setdefault(uid, []):
            members[uid].append(mu)
        q = op_qty(o)
        if k in ("buy", "sec_in", "conv_in"):
            qty[uid] += q
        elif k in ("sell", "sec_out", "conv_out"):
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

    def mnames(g):
        return [names.get(u) or {} for u in members.get(g) or [g]]

    def itype(g):
        for i in mnames(g):
            if i.get("type"):
                return i["type"]
        for o in ops:
            if pos_key(o) == g and o.get("instrumentKind"):
                return TYPE_FROM_KIND.get(o["instrumentKind"], "")
        return ""

    def first_bond(g):
        for u in members.get(g) or [g]:
            b = bond_info(client, u)
            if b:
                return b
        return None

    types = {u: itype(u) for u in held}
    real = [u for u in held if not u.startswith("imp:") and types[u] not in ("futures", "option")]
    bond_ids = [u for u in real if types[u] == "bond"]
    bonds = dict(zip(bond_ids, pool_map(first_bond, bond_ids)))
    # номинал амортизируемых облигаций на дату: график MOEX + фактические выплаты из операций
    amort = {}
    for g in bond_ids:
        b = bonds.get(g)
        if not b or not b.get("amort"):
            continue
        ops_ev = []
        for o in ops:
            if pos_key(o) == g and classify(o.get("type")) == "repayments" and op_type(o) == "BOND_REPAYMENT":
                q = sum(op_qty(x) * (1 if classify(x.get("type")) == "buy" else -1) for x in ops
                        if pos_key(x) == g and classify(x.get("type")) in ("buy", "sell") and x["date"] <= o["date"])
                if q > 0:
                    ops_ev.append((o["date"][:10], qf(o.get("payment")) / q))
        isin = next((i.get("isin") for i in mnames(g) if i.get("isin")), None)
        bz = moex_bondization(isin) if (isin and client.ready) else None
        amort[g] = amort_events(bz, ops_ev, today)
    # купон в операциях приходит на день-два позже даты графика (T+1, выходные): пока деньги не в кэше, НКД не обнуляем
    cpn_ops = defaultdict(list)
    for o in ops:
        if classify(o.get("type")) == "coupons" and pos_key(o):
            cpn_ops[pos_key(o)].append(o["date"][:10])
    cpn_win = {}
    for g in bond_ids:
        b = bonds.get(g)
        if b and b.get("coupons") and cpn_ops.get(g):
            cpn_ops[g].sort()
            cpn_win[g] = [(c[0], (datetime.strptime(c[0], "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"),
                           (datetime.strptime(c[0], "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")) for c in b["coupons"]]

    def nkd_day(g, day):
        w = cpn_win.get(g)
        if w:
            i = bisect.bisect_right(w, (day, "~", "~")) - 1
            if i >= 0 and day <= w[i][2]:
                co = cpn_ops[g]
                j = bisect.bisect_right(co, day)
                if j < len(co) and co[j] <= w[i][2]:
                    return w[i][1]
        return day

    inst_cur = {g: next((i.get("cur") for i in mnames(g) if i.get("cur")), None) or "rub" for g in held}
    for u in held:
        if types[u] == "currency":
            inst_cur[u] = "rub"
    curs = {c for c in inst_cur.values()} | {cur_of(o.get("payment")) for o in ops}
    fxu = {c: fx_uid(client, c) for c in curs if c != "rub"}
    for u in held:  # валютные инструменты в портфеле — тоже источник курса
        if types[u] == "currency":
            iso = next((i.get("ticker") for i in mnames(u) if i.get("ticker")), "")[:3].lower()
            if iso and iso != "rub" and not fxu.get(iso):
                fxu[iso] = u
    want = {}                         # свечи нужны под каждым uid позиции (цены есть не у всех)
    for g in real:
        for u in members.get(g) or [g]:
            want[u] = list(held[g])
    extra = [u for u in fxu.values() if u and u not in held]
    bench = {}
    for t in ("LQDT", "TMOS"):
        u = benchmark_uid(client, t) if client.ready else None
        if u:
            bench[t] = u
            extra.append(u)
    for u in extra:
        want[u] = [start, today]
    jobs = [(u, r[0], r[1]) for u, r in want.items()]
    series = dict(zip([j[0] for j in jobs], pool_map(lambda j: candle_series(client, *j), jobs)))
    closes = {}
    for g in real:                    # цены из всех uid бумаги; приоритет у uid с самым длинным рядом
        merged = {}
        for u in sorted(members.get(g) or [g], key=lambda u: len(series.get(u) or ())):
            merged.update(dict(series.get(u) or ()))
        rows = sorted(merged.items())
        closes[g] = dict(drop_spikes(rows, 0.05 if types[g] == "bond" else 0.3))
    for u in extra:
        closes[u] = dict(series.get(u) or ())

    last_close, fallback, cash, scale = {}, {}, defaultdict(float), {}
    qty = defaultdict(float)          # количество в «единицах свечи» (с учётом сплитов)
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

    def nominal_at(u, b, day):
        nom = b.get("nominal") or 1000.0
        return nom + sum(a for da, a in amort.get(u, ()) if da > day)

    def unit(u, day):
        c = last_close.get(u)
        t = types.get(u)
        if c is None:
            return fallback.get(u, 0.0)
        if t == "bond":
            b = bonds.get(u)
            if not b:
                return fallback.get(u, c * 10.0)
            return c / 100.0 * nominal_at(u, b, day) + nkd_at(b, nkd_day(u, day))
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
            k = classify(o.get("type"))
            uid = pos_key(o)
            # сделки с фьючерсами/опционами: payment — условная стоимость контракта, деньги движутся через
            # вариационную маржу (отдельные операции); считать payment деньгами — значит выдумать скачки на ±цену контракта
            if not (k in ("buy", "sell") and uid and types.get(uid) in ("futures", "option")):
                cash[c] += pay
            q = op_qty(o)
            sc = scale.get(uid, 1.0)
            if uid and q and k in ("buy", "sell") and pay:
                r = fx(c) or 1.0
                cl, mr = last_close.get(uid), fx(inst_cur.get(uid, "rub"))
                if cl and mr and (c == "rub" or fx(c)) and types.get(uid) not in ("bond", "currency", "futures", "option"):
                    f = split_scale(abs(pay) / q * r / (cl * mr))
                    if f is not None:
                        sc = scale[uid] = f
                fallback[uid] = abs(pay) / q / sc * r
            if k == "conv_in" and uid and q:
                # у новой бумаги ещё нет своих сделок для определения сплита: сравниваем цену старой бумаги (за вычетом
                # коэффициента) с ценой новой на день обмена — как для обычных сделок
                cv = o.get("_conv") or {}
                fk = cv.get("from_key")
                if last_close.get(uid) and types.get(uid) not in ("bond", "currency", "futures", "option"):
                    nu, ou = unit(uid, ds), unit(fk, ds) if fk else 0.0
                    f = split_scale(ou * scale.get(fk, 1.0) / (cv.get("ratio") or 1) / nu) if nu and ou else None
                    if f is not None:
                        sc = scale[uid] = f
            qa = q * sc
            if k in ("buy", "sec_in") and uid:
                qty[uid] = round(qty[uid] + qa, 6)
            elif k in ("sell", "sec_out") and uid:
                qty[uid] = round(qty[uid] - qa, 6)
            elif k == "conv_out" and uid:
                qty[uid] = 0                  # обмен: вся позиция уходит без денежного потока
            elif k == "conv_in" and uid:
                qty[uid] = round(qty[uid] + qa, 6)
            elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL" and uid:
                qty[uid] = 0
            if k in ("deposits", "withdrawals"):
                flow += pay * (fx(c) or 0.0)
            elif k in ("sec_in", "sec_out") and uid and q:
                flow += (qa if k == "sec_in" else -qa) * unit(uid, ds)
        v = sum(a * (fx(c) or 0.0) for c, a in cash.items())
        for u, q in qty.items():
            if q and types.get(u) not in ("futures", "option"):
                v += q * unit(u, ds)
        invested += flow
        base = v_prev + max(flow, 0.0)
        r = (v - flow - v_prev) / base if base > 1000 else 0.0
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
            "recon": {"calc": vals[-1] if vals else 0, "actual": actual_total}, "glitches": glitches,
            "conversions": conversions_view(events)}


