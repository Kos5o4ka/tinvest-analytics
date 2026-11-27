# ═══════════════════════════════ настройки ═══════════════════════════════

_cfg_lock = threading.Lock()


def _private_write(path, data_bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, threading.get_ident())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data_bytes)
    os.replace(tmp, path)


def _dpapi_win32(protect, raw):
    """Вызов Windows DPAPI (CryptProtectData / CryptUnprotectData) через ctypes. Возвращает bytes или None."""
    import ctypes
    from ctypes import wintypes

    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(raw, len(raw))
    in_b = _BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    out_b = _BLOB()
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(in_b), "TAnalytic", None, None, None, 0x01, ctypes.byref(out_b))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(in_b), None, None, None, None, 0x01, ctypes.byref(out_b))
    if not ok:
        return None
    try:
        return ctypes.string_at(out_b.pbData, out_b.cbData)
    finally:
        kernel32.LocalFree(out_b.pbData)


def _dpapi_protect(text):
    """На Windows шифрует секрет через DPAPI текущего пользователя; иначе или при сбое возвращает исходный текст."""
    if not text or platform.system() != "Windows":
        return text
    s = str(text)
    if s.startswith("dpapi:"):
        return s
    try:
        enc = _dpapi_win32(True, s.encode("utf-8"))
        if enc:
            return "dpapi:" + base64.b64encode(enc).decode("ascii")
    except Exception:  # noqa: BLE001
        pass
    return s


def _dpapi_unprotect(val):
    """Расшифровывает строку вида 'dpapi:...' на Windows; на других ОС или при ошибке возвращает ''."""
    if not isinstance(val, str) or not val.startswith("dpapi:"):
        return val
    if platform.system() != "Windows":
        return ""
    try:
        raw = base64.b64decode(val[6:].encode("ascii"))
        dec = _dpapi_win32(False, raw)
        return dec.decode("utf-8") if dec is not None else ""
    except Exception:  # noqa: BLE001
        return ""


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as f:   # utf-8-sig: Блокнот Windows пишет BOM
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    for k in ("token", "data_key", "sync_master"):
        if isinstance(cfg.get(k), str) and cfg[k].startswith("dpapi:"):
            cfg[k] = _dpapi_unprotect(cfg[k])
    if os.environ.get("TINVEST_TOKEN"):
        cfg["token"] = os.environ["TINVEST_TOKEN"]
    return cfg


def make_backup():
    """Zip с согласованной копией базы и настройками БЕЗ токена и других секретов (SECRET_KEYS)."""
    tmp = os.path.join(APP_DIR, "backup.%d.tmp" % threading.get_ident())
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        cfg = {k: v for k, v in load_config().items() if k not in SECRET_KEYS}     # токен и прочие секреты не входят
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "data.db")
            z.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=2))
            z.writestr("README.txt", "Резервная копия TAnalytic. Токены и пароли в копию не входят.\n"
                       "Восстановление: закройте программу и положите data.db в папку данных (%s).\n" % APP_DIR)
        return buf.getvalue()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def save_config(cfg):
    out = dict(cfg)
    env_tok = os.environ.get("TINVEST_TOKEN")      # токен из окружения на диск не пишем: оставляем сохранённый там
    with _cfg_lock:
        if env_tok and out.get("token") == env_tok:
            disk_tok = ""
            try:
                with open(CONFIG_PATH, encoding="utf-8-sig") as f:   # utf-8-sig: Блокнот Windows пишет BOM
                    disk_tok = (json.load(f) or {}).get("token", "")
            except (OSError, ValueError, AttributeError):
                pass
            out["token"] = disk_tok
        if (out.get("token") or "").strip():
            try:
                demo_remove()  # реальный токен заменяет демо-портфель
            except Exception:  # noqa: BLE001
                pass
        for k in ("token", "data_key", "sync_master"):
            if out.get(k):
                out[k] = _dpapi_protect(str(out[k]))
        _private_write(CONFIG_PATH, json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8"))


def token_key(cfg):
    return ("sb_" if cfg["sandbox"] else "pr_") + hashlib.sha256(cfg["token"].encode()).hexdigest()[:16]


