/* ── «Приятность»: тосты, индикатор фоновой загрузки, память прокрутки, горячие клавиши и шпаргалка ── */

/* 1. Тосты: toast(text, kind?, ms?) — kind: 'ok' | 'info' | 'err'; второй аргумент-число = длительность (совместимо со старым вызовом) */
var TOAST_IC={
  ok:'<path d="M5 12.5l4.2 4.2L19 7"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  err:'<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16h.01"/>'
};
function toast(msg,a,b){
  let kind='info',ms=2500;
  if(typeof a==='number')ms=a;else if(typeof a==='string'){kind=TOAST_IC[a]?a:'info';if(typeof b==='number')ms=b}
  if(kind==='info'&&typeof a!=='string'&&/^(не удалось|ошибка)/i.test(String(msg)))kind='err';
  else if(kind==='info'&&typeof a!=='string'&&/(скопирован|добавлен|сохран|показан|скрыт)/i.test(String(msg)))kind='ok';
  let box=document.getElementById('toasts');
  if(!box){box=document.createElement('div');box.id='toasts';box.setAttribute('role','status');box.setAttribute('aria-live','polite');document.body.appendChild(box)}
  msg=String(msg);
  const same=[...box.children].find(x=>x._msg===msg&&!x._gone);
  if(same){clearTimeout(same._t);same._t=setTimeout(same._close,ms);return}
  const el=document.createElement('div');
  el.className='toast-i k-'+kind;el._msg=msg;
  el.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+TOAST_IC[kind]+'</svg><span></span>';
  el.lastChild.textContent=msg;
  el._close=()=>{if(el._gone)return;el._gone=true;clearTimeout(el._t);el.classList.remove('in');el.classList.add('out');setTimeout(()=>el.remove(),260)};
  el.onclick=el._close;
  box.appendChild(el);
  while(box.children.length>4)box.firstChild._close&&box.firstChild._close(),box.firstChild.remove();
  requestAnimationFrame(()=>requestAnimationFrame(()=>el.classList.add('in')));
  el._t=setTimeout(el._close,ms);
}

/* 2. Тонкая полоса фоновой загрузки под верхней панелью: показывается, если /api/* висит дольше 300 мс */
(function(){
  if(typeof window==='undefined'||!window.fetch||window._dlFetch)return;
  window._dlFetch=1;
  const orig=window.fetch.bind(window);
  let active=0,showT=0,shown=0,shownAt=0,hideT=0;
  const bar=()=>{
    let b=document.getElementById('dl-bar');
    if(!b){const top=document.querySelector('.top');if(!top)return null;b=document.createElement('div');b.id='dl-bar';b.setAttribute('aria-hidden','true');b.innerHTML='<i></i>';top.appendChild(b)}
    return b;
  };
  const show=()=>{showT=0;if(!active)return;const b=bar();if(!b)return;clearTimeout(hideT);shown=1;shownAt=Date.now();b.classList.add('on')};
  const hide=()=>{
    clearTimeout(showT);showT=0;
    if(!shown)return;
    const wait=Math.max(0,450-(Date.now()-shownAt));
    hideT=setTimeout(()=>{if(active)return;shown=0;const b=document.getElementById('dl-bar');if(b)b.classList.remove('on')},wait);
  };
  const tracked=(inp,opt)=>{
    try{
      const u=typeof inp==='string'?inp:(inp&&inp.url)||'';
      if(!/^(\/api\/|https?:\/\/[^/]+\/api\/)/.test(u))return false;
      if(/\/api\/ping\b|stream|\/events\b/.test(u))return false;
      const h=opt&&opt.headers;
      if(h&&/event-stream/i.test(typeof h.get==='function'?(h.get('Accept')||''):String(h.Accept||h.accept||'')))return false;
      return true;
    }catch(e){return false}
  };
  window.fetch=function(inp,opt){
    if(!tracked(inp,opt))return orig(inp,opt);
    active++;if(active===1&&!showT)showT=setTimeout(show,300);
    const done=()=>{active=Math.max(0,active-1);if(!active)hide()};
    const p=orig(inp,opt);
    p.then(done,done);
    return p;
  };
})();

/* 3. Память прокрутки #view по разделам (в пределах сессии) */
var _dlScr;
function dlScrSave(page){try{const v=document.getElementById('view');if(!v||!page)return;(_dlScr=_dlScr||new Map()).set(page,v.scrollTop)}catch(e){}}
function dlScrRestore(page){
  try{
    const y=_dlScr&&_dlScr.get(page),v=document.getElementById('view');
    if(!v)return;
    if(!y){v.scrollTop=0;return}
    v.scrollTop=y;
    /* контент мог дорисоваться асинхронно — повторяем, пока позиция не стала достижимой */
    [120,400,900].forEach(ms=>setTimeout(()=>{if(S.page===page&&v.scrollTop<y&&v.scrollHeight>=y+v.clientHeight*.5&&Math.abs(v.scrollTop)<2)v.scrollTop=y},ms));
  }catch(e){}
}

/* 4. Горячие клавиши. Блокировка при вводе/модалках — kbBlocked() из 14a_scr_keys.js. «/», j/k/Пробел/Enter/f/v обрабатывает 14a_scr_keys.js */
const KS_GO=[['h','dash','Главная'],['p','pos','Портфель'],['v','pay','Выплаты'],['b','bonds','Облигации'],['t','tax','Налоги'],['c','calc','Калькулятор'],['s','set','Настройки']];
const KS_CODE={KeyG:'g',KeyH:'h',KeyP:'p',KeyV:'v',KeyB:'b',KeyT:'t',KeyC:'c',KeyS:'s',KeyR:'r'};
const DLK={chord:0,t:0};
function dlKey(e){return KS_CODE[e.code]||(e.key&&e.key.length===1?e.key.toLowerCase():e.key)}
function dlChordHide(){DLK.chord=0;clearTimeout(DLK.t);const c=document.getElementById('dl-chord');if(c){c.classList.remove('in');setTimeout(()=>{if(!DLK.chord)c.remove()},180)}}
function dlChordShow(){
  DLK.chord=1;clearTimeout(DLK.t);DLK.t=setTimeout(dlChordHide,1500);
  let c=document.getElementById('dl-chord');
  if(!c){
    c=document.createElement('div');c.id='dl-chord';
    c.innerHTML='<kbd>g</kbd>'+KS_GO.map(([k,,t])=>`<span><kbd>${k}</kbd>${t}</span>`).join('');
    document.body.appendChild(c);requestAnimationFrame(()=>requestAnimationFrame(()=>c.classList.add('in')));
  }
}
function dlThemeToggle(){const t=document.getElementById('thm');if(t)t.click()}
document.addEventListener('keydown',e=>{
  if(e.repeat||(typeof kbBlocked==='function'?kbBlocked(e):e.ctrlKey||e.metaKey||e.altKey))return;
  if(e.key==='Shift'||e.key==='Control'||e.key==='Alt'||e.key==='Meta')return;
  const isQ=e.key==='?'||(e.shiftKey&&e.code==='Slash');
  if(isQ){e.preventDefault();dlChordHide();ksToggle();return}
  if(e.shiftKey)return;
  const k=dlKey(e);
  if(DLK.chord){
    const hit=KS_GO.find(x=>x[0]===k);
    dlChordHide();
    if(hit&&PAGES.some(p=>p&&p[0]===hit[1])){e.preventDefault();go(hit[1])}
    else if(k==='Escape')e.preventDefault();
    return;
  }
  if(k==='g'){e.preventDefault();dlChordShow();return}
  if(k==='r'){e.preventDefault();const r=document.getElementById('refresh');if(r&&!r.disabled)r.click();return}
  if(k==='h'){e.preventDefault();setIncog(!INCOG.on);return}
  if(k==='t'){e.preventDefault();dlThemeToggle();return}
});

/* Шпаргалка («?» или пункт меню «…»): сетка групп, клавиши в <kbd> с объёмом */
const KS_GROUPS=[
  ['Навигация',[[['g','h'],'Главная'],[['g','p'],'Портфель'],[['g','v'],'Выплаты'],[['g','b'],'Облигации'],[['g','t'],'Налоги'],[['g','c'],'Калькулятор'],[['g','s'],'Настройки']]],
  ['Действия',[[['/'],'Поиск'],[['Ctrl','K'],'Палитра команд и калькулятор'],[['r'],'Обновить данные'],[['h'],'Скрыть / показать суммы'],[['t'],'Тёмная / светлая тема'],[['?'],'Эта шпаргалка'],[['Esc'],'Закрыть окно']]],
  ['Таблицы',[[['j','k'],'Строка вниз / вверх'],[['↓','↑'],'То же, когда строка выбрана'],[['Пробел'],'★ в список наблюдения'],[['Enter'],'Открыть карточку строки']]],
  ['Скринер',[[['f'],'Тип: Все → Флоатеры → Фиксы → ОФЗ'],[['v'],'Плотность: Комфорт → Компакт → Scatter']]]
];
function ksToggle(){
  const o=document.getElementById('ks-ov');
  if(o){ksClose();return}
  if(typeof kpClose==='function'&&KP.open)kpClose();
  const el=document.createElement('div');el.id='ks-ov';
  const kb=a=>a.map(x=>`<kbd>${esc(x)}</kbd>`).join('<i>затем</i>').replace(/<i>затем<\/i>/g,'<i>›</i>');
  el.innerHTML=`<div id="ks" role="dialog" aria-modal="true" aria-label="Горячие клавиши">
    <div class="ks-hd"><h2>Горячие клавиши</h2><button class="ks-x" aria-label="Закрыть">✕</button></div>
    <div class="ks-grid">${KS_GROUPS.map(([g,rows])=>`<section><h3>${esc(g)}</h3>${rows.map(([k,t])=>`<div class="ks-r"><span>${esc(t)}</span><b>${kb(k)}</b></div>`).join('')}</section>`).join('')}</div>
    <div class="ks-ft">Клавиши не срабатывают, пока вы печатаете в поле или открыто окно · Esc — закрыть</div></div>`;
  el.addEventListener('mousedown',e=>{if(e.target===el)ksClose()});
  el.querySelector('.ks-x').onclick=ksClose;
  document.body.appendChild(el);
  requestAnimationFrame(()=>requestAnimationFrame(()=>el.classList.add('in')));
}
function ksClose(){const o=document.getElementById('ks-ov');if(!o||o._c)return;o._c=1;o.classList.remove('in');setTimeout(()=>o.remove(),180)}
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&document.getElementById('ks-ov')){e.preventDefault();e.stopPropagation();ksClose()}
},true);
{const b=document.getElementById('kbhelp');if(b)b.onclick=()=>ksToggle()}
