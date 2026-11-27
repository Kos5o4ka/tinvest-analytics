# ═══════════════════════════════ блокировка экрана (PIN / биометрия) ═══════════════════════════════
# По умолчанию выключена (lock_enabled=False). При включённой блокировке все /api/* (кроме /api/ping, /api/lock/status,
# /api/lock/unlock, /api/app/shutdown) возвращают HTTP 423 до разблокировки в текущей сессии сервера.

_lock_unlocked = [False]
_lock_state_lock = threading.Lock()
_bio_runner = None
_LOCK_PBKDF_ROUNDS = 120000

_BIO_SWIFT_SRC = (
    'import Foundation\n'
    'import LocalAuthentication\n'
    'let ctx = LAContext()\n'
    'var err: NSError?\n'
    'let reason = ProcessInfo.processInfo.environment["TA_BIO_REASON"] ?? "Unlock TAnalytic"\n'
    'guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &err) else {\n'
    '    fputs(err?.localizedDescription ?? "unavailable", stderr)\n'
    '    exit(2)\n'
    '}\n'
    'let sem = DispatchSemaphore(value: 0)\n'
    'var ok = false\n'
    'var msg = ""\n'
    'ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, error in\n'
    '    ok = success\n'
    '    if let e = error { msg = e.localizedDescription }\n'
    '    sem.signal()\n'
    '}\n'
    'sem.wait()\n'
    'if !ok { fputs(msg, stderr) }\n'
    'exit(ok ? 0 : 1)\n'
)

_BIO_WIN_PS = (
    "$ErrorActionPreference = 'Stop'\n"
    "[void][Windows.Security.Credentials.UI.UserConsentVerifier, Windows.Security.Credentials.UI, ContentType = WindowsRuntime]\n"
    "Add-Type -AssemblyName System.Runtime.WindowsRuntime\n"
    "$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { "
    "$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]\n"
    "function Await($WinRtTask, $ResultType) {\n"
    "    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)\n"
    "    $netTask = $asTask.Invoke($null, @($WinRtTask))\n"
    "    $netTask.Wait(-1) | Out-Null\n"
    "    $netTask.Result\n"
    "}\n"
    "$avail = Await ([Windows.Security.Credentials.UI.UserConsentVerifier]::CheckAvailabilityAsync()) "
    "([Windows.Security.Credentials.UI.UserConsentVerifierAvailability])\n"
    "if ($avail -ne 'Available') { Write-Error \"unavailable:$avail\"; exit 2 }\n"
    "$reason = $env:TA_BIO_REASON\n"
    "if (-not $reason) { $reason = 'Unlock TAnalytic' }\n"
    "$res = Await ([Windows.Security.Credentials.UI.UserConsentVerifier]::RequestVerificationAsync($reason)) "
    "([Windows.Security.Credentials.UI.UserConsentVerificationResult])\n"
    "if ($res -eq 'Verified') { exit 0 } else { Write-Error \"$res\"; exit 1 }\n"
)


def _lock_hash_pin(pin, salt_bytes):
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt_bytes, _LOCK_PBKDF_ROUNDS).hex()


def _lock_verify_pin(cfg, pin):
    h, s = str(cfg.get("lock_pin_hash") or ""), str(cfg.get("lock_pin_salt") or "")
    if not h or not s:
        return False
    try:
        salt_bytes = bytes.fromhex(s)
    except ValueError:
        return False
    cand = _lock_hash_pin(str(pin or ""), salt_bytes)
    return hmac.compare_digest(cand, h)


def _lock_marker_sync(cfg):
    """Маркер рядом с конфигом отражает «блокировка включена» (см. lock_marker_path). Ошибки записи не критичны."""
    if cfg.get("_lock_corrupt"):
        return
    try:
        mp = lock_marker_path()
        if _lock_configured(cfg):
            if not os.path.exists(mp):
                _private_write(mp, ("TAnalytic: PIN-блокировка включена. Удалите этот файл вместе с PIN-настройками, "
                                   "чтобы снять блокировку.\n").encode("utf-8"))
        elif os.path.exists(mp):
            os.remove(mp)
    except OSError:
        pass


def _lock_configured(cfg):
    """Блокировка действует только с заданным PIN: биометрия — удобство поверх PIN, а не единственный ключ
    (иначе без Touch ID / Windows Hello в программу не войти)."""
    return bool(cfg.get("lock_enabled")) and bool(cfg.get("lock_pin_hash"))


# защита от перебора PIN: после LOCK_FREE_TRIES неудач — растущая пауза (в памяти процесса)
LOCK_FREE_TRIES = 5
LOCK_MAX_WAIT = 300
_lock_fails = {"n": 0, "until": 0.0}


def _lock_throttle_check(now=None):
    now = time.time() if now is None else now
    left = _lock_fails["until"] - now
    if left > 0:
        raise ApiError("Слишком много неверных попыток. Подождите %d с." % int(left + 0.999), 429)


def _lock_fail(now=None):
    now = time.time() if now is None else now
    _lock_fails["n"] += 1
    extra = _lock_fails["n"] - LOCK_FREE_TRIES
    if extra >= 0:
        _lock_fails["until"] = now + min(LOCK_MAX_WAIT, 2 ** min(extra, 9) * 2)


def _lock_ok():
    _lock_fails["n"] = 0
    _lock_fails["until"] = 0.0


def lock_is_locked(cfg):
    if not _lock_configured(cfg):
        return False
    return not _lock_unlocked[0]


def bio_available():
    if os.environ.get("TINVEST_NO_BIO") == "1":
        return False
    sysname = platform.system()
    if sysname == "Darwin":
        return os.path.exists("/System/Library/Frameworks/LocalAuthentication.framework")
    if sysname == "Windows":
        return bool(shutil.which("powershell"))
    return False


def _bio_mac_cmd():
    """Возвращает команду запуска macOS LocalAuthentication (кэшированный бинарник в APP_DIR/cache или swift -e)."""
    h = hashlib.sha256(_BIO_SWIFT_SRC.encode("utf-8")).hexdigest()[:12]
    cache_dir = os.path.join(APP_DIR, "cache")
    bin_path = os.path.join(cache_dir, "bio_helper_" + h)
    if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
        return [bin_path]
    swiftc = shutil.which("swiftc")
    if swiftc:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            src_path = bin_path + ".swift"
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(_BIO_SWIFT_SRC)
            r = subprocess.run([swiftc, "-O", src_path, "-o", bin_path], timeout=30, capture_output=True, text=True)
            try:
                os.remove(src_path)
            except OSError:
                pass
            if r.returncode == 0 and os.path.isfile(bin_path):
                return [bin_path]
        except (OSError, subprocess.SubprocessError):
            pass
    return ["swift", "-e", _BIO_SWIFT_SRC]


def bio_verify(reason="Разблокировать TAnalytic"):
    """Нативная проверка биометрии / системного пароля -> (ok: bool, err: str)."""
    if _bio_runner is not None:
        return _bio_runner(reason)
    if not bio_available():
        return False, "Биометрия недоступна на этом устройстве"
    env = dict(os.environ, TA_BIO_REASON=str(reason or "Разблокировать TAnalytic"))
    sysname = platform.system()
    kw = {"env": env, "timeout": 30, "capture_output": True, "text": True}
    if sysname == "Darwin":
        cmd = _bio_mac_cmd()
    elif sysname == "Windows":
        cmd = ["powershell", "-NoProfile", "-Command", _BIO_WIN_PS]
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        return False, "Биометрия недоступна"
    try:
        proc = subprocess.run(cmd, **kw)
    except subprocess.TimeoutExpired:
        return False, "Время ожидания биометрии истекло"
    except OSError as e:
        return False, str(e)
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "Проверка отклонена").strip()
    return False, err[:240]


def lock_status_dict(cfg):
    return {
        "enabled": bool(cfg.get("lock_enabled")),
        "unlocked": not lock_is_locked(cfg),
        "has_pin": bool(cfg.get("lock_pin_hash")),
        "bio": bool(cfg.get("lock_bio", True)),
        "bio_available": bio_available(),
        "config_corrupt": bool(cfg.get("_lock_corrupt")),
        "reset_hint": _lock_reset_hint(cfg),
    }


def _lock_reset_hint(cfg):
    mp = lock_marker_path()
    if cfg.get("_lock_corrupt"):
        return ("Файл настроек %s повреждён, поэтому программа осталась заблокированной. Закройте программу и удалите файл "
                "%s: блокировка снимется, данные портфеля не пострадают (удалять базу и сам config.json не нужно: "
                "исправьте его или восстановите из резервной копии)." % (CONFIG_PATH, mp))
    return ("Если PIN забыт: закройте программу и удалите строки lock_enabled, lock_pin_hash и lock_pin_salt из файла %s, "
            "а также файл-маркер %s. Данные портфеля при этом не удаляются." % (CONFIG_PATH, mp))


def lock_status_get(cfg, acc, q, force):
    return lock_status_dict(cfg)


def lock_setup_post(cfg, body):
    """Настройка блокировки. Поля: enabled, pin (новый), clear_pin, bio, current_pin.
    Если PIN уже задан, любое изменение требует текущий PIN (иначе блокировку снимет любой, кто сел за открытую программу)."""
    with _lock_state_lock:
        if _lock_configured(cfg) and not _lock_unlocked[0]:
            raise ApiError("Программа заблокирована", 423)
        if cfg.get("lock_pin_hash"):
            _lock_throttle_check()
            if not _lock_verify_pin(cfg, body.get("current_pin")):
                _lock_fail()
                raise ApiError("Неверный текущий PIN.", 403)
            _lock_ok()
        enabled = bool(body["enabled"]) if "enabled" in body else bool(cfg.get("lock_enabled"))
        if "bio" in body:
            cfg["lock_bio"] = bool(body["bio"])
        if body.get("clear_pin"):
            cfg["lock_pin_hash"] = ""
            cfg["lock_pin_salt"] = ""
            enabled = False                                  # без PIN блокировка не действует
        elif body.get("pin"):
            pin = str(body["pin"]).strip()
            if not (4 <= len(pin) <= 12) or not pin.isdigit():
                raise ApiError("PIN — от 4 до 12 цифр.", 400)
            salt = os.urandom(16)
            cfg["lock_pin_salt"] = salt.hex()
            cfg["lock_pin_hash"] = _lock_hash_pin(pin, salt)
        if enabled and not cfg.get("lock_pin_hash"):
            raise ApiError("Сначала задайте PIN-код: он нужен, даже если включена биометрия.", 400)
        cfg["lock_enabled"] = enabled
        _lock_unlocked[0] = True                             # текущую сессию сразу после настройки не блокируем
        save_config(cfg)
        _lock_marker_sync(cfg)
        return dict(lock_status_dict(cfg), ok=True)


def lock_unlock_post(cfg, body):
    with _lock_state_lock:
        if not lock_is_locked(cfg):
            return {"ok": True, "unlocked": True}
        _lock_throttle_check()
        method = str(body.get("method") or ("bio" if body.get("bio") else "pin"))
        if method == "bio":
            if cfg.get("_lock_corrupt") or not cfg.get("lock_bio", True):
                raise ApiError("Биометрическая разблокировка отключена.", 403)
            ok, err = bio_verify(str(body.get("reason") or "Разблокировать TAnalytic"))
            if not ok:
                raise ApiError(err or "Биометрическая проверка не пройдена.", 403)
            _lock_unlocked[0] = True
            return {"ok": True, "unlocked": True}
        pin = str(body.get("pin") or "")
        if not _lock_verify_pin(cfg, pin):
            _lock_fail()
            raise ApiError("Неверный PIN.", 403)
        _lock_ok()
        _lock_unlocked[0] = True
        return {"ok": True, "unlocked": True}


def lock_bio_post(cfg, body):
    """Проверка биометрии из Настроек (только в разблокированной программе: сюда не пускает проверка 423)."""
    ok, err = bio_verify(str(body.get("reason") or "Проверка биометрии TAnalytic"))
    return {"ok": bool(ok), "error": err or ""}


def lock_now_post(cfg, body):
    with _lock_state_lock:
        if _lock_configured(cfg):
            _lock_unlocked[0] = False
        return {"ok": True, "locked": lock_is_locked(cfg)}


def _lock_on_startup():
    with _lock_state_lock:
        _lock_unlocked[0] = False
        _lock_marker_sync(load_config())                     # включённая раньше блокировка получает маркер (после обновления)


API_GET["/api/lock/status"] = lock_status_get
API_POST["/api/lock/setup"] = lock_setup_post
API_POST["/api/lock/unlock"] = lock_unlock_post
API_POST["/api/lock/bio"] = lock_bio_post
API_POST["/api/lock/now"] = lock_now_post
STARTUP_HOOKS.append(_lock_on_startup)
