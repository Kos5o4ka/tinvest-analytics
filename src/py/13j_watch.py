# ═══════════════════════════════ список наблюдения, заметки, уведомления в Telegram ═══════════════════════════════
# Список наблюдения и дневник хранятся только в локальной базе. Уведомления в Telegram идут через сервер данных
# (POST /v1/notify с ключом из бота) и общий бот: наружу уходят только тексты уведомлений, токен Т-Инвестиций — никогда.
# Прежний «личный бот» (tg_token, tg_chat) удалён; старые значения стираются из настроек при запуске.

WATCH_KEY, NOTES_KEY, TG_SENT_KEY, TG_STATE_KEY = "watch_v1", "notes_v1", "tg_sent_v1", "tg_state_v1"
TG_DEFAULTS = {"tg_enabled": False, "tg_on_mon": True, "tg_on_watch": True, "tg_pay_days": 0, "tg_digest": False, "tg_digest_time": "10:00"}
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
        base = {"isin": isin, "isins": [isin], "name": row["name"], "bonds": [row["name"]]}
        ty, tp = it.get("target_yield"), it.get("target_price")
        if s and ty is not None and s.get("yield") is not None and s["yield"] >= ty:
            alerts.append(dict(base, id="gy|%s|%s" % (isin, ty), severity="medium", kind="goal", date=today,
                               message="Цель достигнута: доходность %s %% (цель — от %s %%)" % (_f2(s["yield"]), _f2(ty)), url=""))
        if s and tp is not None and s.get("price") is not None and s["price"] <= tp:
            alerts.append(dict(base, id="gp|%s|%s" % (isin, tp), severity="medium", kind="goal", date=today,
                               message="Цель достигнута: цена %s %% (цель — не выше %s %%)" % (_f2(s["price"]), _f2(tp)), url=""))
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


TG_DISCLAIMER = "\n\n<i>Не является ИИР.</i>"


def tg_send(cfg, text):
    """Ставит сообщение в очередь бота через сервер данных. Ошибки — ApiError с понятным текстом."""
    srv, key = ds_conf()
    if not srv:
        raise ApiError("Уведомления работают через сервер данных, а он выключен («off»). Включите сервер данных в настройках.", 400)
    if not key:
        raise ApiError("Войдите по ключу из бота.", 400)
    if len(text) > 3400:
        text = text[:3400].rsplit("\n", 1)[0] if "\n" in text[:3400] else text[:3400]
    try:
        code, j = tg_post_notify(srv, key, text + TG_DISCLAIMER)
    except Exception:  # noqa: BLE001
        raise ApiError("Сервер недоступен.", 502)
    if code == 200 and j.get("ok"):
        return j.get("queued")
    err = str(j.get("error") or "")
    if code == 409 or err == "notify_off":
        raise ApiError("Уведомления выключены в боте: отправьте ему /notify_on.", 409)
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
    for k in ("tg_enabled", "tg_on_mon", "tg_on_watch", "tg_digest"):
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
    return {"ok": True, "settings": tg_public(cfg)}


def tg_info(cfg, acc, q, force):
    """Для карточки настроек: имя общего бота, включён ли сервер данных, выполнен ли вход по ключу."""
    srv, key = ds_conf()
    st = auth_status() if srv else {"state": "off", "bot": _auth["bot"]}
    return {"bot": st.get("bot") or DS_BOT_DEFAULT, "server": bool(srv), "state": st.get("state"), "key_set": bool(key)}


def tg_test(cfg, body):
    tg_send(load_config(), "✅ <b>T-Invest Analytics</b>: тестовое сообщение. Уведомления подключены.")
    return {"ok": True}


def tg_run_now(cfg, body):
    n = tg_tick(force_digest=bool(body.get("digest")), manual=True)
    return {"ok": True, "sent": n}


API_POST["/api/tg/save"] = tg_save
API_GET["/api/tg/info"] = tg_info
API_POST["/api/tg/test"] = tg_test
API_POST["/api/tg/run"] = tg_run_now


_TG_KIND = {"price": "📉", "spread": "📈", "offer": "🔔", "default": "⛔", "rating": "🏷", "watch": "👁", "outlook": "👁",
            "halt": "⏸", "liquidity": "💧", "goal": "🎯", "reminder": "📝"}
_TG_COOL = {"price": 7 * DAY, "spread": 7 * DAY}      # повтор не раньше, чем через неделю; остальные тревоги — один раз


def _tg_key(a):
    k = a["id"]
    if a.get("kind") in _TG_COOL:
        k = "%s|%s|%s" % (a["kind"], a.get("isin"), "")
    return k


def _tg_alert_line(a):
    nm = a.get("name") or ""
    return "%s <b>%s</b>: %s" % (_TG_KIND.get(a.get("kind"), "•"), _tg_esc(nm), _tg_esc(a.get("message")))


def _tg_dispatch(cfg, title, alerts, sent, now):
    """Отправляет ещё не отправленные тревоги одним сообщением (до 10 штук). Возвращает число тревог."""
    fresh = []
    for a in alerts:
        k = _tg_key(a)
        last = sent.get(k)
        if last is not None and now - last < _TG_COOL.get(a.get("kind"), 400 * DAY):
            continue
        fresh.append((k, a))
    if not fresh:
        return 0
    sent_n = 0
    for i in range(0, min(len(fresh), 30), 10):          # до трёх сообщений за проверку; остальное уйдёт в следующий раз
        chunk = fresh[i:i + 10]
        tg_send(cfg, "<b>%s</b>\n\n%s" % (_tg_esc(title), "\n\n".join(_tg_alert_line(a) for k, a in chunk)))
        for k, a in chunk:
            sent[k] = now
        sent_n += len(chunk)
    return sent_n


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
        ps, pe = it.get("period_start"), it.get("period_end")
        base = "ofr|%s|%s|" % (isin, od)
        if kind == "put":
            if it.get("coupon_status") == "announced" and it.get("new_rate") is not None and (not pe or today <= pe):
                out.append((base + "coupon", "🔔 <b>%s</b>: эмитент объявил купон после пут-оферты (%s): %s %% годовых. Можно решать, предъявлять ли бумагу."
                            % (nm, _tg_dmy(od), _f2(it["new_rate"]))))
            if ps and pe and ps <= today <= pe:
                out.append((base + "open", "🔔 <b>%s</b>: открыт приём заявок по пут-оферте, с %s по %s (выкуп %s). Заявку подаёт брокер."
                            % (nm, _tg_dmy(ps), _tg_dmy(pe), _tg_dmy(od))))
            if pe:
                left = _of_days(today, pe)
                if 0 <= left <= TG_OFR_CLOSE_DAYS and (not ps or ps <= today):
                    t = ("осталось %d дня подать заявку" % left if left >= 2 else "остался 1 день, чтобы подать заявку" if left == 1
                         else "сегодня последний день подачи заявки")
                    out.append((base + "close", "⏰ <b>%s</b>: %s на пут-оферту (последний день %s, выкуп %s)." % (nm, t, _tg_dmy(pe), _tg_dmy(od))))
        elif kind == "call":
            left = _of_days(today, od)
            if 0 < left <= TG_OFR_CALL_DAYS:
                out.append((base + "call", "🔔 <b>%s</b>: возможное досрочное погашение (колл) %s, через %d дн. Решает эмитент, заявку подавать не нужно."
                            % (nm, _tg_dmy(od), left)))
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


_TG_EV = {"coupon": "купон", "dividend": "дивиденд", "redemption": "погашение", "offer": "оферта"}


def _tg_ev_line(e):
    amt = " · %s ₽" % ("{:,.0f}".format(e[3]).replace(",", " ")) if e[3] else ""
    return "%s · %s · %s%s" % (e[0][8:] + "." + e[0][5:7], _TG_EV.get(e[1], e[1] or ""), _tg_esc(e[2]), amt)


def tg_digest_text(cfg):
    parts = ["<b>Сводка T-Invest Analytics · %s</b>" % date.today().strftime("%d.%m.%Y")]
    if cfg.get("token"):
        try:
            s = build_summary(cfg, "all", "all")
            p = s.get("portfolio") or {}
            if p.get("total") is not None:
                d = p.get("daily")
                parts.append("Портфель: %s ₽%s" % ("{:,.0f}".format(p["total"]).replace(",", " "),
                             (" (за день %s%s ₽)" % ("+" if d >= 0 else "−", "{:,.0f}".format(abs(d)).replace(",", " "))) if d is not None else ""))
        except Exception:  # noqa: BLE001
            pass
        try:
            ev = _tg_payments(cfg, 7)
            if ev:
                parts.append("Ближайшие 7 дней:\n" + "\n".join(_tg_ev_line(e) for e in ev[:8]) + ("\n…и ещё %d" % (len(ev) - 8) if len(ev) > 8 else ""))
            else:
                parts.append("Ближайшие 7 дней: выплат нет.")
        except Exception:  # noqa: BLE001
            pass
        try:
            m = build_monitor(cfg, "all")
            parts.append("Мониторинг портфеля: высоких тревог — %d, средних — %d." % (m["summary"]["high"], m["summary"]["medium"]))
        except Exception:  # noqa: BLE001
            pass
    try:
        w = watch_payload(cfg)
        if w["items"]:
            ln = []
            for r in w["items"][:8]:
                ln.append("%s: %s" % (_tg_esc(r["name"]), ("доходность %s %%" % _f2(r["yield_"])) if r.get("yield_") is not None else "нет данных"))
            parts.append("Наблюдение (%d, тревог: %d):\n%s" % (len(w["items"]), len(w["alerts"]), "\n".join(ln)))
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
        try:
            if cfg.get("tg_on_mon", True) and cfg.get("token"):
                al = [a for a in build_monitor(cfg, "all")["alerts"] if a["severity"] == "high"]
                n += _tg_dispatch(cfg, "Тревоги по портфелю", al, sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:
            if cfg.get("tg_on_mon", True) and cfg.get("token"):
                today_ = date.today().isoformat()
                due = [(k, t) for k, t in tg_offer_due(_tg_offer_items(cfg, today_), today_) if k not in sent][:10]
                if due:
                    tg_send(cfg, "<b>Оферты по портфелю</b>\n\n" + "\n\n".join(t for _k, t in due))
                    for k, _t in due:
                        sent[k] = now
                    n += len(due)
        except Exception:  # noqa: BLE001
            pass
        try:
            if cfg.get("tg_on_watch", True) and (watch_isins() or notes_all()):
                al = [a for a in watch_payload(cfg)["alerts"] if a["severity"] != "info"]
                n += _tg_dispatch(cfg, "Наблюдение и цели", al, sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:
            days = int(cfg.get("tg_pay_days") or 0)
            if days > 0 and cfg.get("token"):
                ev = [e for e in _tg_payments(cfg, days)]
                fresh = []
                for e in ev:
                    k = "pay|%s|%s|%s" % (e[0], e[1], e[2])
                    if k not in sent:
                        fresh.append((k, e))
                if fresh:
                    tg_send(cfg, "<b>Ближайшие выплаты (%d дн.)</b>\n\n%s" % (days, "\n".join(_tg_ev_line(e) for k, e in fresh[:15])))
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
