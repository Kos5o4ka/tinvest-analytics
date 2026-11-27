# ═══════════════════════════════ акции Мосбиржи: котировки, свечи, карточка, скринер ═══════════════════════════════
# Источники: ISS Мосбиржи (котировки TQBR, дневная история для недельной/месячной динамики, свечи, дивиденды) и, если задан токен,
# T-Invest API (сектор, дивиденды GetDividends, фундаментальные показатели GetAssetFundamentals, даты отчётности GetAssetReports).
# Без токена мультипликаторы считаются по МСФО из smart-lab (13m_ifrs.ifrs_multiples), дата отчётности неизвестна.
# Проценты везде — числами в процентных пунктах (12.5 = 12,5 %), как и chg_d/chg_w/chg_m.
# Контракт для других модулей: stocks_universe, funds_universe, stk_lookup, stock_candles, stock_history_closes.
# Карточка stock_card открывает и биржевые фонды (kind = "fund"); паспорт и состав фонда — в 13s2_funds.py.

STK_ISS = "https://iss.moex.com/iss/"
STK_SH = "engines/stock/markets/shares/boards/%s/securities.json?iss.meta=off&iss.only=securities,marketdata"
STK_HIST = "history/engines/stock/markets/shares/boards/TQBR/securities.json?iss.meta=off&iss.only=history,history.cursor&history.columns=SECID,CLOSE&date=%s&start=%d"
STK_WEEK, STK_MONTH = 5, 21                    # торговых дней назад для chg_w / chg_m
STK_DEFAULT_SECTOR = "Прочее"
_stk_lock = threading.Lock()

_STK_SECTOR_SRC = {
    "Нефть и газ": "GAZP LKOH ROSN NVTK SIBN TATN TATNP SNGS SNGSP BANE BANEP TRNFP RNFT KRKNP JNOS JNOSP",
    "Банки и финансы": "SBER SBERP VTBR T TCSG CBOM BSPB BSPBP SVCB MBNK MOEX SPBE RENI LEAS SFIN ZAYM MGKL KUZB",
    "Металлы и добыча": "GMKN NLMK CHMF MAGN MTLR MTLRP ALRS PLZL RUAL TRMK SELG UGLD VSMO CHMK RASP ENPG LNZL LNZLP",
    "Телеком": "RTKM RTKMP MTSS MGTS MGTSP TTLK CNTL CNTLP",
    "IT": "YDEX YNDX VKCO OZON POSI HEAD ASTR DIAS CIAN WUSH SOFL",
    "Потребительский сектор": "MGNT X5 FIXP LENT MVID BELU GCHE ABRD DELI OZPH APTK HNFG KROT RAGR AQUA ABIO MDMG GEMC ROST",
    "Электроэнергетика": "IRAO HYDR FEES MSNG MSRS MRKC MRKP MRKU MRKV MRKS MRKZ MRKY LSNG LSNGP TGKA TGKB TGKBP TGKN OGKB UPRO ELFV KLSB YKEN YKENP ENRU DVEC",
    "Химия": "AKRN PHOR KAZT KAZTP NKNC NKNCP KZOS KZOSP",
    "Транспорт": "AFLT FLOT NMTP FESH GLTR NKHP EUTR UNAC",
    "Строительство и девелопмент": "PIKK SMLT LSRG ETLN",
}
STK_SECTORS = {k: s for s, t in _STK_SECTOR_SRC.items() for k in t.split()}
STK_API_SECTORS = {"energy": "Нефть и газ", "financial": "Банки и финансы", "materials": "Металлы и добыча", "telecom": "Телеком", "it": "IT",
                   "consumer": "Потребительский сектор", "utilities": "Электроэнергетика", "real_estate": "Строительство и девелопмент",
                   "industrials": "Прочее", "health_care": "Потребительский сектор", "other": "Прочее"}
STK_SECTOR_NAMES = ["Нефть и газ", "Банки и финансы", "Металлы и добыча", "Телеком", "IT", "Потребительский сектор", "Электроэнергетика",
                    "Химия", "Транспорт", "Строительство и девелопмент", "Прочее"]


def _stk_f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def _stk_msk_now():
    return datetime.now(timezone(timedelta(hours=3)))


def _stk_trading(now=None):
    n = now or _stk_msk_now()
    return n.weekday() < 5 and 9 <= n.hour < 24


def _stk_ttl(now=None):
    return 120 if _stk_trading(now) else 3600


def _stk_iss(path, timeout=25):
    return json.loads(http_text(STK_ISS + path, timeout=timeout))


def _stk_tab(j, name):
    t = (j or {}).get(name) or {}
    cols = t.get("columns") or []
    return [dict(zip(cols, r)) for r in t.get("data") or []]


def stk_rows_from_iss(j, sector_of=None, default_sector=STK_DEFAULT_SECTOR):
    """Ответ ISS (securities + marketdata одной доски) -> список бумаг в формате stocks_universe (chg_w, chg_m = None)."""
    md = {}
    for r in _stk_tab(j, "marketdata"):
        if r.get("SECID"):
            md[r["SECID"]] = r
    out = []
    for r in _stk_tab(j, "securities"):
        sid = r.get("SECID")
        if not sid:
            continue
        m = md.get(sid) or {}
        prev = _stk_f(r.get("PREVPRICE")) or _stk_f(r.get("PREVWAPRICE"))
        price = _stk_f(m.get("LAST")) or _stk_f(m.get("MARKETPRICE")) or _stk_f(m.get("LCURRENTPRICE")) or prev
        if not price:
            continue
        chg = (price / prev - 1) * 100 if prev else _stk_f(m.get("LASTTOPREVPRICE"))
        cap = _stk_f(m.get("ISSUECAPITALIZATION"))
        if not cap and r.get("ISSUESIZE"):
            cap = price * float(r["ISSUESIZE"])
        out.append({"secid": sid, "isin": r.get("ISIN") or "", "name": r.get("SECNAME") or r.get("SHORTNAME") or sid,
                    "shortname": r.get("SHORTNAME") or sid,
                    "sector": (sector_of or {}).get(sid) or default_sector, "price": price, "prev": prev,
                    "chg_d": None if chg is None else round(chg, 2),
                    "value_today": _stk_f(m.get("VALTODAY_RUR")) or _stk_f(m.get("VALTODAY")) or 0.0,
                    "cap": cap or None, "lot": int(r.get("LOTSIZE") or 1), "chg_w": None, "chg_m": None,
                    "instrid": r.get("INSTRID") or "", "sectype": str(r.get("SECTYPE") or ""),
                    "is_fund": str(r.get("INSTRID") or "").startswith("IF")})
    return out


STK_FUND_CATS = {
    "Денежный рынок": "LQDT AKMM SBMM TMON AMNR CASH MONY OLIQ PSMM FMMM TSAV BCSD",
    "Золото и металлы": "GOLD TGLD AKGD SBGD BCSG PSGM",
    "Облигации": "SBGB OBLG AKMB TBRU SBRB TOFZ INFL OFZS WOFZ SUGB SBCB CORP BOND ROBL BNDA BNDB BNDC AMGB PSRB TLCB SBLB SBHI SBFR AKFB TPAY",
    "Акции": "TMOS SBMX EQMX AKME TDIV DIVD AKIE AKAI AIIQ MKBD",
    "Валюта": "TUSD TEUR TCNY YUAN CNYM WUSD AMNY",
}
STK_FUND_CAT_OF = {t: c for c, ts in STK_FUND_CATS.items() for t in ts.split()}
STK_FUND_OTHER = "Прочие фонды"
# Эвристика по названию (SECNAME / полное название выпуска из ISS), порядок важен: первое совпадение решает.
# «Валютные облигации», «облигации в юанях» — облигации; «денежный рынок в юанях», «накопительный в юанях» — валюта.
_STK_FUND_RULES = (
    ("Золото и металлы", r"золот|драгмет|драгоцен|металл|платин|паллад"),
    ("Недвижимость", r"недв|арендн|складск|промышленные парки|\bндв\b|лахта|фжн|парус|рентал|рентн|комнед|термы|термолэнд|"
                     r"современн\w* \d|активо"),
    ("Облигации", r"облиг|\bобл\b|\bобл\.|офз|бонд|еврообл|флоатер|переменн\w* купон|долгов|гособлиг|корп\.? обл|высокодоходн|"
                  r"\bвдо\b|суборд"),
    ("Валюта", r"юан|доллар|\bевро\b|валют|\bcny\b|\busd\b"),
    ("Денежный рынок", r"денеж\w*\.? рын|\bден\.? рын|ликвид|казна|казнач|накопит|сберегат|ежедневн\w* процент|\bрепо\b|\bmm\b"),
    ("Акции", r"акци|\bакц|индекс|дивид|фишк|ммвб|мосбирж|лидер|технолог|интеллект|потреб|финансов|роста|айпио|\bipo\b|квант|трендов|"
              r"халял|российские акции|устойч|ответств|первичных размещ"),
    ("Смешанные", r"портф|всепогод|лежебок|моя цель|смеш|баланс|стратеги|смарт|разумн|консерв|осторожн|антиинфляц|инфляц|"
                  r"пассивн\w* доход|ежемесячн\w* доход|абсолютн"),
)
_STK_FUND_RX = [(c, re.compile(rx)) for c, rx in _STK_FUND_RULES]


def stk_fund_category(secid, name=""):
    """Категория фонда для тепловой карты: сначала таблица тикеров, затем эвристика по названию, иначе «Прочие фонды»."""
    c = STK_FUND_CAT_OF.get((secid or "").upper())
    if c:
        return c
    n = " ".join(str(name or "").lower().replace("ё", "е").replace("–", "-").replace("«", " ").replace("»", " ").replace('"', " ").split())
    for cat, rx in _STK_FUND_RX:
        if rx.search(n):
            return cat
    return STK_FUND_OTHER


def stock_history_closes(date_s):
    """Цены закрытия всех акций TQBR за один день: {secid: close}. Прошлые даты кэшируются навсегда; нет торгов — {}."""
    key = "stk_hist_v1_" + date_s
    past = date_s < date.today().isoformat()
    hit = store().get(key, None if past else 300)
    if hit is not None:
        return hit
    j = _stk_iss(STK_HIST % (date_s, 0))
    cur = (_stk_tab(j, "history.cursor") or [{}])[0] if "history.cursor" in j else {}
    rows = _stk_tab(j, "history")
    total, size = int(cur.get("TOTAL") or len(rows)), int(cur.get("PAGESIZE") or 100) or 100
    starts = list(range(size, total, size))
    for part in pool_map(lambda s: _stk_tab(_stk_iss(STK_HIST % (date_s, s)), "history"), starts, workers=4):
        rows.extend(part)
    out = {r["SECID"]: float(r["CLOSE"]) for r in rows if r.get("SECID") and _stk_f(r.get("CLOSE"))}
    if out or past:
        store().put(key, out)
    return out


def _stk_sessions():
    """Даты последних торговых сессий (по свечам SBER), по возрастанию."""
    cs = stock_candles("SBER", 24, 60)
    return [c["t"][:10] for c in cs]


def _stk_changes(rows):
    """Дописывает chg_w / chg_m: цена сейчас к закрытию 5 и 21 торговый день назад. Ошибки сети не критичны."""
    try:
        ses = _stk_sessions()
    except Exception:  # noqa: BLE001
        return
    for field, n in (("chg_w", STK_WEEK), ("chg_m", STK_MONTH)):
        if len(ses) <= n:
            continue
        base = None
        for idx in range(-1 - n, -len(ses) - 1, -1):
            try:
                b = stock_history_closes(ses[idx])
                if b:
                    base = b
                    break
            except Exception:  # noqa: BLE001
                continue
        if not base:
            continue
        for r in rows:
            b = base.get(r["secid"])
            if b and r.get("price"):
                r[field] = round((r["price"] / b - 1) * 100, 2)


def stk_api_map(cfg):
    """Справочник T-Invest по акциям TQBR: {тикер: {uid, asset_uid, sector}}; пусто без токена или при ошибке. Кэш 7 дней."""
    if not cfg or not (cfg.get("token") or "").strip():
        return {}
    key = "stk_tmap_v1"
    hit = store().get(key, 7 * DAY)
    if hit is not None:
        return hit
    try:
        out = {}
        for i in TInvest(cfg).instruments_all("Shares"):
            t = i.get("ticker")
            if t and i.get("classCode") == "TQBR" and t not in out:
                out[t] = {"uid": i.get("uid") or "", "asset_uid": i.get("assetUid") or "", "sector": i.get("sector") or ""}
        if out:
            store().put(key, out)
        return out
    except ApiError:
        return {}


def stk_apply_snapshot(rows, snap):
    """Недельное и месячное изменение из готового среза сервера (по тикеру) -> число заполненных бумаг. Не трогает уже заполненное."""
    by = {r.get("secid"): r for r in snap or [] if isinstance(r, dict)}
    n = 0
    for r in rows:
        x = by.get(r.get("secid"))
        if not x:
            continue
        for f in ("chg_w", "chg_m"):
            if r.get(f) is None and isinstance(x.get(f), (int, float)) and not isinstance(x.get(f), bool):
                r[f] = x[f]
        n += r.get("chg_w") is not None and r.get("chg_m") is not None
    return n


def _stk_fill_changes(rows):
    """chg_w / chg_m: сначала из среза сервера (без десятков запросов за историей закрытий). Если срез недоступен, устарел или
    не покрывает торгуемые бумаги — прежний путь (цены закрытий с Мосбиржи); при полном покрытии он не нужен."""
    try:
        snap = market_snapshot_stocks()
    except Exception:  # noqa: BLE001
        snap = None
    if snap:
        stk_apply_snapshot(rows, snap)
        if all(r.get("chg_w") is not None and r.get("chg_m") is not None for r in rows if (r.get("value_today") or 0) > 0):
            return
    _stk_changes(rows)


def _stk_tqbr_rows(force=False):
    """Все бумаги TQBR (акции и фонды) с chg_w/chg_m; общий кэш. Фонды помечены is_fund (INSTRID «IF…»)."""
    key = ("stk_universe",)
    rows = None if force else mem_get(key, _stk_ttl())
    if rows is None:
        with key_lock("stk_universe"):
            rows = None if force else mem_get(key, _stk_ttl())
            if rows is None:
                rows = stk_rows_from_iss(_stk_iss(STK_SH % "TQBR", 40), STK_SECTORS)
                _stk_fill_changes(rows)
                mem_put(key, rows)
    return rows


def stocks_universe(force=False, cfg=None):
    """Акции TQBR (без фондов): [{secid, isin, name, shortname, sector, price, prev, chg_d, value_today, cap, lot, chg_w, chg_m}].
    Сектор: встроенный справочник, для остальных — сектор T-Invest (если передан cfg с токеном), иначе «Прочее».
    Кэш 2 минуты в торговые часы, иначе час. Кэш общий, возвращается копия строк."""
    out = [dict(r) for r in _stk_tqbr_rows(force) if not r.get("is_fund")]
    tm = stk_api_map(cfg) if cfg else {}
    for r in out:
        a = tm.get(r["secid"])
        if a:
            r["uid"], r["asset_uid"] = a["uid"], a["asset_uid"]
            if r["secid"] not in STK_SECTORS and a["sector"]:
                r["sector"] = STK_API_SECTORS.get(a["sector"], STK_DEFAULT_SECTOR)
    return out


def funds_universe():
    """Фонды (с 2025 торгуются на TQBR, INSTRID «IF…») в формате stocks_universe; sector — категория фонда (stk_fund_category).
    Если на TQBR фондов нет — запасной вариант: доска TQTF."""
    rows = [dict(r) for r in _stk_tqbr_rows() if r.get("is_fund")]
    if not rows:
        rows = _stk_tqtf_rows()
    for r in rows:
        r["sector"] = stk_fund_category(r["secid"], r.get("name") or r.get("shortname"))
    return rows


def _stk_tqtf_rows():
    """Бумаги доски TQTF (фонды до переезда на TQBR и те, что там остались), копии строк с is_fund=True. Кэш как у TQBR."""
    key = ("stk_funds",)
    cached = mem_get(key, _stk_ttl())
    if cached is None:
        cached = stk_rows_from_iss(_stk_iss(STK_SH % "TQTF", 40), None, STK_FUND_OTHER)
        _stk_changes(cached)
        mem_put(key, cached)
    return [dict(r, is_fund=True) for r in cached]


STK_IV = {"H": 60, "D": 24, "W": 7, "M": 31}
STK_DAYS = {60: 45, 24: 650, 7: 1700, 31: 3000}


def stk_candles_from_iss(rows, interval):
    """Строки таблицы candles ISS -> [{t, o, h, l, c, v}]; t — дата (дневные и крупнее) или «ГГГГ-ММ-ДД ЧЧ:ММ»."""
    out = []
    for r in rows:
        o, h, l, c = (_stk_f(r.get(k)) for k in ("open", "high", "low", "close"))
        if None in (o, h, l, c) or not r.get("begin"):
            continue
        b = str(r["begin"])
        out.append({"t": b[:16] if interval in (1, 10, 60) else b[:10], "o": o, "h": h, "l": l, "c": c, "v": _stk_f(r.get("volume")) or 0.0})
    return out


def stock_candles(secid, interval=24, days=400):
    """Свечи ISS (interval: 1, 10, 60, 24, 7, 31) за последние days дней; страницы по 500. Кэш по (бумага, интервал, дата)."""
    secid = (secid or "").strip().upper()
    interval = int(interval)
    today = date.today().isoformat()
    key = "stk_c_v1_%s_%d_%d_%s" % (secid, interval, days, today)
    hit = store().get(key, 300 if _stk_trading() else None)
    if hit is not None:
        return hit
    frm = (date.today() - timedelta(days=days)).isoformat()
    out, start = [], 0
    for _ in range(40):
        j = _stk_iss("engines/stock/markets/shares/securities/%s/candles.json?iss.meta=off&interval=%d&from=%s&till=%s&start=%d"
                     % (urllib.parse.quote(secid), interval, frm, today, start), 30)
        rows = _stk_tab(j, "candles")
        out.extend(stk_candles_from_iss(rows, interval))
        if len(rows) < 500:
            break
        start += len(rows)
    if out:
        store().put(key, out)
    return out


# ── дивиденды ──

def stk_api_dividends(items):
    """GetDividends -> тот же формат."""
    out = []
    for x in items or []:
        v = qf(x.get("dividendNet")) if x.get("dividendNet") else None
        d = iso_date(x.get("recordDate"))
        if not v or not d:
            continue
        out.append({"record": d, "payment": iso_date(x.get("paymentDate")), "declared": iso_date(x.get("declaredDate")),
                    "last_buy": iso_date(x.get("lastBuyDate")), "value": v, "cur": cur_of(x.get("dividendNet"), "rub").upper(), "src": "tinvest"})
    return out


def stk_srv_dividends(items):
    """md/dividends сервера данных -> внутренний формат (как stk_api_dividends)."""
    out = []
    for x in items or []:
        v = _stk_f(x.get("value"))
        if v and x.get("record"):
            out.append({"record": x["record"], "payment": x.get("payment"), "declared": x.get("declared"), "last_buy": x.get("last_buy"),
                        "value": v, "cur": str(x.get("currency") or "RUB").upper(), "src": "tinvest"})
    return out


def stk_dividends_build(items, price, today=None, limit=30):
    """Сводка по дивидендам: объединение источников по дате фиксации, доходность к текущей цене, годовая (TTM) и ближайшая будущая выплата."""
    today = today or date.today().isoformat()
    by = {}
    for it in items:
        k = (it["record"], round(float(it["value"]), 6))    # две выплаты в один день фиксации (обычная + special) — разные строки
        if k not in by or it.get("src") == "tinvest":
            by[k] = it
    rows = sorted(by.values(), key=lambda x: x["record"], reverse=True)
    y1 = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
    for r in rows:
        r["yield_pct"] = round(r["value"] / price * 100, 2) if price and r["cur"] in ("RUB", "RUR") else None
        r["future"] = r["record"] >= today
    ttm = sum(r["value"] for r in rows if y1 < r["record"] <= today and r["cur"] in ("RUB", "RUR"))
    fut = sorted((r for r in rows if r["future"]), key=lambda x: x["record"])
    return {"items": rows[:limit], "ttm_value": round(ttm, 4), "yield_ttm": round(ttm / price * 100, 2) if price and ttm else None,
            "next": fut[0] if fut else None}


def stock_dividends(secid, price, uid=None, cfg=None, history=False):
    """history=True — добрать длинную историю (dohod.ru, см. 13x9b_divhist): T-Invest отдаёт ~6 лет, у компаний 20+. Источник каждой строки — в поле src."""
    items = []
    source = "none"                                    # ISS dividends.json мёртв — только T-Invest / сервер данных
    if uid and cfg and (cfg.get("token") or "").strip():
        try:
            now = datetime.now(timezone.utc)
            items.extend(stk_api_dividends(TInvest(cfg).dividends(uid, (now - timedelta(days=6 * 365)).strftime("%Y-%m-%dT00:00:00Z"),
                                                                  (now + timedelta(days=400)).strftime("%Y-%m-%dT00:00:00Z"))))
            source = "tinvest"
        except ApiError:
            pass
    else:
        srv = ds_parsed("md/dividends", {"secid": secid})
        if isinstance(srv, dict) and srv.get("items") is not None:
            items.extend(stk_srv_dividends(srv["items"]))
            source = "tinvest-server"
    hist = None
    if history:
        had = bool(items)
        items, hist = dh_enrich(items, secid)
        if not had and hist.get("added"):
            source = DH_SRC                                # токена и сервера нет: вся история — со стороннего источника
    res = stk_dividends_build(items, price, limit=DH_LIMIT if history else 30)
    res["source"] = source
    if hist is not None:
        res["hist"] = {"src": DH_SRC_NAME, "status": hist.get("status"), "added": hist.get("added"), "url": hist.get("url"), "note": hist.get("note"),
                       "from": hist.get("from"), "years": len({r["record"][:4] for r in res["items"]})}
    return res


# ── мультипликаторы, отчётность ──

def stk_from_fund(f):
    """GetAssetFundamentals (один актив) -> мультипликаторы. Проценты API приходят в процентных пунктах. 0 = «нет данных»."""
    def g(k, zero_none=True):
        v = _stk_f((f or {}).get(k))
        return None if v is None or (zero_none and v == 0) else v
    dy = g("dividendYieldDailyTtm", False)
    if not dy:
        dy = g("forwardAnnualDividendYield", False)
    return {"pe": g("peRatioTtm"), "pb": g("priceToBookTtm"), "ev_ebitda": g("evToEbitdaMrq"), "div_yield": dy,
            "rev_growth": g("oneYearAnnualRevenueGrowthRate", False), "ni_growth": None, "roe": g("roe", False),
            "nd_ebitda": g("netDebtToEbitda", False), "period": "TTM", "source": "tinvest"}


def stk_srv_fund(f, source="tinvest-server"):
    """Строка md/fundamentals сервера -> мультипликаторы."""
    out = {k: _stk_f((f or {}).get(k)) for k in ("pe", "pb", "ev_ebitda", "div_yield", "rev_growth", "roe", "nd_ebitda")}
    out.update(ni_growth=None, period="TTM", source=source)
    return out


def stock_multiples(secid, cap, asset_uid=None, cfg=None):
    if cfg and (cfg.get("token") or "").strip():
        if asset_uid:
            try:
                fs = TInvest(cfg).asset_fundamentals([asset_uid])
                if fs:
                    return stk_from_fund(fs[0])
            except ApiError:
                pass
    else:
        srv = ds_parsed("md/fundamentals")
        if srv and srv.get(secid):
            return stk_srv_fund(srv[secid])
    m = ifrs_multiples(ifrs_fin(secid), cap)
    m["div_yield"] = None
    return m


def stock_next_report(uid, cfg, secid=None):
    """Ближайшая будущая дата отчётности из T-Invest или None. uid — UID инструмента (по assetUid API отвечает 404).
    Без своего токена — через сервер данных (md/reports по тикеру)."""
    if not (cfg and (cfg.get("token") or "").strip()) and secid:
        srv = ds_parsed("md/reports", {"secid": secid})
        if srv is not None:
            if srv.get("date"):
                return {"date": srv["date"], "year": srv.get("year"), "num": srv.get("num"), "type": srv.get("type"), "note": None,
                        "source": "tinvest-server"}
            return {"date": None, "note": "Дата следующей отчётности пока не опубликована.", "source": "tinvest-server"}
    if not (uid and cfg and (cfg.get("token") or "").strip()):
        return {"date": None, "note": "Даты отчётности доступны при подключённом токене T-Invest."}
    try:
        now = datetime.now(timezone.utc)
        rs = TInvest(cfg).asset_reports(uid, now.strftime("%Y-%m-%dT00:00:00Z"), (now + timedelta(days=400)).strftime("%Y-%m-%dT00:00:00Z"))
    except ApiError as e:
        return {"date": None, "note": str(e)[:120]}
    today = date.today().isoformat()
    fut = sorted((iso_date(r.get("reportDate")), r) for r in rs if iso_date(r.get("reportDate")) and iso_date(r.get("reportDate")) >= today)
    if not fut:
        return {"date": None, "note": "Дата следующей отчётности пока не опубликована."}
    r = fut[0][1]
    return {"date": fut[0][0], "year": r.get("periodYear"), "num": r.get("periodNum"), "type": r.get("periodType"), "note": None}


# ── карточка ──

def stk_lookup(secid, cfg=None):
    """Бумага для карточки: (строка котировки, "share" | "fund"). Сначала акции TQBR, затем фонды (TQBR, потом TQTF); нет — (None, None)."""
    q = next((r for r in stocks_universe(cfg=cfg) if r["secid"] == secid), None)
    if q is not None:
        return q, "share"
    q = next((r for r in funds_universe() if r["secid"] == secid), None)
    if q is None:
        try:
            q = next((r for r in _stk_tqtf_rows() if r["secid"] == secid), None)
        except Exception:  # noqa: BLE001 — запасная доска недоступна: просто «не найдено»
            q = None
        if q is not None:
            q["sector"] = stk_fund_category(secid, q.get("name") or q.get("shortname"))
    return (q, "fund") if q is not None else (None, None)


def stock_card(secid, interval="D", cfg=None):
    """Карточка акции или биржевого фонда: котировка, свечи (D/W/H), индикаторы и сводный сигнал, уровни.
    Для акции ещё мультипликаторы, дивиденды, дата отчётности; для фонда — паспорт (fund) и дивиденды, если фонд их платит.
    Состав фонда — отдельным запросом /api/fund/holdings (13s2_funds.py), карточка его не ждёт."""
    secid = (secid or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9._-]{1,16}", secid):
        raise ApiError("Некорректный тикер.", 400)
    iv = STK_IV.get(str(interval).upper(), STK_IV.get("D")) if not str(interval).isdigit() else int(interval)
    q, kind = stk_lookup(secid, cfg)
    if q is None:
        raise ApiError("Бумага %s не найдена среди акций и фондов, торгуемых на Мосбирже." % secid, 404)
    cs = stock_candles(secid, iv, STK_DAYS.get(iv, 650))
    ser = ta_series(cs) if cs else {}
    view = {"D": 220, "W": 200, "H": 260, "M": 120}.get({v: k for k, v in STK_IV.items()}.get(iv, "D"), 220)
    k0 = max(0, len(cs) - view)
    r4 = lambda a: [None if v is None else round(v, 4) for v in a[k0:]]  # noqa: E731
    summ = ta_summary(cs) if cs else {"signal": None, "votes": [], "last": {}}
    uid, auid = q.get("uid"), q.get("asset_uid")
    out = {"secid": secid, "kind": kind, "quote": q, "interval": iv, "candles": cs[k0:], "series": {k: r4(v) for k, v in ser.items()},
           "levels": levels(cs) if cs else {"support": [], "resistance": []}, "ta": summ,
           "token": bool(cfg and (cfg.get("token") or "").strip()), "updated": time.time()}
    if kind == "fund":
        try:
            divs = stock_dividends(secid, q["price"], None, cfg, history=False)
        except Exception:  # noqa: BLE001 — дивиденды фонда не обязательны
            divs = {"items": [], "ttm_value": 0, "yield_ttm": None, "next": None, "source": "none"}
        fm = fund_meta(secid, q.get("sector"))
        if q.get("sector") == STK_FUND_OTHER and (fm.get("issue_name") or fm.get("full_name")):   # короткое имя TQBR не подсказало — пробуем полное
            cat = stk_fund_category(secid, (fm.get("issue_name") or "") + " " + (fm.get("full_name") or ""))
            q["sector"] = fm["category"] = cat
        try:
            fm["nav"] = fund_nav(secid, q.get("price"))
        except Exception:  # noqa: BLE001 — СЧА и iNAV не обязательны для карточки
            fm["nav"] = None
        out.update(multiples=None, report=None, dividends=divs, fund=fm)
        return out
    out.update(multiples=stock_multiples(secid, q.get("cap"), auid, cfg), dividends=stock_dividends(secid, q["price"], uid, cfg, history=True),
               report=stock_next_report(uid, cfg, secid))
    return out


# ── скринер ──

STK_CHEAP_PE, STK_HIGH_DIV, STK_FAST_GROWTH = "cheap_pe", "high_div", "fast_growth"
STK_PRESETS = [{"id": STK_CHEAP_PE, "name": "Дешёвые по P/E", "hint": "P/E больше 0 и ниже медианы сектора"},
               {"id": STK_HIGH_DIV, "name": "Высокие дивиденды", "hint": "дивидендная доходность выше 10 %"},
               {"id": STK_FAST_GROWTH, "name": "Быстрый рост", "hint": "рост выручки больше 20 %"}]
STK_SCR_TTL = DAY
STK_SCR_MAX = 250


def stk_median(vals):
    v = sorted(vals)
    n = len(v)
    return None if not n else v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def stk_tags(rows):
    """Каждой строке: pe_sector (медиана P/E сектора, при < 3 значений — по всему рынку) и теги пресетов."""
    pes = {}
    for r in rows:
        if r.get("pe") and r["pe"] > 0:
            pes.setdefault(r["sector"], []).append(r["pe"])
    allm = stk_median([x for v in pes.values() for x in v])
    med = {s: (stk_median(v) if len(v) >= 3 else allm) for s, v in pes.items()}
    for r in rows:
        m = med.get(r["sector"], allm)
        r["pe_sector"] = m
        t = []
        if r.get("pe") and 0 < r["pe"] and m and r["pe"] < m:
            t.append(STK_CHEAP_PE)
        if r.get("div_yield") is not None and r["div_yield"] > 10:
            t.append(STK_HIGH_DIV)
        if r.get("rev_growth") is not None and r["rev_growth"] > 20:
            t.append(STK_FAST_GROWTH)
        r["tags"] = t
    return rows


_stk_scr = {"running": False, "res": None, "t": 0.0, "done": 0, "total": 0, "err": None}
_stk_scr_lock = threading.Lock()


def _stk_scr_pick(cfg=None):
    rows = [r for r in stocks_universe(cfg=cfg) if r.get("cap")]
    rows.sort(key=lambda r: -(r["cap"] or 0))
    return rows[:STK_SCR_MAX]


def stk_screener_build(cfg, progress=None):
    base = _stk_scr_pick(cfg)
    token = bool(cfg and (cfg.get("token") or "").strip())
    api_ok = False
    fund = {}
    srv = None if token else ds_parsed("md/fundamentals")
    if srv:
        fund = {r["secid"]: stk_srv_fund(srv[r["secid"]]) for r in base if srv.get(r["secid"])}
        api_ok = bool(fund)
    if token:
        try:
            for f in TInvest(cfg).asset_fundamentals([r.get("asset_uid") for r in base]):
                fund[f.get("assetUid")] = stk_from_fund(f)
            api_ok = bool(fund)
        except ApiError:
            api_ok = False
    rows = []
    for i, r in enumerate(base):
        m = (fund.get(r["secid"]) if srv else fund.get(r.get("asset_uid"))) if api_ok else None
        if m is None:
            try:
                m = ifrs_multiples(ifrs_fin(r["secid"]), r["cap"])
                m["div_yield"] = None
            except Exception:  # noqa: BLE001
                m = {}
            if progress:
                progress(i + 1, len(base))
        row = {k: r[k] for k in ("secid", "name", "shortname", "sector", "price", "chg_d", "chg_w", "chg_m", "cap", "value_today")}
        row.update({k: m.get(k) for k in ("pe", "pb", "ev_ebitda", "div_yield", "rev_growth", "ni_growth", "roe", "nd_ebitda")})
        rows.append(row)
    return {"rows": stk_tags(rows), "source": ("tinvest-server" if srv else "tinvest") if api_ok else "ifrs", "presets": STK_PRESETS,
            "sectors": sorted({r["sector"] for r in rows}), "updated": time.time()}


def _stk_scr_run(cfg):
    def prog(d, n):
        _stk_scr.update(done=d, total=n)
    try:
        res = stk_screener_build(cfg, prog)
        with _stk_scr_lock:
            _stk_scr.update(res=res, t=time.time(), err=None)
        try:
            store().put("stk_scr_v1", res)
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        _stk_scr["err"] = str(e)[:200]
    finally:
        _stk_scr.update(running=False)


def _stk_scr_server(force):
    """Без своего токена, но сервер данных отдаёт фундаментал: расчёт сразу (без фонового задания smart-lab). None — сервера нет."""
    if ds_parsed("md/fundamentals") is None:
        return None
    key = ("stk_scr_srv",)
    res = None if force else mem_get(key, 300)
    if res is None:
        res = stk_screener_build({})
        if res.get("source") != "tinvest-server":
            return None
        mem_put(key, res)
    return dict(res, loading=False, progress={"done": 0, "total": 0}, error=None, stale_error=None)


def stock_screener(cfg=None, force=False):
    """Скринер акций. С токеном — показатели T-Invest (быстро); без — МСФО smart-lab фоновым заданием (первый расчёт — минуты, кэш сутки).
    -> {rows, source, presets, sectors, updated, loading, progress:{done,total}, error}."""
    if not (cfg and (cfg.get("token") or "").strip()):
        fast = _stk_scr_server(force)
        if fast:
            return fast
    with _stk_scr_lock:
        if _stk_scr["res"] is None and not force:
            old = store().get("stk_scr_v1")
            if old:
                _stk_scr.update(res=old, t=old.get("updated") or 0)
        has_tok = bool(cfg and (cfg.get("token") or "").strip())
        src_ok = not has_tok or (_stk_scr["res"] or {}).get("source") == "tinvest"   # появился токен — пересчитать по T-Invest
        fresh = _stk_scr["res"] is not None and time.time() - _stk_scr["t"] < STK_SCR_TTL and not force and src_ok
        if not fresh and not _stk_scr["running"]:
            _stk_scr.update(running=True, done=0, total=0)
            threading.Thread(target=_stk_scr_run, args=(cfg,), daemon=True).start()
        res, running, err = _stk_scr["res"], _stk_scr["running"], _stk_scr["err"]
        prog = {"done": _stk_scr["done"], "total": _stk_scr["total"]}
    if res is None:
        return {"rows": [], "presets": STK_PRESETS, "sectors": [], "loading": running, "progress": prog, "source": None,
                "error": None if running else (err or "нет данных")}
    return dict(res, loading=running, progress=prog, error=None, stale_error=err)


# ── маршруты ──

def stocks_get(cfg, acc, q, force):
    if q.get("kind") == "funds":
        return {"rows": funds_universe()}
    rows = stocks_universe(force=bool(force), cfg=cfg)
    return {"rows": [{k: r.get(k) for k in ("secid", "isin", "name", "shortname", "sector", "price", "chg_d", "value_today", "cap", "chg_w", "chg_m")} for r in rows]}


def stock_get(cfg, acc, q, force):
    secid = (q.get("secid") or "").strip().upper()
    if not secid:
        raise ApiError("Не указан тикер.", 400)
    key = ("stk_card", secid, q.get("tf") or "D", token_key(cfg))
    if not force:
        hit = mem_get(key, 60)
        if hit:
            return hit
    return mem_put(key, stock_card(secid, q.get("tf") or "D", cfg))


def stock_screener_get(cfg, acc, q, force):
    return stock_screener(cfg, bool(force))


API_GET["/api/stocks"] = stocks_get
API_GET["/api/stock"] = stock_get
API_GET["/api/stock_screener"] = stock_screener_get
