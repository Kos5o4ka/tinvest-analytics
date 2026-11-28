"""Клиентская функция ext_open: прямой режим, сервер данных, откат на прямой запрос, ключ. Офлайн."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402


class Fake:
    """Один сервер изображает и источник (прямой режим), и сервер данных (/v1/fetch)."""

    def __init__(self):
        self.log = []
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _r(self, code, body, hdr=()):
                self.send_response(code)
                for k, v in hdr:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                me.log.append((self.path, self.headers.get("X-Client-Key"), self.headers.get("X-Up-Cookie")))
                if self.path.startswith("/v1/health"):
                    return self._r(200, json.dumps({"ok": True, "version": "9.9", "uptime": 1, "cache_items": 3}).encode())
                if self.path.startswith("/v1/fetch"):
                    mode = me.mode
                    if mode == "401":
                        return self._r(401, b"{}")
                    if mode == "403host":
                        return self._r(403, json.dumps({"error": "host not allowed"}).encode())
                    if mode == "403":
                        return self._r(403, b"{}")
                    if mode == "5xx":
                        return self._r(500, b"x")
                    if mode == "404":
                        return self._r(404, b"gone", [("X-Cache", "miss"), ("Content-Type", "text/plain")])
                    if mode == "blocked":
                        return self._r(503, b"{}", [("X-Upstream-Error", "1"), ("X-Upstream-Blocked", "90"), ("Retry-After", "90")])
                    if mode == "blocked0":
                        return self._r(503, b"{}", [("X-Upstream-Error", "1"), ("X-Upstream-Blocked", "0")])
                    if mode == "upfail":
                        return self._r(502, b"{}", [("X-Upstream-Error", "1")])
                    return self._r(200, b"via-server", [("X-Cache", "hit"), ("Content-Type", "text/plain"), ("X-Set-Cookie", "sid=7; Path=/")])
                if self.path.startswith("/d429"):
                    return self._r(429, b"slow", [("Retry-After", "40")] if me.dmode == "ra" else [])
                if self.path.startswith("/d403"):
                    return self._r(403, b"nope")
                self._r(200, b"direct", [("Content-Type", "text/plain")])

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self._r(200, b"post:" + self.rfile.read(n))

        self.mode = "ok"
        self.dmode = ""
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class ExtOpenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load.load()

    def setUp(self):
        self.fk = Fake()
        self.addCleanup(self.fk.close)
        self.orig = dict(self.m._ds_state)
        self.m._ds_bypass.clear()
        self.m._direct_block.clear()
        os.environ["TINVEST_DATA_SERVER"] = "off"
        os.environ.pop("TINVEST_DATA_KEY", None)
        self.set_cfg("", "")

    def tearDown(self):
        os.environ["TINVEST_DATA_SERVER"] = "off"
        os.environ.pop("TINVEST_DATA_KEY", None)
        self.set_cfg("", "")

    def set_cfg(self, url, key):
        cfg = self.m.load_config()
        cfg["data_server"], cfg["data_key"] = url, key
        self.m.save_config(cfg)
        self.m.ds_reset()
        for k in ("hit", "miss", "stale", "direct"):
            self.m._ds_state[k] = 0

    def test_direct_mode(self):
        st, body, ct = self.m.ext_open(self.fk.base + "/x")
        self.assertEqual((st, body, ct), (200, b"direct", "text/plain"))
        self.assertEqual(self.m.ds_status()["mode"], "direct")
        self.assertEqual(self.m.http_text(self.fk.base + "/x"), "direct")
        self.assertEqual(self.m.ext_open(self.fk.base + "/p", data=b"a=1")[1], b"post:a=1")

    def test_server_mode_and_key_header(self):
        self.set_cfg(self.fk.base, "k123")
        jar = {}
        st, body, ct = self.m.ext_open("https://iss.moex.com/iss/x.json?a=1&b=2", jar=jar)
        self.assertEqual(body, b"via-server")
        path, key, _ = self.fk.log[-1]
        self.assertTrue(path.startswith("/v1/fetch?url=https%3A%2F%2Fiss.moex.com%2Fiss%2Fx.json%3Fa%3D1%26b%3D2"))
        self.assertEqual(key, "k123")
        self.assertEqual(jar, {"sid": "7"})
        self.m.ext_open("https://iss.moex.com/iss/y", jar=jar)
        self.assertEqual(self.fk.log[-1][2], "sid=7")
        s = self.m.ds_status()
        self.assertEqual((s["mode"], s["hit"], s["direct"]), ("server", 2, 0))

    def test_env_config(self):
        os.environ["TINVEST_DATA_SERVER"] = self.fk.base
        os.environ["TINVEST_DATA_KEY"] = "envkey"
        self.m.ds_reset()
        self.assertEqual(self.m.ext_open("https://iss.moex.com/a")[1], b"via-server")
        self.assertEqual(self.fk.log[-1][1], "envkey")

    def test_fallback_when_server_down_and_marking(self):
        s = Fake()
        dead = s.base
        s.close()
        self.set_cfg(dead, "")
        # сервер недоступен, а «источник» для прямого запроса живой
        t0 = time.time()
        st, body, ct = self.m.ext_open(self.fk.base + "/real")
        self.assertEqual(body, b"direct")
        self.assertEqual(self.m.ds_status()["mode"], "down")
        t1 = time.time()
        self.m.ext_open(self.fk.base + "/real2")
        self.assertLess(time.time() - t1, 1.0)          # сервер больше не опрашивается
        self.assertGreater(self.m._ds_state["down_until"], t0 + 200)
        self.m.ds_reset()
        self.assertEqual(self.m.ds_status()["mode"], "server")

    def test_fallback_on_401_and_5xx_but_not_404(self):
        self.set_cfg(self.fk.base, "")
        for mode in ("401", "5xx"):
            self.fk.mode = mode
            self.m.ds_reset()
            self.assertEqual(self.m.ext_open(self.fk.base + "/real")[1], b"direct")
            self.assertEqual(self.m.ds_status()["mode"], "down", mode)
        self.fk.mode = "upfail"                         # сервер жив, источник нет: прямой запрос, но сервер не «падает»
        self.m.ds_reset()
        self.assertEqual(self.m.ext_open(self.fk.base + "/real")[1], b"direct")
        self.assertEqual(self.m.ds_status()["mode"], "server")
        self.fk.mode = "404"
        n = len(self.fk.log)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.m.ext_open(self.fk.base + "/real")
        self.assertEqual(cm.exception.code, 404)
        self.assertEqual(len(self.fk.log), n + 1)       # прямой повтор не делался

    def test_host_not_allowed_keeps_server(self):
        """403 «host not allowed» (сайта нет в списке сервера): запрос напрямую, но сервер остаётся включённым для остальных."""
        self.set_cfg(self.fk.base, "k")
        self.fk.mode = "403host"
        self.m.ds_reset()
        self.assertEqual(self.m.ext_open(self.fk.base + "/btc")[1], b"direct")
        self.assertEqual(self.m.ds_status()["mode"], "server")
        self.fk.mode = "ok"
        self.assertEqual(self.m.ext_open(self.fk.base + "/real")[1], b"via-server")
        self.fk.mode = "403"                             # обычный 403 (ключ не принят) по-прежнему выключает сервер
        self.m.ds_reset()
        self.assertEqual(self.m.ext_open(self.fk.base + "/real")[1], b"direct")
        self.assertEqual(self.m.ds_status()["mode"], "down")

    def _fetches(self):
        return [p for p, _, _ in self.fk.log if p.startswith("/v1/fetch")]

    def test_blocked_header_goes_direct_and_bypasses_host(self):
        self.set_cfg(self.fk.base, "k")
        self.fk.mode = "blocked"
        a = self.fk.base + "/real"                         # 127.0.0.1
        self.assertEqual(self.m.ext_open(a)[1], b"direct")
        self.assertEqual(self.m.ds_status()["mode"], "server")        # сервер не «упал»
        bp = self.m.ds_status()["bypass"]
        self.assertEqual(list(bp), ["127.0.0.1"])
        self.assertTrue(80 < bp["127.0.0.1"] <= 91)
        n = len(self._fetches())
        self.fk.mode = "ok"
        self.assertEqual(self.m.ext_open(self.fk.base + "/again")[1], b"direct")   # тот же хост: сервер пропускаем
        self.assertEqual(len(self._fetches()), n)
        self.assertEqual(self.m.ds_status()["direct"], 2)
        other = self.fk.base.replace("127.0.0.1", "localhost") + "/x"
        self.assertEqual(self.m.ext_open(other)[1], b"via-server")                 # другой хост — через сервер
        self.assertEqual(len(self._fetches()), n + 1)
        self.m._ds_bypass["127.0.0.1"] = time.time() - 1                           # срок вышел
        self.assertEqual(self.m.ext_open(self.fk.base + "/z")[1], b"via-server")
        self.assertEqual(self.m.ds_status()["bypass"], {})

    def test_bypass_clamp_and_zero(self):
        self.set_cfg(self.fk.base, "")
        self.fk.mode = "blocked0"                          # одиночный отказ: хост не обходим
        self.assertEqual(self.m.ext_open(self.fk.base + "/real")[1], b"direct")
        self.assertEqual(self.m.ds_status()["bypass"], {})
        self.m._ds_note_bypass("h", "5")
        self.m._ds_note_bypass("g", "999999")
        self.m._ds_note_bypass("d", None)
        bp = self.m.ds_status()["bypass"]
        self.assertTrue(30 <= bp["h"] <= 31 and 1799 <= bp["g"] <= 1801 and 299 <= bp["d"] <= 301)

    def test_404_from_source_unchanged(self):
        self.set_cfg(self.fk.base, "")
        self.fk.mode = "404"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.m.ext_open(self.fk.base + "/real")
        self.assertEqual(cm.exception.code, 404)
        self.assertEqual(self.m.ds_status()["bypass"], {})

    def test_direct_429_client_cooldown(self):
        self.fk.dmode = "ra"
        url = self.fk.base + "/d429"
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.m.ext_open(url)
        self.assertEqual(cm.exception.code, 429)
        n = len(self.fk.log)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.m.ext_open(self.fk.base + "/fine")        # пауза держится на хосте, сети не касаемся
        self.assertEqual(cm.exception.code, 429)
        self.assertIn("временно ограничил запросы, повтор через", cm.exception.msg)
        self.assertIn("127.0.0.1", cm.exception.msg)
        self.assertEqual(len(self.fk.log), n)
        self.assertEqual(self.m.ext_open(self.fk.base.replace("127.0.0.1", "localhost") + "/fine")[1], b"direct")   # другие хосты не затронуты
        self.m._direct_block["127.0.0.1"][0] = time.time() - 1       # пауза кончилась -> запрос идёт, успех сбрасывает
        self.assertEqual(self.m.ext_open(self.fk.base + "/fine")[1], b"direct")
        self.assertNotIn("127.0.0.1", self.m._direct_block)

    def test_direct_429_exponential_without_retry_after(self):
        self.fk.dmode = ""
        for want in (120, 240):
            with self.assertRaises(urllib.error.HTTPError):
                self.m.ext_open(self.fk.base + "/d429")
            left = self.m._direct_block["127.0.0.1"][0] - time.time()
            self.assertTrue(want - 2 <= left <= want, left)
            self.m._direct_block["127.0.0.1"][0] = time.time() - 1

    def test_server_timeout_sends_host_direct(self):
        """Сервер не ответил по источнику за отведённое время: следующие запросы к этому хосту не ждут сервер снова."""
        import socket
        from unittest import mock
        self.set_cfg(self.fk.base, "k")
        calls = []

        def slow(req, timeout=30):
            calls.append(req.full_url)
            raise socket.timeout("timed out")
        with mock.patch.object(self.m, "ds_urlopen", slow):
            self.assertEqual(self.m.ext_open(self.fk.base + "/a")[1], b"direct")
            self.assertEqual(self.m.ext_open(self.fk.base + "/b")[1], b"direct")
        self.assertEqual(len(calls), 1)                                   # второй запрос сразу напрямую
        self.assertTrue(self.m._ds_bypassed("127.0.0.1"))
        self.assertLess(self.m._ds_state["down_until"], time.time())     # сервер для других источников не отключён
        dead = "http://127.0.0.1:1"                                       # напрямую хост недоступен -> обход снимается
        self.m._ds_note_bypass("127.0.0.1", "600")
        with mock.patch.object(self.m, "ds_urlopen", slow):
            with self.assertRaises(urllib.error.URLError):
                self.m.ext_open(dead + "/c", timeout=2)
        self.assertFalse(self.m._ds_bypassed("127.0.0.1"))

    def test_direct_403_only_when_bypassed(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.m.ext_open(self.fk.base + "/d403")
        self.assertEqual(self.m._direct_block, {})
        self.m._ds_note_bypass("127.0.0.1", "60")
        with self.assertRaises(urllib.error.HTTPError):
            self.m.ext_open(self.fk.base + "/d403")
        self.assertIn("127.0.0.1", self.m._direct_block)

    def test_connection_test_endpoint(self):
        self.set_cfg(self.fk.base, "")
        r = self.m.ds_test({}, {"url": "http://evil.example", "key": "z"})   # адрес из формы игнорируется
        self.assertEqual((r["ok"], r["version"]), (True, "9.9"))
        self.assertEqual(self.fk.log[-1][1], "z")

    def test_key_never_exposed(self):
        self.set_cfg(self.fk.base, "topsecret-key")
        self.assertIn("data_key", self.m.SECRET_KEYS)
        pub = {k: v for k, v in self.m.load_config().items() if k not in self.m.SECRET_KEYS}
        self.assertNotIn("data_key", pub)
        self.assertNotIn("topsecret-key", json.dumps(pub))
        self.assertNotIn("topsecret-key", json.dumps(self.m.ds_status()))
        # резервная копия тоже без ключа
        import io
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(self.m.make_backup()))
        self.assertNotIn(b"topsecret-key", b"".join(z.read(n) for n in z.namelist()))


if __name__ == "__main__":
    unittest.main()
