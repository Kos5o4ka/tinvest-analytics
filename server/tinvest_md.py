#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Минимальный клиент рыночных данных T-Invest API для сервера данных TAnalytic. Только stdlib, Python 3.8+.

БЕЗОПАСНОСТЬ. Здесь используется личный токен ВЛАДЕЛЬЦА сервера, и только на чтение. Токен живёт на VPS (см. server/README.md),
в git его нет. Из этого модуля токен никогда не попадает ни в ответы, ни в журналы, ни в тексты ошибок (везде маска t.***XXXX).
Разрешены только методы из белого списка ALLOWED (рыночные данные и справочники); счета, портфель, операции, заявки — нет.

Порядок поиска токена (load_token): $CREDENTIALS_DIRECTORY/tinvest_token -> $TINVEST_SERVER_TOKEN -> файл из --token-file.
Лимиты: токен-бакет на сервис (MarketData <= 300/мин, Instruments <= 100/мин); интерактивные запросы (priority=0) могут брать
весь запас, фоновые (priority=1) оставляют часть бакета интерактивным.
"""
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request

BASE = "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1."
ALLOWED = {
    "MarketDataService": {"GetCandles", "GetLastTrades", "GetOrderBook", "GetLastPrices", "GetTradingStatus"},
    "InstrumentsService": {"Shares", "Bonds", "Etfs", "GetAssetFundamentals", "GetAssetReports", "GetDividends",
                           "GetBondCoupons", "FindInstrument", "GetInstrumentBy"},
}
LIMITS = {"MarketDataService": 300, "InstrumentsService": 100}      # запросов в минуту по умолчанию
INTERACTIVE, BACKGROUND = 0, 1
TOKEN_RX = re.compile(r"t\.[A-Za-z0-9_\-]{20,}")


class MDError(Exception):
    """Ошибка клиента; текст уже очищен от токена."""


class NotAllowed(MDError):
    pass


class RateLimited(MDError):
    pass


def mask(token):
    t = (token or "").strip()
    if not t:
        return "<none>"
    return "t.***" + t[-4:]


def scrub(text, token=""):
    """Убирает токен (целиком и по шаблону) из произвольного текста."""
    s = str(text)
    if token:
        s = s.replace(token, mask(token))
    return TOKEN_RX.sub(lambda m: mask(m.group(0)), s)


def load_token(token_file=None, env=None):
    """-> (токен или '', откуда: 'credentials'|'env'|'file'|'')."""
    env = os.environ if env is None else env
    cd = env.get("CREDENTIALS_DIRECTORY")
    cands = []
    if cd:
        cands.append(("credentials", os.path.join(cd, "tinvest_token")))
    cands.append(("env", None))
    if token_file:
        cands.append(("file", token_file))
    for kind, path in cands:
        if kind == "env":
            v = (env.get("TINVEST_SERVER_TOKEN") or "").strip()
        else:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    v = f.read().strip()
            except (OSError, UnicodeDecodeError):
                v = ""
        if v:
            return v, kind
    return "", ""


class Bucket:
    """Токен-бакет с приоритетами. capacity = per_min (всплеск не больше минуты), пополнение per_min/60 в секунду."""

    def __init__(self, per_min, reserve=0.3, clock=time.monotonic, sleep=time.sleep):
        self.rate = per_min / 60.0
        self.cap = float(max(1, per_min))
        self.tokens = self.cap
        self.reserve = self.cap * reserve
        self.clock, self.sleep = clock, sleep
        self.t = clock()
        self.lock = threading.Lock()

    def _refill(self):
        n = self.clock()
        self.tokens = min(self.cap, self.tokens + (n - self.t) * self.rate)
        self.t = n

    def acquire(self, priority=BACKGROUND, timeout=30.0):
        """Берёт один токен; фоновым запросам нужен ещё запас reserve. RateLimited, если не дождались."""
        end = self.clock() + timeout
        need = 1.0 + (self.reserve if priority != INTERACTIVE else 0.0)
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= need:
                    self.tokens -= 1.0
                    return
                wait = (need - self.tokens) / self.rate if self.rate > 0 else 1.0
            if self.clock() + wait > end:
                raise RateLimited("лимит запросов T-Invest")
            self.sleep(min(max(wait, 0.02), 1.0))


# Корневой сертификат Минцифры (Russian Trusted Root CA): API Т-Банка подписан им, стандартный Python его не знает.
# Копия RUSSIAN_TRUSTED_ROOT_CA из src/py/02_certs.py — tests/test_flows.py проверяет, что они совпадают.
RUSSIAN_TRUSTED_ROOT_CA = """
-----BEGIN CERTIFICATE-----
MIIFwjCCA6qgAwIBAgICEAAwDQYJKoZIhvcNAQELBQAwcDELMAkGA1UEBhMCUlUx
PzA9BgNVBAoMNlRoZSBNaW5pc3RyeSBvZiBEaWdpdGFsIERldmVsb3BtZW50IGFu
ZCBDb21tdW5pY2F0aW9uczEgMB4GA1UEAwwXUnVzc2lhbiBUcnVzdGVkIFJvb3Qg
Q0EwHhcNMjIwMzAxMjEwNDE1WhcNMzIwMjI3MjEwNDE1WjBwMQswCQYDVQQGEwJS
VTE/MD0GA1UECgw2VGhlIE1pbmlzdHJ5IG9mIERpZ2l0YWwgRGV2ZWxvcG1lbnQg
YW5kIENvbW11bmljYXRpb25zMSAwHgYDVQQDDBdSdXNzaWFuIFRydXN0ZWQgUm9v
dCBDQTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAMfFOZ8pUAL3+r2n
qqE0Zp52selXsKGFYoG0GM5bwz1bSFtCt+AZQMhkWQheI3poZAToYJu69pHLKS6Q
XBiwBC1cvzYmUYKMYZC7jE5YhEU2bSL0mX7NaMxMDmH2/NwuOVRj8OImVa5s1F4U
zn4Kv3PFlDBjjSjXKVY9kmjUBsXQrIHeaqmUIsPIlNWUnimXS0I0abExqkbdrXbX
YwCOXhOO2pDUx3ckmJlCMUGacUTnylyQW2VsJIyIGA8V0xzdaeUXg0VZ6ZmNUr5Y
Ber/EAOLPb8NYpsAhJe2mXjMB/J9HNsoFMBFJ0lLOT/+dQvjbdRZoOT8eqJpWnVD
U+QL/qEZnz57N88OWM3rabJkRNdU/Z7x5SFIM9FrqtN8xewsiBWBI0K6XFuOBOTD
4V08o4TzJ8+Ccq5XlCUW2L48pZNCYuBDfBh7FxkB7qDgGDiaftEkZZfApRg2E+M9
G8wkNKTPLDc4wH0FDTijhgxR3Y4PiS1HL2Zhw7bD3CbslmEGgfnnZojNkJtcLeBH
BLa52/dSwNU4WWLubaYSiAmA9IUMX1/RpfpxOxd4Ykmhz97oFbUaDJFipIggx5sX
ePAlkTdWnv+RWBxlJwMQ25oEHmRguNYf4Zr/Rxr9cS93Y+mdXIZaBEE0KS2iLRqa
OiWBki9IMQU4phqPOBAaG7A+eP8PAgMBAAGjZjBkMB0GA1UdDgQWBBTh0YHlzlpf
BKrS6badZrHF+qwshzAfBgNVHSMEGDAWgBTh0YHlzlpfBKrS6badZrHF+qwshzAS
BgNVHRMBAf8ECDAGAQH/AgEEMA4GA1UdDwEB/wQEAwIBhjANBgkqhkiG9w0BAQsF
AAOCAgEAALIY1wkilt/urfEVM5vKzr6utOeDWCUczmWX/RX4ljpRdgF+5fAIS4vH
tmXkqpSCOVeWUrJV9QvZn6L227ZwuE15cWi8DCDal3Ue90WgAJJZMfTshN4OI8cq
W9E4EG9wglbEtMnObHlms8F3CHmrw3k6KmUkWGoa+/ENmcVl68u/cMRl1JbW2bM+
/3A+SAg2c6iPDlehczKx2oa95QW0SkPPWGuNA/CE8CpyANIhu9XFrj3RQ3EqeRcS
AQQod1RNuHpfETLU/A2gMmvn/w/sx7TB3W5BPs6rprOA37tutPq9u6FTZOcG1Oqj
C/B7yTqgI7rbyvox7DEXoX7rIiEqyNNUguTk/u3SZ4VXE2kmxdmSh3TQvybfbnXV
4JbCZVaqiZraqc7oZMnRoWrXRG3ztbnbes/9qhRGI7PqXqeKJBztxRTEVj8ONs1d
WN5szTwaPIvhkhO3CO5ErU2rVdUr89wKpNXbBODFKRtgxUT70YpmJ46VVaqdAhOZ
D9EUUn4YaeLaS8AjSF/h7UkjOibNc4qVDiPP+rkehFWM66PVnP1Msh93tc+taIfC
EYVMxjh8zNbFuoc7fzvvrFILLe7ifvEIUqSVIC/AzplM/Jxw7buXFeGP1qVCBEHq
391d/9RAfaZ12zkwFsl+IKwE/OZxW8AHa9i1p4GO0YSNuczzEm4=
-----END CERTIFICATE-----
"""
_SSL_CTX = None


def ssl_context():
    """Системные корневые сертификаты + сертификат Минцифры (только внутри этого процесса)."""
    global _SSL_CTX
    if _SSL_CTX is None:
        ctx = ssl.create_default_context()
        if not ctx.cert_store_stats().get("x509_ca"):
            for path in ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/cert.pem"):
                if os.path.isfile(path):
                    try:
                        ctx.load_verify_locations(cafile=path)
                        break
                    except ssl.SSLError:
                        pass
        ctx.load_verify_locations(cadata=RUSSIAN_TRUSTED_ROOT_CA)
        _SSL_CTX = ctx
    return _SSL_CTX


def _default_post(url, body, headers, timeout):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def quotation(q):
    """{'units':'12','nano':340000000} -> 12.34."""
    if not isinstance(q, dict):
        return None
    try:
        return int(q.get("units") or 0) + int(q.get("nano") or 0) / 1e9
    except (TypeError, ValueError):
        return None


class MDClient:
    def __init__(self, token, limits=None, post=None, clock=time.monotonic, sleep=time.sleep):
        self._token = (token or "").strip()
        lim = dict(LIMITS)
        lim.update(limits or {})
        self.buckets = {s: Bucket(n, clock=clock, sleep=sleep) for s, n in lim.items()}
        self._post = post or _default_post
        self.calls = 0

    @property
    def enabled(self):
        return bool(self._token)

    def __repr__(self):
        return "<MDClient %s>" % mask(self._token)

    def call(self, service, method, body=None, priority=BACKGROUND, timeout=20, wait=30.0):
        if method not in ALLOWED.get(service, ()):
            raise NotAllowed("метод %s/%s не разрешён" % (service, method))
        if not self._token:
            raise MDError("токен не задан")
        self.buckets[service].acquire(priority, wait)
        self.calls += 1
        hd = {"Authorization": "Bearer " + self._token, "Content-Type": "application/json", "Accept": "application/json",
              "x-app-name": "tinvest-analytics-server"}
        try:
            code, raw = self._post(BASE + service + "/" + method, json.dumps(body or {}).encode("utf-8"), hd, timeout)
        except Exception as e:  # noqa: BLE001
            raise MDError("T-Invest недоступен: %s" % scrub(type(e).__name__ + " " + str(e), self._token))
        try:
            j = json.loads((raw or b"{}").decode("utf-8", "replace") or "{}")
        except ValueError:
            j = {}
        if code == 429:
            raise RateLimited("T-Invest: HTTP 429")
        if code != 200:
            msg = j.get("message") if isinstance(j, dict) else ""
            raise MDError("T-Invest HTTP %s %s" % (code, scrub(str(msg or "")[:200], self._token)))
        return j

    # — удобные обёртки —
    def last_trades(self, uid, frm, to, priority=BACKGROUND):
        """frm/to — RFC3339 (UTC). -> [{ts: unix, side: 'buy'|'sell', price, qty}]"""
        j = self.call("MarketDataService", "GetLastTrades",
                      {"instrumentId": uid, "from": frm, "to": to, "tradeSource": "TRADE_SOURCE_EXCHANGE"}, priority)
        return parse_trades(j)

    def order_book(self, uid, depth=20, priority=INTERACTIVE):
        j = self.call("MarketDataService", "GetOrderBook", {"instrumentId": uid, "depth": depth}, priority)
        return parse_book(j)

    def instruments(self, kind):
        m = {"share": "Shares", "bond": "Bonds", "etf": "Etfs"}[kind]
        j = self.call("InstrumentsService", m, {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}, BACKGROUND, timeout=60)
        return j.get("instruments") or []

    def find_by_ticker(self, ticker, class_code, priority=INTERACTIVE):
        j = self.call("InstrumentsService", "GetInstrumentBy",
                      {"idType": "INSTRUMENT_ID_TYPE_TICKER", "classCode": class_code, "id": ticker}, priority)
        return j.get("instrument") or {}

    def dividends(self, uid, frm, to, priority=INTERACTIVE):
        j = self.call("InstrumentsService", "GetDividends", {"instrumentId": uid, "from": frm, "to": to}, priority)
        return parse_dividends(j)

    def fundamentals(self, asset_uids, priority=BACKGROUND):
        """До 100 assetUid за вызов (вызывающий режет на пачки). -> {assetUid: показатели}."""
        j = self.call("InstrumentsService", "GetAssetFundamentals", {"assets": list(asset_uids)[:100]}, priority, timeout=60)
        return {f.get("assetUid"): norm_fund(f) for f in (j.get("fundamentals") or []) if f.get("assetUid")}

    def reports(self, uid, frm, to, priority=BACKGROUND):
        j = self.call("InstrumentsService", "GetAssetReports", {"instrumentId": uid, "from": frm, "to": to}, priority)
        return j.get("reports") or []


def _iso_ts(s):
    from datetime import datetime, timezone
    s = (s or "").strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?", s)
        if not m:
            return None
        d = datetime.fromisoformat(m.group(1))
        if m.group(2):
            d = d.replace(microsecond=int(float(m.group(2)) * 1e6))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def parse_trades(j):
    out = []
    for t in (j or {}).get("trades") or []:
        d = str(t.get("direction") or "")
        side = "buy" if d.endswith("BUY") else "sell" if d.endswith("SELL") else ""
        price, ts = quotation(t.get("price")), _iso_ts(t.get("time"))
        try:
            qty = int(t.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0
        if side and price is not None and ts is not None and qty > 0:
            out.append({"ts": ts, "side": side, "price": price, "qty": qty})
    out.sort(key=lambda x: x["ts"])
    return out


def parse_book(j):
    def side(rows):
        out = []
        for r in rows or []:
            p = quotation(r.get("price"))
            try:
                q = int(r.get("quantity") or 0)
            except (TypeError, ValueError):
                q = 0
            if p is not None and q > 0:
                out.append([p, q])
        return out
    j = j or {}
    return {"bids": side(j.get("bids")), "asks": side(j.get("asks")), "last": quotation(j.get("lastPrice")),
            "limit_up": quotation(j.get("limitUp")), "limit_down": quotation(j.get("limitDown")),
            "ts": _iso_ts(j.get("orderbookTs")) or time.time()}


def _d(s):
    s = str(s or "")
    return None if not s or s.startswith("1970") else s[:10]


def parse_dividends(j):
    """GetDividends -> [{record, payment, declared, last_buy, value, currency, yield_pct}], свежие первыми."""
    out = []
    for x in (j or {}).get("dividends") or []:
        v, rec = quotation(x.get("dividendNet")), _d(x.get("recordDate"))
        if not v or not rec:
            continue
        y = quotation(x.get("yieldValue"))
        out.append({"record": rec, "payment": _d(x.get("paymentDate")), "declared": _d(x.get("declaredDate")),
                    "last_buy": _d(x.get("lastBuyDate")), "value": v,
                    "currency": str((x.get("dividendNet") or {}).get("currency") or "rub").upper(),
                    "yield_pct": round(y, 2) if y else None})
    out.sort(key=lambda r: r["record"], reverse=True)
    return out


def norm_fund(f):
    """Показатели GetAssetFundamentals; 0 у P/E, P/B, EV/EBITDA = «нет данных». Проценты уже в процентных пунктах."""
    def g(k, zero_none=True):
        v = quotation(f.get(k)) if isinstance(f.get(k), dict) else f.get(k)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return None if v != v or v in (float("inf"), float("-inf")) or (zero_none and v == 0) else v
    dy = g("dividendYieldDailyTtm", False) or g("forwardAnnualDividendYield", False)
    return {"pe": g("peRatioTtm"), "pb": g("priceToBookTtm"), "ev_ebitda": g("evToEbitdaMrq"), "div_yield": dy,
            "rev_growth": g("oneYearAnnualRevenueGrowthRate", False), "roe": g("roe", False),
            "nd_ebitda": g("netDebtToEbitda", False), "net_income": g("netIncomeTtm", False),
            "cap": g("marketCapitalization", False)}
