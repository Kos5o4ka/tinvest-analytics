"""Сопоставление названий эмитентов с рейтингами, миграция v1→v2 и свежесть кэша эмитентов."""
import os
import unittest
from datetime import date, timedelta

from tests._load import load

T = load()
KEYS = ("ratings_v1", "ratings_site_v1", "ratings_expert_v1", "ratings_v3", "ratings_v2", "ratings_site_v2", "ratings_expert_v2")


def _item(issuer, rating="A+", agency="АКРА"):
    return {"issuer": issuer, "agency": agency, "level": "issuer", "rating": rating, "outlook": "", "date": date.today().isoformat()}


FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "ru_ratings_page.html")


def _posts():
    with open(FIX, encoding="utf-8") as f:
        ids, posts = T.tg_parse_page(f.read(), "ru_ratings")
    return {p[0]: p for p in posts}


def _parse(pid):
    _, iso, txt, links = _posts()[pid]
    return T.parse_ru_ratings_post(txt, links, iso)


class RuRatingsParse(unittest.TestCase):
    def test_page_and_links(self):
        ids, posts = T.tg_parse_page(open(FIX, encoding="utf-8").read(), "ru_ratings")
        self.assertEqual(len(ids), 10)
        self.assertEqual(T.tg_parse_page(open(FIX, encoding="utf-8").read(), "issuerRatings")[0], [])      # чужой канал
        self.assertIn("https://raexpert.ru/releases/2026/nov20", _posts()[3082][3])

    def test_expert_ra(self):
        r = _parse(3082)
        self.assertEqual((r["agency"], r["issuer"], r["rating"], r["outlook"], r["date"], r["level"]),
                         ("Эксперт РА", "ОГК-2", "AAA", "стабильный", "2026-11-20", "issuer"))
        self.assertEqual(r["url"], "https://raexpert.ru/releases/2026/nov20")

    def test_expert_outlook_change(self):
        r = _parse(3091)
        self.assertEqual((r["rating"], r["outlook"]), ("BB-", "развивающийся"))

    def test_acra_caps_bond_level(self):
        r = _parse(3092)
        self.assertEqual((r["agency"], r["issuer"], r["rating"], r["url"]),
                         ("АКРА", "А7", "AA", "https://www.acra-ratings.ru/press-releases/7527/"))

    def test_nkr_dot_ru(self):
        r = _parse(3095)
        self.assertEqual((r["agency"], r["issuer"], r["rating"], r["date"]), ("НКР", "РДВ Технолоджи", "B+", "2026-11-23"))
        self.assertTrue(r["url"].startswith("https://ratings.ru/"))

    def test_nra_pipe_ru(self):
        r = _parse(3084)
        self.assertEqual((r["agency"], r["rating"], r["outlook"]), ("НРА", "BB+", "стабильный"))

    def test_withdrawn(self):
        r = _parse(3085)
        self.assertTrue(r["withdrawn"])
        self.assertEqual((r["agency"], r["issuer"]), ("Эксперт РА", "Элит Строй"))
        self.assertNotIn("rating", r)

    def test_region_from_structured_lines(self):
        r = _parse(2690)
        self.assertEqual((r["issuer"], r["rating"]), ("Нижегородская область", "A"))

    def test_dropped_posts(self):
        for pid in (2982, 2769, 2894):                       # ESG, НПФ (некредитный), аналитика без рейтинга
            self.assertIsNone(_parse(pid), pid)

    def test_action_from_ru_post(self):
        log = {"events": []}
        _, iso, txt, links = _posts()[3085]
        T.rating_log_add(log, 3085, iso, txt, "ru_ratings", links)
        e = log["events"][0]
        self.assertEqual((e["action"], e["prev"], e["src"], e["date"]), ("отозван", "BBB-", "ru_ratings", "2026-11-20"))
        self.assertEqual(e["url"], "https://raexpert.ru/releases/2026/nov20b")


class SafeUrl(unittest.TestCase):
    def test_whitelist(self):
        ok = ["https://www.acra-ratings.ru/press-releases/1/", "https://raexpert.ru/x", "https://ratings.ru/a",
              "https://www.ra-national.ru/p", "https://t.me/ru_ratings/1"]
        for u in ok:
            self.assertEqual(T.rt_safe_url(u), u)
        for u in ["http://raexpert.ru/x", "https://evilraexpert.ru/x", "https://raexpert.ru.evil.com/x",
                  "javascript:alert(1)", "https://user@raexpert.ru/x", "https://example.com", "", None, "//t.me/x"]:
            self.assertEqual(T.rt_safe_url(u), "", u)


class Merge(unittest.TestCase):
    def rec(self, src, d, r="A", url="u"):
        return {"issuer": "X", "agency": "АКРА", "level": "issuer", "rating": r, "outlook": "", "date": d, "post": 1,
                "src": src, "url": url}

    def test_fresher_wins_equal_prefers_ru(self):
        it = {}
        T.rt_merge(it, "k", self.rec("issuerRatings", "2026-11-01", "A", ""))
        T.rt_merge(it, "k", self.rec("ru_ratings", "2026-11-01", "A+", "https://raexpert.ru/a"))
        self.assertEqual(it["k"]["src"], "ru_ratings")                      # равная дата
        T.rt_merge(it, "k", self.rec("issuerRatings", "2026-11-01", "B", ""))
        self.assertEqual(it["k"]["rating"], "A+")                           # равная дата — ru_ratings остаётся
        T.rt_merge(it, "k", self.rec("issuerRatings", "2026-11-05", "A", ""))
        self.assertEqual((it["k"]["src"], it["k"]["date"]), ("issuerRatings", "2026-11-05"))
        self.assertEqual(it["k"]["url"], "")                                # другой рейтинг — ссылку не наследуем
        T.rt_merge(it, "k", self.rec("ru_ratings", "2026-11-03", "BB", "https://raexpert.ru/b"))
        self.assertEqual(it["k"]["date"], "2026-11-05")                     # более старое из другого канала отброшено

    def test_url_inherited_for_same_rating(self):
        it = {}
        T.rt_merge(it, "k", self.rec("ru_ratings", "2026-11-01", "A", "https://raexpert.ru/a"))
        T.rt_merge(it, "k", self.rec("issuerRatings", "2026-11-02", "A", ""))
        self.assertEqual((it["k"]["src"], it["k"]["url"]), ("issuerRatings", "https://raexpert.ru/a"))

    def test_log_dedupe_prefers_ru(self):
        base = {"agency": "АКРА", "issuer": "Эмитент", "level": "issuer", "action": "подтверждён", "rating": "A",
                "prev": None, "tokens": ["эмитент"], "outlook": ""}
        today = date.today()
        log = {"events": [dict(base, post=5, date=(today - timedelta(days=1)).isoformat(), src="issuerRatings"),
                          dict(base, post=9, date=today.isoformat(), src="ru_ratings"),
                          dict(base, post=7, date=(today - timedelta(days=40)).isoformat(), src="issuerRatings")]}
        T.rating_log_trim(log)
        self.assertEqual(sorted((e["src"], e["post"]) for e in log["events"]), [("issuerRatings", 7), ("ru_ratings", 9)])


class UrlInRatingFor(unittest.TestCase):
    def setUp(self):
        for k in KEYS:
            T.store().put(k, {})
        T._rt_idx.clear()

    tearDown = setUp

    def test_url_post_and_none(self):
        a = dict(_item("Альфа Эмитент", "A+", "АКРА"), post=5, src="ru_ratings", url="https://www.acra-ratings.ru/press-releases/9/")
        b = dict(_item("Альфа Эмитент", "A", "Эксперт РА"), post=77)                  # старая запись: канал по умолчанию
        c = _item("Альфа Эмитент", "BBB", "НКР")                                      # сайт НКР: поста нет
        T.store().put(T.RT_KEY, {"items": {"a|АКРА|issuer": a, "a|Эксперт РА|issuer": b, "a|НКР|issuer": c}, "updated": 1})
        r = T.rating_for("Альфа Эмитент 001Р-01")
        by = {x["agency"]: x for x in r["all"]}
        self.assertEqual(by["АКРА"]["url"], "https://www.acra-ratings.ru/press-releases/9/")
        self.assertEqual(by["Эксперт РА"]["url"], "https://t.me/issuerRatings/77")
        self.assertIsNone(by["НКР"]["url"])
        self.assertEqual((r["agency"], r["url"], r["src"]), ("НКР", None, None))      # худший — НКР BBB

    def test_unsafe_url_dropped(self):
        a = dict(_item("Бета Эмитент"), url="https://evil.example/x")
        T.store().put(T.RT_KEY, {"items": {"b|АКРА|issuer": a}, "updated": 1})
        self.assertIsNone(T.rating_for("Бета Эмитент 001")["url"])

    def test_v2_fallback_chain(self):
        T.store().put("ratings_v2", {"items": {"k": _item('ООО "Гамма"')}, "updated": 1})
        self.assertEqual(T.rating_for("Гамма 001Р-01")["v"], "A+")


class Monitor(unittest.TestCase):
    def test_alert_url_press_release_or_post(self):
        ev = {"agency": "АКРА", "issuer": "Эмитент", "level": "issuer", "action": "понижен", "rating": "BBB", "prev": "A",
              "outlook": "", "watch": "", "tokens": ["эмитент"], "date": date.today().isoformat(), "post": 5}
        rows = [({"isin": "RU1", "name": "Эмитент 001"}, [frozenset(["эмитент"])])]
        cut = (date.today() - timedelta(days=30)).isoformat()
        a1 = T._mon_rating_alerts(rows, [dict(ev, src="ru_ratings", url="https://raexpert.ru/r")], cut)[0]
        self.assertEqual(a1["url"], "https://raexpert.ru/r")
        a2 = T._mon_rating_alerts(rows, [dict(ev, src="ru_ratings", url="")], cut)[0]
        self.assertEqual(a2["url"], "https://t.me/ru_ratings/5")


class NameWords(unittest.TestCase):
    def test_alnum_issuer_kept(self):
        self.assertEqual(T.name_words('ООО "А101"'), ("а101",))
        self.assertEqual(T.name_words("А101 001Р-01"), ("а101",))

    def test_series_ignored(self):
        self.assertEqual(T.name_words("Интерлизинг 001Р-11"), ("интерлизинг",))
        self.assertEqual(T.name_words("БО-П01"), ())
        self.assertEqual(T.name_words("001Р-11"), ())
        self.assertEqual(T.name_words("ПСБ Лизинг БО-П03"), ("псб", "лизинг"))


class Migration(unittest.TestCase):
    def setUp(self):
        for k in KEYS:
            T.store().put(k, {})
        T._rt_idx.clear()

    tearDown = setUp

    def test_v1_fallback_then_v2(self):
        T.store().put("ratings_v1", {"items": {"k": _item('ООО "А101"')}, "updated": 1})
        r = T.rating_for("А101 001Р-01")
        self.assertEqual(r and r["v"], "A+")
        s1 = T.ratings_stamp()
        T.store().put(T.RT_KEY, {"items": {"k2": _item("Другой эмитент", "BBB")}, "updated": 2})
        self.assertNotEqual(T.ratings_stamp(), s1)
        self.assertIsNone(T.rating_for("А101 001Р-01"))           # v2 непуст — v1 игнорируется
        self.assertEqual(T.rating_for("Другой эмитент 001Р-01")["v"], "BBB")

    def test_issuers_job_recomputed_on_new_ratings(self):
        import time
        calls = []
        orig = T._iss_portfolio
        T._iss_portfolio = lambda cfg, acc, job: calls.append(1) or {"rows": []}
        T._iss_jobs.clear()
        try:
            def run():
                T.issuers_payload({"token": "x", "sandbox": False}, "all", {}, False)
                for _ in range(100):
                    j = next(iter(T._iss_jobs.values()))
                    if j["state"] == "done":
                        break
                    time.sleep(0.02)
            run()
            run()
            self.assertEqual(len(calls), 1)                              # рейтинги те же — кэш жив
            T.store().put(T.RT_KEY, {"items": {"k": _item("Эмитент")}, "updated": 5})
            run()
            self.assertEqual(len(calls), 2)                              # рейтинги изменились — пересчёт
        finally:
            T._iss_portfolio = orig
            T._iss_jobs.clear()


if __name__ == "__main__":
    unittest.main()
