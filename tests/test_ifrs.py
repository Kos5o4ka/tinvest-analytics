"""Тесты МСФО эмитентов (офлайн, синтетические данные). Живая проверка: TINVEST_LIVE=1 python3 -m unittest tests.test_ifrs -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

m = _load.load()


def _tr(field, vals):
    cells = "".join("<td>%s\t</td>" % v for v in vals[:-1]) + '<td class="ltm_spc">&nbsp;</td><td>%s</td>' % vals[-1]
    return '<tr field="%s"><th>x</th><th></th><td class="chartrow"><a class="charticon2"></a></td>%s</tr>' % (field, cells)


def page(rows, labels=("2023", "2024", "2025")):
    hdr = ('<tr class="header_row"><th colspan="2">T<span>smart-lab.ru</span></th><td class="chartrow">&nbsp;</td>'
           + "".join("<td ><strong>%s</strong></td>" % y for y in labels)
           + '<td class="ltm_spc">&nbsp;</td><td class="editrow"><strong>LTM</strong><span>?</span></td></tr>')
    return "<table>" + hdr + "".join(_tr(k, v) for k, v in rows.items()) + "</table>"


# 3 года + LTM, значения в млрд ₽
CORP = {
    "date": ["01.03.2024", "01.03.2025", "01.03.2026", "01.09.2026"],
    "currency": ["RUB"] * 4,
    "revenue": ["1 000", "1 100", "1 200", "1 250"],
    "operating_income": ["200", "220", "-5.0", "260"],
    "ebitda": ["300", "330", "360", "380"],
    "net_income": ["100", "110", "120", "125"],
    "interest_expenses": ["50", "55", "60", ""],
    "debt": ["900", "950", "1 000", "1 000"],
    "cash": ["100", "100", "150", "150"],
    "assets": ["3 000", "3 200", "3 400", "3 500"],
    "net_assets": ["1 000", "1 100", "1 200", "1 250"],
    "ocf": ["250", "260", "270", "280"],
    "capex": ["200", "210", "220", "225"],
    "roe": ["10.0%", "10.5%", "10%", "10%"],
}
BANK = {
    "date": ["01.03.2024", "01.03.2025", "01.03.2026", "01.09.2026"],
    "currency": ["RUB"] * 4,
    "net_operating_income": ["100", "110", "125", "130"],
    "net_income": ["30", "35", "40", "42"],
    "bank_assets": ["1 000", "1 100", "1 200", "1 250"],
    "capital": ["110", "120", "130", "135"],
    "roe": ["20%", "21%", "22%", "22%"],
    "cost_of_risk_ratio": ["1.0%", "1.2%", "0.9%", "0.9%"],
    "share_of_non_performing_loans": ["3.0%", "3.2%", "3.1%", "3.0%"],
    "total_capital_adequacy_ratio": ["14.0%", "14.1%", "14.2%", "14.2%"],
}


class Num(unittest.TestCase):
    def test_parse(self):
        n = m._ifrs_num
        self.assertEqual(n("11 674"), 11674.0)
        self.assertEqual(n("11 674\t"), 11674.0)
        self.assertEqual(n("-364.0"), -364.0)
        self.assertAlmostEqual(n("31.4%"), 0.314)
        self.assertEqual(n("2,5"), 2.5)
        for bad in ("", "  ", "&nbsp;", "—", "abc", None):
            self.assertIsNone(n(bad))


class Parse(unittest.TestCase):
    def test_structure(self):
        p = m.ifrs_parse(page(CORP))
        self.assertEqual(p["labels"], ["2023", "2024", "2025", "LTM"])
        self.assertEqual(p["rows"]["revenue"][0], "1 000")
        self.assertEqual(p["rows"]["revenue"][3], "1 250")

    def test_garbage(self):
        self.assertIsNone(m.ifrs_parse(""))
        self.assertIsNone(m.ifrs_parse("<html>captcha</html>"))
        self.assertIsNone(m.ifrs_parse("<table><tr field=\"a\"><td>1</td></tr></table>"))

    def test_build_corp(self):
        f = m.ifrs_build(m.ifrs_parse(page(CORP)), "TEST")
        self.assertEqual(f["status"], "ok")
        self.assertFalse(f["bank"])
        self.assertEqual([y["y"] for y in f["years"]], [2023, 2024, 2025])
        y = f["years"][-1]
        self.assertEqual(y["rev"], 1200000.0)                     # млн ₽
        self.assertAlmostEqual(y["nd_ebitda"], 850.0 / 360.0)
        self.assertAlmostEqual(y["cover"], 360.0 / 60.0)
        self.assertAlmostEqual(y["fcf"], 50000.0)
        self.assertAlmostEqual(y["growth"], 1200 / 1100.0 - 1)
        self.assertIsNotNone(f["ltm"])
        self.assertEqual(f["as_of"], "01.09.2026")

    def test_not_rub(self):
        rows = dict(CORP, currency=["USD"] * 4)
        self.assertEqual(m.ifrs_build(m.ifrs_parse(page(rows)), "X")["status"], "notrub")

    def test_empty_data(self):
        rows = {"currency": ["RUB"] * 4, "revenue": [""] * 4, "ebitda": [""] * 4}
        self.assertEqual(m.ifrs_build(m.ifrs_parse(page(rows)), "X")["status"], "nodata")

    def test_bank(self):
        f = m.ifrs_build(m.ifrs_parse(page(BANK)), "BNK")
        self.assertTrue(f["bank"])
        self.assertAlmostEqual(f["years"][-1]["eq_ratio"], 0.108333, places=4)


def _fin(**over):
    base = {"y": 2025, "rev": 1000.0, "ebitda": 300.0, "net": 100.0, "interest": 50.0, "debt": 800.0, "cash": 100.0, "net_debt": 700.0, "assets": 3000.0,
            "equity": 1000.0, "ocf": 250.0, "capex": 200.0, "fcf": 50.0, "growth": 0.05}
    base.update(over)
    e, nd, it = base["ebitda"], base["net_debt"], base["interest"]
    base["nd_ebitda"] = nd / e if (nd is not None and e and e > 0) else None
    base["cover"] = e / it if (it and it > 0 and e is not None) else None
    base["margin_ebitda"] = e / base["rev"] if base["rev"] else None
    base["eq_ratio"] = base["equity"] / base["assets"]
    return {"status": "ok", "ticker": "T", "bank": False, "years": [dict(base, y=base["y"] - 1, growth=None), base], "ltm": None, "as_of": "01.03.2026"}


class Score(unittest.TestCase):
    def setUp(self):
        self.y = m.date.today().year - 1

    def test_strong(self):
        s = m.iss_score_ifrs(_fin(y=self.y, net_debt=200.0, interest=20.0, ebitda=400.0, equity=1500.0, growth=0.1))
        self.assertTrue(s["ok"])
        self.assertGreaterEqual(s["score"], 90)
        self.assertEqual(s["basis"], "ifrs")

    def test_net_cash(self):
        s = m.iss_score_ifrs(_fin(y=self.y, net_debt=-50.0))
        lev = [p for p in s["parts"] if p["id"] == "lev"][0]
        self.assertEqual(lev["pts"], lev["max"])

    def test_negative_ebitda_with_debt(self):
        s = m.iss_score_ifrs(_fin(y=self.y, ebitda=-10.0))
        self.assertEqual([p for p in s["parts"] if p["id"] == "lev"][0]["pts"], 0)
        self.assertEqual([p for p in s["parts"] if p["id"] == "cover"][0]["pts"], 0)

    def test_penalties(self):
        s = m.iss_score_ifrs(_fin(y=self.y, net=-5.0, equity=-100.0))
        names = [p["name"] for p in s["penalties"]]
        self.assertIn("Убыток по итогам года", names)
        self.assertIn("Отрицательный капитал", names)
        self.assertIn("Убыток второй год подряд", names)       # предыдущий год в _fin тоже с net=-5

    def test_leasing_mode(self):
        f = _fin(y=self.y, net_debt=4000.0, equity=1000.0, growth=0.1)
        s = m.iss_score_ifrs(f, is_fin=True)
        ids = [p["id"] for p in s["parts"]]
        self.assertIn("lev", ids)
        self.assertNotIn("cover", ids)
        self.assertNotIn("fcf", ids)
        self.assertTrue(s["fin_mode"])

    def test_stale(self):
        s = m.iss_score_ifrs(_fin(y=2019))
        self.assertTrue(any("старше" in p["name"] for p in s["penalties"]))

    def test_no_data(self):
        self.assertFalse(m.iss_score_ifrs({"status": "nodata", "years": []})["ok"])
        self.assertFalse(m.iss_score_ifrs(None)["ok"])

    def test_bank_ok(self):
        f = m.ifrs_build(m.ifrs_parse(page(BANK)), "BNK")
        s = m.iss_score_ifrs(f)
        self.assertTrue(s["ok"])
        self.assertTrue(s["bank"])
        self.assertGreater(s["score"], 50)

    def test_bank_too_few(self):
        rows = {"currency": ["RUB"] * 4, "net_operating_income": ["100", "110", "125", "130"], "net_income": ["30", "35", "40", "42"]}
        f = m.ifrs_build(m.ifrs_parse(page(rows)), "BNK")
        s = m.iss_score_ifrs(f)
        self.assertFalse(s["ok"])
        self.assertTrue(s["reason"])


class Mapping(unittest.TestCase):
    def test_table(self):
        ts = [v[0] for v in m.IFRS_BY_INN.values()]
        for inn, (t, g) in m.IFRS_BY_INN.items():
            self.assertTrue(inn.isdigit() and len(inn) in (10, 12), inn)
            self.assertEqual(t, t.upper())
            self.assertTrue(g)
        self.assertEqual(len(m.IFRS_BY_INN), len(set(m.IFRS_BY_INN)))
        for rx, t, g in m.IFRS_BY_NAME:
            self.assertEqual(t, t.upper())
            m.re.compile(rx)

    def test_by_inn_and_name(self):
        em = {"emitter_id": None, "inn": "7726588547", "title": "ООО \"Газпром капитал\""}
        r = m.ifrs_ticker_for("RU000A000000", em)
        self.assertEqual(r["ticker"], "GAZP")
        self.assertEqual(r["kind"], "group")
        r = m.ifrs_ticker_for("RU000A000000", {"emitter_id": None, "inn": "1", "title": "ООО Корпоративный центр ИКС 5"})
        self.assertEqual(r["ticker"], "X5")
        self.assertIsNone(m.ifrs_ticker_for("RU000A000000", {"emitter_id": None, "inn": "1", "title": "ООО Ромашка"}))


@unittest.skipUnless(os.environ.get("TINVEST_LIVE"), "нужна сеть: TINVEST_LIVE=1")
class Live(unittest.TestCase):
    def test_gazp(self):
        f = m.ifrs_fin("GAZP")
        self.assertEqual(f["status"], "ok")
        self.assertTrue(m.iss_score_ifrs(f)["ok"])


if __name__ == "__main__":
    unittest.main()
