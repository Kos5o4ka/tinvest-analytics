"""Ставки: интерполяция сетки КБД, разбор сроков, форма ответа rates_payload (без сети)."""
import unittest
from datetime import date, timedelta

from tests._load import load

T = load()
GRID = {"0.25": 10.0, "1.0": 12.0, "2.0": 13.0, "5.0": 14.5, "10.0": 15.0}


def wd(n):
    """n-й рабочий день назад от сегодня (ISO)."""
    d = date.today()
    while n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


class Interp(unittest.TestCase):
    def test_exact_and_between(self):
        self.assertEqual(T.kbd_interp(GRID, 2), 13.0)
        self.assertAlmostEqual(T.kbd_interp(GRID, 3.5), 13.75)
        self.assertAlmostEqual(T.kbd_interp(GRID, 0.625), 11.0)

    def test_out_of_range_none(self):
        self.assertIsNone(T.kbd_interp(GRID, 0.1))
        self.assertIsNone(T.kbd_interp(GRID, 20))
        self.assertIsNone(T.kbd_interp({}, 2))

    def test_parse_terms(self):
        self.assertEqual(T.parse_rate_terms(None), [2.0])
        self.assertEqual(T.parse_rate_terms("10,1,2,2,0.1,99,x,5,5,5.5"), [1.0, 2.0, 5.0, 5.5, 10.0])
        self.assertEqual(len(T.parse_rate_terms("1,2,3,4,5,6,7,8")), 6)
        self.assertEqual(T.parse_rate_terms("0,100"), [2.0])


class Payload(unittest.TestCase):
    def setUp(self):
        self.st = T.store()
        self._rs, self._ks = T.rates_start, T.key_rate_series
        T.rates_start = lambda days: None
        T.key_rate_series = lambda: [[wd(30), 16.0]]

    def tearDown(self):
        T.rates_start, T.key_rate_series = self._rs, self._ks
        self.st.put(T.KBD_KEY, {})
        self.st.put(T.KBD_OLD_KEY, {})

    def test_shape_and_values(self):
        d1, d2 = wd(3), wd(1)
        self.st.put(T.KBD_KEY, {d1: GRID, d2: dict(GRID, **{"2.0": 13.5})})
        self.st.put(T.KBD_OLD_KEY, {})
        p = T.rates_payload(365, "2,5,3.5")
        self.assertEqual(p["terms"], [2.0, 3.5, 5.0])
        self.assertEqual(p["iso"], [d1, d2])
        self.assertEqual(set(p["kbd"]), {"2", "3.5", "5"})
        self.assertEqual(p["kbd"]["2"], [13.0, 13.5])
        self.assertEqual(p["kbd"]["5"], [14.5, 14.5])
        self.assertEqual(p["key"], [16.0, 16.0])
        self.assertTrue(p["loading"])       # в кэше мало дат

    def test_old_cache_fallback(self):
        d1, d2 = wd(3), wd(1)
        self.st.put(T.KBD_KEY, {d2: GRID})
        self.st.put(T.KBD_OLD_KEY, {d1: 12.7, d2: 99.0, wd(5): None})
        p = T.rates_payload(365, "2,10")
        self.assertEqual(p["iso"], [d1, d2])
        self.assertEqual(p["kbd"]["2"], [12.7, 13.0])       # d2 берётся из v2, а не из старого кэша
        self.assertEqual(p["kbd"]["10"], [None, 15.0])      # для старых значений другие сроки неизвестны

    def test_default_terms(self):
        self.st.put(T.KBD_KEY, {wd(1): GRID})
        p = T.rates_payload("365")
        self.assertEqual(list(p["kbd"]), ["2"])


if __name__ == "__main__":
    unittest.main()
