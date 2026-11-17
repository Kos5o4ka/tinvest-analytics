# ═══════════════════════════ деньги и базис: фонды ликвидности и базис фьючерсов (cash & carry) ═══════════════════════════
# Фонды ликвидности: дневные цены паёв (свечи ISS) -> реализованная доходность в годовом выражении, отставание от ставки RUSFAR
# (или ключевой), доходность после НДФЛ для заданного срока. Базис: фьючерсы FORTS (ISS) против спота; дивиденды до экспирации.
# Все числа — модельные оценки по заявленным допущениям; процентные значения — в процентных пунктах (12.5 = 12,5 %).
# Эндпоинты: /api/mm/funds, /api/mm/basis. Префикс имён mm_ / MM_.

MM_WINDOWS = (("1m", 30), ("3m", 91), ("6m", 182), ("1y", 365))
MM_FUND_SEED = ("LQDT", "SBMM", "AKMM", "TMON", "AKMP", "BCSD", "FMMM", "MONY", "OLIQ", "PSMM", "CASH", "FINC", "TSAV", "AMNR", "SILA", "SCLI", "GOOD")
MM_FUND_IN = re.compile(r"денеж|ликвид|сберегат|накопит|ежедневн", re.I)
MM_FUND_OUT = re.compile(r"юан|золот|валют|долл|евро|облиг|usd|cny|поток|акци|дивиденд", re.I)   # «Денежный поток» — фонд акций
MM_OZ_G = 31.1034768                                   # граммов в тройской унции
MM_ISS = "https://iss.moex.com/iss/"
MM_BASIS_TTL = 600
MM_BASIS_SANITY = 15.0                                 # |базис| больше стольких % — единицы не сошлись, строка скрывается
MM_UNDERLYINGS = (
    {"asset": ("SBRF",), "name": "Сбербанк (акции)", "kind": "share", "spot": "SBER"},
    {"asset": ("GAZR",), "name": "Газпром (акции)", "kind": "share", "spot": "GAZP"},
    {"asset": ("LKOH",), "name": "Лукойл (акции)", "kind": "share", "spot": "LKOH"},
    {"asset": ("GOLD",), "name": "Золото (унция)", "kind": "gold", "spot": "GLDRUB_TOM"},
    {"asset": ("Si",), "name": "Доллар США", "kind": "fx", "spot": "USD000UTSTOM"},
    {"asset": ("CNY", "CR"), "name": "Юань", "kind": "fx", "spot": "CNYRUB_TOM"},
)
MM_NOTE_FUNDS = ("Доходность считается по изменению цены пая (фонды ликвидности накапливают доход в цене и выплат не делают). "
                 "Отставание от ставки включает комиссии фонда и проскальзывание, а также разницу между ставкой RUSFAR и фактической доходностью портфеля фонда; "
                 "отдельно размер комиссий программа не определяет. Прошлая доходность не гарантирует будущую.")
MM_NOTE_BASIS = ("Модель: покупка базового актива и продажа фьючерса, удержание до экспирации. Не учтены комиссии, налоги, проскальзывание, "
                 "ставка по обеспечению и риск изменения гарантийного обеспечения; дивиденды — только уже объявленные (дата отсечки до экспирации). "
                 "Доходность на капитал с обеспечением консервативно считает, что гарантийное обеспечение (ГО) вносится сверх стоимости актива.")


def mm_f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def mm_d(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# ── расчёты (чистые функции) ──

def mm_ann(p0, p1, days):
    """Годовая доходность по росту цены, %: (P1/P0)^(365/дни) − 1. Дневная капитализация подразумевается самим законом роста цены."""
    if not p0 or not p1 or p0 <= 0 or p1 <= 0 or not days or days <= 0:
        return None
    return ((p1 / p0) ** (365.0 / days) - 1) * 100


def mm_window_return(closes, days, max_gap=7):
    """closes — [(ISO-дата, цена)] по возрастанию. Окно в days календарных дней, оканчивающееся последней точкой.
    Начальная точка — последнее закрытие не позже (конец − days); если истории не хватает (первая точка позже этой даты
    больше чем на max_gap дней) — None. Возвращает {ret, total, days, start, end} (ret — годовая, %)."""
    pts = [(mm_d(d), p) for d, p in closes if mm_d(d) and mm_f(p)]
    if len(pts) < 2:
        return None
    end_d, p1 = pts[-1]
    target = end_d - timedelta(days=days)
    p0 = None
    for d, p in pts:
        if d <= target:
            p0 = (d, p)
        else:
            break
    if p0 is None:
        first = pts[0]
        if (first[0] - target).days > max_gap or first[0] >= end_d:
            return None
        p0 = first
    d0, v0 = p0
    n = (end_d - d0).days
    if n < max(5, days // 3):
        return None
    return {"ret": mm_ann(v0, p1, n), "total": (p1 / v0 - 1) * 100, "days": n, "start": d0.isoformat(), "end": end_d.isoformat()}


def mm_rate_factor(rates, d0, d1):
    """Накопленный множитель при размещении по ставке (% годовых, ежедневная капитализация на календарный день) от d0 (искл.) до d1 (вкл.).
    rates — [(ISO-дата, ставка %)] по возрастанию; между точками ставка переносится вперёд. None — ставки на d0 нет в данных."""
    rs = [(mm_d(d), mm_f(v)) for d, v in rates]
    rs = [(d, v) for d, v in rs if d and v is not None]
    if not rs or rs[0][0] > d0 + timedelta(days=7):
        return None
    j, cur, f, d = 0, rs[0][1], 1.0, d0
    while j < len(rs) and rs[j][0] <= d0:
        cur = rs[j][1]
        j += 1
    while d < d1:
        d += timedelta(days=1)
        while j < len(rs) and rs[j][0] <= d:
            cur = rs[j][1]
            j += 1
        f *= 1 + cur / 100.0 / 365.0
    return f


def mm_bench_ann(rates, d0, d1):
    """Годовая доходность ставки за окно [d0, d1] с ежедневной капитализацией, %."""
    n = (d1 - d0).days
    f = mm_rate_factor(rates, d0, d1)
    if f is None or n <= 0:
        return None
    return (f ** (365.0 / n) - 1) * 100


def mm_gap(fund_ann, bench_ann):
    """Отставание от ставки, п.п.: доходность фонда минус ставка (отрицательное — фонд отстаёт). Неявные издержки (комиссия, проскальзывание)."""
    if fund_ann is None or bench_ann is None:
        return None
    return fund_ann - bench_ann


def mm_after_tax(amount, days, gross_ann, fee_pct=0.0, year=None):
    """Результат вложения amount ₽ на days календарных дней при годовой доходности gross_ann (эффективная, %).
    Комиссия брокера fee_pct % берётся с оборота покупки и продажи; налог по tx_ndfl (13 %, 15 % с превышения порога) с дохода
    после вычета комиссий; ЛДВ — если срок больше трёх лет: освобождается доход до 3 млн ₽ за каждый полный год владения (приближённо)."""
    if not amount or amount <= 0 or not days or days <= 0 or gross_ann is None or gross_ann <= -100:
        return None
    year = year or date.today().year
    f = max(0.0, fee_pct or 0.0) / 100.0
    invested = amount / (1 + f)
    proceeds = invested * (1 + gross_ann / 100.0) ** (days / 365.0)
    sell_fee = proceeds * f
    base = proceeds - sell_fee - amount
    full_years = days // 365
    ldv = days > 3 * 365
    exempt = 3e6 * full_years if ldv else 0.0
    taxable = max(0.0, base - exempt)
    tax = tx_ndfl(taxable, year)[0]
    net = proceeds - sell_fee - tax
    net_total = net / amount - 1
    ann = ((net / amount) ** (365.0 / days) - 1) * 100 if net > 0 else None
    return {"amount": amount, "days": days, "gross_gain": proceeds - invested, "fees": (amount - invested) + sell_fee, "tax": tax,
            "net_gain": net - amount, "net_total_pct": net_total * 100, "net_ann": ann, "ldv": ldv, "ldv_exempt": min(exempt, max(0.0, base))}


def mm_contract_rub(price, step_price, min_step):
    """Стоимость контракта в рублях по котировке: цена × (стоимость шага / шаг цены). Для акций это сама цена (шаг 1 ₽ = 1 ₽),
    для юаня (шаг 0,001 = 1 ₽) — цена × 1000, для золота и Si — через курс, заложенный биржей в стоимость шага."""
    p, sp, ms = mm_f(price), mm_f(step_price), mm_f(min_step)
    if p is None or not sp or not ms:
        return None
    return p * sp / ms


def mm_basis(fut_rub, lot, spot_unit, days, divs=0.0, margin=None):
    """Cash & carry: купить lot единиц базового актива по spot_unit ₽ за единицу и продать фьючерс (fut_rub ₽ за контракт).
    divs — ожидаемые дивиденды на единицу до экспирации. Базис = F − S·lot; доходность годовых по простой формуле (F/S − 1)·365/дни.
    Доходность на капитал с ГО: прибыль / (стоимость актива + ГО)."""
    if not fut_rub or not lot or not spot_unit or not days or days <= 0 or spot_unit <= 0:
        return None
    f_unit = fut_rub / lot
    spot_val = spot_unit * lot
    basis = fut_rub - spot_val
    basis_pct = (f_unit / spot_unit - 1) * 100
    k = 365.0 / days
    raw_ann = basis_pct * k
    div_total = (divs or 0.0) * lot
    pnl = basis + div_total
    adj_ann = pnl / spot_val * 100 * k
    cap = spot_val + (margin or 0.0)
    roc_ann = pnl / cap * 100 * k if margin else None
    return {"f_unit": f_unit, "spot_unit": spot_unit, "basis": basis, "basis_pct": basis_pct, "ann_raw": raw_ann, "div_unit": divs or 0.0,
            "div_total": div_total, "ann_adj": adj_ann, "pnl": pnl, "capital": cap, "ann_roc": roc_ann, "days": days}


# ── фонды: поиск, история, ставки ──

def mm_fund_names():
    """{тикер: название} кандидатов по названию в списке бумаг ISS (фонды денежного рынка, рублёвые), кэш на сутки; при сбое — известные тикеры."""
    key = "mm_fund_names_v1"
    hit = store().get(key, 24 * 3600)
    if hit:
        return hit
    out = {}
    try:
        j = json.loads(http_text(MM_ISS + "engines/stock/markets/shares/securities.json?iss.meta=off&iss.only=securities&securities.columns=SECID,SECNAME,SHORTNAME", timeout=40))
        for r in _iss_table(j, "securities"):
            sid, nm = r.get("SECID") or "", r.get("SECNAME") or ""
            if sid and len(sid) <= 5 and not sid.startswith("RU0") and MM_FUND_IN.search(nm) and not MM_FUND_OUT.search(nm):
                out[sid] = nm
            elif sid in MM_FUND_SEED:
                out[sid] = nm or sid
    except Exception:  # noqa: BLE001
        return {s: s for s in MM_FUND_SEED[:4]}
    for s in MM_FUND_SEED[:4]:
        out.setdefault(s, s)
    if out:
        store().put(key, out)
    return out


def mm_rate_series():
    """(rusfar, key): RUSFAR [(дата, %)] и ключевая ставка [(дата, %)]; недоступное — []."""
    rf, kr = [], []
    try:
        rf = sorted(bench_history("RUSFAR", (date.today() - timedelta(days=430)).isoformat()).items())
    except Exception:  # noqa: BLE001
        pass
    try:
        kr = [(d, v) for d, v in key_rate_series()]
    except Exception:  # noqa: BLE001
        pass
    return rf, kr


def mm_fund_row(secid, name):
    try:
        cs = stock_candles(secid, 24, 400)
    except Exception:  # noqa: BLE001
        return None
    closes = [(c["t"], c["c"]) for c in cs if c.get("c")]
    if len(closes) < 10:
        return None
    return {"secid": secid, "name": name, "closes": closes}


def mm_funds_base():
    """Тяжёлая часть (сеть): список фондов с доходностями по окнам и отставанием от ставки. Кэш в памяти 10 минут."""
    key = ("mm_funds_base",)
    hit = mem_get(key, 600)
    if hit is not None:
        return hit
    with key_lock("mm_funds_base"):
        hit = mem_get(key, 600)
        if hit is not None:
            return hit
        names = mm_fund_names()
        rows = [r for r in pool_map(lambda kv: mm_fund_row(kv[0], kv[1]), sorted(names.items()), workers=6) if r]
        rf, kr = mm_rate_series()
        out = []
        for r in rows:
            last = mm_d(r["closes"][-1][0])
            if not last or (date.today() - last).days > 10:
                continue
            wins = {}
            for wk, n in MM_WINDOWS:
                w = mm_window_return(r["closes"], n)
                if w and w["ret"] is not None:
                    d0, d1 = mm_d(w["start"]), mm_d(w["end"])
                    b_rf, b_kr = mm_bench_ann(rf, d0, d1), mm_bench_ann(kr, d0, d1)
                    b, bn = (b_rf, "RUSFAR") if b_rf is not None else (b_kr, "ключевая ставка")
                    w.update(bench=b, bench_name=bn if b is not None else None, gap=mm_gap(w["ret"], b),
                             key=b_kr, rusfar=b_rf)
                wins[wk] = w
            if not any(wins.values()):
                continue
            out.append({"secid": r["secid"], "name": r["name"], "last": r["closes"][-1][1], "last_date": r["closes"][-1][0], "wins": wins})
        out.sort(key=lambda x: -((x["wins"].get("3m") or {}).get("ret") or -999))
        return mem_put(key, {"funds": out, "rusfar": rf[-1][1] if rf else None, "rusfar_date": rf[-1][0] if rf else None,
                             "key": kr[-1][1] if kr else None, "key_date": kr[-1][0] if kr else None})


def mm_funds_payload(q):
    def num(k, d, lo, hi):
        v = mm_f(str(q.get(k, "")).replace(",", "."))
        return d if v is None else max(lo, min(hi, v))
    amount = num("amount", 1000000.0, 1000.0, 1e10)
    days = int(num("days", 365, 1, 3650))
    fee = num("fee", 0.0, 0.0, 5.0)
    win = q.get("win") if q.get("win") in ("1m", "3m", "6m", "1y") else "3m"
    base = mm_funds_base()
    funds = base["funds"]
    if not funds:
        return {"error": "Не удалось загрузить историю цен фондов с Мосбиржи. Повторите позже.", "funds": []}
    fund = (q.get("fund") or "").strip().upper()
    sel = next((f for f in funds if f["secid"] == fund), None) or next((f for f in funds if f["secid"] == "LQDT"), funds[0])
    key_now = base["key"]
    save = num("save", (key_now - 2.0) if key_now is not None else 10.0, 0.0, 100.0)
    year = date.today().year
    fw = (sel["wins"].get(win) or next((w for w in sel["wins"].values() if w), None))
    cmp_rows = []

    def add(kind, title, gross, note=""):
        at = mm_after_tax(amount, days, gross, fee if kind in ("fund", "ofz") else 0.0, year) if gross is not None else None
        cmp_rows.append({"kind": kind, "title": title, "gross": gross, "after": at, "note": note})

    if fw:
        add("fund", "Фонд %s (доходность за %s)" % (sel["secid"], {"1m": "месяц", "3m": "3 месяца", "6m": "6 месяцев", "1y": "год"}[win]), fw["ret"],
            "реализованная доходность, прошлое не гарантирует будущее")
    add("save", "Накопительный счёт (ставка введена вами)", save, "ставка принята эффективной годовой; необлагаемый лимит процентов не учтён")
    for y in (0.25, 0.5, 1.0):
        v = None
        for _ in range(2):
            try:
                v = kbd_at(y)
            except Exception:  # noqa: BLE001
                v = None
            if v is not None:
                break
        add("ofz", "ОФЗ со сроком до %s г. (кривая бескупонной доходности)" % ("%g" % y).replace(".", ","), v,
            "ориентир по КБД: реальные выпуски торгуются с отклонением; купонный доход и цена облагаются так же")
    if base["rusfar"] is not None:
        add("rate", "Ставка RUSFAR (ориентир)", base["rusfar"], "не инструмент: показывает уровень денежного рынка")
    if key_now is not None:
        add("rate", "Ключевая ставка (ориентир)", key_now, "не инструмент")
    # ставки-ориентиры без комиссии
    return {"funds": [{"secid": f["secid"], "name": f["name"], "last": f["last"], "last_date": f["last_date"], "wins": f["wins"]} for f in funds],
            "selected": sel["secid"], "win": win, "amount": amount, "days": days, "fee": fee, "save": save,
            "rusfar": base["rusfar"], "rusfar_date": base["rusfar_date"], "key": key_now, "key_date": base["key_date"],
            "compare": cmp_rows, "note": MM_NOTE_FUNDS, "ldv_note": "Льгота долгосрочного владения (ЛДВ) применяется при владении более трёх лет, до 3 млн ₽ дохода за каждый полный год; "
                                                                      "выше порога годового дохода (в 2025 и позже — 2,4 млн ₽) налог 15 % вместо 13 %."}


# ── базис фьючерсов ──

def mm_pick_price(md):
    """Цена контракта из marketdata: LAST при наличии сделок сегодня, иначе расчётная цена, иначе None. Возвращает (цена, источник)."""
    last, settle, vol = mm_f(md.get("LAST")), mm_f(md.get("SETTLEPRICE")), mm_f(md.get("VOLTODAY")) or 0
    if last and vol > 0:
        return last, "последняя сделка"
    if settle:
        return settle, "расчётная цена"
    return None, None


def mm_nearest(secs, md, assets, today):
    """Два ближайших ещё не истёкших срочных контракта по коду актива -> [{secid, expiry, ...}]."""
    rows = []
    for s in secs:
        if s.get("ASSETCODE") not in assets:
            continue
        exp = mm_d(s.get("LASTTRADEDATE"))
        if not exp or exp.year > 2090 or exp <= today:
            continue
        m = md.get(s.get("SECID")) or {}
        price, src = mm_pick_price(m)
        if price is None:
            price, src = mm_f(s.get("PREVSETTLEPRICE")), "прошлая расчётная цена"
        rows.append({"secid": s["SECID"], "short": s.get("SHORTNAME") or s["SECID"], "expiry": exp, "price": price, "src": src,
                     "lot": mm_f(s.get("LOTVOLUME")), "margin": mm_f(s.get("INITIALMARGIN")), "step_price": mm_f(s.get("STEPPRICE")),
                     "min_step": mm_f(s.get("MINSTEP")), "oi": mm_f(m.get("OPENPOSITION"))})
    rows.sort(key=lambda r: r["expiry"])
    return rows[:2]


def mm_spots():
    """Спот: {тикер: цена ₽} — акции TQBR и валютная секция (CETS: USD000UTSTOM, CNYRUB_TOM, GLDRUB_TOM за грамм)."""
    out = {}
    try:
        for r in stocks_universe():
            if r["secid"] in ("SBER", "GAZP", "LKOH"):
                out[r["secid"]] = r["price"]
    except Exception:  # noqa: BLE001
        pass
    try:
        j = json.loads(http_text(MM_ISS + "engines/currency/markets/selt/boards/CETS/securities.json?iss.meta=off&iss.only=marketdata"
                                 "&marketdata.columns=SECID,LAST,WAPRICE,MARKETPRICE", timeout=30))
        for r in _iss_table(j, "marketdata"):
            if r["SECID"] in ("USD000UTSTOM", "CNYRUB_TOM", "GLDRUB_TOM"):
                v = mm_f(r.get("LAST")) or mm_f(r.get("MARKETPRICE")) or mm_f(r.get("WAPRICE"))
                if v:
                    out[r["SECID"]] = v
    except Exception:  # noqa: BLE001
        pass
    return out


def mm_divs_until(secid, price, today, expiry, cfg=None):
    """Объявленные дивиденды с датой фиксации в (сегодня, экспирация], ₽ на акцию: (сумма, [{record, value}], есть_ли_данные_о_дивидендах)."""
    try:
        uid = (stk_api_map(cfg) or {}).get(secid, {}).get("uid") if cfg and (cfg.get("token") or "").strip() else None
        res = stock_dividends(secid, price, uid, cfg)
    except Exception:  # noqa: BLE001
        return 0.0, [], False
    its = res.get("items") or []
    items = [{"record": x["record"], "value": x["value"]} for x in its
             if x.get("cur") in ("RUB", "RUR") and today.isoformat() < x["record"] <= expiry.isoformat()]
    return sum(i["value"] for i in items), sorted(items, key=lambda i: i["record"]), bool(its)


def mm_basis_build(secs, md, spots, rate_ref, today, divs_fn=None):
    """Строки базиса по набору базовых активов. Контракты с несошедшимися единицами (|базис| > MM_BASIS_SANITY %) пропускаются."""
    rows, skipped = [], []
    divs_fn = divs_fn or mm_divs_until
    for u in MM_UNDERLYINGS:
        futs = mm_nearest(secs, md, u["asset"], today)
        spot = spots.get(u["spot"])
        if not futs or not spot:
            skipped.append("%s: нет данных (%s)" % (u["name"], "котировки спота" if not spot else "контрактов"))
            continue
        spot_unit = spot * MM_OZ_G if u["kind"] == "gold" else spot
        for f in futs:
            fr = mm_contract_rub(f["price"], f["step_price"], f["min_step"])
            days = (f["expiry"] - today).days
            if fr is None or not f["lot"] or days < 1:
                continue
            dsum, ditems, dknown = divs_fn(u["spot"], spot, today, f["expiry"]) if u["kind"] == "share" else (0.0, [], True)
            b = mm_basis(fr, f["lot"], spot_unit, days, dsum, f["margin"])
            if not b:
                continue
            if abs(b["basis_pct"]) > MM_BASIS_SANITY:
                skipped.append("%s %s: базис %.1f %% — единицы контракта не удалось согласовать, строка скрыта" % (u["name"], f["short"], b["basis_pct"]))
                continue
            b.update(asset=u["name"], kind=u["kind"], secid=f["secid"], short=f["short"], expiry=f["expiry"].isoformat(), price=f["price"], price_src=f["src"],
                     lot=f["lot"], margin=f["margin"], contract_rub=fr, divs=ditems, divs_known=dknown,
                     unit={"share": "акция", "gold": "унция", "fx": "ед. валюты"}[u["kind"]],
                     excess=(b["ann_adj"] - rate_ref) if rate_ref is not None else None)
            rows.append(b)
    return rows, skipped


def mm_basis_payload(force=False, cfg=None):
    key = ("mm_basis",)
    if not force:
        hit = mem_get(key, MM_BASIS_TTL)
        if hit is not None:
            return hit
    with key_lock("mm_basis"):
        if not force:
            hit = mem_get(key, MM_BASIS_TTL)
            if hit is not None:
                return hit
        try:
            j = json.loads(http_text(MM_ISS + "engines/futures/markets/forts/securities.json?iss.meta=off&iss.only=securities,marketdata"
                                     "&securities.columns=SECID,SHORTNAME,ASSETCODE,LASTTRADEDATE,PREVSETTLEPRICE,LOTVOLUME,INITIALMARGIN,MINSTEP,STEPPRICE"
                                     "&marketdata.columns=SECID,LAST,SETTLEPRICE,VOLTODAY,OPENPOSITION", timeout=45))
            secs = _iss_table(j, "securities")
            md = {r["SECID"]: r for r in _iss_table(j, "marketdata")}
        except Exception as e:  # noqa: BLE001
            return {"error": "Не удалось загрузить срочный рынок Мосбиржи: %s" % e, "rows": [], "note": MM_NOTE_BASIS}
        spots = mm_spots()
        rf, kr = mm_rate_series()
        today = date.today()
        rusfar = rf[-1][1] if rf else None
        keyr = kr[-1][1] if kr else None
        ref = rusfar if rusfar is not None else keyr
        rows, skipped = mm_basis_build(secs, md, spots, ref, today, lambda sid, p, t, e: mm_divs_until(sid, p, t, e, cfg))
        out = {"rows": rows, "skipped": skipped, "rusfar": rusfar, "key": keyr, "ref": ref, "ref_name": "RUSFAR" if rusfar is not None else "ключевая ставка",
               "asof": datetime.now().strftime("%Y-%m-%d %H:%M"), "note": MM_NOTE_BASIS}
        if not rows:
            out["error"] = "Нет данных для расчёта базиса (биржа не отдала котировки)."
            return out
        return mem_put(key, out)


def mm_api_funds(cfg, acc, q, force):
    try:
        return mm_funds_payload(q)
    except Exception as e:  # noqa: BLE001
        return {"error": "Не удалось рассчитать фонды ликвидности: %s" % e, "funds": []}


def mm_api_basis(cfg, acc, q, force):
    try:
        return mm_basis_payload(bool(force), cfg)
    except Exception as e:  # noqa: BLE001
        return {"error": "Не удалось рассчитать базис: %s" % e, "rows": [], "note": MM_NOTE_BASIS}


API_GET["/api/mm/funds"] = mm_api_funds
API_GET["/api/mm/basis"] = mm_api_basis
