/* ── тема, печать ── */
function themeNow(t){return t==='auto'?(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'):t}
function applyTheme(t){try{localStorage.setItem('ta_theme',t)}catch(e){}document.documentElement.dataset.theme=themeNow(t);if(S.cfg)S.cfg.theme=t}
function curTheme(){let t='auto';try{t=localStorage.getItem('ta_theme')||(S.cfg&&S.cfg.theme)||'auto'}catch(e){}return t}
$('#thm').onclick=()=>{const n={auto:'light',light:'dark',dark:'auto'}[curTheme()]||'auto';applyTheme(n);post('/api/config',{theme:n}).catch(()=>{});if(S.data)render()};
$('#pdf').onclick=()=>window.print();
let _prevTheme=null;
window.addEventListener('beforeprint',()=>{_prevTheme=document.documentElement.dataset.theme;document.documentElement.dataset.theme='light'});
window.addEventListener('afterprint',()=>{if(_prevTheme)document.documentElement.dataset.theme=_prevTheme});
function prInfo(){const a=S.accounts.find(x=>x.id===S.account),pg=(PAGES.find(p=>p&&p[0]===S.page)||[])[1]||'';
  const per=PAGES&&PERIOD_PAGES.includes(S.page)?((PERIODS.find(x=>x[0]===S.period)||[])[1]||''):'';
  $('#prinfo').textContent=['TAnalytic',pg,S.account==='all'?'все счета':(a?a.name:''),per,new Date().toLocaleDateString('ru-RU')].filter(Boolean).join(' · ')}

