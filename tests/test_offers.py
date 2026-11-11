"""Классификация оферт: put / call / unknown, дубли, отменённые и прошедшие даты (без сети)."""
import unittest

from tests._load import load

T = load()
TODAY = "2026-11-12"


def off(date, typ, ps=None, pe=None, price=100):
    return {"offerdate": date, "offerdatestart": ps, "offerdateend": pe, "price": price, "offertype": typ}


def kinds(bz_offers=(), opt=None, broker=None):
    return [(o["date"], o["kind"]) for o in T.offer_kinds({"offers": list(bz_offers)}, opt, broker, TODAY)]


class OfferKinds(unittest.TestCase):
    def test_put_only_plain_offer(self):
        r = T.offer_kinds({"offers": [off("2027-01-26", "Оферта", "2027-01-15", "2027-01-21")]}, None, None, TODAY)
        self.assertEqual([(o["date"], o["kind"]) for o in r], [("2027-01-26", "put")])
        self.assertFalse(r[0]["inferred"])
        self.assertEqual((r[0]["period_start"], r[0]["period_end"]), ("2027-01-15", "2027-01-21"))

    def test_put_without_period_marked_inferred(self):
        r = T.offer_kinds({"offers": [off("2027-07-28", "Оферта")]}, None, None, TODAY)
        self.assertEqual(r[0]["kind"], "put")
        self.assertTrue(r[0]["inferred"])

    def test_several_put_dates(self):
        got = kinds([off("2027-07-28", "Оферта"), off("2027-01-26", "Оферта")], {"put": ["2027-01-26"], "call": [], "prices": {}})
        self.assertEqual(got, [("2027-01-26", "put"), ("2027-07-28", "put")])

    def test_call_only_offer_redemption(self):
        r = T.offer_kinds({"offers": [off("0000-00-00", "Оферта/Погашение", price=None), off("2028-08-27", "Оферта/Погашение")]},
                          {"put": [], "call": ["2028-08-27"], "prices": {"2028-08-27": 100}}, None, TODAY)
        self.assertEqual([(o["date"], o["kind"]) for o in r], [("2028-08-27", "call")])
        self.assertEqual(r[0]["source"], "moex_call_field+moex_offertype")
        self.assertEqual(r[0]["price"], 100)

    def test_explicit_call_field_without_bondization(self):
        self.assertEqual(kinds([], {"put": [], "call": ["2026-12-01"], "prices": {}}), [("2026-12-01", "call")])

    def test_both_kinds_and_same_date(self):
        got = kinds([off("2027-03-01", "Оферта"), off("2027-09-01", "Оферта/Погашение")],
                    {"put": ["2027-03-01"], "call": ["2027-09-01", "2027-03-01"], "prices": {}})
        self.assertEqual(got, [("2027-03-01", "put"), ("2027-03-01", "call"), ("2027-09-01", "call")])
        self.assertEqual(T.offer_kind_on(T.offer_kinds({"offers": []}, {"put": ["2027-03-01"], "call": ["2027-03-01"]}, None, TODAY),
                                         "2027-03-01"), "both")

    def test_unknown_type_is_not_guessed(self):
        r = T.offer_kinds({"offers": [off("2027-05-05", "Что-то новое: оферта")]}, None, None, TODAY)
        self.assertEqual([(o["date"], o["kind"]) for o in r], [("2027-05-05", "unknown")])
        self.assertEqual(T.offer_kind_on(r, "2027-05-05"), "unknown")

    def test_unknown_dropped_when_date_has_known_kind(self):
        got = kinds([off("2027-05-05", "Оферта особая")], {"put": [], "call": ["2027-05-05"], "prices": {}})
        self.assertEqual(got, [("2027-05-05", "call")])

    def test_cancelled_offer_has_status(self):
        r = T.offer_kinds({"offers": [off("2027-02-02", "Оферта (отменена)"), off("2027-04-04", "Оферта (не состоялась)")]}, None, None, TODAY)
        self.assertEqual([(o["kind"], o["status"]) for o in r], [("put", "cancelled"), ("put", "cancelled")])

    def test_past_and_held_excluded(self):
        got = kinds([off("2026-05-25", "Оферта"), off("2026-11-12", "Оферта"), off("2027-02-02", "Оферта (состоялось)"),
                     off("2027-06-06", "Оферта")], {"put": ["2026-11-01"], "call": [], "prices": {}}, "2026-10-01")
        self.assertEqual(got, [("2027-06-06", "put")])

    def test_broker_date_joins_near_moex_date_else_unknown(self):
        self.assertEqual(kinds([], None, "2027-01-10"), [("2027-01-10", "unknown")])
        self.assertEqual(kinds([off("2027-01-10", "Оферта")], None, "2027-01-10"), [("2027-01-10", "put")])
        self.assertEqual(kinds([off("2027-02-12", "Оферта")], None, "2027-02-09"), [("2027-02-12", "put")])
        r = T.offer_kinds({"offers": []}, {"put": [], "call": ["2027-01-10"], "prices": {}}, "2027-01-10", TODAY)
        self.assertEqual((len(r), r[0]["source"]), (1, "moex_call_field+broker"))

    def test_empty(self):
        self.assertEqual(T.offer_kinds({}, None, None, TODAY), [])


class OfferPayloadRecords(unittest.TestCase):
    def test_call_record_has_no_put_fields_and_put_has_hint(self):
        bz = {"coupons": [], "amort": [], "offers": []}
        offs = T.offer_kinds(bz, {"put": ["2027-01-26"], "call": ["2027-06-01"], "prices": {}}, None, TODAY)
        r = {"isin": "X", "name": "Тест", "qty": 10, "value_rub": 10000.0, "nominal": 1000.0, "price_pct": 99.0}
        res = T._of_one(r, bz, offs, TODAY, {})
        self.assertEqual([x["kind"] for x in res], ["put", "call"])
        self.assertEqual(res[1]["hint"]["code"], "call")
        self.assertIsNone(res[1]["to_offer_rub"])
        self.assertGreater(res[0]["to_offer_rub"], 0)

    def test_cancelled_not_shown(self):
        offs = T.offer_kinds({"offers": [off("2027-02-02", "Оферта (отменена)")]}, None, None, TODAY)
        self.assertEqual(T._of_one({"isin": "X", "name": "T"}, {}, offs, TODAY, {}), [])


if __name__ == "__main__":
    unittest.main()
