"""Остатки ревью интерфейса: CSV-хелпер, точка обгона вклада, вкладки карточки облигации, скелетоны, локальный период."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import ROOT  # noqa: E402

JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
JS = os.path.join(ROOT, "src", "web", "js")


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def jsrun(files, body):
    runner = JSC if os.path.exists(JSC) else shutil.which("jsc")
    if not runner:
        raise unittest.SkipTest("нет jsc")
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "t.js")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("".join("load(%s);\n" % json.dumps(os.path.join(JS, x)) for x in files))
            fh.write("const out={};\n%s\nprint(JSON.stringify(out));\n" % body)
        r = subprocess.run([runner, f], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise AssertionError(r.stdout + r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


class CsvHelper(unittest.TestCase):
    def test_bom_semicolon_crlf_and_quotes(self):
        o = jsrun(["70_ui_leftovers.js"],
                  "out.t=taCsvText(['Название','Цена, %'],[['ОФЗ 26238; «длинная»','97,5'],['С \"кавычкой\"',null],['=1+1','@x']]);")
        t = o["t"]
        self.assertTrue(t.startswith("﻿"))
        lines = t[1:].split("\r\n")
        self.assertEqual(lines[0], "Название;Цена, %")
        self.assertEqual(lines[1], '"ОФЗ 26238; «длинная»";97,5')
        self.assertEqual(lines[2], '"С ""кавычкой""";')
        self.assertEqual(lines[3], "'=1+1;'@x")          # защита от формул Excel

    def test_buttons_are_russian_and_auto_attached(self):
        src = rd("src", "web", "js", "10_pos.js")
        self.assertIn("Скачать CSV", src)
        self.assertNotIn("Экспорт CSV", src)
        self.assertIn("taCsvAttach", rd("src", "web", "js", "70_ui_leftovers.js"))
        # основные таблицы уже имеют свою кнопку
        for f in ("12_bonds.js", "14_scr.js", "17_ops.js", "54_txo.js"):
            self.assertIn("taCsvBtn", rd("src", "web", "js", f))


class Overtake(unittest.TestCase):
    def test_overtake_month(self):
        o = jsrun(["33_calc.js"], """
out.a=clOvertake([0,1,2,3,4,5],[0,2,2.5,3,3.5,4]);
out.b=clOvertake([0,3,3,3,3,3],[0,1,2,3,4,5]);
out.c=clOvertake([0,1,1,1],[0,2,2,2]);
out.d=clOvertake([0,5,6,7,8],[0,4,5,6,7]);
""")
        self.assertEqual(o["a"]["beats"], True)
        self.assertEqual(o["a"]["month"], 4)               # c этого месяца выше до конца срока
        self.assertEqual(o["b"], {"beats": False, "ever": True})   # был впереди, но к концу вклад обогнал
        self.assertEqual(o["c"], {"beats": False, "ever": False})
        self.assertEqual(o["d"]["month"], 1)

    def test_fixed_deposit_rate_moves_overtake(self):
        pre = """
const P=clDefaultParams();P.portfolio=null;
const mkF=o=>Object.assign({start:500000,monthly:20000,idx:5,years:10,ownRate:15,reinvest:true,freq:4,lot:1000,lotFund:'fund',scn:'cbr',ownKey:12,acct:'plain',
  reinvDed:true,ldv:true,defaults:true,depSpread:1.5,depFixed:'',mixStk:50,mixBond:'ofz',stkGrow:'',stkDiv:'',stkSig:'',fxWeak:'',iisYear:0,salRate:13,salary:0},o||{});
const SD=new Date(2026,0,1);
const cmp=o=>{const F=mkF(o),env=clEnv(P,F,SD),p=clParams(F,0,2026);const d=clSim('dep',p,P,env,F),b=clSim('ofz',p,P,env,F);return{rate:env.depRate(0),o:clOvertake(b.cap,d.cap),fd:d.cap[p.months],fb:b.cap[p.months]}};
"""
        o = jsrun(["33_calc.js"], pre + "out.lo=cmp({depFixed:2});out.hi=cmp({depFixed:40});out.base=cmp({});")
        self.assertAlmostEqual(o["lo"]["rate"], 2.0)
        self.assertAlmostEqual(o["hi"]["rate"], 40.0)
        self.assertTrue(o["lo"]["o"]["beats"])              # вклад под 2 % проигрывает ОФЗ почти сразу
        self.assertLessEqual(o["lo"]["o"]["month"], 3)
        self.assertFalse(o["hi"]["o"]["beats"])             # вклад под 40 % ОФЗ не догонит
        self.assertGreater(o["hi"]["fd"], o["hi"]["fb"])
        self.assertNotAlmostEqual(o["base"]["rate"], 2.0)   # по умолчанию ставка идёт от ключевой

    def test_ui_has_field_row_and_chart_mark(self):
        ui = rd("src", "web", "js", "33a_calc_ui.js")
        self.assertIn("depFixed", ui)
        self.assertIn("Вклад: своя ставка, % годовых", ui)
        self.assertIn("'Обгон вклада'", ui)
        self.assertIn("marks", ui)
        self.assertIn("o.marks", rd("src", "web", "js", "04_charts.js"))


class Tabs(unittest.TestCase):
    def test_bondcard_tabs_remembered(self):
        s = rd("src", "web", "js", "27_bondcard.js")
        self.assertIn("BC_TABS=[", s)
        self.assertIn("lsSet('ta_bc_tab'", s)
        self.assertIn("BC.tab=bcSavedTab()", s)
        o = jsrun(["70_ui_leftovers.js"], """
const BC_TABS=[['overview','a'],['flows','b']];let st='flows';
globalThis.lsGet=()=>st;out.a=bcSavedTab();st='junk';out.b=bcSavedTab();""")
        self.assertEqual((o["a"], o["b"]), ("flows", "overview"))


class SkeletonsAndPeriod(unittest.TestCase):
    def test_wait_chart_used_and_reduced_motion(self):
        self.assertIn("const waitChart=", rd("src", "web", "js", "07_helpers.js"))
        for f in ("09_ret.js", "32_bench.js", "24_rates.js", "12_bonds.js"):
            self.assertIn("waitChart(", rd("src", "web", "js", f), f)
        self.assertIn("chartSkeletonHtml", rd("src", "web", "js", "27_bondcard.js"))
        self.assertIn("prefers-reduced-motion", rd("src", "web", "css", "59_winfix.css"))

    def test_local_period_switch(self):
        for f in ("08_dash.js", "09_ret.js", "18_fees.js"):
            self.assertIn("periodSegLocal()", rd("src", "web", "js", f), f)
        self.assertIn(".per-local", rd("src", "web", "css", "62_leftovers.css"))


if __name__ == "__main__":
    unittest.main()
