def _ld_when(y):
    return ("%.1f" % y).replace(".", ",") + " г."


def _safe_call(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001
        return None


# ───── лесенка текущего портфеля: сколько денег и когда возвращается ─────

LD_HEAVY = 1.5            # период «перегружен», если сумма больше среднего во столько раз
LD_QUARTERS_UNTIL = 1     # кварталами показываем текущий и следующий календарные годы, дальше — годами


def _ld_qkey(d):
    return "%s-Q%d" % (d[:4], (int(d[5:7]) - 1) // 3 + 1)


def _ld_pkey(d, today, gran):
    if gran == "quarter" and int(d[:4]) <= int(today[:4]) + LD_QUARTERS_UNTIL:
        return _ld_qkey(d)
    return d[:4]


def _ld_plabel(key):
    return ("%s кв. %s" % (key[6], key[:4])) if "-Q" in key else key


def _ld_pspan(today, gran, keys):
    """Все периоды от первого до последнего непрерывно: кварталы текущего и следующего года, затем годы."""
    if not keys:
        return []
    y0 = int(today[:4])
    out = []
    if gran == "quarter":
        q0 = (int(today[5:7]) - 1) // 3
        for y in range(y0, y0 + LD_QUARTERS_UNTIL + 1):
            for q in range(q0 if y == y0 else 0, 4):
                out.append("%d-Q%d" % (y, q + 1))
        last_y = max(int(k[:4]) for k in keys)
        last_q = max([k for k in keys if "-Q" in k] or [""])
        if last_y <= y0 + LD_QUARTERS_UNTIL:                       # хвост без событий не показываем
            out = [k for k in out if k <= last_q] or out[:1]
        out += [str(y) for y in range(y0 + LD_QUARTERS_UNTIL + 1, last_y + 1)]
        return out
    ys = sorted(int(k[:4]) for k in keys)
    return [str(y) for y in range(ys[0], ys[-1] + 1)]


def ld_buckets(items, today, gran="year"):
    """items: [{isin, name, ytm, events: [{date, type, amount}]}] -> периоды лесенки.
    Период: {key, label, kind, total, share, flag ('heavy'|'gap'|None), by_type, items}.
    heavy — сумма больше LD_HEAVY * среднего по периодам того же размера (между первым и последним непустым), gap — пустой период внутри."""
    grp = defaultdict(list)
    for it in items:
        for ev in it["events"]:
            if ev["date"] > today and ev["amount"] > 0:
                grp[_ld_pkey(ev["date"], today, gran)].append((it, ev))
    grand = sum(ev["amount"] for v in grp.values() for _, ev in v)
    periods = []
    for key in _ld_pspan(today, gran, list(grp)):
        rows, by, called = {}, {"redemption": 0.0, "offer": 0.0, "amort": 0.0}, 0.0
        for it, ev in grp.get(key, []):
            r = rows.setdefault((it["isin"], ev["type"]), {"isin": it["isin"], "name": it["name"], "date": ev["date"], "type": ev["type"],
                                                           "amount": 0.0, "n": 0, "ytm": it.get("ytm"), "call": None, "call_kind": None, "call_amount": 0.0})
            r["amount"] += ev["amount"]
            if ev.get("call"):                       # возможен досрочный возврат по колл (решает эмитент)
                r["call"], r["call_kind"] = ev["call"], ev.get("call_kind")
                r["call_amount"] += ev["amount"]
                called += ev["amount"]
            r["n"] += 1
            r["date"] = min(r["date"], ev["date"])
            by[ev["type"]] += ev["amount"]
        lst = sorted(rows.values(), key=lambda r: (r["date"], r["name"]))
        tot = sum(r["amount"] for r in lst)
        for r in lst:
            r["pct"] = r["amount"] / grand * 100.0 if grand else 0.0
        periods.append({"key": key, "label": _ld_plabel(key), "kind": "q" if "-Q" in key else "y", "total": tot,
                        "share": tot / grand * 100.0 if grand else 0.0, "flag": None, "by_type": by, "callable": called, "items": lst})
    first_any = next((i for i, p in enumerate(periods) if p["total"] > 0), len(periods))
    for kind in ("q", "y"):
        ps = [p for p in periods if p["kind"] == kind]
        nz = [i for i, p in enumerate(ps) if p["total"] > 0]
        if len(nz) < 1:
            continue
        span = ps[nz[0]:nz[-1] + 1]
        avg = sum(p["total"] for p in span) / float(len(span)) if span else 0.0
        for i, p in enumerate(ps):
            if p["total"] <= 0:
                if nz[0] < i < nz[-1] or (kind == "y" and first_any < periods.index(p) and i < nz[-1]):
                    p["flag"] = "gap"
            elif len(span) >= 3 and p["total"] > LD_HEAVY * avg:
                p["flag"] = "heavy"
    return periods


def ld_summary(items, today, years):
    """Плашки: средний срок (по сумме возврата), ближайшая выплата, самый тяжёлый год, пустые годы."""
    evs = [(ev["date"], ev["amount"], it["name"]) for it in items for ev in it["events"] if ev["date"] > today and ev["amount"] > 0]
    tot = sum(a for _, a, _ in evs)
    avg = sum(_of_days(today, d) / 365.25 * a for d, a, _ in evs) / tot if tot else None
    nxt = None
    if evs:
        d0 = min(d for d, _, _ in evs)
        nxt = {"date": d0, "amount": sum(a for d, a, _ in evs if d == d0), "names": sorted({n for d, _, n in evs if d == d0})}
    heavy = max([p for p in years if p["total"] > 0], key=lambda p: p["total"], default=None)
    cal = [(ev["amount"], ev.get("call_kind")) for it in items for ev in it["events"] if ev["date"] > today and ev["amount"] > 0 and ev.get("call")]
    callable_ = {"amount": sum(a for a, _ in cal), "share": sum(a for a, _ in cal) / tot * 100.0 if tot else 0.0,
                 "count": len({it["isin"] for it in items for ev in it["events"] if ev["date"] > today and ev.get("call")}),
                 "unknown_amount": sum(a for a, k in cal if k == "unknown")}
    return {"total": tot, "avg_years": avg, "next": nxt, "callable": callable_,
            "heavy": {"label": heavy["label"], "share": heavy["share"], "total": heavy["total"], "flag": heavy["flag"]} if heavy else None,
            "gaps": [p["label"] for p in years if p["flag"] == "gap"]}


def ld_events(maturity, call, nominal, qty, k, amort, today, use_offer):
    """События возврата денег по одной бумаге: амортизации + погашение, либо + оферта вместо погашения. Суммы в рублях.
    call — дата ПУТ-оферты (колл сюда не передаётся: эмитент может не воспользоваться правом, ступень стоит на погашении)."""
    cut = call if use_offer and call and today < call and (not maturity or call < maturity) else None
    end = cut or maturity
    if not end or end <= today:
        return []
    out, paid = [], 0.0
    for ad, av in sorted(amort or []):
        if not ad or not av or ad <= today or ad >= end:
            continue
        paid += av
        out.append({"date": ad, "type": "amort", "amount": av * qty * k})
    out.append({"date": end, "type": "offer" if cut else "redemption", "amount": max(nominal - paid, 0.0) * qty * k})
    return out


def ladder_portfolio(cfg, acc="all"):
    rep = build_bonds(cfg, acc)
    today = date.today().isoformat()
    rows = [r for r in rep.get("rows", []) if r.get("qty") and r.get("nominal") and (r.get("maturity") or r.get("call"))]
    value = sum(r.get("value_rub") or 0.0 for r in rep.get("rows", []))
    if not rows:
        return {"today": today, "empty": True, "value": value, "variants": {}, "has_offers": False, "has_calls": False, "undated": []}

    def bz_of(r):
        return _safe_call(moex_bondization, r["isin"]) if r.get("isin") else None
    bzs = pool_map(bz_of, rows, workers=8)
    has_offers, has_calls, undated, built = False, False, [], {"offer": [], "maturity": []}
    for r, bz in zip(rows, bzs):
        k = 1.0
        if (r.get("face_cur") or "rub") != "rub":                     # номинал в валюте -> рубли по курсу, выведенному из оценки позиции
            pp = r.get("price_pct")
            k = (r.get("value_rub") or 0.0) / (r["qty"] * pp / 100.0 * r["nominal"]) if pp else 0.0
            if k <= 0:
                continue
        am = [(a.get("amortdate"), a.get("value")) for a in (bz or {}).get("amort") or []]
        call = r.get("put_date") if r.get("put_date") and r["put_date"] > today else None       # срок до оферты — только пут
        if call and r.get("maturity") and call < r["maturity"]:
            has_offers = True
        cds = sorted(d for d in r.get("call_dates") or [] if d > today and (not r.get("maturity") or d < r["maturity"]))
        cflag = (cds[0], "call") if cds else ((r["unk_date"], "unknown") if r.get("unk_date") and r["unk_date"] > today else None)
        for v, use in (("offer", True), ("maturity", False)):
            if not use and not r.get("maturity"):
                if v == "maturity":
                    undated.append(r["name"])
                continue
            ev = ld_events(r.get("maturity"), call, r["nominal"], r["qty"], k, am, today, use)
            if ev and cflag and ev[-1]["date"] > cflag[0]:
                ev[-1]["call"], ev[-1]["call_kind"] = cflag
                has_calls = True
            if ev:
                built[v].append({"isin": r.get("isin") or r.get("ticker") or "", "name": r["name"], "ytm": r.get("ytm"), "events": ev})
    variants = {}
    for v, its in built.items():
        yr = ld_buckets(its, today, "year")
        variants[v] = {"year": yr, "quarter": ld_buckets(its, today, "quarter"), "summary": ld_summary(its, today, yr), "bonds": len(its)}
    return {"today": today, "empty": not any(built.values()), "value": value, "variants": variants, "has_offers": has_offers,
            "has_calls": has_calls, "undated": sorted(set(undated))}
