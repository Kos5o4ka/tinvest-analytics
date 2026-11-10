# ═══════════════════════════════ счета и сводка ═══════════════════════════════

_mem, _mem_lock = {}, threading.Lock()


def mem_get(key, ttl):
    with _mem_lock:
        hit = _mem.get(key)
    return hit[1] if hit and time.time() - hit[0] < ttl else None


def mem_put(key, val):
    with _mem_lock:
        _mem[key] = (time.time(), val)
    return val


def mem_clear():
    with _mem_lock:
        _mem.clear()


def imports_list():
    return store().get("imports") or []


def fetch_operations(client, cfg, acc, opened=None, full=False):
    """Инкрементальная загрузка: первый раз — вся история, дальше — только последние ~10 дней."""
    st = store()
    key = token_key(cfg) + ":" + acc
    meta = None if full else st.get("sync:" + key)
    now = datetime.now(timezone.utc)
    if full:
        st.ops_clear(key)
    if meta:
        frm = (datetime.strptime(meta[:19], "%Y-%m-%dT%H:%M:%S") - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        frm = (opened or "2006-01-01T00:00:00Z")[:19] + "Z"
    items = client.operations(acc, frm, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    st.ops_put(key, items)
    st.put("sync:" + key, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return st.ops(key)


def account_data(cfg, a, force=False):
    """(портфель как список строк позиций + итоги, операции, маржа) для одного счёта, с кэшем 90 с."""
    key = ("acc", token_key(cfg), a["id"])
    hit = None if force else mem_get(key, 90)
    if hit:
        return hit
    client = TInvest(cfg)
    if a["kind"] == "import":
        ops = store().ops(a["id"])
        res = {"port": None, "ops": ops, "margin": None}
    else:
        with ThreadPoolExecutor(max_workers=3) as ex:
            fp = ex.submit(client.portfolio, a["id"])
            fo = ex.submit(fetch_operations, client, cfg, a["id"], a.get("opened"))
            fm = ex.submit(client.margin, a["id"])
            res = {"port": fp.result(), "ops": fo.result(), "margin": fm.result()}
    for o in res["ops"]:
        o["_acc"], o["_accname"] = a["id"], a["name"]
    return mem_put(key, res)


def list_accounts(cfg, force=False):
    key = ("accounts", token_key(cfg))
    hit = None if force else mem_get(key, 60)
    if hit:
        return hit
    client = TInvest(cfg)
    accs = []
    if client.ready:
        for x in client.accounts():
            accs.append({"id": x["id"], "name": x.get("name") or x["id"], "kind": "tinvest",
                         "type": {"ACCOUNT_TYPE_TINKOFF_IIS": "ИИС", "ACCOUNT_TYPE_INVEST_BOX": "Копилка"}.get(x.get("type"), ""),
                         "closed": x.get("status") == "ACCOUNT_STATUS_CLOSED", "opened": x.get("openedDate")})

        def tot(a):
            try:
                p = client.portfolio(a["id"])
                return qf(p.get("totalAmountPortfolio")), len(p.get("positions") or [])
            except ApiError:
                return 0.0, 0
        for a, (t, n) in zip(accs, pool_map(tot, accs)):
            a["total"], a["empty"] = t, (t < 0.01 and n == 0)
    for imp in imports_list():
        a = {"id": imp["id"], "name": imp["name"], "kind": "import", "type": imp.get("broker") or "",
             "closed": False, "opened": None}
        try:
            rows = imported_positions(client, store().ops(imp["id"]), instruments(client, []))
            a["total"] = sum((r["value_rub"] or 0) for r in rows)
        except Exception:  # noqa: BLE001
            a["total"] = 0.0
        a["empty"] = a["total"] < 0.01
        accs.append(a)
    if not accs:
        raise ApiError("Нет счетов: добавьте API-токен в «Настройках» или импортируйте отчёт брокера.", 404)
    return mem_put(key, accs)


def selection(cfg, acc, force=False):
    accs = list_accounts(cfg, force)
    if acc == "all":
        sel = [a for a in accs if not a["empty"]] or accs
    else:
        sel = [a for a in accs if a["id"] == acc] or [accs[0]]
    data = pool_map(lambda a: account_data(cfg, a, force), sel, workers=4)
    return accs, sel, data


def build_summary(cfg, acc, period, force=False):
    client = TInvest(cfg)
    accs, sel, data = selection(cfg, acc, force)
    ops = sorted([o for d in data for o in d["ops"]], key=lambda o: o.get("date") or "")
    keys = set()
    for d in data:
        for x in (d["port"] or {}).get("positions") or []:
            keys.add((x.get("instrumentUid"), x.get("figi")))
    keys |= {(o.get("instrumentUid"), o.get("figi")) for o in ops
             if (o.get("instrumentUid") or o.get("figi")) and not str(o.get("instrumentUid") or "").startswith("imp:")}
    names = instruments(client, keys)
    lists, extra = [], {"daily": 0.0, "has_daily": False, "yield_w": 0.0}
    for a, d in zip(sel, data):
        if d["port"] is not None:
            rows = tinvest_positions(d["port"], names)
            p = d["port"]
            if p.get("dailyYield"):
                extra["daily"] += qf(p["dailyYield"])
                extra["has_daily"] = True
            store().snap(token_key(cfg) + ":" + a["id"], qf(p.get("totalAmountPortfolio")))
        else:
            rows = imported_positions(client, d["ops"], names)
        lists.append(rows)
    rows = merge_positions(lists)
    t = totals_from_rows(rows)
    total = sum(qf((d["port"] or {}).get("totalAmountPortfolio")) for d in data if d["port"] is not None) + \
        sum(sum((r["value_rub"] or 0) for r in lst) for lst, d in zip(lists, data) if d["port"] is None)
    res = analyze(ops, names, period, total)
    cost = sum(r.get("cost_rub") or 0 for r in rows if r["type"] not in ("currency", "futures"))
    upnl = sum(r.get("pnl_rub") or 0 for r in rows if r["type"] not in ("currency",))
    res["portfolio"] = {"total": total, "shares": t["shares"], "bonds": t["bonds"], "etf": t["etf"],
                        "currencies": t["currencies"], "futures": t["futures"], "options": t["options"], "sp": t["sp"],
                        "other": t["other"], "upnl": upnl, "yield_pct": upnl / cost * 100 if cost else 0.0,
                        "daily": extra["daily"] if extra["has_daily"] else None,
                        "daily_pct": extra["daily"] / (total - extra["daily"]) * 100 if extra["has_daily"] and total - extra["daily"] else None,
                        "positions": rows}
    if len(sel) == 1 and data[0]["margin"]:
        m = data[0]["margin"]
        res["margin"] = {k: qf(m.get(k)) for k in ("liquidPortfolio", "startingMargin", "minimalMargin",
                                                   "fundsSufficiencyLevel", "amountOfMissingFunds", "correctedMargin")}
    res["accounts"] = accs
    res["account"] = "all" if acc == "all" else sel[0]["id"]
    res["selected"] = [a["id"] for a in sel]
    res["sandbox"] = cfg["sandbox"]
    res["token"] = bool(cfg["token"])
    res["updated"] = datetime.now().strftime("%H:%M")
    return res


def build_bonds(cfg, acc, force=False):
    ratings_start()          # обновит рейтинги, если данным больше 12 часов
    key = ("bonds", token_key(cfg), acc)
    hit = None if force else mem_get(key, 600)
    if hit:
        st = ratings_status()
        if hit.get("ratings_info", {}).get("updated") != st["updated"]:
            hit["ratings"] = apply_ratings(hit["rows"])
        hit["ratings_info"] = st
        return hit
    s = build_summary(cfg, acc, "all")
    rep_ = mem_put(key, bonds_report(TInvest(cfg), s["portfolio"]["positions"]))
    try:
        expert_start([r["name"] for r in rep_["rows"]])      # дозапросит рейтинги Эксперт РА по эмитентам портфеля
    except Exception:  # noqa: BLE001
        pass
    return rep_


def build_history_for(cfg, acc, force=False):
    key = ("hist", token_key(cfg), acc)
    hit = None if force else mem_get(key, 900)
    if hit:
        return hit
    client = TInvest(cfg)
    accs, sel, data = selection(cfg, acc)
    ops = sorted([o for d in data for o in d["ops"]], key=lambda o: o.get("date") or "")
    keys = {(o.get("instrumentUid"), o.get("figi")) for o in ops
            if (o.get("instrumentUid") or o.get("figi")) and not str(o.get("instrumentUid") or "").startswith("imp:")}
    names = instruments(client, keys)
    total = sum(qf((d["port"] or {}).get("totalAmountPortfolio")) for d in data if d["port"] is not None)
    if any(d["port"] is None for d in data):
        total += sum(sum((r["value_rub"] or 0) for r in imported_positions(client, d["ops"], names)) for d in data if d["port"] is None)
    h = build_history(client, ops, names, total) or {"days": []}
    return mem_put(key, h)


def operations_csv(data):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Дата", "Тип", "Категория", "Название", "Тикер", "Кол-во", "Цена", "Сумма", "Валюта", "Комиссия", "Результат", "Счёт"])
    for r in data["ops"]:
        r = r[:11] + r[12:13]
        w.writerow([("" if not x else str(round(x, 9)).replace(".", ",")) if isinstance(x, (int, float)) else x for x in r])
    return buf.getvalue().encode("utf-8-sig")


# ═══════════════════════════════ логотипы ═══════════════════════════════

_logo_lock = threading.Lock()


def logo_bytes(name):
    base = re.sub(r"[^A-Za-z0-9_.-]", "", name or "").replace(".png", "")
    if not base:
        return None
    path = os.path.join(LOGO_DIR, base + ".png")
    miss = path + ".miss"
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    if os.path.exists(miss) and time.time() - os.path.getmtime(miss) < 3 * DAY:
        return None
    cfg = load_config()
    ctx = TInvest(cfg).ctx
    try:
        req = urllib.request.Request(LOGO_CDN + base + "x160.png", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            data = r.read()
        if not data.startswith(b"\x89PNG"):
            raise OSError("not png")
        with _logo_lock:
            os.makedirs(LOGO_DIR, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        return data
    except Exception:  # noqa: BLE001
        os.makedirs(LOGO_DIR, exist_ok=True)
        open(miss, "w").close()
        return None


