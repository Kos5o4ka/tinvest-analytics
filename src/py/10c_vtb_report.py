# ═══════════════════════════════ отчёт брокера ВТБ (xlsx) ═══════════════════════════════
#
# «Отчет Банка ВТБ (ПАО) за период … о сделках, операциях и состоянии счетов Клиента». Разбор по той же схеме, что у отчёта
# Т-Инвестиций (10b_tbank_report.py): свои парсер и сверка, общие finalize_import / слияние файлов в один счёт.
#   «Заключенные…» и «Завершенные…» сделки    -> BUY / SELL, объединяются и дедуплицируются по «№ сделки»
#                                                 (сделка, заключённая в конце периода, завершится уже в следующем файле)
#   «Движение денежных средств»                -> пополнения/выводы, купоны, дивиденды, погашения, налоги, вознаграждение брокера;
#                                                 «Сальдо расчетов по сделкам» — зеркало сделок, пропускается
#   «Отчёт об остатках ценных бумаг»           -> входящий остаток = служебная операция на начало периода (_opening)
#   «Движение ценных бумаг»                    -> «Расчеты по заключенным сделкам» — зеркало сделок; остальное — движение без сделки
# Комиссии берутся из денежного движения («Вознаграждение брокера»), а не из колонок сделок: это те же деньги, дважды не считаем.
# Деньги и бумаги сверяются с «Плановым исходящим остатком»: он включает сделки, заключённые, но ещё не рассчитанные.
# Ячейки с датой/суммой ридер xlsx отдаёт как «@xl<число>»: parse_date/parse_num понимают оба вида.

VT_TITLES = (("summary", "сводная информация по субсчету"), ("cashbal", "отчет об остатках денежных средств"),
             ("cash", "движение денежных средств"), ("secbal", "отчет об остатках ценных бумаг"),
             ("secmov", "движение ценных бумаг"), ("deals", "заключенные в отчетном периоде сделки"),
             ("done", "завершенные в отчетном периоде сделки"))
VT_ISIN_RE = re.compile(r"^(.*?),\s*[^,]*,\s*([A-Z]{2}[A-Z0-9]{9}\d)\s*$")


def vt_norm(s):
    return tb_norm(s).replace("ё", "е")


def vt_detect(tables):
    """Таблица отчёта Банка ВТБ (ПАО) о сделках, операциях и состоянии счетов Клиента или None."""
    for t in tables[:3]:
        head = " ".join(vt_norm(c) for r in t[:6] for c in r if str(c).strip())
        if "отчет банка втб" in head and "за период" in head:
            return t
    return None


def vt_sections(rows):
    """{'cash': [...], 'deals': [...]} — строки между заголовками разделов (заголовок — единственная ячейка строки)."""
    out, cur = {}, None
    for r in rows:
        nz = [str(c).strip() for c in r if str(c).strip()]
        if len(nz) == 1:
            low = vt_norm(nz[0])
            hit = next((k for k, p in VT_TITLES if low.startswith(p)), None)
            if hit:
                cur = hit
                out.setdefault(cur, [])
                continue
        if cur is not None:
            out[cur].append(r)
    return out


def vt_period(rows):
    for r in rows[:6]:
        for c in r:
            m = re.search(r"за период с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})", str(c))
            if m:
                return parse_date(m.group(1)), parse_date(m.group(2))
    return None, None


def vt_cols(row, *need):
    """Карта {заголовок: колонка}, если в строке есть заголовки, начинающиеся на все need (иначе None)."""
    cm = {}
    for i, c in enumerate(row):
        k = vt_norm(c)
        if k and k not in cm:
            cm[k] = i
    return cm if all(any(k.startswith(n) for k in cm) for n in need) else None


def vt_cell(row, cm, prefix, exact=False):
    for k, i in cm.items():
        if k == prefix if exact else k.startswith(prefix):
            return str(row[i]).strip() if i < len(row) and row[i] is not None else ""
    return ""


def vt_isin(cell):
    """«Наименование, № гос. регистрации, ISIN» -> (название, ISIN)."""
    m = VT_ISIN_RE.match(str(cell or "").strip())
    if m:
        return m.group(1).strip(), m.group(2)
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", str(cell or ""))
    return (str(cell or "").split(",")[0].strip(), m.group(1) if m else "")


def vt_balances(rows):
    """«Отчёт об остатках денежных средств» -> {cur: (входящий, исходящий, плановый)} по колонкам «Итого»."""
    out, head, itogo = {}, None, []
    for r in rows:
        h = vt_cols(r, "валюта", "входящий остаток", "исходящий остаток")
        if h:
            head = h
            continue
        if head and not itogo and any(vt_norm(c) == "итого" for c in r):
            itogo = [i for i, c in enumerate(r) if vt_norm(c) == "итого"]
            continue
        cur = str(r[1]).strip() if len(r) > 1 else ""
        if head and itogo and re.fullmatch(r"[A-Z]{3}", cur) and len(itogo) >= 2:
            plan_i = next((i for k, i in head.items() if k.startswith("плановый")), None)
            v = lambda i: tb_num(r[i]) if i is not None and i < len(r) else 0.0
            out[norm_cur(cur)] = (v(itogo[0]), v(itogo[1]), v(plan_i) if plan_i is not None else v(itogo[1]))
    return out


def vt_cash(rows):
    """«Движение денежных средств» -> список строк {d, amount, cur, op, note}."""
    out, cm = [], None
    for r in rows:
        h = vt_cols(r, "дата", "сумма", "валюта", "тип операции")
        if h:
            cm = h
            continue
        if not cm:
            continue
        op, d = vt_cell(r, cm, "тип операции"), parse_date(vt_cell(r, cm, "дата"))
        if not op or not d:
            continue
        out.append({"d": d, "amount": tb_num(vt_cell(r, cm, "сумма")), "cur": norm_cur(vt_cell(r, cm, "валюта")), "op": op,
                    "note": vt_cell(r, cm, "комментарий")})
    return out


def vt_deals(rows):
    out, cm = [], None
    for r in rows:
        h = vt_cols(r, "наименование ценной бумаги", "дата и время заключения", "вид сделки", "количество")
        if h:
            cm = h
            continue
        if not cm:
            continue
        name, isin = vt_isin(vt_cell(r, cm, "наименование ценной бумаги"))
        kind, dt = vt_cell(r, cm, "вид сделки"), parse_date(vt_cell(r, cm, "дата и время заключения"))
        num = vt_cell(r, cm, "№ сделки", exact=True)
        if not (isin and kind and dt and num):
            continue
        out.append({"num": num, "kind": kind, "dt": dt, "name": name, "isin": isin, "qty": abs(tb_num(vt_cell(r, cm, "количество"))),
                    "total": abs(tb_num(vt_cell(r, cm, "сумма сделки"))), "nkd": abs(tb_num(vt_cell(r, cm, "нкд по сделке"))),
                    "cur": norm_cur(vt_cell(r, cm, "валюта расчетов")), "repo": "репо" in vt_norm(kind)
                    or bool(vt_cell(r, cm, "ставка репо").strip("0.-, "))})
    return out


def vt_secbal(rows):
    """«Отчёт об остатках ценных бумаг» -> {isin: {name, open, close, plan}}."""
    out, cm = {}, None
    for r in rows:
        h = vt_cols(r, "наименование ценной бумаги", "входящий остаток", "исходящий остаток")
        if h:
            cm = h
            continue
        if not cm:
            continue
        name, isin = vt_isin(vt_cell(r, cm, "наименование ценной бумаги"))
        if not isin:
            continue
        p = out.setdefault(isin, {"name": name, "open": 0.0, "close": 0.0, "plan": 0.0})
        p["open"] += tb_num(vt_cell(r, cm, "входящий остаток"))
        p["close"] += tb_num(vt_cell(r, cm, "исходящий остаток"))
        p["plan"] += tb_num(vt_cell(r, cm, "плановый исходящий остаток"))
    return out


def vt_secmov(rows):
    out, cm = [], None
    for r in rows:
        h = vt_cols(r, "наименование ценной бумаги", "дата операции", "количество", "тип операции")
        if h:
            cm = h
            continue
        if not cm:
            continue
        name, isin = vt_isin(vt_cell(r, cm, "наименование ценной бумаги"))
        d = parse_date(vt_cell(r, cm, "дата операции"))
        if isin and d:
            out.append({"name": name, "isin": isin, "d": d, "qty": abs(tb_num(vt_cell(r, cm, "количество"))),
                        "op": vt_cell(r, cm, "тип операции"), "note": vt_cell(r, cm, "комментарий")})
    return out


def vt_cash_type(op, note, redeemed_full):
    """Строка денежного движения -> (вид, подпись); None — зеркало сделок."""
    o, n = vt_norm(op), vt_norm(note)
    if o.startswith("сальдо расчетов по сделкам"):
        return None
    if o.startswith("зачисление денежных"):
        return "INPUT", "Пополнение счёта"
    if o.startswith("списание денежных"):
        return "OUTPUT", "Вывод средств"
    if o.startswith("купонный доход"):
        return "COUPON", "Купон"
    if o.startswith("дивиденды"):
        return "DIVIDEND", "Дивиденды"
    if o.startswith("погашение"):
        return ("BOND_REPAYMENT_FULL", "Погашение") if redeemed_full else ("BOND_REPAYMENT", "Амортизация")
    if "ндфл" in o or o.startswith("налог"):
        if "дивиденд" in n:
            return "DIVIDEND_TAX", "Налог с дивидендов"
        if "купон" in n:
            return "BOND_TAX", "Налог с купона"
        return "TAX", "Налог"
    if o.startswith("вознаграждение брокера"):
        if "депозитар" in n or "обслуж" in n or "тариф" in n:
            return "SERVICE_FEE", "Обслуживание"
        return "BROKER_FEE", "Комиссия брокера"
    if "маржин" in o or "маржин" in n:
        return "MARGIN_FEE", "Маржинальная комиссия"
    if "комисс" in o or "вознагражд" in o:
        return "SERVICE_FEE", op
    return "OTHER", op


def vtb_parse(table, splits=None):
    """Разбор отчёта ВТБ -> (ops, meta) в том же виде, что tbank_parse (см. tbank_reconcile / tbank_preview)."""
    d_from, d_to = vt_period(table)
    if d_from is None:
        raise ApiError("В отчёте ВТБ не нашёл период.", 400)
    sec = vt_sections(table)
    period = {"from": d_from.strftime("%Y-%m-%d"), "to": (d_to or d_from).strftime("%Y-%m-%d")}
    start = d_from.replace(hour=0, minute=0, second=0)
    end_dt = (d_to or d_from).replace(hour=23, minute=59, second=59)
    bal = vt_balances(sec.get("cashbal") or [])
    cash_rows = vt_cash(sec.get("cash") or [])
    pos = vt_secbal(sec.get("secbal") or [])
    mov = vt_secmov(sec.get("secmov") or [])
    stat = defaultdict(int)
    ops, deal_seen, xids = [], {}, set()
    for x in vt_deals(sec.get("deals") or []) + vt_deals(sec.get("done") or []):  # «заключённые» + «завершённые», дедуп по номеру
        deal_seen.setdefault(x["num"], x)
    deals = sorted(deal_seen.values(), key=lambda z: z["dt"])
    dq, day_deals, first_unit = defaultdict(float), defaultdict(list), {}
    for x in deals:
        low = x["kind"].lower()
        sign = 1 if "покуп" in low else -1 if "продаж" in low else 0
        if x["repo"]:
            stat["repo"] += 1
            continue
        if not sign or not x["qty"]:
            stat["unknown_deal"] += 1
            continue
        unit = x["total"] / x["qty"]
        first_unit.setdefault(x["isin"], unit)
        dq[x["isin"]] += sign * x["qty"]
        day_deals[x["isin"]].append((x["dt"], sign * x["qty"], unit))
        ops.append({"id": "vtb-" + re.sub(r"[^0-9A-Za-z]", "", x["num"]), "date": tb_iso(x["dt"]),
                    "type": "OPERATION_TYPE_" + ("BUY" if sign > 0 else "SELL"),
                    "payment": to_money(round(-sign * x["total"], 9), x["cur"]), "name": x["name"], "_ident": x["isin"],
                    "quantity": tb_qty_str(x["qty"]), "quantityDone": tb_qty_str(x["qty"]),
                    "price": to_money(round(unit, 9), x["cur"])})
        stat["buy" if sign > 0 else "sell"] += 1
    # движение бумаг без сделки: «Расчеты по заключенным сделкам» — зеркало сделок
    redeemed, dm, xfer = set(), defaultdict(float), []
    for x in mov:
        low = vt_norm(x["op"] + " " + x["note"])
        if "расчеты по заключенным сделкам" in low:
            stat["mirror_sec"] += 1
            continue
        if "погашен" in low:
            redeemed.add(x["isin"])
            continue
        sign = 1 if any(w in low for w in ("зачисл", "ввод", "покупка", "поступ")) else -1 if any(
            w in low for w in ("списан", "вывод", "продаж")) else 0
        if not sign or not x["qty"]:
            stat["unknown_move"] += 1
            continue
        dm[x["isin"]] += sign * x["qty"]
        xfer.append((x, sign))
    cash_seen = {}
    for x in cash_rows:
        typ = vt_cash_type(x["op"], x["note"], False)
        if typ is None:
            stat["mirror"] += 1
            continue
        kind, label = typ
        _n, isin = vt_isin(x["note"]) if "ISIN" in x["note"] else ("", "")
        if kind == "BOND_REPAYMENT" and isin in redeemed:
            kind, label = "BOND_REPAYMENT_FULL", "Погашение"
        nm = re.search(r"(?:облигациям|акциям)\s+(.*?)\s+ISIN", x["note"])
        o = {"id": tb_hash_id("vtb", (x["cur"], x["d"].strftime("%Y%m%d"), x["amount"], x["op"], x["note"]), cash_seen),
             "date": tb_iso(x["d"]), "payment": to_money(round(x["amount"], 9), x["cur"]),
             "name": (nm.group(1) if nm else "") or label}
        if kind in ("COUPON", "DIVIDEND", "BOND_REPAYMENT", "BOND_REPAYMENT_FULL", "DIVIDEND_TAX") and isin:
            o["_ident"] = isin
        o["type"] = "OPERATION_TYPE_X_OTHER" if kind == "OTHER" else "OPERATION_TYPE_" + kind
        if kind == "OTHER":
            o["name"] = label
        ops.append(o)
        stat[classify(o["type"])] += 1
    # остатки: входящий = операция на начало периода; всё, что не объяснено сделками, — движение без сделки
    open_iso = tb_iso(start)
    tag = {"_opening": True, "_period": [period["from"], period["to"]]}
    sp = splits if splits is not None else splits_by_isin(period["from"], period["to"], set(pos) | set(dq))
    meta_pos = {}
    for isin in set(pos) | set(dq):
        p = pos.get(isin) or {"name": "", "open": 0.0, "close": 0.0, "plan": 0.0}
        econ_open, econ_close = p["open"], p["plan"] if isin in pos else dq[isin]
        meta_pos[isin] = {"name": p["name"], "open": p["open"], "close": p["close"], "plan": p["plan"], "econ_open": econ_open,
                          "econ_close": econ_close, "resid": econ_close - split_walk(econ_open, day_deals.get(isin, ()), sp.get(isin, ())) - dm.get(isin, 0.0)}
    name_of = {x["isin"]: x["name"] for x in deals}
    for isin, p in sorted(meta_pos.items()):
        nm, unit = p["name"] or name_of.get(isin) or isin, first_unit.get(isin, 0.0)
        r = p["resid"]
        if isin in redeemed and p["econ_close"] < 0.5 and r < -0.5:
            r = 0.0  # погашение: бумаги списаны, это учёл денежный раздел
        if abs(r) <= 1e-6:
            r = 0.0
        if p["econ_open"] > 1e-6:
            ops.append(dict({"id": "vtb-open-sec-%s-%s" % (isin, period["from"]), "date": open_iso,
                             "type": "OPERATION_TYPE_INPUT_SECURITIES", "payment": to_money(0, "rub"),
                             "name": nm, "_ident": isin, "quantity": tb_qty_str(p["econ_open"]),
                             "quantityDone": tb_qty_str(p["econ_open"]), "price": to_money(round(unit, 9), "rub"),
                             "description": "Входящий остаток на начало периода (отчёт об остатках ценных бумаг)"}, **tag))
            stat["opening_sec"] += 1
        # продажи без покрытия FIFO не знает: недостающее довносим входящей операцией перед продажей и снимаем после покрытия
        run, short, extra = p["econ_open"] + max(r, 0.0), 0.0, []
        for t, q, u in split_timeline(day_deals.get(isin, ()), sp.get(isin, ())):
            if q is None:
                run *= u
                short *= u
                continue
            if q < 0:
                take = min(run, -q)
                run -= take
                if -q - take > 1e-6:
                    extra.append((True, -q - take, t - timedelta(seconds=1), u))
                    short += -q - take
            else:
                c = min(short, q)
                if c > 1e-6:
                    extra.append((False, c, t + timedelta(seconds=1), u))
                    short -= c
                run += q - c
        if short > 1e-6:
            extra.append((False, short, end_dt, unit))
        # движение без сделки с известной датой — отдельными операциями, остаток нерасшифрованного — на границе периода
        for x, sign in xfer:
            if x["isin"] == isin:
                extra.append((sign > 0, x["qty"], x["d"].replace(hour=0, minute=0, second=1), unit))
        if r > 0:
            extra.append((True, r, start.replace(second=1), unit))
        elif r < 0:
            extra.append((False, -r, end_dt, unit))
        for sec_in, qty_x, when, u in extra:
            xid = "vtb-xfer-%s-%s-%s" % ("in" if sec_in else "out", isin, tb_iso(when))
            xid = uniq_op_id(xid, xids)
            ops.append({"id": xid, "date": tb_iso(when),
                        "type": "OPERATION_TYPE_" + ("INPUT_SECURITIES" if sec_in else "OUTPUT_SECURITIES"),
                        "payment": to_money(0, "rub"), "name": nm, "_ident": isin,
                        "quantity": tb_qty_str(qty_x), "quantityDone": tb_qty_str(qty_x), "price": to_money(round(u, 9), "rub"),
                        "description": "Движение бумаг без сделки (отчёт ВТБ): перевод, корпоративное действие или продажа без покрытия"})
            stat["xfer_in" if sec_in else "xfer_out"] += 1
    for cur, (b_in, _b_out, _b_plan) in sorted(bal.items()):
        if abs(b_in) >= 0.005:
            ops.append(dict({"id": "vtb-open-cash-%s-%s" % (cur, period["from"]), "date": open_iso,
                             "type": "OPERATION_TYPE_INPUT" if b_in > 0 else "OPERATION_TYPE_X_OPENING",
                             "payment": to_money(round(b_in, 2), cur), "name": "Входящий остаток на начало периода"}, **tag))
            stat["opening_cash"] += 1
    ops.sort(key=lambda o: (o["date"], 0 if o.get("_opening") else 1))
    meta = {"format": "vtb", "title": "Отчёт брокера ВТБ", "period": period, "cash_open": {c: v[0] for c, v in bal.items()},
            "cash_close": {c: v[2] for c, v in bal.items()}, "pos": meta_pos, "stat": dict(stat)}
    return ops, meta


def broker_try(filename, raw):
    """(ops, meta) для отчёта известного брокера (Т-Инвестиции, ВТБ); иначе None — тогда общий импортёр."""
    fn = (filename or "").lower()
    if not (fn.endswith((".xlsx", ".xlsm")) or raw[:2] == b"PK"):
        return None
    try:
        tables = read_tables(filename, raw)
    except Exception:  # noqa: BLE001 — битый файл: пусть скажет общий импортёр
        return None
    t = tb_detect(tables)
    if t:
        return tbank_parse(t)
    t = vt_detect(tables)
    return vtb_parse(t) if t else None
