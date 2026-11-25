# ═══════════════════════════════ позиции ═══════════════════════════════

def pos_row(info, **kw):
    info = info or {}
    r = {"uid": info.get("uid") or kw.get("uid") or "", "ticker": info.get("ticker") or kw.get("ticker") or "", "isin": info.get("isin") or "",
         "name": info.get("name") or kw.get("name") or info.get("ticker") or kw.get("ticker") or "",
         "logo": info.get("logo") or "", "color": info.get("color") or "", "sector": info.get("sector") or "",
         "type": kw.get("type") or info.get("type") or "", "qty": 0.0, "avg": 0.0, "price": 0.0, "cur": "rub",
         "value": 0.0, "value_rub": None, "cost_rub": 0.0, "pnl": 0.0, "pnl_rub": None, "pnl_pct": None,
         "daily": None, "blocked": False, "nkd": 0.0}
    r.update({k: v for k, v in kw.items() if k not in ("uid", "ticker", "name") or v})
    return r


CUR_TICKERS = {"usd": "USD000UTSTOM", "eur": "EUR_RUB__TOM", "cny": "CNYRUB_TOM", "hkd": "HKDRUB_TOM",
               "gbp": "GBPRUB_TOM", "chf": "CHFRUB_TOM", "jpy": "JPYRUB_TOM", "try": "TRYRUB_TOM",
               "kzt": "KZTRUB_TOM", "byn": "BYNRUB_TOM", "amd": "AMDRUB_TOM"}


def fx_uid(client, cur):
    st = store()
    v = st.get("fxuid:" + cur, ttl=30 * DAY)
    if v or cur not in CUR_TICKERS or not client.ready:
        return v
    try:
        found = client.find(CUR_TICKERS[cur])
    except ApiError:
        return None
    for i in found:
        if (i.get("ticker") or "").upper() == CUR_TICKERS[cur] and i.get("uid"):
            st.put("fxuid:" + cur, i["uid"])
            return i["uid"]
    return None


def fx_now(client, curs):
    out = {"rub": 1.0}
    need = {c: fx_uid(client, c) for c in curs if c != "rub"}
    uids = [u for u in need.values() if u]
    lp = {}
    if uids and client.ready:
        try:
            lp = client.last_prices(uids)
        except ApiError:
            lp = {}
    for c, u in need.items():
        if u and lp.get(u):
            out[c] = lp[u]
    for c in curs:
        if c not in out:                                # без токена/uid — курс ЦБ РФ
            try:
                r = tax_cbr_rate(c, date.today().isoformat())
                if r:
                    out[c] = r
            except Exception:  # noqa: BLE001
                pass
    return out


def tinvest_positions(port, names):
    raw = port.get("positions") or []
    fx = {"rub": 1.0}
    for x in raw:
        if x.get("instrumentType") == "currency":
            info = names.get(x.get("instrumentUid") or x.get("figi")) or {}
            iso = (x.get("ticker") or info.get("ticker") or "")[:3].lower()
            if iso and iso != "rub" and qf(x.get("currentPrice")) > 0:
                fx[iso] = qf(x.get("currentPrice"))
    out = []
    for x in raw:
        info = names.get(x.get("instrumentUid") or x.get("figi")) or {}
        qty = qf(x.get("quantity"))
        avg = qf(x.get("averagePositionPriceFifo")) or qf(x.get("averagePositionPrice"))
        price = qf(x.get("currentPrice"))
        nkd = qf(x.get("currentNkd"))
        cur = cur_of(x.get("currentPrice"))
        itype = x.get("instrumentType") or info.get("type") or ""
        if itype == "futures":
            value, cost = qf(x.get("varMargin")), 0.0
        else:
            value, cost = qty * (price + nkd), qty * avg
        if x.get("expectedYieldFifo") or x.get("expectedYield"):
            pnl = qf(x.get("expectedYieldFifo")) or qf(x.get("expectedYield"))
        else:
            pnl = qty * (price - avg) if avg else 0.0
        rate = fx.get(cur)
        tk = x.get("ticker") or info.get("ticker") or (x.get("figi") or "")[:12]
        if itype == "currency":
            tk = tk[:3].upper()
            info = dict(info, name=CUR_NAMES.get(tk, info.get("name") or tk), ticker=tk)
        out.append(pos_row(info, uid=x.get("instrumentUid") or info.get("uid") or x.get("figi") or "", ticker=tk,
                           type=itype, qty=qty, avg=avg, price=price, cur=cur, nkd=nkd, value=value,
                           value_rub=value * rate if rate is not None else None,
                           cost_rub=cost * rate if rate is not None else 0.0, pnl=pnl,
                           pnl_rub=pnl * rate if rate is not None else None,
                           pnl_pct=pnl / cost * 100 if cost else None,
                           daily=qf(x.get("dailyYield")) if x.get("dailyYield") else None, blocked=bool(x.get("blocked"))))
    return out


CUR_NAMES = {"RUB": "Рубли", "USD": "Доллар США", "EUR": "Евро", "CNY": "Китайский юань", "HKD": "Гонконгский доллар",
             "GBP": "Фунт стерлингов", "CHF": "Швейцарский франк", "KZT": "Тенге", "TRY": "Турецкая лира",
             "AMD": "Армянский драм", "BYN": "Белорусский рубль", "JPY": "Японская иена"}


def imported_positions(client, ops, names):
    f = fifo(ops)
    real = [u for u in f if not u.startswith("imp:")]
    lp = {}
    if real and client.ready:
        try:
            lp = client.last_prices(real)
        except ApiError:
            lp = {}
    curs = {(names.get(u) or {}).get("cur", "rub") for u in f}
    cash = defaultdict(float)
    for o in ops:
        cash[cur_of(o.get("payment"))] += qf(o.get("payment"))
    fx = fx_now(client, curs | set(cash))
    mq = moex_quotes([u[4:] for u in f if u.startswith("imp:") and u not in lp])      # без токена — котировки Мосбиржи
    out = []
    for uid, p in f.items():
        info = names.get(uid) or {"name": next((o.get("name") for o in ops if (o.get("instrumentUid") or o.get("figi")) == uid), uid),
                                  "ticker": uid.replace("imp:", "")[:14]}
        itype = info.get("type") or next((TYPE_FROM_KIND.get(o.get("instrumentKind")) for o in ops
                                          if (o.get("instrumentUid") or o.get("figi")) == uid and o.get("instrumentKind")), "") or ""
        qty, cost = p["qty"], p["cost"]
        cur = info.get("cur") or "rub"
        nkd, unit = 0.0, None
        if uid in lp:
            unit = lp[uid]
            if itype == "bond":
                b = bond_info(client, uid)
                nominal = (b or {}).get("nominal") or 1000.0
                unit = unit / 100.0 * nominal
                nkd = (b or {}).get("aci") or 0.0
        if unit is None and uid.startswith("imp:"):
            q = mq.get(uid[4:].upper())
            k = 1.0 if (cur or "rub") == "rub" else fx.get(cur)     # котировка Мосбиржи в рублях -> в валюту позиции
            if q and q.get("price") and k:
                unit, nkd = q["price"] / k, (q.get("nkd") or 0.0) / k
                if not itype and q.get("type"):
                    itype = {"etf": "etf"}.get(q["type"], q["type"])
        if unit is None:
            unit = p["last_unit"]
        value = qty * (unit + nkd)
        rate = fx.get(cur)
        pnl = qty * unit - cost
        out.append(pos_row(info, uid=uid, type=itype, qty=qty, avg=cost / qty if qty else 0.0, price=unit, cur=cur, nkd=nkd,
                           value=value, value_rub=value * rate if rate else None, cost_rub=cost * (rate or 1.0),
                           pnl=pnl, pnl_rub=pnl * rate if rate else None, pnl_pct=pnl / cost * 100 if cost else None))
    for c, v in cash.items():
        if abs(v) >= 0.01:
            rate = fx.get(c)
            iso = c.upper()
            out.append(pos_row({"name": CUR_NAMES.get(iso, iso), "ticker": iso}, uid="cash:" + c, type="currency",
                               qty=v, price=rate or 0.0, avg=0.0, cur="rub", value=v * (rate or 0.0),
                               value_rub=v * rate if rate else None, pnl=0.0, pnl_rub=0.0))
    return out


def merge_positions(lists):
    acc = {}
    for rows in lists:
        for r in rows:
            k = r["uid"] or r["ticker"]
            if r["type"] == "currency":
                k = "cur:" + (r["ticker"] or "")[:3].upper()
            if k not in acc:
                acc[k] = dict(r)
                continue
            a = acc[k]
            for f in ("qty", "value", "cost_rub", "pnl"):
                a[f] = (a.get(f) or 0.0) + (r.get(f) or 0.0)
            for f in ("value_rub", "pnl_rub", "daily"):
                if a.get(f) is not None or r.get(f) is not None:
                    a[f] = (a.get(f) or 0.0) + (r.get(f) or 0.0)
            a["blocked"] = a["blocked"] or r["blocked"]
    out = list(acc.values())
    for r in out:
        if r["type"] != "currency" and r["qty"]:
            if r.get("cost_rub") and r.get("value_rub") is not None and r["cur"] == "rub":
                r["avg"] = r["cost_rub"] / r["qty"]
            if r.get("cost_rub") and r.get("pnl_rub") is not None:
                r["pnl_pct"] = r["pnl_rub"] / r["cost_rub"] * 100
    total = sum((r["value_rub"] or 0) for r in out if r["type"] != "futures") or 1
    for r in out:
        r["share"] = (r["value_rub"] or 0) / total * 100 if r["type"] != "futures" else 0
    out.sort(key=lambda r: -(r["value_rub"] if r["value_rub"] is not None else r["value"]))
    return out


def totals_from_rows(rows):
    t = defaultdict(float)
    for r in rows:
        v = r["value_rub"] or 0.0
        t[{"share": "shares", "bond": "bonds", "etf": "etf", "currency": "currencies", "futures": "futures",
           "option": "options", "sp": "sp"}.get(r["type"], "other")] += v
    t["total"] = sum(v for k, v in t.items() if k != "futures")
    return t


# ═══════════════════════════════ облигации и выплаты ═══════════════════════════════

def _spread(ytm, dur):
    try:
        k = kbd_at(dur) if ytm is not None and dur else None
        return round(ytm - k, 2) if k is not None else None
    except Exception:  # noqa: BLE001
        return None


RISK_RU = {"RISK_LEVEL_LOW": "низкий", "RISK_LEVEL_MODERATE": "средний", "RISK_LEVEL_HIGH": "высокий"}


STRESS_DY = (-3, -2, -1, 1, 2, 3)
YTM_HIGH = 100.0         # доходность выше 100% годовых — «высокий риск дефолта»: только помечается, из расчётов НЕ исключается


def bond_isin(r):
    inst = store().get("inst:" + (r.get("uid") or ""), ttl=30 * DAY) or {}
    return (inst.get("isin") or r.get("ticker") or "").upper()


def portfolio_irr(items, today):
    """Единая доходность облигационного портфеля (IRR): все будущие потоки позиций (потоки на 1 бумагу x количество,
    в рублях по текущему курсу валюты номинала) против суммарной текущей стоимости с НКД. Одно решение cf_ytm.
    irr_tax — то же после НДФЛ: потоки каждой бумаги берутся уже за вычетом налога (net_flows), дальше без налога.
    Бумаги без точных потоков (приближённый расчёт) в IRR не входят: value/count показывают охват.
    Возвращает {irr, irr_tax, value (в рублях, стоимость с НКД), count}; доходности в %."""
    gross, net, dirty = defaultdict(float), defaultdict(float), 0.0
    for ex, qty, fx in items:
        k = qty * fx
        dirty += ex["dirty"] * k
        for d, c, p in ex["flows"]:
            if d > today:
                gross[d] += (c + p) * k
        for d, a in net_flows(ex["flows"], today, ex["basis"], ex.get("aci", 0.0)):
            net[d] += a * k
    res = {"irr": None, "irr_tax": None, "value": dirty, "count": len(items)}
    if dirty > 0 and gross:
        y = cf_ytm(dirty, [(d, a, 0.0) for d, a in sorted(gross.items())], today)
        yt = cf_ytm(dirty, [(d, a, 0.0) for d, a in sorted(net.items())], today)
        res["irr"] = y * 100 if y is not None else None
        res["irr_tax"] = yt * 100 if yt is not None else None
    return res


def keyrate_brief():
    """Короткая сводка об использованном прогнозе ключевой ставки для UI (без пути)."""
    try:
        i = keyrate_forecast_info()
        return {"source": i["source"], "name": i["source_name"], "as_of": i["as_of"], "key_rate": i["key_rate"],
                "yearly": i["yearly"], "mode": i["mode"]}
    except Exception:  # noqa: BLE001
        return None


def bond_exact(client, r, b, today, rates):
    """Точный расчёт по потокам MOEX. Возвращает словарь полей строки либо None (тогда — приближение)."""
    if b.get("perpetual") or not b.get("maturity"):
        return None
    isin = bond_isin(r)
    try:
        bz = moex_bondization(isin)
    except Exception:  # noqa: BLE001
        return None
    if not bz:
        return None
    face = b.get("nominal") or 1000.0
    price, avg, aci = bond_price_face(r, b, rates)
    if not price:
        return None
    est = {}
    dirty = price + aci
    try:
        opt = moex_bond_options(isin)
    except Exception:  # noqa: BLE001
        opt = None
    offs = offer_kinds(bz, opt, b.get("call"), today)
    yk = yields_by_kind(bz, today, face, dirty, offs, floating=bool(b.get("floating")), est_out=est, price=price)
    if not yk or not yk["flows"] or yk["end"] <= today:
        return None
    flows, kind, end, y = yk["flows"], yk["end_kind"], yk["end"], yk["y"]
    if yk["basis"] in ("maturity", "call") and abs((datetime.strptime(yk["maturity"], "%Y-%m-%d") - datetime.strptime(b["maturity"], "%Y-%m-%d")).days) > 45:
        return None                      # график MOEX не сходится с данными брокера
    if y is None:
        return None
    yt = cf_ytm(dirty, flows, today, tax=True, basis=price, aci=aci)
    mac, mod, conv = cf_risk(flows, today, y)
    st = stress(price / face * 100.0, flows, today, face, aci, STRESS_DY, y)
    live = [o for o in offs if o["status"] != "cancelled" and today < o["date"] < yk["maturity"]]
    pc = lambda v: v * 100 if v is not None else None
    ykp = {"basis": yk["basis"], "ytm": pc(yk["ytm"]), "ytp": pc(yk["ytp"]), "ytp_date": yk["ytp_date"],
           "yto": pc(yk["yto"]), "yto_date": yk["yto_date"], "ytc": [[d, pc(v)] for d, v in yk["ytc_list"]],
           "ytw": pc(yk["ytw"]), "ytw_date": yk["ytw_date"], "ytw_kind": yk["ytw_kind"]}
    return {"isin": isin, "ytm": y * 100, "ytm_tax": yt * 100 if yt is not None else None, "dur": mac, "mdur": mod,
            "convexity": conv, "to": kind, "to_kind": yk["to_kind"], "ybasis": yk["basis"], "yk": ykp, "end": end,
            "put_date": min([o["date"] for o in live if o["kind"] == "put"] or [None], key=lambda x: x or "9"),
            "call_dates": sorted({o["date"] for o in live if o["kind"] == "call"}),
            "unk_date": min([o["date"] for o in live if o["kind"] == "unknown"] or [None], key=lambda x: x or "9"),
            "stress_pct": {dy: (p / 100.0 * face + aci) / dirty * 100 - 100 for dy, p in st.items()},
            "cf_source": "moex", "est_coupons": len(est), "est_detail": est, "bz": bz, "flows": flows, "basis": price, "dirty": dirty, "aci": aci}


def bond_price_face(r, b, rates):
    """(чистая цена, средняя цена покупки, НКД) на одну облигацию в ВАЛЮТЕ НОМИНАЛА. Цена позиции приходит в валюте
    r['cur'] (для валютных облигаций T-Invest отдаёт её в рублях, номинал — в USD/EUR), поэтому конвертируем."""
    fc = (b.get("cur") or "rub").lower()
    k = 1.0
    if r["cur"] != fc:
        rp = 1.0 if r["cur"] == "rub" else (r["value_rub"] / r["value"] if r.get("value") and r.get("value_rub") else rates.get(r["cur"]))
        rf = 1.0 if fc == "rub" else rates.get(fc)
        if not rp or not rf:
            return 0.0, 0.0, 0.0
        k = rp / rf
    aci = b.get("aci")
    return (r["price"] or 0.0) * k, (r["avg"] or 0.0) * k, aci if aci is not None else 0.0


def issuer_group_key(name):
    """Ключ эмитента по названию выпуска: без правовых форм и номеров серий; все ОФЗ — один эмитент (Минфин)."""
    n = (name or "").strip()
    low = n.lower().replace("ё", "е")
    if low.startswith("офз") or "минфин" in low or low.startswith("ofz"):
        return "минфин"
    return "".join(sorted(name_tokens(_bond_query(n)))) or low


def moex_coupon_schedule(isin):
    """График купонов выпуска с Мосбиржи в формате bond_info: [[дата, выплата на 1 бумагу или 0.0, если не объявлена]]."""
    try:
        bz = moex_bondization(isin)
    except Exception:  # noqa: BLE001
        return []
    out = {}
    for c in (bz or {}).get("coupons") or []:
        d = c.get("coupondate")
        if d:
            out[d] = float(c.get("value") or 0.0)
    return sorted([d, v] for d, v in out.items())


def bonds_report(client, rows, horizon_days=365):
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=horizon_days)).isoformat()   # окно выплат; 365 — «Выплаты», больше — матрица потоков
    bonds = [r for r in rows if r["type"] == "bond" and r["uid"] and r["qty"] > 0]
    infos = dict(zip([r["uid"] for r in bonds], pool_map(lambda r: bond_info(client, r["uid"]), bonds)))
    # без токена (импорт отчёта, демо) график купонов брокера недоступен — берём его с Мосбиржи, иначе нет ни выплат, ни календаря
    need = [r for r in bonds if infos.get(r["uid"]) and not infos[r["uid"]].get("coupons")]
    for r, cp in zip(need, pool_map(lambda r: moex_coupon_schedule(bond_isin(r)), need)):
        if cp:
            infos[r["uid"]] = dict(infos[r["uid"]], coupons=cp)
    out, pays = [], []
    tot_bonds = sum((r["value_rub"] or 0) for r in bonds) or 0.0
    rates = fx_now(client, {(infos.get(r["uid"]) or {}).get("cur", "rub") for r in bonds} | {r["cur"] for r in bonds})
    exacts = dict(zip([r["uid"] for r in bonds], pool_map(
        lambda r: bond_exact(client, r, infos[r["uid"]], today, rates) if infos.get(r["uid"]) else None, bonds)))
    ckinds = [{"uid": r["uid"], "isin": bond_isin(r), "call": infos[r["uid"]]["call"]} for r in bonds
              if infos.get(r["uid"]) and infos[r["uid"]].get("call") and infos[r["uid"]]["call"] > today]
    annotate_offer_kinds(ckinds, today)       # put/call у даты оферты брокера (из кэша Мосбиржи)
    ckind = {x["uid"]: x.get("call_kind") for x in ckinds}
    stress_rub = defaultdict(float)
    high_yield, irr_items = [], []
    w = defaultdict(float)
    ladder, risk = defaultdict(float), defaultdict(float)
    kinds = defaultdict(int)
    for r in bonds:
        b = infos.get(r["uid"])
        v = r["value_rub"] or 0.0
        row = {k: r.get(k) for k in ("uid", "name", "ticker", "logo", "color", "qty", "value_rub", "pnl_rub", "pnl_pct", "cur")}
        row["share"] = v / tot_bonds * 100 if tot_bonds else 0
        if not b:
            out.append(row)
            continue
        nominal = b.get("nominal") or 1000.0
        price, avg, _aci = bond_price_face(r, b, rates)
        ck = ckind.get(r["uid"])
        m = bond_metrics(b, price, today, ignore_call=(ck == "call"))      # колл — право эмитента: без точных потоков считаем к погашению
        ex = exacts.get(r["uid"])
        row.update({"buy_pct": avg / nominal * 100 if avg else None, "price_pct": price / nominal * 100 if price else None,
                    "nominal": nominal, "face_cur": b.get("cur") or "rub", "isin": (ex or {}).get("isin") or bond_isin(r),
                    "ytm": m["ytm"], "ytm_tax": None, "dur": m["dur"], "mdur": None, "convexity": None, "to": m["to"],
                    "coupon": m["coupon_rate"], "cur_yield": m["cur_yield"], "next": m["next"], "maturity": b.get("maturity"),
                    "call": b.get("call"), "risk": RISK_RU.get(b.get("risk"), ""), "floating": b.get("floating"),
                    "amort": b.get("amort"), "sector": b.get("sector"), "cf_source": "approx", "call_kind": ck,
                    "to_kind": (("put" if ck == "both" else ck) if m["to"] == "offer" else None), "ybasis": "put" if m["to"] == "offer" and ck in ("put", "both") else ("unknown" if m["to"] == "offer" else ("call" if ck == "call" else "maturity")),
                    "yk": None, "put_date": b["call"] if m["to"] == "offer" and ck in ("put", "both") else None,
                    "call_dates": [b["call"]] if ck in ("call", "both") else [], "unk_date": b["call"] if m["to"] == "offer" and ck not in ("put", "both") else None})
        if ex:
            row.update({k: ex[k] for k in ("ytm", "ytm_tax", "dur", "mdur", "convexity", "to", "cf_source")})
            row.update({k: ex.get(k) for k in ("to_kind", "yk", "put_date", "unk_date")})
            row.update(ybasis=ex.get("ybasis") or "maturity", call_dates=ex.get("call_dates") or [])
            row["end"] = ex["end"]
            row["est_coupons"] = ex.get("est_coupons") or 0
            fc_ = (b.get("cur") or "rub").lower()
            rf_ = 1.0 if fc_ == "rub" else rates.get(fc_)
            if rf_:
                irr_items.append((ex, r["qty"], rf_))
            sp = ex["stress_pct"]
        else:
            if m["ytm"] is not None and m["dur"]:      # приближение: только дюрация
                row["mdur"] = m["dur"] / (1 + m["ytm"] / 100)
                sp = {dy: -row["mdur"] * dy for dy in STRESS_DY}
            else:
                sp = {}
        row["spread"] = _spread(row["ytm"], row["dur"])
        row["stress"] = {str(dy): {"pct": p, "rub": p / 100.0 * v} for dy, p in sp.items()}
        for dy, p in sp.items():
            stress_rub[dy] += p / 100.0 * v
        m = dict(m, ytm=row["ytm"], dur=row["dur"])
        out.append(row)
        if row["ytm"] is not None and v and row["ytm"] > YTM_HIGH:
            high_yield.append({"ticker": row["ticker"], "name": row["name"], "ytm": row["ytm"], "value": v})
        if row["ytm"] is not None and v:
            w["ytm"] += row["ytm"] * v
            w["ytm_v"] += v
            if row.get("ytm_tax") is not None:
                w["yt"] += row["ytm_tax"] * v
                w["yt_v"] += v
        if row.get("mdur") is not None and v:
            w["md"] += row["mdur"] * v
            w["md_v"] += v
        if m["dur"] is not None and v:
            w["dur"] += m["dur"] * v
            w["dur_v"] += v
        if m["cur_yield"] is not None and v:
            w["cy"] += m["cur_yield"] * v
            w["cy_v"] += v
        end = (row.get("put_date") or b.get("maturity") or "") if ex else (
            (b["call"] if row["ybasis"] == "put" and b.get("call") and b["call"] > today else b.get("maturity")) or "")      # лесенка: оферта — только пут
        ladder[end[:4] or "бессрочные"] += v
        risk[RISK_RU.get(b.get("risk"), "нет данных")] += v
        kinds["Флоатер" if b.get("floating") else "Фиксированный купон"] += 1
        if b.get("amort"):
            kinds["С амортизацией"] += 1
        known = [p for _, p in b.get("coupons") or [] if p]
        fc_ = (b.get("cur") or "rub").lower()
        k_ = 1.0 if fc_ == "rub" else (rates.get(fc_) or 1.0)       # выплаты считаем в рублях по текущему курсу номинала
        fest = (ex or {}).get("est_detail") or {}
        for d, p in b.get("coupons") or []:
            if today <= d <= horizon:
                if not p and b.get("floating") and d in fest:
                    amt, est = fest[d]["amt"] * r["qty"] * k_, "forecast"      # прогноз ключевой ставки ЦБ + спред эмитента
                else:
                    amt, est = (p or (known[-1] if known else 0.0)) * r["qty"] * k_, not p
                if amt:
                    pays.append({"date": d, "kind": "coupon", "name": r["name"], "ticker": r["ticker"], "logo": r["logo"],
                                 "amount": amt, "est": est})
        # прогнозные купоны флоатера, которых ещё нет в графике брокера
        have = {d for d, _ in b.get("coupons") or []}
        for d, e in sorted(fest.items()):
            if d not in have and today <= d <= horizon and e["amt"]:
                pays.append({"date": d, "kind": "coupon", "name": r["name"], "ticker": r["ticker"], "logo": r["logo"],
                             "amount": e["amt"] * r["qty"] * k_, "est": "forecast"})
        # амортизации (частичное погашение номинала) из графика MOEX; погашение в последний день — остаток номинала
        am_total = 0.0
        if ex and b.get("maturity"):
            for a in sorted((ex.get("bz") or {}).get("amort") or [], key=lambda x: x.get("amortdate") or ""):
                ad, av = a.get("amortdate"), a.get("value")
                if not ad or not av or ad < today or ad >= b["maturity"]:
                    continue
                am_total += av
                if ad <= horizon:
                    pays.append({"date": ad, "kind": "amortization", "name": r["name"], "ticker": r["ticker"],
                                 "logo": r["logo"], "amount": av * r["qty"] * k_, "est": False})
        if b.get("maturity") and today <= b["maturity"] <= horizon:
            pays.append({"date": b["maturity"], "kind": "redemption", "name": r["name"], "ticker": r["ticker"],
                         "logo": r["logo"], "amount": max(nominal - am_total, 0.0) * r["qty"] * k_, "est": False})
    # дивиденды по акциям (объявленные)
    shares = [r for r in rows if r["type"] in ("share",) and r["uid"] and r["qty"] > 0]

    def srv_divs(secid):
        """Дивиденды с сервера данных (md/dividends) -> [[дата, на акцию, валюта]] в окне [today, horizon]."""
        d = ds_parsed("md/dividends", {"secid": secid}) if secid else None
        if not isinstance(d, dict) or d.get("items") is None:
            return None
        out_ = []
        for x in d["items"]:
            dt = iso_date(x.get("payment")) or iso_date(x.get("record"))
            v_ = qf(x.get("value")) if not isinstance(x.get("value"), (int, float)) else float(x["value"])
            if dt and v_ and today <= dt <= horizon:
                out_.append([dt, v_, str(x.get("currency") or "rub").lower()])
        return out_

    def divs(r):
        st = store()
        v = st.get("div2:" + r["uid"], ttl=DAY)
        if v is None and (r["uid"].startswith("imp:") or not client.ready):
            sid = (moex_secid(r["uid"][4:]) or r["uid"][4:]) if r["uid"].startswith("imp:") else r.get("ticker")
            v = srv_divs(sid)
            if v is not None:
                st.put("div2:" + r["uid"], v)
        elif v is None and client.ready:
            try:
                ds = client.dividends(r["uid"], today + "T00:00:00Z", horizon + "T00:00:00Z")
                v = [[iso_date(d.get("paymentDate")) or iso_date(d.get("recordDate")), qf(d.get("dividendNet")),
                      cur_of(d.get("dividendNet"), r.get("cur") or "rub")] for d in ds]
                st.put("div2:" + r["uid"], v)
            except ApiError:
                v = []
        return r, v or []

    div_data = list(pool_map(divs, shares))
    dcurs = {(x[2] if len(x) > 2 else r.get("cur") or "rub") for r, ds in div_data for x in ds}
    if dcurs - set(rates):
        rates = dict(fx_now(client, dcurs - set(rates)), **rates)
    for r, ds in div_data:
        for x in ds:
            d, per = x[0], x[1]
            dc = (x[2] if len(x) > 2 else r.get("cur") or "rub").lower()
            kk = 1.0 if dc == "rub" else rates.get(dc)
            if d and today <= d <= horizon and per and kk:        # выплата в валюте — переводим в рубли по текущему курсу
                pays.append({"date": d, "kind": "dividend", "name": r["name"], "ticker": r["ticker"], "logo": r["logo"],
                             "amount": per * r["qty"] * kk, "est": False, "cur": dc})
    pays.sort(key=lambda p: p["date"])
    irr = portfolio_irr(irr_items, today)
    metrics = {"count": len(bonds), "value": tot_bonds,
               "ytm": w["ytm"] / w["ytm_v"] if w["ytm_v"] else None,
               "ytm_tax": w["yt"] / w["yt_v"] if w["yt_v"] else None,
               "mdur": w["md"] / w["md_v"] if w["md_v"] else None,
               "ytm_value": w["ytm_v"], "high_yield": high_yield, "high_yield_value": sum(o["value"] for o in high_yield),
               "irr": irr["irr"], "irr_tax": irr["irr_tax"], "irr_value": irr["value"], "irr_count": irr["count"],
               "keyrate": keyrate_brief(),
               "approx_count": sum(1 for x in out if x.get("cf_source") == "approx"),
               "stress": {str(dy): {"rub": stress_rub[dy], "pct": stress_rub[dy] / tot_bonds * 100 if tot_bonds else None}
                          for dy in STRESS_DY},
               "dur": w["dur"] / w["dur_v"] if w["dur_v"] else None,
               "cur_yield": w["cy"] / w["cy_v"] if w["cy_v"] else None,
               "coupons_12m": sum(p["amount"] for p in pays if p["kind"] == "coupon"),
               "issuers": len({issuer_group_key(r["name"]) for r in bonds})}
    out.sort(key=lambda x: -(x.get("value_rub") or 0))
    for x in out:
        if x.get("call") and x.get("call") > today and "call_kind" not in x:
            x["call_kind"] = ckind.get(x.get("uid"))
    return {"rows": out, "metrics": metrics, "ladder": sorted(ladder.items()), "risk": sorted(risk.items(), key=lambda x: -x[1]),
            "kinds": sorted(kinds.items(), key=lambda x: -x[1]), "payments": pays,
            "ratings": apply_ratings(out), "ratings_info": ratings_status(),
            "radar": offer_amort_radar(client, bonds, today, horizon_days=60, infos=infos, exacts=exacts, rates=rates)}


CONC_THRESHOLDS = {"issuer": 15.0, "sector": 35.0, "below_a_minus": 30.0}


def portfolio_concentration(rows):
    """Анализ концентрации портфеля по эмитентам, секторам, валютам и кредитному качеству (без сети)."""
    active = [r for r in (rows or []) if r.get("type") != "futures" and (r.get("value_rub") or 0.0) > 0]
    total = sum(r["value_rub"] for r in active)
    if total <= 0:
        return {"total": 0.0, "issuers": [], "issuers_count": 0, "max_issuer_share": 0.0, "top3_share": 0.0,
                "sectors": [], "currencies": [],
                "below_a_minus": {"value_rub": 0.0, "share": 0.0, "count": 0},
                "unrated_bonds": {"value_rub": 0.0, "share": 0.0, "count": 0},
                "thresholds": dict(CONC_THRESHOLDS), "warnings": []}

    issuers = {}
    sectors = defaultdict(float)
    currencies = defaultdict(float)
    below_rub, below_cnt = 0.0, 0
    unrated_rub, unrated_cnt = 0.0, 0
    a_minus_idx = RATING_SCALE.index("A-")

    for r in active:
        v = float(r["value_rub"])
        rtype = r.get("type") or ""
        cur = (r.get("ticker") or r.get("cur") or "rub")[:3].lower() if rtype == "currency" else (r.get("cur") or "rub").lower()
        currencies[cur] += v
        if rtype == "currency":
            continue

        isin = (r.get("isin") or "").upper()
        if not isin and rtype == "bond":
            try:
                isin = bond_isin(r)
            except Exception:  # noqa: BLE001
                isin = ""
        cat = None
        if isin:
            try:
                cat = tcat_info(isin)
            except Exception:  # noqa: BLE001
                cat = None

        name = (r.get("name") or (cat or {}).get("name") or r.get("ticker") or r.get("uid") or "").strip()
        ikey = issuer_group_key(name) or name.lower()
        if ikey not in issuers:
            disp = "Минфин (ОФЗ)" if ikey == "минфин" else name
            issuers[ikey] = {"key": ikey, "name": disp, "value_rub": 0.0, "count": 0}
        issuers[ikey]["value_rub"] += v
        issuers[ikey]["count"] += 1

        sec = r.get("sector") or (cat or {}).get("sector") or ("etf" if rtype == "etf" else "")
        sectors[sec] += v

        rt = r.get("rating")
        if rt is None and rtype == "bond":
            try:
                rt = best_rating(isin or r.get("ticker"), name)
            except Exception:  # noqa: BLE001
                rt = None
        rv = rt.get("v") if isinstance(rt, dict) else (rt if isinstance(rt, str) else None)
        if rv and rv in RATING_SCALE:
            if RATING_SCALE.index(rv) > a_minus_idx:
                below_rub += v
                below_cnt += 1
        elif rtype == "bond":
            unrated_rub += v
            unrated_cnt += 1

    iss_list = sorted(issuers.values(), key=lambda x: -x["value_rub"])
    for x in iss_list:
        x["share"] = x["value_rub"] / total * 100.0
    max_iss = iss_list[0]["share"] if iss_list else 0.0
    top3 = sum(x["share"] for x in iss_list[:3])

    sec_list = [{"key": k, "value_rub": val, "share": val / total * 100.0}
                for k, val in sorted(sectors.items(), key=lambda kv: -kv[1])]
    cur_list = [{"cur": k, "value_rub": val, "share": val / total * 100.0}
                for k, val in sorted(currencies.items(), key=lambda kv: -kv[1])]

    below_pct = below_rub / total * 100.0
    unrated_pct = unrated_rub / total * 100.0

    warnings = []
    if max_iss > CONC_THRESHOLDS["issuer"] and iss_list:
        top_i = iss_list[0]
        warnings.append({"kind": "issuer", "severity": "high" if max_iss > 25.0 else "warn",
                         "title": "Концентрация на эмитенте",
                         "detail": "%s — %.1f%% портфеля (порог %.0f%%)" % (top_i["name"], max_iss, CONC_THRESHOLDS["issuer"]),
                         "value": max_iss, "threshold": CONC_THRESHOLDS["issuer"]})
    known_secs = [s for s in sec_list if s["key"] and s["key"] != "etf"]
    if known_secs and known_secs[0]["share"] > CONC_THRESHOLDS["sector"]:
        top_s = known_secs[0]
        warnings.append({"kind": "sector", "severity": "warn",
                         "title": "Перекос по сектору",
                         "detail": "%s — %.1f%% портфеля (порог %.0f%%)" % (top_s["key"], top_s["share"], CONC_THRESHOLDS["sector"]),
                         "value": top_s["share"], "threshold": CONC_THRESHOLDS["sector"], "sector": top_s["key"]})
    if below_pct > CONC_THRESHOLDS["below_a_minus"]:
        warnings.append({"kind": "rating", "severity": "high" if below_pct > 50.0 else "warn",
                         "title": "Высокая доля бумаг ниже A-",
                         "detail": "%.1f%% портфеля с рейтингом ниже A- (порог %.0f%%)" % (below_pct, CONC_THRESHOLDS["below_a_minus"]),
                         "value": below_pct, "threshold": CONC_THRESHOLDS["below_a_minus"]})

    return {"total": total, "issuers": iss_list[:10], "issuers_count": len(iss_list),
            "max_issuer_share": max_iss, "top3_share": top3,
            "sectors": sec_list, "currencies": cur_list,
            "below_a_minus": {"value_rub": below_rub, "share": below_pct, "count": below_cnt},
            "unrated_bonds": {"value_rub": unrated_rub, "share": unrated_pct, "count": unrated_cnt},
            "thresholds": dict(CONC_THRESHOLDS), "warnings": warnings}


def offer_amort_radar(client, rows, today=None, horizon_days=60, infos=None, exacts=None, rates=None):
    """Радар ближайших пут-оферт (без объявленного купона или со снижением ставки) и частичных амортизаций."""
    today = (today or date.today().isoformat())[:10]
    t_dt = datetime.strptime(today, "%Y-%m-%d").date()
    end_date = (t_dt + timedelta(days=horizon_days)).isoformat()
    items = []

    for r in (rows or []):
        if r.get("type") != "bond" or (r.get("qty") or 0) <= 0:
            continue
        uid = r.get("uid") or ""
        isin = (r.get("isin") or "").upper()
        if not isin:
            try:
                isin = bond_isin(r)
            except Exception:  # noqa: BLE001
                isin = ""
        b = (infos or {}).get(uid)
        if b is None and client and uid:
            try:
                b = bond_info(client, uid)
            except Exception:  # noqa: BLE001
                b = None
        ex = (exacts or {}).get(uid)
        bz = (ex or {}).get("bz")
        if bz is None and isin:
            try:
                bz = moex_bondization(isin)
            except Exception:  # noqa: BLE001
                bz = None
        opt = None
        if isin:
            try:
                opt = moex_bond_options(isin)
            except Exception:  # noqa: BLE001
                opt = None

        mat = ((b or {}).get("maturity") or "")[:10]
        name = r.get("name") or (b or {}).get("name") or r.get("ticker") or isin
        ticker = r.get("ticker") or ""

        try:
            offs = offer_kinds(bz, opt, (b or {}).get("call"), today)
        except Exception:  # noqa: BLE001
            offs = []

        raw_coupons = list((bz or {}).get("coupons") or [])
        if not raw_coupons and isin:
            try:
                sched = moex_coupon_schedule(isin)
            except Exception:  # noqa: BLE001
                sched = []
            raw_coupons = [{"coupondate": d, "value": v, "valueprc": None} for d, v in sched]
        if not raw_coupons and (b or {}).get("coupons"):
            raw_coupons = [{"coupondate": d, "value": v, "valueprc": None} for d, v in b["coupons"]]

        coupons = sorted(
            [c for c in raw_coupons if c.get("coupondate")],
            key=lambda c: c["coupondate"]
        )

        for o in offs:
            if o.get("kind") != "put" or o.get("status") == "cancelled":
                continue
            od = (o.get("date") or "")[:10]
            if not od or not (today <= od <= end_date):
                continue
            if mat and od >= mat:
                continue

            cur_c = None
            for c in coupons:
                cd = c["coupondate"][:10]
                if cd <= od and ((c.get("valueprc") or 0) > 0 or (c.get("value") or 0) > 0):
                    cur_c = c
            post_c = [c for c in coupons if c["coupondate"][:10] > od and (not mat or c["coupondate"][:10] <= mat)]
            nxt = post_c[0] if post_c else None

            kind = None
            cur_rate = float(cur_c["valueprc"]) if cur_c and cur_c.get("valueprc") is not None else None
            nxt_rate = float(nxt["valueprc"]) if nxt and nxt.get("valueprc") is not None else None
            cur_val = float(cur_c["value"]) if cur_c and cur_c.get("value") is not None else None
            nxt_val = float(nxt["value"]) if nxt and nxt.get("value") is not None else None

            if nxt is None:
                kind = "blind_put"
            else:
                declared = (nxt_rate is not None and nxt_rate > 0) or (nxt_val is not None and nxt_val > 0)
                if not declared:
                    kind = "blind_put"
                elif cur_c is not None:
                    if nxt_rate is not None and cur_rate is not None and nxt_rate > 0 and cur_rate > 0:
                        if nxt_rate < cur_rate - 1e-6:
                            kind = "coupon_cut"
                    elif nxt_val is not None and cur_val is not None and nxt_val > 0 and cur_val > 0:
                        if nxt_val < cur_val - 1e-6:
                            kind = "coupon_cut"

            if kind:
                days_left = (datetime.strptime(od, "%Y-%m-%d").date() - t_dt).days
                items.append({
                    "kind": kind, "date": od, "days_left": days_left,
                    "isin": isin, "ticker": ticker, "name": name,
                    "value_rub": r.get("value_rub"),
                    "cur_rate": cur_rate, "next_rate": nxt_rate,
                    "cur_val": cur_val, "next_val": nxt_val,
                })

        fc = ((b or {}).get("cur") or r.get("cur") or "rub").lower()
        k_ = 1.0 if fc == "rub" else ((rates or {}).get(fc) or 1.0)
        for a in (bz or {}).get("amort") or []:
            ad = (a.get("amortdate") or "")[:10]
            av = float(a.get("value") or 0.0)
            aprc = a.get("valueprc")
            if not ad or av <= 0 or not (today <= ad <= end_date):
                continue
            if mat and ad >= mat:
                continue
            if not mat and aprc is not None and float(aprc) >= 100.0 - 1e-6:
                continue
            days_left = (datetime.strptime(ad, "%Y-%m-%d").date() - t_dt).days
            items.append({
                "kind": "amort", "date": ad, "days_left": days_left,
                "isin": isin, "ticker": ticker, "name": name,
                "value": av, "valueprc": float(aprc) if aprc is not None else None,
                "amount_rub": av * float(r.get("qty") or 0) * k_,
                "value_rub": r.get("value_rub"),
            })

    items.sort(key=lambda x: (x["date"], x["kind"], x["name"]))
    counts = {"blind_put": 0, "coupon_cut": 0, "amort": 0}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    counts["total"] = len(items)
    return {"today": today, "horizon_days": horizon_days, "items": items, "counts": counts}




