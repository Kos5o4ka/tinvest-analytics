
# ═══════════════════════════════ точная математика облигаций (потоки MOEX) ═══════════════════════════════
# Потоки считаются на одну облигацию в валюте номинала: список (дата ISO, купон, погашение номинала).

BC_TTL, BC_ERR_TTL, BC_TAX = 24 * 3600, 3600, 0.13
BC_URL = "https://iss.moex.com/iss/securities/%s/bondization.json?iss.meta=off&limit=unlimited"


def _bc_table(d, name):
    t = (d or {}).get(name) or {}
    cols = t.get("columns") or []
    return [dict(zip(cols, row)) for row in t.get("data") or []]


def moex_bondization(isin):
    """Купоны, амортизации и оферты выпуска с MOEX ISS. Кэш 24 ч; ошибки/пустой ответ кэшируются на 1 ч."""
    isin = (isin or "").strip().upper()
    if not isin or not re.match(r"^[A-Z0-9]{4,14}$", isin):
        return None
    st = store()
    key = "bondiz:" + isin
    v = st.get(key, ttl=BC_TTL)
    if v is not None:
        if v.get("ok"):
            return v
        if time.time() - v.get("ts", 0) < BC_ERR_TTL:
            return None
    try:
        d = json.loads(http_text(BC_URL % isin, 20))
        out = {"ok": True, "ts": time.time(), "coupons": _bc_table(d, "coupons"),
               "amort": _bc_table(d, "amortizations"), "offers": _bc_table(d, "offers")}
        if not out["coupons"] and not out["amort"]:
            raise ValueError("пусто")
        for k in ("coupons", "amort", "offers"):      # оставляем только нужные поля
            keep = {"coupons": ("coupondate", "value", "valueprc", "faceunit"),
                    "amort": ("amortdate", "value", "valueprc", "faceunit"),
                    "offers": ("offerdate", "price", "offertype", "faceunit")}[k]
            out[k] = [{c: r.get(c) for c in keep} for r in out[k]]
    except Exception:  # noqa: BLE001
        out = {"ok": False, "ts": time.time()}
    st.put(key, out)
    return out if out.get("ok") else None


def bond_flows(bz, today, face, mode="auto"):
    """Будущие потоки на одну облигацию: [(дата, купон, номинал)] и признак окончания ('offer'/'maturity').
    face — текущий номинал. Неизвестные купоны (флоатеры) = последний известный. Если есть будущая оферта
    (покупка по цене offer price) и mode != 'maturity', потоки обрываются на дате оферты.
    Возвращает (flows, end_kind, end_date) либо (None, None, None)."""
    cps = sorted((c["coupondate"], c.get("value")) for c in bz["coupons"] if c.get("coupondate"))
    am_all = sorted((a["amortdate"], a.get("value")) for a in bz["amort"] if a.get("amortdate") and a.get("value"))
    am = [a for a in am_all if a[0] > today]
    fut = [(d, v) for d, v in cps if d > today]
    if not fut and not am:
        return None, None, None

    def face_at(d):       # номинал в начале купонного периода, оканчивающегося в d (амортизация в дату d уже после купона)
        return face + sum(v for da, v in am_all if d <= da <= today) - sum(v for da, v in am_all if today < da < d)

    # ставка последнего известного купона = выплата / номинал, на который она начислена
    rate = None
    for d, v in cps:
        if v and (d <= today or rate is None):
            rate = v / max(face_at(d), 1e-9)
        if d > today and v:
            break
    cpn, last_rate = {}, None
    for d, v in cps:
        if v:
            last_rate = v / max(face_at(d), 1e-9)
            if d > today:
                cpn[d] = v
        elif d > today:
            r_ = last_rate if last_rate is not None else rate
            cpn[d] = (r_ or 0.0) * face_at(d)       # неизвестный купон: последняя ставка на текущий остаток номинала
    prin = defaultdict(float)
    for d, v in am:
        prin[d] += v
    rest = face - sum(prin.values())
    mat = max([d for d, _ in fut] + [d for d in prin] or [""])
    if rest > 0.0001 * face and mat:      # остаток номинала гасится в последний день
        prin[mat] += rest
    elif rest < -0.0001 * face:
        return None, None, None          # данные не сходятся с номиналом
    end_kind, end = "maturity", mat
    if mode != "maturity":
        offs = []
        for o in bz.get("offers") or []:
            t = (o.get("offertype") or "")
            if "оферт" in t.lower() and "состоял" not in t.lower() and (o.get("offerdate") or "") > today:
                offs.append(o)
        if offs:
            o = min(offs, key=lambda x: x["offerdate"])
            if o["offerdate"] < mat or not mat:
                end_kind, end = "offer", o["offerdate"]
                op = (o.get("price") or 100.0) / 100.0
                remain = face - sum(v for d, v in prin.items() if d < end)
                prin = {d: v for d, v in prin.items() if d < end}
                prin[end] = prin.get(end, 0.0) + remain * op
                # покупатель по оферте получает и НКД на дату оферты (линейно внутри купонного периода)
                allc = sorted(cpn)
                nx = [d for d in allc if d > end]
                pv_ = [d for d in allc if d <= end] or [d for d, _ in cps if d <= end][-1:]
                if nx and pv_:
                    d0, d1, de = (datetime.strptime(x, "%Y-%m-%d") for x in (pv_[-1], nx[0], end))
                    if (d1 - d0).days > 0 and end not in cpn:
                        cpn[end] = cpn[nx[0]] * (de - d0).days / (d1 - d0).days
    days = sorted(set(d for d in list(cpn) + list(prin) if d <= end))
    flows = [(d, cpn.get(d, 0.0), prin.get(d, 0.0)) for d in days]
    return flows, end_kind, end


def _bc_t(d, settle):
    return (datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(settle, "%Y-%m-%d")).days / 365.0


def _bc_pv(flows, settle, y, tax=False, basis=0.0):
    tl = [(_bc_t(d, settle), c, p) for d, c, p in flows]
    tot = 0.0
    for i, (t, c, p) in enumerate(tl):
        a = c + p
        if tax:
            a = c * (1 - BC_TAX) + p
            if i == len(tl) - 1:
                a -= BC_TAX * max(0.0, sum(x[2] for x in tl) - basis)
        tot += a / (1 + y) ** t
    return tot


def cf_ytm(dirty, flows, settle, tax=False, basis=0.0):
    """Эффективная годовая доходность (дробью, 0.12 = 12%) по потокам; None, если корня нет.
    tax=True: после НДФЛ 13% — на купоны и на положительную разницу (погашение - basis) в дату последнего потока."""
    if not flows or not dirty or dirty <= 0:
        return None
    fl = [f for f in flows if f[0] > settle]
    if not fl:
        return None
    f = lambda y: _bc_pv(fl, settle, y, tax, basis) - dirty
    lo, hi = -0.95, 50.0
    flo, fhi = f(lo), f(hi)
    if flo != flo or fhi != fhi or flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
        if hi - lo < 1e-10:
            break
    return (lo + hi) / 2


def cf_risk(flows, settle, y):
    """(дюрация Маколея в годах, модифицированная, выпуклость) при доходности y (дробью)."""
    pvs = [(_bc_t(d, settle), (c + p) / (1 + y) ** _bc_t(d, settle)) for d, c, p in flows if d > settle]
    tot = sum(v for _, v in pvs)
    if not tot:
        return None, None, None
    mac = sum(t * v for t, v in pvs) / tot
    conv = sum(t * (t + 1) * v for t, v in pvs) / tot / (1 + y) ** 2
    return mac, mac / (1 + y), conv


def stress(price, flows, settle, face, aci=0.0, dy_list=(-3, -2, -1, 1, 2, 3), y=None):
    """Полная переоценка: {dy: новая чистая цена, % номинала} при параллельном сдвиге доходности на dy п.п.
    price — чистая цена, % номинала; aci — НКД в валюте номинала."""
    if y is None:
        y = cf_ytm(price / 100.0 * face + aci, flows, settle)
    if y is None:
        return {}
    out = {}
    for dy in dy_list:
        ny = y + dy / 100.0
        if ny <= -0.95:
            continue
        out[dy] = (_bc_pv([f for f in flows if f[0] > settle], settle, ny) - aci) / face * 100.0
    return out
