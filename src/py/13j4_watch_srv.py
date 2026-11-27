

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
    p = {"v": 1, "goals": [], "reminders": [], "offers": [], "pay_days": 0, "pays": [], "sent": [],
         "weekly_digest": bool(cfg.get("tg_weekly_digest", False))}
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
    has_port = bool(cfg.get("token") or imports_list())
    if cfg.get("tg_on_mon", True) and has_port:
        try:
            p["offers"] = [{k: o.get(k) for k in ("isin", "name", "kind", "date", "period_start", "period_end", "coupon_status", "new_rate")}
                           for o in _tg_offer_items(cfg, today)]
        except Exception:  # noqa: BLE001
            pass
    days = int(cfg.get("tg_pay_days") or 0)
    if days > 0 and has_port:
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
                                 headers={"Content-Type": "application/json", "X-Client-Key": key, "User-Agent": EXT_UA["User-Agent"], **hwid_headers()})
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


def _tg_srv_merge_goals(goals, deleted=None):
    """Вливает цели, изменённые в боте, в локальный WATCH_KEY, не перезаписывая локальные поля (note, added и т. д.).
    Снимает цели только у ISIN, явно удалённых в боте (deleted): отсутствие бумаги в ответе сервера — не удаление."""
    if not isinstance(goals, list):
        return False
    deleted = {i for i in (_isin_ok(x) for x in (deleted or []) if isinstance(x, str)) if i}
    by_isin = {}
    for g in goals:
        if not isinstance(g, dict):
            continue
        isin = _isin_ok(g.get("isin"))
        if isin:
            by_isin[isin] = g
    changed = False
    with _watch_lock:
        items = watch_items()
        cur_by = {x["isin"]: x for x in items}
        today = date.today().isoformat()
        for isin, g in by_isin.items():
            cur = cur_by.get(isin)
            if cur is None:
                cur = {"isin": isin, "added": today}
                items.append(cur)
                cur_by[isin] = cur
                changed = True
            for k in ("target_yield", "target_price"):
                if k not in g:
                    v = None
                else:
                    v = _num(g[k]) if g[k] is not None and str(g[k]).strip() != "" else None
                    if v is not None and v <= 0:
                        v = None
                if v is None:
                    if k in cur:
                        cur.pop(k, None)
                        changed = True
                else:
                    rv = round(v, 4)
                    if cur.get(k) != rv:
                        cur[k] = rv
                        changed = True
        kept = []
        for x in items:
            if x["isin"] in deleted and x["isin"] not in by_isin and ("target_yield" in x or "target_price" in x):
                x.pop("target_yield", None)
                x.pop("target_price", None)
                changed = True
                if not x.get("note"):
                    continue
            kept.append(x)
        items = kept
        if changed:
            store().put(WATCH_KEY, items)
    if changed:
        mem_clear_watch()
    return changed


def _tg_srv_sync(cfg, sent, force=False, resume=False):
    """Отправляет подписку, если она изменилась, устарела или force. Состояние — в TG_SRV_KEY. -> True, если подписка на сервере.
    resume=True — только по явному включению пользователем: снимает остановку, сделанную в боте (/alerts)."""
    st, now = _tg_srv_state(), time.time()
    p = tg_srv_payload(cfg, sent)
    if resume:
        p["resume"] = True
    p["bot_goals_rev"] = int((st or {}).get("bot_goals_rev") or 0)
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
        rev, prev_rev = j.get("bot_goals_rev"), st.get("bot_goals_rev")
        # цели из бота вливаем, только если программа сама отправляет цели (иначе пустой список в ответе ничего не значит)
        if cfg.get("tg_on_watch", True) and isinstance(j.get("goals"), list) and rev is not None and rev != (prev_rev or 0):
            _tg_srv_merge_goals(j["goals"], j.get("bot_deleted"))
        st = {"active": True, "ok": now, "hash": h, "err": "", "at": now, "counts": j.get("counts") or {}}
        if rev is not None:
            st["bot_goals_rev"] = rev
        elif prev_rev is not None:
            st["bot_goals_rev"] = prev_rev
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
