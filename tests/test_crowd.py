"""Краудсорсинг раскрытий, сторона сервера: очередь, аренда, проверка страниц, лимиты, приём и большинство, недоверие, режим --crowd сборщика. Офлайн."""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crowd  # noqa: E402
import disclosure_worker as dw  # noqa: E402
from test_disclosure_worker import FEED, ISIN, MSG_HTML, PAID, FakeNet, T  # noqa: E402
from test_server import Fx  # noqa: E402

DAY = "16.11.2026"
FEED_URL = "https://e-disclosure.azipi.ru/messages/list/day-%s/?MESSAGE_BY_DAY=%s&PAGEN_2=%d"
MSG_URL = "https://e-disclosure.azipi.ru/messages/%d/"
T0 = 1_800_000_000.0                      # около 2027-01-15; для сборщика ниже используется своя шкала времени


def feed_html(day=DAY, extra=""):
    return ('<html><body>АЗИПИ<div class="item"><div class="date">%s 12:00:00</div><a href="/messages/12/x/">t</a></div>'
            '<a href="?PAGEN_2=2">2</a>%s</body></html>' % (day, extra)).encode("utf-8")


def msg_html(mid=4608488, extra=""):
    return ("<html><body>АЗИПИ Сообщение %d %s</body></html>" % (mid, extra)).encode("utf-8")


def b64(raw):
    return crowd.gzip_b64(raw)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="crowd_")
        self.now = [T0]
        self.st = crowd.CrowdStore(os.path.join(self.d, "crowd.sqlite"), lambda: self.now[0])

    def tearDown(self):
        self.st.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def tick(self, s=6):
        self.now[0] += s
        return self.now[0]

    def sub(self, key, tid, url, raw, status=200, **kw):
        return self.st.submit(key, tid, url, status, b64(raw), "text/html; charset=utf-8", kw.get("now", self.tick()))

    def one(self, key, url, prio=3):
        self.st.want([url], prio, self.now[0])
        t = [x for x in self.st.lease(key, 5, self.now[0]) if x["url"] == url][0]
        return t["id"]


class QueueTests(StoreCase):
    def test_classify_only_two_shapes(self):
        self.assertEqual(crowd.classify(FEED_URL % (DAY, DAY, 3)), ("feed", DAY, 3))
        self.assertEqual(crowd.classify(MSG_URL % 4608488), ("msg", 4608488, 0))
        for bad in ("http://e-disclosure.azipi.ru/messages/1/", "https://e-disclosure.ru/messages/1/", "https://evil.example/messages/1/",
                    "https://e-disclosure.azipi.ru/messages/1/?x=1", "https://e-disclosure.azipi.ru/messages/1/../../etc",
                    "https://e-disclosure.azipi.ru@evil.example/messages/1/", FEED_URL % (DAY, "17.11.2026", 1), FEED_URL % ("31.02.2026", "31.02.2026", 1),
                    "https://e-disclosure.azipi.ru/", "", None, 5):
            self.assertIsNone(crowd.classify(bad), bad)
        with self.assertRaises(ValueError):
            self.st.want(["https://evil.example/x"], 0)

    def test_priority_order_and_lease(self):
        self.st.want([MSG_URL % 1], crowd_prio(2), self.now[0])
        self.st.want([FEED_URL % (DAY, DAY, 1)], 3, self.now[0])
        self.st.want(["https://e-disclosure.azipi.ru/messages/list/day-17.11.2026/?MESSAGE_BY_DAY=17.11.2026&PAGEN_2=1"], 0, self.now[0])
        got = self.st.lease("a", 2, self.now[0])
        self.assertEqual([t["url"].split("/")[-2] if "list" not in t["url"] else "L" + t["url"].split("day-")[1][:10] for t in got], ["L17.11.2026", "1"])
        self.assertEqual(self.st.lease("a", 2, self.now[0]), got)              # повтор запроса: те же арендованные задания
        rest = self.st.lease("b", 5, self.now[0])
        self.assertEqual(len(rest), 1)                                          # у b осталось только третье
        self.assertEqual(self.st.lease("c", 5, self.now[0]), [])
        self.assertEqual(self.st.status(self.now[0])["leased"], 3)

    def test_lease_expires_and_is_reissued(self):
        self.st.want([MSG_URL % 1], 2, self.now[0])
        t = self.st.lease("a", 1, self.now[0])
        self.assertEqual(self.st.lease("b", 1, self.now[0] + 100), [])
        t2 = self.st.lease("b", 1, self.now[0] + crowd.LEASE_SEC + 1)
        self.assertEqual(t2, t)                                                 # тот же id, другой арендатор
        self.assertEqual(self.st.lease("a", 1, self.now[0] + crowd.LEASE_SEC + 2), [])

    def test_n_is_capped(self):
        self.st.want([MSG_URL % i for i in range(1, 12)], 2, self.now[0])
        self.assertEqual(len(self.st.lease("a", 99, self.now[0])), crowd.MAX_TASKS_PER_CALL)

    def test_want_refresh_requeues_stale_page(self):
        url = FEED_URL % (DAY, DAY, 1)
        tid = self.one("a", url)
        self.assertTrue(self.sub("a", tid, url, feed_html())["accepted"])
        self.assertEqual(self.st.want([url], 0, self.now[0]), 0)                 # без newer_than принятая страница годится
        self.assertEqual(self.st.want([url], 0, self.now[0], newer_than=self.now[0] - 1), 0)
        self.assertEqual(self.st.want([url], 0, self.now[0], newer_than=self.now[0] + 1), 1)
        self.assertIsNone(self.st.get(url, self.now[0] + 1))                      # старая копия «устарела»
        self.assertEqual(self.st.get(url)[0], 200)
        t = self.st.lease("b", 1, self.now[0] + 1)
        self.assertEqual(t[0]["id"], tid)
        self.assertTrue(self.st.submit("b", tid, url, 200, b64(feed_html(extra="новое")), "", self.now[0] + 7)["accepted"])
        self.assertIn("новое", self.st.get(url, self.now[0] + 1)[1].decode())


def crowd_prio(n):
    return n


class SubmitValidation(StoreCase):
    def check(self, url, raw, code, err):
        self.now[0] += 100                                                       # пауза после прошлого отказа успела пройти
        tid = self.one("a", url)
        with self.assertRaises(crowd.CrowdError) as cm:
            self.sub("a", tid, url, raw)
        self.assertEqual((cm.exception.code, cm.exception.error), (code, err))
        return tid

    def test_accepts_valid_pages(self):
        for url, raw in ((FEED_URL % (DAY, DAY, 1), feed_html()), (MSG_URL % 4608488, msg_html())):
            tid = self.one("a", url)
            self.assertEqual(self.sub("a", tid, url, raw), {"accepted": True})
            self.assertEqual(self.st.get(url)[1], raw)

    def test_rejects(self):
        furl, murl = FEED_URL % (DAY, DAY, 1), MSG_URL % 4608488
        self.check(furl, feed_html(extra="<div class='g-recaptcha'></div>"), 422, "captcha or error page")
        self.check(furl, feed_html(day="15.11.2026"), 422, "feed page without the requested date")
        self.check(murl, msg_html(mid=4608489), 422, "message page without the message id")
        self.check(murl, b"<html>Just a moment...</html>", 422, "captcha or error page")
        self.check(murl, b"<html>" + b"x" * (crowd.MAX_BODY + 10) + b"</html>", 413, "too large")
        tid = self.one("b", MSG_URL % 7)
        with self.assertRaises(crowd.CrowdError) as cm:                         # чужое задание: адрес не совпадает с заданием
            self.st.submit("b", tid, MSG_URL % 8, 200, b64(msg_html(8)), "", self.tick())
        self.assertEqual(cm.exception.error, "unknown task")
        with self.assertRaises(crowd.CrowdError) as cm:
            self.st.submit("b", 99999, MSG_URL % 7, 200, b64(msg_html(7)), "", self.tick())
        self.assertEqual(cm.exception.code, 400)
        with self.assertRaises(crowd.CrowdError) as cm:
            self.st.submit("b", tid, MSG_URL % 7, 200, "!!не base64!!", "", self.tick())
        self.assertEqual(cm.exception.error, "bad body")
        self.assertIsNone(self.st.get(MSG_URL % 7))                              # ничего не принято

    def test_rejected_page_releases_task_with_delay(self):
        url = MSG_URL % 5
        tid = self.check(url, b"<html>captcha</html>", 422, "captcha or error page")
        self.assertEqual(self.st.lease("b", 1, self.now[0] + 1), [])             # 60 с пауза, потом снова в очереди
        self.assertEqual(self.st.lease("b", 1, self.now[0] + 70)[0]["id"], tid)

    def test_task_fails_after_many_rejections(self):
        url = MSG_URL % 6
        self.st.want([url], 2, self.now[0])
        for i in range(crowd.MAX_TRIES):
            self.now[0] += 70
            t = self.st.lease("a", 1, self.now[0])
            self.assertEqual(len(t), 1, i)
            with self.assertRaises(crowd.CrowdError):
                self.st.submit("a", t[0]["id"], url, 200, b64(b"<html>captcha</html>"), "", self.tick(100))
        self.assertEqual(self.st.get(url)[0], "failed")
        self.assertEqual(self.st.lease("a", 1, self.now[0] + 99999), [])

    def test_rate_limit_and_daily_cap(self):
        urls = [MSG_URL % i for i in range(20, 24)]
        ids = {u: self.one("a", u) for u in urls}
        self.assertTrue(self.st.submit("a", ids[urls[0]], urls[0], 200, b64(msg_html(20)), "", self.now[0] + 10)["accepted"])
        with self.assertRaises(crowd.CrowdError) as cm:
            self.st.submit("a", ids[urls[1]], urls[1], 200, b64(msg_html(21)), "", self.now[0] + 12)
        self.assertEqual(cm.exception.code, 429)
        self.assertGreaterEqual(cm.exception.extra["retry_after"], 1)
        self.assertTrue(self.st.submit("a", ids[urls[1]], urls[1], 200, b64(msg_html(21)), "", self.now[0] + 16)["accepted"])
        old = crowd.DAY_CAP
        crowd.DAY_CAP = 2
        try:
            with self.assertRaises(crowd.CrowdError) as cm:
                self.st.submit("a", ids[urls[2]], urls[2], 200, b64(msg_html(22)), "", self.now[0] + 30)
            self.assertEqual((cm.exception.code, cm.exception.error), (429, "daily cap"))
        finally:
            crowd.DAY_CAP = old
        self.assertTrue(self.st.submit("b", ids[urls[2]], urls[2], 200, b64(msg_html(22)), "", self.now[0] + 31)["accepted"])   # лимит на ключ

    def test_gone_needs_two_keys_or_repeats(self):
        url = MSG_URL % 9
        tid = self.one("a", url)
        r = self.st.submit("a", tid, url, 404, "", "", self.tick())
        self.assertEqual((r["accepted"], r.get("retry")), (False, True))
        self.assertIsNone(self.st.get(url))
        t = self.st.lease("b", 1, self.now[0] + crowd.GONE_RETRY + 1)
        self.assertEqual(len(t), 1)
        r = self.st.submit("b", t[0]["id"], url, 404, "", "", self.now[0] + crowd.GONE_RETRY + 10)
        self.assertTrue(r.get("gone"))
        self.assertEqual(self.st.get(url)[0], 404)

    def test_server_error_status_requeues(self):
        url = MSG_URL % 10
        tid = self.one("a", url)
        self.assertTrue(self.st.submit("a", tid, url, 503, "", "", self.tick())["retry"])
        self.assertEqual(self.st.lease("a", 1, self.now[0] + 1), [])
        self.assertEqual(len(self.st.lease("a", 1, self.now[0] + crowd.RETRY_5XX + 1)), 1)


class AcceptanceTests(StoreCase):
    def test_majority_replaces_first_accepted(self):
        url = MSG_URL % 4608488
        tid = self.one("a", url)
        self.sub("a", tid, url, msg_html(extra="версия-A"))
        self.assertEqual(self.st.pop_events(), [])
        # b присылает другое: ничья 1:1, остаётся первая, спор помечен
        r = self.sub("b", tid, url, msg_html(extra="версия-B"))
        self.assertTrue(r["conflict"])
        self.assertIn("версия-A", self.st.get(url)[1].decode())
        self.assertEqual(self.st.pop_events(), [])
        # c соглашается с b: 2:1 — страница заменена, сборщик получает событие
        r = self.sub("c", tid, url, msg_html(extra="версия-B"))
        self.assertTrue(r["conflict"] or r["verified"])
        self.assertIn("версия-B", self.st.get(url)[1].decode())
        self.assertEqual(self.st.pop_events(), [(url, "replaced")])
        self.assertEqual(self.st.pop_events(), [])

    def test_same_sha_is_verification_not_conflict(self):
        url = MSG_URL % 4608488
        tid = self.one("a", url)
        self.sub("a", tid, url, msg_html())
        r = self.sub("b", tid, url, b"<!-- c -->" + msg_html() + b"\n  ")      # отличается только нормализуемым шумом
        self.assertEqual(r, {"accepted": True, "verified": True})
        self.assertEqual(self.st.pop_events(), [])

    def test_verification_is_offered_to_another_key(self):
        url = MSG_URL % 4608488
        tid = self.one("a", url)
        self.sub("a", tid, url, msg_html())
        self.st.rng = _Always()
        self.assertEqual(self.st.lease("a", 2, self.now[0]), [])                # автору свою страницу не дают
        got = self.st.lease("b", 2, self.now[0])
        self.assertEqual([t["url"] for t in got], [url])
        self.assertEqual(self.st.lease("c", 2, self.now[0]), [])                 # уже у b

    def test_distrusted_key_is_ignored_and_pages_requeued(self):
        u1, u2 = MSG_URL % 4608488, MSG_URL % 4608489
        t1, t2 = self.one("bad", u1), self.one("bad", u2)
        self.sub("bad", t1, u1, msg_html(extra="яд"))
        self.sub("bad", t2, u2, msg_html(4608489, extra="яд"))
        self.assertEqual(self.st.distrust("bad"), 2)
        self.assertEqual(sorted(self.st.pop_events()), sorted([(u1, "revoked"), (u2, "revoked")]))
        self.assertIsNone(self.st.get(u1))
        self.assertEqual(self.st.status(self.now[0])["queue"], 2)
        self.assertEqual(self.st.lease("bad", 5, self.now[0]), [])                # ему задания не выдаются
        r = self.sub("bad", t1, u1, msg_html(extra="ещё яд"))
        self.assertEqual(r, {"accepted": False, "ignored": True})
        self.assertIsNone(self.st.get(u1))
        good = self.st.lease("good", 5, self.now[0])
        self.assertEqual(len(good), 2)
        self.assertTrue(self.sub("good", good[0]["id"], good[0]["url"], msg_html(int(good[0]["url"].split("/")[-2]), "чисто"))["accepted"])
        self.assertEqual(self.st.status(self.now[0])["contributors_24h"], 1)       # недоверенные не считаются
        self.st.distrust("bad", False)
        self.assertTrue(self.st.lease("bad", 5, self.now[0]))

    def test_distrust_prefers_stored_alternative(self):
        url = MSG_URL % 4608488
        tid = self.one("bad", url)
        self.sub("bad", tid, url, msg_html(extra="яд"))
        self.sub("good", tid, url, msg_html(extra="чисто"))                       # спор 1:1, принято «яд»
        self.assertIn("яд", self.st.get(url)[1].decode())
        self.st.distrust("bad")
        self.assertIn("чисто", self.st.get(url)[1].decode())
        self.assertEqual(self.st.pop_events(), [(url, "replaced")])

    def test_status_has_no_key_ids_and_counts(self):
        url = MSG_URL % 4608488
        self.sub("tg:12345", self.one("tg:12345", url), url, msg_html())
        s = self.st.status(self.now[0])
        self.assertEqual((s["accepted_today"], s["contributors_24h"], s["queue"]), (1, 1, 0))
        self.assertNotIn("12345", json.dumps(s))

    def test_purge(self):
        url = MSG_URL % 4608488
        self.sub("a", self.one("a", url), url, msg_html())
        self.st.purge(self.now[0] + (crowd.KEEP_DAYS + 1) * 86400)
        self.assertIsNone(self.st.get(url))
        self.assertEqual(self.st.conn().execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)


class _Always:
    def random(self):
        return 0.0


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.f = Fx(key="s3cret")
        self.h = {"X-Client-Key": "s3cret"}

    def tearDown(self):
        self.f.close()

    def get(self, path, headers=None):
        st, body, _h = self.f.call(None, None, self.h if headers is None else headers, path)
        return st, json.loads(body.decode())

    def post(self, path, obj, headers=None):
        st, body, _h = self.f.call(None, json.dumps(obj).encode(), dict(self.h if headers is None else headers, **{"Content-Type": "application/json"}), path)
        return st, json.loads(body.decode())

    def test_auth_required(self):
        for path in ("/v1/crowd/task?n=2", "/v1/crowd/status"):
            self.assertEqual(self.get(path, {})[0], 401)
            self.assertEqual(self.get(path, {"X-Client-Key": "wrong"})[0], 401)
        self.assertEqual(self.post("/v1/crowd/submit", {}, {})[0], 401)

    def test_open_server_still_rejects_anonymous(self):
        f = Fx()                                              # сервер без ключей: остальные эндпоинты открыты, сбор страниц — нет
        try:
            for path in ("/v1/crowd/task", "/v1/crowd/status"):
                st, body, _h = f.call(None, None, {}, path)
                self.assertEqual(st, 401)
            st, body, _h = f.call(None, b"{}", {}, "/v1/crowd/submit")
            self.assertEqual(st, 401)
        finally:
            f.close()

    def test_task_submit_status_roundtrip(self):
        self.f.app.crowd.want([MSG_URL % 4608488], 2)
        st, j = self.get("/v1/crowd/task?n=2")
        self.assertEqual((st, j["ok"], len(j["tasks"]), j["queue"]), (200, True, 1, 0))
        t = j["tasks"][0]
        self.assertEqual(set(t), {"id", "url"})
        self.assertEqual(self.get("/v1/crowd/task")[1]["tasks"], [t])                    # идемпотентно
        self.f.now[0] += 10
        st, r = self.post("/v1/crowd/submit", {"id": t["id"], "url": t["url"], "status": 200, "body_b64": b64(msg_html()), "ctype": "text/html"})
        self.assertEqual((st, r["ok"], r["accepted"]), (200, True, True))
        st, s = self.get("/v1/crowd/status")
        self.assertEqual((s["accepted_today"], s["queue"], s["contributors_24h"]), (1, 0, 1))
        self.assertNotIn("key", json.dumps(s).replace("contributors", ""))
        self.assertEqual(self.get("/v1/crowd/task")[1]["tasks"], [])
        self.assertEqual(self.get("/v1/crowd/task")[1]["retry_after"], 300)

    def test_submit_errors(self):
        self.f.app.crowd.want([MSG_URL % 4608488], 2)
        t = self.get("/v1/crowd/task")[1]["tasks"][0]
        self.f.now[0] += 10
        self.assertEqual(self.post("/v1/crowd/submit", {"id": "x"})[0], 400)
        st, r = self.post("/v1/crowd/submit", {"id": t["id"], "url": t["url"], "status": 200, "body_b64": b64(b"<html>captcha</html>")})
        self.assertEqual((st, r["ok"], r["error"]), (422, False, "captcha or error page"))
        self.f.now[0] += 1
        st, r = self.post("/v1/crowd/submit", {"id": t["id"], "url": t["url"], "status": 200, "body_b64": b64(msg_html())})
        self.assertEqual(st, 429)
        self.assertIn("retry_after", r)
        self.assertEqual(self.f.call(None, None, self.h, "/v1/crowd/nope")[0], 404)


# ───────────── сборщик в режиме --crowd ─────────────
class SimClient:
    """Поддельный пользователь: берёт задания из очереди и «скачивает» страницы из FakeNet."""

    def __init__(self, store, net, key, clock):
        self.store, self.net, self.key, self.clock = store, net, key, clock
        self.done = []

    def page(self, url):
        c = crowd.classify(url)
        if c[0] == "msg":
            return MSG_HTML.replace("4608488", str(c[1])).encode("utf-8")
        d = c[1]
        html = self.net(url)
        if 'class="item"' not in html:
            html += '<a href="/messages/list/day-%s/?MESSAGE_BY_DAY=%s">%s</a>' % (d, d, d)
        return html.encode("utf-8")

    def round(self, n=5):
        tasks = self.store.lease(self.key, n, self.clock[0])
        for t in tasks:
            self.clock[0] += 6
            r = self.store.submit(self.key, t["id"], t["url"], 200, b64(self.page(t["url"])), "text/html; charset=utf-8", self.clock[0])
            assert r["accepted"], (t, r)
            self.done.append(t["url"])
        return len(tasks)


class CrowdWorkerTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="crowdw_")
        self.clock = [dw.MSK and dw.datetime(2026, 11, 17, 10, 0, tzinfo=dw.MSK).timestamp()]
        self.net = FakeNet(FEED)
        self.store = crowd.CrowdStore(os.path.join(self.d, "crowd.sqlite"), lambda: self.clock[0])
        self.fetch = dw.CrowdFetch(self.store, self.net)
        self.db = dw.open_db(self.d)
        self.w = dw.Worker(self.db, self.fetch, T, "ver1", "2026-11-11", 60, now=lambda: dw.datetime(2026, 11, 17, 10, 0, tzinfo=dw.MSK),
                           clock=lambda: self.clock[0])
        self.cl = SimClient(self.store, self.net, "u1", self.clock)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def q(self, s):
        return self.db.execute(s).fetchall()

    def urls(self, state="queued"):
        return [r[0] for r in self.store.conn().execute("SELECT url FROM tasks WHERE state=? ORDER BY prio, id", (state,))]

    def test_end_to_end_with_parallel_batches(self):
        self.w.live_cycle()
        self.assertEqual(self.q("SELECT COUNT(*) FROM universe"), [(1,)])           # ISS качается напрямую
        q = self.urls()
        self.assertEqual(len(q), 2)                                                 # лента сегодня (0) и вчера (1) просят сразу
        self.assertIn("day-17.11.2026", q[0])
        self.assertEqual(self.net.feed_urls(), [])                                  # воркер сам к azipi не ходит
        self.assertEqual(self.cl.round(), 2)
        self.w.live_cycle()
        # сегодня: страница 1 дала новые элементы — просим 2; вчера: известно 2 страницы, обе просятся сразу, день ждёт
        self.assertEqual(self.q("SELECT COUNT(*) FROM feed WHERE day='2026-11-16'"), [(0,)])
        self.assertEqual(len(self.urls()), 2)
        self.assertEqual(self.cl.round(), 2)
        self.w.live_cycle()
        self.assertEqual(self.q("SELECT COUNT(*) FROM feed"), [(8,)])
        self.assertEqual(self.q("SELECT status, items FROM days"), [("done", 4)])
        self.assertEqual(self.urls(), [MSG_URL % 4608500])                           # текст нужного сообщения
        self.assertEqual(self.cl.round(), 1)
        self.w.live_cycle()
        r = self.q("SELECT doc_id, isin, kind FROM facts")
        self.assertEqual(r, [(4608500, ISIN, "coupon_paid")])
        # повторный цикл ничего не просит заново
        self.w.live_cycle()
        self.assertEqual(self.urls(), [])

    def test_live_refresh_after_age(self):
        for _ in range(8):
            self.w.live_cycle()
            self.cl.round()
        self.assertEqual(self.q("SELECT COUNT(*) FROM feed"), [(8,)])
        self.w.live_cycle()
        self.assertEqual(self.urls(), [])
        self.net.feed["2026-11-17"].insert(0, (5001, PAID, "7703104630"))
        self.clock[0] += 5                                                           # свежая копия ещё годится: ничего не просим
        self.w.live_cycle()
        self.assertEqual(self.urls(), [])
        self.clock[0] += dw.LIVE_AGE + 1
        self.w.live_cycle()
        self.assertEqual(len(self.urls()), 1)
        self.assertIn("day-17.11.2026", self.urls()[0])
        for _ in range(6):
            self.cl.round()
            self.w.live_cycle()
        self.assertEqual(self.q("SELECT COUNT(*) FROM facts"), [(2,)])

    def test_history_waits_and_looks_ahead(self):
        self.w.live_cycle()
        self.assertEqual(self.w.backfill_step(), "wait")                              # первая страница дня ещё в пути
        for _ in range(12):
            self.w.live_cycle()
            self.cl.round()
            if self.w.backfill_step() != "wait":
                break
        # дни 15 и 14 пустые; в очереди были страницы заранее (P_AHEAD)
        days = dict(self.q("SELECT day, status FROM days"))
        self.assertEqual(days.get("2026-11-16"), "done")
        prios = {r[0] for r in self.store.conn().execute("SELECT prio FROM tasks")}
        self.assertIn(dw.P_AHEAD, prios)
        self.assertTrue(any("day-14.11.2026" in u for u in self.cl.done))

    def test_pending_never_marks_day_partial(self):
        self.assertEqual(self.w.backfill_step(), "wait")
        self.assertEqual(self.q("SELECT COUNT(*) FROM days"), [(0,)])

    def test_replaced_page_triggers_reload_of_message(self):
        for _ in range(6):
            self.w.live_cycle()
            self.cl.round()
        self.assertEqual(self.q("SELECT fetched FROM feed WHERE id=4608500"), [(1,)])
        self.store.conn().execute("INSERT INTO events(url, kind, ts) VALUES(?,?,?)", (MSG_URL % 4608500, "replaced", self.clock[0]))
        self.w.live_cycle()
        self.assertEqual(self.q("SELECT fetched FROM feed WHERE id=4608500"), [(0,)])       # сброшено: страница заменена
        self.assertEqual(self.store.pop_events(), [])
        self.w.live_cycle()
        self.assertEqual(self.q("SELECT fetched FROM feed WHERE id=4608500"), [(1,)])       # и заново взято из очереди

    def test_direct_mode_has_no_crowd_hooks(self):
        w = dw.Worker(dw.open_db(tempfile.mkdtemp(prefix="dwd_")), FakeNet(FEED), T, "v", "2026-11-11", 60, now=lambda: dw.datetime(2026, 11, 17, 10, 0, tzinfo=dw.MSK))
        self.assertFalse(w.crowd)
        w.live_cycle()
        self.assertEqual(w.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
