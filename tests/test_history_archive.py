"""Архив дневных цен на сервере (/v1/history): тот же ряд, что приложение собирало со страниц ISS, и откат при неполном архиве."""
import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import _load  # noqa: E402
import history  # noqa: E402

TODAY = date(2024, 3, 1)


def days(frm, n):
    d, out = date.fromisoformat(frm), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


DATES = days("2023-01-02", 300)


class FakeIss:
    """Отдаёт историю как ISS: страницы по 100 строк, курсор, колонки из history.columns. У фонда — два режима торгов."""

    def __init__(self):
        self.calls = 0

    def rows(self, market, secid):
        out = []
        for i, d in enumerate(DATES):
            if market == "index":
                out.append({"TRADEDATE": d, "CLOSE": 100 + i * 0.5, "BOARDID": "SNDX", "VALUE": None})
            else:
                out.append({"BOARDID": "TQTF", "TRADEDATE": d, "CLOSE": 1.0 + i / 1000, "VALUE": 1000.0 + i, "YIELDCLOSE": None})
                out.append({"BOARDID": "SMAL", "TRADEDATE": d, "CLOSE": 9.0, "VALUE": 1.0, "YIELDCLOSE": None})
        return out

    def __call__(self, url):
        self.calls += 1
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        parts = u.path.split("/")
        market, secid = parts[parts.index("markets") + 1], parts[-1].split(".")[0]
        cols = q.get("history.columns", "TRADEDATE,CLOSE").split(",")
        rows = [r for r in self.rows(market, secid) if r["TRADEDATE"] >= q["from"] and (not q.get("till") or r["TRADEDATE"] <= q["till"])]
        start = int(q.get("start", 0))
        page = rows[start:start + 100]
        return {"history": {"columns": cols, "data": [[r.get(c) for c in cols] for r in page]},
                "history.cursor": {"columns": ["INDEX", "TOTAL", "PAGESIZE"], "data": [[start, len(rows), 100]]}}


class Archive(unittest.TestCase):
    def setUp(self):
        self.iss = FakeIss()
        self.t = [1_700_000_000.0]
        self.st = history.HistoryStore(os.path.join(tempfile.mkdtemp(prefix="hist_"), "h.sqlite"), self.iss,
                                       clock=lambda: self.t[0], today=lambda: TODAY)

    def test_best_board_pagination_and_reuse(self):
        r = self.st.query("shares", "lqdt", "2023-01-01")
        self.assertEqual(len(r["rows"]), len(DATES))                       # 600 строк ISS -> 300 дат, 6 страниц
        self.assertEqual(r["rows"][0][1], 1.0)                             # режим с наибольшим оборотом, не SMAL
        self.assertEqual(r["secid"], "LQDT")
        n = self.iss.calls
        self.st.query("shares", "LQDT", "2023-06-01")
        self.assertEqual(self.iss.calls, n)                                # из архива, без ISS
        self.st.query("shares", "LQDT", "2022-06-01")                     # раньше покрытого — догружается только начало
        self.assertEqual(self.iss.calls, n + 1)
        self.t[0] += history.TAIL_TTL + 1
        self.st.query("shares", "LQDT", "2023-06-01")                     # хвост устарел — одна страница хвоста
        self.assertEqual(self.iss.calls, n + 2)

    def test_iss_failure_raises(self):
        st = history.HistoryStore(os.path.join(tempfile.mkdtemp(prefix="hist_"), "h.sqlite"), lambda u: None)
        with self.assertRaises(history.HistoryError):
            st.query("index", "RGBITR", "2023-01-01")
        with self.assertRaises(ValueError):
            st.query("bad", "X", "2023-01-01")
        with self.assertRaises(ValueError):
            st.query("index", "X;DROP", "2023-01-01")

    def test_refresh_all_drops_unused(self):
        self.st.query("index", "RGBITR", "2023-01-01")
        self.t[0] += (history.KEEP_DAYS + 1) * 86400
        ok, bad, gone = self.st.refresh_all()
        self.assertEqual(gone, 1)


class ClientUsesArchive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _load.load()

    def iss_text(self, iss):
        return lambda url, *a, **k: json.dumps(iss(url))

    def test_same_series_as_iss_and_fallback_on_gap(self):
        m = self.m
        iss = FakeIss()
        st = history.HistoryStore(os.path.join(tempfile.mkdtemp(prefix="hist_"), "h.sqlite"), iss, today=lambda: TODAY)
        for code in ("LQDT", "RGBITR"):
            with mock.patch.object(m, "ds_history", return_value=None), mock.patch.object(m, "http_text", self.iss_text(iss)):
                direct = m._bench_fetch(code, "2023-01-01")
            arch = st.query("shares" if code == "LQDT" else "index", code, "2023-01-01")
            with mock.patch.object(m, "ds_history", return_value=arch), mock.patch.object(m, "http_text", side_effect=AssertionError):
                via = m._bench_fetch(code, "2023-01-01")
            self.assertEqual(via, direct, code)
        gap = dict(arch, cov_from="2023-05-01")                            # архив начинается позже запрошенного — к ISS
        with mock.patch.object(m, "ds_history", return_value=gap), mock.patch.object(m, "http_text", self.iss_text(FakeIss())):
            self.assertEqual(len(m._bench_fetch("RGBITR", "2023-01-01")), len(DATES))


if __name__ == "__main__":
    unittest.main()
