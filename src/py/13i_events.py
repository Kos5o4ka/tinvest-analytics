# ═══════════════════════════════ календарь событий ═══════════════════════════════

EV_KINDS = {"cbr": "Заседание ЦБ", "coupon": "Купон", "redemption": "Погашение", "amort": "Амортизация", "dividend": "Дивиденд",
            "offer": "Оферта", "primary": "Размещение", "w_coupon": "Купон (наблюдение)", "w_redemption": "Погашение (наблюдение)",
            "w_offer": "Оферта (наблюдение)"}
# сырые виды выплат из портфеля -> виды календаря (амортизация у брокера приходит как "amortization", у Мосбиржи — "amort")
EV_KIND_ALIAS = {"amortization": "amort", "maturity": "redemption", "repayment": "redemption"}
EV_NOTE = {"coupon": "купонная выплата", "redemption": "погашение облигации", "dividend": "дивиденд", "amort": "частичное погашение номинала"}
EV_MAX_DAYS = 400
CBR_CAL_URL = "https://www.cbr.ru/dkp/cal_mp/"
CBR_CAL_KEY = "cbr_cal_v1"
_RU_MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7, "августа": 8, "сентября": 9,
              "октября": 10, "ноября": 11, "декабря": 12}


def cbr_meetings():
    """Даты заседаний Совета директоров Банка России по ключевой ставке: {"dates": [...], "ok": bool, "error": str}. Кэш 1 день."""
    st = store()
    hit = st.get(CBR_CAL_KEY, ttl=DAY)
    if hit and hit.get("dates"):
        return hit
    try:
        s = http_text(CBR_CAL_URL, timeout=30)
        s = s.replace("&nbsp;", " ").replace("\xa0", " ")
        parts = re.split(r'<div class="date[^"]*">', s)
        dates = set()
        for p in parts[1:]:
            m = re.match(r"\s*(\d{1,2})\s+([а-яё]+)\s+(\d{4})", p)
            if not m or m.group(2) not in _RU_MONTHS:
                continue
            head = p[:1500]
            nxt = head.find('class="date')
            body = head if nxt < 0 else head[:nxt]
            if re.search(r"Заседание Совета директоров", body):
                dates.add(date(int(m.group(3)), _RU_MONTHS[m.group(2)], int(m.group(1))).isoformat())
        if not dates:
            raise ValueError("на странице ЦБ не найдено заседаний")
        out = {"dates": sorted(dates), "ok": True}
        st.put(CBR_CAL_KEY, out)
        return out
    except Exception as e:  # noqa: BLE001
        old = st.get(CBR_CAL_KEY)
        if old and old.get("dates"):
            return dict(old, stale=True)
        return {"dates": [], "ok": False, "error": str(e)[:160]}


def ev_kind(k):
    """Приводит вид события к каноническому (амортизация и т.п.)."""
    k = str(k or "")
    return EV_KIND_ALIAS.get(k, k)


def _ev(d, kind, title, isin=None, amount=None, note="", **kw):
    e = {"date": d, "kind": ev_kind(kind), "title": title, "isin": isin or None, "amount": amount, "note": note}
    e.update(kw)
    return e


EV_BADGE = {"put": "PUT", "call": "CALL", "unknown": "тип не указан"}


def _ru_pct(x):
    return str(x).replace(".", ",")


def offer_events(offs, name, isin, frm, to, pref=""):
    """События по офертам выпуска (offs — результат offer_kinds) в окне [frm, to]. У каждого есть badge (PUT / CALL / тип не указан)
    и label. PUT: открытие приёма заявок, последний день подачи, дата выкупа; CALL: возможное досрочное погашение; тип неизвестен: оферта."""
    out = []
    kind = pref + "offer"
    for o in offs:
        if o.get("status") == "cancelled":
            continue
        k, d = o["kind"], o["date"]
        badge = EV_BADGE.get(k, EV_BADGE["unknown"])
        price = (" по цене %s%% от номинала" % _ru_pct(o["price"])) if o.get("price") else ""
        ps, pe = o.get("period_start"), o.get("period_end")
        win = ("; приём заявок %s – %s" % (_dmy(ps), _dmy(pe))) if ps and pe else ""
        if k == "put":
            if ps and frm <= ps <= to:
                out.append(_ev(ps, kind, name, isin, None, "Открыт приём заявок по пут-оферте; выкуп %s%s" % (_dmy(d), price),
                               badge=badge, label="Открыт приём заявок по пут-оферте", sub="put_open"))
            if pe and frm <= pe <= to:
                out.append(_ev(pe, kind, name, isin, None, "Последний день подачи заявки (через брокера); выкуп %s%s" % (_dmy(d), price),
                               badge=badge, label="Последний день подачи заявки", sub="put_close"))
            if frm <= d <= to:
                out.append(_ev(d, kind, name, isin, None, "Дата выкупа по оферте%s%s" % (price, win),
                               badge=badge, label="Дата выкупа по оферте", sub="put_buyback"))
        elif frm <= d <= to:
            if k == "call":
                out.append(_ev(d, kind, name, isin, None, "Возможное досрочное погашение (колл): решает эмитент, заявку подавать не нужно%s" % price,
                               badge=badge, label="Возможное досрочное погашение (колл)", sub="call"))
            else:
                out.append(_ev(d, kind, name, isin, None, "Оферта%s: тип не указан, проверьте условия в документах выпуска%s" % (price, win),
                               badge=badge, label="Оферта (тип не указан)", sub="unknown"))
    return out


def _day_diff(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def _dmy(d):
    return "%s.%s.%s" % (d[8:10], d[5:7], d[:4]) if d and len(d) == 10 else (d or "")


def _bz_events(isin, name, today, horizon, pref, held=None):
    """События выпуска из данных Мосбиржи: купоны, амортизации, погашение (последняя выплата), оферты."""
    bz = moex_bondization(isin)
    if not bz:
        return []
    out = []
    pay = [(c["coupondate"], c) for c in bz.get("coupons") or [] if c.get("coupondate")]
    am = [(a["amortdate"], a) for a in bz.get("amort") or [] if a.get("amortdate")]
    last_am = max([d for d, _ in am] or [""])
    last_cp = max([d for d, _ in pay] or [""])
    mat = max(last_am, last_cp)
    for d, c in pay:
        if today <= d <= horizon:
            v = c.get("value")
            out.append(_ev(d, pref + "coupon", name, isin, (v * held) if (v and held) else None,
                           ("купон %s на бумагу" % ("%.2f" % v).replace(".", ",") + " " + ("₽" if (c.get("faceunit") or "SUR") in ("SUR", "RUB") else c.get("faceunit") or "")) if v
                           else "размер купона ещё не объявлен"))
    for d, a in am:
        if today <= d <= horizon:
            if d == mat:
                out.append(_ev(d, pref + "redemption", name, isin, None, "погашение выпуска"))
            elif not pref:
                v = a.get("value")
                out.append(_ev(d, "amort", name, isin, (v * held) if (v and held) else None, "частичное погашение номинала"))
    if mat and today <= mat <= horizon and mat not in [d for d, _ in am]:
        out.append(_ev(mat, pref + "redemption", name, isin, None, "погашение выпуска"))
    try:
        opt = moex_bond_options(isin)
    except Exception:  # noqa: BLE001
        opt = None
    out += offer_events(offer_kinds(bz, opt, None, _day_add(today, -1), with_done=True), name, isin, today, horizon, pref)
    return out


def events_payload(cfg, acc, q):
    today = date.today().isoformat()
    frm = (q.get("from") or "").strip() or today[:8] + "01"
    if not re.match(r"^\d{4}-\d\d-\d\d$", frm):
        raise ApiError("Даты нужно указывать в формате ГГГГ-ММ-ДД.", 400)
    to = (q.get("to") or "").strip() or _day_add(frm, 92)
    if not re.match(r"^\d{4}-\d\d-\d\d$", to):
        raise ApiError("Даты нужно указывать в формате ГГГГ-ММ-ДД.", 400)
    try:
        bad = to < frm or _day_diff(frm, to) > EV_MAX_DAYS
    except ValueError:
        raise ApiError("Такой даты не существует.", 400)
    if bad:
        raise ApiError("Период для календаря должен быть не длиннее %d дней." % EV_MAX_DAYS, 400)
    kinds = [ev_kind(k) for k in (q.get("kinds") or "").split(",") if k]
    events, warn, src = [], [], {}
    # 1. заседания Банка России
    cb = cbr_meetings()
    src["cbr"] = bool(cb.get("ok"))
    if not cb.get("ok"):
        warn.append("Календарь заседаний Банка России не удалось получить с сайта cbr.ru (%s). Остальные события показаны." % cb.get("error", "нет связи"))
    for d in cb.get("dates") or []:
        if frm <= d <= to:
            events.append(_ev(d, "cbr", "Заседание Банка России по ключевой ставке", None, None,
                              "решение по ключевой ставке объявляется в 13:30 по Москве"))
    # 2. выплаты и оферты по портфелю
    held = set()
    try:
        rep = build_bonds(cfg, acc)
        src["portfolio"] = True
        by_tk = {r.get("ticker"): r for r in rep["rows"] if r.get("ticker")}
        for p in rep.get("payments") or []:
            if not (frm <= p["date"] <= to):
                continue
            r = by_tk.get(p.get("ticker")) or {}
            pk = ev_kind(p["kind"])
            isin = r.get("isin") if pk != "dividend" else None
            note = EV_NOTE.get(pk) or EV_KINDS.get(pk, "выплата").lower()
            if p.get("est"):
                note += " (оценка)"
            events.append(_ev(p["date"], pk, p["name"], isin, round(p["amount"], 2), note))
        for r in rep["rows"]:
            if r.get("isin") and r.get("qty"):
                held.add(r["isin"])
        rows = [r for r in rep["rows"] if r.get("isin") and r.get("qty")]

        def one(r):
            try:
                bz = moex_bondization(r["isin"])
                try:
                    opt = moex_bond_options(r["isin"])
                except Exception:  # noqa: BLE001
                    opt = None
                offs = offer_kinds(bz or {}, opt, r.get("call"), _day_add(frm, -1), with_done=True)
                out = offer_events(offs, r["name"], r["isin"], frm, to)
                for a in (bz or {}).get("amort") or []:
                    d = a.get("amortdate")
                    if d and frm <= d <= to and a.get("value") and d != max([x.get("amortdate") or "" for x in bz["amort"]] + [""]):
                        out.append(_ev(d, "amort", r["name"], r["isin"], round(a["value"] * r["qty"], 2), "частичное погашение номинала"))
                return out
            except Exception:  # noqa: BLE001
                return []
        have_am = {(e["isin"], e["date"]) for e in events if e["kind"] == "amort"}
        for lst in pool_map(one, rows, workers=8):
            for e in lst:
                if e["kind"] == "amort" and (e["isin"], e["date"]) in have_am:
                    continue
                events.append(e)
    except Exception as e:  # noqa: BLE001
        src["portfolio"] = False
        warn.append("Выплаты и оферты по портфелю не загружены: %s" % str(e)[:140])
    # 3. объявленные размещения
    try:
        for r in primary_rows():
            d = r.get("start")
            if d and frm <= d <= to:
                events.append(_ev(d, "primary", r.get("short") or r.get("issuer"), r.get("isin") or None, None,
                                  ((r.get("desc") or "") + ((" · книга заявок: " + r["book"]) if r.get("book") else "")).strip(" ·") or "начало размещения"))
        src["primary"] = True
    except Exception as e:  # noqa: BLE001
        src["primary"] = False
        warn.append("Размещения не загружены: %s" % str(e)[:100])
    # 4. список наблюдения
    fn = globals().get("watch_isins")
    if fn:
        try:
            ws = [x for x in (fn() or []) if x]
            items = []
            for x in ws:
                if isinstance(x, dict):
                    items.append((x.get("isin"), x.get("name") or x.get("isin")))
                else:
                    items.append((str(x), str(x)))
            items = [(i, n) for i, n in items if i and i not in held][:60]

            def wone(it):
                try:
                    nm = it[1]
                    if nm == it[0]:
                        ci = tcat_info(it[0]) if globals().get("tcat_info") else None
                        nm = (ci or {}).get("name") or it[0]
                    return _bz_events(it[0], nm, frm, to, "w_")
                except Exception:  # noqa: BLE001
                    return []
            for lst in pool_map(wone, items, workers=8):
                events += lst
            src["watch"] = len(items)
        except Exception as e:  # noqa: BLE001
            warn.append("Список наблюдения не загружен: %s" % str(e)[:100])
    if kinds:
        events = [e for e in events if e["kind"] in kinds]
    seen, uniq = {}, []
    for e in sorted(events, key=lambda e: (e["date"], e["kind"], e["title"])):
        k = (e["date"], e["kind"], e["title"], e.get("isin"), e.get("sub"))
        if k in seen:
            if e.get("amount") is not None and seen[k]["amount"] is not None and e["kind"] in ("coupon", "dividend", "redemption", "amort"):
                seen[k]["amount"] = round(seen[k]["amount"] + e["amount"], 2)
            continue
        seen[k] = e
        uniq.append(e)
    return {"account": acc, "from": frm, "to": to, "events": uniq, "kinds": EV_KINDS, "warnings": warn, "sources": src, "today": today}


# ── iCalendar (RFC 5545) ──

def _ics_esc(t):
    return str(t if t is not None else "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def _ics_fold(line):
    """Строки длиннее 75 октетов переносятся (CRLF + пробел), многобайтные символы не режутся."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    out, cur, n = [], "", 0
    for ch in line:
        w = len(ch.encode("utf-8"))
        if n + w > (75 if not out else 74):
            out.append(cur)
            cur, n = "", 0
        cur += ch
        n += w
    out.append(cur)
    return "\r\n ".join(out)


def build_ics(events):
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TAnalytic//Calendar//RU", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:TAnalytic: события", "X-WR-TIMEZONE:Europe/Moscow"]
    for e in events:
        try:
            d0 = datetime.strptime(e["date"], "%Y-%m-%d")
        except ValueError:
            continue
        d1 = d0 + timedelta(days=1)
        uid = hashlib.sha1(("%s|%s|%s|%s%s" % (e["date"], e["kind"], e.get("isin") or "", e["title"], ("|" + e["sub"]) if e.get("sub") else "")).encode("utf-8")).hexdigest()[:24] + "@tinvest-analytics"
        summ = "%s: %s" % (e.get("label") or EV_KINDS.get(e["kind"], e["kind"]), e["title"])
        if e.get("badge"):
            summ += " [%s]" % e["badge"]
        desc = e.get("note") or ""
        if e.get("amount") is not None:
            desc += ("; " if desc else "") + "сумма ≈ %s ₽" % ("{:,.2f}".format(e["amount"]).replace(",", " ").replace(".", ","))
        if e.get("isin"):
            desc += ("; " if desc else "") + "ISIN " + e["isin"]
        lines += ["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + now, "DTSTART;VALUE=DATE:" + d0.strftime("%Y%m%d"),
                  "DTEND;VALUE=DATE:" + d1.strftime("%Y%m%d"), "SUMMARY:" + _ics_esc(summ), "DESCRIPTION:" + _ics_esc(desc),
                  "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(_ics_fold(l) for l in lines) + "\r\n").encode("utf-8")


def _api_events(cfg, acc, q, force):
    return events_payload(cfg, acc, q)


def _api_events_ics(cfg, acc, q, force):
    q = dict(q)
    q.setdefault("from", date.today().isoformat())
    q.setdefault("to", _day_add(q["from"], 366))
    q["kinds"] = q.get("kinds", "")
    p = events_payload(cfg, acc, q)
    return (200, build_ics(p["events"]), "text/calendar; charset=utf-8",
            {"Content-Disposition": 'attachment; filename="tinvest_events.ics"'})


API_GET["/api/events"] = _api_events
API_GET["/api/events.ics"] = _api_events_ics
