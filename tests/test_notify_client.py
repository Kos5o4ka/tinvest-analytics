"""Уведомления приложения: POST /v1/notify на сервер данных (локальная заглушка), сообщения об ошибках, очистка старых настроек."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

M = _load.load()


class Stub:
    def __init__(self):
        self.code, self.reply = 200, {"ok": True, "queued": 1}
        self.posts = []
        me = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                me.posts.append((self.path, self.headers.get("X-Client-Key"), json.loads(body)))
                b = json.dumps(me.reply).encode()
                self.send_response(me.code)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class T(unittest.TestCase):
    def setUp(self):
        self.stub = Stub()
        self.conf(data_server=self.stub.url, data_key="TIA-AAAA-AAAA-AAAA")

    def tearDown(self):
        self.stub.close()
        self.conf(data_server="off", data_key="")

    def conf(self, **kw):
        c = M.load_config()
        c.update(kw)
        M.save_config(c)
        M.ds_reset()

    def err(self):
        with self.assertRaises(M.ApiError) as cm:
            M.tg_send(M.load_config(), "x")
        return str(cm.exception), cm.exception.status if hasattr(cm.exception, "status") else None

    def test_send_ok(self):
        self.assertEqual(M.tg_send(M.load_config(), "<b>Привет</b>"), 1)
        path, key, body = self.stub.posts[0]
        self.assertEqual((path, key), ("/v1/notify", "TIA-AAAA-AAAA-AAAA"))
        self.assertTrue(body["text"].startswith("<b>Привет</b>"))
        self.assertTrue(body["text"].endswith(M.TG_DISCLAIMER))

    def test_long_text_fits_limit(self):
        M.tg_send(M.load_config(), "\n".join("строка %d" % i for i in range(1000)))
        t = self.stub.posts[0][2]["text"]
        self.assertLessEqual(len(t), 3500)
        self.assertTrue(t.endswith(M.TG_DISCLAIMER))

    def test_errors(self):
        self.stub.code, self.stub.reply = 409, {"ok": False, "error": "notify_off"}
        self.assertIn("/notify_on", self.err()[0])
        self.stub.code, self.stub.reply = 402, {"error": "pro_required"}
        self.assertIn("Pro", self.err()[0])
        self.stub.code, self.stub.reply = 429, {"ok": False, "error": "rate_limit"}
        self.assertIn("Слишком много сообщений", self.err()[0])
        self.stub.code, self.stub.reply = 401, {"ok": False, "error": "expired"}
        self.assertIn("Войдите по ключу", self.err()[0])
        self.stub.code, self.stub.reply = 403, {"error": "x"}
        self.assertIn("только по ключу", self.err()[0])
        self.stub.code, self.stub.reply = 503, {}
        self.assertIn("Сервер недоступен", self.err()[0])

    def test_no_key_and_off_and_offline(self):
        self.conf(data_key="")
        self.assertIn("Войдите по ключу", self.err()[0])
        self.assertEqual(self.stub.posts, [])
        self.conf(data_server="off", data_key="TIA-AAAA-AAAA-AAAA")
        self.assertIn("сервер данных", self.err()[0])
        self.conf(data_server="http://127.0.0.1:9", data_key="TIA-AAAA-AAAA-AAAA")
        self.assertIn("Сервер недоступен", self.err()[0])

    def test_tick_requires_opt_in_and_login(self):
        self.conf(tg_enabled=False, tg_digest=True, tg_digest_time="00:00")
        self.assertEqual(M.tg_tick(), 0)
        self.assertEqual(self.stub.posts, [])
        self.conf(tg_enabled=True, tg_digest=True, tg_digest_time="00:00", data_key="")
        self.assertEqual(M.tg_tick(), 0)
        self.assertEqual(self.stub.posts, [])
        self.conf(tg_enabled=True, tg_digest=True, tg_digest_time="00:00", data_key="TIA-AAAA-AAAA-AAAA")
        M.tg_tick()
        self.assertEqual(len(self.stub.posts), 1)
        self.assertIn("Сводка", self.stub.posts[0][2]["text"])
        self.assertTrue(self.stub.posts[0][2]["text"].startswith("<b>Сводка TAnalytic</b> · "))

    def test_legacy_keys_cleanup_and_save(self):
        self.conf(tg_token="123456:SECRETSECRETSECRETSECRET", tg_chat="42")
        M._tg_cleanup()
        c = M.load_config()
        self.assertNotIn("tg_token", c)
        self.assertNotIn("tg_chat", c)
        self.conf(tg_token="x", tg_chat="1")
        r = M.tg_save({}, {"tg_enabled": True, "tg_pay_days": 99, "token": "ignored", "chat": "5"})
        self.assertTrue(r["settings"]["tg_enabled"])
        self.assertEqual(r["settings"]["tg_pay_days"], 60)
        self.assertNotIn("tg_chat", r["settings"])
        c = M.load_config()
        self.assertNotIn("tg_token", c)
        self.assertNotIn("tg_chat", c)
        self.assertNotIn("/api/tg/find_chat", M.API_POST)


    def test_test_message_format(self):
        M.tg_test({}, {})
        t = self.stub.posts[0][2]["text"]
        self.assertTrue(t.startswith("<b>Тестовое сообщение</b>\n\n"))
        self.assertTrue(t.endswith(M.TG_DISCLAIMER))


if __name__ == "__main__":
    unittest.main()


class DigestEventLabels(unittest.TestCase):
    """Строки «Ближайшие 7 дней» в сводке Telegram: типы выплат по-русски, без внутренних имён вроде amortization."""

    def test_kinds_are_russian(self):
        for kind, label in (("coupon", "купон"), ("amortization", "амортизация"), ("redemption", "погашение"),
                            ("dividend", "дивиденд"), ("offer", "оферта")):
            line = M._tg_ev_line(("%d-11-20" % M.date.today().year, kind, "Выпуск", 5000))
            self.assertEqual(line, "20 ноября · <b>Выпуск</b> — %s, 5 000 ₽" % label)

    def test_unknown_kind_has_no_english(self):
        for kind in ("something_new", None):
            self.assertIn(" — выплата", M._tg_ev_line(("2026-11-20", kind, "Выпуск", None)))


class MessageFormat(unittest.TestCase):
    """Оформление сообщений: числа, даты, ссылки, экранирование, предел длины."""

    def test_numbers(self):
        self.assertEqual(M._tg_num(1234567.8), "1 234 568")
        self.assertEqual(M._tg_rub(5000), "5 000 ₽")
        self.assertEqual(M._tg_rub(12.5), "12,50 ₽")
        self.assertEqual(M._tg_pct(14.5), "14,50%")

    def test_dates_russian(self):
        y = M.date.today().year
        self.assertEqual(M._tg_date("%d-03-05" % y), "5 марта")
        self.assertEqual(M._tg_date("%d-12-31" % (y + 1)), "31 декабря %d" % (y + 1))

    def test_links_escaped_and_only_http(self):
        self.assertEqual(M._tg_link("javascript:alert(1)", "x"), "")
        self.assertEqual(M._tg_link("https://a.ru/?a=1&b=\"2\"", "<б>"), '<a href="https://a.ru/?a=1&amp;b=%222%22">&lt;б&gt;</a>')
        self.assertIn("issue.aspx?code=RU000A0TEST1", M._tg_moex("RU000A0TEST1"))
        self.assertEqual(M._tg_moex(""), "")

    def test_alert_line(self):
        a = {"kind": "rating", "name": "Банк <X>", "message": "рейтинг понижен & отозван", "isin": "RU000A0TEST1", "url": "https://acra-ratings.ru/press/1"}
        ln = M._tg_alert_line(a)
        self.assertTrue(ln.startswith("[рейтинг] <b>Банк &lt;X&gt;</b> — рейтинг понижен &amp; отозван\n"))
        self.assertIn('<a href="https://acra-ratings.ru/press/1">Пресс-релиз</a> · <a href="https://www.moex.com/ru/issue.aspx?code=RU000A0TEST1">на Мосбирже</a>', ln)
        self.assertEqual(M._tg_alert_line({"kind": "price", "name": "A", "message": "m"}), "[цена] <b>A</b> — m")
        self.assertTrue(M._tg_alert_line({"kind": "goal", "name": "A", "message": "m"}).startswith("[цель]"))

    def test_cap_and_fit(self):
        self.assertEqual(M._tg_cap(["a", "b", "c"], 2), "a\nb\n…и ещё 1")
        self.assertEqual(M._tg_cap(["a", "b"], 2), "a\nb")
        t = "<b>Заголовок</b>\n\n" + "\n".join("<i>строка %d</i> <a href=\"https://x.ru\">ссылка</a>" % i for i in range(300))
        r = M._tg_fit(t, 500)
        self.assertLessEqual(len(r), 500)
        self.assertTrue(r.endswith("…"))
        self.assertEqual(r.count("<a "), r.count("</a>"))
        self.assertEqual(r.count("<i>"), r.count("</i>"))
        self.assertEqual(M._tg_fit("коротко", 500), "коротко")
        z = M._tg_fit("<b>" + "я" * 600, 300)
        self.assertTrue(z.endswith("</b>") and len(z) <= 300)

    def test_dispatch_format_dedup_and_limit(self):
        sent, msgs = {}, []
        orig = M.tg_send
        M.tg_send = lambda cfg, text: msgs.append(text)
        try:
            al = [{"id": "x%d" % i, "kind": "watch", "name": "Бумага %d" % i, "message": "м" * 200, "isin": "RU000A0TEST1"} for i in range(40)]
            n = M._tg_dispatch({}, "Тревоги по портфелю", al, sent, 1000.0)
            self.assertEqual(n, len(sent))
            self.assertLessEqual(len(msgs), 3)
            self.assertTrue(all(m.startswith("<b>Тревоги по портфелю</b>\n\n") for m in msgs))
            self.assertTrue(all(len(m) + len(M.TG_DISCLAIMER) <= M.TG_LIMIT for m in msgs))
            self.assertIn("…и ещё %d — придут при следующей проверке" % (40 - n), msgs[-1])
            self.assertEqual(M._tg_dispatch({}, "t", al[:n], sent, 2000.0), 0)       # отправленные не повторяются
            msgs.clear()
            M._tg_dispatch({}, "Наблюдение и цели", [{"id": "g1", "kind": "goal", "name": "Б", "message": "цель"}], {}, 1.0, icon="")
            self.assertTrue(msgs[0].startswith("<b>Наблюдение и цели</b>"))
        finally:
            M.tg_send = orig

    def test_offer_texts_human(self):
        y = M.date.today().year
        i = {"isin": "RU1", "name": "Бонд <1>", "kind": "put", "date": "%d-12-26" % (y + 1), "period_start": "%d-12-15" % (y + 1),
             "period_end": "%d-12-21" % (y + 1), "coupon_status": "announced", "new_rate": 14.5}
        t = dict(M.tg_offer_due([i], "%d-12-10" % (y + 1)))["ofr|RU1|%d-12-26|coupon" % (y + 1)]
        self.assertIn("<b>Бонд &lt;1&gt;</b> — ", t)
        self.assertIn("14,50% годовых", t)
        self.assertIn("26 декабря %d" % (y + 1), t)
        self.assertIn("на Мосбирже", t)
