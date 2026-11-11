"""Сводка «Сегодня»: окно выплат, окно и статусы оферт, рейтинги, пустой случай (без сети)."""
import unittest

from tests._load import load

T = load()
TODAY = "2026-11-12"


def pay(d, kind="coupon", amount=100.0, name="Бумага"):
    return {"date": d, "kind": kind, "name": name, "amount": amount}


def offer(d, kind="put", ps=None, pe=None, status="scheduled"):
    return {"date": d, "kind": kind, "period_start": ps, "period_end": pe, "status": status}


class Payments(unittest.TestCase):
    def test_window_and_kinds(self):
        pays = [pay("2026-11-11"), pay("2026-11-12", amount=50), pay("2026-11-19", "dividend", 200), pay("2026-11-20"),
                pay("2026-11-15", "redemption", 1000), pay("2026-11-13", "amortization", 10)]
        r = T.td_payments(pays, TODAY)
        self.assertEqual(r["count"], 3)
        self.assertAlmostEqual(r["sum"], 260)
        self.assertEqual(r["next_date"], "2026-11-12")
        self.assertEqual(set(r["by_kind"]), {"coupon", "dividend", "amortization"})

    def test_empty(self):
        r = T.td_payments([], TODAY)
        self.assertEqual((r["count"], r["sum"]), (0, 0))


class Offers(unittest.TestCase):
    def test_statuses(self):
        self.assertEqual(T.td_offer_status(offer("2026-11-30", ps="2026-11-10", pe="2026-11-20"), TODAY), "open")
        self.assertEqual(T.td_offer_status(offer("2026-11-30", ps="2026-11-15", pe="2026-11-20"), TODAY), "upcoming")
        self.assertEqual(T.td_offer_status(offer("2026-11-30", ps="2026-11-01", pe="2026-11-10"), TODAY), "closed")
        self.assertEqual(T.td_offer_status(offer("2026-11-30"), TODAY), "unknown")

    def test_window_sorting_and_filters(self):
        a, b = {"isin": "A", "name": "А"}, {"isin": "B", "name": "Б"}
        pairs = [(a, [offer("2026-12-05", "call"), offer("2027-03-01"), offer("2026-11-20", status="cancelled")]),
                 (b, [offer("2026-11-25", ps="2026-11-10", pe="2026-11-18"), offer("2026-12-10", ps="2026-11-01", pe="2026-11-05")])]
        r = T.td_offers(pairs, TODAY)
        self.assertEqual([(x["isin"], x["date"], x["status"]) for x in r["items"]],
                         [("B", "2026-11-25", "open"), ("A", "2026-12-05", "unknown")])
        self.assertEqual((r["put"], r["call"], r["count"]), (1, 1, 2))
        self.assertEqual(r["items"][0]["period_end"], "2026-11-18")

    def test_empty(self):
        self.assertEqual(T.td_offers([], TODAY)["count"], 0)


class Digest(unittest.TestCase):
    def test_empty_digest(self):
        d = T.td_digest([], [], [], [], TODAY, alerts=[])
        self.assertTrue(d["empty"])
        for k in ("payments", "offers", "ratings", "alerts"):
            self.assertNotIn(k, d)

    def test_sections_present_only_when_nonempty(self):
        d = T.td_digest([pay("2026-11-14")], [({"isin": "A", "name": "А"}, [offer("2026-11-25")])], [], [], TODAY,
                        alerts=[{"severity": "high"}, {"severity": "info"}])
        self.assertFalse(d["empty"])
        self.assertEqual(d["payments"]["count"], 1)
        self.assertEqual(d["offers"]["count"], 1)
        self.assertNotIn("ratings", d)
        self.assertEqual(d["alerts"], {"count": 1, "high": 1})

    def test_no_alerts_key_when_monitor_not_ready(self):
        d = T.td_digest([], [], [], [], TODAY, alerts=None)
        self.assertNotIn("alerts", d)

    def test_endpoint_registered_and_empty_without_token(self):
        self.assertIn("/api/today", T.API_GET)
        r = T.today_get({"token": "", "sandbox": False}, "all", {}, False)
        self.assertTrue(r["empty"])


if __name__ == "__main__":
    unittest.main()
