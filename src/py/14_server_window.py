# ═══════════════════════════════ HTTP-сервер ═══════════════════════════════

_ping = [0.0]


class Handler(BaseHTTPRequestHandler):
    server_version = "TInvestAnalytics/3.0"

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
        self.send_header("Cache-Control", "max-age=604800" if ctype == "image/png" else "no-store")
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
        return self.headers.get("Host", "") in ("127.0.0.1:%d" % port, "localhost:%d" % port)

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

    def do_GET(self):
        if not self.ok_host():
            return self.send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        def run():
            if u.path == "/":
                return self.send(200, PAGE, "text/html; charset=utf-8")
            if u.path.startswith("/logo/"):
                data = logo_bytes(unquote(u.path[6:]))
                return self.send(200, data, "image/png") if data else self.send(404, {"error": "no logo"})
            if u.path == "/api/ping":
                _ping[0] = time.time()
                return self.send(200, {"ok": True})
            cfg = load_config()
            f = q.get("force") == "1"
            acc = q.get("account", "all") or "all"
            if u.path == "/api/config":
                pub = {k: v for k, v in cfg.items() if k != "token"}
                pub.update(token_set=bool(cfg["token"]), token_hint=("…" + cfg["token"][-4:]) if cfg["token"] else "",
                           imports=imports_list(), data_dir=APP_DIR, version=APP_VERSION)
                return self.send(200, pub)
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
            if u.path == "/api/primary":
                return self.send(200, primary_payload())
            if u.path == "/api/ratings":
                return self.send(200, ratings_status())
            if u.path == "/api/rates":
                return self.send(200, rates_payload(q.get("days", "365")))
            if u.path == "/api/backup":
                return self.send(200, make_backup(), "application/zip",
                                 {"Content-Disposition": 'attachment; filename="tinvest_backup_%s.zip"' % date.today().isoformat()})
            if u.path == "/api/import/template.csv":
                return self.send(200, TEMPLATE_CSV.encode("utf-8-sig"), "text/csv; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="import_template.csv"'})
            self.send(404, {"error": "not found"})
        self.guard(run)

    def do_POST(self):
        if not self.ok_host() or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self.send(403, {"error": "forbidden"})
        path = urlparse(self.path).path

        def run():
            n = int(self.headers.get("Content-Length") or 0)
            if n > 80 * 1024 * 1024:
                raise ApiError("Файл слишком большой (больше 60 МБ).", 400)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            cfg = load_config()
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
                if "notify_days" in body:
                    try:
                        cfg["notify_days"] = max(0, min(60, int(body["notify_days"])))
                    except (TypeError, ValueError):
                        pass
                for k in ("hosts_prod", "hosts_sandbox"):
                    if isinstance(body.get(k), list):
                        hosts = [str(h).strip() for h in body[k] if str(h).strip()]
                        if hosts:
                            cfg[k] = hosts
                if cfg["ca_file"] and not os.path.isfile(cfg["ca_file"]):
                    raise ApiError("Файл сертификата не найден: " + cfg["ca_file"], 400)
                save_config(cfg)
                mem_clear()
                return self.send(200, {"ok": True})
            if path == "/api/ratings/refresh":
                return self.send(200, {"started": ratings_start(force=True), **ratings_status()})
            client = TInvest(cfg)
            if path == "/api/test":
                return self.send(200, {"ok": True, "accounts": len(client.accounts())})
            if path == "/api/cache/clear":
                store().wipe_cache()
                shutil.rmtree(LOGO_DIR, ignore_errors=True)
                mem_clear()
                return self.send(200, {"ok": True})
            if path == "/api/import/preview":
                raw = base64.b64decode(body.get("data") or "")
                return self.send(200, import_preview(body.get("filename") or "", raw))
            if path == "/api/import/parse":
                raw = base64.b64decode(body.get("data") or "")
                ops, skipped = import_ops(body.get("filename") or "", raw, int(body.get("table") or 0),
                                          int(body.get("header_row") or 0), body.get("mapping") or {})
                kinds = defaultdict(int)
                for o in ops:
                    kinds[classify(o["type"])] += 1
                sample = [[o["date"][:10], op_type(o), o.get("name") or "", op_qty(o), qf(o["payment"]), cur_of(o["payment"])]
                          for o in ops[:15]]
                return self.send(200, {"count": len(ops), "skipped": skipped, "kinds": kinds, "sample": sample,
                                       "from": ops[0]["date"][:10] if ops else None, "to": ops[-1]["date"][:10] if ops else None})
            if path == "/api/import/commit":
                raw = base64.b64decode(body.get("data") or "")
                ops, skipped = import_ops(body.get("filename") or "", raw, int(body.get("table") or 0),
                                          int(body.get("header_row") or 0), body.get("mapping") or {})
                if not ops:
                    raise ApiError("В файле не нашлось операций с выбранными колонками.", 400)
                ops, ids = finalize_import(client, ops)
                acc_id = body.get("target") if str(body.get("target") or "").startswith("imp-") else "imp-" + uuid.uuid4().hex[:10]
                lst = imports_list()
                ex = next((x for x in lst if x["id"] == acc_id), None)
                if ex is None:
                    ex = {"id": acc_id, "name": (body.get("name") or "").strip() or "Импорт " + date.today().strftime("%d.%m.%Y"),
                          "broker": (body.get("broker") or "").strip(), "created": utc_now_str(), "files": []}
                    lst.append(ex)
                ex["files"].append({"name": body.get("filename") or "", "count": len(ops), "at": utc_now_str()})
                store().ops_put(acc_id, ops)
                store().put("imports", lst)
                mem_clear()
                found = sum(1 for v in ids.values() if v.get("uid"))
                return self.send(200, {"ok": True, "id": acc_id, "count": len(ops), "skipped": skipped,
                                       "resolved": found, "idents": len(ids)})
            if path == "/api/import/delete":
                lst = [x for x in imports_list() if x["id"] != body.get("id")]
                store().put("imports", lst)
                store().ops_clear(body.get("id") or "")
                mem_clear()
                return self.send(200, {"ok": True})
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
            self.send(404, {"error": "not found"})
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


def main():
    cfg = load_config()
    port = int(os.environ.get("TINVEST_PORT") or cfg["port"])
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    store()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
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
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


