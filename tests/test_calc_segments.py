"""Сегменты и портфель для калькулятора: фильтры выпусков, флоатеры отдельно, доли классов активов портфеля."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()


def patched(**kw):
    class Ctx:
        def __enter__(self):
            self.old = {k: getattr(M, k, None) for k in kw}
            for k, v in kw.items():
                setattr(M, k, v)

        def __exit__(self, *a):
            for k, v in self.old.items():
                setattr(M, k, v)
    return Ctx()


def row(i, kind, y, dur=2.0, rating=None, **kw):
    r = {"id": "X%d" % i, "isin": "RU000X%d" % i, "kind": kind, "cur": "RUB", "yield": y, "dur": dur, "rating": rating,
         "floating": False, "linker": False, "sub": ""}
    r.update(kw)
    return r


class Segments(unittest.TestCase):
    def rows(self):
        out = []
        for i, y in enumerate((17.0, 18.0, 19.0)):                       # обычные AA
            out.append(row(i, "corp", y, rating="AA"))
        out.append(row(10, "corp", 30.0, dur=0.3, rating="AA", floating=True))      # флоатер
        out.append(row(11, "corp", 35.0, dur=9.0, rating="AA"))                      # бессрочный (по справочнику)
        out.append(row(12, "corp", 33.0, dur=3.0, rating="AA", sub="субординированная"))
        for i, y in enumerate((14.0, 15.0, 16.0)):                       # обычные ОФЗ
            out.append(row(20 + i, "ofz", y, dur=4.0))
        out.append(row(30, "ofz", 9.0, dur=6.0, linker=True))                        # линкер
        out.append(row(31, "ofz", 12.0, dur=0.2, floating=True, sub="ofz_floater"))  # флоатер ОФЗ
        for i, y in enumerate((17.5, 18.5, 19.5)):                       # флоатеры
            out.append(row(40 + i, "corp", y, dur=0.2, rating="AA", floating=True))
        return out

    def test_median_ignores_floaters_linkers_perpetual(self):
        ti = lambda isin: {"perpetual": True} if isin == "RU000X11" else {}
        with patched(screener_payload=lambda: {"rows": self.rows()}, tcat_info=ti):
            seg = M._calc_segments(16.0)
        self.assertEqual(seg["aa"]["n"], 3)
        self.assertAlmostEqual(seg["aa"]["yield"], 18.0)
        self.assertAlmostEqual(seg["aa"]["dur"], 2.0)
        self.assertEqual(seg["ofz"]["n"], 3)
        self.assertAlmostEqual(seg["ofz"]["yield"], 15.0)
        self.assertAlmostEqual(seg["ofz"]["dur"], 4.0)

    def test_floaters_get_own_segment_with_spread(self):
        with patched(screener_payload=lambda: {"rows": self.rows()}, tcat_info=lambda isin: {}):
            seg = M._calc_segments(16.0)
        f = seg["flt"]
        self.assertGreaterEqual(f["n"], 3)
        self.assertFalse(f["estimate"])
        self.assertAlmostEqual(f["spread"], f["yield"] - 16.0, places=2)
        self.assertLess(f["dur"], 1.0)
        self.assertGreater(f["loss"], 0)

    def test_fallback_when_no_market(self):
        def boom():
            raise RuntimeError("нет данных")
        with patched(screener_payload=boom):
            seg = M._calc_segments(16.0)
        self.assertTrue(seg["flt"]["estimate"])
        self.assertAlmostEqual(seg["flt"]["yield"], 16.0 + M.CALC_FLT_SPREAD)
        self.assertEqual(set(seg), {"ofz", "aaa", "aa", "a", "hy", "flt"})


class PortfolioShares(unittest.TestCase):
    def test_shares_by_class(self):
        pos = [{"type": "bond", "value_rub": 500.0, "ticker": "SU1"}, {"type": "share", "value_rub": 300.0, "ticker": "SBER"},
               {"type": "etf", "value_rub": 100.0, "ticker": "LQDT"}, {"type": "etf", "value_rub": 50.0, "ticker": "TMOS"},
               {"type": "currency", "value_rub": 50.0, "ticker": "USD"}, {"type": "futures", "value_rub": 999.0, "ticker": "F"}]
        sh = M._calc_shares(pos)
        self.assertAlmostEqual(sh["bonds"], 0.5)
        self.assertAlmostEqual(sh["stocks"], 0.3)
        self.assertAlmostEqual(sh["lqdt"], 0.1)
        self.assertAlmostEqual(sh["funds"], 0.05)
        self.assertAlmostEqual(sh["cash"], 0.05)
        self.assertAlmostEqual(sum(sh.values()), 1.0, places=3)
        self.assertIsNone(M._calc_shares([]))

    def test_portfolio_carries_structure_and_duration(self):
        summary = {"portfolio": {"total": 1000.0, "bonds": 600.0, "positions": [
            {"type": "bond", "value_rub": 600.0, "ticker": "A"}, {"type": "share", "value_rub": 400.0, "ticker": "B"}]}, "months": []}
        bonds = {"metrics": {"irr": 15.0, "coupons_12m": 90.0},
                 "rows": [{"dur": 2.0, "value_rub": 300.0}, {"dur": 4.0, "value_rub": 300.0}, {"dur": 0.2, "value_rub": 100.0, "floating": True}]}
        with patched(imports_list=lambda: [{"id": "imp:1"}], build_summary=lambda cfg, acc, f: summary,
                     build_bonds=lambda cfg, acc, force=False: bonds):
            pf = M._calc_portfolio({"token": ""}, "all")
        self.assertAlmostEqual(pf["shares"]["bonds"], 0.6)
        self.assertAlmostEqual(pf["shares"]["stocks"], 0.4)
        self.assertAlmostEqual(pf["dur_bonds"], 3.0)         # флоатер в дюрацию не входит
        self.assertEqual(pf["irr"], 15.0)
        self.assertIsNone(pf["income_month"])


if __name__ == "__main__":
    unittest.main()
