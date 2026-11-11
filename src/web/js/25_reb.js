/* ── Ребалансировка ── */
S.reb={contrib:'',buyOnly:true,draft:null,tax:null};S.payDays=90;
/* налог при продаже (маршрут /api/tax/reb): сначала продаём бумаги с убытком и с наступившей ЛДВ */
function rebTaxHtml(act,keys){
  if(S.reb.buyOnly)return'';
  const sells=keys.filter(k=>(act[k]||0)<-1&&!['currency','other'].includes(k)).map(k=>k+':'+Math.round(-act[k]));
  if(!sells.length)return'';
  const key=S.account+'|'+sells.join(','),t=S.reb.tax;
  if(!t||t.key!==key){
    const cur=S.reb.tax={key,data:null,err:0};
    api('/api/tax/reb?'+new URLSearchParams({account:S.account,sells:sells.join(',')}))
      .then(j=>{if(S.reb.tax===cur){cur.data=j;if(S.page==='reb')renderSoon()}})
      .catch(e=>{if(S.reb.tax===cur){cur.err=1;if(S.page==='reb')renderSoon()}});
    return`<div class="card">${waitBox('Считаю налог с продаж…')}</div>`;
  }
  if(t.err)return'';
  if(!t.data)return`<div class="card">${waitBox('Считаю налог с продаж…')}</div>`;
  const it=t.data.items.filter(x=>x.tax_plan!=null);
  if(!it.length)return'';
  const tot=it.reduce((a,x)=>a+x.tax_plan,0),nv=it.reduce((a,x)=>a+x.tax_naive,0);
  const why=w=>w==='убыток'?'<span class="pos">убыток: налог не возникает</span>':w==='есть налог'?'<span class="neg">есть налог</span>':'<span class="pos">ЛДВ: прибыль освобождена</span>';
  return`<div class="card"><h2>Налог при продаже<span class="sp">оценка НДФЛ за текущий год с учётом уже полученной прибыли</span></h2>
    <div class="g g4">${kpi('Налог по плану',M(tot,'rub',0),'сначала лоты с убытком и с наступившей ЛДВ',tot>0?'neg':'pos')}${kpi('Если продавать пропорционально',M(nv,'rub',0),'всем бумагам класса поровну')}${kpi('Выгода порядка продаж',M(Math.max(0,nv-tot),'rub',0),'меньше налога',nv>tot?'pos':'')}</div>
    ${it.map(x=>`<h3 style="margin:14px 0 6px;font-size:13px">${esc(TYPES[x.cls]||x.cls)}: продать на ${M(x.covered,'rub',0)}${x.covered<x.amount-1?` (из ${M(x.amount,'rub',0)} — не хватает бумаг с известной ценой)`:''} · налог ${M(x.tax_plan,'rub',0)}</h3>
      <div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>Продать</th><th>Результат продажи</th><th class="l">Почему</th></tr></thead><tbody>${x.plan.map(p=>`<tr><td class="l"><b>${esc(p.name)}</b><br><small class="mu">${esc(p.ticker)}</small></td><td class="num">${M(p.sell_rub,'rub',0)}<br><small class="mu">${NF0.format(p.qty)} шт.</small></td><td class="num ${cls(p.result)}">${SM(p.result)}</td>
        <td class="l">${why(p.why)}${p.ldv_soon?'<br><small class="neg">ЛДВ наступит меньше чем через полгода — лучше подождать</small>':''}</td></tr>`).join('')||'<tr><td colspan="4" class="l mu">Нет данных о лотах</td></tr>'}</tbody></table></div>`).join('')}
    <p class="note">Справочная оценка: порядок бумаг подбирается по ожидаемому налогу, продажа идёт по FIFO внутри каждой бумаги. Брокер как налоговый агент считает сам; это не налоговая консультация.</p></div>`;
}
function pReb(){
  const ps=S.data.portfolio.positions,tot=ps.reduce((a,x)=>a+(x.value_rub||0),0);
  if(!(tot>0))return'<div class="card empty">В портфеле нет активов для расчёта</div>';
  const cur={};ps.forEach(x=>{const t=x.type||'other';cur[t]=(cur[t]||0)+(x.value_rub||0)});
  if(!S.reb.draft)S.reb.draft=Object.assign({},(S.cfg&&S.cfg.targets)||{});
  const tg=S.reb.draft;
  const keys=[...new Set([...Object.keys(cur),...Object.keys(tg)])].sort((a,b)=>(cur[b]||0)-(cur[a]||0));
  const sumT=keys.reduce((a,k)=>a+(+tg[k]||0),0),has=sumT>0;
  const C=Math.max(0,+S.reb.contrib||0),T2=tot+C,buyOnly=S.reb.buyOnly;
  const w=k=>has?(+tg[k]||0)/sumT:0;
  let act={};
  if(has){
    if(buyOnly){const need={};keys.forEach(k=>{need[k]=Math.max(0,T2*w(k)-(cur[k]||0))});const sp=keys.reduce((a,k)=>a+need[k],0);
      keys.forEach(k=>{act[k]=C>0&&sp>0?need[k]*C/sp:0})}
    else keys.forEach(k=>{act[k]=T2*w(k)-(cur[k]||0)});
  }
  const need0=has?Math.max(0,Math.max(...keys.filter(k=>w(k)>0).map(k=>(cur[k]||0)/w(k)))-tot):0;
  const after=k=>((cur[k]||0)+(act[k]||0))/(buyOnly?T2:T2);
  const rows=keys.map(k=>{const cp=(cur[k]||0)/tot*100,tp=has?w(k)*100:0,dv=cp-tp,a=act[k]||0;
    return`<tr><td class="l"><b>${esc(TYPES[k]||(k==='other'?'Прочее':k))}</b></td><td class="num">${M(cur[k]||0)}</td><td class="num">${pctp(cp)}</td>
      <td class="num"><input class="in num reb-in" data-k="${esc(k)}" type="number" min="0" max="100" step="0.5" value="${tg[k]!=null?tg[k]:''}" placeholder="0"> %</td>
      <td class="num ${has?(Math.abs(dv)<0.5?'mu':dv>0?'neg':'pos'):'mu'}">${has?(dv>0?'+':'')+dv.toFixed(1).replace('.',',')+' п.п.':'—'}</td>
      <td class="num ${a>0.5?'pos':a<-0.5?'neg':'mu'}">${Math.abs(a)<1?'—':(a>0?'Докупить ':'Продать ')+M(Math.abs(a))}</td>
      <td class="num">${has?pctp(after(k)*100):'—'}</td></tr>`}).join('');
  const dev=has?keys.reduce((a,k)=>a+Math.abs((cur[k]||0)/tot-w(k)),0)/2*100:0;
  return`<div class="g g4">${kpi('Стоимость портфеля',M(tot),'по текущим ценам')}${kpi('Сумма целей',`<span class="${!has?'mu':Math.abs(sumT-100)<0.05?'pos':'neg'}">${sumT.toFixed(1).replace('.',',')} %</span>`,!has?'введите целевые доли ниже':Math.abs(sumT-100)<0.05?'цели заданы':'расчёт нормирован к 100%')}
    ${kpi('Отклонение от целей',has?pctp(dev):'—','сколько % портфеля стоит «не там»',has&&dev>5?'neg':'')}${kpi('Без продаж нужно внести',has?M(need0):'—','чтобы выйти на цели одними покупками')}</div>
  <div class="card"><h2>Целевая структура по классам активов</h2>
    <div class="row" style="margin-bottom:14px;gap:18px;flex-wrap:wrap"><label class="field" style="max-width:240px"><span>Новый взнос, ₽ (необязательно)</span><input class="in num" id="rb-c" type="number" min="0" step="1000" value="${S.reb.contrib}" placeholder="0"></label>
      <label class="sw"><input type="checkbox" id="rb-b" ${buyOnly?'checked':''}><i></i><div><b>Только докупать</b><small>Ничего не продавать, распределить взнос</small></div></label></div>
    <div class="tbl"><table><thead><tr><th class="l">Класс</th><th>Сейчас, ₽</th><th>Сейчас</th><th>Цель</th><th>Отклонение</th><th>Действие</th><th>После</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="row" style="margin-top:14px"><button class="btn" id="rb-s">Сохранить цели</button><button class="btn ghost" id="rb-r">Сбросить</button><span class="reb-sum" id="rb-sum"></span></div></div>
  ${rebTaxHtml(act,keys)}
  <p class="note">Расчёт по классам активов (акции, облигации, фонды, валюта…) на уровне портфеля, без учёта комиссий и лотности; налог при продаже оценивается отдельно (в режиме с продажами). Это справочный расчёт, а не инвестиционная рекомендация. Цели сохраняются локально.</p>`;
}
function bindReb(){
  const d=S.reb.draft;
  $('#view').querySelectorAll('.reb-in').forEach(i=>i.onchange=()=>{const v=parseFloat(String(i.value).replace(',','.'));if(v>0)d[i.dataset.k]=Math.min(100,v);else delete d[i.dataset.k];render()});
  $('#rb-c').onchange=e=>{S.reb.contrib=e.target.value;render()};
  $('#rb-b').onchange=e=>{S.reb.buyOnly=e.target.checked;render()};
  $('#rb-r').onclick=()=>{S.reb.draft=null;S.reb.contrib='';render()};
  $('#rb-s').onclick=async e=>{e.currentTarget.disabled=true;try{await post('/api/config',{targets:d});S.cfg.targets=Object.assign({},d);$('#rb-sum').textContent='Сохранено'}catch(x){$('#rb-sum').textContent=x.message}finally{e.currentTarget.disabled=false}};
}

