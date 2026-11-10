/* ── Комиссии ── */
function pFees(){
  const d=S.data;let out='';
  const t=T(),total=sumK(t,FEEK),turn=(t.buy_turnover||0)+(t.sell_turnover||0);
  out+=`<div class="g g4">${kpi('Все комиссии и плата за маржу',M(total),periodName(),null,S2)}${kpi('Комиссия брокера',M(t.fee_broker||0),turn?`${f2((t.fee_broker||0)/turn*100)} % от оборота ${short(turn)} ₽`:'',null,S1)}
    ${kpi('Обслуживание + прочее',M((t.fee_service||0)+(t.fee_other||0)),'тариф, вывод, прочие сборы',null,S3)}${kpi('Плата за маржу',M(t.margin_fee||0),'перенос непокрытых позиций',null,S5)}</div>`;
  const items=[['fee_broker',S1],['fee_service',S3],['fee_other',S4],['margin_fee',S5]];
  const ms=monthsSeries();
  chart('c-fees',bars,{labels:ms.labels,tipLabels:ms.tips,stack:true,total:true,skipZero:true,series:items.map(([k,c])=>({n:L[k],c,v:ms.rows.map(r=>r[k]||0)}))});
  out+=`<div class="g c-2-1"><div class="card"><h2>Комиссии по месяцам, ₽<span class="sp">${periodName()}</span></h2><div id="c-fees" class="chart"></div></div>
    <div class="card"><h2>Структура расходов, ₽</h2>${total?hbars(items.filter(([k])=>t[k]).map(([k,c])=>({n:L[k],v:t[k]||0,c,s:pctp((t[k]||0)/total*100)})),S1,null,1):'<div class="empty">Комиссий нет</div>'}
    <p class="note" style="margin-top:16px">Положительная сумма — уплачено, возвраты её уменьшают.</p></div></div>`;
  const other=Object.keys(d.totals).filter(c=>c!=='rub'&&FEEK.some(k=>d.totals[c][k]));
  if(other.length)out+=`<div class="card"><h2>Комиссии в других валютах</h2><table><thead><tr><th>Статья</th>${other.map(c=>`<th>${sym(c)}</th>`).join('')}</tr></thead><tbody>`+
    FEEK.map(k=>`<tr><td>${L[k]}</td>${other.map(c=>`<td class="num">${M(d.totals[c][k]||0,c)}</td>`).join('')}</tr>`).join('')+'</tbody></table></div>';
  return out;
}

