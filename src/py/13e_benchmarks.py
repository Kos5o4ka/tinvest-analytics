# ═══════════════════════════════ сравнение с рынком: индексы и фонды Мосбиржи ═══════════════════════════════
# Наружу уходят только обезличенные GET-запросы к iss.moex.com (история индексов и фондов); состав портфеля никуда не передаётся.

BENCH_CATALOG = [
    {"code": "RGBITR", "kind": "index", "group": "Индексы облигаций", "name": "ОФЗ (индекс гособлигаций)",
     "note": "Государственные облигации России с учётом купонов. Почти без кредитного риска, но цена заметно колеблется при смене ставок."},
    {"code": "RUCBTRNS", "kind": "index", "group": "Индексы облигаций", "name": "Корпоративные облигации (индекс)",
     "note": "Широкая корзина облигаций российских компаний с учётом купонов. Главный ориентир для облигационного портфеля."},
    {"code": "RUCBTRBBBNS", "kind": "index", "group": "Индексы облигаций", "name": "Корпоративные облигации среднего риска (индекс, рейтинг ВВВ)",
     "note": "Корзина корпоративных облигаций рейтинга ВВВ: доходность выше, чем у надёжных эмитентов, и риск тоже выше."},
    {"code": "RUCBHYTR", "kind": "index", "group": "Индексы облигаций", "name": "Высокодоходные облигации — индекс ВДО",
     "note": "Облигации небольших компаний с повышенным риском (ВДО). Платят больше, но чаще встречаются просадки и дефолты."},
    {"code": "LQDT", "kind": "fund", "group": "Фонды ликвидности", "name": "LQDT — ликвидность (ВИМ)",
     "note": "Фонд денежного рынка: деньги «лежат» под ставку РЕПО, продаются в день сделки. Самый простой безрисковый ориентир."},
    {"code": "TMON", "kind": "fund", "group": "Фонды ликвидности", "name": "TMON — Денежный рынок (Т-Капитал)",
     "note": "Фонд денежного рынка от Т-Капитала. Работает по тому же принципу, что и LQDT."},
    {"code": "SBMM", "kind": "fund", "group": "Фонды ликвидности", "name": "SBMM — Денежный рынок (Сбер)",
     "note": "Фонд денежного рынка от Сбер Управление Активами."},
    {"code": "AKMM", "kind": "fund", "group": "Фонды ликвидности", "name": "AKMM — Ликвидность (Ак Барс)",
     "note": "Фонд денежного рынка от Ак Барс Капитал."},
    {"code": "SBRB", "kind": "fund", "group": "Облигационные фонды", "name": "SBRB — Русские облигации (Сбер)",
     "note": "Фонд, который накапливает купоны в цене пая (выплат пайщикам нет). Диверсифицированная корзина облигаций."},
    {"code": "AKMB", "kind": "fund", "group": "Облигационные фонды", "name": "AKMB — Облигации (Ак Барс)",
     "note": "Облигационный фонд без выплат: доход остаётся в цене пая."},
    {"code": "TBRU", "kind": "fund", "group": "Облигационные фонды", "name": "TBRU — Облигации (Т-Капитал)",
     "note": "Облигационный фонд без выплат: доход остаётся в цене пая."},
]
BENCH_RF = {"code": "RUSFAR", "kind": "index", "group": "Ставка денежного рынка", "name": "Ставка RUSFAR (накопленная)",
            "note": "Ставка однодневного межбанковского кредита. Накопленная — как если бы деньги каждый день размещались под эту ставку."}
BENCH_TTL = 6 * 3600
BENCH_FROM_MIN = "2019-01-01"
_bench_locks, _bench_locks_lock, _bench_fail = {}, threading.Lock(), {}
_bench_rf_memo = {}


def _bench_kind(code):
    for b in BENCH_CATALOG + [BENCH_RF]:
        if b["code"] == code:
            return b["kind"]
    return "index"


def _bench_iss(url):
    last = None
    for i in range(3):
        try:
            return json.loads(http_text(url, 30))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4 * (i + 1))
    raise last


def _bench_fetch(code, frm, to=None):
    """Дневные закрытия с Мосбиржи (ISS отдаёт страницами по 100 строк). Фонд на нескольких досках за день — строка с максимальным оборотом."""
    fund = _bench_kind(code) == "fund"
    mkt = "shares" if fund else "index"
    cols = "BOARDID,TRADEDATE,CLOSE,VALUE" if fund else "TRADEDATE,CLOSE"
    out, best, start = {}, {}, 0
    for _ in range(80):
        url = ("https://iss.moex.com/iss/history/engines/stock/markets/%s/securities/%s.json?from=%s%s&start=%d"
               "&iss.only=history,history.cursor&history.columns=%s") % (mkt, code, frm, "&till=" + to if to else "", start, cols)
        j = _bench_iss(url)
        rows = (j.get("history") or {}).get("data") or []
        for r in rows:
            if fund:
                _, d, c, v = r
                if c is None:
                    continue
                if d not in best or (v or 0) >= best[d]:
                    best[d], out[d] = (v or 0), float(c)
            elif r[1] is not None:
                out[r[0]] = float(r[1])
        cur = ((j.get("history.cursor") or {}).get("data") or [[0, 0, 100]])[0]
        start = cur[0] + len(rows)
        if not rows or start >= cur[1]:
            break
    return out


def bench_history(code, frm=None, force=False):
    """{дата: закрытие}. Кэш в SQLite под ключом bench_v1:{CODE}: дозагружается хвост (с последней даты минус 5 дней)
    не чаще раза в 6 часов, а при запросе более ранней даты — начало. При сбое сети отдаётся прежний кэш."""
    frm = max(frm or BENCH_FROM_MIN, BENCH_FROM_MIN)
    key = "bench_v1:" + code
    with _bench_locks_lock:
        lk = _bench_locks.setdefault(code, threading.Lock())
    with lk:
        c = store().get(key)
        now = time.time()
        failed = now - _bench_fail.get(code, 0) < 300
        try:
            if not c or not c.get("d"):
                if failed:
                    return {}
                c = {"t": now, "from": frm, "d": _bench_fetch(code, frm)}
                store().put(key, c)
            else:
                changed = False
                if frm < c["from"] and not failed:
                    c["d"].update(_bench_fetch(code, frm, (datetime.strptime(c["from"], "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")))
                    c["from"] = frm
                    changed = True
                if (force or now - c["t"] > BENCH_TTL) and not failed:
                    last = max(c["d"])
                    since = (datetime.strptime(last, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
                    c["d"].update(_bench_fetch(code, since))
                    c["t"] = now
                    changed = True
                if changed:
                    store().put(key, c)
        except Exception:  # noqa: BLE001
            _bench_fail[code] = now
            return (c or {}).get("d") or {}
        return c["d"]


def _bench_carry(series, days):
    """Значения ряда на каждый календарный день с переносом последнего известного вперёд (до первой даты — None)."""
    ks = sorted(series)
    out, j, cur = [], 0, None
    for d in days:
        while j < len(ks) and ks[j] <= d:
            cur = series[ks[j]]
            j += 1
        out.append(cur)
    return out


def bench_rusfar_acc(frm=None):
    """RUSFAR — это ставка в % годовых. Накопленный доход: произведение (1 + r/100/365) по календарным дням. {дата: уровень}."""
    rates = bench_history("RUSFAR", frm)
    if not rates:
        return {}
    ks = sorted(rates)
    memo = _bench_rf_memo.get("v")
    if memo and memo[0] == (len(ks), ks[0], ks[-1]):
        return memo[1]
    d0, d1 = datetime.strptime(ks[0], "%Y-%m-%d").date(), date.today()
    lvl, r, out, j, d = 1.0, rates[ks[0]], {}, 0, d0
    while d <= d1:
        ds = d.isoformat()
        while j < len(ks) and ks[j] <= ds:
            r = rates[ks[j]]
            j += 1
        lvl *= 1 + r / 100.0 / 365.0
        out[ds] = lvl
        d += timedelta(days=1)
    _bench_rf_memo["v"] = ((len(ks), ks[0], ks[-1]), out)
    return out


def bench_lqdt_yield():
    """Текущая доходность фонда ликвидности LQDT, % годовых: рост цены пая за последние 30 дней, пересчитанный на год
    ((P_t / P_t-30) ^ (365 / дни) - 1). None при ошибке. Вызывается и из других разделов (калькулятор, скринер)."""
    key = "bench_lqdt_yield_v1"
    try:
        hit = store().get(key, 3 * 3600)
        if hit and hit.get("v") is not None:
            return hit["v"]
        frm = (date.today() - timedelta(days=75)).isoformat()
        h = bench_history("LQDT", frm)
        if len(h) < 5:
            return None
        ks = sorted(h)
        last = ks[-1]
        if (date.today() - datetime.strptime(last, "%Y-%m-%d").date()).days > 10:
            return None
        target = (datetime.strptime(last, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        i = bisect.bisect_right(ks, target) - 1
        if i < 0:
            return None
        days = (datetime.strptime(last, "%Y-%m-%d") - datetime.strptime(ks[i], "%Y-%m-%d")).days
        if days < 20 or h[ks[i]] <= 0:
            return None
        v = ((h[last] / h[ks[i]]) ** (365.0 / days) - 1) * 100
        v = round(v, 2)
        store().put(key, {"v": v, "d": last})
        return v
    except Exception:  # noqa: BLE001
        return None


# ── расчёты ──

def _bn_stats(xs):
    n = len(xs)
    if n < 2:
        return 0.0, 0.0
    m = sum(xs) / n
    return m, (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5


def _bn_risk(idx, lv, rf, pt=None):
    """Риск-метрики по точкам-индексам idx (торговые дни). lv/rf — уровни по календарным дням. pt — доходности портфеля для беты."""
    L = [lv[i] for i in idx]
    if len(L) < 3 or any(x is None or x <= 0 for x in L):
        return None
    r = [L[k] / L[k - 1] - 1 for k in range(1, len(L))]
    ex = []
    for k in range(1, len(idx)):
        a, b = rf[idx[k - 1]], rf[idx[k]]
        ex.append(r[k - 1] - ((b / a - 1) if a and b else 0.0))
    m, sd = _bn_stats(r)
    peak, dd = L[0], 0.0
    for x in L:
        peak = max(peak, x)
        dd = min(dd, x / peak - 1)
    res = {"vol": sd * 252 ** 0.5, "maxdd": dd, "n": len(r),
           "sharpe": (_bn_stats(ex)[0] / sd * 252 ** 0.5) if sd > 1e-9 else None, "ret": r}
    return res


def _bn_cov(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return None, None
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    va = sum((x - ma) ** 2 for x in a) / (n - 1)
    vb = sum((x - mb) ** 2 for x in b) / (n - 1)
    beta = cov / vb if vb > 1e-14 else None
    corr = cov / (va * vb) ** 0.5 if va > 1e-14 and vb > 1e-14 else None
    return beta, corr


def _bn_window(days, period):
    today = date.today()
    last = len(days) - 1
    s = e = None
    if period == "1m":
        s = (today - timedelta(days=30)).isoformat()
    elif period == "3m":
        s = (today - timedelta(days=91)).isoformat()
    elif period == "12m":
        s = (today - timedelta(days=365)).isoformat()
    elif period == "ytd":
        s = "%d-01-01" % today.year
    elif period == "py":
        s, e = "%d-01-01" % (today.year - 1), "%d-12-31" % (today.year - 1)
    i0 = 0
    if s:
        i0 = next((i for i, d in enumerate(days) if d >= s), None)
        if i0 is None:
            return None
        i0 = max(0, i0 - 1)
    i1 = last
    if e:
        while i1 > 0 and days[i1] > e:
            i1 -= 1
    if i1 <= i0:
        return None
    return i0, i1


def _bn_thin(n, k=400):
    if n <= k:
        return list(range(n))
    step = (n - 1) / float(k - 1)
    idx = sorted({int(round(i * step)) for i in range(k)} | {n - 1})
    return idx


def bench_liquidity(cfg, acc, total):
    mon = build_monitor(cfg, acc)
    rows = [r for r in (mon.get("rows") or []) if (r.get("value_rub") or 0) > 0]
    defs = [("d1", "до 1 дня", lambda x: x <= 1), ("d5", "1–5 дней", lambda x: 1 < x <= 5), ("dm", "больше 5 дней", lambda x: x > 5)]
    bv = sum(r["value_rub"] for r in rows)
    out = []
    for k, label, fn in defs:
        sel = [r for r in rows if r.get("days_to_sell") is not None and fn(r["days_to_sell"])]
        out.append({"key": k, "label": label, "value": sum(r["value_rub"] for r in sel), "count": len(sel)})
    sel = [r for r in rows if r.get("days_to_sell") is None]
    out.append({"key": "na", "label": "нет данных", "value": sum(r["value_rub"] for r in sel), "count": len(sel)})
    for b in out:
        b["share"] = b["value"] / bv * 100 if bv else None
        b["share_total"] = b["value"] / total * 100 if total else None
    slow = sorted([r for r in rows if r.get("days_to_sell") is not None], key=lambda r: -r["days_to_sell"])[:8]
    return {"bonds_value": bv, "bonds_count": len(rows), "portfolio_value": total, "buckets": out,
            "slowest": [{"name": r.get("name"), "isin": r.get("isin"), "value_rub": r["value_rub"], "days": r["days_to_sell"],
                         "turnover": r.get("turnover_avg")} for r in slow],
            "part": MON_PART * 100, "fund_days": 0}


def bench_premium(cfg, acc):
    lq = bench_lqdt_yield()
    b = build_bonds(cfg, acc)
    m = b.get("metrics") or {}
    rows = [r for r in (b.get("rows") or []) if r.get("ytm") is not None and (r.get("value_rub") or 0) > 0 and r.get("qty")]
    ok = [r for r in rows if r["ytm"] <= YTM_HIGH]
    wv = sum(r["value_rub"] for r in ok)
    res = {"lqdt": lq, "ytm_ex": sum(r["ytm"] * r["value_rub"] for r in ok) / wv if wv else None, "ytm": m.get("ytm"), "irr": m.get("irr"), "ytm_tax": m.get("ytm_tax"), "bonds_value": m.get("value"),
           "count": m.get("count"), "high_yield_value": m.get("high_yield_value"), "below": [], "below_value": 0.0}
    if lq is not None:
        res["prem_ytm"] = m["ytm"] - lq if m.get("ytm") is not None else None
        res["prem_ytm_ex"] = res["ytm_ex"] - lq if res["ytm_ex"] is not None else None
        res["prem_irr"] = m["irr"] - lq if m.get("irr") is not None else None
        bl = sorted([r for r in rows if r["ytm"] < lq], key=lambda r: r["ytm"] - lq)
        res["below_value"] = sum(r["value_rub"] for r in bl)
        res["below"] = [{"name": r.get("name"), "isin": r.get("isin"), "ytm": r["ytm"], "diff": r["ytm"] - lq, "value_rub": r["value_rub"]} for r in bl[:12]]
        res["below_count"] = len(bl)
    return res


def bench_payload(cfg, acc, q=None):
    q = q or {}
    period = q.get("period") or "all"
    if period not in ("1m", "3m", "ytd", "12m", "py", "all"):
        period = "all"
    want = {c for c in (q.get("codes") or "").replace(";", ",").split(",") if c}
    key = ("bench", token_key(cfg), acc, period, tuple(sorted(want)))
    hit = mem_get(key, 600)
    if hit:
        return hit
    h = build_history_for(cfg, acc)
    days = h.get("days") or []
    if len(days) < 3:
        return {"error": "Нет операций для сравнения: история портфеля пуста."}
    win = _bn_window(days, period)
    if not win:
        return {"error": "За выбранный период нет данных по портфелю. Выберите период длиннее."}
    i0, i1 = win
    notes = []
    frm = (datetime.strptime(days[i0], "%Y-%m-%d") - timedelta(days=12)).strftime("%Y-%m-%d")
    cat = [b for b in BENCH_CATALOG if not want or b["code"] in want]
    jobs = [b["code"] for b in cat] + ["RUSFAR"]
    if not any(b["code"] == "LQDT" for b in cat):
        jobs.append("LQDT")      # календарь торговых дней
    jobs = list(dict.fromkeys(jobs))
    hs = dict(zip(jobs, pool_map(lambda c: bench_history(c, frm), jobs, workers=6)))
    # торговые дни Мосбиржи
    cal_src = hs.get("LQDT") or next((v for v in hs.values() if v), {})
    d_start, d_end = days[i0], days[i1]
    cal = sorted(d for d in cal_src if d_start < d <= d_end)
    didx = {d: i for i, d in enumerate(days)}
    cal_i = [didx[d] for d in cal if d in didx]
    # безрисковая ставка
    acc_rf = bench_rusfar_acc(frm)
    rf = _bench_carry(acc_rf, days) if acc_rf else [None] * len(days)
    if not acc_rf:
        notes.append("Ставка RUSFAR не загрузилась: коэффициент Шарпа посчитан без вычета безрисковой ставки.")
    elif acc_rf and min(acc_rf) > d_start:
        notes.append("Данные RUSFAR начинаются с %s: до этой даты безрисковая ставка принята равной нулю." % min(acc_rf))
    val, inv, twr = h["value"], h["invested"], h["twr"]
    # портфель
    base_t = twr[i0]
    pw = [x / base_t - 1 for x in twr[i0:i1 + 1]]
    years = (datetime.strptime(d_end, "%Y-%m-%d") - datetime.strptime(d_start, "%Y-%m-%d")).days / 365.25
    total = pw[-1]
    ann = (1 + total) ** (1 / years) - 1 if years >= 0.98 and total > -1 else None
    pidx = [i0] + cal_i
    prk = _bn_risk(pidx, twr, rf)
    if prk:
        k = max(range(len(prk["ret"])), key=lambda n: abs(prk["ret"][n]))
        if abs(prk["ret"][k]) > 0.1:
            notes.append("В истории портфеля есть резкий скачок %s%% за один торговый день (%s). Обычно это следствие неполных цен по какой-то бумаге; "
                         "из-за такого скачка волатильность, просадка и бета портфеля за период могут быть завышены." % (
                             ("%+.0f" % (prk["ret"][k] * 100)).replace("-", "−"), days[pidx[k + 1]]))
    flows = [(i, inv[i] - inv[i - 1]) for i in range(i0 + 1, i1 + 1) if abs(inv[i] - inv[i - 1]) > 0.005]
    net_flow = sum(f for _, f in flows)
    dts = [datetime.strptime(d, "%Y-%m-%d").date() for d in days]

    def xr(v_end, series_flows):
        fl = ([(dts[i0], -val[i0])] if val[i0] > 0 else []) + [(dts[i], -f) for i, f in series_flows] + [(dts[i1], v_end)]
        if years < 0.25:       # годовая ставка по коротким отрезкам вводит в заблуждение
            return None
        try:
            return xirr(fl)
        except Exception:  # noqa: BLE001
            return None

    pf = {"ret": total * 100, "ann": ann * 100 if ann is not None else None,
          "vol": prk["vol"] * 100 if prk else None, "maxdd": prk["maxdd"] * 100 if prk else None,
          "sharpe": prk["sharpe"] if prk else None, "xirr": (lambda x: x * 100 if x is not None else None)(xr(val[i1], flows)),
          "value_start": val[i0], "value_end": val[i1], "net_flow": net_flow, "gain": val[i1] - val[i0] - net_flow}
    # график: проредить
    tix = _bn_thin(i1 - i0 + 1)
    sd = [days[i0 + k] for k in tix]
    series = {"dates": sd, "portfolio": [round(pw[k] * 100, 3) for k in tix], "bench": {}}
    out = []
    for b in cat + [BENCH_RF]:
        code = b["code"]
        if code == "RUSFAR":
            if not acc_rf:
                continue
            lv = rf
        else:
            ser = hs.get(code) or {}
            if not ser:
                out.append(dict(b, available=False, reason="Мосбиржа не отдала историю"))
                continue
            lv = _bench_carry(ser, days)
        j = next((i for i in range(i0, i1 + 1) if lv[i]), None)
        if j is None or j > i1 - 5:
            out.append(dict(b, available=False, reason="нет данных за период"))
            continue
        partial = j > i0 + 7
        if partial:
            notes.append("%s: история в выбранном периоде начинается с %s." % (code, days[j]))
        j = max(j, i0)
        b0 = lv[j]
        cum = [None if lv[i] is None or i < j else lv[i] / b0 - 1 for i in range(i0, i1 + 1)]
        series["bench"][code] = [None if cum[k] is None else round(cum[k] * 100, 3) for k in tix]
        tot_b = cum[-1]
        yrs = (datetime.strptime(d_end, "%Y-%m-%d") - datetime.strptime(days[j], "%Y-%m-%d")).days / 365.25
        ann_b = (1 + tot_b) ** (1 / yrs) - 1 if yrs >= 0.98 and tot_b > -1 else None
        idx = [j] + [i for i in cal_i if i > j]
        rk = _bn_risk(idx, lv, rf)
        e = dict(b, available=True, partial=partial, start=days[j], ret=tot_b * 100, ann=ann_b * 100 if ann_b is not None else None,
                 vol=rk["vol"] * 100 if rk else None, maxdd=rk["maxdd"] * 100 if rk else None,
                 sharpe=rk["sharpe"] if (rk and code != "RUSFAR") else None, beta=None, corr=None, same=None)
        if rk and prk and code != "RUSFAR":
            pr = _bn_risk(idx, twr, rf)
            if pr:
                e["beta"], e["corr"] = _bn_cov(pr["ret"], rk["ret"])
        # «те же деньги в тот же день — в бенчмарк»
        if code != "RUSFAR":
            u = val[j] / lv[j] if val[j] > 0 else 0.0
            sf, ok = [], True
            for i in range(j + 1, i1 + 1):
                f = inv[i] - inv[i - 1]
                if abs(f) > 0.005:
                    if not lv[i]:
                        ok = False
                        break
                    u += f / lv[i]
                    sf.append((i, f))
            if ok and u >= 0:
                fin = u * lv[i1]
                nf = sum(f for _, f in sf)
                x = None
                if j == i0:
                    x = xr(fin, sf)
                e["same"] = {"final": fin, "diff": val[i1] - fin, "gain": fin - val[j] - nf, "xirr": x * 100 if x is not None else None}
        out.append(e)
    res = {"period": period, "start": d_start, "end": d_end, "years": years, "series": series, "portfolio": pf,
           "bench": out, "groups": list(dict.fromkeys([b["group"] for b in BENCH_CATALOG] + [BENCH_RF["group"]])),
           "trading_days": len(cal_i), "notes": notes}
    try:
        res["liquidity"] = bench_liquidity(cfg, acc, val[-1])
    except Exception as e:  # noqa: BLE001
        res["liquidity"] = None
        notes.append("Данные о ликвидности недоступны: %s" % str(e)[:100])
    try:
        res["premium"] = bench_premium(cfg, acc)
    except Exception as e:  # noqa: BLE001
        res["premium"] = None
        notes.append("Данные о доходности облигаций недоступны: %s" % str(e)[:100])
    res["lqdt_yield"] = bench_lqdt_yield()
    return mem_put(key, res)
