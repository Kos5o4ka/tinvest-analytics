/* калькулятор инвестиций: интерфейс (слева параметры, справа результат; три вкладки: накопить, жить с капитала, подбор под цель) */
/* ── Состояние ── */
const CL_DEF={start:500000,monthly:20000,idx:5,idxMode:'own',years:10,strat:{dep:1,fund:1,ofz:1,aa:1,a:1},ownRate:15,reinvest:true,freq:4,lot:1000,lotFund:'fund',scn:'cbr',ownKey:12,
  acct:'plain',reinvDed:true,ldv:true,defaults:true,real:true,depSpread:1.5,adv:false,view:'',iisYear:new Date().getFullYear(),salRate:13,salary:0,
  mixStk:50,mixBond:'ofz',stkGrow:'',stkDiv:'',fxWeak:'',inflOvr:'',
  spend:80000,spendYears:30,goalAmt:100000,goalMode:'contrib',goalStrat:'ofz',cmpA:'ofz',cmpB:'mix',lifeView:''};
let CL_F=null;
function clLoadF(){
  if(CL_F)return CL_F;
  const F=JSON.parse(JSON.stringify(CL_DEF));
  try{const s=JSON.parse(localStorage.getItem('ta_calc')||'null');
    if(s&&typeof s==='object')for(const k in F){if(s[k]!==undefined&&(typeof s[k]===typeof F[k]||(F[k]===''&&typeof s[k]==='number')))F[k]=k==='strat'?Object.assign({},s[k]):s[k]}}catch(e){}
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
/* «Мой портфель» доступен, если известны хотя бы доли классов активов (даже без облигаций) */
function clAvail(P){const pf=P.portfolio;return CL_STR.filter(s=>s[0]!=='pf'||(pf&&(pf.irr!=null||pf.shares)))}
function clMode(){const m=lsJson('ta_calc_mode','inv');return m==='life'||m==='goal'?m:'inv'}
function cgSetMode(m){lsSet('ta_calc_mode',JSON.stringify(m));render()}
function clRun(F,P){
  const env=clEnv(P,F),p=clParams(F,0,env.y0,P),N=p.months,ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  const res=ids.map(id=>{const s=CL_STR.find(x=>x[0]===id),r=clSim(id,p,P,env,F);r.id=id;r.name=s[1];r.color=s[2];return r});
  return{env,p,N,res};
}
/* доход в месяц после налога: пассивный доход облагается по шкале 13/15 % (на ИИС-3 с выдержанным сроком — нет) */
function clAfterTax(gross,exempt){const y=Math.max(0,gross)*12;return exempt?gross:(y-clNdfl(y))/12}
const clDates=(env,N)=>{const labels=[],tips=[];for(let k=0;k<=N;k++){const d=new Date(env.y0,env.m0+k,1),mm=String(d.getMonth()+1).padStart(2,'0');labels.push(mm+'.'+d.getFullYear());tips.push(mm+'.'+d.getFullYear()+' · '+(k?clYM(k):'сейчас'))}return{labels,tips}};
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
  rows.push(['Инфляция (по годам)',(F.inflOvr!==''?pctp(+F.inflOvr,1)+' в год (своя)':P.inflation.yearly&&P.inflation.yearly.length?P.inflation.yearly.map(y=>y.year+': '+pctp(y.mid,1)).join('; '):pctp(P.inflation.default,1)+' в год'),P.inflation.estimate?'оценка':'прогноз Банка России']);
  rows.push(['Вклад: ставка',pctp(env.depRate(0),2),'ключевая − '+f2(F.depSpread)+' п.п.']);
  rows.push(['Фонд ликвидности: доходность',pctp(env.fundRate(0),2),P.lqdt.estimate?'оценка: ключевая − '+f2(P.lqdt.spread)+' п.п.':'по данным фонда']);
  ['ofz','aaa','aa','a','hy'].forEach(id=>{const s=P.segments[id];if(!s)return;
    rows.push([s.name+': доходность / срок',pctp(s.yield,2)+' / '+f2(s.dur)+' г.','потери от дефолтов '+f2(s.loss)+' % в год'+(s.estimate?' · оценка':'')])});
  const fl=P.segments.flt;if(fl)rows.push([fl.name+': доходность',pctp(fl.yield,2),'ключевая + '+f2(fl.spread!=null?fl.spread:fl.yield-P.key_rate.current)+' п.п.'+(fl.estimate?' · оценка':'')]);
  const st=P.stocks||{div:8,growth:6};
  rows.push(['Акции РФ: дивиденды / рост цены',pctp(env.stDiv,1)+' / '+pctp(F.stkGrow!==''?+F.stkGrow:st.growth,1),'допущение, можно изменить в «Допущения по акциям и валюте»']);
  const fx=P.fx_bonds||{yield:6,fx:5};
  rows.push(['Замещающие облигации: купон / ослабление рубля',pctp(fx.yield,1)+' / '+pctp(F.fxWeak!==''?+F.fxWeak:fx.fx,1),'допущение; прибыль от курса облагается при погашении или продаже']);
  if(P.portfolio&&P.portfolio.irr!=null)rows.push(['Мой портфель: доходность облигаций',pctp(P.portfolio.irr,2),'доходность к погашению по потокам облигаций']);
  const sh=P.portfolio&&P.portfolio.shares;
  if(sh){const nm={bonds:'облигации',stocks:'акции',funds:'прочие фонды',lqdt:'фонды ликвидности',cash:'деньги',other:'прочее'};
    rows.push(['Мой портфель: структура',Object.keys(nm).filter(k=>sh[k]>0).map(k=>nm[k]+' '+pctp(sh[k]*100,0)).join(', '),P.portfolio.dur_bonds?'дюрация облигаций '+f2(P.portfolio.dur_bonds)+' г.':'считается как смесь частей'])}
  return`<div class="tbl"><table><thead><tr><th class="l">Параметр</th><th>Значение</th><th class="l">Источник / примечание</th></tr></thead><tbody>${
    rows.map(r=>`<tr><td class="l">${r[0]}</td><td class="num">${r[1]}</td><td class="l mu">${r[2]}</td></tr>`).join('')}</tbody></table></div>`;
}
/* ── Медианы случайных траекторий: считаются в фоне; пока их нет, итоги показаны без учёта дефолтов ── */
let CL_MED={key:'',v:{}},CL_MCT=0;
function clMedKey(F,P){const o=Object.assign({},F);delete o.view;delete o.adv;delete o.lifeView;delete o.cmpA;delete o.cmpB;return JSON.stringify([o,P.key_rate.current,P.fallback?1:0,P.portfolio&&P.portfolio.value])}
function clMedGet(F,P,id){return F.defaults&&CL_MED.key===clMedKey(F,P)?CL_MED.v[id]:undefined}
function clMedCell(m,dv){return'<b>'+clRub(m.p50/dv)+'</b><br><small class="mu">'+short(m.p10/dv)+' – '+short(m.p90/dv)+'</small>'}
function clMcFill(){
  clearTimeout(CL_MCT);CL_MCT=0;const F=clLoadF();if(!F.defaults||clMode()!=='inv')return;
  const cells=Array.from(document.querySelectorAll('td[data-mc]'));if(!cells.length)return;
  const P=clMkt(),key=clMedKey(F,P),env=clEnv(P,F),N=clParams(F,0,env.y0,P).months,dv=F.real?env.D[N]:1;
  if(CL_MED.key!==key)CL_MED={key,v:{}};
  let did=false;
  const step=i=>{CL_MCT=0;const td=cells[i];
    if(!td){if(did)clUpdate();return}
    if(!td.isConnected||CL_MED.key!==key)return;
    let m=CL_MED.v[td.dataset.mc];
    if(!m){const q=clMC(F,P,td.dataset.mc,100,1);m={p10:q.p10[N],p50:q.p50[N],p90:q.p90[N]};CL_MED.v[td.dataset.mc]=m;did=true}
    td.innerHTML=clMedCell(m,dv);
    CL_MCT=setTimeout(()=>step(i+1),0)};
  CL_MCT=setTimeout(()=>step(0),did?0:200);
}
function clTile(lbl,val,sub,dot,cls){
  return`<div class="st-tile"><div class="st-tl"><span>${lbl}</span><span class="st-dot ${dot||'mu'}"></span></div><div class="st-tv num ${cls||''}">${val}</div><div class="st-ts">${sub||'&nbsp;'}</div></div>`;
}
function clBeatDeposit(cur,p,P,env,F){
  if(cur.id==='dep')return{isDep:true};
  const dep=clSim('dep',p,P,env,F),N=p.months;
  if(!(cur.cap[N]>dep.cap[N]))return{beats:false};
  let k=N;
  while(k>1&&cur.cap[k-1]>dep.cap[k-1])k--;
  return{beats:true,month:k};
}
function clWaterfallHtml(cur){
  const gross=cur.income+cur.taxes,taxes=cur.taxes,ded=cur.deductions,net=cur.final-cur.deposited;
  const mx=Math.max(1,Math.abs(gross),Math.abs(taxes),Math.abs(ded),Math.abs(net));
  const step=(lbl,val,c,isNet,sg)=>{
    const w=Math.max(4,Math.min(100,Math.abs(val)/mx*100));
    const txt=(sg||'')+clRub(Math.abs(val));
    return`<div class="cl-wf-step${isNet?' is-net':''}"><span class="cl-wf-lbl">${lbl}</span><b class="cl-wf-val num ${isNet?(val>=0?'pos':'neg'):''}">${val<0&&!sg?'−':''}${txt}</b><div class="cl-wf-track"><i style="width:${w.toFixed(1)}%;background:${c}"></i></div></div>`;
  };
  return`<div class="card"><h2>Мост результата: доходы, налоги и вычеты<span class="sp">${esc(cur.name)} · в номинальных рублях</span></h2>
    <div class="cl-wf">${step('+ Доход до налога',gross,'var(--s1)',false,gross>=0?'+':'−')}${step('− Налоги (НДФЛ)',taxes,'var(--neg)',false,'−')}${step('+ Вычеты ИИС',ded,'var(--s4)',false,'+')}${step('= Чистый результат',net,'var(--pos)',true,net>=0?'+':'−')}</div>
    <p class="note" style="margin-top:8px">Вложено своих средств: <b>${clRub(cur.deposited)}</b> · итоговый капитал (номинал): <b>${clRub(cur.final)}</b> (= внесено + чистый результат).</p></div>`;
}
/* ── Правая часть: накопить капитал ── */
function clOut(){
  const F=clLoadF(),P=clMkt();
  const ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  if(!ids.length)return`<div class="card empty">Выберите хотя бы одну стратегию для сравнения</div>`;
  const run=clRun(F,P),{env,N,res,p}=run,real=F.real,dv=k=>real?env.D[k]:1,mode=real?'в сегодняшних деньгах':'в номинальных рублях';
  const {labels,tips}=clDates(env,N);
  res.forEach(r=>{r.med=clMedGet(F,P,r.id);r.effReal=r.med?r.med.p50/env.D[N]:r.finalReal});
  const best=res.slice().sort((a,b)=>b.effReal-a.effReal)[0],cur=res.find(r=>r.id===F.view)||best,defl=env.D[N];
  /* состав капитала выбранной стратегии: внесено + вычеты ИИС + доход после налогов */
  const RF=cur.id==='dep'?null:cur.RF,sIn=[],sDed=[],sInc=[];let ci=0,cd=0;
  for(let k=0;k<=N;k++){ci+=clContrib(p,k)/dv(k);if(RF)cd+=RF[k]/dv(k);sIn.push(ci);sDed.push(cd);sInc.push(cur.cap[k]/dv(k)-ci-cd)}
  const ser=[{n:'Внесено',c:'#8a93a6',v:sIn}];if(cd>0)ser.push({n:'Вычеты и возвраты ИИС',c:'var(--s4)',v:sDed});ser.push({n:'Доход после налогов',c:'var(--s3)',v:sInc});
  chart('cl-stack',clStack,{h:300,series:ser,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных'});
  const hasMed=!!cur.med,fin=hasMed?cur.med.p50/dv(N):(real?cur.finalReal:cur.final),inc=sInc[N],pas=real?cur.passiveReal:cur.passive;
  const finSub=esc(cur.name)+' · '+(real?'в сегодняшних деньгах':'номинал')+(F.defaults?(hasMed?' · медиана с дефолтами':' · без учёта дефолтов'):'');
  const beat=clBeatDeposit(cur,p,P,env,F);
  const beatVal=beat.isDep?'сам вклад':beat.beats?clYM(beat.month):'не обгоняет';
  const beatSub=beat.isDep?'базовая точка сравнения':beat.beats?`с ${beat.month}-го мес. обгоняет вклад после налогов`:`уступает вкладу на горизонте ${clYM(N)}`;
  const pick=res.length>1?`<div class="cl-view"><span>Итоги и график для</span><select class="in" id="cl-view"><option value="">лучшей стратегии (${esc(best.name)})</option>${
    res.map(r=>`<option value="${r.id}" ${r.id===F.view?'selected':''}>${esc(r.name)}</option>`).join('')}</select></div>`:'';
  const kp=`${pick}<div class="st-tiles cl-tiles">${clTile('Итоговый капитал',clRub(fin),finSub,'pos','pos')}
    ${clTile('Чистый доход',clRub(inc),'после налогов, сверх внесённого'+(cd>0?' и вычетов':'')+(hasMed?' · без дефолтов':''),inc>=0?'pos':'neg',cls(inc))}
    ${clTile('Уплачено налогов',clRub(cur.taxes),'НДФЛ за '+clYM(N)+', номинал',cur.taxes>0?'warn':'pos')}
    ${clTile('Пассивный доход в месяц',clRub(pas),'после налога, '+(real?'в сегодняшних деньгах':'номинал')+(F.defaults?' · без дефолтов':''),'mu')}</div>
    <div class="st-callout"><b>Точка обгона вклада:</b> <span class="num ${beat.beats?'pos':''}">${esc(beatVal)}</span> — ${esc(beatSub)}.</div>`;
  const wf=clWaterfallHtml(cur);
  const stk=`<div class="card"><h2>Из чего состоит капитал<span class="sp">${esc(cur.name)} · ${mode}</span></h2><div id="cl-stack" class="chart"></div>
    <div class="note" style="margin-top:10px">Цены за ${clYM(N)} вырастут в ×${f2(defl)} по прогнозу инфляции: 1 ₽ в конце срока ≈ ${f2(1/defl)} ₽ сегодня.${real?' Взносы, вычеты и доход пересчитаны в сегодняшние деньги на дату поступления.':''} Слои — без случайных событий.</div></div>`;
  const th=['Стратегия','Итоговый капитал','Внесено','Получено дохода','Уплачено налогов','Вычеты и возвраты ИИС','Капитал в сегодняшних деньгах','Пассивный доход в месяц (после налога)','Годовая доходность после налогов, номинал / реальная'].concat(F.defaults?['Медиана с дефолтами и шоками ставки']:[]);
  const rows=res.map(r=>`<tr data-s="${r.id}" class="${r===cur?'cl-cur':''}"><td class="l"><i class="cl-dot" style="background:${r.color}"></i>${esc(r.name)}${r===best?' <small class="mu">лучшая</small>':''}</td><td class="num"><b>${clRub(r.final)}</b></td><td class="num">${clRub(r.deposited)}</td>
    <td class="num ${cls(r.income)}">${clRub(r.income)}</td><td class="num">${clRub(r.taxes)}</td><td class="num">${r.deductions>0?clRub(r.deductions):'—'}</td><td class="num"><b>${clRub(r.finalReal)}</b></td>
    <td class="num">${clRub(r.passive)}<br><small class="mu">${clRub(r.passiveReal)} сегодня</small></td><td class="num">${r.xirr==null?'—':pctp(r.xirr,1)}<br><small class="mu">${r.xirrReal==null?'—':pctp(r.xirrReal,1)} реальная</small></td>${F.defaults?`<td class="num" data-mc="${r.id}">${r.med?clMedCell(r.med,real?env.D[N]:1):'<small class="mu">считаю…</small>'}</td>`:''}</tr>`).join('');
  const warn=[],ai=clAccInfo(p);
  if(F.acct!=='plain'){
    if(res.some(r=>r.id==='dep'))warn.push('Вклад лежит в банке, а не на ИИС: вычет и льготы ИИС к нему не применяются, налог считается как на обычном счёте.');
    if(!ai.exempt)warn.push('ИИС-3, год открытия '+ai.openYear+': минимальный срок '+ai.term+' лет, а к концу расчёта счёт будет открыт '+clYM(ai.own)+'. При закрытии раньше срока полученные вычеты возвращаются, а весь доход облагается налогом.');
    else warn.push('ИИС-3, год открытия '+ai.openYear+': минимальный срок '+ai.term+' лет выдержан; доход освобождён от налога до 30 млн ₽ за всё время, вычет — '+f2(ai.rate*100)+' % от взносов до 400 тыс. ₽ в год (52–88 тыс. ₽ в год при ставках 13–22 %'+(F.salary>0?', не больше НДФЛ с дохода '+clRub(F.salary):'')+').');
    if(!(ai.rate>0))warn.push('Ставка НДФЛ с зарплаты не указана: вычет не начисляется (ИП и самозанятые без НДФЛ с зарплаты его не получают).');
  }
  if(F.acct==='plain'&&res.some(r=>r.id==='fund'||r.id==='stk')&&F.ldv)warn.push('ЛДВ: рост пая или цены акций без налога при владении от 3 лет, лимит 3 млн ₽ × средневзвешенный срок владения; каждое пополнение учитывается отдельно по сроку владения. Дивиденды акций облагаются ежегодно.');
  if(res.some(r=>r.id==='fxb'))warn.push('Замещающие облигации: купон в валюте, рублёвая курсовая переоценка облагается налогом при погашении или продаже (на ИИС-3 с выдержанным сроком — нет).');
  if(res.some(r=>r.id==='mix'||r.id==='pf'))warn.push('Смесь частей: доли поддерживаются распределением стартовой суммы и взносов, без продаж ради ребалансировки; порог 15 % делится пропорционально долям.');
  if(P.portfolio==null&&F.strat.pf)warn.push('Нет данных о портфеле — «Мой портфель» недоступен.');
  const wn=warn.length?`<div class="st-callout${F.acct!=='plain'&&!ai.exempt?' warn':''}" style="margin:12px 0 0">${warn.map(w=>'• '+esc(w)).join('<br>')}</div>`:'';
  const tbl=`<div class="card"><h2>Сравнение стратегий<span class="sp">через ${clYM(N)}</span></h2><div class="tbl cl-tbl"><table><thead><tr>${th.map((t,i)=>`<th class="${i?'':'l'}">${t}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="note" style="margin-top:10px">«Итоговый капитал» — если закрыть позиции и вывести деньги в конце срока: за вычетом всех налогов, включая налог последнего года, налог при закрытии ИИС и налог при продаже. «Годовая доходность» — эффективная ставка взносов против итога с учётом их дат (после налогов); реальная — за вычетом инфляции. «Получено дохода» = итог − внесено − вычеты.${res.length>1?' Нажмите на строку, чтобы показать стратегию в итогах и на графике.':''}${F.defaults?' Основной расчёт идёт без случайных событий и поэтому не учитывает дефолты; последний столбец и «лучшая» стратегия — по медиане 100 случайных траекторий с дефолтами по выпускам (редкие события, а не равномерная усушка) и шоками ключевой ставки и рынка акций, так что разница включает не только дефолты.':''}</div>${wn}</div>`;
  let cmp='';
  if(res.length>1){
    const cdl=[];let a=0;for(let k=0;k<=N;k++){a+=clContrib(p,k)/dv(k);cdl.push(a)}
    const series=res.map(r=>({n:r.name,c:r.color,v:r.cap.map((v,k)=>v/dv(k))}));
    series.push({n:'Внесено своих денег',c:'#9aa3b5',dash:1,w:1.6,v:cdl});
    chart('cl-chart',line,{h:300,series,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных'});
    cmp=`<div class="card"><h2>Рост капитала по стратегиям<span class="sp">${mode}</span></h2><div id="cl-chart" class="chart"></div></div>`;
  }
  const deep=typeof clDeepHtml==='function'?clDeepHtml(F,P,run,cur):'';
  return`${kp}${wf}${stk}${deep}${tbl}${cmp}<div class="card"><h2>Что заложено в расчёт</h2>${clSegTable(P,F,env)}</div>`;
}
/* ── Правая часть: жизнь с капитала ── */
function clLifeOut(){
  const F=clLoadF(),P=clMkt(),ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  if(!ids.length)return`<div class="card empty">Выберите хотя бы одну стратегию</div>`;
  if(!(F.spend>0))return`<div class="card empty">Введите, сколько тратить в месяц после выхода на капитал</div>`;
  const real=F.real,mode=real?'в сегодняшних деньгах':'в номинальных рублях';
  const runs=ids.map(id=>{const x=clLifeRun(F,P,id),o=Object.assign({},x.o,{spend:0}),perp=clPerpetual(F,P,x.env,id,x.r.final,x.N,o);
    const s=CL_STR.find(z=>z[0]===id);return Object.assign(x,{id,name:s[1],color:s[2],perp})});
  const cur=runs.find(r=>r.id===F.lifeView)||runs[0],{env,N,life}=cur,H=life.H,dv=k=>real?env.D[k]:1;
  const {labels,tips}=clDates(env,N+H);
  const capPath=Array.from(cur.r.cap).concat(life.path.slice(1)),cdl=[];let a=0;
  for(let k=0;k<capPath.length;k++){a+=k<=N?clContrib(cur.p,k)/dv(k):0;cdl.push(a)}
  const lab=labels.slice(0,capPath.length),tp=tips.slice(0,capPath.length);
  chart('cl-lifech',line,{h:300,labels:lab,tipLabels:tp,fa:short,ft:v=>clRub(v),empty:'Нет данных',
    series:[{n:'Капитал',c:'var(--s3)',v:capPath.map((v,k)=>v/dv(k))},{n:'Внесено своих денег',c:'#9aa3b5',dash:1,w:1.4,v:cdl.slice(0,capPath.length)}]});
  const K0=cur.r.final,K0r=K0/env.D[N],spendEnd=F.spend*env.D[N];
  const years=life.dep!=null?life.dep/12:null;
  const lasts=life.dep==null?`на весь срок ${clYM(H)}`:`${clYM(life.dep)} (до ${new Date(env.y0,env.m0+N+life.dep,1).getFullYear()} года)`;
  const cover=cur.perp>0?cur.perp/F.spend*100:0;
  const kp=`<div class="st-tiles cl-tiles">${clTile('Капитал к выходу',clRub(real?K0r:K0),esc(cur.name)+' · '+mode+(real?'':'; в сегодняшних: '+clRub(K0r)),'pos','pos')}
    ${clTile('Вечный доход в месяц',clRub(real?cur.perp:cur.perp*env.D[N]),'сохраняет покупательную способность капитала; '+f2(cover)+' % ваших трат',cover>=100?'pos':'warn')}
    ${clTile('Тратите в месяц',clRub(real?F.spend:spendEnd),(real?'в сегодняшних деньгах':'к дате выхода '+clRub(spendEnd))+', растёт с инфляцией','mu')}
    ${clTile('Капитала хватит',life.dep==null?'весь срок':clYM(life.dep),life.dep==null?'снятие '+clYM(H)+' без исчерпания':'исчерпается '+lasts,life.dep==null?'pos':'neg',life.dep==null?'pos':'neg')}</div>`;
  const verdict=life.dep==null?`При тратах ${clRub(F.spend)} в месяц (в сегодняшних деньгах, с ростом на инфляцию) капитала <b>хватает на весь срок ${clYM(H)}</b>; к концу останется ${clRub(real?life.end/env.D[N+H]:life.end)}${real?' в сегодняшних деньгах':''}.`:
    `При тратах ${clRub(F.spend)} в месяц (в сегодняшних деньгах, с ростом на инфляцию) капитал <b>исчерпается через ${clYM(life.dep)} после выхода</b>. Безопасное снятие, не съедающее капитал, — около <b>${clRub(cur.perp)}</b> в месяц в сегодняшних деньгах.`;
  const th=['Стратегия','Капитал к выходу, сегодняшние ₽','Вечный доход в месяц, сегодняшние ₽','Покрытие трат','Хватит на'];
  const rows=runs.map(r=>`<tr data-lf="${r.id}" class="${r===cur?'cl-cur':''}"><td class="l"><i class="cl-dot" style="background:${r.color}"></i>${esc(r.name)}</td><td class="num">${clRub(r.r.final/r.env.D[r.N])}</td><td class="num"><b>${clRub(r.perp)}</b></td>
    <td class="num ${r.perp>=F.spend?'pos':'neg'}">${f2(F.spend>0?r.perp/F.spend*100:0)} %</td><td class="num">${r.life.dep==null?'весь срок':clYM(r.life.dep)}</td></tr>`).join('');
  const deep=typeof clLifeMcHtml==='function'?clLifeMcHtml(F,P,cur):'';
  return`${kp}<div class="card cl-goal"><h2>Выход на капитал<span class="sp">${esc(cur.name)}</span></h2><div class="st-callout${life.dep==null?'':' warn'}">${verdict}</div>
    <div class="note" style="margin-top:8px">Сначала копим ${clYM(N)}, затем ежемесячно снимаем ${clRub(F.spend)} (сегодняшних денег) с индексацией на инфляцию в течение ${clYM(H)}. Две цифры: <b>вечный доход</b> — сколько можно снимать, не уменьшая реальный капитал; <b>срок исчерпания</b> — на сколько лет хватит при заданных тратах. Если снимать только купоны в номинале, капитал сохранится в рублях, но потеряет покупательную способность на величину инфляции.</div></div>
   <div class="card"><h2>Капитал: накопление и снятие<span class="sp">${mode}</span></h2><div id="cl-lifech" class="chart"></div></div>
   ${deep}
   <div class="card"><h2>Сравнение стратегий<span class="sp">снятие с ${clYM(N)}</span></h2><div class="tbl cl-tbl"><table><thead><tr>${th.map((t,i)=>`<th class="${i?'':'l'}">${t}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="note" style="margin-top:10px">Нажмите на строку, чтобы показать стратегию. Допущения фазы снятия: к выходу позиции пересобираются в тех же пропорциях по цене после налогов; доход, облагаемый ежегодно (купоны, дивиденды, проценты), — налог в конце года; рост цены — налог с доли прироста в каждом снятии; на ИИС-3 с выдержанным сроком налога нет до 30 млн ₽ финансового результата за всё время; ЛДВ считается соблюдённой. Ставки в фазе снятия следуют сценарию ключевой ставки.</div></div>
   <div class="card"><h2>Что заложено в расчёт</h2>${clSegTable(P,F,env)}</div>`;
}
/* ── Правая часть: подбор под цель по пассивному доходу ── */
function cgCalc(F,P){
  const av=clAvail(P),sid=av.some(s=>s[0]===F.goalStrat)?F.goalStrat:'ofz',pf=P.portfolio;
  const H=Object.assign({},F,{goalAmt:F.goalAmt});
  const env=clEnv(P,H),g=clGoal(H,P,env,sid,F.real);
  const out={sid,H,env,g};
  if(!g.ok)return out;
  const N=g.months||clParams(H,0,env.y0,P).months,p=clParams(H,N,env.y0,P);if(g.monthly!=null)p.monthly=g.monthly;
  out.N=N;out.p=p;out.r=clSim(sid,p,P,env,H);out.r0=clSim(sid,Object.assign({},p,{monthly:0}),P,env,H);out.ai=clAccInfo(p);
  const inc=pf&&pf.income_month;
  if(inc!=null&&inc>0){const net=clAfterTax(inc,out.ai.exempt);out.cov={gross:inc,net,pctGross:inc/F.goalAmt*100,pctNet:net/F.goalAmt*100,real:F.real}}
  return out;
}
function clGoalOut(){
  const F=clLoadF(),P=clMkt();
  if(!(F.goalAmt>0))return`<div class="card empty">Введите желаемый доход в месяц</div>`;
  const c=cgCalc(F,P),s=CL_STR.find(x=>x[0]===c.sid),real=F.real,mode=real?'в сегодняшних деньгах':'в номинальных рублях';
  const amt=clRub(F.goalAmt)+' в месяц ('+mode+', после налога)',T=clYM(Math.round((+F.years||1)*12));
  if(!c.g.ok)return`<div class="card cl-goal"><h2>Цель недостижима</h2><div class="cl-ans">Для стратегии «${esc(s[1])}» цель ${amt} ${F.goalMode==='years'?'недостижима и за 50 лет при таком пополнении':'недостижима при сроке '+T+' даже при очень больших пополнениях'}.</div></div>`;
  const {r,r0,N,env,p}=c,dv=env.D[N],{labels,tips}=clDates(env,N);
  const f=real?(k=>env.D[k]):(()=>1),cdl=[];let a=0;for(let k=0;k<=N;k++){a+=clContrib(p,k)/f(k);cdl.push(a)}
  chart('cg-chart',line,{h:300,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных',
    series:[{n:'Капитал с подобранным пополнением',c:'var(--s3)',v:r.cap.map((v,k)=>v/f(k))},{n:'Без пополнений',c:'#8a93a6',dash:1,w:1.6,v:r0.cap.map((v,k)=>v/f(k))},{n:'Внесено своих денег',c:'#9aa3b5',dash:1,w:1.4,v:cdl}]});
  let head;
  if(F.goalMode==='years')head=c.g.months<=1?`Цель ${amt} достигается сразу: стартовой суммы достаточно.`:`Чтобы получать ${amt} на стратегии «${esc(s[1])}», при пополнении ${clRub(F.monthly)} в месяц понадобится около <b>${clYM(c.g.months)}</b>.`;
  else head=c.g.monthly<=0?`Цель ${amt} за ${clYM(N)} достигается и без ежемесячных пополнений: хватает стартовой суммы.`:
    `Чтобы через ${clYM(N)} получать ${amt} на стратегии «${esc(s[1])}», нужно пополнять примерно <b>${clRub(c.g.monthly)}</b> в месяц (индексация взносов: ${p.idx>0?f2(p.idx)+' % в год':'нет'}).`;
  const cv=c.cov;
  const cov=cv?`<div class="card cl-goal"><h2>Где вы сейчас</h2><div class="cl-ans">Сейчас купоны и дивиденды дают около <b>${clRub(cv.gross)}</b> в месяц до налога и около <b>${clRub(cv.net)}</b> после налога. Цель — ${clRub(F.goalAmt)} после налога${cv.real?' в сегодняшних деньгах':''}: покрыто <b>${f2(cv.pctNet)} %</b> (до налога — ${f2(cv.pctGross)} %, но сравнивать нужно с целью после налога). Оценка по графику выплат на 12 месяцев, без учёта будущих изменений портфеля.</div></div>`:
    `<div class="card"><div class="note">Данных о текущем доходе нет: подключите токен или откройте вкладку при загруженном портфеле.</div></div>`;
  const kp=`<div class="st-tiles cl-tiles">${clTile(F.goalMode==='years'?'Нужный срок':'Пополнение в месяц',F.goalMode==='years'?clYM(c.g.months):(c.g.monthly<=0?'не требуется':clRub(c.g.monthly)),esc(s[1])+(F.goalMode==='years'?' · пополнение '+clRub(F.monthly):' · срок '+clYM(N)),c.g.monthly<=0?'pos':'mu',c.g.monthly<=0?'pos':'')}
    ${clTile('Капитал к цели',clRub(real?r.finalReal:r.final),(real?'в сегодняшних деньгах, ':'')+'номинал: '+clRub(r.final),'mu')}
    ${clTile('Пассивный доход в месяц',clRub(real?r.passiveReal:r.passive),'после налога, '+mode,'pos','pos')}
    ${clTile('Уплачено налогов',clRub(r.taxes),'за '+clYM(N)+', номинал'+(r.deductions>0?'; вычеты ИИС-3: '+clRub(r.deductions):''),r.taxes>0?'warn':'pos')}</div>`;
  return`${kp}<div class="card cl-goal"><h2>Подбор под цель<span class="sp">${esc(s[1])}</span></h2><div class="st-callout">${head}</div>
   <div class="note" style="margin-top:8px">Пассивный доход — проценты, купоны или дивиденды, которые капитал приносит в год, делённые на 12, после налога по шкале 13/15 % (на ИИС-3 при выдержанном сроке налога нет). Цель ${real?'пересчитана на инфляцию: к концу срока 1 ₽ будет стоить примерно '+f2(dv)+' сегодняшних':'задана в номинальных рублях'}. Расчёт идёт без случайных событий (дефолты не учтены).</div></div>
  ${cov}
  <div class="card"><h2>Рост капитала<span class="sp">через ${clYM(N)} · ${mode}</span></h2><div id="cg-chart" class="chart"></div></div>
  ${typeof clGoToHtml==='function'?clGoToHtml(F,c):''}`;
}
function clTabOut(){const m=clMode();return m==='life'?clLifeOut():m==='goal'?clGoalOut():clOut()}
/* ── Левая часть: параметры ── */
const CL_PRESETS=[
  ['cushion','Подушка безопасности','6–12 месяцев расходов: вклад, фонд ликвидности, короткие ОФЗ, низкий риск'],
  ['house','Крупная покупка через 3–5 лет','ИИС-3, ОФЗ и облигации AAA: защита от просадки к концу срока'],
  ['passive100','Пассивный доход 100 тыс. ₽ в месяц','смесь акций и облигаций, реинвестирование; цель видна на вкладке «Подбор под цель»'],
  ['mine','Ускорить мой портфель','ваш баланс, среднее пополнение за год и текущая структура']];
function clForm(F,P){
  const pf=P.portfolio,m=clMode(),st=P.stocks||{div:8,growth:6},fx=P.fx_bonds||{yield:6,fx:5};
  const num=(id,l,v,o)=>`<label class="field"><span>${l}</span><input class="in" id="cl-${id}" type="number" inputmode="decimal" value="${esc(v)}" ${o||''}></label>`;
  const sw=(id,t,sm,on)=>`<label class="sw"><input type="checkbox" id="cl-${id}" ${on?'checked':''}><i></i><div><b>${t}</b><small>${sm}</small></div></label>`;
  const sel=(id,l,opts,v)=>`<label class="field"><span>${l}</span><select class="in" id="cl-${id}">${opts.map(o=>`<option value="${o[0]}" ${String(o[0])===String(v)?'selected':''}>${o[1]}</option>`).join('')}</select></label>`;
  const lever=(id,l,opts,v)=>`<div class="cl-lv"><span>${l}</span><div class="seg" id="cl-${id}" role="group" aria-label="${l}">${opts.map(o=>`<button type="button" data-v="${o[0]}" aria-pressed="${String(o[0])===String(v)}" class="${String(o[0])===String(v)?'on':''}">${o[1]}</button>`).join('')}</div></div>`;
  const av=clAvail(P);
  const chips=av.map(s=>`<label class="cl-chip"><input type="checkbox" data-s="${s[0]}" ${F.strat[s[0]]?'checked':''}><span><i style="background:${s[2]}"></i>${s[1]}</span></label>`).join('');
  const bondOpts=[['ofz','ОФЗ'],['flt','Флоатеры'],['aaa','Корпоративные AAA'],['aa','Корпоративные AA'],['a','Корпоративные A']];
  const mixRow=CL_MIX.map(x=>`<button type="button" data-v="${x[2]==null?'own':x[2]}" class="${(x[2]==null?![20,50,80].includes(+F.mixStk):+F.mixStk===x[2])?'on':''}">${x[1]}</button>`).join('');
  const tab=m==='life'?`<div class="cl-sec">Жизнь с капитала</div><div class="cl-grid cl-g2">${num('spend','Тратить в месяц, ₽ (в сегодняшних деньгах)',F.spend,'min="0" step="5000"')}${num('spendYears','Сколько лет тратить',F.spendYears,'min="1" max="50" step="1"')}</div>
      <div class="note">Тратить после накопления; траты растут вместе с инфляцией.</div>`
    :m==='goal'?`<div class="cl-sec">Цель по пассивному доходу</div><div class="cl-grid cl-g2">${num('goalAmt','Желаемый доход в месяц после налога, ₽',F.goalAmt,'min="0" step="5000"')}
      ${sel('goalMode','Что найти',[['contrib','нужное пополнение (срок задан)'],['years','нужный срок (пополнение задано)']],F.goalMode)}</div>
      <div class="cl-grid cl-g2">${sel('goalStrat','Стратегия для подбора',av.map(x=>[x[0],x[1]]),av.some(x=>x[0]===F.goalStrat)?F.goalStrat:'ofz')}</div>`:'';
  const multi=m!=='goal';
  return`<div class="cl-pre" id="cl-pre">${CL_PRESETS.map(x=>`<button type="button" class="cl-preset" data-clp="${x[0]}" ${x[0]==='mine'&&!(pf&&pf.value!=null)?'disabled title="нет данных о портфеле"':''}><b>${x[1]}</b><small>${x[2]}</small></button>`).join('')}</div>
  <div class="note" id="cl-prehint" style="display:none"></div>
  <div id="cl-form">
   <div class="cl-grid cl-g2">${num('start','Стартовый капитал, ₽',F.start,'min="0" step="10000"')}${num('monthly','Пополнение в месяц, ₽',F.monthly,'min="0" step="1000"')}</div>
   <label class="field"><span>Срок: <b id="cl-yv">${F.years}</b> лет</span><input id="cl-years" type="range" min="1" max="30" step="1" value="${F.years}"></label>
   ${pf&&pf.value!=null?`<div class="cl-row"><button type="button" class="btn ghost" id="cl-pf">Подставить мой портфель</button><span class="note">старт ${clRub(pf.value)}${pf.monthly!=null?`, пополнение ${clRub(pf.monthly)} в месяц`:''}</span></div>`:''}
   <div class="cl-sec">Главное</div>
   ${lever('acct','Счёт',[['plain','Обычный брокерский'],['iis3','ИИС-3 (вычет и льгота)']],F.acct)}
   ${lever('real','В деньгах',[['1','В ценах сегодня'],['0','Номинал']],F.real?'1':'0')}
   ${lever('scn','Сценарий ЦБ',[['cbr','Базовый'],['soft','Снижение ставки'],['hard','Жёсткая ДКП'],['own','Свой']],F.scn)}
   <label class="field" id="cl-ownkeybox" style="${F.scn==='own'?'':'display:none'}"><span>Ключевая ставка, %</span><input class="in" id="cl-ownKey" type="number" step="0.5" min="1" max="50" value="${esc(F.ownKey)}"></label>
   ${lever('idxMode','Пополнения',[['fix','Фикс ₽/мес'],['infl','Растут с инфляцией'],['own','Своя индексация']],F.idxMode)}
   <label class="field" id="cl-idxbox" style="${F.idxMode==='own'?'':'display:none'}"><span>Индексация пополнений, % в год</span><input class="in" id="cl-idx" type="number" min="0" max="50" step="0.5" value="${esc(F.idx)}"></label>
   <div id="cl-iisbox" style="${F.acct==='iis3'?'':'display:none'}"><div class="cl-grid cl-g2">${num('iisYear','Год открытия ИИС-3',F.iisYear,'min="2024" max="'+new Date().getFullYear()+'" step="1"')}
    ${sel('salRate','Ставка НДФЛ с вашей зарплаты',[[13,'13 %'],[15,'15 %'],[18,'18 %'],[20,'20 %'],[22,'22 %'],[0,'не плачу (ИП, самозанятый)']],F.salRate)}</div>
    ${num('salary','Официальный доход за год, ₽ (пусто — без ограничения вычета)',F.salary||'','min="0" step="10000" placeholder="не ограничивать"')}
    <div class="st-callout cl-iis-cap">Лимит вычета по ИИС-3: <b>52–88 тыс. ₽</b> в год (13–22 % от взносов до 400 тыс. ₽ в год, не больше уплаченного НДФЛ).</div></div>
   ${tab}
   <div class="cl-sec">${multi?'Во что вкладываем':'Стратегия'}</div>
   ${multi?`<div class="cl-chips" id="cl-strat">${chips}</div>`:`<div class="note">Стратегия выбирается выше, в «Цель по пассивному доходу».</div>`}
   <div class="cl-mixbox" id="cl-mixbox" style="${F.strat.mix||(!multi&&F.goalStrat==='mix')?'':'display:none'}"><div class="cl-lv"><span>Доля акций: <b id="cl-mixv">${F.mixStk}</b> %, облигаций: <b id="cl-mixb">${100-F.mixStk}</b> %</span><div class="seg" id="cl-mixpre">${mixRow}</div></div>
    <input id="cl-mixStk" type="range" min="0" max="100" step="5" value="${F.mixStk}" aria-label="Доля акций">
    ${sel('mixBond','Облигационная часть микса',bondOpts,F.mixBond)}</div>
   <div class="cl-grid" id="cl-ownbox" style="margin-top:12px;${F.strat.own||(!multi&&F.goalStrat==='own')?'':'display:none'}">${num('ownRate','Своя ставка, % годовых',F.ownRate,'step="0.5" min="0" max="100"')}</div>
   <details class="cl-adv" id="cl-adv" ${F.adv?'open':''}><summary>Дополнительно</summary>
    <div class="cl-sec">Налоги и счёт</div>
    <div class="cl-grid">${sw('reinvDed','Вложить вычет ИИС','возвращённый налог снова вкладывается',F.reinvDed)}
     ${sw('ldv','ЛДВ для фондов и акций','без налога на рост от 3 лет владения',F.ldv)}${sw('defaults','Учитывать дефолты','случайные дефолты выпусков (Монте-Карло), а не ежемесячная усушка',F.defaults)}</div>
    <div class="cl-sec">Допущения по акциям и валюте</div>
    <div class="cl-grid cl-g2">${num('stkDiv','Акции: дивиденды, % в год',F.stkDiv,'step="0.5" min="0" max="50" placeholder="'+st.div+'"')}${num('stkGrow','Акции: рост цены, % в год',F.stkGrow,'step="0.5" min="-20" max="50" placeholder="'+st.growth+'"')}
     ${num('fxWeak','Ослабление рубля, % в год',F.fxWeak,'step="0.5" min="-20" max="50" placeholder="'+fx.fx+'"')}${num('inflOvr','Инфляция, % в год',F.inflOvr,'step="0.5" min="0" max="50" placeholder="прогноз ЦБ"')}</div>
    <div class="cl-sec">Вклад, купоны, покупка бумаг</div>
    <div class="cl-grid cl-g2">${num('depSpread','Вклад: ключевая минус, п.п.',F.depSpread,'step="0.1" min="0" max="10"')}${sw('reinvest','Реинвестировать купоны','иначе копятся без дохода',F.reinvest)}
     ${sel('freq','Выплаты купонов',[[12,'раз в месяц'],[4,'раз в квартал'],[2,'раз в полгода']],F.freq)}${num('lot','Цена лота, ₽',F.lot,'min="0" step="100"')}
     ${sel('lotFund','Остаток, не хватающий на бумагу',[['fund','лежит в фонде ликвидности'],['wait','ждёт следующей покупки']],F.lotFund)}</div>
   </details>
  </div>`;
}
function pCalcPage(){
  const F=clLoadF();
  const ld=S.calcAcc!==S.account;if(ld)clLoad();
  const P=(!ld&&S.calcP)||clDefaultParams(),fb=!ld&&!S.calcP,m=clMode();
  const tabs=`<div class="row noprint"><div class="seg cl-tabs" role="tablist">${[['inv','Накопить капитал'],['life','Жизнь с капитала'],['goal','Подбор под цель']].map(([k,t])=>`<button role="tab" aria-selected="${k===m}" class="${k===m?'on':''}" onclick="cgSetMode('${k}')">${t}</button>`).join('')}</div></div>`;
  return`<div class="cl-page">${tabs}${ld?`<div class="card">${waitBox('Загружаю параметры рынка (ставки, доходности, ваш портфель)… пока расчёт идёт на значениях по умолчанию')}</div>`:''}${fb?`<div class="st-callout warn">Не удалось загрузить рыночные данные (${esc(S.calcErr||'нет ответа')}). Использованы значения по умолчанию, расчёт приблизителен.</div>`:''}
  <div class="cl-split"><aside class="card cl-side" aria-label="Параметры расчёта">${clForm(F,P)}</aside>
  <div class="cl-main"><div id="cl-out">${clTabOut()}</div>
  <div class="card"><h2>Как это считается</h2><div class="note">${clHowNote(F)}</div></div>
  <div class="note cl-disc">Модель упрощённая. Результаты — не прогноз и не индивидуальная инвестиционная рекомендация: реальные ставки, цены, налоги и дефолты будут отличаться.</div></div></div></div>`;
}
function clHowNote(F){return`Один движок на всех вкладках: шаг расчёта — месяц; взносы вносятся в конце месяца; налоговый год — календарный. Шкала НДФЛ для инвестиционных доходов (купоны, продажа бумаг, проценты по вкладам, дивиденды): 13 % до 2,4 млн ₽ дохода в год, 15 % с превышения.
   <b>Вклад</b>: ежемесячная капитализация по ставке «ключевая − ${f2(F.depSpread)} п.п.» по пути выбранного сценария. НДФЛ — с процентов за год сверх необлагаемой суммы (1 млн ₽ × максимальная ключевая ставка года); начисляется в конце года, а платится 1 декабря следующего года. Необлагаемая сумма общая на все вклады человека: если есть другие вклады, налог будет больше.
   <b>Фонд ликвидности</b>: ежедневное начисление приближено месячным по «ключевая − спред к ключевой»; налог только при продаже в конце срока. ЛДВ: паи старше 3 лет, лимит 3 млн ₽ × средневзвешенный срок владения этих паёв (при продаже ради налога самые старые паи уходят первыми); налог с прироста паёв, проданных ради уплаты налога, не считается.
   <b>Акции</b>: цена растёт на допущение «рост цены», дивиденды начисляются ежемесячно (налог раз в год, на ИИС — при закрытии) и реинвестируются; рост цены облагается при продаже, ЛДВ — как у паёв. <b>Флоатеры</b>: купон = ключевая + спред, цена около номинала. <b>Замещающие облигации</b>: купон в валюте, рубль слабеет на заданный процент в год, курсовая прибыль облагается при погашении или продаже.
   <b>ОФЗ, корпоративные, ВДО</b>: покупаем по текущей медианной доходности сегмента (без флоатеров, линкеров, бессрочных и субординированных выпусков), держим до погашения (срок ≈ медианная дюрация); погашенный номинал и купоны вкладываются по будущей доходности ≈ текущая + β × (ключевая в тот момент − ключевая сейчас), β = 0,6 для ОФЗ и 0,7 для остальных. Рыночная цена выпуска меняется с дюрацией: 1 − дюрация × (доходность сейчас − доходность покупки); к погашению она сходится к номиналу. Налог на брокерском счёте удерживается раз в год и при выводе денег в конце срока; берётся из свободных денег, а если их не хватает — продаётся часть облигаций по рыночной цене. На ИИС налог удерживается только при закрытии счёта.
   <b>ИИС-3</b>: срок освобождения зависит от года открытия (2024–2026 — 5 лет, 2027 — 6, 2028 — 7, 2029 — 8, 2030 — 9, с 2031 — 10); при выдержанном сроке налога с дохода до 30 млн ₽ нет, в том числе с пассивного дохода. Вычет — ставка вашего НДФЛ с зарплаты × взносы до 400 тыс. ₽ в год, но не больше уплаченного НДФЛ; лимита взносов 1 млн ₽ в год у ИИС-3 нет. Если закрыть счёт раньше срока, вычеты за время расчёта возвращаются, а доход облагается; вычеты, полученные до начала расчёта, не учитываются.
   <b>Дефолты и шоки</b>: основной расчёт идёт без случайных событий; в Монте-Карло каждый «транш» (покупка за месяц) с вероятностью сегмента обесценивается на 75 %, а ключевая ставка и рынок акций получают случайные шоки. <b>Смесь частей</b> («Микс», «Мой портфель»): доли поддерживаются распределением стартовой суммы и взносов, без продаж ради ребалансировки; «Мой портфель» — по вашим весам (облигации с вашей доходностью и дюрацией, акции, фонды ликвидности, деньги). <b>Своя ставка</b> — постоянная ставка с купонным налогом. Капитал в промежуточные месяцы показан за вычетом начисленного, но ещё не удержанного налога. Инфляция — прогноз Банка России, после его горизонта — последнее значение.`}
function clUpdate(){S.charts=[];const o=$('#cl-out');if(!o)return;o.innerHTML=clTabOut();mountCharts();clMcFill();if(typeof clDeepFill==='function')clDeepFill()}
function bindCalcInv(){
  const form=$('#cl-form');if(!form)return;const F=clLoadF(),P=clMkt();
  const rn=(id,d,lo,hi)=>{const e=$('#cl-'+id);if(!e)return d;let v=parseFloat(String(e.value).replace(',','.'));if(!isFinite(v))v=d;if(lo!=null)v=Math.max(lo,v);if(hi!=null)v=Math.min(hi,v);return v};
  const rs=(id,d)=>{const e=$('#cl-'+id);if(!e||String(e.value).trim()==='')return'';const v=parseFloat(String(e.value).replace(',','.'));return isFinite(v)?v:d};
  const ck=id=>{const e=$('#cl-'+id);return e?e.checked:false};
  const vl=id=>{const e=$('#cl-'+id);return e?e.value:''};
  const yr=new Date().getFullYear(),m=clMode();
  const read=()=>{
    F.start=rn('start',0,0);F.monthly=rn('monthly',0,0);F.idx=rn('idx',0,0,50);F.years=Math.round(rn('years',10,1,30));F.ownRate=rn('ownRate',15,0,100);
    F.reinvest=ck('reinvest');F.freq=+vl('freq')||4;F.lot=rn('lot',0,0);F.lotFund=vl('lotFund')||'fund';F.ownKey=rn('ownKey',12,1,50);
    F.iisYear=Math.round(rn('iisYear',yr,2024,yr));F.salRate=+vl('salRate');F.salary=rn('salary',0,0);F.reinvDed=ck('reinvDed');F.ldv=ck('ldv');F.defaults=ck('defaults');F.depSpread=rn('depSpread',1.5,0,10);
    F.mixStk=Math.round(rn('mixStk',50,0,100));F.mixBond=vl('mixBond')||'ofz';F.stkDiv=rs('stkDiv',0);F.stkGrow=rs('stkGrow',0);F.fxWeak=rs('fxWeak',0);F.inflOvr=rs('inflOvr',0);
    if(m==='life'){F.spend=rn('spend',0,0);F.spendYears=Math.round(rn('spendYears',30,1,50))}
    if(m==='goal'){F.goalAmt=rn('goalAmt',0,0);F.goalMode=vl('goalMode')==='years'?'years':'contrib';F.goalStrat=vl('goalStrat')||'ofz'}
    form.querySelectorAll('#cl-strat input').forEach(c=>{F.strat[c.dataset.s]=c.checked?1:0});
    $('#cl-yv').textContent=F.years;$('#cl-mixv').textContent=F.mixStk;$('#cl-mixb').textContent=100-F.mixStk;
    const mixOn=m==='goal'?F.goalStrat==='mix':!!F.strat.mix,ownOn=m==='goal'?F.goalStrat==='own':!!F.strat.own;
    $('#cl-mixbox').style.display=mixOn?'':'none';$('#cl-ownbox').style.display=ownOn?'':'none';
    $('#cl-ownkeybox').style.display=F.scn==='own'?'':'none';$('#cl-idxbox').style.display=F.idxMode==='own'?'':'none';$('#cl-iisbox').style.display=F.acct==='iis3'?'':'none';
    $('#cl-mixpre').querySelectorAll('button').forEach(b=>b.classList.toggle('on',b.dataset.v==='own'?![20,50,80].includes(F.mixStk):+b.dataset.v===F.mixStk));
    clSave();clUpdate();
  };
  form.addEventListener('input',read);form.addEventListener('change',read);
  const ad=$('#cl-adv');if(ad)ad.addEventListener('toggle',()=>{F.adv=ad.open;clSave()});
  [['acct',v=>{F.acct=v}],['real',v=>{F.real=v==='1'}],['scn',v=>{F.scn=v}],['idxMode',v=>{F.idxMode=v}]].forEach(([id,fn])=>{const s=$('#cl-'+id);if(s)s.onclick=e=>{const b=e.target.closest('button');if(!b)return;
    s.querySelectorAll('button').forEach(x=>{x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',x===b?'true':'false')});fn(b.dataset.v);read()}});
  const mp=$('#cl-mixpre');if(mp)mp.onclick=e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.v!=='own')$('#cl-mixStk').value=b.dataset.v;read()};
  const o=$('#cl-out');
  if(o){const pick=v=>{F.view=v;clSave();clUpdate()};
    o.onchange=e=>{if(e.target.id==='cl-view')pick(e.target.value);else if(typeof clDeepChange==='function')clDeepChange(e)};
    o.onclick=e=>{const l=e.target.closest('tr[data-lf]');if(l){F.lifeView=l.dataset.lf;clSave();clUpdate();return}
      const t=e.target.closest('tr[data-s]');if(t&&o.querySelectorAll('tr[data-s]').length>1)pick(t.dataset.s);else if(typeof clDeepClick==='function')clDeepClick(e)}}
  clMcFill();if(typeof clDeepFill==='function')clDeepFill();
  const b=$('#cl-pf');if(b)b.onclick=()=>{const pf=P.portfolio;if(!pf)return;if(pf.value!=null)F.start=Math.round(pf.value);if(pf.monthly!=null)F.monthly=Math.round(pf.monthly);F.strat.pf=1;clSave();render()};
  const pr=$('#cl-pre');if(pr)pr.onclick=e=>{
    const x=e.target.closest('[data-clp]');if(!x||x.disabled)return;
    const k=x.dataset.clp,pf=P.portfolio;let hint='';
    if(k==='cushion'){Object.assign(F,{start:300000,monthly:25000,years:1,acct:'plain',idxMode:'fix',strat:{dep:1,fund:1,ofz:1}})}
    if(k==='house'){Object.assign(F,{start:500000,monthly:35000,years:5,acct:'iis3',idxMode:'own',idx:5,strat:{ofz:1,aaa:1,fund:1},goalStrat:'ofz'})}
    if(k==='passive100'){Object.assign(F,{start:300000,monthly:30000,years:15,acct:'iis3',idxMode:'infl',goalAmt:100000,goalMode:'contrib',goalStrat:'mix',mixStk:30,mixBond:'ofz',strat:{mix:1,ofz:1,stk:1}});
      hint=m==='goal'?'':'Цель — 100 000 ₽ в месяц после налога — задана; результат подбора на вкладке «Подбор под цель». <a href="#" onclick="cgSetMode(\'goal\');return false">Открыть</a>'}
    if(k==='mine'&&pf){if(pf.value!=null)F.start=Math.round(pf.value);if(pf.monthly!=null)F.monthly=Math.round(pf.monthly);F.strat={pf:1,ofz:1,mix:1};F.goalStrat='pf'}
    clSave();S._clHint=hint;render();
  };
  if(S._clHint){const h=$('#cl-prehint');if(h){h.innerHTML=S._clHint;h.style.display=''}S._clHint=''}
}
function pCalc(){return pCalcPage()}
function bindCalc(){bindCalcInv()}
