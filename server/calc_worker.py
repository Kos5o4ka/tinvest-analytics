#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сервер расчётов TAnalytic: тяжёлые расчёты по публичным рыночным данным считаются один раз на сервере, клиенты забирают готовый JSON.
Отдельный долгоживущий процесс, только stdlib, Python 3.8+. Токен T-Invest не нужен и не читается.

Берёт собранный клиент tinvest_analytics.py (тот же файл, что у клиентов) и вызывает его функции расчёта. Результат пишется атомарно
в `<data>/calc/<имя>.json` как {"t": время, "data": {...}}; сервер данных отдаёт его как /v1/parsed/calc/<имя> (не старше часа).
Не получилось пересчитать — прежний файл остаётся (клиенты получат 404 после его устаревания и посчитают у себя).

Добавить расчёт — одна строка в register_calcs(): имя -> (функция без аргументов, возвращающая JSON-совместимый словарь; период, с).

    python3 calc_worker.py --data DIR [--lib PATH] [--only fng] [--once] [--verbose]
"""
import argparse
import importlib.util
import json
import logging
import os
import signal
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("calc")
CALCS = {}                       # имя -> (функция, период пересчёта, с); заполняется в register_calcs()
PROGRESS = {}                    # имя -> функция без аргументов -> строка о ходе расчёта (для журнала раз в минуту)
PROGRESS_EVERY = 60


def load_lib(path, data_dir):
    """Собранный tinvest_analytics.py как модуль: своя папка кэша, сервер данных выключен (иначе воркер спрашивал бы сам себя)."""
    os.environ["TINVEST_DATA_SERVER"] = "off"
    os.environ["TINVEST_HOME"] = os.path.join(data_dir, "calc_home")
    os.makedirs(os.environ["TINVEST_HOME"], exist_ok=True)
    spec = importlib.util.spec_from_file_location("tinvest_analytics_lib", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["tinvest_analytics_lib"] = m
    spec.loader.exec_module(m)
    _local_parsed(m, data_dir)
    return m


def _local_parsed(lib, data_dir):
    """Сервер данных в воркере выключен, но часть готовых данных лежит рядом: потоки денег (flows.sqlite от flows_worker.py)
    нужны индексу страха и жадности (компонент «поток»). Отдаём их напрямую из базы той же функцией, что и сервер."""
    sys.path.insert(0, HERE)
    import tinvest_server

    def ds_parsed(name, params=None, timeout=20):
        if not name.startswith("flows/"):
            return None
        code, obj = tinvest_server.flows_query(data_dir, name, {k: [str(v)] for k, v in (params or {}).items()})
        return obj.get("data") if code == 200 and obj.get("ok") else None
    lib.ds_parsed = ds_parsed


def register_calcs(lib):
    CALCS["fng"] = (lib.fng_compute, 900)            # индекс страха и жадности: первый расчёт — ~2 000 запросов к ISS (десятки минут на VPS)
    st = getattr(lib, "_fng", None)
    if isinstance(st, dict):
        PROGRESS["fng"] = lambda: "этап «%s», дней с закрытиями %s из %s" % (st.get("phase") or "—", st.get("have", 0), st.get("need", 0))
    # период < CALC_MAX_AGE сервера (час), иначе клиенты получат «устарело» и посчитают сами
    CALCS["pri_vol"] = (lib.pv_compute, 300)         # объёмы первичных размещений (живые данные: в торги клиент ждёт не старше 5 мин)
    CALCS["inflation"] = (lib.weekly_inflation_calc, 3000)   # недельная инфляция: вся история заметок Росстата один раз на сервере


def write_result(data_dir, name, data, now=None):
    """Атомарно: <data>/calc/<name>.json через временный файл и os.replace."""
    d = os.path.join(data_dir, "calc")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".json")
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"t": time.time() if now is None else now, "data": data}, f, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def run_calc(data_dir, name, fn, stop=None, progress=None):
    """Один расчёт -> True/False; None — остановлен по сигналу (прогресс расчёта остаётся в кэше calc_home).
    Ошибка не трогает прежний файл. Со `stop` расчёт идёт в фоновом потоке: процесс сразу реагирует на SIGTERM
    и раз в PROGRESS_EVERY секунд пишет в журнал, как идёт расчёт (первый расчёт на VPS бывает долгим)."""
    t0 = time.time()
    box = {}

    def work():
        try:
            box["data"] = fn()
        except Exception as e:  # noqa: BLE001
            box["err"] = e
    if stop is None:
        work()
    else:
        th = threading.Thread(target=work, name="calc-" + name, daemon=True)
        th.start()
        while th.is_alive():
            if stop.wait(PROGRESS_EVERY):
                log.info("%s: остановка во время расчёта (%.0f с); скачанное сохранено в кэше, продолжится после запуска",
                         name, time.time() - t0)
                return None
            if th.is_alive():
                try:
                    msg = progress() if progress else ""
                except Exception:  # noqa: BLE001
                    msg = ""
                log.info("%s: считаю %.0f с%s", name, time.time() - t0, (": " + msg) if msg else "")
    if "err" in box:
        log.warning("%s: расчёт не удался, прежний результат сохранён: %s", name, box["err"])
        return False
    try:
        write_result(data_dir, name, box.get("data"))
    except Exception as e:  # noqa: BLE001
        log.warning("%s: расчёт не удался, прежний результат сохранён: %s", name, e)
        return False
    log.info("%s: готово за %.0f с", name, time.time() - t0)
    return True


def loop(data_dir, calcs, stop, once=False):
    last = {}
    while not stop.is_set():
        for name, (fn, every) in calcs.items():
            if stop.is_set():
                break
            if not once and time.time() - last.get(name, 0) < every:
                continue
            last[name] = time.time()
            if run_calc(data_dir, name, fn, stop, PROGRESS.get(name)) is None:
                return
        if once:
            return
        stop.wait(10)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Сервер расчётов для сервера данных TAnalytic")
    ap.add_argument("--data", required=True, help="каталог данных (calc/*.json, calc_home/)")
    ap.add_argument("--lib", default=os.path.join(os.path.dirname(HERE), "tinvest_analytics.py"), help="собранный tinvest_analytics.py")
    ap.add_argument("--only", help="считать только этот расчёт")
    ap.add_argument("--once", action="store_true", help="один проход и выход")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.makedirs(a.data, exist_ok=True)
    register_calcs(load_lib(a.lib, a.data))
    calcs = {k: v for k, v in CALCS.items() if not a.only or k == a.only}
    stop = threading.Event()
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: stop.set())
    log.info("старт: данные %s, расчёты %s", a.data, ", ".join(calcs))
    loop(a.data, calcs, stop, a.once)
    log.info("остановлен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
