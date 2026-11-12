"""Помощник по пут-оферте, события календаря по офертам и напоминания Telegram (чистые функции, без сети)."""
import unittest

from tests._load import load

T = load()
TODAY = "2026-11-12"


def cp(d, v=None, p=None):
    return {"coupondate": d, "value": v, "valueprc": p}


class NewCoupon(unittest.TestCase):
    OD = "2027-01-26"

    def test_announced_by_percent(self):
        r = T.of_new_coupon([cp("2026-07-26", 40, 8.0), cp("2027-01-26", 40, 8.0), cp("2027-07-26", None, 14.5)], self.OD, 1000)
        self.assertEqual((r["status"], r["date"], r["rate"]), ("announced", "2027-07-26", 14.5))

    def test_announced_by_value(self):
        r = T.of_new_coupon([cp("2027-01-26", 40), cp("2027-07-26", 73.0)], self.OD, 1000)
        self.assertEqual(r["status"], "announced")
        self.assertAlmostEqual(r["rate"], 73.0 / 1000 * 365 / 181 * 100, places=6)

    def test_not_yet(self):
        r = T.of_new_coupon([cp("2027-01-26", 40, 8.0), cp("2027-07-26"), cp("2028-01-26")], self.OD, 1000)
        self.assertEqual(r["status"], "pending")
        self.assertIsNone(r["rate"])

    def test_coupon_on_offer_date_is_old_rate(self):
        self.assertEqual(T.of_new_coupon([cp("2027-01-26", 40, 8.0)], self.OD, 1000)["status"], "pending")

    def test_floater_formula(self):
        self.assertEqual(T.of_new_coupon([cp("2027-01-26", 40), cp("2027-07-26")], self.OD, 1000, floating=True)["status"], "formula")
        self.assertEqual(T.of_new_coupon([cp("2027-07-26", None, 12.0)], self.OD, 1000, floating=True)["status"], "announced")


class Outcome(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(T.of_outcome(14.0, 15.0)[0], "below")
        self.assertEqual(T.of_outcome(14.5, 15.0)[0], "fair")      # граница -0,5 включается в fair
        self.assertEqual(T.of_outcome(15.5, 15.0)[0], "fair")
        self.assertEqual(T.of_outcome(15.6, 15.0)[0], "above")
        self.assertEqual(T.of_outcome(None, 15.0), (None, None))
        self.assertEqual(T.of_outcome(15.0, None), (None, None))


def rec(**kw):
    r = {"kind": "put", "date": "2027-01-26", "period_start": "2027-01-15", "period_end": "2027-01-21", "period_status": "upcoming",
         "coupon_status": "pending", "new_rate": None, "hold_yield": None, "peer_median": None, "peers_n": 0, "offer_price": 100.0,
         "price": 99.0, "risk_notes": []}
    r.update(kw)
    return r


class Helper(unittest.TestCase):
    def test_not_put(self):
        self.assertIsNone(T.of_helper(rec(kind="call")))

    def test_pending_neutral(self):
        h = T.of_helper(rec())
        self.assertIsNone(h["outcome"])
        self.assertIn("Новый купон ещё не объявлен", h["text"])
        self.assertIn("с 15.01 по 21.01", h["text"])
        pend = T.of_helper(rec(period_start=None, period_end=None))
        self.assertNotIn("Ожидаемый", pend["text"])

    def test_formula(self):
        h = T.of_helper(rec(coupon_status="formula"))
        self.assertEqual(h["status"], "formula")
        self.assertIsNone(h["outcome"])

    def test_three_outcomes(self):
        base = dict(coupon_status="announced", new_rate=15.0, peer_median=16.0, peers_n=5)
        b = T.of_helper(rec(hold_yield=14.0, **base))
        self.assertEqual(b["outcome"], "below")
        self.assertIn("ниже медианы похожих выпусков на 2,0 п. п.", b["title"])
        self.assertIn("с 15.01 по 21.01", b["apply"])
        self.assertEqual(T.of_helper(rec(hold_yield=16.2, **base))["title"], "Доходность на уровне медианы похожих выпусков")
        self.assertEqual(T.of_helper(rec(hold_yield=17.5, **base))["title"], "Доходность выше медианы похожих выпусков")

    def test_no_peers_and_closed_and_price(self):
        h = T.of_helper(rec(coupon_status="announced", new_rate=15.0, hold_yield=15.0))
        self.assertIsNone(h["outcome"])
        self.assertEqual(T.of_helper(rec(period_status="closed"))["status"], "closed")
        h = T.of_helper(rec(coupon_status="announced", new_rate=10.0, hold_yield=10.0, peer_median=15.0, peers_n=4, price=101.0))
        self.assertIn("выше цены выкупа", h["text"])


class Events(unittest.TestCase):
    def offs(self):
        return [{"date": "2027-01-26", "kind": "put", "status": "scheduled", "price": 100, "period_start": "2027-01-15", "period_end": "2027-01-21"},
                {"date": "2027-03-01", "kind": "call", "status": "scheduled", "price": None, "period_start": None, "period_end": None},
                {"date": "2027-03-05", "kind": "unknown", "status": "scheduled", "price": None, "period_start": None, "period_end": None},
                {"date": "2027-01-27", "kind": "put", "status": "cancelled", "price": None, "period_start": None, "period_end": None}]

    def test_events(self):
        ev = T.offer_events(self.offs(), "Бонд", "RU1", "2027-01-01", "2027-03-31")
        self.assertEqual([(e["date"], e["sub"], e["badge"]) for e in ev],
                         [("2027-01-15", "put_open", "PUT"), ("2027-01-21", "put_close", "PUT"), ("2027-01-26", "put_buyback", "PUT"),
                          ("2027-03-01", "call", "CALL"), ("2027-03-05", "unknown", "тип не указан")])
        self.assertEqual(ev[3]["label"], "Возможное досрочное погашение (колл)")
        self.assertEqual(ev[0]["label"], "Открыт приём заявок по пут-оферте")

    def test_window_filter(self):
        ev = T.offer_events(self.offs(), "Бонд", "RU1", "2027-01-20", "2027-01-31", "w_")
        self.assertEqual([e["sub"] for e in ev], ["put_close", "put_buyback"])
        self.assertTrue(all(e["kind"] == "w_offer" for e in ev))


class Reminders(unittest.TestCase):
    def it(self, **kw):
        d = {"isin": "RU1", "name": "Бонд", "kind": "put", "date": "2027-01-26", "period_start": "2027-01-15", "period_end": "2027-01-21",
             "coupon_status": "pending", "new_rate": None}
        d.update(kw)
        return d

    def keys(self, items, today):
        return [k for k, _ in T.tg_offer_due(items, today)]

    def test_schedule(self):
        i = self.it()
        self.assertEqual(self.keys([i], "2027-01-01"), [])
        self.assertEqual(self.keys([i], "2027-01-15"), ["ofr|RU1|2027-01-26|open"])
        self.assertEqual(self.keys([i], "2027-01-19"), ["ofr|RU1|2027-01-26|open", "ofr|RU1|2027-01-26|close"])
        self.assertEqual(self.keys([i], "2027-01-18"), ["ofr|RU1|2027-01-26|open"])
        self.assertEqual(self.keys([i], "2027-01-22"), [])

    def test_coupon_and_texts(self):
        i = self.it(coupon_status="announced", new_rate=14.5)
        got = dict(T.tg_offer_due([i], "2027-01-10"))
        self.assertEqual(list(got), ["ofr|RU1|2027-01-26|coupon"])
        self.assertIn("14,50", got["ofr|RU1|2027-01-26|coupon"])
        t = dict(T.tg_offer_due([i], "2027-01-19"))["ofr|RU1|2027-01-26|close"]
        self.assertIn("осталось 2 дня подать заявку", t)

    def test_call_14_days(self):
        c = self.it(kind="call", period_start=None, period_end=None, date="2027-03-01")
        self.assertEqual(self.keys([c], "2027-02-14"), [])
        self.assertEqual(self.keys([c], "2027-02-15"), ["ofr|RU1|2027-03-01|call"])
        self.assertEqual(self.keys([c], "2027-03-01"), [])

    def test_keys_stable_for_dedup(self):
        i = self.it()
        a = self.keys([i], "2027-01-19")
        self.assertEqual(a, self.keys([i], "2027-01-20"))


if __name__ == "__main__":
    unittest.main()
