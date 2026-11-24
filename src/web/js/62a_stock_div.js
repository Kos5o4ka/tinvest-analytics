/* ── Вкладка «Дивиденды» в карточке акции или фонда: полный анализ в одном месте ──
   История выплат за все годы, годовые суммы и рост, доходности, регулярность, ближайший дивиденд с последним днём покупки,
   надёжность, статистика дивидендного гэпа, «удержать или продать накануне», ваши полученные дивиденды.
   Все расчёты — на сервере (/api/divlab?secid=, 13x9_divlab.py); здесь только отображение. Грузится лениво, при открытии вкладки. */
function stkDvKey(){return[S.stk.secid,S.account,S.dl.tax,S.dl.fee].join('|')}
function stkDvRerender(){if(S.page==='stk')renderSoon();skRender()}
function stkDvLoad(force){
  const st=S.stk,k=stkDvKey(),D=st.dv||(st.dv={}),sec=st.secid;if(!sec)return;
  if(!force&&D.key===k&&(D.data||D.loading||D.err))return;
  D.key=k;D.loading=true;D.err='';
  if(force||(D.data&&D.data.secid!==sec))D.data=null;
  api('/api/divlab?'+dlQs({secid:sec})+(force?'&force=1':'')).then(j=>{if(D.key!==k)return;D.loading=false;D.data=j;stkDvRerender()})
    .catch(e=>{if(D.key!==k)return;D.loading=false;D.err=e.message||String(e);stkDvRerender()});
}
const stkDvRub=(v,d)=>v==null||isNaN(v)?'—':stkN(v,d==null?(Math.abs(v)<1?4:2):d)+' ₽';
const stkDvSg=v=>v==null?'—':(v>0?'+':v<0?'−':'')+stkN(Math.abs(v),1)+' %';
const stkDvYrs=n=>n+' '+dlEv(n,'год','года','лет');
function stkDvSrc(s){return s==='dohod'?'<small class="mu" title="Источник: dohod.ru — длинная история выплат">dohod.ru</small>':'<small class="mu" title="Источник: T-Invest">T-Invest</small>'}
/* верхняя полоса показателей */
function stkDvKpis(pf){
  const cg=(v,y)=>v==null?'<span class="mu">—</span>':stkPc(v,1);
  return`<div class="g g4">${kpi('Доходность за 12 месяцев',pf.yield_ttm!=null?stkN(pf.yield_ttm,2)+' %':'—',pf.ttm?'выплачено '+stkDvRub(pf.ttm)+' на акцию':'выплат за год не было')}
    ${kpi('Объявлено вперёд',pf.yield_forward!=null?stkN(pf.yield_forward,2)+' %':'—',pf.forward?stkDvRub(pf.forward)+' на акцию, ещё не выплачено':'новых дивидендов не объявлено')}
    ${kpi('Рост дивиденда в год',`<span title="Среднегодовой рост суммы дивидендов за ${pf.last_full_year} к ${pf.last_full_year-5} году">${cg(pf.cagr5)}</span>`,'за 5 лет; за 10 лет: '+stkDvSg(pf.cagr10))}
    ${kpi('Платит подряд',pf.streak_paid?stkDvYrs(pf.streak_paid):'—',(pf.streak_growth?'растёт '+stkDvYrs(pf.streak_growth)+' подряд':'роста подряд нет')+' · '+esc((pf.regularity||{}).label||''))}</div>`;
}
/* ближайший дивиденд и что получит держатель */
function stkDvNext(d,pf){
  const nx=pf.next,pos=d.position,np=pf.next_pos;
  if(!nx)return`<div class="card"><h2>Ближайший дивиденд</h2><div class="empty" style="padding:20px">Выплат не найдено.</div></div>`;
  const px=d.price,pct=px?stkN(nx.value/px*100,2)+' % к цене':'';
  const rows=[[nx.upcoming?'Закрытие реестра':'Было закрытие реестра',ddm(nx.record)],
    ['Последний день покупки',nx.last_buy?(nx.last_buy_est?'≈ ':'')+ddm(nx.last_buy):'—'],
    nx.payment?['Выплата (ориентир)',ddm(nx.payment)]:null,nx.declared?['Объявлен',ddm(nx.declared)]:null].filter(Boolean);
  let hold='';
  if(np)hold=`<div class="sd-pos"><b>На ваши ${stkN(np.qty,0)} шт.:</b> ${stkDvRub(np.gross,2)} до налога, <b class="pos">${stkDvRub(np.net,2)}</b> после налога ${stkN(np.tax_rate*100,0)} %</div>`;
  else if(pos&&!nx.upcoming)hold=`<div class="sd-pos mu">У вас ${stkN(pos.qty,0)} шт. — новый дивиденд пока не объявлен.</div>`;
  return`<div class="card"><h2>${nx.upcoming?'Ближайший дивиденд':'Последний дивиденд'}<span class="sp">${nx.upcoming?'объявлен':'новых не объявлено'}</span></h2>
    <div class="sd-big num">${stkDvRub(nx.value)}<small class="mu"> на акцию${pct?' · '+pct:''}</small></div>
    <div class="tbl"><table><tbody>${rows.map(r=>`<tr><td class="l">${r[0]}</td><td class="num"><b>${r[1]}</b></td></tr>`).join('')}</tbody></table></div>${hold}
    <p class="note" style="margin-top:8px">Чтобы получить дивиденд, акцию нужно купить не позже последнего дня покупки: с 31.07.2023 расчёты на Мосбирже идут в режиме T+1, поэтому это рабочий день перед датой закрытия реестра.${nx.last_buy_est?' Знак «≈» — дата рассчитана по будням, праздники не учтены.':''} Будущие размеры и даты могут измениться до решения собрания акционеров.</p></div>`;
}
/* годовые суммы: выплачено + объявлено (на акцию, по году закрытия реестра) */
function stkDvYearsCard(d,pf,p){
  const ys=pf.years||[];
  if(!ys.length)return'';
  const sp=(pf.skipped||[]).length?'без выплат: '+pf.skipped.join(', '):'';
  chart('c-'+p+'dvy',bars,{h:230,labels:ys.map(y=>String(y.year)),legend:ys.some(y=>y.announced>0)?undefined:false,stack:true,total:true,skipZero:true,
    series:[{n:'Выплачено',c:S3,v:ys.map(y=>y.sum)},{n:'Объявлено',c:S5,v:ys.map(y=>y.announced)}],
    tipLabels:ys.map(y=>y.year+(y.n?' · '+y.n+' '+dlEv(y.n,'выплата','выплаты','выплат'):'')+(y.yield_pct?' · '+stkN(y.yield_pct,1)+' % к текущей цене':'')),
    fa:v=>v===0?'0':stkN(v,v<10?1:0),ft:v=>stkDvRub(v),empty:'Выплат не было'});
  const reg=pf.regularity||{};
  return`<div class="card"><h2>Дивиденд на акцию по годам<span class="sp">${esc(sp)}</span></h2><div id="c-${p}dvy" class="chart"></div>
    <p class="note" style="margin-top:6px">Сумма по году закрытия реестра. Обычно платит ${esc(reg.label||'—')}${pf.first_year?', история выплат — с '+pf.first_year+' года':''}. Подряд без снижения: ${stkDvYrs(pf.streak_nodecline||0)}. Рост в год — среднегодовой рост суммы за ${pf.last_full_year} г. к сумме пятью и десятью годами раньше.</p></div>`;
}
/* статистика дивидендного гэпа (компактно) + гистограмма */
function stkDvGap(d,p){
  const st=d.stats||{count:0};
  if(!st.count)return`<div class="card"><h2>Дивидендный гэп</h2><div class="empty" style="padding:20px">Нет прошлых отсечек, покрытых историей котировок за 6 лет.</div></div>`;
  chart('c-'+p+'dvh',dlHistChart,{hist:st.hist});
  const w=st.within||{},bar=n=>{const x=w[n]||{};return`<div class="sd-w"><span>за ${n} дн.</span><span class="sd-wb"><i style="width:${x.pct||0}%"></i></span><b class="num">${x.pct!=null?pctp(x.pct,0):'—'}</b><small class="mu">${x.of?x.n+' из '+x.of:''}</small></div>`};
  return`<div class="card"><h2>Дивидендный гэп<span class="sp">${st.count} ${dlEv(st.count,'отсечка','отсечки','отсечек')} за 6 лет</span></h2>
    <div class="sd-gg"><div><div class="sd-gk"><div><small class="mu">Медиана до закрытия</small><b class="num">${st.median_days!=null?dlDays(st.median_days):'—'}</b><small class="mu">торговых; закрыто ${st.closed} из ${st.count}</small></div>
      <div><small class="mu">Гэп, медиана</small><b class="num">${st.median_k!=null?pctp(st.median_k*100,0):'—'}</b><small class="mu">от дивиденда${st.avg_gap_pct!=null?'; '+dlN(st.avg_gap_pct,1)+' % от цены':''}</small></div></div>
    <div class="sd-ws">${['30','60','90'].map(bar).join('')}</div></div>
    <div id="c-${p}dvh" class="chart"></div></div>
    <p class="note">Гэп — падение цены в первый день без права на дивиденд. Закрыт — цена вернулась к уровню последнего дня покупки.${st.still_open?' Ещё открыты (слишком свежие): '+st.still_open+'.':''}</p></div>`;
}
/* «удержать или продать накануне» + поля налога и комиссии */
function stkDvPayoff(d,p){
  const D=S.dl;
  return`<div class="sd-calc">${dlPayoffCard(d).replace('</h2>',`</h2><div class="sd-in"><label class="field dl-f"><span>Налог на дивиденды, %</span><input class="in num" id="${p}dvtax" value="${esc(D.tax)}" inputmode="decimal"></label>
      <label class="field dl-f"><span>Комиссия брокера, %</span><input class="in num" id="${p}dvfee" value="${esc(D.fee)}" inputmode="decimal"></label></div>`)}</div>`;
}
/* ваши дивиденды по операциям */
function stkDvMine(d){
  const r=d.received;if(!r)return'';
  const rows=r.items.slice(0,40).map(x=>`<tr><td class="l num">${ddm(x.date)}</td><td class="num">${stkDvRub(x.gross,2)}</td><td class="num mu">${x.tax?'−'+stkDvRub(x.tax,2):'—'}</td><td class="num"><b>${stkDvRub(x.net,2)}</b></td></tr>`).join('');
  return`<div class="card"><h2>Ваши дивиденды<span class="sp">по операциям счёта</span></h2>
    <div class="g g3" style="margin-bottom:10px">${kpi('Получено всего',stkDvRub(r.net,0),'после налога; до налога '+stkDvRub(r.gross,0),'pos')}${kpi('Удержан налог',stkDvRub(r.tax,0),'налоговый агент — брокер')}
      ${kpi('Выплат',String(r.items.length),r.years.length?'с '+r.years[0].year+' г.':'')}</div>
    <div class="tbl" style="max-height:260px"><table><thead><tr><th class="l">Зачисление</th><th>До налога</th><th>Налог</th><th>Получено</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}
/* полная история выплат */
function stkDvHist(d){
  const it=d.divs||[];
  if(!it.length)return'';
  const dh=d.div_hist||{};
  const body=it.map(r=>`<tr class="${r.future?'pnew':''}"><td class="l num">${ddm(r.record)}${r.future?' <small class="pos">будущая</small>':''}</td><td class="num">${r.last_buy?ddm(r.last_buy):'—'}</td><td class="num">${r.payment?ddm(r.payment):'—'}</td>
    <td class="num"><b>${stkDvRub(r.value)}</b></td><td class="num">${r.yield_pct==null?'—':stkN(r.yield_pct,2)+' %'}</td><td class="l">${stkDvSrc(r.src)}</td></tr>`).join('');
  const note=dh.added?`Ранние годы — по данным <a href="${esc(dh.url||'https://www.dohod.ru')}" target="_blank" rel="noopener noreferrer">dohod.ru</a> (T-Invest отдаёт около 6 лет). `:dh.status==='err'?'Длинная история с dohod.ru сейчас недоступна. ':'';
  return`<div class="card"><h2>Все выплаты<span class="sp">${it.length} ${dlEv(it.length,'выплата','выплаты','выплат')}</span></h2>
    <div class="tbl" style="max-height:420px"><table><thead><tr><th class="l">Закрытие реестра</th><th title="Последний день, когда покупка давала право на дивиденд">Посл. день покупки</th><th>Выплата</th><th>На акцию</th><th title="Размер дивиденда к текущей цене акции">К текущей цене</th><th class="l">Источник</th></tr></thead><tbody>${body}</tbody></table></div>
    <p class="note" style="margin-top:8px">${note}Доходность каждой выплаты — к сегодняшней цене, а не к цене на дату выплаты.</p></div>`;
}
function stkDivTab(c,p){
  const st=S.stk;
  if(!st.dv||st.dv.key!==stkDvKey())stkDvLoad(false);
  const D=st.dv,d=D.data&&D.data.secid===st.secid?D.data:null;
  if(D.err&&!d)return`<div class="msg err">${esc(D.err)} <button class="btn ghost" id="${p}dvr">Повторить</button></div>`;
  if(!d)return`<div class="card">${waitBox('Собираю историю дивидендов за все годы, котировки за 6 лет и отчётность…')}</div>`;
  const pf=d.profile;
  const err=d.error?`<div class="msg info" style="margin-bottom:12px">${esc(d.error)}</div>`:'';
  if(!pf||!(d.divs||[]).length)return err+`<div class="card"><div class="empty" style="padding:30px">${c.kind==='fund'?'Выплат по этому фонду не найдено — доход, вероятно, остаётся в цене пая.':'Дивидендов по этой бумаге не найдено. Возможно, компания не платит дивиденды или данные временно недоступны.'}</div></div>`;
  const busy=D.loading?`<div class="msg info" style="margin-bottom:12px">Пересчитываю…</div>`:'';
  const fund=c.kind==='fund'||d.kind==='fund';
  return busy+err+stkDvKpis(pf)+
    `<div class="g ${fund||!d.safety?'':'g2'}" style="margin-top:16px">${stkDvNext(d,pf)}${fund||!d.safety?'':dlSafetyCard(d.safety)}</div>
    <div style="margin-top:16px">${stkDvYearsCard(d,pf,p)}</div>
    <div style="margin-top:16px">${stkDvGap(d,p)}</div>
    <div style="margin-top:16px">${stkDvPayoff(d,p)}</div>
    ${d.received?`<div style="margin-top:16px">${stkDvMine(d)}</div>`:''}
    <div style="margin-top:16px">${stkDvHist(d)}</div>
    ${(d.gaps||[]).length?`<details class="card sd-det" style="margin-top:16px"><summary><b>История гэпов по отсечкам</b> <span class="mu">${d.gaps.length} ${dlEv(d.gaps.length,'событие','события','событий')}</span></summary>${dlGapsTable(d.gaps)}</details>`:''}
    <p class="note">Дивиденды: T-Invest${(d.div_hist||{}).added?' и dohod.ru':''}; котировки — Мосбиржа. Описательная статистика по прошлым выплатам, не прогноз и не инвестиционная рекомендация. <button class="btn ghost" id="${p}dvr" style="margin-left:6px">Обновить данные</button></p>`;
}
function bindStkDiv(root,p){
  const g=id=>root.querySelector('#'+p+id),D=S.dl;
  const r=g('dvr');if(r)r.onclick=()=>{stkDvLoad(true);stkDvRerender()};
  [['dvtax','tax'],['dvfee','fee']].forEach(([id,k])=>{const e=g(id);if(e)e.onchange=()=>{D[k]=e.value;D.data=null;D.port=null;stkDvLoad(false);stkDvRerender()}});
}
