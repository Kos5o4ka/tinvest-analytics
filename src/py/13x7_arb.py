# ═══════════════════ арбитраж внутри кривой эмитента, инверсия кривой (EWS) и рубль vs валюта ═══════════════════
# Детерминированный анализ скринера облигаций Мосбиржи без ИИ:
# 1) перекосы доходности внутри кривой одного эмитента при близкой дюрации + срок окупаемости перекладки;
# 2) инверсия кривой одного эмитента (короткий выпуск заметно дороже по YTM длинного — ранний сигнал стресса);
# 3) сравнение рублёвых и валютных (USD/EUR/CNY) выпусков того же эмитента — безубыточная девальвация рубля после НДФЛ.


def _arb_key(r):
    """Ключ группировки эмитента для облигаций скринера."""
    k = issuer_group_key(r.get("name") or "")
    if k:
        return k
    toks = sorted(name_tokens(r.get("name") or ""))
    return " ".join(toks[:2]) if toks else ""


def _arb_rating_str(r):
    rt = r.get("rating")
    if isinstance(rt, dict):
        return rt.get("v")
    return rt if isinstance(rt, str) else None


def arb_compute(rows, fx_rates=None, fee_pct=0.05, tax_rate=0.13):
    """Чистый расчёт по строкам скринера -> {pairs, inversions, fx_vs_rub, stats}."""
    fx_rates = fx_rates or {}
    rub_groups = {}
    fx_groups = {}
    for r in rows or []:
        y = r.get("yield")
        dur = r.get("dur") or r.get("macdur")
        if y is None or dur is None or not (0.5 <= y <= 120.0) or dur < 0.15:
            continue
        if r.get("floating") or r.get("kind") != "corp":
            continue
        cur = (r.get("cur") or "RUB").upper()
        gk = _arb_key(r)
        if not gk:
            continue
        item = {"isin": r.get("isin") or r.get("id"), "name": r.get("name") or r.get("id"),
                "yield": float(y), "dur": float(dur), "price": r.get("price"), "cur": cur,
                "turn": float(r.get("turn") or 0.0), "rating": _arb_rating_str(r),
                "offer": r.get("offer"), "mat": r.get("mat"), "group": gk}
        if cur == "RUB":
            rub_groups.setdefault(gk, []).append(item)
        elif cur in ("USD", "EUR", "CNY"):
            fx_groups.setdefault(gk, []).append(item)

    # 1. Арбитраж внутри кривой одного эмитента (близкая дюрация, разница YTM >= 0.8 п.п.)
    switch_cost_pct = 2.0 * max(0.0, float(fee_pct)) + 0.20    # комиссия продажи+покупки + оценка бид-аск спреда 0.2%
    pairs = []
    for gk, bs in rub_groups.items():
        if len(bs) < 2:
            continue
        best = None
        for i in range(len(bs)):
            for j in range(len(bs)):
                if i == j:
                    continue
                cheap, rich = bs[i], bs[j]
                if cheap["yield"] > 60 or rich["yield"] > 60:
                    continue
                dy = cheap["yield"] - rich["yield"]
                dd = abs(cheap["dur"] - rich["dur"])
                if dy < 0.8 or dd > 1.2:
                    continue
                if cheap["turn"] <= 0 and rich["turn"] <= 0:
                    continue
                net_dy = dy * (1.0 - tax_rate)
                payback_mo = round(switch_cost_pct / net_dy * 12.0, 1) if net_dy > 0 else None
                cand = {"issuer": gk, "rating": cheap["rating"] or rich["rating"],
                        "buy": cheap, "sell": rich,
                        "spread_bp": int(round(dy * 100)), "dur_diff": round(dd, 2),
                        "switch_cost_pct": round(switch_cost_pct, 2), "payback_mo": payback_mo}
                if best is None or cand["spread_bp"] > best["spread_bp"]:
                    best = cand
        if best:
            pairs.append(best)
    pairs.sort(key=lambda x: -x["spread_bp"])

    # 2. Детектор инверсии кривой эмитента (короткий выпуск заметно выше длинного по YTM — стресс ликвидности / EWS)
    inversions = []
    for gk, bs in rub_groups.items():
        if len(bs) < 2:
            continue
        by_d = sorted(bs, key=lambda b: b["dur"])
        short_b = next((b for b in by_d if b["dur"] <= 1.5 and b["yield"] >= 18.0), None)
        if not short_b:
            continue
        long_cands = [b for b in by_d if b["dur"] >= short_b["dur"] + 0.7]
        if not long_cands:
            continue
        long_b = min(long_cands, key=lambda b: b["yield"])
        inv = short_b["yield"] - long_b["yield"]
        if inv >= 2.5:
            inv_bp = int(round(inv * 100))
            sev = "high" if (inv_bp >= 500 or short_b["yield"] >= 30.0) else "warn"
            inversions.append({"issuer": gk, "rating": short_b["rating"] or long_b["rating"],
                               "short": short_b, "long": long_b, "inv_bp": inv_bp,
                               "severity": sev, "n_bonds": len(bs)})
    inversions.sort(key=lambda x: -x["inv_bp"])

    # 3. Рубль vs Валюта у одного эмитента (безубыточная девальвация рубля после НДФЛ)
    fx_vs_rub = []
    for gk, fbs in fx_groups.items():
        rbs = [b for b in rub_groups.get(gk, []) if b["yield"] <= 45.0]
        if not rbs:
            continue
        for cur in ("USD", "CNY", "EUR"):
            cfs = [b for b in fbs if b["cur"] == cur and b["yield"] <= 30.0]
            if not cfs:
                continue
            # Берём пару с минимальной разницей по дюрации
            best_pair = min(((rb, fb, abs(rb["dur"] - fb["dur"])) for rb in rbs for fb in cfs), key=lambda x: x[2])
            rb, fb, dd = best_pair
            if dd > 2.5:
                continue
            yr = rb["yield"] / 100.0
            yf = fb["yield"] / 100.0
            # Без ЛДВ (единая ставка НДФЛ 13% на купон и валютную переоценку): множитель (1-t) сокращается
            be_pre = ((1.0 + yr) / (1.0 + yf) - 1.0) * 100.0
            # С ЛДВ (> 3 лет): валютная переоценка тела освобождается от НДФЛ, а купоны облагаются по 13% -> порог девальвации ниже
            yr_n = yr * (1.0 - tax_rate)
            yf_n = yf * (1.0 - tax_rate)
            be_ldv = ((1.0 + yr_n) / (1.0 + yf_n) - 1.0) * 100.0
            spot = fx_rates.get(cur)
            target_fx = round(spot * (1.0 + be_pre / 100.0), 2) if spot else None
            fx_vs_rub.append({"issuer": gk, "rating": rb["rating"] or fb["rating"], "cur": cur,
                              "rub": rb, "fx": fb, "dur_diff": round(dd, 2),
                              "be_pre_pct": round(be_pre, 2), "be_ldv_pct": round(be_ldv, 2),
                              "fx_now": round(spot, 2) if spot else None, "fx_breakeven_1y": target_fx})
    fx_vs_rub.sort(key=lambda x: x["be_pre_pct"])

    return {"pairs": pairs[:40], "inversions": inversions[:30], "fx_vs_rub": fx_vs_rub[:30],
            "stats": {"issuers_rub": len(rub_groups), "pairs": len(pairs), "inversions": len(inversions), "fx_pairs": len(fx_vs_rub)},
            "fee_pct": fee_pct, "tax_rate": tax_rate}


def _api_arb(cfg, acc, q, force):
    try:
        rows = screener_rows()
    except Exception as e:  # noqa: BLE001
        return {"error": "Не удалось загрузить скринер облигаций: %s" % str(e)[:140], "pairs": [], "inversions": [], "fx_vs_rub": []}
    today = date.today().isoformat()
    fx_rates = {}
    for c in ("USD", "CNY", "EUR"):
        try:
            v = tax_cbr_rate(c, today)
            if v:
                fx_rates[c] = v
        except Exception:  # noqa: BLE001
            pass
    try:
        fee = max(0.0, min(2.0, float(str(q.get("fee", "0.05")).replace(",", "."))))
    except ValueError:
        fee = 0.05
    return arb_compute(rows, fx_rates=fx_rates, fee_pct=fee)


API_GET["/api/arb"] = _api_arb
