"""Математика калькулятора на JS (src/web/js/33_calc.js) через JavaScriptCore: без браузера и без сети.
Тесты пропускаются, если на машине нет jsc (macOS) или node."""
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
ENGINE = os.path.join(ROOT, "src", "web", "js", "33_calc.js")

PRE = r"""
const P=clDefaultParams();P.portfolio={irr:15,dur_bonds:3,value:1e6,shares:{bonds:.5,stocks:.3,funds:0,lqdt:.1,cash:.1,other:0}};
const mkF=o=>Object.assign({start:500000,monthly:20000,idx:5,years:10,ownRate:15,reinvest:true,freq:4,lot:1000,lotFund:'fund',scn:'cbr',ownKey:12,acct:'plain',
  reinvDed:true,ldv:true,defaults:true,depSpread:1.5,mixStk:50,mixBond:'ofz',stkGrow:'',stkDiv:'',stkSig:'',fxWeak:'',iisYear:0,salRate:13,salary:0},o||{});
const SD=new Date(2026,0,1);
const run=(id,o,months)=>{const F=mkF(o),env=clEnv(P,F,SD),p=clParams(F,months||0,2026);return clSim(id,p,P,env,F)};
const out={};
"""


def js(body):
    runner = JSC if os.path.exists(JSC) else shutil.which("jsc")
    if not runner:
        raise unittest.SkipTest("нет jsc")
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "t.js")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("load(%s);\n%s\n%s\nprint(JSON.stringify(out));\n" % (json.dumps(ENGINE), PRE, body))
        r = subprocess.run([runner, f], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise AssertionError(r.stdout + r.stderr)
    return json.loads(r.stdout.strip().splitlines()[-1])


class Tax(unittest.TestCase):
    def test_ndfl_scale_and_iis_term(self):
        o = js("out.a=clNdfl(2.4e6);out.b=clNdfl(3e6);out.c=clNdfl(3e6,.5);out.z=clNdfl(-5);"
               "out.t=[2024,2026,2027,2029,2030,2031,2040].map(clIisTerm);")
        self.assertAlmostEqual(o["a"], 312000.0)
        self.assertAlmostEqual(o["b"], 312000 + 600000 * 0.15)
        self.assertAlmostEqual(o["c"], 1.2e6 * 0.13 + 1.8e6 * 0.15)     # порог 15 % делится пропорционально доле портфеля
        self.assertEqual(o["z"], 0)
        self.assertEqual(o["t"], [5, 5, 6, 8, 9, 10, 10])               # как txo_iis3_term на сервере

    def test_iis_term_depends_on_open_year(self):
        o = js("""
        const mk=y=>{const F=mkF({acct:'iis3',iisYear:y}),p=clParams(F,0,2026);return clAccInfo(p)};
        out.y2026=mk(2026);out.y2024=mk(2024);
        const F=mkF({acct:'iis3',years:5}),p=clParams(F,0,2026);out.five=clAccInfo(p).exempt;
        const F2=mkF({acct:'iis3',years:4}),p2=clParams(F2,0,2026);out.four=clAccInfo(p2).exempt;
        """)
        self.assertEqual(o["y2026"]["term"], 5)
        self.assertEqual(o["y2024"]["term"], 5)
        self.assertTrue(o["five"])
        self.assertFalse(o["four"])

    def test_iis_passive_income_is_tax_free(self):
        o = js("""
        const a=run('ofz',{acct:'iis3'}),b=run('ofz',{acct:'plain'});
        out.iis=[a.passive*12,a.incGross];out.plain=[b.passive*12,b.incGross];out.taxIis=a.taxes;""")
        self.assertAlmostEqual(o["iis"][0], o["iis"][1], places=4)           # налога на пассивный доход на ИИС-3 нет
        self.assertLess(o["plain"][0], o["plain"][1] * 0.9)                  # на обычном счёте налог есть
        self.assertEqual(o["taxIis"], 0)

    def test_iis_short_term_returns_deductions_and_taxes_income(self):
        o = js("""
        const a=run('ofz',{acct:'iis3',years:3}),b=run('ofz',{acct:'iis3',years:5}),c=run('ofz',{acct:'iis3',years:3,iisYear:2024});
        out.short={ded:a.deductions,tax:a.taxes,final:a.final};out.long={ded:b.deductions,tax:b.taxes};out.plain=c.final;""")
        self.assertAlmostEqual(o["short"]["ded"], 0.0, places=6)             # вычеты вернулись
        self.assertGreater(o["short"]["tax"], 0)
        self.assertGreater(o["long"]["ded"], 0)
        self.assertEqual(o["long"]["tax"], 0)
        self.assertLess(o["short"]["final"], o["plain"])        # при выдержанном сроке (счёт открыт в 2024 году) итог выше, чем при досрочном закрытии

    def test_refund_limited_by_salary_and_rate(self):
        o = js("""
        const f=(o)=>{const F=mkF(Object.assign({acct:'iis3',start:0,monthly:50000,idx:0,years:5},o)),p=clParams(F,0,2026);return clRefunds(p,clAccInfo(p))[12]};
        out.r13=f({});out.r15=f({salRate:15});out.low=f({salary:200000});out.none=f({salRate:0});""")
        self.assertAlmostEqual(o["r13"], 52000.0)       # 400 тыс. × 13 %
        self.assertAlmostEqual(o["r15"], 60000.0)
        self.assertAlmostEqual(o["low"], 26000.0)       # официальный доход 200 тыс. в год: вернуть больше уплаченного нельзя
        self.assertEqual(o["none"], 0)                  # ИП и самозанятые без НДФЛ с зарплаты вычет не получают

    def test_no_one_million_limit_in_engine(self):
        o = js("const F=mkF({acct:'iis3',start:3e6,monthly:0,years:5}),p=clParams(F,0,2026);out.r=clRefunds(p,clAccInfo(p));out.n=p.months;")
        self.assertAlmostEqual(o["r"][12], 52000.0)     # вычет ограничен базой 400 тыс., а не взносом 1 млн


class Deposit(unittest.TestCase):
    def test_tax_paid_next_december(self):
        o = js("const r=run('dep',{start:1e7,monthly:0,years:3,scn:'own',ownKey:20});out.log=r.taxLog;out.taxes=r.taxes;")
        self.assertGreaterEqual(len(o["log"]), 2)
        first = min(x[0] for x in o["log"])
        self.assertEqual(first, 23)         # налог за 2026 год: 1 декабря 2027 года (месяц 23 от 1 января 2026)
        self.assertAlmostEqual(sum(x[1] for x in o["log"]), o["taxes"], places=4)


class Lots(unittest.TestCase):
    def test_ldv_weighted_term_and_limit(self):
        """Две крупные покупки: ЛДВ по лотам старше трёх лет, срок — средневзвешенный по паям; прирост сверх лимита облагается."""
        o = js("""
        const F=mkF({start:1e6,monthly:1e6,idx:0,years:5,scn:'own',ownKey:100,ldv:true}),env=clEnv(P,F,SD),p=clParams(F,0,2026);
        const r=clSimLots(p,env,clFundA(env));
        let gain=0,eg=0,eu=0,ey=0;
        for(let k0=0;k0<=60;k0++){const amt=k0===0?1e6:(k0<=60?1e6:0);if(k0>60)break;const u=amt/env.G[k0],v=u*env.G[60],g=v-amt;gain+=g;
          if(60-k0>=36){eg+=g;eu+=u;ey+=u*Math.floor((60-k0)/12)}}
        const ex=Math.min(eg,3e6*(ey/eu));
        out.tax=r.taxes;out.exp=clNdfl(Math.max(0,gain-ex));out.eg=eg;out.lim=3e6*(ey/eu);
        const F2=mkF({start:1e6,monthly:1e6,idx:0,years:5,scn:'own',ownKey:100,ldv:false}),e2=clEnv(P,F2,SD);
        out.noLdv=clSimLots(clParams(F2,0,2026),e2,clFundA(e2)).taxes;""")
        self.assertGreater(o["eg"], o["lim"])              # лимит действительно сработал
        self.assertAlmostEqual(o["tax"], o["exp"], places=2)
        self.assertGreater(o["noLdv"], o["tax"])

    def test_ldv_not_applied_before_three_years(self):
        o = js("""const a=run('fund',{years:2,ldv:true}),b=run('fund',{years:2,ldv:false});out.a=a.taxes;out.b=b.taxes;""")
        self.assertAlmostEqual(o["a"], o["b"], places=6)


class Engine(unittest.TestCase):
    def test_portfolio_reacts_to_key_rate_and_has_structure(self):
        o = js("""
        const lo=run('pf',{scn:'own',ownKey:8}),hi=run('pf',{scn:'own',ownKey:22});
        out.lo=lo.final;out.hi=hi.final;out.n=clParts('pf',P,mkF()).length;out.w=clParts('pf',P,mkF()).reduce((a,x)=>a+x.w,0);""")
        self.assertNotAlmostEqual(o["lo"], o["hi"], places=0)
        self.assertEqual(o["n"], 4)
        self.assertAlmostEqual(o["w"], 1.0)

    def test_floater_follows_key_rate_ofz_less(self):
        o = js("""
        const f=(id,k)=>run(id,{scn:'own',ownKey:k,years:5}).final;
        out.flt=f('flt',24)/f('flt',8);out.ofz=f('ofz',24)/f('ofz',8);""")
        self.assertGreater(o["flt"], o["ofz"])

    def test_mix_is_between_components(self):
        o = js("""
        const s=run('stk',{years:8,start:1e6,monthly:0}).final,b=run('ofz',{years:8,start:1e6,monthly:0}).final,
          m=run('mix',{years:8,start:1e6,monthly:0,mixStk:50}).final;out.s=s;out.b=b;out.m=m;""")
        self.assertGreater(o["m"], min(o["s"], o["b"]))
        self.assertLess(o["m"], max(o["s"], o["b"]) * 1.001)

    def test_defaults_are_discrete_not_smeared(self):
        o = js("""
        const a=run('hy',{defaults:true}),b=run('hy',{defaults:false});out.same=a.final-b.final;
        const mc=clMC(mkF({years:8}),P,'hy',120,3,SD);out.p=[mc.p10[96],mc.p50[96],mc.p90[96]];out.d=mc.defaults;
        out.det=run('hy',{years:8}).final;""")
        self.assertEqual(o["same"], 0)                   # без случайных событий капитал не «усыхает» каждый месяц
        self.assertLess(o["p"][0], o["p"][1])
        self.assertLess(o["p"][1], o["p"][2])
        self.assertGreater(o["d"], 0)                    # в траекториях Монте-Карло дефолты случаются как события
        self.assertLess(o["p"][1], o["det"])             # медиана с дефолтами и шоками ставки ниже бездефолтной траектории

    def test_goal_solver_matches_target(self):
        o = js("""
        const F=mkF({goalAmt:60000,goalMode:'contrib',years:10,acct:'iis3'}),env=clEnv(P,F,SD),g=clGoal(F,P,env,'ofz',true);
        const p=clParams(F,0,2026);p.monthly=g.monthly;const r=clSim('ofz',p,P,env,F);out.ok=g.ok;out.pas=r.passiveReal;
        const F2=mkF({goalAmt:60000,goalMode:'years',acct:'plain'}),g2=clGoal(F2,P,clEnv(P,F2,SD),'ofz',true);out.m=g2.months;""")
        self.assertTrue(o["ok"])
        self.assertAlmostEqual(o["pas"], 60000.0, delta=60)
        self.assertGreater(o["m"], 12)

    def test_stock_dividends_taxed_on_plain_and_free_on_iis(self):
        o = js("const a=run('stk',{acct:'plain'}),b=run('stk',{acct:'iis3'});out.a=a.passive*12/a.incGross;out.b=b.passive*12/b.incGross;")
        self.assertLess(o["a"], 0.9)
        self.assertAlmostEqual(o["b"], 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
