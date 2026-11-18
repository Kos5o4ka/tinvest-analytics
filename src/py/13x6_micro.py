# ═══════════════ «Стакан: ликвидность»: проскальзывание крупной заявки и эвристика скрытой (айсберг) ликвидности ═══════════════
# Стакан и сделки — те же источники, что у «Кто покупает» (сервер данных md/* либо собственный токен T-Invest); бесплатные данные
# Мосбиржи (ISS) для стакана не используются. Окно снимков стакана и сделок хранится в памяти и копится только пока экран опрашивают.

MIC_PRESETS = (1e6, 5e6, 10e6)
MIC_BAND = (0.005, 0.01)                   # глубина в пределах ±0,5 % и ±1 % от середины
MIC_WINDOW = 600                           # окно наблюдения за стаканом и сделками, с
MIC_IDLE = 120                             # без опроса столько секунд — бумагу перестаём отслеживать
MIC_MAX_TRACKED = 5
MIC_TOP_LEVELS = 5
MIC_FACTOR = 2.0                           # исполнено не менее чем в 2 раза больше максимального видимого размера уровня
MIC_PERSIST = 0.7                          # доля снимков, в которых уровень присутствовал
MIC_MIN_SNAPS, MIC_MIN_SPAN = 3, 20        # минимум снимков и секунд наблюдения для вывода
MIC_DEPTH = 50
_mic_state, _mic_lock = {}, threading.Lock()


def _mic_rub(x):
    return format(int(round(x)), ",").replace(",", " ")


def _mic_f(x):
    try:
        return ("%.2f" % float(x)).rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return "—"


# ───────────────────────── параметры бумаги ─────────────────────────
def _mic_screener_hit(secid):
    try:
        rows = screener_rows() or []
    except Exception:  # noqa: BLE001
        return None
    u = secid.upper()
    return next((r for r in rows if str(r.get("id") or "").upper() == u or str(r.get("isin") or "").upper() == u), None)


def _mic_mdur(secid):
    """Модифицированная дюрация (годы) по строке скринера облигаций или None."""
    r = _mic_screener_hit(secid)
    if not r or not r.get("dur"):
        return None
    y = r.get("yield")
    return float(r["dur"]) / (1 + (float(y) / 100 if y is not None else 0))


def _mic_meta(cfg, secid):
    """{lot, face, is_bond[, face_assumed]} или None, если размер лота определить нельзя."""
    if cfg.get("token"):
        try:
            m = _flw_own_meta(TInvest(cfg), secid)
        except ApiError:
            m = None
        if m:
            m = dict(m)
            if m.get("is_bond") and not m.get("face"):
                m["face"], m["face_assumed"] = 1000.0, True
            return m
    hit = _mic_screener_hit(secid)
    if hit:
        return {"lot": 1, "face": float(hit.get("nominal") or 1000), "is_bond": True, "face_assumed": not hit.get("nominal")}
    try:
        u = globals().get("stocks_universe")
        h = next((r for r in (u() if u else []) if r.get("secid") == secid.upper()), None)
        if h and h.get("lot"):
            return {"lot": max(1, int(h["lot"])), "face": None, "is_bond": False}
    except Exception:  # noqa: BLE001
        pass
    return None


def _mic_norm_trades(rows, lot):
    """Сделки -> [{ts, side, price, lots}]; qty в штуках делится на лот."""
    out = []
    for t in rows or []:
        try:
            ts, p, q = t.get("ts"), float(t.get("price")), float(t.get("qty"))
        except (TypeError, ValueError, AttributeError):
            continue
        if ts is None or t.get("side") not in ("buy", "sell") or q <= 0:
            continue
        out.append({"ts": float(ts), "side": t["side"], "price": p, "lots": q / max(1, lot)})
    return out


def _mic_fetch(cfg, secid, depth=MIC_DEPTH):
    """Стакан и сделки. -> {ok, bids, asks, trades (в лотах, None — сделки недоступны), source, source_label, ts, meta}."""
    meta = _mic_meta(cfg, secid)
    book = _flw_ds("md/orderbook", {"secid": secid, "depth": depth}, FLW_BOOK_TTL)
    trades, src = None, ""
    if book:
        tr = _flw_ds("md/trades", {"secid": secid, "minutes": 60}, FLW_BOOK_TTL)
        if tr is not None:
            trades = _mic_norm_trades(tr.get("trades"), (meta or {}).get("lot") or 1)   # _md_trades отдаёт штуки (pieces = qty * lot)
        src = "server"
    else:
        try:
            own = _flw_own(cfg, secid, depth)
        except ApiError as e:
            return {"ok": False, "error": str(e)}
        if own:
            book, raw = own
            trades = _mic_norm_trades(raw, (meta or {}).get("lot") or 1) if hasattr(TInvest, "last_trades") else None
            src = "own"
    if not book:
        return {"ok": False, "error": "Стакан недоступен: на сервере данных нет токена T-Invest, а собственный токен не задан. "
                                       "Бесплатные данные Мосбиржи (ISS) стакан не содержат."}
    label = {"server": "T-Invest через сервер данных, реальное время", "own": "T-Invest по вашему токену, реальное время"}[src]
    return {"ok": True, "bids": _flw_levels(book.get("bids")), "asks": _flw_levels(book.get("asks")), "trades": trades,
            "source": src, "source_label": label, "ts": book.get("ts") or time.time(), "meta": meta}


# ───────────────────────── проскальзывание ─────────────────────────
def mic_rub_per_lot(meta):
    """Рублей на один лот при цене 1: акции — штук в лоте; облигации — лот × номинал / 100 (цена в % от номинала)."""
    lot = max(1, int(meta.get("lot") or 1))
    if meta.get("is_bond"):
        return lot * float(meta.get("face") or 1000.0) / 100.0
    return float(lot)


def mic_walk(levels, target_rub, k):
    """Проход по видимым уровням от лучшего; levels — [[цена, лоты]], k — рублей на лот при цене 1. Заявка — целое число лотов."""
    remaining, lots, spent, steps = float(target_rub), 0, 0.0, []
    stopped = False
    for p, q in levels:
        per = p * k
        if per <= 0:
            continue
        n = min(int(q), int(remaining // per))
        if n > 0:
            lots += n
            spent += n * per
            remaining -= n * per
            steps.append({"price": p, "lots": n, "rub": round(n * per, 2)})
        if n < int(q):
            stopped = True                      # на этом уровне денег хватило не на весь объём: заявка исполнена
            break
    min_per = min((p * k for p, _ in levels if p > 0), default=0.0)
    complete = lots > 0 and (stopped or remaining < min_per)
    return {"lots": lots, "rub": round(spent, 2), "unfilled_rub": round(max(0.0, remaining), 2), "complete": complete,
            "levels_used": len(steps), "steps": steps, "visible_lots": sum(int(q) for _, q in levels),
            "vwap": (spent / (lots * k)) if lots else None}


def mic_impact(book, meta, side, target_rub, mdur=None):
    """Расчёт заявки по стакану {bids, asks}: покупка идёт по продавцам (asks), продажа — по покупателям (bids)."""
    bids = sorted(book.get("bids") or [], key=lambda x: -x[0])
    asks = sorted(book.get("asks") or [], key=lambda x: x[0])
    if not bids or not asks:
        return {"ok": False, "error": "В стакане нет заявок с одной из сторон."}
    if side not in ("buy", "sell"):
        return {"ok": False, "error": "Сторона заявки: покупка или продажа."}
    k = mic_rub_per_lot(meta)
    bb, ba = bids[0][0], asks[0][0]
    mid = (bb + ba) / 2.0
    levels = asks if side == "buy" else bids
    w = mic_walk(levels, target_rub, k)
    out = {"ok": True, "side": side, "target_rub": target_rub, "mid": mid, "best_bid": bb, "best_ask": ba,
           "spread": ba - bb, "spread_bp": (ba - bb) / mid * 1e4, "crossed": bb >= ba, "is_bond": bool(meta.get("is_bond")),
           "lot": meta.get("lot"), "face": meta.get("face"), "filled_lots": w["lots"], "filled_rub": w["rub"],
           "unfilled_rub": w["unfilled_rub"], "complete": w["complete"], "levels_used": w["levels_used"], "steps": w["steps"],
           "visible_lots": w["visible_lots"], "visible_levels": len(levels), "vwap": w["vwap"]}
    if w["lots"]:
        sg = 1 if side == "buy" else -1
        out["slip_mid_bp"] = sg * (w["vwap"] - mid) / mid * 1e4
        out["slip_mid_rub"] = sg * (w["vwap"] - mid) * w["lots"] * k
        out["slip_best_bp"] = sg * (w["vwap"] - levels[0][0]) / levels[0][0] * 1e4
        out["depth_share"] = w["lots"] / w["visible_lots"] if w["visible_lots"] else None
        if meta.get("is_bond") and mdur:
            out["yield_bp"] = out["slip_mid_bp"] / mdur         # Δдоходности ≈ Δцены% / модифицированная дюрация
            out["mdur"] = mdur
    if not w["complete"]:
        total = sum(p * q * k for p, q in levels)
        out["warning"] = "Видимой ликвидности не хватает: исполнится %s из %s ₽ (видно %d ур., всего %s ₽ на этой стороне)." % (
            _mic_rub(w["rub"]), _mic_rub(target_rub), len(levels), _mic_rub(total))
    band = {}
    for x in MIC_BAND:
        band[str(x)] = {"bid_lots": sum(q for p, q in bids if p >= mid * (1 - x)), "ask_lots": sum(q for p, q in asks if p <= mid * (1 + x)),
                        "bid_rub": round(sum(p * q * k for p, q in bids if p >= mid * (1 - x))),
                        "ask_rub": round(sum(p * q * k for p, q in asks if p <= mid * (1 + x)))}
    out["depth_band"] = band
    return out


def mic_impact_get(cfg, acc, q, force):
    secid = _flw_secid(q)
    if not secid:
        raise ApiError("Не указана бумага.", 400)
    side = q.get("side") if q.get("side") in ("buy", "sell") else "buy"
    try:
        rub = float(str(q.get("rub") or 1e6).replace(",", "."))
    except ValueError:
        rub = 1e6
    rub = min(max(rub, 1000.0), 1e10)
    f = _mic_fetch(cfg, secid)
    if not f["ok"]:
        return {"ok": False, "secid": secid, "error": f["error"]}
    meta = f.get("meta")
    if not meta:
        return {"ok": False, "secid": secid, "error": "Не удалось определить размер лота бумаги: пересчёт в рубли невозможен."}
    mdur = _mic_mdur(secid) if meta.get("is_bond") else None
    book = {"bids": f["bids"], "asks": f["asks"]}
    res = mic_impact(book, meta, side, rub, mdur)
    if not res["ok"]:
        return dict(res, secid=secid, source_label=f["source_label"])
    keep = ("complete", "vwap", "slip_mid_bp", "slip_mid_rub", "depth_share", "filled_rub", "yield_bp")
    presets = []
    for p in MIC_PRESETS:
        r = mic_impact(book, meta, side, p, mdur)
        presets.append(dict({k: r.get(k) for k in keep}, rub=p))
    notes = ["Расчёт по видимому стакану (до %d уровней) на момент запроса: скрытый объём и изменение стакана при исполнении не учтены; комиссия не учтена. "
             "Проскальзывание — отклонение средневзвешенной цены исполнения от середины между лучшей покупкой и лучшей продажей." % MIC_DEPTH]
    if meta.get("is_bond"):
        notes.append("Облигации: цена в %% от номинала (%s ₽), сумма = цена × номинал / 100 × количество; накопленный купонный доход оплачивается сверху." % _mic_f(meta.get("face")))
        if meta.get("face_assumed"):
            notes.append("Номинал не получен, принят 1000 ₽.")
        if mdur is None:
            notes.append("Влияние на доходность не показано: модифицированная дюрация выпуска не найдена в скринере.")
    return dict(res, secid=secid, source=f["source"], source_label=f["source_label"], ts=f["ts"], presets=presets, notes=notes)


# ───────────────────────── эвристика скрытой ликвидности ─────────────────────────
def mic_ice_update(secid, book, trades, now=None):
    """Добавляет снимок стакана и сделки в окно бумаги. trades=None — сделки недоступны. Вызывается только при опросе."""
    now = time.time() if now is None else now
    with _mic_lock:
        for s in [s for s, st in _mic_state.items() if now - st["polled"] > MIC_IDLE]:
            del _mic_state[s]
        st = _mic_state.get(secid)
        if st is None:
            if len(_mic_state) >= MIC_MAX_TRACKED:
                del _mic_state[min(_mic_state, key=lambda s: _mic_state[s]["polled"])]
            st = _mic_state[secid] = {"snaps": [], "trades": {}, "polled": now, "have_trades": True}
        st["polled"] = now
        st["have_trades"] = trades is not None
        st["snaps"].append({"ts": now, "bids": {p: q for p, q in book.get("bids") or []}, "asks": {p: q for p, q in book.get("asks") or []}})
        first = st["snaps"][0]["ts"]
        cnt = {}
        for t in trades or []:
            if t["ts"] < first - 1 or t["ts"] > now + 5:
                continue
            key = (t["ts"], t["side"], t["price"], t["lots"])
            cnt[key] = cnt.get(key, 0) + 1
        for key, n in cnt.items():
            st["trades"][key] = max(st["trades"].get(key, 0), n)
        cut = now - MIC_WINDOW
        st["snaps"] = [s for s in st["snaps"] if s["ts"] >= cut]
        st["trades"] = {k: n for k, n in st["trades"].items() if k[0] >= cut}
    return st


def mic_ice_report(secid, now=None):
    """Разбор окна. Статусы: unavailable (нет сделок), collecting (мало данных), ready."""
    now = time.time() if now is None else now
    with _mic_lock:
        st = _mic_state.get(secid)
        if not st or now - st["polled"] > MIC_IDLE:
            return {"status": "collecting", "snapshots": 0, "observed_sec": 0, "window_sec": MIC_WINDOW, "candidates": []}
        snaps, trades, have = list(st["snaps"]), dict(st["trades"]), st["have_trades"]
    span = snaps[-1]["ts"] - snaps[0]["ts"]
    base = {"snapshots": len(snaps), "observed_sec": round(span), "window_sec": MIC_WINDOW, "candidates": []}
    if not have:
        return dict(base, status="unavailable", message="Детектор недоступен: для этого источника нет ленты сделок.")
    if len(snaps) < MIC_MIN_SNAPS or span < MIC_MIN_SPAN:
        return dict(base, status="collecting", message="Накапливаю наблюдения: нужно не менее %d снимков за %d с." % (MIC_MIN_SNAPS, MIC_MIN_SPAN))
    last = snaps[-1]
    cands, checked = [], 0
    for side, key, aggr in (("ask", "asks", "buy"), ("bid", "bids", "sell")):
        for p in sorted(last[key], reverse=(side == "bid"))[:MIC_TOP_LEVELS]:
            checked += 1
            series = [(s["ts"], s[key].get(p)) for s in snaps]
            i0 = next(i for i, (_, q) in enumerate(series) if q)
            tail = series[i0:]
            frac = sum(1 for _, q in tail if q) / len(tail)
            vmax = max(q for _, q in tail if q)
            drops, prev = 0, None
            for _, q in tail:
                qv = q or 0
                if prev is not None and qv < prev:
                    drops += prev - qv
                prev = qv
            ex = sorted((k[0], k[3]) for k, n in trades.items() if k[1] == aggr and k[2] == p and k[0] >= series[i0][0] - 1 for _ in range(n))
            executed = sum(l for _, l in ex)
            hidden = max(0.0, executed - drops)
            if executed >= MIC_FACTOR * vmax and frac >= MIC_PERSIST and hidden > 0:
                cands.append({"side": side, "price": p, "executed_lots": round(executed, 2), "visible_max_lots": vmax,
                              "visible_now_lots": series[-1][1], "visible_consumed_lots": round(drops, 2),
                              "hidden_est_lots": round(hidden, 2), "factor": round(executed / vmax, 1), "persist": round(frac, 2),
                              "first_seen": series[i0][0], "last_seen": series[-1][0],
                              "evidence": {"book": [[round(ts, 1), q] for ts, q in tail[-8:]], "trades": [[round(ts, 1), round(l, 2)] for ts, l in ex[-8:]]}})
    cands.sort(key=lambda c: -c["hidden_est_lots"])
    return dict(base, status="ready", candidates=cands, levels_checked=checked)


def mic_iceberg_get(cfg, acc, q, force):
    secid = _flw_secid(q)
    if not secid:
        raise ApiError("Не указана бумага.", 400)
    f = _mic_fetch(cfg, secid, 10)
    if not f["ok"]:
        return {"ok": False, "secid": secid, "error": f["error"]}
    mic_ice_update(secid, {"bids": f["bids"], "asks": f["asks"]}, f["trades"])
    rep = mic_ice_report(secid)
    return dict(rep, ok=True, secid=secid, source=f["source"], source_label=f["source_label"], ts=f["ts"],
                note="Эвристика, а не факт: уровень, на котором исполнено не менее чем в %d раза больше его максимального видимого размера и который держался "
                     "не менее %d %% снимков, может скрывать часть объёма. Результат зависит от свежести данных и частоты опроса; "
                     "окно — до %d мин и копится только пока экран открыт." % (MIC_FACTOR, MIC_PERSIST * 100, MIC_WINDOW // 60))


API_GET["/api/mic/impact"] = mic_impact_get
API_GET["/api/mic/iceberg"] = mic_iceberg_get
