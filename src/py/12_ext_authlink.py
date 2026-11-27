# ═══════════════ вход в один клик: ссылка t.me/<бот>?start=auth_<нонс> без копирования ключа ═══════════════
# Приложение создаёт на сервере ожидающую ссылку: нонс (идёт в ссылку, на сервере хранится хешем) и хеш секрета verifier
# (сам секрет остаётся в памяти программы). Пользователь подтверждает вход в боте; приложение опрашивает сервер, предъявляя
# verifier, и получает ключ один раз (pending -> approved -> consumed, 120 секунд). Токен Т-Инвестиций в этом обмене не участвует.

_auth_link = {"nonce": "", "verifier": "", "at": 0.0}
AUTH_LINK_TTL = 120


def _auth_link_post(path, body):
    srv = ds_conf()[0]
    if not srv:
        raise ApiError("Сервер данных отключён: вход не нужен.", 400)
    req = urllib.request.Request(srv + "/v1/auth/" + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": EXT_UA["User-Agent"]})
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ssl()) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    except Exception as e:  # noqa: BLE001
        raise ApiError("Нет связи с сервером: %s" % (getattr(e, "reason", None) or type(e).__name__), 502)
    try:
        j = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        j = None
    return code, (j if isinstance(j, dict) else {})


def auth_confirm_code(verifier, nonce):
    """Короткий код подтверждения (4 цифры): программа показывает его на экране, бот — в чате, и пользователь сверяет их перед
    «Подтвердить вход». Так подсунутая чужая ссылка не пройдёт: у чужой ссылки код другой. Код считается от хеша verifier
    (challenge, он и так хранится на сервере), а не от самого verifier, поэтому по коду verifier не подобрать."""
    ch = hashlib.sha256(str(verifier).encode("utf-8")).digest()
    h = hmac.new(ch, b"tinvest-auth-code|" + str(nonce).encode("utf-8"), hashlib.sha256).digest()
    return "%04d" % (int.from_bytes(h[:4], "big") % 10000)


def auth_link_start(cfg, body):
    nonce, verifier = secrets.token_urlsafe(18), secrets.token_urlsafe(32)      # 24 и 43 знака; в ссылке Telegram до 64 знаков
    code, j = _auth_link_post("start", {"nonce": nonce, "challenge": hashlib.sha256(verifier.encode("utf-8")).hexdigest()})
    if code == 404:
        raise ApiError("Этот сервер данных пока не поддерживает вход в один клик: вставьте ключ из бота.", 404)
    if code == 429:
        raise ApiError("Слишком много попыток входа, повторите позже.", 429)
    if code != 200 or not j.get("ok"):
        raise ApiError("Сервер не принял запрос входа (ответ %d)." % code, 502)
    _auth_link.update(nonce=nonce, verifier=verifier, at=time.time())
    return {"ok": True, "url": "https://t.me/%s?start=auth_%s" % (_auth["bot"].lstrip("@"), nonce), "ttl": int(j.get("ttl") or AUTH_LINK_TTL),
            "code": auth_confirm_code(verifier, nonce)}


def auth_link_poll(cfg, body):
    nonce, verifier = _auth_link["nonce"], _auth_link["verifier"]
    if not nonce or time.time() - _auth_link["at"] > AUTH_LINK_TTL + 15:
        _auth_link.update(nonce="", verifier="")
        return {"state": "expired"}
    code, j = _auth_link_post("poll", {"nonce": nonce, "verifier": verifier})
    if code != 200 or not j.get("ok"):
        _auth_link.update(nonce="", verifier="")
        return {"state": "expired"}
    st = j.get("state")
    if st == "approved" and j.get("key"):
        _auth_link.update(nonce="", verifier="")
        res = auth_login(cfg, {"key": j["key"]})
        if isinstance(res, tuple):
            return {"state": "expired"}
        return {"state": "approved", "auth": res}
    return {"state": "pending" if st == "pending" else "expired"}


API_POST["/api/auth/link/start"] = auth_link_start
API_POST["/api/auth/link/poll"] = auth_link_poll
