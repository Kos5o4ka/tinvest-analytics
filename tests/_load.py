"""Загрузка собранного tinvest_analytics.py как модуля с изолированной папкой данных (без сети и без настоящего токена)."""
import importlib.util
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mod = None


def load():
    global _mod
    if _mod is None:
        home = tempfile.mkdtemp(prefix="tinvest_test_")
        os.environ["TINVEST_HOME"] = home
        spec = importlib.util.spec_from_file_location("tinvest_analytics_under_test", os.path.join(ROOT, "tinvest_analytics.py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules["tinvest_analytics_under_test"] = m
        spec.loader.exec_module(m)
        _mod = m
    return _mod
