# ═══════════════════════════════ список наблюдения, заметки, уведомления в Telegram ═══════════════════════════════
# Список наблюдения и дневник хранятся только в локальной базе. Уведомления в Telegram идут через сервер данных
# (POST /v1/notify с ключом из бота) и общий бот: наружу уходят только тексты уведомлений, токен Т-Инвестиций — никогда.
# По желанию (tg_server) на сервер уходит ещё «подписка» на тревоги по публичным данным — см. раздел «проверка на сервере» ниже.
# Прежний «личный бот» (tg_token, tg_chat) удалён; старые значения стираются из настроек при запуске.

WATCH_KEY, NOTES_KEY, TG_SENT_KEY, TG_STATE_KEY = "watch_v1", "notes_v1", "tg_sent_v1", "tg_state_v1"
TG_DEFAULTS = {"tg_enabled": False, "tg_on_mon": True, "tg_on_watch": True, "tg_pay_days": 0, "tg_digest": False, "tg_digest_time": "10:00",
               "tg_weekly_digest": False, "tg_server": False}
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


