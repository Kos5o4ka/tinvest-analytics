# ═══════════════════════════════ оферты и конструктор лесенки ═══════════════════════════════
# Справочные подсказки на данных Мосбиржи (bondization) и скринера; не индивидуальные инвестиционные рекомендации.

OF_DAYS, OF_PRICE_EPS, OF_MARGIN = 365, 0.1, 0.5      # окно оферт, дней; допуск цены, п. п.; запас до медианы аналогов, п. п.
OF_CALL_WORDS = ("колл", "call", "досроч")            # Мосбиржа обозначает put-оферту просто «Оферта»; колл — по ключевым словам


def _of_days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def _of_med(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)


def _of_date(s):
    return s if s and len(s) == 10 and not s.startswith("0000") else None


def _of_aci(bz, flows, d):
    """НКД на дату d на одну облигацию: линейно внутри купонного периода (по ближайшему будущему купону потоков)."""
    prev = [c["coupondate"] for c in bz["coupons"] if c.get("coupondate") and c["coupondate"] <= d]
    nxt = [(x[0], x[1]) for x in flows if x[0] > d and x[1] > 0]
    if not prev or not nxt:
        return 0.0
    p0, (n0, amt) = max(prev), min(nxt)
    span = _of_days(p0, n0)
    return amt * _of_days(p0, d) / span if span > 0 else 0.0


def _of_cut(bz, flows, face, od, op):
    """Потоки до оферты: покупатель по оферте получает op x остаток номинала и НКД на дату оферты."""
    head = [x for x in flows if x[0] < od]
    remain = face - sum(x[2] for x in head)
    c_od = sum(x[1] for x in flows if x[0] == od)
    acc = 0.0 if c_od else _of_aci(bz, flows, od)
    return head + [(od, c_od + acc, remain * op)], remain


def _of_peers(me, rating, floating, dur):
    """Медиана доходности и число аналогов: тот же рейтинг +/-1 ступень (если мало, +/-2), дюрация близка к dur."""
    if not dur or not rating or rating not in RATING_SCALE:
        return None, 0
    ri = RATING_SCALE.index(rating)
    uni = _bc_universe()
    for width in (1, 2):
        pool = []
        for e in uni:
            rt = e.get("_rt")
            if e["cur"] != "RUB" or not (0 < e["yield"] < 40) or not e.get("dur") or not rt or rt["v"] not in RATING_SCALE:
                continue
            if bool((e["_ci"] or {}).get("floating")) != bool(floating):
                continue
            if abs(RATING_SCALE.index(rt["v"]) - ri) > width or (me and e["_isin"] == me["_isin"]):
                continue
            if me and me.get("_iss") and e["_iss"] and e["_iss"] == me["_iss"]:
                continue
            if abs(e["dur"] - dur) > max(0.4, dur * 0.4):
                continue
            pool.append((abs(e["dur"] - dur) + 0.5 * abs(RATING_SCALE.index(rt["v"]) - ri), e["yield"]))
        if len(pool) >= 3:
            pool.sort()
            return _of_med([y for _, y in pool[:12]]), min(len(pool), 12)
    return None, 0


def _of_pct(x):
    return ("%.1f" % x).replace(".", ",")


def _of_one(r, bz, today, flags):
    """Оферты одной позиции в ближайшие OF_DAYS дней -> список записей."""
    horizon = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=OF_DAYS)).strftime("%Y-%m-%d")
    face = r.get("nominal") or 1000.0
    offs = []
    for o in bz.get("offers") or []:
        t = (o.get("offertype") or "")
        od = _of_date(o.get("offerdate"))
        if not od or "оферт" not in t.lower() or "состоял" in t.lower() or not today < od <= horizon:
            continue
        offs.append((od, o, any(w in t.lower() for w in OF_CALL_WORDS)))
    if not offs:
        return []
    fl_ = bool(r.get("floating"))
    flows, _k, _e = bond_flows(bz, today, face, mode="maturity", floating=fl_)
    cps = sorted((c["coupondate"], c.get("value"), c.get("valueprc")) for c in bz["coupons"] if c.get("coupondate"))
    rt = (r.get("rating") or {})
    rv = rt.get("v")
    me = next((e for e in _bc_universe() if e["_isin"] == r.get("isin")), None)
    outlooks = " ".join((x.get("outlook") or "") for x in rt.get("all") or []).lower()
    risk_notes = []
    if flags.get("default"):
        risk_notes.append("по данным Мосбиржи, у выпуска был дефолт")
    elif flags.get("tech"):
        risk_notes.append("по данным Мосбиржи, у выпуска был технический дефолт")
    if "негатив" in outlooks:
        risk_notes.append("у рейтинга негативный прогноз")
    if "наблюден" in outlooks:
        risk_notes.append("рейтинг взят под наблюдение")
    price_pct = r.get("price_pct")
    out = []
    for od, o, is_call in sorted(offs, key=lambda x: x[0]):
        days = _of_days(today, od)
        ps, pe = _of_date(o.get("offerdatestart")), _of_date(o.get("offerdateend"))
        price = o.get("price") or 100.0
        status, days_left = "unknown", None
        if ps and pe:
            days_left = _of_days(today, pe)
            status = "open" if ps <= today <= pe else ("upcoming" if today < ps else "closed")
        urgent = status == "open" or (status == "upcoming" and days_left is not None and days_left <= 7) or \
            (status == "unknown" and days <= 7)
        rec = {"isin": r.get("isin"), "uid": r.get("uid"), "name": r["name"], "logo": r.get("logo"), "color": r.get("color"),
               "qty": r.get("qty"), "value_rub": r.get("value_rub"), "rating": rv, "floating": fl_,
               "kind": "call" if is_call else "put", "date": od, "days": days, "period_start": ps, "period_end": pe,
               "period_status": status, "period_days_left": days_left, "urgent": urgent, "offer_price": price,
               "price": price_pct, "ytm_now": r.get("ytm"), "to_offer_rub": (r.get("qty") or 0) * face * price / 100.0,
               "risk_notes": risk_notes, "yield_to_offer": None, "coupon_known": False, "new_rate": None,
               "hold_yield": None, "peer_median": None, "peers_n": 0, "threshold": None}
        if is_call:
            rec["hint"] = {"code": "call", "title": "Эмитент может погасить досрочно",
                           "text": "Эмитент вправе выкупить или погасить бумаги досрочно: доходность к этой дате может оказаться "
                                   "единственной, на которую стоит рассчитывать. Заявку подавать не нужно."}
            out.append(rec)
            continue
        after_cut = None
        try:
            if flows:
                cut, remain = _of_cut(bz, flows, face, od, price / 100.0)
                aci_now = _of_aci(bz, flows, today)
                if price_pct:
                    dirty = price_pct / 100.0 * face + aci_now
                    y = cf_ytm(dirty, cut, today)
                    rec["yield_to_offer"] = y * 100 if y is not None else None
                after = [x for x in flows if x[0] > od]
                if after:
                    after_cut = (after, remain, _of_aci(bz, flows, od))
        except Exception:  # noqa: BLE001
            after_cut = None
        nxt = next(((d, v, vp) for d, v, vp in cps if d > od), None)
        known = bool(nxt and (nxt[1] or nxt[2]))
        rec["coupon_known"] = known
        if known:
            nd = nxt[0]
            prev = max([d for d, _, _ in cps if d <= od] or [""])
            rec["new_rate"] = nxt[2] if nxt[2] else (nxt[1] / max(face, 1e-9) * 365.0 / max(_of_days(prev or today, nd), 1) * 100.0)
        mac = None
        if after_cut:
            after, remain, aci_od = after_cut
            y2 = cf_ytm(remain + aci_od, after, od)
            if y2 is not None:
                mac, _m, _c = cf_risk(after, od, y2)
                if known:
                    rec["hold_yield"] = y2 * 100
        med, n = _of_peers(me, rv, fl_, mac)
        if med is not None:
            rec["peer_median"], rec["peers_n"], rec["threshold"] = med, n, med - OF_MARGIN
        rec["hint"] = _of_hint(rec, risk_notes)
        out.append(rec)
    return out


def _of_hint(rec, risk_notes):
    price, op, med = rec["price"], rec["offer_price"], rec["peer_median"]
    hy, thr = rec["hold_yield"], rec["threshold"]
    how = ("Заявку на выкуп подаёт брокер; обычно он принимает поручения на несколько дней раньше окончания периода "
           "предъявления — уточните сроки у брокера.")
    if rec["period_status"] == "closed":
        return {"code": "closed", "title": "Период предъявления закончился",
                "text": "Принимать заявки на выкуп уже поздно: бумага останется у вас, условия после оферты определяет эмитент."}
    if price is not None and price > op + OF_PRICE_EPS:
        return {"code": "sell_market", "title": "Выгоднее продать на бирже",
                "text": "Рыночная цена (%s %%) выше цены выкупа (%s %%): на бирже получите больше, чем по оферте. "
                        "Предъявлять бумаги не нужно." % (_of_pct(price), _of_pct(op))}
    if risk_notes:
        low = (" Рыночная цена (%s %%) заметно ниже цены выкупа: рынок сомневается, что эмитент выкупит бумаги." % _of_pct(price)
               if price is not None and price < op - 10 else "")
        return {"code": "put", "title": "Рассмотрите предъявление",
                "text": "Есть признаки повышенного риска эмитента: %s. Предъявление к выкупу по %s %% вернёт деньги по номиналу "
                        "до того, как условия могут измениться.%s %s" % ("; ".join(risk_notes), _of_pct(op), low, how)}
    if rec["floating"] and not rec["coupon_known"]:
        return {"code": "hold", "title": "Можно держать",
                "text": "Купон плавающий и следует за ключевой ставкой, поэтому после оферты он обычно остаётся на уровне рынка. "
                        "Предъявлять нужно, только если вам нужны деньги."}
    if rec["coupon_known"] and hy is not None:
        if med is not None and hy < med - OF_MARGIN:
            return {"code": "put", "title": "Рассмотрите предъявление",
                    "text": "Новый купон (%s %% годовых) даёт доходность %s %% против %s %% у похожих выпусков (%d шт.): ниже "
                            "рынка больше чем на 0,5 п. п. Деньги по оферте (%s %%) можно вложить в бумагу с более высокой "
                            "доходностью. %s" % (_of_pct(rec["new_rate"] or 0), _of_pct(hy), _of_pct(med), rec["peers_n"],
                                                 _of_pct(op), how)}
        if med is None:
            return {"code": "hold", "title": "Можно держать",
                    "text": "Новый купон известен (%s %% годовых), доходность после оферты %s %%. Сравнить с рынком не с чем: "
                            "подходящих аналогов мало. Оцените ставку сами." % (_of_pct(rec["new_rate"] or 0), _of_pct(hy))}
        return {"code": "hold", "title": "Можно держать",
                "text": "Новый купон (%s %% годовых) даёт доходность %s %% против %s %% у похожих выпусков (%d шт.): на уровне "
                        "рынка. Предъявлять нет смысла, если деньги не нужны." % (_of_pct(rec["new_rate"] or 0), _of_pct(hy),
                                                                                   _of_pct(med), rec["peers_n"])}
    t = "Ставка нового купона ещё не объявлена: дождитесь объявления."
    if thr is not None:
        t += " Если ставка будет ниже ≈%s %% (медиана похожих выпусков %s %% минус 0,5 п. п.), предъявление выглядит разумнее." \
             % (_of_pct(thr), _of_pct(med))
    if rec["urgent"]:
        t += " Срок предъявления близко. " + how
    return {"code": "wait", "title": "Дождитесь объявления ставки", "text": t}


def offers_payload(cfg, acc):
    rep = build_bonds(cfg, acc)
    today = date.today().isoformat()
    rows = [r for r in rep["rows"] if r.get("isin") and r.get("qty")]

    def one(r):
        try:
            bz = moex_bondization(r["isin"])
            if not bz:
                return [], None
            if not any(_of_date(o.get("offerdate")) for o in bz.get("offers") or []):
                return [], None
            flags = _mon_flags(r["isin"])
            return _of_one(r, bz, today, flags), None
        except Exception as e:  # noqa: BLE001
            return [], "%s: %s" % (r.get("name"), str(e)[:100])
    res = pool_map(one, rows, workers=8)
    items = sorted([x for lst, _ in res for x in lst], key=lambda x: (x["date"], x["name"]))
    errs = [e for _, e in res if e]
    # оферты по данным брокера, которых нет в Мосбирже
    have = {x["isin"] for x in items}
    horizon = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=OF_DAYS)).strftime("%Y-%m-%d")
    for r in rows:
        c = r.get("call")
        if c and today < c <= horizon and r["isin"] not in have:
            items.append({"isin": r["isin"], "uid": r.get("uid"), "name": r["name"], "logo": r.get("logo"), "color": r.get("color"),
                          "qty": r.get("qty"), "value_rub": r.get("value_rub"), "rating": (r.get("rating") or {}).get("v"),
                          "floating": bool(r.get("floating")), "kind": "call", "date": c, "days": _of_days(today, c),
                          "period_start": None, "period_end": None, "period_status": "unknown", "period_days_left": None,
                          "urgent": False, "offer_price": None, "price": r.get("price_pct"), "ytm_now": r.get("ytm"),
                          "to_offer_rub": None, "risk_notes": [], "yield_to_offer": None, "coupon_known": False,
                          "new_rate": None, "hold_yield": None, "peer_median": None, "peers_n": 0, "threshold": None,
                          "hint": {"code": "call", "title": "Возможна досрочная дата",
                                   "text": "По данным брокера, у выпуска есть дата досрочного погашения или оферты. На Мосбирже "
                                           "условия не опубликованы — уточните в проспекте выпуска."}})
    items.sort(key=lambda x: (x["date"], x["name"]))
    puts = [x for x in items if x["kind"] == "put"]
    return {"account": acc, "today": today, "items": items, "count": len(items), "put_count": len(puts),
            "urgent_count": sum(1 for x in puts if x["urgent"]),
            "value_rub": sum(x["value_rub"] or 0 for x in items), "to_offer_rub": sum(x["to_offer_rub"] or 0 for x in puts),
            "bonds_count": len(rows), "errors": errs,
            "empty_text": "В ближайшие 12 месяцев по облигациям портфеля оферт нет: выпуски погашаются по графику.",
            "notes": ["Оферта — право держателя продать бумагу эмитенту по заранее известной цене. Если вы ничего не делаете, "
                      "бумага остаётся у вас, но купон после оферты эмитент может изменить.",
                      "Мосбиржа публикует оферты одним типом; право эмитента досрочно погасить (колл) в данных обычно не отдельно "
                      "помечено, поэтому такие даты могут быть не видны."]}


# ═══════════════════ конструктор лесенки облигаций ═══════════════════

LD_MAX_BONDS, LD_YTM_MAX, LD_NOTCH, LD_SPREAD_MAX = 20, 40.0, 0.5, 9.0      # максимум бумаг, предел доходности (аномалии), штраф за ступень рейтинга, п. п.


def _ld_int(v, lo, hi, d):
    try:
        x = int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return d
    return max(lo, min(hi, x))


def _ld_flag(v, d):
    return d if v in (None, "") else str(v).lower() in ("1", "true", "on", "yes")


def _ld_add(d, years):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=round(years * 365.25))).strftime("%Y-%m-%d")


def _ld_months(bz, today):
    """Месяцы (1-12), в которые бумага платит купон (по ближайшим 14 месяцам графика)."""
    lim = _ld_add(today, 14 / 12.0)
    return sorted({int(c["coupondate"][5:7]) for c in bz["coupons"] if c.get("coupondate") and today < c["coupondate"] <= lim})


_LD_IDS = {}


def _ld_bz(isin):
    """Потоки выпуска: по ISIN, а если пусто (так бывает у ОФЗ) — по коду бумаги на Мосбирже."""
    bz = _safe_call(moex_bondization, isin)
    sid = _LD_IDS.get(isin)
    if not bz and sid and sid != isin:
        bz = _safe_call(moex_bondization, sid)
    return bz


def _ld_cands(q_min_rating, floaters, amort, min_turn, today):
    """Вселенная -> кандидаты лесенки: (запись, рейтинг, дата окончания, вид окончания, годы до окончания)."""
    mi = RATING_SCALE.index(q_min_rating)
    out = []
    for e in _bc_universe():
        ci = e.get("_ci") or {}
        if e["cur"] != "RUB" or not (0 < e["yield"] <= LD_YTM_MAX) or not e.get("mat") or e["mat"] <= today:
            continue
        if ci.get("perpetual") or ci.get("subordinated") or e.get("sub") and "суборд" in str(e.get("sub")).lower():
            continue
        if bool(ci.get("floating")) and not floaters or bool(ci.get("amort")) and not amort:
            continue
        if (e.get("turn") or 0) < min_turn:
            continue
        if e.get("spread") is not None and e["spread"] > LD_SPREAD_MAX:      # слишком щедрая доходность — признак ловушки
            continue
        _LD_IDS[e["_isin"]] = e["id"]
        rt = e.get("_rt")
        rv = rt["v"] if rt else ("AAA" if e["kind"] == "ofz" else None)
        if rv not in RATING_SCALE or RATING_SCALE.index(rv) > mi:
            continue
        end, kind = e["mat"], "maturity"
        if e.get("offer") and today < e["offer"] < end:
            end, kind = e["offer"], "offer"
        out.append({"e": e, "rv": rv, "end": end, "kind": kind, "t": _of_days(today, end) / 365.25})
    return out


def ladder_payload(cfg, q=None):
    q = q or {}
    if q.get("mode") == "portfolio":
        return ladder_portfolio(cfg, q.get("account", "all") or "all")
    today = date.today().isoformat()
    total = _fnum(q.get("sum"), 1000.0, 1e10, 500000.0)
    years = _ld_int(q.get("years"), 1, 10, 5)
    rungs_n = _ld_int(q.get("rungs"), 1, 12, years) if q.get("rungs") not in (None, "") else years
    mr = (q.get("min_rating") or "A").upper()
    mr = mr if mr in RATING_SCALE else "A"
    floaters, amort = _ld_flag(q.get("floaters"), False), _ld_flag(q.get("amort"), True)
    monthly = _ld_flag(q.get("monthly"), False)
    cap = _fnum(q.get("max_issuer"), 1.0, 100.0, max(5, round(100.0 / rungs_n / 2)))
    min_turn = _fnum(q.get("min_turnover"), 0.0, 1e12, 1000000.0)
    par = {"sum": total, "years": years, "rungs": rungs_n, "min_rating": mr, "floaters": floaters, "amort": amort,
           "max_issuer": cap, "min_turnover": min_turn, "monthly": monthly}
    warnings, notes = [], []
    cands = _ld_cands(mr, floaters, amort, min_turn, today)
    step = years / float(rungs_n)
    per_rung = total / rungs_n
    k_cap = int(-(-100.0 // (rungs_n * cap)))              # сколько бумаг на ступень нужно, чтобы доля эмитента не превысила лимит
    k = max(1, k_cap)
    if rungs_n * k > LD_MAX_BONDS:
        k = max(1, LD_MAX_BONDS // rungs_n)
        warnings.append("Лимит доли эмитента %s %% при таком числе ступеней потребовал бы больше %d бумаг; взято по %d на ступень, "
                        "доля одного эмитента может быть выше лимита." % (("%g" % cap).replace(".", ","), LD_MAX_BONDS, k))
    k = min(k, 3 if rungs_n * 3 <= LD_MAX_BONDS else k)
    if per_rung / k < 3000 and k > 1:
        k = max(1, int(per_rung // 3000))
    if per_rung < 1500:
        warnings.append("Сумма слишком мала для %d ступеней: на ступень приходится около %d ₽, а облигация стоит около 1 000 ₽ "
                        "и больше. Уменьшите число ступеней." % (rungs_n, round(per_rung)))
    win = []
    for i in range(rungs_n):
        mid = step * (i + 1)
        win.append((max(0.25, mid - step / 2.0), mid + step / 2.0 if i < rungs_n - 1 else min(mid + step / 2.0, years + 0.5), mid))
    # кандидаты по окнам; для «ровного дохода» подгружаем график купонов у лучших в каждом окне
    pools = []
    for lo, hi, mid in win:
        pl = [c for c in cands if lo <= c["t"] <= hi]
        for c in pl:
            ri = RATING_SCALE.index(c["rv"])
            c["score"] = c["e"]["yield"] - LD_NOTCH * ri - 0.3 * abs(c["t"] - mid) / max(step / 2.0, 0.25)
        pl.sort(key=lambda c: -c["score"])
        pools.append(pl)
    bzs = {}
    if monthly:
        want = [c["e"]["_isin"] for pl in pools for c in pl[:10]]
        for isin, bz in zip(want, pool_map(lambda x: _ld_bz(x), want, workers=8)):
            bzs[isin] = bz
    chosen = [[] for _ in range(rungs_n)]
    used_iss, iss_share, covered = set(), defaultdict(float), set()

    def iss_key(c):
        e = c["e"]
        return e["_isin"] if e["kind"] == "ofz" or not e.get("_iss") else tuple(sorted(e["_iss"]))
    order = sorted(range(rungs_n), key=lambda i: len(pools[i]))        # сначала ступени с наименьшим выбором
    share = 100.0 / (rungs_n * k)
    for i in order:
        pl = pools[i]
        for strict in (True, False):
            while len(chosen[i]) < k:
                best = None
                for c in pl:
                    ik = iss_key(c)
                    if c in chosen[i] or any(iss_key(x) == ik for x in chosen[i]):
                        continue
                    if strict and ik in used_iss:
                        continue
                    if not strict and iss_share[ik] + share > cap + 1e-9:
                        continue
                    sc = c["score"]
                    if monthly and bzs.get(c["e"]["_isin"]):
                        c["months"] = _ld_months(bzs[c["e"]["_isin"]], today)
                        sc += 0.25 * len(set(c["months"]) - covered) + 0.0
                    if best is None or sc > best[0]:
                        best = (sc, c)
                if not best:
                    break
                c = best[1]
                chosen[i].append(c)
                used_iss.add(iss_key(c))
                iss_share[iss_key(c)] += share
                if monthly and c.get("months"):
                    covered |= set(c["months"])
            if len(chosen[i]) >= k:
                break
    # проверка дефолтных флагов у выбранных; замена на следующих в окне
    flat = [(i, c) for i in range(rungs_n) for c in chosen[i]]
    flg = dict(zip([c["e"]["_isin"] for _, c in flat], pool_map(lambda x: _mon_flags(x[1]["e"]["_isin"]), flat, workers=8)))
    for i in range(rungs_n):
        bad_ = [c for c in chosen[i] if (flg.get(c["e"]["_isin"]) or {}).get("default") or (flg.get(c["e"]["_isin"]) or {}).get("tech")]
        for c in bad_:
            chosen[i].remove(c)
            warnings.append("%s исключена: по данным Мосбиржи у выпуска был дефолт." % c["e"]["name"])
            have = {iss_key(x) for x in chosen[i]}
            for c2 in pools[i]:
                if c2 not in chosen[i] and c2 is not c and iss_key(c2) not in have and iss_key(c2) not in used_iss:
                    f2_ = _mon_flags(c2["e"]["_isin"])
                    if not (f2_.get("default") or f2_.get("tech")):
                        chosen[i].append(c2)
                        used_iss.add(iss_key(c2))
                        break
    sel = [c for i in range(rungs_n) for c in chosen[i]]
    for c in sel:
        if c["e"]["_isin"] not in bzs:
            bzs[c["e"]["_isin"]] = None
    need = [c["e"]["_isin"] for c in sel if bzs.get(c["e"]["_isin"]) is None]
    for isin, bz in zip(need, pool_map(lambda x: _ld_bz(x), need, workers=8)):
        bzs[isin] = bz
    # потоки и цена с НКД; бумаги без потоков отбрасываем, на их место ставим следующих кандидатов окна
    def prep(c):
        e = c["e"]
        bz = bzs.get(e["_isin"])
        if bz is None and e["_isin"] not in bzs:
            bz = bzs[e["_isin"]] = _ld_bz(e["_isin"])
        face = float(e.get("nominal") or 1000.0)
        try:
            fl, kind, end = bond_flows(bz, today, face, floating=bool((e["_ci"] or {}).get("floating"))) if bz else (None, None, None)
        except Exception:  # noqa: BLE001
            fl = None
        if not fl:
            return "%s пропущена: нет данных о графике выплат." % e["name"]
        aci = _of_aci(bz, fl, today)
        dirty = e["price"] / 100.0 * face + aci
        y = cf_ytm(dirty, fl, today)
        if y is not None and y * 100.0 > LD_YTM_MAX:
            return "%s пропущена: расчётная доходность выглядит аномальной." % e["name"]
        c.update(flows=fl, face=face, dirty=dirty, ytm=(y * 100.0 if y is not None else e["yield"]), end=end, kind=kind,
                 months=_ld_months(bz, today))
        return None
    for i in range(rungs_n):
        keep = []
        for c in chosen[i]:
            er = prep(c)
            if er:
                warnings.append(er)
            else:
                keep.append(c)
        if keep and len(keep) < k or (not keep and chosen[i]):
            have = {iss_key(x) for x in keep}
            tried = 0
            for c2 in pools[i]:
                if len(keep) >= k or tried >= 8:
                    break
                if c2 in chosen[i] or iss_key(c2) in have or iss_key(c2) in used_iss:
                    continue
                f2_ = _mon_flags(c2["e"]["_isin"])
                if f2_.get("default") or f2_.get("tech"):
                    continue
                tried += 1
                if not prep(c2):
                    keep.append(c2)
                    have.add(iss_key(c2))
                    used_iss.add(iss_key(c2))
        chosen[i] = keep
    # покупка: целые лоты, остаток — свободные деньги
    free = total
    for i in range(rungs_n):
        if not chosen[i]:
            continue
        tgt = per_rung / len(chosen[i])
        for c in chosen[i]:
            c["target"] = tgt
            c["lots"] = int(tgt // c["dirty"])
            free -= c["lots"] * c["dirty"]
    allc = [c for i in range(rungs_n) for c in chosen[i]]
    while allc:
        opts = [c for c in allc if c["dirty"] <= free + 1e-9 and c["target"] - c["lots"] * c["dirty"] + 0.5 * c["dirty"] > 0]
        if not opts:
            break
        c = max(opts, key=lambda c: c["target"] - c["lots"] * c["dirty"])
        c["lots"] += 1
        free -= c["dirty"]
    for i in range(rungs_n):
        if not chosen[i]:
            warnings.append("На ступень «около %s» не нашлось подходящих бумаг (рейтинг не ниже %s, оборот от %s ₽/день): "
                            "деньги ступени остались свободными. Смягчите рейтинг или ликвидность."
                            % (_ld_when(win[i][2]), mr, "{:,}".format(int(min_turn)).replace(",", " ")))
        elif len(chosen[i]) < k:
            warnings.append("На ступень «около %s» нашлось только %d из %d нужных бумаг." % (_ld_when(win[i][2]), len(chosen[i]), k))
    zero = [c for c in allc if c["lots"] <= 0]
    for c in zero:
        warnings.append("%s не куплена: цена лота выше выделенной суммы." % c["e"]["name"])
    allc = [c for c in allc if c["lots"] > 0]
    invested = sum(c["lots"] * c["dirty"] for c in allc)
    # денежный поток
    mon = defaultdict(lambda: [0.0, 0.0])
    agg = defaultdict(float)
    cp12 = 0.0
    lim12 = _ld_add(today, 1)
    for c in allc:
        for d, cp, pr in c["flows"]:
            mon[d[:7]][0] += cp * c["lots"]
            mon[d[:7]][1] += pr * c["lots"]
            agg[d] += (cp + pr) * c["lots"]
            if d <= lim12:
                cp12 += cp * c["lots"]
    cfm = []
    if mon:
        y0, m0 = int(today[:4]), int(today[5:7])
        last = max(mon)
        ym = "%04d-%02d" % (y0, m0)
        while ym <= last:
            v = mon.get(ym, [0.0, 0.0])
            cfm.append({"month": ym, "coupons": v[0], "principal": v[1]})
            yy, mm = int(ym[:4]), int(ym[5:7])
            ym = "%04d-%02d" % (yy + (mm == 12), mm % 12 + 1)
    yld = dur = None
    if invested > 0 and agg:
        fl_ = [(d, a, 0.0) for d, a in sorted(agg.items())]
        yv = cf_ytm(invested, fl_, today)
        if yv is not None:
            yld = yv * 100.0
            dur = cf_risk(fl_, today, yv)[0]
    rows = []
    for i in range(rungs_n):
        bl = []
        for c in chosen[i]:
            if c["lots"] <= 0:
                continue
            e = c["e"]
            bl.append({"isin": e["_isin"], "name": e["name"], "rating": c["rv"], "ytm": c["ytm"], "end_date": c["end"],
                       "end_kind": c["kind"], "price": e["price"], "price_dirty": c["dirty"], "lots": c["lots"],
                       "cost": c["lots"] * c["dirty"], "coupon_months": c["months"], "floating": bool((e["_ci"] or {}).get("floating")),
                       "amort": bool((e["_ci"] or {}).get("amort")), "share": c["lots"] * c["dirty"] / total * 100.0})
        rows.append({"target_date": _ld_add(today, win[i][2]), "target_years": win[i][2], "window": [_ld_add(today, win[i][0]), _ld_add(today, win[i][1])],
                     "bonds": bl, "cost": sum(b["cost"] for b in bl)})
    issuers = {iss_key(c) for c in allc}
    big = max([(iss_share_ := sum(c["lots"] * c["dirty"] for c in allc if iss_key(c) == ik) / total * 100.0) for ik in issuers] or [0])
    if big > cap + 0.5:
        warnings.append("Доля крупнейшего эмитента %s %% выше лимита %s %%: не хватило разных эмитентов." %
                        (("%.1f" % big).replace(".", ","), ("%g" % cap).replace(".", ",")))
    if any(c["kind"] == "offer" for c in allc):
        notes.append("Если у выпуска есть оферта, срок считается до неё: к этой дате вы предъявляете бумагу эмитенту по цене выкупа "
                     "(обычно 100 %). Заявку подаёт брокер.")
    notes.append("Бумаги гасятся по очереди: деньги возвращаются каждый год, и их можно вложить по новой ставке. Если ставки "
                 "вырастут, вы реинвестируете дороже, если упадут, длинные ступени уже зафиксировали высокую доходность.")
    if monthly:
        notes.append("Включён ровный ежемесячный доход: при выборе бумаг учитывается, в какие месяцы они платят купоны.")
    if any(b["floating"] for r_ in rows for b in r_["bonds"]):
        notes.append("Купоны флоатеров оценены по прогнозу ключевой ставки Банка России: фактические выплаты могут отличаться.")
    if any(b["rating"] == "AAA" and next((c for c in allc if c["e"]["_isin"] == b["isin"]), {}).get("e", {}).get("kind") == "ofz"
           for r_ in rows for b in r_["bonds"]):
        notes.append("ОФЗ рейтинга не имеют; для отбора приравнены к AAA как государственный долг.")
    return {"params": par, "today": today, "rungs": rows,
            "totals": {"invested": invested, "free": total - invested, "ytm": yld, "dur": dur, "bonds": len(allc),
                       "issuers": len(issuers), "rungs_filled": sum(1 for r_ in rows if r_["bonds"]),
                       "coupon_12m": cp12, "monthly_avg": cp12 / 12.0, "max_issuer": big,
                       "months_with_coupon": sum(1 for m in cfm[:12] if m["coupons"] > 0)},
            "cashflow_by_month": cfm, "notes": notes, "warnings": warnings}


def _ld_when(y):
    return ("%.1f" % y).replace(".", ",") + " г."


def _safe_call(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001
        return None


# ───── лесенка текущего портфеля: сколько денег и когда возвращается ─────

LD_HEAVY = 1.5            # период «перегружен», если сумма больше среднего во столько раз
LD_QUARTERS_UNTIL = 1     # кварталами показываем текущий и следующий календарные годы, дальше — годами


def _ld_qkey(d):
    return "%s-Q%d" % (d[:4], (int(d[5:7]) - 1) // 3 + 1)


def _ld_pkey(d, today, gran):
    if gran == "quarter" and int(d[:4]) <= int(today[:4]) + LD_QUARTERS_UNTIL:
        return _ld_qkey(d)
    return d[:4]


def _ld_plabel(key):
    return ("%s кв. %s" % (key[6], key[:4])) if "-Q" in key else key


def _ld_pspan(today, gran, keys):
    """Все периоды от первого до последнего непрерывно: кварталы текущего и следующего года, затем годы."""
    if not keys:
        return []
    y0 = int(today[:4])
    out = []
    if gran == "quarter":
        q0 = (int(today[5:7]) - 1) // 3
        for y in range(y0, y0 + LD_QUARTERS_UNTIL + 1):
            for q in range(q0 if y == y0 else 0, 4):
                out.append("%d-Q%d" % (y, q + 1))
        last_y = max(int(k[:4]) for k in keys)
        last_q = max([k for k in keys if "-Q" in k] or [""])
        if last_y <= y0 + LD_QUARTERS_UNTIL:                       # хвост без событий не показываем
            out = [k for k in out if k <= last_q] or out[:1]
        out += [str(y) for y in range(y0 + LD_QUARTERS_UNTIL + 1, last_y + 1)]
        return out
    ys = sorted(int(k[:4]) for k in keys)
    return [str(y) for y in range(ys[0], ys[-1] + 1)]


def ld_buckets(items, today, gran="year"):
    """items: [{isin, name, ytm, events: [{date, type, amount}]}] -> периоды лесенки.
    Период: {key, label, kind, total, share, flag ('heavy'|'gap'|None), by_type, items}.
    heavy — сумма больше LD_HEAVY * среднего по периодам того же размера (между первым и последним непустым), gap — пустой период внутри."""
    grp = defaultdict(list)
    for it in items:
        for ev in it["events"]:
            if ev["date"] > today and ev["amount"] > 0:
                grp[_ld_pkey(ev["date"], today, gran)].append((it, ev))
    grand = sum(ev["amount"] for v in grp.values() for _, ev in v)
    periods = []
    for key in _ld_pspan(today, gran, list(grp)):
        rows, by = {}, {"redemption": 0.0, "offer": 0.0, "amort": 0.0}
        for it, ev in grp.get(key, []):
            r = rows.setdefault((it["isin"], ev["type"]), {"isin": it["isin"], "name": it["name"], "date": ev["date"], "type": ev["type"],
                                                           "amount": 0.0, "n": 0, "ytm": it.get("ytm")})
            r["amount"] += ev["amount"]
            r["n"] += 1
            r["date"] = min(r["date"], ev["date"])
            by[ev["type"]] += ev["amount"]
        lst = sorted(rows.values(), key=lambda r: (r["date"], r["name"]))
        tot = sum(r["amount"] for r in lst)
        for r in lst:
            r["pct"] = r["amount"] / grand * 100.0 if grand else 0.0
        periods.append({"key": key, "label": _ld_plabel(key), "kind": "q" if "-Q" in key else "y", "total": tot,
                        "share": tot / grand * 100.0 if grand else 0.0, "flag": None, "by_type": by, "items": lst})
    first_any = next((i for i, p in enumerate(periods) if p["total"] > 0), len(periods))
    for kind in ("q", "y"):
        ps = [p for p in periods if p["kind"] == kind]
        nz = [i for i, p in enumerate(ps) if p["total"] > 0]
        if len(nz) < 1:
            continue
        span = ps[nz[0]:nz[-1] + 1]
        avg = sum(p["total"] for p in span) / float(len(span)) if span else 0.0
        for i, p in enumerate(ps):
            if p["total"] <= 0:
                if nz[0] < i < nz[-1] or (kind == "y" and first_any < periods.index(p) and i < nz[-1]):
                    p["flag"] = "gap"
            elif len(span) >= 3 and p["total"] > LD_HEAVY * avg:
                p["flag"] = "heavy"
    return periods


def ld_summary(items, today, years):
    """Плашки: средний срок (по сумме возврата), ближайшая выплата, самый тяжёлый год, пустые годы."""
    evs = [(ev["date"], ev["amount"], it["name"]) for it in items for ev in it["events"] if ev["date"] > today and ev["amount"] > 0]
    tot = sum(a for _, a, _ in evs)
    avg = sum(_of_days(today, d) / 365.25 * a for d, a, _ in evs) / tot if tot else None
    nxt = None
    if evs:
        d0 = min(d for d, _, _ in evs)
        nxt = {"date": d0, "amount": sum(a for d, a, _ in evs if d == d0), "names": sorted({n for d, _, n in evs if d == d0})}
    heavy = max([p for p in years if p["total"] > 0], key=lambda p: p["total"], default=None)
    return {"total": tot, "avg_years": avg, "next": nxt,
            "heavy": {"label": heavy["label"], "share": heavy["share"], "total": heavy["total"], "flag": heavy["flag"]} if heavy else None,
            "gaps": [p["label"] for p in years if p["flag"] == "gap"]}


def ld_events(maturity, call, nominal, qty, k, amort, today, use_offer):
    """События возврата денег по одной бумаге: амортизации + погашение, либо + оферта вместо погашения. Суммы в рублях."""
    cut = call if use_offer and call and today < call and (not maturity or call < maturity) else None
    end = cut or maturity
    if not end or end <= today:
        return []
    out, paid = [], 0.0
    for ad, av in sorted(amort or []):
        if not ad or not av or ad <= today or ad >= end:
            continue
        paid += av
        out.append({"date": ad, "type": "amort", "amount": av * qty * k})
    out.append({"date": end, "type": "offer" if cut else "redemption", "amount": max(nominal - paid, 0.0) * qty * k})
    return out


def ladder_portfolio(cfg, acc="all"):
    rep = build_bonds(cfg, acc)
    today = date.today().isoformat()
    rows = [r for r in rep.get("rows", []) if r.get("qty") and r.get("nominal") and (r.get("maturity") or r.get("call"))]
    value = sum(r.get("value_rub") or 0.0 for r in rep.get("rows", []))
    if not rows:
        return {"today": today, "empty": True, "value": value, "variants": {}, "has_offers": False, "undated": []}

    def bz_of(r):
        return _safe_call(moex_bondization, r["isin"]) if r.get("isin") else None
    bzs = pool_map(bz_of, rows, workers=8)
    has_offers, undated, built = False, [], {"offer": [], "maturity": []}
    for r, bz in zip(rows, bzs):
        k = 1.0
        if (r.get("face_cur") or "rub") != "rub":                     # номинал в валюте -> рубли по курсу, выведенному из оценки позиции
            pp = r.get("price_pct")
            k = (r.get("value_rub") or 0.0) / (r["qty"] * pp / 100.0 * r["nominal"]) if pp else 0.0
            if k <= 0:
                continue
        am = [(a.get("amortdate"), a.get("value")) for a in (bz or {}).get("amort") or []]
        call = r.get("call") if r.get("call") and r["call"] > today else None
        if call and r.get("maturity") and call < r["maturity"]:
            has_offers = True
        for v, use in (("offer", True), ("maturity", False)):
            if not use and not r.get("maturity"):
                if v == "maturity":
                    undated.append(r["name"])
                continue
            ev = ld_events(r.get("maturity"), call, r["nominal"], r["qty"], k, am, today, use)
            if ev:
                built[v].append({"isin": r.get("isin") or r.get("ticker") or "", "name": r["name"], "ytm": r.get("ytm"), "events": ev})
    variants = {}
    for v, its in built.items():
        yr = ld_buckets(its, today, "year")
        variants[v] = {"year": yr, "quarter": ld_buckets(its, today, "quarter"), "summary": ld_summary(its, today, yr), "bonds": len(its)}
    return {"today": today, "empty": not any(built.values()), "value": value, "variants": variants, "has_offers": has_offers,
            "undated": sorted(set(undated))}
