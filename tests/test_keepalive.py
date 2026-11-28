"""Постоянные соединения с сервером данных и журнал медленных экранов."""
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402


class Stub:
    def __init__(self, idle=5.0):
        self.ports = []
        me = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = idle

            def log_message(self, *a):
                pass

            def do_GET(self):
                me.ports.append(self.client_address[1])
                code, hdr = 200, {}
                if self.path.startswith("/nf"):
                    code, hdr = 404, {"X-Cache": "hit"}
                elif self.path.startswith("/auth"):
                    code = 401
                b = json.dumps({"path": self.path}).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(b)))
                for k, v in hdr.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(b)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class KeepAlive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load.load()

    def setUp(self):
        self.m.ds_pool_clear()

    def get(self, st, path):
        with self.m.ds_urlopen(urllib.request.Request(st.base + path), timeout=5) as r:
            return r.status, json.loads(r.read())

    def test_two_requests_share_one_connection(self):
        st = Stub()
        self.addCleanup(st.close)
        self.assertEqual(self.get(st, "/a"), (200, {"path": "/a"}))
        self.assertEqual(self.get(st, "/b?x=1"), (200, {"path": "/b?x=1"}))
        self.assertEqual(len(set(st.ports)), 1)

    def test_server_closed_idle_connection_is_retried(self):
        st = Stub(idle=0.2)
        self.addCleanup(st.close)
        self.get(st, "/a")
        time.sleep(0.5)                                     # сервер закрыл простаивающее соединение
        self.assertEqual(self.get(st, "/b")[0], 200)
        self.assertEqual(len(set(st.ports)), 2)

    def test_errors_match_urlopen(self):
        st = Stub()
        self.addCleanup(st.close)
        with self.assertRaises(urllib.error.HTTPError) as c:
            self.get(st, "/nf")
        self.assertEqual((c.exception.code, c.exception.headers.get("X-Cache")), (404, "hit"))
        self.assertEqual(json.loads(c.exception.read()), {"path": "/nf"})
        with self.assertRaises(urllib.error.HTTPError) as c:
            self.get(st, "/auth")
        self.assertEqual(c.exception.code, 401)
        self.assertEqual(self.get(st, "/a")[0], 200)        # после ошибок соединение по-прежнему рабочее
        self.assertEqual(len(set(st.ports)), 1)

    def test_refused_is_urlerror(self):
        st = Stub()
        base = st.base
        st.close()
        with self.assertRaises(urllib.error.URLError):
            with self.m.ds_urlopen(urllib.request.Request(base + "/a"), timeout=2):
                pass


class PerfLog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load.load()

    def test_slow_route_logged_without_query_data(self):
        m = self.m
        path = os.path.join(m.APP_DIR, "perf.log")
        if os.path.exists(path):
            os.remove(path)
        c0 = m.perf_snapshot()
        m.perf_count("tinvest")
        m.perf_log(m.perf_label("/api/bench", "account=123&kind=x&token=SECRET"), 1.25, c0)
        m.perf_log("/api/fast", 0.1, c0)
        txt = open(path, encoding="utf-8").read()
        self.assertIn("приблизительные", txt)
        self.assertIn("/api/bench?kind=x\t1.25", txt)
        self.assertIn("Т-Инвестиции 1", txt)
        self.assertNotIn("SECRET", txt)
        self.assertNotIn("account", txt)
        self.assertNotIn("/api/fast", txt)


if __name__ == "__main__":
    unittest.main()
