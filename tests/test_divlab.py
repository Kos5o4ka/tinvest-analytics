"""Дивидендные гэпы: закрытие гэпа, незакрытые и свежие события, статистика, выигрыш/проигрыш, надёжность, API с замоканной сетью. Офлайн."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

T = load()


def wdays(n, start=date(2025, 1, 6)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def candles(ds, price=100.0, over=None):
    """Ровные свечи: open=close=price, high=price+0.5; over: {индекс: {поле: значение}}."""
    out = []
    for i, d in enumerate(ds):
        c = {"t": d, "o": price, "h": price + 0.5, "l": price - 0.5, "c": price, "v": 1.0}
        c.update((over or {}).get(i, {}))
        out.append(c)
    return out


class Gaps(unittest.TestCase):
    def setUp(self):
        self.ds = wdays(80)
        self.rec = self.ds[20]            # дата фиксации; последний день покупки = ds[19], гэп = ds[20]

    def gap(self, over, div=10.0, n_end=None):
        cs = candles(self.ds[:n_end] if n_end else self.ds, 100.0, over)
        return T.dl_gaps([{"record": self.rec, "value": div, "cur": "RUB"}], cs)

    def test_closes_on_day_k(self):
        over = {i: {"o": 90.0, "h": 92.0, "c": 91.0} for i in range(20, 80)}
        over[25] = {"o": 95.0, "h": 100.0, "c": 99.0}          # день гэпа ds[20] = k0, ds[25] = k5
        g = self.gap(over)[0]
        self.assertEqual(g["last_buy"], self.ds[19])
        self.assertEqual(g["gap_day"], self.ds[20])
        self.assertEqual(g["p_pre"], 100.0)
        self.assertEqual(g["p_post"], 90.0)
        self.assertEqual(g["gap"], 10.0)
        self.assertEqual(g["gap_pct"], 10.0)
        self.assertEqual(g["k"], 1.0)
        self.assertTrue(g["closed"])
        self.assertEqual(g["days"], 5)

    def test_closed_same_day(self):
        g = self.gap({20: {"o": 92.0, "h": 101.0, "c": 99.0}})[0]
        self.assertTrue(g["closed"])
        self.assertEqual(g["days"], 0)

    def test_never_closes(self):
        over = {i: {"o": 90.0, "h": 95.0 if i < 40 else 93.0, "c": 91.0} for i in range(20, 80)}
        g = self.gap(over)[0]
        self.assertFalse(g["closed"])
        self.assertIsNone(g["days"])
        self.assertEqual(g["recovery_pct"], 50.0)               # макс. high 95: (95-90)/(100-90)
        self.assertEqual(g["n_after"], 59)

    def test_missing_open_falls_back_to_close(self):
        over = {20: {"o": None, "h": 96.0, "c": 94.0}}
        g = self.gap(over)[0]
        self.assertEqual(g["p_post"], 94.0)
        self.assertEqual(g["gap"], 6.0)

    def test_last_buy_field_used(self):
        cs = candles(self.ds, 100.0, {i: {"o": 90.0, "h": 92.0, "c": 91.0} for i in range(18, 80)})
        d = [{"record": self.rec, "value": 10, "cur": "RUB", "last_buy": self.ds[17]}]
        g = T.dl_gaps(d, cs)[0]
        self.assertEqual(g["last_buy"], self.ds[17])
        self.assertEqual(g["gap_day"], self.ds[18])

    def test_skips_uncovered_and_foreign_currency(self):
        cs = candles(self.ds)
        divs = [{"record": "2020-01-01", "value": 5, "cur": "RUB"}, {"record": "2030-01-01", "value": 5, "cur": "RUB"},
                {"record": self.rec, "value": 5, "cur": "USD"}, {"record": self.rec, "value": 0, "cur": "RUB"}]
        self.assertEqual(T.dl_gaps(divs, cs), [])
        self.assertEqual(T.dl_gaps(divs, []), [])

    def test_too_recent_is_not_judged(self):
        g = self.gap({i: {"o": 90.0, "h": 92.0, "c": 91.0} for i in range(20, 30)}, n_end=30)[0]
        self.assertFalse(g["closed"])
        self.assertEqual(g["n_after"], 9)
        st = T.dl_stats([g])
        self.assertEqual(st["still_open"], 1)
        self.assertEqual(st["within"]["30"], {"n": 0, "of": 0, "pct": None})


class Stats(unittest.TestCase):
    @staticmethod
    def g(days, n_after=200, k=1.0, closed=True):
        return {"closed": closed, "days": days, "n_after": n_after, "k": k, "gap_pct": 5.0}

    def test_percentages_and_median(self):
        gs = [self.g(0), self.g(10), self.g(40), self.g(100), self.g(None, 200, closed=False), self.g(None, 20, closed=False)]
        st = T.dl_stats(gs)
        self.assertEqual(st["count"], 6)
        self.assertEqual(st["closed"], 4)
        self.assertEqual(st["median_days"], 25.0)                  # медиана 0, 10, 40, 100
        self.assertEqual(st["within"]["30"], {"n": 2, "of": 5, "pct": 40.0})     # свежий (20 дн.) в знаменатель не входит
        self.assertEqual(st["within"]["60"]["n"], 3)
        self.assertEqual(st["within"]["90"]["n"], 3)
        self.assertEqual(st["still_open"], 1)
        hist = {h["label"]: h["n"] for h in st["hist"]}
        self.assertEqual(hist["в день отсечки"], 1)
        self.assertEqual(hist["6–20 дн."], 1)
        self.assertEqual(hist["не закрыт"], 1)
        self.assertEqual(hist["ещё открыт"], 1)

    def test_empty(self):
        st = T.dl_stats([])
        self.assertEqual(st["count"], 0)
        self.assertIsNone(st["median_days"])
        self.assertIsNone(st["avg_k"])

    def test_avg_k(self):
        st = T.dl_stats([self.g(1, k=0.5), self.g(2, k=1.5)])
        self.assertEqual(st["avg_k"], 1.0)


class Payoff(unittest.TestCase):
    def test_numbers(self):
        p = T.dl_payoff(10.0, 100.0, 90.0, 80.0, 0.13, 0.001)
        self.assertAlmostEqual(p["hold"], 10 * 0.87 - 10)          # -1.3
        self.assertAlmostEqual(p["p_buy"], 91.0)
        # (90-91) - 2*0.001*100 - 0.13*(100-80) = -1 - 0.2 - 2.6: откупили дороже открытия, заплатили комиссии и налог
        self.assertAlmostEqual(p["sell_rebuy"], -3.8)
        self.assertAlmostEqual(p["diff"], -3.8 + 1.3)
        self.assertEqual(p["gap_pct"], 10.0)

    def test_no_tax_when_cost_above_price(self):
        p = T.dl_payoff(10.0, 100.0, 90.0, 120.0, 0.13, 0.0)
        self.assertEqual(p["tax_sale"], 0.0)
        self.assertAlmostEqual(p["sell_rebuy"], -1.0)

    def test_unknown_cost(self):
        p = T.dl_payoff(10.0, 100.0, 90.0, None, 0.13, 0.0)
        self.assertFalse(p["cost_known"])
        self.assertEqual(p["tax_sale"], 0.0)


class LastBuyRule(unittest.TestCase):
    def test_t2_before_august_2023(self):
        cs = []
        for i, d in enumerate(("2023-06-01", "2023-06-02", "2023-06-05", "2023-06-06", "2023-06-07")):
            cs.append({"t": d, "o": 100.0, "h": 100.0, "l": 90.0, "c": 100.0 if i < 1 else 90.0})
        g = T.dl_gaps([{"record": "2023-06-05", "value": 10, "cur": "RUB"}], cs)[0]
        self.assertEqual(g["last_buy"], "2023-06-01")          # T+2: за два торговых дня до фиксации
        self.assertEqual(g["p_pre"], 100.0)
        g = T.dl_gaps([{"record": "2023-06-05", "value": 10, "cur": "RUB", "last_buy": "2023-06-02"}], cs)[0]
        self.assertEqual(g["last_buy"], "2023-06-01")          # last_buy по правилу T+1 для старой отсечки игнорируется

    def test_t1_after_august_2023(self):
        cs = [{"t": d, "o": 100.0, "h": 100.0, "l": 90.0, "c": c} for d, c in
              (("2024-06-03", 100.0), ("2024-06-04", 100.0), ("2024-06-05", 90.0), ("2024-06-06", 90.0))]
        g = T.dl_gaps([{"record": "2024-06-05", "value": 10, "cur": "RUB"}], cs)[0]
        self.assertEqual(g["last_buy"], "2024-06-04")


class Safety(unittest.TestCase):
    def test_full_score(self):
        s = T.dl_safety({"fcf": 150.0, "div_total": 100.0, "nd_ebitda": 1.0, "pay_years": 6, "roe": 25.0})
        self.assertEqual(s["score"], 100)
        self.assertEqual(s["label"], "надёжно")
        self.assertEqual(s["flags"], [])

    def test_fcf_below_dividends_flag(self):
        s = T.dl_safety({"fcf": 10.0, "div_total": 100.0, "nd_ebitda": 3.0, "pay_years": 3, "roe": 5.0})
        self.assertEqual([c["points"] for c in s["components"]], [0, 10, 15, 0])
        self.assertEqual(s["score"], 25)
        self.assertEqual(s["zone"], "neg")
        self.assertIn("дивиденды больше свободного денежного потока", s["flags"])

    def test_tiers(self):
        pts = lambda f: T.dl_safety(dict({"fcf": 100.0, "div_total": 100.0, "nd_ebitda": 1.0, "pay_years": 5, "roe": 15.0}, **f))["components"]  # noqa: E731
        self.assertEqual(pts({})[0]["points"], 30)
        self.assertEqual(pts({"fcf": 70.0})[0]["points"], 15)
        self.assertEqual(pts({"nd_ebitda": 2.0})[1]["points"], 20)
        self.assertEqual(pts({"nd_ebitda": 3.4})[1]["points"], 10)
        self.assertEqual(pts({"pay_years": 1})[2]["points"], 5)

    def test_missing_components_rescaled(self):
        s = T.dl_safety({"fcf": 150.0, "div_total": 100.0, "nd_ebitda": None, "pay_years": 6, "roe": None})
        self.assertEqual(s["available_weight"], 60)
        self.assertEqual(s["score"], 100)                          # 60 из 60
        self.assertFalse(s["components"][1]["available"])
        self.assertEqual(s["components"][1]["note"], "нет данных")

    def test_too_little_data(self):
        s = T.dl_safety({"fcf": None, "div_total": None, "nd_ebitda": 1.0, "pay_years": None, "roe": 12.0})
        self.assertEqual(s["available_weight"], 40)
        self.assertIsNone(s["score"])
        self.assertIsNotNone(s["note"])

    def test_bank_excludes_net_debt(self):
        s = T.dl_safety({"bank": True, "net": 300.0, "div_total": 100.0, "nd_ebitda": 9.0, "pay_years": 5, "roe": 22.0})
        nd = s["components"][1]
        self.assertFalse(nd["available"])
        self.assertEqual(s["available_weight"], 70)
        self.assertEqual(s["score"], 100)

    def test_bank_payout_component(self):
        base = {"bank": True, "div_total": 100.0, "pay_years": 5, "roe": 22.0}
        for net, pts in ((300.0, 40), (160.0, 28), (120.0, 16), (100.0, 8), (80.0, 0), (-5.0, 0)):
            s = T.dl_safety(dict(base, net=net))
            c = s["components"][0]
            self.assertEqual((c["name"], c["points"]), ("Покрытие дивидендов прибылью", pts))
            self.assertIsNotNone(s["score"])
        self.assertIsNone(T.dl_safety(dict(base))["score"])        # нет net -> по-прежнему мало данных

    def test_nonbank_unchanged(self):
        s = T.dl_safety({"fcf": 130.0, "net": 1.0, "div_total": 100.0, "nd_ebitda": 1.0, "pay_years": 5, "roe": 22.0})
        self.assertEqual((s["components"][0]["name"], s["score"]), ("Покрытие дивидендов свободным денежным потоком", 100))

    def test_zones(self):
        self.assertEqual(T.dl_zone(80)[1], "надёжно")
        self.assertEqual(T.dl_zone(79)[1], "умеренно")
        self.assertEqual(T.dl_zone(49)[1], "высокий риск")

    def test_streak(self):
        self.assertEqual(T.dl_streak({2022, 2023, 2024, 2025}, 2026), 4)
        self.assertEqual(T.dl_streak({2020, 2021, 2024}, 2026), 0)
        self.assertEqual(T.dl_streak({2025, 2026}, 2026), 2)


class Api(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(T, k) for k in ("stock_candles", "stock_dividends", "stocks_universe", "ifrs_fin", "stock_multiples", "build_summary")}
        self.ds = wdays(200, date(2025, 1, 6))
        rec = self.ds[100]
        over = {i: {"o": 90.0, "h": 92.0, "c": 91.0} for i in range(100, 200)}
        over[110] = {"o": 95.0, "h": 101.0, "c": 99.0}
        self.cs = candles(self.ds, 100.0, over)
        self.fut = (date.today() + timedelta(days=20)).isoformat()
        T.stock_candles = lambda secid, interval=24, days=400: self.cs
        T.stock_dividends = lambda secid, price, uid=None, cfg=None: {
            "items": [{"record": rec, "value": 10.0, "cur": "RUB", "payment": None, "last_buy": None},
                      {"record": self.fut, "value": 12.0, "cur": "RUB", "payment": None, "last_buy": None}], "ttm_value": 10.0, "source": "test"}
        T.stocks_universe = lambda force=False, cfg=None: [{"secid": "TST", "shortname": "Тест", "sector": "Прочее", "price": 100.0, "cap": 1e9, "uid": "u"}]
        T.ifrs_fin = lambda t: {"status": "ok", "bank": False, "years": [], "ltm": {"fcf": 200.0, "nd_ebitda": 1.0, "roe": 0.2}}
        T.stock_multiples = lambda *a, **k: {"nd_ebitda": 1.0, "roe": 20.0}
        T.build_summary = lambda cfg, acc, period, force=False: {"portfolio": {"positions": [
            {"type": "share", "ticker": "TST", "name": "Тест", "qty": 10.0, "avg": 80.0, "price": 100.0},
            {"type": "bond", "ticker": "X", "qty": 1.0}]}}
        T.store().delete_prefix("dl_v1_")

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(T, k, v)
        T.store().delete_prefix("dl_v1_")

    def test_stock(self):
        r = T.API_GET["/api/divlab"]({}, "all", {"secid": "tst"}, True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["secid"], "TST")
        self.assertEqual(r["stats"]["count"], 1)
        self.assertEqual(r["stats"]["median_days"], 10.0)
        self.assertEqual(r["gaps"][0]["days"], 10)
        self.assertEqual(r["next"]["record"], self.fut)
        self.assertTrue(r["next"]["upcoming"])
        p = r["payoff"]
        self.assertFalse(p["held"])                                # без параметра account позиции не подмешиваются
        self.assertAlmostEqual(p["gap"], 12.0)                     # k=1: ожидаемый гэп = дивиденд
        self.assertEqual(r["safety"]["label"], "надёжно")
        self.assertIsNone(r["error"])

    def test_stock_with_position_cost(self):
        r = T.API_GET["/api/divlab"]({}, "all", {"secid": "TST", "account": "all"}, False)
        self.assertTrue(r["payoff"]["held"])
        self.assertEqual(r["payoff"]["qty"], 10.0)
        self.assertGreater(r["payoff"]["tax_sale"], 0)

    def test_portfolio(self):
        r = T.API_GET["/api/divlab"]({}, "all", {"account": "all"}, True)
        self.assertEqual(r["mode"], "portfolio")
        self.assertEqual(r["held"], 1)
        row = r["rows"][0]
        self.assertEqual(row["secid"], "TST")
        self.assertEqual(row["next"]["value"], 12.0)
        self.assertAlmostEqual(row["net_total"], 12.0 * 10 * 0.87, places=2)
        self.assertEqual(row["median_days"], 10.0)
        self.assertEqual(row["label"], "надёжно")

    def test_network_errors_are_soft(self):
        def boom(*a, **k):
            raise OSError("нет сети")
        T.stock_candles = boom
        T.stock_dividends = boom
        r = T.API_GET["/api/divlab"]({}, "all", {"secid": "TST"}, True)
        self.assertTrue(r["ok"])
        self.assertIn("недоступны", r["error"])
        self.assertEqual(r["gaps"], [])

    def test_no_positions(self):
        T.build_summary = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("нет токена"))
        r = T.API_GET["/api/divlab"]({}, "all", {}, False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["rows"], [])
        self.assertTrue(r["error"])

    def test_bad_ticker(self):
        with self.assertRaises(T.ApiError):
            T.API_GET["/api/divlab"]({}, "all", {"secid": "!!"}, False)


if __name__ == "__main__":
    unittest.main()
