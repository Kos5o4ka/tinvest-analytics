# ═══════════════ облачная синхронизация: обмен с сервером данных, применение слияния, настройки ═══════════════
# По умолчанию выключена (cfg["sync_enabled"]). Токен Т-Инвестиций на сервер не передаётся никогда; на сервер уходит
# только зашифрованный на этом компьютере блок (см. 13l2_sync_core.py). Ключ шифрования (производный от кодовой фразы)
# хранится в настройках как секрет и в резервные копии не попадает; сама фраза на диск не записывается.

SYNC_PERIOD = 600                      # опрос облака, пока программа открыта
SYNC_KICK_DELAY = 6                    # после правки данных — через столько секунд
_sync_lock = threading.Lock()
_sync_kick_state = {"timer": None}


def sync_device_name(cfg):
    import platform
    name = str(cfg.get("sync_device") or "").strip()
    return (name or {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(platform.system(), platform.system() or "ПК"))[:40]


def sync_req(method, path, body=None, timeout=90):
    """{сервер}/v1/sync/<path> -> (код, dict). Бросает ApiError, если сервера или ключа нет или нет связи."""
    srv, key = ds_conf()
    if not srv or not key:
        raise ApiError("Для синхронизации нужен вход по ключу из Telegram-бота.", 400)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(srv.rstrip("/") + "/v1/sync/" + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Client-Key": key,
                                          "User-Agent": EXT_UA["User-Agent"]})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    except Exception as e:  # noqa: BLE001
        raise ApiError("Нет связи с сервером: %s" % (getattr(e, "reason", None) or type(e).__name__), 502)
    try:
        j = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        j = None
    j = j if isinstance(j, dict) else {}
    if code in (401, 403):
        raise ApiError("Ключ из бота не принят: войдите заново.", 401)
    if code == 404:
        raise ApiError("Этот сервер данных пока не поддерживает синхронизацию.", 404)
    if code == 429:
        raise ApiError("Слишком частые обращения к серверу, повторим позже.", 429)
    return code, j


def _sync_recs_equal(a, b):
    if set(a) != set(b):
        return False
    return all(_sync_same(a[k], b[k]) and (a[k].get("u") or 0) == (b[k].get("u") or 0) for k in a)


def _sync_ops_sigs(recs):
    return {rid: _sync_sig(r["v"]) for rid, r in recs.items() if r["k"] == "op"}


def sync_apply(cfg, merged, cur):
    """Записывает результат слияния в локальную базу. cur — состояние до слияния (sync_collect). Токен и секреты не трогает."""
    st = store()
    # --- счета и операции ---
    lst_old = imports_list()
    byid = {x.get("id"): x for x in lst_old}
    keep = [x for x in lst_old if x.get("demo") or x.get("id") == DEMO_ID or not str(x.get("id") or "").startswith("imp-")]
    ops_by = defaultdict(list)
    for rid, r in merged.items():
        if r["k"] == "op":
            ops_by[rid[3:].split("|", 1)[0]].append(r["v"])
    cur_sigs, new_sigs = _sync_ops_sigs(cur), _sync_ops_sigs(merged)
    dirty = set()
    for rid in set(cur_sigs) | set(new_sigs):
        if cur_sigs.get(rid) != new_sigs.get(rid):
            dirty.add(rid[3:].split("|", 1)[0])
    client = TInvest(cfg)
    new_list, seen = list(keep), set()
    for rid in sorted(merged):
        r = merged[rid]
        if r["k"] != "acc":
            continue
        v = r["v"]
        if v.get("kind") == "tb":
            logical, xid = "tb:" + v["aid"], "imp-tb-" + v["aid"]
            ex = dict(byid.get(xid) or {})
            ex.update({"id": xid, "name": v.get("name") or v["aid"], "broker": "Т-Инвестиции", "broker_id": "tinvest",
                       "type": v.get("type") or "", "sync_src": "tinvest", "src_acc": v["aid"], "snapshot": True})
            ex.setdefault("files", [])
            ex.setdefault("created", utc_now_str())
            derived = False
        else:
            logical, xid, ex, derived = v["id"], v["id"], dict(v), True
        seen.add(xid)
        ops = [dict(o) for o in ops_by.get(logical, [])]
        if logical in dirty or xid not in byid:
            if derived:
                ops = manual_recompute(client, ops)
            else:
                ops.sort(key=lambda o: o.get("date") or "")
            st.ops_clear(xid)
            st.ops_put(xid, ops)
        ex["ops"] = len(ops)
        new_list.append(ex)
    for x in lst_old:                              # счета, удалённые на другом устройстве
        xid = str(x.get("id") or "")
        if xid.startswith("imp-") and not (x.get("demo") or xid == DEMO_ID) and xid not in seen:
            st.ops_clear(xid)
    st.put("imports", new_list)
    # --- наблюдение, дневник ---
    for name, key, getter in (("watch", WATCH_KEY, watch_items), ("note", NOTES_KEY, notes_all)):
        sid = (lambda it: it["isin"]) if name == "watch" else (lambda it: it["id"])
        want = {rid[len(name) + 1:]: r["v"] for rid, r in merged.items() if r["k"] == name}
        have = {sid(it): it for it in getter()}
        if _sync_sig(want) != _sync_sig(have):
            order = [k for k in have if k in want] + sorted(k for k in want if k not in have)
            st.put(key, [want[k] for k in order])
    # --- настройки ---
    upd = {}
    for k in SYNC_CFG_KEYS:
        r = merged.get("cfg:" + k)
        if r and cfg.get(k) != r["v"]:
            upd[k] = r["v"]
    if upd:
        c2 = load_config()
        c2.update(upd)
        save_config(c2)
    t = merged.get("kv:tax")
    if t and st.get(TAX_SETTINGS_KEY) != t["v"]:
        st.put(TAX_SETTINGS_KEY, t["v"])
    mem_clear()
    try:
        mem_clear_watch()
    except Exception:  # noqa: BLE001
        pass


def _sync_state_save(**kw):
    st = dict(store().get(SYNC_STATE_KEY) or {})
    st.update(kw)
    store().put(SYNC_STATE_KEY, st)
    return st


def sync_cfg_ready(cfg):
    return bool(cfg.get("sync_enabled") and cfg.get("sync_master") and cfg.get("sync_salt"))


def sync_run(reason=""):
    """Один цикл: забрать из облака, слить, при необходимости отправить обратно и применить локально. -> статус."""
    cfg = load_config()
    if not sync_cfg_ready(cfg):
        raise ApiError("Синхронизация выключена.", 400)
    with _sync_lock:
        try:
            res = _sync_run(cfg)
            _sync_state_save(error="", at=time.time(), **res)
        except ApiError as e:
            _sync_state_save(error=str(e))
            raise
        except SyncError as e:
            _sync_state_save(error=str(e))
            raise ApiError(str(e), 400)
    return sync_status()


SYNC_LOCAL_RETRIES = 2                  # сколько раз повторить цикл, если локальные данные изменились во время обмена


def _sync_dels_get(st):
    return dict(st.get(SYNC_DELS_KEY) or {})


def _sync_run(cfg):
    st = store()
    master, salt = bytes.fromhex(cfg["sync_master"]), cfg["sync_salt"]
    state = st.get(SYNC_STATE_KEY) or {}
    base = st.get(SYNC_BASE_KEY) or {}
    device = sync_device_name(cfg)
    now = time.time()
    local_tries, conflicts = 0, 0
    while True:
        cur, dels = sync_collect(cfg, st), _sync_dels_get(st)
        code, j = sync_req("GET", "pull")
        if code != 200 or not j.get("ok"):
            raise ApiError("Сервер ответил %d на запрос облачной копии." % code, 502)
        queue = j.get("queue_items") or []
        warning = ""
        use_base = base
        if j.get("exists"):
            if j.get("salt") != salt:
                raise ApiError("Облачная копия создана с другой кодовой фразой. Выключите синхронизацию и подключитесь заново.", 409)
            doc = sync_doc(sync_open(master, base64.b64decode(j["blob"])))
            remote, tombs_r = doc["recs"], dict(doc.get("tombs") or {})
            rev = int(j["rev"])
            if doc.get("rev") is not None and int(doc["rev"]) != rev:
                raise ApiError("Облачная копия не соответствует номеру версии на сервере (подмена блока или сбой сервера). "
                               "Данные на этом компьютере не тронуты.", 409)
            if doc.get("salt") not in (None, salt):
                raise ApiError("Облачная копия создана с другой кодовой фразой. Выключите синхронизацию и подключитесь заново.", 409)
            if rev < int(state.get("rev") or 0):
                # сервер вернул версию старее той, что уже была: откат или подсунутый старый блок. Удалений из сравнения со
                # старым состоянием не применяем: данные объединяются, затем уходят в облако как новая версия.
                warning = ("Сервер вернул более старую версию облачной копии (откат или подмена). Удаления на этот раз не "
                           "применялись: данные объединены и отправлены заново.")
                use_base = {"recs": {}, "tombs": base.get("tombs") or {}}
                tombs_r = {}
        else:
            if state.get("rev"):
                _sync_off(cfg)
                raise ApiError("Облачная копия удалена на сервере (возможно, кнопкой на другом устройстве). Синхронизация выключена, "
                               "данные на этом компьютере не тронуты.", 410)
            remote, tombs_r, rev = {}, {}, 0
        qrecs, qids = sync_queue_recs(queue, now)
        local, tombs_l, base_eff = sync_local_view(cur, use_base, now, dels)
        for rid, r in qrecs.items():
            if rid not in local and not _sync_killed(tombs_l, rid, r):
                local[rid] = r
        merged, tombs = sync_merge(base_eff.get("recs") or {}, local, remote, tombs_l, tombs_r, now)
        pushed = False
        if not j.get("exists") or not _sync_recs_equal(merged, remote) or tombs != tombs_r or qids or warning:
            blob = sync_seal(master, sync_pack(merged, tombs, device, now, rev=rev + 1, salt=salt))
            code, pj = sync_req("POST", "push", {"base_rev": rev, "device": device, "salt": salt, "sha256": hashlib.sha256(blob).hexdigest(),
                                                  "blob": base64.b64encode(blob).decode("ascii"), "ack_queue_ids": qids})
            if code == 409:
                conflicts += 1
                if conflicts > 4:
                    break
                continue                                    # кто-то успел раньше: заново забираем и сливаем
            if code == 413:
                raise ApiError("Данные не помещаются в облачную копию (до 4 МБ в сжатом виде).", 413)
            if code != 200 or not pj.get("ok"):
                raise ApiError("Сервер не принял облачную копию (ответ %d)." % code, 502)
            rev, pushed = int(pj["rev"]), True
        with _man_lock:                                     # тот же замок, что у ручного учёта и импорта
            if sync_collect(cfg, st) != cur or _sync_dels_get(st) != dels:
                changed = True
            else:
                changed = False
                if not _sync_recs_equal(merged, cur_with_u(cur, merged)):
                    sync_apply(cfg, merged, cur)
                st.put(SYNC_BASE_KEY, {"recs": merged, "tombs": tombs})
                left = {k: v for k, v in _sync_dels_get(st).items() if k not in dels}
                st.put(SYNC_DELS_KEY, left)
        if not changed:
            return {"rev": rev, "device": device, "pushed": pushed, "records": len(merged), "queue_taken": len(qids), "warning": warning}
        # Пока шёл обмен, данные на этом компьютере изменились (ручная запись, импорт): прежнее состояние не трогаем, цикл заново.
        # Облако уже содержит наш результат, трёхстороннее слияние с прежним состоянием учтёт и новые правки.
        local_tries += 1
        if local_tries > SYNC_LOCAL_RETRIES:
            break
    raise ApiError("Не удалось согласовать изменения: данные одновременно меняют на нескольких устройствах или на этом компьютере. "
                   "Повторим позже.", 409)


def cur_with_u(cur, merged):
    """Локальные записи с метками слияния (для сравнения «изменилось ли что-то локально»)."""
    return {rid: dict(r, u=(merged.get(rid) or {}).get("u") or 0) for rid, r in cur.items()}


def _sync_off(cfg):
    c2 = load_config()
    c2["sync_enabled"], c2["sync_master"] = False, ""
    save_config(c2)
    store().put(SYNC_BASE_KEY, {})


def sync_status(cfg=None):
    cfg = cfg or load_config()
    st = store().get(SYNC_STATE_KEY) or {}
    srv, key = ds_conf()
    return {"enabled": bool(cfg.get("sync_enabled")), "ready": sync_cfg_ready(cfg), "logged_in": bool(srv and key),
            "rev": st.get("rev") or 0, "at": st.get("at"), "error": st.get("error") or "", "device": st.get("device") or sync_device_name(cfg),
            "records": st.get("records") or 0, "queue_taken": st.get("queue_taken") or 0, "warning": st.get("warning") or ""}


def sync_run_bg(reason=""):
    try:
        sync_run(reason)
    except Exception:  # noqa: BLE001      ошибка уже записана в состояние и показывается в Настройках
        pass


def sync_kick(delay=SYNC_KICK_DELAY):
    """Данные изменились: через несколько секунд отправить в облако (если синхронизация включена). Серия правок — один запуск."""
    try:
        if not sync_cfg_ready(load_config()):
            return
    except Exception:  # noqa: BLE001
        return
    with _sync_lock_kick:
        t = _sync_kick_state.get("timer")
        if t:
            t.cancel()
        t = threading.Timer(delay, sync_run_bg, args=("kick",))
        t.daemon = True
        _sync_kick_state["timer"] = t
        t.start()


_sync_lock_kick = threading.Lock()


def sync_loop():
    time.sleep(25)
    while True:
        try:
            if sync_cfg_ready(load_config()):
                sync_run_bg("loop")
        except Exception:  # noqa: BLE001
            pass
        time.sleep(SYNC_PERIOD)


def sync_start():
    threading.Thread(target=sync_loop, daemon=True, name="sync").start()


STARTUP_HOOKS.append(sync_start)


# ───────────── включение, выключение, удаление ─────────────
def sync_enable(cfg, body):
    mode = str(body.get("mode") or "create")
    srv, key = ds_conf()
    if not srv or not key:
        raise ApiError("Для синхронизации нужен вход по ключу из Telegram-бота.", 400)
    code, meta = sync_req("GET", "meta")
    phrase, generated = str(body.get("phrase") or "").strip(), False
    if mode == "create":
        if meta.get("exists"):
            raise ApiError("На сервере уже есть облачная копия. Подключитесь к ней по её кодовой фразе или сначала удалите её.", 409)
        if not phrase:
            phrase, generated = sync_new_phrase(), True
        salt = sync_new_salt()
        master = sync_derive(phrase, salt)
    elif mode == "join":
        if not meta.get("exists"):
            raise ApiError("На сервере нет облачной копии: сначала включите синхронизацию на другом устройстве.", 404)
        salt = meta["salt"]
        try:
            master = sync_derive(phrase, salt)
            code, j = sync_req("GET", "pull")
            sync_open(master, base64.b64decode(j["blob"]))          # проверка кодовой фразы до сохранения
        except SyncError as e:
            raise ApiError(str(e), 400)
    else:
        raise ApiError("Неизвестный режим.", 400)
    c2 = load_config()
    c2.update(sync_enabled=True, sync_master=master.hex(), sync_salt=salt)
    save_config(c2)
    store().put(SYNC_BASE_KEY, {})
    store().put(SYNC_STATE_KEY, {})
    store().put(SYNC_DELS_KEY, {})
    try:
        sync_run("enable")
    except ApiError as e:                       # первый обмен не удался: не говорим «включена», настройки возвращаем как были
        c3 = load_config()
        c3["sync_enabled"], c3["sync_master"], c3["sync_salt"] = False, "", ""
        save_config(c3)
        store().put(SYNC_BASE_KEY, {})
        store().put(SYNC_STATE_KEY, {})
        raise ApiError("Не удалось включить синхронизацию: %s" % e, getattr(e, "status", 502) or 502)
    out = sync_status()
    out["ok"] = True
    if generated:
        out["phrase"] = phrase
    return out


def sync_disable(cfg, delete_remote=False):
    """Выключает синхронизацию; локальные данные остаются. delete_remote — ещё и стирает облачную копию и очередь на сервере."""
    deleted = None
    if delete_remote:
        code, j = sync_req("POST", "delete", {})
        if code != 200:
            raise ApiError("Не удалось удалить данные на сервере (ответ %d). Синхронизация осталась включённой." % code, 502)
        deleted = bool(j.get("deleted"))
    c2 = load_config()
    c2["sync_enabled"], c2["sync_master"], c2["sync_salt"] = False, "", ""
    save_config(c2)
    store().put(SYNC_BASE_KEY, {})
    store().put(SYNC_STATE_KEY, {})
    store().put(SYNC_DELS_KEY, {})
    out = sync_status()
    out.update(ok=True, deleted=deleted)
    return out


def sync_server_info():
    """Есть ли облачная копия на сервере (для экрана подключения второго устройства)."""
    code, j = sync_req("GET", "meta")
    return {"exists": bool(j.get("exists")), "rev": j.get("rev") or 0, "updated_at": j.get("updated_at"),
            "device": j.get("device") or "", "size": j.get("size") or 0, "queue": j.get("queue") or 0}


def sync_post(cfg, body):
    act = str(body.get("action") or "")
    if act == "enable":
        return sync_enable(cfg, body)
    if act == "now":
        return sync_run("manual")
    if act == "disable":
        return sync_disable(cfg, bool(body.get("delete_remote")))
    if act == "delete":
        return sync_disable(cfg, True)
    raise ApiError("Неизвестное действие.", 400)


def sync_get(cfg, acc, q, force):
    out = sync_status(cfg)
    if force and out["logged_in"]:
        try:
            out["server"] = sync_server_info()
        except ApiError as e:
            out["server_error"] = str(e)
    return out


API_GET["/api/sync"] = sync_get
API_POST["/api/sync"] = sync_post
