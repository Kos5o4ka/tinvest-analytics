"""«Простыня» первичных размещений: разбор ответов ISS на маленьких образцах (без сети) и живая проверка (TINVEST_LIVE=1)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()
PVK = "pv_cum1:"


def tbl(cols, rows):
    return {"columns": cols, "data": rows}


HC = ["BOARDID", "TRADEDATE", "SECID", "SHORTNAME", "NUMTRADES", "VALUE", "VOLUME", "WAPRICE", "CLOSE", "FACEVALUE"]


class ParseHistory(unittest.TestCase):
    def test_empty_rows_dropped_and_fields(self):
        j = {"history": tbl(HC, [
            ["PSAU", "2026-11-10", "RU000A10EGQ3", "ВТБС1-1726", 22, 222686280, 412382, None, 54, 1000],
            ["PSAU", "2026-11-10", "RU000A1024L7", "Томскобл20", 0, 0, 0, None, None, 200],
            ["TQCB", "2026-11-10", "RU000A10EGQ3", "ВТБС1-1726", 0, 0, 0, None, None, 1000]])}
        rows = M.pv_hist_parse(M.pv_table(j, "history"))
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["s"], r["b"], r["d"], r["q"], r["n"], r["c"], r["f"]), ("RU000A10EGQ3", "PSAU", "2026-11-10", 412382, 22, 54, 1000))

    def test_missing_table(self):
        self.assertEqual(M.pv_table({}, "history"), [])
        self.assertEqual(M.pv_table({"history": {}}, "history"), [])

    def test_aggregate_only_placement_boards(self):
        rows = [{"s": "A", "b": "PSAU", "d": "2026-11-05", "q": 100.0, "v": 90000.0, "n": 2, "nm": "A", "f": 1000},
                {"s": "A", "b": "PSAU", "d": "2026-11-06", "q": 50.0, "v": 45000.0, "n": 1, "nm": "A", "f": 1000},
                {"s": "A", "b": "TQCB", "d": "2026-11-06", "q": 999.0, "v": 9.0, "n": 9, "nm": "A", "f": 1000}]
        a = M.pv_aggregate(rows)["A"]
        self.assertEqual((a["q"], a["v"], a["n"], a["first"], a["last"]), (150.0, 135000.0, 3, "2026-11-05", "2026-11-06"))


class ParseDesc(unittest.TestCase):
    def test_desc(self):
        j = {"description": tbl(["name", "value"], [["SHORTNAME", "ВТБК4-1328"], ["NAME", "Банк ВТБ ПАО КС-4-1328"], ["ISSUEDATE", "2026-11-11"],
                                                    ["MATDATE", "0000-00-00"], ["ISSUESIZE", "50000000"], ["FACEVALUE", "1000"],
                                                    ["ISSUENAME", "Биржевые облигации дисконтные"]])}
        d = M.pv_parse_desc(j)
        self.assertEqual((d["issued"], d["mat"], d["size"], d["face"]), ("2026-11-11", "", 50000000.0, 1000.0))
        self.assertEqual(M.pv_issuer_name(d["full"]), "Банк ВТБ ПАО")


LS = ["SECID", "BOARDID", "SHORTNAME", "FACEVALUE", "ISSUESIZE", "ISSUESIZEPLACED", "COUPONPERCENT", "BONDTYPE"]
LM = ["SECID", "BOARDID", "VALTODAY", "VOLTODAY", "NUMTRADES", "WAPRICE", "YIELD"]


class LiveAndRow(unittest.TestCase):
    def test_live_parse_and_row(self):
        place = M.pv_live_parse({"securities": tbl(LS, [["X1", "PSAU", "Икс", 1000, None, None, None, None]]),
                                 "marketdata": tbl(LM, [["X1", "PSAU", 11326776232, 11330810, 948, 99.96, 0]])})["X1"]
        self.assertEqual(place[0]["today"], 11326776232)
        self.assertIsNone(place[0]["yield"])               # YIELD=0 на площадке размещения — не доходность
        bm = M.pv_live_parse({"securities": tbl(LS, [["X1", "TQCB", "Икс", 1000, 50000000, 20000000, 15.5, "Облигация с фиксированным (известным) купоном"]]),
                              "marketdata": tbl(LM, [["X1", "TQCB", 5000000, 5000, 7, 100.1, 15.2]])})["X1"]
        desc = {"name": "Икс", "full": "Банк ПАО Х-1", "issued": "2026-11-05", "size": 50000000.0, "face": 1000.0, "isin": "X1", "kind": "", "cur": "SUR"}
        agg = {"q": 8000000.0, "v": 8e9, "n": 100, "first": "2026-11-05", "last": "2026-11-06", "days": {"2026-11-05": {"q": 8e6, "v": 8e9, "n": 100}}}
        r = M.pv_build_row("X1", desc, agg, place, bm, "2026-11-11", None)
        self.assertEqual(r["status"], "placing")
        self.assertEqual(r["size_rub"], 5e10)
        self.assertEqual(r["placed_src"], "moex")                          # ISSUESIZEPLACED больше суммы сделок
        self.assertEqual(r["placed_pct"], 40.0)
        self.assertAlmostEqual(r["today"], 11326776232 + 5000000)
        self.assertEqual((r["coupon"], r["yield"]), ("15,50 %", 15.2))
        self.assertEqual(r["first_place"], "2026-11-05")

    def test_row_placed_by_trades_when_no_moex_figure(self):
        desc = {"name": "Д", "issued": "2026-11-05", "size": 1000000.0, "face": 1000.0, "kind": "Облигации дисконтные", "cur": "SUR"}
        agg = {"q": 250000.0, "v": 2.4e8, "n": 5, "first": "2026-11-05", "last": "2026-11-05", "days": {"2026-11-05": {}}}
        r = M.pv_build_row("D", desc, agg, [], None, "2026-11-11", None)
        self.assertEqual((r["status"], r["placed_src"], r["placed_pct"], r["coupon"]), ("placed", "trades", 25.0, "дисконт"))

    def test_upcoming_from_calendar(self):
        cal = [{"isin": "RU000A10GJ80", "short": "ВТБ", "issuer": "Банк ВТБ", "desc": "КС-4", "start": "2026-11-20", "rating": None},
               {"isin": "OLD", "short": "Старый", "issuer": "С", "desc": "", "start": "2026-10-01", "rating": None},
               {"isin": "KNOWN", "short": "Известный", "issuer": "И", "desc": "", "start": "2026-11-20", "rating": None}]
        up = M.pv_upcoming(cal, {"KNOWN"}, "2026-11-11")
        self.assertEqual([x["isin"] for x in up], ["RU000A10GJ80"])
        self.assertEqual(up[0]["status"], "upcoming")


class DaysMerge(unittest.TestCase):
    def test_merge_boards_and_today(self):
        rows = [{"s": "A", "b": "PSAU", "d": "2026-11-05", "q": 100.0, "v": 1000.0, "n": 2, "w": None, "c": 100.0, "y": None},
                {"s": "A", "b": "TQCB", "d": "2026-11-05", "q": 10.0, "v": 105.0, "n": 1, "w": 100.5, "c": 100.5, "y": 14.0},
                {"s": "A", "b": "TQCB", "d": "2026-11-06", "q": 20.0, "v": 200.0, "n": 3, "w": 99.0, "c": 99.0, "y": 14.5}]
        live = [{"b": "TQCB", "today": 300.0, "vol": 30.0, "n": 4, "wap": 98.0, "last": 98.0, "yield": 15.0}]
        days = M.pv_days_merge(rows, live, "2026-11-11")
        self.assertEqual([d["d"] for d in days], ["2026-11-05", "2026-11-06", "2026-11-11"])
        d0 = days[0]
        self.assertEqual((d0["q"], d0["v"], d0["n"], d0["place_v"], d0["sec_v"]), (110.0, 1105.0, 3, 1000.0, 105.0))
        self.assertEqual(d0["px"], 100.0)                                   # цена с самой оборотной площадки
        self.assertEqual(d0["boards"][0]["label"], "размещение")
        self.assertTrue(days[2]["live"])
        self.assertEqual((days[2]["v"], days[2]["y"]), (300.0, 15.0))


class BatchAndCalendar(unittest.TestCase):
    BATCH = {"securities": tbl(["SECID", "BOARDID", "SHORTNAME", "ISSUESIZE", "ISSUESIZEPLACED", "FACEVALUE"],
                               [["RU000A10AAA1", "TQCB", "Альфа1", 1000000, 500000, 1000], ["RU000A10AAA1", "TQIR", "Альфа1", 1000000, 500000, 1000]]),
             "marketdata": tbl(["SECID", "BOARDID", "VALTODAY_RUR", "VOLTODAY", "NUMTRADES"],
                               [["RU000A10AAA1", "TQCB", 1500.5, 15, 3], ["RU000A10AAA1", "TQIR", 0, 0, 0], ["RU000A10BBB2", "TQOB", 10, 1, 1]])}

    def run_compute(self, cal=None, cal_exc=None):
        saved = (M.pv_json, M.primary_rows, M.pv_days_cached, M.pv_other_boards, M.pv_live_board, M.pv_desc, M.pv_live_secid)
        calls = []

        def pj(url, timeout=30):
            calls.append(url)
            return self.BATCH

        def pr():
            if cal_exc:
                raise cal_exc
            return cal or []
        try:
            M.pv_json, M.primary_rows = pj, pr
            M.pv_days_cached = lambda dates, errs: {}
            M.pv_other_boards = lambda a, b, e: []
            M.pv_live_board = lambda mk, b: {}
            M.pv_desc = lambda s: {"issued": "2099-01-01", "name": "x", "full": "x ПАО 1", "isin": s, "face": 1000.0, "size": 1000.0}
            M.pv_live_secid = lambda s: (_ for _ in ()).throw(AssertionError("поштучный запрос не нужен"))
            M._pv_mem.clear()
            return M.pv_compute(), calls
        finally:
            M.pv_json, M.primary_rows, M.pv_days_cached, M.pv_other_boards, M.pv_live_board, M.pv_desc, M.pv_live_secid = saved

    def test_bonds_batch_parse(self):
        saved = M.pv_json
        M.pv_json = lambda url, timeout=30: self.BATCH
        try:
            b = M.pv_bonds_batch()
        finally:
            M.pv_json = saved
        self.assertEqual(sorted(b), ["RU000A10AAA1", "RU000A10BBB2"])
        self.assertEqual([m["b"] for m in b["RU000A10AAA1"]], ["TQCB", "TQIR"])
        self.assertEqual((b["RU000A10AAA1"][0]["today"], b["RU000A10AAA1"][0]["placed"]), (1500.5, 500000))

    def test_desc_old(self):
        self.assertTrue(M.pv_desc_old({"issued": "2026-01-01"}, "2026-10-01"))
        self.assertTrue(M.pv_desc_old({"issued": "", "start": "2026-01-01"}, "2026-10-01"))
        self.assertFalse(M.pv_desc_old({"issued": "2026-10-05"}, "2026-10-01"))
        self.assertFalse(M.pv_desc_old({}, "2026-10-01"))

    def test_empty_calendar_reported_and_timing(self):
        res, calls = self.run_compute(cal=[])
        self.assertTrue(any("0 строк" in e for e in res["errors"]))
        self.assertEqual({"history", "live", "calendar", "desc", "secondary"} - set(res["timing"]), set())
        self.assertEqual(sum("markets/bonds/securities.json" in u for u in calls), 1)

    def test_calendar_failure_and_ok(self):
        res, _ = self.run_compute(cal_exc=OSError("boom"))
        self.assertTrue(any("календарь" in e and "boom" in e for e in res["errors"]))
        res, _ = self.run_compute(cal=[{"isin": "RU000A10AAA1", "start": "2099-01-01", "short": "A", "issuer": "A"}])
        self.assertFalse(res["errors"])
        self.assertEqual([r["secid"] for r in res["rows"]], ["RU000A10AAA1"])


class LongPlacement(unittest.TestCase):
    """Затянувшееся размещение (старт 90 дней назад, всё ещё открыто на PSAU) не теряется и считается кумулятивно с даты старта."""

    def setUp(self):
        self.today = M.pv_msk_now().date().isoformat()
        self.start = M._day_add(self.today, -90)
        self.sid = "RU000ALONG01"
        self.calls = []
        self.saved = (M.pv_json, M.primary_rows, M.pv_days_cached, M.pv_other_boards, M.pv_live_board, M.pv_desc, M.pv_sec_hist, M.store)

        class FakeStore:
            def __init__(s):
                s.d = {}

            def get(s, k, ttl=None):
                return s.d.get(k)

            def put(s, k, v):
                s.d[k] = json.loads(json.dumps(v))
        self.st = FakeStore()
        d = lambda n: M._day_add(self.today, -n)  # noqa: E731
        self.hist = [{"s": self.sid, "b": "PSAU", "d": d(80), "q": 1000.0, "v": 1e6, "n": 3, "w": 100.0, "c": 100.0, "y": None, "nm": "L", "f": 1000},
                     {"s": self.sid, "b": "PSAU", "d": d(40), "q": 2000.0, "v": 2e6, "n": 4, "w": 100.0, "c": 100.0, "y": None, "nm": "L", "f": 1000},
                     {"s": self.sid, "b": "PSAU", "d": d(1), "q": 500.0, "v": 5e5, "n": 1, "w": 100.0, "c": 100.0, "y": None, "nm": "L", "f": 1000},
                     {"s": self.sid, "b": "TQCB", "d": d(1), "q": 77.0, "v": 77.0, "n": 1, "w": 100.0, "c": 100.0, "y": 15.0, "nm": "L", "f": 1000}]
        self.live = {self.sid: [{"b": "PSAU", "today": 3e5, "vol": 300.0, "n": 2, "last": None, "wap": 100.0, "yield": None, "placed": None}]}

        def sec_hist(mk, secid, frm, till):
            self.calls.append((mk, secid, frm, till))
            return [r for r in self.hist if mk == "ndm" and r["d"] >= frm and r["d"] <= till] if secid == self.sid else []
        M.store = lambda: self.st
        M.pv_sec_hist = sec_hist
        M.pv_json = lambda url, timeout=30: {"securities": tbl(["SECID", "BOARDID"], []), "marketdata": tbl(["SECID", "BOARDID"], [])}
        M.primary_rows = lambda: []
        M.pv_days_cached = lambda dates, errs: {}
        M.pv_other_boards = lambda a, b, e: []
        M.pv_live_board = lambda mk, b: self.live if (mk, b) == ("ndm", "PSAU") else {}
        M.pv_desc = lambda s: {"issued": self.start, "name": "Длинный", "full": "Длинный ПАО 1", "isin": s, "face": 1000.0, "size": 10000.0}
        M._pv_mem.clear()

    def tearDown(self):
        (M.pv_json, M.primary_rows, M.pv_days_cached, M.pv_other_boards, M.pv_live_board, M.pv_desc, M.pv_sec_hist, M.store) = self.saved
        M._pv_mem.clear()

    def test_long_placement_cumulative_and_cache(self):
        res = M.pv_compute()
        rows = [r for r in res["rows"] if r["secid"] == self.sid]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["status"], "placing")
        self.assertEqual(r["placed_pcs"], 3800.0)                       # 1000+2000+500+сегодня 300; TQCB не считается
        self.assertEqual(r["placed_pct"], 38.0)
        self.assertEqual(r["placed_src"], "trades")
        self.assertEqual(r["days_on"], 90)
        self.assertEqual(r["first_place"], self.start and M._day_add(self.today, -80))
        self.assertIn(PVK + self.sid, self.st.d)
        # то же число, что и в детализации по дням
        M.pv_sec_hist = lambda mk, secid, frm, till: [x for x in self.hist if mk == "ndm" and frm <= x["d"] <= till]
        M.pv_json = lambda url, timeout=30: ({"securities": tbl(LS, [[self.sid, "PSAU", "L", 1000, None, None, None, None]]),
                                              "marketdata": tbl(LM, [[self.sid, "PSAU", 3e5, 300, 2, 100.0, 0]])}
                                             if "markets/ndm/" in url else {})
        days = M.pv_secid_days(self.sid)
        self.assertEqual(sum(b["q"] for d in days["days"] for b in d["boards"] if b["place"]), r["placed_pcs"])
        # повторный вызов: из кэша, без новых запросов истории
        sec = []
        M.pv_sec_hist = lambda *a: sec.append(a) or []
        M.pv_json = lambda url, timeout=30: {"securities": tbl(["SECID", "BOARDID"], []), "marketdata": tbl(["SECID", "BOARDID"], [])}
        r2 = [x for x in M.pv_compute()["rows"] if x["secid"] == self.sid][0]
        self.assertEqual(r2["placed_pcs"], 3800.0)                      # из кэша (база + хвост в памяти), историю не качаем
        self.assertEqual(sec, [])

    def test_stale_multi_year_listing_dropped(self):
        # старт 3 года назад, на PSAU числится, но сегодня сделок нет и за 30 дней тоже — в «простыню» не попадает
        M.pv_desc = lambda s: {"issued": M._day_add(self.today, -1100), "name": "Висяк", "full": "Область 1", "isin": s, "face": 1000.0, "size": 10000.0}
        self.live[self.sid] = [{"b": "PSAU", "today": 0, "vol": 0, "n": 0, "last": None, "wap": None, "yield": None, "placed": None}]
        self.assertEqual([r for r in M.pv_compute()["rows"] if r["secid"] == self.sid], [])

    def test_cache_incremental(self):
        errs = []
        c1 = M.pv_cum(self.sid, self.start, self.today, ["ndm"], errs)
        self.assertEqual((c1["q"], c1["n"]), (3500.0, 8))
        n = len(self.calls)
        # без _pv_mem хвоста: докачка только с даты после last
        M._pv_mem.clear()
        c2 = M.pv_cum(self.sid, self.start, self.today, ["ndm"], errs)
        self.assertEqual(c2["q"], 3500.0)
        self.assertEqual(len(self.calls), n + 1)
        self.assertGreater(self.calls[-1][2], self.start)               # не с даты старта
        self.assertEqual(errs, [])
        n = len(self.calls)
        M.pv_cum(self.sid, self.start, self.today, ["ndm"], errs)       # хвост в памяти — запроса нет
        self.assertEqual(len(self.calls), n)

    def test_moex_placed_only_if_larger(self):
        desc = {"name": "Х", "issued": self.start, "size": 10000.0, "face": 1000.0}
        bm = [{"b": "TQCB", "today": 0, "vol": 0, "n": 0, "placed": 9000.0}]
        r = M.pv_build_row("X", desc, None, [], bm, self.today, None, {"q": 3000.0, "v": 3e6, "n": 5, "first": self.start})
        self.assertEqual((r["placed_pcs"], r["placed_src"]), (9000.0, "moex"))
        r = M.pv_build_row("X", desc, None, [], [dict(bm[0], placed=100.0)], self.today, None, {"q": 3000.0, "v": 3e6, "n": 5, "first": self.start})
        self.assertEqual((r["placed_pcs"], r["placed_src"]), (3000.0, "trades"))


@unittest.skipUnless(os.environ.get("TINVEST_LIVE") == "1", "живые тесты: задайте TINVEST_LIVE=1")
class LivePrimaryVolumes(unittest.TestCase):
    def test_live_compute(self):
        r = M.pv_compute()
        self.assertGreater(len(r["rows"]), 0)
        placed = [x for x in r["rows"] if x["status"] in ("placing", "placed") and x["size_rub"]]
        self.assertGreater(len(placed), 0)
        for x in placed[:50]:
            self.assertGreaterEqual(x["placed_rub"] or 0, 0)
        d = M.pv_secid_days(placed[0]["secid"])
        self.assertTrue(d["days"])
        print("\nлайв: выпусков %d, первый %s, дней %d, ошибки %s" % (len(r["rows"]), placed[0]["name"], len(d["days"]), r["errors"]))


if __name__ == "__main__":
    unittest.main()


class PrimaryCalendarUnavailable(unittest.TestCase):
    """investmint закрыл доступ программам (403): экран «Первичка» не падает, календарь пуст с пояснением, сайт не долбим повторно."""

    def test_403_is_soft_and_cached(self):
        import urllib.error
        calls = []

        def boom(url, timeout=25):
            if "investmint" in url:
                calls.append(url)
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        saved = (M.http_text, M.ds_parsed, dict(M._pri))
        try:
            M.http_text, M.ds_parsed = boom, (lambda *a, **k: None)
            M._pri.update(t=0, rows=[], err_t=0, err="")
            p = M.primary_payload()
            self.assertEqual(p["rows"], [])
            self.assertIn("403", p["cal_error"])
            M.primary_payload()                              # второй вызов — из запомненной ошибки, без запроса к сайту
            self.assertEqual(len(calls), 1)
        finally:
            M.http_text, M.ds_parsed = saved[0], saved[1]
            M._pri.clear()
            M._pri.update(saved[2])
