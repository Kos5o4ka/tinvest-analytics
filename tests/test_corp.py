"""Устойчивость эмитентов: модели Савицкой и Сайфуллина–Кадыкова, расширенный долг, риск размытия (без сети)."""
import unittest

from tests._load import load

M = load()

CUR = {"1100": 400.0, "1200": 600.0, "1300": 500.0, "1500": 300.0, "1600": 1000.0, "2110": 2000.0, "2200": 200.0, "2400": 100.0,
       "1410": 100.0, "1510": 50.0, "1450": 30.0, "1550": 10.0, "1540": 5.0}
PREV = {"1600": 800.0}


class Models(unittest.TestCase):
    def test_savitskaya(self):
        # X1=(500-400)/600, X2=600/400, X3=2000/900, X4=100/1000, X5=500/1000
        r = M.crp_savitskaya(CUR, PREV)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["x"]["X1"], 1 / 6.0, 6)
        self.assertAlmostEqual(r["x"]["X3"], 2000 / 900.0, 6)
        self.assertAlmostEqual(r["z"], 25.552944, 4)
        self.assertEqual(r["key"], "ok")

    def test_savitskaya_high_risk(self):
        c = dict(CUR, **{"1300": -100.0, "1200": 100.0, "1100": 900.0, "2400": -300.0})
        r = M.crp_savitskaya(c, PREV)
        self.assertLess(r["z"], 8)
        self.assertEqual(r["key"], "high")

    def test_saifullin(self):
        # K1=1/6, K2=2, K3=2000/900, K4=0.1, K5=0.2
        r = M.crp_saifullin(CUR, PREV)
        self.assertAlmostEqual(r["r"], 0.956111, 5)
        self.assertEqual(r["key"], "high")
        self.assertIn("R < 1", r["zone"])

    def test_no_prev_uses_current_assets(self):
        r = M.crp_saifullin(CUR, None)
        self.assertAlmostEqual(r["x"]["K3"], 2.0, 6)

    def test_missing_lines(self):
        c = dict(CUR)
        del c["1200"]
        self.assertFalse(M.crp_savitskaya(c, PREV)["ok"])
        self.assertFalse(M.crp_saifullin(c, PREV)["ok"])


class Financial(unittest.TestCase):
    def test_fin_excluded(self):
        rows = M.crp_analyze_years({2023: PREV, 2024: CUR}, True)
        self.assertTrue(rows[-1]["sav"]["na"] and rows[-1]["sk"]["na"])
        self.assertNotIn("z", rows[-1]["sav"])

    def test_nonfin_calculated(self):
        rows = M.crp_analyze_years({2023: PREV, 2024: CUR}, False)
        self.assertTrue(rows[-1]["sav"]["ok"])

    def test_is_fin(self):
        self.assertTrue(M.crp_is_fin("ООО «Эксперт-Лизинг»"))
        self.assertTrue(M.crp_is_fin("Банк Тест"))
        self.assertFalse(M.crp_is_fin("ПАО «Заводы»"))


class ExtDebt(unittest.TestCase):
    def test_values(self):
        d = M.crp_ext_debt(CUR)
        self.assertEqual((d["reported"], d["extra"], d["extended"]), (150.0, 45.0, 195.0))
        self.assertAlmostEqual(d["uplift"], 0.3)
        self.assertTrue(d["flag"])
        self.assertAlmostEqual(d["ext_ebit"], 195 / 200.0)
        self.assertAlmostEqual(d["ext_eq"], 195 / 500.0)

    def test_flag_threshold(self):
        base = {"1410": 100.0, "1510": 50.0}
        self.assertTrue(M.crp_ext_debt(dict(base, **{"1450": 37.5}))["flag"])      # ровно +25 %
        self.assertFalse(M.crp_ext_debt(dict(base, **{"1450": 37.0}))["flag"])
        self.assertFalse(M.crp_ext_debt(base)["flag"])

    def test_no_data(self):
        self.assertFalse(M.crp_ext_debt({"2110": 5.0})["ok"])


class Dilution(unittest.TestCase):
    def test_matcher(self):
        m = M.crp_dilution_match
        self.assertIn("spo", m("Решение о размещении дополнительных акций (допэмиссия): дополнительный выпуск акций"))
        self.assertIn("convert", m("Размещение конвертируемых облигаций"))
        self.assertIn("option", m("Утверждена опционная программа для менеджмента"))
        self.assertIn("buyback", m("Совет директоров одобрил выкуп акций (buyback)"))
        self.assertIn("lockup", m("Установлен lock-up на 180 дней"))
        self.assertEqual(m("Выплата купонного дохода по облигациям"), [])

    def test_scan_sorted(self):
        items = [{"title": "выкуп акций", "date": "2024-01-01", "url": "u1"}, {"title": "прочее"},
                 {"title": "SPO эмитента", "date": "2025-03-01", "url": "u2"}]
        r = M.crp_dilution_scan(items)
        self.assertEqual([x["url"] for x in r], ["u2", "u1"])


class Events(unittest.TestCase):
    def test_disc_facts_shape(self):
        facts = [{"doc_id": 1, "title": "Сообщение о дополнительном выпуске акций", "published": "2025-02-01T10:00:00", "url": "http://x/1",
                  "isin": "RU000A0", "kind": "other", "conf": 0.0, "data": {}},
                 {"doc_id": 1, "title": "Сообщение о дополнительном выпуске акций", "published": "2025-02-01T10:00:00", "url": "http://x/1", "kind": "other"},
                 {"doc_id": 2, "title": "Выплата купона", "published": "2025-01-01", "url": "http://x/2", "kind": "coupon_paid"}]
        old = M.disc_facts
        M.disc_facts = lambda isin=None, inn=None, kind=None: facts
        try:
            items, src = M.crp_events("RU000A0", "7700000000")
        finally:
            M.disc_facts = old
        self.assertEqual(len(items), 2)
        r = M.crp_dilution_scan(items)
        self.assertEqual([x["kind"] for x in r], ["spo"])
        self.assertEqual(r[0]["url"], "http://x/1")


if __name__ == "__main__":
    unittest.main()
