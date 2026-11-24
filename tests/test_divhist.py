"""Длинная история дивидендов (dohod.ru): разбор страницы, слияние с данными T-Invest, кэш и сбои сети. Офлайн, на фикстурах."""
import os
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()
FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return f.read()


TODAY = "2026-11-23"


class Parse(unittest.TestCase):
    def test_sber_rows_depth_and_forecast_split(self):
        r = M.dh_parse(fx("dohod_sber.html"), TODAY)
        rows = r["rows"]
        self.assertEqual(r["currency"], "RUB")
        self.assertEqual(rows[0]["record"], "2026-07-20")
        self.assertEqual(rows[0]["value"], 37.64)
        self.assertEqual(rows[0]["declared"], "2026-04-21")
        self.assertEqual(rows[0]["status"], "paid")
        self.assertEqual(rows[-1]["record"][:4], "2000")
        self.assertTrue(all(x["status"] in ("paid", "approved") for x in rows))
        self.assertEqual([u["status"] for u in r["upcoming"]], ["forecast"])        # прогноз не смешивается с историей
        self.assertNotIn("2027-07-20", [x["record"] for x in rows])

    def test_duplicate_source_rows_collapsed(self):
        recs = [(x["record"], x["value"]) for x in M.dh_parse(fx("dohod_sber.html"), TODAY)["rows"]]
        self.assertEqual(len(recs), len(set(recs)))

    def test_recommended_and_forecast_statuses(self):
        r = M.dh_parse(fx("dohod_mtss.html"), TODAY)
        st = {u["record"]: u["status"] for u in r["upcoming"]}
        self.assertEqual(st["2027-01-18"], "recommended")                          # строка с отметкой «рекомендовано советом директоров»
        self.assertEqual(st["2027-07-15"], "forecast")
        self.assertEqual(r["rows"][0]["record"], "2026-07-09")

    def test_future_with_declared_date_is_approved(self):
        r = M.dh_parse(fx("dohod_sber.html"), "2026-06-01")
        self.assertEqual(r["rows"][0]["status"], "approved")
        self.assertEqual(r["rows"][1]["status"], "paid")

    def test_column_order_by_headers(self):
        html = ("<table><tr><th>Дивиденд</th><th>Дата закрытия реестра</th><th>Дата объявления дивиденда</th></tr>"
                "<tr><td>1,5</td><td>10.07.2020</td><td>01.06.2020</td></tr></table>")
        r = M.dh_parse(html, TODAY)
        self.assertEqual((r["rows"][0]["record"], r["rows"][0]["value"], r["rows"][0]["declared"]), ("2020-07-10", 1.5, "2020-06-01"))

    def test_bad_markup_and_garbage(self):
        self.assertIsNone(M.dh_parse("<html><body>нет таблиц</body></html>", TODAY))
        self.assertIsNone(M.dh_parse("", TODAY))
        self.assertIsNone(M.dh_parse(None, TODAY))
        self.assertEqual(M.dh_parse("<table><tr><th>Дата закрытия реестра</th><th>Дивиденд</th></tr><tr><td>x</td><td>y</td></tr></table>", TODAY)["rows"], [])

    def test_currency_from_header(self):
        html = ("<p>Дивиденд (USD)</p><table><tr><th>Дата закрытия реестра</th><th>Дивиденд</th></tr>"
                "<tr><td>10.07.2020</td><td>2</td></tr></table>")
        self.assertEqual(M.dh_parse(html, TODAY)["rows"][0]["cur"], "USD")

    def test_slug(self):
        self.assertEqual(M.dh_slug("SBERP"), "sberp")
        self.assertIsNone(M.dh_slug("../x"))
        self.assertIsNone(M.dh_slug(""))


def it(rec, val, src="tinvest", cur="RUB"):
    return {"record": rec, "value": val, "cur": cur, "src": src, "payment": None, "declared": None, "last_buy": None}


def h(rec, val, status="paid", cur="RUB"):
    return {"record": rec, "value": val, "cur": cur, "status": status, "src": "dohod", "declared": None}


class Merge(unittest.TestCase):
    def test_adds_only_earlier_years_main_source_wins(self):
        base = [it("2024-07-11", 33.3), it("2025-07-18", 34.84)]
        hist = [h("2025-07-18", 34.84), h("2024-07-11", 33.4), h("2023-05-11", 25.0), h("2019-06-13", 16.0), h("2024-12-01", 5.0)]
        out, n, scale = M.dh_merge(base, hist, TODAY)
        self.assertEqual(n, 2)                                                     # 2023 и 2019; 2024-12-01 внутри покрытого периода — не берём
        self.assertIsNone(scale)
        self.assertEqual(sorted(x["record"] for x in out), ["2019-06-13", "2023-05-11", "2024-07-11", "2025-07-18"])
        self.assertEqual([x["src"] for x in out if x["record"] in ("2024-07-11", "2025-07-18")], ["tinvest", "tinvest"])
        self.assertEqual({x["src"] for x in out if x["record"] < "2024"}, {"dohod"})

    def test_dedup_date_and_sum_tolerance(self):
        base = [it("2023-05-11", 25.0)]
        out, n, _ = M.dh_merge(base, [h("2023-05-13", 25.2), h("2023-05-14", 25.0), h("2023-05-11", 26.0)], TODAY)
        self.assertEqual(n, 0)                                                     # внутри покрытого периода всё дедуплицируется / не добавляется
        out, n, _ = M.dh_merge([it("2024-07-11", 33.3)], [h("2022-05-11", 25.0), h("2022-05-13", 25.1), h("2022-05-20", 25.0)], TODAY)
        self.assertEqual(sorted(x["record"] for x in out if x["src"] == "dohod"), ["2022-05-11", "2022-05-20"])

    def test_forecast_and_recommended_never_merged(self):
        out, n, _ = M.dh_merge([it("2024-07-11", 33.3)], [h("2020-07-01", 1.0, "forecast"), h("2021-07-01", 2.0, "recommended")], TODAY)
        self.assertEqual(n, 0)

    def test_empty_main_source_takes_all(self):
        out, n, _ = M.dh_merge([], [h("2025-07-18", 34.84), h("2020-07-01", 1.0)], TODAY)
        self.assertEqual(n, 2)

    def test_split_scale_detected_on_overlap(self):
        base = [it("2023-12-26", 915.0), it("2024-06-10", 1000.0)]
        hist = [h("2023-12-26", 9.15), h("2024-06-10", 10.0), h("2022-06-14", 11.66)]
        out, n, scale = M.dh_merge(base, hist, TODAY)
        self.assertEqual(n, 1)
        self.assertAlmostEqual(scale, 100.0, places=3)
        old = [x for x in out if x["src"] == "dohod"][0]
        self.assertAlmostEqual(old["value"], 1166.0, places=2)
        self.assertEqual(old["scaled"], scale)

    def test_small_mismatch_is_not_a_split(self):
        _, _, scale = M.dh_merge([it("2024-07-11", 33.3)], [h("2024-07-11", 30.0), h("2020-07-01", 5.0)], TODAY)
        self.assertIsNone(scale)

    def test_input_not_mutated(self):
        base = [it("2024-07-11", 33.3)]
        M.dh_merge(base, [h("2020-07-01", 5.0)], TODAY)
        self.assertEqual(len(base), 1)

    def test_other_currency_not_dedup_against_rub(self):
        out, n, _ = M.dh_merge([it("2024-07-11", 1.0)], [h("2024-07-11", 1.0, cur="USD")], TODAY)
        self.assertEqual(n, 0)                                                     # покрытый период: не добавляем


class CacheAndErrors(unittest.TestCase):
    def setUp(self):
        self.calls = 0
        M.store().put("dh_v1_sber", None)
        try:
            M.store().write("DELETE FROM kv WHERE k LIKE 'dh_v1_%'")
        except Exception:  # noqa: BLE001
            pass

    def ok_fetch(self, url):
        self.calls += 1
        return fx("dohod_sber.html")

    def test_cache_hit_no_second_request(self):
        a = M.dh_history("SBER", TODAY, self.ok_fetch)
        b = M.dh_history("SBER", TODAY, self.ok_fetch)
        self.assertEqual((a["status"], self.calls), ("ok", 1))
        self.assertEqual(len(b["rows"]), len(a["rows"]))

    def test_network_error_falls_back_to_stale_ok(self):
        M.dh_history("SBER", TODAY, self.ok_fetch)
        hit = M.store().get("dh_v1_sber")
        hit["fetched"] -= M.DH_TTL + 10                                           # кэш протух

        M.store().put("dh_v1_sber", hit)

        def boom(url):
            raise OSError("нет сети")
        r = M.dh_history("SBER", TODAY, boom)
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["rows"])
        self.assertIn("недоступен", r["note"])
        calls = []
        r2 = M.dh_history("SBER", TODAY, lambda u: calls.append(u) or fx("dohod_sber.html"))
        self.assertEqual(calls, [])                                               # в течение часа не долбим источник
        self.assertEqual(r2["status"], "ok")

    def test_error_without_cache_does_not_raise(self):
        def boom(url):
            raise urllib.error.HTTPError(url, 503, "x", {}, None)
        r = M.dh_history("LKOH", TODAY, boom)
        self.assertEqual((r["status"], r["rows"]), ("err", []))

    def test_404_is_nodata(self):
        def nf(url):
            raise urllib.error.HTTPError(url, 404, "x", {}, None)
        self.assertEqual(M.dh_history("ZZZZ", TODAY, nf)["status"], "nodata")

    def test_bad_markup_keeps_old_history(self):
        M.dh_history("SBER", TODAY, self.ok_fetch)
        hit = M.store().get("dh_v1_sber")
        hit["fetched"] -= M.DH_TTL + 10
        M.store().put("dh_v1_sber", hit)
        r = M.dh_history("SBER", TODAY, lambda u: "<html>ничего</html>")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["rows"])

    def test_invalid_ticker_no_request(self):
        r = M.dh_history("../etc", TODAY, lambda u: 1 / 0)
        self.assertEqual(r["status"], "nodata")


class StockDividendsIntegration(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(M, k) for k in ("dh_history", "ds_parsed")}
        rows = M.dh_parse(fx("dohod_sber.html"), TODAY)["rows"]
        M.dh_history = lambda secid, today=None, fetch=None: {"status": "ok", "rows": rows, "upcoming": [], "url": "https://www.dohod.ru/x"}
        srv = {"items": [{"record": "2025-07-18", "payment": None, "value": 34.84, "currency": "RUB"},
                         {"record": "2026-07-20", "payment": None, "value": 37.64, "currency": "RUB"}]}
        M.ds_parsed = lambda n, p=None, **k: srv

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(M, k, v)

    def test_history_flag_extends_and_labels_sources(self):
        r = M.stock_dividends("SBER", 300.0, history=True)
        recs = [x["record"] for x in r["items"]]
        self.assertEqual(recs, sorted(recs, reverse=True))
        self.assertTrue(r["items"][-1]["record"].startswith("2000"))
        self.assertGreater(r["hist"]["years"], 10)
        self.assertEqual(r["hist"]["from"][:4], "2000")
        by = {x["record"]: x["src"] for x in r["items"]}
        self.assertEqual(by["2026-07-20"], "tinvest")
        self.assertEqual(r["source"], "tinvest-server")

    def test_without_flag_unchanged(self):
        r = M.stock_dividends("SBER", 300.0)
        self.assertEqual(len(r["items"]), 2)
        self.assertNotIn("hist", r)

    def test_dohod_failure_keeps_main_data(self):
        M.dh_history = lambda *a, **k: 1 / 0
        r = M.stock_dividends("SBER", 300.0, history=True)
        self.assertEqual(len(r["items"]), 2)
        self.assertEqual(r["hist"]["status"], "err")

    def test_guest_without_any_source_gets_dohod(self):
        M.ds_parsed = lambda *a, **k: None
        r = M.stock_dividends("SBER", 300.0, history=True)
        self.assertEqual(r["source"], "dohod")
        self.assertGreater(len(r["items"]), 10)

    def test_two_payments_same_record_date_kept(self):
        r = M.stk_dividends_build([it("2022-12-21", 256.0), it("2022-12-21", 537.0)], 6000.0, TODAY)
        self.assertEqual(len(r["items"]), 2)


if __name__ == "__main__":
    unittest.main()
