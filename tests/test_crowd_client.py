"""Клиент: помощник сбора раскрытий (13o_crowd.py). Поддельные сервер данных и azipi, сети нет."""
import base64
import gzip
import json
import unittest
from unittest import mock

from tests._load import load

T = load()
FEED = "https://e-disclosure.azipi.ru/messages/list/day-16.11.2026/?MESSAGE_BY_DAY=16.11.2026&PAGEN_2=%d"
MSG = "https://e-disclosure.azipi.ru/messages/%d/"
PAGE = "<html>АЗИПИ 16.11.2026 /messages/ x</html>".encode("utf-8")


class Mem:
    def __init__(self):
        self.d = {}

    def add(self, **kw):
        for k, v in kw.items():
            self.d[k] = v if k in ("last", "queue") else self.d.get(k, 0) + v

    def get(self):
        return dict(self.d)


class Sim:
    """Поддельный сервер данных + azipi + часы."""

    def __init__(self, tasks=None, enabled=True, key="K", srv="http://srv"):
        self.now = [1000.0]
        self.tasks = list(tasks if tasks is not None else [])
        self.cfg = (enabled, srv, key)
        self.srv_calls, self.azipi_calls, self.submits = [], [], []
        self.azipi_result = lambda url: (200, PAGE, "text/html; charset=utf-8")
        self.submit_result = lambda p: (200, {"ok": True, "accepted": True})
        self.srv_error = None
        self.h = T.CrowdHelper(conf=lambda: self.cfg, srv=self.srv, azipi=self.azipi, clock=lambda: self.now[0], stats=Mem())

    def srv(self, method, path, payload=None):
        self.srv_calls.append((method, path))
        if self.srv_error:
            raise self.srv_error
        if path.startswith("/v1/crowd/task"):
            return 200, {"ok": True, "tasks": self.tasks[:2], "queue": len(self.tasks)}     # как аренда: пока не сдано, выдаётся снова
        if path == "/v1/crowd/submit":
            self.submits.append(payload)
            res = self.submit_result(payload)
            if res[0] != 429:
                self.tasks = [t for t in self.tasks if t["id"] != payload["id"]]
            return res
        raise AssertionError(path)

    def azipi(self, url):
        self.azipi_calls.append((self.now[0], url))
        r = self.azipi_result(url)
        if isinstance(r, Exception):
            raise r
        return r

    def run(self, seconds, step=1.0):
        """Крутит step() как фоновый поток: ждёт, сколько велено (не дольше step)."""
        end = self.now[0] + seconds
        while self.now[0] < end:
            d = self.h.step()
            self.now[0] += max(0.0, min(d, step)) or 0.01


def tasks(*urls):
    return [{"id": i + 1, "url": u} for i, u in enumerate(urls)]


class CrowdClientTests(unittest.TestCase):
    def test_enabled_by_default(self):
        self.assertTrue(T.DEFAULT_CONFIG["crowd_enabled"])
        self.assertFalse(T.DEFAULT_CONFIG["crowd_dismissed"])
        s = Sim(tasks(MSG % 1), enabled=False)
        s.run(120)
        self.assertEqual((s.srv_calls, s.azipi_calls, s.h.state), ([], [], "off"))

    def test_pace_and_submit(self):
        s = Sim(tasks(MSG % 1, MSG % 2, MSG % 3))
        s.run(60)
        times = [t for t, _u in s.azipi_calls]
        self.assertEqual([u for _t, u in s.azipi_calls], [MSG % 1, MSG % 2, MSG % 3])
        self.assertTrue(all(b - a >= T.CROWD_PACE - 0.001 for a, b in zip(times, times[1:])), times)
        self.assertEqual(len(s.submits), 3)
        p = s.submits[0]
        self.assertEqual((p["id"], p["url"], p["status"]), (1, MSG % 1, 200))
        self.assertEqual(gzip.decompress(base64.b64decode(p["body_b64"])), PAGE)
        self.assertEqual(s.h.stats.get()["accepted"], 3)

    def test_nothing_sent_besides_page_and_ids(self):
        s = Sim(tasks(MSG % 1))
        s.run(30)
        self.assertEqual(set(s.submits[0]), {"id", "url", "status", "body_b64", "ctype"})

    def test_no_tasks_polls_again_later(self):
        s = Sim([])
        s.run(T.CROWD_IDLE - 20)
        self.assertEqual(len(s.srv_calls), 1)
        self.assertEqual(s.h.state, "idle")
        s.tasks = tasks(MSG % 5)
        s.run(60)
        self.assertEqual([c[1].split("?")[0] for c in s.srv_calls[:3]], ["/v1/crowd/task", "/v1/crowd/task", "/v1/crowd/submit"])
        self.assertEqual([u for _t, u in s.azipi_calls], [MSG % 5])

    def test_backoff_30_min_after_azipi_error(self):
        for res in (OSError("down"), (429, b"", ""), (403, b"", ""), (503, b"", ""), (200, b"<html>Captcha</html>", "")):
            s = Sim(tasks(MSG % 1, MSG % 2))
            s.azipi_result = lambda url, res=res: res
            s.run(10)
            self.assertEqual(len(s.azipi_calls), 1, res)
            self.assertEqual(s.h.state, "backoff")
            self.assertEqual(s.submits, [])
            s.azipi_result = lambda url: (200, PAGE, "")
            s.tasks = tasks(MSG % 3)
            s.run(T.CROWD_BACKOFF - 60)
            self.assertEqual(len(s.azipi_calls), 1, "в паузе к azipi не ходим")
            s.run(200)
            self.assertEqual(len(s.azipi_calls), 2)                         # паузы прошли: продолжили с новых заданий

    def test_404_is_reported_without_body(self):
        s = Sim(tasks(MSG % 1))
        s.azipi_result = lambda url: (404, b"", "")
        s.run(30)
        self.assertEqual([(p["status"], p["body_b64"]) for p in s.submits], [(404, "")])

    def test_server_unavailable_stops_and_retries_later(self):
        s = Sim(tasks(MSG % 1))
        s.srv_error = OSError("refused")
        s.run(500)
        self.assertEqual((len(s.srv_calls), s.azipi_calls, s.h.state), (1, [], "no_server"))
        s.srv_error = None
        s.run(400)
        self.assertEqual(len(s.azipi_calls), 1)

    def test_no_server_or_key_means_idle(self):
        for cfg in ((True, "", "K"), (True, "http://srv", "")):
            s = Sim(tasks(MSG % 1))
            s.cfg = cfg
            s.run(60)
            self.assertEqual((s.srv_calls, s.azipi_calls, s.h.state), ([], [], "no_server"))

    def test_old_server_404_and_bad_key(self):
        for code in (404, 401):
            s = Sim()
            s.srv = lambda m, p, payload=None, code=code: (code, {})
            s.h.srv = s.srv
            s.run(100)
            self.assertEqual((s.azipi_calls, s.h.state), ([], "no_server"))

    def test_foreign_urls_from_server_are_ignored(self):
        bad = ["https://evil.example/x", "http://e-disclosure.azipi.ru/messages/1/", "https://e-disclosure.ru/messages/1/",
               "https://e-disclosure.azipi.ru/messages/1/?a=b", "file:///etc/passwd", "https://iss.moex.com/iss/x.json", 5, None]
        s = Sim([{"id": i, "url": u} for i, u in enumerate(bad, 1)])
        s.run(60)
        self.assertEqual((s.azipi_calls, s.submits), ([], []))
        self.assertTrue(T.crowd_url_ok(FEED % 3) and T.crowd_url_ok(MSG % 12))
        self.assertFalse(T.crowd_url_ok("https://e-disclosure.azipi.ru/messages/list/day-16.11.2026/?MESSAGE_BY_DAY=17.11.2026&PAGEN_2=1"))

    def test_server_rejects_three_times_then_backoff(self):
        s = Sim(tasks(MSG % 1, MSG % 2, MSG % 3, MSG % 4))
        s.submit_result = lambda p: (422, {"ok": False, "error": "x"})
        s.run(120)
        self.assertEqual(len(s.azipi_calls), 3)
        self.assertEqual(s.h.state, "backoff")

    def test_server_429_waits_retry_after(self):
        s = Sim(tasks(MSG % 1, MSG % 2))
        calls = []

        def res(p):
            calls.append(s.now[0])
            return (429, {"ok": False, "retry_after": 100}) if len(calls) == 1 else (200, {"ok": True, "accepted": True})
        s.submit_result = res
        s.run(60)
        self.assertEqual(len(s.azipi_calls), 1)
        s.run(120)
        self.assertEqual([u for _t, u in s.azipi_calls], [MSG % 1, MSG % 1, MSG % 2])     # задание не потеряно: сдано повторно после паузы


class RoutingTests(unittest.TestCase):
    """Страницы azipi идут напрямую; сервер данных получает только /v1/crowd/*."""

    class Resp:
        def __init__(self, url, body=b"x", status=200):
            self.url, self.body, self.status = url, body, status
            self.headers = {"Content-Type": "text/html"}

        def geturl(self):
            return self.url

        def read(self, n=-1):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def setUp(self):
        self.seen = []

        def fake(req, timeout=None, context=None):
            self.seen.append((req.full_url, dict(req.header_items()), context))
            if "/v1/crowd/" in req.full_url:
                return self.Resp(req.full_url, b'{"ok": true, "tasks": []}')
            return self.Resp(req.full_url, b"<html>azipi</html>")
        p = mock.patch("urllib.request.urlopen", fake)
        p.start()
        self.addCleanup(p.stop)
        for name, val in (("ds_conf", lambda: ("http://data.example", "TIA-KEY")),):
            q = mock.patch.object(T, name, val)
            q.start()
            self.addCleanup(q.stop)

    def test_azipi_direct_with_app_ssl_context_and_no_key(self):
        def boom(*a, **k):
            raise AssertionError("ext_open (маршрут через сервер данных) не должен использоваться")
        with mock.patch.object(T, "ext_open", boom):
            st, body, _ct = T.crowd_azipi_get(MSG % 77)
        self.assertEqual((st, body), (200, b"<html>azipi</html>"))
        url, headers, ctx = self.seen[0]
        self.assertEqual(url, MSG % 77)
        self.assertIs(ctx, T._ssl())
        self.assertNotIn("X-client-key", headers)
        self.assertNotIn("TIA-KEY", json.dumps(headers))

    def test_redirect_to_foreign_host_is_not_accepted(self):
        with mock.patch("urllib.request.urlopen", lambda req, timeout=None, context=None: self.Resp("https://evil.example/")):
            self.assertEqual(T.crowd_azipi_get(MSG % 1)[0], 0)

    def test_server_calls_go_only_to_data_server_crowd_paths(self):
        code, j = T.crowd_srv_call("GET", "/v1/crowd/task?n=2")
        self.assertEqual((code, j["ok"]), (200, True))
        url, headers, ctx = self.seen[0]
        self.assertEqual(url, "http://data.example/v1/crowd/task?n=2")
        self.assertEqual(headers.get("X-client-key"), "TIA-KEY")
        self.assertIs(ctx, T._ssl())

    def test_full_loop_with_real_functions(self):
        h = T.CrowdHelper(conf=lambda: (True, "http://data.example", "TIA-KEY"), stats=Mem(), pace=0.0)
        h.step()                                                             # пустой ответ сервера: заданий нет
        self.assertEqual([u for u, _h, _c in self.seen], ["http://data.example/v1/crowd/task?n=2"])
        self.assertEqual(h.state, "idle")


class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        c = T.load_config()
        c["crowd_enabled"], c["crowd_dismissed"] = False, False
        T.save_config(c)

    def test_enable_wakes_helper(self):
        T._crowd_wake.clear()
        T.api_crowd_settings(T.load_config(), {"enabled": True})
        self.assertTrue(T._crowd_wake.is_set())

    def tearDown(self):
        c = T.load_config()
        c["crowd_enabled"], c["crowd_dismissed"] = False, False
        T.save_config(c)

    def test_enable_and_dismiss(self):
        st = T.api_crowd_status(T.load_config(), "all", {}, False)
        self.assertEqual((st["enabled"], st["dismissed"], st["accepted"]), (False, False, 0))
        T.api_crowd_settings(T.load_config(), {"dismissed": True})
        self.assertTrue(T.load_config()["crowd_dismissed"])
        self.assertFalse(T.load_config()["crowd_enabled"])
        T.api_crowd_settings(T.load_config(), {"enabled": True})
        self.assertTrue(T.load_config()["crowd_enabled"])
        self.assertTrue(T.api_crowd_status(T.load_config(), "all", {}, False)["enabled"])
        T.api_crowd_settings(T.load_config(), {"enabled": False})
        self.assertFalse(T.load_config()["crowd_enabled"])
        self.assertIn("/api/crowd/status", T.API_GET)
        self.assertIn("/api/crowd/settings", T.API_POST)
        self.assertIn(T.crowd_start, T.STARTUP_HOOKS)


if __name__ == "__main__":
    unittest.main()
