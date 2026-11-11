"""Сервер данных: allowlist, кэш и TTL, stale при ошибке, single-flight, ключ, POST, бинарные тела, 5xx. Офлайн."""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import tinvest_server as ts  # noqa: E402

BIN = bytes(range(256)) * 4


class Upstream:
    def __init__(self):
        self.hits = 0
        self.delay = 0.0
        self.fail = False
        self.posts = []
        up = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, body, ct="text/plain"):
                self.send_response(code)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Set-Cookie", "svc=1; Path=/")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                up.hits += 1
                time.sleep(up.delay)
                if up.fail or self.path == "/boom":
                    return self._reply(503, b"down")
                if self.path == "/nf":
                    return self._reply(404, b"nope")
                if self.path == "/bin":
                    return self._reply(200, BIN, "application/pdf")
                self._reply(200, ("hit%d" % up.hits).encode())

            def do_POST(self):
                up.hits += 1
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n)
                up.posts.append((self.path, body, self.headers.get("Content-Type")))
                self._reply(200, b"echo:" + body)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.host = "127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def url(self, path):
        return "http://%s%s" % (self.host, path)

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class Fx:
    """Поднимает фейковый источник и сервер данных на случайных портах."""

    def __init__(self, key="", clock=None, keys_db=""):
        self.up = Upstream()
        self.tmp = tempfile.mkdtemp(prefix="tsrv_")
        self.now = [1_000_000.0]
        rules = [(self.up.host, ".*", 100, 100)]
        self.app = ts.DataServer(self.tmp, key=key, clock=clock or (lambda: self.now[0]), extra_allow=[self.up.host],
                                 rates={"*": 1000}, rules=rules, keys_db=keys_db, bot="@testbot")
        self.http = ts.make_http_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.http.server_address[1]

    def call(self, target, data=None, headers=None, path="/v1/fetch"):
        url = self.base + path + ("?url=" + urllib.parse.quote(target, safe="") if target else "")
        req = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.up.close()
        self.app.cache.db.close()


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.f = Fx()

    def tearDown(self):
        self.f.close()

    def test_allowlist_rejects(self):
        for u in ("http://evil.example.com/x", "https://invest-public-api.tbank.ru/rest", "https://api.telegram.org/bot1/x",
                  "ftp://iss.moex.com/x", "file:///etc/passwd", "https://iss.moex.com@evil.example.com/", "https://t.me/someone"):
            self.assertEqual(self.f.call(u)[0], 403, u)
        self.assertEqual(self.f.up.hits, 0)
        self.assertTrue(self.f.app.url_allowed("https://iss.moex.com/iss/x.json"))
        self.assertTrue(self.f.app.url_allowed("https://t.me/s/issuerRatings"))

    def test_hit_and_ttl_expiry(self):
        u = self.f.up.url("/a")
        st, body, h = self.f.call(u)
        self.assertEqual((st, body, h["X-Cache"]), (200, b"hit1", "miss"))
        st, body, h = self.f.call(u)
        self.assertEqual((body, h["X-Cache"]), (b"hit1", "hit"))
        self.f.now[0] += 40
        self.assertEqual(self.f.call(u)[2]["X-Age"], "40")
        self.f.now[0] += 70                                  # TTL 100 истёк
        st, body, h = self.f.call(u)
        self.assertEqual((body, h["X-Cache"]), (b"hit2", "miss"))
        self.assertEqual(self.f.up.hits, 2)

    def test_stale_on_error(self):
        u = self.f.up.url("/a")
        self.f.call(u)
        self.f.now[0] += 500
        self.f.up.fail = True
        st, body, h = self.f.call(u)
        self.assertEqual((st, body, h["X-Cache"]), (200, b"hit1", "stale"))

    def test_5xx_not_cached(self):
        st, body, h = self.f.call(self.f.up.url("/boom"))
        self.assertEqual(st, 502)
        self.assertEqual(h["X-Upstream-Error"], "1")
        self.assertIsNone(h["X-Cache"])
        self.f.call(self.f.up.url("/boom"))
        self.assertEqual(self.f.up.hits, 2)
        self.assertEqual(self.f.app.cache.count(), 0)

    def test_404_cached_and_relayed(self):
        u = self.f.up.url("/nf")
        st, body, h = self.f.call(u)
        self.assertEqual((st, body, h["X-Cache"]), (404, b"nope", "miss"))
        self.assertEqual(self.f.call(u)[2]["X-Cache"], "hit")

    def test_single_flight(self):
        self.f.up.delay = 0.4
        u = self.f.up.url("/slow")
        out = []
        ths = [threading.Thread(target=lambda: out.append(self.f.call(u))) for _ in range(8)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        self.assertEqual(self.f.up.hits, 1)
        self.assertEqual({o[1] for o in out}, {b"hit1"})
        self.assertEqual(len(out), 8)

    def test_binary_preserved(self):
        st, body, h = self.f.call(self.f.up.url("/bin"))
        self.assertEqual((st, body, h["Content-Type"]), (200, BIN, "application/pdf"))
        self.assertEqual(self.f.call(self.f.up.url("/bin"))[1], BIN)

    def test_post_passthrough_and_cache_key(self):
        u = self.f.up.url("/search")
        hd = {"Content-Type": "application/x-www-form-urlencoded"}
        st, body, h = self.f.call(u, b"q=1", hd)
        self.assertEqual((st, body, h["X-Cache"]), (200, b"echo:q=1", "miss"))
        self.assertEqual(self.f.up.posts[0][2], "application/x-www-form-urlencoded")
        self.assertEqual(self.f.call(u, b"q=1", hd)[2]["X-Cache"], "hit")
        self.assertEqual(self.f.call(u, b"q=2", hd)[1], b"echo:q=2")
        self.assertEqual(self.f.up.hits, 2)

    def test_post_not_cached_without_rule(self):
        self.f.close()
        self.f = Fx()
        self.f.app.rules = [(self.f.up.host, ts.re.compile(r".*"), 100, None)]
        u = self.f.up.url("/p")
        self.f.call(u, b"x", {"Content-Type": "text/plain"})
        self.f.call(u, b"x", {"Content-Type": "text/plain"})
        self.assertEqual(self.f.up.hits, 2)

    def test_health_and_stats(self):
        st, body, _ = self.f.call(None, path="/v1/health")
        import json
        j = json.loads(body)
        self.assertTrue(j["ok"])
        self.assertEqual(j["version"], ts.VERSION)
        u = self.f.up.url("/a")
        self.f.call(u)
        self.f.call(u)
        s = json.loads(self.f.call(None, path="/v1/stats")[1])
        self.assertEqual((s["hit"], s["miss"]), (1, 1))
        self.assertEqual(s["hit_ratio"], 0.5)
        self.assertIn(self.f.up.host, s["hosts"])

    def test_cookie_get_not_cached(self):
        u = self.f.up.url("/a")
        self.f.call(u, headers={"X-Up-Cookie": "a=b"})
        self.f.call(u, headers={"X-Up-Cookie": "a=b"})
        self.assertEqual(self.f.up.hits, 2)

    def test_set_cookie_dropped_and_cached_for_ordinary_hosts(self):
        u = self.f.up.url("/a")
        st, body, h = self.f.call(u)
        self.assertIsNone(h["X-Set-Cookie"])
        self.assertEqual(self.f.call(u)[2]["X-Cache"], "hit")

    def test_session_host_set_cookie_relayed_not_cached(self):
        self.f.close()
        self.f = Fx()
        ts.SESSION_HOSTS.add(self.f.up.host)
        self.addCleanup(ts.SESSION_HOSTS.discard, self.f.up.host)
        u = self.f.up.url("/a")
        self.assertEqual(self.f.call(u)[2]["X-Set-Cookie"], "svc=1; Path=/")
        self.f.call(u)
        self.assertEqual(self.f.up.hits, 2)

    def test_eviction(self):
        app = self.f.app
        app.cache.max_bytes = 3000
        for i in range(10):
            self.f.call(self.f.up.url("/bin?i=%d" % i)) if False else app.cache.put("k%d" % i, 200, "x", b"z" * 1000, float(i), 1e12)
        self.assertLessEqual(app.cache.total, 3000)
        self.assertIsNone(app.cache.get("k0", 100.0))
        self.assertIsNotNone(app.cache.get("k9", 100.0))

    def test_rules_ttl(self):
        a = ts.DataServer(tempfile.mkdtemp(), clock=lambda: 0)
        mon = datetime(2026, 11, 9, 12, 0, tzinfo=timezone(timedelta(hours=3))).timestamp()          # понедельник 12:00 МСК
        self.assertEqual(a.ttl_for("iss.moex.com", "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQCB/securities.json", "GET", mon), 300)
        self.assertEqual(a.ttl_for("iss.moex.com", "https://iss.moex.com/iss/engines/stock/zcyc.json?x=1", "GET", mon), 3600)
        self.assertEqual(a.ttl_for("bo.nalog.gov.ru", "https://bo.nalog.gov.ru/nbo/x", "GET", mon), 7 * 86400)
        self.assertIsNone(a.ttl_for("iss.moex.com", "https://iss.moex.com/iss/x", "POST", mon))
        self.assertEqual(a.ttl_for("raexpert.ru", "https://raexpert.ru/search/", "POST", mon), 12 * 3600)


class KeyTests(unittest.TestCase):
    def test_key_required(self):
        f = Fx(key="s3cret")
        try:
            u = f.up.url("/a")
            self.assertEqual(f.call(u)[0], 401)
            self.assertEqual(f.call(u, headers={"X-Client-Key": "wrong"})[0], 401)
            self.assertEqual(f.call(None, headers={"X-Client-Key": "s3cret"}, path="/v1/health")[0], 200)
            self.assertEqual(f.call(u, headers={"X-Client-Key": "s3cret"})[0], 200)
            self.assertEqual(f.call(None, path="/v1/health")[0], 200)          # health открыт без ключа
        finally:
            f.close()


def make_keys_db(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE users(tg_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, created REAL, consent REAL, "
               "banned INTEGER NOT NULL DEFAULT 0, plan TEXT NOT NULL DEFAULT 'free')")
    db.execute("CREATE TABLE keys(key_hash TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, "
               "revoked INTEGER NOT NULL DEFAULT 0, last_used REAL)")
    db.commit()
    return db


class TgKeyTests(unittest.TestCase):
    NOW = 1_000_000.0

    def setUp(self):
        self.dbp = os.path.join(tempfile.mkdtemp(prefix="tkeys_"), "bot.sqlite")
        self.db = make_keys_db(self.dbp)
        self.db.execute("INSERT INTO users(tg_id, username) VALUES (1,'alice'),(2,'bob'),(3,'eve')")
        self.db.execute("UPDATE users SET banned=1 WHERE tg_id=3")
        self.add("TIA-AAAA-AAAA-AAAA", 1, self.NOW + 3600)
        self.add("TIA-BBBB-BBBB-BBBB", 2, self.NOW - 10)                      # истёк
        self.add("TIA-CCCC-CCCC-CCCC", 2, self.NOW + 3600, revoked=1)
        self.add("TIA-DDDD-DDDD-DDDD", 3, self.NOW + 3600)                    # владелец забанен
        self.db.commit()
        self.f = Fx(keys_db=self.dbp)

    def tearDown(self):
        self.f.close()
        self.db.close()

    def add(self, key, tg, expires, revoked=0):
        self.db.execute("INSERT INTO keys(key_hash, tg_id, created, expires, revoked) VALUES (?,?,?,?,?)",
                        (ts.key_hash(key), tg, self.NOW - 100, expires, revoked))

    def check(self, key):
        hd = {"X-Client-Key": key} if key is not None else {}
        st, body, _ = self.f.call(None, headers=hd, path="/v1/auth/check")
        return st, json.loads(body)

    def test_valid_and_normalized(self):
        st, j = self.check("TIA-AAAA-AAAA-AAAA")
        self.assertEqual((st, j["ok"], j["username"], j["plan"], j["bot"]), (200, True, "alice", "free", "testbot"))
        self.assertEqual(j["expires"], self.NOW + 3600)
        self.assertEqual(self.check("  tia-aaaa-aaaa-aaaa ")[0], 200)
        self.assertEqual(self.check("tia-aaaa-aaaa -aaaa")[0], 200)
        self.assertEqual(self.f.call(self.f.up.url("/a"), headers={"X-Client-Key": "TIA-AAAA-AAAA-AAAA"})[0], 200)

    def test_rejections(self):
        self.assertEqual(self.check("TIA-BBBB-BBBB-BBBB"), (401, {"ok": False, "error": "expired", "bot": "testbot"}))
        self.assertEqual(self.check("TIA-CCCC-CCCC-CCCC")[1]["error"], "expired")      # отозван = expired
        self.assertEqual(self.check("TIA-DDDD-DDDD-DDDD")[1]["error"], "banned")
        self.assertEqual(self.check("TIA-ZZZZ-ZZZZ-ZZZZ")[1]["error"], "invalid")
        self.assertEqual(self.check(None)[1]["error"], "invalid")
        u = self.f.up.url("/a")
        self.assertEqual(self.f.call(u)[0], 401)
        st, body, _ = self.f.call(u, headers={"X-Client-Key": "TIA-BBBB-BBBB-BBBB"})
        self.assertEqual((st, json.loads(body)["error"]), (401, "expired"))
        self.assertEqual(self.f.up.hits, 0)

    def test_health_open(self):
        st, body, _ = self.f.call(None, path="/v1/health")
        j = json.loads(body)
        self.assertEqual((st, j["auth"], j["bot"]), (200, "keys", "testbot"))

    def test_cache_does_not_outlive_expiry(self):
        self.add("TIA-EEEE-EEEE-EEEE", 1, self.NOW + 30)
        self.db.commit()
        self.assertEqual(self.check("TIA-EEEE-EEEE-EEEE")[0], 200)
        self.f.now[0] = self.NOW + 31                    # меньше минуты кэша, но срок прошёл
        self.assertEqual(self.check("TIA-EEEE-EEEE-EEEE")[1]["error"], "expired")

    def test_cache_and_revoke_after_ttl(self):
        self.assertEqual(self.check("TIA-AAAA-AAAA-AAAA")[0], 200)
        self.db.execute("UPDATE keys SET revoked=1 WHERE key_hash=?", (ts.key_hash("TIA-AAAA-AAAA-AAAA"),))
        self.db.commit()
        self.assertEqual(self.check("TIA-AAAA-AAAA-AAAA")[0], 200)       # ещё из кэша
        self.f.now[0] = self.NOW + 61
        self.assertEqual(self.check("TIA-AAAA-AAAA-AAAA")[1]["error"], "expired")

    def test_last_used_throttled(self):
        h = ts.key_hash("TIA-AAAA-AAAA-AAAA")
        q = lambda: self.db.execute("SELECT last_used FROM keys WHERE key_hash=?", (h,)).fetchone()[0]
        self.check("TIA-AAAA-AAAA-AAAA")
        self.assertEqual(q(), self.NOW)
        self.f.now[0] = self.NOW + 30
        self.check("TIA-AAAA-AAAA-AAAA")
        self.assertEqual(q(), self.NOW)                  # не чаще раза в минуту
        self.f.now[0] = self.NOW + 90
        self.check("TIA-AAAA-AAAA-AAAA")
        self.assertEqual(q(), self.NOW + 90)

    def test_shared_key_still_works(self):
        self.f.close()
        self.f = Fx(key="s3cret", keys_db=self.dbp)
        u = self.f.up.url("/a")
        self.assertEqual(self.f.call(u, headers={"X-Client-Key": "s3cret"})[0], 200)
        self.assertEqual(self.f.call(u, headers={"X-Client-Key": "TIA-AAAA-AAAA-AAAA"})[0], 200)
        self.assertEqual(self.f.call(u, headers={"X-Client-Key": "nope"})[0], 401)
        st, body, _ = self.f.call(None, headers={"X-Client-Key": "s3cret"}, path="/v1/auth/check")
        self.assertEqual((st, json.loads(body)["expires"]), (200, None))

    def test_db_failure_is_unauthorized_not_crash(self):
        self.f.close()
        self.f = Fx(keys_db=os.path.join(os.path.dirname(self.dbp), "missing.sqlite"))
        self.assertEqual(self.f.call(self.f.up.url("/a"), headers={"X-Client-Key": "TIA-AAAA-AAAA-AAAA"})[0], 401)
        self.assertEqual(self.f.call(None, path="/v1/health")[0], 200)

    def test_no_auth_mode(self):
        f = Fx()
        try:
            st, body, _ = f.call(None, path="/v1/auth/check")
            j = json.loads(body)
            self.assertEqual((st, j["ok"], j["expires"]), (200, True, None))
            self.assertEqual(json.loads(f.call(None, path="/v1/health")[1])["auth"], "none")
        finally:
            f.close()


if __name__ == "__main__":
    unittest.main()
