# ═══════════════ готовый рыночный срез с сервера (/v1/market/snapshot) и локальный кэш ═══════════════
# Позволяет экранам (скринер облигаций, акции, тепловая карта) получать предсобранный срез одним запросом
# вместо десятков/тысяч фоновых запросов на клиенте. Если сервер недоступен или срез пуст -> None (фоллбэк на локальный расчёт).

MARKET_SNAP_TTL = 900
_mkt_snap_lock = threading.Lock()
_mkt_snap_mem = {}


MARKET_SNAP_STALE = 3600           # срез, собранный сервером давно, не используем: экран считает рынок сам
MARKET_SNAP_MAX_BYTES = 64 * 1024 * 1024
_mkt_snap_etag = {}                # kind -> (etag, data): ответ 304 означает «срез не менялся»


def snap_gunzip(body, limit=MARKET_SNAP_MAX_BYTES):
    """Распаковка gzip-тела ответа (с защитой от «бомбы»: больше limit байт — ошибка)."""
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(body, limit)
    if d.unconsumed_tail:
        raise ValueError("ответ слишком велик после распаковки")
    return out


def _snap_http(url, headers, timeout):
    """GET -> (код, тело, заголовки). 304 возвращается как обычный результат с пустым телом; gzip распаковывается."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with ds_urlopen(req, timeout=timeout) as r:
            code, body, hd = r.status, r.read(MARKET_SNAP_MAX_BYTES + 1), r.headers
    except urllib.error.HTTPError as e:
        if e.code != 304:
            raise
        return 304, b"", e.headers
    if len(body) > MARKET_SNAP_MAX_BYTES:
        raise ValueError("ответ слишком велик")
    enc = str(hd.get("Content-Encoding") or "").lower()
    if "gzip" in enc or body[:2] == b"\x1f\x8b":     # сервер без сжатия тоже подходит: просто пропускаем
        body = snap_gunzip(body)
    return code, body, hd


def _market_snap_fetch(kind="all", timeout=20):
    srv, key = ds_conf()
    if not srv or _ds_bypassed(urlparse(srv).netloc):
        return None
    hd = {"User-Agent": EXT_UA["User-Agent"], "Accept-Encoding": "gzip"}   # токен Т-Инвестиций сюда не попадает никогда
    if key:
        hd["X-Client-Key"] = key
        hd.update(hwid_headers())                      # хэш ПК: лимит компьютеров на аккаунт
    old = _mkt_snap_etag.get(kind)
    if old:
        hd["If-None-Match"] = old[0]
    url = "%s/v1/market/snapshot?kind=%s" % (srv.rstrip("/"), urllib.parse.quote(str(kind or "all")))
    try:
        code, body, rh = _snap_http(url, hd, timeout)
        if code == 304:
            return old[1] if old else None
        j = json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(j, dict) or not j.get("ok"):
        return None
    data = j.get("data")
    if not isinstance(data, dict) or data.get("empty"):
        _mkt_snap_etag.pop(kind, None)
        return None
    et = rh.get("ETag") if rh else None
    if et:
        _mkt_snap_etag[kind] = (et, data)
    return data


def snap_is_fresh(data, max_age=MARKET_SNAP_STALE, now=None):
    """Срез собран не раньше max_age секунд назад (по updated_at сервера). Нет отметки времени — считаем устаревшим."""
    try:
        t = float(data.get("updated_at"))
    except (AttributeError, TypeError, ValueError):
        return False
    return (time.time() if now is None else now) - t <= max_age


def market_snapshot_get(kind="all", max_age=MARKET_SNAP_TTL, force=False, timeout=20):
    """Получить срез рынка с сервера (all | bonds | stocks | heatmap | status) с кэшем в памяти и kv.
    Возвращает dict или None, если сервер не ответил / срез ещё не собран / срез старше MARKET_SNAP_STALE."""
    kind = str(kind or "all")
    now = time.time()
    if not force:
        with _mkt_snap_lock:
            hit = _mkt_snap_mem.get(kind)
            if hit and now - hit[0] < max_age:
                return hit[1] if snap_is_fresh(hit[1]) or kind == "status" else None
        try:
            kv = store().get("market_snap_" + kind)
            if isinstance(kv, dict) and now - float(kv.get("t") or 0) < max_age and isinstance(kv.get("data"), dict):
                with _mkt_snap_lock:
                    _mkt_snap_mem[kind] = (float(kv["t"]), kv["data"])
                return kv["data"] if snap_is_fresh(kv["data"]) or kind == "status" else None
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
        return data if snap_is_fresh(data) or kind == "status" else None
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
