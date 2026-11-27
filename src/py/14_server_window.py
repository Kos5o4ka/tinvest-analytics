# ═══════════════════════════════ HTTP-сервер ═══════════════════════════════

_ping = [0.0]
_font_cache = []
_active_server = [None]
START_PAGES = {
    "dash", "ret", "bench", "pos", "bonds", "pay", "off", "ops", "fees", "tax", "reb", "calc", "lad",
    "mkt", "scr", "cmp", "map", "hm", "sig", "risk", "mon", "watch", "iss", "dfl", "flw", "pri", "fng",
    "cal", "kb", "imp", "set", "stk", "sst", "crp", "mic", "ofz", "pm", "txo", "dgap", "mm", "arb", "dbx", "rot",
}


def font_inter_bytes():
    """Встроенный шрифт Inter (variable woff2) для интерфейса: работает без сети и одинаково на Windows, macOS и Linux."""
    if not _font_cache:
        _font_cache.append(base64.b64decode(FONT_INTER_B64))
    return _font_cache[0]
# секреты, которые окно настроек может показать по кнопке «глаз» (GET /api/config/secret)
UI_SECRET_NAMES = ("token", "data_key", "backup_password")


class Handler(BaseHTTPRequestHandler):
    server_version = "TAnalytic/3.0"

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str).encode()
        elif isinstance(body, str):
            body = body.encode()
        gz = len(body) > 2048 and ctype.startswith(("application/json", "text/")) and \
            "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz:
            body = gzip.compress(body, 5)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=604800" if ctype in ("image/png", "font/woff2") else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def ok_host(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % port, "localhost:%d" % port, "[::1]:%d" % port)

    def guard(self, fn):
        try:
            fn()
        except ApiError as e:
            self.send(e.status if 400 <= e.status < 600 else 502, {"error": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.send(500, {"error": "%s: %s" % (type(e).__name__, e)})

    def _reply(self, res):
        if isinstance(res, tuple):
            code, body = res[0], res[1]
            ctype = res[2] if len(res) > 2 and res[2] else "application/json; charset=utf-8"
            return self.send(code, body, ctype, res[3] if len(res) > 3 else None)
        return self.send(200, res)

    def do_GET(self):
        if not self.ok_host():
            return self.send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        if u.path.startswith("/api/") and self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            return self.send(403, {"error": "forbidden"})
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        def run():
            if u.path == "/":
                return self.send(200, PAGE, "text/html; charset=utf-8")
            if u.path == "/fonts/InterVariable.woff2":
                return self.send(200, font_inter_bytes(), "font/woff2")
            if u.path.startswith("/logo/"):
                data = logo_bytes(unquote(u.path[6:]))
                return self.send(200, data, "image/png") if data else self.send(404, {"error": "no logo"})
            if u.path == "/api/ping":
                _ping[0] = time.time()
                return self.send(200, {"ok": True, "app": APP_NAME})
            cfg = load_config()
            if u.path.startswith("/api/") and u.path not in ("/api/ping", "/api/lock/status") and lock_is_locked(cfg):
                return self.send(423, {"error": "Программа заблокирована", "locked": True})
            f = q.get("force") == "1"
            acc = q.get("account", "all") or "all"
            if u.path == "/api/config":
                pub = {k: v for k, v in cfg.items() if k not in SECRET_KEYS}
                pub["secret_set"] = {k: bool(cfg.get(k)) for k in SECRET_KEYS if k != "token"}
                pub.update(token_set=bool(cfg["token"]), token_hint=("…" + cfg["token"][-4:]) if cfg["token"] else "",
                           imports=[dict(x, broker_id=broker_of_account(x)[0]) for x in imports_list()],
                           brokers=BROKERS, data_dir=APP_DIR, version=APP_VERSION)
                return self.send(200, pub)
            if u.path == "/api/config/secret":
                # Сохранённый секрет — только своему окну: Host проверен выше, плюс собственный заголовок
                # (чужая страница не может его поставить без CORS-preflight, который мы не разрешаем). Не логируем.
                if self.headers.get("X-TA-Secret") != "1" or \
                        self.headers.get("Sec-Fetch-Site") not in (None, "same-origin"):
                    return self.send(403, {"error": "forbidden"})
                name = q.get("name", "")
                if name not in UI_SECRET_NAMES or name not in SECRET_KEYS:
                    return self.send(400, {"error": "unknown secret"})
                return self.send(200, {"name": name, "value": str(cfg.get(name) or "")})
            if u.path == "/api/summary":
                return self.send(200, build_summary(cfg, acc, q.get("period", "all"), f))
            if u.path == "/api/bonds":
                return self.send(200, build_bonds(cfg, acc, f))
            if u.path == "/api/history":
                return self.send(200, build_history_for(cfg, acc, f))
            if u.path == "/api/operations.csv":
                data = build_summary(cfg, acc, q.get("period", "all"))
                return self.send(200, operations_csv(data), "text/csv; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="operations.csv"'})
            if u.path == "/api/screener":
                return self.send(200, screener_payload())
            if u.path == "/api/spark":
                try:
                    return self.send(200, spark_payload([x for x in (q.get("ids") or "").split(",") if x][:SPARK_MAX_IDS]))
                except Exception:  # noqa: BLE001
                    return self.send(200, {})
            if u.path == "/api/bond":
                return self.send(200, bond_card(q.get("isin", "")))
            if u.path == "/api/primary":
                return self.send(200, primary_payload())
            if u.path == "/api/ratings":
                return self.send(200, ratings_status())
            if u.path == "/api/keyrate":
                return self.send(200, keyrate_brief() or {"source": "none", "name": "", "yearly": []})
            if u.path == "/api/risk":
                return self.send(200, build_risk(cfg, acc, q))
            if u.path == "/api/signals":
                return self.send(200, signals_payload(cfg, acc, q))
            if u.path == "/api/monitor":
                return self.send(200, build_monitor(cfg, acc))
            if u.path == "/api/bench":
                return self.send(200, bench_payload(cfg, acc, q))
            if u.path == "/api/calc":
                return self.send(200, calc_params(cfg, acc))
            if u.path == "/api/offers":
                return self.send(200, offers_payload(cfg, acc))
            if u.path == "/api/ladder":
                return self.send(200, ladder_payload(cfg, q))
            if u.path == "/api/rates":
                return self.send(200, rates_payload(q.get("days", "365"), q.get("terms", "2")))
            if u.path == "/api/backup":
                return self.send(200, make_backup(), "application/zip",
                                 {"Content-Disposition": 'attachment; filename="tinvest_backup_%s.zip"' % date.today().isoformat()})
            if u.path == "/api/import/template.csv":
                return self.send(200, TEMPLATE_CSV.encode("utf-8-sig"), "text/csv; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="import_template.csv"'})
            fn = API_GET.get(u.path)
            if fn:
                return self._reply(fn(cfg, acc, q, f))
            self.send(404, {"error": "not found"})
        self.guard(run)

    def do_POST(self):
        # Sec-Fetch-Site: запросы с чужих сайтов отклоняем (защита от CSRF; старые браузеры заголовок не шлют)
        if not self.ok_host() or "application/json" not in (self.headers.get("Content-Type") or "") \
                or self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
            return self.send(403, {"error": "forbidden"})
        path = urlparse(self.path).path

        def run():
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                raise ApiError("Некорректный заголовок Content-Length.", 400)
            if n < 0 or n > 80 * 1024 * 1024:
                raise ApiError("Файл слишком большой (больше 60 МБ)." if n > 0 else "Некорректный заголовок Content-Length.", 400)
            try:
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except (ValueError, UnicodeDecodeError):
                raise ApiError("Некорректный JSON.", 400)
            if not isinstance(body, dict):
                raise ApiError("Ожидался JSON-объект.", 400)
            cfg = load_config()
            if path.startswith("/api/") and path not in ("/api/lock/unlock", "/api/app/shutdown") and lock_is_locked(cfg):
                return self.send(423, {"error": "Программа заблокирована", "locked": True})
            if path == "/api/app/shutdown":
                def _stop():
                    time.sleep(0.05)
                    srv = _active_server[0]
                    if srv is not None:
                        try:
                            srv.shutdown()
                        except Exception:  # noqa: BLE001
                            pass
                    app_shutdown()
                threading.Thread(target=_stop, daemon=True, name="app-shutdown").start()
                return self.send(200, {"ok": True})
            if path == "/api/config":
                if body.get("token"):
                    cfg["token"] = "".join(str(body["token"]).split())
                if body.get("clear_token"):
                    cfg["token"] = ""
                for k in ("sandbox", "verify_ssl"):
                    if k in body:
                        cfg[k] = bool(body[k])
                if "ca_file" in body:
                    cfg["ca_file"] = str(body["ca_file"]).strip()
                if body.get("theme") in ("auto", "dark", "light"):
                    cfg["theme"] = body["theme"]
                if body.get("start_page") in START_PAGES:
                    cfg["start_page"] = body["start_page"]
                if isinstance(body.get("ui_prefs"), dict):
                    prefs = dict(cfg.get("ui_prefs") if isinstance(cfg.get("ui_prefs"), dict) else {})
                    for k, v in list(body["ui_prefs"].items())[:40]:
                        k = str(k)[:40]
                        if v is None:
                            prefs.pop(k, None)
                        elif isinstance(v, (bool, int, float)) and not (isinstance(v, float) and (v != v or abs(v) >= 1e15)):
                            prefs[k] = v
                        elif isinstance(v, str):
                            prefs[k] = v[:120]
                    cfg["ui_prefs"] = dict(list(prefs.items())[:60])
                if isinstance(body.get("targets"), dict):
                    tg = {}
                    for k, v in body["targets"].items():
                        try:
                            x = float(v)
                        except (TypeError, ValueError):
                            continue
                        if 0 < x <= 100:
                            tg[str(k)[:24]] = round(x, 2)
                    cfg["targets"] = tg
                if isinstance(body.get("ui_seen"), dict):
                    seen = dict(cfg.get("ui_seen") if isinstance(cfg.get("ui_seen"), dict) else {})
                    for k, v in body["ui_seen"].items():
                        k = str(k)[:40]
                        if isinstance(v, bool) or (isinstance(v, (int, float)) and abs(v) < 1e15):
                            seen[k] = v
                        elif isinstance(v, str):
                            seen[k] = v[:64]
                        elif isinstance(v, dict):
                            seen[k] = {str(a)[:40]: (1 if b else 0) for a, b in list(v.items())[:80]}
                    cfg["ui_seen"] = dict(list(seen.items())[:40])
                if isinstance(body.get("broker_tariffs"), dict):
                    bt = dict(cfg.get("broker_tariffs") if isinstance(cfg.get("broker_tariffs"), dict) else {})
                    for k, v in list(body["broker_tariffs"].items())[:200]:
                        k = str(k)[:64]
                        if not v:
                            bt.pop(k, None)
                        elif isinstance(v, str) and re.fullmatch(r"[a-z0-9_]{1,40}", v):
                            bt[k] = v
                    cfg["broker_tariffs"] = bt
                if body.get("keyrate_mode") in KR_MODES:
                    cfg["keyrate_mode"] = body["keyrate_mode"]
                if "notify_days" in body:
                    try:
                        cfg["notify_days"] = max(0, min(60, int(body["notify_days"])))
                    except (TypeError, ValueError):
                        pass
                for k, lo, hi in (("mon_drop5", 0.1, 50), ("mon_drop30", 0.1, 90), ("mon_spread30", 0.1, 50),
                                  ("mon_sell_days", 0.5, 365), ("mon_offer_days", 1, 365)):
                    if k in body:
                        try:
                            cfg[k] = max(lo, min(hi, float(body[k])))
                        except (TypeError, ValueError):
                            pass
                for k in ("hosts_prod", "hosts_sandbox"):
                    if isinstance(body.get(k), list):
                        hosts = [str(h).strip() for h in body[k] if str(h).strip()]
                        if hosts:
                            cfg[k] = hosts
                if str(cfg.get("data_server") or "").strip().lower() == "off":
                    cfg["data_server"] = ""         # «off» из прежних версий: сервер данных теперь не отключается
                if body.get("data_key"):
                    cfg["data_key"] = "".join(str(body["data_key"]).split())
                if body.get("clear_data_key"):
                    cfg["data_key"] = ""
                if cfg["ca_file"] and not os.path.isfile(cfg["ca_file"]):
                    raise ApiError("Файл сертификата не найден: " + cfg["ca_file"], 400)
                save_config(cfg)
                ds_reset()
                mem_clear(persist=False)        # сохранённые отчёты привязаны к токену (token_key): настройки их не портят
                if "targets" in body or "broker_tariffs" in body:
                    sync_kick_safe()
                return self.send(200, {"ok": True, "app": APP_NAME})
            if path == "/api/ratings/refresh":
                return self.send(200, {"started": ratings_start(force=True), **ratings_status()})
            client = TInvest(cfg)
            if path == "/api/test":
                tcli = client
                if body.get("token"):
                    tcfg = dict(cfg, token="".join(str(body["token"]).split()))
                    if "sandbox" in body:
                        tcfg["sandbox"] = bool(body["sandbox"])
                    tcli = TInvest(tcfg)
                return self.send(200, {"ok": True, "accounts": len(tcli.accounts())})
            if path == "/api/cache/clear":
                clear_local_cache()
                st = store()
                with st.wlock:
                    c = st.conn()
                    c.execute("DELETE FROM ops WHERE acc NOT LIKE 'imp-%'")
                    c.commit()
                mem_clear()
                return self.send(200, {"ok": True, "app": APP_NAME})
            if path == "/api/import/preview":
                raw = base64.b64decode(body.get("data") or "")
                pv = import_preview_any(body.get("filename") or "", raw)
                bid = broker_detect_import(body.get("filename") or "", raw, pv.get("format") or "")
                pv["broker_id"], pv["broker_name"] = bid, BROKERS[bid]
                return self.send(200, pv)
            if path == "/api/import/parse":
                return self.send(200, import_parse_info(body))
            if path == "/api/import/commit":
                with _man_lock:
                    res = import_commit(client, body)
                return self.send(200, res)
            if path == "/api/import/broker":
                bid = str(body.get("broker_id") or "")
                if bid not in BROKERS:
                    raise ApiError("Неизвестный брокер.", 400)
                with _man_lock:
                    lst = imports_list()
                    ex = next((x for x in lst if x["id"] == body.get("id")), None)
                    if ex is None:
                        raise ApiError("Импортированный счёт не найден.", 404)
                    ex["broker_id"] = bid
                    store().put("imports", lst)
                mem_clear()
                return self.send(200, {"ok": True, "broker_id": bid})
            if path == "/api/import/delete":
                with _man_lock:
                    lst = [x for x in imports_list() if x["id"] != body.get("id")]
                    store().put("imports", lst)
                    store().ops_clear(body.get("id") or "")
                    sync_mark_deleted_safe(body.get("id"))
                mem_clear()
                sync_kick_safe()
                return self.send(200, {"ok": True, "app": APP_NAME})
            if path in ("/api/sandbox/open", "/api/sandbox/payin"):
                if not cfg["sandbox"]:
                    raise ApiError("Доступно только в режиме песочницы.", 400)
                mem_clear()
                if path.endswith("open"):
                    return self.send(200, client.call("SandboxService", "OpenSandboxAccount", {"name": "Analytics"}))
                amount = Decimal(str(body.get("amount") or 0))
                if amount <= 0:
                    raise ApiError("Сумма должна быть больше нуля.", 400)
                acc = body.get("accountId")
                if not acc or acc == "all" or str(acc).startswith("imp-"):
                    raise ApiError("Выберите счёт песочницы в списке слева.", 400)
                return self.send(200, client.call("SandboxService", "SandboxPayIn", {"accountId": acc, "amount": to_money(amount)}))
            fn = API_POST.get(path)
            if fn:
                return self._reply(fn(cfg, body))
            self.send(404, {"error": "not found"})
        if path in CONFIG_RMW_PATHS:                # «прочитать — изменить — записать» config.json по очереди,
            with _cfg_post_lock:                     # иначе параллельные сохранения теряют правки друг друга
                self.guard(run)
        else:
            self.guard(run)


# ═══════════════════════════════ окно приложения ═══════════════════════════════

def find_app_browser():
    sysname = platform.system()
    cands = []
    if sysname == "Windows":
        for r in filter(None, [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]):
            cands += [os.path.join(r, "Google", "Chrome", "Application", "chrome.exe"),
                      os.path.join(r, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(r, "Yandex", "YandexBrowser", "Application", "browser.exe"),
                      os.path.join(r, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")]
    elif sysname == "Darwin":
        for app, exe in (("Google Chrome", "Google Chrome"), ("Microsoft Edge", "Microsoft Edge"),
                         ("Yandex", "Yandex"), ("Brave Browser", "Brave Browser"), ("Chromium", "Chromium")):
            for base in ("/Applications", os.path.expanduser("~/Applications")):
                cands.append(os.path.join(base, app + ".app", "Contents", "MacOS", exe))
    else:
        for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
                  "yandex-browser", "brave-browser"):
            p = shutil.which(n)
            if p:
                cands.append(p)
    return next((c for c in cands if c and os.path.isfile(c)), None)


def open_window(url):
    if sys.platform == "win32":                                  # своя иконка в панели задач, а не python.exe
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TAnalytic.App")
        except Exception:
            pass
    exe = find_app_browser()
    if exe:
        try:
            return subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + os.path.join(APP_DIR, "window"),
                                     "--window-size=1480,940", "--no-first-run", "--no-default-browser-check",
                                     "--disable-features=Translate"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
    webbrowser.open(url)
    return None


_cfg_post_lock = threading.Lock()
CONFIG_RMW_PATHS = {"/api/config", "/api/lock/setup", "/api/shell/tray"}


class LocalHTTPServer(ThreadingHTTPServer):
    """Сервер только на 127.0.0.1. Стандартный server_bind вызывает socket.getfqdn(): обратный DNS-запрос
    по адресу машины на macOS идёт через mDNS и вызывает запрос «разрешить находить устройства в локальной сети»,
    а до ответа на него запуск зависает. Имя хоста серверу не нужно."""
    daemon_threads = True

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


def running_instance(url, timeout=1.5):
    """По адресу уже отвечает эта же программа (а не чужой сервер на том же порту)."""
    try:
        with urllib.request.urlopen(url + "api/ping", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}").get("app") == APP_NAME
    except Exception:  # noqa: BLE001
        return False


def app_shutdown():
    """Аккуратное завершение: журнал WAL сбрасывается в data.db, соединения закрываются (а не обрываются os._exit)."""
    for hook in SHUTDOWN_HOOKS:
        try:
            hook()
        except Exception:  # noqa: BLE001
            pass
    if STORE is None:
        return
    try:
        STORE.close_all()
    except Exception:  # noqa: BLE001
        pass


sys.tanalytic_shutdown = app_shutdown        # лаунчер вызывает перед выходом (собранное приложение)


def main():
    cfg = load_config()
    port = int(os.environ.get("TINVEST_PORT") or cfg["port"])
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    store()
    try:
        srv = LocalHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        other = "http://127.0.0.1:%d/" % port
        if running_instance(other):                  # программа уже открыта на этой базе: вторую копию не поднимаем
            print("%s уже запущен → %s" % (APP_NAME, other))
            if "--no-window" not in sys.argv:
                open_window(other)
            return
        srv = LocalHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("%s → %s   (Ctrl+C — выход)\nДанные: %s" % (APP_NAME, url, APP_DIR))
    if "--no-window" not in sys.argv:
        proc = open_window(url)
        if proc:
            def watch():
                t0 = time.time()
                proc.wait()
                if time.time() - t0 > 8:
                    return srv.shutdown()
                while True:
                    time.sleep(30)
                    if _ping[0] and time.time() - _ping[0] > 200:
                        return srv.shutdown()
            threading.Thread(target=watch, daemon=True).start()
    try:
        try:
            ratings_start()
        except Exception:  # noqa: BLE001
            pass
        try:
            warmup_start()
        except Exception:  # noqa: BLE001
            pass
        for hook in STARTUP_HOOKS:
            try:
                hook()
            except Exception:  # noqa: BLE001
                pass
        _active_server[0] = srv
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _active_server[0] = None
        srv.server_close()
        app_shutdown()
    # окно закрыто или Ctrl+C: фоновые расчёты (пулы потоков) прерываем сразу, иначе они падают с трассировкой
    # «cannot schedule new futures after interpreter shutdown». База SQLite транзакционная, данные не теряются.
    if not getattr(sys, "frozen", False):        # в собранном приложении выходом управляет лаунчер
        sys.stdout.flush()
        os._exit(0)


