/* ── Налоги: обзор, расчёт по лотам (FIFO), ЛДВ, ИИС, подсказки, данные для 3-НДФЛ, настройки ── */
S.tx={tab:'ov',data:null,acc:null,busy:0,err:null,year:null,draft:null,msg:''};
try{const t=localStorage.getItem('tx_tab');if(t&&['ov','fc','yr','ldv','iis','hint','decl','set'].includes(t))S.tx.tab=t}catch(e){}
const TXTABS=[['ov','Обзор'],['fc','Прогноз на 31.12'],['yr','Налог по годам'],['ldv','ЛДВ'],['iis','ИИС'],['hint','Подсказки'],['decl','Для декларации'],['set','Настройки налогов']];
const tR=n=>bad(n)?'—':M(n,'rub',0),tS=n=>bad(n)?'—':(n>0?'+':'')+M(n,'rub',0);
const tDt=s=>s?ddm(s):'—';
function txGo(t){S.tx.tab=t;try{localStorage.setItem('tx_tab',t)}catch(e){}render()}
function loadTax(force){
  if(S.tx.busy)return;S.tx.busy=1;const acc=S.account;
  api('/api/tax?'+new URLSearchParams(Object.assign({account:acc},force?{force:'1'}:{}))).then(j=>{
    S.tx.busy=0;S.tx.acc=acc;S.tx.err=null;
    if(S.account!==acc){if(S.page==='tax')render();return}
    S.tx.data=j;S.tx.draft=null;if(S.page==='tax')render()
  }).catch(e=>{S.tx.busy=0;S.tx.acc=acc;S.tx.data=null;S.tx.err=e.message;if(S.page==='tax')render()});
}
const txNote=`<p class="note">Расчёт справочный и не является налоговой консультацией: налог как налоговый агент считает и удерживает брокер, а итог за год определяется декларацией. Приложение считает по тем операциям, которые видит (история счетов и импортированные отчёты).</p>`;

function pTax(){
  const tx=S.tx;
  const tabs=`<div class="seg tx-tabs noprint">${TXTABS.map(([k,t])=>`<button class="${k===tx.tab?'on':''}" onclick="txGo('${k}')">${t}</button>`).join('')}</div>`;
  let body;
  if(tx.tab==='ov')body=txOv();
  else if(tx.err&&tx.acc===S.account)body=`<div class="msg err">${esc(tx.err)} <button class="btn ghost" onclick="S.tx.err=null;S.tx.acc=null;render()">Повторить</button></div>`;
  else if(!tx.data||tx.acc!==S.account){loadTax();body=`<div class="card">${waitBox('Считаю налоги по лотам: покупки, продажи, ЛДВ, убытки…')}</div>`}
  else body=({fc:txFc,yr:txYr,ldv:txLdv,iis:txIis,hint:txHint,decl:txDecl,set:txSet})[tx.tab](tx.data)+txNote;
  return`<div class="tx"><div class="row" style="margin-bottom:14px">${tabs}</div>${body}</div>`;
}

/* ── Обзор (прежняя страница) ── */
function txOv(){
  const d=S.data,lf=d.life,rows=d.tax,cy=new Date().getFullYear(),cur=rows.find(r=>r.year===cy);
  const withheld=sumK(lf,TAXK);
  let out=`<div class="g g4">${kpi('Удержано налогов за всё время',M(withheld),'НДФЛ, удержанный брокером',null,S4)}
    ${kpi(`Оценка НДФЛ за ${cy}`,cur?M(cur.estimate):'—',cur?`база ${short(Math.max(0,cur.trade)+cur.income)} ₽`:'нет дохода',null,S1)}
    ${kpi(`Удержано в ${cy}`,cur?M(cur.withheld):'—','по операциям этого года',null,S3)}
    ${kpi('Ожидается к удержанию',cur?M(Math.max(0,cur.diff)):'—',cur&&cur.diff<0?'удержано больше оценки':'при выводе или в конце года',cur&&cur.diff>0?'neg':'',S2)}</div>`;
  chart('c-tax',bars,{labels:rows.map(r=>String(r.year)),series:[{n:'Оценка НДФЛ',c:S1,v:rows.map(r=>r.estimate)},{n:'Удержано брокером',c:S2,v:rows.map(r=>r.withheld)}]});
  out+=`<div class="g c-1-2"><div class="card"><h2>Удержанные налоги по видам</h2>${withheld?hbars(TAXK.filter(k=>lf[k]).map((k,i)=>({n:L[k],v:lf[k],c:PAL[i]})),S1,null,1):'<div class="empty">Налоги не удерживались</div>'}</div>
    <div class="card"><h2>Оценка и факт по годам, ₽</h2><div id="c-tax" class="chart"></div></div></div>`;
  out+=`<div class="card" style="padding:6px 8px"><div class="tbl"><table><thead><tr><th>Год</th><th>Результат сделок</th><th>Дивиденды, купоны, РЕПО</th><th>Налоговая база</th><th>Оценка НДФЛ</th><th>Удержано</th><th>Разница</th></tr></thead><tbody>`+
    (rows.length?rows.slice().reverse().map(r=>`<tr><td><b>${r.year}</b></td><td class="num ${cls(r.trade)}">${SM(r.trade)}</td><td class="num">${M(r.income)}</td><td class="num">${M(Math.max(0,r.trade)+r.income)}</td>
    <td class="num">${M(r.estimate)}</td><td class="num">${M(r.withheld)}</td><td class="num ${r.diff>0.5?'neg':r.diff<-0.5?'pos':''}">${SM(r.diff)}</td></tr>`).join(''):'<tr><td colspan="7" class="l mu">Нет данных</td></tr>')+
    `</tbody></table></div></div><p class="note"><b>Это быстрая оценка по сводке операций, а не декларация.</b> Ставка: 13 %; с 2021 по 2024 — 15 % с части базы свыше 5 млн ₽; с 2025 — 15 % свыше 2,4 млн ₽.
    База здесь: положительный результат продаж + дивиденды + купоны + доход по РЕПО в рублях. Точный расчёт по лотам (FIFO), с ЛДВ, переносом убытков, ИИС и курсовыми разницами — на вкладках выше. Точные суммы рассчитывает брокер как налоговый агент.</p>`;
  return out;
}

/* ── Налог по годам ── */
function txRowsTable(rows){
  return`<div class="tbl"><table><thead><tr><th>Год</th><th>Результат сделок</th><th>ЛДВ</th><th>Убытки прошлых лет</th><th>Дивиденды</th><th>Купоны, РЕПО</th><th>Налоговая база</th><th>Налог по расчёту</th><th>Удержано</th><th>Разница</th><th>Откл.</th></tr></thead><tbody>${
    rows.slice().reverse().map(r=>`<tr><td><b>${r.year}</b></td><td class="num ${cls(r.trade)}">${tS(r.trade)}</td><td class="num">${r.ldv_exempt>0.5?'−'+tR(r.ldv_exempt):'—'}</td>
      <td class="num">${r.carry_used>0.5?'−'+tR(r.carry_used):'—'}</td><td class="num">${tR(r.dividends)}</td><td class="num">${tR(r.coupons+r.overnight)}</td><td class="num">${tR(r.base)}</td>
      <td class="num"><b>${tR(r.tax)}</b></td><td class="num">${tR(r.withheld)}</td><td class="num ${r.diff>0.5?'neg':r.diff<-0.5?'pos':''}">${tS(r.diff)}</td>
      <td class="num ${r.diff_pct!=null&&Math.abs(r.diff_pct)>25?'neg':'mu'}">${r.diff_pct==null?'—':pct(r.diff_pct,0)}</td></tr>`).join('')}</tbody></table></div>`;
}
function txYr(d){
  const ys=d.years;
  if(!ys.length)return`<div class="card empty">Нет операций для расчёта налога</div>`;
  const cy=new Date().getFullYear(),cur=ys.find(r=>r.year===cy)||ys[ys.length-1];
  const tot=ys.reduce((a,r)=>({tax:a.tax+r.tax,wh:a.wh+r.withheld,ldv:a.ldv+r.ldv_saved}),{tax:0,wh:0,ldv:0});
  chart('c-txy',bars,{labels:ys.map(r=>String(r.year)),series:[{n:'Налог по расчёту',c:S1,v:ys.map(r=>r.tax)},{n:'Удержано брокером',c:S2,v:ys.map(r=>r.withheld)}]});
  let out=`<div class="g g4">${kpi(`Налог по расчёту за ${cur.year}`,tR(cur.tax),`база ${tR(cur.base)}; ставка 13 %${cur.tax15>0?' и 15 %':''}`,null,S1)}
    ${kpi(`Удержано в ${cur.year}`,tR(cur.withheld),cur.diff_pct==null?'по операциям удержания':`расчёт отличается на ${pct(cur.diff_pct,0)}`,null,S2)}
    ${kpi('Сэкономлено за счёт ЛДВ',tR(tot.ldv),'за все годы',tot.ldv>0?'pos':'',S3)}
    ${kpi('Налог по расчёту за всё время',tR(tot.tax),`удержано ${tR(tot.wh)}`,null,S4)}</div>
    <div class="card"><h2>Расчёт и удержанный налог по годам, ₽</h2><div id="c-txy" class="chart"></div></div>
    <div class="card" style="padding:6px 8px"><h2 style="padding:10px 10px 0">Все выбранные счета вместе</h2>${txRowsTable(ys)}${ys.filter(r=>r.extra_progressive>0.5).reverse().map(r=>`<p class="note" style="padding:0 10px">${r.year}: <b>Ожидаемая доплата по прогрессивной шкале (совокупность счетов) ${tR(r.extra_progressive)}</b>. Порог 15 % относится к совокупному доходу налогоплательщика, а счета и ИИС считаются отдельно: если вместе база превысила порог, ФНС доначислит разницу.</p>`).join('')}</div>`;
  if(d.groups.length>1)out+=d.groups.map(g=>`<div class="card" style="padding:6px 8px"><h2 style="padding:10px 10px 0">${esc(g.name)}${g.kind==='iis'?`<span class="sp">${g.iis.exempt?'доход освобождён от налога (срок соблюдён)':'ИИС тип '+({A:'А',B:'Б','3':'3'})[g.iis.type]}</span>`:''}</h2>${txRowsTable(g.rows)}</div>`).join('');
  const cmp=ys.filter(r=>r.diff_pct!=null&&Math.abs(r.diff_pct)>25);
  out+=`<div class="card"><h2>Почему расчёт и удержание могут расходиться</h2><ul class="tx-ul">
    <li><b>Сроки.</b> Брокер удерживает налог не в день сделки, а в конце года, при выводе денег или в январе следующего года, поэтому суммы в соседних годах «плавают».</li>
    <li><b>Данные брокера.</b> Он видит всю историю бумаг (включая переводы из других депозитариев) и считает расходы по своим документам; мы — только по операциям в приложении.</li>
    <li><b>Убытки и купоны.</b> Убыток по сделкам по умолчанию не уменьшает купоны и дивиденды (флажок «Убыток по сделкам уменьшает купонный доход» — во вкладке «Настройки налогов»).</li>
    <li><b>Фьючерсы, ИИС, другие брокеры</b> считаются отдельно; по сделкам в валюте используется курс ЦБ на даты покупки и продажи.</li></ul>
    ${cmp.length?`<p class="note">Заметное расхождение (больше 25 %) в годах: ${cmp.map(r=>r.year).join(', ')}.</p>`:''}
    <ul class="tx-ul note">${d.assumptions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul>
    ${convNote(d.conversions,true)}
    ${d.warnings.length?`<div class="msg info" style="margin-top:8px">${d.warnings.map(esc).join('<br>')}</div>`:''}</div>`;
  return out;
}

/* ── ЛДВ ── */
function txLdv(d){
  const l=d.ldv,up=l.upcoming,rd=l.ready,nxt=up[0];
  let out=`<div class="g g4">${kpi('Сэкономлено за счёт ЛДВ',tR(l.saved_total),'налог, который не пришлось платить',l.saved_total>0?'pos':'',S3)}
    ${kpi('Бумаг с наступившей ЛДВ',String(rd.length),rd.length?`прибыль без налога: ${tR(rd.reduce((a,e)=>a+Math.max(0,e.gain||0),0))}`:'пока нет',null,S1)}
    ${kpi('Ближайшая ЛДВ',nxt?tDt(nxt.date):'—',nxt?`через ${nxt.days} дн.: ${esc(nxt.ticker||nxt.name)}`:'нет лотов на подходе',null,S2)}
    ${kpi('Освобождение',`${short(l.limit)} ₽ × лет`,'предел дохода за каждый полный год владения',null,S4)}</div>`;
  out+=`<div class="card"><h2>Как это работает</h2><p class="note">Если бумага (акции, облигации, фонды), купленная с 2014 года, продана <b>после трёх лет владения</b>, то прибыль не облагается налогом в пределах 3 млн ₽ × число полных лет владения. Срок считается по каждому лоту отдельно, продажа идёт по FIFO (первыми уходят самые старые лоты). На ИИС ЛДВ не применяется.</p></div>`;
  out+=`<div class="card" style="padding:6px 8px"><h2 style="padding:10px 10px 0">ЛДВ уже наступила<span class="sp">можно продавать без налога с прибыли</span></h2><div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>С даты</th><th>Кол-во</th><th>Стоимость покупки</th><th>Сейчас</th><th>Прибыль</th><th>Налог без ЛДВ</th></tr></thead><tbody>${
    rd.length?rd.map(e=>`<tr><td class="l"><b>${esc(e.name)}</b><br><small class="mu">${esc(e.ticker)}</small></td><td class="num">${tDt(e.date)}</td><td class="num">${NF0.format(e.qty)}</td><td class="num">${tR(e.cost)}</td><td class="num">${e.known?tR(e.value):'—'}</td><td class="num ${cls(e.gain)}">${e.known?tS(e.gain):'—'}</td><td class="num">${e.tax_now!=null?tR(e.tax_now):'—'}</td></tr>`).join(''):'<tr><td colspan="7" class="l mu">Лотов старше трёх лет пока нет</td></tr>'}</tbody></table></div></div>`;
  out+=`<div class="card" style="padding:6px 8px"><h2 style="padding:10px 10px 0">Скоро наступит ЛДВ<span class="sp">до этой даты продавать выгодно, только если нет прибыли</span></h2><div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>ЛДВ с даты</th><th>Осталось</th><th>Кол-во</th><th>Прибыль сейчас</th><th>Налог, если продать сегодня</th></tr></thead><tbody>${
    up.length?up.slice(0,60).map(e=>`<tr><td class="l"><b>${esc(e.name)}</b><br><small class="mu">${esc(e.ticker)}</small></td><td class="num">${tDt(e.date)}</td><td class="num ${e.days<=90?'neg':''}">${e.days} дн.</td><td class="num">${NF0.format(e.qty)}</td>
      <td class="num ${cls(e.gain)}">${e.known?tS(e.gain):'—'}</td><td class="num">${e.tax_now!=null?`<b class="${e.tax_now>0?'neg':''}">${tR(e.tax_now)}</b>`:'—'}</td></tr>`).join(''):'<tr><td colspan="6" class="l mu">Нет лотов, ожидающих ЛДВ</td></tr>'}</tbody></table></div></div>`;
  out+=`<div class="card" style="padding:6px 8px"><h2 style="padding:10px 10px 0">Применённая ЛДВ по годам</h2><div class="tbl"><table><thead><tr><th>Год</th><th>Лотов</th><th>Освобождено от налога</th><th>Предел</th><th>Налог сэкономлен</th></tr></thead><tbody>${
    l.years.length?l.years.slice().reverse().map(e=>`<tr><td><b>${e.year}</b></td><td class="num">${e.n}</td><td class="num">${tR(e.exempt)}</td><td class="num">${tR(e.limit)}</td><td class="num pos">${tR(e.saved)}</td></tr>`).join(''):'<tr><td colspan="5" class="l mu">Продаж с ЛДВ не было</td></tr>'}</tbody></table></div></div>`;
  return out;
}

/* ── ИИС ── */
function txIis(d){
  if(!d.iis.length)return`<div class="card empty">Среди выбранных счетов нет ИИС. Выберите счёт ИИС слева или «Все счета».</div>`;
  const TN={A:'А (вычет на взносы)',B:'Б (освобождение дохода)','3':'ИИС-3 (вычет и освобождение)'};
  return d.iis.map(i=>{
    const dedAvail=i.type==='A'||i.type==='3',exAvail=i.type==='B'||i.type==='3';
    return`<div class="card"><h2>${esc(i.name)}<span class="sp">тип ${TN[i.type]}${i.type_set?'':' · предположительно, уточните в настройках'}</span></h2>
    <div class="g g4">${kpi('Открыт',tDt(i.opened),i.opened?'':'укажите дату в настройках',null,S1)}
      ${kpi('Срок владения до',tDt(i.term),i.type==='3'?'5 лет для ИИС-3':'3 года',null,S2)}
      ${kpi('Освобождение дохода',exAvail?(i.term_ok?'действует':'ещё нет'):'не предусмотрено',exAvail?(i.term_ok?'доход внутри счёта не облагается':'до срока при закрытии будет налог'):'для типа А налог платится с дохода',i.term_ok&&exAvail?'pos':'',S3)}
      ${kpi('Вычет на взносы',dedAvail?tR(i.deduct_total):'не предусмотрен',dedAvail?'13 % от взносов до 400 тыс. ₽ в год':'у типа Б вычета на взносы нет',null,S4)}</div>
    ${dedAvail?`<div class="tbl" style="margin-top:12px"><table><thead><tr><th>Год</th><th>Взносы</th><th>Учитывается в вычете (до 400 тыс. ₽)</th><th>Вернуть можно (13 %)</th></tr></thead><tbody>${
      i.years.filter(y=>y.deposits>0).map(y=>`<tr><td><b>${y.year}</b></td><td class="num">${tR(y.deposits)}</td><td class="num">${tR(y.deduct_base)}${y.over>0?`<br><small class="mu">сверх лимита ${tR(y.over)}</small>`:''}</td><td class="num pos">${tR(y.deduct)}</td></tr>`).join('')||'<tr><td colspan="4" class="l mu">Пополнений в истории нет</td></tr>'}</tbody></table></div>
    <p class="note">Вычет возвращает налог, уплаченный с вашей зарплаты и других доходов по ставке 13 %: больше, чем вы заплатили, вернуть нельзя. Заявляется в декларации 3-НДФЛ или через работодателя.</p>`:''}
    ${exAvail?`<p class="note">При закрытии ИИС до срока (${tDt(i.term)}) налог с дохода придётся заплатить; расчётный налог по всему доходу счёта — ${tR(i.tax_if_closed)}. Результат сделок на ИИС: ${tS(i.trade_total)}, дивиденды и купоны: ${tR(i.income_total)}.</p>`:`<p class="note">Для типа А налог на доход внутри ИИС удерживается как обычно; результат сделок: ${tS(i.trade_total)}, дивиденды и купоны: ${tR(i.income_total)}.</p>`}</div>`}).join('')+
    `<p class="note noprint"><a href="#" onclick="txGo('set');return false">Указать тип и дату открытия ИИС</a>. Условия вычета зависят от года открытия счёта — сверьтесь с правилами ФНС.</p>`;
}

/* ── Подсказки ── */
function txHint(d){
  const h=d.hints;
  let out=`<div class="g g4">${kpi('Экономия от сбора убытков',tR(Math.max(0,h.harvest_total)),'вместе, после комиссий и спреда',h.harvest_total>0?'pos':'',S3)}
    ${kpi('Позиций для сбора убытков',String(h.harvest.length),`до конца ${h.year} года осталось ${h.days_left} дн.`,null,S1)}
    ${kpi('Предупреждений по ЛДВ',String(h.ldv_warn.length),'продажа прибыльных бумаг скоро невыгодна',h.ldv_warn.length?'neg':'',S2)}
    ${kpi('Комиссия + спред',pctp((h.fee_rate+h.spread)*100,2),'оценка расходов на продажу и покупку',null,S4)}</div>`;
  out+=`<div class="card" style="padding:6px 8px"><h2 style="padding:10px 10px 0">Сбор убытков до конца года<span class="sp">продать с убытком и сразу откупить</span></h2>
    <p class="note" style="padding:0 10px">Убыток от продажи уменьшает налогооблагаемую прибыль этого года. Экономия = меньшее из убытка и уже полученной прибыли × ставка. Позицию можно откупить сразу: экономический результат не меняется, но стоимость покупки обновится, а срок владения для ЛДВ начнётся заново.</p>
    <div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>Кол-во</th><th>Стоимость</th><th>Убыток при продаже</th><th>Экономия налога</th><th>Расходы (комиссия + спред)</th><th>Выгода</th></tr></thead><tbody>${
      h.harvest.length?h.harvest.map(c=>`<tr><td class="l"><b>${esc(c.name)}</b><br><small class="mu">${esc(c.ticker)} · ${esc(c.gname)}${c.ldv_lost?' · <span class="neg">сбросится срок ЛДВ</span>':''}</small></td><td class="num">${NF0.format(c.qty)}</td><td class="num">${tR(c.value)}</td>
        <td class="num neg">−${tR(c.loss)}</td><td class="num pos">${tR(c.saving)}</td><td class="num">${tR(c.cost)}</td><td class="num ${c.net>0?'pos':'neg'}"><b>${tS(c.net)}</b></td></tr>`).join(''):`<tr><td colspan="7" class="l mu">${esc(h.notes[0]||'Нет подходящих позиций')}</td></tr>`}</tbody></table></div></div>`;
  out+=`<div class="card" style="padding:6px 8px"><h2 style="padding:10px 10px 0">Не продавайте до ЛДВ<span class="sp">до конца льготного срока меньше года, прибыль есть</span></h2><div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>ЛДВ с даты</th><th>Осталось</th><th>Прибыль сейчас</th><th>Налог, если продать сегодня</th></tr></thead><tbody>${
    h.ldv_warn.length?h.ldv_warn.map(e=>`<tr><td class="l"><b>${esc(e.name)}</b><br><small class="mu">${esc(e.ticker)}</small></td><td class="num">${tDt(e.date)}</td><td class="num">через ${e.days} дн.</td><td class="num pos">${tS(e.gain)}</td><td class="num neg"><b>${tR(e.tax_now)}</b></td></tr>`).join(''):'<tr><td colspan="5" class="l mu">Нет таких бумаг</td></tr>'}</tbody></table></div>
    ${h.ldv_warn.length?`<p class="note" style="padding:0 10px">Через указанное число дней по этим бумагам наступит ЛДВ: продавать раньше невыгодно, если есть прибыль.</p>`:''}</div>`;
  if(d.carry_suggest.length)out+=`<div class="card"><h2>Убытки прошлых лет</h2><p class="note">По расчёту у вас были убытки, которые можно перенести на будущие доходы (до 10 лет): ${d.carry_suggest.map(s=>`${s.year} — ${tR(s.loss)}`).join('; ')}. Проверьте суммы по декларациям и внесите в «Настройки налогов».</p></div>`;
  return out;
}

/* ── Прогноз налога на конец года и сбор убытков (информационный расчёт) ── */
function txFc(d){
  const f=d.forecast;
  if(!f||!f.available)return`<div class="card empty">Нет обычных (не ИИС) брокерских счетов в выбранной выборке — прогноз не построен.${f&&f.iis_excluded.length?` ИИС (${f.iis_excluded.map(esc).join(', ')}) в этот прогноз не входят.`:''}</div>`;
  const r=f.forecast,sd=f.sale_day,dd=f.days_to_sale;
  const row=(a,b,c)=>`<tr><td class="l">${a}</td><td class="num">${b}</td><td class="l mu"><small>${c||''}</small></td></tr>`;
  let out=`<div class="g g4">${kpi(`Налог на 31.12.${f.year} (прогноз)`,tR(r.tax_end),`ставка на вершине ${Math.round(r.rate*100)} %`,null,S1)}
    ${kpi('Уже удержано брокером',tR(r.withheld),'по операциям этого года',null,S3)}
    ${kpi('Брокер удержит дополнительно',tR(r.to_withhold),r.refund>0?`удержано больше на ${tR(r.refund)}`:'в конце года или при выводе средств',r.to_withhold>0?'neg':'',S2)}
    ${kpi('Ожидаемые купоны и дивиденды',tR(r.exp_coupons+r.exp_dividends),f.pays_known?`выплат до конца года: ${r.exp_n}`:'прогноз выплат недоступен',null,S4)}</div>`;
  out+=`<div class="card"><h2>Прогноз налога на 31 декабря<span class="sp">обычные брокерские счета, ${f.year}</span></h2><div class="tbl"><table><tbody>
    ${row('Результат продаж (с учётом комиссий)',tS(r.trade),'FIFO по лотам')}
    ${row('Освобождение по ЛДВ и зачёт убытков прошлых лет',(r.ldv_exempt>0.5||r.carry_used>0.5)?'−'+tR(r.ldv_exempt+r.carry_used):'—')}
    ${row('Полученные купоны (с учётом НКД) и дивиденды',tR(r.coupons+r.dividends),'уже выплачены в этом году')}
    ${r.other>0.5?row('РЕПО, фьючерсы и опционы',tR(r.other)):''}
    ${row('Налоговая база на сегодня',`<b>${tR(r.base)}</b>`,`налог на сегодня: ${tR(r.tax_now)}`)}
    ${row('Ожидаемые купоны до конца года',tR(r.exp_coupons),'по графику выплат из «Выплат»; оценки не гарантированы')}
    ${row('Ожидаемые дивиденды до конца года',tR(r.exp_dividends),'только объявленные')}
    ${row('База на конец года',`<b>${tR(r.base_end)}</b>`,`13 % до ${short(r.threshold)} ₽ и 15 % выше`)}
    ${row('Налог 13 % / 15 %',`${tR(r.tax13)} / ${tR(r.tax15)}`)}
    ${row('Налог по расчёту на 31.12',`<b>${tR(r.tax_end)}</b>`)}
    ${row('Удержано брокером',tR(r.withheld))}
    ${row('Будет удержано дополнительно',`<b class="${r.to_withhold>0?'neg':''}">${tR(r.to_withhold)}</b>`,'обычно брокер удерживает налог за год в конце декабря или в январе, либо при выводе денег')}
  </tbody></table></div>
  <p class="note">${f.iis_excluded.length?`ИИС (${f.iis_excluded.map(esc).join(', ')}) в расчёт не входят: у них своя налоговая база и льготы. `:''}Прогноз выплат берётся по всему портфелю без разбивки по счетам, поэтому при смешанной выборке с ИИС ожидаемые купоны могут быть завышены. Расчёт информационный: итоговую сумму определяет брокер и декларация, сверяйтесь с брокером и ФНС.</p></div>`;
  const ha=f.harvest;
  out+=`<div class="card" style="padding:6px 8px"><h2 style="padding:10px 10px 0">Как уменьшить налог до конца года<span class="sp">информационный расчёт, не рекомендация</span></h2>
    <p class="note" style="padding:0 10px">Позиции с нереализованным убытком: если продать их в этом году, убыток уменьшит налогооблагаемую прибыль. Экономия — меньшее из убытка и прибыли года, умноженное на ставку (с учётом уже зачтённых льгот и убытков). ${dd>=0?`Чтобы сделка рассчиталась в ${f.year} году при расчётах T+1, продавать нужно не позже <b>${tDt(sd)}</b> (осталось ${dd} дн.; последний торговый день — ${tDt(f.last_trading_day)}, точная дата зависит от календаря биржи).`:`Расчётная дата ${tDt(sd)} уже прошла: новые продажи рассчитаются в следующем году.`}</p>
    <div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>Кол-во</th><th>Стоимость</th><th>Убыток</th><th>Экономия налога</th><th>Комиссия + спред</th><th>Выгода</th></tr></thead><tbody>${
      ha.length?ha.map(c=>`<tr><td class="l"><b>${esc(c.name)}</b><br><small class="mu">${esc(c.ticker)}${c.ldv_days?` · <span class="neg">через ${c.ldv_days} дн. часть лотов получит ЛДВ</span>`:''}</small></td><td class="num">${NF0.format(c.qty)}</td><td class="num">${tR(c.value)}</td><td class="num neg">−${tR(c.loss)}</td><td class="num pos">${tR(c.saving)}</td><td class="num">${tR(c.cost)}</td><td class="num ${c.net>0?'pos':'neg'}"><b>${tS(c.net)}</b></td></tr>`).join(''):'<tr><td colspan="7" class="l mu">Подходящих позиций нет: либо убытков нет, либо налог за год ещё не начислен.</td></tr>'}</tbody></table></div>
    ${ha.length?`<p class="note" style="padding:0 10px">Общая экономия при продаже всего списка: около ${tR(f.harvest_saving)} (до комиссий): каждая следующая продажа экономит меньше, когда прибыль уже покрыта.</p>`:''}
    ${f.skipped.length?`<p class="note" style="padding:0 10px"><b>Не включены:</b> ${f.skipped.map(c=>`${esc(c.ticker||c.name)} — ${esc(c.reason)}`).join('; ')}.</p>`:''}
    <p class="note" style="padding:0 10px">Откупить ту же бумагу сразу после продажи законом не запрещено, но срок владения для ЛДВ начнётся заново, а средняя цена покупки изменится. Для ИИС подсказки не строятся. Оцените комиссии, спред и последствия сами и сверьтесь с брокером и ФНС.</p></div>`;
  return out;
}

/* ── Для декларации ── */
function txDecl(d){
  const ys=Object.keys(d.decl).map(Number).sort((a,b)=>b-a);
  if(!ys.length)return`<div class="card empty">Нет данных для декларации</div>`;
  const y=ys.includes(+S.tx.year)?+S.tx.year:ys[0],dc=d.decl[y];
  const sel=`<div class="row noprint" style="margin-bottom:12px;gap:12px"><label class="field" style="max-width:200px"><span>Налоговый год</span><select class="in" onchange="S.tx.year=this.value;render()">${ys.map(v=>`<option value="${v}" ${v===y?'selected':''}>${v}</option>`).join('')}</select></label>
    <button class="btn ghost" onclick="window.print()">Печать</button></div>`;
  const wk=w=>Object.keys(w).filter(k=>Math.abs(w[k])>0.005).map(k=>`${esc(L[k]||k)}: ${tR(w[k])}`).join('; ');
  const ii=Object.fromEntries(d.iis.map(i=>[i.id,i]));
  return sel+dc.groups.map(g=>{
    const rowsT=[
      ['Доходы от продажи ценных бумаг',tR(g.proceeds)],['Расходы (покупка, комиссии)',tR(g.cost+g.fees)],['Финансовый результат по сделкам',tS(g.trade)],
      ['Освобождение по ЛДВ',g.ldv_exempt>0.5?'−'+tR(g.ldv_exempt):'—'],['Убытки прошлых лет (зачтено)',g.carry_used>0.5?'−'+tR(g.carry_used):'—'],
      ['Налоговая база по сделкам',tR(g.trade_base)],['Дивиденды',tR(g.dividends)],['Купоны (с учётом НКД)',tR(g.coupons)],['Доход по РЕПО',tR(g.overnight)],['Фьючерсы и опционы',tS(g.deriv)],
      ['Общая налоговая база',`<b>${tR(g.base)}</b>`],['Налог 13 %',tR(g.tax13)],['Налог 15 %',tR(g.tax15)],['Налог по расчёту',`<b>${tR(g.tax)}</b>`],
      ['Удержано брокером',tR(g.withheld)+(wk(g.w)?`<br><small class="mu">${wk(g.w)}</small>`:'')],['К доплате (+) / возврату (−)',`<b class="${g.diff>0.5?'neg':g.diff<-0.5?'pos':''}">${tS(g.diff)}</b>`],
      ['Убыток года к переносу на будущие годы',g.loss_new>0.5?tR(g.loss_new):'—']];
    const i=ii[g.key.replace('iis:','')];
    const iis=i&&(i.type==='A'||i.type==='3')?(i.years.find(v=>v.year===y)||null):null;
    return`<div class="card"><h2>${esc(g.name)}<span class="sp">${y}</span></h2><div class="tbl"><table><tbody>${rowsT.map(r=>`<tr><td class="l">${r[0]}</td><td class="num">${r[1]}</td></tr>`).join('')}</tbody></table></div>
      ${iis?`<p class="note"><b>Вычет по ИИС (тип А):</b> взносы за год ${tR(iis.deposits)}, в вычет идёт ${tR(iis.deduct_base)}, к возврату до ${tR(iis.deduct)} (не больше уплаченного НДФЛ).</p>`:''}
      ${g.lines.length?`<h3 style="margin:14px 0 6px;font-size:13px">Сделки по бумагам (до 80 крупнейших по результату)</h3><div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>Кол-во</th><th>Выручка</th><th>Расход</th><th>Комиссия продажи</th><th>Результат</th><th>из них ЛДВ</th></tr></thead><tbody>${
        g.lines.map(l=>`<tr><td class="l">${esc(l.name)}<br><small class="mu">${esc(l.ticker)}${l.kind==='repay'?' · погашение':l.kind==='amort'?' · амортизация':l.kind==='writeoff'?' · списание остатка':l.kind==='short'?' · шорт':''}</small></td><td class="num">${NF0.format(l.qty)}</td><td class="num">${tR(l.proceeds)}</td><td class="num">${tR(l.cost)}</td><td class="num">${tR(l.fee)}</td><td class="num ${cls(l.result)}">${tS(l.result)}</td><td class="num">${Math.abs(l.ldv_result)>0.5?tS(l.ldv_result):'—'}</td></tr>`).join('')}</tbody></table></div>`:''}</div>`}).join('')+
    `<p class="note">Данные для заполнения 3-НДФЛ — справочные. Если налог удержан брокером полностью, декларация нужна, чтобы заявить вычет по ИИС, ЛДВ или перенос убытка. Справку о доходах и удержанном налоге запросите у брокера.</p>`;
}

/* ── Настройки налогов ── */
function txDraft(d){
  if(!S.tx.draft){const s=d.settings;S.tx.draft={iis:JSON.parse(JSON.stringify(s.iis||{})),loss:Object.keys(s.loss_carry||{}).sort().map(y=>({y:y,a:String(s.loss_carry[y])})),off:!!s.offset_coupons}}
  return S.tx.draft;
}
function txIn(el){
  const dr=S.tx.draft,k=el.dataset.k;
  if(k==='iis'){dr.iis[el.dataset.id]=dr.iis[el.dataset.id]||{type:'',opened:''};dr.iis[el.dataset.id][el.dataset.f]=el.value}
  else if(k==='loss'){dr.loss[+el.dataset.i][el.dataset.f]=el.value}
  else if(k==='off'){dr.off=el.checked}
}
function txLossAdd(y,a){const dr=S.tx.draft;if(y&&dr.loss.some(r=>String(r.y)===String(y)))return;dr.loss.push({y:y?String(y):'',a:a?String(Math.round(a)):''});render()}
function txLossDel(i){S.tx.draft.loss.splice(i,1);render()}
async function txSave(btn){
  const dr=S.tx.draft;btn.disabled=true;
  try{
    const lc={};for(const r of dr.loss){const y=String(r.y).trim(),a=parseFloat(String(r.a).replace(/\s/g,'').replace(',','.'));if(y&&a>0)lc[y]=a}
    await post('/api/tax/settings',{iis:dr.iis,loss_carry:lc,offset_coupons:dr.off});
    S.tx.msg='Сохранено';S.tx.data=null;S.tx.acc=null;render()
  }catch(e){S.tx.msg=e.message;btn.disabled=false;render()}
}
function txSet(d){
  const dr=txDraft(d);
  const iisCards=d.iis.length?d.iis.map(i=>{const c=dr.iis[i.id]||{type:'',opened:''};
    return`<div class="row" style="gap:14px;flex-wrap:wrap;margin-bottom:10px;align-items:flex-end"><div style="min-width:180px"><b>${esc(i.name)}</b><br><small class="mu">дата из API: ${tDt(i.opened)}</small></div>
      <label class="field" style="max-width:230px"><span>Тип ИИС</span><select class="in" data-k="iis" data-id="${esc(i.id)}" data-f="type" onchange="txIn(this)">
        ${[['','Не указан (считать как А)'],['A','А — вычет на взносы'],['B','Б — освобождение дохода'],['3','ИИС-3 (с 2024 года)']].map(([v,t])=>`<option value="${v}" ${c.type===v?'selected':''}>${t}</option>`).join('')}</select></label>
      <label class="field" style="max-width:190px"><span>Дата открытия</span><input class="in" type="date" data-k="iis" data-id="${esc(i.id)}" data-f="opened" value="${esc(c.opened||'')}" onchange="txIn(this)"></label></div>`}).join(''):'<div class="note">Среди выбранных счетов нет ИИС.</div>';
  const loss=dr.loss.map((r,i)=>`<div class="row" style="gap:10px;margin-bottom:8px;align-items:flex-end"><label class="field" style="max-width:110px"><span>Год убытка</span><input class="in num" type="number" min="2000" max="2100" value="${esc(r.y)}" data-k="loss" data-i="${i}" data-f="y" oninput="txIn(this)"></label>
      <label class="field" style="max-width:200px"><span>Непогашенный убыток, ₽</span><input class="in num" type="text" value="${esc(r.a)}" data-k="loss" data-i="${i}" data-f="a" oninput="txIn(this)"></label>
      <button class="btn ghost" onclick="txLossDel(${i})">Убрать</button></div>`).join('');
  const sug=d.carry_suggest.filter(s=>!dr.loss.some(r=>String(r.y)===String(s.year)));
  return`<div class="card"><h2>Счета ИИС</h2>${iisCards}</div>
    <div class="card"><h2>Убытки прошлых лет<span class="sp">для переноса на будущие доходы (до 10 лет)</span></h2>
      <p class="note">Внесите убытки, которые числятся за вами по прошлым декларациям или справкам брокера. Если для года указана сумма, она заменяет расчётный убыток этого года.</p>
      ${loss||'<div class="note" style="margin-bottom:8px">Пока ничего не внесено.</div>'}
      <div class="row" style="gap:10px"><button class="btn ghost" onclick="txLossAdd('','')">+ Добавить год</button></div>
      ${sug.length?`<h3 style="margin:14px 0 6px;font-size:13px">Предложение по расчёту</h3>${sug.map(s=>`<div class="row" style="gap:10px;margin-bottom:6px"><span>${s.year}: убыток по расчёту <b>${tR(s.loss)}</b></span><button class="btn ghost" onclick="txLossAdd(${s.year},${Math.round(s.loss)})">Взять</button></div>`).join('')}`:''}</div>
    <div class="card"><h2>Правила расчёта</h2><label class="sw"><input type="checkbox" ${dr.off?'checked':''} data-k="off" onchange="txIn(this)"><i></i><div><b>Убыток по сделкам уменьшает купонный доход</b><small>включите, если так считает ваш брокер; по умолчанию убыток гасит только прибыль по сделкам</small></div></label></div>
    <div class="row noprint" style="gap:12px;margin-top:6px"><button class="btn" onclick="txSave(this)">Сохранить и пересчитать</button><span class="${/^Сохранено/.test(S.tx.msg)?'pos':'neg'}">${esc(S.tx.msg||'')}</span></div>`;
}
