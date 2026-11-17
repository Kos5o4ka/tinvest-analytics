"""Деньги и базис: годовая доходность, отставание от ставки, налог, базис с дивидендами, единицы контрактов. Офлайн."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


def daily(n, growth, end=date(2026, 11, 13), p0=2.0):
    """Ряд ежедневных цен длиной n+1 дней с постоянным дневным ростом growth."""
    d0 = end - timedelta(days=n)
    return [((d0 + timedelta(days=i)).isoformat(), p0 * (1 + growth) ** i) for i in range(n + 1)]


class Annualize(unittest.TestCase):
    def test_ann_formula(self):
        self.assertAlmostEqual(M.mm_ann(100, 110, 365), 10.0)
        self.assertAlmostEqual(M.mm_ann(100, 105, 182.5), (1.05 ** 2 - 1) * 100)
        self.assertIsNone(M.mm_ann(0, 110, 30))
        self.assertIsNone(M.mm_ann(100, 110, 0))

    def test_window_return(self):
        g = 0.14 / 365
        cs = daily(400, g)
        w = M.mm_window_return(cs, 91)
        self.assertEqual(w["days"], 91)
        self.assertAlmostEqual(w["ret"], ((1 + g) ** 365 - 1) * 100, places=6)

    def test_window_needs_history(self):
        cs = daily(40, 0.0003)
        self.assertIsNone(M.mm_window_return(cs, 365))
        self.assertIsNotNone(M.mm_window_return(cs, 30))


class Benchmark(unittest.TestCase):
    def test_rate_factor_constant(self):
        d0, d1 = date(2026, 1, 1), date(2026, 4, 2)          # 91 день
        rates = [("2025-12-01", 12.0)]
        f = M.mm_rate_factor(rates, d0, d1)
        self.assertAlmostEqual(f, (1 + 0.12 / 365) ** 91)
        self.assertAlmostEqual(M.mm_bench_ann(rates, d0, d1), ((1 + 0.12 / 365) ** 365 - 1) * 100, places=6)

    def test_rate_change_carried(self):
        d0, d1 = date(2026, 1, 1), date(2026, 1, 11)
        rates = [("2025-12-31", 10.0), ("2026-01-06", 20.0)]
        f = M.mm_rate_factor(rates, d0, d1)
        want = (1 + 0.10 / 365) ** 4 * (1 + 0.20 / 365) ** 6      # 2–5 января по 10 %, 6–11 по 20 %
        self.assertAlmostEqual(f, want)

    def test_rate_missing(self):
        self.assertIsNone(M.mm_rate_factor([], date(2026, 1, 1), date(2026, 2, 1)))
        self.assertIsNone(M.mm_rate_factor([("2026-03-01", 10.0)], date(2026, 1, 1), date(2026, 2, 1)))

    def test_gap(self):
        self.assertAlmostEqual(M.mm_gap(14.2, 14.7), -0.5)
        self.assertIsNone(M.mm_gap(None, 14.0))


class AfterTax(unittest.TestCase):
    def test_simple_13(self):
        r = M.mm_after_tax(1000000, 365, 10.0, 0.0, 2026)
        self.assertAlmostEqual(r["gross_gain"], 100000.0)
        self.assertAlmostEqual(r["tax"], 13000.0)
        self.assertAlmostEqual(r["net_gain"], 87000.0)
        self.assertAlmostEqual(r["net_ann"], 8.7)
        self.assertFalse(r["ldv"])

    def test_fee_reduces_base(self):
        r = M.mm_after_tax(1000000, 365, 10.0, 0.1, 2026)
        invested = 1000000 / 1.001
        proceeds = invested * 1.10
        sell = proceeds * 0.001
        base = proceeds - sell - 1000000
        self.assertAlmostEqual(r["tax"], base * 0.13, places=4)
        self.assertAlmostEqual(r["net_gain"], proceeds - sell - r["tax"] - 1000000, places=4)

    def test_progressive_15(self):
        r = M.mm_after_tax(30000000, 365, 10.0, 0.0, 2026)        # доход 3 млн, порог 2,4 млн
        self.assertAlmostEqual(r["tax"], 2400000 * 0.13 + 600000 * 0.15, places=4)

    def test_loss_no_tax(self):
        r = M.mm_after_tax(100000, 365, -5.0, 0.0, 2026)
        self.assertEqual(r["tax"], 0.0)
        self.assertLess(r["net_gain"], 0)

    def test_ldv_over_three_years(self):
        r = M.mm_after_tax(1000000, 4 * 365, 10.0, 0.0, 2026)
        self.assertTrue(r["ldv"])
        self.assertEqual(r["tax"], 0.0)                           # доход ~464 тыс. < 3 млн × 4
        r3 = M.mm_after_tax(1000000, 3 * 365, 10.0, 0.0, 2026)   # ровно три года — ещё без льготы
        self.assertFalse(r3["ldv"])
        self.assertGreater(r3["tax"], 0)

    def test_bad_input(self):
        self.assertIsNone(M.mm_after_tax(0, 365, 10))
        self.assertIsNone(M.mm_after_tax(1000, 0, 10))
        self.assertIsNone(M.mm_after_tax(1000, 365, None))


class Basis(unittest.TestCase):
    def test_annualization(self):
        # покупка 100 акций по 300 ₽, фьючерс 31 500 ₽ за 100 акций, 60 дней
        b = M.mm_basis(31500.0, 100, 300.0, 60)
        self.assertAlmostEqual(b["basis"], 1500.0)
        self.assertAlmostEqual(b["basis_pct"], 5.0)
        self.assertAlmostEqual(b["ann_raw"], 5.0 * 365 / 60)
        self.assertAlmostEqual(b["ann_adj"], b["ann_raw"])

    def test_dividend_adjustment(self):
        b = M.mm_basis(29800.0, 100, 300.0, 90, divs=10.0)         # базис −200 ₽, дивиденд 1000 ₽ на 100 акций
        self.assertAlmostEqual(b["basis"], -200.0)
        self.assertAlmostEqual(b["ann_raw"], -200 / 30000 * 100 * 365 / 90)
        self.assertAlmostEqual(b["pnl"], 800.0)
        self.assertAlmostEqual(b["ann_adj"], 800 / 30000 * 100 * 365 / 90)
        self.assertGreater(b["ann_adj"], b["ann_raw"])

    def test_return_on_capital_with_margin(self):
        b = M.mm_basis(31500.0, 100, 300.0, 73, margin=6000.0)
        self.assertAlmostEqual(b["capital"], 36000.0)
        self.assertAlmostEqual(b["ann_roc"], 1500 / 36000 * 100 * 5)
        self.assertLess(b["ann_roc"], b["ann_adj"])

    def test_invalid(self):
        self.assertIsNone(M.mm_basis(1000.0, 100, 10.0, 0))
        self.assertIsNone(M.mm_basis(1000.0, 100, 0, 30))


class Units(unittest.TestCase):
    def test_contract_rub(self):
        self.assertAlmostEqual(M.mm_contract_rub(30222, 1.0, 1.0), 30222.0)           # акции: цена за контракт
        self.assertAlmostEqual(M.mm_contract_rub(12.376, 1.0, 0.001), 12376.0)         # юань: цена за 1 CNY, шаг 0,001 = 1 ₽
        self.assertAlmostEqual(M.mm_contract_rub(3892.9, 8.25143, 0.1), 3892.9 * 82.5143)   # золото: USD/унция через курс шага
        self.assertIsNone(M.mm_contract_rub(100, None, 1))
        self.assertIsNone(M.mm_contract_rub(100, 1, 0))

    def _fx(self):
        secs = [
            {"SECID": "SRZ6", "SHORTNAME": "SBRF-12.26", "ASSETCODE": "SBRF", "LASTTRADEDATE": "2026-12-17", "PREVSETTLEPRICE": 29957, "LOTVOLUME": 100,
             "INITIALMARGIN": 5329.75, "MINSTEP": 1.0, "STEPPRICE": 1.0},
            {"SECID": "SRH7", "SHORTNAME": "SBRF-3.27", "ASSETCODE": "SBRF", "LASTTRADEDATE": "2027-03-18", "PREVSETTLEPRICE": 31011, "LOTVOLUME": 100,
             "INITIALMARGIN": 5988.72, "MINSTEP": 1.0, "STEPPRICE": 1.0},
            {"SECID": "SRM7", "SHORTNAME": "SBRF-6.27", "ASSETCODE": "SBRF", "LASTTRADEDATE": "2027-06-17", "PREVSETTLEPRICE": 32048, "LOTVOLUME": 100,
             "INITIALMARGIN": 6188.62, "MINSTEP": 1.0, "STEPPRICE": 1.0},
            {"SECID": "SBERF", "SHORTNAME": "SBERF", "ASSETCODE": "SBERF", "LASTTRADEDATE": "2100-01-01", "PREVSETTLEPRICE": 295.56, "LOTVOLUME": 100,
             "INITIALMARGIN": 5034.0, "MINSTEP": 0.01, "STEPPRICE": 1.0},
            {"SECID": "CRZ6", "SHORTNAME": "CNY-12.26", "ASSETCODE": "CNY", "LASTTRADEDATE": "2026-12-17", "PREVSETTLEPRICE": 12.54, "LOTVOLUME": 1000,
             "INITIALMARGIN": 1103.85, "MINSTEP": 0.001, "STEPPRICE": 1.0},
            {"SECID": "GDZ6", "SHORTNAME": "GOLD-12.26", "ASSETCODE": "GOLD", "LASTTRADEDATE": "2026-12-18", "PREVSETTLEPRICE": 3904.1, "LOTVOLUME": 1,
             "INITIALMARGIN": 24234.18, "MINSTEP": 0.1, "STEPPRICE": 8.25143},
            {"SECID": "SiZ6", "SHORTNAME": "Si-12.26", "ASSETCODE": "Si", "LASTTRADEDATE": "2026-12-17", "PREVSETTLEPRICE": 83568, "LOTVOLUME": 1000,
             "INITIALMARGIN": 12851.47, "MINSTEP": 1.0, "STEPPRICE": 1.0},
        ]
        md = {"SRZ6": {"SECID": "SRZ6", "LAST": 30222, "SETTLEPRICE": 30222, "VOLTODAY": 1000},
              "CRZ6": {"SECID": "CRZ6", "LAST": 12.375, "SETTLEPRICE": 12.376, "VOLTODAY": 0},
              "GDZ6": {"SECID": "GDZ6", "LAST": 3892.9, "SETTLEPRICE": 3892.6, "VOLTODAY": 5},
              "SiZ6": {"SECID": "SiZ6", "LAST": 82450, "SETTLEPRICE": 82460, "VOLTODAY": 5}}
        spots = {"SBER": 298.7, "GLDRUB_TOM": 10311.0, "USD000UTSTOM": 82.14, "CNYRUB_TOM": 12.258}
        return secs, md, spots

    def test_nearest_two_and_perpetual_skipped(self):
        secs, md, _ = self._fx()
        near = M.mm_nearest(secs, md, ("SBRF",), date(2026, 11, 17))
        self.assertEqual([r["secid"] for r in near], ["SRZ6", "SRH7"])
        self.assertEqual(near[0]["src"], "последняя сделка")
        self.assertEqual(near[1]["src"], "прошлая расчётная цена")
        self.assertEqual(M.mm_nearest(secs, md, ("SBERF",), date(2026, 11, 17)), [])
        # истёкший контракт не берётся
        self.assertEqual(M.mm_nearest(secs, md, ("SBRF",), date(2026, 12, 17))[0]["secid"], "SRH7")

    def test_price_choice_without_trades(self):
        p, src = M.mm_pick_price({"LAST": 12.375, "SETTLEPRICE": 12.376, "VOLTODAY": 0})
        self.assertEqual((p, src), (12.376, "расчётная цена"))

    def test_build_rows_units(self):
        secs, md, spots = self._fx()
        today = date(2026, 11, 17)
        calls = []

        def divs(sid, price, t, exp):
            calls.append(sid)
            return 5.0, [{"record": "2026-12-01", "value": 5.0}], True
        rows, skipped = M.mm_basis_build(secs, md, spots, 14.0, today, divs)
        by = {r["secid"]: r for r in rows}
        sb = by["SRZ6"]
        self.assertAlmostEqual(sb["f_unit"], 302.22)
        self.assertAlmostEqual(sb["basis"], 30222 - 29870.0)
        self.assertAlmostEqual(sb["div_total"], 500.0)
        self.assertEqual(sb["days"], 30)
        self.assertAlmostEqual(sb["ann_adj"], (30222 - 29870 + 500) / 29870 * 100 * 365 / 30)
        self.assertAlmostEqual(sb["excess"], sb["ann_adj"] - 14.0)
        cn = by["CRZ6"]                                     # юань: 12 376 ₽ за 1000 CNY против 12,258 × 1000
        self.assertAlmostEqual(cn["f_unit"], 12.376)
        self.assertAlmostEqual(cn["basis"], 12376 - 12258.0)
        gd = by["GDZ6"]                                     # золото: ₽ за унцию против ₽/г × 31,1035
        self.assertAlmostEqual(gd["f_unit"], 3892.9 * 82.5143, places=3)
        self.assertAlmostEqual(gd["spot_unit"], 10311 * 31.1034768)
        si = by["SiZ6"]                                     # Si: цена за контракт 1000 USD
        self.assertAlmostEqual(si["f_unit"], 82.45)
        self.assertAlmostEqual(si["basis"], 82450 - 82140.0)
        self.assertEqual(set(calls), {"SBER"})              # дивиденды запрашиваются только для акций
        self.assertEqual(by["CRZ6"]["divs"], [])

    def test_sanity_hides_bad_units(self):
        secs, md, spots = self._fx()
        spots["CNYRUB_TOM"] = 1.2258                         # единицы не сходятся: базис ~ +900 %
        rows, skipped = M.mm_basis_build(secs, md, spots, 14.0, date(2026, 11, 17), lambda *a: (0.0, [], True))
        self.assertNotIn("CRZ6", [r["secid"] for r in rows])
        self.assertTrue(any("не удалось согласовать" in s for s in skipped))

    def test_missing_spot_skipped(self):
        secs, md, spots = self._fx()
        spots.pop("USD000UTSTOM")
        rows, skipped = M.mm_basis_build(secs, md, spots, None, date(2026, 11, 17), lambda *a: (0.0, [], True))
        self.assertNotIn("SiZ6", [r["secid"] for r in rows])
        self.assertTrue(any("Доллар" in s for s in skipped))
        self.assertTrue(all(r["excess"] is None for r in rows))


class Endpoints(unittest.TestCase):
    def test_registered_and_graceful(self):
        self.assertIn("/api/mm/funds", M.API_GET)
        self.assertIn("/api/mm/basis", M.API_GET)
        old = M.mm_funds_base

        def boom():
            raise RuntimeError("нет сети")
        M.mm_funds_base = boom
        try:
            r = M.API_GET["/api/mm/funds"]({}, None, {}, False)
            self.assertIn("error", r)
        finally:
            M.mm_funds_base = old

    def test_funds_payload_with_stub(self):
        closes = daily(400, 0.14 / 365)
        fund = {"secid": "LQDT", "name": "Тест", "last": closes[-1][1], "last_date": closes[-1][0], "wins": {}}
        base = {"funds": [fund], "rusfar": 13.7, "rusfar_date": "2026-11-13", "key": 14.0, "key_date": "2026-11-13"}
        old = M.mm_funds_base
        oldk = M.kbd_at
        M.mm_funds_base = lambda: base
        M.kbd_at = lambda y: 13.0
        try:
            r = M.mm_funds_payload({"amount": "1000000", "days": "365", "save": "12"})
            self.assertEqual(r["selected"], "LQDT")
            kinds = [c["kind"] for c in r["compare"]]
            self.assertIn("save", kinds)
            self.assertEqual(kinds.count("ofz"), 3)
            sv = next(c for c in r["compare"] if c["kind"] == "save")
            self.assertAlmostEqual(sv["after"]["tax"], 120000 * 0.13, places=4)
            self.assertAlmostEqual(sv["after"]["net_ann"], 12 * 0.87, places=6)
        finally:
            M.mm_funds_base = old
            M.kbd_at = oldk


if __name__ == "__main__":
    unittest.main()
