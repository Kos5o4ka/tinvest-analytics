#!/usr/bin/env python3
"""Лаунчер TAnalytic: проверяет обновления на GitHub, скачивает и запускает программу.

Запуск:  python3 tinvest.py          (--no-update — не проверять обновления,
                                       --no-gui — без окна, прогресс в консоли; то же TINVEST_NO_GUI=1)
Просмотр заставки без сети и без записи файлов (нужен pywebview):  TINVEST_SPLASH_DEMO=1 python3 tinvest.py
                                       (=net — ошибка сети с автозапуском, =checksum — неверная контрольная сумма)
Токен лаунчер не читает и никуда не отправляет: он лежит только в папке данных на этом компьютере.
"""
import hashlib, json, os, queue, re, socket, ssl, subprocess, sys, threading, time, urllib.request
from urllib.parse import urlparse

REPO = "Kos5o4ka/tinvest-analytics"
FILE = "tinvest_analytics.py"            # файл программы в релизе
SUMS = "SHA256SUMS"                      # строки вида «<sha256>  <имя файла>»
TITLE = "TAnalytic"
HOME = os.environ.get("TINVEST_HOME") or os.path.join(os.path.expanduser("~"), ".tinvest_analytics")
APP_DIR = os.path.join(HOME, "app")
APP, VER = os.path.join(APP_DIR, FILE), os.path.join(APP_DIR, "version.txt")
OK_HOSTS = ("api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
SHELL_REV = 3                            # ревизия оболочки (окно, иконка, экран обновления); программа сверяет её через TINVEST_SHELL_REV
                                         # 3 — заставка на pywebview и бесшовный переход в окно программы
os.environ["TINVEST_SHELL_REV"] = str(SHELL_REV)
FROZEN = bool(getattr(sys, "frozen", False))      # собрано PyInstaller: sys.executable — сам лаунчер, не Python


class Cancelled(Exception):
    pass


# ───────────────────────────── сеть и проверки ─────────────────────────────

def check_url(url):
    """Только HTTPS и только домены GitHub — и для исходного адреса, и для каждого редиректа."""
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in OK_HOSTS:
        raise ValueError("недопустимый адрес: " + url)
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """GitHub отдаёт файлы релиза через редирект на другой домен — проверяем и его."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ssl_context():
    ctx = ssl.create_default_context()
    # certifi добавляем к системному хранилищу всегда: на свежей Windows оно не пустое, но неполное
    # (корневые сертификаты докачиваются по требованию, а OpenSSL этого не умеет) — отсюда
    # CERTIFICATE_VERIFY_FAILED при обращении к GitHub; на python.org-Python для macOS списка нет вовсе.
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
        return ctx
    except Exception:
        pass
    if not ctx.cert_store_stats().get("x509_ca"):
        for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
            if os.path.isfile(p):
                try:
                    ctx.load_verify_locations(cafile=p)
                    break
                except ssl.SSLError:
                    pass
    return ctx


def fetch(url, limit=20_000_000, progress=None, cancel=None, opener=None):
    """Скачивает url кусками по 64 КБ. progress(скачано, всего, байт/с); cancel — threading.Event."""
    check_url(url)
    opener = opener or urllib.request.build_opener(SafeRedirect, urllib.request.HTTPSHandler(context=ssl_context()))
    req = urllib.request.Request(url, headers={"User-Agent": "tinvest-launcher"})
    buf, t0, last = bytearray(), time.time(), 0.0
    with opener.open(req, timeout=20) as r:
        total = int(r.headers.get("Content-Length") or 0)
        if total > limit:
            raise ValueError("слишком большой файл")
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = r.read(65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > limit:
                raise ValueError("слишком большой файл")
            now = time.time()
            if progress and now - last >= 0.1:
                last = now
                progress(len(buf), total, len(buf) / max(now - t0, 1e-3))
    if progress:
        progress(len(buf), total or len(buf), len(buf) / max(time.time() - t0, 1e-3))
    return bytes(buf)


def parse_sums(text, name):
    """Находит SHA256 файла name в SHA256SUMS (формат sha256sum; лишние строки допустимы)."""
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 2 and p[-1].lstrip("*") == name and re.fullmatch(r"[0-9a-fA-F]{64}", p[0]):
            return p[0].lower()
    raise ValueError("в %s нет контрольной суммы для %s" % (SUMS, name))


def update(report=lambda *a: None, cancel=None, fetch=fetch):
    """Обновляет программу. Возвращает "current" (уже последняя) или "updated". События — через report."""
    report("check")
    rel = json.loads(fetch("https://api.github.com/repos/%s/releases/latest" % REPO, cancel=cancel))
    tag = rel["tag_name"]
    have = ""
    if os.path.exists(VER) and os.path.exists(APP):
        with open(VER) as f:
            have = f.read().strip()
    if tag == have:
        report("current", tag)
        return "current"
    urls = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    if FILE not in urls or SUMS not in urls:
        raise ValueError("в релизе %s нет нужных файлов" % tag)
    report("download", tag)
    code = fetch(urls[FILE], progress=lambda d, t, s: report("progress", d, t, s), cancel=cancel)
    sums = fetch(urls[SUMS], cancel=cancel).decode()
    report("verify", tag)
    if hashlib.sha256(code).hexdigest() != parse_sums(sums, FILE):
        raise ValueError("не совпала контрольная сумма SHA256 — обновление отклонено")
    compile(code, FILE, "exec")                                # хотя бы синтаксически валидный Python
    if cancel is not None and cancel.is_set():
        raise Cancelled()                                      # до этой точки APP не тронут
    os.makedirs(APP_DIR, mode=0o700, exist_ok=True)
    tmp, bak = APP + ".tmp", APP + ".bak"
    with open(tmp, "wb") as f:
        f.write(code)
    moved = False
    try:
        if os.path.exists(APP):
            os.replace(APP, bak)                              # предыдущая версия остаётся как запасная
            moved = True
        os.replace(tmp, APP)                                   # атомарная подмена
    except Exception:
        if moved and not os.path.exists(APP) and os.path.exists(bak):
            try:
                os.replace(bak, APP)                           # откат рабочей версии при сбое замены
            except OSError:
                pass
        raise
    with open(VER, "w") as f:
        f.write(tag)
    return "updated"


def worker(q, cancel):
    """Сетевая работа в отдельном потоке; результат — в очередь (tk из потока трогать нельзя)."""
    try:
        q.put(("ok", update(lambda *e: q.put(e), cancel)))
    except Cancelled:
        q.put(("cancelled",))
    except (OSError, socket.timeout) as e:                     # URLError и HTTPError — тоже OSError
        q.put(("error", "Не удалось связаться с GitHub: %s" % (getattr(e, "reason", None) or e), True))
    except Exception as e:
        q.put(("error", str(e), False))


# ───────────────────────────── форматирование ─────────────────────────────

def ver(tag):
    return tag if tag[:1] in "vV" else "v" + tag


def mb(n):
    return ("%.1f" % (n / 1e6)).replace(".", ",")


def progress_text(done, total, speed):
    s = "%s из %s МБ" % (mb(done), mb(total)) if total else "%s МБ" % mb(done)
    return s + (" · %s МБ/с" % mb(speed) if speed else "")


def console_bar(done, total, speed, width=28):
    frac = min(1.0, done / total) if total else 0.0
    n = int(width * frac)
    pct = " %3d%%" % int(frac * 100) if total else ""
    return "[%s%s]%s  %s" % ("#" * n, "-" * (width - n), pct, progress_text(done, total, speed))


def have_app():
    return os.path.exists(APP) or os.path.exists(APP + ".bak")


# ───────────────────────────── интерфейс: консоль ─────────────────────────────

class Console:
    error = False

    def updating(self, q, cancel):
        """Ждёт результат обновления, рисуя прогресс в одной строке. Возвращает "run" или "quit"."""
        out = sys.stdout.write if sys.stdout else (lambda s: 0)
        try:
            while True:
                ev = q.get()
                if ev[0] == "check":
                    out("Проверка обновлений…\n")
                elif ev[0] == "current":
                    out("Последняя версия %s\n" % ver(ev[1]))
                elif ev[0] == "download":
                    out("Загрузка версии %s\n" % ver(ev[1]))
                elif ev[0] == "progress":
                    out("\r" + console_bar(*ev[1:]) + "  ")
                elif ev[0] == "verify":
                    out("\nПроверка контрольной суммы\n")
                elif ev[0] == "ok":
                    return "run"
                elif ev[0] == "cancelled":
                    return "quit"
                elif ev[0] == "error":
                    out("Обновление пропущено: %s\n" % ev[1])
                    if have_app():
                        return "run"
                    self.error = True
                    out("Программа ещё не скачана, а обновиться не удалось. Проверьте интернет.\n")
                    return "quit"
        except KeyboardInterrupt:
            cancel.set()
            return "quit"

    def close(self):
        pass


# ───────────────────────────── интерфейс: окно tkinter ─────────────────────────────
# Оформление как у самой программы (src/web/css/01_*.css). Только классические tk-виджеты и Canvas:
# ttk на macOS игнорирует цвета, а tk.Button — фон.

BG, SIDE, CARD, CARD2 = "#06080e", "#0a0d15", "#0f1420", "#161e30"
LINE, LINE2 = "#1a2236", "#26314b"
TX, TX2, MU = "#f8fafc", "#94a3b8", "#64748b"
AC, AC2, POS, NEG = "#3b82f6", "#60a5fa", "#3ecf8e", "#ff6b6b"
INK = "#ffffff"                                                  # текст на синей кнопке
FONTS = ("Inter", "SF Pro Text", ".AppleSystemUIFont", "Segoe UI", "Helvetica Neue", "Arial")
STEPS = ("Проверка", "Загрузка", "Проверка подписи", "Запуск")


def mix(a, b, t):
    """Цвет между a и b (t=0 → a, t=1 → b); для «приглушённых» состояний."""
    pa, pb = [[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in (a, b)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(pa, pb))


def rrect(c, x0, y0, x1, y1, r, **kw):
    """Скруглённый прямоугольник на Canvas (сглаженный многоугольник)."""
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


class Btn:
    """Кнопка на Canvas: primary (жёлтая) или ghost (контур), с наведением и «выключенным» видом."""
    def __init__(self, win, label, kind, cmd, x1, cy):
        c, u = win.c, win.u
        w, h = win.f_btn.measure(label) + u(36), u(34)
        self.c, self.kind, self.cmd, self.on, self.hover = c, kind, cmd, True, False
        self.tag = "btn%d" % id(self)
        self.x0 = x1 - w
        self.bg = rrect(c, self.x0, cy - h // 2, x1, cy + h // 2, u(9), tags=(self.tag,), width=1)
        self.tx = c.create_text((self.x0 + x1) // 2, cy, text=label, font=win.f_btn, tags=(self.tag,))
        c.tag_bind(self.tag, "<Enter>", lambda e: self.over(True))
        c.tag_bind(self.tag, "<Leave>", lambda e: self.over(False))
        c.tag_bind(self.tag, "<Button-1>", lambda e: self.on and self.cmd())
        self.paint()

    def over(self, on):
        self.hover = on
        self.paint()

    def enable(self, on=True):
        self.on = on
        self.paint()

    def paint(self):
        if self.kind == "primary":
            fill, line, fg = (AC2 if self.hover else AC), (AC2 if self.hover else AC), INK
            if not self.on:
                fill = line = mix(AC, CARD, 0.6)
                fg = mix(INK, CARD, 0.2)
        else:
            fill, line, fg = (CARD2 if self.hover else CARD), LINE2, TX
            if not self.on:
                fill, line, fg = CARD, LINE, MU
        self.c.itemconfigure(self.bg, fill=fill, outline=line)
        self.c.itemconfigure(self.tx, fill=fg)
        self.c.configure(cursor="hand2" if (self.on and self.hover) else "")

    def destroy(self):
        self.c.delete(self.tag)
        self.c.configure(cursor="")


def draw_logo(c, x, y, size):
    """Знак приложения (как в интерфейсе и иконке): синяя «Т» со стрелкой роста на тёмной подложке."""
    k = size / 32.0
    rrect(c, x, y, x + size, y + size, 9 * k, fill=CARD, outline=LINE2, width=1)
    rrect(c, x + 7 * k, y + 7 * k, x + 25 * k, y + 11.5 * k, 2 * k, fill=AC2, outline=AC2)    # перекладина
    rrect(c, x + 13.5 * k, y + 9 * k, x + 18.5 * k, y + 25 * k, 2 * k, fill=AC, outline=AC)   # ножка
    c.create_line(x + 18.5 * k, y + 16 * k, x + 24.5 * k, y + 10 * k, width=max(2, 2.2 * k),
                  fill="#7dd3fc", capstyle="round")
    c.create_line(x + 20.5 * k, y + 10 * k, x + 24.5 * k, y + 10 * k, x + 24.5 * k, y + 14 * k,
                  width=max(2, 2.2 * k), fill="#7dd3fc", capstyle="round", joinstyle="round")


class Window:
    W, H = 520, 300
    draw_logo = staticmethod(draw_logo)

    def __init__(self, tk):
        from tkinter import font as tkfont
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)    # чёткий текст на HiDPI
            except Exception:
                pass
        self.tk = tk
        self.root = r = tk.Tk()                                  # без дисплея здесь будет TclError
        r.title(TITLE)
        r.configure(bg=BG)
        r.resizable(False, False)
        self.S = max(1.0, r.winfo_fpixels("1i") / 96.0) if sys.platform == "win32" else 1.0
        u = self.u
        w, h = u(self.W), u(self.H)
        r.geometry("%dx%d+%d+%d" % (w, h, (r.winfo_screenwidth() - w) // 2, (r.winfo_screenheight() - h) // 3))
        have = set(tkfont.families(r))
        fam = next((f for f in FONTS if f in have), tkfont.nametofont("TkDefaultFont").actual("family"))

        def font(px, bold=False):                                # размер в пикселях → одинаково на всех системах
            return tkfont.Font(root=r, family=fam, size=-u(px), weight="bold" if bold else "normal")
        self.f_title, self.f_ver, self.f_step = font(17, True), font(12), font(12)
        self.f_stat, self.f_det, self.f_btn, self.f_logo = font(15, True), font(13), font(13, True), font(19, True)

        self.c = c = tk.Canvas(r, width=w, height=h, bg=BG, highlightthickness=0, bd=0)
        c.pack()
        rrect(c, u(16), u(16), w - u(16), h - u(16), u(16), fill=CARD, outline=LINE, width=1)
        self.draw_logo(c, u(40), u(36), u(36))
        c.create_text(u(90), u(38), text=TITLE, font=self.f_title, fill=TX, anchor="nw")
        self.ver_t = c.create_text(u(90), u(60), text="", font=self.f_ver, fill=MU, anchor="nw")
        self.set_version()

        self.step_items = []                                     # (ореол, точка, подпись) для каждого этапа
        for x, name in zip((40, 128, 224, 392), STEPS):
            halo = c.create_oval(u(x - 4), u(111), u(x + 12), u(127), outline=CARD, width=2)
            dot = c.create_oval(u(x), u(115), u(x + 8), u(123), outline="", fill=MU)
            lab = c.create_text(u(x + 16), u(119), text=name, font=self.f_step, fill=MU, anchor="w")
            self.step_items.append((halo, dot, lab))
        self.cur_step, self.step_err = 0, False

        self.dot = c.create_oval(0, 0, 0, 0, outline="", fill=POS, state="hidden")
        self.status = c.create_text(u(40), u(152), font=self.f_stat, fill=TX, anchor="nw", width=u(440))
        self.detail = c.create_text(u(40), u(178), font=self.f_det, fill=TX2, anchor="nw", width=u(440))
        self.hint = c.create_text(u(40), u(204), font=self.f_det, fill=MU, anchor="nw", width=u(440))

        self.bx0, self.bx1, self.by, self.bh = u(40), u(480), u(228), u(6)       # индикатор прогресса
        r_ = self.bh // 2
        self.track = c.create_line(self.bx0 + r_, self.by, self.bx1 - r_, self.by, width=self.bh, fill=LINE, capstyle="round")
        self.fill = c.create_line(0, 0, 0, 0, width=self.bh, fill=AC, capstyle="round", state="hidden")
        self.mode, self.target, self.disp, self.t0 = "indet", 0.0, 0.0, time.time()

        self.btns = []
        self.decision, self.busy, self.error, self.q = None, True, False, None
        self.tick = lambda: None
        self.dead_anim = False
        self.dark_titlebar()
        r.attributes("-topmost", True)                           # окно не должно прятаться за другими
        r.after(300, lambda: r.attributes("-topmost", False))
        self.animate()

    def u(self, v):
        return int(round(v * getattr(self, "S", 1.0)))

    def dark_titlebar(self):
        if sys.platform != "win32":                              # macOS сама подбирает заголовок по теме системы
            return
        try:
            import ctypes
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            val = ctypes.c_int(1)
            for attr in (20, 19):                                # DWMWA_USE_IMMERSIVE_DARK_MODE (новый и старый номер)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4)
        except Exception:
            pass

    # --- примитивы ---
    def set_version(self, tag=None):
        if tag is None:
            try:
                with open(VER) as f:
                    tag = f.read().strip()
            except OSError:
                tag = ""
        self.c.itemconfigure(self.ver_t, text=ver(tag) if tag else "")

    def say(self, text, detail="", dot=None, hint="", err=False):
        c, u = self.c, self.u
        x = u(40)
        if dot:
            x = u(58)
            c.coords(self.dot, u(40), u(158), u(50), u(168))
            c.itemconfigure(self.dot, fill=dot, state="normal")
        else:
            c.itemconfigure(self.dot, state="hidden")
        c.coords(self.status, x, u(152))
        c.itemconfigure(self.status, text=text, fill=NEG if err else TX, width=u(480) - x)
        c.itemconfigure(self.detail, text=detail, fill=TX if err else TX2)
        c.itemconfigure(self.hint, text=hint)

    def set_step(self, i, err=False):
        """Этап i — текущий, предыдущие — пройдены. err: текущий окрашивается в красный."""
        self.cur_step, self.step_err = i, err
        for n, (halo, dot, lab) in enumerate(self.step_items):
            col = POS if n < i else (NEG if err else AC) if n == i else MU
            self.c.itemconfigure(dot, fill=col)
            self.c.itemconfigure(halo, outline=mix(col, CARD, 0.7) if n == i else CARD)
            self.c.itemconfigure(lab, fill=TX if n == i else TX2 if n < i else MU)

    def show_steps(self, on):
        for it in self.step_items:
            for i in it:
                self.c.itemconfigure(i, state="normal" if on else "hidden")

    def bar(self, mode, value=0.0):
        """mode: "indet" (бегущий отрезок), "det" (value 0..1, плавно), "hidden"."""
        self.mode = mode
        if mode == "det":
            self.target = max(0.0, min(1.0, value))
        for i in (self.track,):
            self.c.itemconfigure(i, state="hidden" if mode == "hidden" else "normal")
        if mode == "hidden":
            self.c.itemconfigure(self.fill, state="hidden")

    def animate(self):
        """Кадр анимации индикатора (~60 к/с); сам себя перепланирует, пока окно живо."""
        try:
            self.draw_bar()
            self.root.after(16, self.animate)
        except Exception:                                        # окно уничтожено
            pass

    def draw_bar(self):
        c, W, r = self.c, self.bx1 - self.bx0, self.bh // 2
        s = e = 0.0
        if self.mode == "indet":
            L = W * 0.3
            t = ((time.time() - self.t0) * 0.85) % 1.0
            t = t * t * (3 - 2 * t)                              # ease in-out: отрезок разгоняется и тормозит
            p = -L + t * (W + L)
            s, e = max(0.0, p), min(float(W), p + L)
        elif self.mode == "det":
            self.disp += (self.target - self.disp) * 0.2
            if abs(self.target - self.disp) < 0.0005:
                self.disp = self.target
            s, e = 0.0, self.disp * W
            if 0 < e < 2 * r:
                e = 2 * r
        if self.mode == "hidden" or e - s < 2 * r:
            c.itemconfigure(self.fill, state="hidden")
            return
        c.coords(self.fill, self.bx0 + s + r, self.by, self.bx0 + e - r, self.by)
        c.itemconfigure(self.fill, state="normal")

    def buttons(self, items):
        """items — [(подпись, команда, "primary"/"ghost")] слева направо; раскладываются от правого края."""
        for b in self.btns:
            b.destroy()
        self.btns, x = [], self.u(480)
        for label, cmd, kind in reversed(items):
            b = Btn(self, label, kind, cmd, x, self.u(262))
            self.btns.insert(0, b)
            x = b.x0 - self.u(10)

    def finish(self, decision):
        self.decision = decision
        self.root.quit()

    def poll(self):
        if self.decision is not None:
            return
        try:
            while True:
                self.on_event(self.q.get_nowait())
        except queue.Empty:
            pass
        self.tick()
        self.root.after(50, self.poll)

    # --- этап обновления ---
    def updating(self, q, cancel):
        self.q, self.cancel = q, cancel
        self.bar("indet")
        self.set_step(0)
        self.say("Проверка обновлений…")
        self.buttons([("Отмена", self.on_cancel, "ghost")])
        self.root.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.root.after(30, self.poll)
        self.root.mainloop()
        return self.decision

    def on_cancel(self):
        if self.busy:
            self.cancel.set()
            self.say("Отмена…")
            self.btns[0].enable(False)
        else:
            self.finish("quit")

    def on_event(self, ev):
        k = ev[0]
        if k == "check":
            self.set_step(0)
            self.say("Проверка обновлений…")
        elif k == "current":
            self.set_version(ev[1])
            self.set_step(3)
            self.say("Последняя версия %s" % ver(ev[1]))
        elif k == "download":
            self.set_version(ev[1])
            self.set_step(1)
            self.bar("det", 0.0)
            self.disp = 0.0
            self.say("Загрузка версии %s" % ver(ev[1]))
        elif k == "progress":
            done, total, speed = ev[1:]
            if total:
                self.bar("det", float(done) / total)
            self.c.itemconfigure(self.detail, text=progress_text(done, total, speed))
        elif k == "verify":
            self.set_step(2)
            self.bar("indet")
            self.say("Проверка подписи", "Сверяю контрольную сумму SHA256")
        elif k == "ok":
            self.busy = False
            self.set_step(3)
            self.bar("det", 1.0)
            self.buttons([])
            if ev[1] == "current":
                self.root.after(400, self.finish, "run")        # без лишнего мельтешения
            else:
                self.say("Запуск…")
                self.root.after(300, self.finish, "run")
        elif k == "cancelled":
            self.busy = False
            self.finish("quit")
        elif k == "error":
            self.busy = False
            if ev[2] and have_app():                            # нет сети — просто запускаем скачанную версию
                self.bar("hidden")
                self.set_step(3)
                self.say("Нет связи с GitHub", "Запускаю установленную версию…")
                self.buttons([])
                self.root.after(1200, self.finish, "run")
            else:
                self.show_error(ev[1], have_app())

    def show_error(self, msg, can_run):
        self.error = True
        self.bar("hidden")
        self.set_step(self.cur_step, err=True)
        self.say("Ошибка", msg, dot=NEG, err=True)
        items = [("Закрыть", lambda: self.finish("quit"), "ghost")]
        if can_run:
            items.insert(0, ("Запустить текущую версию", lambda: self.finish("run"), "primary"))
        self.buttons(items)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.finish("quit"))

    # --- этап работы программы (только в собранном приложении) ---
    def running(self, thread, cap, result, native=False):
        """native: окно служит только заставкой, пока сервер не ответит; потом оно закрывается и возвращается "native"."""
        self.decision = None
        self.bar("hidden")
        self.show_steps(False)
        self.say("Программа запущена", "Запуск сервера…", dot=POS, hint="Закройте программу кнопкой «Выйти».")
        self.buttons([("Открыть в браузере", lambda: __import__("webbrowser").open(cap.url), "primary"),
                      ("Выйти", lambda: self.finish("quit"), "ghost")])
        self.btns[0].enable(False)                              # «Открыть» ждёт адрес сервера
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.finish("quit"))
        self.root.attributes("-topmost", False)

        self.q, self.dead = queue.Queue(), False

        def tick():
            if native and result.get("ready") and not self.dead:
                self.dead = True
                self.finish("native")
                return
            if cap.url and self.btns and not self.btns[0].on and not self.dead:
                self.btns[0].enable(True)
                self.c.itemconfigure(self.detail, text=cap.url)
            if not thread.is_alive() and not self.dead:
                self.dead = True
                if result.get("err"):
                    self.show_error("Программа остановилась с ошибкой:\n" + result["err"], False)
                else:
                    self.finish("quit")
        self.tick = tick
        if native:
            self.say("Запуск…", "Открываю окно программы", dot=POS)
            self.buttons([])
        self.root.after(200, self.poll)
        self.root.mainloop()
        if self.decision == "native":
            return "native"
        return result.get("code") or 0

    def close(self):
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        self.root = None
        import gc
        gc.collect()                                            # Tcl-объекты уходят до старта Cocoa-цикла pywebview


def make_window():
    try:
        import tkinter as tk
        return Window(tk)
    except Exception:                                           # нет tkinter или нет дисплея
        return None


# ───────────────────────────── запуск программы ─────────────────────────────

class Capture:
    """В окне без консоли stdout нет: ловим вывод программы, чтобы узнать адрес её сервера."""
    def __init__(self, orig):
        self.orig, self.url = orig, ""

    def write(self, s):
        m = re.search(r"http://127\.0\.0\.1:\d+/", s)
        if m:
            self.url = m.group(0)
        if self.orig:
            try:
                self.orig.write(s)
            except Exception:
                pass
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False


# ───────────────────────────── собственное окно (pywebview) ─────────────────────────────

WIN_W, WIN_H, MIN_W, MIN_H = 1440, 900, 1024, 680
STATE = os.path.join(HOME, "window.json")


def want_native(frozen, no_gui, env=None):
    """Собственное окно — только в собранном приложении с графикой; TINVEST_NO_WEBVIEW=1 отключает (запасной режим)."""
    env = os.environ if env is None else env
    return bool(frozen) and not no_gui and env.get("TINVEST_NO_WEBVIEW") != "1"


FRAME_SLACK = 16      # Windows держит невидимую рамку ресайза ~8 px: развёрнутое окно стоит в (-8, -8), это не «за экраном»


def window_geometry(saved, screen, want=(WIN_W, WIN_H), min_size=(MIN_W, MIN_H)):
    """(ширина, высота, x, y) окна. saved — dict из window.json (или None); screen — (ширина, высота) или None.
    Размер не больше экрана (с полями) и не меньше min_size, если экран позволяет. Позиция — сохранённая, если окно
    видно на экране, иначе по центру экрана (Windows без явных x/y ставит окно в левый верхний угол)."""
    def num(k, d=None):
        v = (saved or {}).get(k)
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else d
    w, h = num("w", want[0]), num("h", want[1])
    x, y = num("x"), num("y")
    if screen:
        sw, sh = screen
        w = min(w, max(sw - 40, 1)); h = min(h, max(sh - 80, 1))
        w = max(w, min(min_size[0], sw)); h = max(h, min(min_size[1], sh))
        if x is None or y is None or x < -w + 100 or y < -FRAME_SLACK or x > sw - 100 or y > sh - 100:
            x, y = center(w, h, screen)
        else:
            y = max(y, 0)
    elif w < min_size[0] or h < min_size[1]:
        w, h = max(w, min_size[0]), max(h, min_size[1])
    return w, h, x, y


def center(w, h, screen):
    """Левый верхний угол окна w×h по центру экрана (чуть выше середины — так окно смотрится ровнее)."""
    if not screen:
        return None, None
    sw, sh = screen
    return max(0, (sw - w) // 2), max(0, (sh - h) * 2 // 5)


def was_maximized(saved):
    return bool((saved or {}).get("maximized"))


def load_state():
    try:
        with open(STATE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def save_state(w, h, x, y, maximized=False):
    try:
        os.makedirs(HOME, mode=0o700, exist_ok=True)
        d = {"w": int(w), "h": int(h), "x": int(x), "y": int(y)}
        if maximized:
            d["maximized"] = True
        with open(STATE, "w") as f:
            json.dump(d, f)
    except Exception:
        pass


def looks_maximized(w, h, x, y, screen):
    """Окно занимает весь экран с отрицательной рамкой Windows (-8, -8) — значит, оно было развёрнуто."""
    if not screen:
        return False
    sw, sh = screen
    return x <= 0 and y <= 0 and w >= sw - 2 * FRAME_SLACK and h >= sh - 160


def wait_ping(get_url, thread, timeout=90):
    """Ждёт, пока сервер программы ответит на /api/ping. False — не дождались или программа остановилась."""
    end = time.time() + timeout
    while time.time() < end and thread.is_alive():
        url = get_url()
        if url:
            try:
                with urllib.request.urlopen(url + "api/ping", timeout=2) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
        time.sleep(0.15)
    return False


WEBVIEW_DIR = os.path.join(HOME, "webview")      # постоянный профиль WebView: тема, режим, меню переживают перезапуск


def start_kwargs():
    """Аргументы webview.start(): постоянный профиль вместо одноразового %TEMP%\\tmp*\\EBWebView
    (иначе localStorage — тема, режим «Профи», свёрнутое меню — стирается при каждом запуске)."""
    try:
        os.makedirs(WEBVIEW_DIR, mode=0o700, exist_ok=True)
    except OSError:
        pass
    return {"private_mode": False, "storage_path": WEBVIEW_DIR}


def screen_size(webview):
    """Рабочая область основного экрана (без панели задач Windows), иначе размер экрана pywebview."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
                return (r.right - r.left, r.bottom - r.top)
        except Exception:
            pass
    try:
        sc = webview.screens[0]
        return (sc.width, sc.height)
    except Exception:
        return None


def webview_setup(webview):
    """Общие настройки pywebview и геометрия окна программы (по window.json): (w, h, x, y, развёрнуто, экран)."""
    webview.settings["ALLOW_DOWNLOADS"] = True                  # выгрузки CSV/ICS по ссылкам
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # t.me, MOEX и прочие target=_blank — в обычный браузер
    screen = screen_size(webview)
    saved = load_state()
    return window_geometry(saved, screen) + (was_maximized(saved), screen)


# ── Windows: тёмная системная шапка в цвет программы (DWM) ──
DWM_DARK, DWM_DARK_OLD, DWM_BORDER, DWM_CAPTION, DWM_TEXT, DWM_CORNER = 20, 19, 34, 35, 36, 33
THEMES = {"dark": {"caption": "#090c12", "text": "#edf1f7", "border": "#1e293b"},
          "light": {"caption": "#f6f7f9", "text": "#0f172a", "border": "#d8dde6"}}


def win_build():
    """Номер сборки Windows (22000+ — Windows 11), 0 — не Windows."""
    if sys.platform != "win32":
        return 0
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def colorref(hex_color):
    """#rrggbb → COLORREF (0x00bbggrr) для DwmSetWindowAttribute."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


def native_hwnd(win):
    nat = getattr(win, "native", None)
    try:
        return int(nat.Handle.ToInt64()) if nat is not None else 0
    except Exception:
        return 0


def dwm_theme(hwnd, theme="dark", build=None):
    """Шапка окна Windows в тон теме программы: тёмный режим (Windows 10 1809+), а на Windows 11 — точные цвета
    фона, текста и рамки. Возвращает список выставленных атрибутов (для проверки)."""
    if not hwnd or sys.platform != "win32":
        return []
    import ctypes
    build = win_build() if build is None else build
    t = THEMES.get(theme) or THEMES["dark"]
    done = []

    def put(attr, v):
        val = ctypes.c_int(v)
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
            done.append(attr)
    try:
        put(DWM_DARK if build >= 18985 else DWM_DARK_OLD, 1 if theme != "light" else 0)
        if build >= 22000:
            put(DWM_CAPTION, colorref(t["caption"]))
            put(DWM_TEXT, colorref(t["text"]))
            put(DWM_BORDER, colorref(t["border"]))
        # Windows 10 перерисовывает заголовок только при смене активности окна
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)   # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
    except Exception:
        pass
    return done


class MainApi:
    """Мост окна программы (window.pywebview.api.*): тема шапки, управление окном, выбор файла."""
    def __init__(self):
        self._win = None

    def set_theme(self, theme):
        if sys.platform == "win32" and self._win is not None:
            dwm_theme(native_hwnd(self._win), "light" if theme == "light" else "dark")
        return True

    def platform(self):
        return {"win32": "win", "darwin": "mac"}.get(sys.platform, "linux")

    def minimize(self):
        self._win and self._win.minimize()

    def toggle_maximize(self):
        w = self._win
        if w is None:
            return
        if getattr(w, "_ta_max", False):
            w.restore()
        else:
            w.maximize()

    def toggle_fullscreen(self):
        self._win and self._win.toggle_fullscreen()

    def close(self):
        self._win and self._win.destroy()

    def pick_file(self, kinds="Отчёты брокера (*.xlsx;*.xls;*.csv;*.html;*.htm;*.xml)"):
        """Системный диалог выбора файла (запасной путь, если <input type=file> не открылся). → {name, b64} или None."""
        import base64
        try:
            import webview
            res = self._win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=(kinds, "Все файлы (*.*)"))
        except Exception:
            return None
        if not res:
            return None
        p = res[0] if isinstance(res, (list, tuple)) else res
        try:
            if os.path.getsize(p) > 50_000_000:
                return {"error": "Файл больше 50 МБ"}
            with open(p, "rb") as f:
                return {"name": os.path.basename(p), "b64": base64.b64encode(f.read()).decode("ascii")}
        except OSError as e:
            return {"error": str(e)}


def app_window(webview, url, thread, geom, hidden=False, html=None, remember_geometry=True):
    """Окно программы. thread — поток программы: когда он завершается, окно закрывается.
    geom — (w, h, x, y[, развёрнуто, экран]) из webview_setup()."""
    w, h, x, y = geom[:4]
    maximized = len(geom) > 4 and bool(geom[4])
    screen = geom[5] if len(geom) > 5 else None
    api = MainApi()
    win = webview.create_window(TITLE, url, html=html, width=w, height=h, x=x, y=y, min_size=(MIN_W, MIN_H),
                                background_color=BG, text_select=True, hidden=hidden, js_api=api)
    api._win = win
    win._ta_max = False
    normal = {"w": w, "h": h, "x": x if x is not None else 0, "y": y if y is not None else 0}

    def remember(*_):
        try:
            cw, ch, cx, cy = win.width, win.height, win.x, win.y
            if cx is None or cx <= -30000:                       # свёрнуто в панель задач: Windows ставит (-32000, -32000)
                return
            if win._ta_max or looks_maximized(cw, ch, cx, cy, screen):
                save_state(normal["w"], normal["h"], normal["x"], normal["y"], maximized=True)
            else:
                normal.update(w=cw, h=ch, x=cx, y=cy)
                save_state(cw, ch, cx, cy)
        except Exception:
            pass

    def on_max(*_):
        win._ta_max = True
        remember()

    def on_restore(*_):
        win._ta_max = False
    for name, fn in (("maximized", on_max), ("restored", on_restore)):
        ev = getattr(win.events, name, None)
        if ev is not None:
            ev += fn
    if remember_geometry:
        for ev in (win.events.closing, win.events.resized, win.events.moved):   # closing не вызывается при выходе по Cmd+Q
            ev += remember

    def shown(*_):
        if sys.platform == "win32":
            dwm_theme(native_hwnd(win), "dark")                  # страница уточнит тему через api.set_theme()
        if maximized:
            try:
                win.maximize()
            except Exception:
                pass
    win._ta_shown = shown
    if not hidden:
        win.events.shown += shown
    if thread is not None:
        threading.Thread(target=lambda: (thread.join(), win.destroy()), daemon=True).start()   # программа остановилась — закрыть окно
    return win


def open_native(url, thread):
    """Окно программы на pywebview (WKWebView / Edge WebView2). Возвращает управление после закрытия окна;
    бросает исключение, если окно показать не удалось (тогда запускается запасное окно tk)."""
    import webview
    app_window(webview, url, thread, webview_setup(webview))
    webview.start(**start_kwargs())


# ───────────────────────────── заставка на pywebview (оболочка ревизии 3) ─────────────────────────────
# Одна безрамочная webview-заставка вместо окна tk: проверка → загрузка N% → запуск. Когда сервер программы
# отвечает, рядом создаётся скрытое окно программы; оно показывается после загрузки страницы, а заставка
# растворяется и закрывается. Переключить рамку у уже открытого окна pywebview 6 не умеет (нет такого API ни
# в Cocoa-, ни в WinForms-бэкенде), поэтому «то же окно» — это два окна одного цикла GUI без пустого кадра.
# Сетевая работа — в фоновом потоке; состояние уходит в страницу через evaluate_js, кнопки — через js_api.

SPLASH_W, SPLASH_H = 520, 330
SPLASH_STEPS = ("Проверка", "Загрузка", "Подпись", "Запуск")
LOGO_SVG = ('<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg"><defs>'
            '<linearGradient id="lg" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#3b82f6"/>'
            '<stop offset=".5" stop-color="#2563eb"/><stop offset="1" stop-color="#1d4ed8"/></linearGradient>'
            '<linearGradient id="la" x1="12" y1="6" x2="26" y2="20" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#60a5fa"/>'
            '<stop offset="1" stop-color="#38bdf8"/></linearGradient></defs>'
            '<rect width="32" height="32" rx="9" fill="#0f1420" stroke="rgba(255,255,255,.08)"/>'
            '<path d="M7 9c0-1.1.9-2 2-2h14c1.1 0 2 .9 2 2v1.5c0 .55-.45 1-1 1H8c-.55 0-1-.45-1-1V9z" fill="url(#lg)"/>'
            '<path d="M13.5 11.5h5V23c0 1.1-.9 2-2 2h-1c-1.1 0-2-.9-2-2V11.5z" fill="url(#lg)"/>'
            '<path d="M18.5 16l6-6m0 0h-4m4 0v4" stroke="url(#la)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')

SPLASH_HTML = r"""<!doctype html><html lang="ru" class="__PLAT__"><head><meta charset="utf-8"><title>TAnalytic</title>
<style>
:root{--bg:#07090d;--card:#0c1017;--card2:#131923;--line:#ffffff0f;--line2:#ffffff1c;--tx:#edf1f7;--tx2:#9aa5b6;--mu:#6b7688;
  --ac:#3b82f6;--ac2:#2f6fe0;--ac-tx:#7aa8f8;--ac-glow:rgba(59,130,246,.22);--pos:#2bc48a;--neg:#f0626a}
*{box-sizing:border-box;margin:0}
html,body{height:100%;overflow:hidden;background:transparent;color:var(--tx);cursor:default;user-select:none;-webkit-user-select:none;
  font:14px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI Variable Text","Segoe UI",Inter,Roboto,"Helvetica Neue",system-ui,sans-serif;
  font-feature-settings:"cv11","ss01","ss03";letter-spacing:-.008em;-webkit-font-smoothing:antialiased}
html.win,html.win body{background:var(--bg)}
.card{position:absolute;inset:0;display:flex;flex-direction:column;padding:26px 30px 24px;border-radius:14px;overflow:hidden;
  background:radial-gradient(120% 90% at 0% 0%,#3b82f61a,transparent 55%),radial-gradient(90% 80% at 100% 100%,#38bdf80d,transparent 60%),var(--card);
  border:1px solid var(--line2);box-shadow:inset 0 1px 0 #ffffff0a;
  animation:in .42s cubic-bezier(.16,1,.3,1) both;transition:opacity .2s ease,transform .2s ease}
html.win .card{border-radius:0;border-color:transparent}
html.win10 .card{border-color:#26314b;box-shadow:inset 0 1px 0 #ffffff0a,inset 0 0 0 1px #00000066}
body.bye .card{opacity:0;transform:scale(.985)}
@keyframes in{from{opacity:0;transform:translateY(6px) scale(.985)}to{opacity:1;transform:none}}
.hd{display:flex;align-items:center;gap:14px}
.lg{width:44px;height:44px;flex:none;line-height:0;filter:drop-shadow(0 6px 18px var(--ac-glow))}
.lg svg{width:44px;height:44px;display:block}
body[data-stage=check] .lg,body[data-stage=launch] .lg{animation:pulse 1.8s ease-in-out infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.045)}}
.nm{font-size:19px;font-weight:700;letter-spacing:-.025em;line-height:1.2}
.nm small{display:block;font-size:12px;font-weight:500;color:var(--mu);letter-spacing:0;margin-top:2px}
.ver{display:inline-block;margin-left:8px;padding:1px 7px;border-radius:6px;font-size:10.5px;font-weight:700;letter-spacing:.04em;
  color:var(--ac-tx);background:#3b82f614;border:1px solid #3b82f626;vertical-align:3px}
.ver:empty{display:none}
.x{margin-left:auto;align-self:flex-start;width:28px;height:28px;border-radius:8px;border:0;background:transparent;color:var(--mu);
  display:grid;place-items:center;cursor:pointer;transition:background .15s,color .15s}
.x:hover{background:#ffffff0d;color:var(--tx)}
.x.mn{margin-left:auto;margin-right:-8px}.x.mn+.x{margin-left:0}
.x#x:hover{background:#e81123;color:#fff}
.x svg{width:12px;height:12px}
.steps{display:flex;gap:18px;margin:24px 0 0;font-size:12px;color:var(--mu)}
.steps span{display:flex;align-items:center;gap:7px;transition:color .2s}
.steps i{width:7px;height:7px;border-radius:50%;background:#ffffff1f;transition:background .2s,box-shadow .2s}
.steps .done{color:var(--tx2)}.steps .done i{background:var(--pos)}
.steps .on{color:var(--tx)}.steps .on i{background:var(--ac);box-shadow:0 0 0 4px #3b82f629}
.steps .err{color:var(--tx)}.steps .err i{background:var(--neg);box-shadow:0 0 0 4px #f0626a29}
.st{margin-top:18px;font-size:17px;font-weight:650;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
body[data-stage=error] .st{color:#ff8a90}
.dt{margin-top:4px;min-height:20px;font-size:13px;color:var(--tx2);font-variant-numeric:tabular-nums;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;user-select:text;-webkit-user-select:text}
.bar{position:relative;height:4px;margin-top:16px;border-radius:4px;background:#ffffff0d;overflow:hidden;transition:opacity .2s}
.bar b{position:absolute;left:0;top:0;bottom:0;width:0;border-radius:4px;background:linear-gradient(90deg,var(--ac2),var(--ac),#60a5fa);
  box-shadow:0 0 12px var(--ac-glow);transition:width .25s ease}
.bar.ind b{width:38%;background:linear-gradient(90deg,transparent,var(--ac),#60a5fa,transparent);animation:slide 1.25s ease-in-out infinite}
.bar.off{opacity:0}
@keyframes slide{from{transform:translateX(-100%)}to{transform:translateX(265%)}}
.ft{margin-top:auto;display:flex;align-items:center;gap:10px;min-height:34px}
.ft .hint{font-size:12px;color:var(--mu);margin-right:auto;white-space:nowrap;font-variant-numeric:tabular-nums}
.btn{height:34px;padding:0 15px;border-radius:9px;font:inherit;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;
  border:1px solid var(--line2);background:var(--card2);color:var(--tx);transition:background .15s,border-color .15s,transform .1s}
.btn:hover{background:#1a2230;border-color:#ffffff2e}
.btn:active{transform:translateY(1px)}
.btn.pri{background:var(--ac);border-color:var(--ac);color:#fff;box-shadow:0 6px 18px -8px var(--ac-glow)}
.btn.pri:hover{background:#4b8df7;border-color:#4b8df7}
.btn:focus-visible,.x:focus-visible{outline:2px solid #3b82f680;outline-offset:2px}
@media (prefers-reduced-motion:reduce){.card,.lg,.bar.ind b{animation:none}.bar.ind b{width:100%;opacity:.5}}
</style></head>
<body data-stage="check"><div class="card">
  <div class="hd"><div class="lg">__LOGO__</div>
    <div class="nm">TAnalytic<span class="ver" id="ver"></span><small>аналитика портфеля</small></div>
    <button class="x mn" id="mn" title="Свернуть" aria-label="Свернуть"><svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2 6h8"/></svg></button>
    <button class="x" id="x" title="Закрыть" aria-label="Закрыть"><svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2 2l8 8M10 2l-8 8"/></svg></button></div>
  <div class="steps" id="steps"></div>
  <div class="st" id="st">Проверяю обновления</div>
  <div class="dt" id="dt"></div>
  <div class="bar ind" id="bar"><b></b></div>
  <div class="ft"><span class="hint" id="hint"></span><span id="btns" style="display:flex;gap:10px"></span></div>
</div>
<script>
(function(){
  var $=function(id){return document.getElementById(id)};
  var STEPS=__STEPS__, lastBtns='';
  function call(n){try{if(window.pywebview&&pywebview.api&&pywebview.api[n])pywebview.api[n]()}catch(e){}}
  $('steps').innerHTML=STEPS.map(function(s){return '<span><i></i>'+s+'</span>'}).join('');
  $('x').onclick=function(){call('close')};
  $('mn').onclick=function(){call('minimize')};
  document.addEventListener('keydown',function(e){if(e.key==='Escape')call('close')});
  window.splash={set:function(s){
    if(s.bye){document.body.classList.add('bye');return}
    if('stage' in s)document.body.dataset.stage=s.stage;
    if('title' in s)$('st').textContent=s.title;
    if('detail' in s)$('dt').textContent=s.detail||'';
    if('hint' in s)$('hint').textContent=s.hint||'';
    if('ver' in s)$('ver').textContent=s.ver||'';
    if('step' in s){var sp=$('steps').children;for(var i=0;i<sp.length;i++)
      sp[i].className=i<s.step?'done':i===s.step?(document.body.dataset.stage==='error'?'err':'on'):'';}
    var b=$('bar');
    if(!('pct' in s)){}
    else if(s.pct===false){b.className='bar off'}
    else if(s.pct==null){b.className='bar ind';b.firstChild.style.width=''}
    else{b.className='bar';b.firstChild.style.width=Math.max(2,Math.min(100,s.pct))+'%'}
    var bs=JSON.stringify(s.buttons||[]);
    if(('buttons' in s)&&bs!==lastBtns){lastBtns=bs;var box=$('btns');box.innerHTML='';
      (s.buttons||[]).forEach(function(x){var el=document.createElement('button');el.className='btn'+(x[2]==='pri'?' pri':'');
        el.textContent=x[1];el.onclick=function(){call(x[0])};box.appendChild(el)});
      }
  }};
})();
</script></body></html>"""


def splash_html(platform=None, build=None):
    """Страница заставки. На macOS окно прозрачное, скругление и обводка рисуются карточкой; на Windows окно
    непрозрачное: на Windows 11 углы скругляет система, на Windows 10 остаётся чёткая обводка карточки."""
    if (platform or sys.platform) == "win32":
        build = win_build() if build is None else build
        plat = "win" if build >= 22000 else "win win10"
    else:
        plat = "mac"
    return (SPLASH_HTML.replace("__PLAT__", plat).replace("__LOGO__", LOGO_SVG)
            .replace("__STEPS__", json.dumps(list(SPLASH_STEPS), ensure_ascii=False)))


def splash_state(ev, tag=""):
    """Событие обновления (как в очереди worker) → состояние заставки для splash.set(). None — событие не меняет вид."""
    k, v = ev[0], (ver(tag) if tag else "")
    if k == "check":
        return {"stage": "check", "step": 0, "title": "Проверяю обновления", "detail": "Сверяю версию с последним релизом на GitHub",
                "pct": None, "buttons": [], "hint": ""}
    if k == "current":
        return {"stage": "launch", "step": 3, "title": "Установлена последняя версия", "detail": v, "pct": None}
    if k == "download":
        return {"stage": "download", "step": 1, "title": "Скачиваю обновление 0%", "detail": "Версия %s" % v, "pct": 0}
    if k == "progress":
        done, total, speed = ev[1:4]
        pct = min(100, int(100 * done / total)) if total else None
        return {"stage": "download", "step": 1, "pct": pct,
                "title": "Скачиваю обновление %d%%" % pct if pct is not None else "Скачиваю обновление",
                "detail": "%s · %s" % (v, progress_text(done, total, speed)) if v else progress_text(done, total, speed)}
    if k == "verify":
        return {"stage": "verify", "step": 2, "title": "Проверяю подпись", "detail": "Сверяю контрольную сумму SHA256", "pct": None}
    return None


class SplashApi:
    """Методы для кнопок заставки (window.pywebview.api.*). Поля с «_» pywebview в страницу не отдаёт."""
    def __init__(self, shell):
        self._shell = shell

    def retry(self):
        self._shell.ui("retry")

    def run(self):
        self._shell.ui("run")

    def close(self):
        self._shell.ui("close")

    def browser(self):
        self._shell.ui("browser")

    def minimize(self):
        try:
            self._shell.splash.minimize()
        except Exception:
            pass


def demo_worker(kind):
    """TINVEST_SPLASH_DEMO: имитация обновления без сети и без записи файлов (для просмотра заставки)."""
    def run(q, cancel):
        try:
            q.put(("check",))
            time.sleep(1.2)
            if kind == "net":
                q.put(("error", "Не удалось связаться с GitHub: [Errno 8] nodename nor servname provided, or not known", True))
                return
            q.put(("download", "v9.9.9"))
            total, t0 = 2_400_000, time.time()
            for i in range(1, 41):
                if cancel.is_set():
                    raise Cancelled()
                time.sleep(0.07)
                q.put(("progress", total * i // 40, total, total * i / 40 / max(time.time() - t0, 1e-3)))
            q.put(("verify", "v9.9.9"))
            time.sleep(0.7)
            if kind == "checksum":
                q.put(("error", "не совпала контрольная сумма SHA256 — обновление отклонено", False))
                return
            q.put(("ok", "updated"))
        except Cancelled:
            q.put(("cancelled",))
    return run


DEMO_PAGE = ("<!doctype html><html><body style='margin:0;height:100vh;display:grid;place-items:center;background:#07090d;"
             "color:#edf1f7;font:15px -apple-system,Segoe UI,sans-serif'><div style='text-align:center'><div style='width:72px;"
             "margin:0 auto 14px'>%s</div>Демо: здесь откроется программа.<br><small style='color:#6b7688'>Окно программы "
             "показано, заставка закрыта.</small></div></body></html>" % LOGO_SVG)


class WebShell:
    """Заставка обновления и запуск программы в одном цикле pywebview (главный поток занят GUI)."""

    def __init__(self, webview, args, no_update=False, demo=""):
        self.wv, self.args, self.no_update, self.demo = webview, args, no_update, demo
        self.q = queue.Queue()
        self.splash = self.main = None
        self.flow_started = False
        self.code, self.result = 0, {}
        try:
            with open(VER) as f:
                self.tag = f.read().strip()
        except OSError:
            self.tag = ""

    # --- связь со страницей ---
    def ui(self, action):
        self.q.put(("ui", action))

    def push(self, **s):
        if self.splash is None:
            return
        if "ver" not in s and not s.get("bye"):
            s["ver"] = ver(self.tag) if self.tag else ""
        try:
            self.splash.evaluate_js("window.splash&&splash.set(%s)" % json.dumps(s))
        except Exception:
            pass

    def have(self):
        return bool(self.demo) or have_app()

    # --- окно ---
    def run(self):
        """Возвращает код выхода; бросает исключение, если GUI не запустился (тогда — запасной путь tk)."""
        wv = self.wv
        self.geom = webview_setup(wv)
        mac = sys.platform == "darwin"
        sx, sy = center(SPLASH_W, SPLASH_H, self.geom[5])
        self.splash = wv.create_window(TITLE, html=splash_html(), js_api=SplashApi(self), width=SPLASH_W, height=SPLASH_H,
                                       x=sx, y=sy, resizable=False, frameless=True, easy_drag=True, transparent=mac,
                                       background_color=BG, min_size=(SPLASH_W, SPLASH_H))
        wv.start(self.flow, **start_kwargs())
        return self.result.get("code") or self.code

    def decorate(self):
        """Тень у прозрачного окна (macOS) и скруглённые углы безрамочного окна (Windows 11)."""
        nat = getattr(self.splash, "native", None)
        if nat is None:
            return
        try:
            if sys.platform == "darwin":
                from PyObjCTools import AppHelper

                def shadow():
                    nat.setHasShadow_(True)
                    nat.invalidateShadow()
                AppHelper.callAfter(shadow)
            elif sys.platform == "win32" and win_build() >= 22000:
                import ctypes
                pref = ctypes.c_int(2)                           # DWMWA_WINDOW_CORNER_PREFERENCE = DWMWCP_ROUND (только Windows 11)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(int(nat.Handle.ToInt64()), DWM_CORNER, ctypes.byref(pref), 4)
        except Exception:
            pass

    def close_all(self):
        for w in (self.splash, self.main):
            try:
                w and w.destroy()
            except Exception:
                pass

    def flow(self):
        self.flow_started = True
        try:
            self.splash.events.loaded.wait(15)
            time.sleep(0.05)
            self.decorate()
            if self.updating() == "quit":
                self.close_all()
                return
            self.launch()
        except Exception as e:                                   # не оставляем пользователя с зависшей заставкой
            try:
                self.code = 1
                self.fail("Ошибка оболочки", str(e) or e.__class__.__name__)
            finally:
                self.close_all()

    # --- этап обновления ---
    def updating(self):
        if self.no_update and not self.demo:
            return "run"
        while True:
            self.q = q = queue.Queue()
            cancel, busy, cancel_t, deadline, last_step = threading.Event(), True, None, None, 0
            work = demo_worker(self.demo) if self.demo else worker
            threading.Thread(target=work, args=(q, cancel), daemon=True).start()
            self.push(**splash_state(("check",)))
            while True:
                try:
                    ev = q.get(timeout=0.25)
                except queue.Empty:
                    ev = None
                now = time.time()
                if cancel_t and now - cancel_t > 3:              # сеть повисла — не держим пользователя
                    return "quit"
                if deadline:
                    left = int(deadline - now + 0.999)
                    if left <= 0:
                        return "run"
                    if ev is None:
                        self.push(stage="error", hint="Автозапуск через %d с" % left)
                if ev is None:
                    continue
                k = ev[0]
                if k == "ui":
                    a = ev[1]
                    if a == "close":
                        if not busy:
                            return "quit"
                        cancel.set()
                        cancel_t = now
                        self.push(stage="check", title="Отмена…", detail="", buttons=[])
                    elif a == "run" and not busy and self.have():
                        return "run"
                    elif a == "retry" and not busy:
                        break
                    continue
                if k in ("current", "download"):
                    self.tag = ev[1]
                st = splash_state(ev, self.tag)
                if st:
                    last_step = st["step"]
                    self.push(**st)
                if k == "ok":
                    self.push(stage="launch", step=3, title="Запускаю", detail="", pct=None, buttons=[])
                    return "run"
                if k == "cancelled":
                    return "quit"
                if k == "error":
                    busy = False
                    msg, net = ev[1], ev[2]
                    btns = [["retry", "Повторить", "pri" if not self.have() else ""]]
                    if self.have():
                        btns.append(["run", "Запустить без обновления", "pri"])
                    else:
                        btns.insert(0, ["close", "Закрыть", ""])
                    self.push(stage="error", step=last_step,
                              title="Нет связи с GitHub" if net else "Обновление не установлено",
                              detail=msg[:1].upper() + msg[1:], pct=False, buttons=btns,
                              hint="" if not (net and self.have()) else "Автозапуск через 6 с")
                    if not self.have():
                        self.code = 1
                    elif net:                                    # офлайн: через несколько секунд — установленная версия
                        deadline = now + 6
            deadline = None
            self.code = 0

    # --- этап запуска ---
    def wait_choice(self, choices, ready=None):
        """Ждёт кнопку заставки (или ready() → "ready")."""
        while True:
            try:
                ev = self.q.get(timeout=0.2)
            except queue.Empty:
                if ready and ready():
                    return "ready"
                continue
            if ev[0] == "ui" and ev[1] in choices:
                return ev[1]

    def fail(self, title, detail, buttons=None):
        self.push(stage="error", step=3, title=title, detail=detail, pct=False, hint="",
                  buttons=buttons or [["close", "Закрыть", "pri"]])
        if not buttons:
            self.wait_choice(("close",))

    def launch(self):
        self.push(stage="launch", step=3, title="Запускаю", detail="Запускаю сервер программы…", pct=None, buttons=[], hint="")
        if not self.have():
            self.code = 1
            self.fail("Программа ещё не скачана", "Обновиться не удалось. Проверьте интернет и запустите снова.")
            self.close_all()
            return
        if self.demo:
            time.sleep(1.2)
            url, html, t = None, DEMO_PAGE, None
        else:
            t, cap, self.result = start_app(self.args)
            state = {}
            threading.Thread(target=lambda: state.update(ok=wait_ping(lambda: cap.url, t, timeout=60)), daemon=True).start()
            while "ok" not in state:
                time.sleep(0.05)
            while not state["ok"]:
                if not t.is_alive():
                    self.code = 1
                    err = self.result.get("err") or "код выхода %s" % self.result.get("code")
                    self.fail("Программа остановилась с ошибкой", err)
                    self.close_all()
                    return
                btns = [["close", "Закрыть", ""]] + ([["browser", "Открыть в браузере", "pri"]] if cap.url else [])
                self.fail("Программа долго не отвечает", "Сервер ещё запускается. Можно подождать или открыть программу в браузере.",
                          btns)
                state.clear()
                threading.Thread(target=lambda: state.update(ok=wait_ping(lambda: cap.url, t, timeout=3600)), daemon=True).start()
                a = self.wait_choice(("close", "browser"), ready=lambda: state.get("ok"))
                if a == "close":
                    self.close_all()
                    return
                if a == "browser":
                    webbrowser_open(cap.url)
                    self.push(hint="Открыто в браузере. Окно закроется вместе с программой.")
                    a = self.wait_choice(("close",), ready=lambda: state.get("ok") or not t.is_alive())
                    if a == "close" or not t.is_alive():
                        self.close_all()
                        return
                self.push(stage="launch", step=3, title="Запускаю", detail="", pct=None, buttons=[], hint="")
            url, html = cap.url, None
        self.push(detail="Открываю окно программы…")
        self.main = app_window(self.wv, url, t, self.geom, hidden=True, html=html, remember_geometry=not self.demo)
        self.main.events.loaded.wait(10)                         # показываем уже отрисованную страницу, без белого кадра
        time.sleep(0.05)
        self.main.show()
        try:
            self.main._ta_shown()                                # тёмная шапка Windows и развёрнутое окно, как было
        except Exception:
            pass
        self.push(bye=True)                                      # заставка растворяется под окном программы
        time.sleep(0.22)
        try:
            self.splash.destroy()
        except Exception:
            pass
        self.splash = None


def run_webshell(args, no_update, demo=""):
    """Заставка и окно на pywebview. None — pywebview недоступен или не запустился (тогда работает прежний путь с tk)."""
    try:
        import webview
    except Exception:
        return None
    shell = WebShell(webview, args, no_update, demo)
    try:
        return shell.run()
    except Exception as e:
        if shell.flow_started:
            raise
        sys.stderr.write("Заставка pywebview недоступна (%s), открываю запасное окно.\n" % e)
        os.environ["TINVEST_NO_WEBVIEW"] = "1"                  # и окно программы — запасное (tk / браузер)
        return None


APP_START_GRACE = 20        # сек: падение новой версии раньше этого срока считаем сбоем запуска и пробуем .bak


def _exec_app(args, result):
    """Выполняет APP; если новой версии нет или она упала при запуске (не Ctrl+C и не позже, после работы),
    один раз запускает предыдущую из .bak."""
    import runpy, traceback
    bak = APP + ".bak"
    path = APP if os.path.exists(APP) else bak
    t0 = time.time()
    sys.argv = [path] + args
    try:
        runpy.run_path(path, run_name="__main__")
        return
    except SystemExit as e:
        result["code"] = e.code if isinstance(e.code, int) else 1
        return
    except KeyboardInterrupt:
        result["code"] = 130
        return
    except Exception:  # noqa: BLE001
        err = traceback.format_exc().strip().splitlines()[-1]
        if path != APP or not os.path.exists(bak) or time.time() - t0 > APP_START_GRACE:
            result["err"] = err
            return
    sys.argv = [bak] + args
    try:
        runpy.run_path(bak, run_name="__main__")
    except SystemExit as e:
        result["code"] = e.code if isinstance(e.code, int) else 1
    except KeyboardInterrupt:
        result["code"] = 130
    except Exception:  # noqa: BLE001
        result["err"] = err


def start_app(args):
    """Запускает программу в фоновом потоке этого процесса. (поток, Capture, result)."""
    result = {}

    def target():
        _exec_app(args, result)
    cap = sys.stdout = sys.stderr = Capture(sys.stdout)
    t = threading.Thread(target=target, daemon=True)           # главный поток занят окном (tk или pywebview)
    t.start()
    return t, cap, result


def run_inprocess(args, ui, native=False):
    """Собранный лаунчер: Python-интерпретатора рядом нет, поэтому программа выполняется внутри него."""
    if isinstance(ui, Console):                                 # консоль: можно прямо в главном потоке
        result = {}
        _exec_app(args, result)
        return result.get("code", 1 if result.get("err") else 0)
    t, cap, result = start_app(args)
    if native:
        def ready():
            result["ready"] = wait_ping(lambda: cap.url, t)
        threading.Thread(target=ready, daemon=True).start()
    r = ui.running(t, cap, result, native)
    if r != "native":
        return r
    ui.close()                                                  # tk полностью разобран до Cocoa/WebView2
    try:
        open_native(cap.url, t)
        return result.get("code") or 0
    except Exception as e:                                      # нет WebView2 и т. п. — запасное окно tk
        sys.stderr.write("Собственное окно недоступно (%s), открываю запасное.\n" % e)
        ui2 = make_window()
        if ui2 is None:
            webbrowser_open(cap.url)
            t.join()
            return result.get("code") or 0
        ui2.set_version()
        return ui2.running(t, cap, result)


# ───────────────────────────── одна копия программы и аккуратный выход ─────────────────────────────

MUTEX_NAME = "TAnalyticSingleInstanceMutex"       # то же имя проверяет установщик (Inno Setup AppMutex)
LOCK_PATH = os.path.join(HOME, "launcher.lock")


class SingleInstance:
    """Не даёт запустить вторую копию на ту же базу data.db: на Windows — именованный мьютекс,
    на macOS/Linux — блокировка файла. acquire() → False, если программа уже открыта."""
    def __init__(self, name=MUTEX_NAME, path=None):
        self.name, self.path = name, path or LOCK_PATH
        self.handle = self.fh = None

    def acquire(self):
        if sys.platform == "win32":
            try:
                import ctypes
                k = ctypes.windll.kernel32
                k.CreateMutexW.restype = ctypes.c_void_p
                self.handle = k.CreateMutexW(None, False, self.name)
                return not (self.handle and k.GetLastError() == 183)     # ERROR_ALREADY_EXISTS
            except Exception:
                return True
        try:
            import fcntl
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            self.fh = open(self.path, "a+")
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (OSError, ImportError):
            if self.fh is not None:
                try:
                    self.fh.close()
                except OSError:
                    pass
                self.fh = None
                return False
            return True

    def release(self):
        try:
            if self.handle and sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self.handle))
            if self.fh is not None:
                self.fh.close()
        except Exception:
            pass
        self.handle = self.fh = None


def activate_running():
    """Вторая копия: вывести на передний план уже открытое окно программы (Windows), иначе — ничего."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, TITLE)
        if not hwnd:
            return False
        u.ShowWindow(hwnd, 9)                                    # SW_RESTORE
        u.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def graceful_exit(code, wait=3.0):
    """Выход без обрыва: программа сбрасывает журнал SQLite (wal_checkpoint) и закрывает соединения,
    затем процесс завершается, не дожидаясь фоновых потоков (пулы сетевых запросов)."""
    hook = getattr(sys, "tanalytic_shutdown", None)
    if callable(hook):
        t = threading.Thread(target=hook, daemon=True)
        t.start()
        t.join(wait)
    try:
        sys.stdout and sys.stdout.flush()
    except Exception:
        pass
    os._exit(code)


def webbrowser_open(url):
    import webbrowser
    webbrowser.open(url)


def main():
    if sys.platform == "win32":                                  # своя иконка в панели задач, а не python.exe
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TAnalytic.App")
        except Exception:
            pass
    argv = sys.argv[1:]
    no_update = "--no-update" in argv
    no_gui = "--no-gui" in argv or os.environ.get("TINVEST_NO_GUI") == "1"
    args = [a for a in argv if a not in ("--no-update", "--no-gui")]
    demo = os.environ.get("TINVEST_SPLASH_DEMO", "")            # 1 / net / checksum: показать заставку без сети и файлов
    demo = "ok" if demo == "1" else demo
    if FROZEN and not demo:
        lock = SingleInstance()
        if not lock.acquire():                                   # программа уже открыта: показать её окно и выйти
            activate_running()
            sys.exit(0)
    if demo or (want_native(FROZEN, no_gui) and "--no-window" not in args):
        code = run_webshell(args + ["--no-window"], no_update, demo)     # окно открывает оболочка, не браузер программы
        if code is not None:
            graceful_exit(code)                                 # не ждём фоновые потоки программы
    ui = None
    if FROZEN or not no_update:
        ui = (None if no_gui else make_window()) or Console()
        q, cancel = queue.Queue(), threading.Event()
        if no_update:
            q.put(("ok", "skipped"))
        else:
            threading.Thread(target=worker, args=(q, cancel), daemon=True).start()
        if ui.updating(q, cancel) == "quit":
            ui.close()
            sys.exit(1 if ui.error and not have_app() else 0)
    if not have_app():
        sys.exit("Программа ещё не скачана, а обновиться не удалось. Проверьте интернет и REPO в лаунчере.")
    if FROZEN:
        if not isinstance(ui, Console) and "--no-window" not in args:
            args.append("--no-window")                           # окно открываем сами (или показываем кнопку), не браузер программы
        code = run_inprocess(args, ui, native=want_native(FROZEN, no_gui) and not isinstance(ui, Console))
        ui.close()
        graceful_exit(code)                                     # не ждём фоновые потоки программы
    if ui:
        ui.close()                                              # окно закрыто полностью до запуска программы
    path = APP if os.path.exists(APP) else APP + ".bak"
    sys.exit(subprocess.call([sys.executable, path] + args))


if __name__ == "__main__":
    main()
