# ═══════════════════ карточка облигации: описание, история, денежный поток, аналоги ═══════════════════

_bc_univ = {"t": 0, "rows": []}
_bc_lock = threading.Lock()
BC_DESC = ("ISSUENAME", "ISSUEDATE", "MATDATE", "ISSUESIZE", "FACEVALUE", "INITIALFACEVALUE", "COUPONFREQUENCY",
           "COUPONPERCENT", "COUPONVALUE", "COUPONDATE", "BOND_TYPE", "BOND_SUBTYPE", "FACEVALUE_TYPE", "LISTLEVEL",
           "ISQUALIFIEDINVESTORS", "HASDEFAULT", "HASTECHNICALDEFAULT", "REGNUMBER", "TYPENAME", "EMITTER_ID")


def _bc_json(url, timeout=25):
    return json.loads(http_text(url, timeout=timeout))


def _bc_desc(isin):
    j = _bc_json("https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description" % isin)
    d = {r[0]: r[2] for r in j["description"]["data"]}
    out = {k: d[k] for k in BC_DESC if d.get(k) not in (None, "")}
    eid = d.get("EMITTER_ID")
    if eid:
        try:
            e = _bc_json("https://iss.moex.com/iss/emitters/%s.json?iss.meta=off&iss.only=emitter" % eid, timeout=15)
            row = dict(zip(e["emitter"]["columns"], (e["emitter"]["data"] or [[]])[0]))
            out["EMITTER"] = row.get("TITLE") or row.get("title")
            out["EMITTER_INN"] = row.get("INN") or row.get("inn")
        except Exception:  # noqa: BLE001
            pass
    return out


def _bc_history(secid):
    key = "bondhist_v1_" + secid
    hit = store().get(key, ttl=6 * 3600)
    if hit:
        return hit
    frm = (date.today() - timedelta(days=370)).isoformat()
    rows, start = [], 0
    while start < 1500:
        j = _bc_json("https://iss.moex.com/iss/history/engines/stock/markets/bonds/securities/%s.json?iss.meta=off"
                     "&history.columns=BOARDID,TRADEDATE,CLOSE,LEGALCLOSEPRICE,WAPRICE,YIELDCLOSE,YIELDATWAP,VALUE"
                     "&from=%s&start=%d" % (secid, frm, start))
        part = _iss_table(j, "history")
        rows += part
        if len(part) < 100:
            break
        start += 100
    boards = defaultdict(int)
    for r in rows:
        boards[r["BOARDID"]] += 1
    main = next((b for b in ("TQCB", "TQOB") if boards.get(b)), max(boards, key=boards.get) if boards else None)
    out = {"d": [], "p": [], "y": [], "v": []}
    for r in sorted((r for r in rows if r["BOARDID"] == main), key=lambda r: r["TRADEDATE"]):
        p = r.get("LEGALCLOSEPRICE") or r.get("CLOSE") or r.get("WAPRICE")
        y = r.get("YIELDCLOSE") or r.get("YIELDATWAP")
        if p is None:
            continue
        out["d"].append(r["TRADEDATE"])
        out["p"].append(round(p, 3))
        out["y"].append(round(y, 2) if y else None)
        out["v"].append(round(r.get("VALUE") or 0))
    if out["d"]:
        store().put(key, out)
    return out


def _bc_norm_table(t):
    if isinstance(t, dict) and "columns" in t:
        return [dict(zip(t["columns"], r)) for r in t["data"]]
    return [x for x in (t or []) if isinstance(x, dict)]


def _bc_flows(isin):
    j = None
    fn = globals().get("moex_bondization")
    if callable(fn):
        try:
            j = fn(isin)
        except Exception:  # noqa: BLE001
            j = None
    if not isinstance(j, dict) or not any(k in j for k in ("coupons", "amortizations", "offers")):
        j = _bc_json("https://iss.moex.com/iss/securities/%s/bondization.json?iss.meta=off&limit=unlimited"
                     "&iss.only=coupons,amortizations,offers" % isin, timeout=30)
    today = date.today().isoformat()
    ev = []
    for c in _bc_norm_table(j.get("coupons")):
        d = c.get("coupondate")
        if d and d >= today:
            ev.append({"d": d, "t": "coupon", "amt": c.get("value_rub") if c.get("value_rub") is not None else c.get("value"),
                       "pct": c.get("valueprc")})
    for a in _bc_norm_table(j.get("amortizations")):
        d = a.get("amortdate")
        if d and d >= today:
            ev.append({"d": d, "t": "redemption" if a.get("data_source") == "maturity" else "amort",
                       "amt": a.get("value_rub") if a.get("value_rub") is not None else a.get("value"),
                       "pct": a.get("valueprc")})
    for o in _bc_norm_table(j.get("offers")):
        d = o.get("offerdate")
        if d and d >= today:
            ev.append({"d": d, "t": "offer", "amt": o.get("value"), "pct": o.get("price")})
    ev.sort(key=lambda e: e["d"])
    return ev


def _bc_mark_est(flows, isin, floating, face):
    """Купоны флоатера без объявленной ставки: подставляем прогноз (ключевая ставка + спред), помечаем est/base/spread."""
    if not floating or not face or not any(e["t"] == "coupon" and e.get("amt") is None for e in flows):
        return False
    bz = moex_bondization(isin)
    est = fl_estimates(bz, date.today().isoformat(), float(face)) if bz else {}
    done = False
    for e in flows:
        x = est.get(e["d"]) if e["t"] == "coupon" and e.get("amt") is None else None
        if x:
            e.update(amt=x["amt"], pct=x["rate"], est=True, base=round(x["base"], 2), spread=round(x["spread"], 2))
            done = True
    return done


def _bc_issuer_key(r):
    t = name_tokens(_bond_query(r.get("full") or r.get("name") or ""))
    return t


def _bc_universe():
    """screener_rows + рейтинг и данные каталога; кэш 10 минут."""
    if time.time() - _bc_univ["t"] < 600 and _bc_univ["rows"]:
        return _bc_univ["rows"]
    with _bc_lock:
        if time.time() - _bc_univ["t"] < 600 and _bc_univ["rows"]:
            return _bc_univ["rows"]
        src = screener_rows()
        out = []
        for r in src:
            e = dict(r)
            e["_isin"] = r.get("isin") or r["id"]
            e["_ci"] = tcat_info(e["_isin"])
            rt = best_rating(e["_isin"], (e["_ci"] or {}).get("name") or r.get("name") or "")
            e["_rt"] = rt
            e["_iss"] = _bc_issuer_key(r)
            out.append(e)
        _bc_univ.update(t=time.time(), rows=out)
        return out


def _bc_lite(e, base_y):
    rt, ci = e["_rt"], e["_ci"] or {}
    return {"isin": e["_isin"], "id": e["id"], "name": e["name"], "yield": e["yield"], "spread": e.get("spread"),
            "dur": e.get("dur"), "rating": rt["v"] if rt else None, "rating_approx": bool(rt and rt["approx"]),
            "sector": ci.get("sector"), "floating": bool(ci.get("floating")), "amort": bool(ci.get("amort")),
            "turn": e.get("turn"), "price": e.get("price"), "mat": e.get("mat"),
            "dy": round(e["yield"] - base_y, 2) if base_y is not None else None}


def _bc_cost(me, e, ri):
    """Расстояние между выпусками для подбора аналогов (меньше = ближе); None, если не аналог. ri: индекс рейтинга me или None."""
    if e["cur"] != "RUB" or not (0 < e["yield"] < 60) or not e.get("dur") or e["dur"] < 0.1:
        return None
    if e["kind"] != me["kind"]:
        return None
    if me["kind"] == "corp" and me["_iss"] and e["_iss"] and (e["_iss"] == me["_iss"]):
        return None
    ert = e["_rt"]
    d = 0.0
    if ri is not None:
        if not ert:
            return None
        n = abs(RATING_SCALE.index(ert["v"]) - ri)
        if n > 2:
            return None
        d += n * 1.0
    elif ert and me["kind"] == "corp":
        d += 0.5
    ci, eci = me["_ci"] or {}, e["_ci"] or {}
    sec, dur = ci.get("sector"), me.get("dur")
    if sec and eci.get("sector") and sec != eci["sector"]:
        d += 0.7
    if dur:
        rel = abs(e["dur"] - dur) / max(dur, e["dur"], 0.5)
        if rel > 0.6:
            return None
        d += rel * 3
    if bool(eci.get("floating")) != bool(ci.get("floating")):
        d += 1.5
    if bool(eci.get("amort")) != bool(ci.get("amort")):
        d += 0.5
    d -= min(1.0, len(str(int(e.get("turn") or 0))) / 9.0) * 0.6
    return d


def _bc_analogs(me, isin):
    """me: запись из _bc_universe (или None). Возвращает (список аналогов, относительная оценка)."""
    uni = _bc_universe()
    if not me:
        return [], None
    rt = me["_rt"]
    ri = RATING_SCALE.index(rt["v"]) if rt else None
    scored = []
    for e in uni:
        if e["_isin"] == isin:
            continue
        d = _bc_cost(me, e, ri)
        if d is not None:
            scored.append((d, e))
    scored.sort(key=lambda x: x[0])
    sps = sorted(e["spread"] for _, e in scored[:30] if e.get("spread") is not None)
    if len(sps) >= 5:      # отсекаем выбросы (дефолтные выпуски, линкеры) относительно медианы ближайших кандидатов
        m0 = sps[len(sps) // 2]
        scored = [x for x in scored if x[1].get("spread") is None or abs(x[1]["spread"] - m0) <= 8]
    top = [_bc_lite(e, me["yield"]) for _, e in scored[:12]]
    rel = None
    sp = [a["spread"] for a in top if a["spread"] is not None]
    if me.get("spread") is not None and len(sp) >= 3:
        sp.sort()
        med = sp[len(sp) // 2] if len(sp) % 2 else (sp[len(sp) // 2 - 1] + sp[len(sp) // 2]) / 2
        diff = round(me["spread"] - med, 2)
        c2 = lambda x: ("%.2f" % x).replace(".", ",")      # noqa: E731
        txt = ("Доходность в пределах разброса аналогов (спред к КБД %s п.п. против медианы %s п.п.)"
               % (c2(me["spread"]), c2(med))) if abs(diff) < 0.25 else \
            ("Облигация %s аналогов: спред к КБД на %s п.п. %s медианы по %d похожим выпускам" %
             ("дешевле" if diff > 0 else "дороже", c2(abs(diff)), "выше" if diff > 0 else "ниже", len(sp)))
        rel = {"median_spread": round(med, 2), "diff": diff, "n": len(sp), "text": txt}
    return top, rel


def _bc_issuer_curve(me):
    """Все торгуемые выпуски того же эмитента (по ключу названия): дюрация -> доходность, плюс КБД для ориентира."""
    key = me.get("_iss")
    pts = []
    if key and me["kind"] == "corp":
        for e in _bc_universe():
            if e["_iss"] == key and e["cur"] == "RUB" and e.get("dur") and e["yield"] > 0:
                rt = e["_rt"]
                pts.append({"isin": e["_isin"], "name": e["name"], "dur": e["dur"], "yield": e["yield"], "spread": e.get("spread"),
                            "rating": rt["v"] if rt else None, "turn": e.get("turn"), "me": e["_isin"] == me["_isin"],
                            "floating": bool((e["_ci"] or {}).get("floating"))})
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p["dur"])
    lo, hi = max(0.0, pts[0]["dur"] - 0.3), pts[-1]["dur"] + 0.5
    kbd = []
    for i in range(13):
        x = lo + (hi - lo) * i / 12
        k = kbd_at(x)
        if k is not None:
            kbd.append([round(x, 2), round(k, 2)])
    return {"points": pts, "kbd": kbd}


def bond_card(isin):
    isin = (isin or "").strip().upper()
    errors = []
    card = {"isin": isin, "found": False, "errors": errors}
    if not re.fullmatch(r"[A-Z0-9]{6,14}", isin):
        errors.append("некорректный ISIN")
        return card
    me = None
    try:
        uni = _bc_universe()
        me = next((e for e in uni if e["_isin"] == isin or e["id"] == isin), None)
    except Exception as e:  # noqa: BLE001
        errors.append("рынок: %s" % str(e)[:120])
        uni = []
    if me:
        isin = me["_isin"]
        card["isin"] = isin
    secid = me["id"] if me else isin

    def run(fn):
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001
            return None, str(e)[:120]
    (desc, e1), (hist, e2), (flows, e3) = pool_map(
        run, [lambda: _bc_desc(isin), lambda: _bc_history(secid), lambda: _bc_flows(isin)], workers=3)
    for lab, er in (("описание", e1), ("история", e2), ("денежный поток", e3)):
        if er:
            errors.append("%s: %s" % (lab, er))
    ci = tcat_info(isin)
    card["catalog"] = ci
    card["desc"] = desc or {}
    card["history"] = hist or {"d": [], "p": [], "y": [], "v": []}
    card["flows"] = flows or []
    try:
        card["offers"] = [o for o in offers_of_isin(isin) if o["status"] != "cancelled"]
        for e in card["flows"]:
            if e["t"] == "offer":
                e["kind"] = offer_kind_on(card["offers"], e["d"])
    except Exception as e:  # noqa: BLE001
        card["offers"] = []
        errors.append("оферты: %s" % str(e)[:120])
    try:
        face = (desc or {}).get("FACEVALUE") or (me or {}).get("nominal")
        if _bc_mark_est(card["flows"], isin, bool((ci or {}).get("floating")), float(face) if face else 0.0):
            info = keyrate_forecast_info()
            card["keyrate"] = {"source": info["source"], "name": info["source_name"], "as_of": info["as_of"]}
    except Exception as e:  # noqa: BLE001
        errors.append("прогноз купонов: %s" % str(e)[:120])
    try:
        rt = (me["_rt"] if me else None) or best_rating(isin, (desc or {}).get("ISSUENAME") or (ci or {}).get("name") or "")
    except Exception as e:  # noqa: BLE001
        rt = None
        errors.append("рейтинг: %s" % str(e)[:120])
    card["rating"] = rt
    if me:
        card["found"] = True
        card["market"] = {k: me.get(k) for k in ("id", "isin", "name", "full", "kind", "cur", "nominal", "price", "yield",
                                                 "dur", "coupon", "next", "mat", "offer", "level", "turn", "trades",
                                                 "zs", "spread", "size")}
        k = kbd_at(me["dur"]) if me.get("dur") else None
        card["kbd"] = round(k, 2) if k is not None else None
        try:
            card["analogs"], card["rel"] = _bc_analogs(me, isin)
        except Exception as e:  # noqa: BLE001
            card["analogs"], card["rel"] = [], None
            errors.append("аналоги: %s" % str(e)[:120])
        try:
            card["issuer_curve"] = _bc_issuer_curve(me)
        except Exception as e:  # noqa: BLE001
            card["issuer_curve"] = None
            errors.append("кривая эмитента: %s" % str(e)[:120])
    else:
        card["market"] = None
        card["analogs"], card["rel"] = [], None
        card["issuer_curve"] = None
        if not errors:
            errors.append("нет торгов на основных режимах Мосбиржи — показаны только справочные данные")
    card["name"] = (me or {}).get("full") or (desc or {}).get("ISSUENAME") or (ci or {}).get("name") or isin
    card["short"] = (me or {}).get("name") or (ci or {}).get("name") or isin
    return card
