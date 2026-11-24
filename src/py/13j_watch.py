# ═══════════════════════════════ список наблюдения, заметки, уведомления в Telegram ═══════════════════════════════
# Список наблюдения и дневник хранятся только в локальной базе. Уведомления в Telegram идут через сервер данных
# (POST /v1/notify с ключом из бота) и общий бот: наружу уходят только тексты уведомлений, токен Т-Инвестиций — никогда.
# По желанию (tg_server) на сервер уходит ещё «подписка» на тревоги по публичным данным — см. раздел «проверка на сервере» ниже.
# Прежний «личный бот» (tg_token, tg_chat) удалён; старые значения стираются из настроек при запуске.

WATCH_KEY, NOTES_KEY, TG_SENT_KEY, TG_STATE_KEY = "watch_v1", "notes_v1", "tg_sent_v1", "tg_state_v1"
TG_DEFAULTS = {"tg_enabled": False, "tg_on_mon": True, "tg_on_watch": True, "tg_pay_days": 0, "tg_digest": False, "tg_digest_time": "10:00",
               "tg_server": False}
TG_LEGACY_KEYS = ("tg_token", "tg_chat")
_watch_lock = threading.Lock()
_tg_lock = threading.Lock()


def _isin_ok(s):
    s = str(s or "").strip().upper()
    return s if re.fullmatch(r"[A-Z0-9]{6,16}", s) else ""


def _num(x):
    try:
        v = float(str(x).replace(",", ".").replace(" ", ""))
        return v if v == v and abs(v) < 1e9 else None
    except (TypeError, ValueError):
        return None


def watch_items():
    return [dict(x) for x in (store().get(WATCH_KEY) or []) if isinstance(x, dict) and x.get("isin")]


def watch_isins():
    """ISIN бумаг из списка наблюдения (для других модулей)."""
    return [x["isin"] for x in watch_items()]


def _scr_by_isin():
    out = {}
    try:
        for s in screener_rows():
            out[s.get("isin") or s["id"]] = s
    except Exception:  # noqa: BLE001
        pass
    return out


def _bond_name(isin, sec=None):
    s = (sec or {}).get(isin)
    if s and s.get("name"):
        return s["name"]
    try:
        ci = tcat_info(isin)
        if ci and ci.get("name"):
            return ci["name"]
    except Exception:  # noqa: BLE001
        pass
    return isin


def watch_post(cfg, body):
    act = str(body.get("action") or "")
    isin = _isin_ok(body.get("isin"))
    if not isin:
        raise ApiError("Укажите ISIN бумаги.", 400)
    with _watch_lock:
        items = watch_items()
        cur = next((x for x in items if x["isin"] == isin), None)
        if act == "toggle":
            act = "remove" if cur else "add"
        if act == "add":
            if not cur:
                cur = {"isin": isin, "added": date.today().isoformat()}
                items.append(cur)
        elif act == "remove":
            items = [x for x in items if x["isin"] != isin]
        elif act == "update":
            if not cur:
                raise ApiError("Бумаги нет в списке наблюдения.", 404)
        else:
            raise ApiError("Неизвестное действие.", 400)
        if act in ("add", "update") and cur is not None:
            for k in ("target_yield", "target_price"):
                if k in body:
                    v = _num(body[k]) if str(body[k]).strip() != "" else None
                    if v is not None and v <= 0:
                        v = None
                    if v is None:
                        cur.pop(k, None)
                    else:
                        cur[k] = round(v, 4)
            if "note" in body:
                n = str(body["note"] or "").strip()[:300]
                if n:
                    cur["note"] = n
                else:
                    cur.pop("note", None)
        store().put(WATCH_KEY, items)
    mem_clear_watch()
    tg_srv_kick()
    return {"ok": True, "isins": [x["isin"] for x in items], "in_watch": any(x["isin"] == isin for x in items)}


def mem_clear_watch():
    with _mem_lock:
        for k in [k for k in _mem if isinstance(k, tuple) and k and k[0] == "monitor_for"]:
            _mem.pop(k, None)


def watch_search(cfg, acc, q, force):
    s = str((q or {}).get("q") or "").strip().lower()
    if len(s) < 2:
        return {"rows": []}
    have = set(watch_isins())
    out = []
    for r in screener_rows():
        isin = r.get("isin") or r["id"]
        if s in (r.get("name") or "").lower() or s in isin.lower() or s in (r.get("full") or "").lower() or s in (r.get("id") or "").lower():
            out.append({"isin": isin, "name": r.get("name"), "yield": r.get("yield"), "mat": r.get("mat"), "in_watch": isin in have,
                        "turn": r.get("turn") or 0})
    out.sort(key=lambda x: (not x["name"].lower().startswith(s) if x["name"] else True, -x["turn"]))
    return {"rows": out[:12]}


# ── дневник ──

def notes_all():
    return [dict(x) for x in (store().get(NOTES_KEY) or []) if isinstance(x, dict) and x.get("id")]


def notes_get(cfg, acc, q, force):
    isin = _isin_ok((q or {}).get("isin"))
    sec = _scr_by_isin()
    rows = [n for n in notes_all() if not isin or n["isin"] == isin]
    for n in rows:
        n["name"] = _bond_name(n["isin"], sec)
    rows.sort(key=lambda n: (n.get("date") or "", n["id"]), reverse=True)
    return {"rows": rows}


def notes_post(cfg, body):
    act = str(body.get("action") or "")
    with _watch_lock:
        items = notes_all()
        if act == "add":
            isin = _isin_ok(body.get("isin"))
            text = str(body.get("text") or "").strip()[:2000]
            if not isin or not text:
                raise ApiError("Укажите бумагу и текст заметки.", 400)
            n = {"id": "n%d%03d" % (int(time.time() * 1000), len(items) % 1000), "isin": isin,
                 "date": date.today().isoformat(), "text": text}
            d = _num(body.get("remind_days"))
            if d is not None and 0 < d <= 3650:
                n["remind_on"] = (date.today() + timedelta(days=int(d))).isoformat()
            items.append(n)
        elif act == "delete":
            items = [x for x in items if x["id"] != body.get("id")]
        elif act == "done":
            for x in items:
                if x["id"] == body.get("id"):
                    x.pop("remind_on", None)
        else:
            raise ApiError("Неизвестное действие.", 400)
        store().put(NOTES_KEY, items)
    mem_clear_watch()
    tg_srv_kick()
    return {"ok": True}


# ── данные раздела «Наблюдение» и тревоги ──

def watch_payload(cfg, acc=None, q=None, force=False):
    items = watch_items()
    isins = [x["isin"] for x in items]
    sec = _scr_by_isin()
    mon = build_monitor_for(cfg, isins) if isins else {"alerts": [], "rows": [], "notes": []}
    mrow = {r["isin"]: r for r in mon.get("rows") or []}
    today = date.today().isoformat()
    rows, alerts = [], list(mon.get("alerts") or [])
    for it in items:
        isin = it["isin"]
        s = sec.get(isin)
        m = mrow.get(isin) or {}
        try:
            ci = tcat_info(isin) or {}
            rt = best_rating(isin, ci.get("name") or (s or {}).get("name") or "")
        except Exception:  # noqa: BLE001
            ci, rt = {}, None
        row = dict(it, name=_bond_name(isin, sec), in_market=bool(s), rating=rt["v"] if rt else None,
                   sector=ci.get("sector"), price=(s or {}).get("price"), yield_=(s or {}).get("yield"),
                   spread=(s or {}).get("spread"), dur=(s or {}).get("dur"), turn=(s or {}).get("turn"),
                   mat=(s or {}).get("mat") or ci.get("maturity"), offer=(s or {}).get("offer"), cur=(s or {}).get("cur"),
                   coupon=(s or {}).get("coupon"), chg5=m.get("chg5"), chg30=m.get("chg30"), spread_chg30=m.get("spread_chg30"),
                   spark=m.get("spark"), flags=m.get("flags") or [], rating_state=m.get("rating"))
        alerts += watch_goal_alerts(isin, row["name"], s, it.get("target_yield"), it.get("target_price"), today)
        if not s:
            row["flags"] = row["flags"] + ["нет данных Мосбиржи"]
        rows.append(row)
    for n in notes_all():
        if n.get("remind_on") and n["remind_on"] <= today:
            nm = _bond_name(n["isin"], sec)
            alerts.append({"isin": n["isin"], "isins": [n["isin"]], "name": nm, "bonds": [nm], "id": "rm|" + n["id"], "severity": "medium",
                           "kind": "reminder", "date": n["remind_on"], "note_id": n["id"], "url": "",
                           "message": "Напоминание из дневника от %s: %s" % (n["date"][8:] + "." + n["date"][5:7], n["text"][:160])})
    alerts.sort(key=lambda a: (_SEV[a["severity"]], _neg(a["date"])))
    for a in alerts:
        for r in rows:
            if r["isin"] in (a.get("isins") or []):
                r["n_" + a["severity"]] = r.get("n_" + a["severity"], 0) + 1
    return {"items": rows, "alerts": alerts, "notes": mon.get("notes") or [],
            "summary": {s_: sum(1 for a in alerts if a["severity"] == s_) for s_ in _SEV}, "updated": time.time()}


def _f2(x):
    return ("%.2f" % x).replace(".", ",")


def watch_goal_alerts(isin, name, s, ty, tp, today):
    """Цели по бумаге списка наблюдения. Чистая функция; её зеркало на сервере — alerts.goal_alerts (тест на совпадение)."""
    out = []
    if not s:
        return out
    base = {"isin": isin, "isins": [isin], "name": name, "bonds": [name]}
    if ty is not None and s.get("yield") is not None and s["yield"] >= ty:
        out.append(dict(base, id="gy|%s|%s" % (isin, ty), severity="medium", kind="goal", date=today,
                        message="Цель достигнута: доходность %s %% (цель — от %s %%)" % (_f2(s["yield"]), _f2(ty)), url=""))
    if tp is not None and s.get("price") is not None and s["price"] <= tp:
        out.append(dict(base, id="gp|%s|%s" % (isin, tp), severity="medium", kind="goal", date=today,
                        message="Цель достигнута: цена %s %% (цель — не выше %s %%)" % (_f2(s["price"]), _f2(tp)), url=""))
    return out


def watch_isins_get(cfg, acc, q, force):
    return {"isins": watch_isins()}


API_GET["/api/watch"] = watch_payload
API_GET["/api/watch/isins"] = watch_isins_get
API_GET["/api/watch/search"] = watch_search
API_GET["/api/notes"] = notes_get
API_POST["/api/watch"] = watch_post
API_POST["/api/notes"] = notes_post


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
                                          "User-Agent": EXT_UA["User-Agent"]}, method="POST")
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
    return "%s <b>%s</b>%s" % (icon, _tg_esc(title), (" · " + _tg_esc(sub)) if sub else "")


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
    for k in ("tg_enabled", "tg_on_mon", "tg_on_watch", "tg_digest", "tg_server"):
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
            "что именно, настраивается в приложении." % _tg_head("🧪", "Тестовое сообщение"))
    return {"ok": True}


def tg_run_now(cfg, body):
    n = tg_tick(force_digest=bool(body.get("digest")), manual=True)
    return {"ok": True, "sent": n}


API_POST["/api/tg/save"] = tg_save
API_GET["/api/tg/info"] = tg_info
API_POST["/api/tg/test"] = tg_test
API_POST["/api/tg/run"] = tg_run_now


_TG_KIND = {"price": "📉", "spread": "📈", "offer": "🔔", "default": "⛔", "rating": "🏷", "watch": "👁", "outlook": "👁",
            "halt": "⏸", "liquidity": "💧", "goal": "⭐", "reminder": "📝"}
_TG_COOL = {"price": 7 * DAY, "spread": 7 * DAY}      # повтор не раньше, чем через неделю; остальные тревоги — один раз


def _tg_key(a):
    k = a["id"]
    if a.get("kind") in _TG_COOL:
        k = "%s|%s|%s" % (a["kind"], a.get("isin"), "")
    return k


def _tg_alert_line(a):
    """«📉 <b>Бумага</b> — сообщение» и строка со ссылками (пресс-релиз/источник, бумага на Мосбирже)."""
    nm = a.get("name") or ""
    line = "%s <b>%s</b> — %s" % (_TG_KIND.get(a.get("kind"), "•"), _tg_esc(nm), _tg_esc(a.get("message")))
    url = str(a.get("url") or "")
    links = []
    if url and "moex.com/ru/issue" not in url:
        links.append(_tg_link(url, "Пресс-релиз" if a.get("kind") == "rating" else "Подробнее"))
    if a.get("isin"):
        links.append(_tg_moex(a["isin"]))
    links = [x for x in links if x]
    return line + ("\n" + " · ".join(links) if links else "")


def tg_dispatch_plan(title, alerts, sent, now, icon="🔔"):
    """Раскладка ещё не отправленных тревог по сообщениям: до трёх сообщений за проверку, до 10 тревог и в предел длины
    каждое; остальное уйдёт в следующий раз (в последнем сообщении об этом сказано). -> [(текст, [(ключ, тревога)])].
    Чистая функция; зеркало на сервере — alerts.dispatch_plan."""
    fresh = []
    for a in alerts:
        k = _tg_key(a)
        last = sent.get(k)
        if last is not None and now - last < _TG_COOL.get(a.get("kind"), 400 * DAY):
            continue
        fresh.append((k, a))
    if not fresh:
        return []
    head = _tg_head(icon, title)
    room = TG_LIMIT - len(TG_DISCLAIMER) - len(head) - 120
    plan, i = [], 0
    for msg_no in range(3):
        if i >= len(fresh):
            break
        chunk, lines, size = [], [], 0
        while i < len(fresh) and len(chunk) < 10:
            ln = _tg_alert_line(fresh[i][1])
            if chunk and size + len(ln) + 2 > room:
                break
            chunk.append(fresh[i])
            lines.append(ln)
            size += len(ln) + 2
            i += 1
        tail = ("\n\n…и ещё %d — придут при следующей проверке" % (len(fresh) - i)) if msg_no == 2 and i < len(fresh) else ""
        plan.append(("%s\n\n%s%s" % (head, "\n\n".join(lines), tail), chunk))
    return plan


def _tg_dispatch(cfg, title, alerts, sent, now, icon="🔔"):
    """Отправляет план tg_dispatch_plan. Возвращает число отправленных тревог."""
    sent_n = 0
    for text, chunk in tg_dispatch_plan(title, alerts, sent, now, icon):
        tg_send(cfg, text)
        for k, a in chunk:
            sent[k] = now
        sent_n += len(chunk)
    return sent_n


_TG_KIND["default_ok"] = "✅"
TG_DFL_DAYS = 30


def defaults_alerts(cfg, sent=None, rows=None, isins=None):
    """Тревоги о техдефолте/дефолте по бумагам портфеля и списка наблюдения (лента defaults_feed) и «исполнено» после него.
    Неисполненное -> kind default, severity high, id dfl|isin|дата|обязательство (один раз). Исполненное -> kind default_ok,
    id dflx|... — только если о дефолте по этой записи мы уже сообщали (ключ dfl|... есть в sent). Бумаги вне портфеля/наблюдения
    не трогаем. rows/isins передаются в тестах, иначе берутся из defaults_feed и _disc_own_isins."""
    sent = sent or {}
    own = list(isins) if isins is not None else _disc_own_isins(cfg, "all")
    if not own:
        return []
    if rows is None:
        rows = defaults_feed((date.today() - timedelta(days=TG_DFL_DAYS)).isoformat(), own)
    mine = set(own)
    out = []
    for r in rows:
        isin = r.get("isin")
        if isin not in mine:
            continue
        tail = "%s|%s" % (r.get("date") or r.get("basis") or "", r.get("obligation") or r.get("status"))
        base = {"isin": isin, "isins": [isin], "name": r.get("issuer") or isin, "bonds": [r.get("issuer") or isin],
                "date": r.get("date") or date.today().isoformat(), "url": r.get("url") or ""}
        what = "дефолт" if r.get("status") == "default" else "технический дефолт"
        ob = (r.get("obligation") or "обязательство").lower()
        amt = (", %s" % _tg_rub(r["amount"])) if r.get("amount") else ""
        due = (", срок %s" % _tg_date(r["due_date"])) if r.get("due_date") else ""
        kd, kx = "dfl|%s|%s" % (isin, tail), "dflx|%s|%s" % (isin, tail)
        if r.get("executed"):
            if kd in sent:
                out.append(dict(base, id=kx, kind="default_ok", severity="medium",
                                message="%s по бумаге исполнен(о): %s%s, раскрытие о выплате от %s" % (what, ob, amt, _tg_date(r["executed"]))))
        else:
            out.append(dict(base, id=kd, kind="default", severity="high",
                            message="%s по бумаге: %s%s%s (%s)" % (what, ob, amt, due, r.get("basis") or "")))
    return out


TG_OFR_CALL_DAYS, TG_OFR_CLOSE_DAYS, TG_OFR_PUT_HORIZON = 14, 2, 120


def _tg_dmy(d):
    return "%s.%s.%s" % (d[8:10], d[5:7], d[:4])


def tg_offer_due(items, today):
    """Напоминания по офертам портфеля -> [(ключ_дедупликации, текст)]. Чистая функция (today передаётся).
    items: [{isin, name, kind, date, period_start, period_end, coupon_status, new_rate}].
    Ключ 'ofr|isin|дата_оферты|тип', тип: coupon (новый купон после пут-оферты объявлен), open (приём заявок открыт),
    close (осталось <= 2 дней до конца приёма), call (до колла <= 14 дней). Каждый ключ уходит один раз (хранилище TG_SENT_KEY)."""
    out = []
    for it in items:
        isin, kind, od = it.get("isin"), it.get("kind"), it.get("date")
        if not isin or not od or od <= today:
            continue
        nm = _tg_esc(it.get("name") or isin)
        lk = "\n" + _tg_moex(isin)
        ps, pe = it.get("period_start"), it.get("period_end")
        base = "ofr|%s|%s|" % (isin, od)
        if kind == "put":
            if it.get("coupon_status") == "announced" and it.get("new_rate") is not None and (not pe or today <= pe):
                out.append((base + "coupon", "🔔 <b>%s</b> — эмитент объявил купон после пут-оферты (%s): %s годовых. Приём заявок открывается в период предъявления.%s"
                            % (nm, _tg_date(od), _tg_pct(it["new_rate"]), lk)))
            if ps and pe and ps <= today <= pe:
                out.append((base + "open", "🔔 <b>%s</b> — открыт приём заявок по пут-оферте: с %s по %s (выкуп %s). Заявку подаёт брокер.%s"
                            % (nm, _tg_date(ps), _tg_date(pe), _tg_date(od), lk)))
            if pe:
                left = _of_days(today, pe)
                if 0 <= left <= TG_OFR_CLOSE_DAYS and (not ps or ps <= today):
                    t = ("осталось %d дня подать заявку" % left if left >= 2 else "остался 1 день, чтобы подать заявку" if left == 1
                         else "сегодня последний день подачи заявки")
                    out.append((base + "close", "⏰ <b>%s</b> — %s на пут-оферту (последний день %s, выкуп %s).%s" % (nm, t, _tg_date(pe), _tg_date(od), lk)))
        elif kind == "call":
            left = _of_days(today, od)
            if 0 < left <= TG_OFR_CALL_DAYS:
                out.append((base + "call", "🔔 <b>%s</b> — возможное досрочное погашение (колл) %s, через %d дн. Решает эмитент, заявку подавать не нужно.%s"
                            % (nm, _tg_date(od), left, lk)))
    return out


def _tg_offer_items(cfg, today):
    """Оферты облигаций портфеля для напоминаний: ближайшие put (до TG_OFR_PUT_HORIZON дней) и call (до TG_OFR_CALL_DAYS)."""
    rows = [r for r in build_bonds(cfg, "all")["rows"] if r.get("isin") and r.get("qty")]
    lim = _day_add(today, TG_OFR_PUT_HORIZON)

    def one(r):
        try:
            bz = moex_bondization(r["isin"])
            res = []
            for o in offer_kinds(bz or {}, moex_bond_options(r["isin"]), r.get("call"), today):
                if o["status"] == "cancelled" or o["kind"] == "unknown" or o["date"] > lim:
                    continue
                nc = of_new_coupon((bz or {}).get("coupons") or [], o["date"], r.get("nominal") or 1000.0, bool(r.get("floating")))
                res.append({"isin": r["isin"], "name": r.get("name"), "kind": o["kind"], "date": o["date"], "period_start": o.get("period_start"),
                            "period_end": o.get("period_end"), "coupon_status": nc["status"], "new_rate": nc["rate"]})
            return res
        except Exception:  # noqa: BLE001
            return []
    return [x for lst in pool_map(one, rows, workers=8) for x in lst]


def _tg_payments(cfg, days):
    b = build_bonds(cfg, "all")
    end = (date.today() + timedelta(days=days)).isoformat()
    today = date.today().isoformat()
    ev = [(p["date"], p.get("kind"), p.get("name"), p.get("amount")) for p in (b.get("payments") or []) if today <= p["date"] <= end]
    ev += [(r["call"], "offer", r.get("name"), None) for r in (b.get("rows") or []) if r.get("call") and today <= r["call"] <= end]
    return sorted(ev, key=lambda x: (x[0], str(x[2])))


_TG_EV = {"coupon": "купон", "dividend": "дивиденд", "amortization": "амортизация", "redemption": "погашение",
          "maturity": "погашение", "offer": "оферта", "call": "оферта CALL", "put": "оферта PUT", "buyback": "выкуп"}


def _tg_ev_line(e):
    """«20 ноября · <b>Выпуск</b> — купон, 5 000 ₽»."""
    amt = ", %s" % _tg_rub(e[3]) if e[3] else ""
    return "%s · <b>%s</b> — %s%s" % (_tg_date(e[0]), _tg_esc(e[2]), _TG_EV.get(e[1], "выплата"), amt)


def tg_pay_fresh(ev, sent):
    """Ещё не отправленные выплаты -> [(ключ «pay|дата|вид|название», событие)]. Зеркало на сервере — alerts.pay_fresh."""
    out = []
    for e in ev:
        k = "pay|%s|%s|%s" % (e[0], e[1], e[2])
        if k not in sent:
            out.append((k, e))
    return out


def tg_pay_text(days, fresh):
    return "%s\n\n%s" % (_tg_head("💰", "Ближайшие выплаты", "%d дн." % days), _tg_cap([_tg_ev_line(e) for k, e in fresh], 15))


def tg_digest_text(cfg):
    parts = [_tg_head("📈", "Сводка TAnalytic", _tg_date(date.today().isoformat()))]
    if cfg.get("token"):
        try:
            s = build_summary(cfg, "all", "all")
            p = s.get("portfolio") or {}
            if p.get("total") is not None:
                d = p.get("daily")
                parts.append("💼 <b>Портфель</b> — %s%s" % (_tg_rub(p["total"]),
                             (" (за день %s%s)" % ("+" if d >= 0 else "−", _tg_rub(abs(d)))) if d is not None else ""))
        except Exception:  # noqa: BLE001
            pass
        try:
            ev = _tg_payments(cfg, 7)
            if ev:
                parts.append("💰 <b>Ближайшие 7 дней</b>\n" + _tg_cap([_tg_ev_line(e) for e in ev], 8))
            else:
                parts.append("💰 <b>Ближайшие 7 дней</b> — выплат нет")
        except Exception:  # noqa: BLE001
            pass
        try:
            m = build_monitor(cfg, "all")
            parts.append("🔔 <b>Мониторинг</b> — высоких тревог: %d, средних: %d" % (m["summary"]["high"], m["summary"]["medium"]))
        except Exception:  # noqa: BLE001
            pass
    try:
        w = watch_payload(cfg)
        if w["items"]:
            ln = ["<b>%s</b> — %s" % (_tg_esc(r["name"]), ("доходность %s" % _tg_pct(r["yield_"])) if r.get("yield_") is not None else "нет данных")
                  for r in w["items"]]
            parts.append("👁 <b>Наблюдение</b> (бумаг: %d, тревог: %d)\n%s" % (len(w["items"]), len(w["alerts"]), _tg_cap(ln, 8)))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)


def tg_tick(force_digest=False, manual=False):
    """Одна проверка: новые тревоги, выплаты, ежедневная сводка. Возвращает число отправленных пунктов."""
    if not _tg_lock.acquire(False):
        return 0
    try:
        cfg = load_config()
        if not manual and not force_digest and not cfg.get("tg_enabled"):
            return 0
        if not all(ds_conf()):                  # нужен сервер данных и вход по ключу из бота
            return 0
        st = store()
        now = time.time()
        sent = {k: v for k, v in (st.get(TG_SENT_KEY) or {}).items() if now - v < 400 * DAY}
        n = 0
        srv = False
        try:        # серверная проверка: обновить подписку и не дублировать то, что отправит сервер
            if cfg.get("tg_server") and cfg.get("tg_enabled"):
                _tg_srv_sync(cfg, sent, force=not _tg_srv_boot[0])
                _tg_srv_boot[0] = True
            srv = tg_srv_active(cfg)
        except Exception:  # noqa: BLE001
            srv = tg_srv_active(cfg)
        try:
            if cfg.get("tg_on_mon", True) and cfg.get("token"):
                al = [a for a in build_monitor(cfg, "all")["alerts"] if a["severity"] == "high"]
                n += _tg_dispatch(cfg, "Тревоги по портфелю", al, sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:
            if cfg.get("tg_on_mon", True) and cfg.get("token") and not srv:
                today_ = date.today().isoformat()
                due = [(k, t) for k, t in tg_offer_due(_tg_offer_items(cfg, today_), today_) if k not in sent][:10]
                if due:
                    tg_send(cfg, _tg_head("🔔", "Оферты по портфелю") + "\n\n" + "\n\n".join(t for _k, t in due))
                    for k, _t in due:
                        sent[k] = now
                    n += len(due)
        except Exception:  # noqa: BLE001
            pass
        try:
            if cfg.get("tg_on_watch", True) and (watch_isins() or notes_all()):
                al = [a for a in watch_payload(cfg)["alerts"] if a["severity"] != "info"
                      and not (srv and a.get("kind") in TG_SRV_KINDS)]
                n += _tg_dispatch(cfg, "Наблюдение и цели", al, sent, now, icon="⭐")
        except Exception:  # noqa: BLE001
            pass
        try:        # крупные сделки и всплески объёма по бумагам списка (13v_flows.py; ключ дедупликации — id тревоги)
            if cfg.get("tg_on_watch", True) and watch_isins() and "flows_watch_alerts" in globals():
                n += _tg_dispatch(cfg, "Потоки по списку наблюдения", flows_watch_alerts(cfg), sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:        # техдефолты/дефолты по бумагам портфеля и списка наблюдения + «исполнено» (13q_disclosure.py)
            if cfg.get("tg_on_mon", True) or cfg.get("tg_on_watch", True):
                n += _tg_dispatch(cfg, "Дефолты по бумагам портфеля и наблюдения", defaults_alerts(cfg, sent), sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:
            days = int(cfg.get("tg_pay_days") or 0)
            if days > 0 and cfg.get("token") and not srv:
                fresh = tg_pay_fresh(_tg_payments(cfg, days), sent)
                if fresh:
                    tg_send(cfg, tg_pay_text(days, fresh))
                    for k, e in fresh:
                        sent[k] = now
                    n += len(fresh)
        except Exception:  # noqa: BLE001
            pass
        try:
            state = st.get(TG_STATE_KEY) or {}
            hh = str(cfg.get("tg_digest_time") or "10:00")
            nowl = datetime.now()
            due = force_digest or (cfg.get("tg_digest") and state.get("digest") != date.today().isoformat()
                                   and nowl.strftime("%H:%M") >= hh)
            if due:
                tg_send(cfg, tg_digest_text(cfg))
                if not force_digest:
                    state["digest"] = date.today().isoformat()
                    st.put(TG_STATE_KEY, state)
                n += 1
        except Exception:  # noqa: BLE001
            pass
        st.put(TG_SENT_KEY, sent)
        return n
    except Exception:  # noqa: BLE001
        return 0            # сеть/Telegram недоступны — попробуем в следующий раз; детали (с токеном) не пишем
    finally:
        _tg_lock.release()


# ═══════════════ проверка на сервере, пока программа закрыта (по желанию, переключатель tg_server) ═══════════════
# Приложение отправляет на сервер данных «подписку» — только правила по публичным данным (см. tg_srv_payload и
# server/alerts.py): цели по бумагам наблюдения, даты напоминаний дневника (без текста), ближайшие оферты и выплаты
# по облигациям портфеля. Токен, номера счетов, стоимость портфеля и остатки денег не отправляются никогда.
# Пока режим включён и сервер принял подписку, эти виды (TG_SRV_KINDS, оферты, выплаты) шлёт только сервер — без дублей:
# ключи уже отправленного передаются в обе стороны (поле sent).

TG_SRV_KEY = "tg_srv_v1"
TG_SRV_KINDS = ("goal", "reminder")
TG_SRV_PREFIX = ("gy|", "gp|", "rm|", "ofr|", "pay|")
TG_SRV_REFRESH = 6 * 3600         # подписку с прежним содержимым обновляем не чаще раза в 6 ч (даты выплат, статус купона после оферты)
TG_SRV_PAY_EXTRA = 8              # выплаты — с запасом на срок жизни подписки (ключ из бота действует 7 дней)
_tg_srv_boot = [False]            # первая проверка после запуска синхронизирует подписку принудительно
_tg_srv_kick_on = [False]


def tg_srv_payload(cfg, sent):
    """Подписка для сервера. Только ISIN, названия бумаг, пороги, даты и суммы ближайших выплат; ничего о счетах."""
    today = date.today().isoformat()
    p = {"v": 1, "goals": [], "reminders": [], "offers": [], "pay_days": 0, "pays": [], "sent": []}
    if cfg.get("tg_on_watch", True):
        items = watch_items()
        notes = [n for n in notes_all() if n.get("remind_on")]
        sec = _scr_by_isin() if items or notes else {}
        for it in items:
            g = {k: it[k] for k in ("target_yield", "target_price") if it.get(k) is not None}
            if g:
                p["goals"].append(dict(g, isin=it["isin"], name=str(_bond_name(it["isin"], sec))[:120]))
        for n in notes:
            p["reminders"].append({"id": n["id"], "isin": n["isin"], "name": str(_bond_name(n["isin"], sec))[:120],
                                   "date": n["date"], "remind_on": n["remind_on"]})
    if cfg.get("tg_on_mon", True) and cfg.get("token"):
        try:
            p["offers"] = [{k: o.get(k) for k in ("isin", "name", "kind", "date", "period_start", "period_end", "coupon_status", "new_rate")}
                           for o in _tg_offer_items(cfg, today)]
        except Exception:  # noqa: BLE001
            pass
    days = int(cfg.get("tg_pay_days") or 0)
    if days > 0 and cfg.get("token"):
        try:
            p["pays"] = [{"date": e[0], "kind": e[1], "name": str(e[2] or "")[:120], "amount": round(e[3], 2) if e[3] else None}
                         for e in _tg_payments(cfg, days + TG_SRV_PAY_EXTRA)][:1000]
            p["pay_days"] = days
        except Exception:  # noqa: BLE001
            pass
    for k in ("offers", "goals", "reminders"):
        p[k] = p[k][:300]
    p["sent"] = sorted(k for k in sent if k.startswith(TG_SRV_PREFIX))[-5000:]
    return p


def tg_srv_req(path, body=None, timeout=20):
    """{сервер}/v1/alerts/<path> -> (код, dict). GET без тела, иначе POST JSON. Бросает исключение при сетевой ошибке."""
    srv, key = ds_conf()
    if not srv or not key:
        raise ApiError("Нужен сервер данных и вход по ключу из бота.", 400)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(srv.rstrip("/") + "/v1/alerts/" + path, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json", "X-Client-Key": key, "User-Agent": EXT_UA["User-Agent"]})
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


_TG_SRV_ERR = {404: "Сервер данных пока не поддерживает проверку тревог — уведомления отправляет программа, пока она запущена.",
               402: "Проверка на сервере доступна в тарифе Pro.", 401: "Войдите по ключу из бота.", 403: "Войдите по ключу из бота.",
               429: "Слишком частые обновления, повторим позже.",
               409: "Проверка на сервере остановлена в боте (/alerts). Чтобы возобновить, снова включите её здесь."}


def _tg_srv_state():
    return dict(store().get(TG_SRV_KEY) or {})


def tg_srv_active(cfg):
    """Сервер принял подписку и сам шлёт TG_SRV_KINDS, оферты и выплаты: программе их отправлять не нужно."""
    return bool(cfg.get("tg_server") and cfg.get("tg_enabled") and _tg_srv_state().get("active"))


def _tg_srv_merge(sent, keys, now):
    for k in keys or []:
        if isinstance(k, str) and k.startswith(TG_SRV_PREFIX):
            sent.setdefault(k, now)


def _tg_srv_sync(cfg, sent, force=False, resume=False):
    """Отправляет подписку, если она изменилась, устарела или force. Состояние — в TG_SRV_KEY. -> True, если подписка на сервере.
    resume=True — только по явному включению пользователем: снимает остановку, сделанную в боте (/alerts)."""
    st, now = _tg_srv_state(), time.time()
    p = tg_srv_payload(cfg, sent)
    if resume:
        p["resume"] = True
    h = hashlib.sha256(json.dumps({k: v for k, v in p.items() if k not in ("sent", "resume")}, sort_keys=True).encode("utf-8")).hexdigest()
    if not force and st.get("active") and st.get("hash") == h and now - (st.get("ok") or 0) < TG_SRV_REFRESH:
        return True
    try:
        code, j = tg_srv_req("sync", p)
    except ApiError as e:
        st.update(err=str(e), at=now)
        store().put(TG_SRV_KEY, st)
        return bool(st.get("active"))
    except Exception:  # noqa: BLE001
        st.update(err="Сервер недоступен, повторим при следующей проверке.", at=now)
        store().put(TG_SRV_KEY, st)
        return bool(st.get("active"))      # сервер недоступен: и программа отправить не сможет (уведомления идут через него)
    if code == 200 and j.get("ok"):
        _tg_srv_merge(sent, j.get("sent"), now)
        st = {"active": True, "ok": now, "hash": h, "err": "", "at": now, "counts": j.get("counts") or {}}
    else:
        st.update(err=_TG_SRV_ERR.get(code) or "Сервер не принял подписку (код %s)." % code, at=now)
        if code in (400, 401, 402, 403, 404, 409, 413):     # подписки на сервере нет или она не действует: отправляет программа
            st["active"] = False
        if code == 409:                                     # остановлено в боте: режим выключаем, пока пользователь не включит снова
            c = load_config()
            c["tg_server"] = False
            save_config(c)
    store().put(TG_SRV_KEY, st)
    return bool(st.get("active"))


def tg_srv_delete(sent=None):
    """Удаляет подписку с сервера; ключи отправленного сервером переносятся к себе, чтобы программа их не повторила."""
    try:
        code, j = tg_srv_req("delete", {})
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        raise ApiError("Сервер недоступен — данные не удалены. Они удалятся автоматически, когда истечёт ключ из бота.", 502)
    if code == 404:
        store().put(TG_SRV_KEY, {})
        return {"deleted": False}
    if code != 200 or not j.get("ok"):
        raise ApiError(_TG_SRV_ERR.get(code) or "Не удалось удалить данные с сервера (код %s)." % code, 502)
    own = sent is None
    if own:
        sent = dict(store().get(TG_SENT_KEY) or {})
    _tg_srv_merge(sent, j.get("sent"), time.time())
    if own:
        store().put(TG_SENT_KEY, sent)
    store().put(TG_SRV_KEY, {})
    return {"deleted": bool(j.get("deleted"))}


def tg_srv_kick():
    """После изменения списка наблюдения, дневника или настроек — обновить подписку в фоне (через 3 с, одним потоком)."""
    try:
        cfg = load_config()
    except Exception:  # noqa: BLE001
        return
    if not (cfg.get("tg_server") and cfg.get("tg_enabled")) or _tg_srv_kick_on[0]:
        return
    _tg_srv_kick_on[0] = True

    def run():
        try:
            time.sleep(3)
            if _tg_lock.acquire(timeout=120):
                try:
                    st = store()
                    sent = dict(st.get(TG_SENT_KEY) or {})
                    _tg_srv_sync(load_config(), sent, force=True)
                    st.put(TG_SENT_KEY, sent)
                finally:
                    _tg_lock.release()
        except Exception:  # noqa: BLE001
            pass
        finally:
            _tg_srv_kick_on[0] = False
    threading.Thread(target=run, daemon=True, name="tg-srv-sync").start()


def tg_srv_get(cfg, acc, q, force):
    st = _tg_srv_state()
    return {"enabled": bool(cfg.get("tg_server")), "active": tg_srv_active(cfg), "ok": st.get("ok"), "error": st.get("err") or "",
            "counts": st.get("counts") or {}}


def tg_srv_post(cfg, body):
    """{action: sync|delete}. sync — сразу отправить подписку; delete — удалить данные с сервера и выключить режим."""
    act = str(body.get("action") or "")
    if act == "delete":
        c = load_config()
        c["tg_server"] = False          # сначала выключаем режим: даже если сервер недоступен, новых данных туда не уйдёт
        save_config(c)
        with _tg_lock:
            r = tg_srv_delete()
        return dict(r, ok=True)
    if act == "sync":
        c = load_config()
        if not (c.get("tg_server") and c.get("tg_enabled")):
            raise ApiError("Включите уведомления и проверку на сервере.", 400)
        with _tg_lock:
            st = store()
            sent = dict(st.get(TG_SENT_KEY) or {})
            ok = _tg_srv_sync(c, sent, force=True, resume=True)
            st.put(TG_SENT_KEY, sent)
        s_ = _tg_srv_state()
        if not ok:
            raise ApiError(s_.get("err") or "Сервер не принял подписку.", 502)
        return {"ok": True, "counts": s_.get("counts") or {}}
    raise ApiError("Неизвестное действие.", 400)


API_GET["/api/tg/server"] = tg_srv_get
API_POST["/api/tg/server"] = tg_srv_post


def _tg_loop():
    time.sleep(90)
    while True:
        try:
            tg_tick()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(int(os.environ.get("TINVEST_TG_PERIOD") or 720))


def tg_start():
    _tg_cleanup()
    threading.Thread(target=_tg_loop, daemon=True, name="tg-notify").start()


STARTUP_HOOKS.append(tg_start)
