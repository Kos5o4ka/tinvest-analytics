"""Проверки экранов, карточек, калькулятора и Design System v2 по WINDOWS_REVIEW."""
import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"

OWNED_JS = [
    "src/web/js/10_pos.js",
    "src/web/js/12_bonds.js",
    "src/web/js/14_scr.js",
    "src/web/js/16_pay.js",
    "src/web/js/17_ops.js",
    "src/web/js/20_imp.js",
    "src/web/js/20a_manual.js",
    "src/web/js/25_reb.js",
    "src/web/js/27_bondcard.js",
    "src/web/js/27a_compare.js",
    "src/web/js/31_monitor.js",
    "src/web/js/33a_calc_ui.js",
    "src/web/js/33b_calc_deep.js",
    "src/web/js/35_ladder.js",
    "src/web/js/37_events.js",
    "src/web/js/38_watch.js",
    "src/web/js/45_stock.js",
    "src/web/js/54_txo.js",
]

OWNED_CSS = [
    "src/web/css/15_calc.css",
    "src/web/css/61_review_ui.css",
]


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _run_jsc(body, files=None):
    runner = JSC if os.path.exists(JSC) else shutil.which("jsc")
    if not runner:
        raise unittest.SkipTest("нет jsc")
    files = files or []
    preamble = r"""
const _store = {};
const localStorage = {
  getItem: k => Object.prototype.hasOwnProperty.call(_store, k) ? _store[k] : null,
  setItem: (k, v) => { _store[k] = String(v); },
  removeItem: k => { delete _store[k]; }
};
const navigator = { userAgent: 'Mac', platform: 'MacIntel', clipboard: { writeText: () => Promise.resolve() } };
function URLSearchParams(o){ this._s = Object.entries(o||{}).map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(String(v??''))).join('&'); }
URLSearchParams.prototype.toString = function(){ return this._s; };
const matchMedia = () => ({ matches: false });
const _mkEl = (id='') => ({
  id, style: {}, dataset: {}, classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
  querySelector: () => null, querySelectorAll: () => [], addEventListener(){}, remove(){},
  setAttribute(){}, appendChild(){}, insertAdjacentElement(){}, focus(){}, click(){},
  innerHTML: '', textContent: '', value: '', checked: false, clientWidth: 900, children: []
});
const document = {
  documentElement: { classList: { add(){} }, dataset: {} },
  body: _mkEl('body'),
  head: _mkEl('head'),
  activeElement: null,
  addEventListener(){},
  createElement: () => _mkEl(),
  getElementById: (id) => _mkEl(id),
  querySelector: (sel) => _mkEl(sel),
  querySelectorAll: () => [],
  execCommand: () => true,
  dispatchEvent(){}
};
const window = { matchMedia, addEventListener(){}, fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }) };
function addEventListener(){}
function setTimeout(){ return 1; }
function clearTimeout(){}
function setInterval(){ return 1; }
function requestAnimationFrame(cb){}
function fetch(){ return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }); }
function toast(){}
function go(){}
function render(){}
function renderSoon(){}
function renderNow(){}
function uiConfirm(){ return Promise.resolve(true); }
function uiAlert(){ return Promise.resolve(); }
function uiErr(){}
function bindTip(){}
function hideTip(){}
function prInfo(){}
function notifyUpcoming(){}
function notifyMon(){}
function ident(x){ return '<span class="id">' + esc((x&&x.name)||'') + '</span>'; }
function logo(){ return '<i></i>'; }
function emptyHint(t){ return '<div class="empty">' + esc(t) + '</div>'; }
function ratingTag(r){ return '<span class="tag">' + esc(r && r.v ? r.v : r) + '</span>'; }
const RSC = ['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC','C','D'];
function rBucket(v){ if(!v) return 'other'; const m=String(v).match(/^(AAA|AA|A|BBB|BB|B)/); return m ? m[1] : 'other'; }
function rtClick(){ return { cls:'', attr:'' }; }
function stkAttrIf(){ return ''; }
function rtSafeUrl(u){ return u||''; }
function concCard(){ return ''; }
function ratingsCard(){ return ''; }
function insightsCard(){ return ''; }
function kpNorm(s){ return String(s||'').toLowerCase(); }
function kpScore(){ return 0; }
function candles(){}
function stkDivTab(){ return ''; }
function stkDvLoad(){}
function bindStkDiv(){}
function drawerClose(o,cb){ if(cb)cb(); }
function dayBars(){}
function payMonths(){ return { labels:[], tips:[], series:[] }; }
function payDays(){ return { days:[], legend:[] }; }
var PRO_PAGES = [];
var PRO_FEATURES = {};
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tf:
        tf.write(preamble + "\n")
        for rel in files:
            tf.write(_read(rel) + "\n")
        tf.write("\nconst out = {};\n" + body + "\nprint(JSON.stringify(out));\n")
        path = tf.name
    try:
        r = subprocess.run([runner, path], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise AssertionError(r.stdout + "\n" + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.remove(path)


class TestStaticRulesAndBuild(unittest.TestCase):
    def test_js_syntax_all_files(self):
        runner = JSC if os.path.exists(JSC) else shutil.which("jsc")
        if not runner:
            self.skipTest("нет jsc")
        files = sorted(glob.glob(os.path.join(ROOT, "src/web/js/*.js")))
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tf:
            for f in files:
                tf.write(f"checkSyntax({json.dumps(f)});\n")
            p = tf.name
        try:
            r = subprocess.run([runner, p], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            os.remove(p)

    def test_no_emojis_no_native_dialogs_no_utc_slice(self):
        em = re.compile(r"[\U0001F300-\U0001FAFF]")
        dlg = re.compile(r"(?<![.\w])(confirm|alert)\s*\(")
        for rel in OWNED_JS + OWNED_CSS:
            txt = _read(rel)
            self.assertEqual(em.findall(txt), [], f"Найдены эмодзи в {rel}")
            if rel.endswith(".js"):
                self.assertIsNone(dlg.search(txt), f"Найден нативный confirm/alert в {rel}")
                self.assertNotIn("toISOString().slice(0,10)", txt, rel)
                self.assertNotIn("toISOString().slice(0, 10)", txt, rel)
            self.assertIsNone(re.search(r"var\(--(?:bg2|text)\)", txt), rel)

    def test_css_review_classes_present(self):
        css = _read("src/web/css/61_review_ui.css")
        for cls in (".hb-bar", ".row-act", ".cmp-dock", ".scr-quick", ".pos-layout",
                    ".bc-tabs", ".bc-isin-cp", ".pay-pb", ".cal-day-card",
                    ".wt-prog", ".txo-bdg-ok", ".txo-bdg-soon", ".txo-bdg-loss",
                    ".imp-guides", ".imp-prog", ".ld-split"):
            self.assertIn(cls, css)
        ccss = _read("src/web/css/15_calc.css")
        self.assertIn(".cl-wf", ccss)
        self.assertIn(".cl-iis-cap", ccss)


class TestScreensRuntime(unittest.TestCase):
    CORE = [
        "src/web/js/01_core.js",
        "src/web/js/02_state_api.js",
        "src/web/js/04_charts.js",
        "src/web/js/06_shell.js",
        "src/web/js/07_helpers.js",
    ]

    def test_bonds_screener_compare_and_dock(self):
        files = self.CORE + [
            "src/web/js/10_pos.js",
            "src/web/js/38_watch.js",
            "src/web/js/27_bondcard.js",
            "src/web/js/27a_compare.js",
            "src/web/js/12_bonds.js",
            "src/web/js/14_scr.js",
        ]
        o = _run_jsc("""
        S.data = { portfolio: { total: 100000, positions: [] }, ops: [], accounts: [] };
        S.bonds = {
          metrics: { count: 1, issuers: 1, value: 50000, irr: 18, irr_tax: 15.6, ytm: 18, ytm_tax: 15.6, mdur: 2.1, dur: 2.3, cur_yield: 16, coupons_12m: 8000, stress: {}, high_yield: [] },
          ladder: [['2027', 50000]], risk: [['низкий', 50000]], kinds: [['фикс', 1]],
          rows: [{ isin: 'RU000A0JX0J2', ticker: 'SU26238', name: 'ОФЗ 26238', qty: 50, price_pct: 60.5, ytm: 16.5, ytm_tax: 14.3, spread: 0.5, dur: 4.5, coupon: 7.1, value_rub: 50000, share: 50, rating: { v: 'AAA' } }]
        };
        out.bondsHtml = pBonds();
        S.scr = {
          floor: { lqdt: 15 },
          rows: [{ id: 'SU26238', isin: 'RU000A0JX0J2', name: 'ОФЗ 26238', kind: 'ofz', cur: 'RUB', yield: 16.5, price: 60.5, coupon: 7.1, mat: '2041-05-15', years: 15, macdur: 6.2, turn: 5e7, liq: 'L1', rating: 'AAA' }]
        };
        S.scrDens = 'scatter';
        S.scrBox = { x0: 1, x1: 10, y0: 10, y1: 20 };
        out.scrHtml = pScr0();
        S.cmp = ['RU000A0JX0J2'];
        CMP.d['RU000A0JX0J2'] = {
          c: {
            isin: 'RU000A0JX0J2', name: 'ОФЗ 26238', short: 'ОФЗ 26238',
            market: { price: 60.5, yield: 16.5, coupon: 7.1, nominal: 1000, nkd: 12, dur: 6.2, cur: 'RUB', mat: '2041-05-15' },
            flows: [{ d: '2027-06-01', t: 'coupon', amt: 35.4 }, { d: '2027-12-01', t: 'coupon', amt: 35.4 }]
          }
        };
        out.cmpPage = pCmp();
        out.cmpTbl = cmpTable();
        out.inc = cmpCalcIncome(CMP.d['RU000A0JX0J2'].c, 100000);
        """, files)
        self.assertIn("hb-bar", o["bondsHtml"])
        self.assertIn("row-act", o["bondsHtml"])
        self.assertIn('id="b-csv"', o["bondsHtml"])
        self.assertIn("scr-quick", o["scrHtml"])
        for lbl in ("ОФЗ", "Корпоративные", "Рейтинг A+", "До 3 лет", "Флоатеры", "Без оферты"):
            self.assertIn(lbl, o["scrHtml"])
        self.assertIn('id="scr-csv"', o["scrHtml"])
        self.assertIn('id="cmp-amt"', o["cmpPage"])
        self.assertIn('id="cmp-slot-q"', o["cmpTbl"])
        self.assertIn('id="cmp-cf-wrap"', o["cmpPage"])
        self.assertGreater(o["inc"]["units"], 100)

    def test_bondcard_tabs_and_stock_v2(self):
        files = self.CORE + ["src/web/js/27_bondcard.js", "src/web/js/45_stock.js"]
        o = _run_jsc("""
        const c = {
          isin: 'RU000A100001', name: 'Тест БО-01',
          market: { price: 98.5, yield: 19.2, spread: 2.1, dur: 1.8, turn: 5e6, coupon: 18, nominal: 1000, cur: 'RUB', mat: '2028-05-01' },
          rating: { v: 'AA-', all: [{ agency: 'АКРА', rating: 'AA-(RU)', outlook: 'Стабильный', date: '2026-03-01' }] },
          offers: [{ date: '2027-06-01', kind: 'put' }],
          flows: [{ d: '2027-01-15', t: 'coupon', amt: 90, pct: 18 }],
          analogs: [{ isin: 'RU000A100002', name: 'Аналог 1', yield: 18.5, dur: 1.9, turn: 3e6 }]
        };
        BC.tab = 'overview'; out.t0 = bcBody(c);
        BC.tab = 'flows'; out.t1 = bcBody(c);
        BC.tab = 'issuer'; out.t2 = bcBody(c);
        BC.tab = 'analogs'; out.t3 = bcBody(c);
        S.stk.secid = 'SBER'; S.stk.cardTf = 'D';
        S.stk.card = {
          secid: 'SBER', kind: 'share',
          quote: { secid: 'SBER', shortname: 'Сбербанк', name: 'ПАО Сбербанк', sector: 'Финансы', isin: 'RU0009029540', price: 295, chg_d: 1.2, chg_w: 2.5, chg_m: 4.1, cap: 6.5e12, lot: 10, value_today: 1e10 },
          candles: [], series: {}, ta: { signal: 'покупать', score: 3, votes: [] }, levels: { support: [], resistance: [] }, dividends: { items: [] }
        };
        out.stk = stkCardHtml('stk-');
        """, files)
        for lbl in ("Обзор и параметры", "Денежный поток и оферты", "Эмитент и рейтинги", "Аналоги и кривая"):
            self.assertIn(lbl, o["t0"])
        self.assertIn("data-bc-copy=", o["t0"])
        self.assertIn("st-ver", o["t0"])
        self.assertIn("st-tiles", o["t0"])
        self.assertIn("st-callout", o["t0"])
        self.assertIn("График оферт", o["t1"])
        self.assertIn("Кредитные рейтинги эмитента", o["t2"])
        self.assertIn("Аналоги", o["t3"])
        self.assertIn("st-ver", o["stk"])
        self.assertIn("st-tiles", o["stk"])

    def test_pos_ops_reb_ladder(self):
        files = self.CORE + [
            "src/web/js/10_pos.js",
            "src/web/js/17_ops.js",
            "src/web/js/25_reb.js",
            "src/web/js/35_ladder.js",
        ]
        o = _run_jsc("""
        S.data = {
          portfolio: {
            total: 100000,
            positions: [
              { type: 'bond', isin: 'SU26238', name: 'ОФЗ 26238', qty: 100, price: 600, value_rub: 60000, share: 60, pnl: 1000, pnl_rub: 1000, pnl_pct: 1.7, cur: 'rub' },
              { type: 'share', ticker: 'SBER', name: 'Сбербанк', qty: 100, price: 300, value_rub: 30000, share: 30, pnl: 500, pnl_rub: 500, pnl_pct: 1.7, cur: 'rub' },
              { type: 'share', ticker: 'VTBR', name: 'ВТБ', qty: 1, price: 500, value_rub: 500, share: 0.5, pnl: -10, pnl_rub: -10, pnl_pct: -2, cur: 'rub', blocked: true }
            ]
          },
          ops: [
            ['2026-05-01 12:00', 'BUY', 'buy', 'Сбербанк', 'SBER', 10, 300, -3000, 'rub', 1.5, 0, '', 'Счёт 1'],
            ['2026-08-01 12:00', 'COUPON', 'coupons', 'ОФЗ 26238', 'SU26238', 0, 0, 3500, 'rub', 0, 0, '', 'Счёт 2']
          ]
        };
        S.accounts = [{ id: 'a1', name: 'Счёт 1' }, { id: 'a2', name: 'Счёт 2' }];
        S.account = 'all';
        S.posGroup = 'issuer';
        S.posHideSmall = true;
        out.posHtml = pPos();
        out.posFilteredLen = posFiltered().length;
        S.opsFrom = '2026-06-01'; S.opsTo = '2026-09-01'; S.opsAcc = 'Счёт 2';
        out.opsHtml = pOps();
        out.opsFilteredLen = opsFiltered().length;
        S.reb.lvl = 'class'; S.reb.draft = { share: 20, bond: 80 }; S.reb.contrib = '10000';
        out.rebClass = pReb();
        S.bonds = { rows: [{ isin: 'SU26238', name: 'ОФЗ 26238', value_rub: 60000, rating: { v: 'AAA' } }], payments: [] };
        S.reb.lvl = 'rating';
        out.rebRating = pReb();
        S.reb.lvl = 'paper';
        out.rebPaper = pReb();
        S.ladTab = 'build';
        out.ladBuild = pLadBuild();
        S.ladP = { data: { empty: false, has_offers: false, undated: [], variants: { maturity: {
          summary: { avg_years: 2.5, next: null, heavy: null, gaps: ['2028'], total: 60000 },
          year: [
            { key: '2027', label: '2027', kind: 'y', total: 60000, share: 100, by_type: { redemption: 60000 }, items: [] },
            { key: '2028', label: '2028', kind: 'y', total: 0, share: 0, flag: 'gap', by_type: {}, items: [] }
          ], quarter: [] } } } };
        out.ladMy = ladMy();
        """, files)
        self.assertEqual(o["posFilteredLen"], 2)
        self.assertIn("pos-layout", o["posHtml"])
        self.assertIn('id="pos-grp"', o["posHtml"])
        self.assertIn('id="pos-hsmall"', o["posHtml"])
        self.assertIn('id="pos-man"', o["posHtml"])
        self.assertIn('id="pos-csv"', o["posHtml"])
        self.assertNotIn("max-height:calc(100vh", o["posHtml"])
        self.assertEqual(o["opsFilteredLen"], 1)
        self.assertIn('id="o-from"', o["opsHtml"])
        self.assertIn('id="o-to"', o["opsHtml"])
        self.assertIn('id="o-acc"', o["opsHtml"])
        self.assertIn('id="ops-csv"', o["opsHtml"])
        self.assertIn("Подобрать в Скринере на", o["rebClass"])
        self.assertIn("Подобрать в Скринере на", o["rebRating"])
        self.assertIn("Подобрать в Скринере на", o["rebPaper"])
        self.assertIn("ld-split", o["ladBuild"])
        self.assertIn('data-gap-year="2028"', o["ladMy"])

    def test_pay_events_watch_monitor_txo_and_calc(self):
        files = self.CORE + [
            "src/web/js/10_pos.js",
            "src/web/js/16_pay.js",
            "src/web/js/37_events.js",
            "src/web/js/38_watch.js",
            "src/web/js/31_monitor.js",
            "src/web/js/54_txo.js",
            "src/web/js/33_calc.js",
            "src/web/js/33b_calc_deep.js",
            "src/web/js/33a_calc_ui.js",
        ]
        o = _run_jsc("""
        localStorage.setItem('ta_calc', JSON.stringify({ goalAmt: 50000 }));
        S.bonds = {
          payments: [
            { date: '2026-12-10', name: 'ОФЗ 26238', kind: 'coupon', amount: 120000, isin: 'SU26238' }
          ],
          rows: [{ isin: 'SU26238', name: 'ОФЗ 26238' }]
        };
        out.payHtml = pPay();
        out.calDay = calDaySummaryCard('2026-12-10', [{ date: '2026-12-10', kind: 'coupon', title: 'ОФЗ 26238', amount: 5000, isin: 'SU26238' }], '2026-12-01');
        out.wtProgHit = wtTargetProg(19.5, 18.0, true);
        out.wtProgWait = wtTargetProg(16.0, 20.0, true);
        S.mon = { acc: 'all', t: Date.now(), data: {
          summary: { high: 1, medium: 0, info: 0 }, log: { events: 2, since: '2026-01-01' },
          thresholds: { mon_drop5: 3, mon_drop30: 5, mon_spread30: 1, mon_sell_days: 5, mon_offer_days: 30 },
          alerts: [{ severity: 'high', kind: 'price', name: 'Тест', message: 'Падение', isin: 'RU0001' }],
          rows: [], notes: ['Заметка мониторинга'], cal_days: 20, timings: { total: 0.1 }
        }};
        out.monHtml = pMon();
        S.txo.hAcc = 'all';
        S.txo.h = {
          available: true, year: 2026, tax_before: 10000, tax_after: 4000,
          totals: { saving: 6000, fees: 200, net: 5800, n: 1 },
          deadline: { sale_day: '2026-12-28', last_trading_day: '2026-12-29', days: 10, passed: false },
          candidates: [
            { name: 'Акция А', ticker: 'AAA', qty: 10, qty_total: 10, value: 10000, loss: 5000, gain_in_prefix: 20000, marginal_rate: 0.13, saving: 650, fees: 10, net: 640, selected: true, ldv_status: 'young', ldv_cost: 0, ldv: [] },
            { name: 'Акция Б', ticker: 'BBB', qty: 10, qty_total: 10, value: 10000, loss: 5000, gain_in_prefix: 20000, marginal_rate: 0.13, saving: 650, fees: 10, net: 640, selected: false, ldv_status: 'warn', ldv_badge: '2.7 г', ldv_cost: 0, ldv: [{ status: 'soon', days: 90, bdate: '2024-03-01', gain: 1000 }] },
            { name: 'Акция В', ticker: 'CCC', qty: 10, qty_total: 10, value: 10000, loss: 5000, gain_in_prefix: 20000, marginal_rate: 0.13, saving: 650, fees: 10, net: 640, selected: false, ldv_status: 'critical', ldv_badge: 'ЛДВ', ldv_cost: 1200, net_ldv: -560, ldv: [{ status: 'reached', days: 0, bdate: '2022-01-01', gain: 9000 }] }
          ],
          assumptions: ['Допущение 1']
        };
        out.txoHtml = txoHarvest();
        S.calcAcc = S.account;
        S.calcP = clDefaultParams();
        CL_F = Object.assign({}, CL_DEF, { acct: 'iis3', years: 10, strat: { dep: 1, ofz: 1 }, view: 'ofz' });
        out.calcOut = clOut();
        out.calcForm = clForm(CL_F, S.calcP);
        """, files)
        self.assertIn("pay-pb", o["payHtml"])
        self.assertIn("/ 12 =", o["payHtml"])
        self.assertIn("cal-day-card", o["calDay"])
        self.assertIn("events.ics", o["calDay"])
        self.assertIn("Цель достигнута", o["wtProgHit"])
        self.assertIn("wt-prog", o["wtProgWait"])
        self.assertIn("st-card", o["monHtml"])
        self.assertIn("st-dot", o["monHtml"])
        self.assertIn("st-callout", o["monHtml"])
        self.assertIn("Без риска ЛДВ", o["txoHtml"])
        self.assertIn("До ЛДВ < 6 мес", o["txoHtml"])
        self.assertIn("Потеря ЛДВ", o["txoHtml"])
        self.assertIn("txo-steps", o["txoHtml"])
        self.assertIn('id="txo-csv"', o["txoHtml"])
        self.assertIn("cl-wf", o["calcOut"])
        self.assertIn("Точка обгона вклада", o["calcOut"])
        self.assertIn("52–88 тыс. ₽", o["calcForm"])


if __name__ == "__main__":
    unittest.main()
