import random
import unittest

from tests._load import load

T = load()


def inter(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(w, 0) * max(h, 0)


class TreemapTests(unittest.TestCase):
    def check(self, vals, x, y, w, h):
        rs = T.treemap_layout(vals, x, y, w, h)
        self.assertEqual(len(rs), len(vals))
        pos = [(r, v) for r, v in zip(rs, vals) if v > 0]
        tot = sum(v for _, v in pos)
        for r, v in pos:
            self.assertAlmostEqual(r[2] * r[3], v / tot * w * h, places=4)
            self.assertGreaterEqual(r[0], x - 1e-6)
            self.assertGreaterEqual(r[1], y - 1e-6)
            self.assertLessEqual(r[0] + r[2], x + w + 1e-6)
            self.assertLessEqual(r[1] + r[3], y + h + 1e-6)
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                self.assertLess(inter(pos[i][0], pos[j][0]), 1e-6)
        self.assertAlmostEqual(sum(r[2] * r[3] for r, _ in pos), w * h if pos else 0, places=4)

    def test_random(self):
        rnd = random.Random(5)
        for n in (1, 2, 7, 40, 150):
            vals = [rnd.random() ** 3 * 1000 + 0.1 for _ in range(n)]
            self.check(vals, 10, 20, 800, 400)
            self.check(vals, 0, 0, 300, 900)

    def test_zero_and_empty(self):
        self.check([5, 0, 3, -1], 0, 0, 100, 50)
        self.assertEqual(T.treemap_layout([], 0, 0, 10, 10), [])
        self.assertEqual(T.treemap_layout([0, 0], 0, 0, 10, 10)[0][2:], (0.0, 0.0))


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self._old = {k: T.__dict__.get(k) for k in ("stocks_universe", "funds_universe", "screener_rows", "best_rating")}

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                T.__dict__.pop(k, None)
            else:
                setattr(T, k, v)

    def test_stocks(self):
        def u(force=False):
            return [
                {"secid": "SBER", "name": "Сбербанк", "shortname": "Сбербанк", "sector": "Финансы", "price": 300, "chg_d": 1.5, "chg_w": 2, "chg_m": 3, "value_today": 100, "cap": 6000},
                {"secid": "VTBR", "shortname": "ВТБ", "sector": "Финансы", "price": 80, "chg_d": -1, "chg_w": 0, "chg_m": 0, "value_today": 50, "cap": 2000},
                {"secid": "GAZP", "shortname": "Газпром", "sector": "Нефть и газ", "price": 120, "chg_d": 0, "chg_w": 5, "chg_m": 9, "value_today": 70, "cap": 3000},
                {"secid": "ZERO", "shortname": "Z", "sector": "Нефть и газ", "chg_d": 1, "value_today": 5, "cap": 0},
            ]
        T.stocks_universe = u
        p = T.heatmap_payload("stocks", "d", "cap")
        self.assertEqual([g["name"] for g in p["groups"]], ["Финансы", "Нефть и газ"])
        self.assertEqual([i["id"] for i in p["groups"][0]["items"]], ["SBER", "VTBR"])
        self.assertEqual(p["stats"]["n"], 3)
        self.assertEqual((p["stats"]["up"], p["stats"]["down"], p["stats"]["flat"]), (1, 1, 1))
        self.assertEqual(p["stats"]["turnover"], 220)
        self.assertAlmostEqual(p["stats"]["wchg"], (1.5 * 6000 - 2000) / 11000, places=2)
        w = T.heatmap_payload("stocks", "w", "value")
        self.assertEqual(sum(len(g["items"]) for g in w["groups"]), 4)
        self.assertEqual(w["groups"][0]["items"][0]["chg"], 2)

    def test_funds_grouped_by_category(self):
        T.funds_universe = lambda: [
            {"secid": "LQDT", "shortname": "LQDT", "sector": "Денежный рынок", "chg_d": 0.1, "value_today": 10, "cap": 500},
            {"secid": "TMOS", "shortname": "TMOS", "sector": "Акции", "chg_d": -1, "value_today": 5, "cap": 300},
            {"secid": "SBMM", "shortname": "SBMM", "sector": "Денежный рынок", "chg_d": 0.2, "value_today": 5, "cap": 100}]
        p = T.heatmap_payload("funds", "d", "cap")
        self.assertEqual([g["name"] for g in p["groups"]], ["Денежный рынок", "Акции"])
        self.assertEqual(p["stats"]["n"], 3)

    def test_missing_universe(self):
        T.__dict__.pop("funds_universe", None)
        self.assertIn("error", T.heatmap_payload("funds"))

    def test_bonds(self):
        rows = [{"id": "RU1", "isin": "RU1", "name": "Б1", "turn": 900, "chg": 0.3, "price": 99, "yield": 15, "rating": "AAA"},
                {"id": "RU2", "isin": "RU2", "name": "Б2", "turn": 500, "chg": -0.2, "price": 98, "yield": 17, "rating": "BBB+"},
                {"id": "RU3", "isin": "RU3", "name": "Б3", "turn": 100, "chg": 0, "price": 97, "yield": 20, "rating": None},
                {"id": "RU4", "isin": "RU4", "name": "Б4", "turn": 0, "chg": 1, "price": 97, "yield": 20, "rating": "AA"}]
        T.screener_rows = lambda: rows
        T.best_rating = lambda isin, name: None
        p = T.heatmap_payload("bonds", "w", "cap")
        self.assertEqual((p["period"], p["size"]), ("d", "value"))
        self.assertEqual([g["name"] for g in p["groups"]], ["AAA", "BBB", "без рейтинга"])
        self.assertEqual(p["stats"]["n"], 3)


if __name__ == "__main__":
    unittest.main()
