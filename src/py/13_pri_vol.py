

# ── первичка: объёмы размещений («простыня» новых выпусков) ──
# Что нашли в ISS (проверено вживую):
#  * Корпоративные и региональные облигации размещаются на РЫНКЕ ndm (не bonds!), площадка PSAU «Размещение - адрес.»
#    (PAUS — в USD, PACY — в CNY). Размещение ОФЗ и аукционы — рынок bonds, площадки PACT/AUCT/PAYT.
#    Новый выпуск до начала торгов в bonds вообще не виден: /engines/stock/markets/bonds/securities/{secid} пуст.
#  * Сегодняшние обороты: /engines/stock/markets/ndm/boards/PSAU/securities.json (marketdata: VALTODAY — ₽ по цене сделок,
#    VOLTODAY — штуки, NUMTRADES). Это же — список всех бумаг, открытых на площадке размещения (около 80, большинство — «краны»
#    без сделок), поэтому «новый выпуск» отбираем по описанию: /iss/securities/{secid}.json (description: ISSUEDATE — дата
#    начала торгов, ISSUESIZE — объём выпуска в ШТУКАХ, FACEVALUE/INITIALFACEVALUE — номинал, MATDATE).
#  * Дневная история размещения: /iss/history/engines/stock/markets/ndm/boards/PSAU/securities.json?date=YYYY-MM-DD
#    (одна страница ≈ 80 строк; столбцы VALUE — ₽ по цене сделок, VOLUME — штуки, NUMTRADES, WAPRICE, CLOSE).
#    По конкретной бумаге — /iss/history/engines/stock/markets/{ndm|bonds}/securities/{secid}.json (все площадки сразу).
#  * Размещено: ISSUESIZEPLACED (штуки) есть только у бумаг, которые уже торгуются на bonds; для ndm-размещений берём сумму
#    VOLUME по площадке размещения. Объём в номинале = штуки × номинал (VALUE у дисконтных/структурных может быть заметно меньше).

PV_DAYS = 30
PV_PLACE_NDM = ("PSAU", "PAUS", "PACY")
PV_PLACE_BONDS = ("PACT", "AUCT", "PAYT")
PV_PLACE = set(PV_PLACE_NDM) | set(PV_PLACE_BONDS)
PV_BOARD_NAMES = {"PSAU": "размещение", "PAUS": "размещение", "PACY": "размещение", "PACT": "размещение (аукцион)",
                  "AUCT": "размещение (аукцион)", "PAYT": "размещение (аукцион)", "TQCB": "Т+ корп.", "TQOB": "Т+ ОФЗ",
                  "TQIR": "Т+ ПИР", "TQRD": "Т+ Д", "TQOD": "Т+ USD", "TQOE": "Т+ EUR", "TQOY": "Т+ CNY", "TQUD": "Т+ USD Д",
                  "PSOB": "РПС", "PTOB": "РПС с ЦК", "PSDB": "РПС Д"}
PV_DAY_KEY, PV_DESC_KEY, PV_DAYS_KEY = "pv_day1:", "pv_desc1:", "pv_secdays1:"
_pv = {"running": False, "res": None, "t": 0.0, "phase": "", "err": None}
_pv_lock = threading.Lock()
_pv_mem = {}          # короткий кэш по бумагам: ключ -> (время, значение)
PV_ISS = "https://iss.moex.com/iss/"


def pv_msk_now():
    return datetime.now(timezone(timedelta(hours=3)))


def pv_ttl(now=None):
    """Срок жизни живых данных: 5 минут в торговые часы (будни 7:00-23:50 МСК), иначе 30 минут."""
    n = now or pv_msk_now()
    return 300 if n.weekday() < 5 and 7 <= n.hour < 24 else 1800


def pv_num(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def pv_date(v):
    return v if isinstance(v, str) and re.match(r"^\d{4}-\d\d-\d\d$", v) and not v.startswith("0000") else ""


def pv_table(j, name):
    """Таблица ISS как список словарей; отсутствующая или пустая -> []."""
    t = (j or {}).get(name) or {}
    cols = t.get("columns") or []
    return [dict(zip(cols, r)) for r in t.get("data") or []]


def pv_json(url, timeout=30):
    try:
        return json.loads(http_text(url, timeout=timeout))
    except (OSError, ValueError):      # ISS иногда рвёт соединение: одна повторная попытка
        time.sleep(0.5)
        return json.loads(http_text(url, timeout=timeout))


def pv_hist_parse(rows, board_only=None):
    """Строки истории ISS -> компактные записи. Пустые строки (площадка открыта, сделок нет) отбрасываются."""
    out = []
    for r in rows:
        b = r.get("BOARDID")
        d = pv_date(r.get("TRADEDATE"))
        if not d or not r.get("SECID") or (board_only and b not in board_only):
            continue
        v, q, n = pv_num(r.get("VALUE")) or 0.0, pv_num(r.get("VOLUME")) or 0.0, int(pv_num(r.get("NUMTRADES")) or 0)
        if not (v or q or n):
            continue
        out.append({"s": r["SECID"], "b": b, "d": d, "v": round(v, 2), "q": q, "n": n, "w": pv_num(r.get("WAPRICE")),
                    "c": pv_num(r.get("CLOSE")), "y": pv_num(r.get("YIELDCLOSE")) or pv_num(r.get("YIELDATWAP")),
                    "nm": r.get("SHORTNAME"), "f": pv_num(r.get("FACEVALUE"))})
    return out


def pv_paged(url, table, timeout=30, maxpages=30):
    """Все страницы таблицы ISS (по 100 строк)."""
    rows, start = [], 0
    for _ in range(maxpages):
        j = pv_json(url + ("&start=%d" % start if start else ""), timeout)
        part = pv_table(j, table)
        rows += part
        if len(part) < 100:
            break
        start += len(part)
    return rows


_PV_HCOLS = "BOARDID,TRADEDATE,SECID,SHORTNAME,NUMTRADES,VALUE,VOLUME,WAPRICE,CLOSE,YIELDCLOSE,YIELDATWAP,FACEVALUE"


def pv_day_fetch(d):
    """Площадка размещения PSAU за один день (прошедший)."""
    url = (PV_ISS + "history/engines/stock/markets/ndm/boards/PSAU/securities.json?iss.meta=off&iss.only=history"
           "&history.columns=%s&date=%s" % (_PV_HCOLS, d))
    return pv_hist_parse(pv_paged(url, "history"))


def pv_days_cached(dates, errs):
    """Дни окна: прошедшие дни хранятся в базе насовсем (вчерашний — 3 часа, пока площадка может поправить итоги)."""
    st = store()
    today = pv_msk_now().date().isoformat()
    res, need = {}, []
    for d in dates:
        e = st.get(PV_DAY_KEY + d, 3 * 3600 if d >= _day_add(today, -1) else None)
        if e is None:
            need.append(d)
        else:
            res[d] = e
    if need:
        def one(d):
            try:
                return d, pv_day_fetch(d)
            except Exception as ex:  # noqa: BLE001
                return d, str(ex)[:120]
        got = []
        for d, v in pool_map(one, need, workers=8):
            if isinstance(v, list):
                res[d] = v
                got.append((PV_DAY_KEY + d, v))
            else:
                errs.append("история %s: %s" % (d, v))
        if got:
            st.put_many(got)
    return res


def pv_range_fetch(mk, board, d1, d2):
    url = (PV_ISS + "history/engines/stock/markets/%s/boards/%s/securities.json?iss.meta=off&iss.only=history"
           "&history.columns=%s&from=%s&till=%s" % (mk, board, _PV_HCOLS, d1, d2))
    return pv_hist_parse(pv_paged(url, "history"))


def pv_other_boards(d1, d2, errs):
    """Остальные площадки размещения (USD, CNY, аукционы ОФЗ): мелкие, одним запросом за период; кэш на 3 часа."""
    st, out = store(), []
    for mk, b in [("ndm", x) for x in PV_PLACE_NDM[1:]] + [("bonds", x) for x in PV_PLACE_BONDS]:
        k = "pv_rng1:%s:%s" % (mk, b)
        e = st.get(k, 3 * 3600)
        if e is None:
            try:
                e = pv_range_fetch(mk, b, d1, d2)
                st.put(k, e)
            except Exception as ex:  # noqa: BLE001
                errs.append("площадка %s: %s" % (b, str(ex)[:100]))
                e = []
        out += e
    return out


def pv_parse_desc(j):
    m = {r.get("name"): r.get("value") for r in pv_table(j, "description")}
    face = pv_num(m.get("FACEVALUE")) or pv_num(m.get("INITIALFACEVALUE")) or 0.0
    init = pv_num(m.get("INITIALFACEVALUE")) or face
    return {"name": m.get("SHORTNAME") or "", "full": m.get("NAME") or "", "kind": m.get("ISSUENAME") or "", "isin": m.get("ISIN") or "",
            "issued": pv_date(m.get("ISSUEDATE")), "start": pv_date(m.get("STARTDATEMOEX")), "mat": pv_date(m.get("MATDATE")),
            "size": pv_num(m.get("ISSUESIZE")), "face": face, "face0": init, "cur": m.get("FACEUNIT") or "SUR",
            "ftype": m.get("FACEVALUE_TYPE") or "", "emitter": m.get("EMITTER_ID")}


def pv_desc_old(d, cut):
    """Описание выпуска с датой старта раньше окна: дата не меняется и в «первичку» выпуск уже не вернётся — хранить можно насовсем."""
    st = (d or {}).get("issued") or (d or {}).get("start") or ""
    return bool(st) and st < cut


def pv_desc(secid):
    st = store()
    cut = _day_add(pv_msk_now().date().isoformat(), -PV_DAYS)
    e = st.get(PV_DESC_KEY + secid)
    if e is not None and pv_desc_old(e, cut):
        return e
    e = st.get(PV_DESC_KEY + secid, 7 * 86400)
    if e is not None:
        return e
    j = pv_json(PV_ISS + "securities/%s.json?iss.meta=off&iss.only=description&description.columns=name,value" % secid, 25)
    e = pv_parse_desc(j)
    st.put(PV_DESC_KEY + secid, e)
    return e


def pv_issuer_name(full):
    """«Банк ВТБ ПАО КС-4-1328» -> «Банк ВТБ ПАО»: отбрасываем серию в конце для поиска рейтинга."""
    s = re.sub(r"\s+(?:[A-Za-zА-Яа-я0-9\-/]*\d[A-Za-zА-Яа-я0-9\-/.]*)\s*$", "", (full or "").strip())
    return s or (full or "")


def pv_live_parse(j):
    """ndm/bonds: бумаги + marketdata по площадкам -> {secid: [{b, today, vol, n, last, wap, yield, size, placed, ...}]}."""
    sec = {}
    for r in pv_table(j, "securities"):
        sec.setdefault(r.get("SECID"), {})[r.get("BOARDID")] = r
    out = {}
    for m in pv_table(j, "marketdata"):
        sid, b = m.get("SECID"), m.get("BOARDID")
        s = (sec.get(sid) or {}).get(b) or {}
        out.setdefault(sid, []).append({
            "b": b, "today": pv_num(m.get("VALTODAY_RUR")) or pv_num(m.get("VALTODAY")) or 0.0, "vol": pv_num(m.get("VOLTODAY")) or 0.0,
            "n": int(pv_num(m.get("NUMTRADES")) or 0), "last": pv_num(m.get("LAST")), "wap": pv_num(m.get("WAPRICE")),
            "yield": pv_num(m.get("YIELD")) or pv_num(m.get("YIELDATWAPRICE")) or pv_num(m.get("CLOSEYIELD")) or None,
            "status": m.get("TRADINGSTATUS"), "name": s.get("SHORTNAME"), "full": s.get("SECNAME"), "settle": pv_date(s.get("SETTLEDATE")),
            "size": pv_num(s.get("ISSUESIZE")), "placed": pv_num(s.get("ISSUESIZEPLACED")), "face": pv_num(s.get("FACEVALUE")),
            "cpn": pv_num(s.get("COUPONPERCENT")), "ctype": s.get("BONDTYPE"), "mat": pv_date(s.get("MATDATE")),
            "offer": pv_date(s.get("OFFERDATE")), "isin": s.get("ISIN")})
    return out


_PV_LS = "SECID,BOARDID,SHORTNAME,SECNAME,FACEVALUE,SETTLEDATE,MATDATE,OFFERDATE,ISSUESIZE,ISSUESIZEPLACED,COUPONPERCENT,BONDTYPE,ISIN"
_PV_LM = "SECID,BOARDID,VALTODAY,VALTODAY_RUR,VOLTODAY,NUMTRADES,LAST,WAPRICE,YIELD,YIELDATWAPRICE,CLOSEYIELD,TRADINGSTATUS"


def pv_live_board(mk, board):
    j = pv_json(PV_ISS + "engines/stock/markets/%s/boards/%s/securities.json?iss.meta=off&iss.only=securities,marketdata"
                "&securities.columns=%s&marketdata.columns=%s" % (mk, board, _PV_LS, _PV_LM), 40)
    return pv_live_parse(j)


def pv_live_secid(secid):
    """Вторичные торги по бумаге на рынке bonds (все площадки): оборот сегодня, доходность, купон, размещено (ISSUESIZEPLACED)."""
    k = "bm:" + secid
    c = _pv_mem.get(k)
    if c and time.time() - c[0] < pv_ttl():
        return c[1]
    j = pv_json(PV_ISS + "engines/stock/markets/bonds/securities/%s.json?iss.meta=off&iss.only=securities,marketdata"
                "&securities.columns=%s&marketdata.columns=%s" % (secid, _PV_LS, _PV_LM), 25)
    v = pv_live_parse(j).get(secid) or []
    _pv_mem[k] = (time.time(), v)
    return v


def pv_aggregate(day_rows):
    """Записи истории площадок размещения -> по бумаге: сумма штук, ₽, сделок, первый/последний день, дневной ряд."""
    out = {}
    for r in day_rows:
        if r["b"] not in PV_PLACE:
            continue
        a = out.setdefault(r["s"], {"q": 0.0, "v": 0.0, "n": 0, "first": r["d"], "last": r["d"], "name": r.get("nm"), "face": r.get("f"), "days": {}})
        a["q"] += r["q"]
        a["v"] += r["v"]
        a["n"] += r["n"]
        a["first"] = min(a["first"], r["d"])
        a["last"] = max(a["last"], r["d"])
        dd = a["days"].setdefault(r["d"], {"q": 0.0, "v": 0.0, "n": 0})
        dd["q"] += r["q"]
        dd["v"] += r["v"]
        dd["n"] += r["n"]
    return out


def pv_coupon_text(live, desc):
    """(текст, флоатер?) — формулу плавающего купона ISS не отдаёт: показываем тип."""
    ct = (live or {}).get("ctype") or ""
    cp = (live or {}).get("cpn")
    kind = (desc or {}).get("kind") or ""
    if "плавающ" in ct:
        return "флоатер", True
    if cp and cp > 0:
        return ("%.2f" % cp).replace(".", ",") + " %", False
    if "дисконт" in kind.lower():
        return "дисконт", False
    if "структурн" in kind.lower() or "структурн" in ct.lower():
        return "структурная", False
    return "", False


def pv_build_row(secid, desc, agg, today_place, bm, today, rating):
    """Одна строка «простыни». today_place — строки marketdata площадки размещения, bm — marketdata рынка bonds."""
    face = desc.get("face") or desc.get("face0") or 1000.0
    a = agg or {}
    live = None
    if bm:
        live = max(bm, key=lambda x: x.get("today") or 0)
    size_pcs = desc.get("size") or (live or {}).get("size")
    placed_moex = max([x.get("placed") or 0 for x in bm or []] or [0])
    tp_val = sum(x.get("today") or 0 for x in today_place or [])
    tp_vol = sum(x.get("vol") or 0 for x in today_place or [])
    tp_n = sum(x.get("n") or 0 for x in today_place or [])
    trades_pcs = (a.get("q") or 0) + tp_vol
    placed_pcs, src = (placed_moex, "moex") if placed_moex else ((trades_pcs, "trades") if trades_pcs else (0.0, ""))
    sec_today = sum(x.get("today") or 0 for x in bm or [])
    pl_days = sorted(a.get("days") or {})
    start = desc.get("issued") or desc.get("start") or a.get("first") or ""
    if tp_val > 0 or (tp_n > 0):
        status = "placing"
    elif trades_pcs:
        status = "placed"
    else:
        status = "upcoming"
    cpn, flt = pv_coupon_text(live, desc)
    return {"secid": secid, "isin": desc.get("isin") or secid, "name": desc.get("name") or a.get("name") or secid, "full": desc.get("full") or "",
            "rating": rating, "coupon": cpn, "floating": flt, "mat": desc.get("mat") or (live or {}).get("mat") or "",
            "offer": (live or {}).get("offer") or "", "start": start, "first_place": pl_days[0] if pl_days else (today if tp_val > 0 else ""),
            "face": face, "size_pcs": size_pcs, "size_rub": size_pcs * face if size_pcs else None,
            "placed_pcs": placed_pcs, "placed_rub": placed_pcs * face if placed_pcs else None, "placed_src": src,
            "placed_pct": round(100.0 * placed_pcs / size_pcs, 1) if size_pcs and placed_pcs else None,
            "place_value": round((a.get("v") or 0) + tp_val, 2), "place_trades": (a.get("n") or 0) + tp_n,
            "today_place": round(tp_val, 2), "today_sec": round(sec_today, 2), "today": round(tp_val + sec_today, 2),
            "today_trades": tp_n + sum(x.get("n") or 0 for x in bm or []),
            "price": (live or {}).get("wap") or (live or {}).get("last"), "yield": (live or {}).get("yield"),
            "status": status, "cur": (desc.get("cur") or "SUR").replace("SUR", "RUB")}


def pv_upcoming(cal, known_isins, today):
    """Строки календаря Мосбиржи, которых ещё нет среди размещающихся (начало размещения сегодня или позже)."""
    out = []
    for r in cal:
        if r.get("start", "") < today or (r.get("isin") and r["isin"] in known_isins):
            continue
        out.append({"secid": r.get("isin") or "", "isin": r.get("isin") or "", "name": r.get("short") or r.get("issuer") or "",
                    "full": r.get("desc") or "", "rating": r.get("rating"), "coupon": "", "floating": False, "mat": "", "offer": "",
                    "start": r["start"], "first_place": "", "face": None, "size_pcs": None, "size_rub": None, "placed_pcs": 0,
                    "placed_rub": None, "placed_src": "", "placed_pct": None, "place_value": 0, "place_trades": 0, "today_place": 0,
                    "today_sec": 0, "today": 0, "today_trades": 0, "price": None, "yield": None, "status": "upcoming", "cur": "RUB",
                    "book": r.get("book") or "", "end": r.get("end") or ""})
    return out


def _pv_rating(isin, name):
    try:
        r = best_rating(isin, name)
        return r
    except Exception:  # noqa: BLE001
        try:
            return rating_for(name)
        except Exception:  # noqa: BLE001
            return None


def pv_calendar_bg(out):
    """Календарь investmint в фоновом потоке: результат кладём в out (cal/err), пока основной конвейер грузит MOEX."""
    t0 = time.time()
    try:
        out["cal"] = primary_rows() or []
    except Exception as ex:  # noqa: BLE001
        out["err"] = "календарь: %s" % str(ex)[:100]
    out["t"] = time.time() - t0


def pv_bonds_batch():
    """Весь рынок bonds одним запросом (~3,5 тыс. бумаг, ≈1 МБ): {secid: [marketdata-строки по площадкам]}."""
    j = pv_json(PV_ISS + "engines/stock/markets/bonds/securities.json?iss.meta=off&iss.only=securities,marketdata"
                "&securities.columns=%s&marketdata.columns=%s" % (_PV_LS, _PV_LM), 60)
    return pv_live_parse(j)


def pv_compute():
    errs, tm = [], {}
    t0 = time.time()

    def lap(name):
        nonlocal t0
        t1 = time.time()
        tm[name] = round(t1 - t0, 2)
        t0 = t1
    cal_box = {}
    cal_th = threading.Thread(target=pv_calendar_bg, args=(cal_box,), daemon=True)
    cal_th.start()
    now = pv_msk_now()
    today = now.date().isoformat()
    cut = _day_add(today, -PV_DAYS)
    _pv["phase"] = "История площадки размещения"
    dates = [_day_add(today, -i) for i in range(1, PV_DAYS + 1)]
    dates = [d for d in dates if datetime.strptime(d, "%Y-%m-%d").weekday() < 5]
    byday = pv_days_cached(dates, errs)
    day_rows = [r for d in sorted(byday) for r in byday[d]] + pv_other_boards(cut, today, errs)
    agg = pv_aggregate(day_rows)
    lap("history")
    descs = {}

    def d1(s):
        try:
            return s, pv_desc(s)
        except Exception as ex:  # noqa: BLE001
            return s, str(ex)[:100]

    def load_descs(secs, sink):
        for s, v in pool_map(d1, sorted(secs), workers=8):
            sink[s] = v
    pre = set(agg)                                      # описания бумаг с историей размещения грузим параллельно «сегодняшним» запросам
    pre_got = {}
    pre_th = threading.Thread(target=load_descs, args=(pre, pre_got), daemon=True)
    pre_th.start()
    _pv["phase"] = "Обороты сегодня"
    live = {}
    for mk, b in [("ndm", x) for x in PV_PLACE_NDM] + [("bonds", x) for x in PV_PLACE_BONDS]:
        try:
            for sid, ms in pv_live_board(mk, b).items():
                live.setdefault(sid, []).extend(ms)
        except Exception as ex:  # noqa: BLE001
            errs.append("сегодня %s: %s" % (b, str(ex)[:100]))
    bonds_all = None
    try:
        bonds_all = pv_bonds_batch()
    except Exception as ex:  # noqa: BLE001
        errs.append("рынок bonds: %s" % str(ex)[:100])
    lap("live")
    _pv["phase"] = "Календарь размещений"
    cal_th.join(60)
    lap("calendar_wait")
    tm["calendar"] = round(cal_box.get("t") or 0, 2)
    cal = cal_box.get("cal") or []
    if cal_box.get("err"):
        errs.append(cal_box["err"])
    elif "cal" not in cal_box:
        errs.append("календарь размещений investmint: не ответил вовремя")
    elif not cal:
        errs.append("календарь размещений investmint: 0 строк — возможно, изменилась разметка сайта")
    cal_isin = {r["isin"]: r for r in cal if r.get("isin")}
    cand = set(agg)
    for sid, ms in live.items():
        if any((m.get("today") or 0) > 0 or (m.get("n") or 0) > 0 or (m.get("settle") or "") >= cut for m in ms):
            cand.add(sid)
    cand |= set(cal_isin)
    _pv["phase"] = "Описания выпусков (%d)" % len(cand)
    pre_th.join()
    got = dict(pre_got)
    load_descs(cand - set(pre_got), got)
    for s, v in got.items():
        if isinstance(v, dict):
            descs[s] = v
        else:
            errs.append("описание %s: %s" % (s, v))
    lap("desc")
    new = [s for s, d in descs.items() if (d.get("issued") or d.get("start") or "") >= cut]
    _pv["phase"] = "Вторичные торги (%d)" % len(new)
    bms = {}
    if bonds_all is not None:
        for s in new:
            bms[s] = bonds_all.get(s) or []           # нет в рынке bonds — торгов там ещё нет (как пустой ответ по бумаге)
    else:
        def b1(s):
            try:
                return s, pv_live_secid(s)
            except Exception as ex:  # noqa: BLE001
                return s, str(ex)[:100]
        for s, v in pool_map(b1, new, workers=8):
            if isinstance(v, list):
                bms[s] = v
            else:
                errs.append("торги %s: %s" % (s, v))
    lap("secondary")
    rows = []
    for s in new:
        d = descs[s]
        tp = [m for m in live.get(s, []) if m["b"] in PV_PLACE]
        rt = _pv_rating(d.get("isin") or s, pv_issuer_name(d.get("full") or d.get("name")))
        row = pv_build_row(s, d, agg.get(s), tp, bms.get(s), today, rt)
        if row["status"] == "upcoming" and (row["start"] or "") < today:
            continue                                    # открыт на площадке, но сделок не было и даты размещения в будущем нет
        rows.append(row)
    known = {r["isin"] for r in rows} | {r["secid"] for r in rows}
    for r in pv_upcoming(cal, known, today):
        r["rating"] = r["rating"] if r.get("rating") else None
        rows.append(r)
    rows.sort(key=lambda r: (r["status"] != "placing", r["status"] == "upcoming", ""), reverse=False)
    rows.sort(key=lambda r: r.get("start") or "", reverse=True)
    rows.sort(key=lambda r: {"placing": 0, "upcoming": 1}.get(r["status"], 2))
    return {"rows": rows, "today": today, "window": PV_DAYS, "errors": errs[:10], "updated": time.time(), "timing": tm,
            "totals": {"placing": sum(1 for r in rows if r["status"] == "placing"), "today_rub": round(sum(r["today"] for r in rows), 2),
                       "size_rub": round(sum(r["size_rub"] or 0 for r in rows), 2)}}


def _pv_run():
    try:
        res = pv_compute()
        with _pv_lock:
            _pv.update(res=res, t=time.time(), err=None)
    except Exception as e:  # noqa: BLE001
        _pv["err"] = str(e)[:200]
    finally:
        _pv.update(running=False, phase="")


def primary_volumes_payload(force=False):
    with _pv_lock:
        fresh = _pv["res"] is not None and time.time() - _pv["t"] < pv_ttl() and not force
        if not fresh and not _pv["running"]:
            _pv["running"] = True
            threading.Thread(target=_pv_run, daemon=True).start()
        res = _pv["res"]
        running, phase, err = _pv["running"], _pv["phase"], _pv["err"]
    if res is None:
        return {"rows": [], "loading": running, "phase": phase, "error": None if running else (err or "нет данных"), "errors": []}
    return dict(res, loading=running, phase=phase, stale_error=err)


# ── по дням: история торгов выпуска по всем площадкам ──

def pv_days_merge(rows, live_rows, today):
    """Записи истории + сегодняшняя marketdata -> [{d, q, v, n, price, yield, place_v, sec_v, boards:[{b,label,q,v,n}]}] по возрастанию даты."""
    days = {}
    for r in rows:
        d = days.setdefault(r["d"], {"d": r["d"], "q": 0.0, "v": 0.0, "n": 0, "place_v": 0.0, "sec_v": 0.0, "px": None, "y": None, "_pv": -1, "boards": {}})
        d["q"] += r["q"]
        d["v"] += r["v"]
        d["n"] += r["n"]
        if r["b"] in PV_PLACE:
            d["place_v"] += r["v"]
        else:
            d["sec_v"] += r["v"]
        b = d["boards"].setdefault(r["b"], {"b": r["b"], "label": PV_BOARD_NAMES.get(r["b"], r["b"]), "place": r["b"] in PV_PLACE, "q": 0.0, "v": 0.0, "n": 0})
        b["q"] += r["q"]
        b["v"] += r["v"]
        b["n"] += r["n"]
        px = r.get("w") or r.get("c")
        if px and r["v"] > d["_pv"]:
            d["_pv"], d["px"] = r["v"], px
            d["y"] = r.get("y")
        elif d["y"] is None and r.get("y"):
            d["y"] = r["y"]
    for m in live_rows or []:
        if not ((m.get("today") or 0) or (m.get("vol") or 0) or (m.get("n") or 0)):
            continue
        d = days.setdefault(today, {"d": today, "q": 0.0, "v": 0.0, "n": 0, "place_v": 0.0, "sec_v": 0.0, "px": None, "y": None, "_pv": -1, "boards": {}, "live": True})
        d["live"] = True
        d["q"] += m.get("vol") or 0
        d["v"] += m.get("today") or 0
        d["n"] += m.get("n") or 0
        if m["b"] in PV_PLACE:
            d["place_v"] += m.get("today") or 0
        else:
            d["sec_v"] += m.get("today") or 0
        b = d["boards"].setdefault(m["b"], {"b": m["b"], "label": PV_BOARD_NAMES.get(m["b"], m["b"]), "place": m["b"] in PV_PLACE, "q": 0.0, "v": 0.0, "n": 0})
        b["q"] += m.get("vol") or 0
        b["v"] += m.get("today") or 0
        b["n"] += m.get("n") or 0
        px = m.get("wap") or m.get("last")
        if px and (m.get("today") or 0) > d["_pv"]:
            d["_pv"], d["px"] = m.get("today") or 0, px
            d["y"] = m.get("yield") or d["y"]
    out = []
    for k in sorted(days):
        d = days[k]
        d.pop("_pv", None)
        d["boards"] = sorted(d["boards"].values(), key=lambda x: -x["v"])
        for f in ("v", "place_v", "sec_v"):
            d[f] = round(d[f], 2)
        out.append(d)
    return out


def pv_secid_days(secid):
    """История торгов выпуска за всё время (обе рынка: ndm — размещение и РПС, bonds — вторичка) + сегодня."""
    k = "pvd:" + secid
    c = _pv_mem.get(k)
    if c and time.time() - c[0] < pv_ttl():
        return c[1]
    desc = pv_desc(secid)
    frm = desc.get("issued") or desc.get("start") or _day_add(pv_msk_now().date().isoformat(), -PV_DAYS)
    today = pv_msk_now().date().isoformat()
    errs, rows, live = [], [], []
    for mk in ("ndm", "bonds"):
        try:
            rows += pv_hist_parse(pv_paged(PV_ISS + "history/engines/stock/markets/%s/securities/%s.json?iss.meta=off&iss.only=history"
                                           "&history.columns=%s&from=%s&till=%s" % (mk, secid, _PV_HCOLS, frm, today), "history"))
        except Exception as ex:  # noqa: BLE001
            errs.append("%s: %s" % (mk, str(ex)[:100]))
        try:
            j = pv_json(PV_ISS + "engines/stock/markets/%s/securities/%s.json?iss.meta=off&iss.only=securities,marketdata&securities.columns=%s"
                        "&marketdata.columns=%s" % (mk, secid, _PV_LS, _PV_LM), 25)
            live += pv_live_parse(j).get(secid) or []
        except Exception as ex:  # noqa: BLE001
            errs.append("сегодня %s: %s" % (mk, str(ex)[:100]))
    rows = [r for r in rows if r["d"] != today]            # сегодняшний день берём из marketdata (в истории он появляется вечером)
    days = pv_days_merge(rows, live, today)
    face = desc.get("face") or desc.get("face0") or 1000.0
    res = {"secid": secid, "name": desc.get("name"), "face": face, "size_pcs": desc.get("size"), "days": days, "errors": errs, "today": today,
           "total": {"q": sum(d["q"] for d in days), "v": round(sum(d["v"] for d in days), 2), "n": sum(d["n"] for d in days),
                     "place_v": round(sum(d["place_v"] for d in days), 2)}}
    if not errs:
        _pv_mem[k] = (time.time(), res)
    return res


def _api_primary_vol(cfg, acc, q, force):
    return primary_volumes_payload(force)


def _api_primary_days(cfg, acc, q, force):
    secid = (q.get("secid") or "").strip().upper()
    if not re.match(r"^[A-Z0-9]{4,20}$", secid):
        raise ApiError("Неверный код выпуска.", 400)
    return pv_secid_days(secid)


API_GET["/api/primary/volumes"] = _api_primary_vol
API_GET["/api/primary/days"] = _api_primary_days
