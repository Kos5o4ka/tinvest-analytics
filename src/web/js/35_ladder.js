/* ── Лесенка облигаций: «Мой портфель» (куда и когда возвращаются деньги) и конструктор новой лесенки ── */
S.ladTab=lsGet('ta_ladtab')||'my';
S.ladO=Object.assign({offers:true,mode:'sum',gran:'year',how:true,col:{}},(()=>{try{return JSON.parse(localStorage.getItem('ta_ladopt')||'null')||{}}catch(e){return{}}})());
S.ladO.col={};
function ladSaveO(){try{localStorage.setItem('ta_ladopt',JSON.stringify({offers:S.ladO.offers,mode:S.ladO.mode,gran:S.ladO.gran,how:S.ladO.how}))}catch(e){}}
const LAD_TY={redemption:['Погашение',S1],offer:['Пут-оферта',S4],amort:['Амортизация',S3]};
function ladLoadP(){
  if(S.ladPAcc!==S.account){S.ladP=null;S.ladPAcc=S.account}
  if(S.ladP)return;
  const acc=S.account;S.ladP={loading:true};
  api('/api/ladder?'+new URLSearchParams({mode:'portfolio',account:acc})).then(d=>{if(S.account!==acc)return;S.ladP={data:d};if(S.page==='lad')renderSoon()})
    .catch(e=>{if(S.account!==acc)return;S.ladP={error:e.message};if(S.page==='lad')renderSoon()});
}
function ladAvgOf(ps,kind){const a=ps.filter(p=>p.kind===kind),nz=a.map((p,i)=>p.total>0?i:-1).filter(i=>i>=0);if(!nz.length)return 0;const sp=a.slice(nz[0],nz[nz.length-1]+1);return sp.reduce((x,p)=>x+p.total,0)/sp.length}
function ladCallBadge(d,k){if(!d)return'';
  return k==='unknown'?` <span class="tag ld-call" title="Тип оферты не указан. Если это колл эмитента, бумагу могут погасить раньше. Ступень поставлена на погашение.">оферта ${ddm(d)} (тип?)</span>`
    :` <span class="tag ld-call" title="Колл — право эмитента досрочно погасить выпуск. Ступень поставлена на погашение, но деньги могут вернуться раньше.">возможен колл ${ddm(d)}</span>`}
function ladPl(n,f){const a=n%100,b=n%10;return a>10&&a<20?f[2]:b===1?f[0]:b>1&&b<5?f[1]:f[2]}
function ladYears(y){const n=Math.round(y*10)/10;return n.toFixed(1).replace('.',',')+(n>=5?' лет':n>=2?' года':' года')}
function ladTip(ps,view){return i=>{const p=ps[i];if(!p)return'';
  let h=`<b>${esc(p.label)}</b>`+(p.total>0?tipRow('var(--tx2)','Вернётся',M(p.total,'rub',0)+' · '+pctp(p.share,1)):`<div>Выплат нет</div>`);
  Object.keys(LAD_TY).forEach(k=>{if(p.by_type[k]>0)h+=tipRow(LAD_TY[k][1],LAD_TY[k][0],M(p.by_type[k],'rub',0))});
  if(p.items.length){h+='<div style="margin-top:6px;border-top:1px solid var(--line);padding-top:4px"></div>';
    p.items.slice().sort((a,b)=>b.amount-a.amount).slice(0,8).forEach(x=>{h+=tipRow(LAD_TY[x.type][1],x.name,M(x.amount,'rub',0))});
    if(p.items.length>8)h+=`<div>и ещё ${p.items.length-8}…</div>`}
  if(p.callable>0)h+=tipRow('var(--tx2)','из них возможен колл',M(p.callable,'rub',0));
  if(p.flag==='heavy')h+='<div style="color:var(--s4)">Больше 1,5× среднего: «тяжёлый» период</div>';
  return h}}
function ladBars(ps,O){
  const mx=Math.max(1,...ps.map(p=>O.mode==='pct'?p.share:p.total));
  const avg={q:ladAvgOf(ps,'q'),y:ladAvgOf(ps,'y')};
  const val=p=>O.mode==='pct'?p.share:p.total;
  return`<div class="ldb" id="ld-bars">${ps.map((p,i)=>{
    const w=val(p)/mx*100;
    const av=O.mode==='pct'?(avg[p.kind]/(ps.reduce((x,q)=>x+q.total,0)||1)*100):avg[p.kind];
    const seg=Object.keys(LAD_TY).filter(k=>p.by_type[k]>0).map(k=>`<i style="flex:${p.by_type[k]};background:${LAD_TY[k][1]}"></i>`).join('');
    const tag=p.flag==='heavy'?'<span class="ld-fl heavy">тяжёлый</span>':p.flag==='gap'?'<span class="ld-fl gap">пусто</span>':'';
    return`<div class="ldb-row ${p.flag||''} ${p.total>0?'':'z'}" data-i="${i}"><span class="ldb-l">${esc(p.label)}</span>
      <div class="ldb-tr"><div class="ldb-bar" style="width:${w.toFixed(2)}%">${seg}</div>${av>0?`<u class="ldb-avg" style="left:${Math.min(av/mx*100,100).toFixed(2)}%"></u>`:''}</div>
      <span class="ldb-v num">${p.total>0?(O.mode==='pct'?pctp(p.share,1):short(p.total)+' ₽'):'—'}${tag}</span></div>`}).join('')}</div>`}
function ladGroups(ps,O){
  let b='';
  ps.forEach(p=>{
    if(!p.items.length)return;const c=O.col[p.key];
    b+=`<tr class="ld-gh" data-g="${esc(p.key)}"><td class="l" colspan="3"><span class="ld-car">${c?'▸':'▾'}</span> <b>${esc(p.label)}</b> <small class="mu">${p.items.length} ${ladPl(p.items.length,['выплата','выплаты','выплат'])}</small>${p.flag==='heavy'?' <span class="ld-fl heavy">тяжёлый</span>':''}</td><td class="num" colspan="2"><b>${M(p.total,'rub',0)}</b></td><td class="num">${pctp(p.share,1)}</td><td></td></tr>`;
    if(!c)p.items.forEach(x=>{b+=`<tr data-isin="${esc(x.isin)}" title="Открыть карточку выпуска"><td class="l"><b style="font-weight:600">${esc(x.name)}</b><br><small class="mu num">${isinTxt(x.isin)}</small></td>
      <td class="num">${ddm(x.date)}</td><td class="l"><span class="tag" style="color:${LAD_TY[x.type][1]}">${LAD_TY[x.type][0]}</span>${x.n>1?` <small class="mu">×${x.n}</small>`:''}${ladCallBadge(x.call,x.call_kind)}</td><td class="num" colspan="2">${M(x.amount,'rub',0)}</td><td class="num">${pctp(x.pct,1)}</td><td class="num">${x.ytm!=null?pctp(x.ytm,1):'<span class="mu">—</span>'}</td></tr>`});
  });
  return b}
function ladMy(){
  const l=S.ladP,O=S.ladO;
  if(!l||l.loading)return`<div class="card">${waitBox('Собираю графики погашений, оферт и амортизаций по облигациям портфеля…')}</div>`;
  if(l.error)return`<div class="msg err">${esc(l.error)}</div>`;
  const d=l.data;
  if(d.empty)return`<div class="card empty">${svgI('<path d="M3 21h4v-5h4v-5h4V6h6"/>')}<div>В портфеле нет облигаций с известной датой погашения: показывать нечего.<br><small class="mu">Лесенку из новых бумаг можно составить на вкладке «Подобрать лесенку».</small></div></div>`;
  const vk=O.offers&&d.has_offers?'offer':'maturity',V=d.variants[vk]||d.variants.offer||d.variants.maturity,sm=V.summary;
  const ps=O.gran==='quarter'?V.quarter:V.year,nx=sm.next,hv=sm.heavy;
  const kp=`<div class="g g4">${kpi('Средний срок возврата',sm.avg_years!=null?ladYears(sm.avg_years):'—',vk==='offer'&&d.has_offers?'до погашения, для бумаг с пут-офертой — до оферты':'до погашения; взвешен по суммам возврата',null,S1)}
    ${kpi('Ближайший возврат',nx?M(nx.amount,'rub',0):'—',nx?`${ddm(nx.date)} · ${esc(nx.names.slice(0,2).join(', '))}${nx.names.length>2?' и ещё '+(nx.names.length-2):''}`:'нет будущих выплат',null,S3)}
    ${kpi('Самый «тяжёлый» год',hv?pctp(hv.share,0):'—',hv?`${esc(hv.label)}: ${M(hv.total,'rub',0)} — ${hv.flag==='heavy'?'заметно выше среднего':'в пределах нормы'}`:'—',hv&&hv.flag==='heavy'?'neg':null,S4)}
    ${kpi('Пустые годы',sm.gaps.length?esc(sm.gaps.join(', ')):'нет',sm.gaps.length?'в эти годы ничего не возвращается':'между первым и последним годом пропусков нет',null,sm.gaps.length?S8:S6)}</div>`;
  const seg=(k,opts,cur)=>`<div class="seg noprint">${opts.map(([v,t])=>`<button class="${cur===v?'on':''}" data-ld="${k}:${v}">${t}</button>`).join('')}</div>`;
  const ctl=`<div class="ld-ctl noprint">${seg('gran',[['year','По годам'],['quarter','Кварталы, затем годы']],O.gran)}${seg('mode',[['sum','Суммы'],['pct','% портфеля']],O.mode)}
    ${d.has_offers?`<label class="sw"><input type="checkbox" id="ld-offs" ${O.offers?'checked':''}><i></i><div><b>Считать пут-оферты как погашение</b><small>по бумагам с пут-офертой срок — до её даты; колл срок не меняет</small></div></label>`:''}</div>`;
  const leg=Object.keys(LAD_TY).filter(k=>ps.some(p=>p.by_type[k]>0)).map(k=>`<span><i style="background:${LAD_TY[k][1]}"></i>${LAD_TY[k][0]}</span>`).join('');
  const how=`<details class="ld-how" ${O.how?'open':''}><summary>Как читать</summary><ul>
    <li><b>Лесенка</b> — это облигации с разными датами погашения: каждый период часть денег возвращается, и её можно вложить заново или потратить.</li>
    <li><b>Ровные ступени</b> означают, что в каждый период возвращается примерно одинаковая сумма. Так проще реинвестировать: часть денег попадает на рынок и при высоких, и при низких ставках, и риск одного неудачного момента меньше.</li>
    <li><b>Пут-оферта</b> — право держателя предъявить бумагу к выкупу: при включённом переключателе ступень стоит на её дате. <b>Колл</b> — право эмитента погасить выпуск досрочно: решает он, поэтому ступень остаётся на погашении, а бумага помечена «возможен колл».</li>
    <li><b>«Тяжёлый» период</b> (больше 1,5× среднего) — на него приходится непропорционально большая часть денег, <b>пустой</b> — денег не возвращается вовсе. Это описание структуры портфеля, а не оценка бумаг и не рекомендация.</li></ul></details>`;
  return kp+`<div class="card"><h2>Лесенка: сколько денег возвращается${O.gran==='quarter'?' по кварталам и годам':' по годам'}<span class="sp">пунктир — среднее; наведите на ступень, чтобы увидеть выпуски</span></h2>${ctl}
    <div class="ld-leg">${leg}<span class="mu">Всего к возврату: ${M(sm.total,'rub',0)}</span>${sm.callable&&sm.callable.amount>0?`<span class="ld-call-sum" title="Колл — право эмитента досрочно погасить выпуск: такие суммы стоят на дате погашения, но могут вернуться раньше">Может вернуться раньше (колл или оферта без типа): ${M(sm.callable.amount,'rub',0)} · ${pctp(sm.callable.share,1)} · ${sm.callable.count} ${ladPl(sm.callable.count,['выпуск','выпуска','выпусков'])}</span>`:''}</div>${ladBars(ps,O)}${how}</div>
    <div class="card"><h2>Состав по периодам<span class="sp">строка периода сворачивается; нажмите на выпуск — карточка</span></h2><div class="noprint ld-ctl2"><button class="btn ghost" id="ld-cl">Свернуть все</button><button class="btn ghost" id="ld-ex">Развернуть все</button></div>
    <div class="tbl"><table class="ld-tbl" id="ld-det"><thead><tr><th class="l">Облигация</th><th>Дата</th><th class="l">Тип</th><th colspan="2">Сумма</th><th>Доля</th><th>Доходность</th></tr></thead><tbody>${ladGroups(ps,O)}</tbody></table></div>
    <div class="note" style="margin-top:10px;font-size:12px;color:var(--mu)">«Доля» — часть всех будущих возвратов номинала по облигациям портфеля. Суммы — номинал по текущему количеству бумаг (без купонов и налога)${d.undated.length?'; без даты погашения, не вошли: '+esc(d.undated.join(', ')):''}.</div></div>`;
}
S.ladQ={sum:'500000',years:'5',rungs:'',rating:'A',floaters:false,amort:true,monthly:false};
try{const v=JSON.parse(localStorage.getItem('lad_q')||'null');if(v&&typeof v==='object')Object.assign(S.ladQ,v)}catch(e){}
const LAD_RT=['AAA','AA','A','BBB','BB'];
const LAD_MN=['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
function ladRun(){
  const q=S.ladQ;try{localStorage.setItem('lad_q',JSON.stringify(q))}catch(e){}
  const p=new URLSearchParams({sum:String(q.sum||'500000').replace(/\s/g,'').replace(',','.'),years:q.years||'5',min_rating:q.rating||'A',floaters:q.floaters?'1':'0',amort:q.amort?'1':'0',monthly:q.monthly?'1':'0'});
  if(q.rungs)p.set('rungs',q.rungs);
  S.lad={loading:true};render();
  api('/api/ladder?'+p).then(d=>{S.lad={data:d};if(S.page==='lad')renderSoon()}).catch(e=>{S.lad={error:e.message};if(S.page==='lad')renderSoon()});
}
function ladChart(el){
  const d=S.lad&&S.lad.data;if(!d||!d.cashflow_by_month||!d.cashflow_by_month.length)return emptyChart(el,260,'Нет выплат');
  const cf=d.cashflow_by_month,lb=cf.map(m=>LAD_MN[+m.month.slice(5)-1]+' '+m.month.slice(2,4));
  bars(el,{h:280,stack:true,labels:lb,series:[{n:'Купоны',c:'#3987e5',v:cf.map(m=>m.coupons)},{n:'Погашения и амортизация',c:'#19a070',v:cf.map(m=>m.principal)}],total:true,fa:short,ft:v=>M(v,'rub',0),empty:'Нет выплат'});
}
function ladYTip(b){
  if(b.yield_basis==='put')return'Доходность к пут-оферте: держатель сам решает, предъявлять ли бумагу';
  const m=b.ytm_mat!=null?'К погашению: '+pctp(b.ytm_mat,2)+'. ':'';
  if(b.yield_basis==='call')return m+'Показана доходность к худшему (YTW): эмитент может погасить выпуск раньше, колл-даты: '+b.call_dates.map(ddm).join(', ');
  if(b.yield_basis==='unknown')return m+'Тип оферты не указан: показана меньшая из доходностей к дате оферты и к погашению';
  return'Доходность к погашению'}
function ladMonths(a){return a&&a.length?`<span class="ld-mon" title="Месяцы, в которые бумага платит купон">${a.map(m=>LAD_MN[m-1]).join(' ')}</span>`:'<span class="mu">—</span>'}
function ladResult(d){
  const t=d.totals,pr=d.params;
  const kp=`<div class="g g4">${kpi('Вложено',M(t.invested,'rub',0),`${t.bonds} бумаг · ${t.issuers} эмитентов`+(t.free>0?` · свободно ${M(t.free,'rub',0)}`:''),null,S1)}
    ${kpi('Доходность лесенки',t.ytm!=null?pctp(t.ytm,1):'—','по потокам лесенки: до пут-оферты и до погашения',null,S3)}
    ${kpi('Дюрация',t.dur!=null?t.dur.toFixed(1).replace('.',',')+' г.':'—','средний срок возврата денег',null,S2)}
    ${kpi('Купоны в месяц',M(t.monthly_avg,'rub',0),`≈ ${M(t.coupon_12m,'rub',0)} за ближайший год`,null,S4)}</div>`;
  const cal=t.callable_bonds?`<div class="msg ok" style="margin-bottom:10px">Колл или оферта без указанного типа у ${t.callable_bonds} ${ladPl(t.callable_bonds,['бумаги','бумаг','бумаг'])}: ${M(t.callable_cost,'rub',0)} (${pctp(t.callable_share,1)} вложенного) могут вернуться раньше погашения.</div>`:'';
  const warn=cal+(d.warnings||[]).map(w=>`<div class="msg err">${esc(w)}</div>`).join('');
  let body='';
  d.rungs.forEach((r,i)=>{
    body+=`<tr class="ld-rung"><td class="l" colspan="4">Ступень ${i+1}: срок около ${ddm(r.target_date)}</td><td colspan="2" class="num">${r.bonds.length?M(r.cost,'rub',0):'—'}</td><td colspan="2"></td></tr>`;
    if(!r.bonds.length)body+=`<tr><td class="l mu" colspan="8">Подходящих бумаг не нашлось</td></tr>`;
    r.bonds.forEach(b=>{body+=`<tr data-isin="${esc(b.isin)}" title="Открыть карточку"><td class="l"><b style="font-weight:600">${esc(b.name)}</b>${b.floating?' <span class="tag">флоатер</span>':''}${b.amort?' <span class="tag">аморт</span>':''}<br><small class="mu num">${isinTxt(b.isin)}</small></td>
      <td class="l"><span class="tag rt rt-${esc(rBucket(b.rating).split(' ')[0])}">${esc(b.rating)}</span></td><td class="num" title="${esc(ladYTip(b))}">${pctp(b.ytm,1)}<br><small class="mu">${b.yield_basis==='put'?'к пут':b.yield_basis==='call'?'худшая (YTW)':b.yield_basis==='unknown'?'оф.?':'к погаш.'}</small></td>
      <td class="num">${ddm(b.end_date)}<br><small class="mu">${b.end_kind==='offer'?'пут-оферта':'погашение'}</small>${b.call_dates&&b.call_dates.length?ladCallBadge(b.call_dates[0],'call'):b.unk_date?ladCallBadge(b.unk_date,'unknown'):''}</td><td class="num">${b.lots} шт.<br><small class="mu">по ${f2(b.price)} %</small></td><td class="num">${M(b.cost,'rub',0)}<br><small class="mu">${pctp(b.share,1)}</small></td>
      <td class="l">${ladMonths(b.coupon_months)}</td></tr>`});
  });
  chart('ld-cf',ladChart);
  return kp+warn+`<div class="card"><h2>Ступени лесенки<span class="sp">нажмите на строку — карточка выпуска</span></h2><div class="tbl"><table class="ld-tbl"><thead><tr><th class="l">Облигация</th><th class="l">Рейтинг</th><th>Доходность</th><th>Срок</th><th>Куплено</th><th>Стоимость</th><th class="l">Купоны</th></tr></thead><tbody>${body}</tbody></table></div></div>
  <div class="card"><h2>Выплаты по месяцам<span class="sp">купоны и возврат номинала</span></h2><div class="chart" id="ld-cf"></div></div>
  <div class="card ld-notes"><h2>Почему так</h2><div class="note">${d.notes.map(n=>`<p>${esc(n)}</p>`).join('')}<p>Цены и доходности — по данным Мосбиржи на сегодня, расчёт с учётом накопленного купонного дохода и без комиссий; налог не учтён. Состав — справочная подборка, не индивидуальная инвестиционная рекомендация: перед покупкой проверьте эмитентов и условия выпусков.</p></div></div>`;
}
function pLad(){
  const tabs=`<div class="seg noprint" style="margin-bottom:14px;width:fit-content">${[['my','Мой портфель'],['build','Подобрать лесенку']].map(([k,t])=>`<button class="${S.ladTab===k?'on':''}" data-ldtab="${k}">${t}</button>`).join('')}</div>`;
  if(S.ladTab!=='build'){ladLoadP();return tabs+ladMy()}
  return tabs+pLadBuild();
}
function pLadBuild(){
  const q=S.ladQ,l=S.lad;
  const form=`<div class="card"><h2>Параметры лесенки<span class="sp">деньги делятся по ступеням с разными сроками погашения</span></h2><div class="flt ld-form">
    <label class="field"><span>Сумма, ₽</span><input class="in" id="ld-sum" type="text" inputmode="numeric" value="${esc(q.sum)}"></label>
    <label class="field"><span>Горизонт, лет (1–10)</span><input class="in" id="ld-years" type="number" min="1" max="10" step="1" value="${esc(q.years)}"></label>
    <label class="field"><span>Ступеней</span><input class="in" id="ld-rungs" type="number" min="1" max="12" step="1" placeholder="= лет" value="${esc(q.rungs)}"></label>
    <label class="field"><span>Рейтинг не ниже</span><select class="in" id="ld-rt">${LAD_RT.map(r=>`<option${q.rating===r?' selected':''}>${r}</option>`).join('')}</select></label>
    <label class="sw"><input type="checkbox" id="ld-fl" ${q.floaters?'checked':''}><i></i><div><b>Флоатеры</b><small>купон плавает со ставкой</small></div></label>
    <label class="sw"><input type="checkbox" id="ld-am" ${q.amort?'checked':''}><i></i><div><b>Амортизация</b><small>долг гасится частями</small></div></label>
    <label class="sw"><input type="checkbox" id="ld-mo" ${q.monthly?'checked':''}><i></i><div><b>Ровный доход</b><small>купоны в разные месяцы</small></div></label>
    <button class="btn" id="ld-go">Подобрать</button></div></div>`;
  if(!l)return form+`<div class="card empty">Задайте сумму и горизонт и нажмите «Подобрать»: программа составит набор облигаций, которые гасятся по очереди.</div>`;
  if(l.loading)return form+`<div class="card">${waitBox('Подбираю бумаги и считаю выплаты…')}</div>`;
  if(l.error||l.data.error)return form+`<div class="msg err">${esc(l.error||l.data.error)}</div>`;
  return form+ladResult(l.data);
}
function bindLad(){
  document.querySelectorAll('[data-ldtab]').forEach(b=>b.onclick=()=>{S.ladTab=b.dataset.ldtab;lsSet('ta_ladtab',S.ladTab);render()});
  document.querySelectorAll('[data-ld]').forEach(b=>b.onclick=()=>{const[k,v]=b.dataset.ld.split(':');S.ladO[k]=v;ladSaveO();render()});
  const of=$('#ld-offs');if(of)of.onchange=()=>{S.ladO.offers=of.checked;ladSaveO();render()};
  const hw=document.querySelector('.ld-how');if(hw)hw.ontoggle=()=>{S.ladO.how=hw.open;ladSaveO()};
  const bars=$('#ld-bars');if(bars){const d=S.ladP&&S.ladP.data,O=S.ladO;if(d&&!d.empty){const V=d.variants[O.offers&&d.has_offers?'offer':'maturity']||d.variants.offer;bindTip(bars,ladTip(O.gran==='quarter'?V.quarter:V.year))}}
  const det=$('#ld-det');if(det)det.onclick=e=>{const h=e.target.closest('[data-g]');if(!h)return;const k=h.dataset.g;S.ladO.col[k]=!S.ladO.col[k];render()};
  const setAll=v=>{const d=S.ladP&&S.ladP.data;if(!d||d.empty)return;const V=d.variants[S.ladO.offers&&d.has_offers?'offer':'maturity']||d.variants.offer;(S.ladO.gran==='quarter'?V.quarter:V.year).forEach(p=>{S.ladO.col[p.key]=v});render()};
  const cl=$('#ld-cl'),ex=$('#ld-ex');if(cl)cl.onclick=()=>setAll(true);if(ex)ex.onclick=()=>setAll(false);
  const g=$('#ld-go');if(!g)return;
  g.onclick=()=>{const q=S.ladQ;q.sum=$('#ld-sum').value;q.years=$('#ld-years').value;q.rungs=$('#ld-rungs').value;q.rating=$('#ld-rt').value;
    q.floaters=$('#ld-fl').checked;q.amort=$('#ld-am').checked;q.monthly=$('#ld-mo').checked;ladRun()};
  ['#ld-sum','#ld-years','#ld-rungs'].forEach(i=>{const e=$(i);if(e)e.onkeydown=ev=>{if(ev.key==='Enter')g.click()}});
}
