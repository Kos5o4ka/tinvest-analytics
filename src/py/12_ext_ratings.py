# ═══════════════════ внешние данные: кредитные рейтинги, КБД, ключевая ставка ═══════════════════
# Наружу уходят только обезличенные GET-запросы к публичным страницам (t.me, cbr.ru, moex.com):
# ни токен, ни состав портфеля никуда не передаются.

EXT_UA = {"User-Agent": "Mozilla/5.0 (compatible; tinvest-analytics)"}
_ext_ctx = []


def http_text(url, timeout=25):
    if not _ext_ctx:
        _ext_ctx.append(make_ssl_context())
    req = urllib.request.Request(url, headers=EXT_UA)
    with urllib.request.urlopen(req, timeout=timeout, context=_ext_ctx[0]) as r:
        return r.read().decode("utf-8", "replace")


# ── кредитные рейтинги (канал @issuerRatings: АКРА, Эксперт РА, НКР, НРА) ──

RATING_CH = "https://t.me/s/issuerRatings"
RATING_SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
                "B+", "B", "B-", "CCC", "CC", "C", "D"]
RT_KEY, RT_DAYS, RT_MAX_PAGES, RT_TTL, RT_OLD = "ratings_v1", 430, 280, 12 * 3600, 600
_L = "[AАBВCС]"
_NOTLET = "(?<![A-Za-zА-Яа-яЁё])"
_RATING_PATS = [re.compile(p) for p in (
    _NOTLET + "(" + _L + "{1,3})([+\\-−–]?)\\s?(?i:\\(RU\\))",
    _NOTLET + "ru(" + _L + "{1,3})([+\\-−–]?)(?![A-Za-zА-Яа-яЁё])(?!\\.[a-z])",
    _NOTLET + "(" + _L + "{1,3})([+\\-−–]?)\\.ru",
    _NOTLET + "(" + _L + "{1,3})([+\\-−–]?)\\|ru\\|")]
_LAT = str.maketrans({"А": "A", "В": "B", "С": "C"})
_Q_STOP = ("стабильн", "позитивн", "негативн", "развива", "наблюдени", "эксперт", "акра", "нкр", "нра", "рейтинг",
           "подробнее")
_LEGAL = {"пао", "ао", "ооо", "оао", "зао", "мфк", "мкк", "пко", "нко", "гк", "группа", "компания", "холдинг",
          "корпорация", "бо", "бп", "кс", "обл", "серия", "серии", "выпуск", "сфо"}
_rt_state = {"running": False, "progress": "", "error": ""}
_rt_lock = threading.Lock()
_rt_idx = {}


def _rating_token(t):
    best = None
    for p in _RATING_PATS:
        m = p.search(t)
        if m and (best is None or m.start() < best.start()):
            best = m
    if not best:
        return None
    v = (best.group(1) + best.group(2)).translate(_LAT).upper().replace("−", "-").replace("–", "-")
    return v if v in RATING_SCALE else None


def _rating_issuer(t):
    for m in re.finditer(r"[«\"“]([^»\"”]{2,70})[»\"”]", t):
        q = m.group(1).strip()
        ql = q.lower().replace("c", "с")
        if any(w in ql for w in _Q_STOP) or "|" in q or re.fullmatch(r"[A-Za-z0-9 ]{1,3}", q):
            continue
        return q
    m = re.search(r"(?:ПАО|АО|ООО|МФК|МКК|ПКО|НКО|ОАО|ЗАО)\s+([А-ЯЁA-Z][\wЁё\-]+(?:\s+[А-ЯЁA-Z][\wЁё\-]+)?)", t)
    if not m:
        m = re.search(r"рейтинг\w*\s+(?:кредитоспособности\s+|облигаци\w+\s+|выпуск\w*\s+)*"
                      r"([А-ЯЁA-Z][^,.«»\n]{2,55}?)\s+(?:на\s+уровне|до\s+уровня)", t, re.I)
        if not m:
            return None
        c = re.split(r"\s+(?:серии|серий|классов?)\b", m.group(1), flags=re.I)[0].strip()
        return c if c and not re.search(r"\d", c) and len(c.split()) <= 6 else None
    words = []
    for w in m.group(1).split():
        if w.upper() in ("НА", "ДО", "ПО", "И", "С", "В", "ПРОГНОЗ", "СЕРИИ", "СЕРИЯ", "ВЫПУСКА", "ОБЛИГАЦИЙ", "КЛАССА"):
            break
        words.append(w)
    return " ".join(words) or None


def name_tokens(s):
    out = set()
    for i, t in enumerate(re.findall(r"[a-zа-я0-9]+", (s or "").lower().replace("ё", "е"))):
        if t in _LEGAL or (i == 0 and t == "банк") or len(t) < 2 or any(ch.isdigit() for ch in t):
            continue
        out.add(t[:5])
    return frozenset(out)


def parse_rating_post(text):
    low = text.lower()
    head = low[:80]
    agency = next((a for pat, a in ((r"\bакра\b", "АКРА"), (r"эксперт\s+ра", "Эксперт РА"), (r"\bнкр\b", "НКР"),
                                    (r"\bнра\b", "НРА")) if re.search(pat, head)), None)
    if not agency or re.search(r"ожидаем|\.sf|структурир|сфо|\bкласс|esg|\.gq|качеств|надежност|некредитн|\.am", low):
        return None
    issuer = _rating_issuer(text)
    if not issuer:
        return None
    level = "bond" if re.search(r"облигаци|выпуск", low) else "issuer"
    if "отозва" in low:
        return {"agency": agency, "issuer": issuer, "level": level, "withdrawn": True}
    v = _rating_token(re.split(r"(?i)\bранее\b", text)[0])
    if not v:
        return None
    om = re.search(r"прогноз.{0,40}?(стабильн|позитивн|негативн|развивающ)", low)
    return {"agency": agency, "issuer": issuer, "level": level, "rating": v,
            "outlook": {"стабильн": "стабильный", "позитивн": "позитивный", "негативн": "негативный",
                        "развивающ": "развивающийся"}.get(om.group(1), "") if om else ""}


def tg_page(before=None):
    s = http_text(RATING_CH + ("?before=%d" % before if before else ""))
    ids, posts = [], []
    for blk in s.split("tgme_widget_message_wrap")[1:]:
        m = re.search(r'data-post="issuerRatings/(\d+)"', blk)
        if not m:
            continue
        ids.append(int(m.group(1)))
        t = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', blk, re.S)
        d = re.search(r'<time datetime="([^"]+)"', blk)
        if t and d:
            import html as _html
            txt = _html.unescape(re.sub(r"<br/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", t.group(1))))
            posts.append((int(m.group(1)), d.group(1), txt))
    return ids, posts


def _ratings_run():
    st = store()
    try:
        try:
            sites_refresh(force=True)         # НКР: полный список эмитентов с сайта
        except Exception:  # noqa: BLE001
            pass
        data = st.get(RT_KEY) or {"items": {}, "max_id": 0, "updated": 0}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RT_DAYS)).isoformat()
        got, before, pages = {}, None, 0
        while pages < RT_MAX_PAGES:
            ids, posts = None, None
            for _ in range(3):
                try:
                    ids, posts = tg_page(before)
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(1.5)
            if ids is None:
                raise OSError("не удалось загрузить канал рейтингов (нет доступа к t.me)")
            if not ids:
                break
            pages += 1
            for p in posts:
                got[p[0]] = p
            _rt_state["progress"] = "загружено страниц: %d" % pages
            mn = min(ids)
            oldest = min((p[1] for p in posts), default="9")
            if data["max_id"] and mn <= data["max_id"]:
                break
            if not data["max_id"] and oldest < cutoff:
                break
            if before is not None and mn >= before:
                break
            before = mn
            time.sleep(0.25)
        items = data["items"]
        for pid in sorted(got):
            if pid <= data["max_id"]:
                continue
            _, iso, text = got[pid]
            r = parse_rating_post(text)
            if not r:
                continue
            toks = "".join(sorted(name_tokens(r["issuer"])))
            if not toks:
                continue
            key = "%s|%s|%s" % (toks, r["agency"], r["level"])
            if r.get("withdrawn"):
                if r["level"] == "issuer":
                    items.pop(key, None)
                continue
            items[key] = {"issuer": r["issuer"], "agency": r["agency"], "level": r["level"], "rating": r["rating"],
                          "outlook": r["outlook"], "date": iso[:10], "post": pid}
        data["max_id"] = max([data["max_id"]] + list(got))
        data["updated"] = time.time()
        st.put(RT_KEY, data)
        _rt_state["error"] = ""
        _rt_idx.clear()
    except Exception as e:  # noqa: BLE001
        _rt_state["error"] = str(e)[:200]
    finally:
        _rt_state["running"] = False
        _rt_state["progress"] = ""


def ratings_start(force=False):
    with _rt_lock:
        if _rt_state["running"]:
            return False
        if not force:
            d = store().get(RT_KEY)
            if d and time.time() - d.get("updated", 0) < RT_TTL:
                return False
        _rt_state["running"] = True
    threading.Thread(target=_ratings_run, daemon=True).start()
    return True


def ratings_status():
    d = store().get(RT_KEY) or {}
    return {"updated": d.get("updated"), "count": len(d.get("items") or {}), "running": _rt_state["running"],
            "progress": _rt_state["progress"], "error": _rt_state["error"]}


def _rating_index():
    d = store().get(RT_KEY) or {}
    sd = store().get(SITE_KEY) or {}
    ed = store().get(EXP_KEY) or {}
    stamp = (d.get("updated"), sd.get("updated"), len(ed.get("items") or {}))
    if _rt_idx.get("u") != stamp:
        old = (date.today() - timedelta(days=RT_OLD)).isoformat()
        merged = {}
        for src in (d.get("items") or {}, sd.get("items") or {}, ed.get("items") or {}):
            for k, it in src.items():
                if it["date"] >= old and (k not in merged or it["date"] >= merged[k]["date"]):
                    merged[k] = it
        items = [(it, name_tokens(it["issuer"])) for it in merged.values()]
        exact, inv = {}, {}
        for it, toks in items:
            if not toks:
                continue
            exact.setdefault(toks, []).append(it)
            for t in toks:
                inv.setdefault(t, []).append((it, toks))
        _rt_idx.clear()
        _rt_idx.update(u=stamp, items=items, exact=exact, inv=inv)
    return _rt_idx


def rating_for(name):
    """Рейтинг эмитента по названию облигации. Точное совпадение названий — надёжно, частичное — approx."""
    bt = name_tokens(name)
    if not bt:
        return None
    ix = _rating_index()
    best = {}

    def put(it, sc):
        sc += 0.5 if it["level"] == "issuer" else 0
        cur = best.get(it["agency"])
        if cur is None or sc > cur[0] or (sc == cur[0] and it["date"] > cur[1]["date"]):
            best[it["agency"]] = (sc, it)
    for it in ix.get("exact", {}).get(bt, []):
        put(it, 100.0)
    seen = set()
    for t in bt:
        for it, toks in ix.get("inv", {}).get(t, []):
            if id(it) in seen or toks == bt:
                continue
            seen.add(id(it))
            if not (toks <= bt or bt <= toks):
                continue
            sc = float(sum(len(x) for x in toks & bt))
            if sc < 6 and any(len(x) > 2 for x in (toks | bt) - (toks & bt)):
                continue
            if sc < 5:
                continue
            put(it, sc)
    if not best:
        return None
    allr = [{"agency": a, "rating": it["rating"], "issuer": it["issuer"], "date": it["date"], "outlook": it["outlook"],
             "approx": sc < 100} for a, (sc, it) in best.items()]
    low = max(allr, key=lambda x: RATING_SCALE.index(x["rating"]))     # консервативно: худшая из оценок
    return {"v": low["rating"], "agency": low["agency"], "issuer": low["issuer"], "date": low["date"],
            "approx": low["approx"], "all": allr}


def apply_ratings(rows):
    dist = defaultdict(float)
    for r in rows:
        r["rating"] = best_rating(r.get("isin") or r.get("ticker"), r.get("name") or "")
        dist[rating_bucket(r["rating"]["v"] if r["rating"] else None)] += r.get("value_rub") or 0
    return sorted(dist.items(), key=lambda x: -x[1])


def rating_bucket(v):
    if not v:
        return "нет рейтинга"
    i = RATING_SCALE.index(v)
    return "AAA" if i == 0 else "AA" if i <= 3 else "A" if i <= 6 else "BBB" if i <= 9 else "BB и ниже"


# ── рейтинги напрямую с сайтов агентств (НКР — список эмитентов, Эксперт РА — поиск по эмитенту) ──
# АКРА и НРА с сайтов недоступны программам (у АКРА сервер отдаёт неполную цепочку сертификатов,
# у НРА — таймауты), поэтому их рейтинги идут только из канала @issuerRatings.

SITE_KEY, EXP_KEY = "ratings_site_v1", "ratings_expert_v1"
_exp_state = {"running": False}
_SERIES_WORDS = {"бо", "бп", "кс", "обл", "серия", "серии", "выпуск"}


def _strip(t):
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", t))).strip()


def nkr_fetch():
    s = http_text("https://ratings.ru/ratings/issuers/", timeout=45)
    items = {}
    for row in re.findall(r'<tr id="bx_[^"]+".*?</tr>', s, re.S):
        td = [_strip(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(td) < 6:
            continue
        v = _rating_token(td[1])
        dm = re.search(r"(\d\d)\.(\d\d)\.(\d{4})", td[5])
        toks = "".join(sorted(name_tokens(td[0])))
        if not v or not dm or not toks:
            continue
        items["%s|НКР|issuer" % toks] = {"issuer": td[0], "agency": "НКР", "level": "issuer", "rating": v,
                                         "outlook": td[2], "date": "%s-%s-%s" % (dm.group(3), dm.group(2), dm.group(1))}
    return items


def sites_refresh(force=False):
    st = store()
    d = st.get(SITE_KEY)
    if d and not force and time.time() - d.get("updated", 0) < RT_TTL:
        return
    items = nkr_fetch()
    if items:
        st.put(SITE_KEY, {"items": items, "updated": time.time()})
        _rt_idx.clear()


def _bond_query(name):
    words = [w for w in re.split(r"\s+", (name or "").strip())
             if w and not any(ch.isdigit() for ch in w) and w.lower().replace("ё", "е") not in _SERIES_WORDS]
    return " ".join(words[:3])


def _expert_session():
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    if not _ext_ctx:
        _ext_ctx.append(make_ssl_context())
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=_ext_ctx[0]))
    op.addheaders = list(EXT_UA.items())
    return op


def expert_lookup(op, query, tokens):
    """Поиск эмитента на raexpert.ru, затем чтение страницы компании. Возвращает dict или None."""
    s = op.open("https://raexpert.ru/", timeout=25).read().decode("utf-8", "replace")
    tok = re.search(r'name="CSRFToken" value="([^"]+)"', s)
    if not tok:
        return None
    req = urllib.request.Request("https://raexpert.ru/search/", urllib.parse.urlencode(
        {"CSRFToken": tok.group(1), "search": query}).encode(), {"Referer": "https://raexpert.ru/"})
    res = op.open(req, timeout=30).read().decode("utf-8", "replace")
    seen, link = set(), None
    for href, name in re.findall(r'href="(/database/companies/[^"?]+?)/?"[^>]*>([^<]+)<', res):
        name = _strip(name)
        if href in seen or not name:
            continue
        seen.add(href)
        if name_tokens(name) == tokens:
            link = (href, name)
            break
    if not link:
        return None
    c = op.open("https://raexpert.ru" + link[0], timeout=30).read().decode("utf-8", "replace")
    m = re.search(r"(ru[^\s,<]+),\s*([А-Яа-я ]+?),\s*<a href=\"/releases/[^\"]+\">(\d\d)\.(\d\d)\.(\d{4})", c)
    if not m:
        return None
    v = _rating_token(m.group(1))
    if not v:
        return None
    return {"issuer": link[1], "agency": "Эксперт РА", "level": "issuer", "rating": v, "outlook": m.group(2).strip().lower(),
            "date": "%s-%s-%s" % (m.group(5), m.group(4), m.group(3))}


def _expert_run(names):
    try:
        st = store()
        d = st.get(EXP_KEY) or {"items": {}, "queried": {}}
        op = None
        now = time.time()
        for name in names:
            q = _bond_query(name)
            tokens = name_tokens(q)
            if not q or not tokens:
                continue
            qk = "".join(sorted(tokens))
            ts = d["queried"].get(qk)
            if ts and now - ts < 3 * 86400:
                continue
            try:
                op = op or _expert_session()
                it = expert_lookup(op, q, tokens)
            except Exception:  # noqa: BLE001
                continue
            d["queried"][qk] = time.time()
            if it:
                d["items"]["%s|Эксперт РА|issuer" % qk] = it
            st.put(EXP_KEY, d)
            _rt_idx.clear()
            time.sleep(0.6)
    finally:
        _exp_state["running"] = False


def expert_start(names):
    with _rt_lock:
        if _exp_state["running"]:
            return
        d = store().get(EXP_KEY) or {"queried": {}}
        now = time.time()
        todo = []
        for n in names:
            qk = "".join(sorted(name_tokens(_bond_query(n))))
            if qk and now - d["queried"].get(qk, 0) > 3 * 86400 and n not in todo:
                todo.append(n)
        if not todo:
            return
        _exp_state["running"] = True
    threading.Thread(target=_expert_run, args=(todo[:80],), daemon=True).start()


