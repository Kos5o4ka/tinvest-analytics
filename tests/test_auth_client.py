"""Вход по ключу: /api/auth/status, /login, /logout и отметка «нужен вход» при 401 в обычной работе. Офлайн (локальная заглушка сервера)."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402


class Stub:
    """Изображает сервер данных: /v1/health, /v1/auth/check, /v1/fetch."""

    def __init__(self):
        self.mode = "keys"          # keys | none | down | 5xx | old
        self.keys = {"TIA-AAAA-AAAA-AAAA": ("ok", 4_000_000_000), "TIA-OLD0-OLD0-OLD0": ("expired", 1), "TIA-BAN0-BAN0-BAN0": ("banned", 5)}
        self.calls = []
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _j(self, code, obj, hdr=()):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(b)))
                for k, v in hdr:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                key = self.headers.get("X-Client-Key") or ""
                me.calls.append((self.path, key))
                if me.mode == "5xx":
                    return self._j(503, {"error": "x"})
                if self.path.startswith("/v1/health"):
                    return self._j(200, {"ok": True, "auth": "none" if me.mode == "none" else "keys", "bot": "stubbot"})
                if self.path.startswith("/v1/auth/check"):
                    if me.mode == "old":
                        return self._j(404, {})
                    if me.mode == "none":
                        return self._j(200, {"ok": True, "expires": None, "username": "", "plan": "", "bot": "stubbot"})
                    st, exp = me.keys.get(key, ("invalid", 0))
                    if st == "ok":
                        return self._j(200, {"ok": True, "expires": exp, "username": "alice", "plan": "free", "bot": "stubbot"})
                    return self._j(401, {"ok": False, "error": st, "bot": "stubbot"})
                if self.path.startswith("/v1/fetch"):
                    if me.mode == "keys" and me.keys.get(key, ("x",))[0] != "ok":
                        return self._j(401, {"ok": False, "error": "invalid"})
                    b = b"via-server"
                    self.send_response(200)
                    self.send_header("X-Cache", "hit")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    return self.wfile.write(b)
                self._j(404, {})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class AuthClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load.load()

    def setUp(self):
        self.st = Stub()
        self.addCleanup(self.st.close)
        self.set_cfg(self.st.base, "")

    def tearDown(self):
        os.environ["TINVEST_DATA_SERVER"] = "off"
        self.set_cfg("", "")

    def set_cfg(self, url, key):
        c = self.m.load_config()
        c["data_server"], c["data_key"] = url, key
        self.m.save_config(c)
        self.m.ds_reset()

    def test_disabled_server_is_ok(self):
        self.set_cfg("off", "")
        self.assertEqual(self.m.auth_status(True)["state"], "ok")

    def test_no_key_need_login(self):
        r = self.m.auth_status(True)
        self.assertEqual((r["state"], r["error"], r["bot"]), ("need_login", "nokey", "stubbot"))

    def test_no_key_open_server_ok(self):
        self.st.mode = "none"
        self.assertEqual(self.m.auth_status(True)["state"], "ok")

    def test_valid_key(self):
        self.set_cfg(self.st.base, "TIA-AAAA-AAAA-AAAA")
        r = self.m.auth_status(True)
        self.assertEqual((r["state"], r["username"], r["expires"], r["bot"]), ("ok", "alice", 4_000_000_000, "stubbot"))

    def test_expired_banned_invalid(self):
        for key, err in (("TIA-OLD0-OLD0-OLD0", "expired"), ("TIA-BAN0-BAN0-BAN0", "banned"), ("TIA-ZZZZ-ZZZZ-ZZZZ", "invalid")):
            self.set_cfg(self.st.base, key)
            r = self.m.auth_status(True)
            self.assertEqual((r["state"], r["error"]), ("need_login", err))

    def test_offline(self):
        self.set_cfg(self.st.base, "TIA-AAAA-AAAA-AAAA")
        self.st.mode = "5xx"
        self.assertEqual(self.m.auth_status(True)["state"], "offline")
        self.st.close()
        self.assertEqual(self.m.auth_status(True)["state"], "offline")

    def test_old_server_without_endpoint(self):
        self.set_cfg(self.st.base, "k")
        self.st.mode = "old"
        self.assertEqual(self.m.auth_status(True)["state"], "ok")

    def test_cache_and_force(self):
        self.set_cfg(self.st.base, "TIA-AAAA-AAAA-AAAA")
        self.m.auth_status(True)
        n = len(self.st.calls)
        self.m.auth_status()
        self.assertEqual(len(self.st.calls), n)
        self.m.auth_status(True)
        self.assertEqual(len(self.st.calls), n + 1)

    def test_login_ok_saves_key_and_normalizes(self):
        r = self.m.auth_login({}, {"key": " tia-aaaa-aaaa-aaaa "})
        self.assertEqual((r["state"], r["username"]), ("ok", "alice"))
        self.assertEqual(self.m.load_config()["data_key"], "TIA-AAAA-AAAA-AAAA")
        self.assertEqual(self.m.ds_conf()[1], "TIA-AAAA-AAAA-AAAA")

    def test_login_rejects_without_saving(self):
        code, body = self.m.auth_login({}, {"key": "TIA-OLD0-OLD0-OLD0"})
        self.assertEqual((code, body["error"]), (401, "Ключ истёк — получите новый в боте"))
        self.assertEqual(self.m.auth_login({}, {"key": "TIA-BAN0-BAN0-BAN0"})[1]["error"], "Доступ ограничен")
        self.assertEqual(self.m.auth_login({}, {"key": "TIA-XXXX-XXXX-XXXX"})[1]["error"], "Неверный ключ")
        self.assertEqual(self.m.load_config()["data_key"], "")
        self.st.mode = "5xx"
        with self.assertRaises(self.m.ApiError):
            self.m.auth_login({}, {"key": "TIA-AAAA-AAAA-AAAA"})
        self.assertEqual(self.m.load_config()["data_key"], "")

    def test_logout(self):
        self.m.auth_login({}, {"key": "TIA-AAAA-AAAA-AAAA"})
        r = self.m.auth_logout({}, {})
        self.assertEqual(r["state"], "need_login")
        self.assertEqual(self.m.load_config()["data_key"], "")

    def test_401_during_work_marks_need_login_and_falls_back(self):
        self.set_cfg(self.st.base, "TIA-AAAA-AAAA-AAAA")
        self.assertEqual(self.m.auth_status(True)["state"], "ok")
        self.st.keys.clear()                                   # ключ отозван на сервере
        direct = Stub()
        self.addCleanup(direct.close)
        try:
            self.m.ext_open(direct.base + "/x")                  # сервер ответит 401, запрос уйдёт напрямую (заглушка отвечает 404)
        except Exception:  # noqa: BLE001
            pass
        r = self.m.auth_status()                                 # без force и без сетевых вызовов
        n = len(self.st.calls)
        self.assertEqual(r["state"], "need_login")
        self.assertEqual(len(self.st.calls), n)

    def test_url_default_and_off(self):
        os.environ["TINVEST_DATA_SERVER"] = ""
        self.set_cfg("", "")
        self.assertEqual(self.m.ds_conf()[0], self.m.DS_DEFAULT)
        self.set_cfg("off", "")
        self.assertEqual(self.m.ds_conf()[0], "")


if __name__ == "__main__":
    unittest.main()
