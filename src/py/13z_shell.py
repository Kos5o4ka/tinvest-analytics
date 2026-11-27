
# ── оболочка (собранное приложение .app/.exe): устарела ли она ──
# Автообновление меняет только tinvest_analytics.py; окно, иконка и экран обновления живут в самой оболочке.
# Оболочка сообщает свою ревизию через TINVEST_SHELL_REV (с ревизии 2); старые оболочки её не передают.
# Ревизия 3 — заставка на pywebview с бесшовным переходом в окно программы.
# Ревизия 4 — установщик Windows (onedir), значок в трее и обновление оболочки из программы;
# на macOS то же обновление из образа .dmg (ревизию не поднимали: сборка macOS с образом уже умеет обновляться).
# Ревизия 5 — оболочка Tauri (установщик NSIS на Windows и образ .dmg на macOS, автообновление через tauri-plugin-updater).
# Оболочки pywebview (ревизия 4 и ниже) получают баннер с предложением перейти на неё: скачать новый установщик.
SHELL_REV_LATEST = 5
SHELL_RELEASES = "https://github.com/Kos5o4ka/tinvest-analytics/releases/latest"


DEFAULT_CONFIG.setdefault("tray_close", False)      # «При закрытии окна сворачивать в трей» (Windows); по умолчанию выключено


def shell_rev(env=None):
    env = os.environ if env is None else env
    try:
        return int(env.get("TINVEST_SHELL_REV") or 0)
    except ValueError:
        return 0


def is_tauri_shell(env=None):
    """Сервер запущен как sidecar оболочки Tauri (она ставит TINVEST_SHELL=tauri)."""
    env = os.environ if env is None else env
    return (env.get("TINVEST_SHELL") or "").strip().lower() == "tauri"


def tray_supported(env=None, frozen=None, plat=None):
    """Трей — только у собранной оболочки pywebview ревизии 4+ на Windows (на macOS пункты скрыты).
    У оболочки Tauri настройки трея нет. Автозапуска в программе нет нигде."""
    if is_tauri_shell(env):
        return False
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    return bool(frozen and (sys.platform if plat is None else plat) == "win32" and shell_rev(env) >= 4)


def tray_close_wanted():
    """Читает лаунчер при закрытии окна (sys.tanalytic_tray)."""
    try:
        return bool(load_config().get("tray_close"))
    except Exception:  # noqa: BLE001
        return False


def shell_status(env=None, frozen=None, cfg=None):
    env = os.environ if env is None else env
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    rev = shell_rev(env)
    asset = {"darwin": "TAnalytic-mac-arm64.dmg" if platform.machine() == "arm64" else "TAnalytic-mac-x64.dmg",
             "win32": "TAnalytic-Setup-win.exe"}.get(sys.platform)
    tray = tray_supported(env, frozen)
    tauri = is_tauri_shell(env)
    return {"frozen": frozen, "rev": rev, "latest": SHELL_REV_LATEST, "tauri": tauri,
            "outdated": bool(frozen and not tauri and rev < SHELL_REV_LATEST),
            "url": SHELL_RELEASES, "asset": asset,
            "tray": tray, "tray_close": bool(tray and (cfg or {}).get("tray_close"))}


def api_shell_tray(cfg, body):
    if not tray_supported():
        raise ApiError("Трей доступен только в установленной версии для Windows.", 400)
    if "tray_close" in body:
        cfg["tray_close"] = bool(body["tray_close"])
        save_config(cfg)
        hook = getattr(sys, "tanalytic_tray_sync", None)       # лаунчер показывает или убирает значок в трее
        if callable(hook):
            try:
                hook()
            except Exception:  # noqa: BLE001
                pass
    return shell_status(cfg=cfg)


API_GET["/api/shell"] = lambda cfg, acc, q, force: shell_status(cfg=cfg)
API_POST["/api/shell/tray"] = api_shell_tray
sys.tanalytic_tray = tray_close_wanted               # лаунчер спрашивает при закрытии окна: свернуть в трей или выйти
