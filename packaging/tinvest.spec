# -*- mode: python ; coding: utf-8 -*-
# Сборка лаунчера:  pyinstaller --noconfirm --distpath OUT/dist --workpath OUT/build packaging/tinvest.spec
#   macOS   -> «T-Invest Analytics.app» (onedir, без консоли)
#   Windows -> TInvestAnalytics.exe (onefile, без консоли)
# Иконки (необязательно): packaging/make_icon.py <папка> и переменная TINVEST_ICON_DIR.
import os, platform, sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gen_hidden_imports import hidden_imports

APP_SRC = os.environ.get("TINVEST_APP_SRC") or os.path.join(ROOT, "tinvest_analytics.py")
ICON_DIR = os.path.abspath(os.environ.get("TINVEST_ICON_DIR") or HERE)   # PyInstaller ищет относительные пути от папки spec

hidden = hidden_imports(APP_SRC) + ["certifi"] + collect_submodules("encodings")
datas = collect_data_files("certifi")           # корневые сертификаты: у Python с python.org их нет

# Собственное окно программы: pywebview (macOS — WKWebView через pyobjc, Windows — Edge WebView2 через pythonnet)
hidden += collect_submodules("webview")
datas += collect_data_files("webview")           # js, а на Windows и lib/*.dll
if sys.platform == "darwin":
    for m in ("objc", "Foundation", "AppKit", "WebKit", "Quartz", "Security", "UniformTypeIdentifiers"):
        hidden += collect_submodules(m)
elif sys.platform == "win32":
    for m in ("clr_loader", "pythonnet"):
        hidden += collect_submodules(m)
        datas += collect_data_files(m)
    hidden += ["clr"]


def icon(ext):
    p = os.path.join(ICON_DIR, "icon." + ext)
    return p if os.path.exists(p) else None


a = Analysis([os.path.join(ROOT, "tinvest.py")], pathex=[], datas=datas, hiddenimports=hidden, noarchive=False)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # Архитектура — по раннеру (arm64 на Apple Silicon, x86_64 на Intel); переопределяется TINVEST_TARGET_ARCH.
    arch = os.environ.get("TINVEST_TARGET_ARCH") or ("arm64" if platform.machine() == "arm64" else "x86_64")
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="T-Invest Analytics", console=False, icon=icon("icns"),
              target_arch=arch)
    coll = COLLECT(exe, a.binaries, a.datas, name="T-Invest Analytics")
    app = BUNDLE(coll, name="T-Invest Analytics.app", icon=icon("icns"), bundle_identifier="io.github.kos5o4ka.tinvest",
                 info_plist={"CFBundleName": "T-Invest Analytics", "CFBundleDisplayName": "T-Invest Analytics",
                             "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0",
                             "LSApplicationCategoryType": "public.app-category.finance"})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="TInvestAnalytics", console=False, icon=icon("ico"),
              upx=False)
