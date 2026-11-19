"""Серверные расчёты: /v1/parsed/calc/<имя>, воркер calc_worker.py и клиентский fng_payload() с запасным локальным расчётом. Офлайн."""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _load  # noqa: E402
import calc_worker as cw  # noqa: E402
import tinvest_server as ts  # noqa: E402
from test_server import Fx  # noqa: E402

M = _load.load()
PAYLOAD = {"value": 61, "label": "Жадность", "ts": "2026-11-18", "components": [], "history": [], "prev": {}, "low_conf": False}


def put_calc(fx, name, t, data=None):
    d = os.path.join(fx.tmp, "calc")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
        json.dump({"t": t, "data": PAYLOAD if data is None else data}, f)


class ServerCalc(unittest.TestCase):
    def setUp(self):
        self.f = Fx()

    def tearDown(self):
        self.f.close()

    def get(self, name):
        st, body, _ = self.f.call(None, path="/v1/parsed/calc/" + name)
        return st, json.loads(body)

    def test_fresh(self):
        put_calc(self.f, "fng", self.f.now[0] - 60)
        st, j = self.get("fng")
        self.assertEqual(st, 200)
        self.assertTrue(j["ok"])
        self.assertEqual(j["v"], ts.PARSED_V)
        self.assertEqual(j["data"], PAYLOAD)
        self.assertEqual(j["t"], self.f.now[0] - 60)

    def test_missing_unknown_stale(self):
        self.assertEqual(self.get("fng")[0], 404)
        put_calc(self.f, "old", self.f.now[0] - ts.CALC_MAX_AGE - 1)
        st, j = self.get("old")
        self.assertEqual(st, 404)
        self.assertFalse(j["ok"])
        self.assertEqual(self.get("nope")[0], 404)

    def test_bad_names(self):
        put_calc(self.f, "fng", self.f.now[0])
        for nm in ("../x", "..%2Fcalc%2Ffng", "FNG", "fng.json", "a/b", "%2e%2e%2fcalc_home"):
            st, _ = self.get(nm)
            self.assertEqual(st, 404, nm)
        self.assertEqual(self.f.app.parsed("calc/../x", {})[0], 404)
        self.assertEqual(self.f.app.parsed("calc/", {})[0], 404)

    def test_broken_file(self):
        d = os.path.join(self.f.tmp, "calc")
        os.makedirs(d)
        with open(os.path.join(d, "bad.json"), "w") as f:
            f.write("{не json")
        self.assertEqual(self.get("bad")[0], 404)


class Worker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tcalc_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self):
        return os.path.join(self.tmp, "calc", "x.json")

    def test_write_and_replace(self):
        self.assertTrue(cw.run_calc(self.tmp, "x", lambda: {"a": 1}))
        with open(self.path(), encoding="utf-8") as f:
            j = json.load(f)
        self.assertEqual(j["data"], {"a": 1})
        self.assertGreater(j["t"], 1e9)
        self.assertTrue(cw.run_calc(self.tmp, "x", lambda: {"a": 2}))
        with open(self.path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["data"], {"a": 2})
        self.assertEqual(os.listdir(os.path.dirname(self.path())), ["x.json"])        # временных файлов не осталось

    def test_failure_keeps_old(self):
        cw.run_calc(self.tmp, "x", lambda: {"a": 1})

        def boom():
            raise RuntimeError("нет сети")
        self.assertFalse(cw.run_calc(self.tmp, "x", boom))
        with open(self.path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["data"], {"a": 1})

    def test_unserializable_keeps_old(self):
        cw.run_calc(self.tmp, "x", lambda: {"a": 1})
        self.assertFalse(cw.run_calc(self.tmp, "x", lambda: {"a": object()}))
        with open(self.path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["data"], {"a": 1})
        self.assertEqual(os.listdir(os.path.dirname(self.path())), ["x.json"])

    def test_loop_once_and_registry(self):
        import threading
        cw.loop(self.tmp, {"x": (lambda: {"k": 1}, 900)}, threading.Event(), once=True)
        self.assertTrue(os.path.exists(self.path()))

        class Lib:
            fng_compute = staticmethod(lambda: {})
        cw.CALCS.clear()
        cw.register_calcs(Lib)
        self.assertIn("fng", cw.CALCS)
        cw.CALCS.clear()


class WorkerStopAndProgress(unittest.TestCase):
    """Долгий расчёт: воркер пишет ход расчёта в журнал и сразу останавливается по сигналу (systemd не ждёт 90 с)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tcalc_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.old = cw.PROGRESS_EVERY
        cw.PROGRESS_EVERY = 0.05
        self.addCleanup(setattr, cw, "PROGRESS_EVERY", self.old)

    def test_stop_during_long_calc(self):
        import threading
        import time as _t
        stop, release = threading.Event(), threading.Event()

        def slow():
            release.wait(5)
            return {"a": 1}
        threading.Timer(0.15, stop.set).start()
        t0 = _t.time()
        with self.assertLogs("calc", level="INFO") as lg:
            res = cw.run_calc(self.tmp, "x", slow, stop, lambda: "дней 3 из 10")
        release.set()
        self.assertIsNone(res)
        self.assertLess(_t.time() - t0, 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "calc", "x.json")))
        self.assertTrue(any("дней 3 из 10" in m for m in lg.output))
        self.assertTrue(any("остановка" in m for m in lg.output))

    def test_threaded_success_and_error(self):
        import threading
        stop = threading.Event()
        self.assertTrue(cw.run_calc(self.tmp, "x", lambda: {"a": 2}, stop))
        with open(os.path.join(self.tmp, "calc", "x.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["data"], {"a": 2})

        def boom():
            raise RuntimeError("нет сети")
        self.assertFalse(cw.run_calc(self.tmp, "x", boom, stop))
        with open(os.path.join(self.tmp, "calc", "x.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["data"], {"a": 2})

    def test_loop_returns_on_stop(self):
        import threading
        stop = threading.Event()
        threading.Timer(0.1, stop.set).start()
        cw.loop(self.tmp, {"x": (lambda: __import__("time").sleep(3) or {}, 900)}, stop)   # не ждёт 3 с


class WorkerLocalFlows(unittest.TestCase):
    """В воркере сервер данных выключен, но потоки денег берутся прямо из flows.sqlite той же функцией, что и сервер."""

    def test_flows_from_local_db(self):
        tmp = tempfile.mkdtemp(prefix="tcalc_")
        self.addCleanup(shutil.rmtree, tmp, True)

        class Lib:
            ds_parsed = staticmethod(lambda *a, **k: "orig")
        cw._local_parsed(Lib, tmp)
        got = Lib.ds_parsed("flows/summary", {"period": "day"})
        self.assertEqual(got["period"], "day")                 # базы ещё нет -> пустая сводка, но не None
        self.assertTrue(got.get("empty"))
        self.assertIsNone(Lib.ds_parsed("flows/summary", {"period": "bad"}))   # неверный параметр -> None, без исключения
        self.assertIsNone(Lib.ds_parsed("calc/fng"))           # остальное — как при выключенном сервере
        self.assertIsNone(Lib.ds_parsed("disclosure/facts", {"isin": "RU000A104JQ3"}))


class ClientFng(unittest.TestCase):
    def setUp(self):
        self.ds, self.kick = M.ds_parsed, M._fng_kick
        self.calls, self.kicks = [], []
        M._fng_kick = lambda force=False: self.kicks.append(force)
        M.mem_clear()

    def tearDown(self):
        M.ds_parsed, M._fng_kick = self.ds, self.kick
        M.mem_clear()

    def test_server_data(self):
        def fake(name, params=None, timeout=20):
            self.calls.append(name)
            return dict(PAYLOAD)
        M.ds_parsed = fake
        out = M.fng_payload()
        self.assertEqual(out["value"], 61)
        self.assertEqual(out["source"], "server")
        self.assertFalse(out["loading"])
        self.assertIsNone(out["error"])
        self.assertEqual(out["progress"]["have"], out["progress"]["need"])
        self.assertEqual(self.kicks, [])                                 # локальный расчёт не запускался
        M.fng_payload()
        self.assertEqual(self.calls, ["calc/fng"])                       # второй раз — из памяти
        M.fng_payload(force=True)
        self.assertEqual(len(self.calls), 2)                             # force обходит память, но идёт на сервер
        self.assertEqual(self.kicks, [])

    def test_fallback_local(self):
        M.ds_parsed = lambda name, params=None, timeout=20: None
        out = M.fng_payload(force=True)
        self.assertEqual(self.kicks, [True])
        self.assertNotIn("source", out)
        self.assertIsNone(out["value"])

    def test_bad_server_answer_falls_back(self):
        M.ds_parsed = lambda name, params=None, timeout=20: {"value": None}
        M.fng_payload()
        self.assertEqual(self.kicks, [False])

    def test_fng_compute_sync(self):
        run = M._fng_run

        def ok():
            M._fng["res"] = dict(PAYLOAD)
            M._fng["err"] = None
            M._fng.update(running=False)

        def bad():
            M._fng["err"] = "нет сети"
            M._fng.update(running=False)
        try:
            M._fng_run = ok
            self.assertEqual(M.fng_compute()["value"], 61)
            M._fng_run = bad
            with self.assertRaises(RuntimeError):
                M.fng_compute()
        finally:
            M._fng_run = run
            M._fng.update(res=None, err=None, running=False)


if __name__ == "__main__":
    unittest.main()
