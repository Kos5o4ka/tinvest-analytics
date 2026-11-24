# ═══════════════════════════════ локальная база ═══════════════════════════════

def apply_pending_restore(path):
    """Восстановление из резервной копии: подготовленная база (data.db.restore-pending) подменяет текущую при открытии.
    Прежняя база сохраняется рядом как data.db.before-restore."""
    pend = path + ".restore-pending"
    if not os.path.exists(pend):
        return False
    try:
        if os.path.exists(path):
            src = sqlite3.connect(path)
            dst = sqlite3.connect(path + ".before-restore")
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
        for ext in ("-wal", "-shm"):
            try:
                os.remove(path + ext)
            except OSError:
                pass
        os.replace(pend, path)
        return True
    except (OSError, sqlite3.Error):
        return False


class Store:
    """SQLite в ~/.tinvest_analytics/data.db: операции, свечи, справочники, импорт."""

    def __init__(self, path):
        self.path = path
        self.local = threading.local()
        self.wlock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        apply_pending_restore(path)
        if not os.path.exists(path):
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
        c = self.conn()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT, t REAL);
            CREATE TABLE IF NOT EXISTS ops(acc TEXT, k TEXT, d TEXT, v TEXT, PRIMARY KEY(acc, k));
            CREATE INDEX IF NOT EXISTS ops_acc_d ON ops(acc, d);
            CREATE TABLE IF NOT EXISTS candles(uid TEXT, d TEXT, c REAL, PRIMARY KEY(uid, d));
            CREATE TABLE IF NOT EXISTS snaps(acc TEXT, d TEXT, total REAL, PRIMARY KEY(acc, d));
        """)
        c.commit()

    def conn(self):
        c = getattr(self.local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=60, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self.local.c = c
        return c

    def write(self, sql, rows=None, many=False):
        with self.wlock:
            c = self.conn()
            if many:
                c.executemany(sql, rows)
            else:
                c.execute(sql, rows or ())
            c.commit()

    def get(self, k, ttl=None):
        r = self.conn().execute("SELECT v, t FROM kv WHERE k=?", (k,)).fetchone()
        if not r or (ttl is not None and time.time() - r[1] > ttl):
            return None
        return json.loads(r[0])

    def put(self, k, v):
        self.write("INSERT OR REPLACE INTO kv(k, v, t) VALUES(?,?,?)", (k, json.dumps(v, ensure_ascii=False), time.time()))

    def put_many(self, items):
        now = time.time()
        self.write("INSERT OR REPLACE INTO kv(k, v, t) VALUES(?,?,?)",
                   [(k, json.dumps(v, ensure_ascii=False), now) for k, v in items], many=True)

    def delete_prefix(self, prefix):
        self.write("DELETE FROM kv WHERE k LIKE ?", (prefix + "%",))

    def ops(self, acc):
        return [json.loads(v) for (v,) in self.conn().execute("SELECT v FROM ops WHERE acc=? ORDER BY d, k", (acc,))]

    def ops_put(self, acc, ops):
        self.write("INSERT OR REPLACE INTO ops(acc, k, d, v) VALUES(?,?,?,?)",
                   [(acc, op_key(o), o.get("date") or "", json.dumps(o, ensure_ascii=False)) for o in ops], many=True)

    def ops_clear(self, acc):
        self.write("DELETE FROM ops WHERE acc=?", (acc,))

    def candles(self, uid):
        return self.conn().execute("SELECT d, c FROM candles WHERE uid=? ORDER BY d", (uid,)).fetchall()

    def candles_put(self, uid, rows):
        if rows:
            self.write("INSERT OR REPLACE INTO candles(uid, d, c) VALUES(?,?,?)", [(uid, d, c) for d, c in rows], many=True)

    def snap(self, acc, total):
        self.write("INSERT OR REPLACE INTO snaps(acc, d, total) VALUES(?,?,?)", (acc, date.today().isoformat(), total))

    def kv_gc(self, rules=None, now=None, vacuum=True):
        """Удаляет устаревшие строки чистых кэшей kv (по явному списку префиксов и возрасту), затем сжимает журнал WAL.
        Пользовательские данные (импорты, операции, настройки, наблюдение, журнал, рейтинги, исторические ряды) не трогает.
        Возвращает {"deleted": n, "vacuum": bool}."""
        now = time.time() if now is None else now
        n = 0
        with self.wlock:
            c = self.conn()
            for pre, age in (rules or KV_GC_RULES):
                cur = c.execute("DELETE FROM kv WHERE substr(k, 1, ?) = ? AND t < ?", (len(pre), pre, now - age))
                n += max(cur.rowcount or 0, 0)
            c.commit()
        try:
            self.conn().execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        except sqlite3.Error:
            pass
        vac = False
        if vacuum and n:
            try:      # VACUUM только если свободных страниц много, а база небольшая: он переписывает файл целиком
                c = self.conn()
                free = c.execute("PRAGMA freelist_count").fetchone()[0]
                pages = c.execute("PRAGMA page_count").fetchone()[0]
                size = pages * c.execute("PRAGMA page_size").fetchone()[0]
                if pages and free / float(pages) > 0.3 and size < KV_GC_VACUUM_MAX:
                    with self.wlock:
                        c.execute("VACUUM")
                    vac = True
            except sqlite3.Error:
                pass
        return {"deleted": n, "vacuum": vac}

    def wipe_cache(self, keep_keys=None):
        fn = globals().get("_ld_protected_keys")
        keys = sorted(keep_keys if keep_keys is not None else (fn() if fn else ()))
        with self.wlock:
            c = self.conn()
            if keys:
                c.execute("DELETE FROM kv WHERE k NOT LIKE 'imports%%' AND k NOT IN (%s)" % ",".join("?" * len(keys)), keys)
            else:
                c.execute("DELETE FROM kv WHERE k NOT LIKE 'imports%'")
            c.execute("DELETE FROM ops WHERE acc NOT LIKE 'imp-%'")
            c.execute("DELETE FROM candles")
            c.commit()


# Чистые кэши, которые без потерь перезапрашиваются из сети: (префикс ключа, максимальный возраст строки, с).
# Сюда НЕ входят: imports*, операции, настройки, наблюдение, журнал, рейтинги, снимки размещений, исторические ряды
# (stk_hist_v1_, fng_cl1:, kbdc1:, pv_*, prih1:, cbr: — курсы для налогов), inst:/bond:/cpn: (нужны без сети).
KV_GC_RULES = (
    ("stk_c_v1_", 3 * DAY),           # графики акций: ключ содержит дату, прошлые дни больше не читаются
    ("mqquote:", 7 * DAY), ("mqmap:", 60 * DAY),
    ("bondmiss:", 7 * DAY), ("bondmiss404:", 7 * DAY), ("instmiss:", 7 * DAY),
    ("bondiz2:", 60 * DAY), ("bopt1:", 60 * DAY), ("bondhist_v1_", 60 * DAY), ("iss_card_v3_", 60 * DAY),
    ("mon_desc_v1_", 60 * DAY), ("disc_desc2:", 60 * DAY), ("find:", 60 * DAY), ("div2:", 60 * DAY),
    ("res:", 60 * DAY),               # результаты расчётов по счетам (в т.ч. старых токенов) — пересчитываются
)
KV_GC_KEY, KV_GC_DELAY, KV_GC_VACUUM_MAX = "kv_gc_v1", 90, 512 * 1024 * 1024


def kv_gc_start(delay=KV_GC_DELAY):
    """Не чаще раза в сутки, в фоне и с задержкой после запуска (чтобы не мешать прогреву): kv_gc()."""
    def job():
        try:
            time.sleep(delay)
            st = store()
            if st.get(KV_GC_KEY, ttl=DAY) is not None:
                return
            st.put(KV_GC_KEY, {"at": time.time()})
            st.put(KV_GC_KEY, dict(st.kv_gc(), at=time.time()))
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=job, daemon=True, name="kv-gc").start()


STARTUP_HOOKS.append(kv_gc_start)

STORE = None
_klocks, _klocks_lock = {}, threading.Lock()


def key_lock(key):
    """Блокировка на ключ: одинаковую тяжёлую работу (запросы к API) параллельные потоки выполняют по одному разу."""
    with _klocks_lock:
        if len(_klocks) > 512:
            for k in [k for k, v in _klocks.items() if k != key and not v.locked()]:
                _klocks.pop(k, None)
        lk = _klocks.get(key)
        if lk is None:
            lk = _klocks[key] = threading.Lock()
        return lk


def store():
    global STORE
    if STORE is None:
        STORE = Store(DB_PATH)
    return STORE


