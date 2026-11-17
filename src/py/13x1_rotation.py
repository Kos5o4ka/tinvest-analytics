# ── Флоатеры или фиксы: модель ротации (полная доходность, сценарии ставки, точка безубыточности, лесенка, лаг фиксации, дюрационный разрыв) ──

ROT_TAX = 0.13
ROT_FLOOR = 4.0                       # нижняя граница ключевой ставки в сценариях, %
ROT_HORIZONS = [(0.25, "3 мес"), (0.5, "6 мес"), (1.0, "1 год"), (2.0, "2 года"), (3.0, "3 года")]
ROT_SCN = [("flat", "Ставка без изменений"), ("cbr", "Прогноз ЦБ"), ("smooth", "Плавное снижение"),
           ("fast", "Быстрое снижение"), ("up", "Повышение")]
ROT_SCN_NOTE = {"flat": "ключевая ставка остаётся на текущем уровне", "cbr": "траектория из прогноза Банка России (или выбранного в настройках источника)",
                "smooth": "минус 50 б.п. на каждом заседании, около −4 п.п. в год", "fast": "около −8 п.п. в год",
                "up": "+2 п.п. за первый год, затем без изменений"}
ROT_BETA = {"long": 0.5, "mid": 0.7, "short": 0.9}     # доля изменения ключевой ставки, передающаяся доходности ОФЗ: >5 лет, 2–5 лет, <2 лет
ROT_FL_DUR = 0.25                     # эффективная дюрация флоатера (до ближайшей фиксации купона), лет
ROT_RU_LAG = 7.0 / 365.0              # сдвиг окна усреднения RUONIA в купонных периодах, лет
ROT_STEP = 1.0 / 12.0
ROT_TTL = 600
_rot_state = {"t": 0.0, "snap": None, "busy": False, "err": ""}
_rot_lock = threading.Lock()


def _rot_clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _rot_num(x, lo, hi, dflt):
    try:
        v = float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return dflt
    return v if lo <= v <= hi else dflt


# ── траектории ключевой ставки ──

def rot_path(kind, k0, fpath=None, today=None, floor=ROT_FLOOR, cut=0.0, years=3.5):
    """Узлы траектории ключевой ставки [(t лет от сегодня, % годовых)] с шагом месяц.
    kind: flat | cbr | smooth | fast | up | cut (параллельное снижение на cut п.п. за год, потом без изменений).
    Для cbr нужен fpath [(дата ISO, %)]; без него возвращается None."""
    n = int(round(years / ROT_STEP))
    if kind == "cbr":
        if not fpath:
            return None
        d0 = today or date.today().isoformat()
        out = []
        for i in range(n + 1):
            t = i * ROT_STEP
            d = (datetime.strptime(d0, "%Y-%m-%d") + timedelta(days=t * 365.0)).strftime("%Y-%m-%d")
            v = keyrate_at(fpath, d)
            out.append((t, max(min(floor, k0), v if v is not None else k0)))
        out[0] = (0.0, k0)
        return out
    out = []
    for i in range(n + 1):
        t = i * ROT_STEP
        if kind == "smooth":
            v = k0 - 4.0 * t
        elif kind == "fast":
            v = k0 - 8.0 * t
        elif kind == "up":
            v = k0 + 2.0 * min(t, 1.0)
        elif kind == "cut":
            v = k0 - cut * min(t, 1.0)
        else:
            v = k0
        out.append((t, max(min(floor, k0), v)))
    out[0] = (0.0, k0)
    return out


def rot_rate(knots, t):
    if t <= knots[0][0]:
        return knots[0][1]
    for (t0, v0), (t1, v1) in zip(knots, knots[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return knots[-1][1]


def rot_avg(knots, a, b, n=24):
    """Средняя ставка пути на отрезке [a, b] (лет), %."""
    if b <= a:
        return rot_rate(knots, a)
    return sum(rot_rate(knots, a + (b - a) * (i + 0.5) / n) for i in range(n)) / n


def rot_growth(knots, a, b):
    """Множитель реинвестирования от a до b по средней ставке пути на этом отрезке."""
    if b <= a:
        return 1.0
    return (1.0 + rot_avg(knots, a, b) / 100.0) ** (b - a)


# ── полная доходность ──

def rot_tr_floater(knots, T, spread, tax=True, period=0.25):
    """Годовая полная доходность флоатера, % годовых: купон = ставка на начало купонного периода + спред, цена ~ номинал,
    купоны реинвестируются по средней ставке пути, НДФЛ 13% с купонов."""
    k = (1.0 - ROT_TAX) if tax else 1.0
    v, t = 0.0, 0.0
    while t < T - 1e-9:
        e = min(t + period, T)
        c = (rot_rate(knots, t) + spread) / 100.0 * (e - t)
        v += c * k * rot_growth(knots, e, T)
        t = e
    return ((1.0 + v) ** (1.0 / T) - 1.0) * 100.0


def rot_pv(flows, t0, y):
    """Приведённая стоимость потоков [(t, купон, номинал)] после момента t0 при доходности y (дробью, годовая)."""
    return sum((c + p) / (1.0 + y) ** (t - t0) for t, c, p in flows if t > t0 + 1e-9)


def rot_ytm(flows, dirty, t0=0.0):
    """Доходность (дробью), при которой PV потоков равна грязной цене; None, если корня нет."""
    if not flows or not dirty or dirty <= 0:
        return None
    lo, hi = -0.5, 5.0
    flo, fhi = rot_pv(flows, t0, lo) - dirty, rot_pv(flows, t0, hi) - dirty
    if flo * fhi > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        fm = rot_pv(flows, t0, mid) - dirty
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
        if hi - lo < 1e-10:
            break
    return (lo + hi) / 2


def rot_dur_conv(flows, y, t0=0.0):
    """(дюрация Маколея, модифицированная, выпуклость) потоков при доходности y; выпуклость всегда положительна."""
    pv = [(t - t0, (c + p) / (1.0 + y) ** (t - t0)) for t, c, p in flows if t > t0 + 1e-9]
    tot = sum(v for _, v in pv)
    if not tot:
        return None, None, None
    mac = sum(t * v for t, v in pv) / tot
    conv = sum(t * (t + 1.0) * v for t, v in pv) / tot / (1.0 + y) ** 2
    return mac, mac / (1.0 + y), conv


def rot_accr(flows, t):
    """НКД на момент t по линейному накоплению внутри купонного периода (в тех же единицах, что и потоки)."""
    nx = [i for i, f in enumerate(flows) if f[0] > t + 1e-9]
    if not nx:
        return 0.0
    i = nx[0]
    t1, c1 = flows[i][0], flows[i][1]
    t0 = flows[i - 1][0] if i > 0 else t1 - 0.5
    if t1 - t0 <= 0 or not c1:
        return 0.0
    return c1 * _rot_clamp((t - t0) / (t1 - t0), 0.0, 1.0)


def rot_beta(years, betas=None):
    b = betas or ROT_BETA
    return b["long"] if years > 5 else (b["mid"] if years >= 2 else b["short"])


def rot_tr_fixed(knots, T, flows, price, accr0=0.0, betas=None, tax=True, y0=None):
    """Годовая полная доходность фиксированной бумаги, % годовых.
    flows — [(t лет, купон, номинал)] в % номинала; price — чистая цена, % номинала; accr0 — НКД, % номинала.
    Доходность на горизонте = y0 + бета x (изменение ключевой ставки за горизонт); цена — полная переоценка потоков."""
    dirty0 = price + accr0
    if y0 is None:
        y0 = rot_ytm(flows, dirty0)
    if y0 is None or dirty0 <= 0:
        return None
    k = (1.0 - ROT_TAX) if tax else 1.0
    life = max(f[0] for f in flows)
    dk = rot_rate(knots, T) - knots[0][1]
    yT = max(0.001, y0 + rot_beta(life, betas) * dk / 100.0)
    dirtyT = rot_pv(flows, T, yT)
    accT = rot_accr(flows, T)
    cleanT = max(0.0, dirtyT - accT)
    cash = sum((c * k + p) * rot_growth(knots, t, T) for t, c, p in flows if t <= T + 1e-9)
    gain_tax = ROT_TAX * max(0.0, cleanT - price) if tax else 0.0
    val = cleanT + accT * k + cash - gain_tax
    if val <= 0:
        return None
    return ((val / dirty0) ** (1.0 / T) - 1.0) * 100.0


def rot_tr_fixed_approx(knots, T, y0, mdur, conv, betas=None, tax=True, life=None):
    """То же приближённо — по модифицированной дюрации и выпуклости (когда графика купонов нет). y0 — % годовых."""
    k = (1.0 - ROT_TAX) if tax else 1.0
    dy = max(-y0 / 100.0 + 0.001, rot_beta(life or mdur or 5.0, betas) * (rot_rate(knots, T) - knots[0][1]) / 100.0)
    dp = -mdur * dy + 0.5 * (conv or 0.0) * dy * dy        # изменение цены дробью (бумага у номинала)
    inc = 0.0
    t = 0.0
    while t < T - 1e-9:
        e = min(t + 0.5, T)
        inc += y0 / 100.0 * (e - t) * k * rot_growth(knots, e, T)
        t = e
    val = 1.0 + dp + inc - (ROT_TAX * max(0.0, dp) if tax else 0.0)
    return ((val ** (1.0 / T)) - 1.0) * 100.0 if val > 0 else None


def rot_breakeven(k0, T, spread, fixed_fn, tax=True, floor=ROT_FLOOR, hi=None):
    """Параллельное снижение ключевой ставки за год (п.п.), при котором доходность фикса равна доходности флоатера.
    fixed_fn(knots, T) -> % годовых. Возвращает {"value": X|None, "state": "ok"|"always"|"never"}:
    always — фикс впереди даже при росте ставки на 5 п.п.; never — не догоняет даже при снижении до нижней границы."""
    top = hi if hi is not None else max(0.0, k0 - floor)

    def diff(cut):
        kn = rot_path("cut", k0, floor=floor, cut=cut)
        f = fixed_fn(kn, T)
        if f is None:
            return None
        return f - rot_tr_floater(kn, T, spread, tax)
    lo = -5.0
    dl, dh = diff(lo), diff(top)
    if dl is None or dh is None:
        return {"value": None, "state": "none"}
    if dl >= 0:
        return {"value": lo, "state": "always"}
    if dh < 0:
        return {"value": top, "state": "never"}
    a, b = lo, top
    for _ in range(60):
        m = (a + b) / 2
        dm = diff(m)
        if dm is None:
            break
        if dm < 0:
            a = m
        else:
            b = m
        if b - a < 1e-4:
            break
    return {"value": round((a + b) / 2, 2), "state": "ok"}


def rot_indicator(kbd10, kbd1, key):
    """Индикатор 0–100: 50 + 4 x A + 3 x S, где A = КБД 10 лет − ключевая (п.п., ограничено ±8), S = КБД 10 лет − КБД 1 год (п.п., ±6).
    Описывает, насколько длинный конец выше ключевой ставки и насколько кривая крута. Это не сигнал к сделке."""
    if kbd10 is None or kbd1 is None or key is None:
        return None
    a, s = kbd10 - key, kbd10 - kbd1
    score = _rot_clamp(50.0 + 4.0 * _rot_clamp(a, -8.0, 8.0) + 3.0 * _rot_clamp(s, -6.0, 6.0), 0.0, 100.0)
    if score < 35:
        lab = "Кривая обратная: длинные ставки ниже ключевой, снижение во многом уже заложено в цены."
    elif score > 65:
        lab = "Длинные ставки заметно выше ключевой, кривая крутая: фикс даёт больший текущий доход."
    else:
        lab = "Нейтральная зона: длинные ставки близки к ключевой, кривая умеренная."
    return {"score": round(score, 1), "a": round(a, 2), "s": round(s, 2), "label": lab}


# ── графики потоков ──

def rot_flows_synth(b, today, years_max=None):
    """Расчётный график: полугодовые купоны назад от даты погашения. b: mat (ISO), coupon (% годовых), nominal.
    Возвращает [(t лет, купон % номинала, номинал %)]."""
    try:
        mat = datetime.strptime(b["mat"], "%Y-%m-%d")
        t0 = datetime.strptime(today, "%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return []
    c = (b.get("coupon") or 0.0) / 2.0
    out, k = [], 0
    while True:
        d = mat - timedelta(days=round(182.625 * k))
        t = (d - t0).days / 365.0
        if t <= 0:
            break
        out.append((t, c, 100.0 if k == 0 else 0.0))
        k += 1
        if k > 80:
            break
    return sorted(out)


def rot_flows_moex(isin, today, face):
    """Потоки по графику выпуска на Мосбирже, % номинала; None, если получить не удалось."""
    try:
        bz = moex_bondization(isin)
        if not bz:
            return None
        fl, _k, _e = bond_flows(bz, today, face)
        if not fl:
            return None
        t0 = datetime.strptime(today, "%Y-%m-%d")
        sc = 100.0 / face
        return [((datetime.strptime(d, "%Y-%m-%d") - t0).days / 365.0, (c or 0.0) * sc, (p or 0.0) * sc) for d, c, p in fl]
    except Exception:  # noqa: BLE001
        return None


# ── вселенная бумаг (фоновая загрузка) ──

def _rot_is_floater(r):
    if r.get("floating") is not None:               # поле из screener_payload (справочник T-Invest / тип облигации ISS)
        return bool(r["floating"])
    nm = (r.get("name") or "")
    if r.get("kind") == "ofz":
        return "ПК" in nm.upper()
    try:
        info = tcat_info(r.get("isin")) if r.get("isin") else None
    except Exception:  # noqa: BLE001
        info = None
    return bool(info and info.get("floating"))


def _rot_build():
    snap = {"t": time.time(), "errors": []}
    rows = []
    try:
        try:
            allr = screener_payload()["rows"]          # с признаком floating, fl_label и fl_base
        except Exception:  # noqa: BLE001
            allr = screener_rows()
        rows = [r for r in allr if r.get("cur") == "RUB"]
    except Exception as e:  # noqa: BLE001
        snap["errors"].append("торги Мосбиржи: %s" % (str(e)[:100] or e.__class__.__name__))
    try:
        ser = key_rate_series()
        snap["k0"] = ser[-1][1] if ser else None
    except Exception as e:  # noqa: BLE001
        snap["k0"] = None
        snap["errors"].append("ключевая ставка: %s" % (str(e)[:100] or e.__class__.__name__))
    try:
        info = keyrate_forecast_info()
        snap["fpath"] = info.get("path") or []
        snap["fsrc"] = info.get("source_name") or ""
        if snap["k0"] is None:
            snap["k0"] = info.get("key_rate")
    except Exception:  # noqa: BLE001
        snap["fpath"], snap["fsrc"] = [], ""
    try:
        snap["kbd"] = kbd_curve()
    except Exception:  # noqa: BLE001
        snap["kbd"] = []
    try:
        snap["meet"] = (cbr_meetings() or {}).get("dates") or []
    except Exception:  # noqa: BLE001
        snap["meet"] = []
    fixed, floats = [], []
    for r in rows:
        if r.get("kind") not in ("ofz", "corp"):
            continue
        if r.get("kind") == "ofz" and r.get("dur") is None:
            continue
        (floats if _rot_is_floater(r) else fixed).append(r)
    snap["ofz"] = sorted([r for r in fixed if r["kind"] == "ofz"], key=lambda r: -(r.get("turn") or 0))
    floats = [r for r in floats if r.get("fl_base") != "infl"]       # купон, привязанный к инфляции, от ставки не зависит
    snap["floats"] = sorted(floats, key=lambda r: -(r.get("turn") or 0))[:30]
    return snap


def _rot_worker():
    try:
        snap = _rot_build()
        err = ""
    except Exception as e:  # noqa: BLE001
        snap, err = None, str(e)[:160] or e.__class__.__name__
    with _rot_lock:
        if snap is not None:
            _rot_state["snap"], _rot_state["t"] = snap, time.time()
        _rot_state["err"], _rot_state["busy"] = err, False


def rot_snapshot(wait=0.0):
    """(снимок, идёт ли загрузка). Снимок обновляется в фоне; устаревший отдаётся, пока считается новый."""
    with _rot_lock:
        fresh = _rot_state["snap"] is not None and time.time() - _rot_state["t"] < ROT_TTL
        if not fresh and not _rot_state["busy"]:
            _rot_state["busy"] = True
            threading.Thread(target=_rot_worker, daemon=True).start()
    if wait:
        end = time.time() + wait
        while time.time() < end and _rot_state["busy"] and _rot_state["snap"] is None:
            time.sleep(0.05)
    with _rot_lock:
        return _rot_state["snap"], _rot_state["busy"], _rot_state["err"]


# ── модельные расчёты на основе снимка ──

def rot_default_bond(ofz):
    """Самая длинная ликвидная фиксированная ОФЗ: оборот не ниже трети медианного среди ОФЗ."""
    cand = [r for r in ofz if r.get("mat") and r.get("price") and r.get("yield")]
    if not cand:
        return None
    turns = sorted(r.get("turn") or 0 for r in cand)
    thr = turns[len(turns) // 2] / 3.0
    liq = [r for r in cand if (r.get("turn") or 0) >= thr] or cand
    return max(liq, key=lambda r: r["mat"])


def rot_fixed_model(b, today):
    """Параметры фикса для расчёта: потоки, цена, НКД, y0 и метод. b — строка скринера."""
    face = float(b.get("nominal") or 1000.0)
    price = float(b["price"])
    flows, method = None, "approx"
    if b.get("isin"):
        flows = rot_flows_moex(b["isin"], today, face)
        if flows:
            method = "moex"
    if not flows and b.get("coupon") is not None:
        flows = rot_flows_synth(b, today)
        if flows:
            method = "synth"
    accr = (float(b["nkd"]) / face * 100.0) if b.get("nkd") not in (None, "") else (rot_accr(flows, 0.0) if flows else 0.0)
    y0 = rot_ytm(flows, price + accr) if flows else None
    if y0 is None and flows:
        y0 = float(b["yield"]) / 100.0
    return {"flows": flows, "price": price, "accr": accr, "y0": y0, "method": method, "face": face}


def rot_matrix(k0, fpath, spread, fm, bond, betas, tax, today):
    """Матрица сценарий x горизонт."""
    rows = []
    for key, name in ROT_SCN:
        kn = rot_path(key, k0, fpath, today)
        row = {"key": key, "name": name, "note": ROT_SCN_NOTE[key], "cells": [], "avail": kn is not None}
        for T, lab in ROT_HORIZONS:
            if kn is None:
                row["cells"].append(None)
                continue
            fl = rot_tr_floater(kn, T, spread, tax)
            fx = rot_tr_fixed(kn, T, fm["flows"], fm["price"], fm["accr"], betas, tax, fm["y0"]) if fm["flows"] else (
                rot_tr_fixed_approx(kn, T, bond["yield"], (bond.get("dur") or 5.0) / (1 + bond["yield"] / 100.0), (bond.get("dur") or 5.0) ** 2, betas, tax))
            row["cells"].append({"T": T, "fixed": None if fx is None else round(fx, 2), "float": round(fl, 2),
                                 "diff": None if fx is None else round(fx - fl, 2),
                                 "win": None if fx is None else ("fixed" if fx > fl else "float")})
        rows.append(row)
    return rows


def rot_meeting_dates(meet, n, today):
    """n ближайших заседаний ЦБ после сегодня; если календаря нет — ориентировочно каждые 6 недель."""
    fut = [d for d in meet if d > today][:n]
    approx = len(fut) < n
    d0 = datetime.strptime(fut[-1] if fut else today, "%Y-%m-%d")
    while len(fut) < n:
        d0 += timedelta(days=42)
        fut.append(d0.strftime("%Y-%m-%d"))
    return fut, approx


def rot_ladder(amount, n, mode, dates, d_fixed, d_float=ROT_FL_DUR):
    """Модельный план: перекладка суммы во флоатерах в фикс траншами по заседаниям.
    equal — равные доли; front — убывающие (n, n-1, ..., 1 долей). Возвращает список траншей с дюрацией портфеля после каждого."""
    n = max(1, int(n))
    wts = [float(n - i) for i in range(n)] if mode == "front" else [1.0] * n
    s = sum(wts)
    out, cum = [], 0.0
    for d, w in zip(dates, wts):
        part = w / s
        cum += part
        out.append({"date": d, "share": round(part * 100, 1), "rub": round(amount * part, 2), "cum_share": round(cum * 100, 1),
                    "duration": round(cum * d_fixed + (1 - cum) * d_float, 2)})
    return out


def rot_fl_lag(r, kn, k0, today):
    """Ожидаемые купоны флоатера на 12 месяцев вперёд с учётом лага фиксации.
    КС: ставка купона фиксируется на начало периода; RUONIA: среднее за период, сдвинутое на ~7 дней назад.
    Спред оценивается как текущий купон минус текущая ставка."""
    c0 = r.get("coupon")
    if c0 is None or not r.get("price"):
        return None
    base = r.get("fl_base")
    ru = base == "ruonia" if base else r.get("kind") == "ofz"
    P = 0.5 if r.get("kind") == "ofz" else 0.25
    try:
        nxt = (datetime.strptime(r["next"], "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days / 365.0
    except Exception:  # noqa: BLE001
        nxt = P
    nxt = _rot_clamp(nxt, 0.0, P)
    cps = [c0]
    s = nxt
    while s < 1.0 - 1e-9 and len(cps) < 8:
        if ru:
            a = max(0.0, s - ROT_RU_LAG)
            dlt = rot_avg(kn, a, a + P) - k0
        else:
            dlt = rot_rate(kn, s) - k0
        cps.append(c0 + dlt)
        s += P
    n = max(1, int(round(1.0 / P)))
    use = cps[:n] if len(cps) >= n else cps
    avg = sum(use) / len(use)
    cy0 = c0 / r["price"] * 100.0
    cyf = avg / r["price"] * 100.0
    return {"id": r["id"], "isin": r.get("isin"), "name": r.get("name"), "link": r.get("fl_label") or ("RUONIA" if ru else "КС / RUONIA (не определено)"),
            "coupon": round(c0, 2), "next": r.get("next"), "price": r.get("price"), "yield": r.get("yield"),
            "future": [round(x, 2) for x in cps[1:4]], "avg12": round(avg, 2), "cy_now": round(cy0, 2), "cy_fwd": round(cyf, 2),
            "delta": round(cyf - cy0, 2), "turn": r.get("turn")}


def rot_payload(cfg, acc, q, force=False):
    q = q or {}
    snap, busy, err = rot_snapshot()
    if snap is None:
        return {"loading": bool(busy), "error": err} if err else {"loading": True}
    k0 = snap.get("k0")
    if k0 is None or not snap.get("ofz"):
        msg = "; ".join(snap.get("errors") or []) or "нет данных о торгах ОФЗ или ключевой ставке"
        with _rot_lock:
            _rot_state["t"] = 0.0                      # следующая загрузка повторит попытку
        return {"error": "Не удалось получить данные: " + msg}
    today = date.today().isoformat()
    spread = _rot_num(q.get("spread"), 0.0, 10.0, 2.0)
    tax = q.get("tax") != "0"
    betas = {"long": _rot_num(q.get("b_long"), 0.0, 1.5, ROT_BETA["long"]), "mid": _rot_num(q.get("b_mid"), 0.0, 1.5, ROT_BETA["mid"]),
             "short": _rot_num(q.get("b_short"), 0.0, 1.5, ROT_BETA["short"])}
    ofz = snap["ofz"]
    bond = next((r for r in ofz if r["id"] == q.get("bond")), None) or rot_default_bond(ofz)
    if bond is None:
        return {"error": "Нет подходящих фиксированных ОФЗ в торгах."}
    fm = rot_fixed_model(bond, today)
    method = {"moex": "полная переоценка по графику купонов выпуска (Мосбиржа)",
              "synth": "полная переоценка по расчётному графику (полугодовые купоны до погашения)",
              "approx": "приближение: модифицированная дюрация и выпуклость"}[fm["method"]]
    matrix = rot_matrix(k0, snap.get("fpath"), spread, fm, bond, betas, tax, today)
    be = []
    for T, lab in ROT_HORIZONS:
        if fm["flows"]:
            fn = lambda kn, TT: rot_tr_fixed(kn, TT, fm["flows"], fm["price"], fm["accr"], betas, tax, fm["y0"])
        else:
            md = (bond.get("dur") or 5.0) / (1 + bond["yield"] / 100.0)
            fn = lambda kn, TT, md=md: rot_tr_fixed_approx(kn, TT, bond["yield"], md, md * md, betas, tax)
        b = rot_breakeven(k0, T, spread, fn, tax)
        be.append(dict(b, T=T, label=lab))
    kb = snap.get("kbd") or []
    interp = lambda y: _interp(kb, y) if kb else None
    ind = rot_indicator(interp(10.0), interp(1.0), k0)
    if ind:
        ind.update(kbd10=round(interp(10.0), 2), kbd1=round(interp(1.0), 2), key=k0)
    # лаг фиксации флоатеров
    scn = q.get("scn") if q.get("scn") in dict(ROT_SCN) else ("cbr" if snap.get("fpath") else "smooth")
    kn = rot_path(scn, k0, snap.get("fpath"), today) or rot_path("flat", k0)
    lag = [x for x in (rot_fl_lag(r, kn, k0, today) for r in snap.get("floats") or []) if x]
    # лесенка
    amount = _rot_num(q.get("amount"), 0.0, 1e12, 1000000.0)
    n = int(_rot_num(q.get("n"), 1, 12, 6))
    mode = "front" if q.get("mode") == "front" else "equal"
    dates, approx = rot_meeting_dates(snap.get("meet") or [], n, today)
    d_fixed = bond.get("dur") or (rot_dur_conv(fm["flows"], fm["y0"])[0] if fm["flows"] and fm["y0"] is not None else 5.0)
    ladder = rot_ladder(amount, n, mode, dates, d_fixed)
    lst = [{"id": r["id"], "name": r["name"], "mat": r["mat"], "yield": r["yield"], "dur": r.get("dur"), "turn": r.get("turn")} for r in ofz
           if r.get("mat") and (r.get("turn") or 0) > 0][:40]
    if not any(x["id"] == bond["id"] for x in lst):
        lst.insert(0, {"id": bond["id"], "name": bond["name"], "mat": bond["mat"], "yield": bond["yield"], "dur": bond.get("dur"), "turn": bond.get("turn")})
    return {"loading": False, "today": today, "key_rate": k0, "forecast_src": snap.get("fsrc"), "forecast_ok": bool(snap.get("fpath")),
            "spread": spread, "tax": tax, "betas": betas, "floor": ROT_FLOOR,
            "bond": {"id": bond["id"], "name": bond["name"], "isin": bond.get("isin"), "mat": bond["mat"], "price": bond["price"], "yield": bond["yield"],
                     "dur": bond.get("dur"), "coupon": bond.get("coupon"), "beta": rot_beta(max([f[0] for f in fm["flows"]] or [0]) if fm["flows"] else (bond.get("dur") or 5) * 1.5, betas)},
            "bonds": lst, "method": method, "method_key": fm["method"], "horizons": [{"T": T, "label": l} for T, l in ROT_HORIZONS],
            "scenarios": [{"key": k, "name": n_, "note": ROT_SCN_NOTE[k]} for k, n_ in ROT_SCN],
            "matrix": matrix, "breakeven": be, "indicator": ind,
            "lag": {"scn": scn, "rows": lag}, "ladder": {"rows": ladder, "amount": amount, "n": n, "mode": mode, "approx_dates": approx,
                                                        "d_fixed": round(d_fixed, 2), "d_float": ROT_FL_DUR},
            "errors": snap.get("errors") or []}


# ── дюрационный разрыв по портфелю ──

ROT_GAP_SCN = [("p+100", "Параллельно +100 б.п.", 1.0, None), ("p-100", "Параллельно −100 б.п.", -1.0, None),
               ("p+300", "Параллельно +300 б.п.", 3.0, None), ("p-300", "Параллельно −300 б.п.", -3.0, None),
               ("steep", "Крутизна: длинный конец +100 б.п.", 1.0, "long"), ("flat", "Выполаживание: длинный конец −100 б.п.", -1.0, "long")]


def rot_value_change(mdur, conv, dy):
    """Относительное изменение цены (дробью) при сдвиге доходности на dy (дробью): -D*dy + C*dy^2/2."""
    return -mdur * dy + 0.5 * conv * dy * dy


def rot_gap(rows, goal):
    """Дюрационный разрыв и стресс-сценарии по строкам облигаций портфеля (value_rub, dur, mdur, convexity, ytm, floating)."""
    items = []
    for r in rows:
        v = r.get("value_rub") or 0.0
        if v <= 0:
            continue
        fl = bool(r.get("floating"))
        md = ROT_FL_DUR if fl else (r.get("mdur") if r.get("mdur") is not None else
                                    (r.get("dur") / (1 + (r.get("ytm") or 0) / 100.0) if r.get("dur") else None))
        if md is None:
            continue
        cv = 0.0 if fl else (r.get("convexity") if r.get("convexity") is not None else md * md + md)
        items.append({"name": r.get("name"), "v": v, "md": md, "cv": cv, "dur": ROT_FL_DUR if fl else (r.get("dur") or md), "fl": fl})
    tot = sum(x["v"] for x in items)
    if not tot:
        return {"empty": True}
    dur = sum(x["v"] * x["dur"] for x in items) / tot
    mdur = sum(x["v"] * x["md"] for x in items) / tot
    gap = dur - goal
    kind, text = _risk_gap_text(gap)
    sc = []
    for key, name, dy, part in ROT_GAP_SCN:
        d = 0.0
        for x in items:
            if x["fl"]:
                continue
            w = 1.0 if part is None else _rot_clamp((x["dur"] - 2.0) / 8.0, 0.0, 1.0)
            d += x["v"] * rot_value_change(x["md"], x["cv"], dy * w / 100.0)
        sc.append({"key": key, "name": name, "pct": d / tot * 100.0, "rub": d})
    return {"empty": False, "value": tot, "duration": dur, "mdur": mdur, "goal": goal, "gap": gap, "gap_kind": kind, "gap_text": text,
            "floating_share": sum(x["v"] for x in items if x["fl"]) / tot * 100.0, "scenarios": sc, "count": len(items)}


def rot_gap_payload(cfg, acc, q, force=False):
    q = q or {}
    goal = _rot_num(q.get("horizon"), 0.1, 50.0, 3.0)
    try:
        rep = build_bonds(cfg, acc)
    except Exception as e:  # noqa: BLE001
        return {"empty": True, "error": "Позиции по облигациям недоступны: %s" % (str(e)[:120] or e.__class__.__name__)}
    out = rot_gap((rep or {}).get("rows") or [], goal)
    out["goal"] = goal
    return out


API_GET["/api/rot"] = rot_payload
API_GET["/api/rot/gap"] = rot_gap_payload
