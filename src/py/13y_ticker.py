# ═══════════════════════════════ бегущая строка котировок ═══════════════════════════════
# /api/ticker -> {"items":[{id,label,price,chg,unit,kind}], "updated": ts}. Проценты — в процентных пунктах.
# Каждый источник тянется независимо: сбой одного не убирает остальные.

TK_ISS = "https://iss.moex.com/iss/"
TK_BLUE = ("SBER", "GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "YDEX", "T", "PLZL", "VTBR", "MGNT", "TATN", "CHMF", "MTSS")
TK_UA = "Mozilla/5.0 (compatible; tanalytic)"


def tk_f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def tk_table(j, name):
    t = (j or {}).get(name) or {}
    cols = t.get("columns") or []
    return [dict(zip(cols, r)) for r in (t.get("data") or [])]


def tk_item(id_, label, price, chg, unit, kind):
    price = tk_f(price)
    if not price:
        return None
    chg = tk_f(chg)
    return {"id": id_, "label": label, "price": price, "chg": None if chg is None else round(chg, 2), "unit": unit, "kind": kind}


def tk_parse_index(j):
    for r in tk_table(j, "marketdata"):
        it = tk_item("IMOEX", "IMOEX", r.get("CURRENTVALUE"), r.get("LASTCHANGEPRC"), "", "index")
        if it:
            return it
    return None


def tk_parse_stocks(rows):
    by = {r.get("secid"): r for r in rows or []}
    out = []
    for s in TK_BLUE:
        r = by.get(s)
        it = r and tk_item(s, s, r.get("price"), r.get("chg_d"), "₽", "stock")
        if it:
            out.append(it)
    return out


TK_CETS = (("USD000UTSTOM", "USD/RUB", "USD", "fx"), ("CNYRUB_TOM", "CNY/RUB", "CNY", "fx"),
           ("EUR_RUB__TOM", "EUR/RUB", "EUR", "fx"), ("GLDRUB_TOM", "Золото, ₽/г", "GOLD", "metal"))


def tk_parse_cets(j):
    """{id: item}; бумаги без сделок за сессию (USD после санкций) пропускаем — для них есть запасной ЦБ."""
    out = {}
    names = {c[0]: c for c in TK_CETS}
    prev = {r.get("SECID"): tk_f(r.get("PREVPRICE")) for r in tk_table(j, "securities")}
    for r in tk_table(j, "marketdata"):
        c = names.get(r.get("SECID"))
        if not c:
            continue
        nt = tk_f(r.get("NUMTRADES"))
        last = tk_f(r.get("LAST"))
        if not last or (nt is not None and nt <= 0):
            continue
        chg = tk_f(r.get("LASTCHANGEPRC"))
        if chg is None and prev.get(r.get("SECID")):
            chg = (last / prev[r["SECID"]] - 1) * 100
        it = tk_item(c[2], c[1], last, chg, "₽", c[3])
        if it:
            out[c[2]] = it
    return out


def tk_parse_cbr(xml):
    """XML_daily ЦБ -> {'USD': 90.5, ...} (курс за единицу)."""
    out = {}
    for m in re.finditer(r"<Valute[^>]*>(.*?)</Valute>", xml or "", re.S):
        b = m.group(1)
        code = re.search(r"<CharCode>(\w+)</CharCode>", b)
        nom = re.search(r"<Nominal>(\d+)</Nominal>", b)
        val = re.search(r"<Value>([\d.,]+)</Value>", b)
        if code and nom and val:
            out[code.group(1)] = float(val.group(1).replace(",", ".")) / float(nom.group(1))
    return out


def tk_cbr_items(cur, prev, want):
    out = {}
    labels = {"USD": "USD/RUB", "CNY": "CNY/RUB", "EUR": "EUR/RUB"}
    for code in want:
        v = cur.get(code)
        if not v:
            continue
        p = prev.get(code)
        out[code] = tk_item(code, labels[code] + " (ЦБ)", v, (v / p - 1) * 100 if p else None, "₽", "fx")
    return {k: v for k, v in out.items() if v}


def tk_parse_btc(j, src):
    """coingecko: {'bitcoin':{'usd':..,'usd_24h_change':..}}; binance: {'lastPrice','priceChangePercent'}."""
    if src == "coingecko":
        b = (j or {}).get("bitcoin") or {}
        return tk_item("BTC", "Bitcoin", b.get("usd"), b.get("usd_24h_change"), "$", "crypto")
    return tk_item("BTC", "Bitcoin", (j or {}).get("lastPrice"), (j or {}).get("priceChangePercent"), "$", "crypto")


def _tk_get(url, timeout=12):
    return ext_open(url, headers={"User-Agent": TK_UA, "Accept": "application/json"}, timeout=timeout)[1].decode("utf-8", "replace")


def tk_fetch_index():
    return tk_parse_index(json.loads(http_text(TK_ISS + "engines/stock/markets/index/securities/IMOEX.json?iss.meta=off&iss.only=marketdata"
                                               "&marketdata.columns=SECID,CURRENTVALUE,LASTCHANGEPRC", timeout=15)))


def tk_fetch_cets():
    return tk_parse_cets(json.loads(http_text(TK_ISS + "engines/currency/markets/selt/boards/CETS/securities.json?iss.meta=off&iss.only=marketdata,securities"
                                              "&marketdata.columns=SECID,LAST,LASTCHANGEPRC,NUMTRADES&securities.columns=SECID,PREVPRICE", timeout=15)))


def tk_fetch_cbr(want):
    def get(d):
        url = "https://www.cbr.ru/scripts/XML_daily.asp" + ("?date_req=" + d.strftime("%d/%m/%Y") if d else "")
        return tk_parse_cbr(http_bytes(url, 15).decode("windows-1251", "replace"))
    cur = get(None)
    try:
        prev = get(date.today() - timedelta(days=1))
    except Exception:  # noqa: BLE001
        prev = {}
    return tk_cbr_items(cur, prev, want)


def tk_fetch_btc():
    mem = mem_get(("tk_btc",), 60)
    if mem is not None:
        return mem or None
    it = None
    try:
        it = tk_parse_btc(json.loads(_tk_get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,rub&include_24hr_change=true")), "coingecko")
    except Exception:  # noqa: BLE001
        pass
    if not it:
        try:
            it = tk_parse_btc(json.loads(_tk_get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")), "binance")
        except Exception:  # noqa: BLE001
            pass
    mem_put(("tk_btc",), it or {})
    return it


def ticker_payload(force=False):
    ttl = 60 if _stk_trading() else 600
    key = ("tk_payload",)
    hit = None if force else mem_get(key, ttl)
    if hit is not None:
        res = dict(hit)
        btc = tk_fetch_btc()      # BTC торгуется круглосуточно: свой кэш 60 с
        res["items"] = [btc if i["id"] == "BTC" and btc else i for i in hit["items"]]
        if btc and not any(i["id"] == "BTC" for i in res["items"]):
            res["items"].append(btc)
        return res
    def _run(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return None

    idx_it, stk_rows, cets_raw, btc_it = pool_map(
        _run,
        [tk_fetch_index, lambda: tk_parse_stocks(stocks_universe(force)), tk_fetch_cets, tk_fetch_btc],
        workers=4,
    )
    items = []
    if idx_it:
        items.append(idx_it)
    if stk_rows:
        items += stk_rows
    cets = dict(cets_raw or {})
    miss = [c for c in ("USD", "CNY", "EUR") if c not in cets]
    if miss:
        cbr = _run(lambda: tk_fetch_cbr(miss))
        if cbr:
            cets.update(cbr)
    for c in ("USD", "CNY", "EUR", "GOLD"):
        if c in cets:
            items.append(cets[c])
    if btc_it:
        items.append(btc_it)
    res = {"items": items, "updated": time.time()}
    if items:
        mem_put(key, res)
    return res


def _api_ticker(cfg, acc, q, force):
    return ticker_payload(bool(force))


API_GET["/api/ticker"] = _api_ticker
