# ═══════════════════════════════ Данные на компьютере (раздел «Настройки») ═══════════════════════════════
# Размер и состав папки данных, открытие папки, очистка кэша и полное удаление данных.
# Все пути строятся только от APP_DIR; символические ссылки никогда не разворачиваются (удаляется сама ссылка).

LD_DB_NAMES = ("data.db", "data.db-wal", "data.db-shm")


def _ld_size(path):
    """Размер файла или папки в байтах без перехода по символическим ссылкам."""
    try:
        st = os.lstat(path)
    except OSError:
        return 0
    if not os.path.isdir(path) or os.path.islink(path):
        return st.st_size
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for n in files + [d for d in dirs if os.path.islink(os.path.join(root, d))]:
            try:
                total += os.lstat(os.path.join(root, n)).st_size
            except OSError:
                pass
    return total


def local_data_info(app_dir=None):
    """Состав папки данных: общий размер и разбивка по частям."""
    base = app_dir or APP_DIR
    names = set()
    try:
        names = set(os.listdir(base))
    except OSError:
        pass
    parts = [("db", "data.db", "База операций и кэш", [n for n in names if n == "data.db" or n.startswith("data.db-")]),
             ("cache", "cache/", "Кэш", ["cache"]),
             ("logos", "logos/", "Логотипы", ["logos"]),
             ("app", "app/", "Скачанная программа", ["app"]),
             ("window", "window/", "Данные окна приложения", ["window", "window.json"]),
             ("config", "config.json", "Настройки, токен и ключ", ["config.json"])]
    used, rows = set(), []
    for key, name, title, files in parts:
        used.update(files)
        rows.append({"key": key, "name": name, "title": title,
                     "bytes": sum(_ld_size(os.path.join(base, f)) for f in files if f in names)})
    rest = sorted(names - used)
    if rest:
        rows.append({"key": "other", "name": "прочее", "title": "Прочие файлы",
                     "bytes": sum(_ld_size(os.path.join(base, f)) for f in rest)})
    return {"dir": base, "total": sum(r["bytes"] for r in rows), "parts": rows, "windows": platform.system() == "Windows"}


def _ld_remove(path):
    """Удаляет файл, ссылку или папку целиком; ссылки не разворачивает."""
    try:
        if os.path.islink(path) or not os.path.isdir(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _ld_empty_dir(path):
    """Очищает содержимое папки (саму папку оставляет)."""
    try:
        if os.path.islink(path) or not os.path.isdir(path):
            return
        for n in os.listdir(path):
            _ld_remove(os.path.join(path, n))
    except OSError:
        pass


def _ld_protected_keys():
    """Ключи таблицы kv с вашими данными или накопленной историей: очистка кэша их не трогает."""
    names = ("WATCH_KEY", "NOTES_KEY", "TG_SENT_KEY", "TG_STATE_KEY", "TAX_SETTINGS_KEY", "SIG_HIST_KEY", "RT_LOG_KEY",
             "MKT_HIST_KEY", "MKT_HIST2_KEY", "MON_SNAP_KEY")
    keys = {"backup_status"}
    for n in names:
        v = globals().get(n)
        if isinstance(v, str):
            keys.add(v)
    return keys


def clear_local_cache(app_dir=None):
    """Удаляет кэш (cache/, logos/, кэш-записи и свечи в data.db). Операции, настройки, список наблюдения и заметки остаются."""
    base = app_dir or APP_DIR
    before = local_data_info(base)["total"]
    st = store()
    keys = sorted(_ld_protected_keys())
    with st.wlock:
        c = st.conn()
        c.execute("DELETE FROM kv WHERE k NOT LIKE 'imports%%' AND k NOT IN (%s)" % ",".join("?" * len(keys)), keys)
        c.execute("DELETE FROM candles")
        c.commit()
        try:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.execute("VACUUM")
        except sqlite3.Error:
            pass
    for d in ("cache", "logos"):
        _ld_empty_dir(os.path.join(base, d))
    mem_clear()
    after = local_data_info(base)["total"]
    return {"ok": True, "freed": max(0, before - after), "info": local_data_info(base)}


def delete_all_local_data(app_dir=None):
    """Удаляет настройки (токен, ключ), базу, кэш и логотипы. Папка app/ остаётся, чтобы программа продолжала работать."""
    global STORE
    base = app_dir or APP_DIR
    if STORE is not None and os.path.abspath(base) == os.path.abspath(APP_DIR):
        try:
            with STORE.wlock:
                c = STORE.conn()
                for t in ("kv", "ops", "candles", "snaps"):
                    c.execute("DELETE FROM " + t)
                c.commit()
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                c.close()
                STORE.local.c = None
        except sqlite3.Error:
            pass
        STORE = None
    for n in LD_DB_NAMES + ("config.json", "window.json", "data.db.before-restore"):
        _ld_remove(os.path.join(base, n))
    for n in ("cache", "logos", "window"):
        _ld_remove(os.path.join(base, n))
    try:
        for n in os.listdir(base):
            if n.startswith("backup.") and n.endswith(".tmp"):
                _ld_remove(os.path.join(base, n))
    except OSError:
        pass
    mem_clear()
    ds_reset()
    return {"ok": True, "info": local_data_info(base)}


def open_data_dir():
    """Открывает папку данных в Finder / Проводнике / файловом менеджере. Путь не принимается извне."""
    os.makedirs(APP_DIR, exist_ok=True)
    sysname = platform.system()
    if sysname == "Windows":
        os.startfile(APP_DIR)           # noqa: S606  (только на Windows)
    elif sysname == "Darwin":
        subprocess.Popen(["open", APP_DIR])
    else:
        subprocess.Popen(["xdg-open", APP_DIR])


def ld_info_get(cfg, acc, q, f):
    return local_data_info()


def ld_open_post(cfg, body):
    try:
        open_data_dir()
    except (OSError, AttributeError) as e:
        raise ApiError("Не удалось открыть папку: %s. Путь: %s" % (e, APP_DIR), 500)
    return {"ok": True}


def ld_clear_post(cfg, body):
    return clear_local_cache()


def ld_wipe_post(cfg, body):
    if body.get("confirm") != "delete-all":
        raise ApiError("Нужно подтверждение удаления.", 400)
    return delete_all_local_data()


API_GET["/api/localdata"] = ld_info_get
API_POST["/api/localdata/open"] = ld_open_post
API_POST["/api/localdata/clear"] = ld_clear_post
API_POST["/api/localdata/wipe"] = ld_wipe_post
