/* ── Ребалансировка + Снежный ком купонов (безналоговая ребалансировка, #9) ── */
S.reb={contrib:'',monthly:'',buyOnly:true,draft:null,tax:null,lvl:lsGet('ta_reb_lvl')||'class',rtDraft:lsJson('ta_reb_rt',null),secDraft:lsJson('ta_reb_sec',null)};S.payDays=90;
const REB_RT_BUCKETS=['AAA','AA','A','BBB','BB и ниже','Без рейтинга'];
function rebRtBucket(r){
  if(!r||!r.rating||!r.rating.v)return'Без рейтинга';
  const bk=rBucket(r.rating.v).split(' ')[0];
  if(bk==='AAA'||bk==='AA'||bk==='A'||bk==='BBB')return bk;
  return'BB и ниже';
}
function rebGoScreener(opts){
  const f=Object.assign({},SCR_DEF,{cur:'RUB'});
  if(opts.rmin)f.rmin=opts.rmin;
  if(opts.kind)f.kind=opts.kind;
  S.sf=f;S.scrPreset='';S.scrOpen=true;
  if(opts.amt>0)toast('Подбор облигаций на '+M(opts.amt,'rub',0));
  go('scr');
}
function rebScrBtn(kindKey,amt,label){
  if(!(amt>100))return'';
  return` <button type="button" class="btn ghost reb-scr-btn" data-reb-scr="${esc(kindKey)}" data-amt="${Math.round(amt)}">${esc(label||'Подобрать в Скринере на '+M(amt,'rub',0)+' →')}</button>`;
}
function rebSnowballHtml(cur,keys,w,tot,dev0){
  const pays=(S.bonds&&S.bonds.payments)||[];
  const now=new Date(),mKeys=[],byM={};
  for(let i=0;i<12;i++){const d=new Date(now.getFullYear(),now.getMonth()+i,1);const k=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');mKeys.push(k);byM[k]=0}
  pays.forEach(p=>{const m=(p.date||'').slice(0,7);if(byM[m]!=null&&(p.kind==='coupon'||p.kind==='dividend'||p.kind==='amortization'||p.kind==='redemption'))byM[m]+=p.amount||0});
  const mExtra=Math.max(0,+S.reb.monthly||0);
  const totPay12=mKeys.reduce((a,k)=>a+byM[k],0);
  const sim=Object.assign({},cur);let sTot=tot;
  const plan=mKeys.map(mk=>{
    const inflow=byM[mk]+mExtra;
    const buys=[];
    if(inflow>1){
      sTot+=inflow;
      const need={};let sn=0;
      keys.forEach(k=>{const v=Math.max(0,sTot*w(k)-(sim[k]||0));need[k]=v;sn+=v});
      keys.forEach(k=>{
        const add=sn>0?inflow*need[k]/sn:inflow*w(k);
        if(add>=10){sim[k]=(sim[k]||0)+add;buys.push([k,add])}
      });
    }
    const dev=keys.reduce((a,k)=>a+Math.abs((sim[k]||0)/Math.max(1,sTot)-w(k)),0)/2*100;
    return{mk,pay:byM[mk],extra:mExtra,inflow,buys,dev};
  });
  const dev12=plan.length?plan[plan.length-1].dev:dev0;
  return`<div class="card"><h2>Снежный ком купонов: безналоговая ребалансировка на 12 мес.<span class="sp">0 ₽ продаж · 0 ₽ НДФЛ</span></h2>
    <div class="row" style="margin-bottom:12px;gap:16px;flex-wrap:wrap;align-items:flex-end">
      <label class="field" style="max-width:250px"><span>Ежемесячное пополнение, ₽</span><input class="in num" id="rb-m" type="number" min="0" step="5000" value="${S.reb.monthly}" placeholder="0"></label>
      <span class="mu" style="font-size:12.5px">Все купоны, дивиденды и пополнения направляются только в отстающие от целевых долей классы активов.</span></div>
    <div class="g g3" style="margin-bottom:12px">
      ${kpi('Поступления по бумагам (12 мес.)',M(totPay12,'rub',0),'купоны, дивиденды, погашения',totPay12>0?'pos':'')}
      ${kpi('Всего на докупки за 12 мес.',M(totPay12+mExtra*12,'rub',0),mExtra>0?'выплаты + по '+M(mExtra,'rub',0)+'/мес':'только из выплат портфеля')}
      ${kpi('Отклонение от целей',pctp(dev0,1)+' → '+pctp(dev12,1),'снижение перекоса без единой продажи',dev12<dev0?'pos':'')}</div>
    <div class="tbl"><table><thead><tr><th class="l">Месяц</th><th>Выплаты портфеля</th><th>Пополнение</th><th class="l">Что докупить (без продаж)</th><th>Отклонение после</th></tr></thead><tbody>`+
    plan.map(r=>`<tr><td class="l"><b>${esc(mlabel(r.mk))} ${r.mk.slice(0,4)}</b></td><td class="num">${r.pay>0?M(r.pay,'rub',0):'<span class="mu">—</span>'}</td>
      <td class="num">${r.extra>0?M(r.extra,'rub',0):'<span class="mu">—</span>'}</td>
      <td class="l">${r.buys.length?r.buys.sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<span class="tag">${esc(TYPES[k]||k)}: ${M(v,'rub',0)}</span>`).join(' '):'<span class="mu">нет поступлений</span>'}</td>
      <td class="num">${pctp(r.dev,1)}</td></tr>`).join('')+`</tbody></table></div></div>`;
}
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
      <div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>Продать</th><th>Результат продажи</th><th class="l">Почему</th></tr></thead><tbody>${x.plan.map(p=>`<tr${stkAttrIf(p.ticker)}><td class="l"><b>${esc(p.name)}</b><br><small class="mu">${esc(p.ticker)}</small></td><td class="num">${M(p.sell_rub,'rub',0)}<br><small class="mu">${NF0.format(p.qty)} шт.</small></td><td class="num ${cls(p.result)}">${SM(p.result)}</td>
        <td class="l">${why(p.why)}${p.ldv_soon?'<br><small class="neg">ЛДВ наступит меньше чем через полгода — лучше подождать</small>':''}</td></tr>`).join('')||'<tr><td colspan="4" class="l mu">Нет данных о лотах</td></tr>'}</tbody></table></div>`).join('')}
    <p class="note">Справочная оценка: порядок бумаг подбирается по ожидаемому налогу, продажа идёт по FIFO внутри каждой бумаги. Брокер как налоговый агент считает сам; это не налоговая консультация.</p></div>`;
}
function rebCalcActions(cur,tg,keys,tot,C,buyOnly){
  const sumT=keys.reduce((a,k)=>a+(+tg[k]||0),0),has=sumT>0,T2=tot+C,w=k=>has?(+tg[k]||0)/sumT:0,act={};
  if(has){
    if(buyOnly){const need={};keys.forEach(k=>{need[k]=Math.max(0,T2*w(k)-(cur[k]||0))});const sp=keys.reduce((a,k)=>a+need[k],0);
      keys.forEach(k=>{act[k]=C>0&&sp>0?need[k]*C/sp:0})}
    else keys.forEach(k=>{act[k]=T2*w(k)-(cur[k]||0)});
  }
  const need0=has?Math.max(0,Math.max(...keys.filter(k=>w(k)>0).map(k=>(cur[k]||0)/w(k)))-tot):0;
  const dev=has?keys.reduce((a,k)=>a+Math.abs((cur[k]||0)/tot-w(k)),0)/2*100:0;
  return{sumT,has,T2,w,act,need0,dev};
}
function rebLvlBar(lvl){
  return`<div class="reb-lvl-bar"><div class="seg" id="rb-lvl">${[['class','По классам'],['rating','По рейтингам облигаций'],['paper','По бумагам в лотах']].map(([k,t])=>`<button type="button" data-rl="${k}" class="${lvl===k?'on':''}">${t}</button>`).join('')}</div></div>`;
}
function rebCtlBar(buyOnly){
  return`<div class="row" style="margin-bottom:14px;gap:18px;flex-wrap:wrap"><label class="field" style="max-width:240px"><span>Новый взнос, ₽ (необязательно)</span><input class="in num" id="rb-c" type="number" min="0" step="1000" value="${S.reb.contrib}" placeholder="0"></label>
    <label class="sw"><input type="checkbox" id="rb-b" ${buyOnly?'checked':''}><i></i><div><b>Только докупать</b><small>Ничего не продавать, распределить взнос</small></div></label></div>`;
}
function pRebRating(totAll){
  const b=S.bonds;
  if(!b)return rebLvlBar('rating')+`<div class="card">${waitBox('Загружаю рейтинги облигаций портфеля…')}</div>`;
  if(b.error)return rebLvlBar('rating')+`<div class="msg err">${esc(b.error)}</div>`;
  const bRows=b.rows||[];
  if(!bRows.length)return rebLvlBar('rating')+emptyHint('В этом счёте нет облигаций для ребалансировки по рейтингам.',[['scr','Подобрать в Скринере',1],['bonds','Мои облигации']]);
  const cur={};REB_RT_BUCKETS.forEach(k=>cur[k]=0);
  bRows.forEach(r=>{const k=rebRtBucket(r);cur[k]=(cur[k]||0)+(r.value_rub||0)});
  const tot=Object.values(cur).reduce((a,x)=>a+x,0)||1;
  if(!S.reb.rtDraft)S.reb.rtDraft={AAA:40,AA:40,A:20};
  const tg=S.reb.rtDraft,keys=REB_RT_BUCKETS.filter(k=>cur[k]>0||tg[k]>0||['AAA','AA','A','BBB'].includes(k));
  const C=Math.max(0,+S.reb.contrib||0),buyOnly=S.reb.buyOnly;
  const{sumT,has,T2,w,act,need0,dev}=rebCalcActions(cur,tg,keys,tot,C,buyOnly);
  const rows=keys.map(k=>{const cp=(cur[k]||0)/tot*100,tp=has?w(k)*100:0,dv=cp-tp,a=act[k]||0;
    const scrBtn=a>100?rebScrBtn('rt:'+k,a):'';
    return`<tr><td class="l"><b>${esc(k)}</b></td><td class="num">${M(cur[k]||0,'rub',0)}</td><td class="num">${pctp(cp)}</td>
      <td class="num"><input class="in num reb-rt-in" data-k="${esc(k)}" type="number" min="0" max="100" step="1" value="${tg[k]!=null?tg[k]:''}" placeholder="0"> %</td>
      <td class="num ${has?(Math.abs(dv)<0.5?'mu':dv>0?'neg':'pos'):'mu'}">${has?(dv>0?'+':'')+dv.toFixed(1).replace('.',',')+' п.п.':'—'}</td>
      <td class="num ${a>0.5?'pos':a<-0.5?'neg':'mu'}">${Math.abs(a)<1?'—':(a>0?'Докупить ':'Продать ')+M(Math.abs(a),'rub',0)}${scrBtn}</td>
      <td class="num">${has?pctp(((cur[k]||0)+a)/T2*100):'—'}</td></tr>`}).join('');
  return rebLvlBar('rating')+`<div class="g g4">${kpi('Облигаций в портфеле',M(tot,'rub',0),`${bRows.length} выпусков · ${pctp(tot/(totAll||1)*100)} портфеля`)}${kpi('Сумма целей',`<span class="${!has?'mu':Math.abs(sumT-100)<0.05?'pos':'neg'}">${sumT.toFixed(1).replace('.',',')} %</span>`,!has?'задайте целевые доли':'к 100%')}
    ${kpi('Отклонение от целей',has?pctp(dev):'—','по рейтингам облигаций',has&&dev>5?'neg':'')}${kpi('Без продаж нужно внести',has?M(need0,'rub',0):'—','для выравнивания облигаций')}</div>
  <div class="card"><h2>Целевая структура облигаций по рейтингам</h2>${rebCtlBar(buyOnly)}
    <div class="scr-presets reb-pre noprint" style="margin-bottom:12px"><span class="mu" style="font-size:12.5px">Быстрые цели:</span>
      <button type="button" class="scr-chip" data-rtrp="cons">Консервативно (AAA 40 / AA 40 / A 20)</button>
      <button type="button" class="scr-chip" data-rtrp="bal">Умеренно (AAA 25 / AA 35 / A 30 / BBB 10)</button>
      <button type="button" class="scr-chip" data-rtrp="eq">Равные доли</button></div>
    <div class="tbl"><table><thead><tr><th class="l">Рейтинг</th><th>Сейчас, ₽</th><th>Сейчас</th><th>Цель</th><th>Отклонение</th><th>Действие</th><th>После</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}
function pRebPaper(ps){
  const nonCur=ps.filter(x=>x.type!=='currency'&&x.type!=='futures'&&(x.value_rub||0)>0);
  if(!nonCur.length)return rebLvlBar('paper')+emptyHint('Нет бумаг для расчёта лотов.',[['imp','Импорт отчёта',1]]);
  const tot=nonCur.reduce((a,x)=>a+(x.value_rub||0),0)||1;
  const keyOf=x=>x.isin||x.ticker||x.uid||x.name;
  if(!S.reb.secDraft){
    const d={};nonCur.forEach(x=>{d[keyOf(x)]=Math.round((x.value_rub||0)/tot*1000)/10});
    S.reb.secDraft=d;
  }
  const tg=S.reb.secDraft,cur={},byKey=new Map();
  nonCur.forEach(x=>{const k=keyOf(x);cur[k]=(cur[k]||0)+(x.value_rub||0);byKey.set(k,x)});
  const keys=[...byKey.keys()].sort((a,b)=>(cur[b]||0)-(cur[a]||0));
  const C=Math.max(0,+S.reb.contrib||0),buyOnly=S.reb.buyOnly;
  const{sumT,has,T2,w,act,need0,dev}=rebCalcActions(cur,tg,keys,tot,C,buyOnly);
  const bRows=(S.bonds&&S.bonds.rows)||[],stkAll=(S.stkList||[]).concat(S.stkFunds||[]);
  const rows=keys.map(k=>{
    const x=byKey.get(k),cp=(cur[k]||0)/tot*100,tp=has?w(k)*100:0,dv=cp-tp,a=act[k]||0;
    const unitPx=(x.qty>0&&(x.value_rub||0)>0)?(x.value_rub/x.qty):((x.price||0)+(x.nkd||0));
    const stInfo=x.type!=='bond'&&x.ticker?stkAll.find(s=>s.secid===x.ticker):null;
    const lot=x.type==='bond'?1:(stInfo&&stInfo.lot>1?stInfo.lot:1);
    const lotCost=unitPx*lot;
    const lots=lotCost>0?Math.round(Math.abs(a)/lotCost):0;
    const bInfo=x.type==='bond'?bRows.find(b=>(x.isin&&b.isin===x.isin)||(x.ticker&&b.ticker===x.ticker)):null;
    const unitLbl=lot>1?`${f0(lots)} лот (${f0(lots*lot)} шт.)`:`${f0(lots)} шт.`;
    const scrBtn=a>lotCost&&x.type==='bond'?rebScrBtn('rt:'+(bInfo?rebRtBucket(bInfo):'A'),a,'Подобрать в Скринере на '+M(a,'rub',0)+' →'):'';
    return`<tr><td class="l">${ident(x)}</td><td class="num">${unitPx>0?M(unitPx,'rub',2):'—'}${lot>1?`<br><small class="mu">лот ${lot} шт.</small>`:''}</td>
      <td class="num">${M(cur[k]||0,'rub',0)}<br><small class="mu">${pctp(cp)}</small></td>
      <td class="num"><input class="in num reb-sec-in" data-k="${esc(k)}" type="number" min="0" max="100" step="0.5" value="${tg[k]!=null?tg[k]:''}" placeholder="0"> %</td>
      <td class="num ${has?(Math.abs(dv)<0.5?'mu':dv>0?'neg':'pos'):'mu'}">${has?(dv>0?'+':'')+dv.toFixed(1).replace('.',',')+' п.п.':'—'}</td>
      <td class="num ${a>0.5?'pos':a<-0.5?'neg':'mu'}">${Math.abs(a)<1||!lots?'—':(a>0?'Купить ':'Продать ')+unitLbl+`<br><small class="mu">${M(lots*lotCost,'rub',0)}</small>`}${scrBtn}</td>
      <td class="num">${has?pctp(((cur[k]||0)+a)/T2*100):'—'}</td></tr>`}).join('');
  return rebLvlBar('paper')+`<div class="g g4">${kpi('Бумаг в расчёте',nonCur.length,M(tot,'rub',0)+' по рыночным ценам')}${kpi('Сумма целей',`<span class="${!has?'mu':Math.abs(sumT-100)<0.05?'pos':'neg'}">${sumT.toFixed(1).replace('.',',')} %</span>`,!has?'задайте доли':'к 100%')}
    ${kpi('Отклонение от целей',has?pctp(dev):'—','по отдельным бумагам',has&&dev>5?'neg':'')}${kpi('Без продаж нужно внести',has?M(need0,'rub',0):'—','по текущим ценам')}</div>
  <div class="card"><h2>Ребалансировка по бумагам в лотах</h2>${rebCtlBar(buyOnly)}
    <div class="scr-presets reb-pre noprint" style="margin-bottom:12px"><span class="mu" style="font-size:12.5px">Заполнить цели:</span>
      <button type="button" class="scr-chip" data-secp="cur">По текущим долям</button>
      <button type="button" class="scr-chip" data-secp="eq">Равные доли</button></div>
    <div class="tbl"><table><thead><tr><th class="l">Бумага</th><th>Цена с НКД</th><th>Сейчас</th><th>Цель</th><th>Отклонение</th><th>В лотах по рынку</th><th>После</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}
function pReb(){
  const ps=S.data.portfolio.positions,tot=ps.reduce((a,x)=>a+(x.value_rub||0),0);
  if(!(tot>0))return emptyHint('Ребалансировке нужны активы в портфеле. Выберите счёт с бумагами или загрузите отчёт брокера.',[['imp','Импорт отчёта',1],['dash','На «Обзор»']]);
  const lvl=['class','rating','paper'].includes(S.reb.lvl)?S.reb.lvl:'class';
  if(lvl==='rating')return pRebRating(tot);
  if(lvl==='paper')return pRebPaper(ps);
  const cur={};ps.forEach(x=>{const t=x.type||'other';cur[t]=(cur[t]||0)+(x.value_rub||0)});
  if(!S.reb.draft)S.reb.draft=Object.assign({},(S.cfg&&S.cfg.targets)||{});
  const tg=S.reb.draft;
  const keys=[...new Set([...Object.keys(cur),...Object.keys(tg)])].sort((a,b)=>(cur[b]||0)-(cur[a]||0));
  const C=Math.max(0,+S.reb.contrib||0),buyOnly=S.reb.buyOnly;
  const{sumT,has,T2,w,act,need0,dev}=rebCalcActions(cur,tg,keys,tot,C,buyOnly);
  const rows=keys.map(k=>{const cp=(cur[k]||0)/tot*100,tp=has?w(k)*100:0,dv=cp-tp,a=act[k]||0;
    const scrBtn=(k==='bond'&&a>100)?rebScrBtn('cls:bond',a):'';
    return`<tr><td class="l"><b>${esc(TYPES[k]||(k==='other'?'Прочее':k))}</b></td><td class="num">${M(cur[k]||0)}</td><td class="num">${pctp(cp)}</td>
      <td class="num"><input class="in num reb-in" data-k="${esc(k)}" type="number" min="0" max="100" step="0.5" value="${tg[k]!=null?tg[k]:''}" placeholder="0"> %</td>
      <td class="num ${has?(Math.abs(dv)<0.5?'mu':dv>0?'neg':'pos'):'mu'}">${has?(dv>0?'+':'')+dv.toFixed(1).replace('.',',')+' п.п.':'—'}</td>
      <td class="num ${a>0.5?'pos':a<-0.5?'neg':'mu'}">${Math.abs(a)<1?'—':(a>0?'Докупить ':'Продать ')+M(Math.abs(a))}${scrBtn}</td>
      <td class="num">${has?pctp(((cur[k]||0)+a)/T2*100):'—'}</td></tr>`}).join('');
  return rebLvlBar('class')+`<div class="g g4">${kpi('Стоимость портфеля',M(tot),'по текущим ценам')}${kpi('Сумма целей',`<span class="${!has?'mu':Math.abs(sumT-100)<0.05?'pos':'neg'}">${sumT.toFixed(1).replace('.',',')} %</span>`,!has?'введите целевые доли ниже':Math.abs(sumT-100)<0.05?'цели заданы':'расчёт нормирован к 100%')}
    ${kpi('Отклонение от целей',has?pctp(dev):'—','сколько % портфеля стоит «не там»',has&&dev>5?'neg':'')}${kpi('Без продаж нужно внести',has?M(need0):'—','чтобы выйти на цели одними покупками')}</div>
  <div class="card"><h2>Целевая структура по классам активов</h2>
    ${rebCtlBar(buyOnly)}
    <div class="scr-presets reb-pre noprint" style="margin-bottom:12px"><span class="mu" style="font-size:12.5px">Быстрые цели:</span>${[['6040','Акции 60 / Облигации 40'],['5050','50 / 50'],['8020','Акции 80 / Облигации 20'],['eq','Равные доли']].map(([k,t])=>`<button type="button" class="scr-chip" data-rbp="${k}">${t}</button>`).join('')}</div>
    <div class="tbl"><table><thead><tr><th class="l">Класс</th><th>Сейчас, ₽</th><th>Сейчас</th><th>Цель</th><th>Отклонение</th><th>Действие</th><th>После</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="row" style="margin-top:14px"><button class="btn" id="rb-s">Сохранить цели</button><button class="btn ghost" id="rb-r">Сбросить</button><span class="reb-sum" id="rb-sum"></span></div></div>
  ${rebTaxHtml(act,keys)}
  ${has?rebSnowballHtml(cur,keys,w,tot,dev):''}
  <p class="note">Расчёт по классам активов (акции, облигации, фонды, валюта…) на уровне портфеля, без учёта комиссий и лотности; налог при продаже оценивается отдельно (в режиме с продажами). Это справочный расчёт, а не инвестиционная рекомендация. Цели сохраняются локально.</p>`;
}
function bindReb(){
  const lv=$('#rb-lvl');
  if(lv)lv.onclick=e=>{const b=e.target.closest('[data-rl]');if(!b||b.dataset.rl===S.reb.lvl)return;S.reb.lvl=b.dataset.rl;lsSet('ta_reb_lvl',S.reb.lvl);render()};
  $('#view').querySelectorAll('[data-reb-scr]').forEach(b=>b.onclick=()=>{
    const spec=b.dataset.rebScr,amt=+b.dataset.amt||0;
    if(spec.startsWith('rt:')){
      const rt=spec.slice(3);
      rebGoScreener({rmin:rt==='AAA'?'AAA':rt==='AA'?'AA-':rt==='A'?'A-':rt==='BBB'?'BBB-':'',amt});
    }else rebGoScreener({rmin:'A-',amt});
  });
  const d=S.reb.draft;
  $('#view').querySelectorAll('.reb-in').forEach(i=>i.onchange=()=>{const v=parseFloat(String(i.value).replace(',','.'));if(v>0)d[i.dataset.k]=Math.min(100,v);else delete d[i.dataset.k];render()});
  $('#view').querySelectorAll('.reb-rt-in').forEach(i=>i.onchange=()=>{const v=parseFloat(String(i.value).replace(',','.'));if(v>0)S.reb.rtDraft[i.dataset.k]=Math.min(100,v);else delete S.reb.rtDraft[i.dataset.k];lsSet('ta_reb_rt',JSON.stringify(S.reb.rtDraft));render()});
  $('#view').querySelectorAll('.reb-sec-in').forEach(i=>i.onchange=()=>{const v=parseFloat(String(i.value).replace(',','.'));if(v>0)S.reb.secDraft[i.dataset.k]=Math.min(100,v);else delete S.reb.secDraft[i.dataset.k];lsSet('ta_reb_sec',JSON.stringify(S.reb.secDraft));render()});
  $('#view').querySelectorAll('[data-rtrp]').forEach(btn=>btn.onclick=()=>{
    const k=btn.dataset.rtrp;
    if(k==='cons')S.reb.rtDraft={AAA:40,AA:40,A:20};
    else if(k==='bal')S.reb.rtDraft={AAA:25,AA:35,A:30,BBB:10};
    else S.reb.rtDraft={AAA:25,AA:25,A:25,BBB:25};
    lsSet('ta_reb_rt',JSON.stringify(S.reb.rtDraft));render();
  });
  $('#view').querySelectorAll('[data-secp]').forEach(btn=>btn.onclick=()=>{
    const k=btn.dataset.secp,ps=(S.data.portfolio.positions||[]).filter(x=>x.type!=='currency'&&x.type!=='futures'&&(x.value_rub||0)>0);
    const tot=ps.reduce((a,x)=>a+(x.value_rub||0),0)||1,nd={};
    ps.forEach(x=>{const key=x.isin||x.ticker||x.uid||x.name;nd[key]=k==='cur'?Math.round((x.value_rub||0)/tot*1000)/10:Math.round(1000/ps.length)/10});
    S.reb.secDraft=nd;lsSet('ta_reb_sec',JSON.stringify(nd));render();
  });
  $('#view').querySelectorAll('[data-rbp]').forEach(btn=>btn.onclick=()=>{
    const k=btn.dataset.rbp,pr={'6040':[60,40],'5050':[50,50],'8020':[80,20]}[k];
    Object.keys(d).forEach(x=>delete d[x]);
    if(pr){d.share=pr[0];d.bond=pr[1]}
    else{const ks=[...$('#view').querySelectorAll('.reb-in')].map(i=>i.dataset.k).filter(x=>!['currency','other'].includes(x));const v=ks.length?Math.round(1000/ks.length)/10:0;ks.forEach(x=>d[x]=v)}
    render();
  });
  const rbc=$('#rb-c');if(rbc)rbc.onchange=e=>{S.reb.contrib=e.target.value;render()};
  const rm=$('#rb-m');if(rm)rm.onchange=e=>{S.reb.monthly=e.target.value;render()};
  const rbb=$('#rb-b');if(rbb)rbb.onchange=e=>{S.reb.buyOnly=e.target.checked;render()};
  const rbr=$('#rb-r');if(rbr)rbr.onclick=()=>{S.reb.draft=null;S.reb.contrib='';S.reb.monthly='';render()};
  const rbs=$('#rb-s');if(rbs)rbs.onclick=async e=>{e.currentTarget.disabled=true;try{await post('/api/config',{targets:d});S.cfg.targets=Object.assign({},d);$('#rb-sum').textContent='Сохранено'}catch(x){$('#rb-sum').textContent=x.message}finally{e.currentTarget.disabled=false}};
}
