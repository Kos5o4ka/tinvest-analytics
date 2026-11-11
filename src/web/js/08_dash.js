/* ── Обзор ── */
function pDash(){
  const d=S.data,p=d.portfolio,t=T(),lf=d.life;
  if(!p.total&&!p.positions.length&&!d.ops.length&&!lf.deposits)return`<div class="card empty fade" style="min-height:420px">${svgI('<rect x="3" y="6" width="18" height="14" rx="3"/><path d="M3 10h18M16 15h2"/>')}
    <div style="font-size:17px;color:var(--tx);font-weight:600">Счёт пока пуст</div><div style="max-width:460px">На этом счёте нет активов и операций${d.sandbox?'. В песочнице его можно пополнить виртуальными деньгами в «Настройках».':'.'} Можно выбрать другой счёт слева или импортировать отчёт другого брокера.</div>
    <div class="row" style="justify-content:center"><button class="btn" data-go="imp">Импорт отчёта</button>${d.sandbox?'<button class="btn ghost" data-go="set">Настройки</button>':''}</div></div>`;
  const income=sumK(t,['dividends','coupons','overnight']),taxes=sumK(t,TAXK);
  const profit=d.profit,ppct=d.invested>0&&profit!=null?profit/d.invested*100:null,hs=histSlice();
  const hero=`<div class="card hero"><div style="position:relative;z-index:1"><div class="lbl">Стоимость портфеля</div>
    <div class="val num">${f2m(p.total)} <small>₽</small></div>
    <div class="row" style="margin-top:10px">${p.daily!=null?`<span class="pill ${cls(p.daily)}">${SM(p.daily)} · ${pct(p.daily_pct)} за день</span>`:''}
    <span class="pill ${cls(p.upnl)}">${SM(p.upnl)} · ${pct(p.yield_pct)} по открытым позициям</span></div></div>
    <div class="meta"><div><span>Вложено (пополнения − выводы)</span><b class="num">${M(d.invested,'rub',0)}</b></div>
    <div><span>Прибыль за всё время</span><b class="num ${cls(profit)}">${profit==null?'—':SM(profit)}</b>${ppct!=null?` <span class="mu num" style="display:inline">${pct(ppct,1)}</span>`:''}</div>
    <div><span>Доходность за период (TWR)</span><b class="num ${hs?cls(hs.total):''}">${hs?pct(hs.total*100,2):S.hist&&!S.hist.error?'—':'…'}</b></div>
    <div><span>XIRR, % годовых</span><b class="num ${cls(d.xirr)}">${d.xirr==null?'—':pct(d.xirr*100,1)}</b></div></div></div>`;
  const turn=(t.buy_turnover||0)+(t.sell_turnover||0);
  const kpis=`<div class="g g6">
    ${kpi('Реализовано по сделкам',SM(t.realized||0),'фиксированный результат продаж',cls(t.realized),S1)}
    ${kpi('Пассивный доход',M(income),`дивиденды ${short(t.dividends||0)} · купоны ${short(t.coupons||0)}`,income?'pos':'',S3)}
    ${kpi('Комиссии брокера',M(sumK(t,['fee_broker','fee_service','fee_other'])),turn?`${f2((t.fee_broker||0)/turn*100)} % от оборота`:'',null,S2)}
    ${kpi('Плата за маржу',M(t.margin_fee||0),t.varmargin?`вар. маржа ${SM(t.varmargin)}`:'шорт и кредитное плечо',null,S5)}
    ${kpi('Налоги удержано',M(taxes),'подробнее — во вкладке «Налоги»',null,S4)}
    ${kpi('Оборот',M(turn,'rub',0),`покупки ${short(t.buy_turnover||0)} · продажи ${short(t.sell_turnover||0)}`,null,S7)}</div>`;
  const alloc=[['Акции',p.shares,S1],['Облигации',p.bonds,S2],['Фонды',p.etf,S3],['Валюта и деньги',p.currencies,S4],['Фьючерсы',p.futures,S5],['Структурные',p.sp,S6],['Опционы',p.options,S7],['Прочее',p.other,S8]].map(([n,v,c])=>({n,v,c}));
  chart('c-alloc',donut,{items:alloc,cap:'Портфель'});
  let eq=waitBox('Восстанавливаю историю стоимости по ценам закрытия…');
  if(S.hist&&S.hist.error)eq=`<div class="msg err">${esc(S.hist.error)}</div>`;
  else if(S.hist&&!hs)eq='<div class="empty">Недостаточно истории за период</div>';
  else if(hs){eq='<div id="c-eq" class="chart"></div>';
    chart('c-eq',line,{h:290,area:true,zero:false,labels:hs.days.map(x=>{const[y,m]=x.split('-');return MON[+m-1]+' '+y.slice(2)}),tipLabels:hs.days.map(dlabel),
      series:[{n:'Стоимость портфеля',c:S1,hex:'#3987e5',v:hs.value},{n:'Вложено',c:'#8b93a7',v:hs.invested,dash:1,w:1.6}]})}
  let mret=waitBox();
  if(S.hist&&S.hist.monthly){const ms=Object.keys(S.hist.monthly).sort().slice(-12);mret='<div id="c-mret" class="chart"></div>';
    chart('c-mret',bars,{labels:ms.map(mlabel),tipLabels:ms.map(m=>{const[y,mm]=m.split('-');return MONF[+mm-1]+' '+y}),labelsOn:ms.length<=12,
      series:[{n:'Доходность',c:S1,v:ms.map(m=>S.hist.monthly[m]*100)}],colorOf:v=>v>=0?'var(--pos)':'var(--neg)',fa:v=>(Math.round(v*10)/10).toString().replace('.',',')+'%',ft:v=>pct(v)})}
  else if(S.hist&&S.hist.error)mret='<div class="empty">Не удалось посчитать доходность по месяцам. Нажмите «Обновить» сверху, чтобы повторить.</div>';
  let pays=waitBox('Собираю график купонов и дивидендов…');
  if(S.bonds&&S.bonds.payments){const pm=payMonths(S.bonds.payments,6);const tot=S.bonds.payments.reduce((a,x)=>a+x.amount,0);
    pays=`<div class="row" style="justify-content:space-between;margin:-4px 0 10px"><span class="t2" style="font-size:12.5px">За 12 месяцев ожидается</span><b class="num pos">${M(tot)}</b></div><div id="c-pay6" class="chart"></div>`;
    chart('c-pay6',bars,{h:190,labels:pm.labels,tipLabels:pm.tips,stack:true,total:true,skipZero:true,series:pm.series,empty:'Выплат не ожидается'})}
  const top=p.positions.filter(x=>x.type!=='currency'&&x.type!=='futures').slice(0,8);
  const mx=Math.max(1,...top.map(x=>x.value_rub||0));
  const topHtml=top.length?`<div class="li">${top.map(x=>`<div class="it">${logo(x,34)}<div><b>${esc(x.name)}</b><small>${esc(x.ticker)} · ${pctp(x.share)} портфеля</small><div class="bar"><i style="width:${(x.value_rub||0)/mx*100}%;background:${S1}"></i></div></div>
    <div class="rv num">${M(x.value_rub??x.value,'rub',0)}<small class="${cls(x.pnl)}">${x.pnl_rub!=null?SM(x.pnl_rub):''} ${x.pnl_pct!=null?'('+pct(x.pnl_pct,1)+')':''}</small></div></div>`).join('')}</div>`:'<div class="empty">Нет открытых позиций</div>';
  const inc=d.income_by.filter(x=>x[0]>0).slice(0,8),imx=Math.max(1,...inc.map(x=>x[0]));
  const incHtml=inc.length?`<div class="li">${inc.map(x=>`<div class="it">${logo({name:x[1],ticker:x[2],logo:x[3]},34)}<div><b>${esc(x[1])}</b><small>${esc(x[2]||'')}${x[4]?' · '+(TYPES[x[4]]||''):''}</small><div class="bar"><i style="width:${x[0]/imx*100}%;background:${S3}"></i></div></div>
    <div class="rv num pos">${M(x[0])}</div></div>`).join('')}</div>`:'<div class="empty">Выплат за период не было</div>';
  const marg=d.margin?`<div class="card"><h2>Маржинальная торговля</h2><div class="g g6" style="gap:12px">
    ${[['Ликвидный портфель','liquidPortfolio'],['Начальная маржа','startingMargin'],['Минимальная маржа','minimalMargin'],['Скорр. маржа','correctedMargin'],['Не хватает средств','amountOfMissingFunds']]
      .map(([n,k])=>`<div><div class="mu" style="font-size:12px">${n}</div><div class="num" style="font-weight:650;font-size:16px;margin-top:4px">${M(d.margin[k])}</div></div>`).join('')}
    <div><div class="mu" style="font-size:12px">Уровень достаточности</div><div class="num ${d.margin.fundsSufficiencyLevel<1.1&&d.margin.fundsSufficiencyLevel>0?'neg':''}" style="font-weight:650;font-size:16px;margin-top:4px">${f2(d.margin.fundsSufficiencyLevel)}</div></div></div></div>`:'';
  return hero+todayCard()+kpis+monCard()+`<div class="g c-2-1"><div class="card"><h2>Стоимость и вложения<span class="sp">${periodName()}</span></h2>${eq}</div>
    <div class="card"><h2>Структура портфеля</h2><div id="c-alloc" class="chart"></div></div></div>
    <div class="g g2"><div class="card"><h2>Доходность по месяцам<span class="sp">последние 12 мес</span></h2>${mret}</div>
    <div class="card"><h2>Ближайшие выплаты<span class="sp">купоны · дивиденды · погашения</span></h2>${pays}</div></div>
    <div class="g g2"><div class="card"><h2>Крупнейшие позиции<span class="sp">стоимость · P&amp;L</span></h2>${topHtml}</div>
    <div class="card"><h2>Кто платит дивиденды и купоны<span class="sp">${periodName()}</span></h2>${incHtml}</div></div>`+marg;
}

function payMonths(pays,n){
  const now=new Date(),keys=[];for(let i=0;i<n;i++){const d=new Date(now.getFullYear(),now.getMonth()+i,1);keys.push(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0'))}
  const k3={coupon:{},dividend:{},redemption:{},amortization:{}};pays.forEach(p=>{const m=p.date.slice(0,7);if(keys.includes(m))(k3[p.kind]=k3[p.kind]||{})[m]=(k3[p.kind][m]||0)+p.amount});
  return{labels:keys.map(mlabel),tips:keys.map(m=>{const[y,mm]=m.split('-');return MONF[+mm-1]+' '+y}),
    series:[{n:'Купоны',c:S1,v:keys.map(k=>k3.coupon[k]||0)},{n:'Дивиденды',c:S3,v:keys.map(k=>k3.dividend[k]||0)},{n:'Погашения',c:S4,v:keys.map(k=>k3.redemption[k]||0)},{n:'Амортизации',c:S5,v:keys.map(k=>k3.amortization[k]||0)}]};
}

