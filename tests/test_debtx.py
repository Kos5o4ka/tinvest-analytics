"""Долговой рынок: линкеры (Фишер), покрытие оферт, налог по валютным облигациям (офлайн)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

m = _load.load()
TODAY = date(2026, 1, 1)


class LinkerTest(unittest.TestCase):
    def test_fisher(self):
        self.assertAlmostEqual(m.dbx_fisher(14.0, 5.0), (1.14 / 1.05 - 1) * 100, 9)
        self.assertAlmostEqual(m.dbx_fisher(14.0, 5.0), 8.5714, 3)
        self.assertIsNone(m.dbx_fisher(None, 5.0))

    def test_avg_forecast(self):
        v, src = m.dbx_avg_forecast([{"year": 2026, "mid": 6.0}, {"year": 2027, "mid": 4.0}], 2.0, TODAY)
        self.assertEqual(src, "cbr")
        self.assertTrue(4.9 < v < 5.1)
        self.assertEqual(m.dbx_avg_forecast([], 3, TODAY), (4.0, "assumed"))


class OfferTest(unittest.TestCase):
    def test_grade(self):
        self.assertEqual(m.dbx_grade(1.5)[0], "high")
        self.assertEqual(m.dbx_grade(0.5)[0], "mid")
        self.assertEqual(m.dbx_grade(0.1)[0], "low")
        self.assertEqual(m.dbx_grade(None)[0], "nodata")
        self.assertEqual(m.dbx_grade(5.0, True)[0], "na")

    def test_candidates(self):
        rows = [{"id": "a", "kind": "corp", "cur": "RUB", "offer": "2026-06-01"}, {"id": "b", "kind": "corp", "cur": "RUB", "offer": "2026-03-01"},
                {"id": "c", "kind": "corp", "cur": "RUB", "offer": "2028-01-01"}, {"id": "d", "kind": "ofz", "cur": "RUB", "offer": "2026-03-01"},
                {"id": "e", "kind": "corp", "cur": "RUB", "offer": "2025-12-01"}]
        self.assertEqual([r["id"] for r in m.dbx_offer_candidates(rows, TODAY)], ["b", "a"])

    def test_fill_per_issuer(self):
        items = [{"id": "1", "inn": "7700000001", "volume": 5e9, "is_fin": False}, {"id": "2", "inn": "7700000001", "volume": 5e9, "is_fin": False},
                 {"id": "3", "inn": "7700000002", "volume": 1e9, "is_fin": True}]
        m.dbx_offer_fill(items, {"7700000001": {"cash": 6000.0, "year": 2024}, "7700000002": {"cash": 9000.0, "year": 2024}})
        self.assertAlmostEqual(items[0]["cover"], 1.2)
        self.assertAlmostEqual(items[0]["cover_all"], 0.6)      # деньги одни на обе оферты эмитента
        self.assertEqual(items[0]["grade"], "mid")
        self.assertEqual(items[2]["grade"], "na")


class FxTest(unittest.TestCase):
    def base(self, **kw):
        p = {"nominal": 1000.0, "price": 100.0, "coupon": 0.0, "freq": 2, "mat": date(2028, 1, 1), "buy_fx": 80.0, "qty": 100.0, "nkd": 0.0,
             "other": 0.0, "scenarios": [0, 20, -20]}
        p.update(kw)
        return p

    def test_zero_currency_return_but_tax(self):
        r = m.dbx_fx_calc(self.base(), TODAY)
        s0, s20, sm = r["scenarios"]
        self.assertEqual(s0["tax_rub"], 0)
        self.assertAlmostEqual(s20["profit_cur"], 0, 6)
        self.assertGreater(s20["tax_rub"], 0)
        self.assertTrue(s20["trap"])
        self.assertAlmostEqual(s20["base_rub"], 100000 * 80 * 0.2, 4)
        self.assertAlmostEqual(s20["tax_rub"], 100000 * 80 * 0.2 * 0.13, 4)
        self.assertLess(s20["post_cur"], 0)
        self.assertEqual(sm["tax_rub"], 0)       # убыток в рублях налога не даёт

    def test_coupons(self):
        r = m.dbx_fx_calc(self.base(coupon=6.0, scenarios=[0]), TODAY)
        self.assertEqual(r["n_coupons"], 4)
        s = r["scenarios"][0]
        self.assertAlmostEqual(s["base_rub"], 4 * 100000 * 0.03 * 80, 4)
        self.assertGreater(s["pre_cur"], s["post_cur"])
        self.assertAlmostEqual(s["pre_cur"], 6.0, delta=0.4)

    def test_progressive_threshold(self):
        self.assertAlmostEqual(m.tx_ndfl(2400000, 2026)[0], 2400000 * 0.13)
        self.assertAlmostEqual(m.tx_ndfl(3400000, 2026)[0], 2400000 * 0.13 + 1000000 * 0.15)
        r = m.dbx_fx_calc(self.base(other=2400000.0, scenarios=[20]), TODAY)
        self.assertAlmostEqual(r["scenarios"][0]["tax_rate"], 0.15, 6)

    def test_xirr(self):
        v = m.dbx_xirr([(date(2026, 1, 1), -100.0), (date(2027, 1, 1), 110.0)])
        self.assertAlmostEqual(v, 0.10, 4)
        self.assertIsNone(m.dbx_xirr([(date(2026, 1, 1), 100.0)]))


if __name__ == "__main__":
    unittest.main()
