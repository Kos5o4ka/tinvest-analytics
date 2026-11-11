# ═══════════════════════════════ API-клиент ═══════════════════════════════

class ApiError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def q2d(v):
    """Quotation / MoneyValue -> Decimal (units и nano имеют одинаковый знак)."""
    if not v:
        return D0
    if isinstance(v, (int, float, str)):
        return Decimal(str(v))
    return Decimal(str(v.get("units") or "0")) + Decimal(int(v.get("nano") or 0)) / Decimal(10 ** 9)


def qf(v):
    return float(q2d(v))


def cur_of(v, default="rub"):
    return ((v or {}).get("currency") or default).lower() if isinstance(v, dict) else default


def to_money(amount, currency="rub"):
    amount = Decimal(str(amount))
    units = int(amount)
    return {"currency": currency, "units": str(units), "nano": int((amount - units) * 10 ** 9)}


def iso_date(s):
    """'2026-01-15T00:00:00Z' -> '2026-01-15'; пустые даты API (1970 год) -> None."""
    if not s or str(s).startswith("1970"):
        return None
    return str(s)[:10]


def utc_now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


API_SEM = threading.BoundedSemaphore(10)      # одновременно не больше 10 запросов к API: не устраиваем шторм


class TInvest:
    _good_host = {}
    _ctx_cache = {}

    def __init__(self, cfg):
        self.token = (cfg.get("token") or "").strip()
        self.sandbox = bool(cfg.get("sandbox"))
        self.hosts = [h for h in cfg["hosts_sandbox" if self.sandbox else "hosts_prod"] if h]
        key = (cfg.get("ca_file") or "", bool(cfg.get("verify_ssl", True)))
        if key not in TInvest._ctx_cache:
            TInvest._ctx_cache[key] = make_ssl_context(*key)
        self.ctx = TInvest._ctx_cache[key]

    @property
    def ready(self):
        return bool(self.token)

    def call(self, service, method, body=None, timeout=60):
        if not self.token:
            raise ApiError("Не задан API-токен — откройте «Настройки».", 400)
        payload = json.dumps(body or {}).encode()
        pref = TInvest._good_host.get(self.sandbox)
        hosts = ([pref] if pref in self.hosts else []) + [h for h in self.hosts if h != pref]
        last = None
        for host in hosts:
            url = "%s/%s.%s/%s" % (host.rstrip("/"), CONTRACT, service, method)
            for attempt in range(6):
                req = urllib.request.Request(url, data=payload, method="POST", headers={
                    "Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                    "Accept": "application/json", "x-app-name": "tinvest-analytics"})
                try:
                    with API_SEM:
                        with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
                            TInvest._good_host[self.sandbox] = host
                            return json.loads(r.read().decode("utf-8") or "{}")
                except urllib.error.HTTPError as e:
                    raw = e.read().decode("utf-8", "replace")
                    if (e.code in (429, 503, 504) or (e.code >= 500 and "RESOURCE_EXHAUSTED" in raw)) and attempt < 5:
                        try:
                            wait = float(e.headers.get("x-ratelimit-reset") or 1)
                        except ValueError:
                            wait = 1.0
                        time.sleep(min(wait, 30) + 0.4 * (attempt + 1))
                        continue
                    try:
                        j = json.loads(raw)
                        msg = j.get("message") or j.get("description") or raw
                    except ValueError:
                        msg = raw[:300]
                    hint = {401: "токен недействителен или не подходит к режиму (боевой / песочница)",
                            403: "у токена нет прав на этот метод"}.get(e.code, "")
                    raise ApiError("%s: HTTP %s — %s%s" % (method, e.code, str(msg).strip(), (" (%s)" % hint) if hint else ""),
                                   e.code if e.code in (400, 401, 403, 404) else 502)
                except (urllib.error.URLError, OSError, ssl.SSLError) as e:
                    last = e
                    break
        hint = (" Сертификат сервера не прошёл проверку. Обычно так бывает, когда VPN, прокси или антивирус "
                "подменяет сертификаты: попробуйте отключить их.") if "CERTIFICATE" in str(last).upper() else ""
        raise ApiError("Нет связи с T-Invest API: %s.%s" % (last, hint))

    # — счета и портфель —
    def accounts(self):
        if self.sandbox:
            return self.call("SandboxService", "GetSandboxAccounts").get("accounts", [])
        return self.call("UsersService", "GetAccounts", {"status": "ACCOUNT_STATUS_ALL"}).get("accounts", [])

    def portfolio(self, acc):
        svc, m = ("SandboxService", "GetSandboxPortfolio") if self.sandbox else ("OperationsService", "GetPortfolio")
        return self.call(svc, m, {"accountId": acc, "currency": "RUB"})

    def margin(self, acc):
        if self.sandbox:
            return None
        try:
            return self.call("UsersService", "GetMarginAttributes", {"accountId": acc}, timeout=20)
        except ApiError:
            return None

    def operations(self, acc, dt_from, dt_to):
        svc, m = ("SandboxService", "GetSandboxOperationsByCursor") if self.sandbox else \
            ("OperationsService", "GetOperationsByCursor")
        items, cursor = [], ""
        for _ in range(5000):
            r = self.call(svc, m, {"accountId": acc, "from": dt_from, "to": dt_to, "cursor": cursor, "limit": 1000,
                                   "state": "OPERATION_STATE_EXECUTED", "withoutCommissions": False,
                                   "withoutTrades": False, "withoutOvernights": False}, timeout=120)
            items.extend(r.get("items") or [])
            if not r.get("hasNext") or not r.get("nextCursor") or r.get("nextCursor") == cursor:
                break
            cursor = r["nextCursor"]
        return items

    # — справочники и рыночные данные —
    def instrument(self, uid=None, figi=None):
        body = {"idType": "INSTRUMENT_ID_TYPE_UID", "id": uid} if uid else {"idType": "INSTRUMENT_ID_TYPE_FIGI", "id": figi}
        return self.call("InstrumentsService", "GetInstrumentBy", body, timeout=20).get("instrument") or {}

    def bond_by(self, uid):
        return self.call("InstrumentsService", "BondBy", {"idType": "INSTRUMENT_ID_TYPE_UID", "id": uid},
                         timeout=20).get("instrument") or {}

    def bond_coupons(self, uid, frm, to):
        return self.call("InstrumentsService", "GetBondCoupons",
                         {"instrumentId": uid, "from": frm, "to": to}, timeout=30).get("events") or []

    def dividends(self, uid, frm, to):
        return self.call("InstrumentsService", "GetDividends",
                         {"instrumentId": uid, "from": frm, "to": to}, timeout=20).get("dividends") or []

    def instruments_all(self, kind):
        """Справочник доступных инструментов одним запросом: kind in Bonds / Shares / Etfs (пакетно вместо GetInstrumentBy)."""
        return self.call("InstrumentsService", kind, {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}, timeout=90).get("instruments") or []

    def find(self, query):
        return self.call("InstrumentsService", "FindInstrument", {"query": query}, timeout=20).get("instruments") or []

    def candles(self, uid, frm, to):
        return self.call("MarketDataService", "GetCandles",
                         {"instrumentId": uid, "from": frm, "to": to, "interval": "CANDLE_INTERVAL_DAY"},
                         timeout=30).get("candles") or []

    def last_prices(self, uids):
        out = {}
        for i in range(0, len(uids), 300):
            r = self.call("MarketDataService", "GetLastPrices", {"instrumentId": uids[i:i + 300]}, timeout=30)
            for p in r.get("lastPrices") or []:
                k = p.get("instrumentUid") or p.get("figi")
                if k and p.get("price"):
                    out[k] = qf(p["price"])
        return out


def pool_map(fn, items, workers=8):
    items = list(items)
    if not items:
        return []
    if len(items) == 1:
        return [fn(items[0])]
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
        return list(ex.map(fn, items))


