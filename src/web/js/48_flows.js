/* ── «Кто покупает»: потоки денег по классам и секторам, крупные сделки, всплески объёма, стакан (сервер данных, /api/flows*) ── */
S.flw={period:'1h',tab:'flow',data:null,key:null,loading:false,large:{cls:'',min:0,data:null,key:null,loading:false},
  spikes:{data:null,loading:false,key:null},book:{secid:'SBER',depth:20,data:null,err:'',busy:false,list:null,inst:null}};
const FLW_CLS={share:'Акции',bond:'Облигации',fund:'Фонды'};
const FLW_SRC={tinvest:'T-Invest, реальное время',iss:'Мосбиржа, задержка 15 мин'};
let _flwTimer=null;
const flwMsk=(ts,full)=>{try{return new Date(ts*1000).toLocaleString('ru-RU',Object.assign({timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit'},full?{second:'2-digit'}:{day:'2-digit',month:'2-digit'}))}catch(e){return''}};
const flwRub=n=>bad(n)?'—':short(n)+' ₽';
const flwNet=n=>`<span class="${n>0?'pos':n<0?'neg':'mu'}">${n>0?'+':''}${flwRub(n)}</span>`;
const flwSide=s=>s==='buy'?'<span class="flw-b buy">покупка</span>':'<span class="flw-b sell">продажа</span>';
const flwPx=p=>bad(p)?'—':(+p).toLocaleString('ru-RU',{maximumFractionDigits:4});
function flwSrcLine(d){
  if(!d||!d.source)return'';
  return`<span class="flw-src ${d.source==='tinvest'?'live':'delay'}" title="Источник сделок">${FLW_SRC[d.source]||esc(d.source)}</span>`;
}
function flwOpen(secid,cls,isin){
  if((cls==='share'||cls==='fund')&&typeof openStock==='function')openStock(secid);
  else if(cls==='bond'&&isin&&typeof openBond==='function')openBond(isin);
  else{S.flw.tab='book';S.flw.book.secid=secid;S.flw.book.data=null;render()}
}
function flwEmpty(d){
  return`<div class="empty" style="padding:28px 12px">${d&&d.configured===false?'Сервер данных недоступен: потоки денег считаются на сервере. Попробуйте позже или проверьте ключ в «Настройках».':'Данных пока нет: сборщик ещё накапливает сделки (в нерабочее время биржи данных нет).'}</div>`;
}
/* ── потоки ── */
function loadFlw(force){
  const D=S.flw,key=D.period;if(D.loading)return;D.loading=true;
  api('/api/flows?'+new URLSearchParams({period:D.period,force:force?1:''})).then(j=>{D.data=j;D.key=key}).catch(e=>{D.data={error:e.message||String(e)};D.key=key})
    .then(()=>{D.loading=false;if(S.page==='flw'&&S.flw.tab==='flow')render()});
}
function flwBars(rows,keyF,nameF){
  const mx=Math.max(1,...rows.map(r=>Math.abs(r.net)));
  return rows.map(r=>`<div class="flw-sr"><span class="flw-sn">${esc(nameF(r))}</span><div class="flw-sb"><i class="${r.net>=0?'p':'n'}" style="width:${(Math.abs(r.net)/mx*100).toFixed(1)}%"></i></div><span class="flw-sv">${flwNet(r.net)}</span></div>`).join('');
}
function flwTop(rows,title){
  if(!rows||!rows.length)return`<div class="card"><h2>${title}</h2><div class="mu" style="padding:14px 0">Нет данных</div></div>`;
  return`<div class="card"><h2>${title}</h2><div class="tbl"><table class="flw-t"><thead><tr><th class="l">Бумага</th><th>Покупки</th><th>Продажи</th><th>Баланс</th></tr></thead><tbody>`
    +rows.map(r=>`<tr data-secid="${esc(r.secid)}" data-cls="${esc(r.cls)}" data-isin="${esc(r.isin||'')}" class="flw-row"><td class="l"><b>${esc(r.name||r.secid)}</b> <small class="mu">${esc(r.name?r.secid:'')}</small></td><td class="num">${flwRub(r.buy)}</td><td class="num">${flwRub(r.sell)}</td><td class="num">${flwNet(r.net)}</td></tr>`).join('')+`</tbody></table></div></div>`;
}
function flwTabFlow(){
  const D=S.flw;
  if(D.key!==D.period&&!D.loading){D.data=null;loadFlw()}
  if(!D.data||D.key!==D.period)return waitBox('Загружаю потоки…');
  const d=D.data;
  if(d.error)return`<div class="msg err">${esc(d.error)}</div>`;
  if(d.configured===false||d.empty)return flwEmpty(d);
  const cls=['share','bond','fund'].map(k=>d.by_class.find(x=>x.cls===k)||{cls:k,buy:0,sell:0,net:0,n:0});
  return`<div class="flw-meta">${flwSrcLine(d)}<span class="mu">данные на ${flwMsk(d.asof)} МСК</span><button class="btn" id="flw-ref">Обновить</button></div>
  <div class="flw-cards">${cls.map(c=>{const t=c.buy+c.sell||1;return`<div class="card flw-c"><h2>${FLW_CLS[c.cls]}<span class="sp">${c.n||0} сделок</span></h2>
    <div class="flw-big">${flwNet(c.net)}</div>
    <div class="flw-bar"><i class="p" style="width:${(c.buy/t*100).toFixed(1)}%"></i><i class="n" style="width:${(c.sell/t*100).toFixed(1)}%"></i></div>
    <div class="flw-leg"><span class="pos">покупки ${flwRub(c.buy)}</span><span class="neg">продажи ${flwRub(c.sell)}</span></div></div>`}).join('')}</div>
  <div class="card" style="margin-top:14px"><h2>По секторам<span class="sp">баланс покупок и продаж</span></h2>${flwBars(d.by_sector.slice(0,14),'sector',r=>r.sector)}</div>
  <div class="flw-two" style="margin-top:14px">${flwTop(d.top_buy,'Чаще покупают')}${flwTop(d.top_sell,'Чаще продают')}</div>
  <p class="note" style="margin-top:10px">Сторона сделки — по данным биржи (кто был инициатором). Баланс = покупки − продажи за период; это поток сделок, а не прогноз цены. Не является индивидуальной инвестиционной рекомендацией.</p>`;
}
/* ── крупные сделки ── */
function loadFlwLarge(force){
  const L=S.flw.large,key=L.cls+'|'+L.min;if(L.loading)return;L.loading=true;
  api('/api/large_trades?'+new URLSearchParams({class:L.cls,min:L.min||'',force:force?1:''})).then(j=>{L.data=j;L.key=key}).catch(e=>{L.data={error:e.message||String(e),rows:[]};L.key=key})
    .then(()=>{L.loading=false;if(S.page==='flw'&&S.flw.tab==='large')render()});
}
function flwTabLarge(){
  const L=S.flw.large,key=L.cls+'|'+L.min;
  if(L.key!==key&&!L.loading){L.data=null;loadFlwLarge()}
  let h=`<div class="flw-bar2"><div class="seg" id="flw-cls">${[['','Все'],['share','Акции'],['bond','Облигации'],['fund','Фонды']].map(([k,t])=>`<button data-c="${k}" class="${L.cls===k?'on':''}">${t}</button>`).join('')}</div>
    <label class="flw-min">от <select id="flw-min">${[[0,'любая сумма'],[5e6,'5 млн ₽'],[10e6,'10 млн ₽'],[50e6,'50 млн ₽'],[100e6,'100 млн ₽']].map(([v,t])=>`<option value="${v}"${+L.min===v?' selected':''}>${t}</option>`).join('')}</select></label></div>`;
  if(!L.data||L.key!==key)return h+waitBox('Загружаю сделки…');
  if(L.data.error)return h+`<div class="msg err">${esc(L.data.error)}</div>`;
  const rows=L.data.rows||[];
  if(!rows.length)return h+flwEmpty(L.data);
  return h+`<div class="tbl"><table class="flw-t"><thead><tr><th class="l">Время (МСК)</th><th class="l">Бумага</th><th class="l">Сторона</th><th>Цена</th><th>Кол-во</th><th>Сумма</th><th class="l">Источник</th></tr></thead><tbody>`
    +rows.map(r=>`<tr class="flw-row" data-secid="${esc(r.secid)}" data-cls="${esc(r.cls)}" data-isin="${esc(r.isin||'')}"><td class="l">${flwMsk(r.ts)}<small class="mu"> ${flwMsk(r.ts,1).slice(-8)}</small></td><td class="l"><b>${esc(r.name||r.secid)}</b> <small class="mu">${esc(r.name?r.secid:'')}</small></td><td class="l">${flwSide(r.side)}</td><td class="num">${flwPx(r.price)}</td><td class="num">${(+r.qty).toLocaleString('ru-RU')}</td><td class="num"><b>${flwRub(r.value)}</b></td><td class="l mu">${r.src==='tinvest'?'T-Invest':'Мосбиржа, −15 мин'}</td></tr>`).join('')+`</tbody></table></div>
    <p class="note" style="margin-top:10px">Крупная сделка — не меньше 5 млн ₽ (облигации 10 млн ₽) и выше 99-го перцентиля сделок бумаги за 20 дней.</p>`;
}
/* ── всплески ── */
function flwSlot(ts){const a=new Date(ts*1000+3*3600e3),h=a.getUTCHours(),m=Math.floor(a.getUTCMinutes()/10)*10,p=n=>String(n).padStart(2,'0');return`${p(h)}:${p(m)}–${p(m+10>=60?(h+1)%24:h)}:${p((m+10)%60)}`}
function loadFlwSpikes(force){
  const L=S.flw.spikes;if(L.loading)return;L.loading=true;
  api('/api/spikes?'+new URLSearchParams({force:force?1:''})).then(j=>{L.data=j}).catch(e=>{L.data={error:e.message||String(e),rows:[]}})
    .then(()=>{L.loading=false;L.key=1;if(S.page==='flw'&&S.flw.tab==='spikes')render()});
}
function flwTabSpikes(){
  const L=S.flw.spikes;
  if(!L.data&&!L.loading)loadFlwSpikes();
  if(!L.data)return waitBox('Загружаю всплески…');
  if(L.data.error)return`<div class="msg err">${esc(L.data.error)}</div>`;
  const rows=L.data.rows||[];
  if(!rows.length)return flwEmpty(L.data);
  return`<div class="tbl"><table class="flw-t"><thead><tr><th class="l">Бумага</th><th class="l">День</th><th class="l">Слот (МСК)</th><th>Всплеск</th><th>Оборот</th><th>Медиана слота</th></tr></thead><tbody>`
    +rows.map(r=>`<tr class="flw-row" data-secid="${esc(r.secid)}" data-cls="${esc(r.cls)}" data-isin="${esc(r.isin||'')}"><td class="l"><b>${esc(r.name||r.secid)}</b> <small class="mu">${esc(r.name?r.secid:'')}</small></td><td class="l">${flwMsk(r.ts)}</td><td class="l">${flwSlot(r.ts)}</td><td class="num"><b class="${r.ratio>=6?'neg':'pos'}">×${(+r.ratio).toFixed(1).replace('.',',')}</b></td><td class="num">${flwRub(r.value)}</td><td class="num mu">${flwRub(r.median)}</td></tr>`).join('')+`</tbody></table></div>
    <p class="note" style="margin-top:10px">Всплеск — оборот за 10 минут не меньше чем в 3 раза выше медианы этого же слота за 20 торговых дней и не меньше 1 млн ₽.</p>`;
}
/* ── стакан ── */
function flwBookHtml(B){
  const d=B.data;
  if(!d)return B.err?`<div class="msg err">${esc(B.err)}</div>`:waitBox('Загружаю стакан…');
  if(!d.ok)return`<div class="empty" style="padding:28px 12px">${esc(d.error||'Стакан недоступен')}</div>`;
  const m=d.metrics||{},asks=d.asks.slice(0,B.depth).slice().reverse(),bids=d.bids.slice(0,B.depth);
  const mx=Math.max(1,...d.asks.slice(0,B.depth).map(x=>x[1]),...bids.map(x=>x[1]));
  const wall=(side,p)=>(m.walls||[]).find(w=>w.side===side&&w.price===p);
  const row=(side)=>([p,q])=>{const w=wall(side,p);return`<div class="flw-l ${side}${w?' wall':''}"><i style="width:${(q/mx*100).toFixed(1)}%"></i><span class="p">${flwPx(p)}</span><span class="q">${(+q).toLocaleString('ru-RU')}</span>${w?`<em>×${w.mult}</em>`:''}</div>`};
  const imb=m.imbalance||0,pos=((imb+1)/2*100).toFixed(1);
  const t=d.tape||{};
  return`<div class="flw-book"><div class="flw-ladder">${asks.map(row('ask')).join('')}<div class="flw-mid">${m.mid!=null?flwPx(m.mid):'—'}<small class="mu"> спред ${m.spread!=null?flwPx(m.spread):'—'}</small></div>${bids.map(row('bid')).join('')}</div>
    <div class="flw-side"><div class="card"><h2>Дисбаланс<span class="sp">первые 10 уровней</span></h2>
      <div class="flw-gauge"><div class="flw-gk" style="left:${pos}%"></div></div>
      <div class="flw-leg"><span class="neg">продавцы</span><b class="${imb>0.05?'pos':imb<-0.05?'neg':''}">${(imb*100>0?'+':'')+(imb*100).toFixed(0)} %</b><span class="pos">покупатели</span></div>
      <p class="note" style="margin-top:8px">Плотности — уровни, где заявок не меньше чем в 5 раз больше медианы уровня${(m.walls||[]).length?': '+m.walls.length:''}.</p></div>
    <div class="card" style="margin-top:12px"><h2>Лента сделок<span class="sp">${flwNet(t.net||0)} за час</span></h2>
      <div class="flw-tape">${(d.trades||[]).slice(0,40).map(x=>`<div class="${x.side}"><span>${x.ts?flwMsk(x.ts,1).slice(-8):''}</span><b>${flwPx(x.price)}</b><span>${(+x.qty).toLocaleString('ru-RU')}</span></div>`).join('')||'<div class="mu">Сделок за час нет</div>'}</div></div></div></div>
    <div class="flw-meta" style="margin-top:8px"><span class="flw-src live">${d.source_label||FLW_SRC.tinvest}</span><span class="mu">обновлено ${flwMsk(d.ts,1).slice(-8)}</span></div>`;
}
function flwBookLoad(){
  const B=S.flw.book;if(B.busy)return;B.busy=true;
  const secid=B.secid;
  api('/api/orderbook?'+new URLSearchParams({secid,depth:B.depth})).then(j=>{if(secid===B.secid){B.data=j;B.err=''}}).catch(e=>{B.err=e.message||String(e)})
    .then(()=>{B.busy=false;const el=$('#flw-bookbox');if(el&&S.page==='flw'&&S.flw.tab==='book')el.innerHTML=flwBookHtml(B)});
}
function flwBookStop(){if(_flwTimer){clearInterval(_flwTimer);_flwTimer=null}}
function flwBookStart(){
  flwBookStop();flwBookLoad();
  _flwTimer=setInterval(()=>{if(S.page!=='flw'||S.flw.tab!=='book'){flwBookStop();return}if(document.hidden)return;flwBookLoad()},2500);
}
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&S.page==='flw'&&S.flw.tab==='book'&&!_flwTimer)flwBookStart()});
function flwTabBook(){
  const B=S.flw.book;
  if(!B.inst&&!B.list){B.list='loading';api('/api/flows_instruments').then(j=>{B.inst=j.rows||[];B.list=null;if(S.page==='flw'&&S.flw.tab==='book')render()}).catch(()=>{B.inst=[];B.list=null})}
  const opts=(B.inst||[]).slice();if(!opts.some(r=>r.secid===B.secid))opts.unshift({secid:B.secid,name:'',cls:''});
  return`<div class="flw-bar2"><label class="flw-min">Бумага <select id="flw-sec">${opts.map(r=>`<option value="${esc(r.secid)}"${r.secid===B.secid?' selected':''}>${esc(r.secid)} ${esc(r.name||'')}</option>`).join('')}</select></label>
    <input id="flw-q" class="inp" placeholder="Тикер, например GAZP" style="width:170px" value=""><label class="flw-min">Глубина <select id="flw-dep">${[10,20,30,50].map(n=>`<option${n===B.depth?' selected':''}>${n}</option>`).join('')}</select></label></div>
    <div id="flw-bookbox">${flwBookHtml(B)}</div>`;
}
/* ── страница ── */
function pFlw(){
  const D=S.flw;
  const body=D.tab==='large'?flwTabLarge():D.tab==='spikes'?flwTabSpikes():D.tab==='book'?flwTabBook():flwTabFlow();
  return`<div class="card"><h2>Кто покупает<span class="sp">потоки денег по сделкам Мосбиржи</span></h2>
    <div class="flw-bar2"><div class="seg" id="flw-tab">${[['flow','Потоки'],['large','Крупные сделки'],['spikes','Всплески объёма'],['book','Стакан']].map(([k,t])=>`<button data-t="${k}" class="${D.tab===k?'on':''}">${t}</button>`).join('')}</div>
    ${D.tab==='flow'?`<div class="seg" id="flw-per">${[['5m','5 мин'],['1h','1 час'],['day','День']].map(([k,t])=>`<button data-p="${k}" class="${D.period===k?'on':''}">${t}</button>`).join('')}</div>`:''}</div>
    ${body}</div>`;
}
function bindFlw(){
  const D=S.flw,on=(id,f)=>{const e=$(id);if(e)e.onclick=f};
  if(D.tab!=='book')flwBookStop();
  on('#flw-tab',e=>{const b=e.target.closest('[data-t]');if(!b)return;D.tab=b.dataset.t;render()});
  on('#flw-per',e=>{const b=e.target.closest('[data-p]');if(!b)return;D.period=b.dataset.p;D.data=null;render()});
  on('#flw-ref',()=>{D.data=null;D.key=null;loadFlw(true);render()});
  on('#flw-cls',e=>{const b=e.target.closest('[data-c]');if(!b)return;D.large.cls=b.dataset.c;D.large.data=null;render()});
  const mn=$('#flw-min');if(mn)mn.onchange=e=>{D.large.min=+e.target.value;D.large.data=null;render()};
  document.querySelectorAll('#view .flw-row').forEach(tr=>tr.onclick=()=>flwOpen(tr.dataset.secid,tr.dataset.cls,tr.dataset.isin));
  const sec=$('#flw-sec');if(sec)sec.onchange=e=>{D.book.secid=e.target.value;D.book.data=null;render()};
  const dep=$('#flw-dep');if(dep)dep.onchange=e=>{D.book.depth=+e.target.value;D.book.data=null;render()};
  const q=$('#flw-q');if(q)q.onkeydown=e=>{if(e.key!=='Enter')return;const v=q.value.trim().toUpperCase();if(/^[A-Z0-9_.\-]{1,24}$/.test(v)){D.book.secid=v;D.book.data=null;render()}};
  if(D.tab==='book')flwBookStart();
}
