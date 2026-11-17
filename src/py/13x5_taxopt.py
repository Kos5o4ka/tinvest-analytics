# ═══════════════════════════════ налоговая оптимизация: сбор убытков по лотам FIFO и планировщик ИИС-3 ═══════════════════════════════
# Справочный расчёт по модели; налог удерживает брокер, итог за год определяется декларацией. Не индивидуальная рекомендация.

# ИИС-3 (НК РФ ст. 219.1 — вычет на взносы; ст. 219.2 — освобождение положительного финансового результата).
TXO_IIS_LIMIT = 400000.0          # взносы, с которых предоставляется вычет, за год
TXO_IIS_EXEMPT_CAP = 30000000.0   # предел освобождаемого финансового результата за всё время
TXO_IIS_RATE_LO, TXO_IIS_RATE_HI = 0.13, 0.15
TXO_HI_THRESHOLD = 2400000.0      # доход в год, выше которого применяется ставка 15 %
TXO_IIS_TERMS = ((2024, 2026, 5), (2027, 2027, 6), (2028, 2028, 7), (2029, 2029, 8), (2030, 2030, 9))   # (с года, по год, срок лет); с 2031 — 10
TXO_MIN_LOSS = 50.0


def txo_iis3_term(open_year):
    """Минимальный срок ИИС-3 (лет) по году открытия: 2024–2026 — 5, 2027 — 6, 2028 — 7, 2029 — 8, 2030 — 9, с 2031 — 10."""
    for a, b, t in TXO_IIS_TERMS:
        if a <= open_year <= b:
            return t
    return 10 if open_year > 2030 else 5


def txo_num(q, key, dflt, lo, hi):
    try:
        v = float(str(q.get(key)).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return dflt
    return min(hi, max(lo, v))


def txo_tax(base, year, rate15):
    """Налог с положительной базы: при ставке 15 % плательщика — плоско 15 %, иначе прогрессия tx_ndfl."""
    base = max(0.0, base)
    return base * TXO_IIS_RATE_HI if rate15 else tx_ndfl(base, year)[0]


# ── сбор убытков ──

def txo_best_prefix(lots, price, fee_rate):
    """Лоты продаются от старых к новым (FIFO), поэтому доступны только префиксы. Результат кусочно-линеен по количеству,
    значит минимум достигается на границе лота. Возвращает (количество, результат) префикса с наибольшим убытком."""
    best_q, best_r, cq, cr = 0.0, 0.0, 0.0, 0.0
    for l in sorted(lots, key=lambda l: l["date"] or date(1970, 1, 1)):
        cq += l["qty"]
        cr += l["qty"] * (price * (1.0 - fee_rate) - l["unit"])
        if cr < best_r - 1e-9:
            best_q, best_r = cq, cr
    return best_q, best_r


def txo_ldv_flags(rows, lots, today, rate):
    out = []
    blind = {l["date"] for l in lots if l.get("blind")}
    for r in rows:
        if r["result"] <= 0 or r["type"] not in TAX_LDV_TYPES or r["bdate"] is None or r["bdate"] in blind or r["bdate"] < TAX_LDV_FROM:
            continue
        if r["ldv"]:
            out.append({"status": "reached", "bdate": r["bdate"].isoformat(), "days": 0, "qty": r["qty"], "gain": r["result"], "tax_at_stake": 0.0})
            continue
        days = (tx_add_years(r["bdate"], 3) + timedelta(days=1) - today).days
        if 0 < days <= 365:
            out.append({"status": "close", "bdate": r["bdate"].isoformat(), "days": days, "qty": r["qty"], "gain": r["result"], "tax_at_stake": r["result"] * rate})
    return out


def txo_harvest_calc(st, settings, fee_rate=None, min_loss=TXO_MIN_LOSS, holidays=()):
    today, cy = st["today"], st["today"].year
    fee_src = "заданная" if fee_rate is not None else "по истории сделок"
    if fee_rate is None:
        fee_rate = st["eng"]["fee_rate"]
    sale_day, last_day = tx_last_sale_day(cy, holidays)
    out = {"available": False, "year": cy, "today": today.isoformat(), "fee_rate": fee_rate, "fee_source": fee_src, "candidates": [], "iis_excluded": [],
           "deadline": {"sale_day": sale_day.isoformat(), "last_trading_day": last_day.isoformat(), "days": (sale_day - today).days, "passed": today > sale_day},
           "totals": {"saving": 0.0, "fees": 0.0, "net": 0.0, "n": 0}, "warnings": list(st["eng"].get("warnings") or []), "reason": "",
           "iis_prefill": txo_iis_prefill(st)}
    for g in st["groups"]:
        if g["kind"] == "iis":
            out["iis_excluded"].append({"name": g["name"], "reason": "ИИС — отдельная налоговая база: убыток внутри счёта не уменьшает налог по обычным счетам "
                                        "(тип А — налог считается при закрытии счёта, тип Б и ИИС-3 при соблюдённом сроке освобождены), поэтому сбор убытков здесь не моделируется."})
    gen = [g for g in st["groups"] if g["kind"] == "gen"]
    if not gen:
        out["reason"] = "Среди выбранных счетов нет обычных брокерских счетов (только ИИС)."
        return out
    if not st["pos"]:
        out["reason"] = "Нет данных о текущих позициях и ценах (нет токена, пустой портфель или демо-режим без позиций)."
        return out
    g = gen[0]
    out["available"] = True
    t0, row0 = tx_cur_tax(g, [], cy, settings)
    base0 = (row0 or {}).get("base", 0.0)
    thr = TXO_HI_THRESHOLD if cy >= 2025 else 5000000.0
    rate0 = 0.15 if base0 > thr else 0.13
    out.update(tax_before=t0, base_before=base0, rate_now=rate0, threshold=thr)
    cands = []
    for uid, lots in tx_group_open(st, g).items():
        pr = tx_pos_price(st["pos"].get(uid))
        if not pr or lots[0]["type"] in TAX_SKIP_TYPES or lots[0]["type"] == "option":
            continue
        q, res = txo_best_prefix(lots, pr, fee_rate)
        if q <= 0 or res > -min_loss:
            continue
        base = {"acc": lots[0]["acc"], "uid": uid, "name": lots[0]["name"], "ticker": lots[0]["ticker"], "type": lots[0]["type"], "bucket": "sec",
                "kind": "sell", "bdate": None}
        rows = tx_fee_sim(lots, q, pr, fee_rate, today, base)
        res = sum(r["result"] for r in rows)
        total_q = sum(l["qty"] for l in lots)
        value = q * pr
        t1, row1 = tx_cur_tax(g, rows, cy, settings)
        base1 = (row1 or {}).get("base", 0.0)
        fee_sell = sum(r["fee"] for r in rows)
        fee_buy = value * fee_rate
        saving = t0 - t1
        carry = max(0.0, ((row1 or {}).get("loss_new", 0.0)) - ((row0 or {}).get("loss_new", 0.0)))
        cands.append({"uid": uid, "name": base["name"], "ticker": base["ticker"], "type": base["type"], "qty": q, "qty_total": total_q, "partial": q < total_q - 1e-9,
                      "price": pr, "value": value, "loss": -res, "gain_in_prefix": sum(r["result"] for r in rows if r["result"] > 0),
                      "base_before": base0, "base_after": base1, "tax_before": t0, "tax_after": t1, "saving": saving,
                      "marginal_rate": (saving / (base0 - base1)) if base0 - base1 > 1 else None, "carry_forward": carry,
                      "fees": fee_sell + fee_buy, "net": saving - fee_sell - fee_buy, "ldv": txo_ldv_flags(rows, lots, today, rate0),
                      "blind": any(l.get("blind") for l in lots), "rows": rows})
    cands.sort(key=lambda c: -c["net"])
    extra, tot_fee = [], 0.0
    for c in cands:
        c["selected"], c["saving_marginal"] = False, 0.0
        if c["net"] <= 1:
            continue
        tp, _ = tx_cur_tax(g, extra, cy, settings)
        tn, _ = tx_cur_tax(g, extra + c["rows"], cy, settings)
        c["saving_marginal"] = tp - tn
        if c["saving_marginal"] - c["fees"] > 1:
            c["selected"] = True
            extra = extra + c["rows"]
            tot_fee += c["fees"]
    t_all, _ = tx_cur_tax(g, extra, cy, settings)
    n_sel = sum(1 for c in cands if c["selected"])
    out["totals"] = {"saving": t0 - t_all, "fees": tot_fee, "net": (t0 - t_all) - tot_fee, "n": n_sel, "tax_after": t_all}
    for c in cands:
        c.pop("rows", None)
    out["candidates"] = cands[:30]
    out["assumptions"] = [
        "Продажа списывает лоты по FIFO (старые первыми), поэтому для каждой бумаги берётся такой префикс лотов, при котором реализованный убыток наибольший; прибыльные лоты внутри префикса уже учтены в расчёте.",
        "Экономия = налог года до сделок минус налог после (по движку страницы «Налоги»: сальдирование внутри группы обычных счетов, ставки 13 % и 15 %, ЛДВ, перенос убытков). Убыток сверх налоговой базы налог года не снижает, а переносится на будущие годы — показан отдельно.",
        "Расходы: комиссия на продажу и на обратную покупку по ставке %s (%s); спред не учтён." % (txo_pct(fee_rate), fee_src),
        "Запрета на «мнимые» сделки (wash sale) в российском налоговом праве нет, но обратная покупка обнуляет срок владения: ЛДВ по новым бумагам отсчитывается заново.",
        "Продажа должна рассчитаться в текущем году: при расчётах T+1 последний день сделки показан выше; календарь торгов определяет биржа."]
    if not settings.get("offset_coupons") and t0 > 0 and cands:
        out["assumptions"].insert(0, "Убытки от продаж сейчас не уменьшают налог с купонов: в настройках страницы «Налоги» выключен зачёт убытков "
                                     "против купонного дохода. Если брокер или декларация его применяют, включите настройку — экономия пересчитается.")
    return out


def txo_pct(x):
    return ("%.2f %%" % (x * 100.0)).replace(".", ",")


def txo_iis_prefill(st):
    for i in st.get("iis") or []:
        if i.get("opened"):
            return {"open_year": int(i["opened"][:4]), "type": i["type"], "name": i["name"], "opened": i["opened"]}
    return None


def txo_harvest_get(cfg, acc, q, force):
    st, settings = tax_state(cfg, acc, force)
    fr = txo_num(q, "fee", -1.0, -1.0, 5.0) if q.get("fee") not in (None, "") else -1.0
    return txo_harvest_calc(st, settings, fr / 100.0 if fr >= 0 else None, txo_num(q, "min_loss", TXO_MIN_LOSS, 0.0, 1e9))


# ── планировщик ИИС-3 ──

def txo_iis3_calc(open_year, contrib, yield_pct, years, income=0.0, rate15=None, reinvest=True, coupon_share=0.5, ldv=True):
    """Сравнение ИИС-3 и обычного брокерского счёта. Модель: взнос в начале года, доходность начисляется в конце года, вычет за год i
    поступает в начале года i+1 (вычет последнего года — наличными после горизонта). Реинвестированный вычет считается взносом сверх плана.
    income > 0 — годовой доход плательщика: определяет ставку (15 % выше 2,4 млн) и ограничивает вычет уплаченным НДФЛ."""
    years = max(1, int(years))
    open_year = int(open_year)
    y = yield_pct / 100.0
    if income > 0:
        rate15 = income > TXO_HI_THRESHOLD
    rate15 = bool(rate15)
    rate = TXO_IIS_RATE_HI if rate15 else TXO_IIS_RATE_LO
    term = txo_iis3_term(open_year)
    ded_base = min(contrib, TXO_IIS_LIMIT)
    # ИИС
    cap, dep, cash, refunds, rows, ref_prev = 0.0, 0.0, 0.0, [], [], 0.0
    # обычный счёт: лоты (стоимость, оценка, год покупки)
    lots, paid_tax = [], 0.0
    for i in range(1, years + 1):
        yr = open_year + i - 1
        if ref_prev > 0:
            if reinvest:
                cap += ref_prev
                dep += ref_prev
            else:
                cash += ref_prev
        cap += contrib
        dep += contrib
        cap *= 1.0 + y
        ref = ded_base * rate
        if income > 0:
            ref = min(ref, tx_ndfl(income, yr)[0])
        refunds.append(ref)
        ref_prev = ref
        # обычный счёт
        lots.append([contrib, contrib, i])
        cp_tax = 0.0
        for l in lots:
            coupon = l[1] * y * coupon_share
            t = txo_tax(coupon, yr, rate15)
            cp_tax += t
            l[1] += l[1] * y * (1.0 - coupon_share) + coupon - t
            l[0] += coupon - t       # реинвестированный купон после налога — новая стоимость покупки
        paid_tax += cp_tax
        rows.append({"year": yr, "n": i, "contribution": contrib, "deduct_base": ded_base, "refund": ref, "iis_capital": cap, "iis_deposits": dep,
                     "broker_capital": sum(l[1] for l in lots), "broker_coupon_tax": cp_tax, "own": contrib * i})

    def broker_exit(k, cur_lots):
        gain_all, gain_ldv, wy_num, wy_den = 0.0, 0.0, 0.0, 0.0
        for cost, val, i0 in cur_lots:
            g = max(0.0, val - cost)
            gain_all += g
            held = k - i0 + 1      # покупка в начале года, продажа в конце года k: срок больше 3 лет только при held >= 4
            if ldv and held > 3:
                gain_ldv += g
                wy_num += max(cost, 0.0) * held
                wy_den += max(cost, 0.0)
        wy = (wy_num / wy_den) if wy_den > 0 else 0.0
        exempt = min(gain_ldv, TAX_LDV_LIMIT * wy)
        return txo_tax(gain_all - exempt, open_year + k - 1, rate15), exempt

    fin_year = open_year + years - 1
    own = contrib * years
    bt, bex = broker_exit(years, lots)
    broker_net = sum(l[1] for l in lots) - bt
    met = years >= term
    gain = cap - dep
    if met:
        over = max(0.0, gain - TXO_IIS_EXEMPT_CAP)
        iis_tax = txo_tax(over, fin_year, rate15)
        returned = 0.0
        iis_net = cap + cash + refunds[-1] - iis_tax      # вычет последнего года приходит наличными после горизонта
    else:
        iis_tax = txo_tax(gain, fin_year, rate15)
        returned = sum(refunds[:-1])                      # полученные вычеты возвращаются, вычет последнего года не заявляется
        iis_net = cap + cash - iis_tax - returned
    # досрочное закрытие в каждый год до срока
    early = []
    for k in range(1, min(years, term - 1) + 1):
        r = rows[k - 1]
        cap_k, dep_k = r["iis_capital"], r["iis_deposits"]
        ref_got = sum(refunds[:k - 1])
        cash_k = 0.0 if reinvest else ref_got
        tax_k = txo_tax(cap_k - dep_k, open_year + k - 1, rate15)
        early.append({"year": r["year"], "n": k, "capital": cap_k, "deposits": dep_k, "refunds_returned": ref_got, "tax": tax_k,
                      "net": cap_k + cash_k - tax_k - ref_got, "own": contrib * k, "extra_cost": tax_k + ref_got})
    out = {"inputs": {"open_year": open_year, "contribution": contrib, "yield_pct": yield_pct, "years": years, "income": income, "rate15": rate15,
                      "reinvest": bool(reinvest), "coupon_share": coupon_share, "ldv": bool(ldv)},
           "rules": {"limit": TXO_IIS_LIMIT, "rate": rate, "max_refund": TXO_IIS_LIMIT * rate, "exempt_cap": TXO_IIS_EXEMPT_CAP, "term": term,
                     "term_ok": met, "term_end_year": open_year + term - 1,
                     "terms": [{"from": a, "to": b, "years": t} for a, b, t in TXO_IIS_TERMS] + [{"from": 2031, "to": None, "years": 10}]},
           "rows": rows, "early": early, "warnings": [],
           "iis": {"capital": cap, "deposits": dep, "tax": iis_tax, "refunds_total": sum(refunds), "refunds_returned": returned, "net": iis_net,
                   "result_over_own": iis_net - own, "term_met": met},
           "broker": {"capital": sum(l[1] for l in lots), "coupon_tax": paid_tax, "exit_tax": bt, "ldv_exempt": bex, "net": broker_net,
                      "result_over_own": broker_net - own},
           "own": own, "advantage": iis_net - broker_net}
    if open_year < 2024:
        out["warnings"].append("ИИС-3 открывают с 2024 года: для более ранних лет срок принят как для 2024–2026 (5 лет).")
    if contrib > TXO_IIS_LIMIT:
        out["warnings"].append("Взносы свыше 400 000 ₽ в год вычет не увеличивают: в расчёт вычета идёт только 400 000 ₽.")
    if not met:
        out["warnings"].append("Горизонт короче минимального срока (%d лет): счёт закрывается досрочно, вычеты возвращаются, налог платится с дохода." % term)
    return out


def txo_iis3_get(cfg, acc, q, force):
    now = date.today().year
    rate15 = None
    if q.get("bracket") in ("13", "15"):
        rate15 = q.get("bracket") == "15"
    flag = lambda k, d: (q.get(k) if q.get(k) not in (None, "") else d) not in ("0", "false", "")
    return txo_iis3_calc(int(txo_num(q, "open_year", now, 2000, 2100)), txo_num(q, "contribution", 400000.0, 0.0, 1e9),
                         txo_num(q, "yield", 12.0, -50.0, 100.0), int(txo_num(q, "years", 10, 1, 40)), txo_num(q, "income", 0.0, 0.0, 1e10), rate15,
                         flag("reinvest", "1"), txo_num(q, "coupon_share", 50.0, 0.0, 100.0) / 100.0, flag("ldv", "1"))


API_GET["/api/txo/harvest"] = txo_harvest_get
API_GET["/api/txo/iis3"] = txo_iis3_get
