# -*- coding: utf-8 -*-
"""Сервер данных: один ключ — не больше TINVEST_MAX_DEVICES компьютеров (по хэшу ПК в X-Hwid), отвязанный ПК не входит."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tempfile  # noqa: E402
from test_server import Fx, make_keys_db, ts  # noqa: E402
import devices  # noqa: E402

KEY = "TIA-AAAA-AAAA-AAAA"


def hw(i):
    return ("%x" % i) * 64 if i < 16 else ("%064x" % i)


class DeviceLimit(unittest.TestCase):
    def setUp(self):
        devices.reset_cache()
        os.environ.pop("TINVEST_MAX_DEVICES", None)
        self.dbp = os.path.join(tempfile.mkdtemp(prefix="tdev_"), "bot.sqlite")
        self.db = make_keys_db(self.dbp)
        self.db.execute("INSERT INTO users(tg_id, username) VALUES (1,'alice')")
        self.db.execute("INSERT INTO keys(key_hash, tg_id, created, expires) VALUES (?,?,?,?)",
                        (ts.key_hash(KEY), 1, 0, 4e9))
        self.db.commit()
        self.f = Fx(keys_db=self.dbp)

    def tearDown(self):
        self.f.close()
        self.db.close()
        os.environ.pop("TINVEST_MAX_DEVICES", None)
        devices.reset_cache()

    def call(self, path, hwid=None, key=KEY):
        hd = {"X-Client-Key": key}
        if hwid:
            hd["X-Hwid"] = hwid
        st, body, _ = self.f.call(None, headers=hd, path=path)
        return st, json.loads(body)

    def test_five_pcs_then_refused(self):
        for i in range(1, 6):
            self.assertEqual(self.call("/v1/auth/check", hw(i))[0], 200)
        st, j = self.call("/v1/auth/check", hw(6))
        self.assertEqual((st, j["error"], j["max_devices"]), (401, "devices", 5))
        self.assertEqual(self.call("/v1/auth/check", hw(3))[0], 200)          # уже известный ПК входит
        self.assertEqual(self.call("/v1/auth/check")[0], 200)                 # старая версия без заголовка
        n = self.db.execute("SELECT COUNT(*) FROM key_devices WHERE tg_id=1").fetchone()[0]
        self.assertEqual(n, 5)

    def test_limit_from_env_and_any_endpoint(self):
        os.environ["TINVEST_MAX_DEVICES"] = "1"
        self.assertEqual(self.call("/v1/auth/check", hw(1))[0], 200)
        st, j = self.f.call(self.f.up.url("/a"), headers={"X-Client-Key": KEY, "X-Hwid": hw(2)})[:2]
        self.assertEqual(st, 401)                                             # не только /v1/auth/check
        self.assertEqual(json.loads(j)["error"], "devices")

    def test_unlinked_pc_is_blocked_and_frees_slot(self):
        os.environ["TINVEST_MAX_DEVICES"] = "2"
        self.call("/v1/auth/check", hw(1))
        self.call("/v1/auth/check", hw(2))
        self.db.execute("UPDATE key_devices SET blocked=1 WHERE hwid=?", (hw(1),))
        self.db.commit()
        devices.reset_cache()
        st, j = self.call("/v1/auth/check", hw(1))
        self.assertEqual((st, j["error"]), (401, "device_blocked"))
        self.assertEqual(self.call("/v1/auth/check", hw(3))[0], 200)          # место освободилось

    def test_bad_hwid_is_ignored(self):
        os.environ["TINVEST_MAX_DEVICES"] = "1"
        self.call("/v1/auth/check", hw(1))
        self.assertEqual(self.call("/v1/auth/check", "not-a-hash")[0], 200)


class ClientSendsHwid(unittest.TestCase):
    def test_every_key_request_carries_hwid(self):
        """Лимит компьютеров обходится, если хоть один запрос с ключом уходит без X-Hwid."""
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "py")
        miss = []
        for name in sorted(n for n in os.listdir(src) if n.endswith(".py")):
            lines = open(os.path.join(src, name), encoding="utf-8").read().split("\n")
            for i, ln in enumerate(lines):
                if '"X-Client-Key"' in ln and "hwid_headers()" not in "\n".join(lines[i:i + 3]):
                    miss.append("%s:%d" % (name, i + 1))
        self.assertEqual(miss, [])


if __name__ == "__main__":
    unittest.main()
