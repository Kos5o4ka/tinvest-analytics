# ═══════════════════════════════ классификация операций ═══════════════════════════════

BUY = {"BUY", "BUY_CARD", "BUY_MARGIN", "DELIVERY_BUY"}
SELL = {"SELL", "SELL_CARD", "SELL_MARGIN", "DELIVERY_SELL"}
DIVS = {"DIVIDEND", "DIVIDEND_TRANSFER", "DIV_EXT"}
REPAY = {"BOND_REPAYMENT", "BOND_REPAYMENT_FULL"}
FEE_SERVICE = {"SERVICE_FEE", "CASH_FEE", "ADVICE_FEE"}
FEE_OTHER = {"SUCCESS_FEE", "TRACK_MFEE", "TRACK_PFEE", "OUT_FEE", "OUT_STAMP_DUTY", "OVER_COM", "OUTPUT_PENALTY"}
DEPOSIT = {"INPUT", "INPUT_SWIFT", "INPUT_ACQUIRING", "INP_MULTI"}
WITHDRAW = {"OUTPUT", "OUTPUT_SWIFT", "OUTPUT_ACQUIRING", "OUT_MULTI"}
TAXES = ("tax_trade", "tax_dividend", "tax_coupon", "tax_repo", "tax_other")
FEES = ("fee_broker", "fee_service", "fee_other", "margin_fee")
FLIP = set(TAXES) | set(FEES) | {"withdrawals"}


def op_type(o):
    return (o.get("type") or "").replace("OPERATION_TYPE_", "")


def classify(t):
    t = (t or "").replace("OPERATION_TYPE_", "")
    if t in BUY: return "buy"
    if t in SELL: return "sell"
    if t in DIVS: return "dividends"
    if t == "COUPON": return "coupons"
    if t in REPAY: return "repayments"
    if t in ("OVERNIGHT", "OVER_INCOME"): return "overnight"
    if t == "BROKER_FEE": return "fee_broker"
    if t == "MARGIN_FEE": return "margin_fee"
    if t in FEE_SERVICE: return "fee_service"
    if t in FEE_OTHER: return "fee_other"
    if t in ("ACCRUING_VARMARGIN", "WRITING_OFF_VARMARGIN"): return "varmargin"
    if "TAX" in t:
        if t.startswith("DIVIDEND_TAX"): return "tax_dividend"
        if t.startswith("BOND_TAX") or t == "TAX_CORRECTION_COUPON": return "tax_coupon"
        if t.startswith("TAX_REPO"): return "tax_repo"
        if t in ("TAX", "TAX_PROGRESSIVE", "TAX_CORRECTION", "TAX_CORRECTION_PROGRESSIVE"): return "tax_trade"
        return "tax_other"
    if t in DEPOSIT: return "deposits"
    if t in WITHDRAW: return "withdrawals"
    if t == "INPUT_SECURITIES": return "sec_in"
    if t == "OUTPUT_SECURITIES": return "sec_out"
    if t == "X_CONV_OUT": return "conv_out"      # служебные операции обмена бумаг (см. 07a_conversions.py)
    if t == "X_CONV_IN": return "conv_in"
    return "other"


def op_key(o):
    return o.get("id") or "%s|%s|%s|%s|%s" % (o.get("date"), o.get("type"), (o.get("payment") or {}).get("units"),
                                              (o.get("payment") or {}).get("nano"), o.get("instrumentUid") or o.get("figi"))


def op_qty(o):
    try:
        return int(Decimal(str(o.get("quantityDone") or o.get("quantity") or 0)))
    except Exception:  # noqa: BLE001
        return 0


def parse_dt(s):
    try:
        return datetime.strptime((s or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime((s or "")[:10], "%Y-%m-%d")
        except ValueError:
            return datetime(1970, 1, 1)


def ndfl_estimate(base, year):
    """НДФЛ с инвестиционного дохода: до 2021 — 13 %; 2021–2024 — 15 % свыше 5 млн; с 2025 — 15 % свыше 2,4 млн."""
    base = max(D0, base)
    if year < 2021:
        return base * Decimal("0.13")
    thr = Decimal(5_000_000 if year < 2025 else 2_400_000)
    return min(base, thr) * Decimal("0.13") + max(D0, base - thr) * Decimal("0.15")


def xirr(flows):
    if len(flows) < 2 or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    t0 = min(d for d, _ in flows)
    if (max(d for d, _ in flows) - t0).days < 30:
        return None
    pts = [((d - t0).days / 365.25, float(a)) for d, a in flows]

    def npv(r):
        return sum(a / (1 + r) ** t for t, a in pts)

    lo, hi = -0.99, 10.0
    f_lo = npv(lo)
    if f_lo * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f = npv(mid)
        if abs(f) < 1e-7:
            break
        if f_lo * f < 0:
            hi = mid
        else:
            lo, f_lo = mid, f
    return (lo + hi) / 2


def period_bounds(period, now):
    if period == "1m": return now - timedelta(days=30), None
    if period == "3m": return now - timedelta(days=91), None
    if period == "12m": return now - timedelta(days=365), None
    if period == "ytd": return datetime(now.year, 1, 1), None
    if period == "py": return datetime(now.year - 1, 1, 1), datetime(now.year, 1, 1)
    return None, None


def fifo(ops):
    """Позиции по сделкам методом FIFO: {uid: {qty, cost, last_unit}}, заодно результат продаж (op['_yield'])."""
    pos = defaultdict(lambda: {"lots": [], "last_unit": 0.0})
    moved = {}
    for o in ops:
        k = classify(o.get("type"))
        uid = o.get("instrumentUid") or o.get("figi")
        q = op_qty(o)
        if k == "conv_out" and uid:
            # обмен бумаг: лоты старой бумаги переходят в новую вместе со стоимостью
            lots = []
            for u in (o.get("_conv") or {}).get("old_uids") or [uid]:
                lots += pos[u]["lots"] if u in pos else []
                if u in pos:
                    pos[u]["lots"] = []
            moved[o.get("id")[:-4] if o.get("id") else uid] = lots
            continue
        if k == "conv_in" and uid:
            lots = moved.pop((o.get("id") or "")[:-3], [])
            r = (o.get("_conv") or {}).get("ratio") or 1
            left = q
            for lq, lu in lots:
                t = min(left, lq * r)
                if t > 0:
                    pos[uid]["lots"].append([t, lu / r])
                    left -= t
            continue
        if not uid or k not in ("buy", "sell", "sec_in", "sec_out", "repayments") or not q:
            if k == "repayments" and uid and op_type(o) == "BOND_REPAYMENT_FULL":
                pos[uid]["lots"] = []
            continue
        pay = abs(qf(o.get("payment")))
        unit = pay / q if q else 0.0
        p = pos[uid]
        if unit:
            p["last_unit"] = unit
        if k in ("buy", "sec_in"):
            if k == "sec_in" and not unit:
                unit = qf(o.get("price")) or p["last_unit"]
            p["lots"].append([q, unit])
        elif k in ("sell", "sec_out"):
            left, cost = q, 0.0
            while left > 0 and p["lots"]:
                lot = p["lots"][0]
                take = min(left, lot[0])
                cost += take * lot[1]
                lot[0] -= take
                left -= take
                if lot[0] <= 0:
                    p["lots"].pop(0)
            if k == "sell":
                o["_yield"] = pay - cost
        elif k == "repayments" and op_type(o) == "BOND_REPAYMENT_FULL":
            p["lots"] = []
    out = {}
    for uid, p in pos.items():
        qty = sum(l[0] for l in p["lots"])
        if qty:
            out[uid] = {"qty": qty, "cost": sum(l[0] * l[1] for l in p["lots"]), "last_unit": p["last_unit"]}
    return out


# ═══════════════════════════════ аналитика операций ═══════════════════════════════

def info_name(info, o=None):
    return (info or {}).get("name") or (o or {}).get("name") or (info or {}).get("ticker") or ""


def analyze(ops, names, period, portfolio_value):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    p_from, p_to = period_bounds(period, now)
    accs_with_broker_ops = {o.get("_acc") for o in ops if classify(o.get("type")) == "fee_broker"}
    dd = lambda: defaultdict(Decimal)
    totals, life, years, months = defaultdict(dd), dd(), defaultdict(dd), defaultdict(dd)
    flows, rows, by_inst = [], [], defaultdict(lambda: [D0, "", "", "", ""])

    for o in ops:
        kind = classify(o.get("type"))
        dt = parse_dt(o.get("date"))
        pay, cur = q2d(o.get("payment")), cur_of(o.get("payment"))
        comm, ccur = q2d(o.get("commission")), cur_of(o.get("commission"), cur)
        yv = o.get("yield")
        yld = q2d(yv) if yv else Decimal(str(o.get("_yield") or 0))
        ycur = cur_of(yv, cur) if yv else cur
        in_p = (p_from is None or dt >= p_from) and (p_to is None or dt < p_to)

        entries = []
        if kind == "buy":
            entries.append(("buy_turnover", cur, abs(pay)))
        elif kind == "sell":
            entries += [("sell_turnover", cur, abs(pay)), ("realized", ycur, yld)]
        elif kind not in ("other", "sec_in", "sec_out", "conv_in", "conv_out"):
            entries.append((kind, cur, -pay if kind in FLIP else pay))
        if kind in ("buy", "sell") and comm and o.get("_acc") not in accs_with_broker_ops:
            entries.append(("fee_broker", ccur, -comm if comm < 0 else comm))

        for cat, c, amt in entries:
            if c == "rub":
                life[cat] += amt
                years[dt.year][cat] += amt
            if in_p:
                totals[c][cat] += amt
                if c == "rub":
                    months[dt.strftime("%Y-%m")][cat] += amt

        if kind in ("deposits", "withdrawals") and cur == "rub" and pay:
            flows.append((dt, abs(pay) if kind == "withdrawals" else -abs(pay)))
        if not in_p:
            continue
        info = names.get(o.get("instrumentUid") or o.get("figi") or "") or {}
        nm = info_name(info, o) if (o.get("instrumentUid") or o.get("figi")) else (o.get("name") or o.get("description") or "")
        if kind in ("dividends", "coupons") and cur == "rub":
            k = info.get("uid") or nm or "—"
            b = by_inst[k]
            b[0] += pay
            b[1], b[2], b[3], b[4] = nm or "—", info.get("ticker") or "", info.get("logo") or "", info.get("type") or ""
        rows.append([
            (o.get("date") or "")[:16].replace("T", " "), op_type(o), kind, nm, info.get("ticker") or "",
            op_qty(o), float(q2d(o.get("price"))), float(pay), cur, float(comm), float(yld),
            info.get("logo") or "", o.get("_accname") or ""])

    invested = life["deposits"] - life["withdrawals"]
    pv = Decimal(str(portfolio_value or 0))
    rate = xirr(flows + ([(now, pv)] if pv > 0 else []))

    tax_rows = []
    for y in sorted(years):
        r = years[y]
        trade = r["realized"]
        income = r["dividends"] + r["coupons"] + r["overnight"]
        if not (trade or income or any(r[k] for k in TAXES)):
            continue
        est = ndfl_estimate(max(D0, trade) + income, y)
        withheld = sum(r[k] for k in TAXES)
        tax_rows.append({"year": y, "trade": float(trade), "income": float(income), "estimate": float(est),
                         "withheld": float(withheld), "diff": float(est - withheld)})

    f = lambda d: {k: float(v) for k, v in d.items()}
    income_by = sorted(([float(v[0]), v[1], v[2], v[3], v[4]] for v in by_inst.values()), key=lambda r: -r[0])[:15]
    return {
        "totals": {c: f(v) for c, v in totals.items()}, "life": f(life), "invested": float(invested), "xirr": rate,
        "profit": float(pv - invested) if life["deposits"] else None,
        "months": [[m, f(v)] for m, v in sorted(months.items())],
        "tax": tax_rows, "ops": rows[::-1], "income_by": income_by,
        "first_op": ops[0]["date"][:10] if ops else None,
    }


