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


if __name__ == "__main__":
    unittest.main()
