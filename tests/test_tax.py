"""Тесты налогового движка (лоты FIFO, ЛДВ, прогрессия, перенос убытков, НКД, курсы) на синтетических операциях. Без сети."""
import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()
_n = [0]


def money(v, cur="rub"):
    return M.to_money(v, cur)


def op(day, typ, pay=0.0, qty=0, uid="u1", itype="share", price=None, comm=None, nkd=None, acc="A", cur="rub", name="Бумага"):
    _n[0] += 1
    o = {"id": "o%d" % _n[0], "date": day + "T10:00:00Z", "type": "OPERATION_TYPE_" + typ, "payment": money(pay, cur), "instrumentUid": uid,
         "instrumentType": itype, "name": name, "ticker": "TST", "_acc": acc, "state": "OPERATION_STATE_EXECUTED"}
    if qty:
        o["quantity"] = o["quantityDone"] = str(qty)
    if price is not None:
        o["price"] = money(price, cur)
    if comm:
        o["commission"] = money(-abs(comm), cur)
    if nkd:
        o["accruedInt"] = money(nkd, cur)
    return o


def buy(day, qty, price, **kw):
    return op(day, "BUY", -qty * price - kw.get("nkd", 0), qty, price=price, **kw)


def sell(day, qty, price, **kw):
    return op(day, "SELL", qty * price + kw.get("nkd", 0), qty, price=price, **kw)


def group(ops, extra=None, carry=None, offset=False, fx=None):
    e = M.tax_engine(ops, None, fx)
    inc = {}
    for (acc, y), v in e["inc"].items():
        d = inc.setdefault(y, {})
        for k, x in v.items():
            d[k] = d.get(k, 0.0) + x
    rows, pool = M.tax_group_years(e["sales"], inc, carry, False, extra, offset)
    return e, {r["year"]: r for r in rows}, pool


class Fifo(unittest.TestCase):
    def test_partial_sale_with_fees(self):
        ops = [buy("2024-01-10", 10, 100, comm=1), buy("2024-02-10", 10, 120, comm=1), sell("2024-06-01", 15, 130, comm=3)]
        e, rows, _ = group(ops)
        self.assertAlmostEqual(sum(s["qty"] for s in e["sales"]), 15)
        self.assertAlmostEqual(rows[2024]["trade"], 1950 - 1001 - 600.5 - 3, places=6)
        self.assertEqual(len(e["open"]), 1)
        self.assertAlmostEqual(e["open"][0]["qty"], 5)
        self.assertAlmostEqual(e["open"][0]["unit"], 120.1, places=6)

    def test_broker_fee_operation_attached(self):
        b = buy("2024-01-10", 10, 100)
        fee = op("2024-01-10", "BROKER_FEE", -5)
        fee["parentOperationId"] = b["id"]
        e, rows, _ = group([b, fee, sell("2024-03-01", 10, 110)])
        self.assertAlmostEqual(rows[2024]["trade"], 100 - 5, places=6)

    def test_commission_not_doubled(self):
        b = buy("2024-01-10", 10, 100, comm=5)
        fee = op("2024-01-10", "BROKER_FEE", -5)
        fee["parentOperationId"] = b["id"]
        e, rows, _ = group([b, fee, sell("2024-03-01", 10, 110)])
        self.assertAlmostEqual(rows[2024]["trade"], 95, places=6)

    def test_nkd(self):
        ops = [buy("2024-01-10", 2, 950, itype="bond", nkd=30), sell("2024-03-01", 2, 980, itype="bond", nkd=50),
               op("2024-02-01", "COUPON", 100, itype="bond")]
        e, rows, _ = group(ops)
        r = rows[2024]
        self.assertAlmostEqual(r["trade"], 2 * 980 - 2 * 950, places=6)
        self.assertAlmostEqual(r["coupons"], 100 + 50 - 30, places=6)

    def test_amortization_reduces_cost(self):
        ops = [buy("2024-01-10", 10, 1000, itype="bond"), op("2024-03-01", "BOND_REPAYMENT", 2000, itype="bond"), sell("2024-05-01", 10, 850, itype="bond")]
        e, rows, _ = group(ops)
        self.assertAlmostEqual(rows[2024]["trade"], 8500 - 8000, places=6)

    def test_full_repayment_realizes_result(self):
        ops = [buy("2024-01-10", 10, 900, itype="bond"), op("2024-12-01", "BOND_REPAYMENT_FULL", 10000, itype="bond")]
        e, rows, _ = group(ops)
        self.assertAlmostEqual(rows[2024]["trade"], 1000, places=6)
        self.assertEqual(e["open"], [])

    def test_residual_cost_written_off_when_position_gone(self):
        ops = [buy("2024-01-10", 10, 1050, itype="bond"), op("2024-12-01", "BOND_REPAYMENT", 9000, itype="bond")]
        e = M.tax_engine(ops, None, None, held={})
        self.assertAlmostEqual(sum(s["result"] for s in e["sales"]), -1500, places=6)

    def test_short_then_cover(self):
        e, rows, _ = group([sell("2024-01-10", 5, 100), buy("2024-02-10", 5, 90)])
        self.assertAlmostEqual(rows[2024]["trade"], 50, places=6)


class Ldv(unittest.TestCase):
    def test_exactly_three_years_is_not_enough(self):
        e, rows, _ = group([buy("2020-03-10", 10, 100), sell("2023-03-10", 10, 200)])
        self.assertFalse(e["sales"][0]["ldv"])
        self.assertAlmostEqual(rows[2023]["tax"], 1000 * 0.13, places=6)

    def test_day_after_three_years(self):
        e, rows, _ = group([buy("2020-03-10", 10, 100), sell("2023-03-11", 10, 200)])
        self.assertTrue(e["sales"][0]["ldv"])
        self.assertEqual(e["sales"][0]["yrs"], 3)
        self.assertAlmostEqual(rows[2023]["ldv_exempt"], 1000)
        self.assertAlmostEqual(rows[2023]["tax"], 0)
        self.assertAlmostEqual(rows[2023]["ldv_saved"], 130, places=6)

    def test_less_than_three_years_and_before_2014(self):
        e, rows, _ = group([buy("2021-03-10", 10, 100), sell("2024-03-09", 10, 200)])
        self.assertFalse(e["sales"][0]["ldv"])
        self.assertFalse(M.tx_ldv_ok(date(2013, 5, 1), date(2020, 1, 1)))

    def test_limit_3m_per_full_year(self):
        e, rows, _ = group([buy("2019-01-10", 1000, 10000), sell("2022-06-01", 1000, 30000)])
        r = rows[2022]
        self.assertAlmostEqual(r["trade"], 20000000)
        self.assertAlmostEqual(r["ldv_limit"], 9000000)
        self.assertAlmostEqual(r["ldv_exempt"], 9000000)
        self.assertAlmostEqual(r["trade_base"], 11000000)

    def test_ldv_loss_is_not_exempt(self):
        e, rows, _ = group([buy("2019-01-10", 10, 100), sell("2023-01-11", 10, 50)])
        self.assertAlmostEqual(rows[2023]["ldv_exempt"], 0)
        self.assertAlmostEqual(rows[2023]["loss_new"], 500)

    def test_currency_ignored(self):
        e, rows, _ = group([buy("2024-01-10", 1, 100, itype="currency"), sell("2024-02-10", 1, 200, itype="currency")])
        self.assertEqual(e["sales"], [])


class Rates(unittest.TestCase):
    def test_progression_by_year(self):
        self.assertAlmostEqual(M.tx_ndfl(3000000, 2025)[0], 2400000 * 0.13 + 600000 * 0.15)
        self.assertAlmostEqual(M.tx_ndfl(3000000, 2023)[0], 390000)
        self.assertAlmostEqual(M.tx_ndfl(6000000, 2024)[0], 5000000 * 0.13 + 1000000 * 0.15)
        self.assertAlmostEqual(M.tx_ndfl(-5, 2025)[0], 0)

    def test_progression_in_report(self):
        e, rows, _ = group([buy("2025-01-10", 1, 1000000), sell("2025-06-01", 1, 4000000)])
        self.assertAlmostEqual(rows[2025]["tax"], 402000, places=4)
        self.assertAlmostEqual(rows[2025]["tax15"], 90000, places=4)


class Netting(unittest.TestCase):
    def test_loss_and_gain_same_year(self):
        ops = [buy("2024-01-10", 10, 100, uid="a"), sell("2024-02-10", 10, 200, uid="a"),
               buy("2024-01-10", 10, 100, uid="b"), sell("2024-02-10", 10, 60, uid="b")]
        e, rows, _ = group(ops)
        self.assertAlmostEqual(rows[2024]["trade"], 600)
        self.assertAlmostEqual(rows[2024]["tax"], 600 * 0.13, places=6)

    def test_carry_forward_auto(self):
        ops = [buy("2023-01-10", 10, 100), sell("2023-02-10", 10, 90),
               buy("2024-01-10", 10, 100, uid="b"), sell("2024-02-10", 10, 115, uid="b")]
        e, rows, pool = group(ops)
        self.assertAlmostEqual(rows[2023]["loss_new"], 100)
        self.assertAlmostEqual(rows[2024]["carry_used"], 100)
        self.assertAlmostEqual(rows[2024]["trade_base"], 50)
        self.assertAlmostEqual(rows[2024]["tax"], 6.5, places=6)
        self.assertEqual(pool, [])

    def test_carry_from_user_declaration(self):
        e, rows, _ = group([buy("2024-01-10", 10, 100), sell("2024-02-10", 10, 200)], carry={"2021": 400})
        self.assertAlmostEqual(rows[2024]["carry_used"], 400)
        self.assertAlmostEqual(rows[2024]["tax"], 600 * 0.13, places=6)

    def test_carry_expires_after_ten_years(self):
        e, rows, _ = group([buy("2024-01-10", 10, 100), sell("2024-02-10", 10, 200)], carry={"2010": 400})
        self.assertAlmostEqual(rows[2024]["carry_used"], 0)

    def test_two_accounts_are_netted(self):
        sel = [{"id": "A", "name": "A", "type": ""}, {"id": "B", "name": "B", "type": ""}]
        ops = [buy("2024-01-10", 10, 100, acc="A"), sell("2024-02-10", 10, 200, acc="A"),
               buy("2024-01-10", 10, 100, acc="B", uid="x"), sell("2024-02-10", 10, 60, acc="B", uid="x")]
        st = M.tax_compute(ops, {}, None, sel, {"iis": {}, "loss_carry": {}}, today=date(2024, 12, 1))
        self.assertEqual(len(st["groups"]), 1)
        self.assertAlmostEqual(st["years"][0]["trade"], 600)

    def test_iis_is_separate_and_exempt_after_term(self):
        sel = [{"id": "A", "name": "A", "type": ""}, {"id": "I", "name": "I", "type": "ИИС", "opened": "2019-01-01T00:00:00Z"}]
        ops = [buy("2024-01-10", 10, 100, acc="A"), sell("2024-02-10", 10, 200, acc="A"),
               buy("2024-01-10", 10, 100, acc="I", uid="x"), sell("2024-02-10", 10, 200, acc="I", uid="x"),
               op("2020-01-10", "INPUT", 500000, acc="I")]
        st = M.tax_compute(ops, {}, None, sel, {"iis": {"I": {"type": "B", "opened": ""}}, "loss_carry": {}}, today=date(2024, 12, 1))
        self.assertEqual(len(st["groups"]), 2)
        iis = [g for g in st["groups"] if g["kind"] == "iis"][0]
        self.assertTrue(iis["iis"]["exempt"])
        self.assertAlmostEqual(iis["rows"][-1]["tax"], 0)
        gen = [g for g in st["groups"] if g["kind"] == "gen"][0]
        self.assertAlmostEqual(gen["rows"][0]["tax"], 130, places=6)
        self.assertEqual(M.tx_iis_table(st, {})[0]["deduct_total"], 0)
        st2 = M.tax_compute(ops, {}, None, sel, {"iis": {"I": {"type": "A", "opened": ""}}, "loss_carry": {}}, today=date(2024, 12, 1))
        self.assertAlmostEqual(M.tx_iis_table(st2, {})[0]["deduct_total"], 400000 * 0.13)

    def test_offset_coupons_option(self):
        ops = [buy("2024-01-10", 10, 100), sell("2024-02-10", 10, 50), op("2024-03-01", "COUPON", 800, itype="bond", uid="b")]
        self.assertAlmostEqual(group(ops, offset=False)[1][2024]["tax"], 800 * 0.13, places=6)
        self.assertAlmostEqual(group(ops, offset=True)[1][2024]["tax"], 300 * 0.13, places=6)

    def test_withheld_comparison(self):
        ops = [buy("2024-01-10", 10, 100), sell("2024-02-10", 10, 200), op("2024-12-20", "TAX", -100)]
        r = group(ops)[1][2024]
        self.assertAlmostEqual(r["withheld"], 100)
        self.assertAlmostEqual(r["diff"], 30, places=6)
        self.assertAlmostEqual(r["diff_pct"], 30, places=4)


class Fx(unittest.TestCase):
    def test_foreign_currency_security(self):
        rates = {"2024-01-10": 90.0, "2024-06-01": 100.0}
        fx = lambda cur, day: rates.get(day) if cur == "usd" else 1.0
        ops = [buy("2024-01-10", 10, 100, cur="usd"), sell("2024-06-01", 10, 110, cur="usd")]
        self.assertAlmostEqual(group(ops, fx=fx)[1][2024]["trade"], 20000, places=4)

    def test_cbr_parse(self):
        xml = ('<?xml version="1.0" encoding="windows-1251"?><ValCurs Date="11.11.2025"><Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode>'
               '<Nominal>1</Nominal><Name>Доллар США</Name><Value>81,5000</Value></Valute><Valute ID="R01375"><NumCode>156</NumCode><CharCode>CNY</CharCode>'
               '<Nominal>10</Nominal><Name>Юаней</Name><Value>114,2000</Value></Valute></ValCurs>').encode("windows-1251")
        old = M.http_bytes
        M.http_bytes = lambda url, timeout=30: xml
        try:
            self.assertAlmostEqual(M.tax_cbr_rate("usd", "2020-05-05"), 81.5)
            self.assertAlmostEqual(M.tax_cbr_rate("CNY", "2020-05-05"), 11.42)
            self.assertEqual(M.tax_cbr_rate("rub", "2020-05-05"), 1.0)
        finally:
            M.http_bytes = old


class Hints(unittest.TestCase):
    def setUp(self):
        self.sel = [{"id": "A", "name": "A", "type": ""}]
        self.ops = [buy("2024-01-10", 10, 100, uid="g"), sell("2024-03-10", 10, 300, uid="g"),
                    buy("2024-02-01", 10, 100, uid="l"), buy("2021-11-20", 10, 100, uid="w")]
        self.pos = [{"uid": "l", "type": "share", "qty": 10, "price": 60.0, "value": 600.0, "value_rub": 600.0, "name": "l", "ticker": "L"},
                    {"uid": "w", "type": "share", "qty": 10, "price": 150.0, "value": 1500.0, "value_rub": 1500.0, "name": "w", "ticker": "W"}]
        self.s = {"iis": {}, "loss_carry": {}}

    def test_harvest_and_ldv_warning(self):
        st = M.tax_compute(self.ops, {}, self.pos, self.sel, self.s, today=date(2024, 11, 1))
        h = M.tx_hints(st, self.s)
        self.assertEqual(len(h["harvest"]), 1)
        c = h["harvest"][0]
        self.assertEqual(c["uid"], "l")
        self.assertAlmostEqual(c["saving"], 400 * 0.13, places=1)
        self.assertGreater(c["net"], 0)
        self.assertEqual([e["uid"] for e in h["ldv_warn"]], ["w"])
        up, _, _ = M.tx_ldv_tables(st)
        self.assertEqual(up[0]["days"], 20)

    def test_reb_plan_prefers_loss_position(self):
        st = M.tax_compute(self.ops, {}, self.pos, self.sel, self.s, today=date(2024, 11, 1))
        plan = M.tax_reb_plan(st, self.s, {"share": 600.0})[0]
        self.assertEqual(plan["plan"][0]["uid"], "l")
        self.assertLessEqual(plan["tax_plan"], plan["tax_naive"])


class Settings(unittest.TestCase):
    def test_roundtrip_and_validation(self):
        s = M.tax_settings_save({}, {"iis": {"X": {"type": "B", "opened": "2020-02-03"}}, "loss_carry": {"2022": "12 500,5"}, "offset_coupons": True})
        self.assertEqual(s["iis"]["X"]["type"], "B")
        self.assertAlmostEqual(s["loss_carry"]["2022"], 12500.5)
        self.assertTrue(s["offset_coupons"])
        with self.assertRaises(M.ApiError):
            M.tax_settings_save({}, {"loss_carry": {"abc": 5}})
        with self.assertRaises(M.ApiError):
            M.tax_settings_save({}, {"iis": {"X": {"type": "B", "opened": "03.02.2020"}}})
        M.tax_settings_save({}, {"iis": {}, "loss_carry": {}, "offset_coupons": False})

    def test_empty_data(self):
        s = {"iis": {}, "loss_carry": {}}
        st = M.tax_compute([], {}, [], [{"id": "A", "name": "A", "type": ""}], s)
        p = M.tax_payload_from(st, s)
        self.assertEqual(p["years"], [])
        json.dumps(p)


if __name__ == "__main__":
    unittest.main()
