const IC={
 dash:'<path d="M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z"/>',
 ret:'<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
 pos:'<path d="M21 12A9 9 0 1 1 12 3v9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
 bonds:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h6M7 13h10M7 16h4"/>',
 pay:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18M8 14h2M14 14h2M8 17h2"/>',
 ops:'<path d="M4 6h16M4 12h16M4 18h10"/>',
 fees:'<path d="M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
 tax:'<path d="M9 14l6-6M9.5 8.5h.01M14.5 13.5h.01"/><path d="M5 3h14v18l-3.5-2-3.5 2-3.5-2L5 21z"/>',
 imp:'<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
 scr:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M8 11h6"/>',
 risk:'<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
 sig:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
 mon:'<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/>',
 map:'<circle cx="7" cy="16" r="2"/><circle cx="12" cy="9" r="2.5"/><circle cx="18" cy="13" r="1.6"/><path d="M3 3v18h18"/>',
 pri:'<path d="M12 2l2.6 6.3 6.9.6-5.2 4.5 1.6 6.7L12 16.4 6.1 20.1l1.6-6.7L2.5 8.9l6.9-.6z"/>',
 mkt:'<path d="M3 4v16h18"/><path d="M7 14l4-4 3 3 5-6"/>',
 reb:'<path d="M12 3v18M5 7h14M5 7l-2 6a3 3 0 0 0 6 0zM19 7l-2 6a3 3 0 0 0 6 0z"/>',
 bench:'<path d="M3 20h18"/><path d="M6 16V9M11 16V5M16 16v-5M20 16v-8"/>',
 calc:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2M12 11h2M16 11h0M8 15h2M12 15h2M8 18h2M12 18h4"/>',
 off:'<path d="M4 12h12M12 7l5 5-5 5"/><path d="M20 4v16"/>',
 lad:'<path d="M7 3v18M17 3v18M7 7h10M7 12h10M7 17h10"/>',
 iss:'<path d="M4 21V8l8-5 8 5v13"/><path d="M9 21v-6h6v6M8 11h.01M12 11h.01M16 11h.01"/>',
 cal:'<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/><path d="M12 14l1.2 2.4 2.6.4-1.9 1.8.5 2.6-2.4-1.3-2.4 1.3.5-2.6-1.9-1.8 2.6-.4z"/>',
 watch:'<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
 set:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>'};
const svgI=(p,sw=1.8)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const PAGES=[['dash','Обзор'],['ret','Доходность'],['bench','Сравнение с рынком'],['pos','Позиции'],['bonds','Облигации'],['pay','Выплаты'],['off','Оферты'],['ops','Операции'],['fees','Комиссии'],['tax','Налоги'],['reb','Ребалансировка'],['calc','Калькулятор'],['lad','Лесенка облигаций'],['mkt','Ставки'],['scr','Скринер облигаций'],['map','Карта рынка'],['sig','Сигналы'],['risk','Риски и сценарии'],['mon','Мониторинг'],['pri','Первичка'],null,['imp','Импорт отчётов'],['set','Настройки']];
const PERIODS=[['1m','Месяц'],['3m','3 мес'],['ytd','С начала года'],['12m','Год'],['py','Прошлый год'],['all','Всё время']];
const PERIOD_PAGES=['dash','ret','bench','ops','fees'];
function lsGet(k){try{return localStorage.getItem(k)}catch(e){return null}}
let st={};try{st=JSON.parse(lsGet('ta_state')||'{}')||{}}catch(e){}
const S={page:st.page||'dash',period:st.period||'all',account:st.account||'all',hideEmpty:st.hideEmpty!==false,
  data:null,bonds:null,hist:null,cfg:null,loading:false,err:null,accounts:[],
  sort:{k:'value_rub',d:-1},bsort:{k:'value_rub',d:-1},posType:'',opsN:200,opsQ:'',opsK:'',charts:[],imp:null};
function persist(){try{localStorage.setItem('ta_state',JSON.stringify({page:S.page,period:S.period,account:S.account,hideEmpty:S.hideEmpty}))}catch(e){}}

async function api(path,opt){
  const r=await fetch(path,opt);let j={};
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
      if(isB){S.bonds=j;if(['dash','bonds','pay'].includes(S.page))render()}
      else{S.hist=j;if(['dash','ret'].includes(S.page))render()}
    }catch(e){delete _stl[key]}
  };
  setTimeout(tick,4000);
}
const post=(p,b)=>api(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});

