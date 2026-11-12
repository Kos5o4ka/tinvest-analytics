/* ── Ставки: КБД и ключевая ставка ── */
S.ratesDays=365;S.rates=null;
const RDAYS=[[90,'3 мес'],[180,'6 мес'],[365,'Год'],[730,'2 года']];
const RT_PRE=[1,2,3,5,10],RT_COL=['#2f6df6','#f59e0b','#8b5cf6','#e5484d','#0ea5a4','#64748b'],RT_MAX=6;
/* выбранные сроки КБД (лет) и свои сроки; хранятся в localStorage */
(()=>{const j=lsJson('ta_rates_terms',{}),ok=a=>Array.isArray(a)?a.map(Number).filter(t=>t>=0.25&&t<=30):[];
  S.rTerms=[...new Set(ok(j.sel))].sort((x,y)=>x-y).slice(0,RT_MAX);if(!S.rTerms.length)S.rTerms=[2];
  S.rCustom=[...new Set(ok(j.custom))].filter(t=>!RT_PRE.includes(t)).sort((x,y)=>x-y)})();
const rtSave=()=>lsSet('ta_rates_terms',JSON.stringify({sel:S.rTerms,custom:S.rCustom}));
const rtLab=t=>t<1?Math.round(t*12)+' мес':String(t).replace('.',',')+' г.';
const rtColor=t=>RT_COL[S.rTerms.indexOf(t)%RT_COL.length];
function rtReload(){S.rates=null;rtSave();render()}
function loadRates(){
  const d=S.ratesDays,tm=S.rTerms.join(',');
  api('/api/rates?days='+d+'&terms='+tm).then(j=>{if(d!==S.ratesDays||tm!==S.rTerms.join(','))return;S.rates=j;if(S.page==='mkt')renderSoon();if(j.loading)setTimeout(()=>{if(S.page==='mkt'&&d===S.ratesDays&&tm===S.rTerms.join(','))loadRates()},3000)})
   .catch(e=>{S.rates={error:e.message,labels:[]};if(S.page==='mkt')renderSoon()});
}
document.addEventListener('click',e=>{
  const c=e.target.closest('#rterms [data-t]');
  if(c){const t=+c.dataset.t,i=S.rTerms.indexOf(t);
    if(i>=0){if(S.rTerms.length>1)S.rTerms.splice(i,1)}else if(S.rTerms.length<RT_MAX){S.rTerms.push(t);S.rTerms.sort((x,y)=>x-y)}else return;
    return rtReload()}
  const x=e.target.closest('#rterms [data-x]');
  if(x){const t=+x.dataset.x;S.rCustom=S.rCustom.filter(v=>v!==t);const i=S.rTerms.indexOf(t);if(i>=0&&S.rTerms.length>1)S.rTerms.splice(i,1);return rtReload()}
  if(e.target.closest('#rtadd'))rtAdd();
});
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.id==='rtin')rtAdd()});
function rtAdd(){
  const el=$('#rtin'),t=Math.round(parseFloat(String(el.value).replace(',','.'))*100)/100;
  if(!(t>=0.25&&t<=30)){el.style.borderColor='var(--neg)';return}
  if(!RT_PRE.includes(t)&&!S.rCustom.includes(t)){S.rCustom.push(t);S.rCustom.sort((x,y)=>x-y)}
  if(!S.rTerms.includes(t)){if(S.rTerms.length>=RT_MAX)return;S.rTerms.push(t);S.rTerms.sort((x,y)=>x-y)}
  rtReload();
}
function termChips(){
  const all=[...RT_PRE,...S.rCustom].sort((x,y)=>x-y);
  return`<div class="rt-bar" id="rterms">${all.map(t=>{const on=S.rTerms.includes(t),cu=S.rCustom.includes(t);
    return`<span class="rt-chip${on?' on':''}"${on?` style="--rc:${rtColor(t)}"`:''}><button data-t="${t}">${on?'<i></i>':''}${rtLab(t)}</button>${cu?`<button class="rt-x" data-x="${t}" title="Убрать срок">×</button>`:''}</span>`}).join('')}
    <span class="rt-add"><input id="rtin" type="number" min="0.25" max="30" step="0.5" placeholder="+ свой срок, лет"><button id="rtadd" class="btn">Добавить</button></span></div>`;
}
const pc1=v=>v==null?'—':(+v).toFixed(2).replace(/0$/,'').replace(/\.0$/,'').replace('.',',')+'%';
const ppf=v=>(v>0?'+':'')+v.toFixed(2).replace('.',',')+' п.п.';
function pMkt(){
  const r=S.rates;
  if(!r){loadRates();return`<div class="card">${waitBox('Загружаю кривую доходности и ключевую ставку…')}</div>`}
  if(r.error)return`<div class="msg err">${esc(r.error)}</div>`;
  const n=r.labels.length,i0=n-1,tms=r.terms||S.rTerms,K=t=>(r.kbd||{})[String(t)]||[];
  const seg=`<div class="seg" id="rdays">${RDAYS.map(([d,t])=>`<button data-d="${d}" class="${d===S.ratesDays?'on':''}">${t}</button>`).join('')}</div>`;
  if(n<2)return`<div class="card">${termChips()}${r.loading?waitBox('Загружаю историю КБД с Мосбиржи — первый раз это занимает до минуты…'):'<div class="empty">Нет данных. Проверьте подключение к интернету.</div>'}</div>`;
  const bt=tms.includes(2)?2:tms[0],bk=K(bt),lastK=bk[i0],lastC=r.key[i0],firstI=bk.findIndex(v=>v!=null),first=bk[firstI];
  const hasSl=tms.includes(1)&&tms.includes(10)&&K(10)[i0]!=null&&K(1)[i0]!=null,sl=hasSl?K(10)[i0]-K(1)[i0]:null;
  chart('c-rates',line,{h:360,zero:false,labels:r.labels,fa:v=>(+v).toFixed(1).replace('.',',')+'%',ft:v=>pc1(v),
    series:[{n:'Ключевая ставка',c:'#3f7a4f',hex:'#3f7a4f',v:r.key,w:2.4,step:true},...tms.map(t=>({n:'КБД · '+rtLab(t),c:rtColor(t),hex:rtColor(t),v:K(t),w:2.2}))],
    hover:i=>{const e=$('#rstrip');if(e)e.innerHTML=stripHtml(r,i)},leave:()=>{const e=$('#rstrip');if(e)e.innerHTML=stripHtml(r,i0)}});
  const dk=lastK!=null&&lastC!=null?lastK-lastC:null;
  return`<div class="g g4">${kpi('КБД · '+rtLab(bt),pc1(lastK),'доходность гособлигаций, '+r.labels[i0],null,rtColor(bt))}${kpi('Ключевая ставка',pc1(lastC),'Банк России',null,'#3f7a4f')}
    ${kpi('КБД '+rtLab(bt)+' − ключевая',dk!=null?ppf(dk):'—',dk==null?'':'рынок закладывает '+(dk>0?'повышение / удержание':'снижение')+' ставки',dk==null?null:dk>0?'neg':'pos')}
    ${hasSl?kpi('Наклон: 10 лет − 1 год',ppf(sl),sl<0?'кривая инвертирована':'длинные ставки выше коротких',sl<0?'pos':null):
      kpi('КБД '+rtLab(bt)+' за период',lastK!=null&&first!=null?ppf(lastK-first):'—','с '+r.labels[Math.max(0,firstI)],lastK!=null&&first!=null?(lastK-first>0?'neg':'pos'):null)}</div>
  <div class="card rates"><h2>Доходность КБД и ключевая ставка<span class="sp">${seg}</span></h2>
    <p class="note rx-lead">Линии КБД — доходность гособлигаций выбранных сроков, зелёная — ключевая ставка. Если линия КБД выше зелёной — рынок ждёт, что ставка останется высокой; ниже — ждёт её снижения. Сроки между точками кривой считаются линейной интерполяцией.</p>
    ${termChips()}
    <div class="axt">Ставка, % годовых</div><div id="c-rates" class="chart"></div><div class="axt" style="text-align:center">Дата</div>
    <div class="strip" id="rstrip">${stripHtml(r,i0)}</div>${r.loading?'<p class="note">Догружаю историю…</p>':''}</div>
  ${ratesXHtml()}
  <p class="note">КБД — кривая бескупонной доходности ОФЗ Московской биржи (выбранные сроки), ключевая ставка — Банка России. Данные берутся с сайтов Мосбиржи и ЦБ при открытой программе и сохраняются локально. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function stripHtml(r,i){return`<b>${r.labels[i]}</b><span>КС: <b>${pc1(r.key[i])}</b></span>`+(r.terms||[]).map(t=>`<span>КБД · ${rtLab(t)}: <b>${pc1(((r.kbd||{})[String(t)]||[])[i])}</b></span>`).join('')}


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
.rt-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:4px 0 12px}
.rt-chip{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;background:var(--card)}
.rt-chip button{all:unset;cursor:pointer;padding:5px 12px;font-size:13px;color:var(--tx2);display:inline-flex;align-items:center;gap:6px}
.rt-chip.on{border-color:var(--rc)}.rt-chip.on button{color:var(--tx)}.rt-chip i{width:9px;height:9px;border-radius:50%;background:var(--rc)}
.rt-chip .rt-x{padding:5px 9px 5px 0;color:var(--mu)}.rt-chip .rt-x:hover{color:var(--neg)}
.rt-add{display:inline-flex;gap:6px;margin-left:auto}.rt-add input{width:150px;background:var(--card);border:1px solid var(--line);border-radius:8px;color:var(--tx);padding:5px 8px;font-size:13px}
`;document.head.appendChild(st)})();
