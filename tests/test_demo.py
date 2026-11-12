"""Демо-режим: включение/выключение демо-портфеля без токена, автоматическое снятие при реальном токене."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

m = _load.load()


class DemoTest(unittest.TestCase):
    def setUp(self):
        m.demo_remove()

    def tearDown(self):
        m.demo_remove()

    def test_enable_disable(self):
        cfg = m.load_config()
        self.assertFalse(m.API_GET["/api/demo/status"](cfg, "all", {}, False)["active"])
        r = m.API_POST["/api/demo/enable"](cfg, {})
        self.assertTrue(r["ok"] and r["count"] > 50)
        self.assertTrue(m.API_GET["/api/demo/status"](cfg, "all", {}, False)["active"])
        imp = [x for x in m.imports_list() if x["id"] == m.DEMO_ID]
        self.assertEqual(len(imp), 1)
        self.assertTrue(imp[0]["demo"])
        # повторное включение не дублирует
        m.API_POST["/api/demo/enable"](cfg, {})
        self.assertEqual(len([x for x in m.imports_list() if x.get("demo")]), 1)
        ops = m.store().ops(m.DEMO_ID)
        cash = sum(m.qf(o["payment"]) for o in ops)
        self.assertGreater(cash, 0)
        run = 0.0
        for o in ops:
            run += m.qf(o["payment"])
            self.assertGreater(run, -0.01, o["date"])
        client = m.TInvest(cfg)
        rows = m.imported_positions(client, ops, m.instruments(client, []))
        real = [x for x in rows if x["type"] != "currency"]
        self.assertGreaterEqual(len(real), 12)
        self.assertEqual({x["type"] for x in real}, {"bond", "share"})
        r = m.API_POST["/api/demo/disable"](cfg, {})
        self.assertTrue(r["removed"])
        self.assertEqual(m.imports_list(), [])
        self.assertEqual(m.store().ops(m.DEMO_ID), [])

    def test_accounts_and_summary_without_token(self):
        cfg = m.load_config()
        cfg["token"] = ""
        m.demo_enable()
        accs = m.list_accounts(cfg, True)
        self.assertEqual([a["id"] for a in accs], [m.DEMO_ID])
        self.assertGreater(accs[0]["total"], 100000)
        s = m.build_summary(cfg, "all", "all", True)
        self.assertTrue(s["portfolio"]["positions"])
        self.assertTrue(s["ops"])

    def test_real_token_removes_demo(self):
        m.demo_enable()
        self.assertTrue(m.demo_active())
        cfg = m.load_config()
        cfg["token"] = "t.fake"
        try:
            m.save_config(cfg)
        finally:
            cfg["token"] = ""
            m.save_config(cfg)
        self.assertFalse(m.demo_active())

    def test_real_import_removes_demo(self):
        m.demo_enable()
        m.finalize_import(m._NoClient(), [])
        self.assertFalse(m.demo_active())

    def test_csv_parses_with_importer(self):
        raw = m.demo_csv().encode("utf-8")
        hit = m.find_header(m.read_tables("demo.csv", raw))
        self.assertIsNotNone(hit)
        kinds = {m.classify(o["type"]) for o in m.rows_to_ops(m.read_tables("demo.csv", raw)[0][1:], hit[3], m.read_tables("demo.csv", raw)[0][0])[0]}
        self.assertTrue({"buy", "sell", "coupons", "dividends", "deposits"} <= kinds)


if __name__ == "__main__":
    unittest.main()
