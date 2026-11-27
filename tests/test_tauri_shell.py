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
        self.assertEqual(conf["identifier"], "ru.tanalytic.desktop")
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
        perms = set(cap["permissions"])
        for req in (
            "core:default",
            "core:window:allow-minimize",
            "core:window:allow-toggle-maximize",
            "core:window:allow-close",
            "core:window:allow-start-dragging",
            "dialog:default",
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
            "--parent-pid",
            "TINVEST_SHELL",
            "on_navigation",
            "Повторить",
        ):
            self.assertIn(needle, lib_rs)
        self.assertNotIn("tauri_bio_verify", lib_rs)
        self.assertNotIn("--tray", lib_rs)
        self.assertNotIn("autostart", lib_rs.lower())
        # single-instance — первый плагин, sidecar стартует в setup, а не до Builder
        self.assertLess(lib_rs.index("tauri_plugin_single_instance::init"), lib_rs.index("tauri_plugin_dialog::init"))
        self.assertNotIn("spawn_sidecar(port).ok()", lib_rs)
        self.assertIn("start_backend(app.handle())", lib_rs.split(".setup(", 1)[1])
        with open(os.path.join(TAURI_DIR, "capabilities", "default.json"), encoding="utf-8") as f:
            caps = json.load(f)
        self.assertEqual(caps["remote"]["urls"], ["http://127.0.0.1:*/*"])

    def test_workflows_and_docs(self):
        yml_path = os.path.join(ROOT, ".github", "workflows", "release.yml")
        self.assertTrue(os.path.isfile(yml_path))
        yml = open(yml_path, encoding="utf-8").read()
        for runner in ("macos-latest", "macos-15-intel", "windows-latest"):
            self.assertIn(runner, yml)
        self.assertIn("TAnalytic-backend", yml)
        self.assertIn("tauri-apps/tauri-action@v0", yml)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "packaging", "tauri", "README.md")))


class TauriReleasePackaging(unittest.TestCase):
    def conf(self):
        with open(os.path.join(TAURI_DIR, "tauri.conf.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_installers_configured(self):
        b = self.conf()["bundle"]
        self.assertEqual(b["resources"], {"resources/backend/": "backend/"})
        self.assertNotIn("externalBin", b)
        nsis = b["windows"]["nsis"]
        self.assertEqual(nsis["languages"], ["Russian"])
        self.assertEqual(nsis["installMode"], "currentUser")
        self.assertEqual(b["windows"]["webviewInstallMode"]["type"], "downloadBootstrapper")
        for key in ("headerImage", "sidebarImage", "installerIcon", "installerHooks"):
            self.assertTrue(os.path.isfile(os.path.join(TAURI_DIR, nsis[key])), key)
        mac = b["macOS"]
        self.assertEqual(mac["minimumSystemVersion"], "11.0")
        self.assertTrue(os.path.isfile(os.path.join(TAURI_DIR, mac["entitlements"])))
        self.assertTrue(os.path.isfile(os.path.join(TAURI_DIR, mac["dmg"]["background"])))
        self.assertEqual((mac["dmg"]["windowSize"]["width"], mac["dmg"]["windowSize"]["height"]), (660, 400))
        self.assertTrue(b["createUpdaterArtifacts"])

    def test_installer_images_sizes(self):
        import struct
        def bmp(name):
            with open(os.path.join(TAURI_DIR, "installer", name), "rb") as f:
                head = f.read(30)
            self.assertEqual(head[:2], b"BM")
            w, h = struct.unpack("<ii", head[18:26])
            bpp = struct.unpack("<H", head[28:30])[0]
            return w, abs(h), bpp
        self.assertEqual(bmp("header.bmp"), (150, 57, 24))
        self.assertEqual(bmp("sidebar.bmp"), (164, 314, 24))

    def test_nsis_hook_migrates_inno(self):
        hook = open(os.path.join(TAURI_DIR, "installer", "hooks.nsh"), encoding="utf-8").read()
        iss = open(os.path.join(ROOT, "packaging", "TAnalytic.iss"), encoding="utf-8-sig").read()
        app_id = iss.split("AppId={{", 1)[1].split("}", 1)[0]
        self.assertIn("{%s}_is1" % app_id, hook)
        self.assertIn("/VERYSILENT", hook)
        self.assertIn("/SUPPRESSMSGBOXES", hook)
        self.assertIn("NSIS_HOOK_PREINSTALL", hook)
        # Inno в тихом режиме данные не удаляет
        self.assertIn("not UninstallSilent", iss)

    def test_updater_configured(self):
        conf = self.conf()
        up = conf["plugins"]["updater"]
        self.assertEqual(up["endpoints"], ["https://github.com/Kos5o4ka/tinvest-analytics/releases/latest/download/latest.json"])
        self.assertTrue(up["pubkey"])
        lib_rs = open(os.path.join(TAURI_DIR, "src", "lib.rs"), encoding="utf-8").read()
        for cmd in ("tauri_update_status", "tauri_update_check", "tauri_update_apply"):
            self.assertIn(cmd, lib_rs.split("generate_handler![", 1)[1])
        self.assertIn("tauri_plugin_updater", lib_rs)
        cargo = open(os.path.join(TAURI_DIR, "Cargo.toml"), encoding="utf-8").read()
        self.assertIn("tauri-plugin-updater", cargo)

    def test_release_workflow_publishes_tauri_assets(self):
        yml = open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8").read()
        for asset in ("TAnalytic-Setup-win.exe", "TAnalytic-mac-arm64.dmg", "TAnalytic-mac-x64.dmg", "latest.json"):
            self.assertIn(asset, yml)
        self.assertIn("--onedir", yml)
        self.assertNotIn("--onefile", yml)
        self.assertIn("PYINSTALLER_COMPILE_BOOTLOADER=1", yml)
        self.assertIn("mac_codesign.sh dir", yml)
        self.assertIn("gh release upload", yml)
        self.assertIn("SHA256SUMS", yml)
        self.assertNotIn("ISCC", yml)


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
        self.assertNotIn("dblclick", js)       # двойной клик по шапке обрабатывает сам Tauri (drag-region)
        self.assertNotIn("tauri_bio_verify", js)

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

    def test_launcher_has_no_lock_gate(self):
        # блокировку целиком показывает сервер (PIN обязателен); лаунчер не должен ни спрашивать биометрию, ни ждать
        for name in ("check_lock_gate", "post_lock_unlock", "fetch_lock_status", "bio_verify"):
            self.assertFalse(hasattr(L, name), name)

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
