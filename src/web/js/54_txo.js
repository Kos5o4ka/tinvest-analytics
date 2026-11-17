/* ── Налоговая оптимизация: сбор убытков по лотам FIFO и планировщик ИИС-3 ── */
S.txo={h:null,hAcc:null,hBusy:0,hErr:null,fee:'',p:null,pBusy:0,pErr:null,F:null};
try{S.txo.F=JSON.parse(localStorage.getItem('txo_iis3')||'null')}catch(e){}
const txoR=n=>bad(n)?'—':M(n,'rub',0),txoS=n=>bad(n)?'—':(n>0?'+':'')+M(n,'rub',0);
const TXO_NOTE='<p class="note">Расчёт по модели и справочный: проверьте его с брокерским отчётом; налог удерживает брокер, итог за год определяется декларацией. Допущения указаны в блоках.</p>';
function txoF(){
  return Object.assign({open_year:new Date().getFullYear(),contribution:400000,yield:12,years:10,bracket:'13',income:'',coupon_share:50,reinvest:'1',ldv:'1'},S.txo.F||{});
}
function txoLoadH(force){
  if(S.txo.hBusy)return;S.txo.hBusy=1;const acc=S.account;
  const p=Object.assign({account:acc},S.txo.fee!==''?{fee:S.txo.fee}:{},force?{force:'1'}:{});
  api('/api/txo/harvest?'+new URLSearchParams(p)).then(j=>{S.txo.hBusy=0;S.txo.hAcc=acc;S.txo.hErr=null;S.txo.h=j;if(S.page==='txo'&&S.account===acc)renderSoon()})
   .catch(e=>{S.txo.hBusy=0;S.txo.hAcc=acc;S.txo.h=null;S.txo.hErr=e.message;if(S.page==='txo')renderSoon()});
}
function txoLoadP(){
  if(S.txo.pBusy)return;S.txo.pBusy=1;
  api('/api/txo/iis3?'+new URLSearchParams(Object.fromEntries(Object.entries(txoF()).filter(([k,v])=>v!==''&&v!=null)))).then(j=>{S.txo.pBusy=0;S.txo.pErr=null;S.txo.p=j;if(S.page==='txo')renderSoon()})
   .catch(e=>{S.txo.pBusy=0;S.txo.pErr=e.message;if(S.page==='txo')renderSoon()});
}
function txoHarvest(){
  const h=S.txo.h;
  if(S.txo.hErr&&S.txo.hAcc===S.account)return`<div class="msg err">${esc(S.txo.hErr)} <button class="btn ghost" onclick="S.txo.hErr=null;S.txo.hAcc=null;render()">Повторить</button></div>`;
  if(!h||S.txo.hAcc!==S.account){txoLoadH();return waitBox('Считаю лоты и налог текущего года…')}
  const ex=(h.iis_excluded||[]).map(x=>`<p class="note"><b>${esc(x.name)}</b>: ${esc(x.reason)}</p>`).join('');
  if(!h.available)return`<div class="empty">${esc(h.reason||'Нет данных для расчёта')}</div>${ex}`;
  const d=h.deadline,t=h.totals;
  let out=`<div class="g g4">${kpi('Экономия налога',txoR(t.saving),`налог ${h.year}: ${txoR(h.tax_before)} → ${txoR(t.tax_after)}`,t.saving>0?'pos':'',S3)}
    ${kpi('Комиссии туда-обратно',txoR(t.fees),'продажа и обратная покупка',null,S4)}
    ${kpi('Чистая выгода модели',txoR(t.net),`позиций в наборе: ${t.n}`,t.net>0?'pos':'',S1)}
    ${kpi('Последний день сделки',ddm(d.sale_day),d.passed?'срок для этого года прошёл':`осталось ${d.days} дн. (T+1, торги до ${ddm(d.last_trading_day)})`,d.passed?'neg':'',S2)}</div>
    <div class="row noprint" style="margin:10px 0"><label class="field"><span>Комиссия, % (пусто — по истории)</span><input class="in" id="txo-fee" type="number" step="0.01" min="0" value="${esc(S.txo.fee)}" style="width:140px"></label>
      <button class="btn" id="txo-fee-go">Пересчитать</button></div>`;
  if(!h.candidates.length)out+='<div class="empty">Бумаг с нереализованным убытком, продажа которых снизила бы налог, модель не нашла (или налога за год пока нет).</div>';
  else out+=`<div class="tbl"><table><thead><tr><th>Бумага</th><th>Продать (старые лоты)</th><th>Убыток</th><th>Прибыль в префиксе</th><th>Ставка</th><th>Экономия</th><th>Комиссии</th><th>Чистая выгода</th><th>Примечания</th></tr></thead><tbody>${h.candidates.map(c=>{
      const nt=[];
      if(c.selected)nt.push('<span class="tag">в наборе</span>');
      if(c.carry_forward>1)nt.push(`<small class="mu">убыток сверх базы ${txoR(c.carry_forward)} перенесётся</small>`);
      if(c.blind)nt.push('<small class="txo-warn">лоты из перевода: стоимость могла быть неизвестна</small>');
      c.ldv.forEach(l=>nt.push(`<span class="tag txo-ldv">ЛДВ ${l.status==='reached'?'наступила':`через ${l.days} дн.`}</span> <small class="mu">${ddm(l.bdate)}: прибыль ${txoR(l.gain)}${l.tax_at_stake?`, налог без ЛДВ ≈ ${txoR(l.tax_at_stake)}`:''}; после обратной покупки срок начнётся заново</small>`));
      return`<tr><td class="l"><b>${esc(c.name)}</b><br><small class="mu">${esc(c.ticker)}</small></td><td class="num">${f2(c.qty)}${c.partial?` из ${f2(c.qty_total)}`:''}<br><small class="mu">${txoR(c.value)}</small></td>
        <td class="num neg">${txoR(-c.loss)}</td><td class="num">${txoR(c.gain_in_prefix)}</td><td class="num">${c.marginal_rate==null?'—':pctp(c.marginal_rate*100,0)}</td>
        <td class="num pos">${txoR(c.saving)}</td><td class="num">${txoR(c.fees)}</td><td class="num ${c.net>0?'pos':'neg'}"><b>${txoS(c.net)}</b></td><td class="l">${nt.join('<br>')}</td></tr>`}).join('')}</tbody></table></div>`;
  out+=`<ul class="txo-ul"><li>${(h.assumptions||[]).map(esc).join('</li><li>')}</li></ul>${ex}`;
  if((h.warnings||[]).length)out+=`<p class="note">${h.warnings.map(esc).join('<br>')}</p>`;
  out+=`<p class="note noprint">Общая картина по налогам и простые подсказки — на странице <a href="#" onclick="go('tax');return false">«Налоги»</a>.</p>`;
  return out;
}
function txoPlanner(){
  const F=txoF(),p=S.txo.p;
  const num=(id,l,v,o)=>`<label class="field"><span>${l}</span><input class="in txo-in" id="txo-${id}" type="number" inputmode="decimal" value="${esc(v)}" ${o||''}></label>`;
  const sel=(id,l,opts,v)=>`<label class="field"><span>${l}</span><select class="in txo-in" id="txo-${id}">${opts.map(o=>`<option value="${o[0]}" ${String(o[0])===String(v)?'selected':''}>${o[1]}</option>`).join('')}</select></label>`;
  const pre=S.txo.h&&S.txo.h.iis_prefill;
  let out=`<div class="txo-form">${num('open_year','Год открытия ИИС-3',F.open_year,'step="1" min="2024"')}${num('contribution','Взнос в год, ₽',F.contribution,'step="10000" min="0"')}
    ${num('yield','Доходность, % годовых',F.yield,'step="0.5"')}${num('years','Горизонт, лет',F.years,'step="1" min="1" max="40"')}
    ${sel('bracket','Ставка плательщика',[['13','13 % (доход до 2,4 млн ₽)'],['15','15 % (доход выше 2,4 млн ₽)']],F.bracket)}
    ${num('income','Доход за год, ₽ (необязательно)',F.income,'step="100000" min="0"')}
    ${num('coupon_share','Доля купонов в доходности, %',F.coupon_share,'step="5" min="0" max="100"')}
    ${sel('reinvest','Вычет',[['1','реинвестировать'],['0','оставить наличными']],F.reinvest)}
    ${sel('ldv','ЛДВ на обычном счёте',[['1','учитывать'],['0','не учитывать']],F.ldv)}</div>
    <p class="note">Если указан доход за год, ставка (15 % выше 2,4 млн ₽) и предел вычета (не больше уплаченного НДФЛ) определяются по нему.</p>
    ${pre?`<p class="note noprint">У вас есть ИИС «${esc(pre.name)}» (открыт ${ddm(pre.opened)}, тип ${esc(pre.type)}). <a href="#" onclick="txoPrefill(${pre.open_year});return false">Подставить год открытия</a>.</p>`:''}`;
  if(S.txo.pErr)return out+`<div class="msg err">${esc(S.txo.pErr)}</div>`;
  if(!p){txoLoadP();return out+waitBox('Считаю…')}
  const r=p.rules,i=p.iis,b=p.broker;
  out+=`<div class="g g4">${kpi('Минимальный срок',`${r.term} лет`,`до конца ${r.term_end_year} г.; горизонт ${p.inputs.years} лет`,r.term_ok?'pos':'neg',S1)}
    ${kpi('Вычет в год (максимум)',txoR(r.max_refund),`${pctp(r.rate*100,0)} от ${txoR(r.limit)}`,null,S2)}
    ${kpi('ИИС-3: итог после налогов',txoR(i.net),`на ${txoR(p.own)} своих взносов`,i.net>=b.net?'pos':'',S3)}
    ${kpi('Обычный счёт: итог',txoR(b.net),`разница ИИС-3 ${txoS(p.advantage)}`,p.advantage>=0?'pos':'neg',S4)}</div>
    <div class="tbl" style="margin-top:12px"><table><thead><tr><th>Год</th><th>Взнос</th><th>Вычет за год</th><th>ИИС-3, капитал на конец года</th><th>Обычный счёт, капитал</th><th>Налог с купонов (обычный)</th></tr></thead><tbody>${
      p.rows.map(x=>`<tr><td><b>${x.year}</b></td><td class="num">${txoR(x.contribution)}</td><td class="num pos">${txoR(x.refund)}</td><td class="num">${txoR(x.iis_capital)}</td><td class="num">${txoR(x.broker_capital)}</td><td class="num">${txoR(x.broker_coupon_tax)}</td></tr>`).join('')}</tbody></table></div>
    <div id="txo-ch" class="chart txo-chart"></div>
    <h3 class="txo-sub">Итог на конец горизонта</h3>
    <div class="tbl"><table><thead><tr><th></th><th>ИИС-3</th><th>Обычный счёт</th></tr></thead><tbody>
      <tr><td class="l">Капитал до налога при закрытии</td><td class="num">${txoR(i.capital)}</td><td class="num">${txoR(b.capital)}</td></tr>
      <tr><td class="l">Налог при закрытии / продаже</td><td class="num">${txoR(i.tax)}</td><td class="num">${txoR(b.exit_tax)}${b.ldv_exempt>0?`<br><small class="mu">освобождено ЛДВ: ${txoR(b.ldv_exempt)}</small>`:''}</td></tr>
      <tr><td class="l">Налог с купонов за время владения</td><td class="num">${r.term_ok?'0 ₽ (срок соблюдён)':'входит в налог при закрытии'}</td><td class="num">${txoR(b.coupon_tax)}</td></tr>
      <tr><td class="l">Вычеты получено / возвращено</td><td class="num">${txoR(i.refunds_total)} / ${txoR(i.refunds_returned)}</td><td class="num">—</td></tr>
      <tr><td class="l"><b>Итог после налогов</b></td><td class="num"><b>${txoR(i.net)}</b></td><td class="num"><b>${txoR(b.net)}</b></td></tr>
      <tr><td class="l">Результат к своим взносам (${txoR(p.own)})</td><td class="num ${i.result_over_own>=0?'pos':'neg'}">${txoS(i.result_over_own)}</td><td class="num ${b.result_over_own>=0?'pos':'neg'}">${txoS(b.result_over_own)}</td></tr></tbody></table></div>`;
  if(p.early.length)out+=`<h3 class="txo-sub">Досрочное закрытие до истечения срока</h3>
    <div class="tbl"><table><thead><tr><th>Закрытие в году</th><th>Капитал</th><th>Вычеты вернуть</th><th>Налог с дохода</th><th>Итого после возврата и налога</th><th>Потеряно относительно срока</th></tr></thead><tbody>${p.early.map(e=>`<tr><td><b>${e.year}</b> <small class="mu">(${e.n}-й год)</small></td><td class="num">${txoR(e.capital)}</td><td class="num neg">${txoR(e.refunds_returned)}</td><td class="num neg">${txoR(e.tax)}</td><td class="num">${txoR(e.net)}</td><td class="num neg">${txoR(e.extra_cost)}</td></tr>`).join('')}</tbody></table></div>`;
  if((p.warnings||[]).length)out+=`<p class="note txo-warn">${p.warnings.map(esc).join('<br>')}</p>`;
  out+=`<ul class="txo-ul"><li>Правила (НК РФ ст. 219.1, 219.2): вычет 13 % (15 % при доходе выше 2,4 млн ₽) с взносов до 400 000 ₽ в год — не больше 52 000 / 60 000 ₽ в год и не больше уплаченного НДФЛ; при соблюдении минимального срока освобождается положительный финансовый результат до 30 млн ₽ за всё время. Минимальный срок по году открытия: 2024–2026 — 5 лет, 2027 — 6, 2028 — 7, 2029 — 8, 2030 — 9, с 2031 — 10.</li>
    <li>Допущения модели: взнос в начале года, доходность в конце года, вычет за год поступает в начале следующего (последний — после горизонта); на обычном счёте купоны облагаются налогом ежегодно, прирост цены — при продаже в конце горизонта, ЛДВ — по лотам, купленным более трёх лет назад, в пределах 3 млн ₽ × лет владения.</li>
    <li>Отличие от <a href="#" onclick="go('calc');return false">калькулятора</a>: там ИИС-3 — один из сценариев сравнения стратегий вложений; здесь отдельно учтены срок по году открытия, ставка 13/15 %, предел вычета по НДФЛ, годовая таблица и досрочное закрытие.</li></ul>`;
  return out;
}
function txoPrefill(y){S.txo.F=Object.assign(txoF(),{open_year:y});S.txo.p=null;txoSave();render()}
function txoSave(){try{localStorage.setItem('txo_iis3',JSON.stringify(S.txo.F))}catch(e){}}
function pTxo(){
  const p=S.txo.p;
  if(p&&p.rows.length)chart('txo-ch',line,{labels:p.rows.map(r=>String(r.year)),h:220,series:[{n:'ИИС-3',c:S1,v:p.rows.map(r=>r.iis_capital)},{n:'Обычный счёт',c:S2,v:p.rows.map(r=>r.broker_capital)},{n:'Свои взносы',c:S4,v:p.rows.map(r=>r.own)}]});
  return`<div class="txo"><div class="card"><h2>Сбор налоговых убытков (${new Date().getFullYear()} год)</h2>
    <p class="note">Модель показывает, при каком наборе продаж налог текущего года снизился бы сильнее всего и сколько останется после комиссий. Это не рекомендация что-либо продавать.</p>${txoHarvest()}</div>
    <div class="card"><h2>Планировщик ИИС-3 <span class="sp">сравнение с обычным счётом</span></h2>${txoPlanner()}</div>${TXO_NOTE}${NIR_NOTE}</div>`;
}
function bindTxo(){
  const g=document.getElementById('txo-fee-go');
  if(g)g.onclick=()=>{S.txo.fee=(document.getElementById('txo-fee').value||'').trim();S.txo.h=null;S.txo.hAcc=null;render()};
  document.querySelectorAll('.txo-in').forEach(el=>{el.addEventListener('change',()=>{
    const F=txoF();document.querySelectorAll('.txo-in').forEach(e=>{F[e.id.slice(4)]=e.value});
    S.txo.F=F;txoSave();S.txo.p=null;render()})});
}
regPage('txo',{title:'Налоговая оптимизация',group:'Учёт и планы',icon:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16M6 16l4-5 3 3 5-7"/><circle cx="7" cy="7" r="2"/></svg>',render:pTxo,bind:bindTxo,pro:true});
