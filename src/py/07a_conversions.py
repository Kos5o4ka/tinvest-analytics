# ═══════════════════════════════ обмены бумаг (конвертации, редомициляция) ═══════════════════════════════
# В операциях API нет записей об обмене ГДР/АДР на акции российской компании: старая бумага «висит» в позиции навсегда,
# а новая продаётся без покупки. Здесь такие обмены находятся (по таблице известных и автоматически) и превращаются
# в служебные операции X_CONV_OUT / X_CONV_IN, которые учитывают история стоимости, налоги и FIFO.

# Каждая запись проверена по данным Мосбиржи (ISS): коды, ISIN, даты начала торгов новой бумаги и непрерывность цены
# старой и новой бумаги в день обмена (цены совпадают -> обмен 1:1). Записи, где коэффициент подтвердить не удалось
# (Русагро, FixPrice, Глобалтранс, Ozon, МД Медикал, Лента), не включены; часть из них ловит автоопределение.
SEC_CONVERSIONS = [
    {"old_tickers": ["US87238U2033"], "old_isins": ["US87238U2033"], "new_ticker": "T", "new_isin": "RU000A107UL4",
     "ratio": 1, "date": "2024-03-18", "label": "ГДР TCS Group на акции Т-Технологии"},
    {"old_tickers": ["YNDX"], "old_isins": ["NL0009805522"], "new_ticker": "YDEX", "new_isin": "RU000A107T19",
     "ratio": 1, "date": "2024-07-24", "label": "Yandex N.V. на акции МКПАО Яндекс"},
    {"old_tickers": ["FIVE"], "old_isins": ["US98387E2054"], "new_ticker": "X5", "new_isin": "RU000A108X38",
     "ratio": 1, "date": "2025-01-09", "label": "ГДР X5 Retail Group на акции ИКС 5"},
    {"old_tickers": ["HHRU"], "old_isins": ["US42207L1061"], "new_ticker": "HEAD", "new_isin": "RU000A107662",
     "ratio": 1, "date": "2024-09-26", "label": "АДР HeadHunter на акции МКПАО Хэдхантер"},
    {"old_tickers": ["CIAN"], "old_isins": ["US83418T1088"], "new_ticker": "CNRU", "new_isin": "RU000A10ANA1",
     "ratio": 1, "date": "2025-04-03", "label": "АДР Cian на акции МКПАО Циан"},
    {"old_tickers": [], "old_isins": ["US29760G1031"], "new_ticker": "ETLN", "new_isin": "RU000A10C1L6",
     "ratio": 1, "date": "2025-09-08", "label": "ГДР Etalon Group на акции МКПАО Эталон Груп"},
    {"old_tickers": ["MAIL"], "old_isins": ["US5603172082"], "new_ticker": "VKCO", "new_isin": "RU000A106YF0",
     "ratio": 1, "date": "2023-10-20", "label": "ГДР Mail.ru Group на акции ПАО ВК"},
]

CONV_SKIP_TYPES = ("currency", "bond", "futures", "option", "dfa", "cfa")
CONV_REFLECT_DAYS = 120


def _cv_day(s):
    return (s or "")[:10]


def _cv_add_day(iso, n):
    return (datetime.strptime(iso, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def _cv_gap(a, b):
    return abs((datetime.strptime(a, "%Y-%m-%d") - datetime.strptime(b, "%Y-%m-%d")).days)


def _cv_positions(ops, names):
    """{(счёт, ключ позиции): данные} по сделкам и переводам бумаг."""
    pos = {}
    for o in ops:
        k = classify(o.get("type"))
        sign = 1 if k in ("buy", "sec_in") else -1 if k in ("sell", "sec_out") else 0
        key = pos_key(o)
        q = op_qty(o)
        if not sign or not key or not q or str(o.get("instrumentUid") or "").startswith("imp:"):
            continue
        acc = o.get("_acc") or ""
        p = pos.setdefault((acc, key), {"acc": acc, "key": key, "ops": [], "tickers": set(), "isins": set(), "uids": {}, "pos": None,
                                        "figi": None, "itype": "", "kind": None})
        p["ops"].append((o.get("date") or "", _cv_day(o.get("date")), sign * q, k))
        if o.get("ticker"):
            p["tickers"].add(o["ticker"])
        uid = o.get("instrumentUid") or o.get("figi")
        if uid:
            p["uids"][uid] = p["uids"].get(uid, 0) + 1
            info = (names or {}).get(uid) or {}
            if info.get("isin"):
                p["isins"].add(info["isin"])
            if info.get("ticker"):
                p["tickers"].add(info["ticker"])
            if info.get("type") and not p["itype"]:
                p["itype"] = info["type"]
        p["pos"] = p["pos"] or o.get("positionUid")
        p["figi"] = p["figi"] or o.get("figi")
        p["kind"] = p["kind"] or o.get("instrumentKind")
        if not p["itype"]:
            p["itype"] = {"bonds": "bond", "shares": "share"}.get(o.get("instrumentType") or "", o.get("instrumentType") or "") \
                or TYPE_FROM_KIND.get(o.get("instrumentKind") or "", "")
    for p in pos.values():
        p["ops"].sort(key=lambda x: x[0])
        p["net"] = sum(x[2] for x in p["ops"])
        run, mn, neg = 0, 0, None
        for dt, day, q, _ in p["ops"]:
            run += q
            if run < mn:
                mn = run
            if run < 0 and neg is None:
                neg = day
        p["neg_day"], p["depth"] = neg, -mn
        p["first_day"], p["last_day"] = p["ops"][0][1], p["ops"][-1][1]
        p["uid"] = max(p["uids"], key=lambda u: p["uids"][u]) if p["uids"] else None
        p["ticker"] = next(iter(sorted(p["tickers"], key=lambda t: (len(t) > 8, t))), "")
    return pos


def _cv_held(p, held):
    if held is None:
        return None
    ids = set(p["uids"]) | {p["key"], p["pos"], p["figi"]}
    vals = [held[i] for i in ids if i and i in held]
    return max(vals) if vals else 0.0


def _cv_is_old(p, e):
    if e["new_isin"] in p["isins"]:
        return False
    return bool(p["isins"] & set(e["old_isins"])) or bool(p["tickers"] & set(e["old_tickers"]))


def _cv_is_new(p, e):
    if e["new_isin"] in p["isins"]:
        return True
    return e["new_ticker"] in p["tickers"] and not (p["isins"] & set(e["old_isins"]))


def _cv_event(acc, date, old, new, old_qty, new_qty, ratio, label, source, new_ticker=None, new_uid=None):
    n = new or {}
    return {"acc": acc, "date": date, "old_key": old["key"], "new_key": n.get("key") or new_uid, "old_qty": old_qty,
            "new_qty": new_qty, "ratio": ratio, "label": label, "source": source,
            "new_uid": n.get("uid") or new_uid, "new_ticker": new_ticker or n.get("ticker") or "",
            "old_ticker": old["ticker"], "old_uid": old["uid"], "old_uids": list(old["uids"]), "old_pos": old["pos"],
            "old_figi": old["figi"], "new_pos": n.get("pos") or new_uid, "new_figi": n.get("figi"),
            "old_kind": old["kind"], "old_type": old["itype"]}


def find_conversions(ops, names, held=None, last_close_day=None, resolve=None):
    """Обмены бумаг по счетам. held — {ключ/uid: кол-во} текущих позиций (если известны), last_close_day — {ключ: дата
    последней свечи}, resolve(ticker) -> uid новой бумаги, которой нет в операциях счёта (иначе такой обмен пропускается)."""
    pos = _cv_positions(ops, names)
    by_acc = defaultdict(list)
    for p in pos.values():
        if p["itype"] not in CONV_SKIP_TYPES:
            by_acc[p["acc"]].append(p)
    events, used = [], set()
    lcd = last_close_day or {}
    for acc, plist in by_acc.items():
        for e in SEC_CONVERSIONS:
            olds = [p for p in plist if _cv_is_old(p, e)]
            news = [p for p in plist if _cv_is_new(p, e)]
            new = max(news, key=lambda p: len(p["ops"])) if news else None
            for old in olds:
                used.add((acc, old["key"]))
                if new:
                    used.add((acc, new["key"]))
                lo = _cv_add_day(old["last_day"], 1)
                if lcd.get(old["key"]):
                    lo = max(lo, _cv_add_day(lcd[old["key"]][:10], 1))
                hi = new["neg_day"] if new and new["neg_day"] else None
                if hi is None:
                    date = max(e["date"], lo)
                else:
                    date = min(max(e["date"], lo), hi) if hi >= lo else lo
                old_qty = sum(x[2] for x in old["ops"] if x[1] < date)
                if old_qty <= 0:
                    continue
                new_qty = int(round(old_qty * e["ratio"]))
                # брокер уже отразил обмен переводом бумаг — повторно не добавляем
                if any(x[3] == "sec_out" and _cv_gap(x[1], date) <= CONV_REFLECT_DAYS for x in old["ops"]):
                    continue
                out_total = sum(-x[2] for x in old["ops"] if x[3] == "sec_out")
                if new and any(x[3] == "sec_in" and _cv_gap(x[1], date) <= CONV_REFLECT_DAYS and x[2] in (new_qty, int(round((old_qty + out_total) * e["ratio"])))
                               for x in new["ops"]):
                    continue
                ho = _cv_held(old, held)
                if ho is not None and ho > 0.5 and ho >= old_qty - 0.5:
                    continue                      # старая бумага всё ещё в портфеле — обмена не было
                new_uid = None
                if not new:
                    new_uid = resolve(e["new_ticker"]) if resolve else None
                    if not new_uid:
                        continue
                events.append(_cv_event(acc, date, old, new, old_qty, new_qty, e["ratio"], e["label"], "table", e["new_ticker"], new_uid))
    # автоопределение: остаток старой бумаги и продажа новой без покупок ровно на этот остаток (коэффициент 1)
    for acc, plist in by_acc.items():
        shares = [p for p in plist if p["itype"] in ("share", "") and (acc, p["key"]) not in used]
        olds = [p for p in shares if p["net"] > 0 and not (_cv_held(p, held) or 0) > 0.5]
        news = [p for p in shares if p["neg_day"]]
        cand = {}
        for o in olds:
            cand[o["key"]] = [n for n in news if n["key"] != o["key"] and n["depth"] == o["net"] and n["neg_day"] > o["last_day"]]
        for o in olds:
            c = cand[o["key"]]
            if len(c) != 1 or sum(1 for k, v in cand.items() if c[0] in v) != 1:
                continue
            n = c[0]
            date = n["neg_day"]
            events.append(_cv_event(acc, date, o, n, o["net"], o["net"], 1, "Обмен бумаг (определён автоматически, предположение)", "auto"))
    # ограничение по текущим позициям: новая бумага не должна «вырасти» сверх фактического остатка
    if held is not None:
        groups = defaultdict(list)
        for ev in events:
            groups[ev["new_key"]].append(ev)
        for nk, evs in groups.items():
            base = sum(p["net"] for p in pos.values() if p["key"] == nk)
            ref = next((p for p in pos.values() if p["key"] == nk), None)
            h = _cv_held(ref, held) if ref else held.get(nk, held.get(evs[0]["new_uid"], 0.0))
            add = sum(ev["new_qty"] for ev in evs)
            if base <= h + 0.5 and base + add > h + 0.5:
                allow = max(0.0, h - base)
                for ev in sorted(evs, key=lambda x: x["date"]):
                    t = min(ev["new_qty"], int(allow))
                    allow -= t
                    ev["new_qty"] = t
        events = [ev for ev in events if ev["new_qty"] > 0]
    return sorted(events, key=lambda x: (x["date"], x["acc"], str(x["old_key"])))


def apply_conversions(ops, events):
    """Новый отсортированный список операций с вставленными служебными X_CONV_OUT / X_CONV_IN."""
    out = list(ops)
    zero = {"currency": "rub", "units": "0", "nano": 0}
    for ev in events:
        meta = {"from_key": ev["old_key"], "to_key": ev["new_key"], "ratio": ev["ratio"], "label": ev["label"], "source": ev["source"],
                "old_uids": ev.get("old_uids") or [], "new_uid": ev.get("new_uid"), "old_qty": ev["old_qty"], "new_qty": ev["new_qty"],
                "old_ticker": ev.get("old_ticker"), "new_ticker": ev.get("new_ticker")}
        base = {"date": ev["date"] + "T00:00:01Z", "state": "OPERATION_STATE_EXECUTED", "payment": dict(zero), "_acc": ev["acc"],
                "_conv": meta, "instrumentKind": ev.get("old_kind") or "INSTRUMENT_TYPE_SHARE", "instrumentType": ev.get("old_type") or "share"}
        cid = "conv:%s:%s:%s" % (ev["acc"], ev["old_key"], ev["date"])
        a = dict(base, id=cid + ":out", type="OPERATION_TYPE_X_CONV_OUT", quantity=str(ev["old_qty"]), quantityDone=str(ev["old_qty"]),
                 instrumentUid=ev.get("old_uid"), positionUid=ev.get("old_pos"), figi=ev.get("old_figi"), ticker=ev.get("old_ticker"))
        b = dict(base, id=cid + ":in", type="OPERATION_TYPE_X_CONV_IN", quantity=str(ev["new_qty"]), quantityDone=str(ev["new_qty"]),
                 instrumentUid=ev.get("new_uid"), positionUid=ev.get("new_pos"), figi=ev.get("new_figi"), ticker=ev.get("new_ticker"))
        out += [a, b]
    out.sort(key=lambda o: o.get("date") or "")
    return out


def conversions_view(events):
    """Список обменов для интерфейса."""
    return [{"date": e["date"], "label": e["label"], "old": e.get("old_ticker") or "", "new": e.get("new_ticker") or "",
             "qty": e["old_qty"], "new_qty": e["new_qty"], "source": e["source"]} for e in events]
