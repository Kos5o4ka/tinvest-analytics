"""Клиент раскрытия: объём в обращении, потоки эмитента, лента техдефолтов, маршруты; регрессия _bc_flows."""
import unittest

from tests._load import load

T = load()
TODAY = "2026-11-17"
URL = "https://e-disclosure.azipi.ru/messages/1/"


def paid(due, qty=None, derived=None, integer=True, conf=1.0, no=8):
    return {"kind": "coupon_paid", "published": due + "T10:00:00", "url": URL, "due_date": due, "event_date": due, "conf": conf,
            "data": {"qty": qty, "qty_derived": derived, "coupon_no": no, "due_date": due, "conf": conf, "checks": {"qty_integer": integer}}}


def declared(due, derived, no=9, per_bond=None, conf=0.9):
    return {"kind": "coupon_declared", "published": due + "T10:00:00", "url": URL, "due_date": due, "conf": conf,
            "data": {"qty_derived": derived, "coupon_no": no, "due_date": due, "per_bond": per_bond, "conf": conf, "checks": {"qty_integer": True}}}


def buyback(d, qty):
    return {"kind": "buyback_result", "published": d + "T10:00:00", "url": URL, "event_date": d, "conf": 1.0,
            "data": {"qty_bought": qty, "date": d, "basis": "put", "conf": 1.0}}


class Patch(unittest.TestCase):
    def patch(self, **kw):
        for k, v in kw.items():
            old = getattr(T, k)
            setattr(T, k, v)
            self.addCleanup(setattr, T, k, old)


class Outstanding(Patch):
    def setUp(self):
        self.facts = []
        self.patch(disc_facts=lambda isin=None, inn=None, kind=None: [f for f in self.facts if not kind or f["kind"] == kind],
                   _disc_issue_desc=lambda isin: {"issue_size": 2000000, "placed": 1500000, "face": 1000.0, "cur": "SUR"})

    def test_explicit(self):
        self.facts = [paid("2026-10-12", qty=1234567), paid("2026-04-12", qty=2000000, no=7)]
        o = T.bond_outstanding("RU000A0AAAA1", TODAY)
        self.assertEqual((o["qty"], o["method"], o["coupon_no"], o["as_of"], o["doc_url"]), (1234567, "coupon_explicit", 8, "2026-10-12", URL))
        self.assertEqual(o["share"], round(1234567 / 2000000, 4))
        self.assertEqual(o["issue_size"], 2000000)

    def test_derived_and_low_conf_skipped(self):
        self.facts = [paid("2026-10-12", qty=5, conf=0.3), paid("2026-07-12", derived=1500000)]
        o = T.bond_outstanding("RU000A0AAAA1", TODAY)
        self.assertEqual((o["qty"], o["method"]), (1500000, "coupon_derived"))
        self.facts = [paid("2026-10-12", derived=1500000, integer=False)]
        self.assertEqual(T.bond_outstanding("RU000A0AAAA1", TODAY)["method"], "issue_placed")

    def test_declared(self):
        self.facts = [declared("2026-11-10", 1800000)]
        o = T.bond_outstanding("RU000A0AAAA1", TODAY)
        self.assertEqual((o["qty"], o["method"], o["coupon_no"]), (1800000, "declared_derived", 9))

    def test_buyback_after_and_floor(self):
        self.facts = [paid("2026-10-12", qty=1000000), buyback("2026-10-20", 300000), buyback("2026-09-01", 999999)]
        o = T.bond_outstanding("RU000A0AAAA1", TODAY)
        self.assertEqual((o["qty"], o["buybacks_after"]), (700000, 1))
        self.facts = [paid("2026-10-12", qty=1000), buyback("2026-10-20", 5000)]
        self.assertEqual(T.bond_outstanding("RU000A0AAAA1", TODAY)["qty"], 0)

    def test_cap_at_issue_size(self):
        self.facts = [paid("2026-10-12", qty=9000000)]
        self.assertEqual(T.bond_outstanding("RU000A0AAAA1", TODAY)["qty"], 2000000)

    def test_fallbacks(self):
        o = T.bond_outstanding("RU000A0AAAA1", TODAY)
        self.assertEqual((o["qty"], o["method"], o["doc_url"]), (1500000, "issue_placed", None))
        self.patch(_disc_issue_desc=lambda isin: {"issue_size": 2000000})
        o = T.bond_outstanding("RU000A0AAAA1", TODAY)
        self.assertEqual((o["qty"], o["method"], o["share"]), (2000000, "issue_size", 1.0))
        self.patch(_disc_issue_desc=lambda isin: {})
        self.assertIsNone(T.bond_outstanding("RU000A0AAAA1", TODAY)["qty"])


class FactsCache(Patch):
    def test_cache_and_off(self):
        calls = []
        self.patch(ds_parsed=lambda name, params=None, timeout=20: calls.append((name, params)) or [{"kind": "x"}])
        a = T.disc_facts(isin="RU000A0CACH1")
        b = T.disc_facts(isin="ru000a0cach1")
        self.assertEqual((a, b, len(calls)), ([{"kind": "x"}], [{"kind": "x"}], 1))
        self.patch(ds_parsed=lambda *a, **k: None)
        self.assertEqual(T.disc_facts(isin="RU000A0CACH2"), [])
        self.assertEqual(T.disc_facts(), [])


def bz_a():
    return {"ok": True, "coupons": [{"coupondate": "2026-12-10", "value": 30.0}, {"coupondate": "2027-03-10", "value": 30.0}],
            "amort": [{"amortdate": "2027-03-10", "value": 250.0}, {"amortdate": "2027-06-10", "value": 750.0}],
            "offers": [{"offerdate": "2027-04-01", "price": 100.0}]}


def bz_b():
    return {"ok": True, "coupons": [{"coupondate": "2026-12-20", "value": 40.0}, {"coupondate": "2027-03-20", "value": None}],
            "amort": [{"amortdate": "2027-05-20", "value": 1000.0}], "offers": []}


class Flows(Patch):
    def setUp(self):
        self.patch(
            _iss_bonds_of=lambda inn: [{"isin": "RU000A0AAAA1", "secid": "A", "name": "Аморт 1", "traded": True},
                                       {"isin": "RU000A0BBBB2", "secid": "B", "name": "Флоат 2", "traded": True},
                                       {"isin": "RU000A0CCCC3", "secid": "C", "name": "Погашен", "traded": False}],
            moex_bondization=lambda isin: {"RU000A0AAAA1": bz_a, "RU000A0BBBB2": bz_b}.get(isin, lambda: None)(),
            bond_outstanding=lambda isin, today=None, desc=None: {"qty": {"RU000A0AAAA1": 1000, "RU000A0BBBB2": 500}[isin], "method": "coupon_explicit"},
            _disc_issue_desc=lambda isin: {"face": 1000.0, "cur": "SUR"},
            disc_facts=lambda isin=None, inn=None, kind=None: [],
            fl_estimates=lambda bz, today, face, path=None: {"2027-03-20": {"amt": 25.0, "rate": 15.0, "base": 14.0, "spread": 1.0}},
            moex_bond_options=lambda isin: {"put": [], "call": ["2027-02-15"] if isin == "RU000A0BBBB2" else []},
            issuer_of=lambda isin: {"short": "Эмитент", "title": "Эмитент ООО", "inn": "7700000000"})

    def test_totals_and_months(self):
        r = T.issuer_cashflows("7700000000", 8, TODAY)
        self.assertEqual([m["m"] for m in r["months"]][:3], ["2026-11", "2026-12", "2027-01"])
        self.assertEqual(len(r["months"]), 8)
        self.assertEqual(r["name"], "Эмитент")
        self.assertEqual([b["isin"] for b in r["bonds"]], ["RU000A0AAAA1", "RU000A0BBBB2"])
        mo = {m["m"]: m for m in r["months"]}
        self.assertEqual(mo["2026-12"]["coupon"], 30000 + 20000)
        self.assertEqual(mo["2026-12"]["by_bond"], {"RU000A0AAAA1": 30000.0, "RU000A0BBBB2": 20000.0})
        self.assertEqual((mo["2027-03"]["amort"], mo["2027-03"]["coupon"]), (250000.0, 30000 + 12500))
        self.assertTrue(mo["2027-03"]["est"])
        self.assertEqual(mo["2027-03"]["est_by_bond"], {"RU000A0BBBB2": 12500.0})
        self.assertEqual(mo["2027-04"]["put"], 750 * 1000)           # остаток номинала после амортизации
        self.assertEqual(mo["2027-02"]["call"], 1000 * 500)
        self.assertTrue(mo["2027-03"]["after_call"] and not mo["2026-12"]["after_call"])
        self.assertEqual(mo["2027-06"]["redemption"], 750000.0)
        self.assertEqual(mo["2027-05"]["redemption"], 500000.0)
        self.assertEqual(r["totals"]["payments"], 1060000 + 532500)
        self.assertEqual((r["totals"]["call"], r["dates"]), (500000, 8))

    def test_missing_data_warns(self):
        self.patch(moex_bondization=lambda isin: bz_a() if isin == "RU000A0AAAA1" else None)
        r = T.issuer_cashflows("7700000000", 8, TODAY)
        self.assertEqual([b["isin"] for b in r["bonds"]], ["RU000A0AAAA1"])
        self.assertTrue(any("RU000A0BBBB2" in w for w in r["warnings"]))
        self.patch(_iss_bonds_of=lambda inn: (_ for _ in ()).throw(RuntimeError("net")))
        r = T.issuer_cashflows("7700000000", 3, TODAY)
        self.assertEqual((r["bonds"], r["totals"]["payments"]), ([], 0))

    def test_declared_rate_for_unknown_coupon(self):
        decl = {"kind": "coupon_declared", "conf": 0.9, "data": {"due_date": "2027-03-20", "per_bond": 33.0, "conf": 0.9}}
        self.patch(disc_facts=lambda isin=None, inn=None, kind=None: [decl] if isin == "RU000A0BBBB2" else [])
        mo = {m["m"]: m for m in T.issuer_cashflows("7700000000", 8, TODAY)["months"]}
        self.assertEqual(mo["2027-03"]["coupon"], 30000 + 16500)
        self.assertFalse(mo["2027-03"]["est"])

    def test_foreign_currency(self):
        self.patch(_disc_issue_desc=lambda isin: {"face": 1000.0, "cur": "USD"}, tax_cbr_rate=lambda cur, iso: 90.0)
        mo = {m["m"]: m for m in T.issuer_cashflows("7700000000", 3, TODAY)["months"]}
        self.assertEqual(mo["2026-12"]["by_bond"]["RU000A0AAAA1"], 30 * 1000 * 90.0)


class Defaults(Patch):
    def test_feed_shape(self):
        fact = {"doc_id": 5, "title": "Сообщение", "published": "2026-11-10T09:00:00", "url": URL, "isin": "RU000A0DDDD4", "inn": "7701234567",
                "kind": "default", "due_date": "2026-11-01", "conf": 0.95,
                "data": {"status": "technical", "obligation": "coupon", "coupon_no": 4, "amount": 1500000.0, "due_date": "2026-11-01"}}
        self.patch(ds_parsed=lambda name, params=None, timeout=20: [fact] if name == "disclosure/defaults" else None,
                   issuer_of=lambda isin: {"short": "Эмитент Д", "title": "Эмитент Д ООО", "inn": "7701234567"},
                   disc_facts=lambda isin=None, inn=None, kind=None: [paid("2026-11-12", qty=10, no=4)] if kind == "coupon_paid" else [],
                   _mon_flags=lambda isin: {"tech": isin == "RU000A0EEEE5", "default": False})
        rows = T.defaults_feed("2026-10-01", ["RU000A0EEEE5", "RU000A0FFFF6", "RU000A0DDDD4"])
        self.assertEqual(len(rows), 2)
        r = rows[0]
        self.assertEqual((r["date"], r["status"], r["issuer"], r["inn"], r["isin"], r["obligation"], r["amount"], r["executed"], r["basis"], r["url"]),
                         ("2026-11-10", "technical", "Эмитент Д", "7701234567", "RU000A0DDDD4", "Купон №4", 1500000.0, "2026-11-12",
                          "Сообщение эмитента", URL))
        f = rows[1]
        self.assertEqual((f["isin"], f["basis"], f["date"], f["executed"], f["status"]), ("RU000A0EEEE5", "Флаг Мосбиржи", None, None, "technical"))

    def test_feed_server_off(self):
        self.patch(ds_parsed=lambda *a, **k: None)
        self.assertEqual(T.defaults_feed("2026-10-01"), [])


class Routes(Patch):
    def test_routes(self):
        self.patch(ds_parsed=lambda *a, **k: None, _disc_issue_desc=lambda isin: {"issue_size": 100, "placed": 80})
        self.assertIn("/api/disclosure", T.API_GET)
        d = T.API_GET["/api/disclosure"]({}, None, {"isin": "RU000A0AAAA1"}, True)
        self.assertEqual((d["outstanding"]["qty"], d["facts"], d["isin"]), (80, [], "RU000A0AAAA1"))
        self.assertIn("error", T.API_GET["/api/disclosure"]({}, None, {"isin": "x"}, True))
        self.patch(issuer_cashflows=lambda inn, h=25, today=None: {"inn": inn, "months": [], "h": h})
        self.assertEqual(T.API_GET["/api/issuer_flows"]({}, None, {"inn": "7700000000", "months": "12"}, True)["h"], 12)
        self.assertIn("error", T.API_GET["/api/issuer_flows"]({}, None, {"inn": "abc"}, True))
        self.patch(_disc_own_isins=lambda cfg, acc: [])
        r = T.API_GET["/api/defaults"]({}, None, {"days": "7"}, True)
        self.assertEqual((r["rows"], "since" in r, "configured" in r), ([], True, True))


class BondCardFlows(Patch):
    def test_amort_and_redemption(self):
        self.patch(moex_bondization=lambda isin: {"coupons": [{"coupondate": "2099-01-01", "value": 30, "valueprc": 6}],
                                                  "amort": [{"amortdate": "2099-02-01", "value": 250, "valueprc": 25},
                                                            {"amortdate": "2099-03-01", "value": 750, "valueprc": 75},
                                                            {"amortdate": "2001-01-01", "value": 1, "valueprc": 1}],
                                                  "offers": [{"offerdate": "2099-02-15", "price": 100}]})
        ev = T._bc_flows("RU000A0AAAA1")
        self.assertEqual([(e["d"], e["t"], e["amt"]) for e in ev],
                         [("2099-01-01", "coupon", 30), ("2099-02-01", "amort", 250), ("2099-02-15", "offer", None), ("2099-03-01", "redemption", 750)])


if __name__ == "__main__":
    unittest.main()
