"""Извлечение текста из HTML/DOCX/RTF/PDF (без сети)."""
import io
import unittest
import zipfile

from tests._load import load

T = load()


def _docx(body):
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body>%s</w:body></w:document>' % body)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", xml)
    return b.getvalue()


class DocText(unittest.TestCase):
    def test_html_basic(self):
        h = ('<html><head><title>T</title><style>p{}</style></head><body><script>var a=1;</script>'
             '<p>2.4. Общий&nbsp;размер   80&nbsp;620</p><table><tr><td>2.5.</td><td>14,86 &amp; руб</td></tr></table>'
             '<div>a<br>b</div><noscript>no</noscript></body></html>')
        r = T.doc_text(h.encode("utf-8"), "text/html; charset=utf-8")
        self.assertEqual(r["kind"], "html")
        self.assertFalse(r["needs_ocr"])
        self.assertIn("2.4. Общий размер 80 620", r["text"])
        self.assertIn("2.5.\t14,86 & руб", r["text"])
        self.assertIn("a\nb", r["text"])
        for bad in ("var a", "no", "p{}"):
            self.assertNotIn(bad, r["text"])
        self.assertNotIn("\n\n\n", r["text"])

    def test_html_cp1251_meta(self):
        h = '<html><head><meta charset="windows-1251"></head><body><p>Привет, мир</p></body></html>'
        r = T.doc_text(h.encode("cp1251"))
        self.assertEqual(r["kind"], "html")
        self.assertEqual(r["text"], "Привет, мир")

    def test_txt_cp1251_fallback_and_utf8(self):
        self.assertEqual(T.doc_text("Купон 5".encode("cp1251"), name="a.txt")["text"], "Купон 5")
        r = T.doc_text("Купон  5".encode("utf-8"))
        self.assertEqual((r["kind"], r["text"]), ("txt", "Купон 5"))

    def test_docx(self):
        body = ('<w:p><w:r><w:t>2.1.</w:t></w:r><w:r><w:tab/></w:r><w:r><w:t>ISIN</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>a</w:t><w:br/><w:t>b</w:t></w:r></w:p>'
                '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>2.2.</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>x y</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
        r = T.doc_text(_docx(body))
        self.assertEqual(r["kind"], "docx")
        self.assertEqual(r["text"], "2.1.\tISIN\na\nb\n2.2.\tx y")

    def test_rtf(self):
        rtf = (b"{\\rtf1\\ansi\\ansicpg1251{\\fonttbl{\\f0 Arial;}}{\\*\\generator x;}"
               b"\\pard \\'e0\\'e1 \\u1087?\\u1088? \\tab z\\par line2}")
        r = T.doc_text(rtf)
        self.assertEqual(r["kind"], "rtf")
        self.assertEqual(r["text"], "аб пр\tz\nline2")

    def test_pdf(self):
        r = T.doc_text(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF")
        self.assertEqual(r["kind"], "pdf")
        self.assertTrue(r["needs_ocr"])
        r = T.doc_text(b"\x00\x01garbage\xff", "application/pdf")
        self.assertEqual(r["kind"], "pdf")
        self.assertTrue(r["needs_ocr"])

    def test_kind_detection(self):
        self.assertEqual(T.doc_text(b"<p>x</p>")["kind"], "html")
        self.assertEqual(T.doc_text(b"x", name="f.HTM")["kind"], "html")
        self.assertEqual(T.doc_text(b"plain")["kind"], "txt")
        self.assertEqual(T.doc_text(b"{\\rtf1 hi}")["kind"], "rtf")
        self.assertEqual(T.doc_text(_docx(""), "", "x.bin")["kind"], "docx")
        self.assertEqual(T.doc_text(b"", "")["text"], "")


if __name__ == "__main__":
    unittest.main()
