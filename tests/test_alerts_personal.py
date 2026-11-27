"""Личные тихие часы и часовой пояс, сводка из нескольких срабатываний (server/alerts.py, 15.5). Офлайн."""
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import alerts as SA  # noqa: E402
import test_watch_server as W  # noqa: E402


class Quiet(unittest.TestCase):
    def test_quiet_local_rules(self):
        t = lambda h, tz=3: datetime(2026, 11, 24, h, 30, tzinfo=SA.timezone(SA.timedelta(hours=tz))).timestamp()   # noqa: E731
        self.assertTrue(SA.quiet_local(t(23), 3, 22, 8))
        self.assertTrue(SA.quiet_local(t(2), 3, 22, 8))
        self.assertFalse(SA.quiet_local(t(12), 3, 22, 8))
        self.assertTrue(SA.quiet_local(t(13), 3, 12, 15))                  # дневные часы без перехода через полночь
        self.assertFalse(SA.quiet_local(t(7), 3, 12, 15))
        self.assertFalse(SA.quiet_local(t(23), 3, None, None))
        self.assertFalse(SA.quiet_local(t(23), 3, 10, 10))                 # начало == конец: тихих часов нет (как в боте)
        now = datetime(2026, 11, 24, 12, 30, tzinfo=SA.MSK).timestamp()    # 12:30 МСК = 21:30 при UTC+12
        self.assertFalse(SA.quiet_local(now, 3, 22, 8))
        self.assertFalse(SA.quiet_local(now, 12, 22, 8))
        self.assertTrue(SA.quiet_local(now + 3600, 12, 22, 8))             # через час там 22:30: тихо

    def test_old_database_without_columns(self):
        p = os.path.join(tempfile.mkdtemp(prefix="tprefs_"), "keys.sqlite")
        W.make_db(p, 1.0).close()                                          # в схеме теста нет quiet_from/quiet_to/tz_offset
        self.assertEqual(SA.prefs_of(SA.AlertStore(p), 1), (None, None, 3))


class Checker(unittest.TestCase):
    """Проверка тревог с личными настройками из таблицы users (как их пишет бот)."""
    sub = W.Server.sub

    def setUp(self):
        W.Server.setUp(self)
        for col, ddl in (("quiet_from", "INTEGER"), ("quiet_to", "INTEGER"), ("tz_offset", "INTEGER NOT NULL DEFAULT 3")):
            self.db.execute("ALTER TABLE users ADD COLUMN %s %s" % (col, ddl))
        self.db.commit()
        self.ck.quiet_hours = (22, 8)

    def prefs(self, uid, qf, qt, tz=3):
        self.db.execute("UPDATE users SET quiet_from=?, quiet_to=?, tz_offset=? WHERE tg_id=?", (qf, qt, tz, uid))
        self.db.commit()

    def test_personal_quiet_hours_beat_default(self):
        self.st.put(1, self.sub())
        self.prefs(1, 12, 14)                                              # у пользователя тихо днём, в 12:00 МСК
        self.ck.run_once()
        self.assertEqual(self.nt.msgs, [])
        self.assertEqual(self.st.sent_keys(1), [])                         # ничего не помечено отправленным: придёт после тишины
        self.prefs(1, 14, 16)
        self.ck.run_once()
        self.assertTrue(self.nt.msgs)

    def test_default_applies_in_users_own_timezone(self):
        self.st.put(1, self.sub())
        self.prefs(1, None, None, 12)                                      # свои часы не заданы, пояс UTC+12; сейчас 21:00 у него
        self.clock[0] = self.NOW + 3600                                    # 22:00 у него: общие тихие часы 22-8 уже действуют
        self.ck.run_once()
        self.assertEqual(self.nt.msgs, [])
        self.clock[0] = self.NOW                                           # 21:00 у него: можно
        self.ck.run_once()
        self.assertTrue(self.nt.msgs)

    def test_equal_hours_mean_no_window_but_null_means_default(self):
        """Бот при «выкл» пишет 0 и 0: окна нет, общие 22-8 не действуют. NULL — пользователь ничего не настраивал."""
        self.st.put(1, self.sub())
        self.clock[0] = self.NOW + 11 * 3600                               # 23:00 по Москве
        self.prefs(1, None, None)
        self.ck.run_once()
        self.assertEqual(self.nt.msgs, [])                                 # не настроено: общее окно 22-8
        self.prefs(1, 0, 0)
        self.ck.run_once()
        self.assertTrue(self.nt.msgs)                                      # выключено явно: сообщения приходят
        self.assertEqual(SA.prefs_of(self.st, 1)[:2], (0, 0))

    def test_one_user_quiet_does_not_block_another(self):
        self.st.put(1, self.sub())
        self.db.execute("UPDATE users SET plan_until=? WHERE tg_id=2", (self.NOW + 30 * 86400,))
        self.db.commit()
        self.st.put(2, self.sub())
        self.prefs(1, 12, 14)
        self.ck.run_once()
        self.assertEqual({u for u, _t in self.nt.msgs}, {2})

    def test_today_follows_users_timezone(self):
        """Окно выплат считается от местного «сегодня» пользователя, а не московского."""
        sub = self.sub(goals=[], reminders=[], offers=[], pay_days=1,
                       pays=[{"date": "2026-11-24", "kind": "coupon", "name": "Выпуск А", "amount": 10.0}])
        self.ck.quiet_hours = None
        self.clock[0] = datetime(2026, 11, 24, 15, 0, tzinfo=SA.MSK).timestamp()      # в Москве ещё 24.11, а при UTC+12 уже 25.11
        self.st.put(1, sub)
        self.prefs(1, None, None, 12)
        self.ck.run_once()
        self.assertEqual(self.nt.msgs, [])                                 # для него 24.11 уже вчера
        self.prefs(1, None, None, 3)
        self.ck.run_once()
        self.assertIn("Выпуск А", "".join(t for _u, t in self.nt.msgs))

    def test_several_events_become_one_digest(self):
        self.st.put(1, self.sub())                                         # оферта + цель + напоминание + выплата: три сообщения
        self.ck.run_once()
        self.assertEqual(len(self.nt.msgs), 1)
        text = self.nt.msgs[0][1]
        self.assertIn("Сводка событий", text)
        self.assertIn("Цель достигнута", text)
        self.assertIn("Выпуск А", text)
        self.assertTrue(text.endswith(SA.TG_DISCLAIMER))
        sent = set(self.st.sent_keys(1))
        self.assertTrue({"gy|RU000A100001|20.0", "rm|n1", "pay|2026-11-25|coupon|Выпуск А"} <= sent)
        self.ck.run_once()
        self.assertEqual(len(self.nt.msgs), 1)                             # повторно не шлёт

    def test_urgent_offer_stays_separate_with_severity(self):
        offers = [{"isin": "RU000A100002", "name": "Пут", "kind": "put", "date": "2026-11-30", "period_start": "2026-11-20", "period_end": "2026-11-25"}]
        self.st.put(1, self.sub(offers=offers))
        self.ck.run_once()
        self.assertEqual(sorted(self.nt.sevs), [0, 0, 2])                  # срочная оферта уходит отдельно и с высокой важностью
        self.assertEqual(len(self.nt.msgs), 3)

    def test_two_messages_are_not_merged(self):
        self.st.put(1, self.sub(reminders=[], pays=[], pay_days=0))        # оферта + цель = два сообщения
        self.ck.run_once()
        self.assertEqual(len(self.nt.msgs), 2)
        self.assertNotIn("Сводка событий", "".join(t for _u, t in self.nt.msgs))

    def test_digest_defers_overflow_to_next_pass(self):
        msgs = [("head\n\n" + "\n\n".join("строка %d-%d" % (m, i) for i in range(6)), ["k%d-%d" % (m, i) for i in range(6)]) for m in range(3)]
        out, deferred = SA.coalesce_messages(msgs)
        self.assertEqual(len(out), 1)
        self.assertEqual(deferred, 1)                                      # 6 + 6 строк влезли, третье сообщение — на следующую проверку
        self.assertEqual(len(out[0][1]), 12)
        urgent = ("срочно", ["ofr|X|2026-11-30|close"])
        out, deferred = SA.coalesce_messages(msgs[:1] + [urgent] + msgs[1:], urgent=lambda ks: ks[0].startswith("ofr|"))
        self.assertEqual((len(out), out[0], deferred), (2, urgent, 1))     # срочное — отдельным сообщением и первым
        self.assertEqual(SA.coalesce_messages(msgs[:2]), (msgs[:2], 0))

    def test_digest_links_are_not_bullets_and_long_lists_are_not_truncated(self):
        link = '<a href="https://example.com/x">Подробнее</a> · <a href="https://www.moex.com/ru/issue.aspx?code=X">на Мосбирже</a>'
        m1 = ("Цели\n\n<b>Выпуск А</b> — цель достигнута\n" + link, ["gy|A"])
        m2 = ("Раскрытия\n\n<b>Выпуск Б</b> — новое раскрытие\n" + link, ["dc|B"])
        m3 = ("Прочее\n\n<b>Выпуск В</b> — событие", ["x|C"])
        out, deferred = SA.coalesce_messages([m1, m2, m3])
        self.assertEqual((len(out), deferred), (1, 0))
        bullets = [x for x in out[0][0].split("\n") if x.startswith("• ")]
        self.assertEqual(len(bullets), 3)                                  # ссылки приклеены к своим пунктам
        self.assertTrue(bullets[0].endswith("на Мосбирже</a>"))
        self.assertFalse([x for x in out[0][0].split("\n") if x.startswith("• <a ")])
        long_msg = ("Выплаты\n\n" + "\n".join("<b>Бумага %d</b> — купон" % i for i in range(9)), ["pay|%d" % i for i in range(9)])
        out, deferred = SA.coalesce_messages([m1, long_msg, m3])
        texts = {t: ks for t, ks in out}
        self.assertIn(long_msg[0], texts)                                  # длинное сообщение целиком, без «…и ещё»
        self.assertEqual(texts[long_msg[0]], long_msg[1])
        shown = [ks for t, ks in out if t.startswith(SA.DIGEST_HEAD)][0]
        self.assertEqual(sorted(shown), ["gy|A", "x|C"])
        self.assertNotIn("…и ещё", "".join(t for t, _k in out))

    def test_no_emoji_in_telegram_texts(self):
        """Правило проекта: без эмодзи в сообщениях (сервер тревог и клиент в приложении)."""
        import re
        rx = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u23E9-\u23FA\u2705\u274C\uFE0F]")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in ("server/alerts.py", "src/py/13j2_watch_tg.py", "src/py/13j3_watch_dispatch.py", "src/py/13v_flows.py"):
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                self.assertEqual([m for m in rx.findall(f.read())], [], rel)
        self.assertEqual(SA.head("", "Заголовок"), "<b>Заголовок</b>")
        self.assertTrue(all("[" in v for v in SA.KIND_ICON.values()))

    def test_disclosure_and_flow_alerts_units(self):
        sub = self.sub(
            goals=[{"isin": "RU000A100001", "name": "Эмитент А", "watch_only": True}],
            offers=[{"isin": "RU000A100002", "name": "Эмитент Б", "kind": "put", "date": "2026-12-10"}],
        )
        disclosures = [
            {"doc_id": 10, "isin": "RU000A100001", "kind": "default", "title": "Технический дефолт по купону", "published": "2026-11-24"},
            {"doc_id": 11, "isin": "RU000A100001", "kind": "rating", "title": "Понижение рейтинга до ruBBB-", "published": "2026-11-24"},
            {"doc_id": 12, "isin": "RU000A100002", "kind": "coupon_declared", "title": "Объявлена ставка купона перед офертой",
             "data": {"new_rate": 19.5}, "published": "2026-11-24"},
            {"doc_id": 13, "isin": "RU000A100001", "kind": "material", "title": "Существенный факт о досрочном выкупе", "published": "2026-11-24"},
            {"doc_id": 14, "isin": "RU000A100001", "kind": "coupon_paid", "title": "Выплата купона", "data": {"paid_pct": 100.0}},
            {"doc_id": 15, "isin": "RU000A999999", "kind": "default", "title": "Чужой дефолт"},
        ]
        d_al = SA.disclosure_alerts(sub, disclosures, sent=set(), now=self.NOW)
        self.assertEqual(len(d_al), 4)
        self.assertEqual({a["kind"] for a in d_al}, {"default", "rating", "coupon_declared", "disclosure"})
        self.assertEqual([a["severity"] for a in d_al if a["kind"] == "default"][0], 2)
        self.assertEqual([a["severity"] for a in d_al if a["kind"] == "rating"][0], 2)
        self.assertEqual([a["severity"] for a in d_al if a["kind"] == "coupon_declared"][0], 2)
        self.assertIn("19,50%", [a["message"] for a in d_al if a["kind"] == "coupon_declared"][0])
        self.assertEqual(SA.disclosure_alerts(sub, disclosures, sent={a["id"] for a in d_al}, now=self.NOW), [])

        flows = {
            "spikes": [
                {"ts": self.NOW - 300, "secid": "A1", "isin": "RU000A100001", "name": "Эмитент А", "value": 15_000_000, "ratio": 4.2},
                {"ts": self.NOW - 300, "secid": "A1", "isin": "RU000A100001", "name": "Эмитент А", "value": 5_000_000, "ratio": 2.5},
                {"ts": self.NOW - 300, "secid": "X9", "isin": "RU000A999999", "name": "Чужая", "value": 20_000_000, "ratio": 5.0},
            ],
            "large": [
                {"ts": self.NOW - 120, "secid": "A1", "isin": "RU000A100001", "name": "Эмитент А", "side": "buy", "price": 98.5, "value": 12_500_000},
            ],
        }
        f_al = SA.flow_alerts(sub, flows, sent=set(), now=self.NOW)
        self.assertEqual(len(f_al), 2)
        self.assertEqual({a["kind"] for a in f_al}, {"flow_spike", "flow_large"})
        self.assertEqual(SA.flow_alerts(sub, flows, sent={a["id"] for a in f_al}, now=self.NOW), [])

    def test_alert_mute_skips_until_expiry(self):
        self.db.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)")
        self.db.execute("INSERT INTO meta(k, v) VALUES(?, ?)", ("alert_mute:1:RU000A100001", str(int(self.NOW + 7 * 86400))))
        self.db.execute("UPDATE keys SET expires=? WHERE tg_id=1", (self.NOW + 30 * 86400,))
        self.db.execute("UPDATE users SET plan_until=? WHERE tg_id=1", (self.NOW + 30 * 86400,))
        self.db.commit()
        sub = self.sub(reminders=[], offers=[], pay_days=0, pays=[])
        self.st.put(1, sub)
        self.ck.run_once(
            disclosure_rows=[{"doc_id": 1, "isin": "RU000A100001", "kind": "default", "title": "Дефолт"}],
            flow_rows=[{"ts": self.NOW - 60, "secid": "A1", "isin": "RU000A100001", "ratio": 5.0, "value": 10_000_000}],
        )
        self.assertEqual(self.nt.msgs, [])
        self.assertEqual(self.st.sent_keys(1), [])

        # После истечения паузы (7 дней + 1 сек) оповещения снова приходят
        self.clock[0] = self.NOW + 7 * 86400 + 1
        self.ck.run_once(
            disclosure_rows=[{"doc_id": 1, "isin": "RU000A100001", "kind": "default", "title": "Дефолт"}],
            flow_rows=[{"ts": self.clock[0] - 60, "secid": "A1", "isin": "RU000A100001", "ratio": 5.0, "value": 10_000_000}],
        )
        self.assertTrue(self.nt.msgs)
        joined = "\n".join(t for _u, t in self.nt.msgs)
        self.assertIn("Дефолт", joined)
        self.assertIn("Всплеск объёма", joined)

    def test_checker_reads_worker_sqlite_dbs_when_data_dir_given(self):
        import sqlite3
        ddir = tempfile.mkdtemp(prefix="tdata_alerts_")
        ddb = sqlite3.connect(os.path.join(ddir, "disclosure.sqlite"))
        ddb.execute("CREATE TABLE docs(id INTEGER PRIMARY KEY, title TEXT, published TEXT)")
        ddb.execute("CREATE TABLE facts(doc_id INTEGER, n INTEGER, isin TEXT, kind TEXT, event_date TEXT, data TEXT)")
        ddb.execute("INSERT INTO docs VALUES(77, 'Понижение рейтинга Эмитента до ruB+', '2026-11-24')")
        ddb.execute("INSERT INTO facts VALUES(77, 0, 'RU000A100001', 'rating', '2026-11-24', '{\"rating\":\"ruB+\"}')")
        ddb.commit()
        ddb.close()

        fdb = sqlite3.connect(os.path.join(ddir, "flows.sqlite"))
        fdb.execute("CREATE TABLE instruments(secid TEXT PRIMARY KEY, isin TEXT, name TEXT)")
        fdb.execute("CREATE TABLE spikes(secid TEXT, day TEXT, slot INTEGER, ts REAL, value REAL, median REAL, ratio REAL)")
        fdb.execute("CREATE TABLE large(tid TEXT PRIMARY KEY, ts REAL, secid TEXT, cls TEXT, side TEXT, price REAL, qty REAL, value REAL, src TEXT)")
        fdb.execute("INSERT INTO instruments VALUES('A1', 'RU000A100001', 'Выпуск 1')")
        fdb.execute("INSERT INTO spikes VALUES('A1', '2026-11-24', 10, ?, 12000000, 3000000, 4.0)", (self.NOW - 120,))
        fdb.commit()
        fdb.close()

        self.ck.data_dir = ddir
        self.st.put(1, self.sub(reminders=[], offers=[], pay_days=0, pays=[]))
        self.ck.run_once()
        joined = "\n".join(t for _u, t in self.nt.msgs)
        self.assertIn("Понижение рейтинга", joined)
        self.assertIn("Всплеск объёма", joined)

    def test_checker_respects_min_severity_and_coalesces(self):
        self.db.execute("ALTER TABLE users ADD COLUMN min_severity INTEGER NOT NULL DEFAULT 0")
        self.db.execute("UPDATE users SET min_severity=2 WHERE tg_id=1")
        self.db.commit()
        sub = self.sub(offers=[], pay_days=3)
        self.st.put(1, sub)
        disclosures = [
            {"doc_id": 1, "isin": "RU000A100001", "kind": "default", "title": "Техдефолт по купону"},
            {"doc_id": 2, "isin": "RU000A100001", "kind": "material", "title": "Существенный факт об собрании"},
        ]
        flows = [{"ts": self.NOW - 60, "secid": "A1", "isin": "RU000A100001", "ratio": 4.0, "value": 9_000_000}]
        self.ck.run_once(disclosure_rows=disclosures, flow_rows=flows)
        # При min_severity=2 отправляется только критический техдефолт (severity=2)
        self.assertEqual(len(self.nt.msgs), 1)
        self.assertEqual(self.nt.sevs, [2])
        self.assertIn("Техдефолт", self.nt.msgs[0][1])

        # Понижаем порог до 0 — оставшиеся 3+ обычных сообщения (цель+напоминание, раскрытие, поток, выплата) склеиваются в сводку
        self.db.execute("UPDATE users SET min_severity=0 WHERE tg_id=1")
        self.db.commit()
        self.ck.run_once(disclosure_rows=disclosures, flow_rows=flows)
        self.assertEqual(len(self.nt.msgs), 2)
        self.assertIn("Сводка событий", self.nt.msgs[1][1])
        self.assertIn("Всплеск объёма", self.nt.msgs[1][1])


if __name__ == "__main__":
    unittest.main()
