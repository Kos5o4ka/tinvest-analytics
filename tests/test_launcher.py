"""Тесты лаунчера tinvest.py: без сети, без окна, в временной папке данных."""
import sys, hashlib, importlib.util, io, json, os, queue, shutil, subprocess, tempfile, threading, unittest, urllib.request

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

    def test_no_bak_fallback_on_interrupt_or_late_crash(self):
        os.makedirs(L.APP_DIR)
        open(L.APP + ".bak", "wb").write(b"import sys\nsys.exit(7)\n")
        open(L.APP, "wb").write(b"raise KeyboardInterrupt\n")
        self.assertEqual(L.run_inprocess([], L.Console()), 130)               # Ctrl+C — выход, а не запуск старой версии
        open(L.APP, "wb").write(b"raise RuntimeError('late')\n")
        import unittest.mock as mock
        ts = iter([0.0, L.APP_START_GRACE + 5.0])
        with mock.patch.object(L.time, "time", side_effect=lambda: next(ts)):
            res = {}
            L._exec_app([], res)
        self.assertIn("late", res.get("err", ""))                              # упала после запуска — .bak не трогаем


class NativeWindow(unittest.TestCase):
    def test_want_native(self):
        self.assertTrue(L.want_native(True, False, {}))
        self.assertFalse(L.want_native(False, False, {}))                       # python3 tinvest.py — как раньше
        self.assertFalse(L.want_native(True, True, {}))                         # --no-gui
        self.assertFalse(L.want_native(True, False, {"TINVEST_NO_WEBVIEW": "1"}))

    def test_geometry_default_and_clamp(self):
        self.assertEqual(L.window_geometry(None, None), (1440, 900, None, None))
        self.assertEqual(L.window_geometry(None, (1512, 982)), (1440, 900, 36, 32))      # по центру экрана
        w, h, _, _ = L.window_geometry(None, (1280, 720))
        self.assertEqual((w, h), (1240, 680))                                   # 720-80=640 < min 680 -> 680
        w, h, _, _ = L.window_geometry({"w": 300, "h": 200}, (1920, 1080))
        self.assertEqual((w, h), (1024, 680))                                   # не меньше min_size

    def test_geometry_tiny_screen(self):
        w, h, _, _ = L.window_geometry(None, (800, 600))
        self.assertEqual((w, h), (800, 600))                                    # экран меньше минимума

    def test_geometry_position(self):
        self.assertEqual(L.window_geometry({"w": 1200, "h": 800, "x": 50, "y": 40}, (1920, 1080)), (1200, 800, 50, 40))
        self.assertEqual(L.window_geometry({"w": 1200, "h": 800, "x": 5000, "y": 40}, (1920, 1080))[2:], (360, 112))
        self.assertEqual(L.window_geometry({"w": "x", "h": None, "x": True}, (1920, 1080)), (1440, 900, 240, 72))

    def test_geometry_windows_maximized_frame(self):
        # развёрнутое окно Windows закрывается в (-8, -8): это не «за экраном», позиция сохраняется
        self.assertEqual(L.window_geometry({"w": 1300, "h": 800, "x": -8, "y": -8}, (1920, 1040))[2:], (-8, 0))
        self.assertTrue(L.looks_maximized(1936, 1056, -8, -8, (1920, 1040)))
        self.assertFalse(L.looks_maximized(1200, 800, 10, 10, (1920, 1040)))
        self.assertTrue(L.was_maximized({"maximized": True}))
        self.assertFalse(L.was_maximized(None))

    def test_center(self):
        self.assertEqual(L.center(520, 330, (1920, 1080)), (700, 300))
        self.assertEqual(L.center(520, 330, None), (None, None))

    def test_colorref(self):
        self.assertEqual(L.colorref("#090c12"), 0x120c09)

    def test_start_kwargs_persistent_profile(self):
        kw = L.start_kwargs()
        self.assertFalse(kw["private_mode"])
        self.assertTrue(kw["storage_path"].endswith("webview"))

    def test_single_instance_lock(self):
        if sys.platform == "win32":
            self.skipTest("мьютекс проверяется на Windows вручную")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.lock")
            a, b = L.SingleInstance(path=p), L.SingleInstance(path=p)
            self.assertTrue(a.acquire())
            self.assertFalse(b.acquire())
            a.release()
            self.assertTrue(b.acquire())
            b.release()

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            old = L.STATE
            L.STATE = os.path.join(d, "window.json")
            try:
                self.assertIsNone(L.load_state())
                L.save_state(1300, 800, 10, 20)
                self.assertEqual(L.load_state(), {"w": 1300, "h": 800, "x": 10, "y": 20})
                L.save_state(1300, 800, 10, 20, maximized=True)
                self.assertTrue(L.load_state()["maximized"])
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
        for plat, build, cls in (("darwin", 0, "mac"), ("win32", 22631, "win"), ("win32", 19045, "win win10")):
            h = L.splash_html(plat, build)
            self.assertNotIn("__", h.replace("__main__", ""))               # все подстановки сделаны
            self.assertIn('class="%s"' % cls, h)
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
        self.assertEqual([n for n in dir(api) if not n.startswith("_")], ["browser", "close", "minimize", "retry", "run"])


class TrayLogic(unittest.TestCase):
    """Трей без Windows: решения принимаются чистыми функциями, WinForms-часть проверяется вручную."""
    def test_should_hide_on_close(self):
        self.assertTrue(L.should_hide_on_close(False, True, True))
        self.assertFalse(L.should_hide_on_close(True, True, True))      # настоящий выход (Выход в трее, обновление)
        self.assertFalse(L.should_hide_on_close(False, False, True))    # значка нет — закрываем, невидимой программы не бывает
        self.assertFalse(L.should_hide_on_close(False, True, False))    # настройка выключена (по умолчанию)

    def test_tray_wanted_reads_app_hook(self):
        old = getattr(sys, "tanalytic_tray", None)
        try:
            sys.tanalytic_tray = lambda: True
            self.assertTrue(L.tray_wanted())
            sys.tanalytic_tray = lambda: 1 / 0
            self.assertFalse(L.tray_wanted())                           # ошибка в программе не мешает закрыть окно
            sys.tanalytic_tray = None
            self.assertFalse(L.tray_wanted())
        finally:
            if old is None:
                del sys.tanalytic_tray
            else:
                sys.tanalytic_tray = old

    def test_split_args_strips_tray(self):
        r = L.split_args(["--tray", "--no-update", "--port", "9"], env={}, plat="win32")
        self.assertEqual(r, (True, False, True, ["--port", "9"]))
        self.assertEqual(L.split_args(["--tray"], env={}, plat="darwin")[2:], (False, []))   # на macOS трея нет
        self.assertTrue(L.split_args([], env={"TINVEST_NO_GUI": "1"}, plat="win32")[1])

    def test_tray_without_windows_is_harmless(self):
        class W:
            native = None
        t = L.Tray(W())
        self.assertFalse(t.start(force=True))                           # нет WinForms — значка нет, ошибки нет
        self.assertFalse(t.ready)
        t.dispose()
        t.sync()


class ShellUpdate(unittest.TestCase):
    """Обновление оболочки: установщик с GitHub, сверка SHA256, запуск без сети и без Windows."""
    SETUP = b"MZ fake installer" * 100
    SETUP_SHA = hashlib.sha256(SETUP).hexdigest()

    def rel(self, tag="v9.9", url="https://github.com/x/Setup.exe"):
        return {"tag_name": tag, "assets": [
            {"name": L.SETUP_ASSET, "browser_download_url": url},
            {"name": "SHA256SUMS", "browser_download_url": "https://github.com/x/sums"}]}

    def fake(self, rel=None, sums=None, blob=None):
        rel = rel or self.rel()
        sums = sums if sums is not None else "%s  tinvest_analytics.py\n%s  %s\n" % (SHA, self.SETUP_SHA, L.SETUP_ASSET)
        blob = self.SETUP if blob is None else blob
        calls = []

        def fetch(url, limit=0, progress=None, cancel=None):
            calls.append((url, limit))
            if url.endswith("/latest"):
                return json.dumps(rel).encode()
            if url.endswith("/sums"):
                return sums.encode()
            return blob
        fetch.calls = calls
        return fetch

    def test_asset_name_matches_workflow(self):
        yml = open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8").read()
        self.assertIn("asset: " + L.SETUP_ASSET, yml)
        self.assertEqual(L.SETUP_ARGS[0], "/S")                  # NSIS: тихая установка

    def test_pick_setup(self):
        self.assertEqual(L.pick_setup(self.rel()), ("https://github.com/x/Setup.exe", "https://github.com/x/sums"))
        with self.assertRaises(ValueError):
            L.pick_setup({"tag_name": "v1", "assets": [{"name": "SHA256SUMS", "browser_download_url": "https://github.com/x/sums"}]})
        with self.assertRaises(ValueError):                       # адрес не с доменов GitHub
            L.pick_setup(self.rel(url="https://evil.example/Setup.exe"))
        with self.assertRaises(ValueError):
            L.pick_setup(self.rel(url="http://github.com/x/Setup.exe"))

    def test_prepare_downloads_and_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            f = self.fake()
            info = L.prepare_installer(d, fetch=f)
            self.assertEqual(info["tag"], "v9.9")
            self.assertEqual(info["path"], os.path.join(d, L.SETUP_ASSET))
            self.assertEqual(open(info["path"], "rb").read(), self.SETUP)
            self.assertEqual(f.calls[-1][1], L.SETUP_LIMIT)       # установщик больше обычного лимита в 20 МБ
            self.assertGreater(L.SETUP_LIMIT, 20_000_000)
            self.assertFalse(os.path.exists(info["path"] + ".part"))

    def test_prepare_rejects_bad_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                L.prepare_installer(d, fetch=self.fake(blob=b"substituted"))
            self.assertEqual(os.listdir(d), [])                   # на диск ничего не попало

    def test_prepare_missing_sum_line(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                L.prepare_installer(d, fetch=self.fake(sums="%s  tinvest_analytics.py\n" % SHA))
            self.assertEqual(os.listdir(d), [])

    def test_prepare_reuses_verified_file(self):
        with tempfile.TemporaryDirectory() as d:
            L.prepare_installer(d, fetch=self.fake())
            f = self.fake(blob=b"must not be downloaded")
            info = L.prepare_installer(d, fetch=f)
            self.assertEqual(info["sha"], self.SETUP_SHA)
            self.assertEqual(len(f.calls), 2)                      # описание релиза и суммы, сам файл не качали

    def test_prepare_replaces_corrupt_old_file(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, L.SETUP_ASSET), "wb") as fh:
                fh.write(b"corrupt")
            info = L.prepare_installer(d, fetch=self.fake())
            self.assertEqual(open(info["path"], "rb").read(), self.SETUP)

    def test_start_installer_args_and_recheck(self):
        with tempfile.TemporaryDirectory() as d:
            info = L.prepare_installer(d, fetch=self.fake())
            got = []
            L.start_installer(info, popen=lambda cmd, **kw: got.append((cmd, kw)))
            cmd, kw = got[0]
            self.assertEqual(cmd[0], info["path"])
            self.assertIn("/S", cmd)
            self.assertTrue(kw["close_fds"])
            with open(info["path"], "ab") as fh:                   # файл изменили после проверки
                fh.write(b"x")
            with self.assertRaises(ValueError):
                L.start_installer(info, popen=lambda *a, **k: self.fail("не должен запускаться"))

    def test_install_and_exit_releases_lock_first(self):
        order = []

        class Lock:
            def release(self): order.append("release")
            def acquire(self): order.append("acquire")
        old = L.LOCK
        L.LOCK = Lock()
        try:
            with tempfile.TemporaryDirectory() as d:
                info = L.prepare_installer(d, fetch=self.fake())
                self.assertTrue(L.install_and_exit(info, popen=lambda *a, **k: order.append("popen"),
                                                   exit_fn=lambda c: order.append("exit%d" % c)))
                self.assertEqual(order, ["release", "popen", "exit0"])
                self.assertTrue(L.QUITTING.is_set())
                L.QUITTING.clear()
                order.clear()
                with open(info["path"], "ab") as fh:
                    fh.write(b"x")
                self.assertFalse(L.install_and_exit(info, popen=lambda *a, **k: order.append("popen"),
                                                    exit_fn=lambda c: order.append("exit")))
                self.assertEqual(order, ["release", "acquire"])    # запуск не удался: мьютекс возвращён, выхода нет
                self.assertFalse(L.QUITTING.is_set())
        finally:
            L.LOCK = old
            L.QUITTING.clear()

    def test_update_supported_only_in_frozen_windows(self):
        self.assertFalse(L.shell_update_supported())               # тесты идут из исходников
        r = L.MainApi().shell_update_prepare()
        self.assertIn("error", r)
        self.assertIn("error", L.MainApi().shell_update_run())


class FakeProc:
    def __init__(self, rc=0, err=b""):
        self.returncode, self.stderr, self.stdout = rc, err, b""


class MacShellUpdate(unittest.TestCase):
    """Обновление оболочки на macOS: выбор образа, сверка суммы, отказ при транслокации, откат. Без hdiutil и без сети."""
    DMG = b"fake dmg" * 200
    DMG_SHA = hashlib.sha256(DMG).hexdigest()

    def test_asset_by_platform_and_arch(self):
        self.assertEqual(L.shell_asset("darwin", "arm64"), "TAnalytic-mac-arm64.dmg")
        self.assertIsNone(L.shell_asset("darwin", "x86_64"))              # Mac на Intel: сборки нет
        self.assertEqual(L.shell_asset("win32", "AMD64"), L.SETUP_ASSET)
        self.assertIsNone(L.shell_asset("linux", "x86_64"))
        yml = open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8").read()
        for a in L.MAC_ASSETS.values():
            self.assertIn("asset: " + a, yml)

    def test_prepare_mac_dmg_verifies_sum(self):
        name = L.MAC_ASSETS["arm64"]
        rel = {"tag_name": "v9.9", "assets": [{"name": name, "browser_download_url": "https://github.com/x/m.dmg"},
                                              {"name": "SHA256SUMS", "browser_download_url": "https://github.com/x/sums"}]}

        def fake(blob):
            sums = "%s  %s\n" % (self.DMG_SHA, name)

            def fetch(url, limit=0, progress=None, cancel=None):
                return json.dumps(rel).encode() if url.endswith("/latest") else sums.encode() if url.endswith("/sums") else blob
            return fetch
        with tempfile.TemporaryDirectory() as d:
            info = L.prepare_installer(d, fetch=fake(self.DMG), asset=name)
            self.assertEqual(info["path"], os.path.join(d, name))
            self.assertEqual(info["sha"], self.DMG_SHA)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                L.prepare_installer(d, fetch=fake(b"substituted"), asset=name)
            self.assertFalse(os.path.exists(os.path.join(d, name)))
        with tempfile.TemporaryDirectory() as d:                   # для образа x64 в релизе нет ни файла, ни суммы
            with self.assertRaises(ValueError):
                L.prepare_installer(d, fetch=fake(self.DMG), asset="TAnalytic-mac-x64.dmg")

    def test_app_path_from_executable(self):
        self.assertEqual(L.mac_app_path("/Applications/TAnalytic.app/Contents/MacOS/TAnalytic"), "/Applications/TAnalytic.app")
        self.assertEqual(L.mac_app_path("/Users/u/Apps/My App.app/Contents/MacOS/TAnalytic"), "/Users/u/Apps/My App.app")
        self.assertIsNone(L.mac_app_path("/usr/bin/python3"))

    def test_blocker_translocation_readonly_not_app(self):
        yes = lambda p, m: True
        self.assertIsNone(L.mac_update_blocker("/Applications/TAnalytic.app", access=yes))
        self.assertIn("временной копии", L.mac_update_blocker(
            "/private/var/folders/ab/T/AppTranslocation/1-2-3/d/TAnalytic.app", access=yes))
        self.assertIn("временной копии", L.mac_update_blocker("/private/var/folders/x/TAnalytic.app", access=yes))
        self.assertIn("нельзя заменить", L.mac_update_blocker("/Volumes/TAnalytic/TAnalytic.app", access=lambda p, m: False))
        self.assertIn("не из", L.mac_update_blocker(None, access=yes))

    def make_world(self, d):
        """Установленное приложение с меткой OLD и образ-файл с верной суммой."""
        app = os.path.join(d, "Apps", "TAnalytic.app")
        os.makedirs(os.path.join(app, "Contents"))
        with open(os.path.join(app, "Contents", "v.txt"), "w") as f:
            f.write("OLD")
        dmg = os.path.join(d, "x.dmg")
        with open(dmg, "wb") as f:
            f.write(self.DMG)
        return app, {"path": dmg, "sha": self.DMG_SHA}

    def fake_run(self, fail=None, src_ok=True):
        """Подмена subprocess.run: «монтирование» создаёт папку с новым приложением, ditto копирует."""
        log = []

        def run(cmd, **kw):
            log.append(cmd)
            tool = cmd[0]
            if fail == tool:
                return FakeProc(1, b"boom\n")
            if tool == "hdiutil" and cmd[1] == "attach":
                mnt = cmd[cmd.index("-mountpoint") + 1]
                if src_ok:
                    os.makedirs(os.path.join(mnt, "TAnalytic.app", "Contents"))
                    with open(os.path.join(mnt, "TAnalytic.app", "Contents", "v.txt"), "w") as f:
                        f.write("NEW")
            elif tool == "ditto":
                shutil.copytree(cmd[1], cmd[2])
            return FakeProc()
        run.log = log
        return run

    def read(self, app):
        with open(os.path.join(app, "Contents", "v.txt")) as f:
            return f.read()

    def test_replace_ok_and_command_order(self):
        with tempfile.TemporaryDirectory() as d:
            app, info = self.make_world(d)
            run = self.fake_run()
            res = L.mac_replace_app(info, app, run=run, workdir=os.path.join(d, "w"), pid=7)
            self.assertEqual(self.read(app), "NEW")
            self.assertEqual(self.read(res["old"]), "OLD")
            self.assertEqual(os.path.dirname(res["old"]), os.path.dirname(app))      # рядом: переименование внутри одного тома
            self.assertEqual([c[0] for c in run.log], ["hdiutil", "ditto", "xattr", "codesign", "hdiutil"])
            for flag in ("-nobrowse", "-readonly"):
                self.assertIn(flag, run.log[0])
            self.assertEqual(run.log[2][:3], ["xattr", "-dr", "com.apple.quarantine"])
            self.assertEqual(run.log[-1][:2], ["hdiutil", "detach"])
            self.assertEqual([n for n in os.listdir(os.path.dirname(app)) if "new" in n], [])   # временной копии не осталось

    def test_rollback_on_each_failure(self):
        for fail in ("ditto", "xattr", "codesign"):
            with tempfile.TemporaryDirectory() as d:
                app, info = self.make_world(d)
                run = self.fake_run(fail=fail)
                with self.assertRaises(L.MacUpdateError):
                    L.mac_replace_app(info, app, run=run, workdir=os.path.join(d, "w"), pid=7)
                self.assertEqual(self.read(app), "OLD", fail)
                self.assertEqual(sorted(os.listdir(os.path.dirname(app))), ["TAnalytic.app"], fail)
                self.assertEqual(run.log[-1][:2], ["hdiutil", "detach"], fail)       # образ отмонтирован и при ошибке

    def test_rollback_when_final_rename_fails(self):
        with tempfile.TemporaryDirectory() as d:
            app, info = self.make_world(d)
            real = os.rename

            def rename(a, b):
                if b == app and a.endswith("new-7"):
                    raise OSError("нет места")
                return real(a, b)
            L.os.rename = rename
            try:
                with self.assertRaises(L.MacUpdateError):
                    L.mac_replace_app(info, app, run=self.fake_run(), workdir=os.path.join(d, "w"), pid=7)
            finally:
                L.os.rename = real
            self.assertEqual(self.read(app), "OLD")
            self.assertEqual(sorted(os.listdir(os.path.dirname(app))), ["TAnalytic.app"])

    def test_image_without_app_and_changed_file(self):
        with tempfile.TemporaryDirectory() as d:
            app, info = self.make_world(d)
            with self.assertRaises(L.MacUpdateError):
                L.mac_replace_app(info, app, run=self.fake_run(src_ok=False), workdir=os.path.join(d, "w"), pid=7)
            self.assertEqual(self.read(app), "OLD")
            with open(info["path"], "ab") as f:
                f.write(b"x")
            run = self.fake_run()
            with self.assertRaises(L.MacUpdateError):
                L.mac_replace_app(info, app, run=run, workdir=os.path.join(d, "w"), pid=7)
            self.assertEqual(run.log, [])                          # изменённый образ даже не монтируется

    def test_install_refuses_translocated_and_does_not_touch(self):
        with tempfile.TemporaryDirectory() as d:
            _, info = self.make_world(d)
            run = self.fake_run()
            ok = L.install_mac_and_exit(info, app="/private/var/folders/ab/T/AppTranslocation/1/d/TAnalytic.app",
                                        run=run, popen=lambda *a, **k: self.fail("перезапуск не нужен"),
                                        exit_fn=lambda c: self.fail("выходить нельзя"))
            self.assertFalse(ok)
            self.assertEqual(run.log, [])
            self.assertFalse(L.QUITTING.is_set())

    def test_install_relaunch_then_exit_and_rollback(self):
        old_blocker, old_dir = L.mac_update_blocker, L.UPDATE_DIR
        L.mac_update_blocker = lambda a, access=None: None
        try:
            with tempfile.TemporaryDirectory() as d:
                L.UPDATE_DIR = os.path.join(d, "upd")
                app, info = self.make_world(d)
                order = []

                def popen(cmd, **kw):
                    order.append("popen")
                    self.assertEqual(cmd[:2], ["/bin/sh", "-c"])
                    self.assertIn("open -n", cmd[2])
                    self.assertEqual(cmd[-2], app)                  # перезапускаем именно тот путь, где стоит приложение
                    self.assertTrue(kw["start_new_session"])
                self.assertTrue(L.install_mac_and_exit(info, app=app, run=self.fake_run(), popen=popen,
                                                       exit_fn=lambda c: order.append("exit%d" % c)))
                self.assertEqual(order, ["popen", "exit0"])         # выход — только после запуска перезапуска
                self.assertEqual(self.read(app), "NEW")
                L.QUITTING.clear()
                # перезапуск запустить не удалось — прежнее приложение возвращается, программа не закрывается
                d2 = os.path.join(d, "b")
                os.makedirs(d2)
                app2, info2 = self.make_world(d2)

                def bad(*a, **k):
                    raise OSError("нет sh")
                ok = L.install_mac_and_exit(info2, app=app2, run=self.fake_run(), popen=bad,
                                            exit_fn=lambda c: self.fail("выходить нельзя"))
                self.assertFalse(ok)
                self.assertEqual(self.read(app2), "OLD")
                self.assertEqual(sorted(os.listdir(os.path.dirname(app2))), ["TAnalytic.app"])
                self.assertFalse(L.QUITTING.is_set())
        finally:
            L.mac_update_blocker, L.UPDATE_DIR = old_blocker, old_dir
            L.QUITTING.clear()

    def test_relaunch_command_is_valid_shell(self):
        r = subprocess.run(["/bin/sh", "-n", "-c", L.MAC_RELAUNCH], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
