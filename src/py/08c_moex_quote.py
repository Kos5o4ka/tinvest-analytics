# ═══════════════════════════════ котировки MOEX ISS для бумаг из отчётов брокера (без токена T-Invest) ═══════════════════════════════

MQ_FIND = "https://iss.moex.com/iss/securities.json?q=%s&iss.meta=off&securities.columns=secid,isin,primary_boardid,group,is_traded"
MQ_BOARD = "https://iss.moex.com/iss/engines/stock/markets/%s/boards/%s/securities/%s.json?iss.meta=off&iss.only=securities,marketdata"
MQ_TTL, MQ_MAP_TTL, MQ_ERR_TTL = 15 * 60, 30 * DAY, 10 * 60
MQ_GROUPS = {"stock_shares": ("share", "shares"), "stock_bonds": ("bond", "bonds"), "stock_ppif": ("etf", "shares"),
             "stock_etf": ("etf", "shares"), "stock_dr": ("share", "shares"), "stock_qnv": ("share", "shares")}


def _mq_num(x):
    try:
        v = float(x)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _mq_find(ident):
    """ident (ISIN или тикер) -> {secid, isin, board, type, market} либо None. Маппинг кэшируется на 30 дней, неудача — на 10 минут."""
    st = store()
    key = "mqmap:" + ident
    v = st.get(key, ttl=MQ_MAP_TTL)
    if v is not None:
        if v.get("ok"):
            return v
        if time.time() - v.get("ts", 0) < MQ_ERR_TTL:
            return None
    best = None
    try:
        rows = _bc_table(json.loads(http_text(MQ_FIND % urllib.parse.quote(ident), 20)), "securities")
        for r in rows:
            g = MQ_GROUPS.get(r.get("group") or "")
            if not g or not r.get("primary_boardid") or not r.get("secid"):
                continue
            exact = ident in (str(r.get("isin") or "").upper(), str(r["secid"]).upper())
            score = (exact, bool(r.get("is_traded")))
            if exact and (best is None or score > best[0]):
                best = (score, {"ok": True, "secid": str(r["secid"]).upper(), "isin": str(r.get("isin") or "").upper(),
                                "board": r["primary_boardid"], "type": g[0], "market": g[1]})
    except Exception:  # noqa: BLE001
        best = None
    out = best[1] if best else {"ok": False, "ts": time.time()}
    try:
        st.put(key, out)
    except Exception:  # noqa: BLE001
        pass
    return out if out.get("ok") else None


_MQ_RUB = ("SUR", "RUB", "RUR")


def _mq_cur(x):
    c = str(x or "").strip().upper()
    return "RUB" if not c or c in _MQ_RUB else c


def _mq_quote(m, sec, px):
    """Котировка в рублях: price — ₽ за штуку, nkd — ₽ на облигацию. Облигация: цена в % от номинала и НКД — в валюте номинала
    (FACEUNIT; у замещающих выпусков он USD/CNY даже при торгах в рублях), акция/фонд — в валюте торгов (CURRENCYID).
    Валюта переводится в рубли по курсу ЦБ на сегодня; нет курса — None (лучше без котировки, чем с ценой не в той валюте)."""
    if not px:
        return None
    nkd = 0.0
    if m["type"] == "bond":
        cur = _mq_cur(sec.get("FACEUNIT") or sec.get("CURRENCYID"))
        face = _mq_num(sec.get("FACEVALUE")) or 1000.0
        px = px / 100.0 * face
        nkd = _mq_num(sec.get("ACCRUEDINT")) or 0.0
    else:
        cur = _mq_cur(sec.get("CURRENCYID") or sec.get("FACEUNIT"))
    k = 1.0
    if cur != "RUB":
        k = tax_cbr_rate(cur, date.today().isoformat())
        if not k:
            return None
    res = {"ok": True, "secid": m["secid"], "type": m["type"], "price": px * k, "nkd": nkd * k, "isin": m["isin"]}
    if cur != "RUB":
        res.update(cur=cur, fx=k)
    return res


def _mq_one(ident):
    ident = (ident or "").strip().upper()
    if not ident:
        return ident, None
    try:
        st = store()
        key = "mqquote:" + ident
        v = st.get(key, ttl=MQ_TTL)
        if v is not None and (v.get("ok") or time.time() - v.get("ts", 0) < MQ_ERR_TTL):
            return ident, (v if v.get("ok") else None)
        m = _mq_find(ident)
        if not m:
            return ident, None
        res = None
        try:
            j = json.loads(http_text(MQ_BOARD % (m["market"], m["board"], urllib.parse.quote(m["secid"])), 20))
            sec = (_bc_table(j, "securities") or [{}])[0]
            md = (_bc_table(j, "marketdata") or [{}])[0]
            px = (_mq_num(md.get("LAST")) or _mq_num(md.get("LCURRENTPRICE")) or _mq_num(md.get("MARKETPRICE"))
                  or _mq_num(sec.get("PREVPRICE")) or _mq_num(sec.get("PREVLEGALCLOSEPRICE")))
            res = _mq_quote(m, sec, px)
        except Exception:  # noqa: BLE001
            res = None
        st.put(key, res or {"ok": False, "ts": time.time()})
        if not res:                                    # неудачу держим недолго
            return ident, None
        return ident, res
    except Exception:  # noqa: BLE001
        return ident, None


def moex_quotes(idents):
    """{ident (ISIN/тикер): {secid, type: share|bond|etf, price (₽ за штуку), nkd (₽ на облигацию), isin}}; без сети/данных — пропуск. Не бросает."""
    ids = sorted({(x or "").strip().upper() for x in idents or [] if x})
    if not ids:
        return {}
    try:
        return {i: q for i, q in pool_map(_mq_one, ids) if q}
    except Exception:  # noqa: BLE001
        return {}


def moex_secid(ident):
    """ISIN/тикер -> SECID Мосбиржи (или None)."""
    try:
        ident = (ident or "").strip().upper()
        m = _mq_find(ident) if ident else None
        return m["secid"] if m else None
    except Exception:  # noqa: BLE001
        return None
