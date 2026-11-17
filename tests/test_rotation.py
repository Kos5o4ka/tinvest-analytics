import unittest

from tests._load import load

M = load()


def flat(k):
    return M.rot_path("flat", k)


def par_bond(y, years=10.0):
    """Номинал 100, полугодовой купон y %, цена 100: потоки [(t, купон, номинал)]."""
    n = int(round(years * 2))
    return [((i + 1) / 2.0, y / 2.0, 100.0 if i == n - 1 else 0.0) for i in range(n)]


class TestRotationEngine(unittest.TestCase):
    def test_flat_case_floater_close_to_fixed(self):
        k0, y = 12.0, 14.0
        kn = flat(k0)
        for T in (1.0, 2.0, 3.0):
            fl = M.rot_tr_floater(kn, T, y - k0, tax=False)
            fx = M.rot_tr_fixed(kn, T, par_bond(y), 100.0, 0.0, tax=False)
            self.assertAlmostEqual(fl, fx, delta=0.6)
        self.assertAlmostEqual(M.rot_tr_floater(kn, 1.0, 2.0, tax=True) / M.rot_tr_floater(kn, 1.0, 2.0, tax=False), 0.87, delta=0.02)

    def test_monotone_in_cut(self):
        fl = par_bond(13.0)
        prev_fx, prev_fl = None, None
        for cut in (-2.0, 0.0, 2.0, 4.0, 6.0):
            kn = M.rot_path("cut", 15.0, cut=cut)
            fx = M.rot_tr_fixed(kn, 1.0, fl, 100.0, 0.0, tax=True)
            ff = M.rot_tr_floater(kn, 1.0, 2.0, tax=True)
            if prev_fx is not None:
                self.assertGreater(fx, prev_fx)
                self.assertLess(ff, prev_fl)
            prev_fx, prev_fl = fx, ff

    def test_breakeven_bisection(self):
        flows = par_bond(14.0, 12.0)
        fn = lambda kn, T: M.rot_tr_fixed(kn, T, flows, 100.0, 0.0, tax=True)
        be = M.rot_breakeven(16.0, 1.0, 1.0, fn, tax=True)
        self.assertEqual(be["state"], "ok")
        kn = M.rot_path("cut", 16.0, cut=be["value"])
        self.assertAlmostEqual(fn(kn, 1.0), M.rot_tr_floater(kn, 1.0, 1.0, True), delta=0.05)
        # слишком большой спред флоатера: фикс не догоняет
        self.assertEqual(M.rot_breakeven(16.0, 1.0, 1.0, fn, tax=True, hi=0.2)["state"], "never")

    def test_indicator_bounds(self):
        for k10, k1, key in ((30, 1, 1), (-30, 40, 40), (14, 15, 16), (12, 12, 12)):
            r = M.rot_indicator(k10, k1, key)
            self.assertTrue(0 <= r["score"] <= 100)
        self.assertEqual(M.rot_indicator(12, 12, 12)["score"], 50.0)
        self.assertIsNone(M.rot_indicator(None, 1, 1))

    def test_convexity_positive_and_duration(self):
        mac, md, cv = M.rot_dur_conv(par_bond(10.0, 10.0), 0.10)
        self.assertGreater(cv, 0)
        self.assertGreater(mac, md)
        self.assertLess(mac, 10.0)
        self.assertGreater(M.rot_value_change(md, cv, -0.01), -M.rot_value_change(md, cv, 0.01))     # выпуклость: рост цены больше падения

    def test_paths_and_floor(self):
        kn = M.rot_path("fast", 16.0)
        self.assertGreaterEqual(min(v for _, v in kn), M.ROT_FLOOR)
        self.assertEqual(kn[0][1], 16.0)
        self.assertIsNone(M.rot_path("cbr", 16.0, []))
        up = M.rot_path("up", 10.0)
        self.assertAlmostEqual(M.rot_rate(up, 2.0), 12.0)

    def test_ladder_and_lag(self):
        d = ["2026-12-01", "2027-02-01", "2027-03-01"]
        eq = M.rot_ladder(300000, 3, "equal", d, 6.0)
        self.assertAlmostEqual(sum(x["rub"] for x in eq), 300000, places=1)
        self.assertAlmostEqual(eq[-1]["duration"], 6.0)
        fr = M.rot_ladder(300000, 3, "front", d, 6.0)
        self.assertGreater(fr[0]["rub"], fr[-1]["rub"])
        r = {"id": "X", "name": "ПК", "kind": "corp", "coupon": 16.0, "price": 100.0, "yield": 16.0, "next": "2027-01-01"}
        kn = M.rot_path("smooth", 16.0, today="2026-11-17")
        out = M.rot_fl_lag(r, kn, 16.0, "2026-11-17")
        self.assertLess(out["avg12"], 16.0)
        self.assertLess(out["delta"], 0)

    def test_gap(self):
        rows = [{"name": "A", "value_rub": 600.0, "dur": 5.0, "mdur": 4.5, "convexity": 30.0, "ytm": 12.0},
                {"name": "F", "value_rub": 400.0, "dur": 3.0, "floating": True, "ytm": 15.0}]
        g = M.rot_gap(rows, 3.0)
        self.assertFalse(g["empty"])
        self.assertAlmostEqual(g["duration"], (600 * 5.0 + 400 * M.ROT_FL_DUR) / 1000)
        sc = {s["key"]: s["pct"] for s in g["scenarios"]}
        self.assertLess(sc["p+100"], 0)
        self.assertGreater(sc["p-100"], 0)
        self.assertGreater(sc["p+100"] + sc["p-100"], 0)       # асимметрия из-за выпуклости
        self.assertTrue(M.rot_gap([], 3.0)["empty"])



class RotBondFilterTests(unittest.TestCase):
    def test_only_ofz_pd(self):
        self.assertTrue(M._rot_is_pd({"id": "SU26238RMFS4", "name": "ОФЗ 26238"}))
        self.assertFalse(M._rot_is_pd({"id": "SU52005RMFS4", "name": "ОФЗ 52005"}))
        self.assertFalse(M._rot_is_pd({"id": "SU46020RMFS2", "name": "ОФЗ 46020"}))

    def test_synth_accrued_consistent(self):
        b = {"id": "X", "mat": "2041-05-15", "coupon": 7.1, "nominal": 1000, "price": 51.23, "yield": 16.35, "nkd": 35.0}
        orig = M.rot_flows_moex
        M.rot_flows_moex = lambda *a, **k: None
        try:
            fm = M.rot_fixed_model(b, "2026-11-17")
        finally:
            M.rot_flows_moex = orig
        self.assertEqual(fm["method"], "synth")
        self.assertAlmostEqual(fm["accr"], M.rot_accr(fm["flows"], 0.0))


if __name__ == "__main__":
    unittest.main()
