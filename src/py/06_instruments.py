# ═══════════════════════════════ справочник инструментов ═══════════════════════════════

TYPE_FROM_KIND = {"INSTRUMENT_TYPE_BOND": "bond", "INSTRUMENT_TYPE_SHARE": "share", "INSTRUMENT_TYPE_ETF": "etf",
                  "INSTRUMENT_TYPE_CURRENCY": "currency", "INSTRUMENT_TYPE_FUTURES": "futures",
                  "INSTRUMENT_TYPE_OPTION": "option", "INSTRUMENT_TYPE_SP": "sp"}


def inst_key(uid, figi):
    return uid or figi or ""


def instruments(client, keys):
    """keys: [(uid, figi)] -> {uid|figi: info}. Кэш в базе на 30 дней."""
    st = store()
    out, need = {}, []
    for u, f in set(keys):
        k = inst_key(u, f)
        if not k:
            continue
        v = st.get("inst:" + k, ttl=30 * DAY)
        if v:
            out[k] = v
            if f:
                out[f] = v
            if v.get("uid"):
                out[v["uid"]] = v
        else:
            need.append((u, f))
    if need and client.ready:
        def one(k):
            u, f = k
            try:
                i = client.instrument(uid=u, figi=None if u else f)
            except ApiError:
                return k, None
            b = i.get("brand") or {}
            return k, {"uid": i.get("uid") or u or "", "figi": i.get("figi") or f or "", "ticker": i.get("ticker") or "",
                       "isin": i.get("isin") or "", "name": i.get("name") or "", "type": i.get("instrumentType") or "",
                       "cur": (i.get("currency") or "rub").lower(), "sector": i.get("sector") or "",
                       "logo": b.get("logoName") or "", "color": b.get("logoBaseColor") or "",
                       "country": i.get("countryOfRisk") or "", "cls": i.get("classCode") or ""}
        save = []
        for k, v in pool_map(one, need[:400]):
            if v:
                for kk in {inst_key(*k), v["uid"], v["figi"]}:
                    if kk:
                        out[kk] = v
                        save.append(("inst:" + kk, v))
        if save:
            st.put_many(save)
    return out


def bond_info(client, uid):
    """Параметры облигации и купоны; кэш: параметры 12 ч, купоны 3 дня (для погашенных — 60 дней)."""
    st = store()
    b = st.get("bond:" + uid, ttl=12 * 3600)
    if b is None and client.ready:
        try:
            r = client.bond_by(uid)
        except ApiError:
            r = None
        if r:
            b = {"nominal": qf(r.get("nominal")) or qf(r.get("initialNominal")) or 1000.0,
                 "initial": qf(r.get("initialNominal")), "cur": cur_of(r.get("nominal")),
                 "maturity": iso_date(r.get("maturityDate")), "call": iso_date(r.get("callDate")),
                 "placement": iso_date(r.get("placementDate")), "cpy": int(r.get("couponQuantityPerYear") or 0),
                 "aci": qf(r.get("aciValue")), "floating": bool(r.get("floatingCouponFlag")),
                 "amort": bool(r.get("amortizationFlag")), "perpetual": bool(r.get("perpetualFlag")),
                 "risk": r.get("riskLevel") or "", "sector": r.get("sector") or "", "name": r.get("name") or ""}
            st.put("bond:" + uid, b)
    if not b:
        return None
    matured = b.get("maturity") and b["maturity"] < date.today().isoformat()
    cp = st.get("cpn:" + uid, ttl=(60 if matured else 3) * DAY)
    if cp is None and client.ready:
        frm = (b.get("placement") or (date.today() - timedelta(days=3650)).isoformat()) + "T00:00:00Z"
        end = b.get("maturity") or (date.today() + timedelta(days=365 * 30)).isoformat()
        to = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=40)).strftime("%Y-%m-%dT00:00:00Z")
        try:
            ev = client.bond_coupons(uid, frm, to)
            cp = sorted([[iso_date(e.get("couponDate")), qf(e.get("payOneBond"))] for e in ev if iso_date(e.get("couponDate"))])
            st.put("cpn:" + uid, cp)
        except ApiError:
            cp = None
    b = dict(b)
    b["coupons"] = cp or []
    return b


def nkd_at(b, day):
    """НКД на дату по графику купонов (линейно между выплатами)."""
    cp = b.get("coupons") or []
    if not cp:
        return 0.0
    dates = [c[0] for c in cp]
    i = bisect.bisect_right(dates, day)
    if i >= len(cp):
        return 0.0
    nxt_d, pay = cp[i]
    if not pay:
        known = [c[1] for c in cp[:i] if c[1]]
        pay = known[-1] if known else 0.0
    prev_d = cp[i - 1][0] if i > 0 else b.get("placement")
    if not prev_d:
        return 0.0
    d0, d1, dd = (datetime.strptime(x, "%Y-%m-%d") for x in (prev_d, nxt_d, day))
    span = (d1 - d0).days
    return pay * max(0, (dd - d0).days) / span if span > 0 else 0.0


def bond_metrics(b, price_rub, today=None):
    """Доходность к погашению/оферте (эффективная), дюрация Маколея, купонная доходность."""
    today = today or date.today().isoformat()
    nominal = b.get("nominal") or 1000.0
    cp = b.get("coupons") or []
    known = [p for _, p in cp if p]
    last_pay = known[-1] if known else 0.0
    future = [(d, p) for d, p in cp if d > today]
    nxt = future[0] if future else None
    if nxt and not nxt[1]:
        nxt = (nxt[0], last_pay)
    cpy = b.get("cpy") or (len([1 for d, _ in cp if d[:4] == today[:4]]) or 0)
    annual = (nxt[1] if nxt else last_pay) * cpy if cpy else 0.0
    res = {"next": nxt, "coupon_rate": annual / nominal * 100 if nominal else None,
           "cur_yield": annual / price_rub * 100 if price_rub else None, "ytm": None, "dur": None, "to": None}
    end = b.get("call") if b.get("call") and b["call"] > today else b.get("maturity")
    if not end or b.get("perpetual") or not price_rub or end <= today:
        return res
    res["to"] = "offer" if end == b.get("call") else "maturity"
    t0 = datetime.strptime(today, "%Y-%m-%d")
    flows = []
    for d, p in future:
        if d > end:
            break
        flows.append(((datetime.strptime(d, "%Y-%m-%d") - t0).days / 365.0, p or last_pay))
    flows.append(((datetime.strptime(end, "%Y-%m-%d") - t0).days / 365.0, nominal))
    dirty = price_rub + (b.get("aci") if b.get("aci") is not None else nkd_at(b, today))

    def pv(y):
        return sum(a / (1 + y) ** t for t, a in flows)

    lo, hi = -0.95, 20.0
    if (pv(lo) - dirty) * (pv(hi) - dirty) > 0:
        return res
    for _ in range(120):
        mid = (lo + hi) / 2
        if pv(mid) > dirty:
            lo = mid
        else:
            hi = mid
    y = (lo + hi) / 2
    tot = pv(y)
    res["ytm"] = y * 100
    res["dur"] = sum(t * a / (1 + y) ** t for t, a in flows) / tot if tot else None
    return res


def benchmark_uid(client, ticker):
    st = store()
    v = st.get("bench:" + ticker, ttl=30 * DAY)
    if v:
        return v
    try:
        found = client.find(ticker)
    except ApiError:
        return None
    best = None
    for i in found:
        if (i.get("ticker") or "").upper() == ticker and i.get("uid"):
            if best is None or i.get("classCode") == "TQTF":
                best = i
    if best:
        st.put("bench:" + ticker, best["uid"])
        return best["uid"]
    return None


def candle_series(client, uid, d_from, d_to):
    """Дневные цены закрытия из локальной базы; недостающее догружается из API годовыми кусками."""
    st = store()
    meta = st.get("cs:" + uid) or {}
    need = []
    if not meta:
        need.append((d_from, d_to))
    else:
        if d_from < meta["from"]:
            need.append((d_from, meta["from"]))
        tail_from = min(meta["to"], (date.today() - timedelta(days=4)).isoformat())
        if d_to > tail_from:
            need.append((tail_from, d_to))
    ok = True
    if need and client.ready:
        for a, b in need:
            cur = datetime.strptime(a, "%Y-%m-%d")
            end = datetime.strptime(b, "%Y-%m-%d") + timedelta(days=1)
            while cur < end:
                nxt = min(end, cur + timedelta(days=364))
                try:
                    cs = client.candles(uid, cur.strftime("%Y-%m-%dT00:00:00Z"), nxt.strftime("%Y-%m-%dT00:00:00Z"))
                    st.candles_put(uid, [(c["time"][:10], qf(c.get("close"))) for c in cs if c.get("time") and c.get("close")])
                except ApiError:
                    ok = False
                    break
                cur = nxt
        if ok:
            st.put("cs:" + uid, {"from": min(d_from, meta.get("from", d_from)), "to": max(d_to, meta.get("to", d_to))})
    return st.candles(uid)


