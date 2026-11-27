"""Ручной учёт сделок (10e_manual_ops.py): построение записей, правка и удаление, сверка с отчётом брокера без дублей."""
import base64
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

M = _load.load()
ISIN = "RU0009029540"
CSV_HEAD = "Дата;Тип операции;ISIN;Тикер;Название;Количество;Цена;Сумма;Валюта;Комиссия;НКД\n"


def body(**kw):
    d = {"kind": "buy", "date": "2025-11-15", "ident": ISIN, "ticker": "SBER", "name": "Сбербанк", "qty": 10, "price": 280, "autocash": True}
    d.update(kw)
    return d


class Isolated(unittest.TestCase):
    def setUp(self):
        self.st = M.store()
        self._old = self.st.get("imports")
        self._old_ops = {a["id"]: self.st.ops(a["id"]) for a in self._old or []}
        for a in self._old or []:
            self.st.ops_clear(a["id"])
        self.st.put("imports", [])
        self.cfg = M.load_config()

    def tearDown(self):
        for a in M.imports_list():
            self.st.ops_clear(a["id"])
        self.st.put("imports", self._old or [])
        for aid, ops in self._old_ops.items():
            self.st.ops_put(aid, ops)
        M.mem_clear()

    def add(self, **kw):
        kw.setdefault("acc_name", "Ручной") if "acc" not in kw else None
        return M.manual_post(self.cfg, body(**kw))

    def csv(self, rows, name="r.csv", target=""):
        raw = (CSV_HEAD + rows).encode("utf-8")
        pv = M.import_preview_any(name, raw)
        return {"filename": name, "data": base64.b64encode(raw).decode(), "table": pv["table"], "header_row": pv["header_row"],
                "mapping": pv["mapping"], "name": "Сбер", "broker": "Сбербанк", "target": target}


class Build(Isolated):
    def test_buy_makes_trade_commission_and_cash(self):
        ops = M.manual_build(body(commission=8.4))
        self.assertEqual([o["id"][-2:] for o in ops][1:], ["-f", "-c"])
        main, fee, cash = ops
        self.assertTrue(main["_manual"] and main["id"].startswith("man-"))
        self.assertEqual(M.qf(main["payment"]), -2800.0)
        self.assertEqual(M.qf(fee["payment"]), -8.4)
        self.assertEqual(M.qf(cash["payment"]), 2808.4)
        self.assertEqual((main["_ident"], main["_isin"], main["_ticker"], main["quantity"]), (ISIN, ISIN, "SBER", "10"))
        self.assertTrue(cash["_manual_autocash"] and cash["_pair"] == main["id"])

    def test_bond_amount_with_nkd_and_explicit_total(self):
        ops = M.manual_build(body(qty=5, price=980.5, nkd=12.5))
        self.assertEqual(M.qf(ops[0]["payment"]), -(5 * 980.5 + 12.5))
        ops = M.manual_build(body(qty=5, price=None, amount=4900))
        self.assertEqual(M.qf(ops[0]["payment"]), -4900.0)

    def test_sell_and_income_have_no_autocash(self):
        self.assertEqual(len(M.manual_build(body(kind="sell"))), 1)
        d = M.manual_build(body(kind="dividend", qty=None, price=None, amount=3480))[0]
        self.assertEqual((M.classify(d["type"]), M.qf(d["payment"])), ("dividends", 3480.0))
        w = M.manual_build({"kind": "withdraw", "amount": "10 000,5", "date": "2025-11-01"})[0]
        self.assertEqual(M.qf(w["payment"]), -10000.5)

    def test_position_mode_is_buy_flagged(self):
        main = M.manual_build(body(mode="position", date=None))[0]
        self.assertTrue(main["_position"])
        self.assertEqual(M.classify(main["type"]), "buy")

    def test_validation(self):
        bad = [body(kind="swap"), body(date="31.02.2025"), body(date="2999-01-01"), body(ident=""), body(qty=0), body(qty="abc"),
               body(price=None), body(currency="рубли"), body(qty=-3), body(group="../etc")]
        for b in bad:
            with self.assertRaises(M.ApiError, msg=str(b)):
                M.manual_build(b)


class Lifecycle(Isolated):
    def test_create_account_position_edit_delete(self):
        r = self.add(commission=5)
        acc, gid = r["acc"], r["group"]
        self.assertTrue(acc.startswith("imp-"))
        ops = self.st.ops(acc)
        self.assertEqual(len(ops), 3)
        pos = M.fifo(ops)
        self.assertEqual(round(pos["imp:" + ISIN]["qty"]), 10)
        cash = sum(M.qf(o["payment"]) for o in ops)
        self.assertAlmostEqual(cash, 0.0, places=2)               # пополнение под покупку закрывает минус
        # правка: количество 12
        M.manual_post(self.cfg, body(acc=acc, group=gid, qty=12, commission=5))
        ops = self.st.ops(acc)
        self.assertEqual(len(ops), 3)
        self.assertEqual(round(M.fifo(ops)["imp:" + ISIN]["qty"]), 12)
        # список для правки
        rows = M.manual_list(self.cfg, "all", {"acc": acc}, False)["rows"]
        self.assertEqual((len(rows), rows[0]["qty"], rows[0]["commission"], rows[0]["autocash"]), (1, 12, 5.0, True))
        # удаление уносит всю группу
        r2 = M.manual_post(self.cfg, {"action": "delete", "acc": acc, "group": gid})
        self.assertEqual(r2["removed"], 3)
        self.assertEqual(self.st.ops(acc), [])
        with self.assertRaises(M.ApiError):
            M.manual_post(self.cfg, {"action": "delete", "acc": acc, "group": gid})

    def test_sale_produces_yield(self):
        acc = self.add()["acc"]
        M.manual_post(self.cfg, body(acc=acc, kind="sell", date="2025-11-20", qty=4, price=300))
        sells = [o for o in self.st.ops(acc) if M.classify(o["type"]) == "sell"]
        self.assertAlmostEqual(M.qf(sells[0]["yield"]), 4 * 300 - 4 * 280, places=2)

    def test_only_import_accounts_and_not_snapshots(self):
        self.st.put("imports", [{"id": "imp-tb-111", "name": "снимок", "sync_src": "tinvest", "src_acc": "111", "files": []}])
        with self.assertRaises(M.ApiError):
            M.manual_post(self.cfg, body(acc="imp-tb-111"))
        with self.assertRaises(M.ApiError):
            M.manual_post(self.cfg, body(acc="2000123456"))
        with self.assertRaises(M.ApiError):
            M.manual_post(self.cfg, body())                       # нет ни счёта, ни названия нового


class Reconcile(Isolated):
    def man(self, **kw):
        ops = M.manual_build(body(**kw))
        for o in ops:
            if o.get("_ident"):
                o["_sec"] = o.pop("_ident")
        return ops

    def rep(self, day="2025-11-15", qty=10, pay=-2800.0, kind="BUY"):
        return {"id": "imp-r1", "date": day + "T10:00:00Z", "type": "OPERATION_TYPE_" + kind, "payment": M.to_money(pay),
                "quantity": str(qty), "quantityDone": str(qty), "_sec": ISIN}

    def test_matches_with_tolerances(self):
        ex = self.man()
        for kw in ({}, {"day": "2025-11-17"}, {"pay": -2810.0}, {"qty": 10}):
            kept, info = M.reconcile_manual_with_report(ex, [self.rep(**kw)])
            self.assertEqual(len(info), 1, kw)
            self.assertFalse([o for o in kept if o["id"] == ex[0]["id"]])

    def test_does_not_match_when_far(self):
        ex = self.man()
        for kw in ({"day": "2025-11-18"}, {"pay": -2900.0}, {"qty": 9}, {"kind": "SELL", "pay": 2800.0}):
            kept, info = M.reconcile_manual_with_report(ex, [self.rep(**kw)])
            self.assertEqual(info, [], kw)
            self.assertEqual(len(kept), len(ex))

    def test_one_report_row_closes_one_manual_trade(self):
        a, b = self.man(), self.man()
        kept, info = M.reconcile_manual_with_report(a + b, [self.rep()])
        self.assertEqual(len(info), 1)
        self.assertEqual(len([o for o in kept if M.classify(o["type"]) == "buy"]), 1)

    def test_companions_follow_only_if_report_has_its_own(self):
        ex = self.man(commission=8)
        kept, _i = M.reconcile_manual_with_report(ex, [self.rep()])
        self.assertEqual(len(kept), 2)                            # в отчёте нет ни комиссий, ни пополнений: остаются
        fee = {"id": "imp-r1-f", "date": "2025-11-15T10:00:00Z", "type": "OPERATION_TYPE_BROKER_FEE", "payment": M.to_money(-8)}
        dep = {"id": "imp-r2", "date": "2025-11-14T10:00:00Z", "type": "OPERATION_TYPE_INPUT", "payment": M.to_money(5000)}
        kept, _i = M.reconcile_manual_with_report(ex, [self.rep(), fee, dep])
        self.assertEqual(kept, [])                                # в отчёте есть свои: ручные уходят вместе со сделкой

    def test_non_manual_and_other_instruments_untouched(self):
        plain = dict(self.man()[0], _manual=False)
        kept, info = M.reconcile_manual_with_report([plain], [self.rep()])
        self.assertEqual((info, len(kept)), ([], 1))
        other = self.man(ident="RU0009024277", ticker="LKOH")
        kept, info = M.reconcile_manual_with_report(other, [self.rep()])
        self.assertEqual(info, [])


class ReportImport(Isolated):
    REPORT = ("05.11.2025;Пополнение;;;;;;100000;RUB;;\n"
              "15.11.2025 10:00:00;Покупка;RU0009029540;SBER;Сбербанк;10;280;2800;RUB;;\n")

    def test_report_replaces_manual_duplicate_not_doubles(self):
        acc = self.add(acc_name="Сбер")["acc"]
        pv = M.import_parse_info(self.csv(self.REPORT, target=acc))
        self.assertEqual(pv["manual_matches"]["count"], 1)
        res = M.import_commit(M._NoClient(), self.csv(self.REPORT, target=acc))
        self.assertEqual(res["reconciled"], 1)
        ops = self.st.ops(acc)
        self.assertEqual(len([o for o in ops if M.classify(o["type"]) == "buy"]), 1)
        self.assertFalse([o for o in ops if o.get("_manual")])
        self.assertEqual(round(M.fifo(ops)["imp:" + ISIN]["qty"]), 10)          # не 20
        self.assertAlmostEqual(sum(M.qf(o["payment"]) for o in ops), 100000 - 2800, places=2)   # деньги не задвоены

    def test_manual_only_account_keeps_unmatched_manual_when_first_report_arrives(self):
        acc = self.add(acc_name="Сбер")["acc"]
        M.manual_post(self.cfg, body(acc=acc, date="2025-10-01", qty=3, price=250))        # этой сделки нет в отчёте
        M.import_commit(M._NoClient(), self.csv(self.REPORT, target=acc))
        ops = self.st.ops(acc)
        manual = [o for o in ops if o.get("_manual") and M.classify(o["type"]) == "buy"]
        self.assertEqual([round(M.op_qty(o)) for o in manual], [3])
        self.assertEqual(round(M.fifo(ops)["imp:" + ISIN]["qty"]), 13)

    def test_unrelated_manual_trade_is_not_swallowed(self):
        acc = self.add(acc_name="Сбер", qty=7, price=281)["acc"]                            # другое количество
        res = M.import_commit(M._NoClient(), self.csv(self.REPORT, target=acc))
        self.assertEqual(res["reconciled"], 0)
        self.assertEqual(round(M.fifo(self.st.ops(acc))["imp:" + ISIN]["qty"]), 17)


if __name__ == "__main__":
    unittest.main()
