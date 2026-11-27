"""Блокировка при повреждённом config.json: если PIN-блокировка была включена (есть маркер lock.enabled), программа остаётся
закрытой (fail-closed); без маркера битый конфиг блокировку не включает. Сброс — удалением файла, названного в подсказке."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402
from test_lock_and_polish import _HttpMixin  # noqa: E402

M = load()


class LockCorruptConfigTests(unittest.TestCase, _HttpMixin):
    @classmethod
    def setUpClass(cls):
        cls._start_srv()

    @classmethod
    def tearDownClass(cls):
        cls._stop_srv()

    def setUp(self):
        self._good = M.load_config()
        self._old_unlocked = M._lock_unlocked[0]
        M.save_config(dict(self._good, lock_enabled=False, lock_pin_hash="", lock_pin_salt=""))
        M._lock_unlocked[0] = False
        M._lock_ok()
        self._rm()

    def tearDown(self):
        self._rm()
        M.save_config(self._good)
        M._lock_unlocked[0] = self._old_unlocked

    def _rm(self):
        try:
            os.remove(M.lock_marker_path())
        except OSError:
            pass

    def _break(self):
        with open(M.CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("{ это не json")

    def test_marker_follows_lock_setup(self):
        self.assertFalse(os.path.exists(M.lock_marker_path()))
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": True, "pin": "4321", "bio": False})[0], 200)
        self.assertTrue(os.path.exists(M.lock_marker_path()))
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": False, "current_pin": "4321"})[0], 200)
        self.assertFalse(os.path.exists(M.lock_marker_path()))

    def test_corrupt_config_with_marker_stays_locked_and_hint_reset_works(self):
        self.assertEqual(self.req("POST", "/api/lock/setup", {"enabled": True, "pin": "4321", "bio": True})[0], 200)
        self.req("POST", "/api/lock/now", {})
        self._break()
        code, st = self.req("GET", "/api/lock/status")
        self.assertEqual(code, 200)
        self.assertTrue(st["enabled"])
        self.assertFalse(st["unlocked"])
        self.assertTrue(st["config_corrupt"])
        self.assertIn(M.lock_marker_path(), st["reset_hint"])
        self.assertIn(M.CONFIG_PATH, st["reset_hint"])
        self.assertEqual(self.req("GET", "/api/config")[0], 423)
        self.assertEqual(self.req("POST", "/api/config", {"theme": "dark"})[0], 423)
        # ни PIN, ни биометрия не открывают; битый файл не перезаписывается
        self.assertEqual(self.req("POST", "/api/lock/unlock", {"pin": "4321"})[0], 403)
        old = M._bio_runner
        M._bio_runner = lambda reason: (True, "")
        try:
            self.assertEqual(self.req("POST", "/api/lock/unlock", {"method": "bio"})[0], 403)
        finally:
            M._bio_runner = old
        with open(M.CONFIG_PATH, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{ это не json")
        # сброс по подсказке: удалить маркер; база портфеля на месте
        os.remove(M.lock_marker_path())
        self.assertEqual(self.req("GET", "/api/lock/status")[1]["enabled"], False)
        self.assertEqual(self.req("GET", "/api/config")[0], 200)
        self.assertTrue(os.path.exists(M.DB_PATH))

    def test_corrupt_config_without_marker_does_not_lock(self):
        self._break()
        code, st = self.req("GET", "/api/lock/status")
        self.assertEqual(code, 200)
        self.assertFalse(st["enabled"])
        self.assertTrue(st["unlocked"])
        self.assertEqual(self.req("GET", "/api/config")[0], 200)

    def test_normal_hint_names_config_and_marker(self):
        h = self.req("GET", "/api/lock/status")[1]["reset_hint"]
        self.assertIn(M.CONFIG_PATH, h)
        self.assertIn(M.lock_marker_path(), h)


if __name__ == "__main__":
    unittest.main()
