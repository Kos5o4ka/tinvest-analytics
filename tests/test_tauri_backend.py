"""Сервер как sidecar оболочки Tauri: слежение за родителем (--parent-pid) и поведение трея/баннера."""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402

M = _load.load()


class ParentWatch(unittest.TestCase):
    def test_posix_alive_and_dead(self):
        calls = []

        def kill(pid, sig):
            calls.append((pid, sig))

        alive = M.parent_alive_checker(4242, plat="linux", getppid=lambda: 1, kill=kill)
        self.assertTrue(alive())
        self.assertEqual(calls, [(4242, 0)])

        def gone(pid, sig):
            raise ProcessLookupError()

        self.assertFalse(M.parent_alive_checker(4242, plat="linux", getppid=lambda: 1, kill=gone)())

        def denied(pid, sig):
            raise PermissionError()

        self.assertTrue(M.parent_alive_checker(4242, plat="linux", getppid=lambda: 1, kill=denied)())

    def test_posix_reparented_means_dead(self):
        ppid = [4242]
        alive = M.parent_alive_checker(4242, plat="linux", getppid=lambda: ppid[0], kill=lambda p, s: None)
        self.assertTrue(alive())
        ppid[0] = 1                                   # родителя не стало: процесс усыновлён init
        self.assertFalse(alive())

    def test_onefile_loader_parent_is_not_compared(self):
        # прямой родитель — загрузчик PyInstaller (не оболочка): ориентируемся только на kill(pid, 0)
        alive = M.parent_alive_checker(4242, plat="linux", getppid=lambda: 777, kill=lambda p, s: None)
        self.assertTrue(alive())

    def test_watcher_calls_on_dead_once_parent_gone(self):
        state = {"n": 0}
        done = threading.Event()

        def alive(pid):
            state["n"] += 1
            return state["n"] < 3

        t = M.parent_watch_start(99, interval=0.01, alive=alive, on_dead=done.set)
        self.assertTrue(done.wait(3))
        t.join(3)
        self.assertEqual(state["n"], 3)

    def test_watcher_ignores_check_errors(self):
        n = {"i": 0}
        done = threading.Event()

        def alive(pid):
            n["i"] += 1
            if n["i"] == 1:
                raise OSError("нет доступа")
            return n["i"] < 3

        M.parent_watch_start(99, interval=0.01, alive=alive, on_dead=done.set)
        self.assertTrue(done.wait(3))
        self.assertEqual(n["i"], 3)

    def test_main_parses_parent_pid(self):
        import inspect
        src = inspect.getsource(M.main)
        self.assertIn("--parent-pid", src)
        self.assertIn("parent_watch_start", src)


class TauriShellStatus(unittest.TestCase):
    ENV = {"TINVEST_SHELL": "tauri", "TINVEST_SHELL_REV": "5"}

    def test_tray_off_and_not_outdated(self):
        self.assertFalse(M.tray_supported(env=self.ENV, frozen=True, plat="win32"))
        st = M.shell_status(env=self.ENV, frozen=True, cfg={"tray_close": True})
        self.assertTrue(st["tauri"])
        self.assertFalse(st["tray"])
        self.assertFalse(st["outdated"])
        self.assertNotIn("autostart", st)

    def test_tauri_without_rev_not_outdated(self):
        self.assertFalse(M.shell_status(env={"TINVEST_SHELL": "tauri"}, frozen=True)["outdated"])

    def test_tray_endpoint_refused_under_tauri(self):
        old = os.environ.get("TINVEST_SHELL")
        os.environ["TINVEST_SHELL"] = "tauri"
        try:
            with self.assertRaises(M.ApiError):
                M.api_shell_tray({}, {"tray_close": True})
        finally:
            if old is None:
                os.environ.pop("TINVEST_SHELL", None)
            else:
                os.environ["TINVEST_SHELL"] = old


if __name__ == "__main__":
    unittest.main()
