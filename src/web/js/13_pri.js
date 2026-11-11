/* ── Первичные размещения ── */
S.pri=null;
function loadPri(){api('/api/primary').then(j=>{S.pri=j;if(S.page==='pri')render()}).catch(e=>{S.pri={error:e.message,rows:[]};if(S.page==='pri')render()})}
function pPri(){
  const d=S.pri;
  if(!d){loadPri();return`<div class="card">${waitBox('Загружаю календарь первичных размещений…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="pri-r">Повторить</button></div>`;
  const today=new Date().toISOString().slice(0,10),rows=d.rows;
  const wk=new Date(Date.now()+7*864e5).toISOString().slice(0,10);
  const body=rows.map(r=>`<tr class="${r.start===today?'pnew':''}"${r.isin?` data-isin="${esc(r.isin)}"`:''}><td class="l"><b>${esc(r.short||r.issuer)}</b><br><small class="mu">${esc(r.desc)}</small>${r.isin?`<br><small class="mu num">${esc(r.isin)}</small>`:''}</td>
    <td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td>
    <td class="num">${ddm(r.start)}${r.start===today?'<br><small class="pos">сегодня</small>':''}</td><td class="num">${esc(r.end.replace(' г.',''))}</td>
    <td class="l">${esc(r.book)}</td><td class="l">${r.link?`<a class="blue-link" href="${esc(r.link)}" target="_blank" rel="noopener">объявление Мосбиржи ↗</a>`:''}</td></tr>`).join('');
  return`<div class="g g4">${kpi('Размещений в списке',rows.length,'объявлено Мосбиржей')}${kpi('Сегодня',rows.filter(r=>r.start===today).length,'плановое начало размещения')}
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
  api('/api/primary/stats').then(j=>{S._priStL=0;S.priSt=j;if(S.page==='pri'){render();if(j.loading)setTimeout(()=>{if(S.page==='pri')loadPriSt(true)},4000)}})
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
