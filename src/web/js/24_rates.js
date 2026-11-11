/* ── Ставки: КБД и ключевая ставка ── */
S.ratesDays=365;S.rates=null;
const RDAYS=[[90,'3 мес'],[180,'6 мес'],[365,'Год'],[730,'2 года']];
function loadRates(){
  const d=S.ratesDays;
  api('/api/rates?days='+d).then(j=>{if(d!==S.ratesDays)return;S.rates=j;if(S.page==='mkt')renderSoon();if(j.loading)setTimeout(()=>{if(S.page==='mkt'&&d===S.ratesDays)loadRates()},3000)})
   .catch(e=>{S.rates={error:e.message,labels:[]};if(S.page==='mkt')renderSoon()});
}
const pc1=v=>v==null?'—':(+v).toFixed(2).replace(/0$/,'').replace(/\.0$/,'').replace('.',',')+'%';
function pMkt(){
  const r=S.rates;
  if(!r){loadRates();return`<div class="card">${waitBox('Загружаю кривую доходности и ключевую ставку…')}</div>`}
  if(r.error)return`<div class="msg err">${esc(r.error)}</div>`;
  const n=r.labels.length,i0=n-1;
  const seg=`<div class="seg" id="rdays">${RDAYS.map(([d,t])=>`<button data-d="${d}" class="${d===S.ratesDays?'on':''}">${t}</button>`).join('')}</div>`;
  if(n<2)return`<div class="card">${r.loading?waitBox('Загружаю историю КБД с Мосбиржи — первый раз это занимает до минуты…'):'<div class="empty">Нет данных. Проверьте подключение к интернету.</div>'}</div>`;
  const lastK=r.kbd[i0],lastC=r.key[i0],first=r.kbd[0];
  chart('c-rates',line,{h:360,zero:false,labels:r.labels,fa:v=>(+v).toFixed(1).replace('.',',')+'%',ft:v=>pc1(v),
    series:[{n:'КБД · 2 года',c:'#2f6df6',hex:'#2f6df6',v:r.kbd,w:2.2},{n:'Ключевая ставка',c:'#3f7a4f',hex:'#3f7a4f',v:r.key,w:2.4,step:true}],
    hover:i=>{const e=$('#rstrip');if(e)e.innerHTML=stripHtml(r,i)},leave:()=>{const e=$('#rstrip');if(e)e.innerHTML=stripHtml(r,i0)}});
  return`<div class="g g4">${kpi('КБД · 2 года',pc1(lastK),'доходность гособлигаций, '+r.labels[i0],null,'#2f6df6')}${kpi('Ключевая ставка',pc1(lastC),'Банк России',null,'#3f7a4f')}
    ${kpi('КБД − ключевая',lastC!=null?((lastK-lastC>0?'+':'')+(lastK-lastC).toFixed(2).replace('.',',')+' п.п.'):'—','рынок закладывает '+(lastK>lastC?'повышение / удержание':'снижение')+' ставки',lastK>lastC?'neg':'pos')}
    ${kpi('КБД за период',((lastK-first>0?'+':'')+(lastK-first).toFixed(2).replace('.',',')+' п.п.'),'с '+r.labels[0],lastK-first>0?'neg':'pos')}</div>
  <div class="card rates"><h2>Доходность КБД (2 года) и ключевая ставка<span class="sp">${seg}</span></h2>
    <div class="axt">Ставка, % годовых</div><div id="c-rates" class="chart"></div><div class="axt" style="text-align:center">Дата</div>
    <div class="strip" id="rstrip">${stripHtml(r,i0)}</div>${r.loading?'<p class="note">Догружаю историю…</p>':''}</div>
  ${ratesXHtml()}
  <p class="note">КБД — кривая бескупонной доходности ОФЗ Московской биржи (срок 2 года), ключевая ставка — Банка России. Данные берутся с сайтов Мосбиржи и ЦБ при открытой программе и сохраняются локально. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function stripHtml(r,i){return`<b>${r.labels[i]}</b><span>КБД · 2 года: <b>${pc1(r.kbd[i])}</b></span><span>КС: <b>${pc1(r.key[i])}</b></span>`}


/* ── Кривая КБД: сегодня против прошлых дат; история спредов к КБД по рейтингам ── */
S.ratesX=null;
function loadRatesX(force){
  if(S._rxL&&!force)return;S._rxL=1;
  api('/api/rates/extra').then(j=>{S._rxL=0;S.ratesX=j;if(S.page==='mkt'){renderSoon();if(j.loading)setTimeout(()=>{if(S.page==='mkt')loadRatesX(true)},5000)}})
   .catch(e=>{S._rxL=0;S.ratesX={error:e.message}})
}
const RX_COL=['#ffdd2d','#3987e5','#19a070','#d95926','#9085e9'];
const RX_BCOL={'AAA':'#3987e5','AA':'#19a070','A':'#ffdd2d','BBB':'#d95926','BB и ниже':'#e66767'};
function ratesXHtml(){
  if(!S.ratesX)loadRatesX();
  const x=S.ratesX;
  if(!x)return`<div class="card rates">${waitBox('Загружаю кривую КБД за прошлые даты и историю спредов…')}</div>`;
  if(x.error)return`<div class="msg err">${esc(x.error)}</div>`;
  const cv=x.curves||{},its=cv.items||[],sp=x.spreads||{dates:[],series:{}};
  let h='';
  if(its.length>1){
    chart('c-rx-curve',line,{h:320,zero:false,labels:cv.labels,fa:v=>(+v).toFixed(1).replace('.',',')+'%',ft:v=>pc1(v),
      series:its.map((it,i)=>({n:it.label+' ('+ddm(it.date)+')',c:RX_COL[i%5],hex:RX_COL[i%5],v:it.y,w:i===0?3:1.8,dash:i>0&&i>2}))});
    h+=`<div class="card rates"><h2>Кривая КБД: сегодня и раньше</h2><div class="axt">Доходность, % годовых</div><div id="c-rx-curve" class="chart"></div><div class="axt" style="text-align:center">Срок до погашения</div>
      ${(x.notes||[]).map(t=>`<p style="margin:6px 4px;color:var(--tx2)">${esc(t)}</p>`).join('')}</div>`;
  }
  const names=Object.keys(sp.series||{});
  if(sp.dates.length>=2&&names.length){
    chart('c-rx-spr',line,{h:300,zero:false,labels:sp.dates.map(ddm),tipLabels:sp.dates.map(dlabel),fa:v=>(+v).toFixed(1).replace('.',',')+' п.п.',ft:v=>(+v).toFixed(2).replace('.',',')+' п.п.',
      series:names.map(b=>({n:b,c:RX_BCOL[b]||'#a8aebb',hex:RX_BCOL[b]||'#a8aebb',v:sp.series[b],w:2}))});
    h+=`<div class="card rates"><h2>Спреды к КБД по рейтингам во времени<span class="sp">медиана по рублёвым корпоративным облигациям</span></h2>
      <div class="axt">Спред к КБД, п.п.</div><div id="c-rx-spr" class="chart"></div>
      ${(x.spread_notes||[]).map(t=>`<p style="margin:6px 4px;color:var(--tx2)">${esc(t)}</p>`).join('')}
      <p class="note">Спред — на сколько доходность выпуска выше доходности гособлигаций того же срока (КБД). Даты по горизонтали идут неравномерно: свежие точки накоплены программой, ${sp.bf&&sp.bf.length?'более ранние ('+sp.bf.length+') восстановлены по истории торгов Мосбиржи с сегодняшними рейтингами, поэтому они приблизительные':'история продолжает накапливаться'}.${x.loading?' Догружаю историю…':''}</p></div>`;
  }else h+=`<div class="card rates"><h2>Спреды к КБД по рейтингам во времени</h2>${x.loading?waitBox('Восстанавливаю историю спредов по торгам Мосбиржи — это занимает пару минут…'):'<div class="empty">История спредов накапливается: каждый день работы программы добавляет точку.</div>'}</div>`;
  return h;
}
