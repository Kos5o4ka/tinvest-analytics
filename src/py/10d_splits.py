# ═══════════════════════════════ сплиты в импорте отчётов ═══════════════════════════════
# В отчётах брокеров количество бумаг после сплита/консолидации «появляется без сделки» (3.1 на начало периода — до сплита,
# на конец — после). Список сплитов берём у Мосбиржи (ISS statistics/engines/stock/splits), сопоставляем бумагу по ISIN
# (secid в списке бывает тикером или самим ISIN) и:
#   1) при разборе отчёта количество на день сплита умножается на after/before, поэтому «движения без сделки» не возникает;
#   2) при слиянии файлов (finalize_import) в счёт вставляется пара служебных операций X_CONV_OUT / X_CONV_IN (как в 07a_conversions),
#      которая переносит лоты FIFO в новое количество и сохраняет стоимость и срок владения. Пара идемпотентна по id.
# Нет сети — работаем как раньше, без сплитов.

SPLITS_URL = "https://iss.moex.com/iss/statistics/engines/stock/splits.json?iss.meta=off"
SECURITY_URL = "https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description"


def moex_splits_list():
    """[{date, secid, before, after}] из ISS (кэш на сутки). При ошибке сети — [] (пустой результат не кэшируется)."""
    st = store()
    v = st.get("moex:splits", ttl=DAY)
    if v is not None:
        return v
    try:
        data = json.loads(http_text(SPLITS_URL))["splits"]
        cols = data["columns"]
        rows = []
        for r in data["data"]:
            d = dict(zip(cols, r))
            if d.get("tradedate") and d.get("secid") and d.get("before") and d.get("after"):
                rows.append({"date": str(d["tradedate"])[:10], "secid": str(d["secid"]), "before": float(d["before"]),
                             "after": float(d["after"])})
    except Exception:  # noqa: BLE001 — нет сети/сбой источника: импорт идёт без сплитов
        return []
    st.put("moex:splits", rows)
    return rows


def moex_secid_isin(secid):
    """ISIN по коду бумаги Мосбиржи (кэш на месяц); пустая строка, если узнать не удалось."""
    st = store()
    v = st.get("moex:secisin:" + secid, ttl=30 * DAY)
    if v is not None:
        return v
    try:
        data = json.loads(http_text(SECURITY_URL % urllib.parse.quote(secid)))["description"]
        cols = data["columns"]
        isin = ""
        for r in data["data"]:
            d = dict(zip(cols, r))
            if d.get("name") == "ISIN":
                isin = str(d.get("value") or "")
    except Exception:  # noqa: BLE001
        return ""
    st.put("moex:secisin:" + secid, isin)
    return isin


def splits_by_isin(d_from, d_to, wanted, secid_isin=None):
    """{ключ бумаги: [(дата 'ГГГГ-ММ-ДД', коэффициент after/before)]} для сплитов в [d_from; d_to] (строки дат) по нужным бумагам
    wanted (ISIN или тикеры, как они записаны в операциях). secid_isin — известные соответствия «код -> ISIN» из самого отчёта."""
    wanted = set(w for w in wanted if w)
    if not wanted:
        return {}
    rows = [r for r in moex_splits_list() if d_from <= r["date"] <= d_to and r["before"] and r["before"] != r["after"]]
    known = dict(secid_isin or {})
    need = sorted({r["secid"] for r in rows if r["secid"] not in wanted and r["secid"] not in known and not ISIN_RE.match(r["secid"])})
    for sid, isin in pool_map(lambda x: (x, moex_secid_isin(x)), need, workers=4):
        known[sid] = isin
    out = {}
    for r in rows:
        sid = r["secid"]
        key = sid if sid in wanted else known.get(sid)
        if key in wanted:
            out.setdefault(key, []).append((r["date"], r["after"] / r["before"]))
    return {k: sorted(v) for k, v in out.items()}


def split_label(before, after):
    f = lambda x: str(int(x)) if x == int(x) else str(x)
    return "Сплит %s:%s (Мосбиржа)" % (f(before), f(after)) if after >= before else "Консолидация %s:%s (Мосбиржа)" % (f(before), f(after))


def import_apply_splits(ops, until=None):
    """Вставляет в операции счёта пары X_CONV_OUT / X_CONV_IN на дни сплитов по всей истории (после слияния файлов).
    Ранее вставленные пары (id split:…) пересчитываются заново; бумаги, которых на день сплита не было, пропускаются."""
    ops = [o for o in ops if not str(o.get("id") or "").startswith("split:")]
    dates = sorted(o["date"][:10] for o in ops if o.get("date"))
    if not dates:
        return ops
    by_sec = defaultdict(list)
    for o in ops:
        if o.get("_sec") and classify(o["type"]) in ("buy", "sell", "sec_in", "sec_out", "repayments"):
            by_sec[o["_sec"]].append(o)
    # конец диапазона — сегодня: бумага могла остаться в портфеле, а сплит случиться уже после последней операции
    sp = splits_by_isin(dates[0], until or max(dates[-1], datetime.now(timezone.utc).strftime("%Y-%m-%d")), by_sec)
    zero = to_money(0, "rub")
    for sec, evs in sp.items():
        rows = sorted(by_sec[sec], key=lambda o: o["date"])
        for idx, (day, ratio) in enumerate(evs):
            qty, ei = 0.0, 0
            for o in rows:
                d = o["date"][:10]
                if d >= day:
                    break
                while ei < idx and evs[ei][0] <= d:   # предыдущие сплиты этой бумаги уже сработали
                    qty *= evs[ei][1]
                    ei += 1
                k, q = classify(o["type"]), op_qty(o)
                if k in ("buy", "sec_in"):
                    qty += q
                elif k in ("sell", "sec_out"):
                    qty -= q
                elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL":
                    qty = 0.0
            while ei < idx:
                qty *= evs[ei][1]
                ei += 1
            if qty <= 1e-6:
                continue
            new_q = qty * ratio
            new_q = int(round(new_q)) if abs(new_q - round(new_q)) < 1e-6 else round(new_q, 6)
            sample = max(rows, key=lambda o: o["date"])
            uid = sample.get("instrumentUid") or sample.get("figi")
            before, after = (1, ratio) if ratio >= 1 else (round(1 / ratio), 1)
            cv = {"from_key": uid, "to_key": uid, "ratio": ratio, "label": split_label(before, after), "source": "moex_split",
                  "old_uids": [uid], "new_uid": uid, "old_qty": qty, "new_qty": new_q}
            base = {"date": day + "T00:00:01Z", "state": "OPERATION_STATE_EXECUTED", "payment": dict(zero), "_conv": cv, "_sec": sec,
                    "name": sample.get("name") or sec, "instrumentUid": sample.get("instrumentUid"), "figi": sample.get("figi"),
                    "instrumentKind": sample.get("instrumentKind") or "INSTRUMENT_TYPE_SHARE"}
            cid = "split:%s:%s" % (sec, day)
            qs = lambda x: str(int(x)) if x == int(x) else repr(x)
            # «in» на секунду позже «out»: хранилище отдаёт операции по (дата, ключ), а ':in' < ':out' по алфавиту
            ops.append(dict(base, id=cid + ":out", type="OPERATION_TYPE_X_CONV_OUT", quantity=qs(qty), quantityDone=qs(qty)))
            ops.append(dict(base, id=cid + ":in", date=day + "T00:00:02Z", type="OPERATION_TYPE_X_CONV_IN",
                            quantity=qs(new_q), quantityDone=qs(new_q)))
    ops.sort(key=lambda o: (o["date"], 0 if o.get("_opening") else 1))
    return ops


def split_walk(run, events, splits):
    """Количество на конец периода: стартовое run, сделки events [(время, ±кол-во, …)], в дни сплитов количество умножается."""
    items = sorted([(x[0], 1, x[1]) for x in events] + [(datetime.strptime(d, "%Y-%m-%d"), 0, r) for d, r in splits],
                   key=lambda z: (z[0], z[1]))
    for _t, kind, v in items:
        run = run * v if kind == 0 else run + v
    return run


def split_timeline(events, splits):
    """Сделки (время, ±кол-во, цена) вперемешку с маркерами сплитов (время, None, коэффициент) в хронологическом порядке."""
    return sorted(list(events) + [(datetime.strptime(d, "%Y-%m-%d"), None, r) for d, r in splits],
                  key=lambda z: (z[0], 0 if z[1] is None else 1))
