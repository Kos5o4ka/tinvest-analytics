# ═══════════════════════════════ модель тарифов брокера (оптимизатор на экране «Комиссии») ═══════════════════════════════
# Модель не зависит от выбранного периода: всегда последние 12 календарных месяцев (включая текущий) до сегодняшнего дня.

# Биржевые фонды Т-Капитала (БПИФ и ЗПИФ рыночных финансовых инструментов) — сверено со списком t-capital-funds.ru/statistics (11.2026)
FM_TCAP_TICKERS = {"TMOS", "TBRU", "TRUR", "TGLD", "TPAY", "TITR", "TLCB", "TOFZ", "TECH", "TSPX", "TBUY", "TRND", "TGRN", "TMON",
                   "TCBR", "TDIV", "TEUR", "TUSD", "TIPO", "TBEU", "TSST", "TFNX", "TEMS", "TIRA", "TSAV", "TCNY", "TBIO",
                   "TPAS", "TEUS", "TRAI", "TSOX", "TSPC"}
FM_NOFEE_TYPES = ("currency", "futures", "option", "sp")     # у валюты, срочного рынка и структурных свои ставки — не тарифная модель акций/облигаций
FM_DELIVERY = {"DELIVERY_BUY", "DELIVERY_SELL"}              # поставка по фьючерсам — комиссии по тарифу нет


def fm_window(now):
    """Начало окна: первое число месяца, отстоящего на 11 месяцев назад. Возвращает (datetime, список 'YYYY-MM')."""
    y, m = now.year, now.month - 11
    while m <= 0:
        y, m = y - 1, m + 12
    start = datetime(y, m, 1)
    yms, yy, mm = [], y, m
    for _ in range(12):
        yms.append("%04d-%02d" % (yy, mm))
        mm += 1
        if mm > 12:
            yy, mm = yy + 1, 1
    return start, yms


def fm_is_nofee(o, info):
    """Сделка без процентной комиссии по тарифу: поставка по фьючерсам, фонды Т-Капитала, валюта/срочный рынок/структурные."""
    if op_type(o) in FM_DELIVERY:
        return "delivery"
    typ = (info or {}).get("type") or o.get("instrumentType") or ""
    if typ in FM_NOFEE_TYPES:
        return typ
    tick = ((info or {}).get("ticker") or o.get("ticker") or "").upper()
    nm = ((info or {}).get("name") or o.get("name") or "").lower()
    if typ in ("etf", "") and (tick in FM_TCAP_TICKERS or "т-капитал" in nm or "t-capital" in nm or ("тинькофф" in nm and typ == "etf")):
        return "tcap"
    return ""


def fm_tariffs(turn, active_mo, port_value):
    """Три стандартных тарифа: комиссия с оборота + абонплата. active_mo — месяцы с операциями; Премиум платится все 12 месяцев."""
    pv = port_value or 0
    t = [
        {"name": "Инвестор", "rate": 0.003, "sub": 0.0, "note": "0,30 % за сделку, без абонплаты"},
        {"name": "Трейдер", "rate": 0.0005, "sub": 0.0 if pv >= 2e6 else 390.0 * active_mo,
         "note": "0,05 % за сделку, 0 ₽/мес (портфель ≥ 2 млн ₽)" if pv >= 2e6 else "0,05 % за сделку + 390 ₽ в месяцы с операциями"},
        {"name": "Премиум", "rate": 0.0004, "sub": 0.0 if pv >= 3e6 else 2990.0 * 12,
         "note": "0,04 % за сделку, 0 ₽/мес (портфель ≥ 3 млн ₽)" if pv >= 3e6 else "0,04 % за сделку + 2 990 ₽/мес"},
    ]
    for x in t:
        x["fee"] = turn * x["rate"]
        x["cost"] = x["fee"] + x["sub"]
    return t


def fee_model(ops, names, portfolio_value, now=None, t_accs=None):
    """Модель тарифа по последним 12 мес.: оборот только по биржевым сделкам с процентной комиссией, факт и оценка текущего тарифа.
    t_accs — id счетов Т-Инвестиций: операции остальных счетов (отчёты других брокеров) в модель не попадают."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if t_accs is not None:
        t_accs = set(t_accs)
        ops = [o for o in ops if o.get("_acc") in t_accs]
    start, yms = fm_window(now)
    accs_bf = {o.get("_acc") for o in ops if classify(o.get("type")) == "fee_broker"}
    turn = excl = paid_broker = paid_service = 0.0
    by_ym = defaultdict(float)
    excl_by = defaultdict(float)
    for o in ops:
        dt = parse_dt(o.get("date"))
        if dt < start or dt > now:
            continue
        kind = classify(o.get("type"))
        pay, cur = q2d(o.get("payment")), cur_of(o.get("payment"))
        if cur != "rub":
            continue
        if kind in ("buy", "sell"):
            info = names.get(o.get("instrumentUid") or o.get("figi") or "") or {}
            why = fm_is_nofee(o, info)
            amt = float(abs(pay))
            if why:
                excl += amt
                excl_by[why] += amt
            else:
                turn += amt
                by_ym[dt.strftime("%Y-%m")] += amt
            comm = q2d(o.get("commission"))
            if comm and o.get("_acc") not in accs_bf:
                paid_broker += float(abs(comm))
        elif kind == "fee_broker":
            paid_broker += float(-pay if pay < 0 else pay)
        elif kind == "fee_service":
            paid_service += float(-pay)
    active = sum(1 for m in yms if by_ym.get(m, 0) > 0)
    tariffs = fm_tariffs(turn, active, portfolio_value)
    best = min(tariffs, key=lambda x: x["cost"]) if turn > 0 else None
    paid = paid_broker + paid_service
    rate = paid_broker / turn if turn > 0 else None
    current = None
    if rate is not None and paid_broker > 0:
        if paid_service / 12 >= 1500:
            current = "Премиум"
        elif rate >= 0.0017:
            current = "Инвестор"
        else:
            current = "Трейдер"
    below = bool(best and paid < best["cost"] * 0.9)
    save = max(0.0, paid - best["cost"]) if best else 0.0
    return {"from": start.date().isoformat(), "to": now.date().isoformat(), "months": 12, "active_months": active,
            "turnover": turn, "excluded": excl, "excluded_by": dict(excl_by), "paid_broker": paid_broker,
            "paid_service": paid_service, "paid": paid, "eff_rate": rate, "current": current,
            "tariffs": tariffs, "best": best["name"] if best else None, "best_cost": best["cost"] if best else None,
            "save": save, "below_model": below, "port_value": portfolio_value or 0}


# ═══════════════════════════════ брокеры счетов и тарифы других брокеров ═══════════════════════════════

BROKERS = {"tinvest": "Т-Инвестиции", "vtb": "ВТБ", "sber": "Сбер", "finam": "Финам", "bcs": "БКС", "alfa": "Альфа-Инвестиции",
           "gpb": "Газпромбанк", "open": "Открытие", "uralsib": "Уралсиб", "psb": "ПСБ", "freedom": "Фридом Финанс",
           "other": "Другой брокер"}
# порядок важен: первое совпадение; латиница коротких названий — целым словом
BROKER_PATTERNS = (
    ("tinvest", r"т-?банк|t-?bank|тинькофф|тинькоф|tinkoff|т-?инвест|t-?invest|т-?капитал"),
    ("vtb", r"втб|\bvtb\b"),
    ("sber", r"сбер|\bsber"),
    ("finam", r"финам|finam"),
    ("bcs", r"бкс|\bbcs\b|broker\.ru"),
    ("alfa", r"альфа|\balfa"),
    ("gpb", r"газпромбанк|\bгпб\b|gazprombank"),
    ("open", r"открытие|open-?broker|открытие брокер"),
    ("uralsib", r"уралсиб|uralsib"),
    ("psb", r"\bпсб\b|промсвязьбанк|\bpsb\b"),
    ("freedom", r"фридом|freedom|\bффин\b|ffin"),
)
IMPORT_FORMAT_BROKER = {"tbank": "tinvest", "vtb": "vtb"}

# Тарифы других брокеров: только проверенные по сайту брокера, без выдуманных цифр. Ставки — % от суммы сделки,
# для ступенчатых тарифов — первая (наименьшая по обороту) ступень. monthly_mode: "active" — плата в месяцы со сделками, "always" — каждый месяц.
BROKER_TARIFFS = {
    "vtb": {"name": "ВТБ", "tariffs": [
        {"id": "my_online_base", "name": "Мой онлайн (уровень Базовый)", "rate_pct": {"shares": 0.25, "bonds": 0.25},
         "monthly_fee": 0, "monthly_mode": "active",
         "notes": "0,25 % от оборота за день; плюс комиссия биржи для заявок-тейкеров 0,03 % (по облигациям до 0,015 %)",
         "source_url": "https://www.vtb.ru/personal/investicii/tarify/", "as_of": "2026-11"},
        {"id": "my_online_silver", "name": "Мой онлайн (уровень Серебряный)", "rate_pct": {"shares": 0.20, "bonds": 0.20},
         "monthly_fee": 0, "monthly_mode": "active",
         "notes": "0,20 % от оборота за день при уровне Серебряный программы лояльности ВТБ",
         "source_url": "https://www.vtb.ru/personal/investicii/tarify/", "as_of": "2026-11"},
        {"id": "my_online_gold", "name": "Мой онлайн (уровень Золотой)", "rate_pct": {"shares": 0.15, "bonds": 0.15},
         "monthly_fee": 0, "monthly_mode": "active",
         "notes": "0,15 % от оборота за день при уровне Золотой программы лояльности ВТБ",
         "source_url": "https://www.vtb.ru/personal/investicii/tarify/", "as_of": "2026-11"},
        {"id": "my_online_priv", "name": "Мой онлайн привилегия", "rate_pct": {"shares": 0.10, "bonds": 0.10},
         "monthly_fee": 0, "monthly_mode": "active",
         "notes": "0,1 % при уровне Изумруд; 0,09 % Сапфир; 0,085 % Рубин; 0,08 % Бриллиант — модель считает по 0,1 %",
         "source_url": "https://www.vtb.ru/personal/investicii/tarify/", "as_of": "2026-11"},
        {"id": "my_online_prime", "name": "Мой онлайн прайм", "rate_pct": {"shares": 0.06, "bonds": 0.06},
         "monthly_fee": 0, "monthly_mode": "active", "notes": "0,06 % от оборота за день",
         "source_url": "https://www.vtb.ru/personal/investicii/tarify/", "as_of": "2026-11"},
        {"id": "professional", "name": "Профессиональный", "rate_pct": {"shares": 0.045, "bonds": 0.045},
         "monthly_fee": 390, "monthly_mode": "active",
         "notes": "0,045 % при обороте за день до 1 млн ₽ (дальше ниже); 390 ₽ в месяц с первой сделкой, если акций ВТБ меньше 300",
         "source_url": "https://www.vtb.ru/personal/investicii/tarify/", "as_of": "2026-11"},
    ]},
    "sber": {"name": "Сбер", "tariffs": []},
    "finam": {"name": "Финам", "tariffs": []},
    "bcs": {"name": "БКС", "tariffs": []},
    "alfa": {"name": "Альфа-Инвестиции", "tariffs": []},
    "gpb": {"name": "Газпромбанк", "tariffs": []},
    "open": {"name": "Открытие", "tariffs": []},
    "uralsib": {"name": "Уралсиб", "tariffs": []},
    "psb": {"name": "ПСБ", "tariffs": []},
    "freedom": {"name": "Фридом Финанс", "tariffs": []},
    "other": {"name": "Другой брокер", "tariffs": []},
}


def broker_guess(text):
    """Канонический id брокера по свободному тексту (название брокера, счёта, файла, шапки отчёта); иначе 'other'."""
    t = str(text or "").lower().replace("ё", "е")
    for bid, pat in BROKER_PATTERNS:
        if re.search(pat, t):
            return bid
    return "other"


def broker_of_account(acc):
    """(id, название) брокера счёта. acc — счёт из list_accounts или запись импорта из store().get("imports")."""
    acc = acc or {}
    if acc.get("kind") == "tinvest":
        bid = "tinvest"
    elif acc.get("broker_id") in BROKERS:
        bid = acc["broker_id"]
    elif acc.get("demo") or acc.get("id") == "imp-demo":
        bid = "tinvest"                      # демо-портфель показывает возможности для счёта Т-Инвестиций
    elif acc.get("format") in IMPORT_FORMAT_BROKER:
        bid = IMPORT_FORMAT_BROKER[acc["format"]]
    elif not str(acc.get("id") or "").startswith("imp-") and acc.get("kind") != "import":
        bid = "tinvest"
    else:
        bid = broker_guess(" ".join(str(acc.get(k) or "") for k in ("broker", "type", "name")))
    return bid, BROKERS[bid]


def broker_detect_import(filename, raw, fmt, broker_text="", name=""):
    """Брокер нового импорта: формат отчёта → текст пользователя → имя файла и шапка таблиц (строки до заголовка операций)."""
    if fmt in IMPORT_FORMAT_BROKER:
        return IMPORT_FORMAT_BROKER[fmt]
    bid = broker_guess((broker_text or "") + " " + (name or ""))
    if bid != "other":
        return bid
    bid = broker_guess(filename)
    if bid != "other" or not raw:
        return bid
    try:
        tables = read_tables(filename, raw)
        hit = find_header(tables)
    except Exception:  # noqa: BLE001
        return "other"
    ti, ri = (hit[1], hit[2]) if hit else (-1, 15)
    parts = []
    for i, t in enumerate(tables[:6]):
        lim = ri if i == ti else (15 if ti < 0 or i < ti else 0)
        for r in t[:min(lim, 15)]:
            parts.extend(str(c) for c in r if c)
    return broker_guess(" ".join(parts)[:20000])


def broker_tariff(bid, tid):
    return next((x for x in (BROKER_TARIFFS.get(bid) or {}).get("tariffs") or [] if x["id"] == tid), None)


def fm_inst_type(o, info):
    typ = (info or {}).get("type") or o.get("instrumentType") or ""
    if not typ:
        k = str(o.get("instrumentKind") or "")
        typ = k.replace("INSTRUMENT_TYPE_", "").lower() if k.startswith("INSTRUMENT_TYPE_") else ""
    return typ


def broker_account_fees(acc_id, ops, names, tariff=None, now=None):
    """Комиссии счёта другого брокера за последние 12 мес.: факт и эффективная ставка; с выбранным тарифом — модель тарифа."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    start, yms = fm_window(now)
    t_sh = t_bd = paid_broker = paid_service = 0.0
    by_ym = defaultdict(float)
    for o in ops:
        if o.get("_acc") != acc_id:
            continue
        dt = parse_dt(o.get("date"))
        if dt < start or dt > now:
            continue
        kind = classify(o.get("type"))
        pay = q2d(o.get("payment"))
        if cur_of(o.get("payment")) != "rub":
            continue
        if kind in ("buy", "sell"):
            comm = q2d(o.get("commission"))
            if comm:
                paid_broker += float(abs(comm))
            info = names.get(o.get("instrumentUid") or o.get("figi") or "") or {}
            typ = fm_inst_type(o, info)
            if op_type(o) in FM_DELIVERY or typ in FM_NOFEE_TYPES:
                continue
            amt = float(abs(pay))
            if typ == "bond":
                t_bd += amt
            else:
                t_sh += amt
            by_ym[dt.strftime("%Y-%m")] += amt
        elif kind == "fee_broker":
            paid_broker += float(-pay if pay < 0 else pay)
        elif kind == "fee_service":
            paid_service += float(-pay)
    turn = t_sh + t_bd
    active = sum(1 for m in yms if by_ym.get(m, 0) > 0)
    res = {"from": start.date().isoformat(), "to": now.date().isoformat(), "turnover": turn, "turnover_shares": t_sh,
           "turnover_bonds": t_bd, "active_months": active, "paid_broker": paid_broker, "paid_service": paid_service,
           "paid": paid_broker + paid_service, "eff_rate": paid_broker / turn if turn > 0 else None, "model": None}
    if tariff:
        rp = tariff.get("rate_pct") or {}
        fee = t_sh * float(rp.get("shares") or 0) / 100 + t_bd * float(rp.get("bonds") or 0) / 100
        mo = active if tariff.get("monthly_mode") == "active" else 12
        sub = float(tariff.get("monthly_fee") or 0) * mo
        res["model"] = {"id": tariff["id"], "name": tariff["name"], "fee": fee, "sub": sub, "cost": fee + sub,
                        "diff": res["paid"] - (fee + sub), "notes": tariff.get("notes") or "",
                        "source_url": tariff.get("source_url") or "", "as_of": tariff.get("as_of") or ""}
    return res
