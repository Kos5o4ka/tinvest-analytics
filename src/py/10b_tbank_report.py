# ═══════════════════════════════ отчёт брокера Т-Инвестиций (xlsx) ═══════════════════════════════
#
# Общий импортёр берёт первую найденную таблицу (раздел 1.1 «сделки») и ломает учёт: РЕПО-ноги считает
# настоящими сделками, не видит раздел 2 «Операции с денежными средствами» и теряет входящие остатки.
# Здесь — отдельный разбор отчёта «Отчет о сделках и операциях» АО «ТБанк»:
#   1.1  сделки без РЕПО (id по «Номеру сделки»)              -> BUY / SELL + отдельная комиссия
#   2.   денежные операции (пополнения, выплаты, налоги…)      -> операции со стабильным хэш-id;
#        строки-«зеркала» сделок («Покупка/продажа», «Комиссия за сделки», «DFP/RFP») пропускаются,
#        РЕПО сворачивается в дневное нетто типа «прочее» (на остаток денег влияет, на аналитику — нет)
#   3.1  остатки по бумагам: входящий остаток -> синтетическая «входящая» операция на начало периода;
#        движение без сделок (переводы, DFP) -> синтетическая операция на границе периода
#   4.1  соответствие «Код актива» -> ISIN
# Синтетические операции помечены полем _opening и снимаются автоматически, когда добавлен более ранний файл
# (см. import_merge_ops), поэтому два соседних отчёта склеиваются без разрывов.

TB_REPO_RE = re.compile(r"^\s*репо", re.I)
TB_MIRROR_OPS = ("покупка/продажа", "комиссия за сделки", "dfp/rfp")
TB_SEC_TITLE_RE = re.compile(r"^(\d)\.(\d)?\s+\S")
TB_EXPECT = {
    "1.1": ("номер сделки", "дата заключения", "вид сделки", "код актива", "количество"),
    "2": ("дата исполнения", "операция", "сумма зачисления", "сумма списания"),
    "3.1": ("код актива", "isin", "входящий остаток", "исходящий остаток"),
}
TB_KIND_RU = {"buy": "покупок", "sell": "продаж", "coupons": "купонов", "dividends": "дивидендов", "deposits": "пополнений",
              "withdrawals": "выводов", "fee_broker": "комиссий", "fee_service": "обслуживание", "margin_fee": "маржа",
              "tax_trade": "налогов", "tax_dividend": "налогов с дивидендов", "tax_coupon": "налогов с купонов",
              "repayments": "погашений", "sec_in": "входящих бумаг", "sec_out": "списаний бумаг", "other": "прочее",
              "varmargin": "вариационная маржа"}


def tb_norm(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\xa0", " ")).strip().lower()


def tb_detect(tables):
    """Таблица отчёта «Отчет о сделках и операциях» брокера Т-Инвестиций (АО «ТБанк», ранее «Тинькофф») или None."""
    for t in tables[:3]:
        head = " ".join(tb_norm(r[0]).replace("ё", "е") for r in t[:25] if r)
        if "отчет о сделках и операциях" in head and re.search(r"тбанк|т-банк|тинькофф|т-инвест", head):
            if any(tb_norm(r[0]).startswith("1.1 информация о совершенных") for r in t[:80] if r):
                return t
    return None


def tb_sections(rows):
    """{'1.1': [строки…], '2': [...]} — строки между заголовками разделов; ключ — номер раздела."""
    out, cur = {}, None
    for r in rows:
        c0 = str(r[0]).strip() if r else ""
        m = TB_SEC_TITLE_RE.match(c0) if c0 and not any(str(x).strip() for x in r[1:]) else None
        if m:
            cur = m.group(1) + ("." + m.group(2) if m.group(2) else "")
            out.setdefault(cur, [])
            continue
        if cur is not None:
            out[cur].append(r)
    return out


def tb_cols(row, expect):
    """Карта {заголовок: колонка}, если строка — заголовок таблицы (содержит все нужные подписи)."""
    cm = {}
    for i, c in enumerate(row):
        k = tb_norm(c)
        if k and k not in cm:
            cm[k] = i
    return cm if all(e in cm for e in expect) else None


def tb_cell(row, cm, key):
    i = cm.get(key)
    return str(row[i]).strip() if i is not None and i < len(row) and row[i] is not None else ""


def tb_num(s):
    v = parse_num(s)
    return v if v is not None else 0.0


def tb_dt(d, t=""):
    """«дд.мм.гггг» + «чч:мм:сс» -> datetime."""
    dt = parse_date(d)
    if not dt:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?", str(t or "").strip())
    if m and dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        dt = dt.replace(hour=min(int(m.group(1)), 23), minute=int(m.group(2)), second=int(m.group(3) or 0))
    return dt


def tb_iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def tb_period(rows):
    for r in rows[:30]:
        m = re.search(r"за период\s+(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})", str(r[0]) if r else "")
        if m:
            return parse_date(m.group(1)), parse_date(m.group(2))
    return None, None


def tb_hash_id(prefix, parts, seen):
    """Стабильный id по содержимому строки; одинаковые строки внутри файла различаются порядковым номером."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:14]
    n = seen[h] = seen.get(h, 0) + 1
    return "%s-%s%s" % (prefix, h, "" if n == 1 else "-%d" % n)


def uniq_op_id(xid, seen):
    """id перевода бумаг: при совпадении (одна бумага, одна секунда) — суффикс -2, -3...; прежние id не меняются."""
    base, n = xid, 1
    while xid in seen:
        n += 1
        xid = "%s-%d" % (base, n)
    seen.add(xid)
    return xid


def tb_deals(rows):
    """Строки раздела 1.1/1.2 -> список сделок (все виды, включая РЕПО; фильтрует вызывающий)."""
    out, cm = [], None
    for r in rows:
        h = tb_cols(r, TB_EXPECT["1.1"])
        if h:
            cm = h
            continue
        if not cm:
            continue
        num, kind = tb_cell(r, cm, "номер сделки"), tb_cell(r, cm, "вид сделки")
        if not num or not kind:
            continue
        dt = tb_dt(tb_cell(r, cm, "дата заключения"), tb_cell(r, cm, "время"))
        if not dt:
            continue
        # биржевой и клиринговый сбор отдельно с клиента не списываются (в «Комиссии за сделки» раздела 2 — только брокерская)
        comm = abs(tb_num(tb_cell(r, cm, "комиссия брокера")))
        out.append({"num": num, "kind": kind, "repo": bool(TB_REPO_RE.match(kind)), "dt": dt,
                    "name": tb_cell(r, cm, "наименование актива"), "code": tb_cell(r, cm, "код актива"),
                    "qty": abs(tb_num(tb_cell(r, cm, "количество"))), "net": tb_num(tb_cell(r, cm, "сумма (без нкд)")),
                    "nkd": tb_num(tb_cell(r, cm, "нкд")), "total": tb_num(tb_cell(r, cm, "сумма сделки")),
                    "cur": norm_cur(tb_cell(r, cm, "валюта расчетов")), "comm": comm})
    return out


def tb_cash_section(rows):
    """Раздел 2 -> (остатки {cur: (входящий, исходящий)}, строки-операции)."""
    bal, ops, cur, cm, bm = {}, [], None, None, None
    for r in rows:
        nz = [(i, str(c).strip()) for i, c in enumerate(r) if str(c).strip()]
        if not nz:
            continue
        b = tb_cols(r, ("валюта", "входящий остаток", "исходящий остаток"))
        if b:
            bm = b
            continue
        h = tb_cols(r, TB_EXPECT["2"])
        if h:
            cm = h
            continue
        if len(nz) == 1 and re.fullmatch(r"[A-Z]{3}", nz[0][1]):
            cur, cm = nz[0][1].lower(), None
            continue
        if bm is not None and cm is None and re.fullmatch(r"[A-Z]{3}", tb_cell(r, bm, "валюта")):
            bal[tb_cell(r, bm, "валюта").lower()] = (tb_num(tb_cell(r, bm, "входящий остаток")),
                                                     tb_num(tb_cell(r, bm, "исходящий остаток")))
            continue
        if cm is None or cur is None:
            continue
        op = tb_cell(r, cm, "операция")
        if not op:
            continue
        ops.append({"cur": cur, "d": tb_cell(r, cm, "дата"), "t": tb_cell(r, cm, "время совершения"),
                    "x": tb_cell(r, cm, "дата исполнения"), "op": op,
                    "cr": tb_num(tb_cell(r, cm, "сумма зачисления")), "db": tb_num(tb_cell(r, cm, "сумма списания")),
                    "note": tb_cell(r, cm, "примечание")})
    return bal, ops


def tb_note(note):
    """Из «Тип КД: …, Наименование: …, ISIN: …» -> (тип КД, название, ISIN)."""
    kd = re.search(r"Тип КД:\s*(.*?)(?:,\s*(?:Наименование|ISIN|Референс|Дата)\b|$)", note or "")
    nm = re.search(r"Наименование:\s*(.*?),\s*ISIN:", note or "")
    isin = re.search(r"ISIN:\s*([A-Z]{2}[A-Z0-9]{9}\d)", note or "")
    return (kd.group(1).strip() if kd else ""), (nm.group(1).strip() if nm else ""), (isin.group(1) if isin else "")


def tb_cash_type(op, note):
    """Строка раздела 2 -> (вид операции, подпись); None для строк-зеркал сделок."""
    o, kd = tb_norm(op), tb_norm(tb_note(note)[0])
    if o in TB_MIRROR_OPS:
        return None
    if o.startswith("выплата доходов по корпоративным"):
        if "частичн" in kd or "амортиз" in kd:
            return "BOND_REPAYMENT", "Амортизация"
        if "погашен" in kd:
            return "BOND_REPAYMENT_FULL", "Погашение"
        if "дивиденд" in kd:
            return "DIVIDEND", "Дивиденды"
        if "облигац" in kd or "купон" in kd:
            return "COUPON", "Купон"
        return "DIVIDEND", "Выплата дохода"
    if o.startswith("возмещение дохода по сделке репо"):
        return "COUPON", "Возмещение дохода по сделке РЕПО"
    if o == "пополнение счета":
        return "INPUT", "Пополнение счёта"
    if o == "вывод средств":
        return "OUTPUT", "Вывод средств"
    if o.startswith("перевод зачисление"):
        return "INPUT", "Перевод (зачисление)"
    if o.startswith("перевод списание"):
        return "OUTPUT", "Перевод (списание)"
    if o.startswith("налог (дивиденд"):
        return "DIVIDEND_TAX", "Налог с дивидендов"
    if o.startswith("налог"):
        return "TAX", "Налог"
    if o.startswith("комиссия по тарифу"):
        return "SERVICE_FEE", "Комиссия по тарифу"
    if "комиссия" in o and "пфи" in o:
        return "BROKER_FEE", "Комиссия за сделки с производными"
    if o.startswith("вариационная маржа"):
        return "VARMARGIN", "Вариационная маржа"
    if "маржин" in o:
        return "MARGIN_FEE", "Маржинальная комиссия"
    if o.startswith("отражение требований по непокрытой"):
        return "UNCOVERED", "Требования по непокрытой позиции"
    if o == "репо":
        return "REPO", "РЕПО"
    return "OTHER", op


def tb_positions(rows):
    """Раздел 3.1 -> {isin: {name, code, open, close, plan}}."""
    out, cm = {}, None
    for r in rows:
        h = tb_cols(r, TB_EXPECT["3.1"])
        if h:
            cm = h
            continue
        if not cm:
            continue
        isin, code = tb_cell(r, cm, "isin").upper(), tb_cell(r, cm, "код актива")
        key = isin or code
        if not key or not tb_cell(r, cm, "исходящий остаток"):
            continue
        p = out.setdefault(key, {"name": tb_cell(r, cm, "наименование актива"), "code": code, "open": 0.0, "close": 0.0, "plan": 0.0})
        p["open"] += tb_num(tb_cell(r, cm, "входящий остаток"))
        p["close"] += tb_num(tb_cell(r, cm, "исходящий остаток"))
        p["plan"] += tb_num(tb_cell(r, cm, "плановый исходящий остаток"))
    return out


def tb_isin_map(sections):
    """«Код актива» -> ISIN по разделам 3.1 и 4.1."""
    m = {}
    for sec in ("3.1", "4.1"):
        cm = None
        for r in sections.get(sec) or []:
            h = tb_cols(r, ("код актива", "isin"))
            if h:
                cm = h
                continue
            if cm:
                code, isin = tb_cell(r, cm, "код актива"), tb_cell(r, cm, "isin").upper()
                if code and ISIN_RE.match(isin):
                    m[code] = isin
    return m


def tb_deriv_codes(sections):
    """Коды фьючерсов/опционов из раздела 4.3: их «сделки» — не деньги и не бумаги (расчёты идут вариационной маржой)."""
    out, cm = set(), None
    for r in sections.get("4.3") or []:
        h = tb_cols(r, ("код контракта",))
        if h:
            cm = h
            continue
        if cm and tb_cell(r, cm, "код контракта"):
            out.add(tb_cell(r, cm, "код контракта"))
    return out


def tb_qty_str(q):
    return str(int(round(q))) if abs(q - round(q)) < 1e-9 else ("%.9f" % q).rstrip("0").rstrip(".")


def tbank_parse(table, splits=None):
    """Разбор отчёта Т-Инвестиций. Возвращает (ops, meta): ops в том же формате, что и у общего импортёра
    (с полем _ident для поиска бумаги), meta — период, остатки и счётчики для сверки и предпросмотра."""
    d_from, d_to = tb_period(table)
    sections = tb_sections(table)
    isin_of = tb_isin_map(sections)
    # у «Кода актива» бывает вид ISIN, но не ISIN (SU26238RMFS4 у ОФЗ) — таблица 3.1/4.1 главнее
    ident = lambda code: isin_of.get(code) or code
    deals = tb_deals(sections.get("1.1") or [])
    pending = tb_deals(sections.get("1.2") or [])
    pos = tb_positions(sections.get("3.1") or [])
    deriv = tb_deriv_codes(sections)
    bal, cash_rows = tb_cash_section(sections.get("2") or [])
    if d_from is None:
        dts = [x["dt"] for x in deals] + [parse_date(x["x"]) for x in cash_rows if parse_date(x["x"])]
        if not dts:
            raise ApiError("В отчёте Т-Инвестиций не нашёл период и операции.", 400)
        d_from, d_to = min(dts), max(dts)
    start = d_from.replace(hour=0, minute=0, second=0)
    period = {"from": start.strftime("%Y-%m-%d"), "to": (d_to or d_from).strftime("%Y-%m-%d")}
    ops, stat, xids = [], defaultdict(int), set()

    # ── сделки (раздел 1.1) ──
    dq_trade, dq_repo, first_unit, nums = defaultdict(float), defaultdict(float), {}, defaultdict(int)
    day_deals = defaultdict(list)
    for x in deals:
        low = x["kind"].lower()
        sign = 1 if "покуп" in low else -1 if "продаж" in low else 0
        isin = ident(x["code"])
        if x["repo"]:
            stat["repo"] += 1
            if sign and x["qty"]:
                dq_repo[isin] += sign * x["qty"]
            continue
        if x["code"] in deriv:
            stat["deriv_deals"] += 1
            continue
        if not sign or not x["qty"]:
            stat["unknown_deal"] += 1
            continue
        dq_trade[isin] += sign * x["qty"]
        total = abs(x["total"]) or abs(x["net"]) + abs(x["nkd"])
        unit = (abs(x["net"]) + abs(x["nkd"])) / x["qty"]
        first_unit.setdefault(isin, unit)
        day_deals[isin].append((x["dt"], sign * x["qty"], total / x["qty"]))
        nums[x["num"]] += 1
        base = "tb-" + re.sub(r"[^0-9A-Za-z]", "", x["num"]) + ("" if nums[x["num"]] == 1 else "-%d" % nums[x["num"]])
        o = {"id": base, "date": tb_iso(x["dt"]), "type": "OPERATION_TYPE_" + ("BUY" if sign > 0 else "SELL"),
             "payment": to_money(round(-sign * total, 9), x["cur"]), "name": x["name"] or x["code"], "_ident": isin,
             "quantity": tb_qty_str(x["qty"]), "quantityDone": tb_qty_str(x["qty"]),
             "price": to_money(round(unit, 9), x["cur"])}
        ops.append(o)
        stat["buy" if sign > 0 else "sell"] += 1
        if x["comm"]:
            ops.append({"id": base + "-f", "date": o["date"], "type": "OPERATION_TYPE_BROKER_FEE",
                        "payment": to_money(-round(x["comm"], 9), x["cur"]),
                        "name": "Комиссия: " + (x["name"] or x["code"]), "_ident": isin})

    # ── денежные операции (раздел 2) ──
    repo_net, cash_seen, redeemed = defaultdict(float), {}, set()
    for x in cash_rows:
        if tb_norm(x["note"]) == "план":
            stat["planned"] += 1
            continue
        typ = tb_cash_type(x["op"], x["note"])
        if typ is None:
            stat["mirror"] += 1
            continue
        kind, label = typ
        amount = round(x["cr"] - x["db"], 9)
        dt = tb_dt(x["d"], x["t"]) if x["d"] else parse_date(x["x"])
        if not dt:
            stat["skipped"] += 1
            continue
        if kind == "REPO":
            repo_net[(dt.strftime("%Y-%m-%d"), x["cur"])] += amount
            continue
        _kd, nm, isin = tb_note(x["note"])
        o = {"id": tb_hash_id("tb", (x["cur"], x["d"], x["t"], x["x"], x["op"], x["cr"], x["db"], x["note"]), cash_seen),
             "date": tb_iso(dt), "payment": to_money(amount, x["cur"]), "name": nm or label}
        if kind in ("COUPON", "DIVIDEND", "BOND_REPAYMENT", "BOND_REPAYMENT_FULL", "DIVIDEND_TAX"):
            o["_ident"] = isin or nm
            if kind == "BOND_REPAYMENT_FULL" and isin:
                redeemed.add(isin)
        if kind == "VARMARGIN":
            o["type"] = "OPERATION_TYPE_" + ("ACCRUING_VARMARGIN" if amount >= 0 else "WRITING_OFF_VARMARGIN")
        elif kind in ("UNCOVERED", "OTHER"):
            o["type"], o["name"] = "OPERATION_TYPE_X_" + kind, label
        else:
            o["type"] = "OPERATION_TYPE_" + kind
        ops.append(o)
        stat[classify(o["type"])] += 1
    for (day, cur), v in sorted(repo_net.items()):
        if abs(v) >= 0.005:
            ops.append({"id": "tb-repo-%s-%s" % (day, cur), "date": day + "T00:00:00Z", "type": "OPERATION_TYPE_X_REPO",
                        "payment": to_money(round(v, 2), cur), "name": "Расчёты по сделкам РЕПО (нетто за день)"})
            stat["repo_cash"] += 1

    # ── входящие остатки и движение бумаг без сделок ──
    lent_end = defaultdict(float)  # бумаги, ушедшие в РЕПО и ещё не вернувшиеся к концу периода (вторые ноги из 1.2)
    for x in pending:
        if x["repo"] and re.match(r"^\s*репо\s*2", x["kind"], re.I):
            lent_end[ident(x["code"])] += x["qty"] if "покуп" in x["kind"].lower() else -x["qty"]
    # сплиты Мосбиржи внутри периода: количество на их день умножается, поэтому «лишних» бумаг без сделки не возникает
    sp = splits if splits is not None else splits_by_isin(period["from"], period["to"], set(pos) | set(dq_trade) | set(lent_end), isin_of)
    meta_pos = {}
    for isin, p in pos.items():
        key = isin if ISIN_RE.match(isin) else ident(p["code"])
        econ_close = p["close"] + lent_end.get(key, 0.0)
        econ_open = p["open"] + lent_end.get(key, 0.0) + dq_repo.get(key, 0.0)
        meta_pos[key] = {"name": p["name"], "open": p["open"], "close": p["close"], "plan": p["plan"], "econ_open": econ_open,
                         "econ_close": econ_close,
                         "resid": econ_close - split_walk(econ_open, day_deals.get(key, ()), sp.get(key, ()))}
    for key in set(dq_trade) | set(lent_end):
        if key not in meta_pos:  # бумаги нет в 3.1 (нулевые остатки)
            eo = lent_end.get(key, 0.0) + dq_repo.get(key, 0.0)
            meta_pos[key] = {"name": "", "open": 0.0, "close": 0.0, "plan": 0.0, "econ_open": eo,
                             "econ_close": lent_end.get(key, 0.0),
                             "resid": lent_end.get(key, 0.0) - split_walk(eo, day_deals.get(key, ()), sp.get(key, ()))}
    day_deals = {k: sorted(v, key=lambda z: z[0]) for k, v in day_deals.items()}
    name_of = {ident(x["code"]): x["name"] for x in deals + pending if x["name"]}
    open_iso = tb_iso(start)
    end_dt = datetime.strptime(period["to"], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    tag = {"_opening": True, "_period": [period["from"], period["to"]]}
    for key, p in sorted(meta_pos.items()):
        nm = p["name"] or name_of.get(key) or key
        unit = first_unit.get(key, 0.0)
        if p["econ_open"] > 0.5:
            q = p["econ_open"]
            ops.append(dict({"id": "tb-open-sec-%s-%s" % (key, period["from"]), "date": open_iso,
                             "type": "OPERATION_TYPE_INPUT_SECURITIES", "payment": to_money(0, "rub"),   # деньги не двигаются: оценка — в price
                             "name": nm, "_ident": key, "quantity": tb_qty_str(q), "quantityDone": tb_qty_str(q),
                             "price": to_money(round(unit, 9), "rub"),
                             "description": "Входящий остаток на начало периода (раздел 3.1 отчёта)"}, **tag))
            stat["opening_sec"] += 1
        r = p["resid"]
        if key in redeemed and p["econ_close"] < 0.5 and r < -0.5:
            r = 0.0  # списание бумаг — это погашение, его уже учтёл денежный раздел
        if abs(r) <= 0.5:
            r = 0.0
        # FIFO не знает коротких позиций: если продаж больше, чем бумаг на руках (продажа «с плеча» с покрытием через
        # секунды), недостающее довносим входящей операцией перед продажей и снимаем после покупки-покрытия
        run, short, extra = p["econ_open"] + max(r, 0.0), 0.0, []
        for t, dq, u in split_timeline(day_deals.get(key, ()), sp.get(key, ())):
            if dq is None:
                run *= u
                short *= u
                continue
            if dq < 0:
                take = min(run, -dq)
                run -= take
                if -dq - take > 0.5:
                    extra.append((True, -dq - take, t - timedelta(seconds=1), u))
                    short += -dq - take
            else:
                c = min(short, dq)
                if c > 0.5:
                    extra.append((False, c, t + timedelta(seconds=1), u))
                    short -= c
                run += dq - c
        if short > 0.5:
            extra.append((False, short, end_dt, unit))
        if r > 0:
            extra.append((True, r, start.replace(second=1), unit))
        elif r < 0:
            extra.append((False, -r, end_dt, unit))
        for sec_in, qty_x, when, u in extra:
            xid = "tb-xfer-%s-%s-%s" % ("in" if sec_in else "out", key, tb_iso(when))
            xid = uniq_op_id(xid, xids)
            ops.append({"id": xid,
                        "date": tb_iso(when), "type": "OPERATION_TYPE_" + ("INPUT_SECURITIES" if sec_in else "OUTPUT_SECURITIES"),
                        "payment": to_money(0, "rub"), "name": nm, "_ident": key,   # перевод бумаг не двигает деньги; оценка — в price
                        "quantity": tb_qty_str(qty_x), "quantityDone": tb_qty_str(qty_x), "price": to_money(round(u, 9), "rub"),
                        "description": "Движение бумаг без сделки (раздел 3.1 отчёта): перевод, DFP, корпоративное действие или продажа без покрытия"})
            stat["xfer_in" if sec_in else "xfer_out"] += 1
    # входящий остаток денег: положительный — как пополнение на начало периода, отрицательный — служебная запись
    for cur, (b_in, _b_out) in sorted(bal.items()):
        if abs(b_in) >= 0.005:
            ops.append(dict({"id": "tb-open-cash-%s-%s" % (cur, period["from"]), "date": open_iso,
                             "type": "OPERATION_TYPE_INPUT" if b_in > 0 else "OPERATION_TYPE_X_OPENING",
                             "payment": to_money(round(b_in, 2), cur), "name": "Входящий остаток на начало периода"}, **tag))
            stat["opening_cash"] += 1
    ops.sort(key=lambda o: (o["date"], 0 if o.get("_opening") else 1))
    meta = {"format": "tbank", "title": "Отчёт брокера Т-Инвестиций", "period": period, "cash_open": {c: v[0] for c, v in bal.items()},
            "cash_close": {c: v[1] for c, v in bal.items()}, "pos": meta_pos, "stat": dict(stat)}
    return ops, meta


def tbank_reconcile(ops, meta):
    """Сверка операций с итогами самого отчёта: деньги по валютам и количество бумаг по ISIN.
    {'cash': {cur: (по отчёту, по операциям)}, 'pos': {isin: (по отчёту, по операциям)}, 'ok': bool}."""
    cash = defaultdict(float)
    for o in ops:                                   # все операции, как их суммирует портфель (переводы бумаг — с нулевой суммой)
        cash[cur_of(o["payment"])] += qf(o["payment"])
    work = []
    for o in sorted(ops, key=lambda o: o["date"]):
        w = dict(o)
        if w.get("_ident") and classify(w["type"]) in ("buy", "sell", "sec_in", "sec_out", "repayments"):
            w["instrumentUid"] = "imp:" + w["_ident"]
            w["_sec"] = w["_ident"]
        work.append(w)
    work = import_apply_splits(work, until=meta["period"]["to"])   # сплиты после конца периода отчёта в его остатках не видны
    held = {u[4:]: v["qty"] for u, v in fifo(work).items()}
    res = {"cash": {c: (meta["cash_close"].get(c, 0.0), cash.get(c, 0.0)) for c in set(meta["cash_close"]) | set(cash)},
           "pos": {k: (p["econ_close"], held.get(k, 0.0)) for k, p in meta["pos"].items()}}
    for k, q in held.items():
        res["pos"].setdefault(k, (0.0, q))
    res["ok"] = all(abs(a - b) < 1.0 for a, b in res["cash"].values()) and all(abs(a - b) < 0.5 for a, b in res["pos"].values())
    return res


def tbank_try(filename, raw):
    """(ops, meta), если файл — отчёт Т-Инвестиций; иначе None (тогда работает общий импортёр)."""
    fn = (filename or "").lower()
    if not (fn.endswith((".xlsx", ".xlsm")) or raw[:2] == b"PK"):
        return None
    try:
        tables = read_tables(filename, raw)
    except Exception:  # noqa: BLE001 — не xlsx/битый файл: пусть разбирается общий импортёр и скажет понятную ошибку
        return None
    t = tb_detect(tables)
    return tbank_parse(t) if t else None


def tbank_preview(ops, meta):
    """Предпросмотр: что нашли, что пропустили, сошлись ли деньги и бумаги с итогами отчёта, куда предложить добавить."""
    kinds = defaultdict(int)
    for o in ops:
        kinds[classify(o["type"])] += 1
    rec = tbank_reconcile(ops, meta)
    bad_cash = {c: [a, b] for c, (a, b) in rec["cash"].items() if abs(a - b) >= 1.0}
    bad_pos = sorted(((abs(a - b), k, a, b) for k, (a, b) in rec["pos"].items() if abs(a - b) >= 0.5), reverse=True)
    st = meta["stat"]
    mine = [x for x in imports_list() if x.get("format") == meta["format"]]  # добавлять предлагаем только к счетам того же брокера
    return {"format": meta["format"], "title": meta["title"], "period": meta["period"], "count": len(ops),
            "kinds": dict(kinds), "kinds_ru": TB_KIND_RU, "repo_skipped": st.get("repo", 0), "mirror_skipped": st.get("mirror", 0),
            "opening_sec": st.get("opening_sec", 0), "xfer": st.get("xfer_in", 0) + st.get("xfer_out", 0),
            "cash_ok": not bad_cash, "cash_bad": bad_cash, "pos_total": len(rec["pos"]), "pos_bad": len(bad_pos),
            "pos_worst": [[k, a, b] for _, k, a, b in bad_pos[:5]],
            "sample": [[o["date"][:10], op_type(o), o.get("name") or "", op_qty(o), qf(o["payment"]), cur_of(o["payment"])]
                       for o in ops if not o.get("_opening") and classify(o["type"]) != "other"][:12],
            "targets": [{"id": x["id"], "name": x.get("name") or ""} for x in mine]}


def import_preview_any(filename, raw):
    hit = broker_try(filename, raw)
    return tbank_preview(*hit) if hit else import_preview(filename, raw)


def import_ops_any(filename, raw, table, header_row, mapping):
    """(ops, пропущено строк, формат, meta): отчёт Т-Инвестиций разбирается своим парсером, остальное — по выбранным колонкам."""
    hit = broker_try(filename, raw)
    if hit:
        return hit[0], hit[1]["stat"].get("skipped", 0), hit[1]["format"], hit[1]
    ops, skipped = import_ops(filename, raw, table, header_row, mapping)
    return ops, skipped, "", None
