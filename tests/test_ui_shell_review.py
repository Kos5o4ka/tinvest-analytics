"""Тесты оболочки интерфейса, экрана блокировки, переноса отчётов, настроек, обзора, графиков и KB."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import ROOT  # noqa: E402

JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _jsc_runner():
    return JSC if os.path.exists(JSC) else shutil.which("jsc")


def _run_jsc(code):
    runner = _jsc_runner()
    if not runner:
        raise unittest.SkipTest("нет jsc")
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "run.js")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(code)
        r = subprocess.run([runner, fp], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError("jsc error:\n" + r.stdout + r.stderr)
    return r.stdout


DOM_STUB = r"""
const _els = {};
function _mkEl(tag, id) {
  return {
    tagName: (tag || 'DIV').toUpperCase(),
    id: id || '',
    className: '',
    innerHTML: '',
    textContent: '',
    value: '',
    checked: false,
    disabled: false,
    hidden: false,
    title: '',
    style: {},
    dataset: {},
    children: [],
    classList: {
      _s: new Set(),
      add(...a){ a.forEach(x=>this._s.add(x)); },
      remove(...a){ a.forEach(x=>this._s.delete(x)); },
      toggle(x, on){ if(on===undefined) on=!this._s.has(x); if(on) this._s.add(x); else this._s.delete(x); },
      contains(x){ return this._s.has(x); }
    },
    setAttribute(){},
    getAttribute(){ return null; },
    addEventListener(){},
    removeEventListener(){},
    querySelector(){ return null; },
    querySelectorAll(){ return []; },
    appendChild(c){ this.children.push(c); if(c && c.id) _els[c.id]=c; return c; },
    remove(){ if(this.id) delete _els[this.id]; },
    closest(){ return null; },
    focus(){},
    select(){},
    click(){}
  };
}
const _ls = {};
var localStorage = {
  getItem(k){ return Object.prototype.hasOwnProperty.call(_ls, k) ? _ls[k] : null; },
  setItem(k, v){ _ls[k] = String(v); },
  removeItem(k){ delete _ls[k]; }
};
var navigator = { platform: 'MacIntel', userAgent: 'Mozilla/5.0 (Macintosh)', userAgentData: { platform: 'macOS' } };
var location = { hash: '', href: 'http://127.0.0.1:8765/' };
var document = {
  readyState: 'complete',
  activeElement: null,
  documentElement: _mkEl('HTML'),
  body: _mkEl('BODY'),
  createElement(t){ return _mkEl(t); },
  getElementById(id){ return _els[id] || null; },
  querySelector(s){ if(s && s[0]==='#') return _els[s.slice(1)] || null; return null; },
  querySelectorAll(){ return []; },
  addEventListener(){}
};
var window = {
  addEventListener(){},
  removeEventListener(){},
  matchMedia(){ return { matches: false }; },
  print(){}
};
var addEventListener = function(){};
var setTimeout = function(fn){ return 1; };
var clearTimeout = function(){};
var setInterval = function(){ return 1; };
var matchMedia = window.matchMedia;
function toast(){}
"""


class TestUiShellSyntaxAndBuild(unittest.TestCase):
    def test_all_js_files_pass_jsc_syntax(self):
        runner = _jsc_runner()
        if not runner:
            raise unittest.SkipTest("нет jsc")
        files = sorted(glob.glob(os.path.join(ROOT, "src", "web", "js", "*.js")))
        self.assertGreater(len(files), 70)
        checks = "\n".join(
            f"if (checkSyntax({json.dumps(p)}) !== 0) {{ print('FAIL:' + {json.dumps(p)}); quit(1); }}"
            for p in files
        )
        checks += f"\nprint('OK:{len(files)}');"
        out = _run_jsc(checks)
        self.assertIn(f"OK:{len(files)}", out)

    def test_build_includes_lock_ui_and_tariffs(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_mod", os.path.join(ROOT, "build.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bundle = mod.build().decode("utf-8")
        self.assertIn("lockShow", bundle)
        self.assertIn("handleGlobalDropFile", bundle)
        self.assertIn("id:'tariffs'", bundle)
        self.assertIn("chartSkeleton", bundle)

    def test_no_color_emojis_or_native_dialogs(self):
        emoji_rx = re.compile(r"[\U0001F300-\U0001FAFF]")
        native_rx = re.compile(r"\b(?:window\.)?(?:confirm|alert)\s*\(")
        for p in sorted(glob.glob(os.path.join(ROOT, "src", "web", "js", "*.js"))):
            txt = open(p, encoding="utf-8").read()
            self.assertEqual(emoji_rx.findall(txt), [], f"Emoji in {p}")
            for line in txt.splitlines():
                s = line.strip()
                if s.startswith("//") or s.startswith("/*"):
                    continue
                self.assertIsNone(native_rx.search(line), f"Native confirm/alert in {p}: {line}")


class TestKbTariffs(unittest.TestCase):
    def test_tariffs_article_content_and_runtime(self):
        kb_path = os.path.join(ROOT, "src", "web", "js", "42_kb.js")
        core_path = os.path.join(ROOT, "src", "web", "js", "01_core.js")
        out = _run_jsc(
            DOM_STUB
            + f"const S={{}};\nload({json.dumps(core_path)});\nload({json.dumps(kb_path)});\n"
            + "const a = KB.find(x => x.id === 'tariffs');\n"
            + "print(JSON.stringify(a));\n"
        )
        art = json.loads(out.strip().splitlines()[-1])
        self.assertIsNotNone(art)
        self.assertEqual(art["c"], "Программа")
        self.assertEqual(art["t"], "Тарифы: Free и Pro")
        body = art["h"]
        for needle in ("0 ₽", "199 ₽/мес", "1 990 ₽/год", "7 дней", "@tanalyticbot", "оплата пока не подключена"):
            self.assertIn(needle.lower(), body.lower())


class TestShellSearchPeriodAndPrefs(unittest.TestCase):
    def test_search_pill_period_bar_and_conn_indicator_in_shell(self):
        html = _read("src/web/shell.html")
        top_part = html.split('<div class="top">', 1)[1].split('<div id="view">', 1)[0]
        self.assertNotIn('id="period"', top_part)
        self.assertIn('id="srch"', top_part)
        self.assertIn("Поиск по бумагам и разделам…", top_part)
        self.assertIn('class="srch-k"', top_part)
        self.assertIn('id="conn-st"', html)
        self.assertIn("Подключено", html)

        shell_js = _read("src/web/js/06_shell.js")
        self.assertIn("function periodBarHtml()", shell_js)
        self.assertIn("PERIOD_PAGES.includes(S.page)", shell_js)

    def test_ui_prefs_hydration_start_page_and_period_pages_in_jsc(self):
        files = [
            os.path.join(ROOT, "src", "web", "js", "01_core.js"),
            os.path.join(ROOT, "src", "web", "js", "02_state_api.js"),
            os.path.join(ROOT, "src", "web", "js", "06_shell.js"),
            os.path.join(ROOT, "src", "web", "js", "22_theme_print.js"),
            os.path.join(ROOT, "src", "web", "js", "58_ux.js"),
        ]
        setup = DOM_STUB + """
        _els['srch'] = _mkEl('BUTTON', 'srch');
        _els['srch-k'] = _mkEl('KBD', 'srch-k');
        _els['nav'] = _mkEl('NAV', 'nav');
        _els['nav-fix'] = _mkEl('NAV', 'nav-fix');
        _els['acl'] = _mkEl('DIV', 'acl');
        _els['hideEmpty'] = _mkEl('INPUT', 'hideEmpty');
        _els['refresh'] = _mkEl('BUTTON', 'refresh');
        _els['title'] = _mkEl('H1', 'title');
        _els['thm'] = _mkEl('BUTTON', 'thm');
        _els['more'] = _mkEl('BUTTON', 'more');
        _els['more-dd'] = _mkEl('DIV', 'more-dd');
        _els['pdf'] = _mkEl('BUTTON', 'pdf');
        _els['eye'] = _mkEl('BUTTON', 'eye');
        _els['view'] = _mkEl('DIV', 'view');
        _els['conn-st'] = _mkEl('SPAN', 'conn-st');
        _els['acc-dd'] = _mkEl('DIV', 'acc-dd');
        function proNavBadge(){ return ''; }
        function isPro(){ return true; }
        """
        loads = "\n".join(_read(os.path.relpath(f, ROOT)) for f in files) + "\n"
        test_js = """
        S.cfg = {
          start_page: 'scr',
          ui_prefs: { theme: 'light', accent: 'emerald', density: 'compact', ux_mode: 'pro', side_mini: true, nav_hidden: ['dfl'], ticker_off: true, incog: true }
        };
        uxSeenSync();
        const res = {
          pageAfterBoot: S.page,
          theme: localStorage.getItem('ta_theme'),
          accent: localStorage.getItem('ta_accent'),
          density: localStorage.getItem('ta_density'),
          uxMode: UX.mode,
          sideMini: UX.mini,
          navHidden: S.navHidden,
          tickerOff: localStorage.getItem('ta_ticker_off'),
          incog: INCOG.on,
          periodPages: PERIOD_PAGES,
        };
        S.data = { portfolio: { total: 1000, positions: [] } };
        S.page = 'dash';
        res.dashHasPeriod = periodBarHtml().includes('id="period"');
        S.page = 'bonds';
        res.bondsHasPeriod = periodBarHtml().includes('id="period"');
        print(JSON.stringify(res));
        """
        out = _run_jsc(setup + loads + test_js)
        res = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(res["pageAfterBoot"], "scr")
        self.assertEqual(res["theme"], "light")
        self.assertEqual(res["accent"], "emerald")
        self.assertEqual(res["density"], "compact")
        self.assertEqual(res["uxMode"], "pro")
        self.assertTrue(res["sideMini"])
        self.assertEqual(res["navHidden"], ["dfl"])
        self.assertEqual(res["tickerOff"], "1")
        self.assertTrue(res["incog"])
        self.assertEqual(res["periodPages"], ["dash", "ret", "bench", "ops", "fees"])
        self.assertTrue(res["dashHasPeriod"])
        self.assertFalse(res["bondsHasPeriod"])


class TestLockAndDragDrop(unittest.TestCase):
    def test_api_423_triggers_lockShow_in_jsc(self):
        core_path = os.path.join(ROOT, "src", "web", "js", "01_core.js")
        state_path = os.path.join(ROOT, "src", "web", "js", "02_state_api.js")
        code = DOM_STUB + f"""
        load({json.dumps(core_path)});
        load({json.dumps(state_path)});
        let lockCalledWith = null;
        function lockShow(j){{ lockCalledWith = j; }}
        function fetch(){{
          return Promise.resolve({{ ok: false, status: 423, json: () => Promise.resolve({{ error: 'locked', enabled: true, unlocked: false }}) }});
        }}
        (async () => {{
          let err = null;
          try {{ await api('/api/summary'); }} catch(e) {{ err = e.message; }}
          for (let i = 0; i < 5; i++) await Promise.resolve();   // экран блокировки берёт настройки из /api/lock/status
          print(JSON.stringify({{ err, lockCalledWith }}));
        }})();
        """
        out = _run_jsc(code)
        res = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(res["err"], "locked")
        self.assertEqual(res["lockCalledWith"], {"error": "locked", "enabled": True, "unlocked": False})

    def test_lock_and_drop_overlay_markup_and_endpoints(self):
        lock_js = _read("src/web/js/69_lock_ui.js")
        self.assertIn("/api/lock/status", lock_js)
        self.assertIn("/api/lock/unlock", lock_js)
        self.assertIn("lock-ov", lock_js)
        self.assertIn("lock-bio", lock_js)
        self.assertIn("lock-pin", lock_js)
        self.assertIn("drop-ov", lock_js)
        self.assertIn("Отпустите файл, чтобы импортировать отчёт брокера", lock_js)
        self.assertIn("impDropFile", lock_js)
        self.assertIn("_pendingDropFile", lock_js)


class TestDashboardAndCharts(unittest.TestCase):
    def test_dash_sparkline_delta_badge_and_top8_toggle(self):
        core_path = os.path.join(ROOT, "src", "web", "js", "01_core.js")
        dash_path = os.path.join(ROOT, "src", "web", "js", "08_dash.js")
        code = DOM_STUB + f"""
        load({json.dumps(core_path)});
        load({json.dumps(dash_path)});
        const hs = {{ value: [100000, 105000, 110000], invested: [100000, 100000, 100000], total: 0.10 }};
        const svg = heroSparkSvg(hs);
        const badge = dashDeltaBadge(hs);
        print(JSON.stringify({{ hasSvg: svg.includes('<svg') && svg.includes('<polyline'), badge }}));
        """
        out = _run_jsc(code)
        res = json.loads(out.strip().splitlines()[-1])
        self.assertTrue(res["hasSvg"])
        self.assertIn("dash-delta", res["badge"])
        self.assertIn("10", res["badge"])
        self.assertIn("%", res["badge"])

        dash_src = _read("src/web/js/08_dash.js")
        self.assertIn("hero-spark", dash_src)
        self.assertIn("Топ-8", dash_src)
        self.assertIn("data-dash-top", dash_src)

    def test_charts_skeleton_and_unified_crosshair(self):
        core_path = os.path.join(ROOT, "src", "web", "js", "01_core.js")
        charts_path = os.path.join(ROOT, "src", "web", "js", "04_charts.js")
        code = DOM_STUB + f"""
        const S = {{ charts: [] }};
        load({json.dumps(core_path)});
        load({json.dumps(charts_path)});
        const el = _mkEl('DIV', 'ch1');
        _els['ch1'] = el;
        chartSkeleton('ch1', 220, 'Загрузка…');
        print(JSON.stringify({{ html: el.innerHTML }}));
        """
        out = _run_jsc(code)
        res = json.loads(out.strip().splitlines()[-1])
        self.assertIn("chart-sk", res["html"])
        self.assertIn("min-height:220px", res["html"])
        self.assertIn("Загрузка…", res["html"])

        charts_src = _read("src/web/js/04_charts.js")
        self.assertIn("function chartSkeleton(", charts_src)
        self.assertIn("function chartEnhanceIssuerCurve(", charts_src)
        self.assertIn('<g class="hv"></g>', charts_src)


class TestSettingsEnhancements(unittest.TestCase):
    def test_settings_sections_and_controls(self):
        s_main = _read("src/web/js/21_set.js")
        s_parts = _read("src/web/js/21a_set_parts.js")
        s_ui = _read("src/web/js/21b_set_ui.js")
        css_set = _read("src/web/css/56_settings_v2.css")

        self.assertIn("'set-sec'", s_main)
        self.assertIn("Блокировка при входе (Touch ID / Windows Hello / PIN)", s_main)
        self.assertIn("lk-pin", s_main)
        self.assertIn("lk-bio-test", s_main)
        self.assertIn("lk-now", s_main)
        self.assertIn("/api/localdata/vacuum", s_main)
        self.assertIn("ST_DIRTY_REG", s_main)

        self.assertIn("/api/crowd/log", s_parts)
        self.assertIn("Журнал сбора раскрытий", s_parts)

        self.assertIn('id="start-page"', s_ui)
        for p in ("dash", "bonds", "scr", "cal"):
            self.assertIn(f"['{p}',", s_ui)
        self.assertIn('id="ntf-test"', s_ui)
        self.assertIn('id="st-dirty-bar"', s_ui)
        self.assertIn('id="st-dirty-cancel"', s_ui)
        self.assertIn('id="st-dirty-save"', s_ui)
        self.assertIn(".st-dirty-bar", css_set)


class TestUiFixesBatch(unittest.TestCase):
    def test_roadmap_removed_and_changelog_kept(self):
        s_ui = _read("src/web/js/21b_set_ui.js")
        s_boot = _read("src/web/js/26_changelog_boot.js")
        self.assertNotIn("Роадмап", s_ui)
        self.assertNotIn("roadmapHtml", s_ui)
        self.assertIn("whatsnew", s_ui)
        self.assertNotIn("roadmapHtml", s_boot)
        self.assertIn("changelogHtml", s_boot)

    def test_calc_split_and_aside_width(self):
        css = _read("src/web/css/15_calc.css")
        self.assertIn("minmax(340px,400px) minmax(0,1fr)", css)
        self.assertIn("aside.cl-side,.cl-side", css)
        self.assertIn("width:100%", css)
        self.assertIn("@media(max-width:1100px){.cl-split{grid-template-columns:1fr}", css)

    def test_arb_null_guard_nowrap_and_ux_sub(self):
        arb = _read("src/web/js/59_arb.js")
        prem = _read("src/web/css/52_premium.css")
        self.assertIn("S.page==='arb'&&$('#view')", arb)
        self.assertIn("flex-wrap:nowrap", arb)
        self.assertIn("border-radius:10px 10px 0 0", prem)
        self.assertIn("border-radius:12px", prem)

    def test_flows_default_period_day(self):
        flw = _read("src/web/js/48_flows.js")
        self.assertIn("period:'day'", flw)

    def test_bell_compact_card_and_css(self):
        ux = _read("src/web/js/68_ux_extra.js")
        winfix = _read("src/web/css/59_winfix.css")
        self.assertIn("function bellAlertHtml(", ux)
        self.assertIn("bell-card", ux)
        self.assertIn("bell-top", ux)
        self.assertIn("bell-body", ux)
        self.assertIn(".bell-card{", winfix)
        self.assertIn(".bell-top{", winfix)
        self.assertIn(".bell-body{", winfix)

    def test_settings_stack_and_unified_inputs(self):
        css_set = _read("src/web/css/56_settings_v2.css")
        css_tbl = _read("src/web/css/05_tables_forms.css")
        css_prem = _read("src/web/css/52_premium.css")
        self.assertIn(".st-row.stack .st-t{flex:none}", css_set)
        for css in (css_tbl, css_prem):
            self.assertIn("height:38px", css)
            self.assertIn("box-sizing:border-box", css)
            self.assertIn("appearance:none", css)

    def test_dash_hero_logo_test_png_and_monitor_error(self):
        logos_path = os.path.join(ROOT, "src", "web", "js", "05_logos.js")
        core_path = os.path.join(ROOT, "src", "web", "js", "01_core.js")
        code = DOM_STUB + f"""
        load({json.dumps(core_path)});
        load({json.dumps(logos_path)});
        const html1 = logo({{name:'Тест', ticker:'TEST', logo:'test.png'}}, 34);
        const html2 = logo({{name:'Сбер', ticker:'SBER', logo:'sber.png'}}, 34);
        print(JSON.stringify({{ hasTest: html1.includes('/logo/'), hasSber: html2.includes('/logo/sber.png') }}));
        """
        out = _run_jsc(code)
        res = json.loads(out.strip().splitlines()[-1])
        self.assertFalse(res["hasTest"])
        self.assertTrue(res["hasSber"])

        mon = _read("src/web/js/31_monitor.js")
        self.assertIn("if(['mon','dash'].includes(S.page))renderSoon()", mon.split(".catch(")[1])

        winfix = _read("src/web/css/59_winfix.css")
        self.assertIn(".hero>.meta{position:relative;z-index:1}", winfix)
        self.assertIn("top:auto;bottom:0", winfix)

    def test_topbar_nowrap_desktop(self):
        lay = _read("src/web/css/02_layout.css")
        winfix = _read("src/web/css/59_winfix.css")
        self.assertIn("flex-wrap:nowrap", lay)
        self.assertIn(".top{flex-wrap:nowrap}", winfix)


if __name__ == "__main__":
    unittest.main()
