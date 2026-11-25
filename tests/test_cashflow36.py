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


if __name__ == "__main__":
    unittest.main()
