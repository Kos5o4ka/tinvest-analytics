/* ── Ставки: КБД и ключевая ставка ── */
S.ratesDays=365;S.rates=null;
const RDAYS=[[90,'3 мес'],[180,'6 мес'],[365,'Год'],[730,'2 года']];
function loadRates(){
  const d=S.ratesDays;
  api('/api/rates?days='+d).then(j=>{if(d!==S.ratesDays)return;S.rates=j;if(S.page==='mkt')render();if(j.loading)setTimeout(()=>{if(S.page==='mkt'&&d===S.ratesDays)loadRates()},3000)})
   .catch(e=>{S.rates={error:e.message,labels:[]};if(S.page==='mkt')render()});
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
  <p class="note">КБД — кривая бескупонной доходности ОФЗ Московской биржи (срок 2 года), ключевая ставка — Банка России. Данные берутся с сайтов Мосбиржи и ЦБ при открытой программе и сохраняются локально. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function stripHtml(r,i){return`<b>${r.labels[i]}</b><span>КБД · 2 года: <b>${pc1(r.kbd[i])}</b></span><span>КС: <b>${pc1(r.key[i])}</b></span>`}

