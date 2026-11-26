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

    def test_bug_ui02_ofz_no_portfolio(self):
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        shell_js = open(os.path.join(root, "src/web/js/06_shell.js"), encoding="utf-8").read()
        m = re.search(r"NO_PORTFOLIO_PAGES=new Set\(\[([^\]]+)\]\)", shell_js)
        self.assertIsNotNone(m)
        pages = set(re.findall(r"'([^']+)'", m.group(1)))
        for p in ("ofz", "arb", "dgap", "rot", "dbx", "mm", "crp", "mic"):
            self.assertIn(p, pages)

    def test_bug_ui03_no_emoji_and_ru_terms(self):
        import glob
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        em_pat = re.compile(r"[\U0001F300-\U0001FAFF]")
        hits = []
        for p in sorted(glob.glob(os.path.join(root, "src/web/**/*"), recursive=True)):
            if not p.endswith((".js", ".html", ".css")):
                continue
            txt = open(p, encoding="utf-8").read()
            if em_pat.search(txt):
                hits.append(os.path.relpath(p, root))
        taxopt = open(os.path.join(root, "src/py/13x5_taxopt.py"), encoding="utf-8").read()
        if em_pat.search(taxopt) or "\U0001f6e1" in taxopt:
            hits.append("src/py/13x5_taxopt.py")
        self.assertEqual(hits, [], f"Найдены эмодзи в UI: {hits}")

        for rel, bad_terms in (
            ("src/web/js/14_scr.js", ["'Scatter'", "'CY, %'", "'MacDur, лет'"]),
            ("src/web/js/65_delight.js", ["Scatter"]),
            ("src/web/js/60_pm.js", ["Trade Post-Mortem", "Win Rate", "Profit Factor", "cashflow-matched"]),
        ):
            txt = open(os.path.join(root, rel), encoding="utf-8").read()
            for term in bad_terms:
                self.assertNotIn(term, txt, f"{term} найден в {rel}")

    def test_bug_ui04_local_iso(self):
        import glob
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        core_js = open(os.path.join(root, "src/web/js/01_core.js"), encoding="utf-8").read()
        self.assertIn("localIso", core_js)
        self.assertIn("getFullYear()", core_js)
        bad = []
        for p in sorted(glob.glob(os.path.join(root, "src/web/js/*.js"))):
            txt = open(p, encoding="utf-8").read()
            if "toISOString().slice(0,10)" in txt or "toISOString().slice(0, 10)" in txt:
                bad.append(os.path.basename(p))
        self.assertEqual(bad, [], f"Найдено UTC toISOString().slice(0,10) в: {bad}")

    def test_bug_ui05_misc_fixes(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        crp = open(os.path.join(root, "src/web/js/53_crp.js"), encoding="utf-8").read()
        self.assertNotIn("window.scrollTo(0,0)", crp)
        self.assertIn("scrollTop=0", crp)

        pm = open(os.path.join(root, "src/web/js/60_pm.js"), encoding="utf-8").read()
        self.assertGreaterEqual(pm.count('id="pm-r"'), 2)

        rt = open(os.path.join(root, "src/web/js/11_ratings.js"), encoding="utf-8").read()
        self.assertIn("i<0?'нет рейтинга'", rt)

        iss = open(os.path.join(root, "src/web/js/36_issuers.js"), encoding="utf-8").read()
        self.assertNotIn("r.rating?RSC.indexOf(r.rating):null", iss)

        bc = open(os.path.join(root, "src/py/13a_bondcard.py"), encoding="utf-8").read()
        self.assertNotIn('.get("NAME")', bc)


class TestCurToRub(unittest.TestCase):
    def test_cur_to_rub_variants(self):
        self.assertIsNone(M.cur_to_rub(None, "usd", {"usd": 90.0}))
        self.assertEqual(M.cur_to_rub(100, "rub", {"usd": 90.0}), 100.0)
        self.assertEqual(M.cur_to_rub(100, "SUR", {"usd": 90.0}), 100.0)
        self.assertEqual(M.cur_to_rub(100, None, {"usd": 90.0}), 100.0)
        self.assertAlmostEqual(M.cur_to_rub(10, "USD", {"usd": 92.5}), 925.0)
        self.assertAlmostEqual(M.cur_to_rub(10, "cny", {"CNY": 12.5}), 125.0)
        self.assertEqual(M.cur_to_rub(50, "eur", {}), 50.0)
        self.assertIsNone(M.cur_to_rub(50, "eur", {}, default=None))


def _check_js_delimiters(code):
    """Verify balanced (), [], {} across JS code, skipping strings, templates, comments, and regexes."""
    stack, tpl_brace_stack = [], []
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = {v: k for k, v in pairs.items()}
    i, n, line, prev_tok = 0, len(code), 1, ""
    regex_prev = frozenset((
        "", "(", "[", "{", ",", ";", ":", "=", "!", "&", "|", "?", "+", "-", "*", "%", "^", "~", "<", ">",
        "return", "case", "throw", "typeof", "void", "delete", "in", "of", "else",
    ))

    def skip_line_comment(pos):
        while pos < n and code[pos] != "\n":
            pos += 1
        return pos

    def skip_block_comment(pos):
        nonlocal line
        pos += 2
        while pos < n - 1 and not (code[pos] == "*" and code[pos + 1] == "/"):
            if code[pos] == "\n":
                line += 1
            pos += 1
        return pos + 2

    def skip_string(pos, quote):
        nonlocal line
        pos += 1
        while pos < n:
            ch = code[pos]
            if ch == "\\":
                pos += 2
                continue
            if ch == "\n":
                line += 1
            if ch == quote:
                return pos + 1
            pos += 1
        raise AssertionError(f"Unclosed string {quote} at line {line}")

    def scan_template(pos):
        nonlocal line
        pos += 1
        while pos < n:
            ch = code[pos]
            if ch == "\\":
                pos += 2
                continue
            if ch == "\n":
                line += 1
            if ch == "`":
                return pos + 1
            if ch == "$" and pos + 1 < n and code[pos + 1] == "{":
                stack.append(("{", line))
                tpl_brace_stack.append(len(stack))
                return pos + 2
            pos += 1
        raise AssertionError(f"Unclosed template literal at line {line}")

    def skip_regex(pos):
        pos += 1
        in_class = False
        while pos < n:
            ch = code[pos]
            if ch == "\\":
                pos += 2
                continue
            if ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
            elif ch == "/" and not in_class:
                pos += 1
                while pos < n and code[pos].isalpha():
                    pos += 1
                return pos
            elif ch == "\n":
                raise AssertionError(f"Unclosed regex at line {line}")
            pos += 1
        raise AssertionError(f"Unclosed regex at line {line}")

    while i < n:
        ch = code[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            if code[i + 1] == "/":
                i = skip_line_comment(i)
                continue
            if code[i + 1] == "*":
                i = skip_block_comment(i)
                continue
            if prev_tok in regex_prev:
                i = skip_regex(i)
                prev_tok = "regex"
                continue
        if ch in ('"', "'"):
            i = skip_string(i, ch)
            prev_tok = "str"
            continue
        if ch == "`":
            i = scan_template(i)
            prev_tok = "`"
            continue
        if ch in pairs:
            stack.append((ch, line))
            prev_tok = ch
            i += 1
            continue
        if ch in closing:
            if not stack or stack[-1][0] != closing[ch]:
                raise AssertionError(f"Mismatched {ch} at line {line}, stack={stack[-3:]}")
            stack.pop()
            if ch == "}" and tpl_brace_stack and len(stack) == tpl_brace_stack[-1] - 1:
                tpl_brace_stack.pop()
                i = scan_template(i)
                prev_tok = "`"
                continue
            prev_tok = ch
            i += 1
            continue
        if ch.isalpha() or ch in "_$":
            j = i + 1
            while j < n and (code[j].isalnum() or code[j] in "_$"):
                j += 1
            prev_tok = code[i:j]
            i = j
            continue
        if ch.isdigit():
            j = i + 1
            while j < n and (code[j].isalnum() or code[j] in "._"):
                j += 1
            prev_tok = "num"
            i = j
            continue
        prev_tok = ch
        i += 1
    if stack:
        raise AssertionError(f"Unclosed delimiters: {stack[-5:]}")


class TestJsSmoke(unittest.TestCase):
    def test_js_concat_delimiters_and_symbols(self):
        import glob
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        js_files = sorted(glob.glob(os.path.join(root, "src/web/js/*.js")))
        self.assertGreater(len(js_files), 60)
        names = [os.path.basename(p) for p in js_files]
        for expected in ("21_set.js", "21a_set_parts.js", "21b_set_ui.js", "33_calc.js", "33a_calc_ui.js"):
            self.assertIn(expected, names)
        self.assertLess(names.index("21_set.js"), names.index("21a_set_parts.js"))
        self.assertLess(names.index("21a_set_parts.js"), names.index("21b_set_ui.js"))
        self.assertLess(names.index("33_calc.js"), names.index("33a_calc_ui.js"))

        joined = "\n".join(open(p, encoding="utf-8").read() for p in js_files)
        _check_js_delimiters(joined)

        for sym in ("function renderSettings", "function pCalc", "function bindCalc", "function clNdfl", "function clSim",
                    "PRO_FEATURES", "PRO_PAGES", "function crowdInviteHtml"):
            self.assertIn(sym, joined, f"Missing JS symbol: {sym}")

        for route in ("/api/calc/goal", "/api/config", "/api/crowd/status", "/api/flows_instruments"):
            self.assertIn(route, joined, f"Missing JS API route reference: {route}")

        for dead_route in ("/api/crp/batch/status", "/api/disclosure", "/api/flows_instrument'"):
            self.assertNotIn(dead_route, joined, f"Dead route still referenced in JS: {dead_route}")

        emoji_rx = re.compile(r"[\U0001F300-\U0001FAFF]")
        self.assertEqual(emoji_rx.findall(joined), [], "Color emojis found in src/web/js/*.js")


class TestFrontendBugfixes(unittest.TestCase):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _read(self, rel):
        with open(os.path.join(self.ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_bug1_no_returnemptyHint(self):
        import glob
        import re
        for p in glob.glob(os.path.join(self.ROOT, "src/web/js/*.js")):
            txt = open(p, encoding="utf-8").read()
            self.assertIsNone(re.search(r"\breturnemptyHint\s*\(", txt), f"returnemptyHint in {p}")
        for rel in ("src/web/js/09_ret.js", "src/web/js/12_bonds.js", "src/web/js/25_reb.js"):
            self.assertIn("return emptyHint(", self._read(rel))

    def test_bug2_no_undefined_css_vars(self):
        import glob
        import re
        for ext in ("src/web/js/*.js", "src/web/css/*.css"):
            for p in glob.glob(os.path.join(self.ROOT, ext)):
                txt = open(p, encoding="utf-8").read()
                self.assertIsNone(re.search(r"var\(--(?:bg2|text)\)", txt), f"Undefined CSS var in {p}")
        self.assertIn("var(--card2)", self._read("src/web/js/08_dash.js"))
        self.assertIn("var(--card2)", self._read("src/web/js/12_bonds.js"))
        self.assertIn("var(--tx)", self._read("src/web/css/39_txo.css"))

    def test_bug3_print_css_and_tax_decl_breaks(self):
        pcss = self._read("src/web/css/08_print.css")
        for v in ("--bg:", "--card:", "--card2:", "--tx:", "--tx2:", "--mu:", "--line:", "--line2:"):
            self.assertIn(v, pcss, f"Missing print theme reset {v}")
        self.assertIn("#tkr", pcss)
        self.assertNotIn("position:fixed", pcss)
        self.assertIn("tx-decl-card", pcss)
        self.assertIn('class="tkr noprint" id="tkr"', self._read("src/web/shell.html"))
        self.assertIn(".tx-decl-card{break-inside:auto}", self._read("src/web/css/20_tax.css"))
        self.assertIn('class="card tx-decl-card"', self._read("src/web/js/19_tax.js"))

    def test_bug6_boot_waits_for_late_pages(self):
        boot = self._read("src/web/js/26_changelog_boot.js")
        self.assertIn("async function boot()", boot)
        idx_await = boot.index("await Promise.resolve()")
        idx_check = boot.index("if(!PAGES.some(")
        self.assertLess(idx_await, idx_check)

    def test_bug7_9_10_pay_and_txo(self):
        pay = self._read("src/web/js/16_pay.js")
        self.assertIn("PAY_J.acc===acc", pay)
        self.assertIn("CF36.acc===acc", pay)
        self.assertIn("if(S.account!==acc){PAY_J.st='idle'", pay)
        self.assertIn("if(S.account!==acc){CF36.st='idle'", pay)
        self.assertNotIn("if(tab==='cf36'){CF36.open=true;", pay)
        self.assertIn("mr.by.redemption!=null?mr.by.redemption:(mr.total||0)", pay)

        txo = self._read("src/web/js/54_txo.js")
        self.assertIn("S.txo.hBusyAcc===acc", txo)
        self.assertIn("if(S.account!==acc){if(S.page==='txo')renderSoon();return}", txo)

    def test_bug12_settings_mode_badge_and_hit_selector(self):
        sui = self._read("src/web/js/21b_set_ui.js")
        self.assertGreaterEqual(sui.count("updateModeBadge("), 3)
        scss = self._read("src/web/css/56_settings_v2.css")
        self.assertIn(".st-row.st-hit", scss)


if __name__ == "__main__":
    unittest.main()
