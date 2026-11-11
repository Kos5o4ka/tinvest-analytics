"""Уведомления приложения: POST /v1/notify на сервер данных (локальная заглушка), сообщения об ошибках, очистка старых настроек."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

M = _load.load()


class Stub:
    def __init__(self):
        self.code, self.reply = 200, {"ok": True, "queued": 1}
        self.posts = []
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                me.posts.append((self.path, self.headers.get("X-Client-Key"), json.loads(body)))
                b = json.dumps(me.reply).encode()
                self.send_response(me.code)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class T(unittest.TestCase):
    def setUp(self):
        self.stub = Stub()
        self.conf(data_server=self.stub.url, data_key="TIA-AAAA-AAAA-AAAA")

    def tearDown(self):
        self.stub.close()
        self.conf(data_server="off", data_key="")

    def conf(self, **kw):
        c = M.load_config()
        c.update(kw)
        M.save_config(c)
        M.ds_reset()

    def err(self):
        with self.assertRaises(M.ApiError) as cm:
            M.tg_send(M.load_config(), "x")
        return str(cm.exception), cm.exception.status if hasattr(cm.exception, "status") else None

    def test_send_ok(self):
        self.assertEqual(M.tg_send(M.load_config(), "<b>Привет</b>"), 1)
        path, key, body = self.stub.posts[0]
        self.assertEqual((path, key), ("/v1/notify", "TIA-AAAA-AAAA-AAAA"))
        self.assertTrue(body["text"].startswith("<b>Привет</b>"))
        self.assertTrue(body["text"].endswith(M.TG_DISCLAIMER))

    def test_long_text_fits_limit(self):
        M.tg_send(M.load_config(), "\n".join("строка %d" % i for i in range(1000)))
        t = self.stub.posts[0][2]["text"]
        self.assertLessEqual(len(t), 3500)
        self.assertTrue(t.endswith(M.TG_DISCLAIMER))

    def test_errors(self):
        self.stub.code, self.stub.reply = 409, {"ok": False, "error": "notify_off"}
        self.assertIn("/notify_on", self.err()[0])
        self.stub.code, self.stub.reply = 402, {"error": "pro_required"}
        self.assertIn("Pro", self.err()[0])
        self.stub.code, self.stub.reply = 429, {"ok": False, "error": "rate_limit"}
        self.assertIn("Слишком много сообщений", self.err()[0])
        self.stub.code, self.stub.reply = 401, {"ok": False, "error": "expired"}
        self.assertIn("Войдите по ключу", self.err()[0])
        self.stub.code, self.stub.reply = 403, {"error": "x"}
        self.assertIn("только по ключу", self.err()[0])
        self.stub.code, self.stub.reply = 503, {}
        self.assertIn("Сервер недоступен", self.err()[0])

    def test_no_key_and_off_and_offline(self):
        self.conf(data_key="")
        self.assertIn("Войдите по ключу", self.err()[0])
        self.assertEqual(self.stub.posts, [])
        self.conf(data_server="off", data_key="TIA-AAAA-AAAA-AAAA")
        self.assertIn("сервер данных", self.err()[0])
        self.conf(data_server="http://127.0.0.1:9", data_key="TIA-AAAA-AAAA-AAAA")
        self.assertIn("Сервер недоступен", self.err()[0])

    def test_tick_requires_opt_in_and_login(self):
        self.conf(tg_enabled=False, tg_digest=True, tg_digest_time="00:00")
        self.assertEqual(M.tg_tick(), 0)
        self.assertEqual(self.stub.posts, [])
        self.conf(tg_enabled=True, tg_digest=True, tg_digest_time="00:00", data_key="")
        self.assertEqual(M.tg_tick(), 0)
        self.assertEqual(self.stub.posts, [])
        self.conf(tg_enabled=True, tg_digest=True, tg_digest_time="00:00", data_key="TIA-AAAA-AAAA-AAAA")
        M.tg_tick()
        self.assertEqual(len(self.stub.posts), 1)
        self.assertIn("Сводка", self.stub.posts[0][2]["text"])

    def test_legacy_keys_cleanup_and_save(self):
        self.conf(tg_token="123456:SECRETSECRETSECRETSECRET", tg_chat="42")
        M._tg_cleanup()
        c = M.load_config()
        self.assertNotIn("tg_token", c)
        self.assertNotIn("tg_chat", c)
        self.conf(tg_token="x", tg_chat="1")
        r = M.tg_save({}, {"tg_enabled": True, "tg_pay_days": 99, "token": "ignored", "chat": "5"})
        self.assertTrue(r["settings"]["tg_enabled"])
        self.assertEqual(r["settings"]["tg_pay_days"], 60)
        self.assertNotIn("tg_chat", r["settings"])
        c = M.load_config()
        self.assertNotIn("tg_token", c)
        self.assertNotIn("tg_chat", c)
        self.assertNotIn("/api/tg/find_chat", M.API_POST)


if __name__ == "__main__":
    unittest.main()
