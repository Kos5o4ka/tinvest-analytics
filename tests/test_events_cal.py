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
              moex_bond_options=lambda i: None, primary_rows=lambda: [], watch_isins=lambda: [],
              key_rate_now=lambda: (16.5, "2026-10-27")):
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
                  primary_rows=lambda: [], watch_isins=lambda: [], key_rate_now=lambda: (None, None)):
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


class CbrCalendar(unittest.TestCase):
    PAGE = ('<div class="date">13 февраля 2027</div><div>Заседание Совета директоров Банка России по ключевой ставке</div>'
            '<div class="date">20 февраля 2027</div><div>Публикация резюме обсуждения</div>'
            '<div class="date">18&nbsp;декабря 2026</div><div>Заседание Совета директоров по денежно-кредитной политике</div>')

    def setUp(self):
        st = T.store()
        for k in (T.CBR_CAL_KEY, T.CBR_CAL_KEY + ":err"):
            st.write("DELETE FROM kv WHERE k=?", (k,))

    def test_parse_only_meetings(self):
        self.assertEqual(T._cbr_parse_meetings(self.PAGE), ["2026-12-18", "2027-02-13"])

    def test_next_meeting_and_error_backoff(self):
        calls = []

        def fake(url, timeout=30):
            calls.append(url)
            return self.PAGE
        with Fake(http_text=fake):
            n = T.cbr_next_meeting("2026-11-24")
        self.assertEqual(n, {"date": "2026-12-18", "days": 24})
        self.assertEqual(T.cbr_next_meeting("2026-12-18")["days"], 0)      # в день заседания — оно и есть ближайшее
        self.assertIsNone(T.cbr_next_meeting("2027-03-01"))

        st = T.store()
        st.write("UPDATE kv SET t=? WHERE k=?", (0, T.CBR_CAL_KEY))         # кэш устарел, сайт недоступен

        def down(url, timeout=30):
            calls.append(url)
            raise OSError("нет связи")
        with Fake(http_text=down):
            a = T.cbr_meetings()
            b = T.cbr_meetings()
        self.assertTrue(a.get("stale"))
        self.assertEqual(a["dates"], ["2026-12-18", "2027-02-13"])
        self.assertEqual(b["dates"], a["dates"])
        self.assertEqual(len(calls), 2)          # второй вызов не ждёт сайт: ошибка запомнена на час

    def test_payload_has_next_and_quiet_primary(self):
        def boom():
            raise RuntimeError("investmint.ru закрыл доступ для программ (HTTP 403)")
        rep = {"rows": [], "payments": [{"date": "2026-12-01", "kind": "coupon", "name": "ОФЗ", "ticker": "SU", "amount": 10.0}]}
        with Fake(cbr_meetings=lambda: {"dates": ["2026-12-18"], "ok": True}, build_bonds=lambda c, a: rep,
                  primary_rows=boom, watch_isins=lambda: [], key_rate_now=lambda: (16.5, "2026-10-27"),
                  date=type("D", (T.date,), {"today": classmethod(lambda c: T.date(2026, 11, 24))})):
            p = T.events_payload({}, "all", {"from": "2026-12-01", "to": "2026-12-31"})
        self.assertEqual(p["next_cbr"], {"date": "2026-12-18", "days": 24})
        self.assertEqual(p["key_rate"], 16.5)
        self.assertEqual(p["warnings"], [])
        self.assertEqual(len(p["notes"]), 1)
        self.assertEqual([e["kind"] for e in p["events"]], ["coupon", "cbr"])


class KeyRateNow(unittest.TestCase):
    def test_since(self):
        with Fake(key_rate_series=lambda: [["2026-10-01", 17.0], ["2026-10-27", 16.5], ["2026-10-28", 16.5]]):
            self.assertEqual(T.key_rate_now(), (16.5, "2026-10-27"))


if __name__ == "__main__":
    unittest.main()
