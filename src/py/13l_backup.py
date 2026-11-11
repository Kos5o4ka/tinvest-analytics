# ═══════════════════════════════ зашифрованная резервная копия и экспорт ═══════════════════════════════
# Шифрование: стандартный AES-256 (FIPS-197) в режиме CTR (NIST SP 800-38A) на чистом Python + HMAC-SHA256
# (encrypt-then-MAC), ключи из пароля через PBKDF2-HMAC-SHA256. Своих шифров нет.
import hmac
import secrets
import struct
import tempfile


def _aes_tables():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = (p ^ (p << 1) ^ (0x11B if p & 0x80 else 0)) & 0xFF         # p *= 3
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        if q & 0x80:
            q ^= 0x09                                                  # q /= 3
        x = q
        for n in (1, 2, 3, 4):
            x ^= ((q << n) | (q >> (8 - n))) & 0xFF
        sbox[p] = x ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    te0, te1, te2, te3 = [], [], [], []
    for s in sbox:
        s2 = ((s << 1) ^ (0x11B if s & 0x80 else 0)) & 0xFF
        s3 = s2 ^ s
        w = (s2 << 24) | (s << 16) | (s << 8) | s3
        te0.append(w)
        te1.append(((w >> 8) | (w << 24)) & 0xFFFFFFFF)
        te2.append(((w >> 16) | (w << 16)) & 0xFFFFFFFF)
        te3.append(((w >> 24) | (w << 8)) & 0xFFFFFFFF)
    return sbox, te0, te1, te2, te3


_SBOX, _TE0, _TE1, _TE2, _TE3 = _aes_tables()


def aes256_expand_key(key):
    """Расписание ключей AES-256: 60 слов по 32 бита."""
    if len(key) != 32:
        raise ValueError("Ключ AES-256 должен быть 32 байта")
    sb = _SBOX
    w = list(struct.unpack(">8I", key))
    rcon = 1
    for i in range(8, 60):
        t = w[i - 1]
        if i % 8 == 0:
            t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
            t = (sb[t >> 24] << 24) | (sb[(t >> 16) & 255] << 16) | (sb[(t >> 8) & 255] << 8) | sb[t & 255]
            t ^= rcon << 24
            rcon = ((rcon << 1) ^ (0x11B if rcon & 0x80 else 0)) & 0xFF
        elif i % 8 == 4:
            t = (sb[t >> 24] << 24) | (sb[(t >> 16) & 255] << 16) | (sb[(t >> 8) & 255] << 8) | sb[t & 255]
        w.append(w[i - 8] ^ t)
    return w


def aes256_encrypt_block(rk, block):
    return b"".join(_aes_blocks(rk, [struct.unpack(">4I", block)]))


def _aes_blocks(rk, blocks):
    """Шифрует список блоков, каждый — кортеж из четырёх 32-битных слов; возвращает список 16-байтных строк."""
    t0, t1, t2, t3, sb = _TE0, _TE1, _TE2, _TE3, _SBOX
    pack = struct.Struct(">4I").pack
    r0, r1, r2, r3 = rk[0], rk[1], rk[2], rk[3]
    rounds = [rk[4 * i:4 * i + 4] for i in range(1, 14)]
    f0, f1, f2, f3 = rk[56], rk[57], rk[58], rk[59]
    out = []
    for a, b, c, d in blocks:
        a ^= r0
        b ^= r1
        c ^= r2
        d ^= r3
        for k0, k1, k2, k3 in rounds:
            a, b, c, d = (t0[a >> 24] ^ t1[(b >> 16) & 255] ^ t2[(c >> 8) & 255] ^ t3[d & 255] ^ k0,
                          t0[b >> 24] ^ t1[(c >> 16) & 255] ^ t2[(d >> 8) & 255] ^ t3[a & 255] ^ k1,
                          t0[c >> 24] ^ t1[(d >> 16) & 255] ^ t2[(a >> 8) & 255] ^ t3[b & 255] ^ k2,
                          t0[d >> 24] ^ t1[(a >> 16) & 255] ^ t2[(b >> 8) & 255] ^ t3[c & 255] ^ k3)
        out.append(pack(
            ((sb[a >> 24] << 24) | (sb[(b >> 16) & 255] << 16) | (sb[(c >> 8) & 255] << 8) | sb[d & 255]) ^ f0,
            ((sb[b >> 24] << 24) | (sb[(c >> 16) & 255] << 16) | (sb[(d >> 8) & 255] << 8) | sb[a & 255]) ^ f1,
            ((sb[c >> 24] << 24) | (sb[(d >> 16) & 255] << 16) | (sb[(a >> 8) & 255] << 8) | sb[b & 255]) ^ f2,
            ((sb[d >> 24] << 24) | (sb[(a >> 16) & 255] << 16) | (sb[(b >> 8) & 255] << 8) | sb[c & 255]) ^ f3))
    return out


def aes256_ctr(key, iv16, data):
    """AES-256-CTR (шифрование и расшифровка одинаковы): счётчик — 128-битное число, +1 на блок (SP 800-38A F.5.5)."""
    rk = aes256_expand_key(key)
    ctr = int.from_bytes(iv16, "big")
    out = bytearray()
    step = 4096 * 16
    mask = (1 << 128) - 1
    for off in range(0, len(data), step):
        chunk = data[off:off + step]
        n = (len(chunk) + 15) // 16
        blocks = []
        for i in range(n):
            v = (ctr + i) & mask
            blocks.append(((v >> 96) & 0xFFFFFFFF, (v >> 64) & 0xFFFFFFFF, (v >> 32) & 0xFFFFFFFF, v & 0xFFFFFFFF))
        ctr = (ctr + n) & mask
        ks = b"".join(_aes_blocks(rk, blocks))[:len(chunk)]
        out += (int.from_bytes(chunk, "big") ^ int.from_bytes(ks, "big")).to_bytes(len(chunk), "big")
    return bytes(out)


BK_MAGIC = b"TINVBAK1"          # 8 байт: формат + версия
BK_ITER = 300000
BK_EXT = ".tinvbak"
BK_RE = re.compile(r"^tinvest_backup_\d{4}-\d{2}-\d{2}(_\d{6})?" + re.escape(BK_EXT) + "$")


class BackupError(Exception):
    pass


def _bk_keys(password, salt, iters):
    master = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters, 32)
    return (hmac.new(master, b"tinvest-backup-enc", hashlib.sha256).digest(),
            hmac.new(master, b"tinvest-backup-mac", hashlib.sha256).digest())


def encrypt_bytes(password, plain, iters=BK_ITER):
    """Файл: MAGIC(8) | итерации KDF u32 | соль(16) | nonce(12) | шифртекст | HMAC-SHA256(32) по всему предыдущему."""
    if not password:
        raise BackupError("Не задан пароль.")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    ek, mk = _bk_keys(password, salt, iters)
    head = BK_MAGIC + struct.pack(">I", iters) + salt + nonce
    body = aes256_ctr(ek, nonce + b"\0\0\0\0", plain)
    return head + body + hmac.new(mk, head + body, hashlib.sha256).digest()


def decrypt_bytes(password, blob):
    if len(blob) < 8 + 4 + 16 + 12 + 32 or blob[:8] != BK_MAGIC:
        raise BackupError("Это не файл резервной копии T-Invest Analytics (или он повреждён).")
    iters = struct.unpack(">I", blob[8:12])[0]
    if not 1000 <= iters <= 20000000:
        raise BackupError("Файл повреждён: неверные параметры шифрования.")
    salt, nonce = blob[12:28], blob[28:40]
    body, tag = blob[40:-32], blob[-32:]
    ek, mk = _bk_keys(password or "", salt, iters)
    if not hmac.compare_digest(hmac.new(mk, blob[:-32], hashlib.sha256).digest(), tag):
        raise BackupError("Неверный пароль или файл повреждён (проверка целостности не пройдена).")
    return aes256_ctr(ek, nonce + b"\0\0\0\0", body)


# ───────────── содержимое копии ─────────────

BK_SKIP_RESTORE = {"token", "sandbox", "verify_ssl", "ca_file", "hosts_prod", "hosts_sandbox"}


def backup_plain():
    """Zip: согласованная копия базы + настройки без токена и без секретов."""
    tmp = os.path.join(APP_DIR, "backup.%d.tmp" % threading.get_ident())
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        cfg = {k: v for k, v in load_config().items() if k not in SECRET_KEYS}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(tmp, "data.db")
            z.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=2))
            z.writestr("README.txt", "Зашифрованная резервная копия T-Invest Analytics. Токен API и пароли в копию не входят.\n")
        return buf.getvalue()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def backup_dir_check(path):
    """(ok, сообщение): папка существует и доступна для записи."""
    p = os.path.expanduser((path or "").strip())
    if not p:
        return False, "Папка не указана."
    if not os.path.isdir(p):
        return False, "Папка не найдена: " + p
    try:
        fd, name = tempfile.mkstemp(prefix=".tinv_w", dir=p)
        os.close(fd)
        os.remove(name)
    except OSError as e:
        return False, "В папку нельзя записывать: %s" % (e.strerror or e)
    return True, "Папка доступна для записи."


def backup_list(dirpath):
    p = os.path.expanduser((dirpath or "").strip())
    out = []
    try:
        for n in os.listdir(p):
            if BK_RE.match(n):
                st = os.stat(os.path.join(p, n))
                out.append({"name": n, "size": st.st_size, "mtime": st.st_mtime})
    except OSError:
        pass
    return sorted(out, key=lambda x: x["name"], reverse=True)


def backup_prune(dirpath, keep):
    """Удаляет самые старые свои копии сверх лимита (только файлы по шаблону имени)."""
    p = os.path.expanduser(dirpath.strip())
    removed = 0
    for x in backup_list(p)[max(1, int(keep)):]:
        try:
            os.remove(os.path.join(p, x["name"]))
            removed += 1
        except OSError:
            pass
    return removed


_bk_lock = threading.Lock()
_bk_state = {"running": False}


def _bk_status_put(**kw):
    try:
        store().put("backup_status", kw)
    except Exception:  # noqa: BLE001
        pass


def run_backup(cfg, password=None, name_time=True):
    """Делает копию в папку назначения; возвращает словарь статуса. Ошибки — BackupError."""
    pw = password or cfg.get("backup_password") or ""
    if not pw:
        raise BackupError("Не задан пароль для шифрования копии.")
    ok, msg = backup_dir_check(cfg.get("backup_dir"))
    if not ok:
        raise BackupError(msg)
    t0 = time.time()
    plain = backup_plain()
    blob = encrypt_bytes(pw, plain)
    now = datetime.now()
    fname = "tinvest_backup_%s%s" % (now.strftime("%Y-%m-%d_%H%M%S") if name_time else now.strftime("%Y-%m-%d"), BK_EXT)
    d = os.path.expanduser(cfg["backup_dir"].strip())
    final = os.path.join(d, fname)
    tmp = final + ".part"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, final)
    removed = backup_prune(d, cfg.get("backup_keep") or 14)
    return {"ok": True, "t": time.time(), "file": fname, "size": len(blob), "sec": round(time.time() - t0, 1), "removed": removed}


def _bk_job(cfg, password, name_time):
    if not _bk_lock.acquire(False):
        return
    _bk_state["running"] = True
    try:
        st = run_backup(cfg, password, name_time)
    except BackupError as e:
        st = {"ok": False, "t": time.time(), "error": str(e)}
    except Exception as e:  # noqa: BLE001
        st = {"ok": False, "t": time.time(), "error": "Не удалось сделать копию: %s" % e}
    finally:
        _bk_state["running"] = False
        _bk_lock.release()
    _bk_status_put(**st)


def _bk_clamp_keep(v, default=14):
    try:
        return max(1, min(365, int(v)))
    except (TypeError, ValueError):
        return default


def _bk_suggest():
    home = os.path.expanduser("~")
    cands = []
    for base in ("Yandex.Disk", "YandexDisk", "Yandex Disk", "Яндекс Диск", "Google Drive", "Google Диск", "iCloudDrive",
                 "OneDrive", "Dropbox", os.path.join("Library", "Mobile Documents", "com~apple~CloudDocs")):
        cands.append(("Яндекс Диск" if "andex" in base or "Яндекс" in base else
                      "Google Drive" if "Google" in base else "iCloud Drive" if "iCloud" in base or "CloudDocs" in base else base,
                      os.path.join(home, base)))
    cs = os.path.join(home, "Library", "CloudStorage")
    try:
        for n in sorted(os.listdir(cs)):
            lab = "Google Drive" if n.startswith("GoogleDrive") else "Яндекс Диск" if "andex" in n else \
                "iCloud Drive" if "iCloud" in n else n
            cands.append((lab, os.path.join(cs, n)))
    except OSError:
        pass
    return [{"label": a, "path": b} for a, b in cands if os.path.isdir(b)]


def api_backup_status(cfg, acc, q, force):
    st = None
    try:
        st = store().get("backup_status")
    except Exception:  # noqa: BLE001
        pass
    d = (cfg.get("backup_dir") or "").strip()
    ok, msg = backup_dir_check(d) if d else (False, "")
    return {"running": _bk_state["running"], "last": st, "dir": d, "dir_ok": ok, "dir_msg": msg,
            "files": backup_list(d) if ok else [], "suggest": _bk_suggest(), "pw_set": bool(cfg.get("backup_password")),
            "auto": bool(cfg.get("backup_auto")), "keep": _bk_clamp_keep(cfg.get("backup_keep")),
            "home": os.path.expanduser("~"), "windows": platform.system() == "Windows",
            "restore_pending": os.path.exists(DB_PATH + ".restore-pending")}


def api_backup_settings(cfg, body):
    if "backup_dir" in body:
        cfg["backup_dir"] = str(body["backup_dir"] or "").strip()
    if "backup_auto" in body:
        cfg["backup_auto"] = bool(body["backup_auto"])
    if "backup_keep" in body:
        cfg["backup_keep"] = _bk_clamp_keep(body["backup_keep"])
    if body.get("backup_password"):
        pw = str(body["backup_password"])
        if len(pw) < 6:
            raise ApiError("Пароль копии — не короче 6 символов.", 400)
        cfg["backup_password"] = pw
    if body.get("clear_password"):
        cfg["backup_password"] = ""
        cfg["backup_auto"] = False
    if cfg.get("backup_auto") and not cfg.get("backup_password"):
        raise ApiError("Для автоматических копий сохраните пароль.", 400)
    if cfg.get("backup_dir"):
        ok, msg = backup_dir_check(cfg["backup_dir"])
        if not ok and (cfg.get("backup_auto") or "backup_dir" in body):
            raise ApiError(msg, 400)
    save_config(cfg)
    return {"ok": True}


def api_backup_run(cfg, body):
    pw = str(body.get("password") or "") or cfg.get("backup_password") or ""
    if not pw:
        raise ApiError("Введите пароль для шифрования копии.", 400)
    ok, msg = backup_dir_check(cfg.get("backup_dir"))
    if not ok:
        raise ApiError(msg, 400)
    if _bk_state["running"]:
        return {"started": False, "running": True}
    threading.Thread(target=_bk_job, args=(dict(cfg), pw, True), daemon=True).start()
    return {"started": True}


def api_backup_restore(cfg, body):
    try:
        blob = base64.b64decode(body.get("data") or "", validate=False)
    except Exception:  # noqa: BLE001
        raise ApiError("Не удалось прочитать файл.", 400)
    try:
        plain = decrypt_bytes(str(body.get("password") or ""), blob)
        z = zipfile.ZipFile(io.BytesIO(plain))
        if "data.db" not in z.namelist():
            raise BackupError("В копии нет базы данных.")
        db = z.read("data.db")
        cfg_new = json.loads(z.read("config.json").decode("utf-8")) if "config.json" in z.namelist() else {}
    except BackupError as e:
        raise ApiError(str(e), 400)
    except (zipfile.BadZipFile, ValueError, KeyError):
        raise ApiError("Содержимое копии повреждено.", 400)
    pend = DB_PATH + ".restore-pending"
    tmp = pend + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(db)
        c = sqlite3.connect(tmp)
        try:
            tabs = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"kv", "ops"} <= tabs or c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("База в копии повреждена или не от этого приложения.")
        finally:
            c.close()
        os.replace(tmp, pend)
    except BackupError as e:
        raise ApiError(str(e), 400)
    except sqlite3.Error:
        raise ApiError("База в копии повреждена.", 400)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if isinstance(cfg_new, dict):       # настройки интерфейса возвращаем; токен, секреты и подключение не трогаем
        for k, v in cfg_new.items():
            if k in SECRET_KEYS or k in BK_SKIP_RESTORE or k.startswith("backup_") or k not in DEFAULT_CONFIG:
                continue
            cfg[k] = v
        save_config(cfg)
    return {"ok": True, "restart": True}


def _bk_loop():
    while True:
        try:
            cfg = load_config()
            if cfg.get("backup_auto") and cfg.get("backup_password") and cfg.get("backup_dir"):
                today = date.today().strftime("tinvest_backup_%Y-%m-%d")
                ok, _m = backup_dir_check(cfg["backup_dir"])
                if not ok:
                    _bk_status_put(ok=False, t=time.time(), error=_m)
                elif not any(x["name"].startswith(today) for x in backup_list(cfg["backup_dir"])):
                    _bk_job(cfg, None, False)
        except Exception as e:  # noqa: BLE001
            _bk_status_put(ok=False, t=time.time(), error="Автокопия: %s" % e)
        time.sleep(900)


def backup_start():
    threading.Thread(target=_bk_loop, daemon=True).start()


# ───────────── экспорт таблиц ─────────────

_EXPORT_NAMES = {"positions": "positions", "bonds": "bonds", "ops": "operations", "payments": "payments", "screener": "screener"}
_KIND_RU = {"coupon": "Купон", "amortization": "Амортизация", "redemption": "Погашение", "dividend": "Дивиденд"}
_TYPE_RU = {"bond": "Облигация", "share": "Акция", "etf": "Фонд", "currency": "Валюта", "futures": "Фьючерс"}


def _ex_table(what, cfg, acc):
    """(заголовки, строки) — значения: числа, строки (даты ISO), None."""
    def pick(items, cols):
        return [[(f(r) if callable(f) else r.get(f)) for _h, f in cols] for r in items]
    if what == "positions":
        d = build_summary(cfg, acc, "all")
        cols = [("Название", "name"), ("Тикер", "ticker"), ("Тип", lambda r: _TYPE_RU.get(r.get("type"), r.get("type"))),
                ("Кол-во", "qty"), ("Средняя цена", "avg"), ("Цена", "price"), ("Валюта", lambda r: (r.get("cur") or "").upper()),
                ("Стоимость", "value"), ("Стоимость, ₽", "value_rub"), ("Вложено, ₽", "cost_rub"),
                ("P&L, ₽", "pnl_rub"), ("P&L, %", "pnl_pct"), ("Доля, %", "share"), ("НКД", "nkd")]
        return [h for h, _ in cols], pick(d["portfolio"]["positions"], cols)
    if what in ("bonds", "payments"):
        d = build_bonds(cfg, acc)
        if what == "payments":
            cols = [("Дата", "date"), ("Вид", lambda r: _KIND_RU.get(r.get("kind"), r.get("kind"))), ("Название", "name"),
                    ("Тикер", "ticker"), ("Сумма, ₽", "amount"),
                    ("Оценка", lambda r: "прогноз" if r.get("est") else "")]
            return [h for h, _ in cols], pick(d["payments"], cols)
        cols = [("Название", "name"), ("Тикер", "ticker"), ("ISIN", "isin"), ("Кол-во", "qty"), ("Стоимость, ₽", "value_rub"),
                ("Доля, %", "share"), ("P&L, ₽", "pnl_rub"), ("P&L, %", "pnl_pct"), ("Цена, % номинала", "price_pct"),
                ("Купон, %", "coupon"), ("Доходность к погашению, %", "ytm"), ("Доходность после налога, %", "ytm_tax"),
                ("Дюрация, лет", "dur"), ("Погашение", "maturity"), ("Оферта", "call"), ("Следующий купон", "next"),
                ("Сектор", "sector"), ("Риск", "risk"), ("Флоатер", lambda r: "да" if r.get("floating") else ""),
                ("Амортизация", lambda r: "да" if r.get("amort") else "")]
        return [h for h, _ in cols], pick(d["rows"], cols)
    if what == "screener":
        d = screener_payload()
        cols = [("Название", "name"), ("Тикер", "id"), ("ISIN", "isin"), ("Вид", lambda r: "ОФЗ" if r.get("kind") == "ofz" else "Корпоративная"),
                ("Цена, %", "price"), ("Доходность, %", "yield"), ("Дюрация, лет", "dur"), ("Купон, %", "coupon"),
                ("Погашение", "mat"), ("Оферта", "offer"), ("Спред к КБД, п.п.", "spread"), ("Рейтинг", "rating"),
                ("Сектор", "sector"), ("Оборот, ₽", "turn"), ("Сделок", "trades")]
        return [h for h, _ in cols], pick(d["rows"], cols)
    if what == "ops":
        d = build_summary(cfg, acc, "all")
        hdr = ["Дата", "Тип", "Категория", "Название", "Тикер", "Кол-во", "Цена", "Сумма", "Валюта", "Комиссия", "Результат", "Счёт"]
        return hdr, [list(r[:11]) + list(r[12:13]) for r in d["ops"]]
    raise ApiError("Неизвестная таблица для экспорта.", 400)


def _csv_cell(x):
    if isinstance(x, bool):
        return "да" if x else ""
    if isinstance(x, (int, float)):
        return str(round(x, 9)).replace(".", ",")
    return "" if x is None else str(x)


def export_csv(hdr, rows):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(hdr)
    for r in rows:
        w.writerow([_csv_cell(x) for x in r])
    return buf.getvalue().encode("utf-8-sig")


_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_ISO_D = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _xl_col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _xl_esc(s):
    return _XML_BAD.sub("", s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def export_xlsx(hdr, rows, sheet="Данные"):
    """Минимальный корректный .xlsx: числа — числами, даты ГГГГ-ММ-ДД — датами (серийный номер), остальное — строками."""
    epoch = date(1899, 12, 30)
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
           '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/><cols>']
    for i, h in enumerate(hdr):
        out.append('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, max(10, min(40, len(h) + 4))))
    out.append("</cols><sheetData><row r=\"1\">")
    for i, h in enumerate(hdr):
        out.append('<c r="%s1" s="1" t="inlineStr"><is><t>%s</t></is></c>' % (_xl_col(i), _xl_esc(h)))
    out.append("</row>")
    for n, r in enumerate(rows, 2):
        out.append('<row r="%d">' % n)
        for i, x in enumerate(r):
            ref = "%s%d" % (_xl_col(i), n)
            if x is None or x == "":
                continue
            if isinstance(x, bool):
                out.append('<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, "да" if x else "нет"))
            elif isinstance(x, (int, float)):
                if x != x or x in (float("inf"), float("-inf")):
                    continue
                out.append('<c r="%s"><v>%s</v></c>' % (ref, repr(x)))
            else:
                s = str(x)
                if _ISO_D.match(s):
                    try:
                        y, m, d = int(s[:4]), int(s[5:7]), int(s[8:10])
                        out.append('<c r="%s" s="2"><v>%d</v></c>' % (ref, (date(y, m, d) - epoch).days))
                        continue
                    except ValueError:
                        pass
                out.append('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, _xl_esc(s)))
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    sheet_xml = "".join(out)
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook %s '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            '<sheet name="%s" sheetId="1" r:id="rId1"/></sheets></workbook>' % (ns, _xl_esc(sheet)[:31]),
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>',
        "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet %s>'
            '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd"/></numFmts>'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>' % ns,
        "xl/worksheets/sheet1.xml": sheet_xml,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, s in files.items():
            z.writestr(n, s.encode("utf-8"))
    return buf.getvalue()


def api_export(cfg, acc, q, force):
    what, fmt = q.get("what", ""), (q.get("fmt") or "csv").lower()
    if what not in _EXPORT_NAMES:
        raise ApiError("Неизвестная таблица для экспорта.", 400)
    if fmt not in ("csv", "xlsx"):
        raise ApiError("Формат: csv или xlsx.", 400)
    hdr, rows = _ex_table(what, cfg, acc)
    stamp = date.today().isoformat()
    fname = "tinvest_%s_%s.%s" % (_EXPORT_NAMES[what], stamp, fmt)
    hd = {"Content-Disposition": 'attachment; filename="%s"' % fname}
    if fmt == "csv":
        return 200, export_csv(hdr, rows), "text/csv; charset=utf-8", hd
    return 200, export_xlsx(hdr, rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", hd


SECRET_KEYS.add("backup_password")
DEFAULT_CONFIG.setdefault("backup_dir", "")
DEFAULT_CONFIG.setdefault("backup_password", "")
DEFAULT_CONFIG.setdefault("backup_auto", False)
DEFAULT_CONFIG.setdefault("backup_keep", 14)
API_GET["/api/backup/status"] = api_backup_status
API_GET["/api/export"] = api_export
API_POST["/api/backup/settings"] = api_backup_settings
API_POST["/api/backup/run"] = api_backup_run
API_POST["/api/backup/restore"] = api_backup_restore
STARTUP_HOOKS.append(backup_start)
