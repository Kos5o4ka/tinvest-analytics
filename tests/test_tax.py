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

    def test_iis3_exempt_limit_single_year(self):
        rows, _ = M.tax_group_years([], {2025: {"coupon": 35e6}}, None, True)
        r = rows[0]
        self.assertAlmostEqual(r["iis_exempt_used"], 30e6)
        self.assertAlmostEqual(r["tax"], M.tx_ndfl(5e6, 2025)[0])

    def test_iis3_exempt_limit_cumulative(self):
        rows, _ = M.tax_group_years([], {2024: {"coupon": 20e6}, 2025: {"coupon": 15e6}}, None, True)
        self.assertAlmostEqual(rows[0]["tax"], 0)
        self.assertAlmostEqual(rows[1]["iis_exempt_used"], 10e6)
        self.assertAlmostEqual(rows[1]["tax"], M.tx_ndfl(5e6, 2025)[0])

    def test_iis3_small_profit_untaxed(self):
        rows, _ = M.tax_group_years([], {2025: {"coupon": 1e6}}, None, True)
        self.assertAlmostEqual(rows[0]["tax"], 0)
        self.assertAlmostEqual(rows[0]["iis_exempt_used"], 1e6)

    def test_iis_dividends_taxed_and_iis_b_unlimited(self):
        rows, _ = M.tax_group_years([], {2025: {"div": 1e6, "coupon": 1e6}}, None, True)
        self.assertAlmostEqual(rows[0]["iis_exempt_used"], 1e6)
        self.assertAlmostEqual(rows[0]["tax"], M.tx_ndfl(1e6, 2025)[0])

        sel = [{"id": "I", "name": "ИИС", "type": "ИИС", "opened": "2018-01-01T00:00:00Z"}]
        ops = [buy("2024-01-10", 1000, 10000, acc="I"), sell("2024-02-10", 1000, 60000, acc="I"),
               op("2024-03-01", "DIVIDEND", 100000, acc="I")]
        st_b = M.tax_compute(ops, {}, None, sel, {"iis": {"I": {"type": "B", "opened": "2018-01-01"}}, "loss_carry": {}}, today=date(2025, 1, 10))
        r_b = [g for g in st_b["groups"] if g["kind"] == "iis"][0]["rows"][0]
        self.assertAlmostEqual(r_b["iis_exempt_used"], 50e6)
        self.assertAlmostEqual(r_b["tax"], M.tx_ndfl(100000, 2024)[0])

        st_3 = M.tax_compute(ops, {}, None, sel, {"iis": {"I": {"type": "3", "opened": "2018-01-01"}}, "loss_carry": {}}, today=date(2025, 1, 10))
        r_3 = [g for g in st_3["groups"] if g["kind"] == "iis"][0]["rows"][0]
        self.assertAlmostEqual(r_3["iis_exempt_used"], 30e6)
        self.assertAlmostEqual(r_3["tax"], M.tx_ndfl(20e6 + 100000, 2024)[0])

    def test_iis_deduct_rate_15(self):
        sel = [{"id": "I", "name": "I", "type": "ИИС", "opened": "2019-01-01T00:00:00Z"}]
        ops = [op("2024-01-10", "INPUT", 500000, acc="I")]
        st = M.tax_compute(ops, {}, None, sel, {"iis": {"I": {"type": "A", "opened": ""}}, "loss_carry": {}}, today=date(2024, 12, 1))
        self.assertAlmostEqual(M.tx_iis_table(st, {"ndfl_rate": 15})[0]["deduct_total"], 400000 * 0.15)
        self.assertAlmostEqual(M.tx_iis_table(st, {})[0]["deduct_total"], 400000 * 0.13)

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


class Progressive(unittest.TestCase):
    def _row(self, base, year=2025, iis_used=0.0):
        r = {k: 0.0 for k in M.TAX_SUM_KEYS}
        r.update(year=year, base=base, iis_exempt_used=iis_used, tax=M.tx_ndfl(base - iis_used, year)[0], w={})
        return r

    def test_extra_progressive_on_combined_base(self):
        # два отдельных расчёта по 2 млн каждый (порог 2,4 млн) в сумме дают 4 млн: часть вместе облагается по 15 %
        rows = M.tx_sum_rows([[self._row(2000000.0)], [self._row(2000000.0)]])
        t = rows[0]
        self.assertAlmostEqual(t["tax"], 2 * 2000000 * 0.13)
        self.assertAlmostEqual(t["extra_progressive"], (4000000 - 2400000) * 0.02)

    def test_no_extra_when_below_threshold_or_exempt(self):
        self.assertEqual(M.tx_sum_rows([[self._row(1000000.0)], [self._row(1000000.0)]])[0]["extra_progressive"], 0.0)
        r = M.tx_sum_rows([[self._row(2000000.0)], [self._row(2000000.0, iis_used=2000000.0)]], [False, True])[0]
        self.assertEqual(r["extra_progressive"], 0.0)       # освобождённый ИИС в совокупную базу не входит


class FifoAmort(unittest.TestCase):
    def test_partial_repayment_reduces_cost(self):
        ops = [buy("2024-01-10", 10, 1000, uid="b1", itype="bond"),
               op("2024-06-10", "BOND_REPAYMENT", pay=2500, uid="b1", itype="bond")]
        f = M.fifo(ops)
        self.assertAlmostEqual(f["b1"]["qty"], 10)
        self.assertAlmostEqual(f["b1"]["cost"], 10 * 1000 - 2500)


if __name__ == "__main__":
    unittest.main()


class Forecast(unittest.TestCase):
    """Прогноз налога на 31.12 и сбор убытков."""

    def setUp(self):
        self.sel = [{"id": "A", "name": "A", "type": ""}]
        self.s = {"iis": {}, "loss_carry": {}}
        self.pos = [{"uid": "l", "type": "share", "qty": 10, "price": 60.0, "value": 600.0, "value_rub": 600.0, "name": "l", "ticker": "L"},
                    {"uid": "m", "type": "share", "qty": 10, "price": 80.0, "value": 800.0, "value_rub": 800.0, "name": "m", "ticker": "M"},
                    ]
        self.ops = [buy("2026-01-10", 10, 100, uid="g"), sell("2026-03-10", 10, 300, uid="g"),         # прибыль 2000
                    buy("2026-02-01", 10, 100, uid="l"), buy("2026-02-01", 10, 110, uid="m"),         # убытки 400 и 300
                    ]
        self.today = date(2026, 11, 12)

    def st(self):
        return M.tax_compute(self.ops, {}, self.pos, self.sel, self.s, today=self.today)

    def test_last_sale_day(self):
        self.assertEqual(M.tx_last_sale_day(2026), (date(2026, 12, 29), date(2026, 12, 30)))
        self.assertEqual(M.tx_last_sale_day(2025), (date(2025, 12, 29), date(2025, 12, 30)))
        # 2027: 31.12 — пятница, но считается выходным; 30.12 четверг; продавать до 29.12
        self.assertEqual(M.tx_last_sale_day(2027), (date(2027, 12, 29), date(2027, 12, 30)))
        # праздничный день из внешнего календаря сдвигает дату
        self.assertEqual(M.tx_last_sale_day(2026, {date(2026, 12, 30)})[1], date(2026, 12, 29))

    def test_forecast_numbers(self):
        f = M.tx_forecast(self.st(), self.s, [
            {"date": "2026-12-05", "kind": "coupon", "amount": 1000.0}, {"date": "2026-12-20", "kind": "dividend", "amount": 500.0},
            {"date": "2026-10-01", "kind": "coupon", "amount": 99999.0}, {"date": "2027-01-10", "kind": "coupon", "amount": 99999.0},
            {"date": "2026-12-25", "kind": "redemption", "amount": 99999.0}])
        r = f["forecast"]
        self.assertAlmostEqual(r["trade"], 2000.0)
        self.assertAlmostEqual(r["base"], 2000.0)
        self.assertAlmostEqual(r["exp_coupons"], 1000.0)
        self.assertAlmostEqual(r["exp_dividends"], 500.0)
        self.assertAlmostEqual(r["tax_end"], 3500 * 0.13)
        self.assertAlmostEqual(r["to_withhold"], 3500 * 0.13)
        self.assertEqual(f["sale_day"], "2026-12-29")

    def test_forecast_progressive_rate(self):
        f = M.tx_forecast(self.st(), self.s, [{"date": "2026-12-05", "kind": "coupon", "amount": 2500000.0}])
        r = f["forecast"]
        self.assertAlmostEqual(r["tax_end"], 2400000 * 0.13 + 102000 * 0.15)
        self.assertAlmostEqual(r["tax13"], 2400000 * 0.13)

    def test_forecast_without_payments_and_without_gen_accounts(self):
        f = M.tx_forecast(self.st(), self.s, None)
        self.assertFalse(f["pays_known"])
        self.assertAlmostEqual(f["forecast"]["tax_end"], 260.0)
        iis = [{"id": "A", "name": "A", "type": "iis"}]
        st = M.tax_compute(self.ops, {}, self.pos, iis, {"iis": {"A": {"type": "A"}}, "loss_carry": {}}, today=self.today)
        f = M.tx_forecast(st, self.s, [])
        if not f["available"]:
            self.assertEqual(f["harvest"], [])

    def test_harvest_order_and_ldv_flag(self):
        f = M.tx_forecast(self.st(), self.s, [])
        self.assertEqual([c["uid"] for c in f["harvest"]], ["l", "m"])                  # сначала больший убыток
        self.assertAlmostEqual(f["harvest"][0]["saving"], 400 * 0.13, places=1)
        self.assertAlmostEqual(f["harvest"][1]["saving_marginal"], 300 * 0.13, places=1)
        self.assertAlmostEqual(f["harvest_saving"], 700 * 0.13, places=1)
        self.assertEqual([c["uid"] for c in f["skipped"]], [])

    def test_ldv_soon_is_skipped(self):
        # w: лот 2023 года куплен по 100 (в прибыли, ЛДВ через 20 дней), лот 2026 года по 400 (убыток 2500): продажа всей позиции лишит ЛДВ
        self.pos.append({"uid": "w", "type": "share", "qty": 20, "price": 150.0, "value": 3000.0, "value_rub": 3000.0, "name": "w", "ticker": "W"})
        self.ops += [buy("2023-11-22", 10, 100, uid="w"), buy("2026-07-01", 10, 400, uid="w")]
        f = M.tx_forecast(self.st(), self.s, [])
        sk = [c for c in f["skipped"] if c["uid"] == "w"]
        self.assertEqual(len(sk), 1)
        self.assertEqual(sk[0]["ldv_days"], 11)
        self.assertIn("ЛДВ", sk[0]["reason"])
        self.assertNotIn("w", [c["uid"] for c in f["harvest"]])


class FeeKeyAllocation(unittest.TestCase):
    def test_same_second_fees_not_multiplied_n_squared(self):
        # Две покупки в одну секунду без parentOperationId + две комиссии -5 и -5 -> суммарная комиссия 10, а не 20
        ts = "2025-01-10T12:00:00Z"
        b1 = buy("2025-01-10", 1, 1000)
        b2 = buy("2025-01-10", 1, 1000)
        f1 = op("2025-01-10", "BROKER_FEE", -5)
        f2 = op("2025-01-10", "BROKER_FEE", -5)
        for o in (b1, b2, f1, f2):
            o["date"] = ts
        s = sell("2025-02-10", 2, 1100)
        eng = M.tax_engine([b1, b2, f1, f2, s], None, None)
        self.assertAlmostEqual(sum(r["cost"] for r in eng["sales"]), 2010.0, places=6)

    def test_fee_key_proportional_partial_coverage_and_zero_turnover(self):
        # t1 имеет собственную commission=-3; t4 привязана через parentOperationId (-7 не должна утечь в fee_key);
        # t2 (оборот 1000) и t3 (оборот 2000) делят общую комиссию 12 пропорционально 1:2 -> 4 и 8
        ts = "2025-01-10T12:00:00Z"
        t1 = buy("2025-01-10", 1, 1000, comm=3)
        t2 = buy("2025-01-10", 1, 1000)
        t3 = buy("2025-01-10", 1, 2000)
        t4 = buy("2025-01-10", 1, 500)
        f_parent = op("2025-01-10", "BROKER_FEE", -7)
        f_parent["parentOperationId"] = t4["id"]
        f_shared = op("2025-01-10", "BROKER_FEE", -12)
        for o in (t1, t2, t3, t4, f_parent, f_shared):
            o["date"] = ts
        eng = M.tax_engine([t1, t2, t3, t4, f_parent, f_shared], None, None)
        units = [round(l["unit"], 6) for l in eng["open"]]
        self.assertEqual(units, [1003.0, 1004.0, 2008.0, 507.0])

        # Нулевой оборот у трёх сделок в одну секунду -> равное деление с остатком на последнюю сделку, сумма строго 10.0
        z1 = op("2025-01-11", "BUY", 0.0, qty=1, uid="uz")
        z2 = op("2025-01-11", "BUY", 0.0, qty=1, uid="uz")
        z3 = op("2025-01-11", "BUY", 0.0, qty=1, uid="uz")
        fz = op("2025-01-11", "BROKER_FEE", -10, uid="uz")
        for o in (z1, z2, z3, fz):
            o["date"] = "2025-01-11T12:00:00Z"
        eng_z = M.tax_engine([z1, z2, z3, fz], None, None)
        self.assertAlmostEqual(sum(l["qty"] * l["unit"] for l in eng_z["open"]), 10.0, places=9)

    def test_finalize_import_preserves_imp_uid_on_fee_and_tax(self):
        class Offline:
            ready = False

        raw_ops = [
            {"id": "imp-1", "date": "2025-01-10T12:00:00Z", "type": "OPERATION_TYPE_BUY",
             "payment": money(-1000), "quantity": "1", "quantityDone": "1", "price": money(1000),
             "name": "Unknown", "_ident": "UNKNOWNISIN"},
            {"id": "imp-1-f", "date": "2025-01-10T12:00:00Z", "type": "OPERATION_TYPE_BROKER_FEE",
             "payment": money(-5), "name": "Комиссия: Unknown", "_ident": "UNKNOWNISIN"},
            {"id": "imp-1-t", "date": "2025-01-10T12:00:00Z", "type": "OPERATION_TYPE_TAX",
             "payment": money(-13), "name": "Налог", "_ident": "UNKNOWNISIN"},
            {"id": "imp-1-dt", "date": "2025-01-10T12:00:00Z", "type": "OPERATION_TYPE_DIVIDEND_TAX",
             "payment": money(-2), "name": "Налог див", "_ident": "UNKNOWNISIN"},
            {"id": "imp-1-ct", "date": "2025-01-10T12:00:00Z", "type": "OPERATION_TYPE_BOND_TAX",
             "payment": money(-1), "name": "Налог куп", "_ident": "UNKNOWNISIN"},
            {"id": "imp-2", "date": "2025-02-10T12:00:00Z", "type": "OPERATION_TYPE_SELL",
             "payment": money(1200), "quantity": "1", "quantityDone": "1", "price": money(1200),
             "name": "Unknown", "_ident": "UNKNOWNISIN"},
        ]
        finalized, _ = M.finalize_import(Offline(), raw_ops, keep_demo=True, synth=False)
        by_id = {o["id"]: o for o in finalized}
        self.assertEqual(by_id["imp-1-f"].get("instrumentUid"), "imp:UNKNOWNISIN")
        self.assertEqual(by_id["imp-1-t"].get("instrumentUid"), "imp:UNKNOWNISIN")
        self.assertEqual(by_id["imp-1-dt"].get("instrumentUid"), "imp:UNKNOWNISIN")
        self.assertEqual(by_id["imp-1-ct"].get("instrumentUid"), "imp:UNKNOWNISIN")
        eng = M.tax_engine(finalized, None, None)
        self.assertEqual(len(eng["sales"]), 1)
        self.assertAlmostEqual(eng["sales"][0]["cost"], 1005.0, places=6)


class FifoShortsAndEpsilon(unittest.TestCase):
    def test_float_epsilon_closes_position(self):
        ops = [buy("2025-01-10", 0.1, 100), buy("2025-01-11", 0.2, 100), sell("2025-01-12", 0.3, 100)]
        self.assertEqual(M.fifo(ops), {})

    def test_uncovered_short_sell_does_not_fabricate_100pct_yield(self):
        s = sell("2025-01-10", 10, 1000)
        res = M.fifo([s])
        self.assertEqual(res, {})
        self.assertAlmostEqual(s["_yield"], 0.0, places=9)

    def test_short_then_cover_realizes_profit_in_fifo_and_analyze(self):
        s = sell("2025-01-10", 10, 100)
        b = buy("2025-02-10", 10, 90)
        res = M.fifo([s, b])
        self.assertEqual(res, {})
        self.assertAlmostEqual(s["_yield"], 0.0, places=9)
        self.assertAlmostEqual(b["_yield"], 100.0, places=9)
        an = M.analyze([s, b], {}, "all", 0)
        self.assertAlmostEqual(an["life"].get("realized", 0.0), 100.0, places=6)


class NdflDeclarationPackage(unittest.TestCase):
    def test_decl_fx_payouts_and_cbr_conversion(self):
        rates = {"2024-03-15": 92.0, "2024-06-20": 12.5}
        fx = lambda cur, day: rates.get(day) if cur in ("usd", "cny") else 1.0
        div_usd = op("2024-03-15", "DIVIDEND", pay=100.0, uid="u_aapl", cur="usd", name="Apple")
        tax_usd = op("2024-03-15", "DIVIDEND_TAX", pay=-10.0, uid="u_aapl", cur="usd", name="Apple")
        tax_usd["parentOperationId"] = div_usd["id"]
        cpn_cny = op("2024-06-20", "COUPON", pay=200.0, uid="u_cny", itype="bond", cur="cny", name="Юань Бонд")
        div_rub = op("2024-07-01", "DIVIDEND", pay=500.0, uid="u_sber", cur="rub", name="Сбер")
        sel = [{"id": "A", "name": "Основной", "type": ""}]
        st = M.tax_compute([div_usd, tax_usd, cpn_cny, div_rub], {}, [], sel, {"iis": {}, "loss_carry": {}}, fx=fx)
        decl = M.tx_decl(st)
        self.assertIn(2024, decl)
        fxp = decl[2024]["fx_payouts"]
        self.assertEqual(len(fxp), 2)
        self.assertEqual(fxp[0]["cur"], "USD")
        self.assertAlmostEqual(fxp[0]["amount"], 100.0)
        self.assertAlmostEqual(fxp[0]["rate"], 92.0)
        self.assertAlmostEqual(fxp[0]["amount_rub"], 9200.0)
        self.assertAlmostEqual(fxp[0]["tax_orig"], 10.0)
        self.assertAlmostEqual(fxp[0]["tax_rub"], 920.0)
        self.assertIn("ЦБ РФ", fxp[0]["source"])
        self.assertEqual(fxp[1]["cur"], "CNY")
        self.assertAlmostEqual(fxp[1]["amount_rub"], 2500.0)

    def test_decl_sales_and_loss_carry_breakdown(self):
        ops = [
            buy("2023-01-10", 10, 100, uid="u1", name="Бумага 1"),
            sell("2023-06-01", 10, 60, uid="u1", name="Бумага 1"),
            buy("2024-01-10", 10, 100, uid="u2", name="Бумага 2"),
            sell("2024-06-01", 10, 130, uid="u2", name="Бумага 2"),
        ]
        sel = [{"id": "A", "name": "Основной", "type": ""}]
        st = M.tax_compute(ops, {}, [], sel, {"iis": {}, "loss_carry": {}})
        decl = M.tx_decl(st)
        g23 = decl[2023]["groups"][0]
        self.assertAlmostEqual(g23["loss_new"], 400.0)
        self.assertEqual(g23["carry_pool"], [{"year": 2023, "amount": 400.0}])
        self.assertEqual(len(g23["sales"]), 1)
        self.assertEqual(g23["sales"][0]["bdate"], "2023-01-10")
        self.assertEqual(g23["sales"][0]["sdate"], "2023-06-01")
        g24 = decl[2024]["groups"][0]
        self.assertAlmostEqual(g24["carry_used"], 300.0)
        self.assertAlmostEqual(g24["trade_base"], 0.0)
        self.assertEqual(g24["carry_pool"], [{"year": 2023, "amount": 100.0}])
        self.assertAlmostEqual(decl[2024]["loss_carry"]["carry_used"], 300.0)
        self.assertEqual(decl[2024]["loss_carry"]["pool"], [{"year": 2023, "amount": 100.0}])

    def test_decl_csv_endpoint_and_bom(self):
        rates = {"2024-03-15": 90.0}
        fx = lambda cur, day: rates.get(day) if cur == "usd" else 1.0
        ops = [
            buy("2024-01-10", 10, 100, uid="u1", name="Акция А"),
            sell("2024-05-10", 10, 150, uid="u1", name="Акция А"),
            op("2024-03-15", "DIVIDEND", pay=50.0, uid="u2", cur="usd", name="Microsoft"),
        ]
        sel = [{"id": "A", "name": "Основной", "type": ""}]
        st = M.tax_compute(ops, {}, [], sel, {"iis": {}, "loss_carry": {"2022": 200.0}}, fx=fx)
        old_state = M.tax_state
        M.tax_state = lambda cfg, acc, force=False: (st, {"iis": {}, "loss_carry": {"2022": 200.0}})
        try:
            code, body, ctype, headers = M.API_GET["/api/tax/decl.csv"]({}, "all", {"year": "2024"}, False)
        finally:
            M.tax_state = old_state
        self.assertEqual(code, 200)
        self.assertIn("text/csv", ctype)
        self.assertEqual(headers["Content-Disposition"], 'attachment; filename="3ndfl_2024.csv"')
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        text = body.decode("utf-8-sig")
        self.assertIn(";", text)
        self.assertIn("Сделка;Основной;2024-05-10;2024-01-10;Акция А", text)
        self.assertIn("Валютная выплата;Основной;2024-03-15;;Microsoft", text)
        self.assertIn(";USD;50,0;90,0;4500,0;", text)
        with self.assertRaises(M.ApiError):
            M.tax_decl_csv_get({}, "all", {"year": "bad"}, False)

