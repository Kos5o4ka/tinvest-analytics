/* ── Выплаты ── */
function pPay(){
  const b=S.bonds;
  if(!b)return`<div class="card">${waitBox('Собираю графики купонов и объявленные дивиденды…')}</div>`;
  if(b.error)return`<div class="msg err">${esc(b.error)}</div>`;
  const ps=b.payments,now=new Date(),in30=new Date(now.getTime()+30*864e5).toISOString().slice(0,10);
  const sum=f=>ps.filter(f).reduce((a,x)=>a+x.amount,0);
  const pm=payMonths(ps,12);
  const pdd=payDays(ps,S.payDays);chart('c-days',dayBars,{days:pdd.days,legend:pdd.legend,h:340});
  chart('c-pay',bars,{h:260,labels:pm.labels,tipLabels:pm.tips,stack:true,total:true,skipZero:true,series:pm.series,empty:'Выплат не ожидается'});
  const KIND={coupon:['Купон',S1],dividend:['Дивиденд',S3],redemption:['Погашение',S4],amortization:['Амортизация',S5]};
  const byM={};ps.forEach(p=>(byM[p.date.slice(0,7)]=byM[p.date.slice(0,7)]||[]).push(p));
  const list=Object.keys(byM).sort().map(m=>{const[y,mm]=m.split('-');const t=byM[m].reduce((a,x)=>a+x.amount,0);
    return`<div class="card"><h2>${MONF[+mm-1]} ${y}<span class="sp num" style="color:var(--pos);font-size:13px;font-weight:600">${M(t)}</span></h2><div class="li">`+
    byM[m].map(p=>`<div class="it"${p.kind==='dividend'&&p.ticker?stkAttr(p.ticker,'div'):''}>${logo(p,34)}<div><b>${esc(p.name)}</b><small>${ddm(p.date)} · <span style="color:${KIND[p.kind][1]}">${KIND[p.kind][0]}</span>${p.est==='forecast'?' · прогноз по ключевой ставке':p.est?' · оценка':''}</small></div><div class="rv num">${M(p.amount)}</div></div>`).join('')+`</div></div>`}).join('');
  return`<div class="g g4">${kpi('Ближайшие 30 дней',M(sum(p=>p.date<=in30)),'',null,S1)}${kpi('За 12 месяцев',M(sum(()=>1)),'купоны, дивиденды, амортизации и погашения','pos',S3)}
    ${kpi('Купоны',M(sum(p=>p.kind==='coupon')),ps.filter(p=>p.kind==='coupon').length+' выплат',null,S1)}${kpi('Дивиденды',M(sum(p=>p.kind==='dividend')),'только объявленные, до налога',null,S3)}</div>
    <div class="card"><h2>Календарь выплат по месяцам, ₽</h2><div id="c-pay" class="chart"></div></div>
    <div class="card"><h2>Выплаты по дням<span class="sp"><span class="seg" id="pdays">${[[30,'30 дней'],[90,'90 дней'],[365,'Год']].map(([d,t])=>`<button data-d="${d}" class="${d===S.payDays?'on':''}">${t}</button>`).join('')}</span></span></h2><div id="c-days" class="chart"></div></div>
    ${list?`<div class="g g2">${list}</div>`:emptyHint('В ближайший год выплат не ожидается: в портфеле нет облигаций с купонами и акций с объявленными дивидендами. Подобрать облигации с купоном можно в скринере.',[['scr','Подобрать облигации',1],['bonds','Мои облигации']])}
    ${cf36Section()}
    <p class="note">Купоны — по графику эмитента и текущему количеству бумаг (до НДФЛ). Для флоатеров ещё не объявленные купоны — прогноз по ключевой ставке ЦБ плюс спред эмитента (пометка «прогноз по ключевой ставке»). Амортизации — частичное погашение номинала по графику Мосбиржи. Дивиденды — только уже объявленные, сумма до налога.</p>`;
}



/* ── Матрица потоков на 3 года + «Снежный ком 2.0» (грузится лениво, при открытии раздела) ── */
const CF36={open:false,st:'idle',data:null,err:'',acc:null,rate:'lqdt',own:'12',reinv:true,tries:0};
const CF36_K=[['coupon','Купоны',S1],['dividend','Дивиденды',S3],['amortization','Амортизации',S5],['redemption','Погашения',S4]];
const cf36Pct=v=>v==null||isNaN(v)?'—':(+v).toFixed(2).replace('.',',')+' %';
/* K(m) = K(m−1)·(1 + r/12) + CF(m) — та же формула, что cf36_simulate на сервере */
function cf36Sim(ms,rate,start){
  const k=(rate||0)/1200;let kp=start||0,kc=start||0;const p=[],c=[];
  ms.forEach(m=>{const cf=+(m.total||0);kp+=cf;kc=kc*(1+k)+cf;p.push(kp);c.push(kc)});
  return{plain:p,comp:c};
}
function cf36Rate(){
  const r=(CF36.data&&CF36.data.rates)||{};
  if(CF36.rate==='lqdt')return r.lqdt;
  if(CF36.rate==='ofz')return r.ofz1y;
  const v=parseFloat(String(CF36.own).replace(',','.'));return isNaN(v)?null:Math.max(0,Math.min(100,v));
}
function cf36Load(){
  if(CF36.st==='load')return;
  const acc=S.account;CF36.st='load';CF36.acc=acc;CF36.err='';
  api('/api/cashflow36?'+new URLSearchParams({account:acc})).then(j=>{
    if(S.account!==acc)return;
    if(j&&j.stale&&CF36.tries<10){CF36.tries++;CF36.data=j;CF36.st='ok';setTimeout(()=>{if(S.account===acc&&CF36.open){CF36.st='idle';cf36Load()}},4000)}
    else{CF36.data=j;CF36.st='ok';CF36.tries=0}
    if(S.page==='pay')renderSoon();
  }).catch(e=>{if(S.account!==acc)return;CF36.st='err';CF36.err=e.message||'Не удалось получить данные';if(S.page==='pay')renderSoon()});
}
function cf36Grid(d){
  const ms=d.months||[],mx=Math.max(...ms.map(m=>m.total),1);
  const rows=[0,1,2].map(y=>{
    const part=ms.slice(y*12,y*12+12);if(!part.length)return'';
    const tot=part.reduce((a,m)=>a+m.total,0),emp=part.filter(m=>m.total<=0).length;
    const cells=part.map((m,j)=>{const i=y*12+j,lab=mlabel(m.ym);
      if(m.total<=0)return`<div class="cf36-c cf36-e" data-i="${i}"><span class="cf36-m">${esc(lab)}</span><span class="cf36-v">пусто</span></div>`;
      const a=Math.round(10+Math.sqrt(m.total/mx)*50),eh=Math.round(m.est/m.total*100);
      return`<div class="cf36-c" data-i="${i}" style="background:color-mix(in srgb,var(--ac) ${a}%,transparent)"><span class="cf36-m">${esc(lab)}</span><span class="cf36-v num">${short(m.total)}</span>${eh>0?`<i class="cf36-h" style="height:${Math.max(4,Math.round(eh*.3))}px" title="оценка: ${eh}%"></i>`:''}</div>`}).join('');
    return`<div class="cf36-r"><div class="cf36-rh"><b>${y+1}-й год</b><small>${esc(mlabel(part[0].ym))} – ${esc(mlabel(part[part.length-1].ym))}</small><span class="num">${M(tot)}</span>${emp?`<small class="cf36-w">пустых: ${emp}</small>`:''}</div><div class="cf36-row">${cells}</div></div>`}).join('');
  return`<div class="cf36-scroll"><div class="cf36-grid" id="cf36-grid">${rows}</div></div>`;
}
function cf36Tip(i){
  const m=CF36.data.months[i],[y,mm]=m.ym.split('-');
  let h=`<b>${MONF[+mm-1]} ${y}</b>`;
  if(m.total<=0)return h+'<div>Выплат нет</div>';
  CF36_K.forEach(([k,n,c])=>{if(m.by[k])h+=tipRow(c,n,M(m.by[k]))});
  h+=`<div class="tot">Итого<span>${M(m.total)}</span></div>`;
  if(m.est>0)h+=`<div>в т. ч. оценка<span>${M(m.est)}</span></div>`;
  (m.top||[]).forEach(t=>h+=`<div style="color:var(--tx2)">${esc(t.name)}${t.est?' (оценка)':''}<span>${M(t.amount)}</span></div>`);
  return h;
}
function cf36Calc(){
  const d=CF36.data,r=cf36Rate();
  if(!d||r==null)return null;
  const sim=cf36Sim(d.months,r,0),n=sim.plain.length;
  return{r,sim,fin:sim.comp[n-1],fin0:sim.plain[n-1]};
}
function cf36Kpis(){
  const c=cf36Calc();if(!c)return'<div class="msg">Укажите ставку, чтобы рассчитать реинвестирование.</div>';
  const on=CF36.reinv,fin=on?c.fin:c.fin0;
  return`<div class="g g3"><div class="card kpi"><div class="k"><i style="background:${S1}"></i>${on?'Итог с реинвестом':'Итог (реинвест выключен)'}</div><div class="v num pos">${M(fin)}</div><div class="s">под ${cf36Pct(c.r)} годовых</div></div>
  <div class="card kpi"><div class="k"><i style="background:${S4}"></i>Итог без реинвеста</div><div class="v num">${M(c.fin0)}</div><div class="s">выплаты просто копятся</div></div>
  <div class="card kpi"><div class="k">Разница</div><div class="v num ${on?'pos':''}">${on?'+'+M(c.fin-c.fin0):M(0)}</div><div class="s">${on?'проценты на реинвестирование':'включите реинвест'}</div></div></div>`;
}
function cf36Line(el){
  const c=cf36Calc(),d=CF36.data;if(!c||!d)return;
  const labels=d.months.map(m=>mlabel(m.ym)),ser=[];
  if(CF36.reinv)ser.push({n:'С реинвестом',c:S1,v:c.sim.comp});
  ser.push({n:'Без реинвеста',c:S4,v:c.sim.plain,dash:CF36.reinv,w:CF36.reinv?1.6:2});
  line(el,{h:240,labels,series:ser,tipLabels:d.months.map(m=>{const[y,mm]=m.ym.split('-');return MONF[+mm-1]+' '+y}),empty:'Нет данных'});
}
function cf36Update(){
  const k=document.getElementById('cf36-kpi');if(k)k.innerHTML=cf36Kpis();
  const el=document.getElementById('cf36-chart');if(el)try{cf36Line(el)}catch(e){console.error(e)}
}
function cf36Body(){
  if(CF36.st==='load'||CF36.st==='idle')return waitBox('Собираю графики выплат на 36 месяцев…');
  if(CF36.st==='err')return`<div class="msg err">${esc(CF36.err)} <button class="btn ghost cf36-retry">Повторить</button></div>`;
  const d=CF36.data;
  if(!d||d.error)return`<div class="msg err">${esc((d&&d.error)||'Нет данных')} <button class="btn ghost cf36-retry">Повторить</button></div>`;
  const ms=d.months||[],n=ms.length||36,emp=ms.filter(m=>m.total<=0).length,tot=ms.reduce((a,m)=>a+m.total,0),r=d.rates||{};
  const rb=(k,t,v)=>`<button data-r="${k}" class="${CF36.rate===k?'on':''}" ${k!=='own'&&v==null?'disabled title="нет данных"':''}>${t}${k!=='own'&&v!=null?' · '+cf36Pct(v):''}</button>`;
  const src=CF36.rate==='lqdt'?r.lqdt_src:CF36.rate==='ofz'?r.ofz1y_src:'введена вручную';
  return`<div class="g g4">${kpi('За 3 года',M(tot),'в среднем '+M(tot/n)+' в месяц','pos',S3)}${kpi('Пустых месяцев',emp+' из '+n,emp?'нет ни одной выплаты':'выплаты каждый месяц',emp?'neg':'pos')}
    ${kpi('Оценочная часть',M(d.est_total||0),tot?Math.round((d.est_total||0)/tot*100)+' % от суммы':'',null,S5)}${kpi('Макс. месяц',M(Math.max(0,...ms.map(m=>m.total))),'пик выплат')}</div>
    ${cf36Grid(d)}
    <div class="cf36-leg"><span><i class="cf36-sw" style="background:color-mix(in srgb,var(--ac) 45%,transparent)"></i>чем темнее, тем больше выплат</span><span><i class="cf36-sw cf36-hs"></i>штриховка — оценочная часть</span><span><i class="cf36-sw cf36-ee"></i>пустой месяц</span></div>
    <h3 class="cf36-h3">Снежный ком 2.0<span class="sp">что будет, если выплаты реинвестировать</span></h3>
    <div class="cf36-ctl"><span class="seg cf36-rate">${rb('lqdt','LQDT',r.lqdt)}${rb('ofz','Короткие ОФЗ',r.ofz1y)}${rb('own','Своя ставка')}</span>
      ${CF36.rate==='own'?`<label class="cf36-own">ставка, % годовых <input class="cf36-in" inputmode="decimal" value="${esc(CF36.own)}" size="5"></label>`:''}
      <label class="cf36-chk"><input type="checkbox" class="cf36-reinv" ${CF36.reinv?'checked':''}> реинвестировать выплаты</label></div>
    <div class="cf36-src">Ставка: ${esc(src||'—')}. LQDT — фонд ликвидности, сам не гарантирует доходность.</div>
    <div id="cf36-kpi">${cf36Kpis()}</div>
    <div id="cf36-chart" class="chart"></div>
    <p class="note">Формула: K(m) = K(m−1)·(1 + r/12) + CF(m), где CF(m) — выплаты месяца m, r — годовая ставка реинвестирования, K(0) = 0. Налоги на проценты от реинвестирования не учтены.</p>
    <p class="note">${(d.notes||[]).map(esc).join(' ')} Оценки помечены штриховкой; дивиденды не гарантированы и могут быть отменены или изменены, а будущие ставки — отличаться от прогноза. Это не инвестиционная рекомендация.</p>`;
}
function cf36Section(){
  if(CF36.acc!==null&&CF36.acc!==S.account&&CF36.st!=='load'){CF36.st='idle';CF36.data=null}
  if(CF36.open&&CF36.st==='idle')cf36Load();
  if(CF36.open)chart('cf36-chart',(el)=>cf36Line(el),{});
  return`<div class="card cf36"><h2>Матрица потоков на 3 года<span class="sp"><button class="btn ghost cf36-tgl">${CF36.open?'Свернуть':'Показать'}</button></span></h2>
    ${CF36.open?`<div id="cf36-body">${cf36Body()}</div>`:'<p class="note" style="margin:0">36 месяцев выплат по купонам, дивидендам, амортизациям и погашениям, пустые месяцы и симулятор реинвестирования. Данные загружаются при открытии.</p>'}</div>`;
}
document.addEventListener('click',e=>{
  const t=e.target;if(!t.closest)return;
  if(t.closest('.cf36-tgl')){CF36.open=!CF36.open;render();return}
  if(t.closest('.cf36-retry')){CF36.st='idle';CF36.tries=0;render();return}
  const b=t.closest('.cf36-rate [data-r]');if(b&&!b.disabled){CF36.rate=b.dataset.r;render()}
});
document.addEventListener('input',e=>{
  const t=e.target;if(!t.classList)return;
  if(t.classList.contains('cf36-in')){CF36.own=t.value;cf36Update()}
  else if(t.classList.contains('cf36-reinv')){CF36.reinv=t.checked;cf36Update()}
});
document.addEventListener('mouseover',e=>{
  const g=e.target.closest&&e.target.closest('#cf36-grid');
  if(g&&!g._cf){g._cf=1;bindTip(g,i=>cf36Tip(i))}
});
