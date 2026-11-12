/* ── Мониторинг: тревоги по портфелю, ликвидность, спреды ── */
const MON_SEV={high:['Высокая','mon-h'],medium:['Средняя','mon-m'],info:['Инфо','mon-i']};
function monEnsure(){
  const acc=S.account,m=S.mon;
  if(m&&m.acc===acc&&(m.loading||m.error||(m.data&&Date.now()-m.t<6e5)))return;
  S.mon={acc,loading:true,t:Date.now()};
  api('/api/monitor?'+new URLSearchParams({account:acc})).then(d=>{if(S.account!==acc)return;S.mon={acc,data:d,t:Date.now()};
    try{notifyMon(d)}catch(e){}
    if(['mon','dash'].includes(S.page))renderSoon()}).catch(e=>{if(S.account!==acc)return;S.mon={acc,error:e.message,t:Date.now()};if(S.page==='mon')renderSoon()});
}
function monSpark(sp,w=96,h=26){
  if(!sp||sp.length<3)return'<span class="mu">—</span>';
  const v=sp.map(p=>p[1]),mn=Math.min(...v),mx=Math.max(...v),r=mx-mn||1;
  const pts=v.map((y,i)=>(i/(v.length-1)*(w-2)+1).toFixed(1)+','+(h-3-(y-mn)/r*(h-6)).toFixed(1)).join(' ');
  const up=v[v.length-1]-v[0],c=up>0.3?'var(--neg)':up<-0.3?'var(--pos)':'var(--tx2)';
  return`<svg class="mon-sp" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><title>Спред к КБД за ${sp.length} торг. дней: ${f2(v[0])} → ${f2(v[v.length-1])} п.п.</title><polyline fill="none" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" points="${pts}"/></svg>`;
}
function monAlertHtml(a){
  const[s,c]=MON_SEV[a.severity]||MON_SEV.info,n=(a.isins||[]).length;
  const nm=a.kind==='rating'?`${esc(a.name)}${n?` <small class="mu">· ${esc((a.bonds||[]).slice(0,2).join(', '))}${n>2?' и ещё '+(n-2):''}</small>`:''}`:esc(a.name||'');
  return`<div class="mon-al ${c}" ${a.isin?`data-isin="${esc(a.isin)}"`:''}><span class="mon-sev">${s}</span><span class="mon-d num"${a.asof?' title="Состояние на сегодня: дата события не публикуется"':''}>${a.asof?'сейчас':a.date?ddm(a.date):''}</span>
    <div class="mon-b"><b>${nm}</b><span>${esc(a.message)}</span></div>${a.url?`<a href="${esc(a.url)}" target="_blank" rel="noopener" title="Источник">↗</a>`:''}</div>`;
}
function monCard(){
  if(!(S.bonds&&S.bonds.rows&&S.bonds.rows.length))return'';
  monEnsure();
  const m=S.mon;
  if(!m||m.loading)return`<div class="card mon-card noprint"><h2>Тревоги<span class="sp">загружаю…</span></h2><div class="mu" style="font-size:12.5px">Проверяю рейтинги, цены и спреды облигаций портфеля</div></div>`;
  if(m.error||!m.data)return'';
  const al=m.data.alerts.filter(a=>a.severity!=='info'),top=al.slice(0,3);
  return`<div class="card mon-card noprint"><h2>Тревоги<span class="sp">${m.data.summary.high} высоких · ${m.data.summary.medium} средних</span>
    <button class="btn ghost" data-go="mon" style="margin-left:auto;padding:4px 12px;font-size:12px">Мониторинг</button></h2>
    ${top.length?top.map(monAlertHtml).join('')+(al.length>3?`<div class="mu" style="font-size:12px;margin-top:6px">…и ещё ${al.length-3}</div>`:''):'<div class="mon-ok">Значимых тревог по облигациям портфеля нет</div>'}</div>`;
}
function monRatingTag(r){
  if(!r||!r.v)return'<span class="mu">—</span>';
  return`<span class="tag rt rt-${rBucket(r.v).split(' ')[0]}" title="${esc(r.agency||'')}">${esc(r.v)}</span>`
    +(r.outlook?` <small class="${r.neg?'neg':'mu'}">${esc(r.outlook)}</small>`:'')+(r.watch?' <span class="tag mon-w" title="Рейтинг под наблюдением">набл.</span>':'');
}
function pMon(){
  monEnsure();
  const m=S.mon;
  if(!m||m.loading)return`<div class="card">${waitBox('Собираю рейтинговые события, историю цен и спредов… При первом запуске до минуты.')}</div>`;
  if(m.error)return`<div class="msg err">${esc(m.error)} <button class="btn ghost" id="mon-r">Повторить</button></div>`;
  const d=m.data,th=d.thresholds,sm=d.summary;
  const rows=d.rows.map(r=>`<tr data-isin="${esc(r.isin)}" title="Открыть карточку"><td class="l"><b style="font-weight:600">${esc(r.name)}</b><br><small class="mu">${esc(r.ticker||r.isin)}${r.call?' · оферта '+ddm(r.call):''}${r.maturity?' · погашение '+ddm(r.maturity):''}</small></td>
    <td class="num">${M(r.value_rub,'rub',0)}</td><td class="l">${monRatingTag(r.rating)}</td>
    <td class="num">${r.price!=null?f2(r.price):'—'}</td>
    <td class="num ${cls(r.chg5)}">${r.chg5!=null?pct(r.chg5,1):'—'}</td><td class="num ${cls(r.chg30)}">${r.chg30!=null?pct(r.chg30,1):'—'}</td>
    <td class="num">${r.spread!=null?(r.spread>40?`<span title="Доходность по такой цене нерепрезентативна (бумага торгуется как дефолтная): ${f2(r.spread)} п.п.">&gt;40</span>`:(r.spread>0?'+':'')+f2(r.spread)):'—'}</td>
    <td class="num ${r.spread_chg30>0?'neg':r.spread_chg30<0?'pos':''}">${r.spread_chg30!=null?(r.spread_chg30>0?'+':'')+f2(r.spread_chg30):'—'}</td>
    <td>${r.floating?'<small class="mu">флоатер</small>':monSpark(r.spark)}</td>
    <td class="num">${r.turnover_avg!=null?short(r.turnover_avg)+' ₽':'—'}</td>
    <td class="num ${r.days_to_sell==null?(r.no_history?'mu':'neg'):r.days_to_sell>th.mon_sell_days?'neg':''}">${r.no_history?'—':r.days_to_sell==null?'∞':(r.days_to_sell<0.01?'<0,01':f2(r.days_to_sell))}</td>
    <td class="l">${(r.flags||[]).map(f=>`<span class="tag" style="color:var(--neg)">${esc(f)}</span>`).join(' ')}</td></tr>`).join('');
  const fld=(k,t,min,step)=>`<label class="field"><span>${t}</span><input class="in num" id="mt-${k}" type="number" min="${min}" step="${step}" value="${th[k]}"></label>`;
  return`<div class="g g4">${kpi('Высокие',sm.high,'понижение рейтинга, дефолт, сильное падение','neg',S8)}${kpi('Средние',sm.medium,'наблюдение, оферты, умеренное падение','',S4)}
    ${kpi('Информационные',sm.info,'повышения, неликвидность, прогнозы',null,S1)}${kpi('Журнал рейтингов',d.log.events,d.log.since?'событий с '+ddm(d.log.since):'пока пуст',null,S2)}</div>
  ${(d.notes||[]).map(n=>`<div class="msg">${esc(n)}</div>`).join('')}
  <div class="card"><h2>Тревоги<span class="sp">рейтинговые действия — за 90 дней; цены и спреды — по последним торгам; погашения, амортизации и оферты — ближайшие ${Math.max(+th.mon_offer_days||30,30)} дн., даты Мосбиржи</span><button class="btn ghost" id="mon-r" style="margin-left:auto;padding:4px 12px;font-size:12px">Обновить</button></h2>
    ${d.alerts.length?d.alerts.slice(0,S.monAll?999:12).map(monAlertHtml).join('')+(d.alerts.length>12?`<button class="btn ghost" id="mon-all" style="margin-top:6px">${S.monAll?'Свернуть':'Показать все ('+d.alerts.length+')'}</button>`:''):'<div class="mon-ok">Тревог нет</div>'}</div>
  ${watchMonGroup()}
  <div class="card"><h2>Облигации портфеля<span class="sp">цены Мосбиржи, спред — доходность минус КБД на дюрации бумаги</span></h2>
    <div class="tbl"><table id="mon-tab"><thead><tr><th class="l">Облигация</th><th>Стоимость</th><th class="l">Рейтинг · прогноз</th><th>Цена, %</th><th>Δ 5 дн.</th><th>Δ 30 дн.</th>
    <th>Спред, п.п.</th><th>Δ спреда 30 дн.</th><th>Спред 90 дн.</th><th>Оборот в день</th><th title="Стоимость позиции / (20 % среднего дневного оборота за 30 дней)">Дней на продажу</th><th class="l">Признаки</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="note" style="margin-top:10px">Оборот — среднее за 30 дней по торговым дням (${d.cal_days} дн.). «Дней на продажу» — сколько дней потребуется, чтобы продать позицию, забирая не более 20 % дневного оборота. Время расчёта: ${d.timings.total} с.</p></div>
  <details class="card"><summary style="cursor:pointer;font-weight:600;color:var(--tx2)">Пороги тревог</summary><div class="mon-th">
    ${fld('mon_drop5','Падение цены за 5 дней, %',0.1,0.5)}${fld('mon_drop30','Падение цены за 30 дней, %',0.1,0.5)}${fld('mon_spread30','Рост спреда за 30 дней, п.п.',0.1,0.5)}
    ${fld('mon_sell_days','Неликвид: дней на продажу более',0.5,0.5)}${fld('mon_offer_days','Оферта: за сколько дней предупреждать',1,1)}
    <button class="btn" id="mon-save" style="align-self:flex-end">Сохранить</button></div>
    <p class="note" style="margin-top:10px">Вдвое превышенный порог даёт высокую важность. Что программа не видит: факт оплаты купона (биржа его не публикует). Дефолт определяется по флагам Мосбиржи, дефолтному рейтингу (D, C) и остановке торгов.</p></details>`;
}
function bindMon(){
  const r=$('#mon-r');if(r)r.onclick=()=>{S.mon=null;render()};
  const al=$('#mon-all');if(al)al.onclick=()=>{S.monAll=!S.monAll;render()};
  const sv=$('#mon-save');
  if(sv)sv.onclick=async()=>{const b={};['mon_drop5','mon_drop30','mon_spread30','mon_sell_days','mon_offer_days'].forEach(k=>b[k]=$('#mt-'+k).value);
    sv.disabled=true;try{await post('/api/config',b);S.cfg=await api('/api/config')}catch(e){}S.mon=null;render()};
}
