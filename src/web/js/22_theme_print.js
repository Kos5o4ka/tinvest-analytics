/* ── тема, печать ── */
function themeNow(t){return t==='auto'?(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'):t}
let _thmT=0;
function applyTheme(t){try{localStorage.setItem('ta_theme',t)}catch(e){}const h=document.documentElement;h.classList.add('thm-anim');clearTimeout(_thmT);_thmT=setTimeout(()=>h.classList.remove('thm-anim'),260);h.dataset.theme=themeNow(t);if(S.cfg)S.cfg.theme=t;thmLabel()}
function thmLabel(){const e=document.getElementById('thm-t');if(e)e.textContent=document.documentElement.dataset.theme==='light'?'Тёмная тема':'Светлая тема'}
function curTheme(){let t='auto';try{t=localStorage.getItem('ta_theme')||(S.cfg&&S.cfg.theme)||'auto'}catch(e){}return t}
// один клик = видимая смена: от того, что сейчас на экране (раньше цикл auto→light→dark→auto при тёмной системе давал «пустой» клик dark→auto)
$('#thm').onclick=()=>{const n=document.documentElement.dataset.theme==='light'?'dark':'light';applyTheme(n);post('/api/config',{theme:n}).catch(()=>{});render()};
thmLabel();
// меню «⋯» в шапке
function moreOpen(on){const d=$('#more-dd');d.hidden=!on;$('#more').setAttribute('aria-expanded',on?'true':'false')}
$('#more').onclick=e=>{e.stopPropagation();moreOpen($('#more-dd').hidden)};
$('#more-dd').addEventListener('click',e=>{if(e.target.closest('.mi'))setTimeout(()=>moreOpen(false),0)});
document.addEventListener('click',e=>{if(!e.target.closest('#more-wrap'))moreOpen(false)});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#more-dd').hidden)moreOpen(false)});
$('#pdf').onclick=()=>window.print();
let _prevTheme=null;
window.addEventListener('beforeprint',()=>{_prevTheme=document.documentElement.dataset.theme;document.documentElement.dataset.theme='light'});
window.addEventListener('afterprint',()=>{if(_prevTheme)document.documentElement.dataset.theme=_prevTheme});
function prInfo(){const a=S.accounts.find(x=>x.id===S.account),pg=(PAGES.find(p=>p&&p[0]===S.page)||[])[1]||'';
  const per=PAGES&&PERIOD_PAGES.includes(S.page)?((PERIODS.find(x=>x[0]===S.period)||[])[1]||''):'';
  $('#prinfo').textContent=['TAnalytic',pg,S.account==='all'?'все счета':(a?a.name:''),per,new Date().toLocaleDateString('ru-RU')].filter(Boolean).join(' · ')}

