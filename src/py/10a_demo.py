# ═══════════════════════════════ демо-портфель (без токена) ═══════════════════════════════
# Модельный портфель в формате импорта отчёта брокера. Даты задаются смещением «дней назад» от сегодняшнего дня,
# поэтому история всегда охватывает последние ~2 года. Цены и суммы выплат — приблизительные, не данные реального клиента.

DEMO_ID = "imp-demo"
DEMO_NAME = "Демо-портфель"

# (ISIN, тикер MOEX, название, вид, купон на 1 облигацию в ₽, период купона в днях, дней назад до последнего купона)
DEMO_INSTRUMENTS = [
    ("RU000A1038V6", "SU26238RMFS4", "ОФЗ-ПД 26238", "bond", 35.40, 182, 162),
    ("RU000A106E90", "SU26243RMFS4", "ОФЗ-ПД 26243", "bond", 48.87, 182, 162),
    ("RU000A108EH4", "SU26248RMFS3", "ОФЗ-ПД 26248", "bond", 61.08, 182, 162),
    ("RU000A106Z61", "SU29025RMFS2", "ОФЗ-ПК 29025 (флоатер)", "bond", 37.00, 91, 77),
    ("RU000A10DS74", "RU000A10DS74", "Сбербанк Sb51R", "bond", 12.21, 30, 1),
    ("RU000A1008D7", "RU000A1008D7", "РЖД 1Р-14R", "bond", 45.38, 182, 6),
    ("RU000A10CL07", "RU000A10CL07", "Магнит БО 001P-09", "bond", 10.93, 30, 22),
    ("RU000A10ER66", "RU000A10ER66", "ФосАгро БО 001P-06", "bond", 11.30, 30, 14),
    ("RU000A10BW62", "RU000A10BW62", "МТС 2P-12", "bond", 10.89, 30, 23),
    ("RU000A10BGY3", "RU000A10BGY3", "МТС 2P-10", "bond", 10.89, 30, 27),
    ("RU000A0JXQ44", "RU000A0JXQ44", "РЖД Б01P2R", "bond", 71.80, 182, 27),
    ("RU0009029540", "SBER", "Сбербанк России ПАО ао", "share", 0, 0, 0),
    ("RU0009024277", "LKOH", "НК ЛУКОЙЛ (ПАО) - ао", "share", 0, 0, 0),
]

# ISIN -> (дата погашения, купонов в год, плавающий купон) — для карточки облигации без справочника Т-Инвестиций
DEMO_BOND_PARAMS = {
    "RU000A1038V6": ("2041-05-15", 2, False), "RU000A106E90": ("2038-05-19", 2, False), "RU000A108EH4": ("2040-05-16", 2, False),
    "RU000A106Z61": ("2037-08-12", 4, True), "RU000A10DS74": ("2028-06-03", 12, False), "RU000A1008D7": ("2029-05-04", 2, False),
    "RU000A10CL07": ("2027-08-17", 12, False), "RU000A10ER66": ("2029-04-16", 12, False), "RU000A10BW62": ("2030-06-01", 12, False),
    "RU000A10BGY3": ("2030-03-30", 12, False), "RU000A0JXQ44": ("2037-04-02", 2, False),
}

# (дней назад, операция, ISIN, количество, цена в % номинала (облигации) или ₽ (акции))
DEMO_TRADES = [
    (720, "Покупка", "RU000A1038V6", 200, 63.2), (690, "Покупка", "RU000A106E90", 150, 78.5),
    (600, "Покупка", "RU000A10CL07", 300, 100.6), (570, "Покупка", "RU0009029540", 500, 275.0),
    (540, "Покупка", "RU000A108EH4", 120, 88.0), (500, "Покупка", "RU000A106Z61", 300, 98.9),
    (480, "Покупка", "RU0009024277", 20, 6900.0), (450, "Покупка", "RU000A10DS74", 400, 99.5),
    (420, "Покупка", "RU000A10BW62", 300, 100.3), (380, "Покупка", "RU000A1008D7", 250, 86.4),
    (330, "Покупка", "RU000A10ER66", 200, 101.2), (300, "Покупка", "RU000A1038V6", 150, 56.0),
    (250, "Покупка", "RU000A106E90", 100, 70.2), (250, "Покупка", "RU0009029540", 200, 310.0),
    (250, "Покупка", "RU000A0JXQ44", 100, 97.0), (200, "Покупка", "RU000A10BGY3", 200, 99.9),
    (90, "Продажа", "RU000A10CL07", 100, 99.8), (70, "Продажа", "RU0009029540", 200, 322.0),
    (60, "Продажа", "RU000A1038V6", 100, 53.5),
]
# (дней назад, ISIN, выплата на 1 бумагу в ₽) — дивиденды
DEMO_DIVS = [(482, "RU0009029540", 34.84), (117, "RU0009029540", 37.0), (330, "RU0009024277", 541.0), (150, "RU0009024277", 514.0)]
# (дней назад, сумма) — пополнения счёта
DEMO_DEPOSITS = [(730, 1800000)]   # дальше счёт досыпается автоматически, когда не хватает на покупку


def _demo_fmt(x, nd=2):
    return ("%." + str(nd) + "f") % x if x is not None else ""


def demo_rows(today=None):
    """Строки отчёта: [дата, тип, ISIN, тикер, название, кол-во, цена, сумма, валюта, комиссия, НКД] — по возрастанию даты."""
    today = today or date.today()
    info = {i[0]: i for i in DEMO_INSTRUMENTS}
    day = lambda n: today - timedelta(days=n)
    ev = []   # (дата, порядок, строка)

    def nkd_at(isin, d):
        _, _, _, _, cv, per, last = info[isin]
        ago = (today - d).days
        k = 0
        while last + k * per < ago:
            k += 1
        prev = last + k * per                 # дней назад до предыдущего купона
        return cv * (prev - ago) / per

    for n, amt in DEMO_DEPOSITS:
        ev.append((day(n), 0, [day(n), "Пополнение", "", "", "", "", "", amt, "RUB", "", ""]))
    held = defaultdict(list)                  # isin -> [(дата, ±кол-во)]
    for n, op, isin, qty, price in DEMO_TRADES:
        _, tick, name, kind = info[isin][:4]
        d = day(n)
        if kind == "bond":
            nk = nkd_at(isin, d)
            amount = qty * (price / 100.0 * 1000.0 + nk)
        else:
            nk, amount = 0.0, qty * price
        comm = round(amount * 0.0005, 2)
        ev.append((d, 1, [d, op, isin, tick, name, qty, price, round(amount, 2), "RUB", comm, ""]))
        held[isin].append((d, qty if op == "Покупка" else -qty))

    def qty_at(isin, d):
        return sum(q for dd, q in held[isin] if dd <= d)

    income = defaultdict(float)               # год -> облагаемый доход (для НДФЛ)
    for isin, _, name, kind, cv, per, last in DEMO_INSTRUMENTS:
        if kind != "bond":
            continue
        k = 0
        while last + k * per <= 730:
            d = day(last + k * per)
            q = qty_at(isin, d - timedelta(days=1))
            if q > 0:
                amt = round(q * cv, 2)
                ev.append((d, 2, [d, "Купон", isin, info[isin][1], name, "", "", amt, "RUB", "", ""]))
                income[d.year] += amt
            k += 1
    for n, isin, per_share in DEMO_DIVS:
        d = day(n)
        q = qty_at(isin, d - timedelta(days=1))
        if q > 0:
            amt = round(q * per_share, 2)
            ev.append((d, 2, [d, "Дивиденд", isin, info[isin][1], info[isin][2], "", "", amt, "RUB", "", ""]))
            income[d.year] += amt
    for y, inc in sorted(income.items()):     # НДФЛ удерживается в конце года за прошедшие выплаты
        d = date(y, 12, 25)
        if d < today and d >= day(730):
            paid = sum(r[7] for dd, _, r in ev if r[1] in ("Купон", "Дивиденд") and dd.year == y and dd <= d)
            ev.append((d, 3, [d, "НДФЛ", "", "", "", "", "", round(paid * 0.13, 2), "RUB", "", ""]))
    ev.sort(key=lambda e: (e[0], e[1]))
    cash, topups = 0.0, []
    for d, _, r in ev:                        # пополнения «по необходимости», круглыми суммами
        sign = {"Покупка": -1, "Продажа": 1, "НДФЛ": -1}.get(r[1], 1)
        delta = sign * r[7] - (r[9] or 0)
        if cash + delta < 0:
            need = int(-(cash + delta) // 50000 + 1) * 50000
            topups.append((d - timedelta(days=1), 0, [d - timedelta(days=1), "Пополнение", "", "", "", "", "", need, "RUB", "", ""]))
            cash += need
        cash += delta
    ev = sorted(ev + topups, key=lambda e: (e[0], e[1]))
    out = []
    for d, _, r in ev:
        r = list(r)
        r[0] = d.strftime("%d.%m.%Y")
        out.append(["" if v is None else (_demo_fmt(v).replace(".", ",") if isinstance(v, float) else str(v)) for v in r])
    return out


def demo_csv(today=None):
    """Тот же отчёт в виде CSV-текста (формат шаблона импорта)."""
    head = ["Дата", "Тип операции", "ISIN", "Тикер", "Название", "Количество", "Цена", "Сумма", "Валюта", "Комиссия", "НКД"]
    return "\n".join(";".join(r) for r in [head] + demo_rows(today)) + "\n"


class _NoClient:
    ready = False


def demo_active():
    return any(x.get("demo") or x.get("id") == DEMO_ID for x in imports_list())


def demo_remove():
    """Убирает только демо-импорт и его данные. Возвращает True, если что-то было удалено."""
    if not demo_active():
        return False
    store().put("imports", [x for x in imports_list() if not (x.get("demo") or x.get("id") == DEMO_ID)])
    store().ops_clear(DEMO_ID)
    mem_clear()
    return True


def demo_seed():
    """Справочные записи для бумаг демо (иначе без токена нет ни ISIN, ни параметров облигации). Кэш истекает — обновляем при обращении."""
    st = store()
    put = []
    for isin, tick, name, kind, *_ in DEMO_INSTRUMENTS:
        uid = "imp:" + isin
        if st.get("inst:" + uid, ttl=20 * DAY) is None:
            put.append(("inst:" + uid, {"uid": uid, "figi": "", "ticker": tick, "isin": isin, "name": name, "type": kind,
                                        "cur": "rub", "sector": "", "logo": "", "color": "", "country": "RU", "cls": ""}))
        if kind == "bond" and st.get("bond:" + uid, ttl=6 * 3600) is None and isin in DEMO_BOND_PARAMS:
            mat, cpy, fl = DEMO_BOND_PARAMS[isin]
            put.append(("bond:" + uid, {"nominal": 1000.0, "initial": 1000.0, "cur": "rub", "maturity": mat, "call": None,
                                        "placement": None, "cpy": cpy, "aci": 0.0, "floating": fl, "amort": False,
                                        "perpetual": False, "risk": "", "sector": "", "name": name}))
    if put:
        st.put_many(put)


def demo_enable():
    raw = demo_csv().encode("utf-8")
    tables = read_tables("demo.csv", raw)
    mapping = guess_mapping(tables[0][0])
    ops, _ = rows_to_ops([r for r in tables[0][1:] if any(r)], mapping, tables[0][0])
    ops, _ids = finalize_import(_NoClient(), ops, keep_demo=True)
    kinds = {i[0]: "INSTRUMENT_TYPE_" + i[3].upper() for i in DEMO_INSTRUMENTS}
    for o in ops:
        ident = (o.get("instrumentUid") or "").replace("imp:", "")
        if ident in kinds:
            o["instrumentKind"] = kinds[ident]
    store().ops_clear(DEMO_ID)
    store().ops_put(DEMO_ID, ops)
    demo_seed()
    lst = [x for x in imports_list() if x.get("id") != DEMO_ID]
    lst.append({"id": DEMO_ID, "name": DEMO_NAME, "broker": "Демо", "demo": True, "created": utc_now_str(),
                "files": [{"name": "demo.csv", "count": len(ops), "at": utc_now_str()}]})
    store().put("imports", lst)
    mem_clear()
    return len(ops)


def _api_demo_enable(cfg, body):
    n = demo_enable()
    return {"ok": True, "id": DEMO_ID, "count": n}


def _api_demo_disable(cfg, body):
    return {"ok": True, "removed": demo_remove()}


def _api_demo_status(cfg, acc, q, force):
    on = demo_active()
    if on:
        demo_seed()
    return {"active": on, "id": DEMO_ID, "name": DEMO_NAME}


API_GET["/api/demo/status"] = _api_demo_status
API_POST["/api/demo/enable"] = _api_demo_enable
API_POST["/api/demo/disable"] = _api_demo_disable
