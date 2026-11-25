"""Спред флоатера (кэш и подпись), лидеры падения в «Сегодня», исполнение амортизации/погашения, тревоги о техдефолте (без сети)."""
import time
import unittest

from tests._load import load

T = load()
URL = "https://e-disclosure.azipi.ru/messages/1/"


class Patch(unittest.TestCase):
    def patch(self, **kw):
        for k, v in kw.items():
            old = getattr(T, k)
            setattr(T, k, v)
            self.addCleanup(setattr, T, k, old)


def bz_float(rate=13.5):
    return {"coupons": [{"coupondate": d, "value": 33.0, "valueprc": rate} for d in
                        ("2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01")], "amort": [], "offers": []}


class FloaterSpread(Patch):
    def setUp(self):
        self.patch(key_rate_series=lambda: [["2025-01-01", 10.0]])

    def test_calc_and_label(self):
        self.assertEqual(T.fl_spread_calc(bz_float(), 1000.0, "2026-11-17"), 3.5)
        self.assertEqual(T.fl_label({"base": "key", "spread": 3.5}), "КС + 3,50%")
        self.assertEqual(T.fl_label({"base": "key", "spread": -0.25}), "КС − 0,25%")
        self.assertEqual(T.fl_label({"base": "ruonia", "spread": None}), "RUONIA")
        self.assertEqual(T.fl_label({"base": "infl"}), "ИНФЛЯЦИЯ")
        self.assertEqual(T.fl_label(None), "ФЛОАТЕР")
        self.assertEqual(T.fl_label({"base": "key", "spread": None}), "ФЛОАТЕР")
        self.assertEqual(T.fl_label(None, floating=False), "ФИКС")

    def test_base_kind(self):
        self.assertEqual(T.fl_base_kind("ОФЗ-ПК 29014", None), "ruonia")
        self.assertEqual(T.fl_base_kind("Эмитент 001Р", "ofz"), "ruonia")
        self.assertEqual(T.fl_base_kind("Эмитент БО-П05", "corp"), "key")

    def test_cache_read_sync(self):
        T.fl_spread_put("RU000FLOAT01", "Эмитент БО-П05", bz_float(), 1000.0, "corp")
        T.fl_spread_put("SU29014RMFS0", "ОФЗ-ПК 29014", None, 1000.0, "ofz")
        self.assertIsNone(T.fl_spread_put("RU000FLOAT02", "Без графика", None, 1000.0, "corp"))
        c = T.fl_spread_cached()
        self.assertEqual(T.fl_label(c["RU000FLOAT01"]), "КС + 3,50%")
        self.assertEqual(T.fl_label(c["SU29014RMFS0"]), "RUONIA")
        self.assertNotIn("RU000FLOAT02", c)
        self.assertEqual(list(T.fl_spread_cached(["RU000FLOAT01"])), ["RU000FLOAT01"])
        T.store().write("UPDATE kv SET t=? WHERE k=?", (time.time() - 31 * 86400, T.FL_SPREAD_KEY + "RU000FLOAT01"))
        self.assertNotIn("RU000FLOAT01", T.fl_spread_cached())          # TTL 30 сут

    def test_kick_only_missing_floaters(self):
        calls = []
        self.patch(fl_spread_job=lambda todo: (calls.append([r["isin"] for r in todo]), T._fl_job.update(running=False)))
        rows = [{"isin": "A1", "floating": True, "cur": "RUB"}, {"isin": "B2", "floating": False, "cur": "RUB"},
                {"isin": "C3", "floating": True, "cur": "RUB"}]
        self.assertTrue(T.fl_spread_kick(rows, {"C3": {}}))
        for t in __import__("threading").enumerate():
            if t.name == "fl-spread":
                t.join(2)
        self.assertEqual(calls, [["A1"]])


class TodayMovers(unittest.TestCase):
    ROWS = [{"name": "А", "isin": "RU1", "chg": -5.0, "turn": 5e6, "price": 90}, {"name": "Б", "isin": "RU2", "chg": -9.0, "turn": 5e5, "price": 50},
            {"name": "В", "isin": "RU3", "chg": -2.0, "turn": 2e6, "price": 99}, {"name": "Г", "id": "RU4", "chg": 3.0, "turn": 9e6, "price": 101}]

    def test_filter_and_order(self):
        m = T.td_movers(self.ROWS)
        self.assertEqual([x["isin"] for x in m["items"]], ["RU1", "RU3"])        # без малого оборота и без роста
        self.assertEqual(m["count"], 2)

    def test_in_payload(self):
        d = T.td_digest([], [], [], [], "2026-11-17", alerts=[], movers=T.td_movers(self.ROWS))
        self.assertFalse(d["empty"])
        self.assertEqual(len(d["movers"]["items"]), 2)
        d2 = T.td_digest([], [], [], [], "2026-11-17", movers=T.td_movers([]))
        self.assertTrue(d2["empty"] and "movers" not in d2)


def pf(published, payment, no=None, pct=None):
    return {"kind": "coupon_paid", "published": published + "T10:00:00", "url": URL,
            "data": {"payment": payment, "coupon_no": no, "paid_pct": pct}}


def dfl(ob, due="2026-11-01", pub="2026-11-05", no=None):
    return {"published": pub + "T09:00:00", "url": URL, "data": {"obligation": ob, "due_date": due, "coupon_no": no, "status": "technical"}}


class Executed(Patch):
    def run_exec(self, ob, facts, **kw):
        self.patch(disc_facts=lambda isin=None, inn=None, kind=None: facts)
        return T._dfl_executed("RU000A0AAAA1", dfl(ob, **kw))

    def test_amortization_and_redemption(self):
        self.assertEqual(self.run_exec("amortization", [pf("2026-11-10", "amortization")]), "2026-11-10")
        self.assertEqual(self.run_exec("amortization", [pf("2026-11-10", "coupon+amortization")]), "2026-11-10")
        self.assertEqual(self.run_exec("redemption", [pf("2026-11-11", "coupon+redemption")]), "2026-11-11")
        self.assertIsNone(self.run_exec("redemption", [pf("2026-11-11", "amortization")]))         # другой вид
        self.assertIsNone(self.run_exec("amortization", [pf("2026-10-20", "amortization")]))        # до срока/сообщения
        self.assertIsNone(self.run_exec("amortization", [pf("2026-11-10", "amortization", pct=40)]))  # частично

    def test_coupon_kept(self):
        self.assertEqual(self.run_exec("coupon", [pf("2026-11-12", "coupon", no=4, pct=100)], no=4), "2026-11-12")
        self.assertIsNone(self.run_exec("coupon", [pf("2026-11-12", "coupon", no=5)], no=4))
        self.assertIsNone(self.run_exec("coupon", [pf("2026-11-12", "coupon", no=4, pct=50)], no=4))
        self.assertIsNone(self.run_exec("other", [pf("2026-11-12", "coupon", no=4)]))


class DefaultAlerts(Patch):
    ROW = {"date": "2026-11-10", "due_date": "2026-11-01", "status": "technical", "issuer": "Эмитент Д", "isin": "RU000A0DDDD4",
           "obligation": "Амортизация", "amount": 1500000.0, "executed": None, "basis": "Сообщение эмитента", "url": URL}

    def test_once_dedup_and_followup(self):
        sent, msgs = {}, []
        self.patch(tg_send=lambda cfg, text: msgs.append(text))
        own = ["RU000A0DDDD4"]
        rows = [self.ROW, dict(self.ROW, isin="RU000A0OTHER9")]            # чужая бумага не попадает
        al = T.defaults_alerts({}, sent, rows=rows, isins=own)
        self.assertEqual([(a["kind"], a["severity"]) for a in al], [("default", "high")])
        self.assertEqual(T._tg_dispatch({}, "t", al, sent, 1000.0), 1)
        self.assertEqual(T._tg_dispatch({}, "t", T.defaults_alerts({}, sent, rows=rows, isins=own), sent, 2000.0), 0)   # повтор не уходит
        self.assertEqual(len(msgs), 1)
        self.assertIn("технический дефолт", msgs[0])
        ex = [dict(self.ROW, executed="2026-11-14")]
        al2 = T.defaults_alerts({}, sent, rows=ex, isins=own)
        self.assertEqual([a["kind"] for a in al2], ["default_ok"])
        self.assertEqual(T._tg_dispatch({}, "t", al2, sent, 3000.0), 1)
        self.assertEqual(T._tg_dispatch({}, "t", T.defaults_alerts({}, sent, rows=ex, isins=own), sent, 4000.0), 0)
        self.assertEqual(len(msgs), 2)
        self.assertIn("исполнен", msgs[1])

    def test_no_followup_if_never_reported(self):
        self.assertEqual(T.defaults_alerts({}, {}, rows=[dict(self.ROW, executed="2026-11-14")], isins=["RU000A0DDDD4"]), [])
        self.assertEqual(T.defaults_alerts({}, {}, rows=[self.ROW], isins=[]), [])


class PortfolioConcentration(Patch):
    def test_empty_and_futures_only(self):
        c = T.portfolio_concentration([])
        self.assertEqual(c["total"], 0.0)
        self.assertEqual(c["warnings"], [])
        c2 = T.portfolio_concentration([{"type": "futures", "value_rub": 50000.0, "cur": "rub"}])
        self.assertEqual(c2["total"], 0.0)

    def test_issuers_sectors_currencies_ratings_and_warnings(self):
        self.patch(tcat_info=lambda isin: None, best_rating=lambda isin, name: None)
        rows = [
            {"type": "bond", "uid": "u1", "isin": "SU26238RMFS4", "name": "ОФЗ 26238", "sector": "gov",
             "cur": "rub", "value_rub": 20000.0, "rating": {"v": "AAA"}},
            {"type": "bond", "uid": "u2", "isin": "SU26240RMFS0", "name": "ОФЗ 26240", "sector": "gov",
             "cur": "rub", "value_rub": 10000.0, "rating": {"v": "AAA"}},
            {"type": "bond", "uid": "u3", "isin": "RU000A100001", "name": "Альфа БО-П01", "sector": "financial",
             "cur": "usd", "value_rub": 40000.0, "rating": {"v": "BBB+"}},
            {"type": "bond", "uid": "u4", "isin": "RU000A100002", "name": "Бета БО-01", "sector": "financial",
             "cur": "rub", "value_rub": 15000.0, "rating": None},
            {"type": "bond", "uid": "u5", "isin": "RU000A100003", "name": "Гамма БО-01", "sector": "energy",
             "cur": "rub", "value_rub": 5000.0, "rating": {"v": "A-"}},
            {"type": "currency", "uid": "cash:rub", "ticker": "RUB", "name": "Рубли", "cur": "rub", "value_rub": 10000.0},
        ]
        c = T.portfolio_concentration(rows)
        self.assertAlmostEqual(c["total"], 100000.0)
        self.assertEqual(c["issuers_count"], 4)
        self.assertAlmostEqual(c["max_issuer_share"], 40.0)
        # top-3: Альфа (40%) + Минфин (30%) + Бета (15%) = 85%
        self.assertAlmostEqual(c["top3_share"], 85.0)
        self.assertEqual(c["issuers"][0]["share"], 40.0)
        self.assertEqual(c["issuers"][1]["key"], "минфин")
        self.assertAlmostEqual(c["issuers"][1]["share"], 30.0)
        # sectors: financial = 55%, gov = 30%, energy = 5%
        sec_map = {s["key"]: s["share"] for s in c["sectors"]}
        self.assertAlmostEqual(sec_map["financial"], 55.0)
        self.assertAlmostEqual(sec_map["gov"], 30.0)
        # currencies: rub = 60%, usd = 40%
        cur_map = {x["cur"]: x["share"] for x in c["currencies"]}
        self.assertAlmostEqual(cur_map["rub"], 60.0)
        self.assertAlmostEqual(cur_map["usd"], 40.0)
        # ratings: BBB+ (40%) is below A-; A- (5%) is not; Бета (15%) is unrated bond
        self.assertAlmostEqual(c["below_a_minus"]["share"], 40.0)
        self.assertEqual(c["below_a_minus"]["count"], 1)
        self.assertAlmostEqual(c["unrated_bonds"]["share"], 15.0)
        self.assertEqual(c["unrated_bonds"]["count"], 1)
        # all 3 warnings triggered: issuer 40%>15%, sector 55%>35%, rating 40%>30%
        self.assertEqual({w["kind"] for w in c["warnings"]}, {"issuer", "sector", "rating"})

    def test_no_warnings_when_diversified(self):
        self.patch(tcat_info=lambda isin: None, best_rating=lambda isin, name: None)
        names = ["Газпром", "Лукойл", "Сбербанк", "Яндекс", "Магнит", "Новатэк", "Полюс", "Роснефть", "Татнефть", "МТС"]
        rows = [
            {"type": "share", "uid": f"s{i}", "name": nm, "sector": f"sec{i % 4}",
             "cur": "rub", "value_rub": 10000.0}
            for i, nm in enumerate(names)
        ]
        c = T.portfolio_concentration(rows)
        self.assertAlmostEqual(c["max_issuer_share"], 10.0)
        self.assertEqual(c["warnings"], [])


if __name__ == "__main__":
    unittest.main()
