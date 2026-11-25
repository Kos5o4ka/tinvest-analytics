# ═══════════════════ устойчивость эмитентов: банкротные модели, расширенный долг, риск размытия ═══════════════════
# Всё считается по РСБУ из ГИР БО (суммы в тыс. ₽). Это приближённая модель, а не заключение о платёжеспособности.

CRP_CODES_BS = ("1100", "1200", "1300", "1400", "1410", "1450", "1500", "1510", "1540", "1550", "1600")
CRP_CODES_FR = ("2110", "2200", "2400")
CRP_TTL = 7 * 86400
_crp_jobs = {}
_crp_jobs_lock = threading.Lock()

CRP_DILUTION = [
    ("spo", "Допэмиссия / SPO", re.compile(r"допол\w*\s+(?:выпуск\w*|эмисси\w*)\s*(?:обыкн\w*\s+|привилег\w*\s+)?(?:акци|ценных)|допол\w+\s+эмисси|\bSPO\b|вторичн\w+\s+(?:публичн\w+\s+)?размещени\w+\s+акци|размещени\w+\s+(?:допол\w+\s+)?акци|увеличени\w+\s+уставн\w+\s+капитал", re.I)),
    ("convert", "Конвертируемые бумаги", re.compile(r"конвертируем\w+\s+(?:облигац|ценн|бумаг)|конвертаци\w+\s+(?:облигац|в\s+акци)|облигац\w+,?\s+конвертируем", re.I)),
    ("option", "Опционная программа", re.compile(r"опцион\w*\s+(?:программ|план)|программ\w+\s+опцион|мотивационн\w+\s+программ|\bESOP\b|\bMSOP\b|\bLTI\b", re.I)),
    ("buyback", "Выкуп / размещение акций", re.compile(r"выкуп\w*\s+(?:собственн\w+\s+)?акци|buy-?back|обратн\w+\s+выкуп|приобретени\w+\s+(?:эмитентом\s+)?собственн\w+\s+акци", re.I)),
    ("lockup", "Ограничение продажи (lock-up)", re.compile(r"lock-?up|лок-?ап|локап|ограничени\w+\s+на\s+продаж\w+\s+акци", re.I)),
]


def crp_dilution_match(text):
    """Список ключей категорий риска размытия, найденных в заголовке/тексте раскрытия."""
    t = text or ""
    return [k for k, _n, rx in CRP_DILUTION if rx.search(t)]


def crp_dilution_scan(items):
    """items: [{title, date, url}] -> совпадения [{kind, label, title, date, url}], свежие сверху."""
    names = {k: n for k, n, _rx in CRP_DILUTION}
    out = []
    for it in items or []:
        for k in crp_dilution_match(it.get("title") or ""):
            out.append({"kind": k, "label": names[k], "title": it.get("title"), "date": it.get("date"), "url": it.get("url")})
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out


def _crp_div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _crp_sub(a, b):
    return None if a is None or b is None else a - b


def crp_savitskaya(c, prev=None):
    """Модель Савицкой. c, prev — {код РСБУ: значение}. Возвращает {ok, z, x:{X1..X5}, zone, key}."""
    ca, nca, eq, assets = c.get("1200"), c.get("1100"), c.get("1300"), c.get("1600")
    pa = (prev or {}).get("1600")
    avg = (assets + pa) / 2.0 if assets is not None and pa is not None else assets
    x = {"X1": _crp_div(_crp_sub(eq, nca), ca), "X2": _crp_div(ca, nca), "X3": _crp_div(c.get("2110"), avg),
         "X4": _crp_div(c.get("2400"), assets), "X5": _crp_div(eq, assets)}
    if any(v is None for v in x.values()):
        return {"ok": False, "x": x, "reason": "не хватает строк отчётности"}
    z = 0.111 * x["X1"] + 13.239 * x["X2"] + 1.676 * x["X3"] + 0.515 * x["X4"] + 3.80 * x["X5"]
    hi = z < 8
    return {"ok": True, "z": z, "x": x, "key": "high" if hi else "ok", "zone": "высокий риск (Z < 8)" if hi else "ниже высокого риска (Z ≥ 8)",
            "avg_prev": pa is not None}


def crp_saifullin(c, prev=None):
    """Модель Сайфуллина–Кадыкова: R = 2K1 + 0,1K2 + 0,08K3 + 0,45K4 + K5."""
    ca, nca, eq, assets = c.get("1200"), c.get("1100"), c.get("1300"), c.get("1600")
    pa = (prev or {}).get("1600")
    avg = (assets + pa) / 2.0 if assets is not None and pa is not None else assets
    rev = c.get("2110")
    np_val = c.get("2400")
    k5 = _crp_div(np_val, eq)
    if eq is not None and eq < 0 and k5 is not None and k5 > 0:
        k5 = -k5                       # убыток при отрицательном капитале не может давать положительную рентабельность
    k = {"K1": _crp_div(_crp_sub(eq, nca), ca), "K2": _crp_div(ca, c.get("1500")), "K3": _crp_div(rev, avg),
         "K4": _crp_div(c.get("2200"), rev), "K5": k5}
    if any(v is None for v in k.values()):
        return {"ok": False, "x": k, "reason": "не хватает строк отчётности"}
    r = 2 * k["K1"] + 0.1 * k["K2"] + 0.08 * k["K3"] + 0.45 * k["K4"] + k["K5"]
    neg_eq = eq is not None and eq <= 0
    bad = neg_eq or r < 1
    zone = ("неудовлетворительное состояние (отрицательный капитал)" if neg_eq
            else "неудовлетворительное состояние (R < 1)" if bad else "удовлетворительное состояние (R ≥ 1)")
    return {"ok": True, "r": r, "x": k, "key": "high" if bad else "ok", "zone": zone, "avg_prev": pa is not None}


CRP_EXT_FLAG = 0.25


def crp_ext_debt(c):
    """Расширенная долговая нагрузка по балансу (тыс. ₽). Возвращает компоненты, итоги и коэффициенты."""
    g = c.get
    if g("1410") is None and g("1510") is None and all(g(k) is None for k in ("1450", "1550", "1540")):
        return {"ok": False}
    rep = (g("1410") or 0) + (g("1510") or 0)
    extra = sum(g(k) or 0 for k in ("1450", "1550", "1540"))
    ext = rep + extra
    ebit, eq = g("2200"), g("1300")
    flag = extra > 0 and ext >= rep * (1 + CRP_EXT_FLAG)
    names = [("1410", "Долгосрочные заимствования"), ("1510", "Краткосрочные заимствования"), ("1450", "Прочие долгосрочные обязательства"),
             ("1550", "Прочие краткосрочные обязательства"), ("1540", "Оценочные обязательства")]
    return {"ok": True, "reported": rep, "extra": extra, "extended": ext,
            "uplift": (ext / rep - 1) if rep > 0 else None, "flag": bool(flag),
            "components": [{"code": k, "name": n, "value": g(k)} for k, n in names],
            "ext_ebit": ext / ebit if ebit and ebit > 0 else None, "rep_ebit": rep / ebit if ebit and ebit > 0 else None,
            "ext_eq": ext / eq if eq and eq > 0 else None, "rep_eq": rep / eq if eq and eq > 0 else None,
            "ebit": ebit, "equity": eq}


def crp_is_fin(name, sector=None):
    return bool(ISS_FIN_RE.search(name or "") or re.search(r"банк|страхов|\bНКО\b", name or "", re.I) or sector == "financial")


def crp_analyze_years(years, is_fin):
    """years: {год: {код: значение}} -> строки по годам (последние 5)."""
    rows = []
    for y in sorted(years)[-5:]:
        c, prev = years[y], years.get(y - 1)
        row = {"y": y, "debt": crp_ext_debt(c), "fin": bool(is_fin)}
        if is_fin:
            na = {"ok": False, "na": True, "reason": "неприменимо к банкам, лизингу, МФО и другим финансовым компаниям"}
            row["sav"], row["sk"] = dict(na), dict(na)
        else:
            row["sav"], row["sk"] = crp_savitskaya(c, prev), crp_saifullin(c, prev)
        rows.append(row)
    return rows


def _crp_parse(lst):
    """Список отчётов ФНС -> {год: {код: тыс. ₽}} с расширенным набором строк (логика как в _iss_parse_bfo)."""
    years, prio = {}, {}
    for y in lst or []:
        try:
            per = int(y.get("period"))
        except (TypeError, ValueError, AttributeError):
            continue
        cor = None
        for tc in y.get("typeCorrections") or []:
            c = (tc or {}).get("correction")
            if isinstance(c, dict) and (c.get("balance") or c.get("financialResult")):
                cor = c
                if c.get("periodType") in (12, None):
                    break
        if not cor:
            continue
        for off in (0, 1, 2):
            for kind, codes in (("financialResult", CRP_CODES_FR), ("balance", CRP_CODES_BS)):
                if kind == "financialResult" and off == 2:
                    continue
                for code in codes:
                    v = _iss_pick(cor, kind, code, off)
                    if v is None:
                        continue
                    k = (per - off, code)
                    if k not in prio or off < prio[k]:
                        prio[k] = off
                        years.setdefault(per - off, {})[code] = v
    return years


def crp_raw(inn, name=""):
    """Сырые строки РСБУ по годам из ГИР БО (кэш 7 суток). {status, years:{y:{код:знач}}, note}."""
    key = "crp_raw_v1_" + inn
    hit = store().get(key, ttl=CRP_TTL)
    if hit:
        return {"status": hit["status"], "years": {int(k): v for k, v in hit["years"].items()}, "note": hit.get("note")}
    fin = issuer_fin(inn, name)
    if fin.get("status") != "ok" or not fin.get("org_id"):
        return {"status": fin.get("status") or "nf", "years": {}, "note": fin.get("note") or "Отчётность не найдена."}
    lst = _iss_fns_get("/nbo/organizations/%s/bfo/" % fin["org_id"])
    ys = _crp_parse(lst if isinstance(lst, list) else [])
    res = {"status": "ok" if ys else "nobfo", "years": ys, "note": None if ys else "Отчётность в ГИР БО пустая или в нестандартной форме."}
    store().put(key, {"status": res["status"], "years": {str(k): v for k, v in ys.items()}, "note": res["note"]})
    return res


def crp_events(isin, inn):
    """Факты раскрытия эмитента (при наличии ИНН — по ИНН, плюс по ISIN для полноты) -> ([{title, date, url}], источники). Без дублей."""
    lst = []
    try:
        if inn:
            lst.extend(disc_facts(None, inn) or [])
        if isin:
            lst.extend(disc_facts(isin, None) or [])
    except Exception:  # noqa: BLE001
        if not lst:
            return [], []
    out, seen = [], set()
    for it in lst:
        if not isinstance(it, dict):
            continue
        k = it.get("doc_id") or (it.get("title"), it.get("published"))
        if k in seen:
            continue
        seen.add(k)
        out.append({"title": it.get("title") or "", "date": it.get("published") or it.get("event_date"), "url": it.get("url")})
    return out, ["раскрытие информации (disc_facts)"]


def crp_resolve(q):
    """ISIN / тикер / ИНН -> {inn, name, isin} или {error}."""
    s = (q or "").strip().upper()
    if not s:
        return {"error": "Введите ISIN, тикер или ИНН эмитента."}
    if s.isdigit() and len(s) in (10, 12):
        return {"inn": s, "name": "", "isin": None}
    em = issuer_of(s)
    if not em or not em.get("inn"):
        return {"error": "Не удалось определить эмитента (нужен ИНН: иностранные эмитенты и государство не поддерживаются)."}
    return {"inn": em["inn"], "name": em.get("short") or em.get("title") or "", "isin": s if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", s) else None,
            "full": em.get("title")}


def crp_card(q):
    r = crp_resolve(q)
    if r.get("error"):
        return {"ok": False, "error": r["error"]}
    inn, name, isin = r["inn"], r.get("full") or r.get("name") or "", r.get("isin")
    sector = (tcat_info(isin or (q or "").strip().upper()) or {}).get("sector")
    is_fin = crp_is_fin(name, sector)
    raw = crp_raw(inn, name)
    out = {"ok": True, "inn": inn, "name": r.get("name") or name, "is_fin": is_fin, "status": raw["status"], "note": raw.get("note"), "years": []}
    if raw["years"]:
        out["years"] = crp_analyze_years(raw["years"], is_fin)
    items, srcs = crp_events(isin, inn)
    out["dilution"] = {"matches": crp_dilution_scan(items), "n_scanned": len(items), "sources": srcs,
                       "links": bond_doc_links(isin or "", None, inn)}
    return out


def crp_api(cfg, acc, q, force):
    s = (q.get("q") or "").strip()
    key = "crp_card_v1_" + s.upper()
    if not force:
        hit = store().get(key, ttl=6 * 3600)
        if hit:
            return hit
    try:
        c = crp_card(s)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "Ошибка расчёта: %s" % str(e)[:120]}
    if c.get("ok") and c["years"]:
        store().put(key, c)
    return c


def crp_summary_row(c):
    """Краткая строка пакетного режима из карточки."""
    ys = c.get("years") or []
    last = ys[-1] if ys else None
    return {"inn": c.get("inn"), "name": c.get("name"), "is_fin": c.get("is_fin"), "year": last and last["y"],
            "sav": last and last["sav"].get("z"), "sav_key": last and last["sav"].get("key"),
            "sk": last and last["sk"].get("r"), "sk_key": last and last["sk"].get("key"),
            "uplift": last and last["debt"].get("uplift"), "flag": bool(last and last["debt"].get("flag")),
            "ext_ebit": last and last["debt"].get("ext_ebit"), "n_dil": len((c.get("dilution") or {}).get("matches") or []),
            "note": c.get("note") or c.get("error")}


def _crp_my_issuers(cfg, acc):
    """Эмитенты облигаций и акций портфеля: [(идентификатор для разбора, название)]."""
    out, seen = [], set()
    try:
        for r in build_bonds(cfg, acc).get("rows", []):
            if r.get("isin") and r.get("sector") != "government" and r["isin"] not in seen:
                seen.add(r["isin"])
                out.append((r["isin"], r.get("name") or r["isin"]))
    except Exception:  # noqa: BLE001
        pass
    try:
        for r in build_summary(cfg, acc, "all")["portfolio"]["positions"]:
            if r.get("type") == "share" and (r.get("qty") or 0) > 0:
                k = r.get("isin") or r.get("ticker")
                if k and k not in seen:
                    seen.add(k)
                    out.append((k, r.get("name") or k))
    except Exception:  # noqa: BLE001
        pass
    return out


def crp_batch(cfg, acc, q, force):
    key = (token_key(cfg), acc)
    with _crp_jobs_lock:
        job = _crp_jobs.get(key)
        if job and job["state"] == "run":
            return {"pending": True, "done": job["done"], "total": job["total"]}
        if job and job["state"] == "done" and not force and time.time() - job["t"] < 1800:
            return job["res"]
        job = {"state": "run", "done": 0, "total": 0, "t": time.time(), "res": None}
        _crp_jobs[key] = job

    def work():
        try:
            lst = _crp_my_issuers(cfg, acc)
            job["total"] = len(lst)
            rows, seen = [], set()
            for ident, nm in lst:           # последовательно: ГИР БО и так ограничен по частоте
                try:
                    c = crp_card(ident)
                    if c.get("ok"):
                        if c["inn"] in seen:
                            job["done"] += 1
                            continue
                        seen.add(c["inn"])
                        row = crp_summary_row(c)
                        row["name"] = row["name"] or nm
                    else:
                        row = {"name": nm, "note": c.get("error")}
                    row["q"] = ident
                    rows.append(row)
                except Exception as e:  # noqa: BLE001
                    rows.append({"name": nm, "q": ident, "note": "Ошибка: %s" % str(e)[:80]})
                job["done"] += 1
            job["res"] = {"rows": rows, "n": len(rows), "updated": datetime.now().strftime("%H:%M")}
        except Exception as e:  # noqa: BLE001
            job["res"] = {"error": str(e)[:200] or "Не удалось собрать эмитентов"}
        job["state"] = "done"
        job["t"] = time.time()
    threading.Thread(target=work, daemon=True).start()
    return {"pending": True, "done": 0, "total": 0}


API_GET["/api/crp"] = crp_api
API_GET["/api/crp/batch"] = crp_batch
