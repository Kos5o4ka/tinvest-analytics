/* калькулятор инвестиций */
/* ── Чистая часть: модель (без DOM, считается на клиенте) ── */
const CL_BR=[[2.4e6,.13],[Infinity,.15]];   /* шкала НДФЛ для инвестиционных доходов (купоны, продажа бумаг, проценты по вкладам): 13 % до 2,4 млн ₽ в год, 15 % с превышения */
const CL_STR=[['dep','Вклад','#8a93a6'],['fund','Фонд ликвидности','#19a070'],['ofz','ОФЗ','#3987e5'],['aaa','Корпоративные AAA','#7ab4f5'],['aa','Корпоративные AA','#9085e9'],
  ['a','Корпоративные A','#c98500'],['hy','ВДО (BB и ниже)','#e66767'],['pf','Мой портфель','#d55181'],['own','Своя ставка','#d95926']];
const CL_BETA={ofz:.6,aaa:.7,aa:.7,a:.7,hy:.7};
const CL_ACC=[['plain','Обычный брокерский счёт'],['iisA','ИИС типа А (вычет с взносов)'],['iisB','ИИС типа Б (доход без налога)'],['iis3','ИИС-3 (вычет и освобождение дохода)']];
function clNdfl(b){if(!(b>0))return 0;let t=0,lo=0;for(const[h,r]of CL_BR){if(b>lo)t+=(Math.min(b,h)-lo)*r;lo=h;if(b<=h)break}return t}
function clTaxInc(inc,x){return clNdfl(inc+x)-clNdfl(inc)}
const clYE=(env,k)=>(env.m0+k)%12===0;   /* шаг k приходится на 1 января: закончился календарный (налоговый) год */
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
/* Вклад: ежемесячная капитализация; НДФЛ раз в год (уведомление) с процентов за календарный год сверх необлагаемой суммы: 1 млн ₽ × макс. ключевая ставка года */
function clSimDep(p,env){
  const N=p.months;let B=0,dep=0,iy=0,mk=0;const cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[]};
  const due=()=>clNdfl(Math.max(0,iy-1e6*mk/100));
  for(let k=0;k<=N;k++){
    if(k>0){const g=B*env.depRate(k-1)/1200;B+=g;iy+=g;mk=Math.max(mk,env.key(k-1));
      if(clYE(env,k)||k===N){const tx=due();B-=tx;r.taxes+=tx;iy=0;mk=0}}
    const c=clContrib(p,k);B+=c;dep+=c;cap.push(B-due());
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
/* Облигации с фиксированным купоном (держим до погашения) и «ставка + купонный налог».
   Купоны реинвестируются целиком; НДФЛ удерживается раз в год (конец календарного года) и при выводе в конце срока,
   на ИИС — только при закрытии счёта. Налог платится из свободных денег, затем продажей части облигаций. */
function clSimBond(id,p,env,seg){
  const N=p.months,ai=clAccInfo(p),RF=clRefunds(p,ai),f=p.freq,per=Math.max(1,Math.round(12/f));
  const y0=seg.yield,beta=seg.beta||0,matM=seg.dur>0?Math.max(Math.round(seg.dur*12),per):Infinity,loss=p.defaults?(seg.loss||0):0;
  const ynew=k=>k===0?y0:Math.max(.5,y0+beta*(env.key(k)-env.kr0));
  const tr=[],cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[]};
  let cashInv=0,idle=0,pot=0,incY=0,incTot=0;const useLot=p.lot>1;
  /* начисленный, но не удержанный налог: на ИИС — весь доход в год закрытия (ИИС Б / ИИС-3 — сверх лимита освобождения) */
  const due=()=>ai.iis?clNdfl(ai.exempt?Math.max(0,incTot-ai.cap):incTot):clNdfl(incY);
  const pay=x=>{if(!(x>0))return;r.taxes+=x;let t;
    t=Math.min(idle,x);idle-=t;x-=t;t=Math.min(cashInv,x);cashInv-=t;x-=t;t=Math.min(pot,x);pot-=t;x-=t;
    if(x>0){const sm=tr.reduce((a,q)=>a+q.amt,0);if(sm>0){const q=Math.max(0,1-x/sm);tr.forEach(z=>{z.amt*=q})}}};
  for(let k=0;k<=N;k++){
    if(k>0){
      if(pot>0){const g=pot*env.fundRate(k-1)/1200;pot+=g;incY+=g;incTot+=g}
      let coup=0,prin=0;
      for(let i=tr.length-1;i>=0;i--){const t=tr[i];
        if(loss)t.amt*=1-loss/1200;
        if(k>t.k0&&k<=t.mat&&(k-t.k0)%per===0)coup+=t.amt*t.y/100/f;
        if(k===t.mat){prin+=t.amt;tr.splice(i,1)}}
      incY+=coup;incTot+=coup;
      if(p.reinvest)cashInv+=coup;else idle+=coup;
      cashInv+=prin;
      if(k===N)pay(due());else if(!ai.iis&&clYE(env,k)){pay(clNdfl(incY));incY=0}
    }
    if(RF[k]>0){if(p.reinvDed)cashInv+=RF[k];else idle+=RF[k];r.deductions+=RF[k]}
    const c=clContrib(p,k);cashInv+=c;r.deposited+=c;
    const avail=cashInv+pot;
    if(avail>0.005){const amt=useLot?Math.floor(avail/p.lot+1e-9)*p.lot:avail;
      if(amt>0)tr.push({k0:k,amt,y:ynew(k),mat:k+matM});
      const rem=avail-amt;if(p.lotFund){cashInv=0;pot=rem}else{cashInv=rem;pot=0}}
    let v=idle+cashInv+pot;for(const t of tr)v+=t.amt;cap.push(k<N?v-due():v);
  }
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
function clGoal(F,P,env,sid,real){
  const T=+F.goalAmt||0,pas=(months,monthly)=>{const p=clParams(F,months);p.monthly=monthly;const r=clSim(sid,p,P,env,F);return real===false?r.passive:r.passiveReal};
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
  acct:'plain',reinvDed:true,ldv:true,defaults:true,real:true,depSpread:1.5,goalMode:'contrib',goalStrat:'ofz',adv:false,view:''};
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
const clMkt=()=>(S.calcAcc===S.account&&S.calcP)||clDefaultParams();
function clAvail(P){return CL_STR.filter(s=>s[0]!=='pf'||(P.portfolio&&P.portfolio.irr!=null))}
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
    s+=`<polygon points="${up.concat(a.map(pt2).reverse()).join(' ')}" fill="${ser[j].c}" fill-opacity=".5"/><polyline points="${up.join(' ')}" fill="none" stroke="${ser[j].c}" stroke-width="1.6" stroke-linejoin="round"/>`});
  let hits='';const cw=pw/(n-1);
  for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${X(i)-cw/2}" y="${pt}" width="${cw}" height="${ph}" fill="transparent"/>`;
  el.innerHTML=legend(ser)+`<svg width="${W}" height="${H}">${s}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{if(i<0){hv.innerHTML='';return}hv.innerHTML=`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph}" stroke="var(--mu)" stroke-opacity=".6" stroke-dasharray="3 3"/>`+
    cum.map(([a,b],j)=>`<circle cx="${X(i)}" cy="${Y(b[i])}" r="4" fill="${ser[j].c}" stroke="var(--card)" stroke-width="2"/>`).join('')};
  bindTip(el,i=>`<b>${esc(tl[i])}</b>`+ser.slice().reverse().map(se=>tipRow(se.c,se.n,ft(se.v[i]||0))).join('')+
    `<div style="border-top:1px solid var(--line2);padding-top:5px;margin-top:6px">Итого<span>${ft(acc[i])}</span></div>`);
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
  const F=clLoadF(),P=clMkt();
  const ids=clAvail(P).map(s=>s[0]).filter(id=>F.strat[id]);
  if(!ids.length)return`<div class="card empty">Выберите хотя бы одну стратегию для сравнения</div>`;
  const run=clRun(F,P),{env,N,res,p}=run,real=F.real,dv=k=>real?env.D[k]:1,mode=real?'в сегодняшних деньгах':'в номинальных рублях';
  const labels=[],tips=[];
  for(let k=0;k<=N;k++){const d=new Date(env.y0,env.m0+k,1),mm=String(d.getMonth()+1).padStart(2,'0');labels.push(mm+'.'+d.getFullYear());tips.push(mm+'.'+d.getFullYear()+' · '+(k?clYM(k):'сейчас'))}
  const best=res.slice().sort((a,b)=>b.finalReal-a.finalReal)[0],cur=res.find(r=>r.id===F.view)||best,defl=env.D[N];
  /* состав капитала выбранной стратегии: внесено + вычеты ИИС + доход после налогов */
  const RF=cur.id==='dep'?null:clRefunds(p,clAccInfo(p)),sIn=[],sDed=[],sInc=[];let ci=0,cd=0;
  for(let k=0;k<=N;k++){ci+=clContrib(p,k)/dv(k);if(RF)cd+=RF[k]/dv(k);sIn.push(ci);sDed.push(cd);sInc.push(cur.cap[k]/dv(k)-ci-cd)}
  const ser=[{n:'Внесено',c:'#8a93a6',v:sIn}];if(cd>0)ser.push({n:'Вычеты и возвраты ИИС',c:'#c98500',v:sDed});ser.push({n:'Доход после налогов',c:'#19a070',v:sInc});
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
  const th=['Стратегия','Итоговый капитал','Внесено','Получено дохода','Уплачено налогов','Вычеты и возвраты ИИС','Капитал в сегодняшних деньгах','Пассивный доход в месяц (после налога)','Эффективная годовая доходность'];
  const rows=res.map(r=>`<tr data-s="${r.id}" class="${r===cur?'cl-cur':''}"><td class="l"><i class="cl-dot" style="background:${r.color}"></i>${esc(r.name)}${r===best?' <small class="mu">лучшая</small>':''}</td><td class="num"><b>${clRub(r.final)}</b></td><td class="num">${clRub(r.deposited)}</td>
    <td class="num ${cls(r.income)}">${clRub(r.income)}</td><td class="num">${clRub(r.taxes)}</td><td class="num">${r.deductions>0?clRub(r.deductions):'—'}</td><td class="num"><b>${clRub(r.finalReal)}</b></td>
    <td class="num">${clRub(r.passive)}<br><small class="mu">${clRub(r.passiveReal)} сегодня</small></td><td class="num">${r.xirr==null?'—':pctp(r.xirr,1)}</td></tr>`).join('');
  const warn=[];
  if(F.acct!=='plain'){
    if(res.some(r=>r.id==='dep'))warn.push('Вклад лежит в банке, а не на ИИС: вычет и льготы ИИС к нему не применяются, налог считается как на обычном счёте.');
    if((p.start+p.monthly*12)>1e6)warn.push('Взносы на ИИС ограничены 1 млн ₽ в год: калькулятор этот лимит не проверяет, проверьте свои суммы.');
    if(F.acct==='iisB'&&N<36)warn.push('Освобождение дохода на ИИС типа Б действует при сроке от 3 лет: при меньшем сроке налог удерживается при закрытии счёта.');
    if(F.acct==='iis3'&&N<60)warn.push('ИИС-3: освобождение дохода (до 30 млн ₽) принято при сроке владения от 5 лет; при меньшем сроке налог удерживается при закрытии счёта.');
    if(F.acct==='iis3'&&N>=60)warn.push('Допущение ИИС-3: минимальный срок для освобождения дохода принят равным 5 годам, лимит освобождаемого дохода 30 млн ₽; вычет считается как на ИИС типа А (13 % от взносов до 400 тыс. ₽ в год).');
  }
  if(F.acct==='plain'&&res.some(r=>r.id==='fund')&&F.ldv)warn.push('ЛДВ для фонда ликвидности: рост пая без налога при владении 3 года и более, лимит 3 млн ₽ × число лет. Каждое пополнение учитывается отдельно по сроку владения.');
  if(P.portfolio==null&&F.strat.pf)warn.push('Нет данных о портфеле — «Мой портфель» недоступен.');
  const wn=warn.length?`<div class="note" style="margin-top:12px">${warn.map(w=>'• '+esc(w)).join('<br>')}</div>`:'';
  const tbl=`<div class="card"><h2>Сравнение стратегий<span class="sp">через ${clYM(N)}</span></h2><div class="tbl cl-tbl"><table><thead><tr>${th.map((t,i)=>`<th class="${i?'':'l'}">${t}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>
    <div class="note" style="margin-top:10px">«Итоговый капитал» — если закрыть позиции и вывести деньги в конце срока: за вычетом всех налогов, включая налог последнего года, налог при закрытии ИИС и (для фонда ликвидности) налог при продаже. «Эффективная годовая доходность» — XIRR взносов против итога (номинальная, без учёта инфляции). «Получено дохода» = итог − внесено − вычеты.${res.length>1?' Нажмите на строку, чтобы показать стратегию в итогах и на графике.':''}</div>${wn}</div>`;
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
  <div class="card"><h2>Параметры<span class="sp">пересчёт мгновенный</span></h2><div id="cl-form">
   <div class="cl-grid cl-base">${num('start','Стартовый капитал, ₽',F.start,'min="0" step="10000"')}${num('monthly','Пополнение в месяц, ₽',F.monthly,'min="0" step="1000"')}
    <label class="field"><span>Срок: <b id="cl-yv">${F.years}</b> лет</span><input id="cl-years" type="range" min="1" max="30" step="1" value="${F.years}"></label></div>
   ${pf&&pf.value!=null?`<div class="cl-row"><button class="btn ghost" id="cl-pf">Подставить мой портфель</button><span class="note">старт ${clRub(pf.value)}${pf.monthly!=null?`, пополнение ${clRub(pf.monthly)} в месяц (среднее за 12 мес.)`:''}</span></div>`:''}
   <div class="cl-sec">Во что вкладываем</div><div class="cl-chips" id="cl-strat">${chips}</div>
   <div class="cl-grid" id="cl-ownbox" style="margin-top:12px;${F.strat.own?'':'display:none'}">${num('ownRate','Своя ставка, % годовых',F.ownRate,'step="0.5" min="0" max="100"')}</div>
   <details class="cl-adv" id="cl-adv" ${F.adv?'open':''}><summary>Дополнительные параметры<span id="cl-advsum">${esc(clAdvSum(F))}</span></summary>
    <div class="cl-sec">Счёт и налоги</div>
    <div class="cl-grid">${sel('acct','Тип счёта',CL_ACC,F.acct)}${sw('reinvDed','Реинвестировать вычет ИИС','возвращённый налог снова вкладывается',F.reinvDed)}
     ${sw('ldv','ЛДВ для фонда ликвидности','без налога на рост пая при владении от 3 лет',F.ldv)}${sw('defaults','Учитывать дефолты','вычитаем ожидаемые потери сегмента каждый год',F.defaults)}</div>
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
  <div class="card"><h2>Как это считается</h2><div class="note">Шаг расчёта — месяц; взносы вносятся в конце месяца; налоговый год — календарный. Шкала НДФЛ для инвестиционных доходов (купоны, продажа бумаг, проценты по вкладам): 13 % до 2,4 млн ₽ дохода в год, 15 % с превышения.
   <b>Вклад</b>: ежемесячная капитализация по ставке «ключевая − ${f2(F.depSpread)} п.п.» по пути выбранного сценария. НДФЛ платится раз в год по уведомлению с процентов за год сверх необлагаемой суммы (1 млн ₽ × максимальная ключевая ставка года по сценарию); в модели налог списывается со вклада в конце года (в жизни — до 1 декабря следующего года). Необлагаемая сумма общая на все вклады человека: если есть другие вклады, налог будет больше.
   <b>Фонд ликвидности</b>: ежедневное начисление приближено месячным по «ключевая − спред к ключевой»; налог только при продаже в конце срока (или ЛДВ / ИИС).
   <b>ОФЗ, корпоративные, ВДО</b>: покупаем по текущей медианной доходности сегмента, держим до погашения (срок ≈ медианная дюрация), купоны по этой доходности; погашенный номинал и купоны вкладываются по будущей доходности ≈ текущая + β × (ключевая в тот момент − ключевая сейчас), β = 0,6 для ОФЗ и 0,7 для остальных. Купоны реинвестируются целиком: брокер удерживает НДФЛ с купонов раз в год, в конце календарного года, и с остатка — при выводе денег в конце срока; налог берётся из свободных денег на счёте, а если их не хватает — продаётся часть облигаций. На ИИС налог удерживается только при закрытии счёта (весь доход попадает в базу года закрытия); на ИИС типа Б от 3 лет и ИИС-3 от 5 лет налога нет (ИИС-3 — с дохода до 30 млн ₽). Переоценка цены облигаций при удержании до погашения не учитывается; на конец срока позиции считаются по номиналу.
   <b>Мой портфель</b>: доходность облигаций портфеля (IRR) используется как ставка; <b>Своя ставка</b> — постоянная ставка с купонным налогом. Капитал в промежуточные месяцы показан за вычетом начисленного, но ещё не удержанного налога. Инфляция — прогноз Банка России, после его горизонта — последнее значение.</div></div>
  <div class="note cl-disc">Модель упрощённая. Результаты — не прогноз и не индивидуальная инвестиционная рекомендация: реальные ставки, цены, налоги и дефолты будут отличаться.</div>`;
}
function clUpdate(){S.charts=[];const o=$('#cl-out');if(!o)return;o.innerHTML=clOut();mountCharts()}
function bindCalcInv(){
  const form=$('#cl-form');if(!form)return;const F=clLoadF(),P=clMkt();
  const rn=(id,d,lo,hi)=>{const e=$('#cl-'+id);if(!e)return d;let v=parseFloat(String(e.value).replace(',','.'));if(!isFinite(v))v=d;if(lo!=null)v=Math.max(lo,v);if(hi!=null)v=Math.min(hi,v);return v};
  const read=()=>{
    F.start=rn('start',0,0);F.monthly=rn('monthly',0,0);F.idx=rn('idx',0,0,50);F.years=Math.round(rn('years',10,1,30));F.ownRate=rn('ownRate',15,0,100);
    F.reinvest=$('#cl-reinvest').checked;F.freq=+$('#cl-freq').value;F.lot=rn('lot',0,0);F.lotFund=$('#cl-lotFund').value;F.ownKey=rn('ownKey',12,1,50);
    F.acct=$('#cl-acct').value;F.reinvDed=$('#cl-reinvDed').checked;F.ldv=$('#cl-ldv').checked;F.defaults=$('#cl-defaults').checked;F.depSpread=rn('depSpread',1.5,0,10);
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
  const b=$('#cl-pf');if(b)b.onclick=()=>{const pf=P.portfolio;if(!pf)return;if(pf.value!=null)F.start=Math.round(pf.value);if(pf.monthly!=null)F.monthly=Math.round(pf.monthly);F.strat.pf=1;clSave();render()};
}

/* ── Вкладка «Пассивный доход»: математика на сервере (/api/calc/goal), здесь только ввод и вывод ── */
const CG_DEF={monthly:100000,hz:'years',years:10,date:'',yield:'',value:'',real:true,infl:''};
let CG_F=null,CG_T=0;
function cgLoad(){
  if(CG_F)return CG_F;const s=lsJson('ta_calc_goal',{}),F=Object.assign({},CG_DEF);
  if(s&&typeof s==='object')for(const k in F){if(s[k]!==undefined&&typeof s[k]===typeof F[k])F[k]=s[k]}
  return CG_F=F;
}
function cgMode(){return lsJson('ta_calc_mode','inv')==='goal'?'goal':'inv'}
function cgSetMode(m){lsSet('ta_calc_mode',JSON.stringify(m));render()}
function cgQuery(F){
  const q={account:S.account,monthly:F.monthly,real:F.real?'1':'0'};
  if(F.hz==='date'&&F.date)q.date=F.date;else q.years=F.years;
  if(F.yield!=='')q.yield=F.yield;if(F.value!=='')q.value=F.value;if(F.infl!=='')q.infl=F.infl;
  return new URLSearchParams(q).toString();
}
function cgFetch(){
  const F=cgLoad(),acc=S.account,n=++CG_T;
  api('/api/calc/goal?'+cgQuery(F)).then(j=>{if(n!==CG_T)return;S.cgData=j;S.cgAcc=acc;cgPaint()}).catch(e=>{if(n!==CG_T)return;S.cgData={error:e.message};cgPaint()});
}
function cgPaint(){const o=$('#cg-out');if(!o)return;S.charts=[];o.innerHTML=cgOut();mountCharts();cgHints()}
function cgHints(){
  const d=S.cgData&&S.cgData.defaults;if(!d)return;
  const set=(id,v,suf)=>{const e=$('#cg-'+id);if(e&&e.value==='')e.placeholder=v==null?'':(String(v)+(suf||''))};
  set('yield',d.yield==null?'':d.yield);set('value',d.value==null?'':Math.round(d.value));set('infl',S.cgData.infl?S.cgData.infl.value:'');
}
/* подбор на конкретной стратегии калькулятора: срок и стартовая сумма — из расчёта выше, остальные параметры — из вкладки «Накопить капитал» */
function cgStrat(r){
  const F=clLoadF(),P=clMkt(),av=clAvail(P),sid=av.some(s=>s[0]===F.goalStrat)?F.goalStrat:'ofz',s=CL_STR.find(x=>x[0]===sid);
  const G=Object.assign({},F,{goalAmt:r.monthly,start:r.value||0,years:r.months/12}),g=clGoal(G,P,clEnv(P,G),sid,!!r.real),N=r.months;
  const amt=clRub(r.monthly)+' в месяц'+(r.real?' (в сегодняшних деньгах, после налога)':' (после налога)');
  let t;
  if(!g.ok)t=`Для стратегии «${esc(s[1])}» цель ${amt} ${F.goalMode==='years'?'недостижима и за 50 лет при таком пополнении':'недостижима при заданном сроке даже при очень больших пополнениях'}.`;
  else if(F.goalMode==='years')t=g.months<=1?`Цель ${amt} достигается сразу: стартовой суммы достаточно.`:
    `Чтобы получать ${amt} на стратегии «${esc(s[1])}», при пополнении ${clRub(F.monthly)} в месяц понадобится около <b>${clYM(g.months)}</b>.`;
  else t=g.monthly<=0?`Цель ${amt} за ${clYM(N)} достигается и без ежемесячных пополнений: хватает стартовой суммы.`:
    `Чтобы через ${clYM(N)} получать ${amt} на стратегии «${esc(s[1])}», нужно пополнять примерно <b>${clRub(g.monthly)}</b> в месяц (с ежегодной индексацией ${f2(F.idx)} %).`;
  const so=av.map(x=>`<option value="${x[0]}" ${x[0]===sid?'selected':''}>${x[1]}</option>`).join('');
  return`<div class="card cl-goal"><h2>На конкретной стратегии<span class="sp">ставки, налоги и дефолты как во вкладке «Накопить капитал»</span></h2>
   <div class="cl-grid cl-base" style="margin-bottom:12px"><label class="field"><span>Стратегия</span><select class="in" id="cg-gs">${so}</select></label>
    <label class="field"><span>Что найти</span><select class="in" id="cg-gm"><option value="contrib" ${F.goalMode!=='years'?'selected':''}>нужное пополнение (срок задан)</option><option value="years" ${F.goalMode==='years'?'selected':''}>нужный срок (пополнение ${clRub(F.monthly)} в месяц)</option></select></label></div>
   <div class="cl-ans">${t}</div><div class="note" style="margin-top:8px">Стартовая сумма — ${clRub(r.value||0)}, срок — ${clYM(N)}, как в расчёте выше; тип счёта, сценарий ставки, индексация и пополнение — из вкладки «Накопить капитал». Пассивный доход — проценты или купоны, которые капитал приносит в год, делённые на 12, после налога по шкале 13/15 %.</div></div>`;
}
function cgOut(){
  const j=S.cgData,F=cgLoad();
  if(!j)return`<div class="card">${waitBox('Считаю…')}</div>`;
  if(j.error&&!j.result)return`<div class="msg err">${esc(j.error)}</div>`;
  const r=j.result;if(!r)return`<div class="card empty">Введите желаемый доход в месяц</div>`;
  const d=j.defaults||{},src=[];
  if(F.yield===''&&d.yield!=null)src.push(`доходность ${f2(r.yield_pct)} % взята из облигаций вашего портфеля`);
  if(F.value==='' &&d.value!=null)src.push(`текущая стоимость ${clRub(r.value)} взята из портфеля`);
  const ym=clYM(r.months);
  chart('cg-chart',line,{h:300,labels:r.chart.labels.map(l=>l.slice(5)+'.'+l.slice(0,4)),fa:short,ft:v=>clRub(v),empty:'Нет данных',
    series:[{n:'Капитал при нужном пополнении',c:'#19a070',v:r.chart.capital},{n:'Без пополнений',c:'#8a93a6',dash:1,w:1.6,v:r.chart.no_contrib},{n:'Нужный капитал',c:'#d95926',dash:1,w:1.8,v:r.chart.target}]});
  const cv=r.coverage;
  const cov=cv&&cv.pct!=null?`<div class="card cl-goal"><h2>Где вы сейчас</h2><div class="cl-ans">Сейчас купоны и дивиденды дают около <b>${clRub(cv.income)}</b> в месяц${d.income_src&&F.value===''?` (${esc(d.income_src)})`:''} — это <b>${f2(cv.pct)} %</b> цели. Оценка до налога и без учёта будущих изменений портфеля.</div></div>`:
    `<div class="card"><div class="note">Данных о текущем доходе нет: подключите токен или укажите стоимость портфеля.</div></div>`;
  let st='';try{st=cgStrat(r)}catch(e){console.error(e)}
  return`<div class="g g4">${kpi('Нужный капитал сегодня',clRub(r.capital_today),`${clRub(r.monthly)} в мес. после налога`,null,S1)}
    ${kpi(r.real&&r.inflation_factor>1.001?'Нужный капитал на дату цели':'Нужный капитал к цели',clRub(r.capital_end),r.real&&r.inflation_factor>1.001?`цель с инфляцией: ${clRub(r.goal_end)} в мес.`:'без поправки на инфляцию',null,S4)}
    ${kpi('Пополнение в месяц',r.reached?'не требуется':clRub(r.contribution),r.reached?'текущего капитала достаточно':`за ${ym} внесёте ${short(r.contribution_total)} ₽`,r.reached?'pos':'',S3)}
    ${kpi('Доходность после налога',f2(r.yield_net)+' %',`ставка ${f2(r.yield_pct)} % за вычетом 13 %`,null,S2)}</div>
  ${cov}
  <div class="card"><h2>Рост капитала и цель<span class="sp">через ${ym}</span></h2><div id="cg-chart" class="chart"></div>
   <div class="note" style="margin-top:10px">${src.length?esc(src.join('; '))+'. ':''}${r.real?`Цель задана в сегодняшних деньгах: при инфляции ${f2(r.infl_pct)} % в год к дате цели нужно ${clRub(r.goal_end)} в месяц.`:'Цель задана в номинальных рублях, без поправки на инфляцию.'}</div></div>
  ${st}
  <div class="card"><h2>Как это считается</h2><div class="note">Нужный капитал = доход в месяц × 12 ÷ (доходность × (1 − 13 %)). Капитал растёт на доходность после налога, доход реинвестируется; пополнения вносятся в конце месяца и не индексируются. Ставка и налог принимаются постоянными (шкалу НДФЛ с 15 % свыше 2,4 млн ₽ дохода в год этот расчёт не учитывает — её учитывает блок «На конкретной стратегии»), риски и дефолты не заложены. Расчёт информационный и не является инвестиционной рекомендацией; налоги уточняйте у брокера и в ФНС.</div></div>`;
}
function pCalcGoal(){
  const F=cgLoad();
  const num=(id,l,v,o)=>`<label class="field"><span>${l}</span><input class="in" id="cg-${id}" type="number" inputmode="decimal" value="${esc(v)}" ${o||''}></label>`;
  if(S.calcAcc!==S.account)clLoad();
  if(S.cgAcc!==S.account||!S.cgData){S.cgData=null;setTimeout(cgFetch,0)}
  return`<div class="card"><h2>Цель по пассивному доходу<span class="sp">сколько нужно накопить</span></h2><div id="cg-form">
    <div class="cl-grid">${num('monthly','Желаемый доход в месяц после налога, ₽',F.monthly,'min="0" step="5000"')}
     <label class="field"><span>Горизонт</span><select class="in" id="cg-hz"><option value="years" ${F.hz==='years'?'selected':''}>Через N лет</option><option value="date" ${F.hz==='date'?'selected':''}>К дате</option></select></label>
     <div id="cg-yearsbox" style="${F.hz==='years'?'':'display:none'}">${num('years','Лет',F.years,'min="1" max="50" step="1"')}</div>
     <div id="cg-datebox" style="${F.hz==='date'?'':'display:none'}">${num('date','Дата цели',F.date,'').replace('type="number" inputmode="decimal"','type="date"')}</div>
     ${num('yield','Ожидаемая доходность портфеля до налога, % годовых',F.yield,'min="0" max="99" step="0.5" placeholder="из портфеля"')}
     ${num('value','Текущая стоимость портфеля, ₽',F.value,'min="0" step="10000" placeholder="из портфеля"')}
     <label class="sw"><input type="checkbox" id="cg-real" ${F.real?'checked':''}><i></i><div><b>Цель в сегодняшних деньгах</b><small>учесть инфляцию до даты цели</small></div></label>
     ${num('infl','Инфляция, % в год',F.infl,'min="0" max="50" step="0.5" placeholder="прогноз ЦБ"')}</div>
    <div class="note">Пустые поля заполняются данными портфеля (нужен токен); без токена введите значения вручную.</div></div></div>
   <div id="cg-out">${cgOut()}</div>`;
}
function bindCalcGoal(){
  const form=$('#cg-form');if(!form)return;const F=cgLoad();
  const rd=id=>{const e=$('#cg-'+id);return e?e.value.trim():''};
  const nm=(id,d)=>{const v=parseFloat(rd(id).replace(',','.'));return isFinite(v)&&v>=0?v:d};
  const read=()=>{
    F.monthly=nm('monthly',0);F.hz=rd('hz')==='date'?'date':'years';F.years=nm('years',10);F.date=rd('date');
    F.yield=rd('yield')===''?'':nm('yield','');F.value=rd('value')===''?'':nm('value','');F.real=$('#cg-real').checked;F.infl=rd('infl')===''?'':nm('infl','');
    $('#cg-yearsbox').style.display=F.hz==='years'?'':'none';$('#cg-datebox').style.display=F.hz==='date'?'':'none';
    lsSet('ta_calc_goal',JSON.stringify(F));clearTimeout(bindCalcGoal.t);bindCalcGoal.t=setTimeout(cgFetch,250);
  };
  form.addEventListener('input',read);form.addEventListener('change',read);
  const o=$('#cg-out');if(o)o.onchange=e=>{const t=e.target;if(t.id!=='cg-gs'&&t.id!=='cg-gm')return;const G=clLoadF();G[t.id==='cg-gs'?'goalStrat':'goalMode']=t.value;clSave();cgPaint()};
  if(S.cgData)cgHints();
}
function pCalc(){
  const m=cgMode();
  const sw=`<div class="row noprint"><div class="seg cl-tabs">${[['inv','Накопить капитал'],['goal','Пассивный доход']].map(([k,t])=>`<button class="${k===m?'on':''}" onclick="cgSetMode('${k}')">${t}</button>`).join('')}</div></div>`;
  return`<div class="cl-page">${sw}${m==='goal'?pCalcGoal():pCalcInv()}</div>`;
}
function bindCalc(){if(cgMode()==='goal')bindCalcGoal();else bindCalcInv()}
