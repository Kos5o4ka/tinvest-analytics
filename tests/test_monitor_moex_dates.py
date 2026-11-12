"""Мониторинг: события графика выпуска по данным Мосбиржи, склейка рейтинговых тревог, названия эмитентов."""
import unittest

from _load import load

m = load()
BZ = {"coupons": [{"coupondate": "2026-11-29", "value": 10}, {"coupondate": "2026-12-20", "value": 10}],
      "amort": [{"amortdate": "2026-12-01", "valueprc": 25.0, "value": 250}, {"amortdate": "2027-03-01", "valueprc": 75.0, "value": 750}],
      "offers": []}


class MoexEvents(unittest.TestCase):
    def test_window_and_kinds(self):
        r = m.mon_moex_events(BZ, [], "2026-11-12", 30)
        self.assertEqual(r["maturity"], "2027-03-01")
        self.assertEqual([(e["kind"], e["date"], e["left"]) for e in r["events"]], [("amort", "2026-12-01", 19)])
        r = m.mon_moex_events(BZ, [], "2026-11-12", 200)
        self.assertEqual([e["kind"] for e in r["events"]], ["amort", "maturity"])

    def test_past_events_dropped(self):
        r = m.mon_moex_events(BZ, [], "2026-12-02", 30)
        self.assertEqual(r["events"], [])

    def test_maturity_without_amort(self):
        r = m.mon_moex_events({"coupons": BZ["coupons"], "amort": []}, [], "2026-12-10", 30)
        self.assertEqual(r["maturity"], "2026-12-20")
        self.assertEqual([e["kind"] for e in r["events"]], ["maturity"])

    def test_offers_from_moex(self):
        offs = [{"date": "2026-11-20", "kind": "put", "status": "scheduled"},
                {"date": "2026-11-25", "kind": "call", "status": "cancelled"},
                {"date": "2027-05-01", "kind": "put", "status": "scheduled"}]
        r = m.mon_moex_events(BZ, offs, "2026-11-12", 30)
        self.assertEqual([(e["date"], e.get("offer_kind")) for e in r["events"] if e["kind"] == "offer"], [("2026-11-20", "put")])
        self.assertEqual(r["next_offer"], "2026-11-20")

    def test_texts(self):
        e = m.mon_moex_events(BZ, [], "2026-11-12", 30)["events"][0]
        self.assertIn("Амортизация 25,0 % номинала 01.12.2026 (через 19 дн.)", m.mon_event_alert(e))
        self.assertIn("Мосбирж", m.mon_event_alert(e))


class Issuer(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(m.mon_clean_issuer("ГК «Самолет"), "ГК Самолет")
        self.assertEqual(m.mon_clean_issuer("АФК «СИСТЕМА"), "АФК Система")
        self.assertEqual(m.mon_clean_issuer("БАЛТИЙСКИЙ ЛИЗИНГ"), "Балтийский Лизинг")
        self.assertEqual(m.mon_clean_issuer("ГК «Самолет»"), "ГК «Самолет»")
        self.assertEqual(m.mon_clean_issuer("СОПФ ДОМ.РФ"), "СОПФ ДОМ.РФ")


class RatingAlerts(unittest.TestCase):
    def ev(self, post, level, d, act="понижен"):
        return {"agency": "НРА", "issuer": "Селигдар", "tokens": ["селигдар"], "level": level, "date": d, "post": post,
                "action": act, "rating": "A+", "prev": None}

    def test_dedupe_and_aging(self):
        rows = [({"isin": "X1", "name": "Селигдар 1"}, [{"селигдар"}])]
        evs = [self.ev(1, "bond", "2026-11-01"), self.ev(2, "issuer", "2026-11-01"), self.ev(3, "issuer", "2026-09-01")]
        al = m._mon_rating_alerts(rows, evs, "2026-08-14", "2026-11-12")
        self.assertEqual(len(al), 2)
        self.assertEqual(al[0]["severity"], "high")
        self.assertIn("эмитент и облигации", al[0]["message"])
        self.assertEqual(al[1]["severity"], "medium")


if __name__ == "__main__":
    unittest.main()
