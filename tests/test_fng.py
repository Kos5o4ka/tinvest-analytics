"""Индекс страха и жадности: процентный ранг, компоненты на синтетических рядах, перенормировка, границы меток, форма ответа. Офлайн."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


def days(n, end=None):
    end = end or date(2026, 11, 13)
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def series(vals, ds=None):
    ds = ds or days(len(vals))
    return dict(zip(ds, vals))


class Pct(unittest.TestCase):
    def test_rank(self):
        self.assertEqual(M.fng_pct(5, [1, 2, 3, 4, 5]), 90.0)      # 4 меньше + половина равных (1 из 5)
        self.assertEqual(M.fng_pct(1, [1, 2, 3, 4]), 12.5)
        self.assertEqual(M.fng_pct(7, [7]), 50.0)
        self.assertIsNone(M.fng_pct(1, []))

    def test_score_invert_and_min_points(self):
        ds = days(200)
        s = series(list(range(200)), ds)
        sc, n, v = M.fng_score(s, ds[-1], False)
        self.assertGreater(sc, 99)
        self.assertEqual(n, 200)
        self.assertLess(M.fng_score(s, ds[-1], True)[0], 1)
        self.assertIsNone(M.fng_score(series([1, 2, 3]), days(3)[-1], False))        # меньше 10 точек

    def test_window_two_years(self):
        d_old = "2020-01-01"
        s = {d_old: 1000.0}
        s.update(series([1.0] * 30))
        sc, n, v = M.fng_score(s, max(s), False)
        self.assertEqual(n, 30)                                        # старое значение вне окна


class Labels(unittest.TestCase):
    def test_boundaries(self):
        for v, t in ((0, "Крайний страх"), (24, "Крайний страх"), (24.6, "Страх"), (25, "Страх"), (44, "Страх"), (45, "Нейтрально"),
                     (55, "Нейтрально"), (56, "Жадность"), (75, "Жадность"), (76, "Крайняя жадность"), (100, "Крайняя жадность")):
            self.assertEqual(M.fng_label(v), t, v)
        self.assertIsNone(M.fng_label(None))


class Components(unittest.TestCase):
    def test_momentum_sma(self):
        s = series([100.0] * 125 + [110.0])
        dev = M.fng_sma_dev(s, 125)
        last = max(dev)
        self.assertAlmostEqual(dev[last], (110 / ((100 * 124 + 110) / 125) - 1) * 100, places=6)
        self.assertEqual(len(dev), 2)

    def test_safe_bonds_outperform(self):
        ds = days(40)
        stocks = series([100.0] * 20 + [90.0] * 20, ds)                 # акции упали на 10%
        bonds = series([100.0 + i * 0.1 for i in range(40)], ds)         # облигации растут
        r = M.fng_safe_series(bonds, stocks)
        self.assertGreater(r[ds[-1]], 10)

    def test_breadth_and_highs(self):
        n = 130
        ds = days(n)
        closes = {}
        for i, d in enumerate(ds):
            c = {}
            for k in range(40):
                up = k < 30                                              # 30 из 40 акций растут, 10 падают
                c["S%d" % k] = 100 + (i if up else -i * 0.3)
            closes[d] = c
        br, hl = M.fng_breadth_hl(closes)
        self.assertAlmostEqual(br[ds[-1]], 75.0)
        self.assertAlmostEqual(hl[ds[-1]], (30 - 10) / 40 * 100)
        self.assertNotIn(ds[10], br)                                     # мало истории — значения нет
        self.assertNotIn(ds[60], hl)                                     # меньше 120 наблюдений для 52 недель

    def test_flow_parse(self):
        j = {"rows": [{"name": "Акции", "net": 5.0}, {"name": "Фонды денежного рынка", "net": 2.0}, {"name": "Облигации", "net": 9}]}
        self.assertEqual(M.fng_flow_parse(j), 3.0)
        self.assertIsNone(M.fng_flow_parse({"rows": [{"name": "Акции", "net": 1}]}))
        self.assertIsNone(M.fng_flow_parse(None))


def synth(n=300, closes=True):
    ds = days(n)
    imoex = series([2000 + i * 2 + (i % 7) * 5 for i in range(n)], ds)
    rvi = series([30 + (i % 11) for i in range(n)], ds)
    rgb = series([100 + i * 0.05 for i in range(n)], ds)
    cl = {}
    if closes:
        for i, d in enumerate(ds):
            cl[d] = {"S%d" % k: 100 + i * (1 if k % 3 else -0.2) + (i % 5) for k in range(40)}
    return ds, imoex, rvi, rgb, cl


class Assemble(unittest.TestCase):
    def test_payload_shape(self):
        ds, imoex, rvi, rgb, cl = synth()
        r = M.fng_assemble(imoex, rvi, rgb, cl, {}, {})
        self.assertEqual(set(r), {"value", "label", "ts", "components", "history", "prev", "low_conf"})
        self.assertEqual(r["ts"], ds[-1])
        self.assertTrue(0 <= r["value"] <= 100)
        self.assertEqual(r["label"], M.fng_label(r["value"]))
        keys = {c["key"] for c in r["components"]}
        self.assertEqual(keys, {"mom", "breadth", "hl", "vol", "safe"})
        for c in r["components"]:
            self.assertEqual(set(c), {"key", "name", "raw", "score", "weight", "conf", "pts", "note"})
            self.assertAlmostEqual(c["weight"], 0.2)
        self.assertAlmostEqual(sum(c["score"] for c in r["components"]) / 5, r["value"], delta=0.06)
        self.assertGreater(len(r["history"]), 50)
        self.assertEqual(r["history"][-1]["v"], r["value"])
        self.assertIn("day", r["prev"])
        self.assertIsNotNone(r["prev"]["week"])

    def test_missing_component_renormalised(self):
        ds, imoex, rvi, rgb, cl = synth()
        full = M.fng_assemble(imoex, rvi, rgb, cl, {}, {})
        part = M.fng_assemble(imoex, {}, rgb, cl, {}, {})                 # нет RVI
        self.assertEqual(len(part["components"]), len(full["components"]) - 1)
        self.assertAlmostEqual(sum(c["weight"] for c in part["components"]), 1.0, places=2)
        self.assertAlmostEqual(sum(c["score"] for c in part["components"]) / 4, part["value"], delta=0.06)

    def test_low_confidence_extra_components(self):
        ds, imoex, rvi, rgb, cl = synth()
        sp = series([5 + (i % 4) for i in range(15)], ds[-15:])
        r = M.fng_assemble(imoex, rvi, rgb, cl, sp, {})
        c = [x for x in r["components"] if x["key"] == "spread"][0]
        self.assertEqual(c["conf"], "low")
        self.assertTrue(r["low_conf"])

    def test_empty(self):
        r = M.fng_assemble({}, {}, {}, {}, {}, {})
        self.assertIsNone(r["value"])
        self.assertEqual(r["components"], [])


class RunMocked(unittest.TestCase):
    def test_background_run_and_payload(self):
        ds, imoex, rvi, rgb, cl = synth(200, closes=False)
        bench = {"IMOEX": imoex, "RVI": rvi, "RGBITR": rgb}
        saved = {k: getattr(M, k) for k in ("bench_history", "fng_fetch_day", "FNG_DAYS", "_fng_kick", "_fng_flow_points")}
        try:
            M.bench_history = lambda code, frm=None, force=False: bench[code]
            M.fng_fetch_day = lambda d: {"S%d" % k: 100 + k + hash(d) % 3 for k in range(35)}
            M.FNG_DAYS = 60
            M._fng_flow_points = lambda: {}
            M._fng.update(res=None, cl={}, running=True)
            M._fng_run()
            self.assertFalse(M._fng["running"])
            M._fng_kick = lambda force=False: None
            p = M.fng_payload()
            self.assertFalse(p["loading"])
            self.assertIn("progress", p)
            self.assertEqual(p["ts"], ds[-1])
            self.assertTrue(p["components"])
            self.assertTrue(0 <= p["value"] <= 100)
        finally:
            for k, v in saved.items():
                setattr(M, k, v)
            M._fng.update(res=None, cl={}, running=False)

    def test_payload_before_ready(self):
        saved = M._fng_kick
        try:
            M._fng_kick = lambda force=False: None
            M._fng.update(res=None, running=True)
            p = M.fng_payload()
            self.assertTrue(p["loading"])
            self.assertIsNone(p["value"])
            self.assertEqual(p["components"], [])
        finally:
            M._fng_kick = saved
            M._fng.update(res=None, running=False)


if __name__ == "__main__":
    unittest.main()
