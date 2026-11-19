# ═══════════════════════════════ индекс страха и жадности российского рынка ═══════════════════════════════
# 0 — крайний страх, 100 — крайняя жадность. Семь компонентов, у каждого оценка 0–100 = процентный ранг сегодняшнего значения
# среди значений за последние 2 года; итог — среднее по доступным компонентам. Наружу уходят только обезличенные GET-запросы
# к iss.moex.com (история индексов и закрытия акций TQBR); данные портфеля не используются.
import bisect
from collections import deque

FNG_WINDOW_DAYS = 730            # окно для процентного ранга
FNG_FULL_PTS = 120               # меньше точек истории -> низкая достоверность
FNG_MIN_PTS = 10                 # меньше точек оценку не считаем
FNG_DAYS = 930                   # глубина загрузки закрытий акций (~2,5 года)
FNG_HIST_DAYS = 400              # сколько дней своей истории индекса считаем
FNG_CL_KEY = "fng_cl1:"          # закрытия TQBR за день: {secid: close}, по ключу на дату
FNG_SP_KEY = "fng_sp1"           # спред ВДО к КБД по дням: {дата: п.п.}
FNG_FL_KEY = "fng_fl1"           # поток «акции минус фонды денежного рынка» по дням
FNG_TTL = 1800
FNG_SRV_TTL = 300                # сколько держим в памяти готовый ответ сервера данных
FNG_COMPS = [
    ("mom", "Моментум", False), ("breadth", "Ширина рынка", False), ("hl", "Новые максимумы и минимумы", False),
    ("vol", "Волатильность", True), ("safe", "Спрос на защитные активы", True), ("spread", "Спрос на риск в долге", True),
    ("flow", "Поток денег", False)]
FNG_LABELS = [(24, "Крайний страх"), (44, "Страх"), (55, "Нейтрально"), (75, "Жадность"), (100, "Крайняя жадность")]
_fng = {"running": False, "res": None, "t": 0.0, "err": None, "have": 0, "need": 0, "cl": {}, "phase": ""}
_fng_lock = threading.Lock()
_fng_rl = {"t": 0.0, "lock": threading.Lock()}


def fng_label(v):
    if v is None:
        return None
    v = round(v)
    for hi, t in FNG_LABELS:
        if v <= hi:
            return t
    return FNG_LABELS[-1][1]


def fng_pct(v, hist):
    """Процентный ранг v среди hist (hist включает v): доля меньших + половина равных, 0–100."""
    n = len(hist)
    if not n:
        return None
    less = sum(1 for x in hist if x < v)
    eq = sum(1 for x in hist if x == v)
    return 100.0 * (less + 0.5 * eq) / n


def _fng_dadd(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def fng_asof(keys, ser, d, gap=5):
    """Значение ряда на дату d или последнее известное не старше gap дней; keys — отсортированные даты ряда."""
    i = bisect.bisect_right(keys, d) - 1
    if i < 0:
        return None
    k = keys[i]
    if k != d and (datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(k, "%Y-%m-%d")).days > gap:
        return None
    return ser[k]


# ── ряды компонентов (чистые функции: словарь {дата: значение} -> словарь {дата: сырое значение}) ──

def fng_sma_dev(ser, n):
    """Отклонение закрытия от скользящей средней за n наблюдений, %."""
    ks = sorted(ser)
    out, s, win = {}, 0.0, deque()
    for k in ks:
        v = ser[k]
        win.append(v)
        s += v
        if len(win) > n:
            s -= win.popleft()
        if len(win) == n and s:
            out[k] = (v / (s / n) - 1) * 100.0
    return out


def fng_safe_series(bonds, stocks, n=20):
    """Доходность гособлигаций за n торговых дней минус доходность акций, п.п. (календарь — даты индекса акций)."""
    ks = sorted(stocks)
    bk = sorted(bonds)
    out = {}
    for i in range(n, len(ks)):
        d, d0 = ks[i], ks[i - n]
        b1, b0 = fng_asof(bk, bonds, d), fng_asof(bk, bonds, d0)
        if not b1 or not b0 or not stocks[d0]:
            continue
        out[d] = (b1 / b0 - 1) * 100.0 - (stocks[d] / stocks[d0] - 1) * 100.0
    return out


def fng_breadth_hl(closes, min_stocks=30):
    """closes: {дата: {secid: close}}. Возвращает ({дата: % акций выше своей SMA50}, {дата: (макс. за 52 нед. − мин.) / число, %})."""
    dates = sorted(d for d, c in closes.items() if c and len(c) >= min_stocks)
    obs = {}
    for i, d in enumerate(dates):
        for s, c in closes[d].items():
            if c:
                obs.setdefault(s, []).append((i, float(c)))
    n = len(dates)
    ab, n50, hi, lo, n250 = [0] * n, [0] * n, [0] * n, [0] * n, [0] * n
    for lst in obs.values():
        w50, s50 = deque(), 0.0
        mx, mn = deque(), deque()          # монотонные очереди (индекс наблюдения, значение), окно 250
        for j, (i, c) in enumerate(lst):
            w50.append(c)
            s50 += c
            if len(w50) > 50:
                s50 -= w50.popleft()
            if len(w50) >= 40:
                n50[i] += 1
                if c > s50 / len(w50):
                    ab[i] += 1
            while mx and mx[-1][1] <= c:
                mx.pop()
            mx.append((j, c))
            while mx[0][0] <= j - 250:
                mx.popleft()
            while mn and mn[-1][1] >= c:
                mn.pop()
            mn.append((j, c))
            while mn[0][0] <= j - 250:
                mn.popleft()
            if j + 1 >= 120:
                n250[i] += 1
                if c >= mx[0][1]:
                    hi[i] += 1
                if c <= mn[0][1]:
                    lo[i] += 1
    br, hl = {}, {}
    for i, d in enumerate(dates):
        if n50[i] >= min_stocks:
            br[d] = 100.0 * ab[i] / n50[i]
        if n250[i] >= min_stocks:
            hl[d] = 100.0 * (hi[i] - lo[i]) / n250[i]
    return br, hl


def fng_flow_parse(j):
    """Поток в акции минус потоки в фонды денежного рынка из ответа flows/summary (формат сервера разбираем терпимо). None — не нашли."""
    rows = j
    if isinstance(j, dict):
        for k in ("rows", "items", "classes", "data", "flows"):
            if isinstance(j.get(k), (list, dict)):
                rows = j[k]
                break
    if isinstance(rows, dict):
        rows = [dict(v, name=k) if isinstance(v, dict) else {"name": k, "net": v} for k, v in rows.items()]
    if not isinstance(rows, list):
        return None
    sh, mm, fs, fm = 0.0, 0.0, False, False
    for r in rows:
        if not isinstance(r, dict):
            continue
        lab = " ".join(str(r.get(k) or "") for k in ("key", "class", "name", "title", "label", "asset")).lower()
        val = None
        for k in ("net", "net_flow", "netflow", "flow", "delta", "value"):
            if isinstance(r.get(k), (int, float)):
                val = float(r[k])
                break
        if val is None:
            continue
        if any(w in lab for w in ("ликвид", "денеж", "money", "lqdt", "tmon", "sbmm", "akmm")):
            mm += val
            fm = True
        elif any(w in lab for w in ("акци", "share", "equity", "stock")):
            sh += val
            fs = True
    return sh - mm if fs and fm else None


def fng_score(ser, d, invert, gap=5):
    """(оценка 0–100, число точек истории, сырое значение) компонента на дату d; None — нет значения."""
    ks = sorted(ser)
    v = fng_asof(ks, ser, d, gap)
    if v is None:
        return None
    lo = bisect.bisect_right(ks, _fng_dadd(d, -FNG_WINDOW_DAYS))
    hi = bisect.bisect_right(ks, d)
    hist = [ser[k] for k in ks[lo:hi]]
    if v not in hist:
        hist.append(v)
    if len(hist) < FNG_MIN_PTS:
        return None
    sc = fng_pct(v, hist)
    return (100.0 - sc if invert else sc), len(hist), v


def fng_mean(scores):
    """Среднее по доступным компонентам (веса перенормируются)."""
    xs = [s for s in scores if s is not None]
    return sum(xs) / len(xs) if xs else None


FNG_GAP = {"spread": 10, "flow": 10}


def fng_note(key, raw, score):
    f = lambda x, p=1: ("%+." + str(p) + "f") % x
    if key == "mom":
        return "IMOEX %s%% к 125-дневной средней: %s" % (f(raw), "рынок растёт выше своего тренда" if raw > 0 else "рынок ниже своего тренда")
    if key == "breadth":
        return "%.0f%% акций торгуются выше своей 50-дневной средней" % raw
    if key == "hl":
        return "Разница между долей акций на годовых максимумах и минимумах: %s п.п." % f(raw)
    if key == "vol":
        return "Индекс волатильности RVI на %s%% относительно 50-дневной средней: %s" % (f(raw), "тревога растёт" if raw > 0 else "спокойнее обычного")
    if key == "safe":
        return "Гособлигации за 20 дней обогнали акции на %s п.п." % f(raw) if raw > 0 else "Акции за 20 дней обогнали гособлигации на %.1f п.п." % -raw
    if key == "spread":
        return "Спред ВДО к кривой ОФЗ %.2f п.п.: %s" % (raw, "шире обычного, инвесторы требуют больше за риск" if score < 50 else "уже обычного")
    return "Чистый поток в акции за вычетом фондов денежного рынка за день: %s" % f(raw, 0)


def fng_assemble(imoex, rvi, rgb, closes, spread, flow, today=None):
    """Собирает результат из рядов. imoex/rvi/rgb/spread/flow — {дата: значение}; closes — {дата: {secid: close}}. Чистая функция."""
    raw = {}
    if len(imoex) >= 20:
        raw["mom"] = fng_sma_dev(imoex, 125)
        if rvi:
            raw["vol"] = fng_sma_dev(rvi, 50)
        if rgb:
            raw["safe"] = fng_safe_series(rgb, imoex)
    if closes:
        raw["breadth"], raw["hl"] = fng_breadth_hl(closes)
    if spread:
        raw["spread"] = dict(spread)
    if flow:
        raw["flow"] = dict(flow)
    raw = {k: v for k, v in raw.items() if v}
    cal = sorted(imoex)
    if not cal:
        return {"value": None, "label": None, "ts": None, "components": [], "history": [], "prev": {}, "low_conf": False}
    last = cal[-1]
    meta = {k: (n, inv) for k, n, inv in FNG_COMPS}
    comps = []
    for k, n, inv in FNG_COMPS:
        if k not in raw:
            continue
        r = fng_score(raw[k], last, inv, FNG_GAP.get(k, 5))
        if r:
            sc, npts, v = r
            comps.append({"key": k, "name": n, "raw": round(v, 3), "score": round(sc, 1), "conf": "ok" if npts >= FNG_FULL_PTS else "low",
                          "pts": npts, "note": fng_note(k, v, sc)})
    val = fng_mean([c["score"] for c in comps])
    for c in comps:
        c["weight"] = round(1.0 / len(comps), 4)
    # собственная история индекса: прошлые даты считаем только по компонентам с достаточной историей
    hist = []
    for d in [x for x in cal if x >= _fng_dadd(last, -FNG_HIST_DAYS)]:
        sc = []
        for k, ser in raw.items():
            if d == last:
                continue
            r = fng_score(ser, d, meta[k][1], FNG_GAP.get(k, 5))
            if r and r[1] >= FNG_FULL_PTS:
                sc.append(r[0])
        v = val if d == last else (fng_mean(sc) if len(sc) >= 3 else None)
        if v is not None:
            hist.append({"d": d, "v": round(v, 1)})
    prev = {}
    for name, n in (("day", 1), ("week", 7), ("month", 30), ("year", 365)):
        tgt = _fng_dadd(last, -n)
        c = [h for h in hist if h["d"] <= tgt]
        prev[name] = c[-1] if c else None
    return {"value": None if val is None else round(val, 1), "label": fng_label(val), "ts": last, "components": comps, "history": hist,
            "prev": prev, "low_conf": any(c["conf"] == "low" for c in comps) or len(comps) < 4}


# ── загрузка данных ──

def _fng_throttle():
    with _fng_rl["lock"]:
        w = _fng_rl["t"] + 0.5 - time.time()
        if w > 0:
            time.sleep(w)
        _fng_rl["t"] = time.time()


def fng_fetch_day(d):
    """Закрытия акций TQBR за день: {secid: close}. Сначала общий сборщик (если есть), иначе страницы ISS не чаще 2 запросов/с."""
    fn = globals().get("stock_history_closes")
    if fn:
        try:
            r = fn(d)
            if isinstance(r, dict):
                return {k: float(v) for k, v in r.items() if v}
        except Exception:  # noqa: BLE001
            pass
    out, start = {}, 0
    for _ in range(10):
        _fng_throttle()
        j = json.loads(http_text(
            "https://iss.moex.com/iss/history/engines/stock/markets/shares/boards/TQBR/securities.json?iss.meta=off&date=%s&start=%d"
            "&iss.only=history,history.cursor&history.columns=SECID,CLOSE,NUMTRADES" % (d, start), 40))
        rows = (j.get("history") or {}).get("data") or []
        for s, c, nt in rows:
            if c and (nt or 0) > 0:
                out[s] = float(c)
        cur = ((j.get("history.cursor") or {}).get("data") or [[0, 0, 100]])[0]
        start = cur[0] + len(rows)
        if not rows or start >= cur[1]:
            break
    return out


def fng_universe():
    fn = globals().get("stocks_universe")
    if not fn:
        return None
    try:
        u = fn()
        if isinstance(u, dict):
            u = list(u)
        s = {x if isinstance(x, str) else (x.get("secid") or x.get("id") or x.get("SECID")) for x in u}
        s.discard(None)
        return s or None
    except Exception:  # noqa: BLE001
        return None


def _fng_spread_points():
    """Спред ВДО (рейтинг BB и ниже, иначе BBB) к КБД по дням из накопленной истории раздела «Ставки»."""
    st = store()
    acc = st.get(FNG_SP_KEY) or {}
    f = globals().get("spreads_history_payload")
    if f:
        try:
            h = f()
            for b in ("BB и ниже", "BBB"):
                v = (h.get("series") or {}).get(b)
                if v and any(x is not None for x in v):
                    for d, x in zip(h["dates"], v):
                        if x is not None and d not in acc:
                            acc[d] = x
                    break
        except Exception:  # noqa: BLE001
            pass
    rows = (globals().get("_scr") or {}).get("rows") or []
    if rows and any(r.get("rating") for r in rows):
        xs = [r["spread"] for r in rows if r.get("kind") == "corp" and r.get("spread") is not None and r.get("cur") == "RUB"
              and r.get("rating") and rating_bucket(r["rating"]) == "BB и ниже"]
        if len(xs) >= 3:
            acc[date.today().isoformat()] = _med(xs)
    st.put(FNG_SP_KEY, acc)
    return acc


def _fng_flow_points():
    st = store()
    acc = st.get(FNG_FL_KEY) or {}
    try:
        j = ds_parsed("flows/summary", {"period": "day"})
        v = fng_flow_parse(j) if j is not None else None
        if v is not None:
            acc[date.today().isoformat()] = v
            st.put(FNG_FL_KEY, acc)
    except Exception:  # noqa: BLE001
        pass
    return acc


def _fng_publish(imoex, rvi, rgb, closes):
    uni = fng_universe()
    cl = {d: ({s: c for s, c in v.items() if s in uni} if uni else v) for d, v in closes.items()} if closes else {}
    res = fng_assemble(imoex, rvi, rgb, cl, _fng_spread_points(), _fng_flow_points())
    res["updated"] = time.time()
    with _fng_lock:
        _fng["res"] = res
        _fng["t"] = time.time()


def _fng_run():
    try:
        st = store()
        frm = _fng_dadd(date.today().isoformat(), -FNG_DAYS)
        ser = {}
        _fng["phase"] = "индексы"
        for k, code in (("imoex", "IMOEX"), ("rvi", "RVI"), ("rgb", "RGBITR")):
            try:
                ser[k] = bench_history(code, frm) or {}
            except Exception:  # noqa: BLE001
                ser[k] = {}
        closes = _fng["cl"]
        for d in [d for d in closes if d >= _fng_dadd(date.today().isoformat(), -3)]:
            del closes[d]                                # свежие дни перечитываем: закрытие сегодняшнего дня появляется вечером
        _fng_publish(ser["imoex"], ser["rvi"], ser["rgb"], closes)
        _fng["phase"] = "закрытия акций"
        today = date.today()
        days = [(today - timedelta(days=i)) for i in range(FNG_DAYS + 1)]
        days = [d.isoformat() for d in days if d.weekday() < 5]
        _fng["need"] = len(days)
        fetched = 0
        for d in days:                                   # от свежих к старым: непрерывный «хвост» уже даёт текущее значение
            if d in closes:
                continue
            v = st.get(FNG_CL_KEY + d)
            if v is None:
                try:
                    v = fng_fetch_day(d)
                except Exception:  # noqa: BLE001
                    continue
                recent = d >= _fng_dadd(today.isoformat(), -3)
                if v or not recent:
                    if d < today.isoformat():
                        st.put(FNG_CL_KEY + d, v)
                fetched += 1
            closes[d] = v
            _fng["have"] = sum(1 for x in closes.values() if x)
            if fetched and (fetched == 60 or fetched % 150 == 0):
                _fng_publish(ser["imoex"], ser["rvi"], ser["rgb"], {k: x for k, x in closes.items() if x})
        _fng["have"] = sum(1 for x in closes.values() if x)
        _fng_publish(ser["imoex"], ser["rvi"], ser["rgb"], {k: x for k, x in closes.items() if x})
        _fng["err"] = None
    except Exception as e:  # noqa: BLE001
        _fng["err"] = str(e)[:200]
    finally:
        _fng.update(running=False, phase="", t=time.time())


def _fng_kick(force=False):
    with _fng_lock:
        if _fng["running"] or (not force and _fng["res"] is not None and time.time() - _fng["t"] < FNG_TTL):
            return
        _fng["running"] = True
    threading.Thread(target=_fng_run, daemon=True).start()


def fng_compute():
    """Синхронный расчёт индекса целиком (для серверного воркера calc_worker.py): готовый словарь без флагов загрузки.
    Бросает исключение, если расчёт не удался. Внутри — тот же _fng_run, что и в фоновом потоке клиента."""
    with _fng_lock:
        _fng["running"] = True
    _fng["err"] = None
    _fng_run()
    with _fng_lock:
        res, err = _fng["res"], _fng["err"]
    if err or not res:
        raise RuntimeError(err or "нет результата")
    return dict(res)


def _fng_server(force):
    """Готовый индекс с сервера данных (calc/fng) либо None. Ответ держим в памяти FNG_SRV_TTL, чтобы опрос интерфейса не нагружал сервер."""
    if not force:
        hit = mem_get("fng_srv", FNG_SRV_TTL)
        if hit is not None:
            return hit
    j = ds_parsed("calc/fng")
    if not isinstance(j, dict) or j.get("value") is None:
        return None
    return mem_put("fng_srv", j)


def fng_payload(force=False):
    srv = _fng_server(force)
    if srv is not None:
        out = dict(srv)
        out.update(loading=False, progress={"have": 1, "need": 1, "phase": ""}, error=None, source="server")
        return out
    _fng_kick(force)
    with _fng_lock:
        res, running, err = _fng["res"], _fng["running"], _fng["err"]
    out = dict(res) if res else {"value": None, "label": None, "ts": None, "components": [], "history": [], "prev": {}, "low_conf": True}
    out.update(loading=running, progress={"have": _fng["have"], "need": _fng["need"], "phase": _fng["phase"]}, error=None if res or running else err)
    return out


API_GET["/api/fng"] = lambda cfg, acc, q, force: fng_payload(force)
