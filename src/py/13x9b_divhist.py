# ═══════════════════ длинная история дивидендов: dohod.ru (с 2000-х) + слияние с данными T-Invest / сервера ═══════════════════
# T-Invest GetDividends отдаёт ~6 лет, у компаний история 20+ лет. Добираем более ранние годы со страницы
# https://www.dohod.ru/ik/analytics/dividend/<тикер> (публичная, без входа; robots.txt разрешает /ik/). Запрос — обычный GET без личных данных,
# через сервер данных (белый список хостов) или напрямую. Разбор устойчив к смене порядка колонок (колонки ищутся по заголовкам).
# Строки «прогноз» и «рекомендовано» (запись реестра ещё не утверждена) в историю не смешиваются — они лежат отдельно в upcoming.
# Описательная статистика по прошлым выплатам, не инвестиционная рекомендация.

DH_BASE = "https://www.dohod.ru/ik/analytics/dividend/%s"
DH_TTL = 7 * 86400                    # история прошлых лет неизменна: неделя
DH_ERR_TTL = 3600                     # сбой сети: повтор не чаще раза в час, пока отдаём прошлый успешный ответ
DH_NF_TTL = 3 * 86400                 # на dohod.ru нет страницы тикера (облигации, ETF, новые бумаги)
DH_SRC = "dohod"
DH_SRC_NAME = "dohod.ru"
DH_DATE_TOL = 3                       # дедупликация: даты фиксации реестра ±3 дня
DH_SUM_TOL = 0.01                     # ... и суммы ±1 %
DH_LIMIT = 200                        # строк в сводке с полной историей
_dh_lock = threading.Lock()
_dh_last = [0.0]
_DH_CUR = {"руб": "RUB", "rub": "RUB", "usd": "USD", "$": "USD", "долл": "USD", "eur": "EUR", "€": "EUR", "cny": "CNY", "юан": "CNY",
           "hkd": "HKD", "гонкон": "HKD", "kzt": "KZT", "тенге": "KZT"}


def dh_slug(secid):
    s = (secid or "").strip()
    return s.lower() if re.fullmatch(r"[A-Za-z0-9]{1,12}", s) else None


def _dh_text(frag):
    t = re.sub(r"<[^>]+>", " ", frag or "")
    t = t.replace("&nbsp;", " ").replace("&#160;", " ").replace("\xa0", " ").replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s+", " ", t).strip()


def _dh_date(t):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", t or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def _dh_amount(t):
    m = re.search(r"-?\d[\d ]*(?:[.,]\d+)?", (t or "").replace(" ", " "))
    if not m:
        return None
    try:
        v = float(m.group(0).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _dh_currency(page):
    """Валюта из заголовков вида «Дивиденд (руб.)»; по умолчанию рубли."""
    for m in re.finditer(r"Дивиденд[^<]{0,12}\(([^)<]{1,12})\)", page or "", re.I):
        c = m.group(1).strip().lower()
        for k, v in _DH_CUR.items():
            if k in c:
                return v
    return "RUB"


def dh_parse(page, today=None):
    """HTML страницы dohod.ru -> {rows, upcoming, currency, title} или None (страница в неожиданном формате).
    rows — фактические и утверждённые выплаты [{record, declared, value, cur, status paid|approved, src}], от новых к старым;
    upcoming — рекомендации и прогнозы (status recommended|forecast), в историю не идут."""
    if not page or not isinstance(page, str):
        return None
    today = today or date.today().isoformat()
    cur = _dh_currency(page)
    tbl = None
    for m in re.finditer(r"<table\b[^>]*>(.*?)</table>", page, re.S | re.I):
        body = m.group(1)
        head = _dh_text(" ".join(re.findall(r"<th\b[^>]*>(.*?)</th>", body, re.S | re.I))).lower()
        if "закрытия реестра" in head and "дивиденд" in head:
            tbl = body
            break
    if tbl is None:
        return None
    cols = {"declared": 0, "record": 1, "amount": 3}
    for tr in re.finditer(r"<tr\b([^>]*)>(.*?)</tr>", tbl, re.S | re.I):
        ths = [_dh_text(x).lower() for x in re.findall(r"<th\b[^>]*>(.*?)</th>", tr.group(2), re.S | re.I)]
        if ths:
            for i, h in enumerate(ths):
                if "закрытия реестра" in h:
                    cols["record"] = i
                elif "объявлен" in h:
                    cols["declared"] = i
                elif h.startswith("дивиденд"):
                    cols["amount"] = i
            break
    rows, upcoming, seen = [], [], set()
    for tr in re.finditer(r"<tr\b([^>]*)>(.*?)</tr>", tbl, re.S | re.I):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", tr.group(2), re.S | re.I)
        if len(cells) <= max(cols.values()):
            continue
        rec = _dh_date(_dh_text(cells[cols["record"]]))
        val = _dh_amount(_dh_text(cells[cols["amount"]]))
        if not rec or not val or val <= 0:
            continue
        decl = _dh_date(_dh_text(cells[cols["declared"]]))
        raw = tr.group(2).lower()
        is_fc = "forecast" in tr.group(1).lower() or "(прогноз)" in raw
        if is_fc:
            status = "recommended" if ("рекоменд" in raw and "(прогноз)" not in raw) else "forecast"
        elif rec >= today:
            status = "approved" if decl else "recommended"
        else:
            status = "paid"
        item = {"record": rec, "declared": decl, "value": round(val, 6), "cur": cur, "status": status, "src": DH_SRC}
        if status in ("paid", "approved"):
            k = (rec, item["value"])
            if k in seen:
                continue                                      # у источника встречаются дубли строк
            seen.add(k)
            rows.append(item)
        else:
            upcoming.append(item)
    if not rows and not upcoming and "<td" not in tbl:
        return None
    rows.sort(key=lambda x: x["record"], reverse=True)
    upcoming.sort(key=lambda x: x["record"])
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S | re.I)
    return {"rows": rows, "upcoming": upcoming, "currency": cur, "title": _dh_text(h1.group(1)) if h1 else ""}


def _dh_http(url):
    with _dh_lock:                                            # не чаще одного запроса в секунду на всё приложение
        wait = 1.0 - (time.time() - _dh_last[0])
        if wait > 0:
            time.sleep(wait)
        _dh_last[0] = time.time()
    return ext_open(url, timeout=20)[1].decode("utf-8", "replace")


def dh_history(secid, today=None, fetch=None):
    """Тикер -> {status ok|nodata|parse|err, rows, upcoming, fetched, ...}. Кэш в store: 7 суток; сбой сети отдаёт прошлый успешный ответ.
    Не бросает исключений. fetch(url) -> html подменяется в тестах."""
    slug = dh_slug(secid)
    empty = {"status": "nodata", "rows": [], "upcoming": [], "currency": "RUB", "url": None, "source": DH_SRC_NAME}
    if not slug:
        return empty
    key = "dh_v1_" + slug
    now = time.time()
    try:
        hit = store().get(key)
    except Exception:  # noqa: BLE001
        hit = None
    if hit:
        age = now - (hit.get("fetched") or 0)
        ttl = DH_TTL if hit.get("status") == "ok" else DH_NF_TTL if hit.get("status") == "nodata" else DH_ERR_TTL
        if age < ttl and now >= (hit.get("retry_at") or 0):
            return hit
        if hit.get("status") == "ok" and now < (hit.get("retry_at") or 0):
            return hit                                        # недавний сбой при обновлении: пока отдаём прошлую историю
    url = DH_BASE % slug
    try:
        page = (fetch or _dh_http)(url)
        parsed = dh_parse(page, today)
        if parsed is None:
            res = dict(empty, status="parse", url=url, fetched=now, note="Страница dohod.ru в неожиданном формате.")
        else:
            res = {"status": "ok" if parsed["rows"] or parsed["upcoming"] else "nodata", "rows": parsed["rows"], "upcoming": parsed["upcoming"],
                   "currency": parsed["currency"], "title": parsed["title"], "url": url, "source": DH_SRC_NAME, "fetched": now}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            res = dict(empty, url=url, fetched=now, note="На dohod.ru нет страницы дивидендов этого тикера.")
        else:
            res = dh_err(hit, empty, url, now, "dohod.ru временно недоступен (HTTP %s)." % e.code)
    except Exception as e:  # noqa: BLE001
        res = dh_err(hit, empty, url, now, "dohod.ru недоступен: %s" % str(e)[:80])
    if res["status"] == "parse" and hit and hit.get("status") == "ok":
        res = dict(hit, retry_at=now + DH_ERR_TTL)            # разметка поменялась, а старая история есть — не затираем
    try:
        store().put(key, res)
    except Exception:  # noqa: BLE001
        pass
    return res


def dh_err(hit, empty, url, now, note):
    """Сетевая ошибка: есть прошлая успешная история — отдаём её (повтор через час), иначе запись об ошибке."""
    if hit and hit.get("status") == "ok":
        return dict(hit, retry_at=now + DH_ERR_TTL, note=note)
    return dict(empty, status="err", url=url, fetched=now, note=note)


def _dh_days(a, b):
    try:
        return abs((datetime.strptime(a[:10], "%Y-%m-%d") - datetime.strptime(b[:10], "%Y-%m-%d")).days)
    except (TypeError, ValueError):
        return 10 ** 6


def _dh_same(a, b):
    """Одна и та же выплата: дата фиксации ±3 дня и сумма ±1 % (валюта, если указана, совпадает)."""
    if _dh_days(a["record"], b["record"]) > DH_DATE_TOL:
        return False
    if str(a.get("cur") or "RUB").upper() != str(b.get("cur") or "RUB").upper():
        return False
    x, y = float(a["value"]), float(b["value"])
    return abs(x - y) <= DH_SUM_TOL * max(abs(x), abs(y))


def dh_merge(items, hist_rows, today=None):
    """Слияние: items (T-Invest / сервер данных) сохраняются как есть; из hist_rows добираются выплаты вне периода, который покрывают items
    (раньше самой ранней и позже самой поздней с запасом ±3 дня). Внутри покрытого периода дубликаты по дате/сумме отбрасываются и
    ничего нового не добавляется (данные брокера точнее). Если единицы расходятся целым коэффициентом (сплит акций) — на совпавших датах
    он определяется и применяется к добираемым строкам. Возвращает (items + новые, сколько добавлено, коэффициент пересчёта или None)."""
    today = today or date.today().isoformat()
    base = [dict(x) for x in items or []]
    hist = [h for h in hist_rows or [] if h.get("record") and h.get("value") and h.get("status", "paid") in ("paid", "approved")]
    if not hist:
        return base, 0, None
    scale = None
    pairs = []
    for h in hist:
        for b in base:
            if _dh_days(h["record"], b["record"]) <= DH_DATE_TOL and str(b.get("cur") or "RUB").upper() == str(h.get("cur") or "RUB").upper() and b.get("value"):
                pairs.append(float(b["value"]) / float(h["value"]))
                break
    if pairs and all(abs(r - 1) > DH_SUM_TOL for r in pairs):
        lo, hi = min(pairs), max(pairs)
        if hi / lo <= 1.03 and (lo >= 2 or hi <= 0.5):
            scale = sorted(pairs)[len(pairs) // 2]
    if base:
        lo_d = min(b["record"] for b in base)
        hi_d = max(b["record"] for b in base)
        cover = (( datetime.strptime(lo_d[:10], "%Y-%m-%d") - timedelta(days=DH_DATE_TOL)).strftime("%Y-%m-%d"),
                 (datetime.strptime(hi_d[:10], "%Y-%m-%d") + timedelta(days=DH_DATE_TOL)).strftime("%Y-%m-%d"))
    else:
        cover = None
    added = []
    for h in sorted(hist, key=lambda x: x["record"]):
        x = dict(h)
        if scale:
            x["value"] = round(float(x["value"]) * scale, 6)
            x["scaled"] = round(scale, 6)
        if cover and cover[0] <= x["record"] <= cover[1]:
            continue                                          # покрыто основным источником
        if any(_dh_same(x, b) for b in base + added):
            continue
        x["src"] = DH_SRC
        x.setdefault("payment", None)
        x.setdefault("last_buy", None)
        added.append(x)
    return base + added, len(added), scale


def dh_enrich(items, secid, today=None, fetch=None):
    """items основного источника + история dohod.ru -> (items, meta). meta: {src, added, from, years, status, note}. Не бросает исключений."""
    meta = {"src": DH_SRC_NAME, "added": 0, "status": "off", "from": None, "years": None, "url": None, "note": None, "scaled": None}
    try:
        h = dh_history(secid, today, fetch)
        meta.update(status=h.get("status"), url=h.get("url"), note=h.get("note"))
        if h.get("status") != "ok":
            return items, meta
        merged, n, scale = dh_merge(items, h.get("rows"), today)
        meta.update(added=n, scaled=scale)
        if n:
            recs = [x["record"] for x in merged if x.get("src") == DH_SRC]
            meta["from"] = min(recs)
        return merged, meta
    except Exception as e:  # noqa: BLE001
        meta.update(status="err", note=str(e)[:80])
        return items, meta
