"""Матрица потоков на 36 месяцев и симулятор реинвестирования. Офлайн: сеть подменена."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


class Simulate(unittest.TestCase):
    def test_known_numbers(self):
        r = M.cf36_simulate([1000.0] * 36, 12.0)
        self.assertAlmostEqual(r["capital"][2], 1000 * 1.01 ** 2 + 1000 * 1.01 + 1000, places=6)
        self.assertAlmostEqual(r["capital"][2], 3030.10, places=2)
        self.assertEqual(r["capital_no"][2], 3000.0)
        self.assertAlmostEqual(r["diff"], r["final"] - 36000.0)
        self.assertAlmostEqual(r["interest"], r["diff"])
        self.assertGreater(r["interest"], 0)

    def test_no_reinvest_and_start(self):
        r = M.cf36_simulate([{"total": 100.0}, {"total": 0.0}, {"total": 50.0}], 20.0, start=1000.0, reinvest=False)
        self.assertEqual(r["capital"], [1100.0, 1100.0, 1150.0])
        self.assertEqual(r["interest"], 0.0)
        r2 = M.cf36_simulate([0, 0], 12.0, start=100.0)
        self.assertAlmostEqual(r2["final"], 100 * 1.01 ** 2)


class Bucket(unittest.TestCase):
    def test_36_months_with_empty(self):
        today = date(2026, 11, 22)
        keys = M.cf36_month_keys(today)
        self.assertEqual((len(keys), keys[0], keys[1], keys[-1]), (36, "2026-11", "2026-12", "2029-10"))
        pays = [{"date": "2026-12-10", "kind": "coupon", "amount": 100.0, "est": False, "name": "A"},
                {"date": "2026-12-20", "kind": "dividend", "amount": 50.0, "est": True, "name": "B"},
                {"date": "2029-10-31", "kind": "redemption", "amount": 1000.0, "est": False, "name": "A"},
                {"date": "2029-11-01", "kind": "coupon", "amount": 5.0, "est": False, "name": "A"}]     # за окном
        m = M.cf36_bucket(pays, today)
        self.assertEqual(len(m), 36)
        self.assertEqual(m[0]["total"], 0.0)
        self.assertEqual(m[1]["total"], 150.0)
        self.assertEqual(m[1]["est"], 50.0)
        self.assertEqual(m[1]["by"]["dividend"], 50.0)
        self.assertEqual(m[-1]["by"]["redemption"], 1000.0)
        self.assertEqual(sum(1 for x in m if x["total"] <= 0), 34)
        self.assertEqual(m[1]["top"][0]["name"], "A")

    def test_horizon(self):
        self.assertEqual(M.cf36_horizon_days(date(2026, 11, 22)), (date(2029, 11, 1) - date(2026, 11, 22)).days - 1)


class Report(unittest.TestCase):
    def _run(self, **kw):
        today = date.today()
        d = lambda n: (today + timedelta(days=n)).isoformat()
        b = {"nominal": 1000.0, "cur": "rub", "maturity": d(900), "call": None, "placement": d(-400), "cpy": 2, "aci": 5.0,
             "floating": False, "amort": False, "perpetual": False, "risk": "", "sector": "", "name": "T",
             "coupons": [[d(30), 40.0], [d(400), None], [d(700), None]]}
        saved = {k: getattr(M, k) for k in ("bond_info", "fx_now", "bond_exact", "keyrate_brief", "apply_ratings", "ratings_status")}
        M.bond_info = lambda c, u: dict(b)
        M.fx_now = lambda c, cs: {"rub": 1.0}
        M.bond_exact = lambda *a: None
        M.keyrate_brief = lambda: None
        M.apply_ratings = lambda rows: []
        M.ratings_status = lambda: {}
        row = {"uid": "u1", "ticker": "T1", "name": "Тест", "logo": "", "color": "", "type": "bond", "qty": 10.0, "avg": 990.0,
               "price": 995.0, "cur": "rub", "value": 10000.0, "value_rub": 10000.0, "pnl_rub": 0.0, "pnl_pct": 0.0}
        try:
            return M.bonds_report(object(), [row], **kw), d
        finally:
            for k, v in saved.items():
                setattr(M, k, v)

    def test_horizon_default_and_long(self):
        rep, d = self._run()
        self.assertEqual([p["kind"] for p in rep["payments"]], ["coupon"])          # 365 дней: только первый купон
        rep, d = self._run(horizon_days=1096)
        pays = rep["payments"]
        cps = [p for p in pays if p["kind"] == "coupon"]
        self.assertEqual([(p["date"], p["est"], p["amount"]) for p in cps],
                         [(d(30), False, 400.0), (d(400), True, 400.0), (d(700), True, 400.0)])    # None -> последний известный, est
        self.assertEqual(pays[-1]["kind"], "redemption")

    def test_payload_offline(self):
        today = date.today()
        names = ("build_summary", "bonds_report", "stock_dividends", "cf36_rates", "TInvest")
        saved = {k: getattr(M, k) for k in names}
        pos = [{"type": "share", "uid": "s1", "ticker": "SBER", "name": "Сбер", "qty": 100.0}]
        M.build_summary = lambda cfg, acc, per: {"portfolio": {"positions": pos}}
        M.bonds_report = lambda c, rows, horizon_days=365: {"payments": [
            {"date": (today + timedelta(days=5)).isoformat(), "kind": "coupon", "name": "X", "ticker": "X", "amount": 70.0, "est": False}]}
        M.TInvest = lambda cfg: object()
        rec = (today - timedelta(days=100))
        M.stock_dividends = lambda secid, price, uid=None, cfg=None: {"items": [
            {"record": rec.isoformat(), "payment": rec.isoformat(), "value": 30.0, "cur": "RUB"}]}
        M.cf36_rates = lambda: {"lqdt": 13.0, "ofz1y": 14.0}
        try:
            r = M.cashflow36_payload({"token": "t", "sandbox": False}, "all", True)
        finally:
            for k, v in saved.items():
                setattr(M, k, v)
        self.assertEqual(len(r["months"]), 36)
        self.assertGreaterEqual(r["est_dividends"], 2)
        self.assertAlmostEqual(r["est_total"], r["est_dividends"] * 30.0 * 100 * 0.87, places=2)
        est = [m for m in r["months"] if m["est"] > 0]
        self.assertTrue(all(abs(m["est"] - 2610.0) < 0.01 for m in est))
        self.assertEqual(len(r["empty_months"]), sum(1 for m in r["months"] if m["total"] <= 0))
        self.assertEqual(r["rates"]["lqdt"], 13.0)

    def test_dividend_failure_silent(self):
        saved = M.stock_dividends
        def boom(*a, **k):
            raise RuntimeError("net")
        M.stock_dividends = boom
        try:
            self.assertEqual(M.cf36_est_dividends([{"ticker": "X", "uid": "u", "qty": 1.0}], [], {}), [])
        finally:
            M.stock_dividends = saved


if __name__ == "__main__":
    unittest.main()
