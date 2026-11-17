# ═══════════════ раскрытие информации эмитентов: клиент (факты с сервера данных, объём в рынке, потоки эмитента, техдефолты) ═══════════════
# Факты разбирает сервер данных (disclosure/facts, disclosure/defaults); здесь — только потребление: объём выпуска в обращении,
# рублёвый эквивалент будущих выплат эмитента по всем его выпускам, лента дефолтов. Сервер выключен/недоступен -> пустые списки.

DISC_TTL, DISC_ERR_TTL = 6 * 3600, 15 * 60
DISC_KIND_RU = {"coupon_paid": "Выплата купона", "coupon_declared": "Ставка купона", "default": "Неисполнение обязательства",
                "buyback_result": "Итоги выкупа"}
DISC_OBL_RU = {"coupon": "Купон", "amortization": "Амортизация", "redemption": "Погашение", "offer": "Выкуп по оферте", "other": "Обязательство"}
DISC_FX_RUB = ("", "RUB", "RUR", "SUR")


def _disc_num(x):
    try:
        return None if x is None or isinstance(x, bool) else float(x)
    except (TypeError, ValueError):
        return None


def _disc_ru(n):
    return ("{:,.0f}".format(n)).replace(",", " ")


def disc_facts(isin=None, inn=None, kind=None):
    """Факты раскрытия по ISIN или ИНН, новые сверху: [{doc_id, title, published, url, isin, inn, kind, event_date, due_date, conf, data}].
    Кэш в kv: 6 ч, ошибка/выключенный сервер — 15 мин. Пусто, если сервер данных недоступен."""
    isin = (isin or "").strip().upper() or None
    inn = (inn or "").strip() or None
    if not isin and not inn:
        return []
    params = {"isin": isin} if isin else {"inn": inn}
    if kind:
        params["kind"] = kind
    key = "disc1:%s:%s" % (isin or inn, kind or "")
    st = store()
    hit = st.get(key)
    if isinstance(hit, dict) and time.time() - hit.get("ts", 0) < (DISC_TTL if hit.get("ok") else DISC_ERR_TTL):
        return hit.get("data") or []
    try:
        res = ds_parsed("disclosure/facts", params)
    except Exception:  # noqa: BLE001
        res = None
    ok = isinstance(res, list)
    data = [x for x in res if isinstance(x, dict)] if ok else []
    st.put(key, {"ok": ok, "ts": time.time(), "data": data})
    return data


def _disc_issue_desc(isin):
    """Объём выпуска из описания Мосбиржи: {issue_size, placed, face, cur, name}; кэш сутки. {} при ошибке."""
    isin = (isin or "").strip().upper()
    if not isin:
        return {}
    key = "disc_desc1:" + isin
    hit = store().get(key, ttl=DAY)
    if hit is not None:
        return hit
    try:
        j = json.loads(http_text("https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description" % isin, 20))
        d = {r[0]: r[2] for r in j["description"]["data"]}
    except Exception:  # noqa: BLE001
        return {}
    n = lambda k: (int(_disc_num(d.get(k))) if _disc_num(d.get(k)) else None)      # noqa: E731
    out = {"issue_size": n("ISSUESIZE"), "placed": n("ISSUESIZEPLACED"), "face": _disc_num(d.get("FACEVALUE")),
           "cur": d.get("FACEUNIT") or "SUR", "name": d.get("SHORTNAME") or d.get("NAME") or isin}
    if d:
        store().put(key, out)
    return out


def _disc_fdate(f):
    d = f.get("data") or {}
    return d.get("due_date") or d.get("date") or f.get("due_date") or f.get("event_date") or (f.get("published") or "")[:10] or None


def _disc_conf(f):
    d = f.get("data") or {}
    c = d.get("conf") if d.get("conf") is not None else f.get("conf")
    return _disc_num(c) or 0.0


def bond_outstanding(isin, today=None, desc=None):
    """Сколько бумаг выпуска в обращении: по последнему раскрытию (купон -> число бумаг), иначе по объёму выпуска Мосбиржи.
    -> {qty, issue_size, placed, share, method, as_of, coupon_no, doc_url, buybacks_after, conf}."""
    isin = (isin or "").strip().upper()
    today = today or date.today().isoformat()
    try:
        facts = disc_facts(isin=isin)
    except Exception:  # noqa: BLE001
        facts = []
    try:
        desc = desc or _disc_issue_desc(isin) or {}
    except Exception:  # noqa: BLE001
        desc = {}
    size, placed = desc.get("issue_size"), desc.get("placed")
    if desc.get("ISSUESIZE") is not None or desc.get("ISSUESIZEPLACED") is not None:       # передан сырой словарь ISS (_bc_desc)
        size = int(_disc_num(desc.get("ISSUESIZE")) or 0) or None
        placed = int(_disc_num(desc.get("ISSUESIZEPLACED")) or 0) or None
    out = {"qty": None, "issue_size": size, "placed": placed, "share": None, "method": None, "as_of": None, "coupon_no": None,
           "doc_url": None, "buybacks_after": 0, "conf": None}

    def dated(kind):
        rows = [f for f in facts if f.get("kind") == kind and isinstance(f.get("data"), dict)]
        rows = [f for f in rows if (_disc_fdate(f) or "") <= today]
        return sorted(rows, key=lambda f: _disc_fdate(f) or "", reverse=True)
    pick = None
    for f in dated("coupon_paid"):
        d = f["data"]
        if _disc_conf(f) < 0.5:
            continue
        if d.get("qty") is not None and _disc_num(d["qty"]) is not None:
            pick = (f, int(d["qty"]), "coupon_explicit")
        elif d.get("qty_derived") is not None and (d.get("checks") or {}).get("qty_integer"):
            pick = (f, int(d["qty_derived"]), "coupon_derived")
        if pick:
            break
    if not pick:
        for f in dated("coupon_declared"):
            d = f["data"]
            if d.get("qty_derived") is not None and (d.get("checks") or {}).get("qty_integer"):
                pick = (f, int(d["qty_derived"]), "declared_derived")
                break
    if pick:
        f, qty, method = pick
        as_of = _disc_fdate(f)
        n_bb = 0
        for b in dated("buyback_result"):
            bd = b["data"].get("date") or b.get("event_date") or (b.get("published") or "")[:10]
            if as_of and bd and bd > as_of:
                n_bb += 1
                qb = _disc_num(b["data"].get("qty_bought"))
                if qb:
                    qty = max(0, qty - int(qb))
        if size and qty > size:
            qty = size
        out.update(qty=qty, method=method, as_of=as_of, coupon_no=f["data"].get("coupon_no"), doc_url=f.get("url"),
                   buybacks_after=n_bb, conf=_disc_conf(f))
    elif placed:
        out.update(qty=placed, method="issue_placed", conf=0.3)
    elif size:
        out.update(qty=size, method="issue_size", conf=0.2)
    if out["qty"] is not None and size:
        out["share"] = round(out["qty"] / float(size), 4)
    return out


def disc_brief(f):
    """Краткая строка по факту для карточки: {date, kind, label, text, url, title}."""
    d = f.get("data") or {}
    k = f.get("kind")
    bits = []
    if k == "coupon_paid":
        if d.get("coupon_no"):
            bits.append("купон №%s" % d["coupon_no"])
        if d.get("total") is not None:
            bits.append("выплачено %s ₽" % _disc_ru(d["total"]))
        q = d.get("qty") if d.get("qty") is not None else d.get("qty_derived")
        if q is not None:
            bits.append("%s шт." % _disc_ru(q))
    elif k == "coupon_declared":
        if d.get("coupon_no"):
            bits.append("купон №%s" % d["coupon_no"])
        if d.get("undetermined"):
            bits.append("ставка не определена" + (": " + d["formula"] if d.get("formula") else ""))
        elif d.get("per_bond") is not None:
            bits.append("%s ₽ на бумагу" % ("%.2f" % d["per_bond"]).replace(".", ","))
        elif d.get("rate") is not None:
            bits.append("ставка %s %%" % ("%g" % d["rate"]).replace(".", ","))
    elif k == "default":
        bits.append("технический дефолт" if d.get("status") == "technical" else "дефолт")
        bits.append(DISC_OBL_RU.get(d.get("obligation"), "обязательство").lower() + (" №%s" % d["coupon_no"] if d.get("coupon_no") else ""))
        if d.get("amount") is not None:
            bits.append("%s ₽" % _disc_ru(d["amount"]))
    elif k == "buyback_result":
        if d.get("qty_bought") is not None:
            bits.append("выкуплено %s шт." % _disc_ru(d["qty_bought"]))
        bits.append({"put": "по требованию владельцев", "issuer": "по соглашению"}.get(d.get("basis"), ""))
    return {"date": (f.get("published") or "")[:10] or _disc_fdate(f), "kind": k, "label": DISC_KIND_RU.get(k, k),
            "text": ", ".join(b for b in bits if b), "url": f.get("url"), "title": f.get("title")}


def disclosure_for_bond(isin, desc=None, n=5):
    facts = [f for f in disc_facts(isin=isin) if f.get("kind") in DISC_KIND_RU]
    return {"outstanding": bond_outstanding(isin, desc=desc), "facts": [disc_brief(f) for f in facts[:n]], "n_facts": len(facts)}


# ───────────────────────── денежные потоки эмитента ─────────────────────────

def _disc_add_month(ym, k):
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + k
    return "%04d-%02d" % (y + m // 12, m % 12 + 1)


def _disc_days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def _disc_bond_flows(isin, today, last_ym, warns):
    """Будущие потоки одного выпуска в рублях на ВСЕ бумаги: [{d, t: coupon|amort|redemption|put|call, amt, est}] + qty/method."""
    bz = moex_bondization(isin)
    if not bz:
        warns.append("%s: нет графика выплат Мосбиржи" % isin)
        return None
    o = bond_outstanding(isin, today)
    qty = o.get("qty")
    if not qty:
        warns.append("%s: не удалось определить число бумаг" % isin)
        return None
    desc = _disc_issue_desc(isin) or {}
    face = desc.get("face") or 0.0
    cur = (desc.get("cur") or "SUR").upper()
    fx = 1.0
    if cur not in DISC_FX_RUB:
        fx = tax_cbr_rate(cur, today)
        if not fx:
            warns.append("%s: нет курса ЦБ для %s, выпуск пропущен" % (isin, cur))
            return None
    decl = {}
    try:
        for f in disc_facts(isin=isin, kind="coupon_declared"):
            d = f.get("data") or {}
            dd = d.get("due_date") or f.get("due_date")
            if dd and not d.get("undetermined") and _disc_conf(f) >= 0.5:
                pb = _disc_num(d.get("per_bond"))
                if pb is None and d.get("rate") and d.get("period_from") and d.get("period_to") and face:
                    pb = face * d["rate"] / 100.0 * max(_disc_days(d["period_from"], d["period_to"]), 0) / 365.0
                if pb:
                    decl.setdefault(dd, pb)
    except Exception:  # noqa: BLE001
        pass
    try:
        est = fl_estimates(bz, today, float(face), None) if face else {}
    except Exception:  # noqa: BLE001
        est = {}
    in_h = lambda d: bool(d) and today <= d and d[:7] <= last_ym        # noqa: E731
    am = sorted((a["amortdate"], _disc_num(a.get("value"))) for a in bz.get("amort") or [] if a.get("amortdate"))
    last_am = am[-1][0] if am else None
    cps = sorted((c["coupondate"], _disc_num(c.get("value"))) for c in bz.get("coupons") or [] if c.get("coupondate"))
    flows, known = [], [v for _, v in cps if v]
    last_known = [v for d, v in cps if v and d <= today]
    prev = last_known[-1] if last_known else (known[-1] if known else None)
    for d, v in cps:
        if not in_h(d):
            if v:
                prev = v
            continue
        e = False
        if not v:
            near = [x for x in decl if abs(_disc_days(x, d)) <= 4]
            if near:
                v = decl[near[0]]
            elif d in est:
                v, e = est[d]["amt"], True
            elif prev:
                v, e = prev, True
        else:
            prev = v
        if v:
            flows.append({"d": d, "t": "coupon", "amt": v * qty * fx, "est": e})
    for d, v in am:
        if in_h(d) and v:
            flows.append({"d": d, "t": "redemption" if d == last_am else "amort", "amt": v * qty * fx, "est": False})

    def face_on(d):
        return max(face - sum(v for da, v in am if v and today < da < d), 0.0)
    try:
        opt = moex_bond_options(isin) or {}
    except Exception:  # noqa: BLE001
        opt = {}
    calls = [d for d in opt.get("call") or [] if in_h(d)]
    put_seen = set()
    for of in bz.get("offers") or []:
        d = of.get("offerdate")
        if not in_h(d) or d in put_seen:
            continue
        if d in (opt.get("call") or []) and d not in (opt.get("put") or []):       # дата только колл — не пут
            continue
        put_seen.add(d)
        px = _disc_num(of.get("price")) or 100.0
        flows.append({"d": d, "t": "put", "amt": face_on(d) * px / 100.0 * qty * fx, "est": False})
    for d in calls:
        flows.append({"d": d, "t": "call", "amt": face_on(d) * qty * fx, "est": False})
    return {"flows": flows, "qty": qty, "method": o.get("method"), "call_date": min(calls) if calls else None}


def issuer_cashflows(inn, horizon_months=25, today=None):
    """Месячный ряд будущих выплат эмитента по всем торгуемым выпускам в рублях (число бумаг x выплата на бумагу)."""
    inn = (inn or "").strip()
    today = today or date.today().isoformat()
    n = max(1, int(horizon_months))
    first = today[:7]
    mkeys = [_disc_add_month(first, i) for i in range(n)]
    months = {m: {"m": m, "coupon": 0.0, "amort": 0.0, "redemption": 0.0, "put": 0.0, "call": 0.0, "est": False, "est_amt": 0.0,
                  "after_call": False, "by_bond": {}, "call_by_bond": {}, "parts": {t: {} for t in ("coupon", "amort", "redemption", "put")},
                  "est_by_bond": {}} for m in mkeys}
    warns, bonds, dates = [], [], set()
    try:
        lst = [b for b in _iss_bonds_of(inn) if b.get("traded") and b.get("isin")]
    except Exception as e:  # noqa: BLE001
        lst = []
        warns.append("список выпусков эмитента недоступен: %s" % str(e)[:80])

    def one(b):
        w = []
        try:
            return b, _disc_bond_flows(b["isin"], today, mkeys[-1], w), w
        except Exception as e:  # noqa: BLE001
            return b, None, w + ["%s: %s" % (b["isin"], str(e)[:80])]
    for b, res, w in pool_map(one, lst, workers=4) if lst else []:
        warns += w
        if not res:
            continue
        bonds.append({"isin": b["isin"], "secid": b.get("secid"), "name": b.get("name") or b["isin"], "qty": res["qty"],
                      "method": res["method"], "call_date": res["call_date"]})
        for f in res["flows"]:
            m = months.get(f["d"][:7])
            if not m:
                continue
            a = round(f["amt"], 2)
            dates.add(f["d"])
            m[f["t"]] += a
            if f["t"] == "call":
                m["call_by_bond"][b["isin"]] = round(m["call_by_bond"].get(b["isin"], 0.0) + a, 2)
                continue
            m["by_bond"][b["isin"]] = round(m["by_bond"].get(b["isin"], 0.0) + a, 2)
            pt = m["parts"][f["t"]]
            pt[b["isin"]] = round(pt.get(b["isin"], 0.0) + a, 2)
            if f["est"]:
                m["est_by_bond"][b["isin"]] = round(m["est_by_bond"].get(b["isin"], 0.0) + a, 2)
                m["est"] = True
                m["est_amt"] += a
            if res["call_date"] and f["d"] > res["call_date"]:
                m["after_call"] = True
    series = []
    for k in mkeys:
        m = months[k]
        for x in ("coupon", "amort", "redemption", "put", "call", "est_amt"):
            m[x] = round(m[x], 2)
        series.append(m)
    name = None
    try:
        em = issuer_of(bonds[0]["isin"]) if bonds else None
        name = (em or {}).get("short") or (em or {}).get("title")
    except Exception:  # noqa: BLE001
        pass
    pay = sum(m["coupon"] + m["amort"] + m["redemption"] for m in series)
    return {"inn": inn, "name": name or inn, "months": series, "bonds": bonds, "warnings": warns,
            "totals": {"payments": round(pay, 2), "call": round(sum(m["call"] for m in series), 2),
                       "put": round(sum(m["put"] for m in series), 2)},
            "dates": len(dates), "n_months": sum(1 for m in series if m["coupon"] or m["amort"] or m["redemption"] or m["put"] or m["call"]),
            "today": today}


# ───────────────────────── лента техдефолтов ─────────────────────────

_DFL_PAY_OF = {"coupon": ("coupon", "coupon+amortization", "coupon+redemption"),
               "amortization": ("amortization", "coupon+amortization"),
               "redemption": ("redemption", "coupon+redemption")}


def _dfl_executed(isin, f):
    """Дата исполнения просроченного обязательства по раскрытию о выплате (coupon_paid) того же ISIN, вышедшему не раньше
    сообщения о неисполнении. Купон: тот же номер и paid_pct >= 100 (или не указан). Амортизация/погашение: payment того же вида
    (в т.ч. «купон + амортизация»), выплата не позднее срока не считается — нужна публикация после срока обязательства.
    None — не найдено."""
    d = f.get("data") or {}
    ob = d.get("obligation")
    if ob not in _DFL_PAY_OF:
        return None
    if ob == "coupon" and not d.get("coupon_no"):
        return None
    due = d.get("due_date") or f.get("due_date") or ""
    since = (f.get("published") or "")[:10]
    for p in sorted(disc_facts(isin=isin, kind="coupon_paid"), key=lambda x: x.get("published") or ""):
        pd_ = p.get("data") or {}
        pub = (p.get("published") or "")[:10]
        if pd_.get("paid_pct") is not None and pd_["paid_pct"] < 100:
            continue
        if ob == "coupon":
            if pd_.get("coupon_no") == d["coupon_no"] and pub >= since:
                return pub or _disc_fdate(p)
        elif pd_.get("payment") in _DFL_PAY_OF[ob] and pub and pub >= since and (not due or pub >= due):
            return pub
    return None


def _dfl_ok_date(d):
    return bool(d) and isinstance(d, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) is not None and not d.startswith("0000")


def dfl_last_due(bz, qty, today):
    """Последнее обязательство по графику Мосбиржи с датой строго раньше today (выплата в сам день ещё не просрочена): {date, obligation, amount, parts}.
    bz — moex_bondization (coupons/amort/offers), qty — число бумаг в обращении (None -> суммы не считаем).
    Несколько выплат в один день склеиваются («Купон №5 + амортизация»); последняя амортизация (или последний купон, если
    амортизаций нет) = «Погашение». None, если ни одной даты в прошлом нет."""
    bz = bz or {}
    cps = sorted((c["coupondate"], c.get("value")) for c in bz.get("coupons") or [] if _dfl_ok_date(c.get("coupondate")))
    ams = sorted((a["amortdate"], a.get("value")) for a in bz.get("amort") or [] if _dfl_ok_date(a.get("amortdate")))
    ofs = sorted({o["offerdate"] for o in bz.get("offers") or [] if _dfl_ok_date(o.get("offerdate"))})
    mat = ams[-1][0] if ams else (cps[-1][0] if cps else None)
    days = [d for d, _ in cps if d < today] + [d for d, _ in ams if d < today] + [d for d in ofs if d < today]
    if not days:
        return None
    d = max(days)
    parts, amt, known = [], 0.0, False
    for i, (cd, v) in enumerate(cps):
        if cd == d:
            parts.append("Купон №%d" % (i + 1))
            if v and qty:
                amt += float(v) * qty
                known = True
    for ad, v in ams:
        if ad == d:
            parts.append("Погашение" if ad == mat else "Амортизация")
            if v and qty:
                amt += float(v) * qty
                known = True
    if d in ofs:
        parts.append("Оферта")
    txt = parts[0]
    for x in parts[1:]:
        txt += " + " + (x[0].lower() + x[1:] if x != "Оферта" else "оферта")
    return {"date": d, "obligation": txt, "amount": round(amt, 2) if known else None, "parts": parts}


def _dfl_schedule_row(isin, today=None):
    """Просроченное обязательство по графику Мосбиржи для бумаги с флагом: dfl_last_due с числом бумаг из описания выпуска."""
    today = today or date.today().isoformat()
    bz = moex_bondization(isin)
    if not bz:
        return None
    desc = _disc_issue_desc(isin) or {}
    qty = desc.get("placed") or desc.get("issue_size")
    return dfl_last_due(bz, qty, today)


def defaults_feed(since=None, isins=None, schedule=False):
    """Лента неисполненных обязательств: сообщения эмитентов (сервер данных) + флаги Мосбиржи по бумагам из isins.
    [{date, status, issuer, inn, isin, obligation, amount, executed, basis, url, date_est}], новые сверху.
    schedule=True: строки по флагу Мосбиржи получают дату/обязательство/сумму из графика выплат (date_est=True); без него даты нет
    (так ленту берут тревоги — их ключи дедупликации не должны меняться с датой)."""
    since = since or (date.today() - timedelta(days=30)).isoformat()
    try:
        raw = ds_parsed("disclosure/defaults", {"since": since})
    except Exception:  # noqa: BLE001
        raw = None
    raw = [f for f in raw if isinstance(f, dict)] if isinstance(raw, list) else []

    def one(f):
        d = f.get("data") or {}
        isin = f.get("isin")
        name = None
        try:
            em = issuer_of(isin) if isin else None
            name = (em or {}).get("short") or (em or {}).get("title")
        except Exception:  # noqa: BLE001
            pass
        try:
            ex = _dfl_executed(isin, f) if isin else None
        except Exception:  # noqa: BLE001
            ex = None
        obls = d.get("obligations") or [{"obligation": d.get("obligation"), "amount": d.get("amount")}]
        out = []
        for o in obls:            # одно сообщение может описывать несколько обязательств (купон + частичное погашение) — по строке на каждое
            ob = DISC_OBL_RU.get(o.get("obligation"), "Обязательство")
            num = " №%s" % d["coupon_no"] if d.get("coupon_no") and o.get("obligation") == "coupon" else ""
            out.append({"date": (f.get("published") or "")[:10] or None, "due_date": d.get("due_date") or f.get("due_date"),
                        "status": "default" if d.get("status") == "default" else "technical", "issuer": name or f.get("title") or "",
                        "inn": f.get("inn"), "isin": isin, "obligation": ob + num,
                        "amount": o.get("amount"), "executed": ex, "basis": "Сообщение эмитента", "url": f.get("url"), "date_est": False})
        return out
    rows = [r for part in (pool_map(one, raw[:300], workers=6) if raw else []) for r in part]
    have = {r["isin"] for r in rows if r.get("isin")}
    extra = [i for i in dict.fromkeys(isins or []) if i and i not in have]

    def flag(isin):
        try:
            fl = _mon_flags(isin)
            if not (fl.get("tech") or fl.get("default")):
                return None
            em = issuer_of(isin) or {}
            row = {"date": None, "due_date": None, "status": "default" if fl.get("default") else "technical",
                   "issuer": em.get("short") or em.get("title") or isin, "inn": em.get("inn"), "isin": isin, "obligation": "",
                   "amount": None, "executed": None, "basis": "Флаг Мосбиржи", "url": None, "date_est": False}
            if schedule:
                try:
                    due = _dfl_schedule_row(isin)
                except Exception:  # noqa: BLE001
                    due = None
                if due:
                    row.update(date=due["date"], due_date=due["date"], obligation=due["obligation"], amount=due["amount"], date_est=True)
            return row
        except Exception:  # noqa: BLE001
            return None
    rows += [r for r in (pool_map(flag, extra, workers=6) if extra else []) if r]
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    return rows


# ── фоновый обход всего рынка: у Мосбиржи нет списка бумаг с флагом дефолта, поэтому проверяем описание каждого выпуска ──

DFL_MKT_KEY, DFL_MKT_TTL, DFL_UNI_KEY = "dfl_market_v1", 12 * 3600, "dfl_universe_v1"
_DFL_SCAN = {"running": False, "done": 0, "total": 0, "err": None}
_DFL_LOCK = threading.Lock()


def _dfl_universe():
    """ISIN всех рублёвых/валютных облигаций с RU-ISIN, торгуемых на bonds (без ОФЗ SU...). Кэш сутки."""
    hit = store().get(DFL_UNI_KEY, ttl=DAY)
    if hit:
        return hit
    j = json.loads(http_text("https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json?iss.meta=off"
                             "&iss.only=securities&securities.columns=SECID,ISIN", timeout=90))
    out = []
    for r in j["securities"]["data"]:
        sec, isin = str(r[0] or ""), str(r[1] or "")
        if isin.startswith("RU") and not sec.startswith("SU") and isin not in out:
            out.append(isin)
    if out:
        store().put(DFL_UNI_KEY, out)
    return out


def _dfl_scan_run(isins):
    found = []
    try:
        for i in range(0, len(isins), 60):
            part = isins[i:i + 60]
            for isin, fl in zip(part, pool_map(lambda x: _mon_flags(x), part, workers=6)):
                if fl.get("tech") or fl.get("default"):
                    found.append(isin)
            with _DFL_LOCK:
                _DFL_SCAN["done"] = min(len(isins), i + len(part))
            time.sleep(0.15)
        store().put(DFL_MKT_KEY, {"ts": time.time(), "isins": found, "total": len(isins)})
    except Exception as e:  # noqa: BLE001
        with _DFL_LOCK:
            _DFL_SCAN["err"] = str(e)
    finally:
        with _DFL_LOCK:
            _DFL_SCAN["running"] = False


def dfl_market(force=False):
    """Список ISIN с флагом (тех)дефолта по всему рынку + состояние обхода {running, done, total}. Запускает фоновый обход,
    если сохранённый результат старше 12 ч (или force). Пока идёт обход, isins — пусто/прошлый результат."""
    saved = store().get(DFL_MKT_KEY)
    fresh = bool(saved) and time.time() - saved.get("ts", 0) < DFL_MKT_TTL
    with _DFL_LOCK:
        if (force or not fresh) and not _DFL_SCAN["running"]:
            try:
                uni = _dfl_universe()
            except Exception as e:  # noqa: BLE001
                _DFL_SCAN["err"] = str(e)
                uni = []
            if uni:
                _DFL_SCAN.update(running=True, done=0, total=len(uni), err=None)
                threading.Thread(target=_dfl_scan_run, args=(uni,), daemon=True).start()
        scan = {"running": _DFL_SCAN["running"], "done": _DFL_SCAN["done"], "total": _DFL_SCAN["total"], "error": _DFL_SCAN["err"]}
    return {"isins": list((saved or {}).get("isins") or []), "scan": scan, "ts": (saved or {}).get("ts")}


def _disc_own_isins(cfg, acc):
    out = []
    try:
        out += list(watch_isins())
    except Exception:  # noqa: BLE001
        pass
    try:
        if cfg.get("token") or imports_list():
            out += [r["isin"] for r in (build_bonds(cfg, acc).get("rows") or []) if r.get("isin") and r.get("qty")]
    except Exception:  # noqa: BLE001
        pass
    return list(dict.fromkeys(out))


# ───────────────────────── маршруты ─────────────────────────

def disclosure_get(cfg, acc, q, force):
    isin = (q.get("isin") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{6,14}", isin):
        return {"error": "некорректный ISIN"}
    d = disclosure_for_bond(isin, n=20)
    d.update(isin=isin, configured=bool(ds_conf()[0]))
    return d


def issuer_flows_get(cfg, acc, q, force):
    inn = (q.get("inn") or "").strip()
    if not re.fullmatch(r"\d{10,12}", inn):
        return {"error": "некорректный ИНН"}
    try:
        h = max(1, min(60, int(q.get("months") or 25)))
    except ValueError:
        h = 25
    key = ("issflows", inn, h, date.today().isoformat())
    if not force:
        hit = mem_get(key, 1800)
        if hit:
            return hit
    return mem_put(key, issuer_cashflows(inn, h))


def defaults_get(cfg, acc, q, force):
    try:
        days = max(1, min(365, int(q.get("days") or 30)))
    except ValueError:
        days = 30
    since = (q.get("since") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
        since = (date.today() - timedelta(days=days)).isoformat()
    own = str(q.get("own", "1")) != "0"
    scope = "market" if str(q.get("scope") or "my").strip().lower() == "market" else "my"
    key = ("defaults", since, own, scope, bool(cfg.get("sandbox")), hash(cfg.get("token") or ""), acc)
    scan = None
    mine = _disc_own_isins(cfg, acc) if own else []
    if scope == "market":
        mk = dfl_market(bool(force))
        scan = mk["scan"]
        isins = list(dict.fromkeys(mine + mk["isins"]))
        if not scan["running"] and not force:
            hit = mem_get(key, 900)
            if hit:
                return dict(hit, scan=scan)
    else:
        isins = mine
        if not force:
            hit = mem_get(key, 900)
            if hit:
                return hit
    rows = defaults_feed(since, isins if (own or scope == "market") else None, schedule=True)
    mineset = set(mine)
    for r in rows:
        r["mine"] = r.get("isin") in mineset
    out = {"since": since, "scope": scope, "rows": rows, "configured": bool(ds_conf()[0])}
    if scan is not None:
        out["scan"] = scan
        if scan["running"]:           # промежуточный результат не кэшируем: он меняется по мере обхода
            return out
    return mem_put(key, out)


API_GET["/api/disclosure"] = disclosure_get
API_GET["/api/issuer_flows"] = issuer_flows_get
API_GET["/api/defaults"] = defaults_get
