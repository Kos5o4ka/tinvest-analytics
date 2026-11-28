"""/v1/batch: несколько адресов одним запросом через кэш сервера; ошибки по элементу приложение добирает обычным путём."""
import base64
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402
from test_server import BIN, Fx  # noqa: E402


class ServerBatch(unittest.TestCase):
    def setUp(self):
        self.f = Fx()
        self.addCleanup(self.f.close)

    def post(self, obj):
        st, body, _ = self.f.call(None, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"}, path="/v1/batch")
        return st, json.loads(body)

    def test_items_cache_and_errors(self):
        up = self.f.up
        urls = [up.url("/a"), up.url("/bin"), up.url("/nf"), up.url("/boom"), "http://evil.example.com/x"]
        st, j = self.post({"urls": urls})
        self.assertEqual(st, 200)
        it = j["items"]
        self.assertEqual((it[0]["s"], it[0]["x"]), (200, "miss"))
        self.assertEqual(base64.b64decode(it[1]["b"]), BIN)
        self.assertEqual(it[2]["s"], 404)                                  # ответ источника — это данные, не ошибка
        self.assertIn("err", it[3])
        self.assertEqual(it[4], {"err": "host not allowed"})
        st, j = self.post({"urls": [up.url("/a")]})
        self.assertEqual(j["items"][0]["x"], "hit")                        # второй раз из кэша

    def test_bad_requests(self):
        self.assertEqual(self.post({"urls": []})[0], 400)
        self.assertEqual(self.post({"urls": ["x"] * 101})[0], 400)
        self.assertEqual(self.post({"nope": 1})[0], 400)
        self.assertEqual(self.f.call(None, path="/v1/batch")[0], 405)


class ClientBatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load.load()

    def test_ext_get_many_and_fallback(self):
        m = self.m
        f = Fx()
        self.addCleanup(f.close)
        m._ds_batch_off[0] = 0
        with mock.patch.object(m, "ds_conf", return_value=(f.base, "")):
            res = m.ext_get_many([f.up.url("/a"), f.up.url("/boom")])
        self.assertEqual((res[0][0], res[0][1]), (200, b"hit1"))
        self.assertIsNone(res[1])
        with mock.patch.object(m, "ds_conf", return_value=("", "")):
            self.assertEqual(m.ext_get_many(["http://x/1", "http://x/2"]), [None, None])

    def test_spark_uses_batch_then_falls_back(self):
        m = self.m
        hist = {"history": {"columns": ["TRADEDATE", "CLOSE", "LEGALCLOSEPRICE", "BOARDID"],
                            "data": [["2024-01-02", 99.5, None, "TQCB"], ["2024-01-03", 100.1, None, "TQCB"]]}}
        body = json.dumps(hist).encode()
        m._spark_cache.clear()
        singles = []
        with mock.patch.object(m, "ext_get_many", return_value=[(200, body, "application/json"), None]), \
                mock.patch.object(m, "http_text", side_effect=lambda u, **k: singles.append(u) or json.dumps(hist)):
            out = m.spark_payload(["RU000A0001", "RU000A0002"])
        self.assertEqual(out["RU000A0001"], [99.5, 100.1])
        self.assertEqual(out["RU000A0002"], [99.5, 100.1])
        self.assertEqual(len(singles), 1)                                  # пакет не дал второй — взят обычным запросом


if __name__ == "__main__":
    unittest.main()
