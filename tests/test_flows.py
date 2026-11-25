"""Потоки денег: клиент T-Invest сервера (белый список, маска токена), сборщик с поддельными источниками, эндпоинты, математика стакана,
сканер секретов в репозитории. Офлайн."""
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
import urllib.parse
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402
import flows_worker as fw  # noqa: E402
import tinvest_md as md  # noqa: E402
import tinvest_server as ts  # noqa: E402
from test_server import Fx  # noqa: E402

T = _load.load()
TOKEN = "t." + "Ab1_-" * 20            # синтетический токен, собирается на лету (в исходнике нет похожей строки)
NOW = datetime(2026, 11, 17, 11, 5, tzinfo=fw.MSK).timestamp()


class FakePost:
    def __init__(self, code=200, body=None, exc=None):
        self.code, self.body, self.exc, self.calls = code, body if body is not None else {}, exc, []

    def __call__(self, url, body, headers, timeout):
        self.calls.append((url, json.loads(body.decode()), headers))
        if self.exc:
            raise self.exc
        return self.code, json.dumps(self.body).encode()


class TestMD(unittest.TestCase):
    def test_whitelist_rejects_account_methods(self):
        post = FakePost()
        c = md.MDClient(TOKEN, post=post)
        for svc, m in (("OperationsService", "GetPortfolio"), ("UsersService", "GetAccounts"), ("OrdersService", "PostOrder"),
                       ("MarketDataService", "GetPortfolio"), ("InstrumentsService", "PostOrder"), ("StopOrdersService", "PostStopOrder")):
            with self.assertRaises(md.NotAllowed):
                c.call(svc, m, {})
        self.assertEqual(post.calls, [])
        for svc, ms in md.ALLOWED.items():
            self.assertFalse(any(re.search(r"Portfolio|Operation|Order\b|Account|Post|Cancel|Sandbox", m) and m != "GetOrderBook" for m in ms))
        c.call("MarketDataService", "GetOrderBook", {"instrumentId": "u", "depth": 10})
        self.assertTrue(post.calls[0][0].endswith("MarketDataService/GetOrderBook"))
        self.assertEqual(post.calls[0][2]["Authorization"], "Bearer " + TOKEN)

    def test_mask_and_no_leak_in_errors(self):
        self.assertEqual(md.mask(TOKEN), "t.***" + TOKEN[-4:])
        self.assertNotIn(TOKEN, repr(md.MDClient(TOKEN)))
        for post in (FakePost(exc=OSError("fail with " + TOKEN)), FakePost(code=401, body={"message": "bad token " + TOKEN})):
            c = md.MDClient(TOKEN, post=post)
            with self.assertRaises(md.MDError) as cm:
                c.call("MarketDataService", "GetCandles", {})
            self.assertNotIn(TOKEN, str(cm.exception))
            self.assertNotIn(TOKEN[2:30], str(cm.exception))
        self.assertNotIn(TOKEN, md.scrub("x " + TOKEN + " y"))

    def test_token_read_order(self):
        d = tempfile.mkdtemp()
        try:
            f = os.path.join(d, "file_tok")
            open(f, "w").write("  FILE_TOKEN \n")
            cd = os.path.join(d, "cred")
            os.mkdir(cd)
            open(os.path.join(cd, "tinvest_token"), "w").write("CRED_TOKEN\n")
            self.assertEqual(md.load_token(f, {"CREDENTIALS_DIRECTORY": cd, "TINVEST_SERVER_TOKEN": "ENV_TOKEN"}), ("CRED_TOKEN", "credentials"))
            self.assertEqual(md.load_token(f, {"TINVEST_SERVER_TOKEN": " ENV_TOKEN "}), ("ENV_TOKEN", "env"))
            self.assertEqual(md.load_token(f, {}), ("FILE_TOKEN", "file"))
            self.assertEqual(md.load_token(os.path.join(d, "nope"), {"CREDENTIALS_DIRECTORY": d}), ("", ""))
            self.assertEqual(md.load_token(None, {}), ("", ""))
        finally:
            shutil.rmtree(d)

    def test_bucket_priority(self):
        t = [0.0]
        slept = []
        b = md.Bucket(60, clock=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
        for _ in range(42):                      # фоновые не трогают резерв (30% от 60 = 18)
            b.acquire(md.BACKGROUND, 1)
        with self.assertRaises(md.RateLimited):
            b.acquire(md.BACKGROUND, 0.1)
        b.acquire(md.INTERACTIVE, 0.1)           # интерактивный берёт из резерва

    def test_parse(self):
        j = {"trades": [{"direction": "TRADE_DIRECTION_BUY", "price": {"units": "100", "nano": 500000000}, "quantity": "7",
                         "time": "2026-11-17T08:00:01.250Z"}, {"direction": "TRADE_DIRECTION_UNSPECIFIED", "price": {"units": "1"}, "quantity": "1", "time": "2026-11-17T08:00:02Z"}]}
        r = md.parse_trades(j)
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["side"], r[0]["price"], r[0]["qty"]), ("buy", 100.5, 7))
        b = md.parse_book({"bids": [{"price": {"units": "99"}, "quantity": "5"}], "asks": [{"price": {"units": "101"}, "quantity": "3"}]})
        self.assertEqual((b["bids"], b["asks"]), ([[99.0, 5]], [[101.0, 3]]))


# ───────────── сборщик ─────────────
def jtable(block, cols, rows):
    return json.dumps({block: {"columns": cols, "data": rows}})


class FakeIss:
    def __init__(self):
        self.trades = {"shares": [], "bonds": []}
        self.log = []
        self.candles = {}

    def __call__(self, url):
        self.log.append(url)
        if "/securities.json" in url:
            if "boards/TQBR" in url:
                sec = [["SBER", "RU0009029540", "Сбербанк", 10, 3], ["GAZP", "RU0007661625", "Газпром", 10, 5], ["XETF", "RU000A0FFFF0", "X ETF", 1, 0]]
                mdv = [["SBER", 9e9], ["GAZP", 5e9], ["XETF", 1e8]]
            elif "boards/TQTF" in url:
                sec, mdv = [["TMOS", "RU000A101X76", "Тинькофф iMOEX", 1, 0]], [["TMOS", 3e8]]
            elif "boards/TQOB" in url:
                sec, mdv = [["SU26238RMFS4", "RU000A1038V6", "ОФЗ 26238", 1, 1000]], [["SU26238RMFS4", 2e9]]
            else:
                sec, mdv = [["RU000A0CORP1", "RU000A0CORP1", "Корп 1", 1, 1000]], [["RU000A0CORP1", 1e8]]
            return json.dumps({"securities": {"columns": ["SECID", "ISIN", "SHORTNAME", "LOTSIZE", "FACEVALUE"], "data": sec},
                               "marketdata": {"columns": ["SECID", "VALTODAY"], "data": mdv}})
        if "/trades.json" in url:
            m = "bonds" if "/markets/bonds/" in url else "shares"
            cols = ["TRADENO", "BOARDID", "SECID", "TRADETIME", "PRICE", "QUANTITY", "VALUE", "BUYSELL", "SYSTIME"]
            rows = self.trades[m]
            if "reversed=1" in url:
                return jtable("trades", cols, rows[-1:])
            no = int(re.search(r"tradeno=(\d+)", url).group(1))
            return jtable("trades", cols, [r for r in rows if r[0] > no][:5000])
        if "/candles.json" in url:
            sid = re.search(r"securities/([^/]+)/candles", url).group(1)
            return jtable("candles", ["open", "close", "high", "low", "value", "volume", "begin", "end"], self.candles.get(sid, []))
        raise AssertionError(url)


def tr(no, board, secid, hhmmss, price, qty, value, bs):
    return [no, board, secid, hhmmss, price, qty, value, bs, "2026-11-17 " + hhmmss]


class FakeMD:
    enabled = True

    def __init__(self):
        self.trades = {}
        self.calls = []

    def last_trades(self, uid, frm, to, priority=1):
        self.calls.append((uid, frm, to))
        return list(self.trades.get(uid, []))


class TestWorker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = fw.open_db(os.path.join(self.tmp, "flows.sqlite"))
        self.iss = FakeIss()
        self.now = [NOW]
        self.eng = fw.Engine(self.db, self.iss, None, now=lambda: self.now[0], iss_backfill=10 ** 6)
        self.eng.universe_refresh()

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp)

    def test_universe(self):
        i = self.eng.inst
        self.assertEqual(i["SBER"]["cls"], "share")
        self.assertEqual(i["XETF"]["cls"], "fund")
        self.assertEqual(i["TMOS"]["cls"], "fund")
        self.assertEqual(i["SU26238RMFS4"]["cls"], "bond")
        self.assertEqual(i["SBER"]["sector"], "Банки и финансы")

    def test_iss_aggregates_and_large(self):
        t0 = "11:00:00"
        self.iss.trades["shares"] = [tr(1, "TQBR", "SBER", t0, 300, 100, 3e6, "B"), tr(2, "TQBR", "SBER", "11:01:00", 300, 100, 2e6, "S"),
                                     tr(3, "TQBR", "SBER", "11:02:00", 300, 40000, 12e6, "B"), tr(4, "SMAL", "SBER", "11:02:00", 300, 1, 5e8, "B"),
                                     tr(5, "TQBR", "NOPE", "11:02:00", 300, 1, 5e8, "B")]
        self.eng.iss_trades("shares")
        a = self.db.execute("SELECT buy,sell,n,nl FROM agg WHERE secid='SBER'").fetchall()
        self.assertEqual(len(a), 1)
        self.assertEqual((a[0][0], a[0][1], a[0][2], a[0][3]), (15e6, 2e6, 3, 1))
        big = self.db.execute("SELECT side,value,src FROM large").fetchall()
        self.assertEqual(big, [("buy", 12e6, "iss")])
        # повторный запрос курсора ничего не удваивает
        self.eng.iss_trades("shares")
        self.assertEqual(self.db.execute("SELECT SUM(buy+sell) FROM agg").fetchone()[0], 17e6)

    def test_percentile_threshold(self):
        eng = self.eng
        base = NOW - 3600
        eng.ingest([("SBER", base + i, "buy", 1, 1, 20e6, "iss", "h%d" % i) for i in range(300)])
        eng.adds["SBER"] = 300
        thr = eng.threshold("SBER", "share")
        self.assertGreater(thr, 20e6)
        n0 = self.db.execute("SELECT COUNT(*) FROM large").fetchone()[0]
        eng.ingest([("SBER", NOW, "buy", 1, 1, 10e6, "iss", "mid"), ("SBER", NOW + 1, "sell", 1, 1, 100e6, "iss", "huge")])
        ids = [r[0] for r in self.db.execute("SELECT tid FROM large")]
        self.assertIn("huge", ids)
        self.assertNotIn("mid", ids)
        self.assertEqual(len(ids), n0 + 1)
        # без истории действует только N_min
        self.assertEqual(eng.threshold("GAZP", "share"), 5e6)
        self.assertEqual(eng.threshold("SU26238RMFS4", "bond"), 10e6)

    def test_tinvest_polling_value_and_dedup(self):
        fmd = FakeMD()
        self.eng.md = fmd
        self.db.execute("UPDATE instruments SET uid='u-sber', lot=10 WHERE secid='SBER'")
        self.db.execute("UPDATE instruments SET uid='u-ofz', lot=1, face=1000 WHERE secid='SU26238RMFS4'")
        self.eng.load_inst()
        t = NOW - 60
        fmd.trades["u-sber"] = [{"ts": t, "side": "buy", "price": 300.0, "qty": 2000}, {"ts": t + 1, "side": "sell", "price": 300.0, "qty": 10}]
        fmd.trades["u-ofz"] = [{"ts": t, "side": "buy", "price": 98.5, "qty": 100}]
        self.eng.poll_tinvest(5)
        sber = self.db.execute("SELECT buy,sell,ti FROM agg WHERE secid='SBER'").fetchall()
        self.assertEqual(sum(r[0] for r in sber), 300.0 * 2000 * 10)         # цена × лоты × размер лота
        self.assertEqual(sum(r[1] for r in sber), 300.0 * 10 * 10)
        self.assertEqual(sum(r[2] for r in sber), sum(r[0] + r[1] for r in sber))
        ofz = self.db.execute("SELECT buy FROM agg WHERE secid='SU26238RMFS4'").fetchone()[0]
        self.assertAlmostEqual(ofz, 98.5 / 100 * 1000 * 100)                  # цена в % номинала
        self.assertEqual(self.db.execute("SELECT value,src FROM large WHERE secid='SBER'").fetchall(), [(6e6, "tinvest")])
        self.eng.poll_tinvest(5)                                              # те же сделки снова: дубликатов нет
        self.assertEqual(self.db.execute("SELECT SUM(buy) FROM agg WHERE secid='SBER'").fetchone()[0], 6e6)
        # ISS не считает дважды то, что видел T-Invest
        self.iss.trades["shares"] = [tr(1, "TQBR", "SBER", datetime.fromtimestamp(t, fw.MSK).strftime("%H:%M:%S"), 300, 20000, 6e6, "B")]
        self.eng.iss_trades("shares")
        self.assertEqual(self.db.execute("SELECT SUM(buy) FROM agg WHERE secid='SBER'").fetchone()[0], 6e6)

    def test_tinvest_polling_fx_bond(self):
        fmd = FakeMD()
        self.eng.md = fmd
        self.eng.fx_get = lambda: {"USD": 90.0}
        self.db.execute("UPDATE instruments SET uid='u-usd', lot=1, face=1000 WHERE secid='RU000A0CORP1'")
        self.eng.load_inst()
        self.eng.inst["RU000A0CORP1"]["face_cur"] = "usd"
        fmd.trades["u-usd"] = [{"ts": NOW - 60, "side": "buy", "price": 98.5, "qty": 10}]
        self.eng.poll_tinvest(5)
        val = self.db.execute("SELECT buy FROM agg WHERE secid='RU000A0CORP1'").fetchone()[0]
        self.assertAlmostEqual(val, 98.5 / 100 * 1000 * 10 * 90.0)

    def test_spikes(self):
        for d in range(1, 8):
            self.db.execute("INSERT INTO slot VALUES('SBER',?,66,1000000)", ("2026-11-%02d" % (d + 5 if d + 5 < 17 else 5),))
        self.db.commit()
        base = datetime(2026, 11, 17, 11, 0, tzinfo=fw.MSK).timestamp()
        self.assertEqual(fw.slot_of(base), 66)
        self.eng.ingest([("SBER", base + 10, "buy", 1, 1, 2e6, "iss", "a"), ("SBER", base + 400, "sell", 1, 1, 1e6, "iss", "b")])
        self.assertEqual(self.eng.spikes_check(), 1)                          # 3 млн против медианы 1 млн = ×3
        r = self.db.execute("SELECT ratio,value FROM spikes").fetchall()
        self.assertEqual(self.eng.spikes_check(), 0)                          # второй вызов: затронутых слотов нет
        self.assertTrue(r and r[0][0] >= 3 and r[0][1] == 3e6)
        # малый оборот (< 1 млн ₽) всплеском не считается, даже при большом отношении
        self.eng.ingest([("GAZP", base + 10, "buy", 1, 1, 9e5, "iss", "c")])
        for d in range(1, 8):
            self.db.execute("INSERT INTO slot VALUES('GAZP',?,66,1000)", ("2026-11-%02d" % (d + 5 if d + 5 < 17 else 5),))
        self.eng.spikes_check()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM spikes WHERE secid='GAZP'").fetchone()[0], 0)

    def test_candles_sync(self):
        self.iss.candles["SBER"] = [[1, 1, 1, 1, 5e6, 10, "2026-11-16 11:00:00", "2026-11-16 11:09:59"]]
        self.eng.candles_sync(10)
        self.assertEqual(self.db.execute("SELECT day,slot,value FROM slot WHERE secid='SBER'").fetchall(), [("2026-11-16", 66, 5e6)])
        n = len(self.iss.log)
        self.eng.candles_sync(10)                                             # раз в сутки на бумагу
        self.assertEqual(len(self.iss.log), n)

    def test_queries(self):
        base = datetime(2026, 11, 17, 11, 0, tzinfo=fw.MSK).timestamp()
        self.eng.ingest([("SBER", base + 5, "buy", 300, 1, 8e6, "iss", "a"), ("GAZP", base + 5, "sell", 100, 1, 6e6, "iss", "b"),
                         ("SU26238RMFS4", base + 5, "buy", 99, 1, 12e6, "iss", "c")])
        self.db.commit()
        s = fw.q_summary(self.db, "1h")
        self.assertEqual({c["cls"]: c["net"] for c in s["by_class"]}, {"share": 2e6, "bond": 12e6})
        self.assertEqual(s["top_buy"][0]["secid"], "SU26238RMFS4")
        self.assertEqual(s["top_sell"][0]["secid"], "GAZP")
        self.assertEqual((s["source"], s["delay_min"]), ("iss", 15))
        self.assertEqual(fw.q_summary(fw.open_db(os.path.join(self.tmp, "x.sqlite")), "day")["empty"], True)
        L = fw.q_large(self.db, since=str(int(base) - 10), cls="bond", now=NOW)
        self.assertEqual([r["secid"] for r in L], ["SU26238RMFS4"])
        self.assertEqual(len(fw.q_large(self.db, since=str(int(base) - 10), isins=["RU0009029540"], now=NOW)), 1)
        self.assertEqual(len(fw.q_instrument(self.db, "SBER", "5m")["series"]), 1)


class TestServerEndpoints(unittest.TestCase):
    def setUp(self):
        self.fx = Fx()
        self.db = fw.open_db(os.path.join(self.fx.tmp, "flows.sqlite"))
        self.eng = fw.Engine(self.db, FakeIss(), None, now=lambda: time.time())
        self.eng.universe_refresh()
        self.eng.ingest([("SBER", time.time() - 100, "buy", 300, 1, 9e6, "iss", "z")])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.fx.close()
        shutil.rmtree(self.fx.tmp, ignore_errors=True)

    def get(self, name, **kw):
        return self.fx.app.parsed(name, {k: [str(v)] for k, v in kw.items()})

    def test_flows(self):
        code, j = self.get("flows/summary", period="day")
        self.assertEqual(code, 200)
        self.assertTrue(j["ok"])
        self.assertEqual(j["data"]["by_class"][0]["cls"], "share")
        self.assertEqual(self.get("flows/summary", period="week")[0], 400)
        self.assertEqual(self.get("flows/large", since="2020-01-01")[1]["data"][0]["secid"], "SBER")
        self.assertEqual(self.get("flows/spikes")[1]["data"], [])
        self.assertEqual(self.get("flows/instrument", secid="SBER", period="5m")[1]["data"]["secid"], "SBER")
        self.assertEqual(self.get("flows/instrument")[0], 400)
        self.assertEqual(self.get("flows/large", class_="x")[0], 200)
        self.assertEqual(self.get("flows/nope")[0], 404)

    def test_no_db_is_empty(self):
        d = tempfile.mkdtemp()
        try:
            self.assertEqual(ts.flows_query(d, "flows/large", {})[1]["data"], [])
            self.assertTrue(ts.flows_query(d, "flows/summary", {})[1]["data"]["empty"])
        finally:
            shutil.rmtree(d)

    def test_orderbook_and_trades(self):
        post_calls = []

        def post(url, body, headers, timeout):
            post_calls.append(url)
            if url.endswith("GetOrderBook"):
                return 200, json.dumps({"bids": [{"price": {"units": "99"}, "quantity": "5"}], "asks": [{"price": {"units": "101"}, "quantity": "7"}],
                                        "orderbookTs": "2026-11-17T08:00:00Z"}).encode()
            if url.endswith("GetInstrumentBy"):
                return 200, json.dumps({"instrument": {"uid": "u-1", "lot": 10}}).encode()
            return 200, json.dumps({"trades": [{"direction": "TRADE_DIRECTION_SELL", "price": {"units": "100"}, "quantity": "3",
                                                "time": "2026-11-17T08:00:00Z"}]}).encode()
        app = self.fx.app
        app.md = md.MDClient(TOKEN, post=post)
        code, j = app.parsed("md/orderbook", {"secid": ["ZZZZ"], "depth": ["20"]})
        self.assertEqual(code, 200)
        self.assertEqual(j["data"]["bids"], [[99.0, 5]])
        self.assertEqual(j["data"]["source"], "T-Invest")
        n = len(post_calls)
        app.parsed("md/orderbook", {"secid": ["ZZZZ"], "depth": ["20"]})
        self.assertEqual(len(post_calls), n)                                  # кэш 1,5 с
        code, j = app.parsed("md/trades", {"secid": ["ZZZZ"], "minutes": ["60"]})
        self.assertEqual(j["data"]["trades"][0]["side"], "sell")
        self.assertEqual(j["data"]["trades"][0]["value"], 100 * 3 * 10)
        self.assertNotIn(TOKEN, json.dumps(j))
        self.assertNotIn(TOKEN[2:], json.dumps(app.parsed("md/orderbook", {"secid": ["ZZZZ"]})))
        self.assertEqual(app.parsed("md/orderbook", {})[0], 400)

    def test_no_token_404_and_errors_masked(self):
        app = self.fx.app
        app.md = None
        code, j = app.parsed("md/orderbook", {"secid": ["SBER"]})
        self.assertEqual((code, j["ok"]), (404, False))
        app.md = md.MDClient(TOKEN, post=FakePost(exc=OSError("boom " + TOKEN)))
        code, j = app.parsed("md/orderbook", {"secid": ["SBER"]})
        self.assertNotIn(TOKEN, json.dumps(j))
        self.assertIn(code, (404, 502))

    def test_server_reads_token_from_file(self):
        f = os.path.join(self.fx.tmp, "tok")
        open(f, "w").write(TOKEN + "\n")
        d = tempfile.mkdtemp()
        try:
            app = ts.DataServer(d, token_file=f)
            self.assertTrue(app.md and app.md.enabled)
            self.assertFalse(ts.DataServer(tempfile.mkdtemp(), token_file=os.path.join(d, "none")).md)
        finally:
            shutil.rmtree(d)


class TestClient(unittest.TestCase):
    def test_book_metrics(self):
        bids = [[100 - i, 100] for i in range(10)]
        asks = [[101 + i, 100] for i in range(10)]
        m = T.flows_book_metrics(bids, asks)
        self.assertEqual(m["imbalance"], 0.0)
        self.assertEqual(m["walls"], [])
        asks[3][1] = 600
        bids[1][1] = 50
        m = T.flows_book_metrics(bids, asks)
        self.assertEqual([(w["side"], w["price"]) for w in m["walls"]], [("ask", 104)])
        self.assertEqual(m["walls"][0]["mult"], 6.0)
        self.assertAlmostEqual(m["imbalance"], (950 - 1500) / 2450.0, places=3)
        self.assertEqual(m["spread"], 1)
        self.assertEqual(T.flows_book_metrics([], [])["imbalance"], 0.0)
        # учитываются только первые 10 уровней
        m = T.flows_book_metrics([[1, 10]] * 10 + [[0, 1000]], [[2, 10]] * 10)
        self.assertEqual(m["imbalance"], 0.0)

    def test_tape_net(self):
        r = T.flows_tape_net([{"side": "buy", "value": 100}, {"side": "sell", "price": 2, "qty": 10}, {"side": "buy", "price": 1, "qty": 5}])
        self.assertEqual((r["buy"], r["sell"], r["net"], r["n"]), (105.0, 20.0, 85.0, 3))

    def test_orderbook_route_server_then_own_token(self):
        calls = []
        orig = T.ds_parsed
        orig_ti = T.TInvest

        def fake(name, params=None, timeout=20):
            calls.append(name)
            if name == "md/orderbook":
                return {"bids": [[99, 10]], "asks": [[101, 30]], "ts": 1}
            if name == "md/trades":
                return {"trades": [{"ts": 1, "side": "buy", "price": 100, "qty": 5, "value": 500}]}
        try:
            T.ds_parsed = fake
            T._flw_cache.clear()
            r = T.orderbook_get({}, None, {"secid": "SBER"}, False)
            self.assertTrue(r["ok"])
            self.assertEqual(r["metrics"]["imbalance"], -0.5)
            self.assertEqual(r["tape"]["net"], 500.0)
            # на сервере нет токена -> свой токен пользователя (методы TInvest берутся через getattr)

            class Own:
                def __init__(self, cfg):
                    pass

                def find(self, q):
                    return [{"ticker": "SBER", "classCode": "TQBR", "uid": "u1"}]

                def order_book(self, uid, depth):
                    return {"bids": [{"price": {"units": "50"}, "quantity": "4"}], "asks": [{"price": {"units": "51"}, "quantity": "1"}]}

                def last_trades(self, uid, frm, to):
                    return {"trades": [{"direction": "TRADE_DIRECTION_SELL", "price": {"units": "50"}, "quantity": "2", "time": "2026-11-17T08:00:00Z"}]}
            T.ds_parsed = lambda *a, **k: None
            T.TInvest = Own
            T._flw_cache.clear()
            T._flw_uid.clear()
            r = T.orderbook_get({"token": "x"}, None, {"secid": "SBER"}, False)
            self.assertTrue(r["ok"])
            self.assertEqual(r["bids"], [[50.0, 4.0]])
            self.assertEqual(r["tape"]["sell"], 100.0)
            T._flw_cache.clear()
            r = T.orderbook_get({}, None, {"secid": "SBER"}, False)
            self.assertFalse(r["ok"])
            T.TInvest = type("NoBook", (), {"__init__": lambda s, c: None})
            T._flw_cache.clear()
            self.assertFalse(T.orderbook_get({"token": "x"}, None, {"secid": "SBER"}, False)["ok"])
        finally:
            T.ds_parsed, T.TInvest = orig, orig_ti
            T._flw_cache.clear()

    def test_routes_disabled_server(self):
        T._flw_cache.clear()
        self.assertEqual(T.flows_get({}, None, {"period": "1h"}, False)["configured"], False)
        self.assertEqual(T.large_trades_get({}, None, {}, False), {"configured": False, "rows": []})
        with self.assertRaises(T.ApiError):
            T.orderbook_get({}, None, {"secid": "bad secid!"}, False)
        for p in ("/api/flows", "/api/flows_instrument", "/api/large_trades", "/api/spikes", "/api/orderbook"):
            self.assertIn(p, T.API_GET)

    def test_watch_alerts(self):
        al = T.flows_alerts_from([{"secid": "SBER", "ts": 1700000000, "side": "buy", "value": 12e6, "price": 300, "isin": "RU0009029540", "name": "Сбер"}],
                                 [{"secid": "SBER", "ts": 1700000600, "ratio": 4.2, "value": 3e6, "isin": "RU0009029540", "name": "Сбер"}])
        self.assertEqual([a["kind"] for a in al], ["flow_large", "flow_spike"])
        self.assertIn("крупная покупка", al[0]["message"])
        self.assertIn("×4.2", al[1]["message"])
        self.assertEqual(len({a["id"] for a in al}), 2)
        self.assertIn("flow_large", T._TG_KIND)


class TestSecretScan(unittest.TestCase):
    def test_no_tokens_in_repo(self):
        rx = re.compile(r"t\.[A-Za-z0-9_-]{80,}")
        skip = {".git", "__pycache__", "node_modules", "build", "dist"}
        bad = []
        for dp, dns, fns in os.walk(ROOT):
            dns[:] = [d for d in dns if d not in skip and os.path.join(dp, d) != os.path.join(ROOT, "tests", "fixtures")]
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    if os.path.getsize(p) > 8 * 1024 * 1024:
                        continue
                    with open(p, "rb") as f:
                        raw = f.read()
                    if b"\0" in raw[:4096]:
                        continue
                    txt = raw.decode("utf-8", "replace")
                except OSError:
                    continue
                if rx.search(txt):
                    bad.append(os.path.relpath(p, ROOT))
        self.assertEqual(bad, [], "в репозитории найден токен T-Invest")

    def test_gitignore_has_secret_patterns(self):
        g = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read().split("\n")
        for pat in ("*.env", "secrets/", "tinvest_token"):
            self.assertIn(pat, g)


if __name__ == "__main__":
    unittest.main()


class RussianRootCA(unittest.TestCase):
    def test_same_as_client(self):
        import re as _re
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cli = open(os.path.join(here, "src", "py", "02_certs.py"), encoding="utf-8").read()
        pem = _re.search(r'RUSSIAN_TRUSTED_ROOT_CA = """(.*?)"""', cli, _re.S).group(1)
        self.assertEqual(pem, md.RUSSIAN_TRUSTED_ROOT_CA)
        self.assertTrue(md.ssl_context().cert_store_stats().get("x509_ca"))
