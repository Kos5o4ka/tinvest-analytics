"""Тесты определения типа операции в импорте отчётов брокера: налоги не должны попадать в купоны/дивиденды."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


class ImportTypes(unittest.TestCase):
    def test_taxes_first(self):
        d = M.detect_type
        self.assertEqual(d("Удержание НДФЛ с дивидендов", None, -10.0), "DIVIDEND_TAX")
        self.assertEqual(d("Налог с купона", None, -10.0), "BOND_TAX")
        self.assertEqual(d("Удержан НДФЛ", None, -10.0), "TAX")
        self.assertEqual(d("Налог", None, -10.0), "TAX")

    def test_income_still_detected(self):
        d = M.detect_type
        self.assertEqual(d("Выплата купона", None, 10.0), "COUPON")
        self.assertEqual(d("Выплата дивидендов", None, 10.0), "DIVIDEND")
        self.assertEqual(d("Погашение", None, 10.0), "BOND_REPAYMENT_FULL")
        self.assertEqual(d("Покупка", 1, -100.0), "BUY")

    def test_rows_to_ops_sign_and_class(self):
        header = ["Дата", "Операция", "Сумма", "Валюта"]
        rows = [["01.02.2025", "Удержание НДФЛ с дивидендов", "13", "RUB"],
                ["01.02.2025", "Налог с купона", "5", "RUB"],
                ["01.02.2025", "Выплата купона", "100", "RUB"]]
        ops, _ = M.rows_to_ops(rows, M.guess_mapping(header), header)
        kinds = [(o["type"], M.classify(o["type"]), M.money_val(o["payment"]) if hasattr(M, "money_val") else None) for o in ops]
        self.assertEqual([k[0] for k in kinds], ["OPERATION_TYPE_DIVIDEND_TAX", "OPERATION_TYPE_BOND_TAX", "OPERATION_TYPE_COUPON"])
        self.assertEqual([k[1] for k in kinds], ["tax_dividend", "tax_coupon", "coupons"])
        self.assertTrue(int(ops[0]["payment"]["units"]) < 0 or ops[0]["payment"]["nano"] < 0)

    def test_template_csv_nkd_and_idempotent_reimport(self):
        csv_raw = M.TEMPLATE_CSV.encode("utf-8")
        pv = M.import_preview_any("t.csv", csv_raw)
        ops1, _, _, _ = M.import_ops_any("t.csv", csv_raw, pv["table"], pv["header_row"], pv["mapping"])
        ops2, _, _, _ = M.import_ops_any("t.csv", csv_raw, pv["table"], pv["header_row"], pv["mapping"])
        bond_buy = [o for o in ops1 if o["type"] == "OPERATION_TYPE_BUY" and o.get("_ident") == "RU000A10C6P6"][0]
        self.assertAlmostEqual(M.qf(bond_buy["payment"]), -10050.0, places=2)
        # Если сумма в CSV указана без НКД (10020 при 10 * 100,2 % и НКД 30) — НКД должен прибавиться
        hdr = ["Дата", "Тип операции", "ISIN", "Количество", "Цена", "Сумма", "Валюта", "НКД"]
        ops_clean, _ = M.rows_to_ops([["20.02.2025", "Покупка", "RU000A10C6P6", "10", "100,2", "10020", "RUB", "30"]],
                                      M.guess_mapping(hdr), hdr)
        self.assertAlmostEqual(M.qf(ops_clean[0]["payment"]), -10050.0, places=2)
        # Повторный импорт того же файла не создаёт дублей
        merged = M.import_merge_ops(ops1, ops2)
        self.assertEqual(len(merged), len(ops1))


class IssuerKey(unittest.TestCase):
    def test_issuer_group(self):
        k = M.issuer_group_key
        self.assertEqual(k("ОФЗ 26238"), k("ОФЗ 26240"))
        self.assertEqual(k("ПАО Газпром 001Р-02"), k("Газпром 003Р-01"))
        self.assertNotEqual(k("ГК Самолет БО-П10"), k("Газпром 003Р-01"))
        self.assertNotEqual(k("ПАО Газпром 001Р-02"), "пао")


class DuplicateAndOverlapImport(unittest.TestCase):
    def setUp(self):
        self._old_imp = M.store().get("imports")
        for a in self._old_imp or []:
            self._saved_ops = getattr(self, "_saved_ops", {})
            self._saved_ops[a["id"]] = M.store().ops(a["id"])
        for a in list(self._old_imp or []):
            M.store().ops_clear(a["id"])
        M.store().put("imports", [])

    def tearDown(self):
        for a in M.imports_list():
            M.store().ops_clear(a["id"])
        M.store().put("imports", self._old_imp or [])
        for aid, ops in getattr(self, "_saved_ops", {}).items():
            M.store().ops_put(aid, ops)
        M.mem_clear()

    def _csv_body(self, name, csv_text, target=""):
        import base64
        raw = csv_text.encode("utf-8")
        pv = M.import_preview_any(name, raw)
        return {
            "filename": name,
            "data": base64.b64encode(raw).decode("ascii"),
            "table": pv["table"],
            "header_row": pv["header_row"],
            "mapping": pv["mapping"],
            "name": "Мой портфель",
            "broker": "БКС",
            "target": target,
        }

    def test_reupload_same_csv_returns_409_and_no_duplicates(self):
        csv1 = (
            "Дата;Тип операции;ISIN;Тикер;Название;Количество;Цена;Сумма;Валюта;Комиссия;НКД\n"
            "05.05.2025;Пополнение;;;;;;50000;RUB;;\n"
            "15.05.2025 10:00:00;Покупка;RU0009029540;SBER;Сбербанк;10;270;2700;RUB;;\n"
        )
        res1 = M.import_commit(M._NoClient(), self._csv_body("may1.csv", csv1))
        acc_id = res1["id"]
        self.assertEqual(len(M.imports_list()), 1)

        # Повторная загрузка того же файла в «Новый счёт» (как по умолчанию в UI) — должна падать с 409
        with self.assertRaises(M.ApiError) as cm:
            M.import_commit(M._NoClient(), self._csv_body("may1_copy.csv", csv1, target=""))
        self.assertEqual(cm.exception.status, 409)
        self.assertEqual(len(M.imports_list()), 1)

        pv_dup = M.import_preview_any("may1_copy.csv", csv1.encode("utf-8"))
        self.assertEqual(pv_dup["duplicate_of"]["id"], acc_id)

        # Повторная загрузка того же файла в тот же счёт — тоже ошибка 409
        with self.assertRaises(M.ApiError) as cm2:
            M.import_commit(M._NoClient(), self._csv_body("may1.csv", csv1, target=acc_id))
        self.assertEqual(cm2.exception.status, 409)
        buys = [o for o in M.store().ops(acc_id) if M.classify(o["type"]) == "buy"]
        self.assertEqual(len(buys), 1)

    def test_overlapping_may1_20_and_may10_30_csv_no_duplicate_trades(self):
        # Отчёт 1: 1–20 мая (покупка 5 мая + покупка 15 мая + дивиденд 18 мая)
        csv_1_20 = (
            "Дата;Тип операции;ISIN;Тикер;Название;Количество;Цена;Сумма;Валюта;Комиссия;НКД\n"
            "01.05.2025;Пополнение;;;;;;100000;RUB;;\n"
            "05.05.2025 10:00:00;Покупка;;SBER;Сбербанк;10;270;2700;RUB;;\n"
            "15.05.2025 12:00:00;Покупка;;SBER;Сбербанк;20;280;5600;RUB;;\n"
            "18.05.2025;Дивиденд;;SBER;Сбербанк;;;500;RUB;;\n"
        )
        # Отчёт 2: 10–30 мая (та же покупка 15 мая и дивиденд 18 мая, но с ISIN вместо тикера + новая покупка 25 мая)
        csv_10_30 = (
            "Дата;Тип операции;ISIN;Тикер;Название;Количество;Цена;Сумма;Валюта;Комиссия;НКД\n"
            "15.05.2025 12:00:00;Покупка;RU0009029540;;ПАО Сбербанк;20;280;5600;RUB;;\n"
            "18.05.2025;Дивиденд;RU0009029540;;ПАО Сбербанк;;;500;RUB;;\n"
            "25.05.2025 11:00:00;Покупка;RU0009029540;;ПАО Сбербанк;15;290;4350;RUB;;\n"
        )

        # Fake client, резолвящий и "SBER", и "RU0009029540" в один instrumentUid
        class ResolvingClient:
            ready = True

            def find(self, ident):
                if ident in ("SBER", "RU0009029540"):
                    return [{"isin": "RU0009029540", "ticker": "SBER", "uid": "uid-sber", "figi": "BBG004730N88",
                             "name": "Сбербанк", "type": "share", "kind": "INSTRUMENT_TYPE_SHARE", "classCode": "TQBR"}]
                return []

        M.store().put("res:bonds:test_key:all", {"t": 9e12, "v": {"rows": []}})
        r1 = M.import_commit(ResolvingClient(), self._csv_body("may_1_20.csv", csv_1_20))
        acc_id = r1["id"]
        parsed2 = M.import_parse_info(self._csv_body("may_10_30.csv", csv_10_30))
        self.assertIsNone(parsed2["duplicate_of"])
        self.assertIsNotNone(parsed2["overlap_account"])
        self.assertEqual(parsed2["overlap_account"]["id"], acc_id)
        r2 = M.import_commit(ResolvingClient(), self._csv_body("may_10_30.csv", csv_10_30, target=acc_id))
        ops = M.store().ops(acc_id)
        buys = [o for o in ops if M.classify(o["type"]) == "buy"]
        divs = [o for o in ops if M.classify(o["type"]) == "dividends"]
        self.assertEqual(len(buys), 3)       # 5 мая (10) + 15 мая (20) + 25 мая (15) — без дубля 15 мая!
        self.assertEqual(M.fifo(ops)["uid-sber"]["qty"], 45.0)
        self.assertEqual(len(divs), 1)       # дивиденд 18 мая тоже не продублировался
        self.assertEqual(r2["total"], len(ops))
        # Кэш res:* сброшен после импорта
        self.assertIsNone(M.store().get("res:bonds:test_key:all"))


if __name__ == "__main__":
    unittest.main()
