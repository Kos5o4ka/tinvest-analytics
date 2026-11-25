/* ── Выплаты ── */
const PAY_UI={tab:'plan'};
const PAY_J={st:'idle',data:null,err:'',acc:null,tries:0};

function pjLoad(){
  if(PAY_J.st==='load')return;
  const acc=S.account;PAY_J.st='load';PAY_J.acc=acc;PAY_J.err='';
  api('/api/pay/journal?'+new URLSearchParams({account:acc})).then(j=>{
    if(S.account!==acc)return;
    if(j&&j.stale&&PAY_J.tries<10){PAY_J.tries++;PAY_J.data=j;PAY_J.st='ok';setTimeout(()=>{if(S.account===acc&&PAY_UI.tab==='journal'){PAY_J.st='idle';pjLoad()}},4000)}
    else{PAY_J.data=j;PAY_J.st='ok';PAY_J.tries=0}
    if(S.page==='pay')renderSoon();
  }).catch(e=>{if(S.account!==acc)return;PAY_J.st='err';PAY_J.err=e.message||'Не удалось загрузить журнал выплат';if(S.page==='pay')renderSoon()});
}

function pjRender(){
  if(PAY_J.acc!==null&&PAY_J.acc!==S.account&&PAY_J.st!=='load'){PAY_J.st='idle';PAY_J.data=null}
  if(PAY_J.st==='idle')pjLoad();
  if(PAY_J.st==='load'||PAY_J.st==='idle')return`<div class="card">${waitBox('Собираю фактические выплаты и считаю YOC…')}</div>`;
  if(PAY_J.st==='err')return`<div class="msg err">${esc(PAY_J.err)} <button class="btn ghost pj-retry">Повторить</button></div>`;
  const d=PAY_J.data;
  if(!d||d.error)return`<div class="msg err">${esc((d&&d.error)||'Нет данных')} <button class="btn ghost pj-retry">Повторить</button></div>`;
  const ms=(d.months||[]).slice(-36),secs=d.securities||[],ys=d.years||[];
  if(ms.length){
    const labels=ms.map(m=>mlabel(m.ym));
    const tips=ms.map(m=>{const[y,mm]=m.ym.split('-');return MONF[+mm-1]+' '+y});
    chart('c-pj-m',bars,{h:250,labels,tipLabels:tips,stack:true,total:true,skipZero:true,series:[
      {n:'Купоны',c:S1,v:ms.map(m=>m.coupons_rub)},
      {n:'Дивиденды',c:S3,v:ms.map(m=>m.dividends_rub)}
    ],empty:'Фактических выплат не найдено'});
  }
  const yocStr=v=>v==null||isNaN(v)?'—':(+v).toFixed(2).replace('.',',')+' %';
  const yrsHtml=ys.length?`<div class="card"><h2>Итоги по годам</h2><div class="tbl"><table><thead><tr><th class="l">Год</th><th>Выплат</th><th>Купоны, ₽</th><th>Дивиденды, ₽</th><th>Всего, ₽</th></tr></thead><tbody>${ys.map(y=>`<tr><td class="l"><b>${esc(y.year)}</b></td><td class="num">${y.count}</td><td class="num">${M(y.coupons_rub)}</td><td class="num">${M(y.dividends_rub)}</td><td class="num pos"><b>${M(y.total_rub)}</b></td></tr>`).join('')}</tbody></table></div></div>`:'';
  const secRows=secs.map(s=>`<tr><td class="l">${logo(s,26)} <b>${esc(s.name)}</b>${s.ticker?` <small class="mu">${esc(s.ticker)}</small>`:''}</td><td class="l">${esc(s.type_ru||s.type)}</td><td class="num">${s.qty?s.qty:'—'}</td><td class="num">${M(s.coupons_rub)}</td><td class="num">${M(s.dividends_rub)}</td><td class="num"><b>${M(s.total_rub)}</b></td><td class="num">${s.cost_rub>0?M(s.cost_rub):'—'}</td><td class="num ${s.yoc_pct!=null&&s.yoc_pct>0?'pos':''}">${yocStr(s.yoc_pct)}</td><td class="num">${yocStr(s.yoc_total_pct)}</td></tr>`).join('');
  return`<div class="g g4">${kpi('Всего получено',M(d.total_rub),'купоны и дивиденды за всё время','pos',S3)}${kpi('За последние 12 мес.',M(d.total_12m_rub),'фактические выплаты',null,S1)}
    ${kpi('Купоны (факт)',M(d.coupons_rub),'по всем операциям',null,S1)}${kpi('YOC портфеля (12 мес.)',yocStr(d.portfolio_yoc_pct),'к FIFO-стоимости '+M(d.cost_rub),d.portfolio_yoc_pct?'pos':null,S3)}</div>
    <div class="card"><h2>Фактические выплаты по месяцам, ₽<span class="sp">${ms.length?'последние '+ms.length+' мес.':''}</span></h2>${ms.length?'<div id="c-pj-m" class="chart"></div>':'<p class="note" style="margin:0">Операций по купонам и дивидендам пока нет.</p>'}</div>
    ${yrsHtml}
    <div class="card"><h2>Доходность на цену покупки (YOC) по бумагам<span class="sp">FIFO-база · 12 мес. и накопленно</span></h2>
      ${secs.length?`<div class="tbl"><table><thead><tr><th class="l">Бумага</th><th class="l">Тип</th><th>Кол-во</th><th>Купоны</th><th>Дивиденды</th><th>Всего</th><th>FIFO-стоимость</th><th>YOC 12 мес.</th><th>Накопл. YOC</th></tr></thead><tbody>${secRows}</tbody></table></div>`:'<p class="note" style="margin:0">Нет данных по бумагам с выплатами или открытыми позициями.</p>'}
    </div>
    <p class="note">${(d.notes||[]).map(esc).join(' ')}</p>`;
}

function payTabs(){
  const tabs=[['plan','План выплат'],['journal','Факт и YOC'],['cf36','Прогноз 36 мес.']];
  return`<div class="row" style="margin-bottom:12px"><div class="seg" id="pay-tabs">${tabs.map(([k,t])=>`<button data-ptab="${k}" class="${PAY_UI.tab===k?'on':''}">${t}</button>`).join('')}</div></div>`;
}

function pPay(){
  const tab=PAY_UI.tab;
  if(tab==='journal')return payTabs()+pjRender();
  if(tab==='cf36'){CF36.open=true;return payTabs()+cf36Section()}
  const b=S.bonds;
  if(!b)return payTabs()+`<div class="card">${waitBox('Собираю графики купонов и объявленные дивиденды…')}</div>`;
  if(b.error)return payTabs()+`<div class="msg err">${esc(b.error)}</div>`;
  const ps=b.payments,now=new Date(),in30=localIso(new Date(now.getTime()+30*864e5));
  const sum=f=>ps.filter(f).reduce((a,x)=>a+x.amount,0);
  const pm=payMonths(ps,12);
  const pdd=payDays(ps,S.payDays);chart('c-days',dayBars,{days:pdd.days,legend:pdd.legend,h:340});
  chart('c-pay',bars,{h:260,labels:pm.labels,tipLabels:pm.tips,stack:true,total:true,skipZero:true,series:pm.series,empty:'Выплат не ожидается'});
  const KIND={coupon:['Купон',S1],dividend:['Дивиденд',S3],redemption:['Погашение',S4],amortization:['Амортизация',S5]};
  const byM={};ps.forEach(p=>(byM[p.date.slice(0,7)]=byM[p.date.slice(0,7)]||[]).push(p));
  const list=Object.keys(byM).sort().map(m=>{const[y,mm]=m.split('-');const t=byM[m].reduce((a,x)=>a+x.amount,0);
    return`<div class="card"><h2>${MONF[+mm-1]} ${y}<span class="sp num" style="color:var(--pos);font-size:13px;font-weight:600">${M(t)}</span></h2><div class="li">`+
    byM[m].map(p=>`<div class="it"${p.kind==='dividend'&&p.ticker?stkAttr(p.ticker,'div'):''}>${logo(p,34)}<div><b>${esc(p.name)}</b><small>${ddm(p.date)} · <span style="color:${KIND[p.kind][1]}">${KIND[p.kind][0]}</span>${p.est==='forecast'?' · прогноз по ключевой ставке':p.est?' · оценка':''}</small></div><div class="rv num">${M(p.amount)}</div></div>`).join('')+`</div></div>`}).join('');
  return payTabs()+`<div class="g g4">${kpi('Ближайшие 30 дней',M(sum(p=>p.date<=in30)),'',null,S1)}${kpi('За 12 месяцев',M(sum(()=>1)),'купоны, дивиденды, амортизации и погашения','pos',S3)}
    ${kpi('Купоны',M(sum(p=>p.kind==='coupon')),ps.filter(p=>p.kind==='coupon').length+' выплат',null,S1)}${kpi('Дивиденды',M(sum(p=>p.kind==='dividend')),'только объявленные, до налога',null,S3)}</div>
    <div class="card"><h2>Календарь выплат по месяцам, ₽</h2><div id="c-pay" class="chart"></div></div>
    <div class="card"><h2>Выплаты по дням<span class="sp"><span class="seg" id="pdays">${[[30,'30 дней'],[90,'90 дней'],[365,'Год']].map(([d,t])=>`<button data-d="${d}" class="${d===S.payDays?'on':''}">${t}</button>`).join('')}</span></span></h2><div id="c-days" class="chart"></div></div>
    ${list?`<div class="g g2">${list}</div>`:emptyHint('В ближайший год выплат не ожидается: в портфеле нет облигаций с купонами и акций с объявленными дивидендами. Подобрать облигации с купоном можно в скринере.',[['scr','Подобрать облигации',1],['bonds','Мои облигации']])}
    <p class="note">Купоны — по графику эмитента и текущему количеству бумаг (до НДФЛ). Для флоатеров ещё не объявленные купоны — прогноз по ключевой ставке ЦБ плюс спред эмитента (пометка «прогноз по ключевой ставке»). Амортизации — частичное погашение номинала по графику Мосбиржи. Дивиденды — только уже объявленные, сумма до налога.</p>`;
}



/* ── Матрица потоков на 3 года + «Снежный ком 2.0» (грузится лениво, при открытии раздела) ── */
const CF36={open:false,st:'idle',data:null,err:'',acc:null,rate:'lqdt',traj:'flat',own:'12',reinv:true,usePut:true,useCall:false,tries:0};
const CF36_K=[['coupon','Купоны',S1],['dividend','Дивиденды',S3],['amortization','Амортизации',S5],['redemption','Погашения',S4]];
const cf36Pct=v=>v==null||isNaN(v)?'—':(+v).toFixed(2).replace('.',',')+' %';
/* K(m) = K(m−1)·(1 + r(m)/12) + CF(m) — та же формула, что cf36_simulate на сервере */
function cf36Sim(ms,rateOrSeq,start){
  const isSeq=Array.isArray(rateOrSeq);
  let kp=start||0,kc=start||0;const p=[],c=[];
  ms.forEach((m,i)=>{
    const cf=+(m.total||0);
    const ri=isSeq?(rateOrSeq[i]!=null?rateOrSeq[i]:rateOrSeq[rateOrSeq.length-1]||0):(rateOrSeq||0);
    const k=Math.max(0,ri)/1200;
    kp+=cf;kc=kc*(1+k)+cf;p.push(kp);c.push(kc);
  });
  return{plain:p,comp:c};
}
function cf36Rate(){
  const r=(CF36.data&&CF36.data.rates)||{};
  if(CF36.rate==='lqdt')return r.lqdt;
  if(CF36.rate==='ofz')return r.ofz1y;
  const v=parseFloat(String(CF36.own).replace(',','.'));return isNaN(v)?null:Math.max(0,Math.min(100,v));
}
function cf36RateSeq(){
  const base=cf36Rate();
  if(base==null)return null;
  const d=CF36.data||{},tr=d.trajectories&&d.trajectories.items&&d.trajectories.items[CF36.traj];
  const n=(d.months||[]).length||36;
  if(CF36.rate==='own'||!tr||!tr.rates||!tr.rates.length)return Array(n).fill(base);
  const b0=tr.rates[0];
  return tr.rates.slice(0,n).map(kr=>Math.max(0,base+(kr-b0)));
}
function cf36SimMonths(){
  const d=CF36.data||{};
  const ms=(d.months||[]).map(m=>({ym:m.ym,total:+(m.total||0),by:Object.assign({},m.by||{})}));
  const byYm={};ms.forEach(m=>{byYm[m.ym]=m});
  const kinds=[];if(CF36.usePut)kinds.push('offer_put');if(CF36.useCall)kinds.push('offer_call');
  let offerAdded=0,maturityShifted=0,offerCount=0;
  if(kinds.length&&d.offers&&d.offers.length){
    const seen={};
    d.offers.slice().sort((a,b)=>(a.date||'').localeCompare(b.date||'')).forEach(of=>{
      if(kinds.indexOf(of.kind)<0)return;
      const bkey=of.uid||of.isin||of.name;if(seen[bkey])return;
      const row=byYm[of.ym];if(!row)return;
      seen[bkey]=1;
      const amt=+(of.amount||0);
      row.total+=amt;offerAdded+=amt;offerCount++;
      if(of.maturity_ym&&of.maturity_amount>0&&byYm[of.maturity_ym]){
        const mr=byYm[of.maturity_ym];
        const red=+(mr.by&&mr.by.redemption||mr.total||0);
        const sub=Math.min(+of.maturity_amount,red,mr.total);
        mr.total=Math.max(0,mr.total-sub);
        maturityShifted+=sub;
      }
    });
  }
  let coupDiv=0,amortRed=0;
  ms.forEach(m=>{
    coupDiv+=(+(m.by.coupon||0))+(+(m.by.dividend||0));
    amortRed+=(+(m.by.amortization||0))+(+(m.by.redemption||0));
  });
  amortRed=Math.max(0,amortRed-maturityShifted);
  return{months:ms,offerAdded,maturityShifted,offerCount,coupDiv,amortRed};
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
  const d=CF36.data,seq=cf36RateSeq();
  if(!d||!seq)return null;
  const sm=cf36SimMonths();
  const sim=cf36Sim(sm.months,seq,0),n=sim.plain.length;
  const avgR=seq.reduce((a,x)=>a+x,0)/(seq.length||1);
  return{r:avgR,seq,sm,sim,fin:sim.comp[n-1],fin0:sim.plain[n-1]};
}
function cf36Kpis(){
  const c=cf36Calc();if(!c)return'<div class="msg">Укажите ставку, чтобы рассчитать реинвестирование.</div>';
  const on=CF36.reinv,fin=on?c.fin:c.fin0,sm=c.sm;
  const tr=(CF36.data&&CF36.data.trajectories&&CF36.data.trajectories.items&&CF36.data.trajectories.items[CF36.traj]);
  const rSub=CF36.rate!=='own'&&tr?`${tr.name}: в среднем ${cf36Pct(c.r)}`:`под ${cf36Pct(c.r)} годовых`;
  return`<div class="g g4"><div class="card kpi"><div class="k"><i style="background:${S1}"></i>${on?'Итог с реинвестом':'Итог (реинвест выключен)'}</div><div class="v num pos">${M(fin)}</div><div class="s">${esc(rSub)}</div></div>
  <div class="card kpi"><div class="k"><i style="background:${S4}"></i>Итог без реинвеста</div><div class="v num">${M(c.fin0)}</div><div class="s">купоны/див. ${M(sm.coupDiv)} · тела ${M(sm.amortRed+(sm.offerAdded||0))}</div></div>
  <div class="card kpi"><div class="k">Доход от реинвеста</div><div class="v num ${on?'pos':''}">${on?'+'+M(c.fin-c.fin0):M(0)}</div><div class="s">${on?'сложный процент по траектории':'включите реинвест'}</div></div>
  <div class="card kpi"><div class="k"><i style="background:${S5}"></i>Оферты в расчёте</div><div class="v num">${M(sm.offerAdded||0)}</div><div class="s">${sm.offerCount?sm.offerCount+' оферт(ы) реинвестировано':'оферты не выбраны / отсутствуют'}</div></div></div>`;
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
  const trs=(d.trajectories&&d.trajectories.items)||{};
  const trSeg=CF36.rate!=='own'&&trs.flat?`<span class="seg cf36-traj">${['flat','cut','hike'].map(k=>trs[k]?`<button data-tr="${k}" class="${CF36.traj===k?'on':''}" title="${esc(trs[k].desc)}">${esc(trs[k].name)}</button>`:'').join('')}</span>`:'';
  const os=d.offer_summary||{},ofs=d.offers||[];
  const ofRows=ofs.map(o=>`<tr><td class="l">${ddm(o.date)}</td><td class="l"><b>${esc(o.name)}</b>${o.ticker?` <small class="mu">${esc(o.ticker)}</small>`:''}</td><td class="l">${esc(o.kind_ru)}</td><td class="num">${(+o.price_pct||100).toFixed(2).replace('.',',')} %</td><td class="num"><b>${M(o.amount)}</b></td></tr>`).join('');
  const ofBox=ofs.length?`<div style="margin-top:16px"><h3 class="cf36-h3">Ближайшие оферты (окно 36 мес.)<span class="sp">пут: ${os.put_count||0} (${M(os.put_total||0)}) · колл: ${os.call_count||0} (${M(os.call_total||0)})</span></h3>
    <div class="tbl"><table><thead><tr><th class="l">Дата</th><th class="l">Облигация</th><th class="l">Тип оферты</th><th>Цена выкупа</th><th>Сумма номинала</th></tr></thead><tbody>${ofRows}</tbody></table></div></div>`:'';
  return`<div class="g g4">${kpi('За 3 года',M(tot),'в среднем '+M(tot/n)+' в месяц','pos',S3)}${kpi('Пустых месяцев',emp+' из '+n,emp?'нет ни одной выплаты':'выплаты каждый месяц',emp?'neg':'pos')}
    ${kpi('Оценочная часть',M(d.est_total||0),tot?Math.round((d.est_total||0)/tot*100)+' % от суммы':'',null,S5)}${kpi('Макс. месяц',M(Math.max(0,...ms.map(m=>m.total))),'пик выплат')}</div>
    ${cf36Grid(d)}
    <div class="cf36-leg"><span><i class="cf36-sw" style="background:color-mix(in srgb,var(--ac) 45%,transparent)"></i>чем темнее, тем больше выплат</span><span><i class="cf36-sw cf36-hs"></i>штриховка — оценочная часть</span><span><i class="cf36-sw cf36-ee"></i>пустой месяц</span></div>
    <h3 class="cf36-h3">Снежный ком 2.0<span class="sp">реинвест купонов, амортизаций и оферт по траектории КС</span></h3>
    <div class="cf36-ctl"><span class="seg cf36-rate">${rb('lqdt','LQDT',r.lqdt)}${rb('ofz','Короткие ОФЗ',r.ofz1y)}${rb('own','Своя ставка')}</span>
      ${trSeg}
      ${CF36.rate==='own'?`<label class="cf36-own">ставка, % годовых <input class="cf36-in" inputmode="decimal" value="${esc(CF36.own)}" size="5"></label>`:''}
      <label class="cf36-chk"><input type="checkbox" class="cf36-reinv" ${CF36.reinv?'checked':''}> реинвестировать выплаты</label>
      <label class="cf36-chk"><input type="checkbox" class="cf36-put" ${CF36.usePut?'checked':''}> учитывать пут-оферты</label>
      <label class="cf36-chk"><input type="checkbox" class="cf36-call" ${CF36.useCall?'checked':''}> учитывать колл-оферты</label></div>
    <div class="cf36-src">Ставка: ${esc(src||'—')}. LQDT — фонд ликвидности, сам не гарантирует доходность.</div>
    <div id="cf36-kpi">${cf36Kpis()}</div>
    <div id="cf36-chart" class="chart"></div>
    ${ofBox}
    <p class="note">Формула: K(m) = K(m−1)·(1 + r(m)/12) + CF(m), где CF(m) — выплаты месяца m (с учётом досрочного выхода по выбранным офертам без двойного счёта погашения), r(m) — годовая ставка реинвестирования по выбранной траектории ключевой ставки, K(0) = 0. Налоги на проценты от реинвестирования не учтены.</p>
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
  const pt=t.closest('#pay-tabs [data-ptab]');if(pt){PAY_UI.tab=pt.dataset.ptab;render();return}
  if(t.closest('.pj-retry')){PAY_J.st='idle';PAY_J.tries=0;render();return}
  if(t.closest('.cf36-tgl')){CF36.open=!CF36.open;render();return}
  if(t.closest('.cf36-retry')){CF36.st='idle';CF36.tries=0;render();return}
  const b=t.closest('.cf36-rate [data-r]');if(b&&!b.disabled){CF36.rate=b.dataset.r;render();return}
  const tr=t.closest('.cf36-traj [data-tr]');if(tr){CF36.traj=tr.dataset.tr;render()}
});
document.addEventListener('input',e=>{
  const t=e.target;if(!t.classList)return;
  if(t.classList.contains('cf36-in')){CF36.own=t.value;cf36Update()}
  else if(t.classList.contains('cf36-reinv')){CF36.reinv=t.checked;cf36Update()}
  else if(t.classList.contains('cf36-put')){CF36.usePut=t.checked;cf36Update()}
  else if(t.classList.contains('cf36-call')){CF36.useCall=t.checked;cf36Update()}
});
document.addEventListener('mouseover',e=>{
  const g=e.target.closest&&e.target.closest('#cf36-grid');
  if(g&&!g._cf){g._cf=1;bindTip(g,i=>cf36Tip(i))}
});
