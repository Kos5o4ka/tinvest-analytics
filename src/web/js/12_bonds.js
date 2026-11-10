/* ── Облигации ── */
function heatCell(v,mx,rgb,txt){if(bad(v))return'<td class="num mu">—</td>';const a=Math.max(0,Math.min(1,v/(mx||1)));return`<td class="num" style="background:rgba(${rgb},${(0.06+a*0.5).toFixed(3)})">${txt}</td>`}
function pBonds(){
  const b=S.bonds;
  if(!b)return`<div class="card">${waitBox('Загружаю параметры облигаций и графики купонов…')}</div>`;
  if(b.error)return`<div class="msg err">${esc(b.error)}</div>`;
  const m=b.metrics,tot=S.data.portfolio.total||1;
  if(!m.count)return'<div class="card empty">В портфеле нет облигаций</div>';
  let rows=b.rows.slice();rows.forEach(r=>r.rk=r.rating?RSC.indexOf(r.rating.v):null);const{k,d}=S.bsort;
  rows.sort((a,c)=>{const x=a[k],y=c[k];if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  const mxS=Math.max(...rows.map(r=>r.share||0)),mxY=Math.max(...rows.map(r=>r.ytm||0)),mxD=Math.max(...rows.map(r=>r.dur||0));
  const cols=[['name','Облигация','l'],['qty','Кол-во'],['buy_pct','Покупка, %'],['price_pct','Цена, %'],['value_rub','Стоимость'],['pnl_rub','P&L'],['share','Доля'],['ytm','Доходность'],['spread','Спред к КБД'],['dur','Дюрация'],['coupon','Купон'],['next','След. купон'],['maturity','Погашение'],['rk','Рейтинг','l'],['risk','Риск','l']];
  const th=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  const body=rows.map(r=>`<tr><td>${ident(r,[r.ticker,r.floating?'флоатер':'',r.amort?'амортизация':''].filter(Boolean).join(' · '))}</td>
    <td class="num">${f0(r.qty)}</td><td class="num">${r.buy_pct!=null?f2(r.buy_pct):'—'}</td><td class="num">${r.price_pct!=null?f2(r.price_pct):'—'}</td>
    <td class="num">${M(r.value_rub,'rub',0)}</td>
    <td class="num ${cls(r.pnl_rub)}"><span class="arr">${r.pnl_rub>0?'▲':r.pnl_rub<0?'▼':''}</span>${r.pnl_pct!=null?pct(r.pnl_pct,1):'—'}</td>
    ${heatCell(r.share,mxS,'201,133,0',pctp(r.share))}
    ${heatCell(r.ytm,mxY,'25,158,112',r.ytm!=null?pctp(r.ytm,2)+(r.to==='offer'?' <small class="mu">оф.</small>':''):'—')}
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread)+' п.п.':'—'}</td>
    ${heatCell(r.dur,mxD,'213,81,129',r.dur!=null?r.dur.toFixed(2).replace('.',',')+' г':'—')}
    <td class="num">${r.coupon!=null?pctp(r.coupon,2):'—'}</td>
    <td class="num">${r.next?`${ddm(r.next[0])}<br><small class="mu">${M(r.next[1])}</small>`:'—'}</td>
    <td class="num">${r.maturity?ddm(r.maturity):'—'}${r.call?`<br><small class="mu">оферта ${ddm(r.call)}</small>`:''}</td>
    <td class="l">${r.rating?ratingTag(r.rating):'<span class="mu">—</span>'}</td>
    <td class="l">${r.risk?`<span class="tag" style="${r.risk==='высокий'?'color:var(--neg)':r.risk==='низкий'?'color:var(--pos)':''}">${r.risk}</span>`:''}</td></tr>`).join('');
  chart('c-ladder',bars,{h:220,labels:b.ladder.map(x=>x[0]),series:[{n:'Погашается / оферта',c:S1,v:b.ladder.map(x=>x[1])}],legend:false});
  return`<div class="g g6">${kpi('Облигации',M(m.value,'rub',0),`${m.count} выпусков · ${pctp(m.value/tot*100)} портфеля`,null,S1)}
    ${kpi('Доходность портфеля',pctp(m.ytm,2),'средневзвешенная к погашению / оферте','pos',S3)}
    ${kpi('Дюрация',m.dur!=null?m.dur.toFixed(2).replace('.',',')+' года':'—','средневзвешенная, по Маколею',null,S5)}
    ${kpi('Текущая купонная доходность',pctp(m.cur_yield,2),'годовой купон / цена',null,S4)}
    ${kpi('Купоны за 12 месяцев',M(m.coupons_12m,'rub',0),'по графику выплат, до налога','pos',S7)}
    ${kpi('Эмитентов',m.issuers,'диверсификация по компаниям',null,S2)}</div>
    <div class="card" style="padding:12px 10px 6px"><div class="tbl" style="max-height:calc(100vh - 200px)"><table id="btab" class="bt"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div></div>
    <div class="g g3"><div class="card"><h2>Лестница погашений и оферт, ₽</h2><div id="c-ladder" class="chart"></div></div>
    <div class="card"><h2>Кредитный риск (оценка брокера)</h2>${hbars(b.risk.map(([n,v])=>({n,v,c:n==='высокий'?S8:n==='низкий'?S3:n==='средний'?S4:'#6f7686',s:pctp(v/(m.value||1)*100)})),S1,null,0)}</div>
    <div class="card"><h2>Тип купона, выпусков</h2>${hbars(b.kinds.map(([n,v],i)=>({n,v,c:PAL[i]})),S1,x=>f0(x.v),1)}</div></div>
    ${ratingsCard(b)}
    ${insightsCard(b)}
    <p class="note">Доходность — эффективная годовая к погашению или к ближайшей оферте (пометка «оф.»), по текущей цене с НКД. Для флоатеров будущие купоны приняты равными последнему известному, для облигаций с амортизацией расчёт приблизительный. Дюрация — по Маколею, в годах.</p>`;
}



