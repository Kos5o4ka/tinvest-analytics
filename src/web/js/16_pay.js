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
  const KIND={coupon:['Купон',S1],dividend:['Дивиденд',S3],redemption:['Погашение',S4]};
  const byM={};ps.forEach(p=>(byM[p.date.slice(0,7)]=byM[p.date.slice(0,7)]||[]).push(p));
  const list=Object.keys(byM).sort().map(m=>{const[y,mm]=m.split('-');const t=byM[m].reduce((a,x)=>a+x.amount,0);
    return`<div class="card"><h2>${MONF[+mm-1]} ${y}<span class="sp num" style="color:var(--pos);font-size:13px;font-weight:600">${M(t)}</span></h2><div class="li">`+
    byM[m].map(p=>`<div class="it">${logo(p,34)}<div><b>${esc(p.name)}</b><small>${ddm(p.date)} · <span style="color:${KIND[p.kind][1]}">${KIND[p.kind][0]}</span>${p.est?' · оценка':''}</small></div><div class="rv num">${M(p.amount)}</div></div>`).join('')+`</div></div>`}).join('');
  return`<div class="g g4">${kpi('Ближайшие 30 дней',M(sum(p=>p.date<=in30)),'',null,S1)}${kpi('За 12 месяцев',M(sum(()=>1)),'купоны, дивиденды и погашения','pos',S3)}
    ${kpi('Купоны',M(sum(p=>p.kind==='coupon')),ps.filter(p=>p.kind==='coupon').length+' выплат',null,S1)}${kpi('Дивиденды',M(sum(p=>p.kind==='dividend')),'только объявленные, до налога',null,S3)}</div>
    <div class="card"><h2>Календарь выплат по месяцам, ₽</h2><div id="c-pay" class="chart"></div></div>
    <div class="card"><h2>Выплаты по дням<span class="sp"><span class="seg" id="pdays">${[[30,'30 дней'],[90,'90 дней'],[365,'Год']].map(([d,t])=>`<button data-d="${d}" class="${d===S.payDays?'on':''}">${t}</button>`).join('')}</span></span></h2><div id="c-days" class="chart"></div></div>
    ${list?`<div class="g g2">${list}</div>`:'<div class="card empty">Выплат в ближайший год не ожидается</div>'}
    <p class="note">Купоны — по графику эмитента и текущему количеству бумаг (до НДФЛ). Для флоатеров будущие купоны — оценка по последнему известному. Дивиденды — только уже объявленные, сумма до налога.</p>`;
}

