"""Живая проверка доходности против поля YIELD Мосбиржи. Включается переменной TINVEST_LIVE=1 (нужна сеть):
    TINVEST_LIVE=1 python3 -m unittest tests.test_live_moex -v
"""
import json
import os
import statistics
import sys
import unittest
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

N = 30


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "tinvest-analytics-tests"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def table(d, name):
    t = d.get(name) or {}
    return [dict(zip(t.get("columns") or [], r)) for r in t.get("data") or []]


@unittest.skipUnless(os.environ.get("TINVEST_LIVE") == "1", "живые тесты: задайте TINVEST_LIVE=1")
class LiveMoex(unittest.TestCase):
    def test_yield_vs_moex(self):
        M = load()
        today = date.today().isoformat()
        cands = []
        for board in ("TQCB", "TQOB"):
            d = get("https://iss.moex.com/iss/engines/stock/markets/bonds/boards/%s/securities.json?iss.meta=off"
                    "&iss.only=securities,marketdata" % board)
            sec = {r["SECID"]: r for r in table(d, "securities")}
            for m in table(d, "marketdata"):
                s = sec.get(m["SECID"])
                if s and m.get("YIELD") and m.get("LAST") and (m.get("VALTODAY") or 0) > 0 and s.get("FACEVALUE") \
                        and s.get("FACEUNIT") == "SUR":          # валютные выпуски (номинал в CNY/USD) сравнивать нельзя: цена в рублях
                    cands.append((m["VALTODAY"], s, m))
        cands.sort(key=lambda x: -x[0])
        rows, tried = [], 0
        for _, s, m in cands:
            if len(rows) >= N or tried > 200:
                break
            tried += 1
            try:
                d = get(M.BC_URL % s["SECID"])
            except Exception:  # noqa: BLE001
                continue
            bz = {"coupons": [{k: r.get(k) for k in ("coupondate", "value", "valueprc")} for r in table(d, "coupons")],
                  "amort": [{k: r.get(k) for k in ("amortdate", "value")} for r in table(d, "amortizations")],
                  "offers": [{k: r.get(k) for k in ("offerdate", "price", "offertype")} for r in table(d, "offers")]}
            fut = [c for c in bz["coupons"] if (c["coupondate"] or "") > today]
            if not fut or any(not c["value"] for c in fut) or len({round(c["value"], 4) for c in fut}) > 3:
                continue                                    # только известные купоны (не флоатеры)
            face = s["FACEVALUE"]
            flows, kind, end = M.bond_flows(bz, today, face)
            if not flows or end <= today:
                continue
            dirty = m["LAST"] / 100.0 * face + (s.get("ACCRUEDINT") or 0.0)
            y = M.cf_ytm(dirty, flows, today)
            if y is None or m["YIELD"] > 60:
                continue
            rows.append((s["SECID"], (s.get("SHORTNAME") or "")[:22], kind, m["YIELD"], y * 100, y * 100 - m["YIELD"]))
        print("\n%-13s %-22s %-8s %8s %8s %7s" % ("ISIN", "Выпуск", "до", "MOEX %", "наш %", "разн."))
        for r in rows:
            print("%-13s %-22s %-8s %8.2f %8.2f %+7.2f" % r)
        self.assertGreaterEqual(len(rows), 15, "слишком мало облигаций для сравнения")
        diffs = [abs(r[5]) for r in rows]
        med = statistics.median(diffs)
        share = sum(1 for x in diffs if x <= 0.5) / len(diffs)
        print("выпусков: %d, медиана |разн.| = %.3f п.п., в пределах 0,5 п.п.: %.0f%%" % (len(rows), med, share * 100))
        self.assertLess(med, 0.15)
        self.assertGreaterEqual(share, 0.9)


if __name__ == "__main__":
    unittest.main()
