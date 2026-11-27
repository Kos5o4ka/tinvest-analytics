"""Облачная копия и вход в один клик на сервере данных (server/sync.py): версии, конфликты, очередь из бота, TTL и одноразовость. Офлайн."""
import base64
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import sync as SY  # noqa: E402
import tinvest_server as ts  # noqa: E402

K1, K2 = "TIA-AAAA-AAAA-AAAA", "TIA-BBBB-BBBB-BBBB"
SALT = base64.b64encode(b"0123456789abcdef").decode()


def make_db(path, now):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE users(tg_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, created REAL, consent REAL, "
               "banned INTEGER NOT NULL DEFAULT 0, plan TEXT NOT NULL DEFAULT 'free', notify INTEGER NOT NULL DEFAULT 1, "
               "plan_until REAL, trial_used INTEGER NOT NULL DEFAULT 0, pro_kind TEXT)")
    db.execute("CREATE TABLE keys(key_hash TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, "
               "revoked INTEGER NOT NULL DEFAULT 0, last_used REAL)")
    db.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
    db.execute("INSERT INTO users(tg_id, username) VALUES (1,'a'),(2,'b')")
    db.execute("INSERT INTO keys VALUES (?,1,?,?,0,NULL)", (ts.key_hash(K1), now, now + 7 * 86400))
    db.execute("INSERT INTO keys VALUES (?,2,?,?,0,NULL)", (ts.key_hash(K2), now, now + 7 * 86400))
    db.commit()
    db.close()


def body(blob, base, **kw):
    d = {"base_rev": base, "device": "ПК", "sha256": hashlib.sha256(blob).hexdigest(), "salt": SALT,
         "blob": base64.b64encode(blob).decode(), "ack_queue_ids": []}
    d.update(kw)
    return d


class Store(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.p = os.path.join(tempfile.mkdtemp(prefix="tsync_"), "keys.sqlite")
        make_db(self.p, 0)
        self.st = SY.SyncStore(self.p, clock=lambda: self.now[0])

    def test_push_pull_versions(self):
        self.assertFalse(self.st.meta(1)["exists"])
        m = self.st.push(1, body(b"v1", 0))
        self.assertEqual((m["rev"], m["size"], m["salt"]), (1, 2, SALT))
        self.assertEqual(self.st.push(1, body(b"version2", 1))["rev"], 2)
        meta, blob, q = self.st.pull(1)
        self.assertEqual(base64.b64decode(blob), b"version2")
        self.assertEqual((meta["rev"], q), (2, []))
        self.assertFalse(self.st.meta(2)["exists"])      # чужая копия недоступна

    def test_conflict_returns_current(self):
        self.st.push(1, body(b"a", 0))
        self.st.push(1, body(b"b", 1))
        with self.assertRaises(SY.SyncError) as cm:
            self.st.push(1, body(b"c", 1))               # устройство отстало на одну версию
        e = cm.exception
        self.assertEqual((e.code, e.error, e.extra["meta"]["rev"]), (409, "conflict", 2))
        self.assertEqual(base64.b64decode(e.extra["blob"]), b"b")
        with self.assertRaises(SY.SyncError) as cm:
            self.st.push(1, body(b"c", 0))               # создать «с нуля» поверх существующей нельзя
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.st.meta(1)["rev"], 2)

    def test_validation(self):
        for bad in ({"base_rev": "0"}, dict(body(b"x", 0), sha256="0" * 64), dict(body(b"x", 0), salt="!"),
                    dict(body(b"x", 0), blob="@@@"), dict(body(b"x", 0), ack_queue_ids=["1"]), dict(body(b"", 0))):
            with self.assertRaises(SY.SyncError) as cm:
                self.st.push(1, bad)
            self.assertEqual(cm.exception.code, 400, bad)
        big = b"x" * (SY.MAX_BLOB + 1)
        with self.assertRaises(SY.SyncError) as cm:
            self.st.push(1, body(big, 0))
        self.assertEqual(cm.exception.code, 413)
        self.assertFalse(self.st.meta(1)["exists"])

    def test_salt_is_fixed(self):
        self.st.push(1, body(b"a", 0))
        with self.assertRaises(SY.SyncError) as cm:
            self.st.push(1, body(b"b", 1, salt=base64.b64encode(b"fedcba9876543210").decode()))
        self.assertEqual(cm.exception.error, "salt_changed")
        self.assertEqual(self.st.meta(1)["rev"], 1)

    def test_queue_ack_is_atomic_with_push(self):
        i1 = self.st.queue_add(1, {"t": "buy"})
        i2 = self.st.queue_add(1, {"t": "sell"})
        i3 = self.st.queue_add(2, {"t": "buy"})
        meta, _b, q = self.st.pull(1)
        self.assertEqual([x["id"] for x in q], [i1, i2])
        self.st.push(1, body(b"a", 0))
        with self.assertRaises(SY.SyncError):                    # конфликт: очередь не должна потеряться
            self.st.push(1, body(b"b", 0, ack_queue_ids=[i1, i2]))
        self.assertEqual(self.st.meta(1)["queue"], 2)
        self.st.push(1, body(b"b", 1, ack_queue_ids=[i1, i3]))   # чужой id (i3) игнорируется
        self.assertEqual([x["id"] for x in self.st.pull(1)[2]], [i2])
        self.assertEqual(self.st.meta(2)["queue"], 1)

    def test_queue_limit_and_ttl(self):
        for _ in range(SY.QUEUE_MAX):
            self.st.queue_add(1, {"x": 1})
        with self.assertRaises(SY.SyncError):
            self.st.queue_add(1, {"x": 1})
        self.now[0] += SY.QUEUE_TTL + 1
        self.assertEqual(self.st.pull(1)[2], [])

    def test_delete(self):
        self.st.push(1, body(b"a", 0))
        self.st.queue_add(1, {"x": 1})
        self.assertTrue(self.st.delete(1))
        self.assertEqual(self.st.meta(1), {"exists": False, "rev": 0, "queue": 0})
        self.assertFalse(self.st.delete(1))

    def test_push_rate_limit(self):
        for _ in range(SY.PUSH_PER_HOUR):
            self.assertTrue(self.st.rate_ok(1))
        self.assertFalse(self.st.rate_ok(1))
        self.assertTrue(self.st.rate_ok(2))
        self.now[0] += 3601
        self.assertTrue(self.st.rate_ok(1))


class AuthLink(unittest.TestCase):
    NONCE = "n" * 22
    VER = "v" * 40

    def setUp(self):
        self.now = [5000.0]
        self.p = os.path.join(tempfile.mkdtemp(prefix="tauth_"), "keys.sqlite")
        make_db(self.p, 0)
        self.st = SY.SyncStore(self.p, clock=lambda: self.now[0])
        self.ch = hashlib.sha256(self.VER.encode()).hexdigest()

    def approve(self, key="TIA-XXXX-XXXX-XXXX"):
        self.st.conn().execute("UPDATE auth_links SET state='approved', tg_id=1, key_plain=? WHERE nonce_hash=?",
                               (key, self.st._nh(self.NONCE)))

    def test_flow_and_single_use(self):
        self.st.auth_start(self.NONCE, self.ch)
        self.assertEqual(self.st.auth_poll(self.NONCE, self.VER), {"state": "pending"})
        self.approve()
        r = self.st.auth_poll(self.NONCE, self.VER)
        self.assertEqual(r, {"state": "approved", "key": "TIA-XXXX-XXXX-XXXX"})
        self.assertEqual(self.st.auth_poll(self.NONCE, self.VER), {"state": "expired"})       # повторно ключ не выдаётся
        row = self.st.conn().execute("SELECT key_plain FROM auth_links").fetchone()
        self.assertTrue(row is None or row[0] is None)

    def test_ttl(self):
        self.st.auth_start(self.NONCE, self.ch)
        self.approve()
        self.now[0] += SY.AUTH_TTL + 1
        self.assertEqual(self.st.auth_poll(self.NONCE, self.VER), {"state": "expired"})
        self.assertEqual(self.st.conn().execute("SELECT COUNT(*) FROM auth_links").fetchone()[0], 0)

    def test_wrong_verifier_never_gets_key_and_burns_link(self):
        self.st.auth_start(self.NONCE, self.ch)
        self.approve()
        for _ in range(5):
            with self.assertRaises(SY.SyncError) as cm:
                self.st.auth_poll(self.NONCE, "x" * 40)
            self.assertEqual(cm.exception.code, 403)
        self.assertEqual(self.st.auth_poll(self.NONCE, self.VER), {"state": "expired"})       # ссылка погашена подбором

    def test_validation_and_replay_of_nonce(self):
        for n, c in (("short", self.ch), (self.NONCE, "zz"), ("a" * 60, self.ch), ("не-ascii-" + "n" * 20, self.ch)):
            with self.assertRaises(SY.SyncError):
                self.st.auth_start(n, c)
        self.st.auth_start(self.NONCE, self.ch)
        with self.assertRaises(SY.SyncError) as cm:
            self.st.auth_start(self.NONCE, self.ch)
        self.assertEqual(cm.exception.code, 409)
        self.assertEqual(self.st.auth_poll("u" * 22, self.VER), {"state": "expired"})

    def test_nonce_stored_only_hashed(self):
        self.st.auth_start(self.NONCE, self.ch)
        rows = self.st.conn().execute("SELECT * FROM auth_links").fetchall()
        self.assertNotIn(self.NONCE, json.dumps(rows))
        self.assertNotIn(self.VER, json.dumps(rows))

    def test_rate_limit_per_ip(self):
        for _ in range(SY.AUTH_START_PER_HOUR):
            self.assertTrue(self.st.auth_rate_ok("1.2.3.4"))
        self.assertFalse(self.st.auth_rate_ok("1.2.3.4"))
        self.assertTrue(self.st.auth_rate_ok("5.6.7.8"))

    def test_poll_rate_limits_per_ip_and_per_nonce(self):
        self.st.auth_start(self.NONCE, self.ch)
        for _ in range(SY.AUTH_POLL_PER_NONCE):
            self.st.auth_poll(self.NONCE, self.VER, "1.1.1.1")
        with self.assertRaises(SY.SyncError) as cm:
            self.st.auth_poll(self.NONCE, self.VER, "1.1.1.1")
        self.assertEqual(cm.exception.code, 429)
        for i in range(SY.AUTH_POLL_PER_HOUR):                       # другой адрес и другие ссылки: свой счёт на адрес
            self.assertEqual(self.st.auth_poll("%022d" % i, self.VER, "2.2.2.2"), {"state": "expired"})
        with self.assertRaises(SY.SyncError) as cm:
            self.st.auth_poll("z" * 22, self.VER, "2.2.2.2")
        self.assertEqual(cm.exception.code, 429)
        self.now[0] += 3601
        self.assertEqual(self.st.auth_poll("z" * 22, self.VER, "2.2.2.2"), {"state": "expired"})

    def test_poll_without_nonce_does_not_take_write_lock(self):
        self.st.conn()
        other = sqlite3.connect(self.p, isolation_level=None)
        other.execute("BEGIN IMMEDIATE")                              # кто-то держит блокировку записи
        try:
            t0 = time.time()
            self.assertEqual(self.st.auth_poll("m" * 22, self.VER), {"state": "expired"})
            self.assertLess(time.time() - t0, 1.0)
        finally:
            other.execute("ROLLBACK")
            other.close()

    def test_lone_surrogate_verifier_is_bad_request(self):
        with self.assertRaises(SY.SyncError) as cm:
            self.st.auth_poll(self.NONCE, "\ud800" * 20)
        self.assertEqual(cm.exception.code, 400)


class Http(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="tsync_http_")
        self.dbp = os.path.join(tmp, "keys.sqlite")
        make_db(self.dbp, time.time())
        self.app = ts.DataServer(os.path.join(tmp, "data"), keys_db=self.dbp, md=False)
        self.srv = ts.make_http_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def call(self, path, data=None, key=K1, method=None):
        hd = {"Content-Type": "application/json"}
        if key:
            hd["X-Client-Key"] = key
        req = urllib.request.Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers=hd,
                                     method=method or ("GET" if data is None else "POST"))
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_requires_key(self):
        self.assertEqual(self.call("/v1/sync/meta", key="")[0], 401)
        self.assertEqual(self.call("/v1/sync/meta", key="TIA-ZZZZ-ZZZZ-ZZZZ")[0], 401)
        self.assertEqual(self.call("/v1/sync/nope")[0], 404)
        self.assertEqual(self.call("/v1/sync/push")[0], 405)

    def test_roundtrip_conflict_delete(self):
        self.assertEqual(self.call("/v1/sync/meta")[1]["exists"], False)
        c, j = self.call("/v1/sync/push", body(b"\x00\x01cipher", 0))
        self.assertEqual((c, j["rev"]), (200, 1))
        c, j = self.call("/v1/sync/pull", key=K1)
        self.assertEqual(base64.b64decode(j["blob"]), b"\x00\x01cipher")
        c, j = self.call("/v1/sync/push", body(b"zzz", 0))
        self.assertEqual((c, j["error"], j["meta"]["rev"]), (409, "conflict", 1))
        self.assertEqual(base64.b64decode(j["blob"]), b"\x00\x01cipher")
        self.assertEqual(self.call("/v1/sync/pull", key=K2)[1]["exists"], False)
        self.assertEqual(self.call("/v1/sync/delete", {})[1], {"ok": True, "deleted": True})
        self.assertEqual(self.call("/v1/sync/meta")[1]["exists"], False)

    def test_large_push_within_limit(self):
        blob = os.urandom(1500 * 1024)                 # больше прежнего лимита 1 МБ на тело запроса
        c, j = self.call("/v1/sync/push", body(blob, 0))
        self.assertEqual((c, j["size"]), (200, len(blob)))

    def test_auth_link_http(self):
        n, v = "h" * 24, "q" * 40
        ch = hashlib.sha256(v.encode()).hexdigest()
        self.assertEqual(self.call("/v1/auth/start", {"nonce": n, "challenge": ch}, key="")[0], 200)
        c, j = self.call("/v1/auth/poll", {"nonce": n, "verifier": v}, key="")
        self.assertEqual((c, j["state"]), (200, "pending"))
        c, j = self.call("/v1/auth/poll", {"nonce": n, "verifier": "w" * 40}, key="")
        self.assertEqual((c, j["error"]), (403, "bad_verifier"))
        self.assertEqual(self.call("/v1/auth/start", {"nonce": "x"}, key="")[0], 400)
        req = urllib.request.Request(self.url + "/v1/auth/poll", data=json.dumps({"nonce": n, "verifier": "\ud800" * 20}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
