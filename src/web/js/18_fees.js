/* ── Комиссии + Оптимизатор тарифа брокера (#10) ── */
function feeTariffOptimizer(){
  const fm=(S.data||{}).fee_model;
  if(!fm||(fm.turnover<=0&&fm.paid<=0))return'';
  const dmy=x=>{const[y,m,d]=String(x).split('-');return d+'.'+m+'.'+y.slice(2)};
  const tariffs=fm.tariffs||[],best=tariffs.find(x=>x.name===fm.best)||null;
  const save=fm.save||0,eff=fm.eff_rate;
  const effTxt=eff==null?'нет комиссий за период':'≈ '+(eff*100).toFixed(3).replace('.',',')+' % от оборота'+(fm.current?' · похоже на тариф «'+fm.current+'»':'');
  const avgMoTurn=fm.turnover/Math.max(1,fm.active_months);
  let saveSub,saveCls='';
  if(!best){saveSub='нет оборота по биржевым сделкам'}
  else if(fm.below_model){saveSub='вы платите меньше модели: часть сделок без комиссии (фонды Т-Капитала, акции с нулевой ставкой, акции-приманки брокера) — модель рассчитана на стандартные ставки'}
  else if(save>100){saveSub='можно сэкономить на смене тарифа';saveCls='pos'}
  else saveSub='ваш текущий тариф уже близок к оптимальному';
  const othTxt=(fm.other_accounts||[]).length?' Счета других брокеров ('+fm.other_accounts.map(esc).join(', ')+') в модель не входят — у них свои тарифы, см. блок ниже.':'';
  const exTxt=fm.excluded>0?' В расчёт не вошли сделки без процентной комиссии: '+short(fm.excluded)+' ₽ (фонды Т-Капитала, валюта, срочный рынок, поставка).':'';
  return`<div class="card"><h2>Оптимизатор тарифа брокера<span class="sp" style="white-space:normal">всегда по последним 12 мес.: ${dmy(fm.from)} — ${dmy(fm.to)}, не зависит от выбранного периода · оборот ${short(fm.turnover)} ₽, активных мес.: ${fm.active_months}</span></h2>
    <div class="g g4 feeopt" style="margin-bottom:12px">
      ${kpi('Фактически уплачено',M(fm.paid,'rub',0),'брокерская '+M(fm.paid_broker,'rub',0)+' + обслуживание '+M(fm.paid_service,'rub',0)+' за 12 мес.')}
      ${kpi('Фактическая ставка',eff==null?'—':(eff*100).toFixed(3).replace('.',',')+' %',esc(effTxt))}
      ${best?kpi('Оптимальный тариф',esc(best.name),M(best.cost,'rub',0)+' расчётно за 12 мес.','pos'):kpi('Оптимальный тариф','—','нет данных')}
      ${kpi('Потенциальная экономия',save>100?M(save,'rub',0):'0 ₽',saveSub,saveCls)}</div>
    <p class="note" style="margin:0 0 8px">Порог «Инвестор → Трейдер»: 156 тыс ₽ оборота в месяц; ваш ср. оборот: ${short(avgMoTurn)} ₽/акт. мес.</p>
    <div class="tbl"><table><thead><tr><th class="l">Тариф Т-Инвестиций</th><th>Ставка</th><th>Комиссия с оборота</th><th>Абонплата</th><th>Итого за 12 мес.</th><th class="l">Условия</th></tr></thead><tbody>`+
    tariffs.map(x=>`<tr class="${best&&x.name===best.name?'pnew':''}"><td class="l"><b>${esc(x.name)}</b>${best&&x.name===best.name?' <span class="tag pos">выгоднее</span>':''}${x.name===fm.current?' <span class="tag">ваш, вероятно</span>':''}</td>
      <td class="num">${(x.rate*100).toFixed(2).replace('.',',')} %</td><td class="num">${M(x.fee,'rub',0)}</td>
      <td class="num">${M(x.sub,'rub',0)}</td><td class="num"><b>${M(x.cost,'rub',0)}</b></td><td class="l mu">${esc(x.note)}</td></tr>`).join('')+`</tbody></table></div>
    <p class="note" style="margin-top:8px">Справочная модель для стандартных тарифов Т-Инвестиций: оборот считается только по биржевым покупкам и продажам в рублях (без погашений, купонов, РЕПО, конвертаций и переводов бумаг).${exTxt} Точка безубыточности «Инвестор → Трейдер»: 390 / (0,30% − 0,05%) = 156 000 ₽ оборота в месяц. Тарифы — по справке Т-Инвестиций (ноябрь 2026): «Инвестор» от 0,3 % без абонплаты, «Трейдер» от 0,05 % + 390 ₽ в месяцы с операциями, Premium от 0,04 % + 2 990 ₽/мес. Порог бесплатного обслуживания считается по стоимости всех счетов Т-Инвестиций.${othTxt}</p></div>`;
}
/* Счета других брокеров (импорт отчётов): свои тарифы, модель Т-Инвестиций к ним не применяется */
async function feeSetTariff(id,v){
  try{await post('/api/config',{broker_tariffs:{[id]:v}});load(false,true)}catch(e){uiErr(e)}
}
function feeOtherBrokers(){
  const rows=(S.data||{}).broker_fees||[];
  if(!rows.length)return'';
  const pct=x=>x==null?'—':(x*100).toFixed(3).replace('.',',')+' %';
  const dmy=x=>{const[y,m,d]=String(x).split('-');return d+'.'+m+'.'+y.slice(2)};
  return rows.map(r=>{
    const opts=['<option value="">не выбран</option>'].concat((r.tariffs||[]).map(t=>`<option value="${esc(t.id)}"${t.id===r.tariff_id?' selected':''}>${esc(t.name)}</option>`)).join('');
    const sel=(r.tariffs||[]).length?`<label class="field" style="max-width:340px;margin-bottom:12px"><span>Ваш тариф у брокера ${esc(r.broker_name)}</span><select class="in" onchange="feeSetTariff('${esc(r.id)}',this.value)">${opts}</select></label>`
      :`<p class="note" style="margin:0 0 12px">Тарифы брокера «${esc(r.broker_name)}» пока не заданы — показаны фактические комиссии из отчёта.</p>`;
    const m=r.model;
    let mk='';
    if(m){const d=m.diff,dc=d>100?'neg':(d<-100?'pos':'');
      mk=kpi('Модель тарифа',M(m.cost,'rub',0),'комиссия '+M(m.fee,'rub',0)+(m.sub?' + плата '+M(m.sub,'rub',0):'')+' за 12 мес.')+
        kpi('Факт минус модель',(d>0?'+':'')+M(d,'rub',0),Math.abs(d)<=100?'факт совпадает с моделью':(d>0?'платите больше модели: проверьте тариф или сборы биржи':'платите меньше модели'),dc)}
    return`<div class="card"><h2>Комиссии у брокера ${esc(r.broker_name)} · ${esc(r.name)}<span class="sp" style="white-space:normal">последние 12 мес.: ${dmy(r.from)} — ${dmy(r.to)} · оборот ${short(r.turnover)} ₽ (акции и фонды ${short(r.turnover_shares)} ₽, облигации ${short(r.turnover_bonds)} ₽)</span></h2>
      ${sel}<div class="g g4" style="margin-bottom:8px">
      ${kpi('Фактически уплачено',M(r.paid,'rub',0),'брокерская '+M(r.paid_broker,'rub',0)+' + обслуживание '+M(r.paid_service,'rub',0))}
      ${kpi('Фактическая ставка',pct(r.eff_rate),r.eff_rate==null?'нет оборота по сделкам':'от оборота по сделкам в рублях')}${mk}</div>
      <p class="note" style="margin:0">Тарифы Т-Инвестиций к этому счёту не применяются.${m?' Тариф «'+esc(m.name)+'»: '+esc(m.notes)+'. Источник: '+esc(m.source_url)+' (данные на '+esc(m.as_of)+').':''} Брокер счёта можно поменять в разделе «Импорт отчётов».</p></div>`}).join('');
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
  out+=feeOtherBrokers();
  const other=Object.keys(d.totals).filter(c=>c!=='rub'&&FEEK.some(k=>d.totals[c][k]));
  if(other.length)out+=`<div class="card"><h2>Комиссии в других валютах</h2><table><thead><tr><th>Статья</th>${other.map(c=>`<th>${sym(c)}</th>`).join('')}</tr></thead><tbody>`+
    FEEK.map(k=>`<tr><td>${L[k]}</td>${other.map(c=>`<td class="num">${M(d.totals[c][k]||0,c)}</td>`).join('')}</tr>`).join('')+'</tbody></table></div>';
  return out;
}

