"""Тесты лаунчера tinvest.py: без сети, без окна, в временной папке данных."""
import hashlib, importlib.util, io, json, os, queue, tempfile, threading, unittest, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    spec = importlib.util.spec_from_file_location("tinvest_launcher_under_test", os.path.join(ROOT, "tinvest.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


L = load()
CODE = b"print('hello')\n"
SHA = hashlib.sha256(CODE).hexdigest()


class FakeResp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeOpener:
    def __init__(self, data):
        self.data = data

    def open(self, req, timeout=None):
        return FakeResp(self.data)


class Sums(unittest.TestCase):
    def test_parse(self):
        txt = "%s  tinvest_analytics.py\n%s  TAnalytic-win.exe\n" % (SHA, "b" * 64)
        self.assertEqual(L.parse_sums(txt, "tinvest_analytics.py"), SHA)
        self.assertEqual(L.parse_sums(txt, "TAnalytic-win.exe"), "b" * 64)

    def test_binary_marker_and_case(self):
        self.assertEqual(L.parse_sums("%s *x.py" % SHA.upper(), "x.py"), SHA)

    def test_missing_or_bad(self):
        with self.assertRaises(ValueError):
            L.parse_sums("%s  other.py\n" % SHA, "tinvest_analytics.py")
        with self.assertRaises(ValueError):
            L.parse_sums("zzz  tinvest_analytics.py\n", "tinvest_analytics.py")


class Urls(unittest.TestCase):
    def test_check_url(self):
        L.check_url("https://api.github.com/x")
        L.check_url("https://release-assets.githubusercontent.com/a")
        for bad in ("http://github.com/x", "https://evil.example/x", "https://github.com.evil.io/x", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                L.check_url(bad)

    def test_redirect_validated(self):
        h = L.SafeRedirect()
        req = urllib.request.Request("https://github.com/a")
        ok = h.redirect_request(req, None, 302, "Found", {}, "https://objects.githubusercontent.com/f")
        self.assertEqual(ok.full_url, "https://objects.githubusercontent.com/f")
        with self.assertRaises(ValueError):
            h.redirect_request(req, None, 302, "Found", {}, "https://evil.example/f")
        with self.assertRaises(ValueError):
            h.redirect_request(req, None, 302, "Found", {}, "http://github.com/f")

    def test_fetch_progress_limit_cancel(self):
        data = b"x" * 200000
        seen = []
        got = L.fetch("https://github.com/a", progress=lambda *a: seen.append(a), opener=FakeOpener(data))
        self.assertEqual(got, data)
        self.assertEqual(seen[-1][:2], (200000, 200000))
        with self.assertRaises(ValueError):
            L.fetch("https://github.com/a", limit=100, opener=FakeOpener(data))
        ev = threading.Event()
        ev.set()
        with self.assertRaises(L.Cancelled):
            L.fetch("https://github.com/a", cancel=ev, opener=FakeOpener(data))
        with self.assertRaises(ValueError):
            L.fetch("https://evil.example/a", opener=FakeOpener(data))


class Format(unittest.TestCase):
    def test_progress_text(self):
        self.assertEqual(L.progress_text(12_300_000, 20_100_000, 2_400_000), "12,3 из 20,1 МБ · 2,4 МБ/с")
        self.assertEqual(L.progress_text(1_000_000, 0, 0), "1,0 МБ")

    def test_console_bar(self):
        s = L.console_bar(5, 10, 0, width=10)
        self.assertTrue(s.startswith("[#####-----]  50%"))
        self.assertTrue(L.console_bar(10, 10, 0, width=10).startswith("[##########] 100%"))
        self.assertTrue(L.console_bar(1, 0, 0, width=4).startswith("[----]"))

    def test_ver(self):
        self.assertEqual(L.ver("v1.2"), "v1.2")
        self.assertEqual(L.ver("1.2"), "v1.2")


class Update(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tinvest_launcher_")
        L.APP_DIR = os.path.join(self.tmp, "app")
        L.APP, L.VER = os.path.join(L.APP_DIR, L.FILE), os.path.join(L.APP_DIR, "version.txt")

    def fake(self, sums=None, tag="v9.9", code=CODE):
        rel = {"tag_name": tag, "assets": [
            {"name": "tinvest_analytics.py", "browser_download_url": "https://github.com/x/code"},
            {"name": "SHA256SUMS", "browser_download_url": "https://github.com/x/sums"}]}
        sums = sums if sums is not None else "%s  tinvest_analytics.py\n%s  TAnalytic-win.exe\n" % (SHA, "c" * 64)
        calls = []

        def fetch(url, limit=0, progress=None, cancel=None):
            calls.append(url)
            if url.endswith("/latest"):
                return json.dumps(rel).encode()
            if url.endswith("/sums"):
                return sums.encode()
            if progress:
                progress(len(code), len(code), 1.0)
            return code
        fetch.calls = calls
        return fetch

    def test_install_then_current(self):
        events = []
        self.assertEqual(L.update(lambda *e: events.append(e[0]), None, self.fake()), "updated")
        self.assertEqual(open(L.APP, "rb").read(), CODE)
        self.assertEqual(open(L.VER).read(), "v9.9")
        self.assertEqual(events, ["check", "download", "progress", "verify"])
        f = self.fake()
        self.assertEqual(L.update(lambda *e: None, None, f), "current")
        self.assertEqual(len(f.calls), 1)

    def test_keeps_backup(self):
        os.makedirs(L.APP_DIR)
        open(L.APP, "wb").write(b"old = 1\n")
        L.update(lambda *e: None, None, self.fake())
        self.assertEqual(open(L.APP + ".bak", "rb").read(), b"old = 1\n")

    def test_bad_checksum_leaves_app(self):
        os.makedirs(L.APP_DIR)
        open(L.APP, "wb").write(b"old = 1\n")
        with self.assertRaises(ValueError):
            L.update(lambda *e: None, None, self.fake(sums="%s  tinvest_analytics.py\n" % ("0" * 64)))
        self.assertEqual(open(L.APP, "rb").read(), b"old = 1\n")

    def test_syntax_error_rejected(self):
        bad = b"def (:\n"
        with self.assertRaises(SyntaxError):
            L.update(lambda *e: None, None, self.fake(sums="%s  tinvest_analytics.py\n" % hashlib.sha256(bad).hexdigest(), code=bad))
        self.assertFalse(os.path.exists(L.APP))

    def test_cancel_before_replace(self):
        ev = threading.Event()
        ev.set()
        with self.assertRaises(L.Cancelled):
            L.update(lambda *e: None, ev, self.fake())
        self.assertFalse(os.path.exists(L.APP))

    def test_worker_events(self):
        q = queue.Queue()
        orig = L.update

        def boom(*a, **k):
            raise OSError("нет сети")
        L.update = boom
        try:
            L.worker(q, threading.Event())
        finally:
            L.update = orig
        ev = q.get_nowait()
        self.assertEqual(ev[0], "error")
        self.assertTrue(ev[2])

    def test_write_tmp_failure_keeps_app(self):
        os.makedirs(L.APP_DIR)
        open(L.APP, "wb").write(b"old = 1\n")
        orig_open = open

        def fail_tmp(p, mode="r", *a, **k):
            if str(p).endswith(".tmp") and "w" in mode:
                raise OSError("disk full")
            return orig_open(p, mode, *a, **k)
        import unittest.mock as mock
        with mock.patch("builtins.open", side_effect=fail_tmp):
            with self.assertRaises(OSError):
                L.update(lambda *e: None, None, self.fake())
        self.assertEqual(open(L.APP, "rb").read(), b"old = 1\n")
        self.assertFalse(os.path.exists(L.APP + ".bak"))

    def test_replace_failure_rolls_back_bak(self):
        os.makedirs(L.APP_DIR)
        open(L.APP, "wb").write(b"old = 1\n")
        orig_replace = os.replace

        def fail_second_replace(src, dst):
            if str(src).endswith(".tmp"):
                raise OSError("locked")
            return orig_replace(src, dst)
        import unittest.mock as mock
        with mock.patch.object(L.os, "replace", side_effect=fail_second_replace):
            with self.assertRaises(OSError):
                L.update(lambda *e: None, None, self.fake())
        self.assertEqual(open(L.APP, "rb").read(), b"old = 1\n")

    def test_have_app_and_exec_fallback_to_bak(self):
        os.makedirs(L.APP_DIR)
        open(L.APP + ".bak", "wb").write(b"import sys\nsys.exit(0)\n")
        self.assertTrue(L.have_app())
        self.assertEqual(L.run_inprocess([], L.Console()), 0)
        open(L.APP, "wb").write(b"raise RuntimeError('broken')\n")
        self.assertEqual(L.run_inprocess([], L.Console()), 0)


class NativeWindow(unittest.TestCase):
    def test_want_native(self):
        self.assertTrue(L.want_native(True, False, {}))
        self.assertFalse(L.want_native(False, False, {}))                       # python3 tinvest.py — как раньше
        self.assertFalse(L.want_native(True, True, {}))                         # --no-gui
        self.assertFalse(L.want_native(True, False, {"TINVEST_NO_WEBVIEW": "1"}))

    def test_geometry_default_and_clamp(self):
        self.assertEqual(L.window_geometry(None, None), (1440, 900, None, None))
        self.assertEqual(L.window_geometry(None, (1512, 982)), (1440, 900, None, None))
        w, h, _, _ = L.window_geometry(None, (1280, 720))
        self.assertEqual((w, h), (1240, 680))                                   # 720-80=640 < min 680 -> 680
        w, h, _, _ = L.window_geometry({"w": 300, "h": 200}, (1920, 1080))
        self.assertEqual((w, h), (1024, 680))                                   # не меньше min_size

    def test_geometry_tiny_screen(self):
        w, h, _, _ = L.window_geometry(None, (800, 600))
        self.assertEqual((w, h), (800, 600))                                    # экран меньше минимума

    def test_geometry_position(self):
        self.assertEqual(L.window_geometry({"w": 1200, "h": 800, "x": 50, "y": 40}, (1920, 1080)), (1200, 800, 50, 40))
        self.assertEqual(L.window_geometry({"w": 1200, "h": 800, "x": 5000, "y": 40}, (1920, 1080))[2:], (None, None))
        self.assertEqual(L.window_geometry({"w": "x", "h": None, "x": True}, (1920, 1080)), (1440, 900, None, None))

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            old = L.STATE
            L.STATE = os.path.join(d, "window.json")
            try:
                self.assertIsNone(L.load_state())
                L.save_state(1300, 800, 10, 20)
                self.assertEqual(L.load_state(), {"w": 1300, "h": 800, "x": 10, "y": 20})
                with open(L.STATE, "w") as f:
                    f.write("[1")
                self.assertIsNone(L.load_state())
            finally:
                L.STATE = old

    def test_wait_ping_stops_when_thread_dead(self):
        t = threading.Thread(target=lambda: None)
        t.start()
        t.join()
        self.assertFalse(L.wait_ping(lambda: "", t, timeout=2))


class Splash(unittest.TestCase):
    def test_html_filled(self):
        for plat in ("darwin", "win32"):
            h = L.splash_html(plat)
            self.assertNotIn("__", h.replace("__main__", ""))               # все подстановки сделаны
            self.assertIn('class="%s"' % ("win" if plat == "win32" else "mac"), h)
            self.assertIn("<svg", h)

    def test_states(self):
        self.assertEqual(L.splash_state(("check",))["title"], "Проверяю обновления")
        s = L.splash_state(("progress", 500_000, 2_000_000, 1e6), "1.2")
        self.assertEqual((s["pct"], s["title"], s["step"]), (25, "Скачиваю обновление 25%", 1))
        self.assertTrue(s["detail"].startswith("v1.2 · "))
        self.assertIsNone(L.splash_state(("progress", 10, 0, 0))["pct"])     # размер неизвестен — бегущая полоса
        self.assertEqual(L.splash_state(("verify", "v1"))["step"], 2)
        self.assertIsNone(L.splash_state(("ok", "current")))

    def test_api_routes_to_queue(self):
        class Sh:
            got = []
            def ui(self, a): self.got.append(a)
        api = L.SplashApi(Sh())
        api.retry(); api.run(); api.close(); api.browser()
        self.assertEqual(Sh.got, ["retry", "run", "close", "browser"])
        self.assertEqual([n for n in dir(api) if not n.startswith("_")], ["browser", "close", "retry", "run"])


if __name__ == "__main__":
    unittest.main()
