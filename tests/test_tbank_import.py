"""Тесты импорта отчёта брокера Т-Инвестиций (xlsx): РЕПО не сделки, раздел 2 «Операции с денежными средствами»,
входящие остатки, слияние нескольких файлов в один счёт и откат на общий импортёр для остальных форматов.
Все таблицы синтетические: имитируют раскладку отчёта (заголовки разбросаны по объединённым ячейкам)."""
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()

ISIN = "RU000A0TEST1"
ISIN2 = "RU000A0TEST2"
DEAL_HEAD = {0: "Номер сделки", 8: "Дата заключения", 9: "Время", 15: "Вид сделки", 17: "Наименование \nактива", 19: "Код актива",
             21: "Цена за единицу", 23: "Валюта цены", 26: "Количество", 28: "Сумма (без НКД)", 32: "НКД", 34: "Сумма сделки",
             38: "Валюта расчетов", 39: "Комиссия \nброкера", 45: "Комиссия биржи"}
CASH_HEAD = {0: "Дата", 10: "Время совершения", 22: "Дата исполнения", 37: "Операция", 52: "Сумма зачисления",
             65: "Сумма списания", 76: "Примечание"}
POS_HEAD = {0: "Наименование актива", 13: "Код актива", 20: "ISIN", 27: "Место хранения", 40: "Входящий остаток",
            51: "Зачисление", 61: "Списание", 67: "Исходящий остаток", 78: "Плановый исходящий остаток"}


def row(d):
    r = [""] * (max(d) + 1)
    for i, v in d.items():
        r[i] = v
    return r


def deal(num, d, t, kind, code, qty, net, nkd=0.0, comm=0.0, name="Тест"):
    return row({0: num, 8: d, 9: t, 15: kind, 17: name, 19: code, 21: "99.0", 23: "%", 26: str(float(qty)), 28: str(net),
                32: str(nkd), 34: str(round(net + nkd, 2)), 38: "RUB", 39: str(comm), 45: "0.5"})


def cash(d, t, x, op, cr=0.0, db=0.0, note=""):
    return row({0: d, 10: t, 22: x, 37: op, 52: str(cr), 65: str(db), 76: note})


def report(frm, to, deals, ops, bal_in, bal_out, pos, pending=()):
    """Таблица как read_tables читает xlsx отчёта: одна таблица, разделы — строки-заголовки."""
    t = [row({0: "АКЦИОНЕРНОЕ ОБЩЕСТВО «ТБАНК»"}), row({0: "Брокер: АО «ТБанк», ИНН/КПП 7710140679/771301001"}),
         row({0: "Инвестор: ТЕСТОВ ТЕСТ ТЕСТОВИЧ / 0000000000 от 01.01.2020"}),
         row({0: "Отчет о сделках и операциях за период %s - %s" % (frm, to)}),
         row({0: "1.1 Информация о совершенных и исполненных сделках на конец отчетного периода"}), row(DEAL_HEAD)]
    t += list(deals) + [row({79: "1 из ", 85: "3.0"}), row({0: "1.2 Информация о неисполненных сделках на конец отчетного периода"}),
                        row(DEAL_HEAD)] + list(pending)
    t += [row({0: "1.3 Сделки за расчетный период, обязательства из которых прекращены  не в результате исполнения"}),
          row({0: "2. Операции с денежными средствами"}),
          row({0: "Валюта", 10: "Входящий остаток", 20: "Исходящий остаток", 33: "Плановый исходящий остаток"}),
          row({0: "RUB", 10: str(bal_in), 20: str(bal_out), 33: str(bal_out)}),
          row({0: "USD", 10: "0.0", 20: "0.0", 33: "0.0"}),
          row({0: "RUB"}), row(CASH_HEAD)] + list(ops)
    t += [row({0: "3.1 Движение по ценным бумагам инвестора"}), row(POS_HEAD)]
    for code, isin, op, i, o, cl, pl in pos:
        t.append(row({0: "Бумага " + code, 13: code, 20: isin, 27: "ТБанк", 40: str(op), 51: str(i), 61: str(o), 67: str(cl), 78: str(pl)}))
    t += [row({0: "4.1 Информация о ценных бумагах"}),
          row({0: "Наименование актива", 16: "Код актива", 22: "ISIN", 55: "Тип", 69: "Наименование эмитента"})]
    for code, isin, *_ in pos:
        t.append(row({0: "Бумага " + code, 16: code, 22: isin, 55: "обл прочих рез", 69: "Эмитент"}))
    t += [row({0: "4.3 Информация о производных финансовых инструментах"}),
          row({0: "Вид контракта", 10: "Наименование контракта", 31: "Код контракта"}), row({0: "Фьючерсы", 10: "TST-6.26", 31: "TSM6"})]
    return [t]


def report1():
    deals = [
        deal("1001", "03.02.2025", "11:00:00", "Покупка", ISIN, 10, 9900.0, 50.0, 5.0),
        deal("R1", "04.02.2025", "10:00:00", "РЕПО 1 Продажа", ISIN2, 5, 5000.0),
        deal("R1", "04.02.2025", "10:00:00", "РЕПО 2 Покупка", ISIN2, 5, 5000.0),
        deal("F1", "05.02.2025", "10:00:00", "Покупка", "TSM6", 2, 100.0, 0.0, 1.0),
    ]
    ops = [
        cash("02.02.2025", "10:00:00", "03.02.2025", "Пополнение счета", cr=100000.0),
        cash("", "", "03.02.2025", "Покупка/продажа", db=9950.0),
        cash("", "", "03.02.2025", "Комиссия за сделки", db=5.0),
        cash("", "", "04.02.2025", "РЕПО", cr=5000.0),
        cash("", "", "05.02.2025", "РЕПО", db=5000.0),
        cash("15.03.2025", "19:00:00", "15.03.2025", "Выплата доходов по корпоративным действиям", cr=300.0,
             note="Тип КД: Выплата дохода по облигациям, Наименование: Тест 1, ISIN: %s, Референс КД: 1" % ISIN),
        cash("20.03.2025", "12:00:00", "21.03.2025", "Налог", db=39.0),
        cash("25.03.2025", "12:00:00", "26.03.2025", "Вывод средств", db=1000.0),
        row({79: "2 из ", 85: "3.0"}),
        cash("", "", "30.06.2025", "Покупка/продажа", db=77.0, note="План"),
    ]
    return report("01.01.2025", "30.06.2025", deals, ops, 0.0, 89306.0, [(ISIN, ISIN, 0, 10, 0, 10, 10)])


def report2(extra_deals=(), extra_ops=(), bal_out=93583.0):
    deals = [deal("2001", "10.08.2025", "12:00:00", "Продажа", ISIN, 4, 4200.0, 80.0, 3.0)] + list(extra_deals)
    ops = [cash("", "", "11.08.2025", "Покупка/продажа", cr=4280.0), cash("", "", "11.08.2025", "Комиссия за сделки", db=3.0)] + list(extra_ops)
    return report("01.07.2025", "31.12.2025", deals, ops, 89306.0, bal_out, [(ISIN, ISIN, 10, 0, 4, 6, 6)])


def make_xlsx(rows):
    """Минимальный xlsx с одним листом (строки — inlineStr), чтобы прогнать read_tables как на настоящем файле."""
    def col(i):
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s
    body = []
    for ri, r in enumerate(rows, 1):
        cells = "".join('<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>' % (col(ci), ri, str(v).replace("&", "&amp;").replace("<", "&lt;"))
                        for ci, v in enumerate(r) if str(v) != "")
        body.append('<row r="%d">%s</row>' % (ri, cells))
    xml = '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>' % "".join(body)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/worksheets/sheet1.xml", xml)
    return buf.getvalue()


def parse(table):
    return M.tbank_parse(M.tb_detect(table))


def finalize(ops, existing=None, periods=None):
    return M.finalize_import(M._NoClient(), ops, existing=existing, periods=periods, synth=False)[0]


class TBankParse(unittest.TestCase):
    def test_detect(self):
        self.assertIsNotNone(M.tb_detect(report1()))
        self.assertIsNone(M.tb_detect([[["Дата", "Операция", "Сумма"], ["01.01.2025", "Покупка", "10"]]]))

    def test_repo_and_futures_are_not_trades(self):
        ops, meta = parse(report1())
        trades = [o for o in ops if M.classify(o["type"]) in ("buy", "sell")]
        self.assertEqual([o["id"] for o in trades], ["tb-1001"])
        self.assertEqual(meta["stat"]["repo"], 2)
        self.assertEqual(meta["stat"]["deriv_deals"], 1)
        self.assertEqual(M.qf(trades[0]["payment"]), -9950.0)          # сумма сделки с НКД
        fee = next(o for o in ops if o["id"] == "tb-1001-f")
        self.assertEqual(M.qf(fee["payment"]), -5.0)                    # только брокерская комиссия
        self.assertEqual(M.qf(trades[0]["price"]), 995.0)               # цена за бумагу в рублях, не в процентах

    def test_cash_operations(self):
        ops, meta = parse(report1())
        by = {}
        for o in ops:
            by.setdefault(M.classify(o["type"]), []).append(o)
        self.assertEqual(M.qf(by["deposits"][0]["payment"]), 100000.0)
        self.assertEqual(M.qf(by["withdrawals"][0]["payment"]), -1000.0)
        self.assertEqual(M.qf(by["tax_trade"][0]["payment"]), -39.0)
        self.assertEqual(M.qf(by["coupons"][0]["payment"]), 300.0)
        self.assertEqual(by["coupons"][0]["_ident"], ISIN)
        self.assertEqual(meta["stat"]["mirror"], 2)                     # «Покупка/продажа» и «Комиссия за сделки» — зеркала сделок
        self.assertEqual(meta["stat"]["planned"], 1)                    # строка «План» после периода не учитывается
        repo = by["other"]                                              # РЕПО — только дневное нетто, не сделки
        self.assertEqual([o["type"] for o in repo], ["OPERATION_TYPE_X_REPO"] * 2)
        self.assertAlmostEqual(sum(M.qf(o["payment"]) for o in repo), 0.0, 2)

    def test_corporate_action_kinds(self):
        def kd(txt, op="Выплата доходов по корпоративным действиям"):
            return M.tb_cash_type(op, "Тип КД: %s, Наименование: Х, ISIN: %s" % (txt, ISIN))[0]
        self.assertEqual(kd("Выплата дохода по облигациям"), "COUPON")
        self.assertEqual(kd("Частичное погашение"), "BOND_REPAYMENT")
        self.assertEqual(kd("Погашение в уст. срок"), "BOND_REPAYMENT_FULL")
        self.assertEqual(kd("Выплата дивидендов"), "DIVIDEND")
        self.assertEqual(M.tb_cash_type("Налог (дивиденды)", "")[0], "DIVIDEND_TAX")
        self.assertEqual(M.tb_cash_type("Налог (по итогу года)", "")[0], "TAX")
        self.assertEqual(M.tb_cash_type("Возмещение дохода по сделке РЕПО - зачисление", "")[0], "COUPON")
        self.assertEqual(M.tb_cash_type("Комиссия по тарифу", "")[0], "SERVICE_FEE")
        self.assertEqual(M.tb_cash_type("Перевод зачисление", "")[0], "INPUT")
        self.assertEqual(M.tb_cash_type("Перевод списание", "")[0], "OUTPUT")
        self.assertIsNone(M.tb_cash_type("DFP/RFP", ""))

    def test_redemption_clears_position(self):
        ops, _meta = parse(report1())
        ops.append({"id": "x-red", "date": "2025-06-01T19:00:00Z", "type": "OPERATION_TYPE_BOND_REPAYMENT_FULL",
                    "payment": M.to_money(10000.0), "name": "Тест 1", "_ident": ISIN})
        ops.append({"id": "x-am", "date": "2025-05-01T19:00:00Z", "type": "OPERATION_TYPE_BOND_REPAYMENT",
                    "payment": M.to_money(1000.0), "name": "Тест 1", "_ident": ISIN})
        out = finalize(ops)
        self.assertEqual(M.fifo(out), {})

    def test_reconciles_with_report_totals(self):
        for rep in (report1(), report2()):
            ops, meta = parse(rep)
            rec = M.tbank_reconcile(ops, meta)
            self.assertTrue(rec["ok"], rec)
        ops, meta = parse(report1())
        self.assertAlmostEqual(M.tbank_reconcile(ops, meta)["cash"]["rub"][1], 89306.0, 2)

    def test_single_file_gets_opening_ops(self):
        ops, meta = parse(report2())
        opening = [o for o in ops if o.get("_opening")]
        kinds = sorted(M.classify(o["type"]) for o in opening)
        self.assertEqual(kinds, ["deposits", "sec_in"])
        self.assertEqual(meta["period"], {"from": "2025-07-01", "to": "2025-12-31"})
        # продажа 4 из 10 входящих бумаг получает лоты (стоимость оценена по цене сделки периода)
        out = finalize(ops)
        self.assertEqual(M.fifo(out)["imp:" + ISIN]["qty"], 6)

    def test_rows_with_same_content_get_distinct_ids(self):
        two = [cash("01.02.2025", "10:00:00", "02.02.2025", "Пополнение счета", cr=100.0)] * 2
        rep = report("01.01.2025", "28.02.2025", [], two, 0.0, 200.0, [])
        ops, _ = parse(rep)
        ids = [o["id"] for o in ops if M.classify(o["type"]) == "deposits" and not o.get("_opening")]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)


class TBankMerge(unittest.TestCase):
    def merged(self):
        o1, m1 = parse(report1())
        o2, m2 = parse(report2())
        a = finalize(o1)
        per = [(m1["period"]["from"], m1["period"]["to"]), (m2["period"]["from"], m2["period"]["to"])]
        return a, o2, finalize(o2, existing=a, periods=per), per

    def test_buy_in_first_sell_in_second_file(self):
        _a, _o2, b, _per = self.merged()
        sell = next(o for o in b if o["id"] == "tb-2001")
        # куплено по 9950 за 10 (995 за штуку), продано 4 за 4280: результат = 4280 - 4 * 995
        self.assertAlmostEqual(M.qf(sell["yield"]), 300.0, 2)
        self.assertEqual(M.fifo(b)["imp:" + ISIN]["qty"], 6)

    def test_opening_ops_of_second_file_dropped(self):
        a, o2, b, _per = self.merged()
        self.assertTrue(any(o.get("_opening") for o in o2))
        self.assertEqual([o for o in b if o.get("_opening") and o["date"] >= "2025-07-01"], [])
        self.assertEqual(len([o for o in b if o.get("_opening")]), len([o for o in a if o.get("_opening")]))
        cash_total = sum(M.qf(o["payment"]) for o in b if M.classify(o["type"]) not in ("sec_in", "sec_out"))
        self.assertAlmostEqual(cash_total, 93583.0, 2)                    # исходящий остаток второго отчёта

    def test_reversed_order_gives_same_result(self):
        o1, m1 = parse(report1())
        o2, m2 = parse(report2())
        per = [(m1["period"]["from"], m1["period"]["to"]), (m2["period"]["from"], m2["period"]["to"])]
        later_first = finalize(o2)
        b = finalize(o1, existing=later_first, periods=per)
        self.assertEqual(sorted(o["id"] for o in b), sorted(o["id"] for o in self.merged()[2]))

    def test_overlapping_deal_is_deduplicated_by_number(self):
        o1, m1 = parse(report1())
        # второй отчёт целиком содержит сделку 1001 (периоды пересекаются): в счёте она остаётся одна
        dup = [deal("1001", "03.02.2025", "11:00:00", "Покупка", ISIN, 10, 9900.0, 50.0, 5.0)]
        o2, m2 = parse(report2(extra_deals=dup))
        a = finalize(o1)
        b = finalize(o2, existing=a, periods=[(m1["period"]["from"], m1["period"]["to"]), (m2["period"]["from"], m2["period"]["to"])])
        self.assertEqual(sum(1 for o in b if o["id"] == "tb-1001"), 1)
        self.assertEqual(sum(1 for o in b if o["id"] == "tb-1001-f"), 1)

    def test_remerge_is_idempotent(self):
        _a, o2, b, per = self.merged()
        c = finalize(o2, existing=b, periods=per)
        self.assertEqual(len(c), len(b))
        self.assertEqual(sorted(o["id"] for o in c), sorted(o["id"] for o in b))

    def test_generic_merge_recomputes_fifo_over_all_ops(self):
        h = ["Дата", "Операция", "ISIN", "Количество", "Сумма", "Валюта"]
        buy = M.rows_to_ops([["01.02.2025", "Покупка", ISIN, "10", "1000", "RUB"]], M.guess_mapping(h), h)[0]
        sell = M.rows_to_ops([["01.03.2025", "Продажа", ISIN, "4", "500", "RUB"]], M.guess_mapping(h), h)[0]
        first = finalize_generic(buy)
        both = finalize_generic(sell, existing=first)
        s = next(o for o in both if M.classify(o["type"]) == "sell")
        self.assertAlmostEqual(M.qf(s["yield"]), 100.0, 2)               # 500 - 4 * 100
        synth = [o for o in both if o.get("_synthetic")]                  # досчитанное пополнение пересчитано по всей истории
        self.assertEqual(len(synth), 1)
        self.assertEqual(synth[0]["date"][:10], "2025-02-01")


def finalize_generic(ops, existing=None):
    return M.finalize_import(M._NoClient(), ops, existing=existing)[0]


class TBankEntry(unittest.TestCase):
    def test_preview_and_ops_use_tbank_parser_for_xlsx(self):
        raw = make_xlsx(report1()[0])
        pv = M.import_preview_any("report.xlsx", raw)
        self.assertEqual(pv["format"], "tbank")
        self.assertEqual(pv["title"], "Отчёт брокера Т-Инвестиций")
        self.assertTrue(pv["cash_ok"])
        self.assertEqual(pv["pos_bad"], 0)
        self.assertEqual(pv["repo_skipped"], 2)
        self.assertEqual(pv["kinds"]["buy"], 1)
        ops, _skipped, fmt, meta = M.import_ops_any("report.xlsx", raw, 0, 0, {})
        self.assertEqual(fmt, "tbank")
        self.assertEqual(meta["period"]["from"], "2025-01-01")
        self.assertTrue(any(o["id"] == "tb-1001" for o in ops))

    def test_non_tbank_files_use_generic_importer(self):
        csv_raw = M.TEMPLATE_CSV.encode("utf-8")
        self.assertIsNone(M.tbank_try("t.csv", csv_raw))
        pv = M.import_preview_any("t.csv", csv_raw)
        self.assertNotIn("format", pv)
        self.assertIn("mapping", pv)
        ops, _skipped, fmt, meta = M.import_ops_any("t.csv", csv_raw, pv["table"], pv["header_row"], pv["mapping"])
        self.assertEqual(fmt, "")
        self.assertIsNone(meta)
        self.assertTrue(ops)
        # xlsx не от Т-Инвестиций тоже идёт общим путём
        generic = make_xlsx([["Дата", "Операция", "ISIN", "Количество", "Сумма", "Валюта"], ["01.02.2025", "Покупка", ISIN, "10", "1000", "RUB"]])
        self.assertIsNone(M.tbank_try("g.xlsx", generic))
        self.assertIn("mapping", M.import_preview_any("g.xlsx", generic))


if __name__ == "__main__":
    unittest.main()
