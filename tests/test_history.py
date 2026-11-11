"""Регрессионные тесты восстановления истории стоимости (build_history). Синтетические операции, без сети."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


class Offline:
    ready = False


def day(n):
    return (date(2024, 1, 1) + timedelta(days=n)).isoformat()


def money(x):
    return {"currency": "rub", "units": str(int(x)), "nano": int(round((x - int(x)) * 1e9))}


def op(n, typ, uid=None, pos=None, qty=0, pay=0.0, kind="INSTRUMENT_TYPE_SHARE"):
    o = {"date": day(n) + "T10:00:00Z", "type": "OPERATION_TYPE_" + typ, "payment": money(pay),
         "quantityDone": str(qty), "quantity": str(qty), "state": "OPERATION_STATE_EXECUTED"}
    if uid:
        o.update({"instrumentUid": uid, "positionUid": pos or uid, "instrumentKind": kind})
    return o


def candles(uid, price, n0=0, n1=400):
    M.store().candles_put(uid, [(day(i), price(i) if callable(price) else price) for i in range(n0, n1)])


def run(ops, names):
    h = M.build_history(Offline(), ops, names, 0)
    tw = h["twr"]
    rets = [tw[i] / tw[i - 1] - 1 for i in range(1, len(tw))]
    return h, rets


class History(unittest.TestCase):
    def test_same_position_under_two_uids(self):
        # покупка под одним instrumentUid, продажа под другим (общий positionUid): остатка быть не должно
        a, b = "h-two-a", "h-two-b"
        candles(b, 100.0)
        names = {a: {"type": "share", "cur": "rub"}, b: {"type": "share", "cur": "rub"}}
        ops = [op(0, "INPUT", pay=100000), op(1, "BUY", a, "pos-two", 10, -10000),
               op(50, "SELL", b, "pos-two", 10, 10100)]
        h, rets = run(ops, names)
        self.assertAlmostEqual(h["value"][-1], 100100, delta=1)
        self.assertAlmostEqual(h["value"][100], 100100, delta=1)
        self.assertLess(max(abs(r) for r in rets), 0.02)

    def test_futures_trade_payment_is_not_cash(self):
        fut = "h-fut"
        names = {fut: {"type": "futures", "cur": "rub"}}
        ops = [op(0, "INPUT", pay=100000), op(5, "BUY", fut, qty=1, pay=-30000, kind="INSTRUMENT_TYPE_FUTURES"),
               op(8, "SELL", fut, qty=1, pay=30500, kind="INSTRUMENT_TYPE_FUTURES")]
        h, rets = run(ops, names)
        self.assertAlmostEqual(h["value"][6], 100000, delta=1)         # пока контракт открыт, деньги на месте
        self.assertLess(max(abs(r) for r in rets), 0.001)

    def test_split_adjusted_candles(self):
        # цена сделки 1000, а свечи пересчитаны на сплит 1:10 (100): стоимость не должна падать в 10 раз
        s = "h-split"
        candles(s, 100.0)
        names = {s: {"type": "share", "cur": "rub"}}
        ops = [op(0, "INPUT", pay=20000), op(1, "BUY", s, qty=10, pay=-10000)]
        h, rets = run(ops, names)
        self.assertAlmostEqual(h["value"][30], 20000, delta=5)
        self.assertLess(max(abs(r) for r in rets), 0.001)

    def test_split_between_trades_keeps_value(self):
        # 10 акций куплены до сплита 1:10 по 1000, докупка после сплита по 100 при свечах 100: всего 110 в единицах свечи
        s = "h-split2"
        candles(s, 100.0)
        names = {s: {"type": "share", "cur": "rub"}}
        ops = [op(0, "INPUT", pay=20000), op(1, "BUY", s, qty=10, pay=-10000)]
        h, _ = run(ops, names)
        self.assertAlmostEqual(h["value"][20], 20000, delta=5)

    def test_coupon_cash_lag_keeps_nkd(self):
        # купон по графику 2024-07-04, деньги 07-05: в день графика НКД ещё не обнуляется
        u = "h-bond-cpn"
        M.store().put("bond:" + u, {"nominal": 1000.0, "initial": 1000.0, "cur": "rub", "maturity": "2035-01-01", "call": None,
                                    "placement": "2023-07-04", "cpy": 2, "aci": 0.0, "floating": False, "amort": False,
                                    "perpetual": False, "name": "T"})
        M.store().put("cpn:" + u, [["2024-01-04", 40.0], ["2024-07-04", 40.0], ["2025-01-04", 40.0]])
        candles(u, 100.0)
        names = {u: {"type": "bond", "cur": "rub"}}
        ops = [op(0, "INPUT", pay=200000), op(10, "BUY", u, qty=100, pay=-100000 - 3000, kind="INSTRUMENT_TYPE_BOND"),
               op(186, "COUPON", u, qty=0, pay=4000, kind="INSTRUMENT_TYPE_BOND")]
        self.assertEqual(day(185), "2024-07-04")
        h, rets = run(ops, names)
        self.assertLess(max(abs(r) for r in rets[11:300]), 0.005)

    def test_amortization_nominal_on_date(self):
        # номинал сейчас 750, но до выплаты 2024-06-10 (250 на бумагу) он был 1000: до неё бумага стоит 1000
        u = "h-bond-am"
        M.store().put("bond:" + u, {"nominal": 750.0, "initial": 1000.0, "cur": "rub", "maturity": "2035-01-01", "call": None,
                                    "placement": "2023-07-04", "cpy": 0, "aci": 0.0, "floating": False, "amort": True,
                                    "perpetual": False, "name": "A"})
        M.store().put("cpn:" + u, [])
        candles(u, 100.0)
        names = {u: {"type": "bond", "cur": "rub"}}
        ops = [op(0, "INPUT", pay=100000), op(10, "BUY", u, qty=10, pay=-10000, kind="INSTRUMENT_TYPE_BOND"),
               op(161, "BOND_REPAYMENT", u, qty=0, pay=2500, kind="INSTRUMENT_TYPE_BOND")]
        self.assertEqual(day(161), "2024-06-10")
        h, rets = run(ops, names)
        self.assertAlmostEqual(h["value"][100], 100000, delta=1)
        self.assertAlmostEqual(h["value"][200], 100000, delta=1)
        self.assertLess(max(abs(r) for r in rets), 0.001)

    def test_dividend_to_card_is_not_cash(self):
        # дивиденд на карту (DIV_EXT): доход и сразу вывод — на счёте денег не прибавляется, доходность его учитывает
        s = "h-divext"
        candles(s, 100.0)
        names = {s: {"type": "share", "cur": "rub"}}
        ops = [op(0, "INPUT", pay=100000), op(1, "BUY", s, qty=100, pay=-10000), op(50, "DIV_EXT", s, qty=0, pay=1000)]
        h, rets = run(ops, names)
        self.assertAlmostEqual(h["value"][-1], 100000, delta=1)
        self.assertAlmostEqual(h["invested"][-1], 99000, delta=1)
        self.assertGreater(h["twr"][-1], 1.0)

    def test_zero_priced_position_is_dropped_after_last_candle(self):
        s = "h-dead"
        M.store().candles_put(s, [(day(i), 100.0) for i in range(0, 60)])
        names = {s: {"type": "share", "cur": "rub"}}
        ops = [op(0, "INPUT", pay=100000), op(1, "BUY", s, qty=100, pay=-10000)]
        h = M.build_history(Offline(), ops, names, 0, None, {s})
        self.assertAlmostEqual(h["value"][59], 100000, delta=1)
        self.assertAlmostEqual(h["value"][-1], 90000, delta=1)


class Helpers(unittest.TestCase):
    def test_split_scale(self):
        self.assertEqual(M.split_scale(1.05), 1.0)
        self.assertEqual(M.split_scale(10.2), 10.0)
        self.assertAlmostEqual(M.split_scale(1 / 4900.0), 1 / 5000.0)
        self.assertIsNone(M.split_scale(2.6))
        self.assertIsNone(M.split_scale(0))

    def test_drop_spikes(self):
        rows = [("d1", 100.0), ("d2", 92.0), ("d3", 100.5), ("d4", 101.0)]
        self.assertEqual([r[0] for r in M.drop_spikes(rows, 0.05)], ["d1", "d3", "d4"])
        step = [("d1", 100.0), ("d2", 92.0), ("d3", 92.5), ("d4", 92.4)]       # настоящий уровень — не выбрасываем
        self.assertEqual(len(M.drop_spikes(step, 0.05)), 4)

    def test_amort_events_use_cash_date(self):
        bz = {"amort": [{"amortdate": "2024-06-10", "value": 250}, {"amortdate": "2024-09-10", "value": 250}]}
        ev = M.amort_events(bz, [("2024-06-11", 249.9)], "2024-12-31")
        self.assertEqual(ev, [("2024-06-11", 250.0), ("2024-09-10", 250.0)])
        self.assertEqual(M.amort_events(None, [("2024-06-11", 250.0)], "2024-12-31"), [("2024-06-11", 250.0)])


if __name__ == "__main__":
    unittest.main()
