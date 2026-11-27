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


if __name__ == "__main__":
    unittest.main()
