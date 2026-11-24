
# ── оболочка (собранное приложение .app/.exe): устарела ли она ──
# Автообновление меняет только tinvest_analytics.py; окно, иконка и экран обновления живут в самой оболочке.
# Оболочка сообщает свою ревизию через TINVEST_SHELL_REV (с ревизии 2); старые оболочки её не передают.
# Ревизия 3 — заставка на pywebview с бесшовным переходом в окно программы.
SHELL_REV_LATEST = 3
SHELL_RELEASES = "https://github.com/Kos5o4ka/tinvest-analytics/releases/latest"


def shell_status(env=None, frozen=None):
    env = os.environ if env is None else env
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    try:
        rev = int(env.get("TINVEST_SHELL_REV") or 0)
    except ValueError:
        rev = 0
    asset = {"darwin": "TAnalytic-mac-arm64.zip" if platform.machine() == "arm64" else "TAnalytic-mac-x64.zip",
             "win32": "TAnalytic-win.exe"}.get(sys.platform)
    return {"frozen": frozen, "rev": rev, "latest": SHELL_REV_LATEST, "outdated": bool(frozen and rev < SHELL_REV_LATEST),
            "url": SHELL_RELEASES, "asset": asset}


API_GET["/api/shell"] = lambda cfg, acc, q, force: shell_status()
