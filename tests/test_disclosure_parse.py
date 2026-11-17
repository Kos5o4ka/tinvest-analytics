"""Классификация и поля сообщений e-disclosure (714-П) на реальных фикстурах."""
import os
import unittest

from tests._load import load

T = load()
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "disclosure")


def ext(name):
    meta, text = T.dc_load_fixture(os.path.join(FIX, name + ".txt"))
    return T.dc_extract(text, meta.get("title", ""), meta)


class Parsers(unittest.TestCase):
    def test_number(self):
        n = T.dc_parse_number
        self.assertEqual(n("80 620 552,40 рублей"), 80620552.40)
        self.assertEqual(n("5 425 340."), 5425340)
        self.assertEqual(n("1 000 000 (Один миллион) штук"), 1000000)
        self.assertEqual(n("ставка 7.35%"), 7.35)
        self.assertEqual(n("24 660 000,00 руб."), 24660000.0)
        self.assertIsNone(n("нет"))
        self.assertIsNone(n(None))

    def test_rub(self):
        r = T.dc_parse_rub
        self.assertAlmostEqual(r("18 (Восемнадцать) рублей 32 копейки, что"), 18.32, places=2)
        self.assertAlmostEqual(r("10 170 000 рублей 00 копеек"), 10170000.0, places=2)
        self.assertAlmostEqual(r("256 480 000   \n(Двести пятьдесят) рублей 00 копеек за период"), 256480000.0, places=2)
        self.assertAlmostEqual(r("14,86 рубля"), 14.86, places=2)
        self.assertAlmostEqual(r("20,14 (Двадцать рублей четырнадцать копеек)"), 20.14, places=2)
        self.assertAlmostEqual(r("5 рублей 7 копеек"), 5.07, places=2)

    def test_date(self):
        d = T.dc_parse_date
        self.assertEqual(d("16 ноября 2026 года"), "2026-11-16")
        self.assertEqual(d("«16» ноября 2026 года"), "2026-11-16")
        self.assertEqual(d("«27» ноября 2026 г."), "2026-11-27")
        self.assertEqual(d("«16»\tноября\t2026 г."), "2026-11-16")
        self.assertEqual(d("16.11.2026"), "2026-11-16")
        self.assertEqual(d("13.11.2026г."), "2026-11-13")
        self.assertEqual(d("1 мая 2027"), "2027-05-01")
        self.assertIsNone(d("31.02.2026"))
        self.assertIsNone(d("без даты"))

    def test_sections(self):
        s = T.dc_sections("шапка\n2.1. a\nb\n2.2\tc\n2.3 d\n18.32 рубля\n2.10.\te")
        self.assertEqual(s["2.1"], "a\nb")
        self.assertEqual(s["2.2"], "c")
        self.assertEqual(s["2.3"], "d\n18.32 рубля")
        self.assertEqual(s["2.10"], "e")
        self.assertEqual(T.dc_sections("2.5. x\n3. Подпись\n3.1. y")["2.5"], "x")

    def test_classify(self):
        c = T.dc_classify
        self.assertEqual(c("Выплаченные доходы или иные", ""), "coupon_paid")
        self.assertEqual(c("", "о начисленных (объявленных) доходах по ценным бумагам"), "coupon_declared")
        self.assertEqual(c("Неисполнение обязательств эмитента", ""), "default")
        self.assertEqual(c("Сообщение об итогах приобретения эмитентом облигаций", ""), "buyback_result")
        self.assertEqual(c("События (действия)", "назначение агента по приобретению"), "other")


class Fixtures(unittest.TestCase):
    def test_afks_paid(self):
        r = ext("coupon_paid_afks")
        self.assertEqual((r["kind"], r["inn"], r["event_date"]), ("coupon_paid", "7703104630", "2026-11-16"))
        self.assertEqual(r["code"], "3825735")
        self.assertEqual(len(r["facts"]), 1)
        f = r["facts"][0]
        self.assertEqual((f["isin"], f["payment"], f["qty"]), ("RU000A10B024", "coupon", 5425340))
        self.assertAlmostEqual(f["total"], 80620552.40, places=2)
        self.assertAlmostEqual(f["per_bond"], 14.86, places=2)
        self.assertTrue(f["checks"]["total_matches"])
        self.assertEqual(f["conf"], 1.0)
        self.assertEqual((f["period_from"], f["period_to"]), ("2026-10-14", "2026-11-14"))
        self.assertEqual(f["due_date"], "2026-11-16")
        self.assertEqual(f["paid_pct"], 100)
        self.assertEqual(r["warnings"], [])

    def test_denum_paid(self):
        r = ext("coupon_paid_denum")
        f = r["facts"][0]
        self.assertEqual((r["kind"], f["isin"], f["coupon_no"], f["qty"]), ("coupon_paid", "RU000A10CH37", 15, 200000))
        self.assertAlmostEqual(f["total"], 4028000.0, places=2)
        self.assertAlmostEqual(f["per_bond"], 20.14, places=2)
        self.assertAlmostEqual(f["rate"], 24.5, places=2)
        self.assertEqual(f["period_from"], "2026-10-15")
        self.assertEqual(f["paid_pct"], 100)
        self.assertEqual(f["conf"], 1.0)

    def test_mgkl_default(self):
        r = ext("default_coupon_mgkl")
        f = r["facts"][0]
        self.assertEqual((r["kind"], f["isin"], f["status"], f["obligation"], f["coupon_no"], f["qty"]),
                         ("default", "RU000A10ATC4", "default", "coupon", 21, 1000000))
        self.assertAlmostEqual(f["amount"], 24660000.0, places=2)
        self.assertAlmostEqual(f["per_bond"], 24.66, places=2)
        self.assertAlmostEqual(f["rate"], 30.0, places=2)
        self.assertEqual((f["due_date"], r["event_date"]), ("2026-10-29", "2026-11-13"))
        self.assertNotIn("Подпись", f["reason"])
        self.assertTrue(f["checks"]["total_matches"])

    def test_monopoly_techdefault(self):
        r = ext("techdefault_coupon_monopoly")
        f = r["facts"][0]
        self.assertEqual((r["kind"], r["inn"], f["isin"], f["status"], f["obligation"], f["coupon_no"]),
                         ("default", "7810766685", "RU000A10C5Z7", "technical", "coupon", 16))
        self.assertAlmostEqual(f["amount"], 10170000.0, places=2)
        self.assertEqual(f["due_date"], "2026-11-16")
        self.assertEqual(r["event_date"], f["due_date"])
        self.assertTrue(f["reason"])

    def test_buyback(self):
        r = ext("buyback_put_gazpromneft")
        f = r["facts"][0]
        self.assertEqual((r["kind"], f["isin"], f["qty_bought"], f["basis"], f["date"]),
                         ("buyback_result", "RU000A10DWN9", 231878, "put", "2026-11-13"))
        self.assertEqual(len(r["facts"]), 1)

    def test_kirovsky_formula(self):
        r = ext("coupon_set_formula_kirovsky")
        f = r["facts"][0]
        self.assertEqual((r["kind"], f["isin"], f["coupon_no"], f["base"], f["undetermined"]),
                         ("coupon_declared", "RU000A1014U9", 29, "refinancing", True))
        self.assertAlmostEqual(f["spread"], 5.0, places=2)
        self.assertEqual((f["period_from"], f["period_to"]), ("2026-11-25", "2027-02-24"))
        self.assertIsNotNone(f["put_note"])
        self.assertIn("Сn", f["formula"])
        self.assertIsNone(f["total"])

    def test_rosseti_declared(self):
        r = ext("coupon_declared_rosseti")
        f = r["facts"][0]
        self.assertEqual((r["kind"], r["inn"], f["isin"], f["coupon_no"]), ("coupon_declared", "4716016979", "RU000A0JUCA9", 53))
        self.assertAlmostEqual(f["total"], 256480000.0, places=2)
        self.assertAlmostEqual(f["per_bond"], 18.32, places=2)
        self.assertAlmostEqual(f["rate"], 7.35, places=2)
        self.assertEqual(f["qty_derived"], 14000000)
        self.assertTrue(f["checks"]["qty_integer"])
        self.assertEqual(f["due_date"], "2027-02-26")
        self.assertEqual((f["period_from"], f["period_to"]), ("2026-11-27", "2027-02-26"))
        self.assertFalse(f["undetermined"])

    def test_other_agent(self):
        r = ext("other_buyback_agent_afks")
        self.assertEqual(r["kind"], "other")
        for f in r["facts"]:
            self.assertEqual(f["conf"], 0)
            self.assertEqual(f["kind"], "other")


class Synthetic(unittest.TestCase):
    BASE = ("Выплаченные доходы\n1.4. ИНН: 1234567890\n1.7. Дата: 01.12.2026\n2.1. Признаки ценных бумаг: облигации ISIN RU000A0TEST1\n"
            "2.2. Категория выплат: проценты (купонный доход) по облигациям\n2.3. Период: с 01.11.2026 по 01.12.2026\n"
            "2.4. Общий размер выплаченных доходов: %s рублей\n2.5. Размер в расчете на одну ценную бумагу: %s рублей\n%s"
            "2.9. Дата, в которую обязанность должна быть исполнена: 01.12.2026\n2.10. Объем (в процентах): 100%%\n")

    def test_qty_derived(self):
        t = self.BASE % ("1 000,00", "10,00", "")
        f = T.dc_extract(t, "Выплаченные доходы")["facts"][0]
        self.assertIsNone(f["qty"])
        self.assertEqual((f["qty_derived"], f["qty_out"], f["conf"]), (100, 100, 0.8))

    def test_mismatch(self):
        t = self.BASE % ("1 000,00", "10,00", "2.6. Общее количество: 150 штук\n")
        f = T.dc_extract(t, "Выплаченные доходы")["facts"][0]
        self.assertEqual(f["qty"], 150)
        self.assertFalse(f["checks"]["total_matches"])
        self.assertEqual(f["conf"], 0.8)    # явное количество ценнее сверки сумм

    def test_multi_isin_and_partial(self):
        t = (self.BASE % ("1 000,00", "10,00", "2.6. Общее количество: 100 штук\n")).replace("RU000A0TEST1", "RU000A0TEST1 и SU26238RMFS4 и RU000A0TEST1")
        t = t.replace("100%", "50%")
        r = T.dc_extract(t, "Выплаченные доходы")
        self.assertEqual([f["isin"] for f in r["facts"]], ["RU000A0TEST1", "SU26238RMFS4"])
        self.assertEqual(len(r["warnings"]), 2)


if __name__ == "__main__":
    unittest.main()


class DefaultAge(unittest.TestCase):
    def test_overdue_without_word_becomes_default(self):
        m, t = T.dc_load_fixture(os.path.join(FIX, "techdefault_coupon_monopoly.txt"))
        t = t.replace("1.7. Дата наступления события (существенного факта), о котором составлено сообщение: 16.11.2026",
                      "1.7. Дата наступления события (существенного факта), о котором составлено сообщение: 04.12.2026")
        f = T.dc_extract(t, m["title"], m)["facts"][0]
        self.assertEqual(f["overdue_bdays"], 14)
        self.assertEqual(f["status"], "default")

    def test_same_day_is_technical(self):
        m, t = T.dc_load_fixture(os.path.join(FIX, "techdefault_coupon_monopoly.txt"))
        f = T.dc_extract(t, m["title"], m)["facts"][0]
        self.assertEqual(f["overdue_bdays"], 0)
        self.assertEqual(f["status"], "technical")


class DefaultAmountNotCouponNo(unittest.TestCase):
    def test_coupon_number_before_amount(self):
        txt = ("Неисполнение обязательств эмитента перед владельцами его эмиссионных ценных бумаг\n"
               "1.4. Идентификационный номер налогоплательщика (ИНН) эмитента: 7707600245\n"
               "1.7. Дата наступления события: 17.11.2026\n"
               "2.1 идентификационные признаки ценных бумаг: облигации, ISIN: RU000A10CHX1;\n"
               "2.2 содержание обязательства эмитента, также размер обязательства в денежном выражении:\n"
               "выплата купонного дохода по Биржевым облигациям за 15-й купонный период;\n"
               "общий размер купонных доходов: 15-й купонный период: 681 890 (шестьсот восемьдесят одна тысяча восемьсот девяносто) рублей 00 копеек (14,00% годовых) руб.;\n"
               "общее количество Биржевых облигаций определенного выпуска: 5 500 (пять тысяч пятьсот) штук;\n"
               "2.3 дата, в которую обязательство эмитента должно быть исполнено: 15.11.2026\n"
               "2.4 сведения о неисполнении: неисполнение эмитентом обязательства по вине эмитента;\n")
        f = T.dc_extract(txt, "Неисполнение обязательств эмитента перед владельцами его эмиссионных ценных бумаг")["facts"][0]
        self.assertAlmostEqual(f["amount"], 681890.0, places=2)
        self.assertEqual(f["coupon_no"], 15)
        self.assertEqual(f["qty"], 5500)


class DefaultSeveralObligations(unittest.TestCase):
    HEAD = ("Неисполнение обязательств эмитента перед владельцами его эмиссионных ценных бумаг\n"
            "1.4. Идентификационный номер налогоплательщика (ИНН) эмитента: 2466127447\n"
            "1.7. Дата наступления события: 12.11.2026\n"
            "2.1. Идентификационные признаки ценных бумаг: облигации, ISIN RU000A1098T4\n")

    def test_coupon_and_partial_redemption(self):
        txt = self.HEAD + ("2.2. Содержание обязательства эмитента, а для денежного обязательства также размер обязательства в денежном выражении:\n"
               "– Выплата купонного дохода по Биржевым облигациям в дату окончания 9-го купонного периода в размере 14 280 052,32 (Четырнадцать миллионов) рубля 32 копейки;\n"
               "– Частичное погашение номинальной стоимости облигаций в дату окончания 9-го купонного периода в размере 34 365 600,00 (Тридцать четыре миллиона) рублей 00 копеек;\n"
               "2.3. Дата, в которую обязательство эмитента должно быть исполнено: 12.11.2026;\n")
        f = T.dc_extract(txt, "Неисполнение обязательств эмитента перед владельцами его эмиссионных ценных бумаг")["facts"][0]
        self.assertEqual([o["obligation"] for o in f["obligations"]], ["coupon", "amortization"])
        self.assertAlmostEqual(f["obligations"][1]["amount"], 34365600.0, places=2)

    def test_partial_redemption_mentions_coupon_period(self):
        txt = self.HEAD + ("2.2. Содержание обязательства эмитента, также размер обязательства в денежном выражении: Погашение части номинальной стоимости Биржевых облигаций в дату окончания 12-го купонного периода\n"
               "- общий размер, подлежавшей погашению части номинальной стоимости Биржевых облигаций: 50 000 000 рублей.\n"
               "2.3. Дата, в которую обязательство эмитента должно быть исполнено: 12.11.2026\n")
        f = T.dc_extract(txt, "Неисполнение обязательств эмитента перед владельцами его эмиссионных ценных бумаг")["facts"][0]
        self.assertEqual(f["obligation"], "amortization")
        self.assertAlmostEqual(f["amount"], 50000000.0, places=2)
