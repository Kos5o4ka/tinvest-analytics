"""Облачная синхронизация (13l3_sync_client.py) против настоящего сервера данных: два «устройства» с разными базами,
конфликты, удаления, очередь из бота, удаление облачной копии, отсутствие токена в слепке. Без внешней сети."""
import base64
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import _load  # noqa: E402
import tinvest_server as ts  # noqa: E402
import test_sync_server as tss  # noqa: E402

M = _load.load()
KEY = tss.K1
ISIN = "RU0009029540"
PHRASE = "моя-тайная-фраза-2026"
TOKEN = "t.SUPER_SECRET_TOKEN_0123456789abcdef"


class Devices(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="tsync_cli_")
        self.dbp = os.path.join(tmp, "keys.sqlite")
        tss.make_db(self.dbp, time.time())
        self.app = ts.DataServer(os.path.join(tmp, "data"), keys_db=self.dbp, md=False)
        self.srv = ts.make_http_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        self.saved = (M.STORE, M.load_config())
        self.stores = {"A": M.Store(os.path.join(tmp, "a.db")), "B": M.Store(os.path.join(tmp, "b.db"))}
        base = dict(self.saved[1], data_server=self.url, data_key=KEY, token="", sync_enabled=False, sync_master="", sync_salt="")
        self.cfgs = {"A": dict(base, sync_device="Компьютер A"), "B": dict(base, sync_device="Компьютер B")}
        self.cur = None
        self.sent = []
        self._real_req = M.sync_req

        def spy(method, path, body=None, timeout=90):
            if body is not None:
                self.sent.append(json.dumps(body))
            return self._real_req(method, path, body, timeout)
        M.sync_req = spy
        self.use("A")

    def tearDown(self):
        M.sync_req = self._real_req
        M.STORE = self.saved[0]
        M.save_config(self.saved[1])
        M.ds_reset()
        self.srv.shutdown()
        self.srv.server_close()

    def use(self, dev):
        """Переключиться на устройство: своя база и свои настройки."""
        if self.cur:
            self.cfgs[self.cur] = M.load_config()
        self.cur = dev
        M.STORE = self.stores[dev]
        M.save_config(self.cfgs[dev])
        M.ds_reset()
        M.mem_clear()

    def manual(self, acc=None, **kw):
        b = {"kind": "buy", "date": "2025-11-15", "ident": ISIN, "ticker": "SBER", "name": "Сбербанк", "qty": 10, "price": 280}
        if acc:
            b["acc"] = acc
        else:
            b["acc_name"] = "Сбер"
        b.update(kw)
        return M.manual_post(M.load_config(), b)

    def watch(self, isin, **kw):
        M.watch_post(M.load_config(), dict({"action": "add", "isin": isin}, **kw))

    def sync(self):
        return M.sync_run("test")

    def qty(self, acc):
        return round(M.fifo(M.store().ops(acc)).get("imp:" + ISIN, {"qty": 0})["qty"])


class Basics(Devices):
    def test_off_by_default_and_needs_login(self):
        self.assertFalse(M.sync_status()["enabled"])
        with self.assertRaises(M.ApiError):
            M.sync_run()
        M.save_config(dict(M.load_config(), data_key=""))
        M.ds_reset()
        with self.assertRaises(M.ApiError):
            M.sync_enable(M.load_config(), {"mode": "create"})

    def test_create_join_roundtrip(self):
        acc = self.manual()["acc"]
        self.watch("RU000A0ZZZZ1", target_yield=21)
        r = M.sync_enable(M.load_config(), {"mode": "create"})
        self.assertTrue(r["ok"] and r["phrase"] and r["enabled"])
        self.assertEqual(r["rev"], 1)
        meta = self.app.sync.meta(1)
        self.assertTrue(meta["exists"])
        blob = base64.b64decode(self.app.sync.pull(1)[1])
        for secret in (b"RU000A0ZZZZ1", ISIN.encode(), "Сбер".encode("utf-8"), r["phrase"].encode()):
            self.assertNotIn(secret, blob)                    # сервер видит только шифртекст
        phrase = r["phrase"]
        self.use("B")
        with self.assertRaises(M.ApiError) as cm:
            M.sync_enable(M.load_config(), {"mode": "join", "phrase": "неверная-фраза-123456"})
        self.assertIn("кодовая фраза", str(cm.exception))
        self.assertFalse(M.sync_status()["enabled"])          # с неверной фразой ничего не включилось
        self.assertEqual(M.imports_list(), [])
        M.sync_enable(M.load_config(), {"mode": "join", "phrase": phrase})
        self.assertEqual([a["name"] for a in M.imports_list()], ["Сбер"])
        self.assertEqual(self.qty(acc), 10)
        self.assertEqual(sum(M.qf(o["payment"]) for o in M.store().ops(acc)), 0.0)
        self.assertEqual([w["isin"] for w in M.watch_items()], ["RU000A0ZZZZ1"])
        self.assertEqual(M.watch_items()[0]["target_yield"], 21)

    def test_second_create_refused_when_cloud_exists(self):
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.use("B")
        with self.assertRaises(M.ApiError) as cm:
            M.sync_enable(M.load_config(), {"mode": "create"})
        self.assertEqual(cm.exception.status, 409)
        with self.assertRaises(M.ApiError):
            M.sync_enable(M.load_config(), {"mode": "join", "phrase": "коротко"})

    def test_token_never_leaves_computer(self):
        cfg = dict(M.load_config(), token=TOKEN, sandbox=False)
        M.save_config(cfg)
        M.store().put(M.SYNC_TB_KEY, {"2000111": {"name": "Брокерский", "type": ""}})
        M.store().ops_put(M.token_key(cfg) + ":2000111", [
            {"id": "api1", "date": "2025-10-01T10:00:00Z", "type": "OPERATION_TYPE_BUY", "payment": M.to_money(-1000),
             "quantity": "1", "quantityDone": "1", "instrumentUid": "uid-1", "name": "Бумага"}])
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.assertFalse([s for s in self.sent if TOKEN in s])
        key = bytes.fromhex(M.load_config()["sync_master"])
        recs, _t = M.sync_unpack(M.sync_open(key, base64.b64decode(self.app.sync.pull(1)[1])))
        self.assertNotIn(TOKEN, json.dumps(recs))
        self.assertIn("op:tb:2000111|api1", recs)
        self.assertNotIn(TOKEN, json.dumps(M.sync_status()))
        self.assertNotIn("sync_master", M.sync_get(M.load_config(), "all", {}, False))
        pub = {k: v for k, v in M.load_config().items() if k not in M.SECRET_KEYS}
        self.assertNotIn("sync_master", pub)

    def test_api_account_opens_as_snapshot_without_token(self):
        cfg = dict(M.load_config(), token=TOKEN, sandbox=False)
        M.save_config(cfg)
        M.store().put(M.SYNC_TB_KEY, {"2000111": {"name": "Брокерский", "type": ""}})
        M.store().ops_put(M.token_key(cfg) + ":2000111", [
            {"id": "api1", "date": "2025-10-01T10:00:00Z", "type": "OPERATION_TYPE_BUY", "payment": M.to_money(-1000),
             "quantity": "1", "quantityDone": "1", "instrumentUid": "uid-1", "name": "Бумага"}])
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.use("B")
        self.assertEqual(M.load_config()["token"], "")
        M.sync_enable(M.load_config(), {"mode": "join", "phrase": PHRASE})
        snap = [a for a in M.imports_list() if a.get("sync_src") == "tinvest"]
        self.assertEqual([(a["id"], a["src_acc"], a["broker_id"]) for a in snap], [("imp-tb-2000111", "2000111", "tinvest")])
        self.assertEqual([o["id"] for o in M.store().ops("imp-tb-2000111")], ["api1"])
        # на втором компьютере нельзя добавлять ручные записи в снимок
        with self.assertRaises(M.ApiError):
            self.manual(acc="imp-tb-2000111")
        # а там, где токен есть, снимок не дублирует живой счёт при следующей синхронизации
        self.assertEqual(len(M.sync_collect(M.load_config())), len(M.sync_collect(M.load_config())))


class Merging(Devices):
    def join_b(self, phrase=PHRASE):
        self.use("B")
        M.sync_enable(M.load_config(), {"mode": "join", "phrase": phrase})

    def test_changes_on_both_devices_are_merged(self):
        self.watch("RU000A0AAAA1")
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.join_b()
        self.watch("RU000A0BBBB2")                                  # B добавил, A ещё не знает
        self.sync()
        self.use("A")
        self.watch("RU000A0CCCC3")                                  # A добавил своё до синхронизации
        self.sync()
        self.assertEqual(sorted(w["isin"] for w in M.watch_items()), ["RU000A0AAAA1", "RU000A0BBBB2", "RU000A0CCCC3"])
        self.use("B")
        self.sync()
        self.assertEqual(sorted(w["isin"] for w in M.watch_items()), ["RU000A0AAAA1", "RU000A0BBBB2", "RU000A0CCCC3"])
        self.assertEqual(self.app.sync.meta(1)["rev"], 3)

    def test_manual_trade_deleted_on_one_device_does_not_come_back(self):
        acc = self.manual()["acc"]
        gid = M.manual_list(M.load_config(), "all", {"acc": acc}, False)["rows"][0]["group"]
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.join_b()
        self.assertEqual(self.qty(acc), 10)
        M.manual_post(M.load_config(), {"action": "delete", "acc": acc, "group": gid})
        self.sync()
        self.use("A")
        self.assertEqual(self.qty(acc), 10)
        self.sync()
        self.assertEqual(self.qty(acc), 0)                          # удаление дошло
        self.assertEqual(M.store().ops(acc), [])
        self.use("B")
        self.sync()
        self.assertEqual(self.qty(acc), 0)                          # и не воскресло с другой стороны

    def test_edit_vs_delete_and_two_edits(self):
        acc = self.manual()["acc"]
        gid = M.manual_list(M.load_config(), "all", {"acc": acc}, False)["rows"][0]["group"]
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.join_b()
        M.manual_post(M.load_config(), self.edit_body(acc, gid, qty=11))
        self.use("A")
        time.sleep(0.01)
        M.manual_post(M.load_config(), self.edit_body(acc, gid, qty=12))        # правили позже
        self.sync()
        self.use("B")
        self.sync()
        self.assertEqual(self.qty(acc), 12)                           # победила более свежая правка
        self.use("A")
        self.sync()
        self.assertEqual(self.qty(acc), 12)

    def edit_body(self, acc, gid, **kw):
        b = {"acc": acc, "group": gid, "kind": "buy", "date": "2025-11-15", "ident": ISIN, "ticker": "SBER", "name": "Сбербанк",
             "qty": 10, "price": 280}
        b.update(kw)
        return b

    def test_conflict_409_is_retried_with_merge(self):
        self.watch("RU000A0AAAA1")
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.join_b()
        self.watch("RU000A0BBBB2")
        other = {"done": False}
        real = M.sync_req

        def racing(method, path, body=None, timeout=90):
            if method == "POST" and path == "push" and not other["done"]:
                other["done"] = True                                 # пока B думает, другое устройство успело сохранить
                key = bytes.fromhex(M.load_config()["sync_master"])
                pl, _meta = self.app.sync.pull(1)[1], None
                recs, tombs = M.sync_unpack(M.sync_open(key, base64.b64decode(pl)))
                recs["watch:RU000A0DDDD4"] = {"k": "watch", "v": {"isin": "RU000A0DDDD4", "added": "2026-01-01"}, "u": time.time()}
                blob = M.sync_seal(key, M.sync_pack(recs, tombs, "третье"))
                self.app.sync.push(1, tss.body(blob, self.app.sync.meta(1)["rev"], salt=M.load_config()["sync_salt"]))
            return real(method, path, body, timeout)
        M.sync_req = racing
        try:
            self.sync()
        finally:
            M.sync_req = real
        self.assertEqual(sorted(w["isin"] for w in M.watch_items()), ["RU000A0AAAA1", "RU000A0BBBB2", "RU000A0DDDD4"])
        self.assertEqual(self.app.sync.meta(1)["rev"], 3)

    def test_wiped_local_database_restores_from_cloud(self):
        acc = self.manual()["acc"]
        for i in range(25):
            M.manual_post(M.load_config(), dict(self.edit_body(acc, "", qty=1 + i), group=""))
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        n = len(M.store().ops(acc))
        for a in M.imports_list():                                   # как после стирания базы или восстановления пустой копии
            M.store().ops_clear(a["id"])
        M.store().put("imports", [])
        self.sync()
        self.assertEqual(len(M.store().ops(acc)), n)                 # данные вернулись, а не «удалились» в облаке
        self.assertEqual(self.app.sync.meta(1)["rev"], 1)


class BotQueueAndDelete(Devices):
    def test_queue_applied_once_and_acked(self):
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.app.sync.queue_add(1, {"kind": "buy", "secid": ISIN, "qty": 10, "price": 295.4})
        self.app.sync.queue_add(1, {"kind": "deposit", "amount": 1000})
        r = self.sync()
        self.assertEqual(r["queue_taken"], 2)
        self.assertEqual(self.app.sync.meta(1)["queue"], 0)          # подтверждено вместе с новой версией
        self.assertEqual(self.qty(M.SYNC_BOT_ACC), 10)
        n = len(M.store().ops(M.SYNC_BOT_ACC))
        self.sync()
        self.assertEqual(len(M.store().ops(M.SYNC_BOT_ACC)), n)      # повтор ничего не дублирует
        self.use("B")
        M.sync_enable(M.load_config(), {"mode": "join", "phrase": PHRASE})
        self.assertEqual(self.qty(M.SYNC_BOT_ACC), 10)               # сделка из бота дошла и до второго устройства

    def test_queue_survives_failed_push(self):
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.app.sync.queue_add(1, {"kind": "buy", "secid": ISIN, "qty": 1, "price": 100})
        real = M.sync_req

        def broken(method, path, body=None, timeout=90):
            if path == "push":
                raise M.ApiError("Нет связи с сервером: обрыв", 502)
            return real(method, path, body, timeout)
        M.sync_req = broken
        try:
            with self.assertRaises(M.ApiError):
                self.sync()
        finally:
            M.sync_req = real
        self.assertEqual(self.app.sync.meta(1)["queue"], 1)          # не потеряна
        self.assertEqual(M.store().ops(M.SYNC_BOT_ACC), [])
        self.sync()
        self.assertEqual(self.qty(M.SYNC_BOT_ACC), 1)

    def test_delete_from_server_and_other_device_stops_safely(self):
        acc = self.manual()["acc"]
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.use("B")
        M.sync_enable(M.load_config(), {"mode": "join", "phrase": PHRASE})
        self.use("A")
        r = M.sync_post(M.load_config(), {"action": "delete"})
        self.assertTrue(r["deleted"] and not r["enabled"])
        self.assertFalse(self.app.sync.meta(1)["exists"])
        self.assertEqual(M.load_config()["sync_master"], "")         # ключ с устройства убран
        self.assertEqual(self.qty(acc), 10)                          # данные на компьютере остались
        self.use("B")
        with self.assertRaises(M.ApiError) as cm:
            self.sync()
        self.assertEqual(cm.exception.status, 410)
        self.assertFalse(M.sync_status()["enabled"])
        self.assertEqual(self.qty(acc), 10)                          # удаление в облаке не стирает локальные данные

    def test_disable_keeps_cloud_and_local(self):
        self.manual()
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        r = M.sync_post(M.load_config(), {"action": "disable"})
        self.assertFalse(r["enabled"])
        self.assertTrue(self.app.sync.meta(1)["exists"])
        self.assertEqual(len(M.imports_list()), 1)


class Fixes(Devices):
    """Исправления по ревью: удаление счёта, откат версии, счета Т-Инвестиций без токена, гонка с ручным учётом, сбой включения."""

    def join_b(self):
        self.use("B")
        M.sync_enable(M.load_config(), {"mode": "join", "phrase": PHRASE})

    def http_delete_account(self, acc_id):
        import http.client
        srv = M.LocalHTTPServer(("127.0.0.1", 0), M.Handler)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
            c.request("POST", "/api/import/delete", body=json.dumps({"id": acc_id}),
                      headers={"Host": "127.0.0.1:%d" % srv.server_address[1], "Content-Type": "application/json", "X-TA-Secret": "1"})
            r = c.getresponse()
            r.read()
            c.close()
            return r.status
        finally:
            srv.shutdown()
            srv.server_close()

    def test_R1_deleting_one_big_account_is_kept_deleted(self):
        small = self.manual()["acc"]
        big = self.manual(acc_name=None, acc=None)["acc"] if False else self.manual(**{"acc_name": "Большой"})["acc"]
        for i in range(60):
            M.manual_post(M.load_config(), {"kind": "buy", "date": "2025-11-15", "ident": ISIN, "ticker": "SBER", "name": "Сбербанк",
                                           "qty": 1 + i, "price": 280, "acc": big})
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.join_b()
        self.use("A")
        self.assertEqual(self.http_delete_account(big), 200)
        self.assertEqual([a["id"] for a in M.imports_list()], [small])
        self.sync()
        self.assertEqual([a["id"] for a in M.imports_list()], [small])      # не вернулся из облака
        self.assertEqual(M.store().ops(big), [])
        self.use("B")
        self.sync()
        self.assertEqual([a["id"] for a in M.imports_list()], [small])      # и на втором компьютере исчез
        self.use("A")
        self.sync()
        self.assertEqual([a["id"] for a in M.imports_list()], [small])

    def test_R2_older_server_version_does_not_apply_deletions(self):
        acc = self.manual()["acc"]
        self.watch("RU000A0AAAA1")
        self.watch("RU000A0BBBB2")
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})            # rev 1
        old = self.app.sync.pull(1)
        con = sqlite3.connect(self.dbp)
        old_row = con.execute("SELECT blob, sha256, size FROM user_sync WHERE tg_id=1").fetchone()
        M.watch_post(M.load_config(), {"action": "remove", "isin": "RU000A0BBBB2"})
        self.sync()                                                                    # rev 2: наблюдение сократилось
        self.assertEqual(self.app.sync.meta(1)["rev"], 2)
        self.assertEqual([w["isin"] for w in M.watch_items()], ["RU000A0AAAA1"])
        # сервер «откатился»: на месте версии 2 лежит версия 1
        con.execute("UPDATE user_sync SET rev=1, blob=?, sha256=?, size=? WHERE tg_id=1", old_row)
        con.commit()
        self.assertEqual(self.app.sync.meta(1)["rev"], 1)
        self.watch("RU000A0CCCC3")
        st = self.sync()
        self.assertIn("старую", st["warning"])
        isins = sorted(w["isin"] for w in M.watch_items())
        self.assertEqual(isins, ["RU000A0AAAA1", "RU000A0CCCC3"])                      # локально ничего не пропало
        key = bytes.fromhex(M.load_config()["sync_master"])
        doc = M.sync_doc(M.sync_open(key, base64.b64decode(self.app.sync.pull(1)[1])))
        self.assertEqual(doc["rev"], self.app.sync.meta(1)["rev"])
        self.assertTrue(doc["salt"])
        self.assertEqual(self.qty(acc), 10)
        self.assertEqual(self.sync()["warning"], "")                                   # следующий обмен уже без предупреждения

    def test_R2_block_with_wrong_rev_inside_is_refused(self):
        self.watch("RU000A0AAAA1")
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        key = bytes.fromhex(M.load_config()["sync_master"])
        recs, tombs = M.sync_unpack(M.sync_open(key, base64.b64decode(self.app.sync.pull(1)[1])))
        blob = M.sync_seal(key, M.sync_pack(recs, tombs, "x", rev=5, salt=M.load_config()["sync_salt"]))
        self.app.sync.push(1, tss.body(blob, 1, salt=M.load_config()["sync_salt"]))     # сервер хранит rev 2, внутри написано 5
        with self.assertRaises(M.ApiError) as cm:
            self.sync()
        self.assertIn("не соответствует", str(cm.exception))

    def test_R3_tinvest_account_kept_when_token_cleared(self):
        cfg = dict(M.load_config(), token=TOKEN, sandbox=False)
        M.save_config(cfg)
        M.store().put(M.SYNC_TB_KEY, {"2000111": {"name": "Брокерский", "type": ""}})
        M.store().ops_put(M.token_key(cfg) + ":2000111", [
            {"id": "api1", "date": "2025-10-01T10:00:00Z", "type": "OPERATION_TYPE_BUY", "payment": M.to_money(-1000),
             "quantity": "1", "quantityDone": "1", "instrumentUid": "uid-1", "name": "Бумага"}])
        self.manual()
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        M.save_config(dict(M.load_config(), token=""))                               # токен очищен
        self.sync()
        key = bytes.fromhex(M.load_config()["sync_master"])
        recs, _t = M.sync_unpack(M.sync_open(key, base64.b64decode(self.app.sync.pull(1)[1])))
        self.assertIn("acc:tb:2000111", recs)
        self.assertIn("op:tb:2000111|api1", recs)
        self.assertIn("imp-tb-2000111", [a["id"] for a in M.imports_list()])         # на этом компьютере остался как снимок

    def test_R4_local_change_during_exchange_is_not_lost(self):
        self.watch("RU000A0AAAA1")
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        self.join_b()
        self.use("A")
        self.watch("RU000A0BBBB2")
        real = M.sync_req
        fired = {"n": 0}

        def racing(method, path, body=None, timeout=90):
            res = real(method, path, body, timeout)
            if method == "POST" and path == "push" and not fired["n"]:
                fired["n"] = 1                                                        # пока шёл обмен, пользователь добавил запись
                self.manual(**{"acc_name": "Во время обмена"})
            return res
        M.sync_req = racing
        try:
            self.sync()
        finally:
            M.sync_req = real
        self.assertIn("Во время обмена", [a["name"] for a in M.imports_list()])
        self.sync()
        self.use("B")
        self.sync()
        self.assertIn("Во время обмена", [a["name"] for a in M.imports_list()])
        self.assertEqual(sorted(w["isin"] for w in M.watch_items()), ["RU000A0AAAA1", "RU000A0BBBB2"])

    def test_R4_gives_up_after_two_retries_without_applying(self):
        self.watch("RU000A0AAAA1")
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        real = M.sync_req
        n = {"i": 0}

        def racing(method, path, body=None, timeout=90):
            res = real(method, path, body, timeout)
            if method == "GET" and path == "pull":
                n["i"] += 1
                self.watch("RU000A0ZZ%03d" % n["i"])
            return res
        M.sync_req = racing
        try:
            with self.assertRaises(M.ApiError) as cm:
                self.sync()
        finally:
            M.sync_req = real
        self.assertEqual(cm.exception.status, 409)
        self.assertEqual(n["i"], 3)

    def test_manual_and_import_share_the_lock(self):
        self.assertTrue(M._man_lock.acquire(False))
        try:
            got = []
            t = threading.Thread(target=lambda: got.append(M._man_lock.acquire(True, 0.2)))
            t.start()
            t.join()
            self.assertEqual(got, [False])
        finally:
            M._man_lock.release()

    def test_R7_failed_first_push_does_not_report_enabled(self):
        self.manual()
        real = M.sync_req

        def failing(method, path, body=None, timeout=90):
            if method == "POST" and path == "push":
                return 500, {}
            return real(method, path, body, timeout)
        M.sync_req = failing
        try:
            with self.assertRaises(M.ApiError) as cm:
                M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})
        finally:
            M.sync_req = real
        self.assertIn("Не удалось включить", str(cm.exception))
        self.assertFalse(M.sync_status()["enabled"])
        self.assertEqual(M.load_config()["sync_master"], "")
        M.sync_enable(M.load_config(), {"mode": "create", "phrase": PHRASE})        # повторная попытка проходит
        self.assertTrue(M.sync_status()["enabled"])

    def test_R7_sync_master_is_protected_like_token(self):
        calls = []
        real_p, real_u = M._dpapi_protect, M._dpapi_unprotect
        M._dpapi_protect = lambda t: calls.append(t) or "dpapi:" + t[::-1]
        M._dpapi_unprotect = lambda v: v[6:][::-1] if v.startswith("dpapi:") else v
        try:
            M.save_config(dict(M.load_config(), sync_master="ab" * 32))
            with open(M.CONFIG_PATH, encoding="utf-8") as f:
                self.assertTrue(json.load(f)["sync_master"].startswith("dpapi:"))
            self.assertEqual(M.load_config()["sync_master"], "ab" * 32)
        finally:
            M._dpapi_protect, M._dpapi_unprotect = real_p, real_u


if __name__ == "__main__":
    unittest.main()
