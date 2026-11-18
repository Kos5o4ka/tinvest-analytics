# ── долговой рынок: линкеры (ОФЗ-ИН), радар оферт, валютные облигации после налога ──
# Все расчёты — модельные, не рекомендации. Источники: Мосбиржа (скринер), КБД, прогноз Банка России, отчётность РСБУ (ГИР БО), курсы ЦБ.

DBX_LINKER_RE = re.compile(r"^SU52\d{3}")
DBX_FIN_RE = re.compile(r"банк|страхов|\bНКО\b|лизинг|факторинг|микрофин|МФК|МКК|кредитн|ипотечн|коллектор|ломбард|финанс", re.I)
DBX_OFFER_DAYS = 365
DBX_MAX_ISSUERS = 60
DBX_PACE = 0.25



def dbx_sane_yield(y):
    """Доходность к оферте за несколько дней до неё (у Мосбиржи бывает ±десятки тысяч %) не информативна — скрываем."""
    try:
        y = float(y)
    except (TypeError, ValueError):
        return None
    return y if -5.0 <= y <= 100.0 else None

def _dbx_date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return None


# ── 1. линкеры ──

def dbx_fisher(nominal_pct, real_pct):
    """Инфляция безубыточности по Фишеру: (1+n)/(1+r)-1, в процентах; None если нет данных."""
    if nominal_pct is None or real_pct is None:
        return None
    return ((1 + nominal_pct / 100.0) / (1 + real_pct / 100.0) - 1) * 100.0


def dbx_avg_forecast(yearly, dur, today=None):
    """Средняя прогнозная инфляция на горизонте dur лет: годы из прогноза взвешены днями пересечения, дальше — последнее значение.
    -> (значение %, источник 'cbr'|'assumed'). Без прогноза — допущение 4 % (цель Банка России)."""
    today = today or date.today()
    pts = {int(y["year"]): y["mid"] for y in (yearly or []) if y.get("mid") is not None}
    if not pts or not dur or dur <= 0:
        return 4.0, "assumed"
    end = today + timedelta(days=int(dur * 365.25))
    last = pts[max(pts)]
    tot = acc = 0.0
    y = today.year
    while y <= end.year:
        a, b = max(today, date(y, 1, 1)), min(end, date(y, 12, 31))
        days = (b - a).days + 1
        if days > 0:
            acc += days * pts.get(y, last)
            tot += days
        y += 1
    return (acc / tot if tot else last), "cbr"


def dbx_linkers():
    rows = [r for r in screener_rows() if r.get("kind") == "ofz" and DBX_LINKER_RE.match(r.get("id") or "")]
    try:
        fc = inflation_forecast()
    except Exception:  # noqa: BLE001
        fc = {"source": "none", "yearly": []}
    out = []
    for r in rows:
        d = r.get("dur")
        if not d:
            continue
        nom = kbd_at(d)
        be = dbx_fisher(nom, r["yield"])
        fcv, src = dbx_avg_forecast(fc.get("yearly"), d)
        out.append({"id": r["id"], "name": r["name"], "isin": r.get("isin"), "mat": r["mat"], "price": r["price"], "real": r["yield"], "dur": d,
                    "nominal": round(nom, 2) if nom is not None else None, "be": round(be, 2) if be is not None else None,
                    "diff": round(nom - r["yield"], 2) if nom is not None else None, "fc": round(fcv, 2), "fc_src": src,
                    "gap": round(be - fcv, 2) if be is not None else None, "turn": r.get("turn")})
    out.sort(key=lambda x: x["dur"])
    return {"rows": out, "forecast": {"source": fc.get("source"), "as_of": fc.get("as_of"), "url": fc.get("url"), "yearly": fc.get("yearly")},
            "updated": time.time()}


def dbx_api_linkers(cfg, acc, q, force):
    try:
        return dbx_linkers()
    except Exception as e:  # noqa: BLE001
        return {"error": "Не удалось получить данные Мосбиржи: %s" % str(e)[:140], "rows": []}


# ── 2. радар оферт ──

def dbx_grade(ratio, is_fin=False):
    """Оценка покрытия оферты деньгами эмитента. ratio = (деньги + краткосрочные вложения) / объём выпуска."""
    if is_fin:
        return "na", "показатель неприменим"
    if ratio is None:
        return "nodata", "нет данных"
    if ratio >= 1.0:
        return "high", "покрытие высокое"
    if ratio >= 0.4:
        return "mid", "покрытие среднее"
    return "low", "покрытие низкое"


def dbx_offer_candidates(rows, today=None, days=DBX_OFFER_DAYS):
    today = today or date.today()
    lim = today + timedelta(days=days)
    out = []
    for r in rows:
        if r.get("kind") != "corp" or r.get("cur") != "RUB" or not r.get("offer"):
            continue
        d = _dbx_date(r["offer"])
        if d and today <= d <= lim:
            out.append(dict(r, _od=d))
    out.sort(key=lambda r: r["_od"])
    return out


_dbx_off = {"state": "idle", "done": 0, "total": 0, "rows": [], "t": 0, "capped": 0}
_dbx_lock = threading.Lock()


def _dbx_volume(r):
    """Объём выпуска в рублях (по номиналу): число бумаг в обращении, иначе объём выпуска Мосбиржи. -> (руб, метод)."""
    nom = r.get("nominal") or 1000
    try:
        o = bond_outstanding(r.get("isin"))
        if o and o.get("qty"):
            return o["qty"] * nom, "в обращении"
    except Exception:  # noqa: BLE001
        pass
    if r.get("size"):
        return r["size"] * nom, "объём выпуска"
    return None, None


def dbx_offer_work(cands):
    job = _dbx_off
    try:
        byid = {r["id"]: r for r in cands}
        for it in job["rows"]:
            try:
                em = issuer_of(it["isin"]) if it.get("isin") else None
            except Exception:  # noqa: BLE001
                em = None
            it["inn"] = (em or {}).get("inn")
            it["issuer"] = (em or {}).get("title") or (em or {}).get("short") or it["name"]
            it["is_fin"] = bool(DBX_FIN_RE.search(it["issuer"] or "") or DBX_FIN_RE.search(it.get("full") or ""))
            it["volume"], it["vol_how"] = _dbx_volume(byid[it["id"]])
            time.sleep(DBX_PACE / 2)
        fin_inn = []
        for it in job["rows"]:
            if it.get("inn") and not it["is_fin"] and it["inn"] not in fin_inn:
                fin_inn.append(it["inn"])
        job["capped"] = max(0, len(fin_inn) - DBX_MAX_ISSUERS)
        use = fin_inn[:DBX_MAX_ISSUERS]
        job["total"] = len(use)
        info = {}
        for inn in use:
            try:
                f = issuer_fin(inn)
                y = (f.get("years") or [None])[-1] if f.get("status") == "ok" else None
                info[inn] = {"cash": y.get("cash") if y else None, "year": y.get("y") if y else None, "status": f.get("status"), "note": f.get("note")}
            except Exception as e:  # noqa: BLE001
                info[inn] = {"cash": None, "year": None, "status": "err", "note": str(e)[:80]}
            job["done"] += 1
            time.sleep(DBX_PACE)
        dbx_offer_fill(job["rows"], info, set(use))
    except Exception as e:  # noqa: BLE001
        job["error"] = str(e)[:160]
    job["state"] = "done"
    job["t"] = time.time()


def dbx_offer_fill(items, info, used=None):
    """Покрытие считается по эмитенту: все оферты эмитента в горизонте суммируются (деньги одни на все выпуски).
    cash — млн ₽ (деньги 1250 + краткосрочные вложения 1240, последний год РСБУ), volume — ₽."""
    tot = {}
    for it in items:
        if it.get("volume"):
            k = it.get("inn") or it["id"]
            tot[k] = tot.get(k, 0) + it["volume"]
    for it in items:
        inn = it.get("inn")
        i = info.get(inn) if inn else None
        it["cash"] = i["cash"] if i else None
        it["fin_year"] = i["year"] if i else None
        it["fin_note"] = (i or {}).get("note")
        vol, all_vol = it.get("volume"), tot.get(inn or it["id"])
        it["cover"] = (it["cash"] * 1e6 / vol) if it["cash"] is not None and vol else None
        it["cover_all"] = (it["cash"] * 1e6 / all_vol) if it["cash"] is not None and all_vol else None
        it["issuer_total"] = all_vol
        it["grade"], it["grade_label"] = dbx_grade(it["cover_all"], it.get("is_fin"))
        if used is not None and inn and inn not in used and not it.get("is_fin"):
            it["fin_note"] = "Лимит запуска (%d эмитентов): отчётность не запрашивалась." % DBX_MAX_ISSUERS


def dbx_offers(force=False):
    with _dbx_lock:
        j = _dbx_off
        if j["state"] == "run":
            return dbx_offer_payload()
        if j["state"] == "done" and not force and time.time() - j["t"] < 6 * 3600:
            return dbx_offer_payload()
        try:
            cands = dbx_offer_candidates(screener_rows())
        except Exception as e:  # noqa: BLE001
            return {"error": "Не удалось получить данные Мосбиржи: %s" % str(e)[:140], "rows": []}
        j.update(state="run", done=0, total=0, capped=0, t=time.time(), error=None)
        j["rows"] = [{"id": r["id"], "isin": r.get("isin"), "name": r["name"], "full": r.get("full"), "offer": r["offer"], "mat": r["mat"],
                      "price": r["price"], "yield": dbx_sane_yield(r["yield"]), "nominal": r.get("nominal"), "grade": "loading", "grade_label": "считаю…"}
                     for r in cands]
        threading.Thread(target=dbx_offer_work, args=(cands,), daemon=True).start()
        return dbx_offer_payload()


def dbx_offer_payload():
    j = _dbx_off
    return {"pending": j["state"] == "run", "done": j["done"], "total": j["total"], "rows": j["rows"], "capped": j["capped"],
            "error": j.get("error"), "updated": j["t"]}


# ── 3. валютные облигации после налога ──

def dbx_xirr(flows):
    """Годовая эффективная ставка по потокам [(date, сумма)]; None, если знаки не меняются."""
    if not flows or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    t0 = flows[0][0]

    def npv(r):
        return sum(a / (1 + r) ** ((d - t0).days / 365.0) for d, a in flows)
    lo, hi = -0.95, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def dbx_coupon_dates(today, mat, freq):
    """Даты купонов назад от погашения шагом 12/freq месяцев; только после today."""
    step = max(1, int(round(12.0 / max(1, freq))))
    out, k = [], 0
    while k < 400:
        y, mo = divmod(mat.year * 12 + mat.month - 1 - k * step, 12)
        mo += 1
        ml = [31, 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo - 1]
        d = date(y, mo, min(mat.day, ml))
        if d <= today:
            break
        out.append(d)
        k += 1
    return sorted(out)


def dbx_fx_calc(p, today=None):
    """Модель: p = {nominal, price (% номинала), coupon (% годовых), freq, mat, buy_fx, qty, nkd (в валюте на бумагу), other (прочий налоговый доход года, ₽),
    scenarios [% изменения курса к сегодня на дату погашения]}. Курс идёт линейно от buy_fx к сценарному. База: купоны по курсу на дату выплаты +
    (погашение по курсу на дату − цена покупки по курсу на дату покупки − НКД). Ставка — прогрессивная НДФЛ по году погашения."""
    today = today or date.today()
    mat = p["mat"]
    if mat <= today:
        raise ValueError("Дата погашения должна быть в будущем")
    q, nom, fx0 = p["qty"], p["nominal"], p["buy_fx"]
    cost_cur = (nom * p["price"] / 100.0 + p.get("nkd", 0.0)) * q
    cost_rub = cost_cur * fx0
    cpn_cur = nom * p["coupon"] / 100.0 / p["freq"] * q
    dates = dbx_coupon_dates(today, mat, p["freq"])
    span = float((mat - today).days)
    res = []
    for s in p["scenarios"]:
        if s <= -99.0:
            continue
        fxm = fx0 * (1 + s / 100.0)
        if fxm <= 0:
            continue

        def fx_at(d, fxm=fxm):
            return fx0 + (fxm - fx0) * ((d - today).days / span)
        other = p.get("other", 0.0)
        # НДФЛ с купонов удерживается в даты их выплат (с учётом прогрессии по году), налог с тела — при погашении
        yr_acc = {}
        cpn_rub, cpn_tax_total = 0.0, 0.0
        flows_c, flows_r = [(today, -cost_cur)], [(today, -cost_rub)]
        post_flows_c, post_flows_r = [(today, -cost_cur)], [(today, -cost_rub)]
        for d in dates:
            fxd = fx_at(d)
            cr = cpn_cur * fxd
            cpn_rub += cr
            prev_y = yr_acc.get(d.year, other)
            t_d = max(0.0, tx_ndfl(prev_y + cr, d.year)[0] - tx_ndfl(prev_y, d.year)[0]) if cr > 0 else 0.0
            yr_acc[d.year] = prev_y + cr
            cpn_tax_total += t_d
            flows_c.append((d, cpn_cur))
            flows_r.append((d, cr))
            post_flows_c.append((d, cpn_cur - t_d / fxd))
            post_flows_r.append((d, cr - t_d))
        red_cur = nom * q
        red_rub = red_cur * fxm
        cap_gain_rub = red_rub - cost_rub
        prev_mat = yr_acc.get(mat.year, other)
        cap_tax = max(0.0, tx_ndfl(prev_mat + max(0.0, cap_gain_rub), mat.year)[0] - tx_ndfl(prev_mat, mat.year)[0])
        base = cpn_rub + cap_gain_rub
        tax = cpn_tax_total + cap_tax
        flows_c.append((mat, red_cur))
        flows_r.append((mat, red_rub))
        post_flows_c.append((mat, red_cur - cap_tax / fxm))
        post_flows_r.append((mat, red_rub - cap_tax))
        post_c = dbx_xirr(post_flows_c)
        post_r = dbx_xirr(post_flows_r)
        pre_c, pre_r = dbx_xirr(flows_c), dbx_xirr(flows_r)
        profit_c = cpn_cur * len(dates) + red_cur - cost_cur
        rd = lambda x: None if x is None else round(x * 100, 2)      # noqa: E731
        res.append({"scenario": s, "fx_mat": round(fxm, 4), "profit_cur": round(profit_c, 2), "base_rub": round(base, 2), "tax_rub": round(tax, 2),
                    "tax_rate": round(tax / base, 4) if base > 0 else 0.0, "tax_cur": round(tax / fxm, 2),
                    "pre_cur": rd(pre_c), "post_cur": rd(post_c), "pre_rub": rd(pre_r), "post_rub": rd(post_r),
                    "trap": bool(tax > 0 and profit_c <= 0.02 * cost_cur)})
    return {"cost_cur": round(cost_cur, 2), "cost_rub": round(cost_cur * fx0, 2), "n_coupons": len(dates), "coupon_cur": round(cpn_cur, 2),
            "scenarios": res, "mat": mat.isoformat(), "year": mat.year}


def dbx_api_fxbonds(cfg, acc, q, force):
    try:
        rows = [r for r in screener_rows() if r.get("cur") not in ("RUB", None)]
    except Exception as e:  # noqa: BLE001
        return {"error": "Не удалось получить данные Мосбиржи: %s" % str(e)[:140], "rows": []}
    rows.sort(key=lambda r: (r["cur"], r["mat"]))
    return {"rows": [{k: r.get(k) for k in ("id", "name", "isin", "cur", "nominal", "price", "yield", "coupon", "mat", "kind")} for r in rows]}


def _dbx_f(q, k, d=None):
    try:
        v = str(q.get(k, "")).replace(",", ".").strip()
        return float(v) if v != "" else d
    except ValueError:
        return d


def dbx_api_fx(cfg, acc, q, force):
    try:
        cur = (q.get("cur") or "USD").upper()
        mat = _dbx_date(q.get("mat"))
        if not mat:
            return {"error": "Укажите дату погашения (ГГГГ-ММ-ДД)."}
        fx_now = tax_cbr_rate(cur, date.today().isoformat())
        buy = _dbx_f(q, "buy_fx", None) or fx_now
        if not buy:
            return {"error": "Курс ЦБ недоступен — введите курс покупки вручную.", "fx_now": None}
        sc = [v for v in (float(x.replace(",", ".")) for x in (q.get("scenarios") or "-20,-10,0,10,20,40").split(",") if x.strip()) if v > -99.0][:12]
        if not sc:
            return {"error": "Укажите хотя бы один сценарий изменения курса > −99 %."}
        p = {"nominal": _dbx_f(q, "nominal", 1000.0), "price": _dbx_f(q, "price", 100.0), "coupon": _dbx_f(q, "coupon", 0.0),
             "freq": max(1, min(12, int(_dbx_f(q, "freq", 2)))), "mat": mat, "buy_fx": buy, "qty": max(1.0, _dbx_f(q, "qty", 1.0)),
             "nkd": _dbx_f(q, "nkd", 0.0), "other": _dbx_f(q, "other", 0.0), "scenarios": sc}
        if p["nominal"] <= 0 or p["price"] <= 0:
            return {"error": "Номинал и цена должны быть положительными."}
        out = dbx_fx_calc(p)
        out.update(cur=cur, fx_now=fx_now, buy_fx=buy)
        return out
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:160] or "Ошибка расчёта"}


API_GET["/api/dbx/linkers"] = dbx_api_linkers
API_GET["/api/dbx/offers"] = lambda cfg, acc, q, force: dbx_offers(force)
API_GET["/api/dbx/fxbonds"] = dbx_api_fxbonds
API_GET["/api/dbx/fx"] = dbx_api_fx
