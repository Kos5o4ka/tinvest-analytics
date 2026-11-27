# ═══════════════ готовый рыночный срез с сервера (/v1/market/snapshot) и локальный кэш ═══════════════
# Позволяет экранам (скринер облигаций, акции, тепловая карта) получать предсобранный срез одним запросом
# вместо десятков/тысяч фоновых запросов на клиенте. Если сервер недоступен или срез пуст -> None (фоллбэк на локальный расчёт).

MARKET_SNAP_TTL = 900
_mkt_snap_lock = threading.Lock()
_mkt_snap_mem = {}


def _market_snap_fetch(kind="all", timeout=20):
    srv, key = ds_conf()
    if not srv or _ds_bypassed(urlparse(srv).netloc):
        return None
    hd = {"User-Agent": EXT_UA["User-Agent"]}
    if key:
        hd["X-Client-Key"] = key
    url = "%s/v1/market/snapshot?kind=%s" % (srv.rstrip("/"), urllib.parse.quote(str(kind or "all")))
    try:
        req = urllib.request.Request(url, headers=hd)
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(j, dict) or not j.get("ok"):
        return None
    data = j.get("data")
    if not isinstance(data, dict) or data.get("empty"):
        return None
    return data


def market_snapshot_get(kind="all", max_age=MARKET_SNAP_TTL, force=False, timeout=20):
    """Получить срез рынка с сервера (all | bonds | stocks | heatmap | status) с кэшем в памяти и kv.
    Возвращает dict или None, если сервер не ответил / срез ещё не собран."""
    kind = str(kind or "all")
    now = time.time()
    if not force:
        with _mkt_snap_lock:
            hit = _mkt_snap_mem.get(kind)
            if hit and now - hit[0] < max_age:
                return hit[1]
        try:
            kv = store().get("market_snap_" + kind)
            if isinstance(kv, dict) and now - float(kv.get("t") or 0) < max_age and isinstance(kv.get("data"), dict):
                with _mkt_snap_lock:
                    _mkt_snap_mem[kind] = (float(kv["t"]), kv["data"])
                return kv["data"]
        except Exception:  # noqa: BLE001
            pass
    data = _market_snap_fetch(kind=kind, timeout=timeout)
    if data is not None:
        with _mkt_snap_lock:
            _mkt_snap_mem[kind] = (now, data)
        try:
            store().put("market_snap_" + kind, {"t": now, "data": data})
        except Exception:  # noqa: BLE001
            pass
        return data
    return None


def market_snapshot_bonds(max_age=MARKET_SNAP_TTL, force=False):
    d = market_snapshot_get("bonds", max_age=max_age, force=force)
    return d.get("data") if isinstance(d, dict) else None


def market_snapshot_stocks(max_age=MARKET_SNAP_TTL, force=False):
    d = market_snapshot_get("stocks", max_age=max_age, force=force)
    return d.get("data") if isinstance(d, dict) else None


def market_snapshot_heatmap(max_age=MARKET_SNAP_TTL, force=False):
    d = market_snapshot_get("heatmap", max_age=max_age, force=force)
    return d.get("data") if isinstance(d, dict) else None
