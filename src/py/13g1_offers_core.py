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
        return "Пут-оферта %s (через %d дн.): у держателя есть право предъявить бумагу к выкупу" % (ds, left)
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
    Сравнение строится только когда эмитент объявил купон на период после оферты."""
    if rec.get("kind") != "put":
        return None
    ps, pe = rec.get("period_start"), rec.get("period_end")
    window = ("с %s по %s" % (_of_dm(ps), _of_dm(pe))) if ps and pe else None
    h = {"status": rec.get("coupon_status") or "pending", "outcome": None, "gap": None, "window": window, "title": "", "text": "",
         "numbers": "", "apply": "", "risk_notes": list(rec.get("risk_notes") or []), "kb": "offers",
         "disclaimer": "Справочная информация, не инвестиционная рекомендация."}
    if rec.get("period_status") == "closed":
        h.update(status="closed", title="Период приёма заявок прошёл", text="Приём заявок завершён: бумага остаётся у держателя.")
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
        h.update(title="Доходность ниже медианы похожих выпусков на %s п. п." % _of_pct(-gap),
                 text="Цена оферты (%s %% номинала) при вложении под медианную доходность похожих выпусков даёт более высокую доходность." % _of_pct(rec["offer_price"]))
    elif code == "above":
        h.update(title="Доходность выше медианы похожих выпусков",
                 text="Доходность выше медианы похожих выпусков на %s п. п." % _of_pct(gap))
    elif code == "fair":
        h.update(title="Доходность на уровне медианы похожих выпусков", text="Доходность в пределах %s п. п. от медианы похожих выпусков." % _of_pct(OF_MARGIN))
    else:
        h.update(title="Купон объявлен", text="Сравнить с рынком не с чем: подходящих аналогов мало.")
    if rec.get("price") is not None and rec["price"] > rec["offer_price"] + OF_PRICE_EPS:
        h["text"] += " Но рыночная цена (%s %%) выше цены выкупа (%s %%): на бирже получите больше, чем по оферте." % (
            _of_pct(rec["price"]), _of_pct(rec["offer_price"]))
    return h


