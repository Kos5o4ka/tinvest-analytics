/* ── Первичные размещения ── */
S.pri=null;
function loadPri(){api('/api/primary').then(j=>{S.pri=j;if(S.page==='pri')renderSoon()}).catch(e=>{S.pri={error:e.message,rows:[]};if(S.page==='pri')renderSoon()})}
function pPri(){
  const d=S.pri;
  if(!d){loadPri();return`<div class="card">${waitBox('Загружаю календарь первичных размещений…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="pri-r">Повторить</button></div>`;
  const today=new Date().toISOString().slice(0,10),rows=d.rows;
  const wk=new Date(Date.now()+7*864e5).toISOString().slice(0,10);
  const body=rows.map(r=>`<tr class="${r.start===today?'pnew':''}"${r.isin?` data-isin="${esc(r.isin)}"`:''}><td class="l"><b>${esc(r.short||r.issuer)}</b><br><small class="mu">${esc(r.desc)}</small>${r.isin?`<br><small class="mu num">${isinTxt(r.isin)}</small>`:''}</td>
    <td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td>
    <td class="num">${ddm(r.start)}${r.start===today?'<br><small class="pos">сегодня</small>':''}</td><td class="num">${esc(r.end.replace(' г.',''))}</td>
    <td class="l">${esc(r.book)}</td><td class="l">${r.link?`<a class="blue-link" href="${esc(r.link)}" target="_blank" rel="noopener">объявление Мосбиржи ↗</a>`:''}</td></tr>`).join('');
  return priVolHtml()+`<div class="g g4" style="margin-top:16px">${kpi('Размещений в списке',rows.length,'объявлено Мосбиржей')}${kpi('Сегодня',rows.filter(r=>r.start===today).length,'плановое начало размещения')}
    ${kpi('На этой неделе',rows.filter(r=>r.start>=today&&r.start<=wk).length,'начало в ближайшие 7 дней')}${kpi('С рейтингом',rows.filter(r=>r.rating).length,'эмитент найден в базе рейтингов')}</div>
  <div class="card" style="padding:12px 10px 6px"><div class="row" style="padding:0 6px 10px"><b>Календарь первичных размещений</b><button class="btn ghost" id="pri-r" style="margin-left:auto">Обновить</button></div>
    ${rows.length?`<div class="tbl"><table><thead><tr><th class="l">Эмитент и выпуск</th><th class="l">Рейтинг</th><th>Начало размещения</th><th>Окончание</th><th class="l">Книга заявок</th><th class="l">Источник</th></tr></thead><tbody>${body}</tbody></table></div>`:'<div class="empty">Объявленных размещений нет</div>'}</div>
  ${priStatsHtml()}
  <p class="note">Даты начала размещения — по объявлениям Московской биржи (сводка investmint.ru). Ставку купона эмитент обычно объявляет в день сбора заявок: уточняйте её у брокера. Рейтинг сопоставлен с эмитентом по названию. Справочная информация, не инвестиционная рекомендация.</p>`;
}



/* ── Как торгуются новые выпуски: цена в 1-й день, через 7 и 30 дней и сейчас ── */
S.priSt=null;
function loadPriSt(force){
  if(S._priStL&&!force)return;S._priStL=1;
  api('/api/primary/stats').then(j=>{S._priStL=0;S.priSt=j;if(S.page==='pri'){renderSoon();if(j.loading)setTimeout(()=>{if(S.page==='pri')loadPriSt(true)},4000)}})
   .catch(e=>{S._priStL=0;S.priSt={error:e.message}})
}
const ppd=(v,d=2)=>v==null||isNaN(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',')+' п.п.';
const pp1=v=>v==null||isNaN(v)?'—':(+v).toFixed(2).replace('.',',')+' %';
function priStTable(list,title){
  if(!list.length)return'';
  return`<h3 style="font-size:13px;margin:14px 6px 6px;color:var(--tx2)">${title}</h3><div class="tbl"><table><thead><tr><th class="l">Выпуск</th><th class="l">Рейтинг</th><th>Размещён</th><th>Цена 1-й день</th><th>Через 30 дн.</th><th>Сейчас</th><th>Изменение</th><th>Доходность</th></tr></thead><tbody>`+
  list.map(x=>`<tr data-isin="${esc(x.isin||'')}" title="Открыть карточку выпуска"><td class="l"><b>${esc(x.name)}</b>${x.kind==='ofz'?' <span class="tag">ОФЗ</span>':''}</td>
    <td class="l">${x.rating?`<span class="tag rt rt-${esc(rBucket(x.rating).split(' ')[0])}">${esc(x.rating)}</span>`:'<span class="mu">—</span>'}</td>
    <td class="num">${ddm(x.d0)}</td><td class="num">${pp1(x.p0)}</td><td class="num">${pp1(x.p30)}</td><td class="num">${pp1(x.now)}</td>
    <td class="num ${x.delta>0?'pos':x.delta<0?'neg':''}">${ppd(x.delta)}</td><td class="num">${x.ynow!=null?pp1(x.ynow):'—'}</td></tr>`).join('')+`</tbody></table></div>`;
}
function priStatsHtml(){
  if(!S.priSt)loadPriSt();
  const d=S.priSt;
  const head='<div class="card" style="margin-top:16px"><h2>Как торгуются новые выпуски</h2>';
  if(!d)return head+waitBox('Считаю статистику по размещениям за последние 12 месяцев…')+'</div>';
  if(d.error)return head+`<div class="msg err">${esc(d.error)}</div></div>`;
  const a=d.all||{};
  if(!a.n)return head+(d.loading?waitBox((d.phase||'Готовлю данные')+(d.total?` — ${d.done} из ${d.total}`:'')+'. Первый расчёт занимает 2–3 минуты, потом данные хранятся на компьютере.'):'<div class="empty">Пока нет данных по размещённым выпускам. Проверьте подключение к интернету.</div>')+'</div>';
  const bk=(d.buckets||[]).filter(b=>b.n>=3);
  chart('c-pri-b',bars,{h:260,labels:bk.map(b=>b.bucket+' ('+b.n+')'),zero:true,
    series:[{n:'1-й день, цена − номинал',c:'#3987e5',v:bk.map(b=>b.p0==null?null:+(b.p0-100).toFixed(2))},{n:'Через 30 дней, цена − номинал',c:'#19a070',v:bk.map(b=>b.p30==null?null:+(b.p30-100).toFixed(2))}],
    fa:v=>(+v).toFixed(1).replace('.',','),ft:v=>ppd(v),empty:'Мало данных для графика'});
  const dv=a.p30==null?null:a.p30-100;
  const verdict=a.p30==null?'Через 30 дней данных пока мало.':
    `В первый день новые выпуски торгуются в среднем около ${pp1(a.p0)} от номинала, через 30 дней — около ${pp1(a.p30)}. ${a.below30>50?'Больше половины выпусков через месяц стоят ниже номинала: покупка на размещении чаще оказывалась невыгодной, чем покупка позже.':a.below30<30?'Большинство выпусков через месяц стоят не ниже номинала: покупка на размещении обычно не проигрывала.':'Примерно половина выпусков через месяц стоит ниже номинала, половина — выше: явного преимущества у размещения или вторички нет.'}`;
  return head+`<div class="g g4">${kpi('Выпусков в расчёте',a.n,'размещены за 12 месяцев')}${kpi('Медиана через 7 дней',pp1(a.p7),'от номинала')}
    ${kpi('Медиана через 30 дней',pp1(a.p30),dv==null?'':ppd(dv)+' к номиналу',dv==null?'':dv<0?'neg':'pos')}${kpi('Ниже номинала через 30 дней',a.below30==null?'—':pctp(a.below30,0),'доля выпусков')}</div>
  <p style="margin:12px 6px;color:var(--tx2)">${esc(verdict)}</p>
  <div class="g g2" style="margin-top:6px"><div><div class="axt">Отклонение цены от номинала по рейтингам, п.п.</div><div id="c-pri-b" class="chart"></div></div>
  <div><div class="tbl"><table><thead><tr><th class="l">Группа</th><th>Выпусков</th><th>Цена 1-й день</th><th>Через 30 дн.</th><th>Ниже номинала</th><th>Сейчас к 1-му дню</th></tr></thead><tbody>
    ${(d.buckets||[]).map(b=>`<tr><td class="l">${esc(b.bucket)}</td><td class="num">${b.n}</td><td class="num">${pp1(b.p0)}</td><td class="num">${pp1(b.p30)}</td><td class="num">${b.below30==null?'—':pctp(b.below30,0)}</td><td class="num ${b.d_now>0?'pos':b.d_now<0?'neg':''}">${ppd(b.d_now)}</td></tr>`).join('')}</tbody></table></div>
    ${(d.sectors||[]).length?`<div class="tbl" style="margin-top:12px"><table><thead><tr><th class="l">Сектор</th><th>Выпусков</th><th>Через 30 дн.</th><th>Ниже номинала</th></tr></thead><tbody>
    ${d.sectors.map(b=>`<tr><td class="l">${esc(SECT[b.sector]||b.sector)}</td><td class="num">${b.n}</td><td class="num">${pp1(b.p30)}</td><td class="num">${b.below30==null?'—':pctp(b.below30,0)}</td></tr>`).join('')}</tbody></table></div>`:''}</div></div>
  ${priStTable(d.best||[],'Лучшие размещения: сильнее всего выросли в цене с 1-го дня')}${priStTable(d.worst||[],'Худшие размещения: сильнее всего подешевели')}
  ${d.loading?`<p class="note">Догружаю данные: ${esc(d.phase||'')} ${d.total?d.done+' из '+d.total:''}…</p>`:''}
  <p class="note">Считаются корпоративные облигации и ОФЗ, размещённые за последние 12 месяцев и торгуемые сейчас (досрочно погашенные в расчёт не попали, поэтому картина может быть чуть лучше реальной). Цена — средневзвешенная, в процентах от номинала; «Сейчас» — последняя рыночная цена, у части выпусков она меняется из-за купонов и амортизации. Рейтинг сопоставлен по названию эмитента. Ежедневные снимки объявленных размещений сохраняются на компьютере (накоплено дней: ${d.snap_days}) — позже по ним можно сравнить ориентир купона и итог. Справочная информация, не инвестиционная рекомендация.</p></div>`;
}


/* ── «Простыня» новых выпусков: объём выпуска, сколько размещено, оборот сегодня и разбивка по дням ──
   Данные: /api/primary/volumes (площадки размещения Мосбиржи PSAU/PACT…, ISSUESIZE/ISSUESIZEPLACED) и
   /api/primary/days?secid=… (история торгов выпуска по всем площадкам, грузится при раскрытии строки). */
S.priV=null;S.priVSort={k:'default',d:1};S.priVF='all';S.priVOpen={};S.priDays={};
function loadPriVol(force){
  if(S._pvL&&!force)return;S._pvL=1;clearTimeout(S._pvT);
  api('/api/primary/volumes'+(force?'?force=1':'')).then(j=>{S._pvL=0;S.priV=j;if(S.page==='pri')renderSoon();
    if(j.loading)S._pvT=setTimeout(()=>{if(S.page==='pri')loadPriVol(true)},3500);
    else S._pvT=setTimeout(()=>{if(S.page==='pri'){S._pvL=0;loadPriVol(true)}},300000)})
   .catch(e=>{S._pvL=0;S.priV={error:e.message,rows:[]};if(S.page==='pri')renderSoon()})
}
function loadPriDays(secid){
  const c=S.priDays[secid];if(c&&(c.loading||c.data))return;
  S.priDays[secid]={loading:1};
  api('/api/primary/days?secid='+encodeURIComponent(secid)).then(j=>{S.priDays[secid]={data:j};if(S.page==='pri')renderSoon()})
   .catch(e=>{S.priDays[secid]={error:e.message};if(S.page==='pri')renderSoon()})
}
const pvRub=v=>v==null||isNaN(v)?'—':short(v)+' ₽';
const pvAmt=(v,c)=>c&&c!=='RUB'?(v==null||isNaN(v)?'—':short(v)+' '+c):pvRub(v);   // объём выпуска и «размещено» — в валюте номинала
const pvLabels=bs=>{const m={};(bs||[]).forEach(b=>{const x=m[b.label]||(m[b.label]={label:b.label,place:b.place,v:0,n:0,ids:[]});x.v+=b.v;x.n+=b.n;x.ids.push(b.b)});return Object.values(m)};
const PV_ST={placing:['идёт размещение','pos'],placed:['размещён',''],upcoming:['ещё не размещён','mu']};
const PV_COLS=[['name','Выпуск','l'],['rating','Рейтинг','l'],['coupon','Купон','l'],['start','Дата разм.'],['size_rub','Объём выпуска, ₽'],['placed_rub','Размещено, ₽'],['today','Сегодня, ₽ оборот'],['yield','Доходность сейчас']];
function pvSortRows(rows){
  const{k,d}=S.priVSort;if(k==='default')return rows;
  const val=r=>k==='rating'?(r.rating?r.rating.v:''):r[k];
  return rows.slice().sort((a,b)=>{const x=val(a),y=val(b);
    if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''),'ru');
    return d*((x??-Infinity)-(y??-Infinity))});
}
function pvRow(r,today){
  const st=PV_ST[r.status]||['',''],open=!!S.priVOpen[r.secid]&&r.status!=='upcoming';
  const pct=r.placed_pct,w=Math.max(0,Math.min(100,pct||0));
  const placed=r.status==='upcoming'?'<span class="mu">ещё не размещён</span>':r.placed_rub?`<div class="pv-pl"><span title="${r.placed_src==='trades'?'Сумма сделок на площадке размещения (номинал)':'Данные Мосбиржи (ISSUESIZEPLACED)'}">${pvAmt(r.placed_rub,r.cur)}</span>${pct!=null?`<small class="mu num">${pct.toFixed(pct>=10?0:1).replace('.',',')} %</small>`:''}</div>${pct!=null?`<div class="pv-bar"><i style="width:${w}%"></i></div>`:''}`:'<span class="mu">—</span>';
  const tod=r.today>0?`${pvRub(r.today)}<br><small class="mu num">${r.today_place>0?'размещение '+short(r.today_place):'вторичка'} · ${r.today_trades} сд.</small>`:'<span class="mu">—</span>';
  return`<tr class="${r.start===today?'pnew':''}"${r.isin?` data-isin="${esc(r.isin)}"`:''}>
    <td class="l"><div class="pv-nm">${r.status!=='upcoming'?`<button class="pv-x${open?' on':''}" data-pvx="${esc(r.secid)}" title="Разбивка по дням" aria-expanded="${open}">›</button>`:'<span class="pv-x0"></span>'}<div><b>${esc(r.name)}</b> <small class="${st[1]}">${st[0]}</small><br><small class="mu num">${isinTxt(r.isin)}</small></div></div></td>
    <td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td>
    <td class="l">${r.coupon?esc(r.coupon):'<span class="mu" title="Ставку купона эмитент объявляет в день сбора заявок">—</span>'}</td>
    <td class="num">${r.start?ddm(r.start):'—'}${r.start===today?'<br><small class="pos">сегодня</small>':''}</td>
    <td class="num">${r.size_rub?`${pvAmt(r.size_rub,r.cur)}<br><small class="mu num">${short(r.size_pcs)} шт</small>`:'<span class="mu">—</span>'}</td>
    <td class="num">${placed}</td><td class="num">${tod}</td><td class="num">${r.yield?pp1(r.yield):'<span class="mu">—</span>'}</td></tr>`+(open?`<tr class="pv-dd"><td colspan="8">${pvDaysHtml(r.secid)}</td></tr>`:'');
}
function pvDaysHtml(secid){
  const c=S.priDays[secid];
  if(!c||c.loading)return waitBox('Загружаю историю торгов по дням…');
  if(c.error)return`<div class="msg err">${esc(c.error)}</div>`;
  const d=c.data,days=d.days||[];
  if(!days.length)return`<div class="empty">Торгов по выпуску пока не было</div>`+(d.errors&&d.errors.length?`<p class="note">${esc(d.errors.join('; '))}</p>`:'');
  const last=days.slice(-45);
  chart('c-pvd-'+secid,bars,{h:170,labels:last.map(x=>ddm(x.d).slice(0,5)),stack:true,zero:true,
    series:[{n:'Размещение',c:'#3987e5',v:last.map(x=>x.place_v)},{n:'Вторичный рынок',c:'#19a070',v:last.map(x=>x.sec_v)}],fa:v=>short(v),ft:v=>pvRub(v),empty:'Нет сделок'});
  const rows=days.slice().reverse().map(x=>`<tr><td class="num">${ddm(x.d)}${x.live?' <small class="pos">сегодня</small>':''}</td>
    <td class="l">${pvLabels(x.boards).map(b=>`<span class="tag${b.place?' pv-pt':''}" title="${esc(b.ids.join(', '))}: ${pvRub(b.v)}, ${b.n} сд.">${esc(b.label)}</span>`).join(' ')}</td>
    <td class="num">${NFQ.format(Math.round(x.q))}</td><td class="num">${pvRub(x.v)}</td><td class="num">${x.n}</td>
    <td class="num">${x.px?pp1(x.px):'—'}</td><td class="num">${x.y?pp1(x.y):'—'}</td></tr>`).join('');
  const t=d.total||{};
  return`<div class="pv-dc"><div class="row" style="gap:18px;flex-wrap:wrap;margin-bottom:6px"><span><small class="mu">Всего торгов</small> <b class="num">${pvRub(t.v)}</b></span><span><small class="mu">Размещение</small> <b class="num">${pvRub(t.place_v)}</b></span><span><small class="mu">Сделок</small> <b class="num">${NFQ.format(t.n||0)}</b></span><span><small class="mu">Номинал</small> <b class="num">${NFQ.format(d.face||0)} ₽</b></span></div>
    <div id="c-pvd-${esc(secid)}" class="chart"></div>
    <div class="tbl" style="max-height:340px"><table><thead><tr><th>Дата</th><th class="l">Площадки</th><th>Объём, шт</th><th>Оборот, ₽</th><th>Сделок</th><th>Цена, % ном.</th><th>Доходность</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${d.errors&&d.errors.length?`<p class="note">Часть данных не загрузилась: ${esc(d.errors.join('; '))}</p>`:''}</div>`;
}
function priVolHtml(){
  if(!S.priV)loadPriVol();
  const d=S.priV,head='<div class="card"><div class="row" style="padding:0 6px 8px"><h2 style="margin:0">Новые выпуски: объём и спрос</h2><button class="btn ghost" id="pv-r" style="margin-left:auto">Обновить</button></div>';
  if(!d)return head+waitBox('Загружаю размещения за последние 30 дней…')+'</div>';
  if(d.error)return head+`<div class="msg err">${esc(d.error)}</div></div>`;
  const all=d.rows||[],today=d.today||new Date().toISOString().slice(0,10);
  if(!all.length)return head+(d.loading?waitBox((d.phase||'Готовлю данные')+'. Первая загрузка занимает до минуты, потом данные хранятся на компьютере.'):'<div class="empty">Размещений за последние 30 дней не найдено</div>')+'</div>';
  const cnt=k=>all.filter(r=>r.status===k).length;
  const rows=pvSortRows(all.filter(r=>S.priVF==='all'||r.status===S.priVF));
  const{k,d:sd}=S.priVSort;
  const th=PV_COLS.map(([kk,t,c])=>`<th class="s ${c||''}" data-pvs="${kk}">${t} <span>${k===kk?(sd>0?'↑':'↓'):''}</span></th>`).join('');
  const tot=all.reduce((a,r)=>a+(r.today||0),0),plc=all.reduce((a,r)=>a+(r.placed_rub||0),0);
  const seg=[['all','Все · '+all.length],['placing','Идёт размещение · '+cnt('placing')],['placed','Размещены · '+cnt('placed')],['upcoming','Ожидаются · '+cnt('upcoming')]];
  return head+`<div class="g g4">${kpi('Выпусков в таблице',all.length,'размещены за 30 дней и ожидаются')}${kpi('Идёт размещение',cnt('placing'),'сделки на площадке размещения сегодня')}
    ${kpi('Оборот сегодня',pvRub(tot),'размещение и вторичные торги')}${kpi('Размещено за период',pvRub(plc),'по номиналу, без ожидаемых')}</div>
  <div class="row" style="padding:10px 6px"><div class="seg" id="pv-f">${seg.map(([v,t])=>`<button class="${S.priVF===v?'on':''}" data-pvf="${v}">${t}</button>`).join('')}</div>${d.loading?'<small class="mu" style="margin-left:auto">обновляю…</small>':''}</div>
  <div class="tbl" style="max-height:calc(100vh - 220px)"><table id="pv-tab"><thead><tr>${th}</tr></thead><tbody>${rows.map(r=>pvRow(r,today)).join('')||'<tr><td colspan="8" class="empty">В этой группе пусто</td></tr>'}</tbody></table></div>
  ${(d.errors||[]).length?`<p class="note">Не всё удалось загрузить: ${esc(d.errors.slice(0,3).join('; '))}. Попробуйте «Обновить» чуть позже.</p>`:''}
  <p class="note">Новые выпуски — облигации, торги которыми начались за последние 30 дней, и объявленные размещения. Объём выпуска и «размещено» — в рублях по номиналу: штуки × номинал (у части выпусков «размещено» — сумма сделок на площадке размещения Мосбиржи, а не отчёт эмитента). «Сегодня» — оборот по рыночной цене сделок, данные Мосбиржи обновляются в течение дня (при открытых торгах — раз в несколько минут). Нажмите ›, чтобы увидеть разбивку по дням и площадкам; клик по строке открывает карточку выпуска. Справочная информация, не инвестиционная рекомендация.</p></div>`;
}
document.addEventListener('click',e=>{
  if(S.page!=='pri')return;
  const t=e.target;
  if(t.closest('#pv-r')){S.priV=null;S.priDays={};loadPriVol(true);renderSoon();return}
  const x=t.closest('[data-pvx]');
  if(x){const id=x.dataset.pvx;S.priVOpen[id]=!S.priVOpen[id];if(S.priVOpen[id])loadPriDays(id);render();return}
  const f=t.closest('[data-pvf]');if(f){S.priVF=f.dataset.pvf;render();return}
  const h=t.closest('#pv-tab thead [data-pvs]');
  if(h){const kk=h.dataset.pvs;S.priVSort={k:kk,d:S.priVSort.k===kk?-S.priVSort.d:(['name','coupon','rating'].includes(kk)?1:-1)};render()}
});
