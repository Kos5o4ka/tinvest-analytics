"""Облачная синхронизация, ядро (13l2_sync_core.py): шифрование, трёхстороннее слияние, надгробия, очередь из бота, состав слепка."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

M = _load.load()
DAY = 86400


def R(v, u, k="watch"):
    return {"k": k, "v": v, "u": u}


class Crypto(unittest.TestCase):
    def setUp(self):
        self.salt = M.sync_new_salt()
        self.key = M.sync_derive("правильная-фраза-123", self.salt)

    def test_roundtrip_and_server_cannot_read(self):
        recs = {"watch:RU000A0ZZZZ1": R({"isin": "RU000A0ZZZZ1", "note": "секретная заметка"}, 5)}
        blob = M.sync_seal(self.key, M.sync_pack(recs, {"x": 1.0}))
        self.assertNotIn("секретная".encode("utf-8"), blob)
        self.assertNotIn(b"RU000A0ZZZZ1", blob)
        back, tombs = M.sync_unpack(M.sync_open(self.key, blob))
        self.assertEqual((back, tombs), (recs, {"x": 1.0}))

    def test_wrong_phrase_and_tamper(self):
        blob = M.sync_seal(self.key, b"hello")
        other = M.sync_derive("другая-фраза-12345", self.salt)
        with self.assertRaises(M.SyncError):
            M.sync_open(other, blob)
        bad = bytearray(blob)
        bad[25] ^= 1
        with self.assertRaises(M.SyncError):
            M.sync_open(self.key, bytes(bad))
        with self.assertRaises(M.SyncError):
            M.sync_open(self.key, b"short")

    def test_phrase_rules_and_salt(self):
        with self.assertRaises(M.SyncError):
            M.sync_derive("коротко", self.salt)
        self.assertNotEqual(M.sync_derive("правильная-фраза-123", M.sync_new_salt()), self.key)
        ph = M.sync_new_phrase()
        self.assertEqual(len(ph.split("-")), 5)
        self.assertNotEqual(ph, M.sync_new_phrase())

    def test_unknown_version(self):
        import zlib
        with self.assertRaises(M.SyncError):
            M.sync_unpack(zlib.compress(json.dumps({"v": 99, "recs": {}}).encode()))
        with self.assertRaises(M.SyncError):
            M.sync_unpack(b"not zlib")


class Merge(unittest.TestCase):
    NOW = 1_000_000.0

    def merge(self, base, local, remote, tl=None, tr=None):
        return M.sync_merge(base, local, remote, tl or {}, tr or {}, self.NOW)

    def test_one_side_edit_wins_over_unchanged(self):
        b = {"watch:A": R({"n": 1}, 10)}
        m, _t = self.merge(b, {"watch:A": R({"n": 2}, 20)}, dict(b))
        self.assertEqual(m["watch:A"]["v"], {"n": 2})
        m, _t = self.merge(b, dict(b), {"watch:A": R({"n": 3}, 30)})
        self.assertEqual(m["watch:A"]["v"], {"n": 3})

    def test_both_edit_newer_wins_and_union_of_additions(self):
        b = {"watch:A": R({"n": 1}, 10)}
        m, _t = self.merge(b, {"watch:A": R({"n": 2}, 50), "watch:L": R({"x": 1}, 50)},
                           {"watch:A": R({"n": 3}, 40), "watch:R": R({"x": 2}, 40)})
        self.assertEqual(m["watch:A"]["v"], {"n": 2})
        self.assertEqual(set(m), {"watch:A", "watch:L", "watch:R"})

    def test_local_delete_propagates_when_remote_unchanged(self):
        b = {"note:1": R({"t": "a"}, 10)}
        m, t = self.merge(b, {}, dict(b), tl={"note:1": self.NOW - 5})
        self.assertNotIn("note:1", m)
        self.assertIn("note:1", t)

    def test_remote_delete_propagates_when_local_unchanged(self):
        b = {"note:1": R({"t": "a"}, 10)}
        m, _t = self.merge(b, dict(b), {}, tr={"note:1": self.NOW - 5})
        self.assertNotIn("note:1", m)

    def test_delete_vs_edit_later_wins(self):
        b = {"note:1": R({"t": "a"}, 10)}
        m, _t = self.merge(b, {"note:1": R({"t": "правка"}, 200)}, {}, tr={"note:1": 100})
        self.assertEqual(m["note:1"]["v"], {"t": "правка"})          # правили позже удаления
        m, _t = self.merge(b, {"note:1": R({"t": "правка"}, 50)}, {}, tr={"note:1": 100})
        self.assertNotIn("note:1", m)                                   # удалили позже правки

    def test_deleted_record_does_not_resurrect_from_stale_device(self):
        """Устройство без прежнего состояния (новое) приносит удалённую запись со старой меткой: надгробие сильнее."""
        m, _t = self.merge({}, {"note:1": R({"t": "a"}, 0)}, {}, tr={"note:1": 100})
        self.assertNotIn("note:1", m)

    def test_account_files_union_and_orphan_ops_dropped(self):
        a1 = R({"id": "imp-1", "name": "A", "files": [{"sha256": "aa", "name": "1.csv"}]}, 20, "acc")
        a2 = R({"id": "imp-1", "name": "B", "files": [{"sha256": "bb", "name": "2.csv"}]}, 30, "acc")
        b = {"acc:imp-1": R({"id": "imp-1", "name": "A", "files": []}, 10, "acc")}
        m, _t = self.merge(b, {"acc:imp-1": a1}, {"acc:imp-1": a2})
        self.assertEqual({f["sha256"] for f in m["acc:imp-1"]["v"]["files"]}, {"aa", "bb"})
        self.assertEqual(m["acc:imp-1"]["v"]["name"], "B")
        ops = {"op:imp-2|x": R({"id": "x"}, 5, "op"), "op:imp-1|y": R({"id": "y"}, 5, "op")}
        m, _t = self.merge({}, {**ops, "acc:imp-1": a1}, {})
        self.assertIn("op:imp-1|y", m)
        self.assertNotIn("op:imp-2|x", m)                               # у счёта imp-2 нет записи: операции не нужны

    def test_tombstones_expire(self):
        _m, t = self.merge({}, {}, {}, tr={"old": self.NOW - 181 * DAY, "fresh": self.NOW - 10 * DAY})
        self.assertEqual(set(t), {"fresh"})

    def test_idempotent(self):
        b = {"watch:A": R({"n": 1}, 10)}
        l = {"watch:A": R({"n": 2}, 50), "watch:B": R({"n": 1}, 50)}
        r = {"watch:A": R({"n": 3}, 40)}
        m1, t1 = self.merge(b, l, r)
        m2, t2 = self.merge(m1, m1, m1, tl=t1, tr=t1)
        self.assertEqual((m1, t1), (m2, t2))

    def test_merge_does_not_mutate_inputs(self):
        b = {"watch:A": R({"n": 1}, 10)}
        l = {"watch:A": R({"n": 2}, 50)}
        snap = json.dumps([b, l], sort_keys=True)
        self.merge(b, l, {})
        self.assertEqual(json.dumps([b, l], sort_keys=True), snap)


class LocalView(unittest.TestCase):
    def test_timestamps_and_deletions(self):
        base = {"recs": {"watch:A": R({"n": 1}, 10), "watch:B": R({"n": 1}, 10), "watch:C": R({"n": 1}, 10)}, "tombs": {}}
        cur = {"watch:A": {"k": "watch", "v": {"n": 1}}, "watch:B": {"k": "watch", "v": {"n": 2}}, "watch:N": {"k": "watch", "v": {}}}
        recs, tombs, eff = M.sync_local_view(cur, base, 500.0)
        self.assertEqual(recs["watch:A"]["u"], 10)          # не менялась
        self.assertEqual(recs["watch:B"]["u"], 500.0)       # изменена
        self.assertEqual(recs["watch:N"]["u"], 500.0)       # новая
        self.assertEqual(tombs, {"watch:C": 500.0})         # пропала: удаление
        self.assertIs(eff, base)

    def test_first_sync_has_zero_timestamps(self):
        recs, _t, _b = M.sync_local_view({"watch:A": {"k": "watch", "v": {}}}, {}, 500.0)
        self.assertEqual(recs["watch:A"]["u"], 0)

    def test_wiped_database_is_not_mass_deletion(self):
        base = {"recs": {"op:imp-1|%d" % i: R({"i": i}, 10, "op") for i in range(30)}, "tombs": {}}
        base["recs"]["acc:imp-1"] = R({"id": "imp-1"}, 10, "acc")
        recs, tombs, eff = M.sync_local_view({}, base, 500.0)
        self.assertEqual(tombs, {})                         # ничего не объявлено удалённым
        self.assertEqual(eff["recs"], {})                   # прежнее состояние отброшено: данные вернутся из облака
        m, _t = M.sync_merge(eff["recs"], recs, base["recs"], tombs, {}, 500.0)
        self.assertEqual(len(m), 31)

    def test_api_operations_are_never_inferred_deleted(self):
        base = {"recs": {"op:tb:111|a": R({"id": "a"}, 10, "op"), "watch:X": R({}, 10)}, "tombs": {}}
        _r, tombs, _b = M.sync_local_view({}, base, 500.0)
        self.assertEqual(set(tombs), {"watch:X"})


class QueueAndCollect(unittest.TestCase):
    def test_bot_queue_makes_manual_ops_idempotently(self):
        items = [{"id": 5, "created_at": 1_700_000_000, "op": {"kind": "buy", "secid": "sber", "qty": 10, "price": 295.4}},
                 {"id": 6, "created_at": 1_700_000_100, "op": {"kind": "sell", "secid": "SBER", "qty": 4, "price": 300, "date": "2026-11-20"}},
                 {"id": 7, "created_at": 1_700_000_200, "op": {"kind": "deposit", "amount": 5000}},
                 {"id": 8, "created_at": 1, "op": {"kind": "buy", "secid": "", "qty": 1, "price": 1}},          # мусор
                 {"id": 9, "created_at": 1, "op": {"kind": "note", "isin": "RU0009029540", "text": "проверить отчёт"}}]
        recs, ids = M.sync_queue_recs(items, 2e9)
        self.assertEqual(ids, [5, 6, 7, 8, 9])               # непригодные тоже подтверждаются: очередь не копится
        buy = recs["op:%s|man-bot5" % M.SYNC_BOT_ACC]["v"]
        self.assertEqual((buy["type"], buy["_ident"], buy["_manual"], buy["quantity"]), ("OPERATION_TYPE_BUY", "SBER", True, "10"))
        self.assertEqual(M.qf(buy["payment"]), -2954.0)
        self.assertEqual(M.qf(recs["op:%s|man-bot5-c" % M.SYNC_BOT_ACC]["v"]["payment"]), 2954.0)
        self.assertEqual(recs["op:%s|man-bot6" % M.SYNC_BOT_ACC]["v"]["date"], "2026-11-20T12:00:00Z")
        self.assertEqual(M.qf(recs["op:%s|man-bot7" % M.SYNC_BOT_ACC]["v"]["payment"]), 5000.0)
        self.assertNotIn("op:%s|man-bot8" % M.SYNC_BOT_ACC, recs)
        self.assertEqual(recs["note:nb9"]["v"]["isin"], "RU0009029540")
        self.assertIn("acc:" + M.SYNC_BOT_ACC, recs)
        again, _ids = M.sync_queue_recs(items, 2e9)
        self.assertEqual(set(again), set(recs))                # повторная обработка даёт те же записи, а не дубли

    def test_collect_has_no_token_and_no_demo(self):
        tok = "t.SECRET_TOKEN_ZZZ_0123456789"
        cfg = dict(M.load_config(), token=tok, sandbox=False, targets={"bond": 70})
        recs = M.sync_collect(cfg)
        self.assertNotIn(tok, json.dumps(recs))
        self.assertEqual(recs["cfg:targets"]["v"], {"bond": 70})
        self.assertFalse([r for r in recs if r.startswith("acc:imp-demo")])
        self.assertIn("sync_master", M.SECRET_KEYS)


if __name__ == "__main__":
    unittest.main()
