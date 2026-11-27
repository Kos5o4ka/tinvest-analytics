
# ── оболочка (собранное приложение .app/.exe): устарела ли она ──
# Автообновление меняет только tinvest_analytics.py; окно, иконка и экран обновления живут в самой оболочке.
# Оболочка сообщает свою ревизию через TINVEST_SHELL_REV (с ревизии 2); старые оболочки её не передают.
# Ревизия 3 — заставка на pywebview с бесшовным переходом в окно программы.
# Ревизия 4 — установщик Windows (onedir), значок в трее, автозапуск и обновление оболочки из программы;
# на macOS то же обновление из образа .dmg (ревизию не поднимали: сборка macOS с образом уже умеет обновляться).
SHELL_REV_LATEST = 4
SHELL_RELEASES = "https://github.com/Kos5o4ka/tinvest-analytics/releases/latest"


DEFAULT_CONFIG.setdefault("tray_close", False)      # «При закрытии окна сворачивать в трей» (Windows); по умолчанию выключено
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "TAnalytic"                         # то же имя значения пишет установщик (packaging/TAnalytic.iss)


def shell_rev(env=None):
    env = os.environ if env is None else env
    try:
        return int(env.get("TINVEST_SHELL_REV") or 0)
    except ValueError:
        return 0


def tray_supported(env=None, frozen=None, plat=None):
    """Трей и автозапуск — только у собранной оболочки ревизии 4+ на Windows (на macOS пункты скрыты)."""
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    return bool(frozen and (sys.platform if plat is None else plat) == "win32" and shell_rev(env) >= 4)


def autostart_command(exe=None):
    return '"%s" --tray' % (exe or sys.executable)


def autostart_get(reg=None):
    """Включён ли запуск вместе с Windows: есть ли значение TAnalytic в HKCU\\...\\Run. reg — модуль winreg (подменяется в тестах)."""
    try:
        reg = reg or __import__("winreg")
        k = reg.OpenKey(reg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, reg.KEY_READ)
        try:
            reg.QueryValueEx(k, AUTOSTART_NAME)
            return True
        finally:
            reg.CloseKey(k)
    except Exception:  # noqa: BLE001 — нет ключа, нет winreg (macOS), нет прав
        return False


def autostart_set(on, reg=None, exe=None):
    """Включает или выключает запуск вместе с Windows (запись текущего пользователя, права администратора не нужны)."""
    reg = reg or __import__("winreg")
    if on:
        k = reg.CreateKeyEx(reg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, reg.KEY_SET_VALUE)
        try:
            reg.SetValueEx(k, AUTOSTART_NAME, 0, reg.REG_SZ, autostart_command(exe))
        finally:
            reg.CloseKey(k)
        return True
    try:
        k = reg.OpenKey(reg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, reg.KEY_SET_VALUE)
    except OSError:
        return False                                  # ключа нет — выключать нечего
    try:
        reg.DeleteValue(k, AUTOSTART_NAME)
    except OSError:
        pass                                          # значения уже нет
    finally:
        reg.CloseKey(k)
    return False


def tray_close_wanted():
    """Читает лаунчер при закрытии окна (sys.tanalytic_tray)."""
    try:
        return bool(load_config().get("tray_close"))
    except Exception:  # noqa: BLE001
        return False


def shell_status(env=None, frozen=None, cfg=None, reg=None):
    env = os.environ if env is None else env
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    rev = shell_rev(env)
    asset = {"darwin": "TAnalytic-mac-arm64.dmg" if platform.machine() == "arm64" else "TAnalytic-mac-x64.dmg",
             "win32": "TAnalytic-Setup-win.exe"}.get(sys.platform)
    tray = tray_supported(env, frozen)
    return {"frozen": frozen, "rev": rev, "latest": SHELL_REV_LATEST, "outdated": bool(frozen and rev < SHELL_REV_LATEST),
            "url": SHELL_RELEASES, "asset": asset,
            "tray": tray, "tray_close": bool(tray and (cfg or {}).get("tray_close")),
            "autostart": bool(tray and autostart_get(reg))}


def api_shell_tray(cfg, body):
    if not tray_supported():
        raise ApiError("Трей и автозапуск доступны только в установленной версии для Windows.", 400)
    if "tray_close" in body:
        cfg["tray_close"] = bool(body["tray_close"])
        save_config(cfg)
        hook = getattr(sys, "tanalytic_tray_sync", None)       # лаунчер показывает или убирает значок в трее
        if callable(hook):
            try:
                hook()
            except Exception:  # noqa: BLE001
                pass
    if "autostart" in body:
        try:
            autostart_set(bool(body["autostart"]))
        except Exception as e:  # noqa: BLE001
            raise ApiError("Не удалось изменить автозапуск: %s" % e, 500)
    return shell_status(cfg=cfg)


API_GET["/api/shell"] = lambda cfg, acc, q, force: shell_status(cfg=cfg)
API_POST["/api/shell/tray"] = api_shell_tray
sys.tanalytic_tray = tray_close_wanted               # лаунчер спрашивает при закрытии окна: свернуть в трей или выйти
