# ═══════════════════ мониторинг портфеля: тревоги, ликвидность, история спредов ═══════════════════
# Источники: журнал рейтинговых действий (ratings_log_v1, канал @issuerRatings), рейтинги и статус «под наблюдением»
# из каталога T-Invest, история торгов и описание выпуска на Мосбирже (ISS), кривая КБД по датам.
# Чего программа НЕ видит: факт оплаты купона (ISS его не публикует), поэтому «задержка выплаты» определяется
# только косвенно: флаги дефолта в описании выпуска на Мосбирже, дефолтный рейтинг (D/RD/C), остановка торгов.

MON_DEFAULTS = {"mon_drop5": 3.0, "mon_drop30": 7.0, "mon_spread30": 2.0, "mon_sell_days": 5.0, "mon_offer_days": 30}
MON_SNAP_KEY, MON_CURVE_KEY = "mon_snap_v1", "kbd_curves_v1"
MON_RT_DAYS, MON_SPARK_DAYS, MON_PART = 90, 90, 0.2        # окно рейтинговых событий, окно спарклайна, доля оборота
_mon_lock = threading.Lock()
_SEV = {"high": 0, "medium": 1, "info": 2}


def mon_thresholds(cfg):
    out = {}
    for k, d in MON_DEFAULTS.items():
        try:
            out[k] = float(cfg.get(k, d))
        except (TypeError, ValueError):
            out[k] = d
    return out


def _mon_ymd(n):
    return (date.today() - timedelta(days=n)).isoformat()


def _mon_hist_for(secid):
    """История торгов выпуска (кэш 6 ч в kv) или None."""
    try:
        h = _bc_history(secid)
        return h if h and h.get("d") else None
    except Exception:  # noqa: BLE001
        return None


def _mon_flags(isin):
    """Флаги дефолта из описания выпуска на Мосбирже (кэш 12 ч)."""
    key = "mon_desc_v1_" + isin
    hit = store().get(key, ttl=12 * 3600)
    if hit is not None:
        return hit
    try:
        j = json.loads(http_text("https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description" % isin, timeout=20))
        d = {r[0]: r[2] for r in j["description"]["data"]}
        out = {"default": str(d.get("HASDEFAULT") or "0") == "1", "tech": str(d.get("HASTECHNICALDEFAULT") or "0") == "1",
               "found": bool(d)}
    except Exception:  # noqa: BLE001
        return {"default": False, "tech": False, "found": False}
    store().put(key, out)
    return out


def _mon_ru(d):
    return d[8:] + "." + d[5:7] + "." + d[:4]


def mon_moex_events(bz, offers, today, horizon):
    """События выпуска по данным Мосбиржи (bondization + оферты): погашение, амортизации, оферты в окне [today, today+horizon] дней.
    Только будущие события. -> {'maturity': дата|None, 'events': [{kind: maturity|amort|offer, date, left, ...}], 'next_offer': дата|None}.
    Погашение — последняя дата в графике амортизаций (при его отсутствии — последний купон); остальные даты амортизаций — частичные."""
    end = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=int(horizon))).strftime("%Y-%m-%d")
    bz = bz or {}
    am = {}
    for a in bz.get("amort") or []:
        if a.get("amortdate"):
            am[a["amortdate"]] = a
    cps = [c["coupondate"] for c in bz.get("coupons") or [] if c.get("coupondate")]
    mat = max(am) if am else (max(cps) if cps else None)
    ev = []
    for d, a in sorted(am.items()):
        if today < d <= end:
            ev.append({"kind": "maturity" if d == mat else "amort", "date": d, "pct": a.get("valueprc"), "value": a.get("value")})
    if mat and not am and today < mat <= end:
        ev.append({"kind": "maturity", "date": mat})
    live = [o for o in offers or [] if o.get("status") != "cancelled" and o["date"] > today]
    for d in sorted({o["date"] for o in live if o["date"] <= end}):
        ev.append({"kind": "offer", "date": d, "offer_kind": offer_kind_on(live, d)})
    for e in ev:
        e["left"] = (datetime.strptime(e["date"], "%Y-%m-%d").date() - datetime.strptime(today, "%Y-%m-%d").date()).days
    ev.sort(key=lambda e: e["date"])
    return {"maturity": mat, "events": ev, "next_offer": min((o["date"] for o in live), default=None)}


def mon_event_alert(e):
    """Текст тревоги по событию мосбиржевого графика (погашение, амортизация)."""
    ds, left = _mon_ru(e["date"]), e["left"]
    if e["kind"] == "maturity":
        return "Погашение %s (через %d дн.) — по данным Мосбиржи" % (ds, left)
    part = ""
    if e.get("pct"):
        part = " %s %% номинала" % str(e["pct"]).replace(".", ",")
    return "Амортизация%s %s (через %d дн.) — по данным Мосбиржи" % (part, ds, left)


def mon_clean_issuer(s):
    """Название эмитента из поста агентства: убирает висячие кавычки, ПРОПИСНЫЕ -> обычный регистр (аббревиатуры до 4 букв остаются)."""
    s = re.sub(r"\s+", " ", s or "").strip()
    if s.count("«") != s.count("»"):
        s = s.replace("«", "").replace("»", "").strip()
    if s.isupper():
        s = " ".join(w if len(w) <= 4 or "." in w else w.capitalize() for w in s.split(" "))
    return s


def _mon_curve_one(d):
    j = json.loads(http_text("https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields&date=" + d))
    return d, [[r[2], round(r[3], 3)] for r in sorted(j["yearyields"]["data"], key=lambda r: r[2])]


def _mon_curves(days):
    """Кривые КБД по датам за последние days дней (кэш в kv навсегда; выходные и праздники хранятся пустыми)."""
    st = store()
    cache = st.get(MON_CURVE_KEY) or {}
    need = [_mon_ymd(i) for i in range(1, days + 1) if (date.today() - timedelta(days=i)).weekday() < 5
            and _mon_ymd(i) not in cache]
    if need:
        for d, pts in pool_map(lambda x: _safe(_mon_curve_one, x), need, workers=8):
            if d is not None:
                cache[d] = pts
        keep = _mon_ymd(800)
        cache = {k: v for k, v in cache.items() if k >= keep}
        st.put(MON_CURVE_KEY, cache)
    return cache


def _interp(pts, t):
    if not pts or t is None:
        return None
    if t <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if t <= x1:
            return y0 + (y1 - y0) * (t - x0) / (x1 - x0)
    return pts[-1][1]


def _curve_on(curves, sorted_dates, d):
    """Кривая на дату d: последняя непустая на эту дату или раньше."""
    import bisect
    i = bisect.bisect_right(sorted_dates, d)
    while i > 0:
        i -= 1
        c = curves.get(sorted_dates[i])
        if c:
            return c
    return None


def _at_or_before(ds, target):
    """Индекс последней даты <= target либо None."""
    import bisect
    i = bisect.bisect_right(ds, target) - 1
    return i if i >= 0 else None


def _mon_match(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)           # «ЛК Европлан» ~ «Европлан», но «Золото Селигдара» != «Селигдар»
    return lo <= hi and sum(len(x) for x in lo) >= 5 and all(len(x) <= 2 for x in hi - lo)


def _mon_issuer_keys(row):
    keys = [name_tokens(_bond_query(row.get("name") or ""))]
    b = _tcat_get(row.get("isin") or row.get("ticker"))
    if b:
        for s in (b.get("br"), _bond_query(b.get("n") or "")):
            if s:
                keys.append(name_tokens(s))
    return [k for k in keys if k]


def _mon_rating_state(row, keys, events):
    """Рейтинговое состояние для таблицы: лучший рейтинг, прогноз, флаг «под наблюдением»."""
    rt = row.get("rating")
    watch, outlook, last = False, "", {}
    b = _tcat_get(row.get("isin") or row.get("ticker"))
    if b:
        for ag, lv, dt, fc, w in b["r"]:
            if w:
                watch = True
            if fc and (ag not in last or dt >= last[ag][0]):
                last[ag] = (dt, fc)
    ws = {}
    for e in events:
        if any(_mon_match(set(e["tokens"]), k) for k in keys):
            if e.get("watch") in ("set", "removed"):
                ws[e["agency"]] = e["watch"] == "set"
            if e.get("outlook") and e["agency"] not in last:
                last[e["agency"]] = (e["date"], e["outlook"])
    if any(ws.values()):
        watch = True
    cands = [x for x in (rt or {}).get("all") or []]
    if cands:
        w = max(cands, key=lambda x: RATING_SCALE.index(x["rating"]))
        outlook = (w.get("outlook") or "").split(" · ")[0]
    if not outlook and last:
        outlook = sorted(last.values())[-1][1]
    return {"v": rt["v"] if rt else None, "agency": rt["agency"] if rt else None, "outlook": outlook,
            "watch": watch, "neg": "негатив" in (outlook or "").lower()}


MON_RT_HIGH_DAYS = 30                                      # понижение старше этого срока уже не «высокая» тревога


def _mon_rating_alerts(rows_keys, events, cutoff, today=None):
    """Тревоги по журналу рейтинговых действий: одно событие -> одна тревога на все бумаги этого эмитента.
    Одинаковые действия одного агентства в один день (по эмитенту и по облигациям) склеиваются в одну тревогу.
    Давнее понижение (старше MON_RT_HIGH_DAYS дней) понижается до средней важности."""
    out, seen = [], {}
    old = (datetime.strptime(today, "%Y-%m-%d").date() - timedelta(days=MON_RT_HIGH_DAYS)).isoformat() if today else None
    for e in events:
        if e["date"] < cutoff:
            continue
        et = set(e["tokens"])
        hit = [r for r, keys in rows_keys if any(_mon_match(et, k) for k in keys)]
        if not hit:
            continue
        act, rt, prev = e["action"], e.get("rating"), e.get("prev")
        sev, msg = None, None
        who = "%s: " % e["agency"]
        lvl = "облигации" if e["level"] == "bond" else "эмитент"
        issuer = mon_clean_issuer(e["issuer"])
        if rt in ("D", "C", "CC") or (act == "понижен" and rt in ("CCC",)):
            sev, msg = "high", who + "дефолтный/преддефолтный уровень рейтинга %s (%s)" % (rt, lvl)
        elif act == "понижен":
            sev, msg = "high", who + "рейтинг понижен%s до %s (%s)" % (" с " + prev if prev else "", rt, lvl)
        elif e.get("watch") == "set" or act == "под наблюдением":
            sev, msg = "medium", who + "рейтинг %s взят «под наблюдение» (%s)" % (rt or "", lvl)
        elif act == "прогноз изменён" and (e.get("outlook") or "") == "негативный":
            sev, msg = "medium", who + "прогноз изменён на негативный, рейтинг %s (%s)" % (rt, lvl)
        elif act == "отозван":
            sev = "medium" if e["level"] == "issuer" else "info"
            msg = who + "рейтинг отозван (%s)%s" % (lvl, "; ранее " + prev if prev else "")
        elif act == "повышен":
            sev, msg = "info", who + "рейтинг повышен%s до %s (%s)" % (" с " + prev if prev else "", rt, lvl)
        elif e.get("outlook") == "негативный":
            sev, msg = "info", who + "рейтинг %s %s, прогноз негативный (%s)" % (rt, act, lvl)
        if not sev:
            continue
        if sev == "high" and old and e["date"] < old and rt not in ("D", "C", "CC"):
            sev = "medium"
        ident = (e["agency"], e["date"], act, rt, prev, e.get("watch"), e.get("outlook") if act == "прогноз изменён" else None, tuple(sorted(h.get("isin") or "" for h in hit)))
        if ident in seen:                              # то же действие по другому уровню (эмитент/облигации)
            if lvl not in seen[ident]["_lvl"]:
                seen[ident]["_lvl"].append(lvl)
                seen[ident]["message"] = seen[ident]["_msg"] % "эмитент и облигации"
            continue
        out.append({"id": "rt|%s|%s" % (e["agency"], e["post"]), "severity": sev, "kind": "rating", "date": e["date"],
                    "isin": hit[0].get("isin"), "isins": [h.get("isin") for h in hit], "name": issuer,
                    "bonds": [h.get("name") for h in hit], "message": msg, "url": e.get("url") or
                    "https://t.me/issuerRatings/%s" % e["post"], "_lvl": [lvl], "_msg": msg.replace("(" + lvl + ")", "(%s)")})
        seen[ident] = out[-1]
    for a in out:
        a.pop("_lvl", None)
        a.pop("_msg", None)
    return out


def _mon_snapshots(rows):
    """Ежедневный снимок цены/спреда по ISIN (хранится 400 дней): запасной источник истории спреда."""
    st = store()
    snap = st.get(MON_SNAP_KEY) or {}
    today = date.today().isoformat()
    changed = False
    for r in rows:
        isin = r.get("isin")
        if not isin or r.get("price_pct") is None:
            continue
        d = snap.setdefault(isin, {})
        if today not in d:
            d[today] = [round(r["price_pct"], 3), r.get("spread")]
            changed = True
    keep = _mon_ymd(400)
    if changed:
        for isin in snap:
            snap[isin] = {k: v for k, v in snap[isin].items() if k >= keep}
        st.put(MON_SNAP_KEY, snap)
    return snap


def build_monitor(cfg, acc):
    t0 = time.time()
    th = mon_thresholds(cfg)
    key = ("monitor", token_key(cfg), acc, tuple(sorted(th.items())))
    hit = mem_get(key, 300)
    if hit:
        return hit
    with _mon_lock:
        hit = mem_get(key, 300)
        if hit:
            return hit
        res = _build_monitor(cfg, acc, th, t0)
        mem_put(key, res)
        return res


def _build_monitor(cfg, acc, th, t0):
    tm = {}
    b = build_bonds(cfg, acc)
    tm["bonds"] = round(time.time() - t0, 2)
    rows = [r for r in (b.get("rows") or []) if r.get("isin") and r.get("qty")]
    return _monitor_core(rows, th, t0, tm, [])


def _monitor_core(rows, th, t0, tm, notes, liquidity=True):
    """Проверки мониторинга для произвольного списка бумаг. rows — строки вида build_bonds (isin, name, ticker, value_rub, qty,
    maturity, call, floating, price_pct, dur, spread, ytm, rating). Портфель и список наблюдения идут одним кодом."""
    today = date.today().isoformat()
    # соответствие ISIN -> код на Мосбирже
    t1 = time.time()
    sec = {}
    try:
        for s in screener_rows():
            if s.get("isin"):
                sec[s["isin"]] = s
    except Exception as e:  # noqa: BLE001
        notes.append("Скринер Мосбиржи недоступен: %s" % str(e)[:80])
    tm["screener"] = round(time.time() - t1, 2)
    t1 = time.time()
    secids = {r["isin"]: (sec.get(r["isin"]) or {}).get("id") or r.get("ticker") or r["isin"] for r in rows}
    hists = dict(zip([r["isin"] for r in rows], pool_map(lambda r: _mon_hist_for(secids[r["isin"]]), rows, workers=8)))
    tm["history"] = round(time.time() - t1, 2)
    t1 = time.time()
    flags = dict(zip([r["isin"] for r in rows], pool_map(lambda r: _mon_flags(r["isin"]), rows, workers=8)))
    tm["flags"] = round(time.time() - t1, 2)
    t1 = time.time()
    try:
        curves = _mon_curves(MON_SPARK_DAYS + 40)
    except Exception as e:  # noqa: BLE001
        curves = {}
        notes.append("Кривая КБД по датам недоступна: %s" % str(e)[:80])
    cdates = sorted(curves)
    tm["kbd_curves"] = round(time.time() - t1, 2)
    snap = _mon_snapshots(rows)
    log = store().get(RT_LOG_KEY) or {"events": []}
    events = log.get("events") or []
    if not events:
        notes.append("Журнал рейтинговых действий пока пуст: он наполняется при синхронизации рейтингов (раздел «Облигации» → обновить рейтинги).")
    # окно торгового календаря для среднего оборота
    win_from = _mon_ymd(30)
    cal = set()
    for h in hists.values():
        if h:
            cal.update(d for d in h["d"] if d > win_from)
    ndays = max(len(cal), 15)
    out_rows, alerts = [], []
    rows_keys = []
    for r in rows:
        isin = r["isin"]
        h = hists.get(isin)
        keys = _mon_issuer_keys(r)
        rows_keys.append((r, keys))
        row = {"isin": isin, "name": r.get("name"), "ticker": r.get("ticker"), "value_rub": r.get("value_rub"),
               "qty": r.get("qty"), "maturity": r.get("maturity"), "call": r.get("call"),
               "floating": bool(r.get("floating")), "price_pct": r.get("price_pct"), "flags": []}
        row["rating"] = _mon_rating_state(r, keys, events)
        price = chg5 = chg30 = sp_now = sp_chg = None
        spark = []
        last_d = None
        if h:
            ds, ps, ys, vs = h["d"], h["p"], h["y"], h["v"]
            last_d = ds[-1]
            price = ps[-1]
            for n, nm in ((5, "chg5"), (30, "chg30")):
                i = _at_or_before(ds, _mon_ymd(n))
                if i is not None and ds[i] >= _mon_ymd(n + 10) and ps[i]:
                    v = round((price / ps[i] - 1) * 100, 2)
                    if nm == "chg5":
                        chg5 = v
                    else:
                        chg30 = v
            # спред к КБД по датам: доходность дня минус КБД на дюрации бумаги
            dur = r.get("dur")
            if dur and not r.get("floating") and cdates:
                sp = []
                for d, y in zip(ds, ys):
                    if y is None or d < _mon_ymd(MON_SPARK_DAYS + 35):
                        continue
                    c = _curve_on(curves, cdates, d)
                    k = _interp(c, dur)
                    if k is not None and 0 < y < 80:
                        sp.append((d, round(y - k, 2)))
                if len(sp) >= 5:
                    sd = [x[0] for x in sp]
                    sp_now = sp[-1][1]
                    i = _at_or_before(sd, _mon_ymd(30))
                    if i is not None and sd[i] >= _mon_ymd(40):
                        sp_chg = round(sp_now - sp[i][1], 2)
                    spark = [[d, v] for d, v in sp if d >= _mon_ymd(MON_SPARK_DAYS)]
            tov = sum(v for d, v in zip(ds, vs) if d > win_from)
            avg = tov / ndays
            row["turnover_avg"] = round(avg)
            row["days_to_sell"] = round((r.get("value_rub") or 0) / (MON_PART * avg), 2) if avg > 0 else None
        else:
            row["turnover_avg"] = None
            row["days_to_sell"] = None
        if len(spark) < 5 and isin in snap:        # запасной вариант: накопленные ежедневные снимки
            sp = sorted((d, v[1]) for d, v in snap[isin].items() if v[1] is not None)
            if len(sp) >= 2:
                spark = [[d, v] for d, v in sp if d >= _mon_ymd(MON_SPARK_DAYS)]
                sp_now = sp[-1][1]
        row.update(price=price, chg5=chg5, chg30=chg30, spread=sp_now if sp_now is not None else r.get("spread"),
                   spread_chg30=sp_chg, spark=spark, last_trade=last_d, ytm=r.get("ytm"))
        row["no_history"] = h is None
        base = {"isin": isin, "isins": [isin], "name": r.get("name"), "bonds": [r.get("name")]}
        # --- ценовые тревоги
        parts, sev = [], None
        for chg, lim, lab in ((chg5, th["mon_drop5"], "5 дней"), (chg30, th["mon_drop30"], "30 дней")):
            if chg is not None and chg <= -lim:
                parts.append("%s %% за %s" % (str(chg).replace(".", ","), lab))
                s = "high" if chg <= -2 * lim else "medium"
                sev = s if sev is None or _SEV[s] < _SEV[sev] else sev
        if parts:
            alerts.append(dict(base, id="px|%s|%s" % (isin, today), severity=sev, kind="price", date=last_d or today,
                               message="Цена упала: " + "; ".join(parts) + (" (последняя цена %s %%)" % str(price).replace(".", ",")
                                                                              if price is not None else ""), url=""))
        if sp_chg is not None and sp_chg >= th["mon_spread30"]:
            s = "high" if sp_chg >= 2 * th["mon_spread30"] else "medium"
            alerts.append(dict(base, id="sp|%s|%s" % (isin, today), severity=s, kind="spread", date=last_d or today,
                               message="Спред к КБД вырос на %s п.п. за 30 дней (сейчас %s п.п.)" % (
                                   str(sp_chg).replace(".", ","), str(sp_now).replace(".", ",")), url=""))
        # --- события графика выпуска: даты берём с Мосбиржи (bondization и поля выпуска), а не у брокера
        win = max(int(th["mon_offer_days"]), 30)
        bz = offs = None
        try:
            bz = moex_bondization(isin)
            offs = offers_of_isin(isin, None if bz else r.get("call"), today)
        except Exception:  # noqa: BLE001
            pass
        if bz:
            me = mon_moex_events(bz, offs, today, win)
            row["maturity"] = me["maturity"] or row["maturity"]
            row["call"] = me["next_offer"]
            row["moex_dates"] = True
            for e in me["events"]:
                if e["kind"] == "offer":
                    alerts.append(dict(base, id="of|%s|%s" % (isin, e["date"]), severity="high" if e["left"] <= 7 else "medium",
                                       kind="offer", date=e["date"], message=offer_alert_text(e["offer_kind"], e["left"], _mon_ru(e["date"])) + " — по данным Мосбиржи", url=""))
                else:
                    alerts.append(dict(base, id="%s|%s|%s" % (e["kind"][:2], isin, e["date"]), severity="medium" if e["left"] <= 7 else "info",
                                       kind=e["kind"], date=e["date"], message=mon_event_alert(e), url=""))
        elif offs:                                       # Мосбиржа не отдала график: остаётся дата брокера
            row["call"] = offs[0]["date"]
            for d_ in sorted({o["date"] for o in offs if o["status"] != "cancelled" and o["date"] <= (date.today() + timedelta(days=win)).isoformat()}):
                left = (datetime.strptime(d_, "%Y-%m-%d").date() - date.today()).days
                alerts.append(dict(base, id="of|%s|%s" % (isin, d_), severity="high" if left <= 7 else "medium", kind="offer",
                                   date=d_, message=offer_alert_text(offer_kind_on(offs, d_), left, _mon_ru(d_)) + " (дата брокера)", url=""))
        # --- признаки дефолта
        fl = flags.get(isin) or {}
        if fl.get("default"):
            alerts.append(dict(base, id="df|%s" % isin, severity="high", kind="default", date=today, asof=True,
                               message="По данным Мосбиржи, по выпуску допущен дефолт", url="https://www.moex.com/ru/issue.aspx?code=" + isin))
            row["flags"].append("дефолт")
        elif fl.get("tech"):
            alerts.append(dict(base, id="td|%s" % isin, severity="high", kind="default", date=today, asof=True,
                               message="По данным Мосбиржи, по выпуску был допущен технический дефолт (задержка выплаты). Проверьте, погашена ли задолженность", url="https://www.moex.com/ru/issue.aspx?code=" + isin))
            row["flags"].append("тех. дефолт")
        if last_d and last_d < _mon_ymd(10) and not (r.get("maturity") and r["maturity"] < today):
            alerts.append(dict(base, id="nt|%s|%s" % (isin, last_d), severity="medium", kind="halt", date=last_d,
                               message="Нет торгов с %s: возможна остановка торгов, проверьте выпуск" % (
                                   last_d[8:] + "." + last_d[5:7] + "." + last_d[:4]), url=""))
            row["flags"].append("нет торгов")
        rts = row["rating"]
        if rts["v"] in ("D", "C", "CC"):
            alerts.append(dict(base, id="rd|%s" % isin, severity="high", kind="default", date=today, asof=True,
                               message="Дефолтный/преддефолтный рейтинг %s (%s)" % (rts["v"], rts["agency"]), url=""))
        elif rts["watch"]:
            alerts.append(dict(base, id="wt|%s" % isin, severity="medium", kind="watch", date=today, asof=True,
                               message="Рейтинг эмитента под наблюдением (по данным каталога T-Invest или журнала агентств)", url=""))
        if rts["neg"] and not rts["watch"]:
            alerts.append(dict(base, id="ng|%s" % isin, severity="info", kind="outlook", date=today, asof=True,
                               message="Негативный прогноз по рейтингу (%s)" % (rts["agency"] or ""), url=""))
        # --- ликвидность
        dts = row["days_to_sell"]
        if liquidity and h and (dts is None or dts > th["mon_sell_days"]):
            row["flags"].append("неликвид")
            alerts.append(dict(base, id="lq|%s|%s" % (isin, today[:7]), severity="info", kind="liquidity", date=today, asof=True,
                               message=("Нет оборота за 30 дней: продать позицию быстро не получится" if dts is None else
                                        "Низкая ликвидность: на продажу позиции нужно ~%s дн. (при 20%% дневного оборота)" % str(dts).replace(".", ",")),
                               url=""))
        out_rows.append(row)
    alerts += _mon_rating_alerts(rows_keys, events, _mon_ymd(MON_RT_DAYS), today)
    # дубль «под наблюдением» из каталога не нужен, если журнал уже сообщил о том же эмитенте
    wt_logged = {i for a in alerts if a["kind"] == "rating" for i in a.get("isins") or []}
    alerts = [a for a in alerts if not (a["kind"] in ("watch", "outlook") and a["isin"] in wt_logged)]
    alerts.sort(key=lambda a: (_SEV[a["severity"]], _neg(a["date"])))
    for a in alerts:
        for r in out_rows:
            if r["isin"] in (a.get("isins") or []):
                r["n_" + a["severity"]] = r.get("n_" + a["severity"], 0) + 1
    out_rows.sort(key=lambda r: (-(r.get("n_high") or 0), -(r.get("n_medium") or 0), -(r.get("value_rub") or 0)))
    tm["total"] = round(time.time() - t0, 2)
    return {"updated": time.time(), "thresholds": th, "alerts": alerts, "rows": out_rows,
            "summary": {s: sum(1 for a in alerts if a["severity"] == s) for s in _SEV}, "timings": tm, "notes": notes,
            "log": {"events": len(events), "since": min((e["date"] for e in events), default=None)},
            "cal_days": ndays}


def _neg(d):
    """Ключ для сортировки дат по убыванию."""
    return tuple(-ord(c) for c in d or "")


def monitor_watch_rows(isins):
    """Строки списка наблюдения в формате build_bonds (из строк скринера Мосбиржи и каталога T-Invest)."""
    sec = {}
    for s in screener_rows():
        if s.get("isin"):
            sec[s["isin"]] = s
    rows = []
    for isin in isins:
        s = sec.get(isin)
        if not s:
            continue
        ci = tcat_info(isin) or {}
        rows.append({"isin": isin, "name": s.get("name"), "ticker": s.get("id"), "value_rub": 0, "qty": 1, "maturity": s.get("mat"),
                     "call": s.get("offer"), "call_kind": "put" if s.get("offer") else None, "floating": bool(ci.get("floating")), "price_pct": s.get("price"),
                     "dur": s.get("dur"), "spread": s.get("spread"), "ytm": s.get("yield"),
                     "rating": best_rating(isin, ci.get("name") or s.get("name") or "")})
    return rows


def build_monitor_for(cfg, isins):
    """Те же проверки, что в «Мониторинге», для списка ISIN (без позиции в портфеле: ликвидность и стоимость не считаются)."""
    th = mon_thresholds(cfg)
    isins = sorted(set(i for i in isins if i))
    key = ("monitor_for", tuple(isins), tuple(sorted(th.items())))
    hit = mem_get(key, 300)
    if hit:
        return hit
    with _mon_lock:
        hit = mem_get(key, 300)
        if hit:
            return hit
        t0 = time.time()
        notes = []
        try:
            rows = monitor_watch_rows(isins)
        except Exception as e:  # noqa: BLE001
            rows = []
            notes.append("Скринер Мосбиржи недоступен: %s" % str(e)[:80])
        res = _monitor_core(rows, th, t0, {}, notes, liquidity=False)
        mem_put(key, res)
        return res
