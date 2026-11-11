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
    <p class="note rx-lead">Синяя линия — доходность 2-летних гособлигаций (КБД), зелёная — ключевая ставка. Если синяя выше зелёной — рынок ждёт, что ставка останется высокой; ниже — ждёт её снижения.</p>
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
  if(its.length>1)h+=curveCard(cv,its);
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

/* ── Кривая КБД: сегодня против одной даты для сравнения ── */
S.rxCmp=S.rxCmp||'3 мес. назад';
const RX_CMP=[['1 мес. назад','1 мес'],['3 мес. назад','3 мес'],['6 мес. назад','6 мес'],['12 мес. назад','1 год']];
const RX_TEN=[[0.25,'3 мес'],[1,'1 г'],[2,'2 г'],[5,'5 лет'],[10,'10 лет'],[20,'20 лет']];
const pc2=v=>v==null?'—':(+v).toFixed(2).replace('.',',')+'%';
const pp=(v,sg)=>(sg&&v>0.005?'+':v<-0.005?'−':'')+Math.abs(v).toFixed(2).replace('.',',')+' п.п.';
const dcl=v=>Math.abs(v)<0.005?'':v<0?'pos':'neg';
document.addEventListener('click',e=>{const b=e.target.closest('#rxcmp [data-c]');if(!b)return;S.rxCmp=b.dataset.c;render()});
function curveCard(cv,its){
  const now=its[0],cmp=its.find(it=>it.label===S.rxCmp)||its[1],tm=cv.terms,ix=t=>tm.indexOf(t);
  const lab=(RX_CMP.find(r=>r[0]===cmp.label)||[0,'раньше'])[1],y=(it,t)=>it.y[ix(t)];
  const seg=`<div class="seg" id="rxcmp">${RX_CMP.filter(r=>its.some(it=>it.label===r[0])).map(([k,t])=>`<button data-c="${k}" class="${k===cmp.label?'on':''}">${t}</button>`).join('')}</div>`;
  const mv=(t,name)=>{const a=y(cmp,t),b=y(now,t),d=b-a;return`${name}: <b class="num">${pc2(a)} → ${pc2(b)}</b>, <b class="${dcl(d)}">${Math.abs(d)<0.005?'без изменений':pp(d,1)}</b> за ${lab}`};
  const s0=y(cmp,10)-y(cmp,2),s1=y(now,10)-y(now,2),sh=s1-s0,fmtS=v=>(v<0?'−':'')+Math.abs(v).toFixed(2).replace('.',',')+' п.п.';
  const shape=s1<-0.15?'инвертирована (короткие ставки выше длинных)':s1>0.15?'обычная (длинные ставки выше коротких)':'почти плоская';
  const dyn=Math.abs(sh)<0.15?'форма почти не изменилась':sh>0?'стала круче':'стала площе';
  const mean=s1<-0.15?'Короткие ставки выше длинных: рынок закладывает, что ключевая ставка в будущем будет снижаться.':
    s1>0.15?'Длинные ставки выше коротких: рынок не закладывает скорого снижения ставок и требует больше за длинный срок.':
    'Короткие и длинные ставки близки: рынок не ждёт заметных изменений ставок в обе стороны.';
  const lvl=(y(now,2)-y(cmp,2));
  const lvlT=Math.abs(lvl)<0.1?'Общий уровень ставок почти не изменился.':lvl<0?'Общий уровень ставок снизился: облигации с фиксированным купоном за это время в среднем подорожали.':'Общий уровень ставок вырос: облигации с фиксированным купоном за это время в среднем подешевели.';
  const sum=`<ul class="rx-sum"><li>${mv(1,'Короткие (1 год)')}</li><li>${mv(10,'Длинные (10 лет)')}</li><li>Кривая ${dyn}, сейчас ${shape}: 10 лет − 2 года = <b class="num">${fmtS(s1)}</b> (было ${fmtS(s0)}).</li></ul>
    <p class="rx-mean"><b>Что это значит:</b> ${mean} ${lvlT}</p>`;
  const rows=RX_TEN.filter(([t])=>ix(t)>=0).map(([t,n])=>{const a=y(cmp,t),b=y(now,t),d=b-a;return`<tr><td>${n}</td><td class="num"><b>${pc2(b)}</b></td><td class="num">${pc2(a)}</td><td class="num ${dcl(d)}">${pp(d,1)}</td></tr>`}).join('');
  const AC=document.documentElement.dataset.theme==='light'?'#c99700':'#ffdd2d',nm='Сегодня ('+ddm(now.date)+')',cn=lab+' назад ('+ddm(cmp.date)+')';
  chart('c-rx-curve',line,{h:320,zero:false,labels:cv.labels,fa:v=>(+v).toFixed(1).replace('.',',')+'%',ft:v=>pc2(v),band:{a:1,b:0},
    series:[{n:cn,c:'#8d95a6',hex:'#8d95a6',v:cmp.y,w:2,dash:true},{n:nm,c:AC,hex:AC,v:now.y,w:3.4}],
    tip:i=>{const a=cmp.y[i],b=now.y[i],d=b-a;return`<b>Срок: ${esc(cv.labels[i])}</b>`+tipRow(AC,nm,pc2(b))+tipRow('#8d95a6',cn,pc2(a))+`<div style="border-top:1px solid var(--line2);padding-top:5px;margin-top:6px">Изменение<span class="${dcl(d)}">${pp(d,1)}</span></div>`}});
  return`<div class="card rates"><h2>Кривая КБД: сегодня и раньше<span class="hq" title="КБД — кривая бескупонной доходности ОФЗ, её считает Мосбиржа: показывает, под какой годовой процент государство занимает на разные сроки.">?</span><span class="sp">Сравнить с: ${seg}</span></h2>
    ${sum}
    <div class="legend rx-lg"><span><i style="background:#3ecf8e55"></i>ниже — ставки снизились</span><span><i style="background:#ff6b6b55"></i>выше — ставки выросли</span></div>
    <div class="axt">Доходность, % годовых</div><div id="c-rx-curve" class="chart"></div><div class="axt" style="text-align:center">Срок до погашения</div>
    <table class="rx-tb"><thead><tr><th style="text-align:left">Срок</th><th>Сегодня</th><th>${lab} назад</th><th>Изменение</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
(()=>{const st=document.createElement('style');st.textContent=`.hq{display:inline-flex;align-items:center;justify-content:center;width:17px;height:17px;border-radius:50%;border:1px solid var(--line2);color:var(--mu);font-size:11px;font-weight:600;margin-left:8px;cursor:help;vertical-align:middle}
.rx-sum{margin:4px 0 6px 18px;color:var(--tx2);line-height:1.6}.rx-mean{margin:4px 0 12px;color:var(--tx2)}.rx-lg{margin:0 0 6px}
.rx-tb{width:100%;margin-top:12px}.rx-tb td:first-child{text-align:left}.rx-tb td.pos{color:var(--pos)}.rx-tb td.neg{color:var(--neg)}
.rx-sum b.pos,#tip span.pos{color:var(--pos)}.rx-sum b.neg,#tip span.neg{color:var(--neg)}
.rx-lead{margin:2px 0 10px}
`;document.head.appendChild(st)})();
