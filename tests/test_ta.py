"""Технический анализ: чистые функции (офлайн, известные значения)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

m = _load.load()


def candle(c, rng=2.0, t="2026-01-01"):
    return {"t": t, "o": c, "h": c + rng / 2, "l": c - rng / 2, "c": c, "v": 1}


class Basics(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(m.sma([1, 2, 3, 4, 5], 3), [None, None, 2, 3, 4])
        self.assertEqual(m.sma([1, 2], 3), [None, None])

    def test_ema(self):
        # старт — среднее первых n (=2), k = 0.5
        self.assertEqual(m.ema([1, 2, 3, 4, 5], 3), [None, None, 2, 3, 4])
        e = m.ema([1, 2, 3, 6], 3)
        self.assertAlmostEqual(e[3], 6 * 0.5 + 2 * 0.5)

    def test_rsi(self):
        r = m.rsi([1, 2, 1, 2, 1], 2)
        self.assertEqual(r[:2], [None, None])
        self.assertAlmostEqual(r[2], 50.0)
        self.assertAlmostEqual(r[3], 75.0)               # ag = (0.5·1 + 1)/2 = 0.75, al = 0.25
        self.assertEqual(m.rsi(list(range(1, 30)))[-1], 100.0)
        self.assertEqual(m.rsi(list(range(30, 1, -1)))[-1], 0.0)

    def test_macd(self):
        v = [100 + 0.5 * i + (3 if i % 5 == 0 else 0) for i in range(80)]
        line, sig, hist = m.macd(v)
        ef, es = m.ema(v, 12), m.ema(v, 26)
        self.assertIsNone(line[24])
        self.assertAlmostEqual(line[40], ef[40] - es[40])
        self.assertIsNone(sig[32])
        self.assertIsNotNone(sig[33])
        self.assertAlmostEqual(hist[60], line[60] - sig[60])
        self.assertEqual(len(line), len(sig))

    def test_bollinger(self):
        mid, up, lo = m.bollinger([1, 2, 3, 4, 5], 5, 2)
        self.assertEqual(mid[4], 3)
        self.assertAlmostEqual(up[4], 3 + 2 * math.sqrt(2))
        self.assertAlmostEqual(lo[4], 3 - 2 * math.sqrt(2))
        mid, up, lo = m.bollinger([7.0] * 25)
        self.assertEqual((mid[-1], up[-1], lo[-1]), (7.0, 7.0, 7.0))

    def test_atr(self):
        cs = [candle(100 + i * 0.0, 2.0) for i in range(30)]
        self.assertAlmostEqual(m.atr(cs)[-1], 2.0)
        self.assertIsNone(m.atr(cs)[13])
        cs[20] = dict(candle(110), l=108.0, h=112.0)       # гэп вверх: TR = |112 − 100| = 12
        self.assertGreater(m.atr(cs)[20], 2.0)


class Levels(unittest.TestCase):
    def zigzag(self):
        closes = []
        for _ in range(8):
            closes += [100, 102, 104, 106, 108, 110, 108, 106, 104, 102]     # пики ~110, впадины ~100
        return [candle(c, 1.0) for c in closes] + [candle(105, 1.0)]

    def test_support_resistance(self):
        lv = m.levels(self.zigzag())
        self.assertTrue(lv["resistance"] and lv["support"])
        self.assertAlmostEqual(lv["resistance"][0]["price"], 110.5, delta=0.6)
        self.assertAlmostEqual(lv["support"][0]["price"], 99.5, delta=0.6)
        self.assertGreaterEqual(lv["resistance"][0]["touches"], 5)
        self.assertTrue(all(x["price"] > 105 for x in lv["resistance"]) and all(x["price"] <= 105 for x in lv["support"]))
        self.assertLessEqual(len(lv["support"]), 3)

    def test_short(self):
        self.assertEqual(m.levels([candle(1)] * 3), {"support": [], "resistance": []})


class Summary(unittest.TestCase):
    def test_short_series(self):
        self.assertIsNone(m.ta_summary([candle(1)] * 10)["signal"])

    def test_voting(self):
        up = [candle(100 * 1.01 ** i) for i in range(260)]
        s = m.ta_summary(up)
        v = {x["id"]: x["vote"] for x in s["votes"]}
        self.assertEqual((v["sma50"], v["sma200"], v["rsi"]), (1, 1, -1))     # тренд вверх, но RSI перекуплен
        self.assertEqual(s["score"], sum(v.values()))
        self.assertEqual(s["signal"], "покупать" if s["score"] >= 2 else "продавать" if s["score"] <= -2 else "нейтрально")
        dn = m.ta_summary([candle(1000 * 0.99 ** i) for i in range(260)])
        d = {x["id"]: x["vote"] for x in dn["votes"]}
        self.assertEqual((d["sma50"], d["sma200"], d["rsi"]), (-1, -1, 1))

    def test_sell_on_downtrend(self):
        s = m.ta_summary([candle(300 - 0.4 * i) for i in range(250)])
        self.assertEqual({x["id"]: x["vote"] for x in s["votes"]}["sma200"], -1)
        self.assertIn(s["signal"], ("покупать", "нейтрально", "продавать"))

    def test_series_aligned(self):
        cs = [candle(100 + i) for i in range(60)]
        ser = m.ta_series(cs)
        for k, a in ser.items():
            self.assertEqual(len(a), 60, k)


if __name__ == "__main__":
    unittest.main()
