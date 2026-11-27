"""Тесты импорта отчёта брокера ВТБ (xlsx): «@xl»-ячейки, дедупликация заключённых/завершённых сделок, классификация
денежного движения, сверка с остатками, слияние периодов. Таблицы синтетические, раскладка колонок — как в отчёте."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402
from test_tbank_import import make_xlsx, row, report1  # noqa: E402

M = load()
M.moex_splits_list = lambda: []      # тесты без сети: сплитов нет (см. tests/test_splits_import.py)
ISIN = "RU000A0TEST1"
NAME = "Тест 1, 4B02-01-00001-A, " + ISIN


def xl(y, m, d, frac=0.0):
    """Серийный номер Excel так, как его отдаёт наш ридер для ячеек со стилем даты."""
    return "@xl%s" % ((datetime(y, m, d) - datetime(1899, 12, 30)).days + frac)


DEAL_HEAD = {1: "Наименование ценной бумаги, № гос. регистрации, ISIN", 2: "Дата и время заключения сделки", 5: "Вид сделки",
             7: "Количество (шт.)", 8: "Валюта цены (номинала для облигаций)", 9: "Цена (% для облигаций)", 10: "Валюта расчётов",
             11: "Сумма сделки в валюте расчётов (с учётом НКД для облигаций)", 13: "НКД по сделке в валюте расчётов",
             14: "Комиссия Банка за расчёт по сделке", 16: "Комиссия Банка за заключение сделки", 24: "№ сделки",
             27: "№ сделки у организатора торгов", 36: "Ставка РЕПО"}


def deal(num, when, kind, qty, total, nkd=0.0, repo=""):
    return row({1: NAME, 2: when, 5: kind, 7: str(float(qty)), 8: "RUR", 9: "99.0", 10: "RUR", 11: total, 13: str(nkd), 14: "0.1",
                16: "0.0", 24: num, 27: num[1:], 36: repo})


def cash(d, amount, op, note=""):
    return row({1: d, 2: amount, 6: "RUR", 9: op, 14: note})


def report(frm, to, concluded, completed, cash_rows, bal, secs, movs=()):
    t = [row({3: "Отчет Банка ВТБ (ПАО) за период с %s по %s о сделках, операциях и состоянии счетов Клиента" % (frm, to)}),
         row({1: "Клиент:", 8: "Тестов Т. Т."}), row({1: "Сводная информация по субсчёту Клиента"}),
         row({1: "Описание", 10: "Сумма", 13: "Валюта"}), row({1: "ВХОДЯЩИЙ остаток денежных средств", 10: str(bal[0]), 13: "RUR"}),
         row({1: "Отчёт об остатках денежных средств"}),
         row({1: "Валюта", 2: "Входящий остаток денежных средств", 13: "Изменение за период", 16: "Исходящий остаток денежных средств",
              34: "Плановый исходящий остаток"}),
         row({2: "Основной рынок", 5: "Срочный рынок", 8: "Внебирж. рынок", 10: "Итого", 16: "Основной рынок", 18: "Срочный рынок",
              26: "Внебирж. рынок", 30: "Итого"}),
         row({1: "RUR", 2: str(bal[0]), 5: "0.0", 8: "0.0", 10: str(bal[0]), 13: "1.0", 16: str(bal[1]), 18: "0.0", 26: "0.0",
              30: str(bal[1]), 34: str(bal[2])}),
         row({1: "Движение денежных средств"}), row({1: "Дата", 2: "Сумма", 6: "Валюта", 9: "Тип операции", 14: "Комментарий"}),
         row({1: "Основной рынок"})] + list(cash_rows)
    t += [row({1: "Отчёт об остатках ценных бумаг"}),
          row({1: "Наименование ценной бумаги, № гос. регистрации, ISIN", 5: "Площадка", 8: "Входящий остаток (шт)",
               9: "Изменение за период", 10: "Исходящий остаток (шт)", 11: "Плановый исходящий остаток (шт)"}), row({1: "ОБЛИГАЦИЯ"})]
    for op, cl, pl in secs:
        t.append(row({1: NAME, 5: "Фондовый рынок", 8: str(op), 9: "1.0", 10: str(cl), 11: str(pl)}))
    t += [row({1: "ИТОГО:", 30: "1.0"}), row({1: "Движение ценных бумаг"}),
          row({1: "Наименование ценной бумаги, № гос. регистрации, ISIN", 4: "Площадка/Неторговый раздел счета депо",
               8: "Дата операции", 10: "Количество (шт.)", 13: "Тип операции", 15: "Комментарий"})] + list(movs)
    t += [row({1: "Заключенные в отчетном периоде сделки с ценными бумагами"}), row(DEAL_HEAD)] + list(concluded)
    t += [row({1: "Завершенные в отчетном периоде сделки с ценными бумагами (обязательства прекращены)"}), row(DEAL_HEAD)] + list(completed)
    t += [row({1: "В случае отсутствия в отчетном периоде операций и/или сведений для включения в Разделы: ..."})]
    return [t]


def mirror(d, qty, kind="Покупка"):
    return row({1: NAME, 4: "Фондовый рынок", 8: d, 10: str(float(qty)), 13: kind, 15: "Расчеты по заключенным сделкам"})


BUY1 = deal("B1001", xl(2025, 2, 3, 0.45), "Покупка", 10, "9950.0", 50.0)
PENDING = deal("B1002", xl(2025, 6, 29, 0.5), "Покупка", 5, "5,000.0")        # заключена в конце периода, рассчитается в июле
SELL = deal("B2001", xl(2025, 8, 10, 0.5), "Продажа", 4, "4,280.0", 80.0)


def report1_vtb():
    cash_rows = [
        cash(xl(2025, 2, 3), "@xl100000.0", "Зачисление денежных средств", "Перечисление ДС для приобретения ценных бумаг"),
        cash(xl(2025, 2, 4), "-9950.0", "Сальдо расчетов по сделкам с ценными бумагами"),
        cash(xl(2025, 2, 4), "-5.0", "Вознаграждение брокера", "Комиссия Банка за заключение сделок на Основном рынке"),
        cash(xl(2025, 3, 15), "300.0", "Купонный доход", "Выплата купонного дохода по облигациям Тест 1 ISIN %s, размер" % ISIN),
        cash(xl(2025, 3, 20), "-39.0", "НДФЛ", "Уплата налога/Списание задолженности по налогу"),
        cash("25.03.2025", "-1,000.0", "Списание денежных средств", "Вывод денежных средств с брокерского счета"),
    ]
    return report("01.01.2025", "30.06.2025", [BUY1, PENDING], [BUY1], cash_rows, (0.0, 89306.0, 84306.0),
                  [(0, 10, 15)], [mirror(xl(2025, 2, 4), 10)])


def report2_vtb(extra_movs=(), secs=((10, 11, 11),)):
    cash_rows = [
        cash(xl(2025, 7, 1), "-5000.0", "Сальдо расчетов по сделкам с ценными бумагами"),
        cash(xl(2025, 8, 11), "4280.0", "Сальдо расчетов по сделкам с ценными бумагами"),
        cash(xl(2025, 8, 11), "-3.0", "Вознаграждение брокера", "Комиссия Банка за расчёт по сделкам на Основном рынке"),
        cash(xl(2025, 9, 1), "691.0", "Дивиденды", "Выплата дохода по акциям ПАО \"Тест\" ISIN %s, размер выплаты" % ISIN),
        cash(xl(2025, 9, 2), "-90.0", "НДФЛ", "Налог с дивидендов"),
        cash(xl(2025, 9, 3), "600.0", "Погашение ценных бумаг", "Погашение номинальной стоимости облигаций Тест 1 ISIN %s, размер" % ISIN),
    ]
    return report("01.07.2025", "31.12.2025", [SELL], [PENDING, SELL], cash_rows, (89306.0, 89784.0, 89784.0),
                  list(secs), [mirror(xl(2025, 7, 1), 5), mirror(xl(2025, 8, 11), 4, "Продажа")] + list(extra_movs))


def parse(t):
    return M.vtb_parse(M.vt_detect(t))


def fin(ops, existing=None, periods=None):
    return M.finalize_import(M._NoClient(), ops, existing=existing, periods=periods, synth=False)[0]


class VtbParse(unittest.TestCase):
    def test_detect_is_exclusive(self):
        self.assertIsNotNone(M.vt_detect(report1_vtb()))
        self.assertIsNone(M.tb_detect(report1_vtb()))
        self.assertIsNone(M.vt_detect(report1()))                       # отчёт Т-Инвестиций — другой формат

    def test_xl_cells_and_thousands(self):
        ops, _ = parse(report1_vtb())
        dep = next(o for o in ops if M.classify(o["type"]) == "deposits" and not o.get("_opening"))
        self.assertEqual(M.qf(dep["payment"]), 100000.0)               # «@xl100000.0» — сумма, а не дата
        self.assertEqual(dep["date"], "2025-02-03T00:00:00Z")
        wd = next(o for o in ops if M.classify(o["type"]) == "withdrawals")
        self.assertEqual(M.qf(wd["payment"]), -1000.0)                 # «-1,000.0» и текстовая дата
        buy = next(o for o in ops if o["id"] == "vtb-B1001")
        self.assertEqual(buy["date"][:10], "2025-02-03")
        self.assertEqual(M.qf(buy["payment"]), -9950.0)
        self.assertEqual(M.qf(buy["price"]), 995.0)

    def test_deals_deduplicated_between_sections(self):
        ops, meta = parse(report1_vtb())
        self.assertEqual(sorted(o["id"] for o in ops if M.classify(o["type"]) == "buy"), ["vtb-B1001", "vtb-B1002"])
        ops2, _ = parse(report2_vtb())
        self.assertEqual(sorted(o["id"] for o in ops2 if M.classify(o["type"]) in ("buy", "sell")), ["vtb-B1002", "vtb-B2001"])

    def test_cash_classification(self):
        ops, meta = parse(report2_vtb())
        by = {}
        for o in ops:
            if not o.get("_opening"):
                by.setdefault(M.classify(o["type"]), []).append(o)
        self.assertEqual(M.qf(by["dividends"][0]["payment"]), 691.0)
        self.assertEqual(by["dividends"][0]["_ident"], ISIN)
        self.assertEqual(M.qf(by["tax_dividend"][0]["payment"]), -90.0)
        self.assertEqual(M.op_type(by["repayments"][0]), "BOND_REPAYMENT")  # «Погашение номинальной стоимости» без списания бумаг — амортизация
        self.assertEqual(M.qf(by["fee_broker"][0]["payment"]), -3.0)
        self.assertEqual(meta["stat"]["mirror"], 2)                     # «Сальдо расчетов по сделкам» — зеркало
        self.assertEqual(meta["stat"]["mirror_sec"], 2)
        ops1, _ = parse(report1_vtb())
        self.assertEqual(M.classify(next(o for o in ops1 if "НДФЛ" in o["name"] or o["name"] == "Налог")["type"]), "tax_trade")

    def test_full_redemption_when_securities_written_off(self):
        gone = row({1: NAME, 4: "Фондовый рынок", 8: xl(2025, 9, 3), 10: "11.0", 13: "Погашение", 15: "Погашение облигаций"})
        ops, meta = parse(report2_vtb([gone], ((10, 0, 0),)))
        self.assertEqual([M.op_type(o) for o in ops if M.classify(o["type"]) == "repayments"], ["BOND_REPAYMENT_FULL"])
        self.assertEqual(meta["stat"].get("xfer_out", 0), 0)            # списание бумаг — это погашение, отдельной операции нет

    def test_reconciles_with_plan_balances(self):
        for rep in (report1_vtb(), report2_vtb()):
            ops, meta = parse(rep)
            rec = M.tbank_reconcile(ops, meta)
            self.assertTrue(rec["ok"], rec)
        ops, meta = parse(report1_vtb())
        self.assertAlmostEqual(M.tbank_reconcile(ops, meta)["cash"]["rub"][1], 84306.0, 2)   # с учётом ещё не рассчитанной сделки
        self.assertEqual(M.tbank_reconcile(ops, meta)["pos"][ISIN], (15.0, 15.0))


class VtbMerge(unittest.TestCase):
    def two(self):
        o1, m1 = parse(report1_vtb())
        o2, m2 = parse(report2_vtb())
        a = fin(o1)
        per = [(m1["period"]["from"], m1["period"]["to"]), (m2["period"]["from"], m2["period"]["to"])]
        return a, o2, fin(o2, existing=a, periods=per), per, m2

    def test_fifo_across_files_and_dropped_opening(self):
        a, o2, b, per, m2 = self.two()
        sell = next(o for o in b if o["id"] == "vtb-B2001")
        self.assertAlmostEqual(M.qf(sell["yield"]), 300.0, 2)          # 4280 - 4 * 995: лоты из первого файла
        self.assertEqual(M.fifo(b)["imp:" + ISIN]["qty"], 11)
        self.assertEqual([o for o in b if o.get("_opening") and o["date"] >= "2025-07-01"], [])
        self.assertEqual(sum(1 for o in b if o["id"] == "vtb-B1002"), 1)  # сделка из двух файлов — одна
        cash_total = sum(M.qf(o["payment"]) for o in b)   # все операции, как суммирует портфель
        self.assertAlmostEqual(cash_total, m2["cash_close"]["rub"], 2)

    def test_remerge_idempotent(self):
        _a, o2, b, per, _m = self.two()
        c = fin(o2, existing=b, periods=per)
        self.assertEqual(sorted(o["id"] for o in c), sorted(o["id"] for o in b))

    def test_single_second_file_has_sane_opening(self):
        ops, meta = parse(report2_vtb())
        self.assertEqual(sorted(M.classify(o["type"]) for o in ops if o.get("_opening")), ["deposits", "sec_in"])
        self.assertEqual(M.fifo(fin(ops))["imp:" + ISIN]["qty"], 11)


class VtbEntry(unittest.TestCase):
    def test_preview_and_ops_via_xlsx(self):
        raw = make_xlsx(report1_vtb()[0])
        pv = M.import_preview_any("r.xlsx", raw)
        self.assertEqual((pv["format"], pv["title"]), ("vtb", "Отчёт брокера ВТБ"))
        self.assertTrue(pv["cash_ok"])
        self.assertEqual(pv["pos_bad"], 0)
        self.assertEqual(pv["period"], {"from": "2025-01-01", "to": "2025-06-30"})
        ops, _s, fmt, meta = M.import_ops_any("r.xlsx", raw, 0, 0, {})
        self.assertEqual(fmt, "vtb")
        self.assertTrue(any(o["id"] == "vtb-B1001" for o in ops))

    def test_tbank_still_detected_and_others_generic(self):
        raw = make_xlsx(report1()[0])
        self.assertEqual(M.import_preview_any("t.xlsx", raw)["format"], "tbank")
        generic = make_xlsx([["Дата", "Операция", "ISIN", "Количество", "Сумма", "Валюта"], ["01.02.2025", "Покупка", ISIN, "10", "1000", "RUB"]])
        self.assertIn("mapping", M.import_preview_any("g.xlsx", generic))

    def test_fractional_opening_and_short_cover(self):
        # входящий остаток 0.25 шт. и внутридневной шорт 0.4 шт. не должны отбрасываться порогом 0.5
        t = report("01.01.2025", "30.06.2025",
                   [deal("V1", xl(2025, 2, 3, 0.4), "Продажа", 0.4, "400.0"),
                    deal("V2", xl(2025, 2, 3, 0.5), "Покупка", 0.4, "400.0")],
                   [], [], (0.0, 0.0, 0.0), [(0.25, 0.25, 0.25)], [])
        ops, _meta = parse(t)
        opening = [o for o in ops if o["id"].startswith("vtb-open-sec-%s" % ISIN)]
        self.assertEqual(len(opening), 1)
        self.assertEqual(opening[0]["quantity"], "0.25")
        xfers = [o for o in ops if o["id"].startswith("vtb-xfer-")]
        self.assertEqual(len(xfers), 2)


if __name__ == "__main__":
    unittest.main()
