/* ── Motion engine (FE-14): числовой тикер, плавное переключение разделов, пульс рынка ── */
function _tickNum(s){const v=parseFloat(String(s).replace(/[−–]/g,'-').replace(/\s| /g,'').replace(',','.').replace(/[^0-9.\-]/g,''));return isNaN(v)?null:v}
/* Анимирует смену числа в el: старый текст уходит вверх/вниз, новый въезжает, краткая подсветка --pos/--neg. dir: 1 / -1 / undefined (по значению) */
function tickNum(el,newText,dir){
  if(!el)return;
  const old=el.textContent;
  if(old===newText)return;
  if(dir==null){const a=_tickNum(old),b=_tickNum(newText);dir=a!=null&&b!=null&&a!==b?(b>a?1:-1):0}
  el.querySelectorAll('.tick-old').forEach(x=>x.remove());
  el.textContent=newText;
  if(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  el.classList.add('tick');
  const g=document.createElement('span');g.className='tick-old';g.setAttribute('aria-hidden','true');g.textContent=old;
  el.appendChild(g);
  el.classList.remove('tick-in','tick-up','tick-dn');void el.offsetWidth;
  el.classList.add('tick-in');if(dir>0)el.classList.add('tick-up');else if(dir<0)el.classList.add('tick-dn');
  setTimeout(()=>{g.remove();el.classList.remove('tick-in','tick-up','tick-dn')},700);
}
window.tickNum=tickNum;

/* Диф после рендера: [data-tick="ключ"] помнит последний текст; на первом рендере не анимируем */
const _tickMem=new Map();
function tickScan(root){
  (root||document).querySelectorAll('[data-tick]').forEach(el=>{
    const k=el.dataset.tick,now=el.textContent;
    if(!_tickMem.has(k)){_tickMem.set(k,now);return}
    const prev=_tickMem.get(k);
    if(prev===now)return;
    _tickMem.set(k,now);
    el.textContent=prev;tickNum(el,now);
  });
}
{
  const _rn=renderNow;
  renderNow=function(){const r=_rn.apply(this,arguments);try{tickScan(document.getElementById('view'))}catch(e){}return r};
}

/* Плавное появление раздела — только при смене страницы */
{
  const _go=go;
  go=function(p){
    const same=p===S.page;
    const r=_go.apply(this,arguments);
    if(!same){const v=document.getElementById('view');if(v){v.classList.remove('vsw');void v.offsetWidth;v.classList.add('vsw');setTimeout(()=>v.classList.remove('vsw'),400)}}
    return r;
  };
}

/* Пульс рынка: по московскому времени (UTC+3), расписание фондового рынка MOEX, без учёта праздников */
function mktPhase(now){
  const d=new Date((now||Date.now())+new Date().getTimezoneOffset()*60000+3*3600000);
  const dow=d.getDay(),m=d.getHours()*60+d.getMinutes();
  const off={k:'off',t:'Сессия закрыта'};
  if(dow===0||dow===6)return off;
  if(m>=410&&m<590)return{k:'ses',t:'Утренняя сессия'};      /* 06:50–09:50 */
  if(m>=590&&m<600)return{k:'auc',t:'Аукцион'};              /* 09:50–10:00 */
  if(m>=600&&m<1120)return{k:'on',t:'Идут торги'};           /* 10:00–18:40 */
  if(m>=1120&&m<1130)return{k:'auc',t:'Аукцион'};           /* 18:40–18:50 */
  if(m>=1145&&m<1430)return{k:'ses',t:'Вечерняя сессия'};    /* 19:05–23:50 */
  return off;
}
function mktPulseUpd(){
  let el=document.getElementById('mkt-pulse');
  if(!el){
    const u=document.getElementById('upd');if(!u||!u.parentNode)return;
    el=document.createElement('span');el.id='mkt-pulse';el.className='mkt-pulse';
    el.innerHTML='<i class="mp-dot"></i><span class="mp-tx"></span>';
    u.parentNode.insertBefore(el,u);
  }
  const ph=mktPhase();
  el.className='mkt-pulse '+ph.k;el.title='Московская биржа, фондовый рынок: '+ph.t.toLowerCase()+' (по расписанию, без учёта праздников)';
  el.querySelector('.mp-tx').textContent=ph.t;
}
mktPulseUpd();setInterval(mktPulseUpd,60000);
