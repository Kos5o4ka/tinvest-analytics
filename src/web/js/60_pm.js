/* ── Разбор сделок (Trade Post-Mortem, FIFO) и Призрачный портфель (Cashflow-Matched LQDT / TMOS) (#8) ── */
S.pm={acc:null,data:null,loading:false,err:''};
function pmLoad(force){
  const D=S.pm,acc=S.account;
  if(D.loading&&!force&&D.acc===acc)return;
  D.loading=true;D.acc=acc;D.err='';
  api('/api/postmortem?account='+encodeURIComponent(acc)+(force?'&force=1':'')).then(j=>{
    if(D.acc!==acc)return;D.loading=false;D.data=j;if(S.page==='pm')renderSoon();
  }).catch(e=>{if(D.acc!==acc)return;D.loading=false;D.err=e.message||String(e);if(S.page==='pm')renderSoon()});
}
function pPm(){
  const D=S.pm;
  if(D.acc!==S.account&&!D.loading){D.data=null;pmLoad(false)}
  if(!D.data&&!D.loading)pmLoad(false);
  if(D.loading&&!D.data)return`<div class="card">${waitBox('Разбираю закрытые сделки по FIFO и моделирую призрачный портфель…')}</div>`;
  if(D.err)return`<div class="msg err">${esc(D.err)} <button class="btn ghost" id="pm-r">Повторить</button></div>`;
  const d=D.data||{},tr=d.trades||{},gh=d.ghost||{};
  let ghostHtml='<div class="card"><h2>Призрачный портфель (те же пополнения в те же даты)</h2><div class="empty">Недостаточно истории операций или котировок бенчмарков (LQDT / TMOS).</div></div>';
  if(gh.ok&&gh.items&&gh.items.length){
    const labs=gh.days.map(x=>{const[y,m]=x.split('-');return MON[+m-1]+' '+y.slice(2)}),tips=gh.days.map(dlabel);
    const ser=[{n:'Мой портфель',c:S1,v:gh.real,w:2.4}];
    if(gh.series.LQDT)ser.push({n:'Призрак LQDT',c:S3,v:gh.series.LQDT,w:1.8,dash:1});
    if(gh.series.TMOS)ser.push({n:'Призрак TMOS',c:S2,v:gh.series.TMOS,w:1.8,dash:1});
    chart('c-pm-gh',line,{h:270,zero:false,labels:labs,tipLabels:tips,series:ser});
    ghostHtml=`<div class="card"><div class="row" style="margin-bottom:10px"><h2 style="margin:0">Призрачный портфель<span class="sp">cashflow-matched · те же пополнения и выводы в те же даты</span></h2><button class="btn ghost" id="pm-r" style="margin-left:auto">Обновить</button></div>
      <div class="g g3" style="margin-bottom:12px">${kpi('Мой портфель сейчас',M(gh.real_val,'rub',0),'вложено '+M(gh.invested,'rub',0),null,S1)}
        ${gh.items.map(it=>kpi('Если бы всё в '+it.code,M(it.ghost_val,'rub',0),`мой результат: ${SM(it.diff_rub)}${it.diff_pct!=null?' ('+pct(it.diff_pct,1)+')':''}`,cls(it.diff_rub),it.code==='LQDT'?S3:S2)).join('')}</div>
      <div id="c-pm-gh" class="chart"></div></div>`;
  }
  let trHtml='';
  if(!tr.n){
    trHtml=`<div class="card"><h2>Разбор закрытых сделок (Trade Post-Mortem, FIFO)</h2><div class="empty">Закрытых продаж бумаг по этому счёту пока нет.</div></div>`;
  }else{
    const dispBanner=tr.disposition_flag
      ?`<div class="msg err" style="margin-bottom:12px"><b>Обнаружен эффект диспозиции (×${f2(tr.disposition_ratio)}):</b> убыточные сделки вы держите в среднем <b>${f2(tr.avg_hold_loss)} дн.</b>, а прибыльные фиксируете через <b>${f2(tr.avg_hold_win)} дн.</b></div>`
      :(tr.disposition_ratio!=null?`<div class="bc-verdict" style="margin-bottom:12px">Дисциплина удержания: прибыльные сделки держатся в среднем <b>${f2(tr.avg_hold_win)} дн.</b>, убыточные — <b>${f2(tr.avg_hold_loss)} дн.</b> (коэффициент ${f2(tr.disposition_ratio)}).</div>`:'');
    const tTbl=(list,title)=>list&&list.length?`<div class="card"><h2>${title}</h2><div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>Дата продажи</th><th>Срок, дн.</th><th>Результат, ₽</th><th>%</th></tr></thead><tbody>`+
      list.map(x=>`<tr${stkAttrIf(x.ticker)}><td class="l"><b>${esc(x.name)}</b><br><small class="mu">${esc(x.ticker)}</small></td><td class="num">${ddm(x.sdate)}</td><td class="num">${x.hold_days!=null?Math.round(x.hold_days):'—'}</td>
        <td class="num ${cls(x.result)}"><b>${SM(x.result)}</b></td><td class="num ${cls(x.pct)}">${x.pct!=null?pct(x.pct,1):'—'}</td></tr>`).join('')+`</tbody></table></div></div>`:'';
    trHtml=`<div class="card"><h2>Разбор закрытых сделок (Trade Post-Mortem, FIFO)<span class="sp">всего закрытых продаж: ${tr.n}</span></h2>
      ${dispBanner}
      <div class="g g4" style="margin-bottom:12px">
        ${kpi('Win Rate (доля прибыльных)',tr.win_rate!=null?pctp(tr.win_rate,1):'—',`${tr.wins} в плюс · ${tr.losses} в минус`,tr.win_rate>=50?'pos':'neg')}
        ${kpi('Profit Factor',tr.profit_factor!=null?f2(tr.profit_factor):'—','валовая прибыль / валовой убыток',tr.profit_factor>=1.2?'pos':tr.profit_factor!=null&&tr.profit_factor<1?'neg':'')}
        ${kpi('Средняя прибыль / убыток',tr.avg_win!=null?M(tr.avg_win,'rub',0):'—','ср. убыток: '+(tr.avg_loss!=null?M(tr.avg_loss,'rub',0):'—'))}
        ${kpi('Итого реализовано (FIFO)',SM(tr.net_pnl),'валовая прибыль '+M(tr.gross_profit,'rub',0),cls(tr.net_pnl))}</div>
      ${(tr.by_type||[]).length?`<div class="tbl"><table><thead><tr><th class="l">Класс активов</th><th>Сделок</th><th>Win Rate</th><th>Итоговый результат, ₽</th></tr></thead><tbody>`+
        tr.by_type.map(b=>`<tr><td class="l"><b>${esc(TYPES[b.type]||b.type)}</b></td><td class="num">${b.n}</td><td class="num">${pctp(b.win_rate,1)}</td><td class="num ${cls(b.result)}"><b>${SM(b.result)}</b></td></tr>`).join('')+`</tbody></table></div>`:''}</div>
      <div class="g g2">${tTbl(tr.best,'Лучшие закрытые сделки')}${tTbl(tr.worst,'Худшие закрытые сделки')}</div>`;
  }
  return ghostHtml+trHtml+`<p class="note">Разбор сделок строится по методу FIFO на базе истории операций. Призрачный портфель показывает, сколько денег было бы сегодня, если бы каждое ваше пополнение и вывод в те же самые даты направлялись в фонд денежного рынка LQDT или индексный фонд TMOS. ${NIR_NOTE}</p>`;
}
function bindPm(){
  const r=$('#pm-r');if(r)r.onclick=()=>{S.pm.data=null;pmLoad(true);render()};
}
regPage('pm',{title:'Разбор сделок',group:'Портфель',icon:'<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',render:pPm,bind:bindPm});
if(typeof renderNav==='function')try{renderNav()}catch(e){}
