"""Скринер облигаций из среза сервера: состав полей как у прямого пути, откат на старый формат среза. Без сети."""
import json
import os
import sys
import unittest
from unittest import mock

from _load import load, ROOT

sys.path.insert(0, os.path.join(ROOT, "server"))
import market_worker as W  # noqa: E402

M = load()

SC = ("SECID,SHORTNAME,SECNAME,ISIN,FACEVALUE,FACEUNIT,COUPONPERCENT,NEXTCOUPON,MATDATE,OFFERDATE,LISTLEVEL,PREVLEGALCLOSEPRICE,"
      "YIELDATPREVWAPRICE,COUPONPERIOD,BONDSUBTYPE,ISSUESIZE,ACCRUEDINT,COUPONVALUE,PREVPRICE,BONDTYPE,COUPON_DETAILS").split(",")
MC = "SECID,LAST,YIELD,WAPRICE,DURATION,VALTODAY,NUMTRADES,ZSPREAD,YIELDATWAPRICE,LASTCHANGEPRCNT".split(",")
W_EXTRA = ("chg", "level", "trades", "zs", "cy", "sub", "size", "nkd", "btype", "cpn_det", "offer", "cur", "turn", "macdur", "coupon_raw")


def _board(sec, md):
    return {"securities": {"columns": SC, "data": sec}, "marketdata": {"columns": MC, "data": md}}


BOARDS = {
    "TQCB": _board(
        [["RU1", "Эмит 1", "Эмит 1 001P", "RU000A0000001", "1000", "SUR", 12.125, "2026-12-10", "2028-05-01", "0000-00-00", 1, 99.5, 13.0, 91, "", 1000000, 12.3, 30.31, 99.4, "", None],
         ["RU2", "Эмит 2", "Эмит 2 002P", "RU000A0000002", "1000", "SUR", 10, "2026-12-11", "2027-05-01", "2026-12-01", 2, 98, 11.0, 182, "", 500000, 5, 50, 98, "", None],
         ["RU3", "Без доходности", "Без", "RU000A0000003", "1000", "SUR", 10, None, "2027-05-01", None, 3, 98, None, 182, "", 1, 1, 1, 98, "", None]],
        [["RU1", 99.6, 13.1, 99.55, 400.0, 5000000.0, 120, 250, None, 0.4],
         ["RU2", None, None, None, None, 0.0, 0, None, None, None],
         ["RU3", None, None, None, None, 0.0, 0, None, None, None]]),
    "TQOB": _board(
        [["SU26", "ОФЗ 26", "ОФЗ 26", "RU000A0JXXX1", "1000", "SUR", 7.0, "2026-12-12", "2030-01-01", "0000-00-00", 1, 90, 14, 182, "", 9, 7, 35, 90, "", None]],
        [["SU26", 90.5, 14.2, 90.4, 1200.0, 9000000.0, 300, 10, None, None]]),
}


def _ht(url, timeout=0):
    return json.dumps(BOARDS["TQCB" if "/TQCB/" in url else "TQOB"])


class Adapter(unittest.TestCase):
    def _rows(self, snap):
        M._scr.update(t=0, rows=[])
        with mock.patch.object(M, "market_snapshot_bonds", return_value=snap), mock.patch.object(M, "http_text", side_effect=_ht), \
                mock.patch.object(M, "kbd_at", return_value=None):
            return {r["id"]: r for r in M.screener_rows()}

    def test_same_columns_as_direct_path(self):
        direct = self._rows(None)
        snap = W.parse_moex_bonds(BOARDS)

        def boom(url, timeout=0):
            raise AssertionError("сеть не нужна")
        M._scr.update(t=0, rows=[])
        with mock.patch.object(M, "market_snapshot_bonds", return_value=snap), mock.patch.object(M, "http_text", side_effect=boom), \
                mock.patch.object(M, "kbd_at", return_value=None):
            via = {r["id"]: r for r in M.screener_rows()}
        self.assertEqual(set(via), set(direct))
        self.assertNotIn("RU3", via)
        for k, d in direct.items():
            self.assertEqual(set(via[k]), set(d))
            for f in d:
                self.assertEqual(via[k][f], d[f], (k, f))
        M._scr.update(t=0, rows=[])

    def test_old_format_falls_back(self):
        old = [{k: v for k, v in b.items() if k not in W_EXTRA} for b in W.parse_moex_bonds(BOARDS)]
        self.assertIsNone(M.screener_rows_from_snapshot(old))
        self.assertIsNone(M.screener_rows_from_snapshot(None))
        self.assertIsNone(M.screener_rows_from_snapshot([]))
        self.assertEqual(set(self._rows(old)), {"RU1", "RU2", "SU26"})     # прежний путь по ISS
        M._scr.update(t=0, rows=[])


if __name__ == "__main__":
    unittest.main()
