"""Разбор реальных сообщений e-disclosure.azipi.ru (tests/fixtures/disclosure/real): инварианты и точные значения."""
import glob
import os
import re
import unittest

from tests._load import load

T = load()
REAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "disclosure", "real")
FILES = sorted(glob.glob(os.path.join(REAL, "azipi_*.txt")))
KINDS = {"coupon_paid", "coupon_declared", "default", "buyback_result", "placement_result", "other"}
ISIN = re.compile(r"^(?:RU|SU)[0-9A-Z]{9}[0-9]$")


def ext(code):
    meta, text = T.dc_load_fixture(os.path.join(REAL, "azipi_%s.txt" % code))
    return T.dc_extract(text, meta.get("title", ""), meta)


def fact(code):
    r = ext(code)
    assert r["facts"], code
    return r["facts"][0]


class Invariants(unittest.TestCase):
    def test_fixtures_present(self):
        self.assertGreaterEqual(len(FILES), 40)

    def test_version(self):
        self.assertEqual(T.DC_PARSER_VERSION, "3")

    def test_all(self):
        paid = good = 0
        for p in FILES:
            meta, text = T.dc_load_fixture(p)
            r = T.dc_extract(text, meta.get("title", ""), meta)
            name = os.path.basename(p)
            with self.subTest(name):
                self.assertIn(r["kind"], KINDS)
                self.assertTrue(r["facts"], name)
                for f in r["facts"]:
                    self.assertRegex(f["isin"], ISIN)
                    if r["kind"] == "coupon_paid":
                        q = f["qty_out"]
                        self.assertTrue((isinstance(q, int) and q > 0) or r["warnings"], name)
                        self.assertIn(f["currency"], ("RUB", "CNY", "USD", "EUR"))
            if r["kind"] == "coupon_paid":
                paid += 1
                good += r["facts"][0]["conf"] >= 0.8
        self.assertGreaterEqual(paid, 25)
        self.assertGreaterEqual(good, 0.9 * paid)

    def test_paid_kinds(self):
        for p in FILES:
            meta, text = T.dc_load_fixture(p)
            want = "coupon_paid" if "Выплаченные" in meta["title"] else "coupon_declared" if "Начисленные" in meta["title"] else "default"
            self.assertEqual(T.dc_extract(text, meta["title"], meta)["kind"], want, p)


class Named(unittest.TestCase):
    def test_percent_before_amount(self):          # «15,85%, 13,03 руб. (...) на одну»
        f = fact("4608464")
        self.assertEqual((f["per_bond"], f["rate"], f["total"], f["qty"]), (13.03, 15.85, 260600000.0, 20000000))
        self.assertEqual((f["conf"], f["coupon_no"], f["payment"], f["currency"]), (1.0, 13, "coupon", "RUB"))
        g = fact("4608455")
        self.assertEqual((g["per_bond"], g["rate"], g["qty"]), (13.16, 15.49, 20000000))

    def test_value_on_next_line(self):             # номера пунктов («2.4», «023», «ПБО-02-07») — не значения
        f = fact("4608360")
        self.assertEqual((f["total"], f["per_bond"], f["qty"], f["coupon_no"]), (19728000.0, 16.44, 1200000, 23))
        self.assertEqual(f["conf"], 1.0)

    def test_label_with_dot(self):                 # 4608310: «...эмитента. Размер купона ...: 0,10 руб.»
        f = fact("4608310")
        self.assertEqual(f["payment"], "coupon+redemption")
        self.assertEqual((f["coupon_per_bond"], f["face_per_bond"], f["per_bond"]), (0.10, 1000.0, 0.10))
        self.assertAlmostEqual(f["per_bond_total"], 1000.10)
        self.assertEqual((f["total"], f["qty"], f["conf"]), (273136310.9, 273109, 1.0))
        self.assertEqual(f["period_from"], "2025-11-14")
        self.assertEqual(f["period_to"], "2026-11-13")

    def test_shifted_numbering(self):              # 2.2 = регистрационный номер, категория в 2.3
        f = fact("4608464")
        self.assertEqual((f["payment"], f["period_from"], f["period_to"]), ("coupon", "2026-10-16", "2026-11-15"))
        self.assertEqual(f["isin"], "RU000A10D541")

    def test_combined_payment(self):
        f = fact("4608313")
        self.assertEqual(f["payment"], "coupon+redemption")
        self.assertEqual((f["coupon_per_bond"], f["face_per_bond"]), (50.16, 1000.0))
        self.assertAlmostEqual(f["per_bond_total"], 1050.16)
        self.assertEqual((f["total"], f["qty"], f["conf"]), (10501600000.0, 10000000, 1.0))
        g = fact("4608189")
        self.assertEqual(g["payment"], "coupon+amortization")
        self.assertEqual((g["coupon_per_bond"], g["face_per_bond"], g["total"], g["qty"]), (9.86, 20.0, 14930000.0, 500000))
        self.assertEqual(g["conf"], 1.0)
        h = fact("4608156")
        self.assertEqual((h["payment"], h["coupon_per_bond"], h["face_per_bond"], h["qty"]), ("coupon+amortization", 0.53, 43.2, 150000))

    def test_foreign_currency(self):
        f = fact("4608287")
        self.assertEqual(f["currency"], "CNY")
        self.assertEqual((f["total"], f["per_bond"], f["per_bond_rub"], f["qty"]), (18198223.5, 6.45, 79.43, 3000000))
        self.assertEqual(f["total_rub"], 14183815.10)
        self.assertEqual(f["conf"], 1.0)                # часть бумаг получила рубли: 2 821 4xx + 178 5xx = 3 000 000
        g = fact("4608181")
        self.assertEqual((g["currency"], g["per_bond"], g["per_bond_rub"], g["qty"]), ("CNY", 5.75, 71.31, 4000000))
        r = fact("4608466")                              # рубли, юани — лишь справочный эквивалент
        self.assertEqual((r["currency"], r["per_bond"], r["total"], r["qty"]), ("RUB", 109.36, 54680000.0, 500000))

    def test_series_code_not_qty(self):             # «облигации серии 002P-03 в количестве 7 766 326 штук»
        f = fact("4608225")
        self.assertEqual((f["qty"], f["total"], f["per_bond"], f["conf"]), (7766326, 108495574.22, 13.97, 1.0))

    def test_explicit_qty_keeps_conf(self):
        t = ("Выплаченные доходы\n2.1. Идентификационные признаки: RU000A0TEST1\n2.2. Категория выплат:\nкупонный доход\n"
             "2.4. Общий размер выплаченных доходов:\n1 000,00 руб.\n2.5. Размер выплаченных доходов в расчете на одну ценную бумагу:\n10,00 руб.\n"
             "2.6. Общее количество ценных бумаг:\n150 штук\n")
        r = T.dc_extract(t, "Выплаченные доходы")
        self.assertEqual(r["facts"][0]["conf"], 0.8)
        self.assertIn("суммы не сходятся", r["warnings"])

    def test_declared_and_default(self):
        self.assertEqual(fact("4608180")["per_bond"], 82.27)       # не «12» из «12-й купонный период»
        self.assertEqual(fact("4608180")["qty_out"], 3000000)
        self.assertEqual((fact("4608450")["total"], fact("4608450")["per_bond"]), (1684000000.0, 33.68))
        self.assertEqual(fact("4608213")["qty_out"], 10000000)
        d = fact("4608498")
        self.assertEqual((d["amount"], d["per_bond"], d["qty"], d["status"]), (24660000.0, 24.66, 1000000, "default"))
        self.assertEqual(fact("4608339")["amount"], 10170000.0)


if __name__ == "__main__":
    unittest.main()
