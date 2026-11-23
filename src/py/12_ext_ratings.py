# ═══════════════════ внешние данные: кредитные рейтинги, КБД, ключевая ставка ═══════════════════
# Наружу уходят только обезличенные GET-запросы к публичным страницам (t.me, cbr.ru, moex.com):
# ни токен, ни состав портфеля никуда не передаются.


# ── кредитные рейтинги (каналы @ru_ratings и @issuerRatings: АКРА, Эксперт РА, НКР, НРА) ──

RT_CHANNELS = ("ru_ratings", "issuerRatings")        # порядок = приоритет при равной дате записей
RATING_CH = "https://t.me/s/"
RT_LINK_HOSTS = ("acra-ratings.ru", "raexpert.ru", "ratings.ru", "ra-national.ru", "t.me")
RATING_SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-",
                "B+", "B", "B-", "CCC", "CC", "C", "D"]
RT_KEY, RT_DAYS, RT_MAX_PAGES, RT_TTL, RT_OLD = "ratings_v3", 430, 280, 12 * 3600, 600      # RT_MAX_PAGES — на каждый канал
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


# Окончания для грубого стемминга: «Ульяновской»/«Ульяновская» и «Томска»/«Томск» дают одну основу,
# а разные компании с общим началом («Интерлизинг» и «ИнтерФудГрупп») — разные ключи.
_NAME_ENDINGS = ("иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими", "ой", "ей", "ий", "ый", "ая", "яя",
                 "ое", "ее", "ые", "ие", "ых", "их", "ом", "ем", "ам", "ям", "ах", "ях", "ою", "ую", "юю",
                 "а", "я", "у", "ю", "е", "ы", "и", "о", "ь", "й")


def _name_stem(t):
    if not re.match(r"[а-я]", t):
        return t
    for e in _NAME_ENDINGS:
        if t.endswith(e) and len(t) - len(e) >= 4:
            return t[:-len(e)]
    return t


def name_tokens(s):
    """Основы слов названия (без правовых форм, номеров и падежных окончаний): ключи эмитента для группировки и журнала."""
    out = set()
    for i, t in enumerate(re.findall(r"[a-zа-я0-9]+", (s or "").lower().replace("ё", "е"))):
        if t in _LEGAL or (i == 0 and t == "банк") or len(t) < 2 or any(ch.isdigit() for ch in t):
            continue
        out.add(_name_stem(t))
    return frozenset(out)


_SERIES_TOK = re.compile(r"^(?:бо|боп|бп|п|кс|обл|р|с)?\d+[а-я]?\d*$")        # п01, боп1, бо01: хвост серии выпуска


def name_words(s):
    """Полные нормализованные слова названия по порядку (без правовых форм и слов с цифрами); «Банк» в начале остаётся.
    Если ничего не осталось («А101 001Р-01»), берутся слова с буквы с цифрами внутри, кроме признаков серии."""
    toks = [t for t in re.findall(r"[a-zа-я0-9]+", (s or "").lower().replace("ё", "е")) if t not in _LEGAL and len(t) >= 2]
    out = tuple(t for t in toks if not any(ch.isdigit() for ch in t))
    return out or tuple(t for t in toks if t[0].isalpha() and not _SERIES_TOK.match(t))


def _words_key(w):
    return "".join(sorted(set(w)))


def _words_match(bw, iw):
    """Сравнение названий по полным словам: (100, ...) — равны; иначе приблизительный балл (<100) или None.
    Совпадение только по префиксу допустимо, если одно слово — сокращение другого (капитал ~ кап, сбербанк ~ сберб)."""
    bs, is_ = frozenset(bw), frozenset(iw)
    if not bs or not is_:
        return None
    if bs == is_:
        return 100.0
    bj, ij = "".join(bw), "".join(iw)
    lo, hi = (bj, ij) if len(bj) <= len(ij) else (ij, bj)
    if len(lo) >= 5 and hi.startswith(lo):                          # «ГазпромКап» ~ «Газпром капитал»
        return float(min(len(lo), 90))
    small, big = (bs, is_) if len(bs) <= len(is_) else (is_, bs)
    sc = 0
    used = set()
    for w in small:
        hit = w if w in big else next((x for x in big if x not in used and min(len(w), len(x)) >= 4
                                       and (x.startswith(w) or w.startswith(x))), None)
        if hit is None:
            return None
        used.add(hit)
        sc += min(len(w), len(hit))
    rest = big - used
    if sc < 5 or (sc < 6 and any(len(x) > 2 for x in rest)):
        return None
    return float(min(sc, 90))


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


def rt_safe_url(u):
    """Ссылка на пресс-релиз: только https:// и хосты агентств/Telegram, иначе пустая строка."""
    u = (u or "").strip()
    try:
        pu = urllib.parse.urlsplit(u)
    except ValueError:
        return ""
    h = (pu.hostname or "").lower()
    if pu.scheme != "https" or not h or pu.username or pu.password:
        return ""
    return u if any(h == d or h.endswith("." + d) for d in RT_LINK_HOSTS) else ""


def rt_post_url(src, post):
    return "https://t.me/%s/%s" % (src or "issuerRatings", post) if post else None


_RR_AGENCY = (("акра", "АКРА"), ("эксперт", "Эксперт РА"), ("нкр", "НКР"), ("нра", "НРА"))
_RR_FIELDS = {"🏢": "co", "📝": "txt", "📊": "rt", "📅": "dt", "🔗": "url"}
_RR_RU = re.compile(r"(?i)\bru|\.ru|\(ru\)|\|ru\|")
_RT_SKIP = r"ожидаем|\.sf|структурир|сфо|\bкласс|esg|\.gq|качеств|надежност|некредитн|\.am"
_RR_OUT = {"стабильн": "стабильный", "позитивн": "позитивный", "негативн": "негативный", "развивающ": "развивающийся"}


def _ru_fields(text, links=None):
    """Разбор поста ru_ratings: (агентство, {поле: значение}). Поля: co 🏢, txt 📝, rt 📊, dt 📅, url 🔗."""
    lines = [x.strip() for x in (text or "").split("\n") if x.strip()]
    if not lines:
        return None, {}
    m = re.match(r"рейтинг\s+от\s+(.+)", lines[0], re.I)
    if not m:
        return None, {}
    nm = m.group(1).lower()
    agency = next((a for k, a in _RR_AGENCY if nm.startswith(k)), None)
    f = {}
    for ln in lines[1:]:
        for em, k in _RR_FIELDS.items():
            if ln.startswith(em):
                f.setdefault(k, ln[len(em):].strip())
                break
    url = rt_safe_url(f.get("url", ""))
    if not url:
        url = next((rt_safe_url(u) for u in links or [] if rt_safe_url(u)), "")
    f["url"] = url
    return agency, f


def _ru_body(agency, f):
    """Текст релиза для общих разборщиков: «📝» (Эксперт РА) либо «📊»/«🏢» (АКРА, НКР, НРА — текст в первой строке)."""
    parts = [f.get(k) for k in ("txt", "co", "rt") if f.get(k)]
    if "txt" not in f and "rt" in f:
        parts = [f["rt"]] + ([f["co"]] if f.get("co") else [])
    return " ".join(parts)


def _ru_iso(f, iso):
    m = re.fullmatch(r"(\d\d)\.(\d\d)\.(\d{4})", f.get("dt", ""))
    return "%s-%s-%s" % (m.group(3), m.group(2), m.group(1)) if m else (iso or "")[:10]


def parse_ru_ratings_post(text, links=None, iso=None):
    """Пост @ru_ratings -> {agency, issuer, level, rating, outlook, date, url} (или withdrawn=True), либо None.
    Структура: «Рейтинг от <агентство>», затем строки 🏢 эмитент, 📝 релиз, 📊 рейтинг, 📅 дата, 🔗 ссылка."""
    agency, f = _ru_fields(text, links)
    if not agency:
        return None
    body = _ru_body(agency, f)
    r = parse_rating_post("%s\n%s" % (agency, body))
    if not r and f.get("co") and "txt" not in f and _RR_RU.search(f.get("rt", "")) \
            and not re.search(_RT_SKIP, body.lower()):        # регионы и т. п.: только «🏢 название» и «📊 ruA (Стабильный)»
        v = _rating_token(f["rt"])
        if v:
            r = {"issuer": f["co"], "level": "issuer", "rating": v, "outlook": ""}
    if not r:
        return None
    date_ = _ru_iso(f, iso)
    if not date_:
        return None
    r = dict(r, issuer=re.sub(r"\s+", " ", re.sub(r"[«»\"“”]", "", r["issuer"])).strip())      # вложенные кавычки: «НК «РОСНЕФТЬ»
    out = {"agency": agency, "issuer": r["issuer"], "level": r["level"], "date": date_, "url": f.get("url", "")}
    if r.get("withdrawn"):
        out["withdrawn"] = True
        return out
    v = _rating_token(f.get("rt", "")) if _RR_RU.search(f.get("rt", "")) else None
    out["rating"] = v or r["rating"]
    om = re.search(r"(стабильн|позитивн|негативн|развивающ)", (f.get("rt") or "").lower())
    out["outlook"] = _RR_OUT[om.group(1)] if om else r.get("outlook", "")
    return out


RT_LOG_KEY, RT_LOG_DAYS = "ratings_log_v1", 730        # журнал рейтинговых действий: отдельно от ratings_v1
_RT_D = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:ru\s?D(?![A-Za-zА-Яа-я])|D\s?\(RU\)|D\.ru|RD(?![A-Za-z]))")
_RT_ACTIONS = {"присвоен", "подтверждён", "повышен", "понижен", "отозван", "под наблюдением", "прогноз изменён"}


def _rt_tok_d(t):
    return "D" if _RT_D.search(t or "") else _rating_token(t or "")


def parse_rating_action(text):
    """Рейтинговое действие из поста: {agency, issuer, level, action, rating, prev, outlook, watch, url} или None.
    Шире parse_rating_post: понимает дефолтные уровни (D/RD), «ранее ...», «с X до Y», статус «под наблюдением»."""
    r = parse_rating_post(text)
    low = text.lower()
    head = low[:80]
    if not r:
        agency = next((a for pat, a in ((r"\bакра\b", "АКРА"), (r"эксперт\s+ра", "Эксперт РА"), (r"\bнкр\b", "НКР"),
                                        (r"\bнра\b", "НРА")) if re.search(pat, head)), None)
        if not agency or re.search(r"ожидаем|\.sf|структурир|сфо|\bкласс|esg|\.gq|качеств|надежност|некредитн|\.am", low):
            return None
        issuer = _rating_issuer(text)
        if not issuer or not _RT_D.search(re.split(r"(?i)\bранее\b", text)[0]):
            return None
        r = {"agency": agency, "issuer": issuer, "level": "bond" if re.search(r"облигаци|выпуск", low) else "issuer",
             "rating": "D", "outlook": ""}
    first = re.split(r"\n", text.strip())[0]
    fl = first.lower()
    parts = re.split(r"(?i)\bранее\b", first, maxsplit=1)
    prev = None
    if len(parts) > 1:
        prev = _rt_tok_d(parts[1])
    else:
        m = re.search(r"(?i)\bс\s+(\S+?)\s+до\s+(\S+)", first)
        if m:
            prev = _rt_tok_d(m.group(1))
            r = dict(r, rating=_rt_tok_d(m.group(2)) or r.get("rating"))     # НКР: «с AA.ru до AA-.ru» — новый уровень второй
    watch = ""
    if re.search(r"сн[яя]л\w*\s+статус|снят\w*\s+статус", fl):
        watch = "removed"
    elif re.search(r"статус\w*\s+[«\"“]под наблюдением", fl) and re.search(r"присво|продли|установил|ввел|ввело", fl):
        watch = "set"
    elif "под наблюдением" in fl and "ранее" not in fl.split("под наблюдением")[0]:
        watch = "set"
    if "отозва" in fl:
        act = "отозван"
    elif re.search(r"повысил", fl):
        act = "повышен"
    elif re.search(r"понизил|снизил", fl):
        act = "понижен"
    elif watch == "set" and re.search(r"присво\w+\s+статус|установил\w*\s+статус", fl):
        act = "под наблюдением"
    elif re.search(r"изменил\w*\s+прогноз|изменив\s+прогноз|прогноз\w*\s+(?:по рейтингу\s+)?(?:был\s+)?изменен|пересмотрел\w*\s+прогноз", fl):
        act = "прогноз изменён"
    elif "подтверд" in fl:
        act = "подтверждён"
    elif "присво" in fl:
        act = "присвоен"
    elif watch == "set":
        act = "под наблюдением"
    else:
        return None
    um = re.search(r"https?://\S+", text[len(first):])
    om = re.search(r"прогноз.{0,60}?\bна\s+[«\"“]?(стабильн|позитивн|негативн|развивающ)", fl)
    if om:
        r = dict(r, outlook={"стабильн": "стабильный", "позитивн": "позитивный", "негативн": "негативный",
                             "развивающ": "развивающийся"}[om.group(1)])
    out = {"agency": r["agency"], "issuer": r["issuer"], "level": r["level"], "action": act,
           "rating": r.get("rating"), "prev": prev, "outlook": r.get("outlook") or "", "watch": watch,
           "url": um.group(0).rstrip(".,)") if um else ""}
    if act == "понижен" and out["rating"] and prev and out["rating"] == prev:
        out["action"] = "прогноз изменён"
    return out


def rating_log_add(log, pid, iso, text, src="issuerRatings", links=None):
    url = ""
    if src == "ru_ratings":                      # пост ru_ratings: действие читается из «📝»/«📊», дата — из «📅», ссылка — пресс-релиз
        agency, f = _ru_fields(text, links)
        if not agency:
            return
        a = parse_rating_action("%s: %s\n" % (agency, _ru_body(agency, f)))
        iso, url = _ru_iso(f, iso), f.get("url", "")
    else:
        a = parse_rating_action(text)
    if not a:
        return
    toks = sorted(name_tokens(a["issuer"]))
    if not toks:
        return
    a.update(post=pid, date=iso[:10], tokens=toks, src=src, url=url or rt_safe_url(a.get("url")))
    log["events"].append(a)


def rating_log_trim(log):
    old = (date.today() - timedelta(days=RT_LOG_DAYS)).isoformat()
    evs = sorted((e for e in log["events"] if e["date"] >= old), key=lambda e: (e["date"], e.get("src") or "", e["post"]))
    ru = [e for e in evs if e.get("src") == "ru_ratings"]

    def dup(e):       # то же действие уже есть из ru_ratings (даты постов могут различаться на пару дней)
        if e.get("src") == "ru_ratings":
            return False
        d0 = date.fromisoformat(e["date"])
        return any(x["agency"] == e["agency"] and x["tokens"] == e["tokens"] and x["action"] == e["action"]
                   and x["level"] == e["level"] and x.get("rating") == e.get("rating") and x.get("prev") == e.get("prev")
                   and abs((date.fromisoformat(x["date"]) - d0).days) <= 2 for x in ru)
    log["events"] = [e for e in evs if not dup(e)]


def tg_parse_page(s, channel):
    """HTML зеркала t.me/s/<канал> -> (ids, посты [(id, iso, текст, [ссылки])])."""
    import html as _html
    ids, posts = [], []
    for blk in s.split("tgme_widget_message_wrap")[1:]:
        m = re.search(r'data-post="%s/(\d+)"' % re.escape(channel), blk, re.I)
        if not m:
            continue
        ids.append(int(m.group(1)))
        t = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', blk, re.S)
        d = re.search(r'<time datetime="([^"]+)"', blk)
        if t and d:
            raw = t.group(1)
            links = [_html.unescape(h) for h in re.findall(r'<a\s[^>]*href="([^"]+)"', raw)]
            txt = _html.unescape(re.sub(r"<br/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", raw)))
            posts.append((int(m.group(1)), d.group(1), txt, links))
    return ids, posts


def tg_page(before=None, channel="ru_ratings"):
    return tg_parse_page(http_text("%s%s%s" % (RATING_CH, channel, "?before=%d" % before if before else "")), channel)


def rt_post_parse(channel, text, links, iso):
    """Пост канала -> запись о рейтинге (как parse_rating_post + date/url) либо None."""
    if channel == "ru_ratings":
        return parse_ru_ratings_post(text, links, iso)
    r = parse_rating_post(text)
    if r:
        um = re.search(r"https?://\S+", text)
        r = dict(r, date=iso[:10], url=rt_safe_url(um.group(0).rstrip(".,)")) if um else "")
    return r


def rt_merge(items, key, rec):
    """Положить запись в items: из того же канала — всегда (посты идут по возрастанию), из другого — только если свежее
    по дате, при равной дате побеждает канал с меньшим индексом в RT_CHANNELS (ru_ratings)."""
    old = items.get(key)
    if old:
        osrc, nsrc = old.get("src") or "issuerRatings", rec["src"]
        if osrc != nsrc:
            rk = lambda c: RT_CHANNELS.index(c) if c in RT_CHANNELS else 99
            if (rec["date"], -rk(nsrc)) < (old["date"], -rk(osrc)):
                return
            if not rec.get("url") and old.get("url") and old.get("rating") == rec.get("rating"):
                rec = dict(rec, url=old["url"])
    items[key] = rec


def _rt_scan(channel, base_id, cutoff):
    got, before, pages = {}, None, 0
    while pages < RT_MAX_PAGES:
        ids, posts = None, None
        for _ in range(3):
            try:
                ids, posts = tg_page(before, channel)
                break
            except Exception:  # noqa: BLE001
                time.sleep(1.5)
        if ids is None:
            raise OSError("не удалось загрузить канал @%s (нет доступа к t.me)" % channel)
        if not ids:
            break
        pages += 1
        for p in posts:
            got[p[0]] = p
        _rt_state["progress"] = "@%s: загружено страниц %d" % (channel, pages)
        mn = min(ids)
        oldest = min((p[1] for p in posts), default="9")
        if base_id and mn <= base_id:
            break
        if not base_id and oldest < cutoff:
            break
        if before is not None and mn >= before:
            break
        before = mn
        time.sleep(0.25)
    return got


def _ratings_run():
    st = store()
    try:
        try:
            sites_refresh(force=True)         # НКР: полный список эмитентов с сайта
        except Exception:  # noqa: BLE001
            pass
        data = st.get(RT_KEY) or {"items": {}, "max_ids": {}, "updated": 0}
        rlog = st.get(RT_LOG_KEY) or {"events": [], "max_id": 0}
        dm, lm = data.setdefault("max_ids", {}), rlog.setdefault("max_ids", {"issuerRatings": rlog.get("max_id", 0)})
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RT_DAYS)).isoformat()
        items, errs, okc = data["items"], [], 0
        for ch in RT_CHANNELS:
            try:       # пока журнал пуст — догружаем канал до границы RT_DAYS
                got = _rt_scan(ch, min(dm.get(ch, 0), lm.get(ch, 0)), cutoff)
            except Exception as e:  # noqa: BLE001
                errs.append(str(e)[:120])
                continue
            okc += 1
            for pid in sorted(got):
                _, iso, text, links = got[pid]
                if pid > lm.get(ch, 0):
                    try:
                        rating_log_add(rlog, pid, iso, text, ch, links)
                    except Exception:  # noqa: BLE001
                        pass
                if pid <= dm.get(ch, 0):
                    continue
                try:
                    r = rt_post_parse(ch, text, links, iso)
                except Exception:  # noqa: BLE001
                    r = None
                if not r:
                    continue
                toks = _words_key(name_words(r["issuer"]))
                if not toks:
                    continue
                key = "%s|%s|%s" % (toks, r["agency"], r["level"])
                if r.get("withdrawn"):
                    if r["level"] == "issuer" and (key not in items or items[key]["date"] <= r["date"]):
                        items.pop(key, None)
                    continue
                rt_merge(items, key, {"issuer": r["issuer"], "agency": r["agency"], "level": r["level"],
                                      "rating": r["rating"], "outlook": r["outlook"], "date": r["date"], "post": pid,
                                      "src": ch, "url": r.get("url") or ""})
            if got:
                dm[ch] = max(dm.get(ch, 0), max(got))
                lm[ch] = max(lm.get(ch, 0), max(got))
        if not okc:
            raise OSError(errs[0] if errs else "не удалось загрузить каналы рейтингов")
        data["max_id"] = max(dm.values() or [0])
        data["updated"] = time.time()
        st.put(RT_KEY, data)
        rlog["max_id"] = lm.get("issuerRatings", rlog.get("max_id", 0))
        rating_log_trim(rlog)
        st.put(RT_LOG_KEY, rlog)
        _rt_state["error"] = "; ".join(errs)
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


_RT_PREV = {"ratings_v3": ("ratings_v2", "ratings_v1")}


def _rt_src(key):
    """Хранилище рейтингов; пока новая версия пуста (после смены ключа идёт пересканирование) — берём прежнюю."""
    st = store()
    d = st.get(key)
    if d and d.get("items"):
        return d, 2
    for i, k in enumerate(_RT_PREV.get(key) or ((key[:-2] + "v1",) if key.endswith("_v2") else ())):
        old = st.get(k)
        if old and old.get("items"):
            return old, 1 + i * 10
    return d or {}, 2


def ratings_stamp():
    return _rating_index()["u"]


def _rating_index():
    (d, v1), (sd, v2), (ed, v3) = _rt_src(RT_KEY), _rt_src(SITE_KEY), _rt_src(EXP_KEY)
    stamp = (d.get("updated"), v1, sd.get("updated"), v2, len(ed.get("items") or {}), v3)
    if _rt_idx.get("u") != stamp:
        old = (date.today() - timedelta(days=RT_OLD)).isoformat()
        merged = {}
        for src in (d.get("items") or {}, sd.get("items") or {}, ed.get("items") or {}):
            for k, it in src.items():
                if it["date"] >= old and (k not in merged or it["date"] > merged[k]["date"]
                                          or (it["date"] == merged[k]["date"] and not (merged[k].get("url") or merged[k].get("post")))):
                    merged[k] = it
        items = [(it, name_words(it["issuer"])) for it in merged.values()]
        exact, inv = {}, {}
        for it, ws in items:
            if not ws:
                continue
            exact.setdefault(frozenset(ws), []).append(it)
            for t in {w[:4] for w in ws}:                              # кандидаты по 4-символьному префиксу слова
                inv.setdefault(t, []).append((it, ws))
        _rt_idx.clear()
        _rt_idx.update(u=stamp, items=items, exact=exact, inv=inv)
    return _rt_idx


def _rt_link(it):
    """url пресс-релиза (если есть), иначе ссылка на пост в Telegram, иначе None; плюс post/src записи."""
    post, src = it.get("post"), it.get("src") or ("issuerRatings" if it.get("post") else None)
    return {"url": rt_safe_url(it.get("url")) or rt_post_url(src, post) or None, "post": post, "src": src}


def rating_for(name):
    """Рейтинг эмитента по названию облигации. Точное совпадение названий — надёжно, частичное — approx."""
    bw = name_words(name)
    if not bw:
        return None
    ix = _rating_index()
    best = {}

    def put(it, sc):
        sc += 0.5 if it["level"] == "issuer" else 0
        cur = best.get(it["agency"])
        if cur is None or sc > cur[0] or (sc == cur[0] and it["date"] > cur[1]["date"]):
            best[it["agency"]] = (sc, it)
    bset = frozenset(bw)
    for it in ix.get("exact", {}).get(bset, []):
        put(it, 100.0)
    seen = set()
    for t in {w[:4] for w in bw}:
        for it, ws in ix.get("inv", {}).get(t, []):
            if id(it) in seen or frozenset(ws) == bset:
                continue
            seen.add(id(it))
            sc = _words_match(bw, ws)
            if sc:
                put(it, sc)
    if not best:
        return None
    allr = [{"agency": a, "rating": it["rating"], "issuer": it["issuer"], "date": it["date"], "outlook": it["outlook"],
             "approx": sc < 100, **_rt_link(it)} for a, (sc, it) in best.items()]
    pool = [x for x in allr if not x["approx"]] or allr                  # приблизительные не влияют на «худший», пока есть точные
    low = max(pool, key=lambda x: RATING_SCALE.index(x["rating"]))     # консервативно: худшая из оценок
    return {"v": low["rating"], "agency": low["agency"], "issuer": low["issuer"], "date": low["date"],
            "approx": low["approx"], "url": low["url"], "post": low["post"], "src": low["src"], "all": allr}


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

SITE_KEY, EXP_KEY = "ratings_site_v2", "ratings_expert_v2"
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
        toks = _words_key(name_words(td[0]))
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
    return {}                                           # cookie сессии raexpert (CSRF-токен привязан к ней)


def expert_lookup(op, query, tokens):
    """Поиск эмитента на raexpert.ru, затем чтение страницы компании. Возвращает dict или None."""
    s = ext_open("https://raexpert.ru/", timeout=25, jar=op)[1].decode("utf-8", "replace")
    tok = re.search(r'name="CSRFToken" value="([^"]+)"', s)
    if not tok:
        return None
    res = ext_open("https://raexpert.ru/search/", urllib.parse.urlencode({"CSRFToken": tok.group(1), "search": query}).encode(),
                   {"Referer": "https://raexpert.ru/", "Content-Type": "application/x-www-form-urlencoded"},
                   timeout=30, jar=op)[1].decode("utf-8", "replace")
    seen, link = set(), None
    for href, name in re.findall(r'href="(/database/companies/[^"?]+?)/?"[^>]*>([^<]+)<', res):
        name = _strip(name)
        if href in seen or not name:
            continue
        seen.add(href)
        if frozenset(name_words(name)) == frozenset(tokens):
            link = (href, name)
            break
    if not link:
        return None
    c = ext_open("https://raexpert.ru" + link[0], timeout=30, jar=op)[1].decode("utf-8", "replace")
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
            tokens = name_words(q)
            if not q or not tokens:
                continue
            qk = _words_key(tokens)
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
            qk = _words_key(name_words(_bond_query(n)))
            if qk and now - d["queried"].get(qk, 0) > 3 * 86400 and n not in todo:
                todo.append(n)
        if not todo:
            return
        _exp_state["running"] = True
    threading.Thread(target=_expert_run, args=(todo[:80],), daemon=True).start()


