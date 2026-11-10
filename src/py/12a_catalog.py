# ═══════════════════ каталог облигаций T-Invest (сектор, признаки, рейтинги по ISIN) ═══════════════════
# Только чтение справочника InstrumentsService/Bonds; без токена каталог пуст, а рейтинги берутся по названию.

TCAT_KEY, TCAT_TTL = "tcat_v2", 24 * 3600
_tcat = {"t": 0, "d": {}, "fail": 0, "tk": {}}
_tcat_lock = threading.Lock()


def _tcat_compact(b):
    rts = []
    for r in b.get("ratings") or []:
        rts.append([r.get("agencyName") or "", r.get("ratingLevel") or "", (r.get("ratingDate") or "")[:10],
                    r.get("forecast") or "", bool(r.get("isUnderWatch"))])
    return {"n": b.get("name") or "", "s": b.get("sector") or "", "fl": bool(b.get("floatingCouponFlag")),
            "am": bool(b.get("amortizationFlag")), "sub": bool(b.get("subordinatedFlag")),
            "pp": bool(b.get("perpetualFlag")), "rk": b.get("riskLevel") or "",
            "mat": (b.get("maturityDate") or "")[:10], "cur": (b.get("currency") or "").upper(),
            "tk": b.get("ticker") or "", "br": ((b.get("brand") or {}).get("name") if isinstance(b.get("brand"), dict) else None) or "", "r": rts}


def tcat():
    """dict ISIN -> компактная запись каталога; {} если токена нет или API недоступен."""
    if _tcat["d"] and time.time() - _tcat["t"] < TCAT_TTL:
        return _tcat["d"]
    with _tcat_lock:
        if _tcat["d"] and time.time() - _tcat["t"] < TCAT_TTL:
            return _tcat["d"]
        if not _tcat["d"]:
            try:
                hit = store().get(TCAT_KEY, ttl=TCAT_TTL)
            except Exception:  # noqa: BLE001
                hit = None
            if hit:
                _tcat.update(t=time.time(), d=hit)
                return hit
        if time.time() - _tcat["fail"] < 300:
            return _tcat["d"]
        try:
            cfg = load_config()
            if not (cfg.get("token") or "").strip():
                raise ApiError("нет токена", 400)
            ins = TInvest(cfg).call("InstrumentsService", "Bonds",
                                    {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}, timeout=90).get("instruments") or []
            d = {b["isin"]: _tcat_compact(b) for b in ins if b.get("isin")}
            if d:
                store().put(TCAT_KEY, d)
                _tcat.update(t=time.time(), d=d)
        except Exception:  # noqa: BLE001
            _tcat["fail"] = time.time()
        return _tcat["d"]


def _tcat_get(k):
    """Запись каталога по ISIN или (запасной вариант) по тикеру."""
    d = tcat()
    k = (k or "").strip().upper()
    b = d.get(k)
    if b is None and d:
        if len(_tcat["tk"]) < len(d) // 2:
            _tcat["tk"] = {v["tk"].upper(): v for v in d.values() if v.get("tk")}
        b = _tcat["tk"].get(k)
    return b


def tcat_info(isin):
    b = _tcat_get(isin)
    if not b:
        return None
    return {"sector": b["s"] or None, "floating": b["fl"], "amort": b["am"], "subordinated": b["sub"],
            "perpetual": b["pp"], "risk": b["rk"] or None, "name": b["n"], "maturity": b["mat"] or None,
            "currency": b["cur"] or None}


def _norm_level(s):
    s = (s or "").strip().translate(_LAT).upper().replace("−", "-").replace("–", "-")
    if s in RATING_SCALE:
        return s
    return _rating_token(s)


def best_rating(isin, name):
    """Как rating_for(name), но рейтинги из каталога по ISIN точные; недостающие агентства добавляются по названию."""
    base = rating_for(name or "")
    b = _tcat_get(isin)
    cat = {}
    if b:
        for ag, lv, dt, fc, watch in b["r"]:
            v = _norm_level(lv)
            if not v or not ag:
                continue
            cur = cat.get(ag)
            if cur is None or dt >= cur["date"]:
                cat[ag] = {"agency": ag, "rating": v, "issuer": b["br"] or b["n"], "date": dt,
                           "outlook": (fc or "") + (" · под наблюдением" if watch else ""), "approx": False}
    if not cat:
        return base
    allr = list(cat.values())
    for x in (base or {}).get("all") or []:
        if x["agency"] not in cat and not x.get("approx"):
            allr.append(x)
    low = max(allr, key=lambda x: RATING_SCALE.index(x["rating"]))
    return {"v": low["rating"], "agency": low["agency"], "issuer": low["issuer"], "date": low["date"],
            "approx": low["approx"], "all": allr}
