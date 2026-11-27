# ═══════════════════════════════ налоги по лотам: ЛДВ, ИИС, перенос убытков, подсказки ═══════════════════════════════
# Справочный расчёт. Брокер как налоговый агент считает сам; это не налоговая консультация.
# Лоты покупок по каждой бумаге и счёту, продажи списываются FIFO; комиссии входят в расходы; НКД при покупке/продаже
# учитывается отдельно (уменьшает/увеличивает купонный доход); частичные погашения (амортизация) уменьшают стоимость лотов.

TAX_LDV_TYPES = ("share", "bond", "etf")
TAX_SKIP_TYPES = ("currency", "futures", "dfa")
TAX_LDV_FROM = date(2014, 1, 1)
TAX_LDV_LIMIT = 3000000.0
TAX_IIS_LIMIT = 400000.0
TAX_IIS3_EXEMPT_LIMIT = 30000000.0   # ст. 219.2 НК РФ: предел освобождаемого финансового результата по ИИС-3 за весь срок
TAX_SETTINGS_KEY = "tax:settings"
TAX_SPREAD = 0.001


def tx_add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return date(d.year + n, 3, 1)


def tx_full_years(d0, d1):
    y = d1.year - d0.year
    if (d1.month, d1.day) < (d0.month, d0.day):
        y -= 1
    return max(0, y)


def tx_ldv_ok(bd, sd):
    """ЛДВ: куплено с 01.01.2014 и продано строго позже третьей годовщины покупки."""
    return bd is not None and bd >= TAX_LDV_FROM and sd > tx_add_years(bd, 3)


def tx_ndfl(base, year):
    """(налог, часть по 13 %, часть по 15 %): до 2021 — 13 %; 2021–2024 — 15 % свыше 5 млн; с 2025 — 15 % свыше 2,4 млн."""
    base = max(0.0, base)
    if year < 2021:
        return base * 0.13, base, 0.0
    thr = 5000000.0 if year < 2025 else 2400000.0
    lo, hi = min(base, thr), max(0.0, base - thr)
    return lo * 0.13 + hi * 0.15, lo, hi


# ── курсы ЦБ ──

_cbr_mem = {}


def tax_cbr_rate(cur, iso):
    """Курс ЦБ РФ за 1 единицу валюты на дату (ISO). Прошлые даты кэшируются навсегда. None — курс недоступен."""
    cur = (cur or "").upper()
    if cur in ("", "RUB"):
        return 1.0
    key = "cbr:" + iso
    tab = _cbr_mem.get(key)
    if tab is None:
        try:
            tab = store().get(key)
        except Exception:  # noqa: BLE001
            tab = None
    if tab is None:
        try:
            d = datetime.strptime(iso, "%Y-%m-%d")
            raw = http_bytes("https://www.cbr.ru/scripts/XML_daily.asp?date_req=" + d.strftime("%d/%m/%Y"), 20).decode("windows-1251", "replace")
        except Exception:  # noqa: BLE001
            return None
        tab = {}
        for m in re.finditer(r"<CharCode>([A-Z]{3})</CharCode>\s*<Nominal>(\d+)</Nominal>\s*<Name>.*?</Name>\s*<Value>([\d,]+)</Value>", raw, re.S):
            try:
                tab[m.group(1)] = float(m.group(3).replace(",", ".")) / int(m.group(2))
            except ValueError:
                pass
        if not tab:
            return None
        _cbr_mem[key] = tab
        if iso < date.today().isoformat():
            try:
                store().put(key, tab)
            except Exception:  # noqa: BLE001
                pass
    return tab.get(cur)


# ── настройки ──

def tax_settings():
    s = {}
    try:
        s = store().get(TAX_SETTINGS_KEY) or {}
    except Exception:  # noqa: BLE001
        pass
    iis = {}
    for k, v in (s.get("iis") or {}).items():
        if isinstance(v, dict):
            iis[str(k)] = {"type": v.get("type") if v.get("type") in ("A", "B", "3") else "", "opened": str(v.get("opened") or "")[:10]}
    carry = {}
    for k, v in (s.get("loss_carry") or {}).items():
        try:
            if int(k) > 1990 and float(v) > 0:
                carry[str(int(k))] = round(float(v), 2)
        except (TypeError, ValueError):
            pass
    return {"iis": iis, "loss_carry": carry, "offset_coupons": bool(s.get("offset_coupons")),
            "ndfl_rate": 15 if str(s.get("ndfl_rate")) in ("15", "0.15") else 13}


def mem_clear_tax():
    with _mem_lock:
        for k in [k for k in _mem if isinstance(k, tuple) and k and k[0] == "taxst"]:
            _mem.pop(k, None)


def tax_settings_save(cfg, body):
    cur = tax_settings()
    if isinstance(body.get("iis"), dict):
        for k, v in body["iis"].items():
            if isinstance(v, dict):
                op = str(v.get("opened") or "")[:10]
                if op:
                    try:
                        datetime.strptime(op, "%Y-%m-%d")
                    except ValueError:
                        raise ApiError("Дата открытия ИИС должна быть в формате ГГГГ-ММ-ДД", 400)
                cur["iis"][str(k)] = {"type": v.get("type") if v.get("type") in ("A", "B", "3") else "", "opened": op}
    if "ndfl_rate" in body:
        cur["ndfl_rate"] = 15 if str(body["ndfl_rate"]).strip() in ("15", "0.15") else 13
    if "offset_coupons" in body:
        cur["offset_coupons"] = bool(body["offset_coupons"])
    if isinstance(body.get("loss_carry"), dict):
        cur["loss_carry"] = {}
        for k, v in body["loss_carry"].items():
            try:
                y, a = int(k), float(str(v).replace(",", ".").replace(" ", ""))
            except (TypeError, ValueError):
                raise ApiError("Убытки прошлых лет: год и сумма должны быть числами", 400)
            if y < 1990 or y > 2100 or a < 0:
                raise ApiError("Некорректный год или сумма убытка", 400)
            if a > 0:
                cur["loss_carry"][str(y)] = round(a, 2)
    store().put(TAX_SETTINGS_KEY, cur)
    mem_clear_tax()
    sync_kick_safe()
    return tax_settings()


# ── движок лотов ──

def tx_sell(lots, q, proceeds, fee, sd, base):
    """Списывает q штук из lots по FIFO (мутирует lots). Возвращает (строки продаж, непокрытый остаток)."""
    rows, left = [], float(q)
    up = proceeds / q if q else 0.0
    uf = fee / q if q else 0.0
    can_ldv = base.get("bucket") == "sec" and base.get("type") in TAX_LDV_TYPES
    while left > 1e-9 and lots:
        lot = lots[0]
        t = min(left, lot["qty"])
        r = dict(base)
        r.update(qty=t, bdate=lot["date"], proceeds=t * up, cost=t * lot["unit"], fee=t * uf)
        r["result"] = r["proceeds"] - r["cost"] - r["fee"]
        ok = can_ldv and not lot.get("blind") and tx_ldv_ok(lot["date"], sd)
        r["ldv"] = bool(ok)
        r["yrs"] = tx_full_years(lot["date"], sd) if ok else 0
        rows.append(r)
        lot["qty"] -= t
        left -= t
        if lot["qty"] <= 1e-9:
            lots.pop(0)
    return rows, left


def tx_inc_new():
    return defaultdict(float)


