"""Тесты раздела «Данные на компьютере»: размер и состав папки, очистка кэша, полное удаление. Без сети."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


def put(base, rel, n):
    p = os.path.join(base, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(b"x" * n)


class LocalData(unittest.TestCase):
    def test_info_breakdown(self):
        base = tempfile.mkdtemp(prefix="ld_info_")
        put(base, "data.db", 1000)
        put(base, "data.db-wal", 200)
        put(base, "logos/a.png", 300)
        put(base, "logos/sub/b.png", 50)
        put(base, "app/prog.py", 4000)
        put(base, "config.json", 10)
        put(base, "stray.txt", 7)
        d = M.local_data_info(base)
        by = {p["key"]: p["bytes"] for p in d["parts"]}
        self.assertEqual(by["db"], 1200)
        self.assertEqual(by["logos"], 350)
        self.assertEqual(by["app"], 4000)
        self.assertEqual(by["config"], 10)
        self.assertEqual(by["cache"], 0)
        self.assertEqual(by["other"], 7)
        self.assertEqual(d["total"], sum(by.values()))
        self.assertEqual(d["total"], 1200 + 350 + 4000 + 10 + 7)

    def test_symlink_not_followed(self):
        base = tempfile.mkdtemp(prefix="ld_link_")
        outside = tempfile.mkdtemp(prefix="ld_out_")
        put(outside, "big.bin", 100000)
        try:
            os.symlink(outside, os.path.join(base, "logos"))
        except OSError as e:                                 # Windows без прав администратора / режима разработчика
            self.skipTest("символические ссылки недоступны: %s" % e)
        self.assertLess(M.local_data_info(base)["total"], 5000)
        M._ld_empty_dir(os.path.join(base, "logos"))        # ссылка на папку — не трогаем содержимое цели
        M._ld_remove(os.path.join(base, "logos"))           # удаляется только сама ссылка
        self.assertTrue(os.path.exists(os.path.join(outside, "big.bin")))
        self.assertFalse(os.path.lexists(os.path.join(base, "logos")))

    def test_clear_cache_keeps_user_data(self):
        st = M.store()
        st.put("imports", [{"id": "imp-1"}])
        st.put(M.WATCH_KEY, [{"isin": "RU000A0JX0J2"}])
        st.put("some_cache_key", {"a": 1})
        st.write("INSERT OR REPLACE INTO candles(uid, d, c) VALUES('u','2024-01-01',1.0)")
        st.write("INSERT OR REPLACE INTO ops(acc, k, d, v) VALUES('imp-1','k1','2024-01-01','{}')")
        st.write("INSERT OR REPLACE INTO ops(acc, k, d, v) VALUES('real','k2','2024-01-01','{}')")
        put(M.APP_DIR, "logos/x.png", 100)
        put(M.APP_DIR, "cache/y.bin", 100)
        put(M.APP_DIR, "app/keep.py", 100)
        M.save_config(dict(M.load_config(), notify_days=5))
        r = M.clear_local_cache()
        self.assertTrue(r["ok"])
        self.assertIsNone(st.get("some_cache_key"))
        self.assertEqual(st.get("imports"), [{"id": "imp-1"}])
        self.assertEqual(st.get(M.WATCH_KEY), [{"isin": "RU000A0JX0J2"}])
        self.assertEqual(st.conn().execute("SELECT COUNT(*) FROM candles").fetchone()[0], 0)
        self.assertEqual(st.conn().execute("SELECT COUNT(*) FROM ops").fetchone()[0], 2)
        self.assertEqual(os.listdir(os.path.join(M.APP_DIR, "logos")), [])
        self.assertEqual(os.listdir(os.path.join(M.APP_DIR, "cache")), [])
        self.assertTrue(os.path.exists(os.path.join(M.APP_DIR, "app", "keep.py")))
        self.assertTrue(os.path.exists(M.CONFIG_PATH))

    def test_api_cache_clear_preserves_user_data(self):
        st = M.store()
        st.put("imports", [{"id": "imp-1"}])
        st.put(M.WATCH_KEY, [{"isin": "RU000A107HG1", "added": "2026-11-24"}])
        st.put(M.NOTES_KEY, [{"id": "n1", "isin": "RU000A107HG1", "date": "2026-11-24", "text": "keep"}])
        st.put(M.TAX_SETTINGS_KEY, {"ndfl_rate": 15, "iis": {}, "loss_carry": {}})
        st.put(M._WI_KEY, {"points": []})
        st.put("some_ephemeral_cache", {"x": 1})
        st.write("INSERT OR REPLACE INTO ops(acc, k, d, v) VALUES('imp-1','k1','2024-01-01','{}')")
        st.write("INSERT OR REPLACE INTO ops(acc, k, d, v) VALUES('real-acc','k2','2024-01-01','{}')")

        srv = M.LocalHTTPServer(("127.0.0.1", 0), M.Handler)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        try:
            port = srv.server_address[1]
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("POST", "/api/cache/clear", body=b"{}",
                      headers={"Host": "127.0.0.1:%d" % port, "Content-Type": "application/json"})
            r = c.getresponse()
            body = json.loads(r.read() or b"{}")
            c.close()
        finally:
            srv.shutdown()
            srv.server_close()

        self.assertEqual(r.status, 200)
        self.assertTrue(body.get("ok"))
        self.assertIsNone(st.get("some_ephemeral_cache"))
        self.assertEqual(st.get("imports"), [{"id": "imp-1"}])
        self.assertEqual(st.get(M.WATCH_KEY), [{"isin": "RU000A107HG1", "added": "2026-11-24"}])
        self.assertEqual(st.get(M.NOTES_KEY), [{"id": "n1", "isin": "RU000A107HG1", "date": "2026-11-24", "text": "keep"}])
        self.assertEqual(st.get(M.TAX_SETTINGS_KEY), {"ndfl_rate": 15, "iis": {}, "loss_carry": {}})
        self.assertEqual(st.get(M._WI_KEY), {"points": []})
        # операции Т-Инвестиций сброшены для перезагрузки из API, импортированные сохранены
        accs = [x[0] for x in st.conn().execute("SELECT acc FROM ops").fetchall()]
        self.assertEqual(accs, ["imp-1"])

    def test_delete_all_keeps_app(self):
        base = tempfile.mkdtemp(prefix="ld_wipe_")
        for rel in ("data.db", "config.json", "logos/a.png", "cache/b", "window/p", "window.json", "app/run.py"):
            put(base, rel, 10)
        r = M.delete_all_local_data(base)
        self.assertEqual(sorted(os.listdir(base)), ["app"])
        self.assertEqual(r["info"]["total"], 10)


class WatchSyncTests(unittest.TestCase):
    def setUp(self):
        M.store().put(M.WATCH_KEY, [])
        M.store().put(M.TG_SRV_KEY, {})

    def test_weekly_digest_payload_and_save(self):
        p0 = M.tg_srv_payload({}, {})
        self.assertIs(p0["weekly_digest"], False)

        res = M.tg_save({}, {"tg_weekly_digest": True})
        self.assertTrue(res["settings"]["tg_weekly_digest"])
        cfg = M.load_config()
        self.assertTrue(cfg.get("tg_weekly_digest"))
        p1 = M.tg_srv_payload(cfg, {})
        self.assertIs(p1["weekly_digest"], True)

    def test_bot_goals_back_sync_preserves_local_fields(self):
        st = M.store()
        st.put(M.WATCH_KEY, [
            {"isin": "RU000A107HG1", "added": "2026-10-01", "note": "моя заметка", "target_yield": 18.0},
        ])
        calls = []

        def fake_req(path, body=None, timeout=20):
            calls.append((path, body))
            return 200, {
                "ok": True,
                "bot_goals_rev": 1,
                "goals": [
                    {"isin": "RU000A107HG1", "target_yield": 21.5, "target_price": 97.25},
                    {"isin": "RU000A108EF2", "target_price": 99.0},
                ],
                "counts": {"goals": 2},
            }

        orig_req = M.tg_srv_req
        M.tg_srv_req = fake_req
        try:
            ok = M._tg_srv_sync({"tg_server": True, "tg_enabled": True}, {}, force=True)
        finally:
            M.tg_srv_req = orig_req

        self.assertTrue(ok)
        items = {x["isin"]: x for x in st.get(M.WATCH_KEY)}
        self.assertEqual(items["RU000A107HG1"]["added"], "2026-10-01")
        self.assertEqual(items["RU000A107HG1"]["note"], "моя заметка")
        self.assertEqual(items["RU000A107HG1"]["target_yield"], 21.5)
        self.assertEqual(items["RU000A107HG1"]["target_price"], 97.25)
        self.assertEqual(items["RU000A108EF2"]["target_price"], 99.0)
        self.assertTrue(items["RU000A108EF2"].get("added"))
        self.assertEqual(st.get(M.TG_SRV_KEY).get("bot_goals_rev"), 1)

        # Повторная синхронизация с тем же bot_goals_rev не должна перезаписывать локальную правку
        st.put(M.WATCH_KEY, [
            {"isin": "RU000A107HG1", "added": "2026-10-01", "note": "моя заметка", "target_yield": 22.0},
        ])
        M.tg_srv_req = fake_req
        try:
            M._tg_srv_sync({"tg_server": True, "tg_enabled": True}, {}, force=True)
        finally:
            M.tg_srv_req = orig_req
        items2 = {x["isin"]: x for x in st.get(M.WATCH_KEY)}
        self.assertEqual(items2["RU000A107HG1"]["target_yield"], 22.0)
        self.assertNotIn("RU000A108EF2", items2)

    def test_tg_srv_sync_sends_bot_goals_rev_and_clears_omitted_and_deletions(self):
        st = M.store()
        st.put(M.WATCH_KEY, [
            {"isin": "RU000A107HG1", "added": "2026-10-01", "note": "заметка", "target_yield": 18.0, "target_price": 95.0},
            {"isin": "RU000A108EF2", "added": "2026-10-01", "target_price": 99.0},
            {"isin": "RU000A109999", "added": "2026-10-01"},
        ])
        sent_revs = []
        responses = [
            {"ok": True, "bot_goals_rev": 1, "goals": [{"isin": "RU000A107HG1", "target_price": 97.0}],
             "bot_deleted": ["RU000A108EF2"], "counts": {"goals": 1}},
            {"ok": True, "bot_goals_rev": 2, "goals": [], "bot_deleted": ["RU000A107HG1"], "counts": {"goals": 0}},
        ]

        def fake_req(path, body=None, timeout=20):
            sent_revs.append(body.get("bot_goals_rev"))
            return 200, responses.pop(0)

        orig_req = M.tg_srv_req
        M.tg_srv_req = fake_req
        try:
            M._tg_srv_sync({"tg_server": True, "tg_enabled": True}, {}, force=True)
            items1 = {x["isin"]: x for x in st.get(M.WATCH_KEY)}
            # target_yield был опущен сервером -> очищен; RU000A108EF2 удалён (нет заметки); RU000A109999 без целей сохранён
            self.assertNotIn("target_yield", items1["RU000A107HG1"])
            self.assertEqual(items1["RU000A107HG1"]["target_price"], 97.0)
            self.assertNotIn("RU000A108EF2", items1)
            self.assertIn("RU000A109999", items1)

            M._tg_srv_sync({"tg_server": True, "tg_enabled": True}, {}, force=True)
            items2 = {x["isin"]: x for x in st.get(M.WATCH_KEY)}
            # Последняя цель удалена ботом -> target_price очищен, но note сохранена
            self.assertNotIn("target_price", items2["RU000A107HG1"])
            self.assertEqual(items2["RU000A107HG1"]["note"], "заметка")
            self.assertIn("RU000A109999", items2)
        finally:
            M.tg_srv_req = orig_req

        self.assertEqual(sent_revs, [0, 1])

    def test_tg_srv_sync_keeps_goals_missing_in_reply(self):
        """Бумага, которой нет в ответе сервера, но не удалённая в боте, сохраняет цели; при выключенном
        наблюдении (программа не шлёт цели) ответ сервера целей не трогает."""
        st = M.store()
        base = [{"isin": "RU000A107HG1", "added": "2026-10-01", "target_yield": 18.0},
                {"isin": "RU000A108EF2", "added": "2026-10-01", "target_price": 99.0}]
        reply = {"ok": True, "bot_goals_rev": 1, "goals": [], "counts": {"goals": 0}}
        orig_req = M.tg_srv_req
        M.tg_srv_req = lambda path, body=None, timeout=20: (200, dict(reply))
        try:
            for cfg in ({"tg_server": True, "tg_enabled": True},
                        {"tg_server": True, "tg_enabled": True, "tg_on_watch": False}):
                st.put(M.WATCH_KEY, [dict(x) for x in base])
                st.put(M.TG_SRV_KEY, {})
                M._tg_srv_sync(cfg, {}, force=True)
                items = {x["isin"]: x for x in st.get(M.WATCH_KEY)}
                self.assertEqual(items["RU000A107HG1"]["target_yield"], 18.0)
                self.assertEqual(items["RU000A108EF2"]["target_price"], 99.0)
        finally:
            M.tg_srv_req = orig_req


if __name__ == "__main__":
    unittest.main()
