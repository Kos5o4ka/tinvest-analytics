"""Матрица потоков на 36 месяцев и симулятор реинвестирования. Офлайн: сеть подменена."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


class Simulate(unittest.TestCase):
    def test_known_numbers(self):
        r = M.cf36_simulate([1000.0] * 36, 12.0)
        self.assertAlmostEqual(r["capital"][2], 1000 * 1.01 ** 2 + 1000 * 1.01 + 1000, places=6)
        self.assertAlmostEqual(r["capital"][2], 3030.10, places=2)
        self.assertEqual(r["capital_no"][2], 3000.0)
        self.assertAlmostEqual(r["diff"], r["final"] - 36000.0)
        self.assertAlmostEqual(r["interest"], r["diff"])
        self.assertGreater(r["interest"], 0)

    def test_no_reinvest_and_start(self):
        r = M.cf36_simulate([{"total": 100.0}, {"total": 0.0}, {"total": 50.0}], 20.0, start=1000.0, reinvest=False)
        self.assertEqual(r["capital"], [1100.0, 1100.0, 1150.0])
        self.assertEqual(r["interest"], 0.0)
        r2 = M.cf36_simulate([0, 0], 12.0, start=100.0)
        self.assertAlmostEqual(r2["final"], 100 * 1.01 ** 2)


class Bucket(unittest.TestCase):
    def test_36_months_with_empty(self):
        today = date(2026, 11, 22)
        keys = M.cf36_month_keys(today)
        self.assertEqual((len(keys), keys[0], keys[1], keys[-1]), (36, "2026-11", "2026-12", "2029-10"))
        pays = [{"date": "2026-12-10", "kind": "coupon", "amount": 100.0, "est": False, "name": "A"},
                {"date": "2026-12-20", "kind": "dividend", "amount": 50.0, "est": True, "name": "B"},
                {"date": "2029-10-31", "kind": "redemption", "amount": 1000.0, "est": False, "name": "A"},
                {"date": "2029-11-01", "kind": "coupon", "amount": 5.0, "est": False, "name": "A"}]     # за окном
        m = M.cf36_bucket(pays, today)
        self.assertEqual(len(m), 36)
        self.assertEqual(m[0]["total"], 0.0)
        self.assertEqual(m[1]["total"], 150.0)
        self.assertEqual(m[1]["est"], 50.0)
        self.assertEqual(m[1]["by"]["dividend"], 50.0)
        self.assertEqual(m[-1]["by"]["redemption"], 1000.0)
        self.assertEqual(sum(1 for x in m if x["total"] <= 0), 34)
        self.assertEqual(m[1]["top"][0]["name"], "A")

    def test_horizon(self):
        self.assertEqual(M.cf36_horizon_days(date(2026, 11, 22)), (date(2029, 11, 1) - date(2026, 11, 22)).days - 1)


class Report(unittest.TestCase):
    def _run(self, **kw):
        today = date.today()
        d = lambda n: (today + timedelta(days=n)).isoformat()
        b = {"nominal": 1000.0, "cur": "rub", "maturity": d(900), "call": None, "placement": d(-400), "cpy": 2, "aci": 5.0,
             "floating": False, "amort": False, "perpetual": False, "risk": "", "sector": "", "name": "T",
             "coupons": [[d(30), 40.0], [d(400), None], [d(700), None]]}
        saved = {k: getattr(M, k) for k in ("bond_info", "fx_now", "bond_exact", "keyrate_brief", "apply_ratings", "ratings_status")}
        M.bond_info = lambda c, u: dict(b)
        M.fx_now = lambda c, cs: {"rub": 1.0}
        M.bond_exact = lambda *a: None
        M.keyrate_brief = lambda: None
        M.apply_ratings = lambda rows: []
        M.ratings_status = lambda: {}
        row = {"uid": "u1", "ticker": "T1", "name": "Тест", "logo": "", "color": "", "type": "bond", "qty": 10.0, "avg": 990.0,
               "price": 995.0, "cur": "rub", "value": 10000.0, "value_rub": 10000.0, "pnl_rub": 0.0, "pnl_pct": 0.0}
        try:
            return M.bonds_report(object(), [row], **kw), d
        finally:
            for k, v in saved.items():
                setattr(M, k, v)

    def test_horizon_default_and_long(self):
        rep, d = self._run()
        self.assertEqual([p["kind"] for p in rep["payments"]], ["coupon"])          # 365 дней: только первый купон
        rep, d = self._run(horizon_days=1096)
        pays = rep["payments"]
        cps = [p for p in pays if p["kind"] == "coupon"]
        self.assertEqual([(p["date"], p["est"], p["amount"]) for p in cps],
                         [(d(30), False, 400.0), (d(400), True, 400.0), (d(700), True, 400.0)])    # None -> последний известный, est
        self.assertEqual(pays[-1]["kind"], "redemption")

    def test_payload_offline(self):
        today = date.today()
        names = ("build_summary", "bonds_report", "stock_dividends", "cf36_rates", "TInvest")
        saved = {k: getattr(M, k) for k in names}
        pos = [{"type": "share", "uid": "s1", "ticker": "SBER", "name": "Сбер", "qty": 100.0}]
        M.build_summary = lambda cfg, acc, per: {"portfolio": {"positions": pos}}
        M.bonds_report = lambda c, rows, horizon_days=365: {"payments": [
            {"date": (today + timedelta(days=5)).isoformat(), "kind": "coupon", "name": "X", "ticker": "X", "amount": 70.0, "est": False}]}
        M.TInvest = lambda cfg: object()
        rec = (today - timedelta(days=100))
        M.stock_dividends = lambda secid, price, uid=None, cfg=None, **kw: {"items": [
            {"record": rec.isoformat(), "payment": rec.isoformat(), "value": 30.0, "cur": "RUB"}]}
        M.cf36_rates = lambda: {"lqdt": 13.0, "ofz1y": 14.0}
        try:
            r = M.cashflow36_payload({"token": "t", "sandbox": False}, "all", True)
        finally:
            for k, v in saved.items():
                setattr(M, k, v)
        self.assertEqual(len(r["months"]), 36)
        self.assertGreaterEqual(r["est_dividends"], 2)
        self.assertAlmostEqual(r["est_total"], r["est_dividends"] * 30.0 * 100 * 0.87, places=2)
        est = [m for m in r["months"] if m["est"] > 0]
        self.assertTrue(all(abs(m["est"] - 2610.0) < 0.01 for m in est))
        self.assertEqual(len(r["empty_months"]), sum(1 for m in r["months"] if m["total"] <= 0))
        self.assertEqual(r["rates"]["lqdt"], 13.0)

    def test_dividend_failure_silent(self):
        saved = M.stock_dividends
        def boom(*a, **k):
            raise RuntimeError("net")
        M.stock_dividends = boom
        try:
            self.assertEqual(M.cf36_est_dividends([{"ticker": "X", "uid": "u", "qty": 1.0}], [], {}), [])
        finally:
            M.stock_dividends = saved


class PayJournal(unittest.TestCase):
    def test_build_pay_journal_fifo_yoc_and_fx(self):
        today = date(2026, 11, 25)
        d_old = "2024-06-15T10:00:00Z"
        d_buy = "2025-01-10T10:00:00Z"
        d_rec1 = "2026-06-15T10:00:00Z"
        d_rec2 = "2026-10-20T10:00:00Z"
        ops = [
            {"id": "1", "date": d_buy, "type": "OPERATION_TYPE_BUY", "instrumentUid": "b1",
             "quantityDone": 10, "payment": {"currency": "rub", "units": -10000, "nano": 0}},
            {"id": "2", "date": d_old, "type": "OPERATION_TYPE_COUPON", "instrumentUid": "b1",
             "payment": {"currency": "rub", "units": 500, "nano": 0}},
            {"id": "3", "date": d_rec1, "type": "OPERATION_TYPE_COUPON", "instrumentUid": "b1",
             "payment": {"currency": "rub", "units": 1200, "nano": 0}},
            {"id": "4", "date": d_buy, "type": "OPERATION_TYPE_BUY", "instrumentUid": "s1",
             "quantityDone": 5, "payment": {"currency": "usd", "units": -100, "nano": 0}},
            {"id": "5", "date": d_rec2, "type": "OPERATION_TYPE_DIVIDEND", "instrumentUid": "s1",
             "payment": {"currency": "usd", "units": 10, "nano": 0}},
        ]
        names = {
            "b1": {"uid": "b1", "name": "ОФЗ 26238", "ticker": "SU26238RMFS4", "type": "bond", "cur": "rub"},
            "s1": {"uid": "s1", "name": "Тест USD", "ticker": "TUSD", "type": "share", "cur": "usd"},
        }
        saved = M.tax_cbr_rate
        M.tax_cbr_rate = lambda cur, iso: 90.0 if (cur or "").lower() == "usd" else 1.0
        try:
            res = M.build_pay_journal(ops, names, today=today)
        finally:
            M.tax_cbr_rate = saved

        self.assertTrue(res["ok"])
        # b1: 500 + 1200 = 1700 RUB; s1: 10 * 90 = 900 RUB => 2600 RUB
        self.assertAlmostEqual(res["coupons_rub"], 1700.0, places=2)
        self.assertAlmostEqual(res["dividends_rub"], 900.0, places=2)
        self.assertAlmostEqual(res["total_rub"], 2600.0, places=2)
        self.assertAlmostEqual(res["total_12m_rub"], 2100.0, places=2)
        # FIFO cost: b1 = 10000 RUB, s1 = 100 * 90 = 9000 RUB => 19000 RUB
        self.assertAlmostEqual(res["cost_rub"], 19000.0, places=2)
        self.assertAlmostEqual(res["portfolio_yoc_pct"], round(2100.0 / 19000.0 * 100.0, 2), places=2)
        secs = {s["uid"]: s for s in res["securities"]}
        self.assertAlmostEqual(secs["b1"]["yoc_pct"], 12.0, places=2)
        self.assertAlmostEqual(secs["b1"]["yoc_total_pct"], 17.0, places=2)
        self.assertAlmostEqual(secs["s1"]["yoc_pct"], 10.0, places=2)
        self.assertEqual([y["year"] for y in res["years"]], ["2024", "2026"])
        self.assertEqual(len(res["months"]), 3)

    def test_pay_journal_payload_offline(self):
        names_to_save = ("selection", "instruments", "TInvest", "tax_cbr_rate")
        saved = {k: getattr(M, k) for k in names_to_save}
        ops = [
            {"id": "b1", "date": "2026-01-15T10:00:00Z", "type": "OPERATION_TYPE_BUY", "instrumentUid": "u1",
             "quantityDone": 2, "payment": {"currency": "rub", "units": -2000, "nano": 0}},
            {"id": "c1", "date": date.today().isoformat() + "T10:00:00Z", "type": "OPERATION_TYPE_COUPON",
             "instrumentUid": "u1", "payment": {"currency": "rub", "units": 200, "nano": 0}},
        ]
        M.selection = lambda cfg, acc, force=False: ([], [], [{"port": None, "ops": ops}])
        M.instruments = lambda client, keys: {"u1": {"uid": "u1", "name": "Бонд 1", "ticker": "B1", "type": "bond"}}
        M.TInvest = lambda cfg: object()
        M.tax_cbr_rate = lambda cur, iso: 1.0
        try:
            res = M.pay_journal_payload({"token": "t", "sandbox": False}, "all", True)
        finally:
            for k, v in saved.items():
                setattr(M, k, v)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(res["coupons_rub"], 200.0, places=2)
        self.assertAlmostEqual(res["securities"][0]["yoc_pct"], 10.0, places=2)


class OfferReinvest(unittest.TestCase):
    def test_keyrate_trajectories(self):
        tr = M.cf36_keyrate_trajectories(18.0, n=36)
        self.assertEqual(tr["base"], 18.0)
        self.assertFalse(tr["fallback"])
        self.assertEqual(len(tr["items"]["flat"]["rates"]), 36)
        self.assertEqual(tr["items"]["flat"]["rates"][0], 18.0)
        self.assertEqual(tr["items"]["cut"]["rates"][0], 18.0)
        self.assertEqual(tr["items"]["cut"]["rates"][-1], 12.0)
        self.assertEqual(tr["items"]["hike"]["rates"][0], 18.0)
        self.assertEqual(tr["items"]["hike"]["rates"][-1], 22.0)

    def test_offer_events_offline(self):
        today = date(2026, 11, 25)
        rep_bonds = [{
            "uid": "u_put", "isin": "RU000A100001", "ticker": "BPUT", "name": "Бонд Пут",
            "qty": 10.0, "nominal": 1000.0, "face_cur": "rub", "maturity": "2029-05-01",
            "put_date": "2027-06-01", "call_dates": ["2028-06-01"],
        }]
        saved = (M.moex_bondization, M.moex_bond_options)
        M.moex_bondization = lambda isin: {"ok": True, "amort": [{"amortdate": "2027-03-01", "value": 200.0}], "offers": []}
        M.moex_bond_options = lambda isin: {"ok": True, "put": ["2027-06-01"], "call": ["2028-06-01"], "prices": {"2027-06-01": 100.0}}
        try:
            ofs = M.cf36_offer_events(rep_bonds, {"rub": 1.0}, today=today)
        finally:
            M.moex_bondization, M.moex_bond_options = saved
        self.assertEqual(len(ofs), 2)
        self.assertEqual(ofs[0]["kind"], "offer_put")
        self.assertEqual(ofs[0]["ym"], "2027-06")
        # 1000 - 200 amort = 800 * 10 = 8000
        self.assertAlmostEqual(ofs[0]["amount"], 8000.0, places=2)
        self.assertEqual(ofs[0]["maturity_ym"], "2029-05")
        self.assertEqual(ofs[1]["kind"], "offer_call")

    def test_simulate_offers_no_double_count_and_seq(self):
        today = date(2026, 11, 25)
        keys = M.cf36_month_keys(today)
        months = [{"ym": k, "total": 100.0, "by": {"coupon": 100.0, "redemption": 0.0}} for k in keys]
        # Погашение на последнем месяце 10000
        months[-1]["total"] += 10000.0
        months[-1]["by"]["redemption"] = 10000.0
        offers = [{
            "uid": "u1", "isin": "RU1", "name": "B1", "date": keys[5] + "-15", "ym": keys[5],
            "kind": "offer_put", "amount": 10000.0, "maturity_ym": keys[-1], "maturity_amount": 10000.0,
        }]
        tr = M.cf36_keyrate_trajectories(12.0, n=36)
        sim_put = M.cf36_simulate_offers(months, tr["items"]["flat"]["rates"], offers=offers, offer_kinds=("offer_put",))
        sim_mat = M.cf36_simulate_offers(months, tr["items"]["flat"]["rates"], offers=offers, offer_kinds=())
        # Без двойного счёта: сумма без реинвеста одинакова (36*100 + 10000 = 13600)
        self.assertAlmostEqual(sim_put["final_no"], 13600.0, places=2)
        self.assertAlmostEqual(sim_mat["final_no"], 13600.0, places=2)
        # При ранней пут-оферте доход от реинвеста выше
        self.assertGreater(sim_put["final"], sim_mat["final"])
        self.assertEqual(sim_put["offer_count"], 1)
        # При росте ставки итоговый капитал выше, чем при снижении
        sim_cut = M.cf36_simulate_offers(months, tr["items"]["cut"]["rates"], offers=offers, offer_kinds=("offer_put",))
        sim_hike = M.cf36_simulate_offers(months, tr["items"]["hike"]["rates"], offers=offers, offer_kinds=("offer_put",))
        self.assertGreater(sim_hike["final"], sim_cut["final"])

    def test_simulate_offers_removes_post_flows_and_zero_redemption(self):
        today = date(2026, 11, 25)
        keys = M.cf36_month_keys(today)
        months = [{"ym": k, "total": 100.0, "by": {"coupon": 100.0, "amortization": 0.0, "redemption": 0.0}} for k in keys]
        months[7]["total"] += 500.0
        months[7]["by"]["amortization"] = 500.0
        # В месяце погашения redemption == 0.0 (только купон 100): red == 0.0 не должен сбрасываться на total!
        offers = [{
            "uid": "u1", "isin": "RU1", "name": "B1", "date": keys[5] + "-15", "ym": keys[5],
            "kind": "offer_put", "amount": 10000.0, "maturity_ym": keys[-1], "maturity_amount": 10000.0,
            "post_coupons": {keys[6]: 100.0, keys[7]: 100.0},
            "post_amorts": {keys[7]: 500.0},
        }]
        sim = M.cf36_simulate_offers(months, 0.0, offers=offers, offer_kinds=("offer_put",))
        # Было 36*100 + 500 = 4100; добавлена оферта +10000, сняты 2 купона (-200) и амортизация (-500),
        # а в последнем месяце redemption == 0.0 => купон 100 не вычитается! Итого 4100 + 10000 - 700 = 13400.
        self.assertAlmostEqual(sim["final_no"], 13400.0, places=2)
        self.assertEqual(sim["maturity_shifted"], 0.0)

    def test_cashflow36_payload_reads_rep_rows_for_offers(self):
        today = date.today()
        put_d = (today + timedelta(days=90)).isoformat()
        mat_d = (today + timedelta(days=400)).isoformat()
        names = ("build_summary", "bonds_report", "stock_dividends", "cf36_rates", "TInvest",
                 "moex_bondization", "moex_bond_options")
        saved = {k: getattr(M, k) for k in names}
        M.build_summary = lambda cfg, acc, per: {"portfolio": {"positions": []}}
        M.bonds_report = lambda c, rows, horizon_days=365: {
            "rows": [{"uid": "u1", "isin": "RU000TEST001", "ticker": "T1", "name": "Тест",
                      "qty": 5.0, "nominal": 1000.0, "face_cur": "rub", "maturity": mat_d, "put_date": put_d}],
            "payments": [{"date": put_d, "kind": "coupon", "name": "Тест", "ticker": "T1", "amount": 50.0, "est": False},
                         {"date": mat_d, "kind": "coupon", "name": "Тест", "ticker": "T1", "amount": 50.0, "est": False}],
        }
        M.TInvest = lambda cfg: object()
        M.stock_dividends = lambda *a, **k: {"items": []}
        M.cf36_rates = lambda: {"lqdt": 13.0, "ofz1y": 14.0}
        M.moex_bondization = lambda isin: None
        M.moex_bond_options = lambda isin: None
        try:
            r = M.cashflow36_payload({"token": "t", "sandbox": False}, "all", True)
        finally:
            for k, v in saved.items():
                setattr(M, k, v)
        self.assertEqual(r["offer_summary"]["put_count"], 1)
        self.assertEqual(r["offers"][0]["post_coupons"], {mat_d[:7]: 50.0})


class PayJournalRegressions(unittest.TestCase):
    def test_sur_sec_in_negative_net_and_conversions(self):
        today = date(2026, 11, 25)
        ops = [
            # Конвертация старой ГДР в новую акцию перед FIFO
            {"id": "1", "date": "2024-01-10T10:00:00Z", "type": "OPERATION_TYPE_BUY", "instrumentUid": "old_gdr",
             "quantityDone": 10, "payment": {"currency": "sur", "units": -1000, "nano": 0}},
            {"id": "2", "date": "2025-02-01T10:00:00Z", "type": "OPERATION_TYPE_INPUT_SECURITIES", "instrumentUid": "new_sh",
             "quantityDone": 10, "payment": {"currency": "rub", "units": 0, "nano": 0}},
            {"id": "3", "date": "2026-06-01T10:00:00Z", "type": "OPERATION_TYPE_DIVIDEND", "instrumentUid": "new_sh",
             "payment": {"currency": "sur", "units": 100, "nano": 0}},
            # Бумага с sec_in в USD (payment cur="rub", но инструмент USD)
            {"id": "4", "date": "2025-03-01T10:00:00Z", "type": "OPERATION_TYPE_INPUT_SECURITIES", "instrumentUid": "usd_b",
             "quantityDone": 2, "payment": {"currency": "rub", "units": -100, "nano": 0}},
            # Бумага с отрицательным нетто (выплата < 0, но count > 0)
            {"id": "5", "date": "2026-07-01T10:00:00Z", "type": "OPERATION_TYPE_COUPON", "instrumentUid": "neg_b",
             "payment": {"currency": "rub", "units": -50, "nano": 0}},
        ]
        names = {
            "old_gdr": {"uid": "old_gdr", "name": "TCSG GDR", "ticker": "TCSG", "type": "share", "cur": "rub"},
            "new_sh": {"uid": "new_sh", "name": "Т-Технологии", "ticker": "T", "type": "share", "cur": "rub"},
            "usd_b": {"uid": "usd_b", "name": "USD Bond", "ticker": "USDB", "type": "bond", "cur": "usd"},
            "neg_b": {"uid": "neg_b", "name": "Neg Bond", "ticker": "NEGB", "type": "bond", "cur": "rub"},
        }
        saved = (M.tax_cbr_rate, M.find_conversions, M.apply_conversions)
        M.tax_cbr_rate = lambda cur, iso: 90.0 if (cur or "").lower() == "usd" else 1.0
        M.find_conversions = lambda o, n, h=None, resolve=None: [{"old_uid": "old_gdr", "new_uid": "new_sh", "ratio": 1.0}]
        M.apply_conversions = lambda o, ev: [
            {"id": "conv_b", "date": "2024-01-10T10:00:00Z", "type": "OPERATION_TYPE_BUY", "instrumentUid": "new_sh",
             "quantityDone": 10, "payment": {"currency": "sur", "units": -1000, "nano": 0}},
            *[x for x in o if x["id"] not in ("1", "2")],
        ]
        try:
            res = M.build_pay_journal(ops, names, today=today)
        finally:
            M.tax_cbr_rate, M.find_conversions, M.apply_conversions = saved
        secs = {s["uid"]: s for s in res["securities"]}
        self.assertIn("new_sh", secs)
        self.assertAlmostEqual(secs["new_sh"]["cost_rub"], 1000.0, places=2)
        self.assertAlmostEqual(secs["new_sh"]["yoc_pct"], 10.0, places=2)
        # USD sec_in: 100 USD * 90 = 9000 RUB (не 100 RUB!)
        self.assertAlmostEqual(secs["usd_b"]["cost_rub"], 9000.0, places=2)
        # Отрицательное нетто сохраняется, т.к. есть выплата (count > 0)
        self.assertIn("neg_b", secs)
        self.assertEqual(secs["neg_b"]["count"], 1)
        self.assertFalse(any("SUR" in n for n in res["notes"]))

    def test_pay_journal_payload_per_account_fifo(self):
        names_to_save = ("selection", "instruments", "TInvest", "tax_cbr_rate", "find_conversions")
        saved = {k: getattr(M, k) for k in names_to_save}
        # Счёт A: покупка 10 шт по 100 = 1000; Счёт B: продажа 5 шт без покупки (короткая/чужая),
        # при общем FIFO продажа на B съела бы 5 шт со счёта A! При per-account FIFO на A остаётся 10 шт = 1000.
        ops_a = [
            {"id": "a1", "date": "2026-01-10T10:00:00Z", "type": "OPERATION_TYPE_BUY", "instrumentUid": "u1",
             "quantityDone": 10, "payment": {"currency": "rub", "units": -1000, "nano": 0}},
            {"id": "a2", "date": date.today().isoformat() + "T10:00:00Z", "type": "OPERATION_TYPE_COUPON",
             "instrumentUid": "u1", "payment": {"currency": "rub", "units": 100, "nano": 0}},
        ]
        ops_b = [
            {"id": "b1", "date": "2026-02-10T10:00:00Z", "type": "OPERATION_TYPE_SELL", "instrumentUid": "u1",
             "quantityDone": 5, "payment": {"currency": "rub", "units": 500, "nano": 0}},
        ]
        M.selection = lambda cfg, acc, force=False: ([], [], [{"port": None, "ops": ops_a}, {"port": None, "ops": ops_b}])
        M.instruments = lambda client, keys: {"u1": {"uid": "u1", "name": "Бонд 1", "ticker": "B1", "type": "bond"}}
        M.TInvest = lambda cfg: object()
        M.tax_cbr_rate = lambda cur, iso: 1.0
        M.find_conversions = lambda *a, **k: []
        try:
            res = M.pay_journal_payload({"token": "t", "sandbox": False}, "all", True)
        finally:
            for k, v in saved.items():
                setattr(M, k, v)
        self.assertAlmostEqual(res["cost_rub"], 1000.0, places=2)


if __name__ == "__main__":
    unittest.main()
