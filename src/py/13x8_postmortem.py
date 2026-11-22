# ═══════════════════ разбор сделок (Trade Post-Mortem по FIFO) и призрачный портфель (Cashflow-Matched) ═══════════════════
# Детерминированный анализ истории операций без ИИ:
# 1) Trade Post-Mortem: Win Rate, Profit Factor, средний выигрыш/убыток, Disposition Effect (срок удержания убытков vs прибыли);
# 2) Призрачный портфель: моделирование тех же пополнений и выводов в те же даты в фондах LQDT и TMOS.


def pm_trades_stats(sales):
    """Статистика по закрытым сделкам FIFO из tax_state (g['sales']). Группирует частичные исполнения одной продажи (uid, sdate)."""
    grouped = {}
    for s in sales or []:
        if s.get("bucket") != "sec":
            continue
        sd = s.get("sdate")
        bd = s.get("bdate")
        if sd is None:
            continue
        sd_iso = sd.isoformat() if hasattr(sd, "isoformat") else str(sd)[:10]
        key = (s.get("uid") or s.get("ticker") or s.get("name"), sd_iso, s.get("kind") or "sell")
        g = grouped.get(key)
        hold = (sd - bd).days if (bd is not None and hasattr(sd, "__sub__")) else None
        if g is None:
            g = grouped[key] = {"name": s.get("name") or s.get("ticker") or "", "ticker": s.get("ticker") or "",
                                "type": s.get("type") or "other", "sdate": sd_iso, "qty": 0.0,
                                "cost": 0.0, "proceeds": 0.0, "result": 0.0, "hold_num": 0.0, "hold_den": 0.0}
        q = float(s.get("qty") or 0.0)
        c = float(s.get("cost") or 0.0)
        g["qty"] += q
        g["cost"] += c
        g["proceeds"] += float(s.get("proceeds") or 0.0)
        g["result"] += float(s.get("result") or 0.0)
        if hold is not None and hold >= 0:
            w = max(abs(c), q, 1.0)
            g["hold_num"] += hold * w
            g["hold_den"] += w

    trades = []
    for g in grouped.values():
        res = round(g["result"], 2)
        cost = round(g["cost"], 2)
        pct = round(res / cost * 100.0, 2) if cost > 1.0 else None
        hold = round(g["hold_num"] / g["hold_den"], 1) if g["hold_den"] > 0 else None
        trades.append({"name": g["name"], "ticker": g["ticker"], "type": g["type"], "sdate": g["sdate"],
                       "cost": cost, "proceeds": round(g["proceeds"], 2), "result": res, "pct": pct, "hold_days": hold})

    if not trades:
        return {"n": 0, "wins": 0, "losses": 0, "win_rate": None, "profit_factor": None, "net_pnl": 0.0,
                "gross_profit": 0.0, "gross_loss": 0.0, "avg_win": None, "avg_loss": None,
                "avg_hold_win": None, "avg_hold_loss": None, "disposition_ratio": None, "disposition_flag": False,
                "by_type": [], "best": [], "worst": []}

    wins = [t for t in trades if t["result"] > 0.01]
    losses = [t for t in trades if t["result"] < -0.01]
    gp = sum(t["result"] for t in wins)
    gl = sum(t["result"] for t in losses)
    n_dec = len(wins) + len(losses)
    wr = round(len(wins) / n_dec * 100.0, 1) if n_dec else None
    pf = round(gp / abs(gl), 2) if abs(gl) > 1.0 else (None if not wins else 99.9)
    hw = [t["hold_days"] for t in wins if t["hold_days"] is not None]
    hl = [t["hold_days"] for t in losses if t["hold_days"] is not None]
    avg_hw = round(sum(hw) / len(hw), 1) if hw else None
    avg_hl = round(sum(hl) / len(hl), 1) if hl else None
    disp = round(avg_hl / avg_hw, 2) if (avg_hl is not None and avg_hw and avg_hw >= 1.0) else None

    by_t = {}
    for t in trades:
        b = by_t.setdefault(t["type"], {"type": t["type"], "n": 0, "wins": 0, "result": 0.0})
        b["n"] += 1
        if t["result"] > 0.01:
            b["wins"] += 1
        b["result"] += t["result"]
    by_type = sorted((dict(v, result=round(v["result"], 2), win_rate=round(v["wins"] / v["n"] * 100.0, 1))
                      for v in by_t.values()), key=lambda x: -x["n"])

    trades_by_res = sorted(trades, key=lambda t: t["result"])
    return {"n": len(trades), "wins": len(wins), "losses": len(losses), "win_rate": wr,
            "profit_factor": pf, "net_pnl": round(gp + gl, 2), "gross_profit": round(gp, 2), "gross_loss": round(gl, 2),
            "avg_win": round(gp / len(wins), 2) if wins else None,
            "avg_loss": round(gl / len(losses), 2) if losses else None,
            "avg_hold_win": avg_hw, "avg_hold_loss": avg_hl,
            "disposition_ratio": disp, "disposition_flag": bool(disp is not None and disp >= 1.35 and len(losses) >= 3),
            "by_type": by_type,
            "best": list(reversed(trades_by_res[-8:])), "worst": trades_by_res[:8]}


def pm_ghost_portfolio(hist):
    """Призрачный портфель (Cashflow-Matched): те же внешние пополнения/выводы (изменение invested),
    вложенные в те же даты в бенчмарки (LQDT, TMOS)."""
    days = (hist or {}).get("days") or []
    vals = (hist or {}).get("value") or []
    invs = (hist or {}).get("invested") or []
    bench = (hist or {}).get("bench") or {}
    if len(days) < 2 or len(vals) != len(days) or len(invs) != len(days):
        return {"ok": False, "items": [], "days": [], "real": [], "series": {}}

    real_end = float(vals[-1])
    inv_end = float(invs[-1])
    items = []
    series = {}
    for code in ("LQDT", "TMOS"):
        prices = bench.get(code)
        if not prices or len(prices) != len(days):
            continue
        units = 0.0
        cash_wait = 0.0
        curve = []
        valid = False
        for i in range(len(days)):
            flow = float(invs[i]) - (float(invs[i - 1]) if i > 0 else 0.0)
            p = prices[i]
            if p and p > 0:
                valid = True
                if cash_wait:
                    units = max(0.0, units + cash_wait / p)     # минус = выводы до первой цены: продаём юниты (не ниже 0)
                    cash_wait = 0.0
                units = max(0.0, units + flow / p)      # вывод больше стоимости бенчмарка не делает его шортом
                gv = max(0.0, units * p)
            else:
                cash_wait += flow
                gv = max(0.0, cash_wait)
            curve.append(round(gv, 2))
        if not valid:
            continue
        g_end = curve[-1]
        diff = round(real_end - g_end, 2)
        diff_pct = round(diff / g_end * 100.0, 2) if g_end > 100 else None
        items.append({"code": code, "name": "Денежный рынок (LQDT)" if code == "LQDT" else "Индекс МосБиржи (TMOS)",
                      "ghost_val": round(g_end, 2), "real_val": round(real_end, 2), "invested": round(inv_end, 2),
                      "diff_rub": diff, "diff_pct": diff_pct})
        series[code] = curve

    # Прореживаем до ~180 точек для лёгкого графика
    step = max(1, len(days) // 180)
    idx = list(range(0, len(days), step))
    if idx[-1] != len(days) - 1:
        idx.append(len(days) - 1)
    return {"ok": bool(items), "real_val": round(real_end, 2), "invested": round(inv_end, 2),
            "items": items, "days": [days[i] for i in idx], "real": [vals[i] for i in idx],
            "series": {k: [v[i] for i in idx] for k, v in series.items()}}


def _api_postmortem(cfg, acc, q, force):
    try:
        st, _ = tax_state(cfg, acc, force)
        sales = [s for g in st.get("groups") or [] for s in (g.get("sales") or [])]
        trades = pm_trades_stats(sales)
    except Exception as e:  # noqa: BLE001
        trades = {"n": 0, "error": str(e)[:140]}
    try:
        hist = build_history_for(cfg, acc, force)
        ghost = pm_ghost_portfolio(hist)
    except Exception:  # noqa: BLE001
        ghost = {"ok": False, "items": [], "days": [], "real": [], "series": {}}
    return {"trades": trades, "ghost": ghost}


API_GET["/api/postmortem"] = _api_postmortem
