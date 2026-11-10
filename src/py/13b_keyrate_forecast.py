# ═══════════════════════════════ прогноз ключевой ставки ═══════════════════════════════
# Нужен для флоатеров: будущие купоны = прогноз ключевой ставки + спред эмитента (см. bond_flows в 08a_bondcalc.py).
# Источники по убыванию приоритета (первый сработавший):
#   cbr    — «Среднесрочный прогноз Банка России» (PDF на cbr.ru, строка «Ключевая ставка, в среднем за год»; диапазон -> середина);
#   survey — макроэкономический опрос Банка России (HTML-таблица, медиана «Ключевая ставка ... в среднем за год»);
#   market — форвардные ставки КБД Мосбиржи (приближение, см. _kr_market_path);
#   flat   — текущая ключевая ставка без изменений.

KR_TTL, KR_ERR_TTL = 24 * 3600, 3600
KR_MODES = ("cbr", "survey", "market", "flat")
KR_NAMES = {"cbr": "Среднесрочный прогноз Банка России", "survey": "Макроопрос аналитиков (Банк России)",
            "market": "Рыночные ожидания (форварды КБД)", "flat": "Ключевая ставка без изменений"}
KR_HORIZON_M = 48
_kr_mem = {}
_kr_lock = threading.Lock()


def http_bytes(url, timeout=30):
    if not _ext_ctx:
        _ext_ctx.append(make_ssl_context())
    req = urllib.request.Request(url, headers=EXT_UA)
    with urllib.request.urlopen(req, timeout=timeout, context=_ext_ctx[0]) as r:
        return r.read()


# ── минимальный разбор PDF (stdlib): Flate-потоки, ToUnicode, операторы Tf/Tm/Td/TJ ──

def _pdf_inflate(body):
    head, _, rest = body.partition(b"stream")
    if not rest:
        return b""
    rest = rest[1:] if rest[:1] == b"\n" else (rest[2:] if rest[:2] == b"\r\n" else rest[1:] if rest[:1] == b"\r" else rest)
    rest = rest[:rest.rfind(b"endstream")] if b"endstream" in rest else rest
    if b"FlateDecode" in head:
        return zlib.decompressobj().decompress(rest)
    return rest


def _pdf_objects(d):
    objs = {}
    for m in re.finditer(rb"(?<![0-9])(\d+) 0 obj(.*?)endobj", d, re.S):
        objs[int(m.group(1))] = m.group(2)
    for body in list(objs.values()):
        head = body.partition(b"stream")[0]
        if b"/ObjStm" not in head:
            continue
        n = int(re.search(rb"/N\s+(\d+)", head).group(1))
        first = int(re.search(rb"/First\s+(\d+)", head).group(1))
        data = _pdf_inflate(body)
        nums = [int(x) for x in re.findall(rb"\d+", data[:first])]
        pairs = list(zip(nums[0:2 * n:2], nums[1:2 * n:2]))
        for i, (num, off) in enumerate(pairs):
            end = pairs[i + 1][1] if i + 1 < len(pairs) else len(data) - first
            objs.setdefault(num, data[first + off:first + end])
    return objs


def _pdf_cmap(data):
    s = data.decode("latin-1")
    m = re.search(r"begincodespacerange\s*<([0-9A-Fa-f]+)>", s)
    width = len(m.group(1)) // 2 if m else 1
    mp = {}

    def u(h):
        return bytes.fromhex(h).decode("utf-16-be", "replace")
    for blk in re.findall(r"beginbfchar(.*?)endbfchar", s, re.S):
        for a, b in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            mp[int(a, 16)] = u(b)
    for blk in re.findall(r"beginbfrange(.*?)endbfrange", s, re.S):
        for a, b, c in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])", blk):
            lo, hi = int(a, 16), int(b, 16)
            if c.startswith("["):
                for i, h in enumerate(re.findall(r"<([0-9A-Fa-f]+)>", c)):
                    mp[lo + i] = u(h)
            else:
                base = int(c[1:-1], 16)
                nb = len(c) - 2
                for i in range(hi - lo + 1):
                    mp[lo + i] = u(("%0" + str(nb) + "x") % (base + i))
    return width, mp


def _pdf_tokens(s):
    i, n = 0, len(s)
    out = []
    ws = b" \t\r\n\x00\x0c"
    delim = b"()<>[]/%"
    while i < n:
        c = s[i:i + 1]
        if c in ws:
            i += 1
        elif c == b"%":
            while i < n and s[i:i + 1] not in b"\r\n":
                i += 1
        elif c == b"(":
            depth, j, buf = 1, i + 1, bytearray()
            while j < n and depth:
                ch = s[j:j + 1]
                if ch == b"\\":
                    nx = s[j + 1:j + 2]
                    if nx in b"01234567" and nx:
                        k = j + 1
                        while k < j + 4 and s[k:k + 1] and s[k:k + 1] in b"01234567":
                            k += 1
                        buf.append(int(s[j + 1:k], 8) & 255)
                        j = k
                        continue
                    buf += {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\x0c"}.get(nx, nx)
                    j += 2
                    continue
                if ch == b"(":
                    depth += 1
                elif ch == b")":
                    depth -= 1
                    if not depth:
                        j += 1
                        break
                buf += ch
                j += 1
            out.append(("s", bytes(buf)))
            i = j
        elif c == b"<":
            if s[i + 1:i + 2] == b"<":
                out.append(("op", "<<"))
                i += 2
            else:
                j = s.index(b">", i)
                h = re.sub(rb"\s", b"", s[i + 1:j])
                if len(h) % 2:
                    h += b"0"
                out.append(("s", bytes.fromhex(h.decode())))
                i = j + 1
        elif c == b">":
            out.append(("op", ">>"))
            i += 2 if s[i + 1:i + 2] == b">" else 1
        elif c in b"[]":
            out.append(("op", c.decode()))
            i += 1
        elif c == b"/":
            j = i + 1
            while j < n and s[j:j + 1] not in ws and s[j:j + 1] not in delim:
                j += 1
            out.append(("n", s[i + 1:j].decode("latin-1")))
            i = j
        else:
            j = i
            while j < n and s[j:j + 1] not in ws and s[j:j + 1] not in delim:
                j += 1
            t = s[i:j].decode("latin-1")
            try:
                out.append(("num", float(t)))
            except ValueError:
                out.append(("op", t))
            i = max(j, i + 1)
    return out


def pdf_text_fragments(d):
    """[(x, y, size, text)] из PDF (stdlib: Flate + ToUnicode). Для простых однотипных документов ЦБ."""
    objs = _pdf_objects(d)
    fonts = {}
    for body in objs.values():
        head = body.partition(b"stream")[0]
        for m in re.finditer(rb"/Font\s*(?:<<(.*?)>>|(\d+)\s+0\s+R)", head, re.S):
            blk = m.group(1) if m.group(1) is not None else objs.get(int(m.group(2)), b"")
            for nm, num in re.findall(rb"/([A-Za-z0-9_.+-]+)\s+(\d+)\s+0\s+R", blk):
                fb = objs.get(int(num), b"")
                tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", fb)
                if tu and nm.decode() not in fonts:
                    fonts[nm.decode()] = _pdf_cmap(_pdf_inflate(objs.get(int(tu.group(1)), b"")))
    frags = []
    for body in objs.values():
        head = body.partition(b"stream")[0]
        if b"/Length" not in head or b"/Type" in head and (b"/XObject" in head or b"/ObjStm" in head or b"/XRef" in head):
            continue
        try:
            data = _pdf_inflate(body)
        except Exception:
            continue
        if b"BT" not in data or b" Tf" not in data:
            continue
        stack, font, size = [], None, 10.0
        lm = [0.0, 0.0]
        for kind, v in _pdf_tokens(data):
            if kind != "op" or v in ("[", "]", "<<", ">>"):
                stack.append((kind, v))
                continue
            args = stack
            stack = []
            if v == "Tf":
                nm = [a for a in args if a[0] == "n"]
                nu = [a[1] for a in args if a[0] == "num"]
                font = nm[-1][1] if nm else font
                size = nu[-1] if nu else size
            elif v == "Tm":
                nu = [a[1] for a in args if a[0] == "num"]
                if len(nu) >= 6:
                    lm = [nu[4], nu[5]]
            elif v in ("Td", "TD"):
                nu = [a[1] for a in args if a[0] == "num"]
                if len(nu) >= 2:
                    lm = [lm[0] + nu[-2], lm[1] + nu[-1]]
            elif v in ("TJ", "Tj", "'", '"'):
                width, mp = fonts.get(font, (1, None))
                txt = ""
                for k, a in args:
                    if k != "s":
                        continue
                    if mp is None:
                        txt += a.decode("cp1252", "replace")
                    else:
                        w = width if len(a) % width == 0 else 1
                        for p in range(0, len(a), w):
                            txt += mp.get(int.from_bytes(a[p:p + w], "big"), "")
                if txt:
                    frags.append((lm[0], lm[1], size, txt))
    return frags


# ── источник 1: среднесрочный прогноз Банка России (PDF) ──

KR_CBR_PAGE = "https://www.cbr.ru/dkp/mp_dec/decision_key_rate/"


def _kr_num(s):
    return float(s.replace(",", "."))


def _kr_cells(txt):
    """'19,2 14,6 12,5–13,5 9,0–10,0' -> [(low, high)]. Одиночное значение с двумя знаками (14,61) — сноска, отбрасываем её."""
    toks = re.findall(r"(\d+(?:,\d+)?)(?:\s*[–-]\s*(\d+(?:,\d+)?))?", txt)
    cells = []
    for a, b in toks:
        if not b and re.fullmatch(r"\d+,\d\d", a):
            a = a[:-1]
        cells.append((_kr_num(a), _kr_num(b or a)))
    return cells


def _kr_parse_pdf(data):
    """Строка «Ключевая ставка, в среднем за год» таблицы основных параметров прогноза -> {год: (low, high)}."""
    fr = pdf_text_fragments(data)
    big = [f for f in fr if f[2] >= 8]          # мелкий шрифт — сноски и надстрочные индексы

    def row(y, tol=2.5):
        rs = sorted((f for f in big if abs(f[1] - y) <= tol), key=lambda f: f[0])
        return "".join(f[3] for f in rs)
    lab = [f for f in big if f[3].startswith("Ключевая ставка")]
    first = [f for f in big if f[3].startswith("Инфляция")]
    if not lab or not first:
        raise ValueError("нет строки таблицы")
    y0 = max(f[1] for f in first)
    m = re.search(r"годовых(.*)$", row(lab[0][1]))
    cells = _kr_cells(m.group(1) if m else "")
    hdr = "".join(f[3] for f in sorted((f for f in big if y0 + 3 < f[1] < y0 + 45 and f[0] > 150), key=lambda f: (f[0], -f[1])))
    years = sorted({int(y) for y in re.findall(r"20\d\d", hdr)})
    if len(years) != len(cells) or not years:
        raise ValueError("не сошлись годы (%d) и значения (%d)" % (len(years), len(cells)))
    return {y: c for y, c in zip(years, cells)}


def _kr_cbr():
    s = http_text(KR_CBR_PAGE, 30)
    links = re.findall(r'href="(/Content/Document/File/\d+/forecast_(\d\d)(\d\d)(\d\d)\.pdf)"', s)
    if not links:
        raise ValueError("нет ссылки на прогноз")
    path, yy, mm, dd = max(links, key=lambda x: x[1:])
    as_of = "20%s-%s-%s" % (yy, mm, dd)
    st = store()
    ck = "kr_pdf:" + path
    pt = st.get(ck)
    if pt is None:
        yr = _kr_parse_pdf(http_bytes("https://www.cbr.ru" + path, 40))
        pt = {str(k): list(v) for k, v in yr.items()}
        st.put(ck, pt)                     # PDF конкретного заседания не меняется
    years = {int(k): tuple(v) for k, v in pt.items()}
    # в таблице первым идёт последний фактический год: он не прогноз
    return {"as_of": as_of, "url": "https://www.cbr.ru" + path, "years": years}


# ── источник 2: макроопрос Банка России (HTML-таблица) ──

KR_SURVEY_PAGE = "https://cbr.ru/statistics/ddkp/mo_br/"
_MONTHS_RU = ["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]


def _kr_survey():
    s = http_text(KR_SURVEY_PAGE, 30)
    i = s.find("Ключевая ставка")
    j = s.rfind("<table", 0, i)
    k = s.find("</table>", i)
    if i < 0 or j < 0 or k < 0:
        raise ValueError("нет таблицы опроса")
    rows = []
    for r in re.findall(r"<tr.*?</tr>", s[j:k], re.S):
        rows.append([re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).replace("&nbsp;", " ").strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)])
    hdr = next(r for r in rows if sum(bool(re.match(r"20\d\d", c)) for c in r) >= 3)
    kr = next(r for r in rows if r and r[0].startswith("Ключевая ставка"))
    years = {}
    for h, v in zip(hdr, kr):
        m, y = re.match(r"(20\d\d)", h), re.match(r"\s*(\d+,\d+|\d+)", v)
        if m and y and "факт" not in h:
            years[int(m.group(1))] = (_kr_num(y.group(1)),) * 2        # медиана; в скобках — прошлый опрос
    if not years:
        raise ValueError("нет прогнозных значений")
    plain = re.sub(r"<[^>]+>", " ", s)
    m = re.search(r"Результаты опроса:\s*([А-Яа-я]+)\s+(20\d\d)", plain)
    as_of = ""
    if m:
        mo = next((n + 1 for n, p in enumerate(_MONTHS_RU) if m.group(1).lower().startswith(p)), 0)
        as_of = "%s-%02d" % (m.group(2), mo) if mo else m.group(2)
    return {"as_of": as_of, "url": KR_SURVEY_PAGE, "years": years}


# ── фактическая ключевая ставка ──

def key_rate_on(series, d):
    """Ключевая ставка, действовавшая на дату d (ISO), по ряду [[дата, %]]; None, если ряд не покрывает дату."""
    if not series or d < series[0][0]:
        return None
    i = bisect.bisect_right([x[0] for x in series], d) - 1
    return series[i][1]


def _kr_current():
    ser = key_rate_series()
    if not ser:
        raise ValueError("нет ключевой ставки")
    return ser, ser[-1][1]


# ── построение месячного пути ──

def _kr_days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def _kr_add(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def _kr_interp(knots, t):
    if t <= knots[0][0]:
        return knots[0][1]
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if t <= x1:
            return y0 + (y1 - y0) * (t - x0) / ((x1 - x0) or 1)
    return knots[-1][1]


def _kr_month_starts(today, n):
    y, m = int(today[:4]), int(today[5:7])
    out = []
    for _ in range(n):
        m += 1
        if m > 12:
            y, m = y + 1, 1
        out.append("%04d-%02d-01" % (y, m))
    return out


def _kr_path_from_yearly(yearly, k0, today, series):
    """Путь ставки, у которого среднее за год совпадает со срединным значением прогноза.
    Узлы: сегодня = текущая ставка; для текущего года — середина оставшейся части (цель = средняя ставка на остаток года,
    выведенная из годовой средней и уже известной фактической части); для следующих лет — 2 июля.
    Между узлами линейно, после последнего — плоско. Значения узлов подгоняются итерациями так, чтобы дневное среднее
    по году (для текущего — по оставшейся его части) равнялось целевому."""
    cur = int(today[:4])
    spans = []          # [год, t_от, t_до, цель, t_узла] в днях от сегодня
    for y in sorted(yearly):
        if y < cur:
            continue
        lo, hi = yearly[y]
        mid = (lo + hi) / 2.0
        b = _kr_days(today, "%d-12-31" % y)
        if y == cur:
            if b < 20:
                continue
            ny = _kr_days("%d-01-01" % y, "%d-12-31" % y) + 1
            done = _kr_days("%d-01-01" % y, today)
            tot = 0.0
            for i in range(done):
                r = key_rate_on(series, _kr_add("%d-01-01" % y, i))
                if r is None:
                    tot = None
                    break
                tot += r
            if tot is not None and ny > done:
                rest = (mid * ny - tot) / (ny - done)
                if abs(rest - mid) <= 6 and rest > 0.5:
                    mid = rest
            spans.append([y, 0, b, mid, b / 2.0])
        else:
            a = _kr_days(today, "%d-01-01" % y)
            spans.append([y, a, b, mid, float(_kr_days(today, "%d-07-02" % y))])
    if not spans:
        raise ValueError("нет прогнозных лет")
    vals = [s[3] for s in spans]
    for _ in range(40):
        knots = [(0.0, k0)] + [(s[4], v) for s, v in zip(spans, vals)]
        worst = 0.0
        for n_, s in enumerate(spans):
            avg = sum(_kr_interp(knots, t) for t in range(int(s[1]), int(s[2]) + 1)) / (s[2] - s[1] + 1)
            err = s[3] - avg
            worst = max(worst, abs(err))
            vals[n_] = max(0.5, vals[n_] + 0.8 * err)
        if worst < 0.005:
            break
    knots = [(0.0, k0)] + [(s[4], v) for s, v in zip(spans, vals)]
    pts = [(today, round(k0, 3))]
    for d in _kr_month_starts(today, KR_HORIZON_M):
        pts.append((d, round(_kr_interp(knots, _kr_days(today, d)), 3)))
    return pts


def _kr_market_path(k0, today):
    """Путь из форвардных ставок КБД: 3-месячный форвард f(t) на горизонте t (эффективная годовая ставка).
    Ключевая ставка ~ форвард минус срочная премия: премия принята 0,75 п.п. в год горизонта, но не более 1,5 п.п.
    Начало привязано к текущей ставке: сдвиг (k0 - f(0)) затухает линейно за 2 года. Это грубая оценка рыночных
    ожиданий, а не прогноз ЦБ."""
    if not kbd_curve():
        raise ValueError("нет КБД")

    def z(t):
        return (1 + kbd_at(t) / 100.0) ** t

    def fwd(t):
        h = 0.25
        return ((z(t + h) / z(t)) ** (1 / h) - 1) * 100.0
    f0 = fwd(0.0)
    pts = [(today, round(k0, 3))]
    for d in _kr_month_starts(today, KR_HORIZON_M):
        t = _kr_days(today, d) / 365.0
        pts.append((d, round(max(0.5, fwd(t) + (k0 - f0) * max(0.0, 1 - t / 2.0) - min(1.5, 0.75 * t)), 3)))
    return pts


def _kr_flat_path(k0, today):
    return [(today, round(k0, 3))] + [(d, round(k0, 3)) for d in _kr_month_starts(today, KR_HORIZON_M)]


def _kr_yearly_from_path(path):
    by = defaultdict(list)
    for d, v in path:
        by[int(d[:4])].append(v)
    return [{"year": y, "low": round(min(v), 2), "high": round(max(v), 2), "mid": round(sum(v) / len(v), 2)} for y, v in sorted(by.items())]


def _kr_try(src, today):
    """Один источник -> dict с path/yearly/as_of либо исключение."""
    ser, k0 = _kr_current()
    if src in ("cbr", "survey"):
        st = store()
        ck = "kr_src:" + src
        raw = st.get(ck, ttl=KR_TTL)
        if raw is None:
            raw = (_kr_cbr if src == "cbr" else _kr_survey)()
            st.put(ck, {"as_of": raw["as_of"], "url": raw["url"], "years": {str(k): list(v) for k, v in raw["years"].items()}})
        years = {int(k): tuple(v) for k, v in raw["years"].items() if int(k) >= int(today[:4])}     # фактические годы не нужны
        path = _kr_path_from_yearly(years, k0, today, ser)
        yearly = [{"year": y, "low": lo, "high": hi, "mid": round((lo + hi) / 2.0, 2)} for y, (lo, hi) in sorted(years.items())]
        return {"as_of": raw["as_of"], "url": raw["url"], "yearly": yearly, "path": path, "key_rate": k0}
    path = _kr_market_path(k0, today) if src == "market" else _kr_flat_path(k0, today)
    return {"as_of": today, "url": "", "yearly": _kr_yearly_from_path(path), "path": path, "key_rate": k0}


def keyrate_forecast_info(mode=None):
    """{source, source_name, mode, as_of, yearly:[{year, low, high, mid}], path:[(дата, %)], key_rate, tried:{источник: ошибка}}.
    mode — из настройки keyrate_mode; пробуем выбранный источник, затем следующие по цепочке cbr -> survey -> market -> flat.
    Кэш источников 24 часа (в базе), путь на сегодня — в памяти."""
    if mode is None:
        try:
            mode = load_config().get("keyrate_mode")
        except Exception:  # noqa: BLE001
            mode = None
    if mode not in KR_MODES:
        mode = "cbr"
    today = date.today().isoformat()
    ck = (mode, today)
    with _kr_lock:
        hit = _kr_mem.get(ck)
        if hit and time.time() - hit[0] < (KR_TTL if hit[1].get("source") != "none" else KR_ERR_TTL):
            return hit[1]
        tried, res = {}, None
        for src in KR_MODES[KR_MODES.index(mode):]:
            try:
                res = _kr_try(src, today)
                res["source"] = src
                break
            except Exception as e:  # noqa: BLE001
                tried[src] = str(e)[:140] or e.__class__.__name__
        if res is None:
            res = {"source": "none", "as_of": today, "url": "", "yearly": [], "path": [], "key_rate": None}
        res.update(mode=mode, tried=tried, source_name=KR_NAMES.get(res["source"], "нет данных"))
        _kr_mem.clear()
        _kr_mem[ck] = (time.time(), res)
        return res


def keyrate_path():
    """Месячный путь ключевой ставки [(дата ISO, % годовых)] на ~4 года вперёд (первая точка — сегодня).
    Источник — keyrate_forecast_info(); пусто, если ничего не получилось."""
    try:
        return keyrate_forecast_info()["path"]
    except Exception:  # noqa: BLE001
        return []


def keyrate_at(path, d):
    """Прогнозная ставка на дату d (ISO) по пути (линейная интерполяция между месячными точками)."""
    if not path:
        return None
    if d <= path[0][0]:
        return path[0][1]
    ds = [p[0] for p in path]
    i = bisect.bisect_right(ds, d)
    if i >= len(path):
        return path[-1][1]
    (d0, v0), (d1, v1) = path[i - 1], path[i]
    w = _kr_days(d0, d) / float(_kr_days(d0, d1) or 1)
    return v0 + (v1 - v0) * w
