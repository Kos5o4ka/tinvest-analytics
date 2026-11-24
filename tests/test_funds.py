"""Биржевые фонды: разбор состава (T-Bank, веса индекса ISS), кэш, карточка фонда в stock_card (офлайн, реальные образцы в fixtures)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

m = _load.load()
FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f)


class Parse(unittest.TestCase):
    def test_tbank_structure(self):
        r = m.fnd_tb_parse(fx("tbank_etf_structure_tdiv.json"))
        self.assertEqual(len(r["items"]), 14)
        self.assertEqual(r["count"], 14)
        self.assertEqual(r["nav_cur"], "RUB")
        self.assertGreater(r["nav"], 1e8)
        w = [x["weight"] for x in r["items"]]
        self.assertEqual(w, sorted(w, reverse=True))
        self.assertAlmostEqual(sum(w), 100, delta=1.5)
        top = r["items"][0]
        self.assertEqual((top["name"], top["ticker"], top["type"], top["type_ru"], top["stock"]), ("ДОМ.РФ", "DOMRF", "Stock", "Акция", True))

    def test_tbank_empty_and_garbage(self):
        self.assertIsNone(m.fnd_tb_parse(fx("tbank_etf_structure_empty.json")))   # фонд другой УК: пустой список
        self.assertIsNone(m.fnd_tb_parse(None))
        self.assertIsNone(m.fnd_tb_parse({"items": [{"name": "", "relativeValue": 5}, {"name": "X", "relativeValue": None}]}))
        r = m.fnd_tb_parse({"items": [{"name": "Деньги", "ticker": None, "type": "Currency", "relativeValue": 3},
                                      {"name": "Акция", "ticker": "AAA", "type": "Stock", "relativeValue": 97}]})
        self.assertEqual([x["name"] for x in r["items"]], ["Акция", "Деньги"])
        self.assertFalse(r["items"][1]["stock"])
        self.assertIsNone(r["nav"])

    def test_iss_index(self):
        rows, total, day = m.fnd_iss_index_parse(fx("iss_index_rgbitr.json"))
        self.assertEqual(len(rows), total)
        self.assertGreater(len(rows), 10)
        self.assertRegex(day, r"^\d{4}-\d{2}-\d{2}$")
        self.assertTrue(all(r["ticker"].startswith("SU") and r["isin"] is None for r in rows))   # код ОФЗ — не ISIN
        self.assertAlmostEqual(sum(r["weight"] for r in rows), 100, delta=1.5)


class Holdings(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(m, k) for k in ("http_text",)}
        self.calls = []

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(m, k, v)

    def fake(self, mapping):
        def http_text(url, timeout=25):
            self.calls.append(url)
            for k, v in mapping.items():
                if k in url:
                    if isinstance(v, Exception):
                        raise v
                    return json.dumps(v)
            raise AssertionError("неожиданный запрос " + url)
        m.http_text = http_text

    def test_tbank_source_and_cache(self):
        self.fake({"tbank.ru": fx("tbank_etf_structure_tdiv.json")})
        r = m.fund_holdings("TDIV", force=True)
        self.assertEqual((r["status"], r["basis"], len(r["items"])), ("ok", "fund", 14))
        self.assertIn("tbank.ru", r["source"]["url"])
        n = len(self.calls)
        r2 = m.fund_holdings("TDIV")                         # второй раз — из кэша
        self.assertEqual(len(self.calls), n)
        self.assertEqual(r2["items"], r["items"])

    def test_index_fallback(self):
        self.fake({"tbank.ru": fx("tbank_etf_structure_empty.json"), "RGBITR": fx("iss_index_rgbitr.json")})
        r = m.fund_holdings("SBGB", force=True)
        self.assertEqual((r["status"], r["basis"], r["index"]["id"]), ("ok", "index", "RGBITR"))
        self.assertFalse(any(x["stock"] for x in r["items"]))        # облигации не открываются карточкой акции
        self.assertIn("moex.com", r["source"]["url"])

    def test_no_source(self):
        self.fake({"tbank.ru": fx("tbank_etf_structure_empty.json")})
        r = m.fund_holdings("AKME", force=True, category="Акции")
        self.assertEqual((r["status"], r["items"]), ("none", []))
        self.assertTrue(r["note"])

    def test_tbank_400_is_no_data(self):
        err = m.urllib.error.HTTPError("u", 400, "Bad Request", {}, None)       # T-Bank так отвечает по фондам других УК
        self.fake({"tbank.ru": err})
        r = m.fund_holdings("VDOR", force=True, category="Облигации")
        self.assertEqual((r["status"], r["items"]), ("none", []))
        self.assertNotIn("недоступен", r["note"])

    def test_error_short_ttl(self):
        self.fake({"tbank.ru": OSError("нет сети")})
        r = m.fund_holdings("ZZFN", force=True)
        self.assertEqual(r["status"], "err")
        n = len(self.calls)
        m.fund_holdings("ZZFN")                              # ошибка помнится недолго, но не сразу перезапрашивается
        self.assertEqual(len(self.calls), n)
        m.store().put("fnd_hold_v1_ZZFN", dict(r, fetched=r["fetched"] - m.FND_ERR_TTL - 1))
        self.fake({"tbank.ru": fx("tbank_etf_structure_tdiv.json")})
        self.assertEqual(m.fund_holdings("ZZFN")["status"], "ok")

    def test_bad_ticker(self):
        with self.assertRaises(m.ApiError):
            m.fund_holdings("../x")


class Nav(unittest.TestCase):
    """СЧА и iNAV с Мосбиржи: apps/infogrid/ppif/rates, securities/<тикер>/inavs, доска INAV (реальные ответы ISS в fixtures)."""
    def setUp(self):
        self.saved = {"http_text": m.http_text}
        self.calls = []

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(m, k, v)

    def fake(self, mapping):
        Holdings.fake(self, mapping)

    def test_rates_parse(self):
        r = m.fnd_rates_parse(fx("iss_ppif_rates_vdor.json"), "VDOR")
        self.assertGreater(r["nav"], 1e8)
        self.assertRegex(r["nav_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual((r["nav_cur"], r["issue_date"]), ("RUB", "2026-04-21"))
        self.assertIn("РенКап", r["manager"])
        self.assertIsNone(m.fnd_rates_parse(fx("iss_ppif_rates_vdor.json"), "VDO"))     # поиск нашёл другой тикер — не подставляем
        self.assertIsNone(m.fnd_rates_parse({}, "VDOR"))

    def test_inavs_pick(self):
        j = fx("iss_inavs_tgld.json")
        self.assertEqual(m.fnd_inavs_pick(j, "RUB"), {"code": "TGLDB", "cur": "RUB"})
        self.assertEqual(m.fnd_inavs_pick(j, "USD")["code"], "TGLDA")
        self.assertIsNone(m.fnd_inavs_pick({"inavs": {"columns": ["secid"], "data": []}}))

    def test_inav_parse(self):
        r = m.fnd_inav_parse(fx("iss_inav_vdora.json"))
        self.assertEqual((r["cur"], r["date"]), ("RUB", "2026-11-24"))
        self.assertGreater(r["value"], 900)
        self.assertGreater(r["prev"], 900)
        j = fx("iss_inav_vdora.json")
        j["marketdata"]["data"][0][1] = None                          # нет текущего значения — берём закрытие прошлого дня, без времени
        r2 = m.fnd_inav_parse(j)
        self.assertEqual((r2["value"], r2["time"]), (r["prev"], None))
        self.assertIsNone(m.fnd_inav_parse({}))

    def test_fund_nav_premium_and_cache(self):
        inavs = {"inavs": {"columns": ["secid", "boardid", "ticker", "currencyid"], "data": [["VDORA", "INAV", "VDOR", "RUB"]]}}
        self.fake({"ppif/rates": fx("iss_ppif_rates_vdor.json"), "VDOR/inavs": inavs, "INAV/securities/VDORA": fx("iss_inav_vdora.json")})
        iv = m.fnd_inav_parse(fx("iss_inav_vdora.json"))["value"]
        r = m.fund_nav("VDOR", price=iv * 1.01)
        self.assertGreater(r["nav"], 1e8)
        self.assertEqual((r["inav_code"], r["inav_cur"], r["errors"]), ("VDORA", "RUB", []))
        self.assertAlmostEqual(r["premium"], 1.0, places=2)
        self.assertIn("moex.com", r["source_url"])
        n = len(self.calls)
        m.fund_nav("VDOR", price=iv)                                  # второй раз — из кэша
        self.assertEqual(len(self.calls), n)

    def test_fund_nav_no_inav_and_errors(self):
        empty = {"inavs": {"columns": ["secid"], "data": []}}
        self.fake({"ppif/rates": OSError("нет сети"), "ZZNV/inavs": empty})
        r = m.fund_nav("ZZNV", price=100)
        self.assertIsNone(r["nav"])
        self.assertIsNone(r["inav"])
        self.assertIsNone(r["premium"])
        self.assertTrue(r["errors"] and r["errors"][0].startswith("СЧА"))
        n = len(self.calls)
        m.fund_nav("ZZNV")                                            # ошибка помнится 15 минут: сеть не дёргаем
        self.assertEqual(len(self.calls), n)


class Category(unittest.TestCase):
    def test_names(self):
        c = m.stk_fund_category
        cases = {("VDOR", "БПИФ Ренкап Высокодоходные обл"): "Облигации", ("AMFL", "БПИФ АТОН – Флоатеры"): "Облигации",
                 ("AKMP", "БПИФ Альфа Денежный рынок Плюс"): "Денежный рынок", ("GOOD", "ДОХОДЪ Стратегии денеж. рынка"): "Денежный рынок",
                 ("SBCN", "БПИФ Первая Сберегат. в юанях"): "Валюта", ("AMVY", "АТОН – Облигации в юанях"): "Облигации",
                 ("AKPP", "БПИФ Альфа Платина-Палладий"): "Золото и металлы", ("AMIX", "АТОН – Индекс МосБиржи"): "Акции",
                 ("SBBC", "БПИФ Первая Голубые фишки"): "Акции", ("BCSW", "БПИФ БКС Всепогодный портфель"): "Смешанные",
                 ("XHOUSE", "ЗПИФ Инвестиции в недв"): "Недвижимость", ("ZZZZ", "Нечто"): "Прочие фонды"}
        for (t, n), cat in cases.items():
            self.assertEqual(c(t, n), cat, n)
        self.assertEqual(c("MKBD", "БПИФ МКБ Российские Див. Акции"), "Акции")


class FundCard(unittest.TestCase):
    NAMES = ("stocks_universe", "funds_universe", "stock_candles", "stock_dividends", "fund_meta", "fund_nav", "stock_multiples",
             "stock_next_report")

    def setUp(self):
        self.saved = {k: getattr(m, k) for k in self.NAMES}
        m.stocks_universe = lambda force=False, cfg=None: [{"secid": "SBER", "shortname": "Сбер", "name": "Сбербанк", "sector": "Банки и финансы",
                                                            "price": 300.0, "cap": 1e12, "isin": "RU1", "lot": 1}]
        m.funds_universe = lambda: [{"secid": "TMOS", "shortname": "TMOS ETF", "name": "БПИФ Т-Капитал Индекс МосБиржи", "sector": "Акции",
                                     "price": 6.0, "cap": None, "isin": "RU000A101X76", "lot": 1, "is_fund": True}]
        cs = [{"t": "2026-%02d-%02d" % (1 + i // 28, 1 + i % 28), "o": 6 + i * .01, "h": 6.1 + i * .01, "l": 5.9 + i * .01, "c": 6 + i * .01, "v": 100}
              for i in range(250)]
        m.stock_candles = lambda s, i=24, d=400: cs
        m.stock_dividends = lambda *a, **k: {"items": [], "ttm_value": 0, "yield_ttm": None, "next": None, "source": "none"}
        m.fund_meta = lambda secid, category=None: {"category": category, "manager": "ООО \"Т-Капитал\"", "type_name": "Пай биржевого ПИФа"}
        m.fund_nav = lambda secid, price=None: {"nav": 1.4e10, "nav_date": "2026-11-19", "inav": 5.9, "premium": round((price / 5.9 - 1) * 100, 2)}
        m.stock_multiples = m.stock_next_report = lambda *a, **k: self.fail("для фонда мультипликаторы и отчётность не запрашиваются")

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(m, k, v)

    def test_fund_card(self):
        c = m.stock_card("tmos")
        self.assertEqual((c["kind"], c["secid"], c["quote"]["sector"]), ("fund", "TMOS", "Акции"))
        self.assertIsNone(c["multiples"])
        self.assertIsNone(c["report"])
        self.assertEqual(c["fund"]["manager"], "ООО \"Т-Капитал\"")
        self.assertEqual(len(c["candles"]), 220)
        self.assertEqual((c["fund"]["nav"]["nav"], c["fund"]["nav"]["premium"]), (1.4e10, 1.69))
        self.assertTrue(c["ta"].get("votes"))

    def test_share_still_share(self):
        m.stock_multiples = lambda *a, **k: {"pe": 5}
        m.stock_next_report = lambda *a, **k: {"date": None}
        c = m.stock_card("SBER")
        self.assertEqual(c["kind"], "share")
        self.assertEqual(c["multiples"], {"pe": 5})
        self.assertNotIn("fund", c)

    def test_not_found(self):
        orig = m._stk_tqtf_rows
        m._stk_tqtf_rows = lambda: []
        try:
            with self.assertRaises(m.ApiError) as e:
                m.stock_card("NOPE")
        finally:
            m._stk_tqtf_rows = orig
        self.assertEqual(e.exception.status, 404)

    def test_tqtf_only_fund(self):
        orig = m._stk_tqtf_rows
        m._stk_tqtf_rows = lambda: [{"secid": "FXGD", "shortname": "FXGD", "name": "Золото", "sector": "Прочие фонды", "price": 1.0,
                                     "isin": "IE1", "lot": 1, "is_fund": True}]
        try:
            c = m.stock_card("FXGD")
        finally:
            m._stk_tqtf_rows = orig
        self.assertEqual((c["kind"], c["quote"]["sector"]), ("fund", "Золото и металлы"))

    def test_category_from_full_name(self):
        orig = m.funds_universe
        m.funds_universe = lambda: [{"secid": "ZZRC", "shortname": "ZZRC ETF", "name": "БПИФ Нечто", "sector": "Прочие фонды", "price": 1.0,
                                     "isin": "RU2", "lot": 10, "is_fund": True}]
        m.fund_meta = lambda secid, category=None: {"category": category, "full_name": "БПИФ Нечто",
                                                    "issue_name": "паи БПИФ «Нечто – Высокодоходные облигации»"}
        try:
            c = m.stock_card("ZZRC")
        finally:
            m.funds_universe = orig
        self.assertEqual((c["quote"]["sector"], c["fund"]["category"]), ("Облигации", "Облигации"))


if __name__ == "__main__":
    unittest.main()
