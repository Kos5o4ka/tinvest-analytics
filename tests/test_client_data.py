"""Клиент данных: лента техдефолтов (фильтр «мой», ссылки, имя эмитента, кэш), срез рынка (gzip, 304, откат), резерв календаря. Без сети."""
import gzip
import json
import time
import unittest
import urllib.error
from unittest import mock

from _load import load

M = load()


def _msg(**kw):
    f = {"doc_id": 777, "title": "Сообщение о неисполнении обязательств", "published": "2026-11-20T10:00:00", "isin": "RU000A10EG10",
         "inn": "7701234567", "url": "https://e-disclosure.azipi.ru/messages/777/",
         "data": {"obligation": "coupon", "coupon_no": 4, "status": "technical"}}
    f.update(kw)
    return f


class Feed(unittest.TestCase):
    def _feed(self, raw, issuer=None, desc=None):
        with mock.patch.object(M, "ds_parsed", return_value=raw), \
                mock.patch.object(M, "issuer_of", return_value=issuer), \
                mock.patch.object(M, "_disc_issue_desc", return_value=desc or {}), \
                mock.patch.object(M, "_dfl_executed", return_value=None):
            return M.defaults_feed("2026-01-01", [])

    def test_issuer_name_not_subject(self):
        r = self._feed([_msg()], issuer={"short": "ООО Ромашка", "title": "ООО Ромашка полное"})[0]
        self.assertEqual(r["issuer"], "ООО Ромашка")
        self.assertEqual(r["subject"], "Сообщение о неисполнении обязательств")

    def test_issuer_fallback_to_issue_name_then_isin(self):
        r = self._feed([_msg()], issuer=None, desc={"name": "Ромашка 001Р-01"})[0]
        self.assertEqual(r["issuer"], "Ромашка 001Р-01")
        r = self._feed([_msg()], issuer=None, desc={})[0]
        self.assertEqual(r["issuer"], "RU000A10EG10")           # тема сообщения в поле эмитента не попадает
        self.assertNotIn("неисполнении", r["issuer"])

    def test_issuer_title_equal_isin_ignored(self):
        with mock.patch.object(M, "issuer_of", return_value={"title": "RU000A10EG10"}), \
                mock.patch.object(M, "_disc_issue_desc", return_value={"name": "Выпуск"}):
            self.assertEqual(M._dfl_issuer_name("RU000A10EG10"), "Выпуск")

    def test_url_from_server_and_built(self):
        self.assertEqual(M.dfl_msg_url({"url": "https://e-disclosure.azipi.ru/messages/5/"}), "https://e-disclosure.azipi.ru/messages/5/")
        self.assertEqual(M.dfl_msg_url({"doc_id": 42}), "https://e-disclosure.azipi.ru/messages/42/")
        self.assertEqual(M.dfl_msg_url({"url": "javascript:alert(1)", "doc_id": 42}), "https://e-disclosure.azipi.ru/messages/42/")
        self.assertIsNone(M.dfl_msg_url({"url": "http://evil.example/x"}))
        r = self._feed([_msg(url=None)], issuer={"short": "Э"})[0]
        self.assertEqual(r["url"], "https://e-disclosure.azipi.ru/messages/777/")


class Get(unittest.TestCase):
    def setUp(self):
        self.calls = 0
        M.store().write("DELETE FROM kv WHERE k LIKE 'dfl_feed_v2:%'")

    def _get(self, q, force=False, own=("A",)):
        def feed(since, isins, schedule=False):
            self.calls += 1
            return [{"isin": "A", "date": "2026-11-01"}, {"isin": "B", "date": "2026-11-02"}]
        mk = {"isins": ["B"], "scan": {"running": False, "done": 0, "total": 0, "error": None}, "ts": 1}
        with mock.patch.object(M, "defaults_feed", side_effect=feed), \
                mock.patch.object(M, "_disc_own_isins", return_value=list(own)), \
                mock.patch.object(M, "dfl_market", return_value=mk), \
                mock.patch.object(M, "_dfl_refresh_bg") as bg:
            return M.defaults_get({"token": "t"}, "all", q, force), bg

    def test_my_filters_strictly_mine(self):
        out, _ = self._get({"scope": "my", "days": "30"}, force=True)
        self.assertEqual([r["isin"] for r in out["rows"]], ["A"])
        self.assertTrue(all(r["mine"] for r in out["rows"]))

    def test_market_keeps_all(self):
        out, _ = self._get({"scope": "market", "days": "30"}, force=True)
        self.assertEqual({r["isin"]: r["mine"] for r in out["rows"]}, {"A": True, "B": False})

    def test_cache_hit_no_recompute_and_stale_refreshes(self):
        q = {"scope": "my", "days": "30"}
        self._get(q, force=True)
        self.assertEqual(self.calls, 1)
        out, bg = self._get(q)
        self.assertEqual(self.calls, 1)
        self.assertIn("cached_at", out)
        self.assertFalse(out["refreshing"])
        bg.assert_not_called()
        key = M._dfl_cache_key("", 30, True, "my", {"token": "t"}, "all")
        hit = M.store().get(key)
        hit["ts"] = time.time() - M.DFL_FEED_TTL - 5
        M.store().put(key, hit)
        out, bg = self._get(q)
        self.assertEqual(self.calls, 1)                          # старый результат отдан сразу
        self.assertTrue(out["refreshing"])
        bg.assert_called_once()

    def test_cache_key_has_no_token(self):
        k = M._dfl_cache_key("", 30, True, "my", {"token": "SECRET-TOKEN"}, "acc")
        self.assertNotIn("SECRET", k)


def _resp(body, headers=None, code=200):
    r = mock.MagicMock()
    r.status, r.headers = code, headers or {}
    r.read.return_value = body
    r.__enter__.return_value = r
    return r


def _snap(age=0):
    return {"ok": True, "v": 1, "data": {"empty": False, "kind": "stocks", "updated_at": time.time() - age,
                                         "data": [{"secid": "SBER", "chg_w": 1.5, "chg_m": 2.5}]}}


class Snapshot(unittest.TestCase):
    def setUp(self):
        M._mkt_snap_etag.clear()
        M._mkt_snap_mem.clear()
        M.store().write("DELETE FROM kv WHERE k LIKE 'market_snap_%'")
        self.p = mock.patch.object(M, "ds_conf", return_value=("https://srv.test", "key1"))
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_gunzip_and_headers(self):
        seen = {}

        def uo(req, timeout=0, context=None):
            seen.update(req.headers)
            return _resp(gzip.compress(json.dumps(_snap()).encode()), {"Content-Encoding": "gzip", "ETag": '"e1"'})
        with mock.patch.object(M.urllib.request, "urlopen", side_effect=uo):
            d = M.market_snapshot_get("stocks", force=True)
        self.assertEqual(d["data"][0]["secid"], "SBER")
        self.assertEqual(seen.get("Accept-encoding"), "gzip")
        self.assertEqual(seen.get("X-client-key"), "key1")
        self.assertNotIn("Authorization", seen)

    def test_plain_body_works(self):
        with mock.patch.object(M.urllib.request, "urlopen", return_value=_resp(json.dumps(_snap()).encode())):
            self.assertIsNotNone(M.market_snapshot_get("stocks", force=True))

    def test_gunzip_bomb_limited(self):
        with self.assertRaises(ValueError):
            M.snap_gunzip(gzip.compress(b"0" * 5000), limit=100)

    def test_304_uses_stored(self):
        with mock.patch.object(M.urllib.request, "urlopen", return_value=_resp(json.dumps(_snap()).encode(), {"ETag": '"e1"'})):
            M.market_snapshot_get("stocks", force=True)
        seen = {}

        def uo(req, timeout=0, context=None):
            seen.update(req.headers)
            raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)
        with mock.patch.object(M.urllib.request, "urlopen", side_effect=uo):
            d = M.market_snapshot_get("stocks", force=True)
        self.assertEqual(seen.get("If-none-match"), '"e1"')
        self.assertEqual(d["data"][0]["secid"], "SBER")

    def test_fallbacks_to_none(self):
        with mock.patch.object(M.urllib.request, "urlopen", side_effect=OSError("down")):
            self.assertIsNone(M.market_snapshot_get("stocks", force=True))
        with mock.patch.object(M.urllib.request, "urlopen", return_value=_resp(json.dumps({"ok": True, "data": {"empty": True}}).encode())):
            self.assertIsNone(M.market_snapshot_get("stocks", force=True))
        old = _snap(age=M.MARKET_SNAP_STALE + 60)
        with mock.patch.object(M.urllib.request, "urlopen", return_value=_resp(json.dumps(old).encode())):
            self.assertIsNone(M.market_snapshot_get("stocks", force=True))
            self.assertIsNone(M.market_snapshot_stocks())

    def test_stocks_changes_from_snapshot_else_history(self):
        snap = _snap()["data"]["data"]
        rows = [{"secid": "SBER", "value_today": 5, "chg_w": None, "chg_m": None}]
        with mock.patch.object(M, "market_snapshot_stocks", return_value=snap), mock.patch.object(M, "_stk_changes") as ch:
            M._stk_fill_changes(rows)
        ch.assert_not_called()
        self.assertEqual((rows[0]["chg_w"], rows[0]["chg_m"]), (1.5, 2.5))
        rows = [{"secid": "SBER", "value_today": 5, "chg_w": None, "chg_m": None},
                {"secid": "XX", "value_today": 1, "chg_w": None, "chg_m": None}]
        with mock.patch.object(M, "market_snapshot_stocks", return_value=snap), mock.patch.object(M, "_stk_changes") as ch:
            M._stk_fill_changes(rows)
        ch.assert_called_once()                                  # покрытия нет — прежний путь
        with mock.patch.object(M, "market_snapshot_stocks", return_value=None), mock.patch.object(M, "_stk_changes") as ch:
            M._stk_fill_changes(rows)
        ch.assert_called_once()


class CalFallback(unittest.TestCase):
    def test_rows_from_moex_boards(self):
        res = {"rows": [{"isin": "RU1", "name": "Эмит 1", "full": "Эмит 1 полн", "start": "2026-12-05", "book": ""},
                        {"isin": "RU2", "name": "Старый", "start": "2026-01-01"},
                        {"isin": "", "name": "Без isin", "start": "2026-12-06"}]}
        out = M.pv_calendar_fallback(res, "2026-11-28")
        self.assertEqual([r["isin"] for r in out], ["RU1"])
        self.assertEqual(out[0]["short"], "Эмит 1")

    def test_payload_uses_fallback(self):
        fb = [{"issuer": "Э", "short": "Э", "desc": "", "isin": "RU1", "start": "2026-12-05", "end": "", "book": "", "status": "", "link": ""}]
        with mock.patch.object(M, "primary_rows", side_effect=M.ApiError("investmint.ru закрыл доступ (HTTP 403)", 502)), \
                mock.patch.object(M, "pv_calendar_fallback", return_value=fb), \
                mock.patch.object(M, "_pri_scr_kick", return_value=False), \
                mock.patch.object(M, "key_rate_series", return_value=[]), \
                mock.patch.object(M, "primary_snapshot"):
            out = M.primary_payload()
        self.assertTrue(out["cal_fallback"])
        self.assertEqual(len(out["rows"]), 1)
        self.assertIn("403", out["cal_error"])


if __name__ == "__main__":
    unittest.main()
