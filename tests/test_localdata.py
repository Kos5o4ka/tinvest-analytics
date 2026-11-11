"""Тесты раздела «Данные на компьютере»: размер и состав папки, очистка кэша, полное удаление. Без сети."""
import os
import sys
import tempfile
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
        os.symlink(outside, os.path.join(base, "logos"))
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

    def test_delete_all_keeps_app(self):
        base = tempfile.mkdtemp(prefix="ld_wipe_")
        for rel in ("data.db", "config.json", "logos/a.png", "cache/b", "window/p", "window.json", "app/run.py"):
            put(base, rel, 10)
        r = M.delete_all_local_data(base)
        self.assertEqual(sorted(os.listdir(base)), ["app"])
        self.assertEqual(r["info"]["total"], 10)


if __name__ == "__main__":
    unittest.main()
