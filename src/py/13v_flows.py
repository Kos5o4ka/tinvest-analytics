# ═══════════════ «Кто покупает»: потоки денег, крупные сделки, всплески объёма, стакан ═══════════════
# Данные считает сборщик на сервере данных (flows/*, md/*); здесь — обёртки с коротким кэшем, расчёт показателей стакана
# (дисбаланс, «плотности», баланс ленты) и тревоги по списку наблюдения. Нет сервера данных — пустые состояния; стакан и лента без
# токена сервера берутся по собственному токену пользователя (TInvest.order_book / last_trades, если эти методы есть в клиенте).

FLW_TTL = 30
FLW_BOOK_TTL = 1.5
FLW_WALL_MULT, FLW_IMB_LEVELS = 5.0, 10
FLW_PERIODS = ("5m", "1h", "day")
FLW_SRC = {"tinvest": "T-Invest, реальное время", "iss": "Мосбиржа, задержка 15 мин"}
_flw_cache, _flw_lock = {}, threading.Lock()
_flw_uid = {}


def _flw_ds(name, params, ttl=FLW_TTL):
    """ds_parsed с кэшем в памяти (≤ ttl секунд). None — сервер выключен/старый/нет данных."""
    key = name + "?" + "&".join("%s=%s" % kv for kv in sorted((params or {}).items()))
    now = time.time()
    with _flw_lock:
        c = _flw_cache.get(key)
        if c and now - c[0] < ttl:
            return c[1]
    try:
        v = ds_parsed(name, params or {}, timeout=8)
    except Exception:  # noqa: BLE001
        v = None
    with _flw_lock:
        if len(_flw_cache) > 400:
            _flw_cache.clear()
        _flw_cache[key] = (now, v)
    return v


def _flw_secid(q):
    s = str((q or {}).get("secid") or "").strip()
    return s if re.fullmatch(r"[A-Za-z0-9_.\-]{1,24}", s) else ""


def _flw_src_label(d):
    src = (d or {}).get("source") or ""
    return {"source": src, "source_label": FLW_SRC.get(src, ""), "delay_min": (d or {}).get("delay_min", 15 if src == "iss" else None)}


# ───────────────────────── математика стакана ─────────────────────────
def _flw_median(v):
    v = sorted(v)
    n = len(v)
    if not n:
        return 0.0
    return float(v[n // 2]) if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def flows_book_metrics(bids, asks, levels=FLW_IMB_LEVELS, wall_mult=FLW_WALL_MULT):
    """bids/asks — [[цена, количество]] от лучшей цены. Возвращает:
    imbalance — (Σbid − Σask)/(Σbid + Σask) по первым `levels` уровням, от −1 (давят продавцы) до +1 (давят покупатели);
    walls — «плотности»: уровни с количеством ≥ wall_mult × медианы количества по всем уровням стакана;
    spread, mid, bid_qty, ask_qty."""
    bids = [[float(p), float(q)] for p, q in (bids or [])]
    asks = [[float(p), float(q)] for p, q in (asks or [])]
    bq = sum(q for _p, q in bids[:levels])
    aq = sum(q for _p, q in asks[:levels])
    tot = bq + aq
    med = _flw_median([q for _p, q in bids + asks])
    walls = []
    if med > 0:
        for side, rows in (("bid", bids), ("ask", asks)):
            for p, q in rows:
                if q >= wall_mult * med:
                    walls.append({"side": side, "price": p, "qty": q, "mult": round(q / med, 1)})
    spread = mid = None
    if bids and asks:
        spread = asks[0][0] - bids[0][0]
        mid = (asks[0][0] + bids[0][0]) / 2.0
    return {"imbalance": round((bq - aq) / tot, 4) if tot > 0 else 0.0, "bid_qty": bq, "ask_qty": aq, "median_qty": med,
            "walls": walls, "spread": spread, "mid": mid}


def flows_tape_net(trades):
    """Баланс ленты: [{side, price, qty, value?}] -> {buy, sell, net, n} в рублях (value, иначе price × qty)."""
    buy = sell = 0.0
    for t in trades or []:
        v = t.get("value")
        v = float(v) if v is not None else float(t.get("price") or 0) * float(t.get("qty") or 0)
        if t.get("side") == "buy":
            buy += v
        elif t.get("side") == "sell":
            sell += v
    return {"buy": round(buy, 2), "sell": round(sell, 2), "net": round(buy - sell, 2), "n": len(trades or [])}


# ───────────────────────── стакан по собственному токену ─────────────────────────
def _flw_q(x):
    """Quotation/MoneyValue {units, nano} или число -> float."""
    if isinstance(x, dict):
        try:
            return int(x.get("units") or 0) + int(x.get("nano") or 0) / 1e9
        except (TypeError, ValueError):
            return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _flw_levels(rows):
    out = []
    for r in rows or []:
        if isinstance(r, dict):
            p, q = _flw_q(r.get("price")), _flw_q(r.get("quantity"))
        else:
            p, q = _flw_q(r[0]), _flw_q(r[1])
        if p is not None and q:
            out.append([p, q])
    return out


def _flw_iso_ts(s):
    """Разбор ISO-времени (в т.ч. с 9-значными наносекундами в Python 3.8–3.10) -> Unix timestamp или None."""
    s = str(s or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?", s)
        if not m:
            return None
        d = datetime.fromisoformat(m.group(1))
        if m.group(2):
            d = d.replace(microsecond=int(float(m.group(2)) * 1e6))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _flw_trade_rows(rows, lot=1, face=None, is_bond=False):
    lot = max(1, int(lot or 1))
    k = (float(face) / 100.0) if (is_bond and face) else (10.0 if is_bond else 1.0)
    out = []
    for t in rows or []:
        side = t.get("side") or str(t.get("direction") or "")
        side = "buy" if side == "buy" or side.endswith("BUY") else "sell" if side == "sell" or side.endswith("SELL") else ""
        p, q = _flw_q(t.get("price")), _flw_q(t.get("qty") if t.get("qty") is not None else t.get("quantity"))
        ts = t.get("ts")
        if ts is None and t.get("time"):
            ts = _flw_iso_ts(t["time"])
        if side and p is not None and q:
            pieces = q * lot
            out.append({"ts": ts, "side": side, "price": p, "qty": pieces, "value": round(p * pieces * k, 2)})
    return out


def _flw_own_meta(cli, secid):
    if secid in _flw_uid:
        m = _flw_uid[secid]
        return m if isinstance(m, dict) else {"uid": m, "lot": 1, "face": None, "is_bond": False}
    best = None
    for i in cli.find(secid) or []:
        if str(i.get("ticker") or "").upper() == secid.upper() and str(i.get("classCode") or "").startswith("TQ"):
            best = i
            break
        if best is None and str(i.get("ticker") or "").upper() == secid.upper():
            best = i
    uid = (best or {}).get("uid")
    if not uid:
        return None
    itype = str((best or {}).get("instrumentType") or "").lower()
    is_bond = itype == "bond" or str((best or {}).get("classCode") or "") in ("TQCB", "TQOB", "TQIR")
    lot = int((best or {}).get("lot") or 1)
    face = None
    if is_bond:
        try:
            bi = bond_info(cli, uid)
            if bi:
                face = bi.get("nominal")
                lot = int(bi.get("lot") or lot or 1)
        except Exception:  # noqa: BLE001
            pass
    elif lot <= 1:
        try:
            u = globals().get("stocks_universe")
            hit = next((r for r in (u() if u else []) if r.get("secid") == secid.upper()), None)
            if hit and hit.get("lot"):
                lot = int(hit["lot"])
        except Exception:  # noqa: BLE001
            pass
    meta = {"uid": uid, "lot": max(1, lot), "face": face, "is_bond": is_bond}
    _flw_uid[secid] = meta
    return meta


def _flw_own_uid(cli, secid):
    m = _flw_own_meta(cli, secid)
    return m["uid"] if m else None


def _flw_own(cfg, secid, depth):
    """Стакан и лента по токену пользователя; None, если токена нет или методов в клиенте нет."""
    if not cfg.get("token"):
        return None
    cli = TInvest(cfg)
    ob, lt = getattr(cli, "order_book", None), getattr(cli, "last_trades", None)
    if not ob:
        return None
    meta = _flw_own_meta(cli, secid)
    if not meta or not meta.get("uid"):
        return None
    uid = meta["uid"]
    raw = ob(uid, depth)
    book = {"bids": _flw_levels(raw.get("bids")), "asks": _flw_levels(raw.get("asks")), "ts": time.time()}
    trades = []
    if lt:
        now = datetime.now(timezone.utc)
        try:
            r = lt(uid, (now - timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ"))
            trades = _flw_trade_rows(r.get("trades") if isinstance(r, dict) else r,
                                     lot=meta.get("lot", 1), face=meta.get("face"), is_bond=meta.get("is_bond", False))
        except ApiError:
            trades = []
    return book, trades


# ───────────────────────── маршруты ─────────────────────────
def flows_get(cfg, acc, q, force):
    period = q.get("period") if q.get("period") in FLW_PERIODS else "1h"
    d = _flw_ds("flows/summary", {"period": period}, 0 if force else FLW_TTL)
    if d is None:
        return {"configured": False, "period": period, "data": None}
    return dict(d, configured=True, **_flw_src_label(d))


def _flw_since_arg(q):
    s = str(q.get("since") or "").strip()
    return s if re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{9,11}(\.\d+)?", s) else ""


def large_trades_get(cfg, acc, q, force):
    p = {"limit": 200}
    if _flw_since_arg(q):
        p["since"] = _flw_since_arg(q)
    if q.get("class") in ("share", "bond", "fund"):
        p["class"] = q["class"]
    try:
        mv = float(q.get("min") or 0)
        if mv > 0:
            p["min"] = int(mv)
    except ValueError:
        pass
    d = _flw_ds("flows/large", p, 0 if force else FLW_TTL)
    if d is None:
        return {"configured": False, "rows": []}
    return {"configured": True, "rows": d}


def spikes_get(cfg, acc, q, force):
    p = {"limit": 200}
    if _flw_since_arg(q):
        p["since"] = _flw_since_arg(q)
    d = _flw_ds("flows/spikes", p, 0 if force else FLW_TTL)
    if d is None:
        return {"configured": False, "rows": []}
    return {"configured": True, "rows": d}


def flows_instruments_get(cfg, acc, q, force):
    d = _flw_ds("flows/instruments", {}, 300)
    if d is not None:
        return {"configured": True, "rows": d}
    rows = []
    try:
        u = globals().get("stocks_universe")
        for r in (u() if u else [])[:150]:
            rows.append({"secid": r.get("secid"), "name": r.get("shortname") or r.get("name") or r.get("secid"), "cls": "share",
                         "isin": r.get("isin") or ""})
    except Exception:  # noqa: BLE001
        rows = []
    return {"configured": False, "rows": rows}


def orderbook_get(cfg, acc, q, force):
    secid = _flw_secid(q)
    if not secid:
        raise ApiError("Не указана бумага.", 400)
    try:
        depth = max(1, min(50, int(q.get("depth") or 20)))
    except ValueError:
        depth = 20
    book = _flw_ds("md/orderbook", {"secid": secid, "depth": depth}, FLW_BOOK_TTL)
    trades, src = None, None
    if book:
        tr = _flw_ds("md/trades", {"secid": secid, "minutes": 60}, FLW_BOOK_TTL)
        trades = (tr or {}).get("trades") or []
        src = "tinvest"
    else:
        try:
            own = _flw_own(cfg, secid, depth)
        except ApiError as e:
            return {"ok": False, "error": str(e), "secid": secid}
        if own:
            book, trades = own
            book = dict(book)
            src = "tinvest"
    if not book:
        return {"ok": False, "secid": secid, "error": "Стакан недоступен: на сервере данных нет токена T-Invest, а собственный токен не задан.",
                "source_label": ""}
    bids, asks = _flw_levels(book.get("bids")), _flw_levels(book.get("asks"))
    return {"ok": True, "secid": secid, "bids": bids, "asks": asks, "ts": book.get("ts") or time.time(), "source": src,
            "source_label": FLW_SRC["tinvest"], "metrics": flows_book_metrics(bids, asks), "trades": (trades or [])[:100],
            "tape": flows_tape_net(trades)}


API_GET["/api/flows"] = flows_get
API_GET["/api/flows_instruments"] = flows_instruments_get
API_GET["/api/large_trades"] = large_trades_get
API_GET["/api/spikes"] = spikes_get
API_GET["/api/orderbook"] = orderbook_get


# ───────────────────────── тревоги по списку наблюдения ─────────────────────────
_TG_KIND.update({"flow_large": "💰", "flow_spike": "📊"})      # значки для Telegram (_TG_KIND задан в 13j_watch)
FLW_ALERT_HOURS, FLW_ALERT_MAX = 6, 10


def _flw_hhmm(ts):
    return datetime.fromtimestamp(ts, timezone(timedelta(hours=3))).strftime("%H:%M")


def flows_alerts_from(large, spikes):
    """Крупные сделки и всплески по бумагам списка -> тревоги в формате мониторинга (id служит ключом дедупликации)."""
    out = []
    for r in large or []:
        side = "покупка" if r.get("side") == "buy" else "продажа"
        out.append({"id": "flow_large|%s|%d|%s|%s" % (r.get("secid"), int(r.get("ts") or 0), r.get("side"), int(r.get("value") or 0)),
                    "kind": "flow_large", "severity": "medium", "isin": r.get("isin"), "name": r.get("name") or r.get("secid"),
                    "message": "крупная %s %s ₽ по %s (%s МСК)" % (side, _disc_ru(r.get("value") or 0), r.get("price"), _flw_hhmm(r.get("ts") or 0))})
    for r in spikes or []:
        out.append({"id": "flow_spike|%s|%d" % (r.get("secid"), int(r.get("ts") or 0)), "kind": "flow_spike", "severity": "medium",
                    "isin": r.get("isin"), "name": r.get("name") or r.get("secid"),
                    "message": "всплеск объёма ×%.1f: %s ₽ за 10 минут (%s МСК)" % (r.get("ratio") or 0, _disc_ru(r.get("value") or 0), _flw_hhmm(r.get("ts") or 0))})
    return out[:FLW_ALERT_MAX * 3]


def flows_watch_alerts(cfg):
    """Тревоги «крупная покупка/продажа» и «всплеск объёма» по бумагам из списка наблюдения за последние часы."""
    isins = [i for i in watch_isins() if _isin_ok(i)][:50]
    if not isins:
        return []
    p = {"isins": ",".join(isins), "since": str(int(time.time() - FLW_ALERT_HOURS * 3600)), "limit": 100}
    large, spikes = _flw_ds("flows/large", p, 0), _flw_ds("flows/spikes", p, 0)
    return flows_alerts_from(large, spikes)
