# ═══════════════════════════════ настройки ═══════════════════════════════

_cfg_lock = threading.Lock()


def _private_write(path, data_bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, threading.get_ident())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data_bytes)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
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
            z.writestr("README.txt", "Резервная копия T-Invest Analytics. Токены и пароли в копию не входят.\n"
                       "Восстановление: закройте программу и положите data.db в папку данных (%s).\n" % APP_DIR)
        return buf.getvalue()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def save_config(cfg):
    with _cfg_lock:
        _private_write(CONFIG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"))


def token_key(cfg):
    return ("sb_" if cfg["sandbox"] else "pr_") + hashlib.sha256(cfg["token"].encode()).hexdigest()[:16]


