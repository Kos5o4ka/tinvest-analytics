# ═══════════════════════════════ сообщения о раскрытии (714-П): классификация и поля ═══════════════════════════════
# Вход — уже извлечённый текст (doc_text из 12b). dc_extract(text, title, meta) -> {"kind", "inn", "ogrn", "event_date", "facts": [...], "warnings": [...]}.
# Виды: coupon_paid (выплаченные доходы), coupon_declared (начисленные/объявленные), default (неисполнение обязательств),
# buyback_result (итоги приобретения облигаций), other. Нумерация пунктов в разных формах отличается, поэтому нужный пункт
# ищется по тексту его заголовка (до двоеточия), а номер — запасной вариант.
# TODO: при нескольких ISIN в одном сообщении числа не делятся по блокам — каждому ISIN достаются общие значения (+ warning).

DC_PARSER_VERSION = "3"   # повышать при изменении логики разбора: сборщик (--reparse) перечитывает старые записи

_DC_MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}
_DC_DATE_TXT = re.compile(r"(?<!\d)(\d{1,2})\s*[»\"”’']?\s*(январ[яь]|феврал[яь]|марта?|апрел[яь]|ма[йя]|июн[яь]|июл[яь]|август[а]?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])\s*(\d{4})", re.I)
_DC_DATE_NUM = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{2})\.(\d{4})(?!\d)")
_DC_NUM = re.compile(r"\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")
_DC_ISIN = re.compile(r"\b(?:RU|SU)[0-9A-Z]{9}[0-9]\b")
_DC_ITEM = re.compile(r"^([1-4]\.\d{1,2})(?:\.(?=\s|$)|(?=\s|$))\s*")
_DC_RUB_AMT = re.compile(r"\d[\d  ]*(?:[.,]\d+)?\s*(?:\([^)]*\)\s*)?руб")
_DC_RATE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%?\s*(?:\([^)]*\)\s*)?(?:процент\w*\s*)?годов", re.I)
_DC_ORD = (("девятнадцат", 19), ("восемнадцат", 18), ("семнадцат", 17), ("шестнадцат", 16), ("пятнадцат", 15), ("четырнадцат", 14),
           ("тринадцат", 13), ("двенадцат", 12), ("одиннадцат", 11), ("девяност", 90), ("девяно", 90), ("восьмидесят", 80), ("восемьдесят", 80),
           ("семидесят", 70), ("семьдесят", 70), ("шестидесят", 60), ("шестьдесят", 60), ("пятидесят", 50), ("пятьдесят", 50),
           ("сороков", 40), ("сорок", 40), ("тридцат", 30), ("двадцат", 20), ("сотый", 100), ("сто", 100), ("десят", 10),
           ("девят", 9), ("восьм", 8), ("седьм", 7), ("шест", 6), ("пят", 5), ("четв", 4), ("трет", 3), ("втор", 2), ("перв", 1))


def dc_parse_number(s):
    """Первое число в строке: пробелы/nbsp — разделители тысяч, запятая или точка — десятичные."""
    m = _DC_NUM.search(s or "")
    if not m:
        return None
    try:
        return float(re.sub(r"[  ]", "", m.group(0)).replace(",", "."))
    except ValueError:
        return None


def dc_parse_rub(s):
    """Рубли: «80 620 552,40 рублей», «18 (Восемнадцать) рублей 32 копейки», «10 170 000 рублей 00 копеек»."""
    s2 = re.sub(r"\([^)]*\)", " ", s or "")
    m = _DC_NUM.search(s2)
    if not m:
        return None
    v = dc_parse_number(m.group(0))
    if v is None:
        return None
    if not re.search(r"[.,]", m.group(0)):
        k = re.match(r"\s*(?:руб\w*\.?)?\s*(\d{1,2})\s*коп", s2[m.end():], re.I)
        if k:
            v += int(k.group(1)) / 100.0
    return v


def _dc_dates(s):
    """Все даты строки [(позиция, 'YYYY-MM-DD')] в порядке появления."""
    res = []
    for m in _DC_DATE_TXT.finditer(s or ""):
        res.append((m.start(), int(m.group(3)), _DC_MONTHS.get(m.group(2).lower()[:3]), int(m.group(1))))
    for m in _DC_DATE_NUM.finditer(s or ""):
        res.append((m.start(), int(m.group(3)), int(m.group(2)), int(m.group(1))))
    out = []
    for pos, y, mo, d in sorted(res):
        try:
            out.append((pos, date(y, mo, d).isoformat()))
        except (TypeError, ValueError):
            continue
    return out


def dc_parse_date(s):
    """Первая дата в строке -> 'YYYY-MM-DD' (месяцы словами в родительном, «16», г./года, dd.mm.yyyy)."""
    d = _dc_dates(s)
    return d[0][1] if d else None


def dc_sections(text):
    """{'2.4': текст пункта}: пункт длится до следующей строки, начинающейся с номера (в т.ч. «2.1\\t», «2.1 »)."""
    secs, cur = {}, None
    for ln in (text or "").split("\n"):
        m = _DC_ITEM.match(ln.strip())
        if m:
            cur = m.group(1)
            if cur in secs:
                cur = "~" + cur            # повтор номера не затирает первый пункт
            secs[cur] = [ln.strip()[m.end():]]
        elif re.match(r"^[1-4]\.\s+[А-ЯЁ]", ln.strip()):
            cur = None                     # заголовок раздела («3. Подпись») закрывает пункт
        elif cur is not None:
            secs[cur].append(ln.strip())
    return {k: "\n".join(v).strip() for k, v in secs.items()}


def dc_classify(title, text):
    s = ((title or "") + " " + (text or "")[:600]).lower()
    s = re.sub(r"\s+", " ", s)
    if ("реализации приобретенных" in s or "реализации приобретённых" in s
            or "продаже ранее приобретенных" in s or "вторичной продаже" in s):
        return "placement_result"
    if ("итогах приобретения" in s or "результатах приобретения" in s
            or "исполнении обязательств по приобретению" in s):
        return "buyback_result"
    if "неисполнение обязательств" in s:
        return "default"
    if "выплаченные доходы" in s or "выплаченных доходах" in s:
        return "coupon_paid"
    if "начисленные доходы" in s or "начисленных (объявленных) доходах" in s:
        return "coupon_declared"
    if ("завершении размещения" in s or "итогах размещения" in s or "результатах размещения" in s
            or ("дополнительн" in s and "размещ" in s and "облигац" in s)):
        return "placement_result"
    return "other"


def dc_load_fixture(path):
    """Файл фикстуры: строки «ключ: значение» (source, published, code, company, title), строка «---», затем текст."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    head, sep, body = raw.partition("\n---\n")
    if not sep:
        return {}, raw
    meta = {}
    for ln in head.split("\n"):
        k, _, v = ln.partition(":")
        if _ and k.strip():
            meta[k.strip()] = v.strip()
    return meta, body.strip("\n")


def _dc_split(sec):
    """Пункт -> (заголовок, значение): по первому «:» (значение может идти со следующей строки), либо по «).» после
    стандартного заголовка без двоеточия (в нём нет цифр), либо по табу; иначе заголовок пуст."""
    i = sec.find(":")
    j = -1
    m = re.search(r"\)\s*\.\s", sec[:801])
    if m and m.start() >= 40 and not re.search(r"\d", sec[:m.start()]) and (i < 0 or m.start() < i):
        j = m.end()
    if j >= 0:
        return sec[:j], sec[j:]
    if 0 <= i <= 800:
        return sec[:i], sec[i + 1:]
    i = sec.find("\t")
    if i >= 0:
        return sec[:i], sec[i + 1:]
    return "", sec


def _dc_pick(secs, label_re, key=None):
    """Значение пункта по заголовку (регулярка, регистр не важен); не нашлось — по номеру key; иначе None."""
    for k, v in secs.items():
        if k[0] == "~":
            continue
        lab, val = _dc_split(v)
        if lab and re.search(label_re, lab, re.I | re.S):
            return val.strip()
    if key and key in secs:
        return _dc_split(secs[key])[1].strip()
    return None


def _dc_ordinal_words(s):
    """«Пятьдесят третий купонный период» -> 53 (слова непосредственно перед «купонн»); перебор с конца, пока слова — порядковое."""
    for m in reversed(list(re.finditer(r"((?:[а-яё]+\s+){1,3})купонн", s or "", re.I))):
        tot = 0
        for w in reversed(m.group(1).lower().split()):
            v = next((n for st, n in _DC_ORD if w.startswith(st)), None)
            if v is None:
                break
            tot += v
        if tot:
            return tot
    return None


def _dc_coupon_no(*texts):
    for t in texts:
        if not t:
            continue
        m = re.search(r"(?<![\d.])(\d+)\s*(?:-\s*\w{1,3})?\s*(?:\([^)]*\)\s*)?(?:отч[её]тн\w*\s*)?\(?купон", t, re.I)
        if m:
            return int(m.group(1))
        n = _dc_ordinal_words(t)
        if n:
            return n
    return None


def _dc_period(v):
    d = _dc_dates(v or "")
    if len(d) >= 2 and re.search(r"\bпо\b|оконч|[–—-]", v):
        return d[0][1], d[1][1]
    return None, None


def _dc_due(v):
    d = _dc_dates(v or "")
    if not d:
        return None
    if len(d) >= 2 and re.search(r"\bс\b.*\bпо\b", v, re.S):
        return d[-1][1]
    return d[0][1]


_DC_PCT = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*(?:\([^)]*\)\s*)?(?:%|процент)", re.I)


def _dc_rate(*texts):
    """Процентная ставка: число перед «%» / «процент…» (в т.ч. «15 (пятнадцать) процентов годовых»)."""
    for t in texts:
        m = _DC_PCT.search(t or "") or _DC_RATE.search(t or "")
        if m:
            return float(m.group(1).replace(",", "."))
    return None


_DC_AMT = re.compile(r"(?<![\w.,])(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)")
_DC_CUR_TAIL = re.compile(r"\s*(?:(?:российск|китайск|американск|европейск)\w*\s+)?(руб|юан|долл|евро|коп)\w*\.?", re.I)
_DC_CUR_STEM = (("юан", "CNY"), ("долл", "USD"), ("евро", "EUR"), ("руб", "RUB"))


def _dc_cur_code(w):
    w = (w or "").lower()
    return next((c for st, c in _DC_CUR_STEM if w.startswith(st)), None)


def dc_amounts(s):
    """Денежные суммы строки [{v, cur, pos, end}]: число, за которым (после скобок со словами) следует руб/юан/долл/евро,
    либо скобка со словами «… рублей …». Числа с «%»/«процент» (ставки), копейки и номера периодов не считаются суммами."""
    s = s or ""
    out = []
    for m in _DC_AMT.finditer(s):
        tok = m.group(1)
        tail = s[m.end():m.end() + 400]
        if re.match(r"\s*%", tail):
            continue
        pm = re.match(r"\s*\(([^)]*)\)", tail)
        pw = pm.group(1) if pm else None
        rest_off = pm.end() if pm else 0
        if re.match(r"\s*процент", tail[rest_off:], re.I):
            continue
        cm = _DC_CUR_TAIL.match(tail, rest_off)
        if cm:
            if cm.group(1).lower() == "коп":
                continue
            cur = _dc_cur_code(cm.group(1))
            end_off = cm.end()
        elif pw and re.search(r"рубл|юан|доллар|евро", pw, re.I):
            cur = _dc_cur_code(re.search(r"рубл|юан|доллар|евро", pw, re.I).group(0))
            end_off = rest_off
        else:
            continue
        try:
            v = float(re.sub(r"[ \u00a0\u202f]", "", tok).replace(",", "."))
        except ValueError:
            continue
        if cur == "RUB" and not re.search(r"[.,]", tok):
            k = re.match(r"\s*\.?\s*(\d{1,2})\s*(?:\([^)]*\)\s*)?коп", tail[end_off:], re.I)
            if k:
                v += int(k.group(1)) / 100.0
        out.append({"v": v, "cur": cur, "pos": m.start(), "end": m.end() + end_off})
    return out


def _dc_ctx_kind(ctx):
    """Что описывает сумма по предшествующему тексту: 'coupon' / 'face' / None (последнее ключевое слово побеждает)."""
    sent = re.split(r"[.;\n]\s+(?=[А-ЯA-Z«\"])|\n", (ctx or "").strip())[-1].lower()   # начало последнего предложения важнее хвоста:
    head = sent[:70]                                                                       # «Размер части номинальной … купонного периода»
    if re.search(r"номинальн|погашен|амортиз", head) and not re.search(r"купон\w*\s+доход|процент", head):
        return "face"
    lc = (ctx or "").lower()[-160:]
    ci = max(lc.rfind("купон"), lc.rfind("процент"), lc.rfind("доход"))
    fi = max(lc.rfind("номинальн"), lc.rfind("погашен"), lc.rfind("амортиз"))
    if fi > ci:
        return "face"
    return "coupon" if ci >= 0 else None


def _dc_pay_kinds(*texts):
    """Виды выплат из текста категории: (купон, часть номинала, погашение номинала)."""
    lc = " ".join(t or "" for t in texts).lower()
    has_c = bool(re.search(r"купон|процент|доход", lc))
    has_a = bool(re.search(r"част\w*\s+номинальн|частичн|амортиз", lc))
    has_r = bool(re.search(r"погашени", lc)) or (bool(re.search(r"номинальн", lc)) and not has_a)
    return has_c, has_a, has_r


_DC_NUMQ = re.compile(r"(?<![\w.,\-–])(\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?![\w\-]|[.,]\d)")


def dc_parse_qty(s):
    """Количество бумаг: «в количестве N», число перед «штук/облигаций/бумаг», иначе первое отдельное число
    (номера вида 002P-03, БО-03 не берутся). Целое или None."""
    s2 = re.sub(r"\([^)]*\)", " ", s or "")
    m = re.search(r"количеств\w*\s*[:\-–]?\s*(\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?![\w\-]|[.,]\d)", s2, re.I)
    if not m:
        for c in _DC_NUMQ.finditer(s2):
            if re.match(r"\s*(?:шт|штук|облигац|бумаг|ценн|биржев|ед\b)", s2[c.end():c.end() + 30], re.I):
                m = c
                break
    if not m:
        m = _DC_NUMQ.search(s2)
    if not m:
        return None
    return int(re.sub(r"[ \u00a0\u202f]", "", m.group(1)))


def _dc_qty(total, per_bond, qty, qty_tol=0.0051):
    """Производные поля и проверки: qty_derived, total_matches, qty_integer, qty_out. Допуск на округление копеек
    на бумагу: qty_tol * qty."""
    r = {"qty_derived": None, "qty_out": qty, "checks": {}}
    if total and per_bond:
        ratio = total / per_bond
        q_est = int(round(ratio))
        r["qty_derived"] = q_est
        r["checks"]["qty_integer"] = q_est > 0 and (
            abs(ratio - q_est) < 0.01
            or (abs(per_bond * q_est - total) <= max(1.0, qty_tol * q_est) and abs(ratio - q_est) < 0.25)
        )
    if qty is not None and total is not None and per_bond is not None:
        r["checks"]["total_matches"] = abs(per_bond * qty - total) <= max(1.0, 0.5 * per_bond, qty_tol * qty)
    if qty is None:
        r["qty_out"] = r["qty_derived"]
    return r


def _dc_isins(*texts):
    out = []
    for t in texts:
        for m in _DC_ISIN.finditer(t or ""):
            if m.group(0) not in out:
                out.append(m.group(0))
    return out


def _dc_int(v):
    return None if v is None else int(round(v))


def _dc_paid(secs, text):
    cat = _dc_pick(secs, r"категория выплат", "2.2") or ""
    per_v = _dc_pick(secs, r"отчетный|отчётный", "2.3") or ""
    tot_v = _dc_pick(secs, r"общий размер выплаченных", "2.4") or ""
    pb_v = _dc_pick(secs, r"в расчете на одну|в расчёте на одну", "2.5") or ""
    qty_v = _dc_pick(secs, r"общее количество", "2.6") or ""
    due_v = _dc_pick(secs, r"дата, в которую", "2.9") or ""
    pct_v = _dc_pick(secs, r"^\s*(?:объем|объём|доля)\b", "2.10") or ""
    has_c, has_a, has_r = _dc_pay_kinds(cat)
    if not (has_c or has_a or has_r):
        has_c, has_a, has_r = _dc_pay_kinds(pb_v)
    has_face = has_a or has_r
    kinds = (["coupon"] if has_c else []) + (["amortization"] if has_a else []) + (["redemption"] if has_r and not has_a else [])
    pay = "+".join(kinds) or "other"
    warn = []
    f = {"payment": pay, "coupon_no": _dc_coupon_no(per_v)}
    f["period_from"], f["period_to"] = _dc_period(per_v)
    ta, pa = dc_amounts(tot_v), dc_amounts(pb_v)
    cur = (ta or pa or [{"cur": "RUB"}])[0]["cur"]
    t_cur = [a for a in ta if a["cur"] == cur]
    f["currency"] = cur
    f["total"] = t_cur[0]["v"] if t_cur else (dc_parse_rub(tot_v) if not ta and re.fullmatch(r"[\s\d.,\u00a0\u202f]*", tot_v.split("(")[0]) else None)
    comp = {"coupon": None, "face": None}
    prev = 0
    for a in pa:
        ctx, prev = pb_v[prev:a["pos"]], a["end"]
        if a["cur"] != cur:
            continue
        k = _dc_ctx_kind(ctx)
        if not has_c:
            k = "face"
        elif not has_face:
            k = "coupon"
        elif k is None:
            k = "coupon" if comp["coupon"] is None else "face"
        if comp[k] is None:
            comp[k] = a["v"]
        elif has_face and has_c:                          # слот уже занят — вторая сумма относится к другой части выплаты
            other = "face" if k == "coupon" else "coupon"
            if comp[other] is None:
                comp[other] = a["v"]
    if not pa and pb_v:
        m = re.match(r"\s*[-–—]?\s*(\d[\d \u00a0\u202f]*(?:[.,]\d+)?)\s*(?:\(|$|\.|;)", pb_v)
        if m:
            comp["face" if (has_face and not has_c) else "coupon"] = dc_parse_number(m.group(1))
    f["coupon_per_bond"], f["face_per_bond"] = comp["coupon"], comp["face"]
    f["per_bond"] = comp["coupon"] if comp["coupon"] is not None else comp["face"]
    parts = [x for x in (comp["coupon"], comp["face"]) if x is not None]
    f["per_bond_total"] = round(sum(parts), 6) if parts else None
    f["per_bond_rub"] = next((a["v"] for a in pa if a["cur"] == "RUB"), None) if cur != "RUB" else None
    f["total_rub"] = next((a["v"] for a in ta if a["cur"] == "RUB"), None) if cur != "RUB" else None
    f["qty"] = dc_parse_qty(qty_v)
    f["rate"] = _dc_rate(tot_v, pb_v)
    f["due_date"] = _dc_due(due_v)
    f["paid_pct"] = dc_parse_number(pct_v)
    q = _dc_qty(f["total"], f["per_bond_total"], f["qty"])
    f.update(qty_derived=q["qty_derived"], qty_out=q["qty_out"], checks=q["checks"])
    ck = q["checks"]
    if cur != "RUB" and f["per_bond_rub"] and f["total_rub"] and f["qty"] and f["total"] and f["per_bond_total"]:
        # выплата частью бумаг в валюте, частью — в рублях: количества складываются
        n = f["total"] / f["per_bond_total"] + f["total_rub"] / f["per_bond_rub"]
        if abs(n - f["qty"]) <= 1.5:
            ck["total_matches"] = True
            ck["split_currency"] = True
    qv = f["qty"]
    if qv is not None and qv > 0:
        if ck.get("total_matches"):
            f["conf"] = 1.0
        else:
            f["conf"] = 0.8
            warn.append("суммы не сходятся" if "total_matches" in ck else "суммы не извлечены")
    elif qv is None and ck.get("qty_integer"):
        f["conf"] = 0.8
    else:
        f["conf"] = 0.4
        if qv is None:
            warn.append("количество не найдено")
    f["warn"] = warn
    return f


_DC_PER_BOND_CTX = re.compile(r"на\s+одну|на\s+1\s|одн(?:ой|у)\s+(?:биржев\w+\s+)?облигаци|по\s+одной|на\s+каждую", re.I)


def _dc_decl_amounts(tot_v, pb_v):
    """(общая сумма, сумма на облигацию) для объявленных доходов. Берутся рублёвые суммы (число + руб), а не первое число
    пункта (номер периода, ставка). Если оба значения лежат в одном пункте — делим по словам «на одну облигацию»."""
    def first(v):
        a = [x for x in dc_amounts(v) if x["cur"] == "RUB"]
        return a[0]["v"] if a else None
    t, p = first(tot_v), first(pb_v)
    if tot_v and (not pb_v or pb_v == tot_v or p is None) and _DC_PER_BOND_CTX.search(tot_v):
        t = p = None
        prev = 0
        for a in dc_amounts(tot_v):
            ctx, prev = tot_v[prev:a["pos"]], a["end"]
            if a["cur"] != "RUB":
                continue
            if _DC_PER_BOND_CTX.search(ctx):
                p = a["v"] if p is None else p
            elif t is None:
                t = a["v"]
    if t is None and p is None and not dc_amounts(tot_v) and not dc_amounts(pb_v):
        t, p = dc_parse_rub(tot_v) if re.match(r"\s*\d", tot_v or "") else None, dc_parse_rub(pb_v) if re.match(r"\s*\d", pb_v or "") else None
    return t, p


def _dc_declared(secs, text):
    per_v = _dc_pick(secs, r"отчетный|отчётный", "2.5") or ""
    tot_v = _dc_pick(secs, r"^\s*общий размер", "2.6") or ""
    pb_v = _dc_pick(secs, r"в расчете на одну|в расчёте на одну|по одной облигации", "2.7") or ""
    due_v = _dc_pick(secs, r"дата, в которую", "2.9") or ""
    low = re.sub(r"\s+", " ", text.lower())
    undet = bool(re.search(r"не\s+определен", text, re.I))
    f = {"coupon_no": _dc_coupon_no(per_v, text)}
    f["period_from"], f["period_to"] = _dc_period(per_v)
    tot_a, pb_a = _dc_decl_amounts(tot_v, pb_v)
    f["total"] = None if undet else tot_a
    f["per_bond"] = None if undet else pb_a
    f["rate"] = _dc_rate(tot_v, pb_v)
    f["due_date"] = _dc_due(due_v)
    fm = re.search(r"по следующей формуле:?\s*(.+?)\s*(?:,\s*где\b|\n|$)", text)
    f["formula"] = fm.group(1).strip() if fm else None
    f["base"], f["spread"] = None, None
    if fm:
        blk = next((v for v in secs.values() if "по следующей формуле" in v), text)
        bl = blk.lower()
        f["base"] = "refinancing" if "ставки рефинансирования" in bl else "key" if "ключевой ставки" in bl else None
        sm = re.search(r"([+\-–−])\s*(\d+(?:[.,]\d+)?)\s*%", f["formula"])
        if sm:
            f["spread"] = float(sm.group(2).replace(",", ".")) * (1 if sm.group(1) == "+" else -1)
    f["undetermined"] = undet
    pm = re.search(r"[^\n]*обязан\w*\s+приобрести[^\n]*", text, re.I)
    f["put_note"] = re.sub(r"^\d+\.\d+\.?\s*", "", pm.group(0).strip()) if pm else None
    q = _dc_qty(f["total"], f["per_bond"], None)
    f.update(qty_derived=q["qty_derived"], qty_out=q["qty_out"], checks=q["checks"])
    if q["checks"].get("qty_integer"):
        f["conf"] = 0.9
    elif undet and f["period_from"]:
        f["conf"] = 0.7
    else:
        f["conf"] = 0.4
    return f


def _dc_obl_kind(seg):
    """Вид обязательства по тексту одного пункта. Частичное погашение проверяется раньше купона: в нём часто написано
    «в дату окончания N-го купонного периода»."""
    lo = (seg or "").lower()
    if re.search(r"амортизац|частичн\w*\s+(досрочн\w*\s+)?погашени|погашени\w*\s+част|част\w*\s+номинальн", lo):
        return "amortization"
    if re.search(r"приобретени|оферт", lo):
        return "offer"
    if "погашени" in lo and "номинал" in lo:
        return "redemption"
    if "купон" in lo or "процент" in lo:
        return "coupon"
    if "погашени" in lo:
        return "redemption"
    return "other"


def _dc_obligations(ob_v):
    """Несколько обязательств в одном сообщении («– Выплата купона … в размере X; – Частичное погашение … в размере Y») ->
    [{obligation, amount}] в порядке текста. Пусто — пункт не делится на части с суммами."""
    parts = [p for p in re.split(r"(?:^|\n)\s*[–—-]\s+|;\s*\n", ob_v or "") if p and p.strip()]
    out = []
    for p in parts:
        am = dc_amounts(p)
        if not am:
            continue
        out.append({"obligation": _dc_obl_kind(p), "amount": am[0]["v"]})
    return out if len(out) > 1 else ([{"obligation": _dc_obl_kind(parts[0] if parts else ob_v), "amount": out[0]["amount"]}] if out else [])


def _dc_default(secs, text):
    ob_v = _dc_pick(secs, r"содержание обязательства", "2.2") or ""
    due_v = _dc_pick(secs, r"дата, в которую", "2.3") or ""
    st_v = _dc_pick(secs, r"сведения о неисполнении", "2.4") or ""
    rs_v = _dc_pick(secs, r"причина неисполнения", "2.5") or ""
    obligations = _dc_obligations(ob_v)
    ob = obligations[0]["obligation"] if obligations else _dc_obl_kind(ob_v)
    amount = None
    # суммы — только через dc_amounts (числа рядом с «руб»), иначе «15-й купонный период: 681 890 рублей» дало бы 15
    m = re.search(r"общий размер[^:\n]*:\s*(.{0,200})", ob_v, re.I | re.S)
    if m:
        am = dc_amounts(m.group(1))
        amount = am[0]["v"] if am else None
    if amount is None:
        m = re.search(r"в размере\s+(.{0,160})", ob_v, re.I | re.S)
        am = dc_amounts(m.group(1)) if m else []
        amount = am[0]["v"] if am else None
    if amount is None:
        m = _DC_RUB_AMT.search(ob_v)
        amount = dc_parse_rub(ob_v[m.start():]) if m else None
    per_bond = None
    m = re.search(r"в расчете на одну[^:\n]*:([^\n]*)", ob_v, re.I)
    if m:
        mm = _DC_RUB_AMT.search(m.group(1))
        per_bond = dc_parse_rub(m.group(1)[mm.start():]) if mm else None
    qty = None
    m = re.search(r"общее количество[^:\n]*:\s*([^\n]*)", ob_v, re.I)
    if m:
        qty = dc_parse_qty(m.group(1))
    sl = st_v.lower()
    status = "default" if ("дефолт" in sl and "технический дефолт" not in sl) else "technical"
    if "технический дефолт" in text.lower():
        status = "technical"
    if len(obligations) > 1:
        amount = obligations[0]["amount"]
    f = {"obligation": ob, "obligations": obligations, "coupon_no": _dc_coupon_no(ob_v), "amount": amount, "per_bond": per_bond, "qty": qty,
         "rate": _dc_rate(ob_v), "due_date": _dc_due(due_v), "status": status, "reason": re.sub(r"\s+", " ", rs_v).strip()[:300]}
    q = _dc_qty(amount, per_bond, qty)
    f.update(qty_derived=q["qty_derived"], qty_out=q["qty_out"], checks=q["checks"])
    f["conf"] = 0.95 if amount is not None and due_v else 0.5
    return f


def _dc_bdays(a, b):
    """Рабочие дни (пн–пт, без праздников) между датами YYYY-MM-DD: (a, b]."""
    import datetime as _d
    x, y = _d.date.fromisoformat(a), _d.date.fromisoformat(b)
    n = 0
    while x < y:
        x += _d.timedelta(days=1)
        n += x.weekday() < 5
    return n


def _dc_default_age(f, ref_date):
    """Без явного слова «дефолт»: просрочка больше 10 рабочих дней от даты платежа — уже дефолт (ст. 17.1 39-ФЗ)."""
    f["overdue_bdays"] = None
    if f.get("due_date") and ref_date:
        f["overdue_bdays"] = _dc_bdays(f["due_date"], ref_date)
        if f["status"] == "technical" and f["overdue_bdays"] > 10:
            f["status"] = "default"


def _dc_buyback(secs, text, event_date):
    sec2 = " ".join(v for k, v in secs.items() if k.startswith("2."))
    body = sec2 or ((secs.get("2.1") or "") + " " + (secs.get("2.2") or ""))
    qty_v = _dc_pick(secs, r"количество\s+(?:фактически\s+)?(?:приобрет|выкуп)|фактически\s+(?:приобрет|выкуп)", None)
    qty = dc_parse_qty(qty_v) if qty_v else None
    if qty is None:
        m = re.search(r"(?:в\s+количестве|приобретено|выкуплено)\s*[:\-–]?\s*(\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)", body, re.I)
        qty = _dc_int(dc_parse_number(m.group(1))) if m else None
    if qty is None:
        for k, v in secs.items():
            if k.startswith("2.") and re.search(r"приобрет|выкуп", v, re.I):
                cand = dc_parse_qty(v)
                if cand:
                    qty = cand
                    break
    lb = body.lower()
    basis = ("put" if ("по требованию владельцев" in lb or "требованию их владельцев" in lb or "оферт" in lb)
             else "issuer" if ("по соглашению с владельцами" in lb or "по усмотрению" in lb) else None)
    d3 = dc_parse_date(_dc_pick(secs, r"дата\s+(?:приобретения|выкупа|наступления\s+события|исполнения)", "2.3") or "")
    return {"qty_bought": qty, "basis": basis, "date": event_date or d3, "conf": 1.0 if qty else 0.5, "checks": {}}


def _dc_placement(secs, text, title, event_date):
    sec2 = " ".join(v for k, v in secs.items() if k.startswith("2."))
    body = sec2 or text or ""
    low = ((title or "") + " " + body[:1200]).lower()
    if "реализации приобрет" in low or "продаже ранее приобрет" in low or "вторичной продаже" in low:
        subkind = "secondary"
    elif "дополнительн" in low or "доразмещ" in low:
        subkind = "additional"
    else:
        subkind = "primary"
    qty_v = _dc_pick(secs, r"количество\s+(?:фактически\s+)?(?:размещ|реализован|продан)|фактически\s+(?:размещ|реализован)", None)
    qty = dc_parse_qty(qty_v) if qty_v else None
    if qty is None:
        m = re.search(r"(?:размещено|реализовано|продано|в\s+количестве)\s*[:\-–]?\s*(\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)", body, re.I)
        qty = _dc_int(dc_parse_number(m.group(1))) if m else None
    d3 = dc_parse_date(_dc_pick(secs, r"дата\s+(?:фактического\s+)?(?:окончания|завершения|реализации|размещения|наступления)", "2.3") or "")
    return {"qty_placed": qty, "subkind": subkind, "date": d3 or event_date, "conf": 1.0 if qty else 0.5, "checks": {}}


def dc_extract(text, title="", meta=None):
    """Главная точка входа: классификация, реквизиты эмитента и факты по каждому ISIN."""
    meta = meta or {}
    title = title or meta.get("title", "")
    text = text or ""
    # «15, 47 руб.» — опечатка с пробелом после запятой: склеиваем, иначе сумма прочиталась бы как 47
    text = re.sub(r"(\d),[ \u00a0](\d{2})(?=\s*(?:руб|коп|\())", r"\1,\2", text)
    kind = dc_classify(title, text)
    secs = dc_sections(text)
    warnings = []
    m = re.search(r"(?<!\d)(\d{12}|\d{10})(?!\d)", secs.get("1.4", ""))
    if not m:
        m = re.search(r"ИНН[^\d]{0,80}(?<!\d)(\d{12}|\d{10})(?!\d)", text)
    inn = m.group(1) if m else None
    m = re.search(r"(?<!\d)(\d{15}|\d{13})(?!\d)", secs.get("1.3", ""))
    if not m:
        m = re.search(r"ОГРН[^\d]{0,80}(?<!\d)(\d{15}|\d{13})(?!\d)", text)
    ogrn = m.group(1) if m else None
    event_date = dc_parse_date(secs.get("1.7", ""))
    res = {"kind": kind, "inn": inn, "ogrn": ogrn, "event_date": event_date, "published": meta.get("published"),
           "code": meta.get("code"), "company": meta.get("company"), "facts": [], "warnings": warnings}
    if kind in ("buyback_result", "placement_result"):
        isins = _dc_isins(secs.get("2.1"), secs.get("2.2"), secs.get("2.3"))
    elif kind == "other":
        isins = _dc_isins(secs.get("2.4"), secs.get("2.1"))
    else:
        isins = _dc_isins(secs.get("2.1"))
    if not isins and kind != "other":
        isins = _dc_isins(text)
        if isins:
            warnings.append("ISIN найден вне пункта идентификации")
    if kind == "other":
        res["facts"] = [{"isin": i, "kind": kind, "conf": 0.0, "checks": {}} for i in isins]
        return res
    if not isins:
        warnings.append("ISIN не найден")
        return res
    if len(isins) > 1:
        warnings.append("несколько ISIN (%d): значения не разделены по блокам" % len(isins))
    if kind == "coupon_paid":
        f = _dc_paid(secs, text)
    elif kind == "coupon_declared":
        f = _dc_declared(secs, text)
    elif kind == "default":
        f = _dc_default(secs, text)
        _dc_default_age(f, event_date or dc_parse_date(meta.get("published") or ""))
    elif kind == "placement_result":
        f = _dc_placement(secs, text, title, event_date)
    else:
        f = _dc_buyback(secs, text, event_date)
    for w in f.get("warn") or []:
        warnings.append(w)
    if kind == "coupon_paid" and f["paid_pct"] is not None and f["paid_pct"] < 100:
        warnings.append("выплачено не полностью: %s%%" % f["paid_pct"])
    for i in isins:
        d = dict(f)
        d.pop("warn", None)
        d["checks"] = dict(f["checks"])
        d["isin"], d["kind"] = i, kind
        res["facts"].append(d)
    return res
