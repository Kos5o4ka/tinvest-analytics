# ═══════════════ единая точка исходящих запросов за ПУБЛИЧНЫМИ данными (Мосбиржа, ФНС, ЦБ, рейтинги, МСФО, логотипы) ═══════════════
# Если задан «сервер данных» (настройки или TINVEST_DATA_SERVER / TINVEST_DATA_KEY), запрос идёт через него:
# GET|POST {сервер}/v1/fetch?url=... Сервер кэширует ответы и сам ходит к источникам. При любой неудаче сервера
# (нет связи, таймаут, 5xx, 401/403) запрос выполняется напрямую, а сервер на 5 минут считается недоступным.
# API Т-Инвестиций и Telegram сюда НЕ входят: они всегда идут напрямую, токен на сервер данных не передаётся.

EXT_UA = {"User-Agent": "Mozilla/5.0 (compatible; tinvest-analytics)"}
_ext_ctx = []
DS_DOWN_SECS = 300
SECRET_KEYS.add("data_key")
DEFAULT_CONFIG.setdefault("data_server", "")
DEFAULT_CONFIG.setdefault("data_key", "")
_ds_state = {"down_until": 0.0, "error": "", "hit": 0, "miss": 0, "stale": 0, "direct": 0}
_ds_lock = threading.Lock()
_ds_conf_cache = [0.0, ("", "")]


def ds_conf():
    """(адрес сервера без «/», ключ). Настройки приложения важнее переменных окружения. Короткий кэш: вызывается на каждый запрос."""
    now = time.time()
    if now - _ds_conf_cache[0] < 2.0:
        return _ds_conf_cache[1]
    try:
        cfg = load_config()
    except Exception:  # noqa: BLE001
        cfg = {}
    url = str(cfg.get("data_server") or os.environ.get("TINVEST_DATA_SERVER") or "").strip().rstrip("/")
    key = str(cfg.get("data_key") or os.environ.get("TINVEST_DATA_KEY") or "").strip()
    if not re.match(r"https?://[^/\s]+", url):
        url = ""
    _ds_conf_cache[:] = [now, (url, key)]
    return url, key


def ds_reset():
    _ds_conf_cache[0] = 0.0
    with _ds_lock:
        _ds_state["down_until"] = 0.0
        _ds_state["error"] = ""


def _ds_down(msg):
    with _ds_lock:
        _ds_state["down_until"] = time.time() + DS_DOWN_SECS
        _ds_state["error"] = msg


def _ssl():
    if not _ext_ctx:                     # те же настройки проверки сертификатов, что и для API Т-Инвестиций (свой CA, корпоративный прокси)
        try:
            c = load_config()
            ctx = make_ssl_context(c.get("ca_file") or "", c.get("verify_ssl", True))
        except Exception:  # noqa: BLE001
            ctx = make_ssl_context()
        _ext_ctx.append(ctx)
    return _ext_ctx[0]


def _cookie_header(jar):
    return "; ".join("%s=%s" % kv for kv in jar.items()) if jar else ""


def _jar_update(jar, set_cookies):
    for c in set_cookies or []:
        nv = c.split(";", 1)[0]
        if "=" in nv:
            k, v = nv.split("=", 1)
            jar[k.strip()] = v.strip()


def _ds_request(srv, key, url, data, headers, timeout):
    """Запрос через сервер данных. Возвращает (статус, тело, content-type, set-cookie[], X-Cache) либо None (нужен прямой запрос).
    Ответ источника (в т.ч. 404) приходит с заголовком X-Cache; его отсутствие значит, что ответил сам сервер (ошибка)."""
    hd = {"User-Agent": EXT_UA["User-Agent"]}
    if key:
        hd["X-Client-Key"] = key
    for k, v in (headers or {}).items():
        if k.lower() in ("referer", "cookie", "accept", "accept-language"):
            hd["X-Up-" + k.title()] = v
        elif k.lower() == "content-type":
            hd["Content-Type"] = v
    req = urllib.request.Request(srv + "/v1/fetch?url=" + urllib.parse.quote(url, safe=""), data=data, headers=hd,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout + 5, context=_ssl()) as r:
            body = r.read()
            return (r.status, body, r.headers.get("Content-Type") or "", r.headers.get_all("X-Set-Cookie") or [],
                    r.headers.get("X-Cache") or "miss")
    except urllib.error.HTTPError as e:
        if e.headers.get("X-Cache"):                   # настоящий ответ источника (404 и т.п.): повторять напрямую не нужно
            return e.code, e.read(), e.headers.get("Content-Type") or "", [], e.headers.get("X-Cache")
        if e.headers.get("X-Upstream-Error"):         # сервер жив, но источник не ответил: пробуем напрямую, сервер не «роняем»
            return None
        _ds_down("сервер ответил %d%s" % (e.code, " (неверный ключ)" if e.code in (401, 403) else ""))
        return None
    except Exception as e:  # noqa: BLE001
        _ds_down("нет связи с сервером: %s" % (getattr(e, "reason", None) or type(e).__name__))
        return None


def ext_open(url, data=None, headers=None, timeout=25, jar=None):
    """Запрос публичных данных -> (статус, байты, content-type). При HTTP-ошибке источника бросает urllib.error.HTTPError
    (как и прежний urlopen). jar — dict с cookie сессии (обновляется из ответа), нужен, например, raexpert (CSRF)."""
    headers = dict(headers or {})
    if jar:
        headers["Cookie"] = _cookie_header(jar)
    srv, key = ds_conf()
    if srv and time.time() >= _ds_state["down_until"]:
        res = _ds_request(srv, key, url, data, headers, timeout)
        if res is not None:
            status, body, ct, cookies, xc = res
            with _ds_lock:
                _ds_state[xc if xc in ("hit", "stale") else "miss"] += 1
            if jar is not None:
                _jar_update(jar, cookies)
            if status >= 400:
                raise urllib.error.HTTPError(url, status, "HTTP %d" % status, {"Content-Type": ct}, io.BytesIO(body))
            return status, body, ct
    with _ds_lock:
        _ds_state["direct"] += 1
    hd = dict(EXT_UA)
    hd.update(headers)
    req = urllib.request.Request(url, data=data, headers=hd)
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
        body = r.read()
        if jar is not None:
            _jar_update(jar, r.headers.get_all("Set-Cookie"))
        return r.status, body, r.headers.get("Content-Type") or ""


def ds_status():
    srv, key = ds_conf()
    with _ds_lock:
        st = dict(_ds_state)
    down = bool(srv) and time.time() < st["down_until"]
    return {"mode": "direct" if not srv else ("down" if down else "server"), "url": srv, "key_set": bool(key),
            "hit": st["hit"], "miss": st["miss"], "stale": st["stale"], "direct": st["direct"],
            "error": st["error"] if down else "", "retry_in": max(0, int(st["down_until"] - time.time())) if down else 0}


def ds_get(cfg, acc, q, force):
    return ds_status()


def ds_test(cfg, body):
    """Проверка сервера: GET /v1/health. Поля url/key из формы; пустой ключ = сохранённый."""
    url = str(body.get("url") or "").strip().rstrip("/") or ds_conf()[0]
    key = str(body.get("key") or "").strip() or ds_conf()[1]
    if not re.match(r"https?://[^/\s]+", url):
        raise ApiError("Укажите адрес сервера, например https://data.example.ru", 400)
    hd = {"User-Agent": EXT_UA["User-Agent"]}
    if key:
        hd["X-Client-Key"] = key
    try:
        with urllib.request.urlopen(urllib.request.Request(url + "/v1/health", headers=hd), timeout=10, context=_ssl()) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise ApiError("Сервер ответил %d%s" % (e.code, ": неверный или отсутствующий ключ" if e.code in (401, 403) else ""), 400)
    except Exception as e:  # noqa: BLE001
        raise ApiError("Не удалось подключиться: %s" % (getattr(e, "reason", None) or type(e).__name__), 400)
    if not isinstance(j, dict) or not j.get("ok"):
        raise ApiError("Это не сервер данных T-Invest Analytics.", 400)
    return {"ok": True, "version": j.get("version", ""), "uptime": j.get("uptime", 0), "cache_items": j.get("cache_items", 0)}


API_GET["/api/dataserver"] = ds_get
API_POST["/api/dataserver/test"] = ds_test


def http_bytes(url, timeout=30):
    return ext_open(url, timeout=timeout)[1]


def http_text(url, timeout=25):
    return ext_open(url, timeout=timeout)[1].decode("utf-8", "replace")
