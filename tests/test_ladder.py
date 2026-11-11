"""Лесенка текущего портфеля: события возврата, разбивка по периодам, подсветка перегруза и пустых лет."""
import unittest

from tests._load import load

T = load()
TODAY = "2026-11-11"


def it(isin, evs, name=None):
    return {"isin": isin, "name": name or isin, "ytm": 15.0, "events": [{"date": d, "type": t, "amount": a} for d, t, a in evs]}


class LadderEvents(unittest.TestCase):
    def test_maturity_with_amort(self):
        ev = T.ld_events("2028-05-01", None, 1000.0, 3, 1.0, [("2027-05-01", 100.0), ("2026-01-01", 50.0)], TODAY, False)
        self.assertEqual([(e["date"], e["type"], e["amount"]) for e in ev],
                         [("2027-05-01", "amort", 300.0), ("2028-05-01", "redemption", 2700.0)])

    def test_offer_replaces_maturity(self):
        ev = T.ld_events("2030-01-01", "2027-06-01", 1000.0, 2, 1.0, [("2027-01-01", 200.0), ("2028-01-01", 200.0)], TODAY, True)
        self.assertEqual([(e["date"], e["type"], e["amount"]) for e in ev],
                         [("2027-01-01", "amort", 400.0), ("2027-06-01", "offer", 1600.0)])
        ev2 = T.ld_events("2030-01-01", "2027-06-01", 1000.0, 2, 1.0, [], TODAY, False)
        self.assertEqual([e["type"] for e in ev2], ["redemption"])

    def test_past_and_perpetual(self):
        self.assertEqual(T.ld_events("2026-01-01", None, 1000.0, 1, 1.0, [], TODAY, True), [])
        self.assertEqual(T.ld_events(None, None, 1000.0, 1, 1.0, [], TODAY, True), [])


class LadderBuckets(unittest.TestCase):
    def setUp(self):
        self.items = [it("A", [("2027-03-01", "redemption", 1000)]), it("B", [("2027-09-01", "redemption", 1000)]),
                      it("C", [("2027-12-01", "redemption", 1000)]),
                      it("D", [("2029-02-01", "amort", 300), ("2029-06-01", "amort", 300), ("2029-12-01", "redemption", 400)]),
                      it("E", [("2031-04-01", "redemption", 1000)])]

    def test_years_gaps_and_heavy(self):
        ps = T.ld_buckets(self.items, TODAY, "year")
        self.assertEqual([p["label"] for p in ps], ["2027", "2028", "2029", "2030", "2031"])
        self.assertEqual([p["flag"] for p in ps], ["heavy", "gap", None, "gap", None])
        self.assertAlmostEqual(ps[0]["share"], 3000 / 5000.0 * 100)
        d = [r for r in ps[2]["items"]]
        self.assertEqual(len(d), 2)                       # амортизации одной бумаги свёрнуты в одну строку
        self.assertEqual(d[0]["n"], 2)
        self.assertAlmostEqual(sum(p["share"] for p in ps), 100.0)
        s = T.ld_summary(self.items, TODAY, ps)
        self.assertEqual(s["gaps"], ["2028", "2030"])
        self.assertEqual(s["heavy"]["label"], "2027")
        self.assertEqual(s["next"]["date"], "2027-03-01")
        self.assertGreater(s["avg_years"], 0.4)

    def test_quarters_then_years(self):
        ps = T.ld_buckets(self.items, TODAY, "quarter")
        keys = [p["key"] for p in ps]
        self.assertEqual(keys[:5], ["2026-Q4", "2027-Q1", "2027-Q2", "2027-Q3", "2027-Q4"])
        self.assertIn("2027-Q1", keys)
        self.assertNotIn("2028-Q1", keys)                 # дальше следующего года — годовые периоды
        self.assertEqual(keys[-4:], ["2028", "2029", "2030", "2031"])
        q2 = next(p for p in ps if p["key"] == "2027-Q2")
        self.assertEqual(q2["flag"], "gap")
        self.assertEqual(next(p for p in ps if p["key"] == "2028")["flag"], "gap")     # пустой год после первых выплат — пропуск

    def test_empty(self):
        self.assertEqual(T.ld_buckets([], TODAY, "year"), [])
        s = T.ld_summary([], TODAY, [])
        self.assertIsNone(s["next"])
        self.assertIsNone(s["heavy"])


if __name__ == "__main__":
    unittest.main()
