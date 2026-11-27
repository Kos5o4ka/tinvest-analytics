# -*- mode: python ; coding: utf-8 -*-
# Сборка лаунчера:  pyinstaller --noconfirm --distpath OUT/dist --workpath OUT/build packaging/tinvest.spec
#   macOS   -> «TAnalytic.app» (onedir, без консоли)
#   Windows -> папка TAnalytic\ с TAnalytic.exe (onedir, без консоли); в установщик её упаковывает packaging/TAnalytic.iss
# Иконки (необязательно): packaging/make_icon.py <папка> и переменная TINVEST_ICON_DIR.
import os, platform, sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gen_hidden_imports import hidden_imports

APP_SRC = os.environ.get("TINVEST_APP_SRC") or os.path.join(ROOT, "tinvest_analytics.py")
ICON_DIR = os.path.abspath(os.environ.get("TINVEST_ICON_DIR") or HERE)   # PyInstaller ищет относительные пути от папки spec

import re
_m = re.search(r'^APP_VERSION = "(\d+)\.(\d+)', open(APP_SRC, encoding="utf8").read(), re.M)
VER = (int(_m.group(1)), int(_m.group(2)), 0, 0) if _m else (0, 0, 0, 0)
VER_STR = "%d.%d" % VER[:2]                    # «0.21» — как в программе и в теге релиза

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
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TAnalytic", console=False, icon=icon("icns"),
              target_arch=arch)
    coll = COLLECT(exe, a.binaries, a.datas, name="TAnalytic")
    app = BUNDLE(coll, name="TAnalytic.app", icon=icon("icns"), bundle_identifier="io.github.kos5o4ka.tinvest",
                 info_plist={"CFBundleName": "TAnalytic", "CFBundleDisplayName": "TAnalytic",
                             "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0",
                             "LSApplicationCategoryType": "public.app-category.finance",
                             "CFBundleShortVersionString": VER_STR, "CFBundleVersion": VER_STR})
else:
    # Сведения о файле (Свойства → Подробно): exe без них эвристики антивирусов оценивают хуже.
    from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
                                                     StringStruct, VarFileInfo, VarStruct)
    ver, vs = VER, VER_STR
    version = VSVersionInfo(
        ffi=FixedFileInfo(filevers=ver, prodvers=ver, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1,
                          subtype=0x0, date=(0, 0)),
        kids=[StringFileInfo([StringTable("041904B0", [
                  StringStruct("CompanyName", "TAnalytic"),
                  StringStruct("FileDescription", "TAnalytic — аналитика инвестиционного портфеля"),
                  StringStruct("FileVersion", vs),
                  StringStruct("InternalName", "TAnalytic"),
                  StringStruct("LegalCopyright", "© Kos5o4ka, github.com/Kos5o4ka/tinvest-analytics"),
                  StringStruct("OriginalFilename", "TAnalytic.exe"),
                  StringStruct("ProductName", "TAnalytic"),
                  StringStruct("ProductVersion", vs)])]),
              VarFileInfo([VarStruct("Translation", [0x0419, 1200])])])
    # onedir: ничего не распаковывается во %TEMP% при каждом запуске (быстрый старт, меньше ложных срабатываний антивирусов)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TAnalytic", console=False, icon=icon("ico"),
              upx=False, version=version)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="TAnalytic")
