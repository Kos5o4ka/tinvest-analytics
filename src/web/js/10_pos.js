/* ── Позиции ── */
function taCsvDownload(filename, headers, rows){
  const escCell=v=>{const s=v==null?'':String(v);return/[;"\r\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s};
  const lines=[headers.map(escCell).join(';')].concat(rows.map(r=>r.map(escCell).join(';')));
  const blob=new Blob(['\uFEFF'+lines.join('\r\n')],{type:'text/csv;charset=utf-8;'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function taCsvBtn(id,title){
  return`<button type="button" class="btn ghost tbl-csv noprint" id="${id}" title="${esc(title||'Скачать таблицу в CSV')}">${svgI('<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',1.8)}Экспорт CSV</button>`;
}

S.posGroup=lsGet('ta_pos_group')||'flat';
S.posHideSmall=lsGet('ta_pos_hsmall')==='1';

function posIssuer(x){
  if(x.type==='currency')return'Валюта и деньги';
  const bRows=(S.bonds&&S.bonds.rows)||[];
  const bHit=(x.isin||x.ticker)?bRows.find(b=>(x.isin&&b.isin===x.isin)||(x.ticker&&b.ticker===x.ticker)):null;
  if(bHit&&(bHit.emitter||bHit.issuer))return bHit.emitter||bHit.issuer;
  const nm=String(x.name||x.ticker||'Прочее').trim();
  if(/^ОФЗ\b/i.test(nm)||/^SU[0-9A-Z]+$/i.test(String(x.isin||'')))return'Минфин России (ОФЗ)';
  let base=nm.replace(/\s+(БО|КО|ПБО|00\d+[РP]|Р\d+|В?\d+Р[- ]\d+).*$/i,'')
    .replace(/\s+\d{2,}$/,'')
    .replace(/-(ао|ап|п|ao|ap)$/i,'')
    .trim();
  return base||nm||'Прочее';
}
function posFiltered(){
  const all=(S.data&&S.data.portfolio&&S.data.portfolio.positions)||[];
  let ps=all.filter(x=>!S.posType||x.type===S.posType);
  if(S.posHideSmall)ps=ps.filter(x=>!(x.share!=null&&x.share<1)&&!x.blocked);
  const{k,d}=S.sort;
  return ps.slice().sort((a,b)=>{const x=a[k],y=b[k];if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
}
function posRowHtml(x,mxs){
  return`<tr${x.type==='bond'&&(x.isin||x.ticker)?` data-isin="${esc(x.isin||x.ticker)}" title="Открыть карточку выпуска"`:(x.type==='share'||x.type==='etf')&&x.ticker?` data-stk="${esc(x.ticker)}" style="cursor:pointer" title="Открыть карточку ${x.type==='etf'?'фонда':'акции'}"`:''}><td>${ident(x)}</td>
    <td class="l"><span class="tag">${TYPES[x.type]||esc(x.type||'Прочее')}</span>${x.blocked?' <span class="tag" style="color:var(--neg)">блок</span>':''}</td>
    <td class="num">${NFQ.format(x.qty)}</td><td class="num">${x.avg&&x.type!=='currency'?M(x.avg,x.cur):'—'}</td><td class="num">${M(x.price,x.cur)}</td>
    <td class="num">${x.value_rub!=null?M(x.value_rub):M(x.value,x.cur)}</td>
    <td class="num"><div class="share"><i style="width:${Math.max(1,(x.share||0)/mxs*60)}px"></i>${pctp(x.share)}</div></td>
    <td class="num ${cls(x.pnl)}">${x.type==='currency'?'<span class="mu">—</span>':x.pnl_rub!=null?SM(x.pnl_rub):SM(x.pnl,x.cur)}</td><td class="num ${cls(x.pnl)}">${x.type==='currency'?'':pct(x.pnl_pct)}</td></tr>`;
}
function posGroupedRows(ps,mxs,mode){
  if(mode==='flat')return ps.map(x=>posRowHtml(x,mxs)).join('');
  const map=new Map();
  ps.forEach(x=>{
    const key=mode==='class'?(TYPES[x.type]||esc(x.type||'Прочее')):posIssuer(x);
    if(!map.has(key))map.set(key,[]);
    map.get(key).push(x);
  });
  const groups=[...map.entries()].sort((a,b)=>{
    const va=a[1].reduce((s,x)=>s+(x.value_rub||0),0),vb=b[1].reduce((s,x)=>s+(x.value_rub||0),0);
    return vb-va;
  });
  return groups.map(([gName,items])=>{
    const val=items.reduce((s,x)=>s+(x.value_rub||0),0);
    const sh=items.reduce((s,x)=>s+(x.share||0),0);
    const pnl=items.reduce((s,x)=>s+(x.type==='currency'?0:(x.pnl_rub||0)),0);
    const hdr=`<tr class="pos-gh"><td class="l" colspan="5"><b>${esc(gName)}</b><span class="pos-gh-cnt">${items.length}</span></td><td class="num"><b>${M(val,'rub',0)}</b></td><td class="num"><b>${pctp(sh)}</b></td><td class="num ${cls(pnl)}"><b>${SM(pnl)}</b></td><td></td></tr>`;
    return hdr+items.map(x=>posRowHtml(x,mxs)).join('');
  }).join('');
}

function pPos(){
  const all=S.data.portfolio.positions,typesHere=[...new Set(all.map(x=>x.type))].filter(Boolean);
  const ps=posFiltered();
  const{k,d}=S.sort;
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
  const grp=['flat','class','issuer'].includes(S.posGroup)?S.posGroup:'flat';
  const rows=posGroupedRows(ps,mxs,grp);
  const grpSeg=`<div class="seg" id="pos-grp" title="Группировка таблицы">${[['flat','Плоский список'],['class','По классам'],['issuer','По эмитентам']].map(([v,t])=>`<button type="button" data-pg="${v}" class="${grp===v?'on':''}">${t}</button>`).join('')}</div>`;
  const tableCard=`<div class="card pos-main" style="padding:14px 12px 8px">
    <div class="tbl-head"><h2 style="margin:0">Позиции портфеля<span class="sp">${ps.length} из ${all.length}</span></h2>
      <div class="row" style="margin-left:auto;gap:8px"><button type="button" class="btn ghost" id="pos-man">+ Добавить вручную</button>${taCsvBtn('pos-csv','Выгрузить текущие позиции в CSV')}</div></div>
    <div class="pos-ctl"><div class="seg" id="ptype"><button class="${!S.posType?'on':''}" data-t="">Все · ${all.length}</button>${typesHere.map(t=>`<button class="${S.posType===t?'on':''}" data-t="${t}">${TYPES[t]||t} · ${all.filter(x=>x.type===t).length}</button>`).join('')}</div>
      ${grpSeg}
      <label class="sw" title="Скрыть позиции с долей меньше 1% и заблокированные бумаги"><input type="checkbox" id="pos-hsmall" ${S.posHideSmall?'checked':''}><i></i><div><b>Скрыть мелочь (&lt;1%) и заблокированные</b></div></label>
      <input class="in" id="pq" type="search" placeholder="Поиск по названию, тикеру, ISIN…" value="${esc(S.posQ||'')}" aria-label="Поиск по позициям" style="flex:1;min-width:200px;max-width:320px;margin-left:auto"></div>
    ${ps.length?`<div class="tbl"><table id="ptab"><thead><tr>${th}</tr></thead><tbody>${rows}</tbody></table></div>`:emptyHint('Открытых позиций под текущие фильтры нет. Сбросьте фильтры или добавьте бумаги.',[['imp','Импорт отчёта',1],['dash','На «Обзор»']])}</div>`;
  const sideCards=`<div class="pos-side"><div class="card"><h2>Секторы</h2><div id="c-sect" class="chart"></div></div>
    <div class="card"><h2>Крупнейшие доли</h2>${hbars(nonCur.slice().sort((a,b)=>(b.value_rub||0)-(a.value_rub||0)).slice(0,10).map(x=>({n:x.name,v:x.share||0})),S1,x=>pctp(x.v),1)}</div></div>`;
  return`<div class="g g4">${kpi('Позиций',nonCur.length,'без учёта валюты и денег')}${kpi('Нереализованный P&L',SM(totPnl),'по открытым позициям',cls(totPnl))}
    ${kpi('В прибыли / в убытке',`<span class="pos">${nonCur.filter(x=>x.pnl>0).length}</span> <span class="mu">/</span> <span class="neg">${nonCur.filter(x=>x.pnl<0).length}</span>`,'позиций')}
    ${kpi('Топ-5 позиций',pctp(top5),'доля в портфеле — концентрация',top5>60?'neg':'')}</div>
    <div class="pos-layout">${tableCard}${sideCards}</div>
    <p class="note">P&amp;L по счетам Т-Инвестиций — по данным брокера (FIFO), для облигаций без НКД. По импортированным счетам — расчёт по сделкам из отчёта и текущим ценам биржи.</p>`;
}

/* живой поиск по таблице позиций: скрываем строки, не меняя сортировку и остальной экран */
function posFilterApply(){
  const t=document.getElementById('ptab');if(!t)return;
  const q=String(S.posQ||'').trim().toLowerCase();
  t.querySelectorAll('tbody tr:not(.pos-gh)').forEach(tr=>{tr.style.display=!q||tr.textContent.toLowerCase().includes(q)||(tr.dataset.isin||'').toLowerCase().includes(q)||(tr.dataset.stk||'').toLowerCase().includes(q)?'':'none'});
}

document.addEventListener('click',e=>{
  const t=e.target;if(!t.closest)return;
  const pg=t.closest('#pos-grp [data-pg]');
  if(pg){S.posGroup=pg.dataset.pg;lsSet('ta_pos_group',S.posGroup);render();return}
  if(t.closest('#pos-man')){if(typeof manualOpen==='function')manualOpen();return}
  if(t.closest('#pos-csv')){
    const q=String(S.posQ||'').trim().toLowerCase();
    const rows=posFiltered().filter(x=>!q||String(x.name||'').toLowerCase().includes(q)||String(x.ticker||'').toLowerCase().includes(q)||String(x.isin||'').toLowerCase().includes(q));
    taCsvDownload('positions.csv',['Название','Тикер','ISIN','Класс','Эмитент','Кол-во','Средняя','Текущая','Валюта','Стоимость, ₽','Доля, %','P&L, ₽','P&L, %','Блок'],
      rows.map(x=>[x.name||'',x.ticker||'',x.isin||'',TYPES[x.type]||x.type||'',posIssuer(x),x.qty??'',x.avg??'',x.price??'',(x.cur||'rub').toUpperCase(),x.value_rub??x.value??'',x.share!=null?x.share.toFixed(2):'',x.pnl_rub??x.pnl??'',x.pnl_pct!=null?x.pnl_pct.toFixed(2):'',x.blocked?'да':'нет']));
  }
});
document.addEventListener('change',e=>{
  if(e.target&&e.target.id==='pos-hsmall'){S.posHideSmall=e.target.checked;lsSet('ta_pos_hsmall',S.posHideSmall?'1':'0');render()}
});
