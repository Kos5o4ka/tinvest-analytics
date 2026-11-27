
# ── переезд со старой оболочки (pywebview/tk, 0.15–0.31) на оболочку Tauri ──
# Старые лаунчеры при каждом запуске сами скачивают свежий tinvest_analytics.py из последнего релиза (сверка SHA256SUMS)
# и выполняют его у себя в процессе, поэтому этот код попадает к каждому старому пользователю.
# Предлагаем перейти: программа сама скачивает установщик Tauri с GitHub, проверяет SHA256 по SHA256SUMS того же релиза,
# ставит его и перезапускается уже в новой оболочке. Данные пользователя (TINVEST_HOME, ~/.tinvest_analytics) не трогаются.
# Автозапуска нет: после переезда программа запускается один раз.
MIGRATE_REPO = "Kos5o4ka/tinvest-analytics"
MIGRATE_HOSTS = ("api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
MIGRATE_SUMS = "SHA256SUMS"
MIGRATE_LIMIT = 150_000_000
MIGRATE_WIN_ASSET = "TAnalytic-Setup-win.exe"
MIGRATE_MAC_APP = "TAnalytic.app"


class MigrateError(Exception):
    pass


def migrate_old_shell(env=None, frozen=None, plat=None):
    """Программа запущена внутри старой оболочки: не Tauri и (собранный лаунчер или TINVEST_SHELL_REV задан),
    ревизия оболочки старше текущей. Запуск из исходников (python3 tinvest_analytics.py) — не старая оболочка."""
    env = os.environ if env is None else env
    plat = sys.platform if plat is None else plat
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_tauri_shell(env) or plat not in ("win32", "darwin"):
        return False
    rev = shell_rev(env)
    return bool((frozen or rev > 0) and rev < SHELL_REV_LATEST)


def migrate_asset(plat=None, machine=None):
    plat = sys.platform if plat is None else plat
    if plat == "win32":
        return MIGRATE_WIN_ASSET
    if plat == "darwin":
        m = (platform.machine() if machine is None else machine).lower()
        return "TAnalytic-mac-arm64.dmg" if m in ("arm64", "aarch64") else "TAnalytic-mac-x64.dmg"
    raise MigrateError("Переезд поддерживается только на Windows и macOS.")


def migrate_check_url(url):
    """Только HTTPS и только домены GitHub — и для исходного адреса, и для каждого редиректа."""
    u = urlparse(str(url))
    if u.scheme != "https" or u.hostname not in MIGRATE_HOSTS:
        raise MigrateError("Недопустимый адрес загрузки (разрешён только GitHub по HTTPS).")
    return url


class _MigrateRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        migrate_check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _migrate_opener():
    try:
        ctx = make_ssl_context(load_config().get("ca_file") or "", True)
    except Exception:  # noqa: BLE001
        ctx = make_ssl_context()
    return urllib.request.build_opener(_MigrateRedirect, urllib.request.HTTPSHandler(context=ctx))


def migrate_fetch(url, sink=None, limit=MIGRATE_LIMIT, progress=None, opener=None):
    """Скачивает url. sink — открытый для записи двоичный файл (иначе результат — bytes). Возвращает (bytes|None, sha256)."""
    migrate_check_url(url)
    opener = opener or _migrate_opener()
    req = urllib.request.Request(url, headers={"User-Agent": "tanalytic-migrate"})
    h, buf, n, last = hashlib.sha256(), bytearray(), 0, 0.0
    with opener.open(req, timeout=30) as r:
        total = int(r.headers.get("Content-Length") or 0)
        if total > limit:
            raise MigrateError("Файл слишком большой.")
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            n += len(chunk)
            if n > limit:
                raise MigrateError("Файл слишком большой.")
            h.update(chunk)
            if sink is not None:
                sink.write(chunk)
            else:
                buf += chunk
            now = time.time()
            if progress and now - last >= 0.2:
                last = now
                progress(n, total)
    if progress:
        progress(n, total or n)
    return (None if sink is not None else bytes(buf)), h.hexdigest()


def migrate_parse_sums(text, name):
    for line in str(text).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise MigrateError("В релизе нет контрольной суммы для %s." % name)


def migrate_pick(rel, name):
    """(адрес файла, адрес SHA256SUMS, тег) из описания релиза; оба адреса — только GitHub."""
    urls = {a.get("name"): a.get("browser_download_url") for a in (rel.get("assets") or []) if isinstance(a, dict)}
    if not urls.get(name) or not urls.get(MIGRATE_SUMS):
        raise MigrateError("В последнем релизе ещё нет установщика новой оболочки (%s)." % name)
    return migrate_check_url(urls[name]), migrate_check_url(urls[MIGRATE_SUMS]), str(rel.get("tag_name") or "")


def migrate_download(dest_dir, asset, progress=None, fetch=None):
    """Скачивает файл оболочки последнего релиза в dest_dir и сверяет SHA256 с SHA256SUMS того же релиза.
    Возвращает {"path", "tag", "sha"}; при несовпадении суммы файл удаляется."""
    fetch = fetch or migrate_fetch
    body, _ = fetch("https://api.github.com/repos/%s/releases/latest" % MIGRATE_REPO, limit=5_000_000)
    rel = json.loads(body.decode("utf-8"))
    url, sums_url, tag = migrate_pick(rel, asset)
    sums, _ = fetch(sums_url, limit=1_000_000)
    want = migrate_parse_sums(sums.decode("utf-8", "replace"), asset)
    path = os.path.join(dest_dir, asset)
    tmp = path + ".part"
    try:
        with open(tmp, "wb") as f:
            _, got = fetch(url, sink=f, progress=progress)
        if got != want:
            raise MigrateError("Не совпала контрольная сумма SHA256: файл отклонён.")
        os.replace(tmp, path)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return {"path": path, "tag": tag, "sha": want}


def _migrate_sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Windows ──
_CMD_BAD = set('"%^&|<>!`\r\n\0')


def _cmd_path(p):
    """Путь, безопасный для подстановки в .cmd в двойных кавычках: абсолютный и без метасимволов cmd."""
    p = str(p)
    if not re.match(r"^[A-Za-z]:\\", p) or any(c in _CMD_BAD for c in p):
        raise MigrateError("Путь содержит недопустимые символы: переезд невозможен.")
    return p


def win_old_exe(exe, env=None):
    """Старый одиночный TAnalytic*.exe (onefile из «Загрузок»), который нужно удалить после переезда, иначе None.
    Установка Inno (Program Files, AppData\\Local\\Programs, рядом unins000.exe) — её удаляет хук установщика NSIS."""
    env = os.environ if env is None else env
    exe = str(exe or "")
    norm = exe.replace("/", "\\")
    base = norm.rsplit("\\", 1)[-1]
    if not (base.lower().startswith("tanalytic") and base.lower().endswith(".exe")):
        return None
    low = norm.lower()
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        pf = (env.get(key) or "").replace("/", "\\").lower().rstrip("\\")
        if pf and low.startswith(pf + "\\"):
            return None
    local = (env.get("LOCALAPPDATA") or "").replace("/", "\\").lower().rstrip("\\")
    if "\\appdata\\local\\programs\\" in low or (local and (low.startswith(local + "\\programs\\") or low.startswith(local + "\\tanalytic\\"))):
        return None
    if os.path.exists(os.path.join(os.path.dirname(exe), "unins000.exe")):
        return None
    return exe


def win_build_cmd(pid, installer, workdir, old_exe=None):
    """Текст .cmd: ждёт выхода старого процесса, тихо ставит NSIS (/S, без прав администратора), запускает новую
    программу, удаляет старый onefile-exe и себя вместе с рабочей папкой. Все пути проверены и стоят в кавычках."""
    pid = int(pid)
    inst, work = _cmd_path(installer), _cmd_path(workdir)
    old = _cmd_path(old_exe) if old_exe else ""
    q = lambda s: '"%s"' % s  # noqa: E731
    sm = "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\TAnalytic\\TAnalytic.lnk"
    L = ["@echo off", "chcp 65001 >nul", "setlocal", "set n=0", ":wait",
         'tasklist /FI "PID eq %d" /FO CSV /NH 2>nul | find """%d""" >nul' % (pid, pid),
         "if errorlevel 1 goto gone", "set /a n+=1", "if %n% GEQ 90 goto gone", "ping -n 2 127.0.0.1 >nul", "goto wait", ":gone",
         "ping -n 2 127.0.0.1 >nul",
         'start "" /wait %s /S' % q(inst),
         "if errorlevel 1 goto failed",
         'set "NEW="',
         'if exist "%LOCALAPPDATA%\\TAnalytic\\TAnalytic.exe" set "NEW=%LOCALAPPDATA%\\TAnalytic\\TAnalytic.exe"',
         'if not defined NEW if exist "%LOCALAPPDATA%\\Programs\\TAnalytic\\TAnalytic.exe" set "NEW=%LOCALAPPDATA%\\Programs\\TAnalytic\\TAnalytic.exe"',
         'if not defined NEW if exist "%s" set "NEW=%s"' % (sm, sm),
         'if defined NEW start "" "%NEW%"']
    if old:
        L += ["set k=0", ":del", "del /f /q %s >nul 2>nul" % q(old), "if not exist %s goto cleanup" % q(old),
              "set /a k+=1", "if %k% GEQ 30 goto cleanup", "ping -n 2 127.0.0.1 >nul", "goto del"]
    L += [":cleanup", "(goto) 2>nul & rd /s /q %s" % q(work), ":failed"]
    if old:
        L += ['if exist %s start "" %s' % (q(old), q(old))]          # установка не удалась: возвращаем пользователю прежнюю программу
    L += ["(goto) 2>nul & rd /s /q %s" % q(work), ""]
    return "\r\n".join(L)


def win_spawn_cmd(cmd_file, popen=None):
    popen = popen or subprocess.Popen
    flags = 0x08000000 | 0x00000200                    # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP: переживает выход программы, окна нет
    return popen(["cmd.exe", "/d", "/c", _cmd_path(cmd_file)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags)


def win_migrate(info, workdir, pid=None, exe=None, env=None, popen=None):
    if _migrate_sha_file(info["path"]) != info["sha"]:
        raise MigrateError("Файл установщика изменился после проверки: переезд отменён.")
    pid = os.getpid() if pid is None else pid
    text = win_build_cmd(pid, info["path"], workdir, win_old_exe(exe or sys.executable, env))
    cmd_file = os.path.join(workdir, "migrate.cmd")
    with open(cmd_file, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return win_spawn_cmd(cmd_file, popen)


# ── macOS ──
def mac_app_of(executable=None):
    parts = os.path.abspath(executable or sys.executable).split(os.sep)
    for i in range(len(parts) - 1, 0, -1):
        if parts[i].endswith(".app") and parts[i + 1:i + 3] == ["Contents", "MacOS"]:
            return os.sep.join(parts[:i + 1]) or os.sep
    return None


def mac_in_place_ok(app, access=os.access):
    if not app or not app.endswith(".app") or "/AppTranslocation/" in app or app.startswith("/private/var/folders/") \
            or app.startswith("/Volumes/"):
        return False
    return bool(access(app, os.W_OK) and access(os.path.dirname(app), os.W_OK))


def mac_target(current=None, access=os.access, exists=os.path.exists, home=None):
    """Куда ставить новое приложение: на место текущего (если можно), иначе /Applications, иначе ~/Applications."""
    if mac_in_place_ok(current, access):
        return current
    apps = "/Applications"
    tgt = os.path.join(apps, MIGRATE_MAC_APP)
    if access(apps, os.W_OK) and (not exists(tgt) or access(tgt, os.W_OK)):
        return tgt
    return os.path.join(home or os.path.expanduser("~"), "Applications", MIGRATE_MAC_APP)


def _mac_run(run, cmd, what, timeout=300):
    try:
        r = run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        raise MigrateError("%s: %s" % (what, e))
    if r.returncode != 0:
        tail = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        raise MigrateError("%s (код %s) %s" % (what, r.returncode, tail[0]))
    return r


def mac_install(info, target, workdir, run=None, pid=None, exists=os.path.exists):
    """Ставит приложение из .dmg в target: копия рядом (ditto), снятие карантина, проверка подписи, затем
    прежнее (если есть) -> «.old», новое -> на место; при ошибке прежнее возвращается. Возвращает {"app","old"}."""
    run = run or subprocess.run
    if _migrate_sha_file(info["path"]) != info["sha"]:
        raise MigrateError("Файл образа изменился после проверки: переезд отменён.")
    pid = os.getpid() if pid is None else pid
    parent = os.path.dirname(target)
    os.makedirs(parent, exist_ok=True)
    new = os.path.join(parent, ".%s.new-%s" % (MIGRATE_MAC_APP, pid))
    old = os.path.join(parent, ".%s.old-%s" % (MIGRATE_MAC_APP, pid))
    mnt = os.path.join(workdir, "mnt")
    os.makedirs(mnt, mode=0o700, exist_ok=True)
    mounted, had_old = False, exists(target)
    try:
        _mac_run(run, ["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mnt, info["path"]],
                 "Не удалось открыть образ диска")
        mounted = True
        src = os.path.join(mnt, MIGRATE_MAC_APP)
        if not os.path.isdir(src):
            raise MigrateError("В образе нет «%s»." % MIGRATE_MAC_APP)
        _mac_run(run, ["ditto", src, new], "Не удалось скопировать приложение")
        _mac_run(run, ["xattr", "-dr", "com.apple.quarantine", new], "Не удалось снять карантинную метку", 60)
        _mac_run(run, ["codesign", "--verify", "--deep", "--strict", new], "Подпись новой копии не прошла проверку", 120)
        if had_old:
            os.rename(target, old)
        try:
            os.rename(new, target)
        except OSError:
            if had_old:
                os.rename(old, target)
            raise
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(new, ignore_errors=True)
        if isinstance(e, MigrateError):
            raise
        raise MigrateError("Не удалось установить приложение: %s" % e)
    finally:
        if mounted:
            try:
                _mac_run(run, ["hdiutil", "detach", mnt], "detach", 60)
            except MigrateError:
                try:
                    run(["hdiutil", "detach", "-force", mnt], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                except Exception:  # noqa: BLE001
                    pass
    return {"app": target, "old": old if had_old else ""}


def mac_rollback(res):
    shutil.rmtree(res["app"], ignore_errors=True)
    if res.get("old"):
        os.rename(res["old"], res["app"])


MIGRATE_MAC_RELAUNCH = ('i=0; while kill -0 "$1" 2>/dev/null && [ $i -lt 150 ]; do sleep 0.2; i=$((i+1)); done; '
                        'open -n "$2"; [ -n "$3" ] && rm -rf "$3"')


def mac_spawn_relaunch(res, popen=None, pid=None):
    popen = popen or subprocess.Popen
    return popen(["/bin/sh", "-c", MIGRATE_MAC_RELAUNCH, "sh", str(os.getpid() if pid is None else pid), res["app"], res.get("old") or ""],
                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)


# ── задача и API ──
_mig = {"state": "idle", "done": 0, "total": 0, "error": "", "tag": "", "where": ""}
_mig_lock = threading.Lock()


def _mig_set(**kw):
    with _mig_lock:
        _mig.update(kw)


def migrate_status():
    with _mig_lock:
        d = dict(_mig)
    d["supported"] = migrate_old_shell()
    d["url"] = SHELL_RELEASES
    return d


def migrate_exit():
    """Аккуратно завершает программу вместе со старым лаунчером (мы внутри его процесса)."""
    try:
        app_shutdown()
    except Exception:  # noqa: BLE001
        pass
    os._exit(0)


def migrate_run(exit_fn=None, plat=None, tmp=None, sleep=time.sleep):
    """Рабочий поток: скачать, проверить, поставить, перезапуститься. Любая ошибка — в статус, программа остаётся как была."""
    plat = sys.platform if plat is None else plat
    exit_fn = exit_fn or migrate_exit
    work = None
    try:
        asset = migrate_asset(plat)
        work = tempfile.mkdtemp(prefix="tanalytic_migrate_", dir=tmp)
        _mig_set(state="downloading", done=0, total=0, error="")
        info = migrate_download(work, asset, progress=lambda d, t: _mig_set(done=d, total=t))
        _mig_set(state="installing", tag=info["tag"])
        if plat == "win32":
            win_migrate(info, work)
            work = None                                  # папку дальше убирает .cmd
        else:
            tgt = mac_target(mac_app_of())
            res = mac_install(info, tgt, work)
            try:
                mac_spawn_relaunch(res)
            except Exception:  # noqa: BLE001
                mac_rollback(res)
                raise
            _mig_set(where=tgt)
        _mig_set(state="restarting")
        sleep(1.5)                                       # баннер успевает показать «перезапуск»
        exit_fn()
    except Exception as e:  # noqa: BLE001
        msg = str(e) if isinstance(e, MigrateError) else "Не удалось связаться с GitHub или установить: %s" % (getattr(e, "reason", None) or e)
        _mig_set(state="error", error=msg)
    finally:
        if work:
            shutil.rmtree(work, ignore_errors=True)


def api_migrate_start(cfg, body):
    if not migrate_old_shell():
        raise ApiError("Переезд нужен только старой оболочке приложения.", 400)
    with _mig_lock:
        if _mig["state"] in ("downloading", "installing", "restarting"):
            return dict(_mig, supported=True, url=SHELL_RELEASES)
        _mig.update(state="downloading", done=0, total=0, error="", tag="", where="")
    threading.Thread(target=migrate_run, daemon=True).start()
    return migrate_status()


API_GET["/api/shell/migrate"] = lambda cfg, acc, q, force: migrate_status()
API_POST["/api/shell/migrate"] = api_migrate_start
