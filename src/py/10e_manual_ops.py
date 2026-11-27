# ═══════════════════════════ ручной учёт сделок и сверка с отчётами брокера ═══════════════════════════
# Ручная запись — обычная операция счёта (как строка отчёта) с пометкой _manual: поэтому FIFO, доходность, налоги и графики
# работают без особых случаев. Одна «группа» записей (id вида man-<12 знаков>): сама сделка, комиссия («<id>-f») и пополнение
# под покупку («<id>-c», _manual_autocash), чтобы остаток денег не уходил в минус. Ручные записи возможны только в счетах
# с кодом imp-…: операции счетов Т-Инвестиций заново загружаются из API и перезаписываются целиком.
# Когда позже загружается отчёт брокера с этими же сделками, ручные дубли заменяются строками отчёта (reconcile_manual_with_report).

MAN_TYPES = {"buy": "BUY", "sell": "SELL", "coupon": "COUPON", "dividend": "DIVIDEND", "deposit": "INPUT",
             "withdraw": "OUTPUT", "fee": "SERVICE_FEE", "asset_ext": "ASSET_EXT"}
ASSET_EXT_KINDS = {"deposit_bank": "Банковский вклад", "cash_ext": "Наличные", "real_estate": "Недвижимость"}
MAN_TRADE, MAN_NEED_SEC = ("buy", "sell"), ("buy", "sell", "coupon", "dividend")
MAN_SIGN = {"buy": -1, "sell": 1, "coupon": 1, "dividend": 1, "deposit": 1, "withdraw": -1, "fee": -1, "asset_ext": 0}
MAN_DAYS, MAN_QTY_EPS, MAN_PAY_ABS, MAN_PAY_REL = 2, 1e-3, 5.0, 0.01
_man_lock = threading.Lock()


def sync_kick_safe():
    """Данные изменились: отправить в облако, если синхронизация включена (ошибки не мешают основной работе)."""
    try:
        fn = globals().get("sync_kick")
        if fn:
            fn()
    except Exception:  # noqa: BLE001
        pass


def sync_mark_deleted_safe(acc_id):
    """Пользователь сам удалил счёт: запомнить как явное удаление для облачной синхронизации (если она включена)."""
    try:
        fn = globals().get("sync_mark_deleted")
        cfg = load_config()
        if fn and cfg.get("sync_enabled"):
            fn(acc_id)
    except Exception:  # noqa: BLE001
        pass


# ───────────── сверка ручных сделок с отчётом ─────────────
def _man_idents(o):
    """Все известные коды бумаги операции (ISIN, тикер, uid) в верхнем регистре."""
    out = set()
    for k in ("instrumentUid", "figi", "_sec", "_ident", "_isin", "_ticker"):
        v = str(o.get(k) or "").strip().upper()
        if v.startswith("IMP:"):
            v = v[4:]
        if v:
            out.add(v)
    return out


def _man_day(o):
    try:
        return datetime.strptime((o.get("date") or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def reconcile_manual_with_report(existing, new_ops, apply=True):
    """Находит ручные сделки (_manual), уже попавшие в загружаемый отчёт: та же бумага и направление, количество (±0,001),
    дата не дальше 2 дней (Т+1, выходные), сумма отличается меньше чем на 1 % (но не меньше 5 ₽).
    Каждая строка отчёта «закрывает» не больше одной ручной записи. Совпавшие ручные записи заменяются строками отчёта;
    вместе с ними уходят их комиссия и пополнение под покупку, если в отчёте есть свои комиссии и пополнения (иначе остаются,
    чтобы остаток денег не изменился). -> (оставшиеся записи счёта, [описание заменённых]).
    apply=False — только подсчёт (для предварительного просмотра)."""
    rep = [o for o in new_ops or [] if not o.get("_opening") and not o.get("_synthetic")]
    rep_kinds = {classify(o.get("type")) for o in rep}
    used, hit = set(), {}
    for man in existing or []:
        if not man.get("_manual") or man.get("_manual_autocash") or man.get("_pair"):
            continue
        kind = classify(man.get("type"))
        if kind not in ("buy", "sell", "coupons", "dividends"):
            continue
        ids, day, qty, pay = _man_idents(man), _man_day(man), op_qty(man), abs(qf(man.get("payment")))
        if not ids or day is None:
            continue
        best = None
        for i, r in enumerate(rep):
            if i in used or classify(r.get("type")) != kind or not (ids & _man_idents(r)):
                continue
            if abs(op_qty(r) - qty) > MAN_QTY_EPS:
                continue
            rd = _man_day(r)
            if rd is None or abs((rd - day).days) > MAN_DAYS:
                continue
            if abs(abs(qf(r.get("payment"))) - pay) > max(MAN_PAY_ABS, pay * MAN_PAY_REL):
                continue
            gap = abs((rd - day).days)
            if best is None or gap < best[0]:
                best = (gap, i)
        if best:
            used.add(best[1])
            hit[man["id"]] = man
    if not hit:
        return list(existing or []), []
    drop = set(hit)
    for o in existing or []:
        pair = o.get("_pair")
        if pair in hit and ((o.get("_manual_autocash") and "deposits" in rep_kinds) or
                            (classify(o.get("type")) == "fee_broker" and "fee_broker" in rep_kinds)):
            drop.add(o.get("id"))
    info = [{"id": m["id"], "date": (m.get("date") or "")[:10], "name": m.get("name") or "", "type": classify(m.get("type")),
             "qty": op_qty(m), "amount": round(abs(qf(m.get("payment"))), 2)} for m in hit.values()]
    info.sort(key=lambda x: (x["date"], x["id"]))
    if not apply:
        return list(existing or []), info
    return [o for o in existing or [] if o.get("id") not in drop], info


def manual_matches_preview(new_ops, target, lst=None):
    """Сколько ручных сделок уже есть в загружаемом отчёте: {count, sample[]}. Проверяются счёт target или все счета."""
    lst = imports_list() if lst is None else lst
    ex = []
    for a in lst:
        if a.get("sync_src") or (target and str(target).startswith("imp-") and a["id"] != target):
            continue
        ex += [o for o in store().ops(a["id"]) if o.get("_manual")]
    if not ex:
        return {"count": 0, "sample": []}
    _kept, info = reconcile_manual_with_report(ex, new_ops, apply=False)
    return {"count": len(info), "sample": info[:5]}


# ───────────── пересчёт счёта ─────────────
def manual_recompute(client, ops):
    """Операции счёта после правки: поиск бумаг для новых записей, порядок по датам, FIFO и доходность сделок."""
    ops = [dict(o) for o in ops]
    for o in ops:
        o.pop("yield", None)
        o.pop("_yield", None)
        if str(o.get("instrumentUid") or "").startswith("imp:") and not o.get("_ident"):
            o["_ident"] = o["instrumentUid"][4:]
    if any(o.get("_ident") for o in ops):
        imp_apply_idents(client, ops)
    ops.sort(key=lambda o: (o.get("date") or "", 0 if o.get("_opening") else 1))
    fifo(ops)
    for o in ops:
        if "_yield" in o:
            o["yield"] = to_money(round(o.pop("_yield"), 9), cur_of(o["payment"]))
    return ops


def _man_check_acc(lst, acc_id):
    x = next((a for a in lst if a.get("id") == acc_id), None)
    if x is None or not str(acc_id).startswith("imp-") or x.get("sync_src") or x.get("demo") or acc_id == DEMO_ID:
        raise ApiError("Ручные записи можно добавлять только в счета из импорта и ручные счета.", 400)
    return x


def _man_num(v, name, lo=0.0, hi=1e12, req=False):
    if v is None or str(v).strip() == "":
        if req:
            raise ApiError("Заполните поле «%s»." % name, 400)
        return None
    try:
        x = float(str(v).replace(",", ".").replace(" ", "").replace(" ", ""))
    except ValueError:
        raise ApiError("Поле «%s»: нужно число." % name, 400)
    if x != x or x < lo or x > hi:
        raise ApiError("Поле «%s»: значение вне допустимых границ." % name, 400)
    return x


def manual_build(body, now=None):
    """Тело запроса -> список операций группы (сделка, комиссия, пополнение). Проверяет значения."""
    kind = str(body.get("kind") or "buy")
    if kind not in MAN_TYPES:
        raise ApiError("Неизвестный тип операции.", 400)
    mode = "position" if body.get("mode") == "position" else "op"
    try:
        day = datetime.strptime(str(body.get("date") or date.today().isoformat())[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ApiError("Дата указана неверно.", 400)
    if day > date.today() + timedelta(days=1) or day.year < 1990:
        raise ApiError("Дата вне допустимых границ.", 400)
    cur = str(body.get("currency") or "rub").lower()
    if not re.fullmatch(r"[a-z]{3}", cur):
        raise ApiError("Валюта указана неверно.", 400)
    ident = str(body.get("ident") or "").strip().upper()[:24]
    ticker = str(body.get("ticker") or "").strip().upper()[:24]
    name = str(body.get("name") or "").strip()[:120]
    gid = str(body.get("group") or "")
    if gid:
        if not re.fullmatch(r"man-[a-z0-9]{3,24}", gid):
            raise ApiError("Неверный номер записи.", 400)
    else:
        gid = "man-" + uuid.uuid4().hex[:12]
    t = (now if now is not None else time.time())
    iso = day.strftime("%Y-%m-%dT12:00:00Z")
    if kind == "asset_ext":
        ak = str(body.get("asset_kind") or "").strip()
        if ak not in ASSET_EXT_KINDS:
            raise ApiError("Неизвестный вид неторгового актива.", 400)
        amount = _man_num(body.get("amount"), "Сумма", 0.0, 1e12, req=True)
        if not amount or amount <= 0:
            raise ApiError("Укажите сумму актива.", 400)
        rate = _man_num(body.get("rate"), "Ставка", 0.0, 1000.0)
        end_raw = str(body.get("end_date") or "").strip()[:10]
        end_iso = ""
        if end_raw:
            try:
                end_d = datetime.strptime(end_raw, "%Y-%m-%d").date()
            except ValueError:
                raise ApiError("Дата окончания указана неверно.", 400)
            if end_d.year < 1990 or end_d.year > 2100:
                raise ApiError("Дата окончания вне допустимых границ.", 400)
            end_iso = end_d.isoformat()
        main = {"id": gid, "date": iso, "type": "OPERATION_TYPE_ASSET_EXT",
                "payment": to_money(0, cur), "name": name or ASSET_EXT_KINDS[ak],
                "_manual": True, "_asset_ext": True, "_asset_kind": ak, "_amount": round(amount, 2), "_u": t}
        if rate is not None:
            main["_rate"] = round(rate, 4)
        if end_iso:
            main["_end_date"] = end_iso
        return [main]
    if mode == "position":
        kind = "buy"
    if kind in MAN_NEED_SEC and not ident:
        raise ApiError("Укажите бумагу: тикер или ISIN.", 400)
    qty = _man_num(body.get("qty"), "Количество", 0.0, 1e9, req=kind in MAN_TRADE)
    if kind in MAN_TRADE and not qty:
        raise ApiError("Количество должно быть больше нуля.", 400)
    price = _man_num(body.get("price"), "Цена", 0.0, 1e9)
    amount = _man_num(body.get("amount"), "Сумма", 0.0, 1e12)
    nkd = _man_num(body.get("nkd"), "НКД", 0.0, 1e12) or 0.0
    comm = _man_num(body.get("commission"), "Комиссия", 0.0, 1e9) or 0.0
    if kind in MAN_TRADE:
        total = amount if amount else (qty * price + nkd if price else None)
    else:
        total = amount
    if not total or total <= 0:
        raise ApiError("Укажите цену или сумму операции.", 400)
    total = round(total, 2)
    main = {"id": gid, "date": iso, "type": "OPERATION_TYPE_" + MAN_TYPES[kind],
            "payment": to_money(MAN_SIGN[kind] * total, cur), "name": name or ident or ticker or "Ручная запись",
            "_manual": True, "_u": t}
    if ident:
        main["_ident"] = ident
    if ticker and ticker != ident:
        main["_ticker"] = ticker
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", ident):
        main["_isin"] = ident
    if mode == "position":
        main["_position"] = True
    if qty:
        main["quantity"] = main["quantityDone"] = str(int(qty)) if qty == int(qty) else repr(round(qty, 9))
        main["price"] = to_money(round(total / qty, 9) if kind in MAN_TRADE else (price or 0), cur)
    out = [main]
    if comm and kind in MAN_TRADE:
        out.append({"id": gid + "-f", "date": iso, "type": "OPERATION_TYPE_BROKER_FEE", "payment": to_money(-round(comm, 2), cur),
                    "name": "Комиссия: " + main["name"], "_manual": True, "_pair": gid, "_u": t,
                    **({"_ident": ident} if ident else {})})
    if kind == "buy" and body.get("autocash", True):
        out.append({"id": gid + "-c", "date": iso, "type": "OPERATION_TYPE_INPUT", "payment": to_money(round(total + comm, 2), cur),
                    "name": "Пополнение под покупку", "_manual": True, "_manual_autocash": True, "_pair": gid, "_u": t})
    return out


def _man_group(o):
    i = str(o.get("id") or "")
    return i[:-2] if i.endswith(("-f", "-c")) and o.get("_pair") else i


def manual_post(cfg, body):
    act = str(body.get("action") or "save")
    st = store()
    with _man_lock:
        lst = imports_list()
        if act == "delete":
            acc_id, gid = str(body.get("acc") or ""), str(body.get("group") or "")
            _man_check_acc(lst, acc_id)
            ops = st.ops(acc_id)
            keep = [o for o in ops if not (o.get("_manual") and _man_group(o) == gid)]
            if len(keep) == len(ops):
                raise ApiError("Запись не найдена.", 404)
            _man_store(cfg, lst, acc_id, keep)
            return {"ok": True, "removed": len(ops) - len(keep)}
        acc_id = str(body.get("acc") or "")
        if not acc_id:
            nm = str(body.get("acc_name") or "").strip()[:80]
            if not nm:
                raise ApiError("Выберите счёт или назовите новый ручной счёт.", 400)
            demo_remove()
            acc_id = "imp-" + uuid.uuid4().hex[:10]
            lst.append({"id": acc_id, "name": nm, "broker": "Ручной учёт", "created": utc_now_str(), "files": [], "manual": True,
                        "broker_id": broker_detect_import("", b"", "", str(body.get("broker") or ""), nm)})
        _man_check_acc(lst, acc_id)
        new = manual_build(body)
        gid = new[0]["id"]
        ops = [o for o in st.ops(acc_id) if not (o.get("_manual") and _man_group(o) == gid)]
        if str(body.get("group") or "") and len(ops) == len(st.ops(acc_id)):
            raise ApiError("Запись для правки не найдена.", 404)
        _man_store(cfg, lst, acc_id, ops + new)
        return {"ok": True, "acc": acc_id, "group": gid}


def _man_store(cfg, lst, acc_id, ops):
    ops = manual_recompute(TInvest(cfg), ops)
    st = store()
    st.ops_clear(acc_id)
    st.ops_put(acc_id, ops)
    for a in lst:
        if a["id"] == acc_id:
            a["ops"] = len(ops)
    st.put("imports", lst)
    mem_clear()
    sync_kick_safe()


def manual_list(cfg, acc, q, force):
    """Ручные записи счёта: группы (сделка + комиссия + пополнение) для таблицы правки."""
    acc_id = str((q or {}).get("acc") or "")
    lst = imports_list()
    out = []
    for a in lst:
        if acc_id and a["id"] != acc_id:
            continue
        if a.get("sync_src") or a.get("demo") or a["id"] == DEMO_ID:
            continue
        groups = {}
        for o in store().ops(a["id"]):
            if o.get("_manual"):
                groups.setdefault(_man_group(o), []).append(o)
        for gid, g in groups.items():
            m = next((o for o in g if o["id"] == gid), None)
            if not m:
                continue
            fee = next((o for o in g if o["id"].endswith("-f")), None)
            is_ext = bool(m.get("_asset_ext"))
            row = {"acc": a["id"], "acc_name": a.get("name"), "group": gid, "date": (m.get("date") or "")[:10],
                   "type": "asset_ext" if is_ext else classify(m.get("type")),
                   "name": m.get("name") or "", "ident": m.get("_sec") or m.get("_isin") or "",
                   "qty": op_qty(m),
                   "amount": round(float(m.get("_amount") or 0), 2) if is_ext else round(abs(qf(m.get("payment"))), 2),
                   "currency": cur_of(m.get("payment")).upper(),
                   "commission": round(abs(qf(fee.get("payment"))), 2) if fee else 0.0,
                   "autocash": any(o.get("_manual_autocash") for o in g), "position": bool(m.get("_position"))}
            if is_ext:
                row["asset_kind"] = m.get("_asset_kind") or ""
                if m.get("_rate") is not None:
                    row["rate"] = m.get("_rate")
                if m.get("_end_date"):
                    row["end_date"] = m.get("_end_date")
            out.append(row)
    out.sort(key=lambda r: (r["date"], r["group"]), reverse=True)
    return {"rows": out[:500], "accounts": [{"id": a["id"], "name": a.get("name")} for a in lst
                                           if str(a["id"]).startswith("imp-") and not (a.get("sync_src") or a.get("demo") or a["id"] == DEMO_ID)]}


def manual_search(cfg, acc, q, force):
    """Поиск бумаги для ручной записи: тикер, ISIN или название (облигации, акции, фонды). Цена — по рынку."""
    s = str((q or {}).get("q") or "").strip().lower()
    if len(s) < 2:
        return {"rows": []}
    out = []

    def ok(*vals):
        return any(s in str(v or "").lower() for v in vals)
    try:
        for r in screener_rows():
            if ok(r.get("name"), r.get("isin"), r.get("id"), r.get("full")):
                out.append({"ident": r.get("isin") or r["id"], "ticker": r["id"], "name": r.get("name") or r["id"], "kind": "bond",
                            "price": r.get("price"), "price_pct": True, "nominal": r.get("nominal"), "nkd": r.get("nkd"),
                            "currency": (r.get("cur") or "RUB").lower(), "turn": r.get("turn") or 0})
    except Exception:  # noqa: BLE001
        pass
    try:
        for r in list(stocks_universe()) + list(funds_universe()):
            if ok(r.get("secid"), r.get("isin"), r.get("name"), r.get("shortname")):
                out.append({"ident": r.get("isin") or r["secid"], "ticker": r["secid"], "name": r.get("shortname") or r.get("name"),
                            "kind": "fund" if r.get("is_fund") else "share", "price": r.get("price"), "price_pct": False,
                            "currency": "rub", "turn": r.get("value_today") or 0})
    except Exception:  # noqa: BLE001
        pass
    out.sort(key=lambda x: (not str(x["name"]).lower().startswith(s) and not x["ticker"].lower().startswith(s), -(x["turn"] or 0)))
    return {"rows": out[:12]}


API_POST["/api/ops/manual"] = manual_post
API_POST["/api/ops/manual/delete"] = lambda cfg, body: manual_post(cfg, dict(body, action="delete"))
API_GET["/api/ops/manual"] = manual_list
API_GET["/api/ops/manual/search"] = manual_search
