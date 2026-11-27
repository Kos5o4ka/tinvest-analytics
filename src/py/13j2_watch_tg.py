# ═══════════════════════════ Telegram ═══════════════════════════

def _tg_cleanup():
    """Одноразово стирает значения прежнего личного бота (токен, chat id) из файла настроек."""
    try:
        cfg = load_config()
        if any(k in cfg for k in TG_LEGACY_KEYS):
            for k in TG_LEGACY_KEYS:
                cfg.pop(k, None)
            save_config(cfg)
    except Exception:  # noqa: BLE001
        pass


def tg_post_notify(srv, key, text, timeout=15):
    """POST {srv}/v1/notify -> (код, dict). Бросает исключение при сетевой ошибке."""
    req = urllib.request.Request(srv.rstrip("/") + "/v1/notify", data=json.dumps({"text": text}).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Client-Key": key,
                                          "User-Agent": EXT_UA["User-Agent"], **hwid_headers()}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    try:
        j = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        j = None
    return code, (j if isinstance(j, dict) else {})


def _tg_esc(s):
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


TG_DISCLAIMER = "\n\n<i>Не является индивидуальной инвестиционной рекомендацией.</i>"
TG_LIMIT = 3500                  # предел текста одного сообщения вместе с припиской
_TG_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")


def _tg_num(x, dec=0):
    """1234567.8 -> «1 234 568» (пробел — разделитель тысяч), с dec знаками — запятая-разделитель."""
    return ("{:,.%df}" % dec).format(x).replace(",", " ").replace(".", ",")


def _tg_rub(x):
    return _tg_num(x, 0 if abs(x) >= 100 or x == int(x) else 2) + " ₽"


def _tg_pct(x, dec=2):
    return _tg_num(x, dec) + "%"


def _tg_date(iso):
    """«2026-11-20» -> «20 ноября» (год — только если он не текущий)."""
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()
    except ValueError:
        return _tg_esc(iso)
    return "%d %s%s" % (d.day, _TG_MONTHS[d.month - 1], "" if d.year == date.today().year else " %d" % d.year)


def _tg_link(url, text):
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return ""
    return '<a href="%s">%s</a>' % (u.replace("&", "&amp;").replace('"', "%22").replace("<", "%3C").replace(">", "%3E"), _tg_esc(text))


def _tg_moex(isin):
    return _tg_link("https://www.moex.com/ru/issue.aspx?code=%s" % urllib.parse.quote(str(isin or "")), "на Мосбирже") if isin else ""


def _tg_head(icon, title, sub=""):
    return "%s<b>%s</b>%s" % ((icon + " ") if icon else "", _tg_esc(title), (" · " + _tg_esc(sub)) if sub else "")


def _tg_cap(lines, shown, more=""):
    """Первые shown строк + «…и ещё N» (more — пояснение после числа)."""
    out = list(lines[:shown])
    if len(lines) > shown:
        out.append("…и ещё %d%s" % (len(lines) - shown, more))
    return "\n".join(out)


def _tg_fit(text, limit):
    """Обрезка по границе строки с закрытием незакрытых тегов (иначе Telegram не разберёт разметку)."""
    if len(text) <= limit:
        return text
    cut = text[:max(limit - 40, 1)]
    cut = cut.rsplit("\n", 1)[0] if "\n" in cut else cut
    cut = re.sub(r"<[^>]*$", "", cut)             # оборванный тег
    cut = re.sub(r"&[a-z#0-9]*$", "", cut)        # оборванная сущность
    stack = []
    for m in re.finditer(r"<(/?)(b|i|a|code)\b[^>]*>", cut):
        if m.group(1):
            if m.group(2) in stack:
                stack = stack[:len(stack) - stack[::-1].index(m.group(2)) - 1]
        else:
            stack.append(m.group(2))
    return cut.rstrip() + "\n…" + "".join("</%s>" % t for t in reversed(stack))


def tg_send(cfg, text):
    """Ставит сообщение в очередь бота через сервер данных. Ошибки — ApiError с понятным текстом."""
    srv, key = ds_conf()
    if not srv:
        raise ApiError("Уведомления работают через сервер данных, а он выключен («off»). Включите сервер данных в настройках.", 400)
    if not key:
        raise ApiError("Войдите по ключу из бота.", 400)
    text = _tg_fit(text, TG_LIMIT - len(TG_DISCLAIMER))
    try:
        code, j = tg_post_notify(srv, key, text + TG_DISCLAIMER)
    except Exception:  # noqa: BLE001
        raise ApiError("Сервер недоступен.", 502)
    if code == 200 and j.get("ok"):
        return j.get("queued")
    err = str(j.get("error") or "")
    if code == 409 or err == "notify_off":
        raise ApiError("Уведомления выключены в боте: отправьте ему /notify_on.", 409)
    if code == 402 or err == "pro_required":
        raise ApiError("Уведомления в Telegram доступны в тарифе Pro. Подробнее: команда /pro в боте.", 402)
    if code == 429:
        raise ApiError("Слишком много сообщений, попробуйте позже.", 429)
    if code == 401:
        raise ApiError("Войдите по ключу из бота.", 400)
    if code == 403:
        raise ApiError("Уведомления доступны только по ключу из бота. Войдите по ключу.", 400)
    raise ApiError("Сервер недоступен." if code >= 500 or code == 404 else "Не удалось отправить уведомление (код %s)." % code, 502)


def tg_public(cfg):
    return {k: cfg.get(k, d) for k, d in TG_DEFAULTS.items()}


def tg_save(cfg, body):
    cfg = load_config()
    was = bool(cfg.get("tg_server") and cfg.get("tg_enabled"))
    for k in ("tg_enabled", "tg_on_mon", "tg_on_watch", "tg_digest", "tg_weekly_digest", "tg_server"):
        if k in body:
            cfg[k] = bool(body[k])
    if "tg_pay_days" in body:
        d = _num(body["tg_pay_days"])
        cfg["tg_pay_days"] = max(0, min(60, int(d))) if d is not None else 0
    if "tg_digest_time" in body:
        t = str(body["tg_digest_time"]).strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
            raise ApiError("Время сводки — в формате ЧЧ:ММ, например 10:00.", 400)
        cfg["tg_digest_time"] = t
    for k in TG_LEGACY_KEYS:
        cfg.pop(k, None)
    save_config(cfg)
    res = {"ok": True, "settings": tg_public(cfg)}
    now_on = bool(cfg.get("tg_server") and cfg.get("tg_enabled"))
    if was and not now_on and _tg_srv_state():
        try:                     # режим выключен: данные с сервера удаляем сразу
            with _tg_lock:
                tg_srv_delete()
        except ApiError as e:
            res["warning"] = str(e)
    elif now_on and was:
        tg_srv_kick()            # разделы или число дней изменились — обновить подписку (первое включение синхронизирует UI явно)
    return res


def tg_info(cfg, acc, q, force):
    """Для карточки настроек: имя общего бота, включён ли сервер данных, выполнен ли вход по ключу."""
    srv, key = ds_conf()
    st = auth_status() if srv else {"state": "off", "bot": _auth["bot"]}
    return {"bot": st.get("bot") or DS_BOT_DEFAULT, "server": bool(srv), "state": st.get("state"), "key_set": bool(key)}


def tg_test(cfg, body):
    tg_send(load_config(), "%s\n\nTAnalytic подключён к Telegram. Сюда будут приходить тревоги, выплаты и ежедневная сводка — "
            "что именно, настраивается в приложении." % _tg_head("", "Тестовое сообщение"))
    return {"ok": True}


def tg_run_now(cfg, body):
    n = tg_tick(force_digest=bool(body.get("digest")), manual=True)
    return {"ok": True, "sent": n}


API_POST["/api/tg/save"] = tg_save
API_GET["/api/tg/info"] = tg_info
API_POST["/api/tg/test"] = tg_test
API_POST["/api/tg/run"] = tg_run_now


