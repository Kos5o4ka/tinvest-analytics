# ═══════════════════════════════ технический анализ: чистые функции (без сети) ═══════════════════════════════
# Ряды — списки чисел; свечи — [{t, o, h, l, c, v}]. Периоды, где индикатор ещё не определён, заполнены None.
# Скользящие и RSI/ATR — как в большинстве терминалов: SMA — простое среднее; EMA — со сглаживанием 2/(n+1), старт со среднего первых n;
# RSI и ATR — сглаживание Уайлдера; Боллинджер — среднее ± k·стандартное отклонение (по генеральной совокупности).


def sma(vals, n):
    out = [None] * len(vals)
    if n <= 0 or len(vals) < n:
        return out
    s = sum(vals[:n])
    out[n - 1] = s / n
    for i in range(n, len(vals)):
        s += vals[i] - vals[i - n]
        out[i] = s / n
    return out


def ema(vals, n):
    out = [None] * len(vals)
    if n <= 0 or len(vals) < n:
        return out
    k = 2.0 / (n + 1)
    e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi(vals, n=14):
    out = [None] * len(vals)
    if len(vals) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = vals[i] - vals[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n

    def val(a, b):
        return 100.0 if b == 0 and a > 0 else 50.0 if b == 0 else 100.0 - 100.0 / (1 + a / b)
    out[n] = val(ag, al)
    for i in range(n + 1, len(vals)):
        d = vals[i] - vals[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = val(ag, al)
    return out


def macd(vals, fast=12, slow=26, sig=9):
    """-> (линия MACD, сигнальная линия, гистограмма) — три списка длины len(vals)."""
    ef, es = ema(vals, fast), ema(vals, slow)
    line = [(a - b) if a is not None and b is not None else None for a, b in zip(ef, es)]
    first = next((i for i, v in enumerate(line) if v is not None), None)
    signal = [None] * len(vals)
    if first is not None:
        part = ema([v for v in line[first:]], sig)
        signal[first:] = part
    hist = [(a - b) if a is not None and b is not None else None for a, b in zip(line, signal)]
    return line, signal, hist


def bollinger(vals, n=20, k=2.0):
    """-> (середина, верх, низ)."""
    mid = sma(vals, n)
    up, lo = [None] * len(vals), [None] * len(vals)
    for i in range(n - 1, len(vals)):
        w = vals[i - n + 1:i + 1]
        m = mid[i]
        sd = (sum((x - m) ** 2 for x in w) / n) ** 0.5
        up[i], lo[i] = m + k * sd, m - k * sd
    return mid, up, lo


def atr(candles, n=14):
    out = [None] * len(candles)
    if len(candles) <= n:
        return out
    tr = [candles[0]["h"] - candles[0]["l"]]
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]["c"]
        tr.append(max(c["h"] - c["l"], abs(c["h"] - p), abs(c["l"] - p)))
    a = sum(tr[1:n + 1]) / n
    out[n] = a
    for i in range(n + 1, len(candles)):
        a = (a * (n - 1) + tr[i]) / n
        out[i] = a
    return out


def levels(candles, wing=3, top=3):
    """Уровни поддержки/сопротивления: локальные экстремумы (максимум/минимум среди wing свечей по обе стороны),
    сгруппированные так, что ширина группы не больше 1,5·ATR. -> {support: [{price, touches}], resistance: [...]}; по близости к текущей цене, не больше top с каждой стороны."""
    candles = candles[-250:]                          # уровни по последним ~250 свечам: старые экстремумы уже не работают
    n = len(candles)
    if n < 2 * wing + 2:
        return {"support": [], "resistance": []}
    a = [x for x in atr(candles) if x is not None]
    tol = 1.5 * (a[-1] if a else (sum(c["h"] - c["l"] for c in candles) / n))
    pts = []
    for i in range(wing, n - wing):
        hs = [candles[j]["h"] for j in range(i - wing, i + wing + 1)]
        ls = [candles[j]["l"] for j in range(i - wing, i + wing + 1)]
        if candles[i]["h"] == max(hs):
            pts.append(candles[i]["h"])
        if candles[i]["l"] == min(ls):
            pts.append(candles[i]["l"])
    pts.sort()
    clusters = []
    for p in pts:
        if clusters and p - clusters[-1][0] <= tol:           # ширина группы не больше tol (без «цепочек»)
            clusters[-1].append(p)
        else:
            clusters.append([p])
    last = candles[-1]["c"]
    lv = [{"price": sum(c) / len(c), "touches": len(c)} for c in clusters]
    sup = sorted((x for x in lv if x["price"] <= last), key=lambda x: -x["price"])[:top]
    res = sorted((x for x in lv if x["price"] > last), key=lambda x: x["price"])[:top]
    return {"support": sup, "resistance": res}


def _vote(i, name, v, text):
    return {"id": i, "name": name, "vote": v, "text": text}


def ta_summary(candles):
    """Сводный сигнал голосованием: цена против SMA50 и SMA200, RSI(14), пересечение MACD, положение в полосах Боллинджера.
    Каждый индикатор даёт +1 (покупать), 0 или −1 (продавать); итог ≥ +2 — «покупать», ≤ −2 — «продавать», иначе «нейтрально».
    -> {signal, score, votes: [...], last: {c, sma50, sma200, rsi, macd, macd_signal, bb_up, bb_low, atr}} или {signal: None} при коротком ряде."""
    closes = [c["c"] for c in candles]
    if len(closes) < 30:
        return {"signal": None, "score": 0, "votes": [], "last": {}, "note": "Мало истории для расчёта индикаторов."}
    price = closes[-1]
    s50, s200 = sma(closes, 50)[-1], sma(closes, 200)[-1]
    r = rsi(closes)[-1]
    ml, sl, _ = macd(closes)
    mm, ms = ml[-1], sl[-1]
    _, bu, bl = bollinger(closes)
    bu, bl = bu[-1], bl[-1]
    at = atr(candles)[-1]
    votes = []
    if s50 is not None:
        votes.append(_vote("sma50", "Цена и SMA50", 1 if price > s50 else -1, "цена %s SMA50" % ("выше" if price > s50 else "ниже")))
    if s200 is not None:
        votes.append(_vote("sma200", "Цена и SMA200", 1 if price > s200 else -1, "цена %s SMA200" % ("выше" if price > s200 else "ниже")))
    if r is not None:
        votes.append(_vote("rsi", "RSI (14)", 1 if r < 30 else -1 if r > 70 else 0,
                           "перепроданность (RSI < 30)" if r < 30 else "перекупленность (RSI > 70)" if r > 70 else "нейтральная зона 30–70"))
    if mm is not None and ms is not None:
        votes.append(_vote("macd", "MACD", 1 if mm > ms else -1, "MACD %s сигнальной линии" % ("выше" if mm > ms else "ниже")))
    if bu is not None:
        votes.append(_vote("bb", "Полосы Боллинджера", 1 if price < bl else -1 if price > bu else 0,
                           "цена ниже нижней полосы" if price < bl else "цена выше верхней полосы" if price > bu else "цена внутри полос"))
    score = sum(v["vote"] for v in votes)
    signal = "покупать" if score >= 2 else "продавать" if score <= -2 else "нейтрально"
    return {"signal": signal, "score": score, "votes": votes,
            "last": {"c": price, "sma50": s50, "sma200": s200, "rsi": r, "macd": mm, "macd_signal": ms, "bb_up": bu, "bb_low": bl, "atr": at}}


def ta_series(candles):
    """Ряды индикаторов для графика, выровненные по свечам."""
    closes = [c["c"] for c in candles]
    ml, sl, hl = macd(closes)
    bm, bu, bl = bollinger(closes)
    return {"sma50": sma(closes, 50), "sma200": sma(closes, 200), "bb_mid": bm, "bb_up": bu, "bb_low": bl,
            "rsi": rsi(closes), "macd": ml, "macd_signal": sl, "macd_hist": hl}
