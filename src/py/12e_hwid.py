# ═══════════════ HWID: хэш идентификатора ПК для привязки пробного периода ═══════════════
# Наружу уходит только sha256(машинный id + соль приложения); сырой id нигде не хранится и не отправляется.
# Токен Т-Инвестиций в этом обмене не участвует. Если машинный id получить не удалось, берётся случайный id,
# сохранённый в папке данных (файл hwid.id).

HWID_SALT = "tanalytic-hwid-v1"


def _hwid_machine_raw():
    """Сырой машинный id или пустая строка. Только для вычисления хэша."""
    try:
        if sys.platform.startswith("win"):
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0]).strip()
        if sys.platform == "darwin":
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True, timeout=5).stdout
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out.decode("utf-8", "replace"))
            return m.group(1).strip() if m else ""
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    v = f.read().strip()
            except OSError:
                continue
            if v:
                return v
    except Exception:  # noqa: BLE001
        pass
    return ""


def _hwid_fallback_raw():
    p = os.path.join(APP_DIR, "hwid.id")
    try:
        with open(p, "r", encoding="utf-8") as f:
            v = f.read().strip()
        if len(v) >= 16:
            return v
    except OSError:
        pass
    v = uuid.uuid4().hex + uuid.uuid4().hex
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(v)
    except OSError:
        pass
    return v


def hwid_hash(raw):
    return hashlib.sha256((str(raw) + "|" + HWID_SALT).encode("utf-8")).hexdigest()


_hwid_cache = {"v": ""}


def hwid_get():
    """sha256-хэш (64 hex-знака) идентификатора этого ПК."""
    if not _hwid_cache["v"]:
        _hwid_cache["v"] = hwid_hash(_hwid_machine_raw() or _hwid_fallback_raw())
    return _hwid_cache["v"]


def hwid_headers():
    try:
        return {"X-Hwid": hwid_get()}
    except Exception:  # noqa: BLE001
        return {}
