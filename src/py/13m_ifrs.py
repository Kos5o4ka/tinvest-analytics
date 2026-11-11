# ═══════════════════════════════ эмитенты: отчётность группы по МСФО ═══════════════════════════════
# Источник — публичные страницы фундаментальных показателей smart-lab.ru (/q/{ТИКЕР}/f/y/MSFO/, robots.txt разрешает /q/).
# Наружу уходит только тикер акции. Данные агрегатора могут отличаться от официальной отчётности.
# Суммы на сайте — в млрд ₽, в ответах API хранятся в млн ₽ (как РСБУ в 13h).
#
# Как эмитент облигации сопоставляется с тикером (ifrs_ticker_for):
#   1) «сама компания»: у эмитента на Мосбирже есть торгуемая акция (ISS /emitters/{id}/securities);
#   2) «входит в группу»: таблица IFRS_BY_INN (ИНН эмитента -> тикер материнской компании) — для SPV и «дочек»;
#   3) то же по названию эмитента, IFRS_BY_NAME (регулярка по названию) — когда ИНН не проверен.
# Чтобы добавить компанию: найдите ИНН выпускающей структуры (ISS: iss/securities.json?q=<название>, поле emitent_inn),
# проверьте, что у тикера есть страница https://smart-lab.ru/q/<ТИКЕР>/f/y/MSFO/ с данными в рублях, и добавьте строку в таблицу.
#
# Скоринг по МСФО (iss_score_ifrs) — показатели последнего периода (LTM, если он есть и новее года; иначе последний год):
#   покрытие процентов EBITDA/проценты  25 б.:  ≤ 2 — 0,   ≥ 6 — полный
#   чистый долг / EBITDA                25 б.:  ≥ 4,5 — 0, ≤ 1,5 — полный (чистые деньги — полный; EBITDA ≤ 0 при долге — 0)
#   капитал / активы                    15 б.:  ≤ 10 % — 0, ≥ 40 % — полный
#   рентабельность по EBITDA            10 б.:  ≤ 5 % — 0,  ≥ 25 % — полный
#   свободный денежный поток            10 б.:  ≥ 0 — полный, FCF = −50 % EBITDA и ниже — 0
#   рост выручки (год к году)           15 б.:  ≤ −15 % — 0, ≥ +5 % — полный
# Банки (отдельная схема, поля smart-lab другие): капитал/активы (≤ 6 % — 0, ≥ 12 % — полный, 20 б.), ROE (≤ 0 — 0, ≥ 15 % — 20 б.),
#   стоимость риска (≥ 3 % — 0, ≤ 1 % — 15 б.), доля неработающих кредитов (≥ 10 % — 0, ≤ 4 % — 15 б.), достаточность капитала
#   (≤ 10,5 % — 0, ≥ 14 % — 15 б.), рост чистых операционных доходов (≤ −15 % — 0, ≥ +5 % — 10 б.); что отсутствует — не считается.
# Итог = набранные баллы / максимум по доступным показателям × 100 (минимум 40 баллов максимума), затем штрафы:
#   убыток за год −8 (второй год подряд ещё −7), отрицательный капитал −15, последний годовой отчёт старше двух лет −10.

IFRS_BASE = "https://smart-lab.ru/q/%s/f/y/MSFO/"
IFRS_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml", "Accept-Language": "ru,en;q=0.8"}
IFRS_TTL, IFRS_NF_TTL, IFRS_ERR_TTL, IFRS_MAP_TTL = 7 * DAY, DAY, 3600, 30 * DAY
_ifrs_lock = threading.Lock()          # одна загрузка за раз: и ограничение частоты, и защита от дублей
_ifrs_last = [0.0]

# ИНН эмитента (SPV, «дочка») -> (тикер материнской компании, название группы). ИНН проверены по справочнику Мосбиржи.
IFRS_BY_INN = {
    "7726588547": ("GAZP", "Газпром"),          # Газпром капитал
    "7715630469": ("X5", "X5 Group"),            # ИКС 5 ФИНАНС
    "7705619586": ("ETLN", "Эталон"),            # Эталон-Финанс
    "7703255661": ("PIKK", "ПИК"),               # ПИК-Корпорация
    "1402046014": ("SELG", "Селигдар"),          # Золото Селигдара
    "7814148471": ("LENT", "Лента"),             # ООО «Лента»
    "7838347927": ("LSRG", "ЛСР"),               # ЛСР-Инвест
    "7710140679": ("T", "Т-Технологии"),         # АО «ТБанк»
}
# Название эмитента (регулярка, регистр не важен) -> (тикер, группа). Для случаев, когда ИНН не найден в справочнике.
IFRS_BY_NAME = [
    (r"икс\s*5|x5\b", "X5", "X5 Group"),
    (r"газпром\s+капитал|\bгпн\b", "GAZP", "Газпром"),
]


def _ifrs_num(s):
    """'11 674' -> 11674.0; '-364.0' -> -364.0; '31.4%' -> 0.314; '' / '—' / мусор -> None."""
    if s is None:
        return None
    t = re.sub(r"<[^>]+>", "", str(s)).replace("&nbsp;", " ").replace("−", "-")
    t = re.sub(r"[\s  ]+", "", t).replace(",", ".")
    if not t or t in ("-", "—", "–"):
        return None
    pct = t.endswith("%")
    if pct:
        t = t[:-1]
    try:
        v = float(t)
    except ValueError:
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v / 100.0 if pct else v


def ifrs_parse(html):
    """HTML страницы smart-lab -> {labels: ['2021', ..., 'LTM'], rows: {поле: [значения по меткам, строки для текста]}} или None."""
    if not html or "field=" not in html:
        return None
    m = re.search(r"<tr[^>]*class=\"[^\"]*header_row[^\"]*\"[^>]*>(.*?)</tr>", html, re.S)
    if not m:
        return None
    labels = [x.strip() for x in re.findall(r"<strong>\s*([^<]+?)\s*</strong>", m.group(1))]
    labels = [x for x in labels if re.fullmatch(r"\d{4}|LTM", x)]
    if not labels:
        return None
    rows, bad = {}, 0
    for fm in re.finditer(r"<tr[^>]*\bfield=\"([A-Za-z0-9_]+)\"[^>]*>(.*?)</tr>", html, re.S):
        cells = []
        for am, body in re.findall(r"<td([^>]*)>(.*?)</td>", fm.group(2), re.S):
            if "chartrow" in am or "ltm_spc" in am:
                continue
            cells.append(re.sub(r"<[^>]+>", "", body).replace("&nbsp;", " ").strip())
        if len(cells) != len(labels):
            bad += 1
            continue
        rows[fm.group(1)] = cells
    if not rows or bad > len(rows):
        return None
    return {"labels": labels, "rows": rows}


_IFRS_BANK_KEYS = ("bank_assets", "net_interest_income", "net_operating_income")


def _ifrs_val(rows, key, i, scale=1.0):
    r = rows.get(key)
    if not r or i >= len(r):
        return None
    v = _ifrs_num(r[i])
    return None if v is None else v * scale


def _ifrs_period(rows, i, bank, y):
    """Один столбец (год или LTM) -> словарь показателей; суммы в млн ₽, доли — числами (0.25 = 25 %)."""
    g = lambda k, sc=1.0: _ifrs_val(rows, k, i, sc)   # noqa: E731
    M = 1000.0                                           # млрд -> млн
    p = {"y": y}
    if bank:
        p.update(rev=g("net_operating_income", M), net=g("net_income", M), assets=g("bank_assets", M), equity=g("capital", M),
                 nii=g("net_interest_income", M), roe=g("roe"), cost_risk=g("cost_of_risk_ratio"), npl=g("share_of_non_performing_loans"),
                 car=g("total_capital_adequacy_ratio"), nim=g("net_intertest_margin") if "net_intertest_margin" in rows else g("net_interest_margin"),
                 cti=g("cost_to_income"), ltd=g("loan_to_deposit_ratio"))
        if p["equity"] is not None and p["assets"]:
            p["eq_ratio"] = p["equity"] / p["assets"]
        return p
    p.update(rev=g("revenue", M), op_income=g("operating_income", M), ebitda=g("ebitda", M), net=g("net_income", M), interest=g("interest_expenses", M),
             debt=g("debt", M), cash=g("cash", M), net_debt=g("net_debt", M), assets=g("assets", M), ocf=g("ocf", M), capex=g("capex", M),
             roe=g("roe"))
    eq = g("net_assets", M)
    p["equity"] = eq if eq is not None else g("book_value", M)
    if p["net_debt"] is None and p["debt"] is not None and p["cash"] is not None:
        p["net_debt"] = p["debt"] - p["cash"]
    if p["ocf"] is not None and p["capex"] is not None:
        p["fcf"] = p["ocf"] - abs(p["capex"])
    else:
        p["fcf"] = g("fcf", M)
    e, nd, it, rv = p["ebitda"], p["net_debt"], p["interest"], p["rev"]
    p["nd_ebitda"] = nd / e if (nd is not None and e is not None and e > 0) else None
    p["cover"] = e / it if (e is not None and it is not None and it > 0) else None
    p["margin_ebitda"] = e / rv if (e is not None and rv) else None
    p["net_margin"] = p["net"] / rv if (p["net"] is not None and rv) else None
    p["eq_ratio"] = p["equity"] / p["assets"] if (p["equity"] is not None and p["assets"]) else None
    return p


def ifrs_build(parsed, ticker):
    """Результат ifrs_parse -> структура ifrs_fin (без сети; для тестов)."""
    labels, rows = parsed["labels"], parsed["rows"]
    bank = any(k in rows for k in _IFRS_BANK_KEYS) and "revenue" not in rows
    ccy = rows.get("currency") or []
    last_ccy = next((c for c in reversed(ccy) if c), "RUB")
    out = {"status": "ok", "ticker": ticker, "bank": bank, "url": IFRS_BASE % ticker, "currency": last_ccy, "years": [], "ltm": None,
           "as_of": None, "fetched": time.time()}
    if last_ccy.upper() not in ("RUB", "RUR"):
        out.update(status="notrub", note="Отчётность группы в валюте %s — сравнить с рублёвыми показателями нельзя." % last_ccy)
        return out
    dates = rows.get("date") or []
    prev_y = None
    for i, lab in enumerate(labels):
        if lab == "LTM":
            p = _ifrs_period(rows, i, bank, "LTM")
            if any(p.get(k) is not None for k in ("rev", "ebitda", "net")):
                out["ltm"] = p
                out["as_of"] = dates[i] if i < len(dates) and dates[i] else None
            continue
        y = int(lab)
        p = _ifrs_period(rows, i, bank, y)
        if not any(p.get(k) is not None for k in ("rev", "ebitda", "net", "assets")):
            continue
        out["years"].append(p)
    for k, p in enumerate(out["years"]):
        pv = out["years"][k - 1] if k else None
        p["growth"] = None
        if pv and pv["y"] == p["y"] - 1 and p.get("rev") is not None and pv.get("rev") and pv["rev"] > 0:
            p["growth"] = p["rev"] / pv["rev"] - 1
    if out["years"] and not out["as_of"]:
        i = labels.index(str(out["years"][-1]["y"]))
        out["as_of"] = dates[i] if i < len(dates) and dates[i] else None
    if not out["years"]:
        out.update(status="nodata", note="На smart-lab нет данных МСФО по этому тикеру.")
    return out


def _ifrs_http(url):
    with _ifrs_lock:                                   # не чаще одного запроса в секунду на всё приложение
        wait = 1.0 - (time.time() - _ifrs_last[0])
        if wait > 0:
            time.sleep(wait)
        _ifrs_last[0] = time.time()
    if not _ext_ctx:
        _ext_ctx.append(make_ssl_context())
    req = urllib.request.Request(url, headers=IFRS_UA)
    with urllib.request.urlopen(req, timeout=20, context=_ext_ctx[0]) as r:
        return r.read().decode("utf-8", "replace")


_ifrs_fetch_lock = threading.Lock()


def ifrs_fin(ticker):
    """Тикер -> {status ok|nodata|notrub|parse|err, ticker, years, ltm, bank, url, as_of, ...}; кэш 7 дней (нет данных — сутки). Не бросает исключений."""
    ticker = (ticker or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,12}", ticker):
        return {"status": "nodata", "ticker": ticker, "years": [], "ltm": None, "bank": False, "url": None}
    key = "ifrs_fin_v1_" + ticker
    with _ifrs_fetch_lock:
        hit = store().get(key)
        if hit:
            age = time.time() - (hit.get("fetched") or 0)
            if age < (IFRS_TTL if hit.get("status") == "ok" else IFRS_ERR_TTL if hit.get("status") == "err" else IFRS_NF_TTL):
                return hit
        try:
            html = _ifrs_http(IFRS_BASE % ticker)
            parsed = ifrs_parse(html)
            if parsed is None:
                res = {"status": "parse", "ticker": ticker, "years": [], "ltm": None, "bank": False, "url": IFRS_BASE % ticker, "fetched": time.time(),
                       "note": "Страница smart-lab в неожиданном формате."}
            else:
                res = ifrs_build(parsed, ticker)
        except urllib.error.HTTPError as e:
            st = "nodata" if e.code == 404 else "err"
            res = {"status": st, "ticker": ticker, "years": [], "ltm": None, "bank": False, "url": IFRS_BASE % ticker, "fetched": time.time(),
                   "note": "На smart-lab нет страницы МСФО." if e.code == 404 else "smart-lab временно недоступен (HTTP %s)." % e.code}
        except Exception as e:  # noqa: BLE001
            res = {"status": "err", "ticker": ticker, "years": [], "ltm": None, "bank": False, "url": IFRS_BASE % ticker, "fetched": time.time(),
                   "note": "smart-lab недоступен: %s" % str(e)[:80]}
        try:
            store().put(key, res)
        except Exception:  # noqa: BLE001
            pass
        return res


# ── сопоставление эмитента с тикером ──

def _ifrs_emitter_shares(eid):
    """Список бумаг эмитента на Мосбирже, у которых есть акции: [{secid, type, traded}] (кэш 30 дней)."""
    key = "ifrs_emsec_v1_%s" % eid
    hit = store().get(key, ttl=IFRS_MAP_TTL)
    if hit is not None:
        return hit
    j = _iss_json("https://iss.moex.com/iss/emitters/%s/securities.json?iss.meta=off" % eid, 20)
    cols = j["securities"]["columns"]
    out = []
    for r in j["securities"]["data"]:
        d = dict(zip(cols, r))
        if d.get("TYPE") in ("common_share", "preferred_share") and d.get("SECID"):
            out.append({"secid": d["SECID"], "type": d["TYPE"], "traded": bool(d.get("IS_TRADED")), "board": d.get("PRIMARY_BOARDID")})
    store().put(key, out)
    return out


def ifrs_ticker_for(isin, em=None):
    """ISIN облигации -> {ticker, group, kind: 'own'|'group', how} или None, если листингового родителя не нашли."""
    try:
        em = em or issuer_of(isin)
        if not em:
            return None
        eid = em.get("emitter_id")
        if eid:
            sh = [s for s in _ifrs_emitter_shares(eid) if s["traded"]]
            sh.sort(key=lambda s: (s["type"] != "common_share", s["board"] != "TQBR"))
            if sh:
                t = sh[0]["secid"]
                return {"ticker": t, "group": em.get("short") or em.get("title"), "kind": "own",
                        "how": "эмитент — сама компания (акции %s на Мосбирже), показана отчётность группы по МСФО" % t}
        hit = IFRS_BY_INN.get(str(em.get("inn") or ""))
        if not hit:
            title = em.get("title") or ""
            for rx, t, g in IFRS_BY_NAME:
                if re.search(rx, title, re.I):
                    hit = (t, g)
                    break
        if hit:
            return {"ticker": hit[0], "group": hit[1], "kind": "group",
                    "how": "эмитент входит в группу «%s» (акции %s), показана консолидированная отчётность группы" % (hit[1], hit[0])}
    except Exception:  # noqa: BLE001
        return None
    return None


# ── скоринг ──

IFRS_FIN_RE = re.compile(r"лизинг|факторинг|микрофин|МФК|МКК|коллектор|ломбард", re.I)


def iss_score_ifrs(fin, is_fin=False):
    """Скоринг по МСФО (ifrs_fin). Форма результата как у iss_score_fin: {ok, score, key, label, year, parts, penalties, note, basis}.
    is_fin — лизинг, МФО и прочие небанковские финансовые компании: долг для них — «сырьё» бизнеса, поэтому вместо
    чистого долга/EBITDA, покрытия, маржи и FCF (отрицательный при росте портфеля — норма) смотрим
    долг/капитал (≥ 8 — 0, ≤ 3 — полный, 25 б.), капитал/активы (5 % — 0, 15 % — полный, 20 б.), ROE (0 — 0, ≥ 15 % — полный, 20 б.)."""
    if not fin or fin.get("status") != "ok" or not fin.get("years"):
        return {"ok": False, "reason": (fin or {}).get("note") or "Нет отчётности МСФО."}
    yrs = fin["years"]
    ltm = fin.get("ltm")
    c = ltm or yrs[-1]
    last = yrs[-1]
    prev = yrs[-2] if len(yrs) > 1 and yrs[-2]["y"] == last["y"] - 1 else None
    bank = bool(fin.get("bank"))
    parts = []

    def add(pid, name, w, t, value, text):
        if t is not None:
            parts.append({"id": pid, "name": name, "max": w, "pts": round(w * t, 1), "grade": _iss_grade(t), "value": value, "text": text})
    growth = last.get("growth")
    if bank:
        if c.get("eq_ratio") is not None:
            add("eq", "Капитал / активы", 20, _iss_t(c["eq_ratio"], 0.06, 0.12), c["eq_ratio"], "капитал — %s %% активов" % _iss_n(c["eq_ratio"] * 100, 1))
        roe = c.get("roe") if (c.get("equity") is None or c["equity"] > 0) else None
        if roe is None and c.get("net") is not None and c.get("equity") and c["equity"] > 0:
            roe = c["net"] / c["equity"]
        if roe is not None:
            add("roe", "Рентабельность капитала (ROE)", 20, _iss_t(roe, 0.0, 0.15), roe, "ROE %s %%" % _iss_n(roe * 100, 1))
        if c.get("cost_risk") is not None:
            add("crisk", "Стоимость риска", 15, _iss_t(c["cost_risk"], 0.03, 0.01), c["cost_risk"], "резервы съедают %s %% кредитов в год" % _iss_n(c["cost_risk"] * 100, 1))
        if c.get("npl") is not None:
            add("npl", "Неработающие кредиты", 15, _iss_t(c["npl"], 0.10, 0.04), c["npl"], "%s %% кредитов с просрочкой" % _iss_n(c["npl"] * 100, 1))
        if c.get("car") is not None:
            add("car", "Достаточность капитала", 15, _iss_t(c["car"], 0.105, 0.14), c["car"], "общая достаточность %s %%" % _iss_n(c["car"] * 100, 1))
        if growth is not None:
            add("growth", "Динамика доходов", 10, _iss_t(growth, -0.15, 0.05), growth, "чистые операционные доходы %s на %s %%" % ("выросли" if growth >= 0 else "упали", _iss_n(abs(growth) * 100, 0)))
    elif is_fin:
        debt, eq = c.get("debt"), c.get("equity")
        if debt is None and c.get("net_debt") is not None and c.get("cash") is not None:
            debt = c["net_debt"] + c["cash"]
        if debt is None:
            debt = c.get("net_debt")
        if eq is not None and eq <= 0:
            add("lev", "Долг / капитал", 25, 0.0, None, "капитал отрицательный")
        elif debt is not None and eq:
            de = debt / eq
            add("lev", "Долг / капитал", 25, _iss_t(de, 8, 3), de, "долг в %s раза больше капитала" % _iss_n(de, 1))
        if c.get("eq_ratio") is not None:
            add("eq", "Доля капитала", 20, _iss_t(c["eq_ratio"], 0.05, 0.15), c["eq_ratio"], "капитал — %s %% активов" % _iss_n(c["eq_ratio"] * 100, 0))
        roe = c.get("roe") if (eq is None or eq > 0) else None   # при отрицательном капитале ROE бессмысленна
        if roe is None and c.get("net") is not None and eq and eq > 0:
            roe = c["net"] / eq
        if roe is not None:
            add("roe", "Рентабельность капитала (ROE)", 20, _iss_t(roe, 0.0, 0.15), roe, "ROE %s %%" % _iss_n(roe * 100, 1))
        if growth is not None:
            add("growth", "Динамика выручки", 15, _iss_t(growth, -0.15, 0.05), growth, "выручка %s на %s %%" % ("выросла" if growth >= 0 else "упала", _iss_n(abs(growth) * 100, 0)))
    else:
        e, it, nd = c.get("ebitda"), c.get("interest"), c.get("net_debt")
        if it is not None and it > 0:
            if e is not None and e > 0:
                add("cover", "Покрытие процентов", 25, _iss_t(c["cover"], 2.0, 6.0), c["cover"], "EBITDA покрывает проценты в %s раза" % _iss_n(c["cover"], 1))
            elif e is not None:
                add("cover", "Покрытие процентов", 25, 0.0, None, "EBITDA не положительна, проценты платятся из других источников")
        elif c.get("debt") is not None and c.get("assets") and c["debt"] <= 0.02 * c["assets"]:
            add("cover", "Покрытие процентов", 25, 1.0, None, "заёмных средств практически нет")
        if nd is not None:
            if nd <= 0:
                add("lev", "Чистый долг / EBITDA", 25, 1.0, None, "денег больше, чем долга")
            elif e is None or e <= 0:
                add("lev", "Чистый долг / EBITDA", 25, 0.0, None, "есть чистый долг, а EBITDA не положительна")
            else:
                add("lev", "Чистый долг / EBITDA", 25, _iss_t(c["nd_ebitda"], 4.5, 1.5), c["nd_ebitda"], "чистый долг = %s годовой EBITDA" % _iss_n(c["nd_ebitda"], 1))
        if c.get("eq_ratio") is not None:
            add("eq", "Доля капитала", 15, _iss_t(c["eq_ratio"], 0.10, 0.40), c["eq_ratio"], "капитал — %s %% активов" % _iss_n(c["eq_ratio"] * 100, 0))
        if c.get("margin_ebitda") is not None:
            add("margin", "Рентабельность по EBITDA", 10, _iss_t(c["margin_ebitda"], 0.05, 0.25), c["margin_ebitda"], "EBITDA — %s %% выручки" % _iss_n(c["margin_ebitda"] * 100, 1))
        f = c.get("fcf")
        if f is not None:
            if f >= 0:
                add("fcf", "Свободный денежный поток", 10, 1.0, f, "положительный: операционный поток покрывает инвестиции")
            elif e is not None and e > 0:
                add("fcf", "Свободный денежный поток", 10, _iss_t(f / e, -0.5, 0.0), f, "отрицательный: %s %% от EBITDA" % _iss_n(abs(f) / e * 100, 0))
            else:
                add("fcf", "Свободный денежный поток", 10, 0.0, f, "отрицательный при слабой EBITDA")
        if growth is not None:
            add("growth", "Динамика выручки", 15, _iss_t(growth, -0.15, 0.05), growth, "выручка %s на %s %%" % ("выросла" if growth >= 0 else "упала", _iss_n(abs(growth) * 100, 0)))
    mx = sum(p["max"] for p in parts)
    if mx < 40:
        return {"ok": False, "reason": "Слишком мало показателей МСФО для оценки%s." % (" (банк: не хватает данных)" if bank else "")}
    base = sum(p["pts"] for p in parts) / mx * 100
    pen = []
    net = last.get("net")
    if net is not None and net < 0:
        pen.append({"name": "Убыток по итогам года", "pts": -8})
        if prev and prev.get("net") is not None and prev["net"] < 0:
            pen.append({"name": "Убыток второй год подряд", "pts": -7})
    if c.get("equity") is not None and c["equity"] < 0:
        pen.append({"name": "Отрицательный капитал", "pts": -15})
    if last["y"] < date.today().year - 2:
        pen.append({"name": "Отчётность старше двух лет (%d)" % last["y"], "pts": -10})
    sc = max(0, min(100, int(round(base + sum(p["pts"] for p in pen)))))
    k, t = _iss_label(sc)
    per = ("LTM на %s" % fin["as_of"]) if ltm and fin.get("as_of") else ("LTM" if ltm else "%d г." % last["y"])
    return {"ok": True, "score": sc, "key": k, "label": t, "year": last["y"], "period": per, "base": round(base, 1), "parts": parts, "penalties": pen,
            "n_years": len(yrs), "fin_mode": bool(is_fin and not bank), "holding": False, "bank": bank, "basis": "ifrs",
            "note": "Консолидированная отчётность группы (МСФО) по данным агрегатора smart-lab; может отличаться от официальной."}


def ifrs_bundle(isin, em=None):
    """Всё для интеграции: {ticker, how, group, kind, fin, score, url} или None, если МСФО-тикера нет."""
    mp = ifrs_ticker_for(isin, em)
    if not mp:
        return None
    fin = ifrs_fin(mp["ticker"])
    # для групп «финансовой» считаем только лизинг/МФО/факторинг: в названиях холдингов («АФК Система») слово «финансовая» не про бизнес
    nm = (em or {}).get("title") or mp.get("group") or ""
    sc = iss_score_ifrs(fin, bool(IFRS_FIN_RE.search(nm)))
    return {"ticker": mp["ticker"], "how": mp["how"], "group": mp["group"], "kind": mp["kind"], "fin": fin, "score": sc, "url": fin.get("url") or IFRS_BASE % mp["ticker"]}
