/* ── Риски и сценарии: вероятность дефолта, ожидаемая доходность, сценарии ключевой ставки ── */
S.riskQ={rec:'25',target:'',tax:false,hor:'3'};
try{const v=JSON.parse(localStorage.getItem('rk_hor')||'null');if(v&&+v>0)S.riskQ.hor=String(v)}catch(e){}
S.rsort={k:'value_rub',d:-1};
function loadRisk(){
  if(S._riskLoading)return;S._riskLoading=1;const acc=S.account,q=S.riskQ;
  const p=new URLSearchParams({account:acc,recovery:q.rec||'25',horizon:String(q.hor||'3').replace(',','.')});if(q.target!=='')p.set('target',q.target.replace(',','.'));if(q.tax)p.set('tax','1');
  api('/api/risk?'+p).then(j=>{S._riskLoading=0;if(S.account!==acc)return;S.risk=j;S.riskAcc=acc;if(S.page==='risk')renderSoon()})
   .catch(e=>{S._riskLoading=0;S.risk={error:e.message};S.riskAcc=acc;if(S.page==='risk')renderSoon()});
}
const rkPd=x=>x==null?'—':x*100<0.1?'&lt;0,1 %':pctp(x*100,x*100<10?1:0);
const rkRub=(v,d=0)=>bad(v)?'—':INCOG.on?MASK+' ₽':(v>0?'+':v<0?'−':'')+NF0.format(Math.abs(v))+' ₽';
const rkPct=(v,d=1)=>bad(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',')+' %';
function rkScnChart(el){
  const d=S.risk;if(!d||!d.scenarios)return;
  bars(el,{h:260,stack:true,labels:d.scenarios.map(s=>s.name),series:[{n:'Купоны (получено за год)',c:'#3987e5',v:d.scenarios.map(s=>d.scn_total[s.key].coupons)},
    {n:'Изменение цены (переоценка, подтягивание к номиналу)',c:'#19a070',v:d.scenarios.map(s=>d.scn_total[s.key].price)}],total:true,fa:short,ft:v=>rkRub(v),empty:'Нет данных'});
}
function rkFloatText(d){
  const f=d.floaters.floating,x=d.floaters.fixed;
  if(!f.count||!x.count)return f.count?'В портфеле только флоатеры.':'В портфеле нет флоатеров: все выпуски с фиксированным купоном.';
  const fw=[],xw=[];d.scenarios.forEach(s=>{const a=f.scn[s.key].pct,b=x.scn[s.key].pct;(a>=b?fw:xw).push(s.name)});
  let t='';if(fw.length)t+=`Флоатеры выигрывают в сценариях: ${fw.join(', ')}. `;if(xw.length)t+=`Фиксированный купон выигрывает в сценариях: ${xw.join(', ')}. `;
  return t+'Логика: при росте ставки купон флоатера растёт вместе с ней, а цена фиксированных бумаг падает; при снижении ставки фиксированные дорожают, а купон флоатера уменьшается.';
}
function rkRows(d){
  const g={name:r=>r.name,value_rub:r=>r.value_rub,rating:r=>r.rating?RSC.indexOf(r.rating.v):null,ytm:r=>r.ytm,pd_mkt_1y:r=>r.pd_mkt_1y,pd_mkt_T:r=>r.pd_mkt_T,pd_hist_1y:r=>r.pd_hist_1y,
    ratio:r=>r.ratio,ey_hist:r=>r.ey_hist,breakeven:r=>r.breakeven==null&&r.be_gt?99:r.breakeven}[S.rsort.k]||(r=>r.value_rub);
  return d.rows.slice().sort((a,b)=>{const x=g(a),y=g(b);if(typeof x==='string'||typeof y==='string')return S.rsort.d*String(x||'').localeCompare(String(y||''));return S.rsort.d*((x??-Infinity)-(y??-Infinity))});
}
const rkYr=v=>bad(v)?'—':v.toFixed(1).replace('.',',')+' г.';
function rkDurBlock(d){
  const u=d.duration,r=d.real;if(!u&&!r)return'';
  const gk=u?(u.kind==='match'?'':u.kind==='long'?'neg':''):'';
  const gp=u?(u.gap>0?'+':u.gap<0?'−':'')+Math.abs(u.gap).toFixed(1).replace('.',',')+' г.':'';
  const kp=`<div class="g g4">${u?kpi('Дюрация портфеля',rkYr(u.mac),`модифицированная: ${rkYr(u.mod)}`,null,S1):''}
    ${u?kpi('Дюрационный разрыв',gp,`дюрация − горизонт ${rkYr(u.goal)}`,gk,S4):''}
    ${r?kpi('Реальная доходность',pctp(r.real,1),`до налога: ${pctp(r.irr,1)} − инфляция ${pctp(r.inflation,1)}${r.estimate?' (оценка)':''}`,r.real<0?'neg':'',S3):''}
    ${r&&r.real_tax!=null?kpi('Реальная после НДФЛ',pctp(r.real_tax,1),`номинальная после налога: ${pctp(r.irr_tax,1)}`,r.real_tax<0?'neg':'',S2):''}</div>`;
  const tx=u?`<p><b>Срок и ставки.</b> ${esc(u.text)} Дюрация портфеля облигаций — ${rkYr(u.mac)}, горизонт цели — ${rkYr(u.goal)}</p>`:'';
  const rt=r?`<p><b>Реальная доходность</b> — сколько вы зарабатываете сверх роста цен: (1 + доходность) / (1 + инфляция) − 1. Доходность портфеля (IRR) ${pctp(r.irr,1)}, ожидаемая инфляция в среднем за ${rkYr(r.years)} — ${pctp(r.inflation,1)} ${r.estimate?'(прогноз Банка России недоступен, взята оценка 4 %)':'(прогноз Банка России'+(r.as_of?' от '+ddm(r.as_of):'')+')'}.</p>`:'';
  return`<div class="card"><h2>Срок цели и реальная доходность<span class="sp">дюрационный разрыв, инфляция</span></h2>${kp}<div class="note rk-dur" style="margin-top:10px">${tx}${rt}
    <p>Справочная оценка по упрощённой модели, не инвестиционная рекомендация. Доходность выпусков с аномально высокой ставкой завышает общий показатель.</p></div></div>`;
}
function pRisk(){
  if(S.risk&&S.riskAcc!==S.account)S.risk=null;
  if(!S.risk){loadRisk();return`<div class="card">${waitBox('Считаю вероятности дефолта и сценарии ставки (потоки по каждому выпуску)…')}</div>`}
  const d=S.risk,q=S.riskQ;
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="rk-apply">Повторить</button></div>`;
  const ctl=`<div class="card"><h2>Параметры</h2><div class="flt rk-ctl">
    <label class="field"><span>Доля возврата при дефолте, %</span><input class="in" id="rk-rec" type="number" min="0" max="90" step="5" value="${esc(q.rec)}"></label>
    <label class="field"><span>Своя ключевая ставка через 12 мес., %</span><input class="in" id="rk-tgt" type="number" min="0" max="60" step="0.5" placeholder="например 12" value="${esc(q.target)}"></label>
    <label class="field"><span>Горизонт цели, лет</span><input class="in" id="rk-hor" type="number" min="0.5" max="50" step="0.5" value="${esc(q.hor)}"></label>
    <label class="sw"><input type="checkbox" id="rk-tax" ${q.tax?'checked':''}><i></i><div><b>Учесть НДФЛ 13 %</b><small>на купоны и прирост цены</small></div></label>
    <button class="btn" id="rk-apply">Пересчитать</button></div></div>`;
  if(!d.portfolio)return ctl+'<div class="card empty">В портфеле нет облигаций с рассчитанной доходностью</div>';
  const p=d.portfolio,sc=d.scenarios,tt=d.scn_total;
  const worst=sc.reduce((a,s)=>tt[s.key].total<tt[a.key].total?s:a,sc[0]);
  const hasEx=p.promised_ex!=null&&p.distressed_value>0;
  const kp=`<div class="g g4">${kpi('Обещанная доходность',pctp(p.promised,1),hasEx?`без выпусков с доходностью &gt;100 %: ${pctp(p.promised_ex,1)}`:'средневзвешенная к погашению',null,S1)}
    ${kpi('Ожидаемая с учётом дефолтов',pctp(p.expected,1),`по рейтингу: −${f2(p.promised-p.expected)} п.п. · по рынку: ${pctp(p.expected_mkt,1)}`,null,S3)}
    ${kpi('Ожидаемые потери за год',M(-p.exp_loss_rub,'rub',0),`по рынку: ${M(-p.exp_loss_mkt_rub,'rub',0)}`,'neg',S8)}
    ${kpi('Худший сценарий ставки',rkRub(tt[worst.key].total),`${esc(worst.name)} · ${rkPct(tt[worst.key].pct)} за год`,tt[worst.key].total<0?'neg':'',S4)}</div>`;
  const hd=d.horizon?ddm(d.horizon):'';
  const scT=`<div class="tbl"><table><thead><tr><th class="l">Сценарий</th><th>Ставка через 12 мес.</th><th>Δ к текущей</th><th>Купоны</th><th>Цена</th><th>Итого, ₽</th><th>Итого, %</th></tr></thead><tbody>${
    sc.map(s=>{const t=tt[s.key];return`<tr><td class="l">${esc(s.name)}${s.note?`<br><small class="mu">${esc(s.note)}</small>`:''}</td><td class="num">${pctp(s.k12,1)}</td><td class="num ${cls(-s.delta)}">${s.delta>0?'+':s.delta<0?'−':''}${Math.abs(s.delta).toFixed(1).replace('.',',')} п.п.</td>
      <td class="num">${rkRub(t.coupons)}</td><td class="num ${cls(t.price)}">${rkRub(t.price)}</td><td class="num ${cls(t.total)}"><b>${rkRub(t.total)}</b></td><td class="num ${cls(t.pct)}">${rkPct(t.pct)}</td></tr>`}).join('')}</tbody></table></div>`;
  const fl=d.floaters,fT=`<div class="tbl"><table><thead><tr><th class="l">Сценарий</th><th>Флоатеры (${fl.floating.count})</th><th>Фиксированный купон (${fl.fixed.count})</th><th>Победитель</th></tr></thead><tbody>${
    sc.map(s=>{const a=fl.floating.scn[s.key].pct,b=fl.fixed.scn[s.key].pct,w=fl.floating.count&&fl.fixed.count?(a>=b?'флоатеры':'фиксированные'):'—';
      return`<tr><td class="l">${esc(s.name)}</td><td class="num ${cls(a)}">${rkPct(a)}</td><td class="num ${cls(b)}">${rkPct(b)}</td><td class="num">${w}</td></tr>`}).join('')}</tbody></table></div>`;
  const cs=d.casino.length?`<div class="tbl"><table><thead><tr><th class="l">Дефолт k самых рискованных эмитентов</th><th>Потеряно на дефолте</th><th>Итог за год, ₽</th><th>Итог за год, %</th></tr></thead><tbody>${
    d.casino.map(c=>`<tr><td class="l"><b>k = ${c.k}</b><br><small class="mu">${c.issuers.map(i=>esc(i.name)+' ('+M(i.value,'rub',0)+')').join('; ')}</small></td><td class="num neg">${rkRub(-c.lost_rub)}</td>
      <td class="num ${cls(c.result_rub)}"><b>${rkRub(c.result_rub)}</b></td><td class="num ${cls(c.result_pct)}">${rkPct(c.result_pct)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">Недостаточно эмитентов</div>';
  const cols=[['name','Облигация','l'],['value_rub','Стоимость'],['rating','Рейтинг','l'],['ytm','Доходность'],['pd_mkt_1y','PD рынка, 1 год'],['pd_mkt_T','PD рынка, до погашения'],['pd_hist_1y','PD по рейтингу, 1 год'],['ratio','Рынок / рейтинг'],['ey_hist','Ожидаемая доходность'],['breakeven','Запас по росту доходности']];
  const th=cols.map(([k,t,c])=>`<th class="s ${c||''}" data-s="${k}">${t} <span>${S.rsort.k===k?(S.rsort.d>0?'↑':'↓'):''}</span></th>`).join('');
  const body=rkRows(d).map(r=>{
    const flag=r.ratio!=null&&r.ratio>=3?`<br><small class="neg" title="Рыночный спред закладывает вероятность дефолта заметно выше, чем следует из рейтинга: сигнал проблем у эмитента либо возможность">рынок закладывает риск в ${r.ratio>=10?Math.round(r.ratio):f2(r.ratio).replace(',0','')} раз выше рейтинга</small>`:'';
    const be=r.breakeven!=null?f2(r.breakeven)+' п.п.':(r.be_gt?'&gt; 30 п.п.':'—');
    return`<tr data-isin="${esc(r.isin||r.ticker||'')}"><td class="l">${esc(r.name)}<br><small class="mu">${esc(r.isin||'')}${r.floating?' · флоатер':''}${r.exact?'':' · приближённо'}</small></td>
      <td class="num">${M(r.value_rub,'rub',0)}</td><td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td><td class="num">${pctp(r.ytm,1)}</td>
      <td class="num">${rkPd(r.pd_mkt_1y)}</td><td class="num">${rkPd(r.pd_mkt_T)}</td><td class="num">${r.pd_hist_1y!=null?rkPd(r.pd_hist_1y):'<span class="mu">нет рейтинга</span>'}</td>
      <td class="num">${r.ratio!=null?(r.ratio>=10?Math.round(r.ratio):f2(r.ratio))+' ×':'—'}${flag}</td>
      <td class="num ${r.ey_hist<0?'neg':''}">${pctp(r.ey_hist,1)}${r.hist_basis==='market'?' <small class="mu" title="Нет рейтинга: использована рыночная вероятность дефолта">*</small>':''}</td><td class="num" title="${r.be_approx!=null?'Грубая оценка доходность / модифицированная дюрация сегодня: '+f2(r.be_approx)+' п.п. Точный расчёт учитывает, что через год дюрация короче.':''}">${be}</td></tr>`}).join('');
  chart('rk-scn',rkScnChart);
  return ctl+kp+rkDurBlock(d)+`<div class="card"><h2>Сценарии ключевой ставки<span class="sp">доход за 12 месяцев (до ${hd}), без реинвестирования купонов</span></h2><div class="chart" id="rk-scn"></div>${scT}
    <p class="note" style="margin-top:10px">Сдвиг кривой доходности = Δ ключевой ставки × β: β = 1,0 для срока до 1 года и линейно снижается до 0,5 на сроке 7 лет и дольше (длинные ставки реагируют слабее). Кредитные спреды не меняются. Выпуск переоценивается через 12 месяцев: оставшиеся потоки дисконтируются по текущей доходности со сдвигом на дюрации остатка. Купоны флоатеров следуют траектории ставки сценария плюс спред эмитента; ставка идёт линейно к целевой за 12 месяцев. Сценарий «Рынок» доступен, если получен рыночный путь ставки.</p></div>
  <div class="g c-2-1 rk-g"><div class="card"><h2>Флоатеры против фиксированного купона<span class="sp">доходность подпортфелей за 12 месяцев</span></h2>${fT}<p class="note" style="margin-top:10px">${esc(rkFloatText(d))}</p></div>
  <div class="card"><h2>Стресс-тест дефолтов: если эмитенты не вернут долг</h2>${cs}<p class="note" style="margin-top:10px">Дефолтят самые рискованные эмитенты по рыночной вероятности. Потеря = (1 − возврат ${d.recovery.toFixed(0)} %) × стоимость позиций эмитента; купоны по ним за год не учитываются. База — сценарий «ставка без изменений» (${rkRub(d.base_rub)}).</p></div></div>
  <div class="card"><h2>Выпуски: риск дефолта и запас прочности<span class="sp">нажмите на строку — карточка выпуска; заголовок — сортировка</span></h2><div class="tbl rk-tbl"><table id="rk-tab"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div>
    <p class="note" style="margin-top:10px">PD рынка: из спреда к КБД s и доли возврата R: λ = s / (1 − R), PD(T) = 1 − e<sup>−λT</sup>. Ожидаемая доходность = доходность − PD по рейтингу (1 год) × (1 − R). Без рейтинга (*) берётся рыночная PD. Запас — на сколько п.п. должна вырасти доходность, чтобы убрать результат года (купоны + переоценка) в ноль; для коротких и плавающих бумаг запас велик.</p></div>
  <div class="card"><h2>Допущения и источники</h2><p class="note">${esc(d.sources.pd)}<br><br>${esc(d.sources.recovery)}<br><br>Таблица PD по рейтингу, % за год: ${Object.entries(d.pd_hist_table).map(([k,v])=>k+' '+String(v).replace('.',',')).join(' · ')}.
    <br><br>Оценки по упрощённой модели, справочная информация, не инвестиционная рекомендация. Рыночная PD включает премию за ликвидность и риск, поэтому её завышенное значение не всегда означает близкий дефолт.</p></div>`;
}
function bindRisk(){
  const a=$('#rk-apply');
  if(a)a.onclick=()=>{const q=S.riskQ;if($('#rk-rec'))q.rec=$('#rk-rec').value||'25';if($('#rk-tgt'))q.target=$('#rk-tgt').value;if($('#rk-tax'))q.tax=$('#rk-tax').checked;if($('#rk-hor')){q.hor=$('#rk-hor').value||'3';try{localStorage.setItem('rk_hor',JSON.stringify(q.hor))}catch(e){}}S.risk=null;render()};
  ['#rk-rec','#rk-tgt','#rk-hor'].forEach(i=>{const e=$(i);if(e)e.onkeydown=ev=>{if(ev.key==='Enter')a.click()}});
  const t=$('#rk-tab');if(t)t.querySelector('thead').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;S.rsort={k,d:S.rsort.k===k?-S.rsort.d:(k==='name'?1:-1)};render()};
}
