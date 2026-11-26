"""Серверная проверка тревог (server/alerts.py) и её клиент в приложении (13j_watch.py):
совпадение правил и текстов, состав подписки (без токена и счетов), хранилище/проверка/дедупликация на сервере. Офлайн."""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import _load  # noqa: E402
import alerts as SA  # noqa: E402
import tinvest_server as ts  # noqa: E402

M = _load.load()
TODAY = date.today().isoformat()


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


TOKEN = "t.SECRET_TOKEN_abcdefghijklmnopqrstuvwxyz0123456789"
ACC_ID = "2000123456"


def make_db(path, now):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE users(tg_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, created REAL, consent REAL, "
               "banned INTEGER NOT NULL DEFAULT 0, plan TEXT NOT NULL DEFAULT 'free', notify INTEGER NOT NULL DEFAULT 1, "
               "plan_until REAL, trial_used INTEGER NOT NULL DEFAULT 0, pro_kind TEXT)")
    db.execute("CREATE TABLE keys(key_hash TEXT PRIMARY KEY, tg_id INTEGER NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, "
               "revoked INTEGER NOT NULL DEFAULT 0, last_used REAL)")
    db.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
    db.execute("INSERT INTO users(tg_id, username, plan_until) VALUES (1,'pro',?),(2,'free',NULL),(3,'gone',?)", (now + 30 * 86400, now + 30 * 86400))
    db.execute("INSERT INTO keys VALUES (?,1,?,?,0,NULL)", (ts.key_hash("TIA-AAAA-AAAA-AAAA"), now, now + 7 * 86400))
    db.execute("INSERT INTO keys VALUES (?,2,?,?,0,NULL)", (ts.key_hash("TIA-BBBB-BBBB-BBBB"), now, now + 7 * 86400))
    db.execute("INSERT INTO keys VALUES (?,3,?,?,0,NULL)", (ts.key_hash("TIA-CCCC-CCCC-CCCC"), now - 9 * 86400, now - 2 * 86400))
    db.commit()
    return db


GOALS = [  # (котировка, ty, tp)
    ({"yield": 21.5, "price": 97.1}, 20.0, None), ({"yield": 19.99, "price": 97.1}, 20.0, 98.0),
    ({"yield": 25.0, "price": 101.0}, 8.5, 101.0), ({"yield": None, "price": 80.0}, 9.0, 80.25), (None, 10.0, 90.0),
]
OFFERS = [
    {"isin": "RU000A100001", "name": "Выпуск <1>", "kind": "put", "date": d(20), "period_start": d(-3), "period_end": d(1),
     "coupon_status": "announced", "new_rate": 17.25},
    {"isin": "RU000A100002", "name": "Колл & Ко", "kind": "call", "date": d(10), "period_start": None, "period_end": None,
     "coupon_status": "pending", "new_rate": None},
    {"isin": "RU000A100003", "name": "Пут", "kind": "put", "date": d(400), "period_start": d(380), "period_end": d(385),
     "coupon_status": "pending", "new_rate": None},
    {"isin": "RU000A100004", "name": None, "kind": "put", "date": d(5), "period_start": d(-1), "period_end": d(0),
     "coupon_status": "pending", "new_rate": None},
]
PAYS = [(d(1), "coupon", "Выпуск А", 5123.4), (d(2), "amortization", "Выпуск Б", 12.5), (d(3), "offer", "Выпуск В", None),
        (d(4), "dividend", "Акция", 100000.0)]


class Parity(unittest.TestCase):
    """Правила и тексты сервера совпадают с приложением (ключи дедупликации — общие)."""

    def test_goals(self):
        for q, ty, tp in GOALS:
            a = M.watch_goal_alerts("RU000A0ZZZZ1", "Бумага", q, ty, tp, TODAY)
            b = SA.goal_alerts({"isin": "RU000A0ZZZZ1", "name": "Бумага", "target_yield": ty, "target_price": tp},
                               dict(q, name="Бумага") if q else None, TODAY)
            self.assertEqual([(x["id"], x["message"], x["kind"]) for x in a], [(x["id"], x["message"], x["kind"]) for x in b])
        self.assertEqual(len(M.watch_goal_alerts("X1234567", "n", {"yield": 21.5, "price": 97.1}, 20.0, 98.0, TODAY)), 2)

    def test_goal_ids_survive_json(self):
        """id цели строится из числа порога: после JSON-обмена (float) он должен остаться прежним."""
        for v in (9.0, 8.5, 101.0, 12.3456):
            p = SA.validate({"v": 1, "goals": [json.loads(json.dumps({"isin": "RU000A0ZZZZ1", "name": "x", "target_yield": v}))]})
            a = M.watch_goal_alerts("RU000A0ZZZZ1", "x", {"yield": 999, "price": 1}, v, None, TODAY)[0]["id"]
            b = SA.goal_alerts(p["goals"][0], {"yield": 999, "price": 1}, TODAY)[0]["id"]
            self.assertEqual(a, b)

    def alerts(self, n):
        out = []
        for i in range(n):
            out += M.watch_goal_alerts("RU000A1%05d" % i, "Очень длинное название выпуска <%d> & Ко " % i * 3,
                                       {"yield": 30.0, "price": 50.0}, 10.0 + i, 60.0, TODAY)
        return out

    def test_dispatch_plan(self):
        for n in (0, 1, 7, 40):
            al = self.alerts(n)
            a = M.tg_dispatch_plan("Наблюдение и цели", al, {}, time.time(), icon="⭐")
            b = SA.dispatch_plan("Наблюдение и цели", al, set(), icon="⭐")
            self.assertEqual([(t, [k for k, _ in ch]) for t, ch in a], b)
        al = self.alerts(3)
        sent = {al[0]["id"]: time.time()}
        a = M.tg_dispatch_plan("T", al, sent, time.time())
        b = SA.dispatch_plan("T", al, set(sent))
        self.assertEqual([(t, [k for k, _ in ch]) for t, ch in a], b)
        self.assertNotIn(al[0]["id"], b[0][1])

    def test_reminder_keys(self):
        notes = [{"id": "n1700000000000001", "isin": "RU000A100001", "name": "Б", "date": d(-10), "remind_on": d(0)},
                 {"id": "n1700000000000002", "isin": "RU000A100001", "name": "Б", "date": d(-10), "remind_on": d(3)}]
        r = SA.reminder_alerts(notes, TODAY)
        self.assertEqual([x["id"] for x in r], ["rm|n1700000000000001"])         # тот же ключ, что в watch_payload
        self.assertEqual(r[0]["kind"], "reminder")

    def test_offers(self):
        self.assertEqual(M.tg_offer_due(OFFERS, TODAY), SA.offer_due(OFFERS, TODAY))
        self.assertTrue(len(SA.offer_due(OFFERS, TODAY)) >= 4)

    def test_payments(self):
        fa = M.tg_pay_fresh(PAYS, {"pay|%s|coupon|Выпуск А" % d(1): 1})
        fb = SA.pay_fresh(PAYS, {"pay|%s|coupon|Выпуск А" % d(1)})
        self.assertEqual(fa, fb)
        self.assertEqual(M.tg_pay_text(7, fa), SA.pay_text(7, fb, TODAY))
        sub = [{"date": e[0], "kind": e[1], "name": e[2], "amount": e[3]} for e in PAYS] + [{"date": d(30), "kind": "coupon", "name": "Z", "amount": 1.0}]
        self.assertEqual(SA.pay_events(sub, TODAY, 7), sorted(PAYS, key=lambda x: (x[0], x[2])))

    def test_fit(self):
        t = "<b>заголовок</b>\n" + "\n".join("<b>строка %d</b> &amp; <a href=\"https://x\">ссылка</a>" % i for i in range(300))
        self.assertEqual(M._tg_fit(t, 3000), SA.fit(t, 3000))

    def test_quotes_like_screener(self):
        sec_cols = ["SECID", "ISIN", "SHORTNAME", "SECNAME", "MATDATE", "PREVLEGALCLOSEPRICE", "YIELDATPREVWAPRICE", "FACEUNIT",
                    "FACEVALUE", "COUPONPERCENT", "NEXTCOUPON", "OFFERDATE", "LISTLEVEL", "COUPONVALUE", "COUPONPERIOD", "BONDSUBTYPE",
                    "ISSUESIZE", "ACCRUEDINT", "BONDTYPE", "COUPON_DETAILS"]
        md_cols = ["SECID", "WAPRICE", "LAST", "YIELD", "YIELDATWAPRICE", "DURATION", "VALTODAY", "NUMTRADES", "ZSPREAD"]

        def sec(secid, isin, mat, plc, ypw):
            r = dict.fromkeys(sec_cols)
            r.update(SECID=secid, ISIN=isin, SHORTNAME="Б " + secid, SECNAME="x", MATDATE=mat, PREVLEGALCLOSEPRICE=plc,
                     YIELDATPREVWAPRICE=ypw, FACEUNIT="SUR", FACEVALUE=1000, COUPONVALUE=40, COUPONPERIOD=182)
            return [r[c] for c in sec_cols]

        def md(secid, wa, last, y, yw):
            r = dict.fromkeys(md_cols)
            r.update(SECID=secid, WAPRICE=wa, LAST=last, YIELD=y, YIELDATWAPRICE=yw, DURATION=400, VALTODAY=1e6, NUMTRADES=10)
            return [r[c] for c in md_cols]
        boards = {
            "TQCB": {"securities": {"columns": sec_cols, "data": [sec("A1", "RU000A1", d(900), 99.1, 18.123), sec("A2", "RU000A2", d(900), 98.0, None),
                                                                   sec("A3", "RU000A3", "0000-00-00", 97.0, 15.0), sec("A4", "RU000A4", d(500), 96.12345, 17.0)]},
                     "marketdata": {"columns": md_cols, "data": [md("A1", 99.5555, 99.4, 18.456, None), md("A2", None, 97.5, None, 19.019),
                                                                  md("A3", 97.0, 97.0, 15.0, None), md("A4", None, None, None, None)]}},
            "TQOB": {"securities": {"columns": sec_cols, "data": [sec("SU1", "RU000A1", d(2000), 70.0, 14.0)]},
                     "marketdata": {"columns": md_cols, "data": [md("SU1", 70.5, None, 14.5, None)]}},
        }
        orig = (M.http_text, M.kbd_at)
        M.http_text = lambda url, timeout=25: json.dumps(boards["TQCB" if "/TQCB/" in url else "TQOB"])
        M.kbd_at = lambda dur: None
        M._scr.update(t=0, rows=[])
        try:
            app = {r.get("isin") or r["id"]: r for r in M.screener_rows()}
        finally:
            M.http_text, M.kbd_at = orig
            M._scr.update(t=0, rows=[])
        srv = {}
        for b in ("TQCB", "TQOB"):
            SA.quotes_from_iss(boards[b], srv)
        self.assertEqual(sorted(app), sorted(srv))
        for k in app:
            self.assertEqual((app[k]["price"], app[k]["yield"], app[k]["name"]), (srv[k]["price"], srv[k]["yield"], srv[k]["name"]))

    def test_floater_and_currency_boards(self):
        self.assertIn("TQOD", SA.BOARDS)
        self.assertIn("TQOY", SA.BOARDS)
        iss_floater = {
            "securities": {"columns": ["SECID", "ISIN", "SHORTNAME", "MATDATE", "PREVLEGALCLOSEPRICE", "YIELDATPREVWAPRICE"],
                           "data": [["FLT1", "RU000A10FLT1", "Флоатер 1", d(365), 99.0, None]]},
            "marketdata": {"columns": ["SECID", "WAPRICE", "LAST", "YIELD", "YIELDATWAPRICE"],
                           "data": [["FLT1", 99.2, 99.3, None, None]]},
        }
        q = SA.quotes_from_iss(iss_floater)
        self.assertIn("RU000A10FLT1", q)
        self.assertEqual(q["RU000A10FLT1"]["price"], 99.2)
        self.assertIsNone(q["RU000A10FLT1"]["yield"])
        al = SA.goal_alerts({"isin": "RU000A10FLT1", "name": "Флоатер 1", "target_price": 100.0, "target_yield": 20.0},
                            q["RU000A10FLT1"], TODAY)
        self.assertEqual([a["id"] for a in al], ["gp|RU000A10FLT1|100.0"])

    def test_contract_boards_and_prefixes(self):
        """Контракт между приложением и сервером: площадки ISS, префиксы тревог и пороги оферт."""
        self.assertEqual(SA.BOARDS, ("TQCB", "TQOB", "TQOD", "TQOY"))
        self.assertEqual(SA.SENT_PREFIXES, M.TG_SRV_PREFIX)
        self.assertEqual(set(SA.SENT_PREFIXES), {"gy|", "gp|", "rm|", "ofr|", "pay|"})
        self.assertEqual(SA.TG_OFR_CALL_DAYS, M.TG_OFR_CALL_DAYS)
        self.assertEqual(SA.TG_OFR_CLOSE_DAYS, M.TG_OFR_CLOSE_DAYS)
        self.assertEqual(SA.EV, M._TG_EV)
        # validate сохраняет серверные префиксы и отбрасывает локальные (price|, mon|, offer|)
        sent_in = ["gp|RU000A1|99.0", "gy|RU000A1|15.0", "rm|n1", "ofr|RU000A1|2026-12-01|put",
                   "pay|2026-12-01|coupon|A", "mon|RU000A1", "offer|RU000A1", "price|RU000A1"]
        v = SA.validate({"v": 1, "sent": sent_in})
        self.assertEqual(v["sent"], ["gp|RU000A1|99.0", "gy|RU000A1|15.0", "rm|n1",
                                      "ofr|RU000A1|2026-12-01|put", "pay|2026-12-01|coupon|A"])

    def test_iss_quote_parity_currency_boards_and_floater(self):
        """Паритет разбора ISS для валютных площадок (TQOD/TQOY) и флоатеров без YIELD."""
        sec_cols = ["SECID", "ISIN", "SHORTNAME", "MATDATE", "PREVLEGALCLOSEPRICE", "YIELDATPREVWAPRICE"]
        md_cols = ["SECID", "WAPRICE", "LAST", "YIELD", "YIELDATWAPRICE"]
        tqod = {
            "securities": {"columns": sec_cols, "data": [["USD1", "RU000A10USD1", "Замещ USD", d(700), 94.5, 7.2]]},
            "marketdata": {"columns": md_cols, "data": [["USD1", 95.125, 95.2, 7.15, None]]},
        }
        tqoy = {
            "securities": {"columns": sec_cols, "data": [["CNY1", "RU000A10CNY1", "Юань 1", d(500), 98.0, None]]},
            "marketdata": {"columns": md_cols, "data": [["CNY1", None, 98.4, None, None]]},
        }
        q = {}
        SA.quotes_from_iss(tqod, q)
        SA.quotes_from_iss(tqoy, q)
        self.assertEqual(q["RU000A10USD1"], {"price": 95.125, "yield": 7.15, "name": "Замещ USD"})
        self.assertEqual(q["RU000A10CNY1"], {"price": 98.4, "yield": None, "name": "Юань 1"})
        for isin, ty, tp in [("RU000A10USD1", 7.0, 96.0), ("RU000A10CNY1", 10.0, 99.0)]:
            app_al = M.watch_goal_alerts(isin, q[isin]["name"], q[isin], ty, tp, TODAY)
            srv_al = SA.goal_alerts({"isin": isin, "name": q[isin]["name"], "target_yield": ty, "target_price": tp},
                                    q[isin], TODAY)
            self.assertEqual([(x["id"], x["message"]) for x in app_al], [(x["id"], x["message"]) for x in srv_al])


class Payload(unittest.TestCase):
    """Подписка из приложения: только разрешённые поля, без токена, счетов и текста заметок; сервер её принимает."""

    def setUp(self):
        self.saved = {k: getattr(M, k) for k in ("load_config", "imports_list", "_tg_offer_items", "_tg_payments", "_scr_by_isin", "tcat_info", "watch_items", "notes_all")}
        M.imports_list = lambda: []
        M._tg_offer_items = lambda cfg, today: [dict(o) for o in OFFERS]
        M._tg_payments = lambda cfg, days: list(PAYS)
        M._scr_by_isin = lambda: {"RU000A100001": {"name": "Выпуск 1"}}
        M.tcat_info = lambda isin: None
        M.watch_items = lambda: [{"isin": "RU000A100001", "added": TODAY, "target_yield": 20.0, "note": "моя заметка СЕКРЕТ"},
                                 {"isin": "RU000A100009", "added": TODAY}]
        M.notes_all = lambda: [{"id": "n1700000000000001", "isin": "RU000A100001", "date": d(-5), "text": "тайный текст заметки",
                                "remind_on": d(1)}, {"id": "n1700000000000002", "isin": "RU000A100001", "date": d(-5), "text": "без даты"}]

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(M, k, v)

    def cfg(self, **kw):
        c = {"token": TOKEN, "account": ACC_ID, "accounts": [ACC_ID], "tg_enabled": True, "tg_server": True, "tg_on_mon": True,
             "tg_on_watch": True, "tg_pay_days": 7, "data_key": "TIA-AAAA-AAAA-AAAA"}
        c.update(kw)
        return c

    def test_no_secrets(self):
        sent = {"gy|RU000A100001|20.0": 1.0, "price|RU000A1|": 2.0, "pay|%s|coupon|Выпуск А" % d(1): 3.0}
        p = M.tg_srv_payload(self.cfg(), sent)
        raw = json.dumps(p, ensure_ascii=False)
        for bad in (TOKEN, "SECRET_TOKEN", ACC_ID, "TIA-AAAA", "тайный текст", "СЕКРЕТ", "без даты", "account", "token"):
            self.assertNotIn(bad, raw)
        self.assertTrue(set(p) <= SA.TOP and "resume" not in p)
        for name, fields in SA.FIELDS.items():
            for it in p[name]:
                self.assertTrue(set(it) <= fields, (name, it))
        self.assertEqual([g["isin"] for g in p["goals"]], ["RU000A100001"])          # без целей бумага не уходит
        self.assertEqual(p["goals"][0]["name"], "Выпуск 1")
        self.assertEqual([r["id"] for r in p["reminders"]], ["n1700000000000001"])
        self.assertEqual(p["pay_days"], 7)
        self.assertEqual(sorted(p["sent"]), sorted(k for k in sent if not k.startswith("price|")))
        clean = SA.validate(json.loads(raw))
        self.assertEqual(len(clean["offers"]), len(OFFERS))
        self.assertEqual(len(clean["pays"]), len(PAYS))

    def test_switches_limit_payload(self):
        p = M.tg_srv_payload(self.cfg(tg_on_watch=False, tg_on_mon=False, tg_pay_days=0), {})
        self.assertEqual((p["goals"], p["reminders"], p["offers"], p["pays"], p["pay_days"]), ([], [], [], [], 0))
        p = M.tg_srv_payload(self.cfg(token=""), {})
        self.assertEqual((p["offers"], p["pays"]), ([], []))                         # без токена портфеля нет
        self.assertEqual(len(p["goals"]), 1)

    def test_imported_portfolio_without_token(self):
        extra = ("imports_list", "build_summary", "build_monitor", "watch_payload")
        saved_extra = {k: getattr(M, k) for k in extra}
        try:
            M.imports_list = lambda: [{"id": "imp-demo", "name": "Демо"}]
            M.build_summary = lambda cfg, a, b: {"portfolio": {"total": 123456.0, "daily": 100.0}}
            M.build_monitor = lambda cfg, a: {"summary": {"high": 1, "medium": 0}, "alerts": []}
            M.watch_payload = lambda cfg: {"items": [], "alerts": []}
            p = M.tg_srv_payload(self.cfg(token=""), {})
            self.assertEqual(len(p["offers"]), len(OFFERS))
            self.assertEqual(len(p["pays"]), len(PAYS))
            txt = M.tg_digest_text(self.cfg(token=""))
            self.assertIn("Портфель", txt)
            self.assertIn("Ближайшие 7 дней", txt)
            self.assertIn("Мониторинг", txt)
        finally:
            for k, v in saved_extra.items():
                setattr(M, k, v)


class Validation(unittest.TestCase):
    def test_rejects(self):
        ok = {"v": 1, "goals": [{"isin": "RU000A100001", "name": "x", "target_yield": 9}]}
        self.assertEqual(SA.validate(ok)["goals"][0]["target_yield"], 9.0)
        bad = [
            {"v": 2}, {"v": 1, "token": TOKEN}, {"v": 1, "goals": [{"isin": "RU000A100001", "token": "x"}]},
            {"v": 1, "goals": [{"isin": "bad isin!", "target_yield": 1}]}, {"v": 1, "goals": [{"isin": "RU000A100001", "target_yield": "9"}]},
            {"v": 1, "pays": [{"date": "2026-1-1", "kind": "coupon", "name": "x", "amount": 1}]},
            {"v": 1, "pays": [{"date": TODAY, "kind": "salary", "name": "x", "amount": 1}]},
            {"v": 1, "pays": [{"date": TODAY, "kind": "coupon", "name": "x", "amount": 1, "account_id": ACC_ID}]},
            {"v": 1, "reminders": [{"id": "x; drop", "isin": "RU000A100001", "date": TODAY, "remind_on": TODAY}]},
            {"v": 1, "reminders": [{"id": "n1", "isin": "RU000A100001", "date": TODAY, "remind_on": TODAY, "text": "секрет"}]},
            {"v": 1, "pay_days": 61}, {"v": 1, "offers": [{"isin": "RU000A100001", "kind": "other", "date": TODAY}]},
            {"v": 1, "goals": [{"isin": "RU000A100001", "target_yield": 1}] * 301}, "string", [],
        ]
        for b in bad:
            with self.assertRaises(SA.AlertError, msg=repr(b)[:100]) as cm:
                SA.validate(b)
            self.assertEqual(cm.exception.code, 400)
        v = SA.validate({"v": 1, "goals": [{"isin": "RU000A100001", "name": "a\x00b" + "я" * 500}], "sent": ["gy|x", "price|y", 5]})
        self.assertEqual(v["goals"], [])                                         # без порогов цель не хранится
        self.assertEqual(v["sent"], ["gy|x"])
        self.assertFalse(v["weekly_digest"])
        self.assertTrue(SA.validate({"v": 1, "weekly_digest": True})["weekly_digest"])
        for bad_opt in ({"v": 1, "weekly_digest": "yes"}, {"v": 1, "weekly_digest": 1},
                        {"v": 1, "bot_goals_rev": "1"}, {"v": 1, "bot_goals_rev": -1}, {"v": 1, "bot_goals_rev": True}):
            with self.assertRaises(SA.AlertError) as cm:
                SA.validate(bad_opt)
            self.assertEqual(cm.exception.code, 400)


class FakeNotifier:
    def __init__(self):
        self.msgs, self.sevs, self.fail = [], [], None

    def enqueue(self, uid, text, severity=0):
        if self.fail:
            raise ts.NotifyError(429, self.fail)
        self.msgs.append((uid, text))
        self.sevs.append(severity)
        return len(self.msgs)


class Server(unittest.TestCase):
    NOW = 1_790_000_000.0          # будний день, 12:00 МСК

    def setUp(self):
        from datetime import datetime
        self.NOW = datetime(2026, 11, 24, 12, 0, tzinfo=SA.MSK).timestamp()
        self.today = "2026-11-24"
        self.clock = [self.NOW]
        self.dbp = os.path.join(tempfile.mkdtemp(prefix="talerts_"), "keys.sqlite")
        self.db = make_db(self.dbp, self.NOW)
        self.st = SA.AlertStore(self.dbp, clock=lambda: self.clock[0])
        self.nt = FakeNotifier()
        self.fetches = []
        iss = {"securities": {"columns": ["SECID", "ISIN", "SHORTNAME", "MATDATE", "PREVLEGALCLOSEPRICE", "YIELDATPREVWAPRICE"],
                              "data": [["A1", "RU000A100001", "Выпуск 1", "2030-01-01", 95.0, 21.0]]},
               "marketdata": {"columns": ["SECID", "WAPRICE", "LAST", "YIELD", "YIELDATWAPRICE"], "data": [["A1", None, None, None, None]]}}

        def fetch(url):
            self.fetches.append(url)
            return iss if "/TQCB/" in url else None
        self.ck = SA.AlertChecker(self.st, self.nt, fetch, clock=lambda: self.clock[0])

    def sub(self, **kw):
        p = {"v": 1, "goals": [{"isin": "RU000A100001", "name": "x", "target_yield": 20.0}],
             "reminders": [{"id": "n1", "isin": "RU000A100001", "name": "x", "date": "2026-11-01", "remind_on": "2026-11-24"}],
             "offers": [{"isin": "RU000A100002", "name": "Колл", "kind": "call", "date": "2026-11-30"}],
             "pay_days": 3, "pays": [{"date": "2026-11-25", "kind": "coupon", "name": "Выпуск А", "amount": 512.3},
                                     {"date": "2026-12-20", "kind": "coupon", "name": "Позже", "amount": 1.0}]}
        p.update(kw)
        return SA.validate(p)

    def test_store_and_dedup(self):
        keys = self.st.put(1, self.sub(sent=["rm|n1"]))
        self.assertEqual(keys, ["rm|n1"])
        self.assertEqual(SA.summary(self.st.get(1)["sub"])["goals"], 1)
        s1 = self.ck.run_once()
        self.assertEqual(s1["users"], 1)
        texts = "\n".join(t for _u, t in self.nt.msgs)
        self.assertIn("Цель достигнута: доходность 21,00 %", texts)
        self.assertIn("колл", texts)
        self.assertIn("Выпуск А", texts)
        self.assertNotIn("Позже", texts)                                     # вне окна pay_days
        self.assertNotIn("Напоминание", texts)                               # уже отправлено приложением
        self.assertTrue(all(t.endswith(SA.TG_DISCLAIMER) for _u, t in self.nt.msgs))
        n = len(self.nt.msgs)
        self.ck.run_once()
        self.assertEqual(len(self.nt.msgs), n)                               # повторно не шлёт
        sent = set(self.st.sent_keys(1))
        self.assertTrue({"gy|RU000A100001|20.0", "ofr|RU000A100002|2026-11-30|call", "pay|2026-11-25|coupon|Выпуск А", "rm|n1"} <= sent)
        self.st.put(1, self.sub())                                          # обновление подписки не сбрасывает отправленное
        self.ck.run_once()
        self.assertEqual(len(self.nt.msgs), n)

    def test_rate_limited_retry(self):
        self.st.put(1, self.sub())
        self.nt.fail = "rate_limit"
        self.ck.run_once()
        self.assertEqual(self.st.sent_keys(1), [])
        self.nt.fail = None
        self.ck.run_once()
        self.assertTrue(self.nt.msgs)

    def test_quiet_hours_and_free(self):
        self.st.put(1, self.sub())
        self.st.put(2, self.sub())                                          # не Pro: хранится, но не проверяется
        self.clock[0] = self.NOW + 11 * 3600                                # 23:00 МСК
        self.ck.run_once()
        self.assertEqual(self.nt.msgs, [])
        self.clock[0] = self.NOW
        self.ck.run_once()
        self.assertEqual({u for u, _t in self.nt.msgs}, {1})
        self.assertIsNotNone(self.st.get(2))

    def test_purge(self):
        self.st.put(1, self.sub())
        self.st.put(3, self.sub())                                          # ключ истёк
        self.assertEqual(self.ck.run_once()["purged"], 1)
        self.assertIsNone(self.st.get(3))
        self.assertEqual(self.st.sent_keys(3), [])
        self.db.execute("UPDATE keys SET revoked=1 WHERE tg_id=1")
        self.db.commit()
        self.ck.run_once()
        self.assertIsNone(self.st.get(1))

    def test_delete_returns_sent(self):
        self.st.put(1, self.sub())
        self.ck.run_once()
        had, keys = self.st.delete(1)
        self.assertTrue(had and keys)
        self.assertIsNone(self.st.get(1))
        self.assertEqual(self.st.delete(1), (False, []))

    def test_delete_during_quotes_race(self):
        self.st.put(1, self.sub())
        orig_fetch = self.ck.fetch_json
        deleted = [False]

        def racing_fetch(url):
            if not deleted[0]:
                deleted[0] = True
                self.st.delete(1)
            return orig_fetch(url)

        self.ck.fetch_json = racing_fetch
        self.ck.run_once()
        self.assertEqual(self.nt.msgs, [])
        self.assertEqual(self.st.sent_keys(1), [])
        self.st.mark_sent(1, ["gy|RU000A100001|20.0"])
        self.assertEqual(self.st.sent_keys(1), [])

    def test_stopped_in_bot(self):
        self.st.put(1, self.sub())
        self.db.execute("INSERT INTO meta(k, v) VALUES('alerts_stop:1', '1')")
        self.db.commit()
        with self.assertRaises(SA.AlertError) as cm:
            self.st.put(1, self.sub())                                      # автоматическая синхронизация не возвращает подписку
        self.assertEqual(cm.exception.code, 409)
        self.st.put(1, self.sub(resume=True))                               # явное включение в приложении — снимает остановку
        self.assertIsNone(self.db.execute("SELECT 1 FROM meta WHERE k='alerts_stop:1'").fetchone())
        self.assertNotIn("resume", self.st.get(1)["sub"])

    def test_no_quotes_fetch_without_goals(self):
        self.st.put(1, self.sub(goals=[]))
        self.ck.run_once()
        self.assertEqual(self.fetches, [])

    def test_bot_goals_rev_not_clobbered(self):
        self.st.put(1, self.sub())
        rev = self.st.upsert_bot_goal(1, {"isin": "RU000A10BOT1", "name": "Бот-цель", "target_price": 95.0})
        self.assertEqual(rev, 1)
        # Десктоп без bot_goals_rev (или со старой ревизией 0) не затирает цель из бота
        self.st.put(1, self.sub(bot_goals_rev=0))
        cur = self.st.get(1)["sub"]
        self.assertEqual(cur["bot_goals_rev"], 1)
        self.assertEqual({g["isin"] for g in cur["goals"]}, {"RU000A100001", "RU000A10BOT1"})
        # После подтверждения ревизии bot_goals_rev=1 список десктопа становится авторитетным
        self.st.put(1, self.sub(bot_goals_rev=1))
        cur2 = self.st.get(1)["sub"]
        self.assertEqual(cur2["bot_goals_rev"], 1)
        self.assertEqual([g["isin"] for g in cur2["goals"]], ["RU000A100001"])

    def test_bot_goal_deletion_not_clobbered_and_watch_only(self):
        self.st.put(1, self.sub())
        rev = self.st.delete_bot_goal(1, "RU000A100001")
        self.assertEqual(rev, 1)
        # Устаревший sync (bot_goals_rev=0) не должен воскрешать удалённую ботом цель
        self.st.put(1, self.sub(bot_goals_rev=0))
        self.assertEqual(self.st.get(1)["sub"]["goals"], [])
        # Подтверждение ревизии bot_goals_rev=1 позволяет десктопу снова добавить цель
        self.st.put(1, self.sub(bot_goals_rev=1))
        self.assertEqual([g["isin"] for g in self.st.get(1)["sub"]["goals"]], ["RU000A100001"])

        # watch_only цели без порогов валидируются и не запрашивают котировки
        wo = SA.validate({"v": 1, "goals": [{"isin": "RU000A100002", "name": "w", "watch_only": True}]})
        self.assertEqual(wo["goals"], [{"isin": "RU000A100002", "name": "w", "watch_only": True}])
        rev2 = self.st.upsert_bot_goal(1, {"isin": "RU000A10BOT3", "name": "Watch", "watch_only": True})
        self.assertEqual(rev2, 2)
        self.st.put(1, SA.validate({"v": 1, "goals": [{"isin": "RU000A100002", "name": "w", "watch_only": True}], "bot_goals_rev": 2}))
        self.fetches.clear()
        self.ck.run_once()
        self.assertEqual(self.fetches, [])

    def test_high_severity_offer_close_marks_severity_2(self):
        self.st.put(1, self.sub(
            goals=[], reminders=[], pay_days=0, pays=[],
            offers=[{"isin": "RU000A100002", "name": "Пут", "kind": "put", "date": "2026-11-30",
                     "period_start": "2026-11-20", "period_end": "2026-11-25"}],
        ))
        self.ck.run_once()
        self.assertEqual(self.nt.sevs, [2])

    def test_stats_counts_and_max_checked(self):
        self.assertEqual(self.st.stats(), {"subs": 0, "last_checked": None})
        self.st.put(1, self.sub(weekly_digest=True))
        self.assertTrue(self.st.get(1)["sub"]["weekly_digest"])
        self.ck.run_once()
        st = self.st.stats()
        self.assertEqual(st["subs"], 1)
        self.assertEqual(st["last_checked"], self.NOW)


class EndToEnd(unittest.TestCase):
    """Приложение -> настоящий сервер данных (HTTP, база ключей во временной папке)."""

    def setUp(self):
        now = time.time()
        tmp = tempfile.mkdtemp(prefix="talerts_e2e_")
        self.dbp = os.path.join(tmp, "keys.sqlite")
        make_db(self.dbp, now).close()
        self.app = ts.DataServer(os.path.join(tmp, "data"), keys_db=self.dbp, md=False)
        self.srv = ts.make_http_server(self.app, "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        self.saved = {k: getattr(M, k) for k in ("tg_srv_payload",)}
        M.tg_srv_payload = lambda cfg, sent: {"v": 1, "goals": [{"isin": "RU000A100001", "name": "x", "target_price": 99.0}],
                                              "sent": sorted(k for k in sent if k.startswith(M.TG_SRV_PREFIX))}
        self.conf(data_server=self.url, data_key="TIA-AAAA-AAAA-AAAA", tg_enabled=True, tg_server=True)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(M, k, v)
        self.conf(data_server="off", data_key="", tg_enabled=False, tg_server=False)
        M.store().put(M.TG_SRV_KEY, {})
        self.srv.shutdown()
        self.srv.server_close()

    def conf(self, **kw):
        c = M.load_config()
        c.update(kw)
        M.save_config(c)
        M.ds_reset()

    def test_sync_status_delete(self):
        sent = {"gp|RU000A100001|99.0": time.time()}
        self.assertTrue(M._tg_srv_sync(M.load_config(), sent, force=True))
        self.assertTrue(M.tg_srv_active(M.load_config()))
        self.assertEqual(M.tg_srv_get(M.load_config(), None, {}, False)["counts"]["goals"], 1)
        code, j = M.tg_srv_req("status")
        self.assertEqual((code, j["active"]), (200, True))
        st = SA.AlertStore(self.dbp)
        self.assertEqual(st.sent_keys(1), ["gp|RU000A100001|99.0"])
        raw = sqlite3.connect(self.dbp).execute("SELECT data FROM alert_subs").fetchone()[0]
        self.assertNotIn("TIA-", raw)
        # неизменная подписка повторно не отправляется
        st.conn().execute("UPDATE alert_subs SET updated=0")
        M._tg_srv_sync(M.load_config(), sent)
        self.assertEqual(st.get(1)["updated"], 0)
        r = M.tg_srv_post(M.load_config(), {"action": "delete"})
        self.assertTrue(r["deleted"])
        self.assertFalse(M.load_config()["tg_server"])
        self.assertIsNone(st.get(1))
        self.assertIn("gp|RU000A100001|99.0", M.store().get(M.TG_SENT_KEY))

    def test_free_and_unsupported(self):
        self.conf(data_key="TIA-BBBB-BBBB-BBBB")
        self.assertFalse(M._tg_srv_sync(M.load_config(), {}, force=True))
        self.assertIn("Pro", M._tg_srv_state()["err"])
        code, j = M.tg_srv_req("sync", {"v": 1, "token": TOKEN})
        self.assertEqual(code, 402)
        self.conf(data_key="TIA-AAAA-AAAA-AAAA")
        code, j = M.tg_srv_req("sync", {"v": 1, "token": TOKEN})
        self.assertEqual((code, j["error"]), (400, "bad_field"))
        code, _j = M.tg_srv_req("nope", {})
        self.assertEqual(code, 404)

    def test_bot_stop_turns_mode_off(self):
        self.assertTrue(M._tg_srv_sync(M.load_config(), {}, force=True))
        db = sqlite3.connect(self.dbp)
        db.execute("DELETE FROM alert_subs")
        db.execute("INSERT INTO meta(k, v) VALUES('alerts_stop:1', '1')")
        db.commit()
        self.assertFalse(M._tg_srv_sync(M.load_config(), {}, force=True))
        self.assertFalse(M.load_config()["tg_server"])
        self.assertIn("/alerts", M._tg_srv_state()["err"])
        self.conf(tg_server=True)
        self.assertTrue(M.tg_srv_post(M.load_config(), {"action": "sync"})["ok"])     # явное включение

    def test_tick_skips_server_kinds(self):
        """Пока сервер принял подписку, программа не шлёт цели/напоминания сама, а остальные тревоги — шлёт."""
        saved = {k: getattr(M, k) for k in ("watch_payload", "tg_send", "watch_isins", "_tg_srv_sync", "notes_all", "defaults_alerts",
                                            "flows_watch_alerts")}
        sent_texts = []
        M.watch_payload = lambda cfg: {"alerts": [
            {"id": "gy|RU000A100001|9.0", "kind": "goal", "severity": "medium", "isin": "RU000A100001", "name": "Цель", "message": "goal"},
            {"id": "pr|RU000A100001", "kind": "liquidity", "severity": "medium", "isin": "RU000A100001", "name": "Ликв", "message": "liq"}]}
        M.watch_isins = lambda: ["RU000A100001"]
        M.notes_all = lambda: []
        M.tg_send = lambda cfg, text: sent_texts.append(text)
        M._tg_srv_sync = lambda cfg, sent, force=False: True
        M.defaults_alerts = lambda cfg, sent=None: []
        M.flows_watch_alerts = lambda cfg: []
        M.store().put(M.TG_SENT_KEY, {})
        try:
            self.conf(tg_on_mon=False)
            M.store().put(M.TG_SRV_KEY, {"active": True, "ok": time.time()})
            M.tg_tick(manual=True)
            joined = "\n".join(sent_texts)
            self.assertIn("Ликв", joined)
            self.assertNotIn("Цель", joined)
            M.store().put(M.TG_SRV_KEY, {"active": False})
            M.store().put(M.TG_SENT_KEY, {})
            sent_texts.clear()
            M.tg_tick(manual=True)
            self.assertIn("Цель", "\n".join(sent_texts))
        finally:
            for k, v in saved.items():
                setattr(M, k, v)
            M.store().put(M.TG_SENT_KEY, {})

    def test_health_and_sync_bot_goals(self):
        import urllib.request
        st = SA.AlertStore(self.dbp)
        rev = st.upsert_bot_goal(1, {"isin": "RU000A10BOT2", "name": "Бот 2", "target_yield": 18.5})
        self.assertEqual(rev, 1)
        code, j = M.tg_srv_req("sync", {"v": 1, "goals": [{"isin": "RU000A100001", "name": "x", "target_price": 99.0}],
                                        "weekly_digest": True})
        self.assertEqual(code, 200)
        self.assertEqual(j["bot_goals_rev"], 1)
        self.assertEqual({g["isin"] for g in j["goals"]}, {"RU000A100001", "RU000A10BOT2"})
        st.checked(1)
        with urllib.request.urlopen(self.url + "/v1/health", timeout=5) as r:
            h = json.loads(r.read().decode("utf-8"))
        self.assertEqual(h["alerts_subs"], 1)
        self.assertIsNotNone(h["alerts_last_checked"])

    def test_notify_optional_severity_and_alerts_value_error(self):
        import sqlite3
        import urllib.error
        import urllib.request

        def post_notify(payload):
            req = urllib.request.Request(
                self.url + "/v1/notify",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json", "X-Client-Key": "TIA-AAAA-AAAA-AAAA"},
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode("utf-8"))

        self.assertEqual(post_notify({"text": "срочно", "severity": 2})[0], 200)
        self.assertEqual(post_notify({"text": "тоже срочно", "severity": "high"})[0], 200)
        self.assertEqual(post_notify({"text": "плохо", "severity": 9})[0], 400)
        self.assertEqual(post_notify({"text": "плохо", "severity": True})[0], 400)
        db = sqlite3.connect(self.dbp)
        sevs = [r[0] for r in db.execute("SELECT severity FROM outbox ORDER BY id")]
        self.assertEqual(sevs, [2, 2])
        SA.AlertStore(self.dbp).conn().close()
        db.execute("INSERT OR REPLACE INTO alert_subs(tg_id, data, created, updated) VALUES(1, '{bad_json', 1, 1)")
        db.commit()
        db.close()
        code, j = M.tg_srv_req("status")
        self.assertEqual(code, 500)
        self.assertEqual(j.get("error"), "internal_error")

    def test_offer_items_filters_non_isin_tickers(self):
        saved = {k: getattr(M, k) for k in ("build_bonds", "moex_bondization", "moex_bond_options")}
        queried = []
        try:
            M.build_bonds = lambda cfg, acc: {"rows": [
                {"isin": "SBER", "qty": 1, "name": "Short"},
                {"isin": "СБЕР", "qty": 1, "name": "Cyrillic"},
                {"isin": "RU000A100001", "qty": 1, "name": "Valid"},
            ]}
            M.moex_bondization = lambda isin: (queried.append(isin), {"coupons": [], "offers": []})[1]
            M.moex_bond_options = lambda isin: []
            M._tg_offer_items({}, "2026-11-24")
            self.assertEqual(queried, ["RU000A100001"])
        finally:
            for k, v in saved.items():
                setattr(M, k, v)


if __name__ == "__main__":
    unittest.main()
