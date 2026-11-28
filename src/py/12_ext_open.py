# ═══════════════ единая точка исходящих запросов за ПУБЛИЧНЫМИ данными (Мосбиржа, ФНС, ЦБ, рейтинги, МСФО, логотипы) ═══════════════
# Публичные данные идут через сервер данных (DS_DEFAULT; для разработки и тестов — TINVEST_DATA_SERVER / TINVEST_DATA_KEY):
# GET|POST {сервер}/v1/fetch?url=... Сервер кэширует ответы и сам ходит к источникам. При любой неудаче сервера
# (нет связи, таймаут, 5xx, 401/403) запрос выполняется напрямую, а сервер на 5 минут считается недоступным.
# Сервер по умолчанию — DS_DEFAULT; он требует личный ключ из Telegram-бота (7 дней), см. «вход по ключу» ниже
# (/api/auth/*). В интерфейсе адрес не меняется; «off» в TINVEST_DATA_SERVER (разработка) отключает сервер совсем.
# API Т-Инвестиций сюда НЕ входит: он всегда идёт напрямую, токен на сервер данных не передаётся. Уведомления Telegram — отдельный вызов POST /v1/notify (13j_watch.py).

EXT_UA = {"User-Agent": "Mozilla/5.0 (compatible; tinvest-analytics)"}
_ext_ctx = []
DS_DOWN_SECS = 300
DS_DEFAULT = "https://aurora-bot.duckdns.org:8443/tinvest"
DS_BOT_DEFAULT = "tanalyticbot"
AUTH_TTL = 60
SECRET_KEYS.add("data_key")
DEFAULT_CONFIG.setdefault("data_server", "")
DEFAULT_CONFIG.setdefault("data_key", "")
_ds_state = {"down_until": 0.0, "error": "", "hit": 0, "miss": 0, "stale": 0, "direct": 0}
_ds_lock = threading.Lock()
_ds_bypass = {}                          # host -> до какого времени не ходить через сервер (источник заблокировал сервер: 429/captcha)
_direct_block = {}                       # host -> [до какого времени не ходить и напрямую, число подряд отказов]
DS_BYPASS_DEFAULT, DS_BYPASS_MIN, DS_BYPASS_MAX = 300, 30, 1800
DIRECT_BLOCK_BASE, DIRECT_BLOCK_MAX = 120, 1800
_ds_conf_cache = [0.0, ("", "")]
_auth = {"need_login": False, "at": 0.0, "res": None, "bot": DS_BOT_DEFAULT}


def ds_conf():
    """(адрес сервера без «/», ключ). Настройки приложения важнее переменных окружения. Короткий кэш: вызывается на каждый запрос."""
    now = time.time()
    if now - _ds_conf_cache[0] < 2.0:
        return _ds_conf_cache[1]
    try:
        cfg = load_config()
    except Exception:  # noqa: BLE001
        cfg = {}
    # адрес в config.json учитывается, только если это URL (ручная правка для своего сервера); старое «off» из прежних
    # версий настроек больше не отключает сервер — данные рынка всегда берутся с сервера по умолчанию
    own = str(cfg.get("data_server") or "").strip()
    url = (own if re.match(r"https?://[^/\s]+", own) else
           os.environ.get("TINVEST_DATA_SERVER") or DS_DEFAULT).strip().rstrip("/")
    key = str(cfg.get("data_key") or os.environ.get("TINVEST_DATA_KEY") or "").strip()
    if not re.match(r"https?://[^/\s]+", url):          # в т.ч. «off»: сервер отключён
        url = ""
    _ds_conf_cache[:] = [now, (url, key)]
    return url, key


# ─────────────── постоянные соединения с сервером данных (keep-alive) ───────────────
# urlopen открывает новое TCP- и TLS-соединение на каждый запрос: +0,1–0,3 с даже к ответу из кэша, а экраны делают сотни
# запросов. Здесь соединения переиспользуются: общий пул под замком (не thread-local — многие вызовы создают свой
# ThreadPoolExecutor, и соединения умерших потоков утекали бы). Контракт как у urlopen: при коде >= 400 — HTTPError с
# заголовками (get/get_all работают), тайм-ауты пробрасываются как есть. Через прокси (HTTPS_PROXY и системный) — прежний urlopen.
DS_POOL_MAX = 8
_ds_pool = {}                            # (схема, хост:порт) -> [свободные соединения]
_ds_pool_lock = threading.Lock()
_DS_RETRY_ERR = (http.client.RemoteDisconnected, http.client.BadStatusLine, http.client.CannotSendRequest,
                 http.client.ResponseNotReady, BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ssl.SSLError)


class _DsResp:
    """Ответ, прочитанный целиком (соединение сразу возвращается в пул)."""

    def __init__(self, status, headers, body):
        self.status, self.headers, self._b = status, headers, io.BytesIO(body)

    def read(self, n=-1):
        return self._b.read(n)

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def ds_pool_clear():
    with _ds_pool_lock:
        conns = [c for lst in _ds_pool.values() for c in lst]
        _ds_pool.clear()
    for c in conns:
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass


def _ds_pool_get(key, timeout):
    with _ds_pool_lock:
        lst = _ds_pool.get(key)
        c = lst.pop() if lst else None
    if c is not None:
        c.timeout = timeout
        if c.sock is not None:
            try:
                c.sock.settimeout(timeout)
            except OSError:
                c.close()
        return c, True
    scheme, netloc = key
    if scheme == "https":
        return http.client.HTTPSConnection(netloc, timeout=timeout, context=_ssl()), False
    return http.client.HTTPConnection(netloc, timeout=timeout), False


def _ds_pool_put(key, c):
    with _ds_pool_lock:
        lst = _ds_pool.setdefault(key, [])
        if len(lst) < DS_POOL_MAX:
            lst.append(c)
            return
    c.close()


def ds_urlopen(req, timeout=30):
    """Замена urllib.request.urlopen(req, timeout, context=_ssl()) для запросов к серверу данных."""
    u = urllib.parse.urlsplit(req.full_url)
    if u.scheme not in ("http", "https") or urllib.request.getproxies().get(u.scheme):
        return urllib.request.urlopen(req, timeout=timeout, context=_ssl())
    key = (u.scheme, u.netloc)
    path = (u.path or "/") + ("?" + u.query if u.query else "")
    hd = dict(req.header_items())
    hd.setdefault("Host", u.netloc)
    for attempt in (0, 1):
        c, reused = _ds_pool_get(key, timeout)
        try:
            c.request(req.get_method(), path, body=req.data, headers=hd)
            r = c.getresponse()
            body = r.read()
        except _DS_RETRY_ERR as e:
            c.close()
            if reused and attempt == 0:                # сервер закрыл простаивающее соединение — повторяем на новом
                continue
            raise urllib.error.URLError(e)
        except (socket.timeout, TimeoutError):
            c.close()
            raise
        except OSError as e:
            c.close()
            raise urllib.error.URLError(e)
        if r.will_close:
            c.close()
        else:
            _ds_pool_put(key, c)
        if r.status >= 400:
            raise urllib.error.HTTPError(req.full_url, r.status, r.reason, r.headers, io.BytesIO(body))
        return _DsResp(r.status, r.headers, body)
    raise urllib.error.URLError("нет соединения")      # недостижимо: второй проход либо вернул ответ, либо бросил


def ds_reset():
    _ds_conf_cache[0] = 0.0
    ds_pool_clear()
    with _ds_lock:
        _ds_state["down_until"] = 0.0
        _ds_state["error"] = ""
    _auth_reset()


def _auth_reset():
    with _ds_lock:
        _auth["need_login"] = False
        _auth["at"] = 0.0
        _auth["res"] = None


def _ds_is_timeout(e):
    """Тайм-аут чтения (сервер жив, но этот ответ долгий), а не отказ соединения."""
    r = getattr(e, "reason", None)
    return isinstance(e, (TimeoutError, socket.timeout)) or isinstance(r, (TimeoutError, socket.timeout)) or "timed out" in str(e)


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


def _ds_host_refused(err):
    """403 сервера «host not allowed» (сайта нет в его списке) — это не отказ в ключе: сервер для остальных запросов не отключаем.
    Иначе один такой запрос раз в минуту (например, курс BTC в бегущей строке) держал бы сервер выключенным постоянно."""
    try:
        return (json.loads(err.read().decode("utf-8", "replace")) or {}).get("error") == "host not allowed"
    except Exception:  # noqa: BLE001
        return False


def _ds_note_bypass(host, hdr):
    """Сервер сообщил, что источник его заблокировал (X-Upstream-Blocked: секунды; 0 — одиночный отказ, хост не замораживаем)."""
    try:
        secs = int(float(hdr)) if hdr is not None else DS_BYPASS_DEFAULT
    except ValueError:
        secs = DS_BYPASS_DEFAULT
    if secs <= 0 and hdr is not None:
        return
    with _ds_lock:
        _ds_bypass[host] = time.time() + min(max(secs, DS_BYPASS_MIN), DS_BYPASS_MAX)


def _ds_bypassed(host):
    with _ds_lock:
        t = _ds_bypass.get(host, 0.0)
        if t and t <= time.time():
            _ds_bypass.pop(host, None)
            return False
        return bool(t)


def _direct_wait(host):
    with _ds_lock:
        b = _direct_block.get(host)
        return max(0, int(b[0] - time.time()) + 1) if b and b[0] > time.time() else 0


def _direct_note_fail(host, err):
    """Прямой запрос отклонён: 429 всегда, 403/451 — только для хоста, который уже обходит сервер. Пауза: Retry-After или 120 с, 240 … до 1800."""
    if err.code != 429 and not (err.code in (403, 451) and _ds_bypassed(host)):
        return
    ra = _retry_after_sec(getattr(err, "headers", None))
    with _ds_lock:
        n = _direct_block.get(host, [0.0, 0])[1]
        d = min(max(ra, 30), 21600) if ra is not None else min(DIRECT_BLOCK_BASE * (2 ** n), DIRECT_BLOCK_MAX)
        _direct_block[host] = [time.time() + d, n + 1]


def _retry_after_sec(headers):
    """Retry-After в секундах: число или HTTP-дата (RFC 7231); None, если заголовка нет или он не разбирается."""
    try:
        v = (headers.get("Retry-After") or "").strip()
    except AttributeError:
        return None
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _direct_note_ok(host):
    with _ds_lock:
        _direct_block.pop(host, None)


def _ds_request(srv, key, url, data, headers, timeout):
    """Запрос через сервер данных. Возвращает (статус, тело, content-type, set-cookie[], X-Cache) либо None (нужен прямой запрос).
    Ответ источника (в т.ч. 404) приходит с заголовком X-Cache; его отсутствие значит, что ответил сам сервер (ошибка)."""
    hd = {"User-Agent": EXT_UA["User-Agent"]}
    if key:
        hd["X-Client-Key"] = key
        hd.update(hwid_headers())                      # хэш ПК: лимит компьютеров на аккаунт
    for k, v in (headers or {}).items():
        if k.lower() in ("referer", "cookie", "accept", "accept-language"):
            hd["X-Up-" + k.title()] = v
        elif k.lower() == "content-type":
            hd["Content-Type"] = v
    req = urllib.request.Request(srv + "/v1/fetch?url=" + urllib.parse.quote(url, safe=""), data=data, headers=hd,
                                 method="POST" if data is not None else "GET")
    try:
        with ds_urlopen(req, timeout=timeout + 5) as r:
            body = r.read()
            return (r.status, body, r.headers.get("Content-Type") or "", r.headers.get_all("X-Set-Cookie") or [],
                    r.headers.get("X-Cache") or "miss")
    except urllib.error.HTTPError as e:
        if e.headers.get("X-Cache"):                   # настоящий ответ источника (404 и т.п.): повторять напрямую не нужно
            return e.code, e.read(), e.headers.get("Content-Type") or "", [], e.headers.get("X-Cache")
        if e.headers.get("X-Upstream-Blocked") is not None:    # источник заблокировал сервер: этот хост пока ходим напрямую
            _ds_note_bypass((urllib.parse.urlparse(url).hostname or "").lower(), e.headers.get("X-Upstream-Blocked"))
            return None
        if e.headers.get("X-Upstream-Error"):         # сервер жив, но источник не ответил: пробуем напрямую, сервер не «роняем»
            return None
        if e.code == 403 and _ds_host_refused(e):     # сайта нет в списке сервера: этот запрос — напрямую, ключ тут ни при чём
            return None
        if e.code == 401:                              # ключ не принят: UI попросит войти; этот запрос всё же выполняем напрямую
            with _ds_lock:
                _auth["need_login"] = True
                _auth["res"] = None
        _ds_down("сервер ответил %d%s" % (e.code, " (неверный ключ)" if e.code in (401, 403) else ""))
        return None
    except Exception as e:  # noqa: BLE001
        if _ds_is_timeout(e):                          # медленный ответ одного запроса — не повод отключать сервер для всех
            return None
        _ds_down("нет связи с сервером: %s" % (getattr(e, "reason", None) or type(e).__name__))
        return None


DS_PARSED_V = 1
_ds_hist_off = [0.0]                       # старый сервер без /v1/history: не спрашиваем 10 минут


def ds_history(market, secid, frm, till=None, timeout=90):
    """Дневная история бумаги из архива сервера данных одним запросом (вместо десятков страниц ISS).
    -> {"from", "till", "cov_from", "rows": [[дата, close, value, yield], ...]} либо None (сервера нет, старый сервер, ошибка)."""
    srv, key = ds_conf()
    now = time.time()
    if not srv or now < _ds_state["down_until"] or now < _ds_hist_off[0]:
        return None
    q = {"market": market, "secid": secid, "from": frm}
    if till:
        q["till"] = till
    hd = {"User-Agent": EXT_UA["User-Agent"], "Accept-Encoding": "gzip"}
    if key:
        hd["X-Client-Key"] = key
        hd.update(hwid_headers())                      # хэш ПК: лимит компьютеров на аккаунт
    try:
        with ds_urlopen(urllib.request.Request(srv + "/v1/history?" + urllib.parse.urlencode(q), headers=hd), timeout=timeout) as r:
            raw = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.decompress(raw)
            j = json.loads(raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _ds_hist_off[0] = time.time() + 600
        elif e.code == 401:
            with _ds_lock:
                _auth["need_login"] = True
                _auth["res"] = None
        return None
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(j, dict) or j.get("ok") is not True or not isinstance(j.get("rows"), list):
        return None
    return j



def ds_parsed(name, params=None, timeout=20):
    """Готовый разбор страницы источника с сервера данных: GET {сервер}/v1/parsed/<name>?... -> data либо None.
    None: сервер выключен/недоступен, старый сервер (404), ok:false, другая версия формата. Тогда вызывающий разбирает страницу сам."""
    srv, key = ds_conf()
    if not srv or time.time() < _ds_state["down_until"]:
        return None
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    hd = {"User-Agent": EXT_UA["User-Agent"]}
    if key:
        hd["X-Client-Key"] = key
        hd.update(hwid_headers())                      # хэш ПК: лимит компьютеров на аккаунт
    try:
        req = urllib.request.Request(srv + "/v1/parsed/" + name + q, headers=hd)
        with ds_urlopen(req, timeout=timeout + 5) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            with _ds_lock:
                _auth["need_login"] = e.code == 401 or _auth["need_login"]
                _auth["res"] = None
            _ds_down("сервер ответил %d" % e.code)
        return None                                    # 404 (старый сервер), 5xx источника и т.п. — не «роняем» сервер
    except Exception as e:  # noqa: BLE001
        if _ds_is_timeout(e):                          # медленный ответ одного запроса — не повод отключать сервер для всех
            return None
        _ds_down("нет связи с сервером: %s" % (getattr(e, "reason", None) or type(e).__name__))
        return None
    if not isinstance(j, dict) or j.get("ok") is not True or j.get("v") != DS_PARSED_V:
        return None
    return j.get("data")


def ext_open(url, data=None, headers=None, timeout=25, jar=None):
    """Запрос публичных данных -> (статус, байты, content-type). При HTTP-ошибке источника бросает urllib.error.HTTPError
    (как и прежний urlopen). jar — dict с cookie сессии (обновляется из ответа), нужен, например, raexpert (CSRF)."""
    headers = dict(headers or {})
    if jar:
        headers["Cookie"] = _cookie_header(jar)
    srv, key = ds_conf()
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if srv and time.time() >= _ds_state["down_until"] and not _ds_bypassed(host):
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
    wait = _direct_wait(host)
    if wait:                                            # источник ограничил и прямые запросы: сети не касаемся
        raise urllib.error.HTTPError(url, 429, "Источник %s временно ограничил запросы, повтор через %d с" % (host, wait),
                                     {"Retry-After": str(wait)}, io.BytesIO(b""))
    with _ds_lock:
        _ds_state["direct"] += 1
    hd = dict(EXT_UA)
    hd.update(headers)
    req = urllib.request.Request(url, data=data, headers=hd)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
            body = r.read()
            if jar is not None:
                _jar_update(jar, r.headers.get_all("Set-Cookie"))
            result = r.status, body, r.headers.get("Content-Type") or ""
    except urllib.error.HTTPError as e:
        _direct_note_fail(host, e)
        raise
    _direct_note_ok(host)
    return result


def ds_status():
    srv, key = ds_conf()
    with _ds_lock:
        st = dict(_ds_state)
    down = bool(srv) and time.time() < st["down_until"]
    now = time.time()
    with _ds_lock:
        bypass = {h: int(t - now) + 1 for h, t in _ds_bypass.items() if t > now}
    return {"mode": "direct" if not srv else ("down" if down else "server"), "url": srv, "key_set": bool(key), "bypass": bypass,
            "hit": st["hit"], "miss": st["miss"], "stale": st["stale"], "direct": st["direct"],
            "error": st["error"] if down else "", "retry_in": max(0, int(st["down_until"] - time.time())) if down else 0}


def ds_get(cfg, acc, q, force):
    return ds_status()


def ds_test(cfg, body):
    """Проверка сервера: GET /v1/health. Поля url/key из формы; пустой ключ = сохранённый."""
    url = ds_conf()[0]
    key = str(body.get("key") or "").strip() or ds_conf()[1]
    if not re.match(r"https?://[^/\s]+", url):
        raise ApiError("Сервер данных отключён (TINVEST_DATA_SERVER=off).", 400)
    hd = {"User-Agent": EXT_UA["User-Agent"]}
    if key:
        hd["X-Client-Key"] = key
        hd.update(hwid_headers())                      # хэш ПК: лимит компьютеров на аккаунт
    try:
        with urllib.request.urlopen(urllib.request.Request(url + "/v1/health", headers=hd), timeout=10, context=_ssl()) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise ApiError("Сервер ответил %d%s" % (e.code, ": неверный или отсутствующий ключ" if e.code in (401, 403) else ""), 400)
    except Exception as e:  # noqa: BLE001
        raise ApiError("Не удалось подключиться: %s" % (getattr(e, "reason", None) or type(e).__name__), 400)
    if not isinstance(j, dict) or not j.get("ok"):
        raise ApiError("Это не сервер данных TAnalytic.", 400)
    return {"ok": True, "version": j.get("version", ""), "uptime": j.get("uptime", 0), "cache_items": j.get("cache_items", 0)}


# ─────────────── вход по ключу из Telegram-бота ───────────────
def _auth_http(srv, path, key):
    """GET {srv}{path} -> (код, dict). Бросает исключение при сетевой ошибке/таймауте."""
    hd = {"User-Agent": EXT_UA["User-Agent"]}
    if key:
        hd["X-Client-Key"] = key
        hd.update(hwid_headers())                      # только хэш ПК (см. 12e_hwid.py); для пробного периода
    try:
        with urllib.request.urlopen(urllib.request.Request(srv + path, headers=hd), timeout=10, context=_ssl()) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    try:
        j = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        j = None
    return code, (j if isinstance(j, dict) else {})


def _auth_eval(srv, key):
    """Состояние доступа по ответу сервера (без кэша)."""
    base = {"state": "ok", "error": "", "expires": None, "username": "", "bot": _auth["bot"], "server": srv,
            "plan": "pro", "pro_until": None, "trial": False}   # свой сервер / общий ключ / старый сервер: всё доступно
    try:
        if not key:                                    # без ключа пускаем, только если сервер открытый
            code, j = _auth_http(srv, "/v1/health", "")
            if code >= 500 or code == 0:
                return dict(base, state="offline", error="сервер ответил %d" % code)
            if j.get("bot"):
                base["bot"] = str(j["bot"])
            if j.get("auth") in ("keys", "key") or code in (401, 403):
                return dict(base, state="need_login", error="nokey")
            return base
        code, j = _auth_http(srv, "/v1/auth/check", key)
    except Exception as e:  # noqa: BLE001
        return dict(base, state="offline", error="нет связи с сервером: %s" % (getattr(e, "reason", None) or type(e).__name__))
    if j.get("bot"):
        base["bot"] = str(j["bot"])
    if code == 200 and j.get("ok", True):
        plan = str(j.get("plan") or "")
        if "pro_until" not in j:            # старый сервер отдавал заглушку plan="free" без тарифов — всё доступно
            plan = "pro"
        pu = j.get("pro_until")
        return dict(base, expires=j.get("expires"), username=str(j.get("username") or ""),
                    plan="free" if plan == "free" else "pro",
                    pro_until=pu if isinstance(pu, (int, float)) and not isinstance(pu, bool) else None,
                    trial=bool(j.get("trial")) and plan != "free",
                    trial_blocked=bool(j.get("trial_blocked")), message=str(j.get("message") or "") if j.get("trial_blocked") else "")
    if code == 401 or code == 403:
        err = str(j.get("error") or "")
        if err in ("devices", "device_blocked"):
            base["max_devices"] = j.get("max_devices") or 5
        return dict(base, state="need_login", error=err if err in ("expired", "banned", "devices", "device_blocked") else "invalid")
    if code == 404:                                    # старый сервер без /v1/auth/check: доступ не ограничен
        return base
    return dict(base, state="offline", error="сервер ответил %d" % code)


def auth_status(force=False):
    srv, key = ds_conf()
    if not srv:                                        # сервер отключён: приложение работает напрямую
        return {"state": "ok", "error": "", "expires": None, "username": "", "bot": _auth["bot"], "server": "",
                "plan": "pro", "pro_until": None, "trial": False}
    now = time.time()
    with _ds_lock:
        if not force:
            if _auth["need_login"]:
                last = _auth["res"] or {}
                err = last.get("error") if key and last.get("server") == srv else ""
                r = {"state": "need_login", "error": err or ("invalid" if key else "nokey"), "expires": None, "username": "",
                     "bot": _auth["bot"], "server": srv}
                if last.get("max_devices") and err in ("devices", "device_blocked"):
                    r["max_devices"] = last["max_devices"]
                return r
            if _auth["res"] and now - _auth["at"] < AUTH_TTL and _auth["res"].get("server") == srv:
                r = _auth["res"]
                if not (r["state"] == "ok" and r["expires"] and r["expires"] <= now):
                    return dict(r)
    res = _auth_eval(srv, key)
    with _ds_lock:
        _auth["bot"] = res["bot"]
        _auth["need_login"] = res["state"] == "need_login"
        _auth["res"] = dict(res)
        _auth["at"] = time.time()
    return res


def auth_status_get(cfg, acc, q, force):
    return auth_status(force)


def auth_login(cfg, body):
    key = "".join(str(body.get("key") or "").split()).upper()
    if not key:
        raise ApiError("Введите ключ из бота.", 400)
    srv = ds_conf()[0]
    if not srv:
        raise ApiError("Сервер данных отключён в настройках: вход не нужен.", 400)
    res = _auth_eval(srv, key)
    if res["state"] == "need_login":
        msgs = {"expired": "Ключ истёк — получите новый в боте", "banned": "Доступ ограничен",
                "devices": "Ключ уже работает на %s компьютерах. Отвяжите лишний в боте: /devices" % res.get("max_devices", 5),
                "device_blocked": "Этот компьютер отвязан от ключа в боте. Выпустите новый ключ: /key"}
        err = res["error"]
        return 401, {"error": msgs.get(err, "Неверный ключ"), "code": err, "bot": res["bot"]}
    if res["state"] == "offline":
        raise ApiError("Не удалось проверить ключ: %s." % res["error"], 502)
    c = load_config()
    c["data_key"] = key
    save_config(c)
    ds_reset()
    with _ds_lock:
        _auth["bot"] = res["bot"]
        _auth["res"] = dict(res)
        _auth["at"] = time.time()
    return res


def auth_logout(cfg, body):
    c = load_config()
    c["data_key"] = ""
    save_config(c)
    ds_reset()
    return {"state": "need_login", "error": "nokey", "expires": None, "username": "", "bot": _auth["bot"], "server": ds_conf()[0]}


API_GET["/api/auth/status"] = auth_status_get
API_POST["/api/auth/login"] = auth_login
API_POST["/api/auth/logout"] = auth_logout
API_GET["/api/dataserver"] = ds_get
API_POST["/api/dataserver/test"] = ds_test


def http_bytes(url, timeout=30):
    return ext_open(url, timeout=timeout)[1]


def http_text(url, timeout=25):
    return ext_open(url, timeout=timeout)[1].decode("utf-8", "replace")
