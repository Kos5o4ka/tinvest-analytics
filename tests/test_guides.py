"""Гиды по разделам и туры «Как пользоваться»: шаги указывают на существующие элементы, гид открыт только при первом заходе."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ui_leftovers import jsrun, rd  # noqa: E402

PAGE_FILES = {"calc": ["33a_calc_ui.js"], "tax": ["19_tax.js"], "scr": ["14_scr.js"]}
STUB = r"""
var _ui={},posted=[];
function uiGet(k){return _ui[k]==null?null:_ui[k]}
function uiSet(k,v){_ui[k]=v;posted.push(k)}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
var UX={whyOff:{}},UX_WHY={scr:'строка'},KB=[{id:'xirr',t:'XIRR'},{id:'yield',t:'Доходность'}];
"""


def load_guides():
    return jsrun(["71_guides.js"], STUB + "out.g=GUIDES;out.t=GUIDE_TOURS;")


class Guides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        o = load_guides()
        cls.g, cls.t = o["g"], o["t"]

    def test_pages_exist(self):
        pages = set(re.findall(r"\['([a-z]+)','", rd("src", "web", "js", "02_state_api.js").split("const PAGES=", 1)[1].split("\n", 1)[0]))
        self.assertTrue(set(self.g) <= pages, set(self.g) - pages)
        self.assertEqual(set(self.t), {"calc", "tax", "scr"})

    def test_kb_links_exist(self):
        ids = set(re.findall(r"\{id:'([a-z_0-9]+)'", rd("src", "web", "js", "42_kb.js")))
        for page, g in self.g.items():
            for k in g.get("kb", []):
                self.assertIn(k, ids, page)

    def test_tour_selectors_point_to_real_elements(self):
        """Сломанный шаг молча пропускается движком тура — ловим его здесь."""
        for page, steps in self.t.items():
            src = "".join(rd("src", "web", "js", f) for f in PAGE_FILES[page])
            self.assertGreaterEqual(len(steps), 3)
            for st in steps:
                for sel in st["sel"]:
                    for tok in re.findall(r"[#.]([A-Za-z][\w-]*)", sel):
                        self.assertRegex(src, r"(id=\"|class=\"[^\"]*\b|')%s\b" % re.escape(tok), "%s: %s" % (page, sel))
                    m = re.search(r"nth-child\((\d+)\)", sel)
                    if m:
                        tabs = re.findall(r"\['[a-z]+','", rd("src", "web", "js", "19_tax.js").split("const TXTABS=", 1)[1].split("\n", 1)[0])
                        self.assertLessEqual(int(m.group(1)), len(tabs))
                self.assertTrue(st["title"] and st["text"])

    def test_no_emoji_and_short(self):
        for page, g in self.g.items():
            text = g["t"] + "".join(a + b for a, b in g["items"])
            self.assertFalse(re.search("[\U0001F300-\U0001FAFF☀-➿]", text), page)
            self.assertLessEqual(len(g["items"]), 4, page)

    def test_open_once_then_collapsed(self):
        o = jsrun(["71_guides.js"], STUB + r"""
out.first=guideHtml('ret');out.seen=uiGet('guides');
for(const k in GUIDE_OPEN)delete GUIDE_OPEN[k];
out.second=guideHtml('ret');
out.scr=guideHtml('scr');out.none=guideHtml('dash');
UX.whyOff.reb=1;out.hid=guideHtml('reb');
""")
        self.assertIn("guide-body", o["first"])
        self.assertIn("data-kb=\"xirr\"", o["first"])
        self.assertEqual(o["seen"], {"ret": 1})
        self.assertNotIn("guide-body", o["second"])
        self.assertIn("Как это работает", o["second"])
        self.assertNotIn("data-guide-tour", o["second"])            # у «Доходности» тура нет
        self.assertIn("data-guide-tour=\"scr\"", o["scr"])
        self.assertIn("строка", o["scr"])                          # свёрнутая строка — прежняя подсказка UX_WHY
        self.assertIsNone(o["none"])                               # без гида — старая однострочная подсказка
        self.assertNotIn("guide-body", o["hid"])                   # подсказку раньше скрыли: гид сразу свёрнут

    def test_section_tour_does_not_mark_main_tour(self):
        src = rd("src", "web", "js", "58a_tour.js")
        self.assertIn("TOUR.key=own?null:TOUR_KEY", src)
        self.assertIn("if(TOUR.key)uiSet(TOUR.key,tourVer())", src)


if __name__ == "__main__":
    unittest.main()
