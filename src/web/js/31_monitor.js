/* ── Мониторинг: тревоги по портфелю, ликвидность, спреды ── */
const MON_SEV={high:['Высокая','mon-h','neg'],medium:['Средняя','mon-m','warn'],info:['Инфо','mon-i','mu']};
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
  const[s,c,dot]=MON_SEV[a.severity]||MON_SEV.info,n=(a.isins||[]).length;
  const nm=a.kind==='rating'?`${esc(a.name)}${n?` <small class="mu">· ${esc((a.bonds||[]).slice(0,2).join(', '))}${n>2?' и ещё '+(n-2):''}</small>`:''}`:esc(a.name||'');
  const au=safeUrl(a.url);
  return`<div class="st-row mon-al ${c}" ${a.isin?`data-isin="${esc(a.isin)}"`:''}><span class="st-dot ${dot}"></span><span class="mon-sev">${s}</span><span class="mon-d num"${a.asof?' title="Состояние на сегодня: дата события не публикуется"':''}>${a.asof?'сейчас':a.date?ddm(a.date):''}</span>
    <div class="mon-b"><b>${nm}</b><span>${esc(a.message)}</span></div>${au?`<a href="${esc(au)}" target="_blank" rel="noopener" title="Источник">↗</a>`:''}</div>`;
}
function monTile(lbl,val,sub,dot,cls){
  return`<div class="st-tile"><div class="st-tl"><span>${lbl}</span><span class="st-dot ${dot||'mu'}"></span></div><div class="st-tv num ${cls||''}">${val}</div><div class="st-ts">${sub||'&nbsp;'}</div></div>`;
}
function monCard(){
  if(!(S.bonds&&S.bonds.rows&&S.bonds.rows.length))return'';
  monEnsure();
  const m=S.mon;
  if(!m||m.loading)return`<section class="st-card mon-card noprint"><header class="st-gh"><h3>Тревоги</h3><span>загружаю…</span></header><div class="st-callout">Проверяю рейтинги, цены и спреды облигаций портфеля…</div></section>`;
  if(m.error||!m.data)return'';
  const al=m.data.alerts.filter(a=>a.severity!=='info'),top=al.slice(0,3);
  return`<section class="st-card mon-card mon-v2-card noprint"><header class="st-gh"><h3>Тревоги</h3><span>${m.data.summary.high} высоких · ${m.data.summary.medium} средних</span>
    <button class="btn ghost" data-go="mon" style="margin-left:10px;padding:4px 12px;font-size:12px">Мониторинг</button></header>
    ${top.length?top.map(monAlertHtml).join('')+(al.length>3?`<div class="st-line">…и ещё ${al.length-3}</div>`:''):'<div class="st-callout">Значимых тревог по облигациям портфеля нет.</div>'}</section>`;
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
  if(m.error)return`<div class="st-callout warn">${esc(m.error)} <button class="btn ghost" id="mon-r">Повторить</button></div>`;
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
  const thRow=(k,t,sub,min,step)=>`<div class="st-row"><div class="st-t"><b>${t}</b><small>${sub}</small></div><div class="st-c"><input class="in num st-num" id="mt-${k}" type="number" min="${min}" step="${step}" value="${th[k]}"></div></div>`;
  return`<div class="st-tiles">${monTile('Высокие',sm.high,'понижение рейтинга, дефолт, сильное падение',sm.high?'neg':'pos',sm.high?'neg':'')}${monTile('Средние',sm.medium,'наблюдение, оферты, умеренное падение',sm.medium?'warn':'mu')}
    ${monTile('Информационные',sm.info,'повышения, неликвидность, прогнозы','mu')}${monTile('Журнал рейтингов',d.log.events,d.log.since?'событий с '+ddm(d.log.since):'пока пуст',d.log.events?'pos':'mu')}</div>
  ${(d.notes||[]).map(n=>`<div class="st-callout">${esc(n)}</div>`).join('')}
  <section class="st-card mon-v2-card"><header class="st-gh"><h3>Тревоги</h3><span>рейтинги — 90 дн. · оферты — ближайшие ${Math.max(+th.mon_offer_days||30,30)} дн.</span><button class="btn ghost" id="mon-r" style="margin-left:10px;padding:4px 12px;font-size:12px">Обновить</button></header>
    ${d.alerts.length?d.alerts.slice(0,S.monAll?999:12).map(monAlertHtml).join('')+(d.alerts.length>12?`<div class="st-foot"><button class="btn ghost" id="mon-all">${S.monAll?'Свернуть':'Показать все ('+d.alerts.length+')'}</button></div>`:''):'<div class="st-callout">Значимых тревог нет.</div>'}</section>
  ${watchMonGroup()}
  <div class="card"><h2>Облигации портфеля<span class="sp">цены Мосбиржи, спред — доходность минус КБД на дюрации бумаги</span></h2>
    <div class="tbl"><table id="mon-tab"><thead><tr><th class="l">Облигация</th><th>Стоимость</th><th class="l">Рейтинг · прогноз</th><th>Цена, %</th><th>Δ 5 дн.</th><th>Δ 30 дн.</th>
    <th>Спред, п.п.</th><th>Δ спреда 30 дн.</th><th>Спред 90 дн.</th><th>Оборот в день</th><th title="Стоимость позиции / (20 % среднего дневного оборота за 30 дней)">Дней на продажу</th><th class="l">Признаки</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="note" style="margin-top:10px">Оборот — среднее за 30 дней по торговым дням (${d.cal_days} дн.). «Дней на продажу» — сколько дней потребуется, чтобы продать позицию, забирая не более 20 % дневного оборота. Время расчёта: ${d.timings.total} с.</p></div>
  <details class="st-card st-more"><summary style="padding:14px 20px">Пороги тревог</summary><div>
    ${thRow('mon_drop5','Падение цены за 5 дней, %','Порог срабатывания средней тревоги; вдвое больше — высокая',0.1,0.5)}
    ${thRow('mon_drop30','Падение цены за 30 дней, %','Отслеживает плавное снижение цены за месяц',0.1,0.5)}
    ${thRow('mon_spread30','Рост спреда за 30 дней, п.п.','Сигнал расширения кредитного спреда к ОФЗ',0.1,0.5)}
    ${thRow('mon_sell_days','Неликвид: дней на продажу более','Позиция крупнее 20 % дневного оборота на это число дней',0.5,0.5)}
    ${thRow('mon_offer_days','Оферта: за сколько дней предупреждать','Напоминание о ближайшей дате предъявления',1,1)}
    <div class="st-foot"><span class="mu">Вдвое превышенный порог даёт высокую важность. Дефолт определяется по флагам Мосбиржи, рейтингу D/C и остановке торгов.</span><button class="btn" id="mon-save">Сохранить</button></div>
  </div></details>${NIR_NOTE}`;
}
function bindMon(){
  const r=$('#mon-r');if(r)r.onclick=()=>{S.mon=null;render()};
  const al=$('#mon-all');if(al)al.onclick=()=>{S.monAll=!S.monAll;render()};
  const sv=$('#mon-save');
  if(sv)sv.onclick=async()=>{const b={};['mon_drop5','mon_drop30','mon_spread30','mon_sell_days','mon_offer_days'].forEach(k=>b[k]=$('#mt-'+k).value);
    sv.disabled=true;try{await post('/api/config',b);S.cfg=await api('/api/config');toast('Пороги сохранены','ok')}catch(e){toast(e.message,'err')}S.mon=null;render()};
}
