# ═══════════════════════════════ документы раскрытия: извлечение текста ═══════════════════════════════
# doc_text(bytes, ctype, name) -> {"text", "kind": html|pdf|docx|rtf|txt, "needs_ocr"}. Только stdlib, без сети.
# Вид определяется по сигнатуре (%PDF, PK + word/document.xml, {\rtf), затем по ctype/расширению, затем по началу текста.
# Весь текст после извлечения приводится к одному виду (_dt_norm): пробелы схлопнуты, табы между ячейками таблиц сохранены,
# нумерация пунктов («2.4.») остаётся в начале строки.
import codecs

_DT_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DT_BLOCK = frozenset(("p", "div", "br", "tr", "li", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "section", "article"))
_DT_SKIP = frozenset(("script", "style", "noscript", "head", "template"))


def _dt_norm(text):
    """Единая нормализация: неразрывные пробелы, схлопывание пробелов, не более одной пустой строки подряд."""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    t = re.sub("[\u200b\u200c\u200d\ufeff\u00ad]", "", t)
    t = re.sub("[\u00a0\u2000-\u200a\u202f\u205f\u3000]", " ", t)
    out = []
    for ln in t.split("\n"):
        ln = re.sub(r"[ \t]*\t[ \t]*", "\t", re.sub(r" {2,}", " ", ln)).strip(" \t")
        out.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


class _DtHtml(HTMLParser):
    """HTML -> текст: блочные теги дают перевод строки, ячейки таблиц — табуляцию."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.out = []
        self.stack = []        # открытые «скрываемые» теги

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.stack = []    # незакрытый <head> не должен съесть тело
        if tag in _DT_SKIP:
            self.stack.append(tag)
        elif not self.stack and tag in _DT_BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if self.stack:
            if tag == self.stack[-1]:
                self.stack.pop()
            return
        if tag in ("td", "th"):
            self.out.append("\t")
        elif tag in _DT_BLOCK and tag != "br":
            self.out.append("\n")

    def handle_data(self, data):
        if not self.stack:
            self.out.append(re.sub(r"\s+", " ", data))


def _dt_html_text(s):
    p = _DtHtml()
    try:
        p.feed(s)
        p.close()
    except Exception:
        pass
    return "".join(p.out)


def _dt_decode(data, ctype=""):
    """Байты -> строка: BOM, charset из ctype / <meta>, затем utf-8, затем cp1251."""
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", "replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    cands = []
    m = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", ctype or "", re.I)
    if not m:
        m = re.search(rb"charset\s*=\s*[\"']?([\w.-]+)", data[:4096], re.I)
    if m:
        cs = m.group(1)
        cands.append(cs.decode("ascii", "ignore") if isinstance(cs, bytes) else cs)
    cands += ["utf-8", "cp1251"]
    for cs in cands:
        try:
            codecs.lookup(cs)
            return data.decode(cs)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("cp1251", "replace")


def _dt_is_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return "word/document.xml" in z.namelist()
    except Exception:
        return False


def _dt_kind(data, ctype="", name=""):
    head = data[:1024].lstrip()
    if head[:4] == b"%PDF":
        return "pdf"
    if data[:4] == b"PK\x03\x04" and _dt_is_docx(data):
        return "docx"
    if head[:5] == b"{\\rtf":
        return "rtf"
    ct = (ctype or "").lower()
    ext = os.path.splitext((name or "").lower().split("?")[0])[1]
    if "pdf" in ct or ext == ".pdf":
        return "pdf"
    if "wordprocessingml" in ct or ext == ".docx":
        return "docx"
    if "rtf" in ct or ext == ".rtf":
        return "rtf"
    if "html" in ct or ext in (".htm", ".html", ".xhtml"):
        return "html"
    if "text/plain" in ct or ext == ".txt":
        return "txt"
    low = data[:2048].lower()
    if any(t in low for t in (b"<html", b"<body", b"<div", b"<p>", b"<p ")):
        return "html"
    return "txt"


def _dt_pdf(data):
    try:
        frags = pdf_text_fragments(data)
    except Exception:
        return ""
    lines, cur, last_y = [], [], None
    for f in frags:
        try:
            y, txt = float(f[1]), f[3]
        except Exception:
            continue
        if last_y is not None and abs(y - last_y) > 2.0:
            lines.append(" ".join(cur))
            cur = []
        cur.append(txt)
        last_y = y
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines)


def _dt_docx_par(p):
    s = []
    for e in p.iter():
        if e.tag == _DT_W + "t":
            s.append(e.text or "")
        elif e.tag == _DT_W + "tab":
            s.append("\t")
        elif e.tag in (_DT_W + "br", _DT_W + "cr"):
            s.append("\n")
        elif e.tag == _DT_W + "noBreakHyphen":
            s.append("-")
    return "".join(s)


def _dt_docx_walk(el, out):
    for ch in el:
        if ch.tag == _DT_W + "p":
            out.append(_dt_docx_par(ch))
        elif ch.tag == _DT_W + "tr":
            cells = []
            for tc in ch.findall(_DT_W + "tc"):
                cells.append(" ".join(_dt_docx_par(p) for p in tc.iter(_DT_W + "p")))
            out.append("\t".join(cells))
        else:
            _dt_docx_walk(ch, out)


def _dt_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ET.fromstring(z.read("word/document.xml"))
    except Exception:
        return ""
    out = []
    _dt_docx_walk(root, out)
    return "\n".join(out)


_DT_RTF_TOK = re.compile(r"\\'([0-9a-fA-F]{2})|\\([a-zA-Z]+)(-?\d+)? ?|\\([^a-zA-Z])|([{}])|([^\\{}]+)", re.S)
_DT_RTF_DEST = frozenset(("fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "headerl", "headerr", "footerl", "footerr",
                          "footnote", "filetbl", "listtable", "listoverridetable", "generator", "themedata", "colorschememapping",
                          "datastore", "latentstyles", "rsidtbl", "xmlnstbl", "object", "fldinst", "revtbl", "template"))
_DT_RTF_SYM = {"emdash": "\u2014", "endash": "\u2013", "bullet": "\u2022", "lquote": "\u2018", "rquote": "\u2019",
               "ldblquote": "\u201c", "rdblquote": "\u201d", "emspace": " ", "enspace": " ", "qmspace": " "}
_DT_RTF_NL = frozenset(("par", "line", "sect", "page", "row"))


def _dt_rtf(data):
    """Минимальный разбор RTF: \\'xx (кодовая страница), \\uN?, абзацы, табы; служебные группы отбрасываются."""
    s = data.decode("latin-1")
    m = re.search(r"\\ansicpg(\d+)", s[:4096])
    cp = "cp" + m.group(1) if m else "cp1251"
    try:
        codecs.lookup(cp)
    except LookupError:
        cp = "cp1251"

    def byte(b):
        return bytes([b]).decode(cp, "replace")

    out = []
    stack = []
    skip, uc, skip_n, at_start = False, 1, 0, False
    for m in _DT_RTF_TOK.finditer(s):
        hx, word, num, sym, br, txt = m.groups()
        if br == "{":
            stack.append((skip, uc))
            at_start = True
            continue
        if br == "}":
            if stack:
                skip, uc = stack.pop()
            at_start = False
            continue
        first, at_start = at_start, False
        if hx is not None:
            if skip:
                continue
            if skip_n:
                skip_n -= 1
                continue
            out.append(byte(int(hx, 16)))
        elif word is not None:
            if first and word in _DT_RTF_DEST:
                skip = True
            if skip:
                continue
            if word == "u" and num is not None:
                n = int(num)
                out.append(chr(n + 65536 if n < 0 else n))
                skip_n = uc
            elif word == "uc" and num is not None:
                uc = int(num)
            elif word in _DT_RTF_NL:
                out.append("\n")
            elif word in ("tab", "cell"):
                out.append("\t")
            elif word in _DT_RTF_SYM:
                out.append(_DT_RTF_SYM[word])
        elif sym is not None:
            if sym == "*" and first:
                skip = True
            if skip:
                continue
            if sym in "\\{}":
                out.append(sym)
            elif sym == "~":
                out.append(" ")
            elif sym in "\n\r":
                out.append("\n")
        elif txt is not None:
            if skip:
                continue
            txt = txt.replace("\r", "").replace("\n", "")
            if skip_n:
                k = min(skip_n, len(txt))
                txt, skip_n = txt[k:], skip_n - k
            out.append("".join(byte(ord(c)) if 0x80 <= ord(c) < 0x100 else c for c in txt))
    return "".join(out)


def doc_text(data, ctype="", name=""):
    """Байты документа -> {"text", "kind", "needs_ocr"}. Не бросает исключений на мусоре."""
    data = data or b""
    kind = _dt_kind(data, ctype, name)
    needs_ocr = False
    try:
        if kind == "pdf":
            raw = _dt_pdf(data)
            needs_ocr = len(re.findall(r"[^\W\d_]", raw)) < 20
        elif kind == "docx":
            raw = _dt_docx(data)
        elif kind == "rtf":
            raw = _dt_rtf(data)
        elif kind == "html":
            raw = _dt_html_text(_dt_decode(data, ctype))
        else:
            raw = _dt_decode(data, ctype)
    except Exception:
        raw = ""
    return {"text": _dt_norm(raw), "kind": kind, "needs_ocr": needs_ocr}
