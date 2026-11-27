"""Переезд со старой оболочки на Tauri: определение, выбор ассета, сверка суммы, адреса GitHub, .cmd без инъекций,
порядок «запустить -> выйти», macOS (целевая папка, откат). Сеть, subprocess и файловая система подменены."""
import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

M = _load.load()


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Detect(unittest.TestCase):
    def test_old_frozen_launcher(self):
        self.assertTrue(M.migrate_old_shell(env={}, frozen=True, plat="win32"))
        self.assertTrue(M.migrate_old_shell(env={"TINVEST_SHELL_REV": "3"}, frozen=True, plat="darwin"))

    def test_rev_without_frozen(self):
        self.assertTrue(M.migrate_old_shell(env={"TINVEST_SHELL_REV": "4"}, frozen=False, plat="win32"))

    def test_source_run_not_migrated(self):
        self.assertFalse(M.migrate_old_shell(env={}, frozen=False, plat="win32"))
        self.assertFalse(M.migrate_old_shell(env={}, frozen=False, plat="darwin"))

    def test_tauri_not_migrated(self):
        self.assertFalse(M.migrate_old_shell(env={"TINVEST_SHELL": "tauri"}, frozen=True, plat="win32"))

    def test_linux_and_new_rev(self):
        self.assertFalse(M.migrate_old_shell(env={}, frozen=True, plat="linux"))
        self.assertFalse(M.migrate_old_shell(env={"TINVEST_SHELL_REV": "5"}, frozen=True, plat="win32"))

    def test_shell_status_flag(self):
        self.assertIn("migrate", M.shell_status(env={}, frozen=False))


class Asset(unittest.TestCase):
    def test_choice(self):
        self.assertEqual(M.migrate_asset("win32"), "TAnalytic-Setup-win.exe")
        self.assertEqual(M.migrate_asset("darwin", "arm64"), "TAnalytic-mac-arm64.dmg")
        self.assertIsNone(M.migrate_asset("darwin", "x86_64"))            # Mac на Intel: сборки нет
        with self.assertRaises(M.MigrateError):
            M.migrate_asset("linux")


class Net(unittest.TestCase):
    def test_hosts(self):
        for u in ("https://api.github.com/x", "https://github.com/a", "https://objects.githubusercontent.com/a",
                  "https://release-assets.githubusercontent.com/a"):
            self.assertEqual(M.migrate_check_url(u), u)
        for u in ("http://github.com/a", "https://evil.com/a", "https://github.com.evil.com/a",
                  "https://evilgithub.com/a", "ftp://github.com/a", "file:///etc/passwd"):
            with self.assertRaises(M.MigrateError):
                M.migrate_check_url(u)

    def test_redirect_checked(self):
        h = M._MigrateRedirect()
        import urllib.request
        req = urllib.request.Request("https://github.com/a")
        with self.assertRaises(M.MigrateError):
            h.redirect_request(req, None, 302, "Found", {}, "https://evil.example/a")
        with self.assertRaises(M.MigrateError):
            h.redirect_request(req, None, 302, "Found", {}, "http://objects.githubusercontent.com/a")

    def test_parse_sums(self):
        s = "%s  other\n%s *TAnalytic-Setup-win.exe\n" % ("a" * 64, "B" * 64)
        self.assertEqual(M.migrate_parse_sums(s, "TAnalytic-Setup-win.exe"), "b" * 64)
        with self.assertRaises(M.MigrateError):
            M.migrate_parse_sums(s, "missing")

    def _release(self, asset, url="https://github.com/o/r/releases/download/v1/%s", sums="https://github.com/o/r/releases/download/v1/SHA256SUMS"):
        return {"tag_name": "v1", "assets": [{"name": asset, "browser_download_url": url % asset},
                                              {"name": "SHA256SUMS", "browser_download_url": sums}]}

    def _fetch(self, rel, data, sums_hash):
        calls = []

        def fetch(url, sink=None, limit=0, progress=None):
            calls.append(url)
            if url.endswith("/releases/latest"):
                return json.dumps(rel).encode(), ""
            if url.endswith("SHA256SUMS"):
                return ("%s  TAnalytic-Setup-win.exe\n" % sums_hash).encode(), ""
            sink.write(data)
            return None, sha(data)
        return fetch, calls

    def test_download_ok_and_sum_mismatch(self):
        data = b"installer-bytes"
        with tempfile.TemporaryDirectory() as d:
            f, calls = self._fetch(self._release("TAnalytic-Setup-win.exe"), data, sha(data))
            info = M.migrate_download(d, "TAnalytic-Setup-win.exe", fetch=f)
            self.assertEqual(open(info["path"], "rb").read(), data)
            self.assertEqual(info["tag"], "v1")
            self.assertEqual(len(calls), 3)
        with tempfile.TemporaryDirectory() as d:
            f, _ = self._fetch(self._release("TAnalytic-Setup-win.exe"), data, sha(b"other"))
            with self.assertRaises(M.MigrateError):
                M.migrate_download(d, "TAnalytic-Setup-win.exe", fetch=f)
            self.assertEqual(os.listdir(d), [])            # плохой файл не остаётся

    def test_non_github_asset_url_rejected(self):
        rel = self._release("TAnalytic-Setup-win.exe", url="https://evil.example/%s")
        f, _ = self._fetch(rel, b"x", sha(b"x"))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(M.MigrateError):
                M.migrate_download(d, "TAnalytic-Setup-win.exe", fetch=f)

    def test_release_without_asset(self):
        with self.assertRaises(M.MigrateError):
            M.migrate_pick({"tag_name": "v1", "assets": []}, "TAnalytic-Setup-win.exe")


class WinCmd(unittest.TestCase):
    W = "C:\\Users\\u\\AppData\\Local\\Temp\\tanalytic_migrate_x"
    I = W + "\\TAnalytic-Setup-win.exe"

    def test_cmd_content(self):
        t = M.win_build_cmd(1234, self.I, self.W, "C:\\Users\\u\\Downloads\\TAnalytic-win.exe")
        self.assertIn('"PID eq 1234"', t)
        self.assertIn('start "" /wait "%s" /S' % self.I, t)
        self.assertIn('del /f /q "C:\\Users\\u\\Downloads\\TAnalytic-win.exe"', t)
        self.assertLess(t.index("/wait"), t.index("del /f"))
        self.assertIn("TAnalytic.exe", t)
        self.assertNotIn("/AUTORUN", t.upper())

    def test_no_old_exe(self):
        t = M.win_build_cmd(1, self.I, self.W, None)
        self.assertNotIn("del /f", t)

    def test_injection_rejected(self):
        for bad in ('C:\\a"&calc&"\\x.exe', "C:\\a%PATH%\\x.exe", "C:\\a^b\\x.exe", "C:\\a|b\\x.exe", "C:\\a\r\nb\\x.exe", "rel\\x.exe",
                    "C:\\a!b\\x.exe"):
            with self.assertRaises(M.MigrateError):
                M.win_build_cmd(1, bad, self.W)
            with self.assertRaises(M.MigrateError):
                M.win_build_cmd(1, self.I, self.W, bad)
        with self.assertRaises(ValueError):
            M.win_build_cmd("1&calc", self.I, self.W)

    def test_old_exe_rules(self):
        env = {"ProgramFiles": "C:\\Program Files", "LOCALAPPDATA": "C:\\Users\\u\\AppData\\Local"}
        self.assertEqual(M.win_old_exe("C:\\Users\\u\\Downloads\\TAnalytic-win.exe", env), "C:\\Users\\u\\Downloads\\TAnalytic-win.exe")
        self.assertIsNone(M.win_old_exe("C:\\Program Files\\TAnalytic\\TAnalytic.exe", env))
        self.assertIsNone(M.win_old_exe("C:\\Users\\u\\AppData\\Local\\Programs\\TAnalytic\\TAnalytic.exe", env))
        self.assertIsNone(M.win_old_exe("C:\\Users\\u\\AppData\\Local\\TAnalytic\\TAnalytic.exe", env))
        self.assertIsNone(M.win_old_exe("C:\\Users\\u\\Downloads\\python.exe", env))
        self.assertIsNone(M.win_old_exe("C:\\Users\\u\\Downloads\\TAnalytic-win.bat", env))
        self.assertIsNone(M.win_old_exe("C:\\Users\\u\\Downloads\\other-TAnalytic.exe", env))

    def test_spawn_flags_and_argv(self):
        got = {}

        def popen(argv, **kw):
            got["argv"], got["kw"] = argv, kw
        M.win_spawn_cmd("C:\\t\\migrate.cmd", popen)
        self.assertEqual(got["argv"], ["cmd.exe", "/d", "/c", "C:\\t\\migrate.cmd"])
        self.assertTrue(got["kw"]["creationflags"] & 0x00000200)
        self.assertNotIn("shell", got["kw"])

    def test_win_migrate_checks_sum_and_writes_cmd(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "TAnalytic-Setup-win.exe")
            open(p, "wb").write(b"abc")
            with self.assertRaises(M.MigrateError):
                M.win_migrate({"path": p, "sha": sha(b"zzz")}, d, popen=lambda *a, **k: None)
            seen, keep = [], M._cmd_path
            M._cmd_path = lambda x: x                      # на не-Windows пути POSIX; проверка символов покрыта выше
            try:
                M.win_migrate({"path": p, "sha": sha(b"abc")}, d, pid=7, exe=None, env={}, popen=lambda a, **k: seen.append(a))
            finally:
                M._cmd_path = keep
            self.assertTrue(os.path.isfile(os.path.join(d, "migrate.cmd")))
            self.assertEqual(len(seen), 1)


class RunOrder(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.keep = {k: getattr(M, k) for k in ("migrate_download", "win_migrate", "mac_install", "mac_spawn_relaunch", "mac_target",
                                                "mac_app_of", "mac_rollback")}
        M.migrate_download = lambda d, a, progress=None, fetch=None: {"path": os.path.join(d, a), "tag": "v1", "sha": "x"}
        M._mig_set(state="idle", error="")

    def tearDown(self):
        for k, v in self.keep.items():
            setattr(M, k, v)

    def test_windows_spawn_before_exit(self):
        M.win_migrate = lambda info, work, **k: self.events.append("spawn")
        M.migrate_run(exit_fn=lambda: self.events.append("exit"), plat="win32", sleep=lambda s: None)
        self.assertEqual(self.events, ["spawn", "exit"])

    def test_windows_failure_no_exit(self):
        def boom(*a, **k):
            raise M.MigrateError("нет")
        M.win_migrate = boom
        M.migrate_run(exit_fn=lambda: self.events.append("exit"), plat="win32", sleep=lambda s: None)
        self.assertEqual(self.events, [])
        st = M.migrate_status()
        self.assertEqual((st["state"], st["error"]), ("error", "нет"))

    def test_mac_order_and_rollback_when_relaunch_fails(self):
        M.mac_target = lambda cur: "/Applications/TAnalytic.app"
        M.mac_app_of = lambda: None
        M.mac_install = lambda info, tgt, work: (self.events.append("install") or {"app": tgt, "old": "/Applications/.old"})
        M.mac_rollback = lambda res: self.events.append("rollback")

        def bad(res):
            self.events.append("spawn")
            raise OSError("no sh")
        M.mac_spawn_relaunch = bad
        M.migrate_run(exit_fn=lambda: self.events.append("exit"), plat="darwin", sleep=lambda s: None)
        self.assertEqual(self.events, ["install", "spawn", "rollback"])
        M.mac_spawn_relaunch = lambda res: self.events.append("spawn")
        self.events.clear()
        M.mac_rollback = self.keep["mac_rollback"]
        M.migrate_run(exit_fn=lambda: self.events.append("exit"), plat="darwin", sleep=lambda s: None)
        self.assertEqual(self.events, ["install", "spawn", "exit"])

    def test_api_refuses_non_old_shell(self):
        with self.assertRaises(M.ApiError):
            M.api_migrate_start({}, {})          # тесты идут из исходников


class Mac(unittest.TestCase):
    def test_target_in_place(self):
        self.assertEqual(M.mac_target("/Users/u/Apps/TAnalytic.app", access=lambda p, m: True), "/Users/u/Apps/TAnalytic.app")

    def test_translocated_goes_to_applications(self):
        cur = "/private/var/folders/xx/AppTranslocation/ABC/d/TAnalytic.app"
        self.assertEqual(M.mac_target(cur, access=lambda p, m: True, exists=lambda p: False), "/Applications/TAnalytic.app")

    def test_readonly_volume_goes_to_applications(self):
        self.assertEqual(M.mac_target("/Volumes/TAnalytic/TAnalytic.app", access=lambda p, m: False if p.startswith("/Volumes") else True,
                                      exists=lambda p: True), "/Applications/TAnalytic.app")

    def test_unwritable_applications_goes_home(self):
        self.assertEqual(M.mac_target("/Volumes/x/TAnalytic.app", access=lambda p, m: False, home="/Users/u"),
                         "/Users/u/Applications/TAnalytic.app")

    def test_app_of(self):
        self.assertEqual(M.mac_app_of("/Applications/TAnalytic.app/Contents/MacOS/TAnalytic"), "/Applications/TAnalytic.app")
        self.assertIsNone(M.mac_app_of("/usr/bin/python3"))

    def _dmg(self, d):
        p = os.path.join(d, "x.dmg")
        open(p, "wb").write(b"dmg")
        return {"path": p, "sha": sha(b"dmg")}

    def _runner(self, d, fail_on=None):
        calls = []

        class R:
            def __init__(s, c, e=b""):
                s.returncode, s.stderr = c, e

        def run(cmd, **kw):
            calls.append(cmd[0])
            if cmd[0] == "hdiutil" and cmd[1] == "attach":
                os.makedirs(os.path.join(cmd[cmd.index("-mountpoint") + 1], "TAnalytic.app"))
            if cmd[0] == "ditto":
                os.makedirs(cmd[2])
            if cmd[0] == fail_on:
                return R(1, b"boom")
            return R(0)
        return run, calls

    def test_install_replaces_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            tgt = os.path.join(d, "Apps", "TAnalytic.app")
            os.makedirs(tgt)
            open(os.path.join(tgt, "old.txt"), "w").write("1")
            run, calls = self._runner(d)
            res = M.mac_install(self._dmg(d), tgt, d, run=run, pid=5)
            self.assertEqual(calls, ["hdiutil", "ditto", "xattr", "codesign", "hdiutil"])
            self.assertTrue(os.path.isfile(os.path.join(res["old"], "old.txt")))       # прежняя копия сохранена как .old
            self.assertFalse(os.path.exists(os.path.join(tgt, "old.txt")))
            M.mac_rollback(res)
            self.assertTrue(os.path.isfile(os.path.join(tgt, "old.txt")))

    def test_install_failure_keeps_old(self):
        with tempfile.TemporaryDirectory() as d:
            tgt = os.path.join(d, "TAnalytic.app")
            os.makedirs(tgt)
            open(os.path.join(tgt, "old.txt"), "w").write("1")
            run, calls = self._runner(d, fail_on="codesign")
            with self.assertRaises(M.MigrateError):
                M.mac_install(self._dmg(d), tgt, d, run=run, pid=5)
            self.assertTrue(os.path.isfile(os.path.join(tgt, "old.txt")))
            self.assertEqual(calls[-1], "hdiutil")                                     # образ отмонтирован
            self.assertEqual([n for n in os.listdir(d) if n.startswith(".")], [])      # временная копия убрана

    def test_install_checks_sum(self):
        with tempfile.TemporaryDirectory() as d:
            info = self._dmg(d)
            info["sha"] = "0" * 64
            with self.assertRaises(M.MigrateError):
                M.mac_install(info, os.path.join(d, "TAnalytic.app"), d, run=lambda *a, **k: None)

    def test_relaunch_argv(self):
        got = {}
        M.mac_spawn_relaunch({"app": "/Applications/TAnalytic.app", "old": ""}, popen=lambda a, **k: got.update(a=a, k=k), pid=9)
        self.assertEqual(got["a"][:2], ["/bin/sh", "-c"])
        self.assertEqual(got["a"][4:], ["9", "/Applications/TAnalytic.app", ""])
        self.assertTrue(got["k"]["start_new_session"])
        self.assertIn("open -n", got["a"][2])


if __name__ == "__main__":
    unittest.main()
