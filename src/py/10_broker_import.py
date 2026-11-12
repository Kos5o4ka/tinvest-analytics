# ═══════════════════════════════ импорт отчётов брокеров ═══════════════════════════════

ROLES = {
    "date": ["дата и время сделки", "дата заключения", "дата сделки", "дата операции", "дата исполнения", "дата и время",
             "дата/время", "дата", "date", "trade date", "time", "время", "дата расчетов", "дата расчётов"],
    "type": ["тип операции", "вид операции", "тип сделки", "вид сделки", "операция", "направление", "покупка/продажа",
             "тип", "вид", "type", "side", "operation", "action"],
    "isin": ["isin", "код isin", "isin код", "isin ценной бумаги"],
    "ticker": ["тикер", "ticker", "symbol", "код инструмента", "код финансового инструмента", "код бумаги", "код ценной бумаги",
               "код актива"],
    "name": ["наименование ценной бумаги", "наименование инструмента", "наименование", "название", "инструмент",
             "ценная бумага", "бумага", "актив", "эмитент", "name", "instrument", "security", "описание", "комментарий",
             "назначение платежа", "содержание операции"],
    "qty": ["количество", "кол-во", "кол во", "qty", "quantity", "количество, шт", "шт"],
    "price": ["цена сделки", "цена за единицу", "цена", "price", "курс"],
    "amount": ["сумма сделки", "сумма операции", "сумма зачисления/списания", "сумма", "объем сделки", "объём сделки",
               "объем", "объём", "amount", "total", "итого", "стоимость", "сумма, руб", "сумма в валюте"],
    "currency": ["валюта расчетов", "валюта расчётов", "валюта сделки", "валюта цены", "валюта платежа", "валюта", "currency"],
    "commission": ["комиссия брокера", "комиссия", "commission", "fee", "комиссия торговой системы"],
    "nkd": ["нкд", "накопленный купонный доход", "accrued interest", "accrued"],
}
ROLE_RU = {"date": "Дата", "type": "Тип операции", "isin": "ISIN", "ticker": "Тикер", "name": "Название / описание",
           "qty": "Количество", "price": "Цена", "amount": "Сумма", "currency": "Валюта", "commission": "Комиссия",
           "nkd": "НКД"}


def norm_head(s):
    s = str(s or "").lower().replace("ё", "е").replace("\n", " ").replace("\xa0", " ")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^\w/, -]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" ,")


def guess_mapping(header):
    heads = [norm_head(h) for h in header]
    cand = []
    for role, syns in ROLES.items():
        for si, syn in enumerate(syns):
            syn = norm_head(syn)
            for ci, h in enumerate(heads):
                if not h:
                    continue
                if h == syn:
                    score = 0
                elif h.startswith(syn):
                    score = 1
                elif re.search(r"\b" + re.escape(syn) + r"\b", h):
                    score = 2
                else:
                    continue
                cand.append((score, si, role, ci))
    cand.sort()
    mapping, used = {}, set()
    for score, si, role, ci in cand:
        if role in mapping or ci in used:
            continue
        mapping[role] = ci
        used.add(ci)
    return mapping


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell, self.in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.in_cell, self.cell = True, []
            span = dict(attrs).get("colspan")
            self._span = int(span) if span and str(span).isdigit() else 1
        elif tag == "br" and self.in_cell:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None and self.in_cell:
            txt = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            self.row.append(txt)
            for _ in range(getattr(self, "_span", 1) - 1):
                self.row.append("")
            self.in_cell = False
        elif tag == "tr" and self.row is not None and self.tables:
            if any(self.row):
                self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def _xlsx_tables(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("a:si", ns):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["a"])))
    tables = []
    for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)):
        rows = []
        for row in ET.fromstring(z.read(name)).iter("{%s}row" % ns["a"]):
            vals = {}
            for c in row.findall("a:c", ns):
                ref = c.get("r") or ""
                col = 0
                for ch in re.sub(r"\d", "", ref):
                    col = col * 26 + ord(ch.upper()) - 64
                t = c.get("t")
                v = c.find("a:v", ns)
                if t == "s" and v is not None:
                    val = shared[int(v.text)] if v.text and int(v.text) < len(shared) else ""
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["a"]))
                else:
                    val = v.text if v is not None and v.text is not None else ""
                    s_attr = c.get("s")
                    if val and s_attr is not None and re.fullmatch(r"\d{5}(\.\d+)?", val) and 30000 < float(val) < 80000:
                        val = "@xl" + val  # вероятно, дата в формате Excel — уточним при разборе
                vals[max(col, 1) - 1] = val
            if vals:
                rows.append([vals.get(i, "") for i in range(max(vals) + 1)])
        tables.append(rows)
    return tables


def read_tables(filename, raw):
    fn = (filename or "").lower()
    if fn.endswith((".xlsx", ".xlsm")) or raw[:2] == b"PK":
        return _xlsx_tables(raw)
    text = None
    for enc in ("utf-8-sig", "cp1251", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", "replace")
    if fn.endswith((".html", ".htm", ".xls")) or re.search(r"<\s*table", text[:200000], re.I):
        p = _TableParser()
        p.feed(text)
        return [t for t in p.tables if len(t) > 1]
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = max(";,\t", key=sample.count)
    return [[r for r in csv.reader(io.StringIO(text), delimiter=delim)]]


def find_header(tables):
    best = None
    for ti, t in enumerate(tables):
        for ri, row in enumerate(t[:60]):
            m = guess_mapping(row)
            score = len(m) + (3 if "date" in m else 0) + (2 if ("amount" in m or "qty" in m) else 0)
            if len(m) >= 3 and "date" in m and (best is None or score > best[0]):
                best = (score, ti, ri, m)
    return best


def parse_num(s):
    if s is None:
        return None
    s = str(s).strip().replace("\xa0", "").replace(" ", "").replace("−", "-").replace("–", "-")
    if not s or s in ("-", "—"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = re.sub(r"[^\d,.\-eE+]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(s):
    s = str(s or "").strip()
    if s.startswith("@xl"):
        try:
            return datetime(1899, 12, 30) + timedelta(days=float(s[3:]))
        except ValueError:
            return None
    fmts = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%d.%m.%y")
    for cand in (s, s[:19], s[:16], s[:10], s[:8]):
        cand = cand.strip().replace("Z", "")
        for fmt in fmts:
            try:
                return datetime.strptime(cand, fmt)
            except ValueError:
                continue
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s) or re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        a, b, c = m.groups()
        try:
            return datetime(int(c), int(b), int(a)) if len(a) == 2 else datetime(int(a), int(b), int(c))
        except ValueError:
            return None
    return None


_TAX_W = ("ндфл", "налог", "tax")
TYPE_WORDS = [
    # налоги — первыми: «удержание НДФЛ с дивидендов» не должно стать дивидендом, «налог с купона» — купоном
    (("ндфл с дивиденд", "налог с дивиденд", "налог на дивиденд", "удержан налог с дивиденд", "dividend tax", "tax on dividend"), "DIVIDEND_TAX"),
    (("ндфл с купон", "налог с купон", "налог на купон", "ндфл по купон", "налог по купон", "ндфл с процент", "coupon tax", "tax on coupon"), "BOND_TAX"),
    (_TAX_W, "TAX"),
    (("амортиз",), "BOND_REPAYMENT"), (("погашен", "redemption"), "BOND_REPAYMENT_FULL"),
    (("купон", "coupon"), "COUPON"), (("дивиденд", "dividend"), "DIVIDEND"),
    (("маржин", "перенос позиц", "плеч", "заем", "займ"), "MARGIN_FEE"),
    (("обслуж", "тариф", "депозитар"), "SERVICE_FEE"), (("комисс", "commission", "fee"), "BROKER_FEE"),
    (("покуп", "buy", "купля"), "BUY"), (("продаж", "sell"), "SELL"),
    (("пополн", "зачислен", "ввод денеж", "внесен", "deposit", "поступлен"), "INPUT"),
    (("вывод", "списан", "withdraw", "возврат денеж"), "OUTPUT"),
]
CUR_WORDS = {"rub": ("rub", "rur", "руб", "₽"), "usd": ("usd", "доллар", "$"), "eur": ("eur", "евро", "€"),
             "cny": ("cny", "юан", "¥"), "hkd": ("hkd",), "kzt": ("kzt", "тенге"), "gbp": ("gbp",), "chf": ("chf",)}
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def detect_type(text, qty, amount):
    t = (text or "").lower()
    for words, kind in TYPE_WORDS:
        if any(w in t for w in words):
            return kind
    if qty:
        return "BUY" if (amount or 0) < 0 else "SELL" if (amount or 0) > 0 else "BUY"
    if amount:
        return "INPUT" if amount > 0 else "OUTPUT"
    return None


def norm_cur(s):
    t = (s or "").lower()
    for c, words in CUR_WORDS.items():
        if any(w in t for w in words):
            return c
    return "rub"


SIGN = {"BUY": -1, "SELL": 1, "COUPON": 1, "DIVIDEND": 1, "BOND_REPAYMENT": 1, "BOND_REPAYMENT_FULL": 1, "TAX": -1,
        "DIVIDEND_TAX": -1, "BOND_TAX": -1,
        "BROKER_FEE": -1, "SERVICE_FEE": -1, "MARGIN_FEE": -1, "INPUT": 1, "OUTPUT": -1}


def rows_to_ops(rows, mapping, header=None):
    extra_comm = [i for i, h in enumerate(header or []) if "комисс" in norm_head(h) and i != mapping.get("commission")]
    def cell(row, role):
        i = mapping.get(role)
        return row[i] if i is not None and i < len(row) else ""

    ops, skipped = [], 0
    for row in rows:
        dt = parse_date(cell(row, "date"))
        if not dt:
            skipped += 1
            continue
        qty = parse_num(cell(row, "qty"))
        price = parse_num(cell(row, "price"))
        amount = parse_num(cell(row, "amount"))
        comm = parse_num(cell(row, "commission"))
        for ci in extra_comm:
            v = parse_num(row[ci]) if ci < len(row) else None
            if v:
                comm = (comm or 0.0) + abs(v)
        nkd = parse_num(cell(row, "nkd")) or 0.0
        isin = (cell(row, "isin") or "").strip().upper()
        ticker = (cell(row, "ticker") or "").strip().upper()
        name = (cell(row, "name") or "").strip()
        if not isin:
            for v in (ticker, name.upper()):
                if ISIN_RE.match(v):
                    isin = v
        if not isin:
            m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b", (name + " " + cell(row, "type")).upper())
            if m and m.group(1)[:2] in ("RU", "US", "XS", "KZ", "DE", "GB", "IE", "LU", "NL", "CH", "CN", "HK", "JE", "CY", "KY", "VG", "BM"):
                isin = m.group(1)
        kind = detect_type(cell(row, "type") + " " + ("" if mapping.get("type") is not None else name), qty, amount)
        if not kind:
            skipped += 1
            continue
        if kind in ("BUY", "SELL") and not qty:
            skipped += 1
            continue
        if amount is None and qty and price is not None:
            amount = abs(qty) * price
        if amount is not None and nkd and kind in ("BUY", "SELL"):
            amount = abs(amount) + abs(nkd)  # в отчётах НКД обычно указан отдельно от суммы сделки
        if not amount and kind not in ("BUY", "SELL"):
            skipped += 1
            continue
        amount = abs(amount or 0.0) * SIGN.get(kind, 1)
        cur = norm_cur(cell(row, "currency"))
        ident = isin or ticker or (name if kind in ("BUY", "SELL", "COUPON", "DIVIDEND", "BOND_REPAYMENT", "BOND_REPAYMENT_FULL", "DIVIDEND_TAX", "BOND_TAX") else "")
        o = {"id": "imp-" + uuid.uuid4().hex[:12], "date": dt.strftime("%Y-%m-%dT%H:%M:%SZ"), "type": "OPERATION_TYPE_" + kind,
             "payment": to_money(round(amount, 9), cur), "name": name or ticker or isin, "_ident": ident}
        if qty:
            o["quantity"] = o["quantityDone"] = str(int(abs(qty)))
        if price is not None:
            o["price"] = to_money(abs(price), cur)
        ops.append(o)
        if comm:
            ops.append({"id": "imp-" + uuid.uuid4().hex[:12], "date": o["date"], "type": "OPERATION_TYPE_BROKER_FEE",
                        "payment": to_money(-abs(comm), cur), "name": "Комиссия: " + (o["name"] or ""), "_ident": ident})
    ops.sort(key=lambda o: o["date"])
    return ops, skipped


def resolve_idents(client, idents):
    st = store()
    out = {}

    def one(ident):
        v = st.get("find:" + ident, ttl=30 * DAY)
        if v is not None:
            return ident, v
        v = {}
        if client.ready:
            try:
                found = client.find(ident)
            except ApiError:
                return ident, None
            pref = ("TQBR", "TQCB", "TQOB", "TQTF", "TQIR", "TQPI", "TQOD", "SPBXM", "SPBRU", "CETS")
            best = None
            for i in found:
                ok = (ident == (i.get("isin") or "").upper()) or (ident == (i.get("ticker") or "").upper()) or \
                     (ident.lower() == (i.get("name") or "").lower())
                if not ok:
                    continue
                rank = pref.index(i.get("classCode")) if i.get("classCode") in pref else 99
                if best is None or rank < best[0]:
                    best = (rank, i)
            if best:
                i = best[1]
                v = {"uid": i.get("uid"), "figi": i.get("figi"), "name": i.get("name"), "kind": i.get("instrumentKind") or "",
                     "type": i.get("instrumentType") or ""}
            st.put("find:" + ident, v)
        return ident, v

    for ident, v in pool_map(one, sorted(set(i for i in idents if i)), workers=4):
        out[ident] = v or {}
    return out


def finalize_import(client, ops, keep_demo=False):
    if not keep_demo:
        demo_remove()  # настоящий отчёт заменяет демо-портфель
    ids = resolve_idents(client, [o.get("_ident") for o in ops])
    for o in ops:
        ident = o.pop("_ident", "")
        r = ids.get(ident) or {}
        if r.get("uid"):
            o["instrumentUid"], o["figi"] = r["uid"], r.get("figi") or ""
            if r.get("kind"):
                o["instrumentKind"] = r["kind"]
            elif r.get("type"):
                o["instrumentKind"] = "INSTRUMENT_TYPE_" + r["type"].upper()
            if classify(o["type"]) in ("buy", "sell", "coupons", "dividends", "repayments") and r.get("name"):
                o["name"] = r["name"]
        elif ident and classify(o["type"]) in ("buy", "sell", "repayments", "coupons", "dividends"):
            o["instrumentUid"] = "imp:" + ident
    # если в отчёте нет пополнений — досоздаём их, чтобы деньги на счёте не уходили в минус
    if not any(classify(o["type"]) == "deposits" for o in ops):
        cash, extra = defaultdict(float), []
        for o in ops:
            c = cur_of(o["payment"])
            cash[c] += qf(o["payment"])
            if cash[c] < -0.005:
                need = -cash[c]
                extra.append({"id": "imp-" + uuid.uuid4().hex[:12], "date": o["date"], "type": "OPERATION_TYPE_INPUT",
                              "payment": to_money(round(need, 2), c), "name": "Пополнение (досчитано по сделкам)", "_synthetic": True})
                cash[c] += need
        ops = sorted(ops + extra, key=lambda o: (o["date"], 0 if o.get("_synthetic") else 1))
    fifo(ops)
    for o in ops:
        if "_yield" in o:
            o["yield"] = to_money(round(o.pop("_yield"), 9), cur_of(o["payment"]))
    return ops, ids


def import_preview(filename, raw):
    tables = read_tables(filename, raw)
    hit = find_header(tables)
    if not hit:
        raise ApiError("Не нашёл таблицу с операциями: нужна строка заголовков с датой и суммой или количеством.", 400)
    _, ti, ri, mapping = hit
    t = tables[ti]
    header = t[ri]
    body = [r for r in t[ri + 1:] if any(str(c).strip() for c in r)]
    return {"table": ti, "header_row": ri, "header": header, "mapping": mapping, "rows": len(body),
            "sample": body[:12], "tables": len(tables)}


def import_ops(filename, raw, table, header_row, mapping):
    tables = read_tables(filename, raw)
    if table >= len(tables):
        raise ApiError("Таблица не найдена.", 400)
    body = [r for r in tables[table][header_row + 1:] if any(str(c).strip() for c in r)]
    return rows_to_ops(body, {k: int(v) for k, v in mapping.items() if v is not None and str(v) != ""}, tables[table][header_row])


TEMPLATE_CSV = ("Дата;Тип операции;ISIN;Тикер;Название;Количество;Цена;Сумма;Валюта;Комиссия;НКД\n"
                "15.01.2025;Пополнение;;;;;;100000;RUB;;\n"
                "16.01.2025;Покупка;RU0009029540;SBER;Сбербанк;100;270,5;27050;RUB;8,12;\n"
                "20.02.2025;Покупка;RU000A10C6P6;;Авто Финанс Банк БО-001Р-15;10;100,2;10050;RUB;3,01;30\n"
                "15.03.2025;Купон;RU000A10C6P6;;Авто Финанс Банк БО-001Р-15;;;210,5;RUB;;\n"
                "20.07.2025;Дивиденд;RU0009029540;SBER;Сбербанк;;;3480;RUB;;\n"
                "01.08.2025;Продажа;RU0009029540;SBER;Сбербанк;50;310;15500;RUB;4,65;\n"
                "31.12.2025;НДФЛ;;;;;;520;RUB;;\n")


