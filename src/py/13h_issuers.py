# ═══════════════════════════════ эмитенты: отчётность, скоринг ═══════════════════════════════
# Источники (публичные, наружу уходят только ИНН/ISIN эмитентов, ничего о портфеле):
#   • Мосбиржа ISS: ISIN -> EMITTER_ID -> ИНН, список выпусков эмитента, флаги дефолта;
#   • ГИР БО ФНС (bo.nalog.gov.ru): бухгалтерская отчётность по РСБУ (отдельной компании, не группы).
# Суммы в отчётности — в тысячах рублей; в ответах API хранятся в млн ₽.

ISS_FNS = "https://bo.nalog.gov.ru"
ISS_FNS_TTL, ISS_FNS_NF_TTL = 7 * DAY, DAY
ISS_CODES_FR = ("2110", "2200", "2300", "2320", "2330", "2400")
ISS_CODES_BS = ("1200", "1240", "1250", "1300", "1410", "1500", "1510", "1600")
_iss_fns_lock = threading.Lock()
_iss_fns_last = [0.0]
_iss_jobs = {}
_iss_jobs_lock = threading.Lock()


def _iss_json(url, timeout=25):
    return json.loads(http_text(url, timeout=timeout))


def _iss_fns_get(path):
    """Запрос к ФНС: не чаще ~2 в секунду на всё приложение."""
    with _iss_fns_lock:
        wait = 0.5 - (time.time() - _iss_fns_last[0])
        if wait > 0:
            time.sleep(wait)
        _iss_fns_last[0] = time.time()
    return _iss_json(ISS_FNS + path, timeout=30)


def _iss_n(x, d=1):
    return "—" if x is None else ("%.*f" % (d, x)).replace(".", ",")


# ── эмитент по ISIN ──

def issuer_of(isin):
    """ISIN -> {emitter_id, inn, title, short} (кэш навсегда) или None, если определить не удалось."""
    isin = (isin or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{6,14}", isin):
        return None
    key = "iss_emit_v1_" + isin
    hit = store().get(key)
    if hit:
        return hit
    try:
        j = _iss_json("https://iss.moex.com/iss/securities/%s.json?iss.meta=off&iss.only=description" % isin, 20)
        d = {r[0]: r[2] for r in j["description"]["data"]}
        if not d:
            return None
        eid = d.get("EMITTER_ID")
        out = {"emitter_id": int(eid) if eid else None, "inn": None, "title": d.get("ISSUENAME") or isin, "short": None}
        if eid:
            ek = "iss_emitter_v1_%s" % eid
            em = store().get(ek)
            if not em:
                e = _iss_json("https://iss.moex.com/iss/emitters/%s.json?iss.meta=off&iss.only=emitter" % eid, 15)
                row = dict(zip(e["emitter"]["columns"], (e["emitter"]["data"] or [[]])[0]))
                em = {"inn": str(row.get("INN") or "").strip() or None, "title": row.get("TITLE"), "short": row.get("SHORT_TITLE")}
                if row:
                    store().put(ek, em)
            out.update(inn=em.get("inn"), title=em.get("title") or out["title"], short=em.get("short"))
    except Exception:  # noqa: BLE001
        return None
    store().put(key, out)
    return out


# ── отчётность РСБУ из ГИР БО ──

def _iss_pick(rep, kind, code, off):
    """Значение строки code из отчёта: off 0 = текущий год, 1 = предыдущий, 2 = позапрошлый (только баланс)."""
    blk = rep.get(kind) or {}
    pre = ("current", "previous", "beforePrevious")[off]
    v = blk.get(pre + code)
    return float(v) if isinstance(v, (int, float)) else None


def _iss_parse_bfo(lst):
    """Список отчётов ФНС -> {год: {код: значение в тыс. ₽}}; свой год приоритетнее пересчитанных значений из следующих отчётов."""
    reps = []
    for y in lst or []:
        try:
            per = int(y.get("period"))
        except (TypeError, ValueError):
            continue
        tcs = y.get("typeCorrections") or []
        cor = None
        for tc in tcs:
            c = (tc or {}).get("correction")
            if isinstance(c, dict) and (c.get("balance") or c.get("financialResult")):
                cor = c
                if (c.get("periodType") in (12, None)):
                    break
        if cor:
            reps.append((per, cor))
    years = {}
    prio = {}
    for per, c in reps:
        for off in (0, 1, 2):
            yr = per - off
            for kind, codes in (("financialResult", ISS_CODES_FR), ("balance", ISS_CODES_BS)):
                if kind == "financialResult" and off == 2:
                    continue
                for code in codes:
                    v = _iss_pick(c, kind, code, off)
                    if v is None:
                        continue
                    k = (yr, code)
                    if k not in prio or off < prio[k]:
                        prio[k] = off
                        years.setdefault(yr, {})[code] = v
    return years


def _iss_ratio(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _iss_year_row(y, v, prev):
    g = v.get
    rev, np_, ebt, int_ = g("2110"), g("2400"), g("2300"), g("2330")
    int_ = abs(int_) if int_ is not None else None
    if ebt is not None:
        ebit = ebt + (int_ or 0)
    else:
        ebit = g("2200")
    parts = [g("1410"), g("1510")]
    debt = None if all(p is None for p in parts) else sum(p or 0 for p in parts)
    cp = [g("1250"), g("1240")]
    cash = None if all(p is None for p in cp) else sum(p or 0 for p in cp)
    nd = None if debt is None else debt - (cash or 0)
    eq, assets = g("1300"), g("1600")
    r = lambda x: None if x is None else round(x / 1000.0, 1)      # noqa: E731  тыс. ₽ -> млн ₽
    row = {"y": y, "rev": r(rev), "ebit": r(ebit), "interest": r(int_), "net": r(np_), "debt": r(debt), "cash": r(cash),
           "net_debt": r(nd), "equity": r(eq), "assets": r(assets),
           "cover": None, "nd_ebit": None, "cur_liq": _iss_ratio(g("1200"), g("1500")),
           "eq_ratio": _iss_ratio(eq, assets), "margin": _iss_ratio(ebit, rev), "growth": None, "debt_eq": None}
    if ebit is not None and int_ and int_ > 0:
        row["cover"] = ebit / int_
    if nd is not None and ebit is not None and ebit > 0:
        row["nd_ebit"] = nd / ebit
    if debt is not None and eq is not None and eq > 0:
        row["debt_eq"] = debt / eq
    if prev and prev.get("2110") and rev is not None:
        row["growth"] = rev / prev["2110"] - 1
    for k in ("cover", "nd_ebit", "cur_liq", "eq_ratio", "margin", "growth", "debt_eq"):
        if row[k] is not None:
            row[k] = round(row[k], 4)
    # годовая выручка 0/пустая и нет баланса — строка бесполезна
    row["has"] = any(row[k] is not None for k in ("rev", "assets", "equity"))
    return row


def issuer_fin(inn, name=""):
    """Отчётность эмитента по ИНН: {status, years:[...], org_id, name, note}. Кэш 7 суток (ненайденные — 1 сутки)."""
    inn = re.sub(r"\D", "", inn or "")
    if len(inn) not in (10, 12):
        return {"status": "noinn", "years": [], "note": "ИНН эмитента неизвестен (возможно, иностранный эмитент или государство)."}
    key = "iss_fin_v1_" + inn
    hit = store().get(key)
    if hit and time.time() - hit.get("ts", 0) < (ISS_FNS_TTL if hit.get("status") == "ok" else ISS_FNS_NF_TTL):
        return hit
    res = {"status": "nf", "years": [], "inn": inn, "ts": time.time(), "org_id": None, "name": name or ""}
    s = _iss_fns_get("/advanced-search/organizations/search?query=%s&page=0" % inn)
    org = None
    for it in s.get("content") or []:
        if re.sub(r"<[^>]+>", "", str(it.get("inn") or "")).strip() == inn:
            org = it
            if it.get("bfo"):
                break
    nm = (org or {}).get("shortName") or name or ""
    res["name"] = nm
    if not org:
        res["note"] = _iss_nodata_note(nm or name, "Организация не найдена в ГИР БО ФНС (с 2022 года часть компаний вправе не раскрывать отчётность).")
        store().put(key, res)
        return res
    res["org_id"] = org.get("id")
    if not org.get("bfo"):
        res["status"] = "nobfo"
        res["note"] = _iss_nodata_note(nm, "В ГИР БО нет бухгалтерской отчётности этой организации.")
        store().put(key, res)
        return res
    lst = _iss_fns_get("/nbo/organizations/%s/bfo/" % org["id"])
    ys = _iss_parse_bfo(lst if isinstance(lst, list) else [])
    rows = []
    for y in sorted(ys):
        row = _iss_year_row(y, ys[y], ys.get(y - 1))
        if row["has"]:
            rows.append(row)
    res["years"] = rows[-5:]
    if rows:
        res["status"] = "ok"
    else:
        res["status"] = "nobfo"
        res["note"] = _iss_nodata_note(nm, "Отчётность в ГИР БО пустая или в нестандартной форме.")
    store().put(key, res)
    return res


def _iss_nodata_note(name, base):
    if re.search(r"банк|страхов|\bНКО\b|кредитн\w+ организац", name or "", re.I):
        return "Нет данных по РСБУ: банки и страховые компании сдают отчётность в Банк России (формы 0409806 и др.), в ГИР БО её нет."
    return base + " Возможные причины: новая компания, отчётность не публикуется, нестандартная форма."


# ── скоринг ──
# Шесть показателей последнего года, каждый даёт баллы от 0 до максимума линейно между «плохо» и «хорошо»:
#   покрытие процентов EBIT/проценты   25 б.:  ≤ 1,5 — 0,  ≥ 4 — полный балл
#   чистый долг / EBIT                 25 б.:  ≥ 4 — 0,    ≤ 2 — полный (нет чистого долга — полный; EBIT ≤ 0 при долге — 0)
#   доля капитала в активах            15 б.:  ≤ 5 % — 0,  ≥ 30 % — полный
#   текущая ликвидность                10 б.:  ≤ 0,8 — 0,  ≥ 1,5 — полный
#   рентабельность по EBIT             10 б.:  ≤ 0 — 0,    ≥ 12 % — полный
#   рост выручки                       15 б.:  ≤ −15 % — 0, ≥ +5 % — полный
# Для лизинга и прочих финансовых компаний долг — это «сырьё» бизнеса, поэтому вместо чистого долга/EBIT
# берётся долг/капитал (≥ 8 — 0, ≤ 3 — полный), капитал/активы: 5 % — 0, 15 % — полный, ликвидность не считается.
# Итог = набранные баллы / максимум по доступным показателям × 100, затем штрафы:
#   убыток по итогам года −8 (два года подряд ещё −7), отрицательный капитал −15, отчётность старше двух лет −10.
# Метки: ≥ 70 устойчивое, 50–69 среднее, 30–49 слабое, < 30 тревожное.
ISS_FIN_RE = re.compile(r"лизинг|факторинг|финанс|микрофин|МФК|МКК|кредитн|ипотечн|коллектор|ломбард", re.I)
ISS_LABELS = [(70, "strong", "устойчивое"), (50, "mid", "среднее"), (30, "weak", "слабое"), (-1, "alarm", "тревожное")]


def _iss_t(x, bad, good):
    if x is None:
        return None
    return max(0.0, min(1.0, (x - bad) / float(good - bad)))


def _iss_label(sc):
    for lim, k, t in ISS_LABELS:
        if sc >= lim:
            return k, t
    return "alarm", "тревожное"


def _iss_grade(t):
    return "good" if t >= 0.75 else "mid" if t >= 0.35 else "bad"


def iss_score_fin(fin, is_fin=False):
    """Скоринг по готовой отчётности (issuer_fin). Возвращает {ok, score, key, label, year, parts, penalties, note}."""
    yrs = (fin or {}).get("years") or []
    if not yrs:
        return {"ok": False, "reason": (fin or {}).get("note") or "Нет отчётности."}
    c = yrs[-1]
    prev = yrs[-2] if len(yrs) > 1 and yrs[-2]["y"] == c["y"] - 1 else None
    parts = []

    def add(pid, name, w, t, value, text):
        if t is not None:
            parts.append({"id": pid, "name": name, "max": w, "pts": round(w * t, 1), "grade": _iss_grade(t), "value": value, "text": text})

    ebit, intr = c.get("ebit"), c.get("interest")
    if intr is not None and intr > 0:
        if ebit is not None and ebit > 0 and c.get("cover") is not None:
            add("cover", "Покрытие процентов", 25, _iss_t(c["cover"], 1.5, 4.0), c["cover"], "прибыль покрывает проценты в %s раза" % _iss_n(c["cover"], 1))
        elif ebit is not None:
            add("cover", "Покрытие процентов", 25, 0.0, None, "операционной прибыли нет, проценты платятся из других источников")
    elif ebit is not None and ebit > 0 and c.get("debt") is not None and c["debt"] <= 0.02 * (c.get("assets") or 1e18):
        add("cover", "Покрытие процентов", 25, 1.0, None, "заёмных средств практически нет")
    nd, ebit_ok = c.get("net_debt"), ebit is not None and ebit > 0
    if is_fin:
        if c.get("debt") is not None and c.get("equity") is not None:
            if c["equity"] <= 0:
                add("lev", "Долг / капитал", 25, 0.0, None, "капитал отрицательный")
            elif c.get("debt_eq") is not None:
                add("lev", "Долг / капитал", 25, _iss_t(c["debt_eq"], 8, 3), c["debt_eq"], "долг в %s раза больше капитала" % _iss_n(c["debt_eq"], 1))
    elif nd is not None:
        if nd <= 0:
            add("lev", "Чистый долг / EBIT", 25, 1.0, None, "денег больше, чем долга")
        elif not ebit_ok:
            add("lev", "Чистый долг / EBIT", 25, 0.0, None, "есть чистый долг, а операционной прибыли нет")
        else:
            add("lev", "Чистый долг / EBIT", 25, _iss_t(c["nd_ebit"], 4, 2), c["nd_ebit"], "чистый долг = %s годовой прибыли" % _iss_n(c["nd_ebit"], 1))
    if c.get("eq_ratio") is not None:
        hi = 0.15 if is_fin else 0.30
        add("eq", "Доля капитала", 15, _iss_t(c["eq_ratio"], 0.05, hi), c["eq_ratio"], "капитал — %s %% активов" % _iss_n(c["eq_ratio"] * 100, 0))
    if c.get("cur_liq") is not None and not is_fin:
        add("liq", "Текущая ликвидность", 10, _iss_t(c["cur_liq"], 0.8, 1.5), c["cur_liq"], "оборотные активы = %s× краткосрочных обязательств" % _iss_n(c["cur_liq"], 2))
    holding = c.get("margin") is not None and c["margin"] > 1.0       # EBIT больше выручки: доход в основном от дивидендов и финансовых вложений
    if c.get("margin") is not None and not holding:
        add("margin", "Рентабельность по EBIT", 10, _iss_t(c["margin"], 0.0, 0.12), c["margin"], "EBIT — %s %% выручки" % _iss_n(c["margin"] * 100, 1))
    if c.get("growth") is not None:
        add("growth", "Динамика выручки", 15, _iss_t(c["growth"], -0.15, 0.05), c["growth"], "выручка %s на %s %%" % ("выросла" if c["growth"] >= 0 else "упала", _iss_n(abs(c["growth"]) * 100, 0)))
    mx = sum(p["max"] for p in parts)
    if mx < 40:
        return {"ok": False, "reason": "Слишком мало показателей для оценки (в отчётности не хватает строк)."}
    base = sum(p["pts"] for p in parts) / mx * 100
    pen = []
    if c.get("net") is not None and c["net"] < 0:
        pen.append({"name": "Убыток по итогам года", "pts": -8})
        if prev and prev.get("net") is not None and prev["net"] < 0:
            pen.append({"name": "Убыток второй год подряд", "pts": -7})
    if c.get("equity") is not None and c["equity"] < 0:
        pen.append({"name": "Отрицательный капитал", "pts": -15})
    if c["y"] < date.today().year - 2:
        pen.append({"name": "Отчётность старше двух лет (%d)" % c["y"], "pts": -10})
    sc = max(0, min(100, int(round(base + sum(p["pts"] for p in pen)))))
    k, t = _iss_label(sc)
    return {"ok": True, "score": sc, "key": k, "label": t, "year": c["y"], "base": round(base, 1), "parts": parts, "penalties": pen,
            "n_years": len(yrs), "fin_mode": bool(is_fin),
            "holding": holding,
            "note": ("Есть отчётность только за один год: динамику оценить нельзя. " if len(yrs) == 1 else "")
            + ("Прибыль до налогов больше выручки: компания, судя по всему, холдинговая (доход — дивиденды и проценты от дочерних структур). "
               "Её отдельная отчётность плохо отражает группу, оценка ориентировочная." if holding else "")}


def _iss_is_fin(title, sector=None):
    return bool(ISS_FIN_RE.search(title or "")) or sector == "financial"


def issuer_score(isin):
    """Публичная функция для других модулей: скоринг эмитента облигации по ISIN.
    Возвращает {ok, score 0–100, key (strong/mid/weak/alarm), label, year, parts, penalties, issuer, inn} или {ok: False, reason}."""
    try:
        em = issuer_of(isin)
        if not em or not em.get("inn"):
            return {"ok": False, "reason": "Не удалось определить эмитента (нет ИНН)."}
        fin = issuer_fin(em["inn"], em.get("title") or "")
        ci = tcat_info(isin) or {}
        s = iss_score_fin(fin, _iss_is_fin(em.get("title"), ci.get("sector")))
        s["issuer"], s["inn"] = em.get("short") or em.get("title"), em["inn"]
        return s
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": "Ошибка получения отчётности: %s" % str(e)[:100]}


# ── сопоставление с рынком ──

_ISS_SPREAD_PTS = [(0, 92), (1, 80), (2.5, 65), (4.5, 45), (7, 28), (12, 10), (25, 0)]
_ISS_RATING_PTS = [(0, 92), (3, 82), (5, 72), (8, 55), (11, 40), (14, 25), (16, 12), (19, 0)]


def _iss_interp(x, pts):
    if x <= pts[0][0]:
        return float(pts[0][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / float(x1 - x0)
    return float(pts[-1][1])


def iss_market(score, spread, rating):
    """Сравнивает «баллы по отчётности» с тем, что закладывает рынок (спред к КБД) и рейтинговые агентства."""
    out = {"spread": spread, "rating": rating, "market_score": None, "rating_score": None, "key": None, "text": ""}
    if spread is not None:
        out["market_score"] = round(_iss_interp(max(0.0, spread), _ISS_SPREAD_PTS))
    if rating in RATING_SCALE:
        out["rating_score"] = round(_iss_interp(RATING_SCALE.index(rating), _ISS_RATING_PTS))
    if score is None:
        out["text"] = "Для сопоставления нужна отчётность эмитента."
        return out
    refs = [x for x in (out["market_score"], out["rating_score"]) if x is not None]
    if not refs:
        out["text"] = "Нет ни спреда к КБД, ни рейтинга — сопоставить с рынком нечего."
        return out
    ref = out["market_score"] if out["market_score"] is not None else out["rating_score"]
    diff = score - ref
    src = "спред к КБД %s п.п." % _iss_n(spread, 1) if out["market_score"] is not None else "рейтинг %s" % rating
    if diff >= 20:
        out["key"] = "mkt_higher"
        out["text"] = ("Рынок оценивает риск выше, чем следует из отчётности (%s). Либо облигации недооценены, либо есть риски, которых "
                       "не видно в РСБУ: долги группы, зависимость от одного заказчика, корпоративные события." % src)
    elif diff <= -20:
        out["key"] = "mkt_lower"
        out["text"] = ("Рынок оценивает риск ниже, чем следует из отчётности (%s). Возможно, закладывается поддержка владельца или государства, "
                       "либо слабые места отчётности пока не замечены. Стоит присмотреться внимательнее." % src)
    else:
        out["key"] = "match"
        out["text"] = "Оценка рынка (%s) в целом соответствует отчётности." % src
    return out


# ── кредитная история эмитента ──

def _iss_bonds_of(inn):
    """Все выпуски облигаций эмитента, известные Мосбирже (в обращении и погашенные), кэш сутки."""
    key = "iss_bonds_v1_" + inn
    hit = store().get(key, ttl=DAY)
    if hit is not None:
        return hit
    out, seen = [], set()
    for start in (0, 100, 200, 300):
        j = _iss_json("https://iss.moex.com/iss/securities.json?iss.meta=off&q=%s&limit=100&start=%d" % (inn, start), 25)
        rows = _iss_table(j, "securities")
        for r in rows:
            if str(r.get("emitent_inn") or "") != inn or r.get("group") != "stock_bonds":
                continue
            k = r.get("isin") or r.get("secid")
            if k in seen:
                continue
            seen.add(k)
            out.append({"isin": k, "secid": r.get("secid"), "name": r.get("shortname") or r.get("name"), "traded": bool(r.get("is_traded"))})
        if len(rows) < 100:
            break
    store().put(key, out)
    return out


def iss_history(inn):
    """Выпуски эмитента и флаги дефолта/технического дефолта (проверяется до 30 выпусков, сначала торгуемые)."""
    bonds = _iss_bonds_of(inn)
    order = sorted(bonds, key=lambda b: (not b["traded"], b["name"] or ""))
    chk = [b for b in order if b["isin"] and str(b["isin"]).startswith("RU")][:30]
    fl = pool_map(lambda b: _mon_flags(b["isin"]), chk, workers=5)
    items = []
    for b, f in zip(chk, fl):
        items.append({"isin": b["isin"], "name": b["name"], "traded": b["traded"], "default": bool(f.get("default")), "tech": bool(f.get("tech"))})
    nd = sum(1 for x in items if x["default"])
    nt = sum(1 for x in items if x["tech"] and not x["default"])
    if nd:
        verdict = "В истории эмитента есть дефолт по облигациям (%d из %d проверенных выпусков)." % (nd, len(items))
    elif nt:
        verdict = "Был технический дефолт (%d из %d проверенных выпусков): выплата задержана, но затем произведена." % (nt, len(items))
    elif items:
        verdict = "Дефолтов и технических дефолтов по проверенным выпускам не отмечено."
    else:
        verdict = "Выпусков эмитента на Мосбирже не найдено."
    return {"total": len(bonds), "traded": sum(1 for b in bonds if b["traded"]), "checked": len(items), "defaults": nd, "tech": nt,
            "items": items, "verdict": verdict}


# ── карточка эмитента ──

def _iss_market_bonds(inn, isin):
    """Выпуски эмитента, торгуемые в скринере: список для карточки, спред и рейтинг выбранной бумаги."""
    uni = {e["_isin"]: e for e in _bc_universe()}
    out = []
    for b in _iss_bonds_of(inn):
        e = uni.get(b["isin"])
        if e and e.get("cur") == "RUB":
            rt = e.get("_rt")
            out.append({"isin": e["_isin"], "name": e["name"], "yield": e.get("yield"), "spread": e.get("spread"), "dur": e.get("dur"),
                        "rating": rt["v"] if rt else None, "mat": e.get("mat"), "turn": e.get("turn"), "me": e["_isin"] == isin})
    out.sort(key=lambda x: (x["dur"] or 0))
    return out


def _iss_pick_spread(own, others):
    """Спред для сопоставления с отчётностью: собственный, а если он выброс (< −5 или > 40 п.п.: флоатеры, короткие выпуски
    у оферты) — медиана остальных выпусков эмитента. Если все выбросы — спреда нет, сравнение идёт по рейтингу."""
    ok = lambda v: v is not None and -5 <= v <= 40      # noqa: E731
    if ok(own):
        return own
    sp = sorted(v for v in others if ok(v))
    if sp:
        return sp[len(sp) // 2]
    return None


def _iss_spread_rating(mb, isin):
    me = next((x for x in mb if x["me"]), None)
    spread = _iss_pick_spread(me.get("spread") if me else None, [x.get("spread") for x in mb if x is not me])
    rts = [x["rating"] for x in mb if x.get("rating") in RATING_SCALE]
    rating = (me or {}).get("rating") or (max(rts, key=RATING_SCALE.index) if rts else None)
    return spread, rating


def issuer_card(isin):
    isin = (isin or "").strip().upper()
    card = {"ok": False, "isin": isin, "errors": []}
    em = issuer_of(isin)
    if not em:
        card["errors"].append("Не удалось определить эмитента по ISIN (Мосбиржа недоступна или бумага не найдена).")
        return card
    card["issuer"] = {"title": em.get("title"), "short": em.get("short") or em.get("title"), "inn": em.get("inn"), "emitter_id": em.get("emitter_id")}
    inn = em.get("inn")
    if not inn:
        card["errors"].append("У эмитента нет ИНН в справочнике Мосбиржи (иностранный эмитент, государство).")
        card["fin"] = {"status": "noinn", "years": []}
        card["score"] = {"ok": False, "reason": "ИНН эмитента неизвестен."}
        return card

    def run(fn):
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001
            return None, str(e)[:120]
    (fin, e1), (hist, e2), (mb, e3) = pool_map(run, [lambda: issuer_fin(inn, em.get("title") or ""), lambda: iss_history(inn),
                                                     lambda: _iss_market_bonds(inn, isin)], workers=3)
    for lab, er in (("отчётность ФНС", e1), ("история выпусков", e2), ("рыночные данные", e3)):
        if er:
            card["errors"].append("%s: %s" % (lab, er))
    ci = tcat_info(isin) or {}
    card["fin"] = fin or {"status": "err", "years": [], "note": "Отчётность временно недоступна."}
    card["score"] = iss_score_fin(fin, _iss_is_fin(em.get("title"), ci.get("sector"))) if fin else {"ok": False, "reason": "Отчётность недоступна."}
    card["history"] = hist
    card["bonds"] = mb or []
    spread, rating = _iss_spread_rating(card["bonds"], isin)
    if not rating:
        try:
            rt = best_rating(isin, em.get("title") or "")
            rating = rt["v"] if rt else None
        except Exception:  # noqa: BLE001
            rating = None
    card["market"] = iss_market(card["score"].get("score") if card["score"].get("ok") else None, spread, rating)
    card["ok"] = True
    return card


# ── эмитенты портфеля ──

def _iss_portfolio(cfg, acc, job):
    rep_ = build_bonds(cfg, acc)
    rows = [r for r in rep_.get("rows", []) if r.get("isin") and r.get("value_rub")]
    gov = [r for r in rows if r.get("sector") == "government"]
    work = [r for r in rows if r.get("sector") != "government"]
    job["total"] = len(work)
    # 1) эмитент по ISIN (кэш навсегда), 2) группировка по ИНН
    ems = pool_map(lambda r: issuer_of(r["isin"]), work, workers=4)
    groups = {}
    for r, em in zip(work, ems):
        k = (em or {}).get("inn") or ("isin:" + r["isin"])
        g = groups.setdefault(k, {"inn": (em or {}).get("inn"), "title": (em or {}).get("short") or (em or {}).get("title") or r.get("name"),
                                  "full": (em or {}).get("title"), "rows": [], "known": bool(em)})
        g["rows"].append(r)
    glist = list(groups.values())
    job["total"] = len(glist)
    uni = {}
    try:
        uni = {e["_isin"]: e for e in _bc_universe()}
    except Exception:  # noqa: BLE001
        pass

    def one(g):
        try:
            rs = sorted(g["rows"], key=lambda r: -(r.get("value_rub") or 0))
            top = rs[0]
            val = sum(r.get("value_rub") or 0 for r in rs)
            res = {"inn": g["inn"], "title": g["title"], "full": g["full"], "isin": top["isin"], "logo": top.get("logo"), "color": top.get("color"),
                   "value_rub": val, "share": sum(r.get("share") or 0 for r in rs), "n_bonds": len(rs), "bonds": [r["name"] for r in rs][:4]}
            ci = tcat_info(top["isin"]) or {}
            rts = []
            for r in rs:
                try:
                    b = best_rating(r["isin"], r.get("name") or "")
                    if b:
                        rts.append(b["v"])
                except Exception:  # noqa: BLE001
                    pass
            rating = max(rts, key=RATING_SCALE.index) if rts else None
            sps = [uni[r["isin"]].get("spread") for r in rs if r["isin"] in uni]
            spread = _iss_pick_spread(None, sps)
            res["rating"] = rating
            res["spread"] = spread
            if not g["inn"]:
                res.update(status="noinn", note="ИНН эмитента неизвестен.", score=None)
                return res
            fin = issuer_fin(g["inn"], g["full"] or "")
            res["status"] = fin["status"]
            res["note"] = fin.get("note")
            sc = iss_score_fin(fin, _iss_is_fin(g["full"] or g["title"], ci.get("sector")))
            res["fin_mode"] = bool(sc.get("fin_mode"))
            if sc.get("ok"):
                last = fin["years"][-1]
                res.update(score=sc["score"], key=sc["key"], label=sc["label"], year=sc["year"], holding=sc.get("holding"),
                           nd_ebit=last.get("nd_ebit"), cover=last.get("cover"), eq_ratio=last.get("eq_ratio"), cur_liq=last.get("cur_liq"),
                           rev=last.get("rev"), net_debt=last.get("net_debt"), debt_eq=last.get("debt_eq"))
                res["market"] = iss_market(sc["score"], spread, rating)
            else:
                res.update(score=None, note=sc.get("reason") or res.get("note"))
            return res
        except Exception as e:  # noqa: BLE001
            return {"inn": g["inn"], "title": g["title"], "isin": g["rows"][0]["isin"], "value_rub": sum(r.get("value_rub") or 0 for r in g["rows"]),
                    "share": sum(r.get("share") or 0 for r in g["rows"]), "n_bonds": len(g["rows"]), "score": None, "status": "err",
                    "note": "Ошибка: %s" % str(e)[:100]}
        finally:
            job["done"] += 1
    out = pool_map(one, glist, workers=4)
    out.sort(key=lambda x: -(x.get("value_rub") or 0))
    scored = [x for x in out if x.get("score") is not None]
    sh_s = sum(x["share"] for x in scored)
    bad = sum(x["share"] for x in scored if x["key"] in ("weak", "alarm"))
    dist = {k: sum(1 for x in scored if x["key"] == k) for _, k, _t in ISS_LABELS}
    return {"rows": out, "n": len(out), "n_scored": len(scored), "share_scored": sh_s, "share_bad": bad,
            "avg_score": (sum(x["score"] * x["share"] for x in scored) / sh_s) if sh_s else None, "dist": dist,
            "gov_share": sum(r.get("share") or 0 for r in gov), "gov_n": len(gov), "updated": datetime.now().strftime("%H:%M")}


def issuers_payload(cfg, acc, q, force):
    key = (token_key(cfg), acc)
    with _iss_jobs_lock:
        job = _iss_jobs.get(key)
        fresh = job and job["state"] == "done" and time.time() - job["t"] < 1800
        if job and job["state"] == "run":
            return {"pending": True, "done": job["done"], "total": job["total"]}
        if fresh and not force:
            return job["res"]
        job = {"state": "run", "done": 0, "total": 0, "t": time.time(), "res": None}
        _iss_jobs[key] = job

    def work():
        try:
            job["res"] = _iss_portfolio(cfg, acc, job)
            job["state"] = "done"
        except Exception as e:  # noqa: BLE001
            job["res"] = {"error": str(e)[:200] or "Не удалось собрать эмитентов"}
            job["state"] = "done"
        job["t"] = time.time()
    threading.Thread(target=work, daemon=True).start()
    return {"pending": True, "done": 0, "total": 0}


def _iss_api_one(cfg, acc, q, force):
    isin = (q.get("isin") or "").strip().upper()
    key = "iss_card_v2_" + isin
    if not force:
        hit = store().get(key, ttl=6 * 3600)
        if hit:
            return hit
    c = issuer_card(isin)
    if c.get("ok") and not c["errors"]:
        store().put(key, c)
    return c


API_GET["/api/issuer"] = _iss_api_one
API_GET["/api/issuers"] = issuers_payload
