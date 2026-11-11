"""Доходность облигации по типу оферты: пут -> YTP, колл -> YTW (худшая из YTM и YTC), тип не указан -> к дате и к погашению."""
import unittest

from tests._load import load

T = load()
TODAY = "2026-11-12"
BZ = {"coupons": [{"coupondate": d, "value": 50.0} for d in ("2027-05-12", "2027-11-12", "2028-05-12", "2028-11-12")],
      "amort": [], "offers": []}
YTM_980 = 0.11439819665279177          # зафиксировано: расчёт до появления разбора оферт давал те же числа
YTP_980 = 0.12558425933461875


def of(d, kind, price=100):
    return {"date": d, "kind": kind, "price": price, "status": "scheduled"}


def yk(dirty, offers):
    return T.yields_by_kind(BZ, TODAY, 1000.0, dirty, offers)


class NoOffer(unittest.TestCase):
    def test_pinned_numbers(self):
        r = yk(980.0, [])
        self.assertEqual((r["basis"], r["end"], r["end_kind"], r["to_kind"]), ("maturity", "2028-11-12", "maturity", None))
        self.assertAlmostEqual(r["ytm"], YTM_980, 12)
        self.assertAlmostEqual(r["y"], r["ytw"], 14)
        fl, kind, end = T.bond_flows(BZ, TODAY, 1000.0)
        self.assertEqual((kind, end), ("maturity", "2028-11-12"))
        self.assertEqual(r["flows"], fl)
        self.assertAlmostEqual(T.cf_ytm(980.0, fl, TODAY), YTM_980, 12)


class PutOffer(unittest.TestCase):
    def test_put_is_ytp_and_matches_legacy_cut(self):
        r = yk(980.0, [of("2027-11-12", "put")])
        self.assertEqual((r["basis"], r["to_kind"], r["end"], r["end_kind"]), ("put", "put", "2027-11-12", "offer"))
        self.assertAlmostEqual(r["y"], YTP_980, 12)
        self.assertAlmostEqual(r["ytp"], YTP_980, 12)
        bz = dict(BZ, offers=[{"offerdate": "2027-11-12", "price": 100, "offertype": "Оферта"}])       # прежний путь
        fl, kind, end = T.bond_flows(bz, TODAY, 1000.0)
        self.assertEqual((kind, end, r["flows"]), ("offer", "2027-11-12", fl))
        self.assertAlmostEqual(T.cf_ytm(980.0, fl, TODAY), YTP_980, 12)

    def test_cut_argument_and_cancelled(self):
        fl, kind, end = T.bond_flows(BZ, TODAY, 1000.0, cut=("2027-11-12", 101.0))
        self.assertEqual((kind, end, fl[-1]), ("offer", "2027-11-12", ("2027-11-12", 50.0, 1010.0)))
        self.assertEqual(T.bond_flows(BZ, TODAY, 1000.0, cut=("2029-01-01", 100.0))[1], "maturity")
        c = of("2027-11-12", "put")
        c["status"] = "cancelled"
        self.assertEqual(yk(980.0, [c])["basis"], "maturity")


class CallOffer(unittest.TestCase):
    def test_ytw_picks_lower_call_at_premium(self):
        r = yk(1030.0, [of("2027-11-12", "call")])
        self.assertEqual((r["basis"], r["ytw_kind"], r["ytw_date"], r["to_kind"], r["end"]), ("call", "call", "2027-11-12", "call", "2027-11-12"))
        self.assertAlmostEqual(r["ytc_list"][0][1], 0.06963682746259113, 12)
        self.assertAlmostEqual(r["ytm"], 0.08504250477931241, 12)
        self.assertAlmostEqual(r["y"], r["ytc_list"][0][1], 14)
        self.assertEqual(r["flows"][-1][0], "2027-11-12")           # дюрация/IRR считаются до даты YTW

    def test_ytw_picks_maturity_at_discount(self):
        r = yk(980.0, [of("2027-11-12", "call")])
        self.assertEqual((r["basis"], r["ytw_kind"], r["end_kind"], r["to_kind"], r["end"]), ("call", "maturity", "maturity", None, "2028-11-12"))
        self.assertAlmostEqual(r["y"], YTM_980, 12)
        self.assertAlmostEqual(r["ytc_list"][0][1], YTP_980, 12)     # колл по номиналу на той же дате = тот же срез потоков

    def test_several_calls_take_minimum(self):
        r = yk(1030.0, [of("2027-11-12", "call"), of("2028-05-12", "call")])
        self.assertEqual([d for d, _ in r["ytc_list"]], ["2027-11-12", "2028-05-12"])
        self.assertAlmostEqual(r["ytw"], min(y for _, y in r["ytc_list"] + [("m", r["ytm"])]), 14)


class PutAndCall(unittest.TestCase):
    def test_put_first_means_ytp_basis_with_ytw_alongside(self):
        r = yk(980.0, [of("2027-11-12", "put"), of("2028-05-12", "call")])
        self.assertEqual((r["basis"], r["to_kind"]), ("put", "put"))
        self.assertAlmostEqual(r["y"], YTP_980, 12)
        self.assertAlmostEqual(r["ytw"], YTM_980, 12)
        self.assertEqual(len(r["ytc_list"]), 1)

    def test_call_before_put_is_call_basis(self):
        r = yk(1030.0, [of("2027-05-12", "call"), of("2027-11-12", "put")])
        self.assertEqual(r["basis"], "call")
        self.assertEqual(r["ytw_kind"], "call")


class UnknownOffer(unittest.TestCase):
    def test_unknown_shows_both(self):
        r = yk(980.0, [of("2027-11-12", "unknown")])
        self.assertEqual((r["basis"], r["to_kind"], r["end"]), ("unknown", "unknown", "2027-11-12"))
        self.assertAlmostEqual(r["y"], YTP_980, 12)
        self.assertAlmostEqual(r["yto"], YTP_980, 12)
        self.assertAlmostEqual(r["ytm"], YTM_980, 12)


class LadderCallFlags(unittest.TestCase):
    def test_callable_amount_in_buckets_and_summary(self):
        ev = [{"date": "2028-03-01", "type": "redemption", "amount": 1000.0, "call": "2027-09-01", "call_kind": "call"}]
        items = [{"isin": "A", "name": "A", "ytm": 10.0, "events": ev},
                 {"isin": "B", "name": "B", "ytm": 10.0, "events": [{"date": "2028-06-01", "type": "redemption", "amount": 3000.0}]}]
        ps = T.ld_buckets(items, TODAY, "year")
        p = [x for x in ps if x["key"] == "2028"][0]
        self.assertEqual(p["callable"], 1000.0)
        self.assertEqual(p["items"][0]["call"], "2027-09-01")
        s = T.ld_summary(items, TODAY, ps)
        self.assertEqual((s["callable"]["amount"], s["callable"]["count"]), (1000.0, 1))
        self.assertAlmostEqual(s["callable"]["share"], 25.0)


if __name__ == "__main__":
    unittest.main()
