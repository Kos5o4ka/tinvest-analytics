import os
import unittest

from tests._load import load

T = load()


FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def make_pdf(text_hex):
    """Одностраничный PDF без сжатия: шрифт F1 с ToUnicode (код 1..n -> символы)."""
    chars = sorted(set(text_hex))
    cm = "1 beginbfchar\n" + "".join("<%04X> <%04X>\n" % (i + 1, ord(c)) for i, c in enumerate(chars)) + "endbfchar"
    codes = "".join("%04X" % (chars.index(c) + 1) for c in text_hex)
    content = "BT /F1 12 Tf [<%s>] TJ ET" % codes
    objs = {1: "<< /Type /Page /Resources << /Font << /F1 2 0 R >> >> /Contents 4 0 R >>",
            2: "<< /Type /Font /Subtype /Type0 /ToUnicode 3 0 R >>",
            3: "<< /Length %d >>\nstream\n%s\nendstream" % (len(cm), cm),
            4: "<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)}
    return ("%PDF-1.5\n" + "".join("%d 0 obj\n%s\nendobj\n" % (k, v) for k, v in objs.items()) + "%%EOF").encode()


class Phase2(unittest.TestCase):
    def test_cy(self):
        # 40 руб за 182 дня на номинал 1000, цена 96% -> 40*365/182/1000/0.96
        self.assertAlmostEqual(T.bond_cy(40, 182, 1000, 96), 8.36, places=2)
        self.assertIsNone(T.bond_cy(None, 182, 1000, 96))
        self.assertIsNone(T.bond_cy(40, 0, 1000, 96))

    def test_chg_fallback(self):
        self.assertEqual(T.bond_chg({"LASTCHANGEPRCNT": -1.234}, {}, 100), -1.23)
        self.assertEqual(T.bond_chg({"LAST": 99}, {"PREVPRICE": 100}, 99), -1.0)
        self.assertEqual(T.bond_chg({}, {}, 99), 0.0)

    def test_liq_tiers(self):
        rows = [{"turn": t} for t in (100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 0)]
        T.liq_tiers(rows)
        tiers = [r["liq"] for r in rows]
        self.assertEqual(tiers[:2], ["L1", "L1"])
        self.assertEqual(tiers[2:6], ["L2"] * 4)
        self.assertEqual(tiers[6:], ["L3"] * 5)

    def test_movers(self):
        rows = [{"id": "A", "isin": "A", "name": "a", "chg": -3.0, "price": 90, "turn": 5, "trades": 2, "rating": "A"},
                {"id": "B", "isin": "B", "name": "b", "chg": 2.0, "price": 91, "turn": 6, "trades": 3, "rating": None},
                {"id": "C", "isin": "C", "name": "c", "chg": 0, "price": 92, "turn": 7, "trades": 4, "rating": None},
                {"id": "D", "isin": "D", "name": "d", "chg": -1.0, "price": 93, "turn": 8, "trades": 5, "rating": None}]
        old = dict(T._scr)
        T._scr.update(t=T.time.time(), rows=rows)
        try:
            m = T.bond_movers(2)
        finally:
            T._scr.update(old)
        self.assertEqual(m["total"], 3)
        self.assertEqual([r["isin"] for r in m["down"]], ["A", "D"])
        self.assertEqual([r["isin"] for r in m["up"]], ["B", "D"])

    def test_note_parse_html_fixture(self):
        data = open(os.path.join(FIX, "rosstat_weekly_note.html"), "rb").read()
        r = T.weekly_note_parse(data)
        self.assertEqual(r, {"date": "2026-11-09", "pct": 0.12, "ytd": 6.33})

    def test_note_parse_forms(self):
        t = "<p>За период с 27 января по 2 февраля 2026 г. индекс потребительских цен, по оценке Росстата, составил 99,95%.</p>"
        self.assertEqual(T.weekly_note_parse(t.encode())["pct"], -0.05)
        t2 = "<p>За период с 3 по 9 июня 2019 года цены выросли на 0,04%.</p>"
        self.assertEqual(T.weekly_note_parse(t2.encode()), {"date": "2019-06-09", "pct": 0.04, "ytd": None})
        self.assertIsNone(T.weekly_note_parse("<p>ничего</p>".encode()))

    def test_note_parse_pdf(self):
        txt = "ОБ ОЦЕНКЕ с 3 по 9 ноября 202 6 г. индекс потребительских цен, по оценке Росстата, составил 100,12 %, с начала года - 106,33 %"
        r = T.weekly_note_parse(make_pdf(txt))
        self.assertEqual((r["date"], r["pct"], r["ytd"]), ("2026-11-09", 0.12, 6.33))

    def test_listing_parse(self):
        items = T.weekly_listing_parse(open(os.path.join(FIX, "rosstat_listing.html"), encoding="utf8").read())
        self.assertGreaterEqual(len(items), 2)
        self.assertTrue(all(u.startswith("https://rosstat.gov.ru/") for u, _ in items))
        self.assertTrue(all("нефтепродукты" not in t for _, t in items))

    def test_avg_by_week(self):
        rows = [{"year": 2019, "week": 3, "pct": 0.1}, {"year": 2020, "week": 3, "pct": 0.3}, {"year": 2022, "week": 3, "pct": 9}]
        avg, ys = T.weekly_avg_by_week(rows)
        self.assertEqual(avg, [(3, 0.2)])
        self.assertEqual(ys, [2019, 2020])

    def test_collect_and_payload(self):
        def page(*links):
            return "".join('<a href="/n/%s.html">Об оценке индекса потребительских цен с 1 по 7 мая 2026 года</a>' % l for l in links).encode()

        def note(day, v):
            return ("<p>за период с 1 по %d мая 2026 г. индекс потребительских цен составил %s%%</p>" % (day, v)).encode()
        web = {T.ROSSTAT_NEWS: page("a", "b"), T.ROSSTAT_NEWS + "?page=2": page("c", "dead"), T.ROSSTAT_NEWS + "?page=3": b"",
               "https://rosstat.gov.ru/n/a.html": note(14, "100,10"), "https://rosstat.gov.ru/n/b.html": note(7, "100,20"),
               "https://rosstat.gov.ru/n/c.html": note(1, "100,05")}

        def fetch(u):
            if u not in web:
                raise OSError("404")
            return web[u]
        saved = {}
        old = T.store().get(T._WI_KEY)
        try:
            T.store().put(T._WI_KEY, {})
            st = T.weekly_collect(fetch=fetch, pace=0, deep=True, save=lambda s: saved.update(s))
            self.assertEqual(sorted(st["weeks"]), ["2026-05-01", "2026-05-07", "2026-05-14"])
            self.assertEqual(st["dead"], ["https://rosstat.gov.ru/n/dead.html"])
            self.assertTrue(st["deep"])
            p = T.weekly_payload(st)
            self.assertFalse(p["empty"])
            self.assertEqual([r["pct"] for r in p["years"]["2026"]], [0.05, 0.2, 0.1])
            self.assertEqual(p["avg"], [])
            # повторный обход свежих страниц ничего не докачивает и не трогает мёртвые ссылки
            store_st = dict(st)
            T.store().put(T._WI_KEY, store_st)
            n = []
            T.weekly_collect(fetch=lambda u: (n.append(u), fetch(u))[1], pace=0)
            self.assertEqual(n, [T.ROSSTAT_NEWS])
        finally:
            T.store().put(T._WI_KEY, old or {})

    def test_server_allows_rosstat(self):
        import importlib.util
        import os
        spec = importlib.util.spec_from_file_location("tsrv_p2", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server", "tinvest_server.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertIn("rosstat.gov.ru", m.ALLOWED_HOSTS)
        self.assertTrue(any(h == "rosstat.gov.ru" for h, *_ in m.RULES))


if __name__ == "__main__":
    unittest.main()
