"""Тесты налоговой оптимизации: сбор убытков (префикс FIFO, потолок экономии, ставка 15 %, ЛДВ) и планировщик ИИС-3. Без сети."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402
from test_tax import buy, sell, op  # noqa: E402

M = load()
SEL = [{"id": "A", "name": "A", "type": ""}]
S0 = {"iis": {}, "loss_carry": {}}
TODAY = date(2024, 11, 1)


def pos(uid, qty, price):
    return {"uid": uid, "type": "share", "qty": qty, "price": price, "value": qty * price, "value_rub": qty * price, "name": uid, "ticker": uid.upper()}


def harvest(ops, positions, sel=SEL, fee=None):
    st = M.tax_compute(ops, {}, positions, sel, S0, today=TODAY)
    return M.txo_harvest_calc(st, S0, fee)


class Harvest(unittest.TestCase):
    def test_fifo_prefix_with_mixed_lots(self):
        # лоты по порядку: 10 @200 (убыток -500), 10 @100 (прибыль +500), 10 @180 (убыток -300) при цене 150
        ops = [buy("2024-01-10", 10, 1000, uid="g"), sell("2024-03-10", 10, 1500, uid="g"),
               buy("2024-01-05", 10, 200, uid="m"), buy("2024-02-05", 10, 100, uid="m"), buy("2024-03-05", 10, 180, uid="m")]
        h = harvest(ops, [pos("m", 30, 150.0)], fee=0.0)
        c = h["candidates"][0]
        self.assertAlmostEqual(c["qty"], 10)
        self.assertTrue(c["partial"])
        self.assertAlmostEqual(c["loss"], 500)
        self.assertAlmostEqual(c["saving"], 65, places=4)

    def test_prefix_includes_profitable_lot_when_deeper_loss(self):
        ops = [buy("2024-01-10", 10, 1000, uid="g"), sell("2024-03-10", 10, 1500, uid="g"),
               buy("2024-01-05", 10, 100, uid="m"), buy("2024-02-05", 10, 300, uid="m")]
        c = harvest(ops, [pos("m", 20, 150.0)], fee=0.0)["candidates"][0]
        self.assertAlmostEqual(c["qty"], 20)
        self.assertAlmostEqual(c["loss"], 1000)
        self.assertAlmostEqual(c["gain_in_prefix"], 500)

    def test_saving_capped_by_base(self):
        ops = [buy("2024-01-10", 10, 100, uid="g"), sell("2024-03-10", 10, 200, uid="g"),      # база 1000
               buy("2024-02-01", 100, 100, uid="l")]
        c = harvest(ops, [pos("l", 100, 70.0)], fee=0.0)["candidates"][0]               # убыток 3000
        self.assertAlmostEqual(c["loss"], 3000)
        self.assertAlmostEqual(c["saving"], 130, places=4)
        self.assertAlmostEqual(c["carry_forward"], 2000, places=4)

    def test_fees_reduce_net(self):
        ops = [buy("2024-01-10", 10, 100, uid="g"), sell("2024-03-10", 10, 200, uid="g"), buy("2024-02-01", 10, 100, uid="l")]
        c = harvest(ops, [pos("l", 10, 50.0)], fee=0.01)["candidates"][0]
        self.assertAlmostEqual(c["fees"], 500 * 0.01 * 2, places=6)
        self.assertLess(c["net"], c["saving"])

    def test_15_percent_bracket(self):
        # база 2024: 6 млн, порог 5 млн; убыток 1 млн целиком срезает часть по 15 %
        ops = [buy("2024-01-10", 1000, 100, uid="g"), sell("2024-03-10", 1000, 6100, uid="g"), buy("2024-02-01", 1000, 2000, uid="l")]
        h = harvest(ops, [pos("l", 1000, 1000.0)], fee=0.0)
        c = h["candidates"][0]
        self.assertAlmostEqual(h["rate_now"], 0.15)
        self.assertAlmostEqual(c["saving"], 150000, places=3)
        self.assertAlmostEqual(c["marginal_rate"], 0.15, places=4)

    def test_ldv_warning_close_and_reached(self):
        ops = [buy("2024-01-10", 10, 1000, uid="g"), sell("2024-03-10", 10, 1500, uid="g"),
               buy("2021-11-20", 10, 100, uid="w"), buy("2024-02-01", 10, 300, uid="w"),
               buy("2020-01-10", 10, 100, uid="r"), buy("2024-02-01", 10, 300, uid="r")]
        h = harvest(ops, [pos("w", 20, 150.0), pos("r", 20, 150.0)], fee=0.0)
        by = {c["uid"]: c for c in h["candidates"]}
        self.assertEqual(by["w"]["ldv"][0]["status"], "close")
        self.assertEqual(by["w"]["ldv"][0]["days"], 20)
        self.assertGreater(by["w"]["ldv"][0]["tax_at_stake"], 0)
        self.assertEqual(by["r"]["ldv"][0]["status"], "reached")

    def test_iis_only_is_excluded(self):
        sel = [{"id": "I", "name": "I", "type": "ИИС", "opened": "2020-01-01T00:00:00Z"}]
        ops = [buy("2024-02-01", 10, 100, uid="l", acc="I")]
        h = harvest(ops, [pos("l", 10, 50.0)], sel=sel)
        self.assertFalse(h["available"])
        self.assertEqual(len(h["iis_excluded"]), 1)

    def test_no_positions_degrades(self):
        h = harvest([buy("2024-02-01", 10, 100, uid="l")], [])
        self.assertFalse(h["available"])
        self.assertTrue(h["reason"])

    def test_deadline(self):
        h = harvest([buy("2024-02-01", 10, 100, uid="l")], [pos("l", 10, 50.0)])
        self.assertEqual(h["deadline"]["sale_day"], M.tx_last_sale_day(2024)[0].isoformat())


class LdvShield(unittest.TestCase):
    G = [buy("2024-01-10", 10, 1000, uid="g"), sell("2024-03-10", 10, 1500, uid="g")]

    def cand(self, bdate, skip=False, extra=None):
        ops = self.G + [buy(bdate, 10, 300, uid="m")] + (extra or [])
        st = M.tax_compute(ops, {}, [pos("m", 10 + (10 if extra else 0), 150.0)], SEL, S0, today=TODAY)
        h = M.txo_harvest_calc(st, S0, 0.0, skip_ldv2=skip)
        return h, (h["candidates"][0] if h["candidates"] else None)

    def test_young_warn_boundary(self):
        c = self.cand("2022-11-03")[1]                 # 729 дней
        self.assertEqual((c["ldv_status"], c["hold_days_max"]), ("young", 729))
        self.assertEqual(c["ldv_badge"], "")
        c = self.cand("2022-11-02")[1]                 # 730 дней
        self.assertEqual((c["ldv_status"], c["hold_days_max"]), ("warn", 730))
        self.assertIn("стаж 1 г. 11 мес.", c["ldv_badge"])
        self.assertIn("сбросит срок владения", c["ldv_badge"])

    def test_critical_boundary(self):
        c = self.cand("2022-05-03")[1]                 # до ЛДВ 183 дня
        self.assertEqual(c["ldv_status"], "warn")
        c = self.cand("2022-05-01")[1]                 # 181 день
        self.assertEqual(c["ldv_status"], "critical")
        self.assertEqual(c["ldv_days_left"], 181)
        self.assertIn("до ЛДВ осталось 181 дн.", c["ldv_badge"])

    def test_reached_and_na(self):
        self.assertEqual(self.cand("2021-01-05")[1]["ldv_status"], "reached")
        ops = self.G + [buy("2022-11-02", 10, 300, uid="m")]
        st = M.tax_compute(ops, {}, [dict(pos("m", 10, 150.0), type="currency")], SEL, S0, today=TODAY)
        h = M.txo_harvest_calc(st, S0, 0.0)
        for c in h["candidates"]:
            self.assertIn(c["ldv_status"], ("n/a", "young", "warn"))

    def test_ldv_cost_for_profitable_warn_lot(self):
        # старый лот @100 (прибыль +500, стаж ≥ 730 дн.) + молодой @300 (убыток); префикс из двух лотов
        ops = self.G + [buy("2022-06-01", 10, 100, uid="m"), buy("2024-02-05", 10, 300, uid="m")]
        st = M.tax_compute(ops, {}, [pos("m", 20, 150.0)], SEL, S0, today=TODAY)
        h = M.txo_harvest_calc(st, S0, 0.0)
        c = h["candidates"][0]
        self.assertAlmostEqual(c["gain_in_prefix"], 500)
        self.assertEqual(c["ldv_status"], "warn")
        self.assertAlmostEqual(c["ldv_cost"], 500 * h["rate_now"], places=6)
        self.assertAlmostEqual(c["net_ldv"], c["net"] - c["ldv_cost"], places=6)
        if c["selected"]:
            self.assertEqual(h["ldv_summary"]["warn"], 1)
            self.assertAlmostEqual(h["ldv_summary"]["ldv_cost"], c["ldv_cost"], places=6)

    def test_loss_warn_lot_has_no_cost(self):
        c = self.cand("2022-11-02")[1]
        self.assertEqual(c["ldv_cost"], 0.0)

    def test_skip_ldv2_excludes_when_oldest_old(self):
        h, c = self.cand("2022-11-02", skip=True)
        self.assertIsNone(c)
        self.assertEqual(len(h["ldv_skipped"]), 1)
        self.assertIn("FIFO", h["ldv_skipped"][0]["reason"])
        self.assertIn("FIFO", h["ldv_note"])
        h, c = self.cand("2022-11-03", skip=True)
        self.assertIsNotNone(c)
        self.assertEqual(h["ldv_skipped"], [])

    def test_endpoint_param(self):
        self.assertIn("skip_ldv2", M.txo_harvest_get.__code__.co_consts + M.txo_harvest_get.__code__.co_names)


class Iis3(unittest.TestCase):
    def test_term_table(self):
        t = M.txo_iis3_term
        self.assertEqual([t(y) for y in (2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2040)], [5, 5, 5, 6, 7, 8, 9, 10, 10])

    def test_refund_caps(self):
        r = M.txo_iis3_calc(2025, 1000000, 10, 6, rate15=False)
        self.assertAlmostEqual(r["rows"][0]["refund"], 52000)
        self.assertAlmostEqual(r["rules"]["max_refund"], 52000)
        r = M.txo_iis3_calc(2025, 1000000, 10, 6, rate15=True)
        self.assertAlmostEqual(r["rows"][0]["refund"], 60000)
        r = M.txo_iis3_calc(2025, 300000, 10, 6, rate15=False)
        self.assertAlmostEqual(r["rows"][0]["refund"], 39000)
        r = M.txo_iis3_calc(2025, 400000, 10, 6, income=3000000)     # доход выше 2,4 млн -> 15 %
        self.assertTrue(r["inputs"]["rate15"])
        self.assertAlmostEqual(r["rows"][0]["refund"], 60000)
        r = M.txo_iis3_calc(2025, 400000, 10, 6, income=200000)      # вычет не больше уплаченного НДФЛ (26 000)
        self.assertAlmostEqual(r["rows"][0]["refund"], 26000)

    def test_term_met_no_tax_and_beats_broker(self):
        r = M.txo_iis3_calc(2025, 400000, 12, 10, rate15=False, coupon_share=1.0)
        self.assertTrue(r["iis"]["term_met"])
        self.assertAlmostEqual(r["iis"]["tax"], 0)
        self.assertGreater(r["advantage"], 0)
        self.assertEqual(len(r["rows"]), 10)

    def test_exempt_cap_30m(self):
        r = M.txo_iis3_calc(2025, 400000, 30, 30, rate15=False)
        self.assertGreater(r["iis"]["capital"] - r["iis"]["deposits"], 30000000)
        self.assertGreater(r["iis"]["tax"], 0)

    def test_early_closure_penalty(self):
        r = M.txo_iis3_calc(2027, 400000, 10, 4, rate15=False)      # срок 6 лет, горизонт 4 года
        self.assertFalse(r["iis"]["term_met"])
        self.assertAlmostEqual(r["iis"]["refunds_returned"], 52000 * 3)
        self.assertGreater(r["iis"]["tax"], 0)
        last = r["early"][-1]
        self.assertAlmostEqual(last["net"], r["iis"]["net"], places=4)
        self.assertAlmostEqual(last["extra_cost"], last["tax"] + last["refunds_returned"])
        self.assertTrue(r["warnings"])

    def test_endpoint(self):
        j = M.txo_iis3_get({}, "", {"open_year": "2025", "contribution": "400000", "yield": "10", "years": "6", "bracket": "15"}, False)
        self.assertEqual(j["rules"]["term"], 5)
        self.assertAlmostEqual(j["rows"][0]["refund"], 60000)
        self.assertIn("/api/txo/iis3", M.API_GET)
        self.assertIn("/api/txo/harvest", M.API_GET)


if __name__ == "__main__":
    unittest.main()
