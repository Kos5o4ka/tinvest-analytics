"""Производительность сервера данных: gzip, ETag/304, LRU, метрики /v1/health, since у среза, параллельная сборка среза. Офлайн."""
import gzip
import json
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import market_worker as mw  # noqa: E402
import tinvest_server as ts  # noqa: E402
from test_server import Fx  # noqa: E402

BIG = json.dumps({"rows": ["строка %d" % i for i in range(400)]}, ensure_ascii=False).encode("utf-8")


def iss(cols, rows):
    return {"securities": {"columns": cols, "data": rows}, "marketdata": {"columns": ["SECID"], "data": []}}


def fake_fetch(url):
    if "/bonds/" in url:
        return {"securities": {"columns": ["SECID", "ISIN", "SHORTNAME", "SECNAME", "MATDATE", "PREVLEGALCLOSEPRICE"],
                               "data": [["SU1", "RU1", "ОФЗ 1", "ОФЗ 1", "2030-01-01", 99.0]]},
                "marketdata": {"columns": ["SECID"], "data": []}}
    return {"securities": {"columns": ["SECID"], "data": []}, "marketdata": {"columns": ["SECID"], "data": []}}


class GzipEtagTests(unittest.TestCase):
    def setUp(self):
        self.f = Fx()
        self.f.up.override = (200, BIG, "application/json", {})

    def tearDown(self):
        self.f.close()

    def test_gzip_only_on_request(self):
        u = self.f.up.url("/big")
        st, body, h = self.f.call(u)
        self.assertEqual(body, BIG)                                   # без заголовка — без сжатия
        self.assertIsNone(h.get("Content-Encoding"))
        st, body, h = self.f.call(u, headers={"Accept-Encoding": "gzip"})
        self.assertEqual(h.get("Content-Encoding"), "gzip")
        self.assertEqual(h.get("Vary"), "Accept-Encoding")
        self.assertEqual(int(h["Content-Length"]), len(body))
        self.assertEqual(gzip.decompress(body), BIG)
        self.assertLess(len(body), len(BIG))

    def test_small_body_not_compressed(self):
        st, body, h = self.f.call(None, headers={"Accept-Encoding": "gzip"}, path="/v1/health")
        self.assertIsNone(h.get("Content-Encoding"))
        self.assertTrue(json.loads(body)["ok"])

    def test_etag_304(self):
        u = self.f.up.url("/big")
        st, body, h = self.f.call(u)
        tag = h["ETag"]
        self.assertEqual(st, 200)
        st, body, h = self.f.call(u, headers={"If-None-Match": tag})
        self.assertEqual((st, body), (304, b""))
        self.assertEqual(h["ETag"], tag)
        st, body, h = self.f.call(u, headers={"If-None-Match": '"other"'})
        self.assertEqual(st, 200)
        st, body, h = self.f.call(u, headers={"If-None-Match": 'W/' + tag})
        self.assertEqual(st, 304)

    def test_etag_same_with_gzip(self):
        u = self.f.up.url("/big")
        tag = self.f.call(u)[2]["ETag"]
        st, body, h = self.f.call(u, headers={"Accept-Encoding": "gzip", "If-None-Match": tag})
        self.assertEqual(st, 304)

    def test_snapshot_etag_and_since(self):
        db = mw.open_db(os.path.join(self.f.tmp, "market.sqlite"))
        res = mw.collect_once(db, fetch_json=fake_fetch, now=1234.0, fetch_candles=False)
        db.close()
        self.assertIn("build_sec", res)
        st, body, h = self.f.call(None, path="/v1/market/snapshot?kind=bonds")
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body)["data"]["updated_at"], 1234.0)
        st, _, _ = self.f.call(None, path="/v1/market/snapshot?kind=bonds", headers={"If-None-Match": h["ETag"]})
        self.assertEqual(st, 304)
        st, body, _ = self.f.call(None, path="/v1/market/snapshot?kind=bonds&since=1234")
        d = json.loads(body)["data"]
        self.assertTrue(d["unchanged"])
        self.assertNotIn("data", d)
        st, body, _ = self.f.call(None, path="/v1/market/snapshot?kind=bonds&since=1000")
        self.assertIn("data", json.loads(body)["data"])
        self.assertEqual(self.f.call(None, path="/v1/market/snapshot?kind=bonds&since=abc")[0], 400)


class LruTests(unittest.TestCase):
    def test_evicts_oldest_not_all(self):
        c = ts.LRU(3)
        for k in "abc":
            c.set(k, k)
        c.get("a")                      # a теперь самый свежий
        c.set("d", "d")                 # вытесняется b
        self.assertEqual(len(c), 3)
        self.assertIn("a", c)
        self.assertNotIn("b", c)
        self.assertIn("c", c)
        self.assertIn("d", c)

    def test_pcache_is_lru(self):
        f = Fx()
        try:
            self.assertIsInstance(f.app._pcache, ts.LRU)
            for i in range(ts.PCACHE_MAX + 5):
                f.app._pcache.set(i, i)
            self.assertEqual(len(f.app._pcache), ts.PCACHE_MAX)
        finally:
            f.close()


class HealthMetricsTests(unittest.TestCase):
    def test_metrics(self):
        f = Fx()
        try:
            u = f.up.url("/a")
            f.call(u)
            f.call(u)
            h = json.loads(f.call(None, path="/v1/health")[1])
            for k in ("cache_hit_rate", "latency_p50_ms", "latency_p95_ms", "pcache_size", "snapshot_age_sec"):
                self.assertIn(k, h)
            self.assertEqual(h["cache_hit_rate"], 0.5)
            self.assertGreaterEqual(h["latency_n"], 2)
            self.assertGreaterEqual(h["latency_p95_ms"], h["latency_p50_ms"])
            self.assertIsNone(h["snapshot_age_sec"])
            db = mw.open_db(os.path.join(f.tmp, "market.sqlite"))
            mw.collect_once(db, fetch_json=fake_fetch, now=f.now[0] - 120, fetch_candles=False)
            db.close()
            h = json.loads(f.call(None, path="/v1/health")[1])
            self.assertGreaterEqual(h["snapshot_age_sec"], 0)
            self.assertIsNotNone(h["snapshot_build_sec"])
        finally:
            f.close()

    def test_prewarm_never_raises(self):
        f = Fx()
        try:
            st = f.app.prewarm()
            self.assertEqual(st["snapshots"], 0)
        finally:
            f.close()

    def test_sqlite_pragmas(self):
        f = Fx()
        try:
            self.assertEqual(f.app.cache.db.execute("PRAGMA cache_size").fetchone()[0], -ts.SQLITE_CACHE_KB)
        finally:
            f.close()


class ParallelSnapshotTests(unittest.TestCase):
    def test_parallel_capped_and_correct(self):
        lock, state = threading.Lock(), {"cur": 0, "max": 0}

        def fetch(url):
            with lock:
                state["cur"] += 1
                state["max"] = max(state["max"], state["cur"])
            time.sleep(0.02)
            try:
                return fake_fetch(url)
            finally:
                with lock:
                    state["cur"] -= 1

        db = mw.open_db(":memory:")
        res = mw.collect_once(db, fetch_json=fetch, now=1.0, fetch_candles=False, workers=16)
        self.assertEqual(res["bonds_n"], 1)                     # дубликаты по ISIN отброшены
        self.assertGreater(state["max"], 1)
        self.assertLessEqual(state["max"], mw.MAX_WORKERS)

    def test_failed_request_does_not_break(self):
        def fetch(url):
            if "TQCB" in url:
                raise OSError("boom")
            return fake_fetch(url)
        db = mw.open_db(":memory:")
        res = mw.collect_once(db, fetch_json=fetch, now=1.0, fetch_candles=False)
        self.assertEqual(res["bonds_n"], 1)


if __name__ == "__main__":
    unittest.main()
