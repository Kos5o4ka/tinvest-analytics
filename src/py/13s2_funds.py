# ═══════════════════════════════ биржевые фонды (БПИФ): паспорт фонда и состав ═══════════════════════════════
# Карточка фонда строится тем же stock_card (13s_stocks.py): котировка, свечи, индикаторы. Здесь — то, что есть только у фондов:
#   fund_meta(secid)      — вид бумаги, полное название, дата начала торгов, управляющая компания (ISS: description + emitters);
#   fund_holdings(secid)  — состав фонда для отдельного запроса GET /api/fund/holdings (карточка не ждёт его).
# Источники состава (оба публичные, без авторизации):
#   1) T-Bank: web/v2/etf/assets/<тикер>/structure — фактический состав и СЧА. Отдаёт данные по фондам «Т-Капитала»;
#      по фондам других УК приходит пустой список. Даты среза в ответе нет — показываем дату получения.
#   2) Мосбиржа ISS: веса бумаг в индексе, за которым следует фонд (таблица FND_INDEX_OF). Это не фактический портфель,
#      а «состав индекса, за которым следует фонд» — так и подписывается.
# Кэш: удачный ответ — сутки, ошибка источника — 15 минут. Модуль загружается раньше 13s_stocks.py: на уровне модуля
# нельзя ссылаться на имена оттуда (только внутри функций). Префикс имён fnd_ / FND_.

FND_TB_URL = "https://www.tbank.ru/api/invest-gw/fireg-advisory/api/web/v2/etf/assets/%s/structure?idKind=ticker"
FND_TB_PAGE = "https://www.tbank.ru/invest/etfs/%s/"
FND_ISS_IDX = "https://iss.moex.com/iss/statistics/engines/stock/markets/index/analytics/%s.json?iss.meta=off&limit=100&start=%d"
FND_ISS_IDX_PAGE = "https://www.moex.com/ru/index/%s/constituents"
FND_ISS_DESC = "https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description"
FND_ISS_EMIT = "https://iss.moex.com/iss/emitters/%s.json?iss.meta=off"
FND_TTL = DAY
FND_ERR_TTL = 15 * 60
FND_META_TTL = 7 * DAY
# Фонды других УК, которые следуют за индексом Мосбиржи, и сам индекс. Только бумаги, где индекс прямо указан в правилах фонда.
FND_INDEX_OF = {"SBMX": "IMOEX", "EQMX": "IMOEX", "TMOS": "IMOEX", "SBGB": "RGBITR", "SBRB": "RUCBTRNS"}
FND_INDEX_NAMES = {"IMOEX": "Индекс МосБиржи", "RGBITR": "Индекс гособлигаций RGBITR", "RUCBTRNS": "Индекс корпоративных облигаций RUCBTRNS"}
FND_INDEX_SHARES = {"IMOEX"}                       # индексы акций: бумаги из состава открываются карточкой акции
FND_NO_DATA_NOTE = {
    "Денежный рынок": "Фонды денежного рынка обычно вкладывают в сделки репо с центральным контрагентом; поэлементный состав "
                      "публикует управляющая компания в отчётах фонда.",
    "Золото и металлы": "Фонды на золото обычно держат биржевое золото или фьючерсы на него; подробный состав — в отчётах управляющей компании.",
}
_FND_TYPE_RU = {"Stock": "Акция", "Bond": "Облигация", "Currency": "Валюта", "Etf": "Фонд", "Futures": "Фьючерс"}


def _fnd_f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def _fnd_secid(secid):
    s = (secid or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9._-]{1,16}", s):
        raise ApiError("Некорректный тикер.", 400)
    return s


def fnd_tb_parse(j):
    """Ответ T-Bank (structure) -> {items, nav, nav_cur, count} или None, если состава нет (фонд другой УК или пустой ответ).
    items: [{name, ticker, isin, type, type_ru, weight, value, stock}], weight — доля в процентах, по убыванию."""
    if not isinstance(j, dict):
        return None
    items = []
    for x in j.get("items") or []:
        if not isinstance(x, dict):
            continue
        w = _fnd_f(x.get("relativeValue"))
        name = str(x.get("name") or x.get("ticker") or "").strip()
        if w is None or not name:
            continue
        t = str(x.get("type") or "")
        items.append({"name": name, "ticker": x.get("ticker") or None, "isin": None, "type": t,
                      "type_ru": x.get("typeRu") or _FND_TYPE_RU.get(t) or "", "weight": round(w, 4),
                      "value": _fnd_f(x.get("value")), "stock": t == "Stock" and bool(x.get("ticker"))})
    if not items:
        return None
    items.sort(key=lambda r: -r["weight"])
    nav = _fnd_f(j.get("netAssetValue"))
    return {"items": items, "nav": nav or None, "nav_cur": (j.get("currency") or "RUB").upper() if nav else None,
            "count": int(j.get("structureCount") or len(items))}


def fnd_iss_index_parse(j):
    """Страница ISS analytics индекса -> (rows, total, tradedate). rows: [{name, ticker, isin, weight}]."""
    t = (j or {}).get("analytics") or {}
    cols = t.get("columns") or []
    rows, day = [], None
    for r in t.get("data") or []:
        d = dict(zip(cols, r))
        w = _fnd_f(d.get("weight"))
        sec = d.get("secids") or d.get("ticker")
        if w is None or not sec:
            continue
        day = day or d.get("tradedate")
        isin = sec if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", str(sec)) and not str(sec).startswith("SU") else None   # SU…RMFS — код ОФЗ на бирже, не ISIN
        rows.append({"name": d.get("shortnames") or sec, "ticker": d.get("ticker") or sec, "isin": isin, "weight": round(w, 4)})
    cur = (j or {}).get("analytics.cursor") or {}
    cd = dict(zip(cur.get("columns") or [], (cur.get("data") or [[]])[0])) if cur.get("data") else {}
    total = int(cd.get("TOTAL") or len(rows))
    return rows, total, day


def fnd_index_holdings(index):
    """Все бумаги индекса с весами (страницы по 100)."""
    j = json.loads(http_text(FND_ISS_IDX % (index, 0), timeout=20))
    rows, total, day = fnd_iss_index_parse(j)
    start = len(rows)
    while rows and start < min(total, 1000):
        part, _, _ = fnd_iss_index_parse(json.loads(http_text(FND_ISS_IDX % (index, start), timeout=20)))
        if not part:
            break
        rows.extend(part)
        start += len(part)
    rows.sort(key=lambda r: -r["weight"])
    return rows, day


def _fnd_from_tb(secid):
    raw = http_text(FND_TB_URL % urllib.parse.quote(secid), timeout=15)
    return fnd_tb_parse(json.loads(raw))


def fund_holdings_build(secid, category=None):
    """Состав фонда из доступных источников -> словарь ответа /api/fund/holdings (без кэша)."""
    today = date.today().isoformat()
    base = {"secid": secid, "items": [], "as_of": None, "as_of_kind": None, "nav": None, "nav_cur": None, "source": None,
            "basis": None, "index": None, "status": "none", "note": None, "fetched": time.time()}
    errs = []
    tb = None
    try:
        tb = _fnd_from_tb(secid)
    except Exception as e:  # noqa: BLE001 — сеть, JSON, HTTP-ошибка источника
        errs.append("T-Bank: " + str(e)[:80])
    if tb:
        base.update(items=tb["items"], nav=tb["nav"], nav_cur=tb["nav_cur"], as_of=today, as_of_kind="fetched", status="ok", basis="fund",
                    source={"name": "T-Bank (Т-Капитал)", "url": FND_TB_PAGE % secid})
        return base
    idx = FND_INDEX_OF.get(secid)
    if idx:
        rows, day = [], None
        try:
            rows, day = fnd_index_holdings(idx)
        except Exception as e:  # noqa: BLE001
            errs.append("Мосбиржа: " + str(e)[:80])
        if rows:
            shares = idx in FND_INDEX_SHARES
            for r in rows:
                r.update(type="Stock" if shares else "Bond", type_ru="Акция" if shares else "Облигация", value=None, stock=shares)
            base.update(items=rows, as_of=day, as_of_kind="index", status="ok", basis="index",
                        index={"id": idx, "name": FND_INDEX_NAMES.get(idx, idx)},
                        source={"name": "Мосбиржа", "url": FND_ISS_IDX_PAGE % idx})
            return base
    if errs:                                       # хотя бы один источник не ответил — не запоминаем «состава нет» надолго
        base.update(status="err", note="Источник состава сейчас недоступен. " + "; ".join(errs))
        return base
    base["note"] = FND_NO_DATA_NOTE.get(category or "", "Открытого источника с составом этого фонда нет; состав публикует управляющая компания "
                                                       "в отчётах фонда.")
    return base


def fund_holdings(secid, force=False, category=None):
    """Состав фонда с кэшем в store: удачный ответ — сутки, ошибка источника — 15 минут."""
    secid = _fnd_secid(secid)
    key = "fnd_hold_v1_" + secid
    if not force:
        hit = store().get(key, FND_TTL)
        if hit is not None and (hit.get("status") != "err" or time.time() - (hit.get("fetched") or 0) < FND_ERR_TTL):
            return hit
    with key_lock(key):
        res = fund_holdings_build(secid, category)
        store().put(key, res)
    return res


def fund_meta(secid, category=None):
    """Паспорт фонда из ISS: {category, type_name, full_name, issue_date, manager, manager_url}. Ошибки сети не критичны (поля None)."""
    secid = _fnd_secid(secid)
    key = "fnd_meta_v1_" + secid
    hit = store().get(key, FND_META_TTL)
    if hit is None:
        hit = mem_get(("fnd_meta_err", secid), FND_ERR_TTL)
    if hit is None:
        hit, ok = {"type_name": None, "full_name": None, "issue_date": None, "manager": None, "manager_url": None}, True
        try:
            j = json.loads(http_text(FND_ISS_DESC % urllib.parse.quote(secid), timeout=10))
            t = j.get("description") or {}
            d = {r[0]: r[2] for r in t.get("data") or [] if r}
            hit.update(type_name=d.get("TYPENAME"), full_name=d.get("NAME") or d.get("ISSUENAME"), issue_date=d.get("ISSUEDATE"))
            em = d.get("EMITTER_ID")
            if em:
                e = json.loads(http_text(FND_ISS_EMIT % urllib.parse.quote(str(em)), timeout=10))
                et = e.get("emitter") or {}
                er = dict(zip(et.get("columns") or [], (et.get("data") or [[]])[0])) if et.get("data") else {}
                hit.update(manager=er.get("SHORT_TITLE") or er.get("TITLE"), manager_url=er.get("URL") or None)
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            store().put(key, hit)
        else:
            mem_put(("fnd_meta_err", secid), hit)
    return dict(hit, category=category)


def fund_holdings_get(cfg, acc, q, force):
    secid = q.get("secid") or ""
    if not secid.strip():
        raise ApiError("Не указан тикер фонда.", 400)
    s = _fnd_secid(secid)
    try:
        cat = stk_fund_category(s)
    except Exception:  # noqa: BLE001
        cat = None
    return fund_holdings(s, bool(force), cat)


API_GET["/api/fund/holdings"] = fund_holdings_get
