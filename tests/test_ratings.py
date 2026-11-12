"""Сопоставление названий эмитентов с рейтингами, миграция v1→v2 и свежесть кэша эмитентов."""
import unittest
from datetime import date

from tests._load import load

T = load()
KEYS = ("ratings_v1", "ratings_site_v1", "ratings_expert_v1", "ratings_v2", "ratings_site_v2", "ratings_expert_v2")


def _item(issuer, rating="A+", agency="АКРА"):
    return {"issuer": issuer, "agency": agency, "level": "issuer", "rating": rating, "outlook": "", "date": date.today().isoformat()}


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
