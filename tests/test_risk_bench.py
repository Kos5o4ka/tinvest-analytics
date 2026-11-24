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


class RiskBondFlowsMode(unittest.TestCase):
    def test_build_risk_uses_maturity_flows_when_to_is_maturity(self):
        today = A.date.today()
        d_off = (today + A.timedelta(days=180)).isoformat()
        d_c2 = (today + A.timedelta(days=360)).isoformat()
        d_c3 = (today + A.timedelta(days=540)).isoformat()
        d_mat = (today + A.timedelta(days=730)).isoformat()
        bz = {
            "coupons": [
                {"coupondate": d_off, "value": 50.0},
                {"coupondate": d_c2, "value": 50.0},
                {"coupondate": d_c3, "value": 50.0},
                {"coupondate": d_mat, "value": 50.0},
            ],
            "amort": [],
            "offers": [{"offerdate": d_off, "offertype": "Оферта", "price": 100.0}],
        }
        rep = {
            "rows": [{
                "isin": "RU000TEST005", "name": "TestBond", "ticker": "TB5", "uid": "u5",
                "value_rub": 1000.0, "share": 100.0, "rating": None, "ytm": 25.0, "spread": 5.0,
                "dur": 1.6, "mdur": 1.4, "floating": False, "nominal": 1000.0,
                "end": d_mat, "maturity": d_mat, "to": "maturity", "cf_source": "moex",
            }]
        }
        old_bb, old_bz, old_kr, old_inf = A.build_bonds, A.moex_bondization, A.keyrate_forecast_info, A.inflation_forecast
        A.mem_clear()
        A.build_bonds = lambda cfg, acc: rep
        A.moex_bondization = lambda isin: bz
        A.keyrate_forecast_info = lambda kind="cbr": {"key_rate": 20.0, "path": [(today.isoformat(), 20.0), (d_c2, 20.0)], "source": "cbr", "source_name": "ЦБ"}
        A.inflation_forecast = lambda: {"source": "none", "yearly": []}
        try:
            res = A.build_risk({"sandbox": False, "token": ""}, "acc_calc05_mat")
        finally:
            A.build_bonds, A.moex_bondization, A.keyrate_forecast_info, A.inflation_forecast = old_bb, old_bz, old_kr, old_inf
        scn = res["rows"][0]["scn"]
        # При погашении через 2 года снижение ставки до 10% переоценивает тело после 365д выше, чем hold
        self.assertGreater(scn["fix10"]["total"], scn["hold"]["total"])
        # За первые 365д приходят оба купона (d_off и d_c2), а не только первый до оферты
        dirty_mat = A._bc_pv(A.bond_flows(bz, today.isoformat(), 1000.0, mode="maturity")[0], today.isoformat(), 0.25)
        self.assertAlmostEqual(scn["hold"]["coupons"], 100.0 / dirty_mat * 1000.0, places=4)

    def test_build_risk_respects_specific_offer_end_date(self):
        today = A.date.today()
        d_off1 = (today + A.timedelta(days=180)).isoformat()
        d_off2 = (today + A.timedelta(days=540)).isoformat()
        d_mat = (today + A.timedelta(days=730)).isoformat()
        bz = {
            "coupons": [
                {"coupondate": d_off1, "value": 50.0},
                {"coupondate": (today + A.timedelta(days=360)).isoformat(), "value": 50.0},
                {"coupondate": d_off2, "value": 50.0},
                {"coupondate": d_mat, "value": 50.0},
            ],
            "amort": [],
            "offers": [
                {"offerdate": d_off1, "offertype": "Оферта", "price": 100.0},
                {"offerdate": d_off2, "offertype": "Оферта", "price": 102.0},
            ],
        }
        rep = {
            "rows": [{
                "isin": "RU000TEST05B", "name": "TestBond2", "ticker": "TB5B", "uid": "u5b",
                "value_rub": 1000.0, "share": 100.0, "rating": None, "ytm": 25.0, "spread": 5.0,
                "dur": 1.3, "mdur": 1.1, "floating": False, "nominal": 1000.0,
                "end": d_off2, "maturity": d_mat, "to": "offer", "cf_source": "moex",
            }]
        }
        old_bb, old_bz, old_kr, old_inf = A.build_bonds, A.moex_bondization, A.keyrate_forecast_info, A.inflation_forecast
        A.mem_clear()
        A.build_bonds = lambda cfg, acc: rep
        A.moex_bondization = lambda isin: bz
        A.keyrate_forecast_info = lambda kind="cbr": {"key_rate": 20.0, "path": [(today.isoformat(), 20.0), (d_off2, 20.0)], "source": "cbr", "source_name": "ЦБ"}
        A.inflation_forecast = lambda: {"source": "none", "yearly": []}
        try:
            res = A.build_risk({"sandbox": False, "token": ""}, "acc_calc05_off")
        finally:
            A.build_bonds, A.moex_bondization, A.keyrate_forecast_info, A.inflation_forecast = old_bb, old_bz, old_kr, old_inf
        scn = res["rows"][0]["scn"]
        # Оферта d_off2 (+540д) > hd (+365д), поэтому rem не пуст и fix10 > hold
        self.assertGreater(scn["fix10"]["total"], scn["hold"]["total"])


if __name__ == "__main__":
    unittest.main()
