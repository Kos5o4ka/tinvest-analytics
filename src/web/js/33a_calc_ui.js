/* калькулятор инвестиций: интерфейс */
/* ── Интерфейс ── */
const CL_DEF={start:500000,monthly:20000,idx:5,years:10,strat:{dep:1,fund:1,ofz:1,aa:1,a:1},ownRate:15,reinvest:true,freq:4,lot:1000,lotFund:'fund',scn:'cbr',ownKey:12,
  acct:'plain',reinvDed:true,ldv:true,defaults:true,real:true,depSpread:1.5,goalMode:'contrib',goalStrat:'ofz',adv:false,view:'',iisYear:new Date().getFullYear(),salRate:13,salary:0,
  mixStk:50,mixBond:'ofz',stkGrow:'',stkDiv:'',fxWeak:''};
let CL_F=null;
function clLoadF(){
  if(CL_F)return CL_F;
  const F=JSON.parse(JSON.stringify(CL_DEF));
  try{const s=JSON.parse(localStorage.getItem('ta_calc')||'null');
    if(s&&typeof s==='object')for(const k in F){if(s[k]!==undefined&&typeof s[k]===typeof F[k])F[k]=k==='strat'?Object.assign({},s[k]):s[k]}}catch(e){}
  if(F.acct==='iisA'||F.acct==='iisB')F.acct='iis3';
  return CL_F=F;
}
function clSave(){try{localStorage.setItem('ta_calc',JSON.stringify(CL_F))}catch(e){}}
function clLoad(){
  if(S._calcLoading)return;S._calcLoading=1;const acc=S.account;
  api('/api/calc?account='+encodeURIComponent(acc)).then(j=>{S._calcLoading=0;S.calcP=j&&!j.error&&j.key_rate?j:null;S.calcErr=S.calcP?null:((j&&j.error)||'нет данных');S.calcAcc=acc;if(S.page==='calc')renderSoon()})
   .catch(e=>{S._calcLoading=0;S.calcP=null;S.calcErr=e.message;S.calcAcc=acc;if(S.page==='calc')renderSoon()});
}
const clYM=(m)=>{const y=Math.floor(m/12),mm=m%12;return(y?y+' '+(y%10===1&&y!==11?'год':y%10>=2&&y%10<=4&&(y<10||y>20)?'года':'лет'):'')+(y&&mm?' ':'')+(mm?mm+' мес.':'')||'0 мес.'};
const clRub=v=>M(v,'rub',0);
const clMkt=()=>(S.calcAcc===S.account&&S.calcP)||clDefaultParams();
function clAvail(P){return CL_STR.filter(s=>(s[0]!=='pf'||(P.portfolio&&P.portfolio.irr!=null))&&!['flt','stk','fxb','mix'].includes(s[0]))}
function clRun(F,P){
  const env=clEnv(P,F),p=clParams(F),N=p.months,ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  const res=ids.map(id=>{const s=CL_STR.find(x=>x[0]===id),r=clSim(id,p,P,env,F);r.id=id;r.name=s[1];r.color=s[2];return r});
  return{env,p,N,res};
}
/* график с накоплением: слои складываются снизу вверх */
function clStack(el,o){
  const W=el.clientWidth,H=o.h||280,pl=62,pr=10,pt=10,pb=26,ser=o.series,n=o.labels.length,tl=o.tipLabels||o.labels;
  if(n<2||W<50)return emptyChart(el,H,o.empty);
  const fa=o.fa||short,ft=o.ft||(v=>M(v)),cum=[];let acc=new Array(n).fill(0),mn=0,mx=0;
  ser.forEach(se=>{const hi=acc.map((a,i)=>a+(se.v[i]||0));cum.push([acc,hi]);acc=hi;hi.forEach(v=>{mn=Math.min(mn,v);mx=Math.max(mx,v)})});
  if(mx===mn)return emptyChart(el,H,o.empty);
  const{lo,hi,step}=nice(mn,mx),pw=W-pl-pr,ph=H-pt-pb,X=i=>pl+i/(n-1)*pw,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph,pt2=(v,i)=>X(i).toFixed(1)+','+Y(v).toFixed(1);
  let s='';
  for(let v=lo;v<=hi+step/2;v+=step){const y=Y(v);s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}"/><text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${fa(Math.abs(v)<step/1e6?0:v)}</text>`}
  axisTicks(o.labels,X,pl-4,W-pr+4).forEach(([i,x])=>s+=`<text class="ax" x="${x}" y="${H-6}" text-anchor="middle">${esc(o.labels[i])}</text>`);
  cum.forEach(([a,b],j)=>{const up=b.map(pt2);
    s+=`<polygon points="${up.concat(a.map(pt2).reverse()).join(' ')}" fill="${ser[j].c}" fill-opacity=".38"/><polyline points="${up.join(' ')}" fill="none" stroke="${ser[j].c}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`});
  let hits='';const cw=pw/(n-1);
  for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${X(i)-cw/2}" y="${pt}" width="${cw}" height="${ph}" fill="transparent"/>`;
  el.innerHTML=legend(ser)+`<svg width="${W}" height="${H}">${s}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{if(i<0){hv.innerHTML='';return}hv.innerHTML=`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph}" stroke="var(--line2)" stroke-dasharray="3 3"/>`+
    cum.map(([a,b],j)=>`<circle cx="${X(i)}" cy="${Y(b[i])}" r="4" fill="${ser[j].c}" stroke="var(--card)" stroke-width="2"/>`).join('')};
  bindTip(el,i=>`<b>${esc(tl[i])}</b>`+ser.slice().reverse().map(se=>tipRow(se.c,se.n,ft(se.v[i]||0))).join('')+
    `<div class="tot">Итого<span>${ft(acc[i])}</span></div>`);
}
function clSegTable(P,F,env){
  const rows=[];
  rows.push(['Ключевая ставка сейчас',pctp(P.key_rate.current,2),P.key_rate.estimate?'оценка':P.key_rate.source]);
  const at=k=>pctp(env.key(k),1);
  rows.push(['Ключевая через 1 / 2 / 3 года (выбранный сценарий)',at(12)+' / '+at(24)+' / '+at(36),'']);
  rows.push(['Инфляция (по годам)',(P.inflation.yearly&&P.inflation.yearly.length?P.inflation.yearly.map(y=>y.year+': '+pctp(y.mid,1)).join('; '):pctp(P.inflation.default,1)+' в год'),P.inflation.estimate?'оценка':'прогноз Банка России']);
  rows.push(['Вклад: ставка',pctp(env.depRate(0),2),'ключевая − '+f2(F.depSpread)+' п.п.']);
  rows.push(['Фонд ликвидности: доходность',pctp(env.fundRate(0),2),P.lqdt.estimate?'оценка: ключевая − '+f2(P.lqdt.spread)+' п.п.':'по данным фонда']);
  ['ofz','aaa','aa','a','hy'].forEach(id=>{const s=P.segments[id];if(!s)return;
    rows.push([s.name+': доходность / срок',pctp(s.yield,2)+' / '+f2(s.dur)+' г.','потери от дефолтов '+f2(s.loss)+' % в год'+(s.estimate?' · оценка':'')])});
  if(P.portfolio&&P.portfolio.irr!=null)rows.push(['Мой портфель: доходность облигаций',pctp(P.portfolio.irr,2),'IRR по потокам облигаций']);
  const sh=P.portfolio&&P.portfolio.shares;
  if(sh){const nm={bonds:'облигации',stocks:'акции',funds:'прочие фонды',lqdt:'фонды ликвидности',cash:'деньги',other:'прочее'};
    rows.push(['Мой портфель: структура',Object.keys(nm).filter(k=>sh[k]>0).map(k=>nm[k]+' '+pctp(sh[k]*100,0)).join(', '),P.portfolio.dur_bonds?'дюрация облигаций '+f2(P.portfolio.dur_bonds)+' г.':'считается как смесь частей'])}
  return`<div class="tbl"><table><thead><tr><th class="l">Параметр</th><th>Значение</th><th class="l">Источник / примечание</th></tr></thead><tbody>${
    rows.map(r=>`<tr><td class="l">${r[0]}</td><td class="num">${r[1]}</td><td class="l mu">${r[2]}</td></tr>`).join('')}</tbody></table></div>`;
}
function clOut(){
  const F=clLoadF(),P=clMkt();
  const ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  if(!ids.length)return`<div class="card empty">Выберите хотя бы одну стратегию для сравнения</div>`;
  const run=clRun(F,P),{env,N,res,p}=run,real=F.real,dv=k=>real?env.D[k]:1,mode=real?'в сегодняшних деньгах':'в номинальных рублях';
  const labels=[],tips=[];
  for(let k=0;k<=N;k++){const d=new Date(env.y0,env.m0+k,1),mm=String(d.getMonth()+1).padStart(2,'0');labels.push(mm+'.'+d.getFullYear());tips.push(mm+'.'+d.getFullYear()+' · '+(k?clYM(k):'сейчас'))}
  const best=res.slice().sort((a,b)=>b.finalReal-a.finalReal)[0],cur=res.find(r=>r.id===F.view)||best,defl=env.D[N];
  /* состав капитала выбранной стратегии: внесено + вычеты ИИС + доход после налогов */
  const RF=cur.id==='dep'?null:cur.RF,sIn=[],sDed=[],sInc=[];let ci=0,cd=0;
  for(let k=0;k<=N;k++){ci+=clContrib(p,k)/dv(k);if(RF)cd+=RF[k]/dv(k);sIn.push(ci);sDed.push(cd);sInc.push(cur.cap[k]/dv(k)-ci-cd)}
  const ser=[{n:'Внесено',c:'#8a93a6',v:sIn}];if(cd>0)ser.push({n:'Вычеты и возвраты ИИС',c:'var(--s4)',v:sDed});ser.push({n:'Доход после налогов',c:'var(--s3)',v:sInc});
  chart('cl-stack',clStack,{h:300,series:ser,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных'});
  const fin=real?cur.finalReal:cur.final,inc=sInc[N],pas=real?cur.passiveReal:cur.passive;
  const pick=res.length>1?`<div class="cl-view"><span>Итоги и график для</span><select class="in" id="cl-view"><option value="">лучшей стратегии (${esc(best.name)})</option>${
    res.map(r=>`<option value="${r.id}" ${r.id===F.view?'selected':''}>${esc(r.name)}</option>`).join('')}</select></div>`:'';
  const kp=`${pick}<div class="g g4">${kpi('Итоговый капитал',clRub(fin),esc(cur.name)+' · '+(real?'в сегодняшних деньгах':'номинал'),'pos',S3)}
    ${kpi('Чистый доход',clRub(inc),'после налогов, сверх внесённого'+(cd>0?' и вычетов':''),cls(inc),S1)}
    ${kpi('Уплачено налогов',clRub(cur.taxes),'НДФЛ за '+clYM(N)+', номинал',null,S8)}
    ${kpi('Пассивный доход в месяц',clRub(pas),'после налога, '+(real?'в сегодняшних деньгах':'номинал'),null,S4)}</div>`;
  const stk=`<div class="card"><h2>Из чего состоит капитал<span class="sp">${esc(cur.name)} · ${mode}</span></h2><div id="cl-stack" class="chart"></div>
    <div class="note" style="margin-top:10px">Цены за ${clYM(N)} вырастут в ×${f2(defl)} по прогнозу инфляции: 1 ₽ в конце срока ≈ ${f2(1/defl)} ₽ сегодня.${real?' Взносы, вычеты и доход пересчитаны в сегодняшние деньги на дату поступления.':''}</div></div>`;
  const th=['Стратегия','Итоговый капитал','Внесено','Получено дохода','Уплачено налогов','Вычеты и возвраты ИИС','Капитал в сегодняшних деньгах','Пассивный доход в месяц (после налога)','Эффективная годовая доходность'].concat(F.defaults?['Медиана с дефолтами и шоками ставки']:[]);
  const rows=res.map(r=>`<tr data-s="${r.id}" class="${r===cur?'cl-cur':''}"><td class="l"><i class="cl-dot" style="background:${r.color}"></i>${esc(r.name)}${r===best?' <small class="mu">лучшая</small>':''}</td><td class="num"><b>${clRub(r.final)}</b></td><td class="num">${clRub(r.deposited)}</td>
    <td class="num ${cls(r.income)}">${clRub(r.income)}</td><td class="num">${clRub(r.taxes)}</td><td class="num">${r.deductions>0?clRub(r.deductions):'—'}</td><td class="num"><b>${clRub(r.finalReal)}</b></td>
    <td class="num">${clRub(r.passive)}<br><small class="mu">${clRub(r.passiveReal)} сегодня</small></td><td class="num">${r.xirr==null?'—':pctp(r.xirr,1)}</td>${F.defaults?`<td class="num" data-mc="${r.id}"><small class="mu">считаю…</small></td>`:''}</tr>`).join('');
  const warn=[];
  if(F.acct!=='plain'){
    const ai=clAccInfo(p);
    if(res.some(r=>r.id==='dep'))warn.push('Вклад лежит в банке, а не на ИИС: вычет и льготы ИИС к нему не применяются, налог считается как на обычном счёте.');
    if(F.acct==='iis3'&&!ai.exempt)warn.push('ИИС-3, год открытия '+ai.openYear+': минимальный срок '+ai.term+' лет, а к концу расчёта счёт будет открыт '+clYM(ai.own)+'. При закрытии раньше срока полученные вычеты возвращаются, а весь доход облагается налогом.');
    if(F.acct==='iis3'&&ai.exempt)warn.push('ИИС-3, год открытия '+ai.openYear+': минимальный срок '+ai.term+' лет выдержан; доход освобождён от налога до 30 млн ₽ за всё время, вычет — '+f2(ai.rate*100)+' % от взносов до 400 тыс. ₽ в год'+(F.salary>0?' (не больше уплаченного НДФЛ с дохода '+clRub(F.salary)+' в год)':'')+'.');
    if(F.acct==='iis3'&&!(ai.rate>0))warn.push('Ставка НДФЛ с зарплаты не указана: вычет не начисляется (ИП и самозанятые без НДФЛ с зарплаты его не получают).');
  }
  if(F.acct==='plain'&&res.some(r=>r.id==='fund')&&F.ldv)warn.push('ЛДВ для фонда ликвидности: рост пая без налога при владении 3 года и более, лимит 3 млн ₽ × число лет. Каждое пополнение учитывается отдельно по сроку владения.');
  if(P.portfolio==null&&F.strat.pf)warn.push('Нет данных о портфеле — «Мой портфель» недоступен.');
  const wn=warn.length?`<div class="note" style="margin-top:12px">${warn.map(w=>'• '+esc(w)).join('<br>')}</div>`:'';
  const tbl=`<div class="card"><h2>Сравнение стратегий<span class="sp">через ${clYM(N)}</span></h2><div class="tbl cl-tbl"><table><thead><tr>${th.map((t,i)=>`<th class="${i?'':'l'}">${t}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="note" style="margin-top:10px">«Итоговый капитал» — если закрыть позиции и вывести деньги в конце срока: за вычетом всех налогов, включая налог последнего года, налог при закрытии ИИС и (для фонда ликвидности) налог при продаже. «Эффективная годовая доходность» — XIRR взносов против итога (номинальная, без учёта инфляции). «Получено дохода» = итог − внесено − вычеты.${res.length>1?' Нажмите на строку, чтобы показать стратегию в итогах и на графике.':''}${F.defaults?' Основной расчёт — без случайных событий; последний столбец — медиана 100 случайных траекторий с дефолтами по выпускам (редкие события, а не равномерная усушка) и шоками ключевой ставки.':''}</div>${wn}</div>`;
  let cmp='';
  if(res.length>1){
    const cdl=[];let a=0;for(let k=0;k<=N;k++){a+=clContrib(p,k)/dv(k);cdl.push(a)}
    const series=res.map(r=>({n:r.name,c:r.color,v:r.cap.map((v,k)=>v/dv(k))}));
    series.push({n:'Внесено своих денег',c:'#9aa3b5',dash:1,w:1.6,v:cdl});
    chart('cl-chart',line,{h:300,series,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных'});
    cmp=`<div class="card"><h2>Рост капитала по стратегиям<span class="sp">${mode}</span></h2><div id="cl-chart" class="chart"></div></div>`;
  }
  return`${kp}${stk}${tbl}${cmp}<div class="card"><h2>Что заложено в расчёт</h2>${clSegTable(P,F,env)}</div>`;
}
function clAdvSum(F){
  const a=(CL_ACC.find(x=>x[0]===F.acct)||CL_ACC[0])[1].replace(/ \(.*\)$/,'');
  const k={cbr:'ставка по прогнозу ЦБ',hard:'жёсткий сценарий ставки',soft:'мягкий сценарий ставки',own:'ключевая '+f2(F.ownKey)+' %'}[F.scn]||'';
  return[a,k,F.real?'в сегодняшних деньгах':'в номинале'].join(' · ');
}
function pCalcInv(){
  const F=clLoadF();
  const ld=S.calcAcc!==S.account;if(ld)clLoad();
  const P=(!ld&&S.calcP)||clDefaultParams(),pf=P.portfolio,fb=!ld&&!S.calcP;
  const num=(id,l,v,o)=>`<label class="field"><span>${l}</span><input class="in" id="cl-${id}" type="number" inputmode="decimal" value="${esc(v)}" ${o||''}></label>`;
  const sw=(id,t,sm,on)=>`<label class="sw"><input type="checkbox" id="cl-${id}" ${on?'checked':''}><i></i><div><b>${t}</b><small>${sm}</small></div></label>`;
  const sel=(id,l,opts,v)=>`<label class="field"><span>${l}</span><select class="in" id="cl-${id}">${opts.map(o=>`<option value="${o[0]}" ${String(o[0])===String(v)?'selected':''}>${o[1]}</option>`).join('')}</select></label>`;
  const seg=(id,opts,v)=>`<div class="seg" id="cl-${id}">${opts.map(o=>`<button data-v="${o[0]}" class="${String(o[0])===String(v)?'on':''}">${o[1]}</button>`).join('')}</div>`;
  const chips=clAvail(P).map(s=>`<label class="cl-chip"><input type="checkbox" data-s="${s[0]}" ${F.strat[s[0]]?'checked':''}><span><i style="background:${s[2]}"></i>${s[1]}</span></label>`).join('');
  return`${ld?`<div class="card">${waitBox('Загружаю параметры рынка (ставки, доходности, ваш портфель)… пока расчёт идёт на значениях по умолчанию')}</div>`:''}${fb?`<div class="msg err">Не удалось загрузить рыночные данные (${esc(S.calcErr||'нет ответа')}). Использованы значения по умолчанию, расчёт приблизителен.</div>`:''}
  <div class="card"><h2>Параметры<span class="sp">пересчёт мгновенный</span></h2>
   <div class="cl-pre" id="cl-pre"><span class="mu">Быстрые сценарии:</span>
    <button class="btn ghost" data-clp="cushion">Подушка 1 год</button>
    <button class="btn ghost" data-clp="passive50">Пассивный доход 50 тыс/мес</button>
    <button class="btn ghost" data-clp="goal5">Цель через 5 лет (ИИС-3)</button></div>
   <div id="cl-form">
   <div class="cl-grid cl-base">${num('start','Стартовый капитал, ₽',F.start,'min="0" step="10000"')}${num('monthly','Пополнение в месяц, ₽',F.monthly,'min="0" step="1000"')}
    <label class="field"><span>Срок: <b id="cl-yv">${F.years}</b> лет</span><input id="cl-years" type="range" min="1" max="30" step="1" value="${F.years}"></label></div>
   ${pf&&pf.value!=null?`<div class="cl-row"><button class="btn ghost" id="cl-pf">Подставить мой портфель</button><span class="note">старт ${clRub(pf.value)}${pf.monthly!=null?`, пополнение ${clRub(pf.monthly)} в месяц (среднее за 12 мес.)`:''}</span></div>`:''}
   <div class="cl-sec">Во что вкладываем</div><div class="cl-chips" id="cl-strat">${chips}</div>
   <div class="cl-grid" id="cl-ownbox" style="margin-top:12px;${F.strat.own?'':'display:none'}">${num('ownRate','Своя ставка, % годовых',F.ownRate,'step="0.5" min="0" max="100"')}</div>
   <details class="cl-adv" id="cl-adv" ${F.adv?'open':''}><summary>Дополнительные параметры<span id="cl-advsum">${esc(clAdvSum(F))}</span></summary>
    <div class="cl-sec">Счёт и налоги</div>
    <div class="cl-grid">${sel('acct','Тип счёта',CL_ACC,F.acct)}${num('iisYear','Год открытия ИИС-3',F.iisYear,'min="2024" max="'+new Date().getFullYear()+'" step="1"')}
     ${sel('salRate','Ставка НДФЛ с вашей зарплаты (для вычета)',[[13,'13 %'],[15,'15 %'],[18,'18 %'],[20,'20 %'],[22,'22 %'],[0,'не плачу НДФЛ (ИП, самозанятый)']],F.salRate)}
     ${num('salary','Официальный доход за год, ₽ (пусто — без ограничения)',F.salary||'','min="0" step="10000" placeholder="не ограничивать"')}${sw('reinvDed','Реинвестировать вычет ИИС','возвращённый налог снова вкладывается',F.reinvDed)}
     ${sw('ldv','ЛДВ для фонда ликвидности','без налога на рост пая при владении от 3 лет',F.ldv)}${sw('defaults','Учитывать дефолты','случайные дефолты выпусков (Монте-Карло), а не ежемесячная усушка',F.defaults)}</div>
    <div class="cl-sec">Пополнения и вклад</div>
    <div class="cl-grid">${num('idx','Ежегодная индексация пополнений, %',F.idx,'min="0" max="50" step="0.5"')}${num('depSpread','Вклад: ставка = ключевая минус, п.п.',F.depSpread,'step="0.1" min="0" max="10"')}</div>
    <div class="cl-sec">Облигации и реинвестирование</div>
    <div class="cl-grid">${sw('reinvest','Реинвестировать купоны','иначе купоны копятся без дохода',F.reinvest)}${sel('freq','Выплаты купонов',[[12,'12 раз в год (раз в месяц)'],[4,'4 раза в год (раз в квартал)'],[2,'2 раза в год (раз в полгода)']],F.freq)}
     ${num('lot','Цена лота (покупаем целыми бумагами), ₽',F.lot,'min="0" step="100"')}${sel('lotFund','Остаток, не хватающий на бумагу',[['fund','лежит в фонде ликвидности'],['wait','ждёт следующей покупки']],F.lotFund)}</div>
    <div class="cl-sec">Сценарий ключевой ставки</div>
    <div class="cl-row">${seg('scn',[['cbr','Прогноз ЦБ'],['hard','Жёсткий (+2 п.п.)'],['soft','Мягкий (−2 п.п.)'],['own','Своя постоянная']],F.scn)}
     <label class="field" id="cl-ownkeybox" style="${F.scn==='own'?'':'display:none'}"><span>Ставка, %</span><input class="in" id="cl-ownKey" type="number" step="0.5" min="1" max="50" value="${esc(F.ownKey)}" style="width:110px"></label></div>
    <div class="cl-sec">Как показывать</div>
    <div class="cl-row">${seg('real',[['1','В сегодняшних деньгах'],['0','Номинал']],F.real?'1':'0')}</div>
   </details>
  </div></div>
  <div id="cl-out">${clOut()}</div>
  <div class="card"><h2>Как это считается</h2><div class="note">Один движок на всех вкладках: шаг расчёта — месяц; взносы вносятся в конце месяца; налоговый год — календарный. Шкала НДФЛ для инвестиционных доходов (купоны, продажа бумаг, проценты по вкладам, дивиденды): 13 % до 2,4 млн ₽ дохода в год, 15 % с превышения.
   <b>Вклад</b>: ежемесячная капитализация по ставке «ключевая − ${f2(F.depSpread)} п.п.» по пути выбранного сценария. НДФЛ — с процентов за год сверх необлагаемой суммы (1 млн ₽ × максимальная ключевая ставка года); начисляется в конце года, а платится 1 декабря следующего года. Необлагаемая сумма общая на все вклады человека: если есть другие вклады, налог будет больше.
   <b>Фонд ликвидности</b>: ежедневное начисление приближено месячным по «ключевая − спред к ключевой»; налог только при продаже в конце срока. ЛДВ: паи старше 3 лет, лимит 3 млн ₽ × средневзвешенный срок владения этих паёв (при продаже ради налога самые старые паи уходят первыми).
   <b>ОФЗ, корпоративные, ВДО</b>: покупаем по текущей медианной доходности сегмента (без флоатеров, линкеров, бессрочных и субординированных выпусков), держим до погашения (срок ≈ медианная дюрация); погашенный номинал и купоны вкладываются по будущей доходности ≈ текущая + β × (ключевая в тот момент − ключевая сейчас), β = 0,6 для ОФЗ и 0,7 для остальных. Рыночная цена выпуска меняется с дюрацией: 1 − дюрация × (доходность сейчас − доходность покупки); к погашению она сходится к номиналу. Налог на брокерском счёте удерживается раз в год и при выводе денег в конце срока; берётся из свободных денег, а если их не хватает — продаётся часть облигаций по рыночной цене. На ИИС налог удерживается только при закрытии счёта.
   <b>ИИС-3</b>: срок освобождения зависит от года открытия (2024–2026 — 5 лет, 2027 — 6, 2028 — 7, 2029 — 8, 2030 — 9, с 2031 — 10); при выдержанном сроке налога с дохода до 30 млн ₽ нет, в том числе с пассивного дохода. Вычет — ставка вашего НДФЛ с зарплаты × взносы до 400 тыс. ₽ в год, но не больше уплаченного НДФЛ; лимита взносов 1 млн ₽ в год у ИИС-3 нет. Если закрыть счёт раньше срока, вычеты возвращаются, а доход облагается.
   <b>Дефолты</b>: основной расчёт идёт без случайных событий; в Монте-Карло каждый «транш» (покупка за месяц) с вероятностью сегмента обесценивается на 75 %. <b>Мой портфель</b>: смесь по вашим весам (облигации с вашей доходностью и дюрацией, акции, фонды ликвидности, деньги); ставка реинвестирования реагирует на ключевую ставку. <b>Своя ставка</b> — постоянная ставка с купонным налогом. Капитал в промежуточные месяцы показан за вычетом начисленного, но ещё не удержанного налога. Инфляция — прогноз Банка России, после его горизонта — последнее значение.</div></div>
  <div class="note cl-disc">Модель упрощённая. Результаты — не прогноз и не индивидуальная инвестиционная рекомендация: реальные ставки, цены, налоги и дефолты будут отличаться.</div>`;
}
/* медиана случайных траекторий (дефолты по выпускам, шоки ставки): считается по одной стратегии за такт, чтобы экран не замирал */
let CL_MCT=0;
function clMcFill(){
  clearTimeout(CL_MCT);const F=clLoadF();if(!F.defaults)return;
  const cells=Array.from(document.querySelectorAll('td[data-mc]'));if(!cells.length)return;
  const P=clMkt(),env=clEnv(P,F),N=clParams(F).months,dv=F.real?env.D[N]:1;
  const step=i=>{CL_MCT=0;const td=cells[i];if(!td||!td.isConnected)return;
    const m=clMC(F,P,td.dataset.mc,100,1);
    td.innerHTML='<b>'+clRub(m.p50[N]/dv)+'</b><br><small class="mu">'+short(m.p10[N]/dv)+' – '+short(m.p90[N]/dv)+'</small>';
    if(i+1<cells.length)CL_MCT=setTimeout(()=>step(i+1),0)};
  CL_MCT=setTimeout(()=>step(0),250);
}
function clUpdate(){S.charts=[];const o=$('#cl-out');if(!o)return;o.innerHTML=clOut();mountCharts();clMcFill()}
function bindCalcInv(){
  const form=$('#cl-form');if(!form)return;const F=clLoadF(),P=clMkt();
  const rn=(id,d,lo,hi)=>{const e=$('#cl-'+id);if(!e)return d;let v=parseFloat(String(e.value).replace(',','.'));if(!isFinite(v))v=d;if(lo!=null)v=Math.max(lo,v);if(hi!=null)v=Math.min(hi,v);return v};
  const read=()=>{
    F.start=rn('start',0,0);F.monthly=rn('monthly',0,0);F.idx=rn('idx',0,0,50);F.years=Math.round(rn('years',10,1,30));F.ownRate=rn('ownRate',15,0,100);
    F.reinvest=$('#cl-reinvest').checked;F.freq=+$('#cl-freq').value;F.lot=rn('lot',0,0);F.lotFund=$('#cl-lotFund').value;F.ownKey=rn('ownKey',12,1,50);
    F.acct=$('#cl-acct').value;F.iisYear=Math.round(rn('iisYear',new Date().getFullYear(),2024,new Date().getFullYear()));F.salRate=+$('#cl-salRate').value;F.salary=rn('salary',0,0);F.reinvDed=$('#cl-reinvDed').checked;F.ldv=$('#cl-ldv').checked;F.defaults=$('#cl-defaults').checked;F.depSpread=rn('depSpread',1.5,0,10);
    form.querySelectorAll('#cl-strat input').forEach(c=>{F.strat[c.dataset.s]=c.checked?1:0});
    $('#cl-yv').textContent=F.years;$('#cl-advsum').textContent=clAdvSum(F);
    $('#cl-ownbox').style.display=F.strat.own?'':'none';$('#cl-ownkeybox').style.display=F.scn==='own'?'':'none';
    clSave();clUpdate();
  };
  form.addEventListener('input',read);form.addEventListener('change',read);
  const ad=$('#cl-adv');if(ad)ad.addEventListener('toggle',()=>{F.adv=ad.open;clSave()});
  [['scn',v=>{F.scn=v}],['real',v=>{F.real=v==='1'}]].forEach(([id,fn])=>{const s=$('#cl-'+id);if(s)s.onclick=e=>{const b=e.target.closest('button');if(!b)return;
    s.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));fn(b.dataset.v);read()}});
  const o=$('#cl-out');
  if(o){const pick=v=>{F.view=v;clSave();clUpdate()};
    o.onchange=e=>{if(e.target.id==='cl-view')pick(e.target.value)};
    o.onclick=e=>{const t=e.target.closest('tr[data-s]');if(t&&o.querySelectorAll('tr[data-s]').length>1)pick(t.dataset.s)}}
  clMcFill();
  const b=$('#cl-pf');if(b)b.onclick=()=>{const pf=P.portfolio;if(!pf)return;if(pf.value!=null)F.start=Math.round(pf.value);if(pf.monthly!=null)F.monthly=Math.round(pf.monthly);F.strat.pf=1;clSave();render()};
  const pr=$('#cl-pre');if(pr)pr.onclick=e=>{
    const x=e.target.closest('[data-clp]');if(!x)return;
    const k=x.dataset.clp;
    if(k==='cushion'){F.start=300000;F.monthly=25000;F.years=1;F.acct='plain';F.strat={dep:1,fund:1,ofz:1,aa:0,a:0};clSave();render();return}
    if(k==='goal5'){F.start=500000;F.monthly=35000;F.years=5;F.acct='iis3';F.strat={dep:1,fund:1,ofz:1,aa:1,a:0};clSave();render();return}
    if(k==='passive50'){const G=cgLoad();G.monthly=50000;G.years=10;G.hz='years';try{localStorage.setItem('ta_calc_goal',JSON.stringify(G))}catch(err){}cgSetMode('goal');return}
  };
}

/* ── Вкладка «Пассивный доход»: тот же движок, что и «Накопить капитал» (счёт, ИИС-3, шкала НДФЛ, сценарий ставки берутся оттуда), здесь подбор пополнения или срока под цель ── */
const CG_DEF={monthly:100000,hz:'years',years:10,date:'',value:'',real:true,infl:'',strat:'',mode:'contrib'};
let CG_F=null;
function cgLoad(){
  if(CG_F)return CG_F;const s=lsJson('ta_calc_goal',{}),F=Object.assign({},CG_DEF);
  if(s&&typeof s==='object')for(const k in F){if(s[k]!==undefined&&typeof s[k]===typeof F[k])F[k]=s[k]}
  return CG_F=F;
}
function cgMode(){return lsJson('ta_calc_mode','inv')==='goal'?'goal':'inv'}
function cgSetMode(m){lsSet('ta_calc_mode',JSON.stringify(m));render()}
function cgSave(){lsSet('ta_calc_goal',JSON.stringify(cgLoad()))}
/* срок в месяцах: «через N лет» или «к дате» */
function cgMonths(G,today){
  today=today||new Date();
  if(G.hz==='date'&&G.date){const t=new Date(G.date+'T00:00:00');if(isFinite(t)&&t>today)return Math.max(1,Math.min(600,Math.round((t-today)/864e5/30.4375)))}
  return Math.max(1,Math.min(600,Math.round((+G.years||10)*12)));
}
/* доход в месяц после налога: пассивный доход облагается по шкале 13/15 % (на ИИС-3 с выдержанным сроком — нет) */
function clAfterTax(gross,exempt){const y=Math.max(0,gross)*12;return exempt?gross:(y-clNdfl(y))/12}
/* единый расчёт подбора: возвращает всё, что нужно для вывода */
function cgCalc(G,F,P,today){
  const av=clAvail(P),sid=av.some(s=>s[0]===G.strat)?G.strat:(av.some(s=>s[0]==='pf')?'pf':'ofz'),pf=P.portfolio;
  const months=cgMonths(G,today),start=G.value!==''?+G.value:(pf&&pf.value!=null?pf.value:0);
  const H=Object.assign({},F,{start,years:months/12,goalAmt:G.monthly,goalMode:G.mode});
  const P2=G.infl!==''?Object.assign({},P,{inflation:{yearly:[],default:+G.infl,estimate:false}}):P;
  const env=clEnv(P2,H,today),g=clGoal(H,P2,env,sid,G.real);
  const out={sid,months,start,H,P2,env,g};
  if(!g.ok)return out;
  const N=g.months||months,p=clParams(H,N,env.y0);if(g.monthly!=null)p.monthly=g.monthly;
  out.N=N;out.p=p;out.r=clSim(sid,p,P2,env,H);
  const p0=Object.assign({},p,{monthly:0});out.r0=clSim(sid,p0,P2,env,H);
  out.ai=clAccInfo(p);
  const inc=pf&&pf.income_month;
  if(inc!=null&&inc>0){const net=clAfterTax(inc,out.ai.exempt);out.cov={gross:inc,net,pctGross:inc/G.monthly*100,pctNet:net/G.monthly*100,real:G.real}}
  return out;
}
function cgOut(){
  const G=cgLoad(),F=clLoadF(),P=clMkt();
  if(!(G.monthly>0))return`<div class="card empty">Введите желаемый доход в месяц</div>`;
  const c=cgCalc(G,F,P),s=CL_STR.find(x=>x[0]===c.sid),real=G.real,mode=real?'в сегодняшних деньгах':'в номинальных рублях';
  const amt=clRub(G.monthly)+' в месяц ('+mode+', после налога)';
  if(!c.g.ok)return`<div class="card cl-goal"><h2>Цель недостижима</h2><div class="cl-ans">Для стратегии «${esc(s[1])}» цель ${amt} ${G.mode==='years'?'недостижима и за 50 лет при таком пополнении':'недостижима при сроке '+clYM(c.months)+' даже при очень больших пополнениях'}.</div></div>`;
  const {r,r0,N,env,p}=c,dv=env.D[N];
  const labels=[],tips=[];
  for(let k=0;k<=N;k++){const dt=new Date(env.y0,env.m0+k,1),mm=String(dt.getMonth()+1).padStart(2,'0');labels.push(mm+'.'+dt.getFullYear());tips.push(mm+'.'+dt.getFullYear()+' · '+(k?clYM(k):'сейчас'))}
  const f=real?(k=>env.D[k]):(()=>1),cdl=[];let a=0;for(let k=0;k<=N;k++){a+=clContrib(p,k)/f(k);cdl.push(a)}
  chart('cg-chart',line,{h:300,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных',
    series:[{n:'Капитал с подобранным пополнением',c:'var(--s3)',v:r.cap.map((v,k)=>v/f(k))},{n:'Без пополнений',c:'#8a93a6',dash:1,w:1.6,v:r0.cap.map((v,k)=>v/f(k))},{n:'Внесено своих денег',c:'#9aa3b5',dash:1,w:1.4,v:cdl}]});
  let head;
  if(G.mode==='years')head=c.g.months<=1?`Цель ${amt} достигается сразу: стартовой суммы достаточно.`:`Чтобы получать ${amt} на стратегии «${esc(s[1])}», при пополнении ${clRub(F.monthly)} в месяц понадобится около <b>${clYM(c.g.months)}</b>.`;
  else head=c.g.monthly<=0?`Цель ${amt} за ${clYM(N)} достигается и без ежемесячных пополнений: хватает стартовой суммы.`:
    `Чтобы через ${clYM(N)} получать ${amt} на стратегии «${esc(s[1])}», нужно пополнять примерно <b>${clRub(c.g.monthly)}</b> в месяц (с ежегодной индексацией ${f2(F.idx)} %).`;
  const cv=c.cov;
  const cov=cv?`<div class="card cl-goal"><h2>Где вы сейчас</h2><div class="cl-ans">Сейчас купоны и дивиденды дают около <b>${clRub(cv.gross)}</b> в месяц до налога и около <b>${clRub(cv.net)}</b> после налога. Цель — ${clRub(G.monthly)} после налога${cv.real?' в сегодняшних деньгах':''}: покрыто <b>${f2(cv.pctNet)} %</b> (до налога — ${f2(cv.pctGross)} %, но сравнивать нужно с целью после налога). Оценка по графику выплат на 12 месяцев, без учёта будущих изменений портфеля.</div></div>`:
    `<div class="card"><div class="note">Данных о текущем доходе нет: подключите токен или укажите стоимость портфеля.</div></div>`;
  const kp=`<div class="g g4">${kpi(G.mode==='years'?'Нужный срок':'Пополнение в месяц',G.mode==='years'?clYM(c.g.months):(c.g.monthly<=0?'не требуется':clRub(c.g.monthly)),esc(s[1])+(G.mode==='years'?' · пополнение '+clRub(F.monthly):' · срок '+clYM(N)),c.g.monthly<=0?'pos':'',S3)}
    ${kpi('Капитал к цели',clRub(real?r.finalReal:r.final),(real?'в сегодняшних деньгах, ':'')+'номинал: '+clRub(r.final),null,S1)}
    ${kpi('Пассивный доход в месяц',clRub(real?r.passiveReal:r.passive),'после налога, '+mode,'pos',S4)}
    ${kpi('Уплачено налогов',clRub(r.taxes),'за '+clYM(N)+', номинал'+(r.deductions>0?'; вычеты ИИС-3: '+clRub(r.deductions):''),null,S8)}</div>`;
  return`${kp}<div class="card cl-goal"><h2>Подбор под цель<span class="sp">${esc(s[1])}</span></h2><div class="cl-ans">${head}</div>
   <div class="note" style="margin-top:8px">Пассивный доход — проценты, купоны или дивиденды, которые капитал приносит в год, делённые на 12, после налога по шкале 13/15 % (на ИИС-3 при выдержанном сроке налога нет). Цель ${real?'пересчитана на инфляцию: к концу срока 1 ₽ будет стоить примерно '+f2(dv)+' сегодняшних':'задана в номинальных рублях'}.</div></div>
  ${cov}
  <div class="card"><h2>Рост капитала<span class="sp">через ${clYM(N)} · ${mode}</span></h2><div id="cg-chart" class="chart"></div></div>
  <div class="card"><h2>Как это считается</h2><div class="note">Подбор — бисекция по тому же движку, что и вкладка «Накопить капитал»: те же ставки, шкала НДФЛ 13/15 %, ИИС-3 (срок по году открытия, вычет), сценарий ставки ЦБ и индексация пополнений. Тип счёта, сценарий и остальные настройки берутся из вкладки «Накопить капитал». Расчёт информационный и не является инвестиционной рекомендацией; налоги уточняйте у брокера и в ФНС.</div></div>`;
}
function cgPaint(){const o=$('#cg-out');if(!o)return;S.charts=[];o.innerHTML=cgOut();mountCharts()}
function pCalcGoal(){
  const G=cgLoad(),P=clMkt(),pf=P.portfolio,av=clAvail(P);
  const num=(id,l,v,o)=>`<label class="field"><span>${l}</span><input class="in" id="cg-${id}" type="number" inputmode="decimal" value="${esc(v)}" ${o||''}></label>`;
  if(S.calcAcc!==S.account)clLoad();
  const sid=av.some(s=>s[0]===G.strat)?G.strat:(av.some(s=>s[0]==='pf')?'pf':'ofz');
  return`<div class="card"><h2>Цель по пассивному доходу<span class="sp">сколько нужно накопить</span></h2><div id="cg-form">
    <div class="cl-grid">${num('monthly','Желаемый доход в месяц после налога, ₽',G.monthly,'min="0" step="5000"')}
     <label class="field"><span>Горизонт</span><select class="in" id="cg-hz"><option value="years" ${G.hz==='years'?'selected':''}>Через N лет</option><option value="date" ${G.hz==='date'?'selected':''}>К дате</option></select></label>
     <div id="cg-yearsbox" style="${G.hz==='years'?'':'display:none'}">${num('years','Лет',G.years,'min="1" max="50" step="1"')}</div>
     <div id="cg-datebox" style="${G.hz==='date'?'':'display:none'}">${num('date','Дата цели',G.date,'').replace('type="number" inputmode="decimal"','type="date"')}</div>
     <label class="field"><span>Стратегия</span><select class="in" id="cg-strat">${av.map(x=>`<option value="${x[0]}" ${x[0]===sid?'selected':''}>${x[1]}</option>`).join('')}</select></label>
     <label class="field"><span>Что найти</span><select class="in" id="cg-mode"><option value="contrib" ${G.mode!=='years'?'selected':''}>нужное пополнение (срок задан)</option><option value="years" ${G.mode==='years'?'selected':''}>нужный срок (пополнение из вкладки «Накопить капитал»)</option></select></label>
     ${num('value','Текущий капитал, ₽',G.value,'min="0" step="10000" placeholder="'+(pf&&pf.value!=null?Math.round(pf.value):'0')+'"')}
     ${num('infl','Инфляция, % в год',G.infl,'min="0" max="50" step="0.5" placeholder="прогноз ЦБ"')}
     <label class="sw"><input type="checkbox" id="cg-real" ${G.real?'checked':''}><i></i><div><b>Цель в сегодняшних деньгах</b><small>учесть инфляцию до даты цели</small></div></label></div>
    <div class="note">Пустой «Текущий капитал» берётся из портфеля (нужен токен). Счёт, ИИС-3, налоги, своя ставка и сценарий ключевой ставки — как во вкладке «Накопить капитал».</div></div></div>
   <div id="cg-out">${cgOut()}</div>`;
}
function bindCalcGoal(){
  const form=$('#cg-form');if(!form)return;const G=cgLoad();
  const rd=id=>{const e=$('#cg-'+id);return e?e.value.trim():''};
  const nm=(id,d)=>{const v=parseFloat(rd(id).replace(',','.'));return isFinite(v)&&v>=0?v:d};
  const read=()=>{
    G.monthly=nm('monthly',0);G.hz=rd('hz')==='date'?'date':'years';G.years=Math.min(50,Math.max(1,nm('years',10)));G.date=rd('date');G.strat=rd('strat');G.mode=rd('mode')==='years'?'years':'contrib';
    G.value=rd('value')===''?'':nm('value','');G.real=$('#cg-real').checked;G.infl=rd('infl')===''?'':nm('infl','');
    $('#cg-yearsbox').style.display=G.hz==='years'?'':'none';$('#cg-datebox').style.display=G.hz==='date'?'':'none';
    cgSave();clearTimeout(bindCalcGoal.t);bindCalcGoal.t=setTimeout(cgPaint,120);
  };
  form.addEventListener('input',read);form.addEventListener('change',read);
}
function pCalc(){
  const m=cgMode();
  const sw=`<div class="row noprint"><div class="seg cl-tabs">${[['inv','Накопить капитал'],['goal','Пассивный доход']].map(([k,t])=>`<button class="${k===m?'on':''}" onclick="cgSetMode('${k}')">${t}</button>`).join('')}</div></div>`;
  return`<div class="cl-page">${sw}${m==='goal'?pCalcGoal():pCalcInv()}</div>`;
}
function bindCalc(){if(cgMode()==='goal')bindCalcGoal();else bindCalcInv()}
