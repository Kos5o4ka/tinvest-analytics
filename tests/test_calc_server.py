"""Готовые расчёты сервера (calc_worker): приложение берёт их вместо своего долгого расчёта, а без сервера считает само."""
import os
import sys
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import _load  # noqa: E402
import calc_worker  # noqa: E402


class Register(unittest.TestCase):
    def test_new_calcs_registered_below_max_age(self):
        lib = types.SimpleNamespace(fng_compute=lambda: {}, pv_compute=lambda: {}, weekly_inflation_calc=lambda: {})
        calc_worker.CALCS.clear()
        calc_worker.register_calcs(lib)
        self.assertEqual(set(calc_worker.CALCS), {"fng", "pri_vol", "inflation"})
        for name, (_fn, period) in calc_worker.CALCS.items():
            self.assertLess(period, 3600, name)


class ClientTakesServerResult(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load.load()

    def setUp(self):
        self.m._pv.update(res=None, t=0, running=False, err=None)

    def test_primary_volumes_from_server(self):
        m = self.m
        res = {"rows": [{"secid": "X"}], "today": "2024-01-01"}
        with mock.patch.object(m, "ds_calc", return_value=(res, time.time() - 10)), \
                mock.patch.object(m.threading, "Thread", side_effect=AssertionError("локальный расчёт не нужен")):
            out = m.primary_volumes_payload()
        self.assertEqual(out["rows"], [{"secid": "X"}])

    def test_primary_volumes_stale_server_result_ignored(self):
        m = self.m
        started = []
        fake = types.SimpleNamespace(start=lambda: started.append(1))
        with mock.patch.object(m, "ds_calc", return_value=({"rows": []}, time.time() - 7200)), \
                mock.patch.object(m.threading, "Thread", return_value=fake):
            m.primary_volumes_payload()
        self.assertEqual(started, [1])
        m._pv["running"] = False

    def test_inflation_from_server_and_fallback(self):
        m = self.m
        pay = {"years": {"2024": [{"pct": 0.1}]}, "empty": False}
        with mock.patch.object(m, "ds_calc", return_value=(pay, time.time())), \
                mock.patch.object(m.threading, "Thread", side_effect=AssertionError("локальная докачка не нужна")):
            out = m.weekly_inflation()
        self.assertEqual((out["years"], out["loading"]), (pay["years"], False))
        started = []
        with mock.patch.object(m, "ds_calc", return_value=None), \
                mock.patch.object(m.threading, "Thread", return_value=types.SimpleNamespace(start=lambda: started.append(1))):
            m._wi.update(running=False, last=0)
            m.weekly_inflation()
        self.assertEqual(started, [1])
        m._wi["running"] = False


if __name__ == "__main__":
    unittest.main()
