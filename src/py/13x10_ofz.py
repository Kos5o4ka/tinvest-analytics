# ── ОФЗ-Спредер: премия за дюрацию, наклон и кривизна КБД, ОФЗ-ПД относительно кривой ──
# Имена из других фрагментов (kbd_at, screener_rows, API_GET) разрешаются при вызове; на верхнем уровне только определения.

OFZ_CURVE_T = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]
OFZ_CHEAP_BP = 15.0            # ±15 б.п. к КБД — порог «дешевле / дороже кривой»
OFZ_MIN_DUR = 0.25             # короче — спред к кривой шумит
OFZ_TTL = 900
OFZ_DISCLAIMER = ("Справочная аналитика по данным Мосбиржи (КБД, доходности выпусков), не индивидуальная инвестиционная рекомендация. "
                  "Кривая отражает ожидания рынка, а не прогноз: фактическая доходность зависит от решений по ключевой ставке.")
_ofz_cache = {"t": 0.0, "v": None}

OFZ_REGIMES = [
    (-1.5, "deep_inv", "глубокая инверсия",
     "Рынок ждёт снижения ставок: длинные ОФЗ сейчас дают меньше коротких, но выиграют в цене, если ставка действительно пойдёт вниз."),
    (0.0, "inv", "умеренная инверсия",
     "Длинные ставки чуть ниже коротких: рынок закладывает постепенное снижение ставки, за срок почти не платят."),
    (1.0, "flat", "плоская / нормальная",
     "Кривая около нормальной формы: за удлинение срока платят небольшую премию."),
    (1e9, "steep", "крутая",
     "Длинные ставки заметно выше коротких: за срок платят щедро, но и риск просадки цены при росте ставок больше."),
]


def _ofz_k(kbd, t):
    try:
        v = kbd(t)
        return None if v is None else float(v)
    except Exception:  # noqa: BLE001
        return None


def ofz_regime(slope):
    """(-inf, -1.5) глубокая инверсия; [-1.5, 0] умеренная; (0, 1] плоская/нормальная; > 1 крутая."""
    if slope < -1.5:
        r = OFZ_REGIMES[0]
    elif slope <= 0:
        r = OFZ_REGIMES[1]
    elif slope <= 1:
        r = OFZ_REGIMES[2]
    else:
        r = OFZ_REGIMES[3]
    return r[1], r[2], r[3]


def ofz_term_premia(kbd):
    """Приращение КБД за каждый год срока t=1..15, б.п. (для первого года — от 3 месяцев)."""
    out = []
    for t in range(1, 16):
        a = _ofz_k(kbd, t)
        b = _ofz_k(kbd, 0.25 if t == 1 else t - 1)
        if a is not None and b is not None:
            out.append({"t": t, "bp": round((a - b) * 100.0, 1)})
    return out


def ofz_is_floater_or_linker(r):
    sid = (r.get("id") or "").upper()
    if re.match(r"^SU52\d{3}", sid) or r.get("linker"):
        return True
    if r.get("floating") or re.match(r"^SU(24|29)\d{3}", sid):
        return True
    bt = (r.get("btype") or "").lower() + " " + (r.get("sub") or "").lower() + " " + (r.get("name") or "").lower()
    return "плава" in bt or "индексац" in bt or "-пк" in bt or "-ин" in bt or "ипц" in bt


def ofz_bond_list(kbd, bonds):
    out = []
    for r in bonds or []:
        try:
            if r.get("kind") not in (None, "ofz") or ofz_is_floater_or_linker(r):
                continue
            dur, y = r.get("dur"), r.get("yield")
            if dur is None or y is None or float(dur) < OFZ_MIN_DUR:
                continue
            k = _ofz_k(kbd, float(dur))
            if k is None:
                continue
            sp = round((float(y) - k) * 100.0, 1)
            flag = "cheap" if sp > OFZ_CHEAP_BP else "rich" if sp < -OFZ_CHEAP_BP else None
            out.append({"id": r.get("id"), "isin": r.get("isin"), "name": r.get("name"), "yield": round(float(y), 2), "dur": round(float(dur), 2),
                        "price": r.get("price"), "mat": r.get("mat"), "coupon": r.get("coupon"), "kbd": round(k, 2), "spread_bp": sp, "flag": flag})
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["dur"])
    return out


def ofz_spread_calc(kbd, bonds, today=None):
    k = lambda t: _ofz_k(kbd, t)  # noqa: E731
    res = {"asof": (today or date.today()).isoformat()}
    k2, k10 = k(2), k(10)
    if k2 is not None and k10 is not None:
        slope = round(k10 - k2, 2)
        code, name, note = ofz_regime(slope)
        res.update(slope=slope, regime=name, regime_code=code, regime_note=note)
    else:
        res.update(slope=None, regime=None, regime_code=None, regime_note=None)
    tp = ofz_term_premia(kbd)
    res["tp"] = tp
    far = [x["bp"] for x in tp if x["t"] >= 4]
    res["tp_far_avg"] = round(sum(far) / len(far), 1) if far else None
    k3 = k(3)
    res["tp_3_10_avg"] = round((k10 - k3) / 7.0 * 100.0, 1) if k3 is not None and k10 is not None else None
    k1, k5 = k(1), k(5)
    if None not in (k2, k5, k10):
        cv = round(2 * k5 - k2 - k10, 2)
        res["curvature"] = cv
        if cv > 0.1:
            res["structure"] = "bullet"
            res["structure_note"] = "Горб на 3–5 годах: bullet (один выпуск на 4–5 лет) выгоднее штанги."
        elif cv < -0.1:
            res["structure"] = "barbell"
            res["structure_note"] = "Barbell (50% на ~1 год + 50% на ~10 лет) выгоднее bullet."
        else:
            res["structure"] = "neutral"
            res["structure_note"] = "Кривая близка к прямой: bullet и barbell дают почти одинаково."
    else:
        res.update(curvature=None, structure=None, structure_note=None)
    if k5 is not None and k1 is not None and k10 is not None:
        res["bullet"] = round(k5, 2)
        res["barbell"] = round((k1 + k10) / 2.0, 2)
        res["barbell_note"] = "Дюрация штанги ≈ 5,5 лет, у bullet ≈ 5 — сопоставимый рыночный риск."
    else:
        res["bullet"] = res["barbell"] = None
        res["barbell_note"] = None
    res["bonds"] = ofz_bond_list(kbd, bonds)
    res["curve"] = [{"t": t, "y": round(v, 2)} for t in OFZ_CURVE_T for v in [k(t)] if v is not None]
    res["verdict"] = ofz_verdict(res)
    res["disclaimer"] = OFZ_DISCLAIMER
    res["ok"] = bool(res["curve"])
    return res


def ofz_verdict(r):
    parts = []
    sl = r.get("slope")
    if sl is not None:
        parts.append("Наклон КБД 2–10 лет: %+.2f п.п. (%s)." % (sl, r["regime"]))
    far, mid = r.get("tp_far_avg"), r.get("tp_3_10_avg")
    if mid is not None:
        far = mid                                   # тот же показатель, что в карточке «Премия за год срока, 3–10 лет»
    if far is not None:
        if far < 0:
            parts.append("Между 3 и 10 годами кривая убывает (в среднем %.0f б.п. в год): длинные ОФЗ дают меньше коротких, "
                         "а их доходность — это по сути ставка на снижение ключевой ставки." % far)
        elif far < 10:
            parts.append("За каждый год срока между 3 и 10 годами рынок доплачивает в среднем %.0f б.п. в год: удлинять дюрацию ради дополнительной доходности сейчас почти не платят, "
                         "а премия на длинном конце — это по сути ставка на снижение ключевой ставки." % far)
        elif far < 30:
            parts.append("Премия за каждый год срока между 3 и 10 годами — около %.0f б.п.: умеренная плата за удлинение, сравнимая с риском колебаний цены." % far)
        else:
            parts.append("Премия за каждый год срока между 3 и 10 годами — около %.0f б.п.: удлинение дюрации оплачивается заметно, но и просадка цены при росте ставок будет ощутимой." % far)
    if r.get("structure_note"):
        parts.append(r["structure_note"])
    if sl is not None and sl < 0:
        parts.append("Короткие выпуски и фонды ликвидности фиксируют текущую высокую ставку без ценового риска, длинные выигрывают лишь при снижении ставки.")
    return " ".join(parts) if parts else "Данных КБД недостаточно для вывода."


def ofz_spread_payload(force=False):
    now = time.time()
    if not force and _ofz_cache["v"] is not None and now - _ofz_cache["t"] < OFZ_TTL:
        return _ofz_cache["v"]
    try:
        pts = kbd_curve()
    except Exception:  # noqa: BLE001
        pts = []
    if not pts:
        return {"ok": False, "error": "КБД Мосбиржи сейчас недоступна — попробуйте позже.", "disclaimer": OFZ_DISCLAIMER}
    bonds, note = [], None
    try:
        bonds = [r for r in screener_rows() if r.get("kind") == "ofz"]
    except Exception:  # noqa: BLE001
        note = "Список выпусков ОФЗ временно недоступен: показана только кривая."
    try:
        res = ofz_spread_calc(lambda y: _interp(pts, y), bonds, date.today())
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "Не удалось рассчитать: %s" % str(e)[:120], "disclaimer": OFZ_DISCLAIMER}
    res["note"] = note
    _ofz_cache.update(t=now, v=res)
    return res


def _api_ofz_spread(cfg, acc, q, force):
    return ofz_spread_payload(bool(force))


API_GET["/api/ofz_spread"] = _api_ofz_spread
