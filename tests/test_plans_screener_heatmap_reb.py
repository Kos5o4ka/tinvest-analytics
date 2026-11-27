"""Unit-тесты для фиксов Скринера, Тепловой карты, Недельной инфляции и Ребалансировки."""
import json
import os
import tempfile
import unittest

from tests._load import load
from tests.test_ui_screens_review import _read
from tests.test_ui_shell_review import DOM_STUB, ROOT, _run_jsc as _jsc_raw


def _run_jsc(body, files=()):
    """Ядро (01_core.js) + DOM-заглушка + файлы экрана; возвращает последнюю строку вывода (JSON из print)."""
    loads = "".join("load(%s);\n" % json.dumps(os.path.join(ROOT, f))
                    for f in ["src/web/js/01_core.js", "src/web/js/02_state_api.js"] + [f for f in files if not f.startswith(("src/web/js/01_", "src/web/js/02_"))])
    extra = ("if(!document.head)document.head=_mkEl('head');"
             "if(!document.body)document.body=_mkEl('body');\n")
    out = _jsc_raw(DOM_STUB + "\n" + extra + loads + body)
    return out.strip().splitlines()[-1]

T = load()


class FloaterFormulaTests(unittest.TestCase):
    def setUp(self):
        self._old_store = T.STORE
        self._tmp = tempfile.TemporaryDirectory()
        T.STORE = T.Store(os.path.join(self._tmp.name, "test.db"))
        self._old_krs = T.key_rate_series

    def tearDown(self):
        T.STORE = self._old_store
        T.key_rate_series = self._old_krs
        self._tmp.cleanup()

    def test_parse_formula(self):
        self.assertEqual(T.fl_parse_formula("Ключевая ставка Банка России + 2,5%"), ("key", 2.5))
        self.assertEqual(T.fl_parse_formula("КС + 1.75 п.п."), ("key", 1.75))
        self.assertEqual(T.fl_parse_formula("RUONIA + 1,40%"), ("ruonia", 1.4))
        self.assertEqual(T.fl_parse_formula("RUSFAR3M + 1,5%"), ("rusfar", 1.5))
        self.assertEqual(T.fl_parse_formula("Ключевая ставка ЦБ РФ - 0,5%"), ("key", -0.5))
        self.assertEqual(T.fl_parse_formula("ИПЦ + 2,5%"), ("infl", None))
        self.assertEqual(T.fl_parse_formula("RUONIA"), ("ruonia", None))
        self.assertEqual(T.fl_parse_formula(""), (None, None))

    def test_fl_label(self):
        self.assertEqual(T.fl_label({"base": "key", "spread": 2.5}, True), "КС + 2,50%")
        self.assertEqual(T.fl_label({"base": "ruonia", "spread": 1.4}, True), "RUONIA + 1,40%")
        self.assertEqual(T.fl_label({"base": "rusfar", "spread": 1.5}, True), "RUSFAR + 1,50%")
        self.assertEqual(T.fl_label({"base": "ruonia", "spread": None}, True), "RUONIA")
        self.assertEqual(T.fl_label({"base": "rusfar", "spread": None}, True), "RUSFAR")
        self.assertEqual(T.fl_label({"base": "infl"}, True), "ИНФЛЯЦИЯ")
        self.assertEqual(T.fl_label({}, False), "ФИКС")

    def test_spread_put_details_and_no_none_cache(self):
        # Первичный источник COUPON_DETAILS работает даже без bz и кэшируется
        v = T.fl_spread_put("RU000A10TEST", "Тест", None, 1000.0, "corp", "RUSFAR + 1,8%")
        self.assertEqual((v["base"], v["spread"]), ("rusfar", 1.8))
        self.assertIn("RU000A10TEST", T.fl_spread_cached())

        # Для ruonia без details считается спред по прошлым купонам
        T.key_rate_series = lambda: [("2026-01-01", 16.0)]
        bz = {"coupons": [{"coupondate": "2026-01-10", "value": None, "valueprc": None},
                          {"coupondate": "2026-04-10", "value": None, "valueprc": 17.4}], "amort": []}
        v2 = T.fl_spread_put("RU000A10RUON", "ОФЗ-ПК", bz, 1000.0, "ofz", "RUONIA")
        self.assertEqual((v2["base"], v2["spread"]), ("ruonia", 1.4))
        self.assertIn("RU000A10RUON", T.fl_spread_cached())

        # При пустых прошлых купонах None НЕ кэшируется на 30 дней
        bz_empty = {"coupons": [{"coupondate": "2099-01-01", "value": None, "valueprc": None}], "amort": []}
        v3 = T.fl_spread_put("RU000A10NEW1", "Новый флоатер", bz_empty, 1000.0, "corp", "Ключевая ставка")
        self.assertIsNone(v3["spread"])
        self.assertNotIn("RU000A10NEW1", T.fl_spread_cached())

    def test_screener_payload_issuer_and_fl_kick(self):
        old_scr = T.screener_rows
        old_tcat = T.__dict__.get("tcat_info")
        old_br = T.__dict__.get("best_rating")
        old_kick = T.fl_spread_kick
        kicked = []
        try:
            T.screener_rows = lambda: [
                {"id": "B1", "isin": "RU000A10DUQ6", "name": "ВДО Тест", "full": "ООО ВДО Тест 01",
                 "kind": "corp", "cur": "RUB", "nominal": 1000, "price": 80.0, "yield": 81.5, "dur": 1.2,
                 "coupon": 20.0, "next": "2026-12-01", "mat": "2028-01-01", "offer": None, "level": 3,
                 "turn": 100000, "trades": 10, "zs": None, "cy": 25.0, "macdur": 1.2, "chg": 0.0,
                 "sub": None, "size": 1000, "nkd": 10, "btype": "облигация", "cpn_det": None, "spread": 65.0, "liq": "L2"},
                {"id": "B2", "isin": "RU000A10FL01", "name": "Флоатер", "full": "Флоатер 01",
                 "kind": "corp", "cur": "RUB", "nominal": 1000, "price": 100.0, "yield": 19.0, "dur": 1.5,
                 "coupon": 18.5, "next": "2026-12-01", "mat": "2028-01-01", "offer": None, "level": 1,
                 "turn": 500000, "trades": 20, "zs": None, "cy": 18.5, "macdur": 1.5, "chg": 0.0,
                 "sub": None, "size": 1000, "nkd": 5, "btype": "облигация с плавающим купоном",
                 "cpn_det": "RUSFAR + 2,1%", "spread": 2.1, "liq": "L1"},
            ]
            T.tcat_info = lambda isin: {"sector": "financial", "floating": isin == "RU000A10FL01",
                                        "amort": False, "issuer": "Эмитент Альфа" if isin == "RU000A10DUQ6" else "Бета"}
            T.best_rating = lambda isin, name: {"v": "BB", "agency": "АКРА", "approx": False, "all": []}
            T.fl_spread_kick = lambda rows, cached: kicked.append(True)
            p = T.screener_payload()
            by_isin = {r["isin"]: r for r in p["rows"]}
            self.assertEqual(by_isin["RU000A10DUQ6"]["issuer"], "Эмитент Альфа")
            self.assertEqual(by_isin["RU000A10FL01"]["fl_label"], "RUSFAR + 2,10%")
            self.assertEqual(by_isin["RU000A10FL01"]["fl_base"], "rusfar")
            # Проверим, что fl_spread_kick не ставит в очередь бумагу с уже распарсенным cpn_det
            T.fl_spread_kick = old_kick
            T._fl_job["running"] = True  # не запускаем поток, проверяем фильтрацию через _fl_job
            T._fl_job["running"] = False
            self.assertFalse(T.fl_spread_kick([by_isin["RU000A10FL01"]], {}))
        finally:
            T.screener_rows = old_scr
            if old_tcat is None:
                T.__dict__.pop("tcat_info", None)
            else:
                T.tcat_info = old_tcat
            if old_br is None:
                T.__dict__.pop("best_rating", None)
            else:
                T.best_rating = old_br
            T.fl_spread_kick = old_kick


class HeatmapFixesTests(unittest.TestCase):
    def setUp(self):
        self._old = {k: T.__dict__.get(k) for k in ("stocks_universe", "screener_rows", "best_rating", "stock_candles", "stock_history_closes")}

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                T.__dict__.pop(k, None)
            else:
                setattr(T, k, v)

    def test_bonds_ofz_and_bb_guaranteed(self):
        rows = [{"id": f"AAA{i}", "isin": f"AAA{i}", "name": f"AAA {i}", "kind": "corp",
                 "turn": 10000 - i, "chg": 0.1, "price": 100, "yield": 15, "rating": "AAA"} for i in range(320)]
        rows.append({"id": "SU26238", "isin": "SU26238", "name": "ОФЗ 26238", "kind": "ofz",
                     "turn": 50000, "chg": 0.2, "price": 60, "yield": 16, "rating": None})
        rows.append({"id": "BB1", "isin": "RU000BB1", "name": "ВДО ББ", "kind": "corp",
                     "turn": 50, "chg": -0.5, "price": 90, "yield": 24, "rating": "BB"})
        T.screener_rows = lambda: rows
        T.best_rating = lambda isin, name: None
        p = T.heatmap_payload("bonds")
        gnames = [g["name"] for g in p["groups"]]
        self.assertIn("ОФЗ", gnames)
        self.assertIn("≤BB", gnames)
        self.assertNotIn("без рейтинга", gnames)

    def test_equities_none_chg_not_zeroed_and_stk_changes_fallback(self):
        T.stocks_universe = lambda: [
            {"secid": "SBER", "shortname": "Сбер", "sector": "Финансы", "price": 300, "chg_d": 1.0, "chg_w": None, "value_today": 100, "cap": 1000},
            {"secid": "VTBR", "shortname": "ВТБ", "sector": "Финансы", "price": 80, "chg_d": 2.0, "chg_w": 4.0, "value_today": 100, "cap": 1000},
        ]
        p = T.heatmap_payload("stocks", "w", "cap")
        items = {i["id"]: i for i in p["groups"][0]["items"]}
        self.assertIsNone(items["SBER"]["chg"])
        self.assertEqual(items["VTBR"]["chg"], 4.0)
        self.assertEqual(p["stats"]["wchg"], 4.0)

        # _stk_changes fallback при пустой дате -1-n
        days = ["2026-10-%02d" % d for d in range(1, 29)]
        T.stock_candles = lambda s, i=24, d=400: [{"t": x} for x in days]
        T.stock_history_closes = lambda d: {} if d == days[-1 - 5] else {"SBER": 250.0}
        rs = [{"secid": "SBER", "price": 300.0, "chg_w": None, "chg_m": None}]
        T._stk_changes(rs)
        self.assertAlmostEqual(rs[0]["chg_w"], 20.0, places=2)


class LadderCapTests(unittest.TestCase):
    def test_default_max_issuer_no_hard_8_5_limit(self):
        old = {k: T.__dict__.get(k) for k in ("_bc_universe", "_mon_flags", "offers_of_isin")}
        try:
            T._bc_universe = lambda: [
                {"id": f"B{i}", "_isin": f"RU000A{i:06d}", "name": f"Бонд {i}", "kind": "corp", "cur": "RUB",
                 "yield": 18.0, "mat": f"{2027 + i}-06-01", "offer": None, "turn": 5000000, "spread": 2.0,
                 "nominal": 1000, "price": 100.0, "_rt": {"v": "AA"}, "_ci": {}, "_iss": ("EMIT1",)}
                for i in range(3)
            ]
            T._mon_flags = lambda isin: {}
            T.offers_of_isin = lambda isin, off, today: []
            res = T.ladder_payload({}, {"sum": "300000", "years": "3", "rungs": "3"})
            self.assertEqual(res["params"]["max_issuer"], 100.0)
        finally:
            for k, v in old.items():
                if v is None:
                    T.__dict__.pop(k, None)
                else:
                    setattr(T, k, v)


class JsFixesTests(unittest.TestCase):
    def test_scr_isin_and_issuer_search(self):
        out = _run_jsc(r"""
          S.scr = {
            rows: [
              { id: '1', isin: 'RU000A10DUQ6', name: 'ВДО 81%', full: 'ООО ВДО', issuer: 'Эмитент Альфа', cur: 'RUB', kind: 'corp', yield: 81.5, mat: '2028-01-01', turn: 1e6, years: 2 },
              { id: '2', isin: 'RU000A10NORM', name: 'Норма', full: 'ПАО Норма', issuer: 'Бета', cur: 'RUB', kind: 'corp', yield: 18.0, mat: '2028-01-01', turn: 1e6, years: 2 }
            ]
          };
          S.sf = Object.assign({}, SCR_DEF);
          const defCnt = scrRows().length;
          S.sf.q = 'RU000A10DUQ6';
          const isinRes = scrRows().map(r => r.isin);
          S.sf.q = 'эмитент альфа';
          const issRes = scrRows().map(r => r.isin);
          print(JSON.stringify({ defCnt, isinRes, issRes }));
        """, files=["src/web/js/14_scr.js"])
        data = json.loads(out)
        self.assertEqual(data["defCnt"], 1)
        self.assertEqual(data["isinRes"], ["RU000A10DUQ6"])
        self.assertEqual(data["issRes"], ["RU000A10DUQ6"])

    def test_infl_no_dup_legend_and_color_s2(self):
        out = _run_jsc(r"""
          S.infl = {
            years: { '2025': [{week: 1, date: '2025-01-13', pct: 0.5}], '2026': [{week: 1, date: '2026-01-12', pct: 0.4}] },
            avg: [[1, 0.2]], avg_label: '2017–2021', history_from: '2025-01-13', loading: false
          };
          let captured = null;
          function chart(id, fn, o){ captured = o; }
          function line(){}
          const html = inflWeekHtml();
          print(JSON.stringify({ hasManualLegend: html.includes('rx-lg'), colors: captured.series.map(s => s.c) }));
        """, files=["src/web/js/24_rates.js"])
        data = json.loads(out)
        self.assertFalse(data["hasManualLegend"])
        self.assertEqual(data["colors"][:2], ["var(--s1)", "var(--s2)"])

    def test_reb_types_and_saved_presets(self):
        out = _run_jsc(r"""
          S.data = { portfolio: { positions: [
            { type: 'credit_portfolio_dfa', value_rub: 50000 },
            { type: 'unknown_xyz', value_rub: 50000 }
          ] } };
          S.cfg = { targets: { credit_portfolio_dfa: 50, unknown_xyz: 50 } };
          S.reb.draft = null;
          const html = pReb();
          rebSavedStore([{ id: 'u1', name: 'Мой пресет', tg: { share: 70, bond: 30 } }]);
          const loaded = rebSavedLoad();
          print(JSON.stringify({ hasCfa: html.includes('ЦФА'), hasOther: html.includes('Прочее'), hasRawUnknown: html.includes('<b>unknown_xyz</b>'), loadedLen: loaded.length, loadedName: loaded[0].name }));
        """, files=["src/web/js/07_helpers.js", "src/web/js/25_reb.js"])
        data = json.loads(out)
        self.assertTrue(data["hasCfa"])
        self.assertTrue(data["hasOther"])
        self.assertFalse(data["hasRawUnknown"])
        self.assertEqual(data["loadedLen"], 1)
        self.assertEqual(data["loadedName"], "Мой пресет")
        self.assertNotIn("opacity", _read("src/web/css/10_map.css").split("tr.scr-low")[1])


if __name__ == "__main__":
    unittest.main()
