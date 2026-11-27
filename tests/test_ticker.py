"""Бегущая строка котировок: разбор ответов источников и сборка (офлайн, на фикстурах)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

m = _load.load()

CETS = {"marketdata": {"columns": ["SECID", "LAST", "LASTCHANGEPRC", "NUMTRADES"], "data": [
    ["USD000UTSTOM", 80.0, 0.1, 0], ["CNYRUB_TOM", 11.2, -0.5, 1200], ["EUR_RUB__TOM", None, None, 0],
    ["GLDRUB_TOM", 10500.5, 1.234, 300], ["XXX", 1, 1, 1]]}}
CBR = ('<ValCurs><Valute ID="R01235"><CharCode>USD</CharCode><Nominal>1</Nominal><Value>90,5</Value></Valute>'
       '<Valute ID="R01375"><CharCode>CNY</CharCode><Nominal>10</Nominal><Value>125,0</Value></Valute></ValCurs>')


class TickerTest(unittest.TestCase):
    def test_index(self):
        j = {"marketdata": {"columns": ["SECID", "CURRENTVALUE", "LASTCHANGEPRC"], "data": [["IMOEX", 2750.4, -0.31]]}}
        it = m.tk_parse_index(j)
        self.assertEqual((it["id"], it["price"], it["chg"], it["kind"]), ("IMOEX", 2750.4, -0.31, "index"))
        self.assertIsNone(m.tk_parse_index({}))

    def test_stocks_order_and_missing(self):
        rows = [{"secid": "GAZP", "price": 150, "chg_d": 1.0}, {"secid": "SBER", "price": 300, "chg_d": None}, {"secid": "ZZZZ", "price": 1}]
        its = m.tk_parse_stocks(rows)
        self.assertEqual([i["id"] for i in its], ["SBER", "GAZP"])
        self.assertIsNone(its[0]["chg"])

    def test_cets_skips_no_trades(self):
        r = m.tk_parse_cets(CETS)
        self.assertEqual(set(r), {"CNY", "GOLD"})
        self.assertEqual(r["GOLD"]["chg"], 1.23)

    def test_cbr_fallback(self):
        cur, prev = m.tk_parse_cbr(CBR), {"USD": 90.0}
        self.assertAlmostEqual(cur["CNY"], 12.5)
        r = m.tk_cbr_items(cur, prev, ["USD", "CNY", "EUR"])
        self.assertEqual(set(r), {"USD", "CNY"})
        self.assertAlmostEqual(r["USD"]["chg"], 0.56, places=2)
        self.assertIsNone(r["CNY"]["chg"])

    def test_btc(self):
        a = m.tk_parse_btc({"bitcoin": {"usd": 65000, "usd_24h_change": 2.5}}, "coingecko")
        b = m.tk_parse_btc({"lastPrice": "64900.1", "priceChangePercent": "-1.2"}, "binance")
        self.assertEqual((a["price"], a["unit"]), (65000.0, "$"))
        self.assertEqual(b["chg"], -1.2)
        self.assertIsNone(m.tk_parse_btc({}, "coingecko"))

    def test_payload_resilient(self):
        saved = {k: getattr(m, k) for k in ("tk_fetch_index", "tk_fetch_cets", "tk_fetch_cbr", "tk_fetch_btc", "stocks_universe")}

        def boom(*a, **k):
            raise RuntimeError("down")
        try:
            m.mem_clear()
            m.tk_fetch_index = boom
            m.stocks_universe = lambda force=False: [{"secid": "SBER", "price": 300, "chg_d": 1.5}]
            m.tk_fetch_cets = lambda: m.tk_parse_cets(CETS)
            m.tk_fetch_cbr = lambda want: m.tk_cbr_items(m.tk_parse_cbr(CBR), {}, want)
            m.tk_fetch_btc = lambda: m.tk_parse_btc({"lastPrice": "1", "priceChangePercent": "0"}, "binance")
            p = m.ticker_payload(True)
            self.assertEqual([i["id"] for i in p["items"]], ["SBER", "USD", "CNY", "GOLD", "BTC"])
        finally:
            for k, v in saved.items():
                setattr(m, k, v)
            m.mem_clear()

    def test_payload_nonblocking_btc(self):
        saved = {k: getattr(m, k) for k in ("tk_fetch_index", "tk_fetch_cets", "tk_fetch_cbr", "tk_fetch_btc", "stocks_universe")}
        try:
            m.mem_clear()
            m.tk_fetch_index = lambda: m.tk_parse_index({"marketdata": {"columns": ["SECID", "CURRENTVALUE", "LASTCHANGEPRC"], "data": [["IMOEX", 2750.0, 0.1]]}})
            m.stocks_universe = lambda force=False: [{"secid": "SBER", "price": 300, "chg_d": 1.0}]
            m.tk_fetch_cets = lambda: m.tk_parse_cets(CETS)
            m.tk_fetch_cbr = lambda want: m.tk_cbr_items(m.tk_parse_cbr(CBR), {}, want)

            def slow_btc():
                time.sleep(0.6)
                return m.tk_parse_btc({"lastPrice": "90000", "priceChangePercent": "1.5"}, "binance")

            m.tk_fetch_btc = slow_btc
            t0 = time.time()
            p1 = m.ticker_payload(False)
            dt1 = time.time() - t0
            self.assertLess(dt1, 0.55)          # холодный старт не ждёт медленный BTC дольше короткого порога
            self.assertIn("SBER", [i["id"] for i in p1["items"]])

            for _ in range(30):
                if m.mem_get(("tk_btc",), 60):
                    break
                time.sleep(0.05)

            # После прогрева BTC появляется в ответе сразу
            p2 = m.ticker_payload(False)
            self.assertIn("BTC", [i["id"] for i in p2["items"]])

            # Истёкший кэш BTC не блокирует тёплый ответ ticker_payload(False)
            m._mem.pop(("tk_btc",), None)
            t1 = time.time()
            p3 = m.ticker_payload(False)
            self.assertLess(time.time() - t1, 0.15)
            self.assertIn("SBER", [i["id"] for i in p3["items"]])
        finally:
            for _ in range(30):
                if not m._tk_btc_running[0]:
                    break
                time.sleep(0.05)
            for k, v in saved.items():
                setattr(m, k, v)
            m.mem_clear()


if __name__ == "__main__":
    unittest.main()
