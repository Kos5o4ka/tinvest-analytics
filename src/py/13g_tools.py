# ═══════════════════════════════ оферты и конструктор лесенки ═══════════════════════════════
# Справочные подсказки на данных Мосбиржи (bondization) и скринера; не индивидуальные инвестиционные рекомендации.
#
# Как Мосбиржа отдаёт оферты (проверено на ~540 выпусках с датой оферты, ноябрь 2026):
#  1. Список бумаг /iss/engines/stock/markets/bonds/securities[/{ISIN}].json содержит поля
#     PUTOPTIONDATE (ближайшая дата пут-оферты, право держателя; совпадает с OFFERDATE), CALLOPTIONDATE (ближайшая дата колл,
#     право эмитента), BUYBACKDATE/BUYBACKPRICE (ближайшая дата и цена выкупа, put или call — тип не различает).
#     Поля хранят только ОДНУ ближайшую дату каждого типа; пустая дата приходит как null или «0000-00-00».
#  2. bondization.json -> offers[] хранит все даты, но тип записи у него всего три значения offertype:
#     «Оферта» — пут-оферта (все будущие «Оферта» в выборке были put: совпадают с PUTOPTIONDATE или идут следующими
#     циклами, из-за этого у выпуска может быть несколько будущих put-дат);
#     «Оферта/Погашение» — досрочное погашение по усмотрению эмитента (call): дата совпадает с CALLOPTIONDATE, а запись с
#     пустой датой «0000-00-00» — просто погашение в срок, это не оферта;
#     «Оферта (состоялось)» — уже прошедшая оферта.
#     Период предъявления (offerdatestart/offerdateend) Мосбиржа публикует только перед самой офертой.
#  3. /iss/securities/{ISIN}.json (description) даёт лишь BUYBACKDATE, без типа — для классификации не нужен.
#  4. T-Invest API (Bond) отдаёт одну дату callDate без указания типа; поля даты put в API нет. Эта дата в приложении
#     считается колл, если Мосбиржа не знает такой даты как пут.
#  Среди выборки не нашлось выпуска с одновременными put и call, но код допускает обе записи (даже на одну дату).

OF_PRICE_EPS, OF_MARGIN = 0.1, 0.5      # допуск цены, п. п.; запас до медианы аналогов, п. п.
OF_CALL_WORDS = ("колл", "call", "досроч", "погашени", "усмотрен")     # право эмитента
OF_PUT_WORDS = ("put", "пут", "по требованию", "выкуп", "предъявлен")  # право держателя
OF_KIND_ORDER = {"put": 0, "call": 1, "unknown": 2}
OPT_URL = ("https://iss.moex.com/iss/engines/stock/markets/bonds/securities/%s.json?iss.meta=off&iss.only=securities"
           "&securities.columns=SECID,BOARDID,BUYBACKDATE,BUYBACKPRICE,CALLOPTIONDATE,PUTOPTIONDATE")


def moex_bond_options(isin):
    """Явные даты put/call выпуска из списка бумаг Мосбиржи: {'put': [даты], 'call': [даты], 'prices': {дата: цена}}.
    Кэш 24 ч; ошибка кэшируется на 1 ч, тогда None."""
    isin = (isin or "").strip().upper()
    if not isin or not re.match(r"^[A-Z0-9]{4,14}$", isin):
        return None
    st = store()
    key = "bopt1:" + isin
    v = st.get(key, ttl=BC_TTL)
    if v is not None:
        if v.get("ok"):
            return v
        if time.time() - v.get("ts", 0) < BC_ERR_TTL:
            return None
    try:
        rows = _bc_table(json.loads(http_text(OPT_URL % isin, 20)), "securities")
        out = {"ok": True, "ts": time.time(), "put": [], "call": [], "prices": {}}
        for r in rows:
            for fld, k in (("PUTOPTIONDATE", "put"), ("CALLOPTIONDATE", "call")):
                d = _of_date(r.get(fld))
                if d and d not in out[k]:
                    out[k].append(d)
            bd = _of_date(r.get("BUYBACKDATE"))
            if bd and r.get("BUYBACKPRICE"):
                out["prices"][bd] = r["BUYBACKPRICE"]
        out["put"].sort()
        out["call"].sort()
    except Exception:  # noqa: BLE001
        out = {"ok": False, "ts": time.time()}
    st.put(key, out)
    return out if out.get("ok") else None


OF_BROKER_NEAR = 21                                   # дней: дата брокера рядом с датой Мосбиржи — то же событие


def _of_text_kind(t, has_period):
    """Тип по тексту offertype: ('put'|'call'|'unknown', вывод сделан по слабому признаку)."""
    base = re.sub(r"\(.*?\)", "", t).strip().lower()
    if any(w in base for w in OF_CALL_WORDS):
        return "call", False
    if any(w in base for w in OF_PUT_WORDS):
        return "put", False
    if base == "оферта":                      # так Мосбиржа обозначает пут-оферту
        return "put", not has_period
    return "unknown", False


def offer_kinds(bz, opt, broker_call=None, today=None, with_done=False):
    """Все БУДУЩИЕ оферты выпуска из всех источников, без дублей по (дата, тип).
    Запись: {date, kind: put|call|unknown, source, price, period_start, period_end, status: scheduled|cancelled, inferred}.
    with_done=True добавляет и состоявшиеся оферты из bondization (status 'done'; нужно календарю за прошлые месяцы).
    Приоритет: явные поля PUTOPTIONDATE/CALLOPTIONDATE, затем тип записи bondization, затем дата брокера (присоединяется к близкой дате
    Мосбиржи, иначе 'unknown'). Одна дата может быть и put, и call — тогда две записи. Неопределимый тип — 'unknown'."""
    today = today or date.today().isoformat()
    recs = {}

    def add(d, kind, source, price=None, ps=None, pe=None, status="scheduled", inferred=False):
        if not d or d <= today:
            return
        r = recs.get((d, kind))
        if r is None:
            recs[(d, kind)] = {"date": d, "kind": kind, "source": source, "price": price, "period_start": ps,
                               "period_end": pe, "status": status, "inferred": inferred}
            return
        if source not in r["source"].split("+"):
            r["source"] += "+" + source
        for k, val in (("price", price), ("period_start", ps), ("period_end", pe)):
            if r[k] is None:
                r[k] = val
        if status == "cancelled":
            r["status"] = "cancelled"
        r["inferred"] = r["inferred"] and inferred
    prices = (opt or {}).get("prices") or {}
    for k in ("put", "call"):
        for d in (opt or {}).get(k) or []:
            add(d, k, "moex_" + k + "_field", prices.get(d))
    for o in (bz or {}).get("offers") or []:
        t = o.get("offertype") or ""
        d = _of_date(o.get("offerdate"))
        tl = t.lower()
        done = "состоял" in tl and "не состоял" not in tl
        if not d or "оферт" not in tl or (done and not with_done):
            continue
        ps, pe = _of_date(o.get("offerdatestart")), _of_date(o.get("offerdateend"))
        kind, weak = _of_text_kind(t, bool(ps and pe))
        cancelled = "отмен" in tl or "не состоял" in tl
        add(d, kind, "moex_offertype", o.get("price"), ps, pe, "cancelled" if cancelled else ("done" if done else "scheduled"), weak)
    bc = _of_date(broker_call)
    if bc and bc > today:
        # Брокер отдаёт одну дату без типа и нередко на несколько дней раньше даты Мосбиржи (например, 09.02 вместо пута 12.02):
        # близкую дату Мосбиржи считаем тем же событием, иначе честно пишем «тип не указан».
        near = [k for k in recs if abs(_of_days(bc, k[0])) <= OF_BROKER_NEAR]
        if near:
            r = recs[min(near, key=lambda k: abs(_of_days(bc, k[0])))]
            if "broker" not in r["source"].split("+"):
                r["source"] += "+broker"
        else:
            add(bc, "unknown", "broker")
    for d in {k[0] for k in recs if k[1] in ("put", "call")}:      # «неизвестный» на дату с известным типом — тот же факт
        recs.pop((d, "unknown"), None)
    return sorted(recs.values(), key=lambda x: (x["date"], OF_KIND_ORDER[x["kind"]]))


def offers_of_isin(isin, broker_call=None, today=None):
    """Будущие оферты выпуска по кэшированным данным Мосбиржи; без данных — только дата брокера."""
    bz = opt = None
    try:
        bz = moex_bondization(isin)
    except Exception:  # noqa: BLE001
        pass
    try:
        opt = moex_bond_options(isin)
    except Exception:  # noqa: BLE001
        pass
    return offer_kinds(bz or {}, opt, broker_call, today)


def offer_kind_on(offs, d):
    """Тип оферт на дату d: put | call | both | unknown (если даты нет в списке)."""
    live = [x for x in offs if x["status"] != "cancelled"]
    near = [x["date"] for x in live if abs(_of_days(d, x["date"])) <= OF_BROKER_NEAR]
    if near and d not in near:                     # дата брокера чуть сдвинута относительно Мосбиржи
        d = min(near, key=lambda x: abs(_of_days(d, x)))
    ks = {x["kind"] for x in live if x["date"] == d}
    return "both" if {"put", "call"} <= ks else (next(iter(ks)) if len(ks) == 1 else ("put" if "put" in ks else "unknown"))


def annotate_offer_kinds(rows, today=None):
    """Строкам с датой оферты/колл (r['call']) добавляет r['call_kind']: put | call | both | unknown."""
    today = today or date.today().isoformat()
    rows = [r for r in rows if r.get("isin") and r.get("call") and r["call"] > today]

    def one(r):
        try:
            return offer_kind_on(offers_of_isin(r["isin"], r["call"], today), r["call"])
        except Exception:  # noqa: BLE001
            return None
    for r, k in zip(rows, pool_map(one, rows)):
        r["call_kind"] = k


def offer_alert_text(kind, left, ds):
    """Текст тревоги «Мониторинга» по типу оферты; left — дней до даты, ds — дата дд.мм.гггг."""
    if kind == "put":
        return "Пут-оферта %s (через %d дн.): решите, предъявлять ли бумагу к выкупу" % (ds, left)
    if kind == "call":
        return "Колл-опцион %s (через %d дн.): эмитент может досрочно погасить выпуск, заявку подавать не нужно" % (ds, left)
    if kind == "both":
        return "Пут-оферта и колл-опцион %s (через %d дн.): проверьте условия в карточке выпуска" % (ds, left)
    return "Оферта %s (через %d дн.): тип не указан, проверьте условия в документах выпуска" % (ds, left)


OF_KIND_RU = {"put": "пут-оферта", "call": "колл-опцион эмитента", "unknown": "оферта (тип не указан)"}


def _of_days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def _of_med(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)


def _of_date(s):
    return s if s and len(s) == 10 and not s.startswith("0000") else None


def _of_aci(bz, flows, d):
    """НКД на дату d на одну облигацию: линейно внутри купонного периода (по ближайшему будущему купону потоков)."""
    prev = [c["coupondate"] for c in bz["coupons"] if c.get("coupondate") and c["coupondate"] <= d]
    nxt = [(x[0], x[1]) for x in flows if x[0] > d and x[1] > 0]
    if not prev or not nxt:
        return 0.0
    p0, (n0, amt) = max(prev), min(nxt)
    span = _of_days(p0, n0)
    return amt * _of_days(p0, d) / span if span > 0 else 0.0


def _of_cut(bz, flows, face, od, op):
    """Потоки до оферты: покупатель по оферте получает op x остаток номинала и НКД на дату оферты."""
    head = [x for x in flows if x[0] < od]
    remain = face - sum(x[2] for x in head)
    c_od = sum(x[1] for x in flows if x[0] == od)
    acc = 0.0 if c_od else _of_aci(bz, flows, od)
    return head + [(od, c_od + acc, remain * op)], remain


def _of_peers(me, rating, floating, dur):
    """Медиана доходности и число аналогов: тот же рейтинг +/-1 ступень (если мало, +/-2), дюрация близка к dur."""
    if not dur or not rating or rating not in RATING_SCALE:
        return None, 0
    ri = RATING_SCALE.index(rating)
    uni = _bc_universe()
    for width in (1, 2):
        pool = []
        for e in uni:
            rt = e.get("_rt")
            if e["cur"] != "RUB" or not (0 < e["yield"] < 40) or not e.get("dur") or not rt or rt["v"] not in RATING_SCALE:
                continue
            if bool((e["_ci"] or {}).get("floating")) != bool(floating):
                continue
            if abs(RATING_SCALE.index(rt["v"]) - ri) > width or (me and e["_isin"] == me["_isin"]):
                continue
            if me and me.get("_iss") and e["_iss"] and e["_iss"] == me["_iss"]:
                continue
            if abs(e["dur"] - dur) > max(0.4, dur * 0.4):
                continue
            pool.append((abs(e["dur"] - dur) + 0.5 * abs(RATING_SCALE.index(rt["v"]) - ri), e["yield"]))
        if len(pool) >= 3:
            pool.sort()
            return _of_med([y for _, y in pool[:12]]), min(len(pool), 12)
    return None, 0


def _of_pct(x):
    return ("%.1f" % x).replace(".", ",")


def of_new_coupon(coupons, od, face, floating=False):
    """Купон на период после пут-оферты od по купонам Мосбиржи. Объявленным считается первый купон с датой ПОСЛЕ оферты,
    у которого указан размер (value или valueprc).
    -> {'status': 'announced'|'pending'|'formula', 'date', 'rate' (% годовых), 'value'};
    'pending' — эмитент ещё не объявил ставку; 'formula' — у флоатера размера нет: купон считается по формуле (ключевая ставка + спред)."""
    cps = sorted(((c.get("coupondate"), c.get("value"), c.get("valueprc")) for c in coupons or [] if c.get("coupondate")),
                 key=lambda x: x[0])
    nxt = next(((d, v, vp) for d, v, vp in cps if d > od), None)
    if nxt and (nxt[1] or nxt[2]):
        prev = max([d for d, _, _ in cps if d <= od] or [od])
        rate = nxt[2] if nxt[2] else nxt[1] / max(face, 1e-9) * 365.0 / max(_of_days(prev, nxt[0]), 1) * 100.0
        return {"status": "announced", "date": nxt[0], "rate": rate, "value": nxt[1]}
    return {"status": "formula" if floating else "pending", "date": nxt[0] if nxt else None, "rate": None, "value": None}


def of_outcome(hold_yield, peer_median, margin=None):
    """Сравнение доходности бумаги с новым купоном и медианы аналогов -> ('below'|'fair'|'above', разница в п. п.) или (None, None).
    below: ниже рынка больше чем на margin; above: выше рынка больше чем на margin; иначе fair (граница включается в fair)."""
    if hold_yield is None or peer_median is None:
        return None, None
    m = OF_MARGIN if margin is None else margin
    gap = hold_yield - peer_median
    return ("below" if gap < -m else "above" if gap > m else "fair"), gap


def _of_dm(d):
    return "%s.%s" % (d[8:10], d[5:7])


def of_helper(rec):
    """Помощник по пут-оферте (справочно): статус купона, итог сравнения с рынком, даты подачи заявки. rec — запись _of_one.
    Рекомендация появляется только когда эмитент объявил купон на период после оферты."""
    if rec.get("kind") != "put":
        return None
    ps, pe = rec.get("period_start"), rec.get("period_end")
    window = ("с %s по %s" % (_of_dm(ps), _of_dm(pe))) if ps and pe else None
    h = {"status": rec.get("coupon_status") or "pending", "outcome": None, "gap": None, "window": window, "title": "", "text": "",
         "numbers": "", "apply": "", "risk_notes": list(rec.get("risk_notes") or []), "kb": "offers",
         "disclaimer": "Справочная информация, не инвестиционная рекомендация."}
    if rec.get("period_status") == "closed":
        h.update(status="closed", title="Приём заявок закончился", text="Подать заявку уже нельзя: бумага останется у вас.")
        return h
    h["apply"] = ("Подать заявку через брокера %s (дата выкупа %s)." % (window, _of_dm(rec["date"]))) if window else \
        ("Период приёма заявок пока не опубликован. Дата выкупа по оферте: %s." % _of_dm(rec["date"]))
    if h["status"] == "pending":
        h.update(title="Новый купон ещё не объявлен",
                 text="Новый купон ещё не объявлен. Обычно его публикуют примерно за день до открытия приёма заявок — тогда здесь появится подсказка.")
        if window:
            h["text"] += " Ожидаемый приём заявок: %s." % window
        return h
    if h["status"] == "formula":
        h.update(title="Купон по формуле",
                 text="Купон по формуле: плавающая ставка зависит от ключевой ставки, отдельного объявления нет. Сравнение с рынком здесь "
                      "не строится; решайте по условиям выпуска и своим целям.")
        return h
    nr, hy, med = rec.get("new_rate"), rec.get("hold_yield"), rec.get("peer_median")
    h["numbers"] = "Новый купон %s %% годовых" % _of_pct(nr or 0)
    if hy is not None:
        h["numbers"] += "; доходность при текущей цене %s %%" % _of_pct(hy)
    if med is not None:
        h["numbers"] += "; медиана похожих выпусков %s %% (%d шт.)" % (_of_pct(med), rec.get("peers_n") or 0)
    code, gap = of_outcome(hy, med)
    h["outcome"], h["gap"] = code, gap
    if code == "below":
        h.update(title="Купон ниже рынка на %s п. п. — разумно предъявить к оферте" % _of_pct(-gap),
                 text="Деньги по оферте (%s %% номинала) можно вложить в бумагу с более высокой доходностью." % _of_pct(rec["offer_price"]))
    elif code == "above":
        h.update(title="Купон выше рынка — оставить выгоднее",
                 text="Доходность выше медианы похожих выпусков на %s п. п.: предъявлять нет смысла, если деньги не нужны." % _of_pct(gap))
    elif code == "fair":
        h.update(title="Купон в рынке — можно оставить", text="Доходность в пределах %s п. п. от медианы похожих выпусков." % _of_pct(OF_MARGIN))
    else:
        h.update(title="Купон объявлен", text="Сравнить с рынком не с чем: подходящих аналогов мало. Оцените ставку сами.")
    if rec.get("price") is not None and rec["price"] > rec["offer_price"] + OF_PRICE_EPS:
        h["text"] += " Но рыночная цена (%s %%) выше цены выкупа (%s %%): на бирже получите больше, чем по оферте." % (
            _of_pct(rec["price"]), _of_pct(rec["offer_price"]))
    return h


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
            "text": "Мосбиржа не сообщает, кто решает: держатель (put) или эмитент (call). Не подавайте заявку, пока не проверите "
                    "условия в документах выпуска или у брокера."}


def _of_hint(rec, risk_notes):
    price, op, med = rec["price"], rec["offer_price"], rec["peer_median"]
    hy, thr = rec["hold_yield"], rec["threshold"]
    how = ("Заявку на выкуп подаёт брокер; обычно он принимает поручения на несколько дней раньше окончания периода "
           "предъявления — уточните сроки у брокера.")
    if rec["period_status"] == "closed":
        return {"code": "closed", "title": "Период предъявления закончился",
                "text": "Принимать заявки на выкуп уже поздно: бумага останется у вас, условия после оферты определяет эмитент."}
    if price is not None and price > op + OF_PRICE_EPS:
        return {"code": "sell_market", "title": "Выгоднее продать на бирже",
                "text": "Рыночная цена (%s %%) выше цены выкупа (%s %%): на бирже получите больше, чем по оферте. "
                        "Предъявлять бумаги не нужно." % (_of_pct(price), _of_pct(op))}
    if risk_notes:
        low = (" Рыночная цена (%s %%) заметно ниже цены выкупа: рынок сомневается, что эмитент выкупит бумаги." % _of_pct(price)
               if price is not None and price < op - 10 else "")
        return {"code": "put", "title": "Рассмотрите предъявление",
                "text": "Есть признаки повышенного риска эмитента: %s. Предъявление к выкупу по %s %% вернёт деньги по номиналу "
                        "до того, как условия могут измениться.%s %s" % ("; ".join(risk_notes), _of_pct(op), low, how)}
    if rec["floating"] and not rec["coupon_known"]:
        return {"code": "hold", "title": "Можно держать",
                "text": "Купон плавающий и следует за ключевой ставкой, поэтому после оферты он обычно остаётся на уровне рынка. "
                        "Предъявлять нужно, только если вам нужны деньги."}
    if rec["coupon_known"] and hy is not None:
        code = of_outcome(hy, med)[0]
        if code == "below":
            return {"code": "put", "title": "Рассмотрите предъявление",
                    "text": "Новый купон (%s %% годовых) даёт доходность %s %% против %s %% у похожих выпусков (%d шт.): ниже "
                            "рынка больше чем на 0,5 п. п. Деньги по оферте (%s %%) можно вложить в бумагу с более высокой "
                            "доходностью. %s" % (_of_pct(rec["new_rate"] or 0), _of_pct(hy), _of_pct(med), rec["peers_n"],
                                                 _of_pct(op), how)}
        if med is None:
            return {"code": "hold", "title": "Можно держать",
                    "text": "Новый купон известен (%s %% годовых), доходность после оферты %s %%. Сравнить с рынком не с чем: "
                            "подходящих аналогов мало. Оцените ставку сами." % (_of_pct(rec["new_rate"] or 0), _of_pct(hy))}
        return {"code": "hold", "title": "Можно держать",
                "text": "Новый купон (%s %% годовых) даёт доходность %s %% против %s %% у похожих выпусков (%d шт.): %s. "
                        "Предъявлять нет смысла, если деньги не нужны." % (_of_pct(rec["new_rate"] or 0), _of_pct(hy), _of_pct(med),
                                                                            rec["peers_n"], "выше рынка" if code == "above" else "на уровне рынка")}
    t = "Новый купон ещё не объявлен: дождитесь объявления ставки."
    if rec["urgent"]:
        t += " Срок предъявления близко. " + how
    return {"code": "wait", "title": "Дождитесь объявления ставки", "text": t}


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

LD_MAX_BONDS, LD_YTM_MAX, LD_NOTCH, LD_SPREAD_MAX = 20, 40.0, 0.5, 9.0      # максимум бумаг, предел доходности (аномалии), штраф за ступень рейтинга, п. п.


def _ld_int(v, lo, hi, d):
    try:
        x = int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return d
    return max(lo, min(hi, x))


def _ld_flag(v, d):
    return d if v in (None, "") else str(v).lower() in ("1", "true", "on", "yes")


def _ld_add(d, years):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=round(years * 365.25))).strftime("%Y-%m-%d")


def _ld_months(bz, today):
    """Месяцы (1-12), в которые бумага платит купон (по ближайшим 14 месяцам графика)."""
    lim = _ld_add(today, 14 / 12.0)
    return sorted({int(c["coupondate"][5:7]) for c in bz["coupons"] if c.get("coupondate") and today < c["coupondate"] <= lim})


_LD_IDS = {}


def _ld_bz(isin):
    """Потоки выпуска: по ISIN, а если пусто (так бывает у ОФЗ) — по коду бумаги на Мосбирже."""
    bz = _safe_call(moex_bondization, isin)
    sid = _LD_IDS.get(isin)
    if not bz and sid and sid != isin:
        bz = _safe_call(moex_bondization, sid)
    return bz


def _ld_cands(q_min_rating, floaters, amort, min_turn, today):
    """Вселенная -> кандидаты лесенки: (запись, рейтинг, дата окончания, вид окончания, годы до окончания)."""
    mi = RATING_SCALE.index(q_min_rating)
    out = []
    for e in _bc_universe():
        ci = e.get("_ci") or {}
        if e["cur"] != "RUB" or not (0 < e["yield"] <= LD_YTM_MAX) or not e.get("mat") or e["mat"] <= today:
            continue
        if ci.get("perpetual") or ci.get("subordinated") or e.get("sub") and "суборд" in str(e.get("sub")).lower():
            continue
        if bool(ci.get("floating")) and not floaters or bool(ci.get("amort")) and not amort:
            continue
        if (e.get("turn") or 0) < min_turn:
            continue
        if e.get("spread") is not None and e["spread"] > LD_SPREAD_MAX:      # слишком щедрая доходность — признак ловушки
            continue
        _LD_IDS[e["_isin"]] = e["id"]
        rt = e.get("_rt")
        rv = rt["v"] if rt else ("AAA" if e["kind"] == "ofz" else None)
        if rv not in RATING_SCALE or RATING_SCALE.index(rv) > mi:
            continue
        out.append({"e": e, "rv": rv, "end": e["mat"], "kind": "maturity", "t": _of_days(today, e["mat"]) / 365.25, "offs": []})
    # Срок до даты оферты только для ПУТ (решает держатель). Колл (решает эмитент) и «тип не указан» срок не меняют:
    # ступень стоит на погашении, а доходность считается к худшему (см. _ld_eval).
    wo = [c for c in out if c["e"].get("offer") and today < c["e"]["offer"] < c["e"]["mat"]]
    for c, offs in zip(wo, pool_map(lambda c: _safe_call(offers_of_isin, c["e"]["_isin"], c["e"]["offer"], today) or [], wo, workers=8)):
        c["offs"] = [o for o in offs if o["status"] != "cancelled"]
        pd = min([o["date"] for o in c["offs"] if o["kind"] == "put" and today < o["date"] < c["e"]["mat"]] or [""])
        if pd:
            c["end"], c["kind"], c["t"] = pd, "offer", _of_days(today, pd) / 365.25
    return out


def _ld_eval(c, bz, today):
    """Потоки и доходности кандидата с учётом типа оферты. None, если графика выплат нет.
    flows — потоки лесенки: до пут-оферты для пута, иначе до погашения; ytm (%) — доходность для отбора и показа:
    YTP для пута, YTW для колла, для «тип не указан» — меньшая из доходности к дате оферты и к погашению."""
    e = c["e"]
    fl_ = bool((e.get("_ci") or {}).get("floating"))
    face = float(e.get("nominal") or 1000.0)
    full = (_safe_call(bond_flows, bz, today, face, "maturity", fl_) or (None,))[0] if bz else None
    if not full:
        return None
    dirty = e["price"] / 100.0 * face + _of_aci(bz, full, today)
    yk = yields_by_kind(bz, today, face, dirty, c.get("offs") or [], floating=fl_)
    if not yk:
        return None
    b = yk["basis"]
    y = {"put": yk["ytp"], "call": yk["ytw"], "unknown": min([v for v in (yk["yto"], yk["ytm"]) if v is not None], default=None)}.get(b, yk["ytm"])
    put = b == "put"
    return {"face": face, "dirty": dirty, "yk": yk, "basis": b, "y": y, "flows": yk["flows"] if put else full,
            "end": yk["end"] if put else yk["maturity"], "kind": "offer" if put else "maturity"}


def ladder_payload(cfg, q=None):
    q = q or {}
    if q.get("mode") == "portfolio":
        return ladder_portfolio(cfg, q.get("account", "all") or "all")
    today = date.today().isoformat()
    total = _fnum(q.get("sum"), 1000.0, 1e10, 500000.0)
    years = _ld_int(q.get("years"), 1, 10, 5)
    rungs_n = _ld_int(q.get("rungs"), 1, 12, years) if q.get("rungs") not in (None, "") else years
    mr = (q.get("min_rating") or "A").upper()
    mr = mr if mr in RATING_SCALE else "A"
    floaters, amort = _ld_flag(q.get("floaters"), False), _ld_flag(q.get("amort"), True)
    monthly = _ld_flag(q.get("monthly"), False)
    cap = _fnum(q.get("max_issuer"), 1.0, 100.0, max(5, round(100.0 / rungs_n / 2)))
    min_turn = _fnum(q.get("min_turnover"), 0.0, 1e12, 1000000.0)
    par = {"sum": total, "years": years, "rungs": rungs_n, "min_rating": mr, "floaters": floaters, "amort": amort,
           "max_issuer": cap, "min_turnover": min_turn, "monthly": monthly}
    warnings, notes = [], []
    cands = _ld_cands(mr, floaters, amort, min_turn, today)
    step = years / float(rungs_n)
    per_rung = total / rungs_n
    k_cap = int(-(-100.0 // (rungs_n * cap)))              # сколько бумаг на ступень нужно, чтобы доля эмитента не превысила лимит
    k = max(1, k_cap)
    if rungs_n * k > LD_MAX_BONDS:
        k = max(1, LD_MAX_BONDS // rungs_n)
        warnings.append("Лимит доли эмитента %s %% при таком числе ступеней потребовал бы больше %d бумаг; взято по %d на ступень, "
                        "доля одного эмитента может быть выше лимита." % (("%g" % cap).replace(".", ","), LD_MAX_BONDS, k))
    k = min(k, 3 if rungs_n * 3 <= LD_MAX_BONDS else k)
    if per_rung / k < 3000 and k > 1:
        k = max(1, int(per_rung // 3000))
    if per_rung < 1500:
        warnings.append("Сумма слишком мала для %d ступеней: на ступень приходится около %d ₽, а облигация стоит около 1 000 ₽ "
                        "и больше. Уменьшите число ступеней." % (rungs_n, round(per_rung)))
    win = []
    for i in range(rungs_n):
        mid = step * (i + 1)
        win.append((max(0.25, mid - step / 2.0), mid + step / 2.0 if i < rungs_n - 1 else min(mid + step / 2.0, years + 0.5), mid))
    # кандидаты по окнам; для «ровного дохода» подгружаем график купонов у лучших в каждом окне
    pools = []
    for lo, hi, mid in win:
        pl = [c for c in cands if lo <= c["t"] <= hi]
        for c in pl:
            ri = RATING_SCALE.index(c["rv"])
            c["score"] = c["e"]["yield"] - LD_NOTCH * ri - 0.3 * abs(c["t"] - mid) / max(step / 2.0, 0.25)
        pl.sort(key=lambda c: -c["score"])
        pools.append(pl)
    bzs = {}
    if monthly:
        want = [c["e"]["_isin"] for pl in pools for c in pl[:10]]
        for isin, bz in zip(want, pool_map(lambda x: _ld_bz(x), want, workers=8)):
            bzs[isin] = bz
    # колл и «тип не указан»: для отбора берём доходность к худшему, а не доходность Мосбиржи (она может быть к дате колла)
    risky = [c for pl in pools for c in pl[:12] if c["offs"] and c["kind"] != "offer"]
    need_ = sorted({c["e"]["_isin"] for c in risky if c["e"]["_isin"] not in bzs})
    for isin, bz in zip(need_, pool_map(lambda x: _ld_bz(x), need_, workers=8)):
        bzs[isin] = bz
    for c in risky:
        ev = _ld_eval(c, bzs.get(c["e"]["_isin"]), today)
        if ev and ev["y"] is not None:
            c["score"] += ev["y"] * 100.0 - c["e"]["yield"]
    for pl in pools:
        pl.sort(key=lambda c: -c["score"])
    chosen = [[] for _ in range(rungs_n)]
    used_iss, iss_share, covered = set(), defaultdict(float), set()

    def iss_key(c):
        e = c["e"]
        return e["_isin"] if e["kind"] == "ofz" or not e.get("_iss") else tuple(sorted(e["_iss"]))
    order = sorted(range(rungs_n), key=lambda i: len(pools[i]))        # сначала ступени с наименьшим выбором
    share = 100.0 / (rungs_n * k)
    for i in order:
        pl = pools[i]
        for strict in (True, False):
            while len(chosen[i]) < k:
                best = None
                for c in pl:
                    ik = iss_key(c)
                    if c in chosen[i] or any(iss_key(x) == ik for x in chosen[i]):
                        continue
                    if strict and ik in used_iss:
                        continue
                    if not strict and iss_share[ik] + share > cap + 1e-9:
                        continue
                    sc = c["score"]
                    if monthly and bzs.get(c["e"]["_isin"]):
                        c["months"] = _ld_months(bzs[c["e"]["_isin"]], today)
                        sc += 0.25 * len(set(c["months"]) - covered) + 0.0
                    if best is None or sc > best[0]:
                        best = (sc, c)
                if not best:
                    break
                c = best[1]
                chosen[i].append(c)
                used_iss.add(iss_key(c))
                iss_share[iss_key(c)] += share
                if monthly and c.get("months"):
                    covered |= set(c["months"])
            if len(chosen[i]) >= k:
                break
    # проверка дефолтных флагов у выбранных; замена на следующих в окне
    flat = [(i, c) for i in range(rungs_n) for c in chosen[i]]
    flg = dict(zip([c["e"]["_isin"] for _, c in flat], pool_map(lambda x: _mon_flags(x[1]["e"]["_isin"]), flat, workers=8)))
    for i in range(rungs_n):
        bad_ = [c for c in chosen[i] if (flg.get(c["e"]["_isin"]) or {}).get("default") or (flg.get(c["e"]["_isin"]) or {}).get("tech")]
        for c in bad_:
            chosen[i].remove(c)
            warnings.append("%s исключена: по данным Мосбиржи у выпуска был дефолт." % c["e"]["name"])
            have = {iss_key(x) for x in chosen[i]}
            for c2 in pools[i]:
                if c2 not in chosen[i] and c2 is not c and iss_key(c2) not in have and iss_key(c2) not in used_iss:
                    f2_ = _mon_flags(c2["e"]["_isin"])
                    if not (f2_.get("default") or f2_.get("tech")):
                        chosen[i].append(c2)
                        used_iss.add(iss_key(c2))
                        break
    sel = [c for i in range(rungs_n) for c in chosen[i]]
    for c in sel:
        if c["e"]["_isin"] not in bzs:
            bzs[c["e"]["_isin"]] = None
    need = [c["e"]["_isin"] for c in sel if bzs.get(c["e"]["_isin"]) is None]
    for isin, bz in zip(need, pool_map(lambda x: _ld_bz(x), need, workers=8)):
        bzs[isin] = bz
    # потоки и цена с НКД; бумаги без потоков отбрасываем, на их место ставим следующих кандидатов окна
    def prep(c):
        e = c["e"]
        bz = bzs.get(e["_isin"])
        if bz is None and e["_isin"] not in bzs:
            bz = bzs[e["_isin"]] = _ld_bz(e["_isin"])
        ev = _ld_eval(c, bz, today)
        if not ev:
            return "%s пропущена: нет данных о графике выплат." % e["name"]
        yk, y = ev["yk"], ev["y"]
        if y is not None and y * 100.0 > LD_YTM_MAX:
            return "%s пропущена: расчётная доходность выглядит аномальной." % e["name"]
        live = [o for o in c["offs"] if o["status"] != "cancelled"]
        c.update(flows=ev["flows"], face=ev["face"], dirty=ev["dirty"], ytm=(y * 100.0 if y is not None else e["yield"]),
                 end=ev["end"], kind=ev["kind"], months=_ld_months(bz, today), ybasis=ev["basis"],
                 ytm_mat=yk["ytm"] * 100.0 if yk["ytm"] is not None else None,
                 call_dates=sorted({o["date"] for o in live if o["kind"] == "call" and o["date"] < yk["maturity"]}),
                 unk_date=min([o["date"] for o in live if o["kind"] == "unknown" and o["date"] < yk["maturity"]] or [None], key=lambda x: x or "9"))
        return None
    for i in range(rungs_n):
        keep = []
        for c in chosen[i]:
            er = prep(c)
            if er:
                warnings.append(er)
            else:
                keep.append(c)
        if keep and len(keep) < k or (not keep and chosen[i]):
            have = {iss_key(x) for x in keep}
            tried = 0
            for c2 in pools[i]:
                if len(keep) >= k or tried >= 8:
                    break
                if c2 in chosen[i] or iss_key(c2) in have or iss_key(c2) in used_iss:
                    continue
                f2_ = _mon_flags(c2["e"]["_isin"])
                if f2_.get("default") or f2_.get("tech"):
                    continue
                tried += 1
                if not prep(c2):
                    keep.append(c2)
                    have.add(iss_key(c2))
                    used_iss.add(iss_key(c2))
        chosen[i] = keep
    # покупка: целые лоты, остаток — свободные деньги
    free = total
    for i in range(rungs_n):
        if not chosen[i]:
            continue
        tgt = per_rung / len(chosen[i])
        for c in chosen[i]:
            c["target"] = tgt
            c["lots"] = int(tgt // c["dirty"])
            free -= c["lots"] * c["dirty"]
    allc = [c for i in range(rungs_n) for c in chosen[i]]
    while allc:
        opts = [c for c in allc if c["dirty"] <= free + 1e-9 and c["target"] - c["lots"] * c["dirty"] + 0.5 * c["dirty"] > 0]
        if not opts:
            break
        c = max(opts, key=lambda c: c["target"] - c["lots"] * c["dirty"])
        c["lots"] += 1
        free -= c["dirty"]
    for i in range(rungs_n):
        if not chosen[i]:
            warnings.append("На ступень «около %s» не нашлось подходящих бумаг (рейтинг не ниже %s, оборот от %s ₽/день): "
                            "деньги ступени остались свободными. Смягчите рейтинг или ликвидность."
                            % (_ld_when(win[i][2]), mr, "{:,}".format(int(min_turn)).replace(",", " ")))
        elif len(chosen[i]) < k:
            warnings.append("На ступень «около %s» нашлось только %d из %d нужных бумаг." % (_ld_when(win[i][2]), len(chosen[i]), k))
    zero = [c for c in allc if c["lots"] <= 0]
    for c in zero:
        warnings.append("%s не куплена: цена лота выше выделенной суммы." % c["e"]["name"])
    allc = [c for c in allc if c["lots"] > 0]
    invested = sum(c["lots"] * c["dirty"] for c in allc)
    # денежный поток
    mon = defaultdict(lambda: [0.0, 0.0])
    agg = defaultdict(float)
    cp12 = 0.0
    lim12 = _ld_add(today, 1)
    for c in allc:
        for d, cp, pr in c["flows"]:
            mon[d[:7]][0] += cp * c["lots"]
            mon[d[:7]][1] += pr * c["lots"]
            agg[d] += (cp + pr) * c["lots"]
            if d <= lim12:
                cp12 += cp * c["lots"]
    cfm = []
    if mon:
        y0, m0 = int(today[:4]), int(today[5:7])
        last = max(mon)
        ym = "%04d-%02d" % (y0, m0)
        while ym <= last:
            v = mon.get(ym, [0.0, 0.0])
            cfm.append({"month": ym, "coupons": v[0], "principal": v[1]})
            yy, mm = int(ym[:4]), int(ym[5:7])
            ym = "%04d-%02d" % (yy + (mm == 12), mm % 12 + 1)
    yld = dur = None
    if invested > 0 and agg:
        fl_ = [(d, a, 0.0) for d, a in sorted(agg.items())]
        yv = cf_ytm(invested, fl_, today)
        if yv is not None:
            yld = yv * 100.0
            dur = cf_risk(fl_, today, yv)[0]
    rows = []
    for i in range(rungs_n):
        bl = []
        for c in chosen[i]:
            if c["lots"] <= 0:
                continue
            e = c["e"]
            bl.append({"isin": e["_isin"], "name": e["name"], "rating": c["rv"], "ytm": c["ytm"], "end_date": c["end"],
                       "end_kind": c["kind"], "yield_basis": c.get("ybasis"), "ytm_mat": c.get("ytm_mat"),
                       "call_dates": c.get("call_dates") or [], "unk_date": c.get("unk_date"), "price": e["price"], "price_dirty": c["dirty"], "lots": c["lots"],
                       "cost": c["lots"] * c["dirty"], "coupon_months": c["months"], "floating": bool((e["_ci"] or {}).get("floating")),
                       "amort": bool((e["_ci"] or {}).get("amort")), "share": c["lots"] * c["dirty"] / total * 100.0})
        rows.append({"target_date": _ld_add(today, win[i][2]), "target_years": win[i][2], "window": [_ld_add(today, win[i][0]), _ld_add(today, win[i][1])],
                     "bonds": bl, "cost": sum(b["cost"] for b in bl)})
    issuers = {iss_key(c) for c in allc}
    big = max([(iss_share_ := sum(c["lots"] * c["dirty"] for c in allc if iss_key(c) == ik) / total * 100.0) for ik in issuers] or [0])
    if big > cap + 0.5:
        warnings.append("Доля крупнейшего эмитента %s %% выше лимита %s %%: не хватило разных эмитентов." %
                        (("%.1f" % big).replace(".", ","), ("%g" % cap).replace(".", ",")))
    if any(c["kind"] == "offer" for c in allc):
        notes.append("Если у выпуска есть пут-оферта, срок считается до неё: к этой дате вы предъявляете бумагу эмитенту по цене выкупа "
                     "(обычно 100 %). Заявку подаёт брокер. Доходность таких бумаг — к пут-оферте.")
    callable_ = [c for c in allc if c.get("call_dates") or c.get("unk_date")]
    if any(c.get("call_dates") for c in callable_):
        notes.append("У части выпусков есть колл-опцион: эмитент может досрочно погасить бумагу. Ступень стоит на дате погашения, "
                     "а доходность показана к худшему (меньшая из доходности к погашению и к дате колла): если выпуск погасят раньше, "
                     "деньги вернутся раньше и их придётся реинвестировать.")
    if any(c.get("unk_date") and not c.get("call_dates") for c in callable_):
        notes.append("У части выпусков есть оферта, тип которой не указан. Консервативно ступень стоит на погашении, "
                     "доходность — меньшая из доходности к дате оферты и к погашению.")
    notes.append("Бумаги гасятся по очереди: деньги возвращаются каждый год, и их можно вложить по новой ставке. Если ставки "
                 "вырастут, вы реинвестируете дороже, если упадут, длинные ступени уже зафиксировали высокую доходность.")
    if monthly:
        notes.append("Включён ровный ежемесячный доход: при выборе бумаг учитывается, в какие месяцы они платят купоны.")
    if any(b["floating"] for r_ in rows for b in r_["bonds"]):
        notes.append("Купоны флоатеров оценены по прогнозу ключевой ставки Банка России: фактические выплаты могут отличаться.")
    if any(b["rating"] == "AAA" and next((c for c in allc if c["e"]["_isin"] == b["isin"]), {}).get("e", {}).get("kind") == "ofz"
           for r_ in rows for b in r_["bonds"]):
        notes.append("ОФЗ рейтинга не имеют; для отбора приравнены к AAA как государственный долг.")
    return {"params": par, "today": today, "rungs": rows,
            "totals": {"invested": invested, "free": total - invested, "ytm": yld, "dur": dur, "bonds": len(allc),
                       "issuers": len(issuers), "rungs_filled": sum(1 for r_ in rows if r_["bonds"]),
                       "callable_cost": sum(c["lots"] * c["dirty"] for c in callable_),
                       "callable_share": sum(c["lots"] * c["dirty"] for c in callable_) / invested * 100.0 if invested > 0 else 0.0,
                       "callable_bonds": len(callable_),
                       "coupon_12m": cp12, "monthly_avg": cp12 / 12.0, "max_issuer": big,
                       "months_with_coupon": sum(1 for m in cfm[:12] if m["coupons"] > 0)},
            "cashflow_by_month": cfm, "notes": notes, "warnings": warnings}


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
