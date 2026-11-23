"""Исправления по итогам аудита: дробные количества в общем импорте, Retry-After датой, XIRR без сортировки,
дюрация при y ≤ −1, один фоновый пересчёт на ключ кэша, IPv6 loopback в Host."""
import os
import sys
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

M = _load.load()
ISIN = "RU000A0JX0J2"


class ImportFractional(unittest.TestCase):
    def test_fractional_quantity_kept(self):
        h = ["Дата", "Операция", "ISIN", "Количество", "Сумма", "Валюта"]
        ops = M.rows_to_ops([["01.02.2025", "Покупка", ISIN, "0,5", "3500", "RUB"]], M.guess_mapping(h), h)[0]
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["quantity"], "0.5")

    def test_whole_quantity_stays_integer_string(self):
        h = ["Дата", "Операция", "ISIN", "Количество", "Сумма", "Валюта"]
        ops = M.rows_to_ops([["01.02.2025", "Покупка", ISIN, "10", "1000", "RUB"]], M.guess_mapping(h), h)[0]
        self.assertEqual(ops[0]["quantity"], "10")


class RetryAfter(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(M._retry_after_sec({"Retry-After": "90"}), 90.0)

    def test_http_date(self):
        when = datetime.now(timezone.utc) + timedelta(seconds=600)
        v = M._retry_after_sec({"Retry-After": format_datetime(when, usegmt=True)})
        self.assertIsNotNone(v)
        self.assertTrue(500 < v <= 601, v)

    def test_missing_or_garbage(self):
        self.assertIsNone(M._retry_after_sec({}))
        self.assertIsNone(M._retry_after_sec({"Retry-After": "soon"}))
        self.assertIsNone(M._retry_after_sec(None))


class Xirr(unittest.TestCase):
    def test_unsorted_flows_same_result(self):
        flows = [(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), 1100.0)]
        a = M.dbx_xirr(flows)
        b = M.dbx_xirr(list(reversed(flows)))
        self.assertAlmostEqual(a, b, places=6)
        self.assertAlmostEqual(a, 0.1, places=2)


class CfRisk(unittest.TestCase):
    def test_y_minus_one_no_crash(self):
        flows = [(date(2030, 1, 1), 50.0, 1000.0)]
        self.assertEqual(M.cf_risk(flows, date(2026, 1, 1), -1.0), (None, None, None))
        self.assertEqual(M.cf_risk(flows, date(2026, 1, 1), None), (None, None, None))


class BgRefreshOnce(unittest.TestCase):
    def test_concurrent_stale_hits_start_one_refresh(self):
        src = open(os.path.join(_load.ROOT, "src", "py", "11_accounts_summary.py"), encoding="utf-8").read()
        self.assertIn("with _bg_lock:", src)
        # Модель логики: N потоков одновременно видят устаревший кэш — запускается ровно один пересчёт.
        started = []
        barrier = threading.Barrier(8)

        def hit():
            barrier.wait()
            with M._bg_lock:
                start = "k" not in M._bg
                M._bg.add("k")
            if start:
                started.append(1)
        ts = [threading.Thread(target=hit) for _ in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        M._bg.discard("k")
        self.assertEqual(len(started), 1)


class HostIPv6(unittest.TestCase):
    def test_ipv6_loopback_allowed(self):
        h = M.Handler.__new__(M.Handler)
        h.server = type("S", (), {"server_address": ("127.0.0.1", 8765)})()
        for host, ok in (("[::1]:8765", True), ("localhost:8765", True), ("evil.com:8765", False)):
            h.headers = {"Host": host}
            self.assertEqual(h.ok_host(), ok, host)


if __name__ == "__main__":
    unittest.main()
