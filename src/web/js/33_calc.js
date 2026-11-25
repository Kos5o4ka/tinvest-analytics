/* калькулятор инвестиций */
/* ── Чистая часть: модель (без DOM, считается на клиенте) ── */
const CL_BR=[[2.4e6,.13],[Infinity,.15]];   /* шкала НДФЛ для инвестиционных доходов (купоны, продажа бумаг, проценты по вкладам): 13 % до 2,4 млн ₽ в год, 15 % с превышения */
const CL_STR=[['dep','Вклад','#8a93a6'],['fund','Фонд ликвидности','var(--s3)'],['ofz','ОФЗ','var(--s1)'],['aaa','Корпоративные AAA','var(--s2)'],['aa','Корпоративные AA','var(--s7)'],
  ['a','Корпоративные A','var(--s4)'],['hy','ВДО (BB и ниже)','var(--s8)'],['pf','Мой портфель','var(--s5)'],['own','Своя ставка','var(--s8)']];
const CL_BETA={ofz:.6,aaa:.7,aa:.7,a:.7,hy:.7};
const CL_ACC=[['plain','Обычный брокерский счёт'],['iis3','ИИС-3 (вычет и освобождение дохода)']];
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
  return{ded:a==='iis3',exempt:a==='iis3'&&N>=60,cap:a==='iis3'?30e6:Infinity,iis:a!=='plain'};
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
  /* начисленный, но не удержанный налог: на ИИС — весь доход в год закрытия (ИИС-3 — сверх лимита освобождения) */
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
  return{start:+F.start||0,monthly:+F.monthly||0,idx:+F.idx||0,months:months||Math.round((+F.years||1)*12),acct:(F.acct==='iisA'||F.acct==='iisB')?'iis3':F.acct,reinvest:!!F.reinvest,freq:+F.freq||12,
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
