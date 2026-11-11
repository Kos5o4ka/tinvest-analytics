/* калькулятор инвестиций */
/* ── Чистая часть: модель (без DOM, считается на клиенте) ── */
const CL_BR=[[2.4e6,.13],[5e6,.15],[20e6,.18],[50e6,.20],[Infinity,.22]];   /* шкала НДФЛ: 13 % до 2,4 млн ₽ в год, далее 15/18/20/22 % с части дохода */
const CL_STR=[['dep','Вклад','#8a93a6'],['fund','Фонд ликвидности','#19a070'],['ofz','ОФЗ','#3987e5'],['aaa','Корпоративные AAA','#7ab4f5'],['aa','Корпоративные AA','#9085e9'],
  ['a','Корпоративные A','#c98500'],['hy','ВДО (BB и ниже)','#e66767'],['pf','Мой портфель','#d55181'],['own','Своя ставка','#d95926']];
const CL_BETA={ofz:.6,aaa:.7,aa:.7,a:.7,hy:.7};
const CL_ACC=[['plain','Обычный брокерский счёт'],['iisA','ИИС типа А (вычет с взносов)'],['iisB','ИИС типа Б (доход без налога)'],['iis3','ИИС-3 (вычет и освобождение дохода)']];
function clNdfl(b){if(!(b>0))return 0;let t=0,lo=0;for(const[h,r]of CL_BR){if(b>lo)t+=(Math.min(b,h)-lo)*r;lo=h;if(b<=h)break}return t}
function clTaxInc(inc,x){return clNdfl(inc+x)-clNdfl(inc)}
/* значения рынка по умолчанию, если сервер не ответил */
function clDefaultParams(){
  const k=16;return{key_rate:{current:k,source:'условное значение',estimate:true,path:[]},inflation:{yearly:[],default:4,estimate:true},
    segments:{ofz:{name:'ОФЗ',yield:k-.5,dur:4,loss:0,estimate:true},aaa:{name:'Корпоративные AAA',yield:k+.5,dur:2.5,loss:.04,estimate:true},aa:{name:'Корпоративные AA',yield:k+1.5,dur:2.5,loss:.15,estimate:true},
    a:{name:'Корпоративные A',yield:k+3,dur:2,loss:.6,estimate:true},hy:{name:'ВДО (BB и ниже)',yield:k+8,dur:1.5,loss:3.2,estimate:true}},
    lqdt:{yield:k-.7,estimate:true,spread:.7},deposit:{spread:1.5},portfolio:null,fallback:true};
}
/* окружение: путь ключевой ставки по сценарию, дефлятор, ставка фонда */
function clEnv(P,F,startDate){
  const sd=startDate||new Date(),y0=sd.getFullYear(),m0=sd.getMonth(),M=721;
  const path=(P.key_rate.path||[]).map(x=>+x[1]).filter(x=>isFinite(x)),kr0=+P.key_rate.current||16;
  const base=k=>path.length?path[Math.min(k,path.length-1)]:kr0;
  const key=k=>{const b=base(k);
    if(F.scn==='hard')return b+2;if(F.scn==='soft')return Math.min(b,Math.max(b-2,4));if(F.scn==='own')return +F.ownKey||kr0;return b};
  const iy={};(P.inflation.yearly||[]).forEach(x=>{iy[x.year]=x.mid});
  const iyears=Object.keys(iy).map(Number),last=iyears.length?iy[Math.max(...iyears)]:(P.inflation.default!=null?P.inflation.default:4);
  const D=[1];for(let k=1;k<M;k++){const yr=y0+Math.floor((m0+k-1)/12),i=iy[yr]!=null?iy[yr]:last;D.push(D[k-1]*Math.pow(1+i/100,1/12))}
  const lq=P.lqdt||{yield:kr0-.7,estimate:true,spread:.7};
  const fsp=lq.estimate?(lq.spread!=null?lq.spread:.7):Math.max(0,Math.min(3,kr0-lq.yield));
  const fundRate=k=>(!lq.estimate&&k<2)?lq.yield:Math.max(key(k)-fsp,.1);
  const dsp=F.depSpread!=null?+F.depSpread:(P.deposit?P.deposit.spread:1.5);
  return{key,kr0,D,fundRate,depRate:k=>Math.max(key(k)-dsp,.1),y0,m0,infl:last,iy};
}
function clContrib(p,k){return k===0?p.start:(k<=p.months?p.monthly*Math.pow(1+p.idx/100,Math.floor((k-1)/12)):0)}
function clAccInfo(p){
  const a=p.acct,N=p.months;
  return{ded:a==='iisA'||a==='iis3',exempt:(a==='iisB'&&N>=36)||(a==='iis3'&&N>=60),cap:a==='iis3'?30e6:Infinity,iis:a!=='plain'};
}
/* вычет ИИС: сумма и точка начисления (конец года) */
function clRefunds(p,ai){
  const N=p.months,R=new Array(N+1).fill(0);if(!ai.ded)return R;
  const yc={};for(let k=0;k<=N;k++){const y=k===0?0:Math.floor((k-1)/12);yc[y]=(yc[y]||0)+clContrib(p,k)}
  for(const y in yc){const pt=Math.min(12*(+y+1),N);R[pt]+=Math.min(yc[y],400e3)*.13}
  return R;
}
function clIrr(fl){          /* fl[k] — поток в месяц k; возвращает годовую эффективную доходность, % */
  let lo=-.5,hi=1;const f=r=>{let s=0;for(let k=0;k<fl.length;k++)s+=fl[k]/Math.pow(1+r,k);return s};
  if(!fl.some(x=>x<0)||!fl.some(x=>x>0))return null;
  if(f(lo)*f(hi)>0)return null;
  for(let i=0;i<80;i++){const m=(lo+hi)/2;if(f(lo)*f(m)<=0)hi=m;else lo=m}
  return(Math.pow(1+(lo+hi)/2,12)-1)*100;
}
function clFinish(r,p,env,yEnd,lossEnd){
  const N=p.months,capN=r.cap[N];
  const inc=Math.max(0,capN*(yEnd-lossEnd)/100);
  r.passive=(inc-clNdfl(inc))/12;
  r.passiveReal=r.passive/env.D[N];r.final=capN;r.finalReal=capN/env.D[N];
  r.income=capN-r.deposited-r.deductions;
  const fl=new Array(N+1).fill(0);for(let k=0;k<=N;k++)fl[k]-=clContrib(p,k);fl[N]+=capN;r.xirr=clIrr(fl);
  r.yEnd=yEnd;return r;
}
/* Вклад: ежемесячная капитализация; НДФЛ с процентов сверх необлагаемого порога (1 млн ₽ × макс. ключевая ставка года) */
function clSimDep(p,env){
  const N=p.months;let B=0,dep=0,iy=0,mk=0;const cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[]};
  for(let k=0;k<=N;k++){
    if(k>0){const rt=env.depRate(k-1);const g=B*rt/1200;B+=g;iy+=g;mk=Math.max(mk,env.key(k-1));
      if(k%12===0||k===N){const thr=1e6*mk/100,tx=clNdfl(Math.max(0,iy-thr));B-=tx;r.taxes+=tx;iy=0;mk=0}}
    const c=clContrib(p,k);B+=c;dep+=c;cap.push(B);
  }
  r.deposited=dep;return clFinish(r,p,env,env.depRate(Math.max(N-1,0)),0);
}
/* Фонд ликвидности: накопление пая, налог только при продаже (или ЛДВ / ИИС) */
function clSimFund(p,env){
  const N=p.months,ai=clAccInfo(p),RF=clRefunds(p,ai);const G=[1];
  for(let k=0;k<N;k++)G.push(G[k]*(1+env.fundRate(k)/1200));
  const lots=[],cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[]};let idle=0;
  const saleTax=k=>{
    let gain=0,eg=0,old=Infinity,val=0;
    for(const l of lots){const v=l.amt*G[k]/G[l.k0],g=v-l.amt;gain+=g;if(p.ldv&&!ai.iis&&k-l.k0>=36){eg+=g;old=Math.min(old,l.k0)}}
    let taxable=gain;
    if(ai.iis&&ai.exempt)taxable=Math.max(0,gain-ai.cap);
    else if(p.ldv&&!ai.iis&&eg>0)taxable=Math.max(0,gain-Math.min(eg,3e6*(k-old)/12));
    return clNdfl(taxable);
  };
  for(let k=0;k<=N;k++){
    if(RF[k]>0){if(p.reinvDed)lots.push({k0:k,amt:RF[k]});else idle+=RF[k];r.deductions+=RF[k]}
    const c=clContrib(p,k);if(c>0){lots.push({k0:k,amt:c});r.deposited+=c}
    let v=idle;for(const l of lots)v+=l.amt*G[k]/G[l.k0];
    cap.push(v-saleTax(k));
  }
  r.taxes=saleTax(N);
  return clFinish(r,p,env,env.fundRate(Math.max(N-1,0)),0);
}
/* Облигации с фиксированным купоном (держим до погашения) и «ставка + купонный налог» */
function clSimBond(id,p,env,seg){
  const N=p.months,ai=clAccInfo(p),RF=clRefunds(p,ai),f=p.freq,per=Math.max(1,Math.round(12/f));
  const y0=seg.yield,beta=seg.beta||0,matM=seg.dur>0?Math.max(Math.round(seg.dur*12),per):Infinity,loss=p.defaults?(seg.loss||0):0;
  const ynew=k=>k===0?y0:Math.max(.5,y0+beta*(env.key(k)-env.kr0));
  const tr=[],cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[]},incY={};
  let cashInv=0,idle=0,pot=0,incTot=0;const useLot=p.lot>1;
  for(let k=0;k<=N;k++){
    if(k>0){
      const yi=Math.floor((k-1)/12);incY[yi]=incY[yi]||0;
      if(pot>0){const g=pot*env.fundRate(k-1)/1200,tx=clTaxInc(incY[yi],g);incY[yi]+=g;incTot+=g;r.taxes+=tx;pot+=g-tx}
      let coup=0,prin=0;
      for(let i=tr.length-1;i>=0;i--){const t=tr[i];
        if(loss)t.amt*=1-loss/1200;
        if(k>t.k0&&k<=t.mat&&(k-t.k0)%per===0)coup+=t.amt*t.y/100/f;
        if(k===t.mat){prin+=t.amt;tr.splice(i,1)}}
      const tx=clTaxInc(incY[yi],coup);incY[yi]+=coup;incTot+=coup;r.taxes+=tx;
      if(p.reinvest)cashInv+=coup-tx;else idle+=coup-tx;
      cashInv+=prin;
    }
    if(RF[k]>0){if(p.reinvDed)cashInv+=RF[k];else idle+=RF[k];r.deductions+=RF[k]}
    const c=clContrib(p,k);cashInv+=c;r.deposited+=c;
    const avail=cashInv+pot;
    if(avail>0.005){const amt=useLot?Math.floor(avail/p.lot+1e-9)*p.lot:avail;
      if(amt>0)tr.push({k0:k,amt,y:ynew(k),mat:k+matM});
      const rem=avail-amt;if(p.lotFund){cashInv=0;pot=rem}else{cashInv=rem;pot=0}}
    let v=idle+cashInv+pot;for(const t of tr)v+=t.amt;cap.push(v);
  }
  /* ИИС Б / ИИС-3: налог, удержанный в течение срока, возвращается при закрытии (для ИИС-3 — до 30 млн ₽ дохода) */
  if(ai.iis&&ai.exempt&&r.taxes>0){const share=incTot>ai.cap?ai.cap/incTot:1,rf=r.taxes*share;cap[N]+=rf;r.deductions+=rf}
  return clFinish(r,p,env,ynew(N),loss);
}
function clSegOf(id,P,F){
  if(id==='pf'){const pf=P.portfolio;return{yield:pf&&pf.irr!=null?pf.irr:10,dur:0,beta:0,loss:0}}
  if(id==='own')return{yield:+F.ownRate||0,dur:0,beta:0,loss:0};
  const s=P.segments[id];return{yield:s.yield,dur:s.dur,beta:CL_BETA[id]||.7,loss:s.loss};
}
function clSim(id,p,P,env,F){
  if(id==='dep')return clSimDep(p,env);
  if(id==='fund')return clSimFund(p,env);
  return clSimBond(id,p,env,clSegOf(id,P,F));
}
function clParams(F,months){
  return{start:+F.start||0,monthly:+F.monthly||0,idx:+F.idx||0,months:months||Math.round((+F.years||1)*12),acct:F.acct,reinvest:!!F.reinvest,freq:+F.freq||12,
    lot:+F.lot||0,lotFund:F.lotFund==='fund',reinvDed:!!F.reinvDed,ldv:!!F.ldv,defaults:!!F.defaults};
}
/* Цель: нужное ежемесячное пополнение при заданном сроке или нужный срок при заданном пополнении (бисекция) */
function clGoal(F,P,env,sid){
  const T=+F.goalAmt||0,pas=(months,monthly)=>{const p=clParams(F,months);p.monthly=monthly;return clSim(sid,p,P,env,F).passiveReal};
  if(F.goalMode==='years'){
    const m=clParams(F).monthly;let lo=1,hi=600;
    if(pas(hi,m)<T)return{ok:false};
    if(pas(lo,m)>=T)return{ok:true,months:1};
    while(hi-lo>1){const mid=(lo+hi)>>1;if(pas(mid,m)>=T)hi=mid;else lo=mid}
    return{ok:true,months:hi};
  }
  const N=clParams(F).months;let lo=0,hi=1000;
  if(pas(N,0)>=T)return{ok:true,monthly:0};
  while(pas(N,hi)<T&&hi<1e9)hi*=2;
  if(pas(N,hi)<T)return{ok:false};
  for(let i=0;i<40;i++){const mid=(lo+hi)/2;if(pas(N,mid)>=T)hi=mid;else lo=mid}
  return{ok:true,monthly:hi};
}

/* ── Интерфейс ── */
const CL_DEF={start:500000,monthly:20000,idx:5,years:10,strat:{dep:1,fund:1,ofz:1,aa:1,a:1},ownRate:15,reinvest:true,freq:4,lot:1000,lotFund:'fund',scn:'cbr',ownKey:12,
  acct:'plain',reinvDed:true,ldv:true,defaults:true,real:true,depSpread:1.5,goalOn:false,goalAmt:100000,goalMode:'contrib',goalStrat:'ofz'};
let CL_F=null;
function clLoadF(){
  if(CL_F)return CL_F;
  const F=JSON.parse(JSON.stringify(CL_DEF));
  try{const s=JSON.parse(localStorage.getItem('ta_calc')||'null');
    if(s&&typeof s==='object')for(const k in F){if(s[k]!==undefined&&typeof s[k]===typeof F[k])F[k]=k==='strat'?Object.assign({},s[k]):s[k]}}catch(e){}
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
function clAvail(P){return CL_STR.filter(s=>s[0]!=='pf'||(P.portfolio&&P.portfolio.irr!=null))}
function clRun(F,P){
  const env=clEnv(P,F),p=clParams(F),N=p.months,ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  const res=ids.map(id=>{const s=CL_STR.find(x=>x[0]===id),r=clSim(id,p,P,env,F);r.id=id;r.name=s[1];r.color=s[2];return r});
  return{env,p,N,res};
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
  return`<div class="tbl"><table><thead><tr><th class="l">Параметр</th><th>Значение</th><th class="l">Источник / примечание</th></tr></thead><tbody>${
    rows.map(r=>`<tr><td class="l">${r[0]}</td><td class="num">${r[1]}</td><td class="l mu">${r[2]}</td></tr>`).join('')}</tbody></table></div>`;
}
function clOut(){
  const F=clLoadF(),P=(S.calcAcc===S.account&&S.calcP)||clDefaultParams();
  const ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  if(!ids.length)return`<div class="card empty">Выберите хотя бы одну стратегию для сравнения</div>`;
  const run=clRun(F,P),{env,N,res,p}=run,real=F.real;
  const labels=[],tips=[];
  for(let k=0;k<=N;k++){const d=new Date(env.y0,env.m0+k,1),mm=String(d.getMonth()+1).padStart(2,'0');labels.push(mm+'.'+d.getFullYear());tips.push(mm+'.'+d.getFullYear()+' · '+(k?clYM(k):'сейчас'))}
  const cd=[];let acc=0;for(let k=0;k<=N;k++){acc+=real?clContrib(p,k)/env.D[k]:clContrib(p,k);cd.push(acc)}
  const series=res.map(r=>({n:r.name,c:r.color,v:r.cap.map((v,k)=>real?v/env.D[k]:v)}));
  series.push({n:'Внесено своих денег',c:'#9aa3b5',dash:1,w:1.6,v:cd});
  chart('cl-chart',line,{h:320,series,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных'});
  const best=res.slice().sort((a,b)=>b.finalReal-a.finalReal)[0],dep=res[0].deposited,defl=env.D[N];
  const kp=`<div class="g g4">${kpi('Внесено своих денег',clRub(dep),'за '+clYM(N),null,S1)}
    ${kpi('Лучший итог',clRub(real?best.finalReal:best.final),esc(best.name)+(real?' · в сегодняшних деньгах':' · номинал'),'pos',S3)}
    ${kpi('Пассивный доход в месяц',clRub(real?best.passiveReal:best.passive),'после налога, '+esc(best.name),null,S4)}
    ${kpi('Удорожание цен за срок','×'+f2(defl),'1 ₽ через '+clYM(N)+' ≈ '+f2(1/defl)+' ₽ сегодня',null,S8)}</div>`;
  const th=['Стратегия','Итоговый капитал','Внесено','Получено дохода','Уплачено налогов','Вычеты и возвраты ИИС','Капитал в сегодняшних деньгах','Пассивный доход в месяц (после налога)','Эффективная годовая доходность'];
  const rows=res.map(r=>`<tr><td class="l"><i class="cl-dot" style="background:${r.color}"></i>${esc(r.name)}</td><td class="num"><b>${clRub(r.final)}</b></td><td class="num">${clRub(r.deposited)}</td>
    <td class="num ${cls(r.income)}">${clRub(r.income)}</td><td class="num">${clRub(r.taxes)}</td><td class="num">${r.deductions>0?clRub(r.deductions):'—'}</td><td class="num"><b>${clRub(r.finalReal)}</b></td>
    <td class="num">${clRub(r.passive)}<br><small class="mu">${clRub(r.passiveReal)} сегодня</small></td><td class="num">${r.xirr==null?'—':pctp(r.xirr,1)}</td></tr>`).join('');
  const tbl=`<div class="card"><h2>Сравнение стратегий<span class="sp">через ${clYM(N)}</span></h2><div class="tbl"><table><thead><tr>${th.map((t,i)=>`<th class="${i?'':'l'}">${t}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="note" style="margin-top:10px">«Итоговый капитал» — если закрыть позиции в конце срока: с уже удержанными налогами и (для фонда ликвидности) налогом при продаже. «Эффективная годовая доходность» — XIRR взносов против итога (номинальная, без учёта инфляции). «Получено дохода» = итог − внесено − вычеты.</div></div>`;
  const warn=[];
  if(F.acct!=='plain'){
    if(res.some(r=>r.id==='dep'))warn.push('Вклад лежит в банке, а не на ИИС: вычет и льготы ИИС к нему не применяются, налог считается как на обычном счёте.');
    if((p.start+p.monthly*12)>1e6)warn.push('Взносы на ИИС ограничены 1 млн ₽ в год: калькулятор этот лимит не проверяет, проверьте свои суммы.');
    if(F.acct==='iisB'&&N<36)warn.push('Освобождение дохода на ИИС типа Б действует при сроке от 3 лет: при меньшем сроке налог не возвращается.');
    if(F.acct==='iis3'&&N<60)warn.push('ИИС-3: освобождение дохода (до 30 млн ₽) принято при сроке владения от 5 лет; при меньшем сроке налог не возвращается.');
    if(F.acct==='iis3'&&N>=60)warn.push('Допущение ИИС-3: минимальный срок для освобождения дохода принят равным 5 годам, лимит освобождаемого дохода 30 млн ₽; вычет считается как на ИИС типа А (13 % от взносов до 400 тыс. ₽ в год).');
  }
  if(F.acct==='plain'&&res.some(r=>r.id==='fund')&&F.ldv)warn.push('ЛДВ для фонда ликвидности: рост пая без налога при владении 3 года и более, лимит 3 млн ₽ × число лет. Каждое пополнение учитывается отдельно по сроку владения.');
  if(P.portfolio==null&&F.strat.pf)warn.push('Нет данных о портфеле — «Мой портфель» недоступен.');
  const wn=warn.length?`<div class="note" style="margin-top:12px">${warn.map(w=>'• '+esc(w)).join('<br>')}</div>`:'';
  return`${kp}<div class="card"><h2>Рост капитала<span class="sp">${real?'в сегодняшних деньгах (с поправкой на инфляцию)':'в номинальных рублях'}</span></h2><div id="cl-chart" class="chart"></div>${wn}</div>${tbl}${clGoalHtml(F,P,run)}
    <div class="card"><h2>Что заложено в расчёт</h2>${clSegTable(P,F,env)}</div>`;
}
function clGoalHtml(F,P,run){
  if(!F.goalOn)return'';
  const ids=run.res.map(r=>r.id);if(!ids.length)return'';
  const sid=ids.includes(F.goalStrat)?F.goalStrat:ids[0],s=CL_STR.find(x=>x[0]===sid),g=clGoal(F,P,run.env,sid);
  let t;
  if(!g.ok)t=`Для стратегии «${esc(s[1])}» цель ${clRub(F.goalAmt)} в месяц ${F.goalMode==='years'?'недостижима и за 50 лет при таком пополнении':'недостижима при заданном сроке даже при очень больших пополнениях'}.`;
  else if(F.goalMode==='years')t=g.months<=1?`Цель ${clRub(F.goalAmt)} в месяц достигается сразу: стартовой суммы достаточно.`:
    `Чтобы получать ${clRub(F.goalAmt)} в месяц (в сегодняшних деньгах, после налога) на стратегии «${esc(s[1])}», при пополнении ${clRub(F.monthly)} в месяц понадобится около <b>${clYM(g.months)}</b>.`;
  else t=g.monthly<=0?`Цель ${clRub(F.goalAmt)} в месяц за ${clYM(run.N)} достигается и без ежемесячных пополнений: хватает стартовой суммы.`:
    `Чтобы через ${clYM(run.N)} получать ${clRub(F.goalAmt)} в месяц (в сегодняшних деньгах, после налога) на стратегии «${esc(s[1])}», нужно пополнять примерно <b>${clRub(g.monthly)}</b> в месяц (с ежегодной индексацией ${f2(F.idx)} %).`;
  return`<div class="card cl-goal"><h2>Цель: пассивный доход</h2><div class="cl-ans">${t}</div><div class="note" style="margin-top:8px">Пассивный доход — это проценты или купоны, которые приносит накопленный капитал в год, делённые на 12, после налога. Пересчитывается в сегодняшние деньги по прогнозу инфляции.</div></div>`;
}
function pCalc(){
  const F=clLoadF();
  const ld=S.calcAcc!==S.account;if(ld)clLoad();
  const P=(!ld&&S.calcP)||clDefaultParams(),pf=P.portfolio,fb=!ld&&!S.calcP;
  const num=(id,l,v,o)=>`<label class="field"><span>${l}</span><input class="in" id="cl-${id}" type="number" inputmode="decimal" value="${esc(v)}" ${o||''}></label>`;
  const sw=(id,t,sm,on)=>`<label class="sw"><input type="checkbox" id="cl-${id}" ${on?'checked':''}><i></i><div><b>${t}</b><small>${sm}</small></div></label>`;
  const sel=(id,l,opts,v)=>`<label class="field"><span>${l}</span><select class="in" id="cl-${id}">${opts.map(o=>`<option value="${o[0]}" ${String(o[0])===String(v)?'selected':''}>${o[1]}</option>`).join('')}</select></label>`;
  const seg=(id,opts,v)=>`<div class="seg" id="cl-${id}">${opts.map(o=>`<button data-v="${o[0]}" class="${String(o[0])===String(v)?'on':''}">${o[1]}</button>`).join('')}</div>`;
  const chips=clAvail(P).map(s=>`<label class="cl-chip"><input type="checkbox" data-s="${s[0]}" ${F.strat[s[0]]?'checked':''}><span><i style="background:${s[2]}"></i>${s[1]}</span></label>`).join('');
  const goalOpts=clAvail(P).filter(s=>F.strat[s[0]]).map(s=>[s[0],s[1]]);
  return`<div class="cl-page">${ld?`<div class="card">${waitBox('Загружаю параметры рынка (ставки, доходности, ваш портфель)… пока расчёт идёт на значениях по умолчанию')}</div>`:''}${fb?`<div class="msg err">Не удалось загрузить рыночные данные (${esc(S.calcErr||'нет ответа')}). Использованы значения по умолчанию, расчёт приблизителен.</div>`:''}
  <div class="card"><h2>Параметры<span class="sp">пересчёт мгновенный</span></h2><div id="cl-form">
   <div class="cl-grid">${num('start','Стартовая сумма, ₽',F.start,'min="0" step="10000"')}${num('monthly','Пополнение в месяц, ₽',F.monthly,'min="0" step="1000"')}
    ${num('idx','Ежегодная индексация пополнений, %',F.idx,'min="0" max="50" step="0.5"')}
    <label class="field"><span>Срок: <b id="cl-yv">${F.years}</b> лет</span><input id="cl-years" type="range" min="1" max="30" step="1" value="${F.years}"></label></div>
   ${pf&&pf.value!=null?`<div class="cl-row"><button class="btn ghost" id="cl-pf">Подставить мой портфель</button><span class="note">старт ${clRub(pf.value)}${pf.monthly!=null?`, пополнение ${clRub(pf.monthly)} в месяц (среднее за 12 мес.)`:''}</span></div>`:''}
   <div class="cl-sec">Что сравниваем</div><div class="cl-chips" id="cl-strat">${chips}</div>
   <div class="cl-grid" id="cl-ownbox" style="${F.strat.own?'':'display:none'}">${num('ownRate','Своя ставка, % годовых',F.ownRate,'step="0.5" min="0" max="100"')}</div>
   <div class="cl-sec">Облигации и реинвестирование</div>
   <div class="cl-grid">${sw('reinvest','Реинвестировать купоны','иначе купоны копятся без дохода',F.reinvest)}${sel('freq','Выплаты купонов',[[12,'12 раз в год (раз в месяц)'],[4,'4 раза в год (раз в квартал)'],[2,'2 раза в год (раз в полгода)']],F.freq)}
    ${num('lot','Цена лота (покупаем целыми бумагами), ₽',F.lot,'min="0" step="100"')}${sel('lotFund','Остаток, не хватающий на бумагу',[['fund','лежит в фонде ликвидности'],['wait','ждёт следующей покупки']],F.lotFund)}</div>
   <div class="cl-sec">Ключевая ставка</div>
   <div class="cl-row">${seg('scn',[['cbr','Прогноз ЦБ'],['hard','Жёсткий (+2 п.п.)'],['soft','Мягкий (−2 п.п.)'],['own','Своя постоянная']],F.scn)}
    <label class="field" id="cl-ownkeybox" style="${F.scn==='own'?'':'display:none'}"><span>Ставка, %</span><input class="in" id="cl-ownKey" type="number" step="0.5" min="1" max="50" value="${esc(F.ownKey)}" style="width:110px"></label></div>
   <div class="cl-sec">Налоги и поправки</div>
   <div class="cl-grid">${sel('acct','Тип счёта',CL_ACC,F.acct)}${sw('reinvDed','Реинвестировать вычет ИИС','возвращённый налог снова вкладывается',F.reinvDed)}
    ${sw('ldv','ЛДВ для фонда ликвидности','без налога на рост пая при владении от 3 лет',F.ldv)}${sw('defaults','Учитывать дефолты','вычитаем ожидаемые потери сегмента каждый год',F.defaults)}
    ${num('depSpread','Вклад: ставка = ключевая минус, п.п.',F.depSpread,'step="0.1" min="0" max="10"')}</div>
   <div class="cl-sec">Как показывать</div>
   <div class="cl-row">${seg('real',[['1','В сегодняшних деньгах'],['0','Номинал']],F.real?'1':'0')}</div>
   <div class="cl-sec">Цель</div>
   <div class="cl-grid">${sw('goalOn','Режим цели','«Хочу пассивный доход N ₽ в месяц»',F.goalOn)}
    <div id="cl-goalbox" class="cl-grid" style="${F.goalOn?'':'display:none'}">${num('goalAmt','Желаемый доход в месяц, ₽ (в сегодняшних деньгах)',F.goalAmt,'min="0" step="5000"')}
     ${sel('goalMode','Что найти',[['contrib','нужное пополнение (срок задан)'],['years','нужный срок (пополнение задано)']],F.goalMode)}
     <label class="field"><span>Стратегия</span><select class="in" id="cl-goalStrat">${goalOpts.map(o=>`<option value="${o[0]}" ${o[0]===F.goalStrat?'selected':''}>${o[1]}</option>`).join('')}</select></label></div></div>
  </div></div>
  <div id="cl-out">${clOut()}</div>
  <div class="card"><h2>Как это считается</h2><div class="note">Шаг расчёта — месяц; взносы вносятся в конце месяца. <b>Вклад</b>: ежемесячная капитализация по ставке «ключевая − ${f2(F.depSpread)} п.п.» по пути выбранного сценария; НДФЛ — с процентов сверх необлагаемого порога (1 млн ₽ × максимальная ключевая ставка года).
   <b>Фонд ликвидности</b>: ежедневное начисление приближено месячным по «ключевая − спред к ключевой»; налог только при продаже в конце срока (или ЛДВ / ИИС).
   <b>ОФЗ, корпоративные, ВДО</b>: покупаем по текущей медианной доходности сегмента, держим до погашения (срок ≈ медианная дюрация), купоны по этой доходности; погашенный номинал и купоны вкладываются по будущей доходности ≈ текущая + β × (ключевая в тот момент − ключевая сейчас), β = 0,6 для ОФЗ и 0,7 для остальных. Налог с купонов удерживается при каждой выплате. Переоценка цены облигаций при удержании до погашения не учитывается; на конец срока позиции считаются по номиналу.
   <b>Мой портфель</b>: доходность облигаций портфеля (IRR) используется как ставка; <b>Своя ставка</b> — постоянная ставка с купонным налогом. Налоговый год считается от начала расчёта, шкала НДФЛ: 13 % до 2,4 млн ₽ дохода в год, дальше 15 % (и по шкале 18/20/22 % для более крупных сумм). Инфляция — прогноз Банка России, после его горизонта — последнее значение.</div></div>
  <div class="note cl-disc">Модель упрощённая. Результаты — не прогноз и не индивидуальная инвестиционная рекомендация: реальные ставки, цены, налоги и дефолты будут отличаться.</div></div>`;
}
function clUpdate(){
  S.charts=[];const o=$('#cl-out');if(!o)return;o.innerHTML=clOut();mountCharts();
  const g=$('#cl-goalStrat');if(g){const F=clLoadF(),P=(S.calcAcc===S.account&&S.calcP)||clDefaultParams(),opts=clAvail(P).filter(s=>F.strat[s[0]]);
    g.innerHTML=opts.map(s=>`<option value="${s[0]}" ${s[0]===F.goalStrat?'selected':''}>${s[1]}</option>`).join('')}
}
function bindCalc(){
  const form=$('#cl-form');if(!form)return;const F=clLoadF(),P=(S.calcAcc===S.account&&S.calcP)||clDefaultParams();
  const rn=(id,d,lo,hi)=>{const e=$('#cl-'+id);if(!e)return d;let v=parseFloat(String(e.value).replace(',','.'));if(!isFinite(v))v=d;if(lo!=null)v=Math.max(lo,v);if(hi!=null)v=Math.min(hi,v);return v};
  const read=()=>{
    F.start=rn('start',0,0);F.monthly=rn('monthly',0,0);F.idx=rn('idx',0,0,50);F.years=Math.round(rn('years',10,1,30));F.ownRate=rn('ownRate',15,0,100);
    F.reinvest=$('#cl-reinvest').checked;F.freq=+$('#cl-freq').value;F.lot=rn('lot',0,0);F.lotFund=$('#cl-lotFund').value;F.ownKey=rn('ownKey',12,1,50);
    F.acct=$('#cl-acct').value;F.reinvDed=$('#cl-reinvDed').checked;F.ldv=$('#cl-ldv').checked;F.defaults=$('#cl-defaults').checked;F.depSpread=rn('depSpread',1.5,0,10);
    F.goalOn=$('#cl-goalOn').checked;F.goalAmt=rn('goalAmt',0,0);F.goalMode=$('#cl-goalMode').value;if($('#cl-goalStrat'))F.goalStrat=$('#cl-goalStrat').value;
    form.querySelectorAll('#cl-strat input').forEach(c=>{F.strat[c.dataset.s]=c.checked?1:0});
    $('#cl-yv').textContent=F.years;
    $('#cl-ownbox').style.display=F.strat.own?'':'none';$('#cl-ownkeybox').style.display=F.scn==='own'?'':'none';$('#cl-goalbox').style.display=F.goalOn?'':'none';
    clSave();clUpdate();
  };
  form.addEventListener('input',read);form.addEventListener('change',read);
  [['scn',v=>{F.scn=v}],['real',v=>{F.real=v==='1'}]].forEach(([id,fn])=>{const s=$('#cl-'+id);if(s)s.onclick=e=>{const b=e.target.closest('button');if(!b)return;
    s.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));fn(b.dataset.v);read()}});
  const b=$('#cl-pf');if(b)b.onclick=()=>{const pf=P.portfolio;if(!pf)return;if(pf.value!=null)F.start=Math.round(pf.value);if(pf.monthly!=null)F.monthly=Math.round(pf.monthly);F.strat.pf=1;clSave();render()};
}
