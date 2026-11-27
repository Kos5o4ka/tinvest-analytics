"""HWID: хэш идентификатора ПК для привязки пробного периода. Только хэш, сырой id наружу не уходит."""
import hashlib
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

RAW = "RAW-MACHINE-ID-1234-SECRET"


class HwidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load.load()

    def setUp(self):
        self.m._hwid_cache["v"] = ""
        self.addCleanup(lambda: self.m._hwid_cache.update(v=""))

    def test_hash_is_sha256_of_raw_plus_salt(self):
        h = self.m.hwid_hash(RAW)
        self.assertEqual(h, hashlib.sha256((RAW + "|" + self.m.HWID_SALT).encode()).hexdigest())
        self.assertEqual(len(h), 64)
        self.assertNotIn(RAW, h)
        self.assertNotEqual(h, self.m.hwid_hash(RAW + "x"))

    def test_get_uses_machine_id(self):
        orig = self.m._hwid_machine_raw
        self.m._hwid_machine_raw = lambda: RAW
        try:
            self.assertEqual(self.m.hwid_get(), self.m.hwid_hash(RAW))
            self.assertEqual(self.m.hwid_headers(), {"X-Hwid": self.m.hwid_hash(RAW)})
        finally:
            self.m._hwid_machine_raw = orig

    def test_fallback_random_id_is_stable(self):
        orig = self.m._hwid_machine_raw
        self.m._hwid_machine_raw = lambda: ""
        try:
            p = os.path.join(self.m.APP_DIR, "hwid.id")
            if os.path.exists(p):
                os.remove(p)
            a = self.m.hwid_get()
            self.m._hwid_cache["v"] = ""
            self.assertEqual(a, self.m.hwid_get())
            self.assertTrue(os.path.exists(p))
            self.assertEqual(len(a), 64)
        finally:
            self.m._hwid_machine_raw = orig

    def test_header_sent_with_key_and_no_raw_id(self):
        seen = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.append(dict(self.headers))
                b = json.dumps({"ok": True, "expires": 4e9, "plan": "free", "pro_until": None,
                                "trial_blocked": True, "message": "Пробный период на этом компьютере уже использован"}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        orig = self.m._hwid_machine_raw
        self.m._hwid_machine_raw = lambda: RAW
        try:
            res = self.m._auth_eval("http://127.0.0.1:%d" % srv.server_address[1], "TIA-AAAA-AAAA-AAAA")
        finally:
            self.m._hwid_machine_raw = orig
        hd = {k.lower(): v for k, v in seen[0].items()}
        self.assertEqual(hd["x-hwid"], self.m.hwid_hash(RAW))
        self.assertNotIn(RAW, json.dumps(seen))
        self.assertTrue(res["trial_blocked"])
        self.assertIn("уже использован", res["message"])

    def test_no_header_without_key(self):
        seen = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.append(dict(self.headers))
                b = b"{}"
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        self.m._auth_http("http://127.0.0.1:%d" % srv.server_address[1], "/v1/health", "")
        self.assertNotIn("x-hwid", {k.lower() for k in seen[0]})


if __name__ == "__main__":
    unittest.main()
