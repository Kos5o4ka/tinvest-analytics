import unittest

from _load import load

A = load()


class RiskPd(unittest.TestCase):
    def test_market_pd(self):
        lam, p1, pT = A.risk_pd_market(4.2, 0.30, 3.0)
        self.assertAlmostEqual(lam, 0.06)
        self.assertAlmostEqual(p1, 1 - 2.718281828459045 ** -0.06)
        self.assertAlmostEqual(pT, 1 - 2.718281828459045 ** -0.18)

    def test_short_bond_and_edges(self):
        lam, p1, pT = A.risk_pd_market(3.0, 0.25, 0.5)
        self.assertAlmostEqual(p1, pT)
        self.assertEqual(A.risk_pd_market(None, 0.25, 1.0), (None, None, None))
        self.assertEqual(A.risk_pd_market(-1.0, 0.25, 2.0)[1], 0.0)

    def test_scale(self):
        self.assertEqual(A.risk_pd_scale(0.02, 2.0), 0.02)
        self.assertAlmostEqual(A.risk_pd_scale(0.02, 0.25), 1 - 0.98 ** 0.25)
        self.assertIsNone(A.risk_pd_scale(None, 0.5))

    def test_explain(self):
        rows = [{"value_rub": 300.0, "spread": 4.0, "ytm": 20.0, "pd_mkt_1y": 0.05, "pd_mkt_T": 0.1, "years": 2.0, "name": "A", "floating": False, "dur": 1.5},
                {"value_rub": 100.0, "spread": 0.0, "ytm": 15.0, "pd_mkt_1y": 0.0, "pd_mkt_T": 0.0, "years": 1.0, "name": "B", "floating": False},
                {"value_rub": 100.0, "spread": None, "ytm": 15.0, "pd_mkt_1y": None, "pd_mkt_T": None, "years": 1.0, "name": "C", "floating": False}]
        x = A.risk_pd_explain(rows, 0.2)
        self.assertEqual((x["count"], x["no_spread"]), (2, 1))
        self.assertAlmostEqual(x["spread"], 3.0)
        self.assertAlmostEqual(x["lam"], 3.75)
        self.assertEqual(x["example"]["name"], "A")
        self.assertAlmostEqual(x["example"]["kbd"], 16.0)
        self.assertEqual(A.risk_pd_explain([], 0.2)["count"], 0)


class BenchWindow(unittest.TestCase):
    def test_new_periods(self):
        days = [(A.date.today() - A.timedelta(days=n)).isoformat() for n in range(1200, -1, -1)]
        for per, n in (("6m", 182), ("3y", 1096)):
            self.assertIn(per, A.BENCH_PERIODS)
            i0, i1 = A._bn_window(days, per)
            self.assertEqual(i1, len(days) - 1)
            self.assertAlmostEqual(len(days) - 1 - i0, n + 1, delta=1)


if __name__ == "__main__":
    unittest.main()
