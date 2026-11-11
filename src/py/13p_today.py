# ═══════════════════════════════ «Сегодня»: дневная сводка на «Обзоре» ═══════════════════════════════
# Выплаты на 7 дней, ближайшие оферты, рейтинговые действия за неделю и число тревог мониторинга.
# Чистые функции (td_*) не ходят в сеть; сеть и кэши трогает только td_build/today_get. Кэш 10 минут.

TD_PAY_DAYS, TD_OFFER_DAYS, TD_RATING_DAYS, TD_TTL = 7, 30, 7, 600
TD_PAY_KINDS = ("coupon", "dividend", "amortization")


def td_add_days(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def td_payments(pays, today, days=TD_PAY_DAYS):
    """Купоны, дивиденды и амортизации в окне [today, today+days]: сумма, число, разбивка по видам и 5 ближайших."""
    end = td_add_days(today, days)
    sel = sorted((p for p in pays or [] if p.get("kind") in TD_PAY_KINDS and today <= (p.get("date") or "") <= end and p.get("amount")),
                 key=lambda p: (p["date"], -(p.get("amount") or 0)))
    by = {}
    for p in sel:
        by[p["kind"]] = by.get(p["kind"], 0) + p["amount"]
    return {"count": len(sel), "sum": sum(p["amount"] for p in sel), "days": days, "by_kind": by,
            "next_date": sel[0]["date"] if sel else None,
            "items": [{"date": p["date"], "kind": p["kind"], "name": p.get("name"), "amount": p["amount"]} for p in sel[:5]]}


def td_offer_status(o, today):
    """Статус оферты: open (идёт приём заявок) | upcoming (приём ещё не начался) | closed | unknown (период не опубликован)."""
    ps, pe = o.get("period_start"), o.get("period_end")
    if ps and pe:
        return "open" if ps <= today <= pe else ("upcoming" if today < ps else "closed")
    return "unknown"


def td_offers(pairs, today, days=TD_OFFER_DAYS):
    """pairs: [(строка облигации, список оферт offer_kinds)]. Оферты в ближайшие days дней, без отменённых, по возрастанию даты."""
    end = td_add_days(today, days)
    out = []
    for r, offs in pairs or []:
        for o in offs or []:
            if o.get("status") == "cancelled" or not (today <= (o.get("date") or "") <= end):
                continue
            st = td_offer_status(o, today) if o["kind"] == "put" else "unknown"
            if st == "closed":
                continue
            out.append({"isin": r.get("isin"), "name": r.get("name"), "kind": o["kind"], "date": o["date"],
                        "days": (datetime.strptime(o["date"], "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days,
                        "status": st, "period_start": o.get("period_start"), "period_end": o.get("period_end")})
    out.sort(key=lambda x: (x["date"], {"put": 0, "call": 1}.get(x["kind"], 2), x["name"] or ""))
    return {"count": len(out), "days": days, "put": sum(1 for x in out if x["kind"] == "put"),
            "call": sum(1 for x in out if x["kind"] == "call"), "items": out[:5]}


def td_ratings(events, rows_keys, today, days=TD_RATING_DAYS):
    """Рейтинговые действия за days дней по эмитентам портфеля (та же логика, что у тревог монитора)."""
    al = _mon_rating_alerts(rows_keys, events or [], td_add_days(today, -days))
    return {"count": len(al), "days": days, "negative": sum(1 for a in al if a["severity"] in ("high", "medium")),
            "items": [{"date": a["date"], "name": a["name"], "message": a["message"], "severity": a["severity"]} for a in al[:5]]}


def td_digest(pays, pairs, events, rows_keys, today, alerts=None):
    """Собирает сводку; пустые разделы выбрасываются, empty=True — показывать карточку нечего."""
    d = {"today": today, "payments": td_payments(pays, today), "offers": td_offers(pairs, today),
         "ratings": td_ratings(events, rows_keys, today)}
    if alerts is not None:
        d["alerts"] = {"count": sum(1 for a in alerts if a.get("severity") in ("high", "medium")),
                       "high": sum(1 for a in alerts if a.get("severity") == "high")}
    for k in ("payments", "offers", "ratings", "alerts"):
        if k in d and not d[k]["count"]:
            del d[k]
    d["empty"] = not any(k in d for k in ("payments", "offers", "ratings", "alerts"))
    return d


def td_empty():
    return {"today": date.today().isoformat(), "empty": True}


def _td_warm_monitor(cfg, acc):
    try:
        build_monitor(cfg, acc)
    except Exception:  # noqa: BLE001
        pass


def td_build(cfg, acc):
    today = date.today().isoformat()
    rep = build_bonds(cfg, acc)
    rows = [r for r in rep.get("rows") or [] if r.get("isin") and r.get("qty")]

    def one(r):
        try:
            return r, offers_of_isin(r["isin"], r.get("call"), today)
        except Exception:  # noqa: BLE001
            return r, []
    pairs = pool_map(one, rows, workers=8)
    events = (store().get(RT_LOG_KEY) or {}).get("events") or []
    rows_keys = [(r, _mon_issuer_keys(r)) for r in rows]
    alerts = None
    try:                                  # мониторинг тяжёлый: берём только готовый результат, а прогрев запускаем в фоне
        th = mon_thresholds(cfg)
        mon = mem_get(("monitor", token_key(cfg), acc, tuple(sorted(th.items()))), 900)
        if mon is not None:
            alerts = mon.get("alerts") or []
        else:
            threading.Thread(target=_td_warm_monitor, args=(cfg, acc), daemon=True).start()
    except Exception:  # noqa: BLE001
        alerts = None
    return td_digest(rep.get("payments") or [], pairs, events, rows_keys, today, alerts)


def today_get(cfg, acc, q, force):
    if not cfg.get("token") and not imports_list():
        return td_empty()
    key = ("today", token_key(cfg), acc)
    if not force:
        hit = mem_get(key, TD_TTL)
        if hit:
            return hit
    try:
        res = td_build(cfg, acc)
    except Exception:  # noqa: BLE001
        return td_empty()
    return mem_put(key, res)


API_GET["/api/today"] = today_get
