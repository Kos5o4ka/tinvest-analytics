# ═══════════════════════════════ справочник инструментов ═══════════════════════════════

TYPE_FROM_KIND = {"INSTRUMENT_TYPE_BOND": "bond", "INSTRUMENT_TYPE_SHARE": "share", "INSTRUMENT_TYPE_ETF": "etf",
                  "INSTRUMENT_TYPE_CURRENCY": "currency", "INSTRUMENT_TYPE_FUTURES": "futures",
                  "INSTRUMENT_TYPE_OPTION": "option", "INSTRUMENT_TYPE_SP": "sp"}


def inst_key(uid, figi):
    return uid or figi or ""


_inst_lock = threading.Lock()
_bulk = {}                        # вид справочника -> (время, {uid|figi: (info, параметры облигации | None)})
_bulk_lock = threading.Lock()
BULK_TTL = 3600


def inst_info_from(i, kind=None):
    b = i.get("brand") or {}
    return {"uid": i.get("uid") or "", "figi": i.get("figi") or "", "ticker": i.get("ticker") or "",
            "isin": i.get("isin") or "", "name": i.get("name") or "", "type": i.get("instrumentType") or kind or "",
            "cur": (i.get("currency") or "rub").lower(), "sector": i.get("sector") or "",
            "logo": b.get("logoName") or "", "color": b.get("logoBaseColor") or "",
            "country": i.get("countryOfRisk") or "", "cls": i.get("classCode") or ""}


def bond_params(r):
    """Параметры облигации из ответа BondBy / Bonds (одинаковая структура)."""
    return {"nominal": qf(r.get("nominal")) or qf(r.get("initialNominal")) or 1000.0,
            "initial": qf(r.get("initialNominal")), "cur": cur_of(r.get("nominal")),
            "maturity": iso_date(r.get("maturityDate")), "call": iso_date(r.get("callDate")),
            "placement": iso_date(r.get("placementDate")), "cpy": int(r.get("couponQuantityPerYear") or 0),
            "aci": qf(r.get("aciValue")), "floating": bool(r.get("floatingCouponFlag")),
            "amort": bool(r.get("amortizationFlag")), "perpetual": bool(r.get("perpetualFlag")),
            "risk": r.get("riskLevel") or "", "sector": r.get("sector") or "", "name": r.get("name") or ""}


def bulk_catalog(client, endpoint, kind):
    """{uid|figi: (info, параметры облигации)} по одному запросу на весь справочник (держим в памяти час)."""
    with _bulk_lock:
        hit = _bulk.get(endpoint)
        if hit and time.time() - hit[0] < BULK_TTL:
            return hit[1]
    with key_lock("bulk:" + endpoint):
        hit = _bulk.get(endpoint)
        if hit and time.time() - hit[0] < BULK_TTL:
            return hit[1]
        d = {}
        try:
            for i in client.instruments_all(endpoint):
                v = (inst_info_from(i, kind), bond_params(i) if kind == "bond" else None)
                if i.get("uid"):
                    d[i["uid"]] = v
                if i.get("figi"):
                    d[i["figi"]] = v
        except ApiError:
            return {}
        with _bulk_lock:
            _bulk[endpoint] = (time.time(), d)
        return d


def instruments(client, keys):
    """keys: [(uid, figi)] -> {uid|figi: info}. Кэш в базе на 30 дней; отсутствующие берутся пакетно из справочников
    Bonds/Shares/Etfs (один запрос на справочник вместо запроса на каждый инструмент), остальное — по одному."""
    st = store()
    out, need = {}, []

    def scan(todo):
        miss = []
        for u, f in set(todo):
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
            elif st.get("instmiss:" + k, ttl=DAY) is None:
                miss.append((u, f))
        return miss
    need = scan(keys)
    if need and client.ready:
        with _inst_lock:                       # параллельные запросы не дублируют работу
            need = scan(need)
            save = []
            if len(need) > 5:
                cats = pool_map(lambda e: bulk_catalog(client, *e), (("Bonds", "bond"), ("Shares", "share"), ("Etfs", "etf")))
                left, bsave = [], []
                for u, f in need:
                    hit = next((c[x] for c in cats for x in (u, f) if x and x in c), None)
                    if not hit:
                        left.append((u, f))
                        continue
                    info, bp = hit
                    for kk in {inst_key(u, f), info["uid"], info["figi"]}:
                        if kk:
                            out[kk] = info
                            save.append(("inst:" + kk, info))
                    if bp and info["uid"] and st.get("bond:" + info["uid"], ttl=12 * 3600) is None:
                        bsave.append(("bond:" + info["uid"], bp))
                if bsave:
                    st.put_many(bsave)
                need = left

            def one(k):
                u, f = k
                try:
                    i = client.instrument(uid=u, figi=None if u else f)
                except ApiError as e:
                    if e.status == 404:          # инструмента нет в справочнике: не спрашиваем повторно сутки
                        st.put("instmiss:" + inst_key(u, f), 1)
                    return k, None
                return k, inst_info_from(dict(i, uid=i.get("uid") or u or "", figi=i.get("figi") or f or ""))
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
    if b is None and client.ready and st.get("bondmiss:" + uid, ttl=600) is None \
            and st.get("bondmiss404:" + uid, ttl=DAY) is None:
        with key_lock("bond:" + uid):
            b = st.get("bond:" + uid, ttl=12 * 3600)
            if b is None:
                r = None
                hit = (bulk_catalog(client, "Bonds", "bond") or {}).get(uid)
                if hit:
                    b = hit[1]
                else:
                    try:
                        r = client.bond_by(uid)
                    except ApiError as e:
                        # нет в справочнике — не спрашиваем сутки, API занят/ошибка — 10 минут
                        st.put("bondmiss404:" + uid if e.status == 404 else "bondmiss:" + uid, 1)
                    if r:
                        b = bond_params(r)
                if b:
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


def bond_metrics(b, price_rub, today=None, ignore_call=False):
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
    end = b.get("call") if b.get("call") and b["call"] > today and not ignore_call else b.get("maturity")
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


