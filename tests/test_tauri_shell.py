"""Тесты оболочки Tauri v2, фронтенд-интеграции и lock/shutdown-хуков лаунчера tinvest.py."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAURI_DIR = os.path.join(ROOT, "src-tauri")


def load_launcher():
    spec = importlib.util.spec_from_file_location("tinvest_launcher_tauri_test", os.path.join(ROOT, "tinvest.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = load_launcher()


class TauriConfigAndFiles(unittest.TestCase):
    def test_tauri_conf_json(self):
        path = os.path.join(TAURI_DIR, "tauri.conf.json")
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding="utf-8") as f:
            conf = json.load(f)
        self.assertEqual(conf["productName"], "TAnalytic")
        self.assertEqual(conf["version"], "0.31.0")
        self.assertEqual(conf["identifier"], "ru.tanalytic.app")
        win = conf["app"]["windows"][0]
        self.assertEqual(win["label"], "main")
        self.assertEqual((win["width"], win["height"]), (1280, 860))
        self.assertEqual((win["minWidth"], win["minHeight"]), (960, 640))
        self.assertTrue(win["center"])
        self.assertFalse(win["decorations"])
        self.assertTrue(win["shadow"])
        icons = conf["bundle"]["icon"]
        self.assertGreaterEqual(len(icons), 5)
        for rel in icons:
            ip = os.path.join(TAURI_DIR, rel)
            self.assertTrue(os.path.isfile(ip), f"missing icon: {rel}")
            self.assertGreater(os.path.getsize(ip), 0)

    def test_cargo_toml(self):
        path = os.path.join(TAURI_DIR, "Cargo.toml")
        raw = open(path, encoding="utf-8").read()
        try:
            import tomllib
            data = tomllib.loads(raw)
        except ModuleNotFoundError:
            data = None
        if data is not None:
            self.assertEqual(data["package"]["name"], "tanalytic")
            self.assertEqual(data["package"]["version"], "0.31.0")
            self.assertEqual(data["lib"]["name"], "tanalytic_lib")
            deps = data["dependencies"]
            for dep in (
                "tauri",
                "tauri-plugin-single-instance",
                "tauri-plugin-dialog",
                "tauri-plugin-autostart",
                "serde",
                "serde_json",
            ):
                self.assertIn(dep, deps)
            self.assertIn("tray-icon", deps["tauri"]["features"])
        else:
            for needle in (
                'name = "tanalytic"',
                'tauri-plugin-single-instance = "2"',
                'tauri-plugin-dialog = "2"',
                'tauri-plugin-autostart = "2"',
                '"tray-icon"',
            ):
                self.assertIn(needle, raw)

    def test_capabilities_default_json(self):
        path = os.path.join(TAURI_DIR, "capabilities", "default.json")
        with open(path, encoding="utf-8") as f:
            cap = json.load(f)
        self.assertEqual(cap["identifier"], "default")
        self.assertIn("main", cap["windows"])
        urls = cap["remote"]["urls"]
        self.assertIn("http://127.0.0.1:*/*", urls)
        self.assertIn("http://localhost:*/*", urls)
        perms = set(cap["permissions"])
        for req in (
            "core:default",
            "core:window:allow-minimize",
            "core:window:allow-toggle-maximize",
            "core:window:allow-close",
            "core:window:allow-start-dragging",
            "dialog:default",
            "autostart:default",
        ):
            self.assertIn(req, perms)

    def test_rust_sources_and_commands(self):
        build_rs = open(os.path.join(TAURI_DIR, "build.rs"), encoding="utf-8").read()
        main_rs = open(os.path.join(TAURI_DIR, "src", "main.rs"), encoding="utf-8").read()
        lib_rs = open(os.path.join(TAURI_DIR, "src", "lib.rs"), encoding="utf-8").read()

        self.assertIn("tauri_build::build()", build_rs)
        self.assertIn("tanalytic_lib::run()", main_rs)
        self.assertIn('windows_subsystem = "windows"', main_rs)

        for cmd in (
            "tauri_win_minimize",
            "tauri_win_toggle_max",
            "tauri_win_close",
            "tauri_pick_file",
            "tauri_autostart_get",
            "tauri_autostart_set",
            "tauri_bio_verify",
        ):
            self.assertRegex(lib_rs, r"#\[tauri::command\][\s\S]{0,120}\b" + cmd + r"\b")
            self.assertIn(cmd, lib_rs.split("generate_handler![", 1)[1])

        for needle in (
            'TcpListener::bind("127.0.0.1:0")',
            "/api/ping",
            "/api/app/shutdown",
            "tauri_plugin_single_instance",
            "Открыть TAnalytic",
            "Выход",
            "RunEvent::ExitRequested",
            "TitleBarStyle::Overlay",
            "hidden_title(true)",
            "--no-window",
            "TAnalytic-backend",
        ):
            self.assertIn(needle, lib_rs)

    def test_workflows_and_docs(self):
        yml_path = os.path.join(ROOT, ".github", "workflows", "tauri.yml")
        self.assertTrue(os.path.isfile(yml_path))
        yml = open(yml_path, encoding="utf-8").read()
        for runner in ("macos-latest", "macos-15-intel", "windows-latest"):
            self.assertIn(runner, yml)
        self.assertIn("TAnalytic-backend", yml)
        self.assertIn("tauri-apps/tauri-action@v0", yml)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "packaging", "tauri", "README.md")))


class FrontendTauriIntegration(unittest.TestCase):
    def test_js_and_css_present_and_scoped(self):
        js_path = os.path.join(ROOT, "src", "web", "js", "69_tauri.js")
        css_path = os.path.join(ROOT, "src", "web", "css", "60_tauri.css")
        js = open(js_path, encoding="utf-8").read()
        css = open(css_path, encoding="utf-8").read()

        self.assertIn("window.__TAURI_INTERNALS__", js)
        self.assertIn("data-tauri-drag-region", js)
        self.assertIn("tauri-bar", js)
        self.assertIn("tauri_pick_file", js)
        self.assertIn("tauri_win_minimize", js)
        self.assertIn("tauri_win_toggle_max", js)
        self.assertIn("tauri_win_close", js)

        self.assertIn("html.is-tauri .tauri-bar", css)
        self.assertIn("height:34px", css)
        self.assertIn("@media print", css)

        jsc = shutil.which("jsc") or "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"
        if os.path.isfile(jsc):
            res = subprocess.run([jsc, js_path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr or res.stdout)


class LauncherTauriHooks(unittest.TestCase):
    def test_main_api_window_aliases(self):
        class FakeWin:
            def __init__(self):
                self.calls = []
                self._ta_max = False

            def minimize(self):
                self.calls.append("min")

            def maximize(self):
                self._ta_max = True
                self.calls.append("max")

            def restore(self):
                self._ta_max = False
                self.calls.append("restore")

            def destroy(self):
                self.calls.append("close")

        api = L.MainApi()
        api._win = FakeWin()
        api.win_minimize()
        api.win_toggle_max()
        api.win_toggle_max()
        api.win_close()
        self.assertEqual(api._win.calls, ["min", "max", "restore", "close"])

    def test_check_lock_gate_default_and_biometric_flows(self):
        # По умолчанию (lock_enabled=False) биометрия не запрашивается
        called = []
        r0 = L.check_lock_gate(
            "http://127.0.0.1:9999/",
            cfg={},
            get_status=lambda _u: {"enabled": False, "unlocked": True, "_ok": True},
            verify_fn=lambda: called.append("bio") or True,
        )
        self.assertEqual(r0["unlocked"], True)
        self.assertEqual(called, [])

        # Включено и заблокировано, биометрия прошла -> авторазблокировка
        unlocked_urls = []
        r1 = L.check_lock_gate(
            "http://127.0.0.1:9999/",
            cfg={"lock_enabled": True},
            get_status=lambda _u: {"enabled": True, "unlocked": False, "biometric": True, "_ok": True},
            verify_fn=lambda: True,
            unlock_fn=lambda u: unlocked_urls.append(u) or True,
        )
        self.assertEqual(r1, {"locked": True, "unlocked": True, "method": "biometric"})
        self.assertEqual(unlocked_urls, ["http://127.0.0.1:9999/"])

        # Биометрия отклонена -> остаёмся на веб-экране блокировки
        unlocked_urls.clear()
        r2 = L.check_lock_gate(
            "http://127.0.0.1:9999/",
            cfg={"lock_enabled": True},
            get_status=lambda _u: {"enabled": True, "unlocked": False, "biometric": True, "_ok": True},
            verify_fn=lambda: False,
            unlock_fn=lambda u: unlocked_urls.append(u) or True,
        )
        self.assertEqual(r2, {"locked": True, "unlocked": False, "method": "web"})
        self.assertEqual(unlocked_urls, [])

        # Уже разблокировано на сервере -> биометрия не запускается
        r3 = L.check_lock_gate(
            "http://127.0.0.1:9999/",
            cfg={"lock_enabled": True},
            get_status=lambda _u: {"enabled": True, "unlocked": True, "_ok": True},
            verify_fn=lambda: self.fail("verify_fn must not run when already unlocked"),
        )
        self.assertFalse(r3["locked"])
        self.assertTrue(r3["unlocked"])

    def test_shutdown_posts_endpoint_and_runs_hook(self):
        hits = []

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append((self.path, self.headers.get("Content-Type")))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        hook_called = []
        old_hook = getattr(sys, "tanalytic_shutdown", None)
        sys.tanalytic_shutdown = lambda: hook_called.append(True)
        try:
            L.run_shutdown_hook(wait=1.0, url=url)
            self.assertEqual(hits, [("/api/app/shutdown", "application/json")])
            self.assertEqual(hook_called, [True])
        finally:
            srv.shutdown()
            srv.server_close()
            if old_hook is None:
                del sys.tanalytic_shutdown
            else:
                sys.tanalytic_shutdown = old_hook


if __name__ == "__main__":
    unittest.main()
