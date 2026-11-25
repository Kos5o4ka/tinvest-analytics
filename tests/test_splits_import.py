"""Сплиты Мосбиржи в импорте отчётов: резидуал без «лишних» бумаг, пара X_CONV_OUT/X_CONV_IN при слиянии файлов,
консолидация, работа без сети. Сеть не используется: список сплитов подменяется."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402
from test_tbank_import import report, deal, cash  # noqa: E402

M = load()
ISIN = "RU000A0TEST1"
CODE = "TST"


def rep(frm, to, deals, ops, bal, pos):
    return report(frm, to, deals, ops, bal[0], bal[1], pos)


def parse(t):
    return M.tbank_parse(M.tb_detect(t))


def fin(ops, existing=None, periods=None):
    return M.finalize_import(M._NoClient(), ops, existing=existing, periods=periods, synth=False)[0]


class SplitTest(unittest.TestCase):
    splits = [{"date": "2025-04-17", "secid": CODE, "before": 1.0, "after": 10.0}]

    def setUp(self):
        self._old = (M.moex_splits_list, M.moex_secid_isin)
        M.moex_splits_list = lambda: list(self.splits)
        M.moex_secid_isin = lambda s: ISIN if s == CODE else ""

    def tearDown(self):
        M.moex_splits_list, M.moex_secid_isin = self._old

    # бумага: покупка 5 шт. по 1000 до сплита 1:10, после — 10 шт. по 100, продажа 20 шт. по 100
    def full(self):
        deals = [deal("S1", "01.03.2025", "11:00:00", "Покупка", CODE, 5, 5000.0),
                 deal("S2", "01.05.2025", "11:00:00", "Покупка", CODE, 10, 1000.0),
                 deal("S3", "01.06.2025", "11:00:00", "Продажа", CODE, 20, 2000.0)]
        ops = [cash("01.02.2025", "10:00:00", "02.02.2025", "Пополнение счета", cr=10000.0)]
        return rep("01.01.2025", "30.06.2025", deals, ops, (0.0, 6000.0), [(CODE, ISIN, 0, 40, 0, 40, 40)])

    def test_no_phantom_securities_inside_period(self):
        ops, meta = parse(self.full())
        self.assertEqual(meta["pos"][ISIN]["resid"], 0.0)
        self.assertFalse([o for o in ops if M.classify(o["type"]) in ("sec_in", "sec_out")])
        # без списка сплитов (нет сети) остаток 40 «берётся без сделки» — как было раньше
        M.moex_splits_list = lambda: []
        ops0, meta0 = parse(self.full())
        self.assertEqual(meta0["pos"][ISIN]["resid"], 45.0)           # 40 - (5 + 10 - 20)
        self.assertTrue(any(M.classify(o["type"]) == "sec_in" for o in ops0))

    def test_pair_converts_lots_without_realized_result(self):
        ops, meta = parse(self.full())
        out = fin(ops)
        pair = {o["id"]: o for o in out if o["id"].startswith("split:")}
        self.assertEqual(sorted(pair), ["split:%s:2025-04-17:in" % ISIN, "split:%s:2025-04-17:out" % ISIN])
        a, b = pair["split:%s:2025-04-17:out" % ISIN], pair["split:%s:2025-04-17:in" % ISIN]
        self.assertEqual((a["quantity"], b["quantity"]), ("5", "50"))
        self.assertEqual(M.qf(a["payment"]), 0.0)
        self.assertEqual(M.classify(a["type"]), "conv_out")
        self.assertEqual(M.classify(b["type"]), "conv_in")
        self.assertEqual(b["_conv"]["source"], "moex_split")
        self.assertEqual(b["_conv"]["label"], "Сплит 1:10 (Мосбиржа)")
        held = M.fifo(out)["imp:" + ISIN]
        self.assertEqual(held["qty"], 40)
        sell = next(o for o in out if o["id"] == "tb-S3")
        self.assertAlmostEqual(M.qf(sell["yield"]), 0.0, 2)           # 20 шт. по 100 из лота 5 шт. по 1000 -> 50 по 100: без результата
        self.assertAlmostEqual(held["cost"] / held["qty"], 100.0, 2)
        self.assertTrue(M.tbank_reconcile(ops, meta)["ok"])

    def test_pair_order_survives_storage(self):
        # хранилище отдаёт операции по (дата, ключ): «in» обязан идти после «out», иначе лоты теряются
        ops, _ = parse(self.full())
        out = fin(ops)
        M.store().ops_clear("imp-splittest")
        M.store().ops_put("imp-splittest", out)
        back = M.store().ops("imp-splittest")
        self.assertEqual(M.fifo(back)["imp:" + ISIN]["qty"], 40)
        M.store().ops_clear("imp-splittest")

    def test_split_between_two_files(self):
        f1 = rep("01.01.2025", "31.03.2025", [deal("S1", "01.03.2025", "11:00:00", "Покупка", CODE, 5, 5000.0)],
                 [cash("01.02.2025", "10:00:00", "02.02.2025", "Пополнение счета", cr=10000.0)], (0.0, 5000.0), [(CODE, ISIN, 0, 5, 0, 5, 5)])
        f2 = rep("01.04.2025", "30.06.2025", [deal("S2", "01.05.2025", "11:00:00", "Покупка", CODE, 10, 1000.0)], [],
                 (5000.0, 4000.0), [(CODE, ISIN, 5, 10, 0, 60, 60)])
        o1, m1 = parse(f1)
        o2, m2 = parse(f2)
        self.assertEqual(m2["pos"][ISIN]["resid"], 0.0)                 # 5 * 10 + 10 = 60, лишних бумаг нет
        a = fin(o1)
        per = [(m1["period"]["from"], m1["period"]["to"]), (m2["period"]["from"], m2["period"]["to"])]
        b = fin(o2, existing=a, periods=per)
        self.assertEqual(sum(1 for o in b if o["id"].startswith("split:")), 2)
        self.assertEqual(M.fifo(b)["imp:" + ISIN]["qty"], 60)
        c = fin(o2, existing=b, periods=per)                            # повторное слияние не дублирует пару
        self.assertEqual(sorted(o["id"] for o in c), sorted(o["id"] for o in b))
        # бумага осталась в портфеле после сплита: пара есть уже по одному первому файлу, а при слиянии пересчитывается, а не дублируется
        self.assertEqual(sorted(o["quantity"] for o in a if o["id"].startswith("split:")), ["5", "50"])

    def test_consolidation_100_to_1(self):
        self.splits = [{"date": "2025-04-17", "secid": CODE, "before": 100.0, "after": 1.0}]
        deals = [deal("C1", "01.03.2025", "11:00:00", "Покупка", CODE, 500, 5000.0)]
        f = rep("01.01.2025", "30.06.2025", deals, [cash("01.02.2025", "10:00:00", "02.02.2025", "Пополнение счета", cr=5000.0)],
                (0.0, 0.0), [(CODE, ISIN, 0, 5, 0, 5, 5)])
        ops, meta = parse(f)
        self.assertEqual(meta["pos"][ISIN]["resid"], 0.0)
        out = fin(ops)
        b = next(o for o in out if o["id"].endswith(":in"))
        self.assertEqual(b["quantity"], "5")
        self.assertEqual(b["_conv"]["label"], "Консолидация 100:1 (Мосбиржа)")
        held = M.fifo(out)["imp:" + ISIN]
        self.assertEqual((held["qty"], round(held["cost"] / held["qty"], 2)), (5, 1000.0))

    def test_split_before_history_or_zero_position_ignored(self):
        self.splits = [{"date": "2024-04-17", "secid": CODE, "before": 1.0, "after": 10.0},
                       {"date": "2025-05-10", "secid": CODE, "before": 1.0, "after": 10.0}]
        deals = [deal("Z1", "01.03.2025", "11:00:00", "Покупка", CODE, 5, 5000.0),
                 deal("Z2", "01.04.2025", "11:00:00", "Продажа", CODE, 5, 5000.0)]
        f = rep("01.01.2025", "30.06.2025", deals, [cash("01.02.2025", "10:00:00", "02.02.2025", "Пополнение счета", cr=5000.0)],
                (0.0, 5000.0), [(CODE, ISIN, 0, 5, 5, 0, 0)])
        ops, _ = parse(f)
        self.assertFalse([o for o in fin(ops) if o["id"].startswith("split:")])

    def test_fractional_position_split(self):
        deals = [deal("F1", "01.03.2025", "11:00:00", "Покупка", CODE, 0.25, 250.0)]
        f = rep("01.01.2025", "30.06.2025", deals, [cash("01.02.2025", "10:00:00", "02.02.2025", "Пополнение счета", cr=250.0)],
                (0.0, 0.0), [(CODE, ISIN, 0, 0.25, 0, 2.5, 2.5)])
        ops, meta = parse(f)
        self.assertEqual(meta["pos"][ISIN]["resid"], 0.0)
        out = fin(ops)
        pair = {o["id"]: o for o in out if o["id"].startswith("split:")}
        self.assertEqual(sorted(pair), ["split:%s:2025-04-17:in" % ISIN, "split:%s:2025-04-17:out" % ISIN])
        self.assertEqual(pair["split:%s:2025-04-17:out" % ISIN]["quantity"], "0.25")
        self.assertEqual(pair["split:%s:2025-04-17:in" % ISIN]["quantity"], "2.5")
        self.assertAlmostEqual(M.fifo(out)["imp:" + ISIN]["qty"], 2.5, places=6)


class SplitSource(unittest.TestCase):
    def test_no_network_means_no_splits(self):
        old = M.http_text
        try:
            def boom(*a, **k):
                raise OSError("нет сети")
            M.http_text = boom
            self.assertEqual(M._orig_moex_splits_list(), [])
            self.assertEqual(M.moex_secid_isin("NOPE"), "")
        finally:
            M.http_text = old

    def test_iss_answer_parsed_and_cached(self):
        old, calls = M.http_text, []
        data = {"splits": {"columns": ["tradedate", "secid", "before", "after"],
                           "data": [["2026-04-17", "T", 1, 10], ["2025-01-01", "RU000A0JRKT8", 100, 1]]}}
        try:
            M.http_text = lambda url, timeout=25: calls.append(url) or json.dumps(data)
            rows = M._orig_moex_splits_list()
            self.assertEqual(rows[0], {"date": "2026-04-17", "secid": "T", "before": 1.0, "after": 10.0})
            self.assertEqual(len(rows), 2)
            self.assertEqual(M._orig_moex_splits_list(), rows)
            self.assertEqual(len(calls), 1)                            # второй раз — из кэша
        finally:
            M.http_text = old
            M.store().delete_prefix("moex:splits")


if __name__ == "__main__":
    unittest.main()
