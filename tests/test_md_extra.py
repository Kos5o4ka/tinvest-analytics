"""md/dividends, md/fundamentals, md/reports сервера и порядок источников клиента (офлайн, поддельный MDClient и ds_parsed)."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402
import tinvest_md as md  # noqa: E402
from test_flows import FakePost, TOKEN  # noqa: E402
from test_server import Fx  # noqa: E402

m = _load.load()


def shares(n):
    return [{"ticker": "T%d" % i, "classCode": "TQBR", "uid": "u%d" % i, "assetUid": "a%d" % i} for i in range(n)] + \
           [{"ticker": "OTHER", "classCode": "SPBXM", "uid": "ux", "assetUid": "ax"}]


class Post:
    def __init__(self, n=3):
        self.n, self.calls = n, []

    def __call__(self, url, body, headers, timeout):
        b = json.loads(body.decode())
        meth = url.rsplit("/", 1)[1]
        self.calls.append((meth, b))
        if meth == "Shares":
            return 200, json.dumps({"instruments": shares(self.n)}).encode()
        if meth == "GetDividends":
            return 200, json.dumps({"dividends": [
                {"dividendNet": {"currency": "rub", "units": "10", "nano": 500000000}, "paymentDate": "2026-08-01T00:00:00Z",
                 "declaredDate": "1970-01-01T00:00:00Z", "lastBuyDate": "2026-07-10T00:00:00Z", "recordDate": "2026-07-12T00:00:00Z",
                 "yieldValue": {"units": "5", "nano": 230000000}},
                {"dividendNet": {"currency": "rub", "units": "1"}, "recordDate": "2025-07-12T00:00:00Z"},
                {"dividendNet": {"currency": "rub"}, "recordDate": "2024-07-12T00:00:00Z"}]}).encode()
        if meth == "GetAssetFundamentals":
            return 200, json.dumps({"fundamentals": [{"assetUid": a, "peRatioTtm": 4.5, "priceToBookTtm": 0, "roe": 12.0,
                                                      "dividendYieldDailyTtm": 8.0} for a in b["assets"]]}).encode()
        if meth == "GetAssetReports":
            return 200, json.dumps({"reports": [{"reportDate": "2036-12-01T00:00:00Z", "periodYear": 2026, "periodNum": 3},
                                                {"reportDate": "2037-03-01T00:00:00Z", "periodYear": 2026, "periodNum": 4},
                                                {"reportDate": "2026-01-01T00:00:00Z"}]}).encode()
        return 404, b"{}"


class Server(unittest.TestCase):
    def setUp(self):
        self.fx = Fx()
        self.fx.app.md = md.MDClient(TOKEN, post=Post(250))
        self.post = self.fx.app.md._post

    def tearDown(self):
        self.fx.close() if hasattr(self.fx, "close") else None

    def get(self, name, **kw):
        return self.fx.app.parsed(name, {k: [v] for k, v in kw.items()})

    def test_dividends(self):
        code, j = self.get("md/dividends", secid="T7")
        self.assertEqual(code, 200)
        it = j["data"]["items"]
        self.assertEqual(len(it), 2)                         # нулевой дивиденд отброшен
        self.assertEqual(it[0], {"record": "2026-07-12", "payment": "2026-08-01", "declared": None, "last_buy": "2026-07-10",
                                 "value": 10.5, "currency": "RUB", "yield_pct": 5.23})
        self.assertEqual(self.post.calls[-1][1]["instrumentId"], "u7")
        n = len(self.post.calls)
        self.get("md/dividends", secid="T7")
        self.assertEqual(len(self.post.calls), n)            # кэш
        self.assertEqual(self.get("md/dividends", secid="OTHER")[0], 404)   # не TQBR
        self.assertEqual(self.get("md/dividends")[0], 400)
        self.assertNotIn(TOKEN[2:], json.dumps(j))

    def test_fundamentals_batches_and_cache(self):
        code, j = self.get("md/fundamentals")
        self.assertEqual(code, 200)
        self.assertEqual(len(j["data"]), 250)
        self.assertEqual(sum(1 for c in self.post.calls if c[0] == "GetAssetFundamentals"), 3)
        self.assertEqual([len(c[1]["assets"]) for c in self.post.calls if c[0] == "GetAssetFundamentals"], [100, 100, 50])
        r = j["data"]["T3"]
        self.assertEqual((r["pe"], r["pb"], r["roe"], r["div_yield"]), (4.5, None, 12.0, 8.0))
        n = len(self.post.calls)
        self.get("md/fundamentals")
        self.assertEqual(len(self.post.calls), n)

    def test_reports(self):
        code, j = self.get("md/reports", secid="T1")
        self.assertEqual(code, 200)
        self.assertEqual((j["data"]["date"], j["data"]["num"]), ("2036-12-01", 3))
        n = len(self.post.calls)
        self.get("md/reports", secid="T1")
        self.assertEqual(len(self.post.calls), n)

    def test_no_token(self):
        self.fx.app.md = None
        for name, kw in (("md/dividends", {"secid": "SBER"}), ("md/fundamentals", {}), ("md/reports", {"secid": "SBER"})):
            code, j = self.get(name, **kw)
            self.assertEqual((code, j["error"]), (404, "no_token"))

    def test_upstream_error_masked(self):
        self.fx.app.md = md.MDClient(TOKEN, post=FakePost(exc=OSError("boom " + TOKEN)))
        code, j = self.get("md/fundamentals")
        self.assertEqual(code, 502)
        self.assertNotIn(TOKEN, json.dumps(j))


class Client(unittest.TestCase):
    def setUp(self):
        self.orig = m.ds_parsed
        self.calls = []

    def tearDown(self):
        m.ds_parsed = self.orig

    def test_multiples_order(self):
        def fake(name, params=None, timeout=20):
            self.calls.append(name)
            return {"SBER": {"pe": 4.0, "pb": 1.0, "ev_ebitda": None, "div_yield": 9.0, "rev_growth": 5.0, "roe": 20.0}} if name == "md/fundamentals" else None
        m.ds_parsed = fake
        r = m.stock_multiples("SBER", 1e12, None, {})
        self.assertEqual((r["pe"], r["source"], r["div_yield"]), (4.0, "tinvest-server", 9.0))
        orig = m.ifrs_multiples, m.ifrs_fin
        try:
            m.ifrs_fin = lambda t: {}
            m.ifrs_multiples = lambda f, c: {"pe": 1.0, "source": "ifrs"}
            r = m.stock_multiples("GAZP", 1e12, None, {})       # нет в ответе сервера -> МСФО
        finally:
            m.ifrs_multiples, m.ifrs_fin = orig
        self.assertEqual(r["source"], "ifrs")

    def test_own_token_skips_server(self):
        m.ds_parsed = lambda *a, **k: self.calls.append(a) or {"X": {}}
        class C:
            def __init__(self, cfg):
                pass

            def asset_fundamentals(self, u):
                return [{"assetUid": "a", "peRatioTtm": 7.0}]
        orig = m.TInvest
        try:
            m.TInvest = C
            r = m.stock_multiples("SBER", 1e12, "a", {"token": "t"})
        finally:
            m.TInvest = orig
        self.assertEqual((r["pe"], r["source"], self.calls), (7.0, "tinvest", []))

    def test_dividends_and_report_via_server(self):
        def fake(name, params=None, timeout=20):
            if name == "md/dividends":
                return {"items": [{"record": "2030-07-12", "payment": "2030-08-01", "declared": None, "last_buy": None, "value": 10.0,
                                   "currency": "RUB", "yield_pct": 5.0}]}
            return {"date": "2030-05-01", "year": 2030, "num": 1, "type": "x"}
        m.ds_parsed = fake
        orig = m._stk_iss
        try:
            m._stk_iss = lambda *a, **k: {}
            d = m.stock_dividends("SBER", 200.0, None, {})
        finally:
            m._stk_iss = orig
        self.assertEqual(d["source"], "tinvest-server")
        self.assertEqual(d["next"]["value"], 10.0)
        r = m.stock_next_report(None, {}, "SBER")
        self.assertEqual((r["date"], r["source"]), ("2030-05-01", "tinvest-server"))

    def test_screener_fast_path(self):
        uni = [{"secid": "AAA", "name": "A", "shortname": "A", "sector": "IT", "price": 1.0, "chg_d": 0, "chg_w": 0, "chg_m": 0, "cap": 1e9, "value_today": 1}]
        m.ds_parsed = lambda name, params=None, timeout=20: {"AAA": {"pe": 3.0, "div_yield": 12.0, "rev_growth": 30.0}}
        orig = m.stocks_universe
        try:
            m.stocks_universe = lambda force=False, cfg=None: uni
            res = m.stock_screener({}, force=True)
        finally:
            m.stocks_universe = orig
        self.assertEqual(res["source"], "tinvest-server")
        self.assertFalse(res["loading"])
        self.assertEqual(res["rows"][0]["tags"], ["high_div", "fast_growth"])


if __name__ == "__main__":
    unittest.main()
