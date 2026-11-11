"""«Простыня» первичных размещений: разбор ответов ISS на маленьких образцах (без сети) и живая проверка (TINVEST_LIVE=1)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


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
        self.assertEqual(r["placed_src"], "moex")                          # ISSUESIZEPLACED приоритетнее суммы сделок
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
