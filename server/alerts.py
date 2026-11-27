# -*- coding: utf-8 -*-
"""Серверная проверка тревог TAnalytic: работает, пока приложение пользователя закрыто (по желанию пользователя).

Приложение присылает «подписку» (POST /v1/alerts/sync) — только правила по публичным данным:
  goals     — цели по бумагам списка наблюдения: ISIN, название, целевая доходность/цена;
  reminders — напоминания дневника: id заметки, ISIN, название, дата заметки и дата напоминания (БЕЗ текста заметки);
  offers    — ближайшие оферты облигаций портфеля: ISIN, название, тип, даты (график Мосбиржи), объявлен ли новый купон;
  pay_days, pays — ближайшие выплаты: дата, вид, название, сумма (≈ число бумаг × купон по графику Мосбиржи);
  sent      — ключи уже отправленных приложением уведомлений (чтобы сервер их не повторил).
Токен Т-Инвестиций, номера счетов, стоимость портфеля, остатки денег сюда не попадают: лишние поля отклоняются (400).

Хранение: таблицы alert_subs / alert_sent в общей базе бота (keys.sqlite, та же, что у outbox). Подписка удаляется
командой приложения (POST /v1/alerts/delete), кнопкой в боте (/alerts) и автоматически, когда у пользователя не осталось
действующего ключа (ключи — 7 дней), он удалён (/delete) или заблокирован.

Проверка (AlertChecker) — раз в ~15 минут, сообщения кладутся в outbox через Notifier (лимиты и флаг notify как у /v1/notify),
в тихие часы (по умолчанию 22:00–08:00 МСК) не отправляется ничего. Тексты и ключи дедупликации совпадают с приложением
(13j_watch.py): проверяется тестами tests/test_watch_server.py. Только стандартная библиотека.
"""
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
DAY = 86400
SUB_V = 1
SUB_MAX_BYTES = 128 * 1024
LIMITS = {"goals": 300, "reminders": 300, "offers": 500, "pays": 1000, "sent": 5000}
SENT_PREFIXES = ("gy|", "gp|", "rm|", "ofr|", "pay|")
SENT_KEEP = 400 * DAY
SYNC_PER_HOUR = 60

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS alert_subs(tg_id INTEGER PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL, "
    "updated REAL NOT NULL, checked REAL, sent_n INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS alert_sent(tg_id INTEGER NOT NULL, k TEXT NOT NULL, t REAL NOT NULL, PRIMARY KEY(tg_id, k))",
)


class AlertError(Exception):
    def __init__(self, code, error):
        Exception.__init__(self, error)
        self.code, self.error = code, error


# ───────────────────────── проверка подписки ─────────────────────────
ISIN_RX = re.compile(r"^[A-Z0-9]{6,16}$")
DATE_RX = re.compile(r"^\d{4}-\d\d-\d\d$")
NOTE_RX = re.compile(r"^n\d{1,24}$")
PAY_KINDS = ("coupon", "dividend", "amortization", "redemption", "maturity", "offer", "call", "put", "buyback")
FIELDS = {
    "goals": {"isin", "name", "target_yield", "target_price", "watch_only"},
    "reminders": {"id", "isin", "name", "date", "remind_on"},
    "offers": {"isin", "name", "kind", "date", "period_start", "period_end", "coupon_status", "new_rate"},
    "pays": {"date", "kind", "name", "amount"},
}
TOP = {"v", "goals", "reminders", "offers", "pay_days", "pays", "sent", "resume", "bot_goals_rev", "weekly_digest"}


def _bad(what):
    raise AlertError(400, "bad_" + what)


def _s(x, n=120):
    if x is None:
        return ""
    if not isinstance(x, str):
        _bad("string")
    return re.sub(r"[\x00-\x1f\x7f]", " ", x).strip()[:n]


def _isin(x):
    if not isinstance(x, str) or not ISIN_RX.match(x):
        _bad("isin")
    return x


def _date(x, opt=False):
    if x is None and opt:
        return None
    if not isinstance(x, str) or not DATE_RX.match(x):
        _bad("date")
    return x


def _numf(x, opt=True, lo=0.0, hi=1e12):
    if x is None and opt:
        return None
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or not lo <= x <= hi:
        _bad("number")
    return float(x)


def validate(p):
    """Подписка из запроса -> очищенная копия. Любое неизвестное поле, неверный тип или превышение лимита -> AlertError(400)."""
    if not isinstance(p, dict) or p.get("v") != SUB_V:
        _bad("version")
    if set(p) - TOP:
        _bad("field")
    if not isinstance(p.get("resume", False), bool):
        _bad("resume")
    if not isinstance(p.get("weekly_digest", False), bool):
        _bad("weekly_digest")
    bgr = p.get("bot_goals_rev")
    if bgr is not None and (isinstance(bgr, bool) or not isinstance(bgr, int) or bgr < 0 or bgr > 10**9):
        _bad("bot_goals_rev")
    out = {"v": SUB_V, "resume": bool(p.get("resume")), "weekly_digest": bool(p.get("weekly_digest", False)),
           "bot_goals_rev": bgr}
    for name in ("goals", "reminders", "offers", "pays"):
        lst = p.get(name) or []
        if not isinstance(lst, list) or len(lst) > LIMITS[name]:
            _bad(name)
        for it in lst:
            if not isinstance(it, dict) or set(it) - FIELDS[name]:
                _bad("field")
    out["goals"] = []
    for it in p.get("goals") or []:
        wo = it.get("watch_only")
        if wo is not None and not isinstance(wo, bool):
            _bad("watch_only")
        g = {"isin": _isin(it.get("isin")), "name": _s(it.get("name"))}
        for k in ("target_yield", "target_price"):
            v = _numf(it.get(k), hi=1e6)
            if v is not None and v > 0:
                g[k] = v
        if "target_yield" in g or "target_price" in g:
            out["goals"].append(g)
        elif wo:
            g["watch_only"] = True
            out["goals"].append(g)
    out["reminders"] = []
    for it in p.get("reminders") or []:
        nid = it.get("id")
        if not isinstance(nid, str) or not NOTE_RX.match(nid):
            _bad("id")
        out["reminders"].append({"id": nid, "isin": _isin(it.get("isin")), "name": _s(it.get("name")),
                                 "date": _date(it.get("date")), "remind_on": _date(it.get("remind_on"))})
    out["offers"] = []
    for it in p.get("offers") or []:
        if it.get("kind") not in ("put", "call"):
            _bad("kind")
        cs = it.get("coupon_status")
        if cs is not None and (not isinstance(cs, str) or not re.match(r"^[a-z_]{1,20}$", cs)):
            _bad("coupon_status")
        out["offers"].append({"isin": _isin(it.get("isin")), "name": _s(it.get("name")), "kind": it["kind"],
                              "date": _date(it.get("date")), "period_start": _date(it.get("period_start"), True),
                              "period_end": _date(it.get("period_end"), True), "coupon_status": it.get("coupon_status"),
                              "new_rate": _numf(it.get("new_rate"), lo=-100.0, hi=1000.0)})
    pd = p.get("pay_days", 0)
    if isinstance(pd, bool) or not isinstance(pd, int) or not 0 <= pd <= 60:
        _bad("pay_days")
    out["pay_days"] = pd
    out["pays"] = []
    for it in p.get("pays") or []:
        if it.get("kind") not in PAY_KINDS:
            _bad("kind")
        out["pays"].append({"date": _date(it.get("date")), "kind": it["kind"], "name": _s(it.get("name")),
                            "amount": _numf(it.get("amount"))})
    sent = p.get("sent") or []
    if not isinstance(sent, list) or len(sent) > LIMITS["sent"]:
        _bad("sent")
    out["sent"] = [k for k in sent if isinstance(k, str) and len(k) <= 240 and k.startswith(SENT_PREFIXES)]
    return out


# ───────────────────────── форматирование (зеркало 13j_watch.py, проверяется тестами на совпадение) ─────────────────────────
TG_DISCLAIMER = "\n\n<i>Не является индивидуальной инвестиционной рекомендацией.</i>"
TG_LIMIT = 3500
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
TG_OFR_CALL_DAYS, TG_OFR_CLOSE_DAYS = 14, 2
KIND_ICON = {"goal": "[цель]", "reminder": "[напоминание]", "default": "[дефолт]", "default_ok": "[дефолт снят]", "rating": "[рейтинг]",
             "disclosure": "[раскрытие]", "coupon_declared": "[купон]", "flow_large": "[крупная сделка]", "flow_spike": "[всплеск объёма]"}
EV = {"coupon": "купон", "dividend": "дивиденд", "amortization": "амортизация", "redemption": "погашение",
      "maturity": "погашение", "offer": "оферта", "call": "оферта CALL", "put": "оферта PUT", "buyback": "выкуп"}


def esc(s):
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def num(x, dec=0):
    return ("{:,.%df}" % dec).format(x).replace(",", " ").replace(".", ",")


def rub(x):
    return num(x, 0 if abs(x) >= 100 or x == int(x) else 2) + " ₽"


def pct(x, dec=2):
    return num(x, dec) + "%"


def f2(x):
    return ("%.2f" % x).replace(".", ",")


def tdate(iso, today):
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()
    except ValueError:
        return esc(iso)
    return "%d %s%s" % (d.day, MONTHS[d.month - 1], "" if d.year == int(today[:4]) else " %d" % d.year)


def link(url, text):
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return ""
    return '<a href="%s">%s</a>' % (u.replace("&", "&amp;").replace('"', "%22").replace("<", "%3C").replace(">", "%3E"), esc(text))


def moex(isin):
    from urllib.parse import quote
    return link("https://www.moex.com/ru/issue.aspx?code=%s" % quote(str(isin or "")), "на Мосбирже") if isin else ""


def head(icon, title, sub=""):
    return "%s<b>%s</b>%s" % ((icon + " ") if icon else "", esc(title), (" · " + esc(sub)) if sub else "")


def cap(lines, shown, more=""):
    out = list(lines[:shown])
    if len(lines) > shown:
        out.append("…и ещё %d%s" % (len(lines) - shown, more))
    return "\n".join(out)


def fit(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:max(limit - 40, 1)]
    cut = cut.rsplit("\n", 1)[0] if "\n" in cut else cut
    cut = re.sub(r"<[^>]*$", "", cut)
    cut = re.sub(r"&[a-z#0-9]*$", "", cut)
    stack = []
    for m in re.finditer(r"<(/?)(b|i|a|code)\b[^>]*>", cut):
        if m.group(1):
            if m.group(2) in stack:
                stack = stack[:len(stack) - stack[::-1].index(m.group(2)) - 1]
        else:
            stack.append(m.group(2))
    return cut.rstrip() + "\n…" + "".join("</%s>" % t for t in reversed(stack))


def days_between(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def alert_line(a):
    line = "%s <b>%s</b> — %s" % (KIND_ICON.get(a.get("kind"), "•"), esc(a.get("name") or ""), esc(a.get("message")))
    url = str(a.get("url") or "")
    links = []
    if url and "moex.com/ru/issue" not in url:
        links.append(link(url, "Подробнее"))
    if a.get("isin"):
        links.append(moex(a["isin"]))
    links = [x for x in links if x]
    return line + ("\n" + " · ".join(links) if links else "")


def goal_alerts(g, q, today):
    """Цели по бумаге (как watch_goal_alerts в приложении). q — {price, yield} с Мосбиржи или None."""
    out = []
    if not q:
        return out
    base = {"isin": g["isin"], "name": q.get("name") or g.get("name") or g["isin"], "url": "", "date": today, "severity": "medium", "kind": "goal"}
    ty, tp = g.get("target_yield"), g.get("target_price")
    if ty is not None and q.get("yield") is not None and q["yield"] >= ty:
        out.append(dict(base, id="gy|%s|%s" % (g["isin"], ty),
                        message="Цель достигнута: доходность %s %% (цель — от %s %%)" % (f2(q["yield"]), f2(ty))))
    if tp is not None and q.get("price") is not None and q["price"] <= tp:
        out.append(dict(base, id="gp|%s|%s" % (g["isin"], tp),
                        message="Цель достигнута: цена %s %% (цель — не выше %s %%)" % (f2(q["price"]), f2(tp))))
    return out


def reminder_alerts(rems, today):
    """Напоминания дневника: текст заметки на сервер не передаётся, поэтому в сообщении только бумага и дата."""
    out = []
    for n in rems:
        if n["remind_on"] <= today:
            d = n.get("date") or n["remind_on"]
            out.append({"isin": n["isin"], "name": n.get("name") or n["isin"], "id": "rm|" + n["id"], "severity": "medium",
                        "kind": "reminder", "date": n["remind_on"], "url": "",
                        "message": "Напоминание из дневника от %s (текст заметки — в TAnalytic)" % (d[8:] + "." + d[5:7])})
    return out


def dispatch_plan(title, alerts, sent, icon=""):
    """Как tg_dispatch_plan в приложении: до трёх сообщений, до 10 тревог в каждом -> [(текст, [ключ, ...])]."""
    fresh = [(a["id"], a) for a in alerts if a["id"] not in sent]
    if not fresh:
        return []
    hd = head(icon, title)
    room = TG_LIMIT - len(TG_DISCLAIMER) - len(hd) - 120
    out, i = [], 0
    for msg_no in range(3):
        if i >= len(fresh):
            break
        chunk, lines, size = [], [], 0
        while i < len(fresh) and len(chunk) < 10:
            ln = alert_line(fresh[i][1])
            if chunk and size + len(ln) + 2 > room:
                break
            chunk.append(fresh[i][0])
            lines.append(ln)
            size += len(ln) + 2
            i += 1
        tail = ("\n\n…и ещё %d — придут при следующей проверке" % (len(fresh) - i)) if msg_no == 2 and i < len(fresh) else ""
        out.append(("%s\n\n%s%s" % (hd, "\n\n".join(lines), tail), chunk))
    return out


def offer_due(items, today):
    """Зеркало tg_offer_due (13j_watch.py) -> [(ключ, текст)]."""
    out = []
    for it in items:
        isin, kind, od = it.get("isin"), it.get("kind"), it.get("date")
        if not isin or not od or od <= today:
            continue
        nm = esc(it.get("name") or isin)
        lk = "\n" + moex(isin)
        ps, pe = it.get("period_start"), it.get("period_end")
        base = "ofr|%s|%s|" % (isin, od)
        if kind == "put":
            if it.get("coupon_status") == "announced" and it.get("new_rate") is not None and (not pe or today <= pe):
                out.append((base + "coupon", "<b>%s</b> — эмитент объявил купон после пут-оферты (%s): %s годовых. Приём заявок открывается в период предъявления.%s"
                            % (nm, tdate(od, today), pct(it["new_rate"]), lk)))
            if ps and pe and ps <= today <= pe:
                out.append((base + "open", "<b>%s</b> — открыт приём заявок по пут-оферте: с %s по %s (выкуп %s). Заявку подаёт брокер.%s"
                            % (nm, tdate(ps, today), tdate(pe, today), tdate(od, today), lk)))
            if pe:
                left = days_between(today, pe)
                if 0 <= left <= TG_OFR_CLOSE_DAYS and (not ps or ps <= today):
                    t = ("осталось %d дня подать заявку" % left if left >= 2 else "остался 1 день, чтобы подать заявку" if left == 1
                         else "сегодня последний день подачи заявки")
                    out.append((base + "close", "<b>%s</b> — %s на пут-оферту (последний день %s, выкуп %s).%s"
                                % (nm, t, tdate(pe, today), tdate(od, today), lk)))
        elif kind == "call":
            left = days_between(today, od)
            if 0 < left <= TG_OFR_CALL_DAYS:
                out.append((base + "call", "<b>%s</b> — возможное досрочное погашение (колл) %s, через %d дн. Решает эмитент, заявку подавать не нужно.%s"
                            % (nm, tdate(od, today), left, lk)))
    return out


def offers_text(due):
    return head("", "Оферты по портфелю") + "\n\n" + "\n\n".join(t for _k, t in due)


def ev_line(e, today):
    amt = ", %s" % rub(e[3]) if e[3] else ""
    return "%s · <b>%s</b> — %s%s" % (tdate(e[0], today), esc(e[2]), EV.get(e[1], "выплата"), amt)


def pay_fresh(events, sent):
    """Зеркало tg_pay_fresh: [(ключ, (дата, вид, название, сумма))] ещё не отправленных."""
    out = []
    for e in events:
        k = "pay|%s|%s|%s" % (e[0], e[1], e[2])
        if k not in sent:
            out.append((k, e))
    return out


def pay_text(days, fresh, today):
    return "%s\n\n%s" % (head("", "Ближайшие выплаты", "%d дн." % days), cap([ev_line(e, today) for _k, e in fresh], 15))


def pay_events(pays, today, days):
    """Выплаты из подписки в окне [today, today+days], отсортированные как в приложении (_tg_payments)."""
    end = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
    ev = [(p["date"], p["kind"], p["name"], p.get("amount")) for p in pays if today <= p["date"] <= end]
    return sorted(ev, key=lambda x: (x[0], str(x[2])))


# ───────────────────────── котировки облигаций (как screener_rows в приложении) ─────────────────────────
ISS_URL = ("https://iss.moex.com/iss/engines/stock/markets/bonds/boards/%s/securities.json?iss.meta=off"
           "&iss.only=securities,marketdata&securities.columns=SECID,ISIN,SHORTNAME,MATDATE,PREVLEGALCLOSEPRICE,YIELDATPREVWAPRICE"
           "&marketdata.columns=SECID,WAPRICE,LAST,YIELD,YIELDATWAPRICE")
BOARDS = ("TQCB", "TQOB", "TQOD", "TQOY")


def _table(j, name):
    t = (j or {}).get(name) or {}
    cols = t.get("columns") or []
    return [dict(zip(cols, r)) for r in t.get("data") or []]


def quotes_from_iss(j, out=None):
    """Ответ ISS по одному режиму торгов -> {isin: {price, yield, name}} по тем же правилам, что screener_rows."""
    out = {} if out is None else out
    md = {r["SECID"]: r for r in _table(j, "marketdata")}
    for s in _table(j, "securities"):
        m = md.get(s["SECID"], {})
        price = m.get("WAPRICE") or m.get("LAST") or s.get("PREVLEGALCLOSEPRICE")
        yld = m.get("YIELD") or m.get("YIELDATWAPRICE") or s.get("YIELDATPREVWAPRICE")
        if not price or not s.get("MATDATE") or str(s["MATDATE"]).startswith("0000"):
            continue
        out[s.get("ISIN") or s["SECID"]] = {
            "price": round(price, 3),
            "yield": round(float(yld), 2) if yld else None,
            "name": s.get("SHORTNAME"),
        }
    return out


# ───────────────────────── хранилище ─────────────────────────
def fresh_bot_deleted(sub, seen_rev):
    """ISIN, удалённые в боте после ревизии seen_rev, которую программа уже видела."""
    rev = int(sub.get("bot_goals_rev") or 0)
    rev_of = sub.get("bot_rev_of") if isinstance(sub.get("bot_rev_of"), dict) else {}
    return [x for x in sub.get("bot_deleted") or [] if isinstance(x, str) and int(rev_of.get(x) or rev) > int(seen_rev or 0)]


class AlertStore:
    """Подписки и отправленные ключи в общей базе бота. Своё соединение на поток (как KeyStore)."""

    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock
        self._local = threading.local()
        self._ready = False
        self._sync_lock, self._syncs = threading.Lock(), {}

    def conn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            from urllib.parse import quote
            c = sqlite3.connect("file:%s?mode=rw" % quote(self.path.replace("\\", "/"), safe="/:"), uri=True, timeout=5,
                                isolation_level=None, check_same_thread=False)
            c.execute("PRAGMA busy_timeout=5000")
            self._local.c = c
        if not self._ready:
            for q in SCHEMA:
                c.execute(q)
            self._ready = True
        return c

    def rate_ok(self, tg_id):
        now = self.clock()
        with self._sync_lock:
            xs = [t for t in self._syncs.get(tg_id, []) if now - t < 3600]
            if len(xs) >= SYNC_PER_HOUR:
                self._syncs[tg_id] = xs
                return False
            xs.append(now)
            if len(self._syncs) > 10000:
                self._syncs.clear()
            self._syncs[tg_id] = xs
            return True

    def put(self, tg_id, sub):
        """Сохраняет подписку (без sent) и добавляет присланные приложением ключи в отправленные. -> все отправленные ключи."""
        now = self.clock()
        c = self.conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            mk = "alerts_stop:%d" % int(tg_id)
            try:          # пользователь остановил проверку в боте (/alerts): автоматическая синхронизация её не возвращает
                stopped = c.execute("SELECT 1 FROM meta WHERE k=?", (mk,)).fetchone()
                if stopped and sub.get("resume"):
                    c.execute("DELETE FROM meta WHERE k=?", (mk,))
                elif stopped:
                    raise AlertError(409, "stopped_in_bot")
            except sqlite3.OperationalError:
                pass
            row = c.execute("SELECT data FROM alert_subs WHERE tg_id=?", (tg_id,)).fetchone()
            existing = json.loads(row[0]) if row else {}
            existing_rev = int(existing.get("bot_goals_rev") or 0)
            existing_bot_goals = [g for g in (existing.get("bot_goals") or []) if isinstance(g, dict) and g.get("isin")]
            existing_deleted = [x for x in (existing.get("bot_deleted") or []) if isinstance(x, str)]
            client_rev = sub.get("bot_goals_rev")
            data = {k: v for k, v in sub.items() if k not in ("sent", "resume", "bot_goals_rev")}
            if existing_rev > 0 and (client_rev is None or client_rev < existing_rev):
                # применяем только правки бота новее ревизии, которую программа уже видела: иначе удалённая
                # в программе цель из бота воскресала бы при каждой синхронизации
                rev_of = existing.get("bot_rev_of") if isinstance(existing.get("bot_rev_of"), dict) else {}
                seen = client_rev or 0
                fresh = lambda isin: int(rev_of.get(isin) or existing_rev) > seen
                deleted_set = {x for x in existing_deleted if fresh(x)}
                merged = [g for g in (data.get("goals") or []) if g.get("isin") not in deleted_set]
                idx = {g["isin"]: i for i, g in enumerate(merged)}
                for bg in existing_bot_goals:
                    isin = bg["isin"]
                    if not fresh(isin):
                        continue
                    if isin in idx:
                        merged[idx[isin]] = bg
                    else:
                        idx[isin] = len(merged)
                        merged.append(bg)
                data["goals"] = merged
                data["bot_goals"] = existing_bot_goals
                if existing_deleted:
                    data["bot_deleted"] = existing_deleted
                if rev_of:
                    data["bot_rev_of"] = rev_of
                data["bot_goals_rev"] = existing_rev
            elif existing_rev > 0:
                data["bot_goals_rev"] = existing_rev
            raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            if len(raw.encode("utf-8")) > SUB_MAX_BYTES:
                raise AlertError(413, "too_large")
            c.execute("INSERT INTO alert_subs(tg_id, data, created, updated) VALUES(?,?,?,?) "
                      "ON CONFLICT(tg_id) DO UPDATE SET data=excluded.data, updated=excluded.updated", (tg_id, raw, now, now))
            c.executemany("INSERT OR IGNORE INTO alert_sent(tg_id, k, t) VALUES(?,?,?)", [(tg_id, k, now) for k in sub.get("sent") or []])
            c.execute("DELETE FROM alert_sent WHERE tg_id=? AND t<?", (tg_id, now - SENT_KEEP))
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        return self.sent_keys(tg_id)

    def upsert_bot_goal(self, tg_id, goal):
        """Добавляет, обновляет или удаляет цель из бота, увеличивая bot_goals_rev. -> новый bot_goals_rev."""
        if not isinstance(goal, dict):
            _bad("goal")
        isin = _isin(goal.get("isin"))
        is_del = bool(goal.get("deleted") or goal.get("delete"))
        g = None
        if not is_del:
            g = {"isin": isin, "name": _s(goal.get("name"))}
            for k in ("target_yield", "target_price"):
                v = _numf(goal.get(k), hi=1e6)
                if v is not None and v > 0:
                    g[k] = v
            if "target_yield" not in g and "target_price" not in g:
                if goal.get("watch_only"):
                    g["watch_only"] = True
                else:
                    _bad("goal")
        now = self.clock()
        c = self.conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT data FROM alert_subs WHERE tg_id=?", (tg_id,)).fetchone()
            if row:
                data = json.loads(row[0])
            else:
                data = {"v": SUB_V, "goals": [], "reminders": [], "offers": [], "pay_days": 0, "pays": [], "weekly_digest": False}
            deleted = [x for x in (data.get("bot_deleted") or []) if isinstance(x, str) and x != isin]
            if is_del:
                for lst_key in ("goals", "bot_goals"):
                    data[lst_key] = [it for it in (data.get(lst_key) or []) if it.get("isin") != isin]
                deleted.append(isin)
            else:
                for lst_key in ("goals", "bot_goals"):
                    lst = list(data.get(lst_key) or [])
                    for i, it in enumerate(lst):
                        if it.get("isin") == isin:
                            lst[i] = g
                            break
                    else:
                        lst.append(g)
                    data[lst_key] = lst
            if deleted:
                data["bot_deleted"] = deleted[-LIMITS["goals"]:]
            else:
                data.pop("bot_deleted", None)
            rev = int(data.get("bot_goals_rev") or 0) + 1
            data["bot_goals_rev"] = rev
            rev_of = data.get("bot_rev_of") if isinstance(data.get("bot_rev_of"), dict) else {}
            rev_of[isin] = rev
            keep = {g.get("isin") for g in data.get("bot_goals") or []} | set(data.get("bot_deleted") or [])
            data["bot_rev_of"] = {k: v for k, v in rev_of.items() if k in keep}
            raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            if len(raw.encode("utf-8")) > SUB_MAX_BYTES:
                raise AlertError(413, "too_large")
            c.execute("INSERT INTO alert_subs(tg_id, data, created, updated) VALUES(?,?,?,?) "
                      "ON CONFLICT(tg_id) DO UPDATE SET data=excluded.data, updated=excluded.updated", (tg_id, raw, now, now))
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        return rev

    def delete_bot_goal(self, tg_id, isin):
        """Удаляет цель из бота, увеличивая bot_goals_rev. -> новый bot_goals_rev."""
        return self.upsert_bot_goal(tg_id, {"isin": isin, "deleted": True})

    def stats(self):
        """Количество активных подписок и время последней проверки: {subs, last_checked}."""
        r = self.conn().execute("SELECT COUNT(*), MAX(checked) FROM alert_subs").fetchone()
        return {"subs": int(r[0] or 0), "last_checked": r[1]}

    def get(self, tg_id):
        r = self.conn().execute("SELECT data, created, updated, checked, sent_n FROM alert_subs WHERE tg_id=?", (tg_id,)).fetchone()
        if not r:
            return None
        return {"sub": json.loads(r[0]), "created": r[1], "updated": r[2], "checked": r[3], "sent_n": r[4]}

    def users(self):
        return [r[0] for r in self.conn().execute("SELECT tg_id FROM alert_subs ORDER BY tg_id")]

    def sent_keys(self, tg_id):
        return [r[0] for r in self.conn().execute("SELECT k FROM alert_sent WHERE tg_id=? ORDER BY t DESC LIMIT ?", (tg_id, LIMITS["sent"]))]

    def mark_sent(self, tg_id, keys):
        now = self.clock()
        c = self.conn()
        c.executemany("INSERT OR REPLACE INTO alert_sent(tg_id, k, t) SELECT ?,?,? WHERE EXISTS(SELECT 1 FROM alert_subs WHERE tg_id=?)",
                      [(tg_id, k, now, tg_id) for k in keys])
        c.execute("UPDATE alert_subs SET sent_n=sent_n+? WHERE tg_id=?", (len(keys), tg_id))

    def checked(self, tg_id):
        self.conn().execute("UPDATE alert_subs SET checked=? WHERE tg_id=?", (self.clock(), tg_id))

    def delete(self, tg_id):
        """Удаляет подписку и отправленные ключи. -> (была ли подписка, ключи отправленного — вернуть приложению)."""
        keys = self.sent_keys(tg_id)
        c = self.conn()
        n = c.execute("DELETE FROM alert_subs WHERE tg_id=?", (tg_id,)).rowcount
        c.execute("DELETE FROM alert_sent WHERE tg_id=?", (tg_id,))
        return bool(n), keys

    def user_state(self, tg_id):
        """-> gone (нет пользователя/заблокирован/нет действующего ключа) | paused (не Pro или уведомления выключены) | ok."""
        c, now = self.conn(), self.clock()
        try:
            u = c.execute("SELECT banned, notify, plan_until FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        except sqlite3.OperationalError:
            u = c.execute("SELECT banned, 1, NULL FROM users WHERE tg_id=?", (tg_id,)).fetchone()
        if not u or u[0]:
            return "gone"
        k = c.execute("SELECT COUNT(*) FROM keys WHERE tg_id=? AND revoked=0 AND expires>?", (tg_id, now)).fetchone()[0]
        if not k:
            return "gone"
        if not u[1] or not (u[2] and u[2] > now):
            return "paused"
        return "ok"


def prefs_of(store, tg_id):
    """Личные тихие часы и часовой пояс из настроек бота (/quiet): (с, до, UTC-смещение). Нет колонок (старая база) — (None, None, 3).
    NULL, NULL — пользователь тихие часы не настраивал (действует общее окно); равные значения (бот при «выкл» пишет 0 и 0) —
    окна нет совсем."""
    try:
        r = store.conn().execute("SELECT quiet_from, quiet_to, tz_offset FROM users WHERE tg_id=?", (tg_id,)).fetchone()
    except sqlite3.OperationalError:
        return None, None, 3
    if not r:
        return None, None, 3
    tz = r[2] if isinstance(r[2], int) and -12 <= r[2] <= 14 else 3
    return r[0], r[1], tz


def min_severity_of(store, tg_id):
    """Минимальный порог важности уведомлений из настроек бота (/quiet sev): 0 | 1 | 2."""
    try:
        r = store.conn().execute("SELECT min_severity FROM users WHERE tg_id=?", (tg_id,)).fetchone()
    except sqlite3.OperationalError:
        return 0
    try:
        return max(0, min(2, int(r[0] or 0))) if r else 0
    except (TypeError, ValueError):
        return 0


def muted_isins(store, tg_id, now):
    """Множество ISIN, для которых пользователь временно приостановил оповещения (alert_mute:<uid>:<isin> в meta)."""
    prefix = "alert_mute:%d:" % int(tg_id)
    try:
        rows = store.conn().execute("SELECT k, v FROM meta WHERE k LIKE ?", (prefix + "%",)).fetchall()
    except sqlite3.OperationalError:
        return set()
    out = set()
    for k, v in rows:
        try:
            if float(v) > now:
                isin = k[len(prefix):].strip().upper()
                if isin:
                    out.add(isin)
        except (TypeError, ValueError):
            continue
    return out


def summary(sub):
    return {"goals": len(sub.get("goals") or []), "reminders": len(sub.get("reminders") or []),
            "offers": len(sub.get("offers") or []), "pays": len(sub.get("pays") or []), "pay_days": sub.get("pay_days") or 0}


# ───────────────────────── проверка ─────────────────────────
def msk_now(now):
    return datetime.fromtimestamp(now, MSK)


def quiet(now, start=22, end=8):
    h = msk_now(now).hour
    return (h >= start or h < end) if start > end else start <= h < end


def local_now(now, tz_offset=3):
    return datetime.fromtimestamp(now, timezone(timedelta(hours=tz_offset)))


def quiet_local(now, tz_offset, start, end):
    """Тихие часы по местному времени пользователя (то же правило, что в боте: начало == конец — нет тихих часов)."""
    if start is None or end is None or start == end:
        return False
    h = local_now(now, tz_offset).hour
    return (h >= start or h < end) if start > end else start <= h < end


DIGEST_MIN, DIGEST_LINES, DIGEST_HEAD = 3, 14, "<b>Сводка событий по вашему портфелю и наблюдению</b>"


def _digest_items(text):
    """Пункты сводки из текста сообщения: абзацы после заголовка. Строка со ссылками («Подробнее · на Мосбирже») относится к
    предыдущему пункту и отдельным пунктом не становится. -> (пункты, True, если в сообщении не больше 4 пунктов в абзаце)."""
    pars = [p for p in text.split("\n\n") if p.strip()]
    out, full = [], True
    for p in (pars[1:] if len(pars) > 1 else pars):
        items = []
        for x in p.split("\n"):
            x = x.strip()
            if not x:
                continue
            if x.startswith("<a ") and items:
                items[-1] += " · " + x
            else:
                items.append(fit(x, 200).replace("\n…", "…") if len(x) > 200 else x)
        out += items[:4]
        full = full and len(items) <= 4
    return out, full


def _digest_lines(text):
    return _digest_items(text)[0]


def coalesce_messages(msgs, urgent=lambda keys: False):
    """Несколько сообщений за одну проверку склеиваются в один дайджест (срочные остаются отдельными). Дайджест берёт сообщения
    целиком, пока в нём не больше DIGEST_LINES строк; остальные не отправляются и не помечаются отправленными: попадут в следующую
    проверку. Сообщение, которое не помещается в сводку без урезания (длинный список), уходит отдельным сообщением целиком:
    скрытые за «…и ещё N» события отправленными не помечаются. -> (что отправить сейчас, отложено)."""
    keep = [m for m in msgs if urgent(m[1])]
    rest = [m for m in msgs if not urgent(m[1])]
    if len(rest) < DIGEST_MIN:
        return msgs, 0
    lines, keys, used, deferred = [], [], 0, 0
    full_msgs = []
    for text, ks in rest:
        ln, full = _digest_items(text)
        if not full:
            full_msgs.append((text, ks))
            continue
        if lines and len(lines) + len(ln) > DIGEST_LINES:
            deferred += 1
            continue
        lines += ln
        keys += ks
        used += 1
    out = keep + full_msgs
    if used:
        digest = DIGEST_HEAD + "\n\n" + "\n".join("• " + x for x in lines) + "\n\n<i>Подробности — в приложении TAnalytic.</i>"
        out.append((digest, keys))
    return out, deferred


def _watched_isins(sub):
    """-> (множество ISIN из подписки, {ISIN: название}, множество ISIN с офертами)."""
    watched, names, offers = set(), {}, set()
    if not isinstance(sub, dict):
        return watched, names, offers
    for key in ("goals", "bot_goals", "offers", "reminders"):
        for it in sub.get(key) or ():
            if not isinstance(it, dict):
                continue
            isin = str(it.get("isin") or "").strip().upper()
            if not isin:
                continue
            watched.add(isin)
            if it.get("name") and isin not in names:
                names[isin] = str(it["name"])
            if key == "offers":
                offers.add(isin)
    for isin in sub.get("isins") or ():
        s = str(isin or "").strip().upper()
        if s:
            watched.add(s)
    return watched, names, offers


def _num_val(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _sev_int(v, default=1):
    if isinstance(v, int) and not isinstance(v, bool):
        return max(0, min(2, v))
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("high", "crit", "critical", "2"):
            return 2
        if s in ("medium", "normal", "1"):
            return 1
        if s in ("low", "info", "0"):
            return 0
    return default


_DISC_DEFAULT_RX = re.compile(r"дефолт|неисполнен\w*\s+обязательств|просрочк\w*\s+выплат", re.I)
_DISC_RATING_RX = re.compile(r"рейтинг|прогноз.{0,25}(?:негатив|позитив|стабиль|пересмотр|развива)", re.I)
_DISC_DOWN_RX = re.compile(r"пониж|сниж|отзыв|отозван|негатив|дефолт|\bRD\b|\bSD\b|\bD\b", re.I)
_DISC_COUPON_RX = re.compile(r"(?:ставк|размер)\w*\s+купон|купон.{0,30}оферт|оферт.{0,30}купон", re.I)
_DISC_MAT_RX = re.compile(
    r"существен|досрочн\w*\s+погашен|приобретен\w*\s+облигац|выкуп|реорганиз|делистинг|банкрот|ликвидац",
    re.I,
)


def disclosure_alerts(sub, disclosures, sent, now):
    """Существенные факты раскрытия, изменения рейтингов, техдефолты и объявление ставки купона перед офертой
    для отслеживаемых и портфельных ISIN -> список тревог, ещё не попавших в sent."""
    watched, names, offer_isins = _watched_isins(sub)
    if not watched or not disclosures:
        return []
    sent_set = set(sent or ())
    today = datetime.fromtimestamp(now, MSK).strftime("%Y-%m-%d") if now else ""
    out = []
    seen = set()
    for d in disclosures:
        if not isinstance(d, dict):
            continue
        cands = []
        if d.get("isin"):
            cands.append(str(d["isin"]).strip().upper())
        for x in d.get("isins") or ():
            s = str(x or "").strip().upper()
            if s and s not in cands:
                cands.append(s)
        matched = [x for x in cands if x in watched]
        if not matched:
            continue
        kind_in = str(d.get("kind") or "").strip().lower()
        title = str(d.get("title") or d.get("message") or "").strip()
        data = d.get("data") if isinstance(d.get("data"), dict) else {}
        dt = str(d.get("event_date") or d.get("published") or d.get("date") or today)[:10]
        doc_id = d.get("doc_id") if d.get("doc_id") is not None else d.get("id")
        paid_pct = _num_val(data.get("paid_pct"))

        is_default = (
            kind_in in ("default", "technical_default", "default_ok")
            or (kind_in == "coupon_paid" and paid_pct is not None and paid_pct < 99.5)
            or bool(_DISC_DEFAULT_RX.search(title))
        )
        is_rating = (
            kind_in in ("rating", "rating_change", "rating_downgrade", "rating_upgrade", "outlook")
            or bool(d.get("rating") or data.get("rating"))
            or bool(_DISC_RATING_RX.search(title))
        )
        is_coupon = (
            kind_in in ("coupon_declared", "offer_coupon")
            or bool(_DISC_COUPON_RX.search(title))
        )
        is_material = (
            kind_in in ("buyback_result", "placement_result", "material", "fact")
            or bool(d.get("material"))
            or bool(_DISC_MAT_RX.search(title))
        )
        if not (is_default or is_rating or is_coupon or is_material):
            continue

        for isin in matched:
            if is_default:
                if kind_in == "default_ok" or data.get("executed"):
                    kind_out, sev = "default_ok", 1
                    msg = title or "Обязательство после дефолта исполнено"
                else:
                    kind_out, sev = "default", 2
                    ob = str(data.get("obligation") or "").strip()
                    if title:
                        msg = title if "дефолт" in title.lower() or "неисполнен" in title.lower() else ("Технический дефолт: " + title)
                    elif ob:
                        msg = "Технический дефолт (%s)" % ob
                    else:
                        msg = "Технический дефолт / неисполнение обязательств"
            elif is_rating:
                kind_out = "rating"
                probe = " ".join(str(x or "") for x in (title, data.get("action"), data.get("outlook"), d.get("action"), kind_in))
                sev = 2 if (kind_in == "rating_downgrade" or _DISC_DOWN_RX.search(probe)) else 1
                rt = d.get("rating") or data.get("rating")
                old_rt = d.get("old_rating") or data.get("old_rating")
                if title:
                    msg = title
                elif old_rt and rt:
                    msg = "Изменение рейтинга: %s → %s" % (old_rt, rt)
                elif rt:
                    msg = "Кредитный рейтинг: %s" % rt
                else:
                    msg = "Изменение кредитного рейтинга"
            elif is_coupon:
                kind_out = "coupon_declared"
                before_offer = (isin in offer_isins) or ("оферт" in title.lower()) or (kind_in == "offer_coupon")
                sev = 2 if before_offer else 1
                rate = _num_val(d.get("new_rate") if d.get("new_rate") is not None else (data.get("new_rate") if data.get("new_rate") is not None else data.get("rate")))
                if title and rate is not None and "%" not in title:
                    msg = "%s (%s)" % (title, pct(rate))
                elif title:
                    msg = title
                elif rate is not None:
                    msg = "Объявлена ставка купона%s: %s" % (" перед офертой" if before_offer else "", pct(rate))
                else:
                    msg = "Объявлена новая ставка купона"
            else:
                kind_out = "disclosure"
                sev = 2 if re.search(r"банкрот|ликвидац|делистинг", title, re.I) else 1
                msg = title or "Существенный факт раскрытия"

            if d.get("severity") is not None:
                sev = _sev_int(d.get("severity"), sev)

            if isinstance(doc_id, str) and doc_id.startswith(("disc|", "dfl|", "dflx|")):
                aid = doc_id
            elif doc_id is not None and str(doc_id) != "":
                aid = "disc|%s|%s" % (isin, doc_id)
            else:
                aid = "disc|%s|%s|%s|%s" % (isin, kind_out, dt, msg[:40])

            if aid in sent_set or aid in seen:
                continue
            seen.add(aid)
            nm = d.get("name") or d.get("issuer") or d.get("org") or names.get(isin) or isin
            out.append({
                "id": aid,
                "isin": isin,
                "name": nm,
                "kind": kind_out,
                "severity": sev,
                "date": dt,
                "url": d.get("url") or "",
                "message": msg,
            })
    return out


def flow_alerts(sub, flows_spikes, sent, now):
    """Всплески объёма (>= 3x) и аномально крупные сделки по бумагам из подписки -> список тревог, не попавших в sent."""
    watched, names, _ = _watched_isins(sub)
    if not watched or not flows_spikes:
        return []
    sent_set = set(sent or ())
    if isinstance(flows_spikes, dict):
        items = list(flows_spikes.get("spikes") or ()) + list(flows_spikes.get("large") or ())
    else:
        items = list(flows_spikes)
    out = []
    seen = set()
    for r in items:
        if not isinstance(r, dict):
            continue
        isin = str(r.get("isin") or "").strip().upper()
        secid = str(r.get("secid") or "").strip().upper()
        key_id = isin if isin in watched else (secid if secid in watched else "")
        if not key_id:
            continue
        ts = _num_val(r.get("ts"))
        if ts is not None and now is not None and float(now) - ts > 7 * DAY:
            continue
        hhmm = datetime.fromtimestamp(ts, MSK).strftime("%H:%M") if ts is not None else ""
        ts_part = int(ts or 0)
        dt = datetime.fromtimestamp(ts, MSK).strftime("%Y-%m-%d") if ts is not None else (
            datetime.fromtimestamp(now, MSK).strftime("%Y-%m-%d") if now else ""
        )
        kind_in = str(r.get("kind") or "").strip().lower()
        ratio = _num_val(r.get("ratio"))
        side = str(r.get("side") or "").strip().lower()
        val = _num_val(r.get("value"))

        is_spike = kind_in in ("spike", "flow_spike") or (ratio is not None and side not in ("buy", "sell"))
        is_large = kind_in in ("large", "flow_large") or side in ("buy", "sell")

        if is_spike:
            if ratio is None or ratio < 3.0:
                continue
            aid = r.get("id") if isinstance(r.get("id"), str) and r["id"].startswith("flow_") else (
                "flow_spike|%s|%d" % (secid or key_id, ts_part)
            )
            if aid in sent_set or aid in seen:
                continue
            seen.add(aid)
            val_txt = rub(val) if val is not None else "—"
            time_txt = (" (%s МСК)" % hhmm) if hhmm else ""
            msg = "Всплеск объёма ×%.1f: %s за 10 минут%s" % (ratio, val_txt, time_txt)
            sev = _sev_int(r.get("severity"), 1)
            out.append({
                "id": aid,
                "isin": isin or key_id,
                "name": r.get("name") or names.get(key_id) or secid or key_id,
                "kind": "flow_spike",
                "severity": sev,
                "date": dt,
                "url": "",
                "message": msg,
            })
        elif is_large:
            if val is None or val <= 0:
                continue
            side_key = side if side in ("buy", "sell") else "trade"
            aid = r.get("id") if isinstance(r.get("id"), str) and r["id"].startswith("flow_") else (
                "flow_large|%s|%d|%s|%d" % (secid or key_id, ts_part, side_key, int(val))
            )
            if aid in sent_set or aid in seen:
                continue
            seen.add(aid)
            side_ru = "покупка" if side == "buy" else ("продажа" if side == "sell" else "сделка")
            px = _num_val(r.get("price"))
            px_txt = (" по %s" % num(px, 2)) if px is not None else ""
            time_txt = (" (%s МСК)" % hhmm) if hhmm else ""
            msg = "Крупная %s %s%s%s" % (side_ru, rub(val), px_txt, time_txt)
            sev = _sev_int(r.get("severity"), 1)
            out.append({
                "id": aid,
                "isin": isin or key_id,
                "name": r.get("name") or names.get(key_id) or secid or key_id,
                "kind": "flow_large",
                "severity": sev,
                "date": dt,
                "url": "",
                "message": msg,
            })
    return out


def _build_messages(sub, quotes, today, sent, muted=None, disclosures=None, flows_spikes=None, now=None, min_severity=0):
    """Внутренняя сборка сообщений: -> [(текст без приписки, [ключи], severity)]."""
    muted_set = {str(x).strip().upper() for x in (muted or ()) if x}
    min_sev = max(0, min(2, int(min_severity or 0)))
    msgs = []

    if min_sev <= 2:
        offers = [o for o in (sub.get("offers") or []) if str(o.get("isin") or "").upper() not in muted_set]
        due = []
        for k, t in offer_due(offers, today):
            if k in sent:
                continue
            is_close = k.startswith("ofr|") and k.endswith("|close")
            if min_sev >= 2 and not is_close:
                continue
            due.append((k, t))
        due = due[:10]
        if due:
            sev = 2 if any(k.startswith("ofr|") and k.endswith("|close") for k, _t in due) else 0
            msgs.append((offers_text(due), [k for k, _t in due], sev))

    al = []
    if min_sev <= 1:
        for g in sub.get("goals") or []:
            if str(g.get("isin") or "").upper() in muted_set:
                continue
            al += goal_alerts(g, quotes.get(g["isin"]), today)
        rems = [r for r in (sub.get("reminders") or []) if str(r.get("isin") or "").upper() not in muted_set]
        al += reminder_alerts(rems, today)
        for text, keys in dispatch_plan("Наблюдение и цели", al, sent, icon=""):
            msgs.append((text, keys, 0))

    if disclosures:
        sub_eff = sub
        if muted_set:
            sub_eff = dict(sub)
            for k in ("goals", "bot_goals", "offers", "reminders"):
                sub_eff[k] = [it for it in (sub.get(k) or []) if str((it or {}).get("isin") or "").upper() not in muted_set]
            if sub.get("isins"):
                sub_eff["isins"] = [x for x in sub["isins"] if str(x or "").upper() not in muted_set]
        disc_all = [a for a in disclosure_alerts(sub_eff, disclosures, sent, now) if a.get("severity", 1) >= min_sev]
        crit = [a for a in disc_all if a.get("severity", 1) >= 2]
        norm = [a for a in disc_all if a.get("severity", 1) < 2]
        for text, keys in dispatch_plan("Важные раскрытия и рейтинги", crit, sent, icon=""):
            msgs.append((text, keys, 2))
        for text, keys in dispatch_plan("Раскрытия и рейтинги", norm, sent, icon=""):
            msgs.append((text, keys, 0))

    if flows_spikes and min_sev <= 1:
        sub_eff = sub
        if muted_set:
            sub_eff = dict(sub)
            for k in ("goals", "bot_goals", "offers", "reminders"):
                sub_eff[k] = [it for it in (sub.get(k) or []) if str((it or {}).get("isin") or "").upper() not in muted_set]
            if sub.get("isins"):
                sub_eff["isins"] = [x for x in sub["isins"] if str(x or "").upper() not in muted_set]
        fl_al = [a for a in flow_alerts(sub_eff, flows_spikes, sent, now) if a.get("severity", 1) >= min_sev]
        for text, keys in dispatch_plan("Потоки по списку наблюдения", fl_al, sent, icon=""):
            msgs.append((text, keys, 0))

    days = int(sub.get("pay_days") or 0)
    if days > 0 and min_sev <= 1:
        fresh = pay_fresh(pay_events(sub.get("pays") or [], today, days), sent)
        if fresh:
            msgs.append((pay_text(days, fresh, today), [k for k, _e in fresh], 0))
    return msgs


def build_messages(sub, quotes, today, sent, muted=None, disclosures=None, flows_spikes=None, now=None):
    """Подписка + котировки -> [(текст без приписки, [ключи])] в порядке приложения: оферты, наблюдение и цели, раскрытия, потоки, выплаты."""
    return [(t, ks) for t, ks, _sev in _build_messages(
        sub, quotes, today, sent, muted=muted, disclosures=disclosures, flows_spikes=flows_spikes, now=now,
    )]


def _read_disclosures_db(data_dir, isins, now):
    path = os.path.join(data_dir, "disclosure.sqlite") if data_dir else ""
    if not path or not isins or not os.path.exists(path):
        return []
    from urllib.parse import quote
    since = datetime.fromtimestamp(now - 30 * DAY, MSK).strftime("%Y-%m-%d")
    db = None
    try:
        db = sqlite3.connect("file:%s?mode=ro" % quote(path.replace("\\", "/"), safe="/:"), uri=True, timeout=3)
        ph = ",".join("?" * len(isins))
        rows = db.execute(
            "SELECT f.doc_id, d.title, d.published, f.isin, f.kind, f.event_date, f.data "
            "FROM facts f JOIN docs d ON d.id=f.doc_id "
            "WHERE f.isin IN (%s) AND d.published>=? ORDER BY d.published DESC, f.doc_id DESC LIMIT 200" % ph,
            list(isins) + [since],
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if db:
            db.close()
    out = []
    for did, title, pub, isin, kind, ev, raw in rows:
        try:
            data = json.loads(raw or "null")
        except ValueError:
            data = None
        out.append({"doc_id": did, "title": title, "published": pub, "isin": isin, "kind": kind,
                    "event_date": ev, "data": data, "url": "https://e-disclosure.azipi.ru/messages/%d/" % did})
    return out


def _read_flows_db(data_dir, isins, now):
    path = os.path.join(data_dir, "flows.sqlite") if data_dir else ""
    if not path or not isins or not os.path.exists(path):
        return []
    from urllib.parse import quote
    since = now - 6 * 3600
    db = None
    try:
        db = sqlite3.connect("file:%s?mode=ro" % quote(path.replace("\\", "/"), safe="/:"), uri=True, timeout=3)
        ph = ",".join("?" * len(isins))
        spikes = [
            {"kind": "flow_spike", "ts": ts, "secid": s, "name": nm or s, "isin": isn or "",
             "value": v, "median": md, "ratio": r}
            for ts, s, nm, isn, v, md, r in db.execute(
                "SELECT s.ts, s.secid, i.name, i.isin, s.value, s.median, s.ratio "
                "FROM spikes s LEFT JOIN instruments i ON i.secid=s.secid "
                "WHERE s.ts>=? AND s.ratio>=3.0 AND (i.isin IN (%s) OR s.secid IN (%s)) "
                "ORDER BY s.ts DESC LIMIT 100" % (ph, ph),
                [since] + list(isins) + list(isins),
            ).fetchall()
        ]
        large = [
            {"kind": "flow_large", "ts": ts, "secid": s, "name": nm or s, "isin": isn or "",
             "side": sd, "price": p, "qty": q, "value": v}
            for ts, s, nm, isn, sd, p, q, v in db.execute(
                "SELECT l.ts, l.secid, i.name, i.isin, l.side, l.price, l.qty, l.value "
                "FROM large l LEFT JOIN instruments i ON i.secid=l.secid "
                "WHERE l.ts>=? AND (i.isin IN (%s) OR l.secid IN (%s)) "
                "ORDER BY l.ts DESC LIMIT 100" % (ph, ph),
                [since] + list(isins) + list(isins),
            ).fetchall()
        ]
        return spikes + large
    except sqlite3.Error:
        return []
    finally:
        if db:
            db.close()


class AlertChecker:
    """Обход подписок: purge ушедших, котировки Мосбиржи через кэш сервера (fetch), сообщения в outbox через Notifier."""

    def __init__(self, store, notifier, fetch_json, clock=time.time, quiet_hours=(22, 8),
                 disclosure_rows=None, flow_rows=None, data_dir=None):
        self.store, self.notifier, self.fetch_json, self.clock = store, notifier, fetch_json, clock
        self.quiet_hours = quiet_hours
        self.disclosure_rows = disclosure_rows
        self.flow_rows = flow_rows
        self.data_dir = data_dir
        self.last = {"t": None, "users": 0, "sent": 0, "purged": 0}

    def quotes(self, isins):
        if not isins:
            return {}
        out = {}
        for b in BOARDS:
            try:
                j = self.fetch_json(ISS_URL % b)
            except Exception:  # noqa: BLE001
                j = None
            if j:
                quotes_from_iss(j, out)
        return out

    @staticmethod
    def _resolve_rows(src, isins, now):
        if callable(src):
            try:
                return src(isins, now)
            except TypeError:
                return src()
        return src

    def run_once(self, disclosure_rows=None, flow_rows=None):
        now = self.clock()
        stats = {"t": now, "users": 0, "sent": 0, "purged": 0}
        users = self.store.users()
        live = []
        for uid in users:
            st = self.store.user_state(uid)
            if st == "gone":
                self.store.delete(uid)
                stats["purged"] += 1
            elif st == "ok":
                live.append(uid)
        if live:
            st_now = {}
            for uid in live:                     # у каждого свой часовой пояс и тихие часы (настройки бота /quiet)
                qf, qt, tz = prefs_of(self.store, uid)
                if qf is None or qt is None:
                    qf, qt = self.quiet_hours if self.quiet_hours else (None, None)
                st_now[uid] = (tz, quiet_local(now, tz, qf, qt))
            subs = {uid: (self.store.get(uid) or {}).get("sub") or {} for uid in live if not st_now[uid][1]}
            need = {g["isin"] for s in subs.values() for g in s.get("goals") or []
                    if g.get("target_yield") is not None or g.get("target_price") is not None}
            all_watched = set()
            for s in subs.values():
                all_watched |= _watched_isins(s)[0]
            q = self.quotes(need) if subs else {}
            disc_src = disclosure_rows if disclosure_rows is not None else self.disclosure_rows
            if disc_src is not None:
                disc_data = self._resolve_rows(disc_src, all_watched, now)
            elif self.data_dir and all_watched:
                disc_data = _read_disclosures_db(self.data_dir, all_watched, now)
            else:
                disc_data = None
            flow_src = flow_rows if flow_rows is not None else self.flow_rows
            if flow_src is not None:
                flow_data = self._resolve_rows(flow_src, all_watched, now)
            elif self.data_dir and all_watched:
                flow_data = _read_flows_db(self.data_dir, all_watched, now)
            else:
                flow_data = None
            for uid, sub in subs.items():
                if not self.store.get(uid):
                    continue
                stats["users"] += 1
                today = local_now(now, st_now[uid][0]).strftime("%Y-%m-%d")
                sent = set(self.store.sent_keys(uid))
                muted = muted_isins(self.store, uid, now)
                min_sev = min_severity_of(self.store, uid)
                raw_msgs = _build_messages(
                    sub, q, today, sent, muted=muted, disclosures=disc_data, flows_spikes=flow_data,
                    now=now, min_severity=min_sev,
                )
                urgent_keys = {k for _t, ks, sv in raw_msgs if sv >= 2 for k in ks}
                msgs, deferred = coalesce_messages(
                    [(t, ks) for t, ks, _sv in raw_msgs],
                    lambda ks, uk=urgent_keys: any(k in uk for k in ks),
                )
                stats["deferred"] = stats.get("deferred", 0) + deferred
                for text, keys in msgs:
                    if not self.store.get(uid):
                        break
                    sev = 2 if any(k in urgent_keys for k in keys) else 0
                    msg = fit(text, TG_LIMIT - len(TG_DISCLAIMER)) + TG_DISCLAIMER
                    try:
                        if sev:
                            self.notifier.enqueue(uid, msg, severity=sev)
                        else:
                            self.notifier.enqueue(uid, msg)
                    except Exception as e:  # noqa: BLE001   NotifyError: лимит/notify_off/нет пользователя — попробуем в следующий раз
                        if getattr(e, "error", "") == "unknown_user":
                            self.store.delete(uid)
                        break
                    self.store.mark_sent(uid, keys)
                    stats["sent"] += len(keys)
                self.store.checked(uid)
        self.last = stats
        return stats

    def loop(self, stop, period=900, first_delay=60):
        if stop.wait(first_delay):
            return
        while True:
            try:
                self.run_once()
            except Exception as e:  # noqa: BLE001
                import sys
                sys.stderr.write("alerts: %s\n" % type(e).__name__)
            if stop.wait(period):
                return
