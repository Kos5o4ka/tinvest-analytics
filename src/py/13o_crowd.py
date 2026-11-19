# ═══════════════ помощь в сборе раскрытий эмитентов (по желанию пользователя) ═══════════════
# Сервер данных не может открыть e-disclosure.azipi.ru (сайт блокирует его адрес), а у пользователей в России страницы открываются.
# Если «Помогать собирать раскрытия» включено (по умолчанию включено, выключается в «Настройках»), то ПОКА ПРОГРАММА ЗАПУЩЕНА фоновый поток
# берёт у сервера данных задания (адреса страниц azipi), скачивает каждую страницу НАПРЯМУЮ со своего интернет-подключения
# (не через сервер данных и не через ext_open: сервер до azipi не дотянется) и отправляет серверу. Личных данных в запросах нет.
# Вежливость: не чаще одного запроса к azipi раз в CROWD_PACE секунд, после любой ошибки azipi пауза CROWD_BACKOFF, нет заданий
# или сервер недоступен — повторный опрос через несколько минут. Адрес задания проверяется здесь же (только две формы страниц azipi):
# даже скомпрометированный сервер не сможет заставить приложение ходить на другие сайты.

CROWD_PACE = 15.0
CROWD_BACKOFF = 1800.0
CROWD_IDLE = 120.0
CROWD_MAX_BODY = 2 * 1024 * 1024
CROWD_AZIPI = "https://e-disclosure.azipi.ru/"
CROWD_UA = "Mozilla/5.0 (compatible; TAnalytic-crowd/%s; +https://github.com/Kos5o4ka/tinvest-analytics)"
_CROWD_FEED = re.compile(r"^https://e-disclosure\.azipi\.ru/messages/list/day-(\d{2}\.\d{2}\.\d{4})/\?MESSAGE_BY_DAY=\1&PAGEN_2=\d{1,3}$")
_CROWD_MSG = re.compile(r"^https://e-disclosure\.azipi\.ru/messages/\d{1,10}/$")
_CROWD_BAD = ("captcha", "just a moment", "access denied", "attention required", "ddos")
DEFAULT_CONFIG.setdefault("crowd_enabled", True)     # по умолчанию помогаем; выключается в «Настройках»
DEFAULT_CONFIG.setdefault("crowd_dismissed", False)


def crowd_url_ok(url):
    return isinstance(url, str) and len(url) < 200 and bool(_CROWD_FEED.match(url) or _CROWD_MSG.match(url))


def crowd_srv_call(method, path, payload=None, timeout=25):
    """Запрос к серверу данных (только он): -> (код, dict). Исключение при сетевой ошибке. Не использует ext_open."""
    srv, key = ds_conf()
    hd = {"User-Agent": EXT_UA["User-Agent"], "X-Client-Key": key}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hd["Content-Type"] = "application/json"
    req = urllib.request.Request(srv + path, data=data, headers=hd, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
            code, raw = r.status, r.read(1 << 20)
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read(1 << 20)
    try:
        j = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        j = None
    return code, (j if isinstance(j, dict) else {})


def crowd_azipi_get(url, timeout=30):
    """Страница azipi НАПРЯМУЮ (общий SSL-контекст приложения, без сервера данных) -> (статус, байты, content-type).
    Статусы 4xx/5xx возвращаются как есть; сетевые ошибки — исключением."""
    req = urllib.request.Request(url, headers={"User-Agent": CROWD_UA % APP_VERSION, "Accept-Encoding": "identity", "Accept-Language": "ru"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
            if not r.geturl().startswith(CROWD_AZIPI):          # редирект на чужой сайт не принимаем
                return 0, b"", ""
            body = r.read(CROWD_MAX_BODY + 1)
            return r.status, body, r.headers.get("Content-Type") or ""
    except urllib.error.HTTPError as e:
        return e.code, b"", ""


class CrowdHelper:
    """Фоновый помощник. step() делает не более одного действия и возвращает, сколько секунд подождать до следующего; все внешние вещи подставляемы (тесты)."""

    def __init__(self, conf=None, srv=None, azipi=None, clock=time.time, stats=None, pace=None):
        self.conf = conf or (lambda: (bool(load_config().get("crowd_enabled")),) + tuple(ds_conf()))
        self.srv = srv or crowd_srv_call
        self.azipi = azipi or crowd_azipi_get
        self.clock = clock
        self.pace = CROWD_PACE if pace is None else pace
        self.stats = stats if stats is not None else _CrowdStats()
        self.queue, self.last_req, self.idle_until, self.backoff_until = [], 0.0, 0.0, 0.0
        self.state, self.msg, self.bad = "off", "", 0

    def _idle(self, sec, state, msg=""):
        self.idle_until = self.clock() + sec
        self.queue = []
        self.state, self.msg = state, msg
        return sec

    def _backoff(self, msg):
        self.queue = []
        self.backoff_until = self.clock() + CROWD_BACKOFF
        self.state, self.msg = "backoff", msg
        self.stats.add(errors=1)
        return CROWD_BACKOFF

    def _tasks(self):
        try:
            code, j = self.srv("GET", "/v1/crowd/task?n=2")
        except Exception as e:  # noqa: BLE001
            return self._idle(600, "no_server", "нет связи с сервером: %s" % (getattr(e, "reason", None) or type(e).__name__))
        if code in (401, 403):
            return self._idle(1800, "no_server", "сервер не принял ключ")
        if code == 404 or code == 405:
            return self._idle(3600, "no_server", "сервер не поддерживает сбор страниц")
        if code != 200 or not j.get("ok"):
            return self._idle(600, "no_server", "сервер ответил %d" % code)
        self.queue = [t for t in (j.get("tasks") or []) if isinstance(t, dict) and isinstance(t.get("id"), int) and crowd_url_ok(t.get("url"))][:5]
        self.stats.add(queue=int(j.get("queue") or 0))
        if not self.queue:
            return self._idle(CROWD_IDLE, "idle", "заданий пока нет")
        self.state, self.msg = "working", ""
        return 0.0

    def step(self):
        now = self.clock()
        enabled, srv, key = self.conf()
        if not enabled:
            self.queue, self.state, self.msg = [], "off", ""
            return 30.0
        if not srv or not key:
            self.queue, self.state, self.msg = [], "no_server", "сервер данных выключен или нужен вход по ключу"
            return CROWD_IDLE
        if now < self.backoff_until:
            self.state = "backoff"
            return min(self.backoff_until - now, 60.0)
        if not self.queue:
            if now < self.idle_until:
                return min(self.idle_until - now, 60.0)
            r = self._tasks()
            if r:
                return min(r, 60.0)
        wait = self.last_req + self.pace - now
        if wait > 0:
            return wait
        task = self.queue.pop(0)
        url = task["url"]
        self.last_req = now
        try:
            status, body, ctype = self.azipi(url)
        except Exception as e:  # noqa: BLE001
            return self._backoff("azipi не отвечает: %s" % (getattr(e, "reason", None) or type(e).__name__))
        if status in (404, 410):
            payload = {"id": task["id"], "url": url, "status": status, "body_b64": "", "ctype": ""}
        elif status == 200 and len(body) <= CROWD_MAX_BODY:
            low = body[:200000].decode("utf-8", "ignore").lower()
            if any(b in low for b in _CROWD_BAD):
                return self._backoff("azipi показал проверку (captcha)")
            self.stats.add(fetched=1)
            payload = {"id": task["id"], "url": url, "status": 200, "body_b64": base64.b64encode(gzip.compress(body, 6, mtime=0)).decode("ascii"),
                       "ctype": ctype[:100]}
        else:
            return self._backoff("azipi ответил %s" % (status or "ошибкой"))
        try:
            code, j = self.srv("POST", "/v1/crowd/submit", payload)
        except Exception as e:  # noqa: BLE001
            return self._idle(600, "no_server", "нет связи с сервером: %s" % (getattr(e, "reason", None) or type(e).__name__))
        if code == 429:
            return self._idle(max(5.0, min(float(j.get("retry_after") or 30), 3600.0)), "idle", "сервер просит подождать")
        if code == 200 and j.get("accepted"):
            self.bad = 0
            self.stats.add(accepted=1, last=now)
        elif code == 422:                                   # сервер не принял страницу (чужая/ошибочная): не долбим azipi вхолостую
            self.bad += 1
            if self.bad >= 3:
                self.bad = 0
                return self._backoff("сервер трижды не принял страницу")
        self.state = "working" if self.queue else "idle"
        return self.pace


class _CrowdStats:
    """Счётчики в базе приложения (kv 'crowd_stats'): accepted — сколько страниц принято сервером за всё время."""

    def __init__(self):
        self.lock = threading.Lock()

    def get(self):
        try:
            return dict(store().get("crowd_stats") or {})
        except Exception:  # noqa: BLE001
            return {}

    def add(self, **kw):
        with self.lock:
            s = self.get()
            for k, v in kw.items():
                s[k] = v if k in ("last", "queue") else s.get(k, 0) + v
            try:
                store().put("crowd_stats", s)
            except Exception:  # noqa: BLE001
                pass


_crowd = [None]
_crowd_wake = threading.Event()        # будит фоновый поток сразу после изменения настройки


def crowd_helper():
    if _crowd[0] is None:
        _crowd[0] = CrowdHelper()
    return _crowd[0]


def _crowd_loop():
    h = crowd_helper()
    while True:
        try:
            d = h.step()
        except Exception as e:  # noqa: BLE001
            h.state, h.msg, d = "idle", "ошибка: %s" % type(e).__name__, 120.0
        _crowd_wake.wait(max(0.5, min(d, 30.0)))
        _crowd_wake.clear()


def crowd_start():
    threading.Thread(target=_crowd_loop, daemon=True, name="crowd").start()


def api_crowd_status(cfg, acc, q, force):
    h, srv_key = crowd_helper(), ds_conf()
    st = h.stats.get()
    return {"enabled": bool(cfg.get("crowd_enabled")), "dismissed": bool(cfg.get("crowd_dismissed")), "state": h.state, "message": h.msg,
            "available": bool(srv_key[0] and srv_key[1]), "accepted": int(st.get("accepted", 0)), "fetched": int(st.get("fetched", 0)),
            "errors": int(st.get("errors", 0)), "last": st.get("last"), "queue": int(st.get("queue", 0)),
            "backoff_in": max(0, int(h.backoff_until - time.time())), "pace": h.pace}


def api_crowd_settings(cfg, body):
    if "enabled" in body:
        cfg["crowd_enabled"] = bool(body["enabled"])
        if cfg["crowd_enabled"]:
            cfg["crowd_dismissed"] = True
    if "dismissed" in body:
        cfg["crowd_dismissed"] = bool(body["dismissed"])
    save_config(cfg)
    h = crowd_helper()
    h.idle_until = 0.0
    _crowd_wake.set()                    # включили — начинаем сразу, а не через 30 с
    return {"ok": True}


API_GET["/api/crowd/status"] = api_crowd_status
API_POST["/api/crowd/settings"] = api_crowd_settings
STARTUP_HOOKS.append(crowd_start)
