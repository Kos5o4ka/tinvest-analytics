"""Стакан: ликвидность — проход по книге (проскальзывание, единицы акций и облигаций), недостаток глубины, эвристика скрытой ликвидности. Офлайн."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

M = _load.load()

SHARE = {"lot": 10, "face": None, "is_bond": False}
BOND = {"lot": 1, "face": 1000.0, "is_bond": True}


class TestImpact(unittest.TestCase):
    def test_share_buy_vwap_and_units(self):
        # лот = 10 акций; уровень 100 ₽ -> 1000 ₽ за лот
        book = {"bids": [[99.0, 100], [98.0, 100]], "asks": [[101.0, 5], [102.0, 100]]}
        r = M.mic_impact(book, SHARE, "buy", 10000)
        # 5 лотов по 1010 = 5050, затем 4 лота по 1020 = 4080 (остаток 4950 -> 4 лота)
        self.assertEqual(r["filled_lots"], 9)
        self.assertAlmostEqual(r["filled_rub"], 9130.0)
        self.assertAlmostEqual(r["vwap"], (5 * 101 + 4 * 102) / 9)
        self.assertAlmostEqual(r["mid"], 100.0)
        self.assertAlmostEqual(r["slip_mid_bp"], ((5 * 101 + 4 * 102) / 9 - 100) / 100 * 1e4)
        self.assertAlmostEqual(r["slip_mid_rub"], ((5 * 101 + 4 * 102) / 9 - 100) * 9 * 10)
        self.assertTrue(r["complete"])
        self.assertEqual(r["levels_used"], 2)
        self.assertAlmostEqual(r["spread_bp"], 2 / 100 * 1e4)
        self.assertNotIn("yield_bp", r)

    def test_share_sell_uses_bids(self):
        book = {"bids": [[99.0, 3], [98.0, 100]], "asks": [[101.0, 100]]}
        r = M.mic_impact(book, SHARE, "sell", 5000)
        # 3 лота по 990 = 2970; 2 лота по 980 = 1960
        self.assertEqual(r["filled_lots"], 5)
        self.assertAlmostEqual(r["filled_rub"], 4930.0)
        self.assertGreater(r["slip_mid_bp"], 0)
        self.assertAlmostEqual(r["vwap"], (3 * 99 + 2 * 98) / 5)

    def test_bond_units_percent_of_face(self):
        # цена 98 % от номинала 1000 -> 980 ₽ за облигацию
        book = {"bids": [[97.9, 1000]], "asks": [[98.1, 3], [98.5, 1000]]}
        r = M.mic_impact(book, BOND, "buy", 5000)
        # 3 по 981 = 2943; остаток 2057 -> 2 по 985 = 1970
        self.assertEqual(r["filled_lots"], 5)
        self.assertAlmostEqual(r["filled_rub"], 2943 + 1970)
        self.assertAlmostEqual(r["vwap"], (3 * 98.1 + 2 * 98.5) / 5)
        self.assertAlmostEqual(r["mid"], 98.0)
        self.assertAlmostEqual(r["slip_mid_rub"], ((3 * 98.1 + 2 * 98.5) / 5 - 98.0) * 5 * 10)
        r2 = M.mic_impact(book, BOND, "buy", 5000, mdur=2.0)
        self.assertAlmostEqual(r2["yield_bp"], r2["slip_mid_bp"] / 2.0)

    def test_bond_nonunit_face(self):
        meta = {"lot": 1, "face": 100.0, "is_bond": True}
        self.assertAlmostEqual(M.mic_rub_per_lot(meta), 1.0)
        self.assertAlmostEqual(M.mic_rub_per_lot(SHARE), 10.0)

    def test_insufficient_depth(self):
        book = {"bids": [[99.0, 10]], "asks": [[101.0, 2], [102.0, 3]]}
        r = M.mic_impact(book, SHARE, "buy", 1e6)
        self.assertFalse(r["complete"])
        self.assertEqual(r["filled_lots"], 5)
        self.assertIn("не хватает", r["warning"])
        self.assertIn("5", r["warning"])
        self.assertAlmostEqual(r["depth_share"], 1.0)

    def test_order_smaller_than_lot(self):
        r = M.mic_impact({"bids": [[99.0, 10]], "asks": [[101.0, 10]]}, SHARE, "buy", 500)
        self.assertEqual(r["filled_lots"], 0)
        self.assertFalse(r["complete"])

    def test_empty_side(self):
        self.assertFalse(M.mic_impact({"bids": [], "asks": [[1.0, 1]]}, SHARE, "buy", 1000)["ok"])

    def test_depth_band(self):
        book = {"bids": [[100.0, 10], [99.4, 20], [98.0, 50]], "asks": [[100.2, 10], [100.9, 20], [102.0, 50]]}
        r = M.mic_impact(book, {"lot": 1, "face": None, "is_bond": False}, "buy", 100)
        mid = 100.1
        b05, b1 = r["depth_band"]["0.005"], r["depth_band"]["0.01"]
        self.assertEqual(b05["ask_lots"], 10)          # 100,2 внутри +0,5 % (100,6), 100,9 — нет
        self.assertEqual(b1["ask_lots"], 30)
        self.assertEqual(b05["bid_lots"], 10)          # 99,4 < mid*0,995 = 99,6
        self.assertEqual(b1["bid_lots"], 30)
        self.assertAlmostEqual(r["mid"], mid)

    def test_endpoint_with_fake_fetch(self):
        orig_f, orig_s = M._mic_fetch, M._mic_mdur
        M._mic_fetch = lambda cfg, secid, depth=50: {"ok": True, "bids": [[97.9, 100]], "asks": [[98.1, 100]], "trades": [], "source": "own",
                                                    "source_label": "x", "ts": 1.0, "meta": dict(BOND)}
        M._mic_mdur = lambda secid: 3.0
        try:
            r = M.API_GET["/api/mic/impact"]({}, None, {"secid": "SU26238RMFS4", "side": "buy", "rub": "50000"}, False)
        finally:
            M._mic_fetch, M._mic_mdur = orig_f, orig_s
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["presets"]), 3)
        self.assertIn("yield_bp", r)
        self.assertTrue(any("купонный" in n for n in r["notes"]))

    def test_endpoint_book_unavailable(self):
        orig = M._mic_fetch
        M._mic_fetch = lambda cfg, secid, depth=50: {"ok": False, "error": "нет"}
        try:
            r = M.API_GET["/api/mic/impact"]({}, None, {"secid": "SBER"}, False)
        finally:
            M._mic_fetch = orig
        self.assertFalse(r["ok"])
        with self.assertRaises(M.ApiError):
            M.API_GET["/api/mic/impact"]({}, None, {}, False)


def _book(ask_q, bid_q=50, ask_p=101.0, bid_p=100.0):
    return {"asks": [[ask_p, ask_q], [ask_p + 1, 40]], "bids": [[bid_p, bid_q], [bid_p - 1, 40]]}


class TestIceberg(unittest.TestCase):
    def setUp(self):
        M._mic_state.clear()

    def _run(self, secid, snaps, trades, t0=1000.0, step=10.0):
        for i, b in enumerate(snaps):
            M.mic_ice_update(secid, b, trades(t0 + i * step) if callable(trades) else trades, now=t0 + i * step)
        return M.mic_ice_report(secid, now=t0 + (len(snaps) - 1) * step)

    def test_positive_hidden_ask(self):
        # видимо 10 лотов по 101 всё время, а покупатели исполнили 40 лотов по 101
        snaps = [_book(10) for _ in range(6)]
        tr = [{"ts": 1000.0 + 8 + i * 9, "side": "buy", "price": 101.0, "lots": 8} for i in range(5)]
        r = self._run("AAA", snaps, tr)
        self.assertEqual(r["status"], "ready")
        c = r["candidates"]
        self.assertEqual(len(c), 1)
        self.assertEqual((c[0]["side"], c[0]["price"]), ("ask", 101.0))
        self.assertAlmostEqual(c[0]["executed_lots"], 40.0)
        self.assertAlmostEqual(c[0]["hidden_est_lots"], 40.0)
        self.assertGreaterEqual(c[0]["factor"], 2.0)
        self.assertTrue(c[0]["evidence"]["trades"] and c[0]["evidence"]["book"])

    def test_positive_hidden_bid(self):
        snaps = [_book(10, bid_q=5) for _ in range(5)]
        tr = [{"ts": 1015.0 + i, "side": "sell", "price": 100.0, "lots": 6} for i in range(3)]
        r = self._run("BBB", snaps, tr)
        self.assertEqual([(x["side"], x["price"]) for x in r["candidates"]], [("bid", 100.0)])

    def test_negative_executed_below_factor(self):
        snaps = [_book(10) for _ in range(6)]
        tr = [{"ts": 1020.0, "side": "buy", "price": 101.0, "lots": 15}]
        self.assertEqual(self._run("CCC", snaps, tr)["candidates"], [])

    def test_negative_level_not_persistent(self):
        snaps = [_book(10), _book(10), {"asks": [[103.0, 10]], "bids": [[100.0, 50]]}, {"asks": [[103.0, 10]], "bids": [[100.0, 50]]}] \
            + [{"asks": [[101.0, 10]], "bids": [[100.0, 50]]}]
        tr = [{"ts": 1045.0, "side": "buy", "price": 101.0, "lots": 100}]
        self.assertEqual(self._run("DDD", snaps, tr)["candidates"], [])

    def test_negative_visible_consumed(self):
        # уровень реально съедался и пополнялся видимо: исполненное объяснено видимым уменьшением
        snaps = [_book(q) for q in (10, 2, 10, 2, 10, 2)]
        tr = [{"ts": 1000.0 + 20 * i + 5, "side": "buy", "price": 101.0, "lots": 8} for i in range(3)]
        self.assertEqual(self._run("EEE", snaps, tr)["candidates"], [])

    def test_collecting_and_unavailable(self):
        M.mic_ice_update("FFF", _book(10), [], now=1000.0)
        self.assertEqual(M.mic_ice_report("FFF", now=1000.0)["status"], "collecting")
        r = self._run("GGG", [_book(10) for _ in range(5)], None)
        self.assertEqual(r["status"], "unavailable")

    def test_window_expiry_and_idle(self):
        for i in range(4):
            M.mic_ice_update("HHH", _book(10), [], now=1000.0 + i * 10)
        M.mic_ice_update("HHH", _book(10), [], now=1000.0 + 700)
        self.assertEqual(len(M._mic_state["HHH"]["snaps"]), 1)           # старше 10 минут вытеснено
        # без опроса дольше MIC_IDLE бумага забывается
        M.mic_ice_update("III", _book(10), [], now=1900.0)
        self.assertNotIn("HHH", M._mic_state)
        self.assertEqual(M.mic_ice_report("III", now=1900.0 + M.MIC_IDLE + 1)["snapshots"], 0)

    def test_trade_dedup_and_old_trades_ignored(self):
        trades = [{"ts": 1015.0, "side": "buy", "price": 101.0, "lots": 5}, {"ts": 500.0, "side": "buy", "price": 101.0, "lots": 99}]
        for i in range(4):
            M.mic_ice_update("JJJ", _book(10), trades, now=1000.0 + i * 10)
        self.assertEqual(sum(M._mic_state["JJJ"]["trades"].values()), 1)

    def test_tracked_cap(self):
        for i in range(M.MIC_MAX_TRACKED + 2):
            M.mic_ice_update("S%d" % i, _book(10), [], now=1000.0 + i)
        self.assertEqual(len(M._mic_state), M.MIC_MAX_TRACKED)
        self.assertIn("S%d" % (M.MIC_MAX_TRACKED + 1), M._mic_state)

    def test_endpoint_polls_and_normalizes(self):
        orig = M._mic_fetch
        M._mic_fetch = lambda cfg, secid, depth=50: {"ok": True, "bids": [[100.0, 5]], "asks": [[101.0, 5]], "trades": [], "source": "server",
                                                    "source_label": "x", "ts": 1.0, "meta": dict(SHARE)}
        try:
            r = M.API_GET["/api/mic/iceberg"]({}, None, {"secid": "SBER"}, False)
        finally:
            M._mic_fetch = orig
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], "collecting")
        self.assertIn("Эвристика", r["note"])

    def test_norm_trades_divides_by_lot(self):
        out = M._mic_norm_trades([{"ts": 1.0, "side": "buy", "price": 5, "qty": 100}, {"ts": None, "side": "buy", "price": 5, "qty": 1}], 10)
        self.assertEqual(out, [{"ts": 1.0, "side": "buy", "price": 5.0, "lots": 10.0}])


if __name__ == "__main__":
    unittest.main()
