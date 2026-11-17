# ── Тепловая карта рынка: акции / облигации / фонды ──
HM_BUCKETS = ["AAA", "AA", "A", "BBB", "≤BB", "без рейтинга"]


def treemap_layout(values, x, y, w, h):
    """Squarified treemap (Bruls et al.). Возвращает список (x, y, w, h) в порядке входных значений;
    для значений <= 0 — нулевой прямоугольник. Используется только в тестах: боевая раскладка — JS hmSquarify в
    46_heatmap.js. При изменении алгоритма менять ОБЕ реализации синхронно."""
    n = len(values)
    out = [(x, y, 0.0, 0.0)] * n
    idx = sorted((i for i in range(n) if values[i] and values[i] > 0), key=lambda i: -values[i])
    total = float(sum(values[i] for i in idx))
    if not idx or total <= 0 or w <= 0 or h <= 0:
        return out
    k = w * h / total
    areas = [values[i] * k for i in idx]
    cx, cy, cw, ch = float(x), float(y), float(w), float(h)

    def worst(row, side):
        s = sum(row)
        return max(max(side * side * max(row) / (s * s), s * s / (side * side * min(row))), 0)

    pos = 0
    while pos < len(areas):
        side = min(cw, ch)
        row = [areas[pos]]
        j = pos + 1
        while j < len(areas) and worst(row + [areas[j]], side) <= worst(row, side):
            row.append(areas[j])
            j += 1
        s = sum(row)
        if cw >= ch:                      # колонка слева, элементы сверху вниз
            colw = s / ch
            yy = cy
            for t, a in enumerate(row):
                hh = a / colw
                out[idx[pos + t]] = (cx, yy, colw, hh)
                yy += hh
            cx += colw
            cw -= colw
        else:                             # строка сверху, элементы слева направо
            rowh = s / cw
            xx = cx
            for t, a in enumerate(row):
                ww = a / rowh
                out[idx[pos + t]] = (xx, cy, ww, rowh)
                xx += ww
            cy += rowh
            ch -= rowh
        pos = j
    return out


def _hm_num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _hm_stats(items):
    up = sum(1 for i in items if i["chg"] > 0.005)
    dn = sum(1 for i in items if i["chg"] < -0.005)
    tot = sum(i["size"] for i in items)
    turn = sum(i.get("value") or 0 for i in items)
    wch = sum(i["chg"] * i["size"] for i in items) / tot if tot > 0 else 0.0
    return {"up": up, "down": dn, "flat": len(items) - up - dn, "n": len(items),
            "turnover": round(turn), "wchg": round(wch, 2)}


def _hm_group(items, key):
    groups = {}
    for it in items:
        groups.setdefault(key(it), []).append(it)
    out = []
    for name, its in groups.items():
        its.sort(key=lambda i: -i["size"])
        tot = sum(i["size"] for i in its)
        wch = sum(i["chg"] * i["size"] for i in its) / tot if tot > 0 else 0.0
        out.append({"name": name, "size": tot, "chg": round(wch, 2), "items": its})
    out.sort(key=lambda g: -g["size"])
    return out


def _hm_equities(kind, period, size):
    fn = globals().get("stocks_universe" if kind == "stocks" else "funds_universe")
    if not fn:
        return {"error": "Данные по акциям и фондам недоступны"}
    rows = fn() or []
    ck = {"d": "chg_d", "w": "chg_w", "m": "chg_m"}[period]
    items = []
    for r in rows:
        chg = _hm_num(r.get(ck))
        cap, val = _hm_num(r.get("cap")) or 0, _hm_num(r.get("value_today")) or 0
        sz = val if size == "value" else (cap if cap > 0 else (val if kind == "funds" else 0))
        if sz <= 0:
            continue
        sid = r.get("secid")
        items.append({"id": sid, "label": sid, "name": r.get("shortname") or r.get("name") or sid, "size": sz,
                      "chg": chg if chg is not None else 0.0, "price": _hm_num(r.get("price")),
                      "value": val, "cap": cap or None, "sector": r.get("sector") or "Прочее"})
    groups = _hm_group(items, lambda i: i["sector"])
    return {"groups": groups, "stats": _hm_stats(items)}


def _hm_bucket(rating):
    if not rating:
        return "без рейтинга"
    b = rating_bucket(rating)
    return "≤BB" if b == "BB и ниже" else ("без рейтинга" if b == "нет рейтинга" else b)


def _hm_bonds():
    rows = screener_rows() or []
    br = globals().get("best_rating")
    rows = sorted((r for r in rows if (r.get("turn") or 0) > 0), key=lambda r: -r["turn"])[:300]
    items = []
    for r in rows:
        rt = r.get("rating")
        if rt is None and br:
            try:
                x = br(r.get("isin"), r.get("name"))
                rt = x["v"] if x else None
            except Exception:  # noqa: BLE001
                rt = None
        isin = r.get("isin") or r["id"]
        items.append({"id": isin, "label": r.get("name") or r["id"], "name": r.get("full") or r.get("name"),
                      "size": r["turn"], "chg": _hm_num(r.get("chg")) or 0.0, "price": r.get("price"),
                      "value": r["turn"], "cap": None, "yield": r.get("yield"), "rating": rt,
                      "bucket": _hm_bucket(rt)})
    groups = _hm_group(items, lambda i: i["bucket"])
    groups.sort(key=lambda g: HM_BUCKETS.index(g["name"]) if g["name"] in HM_BUCKETS else 99)
    return {"groups": groups, "stats": _hm_stats(items)}


def heatmap_payload(kind="stocks", period="d", size="cap"):
    kind = kind if kind in ("stocks", "bonds", "funds") else "stocks"
    period = period if period in ("d", "w", "m") else "d"
    size = size if size in ("cap", "value") else "cap"
    if kind == "bonds":
        period, size = "d", "value"
        res = _hm_bonds()
    else:
        res = _hm_equities(kind, period, size)
    res.update(kind=kind, period=period, size=size, updated=time.time())
    return res


def _api_heatmap(cfg, acc, q, force):
    return heatmap_payload(q.get("kind", "stocks"), q.get("period", "d"), q.get("size", "cap"))


API_GET["/api/heatmap"] = _api_heatmap
