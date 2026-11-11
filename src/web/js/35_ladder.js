/* ── Конструктор облигационной лестницы ── */
S.ladQ={sum:'500000',years:'5',rungs:'',rating:'A',floaters:false,amort:true,monthly:false};
try{const v=JSON.parse(localStorage.getItem('lad_q')||'null');if(v&&typeof v==='object')Object.assign(S.ladQ,v)}catch(e){}
const LAD_RT=['AAA','AA','A','BBB','BB'];
const LAD_MN=['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
function ladRun(){
  const q=S.ladQ;try{localStorage.setItem('lad_q',JSON.stringify(q))}catch(e){}
  const p=new URLSearchParams({sum:String(q.sum||'500000').replace(/\s/g,'').replace(',','.'),years:q.years||'5',min_rating:q.rating||'A',floaters:q.floaters?'1':'0',amort:q.amort?'1':'0',monthly:q.monthly?'1':'0'});
  if(q.rungs)p.set('rungs',q.rungs);
  S.lad={loading:true};render();
  api('/api/ladder?'+p).then(d=>{S.lad={data:d};if(S.page==='lad')render()}).catch(e=>{S.lad={error:e.message};if(S.page==='lad')render()});
}
function ladChart(el){
  const d=S.lad&&S.lad.data;if(!d||!d.cashflow_by_month||!d.cashflow_by_month.length)return emptyChart(el,260,'Нет выплат');
  const cf=d.cashflow_by_month,lb=cf.map(m=>LAD_MN[+m.month.slice(5)-1]+' '+m.month.slice(2,4));
  bars(el,{h:280,stack:true,labels:lb,series:[{n:'Купоны',c:'#3987e5',v:cf.map(m=>m.coupons)},{n:'Погашения и амортизация',c:'#19a070',v:cf.map(m=>m.principal)}],total:true,fa:short,ft:v=>M(v,'rub',0),empty:'Нет выплат'});
}
function ladMonths(a){return a&&a.length?`<span class="ld-mon" title="Месяцы, в которые бумага платит купон">${a.map(m=>LAD_MN[m-1]).join(' ')}</span>`:'<span class="mu">—</span>'}
function ladResult(d){
  const t=d.totals,pr=d.params;
  const kp=`<div class="g g4">${kpi('Вложено',M(t.invested,'rub',0),`${t.bonds} бумаг · ${t.issuers} эмитентов`+(t.free>0?` · свободно ${M(t.free,'rub',0)}`:''),null,S1)}
    ${kpi('Доходность лесенки',t.ytm!=null?pctp(t.ytm,1):'—','средневзвешенная к погашению',null,S3)}
    ${kpi('Дюрация',t.dur!=null?t.dur.toFixed(1).replace('.',',')+' г.':'—','средний срок возврата денег',null,S2)}
    ${kpi('Купоны в месяц',M(t.monthly_avg,'rub',0),`≈ ${M(t.coupon_12m,'rub',0)} за ближайший год`,null,S4)}</div>`;
  const warn=(d.warnings||[]).map(w=>`<div class="msg err">${esc(w)}</div>`).join('');
  let body='';
  d.rungs.forEach((r,i)=>{
    body+=`<tr class="ld-rung"><td class="l" colspan="4">Ступень ${i+1}: срок около ${ddm(r.target_date)}</td><td colspan="2" class="num">${r.bonds.length?M(r.cost,'rub',0):'—'}</td><td colspan="2"></td></tr>`;
    if(!r.bonds.length)body+=`<tr><td class="l mu" colspan="8">Подходящих бумаг не нашлось</td></tr>`;
    r.bonds.forEach(b=>{body+=`<tr data-isin="${esc(b.isin)}" title="Открыть карточку"><td class="l"><b style="font-weight:600">${esc(b.name)}</b>${b.floating?' <span class="tag">флоатер</span>':''}${b.amort?' <span class="tag">аморт</span>':''}<br><small class="mu">${esc(b.isin)}</small></td>
      <td class="l"><span class="tag rt rt-${esc(rBucket(b.rating).split(' ')[0])}">${esc(b.rating)}</span></td><td class="num">${pctp(b.ytm,1)}</td>
      <td class="num">${ddm(b.end_date)}<br><small class="mu">${b.end_kind==='offer'?'оферта':'погашение'}</small></td><td class="num">${b.lots} шт.<br><small class="mu">по ${f2(b.price)} %</small></td><td class="num">${M(b.cost,'rub',0)}<br><small class="mu">${pctp(b.share,1)}</small></td>
      <td class="l">${ladMonths(b.coupon_months)}</td></tr>`});
  });
  chart('ld-cf',ladChart);
  return kp+warn+`<div class="card"><h2>Ступени лесенки<span class="sp">нажмите на строку — карточка выпуска</span></h2><div class="tbl"><table class="ld-tbl"><thead><tr><th class="l">Облигация</th><th class="l">Рейтинг</th><th>Доходность</th><th>Срок</th><th>Куплено</th><th>Стоимость</th><th class="l">Купоны</th></tr></thead><tbody>${body}</tbody></table></div></div>
  <div class="card"><h2>Выплаты по месяцам<span class="sp">купоны и возврат номинала</span></h2><div class="chart" id="ld-cf"></div></div>
  <div class="card ld-notes"><h2>Почему так</h2><div class="note">${d.notes.map(n=>`<p>${esc(n)}</p>`).join('')}<p>Цены и доходности — по данным Мосбиржи на сегодня, расчёт с учётом накопленного купонного дохода и без комиссий; налог не учтён. Состав — справочная подборка, не индивидуальная инвестиционная рекомендация: перед покупкой проверьте эмитентов и условия выпусков.</p></div></div>`;
}
function pLad(){
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
  const g=$('#ld-go');if(!g)return;
  g.onclick=()=>{const q=S.ladQ;q.sum=$('#ld-sum').value;q.years=$('#ld-years').value;q.rungs=$('#ld-rungs').value;q.rating=$('#ld-rt').value;
    q.floaters=$('#ld-fl').checked;q.amort=$('#ld-am').checked;q.monthly=$('#ld-mo').checked;ladRun()};
  ['#ld-sum','#ld-years','#ld-rungs'].forEach(i=>{const e=$(i);if(e)e.onkeydown=ev=>{if(ev.key==='Enter')g.click()}});
}
