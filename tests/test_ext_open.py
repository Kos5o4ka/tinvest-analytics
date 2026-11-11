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
                    if mode == "5xx":
                        return self._r(500, b"x")
                    if mode == "404":
                        return self._r(404, b"gone", [("X-Cache", "miss"), ("Content-Type", "text/plain")])
                    if mode == "upfail":
                        return self._r(502, b"{}", [("X-Upstream-Error", "1")])
                    return self._r(200, b"via-server", [("X-Cache", "hit"), ("Content-Type", "text/plain"), ("X-Set-Cookie", "sid=7; Path=/")])
                self._r(200, b"direct", [("Content-Type", "text/plain")])

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self._r(200, b"post:" + self.rfile.read(n))

        self.mode = "ok"
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

    def test_connection_test_endpoint(self):
        r = self.m.ds_test({}, {"url": self.fk.base, "key": "z"})
        self.assertEqual((r["ok"], r["version"]), (True, "9.9"))
        self.assertEqual(self.fk.log[-1][1], "z")
        with self.assertRaises(self.m.ApiError):
            self.m.ds_test({}, {"url": "not a url"})

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
