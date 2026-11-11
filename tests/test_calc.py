"""Тесты расчётов на известных ответах. Без сети: python3 -m unittest discover -s tests -v"""
import ast
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import ROOT, load  # noqa: E402

M = load()
BULLET = [("2027-01-01", 100.0, 0.0), ("2028-01-01", 100.0, 1000.0)]     # 2 года, купон 10%, от 2026-01-01 ровно 365 и 730 дней
T0 = "2026-01-01"


class Ytm(unittest.TestCase):
    def test_par_bullet(self):
        self.assertAlmostEqual(M.cf_ytm(1000.0, BULLET, T0), 0.10, places=6)

    def test_discount_pv_matches(self):
        y = M.cf_ytm(900.0, BULLET, T0)
        pv = 100 / (1 + y) + 1100 / (1 + y) ** 2
        self.assertAlmostEqual(pv, 900.0, places=3)
        self.assertGreater(y, 0.10)

    def test_zero_coupon(self):
        fl = [("2028-01-01", 0.0, 1000.0)]
        self.assertAlmostEqual(M.cf_ytm(800.0, fl, T0), (1000 / 800.0) ** 0.5 - 1, places=6)

    def test_amortizing_at_par(self):
        # купон 10% на остаток, номинал гасится двумя равными частями: по номиналу доходность = купону
        fl = [("2027-01-01", 100.0, 500.0), ("2028-01-01", 50.0, 500.0)]
        self.assertAlmostEqual(M.cf_ytm(1000.0, fl, T0), 0.10, places=6)

    def test_no_root_and_empty(self):
        self.assertIsNone(M.cf_ytm(1000.0, [], T0))
        self.assertIsNone(M.cf_ytm(0.0, BULLET, T0))

    def test_tax_lowers_yield(self):
        y = M.cf_ytm(1000.0, BULLET, T0)
        yt = M.cf_ytm(1000.0, BULLET, T0, tax=True, basis=1000.0)
        self.assertAlmostEqual(yt, 0.087, places=5)       # купоны 100 -> 87, налога на погашении нет
        self.assertLess(yt, y)


class Risk(unittest.TestCase):
    def test_duration_formula(self):
        y = 0.10
        mac, mod, conv = M.cf_risk(BULLET, T0, y)
        pv1, pv2 = 100 / 1.1, 1100 / 1.21
        tot = pv1 + pv2
        self.assertAlmostEqual(mac, (1 * pv1 + 2 * pv2) / tot, places=9)
        self.assertAlmostEqual(mod, mac / 1.1, places=9)
        self.assertAlmostEqual(conv, (1 * 2 * pv1 + 2 * 3 * pv2) / tot / 1.21, places=9)

    def test_zero_coupon_duration_equals_maturity(self):
        mac, _, _ = M.cf_risk([("2028-01-01", 0.0, 1000.0)], T0, 0.08)
        self.assertAlmostEqual(mac, 2.0, places=9)


class Stress(unittest.TestCase):
    def test_sign_and_convexity(self):
        st = M.stress(100.0, BULLET, T0, 1000.0, 0.0)
        for dy in (1, 2, 3):
            self.assertLess(st[dy], 100.0)
        for dy in (-1, -2, -3):
            self.assertGreater(st[dy], 100.0)
        self.assertGreater(st[-1] - 100.0, 100.0 - st[1])            # выпуклость: рост цены при -1 п.п. больше падения при +1
        mac, mod, conv = M.cf_risk(BULLET, T0, 0.10)
        self.assertAlmostEqual(st[1] - 100.0, -mod * 1 + 0.5 * conv * 1e-2 * 1, delta=0.05)

    def test_exact_repricing(self):
        st = M.stress(100.0, BULLET, T0, 1000.0, 0.0)
        y = 0.11
        self.assertAlmostEqual(st[1], (100 / (1 + y) + 1100 / (1 + y) ** 2) / 10.0, places=6)


class Flows(unittest.TestCase):
    def bz(self, offers=None, amort=None):
        cps = [("2026-06-01", 50.0), ("2026-12-01", 50.0), ("2027-06-01", 50.0), ("2027-12-01", 50.0)]
        return {"coupons": [{"coupondate": d, "value": v, "valueprc": None} for d, v in cps],
                "amort": [{"amortdate": d, "value": v} for d, v in (amort or [])],
                "offers": offers or []}

    def test_plain_maturity(self):
        fl, kind, end = M.bond_flows(self.bz(), "2026-03-01", 1000.0)
        self.assertEqual((kind, end), ("maturity", "2027-12-01"))
        self.assertEqual(sum(p for _, _, p in fl), 1000.0)
        self.assertEqual(fl[-1], ("2027-12-01", 50.0, 1000.0))

    def test_offer_cut_with_accrued(self):
        off = [{"offerdate": "2027-01-01", "price": 100.0, "offertype": "Оферта на выкуп"}]
        fl, kind, end = M.bond_flows(self.bz(off), "2026-03-01", 1000.0)
        self.assertEqual((kind, end), ("offer", "2027-01-01"))
        self.assertEqual(fl[-1][0], "2027-01-01")
        self.assertAlmostEqual(fl[-1][2], 1000.0)
        self.assertAlmostEqual(fl[-1][1], 50.0 * 31 / 182, places=6)         # НКД на дату оферты
        self.assertTrue(all(d <= end for d, _, _ in fl))
        fl2, kind2, end2 = M.bond_flows(self.bz(off), "2026-03-01", 1000.0, mode="maturity")
        self.assertEqual((kind2, end2), ("maturity", "2027-12-01"))

    def test_offer_price_below_par(self):
        off = [{"offerdate": "2027-01-01", "price": 99.0, "offertype": "Оферта"}]
        fl, _, _ = M.bond_flows(self.bz(off), "2026-03-01", 1000.0)
        self.assertAlmostEqual(fl[-1][2], 990.0)

    def test_amortization(self):
        fl, kind, end = M.bond_flows(self.bz(amort=[("2026-12-01", 300.0), ("2027-06-01", 300.0)]), "2026-03-01", 1000.0)
        prin = {d: p for d, _, p in fl if p}
        self.assertEqual(prin, {"2026-12-01": 300.0, "2027-06-01": 300.0, "2027-12-01": 400.0})
        self.assertEqual(kind, "maturity")

    def test_amort_past_reduces_nothing_future(self):
        fl, _, _ = M.bond_flows(self.bz(amort=[("2026-01-15", 100.0)]), "2026-03-01", 900.0)
        self.assertEqual(sum(p for _, _, p in fl), 900.0)

    def test_inconsistent_amort_rejected(self):
        fl, kind, end = M.bond_flows(self.bz(amort=[("2026-12-01", 1500.0)]), "2026-03-01", 1000.0)
        self.assertIsNone(fl)


class Floater(unittest.TestCase):
    def setUp(self):
        self._o = (M.key_rate_series, M.keyrate_path)
        M.key_rate_series = lambda: [["2025-01-01", 10.0]]
        M.keyrate_path = lambda: [("2026-06-15", 10.0), ("2027-06-15", 8.0)]

    def tearDown(self):
        M.key_rate_series, M.keyrate_path = self._o

    def bz(self):
        known = ["2025-06-01", "2025-09-01", "2025-12-01", "2026-03-01", "2026-06-01"]
        cps = [{"coupondate": d, "value": 30.0, "valueprc": 12.0} for d in known]
        cps += [{"coupondate": "2026-09-01", "value": None, "valueprc": None},
                {"coupondate": "2026-12-01", "value": None, "valueprc": None}]
        return {"coupons": cps, "amort": [], "offers": []}

    def test_forecast(self):
        est = M.fl_estimates(self.bz(), "2026-06-15", 1000.0)
        self.assertEqual(sorted(est), ["2026-09-01", "2026-12-01"])
        self.assertAlmostEqual(est["2026-09-01"]["spread"], 2.0)
        self.assertAlmostEqual(est["2026-09-01"]["rate"], 12.0)                       # период уже идёт: факт 10% + спред 2
        self.assertAlmostEqual(est["2026-09-01"]["amt"], 12.0 / 100 * 1000 * 92 / 365.0, places=6)
        base2 = 10.0 - 2.0 * 78 / 365.0                                              # линейно по пути прогноза
        self.assertAlmostEqual(est["2026-12-01"]["base"], base2, places=6)
        self.assertAlmostEqual(est["2026-12-01"]["amt"], (base2 + 2.0) / 100 * 1000 * 91 / 365.0, places=6)

    def test_in_flows(self):
        out = {}
        fl, _, _ = M.bond_flows(self.bz(), "2026-06-15", 1000.0, floating=True, est_out=out)
        self.assertEqual(sorted(out), ["2026-09-01", "2026-12-01"])
        cp = {d: c for d, c, _ in fl}
        self.assertAlmostEqual(cp["2026-09-01"], out["2026-09-01"]["amt"])

    def test_not_floating_uses_last_known(self):
        fl, _, _ = M.bond_flows(self.bz(), "2026-06-15", 1000.0, floating=False)
        self.assertAlmostEqual(dict((d, c) for d, c, _ in fl)["2026-09-01"], 30.0)

    def test_no_series(self):
        M.key_rate_series = lambda: []
        self.assertEqual(M.fl_estimates(self.bz(), "2026-06-15", 1000.0), {})


class Portfolio(unittest.TestCase):
    def test_irr(self):
        ex = {"dirty": 1000.0, "flows": BULLET, "basis": 1000.0}
        r = M.portfolio_irr([(ex, 2, 1.0)], T0)
        self.assertAlmostEqual(r["irr"], 10.0, places=4)
        self.assertAlmostEqual(r["irr_tax"], 8.7, places=3)
        self.assertEqual((r["count"], r["value"]), (1, 2000.0))

    def test_two_bonds_between(self):
        a = {"dirty": 1000.0, "flows": BULLET, "basis": 1000.0}
        b = {"dirty": 1000.0, "flows": [("2027-01-01", 160.0, 0.0), ("2028-01-01", 160.0, 1000.0)], "basis": 1000.0}
        r = M.portfolio_irr([(a, 1, 1.0), (b, 1, 1.0)], T0)
        self.assertTrue(10.0 < r["irr"] < 16.0)

    def test_fx_multiplier(self):
        ex = {"dirty": 100.0, "flows": [("2027-01-01", 5.0, 100.0)], "basis": 100.0}
        r = M.portfolio_irr([(ex, 10, 90.0)], T0)
        self.assertAlmostEqual(r["irr"], 5.0, places=4)
        self.assertAlmostEqual(r["value"], 100.0 * 10 * 90.0)


class Nkd(unittest.TestCase):
    def test_linear(self):
        b = {"coupons": [["2026-01-01", 50.0], ["2026-07-01", 50.0]], "placement": "2025-07-01"}
        self.assertAlmostEqual(M.nkd_at(b, "2026-04-01"), 50.0 * 90 / 181)
        self.assertAlmostEqual(M.nkd_at(b, "2026-01-01"), 0.0)                      # в день выплаты НКД обнуляется
        self.assertEqual(M.nkd_at(b, "2026-08-01"), 0.0)

    def test_unknown_coupon_uses_last_known(self):
        b = {"coupons": [["2026-01-01", 40.0], ["2026-07-01", 0.0]], "placement": "2025-07-01"}
        self.assertAlmostEqual(M.nkd_at(b, "2026-04-01"), 40.0 * 90 / 181)

    def test_empty(self):
        self.assertEqual(M.nkd_at({"coupons": []}, "2026-01-01"), 0.0)


class Ratings(unittest.TestCase):
    def test_posts(self):
        r = M.parse_rating_post("АКРА присвоило ПАО «Селигдар» кредитный рейтинг A-(RU), прогноз «Стабильный»")
        self.assertEqual((r["agency"], r["rating"], r["outlook"]), ("АКРА", "A-", "стабильный"))
        self.assertIn("Селигдар", r["issuer"])
        r = M.parse_rating_post("Эксперт РА подтвердил кредитный рейтинг ООО «Балтийский лизинг» на уровне ruA, прогноз «Негативный»")
        self.assertEqual((r["agency"], r["rating"], r["outlook"]), ("Эксперт РА", "A", "негативный"))
        r = M.parse_rating_post("НКР присвоил АО «Европлан» кредитный рейтинг AA.ru, прогноз «Позитивный»")
        self.assertEqual((r["agency"], r["rating"], r["outlook"]), ("НКР", "AA", "позитивный"))

    def test_withdrawn_and_noise(self):
        r = M.parse_rating_post("АКРА отозвало кредитный рейтинг ООО «Тест Финанс»")
        self.assertTrue(r and r.get("withdrawn"))
        self.assertIsNone(M.parse_rating_post("Привет, это не рейтинговый пост"))
        self.assertIsNone(M.parse_rating_post("АКРА присвоило ожидаемый рейтинг облигациям ПАО «Тест» ruAA(RU) серии 01"))


class Calendar(unittest.TestCase):
    """bonds_report: прогноз купонов флоатера, амортизация и остаток при погашении (без сети: подмена зависимостей)."""

    def test_payments(self):
        today = M.date.today()
        d = lambda n: (today + M.timedelta(days=n)).isoformat()
        mat = d(300)
        b = {"nominal": 1000.0, "cur": "rub", "maturity": mat, "call": None, "placement": d(-400), "cpy": 4, "aci": 5.0,
             "floating": True, "amort": True, "perpetual": False, "risk": "", "sector": "", "name": "T",
             "coupons": [[d(-60), 30.0], [d(30), 0.0], [d(120), 0.0]]}
        bz = {"amort": [{"amortdate": d(200), "value": 250.0}, {"amortdate": mat, "value": 750.0}]}
        flows = [(d(30), 30.0, 0.0), (d(120), 30.0, 0.0), (d(200), 20.0, 250.0), (mat, 10.0, 750.0)]
        ex = {"isin": "RU000TEST", "ytm": 15.0, "ytm_tax": 13.0, "dur": 0.5, "mdur": 0.45, "convexity": 0.5, "to": "maturity",
              "end": mat, "stress_pct": {}, "cf_source": "moex", "est_coupons": 2, "flows": flows, "basis": 990.0,
              "dirty": 1000.0, "bz": bz,
              "est_detail": {d(30): {"amt": 31.0}, d(120): {"amt": 29.0}}}
        saved = {k: getattr(M, k) for k in ("bond_info", "fx_now", "bond_exact", "keyrate_brief", "apply_ratings", "ratings_status")}
        M.bond_info = lambda c, u: dict(b)
        M.fx_now = lambda c, cs: {"rub": 1.0}
        M.bond_exact = lambda *a: ex
        M.keyrate_brief = lambda: None
        M.apply_ratings = lambda rows: []
        M.ratings_status = lambda: {}
        try:
            row = {"uid": "u1", "ticker": "T1", "name": "Тест", "logo": "", "color": "", "type": "bond", "qty": 10.0, "avg": 990.0,
                   "price": 995.0, "cur": "rub", "value": 10000.0, "value_rub": 10000.0, "pnl_rub": 0.0, "pnl_pct": 0.0}
            rep = M.bonds_report(object(), [row])
        finally:
            for k, v in saved.items():
                setattr(M, k, v)
        pays = rep["payments"]
        cp = [p for p in pays if p["kind"] == "coupon"]
        self.assertEqual([(p["date"], p["est"], round(p["amount"], 2)) for p in cp],
                         [(d(30), "forecast", 310.0), (d(120), "forecast", 290.0)])
        am = [p for p in pays if p["kind"] == "amortization"]
        self.assertEqual([(p["date"], p["amount"]) for p in am], [(d(200), 2500.0)])
        red = [p for p in pays if p["kind"] == "redemption"]
        self.assertEqual([(p["date"], p["amount"]) for p in red], [(mat, 7500.0)])       # без дублирования амортизации
        self.assertAlmostEqual(sum(p["amount"] for p in pays if p["kind"] != "coupon"), 10000.0)


class Compat(unittest.TestCase):
    def test_python38_syntax(self):
        for name in ("tinvest_analytics.py", "tinvest.py"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                ast.parse(f.read(), filename=name, feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main()


class IncomeGoal(unittest.TestCase):
    def test_capital_needed(self):
        r = M.goal_calc(50000, 120, 13.0, 0.0, 0.0, False)           # доходность 13 % до налога = 11,31 % после
        self.assertAlmostEqual(r["capital_today"], 50000 * 12 / (0.13 * 0.87), places=4)
        self.assertAlmostEqual(r["capital_end"], r["capital_today"])

    def test_contribution_reaches_target(self):
        r = M.goal_calc(50000, 120, 13.0, 1000000.0, 0.0, False)
        yn, n = 0.13 * 0.87, 120
        rm = (1 + yn) ** (1 / 12.0) - 1
        fv = 1000000.0 * (1 + rm) ** n + r["contribution"] * ((1 + rm) ** n - 1) / rm
        self.assertAlmostEqual(fv, r["capital_end"], places=3)
        self.assertAlmostEqual(r["chart"]["capital"][-1], r["capital_end"], places=3)
        self.assertGreater(r["contribution"], 0)
        self.assertEqual(r["chart"]["labels"][0], date.today().strftime("%Y-%m"))

    def test_already_reached(self):
        r = M.goal_calc(10000, 60, 12.0, 5000000.0, 0.0, False)
        self.assertTrue(r["reached"])
        self.assertEqual(r["contribution"], 0.0)

    def test_inflation_adjustment(self):
        a = M.goal_calc(50000, 120, 13.0, 0.0, 8.0, True)
        b = M.goal_calc(50000, 120, 13.0, 0.0, 8.0, False)
        self.assertAlmostEqual(a["goal_end"], 50000 * 1.08 ** 10, places=4)
        self.assertAlmostEqual(a["capital_end"], a["capital_today"] * 1.08 ** 10, places=3)
        self.assertAlmostEqual(b["capital_end"], b["capital_today"])
        self.assertGreater(a["contribution"], b["contribution"])

    def test_coverage_and_validation(self):
        r = M.goal_calc(100000, 60, 14.0, 0.0, 0.0, False, income_now=25000.0)
        self.assertAlmostEqual(r["coverage"]["pct"], 25.0)
        with self.assertRaises(ValueError):
            M.goal_calc(1000, 0, 10.0)
        with self.assertRaises(ValueError):
            M.goal_calc(1000, 12, 0.0)

    def test_months_and_endpoint_without_token(self):
        self.assertEqual(M.goal_months({"years": "2.5"}), 30)
        with self.assertRaises(ValueError):
            M.goal_months({"date": "2000-01-01"})
        out = M.calc_goal_get({}, "all", {"monthly": "80000", "years": "8", "yield": "14", "value": "300000", "real": "0"})
        self.assertIsNone(out["error"])
        self.assertAlmostEqual(out["result"]["capital_today"], 80000 * 12 / (0.14 * 0.87), places=3)
        self.assertEqual(M.calc_goal_get({}, "all", {"monthly": "80000", "years": "8"})["result"], None)
        self.assertIn("доходность", M.calc_goal_get({}, "all", {"monthly": "80000", "years": "8"})["error"])
