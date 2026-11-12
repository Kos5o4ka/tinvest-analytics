/* ── Календарь событий ── */
const CAL_KINDS=[['cbr','Заседания ЦБ','#ffdd2d',['cbr']],['coupon','Купоны','#19a070',['coupon']],['redemption','Погашения','#d95926',['redemption']],
  ['amort','Амортизации','#c98500',['amort']],['dividend','Дивиденды','#9085e9',['dividend']],['offer','Оферты','#e66767',['offer']],
  ['primary','Размещения','#3987e5',['primary']],['watch','Наблюдение','#8d94a3',['w_coupon','w_redemption','w_offer']],['other','Прочее','#8d94a3',[]]];
const CAL_NAME={cbr:'Заседание ЦБ',coupon:'Купон',redemption:'Погашение',amort:'Амортизация',dividend:'Дивиденд',offer:'Оферта',primary:'Размещение',
  w_coupon:'Купон · наблюдение',w_redemption:'Погашение · наблюдение',w_offer:'Оферта · наблюдение'};
const CAL_ALIAS={amortization:'amort',maturity:'redemption',repayment:'redemption'};
const calKind=k=>CAL_ALIAS[k]||k;
/* неизвестный вид уходит в группу «other» (чип «Прочее»), чтобы фильтры его не пропускали */
const calGroup=k=>{k=calKind(k);const g=CAL_KINDS.find(g=>g[3].includes(k));return g?g[0]:(String(k).startsWith('w_')?'watch':'other')};
const calCol=k=>(CAL_KINDS.find(g=>g[0]===calGroup(k))||[])[2]||'#8d94a3';
const calName=k=>CAL_NAME[calKind(k)]||'Событие';
const calVis=e=>!S.cal.off[calGroup(e.kind)];
(function(){const n=new Date();S.cal={y:n.getFullYear(),m:n.getMonth(),off:{},cache:{},sel:null,view:'month'}})();
try{const v=JSON.parse(localStorage.getItem('cal_off')||'null');if(v&&typeof v==='object')S.cal.off=v}catch(e){}
try{const v=localStorage.getItem('cal_view');if(v==='year'||v==='month')S.cal.view=v}catch(e){}
const calYm=()=>S.cal.y+'-'+String(S.cal.m+1).padStart(2,'0');
const calYear=()=>S.cal.view==='year';
const calKey=()=>S.account+'|'+(calYear()?'Y'+S.cal.y:calYm());
function calRange(){
  const y=S.cal.y,m=S.cal.m,p=n=>String(n).padStart(2,'0');
  if(calYear())return[`${y}-01-01`,`${y}-12-31`];
  const last=new Date(y,m+1,0).getDate();
  return[`${y}-${p(m+1)}-01`,`${y}-${p(m+1)}-${p(last)}`];
}
function loadCal(){
  const key=calKey(),c=S.cal.cache[key];
  if(c&&(c.loading||c.data||c.error))return;
  const [from,to]=calRange();
  S.cal.cache[key]={loading:true};
  api('/api/events?'+new URLSearchParams({account:S.account,from,to})).then(d=>{S.cal.cache[key]={data:d};if(S.page==='cal')renderSoon()})
   .catch(e=>{S.cal.cache[key]={error:e.message};if(S.page==='cal')renderSoon()});
}
const calP2=n=>String(n).padStart(2,'0');
const CAL_BADGE={PUT:'of-t-put','CALL':'of-t-call'};
function calBadge(e){return e.badge?` <span class="tag ${CAL_BADGE[e.badge]||'of-t-unk'} cal-bd">${esc(e.badge)}</span>`:''}
function calMoney(e){return e.amount!=null?M(e.amount,'rub',2):''}
function calYearHtml(d,today){
  const y=S.cal.y,by={};
  (d.events||[]).filter(calVis).forEach(e=>(by[e.date]=by[e.date]||[]).push(e));
  let h='';
  for(let m=0;m<12;m++){
    const lead=(new Date(y,m,1).getDay()+6)%7,days=new Date(y,m+1,0).getDate();
    let cells='<i class="cy-h">Пн</i><i class="cy-h">Вт</i><i class="cy-h">Ср</i><i class="cy-h">Чт</i><i class="cy-h">Пт</i><i class="cy-h">Сб</i><i class="cy-h">Вс</i>';
    for(let i=0;i<lead;i++)cells+='<span></span>';
    let cnt=0;
    for(let dd=1;dd<=days;dd++){
      const ds=`${y}-${calP2(m+1)}-${calP2(dd)}`,l=by[ds]||[];cnt+=l.length;
      const gs=[...new Set(l.map(e=>calGroup(e.kind)))].slice(0,3);
      const tip=l.slice(0,5).map(e=>e.title+' — '+(e.label||calName(e.kind))).join('\n')+(l.length>5?`\n…и ещё ${l.length-5}`:'');
      cells+=`<b class="cy-c ${ds===today?'today':''} ${l.length?'has':''}"${l.length?` data-day="${ds}" title="${esc(dlabel(ds)+'\n'+tip)}"`:''}>${dd}${gs.length?`<s>${gs.map(k=>`<i style="background:${(CAL_KINDS.find(g=>g[0]===k)||[])[2]||'#8d94a3'}"></i>`).join('')}</s>`:''}</b>`;
    }
    h+=`<div class="cy-m"><button class="cy-t" data-m="${m}">${MONF[m]}${cnt?` <small>${cnt}</small>`:''}</button><div class="cy-g">${cells}</div></div>`;
  }
  return`<div class="cy">${h}</div>`;
}
function calKpis(evs,lbl){
  const sum={};evs.forEach(e=>{const k=calKind(e.kind);if(e.amount!=null&&['coupon','redemption','amort','dividend'].includes(k))sum[k]=(sum[k]||0)+e.amount});
  const total=Object.values(sum).reduce((a,b)=>a+b,0),n=k=>evs.filter(e=>calKind(e.kind)===k).length;
  return`<div class="g g4">${kpi('Событий '+(calYear()?'в году':'в месяце'),evs.length,lbl)}${kpi('Выплаты по портфелю',total?M(total,'rub',0):'—','купоны, погашения, амортизации, дивиденды')}
    ${kpi('Заседаний ЦБ',n('cbr'),'по ключевой ставке')}${kpi('Размещений',n('primary'),'начало по объявлениям Мосбиржи')}</div>`;
}
function pCal(){
  loadCal();
  const key=calKey(),c=S.cal.cache[key]||{loading:true},yr=calYear();
  const y=S.cal.y,m=S.cal.m,today=new Date().toISOString().slice(0,10);
  const nav=`<div class="row cal-nav"><button class="btn ghost" id="cal-prev" title="${yr?'Предыдущий год':'Предыдущий месяц'}">‹</button><b class="cal-title">${yr?y:MONF[m]+' '+y}</b><button class="btn ghost" id="cal-next" title="${yr?'Следующий год':'Следующий месяц'}">›</button>
    <button class="btn ghost" id="cal-today">Сегодня</button><span class="cal-vw"><button id="cal-vm" class="${yr?'':'on'}">Месяц</button><button id="cal-vy" class="${yr?'on':''}">Год</button></span><a class="btn" id="cal-ics" href="/api/events.ics?${new URLSearchParams({account:S.account})}" download="tinvest_events.ics" style="margin-left:auto">Скачать .ics</a></div>`;
  const hasOther=c.data&&(c.data.events||[]).some(e=>calGroup(e.kind)==='other');
  const chips=`<div class="cal-chips">${CAL_KINDS.filter(g=>g[0]!=='other'||hasOther).map(g=>`<button class="cal-chip ${S.cal.off[g[0]]?'':'on'}" data-k="${g[0]}"><i style="background:${g[2]}"></i>${g[1]}</button>`).join('')}</div>`;
  const help=`<p class="note" style="margin:4px 4px 12px">Кнопка «Скачать .ics» сохраняет файл с событиями на год вперёд (все типы, без учёта фильтров). Его можно импортировать в Календарь Google (Настройки → Импорт) или открыть в Календаре Apple двойным щелчком. Файл формируется на вашем компьютере и никуда не отправляется.</p>`;
  if(c.loading)return`<div class="card">${nav}${waitBox('Собираю события: заседания ЦБ, выплаты, оферты, размещения…')}</div>`;
  if(c.error)return`<div class="card">${nav}<div class="msg err">${esc(c.error)} <button class="btn ghost" id="cal-r">Повторить</button></div></div>`;
  const d=c.data,evs=(d.events||[]).filter(calVis);
  if(yr){
    const warn=(d.warnings||[]).map(w=>`<div class="msg err" style="margin:8px 0">${esc(w)}</div>`).join('');
    return`${calKpis(evs,'за '+y+' год')}<div class="card" style="margin-top:16px">${nav}${chips}${warn}${calYearHtml(d,today)}<p class="note" style="margin:10px 4px 0">Точки — типы событий в этот день (до трёх). Нажмите на день, чтобы открыть его в месячном виде, или на название месяца.</p></div>${help}`;
  }
  const by={};evs.forEach(e=>(by[e.date]=by[e.date]||[]).push(e));
  const first=new Date(y,m,1),lead=(first.getDay()+6)%7,days=new Date(y,m+1,0).getDate();
  let cells='';
  for(let i=0;i<lead;i++)cells+='<div class="cal-c off"></div>';
  for(let dd=1;dd<=days;dd++){
    const ds=`${y}-${calP2(m+1)}-${calP2(dd)}`,l=by[ds]||[];
    const kinds=[...new Set(l.map(e=>calGroup(e.kind)))];
    cells+=`<div class="cal-c ${ds===today?'today':''} ${l.length?'has':''} ${S.cal.sel===ds?'sel':''}" data-day="${ds}"><span class="cal-d">${dd}</span>
      ${l.length?`<span class="cal-dots">${kinds.slice(0,6).map(k=>`<i style="background:${(CAL_KINDS.find(g=>g[0]===k)||[])[2]||'#8d94a3'}"></i>`).join('')}</span><span class="cal-n">${l.length}</span>`:''}</div>`;
  }
  const grid=`<div class="cal-grid"><div class="cal-h">Пн</div><div class="cal-h">Вт</div><div class="cal-h">Ср</div><div class="cal-h">Чт</div><div class="cal-h">Пт</div><div class="cal-h">Сб</div><div class="cal-h">Вс</div>${cells}</div>`;
  const ds=Object.keys(by).filter(x=>!S.cal.sel||x===S.cal.sel).sort();
  const list=ds.length?ds.map(dt=>`<div class="cal-day" id="cal-d-${dt}"><div class="cal-dh"><b>${dlabel(dt)}</b><span class="mu">${['вс','пн','вт','ср','чт','пт','сб'][new Date(dt+'T00:00:00').getDay()]}${dt===today?' · сегодня':''}</span></div>
    ${by[dt].map(e=>`<div class="cal-ev"${e.isin?` data-isin="${esc(e.isin)}" title="Открыть карточку выпуска"`:''}><i style="background:${calCol(e.kind)}"></i><div class="cal-et"><b>${esc(e.title)}${calBadge(e)}</b><small class="mu">${esc(e.label||calName(e.kind))}${e.note&&!e.label?' · '+esc(e.note):''}</small>${e.label&&e.note?`<small class="mu">${esc(e.note)}</small>`:''}</div>
      <span class="num cal-am">${calMoney(e)}</span></div>`).join('')}</div>`).join(''):'<div class="empty" style="padding:24px">В этом месяце событий нет'+(Object.keys(S.cal.off).some(k=>S.cal.off[k])?' (часть типов скрыта фильтрами)':'')+'</div>';
  const warn=(d.warnings||[]).map(w=>`<div class="msg err" style="margin:8px 0">${esc(w)}</div>`).join('');
  return`${calKpis(evs,MONF[m].toLowerCase()+' '+y)}
  <div class="card" style="margin-top:16px">${nav}${chips}${warn}${grid}${S.cal.sel?`<div class="row" style="margin:10px 4px 0"><span class="mu">Показан день ${dlabel(S.cal.sel)}</span><button class="btn ghost" id="cal-all">Показать весь месяц</button></div>`:''}</div>
  <div class="card" style="margin-top:16px"><h2>События ${S.cal.sel?'за день':'месяца'}</h2>${list}</div>${help}
  <p class="note">Источники: сайт Банка России (календарь заседаний), Московская биржа (купоны, оферты, размещения), ваш портфель${(d.sources||{}).watch!=null?', список наблюдения':''}. Даты выплат, размеры будущих купонов и оферт могут измениться — сверяйтесь с решением эмитента. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function bindCal(){
  const go=n=>{if(calYear())S.cal.y+=n;else{const d=new Date(S.cal.y,S.cal.m+n,1);S.cal.y=d.getFullYear();S.cal.m=d.getMonth()}S.cal.sel=null;render()};
  const view=(v,sel)=>{S.cal.view=v;S.cal.sel=sel||null;try{localStorage.setItem('cal_view',v)}catch(x){}render()};
  const b=(id,f)=>{const e=$(id);if(e)e.onclick=f};
  b('#cal-prev',()=>go(-1));b('#cal-next',()=>go(1));
  b('#cal-today',()=>{const n=new Date();S.cal.y=n.getFullYear();S.cal.m=n.getMonth();S.cal.sel=null;render()});
  b('#cal-vm',()=>view('month'));b('#cal-vy',()=>view('year'));
  b('#cal-r',()=>{delete S.cal.cache[calKey()];render()});
  document.querySelectorAll('.cy-t').forEach(e=>e.onclick=()=>{S.cal.m=+e.dataset.m;view('month')});
  document.querySelectorAll('.cy-c[data-day]').forEach(e=>e.onclick=()=>{const d=e.dataset.day;S.cal.m=+d.slice(5,7)-1;view('month',d)});
  b('#cal-all',()=>{S.cal.sel=null;render()});
  document.querySelectorAll('.cal-chip').forEach(e=>e.onclick=()=>{const k=e.dataset.k;S.cal.off[k]=!S.cal.off[k];try{localStorage.setItem('cal_off',JSON.stringify(S.cal.off))}catch(x){}render()});
  document.querySelectorAll('.cal-c[data-day]').forEach(e=>e.onclick=()=>{const d=e.dataset.day;S.cal.sel=S.cal.sel===d?null:d;render()});
}
