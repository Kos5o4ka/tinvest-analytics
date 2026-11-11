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


class IssuerKey(unittest.TestCase):
    def test_issuer_group(self):
        k = M.issuer_group_key
        self.assertEqual(k("ОФЗ 26238"), k("ОФЗ 26240"))
        self.assertEqual(k("ПАО Газпром 001Р-02"), k("Газпром 003Р-01"))
        self.assertNotEqual(k("ГК Самолет БО-П10"), k("Газпром 003Р-01"))
        self.assertNotEqual(k("ПАО Газпром 001Р-02"), "пао")


if __name__ == "__main__":
    unittest.main()
