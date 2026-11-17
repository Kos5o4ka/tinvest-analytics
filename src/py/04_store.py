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

    def wipe_cache(self):
        with self.wlock:
            c = self.conn()
            c.execute("DELETE FROM kv WHERE k NOT LIKE 'imports%'")
            c.execute("DELETE FROM ops WHERE acc NOT LIKE 'imp-%'")
            c.execute("DELETE FROM candles")
            c.commit()

    def purge_expired(self, prefixes=(("bondiz2:", 7 * 86400), ("bopt1:", 7 * 86400), ("disc1:", 7 * 86400),
                                      ("disc_desc1:", 7 * 86400), ("fl_spread1:", 45 * 86400))):
        """Удаляет просроченные записи временного кэша в kv; пользовательские и исторические ключи не затрагивает."""
        now, removed = time.time(), 0
        with self.wlock:
            c = self.conn()
            for pref, ttl in prefixes:
                cur = c.execute("DELETE FROM kv WHERE k LIKE ? AND t < ?", (pref + "%", now - ttl))
                removed += max(cur.rowcount, 0)
            if removed:
                c.commit()
        return removed


STORE = None
_klocks, _klocks_lock = {}, threading.Lock()
_KLOCKS_MAX = 512


def key_lock(key):
    """Блокировка на ключ: одинаковую тяжёлую работу (запросы к API) параллельные потоки выполняют по одному разу."""
    with _klocks_lock:
        lk = _klocks.get(key)
        if lk is None:
            if len(_klocks) >= _KLOCKS_MAX:
                stale = [k for k, v in list(_klocks.items()) if not v.locked()]
                for k in stale[:max(1, len(stale) // 2)]:
                    _klocks.pop(k, None)
            lk = _klocks[key] = threading.Lock()
        return lk


def store():
    global STORE
    if STORE is None:
        STORE = Store(DB_PATH)
    return STORE


