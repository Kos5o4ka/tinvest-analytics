/* ── Комиссии + Оптимизатор тарифа брокера (#10) ── */
function feeTariffOptimizer(){
  const d=S.data,ms=(d.months||[]).slice(-12);
  if(!ms.length)return'';
  const portVal=(d.portfolio&&d.portfolio.total)||0;
  let turn12=0,activeMo=0,paid12=0;
  ms.forEach(([,r])=>{
    const tv=(r.buy_turnover||0)+(r.sell_turnover||0);
    turn12+=tv;if(tv>0)activeMo++;
    paid12+=(r.fee_broker||0)+(r.fee_service||0);
  });
  if(turn12<=0&&paid12<=0)return'';
  const nMo=ms.length;
  const tariffs=[
    {name:'Инвестор',rate:0.003,sub:0,cost:turn12*0.003,note:'0,30 % за сделку, без абонплаты'},
    {name:'Трейдер',rate:0.0005,sub:portVal>=2e6?0:290*activeMo,
     cost:turn12*0.0005+(portVal>=2e6?0:290*activeMo),
     note:portVal>=2e6?'0,05 % за сделку, 0 ₽/мес (портфель ≥ 2 млн ₽)':'0,05 % за сделку + 290 ₽ в месяцы со сделками'},
    {name:'Премиум',rate:0.0004,sub:portVal>=3e6?0:1990*nMo,
     cost:turn12*0.0004+(portVal>=3e6?0:1990*nMo),
     note:portVal>=3e6?'0,04 % за сделку, 0 ₽/мес (портфель ≥ 3 млн ₽)':'0,04 % за сделку + 1 990 ₽/мес'}
  ];
  const best=tariffs.reduce((a,b)=>b.cost<a.cost?b:a);
  const save=Math.max(0,paid12-best.cost);
  const avgMoTurn=turn12/Math.max(1,activeMo);
  return`<div class="card"><h2>Оптимизатор тарифа брокера<span class="sp">модель по вашему обороту за последние ${nMo} мес. (${short(turn12)} ₽, активных мес.: ${activeMo})</span></h2>
    <div class="g g4" style="margin-bottom:12px">
      ${kpi('Фактически уплачено',M(paid12,'rub',0),'брокерская + обслуживание за '+nMo+' мес.')}
      ${kpi('Оптимальный тариф',esc(best.name),M(best.cost,'rub',0)+' расчётно за период','pos')}
      ${kpi('Потенциальная экономия',save>100?M(save,'rub',0):'0 ₽',save>100?'можно сэкономить на смене тарифа':'ваш текущий тариф уже близок к оптимуму',save>100?'pos':'')}
      ${kpi('Порог «Инвестор → Трейдер»','116 тыс ₽/мес','ваш ср. оборот: '+short(avgMoTurn)+' ₽/акт. мес.')}</div>
    <div class="tbl"><table><thead><tr><th class="l">Тариф Т-Инвестиций</th><th>Ставка</th><th>Комиссия с оборота</th><th>Абонплата</th><th>Итого за ${nMo} мес.</th><th class="l">Условия</th></tr></thead><tbody>`+
    tariffs.map(x=>`<tr class="${x===best?'pnew':''}"><td class="l"><b>${esc(x.name)}</b>${x===best?' <span class="tag pos">выгоднее</span>':''}</td>
      <td class="num">${(x.rate*100).toFixed(2).replace('.',',')} %</td><td class="num">${M(turn12*x.rate,'rub',0)}</td>
      <td class="num">${M(x.sub,'rub',0)}</td><td class="num"><b>${M(x.cost,'rub',0)}</b></td><td class="l mu">${esc(x.note)}</td></tr>`).join('')+`</tbody></table></div>
    <p class="note" style="margin-top:8px">Справочная модель для стандартных тарифов Т-Инвестиций без учёта сделок с фондами Т-Капитала (0 %) и фьючерсов. Точка безубыточности «Инвестор → Трейдер»: 290 / (0,30% − 0,05%) = 116 000 ₽ оборота в месяц.</p></div>`;
}
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
  out+=feeTariffOptimizer();
  const other=Object.keys(d.totals).filter(c=>c!=='rub'&&FEEK.some(k=>d.totals[c][k]));
  if(other.length)out+=`<div class="card"><h2>Комиссии в других валютах</h2><table><thead><tr><th>Статья</th>${other.map(c=>`<th>${sym(c)}</th>`).join('')}</tr></thead><tbody>`+
    FEEK.map(k=>`<tr><td>${L[k]}</td>${other.map(c=>`<td class="num">${M(d.totals[c][k]||0,c)}</td>`).join('')}</tr>`).join('')+'</tbody></table></div>';
  return out;
}

