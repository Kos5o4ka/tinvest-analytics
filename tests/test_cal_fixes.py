"""Календарь без токена (купоны с Мосбиржи), котировки Мосбиржи в валюте, очистка кэша kv (без сети)."""
import json
import time
import unittest
from datetime import date, timedelta

from tests._load import load

M = load()


class patched:
    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = getattr(M, k, None)
            setattr(M, k, v)

    def __exit__(self, *a):
        for k, v in self.old.items():
            setattr(M, k, v)


class NoTokenCoupons(unittest.TestCase):
    """Импорт/демо без токена: у bond_info нет графика купонов — выплаты берутся из bondization Мосбиржи."""

    def test_moex_schedule_fills_payments(self):
        d1 = (date.today() + timedelta(days=20)).isoformat()
        d2 = (date.today() + timedelta(days=200)).isoformat()
        d0 = (date.today() - timedelta(days=160)).isoformat()
        bz = {"ok": True, "coupons": [{"coupondate": d0, "value": 35.4}, {"coupondate": d1, "value": 35.4},
                                      {"coupondate": d2, "value": None}], "amort": [], "offers": []}
        b = {"nominal": 1000.0, "initial": 1000.0, "cur": "rub", "maturity": "2041-05-15", "call": None, "placement": None,
             "cpy": 2, "aci": 0.0, "floating": False, "amort": False, "perpetual": False, "risk": "", "sector": "", "name": "ОФЗ 26238"}

        class C:
            ready = False
        row = {"uid": "imp:RU000A1038V6", "ticker": "SU26238RMFS4", "name": "ОФЗ 26238", "logo": "", "color": "", "type": "bond",
               "qty": 10.0, "avg": 600.0, "price": 600.0, "cur": "rub", "value": 6000.0, "value_rub": 6000.0, "pnl_rub": 0.0, "pnl_pct": 0.0}
        with patched(bond_info=lambda c, u: dict(b, coupons=[]), moex_bondization=lambda i: bz, bond_exact=lambda *a: None,
                     fx_now=lambda c, cs: {"rub": 1.0}, keyrate_brief=lambda: None, apply_ratings=lambda rows: [],
                     ratings_status=lambda: {}, bond_isin=lambda r: "RU000A1038V6"):
            rep = M.bonds_report(C(), [row])
        cp = [(p["date"], round(p["amount"], 2), p["est"]) for p in rep["payments"] if p["kind"] == "coupon"]
        self.assertEqual(cp, [(d1, 354.0, False), (d2, 354.0, True)])     # будущий купон без размера — оценка по последнему
        self.assertEqual(M.moex_coupon_schedule("X"), [])                    # без патча: неверный ISIN -> пусто, без исключения


class MoexFxQuotes(unittest.TestCase):
    """Облигации в юанях/долларах (TQOY/TQOD) и замещающие (TQCB: торги в рублях, номинал в USD) — в рубли по курсу ЦБ."""
    ROWS = {"RU000A105AA1": ("CNYB", "TQOY", "CNY", "CNY", 98.5, 1000, 12.0),
            "RU000A105BB2": ("USDB", "TQOD", "USD", "USD", 101.0, 1000, 5.0),
            "RU000A105CC3": ("ZAMB", "TQCB", "SUR", "USD", 90.0, 100, 1.5),
            "RU000A105DD4": ("NOFX", "TQOY", "CNY", "XXX", 90.0, 1000, 1.0)}

    def http(self, calls):
        def h(url, timeout=25):
            calls.append(url)
            for isin, (sec, board, cid, fu, px, face, aci) in self.ROWS.items():
                if "securities.json" in url and isin in url:
                    return json.dumps({"securities": {"columns": ["secid", "isin", "primary_boardid", "group", "is_traded"],
                                                      "data": [[sec, isin, board, "stock_bonds", 1]]}})
                if "/boards/%s/securities/%s.json" % (board, sec) in url:
                    return json.dumps({"securities": {"columns": ["SECID", "PREVPRICE", "FACEVALUE", "ACCRUEDINT", "CURRENCYID", "FACEUNIT"],
                                                      "data": [[sec, px, face, aci, cid, fu]]},
                                       "marketdata": {"columns": ["SECID", "LAST"], "data": [[sec, None]]}})
            raise OSError("unexpected " + url)
        return h

    def test_convert(self):
        rates = {"CNY": 11.0, "USD": 80.0}
        M.store().delete_prefix("mq")
        with patched(http_text=self.http([]), tax_cbr_rate=lambda c, d: rates.get(c)):
            q = M.moex_quotes(list(self.ROWS))
        c = q["RU000A105AA1"]
        self.assertAlmostEqual(c["price"], 985.0 * 11.0)
        self.assertAlmostEqual(c["nkd"], 12.0 * 11.0)
        self.assertEqual((c["cur"], c["fx"]), ("CNY", 11.0))
        self.assertAlmostEqual(q["RU000A105BB2"]["price"], 1010.0 * 80.0)
        z = q["RU000A105CC3"]                       # замещающая: номинал 100 USD, цена 90% -> 90 USD -> 7200 ₽
        self.assertAlmostEqual(z["price"], 7200.0)
        self.assertAlmostEqual(z["nkd"], 120.0)
        self.assertNotIn("RU000A105DD4", q)          # нет курса — нет котировки

    def test_rub_unchanged(self):
        sec = {"FACEVALUE": 1000, "ACCRUEDINT": 7.0, "CURRENCYID": "SUR", "FACEUNIT": "SUR"}
        r = M._mq_quote({"secid": "X", "type": "bond", "isin": "I"}, sec, 99.0)
        self.assertEqual((r["price"], r["nkd"]), (990.0, 7.0))
        self.assertNotIn("cur", r)

    def test_imported_position_in_cny(self):
        """Позиция импорта в юанях: цена Мосбиржи в рублях переводится обратно в валюту позиции, value_rub — по курсу."""
        q = {"RU000A105AA1": {"ok": True, "type": "bond", "price": 985.0 * 11.0, "nkd": 132.0, "secid": "CNYB", "isin": "RU000A105AA1"}}

        class C:
            ready = False
        names = {"imp:RU000A105AA1": {"name": "Юаневая", "ticker": "CNYB", "type": "bond", "cur": "cny"}}
        with patched(moex_quotes=lambda ids: q, fx_now=lambda c, cs: {"rub": 1.0, "cny": 11.0},
                     fifo=lambda o: {"imp:RU000A105AA1": {"qty": 2.0, "cost": 1900.0, "last_unit": 950.0}}):
            rows = M.imported_positions(C(), [], names)
        r = [x for x in rows if x["uid"] == "imp:RU000A105AA1"][0]
        self.assertAlmostEqual(r["price"], 985.0)
        self.assertAlmostEqual(r["value_rub"], 2 * (985.0 + 12.0) * 11.0)


class KvGc(unittest.TestCase):
    def test_only_allowlisted_old_cache_deleted(self):
        import os
        import tempfile
        st = M.Store(os.path.join(tempfile.mkdtemp(prefix="kvgc_"), "data.db"))
        now = time.time()
        old, fresh = now - 90 * M.DAY, now - 3600
        rows = {"stk_c_v1_SBER_24_400_2026-08-01": old, "stk_c_v1_SBER_24_400_2026-11-24": fresh,
                "mqquote:SBER": old, "bondiz2:RU000A1038V6": old, "bondiz2:RU000A106E90": fresh, "res:bonds:x:all": old,
                "imports": old, "watch_v1": old, "cbr:2023-10-20": old, "stk_hist_v1_2026-01-05": old, "fng_cl1:2026-01-05": old,
                "inst:imp:X": old, "ratings_v3": old, "stkXc_v1_like_wildcard": old, "res": old, "journal_v1": old}
        for k, t in rows.items():
            st.write("INSERT INTO kv(k, v, t) VALUES(?,?,?)", (k, "{}", t))
        r = st.kv_gc(now=now)
        left = {k for (k,) in st.conn().execute("SELECT k FROM kv")}
        gone = {"stk_c_v1_SBER_24_400_2026-08-01", "mqquote:SBER", "bondiz2:RU000A1038V6", "res:bonds:x:all"}
        self.assertEqual(r["deleted"], len(gone))
        self.assertEqual(left, set(rows) - gone)
        self.assertEqual(st.kv_gc(now=now)["deleted"], 0)

    def test_rules_never_touch_user_data(self):
        for pre, age in M.KV_GC_RULES:
            self.assertGreaterEqual(age, 3 * M.DAY)
            for bad in ("imports", "watch", "journal", "cfg", "config", "ratings", "tg_", "tax_", "snap", "cbr:", "kbdc1:", "fng_cl1:"):
                self.assertFalse(pre.startswith(bad) or bad.startswith(pre), (pre, bad))


if __name__ == "__main__":
    unittest.main()
