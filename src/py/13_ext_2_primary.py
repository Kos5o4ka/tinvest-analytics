# ── первичные размещения (по объявлениям Мосбиржи; сводка investmint.ru) ──

_pri = {"t": 0, "rows": [], "err_t": 0, "err": ""}
PRI_ERR_TTL = 1800      # после отказа investmint не спрашиваем его снова полчаса (сайт закрыл доступ программам — HTTP 403)


# ВАЖНО: placements_parse (и _strip) дублируются в server/tinvest_server.py (эндпоинт /v1/parsed/investmint/placements).
# Менять синхронно; tests/test_parsed.py сверяет результаты на общем HTML-образце.
def placements_parse(s):
    """HTML investmint.ru/bond-placements/ -> список строк календаря размещений (по дате старта). Чистая функция."""
    rows, seen = [], set()
    for tr in re.findall(r"<tr>\s*<td class=\"min-w-56.*?</tr>", s, re.S):
        isin = re.search(r'font-mono text-xs">([A-Z0-9]{12})<', tr)
        issuer = re.search(r'font-medium">(.*?)</div>', tr, re.S)
        desc = re.search(r'text-muted-foreground">(.*?)</div>', tr, re.S)
        start = re.search(r'<time datetime="(\d{4}-\d\d-\d\d)"', tr)
        if not (issuer and start):
            continue
        end = re.search(r"Плановое окончание:\s*([^<]+)<", tr)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        link = re.search(r'href="(https://www\.moex\.com/[^"]+)"', tr)
        key = isin.group(1) if isin else _strip(issuer.group(1)) + start.group(1)
        if key in seen:
            continue
        seen.add(key)
        name = re.sub(r"(?i)\b(общество с ограниченной ответственностью|публичное акционерное общество|акционерное общество)\b", "",
                      _strip(issuer.group(1))).replace('"', "").strip(" ()")
        rows.append({"issuer": _strip(issuer.group(1)), "short": name, "desc": _strip(desc.group(1)) if desc else "",
                     "isin": isin.group(1) if isin else "", "start": start.group(1), "end": _strip(end.group(1)) if end else "",
                     "book": _strip(tds[2]) if len(tds) > 2 else "", "status": _strip(tds[3]) if len(tds) > 3 else "",
                     "link": link.group(1) if link else ""})
    rows.sort(key=lambda r: r["start"])
    return rows


def primary_rows():
    """Календарь будущих размещений (investmint). Ошибка источника -> исключение, но не чаще раза в PRI_ERR_TTL: в промежутке
    повторно бросаем запомненную ошибку, не обращаясь к сайту (вызывающие показывают её или работают без календаря)."""
    now = time.time()
    if now - _pri["t"] < 1800 and _pri["rows"]:
        return _pri["rows"]
    if now - _pri["err_t"] < PRI_ERR_TTL and _pri["err"]:
        raise ApiError(_pri["err"], 502)
    try:
        rows = ds_parsed("investmint/placements", timeout=40)       # разбор на сервере данных; None -> разбираем сами
        if not (isinstance(rows, list) and rows and all(isinstance(r, dict) and r.get("start") for r in rows)):
            rows = placements_parse(http_text("https://investmint.ru/bond-placements/", timeout=40))
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", None)
        _pri.update(err_t=now, err=("investmint.ru закрыл доступ для программ (HTTP %d)" % code) if code in (401, 403, 429)
                    else "investmint.ru не ответил: %s" % (str(e)[:120] or type(e).__name__))
        raise ApiError(_pri["err"], 502)
    _pri.update(t=now, rows=rows, err_t=0, err="")
    return rows


def primary_parse_guide(desc, book=""):
    """Извлекает ориентир купона/доходности (%), срок (лет) и признак флоатера из текста объявления размещения."""
    s = ((desc or "") + " " + (book or "")).replace("\u00a0", " ")
    low = s.lower()
    floater = any(w in low for w in ("флоатер", "кс +", "кс+", "ключев", "ruonia", "плавающ", "переменн"))
    # Ставка купона / ориентир доходности: ищем число перед % (кроме «КС + 2%»)
    guide_y = None
    if not floater:
        for m in re.finditer(r"(?:до|ориентир|купон|ставк\w*|доходност\w*)?[^\d%]{0,20}(\d{1,2}(?:[.,]\d{1,2})?)\s*%", low):
            v = float(m.group(1).replace(",", "."))
            if 4.0 <= v <= 45.0:
                guide_y = v
                break
    # Срок обращения: «3 года», «2,5 лет», «18 мес»
    term = None
    m_yr = re.search(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:год[а]?|лет|г\.)", low)
    if m_yr:
        v = float(m_yr.group(1).replace(",", "."))
        if 0.25 <= v <= 30.0:
            term = v
    else:
        m_mo = re.search(r"(\d{1,3})\s*мес", low)
        if m_mo:
            v = int(m_mo.group(1)) / 12.0
            if 0.2 <= v <= 30.0:
                term = round(v, 2)
    return {"guide_y": guide_y, "term": term, "floater": floater}


def primary_nip_for(row, screener=None, rusfar=None, freeze_days=4):
    """Расчёт премии первички (NIP) к кривой того же эмитента и медиане аналогов по рейтингу/дюрации,
    плюс стоимость заморозки кэша на время сбора заявок (по RUSFAR / КС)."""
    scr = screener or []
    info = primary_parse_guide(row.get("desc"), row.get("book"))
    guide_y = row.get("guide_y") if row.get("guide_y") is not None else info["guide_y"]
    term = row.get("term") if row.get("term") is not None else info["term"]
    floater = bool(row.get("floater") or info["floater"])
    rt = row.get("rating")
    rt_v = rt.get("v") if isinstance(rt, dict) else (rt if isinstance(rt, str) else None)
    bucket = rating_bucket(rt_v) if rt_v else None
    toks = set(name_tokens(row.get("short") or row.get("issuer") or ""))
    # 1. Кривая того же эмитента (торгуемые рублёвые фиксы)
    iss_ys = []
    if toks and scr:
        for b in scr:
            if b.get("cur") not in (None, "RUB") or not (b.get("yield") and 0 < b["yield"] < 60):
                continue
            bt = set(name_tokens(b.get("name") or ""))
            if bt and (toks <= bt or bt <= toks or len(toks & bt) >= max(1, min(len(toks), len(bt)))):
                d_b = b.get("dur")
                if term is None or d_b is None or abs(d_b - term) <= 1.8:
                    iss_ys.append(b["yield"])
    # 2. Медиана аналогов по рейтингу и сроку
    peer_ys = []
    if bucket and bucket != "нет рейтинга" and scr:
        for b in scr:
            if b.get("kind") != "corp" or b.get("cur") not in (None, "RUB") or not (b.get("yield") and 0 < b["yield"] < 60):
                continue
            br = b.get("rating")
            br_v = br.get("v") if isinstance(br, dict) else (br if isinstance(br, str) else None)
            if rating_bucket(br_v) != bucket:
                continue
            d_b = b.get("dur")
            if term is not None and d_b is not None and abs(d_b - term) > 1.2:
                continue
            peer_ys.append(b["yield"])
    iss_y = round(_med(iss_ys), 2) if iss_ys else None
    peer_y = round(_med(peer_ys), 2) if peer_ys else None
    nip_iss = round((guide_y - iss_y) * 100) if (guide_y is not None and iss_y is not None) else None
    nip_peer = round((guide_y - peer_y) * 100) if (guide_y is not None and peer_y is not None) else None
    nip_bp = nip_iss if nip_iss is not None else nip_peer
    ref_src = "issuer" if nip_iss is not None else ("peer" if nip_peer is not None else None)
    rate_ref = rusfar if rusfar is not None else 16.0
    freeze_pct = round((rate_ref / 100.0) * (max(0, freeze_days) / 365.0) * 100.0, 3)
    freeze_drag_bp = round(freeze_pct / max(0.5, term or 2.0) * 100.0)
    net_nip_bp = (nip_bp - freeze_drag_bp) if nip_bp is not None else None
    return {"guide_y": guide_y, "term": term, "floater": floater, "bucket": bucket,
            "issuer_y": iss_y, "issuer_n": len(iss_ys), "peer_y": peer_y, "peer_n": len(peer_ys),
            "nip_issuer_bp": nip_iss, "nip_peer_bp": nip_peer, "nip_bp": nip_bp, "ref_src": ref_src,
            "freeze_days": freeze_days, "freeze_rate": round(rate_ref, 2),
            "freeze_cost_pct": freeze_pct, "freeze_drag_bp": freeze_drag_bp, "net_nip_bp": net_nip_bp}


def primary_payload():
    cal_error = None
    try:
        rows = primary_rows()
    except Exception as e:  # noqa: BLE001
        rows, cal_error = [], str(e)[:200]      # без календаря экран всё равно показывает размещения Мосбиржи и калькулятор
    scr = _scr.get("rows") or []
    if not scr:
        try:
            screener_payload()
            scr = _scr.get("rows") or []
        except Exception:  # noqa: BLE001
            scr = []
    rusfar = None
    try:
        kr = key_rate_series()
        if kr:
            rusfar = kr[-1][1]
    except Exception:  # noqa: BLE001
        pass
    out_rows = []
    for r in rows:
        item = dict(r)
        rt = rating_for(item["short"])
        item["rating"] = rt
        item["nip"] = primary_nip_for(item, scr, rusfar)
        out_rows.append(item)
    # Справочные медианы доходности по рейтинговым группам (для интерактивного калькулятора NIP)
    peer_med = {}
    if scr:
        by_b = {}
        for b in scr:
            if b.get("kind") == "corp" and b.get("cur") in (None, "RUB") and b.get("yield") and 0 < b["yield"] < 60:
                br = b.get("rating")
                bv = rating_bucket(br.get("v") if isinstance(br, dict) else br)
                if bv != "нет рейтинга":
                    by_b.setdefault(bv, []).append(b["yield"])
        peer_med = {k: round(_med(v), 2) for k, v in by_b.items() if v}
    try:
        primary_snapshot(out_rows)
    except Exception:  # noqa: BLE001
        pass
    return {"rows": out_rows, "updated": _pri["t"], "rusfar": rusfar, "peer_medians": peer_med, "cal_error": cal_error}



# ── ключевая ставка ЦБ и КБД Мосбиржи (любые сроки из сетки кривой) ──

# v2: на каждую дату вся сетка {срок: доходность}; v1 хранил только 2 года (используем как запас, пока v2 докачивается)
KBD_KEY, KBD_OLD_KEY, KEY_KEY = "kbd_grid_v2", "kbd2y_v1", "keyrate_v1"
# ── снимки объявленных размещений (накопление: позже можно сравнить ориентир и итог) ──

PRI_SNAP_KEY = "pri_snap_v1"
_snap_lock = threading.Lock()


def primary_snapshot(rows):
    """Раз в день сохраняет список объявленных размещений; если состав и статусы не изменились — только отмечает проверку."""
    slim = [{"isin": r.get("isin"), "short": r.get("short"), "desc": r.get("desc"), "start": r.get("start"), "end": r.get("end"),
             "book": r.get("book"), "status": r.get("status"), "rating": (r.get("rating") or {}).get("v")} for r in rows]
    if not slim:
        return
    st = store()
    today = date.today().isoformat()
    with _snap_lock:
        d = st.get(PRI_SNAP_KEY) or {"days": {}}
        days = d.setdefault("days", {})
        last = days[max(days)] if days else None
        if last == slim and d.get("checked") == today:
            return
        if last != slim:
            days[today] = slim
        d["checked"] = today
        for k in sorted(days)[:-400]:
            days.pop(k, None)
        st.put(PRI_SNAP_KEY, d)


# ── первичка против вторички: как торгуются выпуски, размещённые за последние 12 месяцев ──

PRI_ISS_KEY, PRI_H_PREFIX, PRI_MAX, PRI_DAYS = "pri_issue_v1", "prih1:", 700, 365
_pri_h = {"running": False, "phase": "", "done": 0, "total": 0, "fin": 0, "err": None, "memo": (0, None)}
HIST_URL = ("https://iss.moex.com/iss/history/engines/stock/markets/bonds/securities/%s.json?iss.meta=off"
            "&iss.only=history,history.cursor&history.columns=BOARDID,TRADEDATE,VALUE,NUMTRADES,WAPRICE,LEGALCLOSEPRICE,CLOSE,"
            "YIELDCLOSE,YIELDATWAP&from=%s&till=%s&start=%d")


def _pri_dates(secid):
    j = json.loads(http_text("https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description"
                             "&description.columns=name,value" % secid, timeout=25))
    m = {r[0]: r[1] for r in j["description"]["data"]}
    ok = lambda v: v if v and re.match(r"^\d{4}-\d\d-\d\d$", v) and not v.startswith("0000") else ""  # noqa: E731
    return [ok(m.get("ISSUEDATE")), ok(m.get("STARTDATEMOEX"))]


def _day_add(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def _pri_history(secid, d0, today):
    """Цена и доходность в 1-й день торгов, через 7 и 30 дней. Цена — % от номинала (средневзвешенная по основной площадке дня)."""
    till = min(today, _day_add(d0, 50))
    rows, start = [], 0
    while start < 400:
        j = json.loads(http_text(HIST_URL % (secid, d0, till, start), timeout=30))
        t = j["history"]
        part = [dict(zip(t["columns"], r)) for r in t["data"]]
        rows += part
        if len(part) < 100:
            break
        start += 100
    best = {}
    for r in rows:
        px = r.get("WAPRICE") or r.get("LEGALCLOSEPRICE") or r.get("CLOSE")
        if not px or not r.get("TRADEDATE"):
            continue
        cur = best.get(r["TRADEDATE"])
        if cur is None or (r.get("VALUE") or 0) > (cur.get("VALUE") or 0):
            best[r["TRADEDATE"]] = dict(r, px=px)
    days = sorted(best)
    out = {"d0": None, "p0": None, "y0": None, "p7": None, "y7": None, "p30": None, "y30": None, "t": time.time()}
    if days:
        f = days[0]
        if f <= _day_add(d0, 14):
            out.update(d0=f, p0=round(best[f]["px"], 2), y0=best[f].get("YIELDCLOSE") or best[f].get("YIELDATWAP"))
            for k, n in (("7", 7), ("30", 30)):
                lo, hi = _day_add(f, n), _day_add(f, n + 7)
                c = [x for x in days if lo <= x <= hi]
                if c:
                    out["p" + k] = round(best[c[0]]["px"], 2)
                    out["y" + k] = best[c[0]].get("YIELDCLOSE") or best[c[0]].get("YIELDATWAP")
            out["done"] = today >= _day_add(f, 40)
    out["n_days"] = len(days)
    # выпуск без сделок вообще (ещё не торговался) — перепроверим позже
    out["done"] = bool(out.get("done"))
    return out


def _pri_candidates():
    st = store()
    iss = st.get(PRI_ISS_KEY) or {}
    cut = _day_add(date.today().isoformat(), -PRI_DAYS)
    c = []
    for sid, (a, b) in iss.items():
        ref = b or a
        if ref and ref >= cut:
            c.append((ref, sid))
    c.sort(reverse=True)
    return iss, [(sid, ref) for ref, sid in c[:PRI_MAX]]


def _pri_run():
    try:
        st = store()
        st_rows = _scr["rows"] or screener_rows()
        uni = {r["id"]: r for r in st_rows}
        iss = st.get(PRI_ISS_KEY) or {}
        miss = [s for s in uni if s not in iss]
        _pri_h.update(phase="Узнаю даты размещения выпусков", done=0, total=len(miss))
        for k in range(0, len(miss), 200):
            part = miss[k:k + 200]

            def one(s):
                try:
                    return s, _pri_dates(s)
                except Exception:  # noqa: BLE001
                    return s, None
            for s, v in pool_map(one, part, workers=8):
                if v is not None:
                    iss[s] = v
            st.put(PRI_ISS_KEY, iss)
            _pri_h["done"] = min(len(miss), k + 200)
        iss, cand = _pri_candidates()
        cand = [(s, ref) for s, ref in cand if s in uni]
        today = date.today().isoformat()
        todo = []
        for s, ref in cand:
            e = st.get(PRI_H_PREFIX + s)
            if e and (e.get("done") or time.time() - e.get("t", 0) < 12 * 3600):
                continue
            todo.append((s, ref))
        _pri_h.update(phase="Загружаю историю торгов новых выпусков", done=0, total=len(todo))

        def hist(x):
            try:
                return x[0], _pri_history(x[0], x[1], today)
            except Exception:  # noqa: BLE001
                return x[0], None
        for k in range(0, len(todo), 40):
            res = pool_map(hist, todo[k:k + 40], workers=8)
            st.put_many([(PRI_H_PREFIX + s, v) for s, v in res if v is not None])
            _pri_h["done"] = min(len(todo), k + 40)
        _pri_h["fin"] = time.time()
        _pri_h["err"] = None
    except Exception as e:  # noqa: BLE001
        _pri_h["err"] = str(e)[:200]
    finally:
        _pri_h.update(running=False, phase="", memo=(0, None))


def primary_stats_start(force=False):
    with _rt_lock:
        if _pri_h["running"]:
            return
        if not force and time.time() - _pri_h["fin"] < 6 * 3600:
            return
        _pri_h["running"] = True
    threading.Thread(target=_pri_run, daemon=True).start()


def _grp_stats(items):
    p0 = [x["p0"] for x in items if x["p0"] is not None]
    p7 = [x["p7"] for x in items if x["p7"] is not None]
    p30 = [x["p30"] for x in items if x["p30"] is not None]
    dn = [x["now"] - x["p0"] for x in items if x["now"] is not None and x["p0"] is not None]
    abv = lambda arr: round(100.0 * sum(1 for v in arr if v > 100.0) / len(arr), 1) if arr else None  # noqa: E731
    return {"n": len(items), "p0": _med(p0), "p7": _med(p7), "p30": _med(p30), "n30": len(p30),
            "above0": abv(p0), "above7": abv(p7), "above30": abv(p30),
            "below30": round(100.0 * sum(1 for v in p30 if v < 100) / len(p30), 1) if p30 else None,
            "d_now": _med(dn)}


def primary_stats_payload():
    memo = _pri_h["memo"]
    if memo[1] is not None and time.time() - memo[0] < 120 and not _pri_h["running"]:
        return dict(memo[1], loading=False)
    primary_stats_start()
    st = store()
    iss, cand = _pri_candidates()
    uni = {r["id"]: r for r in _scr["rows"]}
    items = []
    for sid, ref in cand:
        e = st.get(PRI_H_PREFIX + sid)
        r = uni.get(sid)
        if not e or not r or e.get("p0") is None:
            continue
        rt, ci = None, None
        try:
            ti = globals().get("tcat_info")
            ci = ti(r.get("isin")) if ti and r.get("isin") else None
            rt = best_rating(r.get("isin"), (ci or {}).get("name") or r["name"]) if r["kind"] == "corp" else None
        except Exception:  # noqa: BLE001
            rt = None
        sector = (ci or {}).get("sector") if r["kind"] == "corp" else None
        sane = lambda v, lo, hi: v if v is not None and lo <= v <= hi else None  # noqa: E731
        now_ok = r.get("price") if (r.get("yield") or 0) > 0 else None       # без доходности цена ненадёжна (индексируемый номинал и т. п.)
        if not (80 <= e["p0"] <= 120):
            continue
        items.append({"secid": sid, "isin": r.get("isin"), "name": r["name"], "kind": r["kind"], "d0": e["d0"], "p0": e["p0"], "y0": e.get("y0"),
                      "p7": sane(e.get("p7"), 50, 150), "p30": sane(e.get("p30"), 50, 150), "y30": e.get("y30"),
                      "now": sane(now_ok, 10, 150), "ynow": r.get("yield"),
                      "rating": rt["v"] if rt else None, "bucket": "ОФЗ" if r["kind"] == "ofz" else rating_bucket(rt["v"] if rt else None),
                      "sector": sector})
    by_b, by_s = {}, {}
    for x in items:
        by_b.setdefault(x["bucket"], []).append(x)
        if x["sector"]:
            by_s.setdefault(x["sector"], []).append(x)
    order = ["ОФЗ"] + MKT_BUCKETS + ["нет рейтинга"]
    buckets = [dict(_grp_stats(by_b[b]), bucket=b) for b in order if b in by_b]
    sectors = sorted((dict(_grp_stats(v), sector=k) for k, v in by_s.items() if len(v) >= 3), key=lambda g: -g["n"])[:12]
    aged = [x for x in items if x["now"] is not None and x["d0"] <= _day_add(date.today().isoformat(), -7)]
    aged.sort(key=lambda x: x["now"] - x["p0"])
    trim = lambda x: dict(x, delta=round(x["now"] - x["p0"], 2))  # noqa: E731
    by_m = {}
    for x in items:
        by_m.setdefault(x["d0"][:7], []).append(x)
    months = [dict(_grp_stats(v), m=k) for k, v in sorted(by_m.items())]
    snaps = (st.get(PRI_SNAP_KEY) or {}).get("days") or {}
    d30 = _day_add(date.today().isoformat(), -30)
    d90 = _day_add(date.today().isoformat(), -90)
    win30 = _grp_stats([x for x in items if (x.get("d0") or "") >= d30])
    win90 = _grp_stats([x for x in items if (x.get("d0") or "") >= d90])
    res = {"all": _grp_stats(items), "win30": win30, "win90": win90, "buckets": buckets, "sectors": sectors, "months": months,
           "worst": [trim(x) for x in aged[:8]], "best": [trim(x) for x in aged[::-1][:8]],
           "universe": len(cand), "ready": len(items), "snap_days": len(snaps), "updated": _pri_h["fin"], "err": _pri_h["err"]}
    if not _pri_h["running"]:
        _pri_h["memo"] = (time.time(), res)
    return dict(res, loading=_pri_h["running"], phase=_pri_h["phase"], done=_pri_h["done"], total=_pri_h["total"])


def _api_primary_stats(cfg, acc, q, force):
    return primary_stats_payload()


API_GET["/api/primary/stats"] = _api_primary_stats


