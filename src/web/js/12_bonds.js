/* ── Облигации ── */
/* интенсивность показана лёгким «бейджем» вокруг значения, а не заливкой всей ячейки */
function heatCell(v,mx,rgb,txt){if(bad(v))return'<td class="num mu">—</td>';const a=Math.max(0,Math.min(1,v/(mx||1)));return`<td class="num"><span class="hv" style="background:rgba(${rgb},${(0.05+a*0.15).toFixed(3)})">${txt}</span></td>`}
S.bpre=lsGet('ta_bpre')||'main';
function bondsPreset(k){S.bpre=k;lsSet('ta_bpre',k);render()}
function pBonds(){
  const b=S.bonds;
  if(!b)return`<div class="card">${waitBox('Загружаю параметры облигаций и графики купонов…')}</div>`;
  if(b.error)return`<div class="msg err">${esc(b.error)}</div>`;
  const m=b.metrics,tot=S.data.portfolio.total||1;
  if(!m.count)return'<div class="card empty">В портфеле нет облигаций</div>';
  let rows=b.rows.slice();rows.forEach(r=>{r.rk=r.rating?RSC.indexOf(r.rating.v):null;r.next_d=r.next?r.next[0]:null;r.next_sum=r.next&&r.next[1]!=null?r.next[1]*(r.qty||0):null});const{k,d}=S.bsort;
  rows.sort((a,c)=>{const x=a[k],y=c[k];if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  const mxS=Math.max(...rows.map(r=>r.share||0)),mxY=Math.max(1,...rows.map(r=>Math.min(r.ytm||0,60))),mxD=Math.max(...rows.map(r=>r.dur||0));
  const BC_COLS={
    name:['Облигация','l',r=>`<td>${ident(r,[r.ticker,r.floating?(r.est_coupons?'флоатер · прогноз купонов':'флоатер'):'',r.amort?'амортизация':''].filter(Boolean).join(' · '))}</td>`],
    qty:['Кол-во','',r=>`<td class="num">${f0(r.qty)}</td>`],
    buy_pct:['Покупка, %','',r=>`<td class="num">${r.buy_pct!=null?f2(r.buy_pct):'—'}</td>`],
    price_pct:['Цена, %','',r=>`<td class="num">${r.price_pct!=null?f2(r.price_pct):'—'}</td>`],
    value_rub:['Стоимость','',r=>`<td class="num">${M(r.value_rub,'rub',0)}</td>`],
    pnl_rub:['P&L','',r=>`<td class="num ${cls(r.pnl_rub)}"><span class="arr">${r.pnl_rub>0?'▲':r.pnl_rub<0?'▼':''}</span>${r.pnl_pct!=null?pct(r.pnl_pct,1):'—'}</td>`],
    share:['Доля','',r=>heatCell(r.share,mxS,'201,133,0',pctp(r.share))],
    ytm:['Доходность','',r=>heatCell(r.ytm,mxY,'25,158,112',r.ytm!=null?pctp(r.ytm,2)+(r.to==='offer'?` <small class="mu" title="${r.to_kind==='put'?'к дате пут-оферты':r.to_kind==='call'?'к дате колл — досрочного погашения по решению эмитента':'к дате оферты (тип не указан)'}">${r.to_kind==='put'?'пут':r.to_kind==='call'?'колл':'оф.'}</small>`:'')+(r.cf_source==='approx'?' <small class="mu" title="Приблизительный расчёт: нет графика выплат MOEX">≈</small>':''):'—')],
    ytm_tax:['После НДФЛ','',r=>heatCell(r.ytm_tax,mxY,'25,158,112',r.ytm_tax!=null?pctp(r.ytm_tax,2):'—')],
    spread:['Спред к КБД','',r=>`<td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread)+' п.п.':'—'}</td>`],
    dur:['Дюрация','',r=>heatCell(r.dur,mxD,'213,81,129',r.dur!=null?r.dur.toFixed(2).replace('.',',')+' г':'—')],
    coupon:['Купон','',r=>`<td class="num">${r.coupon!=null?pctp(r.coupon,2):'—'}</td>`],
    next:['След. купон','',r=>`<td class="num">${r.next?`${ddm(r.next[0])}<br><small class="mu">${M(r.next[1])}</small>`:'—'}</td>`],
    next_sum:['Сумма выплаты','',r=>`<td class="num">${r.next&&r.next[1]!=null?M(r.next[1]*(r.qty||0),r.face_cur||'rub',0):'—'}</td>`],
    ctype:['Тип купона','l',r=>`<td class="l">${r.floating?'<span class="tag">флоатер</span>':'<span class="tag">фиксированный</span>'}</td>`],
    amort:['Амортизация','l',r=>`<td class="l">${r.amort?'<span class="tag">да</span>':'<span class="mu">—</span>'}</td>`],
    maturity:['Погашение','',r=>`<td class="num">${r.maturity?ddm(r.maturity):'—'}${r.call?`<br><small class="mu">оферта ${ddm(r.call)}</small>`:''}</td>`],
    rk:['Рейтинг','l',r=>`<td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td>`],
    risk:['Риск','l',r=>`<td class="l">${r.risk?`<span class="tag" style="${r.risk==='высокий'?'color:var(--neg)':r.risk==='низкий'?'color:var(--pos)':''}">${r.risk}</span>`:''}</td>`]};
  const BC_PRE={main:['Основное',['name','price_pct','ytm','coupon','maturity','rk','value_rub']],
    an:['Аналитика',['name','price_pct','ytm','ytm_tax','spread','dur','rk','risk','share']],
    cal:['Календарь',['name','next','next_sum','ctype','amort','maturity','coupon']],
    all:['Все колонки',['name','qty','buy_pct','price_pct','value_rub','pnl_rub','share','ytm','ytm_tax','spread','dur','coupon','next','maturity','rk','risk']]};
  const pre=BC_PRE[S.bpre]?S.bpre:'main',cols=BC_PRE[pre][1];
  const th=cols.map(kk=>{const[t,c]=BC_COLS[kk];const sk=kk==='next'?'next_d':kk==='ctype'?'floating':kk;return`<th class="s ${c||''}" data-s="${sk}">${t} <span>${k===sk?(d>0?'↑':'↓'):''}</span></th>`}).join('');
  const body=rows.map(r=>`<tr data-isin="${esc(r.isin||r.ticker||'')}">${cols.map(kk=>BC_COLS[kk][2](r)).join('')}</tr>`).join('');
  const presetBar=`<div class="seg noprint" style="margin:0 0 10px">${Object.entries(BC_PRE).map(([k2,v])=>`<button class="${k2===pre?'on':''}" onclick="bondsPreset('${k2}')">${v[0]}</button>`).join('')}</div>`;
  const sk=['-3','-2','-1','1','2','3'],st=m.stress||{};
  chart('c-stress',bars,{h:220,labels:sk.map(x=>(x>0?'+':'−')+Math.abs(x)+' п.п.'),series:[{n:'Изменение стоимости',c:S3,v:sk.map(x=>(st[x]||{}).rub||0)}],legend:false,
    colorOf:v=>v>=0?'#19a070':'#d5524a',empty:'Нет данных для стресс-теста'});
  const hy=m.high_yield||[],kr=m.keyrate;
  chart('c-ladder',bars,{h:220,labels:b.ladder.map(x=>x[0]),series:[{n:'Погашается / оферта',c:S1,v:b.ladder.map(x=>x[1])}],legend:false});
  return`<div class="g g4">${kpi('Облигации',M(m.value,'rub',0),`${m.count} выпусков · ${m.issuers} эмитентов · ${pctp(m.value/tot*100)} портфеля`,null,S1)}
    ${kpi('Доходность портфеля (IRR)',pctp(m.irr,2),'что принесёт весь облигационный портфель, если все бумаги заплатят по графику: один IRR по суммарному денежному потоку к текущей стоимости с НКД','pos',S3)}
    ${kpi('IRR после НДФЛ',pctp(m.irr_tax,2),'то же после налога 13% на купоны и разницу к цене; без ЛДВ','pos',S3)}
    ${kpi('Средневзвешенная доходность',pctp(m.ytm,2),`среднее доходностей выпусков по стоимости, включая бумаги с доходностью выше 100%; после НДФЛ ${pctp(m.ytm_tax,2)}`,'pos',S3)}
    ${kpi('Модиф. дюрация',m.mdur!=null?m.mdur.toFixed(2).replace('.',',')+' г':'—','−1% к цене на +1 п.п. ставки ≈ 1 × мод. дюрация',null,S5)}
    ${kpi('Дюрация',m.dur!=null?m.dur.toFixed(2).replace('.',',')+' года':'—','средневзвешенная, по Маколею',null,S5)}
    ${kpi('Текущая купонная доходность',pctp(m.cur_yield,2),'годовой купон / цена',null,S4)}
    ${kpi('Купоны за 12 месяцев',M(m.coupons_12m,'rub',0),'по графику выплат, до налога','pos',S7)}</div>
    <div class="card" style="padding:12px 10px 6px">${presetBar}<div class="tbl" style="max-height:calc(100vh - 240px)"><table id="btab" class="bt"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div></div>
    <div class="g g3"><div class="card"><h2>Лестница погашений и оферт, ₽</h2><div id="c-ladder" class="chart"></div></div>
    <div class="card"><h2>Кредитный риск (оценка брокера)</h2>${hbars(b.risk.map(([n,v])=>({n,v,c:n==='высокий'?S8:n==='низкий'?S3:n==='средний'?S4:'#6f7686',s:pctp(v/(m.value||1)*100)})),S1,null,0)}</div>
    <div class="card"><h2>Тип купона, выпусков</h2>${hbars(b.kinds.map(([n,v],i)=>({n,v,c:PAL[i]})),S1,x=>f0(x.v),1)}</div></div>
    <div class="card"><h2>Стресс-тест ставок: изменение стоимости портфеля облигаций, ₽</h2><div id="c-stress" class="chart"></div>
      <div class="tbl"><table class="bt"><thead><tr><th class="l">Сдвиг ставок</th>${sk.map(x=>`<th>${x>0?'+':'−'}${Math.abs(x)} п.п.</th>`).join('')}</tr></thead><tbody>
      <tr><td class="l">Изменение, ₽</td>${sk.map(x=>`<td class="num ${cls((st[x]||{}).rub)}">${(st[x]||{}).rub!=null?M(st[x].rub,'rub',0):'—'}</td>`).join('')}</tr>
      <tr><td class="l">Изменение, %</td>${sk.map(x=>`<td class="num ${cls((st[x]||{}).pct)}">${(st[x]||{}).pct!=null?pct((st[x]||{}).pct,2):'—'}</td>`).join('')}</tr></tbody></table></div>
      <p class="note">Параллельный сдвиг доходностей всех выпусков с полной переоценкой по графику выплат (для выпусков без данных MOEX, помечены ≈, — по модиф. дюрации). Не учитывает изменения кредитных спредов.</p></div>
    ${ratingsCard(b)}
    ${insightsCard(b)}
    <p class="note">Доходность — эффективная годовая к погашению или к ближайшей оферте (пометка «оф.»), по текущей цене с НКД. Для флоатеров ещё не объявленные купоны оценены как ключевая ставка по прогнозу + спред эмитента (спред взят по последним известным купонам); MOEX считает по неизменному купону, поэтому доходности флоатеров здесь могут отличаться от биржевых. Дюрация — по Маколею, в годах. «После НДФЛ» — упрощённо: 13% с купонов и с положительной разницы между погашением и ценой покупки (без прогрессивной ставки 15% и ЛДВ). Пометка ≈ — график выплат MOEX недоступен, расчёт приблизительный.<br>IRR портфеля — единая ставка дисконтирования всех будущих выплат (купоны, амортизации, погашения и оферты, валютные выпуски по текущему курсу) к стоимости портфеля с НКД; по нему видно, сколько в итоге заработает вся «корзина». Средневзвешенная — просто среднее по выпускам. В обе цифры входят все выпуски без исключений.${hy.length?` Высокий риск дефолта (доходность выше 100%, ${M(m.high_yield_value,'rub',0)}): ${hy.map(o=>esc(o.name)+' '+pctp(o.ytm,0)).join(', ')} — такая ставка показывает цену риска, а не обещанный доход.`:''}${kr&&kr.source!=='none'?`<br>Прогноз ключевой ставки для флоатеров: ${esc(kr.name)}${kr.as_of?`, на ${esc(kr.as_of)}`:''}; сейчас ${kr.key_rate!=null?pctp(kr.key_rate,2):'—'}${(kr.yearly||[]).length?`, средняя по годам: ${kr.yearly.slice(0,4).map(y=>y.year+' — '+pctp(y.mid,1)).join(', ')}`:''}. Источник меняется в «Настройках».`:''}</p>`;
}



