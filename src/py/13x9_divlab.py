# ═══════════════════ дивидендные гэпы: лаборатория отсечки, радар по портфелю, оценка надёжности дивидендов ═══════════════════
# Чистая математика (без сети): dl_gaps / dl_stats / dl_payoff / dl_safety. Сеть — только в _dl_analyze (свечи ISS, дивиденды T-Invest/сервер, МСФО).
# Описательная статистика по прошлым отсечкам, не инвестиционная рекомендация.

DL_HORIZON = 250                      # торговых дней на закрытие гэпа
DL_WINDOWS = (30, 60, 90)
DL_T1_FROM = "2023-07-31"            # Мосбиржа перешла с расчётов T+2 на T+1
DL_TTL = 12 * 3600
DL_HIST = [("в день отсечки", 0, 0), ("1–5 дн.", 1, 5), ("6–20 дн.", 6, 20), ("21–60 дн.", 21, 60), ("61–120 дн.", 61, 120), ("121–250 дн.", 121, 250)]


def _dl_num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def dl_median(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    n = len(v)
    return float(v[n // 2]) if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def dl_gaps(divs, candles, horizon=DL_HORIZON):
    """Прошлые рублёвые дивиденды × дневные свечи -> гэпы отсечки.
    divs: [{record, value, cur?, last_buy?}], candles: [{t, o, h, l, c}] (t — ГГГГ-ММ-ДД). Результат — по возрастанию даты фиксации."""
    cs = sorted((c for c in candles or [] if c.get("t") and _dl_num(c.get("c")) is not None), key=lambda c: c["t"])
    if len(cs) < 3:
        return []
    ds = [c["t"][:10] for c in cs]
    out, seen = [], set()
    for d in sorted(divs or [], key=lambda x: x.get("record") or ""):
        rec, val = (d.get("record") or "")[:10], _dl_num(d.get("value"))
        if not rec or not val or val <= 0 or str(d.get("cur") or "RUB").upper() not in ("RUB", "RUR") or rec in seen:
            continue
        seen.add(rec)
        if rec > ds[-1] or rec <= ds[0]:
            continue
        lb = (d.get("last_buy") or "")[:10]
        if lb and ds[0] <= lb < rec and rec >= DL_T1_FROM:   # для отсечек эпохи T+2 T-Invest отдаёт last_buy по правилу T+1 — не верим
            i_last = bisect.bisect_right(ds, lb) - 1          # последний торговый день не позже last_buy
        else:
            # последний день покупки: за 1 торговый день до фиксации (T+1 с 31.07.2023), раньше — за 2 (T+2)
            i_last = bisect.bisect_left(ds, rec) - (1 if rec >= DL_T1_FROM else 2)
        if i_last < 0 or i_last + 1 >= len(cs):
            continue
        try:
            if (datetime.strptime(rec, "%Y-%m-%d") - datetime.strptime(ds[i_last], "%Y-%m-%d")).days > 10:
                continue                                      # дыра в данных: свечи не покрывают отсечку
        except ValueError:
            continue
        pre = _dl_num(cs[i_last]["c"])
        i_gap = i_last + 1
        post = _dl_num(cs[i_gap].get("o")) or _dl_num(cs[i_gap]["c"])
        if not pre or not post:
            continue
        gap = pre - post
        n_after = len(cs) - 1 - i_gap                         # торговых дней после дня гэпа в данных
        closed, days, mx = False, None, post
        for k in range(0, min(horizon, n_after) + 1):
            h = _dl_num(cs[i_gap + k].get("h")) or _dl_num(cs[i_gap + k]["c"])
            if h is not None and h > mx:
                mx = h
            if h is not None and h >= pre:
                closed, days = True, k
                break
        rec_pct = 100.0 if closed else (round((mx - post) / gap * 100.0, 1) if gap > 0 else 0.0)
        out.append({"record": rec, "last_buy": ds[i_last], "gap_day": ds[i_gap], "div": val, "p_pre": round(pre, 4), "p_post": round(post, 4),
                    "gap": round(gap, 4), "gap_pct": round(gap / pre * 100.0, 2), "div_pct": round(val / pre * 100.0, 2), "k": round(gap / val, 3),
                    "closed": closed, "days": days, "recovery_pct": rec_pct, "n_after": n_after})
    return out


def dl_stats(gaps, horizon=DL_HORIZON):
    """Сводка по гэпам: медиана дней до закрытия (только закрытые), доли закрытых за 30/60/90 дней (среди событий, по которым уже можно судить),
    число «ещё открытых» (слишком свежих), средняя k = гэп / дивиденд, гистограмма сроков закрытия."""
    gs = gaps or []
    closed = [g for g in gs if g["closed"]]
    win = {}
    for w in DL_WINDOWS:
        den = [g for g in gs if g["closed"] or g["n_after"] >= w]
        num = [g for g in den if g["closed"] and g["days"] <= w]
        win[str(w)] = {"n": len(num), "of": len(den), "pct": round(len(num) / len(den) * 100.0, 1) if den else None}
    still_open = [g for g in gs if not g["closed"] and g["n_after"] < DL_WINDOWS[-1]]
    ks = [g["k"] for g in gs]
    hist = [{"label": lb, "n": sum(1 for g in closed if lo <= g["days"] <= hi)} for lb, lo, hi in DL_HIST]
    hist.append({"label": "не закрыт", "n": sum(1 for g in gs if not g["closed"] and g["n_after"] >= DL_WINDOWS[-1])})
    hist.append({"label": "ещё открыт", "n": len(still_open)})
    return {"count": len(gs), "closed": len(closed), "median_days": dl_median([g["days"] for g in closed]), "within": win, "still_open": len(still_open),
            "avg_k": round(sum(ks) / len(ks), 3) if ks else None, "median_k": round(dl_median(ks), 3) if ks else None,
            "avg_gap_pct": round(sum(g["gap_pct"] for g in gs) / len(gs), 2) if gs else None, "hist": hist}


def dl_payoff(div, p_pre, p_post_est, cost, tax_rate, fee_rate):
    """На одну акцию, изменение стоимости от цены накануне p_pre: удержание = дивиденд после налога − гэп;
    продажа накануне и обратная покупка по p_buy (на 0,1 гэпа выше открытия) = −(p_buy − p_post) − комиссии − налог с продажи."""
    div, p_pre, p_post_est = float(div), float(p_pre), float(p_post_est)
    tax, fee = float(tax_rate or 0.0), float(fee_rate or 0.0)
    gap = p_pre - p_post_est
    hold = div * (1.0 - tax) - gap
    p_buy = p_post_est + 0.1 * gap
    tax_sale = tax * max(0.0, p_pre - cost) if cost is not None else 0.0
    sell = (p_post_est - p_buy) - 2.0 * fee * p_pre - tax_sale   # продали по p_pre, откупили по p_buy: в итоге та же акция по p_post_est плюс разница
    return {"div": round(div, 4), "p_pre": round(p_pre, 4), "p_post_est": round(p_post_est, 4), "gap": round(gap, 4),
            "gap_pct": round(gap / p_pre * 100.0, 2) if p_pre else None, "p_buy": round(p_buy, 4), "hold": round(hold, 4),
            "sell_rebuy": round(sell, 4), "diff": round(sell - hold, 4), "tax_sale": round(tax_sale, 4), "fees": round(2.0 * fee * p_pre, 4),
            "cost_known": cost is not None, "tax_rate": tax, "fee_rate": fee}


def dl_streak(years, today_year):
    """Подряд идущие календарные годы с выплатами, оканчивающиеся текущим или прошлым годом."""
    ys = set(years)
    y = today_year if today_year in ys else today_year - 1
    n = 0
    while y in ys:
        n += 1
        y -= 1
    return n


DL_ZONES = [(80, "надёжно", "pos"), (50, "умеренно", "warn"), (0, "высокий риск", "neg")]


def dl_zone(score):
    if score is None:
        return None
    return next(z for z in DL_ZONES if score >= z[0])


def dl_safety(fin):
    """Оценка надёжности дивиденда 0–100. fin: {fcf, div_total (оба млн ₽), nd_ebitda, roe (%), pay_years (подряд), bank}.
    Компонент без данных исключается, баллы пересчитываются на доступный вес; при доступных <50 % веса оценки нет."""
    fin = fin or {}
    comps, flags = [], []

    def add(cid, name, w, pts, val, note):
        comps.append({"id": cid, "name": name, "weight": w, "points": pts, "value": val, "note": note, "available": pts is not None})

    fcf, dt = _dl_num(fin.get("fcf")), _dl_num(fin.get("div_total"))
    if fin.get("bank"):
        net = _dl_num(fin.get("net"))
        if net is None or dt is None or dt <= 0:
            add("fcf", "Покрытие дивидендов прибылью", 40, None, None, "нет данных" if dt is None or net is None else "нет выплат за 12 мес.")
        elif net <= 0:
            flags.append("дивиденды выплачиваются при убытке")
            add("fcf", "Покрытие дивидендов прибылью", 40, 0, None, "чистая прибыль не положительна")
        else:
            po = dt / net
            pts = 40 if po <= 0.5 else 28 if po <= 0.7 else 16 if po <= 0.9 else 8 if po <= 1.0 else 0
            if pts == 0:
                flags.append("дивиденды больше чистой прибыли")
            add("fcf", "Покрытие дивидендов прибылью", 40, pts, round(po, 2), "дивиденды / чистая прибыль = %d %%" % round(po * 100))
    elif fcf is None or dt is None or dt <= 0:
        add("fcf", "Покрытие дивидендов свободным денежным потоком", 40, None, None, "нет данных" if dt is None or fcf is None else "нет выплат за 12 мес.")
    else:
        cov = fcf / dt
        pts = 40 if cov >= 1.3 else 30 if cov >= 1.0 else 15 if cov >= 0.7 else 0
        if pts == 0:
            flags.append("дивиденды больше свободного денежного потока")
        add("fcf", "Покрытие дивидендов свободным денежным потоком", 40, pts, round(cov, 2), "FCF / дивиденды = ×%.2f" % cov)
    nd = _dl_num(fin.get("nd_ebitda"))
    if fin.get("bank"):
        add("nd", "Чистый долг / EBITDA", 30, None, None, "не применимо к банкам и финансовым компаниям")
    elif nd is None:
        add("nd", "Чистый долг / EBITDA", 30, None, None, "нет данных")
    else:
        pts = 30 if nd < 1.5 else 20 if nd < 2.5 else 10 if nd < 3.5 else 0
        add("nd", "Чистый долг / EBITDA", 30, pts, round(nd, 2), "×%.2f" % nd)
    py = fin.get("pay_years")
    if py is None:
        add("track", "Стабильность выплат", 20, None, None, "нет данных")
    else:
        pts = 20 if py >= 5 else 15 if py >= 3 else 5
        add("track", "Стабильность выплат", 20, pts, py, "лет подряд с выплатами: %d" % py)
    roe = _dl_num(fin.get("roe"))
    if roe is None:
        add("roe", "Рентабельность капитала (ROE)", 10, None, None, "нет данных")
    else:
        pts = 10 if roe >= 20 else 5 if roe >= 10 else 0
        add("roe", "Рентабельность капитала (ROE)", 10, pts, round(roe, 1), "%.1f %%" % roe)
    avail = sum(c["weight"] for c in comps if c["available"])
    if avail < 50:
        return {"score": None, "zone": None, "label": None, "available_weight": avail, "components": comps, "flags": flags,
                "note": "Недостаточно данных для оценки (доступно %d %% веса)." % avail}
    score = int(round(sum(c["points"] for c in comps if c["available"]) / float(avail) * 100.0))
    z = dl_zone(score)
    return {"score": score, "zone": z[2], "label": z[1], "available_weight": avail, "components": comps, "flags": flags, "note": None}


# ── сеть: сбор данных по бумаге ──

def _dl_rub_divs(items):
    return [d for d in items or [] if str(d.get("cur") or "RUB").upper() in ("RUB", "RUR") and _dl_num(d.get("value"))]


def _dl_fin_inputs(secid, q, dv, divs, cfg):
    """Входы dl_safety: МСФО (FCF, долг) + мультипликаторы (ND/EBITDA, ROE) + число лет подряд с выплатами. Любой сбой -> компонент без данных."""
    today = date.today()
    out = {"fcf": None, "net": None, "div_total": None, "nd_ebitda": None, "roe": None, "bank": (q or {}).get("sector") == "Банки и финансы", "pay_years": None}
    years = {int(d["record"][:4]) for d in divs if d.get("record") and d["record"] <= today.isoformat()}
    if years:
        out["pay_years"] = dl_streak(years, today.year)
    try:
        fin = ifrs_fin(secid)
        if fin.get("bank"):
            out["bank"] = True
        c = (fin.get("ltm") or (fin.get("years") or [None])[-1]) if fin.get("status") == "ok" else None
        if c:
            out["fcf"] = c.get("fcf")
            out["net"] = c.get("net")
            out["nd_ebitda"] = c.get("nd_ebitda")
            if c.get("roe") is not None:
                out["roe"] = c["roe"] * 100
    except Exception:  # noqa: BLE001
        pass
    try:
        m = stock_multiples(secid, (q or {}).get("cap"), (q or {}).get("asset_uid"), cfg) or {}
        if m.get("nd_ebitda") is not None:
            out["nd_ebitda"] = m["nd_ebitda"]
        if m.get("roe") is not None:
            out["roe"] = m["roe"]
    except Exception:  # noqa: BLE001
        pass
    price, cap, ttm = (q or {}).get("price"), (q or {}).get("cap"), (dv or {}).get("ttm_value")
    if price and cap and ttm:
        out["div_total"] = ttm * (cap / price) / 1e6
    return out


def _dl_analyze(secid, cfg, q=None, force=False):
    """Тяжёлый расчёт по одной бумаге (кэш 12 ч): дивиденды, гэпы, надёжность. Ошибки сети — в поле error, не исключением."""
    secid = (secid or "").strip().upper()
    key = "dl_v2_%s_%d" % (secid, 1 if (cfg or {}).get("token") else 0)
    if not force:
        hit = store().get(key, DL_TTL)
        if hit:
            return hit
    err = []
    if q is None:
        try:
            q = next((r for r in stocks_universe(cfg=cfg) if r["secid"] == secid), None)
        except Exception as e:  # noqa: BLE001
            q = None
            err.append("список акций недоступен: %s" % str(e)[:80])
    q = q or {}
    candles = []
    try:
        candles = stock_candles(secid, 24, days=2400)
    except Exception as e:  # noqa: BLE001
        err.append("свечи Мосбиржи недоступны: %s" % str(e)[:80])
    price = q.get("price") or (candles[-1]["c"] if candles else None)
    dv = {}
    try:
        dv = stock_dividends(secid, price, q.get("uid"), cfg) or {}
    except Exception as e:  # noqa: BLE001
        err.append("дивиденды недоступны: %s" % str(e)[:80])
    divs = sorted(_dl_rub_divs(dv.get("items")), key=lambda d: d["record"])
    gaps = dl_gaps(divs, candles)
    safety = dl_safety(_dl_fin_inputs(secid, q, dv, divs, cfg))
    res = {"secid": secid, "name": q.get("shortname") or q.get("name") or secid, "sector": q.get("sector"), "price": price,
           "divs": [{k: d.get(k) for k in ("record", "payment", "last_buy", "value")} for d in divs], "gaps": gaps, "safety": safety,
           "div_source": dv.get("source"), "candles_to": candles[-1]["t"][:10] if candles else None, "candles_n": len(candles), "error": "; ".join(err) or None}
    if candles and divs and not err:
        try:
            store().put(key, res)
        except Exception:  # noqa: BLE001
            pass
    return res


def _dl_next(divs, today):
    """Ближайший будущий дивиденд (по дате фиксации); если нет — последний прошедший."""
    fut = sorted((d for d in divs if d["record"] >= today), key=lambda d: d["record"])
    past = sorted((d for d in divs if d["record"] < today), key=lambda d: d["record"])
    x = dict(fut[0], upcoming=True) if fut else dict(past[-1], upcoming=False) if past else None
    if x and not x.get("last_buy"):
        try:                                                  # оценка: предыдущий будний день (праздники не учтены)
            d = datetime.strptime(x["record"], "%Y-%m-%d") - timedelta(days=1)
            while d.weekday() > 4:
                d -= timedelta(days=1)
            x["last_buy"], x["last_buy_est"] = d.strftime("%Y-%m-%d"), True
        except ValueError:
            pass
    return x


def _dl_cost_map(cfg, acc):
    """Позиции-акции счёта: {тикер: {qty, avg, name}}. Без токена/счёта — пусто."""
    out = {}
    try:
        for r in build_summary(cfg, acc, "all")["portfolio"]["positions"]:
            if r.get("type") == "share" and (r.get("qty") or 0) > 0 and r.get("ticker"):
                o = out.setdefault(r["ticker"], {"qty": 0.0, "cost": 0.0, "name": r.get("name") or r["ticker"], "price": r.get("price")})
                o["qty"] += r["qty"]
                o["cost"] += (r.get("avg") or 0.0) * r["qty"]
    except Exception:  # noqa: BLE001
        return None
    for o in out.values():
        o["avg"] = o["cost"] / o["qty"] if o["qty"] else None
    return out


def _dl_stock_view(secid, cfg, acc, tax, fee, force):
    secid = (secid or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9._-]{1,16}", secid):
        raise ApiError("Некорректный тикер.", 400)
    a = _dl_analyze(secid, cfg, force=force)
    gaps = a["gaps"]
    st = dl_stats(gaps)
    today = date.today().isoformat()
    nx = _dl_next(a["divs"], today)
    pos = (_dl_cost_map(cfg, acc) or {}).get(secid) if acc else None
    payoff = None
    if nx and a.get("price"):
        k = st["median_k"] if st["median_k"] is not None else 1.0
        payoff = dl_payoff(nx["value"], a["price"], a["price"] - k * nx["value"], pos["avg"] if pos else None, tax, fee)
        payoff.update(record=nx["record"], upcoming=nx["upcoming"], k_used=round(k, 3), k_fallback=st["median_k"] is None,
                      qty=pos["qty"] if pos else None, held=bool(pos))
    return {"ok": True, "mode": "stock", "secid": secid, "name": a["name"], "sector": a["sector"], "price": a["price"], "gaps": list(reversed(gaps)),
            "stats": st, "safety": a["safety"], "next": nx, "payoff": payoff, "tax": tax, "fee": fee, "div_source": a["div_source"],
            "candles_to": a["candles_to"], "error": a["error"]}


def _dl_portfolio_view(cfg, acc, tax, force):
    pos = _dl_cost_map(cfg, acc)
    if pos is None:
        return {"ok": True, "mode": "portfolio", "rows": [], "held": 0, "error": "Не удалось получить позиции счёта.", "token": bool(cfg.get("token"))}
    if not pos:
        return {"ok": True, "mode": "portfolio", "rows": [], "held": 0, "error": None, "token": bool(cfg.get("token"))}
    try:
        uni = {r["secid"]: r for r in stocks_universe(cfg=cfg)}
    except Exception:  # noqa: BLE001
        uni = {}
    tickers = sorted(pos)

    def one(t):
        try:
            return _dl_analyze(t, cfg, uni.get(t), force)
        except Exception as e:  # noqa: BLE001
            return {"secid": t, "divs": [], "gaps": [], "safety": {"score": None}, "error": str(e)[:100], "name": pos[t]["name"], "price": pos[t].get("price")}
    res = pool_map(one, tickers, workers=6)
    today = date.today().isoformat()
    rows = []
    for t, a in zip(tickers, res):
        if not a.get("divs") and not a.get("gaps") and not a.get("price") and uni and t not in uni:
            continue                                            # не акция TQBR (например, зарубежная) — радар её не видит
        nx = _dl_next(a.get("divs") or [], today)
        st = dl_stats(a.get("gaps") or [])
        p = pos[t]
        row = {"secid": t, "name": a.get("name") or p["name"], "qty": p["qty"], "avg": p["avg"], "price": a.get("price") or p.get("price"),
               "next": nx if nx and nx["upcoming"] else None, "last": nx if nx and not nx["upcoming"] else None,
               "safety": (a.get("safety") or {}).get("score"), "zone": (a.get("safety") or {}).get("zone"), "label": (a.get("safety") or {}).get("label"),
               "median_days": st["median_days"], "events": st["count"], "median_k": st["median_k"], "within90": st["within"]["90"]["pct"], "error": a.get("error")}
        if row["next"]:
            row["net_total"] = round(row["next"]["value"] * p["qty"] * (1.0 - tax), 2)
            row["gross_total"] = round(row["next"]["value"] * p["qty"], 2)
        rows.append(row)
    rows.sort(key=lambda r: (0 if r["next"] else 1, r["next"]["record"] if r["next"] else "", r["secid"]))
    return {"ok": True, "mode": "portfolio", "rows": rows, "held": len(pos), "tax": tax, "error": None, "token": bool(cfg.get("token"))}


def _api_divlab(cfg, acc, q, force):
    def num(k, d, lo, hi):
        v = _dl_num(str(q.get(k) or "").replace(",", "."))
        return d if v is None else min(hi, max(lo, v))
    tax = num("tax", 13.0, 0.0, 35.0) / 100.0
    fee = num("fee", 0.05, 0.0, 2.0) / 100.0
    secid = (q.get("secid") or "").strip()
    try:
        if secid:
            return _dl_stock_view(secid, cfg, acc if q.get("account") else None, tax, fee, bool(force))
        return _dl_portfolio_view(cfg, acc, tax, bool(force))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": True, "mode": "stock" if secid else "portfolio", "rows": [], "gaps": [], "error": "Данные временно недоступны: %s" % str(e)[:120]}


API_GET["/api/divlab"] = _api_divlab
