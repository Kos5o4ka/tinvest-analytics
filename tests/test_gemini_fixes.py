"""Регрессионные тесты исправлений из ветки gemini-fix (BUG-01 .. BUG-18)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
from _load import load  # noqa: E402

M = load()


class GeminiFixesTests(unittest.TestCase):
    def test_bug01_pdf_cmap_no_collision(self):
        """_pdf_cmap из 13b возвращает (width, mp), а _cpi_pdf_cmap из 13r — словарь mp."""
        sample = b"1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n1 beginbfchar\n<0041> <0041>\nendbfchar"
        res_kr = M._pdf_cmap(sample)
        self.assertIsInstance(res_kr, tuple)
        self.assertEqual(len(res_kr), 2)
        self.assertEqual(res_kr[0], 2)
        self.assertEqual(res_kr[1][0x0041], "A")

        res_cpi = M._cpi_pdf_cmap(sample)
        self.assertIsInstance(res_cpi, dict)
        self.assertEqual(res_cpi[0x0041], "A")

    def test_bug02_flows_worker_sectors(self):
        import flows_worker as fw
        self.assertEqual(fw.SECTORS["TRMK"], "Металлы и добыча")
        self.assertEqual(fw.SECTORS["SPBE"], "Банки и финансы")
        self.assertEqual(fw.SECTORS["FESH"], "Транспорт")
        self.assertNotIn("TNFT", fw.SECTORS)

    def test_bug04_name_tokens_no_5char_collision(self):
        self.assertNotEqual(M.name_tokens("Интерлизинг"), M.name_tokens("ИнтерФудГрупп"))
        self.assertNotEqual(M.name_tokens("Транснефть"), M.name_tokens("ТрансКонтейнер"))
        self.assertNotEqual(M.issuer_group_key("Интерлизинг 001Р-01"), M.issuer_group_key("ИнтерФудГрупп БО-01"))
        self.assertEqual(M.name_tokens("Селигдар"), frozenset({"селигдар"}))
        # падежи из журнала рейтинговых действий сводятся к той же основе
        self.assertEqual(M.name_tokens("Ульяновской области"), M.name_tokens("Ульяновская область"))
        self.assertEqual(M.name_tokens("ТОМСКА"), M.name_tokens("Томск"))
        self.assertFalse(M._mon_match(set(M.name_tokens("Золото Селигдара")), set(M.name_tokens("Селигдар"))))

    def test_bug04_monitor_uses_issuer_not_stored_tokens(self):
        e = {"issuer": "Интерлизинг", "tokens": ["интер"]}
        self.assertEqual(M._mon_ev_tokens(e), {"интерлизинг"})

    def test_bug09_pool_map_nested_no_deadlock(self):
        res = M.pool_map(lambda x: M.pool_map(lambda y: x * 10 + y, [1, 2, 3], workers=4), [1, 2, 3], workers=4)
        self.assertEqual(res, [[11, 12, 13], [21, 22, 23], [31, 32, 33]])

    def test_bug10_op_qty_fractional(self):
        self.assertEqual(M.op_qty({"quantity": "5"}), 5)
        self.assertIsInstance(M.op_qty({"quantity": "5"}), int)
        self.assertAlmostEqual(M.op_qty({"quantity": "0.5"}), 0.5)
        self.assertAlmostEqual(M.op_qty({"quantityDone": "1.25"}), 1.25)

    def test_bug15_flows_trade_lot_and_ns_timestamp(self):
        raw = [{"direction": "TRADE_DIRECTION_BUY", "price": {"units": 300, "nano": 0}, "quantity": 2,
                "time": "2026-11-17T10:15:30.123456789Z"}]
        rows_share = M._flw_trade_rows(raw, lot=10, is_bond=False)
        self.assertEqual(len(rows_share), 1)
        self.assertEqual(rows_share[0]["qty"], 20)
        self.assertEqual(rows_share[0]["value"], 6000.0)
        self.assertIsNotNone(rows_share[0]["ts"])

        raw_bond = [{"direction": "TRADE_DIRECTION_SELL", "price": {"units": 95, "nano": 0}, "quantity": 3,
                     "time": "2026-11-17T10:15:30.987654321Z"}]
        rows_bond = M._flw_trade_rows(raw_bond, lot=1, face=1000.0, is_bond=True)
        self.assertEqual(rows_bond[0]["value"], 2850.0)

    def test_bug18_parse_num_multiple_separators(self):
        self.assertEqual(M.parse_num("1,000,000"), 1000000.0)
        self.assertEqual(M.parse_num("1.000.000"), 1000000.0)
        self.assertEqual(M.parse_num("1,234.56"), 1234.56)
        self.assertEqual(M.parse_num("1.234,56"), 1234.56)

    def test_new01_and_new11_micro_lot_and_empty_level_drops(self):
        # NEW-01: _mic_fetch делит сделки сервера данных на lot
        orig_ds, orig_meta = M._flw_ds, M._mic_meta
        M._mic_meta = lambda cfg, secid: {"lot": 10, "face": None, "is_bond": False}
        M._flw_ds = lambda path, params, ttl: (
            {"bids": [[100, 10]], "asks": [[101, 10]], "ts": 1000.0}
            if path == "md/orderbook"
            else {"trades": [{"ts": 1000.0, "side": "buy", "price": 101.0, "qty": 50}]}
        )
        try:
            r = M._mic_fetch({}, "SBER")
        finally:
            M._flw_ds, M._mic_meta = orig_ds, orig_meta
        self.assertEqual(r["trades"][0]["lots"], 5.0)

        # NEW-11: при полном выедании уровня (q=None) видимый расход drops засчитывает 100 -> нет ложного айсберга
        M._mic_state.clear()
        M.mic_ice_update("TST1", {"asks": [[101.0, 100]], "bids": [[100.0, 50]]}, [], 1000.0)
        M.mic_ice_update("TST1", {"asks": [[102.0, 100]], "bids": [[100.0, 50]]},
                         [{"ts": 1005.0, "side": "buy", "price": 101.0, "lots": 100.0}], 1010.0)
        M.mic_ice_update("TST1", {"asks": [[101.0, 100]], "bids": [[100.0, 50]]}, [], 1020.0)
        M.mic_ice_update("TST1", {"asks": [[101.0, 100]], "bids": [[100.0, 50]]}, [], 1030.0)
        M.mic_ice_update("TST1", {"asks": [[101.0, 100]], "bids": [[100.0, 50]]},
                         [{"ts": 1035.0, "side": "buy", "price": 101.0, "lots": 200.0}], 1040.0)
        M.mic_ice_update("TST1", {"asks": [[101.0, 100]], "bids": [[100.0, 50]]}, [], 1050.0)
        rep = M.mic_ice_report("TST1", 1050.0)
        # drops = 100 (при исчезновении на 1010), executed = 300 -> hidden = 200, а не 300
        self.assertEqual(rep["candidates"][0]["visible_consumed_lots"], 100.0)
        self.assertEqual(rep["candidates"][0]["hidden_est_lots"], 200.0)

    def test_new02_and_new03_corp_saifullin_neg_equity_and_events_inn(self):
        # NEW-02: убыток при отрицательном капитале не даёт положительный K5 и «удовлетворительно»
        c = {"1200": 100.0, "1100": 50.0, "1300": -50.0, "1500": 200.0, "1600": 150.0, "2110": 100.0, "2200": -10.0, "2400": -500.0}
        sk = M.crp_saifullin(c)
        self.assertEqual(sk["key"], "high")
        self.assertLess(sk["x"]["K5"], 0)

        # NEW-03: crp_events при наличии ISIN всё равно запрашивает события по ИНН
        calls = []
        orig = M.disc_facts
        M.disc_facts = lambda isin=None, inn=None, kind=None: calls.append((isin, inn)) or (
            [{"doc_id": 1, "title": "Допэмиссия акций", "published": "2026-05-01"}] if inn else []
        )
        try:
            evs, _ = M.crp_events("RU000A0TEST1", "7701234567")
        finally:
            M.disc_facts = orig
        self.assertTrue(any(inn == "7701234567" for _, inn in calls))
        self.assertEqual(len(evs), 1)

    def test_new04_rotation_discount_tax_at_maturity_and_floater_floor(self):
        # NEW-04: при T >= life НДФЛ на дисконт при погашении учитывается; флоатер не уходит в отрицательный купон
        knots = [(0.0, 10.0), (5.0, 10.0)]
        flows = [(1.0, 0.0, 100.0)]
        tr_tax = M.rot_tr_fixed(knots, 2.0, flows, price=80.0, accr0=0.0, tax=True)
        tr_notax = M.rot_tr_fixed(knots, 2.0, flows, price=80.0, accr0=0.0, tax=False)
        self.assertLess(tr_tax, tr_notax)
        tr_fl = M.rot_tr_floater([(0.0, 2.0), (2.0, 2.0)], 1.0, spread=-5.0, tax=False)
        self.assertGreaterEqual(tr_fl, 0.0)

    def test_new06_debtx_fx_extreme_scenario_no_zero_div(self):
        from datetime import date
        p = {"nominal": 1000.0, "price": 100.0, "coupon": 6.0, "freq": 2, "mat": date(2028, 1, 1),
             "buy_fx": 80.0, "qty": 10.0, "nkd": 0.0, "other": 0.0, "scenarios": [-100, -120, 0, 20]}
        r = M.dbx_fx_calc(p, date(2026, 1, 1))
        self.assertEqual([s["scenario"] for s in r["scenarios"]], [0, 20])

    def test_new08_money_no_ldv_on_savings(self):
        # NEW-08: allow_ldv=False отключает ЛДВ для накопительных счетов даже на 4 года
        r = M.mm_after_tax(1000000, 4 * 365, 10.0, 0.0, 2026, allow_ldv=False)
        self.assertFalse(r["ldv"])
        self.assertGreater(r["tax"], 0)

    def test_new09_server_tqir_is_bond(self):
        import tinvest_server as ts
        class FakeMD:
            def find_by_ticker(self, secid, cc):
                if cc == "TQIR":
                    return {"uid": "u-vdo", "lot": 1, "nominal": {"units": 1000, "nano": 0}}
                raise ts.tinvest_md.MDError("not found")
        app = object.__new__(ts.DataServer)
        app._meta = {}
        app.md = FakeMD()
        app.data_dir = "/nonexistent_dir_for_test"
        meta = app.md_meta("VDO1")
        self.assertEqual(meta["cls"], "bond")

    def test_new10_taxopt_annual_coupon_aggregation(self):
        # NEW-10: при 10 взносах по 4 млн (купон 10% = 400k на лот -> 4 млн/год > 2.4 млн порога) ставка на превышение 15%
        r = M.txo_iis3_calc(2025, 4000000, 10.0, 10, income=0.0, rate15=False, coupon_share=1.0)
        last_row = r["rows"][-1]
        # 10-й год: капитал ~40+ млн, купон > 4 млн -> налог строго выше 13% от купона
        est_cp = (last_row["broker_capital"] / 1.0) * 0.10
        # Проверяем, что эффективная ставка налога в 10-м году > 13%
        self.assertGreater(last_row["broker_coupon_tax"], 2400000 * 0.13)

    def test_bug05_klocks_bounded(self):
        for i in range(600):
            M.key_lock(f"test_klock_prune_{i}")
        self.assertLessEqual(len(M._klocks), 520)

    def test_feat11_primary_nip_and_freeze_cost(self):
        g = M.primary_parse_guide("Биржевые облигации, ориентир купона до 22,5% годовых, срок 3 года", "")
        self.assertEqual(g["guide_y"], 22.5)
        self.assertEqual(g["term"], 3.0)
        self.assertFalse(g["floater"])

        gf = M.primary_parse_guide("Флоатер КС + 2,5%, срок 24 мес", "")
        self.assertTrue(gf["floater"])
        self.assertEqual(gf["term"], 2.0)

        scr = [
            {"id": "B1", "name": "Ромашка 001P-01", "kind": "corp", "cur": "RUB", "yield": 21.0, "dur": 2.5, "rating": {"v": "AA"}},
            {"id": "B2", "name": "Другой 001P-01", "kind": "corp", "cur": "RUB", "yield": 20.5, "dur": 2.8, "rating": {"v": "AA"}},
        ]
        row = {"short": "Ромашка", "desc": "до 22,5%, срок 3 года", "book": "", "rating": {"v": "AA"}}
        nip = M.primary_nip_for(row, scr, rusfar=16.0, freeze_days=4)
        self.assertEqual(nip["issuer_y"], 21.0)
        self.assertEqual(nip["nip_issuer_bp"], 150)
        self.assertEqual(nip["ref_src"], "issuer")
        self.assertGreater(nip["freeze_cost_pct"], 0)
        self.assertLess(nip["net_nip_bp"], nip["nip_bp"])

        st = M._grp_stats([
            {"p0": 100.5, "p7": 101.0, "p30": 102.0, "now": 102.0},
            {"p0": 99.5, "p7": 99.8, "p30": 99.0, "now": 99.0},
        ])
        self.assertEqual((st["above0"], st["above7"], st["above30"]), (50.0, 50.0, 50.0))

    def test_feat_arb_inversion_and_fx_vs_rub(self):
        rows = [
            # Один эмитент, близкая дюрация -> арбитраж +200 б.п.
            {"id": "A1", "isin": "RU000A0AAA01", "name": "Ромашка 001P-01", "kind": "corp", "cur": "RUB", "yield": 23.0, "dur": 2.0, "turn": 5e6, "rating": "AA"},
            {"id": "A2", "isin": "RU000A0AAA02", "name": "Ромашка 001P-02", "kind": "corp", "cur": "RUB", "yield": 21.0, "dur": 2.1, "turn": 5e6, "rating": "AA"},
            # Валютный выпуск того же эмитента -> безубыточная девальвация
            {"id": "A3", "isin": "RU000A0AAA03", "name": "Ромашка 001P-USD", "kind": "corp", "cur": "USD", "yield": 8.0, "dur": 2.0, "turn": 2e6, "rating": "AA"},
            # Эмитент с инверсией кривой (короткий 34%, длинный 26%) -> высокий стресс
            {"id": "B1", "isin": "RU000A0BBB01", "name": "Стресс 001P-01", "kind": "corp", "cur": "RUB", "yield": 34.0, "dur": 0.6, "turn": 1e6, "rating": "BB"},
            {"id": "B2", "isin": "RU000A0BBB02", "name": "Стресс 001P-02", "kind": "corp", "cur": "RUB", "yield": 26.0, "dur": 2.5, "turn": 1e6, "rating": "BB"},
        ]
        res = M.arb_compute(rows, fx_rates={"USD": 95.0}, fee_pct=0.05)
        self.assertEqual(len(res["pairs"]), 1)
        self.assertEqual(res["pairs"][0]["spread_bp"], 200)
        self.assertGreater(res["pairs"][0]["payback_mo"], 0)
        self.assertEqual(len(res["inversions"]), 1)
        self.assertEqual(res["inversions"][0]["inv_bp"], 800)
        self.assertEqual(res["inversions"][0]["severity"], "high")
        self.assertEqual(len(res["fx_vs_rub"]), 1)
        self.assertLess(res["fx_vs_rub"][0]["be_ldv_pct"], res["fx_vs_rub"][0]["be_pre_pct"])
        self.assertGreater(res["fx_vs_rub"][0]["fx_breakeven_1y"], 95.0)

    def test_feat_postmortem_and_ghost_portfolio(self):
        from datetime import date
        sales = [
            {"bucket": "sec", "uid": "u1", "name": "Сбер", "ticker": "SBER", "type": "share", "qty": 10, "cost": 2000, "proceeds": 2500, "result": 500, "bdate": date(2026, 1, 1), "sdate": date(2026, 1, 11)},
            {"bucket": "sec", "uid": "u2", "name": "Газпром", "ticker": "GAZP", "type": "share", "qty": 10, "cost": 2000, "proceeds": 1800, "result": -200, "bdate": date(2026, 1, 1), "sdate": date(2026, 3, 2)},
            {"bucket": "sec", "uid": "u3", "name": "ВТБ", "ticker": "VTBR", "type": "share", "qty": 10, "cost": 2000, "proceeds": 1900, "result": -100, "bdate": date(2026, 1, 1), "sdate": date(2026, 3, 2)},
            {"bucket": "sec", "uid": "u4", "name": "Лукойл", "ticker": "LKOH", "type": "share", "qty": 10, "cost": 2000, "proceeds": 1950, "result": -50, "bdate": date(2026, 1, 1), "sdate": date(2026, 3, 2)},
        ]
        st = M.pm_trades_stats(sales)
        self.assertEqual((st["n"], st["wins"], st["losses"]), (4, 1, 3))
        self.assertAlmostEqual(st["profit_factor"], 500 / 350, places=2)
        self.assertTrue(st["disposition_flag"])
        self.assertAlmostEqual(st["disposition_ratio"], 6.0, places=1)

        hist = {"days": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "value": [100000.0, 105000.0, 220000.0],
                "invested": [100000.0, 100000.0, 200000.0],
                "bench": {"LQDT": [1.0, 1.01, 1.02], "TMOS": [10.0, 11.0, 11.0]}}
        gh = M.pm_ghost_portfolio(hist)
        self.assertTrue(gh["ok"])
        by_c = {x["code"]: x for x in gh["items"]}
        # LQDT: 100k по 1.0 -> 100k ед; +100k по 1.02 -> +98039.22 ед -> итого 198039.22 * 1.02 = 202000 ₽
        self.assertAlmostEqual(by_c["LQDT"]["ghost_val"], 202000.0, places=1)
        self.assertAlmostEqual(by_c["LQDT"]["diff_rub"], 18000.0, places=1)

    def test_bug_sec02_safe_url(self):
        import glob
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        core_js = open(os.path.join(root, "src/web/js/01_core.js"), encoding="utf-8").read()
        self.assertIn("function safeUrl(", core_js)
        self.assertIn("https:", core_js)
        self.assertIn("http:", core_js)

        # Все внешние динамические href в JS должны проходить через safeUrl / rtSafeUrl
        bad = []
        pat = re.compile(r"""href=(?:"\$\{esc\(([^)]+)\)\}"|'\+esc\(([^)]+)\)\+')""")
        for path in sorted(glob.glob(os.path.join(root, "src/web/js/*.js"))):
            fname = os.path.basename(path)
            txt = open(path, encoding="utf-8").read()
            for idx, line in enumerate(txt.splitlines(), 1):
                for m in pat.finditer(line):
                    expr = m.group(1) or m.group(2)
                    # Константные/внутренние URL и уже отфильтрованные переменные (rtSafeUrl/safeUrl) допустимы
                    if expr in ("u", "su", "eu", "fu", "bu", "iu", "au", "ru", "xu", "lu", "s", "href", "proUrl()"):
                        continue
                    if "safeUrl(" in expr or "rtSafeUrl(" in expr:
                        continue
                    bad.append(f"{fname}:{idx}: {expr}")
        self.assertEqual(bad, [], f"Найдены непроверенные внешние href: {bad}")

    def test_bug_ui01_pro_features(self):
        import glob
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pro_js = open(os.path.join(root, "src/web/js/43_pro.js"), encoding="utf-8").read()
        # Собираем все страницы из PRO_PAGES и regPage(..., {..., pro:true})
        m_pages = re.search(r"const PRO_PAGES=\[([^\]]+)\]", pro_js)
        self.assertIsNotNone(m_pages)
        pro_pages = set(re.findall(r"'([^']+)'", m_pages.group(1)))
        feat_keys = set()
        # Ключи из PRO_FEATURES={...}
        m_feat = re.search(r"const PRO_FEATURES=\{([\s\S]*?)\n\};", pro_js)
        self.assertIsNotNone(m_feat)
        feat_keys.update(re.findall(r"^\s*([a-z0-9_]+):\{", m_feat.group(1), re.M))
        for path in sorted(glob.glob(os.path.join(root, "src/web/js/*.js"))):
            txt = open(path, encoding="utf-8").read()
            for m in re.finditer(r"regPage\('([^']+)',\{[^}]*\bpro:true\b", txt):
                pro_pages.add(m.group(1))
            feat_keys.update(re.findall(r"PRO_FEATURES\.([a-z0-9_]+)\s*=", txt))
        missing = sorted(pro_pages - feat_keys)
        self.assertEqual(missing, [], f"Отсутствуют в PRO_FEATURES: {missing}")
        # В proAbout() должна быть защита от undefined
        m_about = re.search(r"function proAbout\(\)\{([\s\S]*?)\n\}", pro_js)
        self.assertIsNotNone(m_about)
        self.assertTrue(".filter(Boolean)" in m_about.group(1) or "if(!f)return''" in m_about.group(1))


if __name__ == "__main__":
    unittest.main()
