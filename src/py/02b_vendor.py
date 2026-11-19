# ═══════════════ дополнительные библиотеки: загрузка по требованию ═══════════════
# Ядро программы работает только на стандартной библиотеке. Тяжёлым функциям (разбор PDF и т.п.) нужны чистые Python-пакеты
# из VENDOR_LOCK: колесо скачивается при первом обращении в APP_DIR/lib, проверяется по SHA256 из замка и импортируется прямо
# из .whl (zipimport, без распаковки). Хэш не совпал — файл не используется. Источник: PyPI, запасной — ассет релиза на GitHub.
#
#   pypdf = vendor_import("pypdf")      # ApiError с понятным текстом, если библиотека недоступна
#   vendor_available("pypdf")           # уже скачана и проверена (без сети)

import importlib
import urllib.parse

VENDOR_DIR = os.path.join(APP_DIR, "lib")
VENDOR_GH = "https://github.com/Kos5o4ka/tinvest-analytics/releases/download/v%s/%s"
_vendor_mx = threading.Lock()
_vendor_ok = {}                     # имя файла -> путь, проверенный в этом процессе


def _vendor_entry(name):
    for e in VENDOR_LOCK:
        if e["name"] == name:
            return e
    raise ApiError("Библиотека %s не входит в состав программы." % name, 500)


def _vendor_supported(e, vi=None):
    return tuple((vi or sys.version_info)[:2]) >= tuple(e["python"])


def _vendor_needed(e, vi=None):
    return not e.get("only_below") or tuple((vi or sys.version_info)[:2]) < tuple(e["only_below"])


def _vendor_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _vendor_urls(e):
    return [e["url"], VENDOR_GH % (APP_VERSION, e["file"])]


def _vendor_get(url, limit, timeout):
    """Байты по адресу (не больше limit). Отдельная функция — чтобы подменять в тестах."""
    req = urllib.request.Request(url, headers={"User-Agent": "TAnalytic/%s" % APP_VERSION})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl()) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("файл больше ожидаемого")
    return data


def _vendor_fetch(e, timeout):
    """Скачать колесо и проверить SHA256. Любой источник годится: подменённый файл не пройдёт проверку."""
    errs = []
    for url in _vendor_urls(e):
        try:
            data = _vendor_get(url, int(e["size"]) + 1024, timeout)
        except Exception as x:  # noqa: BLE001
            errs.append("%s: %s" % (urllib.parse.urlparse(url).netloc, x))
            continue
        if hashlib.sha256(data).hexdigest() != e["sha256"]:
            errs.append("%s: контрольная сумма не совпала" % urllib.parse.urlparse(url).netloc)
            continue
        os.makedirs(VENDOR_DIR, exist_ok=True)
        path = os.path.join(VENDOR_DIR, e["file"])
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        _vendor_cleanup()
        return path
    raise ApiError("Не удалось загрузить библиотеку %s %s (%s). Проверьте интернет и попробуйте ещё раз."
                   % (e["name"], e["version"], "; ".join(errs) or "нет источников"), 503)


def _vendor_cleanup():
    """Удалить из APP_DIR/lib колёса, которых нет в замке (прежние версии)."""
    keep = {e["file"] for e in VENDOR_LOCK}
    try:
        for fn in os.listdir(VENDOR_DIR):
            if fn.endswith(".whl") and fn not in keep:
                os.remove(os.path.join(VENDOR_DIR, fn))
    except OSError:
        pass


def _vendor_file(e, download, timeout):
    """Путь к проверенному колесу или None (download=False и файла нет)."""
    if e["file"] in _vendor_ok:
        return _vendor_ok[e["file"]]
    path = os.path.join(VENDOR_DIR, e["file"])
    if os.path.isfile(path):
        try:
            if _vendor_sha(path) == e["sha256"]:
                _vendor_ok[e["file"]] = path
                return path
        except OSError:
            pass
        try:
            os.remove(path)               # испорченный или подменённый файл
        except OSError:
            pass
    if not download:
        return None
    path = _vendor_fetch(e, timeout)
    _vendor_ok[e["file"]] = path
    return path


def _vendor_chain(name, seen=None):
    """Библиотека и её зависимости из замка, которые нужны на этой версии Python (зависимости — первыми)."""
    seen = seen if seen is not None else []
    e = _vendor_entry(name)
    for r in e.get("requires") or []:
        if _vendor_needed(_vendor_entry(r)) and r not in [x["name"] for x in seen]:
            _vendor_chain(r, seen)
    if e not in seen:
        seen.append(e)
    return seen


def vendor_available(name):
    """Библиотека уже скачана, проверена и подходит к этой версии Python (сеть не трогается)."""
    try:
        chain = _vendor_chain(name)
        if not all(_vendor_supported(e) for e in chain):
            return False
        with _vendor_mx:
            return all(_vendor_file(e, False, 0) for e in chain)
    except Exception:  # noqa: BLE001
        return False


def vendor_import(name, download=True, timeout=60):
    """Импорт дополнительной библиотеки: при необходимости скачать, проверить SHA256, подключить .whl. -> модуль."""
    chain = _vendor_chain(name)
    for e in chain:
        if not _vendor_supported(e):
            raise ApiError("Для этой функции нужен Python %d.%d или новее (сейчас %d.%d). Установите приложение TAnalytic "
                           "или обновите Python." % (e["python"][0], e["python"][1], sys.version_info[0], sys.version_info[1]), 501)
    with _vendor_mx:
        for e in chain:
            path = _vendor_file(e, download, timeout)
            if not path:
                raise ApiError("Библиотека %s ещё не загружена." % e["name"], 503)
            if path not in sys.path:
                sys.path.insert(0, path)    # наша проверенная версия важнее установленной в системе
        importlib.invalidate_caches()
    return importlib.import_module(name)


def vendor_status():
    out = []
    for e in VENDOR_LOCK:
        out.append({"name": e["name"], "version": e["version"], "size": e["size"], "needed": _vendor_needed(e),
                    "supported": _vendor_supported(e), "installed": vendor_available(e["name"]) if _vendor_needed(e) else None})
    return out


API_GET["/api/vendor"] = lambda cfg, acc, q, force: {"ok": True, "dir": VENDOR_DIR, "items": vendor_status()}
