/* Иконки: единая duotone-система на сетке 24×24. Замкнутые фигуры, помеченные D(…), получают мягкую заливку (класс ic-d, цвет — currentColor),
   поверх идёт ровный контур. Заливка усиливается у активного пункта меню и в заголовках разделов (см. 52_premium.css). */
const D=s=>s.replace(/<(rect|path|circle|ellipse)\b([^>]*?)\/>/g,'<$1 class="ic-d"$2/><$1$2/>');
const IC={
 dash:D('<rect x="3" y="3" width="8" height="10" rx="2"/>')+'<rect x="13" y="3" width="8" height="6" rx="2"/>'+D('<rect x="13" y="11" width="8" height="10" rx="2"/>')+'<rect x="3" y="15" width="8" height="6" rx="2"/>',
 ret:'<path class="ic-d" d="M3 21v-4l6-6 4 4 8-8v14z"/><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
 pos:D('<path d="M21 12A9 9 0 1 1 12 3v9z"/>')+'<path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
 bonds:D('<rect x="3" y="5" width="18" height="14" rx="2.5"/>')+'<path d="M7 9.5h6M7 13.5h4"/>'+D('<circle cx="16.5" cy="13" r="2.2"/>'),
 pay:'<path class="ic-d" d="M3 9.5h18V6.5a2.5 2.5 0 0 0-2.5-2.5h-13A2.5 2.5 0 0 0 3 6.5z"/><rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M8 2v4M16 2v4M3 9.5h18"/>'+D('<circle cx="15.5" cy="15" r="2.2"/>'),
 ops:D('<rect x="3.5" y="4" width="17" height="16" rx="2.5"/>')+'<path d="M8 9h8M8 13h8M8 17h5"/>',
 fees:D('<circle cx="12" cy="12" r="9"/>')+'<path d="M9 15l6-6"/><circle cx="9.3" cy="9.3" r=".9" fill="currentColor"/><circle cx="14.7" cy="14.7" r=".9" fill="currentColor"/>',
 tax:D('<path d="M5 3h14v18l-3.5-2-3.5 2-3.5-2L5 21z"/>')+'<path d="M9 14l6-6"/><circle cx="9.5" cy="8.5" r=".8" fill="currentColor"/><circle cx="14.5" cy="13.5" r=".8" fill="currentColor"/>',
 imp:D('<path d="M4 15v3a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-3"/>')+'<path d="M12 3v12M7 10l5 5 5-5"/>',
 cmp:D('<rect x="4" y="9" width="7" height="11" rx="1.6"/>')+D('<rect x="13" y="4" width="7" height="16" rx="1.6"/>'),
 scr:D('<circle cx="10.5" cy="10.5" r="7.5"/>')+'<path d="M21 21l-5.2-5.2M7.5 12l2-2 1.8 1.5 2.5-3"/>',
 risk:D('<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.7-7.5 9.8-4.3-1.1-7.5-5.2-7.5-9.8V6z"/>')+'<path d="M12 8.5v4.5M12 16h.01"/>',
 hm:D('<rect x="3" y="3" width="10" height="11" rx="2"/>')+'<rect x="15" y="3" width="6" height="6" rx="1.5"/>'+D('<rect x="15" y="11" width="6" height="10" rx="1.5"/>')+'<rect x="3" y="16" width="10" height="5" rx="1.5"/>',
 sig:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
 flw:D('<rect x="3.5" y="11" width="3.5" height="9" rx="1"/>')+D('<rect x="10.25" y="4" width="3.5" height="16" rx="1"/>')+D('<rect x="17" y="8" width="3.5" height="12" rx="1"/>'),
 dfl:D('<path d="M12 3l9 16H3z"/>')+'<path d="M9 15l6-5M9 10l6 5"/>',
 mon:D('<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>')+'<path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
 map:D('<circle cx="7" cy="16" r="2"/>')+D('<circle cx="12" cy="9" r="2.5"/>')+D('<circle cx="18" cy="13" r="1.8"/>')+'<path d="M3 3v18h18"/>',
 pri:D('<path d="M12 2l2.6 6.3 6.9.6-5.2 4.5 1.6 6.7L12 16.4 6.1 20.1l1.6-6.7L2.5 8.9l6.9-.6z"/>'),
 mkt:'<path d="M3 4v16h18"/><path class="ic-d" d="M7 14l4-4 3 3 5-6v10H7z"/><path d="M7 14l4-4 3 3 5-6"/>',
 reb:'<path d="M12 3v18M5 7h14M8 21h8"/>'+D('<path d="M5 7l-2 6a3 3 0 0 0 6 0z"/>')+D('<path d="M19 7l-2 6a3 3 0 0 0 6 0z"/>'),
 bench:'<path d="M3 20h18"/>'+D('<rect x="5" y="9" width="3" height="8" rx=".8"/>')+D('<rect x="10.5" y="5" width="3" height="12" rx=".8"/>')+D('<rect x="16" y="11" width="3" height="6" rx=".8"/>'),
 calc:'<rect x="4" y="2.5" width="16" height="19" rx="2.5"/>'+D('<rect x="7.5" y="5.5" width="9" height="4" rx="1"/>')+'<path d="M8 13h.01M12 13h.01M16 13h.01M8 16.5h.01M12 16.5h.01M16 16.5h.01"/>',
 off:'<path d="M4 12h12M12 7l5 5-5 5"/><path d="M20 4v16"/>',
 lad:D('<rect x="3" y="15" width="5" height="6" rx="1.2"/>')+D('<rect x="9.5" y="10" width="5" height="11" rx="1.2"/>')+D('<rect x="16" y="4" width="5" height="17" rx="1.2"/>'),
 iss:D('<path d="M4 21V8l8-5 8 5v13z"/>')+'<path d="M9 21v-6h6v6M8 11h.01M12 11h.01M16 11h.01"/>',
 cal:'<path class="ic-d" d="M3 9.5h18V6.5a2.5 2.5 0 0 0-2.5-2.5h-13A2.5 2.5 0 0 0 3 6.5z"/><rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M8 2v4M16 2v4M3 9.5h18"/><path d="M12 13.5l1.1 2.2 2.4.35-1.75 1.7.4 2.4-2.15-1.15-2.15 1.15.4-2.4-1.75-1.7 2.4-.35z"/>',
 watch:D('<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/>')+'<circle cx="12" cy="12" r="3"/>',
 kb:D('<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/>')+'<path d="M4 21V5M9 8h6M9 12h4"/>',
 fng:D('<path d="M4 17a8 8 0 0 1 16 0z"/>')+'<path d="M12 17l4-5"/><circle cx="12" cy="17" r="1.2"/>',
 set:D('<circle cx="12" cy="12" r="3.5"/>')+'<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'};
/* единый рендерер: класс ic включает duotone-слой и анимацию, штрих 1.7, скруглённые концы */
const svgI=(p,sw=1.7)=>`<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const PAGES=[['dash','Обзор'],['ret','Доходность'],['bench','Сравнение с рынком'],['pos','Позиции'],['bonds','Облигации'],['pay','Выплаты'],['off','Оферты'],['ops','Операции'],['fees','Комиссии'],['tax','Налоги'],['reb','Ребалансировка'],['calc','Калькулятор'],['lad','Лесенка облигаций'],['mkt','Ставки'],['scr','Скринер облигаций'],['cmp','Сравнение облигаций'],['map','Карта рынка'],['hm','Тепловая карта'],['sig','Сигналы'],['risk','Риски и сценарии'],['mon','Мониторинг'],['watch','Наблюдение'],['iss','Эмитенты'],['dfl','Техдефолты'],['flw','Кто покупает'],['pri','Первичка'],['fng','Страх и жадность'],['cal','Календарь событий'],null,['kb','База знаний'],['imp','Импорт отчётов'],['set','Настройки']];
/* группы меню: ключи страниц остаются прежними, PAGES — плоский список для поиска названий */
const NAV_GROUPS=[['Портфель',['dash','ret','bench','pos','bonds','pay','off','ops','fees']],['Учёт и планы',['tax','reb','calc','lad']],
  ['Рынок',['mkt','fng','scr','cmp','map','hm','sig','pri','cal','dfl','flw']],['Риски и контроль',['risk','mon','watch','iss']]];
/* Регистрация экрана из отдельного файла (не трогая общие списки): меню, иконка, Pro, отрисовка и привязка событий.
   regPage('rot',{title:'…',group:'Рынок',icon:'<path …/>',render:pRot,bind:bindRot,pro:true}) */
const PAGE_EXT={};
function regPage(id,o){
  PAGE_EXT[id]=o;PAGES.push([id,o.title]);if(o.icon)IC[id]=o.icon;
  if(o.group){let g=NAV_GROUPS.find(x=>x[0]===o.group);if(!g){g=[o.group,[]];NAV_GROUPS.push(g)}g[1].push(id)}
  if(o.pro&&typeof PRO_PAGES!=='undefined'&&!PRO_PAGES.includes(id))PRO_PAGES.push(id);
}
const NAV_FIXED=['imp','kb','set'],NAV_PINNED=['dash','set'];
function lsJson(k,d){try{const v=JSON.parse(localStorage.getItem(k));return v==null?d:v}catch(e){return d}}
function lsSet(k,v){try{localStorage.setItem(k,v)}catch(e){}}
const PERIODS=[['1m','Месяц'],['3m','3 мес'],['ytd','С начала года'],['12m','Год'],['py','Прошлый год'],['all','Всё время']];
const PERIOD_PAGES=['dash','ret','bench','ops','fees'];
function lsGet(k){try{return localStorage.getItem(k)}catch(e){return null}}
let st={};try{st=JSON.parse(lsGet('ta_state')||'{}')||{}}catch(e){}
const S={navHidden:lsJson('ta_nav_hidden',[]),navShut:lsJson('ta_nav_shut',{}),page:st.page||'dash',period:st.period||'all',account:st.account||'all',hideEmpty:st.hideEmpty!==false,
  data:null,bonds:null,hist:null,cfg:null,loading:false,err:null,accounts:[],
  sort:{k:'value_rub',d:-1},bsort:{k:'value_rub',d:-1},posType:'',opsN:200,opsQ:'',opsK:'',charts:[],imp:null};
function persist(){try{localStorage.setItem('ta_state',JSON.stringify({page:S.page,period:S.period,account:S.account,hideEmpty:S.hideEmpty}))}catch(e){}}

async function api(path,opt){
  let r;
  try{r=await fetch(path,opt)}
  catch(e){throw new Error('Программа не отвечает: похоже, её локальный сервер остановлен. Закройте окно программы и откройте её снова.')}
  let j={};
  try{j=await r.json()}catch(e){}
  if(!r.ok)throw new Error(j.error||('HTTP '+r.status));
  if(j&&j.stale&&/^\/api\/(bonds|history)\?/.test(path))staleRefresh(path,j);
  return j;
}
/* Сервер отдал прошлый сохранённый результат (stale) и пересчитывает его в фоне: перезапрашиваем, пока не придёт свежий */
const _stl={};
function staleRefresh(path,first){
  const key=path.split('?')[0],isB=key==='/api/bonds',acc=S.account;
  if(_stl[key])return;
  let n=0;_stl[key]=1;
  const tick=async()=>{
    n++;
    try{
      const j=await fetch(path.replace(/&?force=1/,'')).then(r=>r.json());
      if(S.account!==acc){delete _stl[key];return}
      if(j&&j.stale&&n<40){setTimeout(tick,4000);return}
      delete _stl[key];
      if(!j||j.error)return;
      if(isB){S.bonds=j;if(['dash','bonds','pay'].includes(S.page))renderSoon()}
      else{S.hist=j;if(['dash','ret'].includes(S.page))renderSoon()}
    }catch(e){delete _stl[key]}
  };
  setTimeout(tick,4000);
}
const post=(p,b)=>api(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
/* «Показано один раз» (тур, подсказки, чек-лист): хранится в конфиге программы (ui_seen), localStorage — только запасной вариант:
   в окне pywebview localStorage между запусками не сохраняется */
function uiGet(k){const u=S.cfg&&S.cfg.ui_seen;if(u&&u[k]!=null)return u[k];const v=lsGet('ui_'+k);if(v==null)return null;try{return JSON.parse(v)}catch(e){return v}}
function uiSet(k,v){
  lsSet('ui_'+k,JSON.stringify(v));
  if(S.cfg){S.cfg.ui_seen=Object.assign({},S.cfg.ui_seen);S.cfg.ui_seen[k]=v}
  const b={};b[k]=v;post('/api/config',{ui_seen:b}).catch(()=>{});
}

