"""Модель тарифа брокера: окно 12 мес. независимо от периода, исключения из оборота, экономия. Без сети."""
import json
import os
import threading
import urllib.error
import urllib.request
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

M = load()
NOW = datetime(2026, 11, 20, 12, 0, 0)
NAMES = {"tmos": {"type": "etf", "ticker": "TMOS", "name": "Т-Капитал Индекс МосБиржи"},
         "sber": {"type": "share", "ticker": "SBER", "name": "Сбербанк"}}
_n = [0]


def money(x):
    return {"currency": "rub", "units": str(int(x)), "nano": int(round((x - int(x)) * 1e9))}


def op(iso, typ, uid, pay, comm=0.0, cur="rub"):
    _n[0] += 1
    p = money(pay)
    p["currency"] = cur
    return {"id": "f%d" % _n[0], "date": iso + "T10:00:00Z", "type": "OPERATION_TYPE_" + typ, "payment": p,
            "commission": money(comm), "quantity": "1", "instrumentUid": uid, "_acc": "A"}


class FeeModel(unittest.TestCase):
    def test_window_and_period_independent(self):
        ops = [op("2026-03-10", "BUY", "sber", -1000000, -3000), op("2025-02-10", "BUY", "sber", -5000000, -15000)]
        fm = M.fee_model(ops, NAMES, 0, NOW)
        self.assertEqual(fm["from"], "2025-12-01")
        self.assertEqual(fm["to"], "2026-11-20")
        self.assertEqual(fm["turnover"], 1000000)          # покупка 2025-02 вне окна
        self.assertEqual(fm["active_months"], 1)
        self.assertAlmostEqual(fm["eff_rate"], 0.003)
        self.assertEqual(fm["current"], "Инвестор")
        # analyze с разными периодами не влияет на модель (она считается отдельно, только по ops)
        a = M.analyze(ops, NAMES, "py", 0)
        b = M.analyze(ops, NAMES, "all", 0)
        self.assertNotEqual(a["totals"], b["totals"])
        self.assertEqual(M.fee_model(ops, NAMES, 0, NOW), M.fee_model(ops, NAMES, 0, NOW))

    def test_exclusions(self):
        ops = [op("2026-05-01", "BUY", "sber", -100000, -300),
               op("2026-05-02", "SELL", "sber", 100000, -300),
               op("2026-05-03", "BUY", "tmos", -500000),            # фонд Т-Капитала
               op("2026-05-04", "BOND_REPAYMENT", "sber", 900000),  # погашение
               op("2026-05-05", "COUPON", "sber", 50000),
               op("2026-05-06", "DELIVERY_BUY", "sber", -700000),
               op("2026-05-07", "BUY", "sber", -1000, cur="usd"),
               op("2026-05-08", "INPUT_SECURITIES", "sber", 0)]
        fm = M.fee_model(ops, NAMES, 0, NOW)
        self.assertEqual(fm["turnover"], 200000)
        self.assertEqual(fm["excluded"], 1200000)
        self.assertEqual(fm["excluded_by"]["tcap"], 500000)
        self.assertEqual(fm["excluded_by"]["delivery"], 700000)
        self.assertEqual(fm["paid_broker"], 600)

    def test_no_double_count_broker_fee_ops(self):
        ops = [op("2026-05-01", "BUY", "sber", -100000, -300), op("2026-05-01", "BROKER_FEE", "sber", -300)]
        self.assertEqual(M.fee_model(ops, NAMES, 0, NOW)["paid_broker"], 300)

    def test_savings(self):
        # оборот 12 млн за 12 мес.: Инвестор 36000, Трейдер 6000+4680, Премиум 4800+35880
        ops = [op("2026-%02d-10" % m, "BUY", "sber", -1000000, -3000) for m in range(1, 12)] + [op("2025-12-10", "BUY", "sber", -1000000, -3000)]
        fm = M.fee_model(ops, NAMES, 0, NOW)
        self.assertEqual(fm["active_months"], 12)
        by = {t["name"]: t["cost"] for t in fm["tariffs"]}
        self.assertAlmostEqual(by["Инвестор"], 36000)
        self.assertAlmostEqual(by["Трейдер"], 6000 + 390 * 12)
        self.assertEqual(fm["best"], "Трейдер")
        self.assertAlmostEqual(fm["save"], 36000 - (6000 + 4680))
        self.assertFalse(fm["below_model"])
        # портфель >= 2 млн: Трейдер без абонплаты
        self.assertAlmostEqual({t["name"]: t["cost"] for t in M.fee_model(ops, NAMES, 2.5e6, NOW)["tariffs"]}["Трейдер"], 6000)

    def test_below_model(self):
        # факт 500 ₽ при обороте 1 млн (0,05 %): Трейдер модель 500+390 > факт, платит меньше всех моделей
        ops = [op("2026-05-01", "BUY", "sber", -1000000, -100)]
        fm = M.fee_model(ops, NAMES, 0, NOW)
        self.assertTrue(fm["below_model"])
        self.assertEqual(fm["save"], 0.0)
        self.assertEqual(fm["current"], "Трейдер")

    def test_empty(self):
        fm = M.fee_model([], NAMES, 0, NOW)
        self.assertIsNone(fm["best"])
        self.assertIsNone(fm["eff_rate"])


    def test_other_broker_ops_excluded(self):
        t = op("2026-05-01", "BUY", "sber", -1000000, -3000)
        v = op("2026-05-02", "BUY", "sber", -9000000, -4500)
        v["_acc"] = "imp-vtb"
        fee = op("2026-05-03", "SERVICE_FEE", "sber", -2990)
        fee["_acc"] = "imp-vtb"
        fm = M.fee_model([t, v, fee], NAMES, 0, NOW, t_accs={"A"})
        self.assertEqual(fm["turnover"], 1000000)
        self.assertEqual(fm["paid_broker"], 3000)
        self.assertEqual(fm["paid_service"], 0)
        self.assertEqual(M.fee_model([t, v], NAMES, 0, NOW)["turnover"], 10000000)   # без фильтра — как раньше
        # отдельный расчёт для счёта ВТБ: факт и модель выбранного тарифа
        tar = M.broker_tariff("vtb", "my_online_prime")
        bf = M.broker_account_fees("imp-vtb", [t, v], NAMES, tar, NOW)
        self.assertEqual(bf["turnover"], 9000000)
        self.assertAlmostEqual(bf["eff_rate"], 0.0005)
        self.assertAlmostEqual(bf["model"]["fee"], 9000000 * 0.0006)
        self.assertIsNone(M.broker_account_fees("imp-vtb", [t, v], NAMES, None, NOW)["model"])

    def test_broker_detection(self):
        acc = M.broker_of_account
        cases = [({"id": "2001", "kind": "tinvest", "name": "Брокерский"}, "tinvest"),
                 ({"id": "imp-1", "kind": "import", "format": "tbank", "name": "x"}, "tinvest"),
                 ({"id": "imp-2", "format": "vtb", "name": "x"}, "vtb"),
                 ({"id": "imp-3", "broker": "ВТБ", "name": "ИИС"}, "vtb"),
                 ({"id": "imp-4", "broker": "", "name": "Тинькофф старый"}, "tinvest"),
                 ({"id": "imp-5", "broker": "Сбербанк", "name": "x"}, "sber"),
                 ({"id": "imp-6", "broker": "Финам", "name": ""}, "finam"),
                 ({"id": "imp-7", "broker": "BCS", "name": ""}, "bcs"),
                 ({"id": "imp-8", "broker": "Альфа-Инвестиции"}, "alfa"),
                 ({"id": "imp-9", "broker": "Газпромбанк"}, "gpb"),
                 ({"id": "imp-10", "broker": "Открытие"}, "open"),
                 ({"id": "imp-11", "broker": "Уралсиб"}, "uralsib"),
                 ({"id": "imp-12", "broker": "ПСБ"}, "psb"),
                 ({"id": "imp-13", "broker": "Freedom Finance"}, "freedom"),
                 ({"id": "imp-14", "broker": "Мой брокер"}, "other"),
                 ({"id": "imp-15", "format": "vtb", "broker_id": "sber"}, "sber"),       # ручная смена брокера важнее формата
                 ({"id": "imp-demo", "broker": "Демо", "demo": True}, "tinvest"),
                 ({"id": "imp-16", "kind": "import", "type": "ВТБ", "name": "x"}, "vtb")]  # счёт из list_accounts
        for a, want in cases:
            self.assertEqual(acc(a)[0], want, a)
        self.assertEqual(M.broker_detect_import("report.csv", b"", "vtb"), "vtb")
        self.assertEqual(M.broker_detect_import("finam_2025.csv", b"", ""), "finam")
        raw = "Брокер: Банк ВТБ (ПАО)\n\nДата;Сумма;Название\n01.02.2025;100;Сбербанк\n".encode("utf-8")
        self.assertEqual(M.broker_detect_import("ops.csv", raw, ""), "vtb")

    def test_tariff_catalog_shape(self):
        for bid, b in M.BROKER_TARIFFS.items():
            self.assertIn(bid, M.BROKERS)
            self.assertNotEqual(bid, "tinvest")
            self.assertTrue(b["name"])
            ids = set()
            for t in b["tariffs"]:
                self.assertRegex(t["id"], r"^[a-z0-9_]{1,40}$")
                self.assertNotIn(t["id"], ids)
                ids.add(t["id"])
                self.assertTrue(t["name"] and t["source_url"].startswith("https://") and t["as_of"])
                self.assertEqual(set(t["rate_pct"]), {"shares", "bonds"})
                for v in t["rate_pct"].values():
                    self.assertTrue(0 <= v < 1)
                self.assertGreaterEqual(t["monthly_fee"], 0)
                self.assertIn(t["monthly_mode"], ("active", "always"))
        self.assertTrue(M.BROKER_TARIFFS["vtb"]["tariffs"])
        self.assertNotIn("TCSG", M.FM_TCAP_TICKERS)
        self.assertEqual(M.DEFAULT_CONFIG["broker_tariffs"], {})


class ConfigBrokerTariffs(unittest.TestCase):
    """POST /api/config (broker_tariffs) и /api/import/broker через настоящий обработчик на 127.0.0.1."""
    @classmethod
    def setUpClass(cls):
        cls.srv = M.LocalHTTPServer(("127.0.0.1", 0), M.Handler)
        threading.Thread(target=cls.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_validation(self):
        before = M.load_config()
        code, _ = self.post("/api/config", {"broker_tariffs": {"imp-a": "my_online_prime", "imp-b": "BAD ID!", "imp-c": 5}})
        self.assertEqual(code, 200)
        cfg = M.load_config()
        self.assertEqual(cfg["broker_tariffs"], {"imp-a": "my_online_prime"})
        self.assertEqual(cfg["theme"], before["theme"])                     # прочие ключи не тронуты
        self.post("/api/config", {"broker_tariffs": {"imp-a": ""}})          # пустое значение снимает выбор
        self.assertEqual(M.load_config()["broker_tariffs"], {})
        self.post("/api/config", {"broker_tariffs": "x"})                    # не словарь — игнор
        self.assertEqual(M.load_config()["broker_tariffs"], {})

    def test_import_broker_override(self):
        saved = M.store().get("imports")
        self.addCleanup(lambda: M.store().put("imports", saved or []))
        M.store().put("imports", [{"id": "imp-t1", "name": "Счёт", "broker": "ВТБ", "format": "vtb", "files": []}])
        self.assertEqual(M.broker_of_account(M.imports_list()[0])[0], "vtb")
        code, _ = self.post("/api/import/broker", {"id": "imp-t1", "broker_id": "sber"})
        self.assertEqual(code, 200)
        self.assertEqual(M.broker_of_account(M.imports_list()[0])[0], "sber")
        self.assertEqual(self.post("/api/import/broker", {"id": "imp-t1", "broker_id": "nope"})[0], 400)
        self.assertEqual(self.post("/api/import/broker", {"id": "imp-zz", "broker_id": "vtb"})[0], 404)

if __name__ == "__main__":
    unittest.main()
