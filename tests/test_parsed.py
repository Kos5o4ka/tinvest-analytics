"""Серверный разбор страниц (/v1/parsed/*) совпадает с клиентским на общих HTML-образцах; клиентский ds_parsed и откат. Офлайн."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "server"))
import _load  # noqa: E402
import tinvest_server as ts  # noqa: E402

m = _load.load()
FX = os.path.join(ROOT, "tests", "fixtures")


def fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


class Same(unittest.TestCase):
    def test_placements(self):
        h = fx("investmint_placements.html")
        a, b = m.placements_parse(h), ts.placements_parse(h)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 3)
        self.assertEqual([r["start"] for r in a], sorted(r["start"] for r in a))
        self.assertEqual(json.loads(json.dumps(a)), a)
        self.assertEqual([r["isin"] for r in a], ["RU000A10XYZ9", "", "RU000A10ABC1"])
        self.assertEqual(a[0]["short"], "Вектор")
        self.assertEqual(m.placements_parse(""), ts.placements_parse(""))

    def test_ifrs(self):
        h = fx("smartlab_ifrs.html")
        a, b = m.ifrs_parse(h), ts.ifrs_parse(h)
        self.assertEqual(a, b)
        self.assertEqual(a["labels"], ["2023", "2024", "2025", "LTM"])
        self.assertIn("revenue", a["rows"])
        for bad in ("", "<html>captcha</html>"):
            self.assertEqual(m.ifrs_parse(bad), ts.ifrs_parse(bad))
        self.assertEqual(m._ifrs_num("31,4%"), ts._ifrs_num("31,4%"))


class Up(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/bond-placements"):
            b = fx("investmint_placements.html").encode()
        elif self.path.startswith("/q/SBER/"):
            b = fx("smartlab_ifrs.html").encode()
        elif self.path.startswith("/q/JUNK/"):
            b = b"<html>captcha</html>"
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class Endpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = ThreadingHTTPServer(("127.0.0.1", 0), Up)
        threading.Thread(target=cls.up.serve_forever, daemon=True).start()
        cls.upaddr = "127.0.0.1:%d" % cls.up.server_address[1]

        def upstream(method, url, body, ctype, headers):
            path = url.split("://", 1)[1].split("/", 1)[1]
            r = urllib.request.Request("http://%s/%s" % (cls.upaddr, path))
            try:
                with urllib.request.urlopen(r, timeout=5) as x:
                    return x.status, "text/html", x.read(), []
            except urllib.error.HTTPError as e:
                return e.code, "text/html", b"", []
        cls.app = ts.DataServer(tempfile.mkdtemp(), key="k", upstream=upstream, rates={"*": 1000})
        cls.http = ts.make_http_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.http.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.up.shutdown()

    def get(self, path, key="k"):
        req = urllib.request.Request(self.base + path, headers={"X-Client-Key": key} if key else {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_placements(self):
        c, j = self.get("/v1/parsed/investmint/placements")
        self.assertEqual(c, 200)
        self.assertTrue(j["ok"])
        self.assertEqual(j["v"], 1)
        self.assertEqual(j["data"], m.placements_parse(fx("investmint_placements.html")))
        self.assertEqual(self.get("/v1/parsed/investmint/placements")[1], j)     # из кэша разбора

    def test_ifrs(self):
        c, j = self.get("/v1/parsed/smartlab/ifrs?ticker=sber")
        self.assertEqual((c, j["ok"]), (200, True))
        self.assertEqual(j["data"], m.ifrs_parse(fx("smartlab_ifrs.html")))

    def test_errors(self):
        self.assertEqual(self.get("/v1/parsed/smartlab/ifrs?ticker=JUNK")[1], {"ok": False, "error": "parse failed"})
        self.assertEqual(self.get("/v1/parsed/smartlab/ifrs?ticker=NOPE")[1]["error"], "upstream status 404")
        self.assertEqual(self.get("/v1/parsed/smartlab/ifrs?ticker=a/b")[0], 400)
        self.assertEqual(self.get("/v1/parsed/nothing")[0], 404)
        self.assertEqual(self.get("/v1/parsed/smartlab/ifrs?ticker=SBER", key="bad")[0], 401)


class Client(unittest.TestCase):
    def setUp(self):
        self.saved = (m.ds_conf, m._ds_state["down_until"])

    def tearDown(self):
        m.ds_conf = self.saved[0]
        m._ds_state["down_until"] = self.saved[1]

    def test_off(self):
        m.ds_conf = lambda: ("", "")
        self.assertIsNone(m.ds_parsed("investmint/placements"))

    def test_ok_and_fallbacks(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if "old" in self.path:
                    self.send_response(404)
                    b = b"{}"
                elif "badv" in self.path:
                    self.send_response(200)
                    b = b'{"ok":true,"v":2,"data":[1]}'
                elif "nok" in self.path:
                    self.send_response(200)
                    b = b'{"ok":false,"error":"x"}'
                else:
                    self.send_response(200)
                    b = b'{"ok":true,"v":1,"data":{"a":1}}'
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
        s = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        try:
            base = "http://127.0.0.1:%d" % s.server_address[1]
            m.ds_conf = lambda: (base, "")
            m._ds_state["down_until"] = 0.0
            self.assertEqual(m.ds_parsed("smartlab/ifrs", {"ticker": "SBER"}), {"a": 1})
            self.assertIsNone(m.ds_parsed("old"))
            self.assertIsNone(m.ds_parsed("badv"))
            self.assertIsNone(m.ds_parsed("nok"))
            self.assertEqual(m._ds_state["down_until"], 0.0)       # 404/ok:false не «роняют» сервер
        finally:
            s.shutdown()
        self.assertIsNone(m.ds_parsed("x"))                         # сервер лёг: None, не исключение
        m._ds_state["down_until"] = 0.0

    def test_primary_rows_fallback(self):
        saved = (m.ds_parsed, m.http_text, m._pri.copy())
        try:
            m._pri.update(t=0, rows=[])
            m.ds_parsed = lambda *a, **k: None
            m.http_text = lambda *a, **k: fx("investmint_placements.html")
            self.assertEqual(len(m.primary_rows()), 3)
            m._pri.update(t=0, rows=[])
            m.ds_parsed = lambda *a, **k: [{"start": "2026-01-01", "isin": "X"}]
            m.http_text = lambda *a, **k: self.fail("не должен ходить сам")
            self.assertEqual(m.primary_rows()[0]["isin"], "X")
        finally:
            m.ds_parsed, m.http_text = saved[0], saved[1]
            m._pri.clear()
            m._pri.update(saved[2])


if __name__ == "__main__":
    unittest.main()
