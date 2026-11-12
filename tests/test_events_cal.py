"""Календарь событий: нормализация видов выплат, слияние амортизаций, диапазон года (без сети)."""
import unittest

from tests._load import load

T = load()
ISIN = "RU000A10XXXX"


class Fake:
    """Подменяет сетевые источники events_payload и возвращает прежние значения при выходе."""
    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = getattr(T, k, None)
            setattr(T, k, v)

    def __exit__(self, *a):
        for k, v in self.old.items():
            setattr(T, k, v)


def payload(pays, bz, frm="2027-01-01", to="2027-12-31"):
    rep = {"rows": [{"ticker": "TK", "isin": ISIN, "name": "Интерлизинг 001P-11", "qty": 10, "call": None}], "payments": pays}
    with Fake(cbr_meetings=lambda: {"dates": ["2027-02-12"], "ok": True}, build_bonds=lambda c, a: rep, moex_bondization=lambda i: bz,
              moex_bond_options=lambda i: None, primary_rows=lambda: [], watch_isins=lambda: []):
        return T.events_payload({}, "acc", {"from": frm, "to": to})


class EvKind(unittest.TestCase):
    def test_alias(self):
        self.assertEqual(T.ev_kind("amortization"), "amort")
        self.assertEqual(T.ev_kind("coupon"), "coupon")
        self.assertEqual(T.ev_kind(None), "")
        self.assertEqual(T._ev("2027-03-01", "amortization", "x")["kind"], "amort")


class AmortMerge(unittest.TestCase):
    def test_payday_and_moex_amort_one_event(self):
        pays = [{"date": "2027-03-01", "kind": "amortization", "name": "Интерлизинг 001P-11", "ticker": "TK", "amount": 100.0, "est": False}]
        bz = {"amort": [{"amortdate": "2027-03-01", "value": 10.0}, {"amortdate": "2028-03-01", "value": 90.0}], "coupons": [], "offers": []}
        p = payload(pays, bz)
        am = [e for e in p["events"] if e["kind"] == "amort"]
        self.assertEqual(len(am), 1)
        self.assertEqual(am[0]["amount"], 100.0)
        self.assertEqual(am[0]["note"], "частичное погашение номинала")
        self.assertFalse([e for e in p["events"] if e["kind"] == "amortization"])

    def test_kinds_filter_uses_alias(self):
        pays = [{"date": "2027-03-01", "kind": "amortization", "name": "A", "ticker": "TK", "amount": 5.0}]
        with Fake(cbr_meetings=lambda: {"dates": [], "ok": True}, build_bonds=lambda c, a: {"rows": [], "payments": pays},
                  primary_rows=lambda: [], watch_isins=lambda: []):
            p = T.events_payload({}, "a", {"from": "2027-01-01", "to": "2027-12-31", "kinds": "amortization"})
        self.assertEqual([e["kind"] for e in p["events"]], ["amort"])


class YearRange(unittest.TestCase):
    def test_year_ok_and_cbr_present(self):
        p = payload([], {"amort": [], "coupons": [], "offers": []})
        self.assertEqual((p["from"], p["to"]), ("2027-01-01", "2027-12-31"))
        self.assertEqual([e["date"] for e in p["events"] if e["kind"] == "cbr"], ["2027-02-12"])

    def test_bad_range(self):
        for frm, to in (("2027-01-01", "2028-12-31"), ("2027-05-01", "2027-04-01"), ("2027-13-01", "2027-12-31")):
            with self.assertRaises(T.ApiError):
                payload([], {}, frm, to)


if __name__ == "__main__":
    unittest.main()
