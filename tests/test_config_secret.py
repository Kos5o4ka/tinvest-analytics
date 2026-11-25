"""GET /api/config/secret: «глаз» в настройках. Только белый список имён, только локальный Host и своё окно. Без сети."""
import http.client
import json
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


class ConfigSecret(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = M.LocalHTTPServer(("127.0.0.1", 0), M.Handler)
        threading.Thread(target=cls.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        before = M.load_config()
        self.addCleanup(lambda: M.save_config(before))
        cfg = M.load_config()
        cfg.update(data_key="dk-secret-123", backup_password="bk-pass-456", token="")
        M.save_config(cfg)

    def get(self, path, host=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or "127.0.0.1:%d" % self.port}
        h.update(headers if headers is not None else {"X-TA-Secret": "1"})
        c.request("GET", path, headers=h)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, json.loads(body or b"{}")

    def test_whitelisted_values(self):
        self.assertEqual(self.get("/api/config/secret?name=data_key"), (200, {"name": "data_key", "value": "dk-secret-123"}))
        self.assertEqual(self.get("/api/config/secret?name=backup_password")[1]["value"], "bk-pass-456")
        self.assertEqual(self.get("/api/config/secret?name=token")[1]["value"], "")      # не задан — пустая строка

    def test_not_whitelisted(self):
        for name in ("theme", "hosts_prod", "", "data_key%00", "__class__"):
            code, _ = self.get("/api/config/secret?name=" + name)
            self.assertEqual(code, 400, name)

    def test_foreign_host_rejected(self):
        for host in ("evil.com:%d" % self.port, "evil.com", "127.0.0.1.evil.com:%d" % self.port):
            code, body = self.get("/api/config/secret?name=data_key", host=host)
            self.assertEqual(code, 403, host)
            self.assertNotIn("dk-secret", json.dumps(body))

    def test_header_and_fetch_site_required(self):
        self.assertEqual(self.get("/api/config/secret?name=data_key", headers={})[0], 403)
        for site in ("cross-site", "same-site", "none"):
            code, _ = self.get("/api/config/secret?name=data_key", headers={"X-TA-Secret": "1", "Sec-Fetch-Site": site})
            self.assertEqual(code, 403, site)
        self.assertEqual(self.get("/api/config/secret?name=data_key",
                                  headers={"X-TA-Secret": "1", "Sec-Fetch-Site": "same-origin"})[0], 200)

    def test_public_config_still_hides_secrets(self):
        code, body = self.get("/api/config", headers={})
        self.assertEqual(code, 200)
        self.assertNotIn("dk-secret-123", json.dumps(body, ensure_ascii=False))
        self.assertTrue(body["secret_set"]["data_key"])


class EnvTokenNotSaved(unittest.TestCase):
    """BUG-SEC-01: TINVEST_TOKEN из env не пишется в config.json и не вызывает demo_remove() при сохранении настроек."""

    def test_post_config_does_not_leak_env_token_or_remove_demo(self):
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="cfg_sec01_")
        cfg_path = os.path.join(tmp_dir, "config.json")
        old_cfg_path = M.CONFIG_PATH
        old_demo_remove = M.demo_remove
        old_env = os.environ.get("TINVEST_TOKEN")
        demo_calls = []
        M.CONFIG_PATH = cfg_path
        M.demo_remove = lambda: demo_calls.append(1)
        os.environ["TINVEST_TOKEN"] = "t.ENV_SECRET_XYZ"

        def cleanup():
            M.CONFIG_PATH = old_cfg_path
            M.demo_remove = old_demo_remove
            if old_env is None:
                os.environ.pop("TINVEST_TOKEN", None)
            else:
                os.environ["TINVEST_TOKEN"] = old_env

        self.addCleanup(cleanup)

        srv = M.LocalHTTPServer(("127.0.0.1", 0), M.Handler)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        port = srv.server_address[1]

        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        payload = json.dumps({"theme": "dark"}).encode("utf-8")
        c.request("POST", "/api/config", body=payload,
                  headers={"Host": "127.0.0.1:%d" % port, "Content-Type": "application/json",
                           "Content-Length": str(len(payload))})
        r = c.getresponse()
        r.read()
        c.close()
        self.assertEqual(r.status, 200)

        with open(cfg_path, encoding="utf-8") as f:
            raw = f.read()
        disk = json.loads(raw)
        self.assertNotIn("t.ENV_SECRET_XYZ", raw)
        self.assertNotIn("_env_token", raw)
        self.assertEqual(disk.get("token"), "")
        self.assertEqual(disk.get("theme"), "dark")
        self.assertEqual(demo_calls, [])


if __name__ == "__main__":
    unittest.main()
