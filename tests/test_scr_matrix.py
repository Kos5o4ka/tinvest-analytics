"""Матрица скринера: признаки linker / ytm_kind / days_to_offer, разбор и кэш спарклайнов (без сети)."""
import json
import unittest
from datetime import date, timedelta

from tests._load import load

T = load()


def row(i, kind="corp", mat="2035-01-01", offer=None):
    return {"id": i, "isin": "RU000" + i, "name": "X" + i, "full": "X", "kind": kind, "cur": "RUB", "nominal": 1000, "price": 99.0,
            "yield": 15.0, "dur": 2.0, "coupon": 10.0, "next": None, "mat": mat, "offer": offer, "level": 1, "turn": 1000, "trades": 5,
            "zs": None, "cy": None, "macdur": 2.0, "chg": 0, "sub": None, "size": None, "nkd": None, "btype": "", "cpn_det": None}


class ScreenerFlags(unittest.TestCase):
    def setUp(self):
        self.saved = (T.screener_rows, T.market_stats, T._stats_history, T.bench_lqdt_yield, T.kbd_curve, T.ratings_status,
                      T.inflation_forecast, T.fl_spread_cached, T.fl_spread_kick)
        today = date.today()
        self.rows = [row("A1", offer=(today + timedelta(days=40)).isoformat()),
                     row("A2", offer=(today - timedelta(days=40)).isoformat()),
                     row("A3", kind="ofz", mat="2030-01-01"),
                     row("A4", offer="2040-01-01", mat="2035-01-01")]
        self.rows[2]["id"] = "SU52005RMFS5"
        T.screener_rows = lambda: self.rows
        T.market_stats = lambda r: {"grid": []}
        T._stats_history = lambda s: {}
        T.bench_lqdt_yield = lambda: None
        T.kbd_curve = lambda: []
        T.ratings_status = lambda: {}
        T.inflation_forecast = lambda: {"source": "cbr", "as_of": "2026-10-01",
                                        "yearly": [{"year": date.today().year, "low": 5, "high": 6, "mid": 5.5}]}
        T.fl_spread_cached = lambda: {}
        T.fl_spread_kick = lambda rows, cached: False

    def tearDown(self):
        (T.screener_rows, T.market_stats, T._stats_history, T.bench_lqdt_yield, T.kbd_curve, T.ratings_status,
         T.inflation_forecast, T.fl_spread_cached, T.fl_spread_kick) = self.saved

    def test_flags(self):
        p = T.screener_payload()
        by = {r["id"]: r for r in p["rows"]}
        self.assertEqual(by["A1"]["ytm_kind"], "offer")
        self.assertEqual(by["A1"]["days_to_offer"], 40)
        self.assertEqual(by["A2"]["ytm_kind"], "mat")
        self.assertIsNone(by["A2"]["days_to_offer"])
        self.assertEqual(by["A4"]["ytm_kind"], "mat")      # оферта позже погашения — игнорируем
        self.assertTrue(by["SU52005RMFS5"]["linker"])
        self.assertFalse(by["A1"]["linker"])
        self.assertEqual(p["infl_exp"], 5.5)
        self.assertIn("Банка России", p["infl_src"])

    def test_no_forecast(self):
        T.inflation_forecast = lambda: {"source": "none", "yearly": []}
        p = T.screener_payload()
        self.assertIsNone(p["infl_exp"])


class SparkTests(unittest.TestCase):
    J = {"history": {"columns": ["TRADEDATE", "CLOSE", "LEGALCLOSEPRICE", "BOARDID"],
                     "data": [["2026-11-03", 99.5, 99.4, "TQCB"], ["2026-11-03", 88.0, None, "TQIR"],
                              ["2026-11-02", None, 99.1, "TQCB"], ["2026-11-04", None, None, "TQCB"],
                              ["2026-11-01", 98.0, None, "TQCB"]]}}

    def test_parse(self):
        self.assertEqual(T.spark_parse(self.J), [98.0, 99.1, 99.5])
        self.assertEqual(T.spark_parse(self.J, 2), [99.1, 99.5])
        self.assertEqual(T.spark_parse({}), [])

    def test_payload_cache_and_errors(self):
        calls = []
        saved = T.http_text

        def fake(url, timeout=25):
            calls.append(url)
            if "RUBAD" in url:
                raise OSError("down")
            return json.dumps(self.J)
        T.http_text = fake
        saved_many = T.ext_get_many
        T.ext_get_many = lambda urls, *a, **k: [None] * len(urls)          # без сети: пачка не пришла, по одному через http_text
        T._spark_cache.clear()
        try:
            out = T.spark_payload(["RU000A0ZZZ01", "ru000a0zzz01", "bad id!", "RUBAD0000000", "RU000A0ZZZ02"])
            self.assertEqual(out, {"RU000A0ZZZ01": [98.0, 99.1, 99.5]})       # на ошибке остановились
            n = len(calls)
            T.spark_payload(["RU000A0ZZZ01"])
            self.assertEqual(len(calls), n)                                   # из кэша
        finally:
            T.http_text = saved
            T.ext_get_many = saved_many
            T._spark_cache.clear()


if __name__ == "__main__":
    unittest.main()
