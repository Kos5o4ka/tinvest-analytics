"""Тесты обменов бумаг (ГДР -> акции, редомициляция): поиск, применение, налоговые лоты, история. Синтетические данные, без сети."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()
_n = [0]


def day(n):
    return (date(2024, 1, 1) + timedelta(days=n)).isoformat()


def money(x):
    return {"currency": "rub", "units": str(int(x)), "nano": int(round((x - int(x)) * 1e9))}


def op(iso, typ, uid, qty, pay=0.0, ticker="TST", acc="A", pos=None):
    _n[0] += 1
    return {"id": "c%d" % _n[0], "date": iso + "T10:00:00Z", "type": "OPERATION_TYPE_" + typ, "payment": money(pay),
            "quantity": str(qty), "quantityDone": str(qty), "instrumentUid": uid, "positionUid": pos or uid, "ticker": ticker,
            "instrumentType": "share", "instrumentKind": "INSTRUMENT_TYPE_SHARE", "_acc": acc, "state": "OPERATION_STATE_EXECUTED"}


def buy(iso, uid, qty, price, **kw):
    return op(iso, "BUY", uid, qty, -qty * price, **kw)


def sell(iso, uid, qty, price, **kw):
    return op(iso, "SELL", uid, qty, qty * price, **kw)


NAMES = {"gdr": {"isin": "NL0009805522", "ticker": "YNDX", "type": "share"},
         "sh": {"isin": "RU000A107T19", "ticker": "YDEX", "type": "share"},
         "oldx": {"isin": "ZZ0000000001", "ticker": "OLDX", "type": "share"},
         "newx": {"isin": "ZZ0000000002", "ticker": "NEWX", "type": "share"}}


class Find(unittest.TestCase):
    def test_table_per_account(self):
        ops = [buy("2024-01-10", "gdr", 5, 100, ticker="YNDX", acc="A"), buy("2024-01-11", "gdr", 3, 100, ticker="YNDX", acc="B"),
               sell("2024-09-01", "sh", 5, 110, ticker="YDEX", acc="A")]
        ev = M.find_conversions(ops, NAMES)
        self.assertEqual(sorted((e["acc"], e["old_qty"], e["new_qty"], e["source"]) for e in ev if e["new_ticker"] == "YDEX" and e["new_uid"] == "sh"),
                         [("A", 5, 5, "table")])
        # у счёта B новой бумаги в операциях нет и разрешить её нечем — обмен не создаётся
        self.assertFalse([e for e in ev if e["acc"] == "B"])
        ev = M.find_conversions(ops, NAMES, resolve=lambda t: "sh" if t == "YDEX" else None)
        self.assertEqual(sorted((e["acc"], e["old_qty"]) for e in ev), [("A", 5), ("B", 3)])
        a = [e for e in ev if e["acc"] == "A"][0]
        self.assertLess("2024-01-11", a["date"])
        self.assertLessEqual(a["date"], "2024-09-01")

    def test_auto_pair_exact_and_mismatch(self):
        ops = [buy("2024-01-10", "oldx", 7, 100, ticker="OLDX"), buy("2024-02-01", "newx", 3, 50, ticker="NEWX"),
               sell("2024-06-01", "newx", 10, 60, ticker="NEWX")]
        ev = M.find_conversions(ops, NAMES)
        self.assertEqual([(e["source"], e["old_qty"], e["date"]) for e in ev], [("auto", 7, "2024-06-01")])
        bad = ops[:-1] + [sell("2024-06-01", "newx", 11, 60, ticker="NEWX")]
        self.assertEqual(M.find_conversions(bad, NAMES), [])
        # старая бумага ещё в портфеле — не пара
        self.assertEqual(M.find_conversions(ops, NAMES, held={"oldx": 7}), [])

    def test_skip_when_broker_reflected(self):
        ops = [buy("2024-01-10", "gdr", 5, 100, ticker="YNDX"), op("2024-07-24", "INPUT_SECURITIES", "sh", 5, ticker="YDEX"),
               sell("2024-09-01", "sh", 5, 110, ticker="YDEX")]
        self.assertEqual(M.find_conversions(ops, NAMES), [])

    def test_held_cap(self):
        ops = [buy("2024-01-10", "gdr", 5, 100, ticker="YNDX"), buy("2024-08-01", "sh", 1, 100, ticker="YDEX")]
        ev = M.find_conversions(ops, NAMES, held={"sh": 3})
        self.assertEqual(ev[0]["new_qty"], 2)

    def test_apply_and_classify(self):
        ops = [buy("2024-01-10", "gdr", 5, 100, ticker="YNDX"), sell("2024-09-01", "sh", 5, 110, ticker="YDEX")]
        ev = M.find_conversions(ops, NAMES)
        out = M.apply_conversions(ops, ev)
        kinds = [M.classify(o["type"]) for o in out]
        self.assertEqual(kinds.count("conv_out"), 1)
        self.assertEqual(kinds.count("conv_in"), 1)
        self.assertEqual(M.analyze(out, {}, "all", 0)["life"].get("conv_in", 0), 0)


class Tax(unittest.TestCase):
    def test_lots_move_with_cost_and_date(self):
        ops = [buy("2023-01-10", "gdr", 5, 100, ticker="YNDX"), buy("2023-06-10", "gdr", 5, 200, ticker="YNDX"),
               sell("2024-09-01", "sh", 7, 300, ticker="YDEX")]
        ev = M.find_conversions(ops, NAMES)
        e = M.tax_engine(M.apply_conversions(ops, ev), None, None)
        self.assertNotIn("Есть продажи без покупок в истории (короткие позиции или переводы): учтены упрощённо.", e["warnings"])
        s = sorted(e["sales"], key=lambda r: r["bdate"])
        self.assertEqual([(r["qty"], r["bdate"].isoformat(), round(r["cost"])) for r in s],
                         [(5.0, "2023-01-10", 500), (2.0, "2023-06-10", 400)])
        self.assertEqual(len(e["open"]), 1)
        self.assertAlmostEqual(e["open"][0]["qty"], 3)
        self.assertEqual(e["open"][0]["uid"], "sh")
        self.assertAlmostEqual(e["open"][0]["unit"], 200)

    def test_without_conversion_is_short(self):
        ops = [buy("2023-01-10", "gdr", 5, 100, ticker="YNDX"), sell("2024-09-01", "sh", 5, 300, ticker="YDEX")]
        e = M.tax_engine(ops, None, None)
        self.assertTrue(e["warnings"])

    def test_fifo_transfers_cost(self):
        ops = [buy("2023-01-10", "gdr", 5, 100, ticker="YNDX"), sell("2024-09-01", "sh", 2, 300, ticker="YDEX")]
        out = M.apply_conversions(ops, M.find_conversions(ops, NAMES))
        f = M.fifo(out)
        self.assertEqual(list(f), ["sh"])
        self.assertAlmostEqual(f["sh"]["qty"], 3)
        self.assertAlmostEqual(f["sh"]["cost"], 300)


class Offline:
    ready = False


class History(unittest.TestCase):
    def test_value_continuous_through_conversion(self):
        M.store().candles_put("hg", [(day(i), 100.0) for i in range(0, 400)])
        M.store().candles_put("hn", [(day(i), 100.0) for i in range(0, 400)])
        names = {"hg": {"isin": "NL0009805522", "ticker": "YNDX", "type": "share", "cur": "rub"},
                 "hn": {"isin": "RU000A107T19", "ticker": "YDEX", "type": "share", "cur": "rub"}}
        ops = [op(day(0), "INPUT", None, 0, 100000), buy(day(1), "hg", 10, 100, ticker="YNDX"), sell(day(300), "hn", 10, 100, ticker="YDEX")]
        for o in ops[:1]:
            o.pop("instrumentUid"), o.pop("positionUid")
        h = M.build_history(Offline(), ops, names, 0)
        self.assertEqual(len(h["conversions"]), 1)
        self.assertEqual(h["conversions"][0]["new"], "YDEX")
        cd = h["days"].index(h["conversions"][0]["date"])
        v = h["value"]
        self.assertAlmostEqual(v[cd - 1], 100000, delta=1)
        self.assertAlmostEqual(v[cd], 100000, delta=1)
        self.assertAlmostEqual(v[-1], 100000, delta=1)
        self.assertEqual(h["invested"][cd], h["invested"][cd - 1])
        self.assertEqual(h["glitches"], 0)


if __name__ == "__main__":
    unittest.main()
