"""Лента техдефолтов: дата/обязательство/сумма по графику Мосбиржи, параметр scope. Без сети."""
import unittest
from unittest import mock

from _load import load

M = load()

BZ = {"ok": True,
      "coupons": [{"coupondate": "2026-08-10", "value": 10.0}, {"coupondate": "2026-09-10", "value": 11.0},
                  {"coupondate": "2026-10-10", "value": 12.0}, {"coupondate": "2026-12-10", "value": 13.0}],
      "amort": [{"amortdate": "2026-10-10", "value": 100.0}, {"amortdate": "2027-01-10", "value": 900.0}],
      "offers": [{"offerdate": "0000-00-00"}]}


class LastDue(unittest.TestCase):
    def test_coupon_plus_amort_same_day(self):
        r = M.dfl_last_due(BZ, 1000, "2026-11-18")
        self.assertEqual(r["date"], "2026-10-10")
        self.assertEqual(r["obligation"], "Купон №3 + амортизация")
        self.assertEqual(r["amount"], (12.0 + 100.0) * 1000)

    def test_coupon_only(self):
        r = M.dfl_last_due(BZ, 10, "2026-09-20")
        self.assertEqual((r["date"], r["obligation"], r["amount"]), ("2026-09-10", "Купон №2", 110.0))

    def test_redemption(self):
        r = M.dfl_last_due(BZ, 2, "2027-02-01")
        self.assertEqual(r["date"], "2027-01-10")
        self.assertEqual(r["obligation"], "Погашение")
        self.assertEqual(r["amount"], 1800.0)

    def test_no_qty_amount_none(self):
        self.assertIsNone(M.dfl_last_due(BZ, None, "2026-11-18")["amount"])

    def test_offer_and_empty(self):
        bz = {"coupons": [{"coupondate": "2026-01-01", "value": 5}], "amort": [], "offers": [{"offerdate": "2026-03-01"}]}
        r = M.dfl_last_due(bz, 1, "2026-06-01")
        self.assertEqual((r["date"], r["obligation"], r["amount"]), ("2026-03-01", "Оферта", None))
        self.assertIsNone(M.dfl_last_due(BZ, 1, "2026-01-01"))
        self.assertIsNone(M.dfl_last_due(None, 1, "2026-01-01"))


class Feed(unittest.TestCase):
    def _feed(self, **kw):
        with mock.patch.object(M, "ds_parsed", return_value=[]), \
                mock.patch.object(M, "_mon_flags", return_value={"tech": True, "default": False}), \
                mock.patch.object(M, "issuer_of", return_value={"short": "Эмит", "inn": "1"}), \
                mock.patch.object(M, "moex_bondization", return_value=BZ), \
                mock.patch.object(M, "_disc_issue_desc", return_value={"placed": 1000}):
            return M.defaults_feed("2026-01-01", ["RU000TEST001"], **kw)

    def test_schedule_row(self):
        r = self._feed(schedule=True)[0]
        self.assertTrue(r["date_est"])
        self.assertEqual(r["basis"], "Флаг Мосбиржи")
        self.assertEqual(r["date"], r["due_date"])
        self.assertIn("Купон", r["obligation"])
        self.assertTrue(r["amount"])

    def test_no_schedule_default_keeps_old_behaviour(self):
        r = self._feed()[0]
        self.assertIsNone(r["date"])
        self.assertFalse(r["date_est"])

    def test_message_row_wins(self):
        msg = [{"isin": "RU000TEST001", "published": "2026-11-01T10:00:00", "data": {"obligation": "coupon", "coupon_no": 3, "status": "technical"}}]
        with mock.patch.object(M, "ds_parsed", return_value=msg), \
                mock.patch.object(M, "_mon_flags", return_value={"tech": True, "default": False}), \
                mock.patch.object(M, "issuer_of", return_value={"short": "Эмит"}), \
                mock.patch.object(M, "_dfl_executed", return_value=None):
            rows = M.defaults_feed("2026-01-01", ["RU000TEST001"], schedule=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["basis"], "Сообщение эмитента")
        self.assertFalse(rows[0]["date_est"])


class Scope(unittest.TestCase):
    def _get(self, q, force=True):
        calls = {}

        def feed(since, isins, schedule=False):
            calls["isins"] = isins
            return [{"isin": "A", "date": "2026-11-01"}]
        mk = {"isins": ["MKT1"], "scan": {"running": True, "done": 5, "total": 10, "error": None}, "ts": None}
        with mock.patch.object(M, "defaults_feed", side_effect=feed), \
                mock.patch.object(M, "_disc_own_isins", return_value=["OWN1"]), \
                mock.patch.object(M, "dfl_market", return_value=mk) as dm:
            out = M.defaults_get({}, "all", q, force)
        return out, calls, dm

    def test_my(self):
        out, calls, dm = self._get({"scope": "my"})
        self.assertEqual(calls["isins"], ["OWN1"])
        self.assertNotIn("scan", out)
        dm.assert_not_called()

    def test_market(self):
        out, calls, dm = self._get({"scope": "market"})
        self.assertEqual(calls["isins"], ["OWN1", "MKT1"])
        self.assertEqual(out["scan"]["total"], 10)
        self.assertEqual(out["scope"], "market")
        self.assertTrue(out["rows"][0].get("mine") is False)

    def test_bad_scope_is_my(self):
        out, calls, _ = self._get({"scope": "zzz"})
        self.assertEqual(out["scope"], "my")


if __name__ == "__main__":
    unittest.main()
