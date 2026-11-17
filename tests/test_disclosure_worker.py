"""Сборщик раскрытий: разбор ленты и сообщения, wanted, цикл live/история с поддельной сетью, чтение через сервер. Офлайн."""
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402
import disclosure_worker as dw  # noqa: E402
import tinvest_server as ts  # noqa: E402
from test_server import Fx  # noqa: E402

FX = os.path.join(ROOT, "tests", "fixtures", "disclosure")
T = _load.load()
DAY_HTML = open(os.path.join(FX, "azipi_day_16112026_p1.html"), encoding="utf-8").read()
MSG_HTML = open(os.path.join(FX, "azipi_message_afks.html"), encoding="utf-8").read()
PAID = "Выплаченные доходы по эмиссионным ценным бумагам эмитента"
ISIN = "RU000A10B024"
ITEM = ('<div class="item"><div class="date">\n%s\t</div><div class="link"><a href="/messages/%d/arhive-2026/" alt="x">%s</a></div>'
        '<div class="info">Организация: <b>%s</b><br />ИНН организации: <b>%s</b><br />Дата события: <b>%s</b></div></div>')
MSK_NOW = lambda: datetime(2026, 11, 17, 10, 0, tzinfo=dw.MSK)  # noqa: E731


def feed_page(items, page, size, day):
    chunk = items[(page - 1) * size:page * size]
    last = max(1, int(math.ceil(len(items) / float(size))))
    d = "%s.%s.%s" % (day[8:], day[5:7], day[:4])
    body = "".join(ITEM % (d + " 12:00:00", i, t, "Орг", inn, d) for i, t, inn in chunk)
    pager = "".join('<a href="?PAGEN_2=%d">%d</a>' % (n, n) for n in range(1, last + 1))
    return "<html><body>%s<div class=\"nav\">%s</div></body></html>" % (body, pager)


class FakeNet:
    """Поддельные ISS и azipi. feed: {день ISO: [(id, заголовок, ИНН)]}. Хранит журнал URL."""

    def __init__(self, feed, size=3):
        self.feed, self.size, self.log = {k: list(v) for k, v in feed.items()}, size, []

    def __call__(self, url):
        self.log.append(url)
        if "iss.moex.com" in url:
            start = int(url.rsplit("start=", 1)[1])
            data = [["AFKS1", "АФК Система 002Р-01", ISIN, 1, 1, "ПАО АФК Система", "7703104630"], ["X", "x", "RU0", 1, 2, "Без ИНН", ""]] if start == 0 else []
            return json.dumps({"securities": {"columns": ["secid", "shortname", "isin", "is_traded", "emitent_id", "emitent_title", "emitent_inn"], "data": data}})
        if "/messages/list/" in url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            d = q["MESSAGE_BY_DAY"][0]
            day = "%s-%s-%s" % (d[6:], d[3:5], d[:2])
            return feed_page(self.feed.get(day, []), int(q["PAGEN_2"][0]), self.size, day)
        if "/messages/" in url:
            return MSG_HTML
        raise AssertionError(url)

    def feed_urls(self, day=None):
        return [u for u in self.log if "/messages/list/" in u and (day is None or "day-%s.%s.%s" % (day[8:], day[5:7], day[:4]) in u)]


def mkworker(net, since="2015-01-01", d=None):
    d = d or tempfile.mkdtemp(prefix="dw_")
    db = dw.open_db(d)
    return dw.Worker(db, net, T, "ver1", since, 60, now=MSK_NOW), d


FEED = {"2026-11-17": [(5000, "Прочее", "1111111111"), (4999, "Стоимость чистых активов", "2222222222"), (4998, "Другое", "3333333333"),
                       (4997, "Ещё", "4444444444")],
        "2026-11-16": [(4608500, PAID, "7703104630"), (4608499, PAID, "9999999999"), (4608498, "Неисполнение обязательств эмитента", "7707600245"),
                       (4608497, "Годовой отчёт", "7703104630")],
        "2026-11-13": [(4600001, "Годовой отчёт", "7703104630")]}


class ParseTests(unittest.TestCase):
    def test_feed_page(self):
        items, last = dw.parse_feed(DAY_HTML)
        self.assertEqual((len(items), last), (10, 64))
        a = items[0]
        self.assertEqual((a["id"], a["inn"], a["ts"], a["event_date"]), (4608498, "7707600245", "2026-11-16 20:00:00", "2026-11-13"))
        self.assertEqual(a["org"], 'Публичное акционерное общество "МГКЛ"')
        self.assertTrue(a["title"].startswith("Неисполнение обязательств эмитента"))
        self.assertEqual(len({i["id"] for i in items}), 10)
        self.assertTrue(all(i["inn"].isdigit() and i["ts"].startswith("2026-11-16") for i in items))

    def test_message_body(self):
        body = dw.extract_body(MSG_HTML, T, PAID)
        self.assertTrue(body.startswith("1. Общие сведения"))
        for bad in ("Карта сайта", "Настоящее сообщение предоставлено", "АЗИПИ"):
            self.assertNotIn(bad, body)
        ex = T.dc_extract(body, PAID, {})
        self.assertEqual(ex["kind"], "coupon_paid")
        f = ex["facts"][0]
        self.assertEqual((f["isin"], f["total"], f["per_bond"], f["qty"]), (ISIN, 80620552.40, 14.86, 5425340))

    def test_wanted(self):
        for t in (PAID, "Начисленные доходы по ценным бумагам", "Неисполнение обязательств эмитента перед владельцами",
                  "Сообщение об итогах приобретения облигаций", "Приобретение (наступление оснований для приобретения) облигаций",
                  "о досрочном погашении", "Погашение облигаций"):
            self.assertTrue(dw.wanted_title(t), t)
        for t in ("Годовой отчёт", "Стоимость чистых активов", ""):
            self.assertFalse(dw.wanted_title(t), t)


class WorkerTests(unittest.TestCase):
    def tearDown(self):
        shutil.rmtree(getattr(self, "d", ""), ignore_errors=True)

    def test_live_cycle_idempotent(self):
        net = FakeNet(FEED)
        w, self.d = mkworker(net)
        w.live_cycle()
        q = lambda s: w.db.execute(s).fetchall()  # noqa: E731
        self.assertEqual(q("SELECT COUNT(*) FROM universe"), [(1,)])
        self.assertEqual(q("SELECT COUNT(*) FROM feed"), [(8,)])
        self.assertEqual(q("SELECT id FROM feed WHERE wanted=1"), [(4608500,)])      # 9999999999 не в универсуме, 7707600245 тоже
        self.assertEqual(q("SELECT fetched FROM feed WHERE id=4608500"), [(1,)])
        r = q("SELECT doc_id, isin, inn, kind, due_date, conf, parser_ver FROM facts")
        self.assertEqual(r, [(4608500, ISIN, "7703104630", "coupon_paid", "2026-11-16", 1.0, "ver1")])
        d = json.loads(q("SELECT data FROM facts")[0][0])
        self.assertEqual((d["total"], d["per_bond"], d["qty"]), (80620552.4, 14.86, 5425340))
        self.assertEqual(q("SELECT status, items FROM days"), [("done", 4)])
        n_msgs = len([u for u in net.log if u.endswith("/messages/4608500/")])
        net.log.clear()
        w.live_cycle()                                           # второй прогон: ничего нового
        self.assertEqual(q("SELECT COUNT(*) FROM feed"), [(8,)])
        self.assertEqual((q("SELECT COUNT(*) FROM docs"), q("SELECT COUNT(*) FROM facts")), ([(1,)], [(1,)]))
        self.assertEqual(len(net.feed_urls("2026-11-17")), 1)    # остановка на первой же странице с известными id
        self.assertEqual(net.feed_urls("2026-11-16"), [])        # вчера уже дособрано
        self.assertEqual((n_msgs, [u for u in net.log if "/messages/4608500/" in u]), (1, []))
        # новое сообщение сверху ленты: добирается одной-двумя страницами
        net.feed["2026-11-17"].insert(0, (5001, PAID, "7703104630"))
        w.live_cycle()
        self.assertEqual(q("SELECT COUNT(*) FROM feed"), [(9,)])
        self.assertEqual(q("SELECT COUNT(*) FROM facts"), [(2,)])

    def test_backfill_marks_days_and_resumes(self):
        net = FakeNet(FEED)
        w, self.d = mkworker(net, since="2026-11-11")
        w.live_cycle()
        steps = [w.backfill_step() for _ in range(2)]            # 16 и 15 уже/пусто: идём по дням 15, 14
        self.assertEqual(steps, ["ok", "ok"])
        days = dict(w.db.execute("SELECT day, status FROM days").fetchall())
        self.assertEqual(days, {"2026-11-16": "done", "2026-11-15": "done", "2026-11-14": "done"})
        w2 = dw.Worker(dw.open_db(self.d), net, T, "ver1", "2026-11-11", 60, now=MSK_NOW)     # перезапуск: продолжает с 13-го
        net.log.clear()
        self.assertEqual(w2.backfill_step(), "ok")
        self.assertEqual(len(net.feed_urls("2026-11-15")), 0)
        self.assertEqual(len(net.feed_urls("2026-11-13")), 1)
        self.assertEqual(w2.db.execute("SELECT COUNT(*) FROM feed WHERE day='2026-11-13'").fetchone()[0], 1)
        while w2.backfill_step() == "ok":
            pass
        self.assertEqual(w2.db.execute("SELECT MIN(day) FROM days").fetchone()[0], "2026-11-11")
        self.assertIsNone(dw.get_meta(w2.db, "archive_end"))     # остановились по --since, а не по концу архива
        self.assertEqual(w2.backfill_step(), "end")

    def test_empty_days_end_of_archive(self):
        net = FakeNet({"2026-11-16": FEED["2026-11-16"]})
        w, self.d = mkworker(net, since="2015-01-01")
        w.live_cycle()
        n = 0
        while w.backfill_step() == "ok":
            n += 1
        self.assertEqual(n, dw.EMPTY_STOP)
        self.assertTrue(dw.get_meta(w.db, "archive_end"))
        net.log.clear()
        self.assertEqual(w.backfill_step(), "end")
        self.assertEqual(net.log, [])                            # после конца архива запросов нет
        st = dw.stats(w.db, 1.5, "2015-01-01", MSK_NOW().date())
        self.assertEqual((st["universe"], st["wanted"], st["fetched"], st["facts"], st["eta_sec"]), (1, 1, 1, {"coupon_paid": 1}, 0))

    def test_reparse_and_parse_error(self):
        net = FakeNet(FEED)
        w, self.d = mkworker(net)
        w.live_cycle()
        w.pver = "ver2"
        w.reparse()
        self.assertEqual(w.db.execute("SELECT COUNT(*), MIN(parser_ver) FROM facts").fetchone(), (1, "ver2"))

        class Bad:
            def dc_extract(self, *a):
                raise RuntimeError("boom")

            doc_text = staticmethod(T.doc_text)
        w.lib = Bad()
        w.reparse()
        self.assertEqual(w.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0], 0)
        self.assertIn("boom", w.db.execute("SELECT err FROM feed WHERE id=4608500").fetchone()[0])


class ServerReadTests(unittest.TestCase):
    def setUp(self):
        self.f = Fx()

    def tearDown(self):
        self.f.close()

    def get(self, path):
        code, body, _ = self.f.call(None, path=path)
        return code, json.loads(body)

    def test_missing_db_is_empty(self):
        self.assertEqual(self.get("/v1/parsed/disclosure/facts?isin=" + ISIN), (200, {"ok": True, "v": 1, "data": []}))
        self.assertEqual(self.get("/v1/parsed/disclosure/defaults")[1]["data"], [])
        self.assertEqual(self.get("/v1/parsed/disclosure/status")[1]["data"], {})

    def test_facts_defaults_status(self):
        w, d = mkworker(FakeNet(FEED), d=self.f.tmp)
        w.live_cycle()
        code, r = self.get("/v1/parsed/disclosure/facts?isin=" + ISIN)
        self.assertEqual(code, 200)
        x = r["data"][0]
        self.assertEqual((x["doc_id"], x["isin"], x["kind"], x["url"], x["published"]),
                         (4608500, ISIN, "coupon_paid", "https://e-disclosure.azipi.ru/messages/4608500/", "2026-11-16 12:00:00"))
        self.assertEqual((x["data"]["total"], x["data"]["qty"]), (80620552.4, 5425340))
        self.assertEqual(len(self.get("/v1/parsed/disclosure/facts?inn=7703104630&kind=coupon_paid")[1]["data"]), 1)
        self.assertEqual(self.get("/v1/parsed/disclosure/facts?isin=" + ISIN + "&kind=default")[1]["data"], [])
        self.assertEqual(self.get("/v1/parsed/disclosure/facts?isin=bad")[0], 400)
        self.assertEqual(self.get("/v1/parsed/disclosure/facts")[0], 400)
        self.assertEqual(self.get("/v1/parsed/disclosure/defaults?since=2026-01-01")[1]["data"], [])
        st = self.get("/v1/parsed/disclosure/status")[1]["data"]
        self.assertEqual((st["universe"], st["docs"], st["facts"]), (1, 1, {"coupon_paid": 1}))
        w.db.close()


if __name__ == "__main__":
    unittest.main()
