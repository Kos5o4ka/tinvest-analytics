"""Привязка пробного периода к ПК на сервере (server/trial.py): второй аккаунт с тем же хэшем не сохраняет пробный. Офлайн."""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import trial as TR  # noqa: E402
import tinvest_server as ts  # noqa: E402

K1, K2 = "TIA-AAAA-AAAA-AAAA", "TIA-BBBB-BBBB-BBBB"
H1, H2 = "a" * 64, "b" * 64
NOW = 1000.0


class TrialHwid(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(tempfile.mkdtemp(prefix="ttrial_"), "keys.sqlite")
        db = sqlite3.connect(self.p)
        db.execute("CREATE TABLE users(tg_id INTEGER PRIMARY KEY, username TEXT, banned INTEGER NOT NULL DEFAULT 0, "
                   "plan TEXT NOT NULL DEFAULT 'free', plan_until REAL, trial_used INTEGER NOT NULL DEFAULT 0, pro_kind TEXT)")
        db.execute("CREATE TABLE keys(key_hash TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, "
                   "revoked INTEGER NOT NULL DEFAULT 0, last_used REAL)")
        for uid, k in ((1, K1), (2, K2)):
            db.execute("INSERT INTO users(tg_id, username, plan, plan_until, trial_used, pro_kind) VALUES (?,?, 'pro', ?, 1, 'trial')",
                       (uid, "u%d" % uid, NOW + 86400))
            db.execute("INSERT INTO keys VALUES (?,?,0,?,0,NULL)", (ts.key_hash(k), uid, NOW + 1e6))
        db.commit()
        db.close()
        self.ks = ts.KeyStore(self.p, clock=lambda: NOW)

    def info(self, k):
        return self.ks.lookup(k)[1]

    def test_second_account_same_pc_loses_trial(self):
        i1, b1 = TR.apply(self.ks, H1, self.info(K1), NOW)
        self.assertFalse(b1)
        self.assertTrue(i1["trial"])
        i2, b2 = TR.apply(self.ks, H1, self.info(K2), NOW)
        self.assertTrue(b2)
        self.assertEqual(i2["plan"], "free")
        self.assertFalse(i2["trial"])
        self.assertEqual(self.info(K2)["plan"], "free")                  # кэш сброшен, дальше тоже Free
        self.assertEqual(self.info(K1)["plan"], "pro")
        c = sqlite3.connect(self.p)
        self.assertEqual(c.execute("SELECT trial_used, plan_until, pro_kind FROM users WHERE tg_id=2").fetchone(), (1, None, None))
        self.assertEqual(c.execute("SELECT tg_id FROM trial_hwid WHERE hwid=?", (H1,)).fetchone()[0], 1)

    def test_owner_and_other_pc_unaffected(self):
        TR.apply(self.ks, H1, self.info(K1), NOW)
        _, b = TR.apply(self.ks, H1, self.info(K1), NOW)
        self.assertFalse(b)
        i2, b2 = TR.apply(self.ks, H2, self.info(K2), NOW)
        self.assertFalse(b2)
        self.assertTrue(i2["trial"])

    def test_no_hwid_or_bad_hwid_keeps_old_behaviour(self):
        for h in (None, "", "xyz", "A" * 10):
            i, b = TR.apply(self.ks, h, self.info(K2), NOW)
            self.assertFalse(b)
            self.assertTrue(i["trial"])
        c = sqlite3.connect(self.p)
        n = c.execute("SELECT name FROM sqlite_master WHERE name='trial_hwid'").fetchone()
        self.assertTrue(n is None or c.execute("SELECT COUNT(*) FROM trial_hwid").fetchone()[0] == 0)

    def test_paid_pro_not_revoked(self):
        c = sqlite3.connect(self.p)
        c.execute("UPDATE users SET pro_kind='pro' WHERE tg_id=2")
        c.commit()
        TR.apply(self.ks, H1, self.info(K1), NOW)
        self.ks._cache.clear()
        i2, _ = TR.apply(self.ks, H1, self.info(K2), NOW)
        self.assertEqual(i2["plan"], "pro")

    def test_params_defaults(self):
        os.environ.pop("TINVEST_PRO_PRICE_STARS", None)
        os.environ.pop("TINVEST_TRIAL_DAYS", None)
        self.assertEqual(TR.price_stars(), 0)
        self.assertEqual(TR.trial_days(), 7)
        self.assertIn("уже использован", TR.MSG_USED)


if __name__ == "__main__":
    unittest.main()
