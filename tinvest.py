#!/usr/bin/env python3
"""Лаунчер T-Invest Analytics: проверяет обновления на GitHub, скачивает и запускает программу.

Запуск:  python3 tinvest.py          (--no-update — не проверять обновления,
                                       --no-gui — без окна, прогресс в консоли; то же TINVEST_NO_GUI=1)
Токен лаунчер не читает и никуда не отправляет: он лежит только в папке данных на этом компьютере.
"""
import hashlib, json, os, queue, re, socket, ssl, subprocess, sys, threading, time, urllib.request
from urllib.parse import urlparse

REPO = "Kos5o4ka/tinvest-analytics"
FILE = "tinvest_analytics.py"            # файл программы в релизе
SUMS = "SHA256SUMS"                      # строки вида «<sha256>  <имя файла>»
TITLE = "T-Invest Analytics"
HOME = os.environ.get("TINVEST_HOME") or os.path.join(os.path.expanduser("~"), ".tinvest_analytics")
APP_DIR = os.path.join(HOME, "app")
APP, VER = os.path.join(APP_DIR, FILE), os.path.join(APP_DIR, "version.txt")
OK_HOSTS = ("api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
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
    if not ctx.cert_store_stats().get("x509_ca"):      # Python с python.org на macOS бывает без корневых сертификатов
        try:
            import certifi
            ctx.load_verify_locations(cafile=certifi.where())
        except Exception:
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
    if os.path.exists(APP):
        os.replace(APP, APP + ".bak")                          # предыдущая версия остаётся как запасная
    tmp = APP + ".tmp"
    with open(tmp, "wb") as f:
        f.write(code)
    os.replace(tmp, APP)                                       # атомарная подмена
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
    return "%.1f" % (n / 1e6)


def progress_text(done, total, speed):
    s = "%s из %s МБ" % (mb(done), mb(total)) if total else "%s МБ" % mb(done)
    return s + (" · %s МБ/с" % mb(speed) if speed else "")


def console_bar(done, total, speed, width=28):
    frac = min(1.0, done / total) if total else 0.0
    n = int(width * frac)
    pct = " %3d%%" % int(frac * 100) if total else ""
    return "[%s%s]%s  %s" % ("#" * n, "-" * (width - n), pct, progress_text(done, total, speed))


def have_app():
    return os.path.exists(APP)


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

BG, SIDE, CARD, CARD2 = "#0b0c0f", "#0f1115", "#16181d", "#1c1f26"
LINE, LINE2 = "#252932", "#2f3440"
TX, TX2, MU = "#eef0f4", "#a8aebb", "#6f7686"
AC, AC2, POS, NEG = "#ffdd2d", "#ffe866", "#3ecf8e", "#ff6b6b"
INK = "#121212"                                                  # текст на жёлтой кнопке
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


class Window:
    W, H = 520, 300

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
        rrect(c, u(40), u(36), u(76), u(72), u(10), fill=AC, outline=AC)             # метка приложения
        c.create_text(u(58), u(55), text="T", font=self.f_logo, fill=INK)
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
    def running(self, thread, cap, result):
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
            if cap.url and not self.btns[0].on and not self.dead:
                self.btns[0].enable(True)
                self.c.itemconfigure(self.detail, text=cap.url)
            if not thread.is_alive() and not self.dead:
                self.dead = True
                if result.get("err"):
                    self.show_error("Программа остановилась с ошибкой:\n" + result["err"], False)
                else:
                    self.finish("quit")
        self.tick = tick
        self.root.after(200, self.poll)
        self.root.mainloop()
        return result.get("code") or 0

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


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


def run_inprocess(args, ui):
    """Собранный лаунчер: Python-интерпретатора рядом нет, поэтому программа выполняется внутри него."""
    import runpy, traceback
    sys.argv = [APP] + args
    result = {}

    def target():
        try:
            runpy.run_path(APP, run_name="__main__")
        except SystemExit as e:
            result["code"] = e.code if isinstance(e.code, int) else 1
        except BaseException:
            result["err"] = traceback.format_exc().strip().splitlines()[-1]
    if isinstance(ui, Console):
        target()                                                # консоль: можно прямо в главном потоке
        return result.get("code", 1 if result.get("err") else 0)
    cap = sys.stdout = sys.stderr = Capture(sys.stdout)
    t = threading.Thread(target=target, daemon=True)           # tk занимает главный поток
    t.start()
    return ui.running(t, cap, result)


def main():
    argv = sys.argv[1:]
    no_update = "--no-update" in argv
    no_gui = "--no-gui" in argv or os.environ.get("TINVEST_NO_GUI") == "1"
    args = [a for a in argv if a not in ("--no-update", "--no-gui")]
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
        code = run_inprocess(args, ui)
        ui.close()
        sys.stdout and sys.stdout.flush()
        os._exit(code)                                          # не ждём фоновые потоки программы
    if ui:
        ui.close()                                              # окно закрыто полностью до запуска программы
    sys.exit(subprocess.call([sys.executable, APP] + args))


if __name__ == "__main__":
    main()
