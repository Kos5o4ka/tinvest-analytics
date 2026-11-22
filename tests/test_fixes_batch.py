"""Пакет исправлений: дивиденды без ISS, imp:-акции в календаре, котировки MOEX, id переводов, ghost-портфель, маркеры капчи, crowd verified."""
import json
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import _load  # noqa: E402

M = _load.load()


def patched(**kw):
    class Ctx:
        def __enter__(self):
            self.old = {k: getattr(M, k) for k in kw}
            for k, v in kw.items():
                setattr(M, k, v)

        def __exit__(self, *a):
            for k, v in self.old.items():
                setattr(M, k, v)
    return Ctx()


class StockDividendsNoIss(unittest.TestCase):
    def test_no_iss_call_and_empty_structure(self):
        def boom(*a, **k):
            raise AssertionError("ISS не должен вызываться")
        with patched(_stk_iss=boom, ds_parsed=lambda *a, **k: None):
            r = M.stock_dividends("SBER", 300.0)
        self.assertEqual((r["items"], r["next"], r["yield_ttm"]), ([], None, None))
        self.assertFalse(hasattr(M, "stk_iss_dividends"))

    def test_guest_uses_server(self):
        srv = {"items": [{"record": "2099-07-18", "payment": None, "value": 34.84, "currency": "RUB"}]}
        with patched(ds_parsed=lambda n, p=None, **k: srv):
            r = M.stock_dividends("SBER", 300.0)
        self.assertEqual(r["source"], "tinvest-server")
        self.assertEqual(r["items"][0]["record"], "2099-07-18")


class MoexQuotes(unittest.TestCase):
    def fake(self, calls):
        def http(url, timeout=25):
            calls.append(url)
            if "securities.json" in url:
                return json.dumps({"securities": {"columns": ["secid", "isin", "primary_boardid", "group", "is_traded"], "data": [
                    ["SBERP", "RU0009029557", "TQBR", "stock_shares", 1],
                    ["SBER", "RU0009029540", "TQBR", "stock_shares", 1],
                    ["SU26238RMFS4", "RU000A1038V6", "TQOB", "stock_bonds", 1]]}})
            if "/bonds/" in url:
                return json.dumps({"securities": {"columns": ["SECID", "PREVPRICE", "FACEVALUE", "ACCRUEDINT", "CURRENCYID"],
                                                  "data": [["SU26238RMFS4", 70.0, 1000, 12.5, "SUR"]]},
                                   "marketdata": {"columns": ["SECID", "LAST"], "data": [["SU26238RMFS4", 71.5]]}})
            return json.dumps({"securities": {"columns": ["SECID", "PREVPRICE", "CURRENCYID"], "data": [["SBER", 300.0, "SUR"]]},
                               "marketdata": {"columns": ["SECID", "LAST"], "data": [["SBER", None]]}})
        return http

    def test_quotes(self):
        calls = []
        M.store().delete_prefix("mq")
        with patched(http_text=self.fake(calls)):
            q = M.moex_quotes(["RU0009029540", "RU000A1038V6", ""])
            self.assertEqual(q["RU0009029540"]["secid"], "SBER")
            self.assertEqual((q["RU0009029540"]["type"], q["RU0009029540"]["price"]), ("share", 300.0))   # LAST пуст -> PREVPRICE
            b = q["RU000A1038V6"]
            self.assertEqual((b["type"], b["nkd"]), ("bond", 12.5))
            self.assertAlmostEqual(b["price"], 715.0)
            n = len(calls)
            M.moex_quotes(["RU0009029540"])
            self.assertEqual(len(calls), n)                                  # из кэша
            self.assertEqual(M.moex_secid("RU000A1038V6"), "SU26238RMFS4")

    def test_network_error_never_raises(self):
        def bad(url, timeout=25):
            raise OSError("нет сети")
        M.store().delete_prefix("mq")
        with patched(http_text=bad):
            self.assertEqual(M.moex_quotes(["RU0009029540", "ZZZ"]), {})
            self.assertIsNone(M.moex_secid("ZZZ"))

    def test_imported_positions_uses_moex(self):
        ops = [{"id": "x1", "instrumentUid": "imp:RU0009029540", "name": "Сбер", "type": "OPERATION_TYPE_BUY", "instrumentKind": "INSTRUMENT_TYPE_SHARE",
                "date": "2026-01-10T10:00:00Z", "quantity": "10", "quantityDone": "10", "state": "OPERATION_STATE_EXECUTED",
                "price": {"units": "250", "nano": 0, "currency": "rub"}, "payment": {"units": "-2500", "nano": 0, "currency": "rub"}}]

        class C:
            ready = False
        with patched(moex_quotes=lambda ids: {"RU0009029540": {"price": 300.0, "nkd": 0.0, "type": "share"}}, fx_now=lambda c, cs: {"rub": 1.0},
                     fifo=lambda o: {"imp:RU0009029540": {"qty": 10.0, "cost": 2500.0, "last_unit": 250.0}}):
            rows = M.imported_positions(C(), ops, {})
        r = [x for x in rows if x["uid"] == "imp:RU0009029540"][0]
        self.assertEqual(r["price"], 300.0)
        with patched(moex_quotes=lambda ids: {}, fx_now=lambda c, cs: {"rub": 1.0},
                     fifo=lambda o: {"imp:RU0009029540": {"qty": 10.0, "cost": 2500.0, "last_unit": 250.0}}):
            rows = M.imported_positions(C(), ops, {})
        self.assertEqual([x for x in rows if x["uid"] == "imp:RU0009029540"][0]["price"], 250.0)


class ImpDividendsCalendar(unittest.TestCase):
    def test_imp_share_in_calendar(self):
        d1 = (date.today() + timedelta(days=30)).isoformat()
        d2 = (date.today() + timedelta(days=800)).isoformat()
        srv = {"items": [{"record": d1, "payment": None, "value": 10.0, "currency": "RUB"},
                         {"record": d2, "payment": None, "value": 99.0, "currency": "RUB"}]}
        seen = []

        def ds(name, params=None, **k):
            seen.append((name, params))
            return srv

        class C:
            ready = False
        row = {"uid": "imp:RU0009029540", "ticker": "RU0009029540"[:14], "name": "Сбер", "logo": "", "color": "", "type": "share", "qty": 5.0,
               "avg": 1.0, "price": 1.0, "cur": "rub", "value": 5.0, "value_rub": 5.0, "pnl_rub": 0.0, "pnl_pct": 0.0}
        M.store().delete_prefix("div2:imp:RU0009029540")
        with patched(ds_parsed=ds, moex_secid=lambda i: "SBER", fx_now=lambda c, cs: {"rub": 1.0}, keyrate_brief=lambda: None,
                     apply_ratings=lambda rows: [], ratings_status=lambda: {}):
            rep = M.bonds_report(C(), [row])
        dv = [p for p in rep["payments"] if p["kind"] == "dividend"]
        self.assertEqual([(p["date"], p["amount"]) for p in dv], [(d1, 50.0)])
        self.assertEqual(seen[0], ("md/dividends", {"secid": "SBER"}))


class TransferIds(unittest.TestCase):
    def test_uniq(self):
        seen = set()
        ids = [M.uniq_op_id("tb-xfer-in-X-2026-01-01T00:00:01Z", seen) for _ in range(3)]
        self.assertEqual(ids, ["tb-xfer-in-X-2026-01-01T00:00:01Z", "tb-xfer-in-X-2026-01-01T00:00:01Z-2", "tb-xfer-in-X-2026-01-01T00:00:01Z-3"])
        self.assertEqual(M.uniq_op_id("other", seen), "other")                 # без коллизии id не меняется


class Ghost(unittest.TestCase):
    def test_withdrawal_does_not_short(self):
        hist = {"days": ["2026-01-01", "2026-01-02", "2026-01-03"], "value": [100.0, 100.0, 10.0], "invested": [100.0, 100.0, -900.0],
                "bench": {"LQDT": [1.0, 1.0, 1.0], "TMOS": [None, None, 2.0]}}
        g = M.pm_ghost_portfolio(hist)
        for it in g["items"]:
            self.assertGreaterEqual(it["ghost_val"], 0.0)
        self.assertTrue(all(v >= 0 for s in g["series"].values() for v in s))
        hist["invested"] = [100.0, 100.0, 50.0]
        hist["bench"]["LQDT"] = [1.0, 1.0, 1.0]
        by = {x["code"]: x for x in M.pm_ghost_portfolio(hist)["items"]}
        self.assertAlmostEqual(by["LQDT"]["ghost_val"], 50.0)


class GhostPreBenchWithdrawal(unittest.TestCase):
    def test_withdrawal_before_first_price_is_kept(self):
        hist = {"days": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"], "value": [100.0, 0.0, 50.0, 50.0], "invested": [100.0, -50.0, 50.0, 50.0],
                "bench": {"LQDT": [None, None, None, 1.0], "TMOS": [None] * 4}}
        by = {x["code"]: x for x in M.pm_ghost_portfolio(hist)["items"]}
        self.assertAlmostEqual(by["LQDT"]["ghost_val"], 50.0)       # 100 - 150 + 100, а не 100

    def test_net_negative_at_first_price_clamps_to_zero(self):
        hist = {"days": ["a", "b", "c"], "value": [100.0, 0.0, 0.0], "invested": [100.0, -50.0, -50.0],
                "bench": {"LQDT": [None, None, 1.0], "TMOS": [None] * 3}}
        by = {x["code"]: x for x in M.pm_ghost_portfolio(hist)["items"]}
        self.assertAlmostEqual(by["LQDT"]["ghost_val"], 0.0)


class FxNowCbrFallback(unittest.TestCase):
    def test_no_token(self):
        class NoClient:
            ready = False
        with patched(tax_cbr_rate=lambda c, iso: {"USD": 90.5}.get(c.upper())):
            r = M.fx_now(NoClient(), ["rub", "usd", "eur"])
        self.assertEqual(r, {"rub": 1.0, "usd": 90.5})


class CalcPortfolioGuard(unittest.TestCase):
    def test_imports_only_not_none(self):
        class S:
            pass
        with patched(imports_list=lambda: [{"id": "imp:1"}], build_summary=lambda cfg, acc, f: {"portfolio": {"total": 1000.0, "bonds": 400.0}}):
            try:
                pf = M._calc_portfolio({"token": "", "sandbox": False}, "all")
            except Exception:  # noqa: BLE001
                pf = "boom"
        self.assertIsInstance(pf, dict)
        with patched(imports_list=lambda: []):
            self.assertIsNone(M._calc_portfolio({"token": ""}, "all"))
            self.assertFalse(M.goal_defaults({"token": ""}, "all")["portfolio"])


class CrowdBad(unittest.TestCase):
    def test_markers(self):
        for s in ("доступ ограничен", "подтвердите, что вы не робот", "проверка безопасности", "are you a robot", "cf-browser-verification"):
            self.assertIn(s, M._CROWD_BAD)


class CrowdTie(unittest.TestCase):
    def test_tie_not_verified_majority_verified(self):
        import tempfile
        import shutil
        import crowd
        from test_crowd import StoreCase, MSG_URL, msg_html

        class Case(StoreCase):
            def runTest(self):
                pass
        c = Case()
        c.setUp()
        try:
            url = MSG_URL % 4608488
            tid = c.one("a", url)
            c.sub("a", tid, url, msg_html(extra="A"))
            r = c.sub("b", tid, url, msg_html(extra="B"))
            self.assertTrue(r["conflict"])
            with c.st._tx() as cn:
                self.assertEqual(cn.execute("SELECT verified, conflict FROM tasks WHERE id=?", (tid,)).fetchone(), (0, 1))
            c.sub("c", tid, url, msg_html(extra="B"))
            with c.st._tx() as cn:
                self.assertEqual(cn.execute("SELECT verified, conflict FROM tasks WHERE id=?", (tid,)).fetchone(), (1, 0))
        finally:
            c.tearDown()


if __name__ == "__main__":
    unittest.main()
