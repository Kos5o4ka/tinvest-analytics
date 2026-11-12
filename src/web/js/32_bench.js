/* ── Сравнение с рынком: индексы облигаций, фонды ликвидности и облигационные БПИФ ── */
S.bn={};S.bnSel=new Set(['LQDT','RUCBTRNS']);S.bnLoad=null;
const BN_COL={RGBITR:[S2],RUCBTRNS:[S4],RUCBHYTR:[S8],LQDT:[S3],TMON:[S6],SBMM:[S7],AKMM:[S2,1],SBRB:[S4,1],AKMB:[S5,1],TBRU:[S7,1],RUSFAR:[S6,1]};
const BN_LC={d1:'#19a070',d5:'#e3a21a',dm:'#e66767',na:'#8a90a0'};
const bnRub=v=>bad(v)?'—':(v>0?'+':v<0?'−':'')+NF0.format(Math.abs(v))+' ₽';
const bnPct=(v,d=1)=>bad(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',')+' %';
const bnPp=(v,d=1)=>bad(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',')+' п.п.';
/* срок сравнения выбирается на самой странице; при смене общего периода в шапке возвращаемся к нему */
const BN_PER=[['1m','1 мес'],['3m','3 мес'],['6m','6 мес'],['12m','1 год'],['3y','3 года'],['ytd','С начала года'],['py','Прошлый год'],['all','Всё время']];
function bnPer(){if(S.bnPg!==S.period){S.bnP=null;S.bnPg=S.period}return S.bnP&&BN_PER.some(x=>x[0]===S.bnP)?S.bnP:S.period}
const bnPerName=()=>(BN_PER.find(x=>x[0]===bnPer())||['','за период'])[1].toLowerCase();
const bnPerLbl=()=>{const k=bnPer();return k==='ytd'||k==='py'||k==='all'?bnPerName():'за '+bnPerName()};
function bnPerSeg(){return`<div class="bn-per noprint"><span class="bn-gl">Срок сравнения</span><div class="seg" id="bn-per">${BN_PER.map(([k,t])=>`<button type="button" class="${k===bnPer()?'on':''}" data-p="${k}">${t}</button>`).join('')}</div></div>`}
function bnSpan(a,b){const dd=(new Date(b)-new Date(a))/864e5;if(dd<75)return Math.round(dd)+' дн.';if(dd<700)return Math.round(dd/30.4)+' мес';return(dd/365.25).toFixed(1).replace('.',',')+' г.'}
function bnKey(){return S.account+'|'+bnPer()}
function bnLoadData(){
  const key=bnKey();if(S.bnLoad===key)return;S.bnLoad=key;
  const p=new URLSearchParams({account:S.account,period:bnPer()});
  api('/api/bench?'+p).then(j=>{if(S.bnLoad===key)S.bnLoad=null;S.bn[key]={d:j,t:Date.now()};if(S.page==='bench'&&bnKey()===key)renderSoon()})
   .catch(e=>{if(S.bnLoad===key)S.bnLoad=null;S.bn[key]={d:{error:e.message},t:Date.now(),fail:1};if(S.page==='bench'&&bnKey()===key)renderSoon()});
}
function bnCur(){const e=S.bn[bnKey()];return e&&Date.now()-e.t<10*60*1000?e:null}
function bnSeries(d){
  const s=d.series,ser=[{n:'Мой портфель',c:S1,hex:'#3987e5',v:s.portfolio,w:2.6}];
  d.bench.forEach(b=>{if(!b.available||!S.bnSel.has(b.code)||!s.bench[b.code])return;const c=BN_COL[b.code]||[S2];
    ser.push({n:b.name,c:c[0],v:s.bench[b.code],w:1.7,dash:!!c[1]})});
  return ser;
}
function bnChart(el){
  const d=bnCur();if(!d||d.d.error)return;const s=d.d.series,short_=d.d.years<0.6;
  const labs=s.dates.map(x=>{if(short_)return ddm(x).slice(0,5);const[y,m]=x.split('-');return MON[+m-1]+' '+y.slice(2)});
  const fp=v=>(Math.round(v*10)/10).toString().replace('.',',')+'%';
  line(el,{h:320,labels:labs,tipLabels:s.dates.map(dlabel),series:bnSeries(d.d),fa:fp,ft:v=>bnPct(v,2),zero:false});
}
function bnChips(d){
  const by={};d.bench.forEach(b=>{(by[b.group]=by[b.group]||[]).push(b)});
  return d.groups.filter(g=>by[g]).map(g=>`<div class="bn-grp"><span class="bn-gl">${esc(g)}</span><div class="bn-chips">${by[g].map(b=>{
    const c=(BN_COL[b.code]||[S2])[0];
    return b.available?`<button type="button" data-c="${b.code}" class="${S.bnSel.has(b.code)?'on':''}" title="${esc(b.note)}"><i style="background:${c}"></i>${esc(b.name)}</button>`
      :`<button type="button" disabled title="${esc(b.reason||'нет данных')}"><i style="background:${c}"></i>${esc(b.name)} · нет данных</button>`}).join('')}</div></div>`).join('');
}
/* окраска ячейки бенчмарка относительно портфеля: красный — бенчмарк в этом лучше вас, зелёный — хуже */
function bnCmp(b,p,hi){if(bad(b)||bad(p)||Math.abs(b-p)<1e-9)return'';return(hi?b>p:b<p)?'neg':'pos'}
function bnTable(d){
  const p=d.portfolio,f1=(v,s='')=>bad(v)?'—':v.toFixed(1).replace('.',',')+s;
  const row=(b,isP)=>{
    const sm=b.same;
    return`<tr${isP?' class="bn-me"':''}><td class="l">${isP?'<b>Мой портфель</b>':`<b>${esc(b.name)}</b>${b.partial?`<br><small class="mu">данные с ${ddm(b.start)}</small>`:''}`}</td>
      <td class="num mu">${bnSpan(isP?d.start:b.start,d.end)}</td>
      <td class="num ${isP?cls(b.ret):bnCmp(b.ret,p.ret,true)}">${bnPct(b.ret)}</td>
      <td class="num ${isP?'':bnCmp(b.ann,p.ann,true)}">${b.ann==null?'<span class="mu">—</span>':bnPct(b.ann)}</td>
      <td class="num ${isP?'':bnCmp(b.vol,p.vol,false)}">${f1(b.vol,' %')}</td>
      <td class="num ${isP?'':bnCmp(b.maxdd,p.maxdd,true)}">${f1(b.maxdd,' %')}</td>
      <td class="num ${isP?'':bnCmp(b.sharpe,p.sharpe,true)}">${bad(b.sharpe)?'—':f2(b.sharpe)}</td>
      <td class="num">${isP?'1,00':bad(b.beta)?'—':f2(b.beta)}</td><td class="num">${isP?'1,00':bad(b.corr)?'—':f2(b.corr)}</td>
      <td class="num">${isP?M(b.value_end,'rub',0):sm?M(sm.final,'rub',0):'—'}</td>
      <td class="num ${isP?'':sm?cls(sm.diff):''}">${isP?'—':sm?bnRub(sm.diff):'—'}</td></tr>`};
  const by={};d.bench.filter(b=>b.available).forEach(b=>{(by[b.group]=by[b.group]||[]).push(b)});
  let h=row(p,true);
  d.groups.filter(g=>by[g]).forEach(g=>{h+=`<tr class="bn-gr"><td class="l" colspan="11">${esc(g)}</td></tr>`+by[g].map(b=>row(b,false)).join('')});
  return`<div class="tbl"><table class="bn-t"><thead><tr><th class="l">Что сравниваем</th><th>Срок</th><th>Доходность ${bnPerLbl()}</th><th>В пересчёте на год</th><th>Колебания цены за год</th><th>Макс. просадка</th><th>Шарп</th><th>Бета к портфелю</th><th>Корреляция</th><th>Было бы с теми же деньгами</th><th>Вы заработали больше (меньше)</th></tr></thead><tbody>${h}</tbody></table></div>`;
}
function bnLiquidity(d){
  const l=d.liquidity;
  if(!l)return`<div class="card"><h2>Как быстро можно продать</h2><div class="empty" style="padding:24px">Данные о ликвидности недоступны</div></div>`;
  if(!l.bonds_count)return`<div class="card"><h2>Как быстро можно продать</h2><div class="empty" style="padding:24px">В портфеле нет облигаций для оценки ликвидности</div></div>`;
  const items=l.buckets.map(b=>({n:b.label,v:b.share||0,c:BN_LC[b.key],s:`${b.count} шт · ${M(b.value,'rub',0)}`,raw:b}));
  const cov=l.portfolio_value?l.bonds_value/l.portfolio_value*100:null;
  const slow=l.slowest.length?`<div class="tbl" style="margin-top:10px"><table><thead><tr><th class="l">Самые медленные позиции</th><th>Стоимость</th><th>Дней на продажу</th></tr></thead><tbody>${
    l.slowest.map(r=>`<tr${r.isin?` data-isin="${esc(r.isin)}"`:''}><td class="l">${esc(r.name)}</td><td class="num">${M(r.value_rub,'rub',0)}</td><td class="num ${r.days>5?'neg':r.days>1?'':'pos'}">${r.days>=10?Math.round(r.days):f2(r.days)}</td></tr>`).join('')}</tbody></table></div>`:'';
  return`<div class="card"><h2>Как быстро можно продать<span class="sp">облигации в портфеле${cov!=null?', '+cov.toFixed(0)+' % портфеля':''}</span></h2>
    ${hbars(items,'#3987e5',x=>pctp(x.v,0),true)}
    ${slow}
    <p class="note" style="margin-top:10px">«Дней на продажу» — за сколько дней можно продать позицию целиком, если забирать не более ${f2(l.part)} % среднего дневного оборота выпуска, чтобы не двигать цену. Фонд ликвидности (LQDT) продаётся в день сделки, без скидки к цене. Оценка по облигациям; акции и фонды в расчёт не входят.</p></div>`;
}
function bnPremium(d){
  const p=d.premium;
  if(!p)return`<div class="card"><h2>Плата за риск</h2><div class="empty" style="padding:24px">Данные об облигациях недоступны</div></div>`;
  if(p.lqdt==null)return`<div class="card"><h2>Плата за риск</h2><div class="empty" style="padding:24px">Доходность фонда ликвидности сейчас недоступна</div></div>`;
  const pr=(t,v,c,s)=>`<div class="bn-pr"><span>${t}${s?`<small class="mu">${s}</small>`:''}</span><b class="num ${c||''}">${v}</b></div>`;
  const hy=p.high_yield_value>0?`<br>В расчёт «без экстремальных» не вошли выпуски с доходностью выше 100 % (${M(p.high_yield_value,'rub',0)}): это почти всегда признак серьёзных проблем эмитента.`:'';
  const below=p.below&&p.below.length?`<div class="tbl" style="margin-top:10px"><table><thead><tr><th class="l">Облигации с доходностью ниже фонда ликвидности</th><th>Доходность</th><th>Разница</th><th>Стоимость</th></tr></thead><tbody>${
    p.below.map(r=>`<tr${r.isin?` data-isin="${esc(r.isin)}"`:''}><td class="l">${esc(r.name)}</td><td class="num">${pctp(r.ytm,1)}</td><td class="num neg">${bnPp(r.diff)}</td><td class="num">${M(r.value_rub,'rub',0)}</td></tr>`).join('')}</tbody></table></div>
    <p class="note" style="margin-top:8px">Это ${p.below_count} из ${p.count} облигаций (${M(p.below_value,'rub',0)}). За меньшую доходность вы берёте больший риск и теряете в ликвидности: такие бумаги стоит держать только по особой причине (срок, налог, оферта).</p>`
    :'<p class="note" style="margin-top:10px;color:var(--pos)">Все облигации портфеля обещают доходность выше фонда ликвидности.</p>';
  const mainP=p.prem_ytm_ex!=null?p.prem_ytm_ex:p.prem_ytm;
  return`<div class="card"><h2>Плата за риск<span class="sp">доходность облигаций против фонда ликвидности</span></h2>
    ${pr('Фонд ликвидности LQDT',pctp(p.lqdt,1),'','по росту пая за 30 дней, в пересчёте на год')}
    ${pr('Ваши облигации — доходность к погашению',p.ytm_ex!=null?pctp(p.ytm_ex,1):'—','','средневзвешенная, без выпусков выше 100 %')}
    ${pr('Облигации портфеля — единая доходность (IRR)',p.irr!=null?pctp(p.irr,1):'—','','все будущие выплаты против стоимости сегодня')}
    ${pr('Премия за риск',mainP!=null?bnPp(mainP):'—',mainP!=null?cls(mainP):'','на сколько облигации обещают больше LQDT')}
    ${below}
    <p class="note" style="margin-top:10px">Доходность облигаций — обещанная при условии, что эмитент всё выплатит; она до налогов и не учитывает риск дефолта. Если премия мала, а риск высок, вы почти ничего не получаете сверх безрискового варианта.${hy}</p></div>`;
}
function pBench(){
  const e=bnCur();
  if(!e){bnLoadData();return`<div class="card">${bnPerSeg()}${waitBox('Сравниваю портфель с индексами и фондами Мосбиржи. Первый раз это может занять несколько минут (загружается история цен и оценивается ликвидность), потом данные берутся из локального кэша…')}</div>`}
  const d=e.d;
  if(d.error)return bnPerSeg()+`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="bn-retry">Повторить</button></div>`;
  const p=d.portfolio,B=c=>d.bench.find(b=>b.code===c&&b.available),lq=B('LQDT'),cb=B('RUCBTRNS');
  const l=d.liquidity,fast=l&&l.bonds_count?(l.buckets.find(b=>b.key==='d1')||{}).share:null;
  const pr=d.premium,prem=pr&&pr.lqdt!=null?(pr.prem_ytm_ex!=null?pr.prem_ytm_ex:pr.prem_ytm):null;
  const sm=lq&&lq.same;
  chart('bn-chart',bnChart);
  const kp=`<div class="g g6">
    ${kpi('Ваша доходность '+bnPerLbl(),bnPct(p.ret,2),`LQDT: ${lq?bnPct(lq.ret,1):'—'} · корп. облигации: ${cb?bnPct(cb.ret,1):'—'}`,cls(p.ret),S1)}
    ${kpi('Те же деньги в LQDT',sm?bnRub(sm.diff):'—',sm?(sm.diff>=0?'вы заработали больше, чем дал бы фонд ликвидности':'фонд ликвидности дал бы больше, чем вы заработали'):'нет данных по LQDT',sm?cls(sm.diff):'',S3)}
    ${kpi('Доходность в годовых (XIRR)',p.xirr==null?'—':bnPct(p.xirr,1),p.xirr==null?'период короче 3 месяцев':`LQDT с теми же вложениями: ${sm&&sm.xirr!=null?bnPct(sm.xirr,1):'—'}`,cls(p.xirr),S7)}
    ${kpi('Коэффициент Шарпа',bad(p.sharpe)?'—':f2(p.sharpe),'доходность сверх безрисковой ставки на единицу риска',p.sharpe>0?'pos':p.sharpe<0?'neg':'',S2)}
    ${kpi('Продаётся за 1 день',fast==null?'—':pctp(fast,0),'доля облигаций, которую можно продать за день',fast!=null&&fast<70?'neg':'',S5)}
    ${kpi('Премия к LQDT',prem==null?'—':bnPp(prem),pr&&pr.lqdt!=null?`LQDT даёт ≈ ${pctp(pr.lqdt,1)} годовых`:'доходность LQDT недоступна',prem==null?'':cls(prem),S4)}</div>`;
  const notes=(d.notes||[]).length?`<div class="msg info" style="margin:0 0 12px">${d.notes.map(esc).join('<br>')}</div>`:'';
  return bnPerSeg()+kp+notes+`<div class="card"><h2>Накопленная доходность ${bnPerLbl()}<span class="sp">${ddm(d.start)} — ${ddm(d.end)}</span></h2>
    <div class="bn-sel" id="bn-sel">${bnChips(d)}</div><div id="bn-chart" class="chart"></div>
    <p class="note" style="margin-top:8px">Показано, на сколько процентов выросли вложения с начала периода. Линия портфеля — по методу TWR: пополнения и выводы не искажают результат.</p></div>
  <div class="card"><h2>Сравнение по показателям ${bnPerLbl()}<span class="sp">красным выделено то, в чём бенчмарк лучше вашего портфеля, зелёным — где хуже</span></h2>${bnTable(d)}
    <p class="note" style="margin-top:10px">«Колебания цены» — насколько сильно портфель «качается» (годовое стандартное отклонение дневных изменений по торговым дням Мосбиржи). «Макс. просадка» — самое большое падение от пика до дна. «Шарп» — доходность сверх ставки RUSFAR (безрисковая ставка межбанка) на единицу колебаний; для фондов ликвидности он малоинформативен, потому что колебаний почти нет, а для периода короче нескольких месяцев — шумный. «Бета» показывает, на сколько процентов в среднем меняется ваш портфель при изменении бенчмарка на 1 %, «корреляция» — насколько они движутся вместе (от −1 до 1). «Было бы с теми же деньгами» — во что превратились бы стоимость портфеля на начало периода и все ваши пополнения и выводы, если бы в те же дни их вложили в этот бенчмарк.</p></div>
  <div class="g g2 bn-g">${bnLiquidity(d)}${bnPremium(d)}</div>
  <div class="card"><h2>Как читать этот раздел</h2><div class="note bn-expl">
    <p><b>Почему сравнение «те же деньги» честнее.</b> Доходность TWR показывает, насколько хорошо работали сами активы, и не зависит от того, когда вы пополняли счёт. Но вам важнее другое: заработали ли вы больше, чем если бы в те же дни положили те же суммы в фонд ликвидности или индекс. Сравнение «те же деньги» отвечает именно на этот вопрос, а итог показан в рублях.</p>
    <p><b>Комиссии и налоги.</b> Комиссии управляющих фондов уже учтены в цене пая: отдельно их вычитать не нужно. Налоги не учтены ни у портфеля, ни у бенчмарков. У фондов налог платится только при продаже пая, а после 3 лет владения может действовать льгота долгосрочного владения (ЛДВ). Купоны облигаций облагаются налогом сразу.</p>
    <p><b>Что за индексы.</b> Индексы полной доходности учитывают купоны и потому сопоставимы с портфелем. Индекс ВДО — облигации небольших компаний с повышенным риском (высокодоходные облигации): они платят больше, но дефолты и резкие просадки там заметно чаще. Облигационные фонды из списка не выплачивают доход пайщикам, он остаётся в цене пая, поэтому их цена честно отражает доходность. Фонды ликвидности вкладывают деньги в короткие сделки РЕПО, их доходность близка к ключевой ставке.</p>
    <p>Прошлая доходность не гарантирует будущую. Раздел носит справочный характер и не является инвестиционной рекомендацией. Данные индексов и фондов — Московская биржа (ISS), с задержкой в один день.</p></div></div>`;
}
function bindBench(){
  const r=$('#bn-retry');if(r)r.onclick=()=>{delete S.bn[bnKey()];S.bnLoad=null;render()};
  const per=$('#bn-per');
  if(per)per.onclick=e=>{const b=e.target.closest('button[data-p]');if(!b||b.dataset.p===bnPer())return;S.bnP=b.dataset.p;S.bnPg=S.period;render()};
  const sel=$('#bn-sel');
  if(sel)sel.onclick=e=>{const b=e.target.closest('button[data-c]');if(!b||b.disabled)return;const c=b.dataset.c;
    if(S.bnSel.has(c))S.bnSel.delete(c);else S.bnSel.add(c);b.classList.toggle('on',S.bnSel.has(c));const el=$('#bn-chart');if(el)bnChart(el)};
}
