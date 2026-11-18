"""Акции: разбор ISS, свечи, дивиденды, мультипликаторы, скринер (офлайн, синтетический JSON ISS)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402
from test_ifrs import CORP, page  # noqa: E402

m = _load.load()

SEC_COLS = ["SECID", "BOARDID", "SHORTNAME", "PREVPRICE", "LOTSIZE", "SECNAME", "ISSUESIZE", "ISIN"]
MD_COLS = ["SECID", "LAST", "VALTODAY", "ISSUECAPITALIZATION", "LASTTOPREVPRICE"]
ISS = {"securities": {"columns": SEC_COLS, "data": [
    ["SBER", "TQBR", "Сбербанк", 300.0, 1, "Сбербанк России ПАО ао", 21586948000, "RU0009029540"],
    ["ZZZZ", "TQBR", "Нет сделок", 10.0, 10, "Без цены", 1000, "RU000A000000"],
    ["NOPR", "TQBR", "Нет цены", None, 1, "Нет цены", 5, "RU000A000001"],
    ["GAZP", "TQBR", "Газпром", 100.0, 10, "Газпром ао", 1000, "RU0007661625"]]},
    "marketdata": {"columns": MD_COLS, "data": [
        ["SBER", 306.0, 5e9, 6.6e12, 2.0], ["ZZZZ", None, 0, None, None], ["GAZP", 95.0, 3e9, None, -5.0]]}}


class Universe(unittest.TestCase):
    def test_rows(self):
        rows = {r["secid"]: r for r in m.stk_rows_from_iss(ISS, m.STK_SECTORS)}
        self.assertEqual(set(rows), {"SBER", "ZZZZ", "GAZP"})          # без цены и без предыдущей цены — пропуск
        s = rows["SBER"]
        self.assertEqual((s["price"], s["prev"], s["chg_d"], s["lot"], s["sector"]), (306.0, 300.0, 2.0, 1, "Банки и финансы"))
        self.assertEqual(s["cap"], 6.6e12)
        self.assertEqual(s["value_today"], 5e9)
        self.assertIsNone(s["chg_w"])
        g = rows["GAZP"]
        self.assertAlmostEqual(g["cap"], 95.0 * 1000)                  # нет капитализации — цена × выпуск
        self.assertEqual(g["chg_d"], -5.0)
        self.assertEqual(rows["ZZZZ"]["price"], 10.0)                  # торгов не было — предыдущая цена
        self.assertEqual(rows["ZZZZ"]["chg_d"], 0.0)
        self.assertEqual(rows["ZZZZ"]["sector"], "Прочее")

    def test_fund_split(self):
        cols = SEC_COLS + ["SECTYPE", "INSTRID"]
        sec = {"columns": cols, "data": [
            ["SBER", "TQBR", "Сбербанк", 300.0, 1, "Сбербанк", 1000, "RU1", "1", "EQIN"],
            ["LQDT", "TQBR", "LQDT", 2.0, 1, "ВИМ ликвидность", 1000, "RU2", "J", "IFTF"],
            ["TMOS", "TQBR", "TMOS", 7.0, 1, "Тинькофф iMOEX", 1000, "RU3", "J", "IFTF"],
            ["RU000A109QR5", "TQBR", "ААА Золото", 5.0, 1, "ААА Золото", 1000, "RU4", "9", "IFA1"],
            ["XXXXXX", "TQBR", "Рентал ПРО", 5.0, 1, "Рентал ПРО", 1000, "RU5", "B", "IFA1"]]}
        md = {"columns": MD_COLS, "data": [["LQDT", 2.1, 1e9, None, None]]}
        rows = {r["secid"]: r for r in m.stk_rows_from_iss({"securities": sec, "marketdata": md}, m.STK_SECTORS)}
        self.assertFalse(rows["SBER"]["is_fund"])
        self.assertTrue(rows["LQDT"]["is_fund"] and rows["LQDT"]["instrid"] == "IFTF")
        orig = (m._stk_iss, m.stock_candles, m.stock_history_closes)
        try:
            m._stk_iss = lambda path, timeout=25: {"securities": sec, "marketdata": md}
            m.stock_candles = lambda s, i=24, d=400: []
            m.mem_clear()
            st = {r["secid"] for r in m.stocks_universe(force=True)}
            fu = {r["secid"]: r for r in m.funds_universe()}
        finally:
            m._stk_iss, m.stock_candles, m.stock_history_closes = orig
            m.mem_clear()
        self.assertEqual(st, {"SBER"})
        self.assertEqual(set(fu), {"LQDT", "TMOS", "RU000A109QR5", "XXXXXX"})
        self.assertEqual((fu["LQDT"]["sector"], fu["TMOS"]["sector"]), ("Денежный рынок", "Акции"))
        self.assertEqual((fu["RU000A109QR5"]["sector"], fu["XXXXXX"]["sector"]), ("Золото и металлы", "Прочие фонды"))

    def test_fund_fallback_tqtf(self):
        paths = []
        orig = (m._stk_iss, m.stock_candles)
        try:
            def fake(path, timeout=25):
                paths.append(path)
                return ISS
            m._stk_iss = fake
            m.stock_candles = lambda s, i=24, d=400: []
            m.mem_clear()
            fu = m.funds_universe()
        finally:
            m._stk_iss, m.stock_candles = orig
            m.mem_clear()
        self.assertTrue(any("TQTF" in p for p in paths))
        self.assertTrue(fu and all(r["is_fund"] for r in fu))

    def test_fund_category(self):
        c = m.stk_fund_category
        self.assertEqual(c("SBGB", ""), "Облигации")
        self.assertEqual(c("ZZZ", "ПИФ Облигации"), "Облигации")
        self.assertEqual(c("ZZZ", "РСХБ Акции"), "Акции")
        self.assertEqual(c("ZZZ", "Какой-то ЗПИФ"), "Прочие фонды")

    def test_sector_table(self):
        self.assertEqual(m.STK_SECTORS["LKOH"], "Нефть и газ")
        self.assertGreater(len(m.STK_SECTORS), 120)
        self.assertTrue(set(m.STK_SECTORS.values()) <= set(m.STK_SECTOR_NAMES))

    def test_universe_with_changes(self):
        calls = []
        orig = (m._stk_iss, m.stock_candles, m.stock_history_closes)
        try:
            m._stk_iss = lambda path, timeout=25: ISS
            days = ["2026-10-%02d" % d for d in range(1, 29)]
            m.stock_candles = lambda s, i=24, d=400: [{"t": x} for x in days]
            m.stock_history_closes = lambda d: calls.append(d) or {"SBER": 270.0 if d == days[-1 - 5] else 300.0, "GAZP": 100.0}
            m.mem_clear()
            rows = {r["secid"]: r for r in m.stocks_universe(force=True)}
        finally:
            m._stk_iss, m.stock_candles, m.stock_history_closes = orig
            m.mem_clear()
        self.assertEqual(calls, [days[-1 - 5], days[-1 - 21]])
        self.assertAlmostEqual(rows["SBER"]["chg_w"], (306 / 270 - 1) * 100, places=2)
        self.assertAlmostEqual(rows["SBER"]["chg_m"], 2.0)
        self.assertIsNone(rows["ZZZZ"]["chg_w"])

    def test_history_closes_paging_and_cache(self):
        def hist(n, start):
            return {"history": {"columns": ["SECID", "CLOSE"], "data": [["T%d" % i, 1.5] for i in range(start, min(n, start + 100))] + [["NONE", None]] * (1 if start == 0 else 0)},
                    "history.cursor": {"columns": ["INDEX", "TOTAL", "PAGESIZE"], "data": [[start, 230, 100]]}}
        got = []
        orig = m._stk_iss
        try:
            def fake(path, timeout=25):
                start = int(path.rsplit("start=", 1)[1])
                got.append(start)
                return hist(230, start)
            m._stk_iss = fake
            r = m.stock_history_closes("2020-01-02")
            self.assertEqual(sorted(got), [0, 100, 200])
            self.assertEqual(len(r), 230)
            self.assertNotIn("NONE", r)
            m.stock_history_closes("2020-01-02")
            self.assertEqual(len(got), 3)                              # прошлая дата — из кэша
        finally:
            m._stk_iss = orig


class Candles(unittest.TestCase):
    ROWS = [{"open": 1, "close": 2, "high": 3, "low": 0.5, "volume": 10, "begin": "2026-11-01 00:00:00"},
            {"open": None, "close": 2, "high": 3, "low": 1, "volume": 1, "begin": "2026-11-02 00:00:00"}]

    def test_parse(self):
        d = m.stk_candles_from_iss(self.ROWS, 24)
        self.assertEqual(d, [{"t": "2026-11-01", "o": 1.0, "h": 3.0, "l": 0.5, "c": 2.0, "v": 10.0}])
        self.assertEqual(m.stk_candles_from_iss([dict(self.ROWS[0], begin="2026-11-01 10:00:00")], 60)[0]["t"], "2026-11-01 10:00")

    def test_paging(self):
        pages = []
        orig = m._stk_iss
        try:
            def fake(path, timeout=25):
                start = int(path.rsplit("start=", 1)[1])
                pages.append(start)
                n = 500 if start == 0 else 3
                return {"candles": {"columns": list(self.ROWS[0]), "data": [[1, 2, 3, 0.5, 10, "2026-01-01 00:00:00"] for _ in range(n)]}}
            m._stk_iss = fake
            out = m.stock_candles("TESTX", 24, 123)
        finally:
            m._stk_iss = orig
        self.assertEqual(pages, [0, 500])
        self.assertEqual(len(out), 503)


class Dividends(unittest.TestCase):
    def test_build(self):
        iss = m.stk_iss_dividends({"dividends": {"columns": ["secid", "registryclosedate", "value", "currencyid"],
                                                 "data": [["SBER", "2025-07-18", 34.84, "RUB"], ["SBER", "2024-07-11", 33.3, "RUB"], ["SBER", "2026-07-17", 0, "RUB"]]}})
        self.assertEqual(len(iss), 2)
        api = m.stk_api_dividends([{"dividendNet": {"units": "36", "nano": 0, "currency": "rub"}, "recordDate": "2026-07-20T00:00:00Z",
                                    "paymentDate": "2026-07-30T00:00:00Z", "declaredDate": "2026-05-01T00:00:00Z"},
                                   {"dividendNet": {"units": "34", "nano": 840000000, "currency": "rub"}, "recordDate": "2025-07-18T00:00:00Z"}])
        r = m.stk_dividends_build(iss + api, 300.0, today="2026-06-01")
        self.assertEqual([x["record"] for x in r["items"]], ["2026-07-20", "2025-07-18", "2024-07-11"])
        self.assertEqual(r["next"]["record"], "2026-07-20")
        self.assertTrue(r["items"][0]["future"])
        self.assertAlmostEqual(r["yield_ttm"], 34.84 / 300 * 100, places=2)         # в TTM только выплата 2025-07-18
        self.assertEqual(r["items"][1]["src"], "tinvest")                          # при совпадении даты берётся T-Invest
        self.assertAlmostEqual(r["items"][0]["yield_pct"], 12.0)

    def test_empty(self):
        r = m.stk_dividends_build([], 100.0)
        self.assertEqual((r["items"], r["yield_ttm"], r["next"]), ([], None, None))


class Multiples(unittest.TestCase):
    def test_fund(self):
        x = m.stk_from_fund({"peRatioTtm": 4.5, "priceToBookTtm": 0, "evToEbitdaMrq": 3.2, "dividendYieldDailyTtm": 11.0,
                             "oneYearAnnualRevenueGrowthRate": 25.0, "roe": 22.0, "netDebtToEbitda": 0.5})
        self.assertEqual((x["pe"], x["pb"], x["ev_ebitda"], x["div_yield"], x["rev_growth"], x["roe"]), (4.5, None, 3.2, 11.0, 25.0, 22.0))
        self.assertEqual(m.stk_from_fund({"forwardAnnualDividendYield": 7.0})["div_yield"], 7.0)

    def test_ifrs(self):
        parsed = m.ifrs_parse(page(CORP))
        fin = m.ifrs_build(parsed, "TEST")
        x = m.ifrs_multiples(fin, 2.5e12)
        self.assertAlmostEqual(x["pe"], 20.0)
        self.assertAlmostEqual(x["pb"], 2.0)
        self.assertAlmostEqual(x["ev_ebitda"], (2_500_000 + 850_000) / 380_000)
        self.assertAlmostEqual(x["roe"], 10.0)
        self.assertAlmostEqual(x["nd_ebitda"], 850 / 380)
        self.assertAlmostEqual(x["rev_growth"], (1200 / 1100 - 1) * 100)
        self.assertEqual(m.ifrs_multiples({"status": "nodata"}, 1e12)["pe"], None)


def row(secid, sector, **kw):
    r = {"secid": secid, "sector": sector, "pe": None, "div_yield": None, "rev_growth": None}
    r.update(kw)
    return r


class Screener(unittest.TestCase):
    def test_tags(self):
        rows = m.stk_tags([row("A", "Банки", pe=3.0), row("B", "Банки", pe=5.0), row("C", "Банки", pe=9.0), row("D", "Банки", pe=-2.0),
                           row("E", "Банки", pe=6.0, div_yield=12.0, rev_growth=30.0), row("F", "Один", pe=2.0)])
        t = {r["secid"]: r["tags"] for r in rows}
        self.assertEqual(rows[0]["pe_sector"], 5.5)                      # медиана 3, 5, 6, 9 (убыток не считается)
        self.assertIn("cheap_pe", t["A"])
        self.assertIn("cheap_pe", t["B"])
        self.assertNotIn("cheap_pe", t["C"])
        self.assertNotIn("cheap_pe", t["D"])                             # P/E < 0 — не «дёшево»
        self.assertEqual(t["E"], ["high_div", "fast_growth"])            # P/E 6 выше медианы 5,5
        self.assertEqual(rows[-1]["pe_sector"], m.stk_median([3, 5, 9, 6, 2]))  # в секторе меньше 3 значений — медиана рынка

    def test_build_ifrs_path(self):
        uni = [{"secid": "TEST", "name": "Тест", "shortname": "Тест", "sector": "Прочее", "price": 100.0, "chg_d": 1.0, "chg_w": 2.0, "chg_m": 3.0,
                "cap": 2.5e12, "value_today": 1.0},
               {"secid": "NOCAP", "name": "x", "shortname": "x", "sector": "Прочее", "price": 1, "chg_d": 0, "chg_w": 0, "chg_m": 0, "cap": None, "value_today": 0}]
        fin = m.ifrs_build(m.ifrs_parse(page(CORP)), "TEST")
        orig = (m.stocks_universe, m.ifrs_fin)
        seen = []
        try:
            m.stocks_universe = lambda force=False, cfg=None: uni
            m.ifrs_fin = lambda t: fin
            res = m.stk_screener_build({}, lambda d, n: seen.append((d, n)))
        finally:
            m.stocks_universe, m.ifrs_fin = orig
        self.assertEqual(res["source"], "ifrs")
        self.assertEqual([r["secid"] for r in res["rows"]], ["TEST"])
        self.assertAlmostEqual(res["rows"][0]["pe"], 20.0)
        self.assertEqual(seen, [(1, 1)])
        self.assertEqual([p["id"] for p in res["presets"]], ["cheap_pe", "high_div", "fast_growth"])

    def test_build_token_path(self):
        uni = [{"secid": "AAA", "name": "A", "shortname": "A", "sector": "IT", "price": 1.0, "chg_d": 0, "chg_w": 0, "chg_m": 0, "cap": 1e9,
                "value_today": 1, "asset_uid": "uid-a"}]
        class FakeClient:
            def __init__(self, cfg):
                pass

            def asset_fundamentals(self, uids):
                assert uids == ["uid-a"]
                return [{"assetUid": "uid-a", "peRatioTtm": 4.0, "dividendYieldDailyTtm": 12.0, "oneYearAnnualRevenueGrowthRate": 40.0}]
        orig = (m.stocks_universe, m.TInvest)
        try:
            m.stocks_universe = lambda force=False, cfg=None: uni
            m.TInvest = FakeClient
            res = m.stk_screener_build({"token": "t"})
        finally:
            m.stocks_universe, m.TInvest = orig
        self.assertEqual(res["source"], "tinvest")
        self.assertEqual(res["rows"][0]["tags"], ["high_div", "fast_growth"])      # одна бумага в секторе: медиана P/E = её же P/E, не «дешевле»


class ApiClient(unittest.TestCase):
    def test_requests(self):
        calls = []

        class C(m.TInvest):
            def __init__(self):
                self.token = "x"

            def call(self, service, method, body=None, timeout=60):
                calls.append((service, method, body))
                return {"fundamentals": [{"assetUid": b} for b in body.get("assets", [])]} if method == "GetAssetFundamentals" else {}
        c = C()
        self.assertEqual(len(c.asset_fundamentals(["u%d" % i for i in range(230)])), 230)
        self.assertEqual([len(x[2]["assets"]) for x in calls], [100, 100, 30])
        c.asset_reports("a", "F", "T")
        c.order_book("i", 10)
        c.last_trades("i", "F", "T")
        self.assertEqual([x[:2] for x in calls[3:]], [("InstrumentsService", "GetAssetReports"), ("MarketDataService", "GetOrderBook"),
                                                      ("MarketDataService", "GetLastTrades")])
        self.assertEqual(calls[4][2], {"instrumentId": "i", "depth": 10})


if __name__ == "__main__":
    unittest.main()
