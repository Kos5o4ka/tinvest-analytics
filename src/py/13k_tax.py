# ═══════════════════════════════ налоги по лотам: ЛДВ, ИИС, перенос убытков, подсказки ═══════════════════════════════
# Справочный расчёт. Брокер как налоговый агент считает сам; это не налоговая консультация.
# Лоты покупок по каждой бумаге и счёту, продажи списываются FIFO; комиссии входят в расходы; НКД при покупке/продаже
# учитывается отдельно (уменьшает/увеличивает купонный доход); частичные погашения (амортизация) уменьшают стоимость лотов.

TAX_LDV_TYPES = ("share", "bond", "etf")
TAX_SKIP_TYPES = ("currency", "futures", "dfa")
TAX_LDV_FROM = date(2014, 1, 1)
TAX_LDV_LIMIT = 3000000.0
TAX_IIS_LIMIT = 400000.0
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
    return {"iis": iis, "loss_carry": carry, "offset_coupons": bool(s.get("offset_coupons"))}


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


def tax_engine(ops, types=None, fx=None, held=None):
    """ops — операции (с полем _acc). types — {uid: info} (type), fx(cur, iso_day) -> курс или None, held — {uid: кол-во}
    из текущих позиций (для сверки лотов). Возвращает продажи, остатки лотов и денежные потоки по (счёт, год)."""
    types = types or {}
    warns = {}
    fx = fx or (lambda cur, day: 1.0 if cur == "rub" else None)

    def rate(cur, d):
        if cur in ("", "rub"):
            return 1.0
        r = fx(cur, d.isoformat())
        if not r:
            warns["fx_" + cur] = "Нет курса ЦБ для %s на часть дат — взят курс 1." % cur.upper()
            return 1.0
        return r

    ops = sorted([o for o in ops if not str(o.get("state") or "").endswith("CANCELED")], key=lambda o: o.get("date") or "")
    fee_parent, fee_key = defaultdict(float), defaultdict(float)
    for o in ops:
        if classify(o.get("type")) == "fee_broker":
            dt = parse_dt(o.get("date"))
            amt = abs(qf(o.get("payment"))) * rate(cur_of(o.get("payment")), dt.date())
            if o.get("parentOperationId"):
                fee_parent[o["parentOperationId"]] += amt
            fee_key[(o.get("_acc") or "", (o.get("date") or "")[:19], o.get("instrumentUid") or o.get("figi") or "")] += amt

    def fee_of(o, dt):
        c = o.get("commission")
        if c and qf(c):
            return abs(qf(c)) * rate(cur_of(c), dt.date())
        if o.get("id") and o["id"] in fee_parent:
            return fee_parent[o["id"]]
        return fee_key.get((o.get("_acc") or "", (o.get("date") or "")[:19], o.get("instrumentUid") or o.get("figi") or ""), 0.0)

    books, sales, meta = {}, [], {}
    moved, convs = {}, []
    inc = defaultdict(tx_inc_new)
    turn = [0.0, 0.0]
    for o in ops:
        kind = classify(o.get("type"))
        acc = o.get("_acc") or ""
        dt = parse_dt(o.get("date"))
        d = dt.date()
        uid = o.get("instrumentUid") or o.get("figi") or o.get("_ident") or ""
        info = types.get(uid) or {}
        itype = o.get("instrumentType") or info.get("type") or ""
        itype = {"bonds": "bond", "shares": "share"}.get(itype, itype) or "share"
        pay = qf(o.get("payment"))
        cur = cur_of(o.get("payment"))
        r = rate(cur, d)
        I = inc[(acc, d.year)]
        if uid and kind in ("buy", "sell", "sec_in", "repayments") and uid not in meta:
            meta[uid] = {"name": info.get("name") or o.get("name") or o.get("ticker") or uid, "ticker": info.get("ticker") or o.get("ticker") or "", "type": itype}
        if kind == "dividends":
            I["div"] += pay * r
        elif kind == "coupons":
            I["coupon"] += pay * r
        elif kind == "overnight":
            I["over"] += pay * r
        elif kind in TAXES:
            I["withheld"] += -pay * r
            I["w_" + kind] += -pay * r
        elif kind == "deposits":
            I["dep"] += abs(pay) * r
        elif kind == "withdrawals":
            I["wd"] += abs(pay) * r
        elif kind == "varmargin":
            I["deriv"] += pay * r
        elif kind in ("buy", "sell"):
            q = op_qty(o)
            fee = fee_of(o, dt)
            if itype == "futures":
                I["deriv_fee"] += fee
                continue
            if itype in TAX_SKIP_TYPES or not uid or not q:
                continue
            bucket = "deriv" if itype == "option" else "sec"
            nkd = abs(qf(o.get("accruedInt"))) if o.get("accruedInt") else 0.0
            gross = abs(pay)
            clean = gross - nkd
            if clean < 0:
                clean, nkd = gross, 0.0
            bk = books.setdefault((acc, uid), {"lots": [], "shorts": [], "last_repay": None, "last_unit": 0.0})
            base = {"acc": acc, "uid": uid, "name": meta[uid]["name"], "ticker": meta[uid]["ticker"], "type": itype, "bucket": bucket,
                    "kind": "sell", "sdate": d, "bdate": None}
            turn[0] += gross * r
            turn[1] += fee
            if kind == "buy":
                I["nkd_paid"] += nkd * r
                left = float(q)
                unit_buy = (clean * r + fee) / q
                bk["last_unit"] = unit_buy
                sh = bk["shorts"]
                while left > 1e-9 and sh:
                    s = sh[0]
                    t = min(left, s["qty"])
                    row = dict(base, kind="short", qty=t, bdate=s["date"], sdate=d, proceeds=t * s["up"], cost=t * unit_buy, fee=t * s["uf"], ldv=False, yrs=0)
                    row["result"] = row["proceeds"] - row["cost"] - row["fee"]
                    sales.append(row)
                    s["qty"] -= t
                    left -= t
                    if s["qty"] <= 1e-9:
                        sh.pop(0)
                if left > 1e-9:
                    bk["lots"].append({"qty": left, "unit": unit_buy, "date": d, "cur": cur})
            else:
                I["nkd_recv"] += nkd * r
                yv = o.get("yield")
                if yv and itype != "option":
                    I["bk_yield"] += qf(yv) * rate(cur_of(yv, cur), d)
                rows, left = tx_sell(bk["lots"], q, clean * r, fee, d, base)
                sales.extend(rows)
                if left > 1e-9:
                    warns["short"] = "Есть продажи без покупок в истории (короткие позиции или переводы): учтены упрощённо."
                    bk["shorts"].append({"qty": left, "up": clean * r / q, "uf": fee / q, "date": d})
        elif kind == "sec_in":
            q = op_qty(o)
            if not uid or not q or itype in TAX_SKIP_TYPES:
                continue
            bk = books.setdefault((acc, uid), {"lots": [], "shorts": [], "last_repay": None, "last_unit": 0.0})
            unit = qf(o.get("price")) * rate(cur_of(o.get("price"), cur), d) if o.get("price") and qf(o.get("price")) else (abs(pay) * r / q if pay else bk["last_unit"])
            if not unit:
                warns["unk_cost"] = "У бумаг, зачисленных переводом, нет цены: стоимость принята нулевой (прибыль завышена)."
            bk["lots"].append({"qty": float(q), "unit": unit, "date": d, "cur": cur, "blind": True})
        elif kind == "conv_out":
            # Обмен бумаг (ГДР/АДР на акции российского МКПАО, смена кода и т.п.) не продажа: лоты старой бумаги уходят в «карман» обмена
            cv = o.get("_conv") or {}
            lots, left = [], float(op_qty(o))
            for u in cv.get("old_uids") or [uid]:
                bk = books.get((acc, u))
                while bk and bk["lots"] and left > 1e-9:
                    lot = bk["lots"][0]
                    t = min(left, lot["qty"])
                    lots.append(dict(lot, qty=t))
                    lot["qty"] -= t
                    left -= t
                    if lot["qty"] <= 1e-9:
                        bk["lots"].pop(0)
            lots.sort(key=lambda l: l["date"])
            moved[o.get("id")] = lots
        elif kind == "conv_in":
            # Лоты переходят в новую бумагу: количество × коэффициент, цена за штуку / коэффициент, даты покупки сохраняются.
            # По закону о редомициляции обмен депозитарных расписок на акции не считается реализацией, срок владения для ЛДВ
            # продолжается, поэтому дата покупки не обнуляется.
            cv = o.get("_conv") or {}
            ratio = cv.get("ratio") or 1
            lots = moved.pop((o.get("id") or "")[:-3] + ":out", [])
            left = float(op_qty(o))
            bk = books.setdefault((acc, uid), {"lots": [], "shorts": [], "last_repay": None, "last_unit": 0.0})
            for lot in lots:
                t = min(left, lot["qty"] * ratio)
                if t > 1e-9:
                    bk["lots"].append(dict(lot, qty=t, unit=lot["unit"] / ratio))
                    left -= t
            bk["lots"].sort(key=lambda l: l["date"])
            if uid not in meta:
                meta[uid] = {"name": info.get("name") or cv.get("new_ticker") or uid, "ticker": info.get("ticker") or cv.get("new_ticker") or "", "type": itype}
            convs.append(cv)
        elif kind == "sec_out":
            q = op_qty(o)
            bk = books.get((acc, uid))
            if bk and q:
                tx_sell(bk["lots"], q, 0.0, 0.0, d, {"bucket": "none"})
        elif kind == "repayments":
            bk = books.get((acc, uid))
            amount = abs(pay) * r
            if not bk or not bk["lots"] or itype in TAX_SKIP_TYPES:
                if amount:
                    warns["repay_nolots"] = "Погашение/амортизация по бумаге без покупок в истории — не учтено в расходах."
                continue
            base = {"acc": acc, "uid": uid, "name": meta.get(uid, {}).get("name", ""), "ticker": meta.get(uid, {}).get("ticker", ""),
                    "type": itype, "bucket": "sec", "kind": "repay", "sdate": d, "bdate": None}
            tq = sum(l["qty"] for l in bk["lots"])
            if op_type(o) == "BOND_REPAYMENT_FULL":
                rows, _ = tx_sell(bk["lots"], tq, amount, 0.0, d, base)
                sales.extend(rows)
            else:
                bk["last_repay"] = d
                red = amount / tq if tq else 0.0
                excess = 0.0
                for l in bk["lots"]:
                    if l["unit"] >= red:
                        l["unit"] -= red
                    else:
                        excess += (red - l["unit"]) * l["qty"]
                        l["unit"] = 0.0
                if excess > 0.005:
                    sales.append(dict(base, kind="amort", qty=0.0, proceeds=excess, cost=0.0, fee=0.0, result=excess, ldv=False, yrs=0))
    # сверка с текущими позициями: лишние лоты (проданные/погашенные вне истории) списываются
    if held is not None:
        by_uid = defaultdict(list)
        for (acc, uid), bk in books.items():
            by_uid[uid].append((acc, bk))
        for uid, lst in by_uid.items():
            have = held.get(uid, 0.0)
            tot = sum(l["qty"] for _, bk in lst for l in bk["lots"])
            if tot <= have + 0.5:
                if have - tot > 0.5:
                    warns["more_pos"] = "В позициях бумаг больше, чем в истории покупок: часть бумаг без даты и цены покупки."
                continue
            extra = tot - have
            for acc, bk in lst:
                if extra <= 1e-9:
                    break
                lr = bk["last_repay"]
                if have <= 0.5 and lr is not None and bk["lots"]:
                    cost = sum(l["qty"] * l["unit"] for l in bk["lots"])
                    qq = sum(l["qty"] for l in bk["lots"])
                    mt = meta.get(uid, {})
                    if cost > 0.005:
                        sales.append({"acc": acc, "uid": uid, "name": mt.get("name", ""), "ticker": mt.get("ticker", ""), "type": mt.get("type", "bond"),
                                      "bucket": "sec", "kind": "writeoff", "sdate": lr, "bdate": None, "qty": qq, "proceeds": 0.0, "cost": cost,
                                      "fee": 0.0, "result": -cost, "ldv": False, "yrs": 0})
                    extra -= qq
                    bk["lots"] = []
                else:
                    n = min(extra, sum(l["qty"] for l in bk["lots"]))
                    tx_sell(bk["lots"], n, 0.0, 0.0, date.today(), {"bucket": "none"})
                    extra -= n
                    warns["gap"] = "Часть бумаг исчезла из позиций без операций продажи (например, конвертация или перевод) — лоты списаны без финрезультата."
    opens = []
    for (acc, uid), bk in books.items():
        for l in bk["lots"]:
            if l["qty"] > 1e-9:
                mt = meta.get(uid, {})
                opens.append({"acc": acc, "uid": uid, "name": mt.get("name", ""), "ticker": mt.get("ticker", ""), "type": mt.get("type", "share"),
                              "qty": l["qty"], "unit": l["unit"], "date": l["date"], "blind": bool(l.get("blind")), "cur": l.get("cur", "rub")})
    return {"sales": sales, "open": opens, "inc": dict(inc), "meta": meta, "warnings": sorted(warns.values()),
            "fee_rate": (turn[1] / turn[0]) if turn[0] > 0 else 0.003}


# ── налоговая база по годам для группы счетов ──

def tx_apply_carry(pool, trade_t, year=9999):
    """Погашает положительный результат убытками прошлых лет (старые — первыми). Возвращает (использовано, остаток базы)."""
    used = 0.0
    if trade_t > 0:
        for p in sorted([p for p in pool if p[0] < year], key=lambda p: p[0]):
            u = min(p[1], trade_t - used)
            if u > 0:
                p[1] -= u
                used += u
    return used, max(0.0, trade_t - used)


def tax_group_years(sales, inc, carry_user=None, iis_exempt=False, extra=None, offset_coupons=False):
    """sales — строки продаж группы; inc — {год: суммы}; carry_user — {"2023": сумма} убытки прошлых лет из деклараций.
    Возвращает (строки по годам, остатки убытков [[год, сумма]])."""
    sales = list(sales) + list(extra or [])
    carry_user = carry_user or {}
    ys = set(r["sdate"].year for r in sales) | set(inc)
    pool = []
    for k, v in carry_user.items():
        if int(k) not in ys:
            pool.append([int(k), float(v)])
    rows, nkd_pool = [], 0.0
    for y in sorted(ys):
        i = inc.get(y, {})
        sec = [s for s in sales if s["bucket"] == "sec" and s["sdate"].year == y]
        dv = [s for s in sales if s["bucket"] == "deriv" and s["sdate"].year == y]
        trade = sum(s["result"] for s in sec)
        elig = [s for s in sec if s["ldv"]]
        elig_res = sum(s["result"] for s in elig)
        wc = sum(max(s["cost"], 0.0) for s in elig)
        wy = (sum(max(s["cost"], 0.0) * s["yrs"] for s in elig) / wc) if wc > 0 else (sum(s["yrs"] for s in elig) / len(elig) if elig else 0.0)
        limit = TAX_LDV_LIMIT * wy
        exempt = min(max(0.0, elig_res), limit)
        pool = [p for p in pool if y - p[0] <= 10 and p[1] > 0.005]
        pool_before = [list(p) for p in pool]
        div = i.get("div", 0.0)
        cg = i.get("coupon", 0.0) + i.get("nkd_recv", 0.0)
        avail = nkd_pool + i.get("nkd_paid", 0.0)
        un = min(avail, max(0.0, cg))
        coupon_net = cg - un
        nkd_pool = avail - un
        trade_t = trade - exempt
        coff = 0.0
        if offset_coupons and trade_t < 0 and coupon_net > 0:
            coff = min(coupon_net, -trade_t)
            coupon_net -= coff
            trade_t += coff
        used, trade_base = tx_apply_carry(pool, trade_t, y)
        new_loss = -trade_t if trade_t < 0 else 0.0
        if str(y) in carry_user:
            new_loss = float(carry_user[str(y)])
        if new_loss > 0.005:
            pool.append([y, new_loss])
        over = i.get("over", 0.0)
        deriv = sum(s["result"] for s in dv) + i.get("deriv", 0.0) - i.get("deriv_fee", 0.0)
        base = trade_base + div + coupon_net + over + max(0.0, deriv)
        tax, lo, hi = tx_ndfl(base, y)
        if iis_exempt:
            tax = 0.0
        saved = 0.0
        if exempt > 0.005 and not iis_exempt:
            tb0 = tx_apply_carry(pool_before, trade, y)[1]
            saved = max(0.0, tx_ndfl(tb0 + div + coupon_net + over + max(0.0, deriv), y)[0] - tax)
        withheld = i.get("withheld", 0.0)
        rows.append({
            "year": y, "proceeds": sum(s["proceeds"] for s in sec), "cost": sum(s["cost"] for s in sec), "fees": sum(s["fee"] for s in sec),
            "trade": trade, "ldv_exempt": exempt, "ldv_limit": limit if elig else 0.0, "ldv_saved": saved, "ldv_n": len(elig),
            "carry_used": used, "loss_new": new_loss, "trade_base": trade_base,
            "dividends": div, "coupons": coupon_net, "coupons_gross": i.get("coupon", 0.0), "nkd_adj": i.get("nkd_recv", 0.0) - un, "coupon_offset": coff,
            "overnight": over, "deriv": deriv, "base": base, "tax": tax, "tax13": lo * 0.13, "tax15": hi * 0.15,
            "withheld": withheld, "w": {k[2:]: v for k, v in i.items() if k.startswith("w_")},
            "diff": tax - withheld, "diff_pct": ((tax - withheld) / withheld * 100.0) if withheld > 1 else None,
            "broker_trade": i.get("bk_yield", 0.0), "deposits": i.get("dep", 0.0), "withdrawals": i.get("wd", 0.0)})
    return rows, [[p[0], p[1]] for p in pool if p[1] > 0.005]


# ── состояние: группы счетов, ИИС, ЛДВ, подсказки ──

TAX_SUM_KEYS = ("proceeds", "cost", "fees", "trade", "ldv_exempt", "ldv_saved", "carry_used", "loss_new", "trade_base", "dividends", "coupons",
                "overnight", "deriv", "base", "tax", "tax13", "tax15", "withheld", "broker_trade", "deposits", "withdrawals")


def tx_gkey(a):
    return "iis:" + a["id"] if a.get("type") == "ИИС" else "gen"


def tx_iis_info(a, setting, first_date, today):
    typ = setting.get("type") or ""
    opened = None
    for s in (setting.get("opened"), (a.get("opened") or "")[:10]):
        if s:
            try:
                opened = datetime.strptime(s[:10], "%Y-%m-%d").date()
                break
            except ValueError:
                pass
    if opened is None:
        opened = first_date
    eff = typ or "A"
    term = tx_add_years(opened, 5 if eff == "3" else 3) if opened else None
    return {"id": a["id"], "name": a["name"], "type": eff, "type_set": bool(typ), "opened": opened.isoformat() if opened else "",
            "term": term.isoformat() if term else "", "term_ok": bool(term and today >= term),
            "exempt": eff in ("B", "3") and bool(term and today >= term)}


def tx_sum_rows(per_group, exempt=None):
    """Итоги по годам. exempt — флаги групп, освобождённых от налога (ИИС с соблюдённым сроком): их база в общую не входит.
    Порог 15 % относится к совокупной базе налогоплательщика, а группы считаются по отдельности, поэтому налог по
    совокупной базе пересчитывается заново; превышение над суммой налогов групп — extra_progressive."""
    tot, comb = {}, defaultdict(float)
    for gi, rows in enumerate(per_group):
        for r in rows:
            if not (exempt and exempt[gi]):
                comb[r["year"]] += r["base"]
            t = tot.setdefault(r["year"], {"year": r["year"], "w": defaultdict(float)})
            for k in TAX_SUM_KEYS:
                t[k] = t.get(k, 0.0) + r[k]
            for k, v in r["w"].items():
                t["w"][k] += v
    out = []
    for y in sorted(tot):
        t = tot[y]
        t["w"] = dict(t["w"])
        extra = tx_ndfl(comb[y], y)[0] - t["tax"]
        t["extra_progressive"] = extra if extra > 0.5 else 0.0
        t["diff"] = t["tax"] - t["withheld"]
        t["diff_pct"] = (t["diff"] / t["withheld"] * 100.0) if t["withheld"] > 1 else None
        out.append(t)
    return out


def tx_lines(sales, year):
    agg = {}
    for s in sales:
        if s["bucket"] != "sec" or s["sdate"].year != year:
            continue
        k = (s["uid"], s["kind"])
        a = agg.setdefault(k, {"name": s["name"], "ticker": s["ticker"], "type": s["type"], "kind": s["kind"], "qty": 0.0, "proceeds": 0.0,
                               "cost": 0.0, "fee": 0.0, "result": 0.0, "ldv_result": 0.0})
        for f in ("qty", "proceeds", "cost", "fee", "result"):
            a[f] += s[f]
        if s["ldv"]:
            a["ldv_result"] += s["result"]
    return sorted(agg.values(), key=lambda a: -abs(a["result"]))[:80]


def tx_pos_price(r):
    if not r or not r.get("qty"):
        return None
    p = r.get("price") or 0.0
    if r.get("value") and r.get("value_rub") is not None:
        p = p * r["value_rub"] / r["value"]
    return p or None


def tax_compute(ops, names, positions, sel, settings, fx=None, today=None, resolve=None):
    """Чистая часть расчёта (без сети): ops + позиции + выбранные счета -> структура состояния."""
    today = today or date.today()
    pos = {}
    for r in positions or []:
        if r.get("type") not in ("currency", "futures") and r.get("uid"):
            pos[r["uid"]] = r
    held = {u: r["qty"] for u, r in pos.items()} if pos else None
    events = find_conversions(ops, names, held, resolve=resolve)
    ops = apply_conversions(ops, events)
    eng = tax_engine(ops, names, fx, held)
    accs = {a["id"]: a for a in sel}
    groups = {}
    for a in sel:
        g = groups.setdefault(tx_gkey(a), {"key": tx_gkey(a), "accounts": []})
        g["accounts"].append(a["id"])
    first_by_acc = {}
    for o in ops:
        d = parse_dt(o.get("date")).date()
        k = o.get("_acc") or ""
        if k not in first_by_acc or d < first_by_acc[k]:
            first_by_acc[k] = d
    out_groups, per_rows, iis_list, per_exempt = [], [], [], []
    off = settings.get("offset_coupons", False)
    for gk, g in groups.items():
        ids = set(g["accounts"])
        sales = [s for s in eng["sales"] if s["acc"] in ids]
        inc = defaultdict(lambda: defaultdict(float))
        for (acc, y), v in eng["inc"].items():
            if acc in ids:
                for k, x in v.items():
                    inc[y][k] += x
        exempt = False
        if gk == "gen":
            g["name"] = "Обычные счета" if len(ids) > 1 else accs[g["accounts"][0]]["name"]
            g["kind"] = "gen"
        else:
            a = accs[g["accounts"][0]]
            iinfo = tx_iis_info(a, settings["iis"].get(a["id"]) or {}, first_by_acc.get(a["id"]), today)
            iis_list.append(iinfo)
            exempt = iinfo["exempt"]
            g["name"] = "ИИС: " + a["name"]
            g["kind"] = "iis"
            g["iis"] = iinfo
            sales = [dict(s, ldv=False, yrs=0) for s in sales]
        rows, pool = tax_group_years(sales, inc, settings["loss_carry"] if gk == "gen" else None, exempt, None, off)
        g["rows"], g["pool"], g["sales"], g["inc"] = rows, pool, sales, inc
        per_rows.append(rows)
        per_exempt.append(exempt)
        out_groups.append(g)
    return {"eng": eng, "groups": out_groups, "years": tx_sum_rows(per_rows, per_exempt), "iis": iis_list, "pos": pos, "today": today, "accs": accs,
            "conversions": conversions_view(events)}


def tx_ldv_tables(st):
    """Будущие и уже наступившие ЛДВ по открытым лотам (только обычные счета: на ИИС ЛДВ не применяется)."""
    today = st["today"]
    gen_ids = set(a for g in st["groups"] if g["kind"] == "gen" for a in g["accounts"])
    cy = today.year
    cur_base = 0.0
    for g in st["groups"]:
        if g["kind"] == "gen":
            for r in g["rows"]:
                if r["year"] == cy:
                    cur_base = r["base"]
    rate = 0.15 if cur_base > (2400000.0 if cy >= 2025 else 5000000.0) else 0.13
    groups, ready = {}, {}
    for l in st["eng"]["open"]:
        if l["acc"] not in gen_ids or l["type"] not in TAX_LDV_TYPES or l["blind"] or not l["date"] or l["date"] < TAX_LDV_FROM:
            continue
        pr = tx_pos_price(st["pos"].get(l["uid"]))
        value = l["qty"] * pr if pr else None
        cost = l["qty"] * l["unit"]
        frm = tx_add_years(l["date"], 3) + timedelta(days=1)
        days = (frm - today).days
        tgt = ready if days <= 0 else groups
        k = l["uid"] if days <= 0 else (l["uid"], frm)
        e = tgt.setdefault(k, {"uid": l["uid"], "name": l["name"], "ticker": l["ticker"], "type": l["type"], "date": frm.isoformat(), "days": days,
                               "qty": 0.0, "cost": 0.0, "value": 0.0, "gain": 0.0, "known": True})
        e["qty"] += l["qty"]
        e["cost"] += cost
        if value is None:
            e["known"] = False
        else:
            e["value"] += value
            e["gain"] += value - cost
    up = sorted(groups.values(), key=lambda e: e["days"])
    for e in up + list(ready.values()):
        e["tax_now"] = max(0.0, e["gain"]) * rate if e["known"] else None
    return up, sorted(ready.values(), key=lambda e: -e["gain"]), rate


def tx_fee_sim(lots, qty, price, fee_rate, today, base):
    cp = [dict(l) for l in sorted(lots, key=lambda l: l["date"] or date(1970, 1, 1))]
    rows, _ = tx_sell(cp, qty, qty * price, qty * price * fee_rate, today, dict(base, sdate=today))
    return rows


def tx_group_open(st, g):
    ids = set(g["accounts"])
    by = defaultdict(list)
    for l in st["eng"]["open"]:
        if l["acc"] in ids:
            by[l["uid"]].append(l)
    return by


def tx_cur_tax(g, extra, cy, settings):
    """Налог текущего года по группе с дополнительными (гипотетическими) продажами."""
    exempt = g["kind"] == "iis" and g["iis"]["exempt"]
    rows, _ = tax_group_years(g["sales"], g["inc"], settings["loss_carry"] if g["kind"] == "gen" else None, exempt, extra, settings.get("offset_coupons", False))
    for r in rows:
        if r["year"] == cy:
            return r["tax"], r
    return 0.0, None


def tx_hints(st, settings):
    today, cy = st["today"], st["today"].year
    fee_rate = st["eng"]["fee_rate"]
    up, rd, rate = tx_ldv_tables(st)
    out = {"year": cy, "days_left": (date(cy, 12, 31) - today).days, "harvest": [], "harvest_total": 0.0, "ldv_warn": [], "notes": [],
           "spread": TAX_SPREAD, "fee_rate": fee_rate}
    for e in up:
        if e["days"] <= 365 and e["known"] and e["gain"] > 0 and e["tax_now"] and e["tax_now"] > 50:
            out["ldv_warn"].append(e)
    for g in st["groups"]:
        if g["kind"] == "iis" and g["iis"]["type"] != "A":
            continue
        t0, row0 = tx_cur_tax(g, [], cy, settings)
        if not row0 or t0 <= 1:
            continue
        cands = []
        for uid, lots in tx_group_open(st, g).items():
            pr = tx_pos_price(st["pos"].get(uid))
            if not pr or lots[0]["type"] in TAX_SKIP_TYPES:
                continue
            q = sum(l["qty"] for l in lots)
            base = {"acc": lots[0]["acc"], "uid": uid, "name": lots[0]["name"], "ticker": lots[0]["ticker"], "type": lots[0]["type"],
                    "bucket": "deriv" if lots[0]["type"] == "option" else "sec", "kind": "sell", "bdate": None}
            rows = tx_fee_sim(lots, q, pr, fee_rate, today, base)
            res = sum(r["result"] for r in rows)
            if res >= -50:
                continue
            value = q * pr
            t1, _ = tx_cur_tax(g, rows, cy, settings)
            cost = value * (fee_rate + TAX_SPREAD)
            cands.append({"uid": uid, "name": base["name"], "ticker": base["ticker"], "type": base["type"], "group": g["key"], "gname": g["name"],
                          "qty": q, "value": value, "loss": -res, "saving": t0 - t1, "cost": cost, "net": t0 - t1 - cost, "rows": rows,
                          "ldv_lost": any(r["ldv"] for r in rows) or any(l["date"] and (tx_add_years(l["date"], 3) - today).days < 120 for l in lots if not l.get("blind"))})
        cands.sort(key=lambda c: -c["net"])
        chosen, extra = [], []
        for c in cands:
            if c["net"] <= 1:
                continue
            t_prev, _ = tx_cur_tax(g, extra, cy, settings)
            t_new, _ = tx_cur_tax(g, extra + c["rows"], cy, settings)
            if (t_prev - t_new) - c["cost"] > 1:
                extra = extra + c["rows"]
                chosen.append(c)
        if chosen:
            t_all, _ = tx_cur_tax(g, extra, cy, settings)
            out["harvest_total"] += (t0 - t_all) - sum(c["cost"] for c in chosen)
        for c in cands:
            c.pop("rows", None)
            if c["net"] > 1:
                out["harvest"].append(c)
    out["harvest"].sort(key=lambda c: -c["net"])
    out["harvest"] = out["harvest"][:25]
    if not out["harvest"]:
        out["notes"].append("Позиций с убытком, продажа которых уменьшила бы налог текущего года, не найдено (или налога за этот год пока нет).")
    return out


def tx_last_sale_day(year, holidays=()):
    """Последний день года, когда сделка ещё рассчитается в этом году при T+1: последний торговый день минус один торговый день.
    Торговым считаем будний день, не равный 31 декабря (на практике 31.12 — выходной на бирже) и не из holidays (набор date).
    Точный календарь торгов определяет биржа."""
    hol = set(holidays or ())

    def trading(d):
        return d.weekday() < 5 and not (d.month == 12 and d.day == 31) and d not in hol
    d = date(year, 12, 31)
    while not trading(d):
        d -= timedelta(days=1)
    last = d
    d = last - timedelta(days=1)
    while not trading(d):
        d -= timedelta(days=1)
    return d, last


def tx_forecast(st, settings, pays=None, holidays=()):
    """Прогноз налога на конец года по обычным (не ИИС) счетам и подсказки по сбору убытков. pays — прогноз выплат (как на странице «Выплаты»)."""
    today, cy = st["today"], st["today"].year
    end = date(cy, 12, 31).isoformat()
    sale_day, last_day = tx_last_sale_day(cy, holidays)
    gen = [g for g in st["groups"] if g["kind"] == "gen"]
    iis = [g["name"] for g in st["groups"] if g["kind"] == "iis"]
    out = {"year": cy, "available": bool(gen), "iis_excluded": iis, "sale_day": sale_day.isoformat(), "last_trading_day": last_day.isoformat(),
           "days_to_sale": (sale_day - today).days, "pays_known": pays is not None, "harvest": [], "skipped": [], "harvest_saving": 0.0}
    if not gen:
        return out
    g = gen[0]
    row = next((r for r in g["rows"] if r["year"] == cy), None) or {}
    f = lambda k: float(row.get(k, 0.0) or 0.0)
    ec = ed = 0.0
    n = 0
    for p in pays or []:
        if today.isoformat() < (p.get("date") or "") <= end and p.get("kind") in ("coupon", "dividend") and p.get("amount"):
            if p["kind"] == "coupon":
                ec += p["amount"]
            else:
                ed += p["amount"]
            n += 1
    base = f("base")
    tax_now = tx_ndfl(base, cy)[0]
    tax_end, lo, hi = tx_ndfl(base + ec + ed, cy)
    thr = 5000000.0 if cy < 2025 else 2400000.0
    out["forecast"] = {
        "trade": f("trade"), "ldv_exempt": f("ldv_exempt"), "carry_used": f("carry_used"), "trade_base": f("trade_base"), "dividends": f("dividends"),
        "coupons": f("coupons"), "other": f("overnight") + max(0.0, f("deriv")), "base": base, "tax_now": tax_now, "withheld": f("withheld"),
        "exp_coupons": ec, "exp_dividends": ed, "exp_n": n, "base_end": base + ec + ed, "tax_end": tax_end, "tax13": lo * 0.13, "tax15": hi * 0.15,
        "to_withhold": max(0.0, tax_end - f("withheld")), "refund": max(0.0, f("withheld") - tax_end), "threshold": thr,
        "rate": 0.15 if base + ec + ed > thr else 0.13}
    # сбор убытков: позиции обычных счетов с нереализованным убытком
    fee_rate = st["eng"]["fee_rate"]
    t0, _ = tx_cur_tax(g, [], cy, settings)
    cands, skipped = [], []
    for uid, lots in tx_group_open(st, g).items():
        pr = tx_pos_price(st["pos"].get(uid))
        if not pr or lots[0]["type"] in TAX_SKIP_TYPES:
            continue
        q = sum(l["qty"] for l in lots)
        base_r = {"acc": lots[0]["acc"], "uid": uid, "name": lots[0]["name"], "ticker": lots[0]["ticker"], "type": lots[0]["type"],
                  "bucket": "deriv" if lots[0]["type"] == "option" else "sec", "kind": "sell", "bdate": None}
        rows = tx_fee_sim(lots, q, pr, fee_rate, today, base_r)
        res = sum(r["result"] for r in rows)
        if res >= -50:
            continue
        t1, _ = tx_cur_tax(g, rows, cy, settings)
        # лоты с прибылью, которым скоро исполнится 3 года (ЛДВ): продажа всей позиции лишит их льготы
        soon = None
        if lots[0]["type"] in TAX_LDV_TYPES:
            for l in lots:
                if l.get("blind") or not l["date"] or l["date"] < TAX_LDV_FROM or l["unit"] >= pr:
                    continue
                dd = (tx_add_years(l["date"], 3) + timedelta(days=1) - today).days
                if 0 < dd <= 365 and (soon is None or dd < soon):
                    soon = dd
        c = {"uid": uid, "name": base_r["name"], "ticker": base_r["ticker"], "qty": q, "value": q * pr, "loss": -res, "saving": t0 - t1,
             "cost": q * pr * (fee_rate + TAX_SPREAD), "ldv_days": soon, "rows": rows}
        c["net"] = c["saving"] - c["cost"]
        if soon is not None and soon <= 180:
            c["reason"] = "через %d дн. часть лотов получит ЛДВ, продавать невыгодно" % soon
            skipped.append(c)
        elif c["net"] > 1:
            cands.append(c)
    cands.sort(key=lambda c: -c["saving"])
    extra = []
    for c in cands:        # накопительный эффект: каждая следующая продажа уменьшает налог меньше, когда прибыль уже покрыта
        tp, _ = tx_cur_tax(g, extra, cy, settings)
        extra = extra + c["rows"]
        tn, _ = tx_cur_tax(g, extra, cy, settings)
        c["saving_marginal"] = tp - tn
    for c in cands + skipped:
        c.pop("rows", None)
    out["harvest"], out["skipped"] = cands[:25], skipped[:10]
    out["harvest_saving"] = sum(c["saving_marginal"] for c in cands)
    out["base_tax"] = t0
    return out


def tx_decl(st):
    decl = {}
    for g in st["groups"]:
        for r in g["rows"]:
            d = decl.setdefault(r["year"], {"year": r["year"], "groups": []})
            e = dict(r)
            e.update(key=g["key"], name=g["name"], kind=g["kind"], lines=tx_lines(g["sales"], r["year"]))
            d["groups"].append(e)
    return decl


def tx_iis_table(st, settings):
    out = []
    for g in st["groups"]:
        if g["kind"] != "iis":
            continue
        i = g["iis"]
        ded = i["type"] in ("A", "3")
        ys = []
        for r in g["rows"]:
            if r["deposits"] > 0 or r["withdrawals"] > 0:
                b = min(r["deposits"], TAX_IIS_LIMIT)
                ys.append({"year": r["year"], "deposits": r["deposits"], "withdrawals": r["withdrawals"], "deduct_base": b if ded else 0.0,
                           "deduct": b * 0.13 if ded else 0.0, "over": max(0.0, r["deposits"] - TAX_IIS_LIMIT)})
        e = dict(i)
        e.update(years=ys, deduct_total=sum(y["deduct"] for y in ys),
                 tax_if_closed=sum(r["tax"] for r in g["rows"]) if not i["exempt"] else 0.0,
                 trade_total=sum(r["trade"] for r in g["rows"]), income_total=sum(r["dividends"] + r["coupons"] for r in g["rows"]))
        out.append(e)
    return out


def tax_payload_from(st, settings, pays=None):
    gen = [g for g in st["groups"] if g["kind"] == "gen"]
    cy = st["today"].year
    up, rd, rate = tx_ldv_tables(st)
    sugg = []
    for g in gen:
        for r in g["rows"]:
            if r["year"] < cy and r["loss_new"] > 0.005 and str(r["year"]) not in settings["loss_carry"]:
                sugg.append({"year": r["year"], "loss": r["loss_new"]})
    ldv_years = {}
    for g in gen:
        for r in g["rows"]:
            if r["ldv_exempt"] > 0 or r["ldv_n"]:
                e = ldv_years.setdefault(r["year"], {"year": r["year"], "exempt": 0.0, "saved": 0.0, "n": 0, "limit": 0.0})
                e["exempt"] += r["ldv_exempt"]
                e["saved"] += r["ldv_saved"]
                e["n"] += r["ldv_n"]
                e["limit"] = max(e["limit"], r["ldv_limit"])
    strip = lambda g: {k: v for k, v in g.items() if k not in ("sales", "inc")}
    return {
        "today": st["today"].isoformat(), "settings": settings,
        "groups": [strip(g) for g in st["groups"]], "years": st["years"],
        "ldv": {"upcoming": up[:80], "ready": rd[:40], "years": [ldv_years[y] for y in sorted(ldv_years)],
                "saved_total": sum(e["saved"] for e in ldv_years.values()), "rate": rate, "limit": TAX_LDV_LIMIT},
        "iis": tx_iis_table(st, settings), "hints": tx_hints(st, settings), "forecast": tx_forecast(st, settings, pays), "decl": tx_decl(st),
        "carry_suggest": sugg, "warnings": st["eng"]["warnings"], "conversions": st.get("conversions") or [],
        "assumptions": [
            "Счета без ИИС объединены в одну налоговую базу (сальдирование прибылей и убытков между счетами одного налогоплательщика); каждый ИИС считается отдельно.",
            "Налог по годам сравнивается с удержанным по дате операции удержания; брокер часто удерживает налог за год в декабре или в январе следующего года.",
            "Ставка: 13 % и 15 % с части базы свыше 5 млн ₽ (2021–2024) или свыше 2,4 млн ₽ (с 2025 года). Заработная плата и другие доходы в порог не входят.",
            "ЛДВ применяется к акциям, облигациям и фондам, купленным с 2014 года и проданным после трёх лет владения; бумаги, полученные переводом, не учитываются.",
            "НКД, уплаченный при покупке, уменьшает купонный доход (остаток переносится), НКД при продаже входит в купонный доход.",
            "Фьючерсы и опционы: отдельная база по вариационной марже; валюта и ЦФА в расчёт не входят."]}


def tax_state(cfg, acc, force=False):
    settings = tax_settings()
    key = ("taxst", token_key(cfg), acc, json.dumps(settings, sort_keys=True))
    hit = None if force else mem_get(key, 120)
    if hit:
        return hit, settings
    with key_lock(key):
        hit = None if force else mem_get(key, 120)
        if hit:
            return hit, settings
        client = TInvest(cfg)
        accs, sel, data = selection(cfg, acc, force)
        ops = sorted([o for d in data for o in d["ops"]], key=lambda o: o.get("date") or "")
        keys = {(o.get("instrumentUid"), o.get("figi")) for o in ops
                if (o.get("instrumentUid") or o.get("figi")) and not str(o.get("instrumentUid") or "").startswith("imp:")}
        names = instruments(client, keys)
        positions = build_summary(cfg, acc, "all", force)["portfolio"]["positions"]
        st = tax_compute(ops, names, positions, sel, settings, tax_cbr_rate,
                         resolve=lambda t: benchmark_uid(client, t) if client.ready else None)
        return mem_put(key, st), settings


def tax_get(cfg, acc, q, force):
    st, settings = tax_state(cfg, acc, force)
    pays = None
    if cfg.get("token"):
        try:
            pays = build_bonds(cfg, acc).get("payments") or []
        except Exception:  # noqa: BLE001
            pays = None
    return tax_payload_from(st, settings, pays)


def tax_post_settings(cfg, body):
    return {"settings": tax_settings_save(cfg, body or {})}


def tax_reb_plan(st, settings, sells):
    """sells: {класс: сумма продажи, ₽}. Для каждого класса сравниваем «продать пропорционально» и «сначала убыточные и с ЛДВ»."""
    today, cy = st["today"], st["today"].year
    fee_rate = st["eng"]["fee_rate"]
    out = []
    for cls_, amount in sells.items():
        cands = []
        for g in st["groups"]:
            for uid, lots in tx_group_open(st, g).items():
                if lots[0]["type"] != cls_:
                    continue
                pr = tx_pos_price(st["pos"].get(uid))
                if not pr:
                    continue
                q = sum(l["qty"] for l in lots)
                base = {"acc": lots[0]["acc"], "uid": uid, "name": lots[0]["name"], "ticker": lots[0]["ticker"], "type": cls_,
                        "bucket": "deriv" if cls_ == "option" else "sec", "kind": "sell", "bdate": None}
                rows = tx_fee_sim(lots, q, pr, fee_rate, today, base)
                t0, _ = tx_cur_tax(g, [], cy, settings)
                t1, _ = tx_cur_tax(g, rows, cy, settings)
                value = q * pr
                cands.append({"g": g, "uid": uid, "lots": lots, "price": pr, "qty": q, "value": value, "base": base,
                              "rate": (t1 - t0) / value if value else 0.0})
        if not cands:
            out.append({"cls": cls_, "amount": amount, "plan": [], "tax_plan": None, "tax_naive": None, "note": "Нет данных о лотах по этому классу"})
            continue

        def run(pick):
            per_g, items = defaultdict(list), []
            for c, qq in pick:
                rows = tx_fee_sim(c["lots"], qq, c["price"], fee_rate, today, c["base"])
                per_g[c["g"]["key"]].extend(rows)
                res = sum(r["result"] for r in rows)
                soon = [l for l in c["lots"] if l["date"] and not l.get("blind") and 0 < (tx_add_years(l["date"], 3) + timedelta(days=1) - today).days <= 180]
                why = "убыток" if res < 0 else ("прибыль освобождена по ЛДВ" if rows and all(r["ldv"] for r in rows) and res > 0 else "есть налог")
                items.append({"uid": c["uid"], "name": c["base"]["name"], "ticker": c["base"]["ticker"], "gname": c["g"]["name"], "qty": qq,
                              "sell_rub": qq * c["price"], "result": res, "why": why, "ldv_soon": bool(soon and res > 0)})
            tot = 0.0
            for c in {id(x[0]["g"]): x[0] for x in pick}.values():
                g = c["g"]
                t0, _ = tx_cur_tax(g, [], cy, settings)
                t1, _ = tx_cur_tax(g, per_g[g["key"]], cy, settings)
                tot += t1 - t0
            return tot, items
        total_v = sum(c["value"] for c in cands)
        amt = min(amount, total_v)
        naive = []
        for c in cands:
            qq = int(c["qty"] * amt / total_v)
            if qq > 0:
                naive.append((c, qq))
        tax_naive, items_naive = run(naive) if naive else (0.0, [])
        plan, rem = [], amt
        for c in sorted(cands, key=lambda c: c["rate"]):
            if rem < c["price"]:
                break
            qq = int(min(c["qty"], rem / c["price"]))
            if qq <= 0:
                continue
            plan.append((c, qq))
            rem -= qq * c["price"]
        tax_plan, items = run(plan) if plan else (0.0, [])
        if tax_plan > tax_naive:
            tax_plan, items = tax_naive, items_naive
        out.append({"cls": cls_, "amount": amount, "covered": amt, "tax_plan": tax_plan, "tax_naive": tax_naive,
                    "saving": max(0.0, tax_naive - tax_plan), "plan": items})
    return out


def tax_reb_get(cfg, acc, q, force):
    sells = {}
    for part in (q.get("sells") or "").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            try:
                if float(v) > 0:
                    sells[k] = float(v)
            except ValueError:
                pass
    st, settings = tax_state(cfg, acc, force)
    return {"items": tax_reb_plan(st, settings, sells), "warnings": st["eng"]["warnings"]}


API_GET["/api/tax"] = tax_get
API_GET["/api/tax/reb"] = tax_reb_get
API_POST["/api/tax/settings"] = tax_post_settings
