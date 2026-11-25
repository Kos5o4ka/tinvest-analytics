_TG_KIND = {"price": "📉", "spread": "📈", "offer": "🔔", "default": "⛔", "rating": "🏷", "watch": "👁", "outlook": "👁",
            "halt": "⏸", "liquidity": "💧", "goal": "⭐", "reminder": "📝"}
_TG_COOL = {"price": 7 * DAY, "spread": 7 * DAY}      # повтор не раньше, чем через неделю; остальные тревоги — один раз


def _tg_key(a):
    k = a["id"]
    if a.get("kind") in _TG_COOL:
        k = "%s|%s|%s" % (a["kind"], a.get("isin"), "")
    return k


def _tg_alert_line(a):
    """«📉 <b>Бумага</b> — сообщение» и строка со ссылками (пресс-релиз/источник, бумага на Мосбирже)."""
    nm = a.get("name") or ""
    line = "%s <b>%s</b> — %s" % (_TG_KIND.get(a.get("kind"), "•"), _tg_esc(nm), _tg_esc(a.get("message")))
    url = str(a.get("url") or "")
    links = []
    if url and "moex.com/ru/issue" not in url:
        links.append(_tg_link(url, "Пресс-релиз" if a.get("kind") == "rating" else "Подробнее"))
    if a.get("isin"):
        links.append(_tg_moex(a["isin"]))
    links = [x for x in links if x]
    return line + ("\n" + " · ".join(links) if links else "")


def tg_dispatch_plan(title, alerts, sent, now, icon="🔔"):
    """Раскладка ещё не отправленных тревог по сообщениям: до трёх сообщений за проверку, до 10 тревог и в предел длины
    каждое; остальное уйдёт в следующий раз (в последнем сообщении об этом сказано). -> [(текст, [(ключ, тревога)])].
    Чистая функция; зеркало на сервере — alerts.dispatch_plan."""
    fresh = []
    for a in alerts:
        k = _tg_key(a)
        last = sent.get(k)
        if last is not None and now - last < _TG_COOL.get(a.get("kind"), 400 * DAY):
            continue
        fresh.append((k, a))
    if not fresh:
        return []
    head = _tg_head(icon, title)
    room = TG_LIMIT - len(TG_DISCLAIMER) - len(head) - 120
    plan, i = [], 0
    for msg_no in range(3):
        if i >= len(fresh):
            break
        chunk, lines, size = [], [], 0
        while i < len(fresh) and len(chunk) < 10:
            ln = _tg_alert_line(fresh[i][1])
            if chunk and size + len(ln) + 2 > room:
                break
            chunk.append(fresh[i])
            lines.append(ln)
            size += len(ln) + 2
            i += 1
        tail = ("\n\n…и ещё %d — придут при следующей проверке" % (len(fresh) - i)) if msg_no == 2 and i < len(fresh) else ""
        plan.append(("%s\n\n%s%s" % (head, "\n\n".join(lines), tail), chunk))
    return plan


def _tg_dispatch(cfg, title, alerts, sent, now, icon="🔔"):
    """Отправляет план tg_dispatch_plan. Возвращает число отправленных тревог."""
    sent_n = 0
    for text, chunk in tg_dispatch_plan(title, alerts, sent, now, icon):
        tg_send(cfg, text)
        for k, a in chunk:
            sent[k] = now
        sent_n += len(chunk)
    return sent_n


_TG_KIND["default_ok"] = "✅"
TG_DFL_DAYS = 30


def defaults_alerts(cfg, sent=None, rows=None, isins=None):
    """Тревоги о техдефолте/дефолте по бумагам портфеля и списка наблюдения (лента defaults_feed) и «исполнено» после него.
    Неисполненное -> kind default, severity high, id dfl|isin|дата|обязательство (один раз). Исполненное -> kind default_ok,
    id dflx|... — только если о дефолте по этой записи мы уже сообщали (ключ dfl|... есть в sent). Бумаги вне портфеля/наблюдения
    не трогаем. rows/isins передаются в тестах, иначе берутся из defaults_feed и _disc_own_isins."""
    sent = sent or {}
    own = list(isins) if isins is not None else _disc_own_isins(cfg, "all")
    if not own:
        return []
    if rows is None:
        rows = defaults_feed((date.today() - timedelta(days=TG_DFL_DAYS)).isoformat(), own)
    mine = set(own)
    out = []
    for r in rows:
        isin = r.get("isin")
        if isin not in mine:
            continue
        tail = "%s|%s" % (r.get("date") or r.get("basis") or "", r.get("obligation") or r.get("status"))
        base = {"isin": isin, "isins": [isin], "name": r.get("issuer") or isin, "bonds": [r.get("issuer") or isin],
                "date": r.get("date") or date.today().isoformat(), "url": r.get("url") or ""}
        what = "дефолт" if r.get("status") == "default" else "технический дефолт"
        ob = (r.get("obligation") or "обязательство").lower()
        amt = (", %s" % _tg_rub(r["amount"])) if r.get("amount") else ""
        due = (", срок %s" % _tg_date(r["due_date"])) if r.get("due_date") else ""
        kd, kx = "dfl|%s|%s" % (isin, tail), "dflx|%s|%s" % (isin, tail)
        if r.get("executed"):
            if kd in sent:
                out.append(dict(base, id=kx, kind="default_ok", severity="medium",
                                message="%s по бумаге исполнен(о): %s%s, раскрытие о выплате от %s" % (what, ob, amt, _tg_date(r["executed"]))))
        else:
            out.append(dict(base, id=kd, kind="default", severity="high",
                            message="%s по бумаге: %s%s%s (%s)" % (what, ob, amt, due, r.get("basis") or "")))
    return out


TG_OFR_CALL_DAYS, TG_OFR_CLOSE_DAYS, TG_OFR_PUT_HORIZON = 14, 2, 120


def _tg_dmy(d):
    return "%s.%s.%s" % (d[8:10], d[5:7], d[:4])


def tg_offer_due(items, today):
    """Напоминания по офертам портфеля -> [(ключ_дедупликации, текст)]. Чистая функция (today передаётся).
    items: [{isin, name, kind, date, period_start, period_end, coupon_status, new_rate}].
    Ключ 'ofr|isin|дата_оферты|тип', тип: coupon (новый купон после пут-оферты объявлен), open (приём заявок открыт),
    close (осталось <= 2 дней до конца приёма), call (до колла <= 14 дней). Каждый ключ уходит один раз (хранилище TG_SENT_KEY)."""
    out = []
    for it in items:
        isin, kind, od = it.get("isin"), it.get("kind"), it.get("date")
        if not isin or not od or od <= today:
            continue
        nm = _tg_esc(it.get("name") or isin)
        lk = "\n" + _tg_moex(isin)
        ps, pe = it.get("period_start"), it.get("period_end")
        base = "ofr|%s|%s|" % (isin, od)
        if kind == "put":
            if it.get("coupon_status") == "announced" and it.get("new_rate") is not None and (not pe or today <= pe):
                out.append((base + "coupon", "🔔 <b>%s</b> — эмитент объявил купон после пут-оферты (%s): %s годовых. Приём заявок открывается в период предъявления.%s"
                            % (nm, _tg_date(od), _tg_pct(it["new_rate"]), lk)))
            if ps and pe and ps <= today <= pe:
                out.append((base + "open", "🔔 <b>%s</b> — открыт приём заявок по пут-оферте: с %s по %s (выкуп %s). Заявку подаёт брокер.%s"
                            % (nm, _tg_date(ps), _tg_date(pe), _tg_date(od), lk)))
            if pe:
                left = _of_days(today, pe)
                if 0 <= left <= TG_OFR_CLOSE_DAYS and (not ps or ps <= today):
                    t = ("осталось %d дня подать заявку" % left if left >= 2 else "остался 1 день, чтобы подать заявку" if left == 1
                         else "сегодня последний день подачи заявки")
                    out.append((base + "close", "⏰ <b>%s</b> — %s на пут-оферту (последний день %s, выкуп %s).%s" % (nm, t, _tg_date(pe), _tg_date(od), lk)))
        elif kind == "call":
            left = _of_days(today, od)
            if 0 < left <= TG_OFR_CALL_DAYS:
                out.append((base + "call", "🔔 <b>%s</b> — возможное досрочное погашение (колл) %s, через %d дн. Решает эмитент, заявку подавать не нужно.%s"
                            % (nm, _tg_date(od), left, lk)))
    return out


def _tg_offer_items(cfg, today):
    """Оферты облигаций портфеля для напоминаний: ближайшие put (до TG_OFR_PUT_HORIZON дней) и call (до TG_OFR_CALL_DAYS)."""
    rows = [r for r in build_bonds(cfg, "all")["rows"] if r.get("isin") and r.get("qty")]
    lim = _day_add(today, TG_OFR_PUT_HORIZON)

    def one(r):
        try:
            bz = moex_bondization(r["isin"])
            res = []
            for o in offer_kinds(bz or {}, moex_bond_options(r["isin"]), r.get("call"), today):
                if o["status"] == "cancelled" or o["kind"] == "unknown" or o["date"] > lim:
                    continue
                nc = of_new_coupon((bz or {}).get("coupons") or [], o["date"], r.get("nominal") or 1000.0, bool(r.get("floating")))
                res.append({"isin": r["isin"], "name": r.get("name"), "kind": o["kind"], "date": o["date"], "period_start": o.get("period_start"),
                            "period_end": o.get("period_end"), "coupon_status": nc["status"], "new_rate": nc["rate"]})
            return res
        except Exception:  # noqa: BLE001
            return []
    return [x for lst in pool_map(one, rows, workers=8) for x in lst]


def _tg_payments(cfg, days):
    b = build_bonds(cfg, "all")
    end = (date.today() + timedelta(days=days)).isoformat()
    today = date.today().isoformat()
    ev = [(p["date"], p.get("kind"), p.get("name"), p.get("amount")) for p in (b.get("payments") or []) if today <= p["date"] <= end]
    ev += [(r["call"], "offer", r.get("name"), None) for r in (b.get("rows") or []) if r.get("call") and today <= r["call"] <= end]
    return sorted(ev, key=lambda x: (x[0], str(x[2])))


_TG_EV = {"coupon": "купон", "dividend": "дивиденд", "amortization": "амортизация", "redemption": "погашение",
          "maturity": "погашение", "offer": "оферта", "call": "оферта CALL", "put": "оферта PUT", "buyback": "выкуп"}


def _tg_ev_line(e):
    """«20 ноября · <b>Выпуск</b> — купон, 5 000 ₽»."""
    amt = ", %s" % _tg_rub(e[3]) if e[3] else ""
    return "%s · <b>%s</b> — %s%s" % (_tg_date(e[0]), _tg_esc(e[2]), _TG_EV.get(e[1], "выплата"), amt)


def tg_pay_fresh(ev, sent):
    """Ещё не отправленные выплаты -> [(ключ «pay|дата|вид|название», событие)]. Зеркало на сервере — alerts.pay_fresh."""
    out = []
    for e in ev:
        k = "pay|%s|%s|%s" % (e[0], e[1], e[2])
        if k not in sent:
            out.append((k, e))
    return out


def tg_pay_text(days, fresh):
    return "%s\n\n%s" % (_tg_head("💰", "Ближайшие выплаты", "%d дн." % days), _tg_cap([_tg_ev_line(e) for k, e in fresh], 15))


def tg_digest_text(cfg):
    parts = [_tg_head("📈", "Сводка TAnalytic", _tg_date(date.today().isoformat()))]
    if cfg.get("token") or imports_list():
        try:
            s = build_summary(cfg, "all", "all")
            p = s.get("portfolio") or {}
            if p.get("total") is not None:
                d = p.get("daily")
                parts.append("💼 <b>Портфель</b> — %s%s" % (_tg_rub(p["total"]),
                             (" (за день %s%s)" % ("+" if d >= 0 else "−", _tg_rub(abs(d)))) if d is not None else ""))
        except Exception:  # noqa: BLE001
            pass
        try:
            ev = _tg_payments(cfg, 7)
            if ev:
                parts.append("💰 <b>Ближайшие 7 дней</b>\n" + _tg_cap([_tg_ev_line(e) for e in ev], 8))
            else:
                parts.append("💰 <b>Ближайшие 7 дней</b> — выплат нет")
        except Exception:  # noqa: BLE001
            pass
        try:
            m = build_monitor(cfg, "all")
            parts.append("🔔 <b>Мониторинг</b> — высоких тревог: %d, средних: %d" % (m["summary"]["high"], m["summary"]["medium"]))
        except Exception:  # noqa: BLE001
            pass
    try:
        w = watch_payload(cfg)
        if w["items"]:
            ln = ["<b>%s</b> — %s" % (_tg_esc(r["name"]), ("доходность %s" % _tg_pct(r["yield_"])) if r.get("yield_") is not None else "нет данных")
                  for r in w["items"]]
            parts.append("👁 <b>Наблюдение</b> (бумаг: %d, тревог: %d)\n%s" % (len(w["items"]), len(w["alerts"]), _tg_cap(ln, 8)))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)


def tg_tick(force_digest=False, manual=False):
    """Одна проверка: новые тревоги, выплаты, ежедневная сводка. Возвращает число отправленных пунктов."""
    if not _tg_lock.acquire(False):
        return 0
    try:
        cfg = load_config()
        if not manual and not force_digest and not cfg.get("tg_enabled"):
            return 0
        if not all(ds_conf()):                  # нужен сервер данных и вход по ключу из бота
            return 0
        st = store()
        now = time.time()
        sent = {k: v for k, v in (st.get(TG_SENT_KEY) or {}).items() if now - v < 400 * DAY}
        n = 0
        srv = False
        try:        # серверная проверка: обновить подписку и не дублировать то, что отправит сервер
            if cfg.get("tg_server") and cfg.get("tg_enabled"):
                _tg_srv_sync(cfg, sent, force=not _tg_srv_boot[0])
                _tg_srv_boot[0] = True
            srv = tg_srv_active(cfg)
        except Exception:  # noqa: BLE001
            srv = tg_srv_active(cfg)
        has_port = bool(cfg.get("token") or imports_list())
        try:
            if cfg.get("tg_on_mon", True) and has_port:
                al = [a for a in build_monitor(cfg, "all")["alerts"] if a["severity"] == "high"]
                n += _tg_dispatch(cfg, "Тревоги по портфелю", al, sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:
            if cfg.get("tg_on_mon", True) and has_port and not srv:
                today_ = date.today().isoformat()
                due = [(k, t) for k, t in tg_offer_due(_tg_offer_items(cfg, today_), today_) if k not in sent][:10]
                if due:
                    tg_send(cfg, _tg_head("🔔", "Оферты по портфелю") + "\n\n" + "\n\n".join(t for _k, t in due))
                    for k, _t in due:
                        sent[k] = now
                    n += len(due)
        except Exception:  # noqa: BLE001
            pass
        try:
            if cfg.get("tg_on_watch", True) and (watch_isins() or notes_all()):
                al = [a for a in watch_payload(cfg)["alerts"] if a["severity"] != "info"
                      and not (srv and a.get("kind") in TG_SRV_KINDS)]
                n += _tg_dispatch(cfg, "Наблюдение и цели", al, sent, now, icon="⭐")
        except Exception:  # noqa: BLE001
            pass
        try:        # крупные сделки и всплески объёма по бумагам списка (13v_flows.py; ключ дедупликации — id тревоги)
            if cfg.get("tg_on_watch", True) and watch_isins() and "flows_watch_alerts" in globals():
                n += _tg_dispatch(cfg, "Потоки по списку наблюдения", flows_watch_alerts(cfg), sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:        # техдефолты/дефолты по бумагам портфеля и списка наблюдения + «исполнено» (13q_disclosure.py)
            if cfg.get("tg_on_mon", True) or cfg.get("tg_on_watch", True):
                n += _tg_dispatch(cfg, "Дефолты по бумагам портфеля и наблюдения", defaults_alerts(cfg, sent), sent, now)
        except Exception:  # noqa: BLE001
            pass
        try:
            days = int(cfg.get("tg_pay_days") or 0)
            if days > 0 and has_port and not srv:
                fresh = tg_pay_fresh(_tg_payments(cfg, days), sent)
                if fresh:
                    tg_send(cfg, tg_pay_text(days, fresh))
                    for k, e in fresh:
                        sent[k] = now
                    n += len(fresh)
        except Exception:  # noqa: BLE001
            pass
        try:
            state = st.get(TG_STATE_KEY) or {}
            hh = str(cfg.get("tg_digest_time") or "10:00")
            nowl = datetime.now()
            due = force_digest or (cfg.get("tg_digest") and state.get("digest") != date.today().isoformat()
                                   and nowl.strftime("%H:%M") >= hh)
            if due:
                tg_send(cfg, tg_digest_text(cfg))
                if not force_digest:
                    state["digest"] = date.today().isoformat()
                    st.put(TG_STATE_KEY, state)
                n += 1
        except Exception:  # noqa: BLE001
            pass
        st.put(TG_SENT_KEY, sent)
        return n
    except Exception:  # noqa: BLE001
        return 0            # сеть/Telegram недоступны — попробуем в следующий раз; детали (с токеном) не пишем
    finally:
        _tg_lock.release()
