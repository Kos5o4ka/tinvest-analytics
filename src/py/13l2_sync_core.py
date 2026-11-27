# ═══════════════ облачная синхронизация между устройствами: шифрование, слепок, слияние ═══════════════
# Токен Т-Инвестиций в слепок не входит никогда. В слепок попадают только: счета, импортированные из отчётов и добавленные
# вручную (названия, брокер, список файлов), их операции, «снимки» счетов Т-Инвестиций (операции без токена, чтобы открыть
# счёт на втором компьютере), список наблюдения, дневник, несекретные настройки (цели ребалансировки, тарифы брокеров, налоговые
# настройки). Слепок сжимается и шифруется на этом компьютере ключом из кодовой фразы (AES-256-CTR + HMAC-SHA256, как у резервной
# копии) — сервер хранит только шифртекст и прочитать его не может.
# Слияние — трёхстороннее (прежнее согласованное состояние, локальное, удалённое) по записям: правка с одной стороны побеждает
# неизменённое с другой, удаление с одной стороны переносится, при правках с обеих сторон побеждает более свежая запись.
import zlib

SYNC_MAGIC = b"TINVSYN1"
SYNC_ITER = 300000
SYNC_V = 1
SYNC_TOMB_DAYS = 180
SYNC_CFG_KEYS = ("targets", "broker_tariffs")
SYNC_BASE_KEY, SYNC_STATE_KEY, SYNC_TB_KEY = "sync_base_v1", "sync_state_v1", "tb_accounts_v1"
SYNC_BOT_ACC = "imp-tgbot"           # ручной счёт для операций, присланных боту
SYNC_MASS_LOSS = 0.5                  # пропала больше половины СЧЕТОВ: считаем, что локальные данные сброшены, а не удалены
SYNC_MASS_MIN_ACCS = 4                # с меньшим числом счетов долю не считаем (пустая локальная база проверяется отдельно)
SYNC_DELS_KEY = "sync_dels_v1"        # явные удаления счетов, ещё не отправленные в облако: {rid счёта: время}
SYNC_SECRET_FIELDS = ("token", "data_key", "backup_password", "sync_master")
SECRET_KEYS.add("sync_master")


class SyncError(Exception):
    pass


# ───────────── шифрование ─────────────
def sync_derive(phrase, salt_b64):
    """Кодовая фраза + соль -> 32-байтный мастер-ключ (PBKDF2-HMAC-SHA256). Фраза на диск не сохраняется."""
    import unicodedata
    p = unicodedata.normalize("NFC", str(phrase or "")).strip()
    if len(p) < 12:
        raise SyncError("Кодовая фраза слишком короткая: нужно не меньше 12 символов.")
    salt = base64.b64decode(salt_b64.encode("ascii"))
    return hashlib.pbkdf2_hmac("sha256", p.encode("utf-8"), salt, SYNC_ITER, 32)


def sync_new_salt():
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def sync_new_phrase():
    """Случайная фраза: 5 групп по 4 символа из алфавита без похожих знаков (около 100 бит)."""
    al = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(al) for _ in range(4)) for _ in range(5))


def _sync_keys(master):
    return (hmac.new(master, b"tinvest-sync-enc", hashlib.sha256).digest(),
            hmac.new(master, b"tinvest-sync-mac", hashlib.sha256).digest())


def sync_seal(master, plain):
    """MAGIC(8) | nonce(12) | шифртекст | HMAC-SHA256(32) по всему предыдущему."""
    ek, mk = _sync_keys(master)
    nonce = secrets.token_bytes(12)
    head = SYNC_MAGIC + nonce
    body = aes256_ctr(ek, nonce + b"\0\0\0\0", plain)
    return head + body + hmac.new(mk, head + body, hashlib.sha256).digest()


def sync_open(master, blob):
    if len(blob) < 8 + 12 + 32 or blob[:8] != SYNC_MAGIC:
        raise SyncError("Облачная копия повреждена или создана другой версией программы.")
    ek, mk = _sync_keys(master)
    if not hmac.compare_digest(hmac.new(mk, blob[:-32], hashlib.sha256).digest(), blob[-32:]):
        raise SyncError("Неверная кодовая фраза или облачная копия повреждена.")
    return aes256_ctr(ek, blob[8:20] + b"\0\0\0\0", blob[20:-32])


def sync_pack(recs, tombs, device="", now=None, rev=None, salt=None):
    """rev и salt вкладываются в зашифрованные данные (они под HMAC): сервер не сможет незаметно подсунуть старый блок под новым
    номером версии или блок от другой соли. Старые блоки без этих полей читаются как раньше."""
    doc = {"v": SYNC_V, "device": device, "at": now if now is not None else time.time(), "recs": recs, "tombs": tombs}
    if rev is not None:
        doc["rev"] = int(rev)
    if salt is not None:
        doc["salt"] = str(salt)
    return zlib.compress(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)


def sync_unpack(plain):
    d = sync_doc(plain)
    return d["recs"], dict(d.get("tombs") or {})


def sync_doc(plain):
    """Разобранный документ слепка целиком (recs, tombs, rev, salt, device)."""
    try:
        doc = json.loads(zlib.decompress(plain).decode("utf-8"))
    except (zlib.error, ValueError, UnicodeDecodeError):
        raise SyncError("Облачная копия повреждена.")
    if not isinstance(doc, dict) or doc.get("v") != SYNC_V or not isinstance(doc.get("recs"), dict):
        raise SyncError("Облачная копия создана более новой версией программы: обновите TAnalytic.")
    return doc


# ───────────── записи слепка ─────────────
def _sync_sig(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sync_same(a, b):
    if a is None or b is None:
        return a is None and b is None
    return _sync_sig(a.get("v")) == _sync_sig(b.get("v"))


def _sync_logical(acc_id):
    return acc_id


def _sync_rec_op(o, derived):
    """Запись операции; метка времени — момент правки ручной записи (_u), чтобы в споре побеждала правка, сделанная позже,
    а не та, что раньше дошла до облака."""
    r = {"k": "op", "v": _sync_op_clean(o, derived)}
    if o.get("_u"):
        r["u"] = float(o["_u"])
    return r


def _sync_op_clean(o, derived):
    o = {k: v for k, v in o.items() if k not in ("_acc", "_accname")}
    if derived:                       # доходность сделки пересчитывается FIFO на каждом устройстве
        o.pop("yield", None)
        o.pop("_yield", None)
    return o


def sync_collect(cfg, st=None):
    """Локальное состояние -> {rid: {"k": вид, "v": значение}}. Без токена, счетов брокера по API и секретов."""
    st = st or store()
    recs = {}
    demo = lambda x: bool(x.get("demo") or x.get("id") == DEMO_ID)      # noqa: E731
    live_ids = set()
    tbm = st.get(SYNC_TB_KEY) or {}
    if (cfg.get("token") or "").strip() and not cfg.get("sandbox"):
        pre = token_key(cfg) + ":"
        for aid, m in tbm.items():
            ops = st.ops(pre + aid)
            if not ops:
                continue
            live_ids.add(aid)
            recs["acc:tb:" + aid] = {"k": "acc", "v": {"kind": "tb", "aid": aid, "name": str(m.get("name") or aid)[:80],
                                                         "type": str(m.get("type") or "")[:20]}}
            for o in ops:
                recs["op:tb:%s|%s" % (aid, op_key(o))] = _sync_rec_op(o, False)
    for x in imports_list():
        if demo(x) or not str(x.get("id") or "").startswith("imp-"):
            continue
        xid = x["id"]
        if x.get("sync_src") == "tinvest":                      # снимок счёта Т-Инвестиций, полученный из облака
            aid = x.get("src_acc") or ""
            if aid in live_ids or not aid:
                continue                                       # на компьютере с токеном источник истины — API
            recs["acc:tb:" + aid] = {"k": "acc", "v": {"kind": "tb", "aid": aid, "name": str(x.get("name") or aid)[:80],
                                                         "type": str(x.get("type") or "")[:20]}}
            for o in st.ops(xid):
                recs["op:tb:%s|%s" % (aid, op_key(o))] = _sync_rec_op(o, False)
            continue
        v = {k: val for k, val in x.items() if k != "ops"}
        recs["acc:" + xid] = {"k": "acc", "v": v}
        for o in st.ops(xid):
            recs["op:%s|%s" % (xid, op_key(o))] = _sync_rec_op(o, True)
    for it in watch_items():
        recs["watch:" + it["isin"]] = {"k": "watch", "v": it}
    for n in notes_all():
        recs["note:" + n["id"]] = {"k": "note", "v": n}
    for k in SYNC_CFG_KEYS:
        if cfg.get(k):
            recs["cfg:" + k] = {"k": "cfg", "v": cfg[k]}
    tax = st.get(TAX_SETTINGS_KEY)
    if tax:
        recs["kv:tax"] = {"k": "kv", "v": tax}
    return recs


def _sync_deletable(rid):
    """Исчезновение записи считается удалением пользователем. Счета Т-Инвестиций из API (acc:tb:) и их операции (op:tb:) так
    не удаляются: токен могли очистить, сменить, включить песочницу, а это не удаление счёта. Явное удаление снимка счёта
    идёт через надгробие (sync_mark_deleted)."""
    return not rid.startswith(("op:tb:", "acc:tb:"))


def _sync_acc_rid(rid):
    return rid.startswith("acc:") and not rid.startswith("acc:tb:")


def sync_mark_deleted(acc_id):
    """Пользователь сам удалил счёт (импорт, ручной счёт или снимок счёта Т-Инвестиций): запомнить как явное удаление, чтобы
    эвристика «база сброшена» не вернула счёт из облака. acc_id — код счёта в списке (imp-…)."""
    acc_id = str(acc_id or "")
    if not acc_id.startswith("imp-"):
        return
    rid = "acc:tb:" + acc_id[len("imp-tb-"):] if acc_id.startswith("imp-tb-") else "acc:" + acc_id
    st = store()
    d = dict(st.get(SYNC_DELS_KEY) or {})
    d[rid] = time.time()
    st.put(SYNC_DELS_KEY, d)


def sync_local_view(cur, base, now, dels=None):
    """Локальные записи с метками времени правки + удаления с прошлой синхронизации. -> (recs, tombs, base_eff).
    Метка записи: прежняя, если запись не менялась с прошлой синхронизации; иначе «сейчас»; без прежнего состояния (первая
    синхронизация этого устройства) — 0, чтобы в спорах побеждали данные облака.
    Если пропала большая доля СЧЕТОВ или в базе не осталось ни одного счёта (стёрта база, восстановлена копия), это не удаление:
    прежнее состояние отбрасывается, и данные вернутся из облака. Одиночное удаление счёта эвристика не считает сбросом, а
    явные удаления (dels: {acc:<id>: время}) всегда становятся надгробиями. Записи, исчезновение которых не считается удалением
    (acc:tb:, op:tb:), переносятся в локальный вид без изменений."""
    brecs, btombs = base.get("recs") or {}, dict(base.get("tombs") or {})
    dels = {rid: ts for rid, ts in (dels or {}).items() if rid not in cur}
    base_accs = [rid for rid in brecs if _sync_acc_rid(rid)]
    lost_accs = [rid for rid in base_accs if rid not in cur and rid not in dels]
    if lost_accs and (not any(_sync_acc_rid(rid) for rid in cur)
                      or (len(base_accs) >= SYNC_MASS_MIN_ACCS and len(lost_accs) > len(base_accs) * SYNC_MASS_LOSS)):
        base, brecs = {"recs": {}, "tombs": btombs}, {}
    lost = [rid for rid in brecs if rid not in cur and _sync_deletable(rid) and not _sync_dead_acc(rid, dels)]
    recs = {}
    for rid, r in cur.items():
        b = brecs.get(rid)
        recs[rid] = {"k": r["k"], "v": r["v"], "u": (b.get("u") or 0) if b and _sync_same(b, r) else (r.get("u") or (now if brecs else 0))}
    for rid, b in brecs.items():
        if rid not in cur and not _sync_deletable(rid) and not _sync_dead_acc(rid, dels):
            recs[rid] = dict(b)                                 # исчезло не по воле пользователя: локально «не менялось»
    for rid in lost:
        btombs[rid] = max(now, btombs.get(rid, 0))
    for arid, ts in dels.items():
        btombs[arid] = max(ts, btombs.get(arid, 0))
        lid = arid[4:]
        for rid in brecs:
            if rid.startswith("op:" + lid + "|"):
                btombs[rid] = max(ts, btombs.get(rid, 0))
                recs.pop(rid, None)
        recs.pop(arid, None)
    return recs, btombs, base


def _sync_dead_acc(rid, dels):
    """Запись относится к счёту, удалённому явно."""
    if rid.startswith("acc:"):
        return rid in dels
    if rid.startswith("op:"):
        return ("acc:" + rid[3:].split("|", 1)[0]) in dels
    return False


def _sync_killed(tombs, rid, rec):
    t = tombs.get(rid)
    return t is not None and t >= (rec.get("u") or 0)


def _sync_merge_acc(a, b):
    """Один счёт правили на двух устройствах: свежая запись + объединённый список загруженных файлов."""
    new, old = (a, b) if (a.get("u") or 0) >= (b.get("u") or 0) else (b, a)
    v = dict(new["v"])
    files, seen = [], set()
    for f in (new["v"].get("files") or []) + (old["v"].get("files") or []):
        key = f.get("sha256") or f.get("name")
        if key not in seen:
            seen.add(key)
            files.append(f)
    if files:
        v["files"] = files
    return {"k": "acc", "v": v, "u": new.get("u") or 0}


def sync_merge(base, local, remote, tombs_l, tombs_r, now):
    """Трёхстороннее слияние записей. base/local/remote: {rid: {"k","v","u"}}. -> (merged, tombs).
    Удаления: запись пропала с одной стороны относительно base — удаляем; удалили с одной стороны, а с другой правили —
    побеждает более поздняя из двух меток (время удаления против времени правки)."""
    tombs = {}
    cutoff = now - SYNC_TOMB_DAYS * 86400
    for src in (tombs_r or {}, tombs_l or {}):
        for rid, ts in src.items():
            if ts > tombs.get(rid, 0):
                tombs[rid] = ts
    tombs = {k: v for k, v in tombs.items() if v > cutoff}
    out = {}
    for rid in set(base) | set(local) | set(remote):
        b, l, r = base.get(rid), local.get(rid), remote.get(rid)
        if _sync_same(l, r):
            res = l if l is not None else None
            if l is not None and r is not None and (r.get("u") or 0) > (l.get("u") or 0):
                res = r
        elif _sync_same(b, l):
            res = r
        elif _sync_same(b, r):
            res = l
        elif l is None or r is None:
            live = l if l is not None else r
            res = None if _sync_killed(tombs, rid, live) else live
        elif l["k"] == "acc":
            res = _sync_merge_acc(l, r)
        else:
            res = r if (r.get("u") or 0) > (l.get("u") or 0) else l
        if res is not None and _sync_killed(tombs, rid, res):
            res = None                                    # удалено позже, чем правили
        if res is not None:
            out[rid] = res
    # операции удалённых счетов не нужны
    accs = {rid[4:] for rid in out if rid.startswith("acc:")}
    for rid in [r for r in out if r.startswith("op:")]:
        if rid[3:].split("|", 1)[0] not in accs:
            out.pop(rid)
    return out, tombs


# ───────────── очередь из бота ─────────────
SYNC_BOT_KINDS = {"buy": "BUY", "sell": "SELL", "deposit": "INPUT", "withdraw": "OUTPUT"}


def sync_queue_recs(items, now):
    """Элементы очереди бота -> записи слепка (ручные операции в счёте «Из Telegram» и заметки).
    Идентификатор операции строится из номера в очереди, поэтому повторная обработка ничего не дублирует.
    -> (recs, ids): ids — все разобранные элементы (в т.ч. непригодные), чтобы подтвердить и не копить их."""
    recs, ids = {}, []
    for it in items or []:
        try:
            qid = int(it["id"])
            op = it.get("op") or {}
            created = float(it.get("created_at") or now)
        except (KeyError, TypeError, ValueError):
            continue
        ids.append(qid)
        kind = str(op.get("kind") or "")
        day = str(op.get("date") or "")[:10]
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", day):
            day = datetime.fromtimestamp(created, timezone.utc).strftime("%Y-%m-%d")
        if kind == "note":
            isin = str(op.get("isin") or "").strip().upper()
            text = str(op.get("text") or "").strip()[:2000]
            if re.fullmatch(r"[A-Z0-9]{6,16}", isin) and text:
                nid = "nb%d" % qid
                recs["note:" + nid] = {"k": "note", "u": created, "v": {"id": nid, "isin": isin, "date": day, "text": text}}
            continue
        if kind not in SYNC_BOT_KINDS:
            continue
        try:
            qty = float(op.get("qty") or 0)
            price = float(op.get("price") or 0)
            amount = float(op.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        ident = str(op.get("secid") or "").strip().upper()[:24]
        oid = "man-bot%d" % qid
        if kind in ("buy", "sell"):
            if not ident or qty <= 0 or (price <= 0 and amount <= 0) or qty > 1e9 or price > 1e9:
                continue
            total = round(amount if amount > 0 else qty * price, 2)
            sign = -1 if kind == "buy" else 1
            o = {"id": oid, "date": day + "T12:00:00Z", "type": "OPERATION_TYPE_" + SYNC_BOT_KINDS[kind],
                 "payment": to_money(sign * total), "name": ident, "_ident": ident, "_manual": True, "_u": created,
                 "quantity": str(int(qty)) if qty == int(qty) else repr(qty), "price": to_money(round(total / qty, 6))}
            o["quantityDone"] = o["quantity"]
            recs["op:%s|%s" % (SYNC_BOT_ACC, oid)] = {"k": "op", "u": created, "v": o}
            if kind == "buy":                                  # деньги на покупку: пополнение на ту же сумму
                c = {"id": oid + "-c", "date": o["date"], "type": "OPERATION_TYPE_INPUT", "payment": to_money(total),
                     "name": "Пополнение под покупку", "_manual": True, "_manual_autocash": True, "_pair": oid, "_u": created}
                recs["op:%s|%s" % (SYNC_BOT_ACC, c["id"])] = {"k": "op", "u": created, "v": c}
        else:
            if amount <= 0 or amount > 1e12:
                continue
            o = {"id": oid, "date": day + "T12:00:00Z", "type": "OPERATION_TYPE_" + SYNC_BOT_KINDS[kind],
                 "payment": to_money(amount if kind == "deposit" else -amount),
                 "name": "Пополнение" if kind == "deposit" else "Вывод", "_manual": True, "_u": created}
            recs["op:%s|%s" % (SYNC_BOT_ACC, oid)] = {"k": "op", "u": created, "v": o}
    if any(r["k"] == "op" for r in recs.values()):
        recs["acc:" + SYNC_BOT_ACC] = {"k": "acc", "u": 0, "v": {
            "id": SYNC_BOT_ACC, "name": "Из Telegram", "broker": "Ручной учёт", "manual": True, "files": [],
            "created": utc_now_str()}}
    return recs, ids
