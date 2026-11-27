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
        out.append({"e": e, "rv": rv, "end": e["mat"], "kind": "maturity", "t": _of_days(today, e["mat"]) / 365.25, "offs": []})
    # Срок до даты оферты только для ПУТ (решает держатель). Колл (решает эмитент) и «тип не указан» срок не меняют:
    # ступень стоит на погашении, а доходность считается к худшему (см. _ld_eval).
    wo = [c for c in out if c["e"].get("offer") and today < c["e"]["offer"] < c["e"]["mat"]]
    for c, offs in zip(wo, pool_map(lambda c: _safe_call(offers_of_isin, c["e"]["_isin"], c["e"]["offer"], today) or [], wo, workers=8)):
        c["offs"] = [o for o in offs if o["status"] != "cancelled"]
        pd = min([o["date"] for o in c["offs"] if o["kind"] == "put" and today < o["date"] < c["e"]["mat"]] or [""])
        if pd:
            c["end"], c["kind"], c["t"] = pd, "offer", _of_days(today, pd) / 365.25
    return out


def _ld_eval(c, bz, today):
    """Потоки и доходности кандидата с учётом типа оферты. None, если графика выплат нет.
    flows — потоки лесенки: до пут-оферты для пута, иначе до погашения; ytm (%) — доходность для отбора и показа:
    YTP для пута, YTW для колла, для «тип не указан» — меньшая из доходности к дате оферты и к погашению."""
    e = c["e"]
    fl_ = bool((e.get("_ci") or {}).get("floating"))
    face = float(e.get("nominal") or 1000.0)
    full = (_safe_call(bond_flows, bz, today, face, "maturity", fl_) or (None,))[0] if bz else None
    if not full:
        return None
    dirty = e["price"] / 100.0 * face + _of_aci(bz, full, today)
    yk = yields_by_kind(bz, today, face, dirty, c.get("offs") or [], floating=fl_)
    if not yk:
        return None
    b = yk["basis"]
    y = {"put": yk["ytp"], "call": yk["ytw"], "unknown": min([v for v in (yk["yto"], yk["ytm"]) if v is not None], default=None)}.get(b, yk["ytm"])
    put = b == "put"
    return {"face": face, "dirty": dirty, "yk": yk, "basis": b, "y": y, "flows": yk["flows"] if put else full,
            "end": yk["end"] if put else yk["maturity"], "kind": "offer" if put else "maturity"}


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
    # колл и «тип не указан»: для отбора берём доходность к худшему, а не доходность Мосбиржи (она может быть к дате колла)
    risky = [c for pl in pools for c in pl[:12] if c["offs"] and c["kind"] != "offer"]
    need_ = sorted({c["e"]["_isin"] for c in risky if c["e"]["_isin"] not in bzs})
    for isin, bz in zip(need_, pool_map(lambda x: _ld_bz(x), need_, workers=8)):
        bzs[isin] = bz
    for c in risky:
        ev = _ld_eval(c, bzs.get(c["e"]["_isin"]), today)
        if ev and ev["y"] is not None:
            c["score"] += ev["y"] * 100.0 - c["e"]["yield"]
    for pl in pools:
        pl.sort(key=lambda c: -c["score"])
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
        ev = _ld_eval(c, bz, today)
        if not ev:
            return "%s пропущена: нет данных о графике выплат." % e["name"]
        yk, y = ev["yk"], ev["y"]
        if y is not None and y * 100.0 > LD_YTM_MAX:
            return "%s пропущена: расчётная доходность выглядит аномальной." % e["name"]
        live = [o for o in c["offs"] if o["status"] != "cancelled"]
        c.update(flows=ev["flows"], face=ev["face"], dirty=ev["dirty"], ytm=(y * 100.0 if y is not None else e["yield"]),
                 end=ev["end"], kind=ev["kind"], months=_ld_months(bz, today), ybasis=ev["basis"],
                 ytm_mat=yk["ytm"] * 100.0 if yk["ytm"] is not None else None,
                 call_dates=sorted({o["date"] for o in live if o["kind"] == "call" and o["date"] < yk["maturity"]}),
                 unk_date=min([o["date"] for o in live if o["kind"] == "unknown" and o["date"] < yk["maturity"]] or [None], key=lambda x: x or "9"))
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
                       "end_kind": c["kind"], "yield_basis": c.get("ybasis"), "ytm_mat": c.get("ytm_mat"),
                       "call_dates": c.get("call_dates") or [], "unk_date": c.get("unk_date"), "price": e["price"], "price_dirty": c["dirty"], "lots": c["lots"],
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
        notes.append("Если у выпуска есть пут-оферта, срок считается до неё: к этой дате вы предъявляете бумагу эмитенту по цене выкупа "
                     "(обычно 100 %). Заявку подаёт брокер. Доходность таких бумаг — к пут-оферте.")
    callable_ = [c for c in allc if c.get("call_dates") or c.get("unk_date")]
    if any(c.get("call_dates") for c in callable_):
        notes.append("У части выпусков есть колл-опцион: эмитент может досрочно погасить бумагу. Ступень стоит на дате погашения, "
                     "а доходность показана к худшему (меньшая из доходности к погашению и к дате колла): если выпуск погасят раньше, "
                     "деньги вернутся раньше и их придётся реинвестировать.")
    if any(c.get("unk_date") and not c.get("call_dates") for c in callable_):
        notes.append("У части выпусков есть оферта, тип которой не указан. Консервативно ступень стоит на погашении, "
                     "доходность — меньшая из доходности к дате оферты и к погашению.")
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
                       "callable_cost": sum(c["lots"] * c["dirty"] for c in callable_),
                       "callable_share": sum(c["lots"] * c["dirty"] for c in callable_) / invested * 100.0 if invested > 0 else 0.0,
                       "callable_bonds": len(callable_),
                       "coupon_12m": cp12, "monthly_avg": cp12 / 12.0, "max_issuer": big,
                       "months_with_coupon": sum(1 for m in cfm[:12] if m["coupons"] > 0)},
            "cashflow_by_month": cfm, "notes": notes, "warnings": warnings}


