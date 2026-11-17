# ── недельная инфляция (Росстат): еженедельные заметки «Об оценке индекса потребительских цен с … по …» ──
# Источник: https://rosstat.gov.ru/central-news (постраничный список «Новости статистики», ?page=N, новые сверху).
# Заметка — PDF (с 2026 г.) или HTML; в тексте: «индекс потребительских цен, по оценке Росстата, составил 100,12%».
# Прошлые недели не меняются: разобранные заметки хранятся в kv навсегда, свежие страницы перечитываются раз в 12 ч,
# история докачивается в фоне (≤1 запрос/с). Мёртвые ссылки старых заметок запоминаются и не перезапрашиваются.

import html
import urllib.parse

ROSSTAT_NEWS = "https://rosstat.gov.ru/central-news"
_WI_KEY = "weekly_cpi_notes_v1"
_WI_TTL = 12 * 3600
_WI_FLOOR = date(2017, 1, 1)
_WI_MAX_PAGES = 100
_WI_DEAD_STOP = 8            # подряд недоступных старых заметок — дальше архив не углубляем
_WI_PACE = 1.0
_wi_lock = threading.Lock()
_wi = {"running": False, "err": None, "last": 0}
_RU_MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7, "августа": 8,
              "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
_MON_RE = "|".join(_RU_MONTHS)


# --- минимальное извлечение текста из PDF (Flate + ToUnicode, без сторонних библиотек) ---

def _pdf_stream(body):
    m = re.search(rb"stream\r?\n(.*)endstream", body, re.S)
    if not m:
        return b""
    d = m.group(1)
    if b"FlateDecode" in body[:m.start()]:
        try:
            d = zlib.decompressobj().decompress(d)
        except Exception:  # noqa: BLE001
            return b""
    return d


def _pdf_cmap(data):
    mp, t = {}, data.decode("latin1")
    for blk in re.findall(r"beginbfchar(.*?)endbfchar", t, re.S):
        for a, c in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            mp[int(a, 16)] = bytes.fromhex(c).decode("utf-16-be", "replace")
    for blk in re.findall(r"beginbfrange(.*?)endbfrange", t, re.S):
        for a, c, d in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            a, c, d = int(a, 16), int(c, 16), int(d, 16)
            for i in range(a, c + 1):
                mp[i] = chr(d + i - a)
    return mp


def pdf_first_page_text(b):
    objs = {int(m.group(1)): m.group(2) for m in re.finditer(rb"(\d+)\s+0\s+obj\b(.*?)endobj", b, re.S)}
    page = next((body for body in objs.values() if re.search(rb"/Type\s*/Page\b", body) and b"/Contents" in body), None)
    if page is None:
        return ""
    fonts = {}
    fm = re.search(rb"/Font\s*<<(.*?)>>", page, re.S)
    for name, num in re.findall(rb"/(\w+)\s+(\d+)\s+0\s+R", fm.group(1) if fm else b""):
        tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", objs.get(int(num), b""))
        fonts[name.decode()] = _pdf_cmap(_pdf_stream(objs[int(tu.group(1))])) if tu and int(tu.group(1)) in objs else None
    cm = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+0\s+R)", page)
    out = []
    for r in [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", cm.group(1))] if cm else []:
        c, cur = _pdf_stream(objs.get(r, b"")), None
        for tok in re.finditer(rb"/(\w+)\s+[\d.]+\s+Tf|\[(.*?)\]\s*TJ|<([0-9A-Fa-f]*)>\s*Tj|\((.*?)(?<!\\)\)\s*Tj|(ET)", c, re.S):
            if tok.group(1):
                cur = fonts.get(tok.group(1).decode())
                continue
            if tok.group(5):
                out.append(" ")
                continue
            if tok.group(2) is not None:
                parts = re.findall(rb"<([0-9A-Fa-f]*)>|\(((?:\\.|[^\\)])*)\)", tok.group(2))
            elif tok.group(3) is not None:
                parts = [(tok.group(3), b"")]
            else:
                parts = [(b"", tok.group(4))]
            for h, lit in parts:
                if h and cur is not None:
                    hb = bytes.fromhex(h.decode())
                    out.append("".join(cur.get(int.from_bytes(hb[i:i + 2], "big"), "") for i in range(0, len(hb), 2)))
                elif h:
                    out.append(bytes.fromhex(h.decode()).decode("cp1251", "replace"))
                else:
                    out.append(re.sub(rb"\\(.)", rb"\1", lit).decode("cp1252", "replace"))
    return "".join(out)


# --- разбор заметки и списка ---

def _wi_num(a, b):
    return float(a + "." + b)


def weekly_note_parse(data, title=""):
    """Заметка (PDF или HTML, bytes) -> {date, pct, ytd} либо None. pct — недельный прирост в %, ytd — с начала года."""
    if data[:4] == b"%PDF":
        text = pdf_first_page_text(data)
    else:
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", data.decode("utf-8", "replace"), flags=re.S | re.I)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    t = re.sub(r"\s+", " ", text.replace("\xa0", " "))
    # индекс потребительских цен (сноска-цифра), по оценке Росстата, составил 100,12%  /  цены выросли на 0,12%
    m = re.search(r"индекс\s+потребительских\s+цен[^.]{0,40}?составил\s*(\d{2,3})\s*[,.]\s*(\d{1,2})\s*%", t, re.I)
    pct = round(_wi_num(m.group(1), m.group(2)) - 100.0, 2) if m else None
    if pct is None:
        m = re.search(r"(?:цены|потребительские цены)\s+(выросли|снизились|увеличились|сократились)\s+на\s*(\d+)\s*[,.]\s*(\d{1,2})\s*%", t, re.I)
        if m:
            pct = _wi_num(m.group(2), m.group(3)) * (1 if m.group(1).lower() in ("выросли", "увеличились") else -1)
    if pct is None:
        return None
    my = re.search(r"с\s+начала\s+года\s*[–—-]?\s*(\d{2,3})\s*[,.]\s*(\d{1,2})\s*%", t, re.I)
    ytd = round(_wi_num(my.group(1), my.group(2)) - 100.0, 2) if my else None
    d = weekly_end_date(t) or weekly_end_date(title)
    return {"date": d.isoformat(), "pct": pct, "ytd": ytd} if d else None


def weekly_end_date(text):
    """Дата конца недели: «… по 9 ноября 2026 г.» (год может быть разорван пробелом: «202 6»)."""
    m = re.search(r"\bпо\s+(\d{1,2})\s+(%s)\s+(20\d)\s?(\d)\b" % _MON_RE, text, re.I)
    if not m:
        return None
    try:
        return date(int(m.group(3) + m.group(4)), _RU_MONTHS[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def weekly_listing_parse(page_html):
    """Страница списка новостей -> [(url, заголовок)] только заметок «Об оценке индекса потребительских цен …», новые сверху."""
    out = []
    for h, t in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page_html, re.S):
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")).strip()
        if re.match(r"Об\s+оценке\s+индекса\s+потребительских\s+цен", t, re.I):
            u = urllib.parse.urljoin(ROSSTAT_NEWS, h)
            if all(u != x[0] for x in out):
                out.append((u, t))
    return out


def weekly_avg_by_week(rows, y0=2017, y1=2021):
    """Среднее по номеру недели за y0..y1: ([(неделя, среднее)], [годы, по которым есть данные])."""
    acc, ys = {}, set()
    for r in rows:
        if y0 <= r["year"] <= y1:
            acc.setdefault(r["week"], []).append(r["pct"])
            ys.add(r["year"])
    return [(w, round(sum(v) / len(v), 3)) for w, v in sorted(acc.items())], sorted(ys)


def _wi_state():
    st = store().get(_WI_KEY) or {}
    st.setdefault("weeks", {})
    st.setdefault("dead", [])
    st.setdefault("t", 0)
    st.setdefault("deep", False)       # история докачана до конца архива
    return st


def weekly_collect(fetch=None, pace=_WI_PACE, deep=False, max_pages=_WI_MAX_PAGES, save=None):
    """Обходит страницы списка (новые -> старые) и разбирает ещё неизвестные заметки.
    deep=False: только свежие страницы — останов, когда на странице нет новых заметок.
    deep=True: пока не упрёмся в _WI_FLOOR, конец списка или _WI_DEAD_STOP недоступных заметок подряд."""
    fetch = fetch or (lambda u: http_bytes(u, timeout=60))
    st = _wi_state()
    known = {v["url"] for v in st["weeks"].values()}
    dead = set(st["dead"])
    dead_run = 0
    for p in range(1, max_pages + 1):
        try:
            page = fetch(ROSSTAT_NEWS + ("?page=%d" % p if p > 1 else "")).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            break
        items = weekly_listing_parse(page)
        fresh = 0
        for u, title in items:
            if u in known or u in dead:
                dead_run = dead_run + 1 if u in dead else 0
                continue
            time.sleep(pace)
            try:
                rec = weekly_note_parse(fetch(u), title)
            except Exception:  # noqa: BLE001
                rec = None
            fresh += 1
            if rec is None:
                dead.add(u)
                dead_run += 1
                continue
            dead_run = 0
            rec["url"] = u
            st["weeks"][rec["date"]] = rec
            known.add(u)
        st["dead"] = sorted(dead)
        if save:
            save(st)
        if not items and p > 1:
            st["deep"] = True
            break
        if not deep and not fresh:
            break
        if deep and (dead_run >= _WI_DEAD_STOP or (st["weeks"] and min(st["weeks"]) < _WI_FLOOR.isoformat())):
            st["deep"] = True
            break
        time.sleep(pace)
    if deep and not st["deep"] and p >= max_pages:
        st["deep"] = True
    st["t"] = time.time()
    return st


def _wi_run():
    try:
        st = weekly_collect(deep=not _wi_state()["deep"], save=lambda s: store().put(_WI_KEY, s))
        store().put(_WI_KEY, st)
        _wi["err"] = None
    except Exception as e:  # noqa: BLE001
        _wi["err"] = str(e)[:200]
    finally:
        with _wi_lock:
            _wi["running"] = False


def weekly_payload(st, loading=False, err=None):
    rows = []
    for d, v in sorted(st["weeks"].items()):
        dt = date.fromisoformat(d)
        rows.append({"year": dt.year, "date": d, "week": min(52, dt.isocalendar()[1]), "pct": v["pct"], "ytd": v.get("ytd")})
    years = {}
    for r in rows:
        years.setdefault(str(r["year"]), []).append(r)
    avg, ys = weekly_avg_by_week(rows)
    label = ("%d–%d" % (ys[0], ys[-1]) if ys[0] != ys[-1] else str(ys[0])) if ys else "2017–2021"
    return {"years": years, "avg": avg, "avg_label": label, "avg_years": ys, "empty": not rows, "loading": loading,
            "history_from": rows[0]["date"] if rows else None, "updated": st.get("t") or None, "error": err,
            "sources": [ROSSTAT_NEWS]}


def weekly_inflation(force=False):
    """Отдаёт то, что уже разобрано; недостающее (свежие недели раз в 12 ч, история при первом запуске) докачивается в фоне."""
    st = _wi_state()
    with _wi_lock:
        stale = force or (time.time() - st["t"] > _WI_TTL or not st["deep"]) and time.time() - _wi["last"] > 600
        if stale and not _wi["running"]:
            _wi["running"] = True
            _wi["last"] = time.time()
            threading.Thread(target=_wi_run, daemon=True).start()
        running = _wi["running"]
    return weekly_payload(st, running, _wi["err"])


API_GET["/api/inflation_weekly"] = lambda cfg, acc, q, force: weekly_inflation(force)
