# ═══════════════ Журнал медленных экранов: сколько секунд и сетевых запросов ушло на запрос интерфейса ═══════════════
# Пишется в <папка данных>/perf.log только для запросов дольше PERF_MIN_SEC. Тела запросов и параметры с данными не пишутся:
# только путь, имя экрана (page=…/kind=… из адреса) и счётчики. Счётчики общие на процесс, поэтому при параллельных
# запросах цифры приблизительные (об этом сказано в шапке файла).

PERF_MIN_SEC = 0.5
PERF_MAX_BYTES = 1_000_000
_perf_lock = threading.Lock()
_perf_cnt = {"tinvest": 0}
PERF_HEAD = ("# TAnalytic: медленные запросы интерфейса (дольше %.1f с). Колонки: время, путь, секунды, запросы к серверу данных "
             "(из кэша / мимо кэша / устаревшие), напрямую к источникам, к API Т-Инвестиций. Счётчики общие на программу: "
             "если в это время шли другие загрузки, цифры приблизительные.\n" % PERF_MIN_SEC)


def perf_count(k):
    with _perf_lock:
        _perf_cnt[k] = _perf_cnt.get(k, 0) + 1


def perf_snapshot():
    with _ds_lock:
        s = {k: _ds_state.get(k, 0) for k in ("hit", "miss", "stale", "direct")}
    with _perf_lock:
        s["tinvest"] = _perf_cnt.get("tinvest", 0)
    return s


def perf_label(path, query=""):
    """Путь + безопасные уточнения (page, kind, tab), чтобы различать экраны с общим адресом. Остальные параметры отбрасываются."""
    try:
        q = parse_qs(query or "")
    except Exception:  # noqa: BLE001
        q = {}
    extra = ["%s=%s" % (k, re.sub(r"[^\w.-]", "", (q.get(k) or [""])[0])[:24]) for k in ("page", "kind", "tab", "mode") if q.get(k)]
    return path + (("?" + "&".join(extra)) if extra else "")


def perf_log(label, sec, before, after=None):
    if sec < PERF_MIN_SEC:
        return
    after = after or perf_snapshot()
    d = {k: after.get(k, 0) - before.get(k, 0) for k in after}
    line = "%s\t%s\t%.2f\tсервер %d/%d/%d\tнапрямую %d\tТ-Инвестиции %d\n" % (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), label, sec, d["hit"], d["miss"], d["stale"], d["direct"], d["tinvest"])
    path = os.path.join(APP_DIR, "perf.log")
    try:
        with _perf_lock:
            if os.path.exists(path) and os.path.getsize(path) > PERF_MAX_BYTES:
                os.replace(path, path + ".1")
            new = not os.path.exists(path)
            with open(path, "a", encoding="utf-8") as f:
                if new:
                    f.write(PERF_HEAD)
                f.write(line)
    except OSError:
        pass
