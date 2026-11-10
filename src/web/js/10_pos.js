/* ── Позиции ── */
function pPos(){
  const all=S.data.portfolio.positions,typesHere=[...new Set(all.map(x=>x.type))].filter(Boolean);
  let ps=all.filter(x=>!S.posType||x.type===S.posType);
  const{k,d}=S.sort;
  ps=ps.slice().sort((a,b)=>{const x=a[k],y=b[k];if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  const nonCur=all.filter(x=>x.type!=='currency');
  const totPnl=nonCur.reduce((a,x)=>a+(x.pnl_rub||0),0),tot=all.reduce((a,x)=>a+(x.value_rub||0),0)||1;
  const top5=nonCur.slice().sort((a,b)=>(b.value_rub||0)-(a.value_rub||0)).slice(0,5).reduce((a,x)=>a+(x.value_rub||0),0)/tot*100;
  const sect={};nonCur.forEach(x=>{const s=SECT[x.sector]||(x.type==='etf'?'Фонды':x.sector?x.sector:'Без сектора');sect[s]=(sect[s]||0)+(x.value_rub||0)});
  const sectItems=Object.entries(sect).sort((a,b)=>b[1]-a[1]);
  const sec8=sectItems.slice(0,7).map(([n,v],i)=>({n,v,c:PAL[i]}));if(sectItems.length>7)sec8.push({n:'Остальные',v:sectItems.slice(7).reduce((a,x)=>a+x[1],0),c:S8});
  chart('c-sect',donut,{items:sec8,cap:'По секторам',size:170});
  const cols=[['name','Инструмент','l'],['type','Тип','l'],['qty','Кол-во'],['avg','Средняя'],['price','Текущая'],['value_rub','Стоимость, ₽'],['share','Доля'],['pnl_rub','P&L, ₽'],['pnl_pct','P&L %']];
  const th=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  const mxs=Math.max(1,...ps.map(x=>x.share||0));
  const rows=ps.map(x=>`<tr><td>${ident(x)}</td>
    <td class="l"><span class="tag">${TYPES[x.type]||esc(x.type)}</span>${x.blocked?' <span class="tag" style="color:var(--neg)">блок</span>':''}</td>
    <td class="num">${NFQ.format(x.qty)}</td><td class="num">${x.avg&&x.type!=='currency'?M(x.avg,x.cur):'—'}</td><td class="num">${M(x.price,x.cur)}</td>
    <td class="num">${x.value_rub!=null?M(x.value_rub):M(x.value,x.cur)}</td>
    <td class="num"><div class="share"><i style="width:${Math.max(1,(x.share||0)/mxs*60)}px"></i>${pctp(x.share)}</div></td>
    <td class="num ${cls(x.pnl)}">${x.type==='currency'?'<span class="mu">—</span>':x.pnl_rub!=null?SM(x.pnl_rub):SM(x.pnl,x.cur)}</td><td class="num ${cls(x.pnl)}">${x.type==='currency'?'':pct(x.pnl_pct)}</td></tr>`).join('');
  return`<div class="g g4">${kpi('Позиций',nonCur.length,'без учёта валюты и денег')}${kpi('Нереализованный P&L',SM(totPnl),'по открытым позициям',cls(totPnl))}
    ${kpi('В прибыли / в убытке',`<span class="pos">${nonCur.filter(x=>x.pnl>0).length}</span> <span class="mu">/</span> <span class="neg">${nonCur.filter(x=>x.pnl<0).length}</span>`,'позиций')}
    ${kpi('Топ-5 позиций',pctp(top5),'доля в портфеле — концентрация',top5>60?'neg':'')}</div>
    <div class="g c-1-2"><div class="card"><h2>Секторы</h2><div id="c-sect" class="chart"></div></div>
    <div class="card"><h2>Крупнейшие доли</h2>${hbars(nonCur.slice().sort((a,b)=>(b.value_rub||0)-(a.value_rub||0)).slice(0,10).map(x=>({n:x.name,v:x.share||0})),S1,x=>pctp(x.v),1)}</div></div>
    <div class="card" style="padding:12px 10px 6px"><div class="row" style="padding:0 6px 10px"><div class="seg" id="ptype"><button class="${!S.posType?'on':''}" data-t="">Все · ${all.length}</button>${typesHere.map(t=>`<button class="${S.posType===t?'on':''}" data-t="${t}">${TYPES[t]||t} · ${all.filter(x=>x.type===t).length}</button>`).join('')}</div></div>
    ${ps.length?`<div class="tbl" style="max-height:calc(100vh - 220px)"><table id="ptab"><thead><tr>${th}</tr></thead><tbody>${rows}</tbody></table></div>`:'<div class="empty">Позиций нет</div>'}</div>
    <p class="note">P&amp;L по счетам Т-Инвестиций — по данным брокера (FIFO), для облигаций без НКД. По импортированным счетам — расчёт по сделкам из отчёта и текущим ценам биржи.</p>`;
}


