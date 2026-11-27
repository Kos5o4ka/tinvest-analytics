"""Тесты блокировки (PIN/биометрия), DPAPI, Store.close_all(), /api/app/shutdown, start_page/ui_prefs, VACUUM, crowd/log и неторговых активов."""
import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


class _HttpMixin:
    @classmethod
    def _start_srv(cls):
        cls.srv = M.LocalHTTPServer(("127.0.0.1", 0), M.Handler)
        threading.Thread(target=cls.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def _stop_srv(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": "127.0.0.1:%d" % self.port}
        raw = None
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
            h["Content-Length"] = str(len(raw))
        if headers:
            h.update(headers)
        c.request(method, path, body=raw, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            j = json.loads(data or b"{}")
        except ValueError:
            j = data
        return r.status, j


class LockTests(unittest.TestCase, _HttpMixin):
    @classmethod
    def setUpClass(cls):
        cls._start_srv()

    @classmethod
    def tearDownClass(cls):
        cls._stop_srv()

    def setUp(self):
        self._before = M.load_config()
        self._old_bio = M._bio_runner
        self._old_unlocked = M._lock_unlocked[0]
        cfg = M.load_config()
        cfg.update(lock_enabled=False, lock_bio=True, lock_pin_hash="", lock_pin_salt="")
        M.save_config(cfg)
        M._lock_unlocked[0] = False
        M._lock_ok()                        # счётчик неверных PIN не переносится между тестами

    def tearDown(self):
        M._bio_runner = self._old_bio
        M.save_config(self._before)
        M._lock_unlocked[0] = self._old_unlocked

    def test_defaults_and_secret_keys(self):
        self.assertIn("lock_pin_hash", M.SECRET_KEYS)
        self.assertIn("lock_pin_salt", M.SECRET_KEYS)
        self.assertFalse(M.DEFAULT_CONFIG["lock_enabled"])
        self.assertEqual(M.DEFAULT_CONFIG["start_page"], "dash")
        self.assertEqual(M.DEFAULT_CONFIG["ui_prefs"], {})
        code, st = self.req("GET", "/api/lock/status")
        self.assertEqual(code, 200)
        self.assertFalse(st["enabled"])
        self.assertTrue(st["unlocked"])
        self.assertFalse(st["has_pin"])

    def test_pin_setup_lock_423_and_unlock(self):
        # Короткий PIN и пустая настройка отклоняются
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": True, "pin": "123", "bio": False})[0], 400)
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": True, "bio": False})[0], 400)

        # Включение блокировки с PIN оставляет текущую сессию разблокированной
        code, res = self.req("POST", "/api/lock/setup", {"enabled": True, "pin": "4321", "bio": False})
        self.assertEqual(code, 200)
        self.assertTrue(res["enabled"] and res["unlocked"] and res["has_pin"])

        # Хэши PIN не попадают в /api/config и в бэкап
        cfg_code, cfg_pub = self.req("GET", "/api/config")
        self.assertEqual(cfg_code, 200)
        self.assertNotIn("lock_pin_hash", cfg_pub)
        self.assertNotIn("lock_pin_salt", cfg_pub)
        self.assertNotIn("4321", json.dumps(M.load_config()))

        # Блокируем вручную -> все /api/* (кроме разрешённых) отдают 423
        self.assertEqual(self.req("POST", "/api/lock/now", {}), (200, {"ok": True, "locked": True}))
        self.assertEqual(self.req("GET", "/api/lock/status")[1]["unlocked"], False)
        self.assertEqual(self.req("GET", "/api/ping")[0], 200)
        for method, path, body in (
            ("GET", "/api/config", None),
            ("GET", "/api/localdata", None),
            ("POST", "/api/config", {"theme": "dark"}),
            ("POST", "/api/lock/setup", {"enabled": False}),
        ):
            st, j = self.req(method, path, body)
            self.assertEqual(st, 423, (method, path))
            self.assertTrue(j.get("locked"))

        # Неверный PIN -> 403, верный PIN -> 200 и снова открыто
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"pin": "0000"})[0], 403)
        self.assertEqual(self.req("GET", "/api/config")[0], 423)
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"pin": "4321"}), (200, {"ok": True, "unlocked": True}))
        self.assertEqual(self.req("GET", "/api/config")[0], 200)

        # Проверка current_pin при смене/отключении
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": False, "current_pin": "9999"})[0], 403)
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": False, "current_pin": "4321"})[0], 200)
        self.assertEqual(self.req("GET", "/api/lock/status")[1]["enabled"], False)

    def test_bio_unlock_and_test_endpoint(self):
        # без PIN блокировку не включить (иначе без биометрии в программу не войти)
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": True, "bio": True})[0], 400)
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": True, "bio": True, "pin": "2468"})[0], 200)
        self.req("POST", "/api/lock/now", {})

        M._bio_runner = lambda reason: (False, "cancelled")
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"method": "bio"})[0], 403)
        self.assertTrue(M.lock_is_locked(M.load_config()))

        M._bio_runner = lambda reason: (True, "")
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"method": "bio"}), (200, {"ok": True, "unlocked": True}))
        self.assertFalse(M.lock_is_locked(M.load_config()))

        # /api/lock/bio проверяет биометрию, не меняя состояние блокировки
        M._bio_runner = lambda reason: (False, "no finger")
        self.assertEqual(self.req("POST", "/api/lock/bio", {}), (200, {"ok": False, "error": "no finger"}))
        self.assertFalse(M.lock_is_locked(M.load_config()))

        # При выключенной lock_bio биометрическая разблокировка запрещена
        self.assertEqual(self.req("POST", "/api/lock/setup", {"bio": False})[0], 403)          # без текущего PIN нельзя
        self.assertEqual(self.req("POST", "/api/lock/setup", {"bio": False, "current_pin": "2468"})[0], 200)
        self.req("POST", "/api/lock/now", {})
        M._bio_runner = lambda reason: (True, "")
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"method": "bio"})[0], 403)
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"pin": "2468"})[0], 200)

    def test_pin_bruteforce_throttled(self):
        M._lock_ok()
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": True, "pin": "5555"})[0], 200)
        self.req("POST", "/api/lock/now", {})
        codes = [self.req("POST", "/api/lock/unlock", {"pin": "0000"})[0] for _ in range(M.LOCK_FREE_TRIES + 1)]
        self.assertEqual(codes[:M.LOCK_FREE_TRIES], [403] * M.LOCK_FREE_TRIES)
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"pin": "5555"})[0], 429)   # даже верный PIN ждёт паузу
        M._lock_ok()
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"pin": "5555"})[0], 200)

    def test_backup_restore_keeps_lock(self):
        for k in ("lock_enabled", "lock_bio", "lock_pin_hash", "lock_pin_salt"):
            self.assertIn(k, M.BK_SKIP_RESTORE)

    def test_no_bio_env_and_startup_reset(self):
        old_env = os.environ.get("TINVEST_NO_BIO")
        os.environ["TINVEST_NO_BIO"] = "1"
        try:
            self.assertFalse(M.bio_available())
        finally:
            if old_env is None:
                os.environ.pop("TINVEST_NO_BIO", None)
            else:
                os.environ["TINVEST_NO_BIO"] = old_env
        M._lock_unlocked[0] = True
        M._lock_on_startup()
        self.assertFalse(M._lock_unlocked[0])


class ConfigPrefsTests(unittest.TestCase, _HttpMixin):
    @classmethod
    def setUpClass(cls):
        cls._start_srv()

    @classmethod
    def tearDownClass(cls):
        cls._stop_srv()

    def setUp(self):
        self._before = M.load_config()
        M._lock_unlocked[0] = False

    def tearDown(self):
        M.save_config(self._before)

    def test_start_page_and_ui_prefs(self):
        code, _ = self.req("POST", "/api/config", {
            "start_page": "bonds",
            "ui_prefs": {"compact": True, "rows": 50, "note": "hello"},
        })
        self.assertEqual(code, 200)
        cfg = M.load_config()
        self.assertEqual(cfg["start_page"], "bonds")
        self.assertEqual(cfg["ui_prefs"], {"compact": True, "rows": 50, "note": "hello"})

        # Неизвестная страница не затирает валидную, None удаляет ключ из ui_prefs
        code, _ = self.req("POST", "/api/config", {
            "start_page": "javascript:alert(1)",
            "ui_prefs": {"compact": None, "rows": 100},
        })
        self.assertEqual(code, 200)
        cfg2 = M.load_config()
        self.assertEqual(cfg2["start_page"], "bonds")
        self.assertEqual(cfg2["ui_prefs"], {"rows": 100, "note": "hello"})


class DpapiTests(unittest.TestCase):
    def test_dpapi_roundtrip_and_fallback(self):
        old_sys = M.platform.system
        old_win32 = M._dpapi_win32
        old_cfg_path = M.CONFIG_PATH
        tmp = tempfile.mkdtemp(prefix="dpapi_")
        M.CONFIG_PATH = os.path.join(tmp, "config.json")
        try:
            M.platform.system = lambda: "Windows"
            M._dpapi_win32 = lambda protect, raw: bytes(b ^ 0x5A for b in raw)
            cfg = dict(M.DEFAULT_CONFIG, token="t.SECRET_TOK", data_key="dk-123")
            M.save_config(cfg)
            disk = json.loads(open(M.CONFIG_PATH, encoding="utf-8").read())
            self.assertTrue(disk["token"].startswith("dpapi:"))
            self.assertTrue(disk["data_key"].startswith("dpapi:"))
            loaded = M.load_config()
            self.assertEqual(loaded["token"], "t.SECRET_TOK")
            self.assertEqual(loaded["data_key"], "dk-123")

            # Повторное сохранение не шифрует дважды
            M.save_config(loaded)
            loaded2 = M.load_config()
            self.assertEqual(loaded2["token"], "t.SECRET_TOK")

            # При ошибке CryptProtectData сохраняется открытым текстом без падения
            def fail_dpapi(protect, raw):
                raise OSError("dpapi down")
            M._dpapi_win32 = fail_dpapi
            M.save_config(dict(M.DEFAULT_CONFIG, token="t.PLAIN"))
            self.assertEqual(json.loads(open(M.CONFIG_PATH, encoding="utf-8").read())["token"], "t.PLAIN")
        finally:
            M.platform.system = old_sys
            M._dpapi_win32 = old_win32
            M.CONFIG_PATH = old_cfg_path

        # На не-Windows dpapi:-строка не ломает загрузку
        self.assertEqual(M._dpapi_unprotect("dpapi:AAAA"), "")


class StoreShutdownTests(unittest.TestCase, _HttpMixin):
    @classmethod
    def setUpClass(cls):
        cls._start_srv()

    @classmethod
    def tearDownClass(cls):
        cls._stop_srv()

    def test_store_close_all_closes_all_thread_conns(self):
        d = tempfile.mkdtemp(prefix="st_close_")
        st = M.Store(os.path.join(d, "test.db"))
        conns = [st.conn()]

        def worker():
            c = st.conn()
            c.execute("SELECT 1").fetchall()
            conns.append(c)

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        self.assertGreaterEqual(len(st._conns), 2)
        st.close_all()
        self.assertEqual(len(st._conns), 0)
        for c in conns:
            with self.assertRaises(sqlite3.ProgrammingError):
                c.execute("SELECT 1")

    def test_shutdown_endpoint_allowed_when_locked(self):
        before = M.load_config()
        called = []
        hook = lambda: called.append(1)
        M.SHUTDOWN_HOOKS.append(hook)
        try:
            M.save_config(dict(before, lock_enabled=True, lock_bio=True))
            M._lock_unlocked[0] = False
            code, res = self.req("POST", "/api/app/shutdown", {})
            self.assertEqual((code, res), (200, {"ok": True}))
            for _ in range(40):
                if called:
                    break
                time.sleep(0.02)
            self.assertEqual(called, [1])
        finally:
            if hook in M.SHUTDOWN_HOOKS:
                M.SHUTDOWN_HOOKS.remove(hook)
            M.save_config(before)
            M._lock_unlocked[0] = False


class LocalDataAndCrowdTests(unittest.TestCase, _HttpMixin):
    @classmethod
    def setUpClass(cls):
        cls._start_srv()

    @classmethod
    def tearDownClass(cls):
        cls._stop_srv()

    def test_vacuum_and_crowd_log(self):
        st = M.store()
        st.put("tmp_vac", {"blob": "x" * 20000})
        st.write("DELETE FROM kv WHERE k='tmp_vac'")
        code, res = self.req("POST", "/api/localdata/vacuum", {})
        self.assertEqual(code, 200)
        self.assertTrue(res["ok"])
        self.assertIn("freed", res)
        self.assertIn("parts", res["info"])

        st.put("crowd_stats", {"accepted": 7, "fetched": 9, "errors": 1})
        code2, log = self.req("GET", "/api/crowd/log")
        self.assertEqual(code2, 200)
        self.assertEqual(log["accepted"], 7)
        self.assertEqual(log["stats"]["fetched"], 9)


class ManualAssetExtTests(unittest.TestCase):
    def setUp(self):
        self.st = M.store()
        self._old = self.st.get("imports")
        self._old_ops = {a["id"]: self.st.ops(a["id"]) for a in self._old or []}
        for a in self._old or []:
            self.st.ops_clear(a["id"])
        self.st.put("imports", [])
        self.cfg = M.load_config()

    def tearDown(self):
        for a in M.imports_list():
            self.st.ops_clear(a["id"])
        self.st.put("imports", self._old or [])
        for aid, ops in self._old_ops.items():
            self.st.ops_put(aid, ops)
        M.mem_clear()

    def test_non_trading_assets_crud_and_fifo_safe(self):
        r1 = M.manual_post(self.cfg, {
            "kind": "asset_ext",
            "asset_kind": "deposit_bank",
            "name": "Вклад в Сбере",
            "amount": 500000,
            "rate": 19.5,
            "end_date": "2028-06-01",
            "acc_name": "Вне биржи",
        })
        acc, gid = r1["acc"], r1["group"]
        M.manual_post(self.cfg, {"kind": "asset_ext", "asset_kind": "cash_ext", "amount": 25000, "acc": acc})
        M.manual_post(self.cfg, {"kind": "asset_ext", "asset_kind": "real_estate", "name": "Квартира", "amount": 8500000, "acc": acc})

        rows = M.manual_list(self.cfg, "all", {"acc": acc}, False)["rows"]
        self.assertEqual(len(rows), 3)
        dep = next(r for r in rows if r["group"] == gid)
        self.assertEqual((dep["type"], dep["asset_kind"], dep["amount"], dep["rate"], dep["end_date"]),
                         ("asset_ext", "deposit_bank", 500000.0, 19.5, "2028-06-01"))

        # Редактирование
        M.manual_post(self.cfg, {
            "kind": "asset_ext", "asset_kind": "deposit_bank", "name": "Вклад в Сбере",
            "amount": 550000, "rate": 20.0, "end_date": "2028-06-01", "acc": acc, "group": gid,
        })
        dep2 = next(r for r in M.manual_list(self.cfg, "all", {"acc": acc}, False)["rows"] if r["group"] == gid)
        self.assertEqual((dep2["amount"], dep2["rate"]), (550000.0, 20.0))

        # fifo / imported_positions / analyze / build_summary не ломаются и не искажают кэш
        ops = self.st.ops(acc)
        self.assertEqual(M.fifo(ops), {})
        self.assertEqual(M.imported_positions(M._NoClient(), ops, {}), [])
        summ = M.build_summary(self.cfg, acc, "all")
        self.assertEqual(summ["portfolio"]["total"], 0.0)

        # Валидация
        for bad in (
            {"kind": "asset_ext", "asset_kind": "crypto", "amount": 100, "acc": acc},
            {"kind": "asset_ext", "asset_kind": "cash_ext", "amount": 0, "acc": acc},
            {"kind": "asset_ext", "asset_kind": "deposit_bank", "amount": 100, "end_date": "bad", "acc": acc},
        ):
            with self.assertRaises(M.ApiError):
                M.manual_post(self.cfg, bad)

        # Удаление
        self.assertEqual(M.manual_post(self.cfg, {"action": "delete", "acc": acc, "group": gid})["removed"], 1)
        self.assertEqual(len(M.manual_list(self.cfg, "all", {"acc": acc}, False)["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
