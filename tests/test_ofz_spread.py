"""ОФЗ-Спредер: наклон, режим, премия за срок, кривизна, спред ОФЗ-ПД к КБД, исключения. Офлайн."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

T = load()


def curve(pts):
    """Кусочно-линейная КБД по точкам {лет: %}."""
    xs = sorted(pts)

    def f(t):
        if t <= xs[0]:
            return pts[xs[0]]
        for a, b in zip(xs, xs[1:]):
            if t <= b:
                return pts[a] + (pts[b] - pts[a]) * (t - a) / (b - a)
        return pts[xs[-1]]
    return f


NORMAL = curve({0.25: 10.0, 2: 10.5, 5: 11.5, 10: 12.5, 30: 13.0})
INVERTED = curve({0.25: 17.0, 1: 16.5, 2: 16.0, 5: 14.0, 10: 13.0, 30: 12.5})
HUMP = curve({0.25: 14.0, 1: 14.5, 2: 15.0, 5: 16.5, 10: 15.0, 30: 14.0})
TODAY = date(2026, 1, 15)


def bond(i, dur, y, **kw):
    r = {"id": i, "isin": "RU" + i, "name": i, "kind": "ofz", "dur": dur, "yield": y, "price": 90.0}
    r.update(kw)
    return r


class Regime(unittest.TestCase):
    def test_normal(self):
        r = T.ofz_spread_calc(NORMAL, [], TODAY)
        self.assertAlmostEqual(r["slope"], 2.0)
        self.assertEqual(r["regime_code"], "steep")
        self.assertTrue(all(x["bp"] > 0 for x in r["tp"]))

    def test_inverted(self):
        r = T.ofz_spread_calc(INVERTED, [], TODAY)
        self.assertAlmostEqual(r["slope"], -3.0)
        self.assertEqual(r["regime_code"], "deep_inv")
        self.assertLess(r["tp_far_avg"], 0)
        self.assertIn("снижения", r["regime_note"])
        self.assertIn("снижение ключевой ставки", r["verdict"])

    def test_boundaries(self):
        self.assertEqual(T.ofz_regime(-1.5)[0], "inv")
        self.assertEqual(T.ofz_regime(-1.51)[0], "deep_inv")
        self.assertEqual(T.ofz_regime(0)[0], "inv")
        self.assertEqual(T.ofz_regime(0.01)[0], "flat")
        self.assertEqual(T.ofz_regime(1)[0], "flat")
        self.assertEqual(T.ofz_regime(1.01)[0], "steep")


class Curvature(unittest.TestCase):
    def test_hump_prefers_bullet(self):
        r = T.ofz_spread_calc(HUMP, [], TODAY)
        self.assertAlmostEqual(r["curvature"], 2 * 16.5 - 15.0 - 15.0)
        self.assertEqual(r["structure"], "bullet")
        self.assertAlmostEqual(r["bullet"], 16.5)
        self.assertAlmostEqual(r["barbell"], (14.5 + 15.0) / 2)

    def test_dip_prefers_barbell(self):
        c = curve({0.25: 14.0, 1: 14.0, 2: 14.0, 5: 13.0, 10: 14.0, 30: 14.0})
        r = T.ofz_spread_calc(c, [], TODAY)
        self.assertLess(r["curvature"], 0)
        self.assertEqual(r["structure"], "barbell")

    def test_straight_neutral(self):
        r = T.ofz_spread_calc(curve({0.25: 10, 30: 10}), [], TODAY)
        self.assertEqual(r["structure"], "neutral")

    def test_tp_shape(self):
        r = T.ofz_spread_calc(NORMAL, [], TODAY)
        self.assertEqual([x["t"] for x in r["tp"]], list(range(1, 16)))
        t1 = r["tp"][0]["bp"]       # от 0,25 до 1 года
        self.assertAlmostEqual(t1, (NORMAL(1) - NORMAL(0.25)) * 100, places=1)
        self.assertEqual(r["curve"][0]["t"], 0.25)


class Bonds(unittest.TestCase):
    def test_spread_and_flags(self):
        k5 = NORMAL(5)
        rows = [bond("SU26240", 5.0, k5 + 0.40), bond("SU26238", 2.0, NORMAL(2) - 0.30), bond("SU26230", 8.0, NORMAL(8) + 0.05)]
        r = T.ofz_spread_calc(NORMAL, rows, TODAY)
        b = {x["id"]: x for x in r["bonds"]}
        self.assertAlmostEqual(b["SU26240"]["spread_bp"], 40.0, places=0)
        self.assertEqual(b["SU26240"]["flag"], "cheap")
        self.assertEqual(b["SU26238"]["flag"], "rich")
        self.assertIsNone(b["SU26230"]["flag"])
        self.assertEqual([x["id"] for x in r["bonds"]], ["SU26238", "SU26240", "SU26230"])   # по дюрации

    def test_exclusions(self):
        rows = [bond("SU26240", 5.0, 12.0),
                bond("SU52005", 4.0, 12.0),                       # линкер
                bond("SU24019", 3.0, 12.0),                       # ОФЗ-ПК
                bond("SU29006", 3.0, 12.0, btype="Облигации"),    # ОФЗ-ПК (29xxx)
                bond("SU26999", 3.0, 12.0, floating=True),
                bond("SU26111", 0.1, 12.0),                       # короче 0,25 года
                bond("SU26112", 3.0, None),                       # нет доходности
                bond("SU26113", None, 12.0),                      # нет дюрации
                bond("RU000A", 3.0, 12.0, kind="corp")]
        r = T.ofz_spread_calc(NORMAL, rows, TODAY)
        self.assertEqual([x["id"] for x in r["bonds"]], ["SU26240"])

    def test_curve_failure(self):
        r = T.ofz_spread_calc(lambda t: None, [bond("SU26240", 5.0, 12.0)], TODAY)
        self.assertFalse(r["ok"])
        self.assertIsNone(r["slope"])
        self.assertEqual(r["bonds"], [])

    def test_disclaimer(self):
        self.assertIn("не индивидуальная", T.ofz_spread_calc(NORMAL, [], TODAY)["disclaimer"])


if __name__ == "__main__":
    unittest.main()
