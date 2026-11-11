# ═══════════════════════════════ список наблюдения, заметки, уведомления в Telegram ═══════════════════════════════
# Список наблюдения и дневник хранятся только в локальной базе. Telegram: личный бот пользователя; наружу (на серверы
# Telegram) уходят только тексты уведомлений. Токен бота — секрет (SECRET_KEYS), в журнал и в ответы API не попадает.

WATCH_KEY, NOTES_KEY, TG_SENT_KEY, TG_STATE_KEY = "watch_v1", "notes_v1", "tg_sent_v1", "tg_state_v1"
TG_DEFAULTS = {"tg_chat": "", "tg_on_mon": True, "tg_on_watch": True, "tg_pay_days": 0, "tg_digest": False, "tg_digest_time": "10:00"}
SECRET_KEYS.add("tg_token")
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

def _tg_base():
    return (os.environ.get("TINVEST_TG_API") or "https://api.telegram.org").rstrip("/")


def _tg_scrub(msg, token):
    msg = str(msg)
    if token:
        msg = msg.replace(token, "***")
    return re.sub(r"bot\d+:[A-Za-z0-9_\-]+", "bot***", msg)[:200]


def tg_call(token, method, params=None, timeout=15):
    """Вызов Bot API. Любые ошибки превращаются в ApiError без токена в тексте."""
    if not token:
        raise ApiError("Токен бота не задан.", 400)
    url = "%s/bot%s/%s" % (_tg_base(), token, method)
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    ctx = None
    if url.startswith("https://"):
        import ssl
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            j = {}
        if e.code in (401, 404):
            raise ApiError("Telegram не принял токен бота. Проверьте, что он скопирован целиком.", 400)
        raise ApiError("Telegram ответил ошибкой: %s" % _tg_scrub(j.get("description") or e.code, token), 502)
    except Exception as e:  # noqa: BLE001
        raise ApiError("Не удалось связаться с Telegram (%s). Если api.telegram.org недоступен из вашей сети, понадобится VPN или прокси."
                       % _tg_scrub(getattr(e, "reason", e), token), 502)
    if not j.get("ok"):
        raise ApiError("Telegram: %s" % _tg_scrub(j.get("description") or "ошибка", token), 502)
    return j.get("result")


def _tg_esc(s):
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


TG_DISCLAIMER = "\n\n<i>Не является ИИР.</i>"


def tg_send(cfg, text):
    chat = str(cfg.get("tg_chat") or "").strip()
    if not chat:
        raise ApiError("Не указан chat id.", 400)
    return tg_call(cfg.get("tg_token"), "sendMessage", {"chat_id": chat, "text": text[:3970] + TG_DISCLAIMER, "parse_mode": "HTML",
                                                         "disable_web_page_preview": True})


def tg_public(cfg):
    return {k: cfg.get(k, d) for k, d in TG_DEFAULTS.items()}


def tg_save(cfg, body):
    cfg = load_config()
    if body.get("token"):
        tok = "".join(str(body["token"]).split())
        if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_\-]{20,}", tok):
            raise ApiError("Токен бота выглядит неверно: он должен быть вида 123456789:AAH… (его выдаёт @BotFather).", 400)
        cfg["tg_token"] = tok
    if body.get("clear_token"):
        cfg["tg_token"] = ""
    if "chat" in body:
        c = str(body["chat"]).strip()
        if c and not re.fullmatch(r"-?\d{1,20}|@[A-Za-z0-9_]{3,64}", c):
            raise ApiError("Chat id — это число (например 123456789). Нажмите «Найти мой chat id».", 400)
        cfg["tg_chat"] = c
    for k in ("tg_on_mon", "tg_on_watch", "tg_digest"):
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
    save_config(cfg)
    return {"ok": True, "token_set": bool(cfg.get("tg_token")), "settings": tg_public(cfg)}


def tg_find_chat(cfg, body):
    cfg = load_config()
    ups = tg_call(cfg.get("tg_token"), "getUpdates", {"limit": 50, "timeout": 0}) or []
    best = None
    for u in ups:
        m = u.get("message") or u.get("edited_message") or u.get("channel_post")
        if m and m.get("chat") and m["chat"].get("id") is not None:
            if m["chat"].get("type", "private") == "private" or best is None:
                best = m["chat"]
    if not best:
        raise ApiError("Сообщений боту пока нет. Откройте своего бота в Telegram, нажмите «Запустить» (/start) или напишите ему любое сообщение и повторите.", 404)
    name = " ".join(x for x in (best.get("first_name"), best.get("last_name")) if x) or best.get("title") or best.get("username") or ""
    cfg["tg_chat"] = str(best["id"])
    save_config(cfg)
    return {"ok": True, "chat": str(best["id"]), "name": name}


def tg_test(cfg, body):
    cfg = load_config()
    tg_send(cfg, "✅ <b>T-Invest Analytics</b>: тестовое сообщение. Уведомления подключены.")
    return {"ok": True}


def tg_run_now(cfg, body):
    n = tg_tick(force_digest=bool(body.get("digest")))
    return {"ok": True, "sent": n}


API_POST["/api/tg/save"] = tg_save
API_POST["/api/tg/find_chat"] = tg_find_chat
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


def tg_tick(force_digest=False):
    """Одна проверка: новые тревоги, выплаты, ежедневная сводка. Возвращает число отправленных пунктов."""
    if not _tg_lock.acquire(False):
        return 0
    try:
        cfg = load_config()
        if not cfg.get("tg_token") or not str(cfg.get("tg_chat") or "").strip():
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
    threading.Thread(target=_tg_loop, daemon=True, name="tg-notify").start()


STARTUP_HOOKS.append(tg_start)
