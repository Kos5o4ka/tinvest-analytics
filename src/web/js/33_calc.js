/* калькулятор инвестиций: единый движок (чистая часть, без DOM; считается на клиенте и проверяется через jsc в tests/test_calc_js.py) */
const CL_BR=[[2.4e6,.13],[Infinity,.15]];   /* шкала НДФЛ для инвестиционных доходов (купоны, продажа бумаг, проценты по вкладам): 13 % до 2,4 млн ₽ в год, 15 % с превышения */
const CL_LGD=.75;                            /* потери при дефолте: 1 − ставка возмещения 25 % */
const CL_STR=[['dep','Вклад','#8a93a6'],['fund','Фонд ликвидности','var(--s3)'],['flt','Флоатеры (ключевая + спред)','var(--s6)'],['ofz','ОФЗ','var(--s1)'],['aaa','Корпоративные AAA','var(--s2)'],['aa','Корпоративные AA','var(--s7)'],
  ['a','Корпоративные A','var(--s4)'],['hy','ВДО (BB и ниже)','var(--s8)'],['stk','Акции РФ','var(--s2)'],['fxb','Замещающие облигации','var(--s6)'],['mix','Акции + облигации (микс)','var(--s3)'],['pf','Мой портфель','var(--s5)'],['own','Своя ставка','var(--s8)']];
const CL_BETA={ofz:.6,aaa:.7,aa:.7,a:.7,hy:.7,flt:1,fxb:0};
const CL_SIG={dep:0,fund:1,flt:2,ofz:6,aaa:5,aa:6,a:7,hy:10,stk:22,fxb:12,own:0};   /* годовой разброс доходности для фазы расходования и веера, % */
const CL_ACC=[['plain','Обычный брокерский счёт'],['iis3','ИИС-3 (вычет и освобождение дохода)']];
const CL_MIX=[['cons','Консервативный 20 / 80',20],['bal','Сбалансированный 50 / 50',50],['agr','Агрессивный 80 / 20',80],['own','Своя пропорция',null]];   /* доля акций, % */
/* срок ИИС-3 по году открытия (как в src/web/js/54_txo.js и txo_iis3_term на сервере): 2024–2026 — 5 лет, 2027 — 6, … 2030 — 9, с 2031 — 10 */
const CL_IIS_TERMS=[[2024,2026,5],[2027,2027,6],[2028,2028,7],[2029,2029,8],[2030,2030,9]];
function clIisTerm(y){for(const[a,b,t]of CL_IIS_TERMS)if(y>=a&&y<=b)return t;return y>2030?10:5}
/* НДФЛ с базы b за календарный год; sc — доля порога 15 % (когда расчёт ведётся по части портфеля) */
function clNdfl(b,sc){if(!(b>0))return 0;sc=sc>0?sc:1;let t=0,lo=0;for(const[h,r]of CL_BR){const hh=h*sc;if(b>lo)t+=(Math.min(b,hh)-lo)*r;lo=hh;if(b<=hh)break}return t}
function clTaxInc(inc,x){return clNdfl(inc+x)-clNdfl(inc)}
const clYE=(env,k)=>(env.m0+k)%12===0;   /* шаг k приходится на 1 января: закончился календарный (налоговый) год */
/* значения рынка по умолчанию, если сервер не ответил */
function clDefaultParams(){
  const k=16;return{key_rate:{current:k,source:'условное значение',estimate:true,path:[]},inflation:{yearly:[],default:4,estimate:true},
    segments:{ofz:{name:'ОФЗ',yield:k-.5,dur:4,loss:0,estimate:true},aaa:{name:'Корпоративные AAA',yield:k+.5,dur:2.5,loss:.04,estimate:true},aa:{name:'Корпоративные AA',yield:k+1.5,dur:2.5,loss:.15,estimate:true},
    a:{name:'Корпоративные A',yield:k+3,dur:2,loss:.6,estimate:true},hy:{name:'ВДО (BB и ниже)',yield:k+8,dur:1.5,loss:3.2,estimate:true},
    flt:{name:'Флоатеры (ключевая + спред)',yield:k+1.5,dur:.25,loss:.15,spread:1.5,estimate:true}},
    lqdt:{yield:k-.7,estimate:true,spread:.7},deposit:{spread:1.5},stocks:{div:8,growth:6,sigma:22,estimate:true},fx_bonds:{yield:6,fx:5,sigma:12,estimate:true},portfolio:null,fallback:true};
}
/* генератор случайных чисел (mulberry32) и нормальное распределение: результаты Монте-Карло воспроизводимы */
function clRng(seed){let a=(seed>>>0)||1;const u=()=>{a=(a+0x6D2B79F5)>>>0;let t=a;t=Math.imul(t^(t>>>15),t|1);t^=t+Math.imul(t^(t>>>7),t|61);return((t^(t>>>14))>>>0)/4294967296};
  let sp=null;u.n=()=>{if(sp!==null){const v=sp;sp=null;return v}let x=0,y=0,r=0;do{x=2*u()-1;y=2*u()-1;r=x*x+y*y}while(r>=1||r===0);const m=Math.sqrt(-2*Math.log(r)/r);sp=y*m;return x*m};return u}
/* окружение: путь ключевой ставки по сценарию, дефлятор, ставка фонда, индекс цен акций; rng — случайные шоки ставки и рынка акций (Монте-Карло) */
function clEnv(P,F,startDate,rng){
  const sd=startDate||new Date(),y0=sd.getFullYear(),m0=sd.getMonth(),M=721;
  const path=(P.key_rate.path||[]).map(x=>+x[1]).filter(x=>isFinite(x)),kr0=+P.key_rate.current||16;
  const base=k=>path.length?path[Math.min(k,path.length-1)]:kr0;
  const sh=new Float64Array(M),zq=new Float64Array(M);
  if(rng){let s=0;for(let k=1;k<M;k++){const z=rng.n();zq[k]=z;s=.985*s+.3*z;sh[k]=Math.max(-5,Math.min(6,s))}}
  const key=k=>{const b=base(k);let v=b;
    if(F.scn==='hard')v=b+2;else if(F.scn==='soft')v=Math.min(b,Math.max(b-2,4));else if(F.scn==='own')v=+F.ownKey||kr0;
    return Math.max(1,v+sh[Math.min(k,M-1)])};
  const iy={};(P.inflation.yearly||[]).forEach(x=>{iy[x.year]=x.mid});
  const iyears=Object.keys(iy).map(Number),last=iyears.length?iy[Math.max(...iyears)]:(P.inflation.default!=null?P.inflation.default:4);
  const D=[1];for(let k=1;k<M;k++){const yr=y0+Math.floor((m0+k-1)/12),i=iy[yr]!=null?iy[yr]:last;D.push(D[k-1]*Math.pow(1+i/100,1/12))}
  const lq=P.lqdt||{yield:kr0-.7,estimate:true,spread:.7};
  const fsp=lq.estimate?(lq.spread!=null?lq.spread:.7):Math.max(0,Math.min(3,kr0-lq.yield));
  const fundRate=k=>(!lq.estimate&&k<2&&!rng)?lq.yield:Math.max(key(k)-fsp,.1);
  const dsp=F.depSpread!=null?+F.depSpread:(P.deposit?P.deposit.spread:1.5);
  const st=P.stocks||{div:8,growth:6,sigma:22},sg=(+F.stkSig||st.sigma||22)/100,gr=F.stkGrow!==''&&F.stkGrow!=null?+F.stkGrow:st.growth;
  const fxs=P.fx_bonds||{yield:6,fx:5,sigma:12};
  /* индексы накопления: фонд ликвидности, цена акций (с шоками, коррелированными с ключевой), курс валюты */
  const G=[1],E=[1],X=[1],mu=Math.log(1+gr/100)/12,sm=sg/Math.sqrt(12),fxm=Math.log(1+(F.fxWeak!==''&&F.fxWeak!=null?+F.fxWeak:fxs.fx)/100)/12,fsm=(fxs.sigma||12)/100/Math.sqrt(12);
  for(let k=0;k<M-1;k++){G.push(G[k]*(1+fundRate(k)/1200));
    let ze=0,zf=0;if(rng){ze=-.3*zq[k+1]+.954*rng.n();zf=.4*ze+.917*rng.n()}
    E.push(E[k]*Math.exp(mu-(rng?sm*sm/2:0)+sm*ze));X.push(X[k]*Math.exp(fxm-(rng?fsm*fsm/2:0)+fsm*zf))}
  return{key,kr0,D,fundRate,depRate:k=>Math.max(key(k)-dsp,.1),y0,m0,infl:last,iy,G,E,X,stDiv:(F.stkDiv!==''&&F.stkDiv!=null?+F.stkDiv:st.div),rng};
}
function clContrib(p,k){return k===0?p.start:(k<=p.months?p.monthly*Math.pow(1+p.idx/100,Math.floor((k-1)/12)):0)}
/* счёт: вычет ИИС-3 (ставка и потолок по зарплатному НДФЛ), срок по году открытия, освобождение дохода до 30 млн ₽ */
function clAccInfo(p){
  const a=p.acct,N=p.months,sc=p.sc>0?p.sc:1,yr=p.y0||new Date().getFullYear(),oy=Math.min(Math.max(+p.iisYear||yr,2024),yr);
  const term=clIisTerm(oy),own=N+(yr-oy)*12;
  return{ded:a==='iis3',iis:a!=='plain',term,openYear:oy,own,exempt:a==='iis3'&&own>=term*12,cap:a==='iis3'?30e6*sc:Infinity,sc,
    rate:(p.salRate!=null?+p.salRate:13)/100,salary:p.salary>0?p.salary*sc:Infinity};
}
/* вычет ИИС: сумма и точка начисления (конец года). Если срок не выдержан — вычеты прошлых лет возвращаются (R.back), вычет последнего года не заявляется */
function clRefunds(p,ai){
  const N=p.months,R=new Array(N+1).fill(0);R.back=0;if(!ai.ded)return R;
  const yc={};for(let k=0;k<=N;k++){const y=k===0?0:Math.floor((k-1)/12);yc[y]=(yc[y]||0)+clContrib(p,k)}
  for(const y in yc){const pt=Math.min(12*(+y+1),N);R[pt]+=Math.min(yc[y],400e3*ai.sc,ai.salary)*ai.rate}
  if(!ai.exempt){R[N]=0;for(let k=0;k<N;k++)R.back+=R[k]}
  return R;
}
function clIrr(fl){          /* fl[k] — поток в месяц k; возвращает годовую эффективную доходность, % */
  let lo=-.5,hi=1;const f=r=>{let s=0;for(let k=0;k<fl.length;k++)s+=fl[k]/Math.pow(1+r,k);return s};
  if(!fl.some(x=>x<0)||!fl.some(x=>x>0))return null;
  if(f(lo)*f(hi)>0)return null;
  for(let i=0;i<80;i++){const m=(lo+hi)/2;if(f(lo)*f(m)<=0)hi=m;else lo=m}
  return(Math.pow(1+(lo+hi)/2,12)-1)*100;
}
/* Вклад: ежемесячная капитализация. НДФЛ с процентов за календарный год сверх необлагаемой суммы (1 млн ₽ × макс. ключевая года) начисляется в конце года, а платится 1 декабря СЛЕДУЮЩЕГО года (через 11 месяцев). */
function clSimDep(p,env){
  const N=p.months,sc=p.sc>0?p.sc:1;let B=0,dep=0,iy=0,mk=0;const cap=[],pend=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[],RF:new Array(N+1).fill(0),back:0,taxLog:[]};
  const due=()=>clNdfl(Math.max(0,iy-1e6*sc*mk/100),sc),owe=()=>pend.reduce((a,x)=>a+x[1],0);
  for(let k=0;k<=N;k++){
    if(k>0){const g=B*env.depRate(k-1)/1200;B+=g;iy+=g;mk=Math.max(mk,env.key(k-1));
      for(let i=pend.length-1;i>=0;i--)if(pend[i][0]<=k){B-=pend[i][1];r.taxes+=pend[i][1];r.taxLog.push([k,pend[i][1]]);pend.splice(i,1)}
      if(clYE(env,k)){const tx=due();if(tx>0)pend.push([k+11,tx]);iy=0;mk=0}
      if(k===N){const rest=due()+owe();B-=rest;r.taxes+=rest;if(rest>0)r.taxLog.push([k,rest]);pend.length=0;iy=0}}
    const c=clContrib(p,k);B+=c;dep+=c;
    cap.push(B-due()-owe());
  }
  r.deposited=dep;
  const inc=Math.max(0,cap[N]*env.depRate(Math.max(N-1,0))/100);
  r.incGross=inc;r.passive=(inc-clNdfl(Math.max(0,inc-1e6*sc*env.key(Math.max(N-1,0))/100),sc))/12;
  return r;
}
/* Паевой / «лотовый» актив: фонд ликвидности (рост пая) и акции (рост цены плюс дивиденды). Лоты покупаются по месяцам; налог с прироста — при продаже
   (на ИИС — при закрытии, при сроке от минимального — только сверх 30 млн ₽). ЛДВ по лотам старше 3 лет с ограничением 3 млн ₽ × средневзвешенный срок владения таких лотов.
   Дивиденды: налог раз в год (на ИИС — при закрытии); НДФЛ с продаж ради уплаты налога берётся по FIFO (самые старые лоты — первыми). */
function clSimLots(p,env,A){
  const N=p.months,sc=p.sc>0?p.sc:1,ai=clAccInfo(p),RF=clRefunds(p,ai),G=A.G,dv=A.div||0;
  const lots=[],cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[],RF:RF.slice(),back:RF.back};let idle=0,incY=0,incTot=0,vN=0;
  const val=(l,k)=>l.amt*G[k]/G[l.k0];
  const ldvOf=k=>{let gain=0,eg=0,eu=0,ew=0,ey=0;
    for(const l of lots){const v=val(l,k),g=v-l.amt;gain+=g;if(p.ldv&&!ai.iis&&k-l.k0>=36){eg+=g;const u=l.amt/G[l.k0];eu+=u;ey+=u*Math.floor((k-l.k0)/12);ew+=v}}
    const ex=eg>0&&eu>0?Math.min(eg,3e6*sc*(ey/eu)):0;return{gain,ex,old:ew}};
  const taxNow=k=>{const l=ldvOf(k);
    if(ai.iis){const base=l.gain+incTot;return clNdfl(ai.exempt?Math.max(0,base-ai.cap):Math.max(0,base),sc)}
    return clNdfl(Math.max(0,l.gain-l.ex+incY),sc)};
  const pay=(x,k)=>{if(!(x>0))return;const t=Math.min(idle,x);idle-=t;x-=t;
    for(let i=0;i<lots.length&&x>1e-9;i++){const l=lots[i],v=val(l,k);if(v<=0)continue;const q=Math.min(v,x),f=q/v;l.amt*=1-f;x-=q}
    while(lots.length&&lots[0].amt<1e-9)lots.shift()};
  for(let k=0;k<=N;k++){
    if(k>0&&dv>0){let d=0;for(const l of lots)d+=val(l,k)*dv/1200;
      if(d>0){incY+=d;incTot+=d;if(p.reinvest)lots.push({k0:k,amt:d});else idle+=d}}
    if(k>0&&!ai.iis&&clYE(env,k)&&k<N){const tx=clNdfl(Math.max(0,incY),sc);r.taxes+=tx;pay(tx,k);incY=0}
    if(RF[k]>0){if(p.reinvDed)lots.push({k0:k,amt:RF[k]});else idle+=RF[k];r.deductions+=RF[k]}
    const c=clContrib(p,k);if(c>0){lots.push({k0:k,amt:c});r.deposited+=c}
    let v=idle;for(const l of lots)v+=val(l,k);vN=v;
    cap.push(v-taxNow(k)-(k===N?RF.back:0));
  }
  r.taxes+=taxNow(N);r.deductions-=RF.back;
  const l=ldvOf(N),tot=vN;
  r.RF[N]-=RF.back;
  /* пассивный доход: дивиденды акций или продажа паёв фонда; ЛДВ освобождает долю старых лотов (пока доход в пределах лимита) */
  const inc=Math.max(0,A.pY!=null?tot*A.pY(N)/100:tot*dv/100);r.incGross=inc;
  const oldShare=tot>0?Math.min(1,l.old/tot):0;
  r.passive=ai.exempt?inc/12:(inc-clNdfl(inc*(A.fund&&p.ldv&&!ai.iis?1-oldShare:1),sc))/12;
  return r;
}
/* Облигации и «ставка + купонный налог». Три вида: с фиксированным купоном (держим до погашения; переоценка по дюрации при росте/падении ставок), флоатеры (купон = ключевая + спред,
   цена около номинала), замещающие (купон в валюте, плюс рублёвая курсовая переоценка, которая облагается при погашении или продаже).
   Купоны реинвестируются; НДФЛ удерживается раз в год и при выводе в конце срока, на ИИС — только при закрытии. Налог платится из свободных денег, затем продажей части облигаций ПО РЫНОЧНОЙ ЦЕНЕ.
   Дефолты — дискретные события по траншам (rng задан: вероятность сегмента, потеря 75 %), а не равномерная усушка. */
function clSimBond(p,env,seg,rng){
  const N=p.months,sc=p.sc>0?p.sc:1,ai=clAccInfo(p),RF=clRefunds(p,ai),f=p.freq,per=Math.max(1,Math.round(12/f));
  const y0=seg.yield,beta=seg.beta||0,fl=!!seg.fl,fx=seg.fx!=null&&seg.fx!==0;
  const matM=fl?Infinity:(seg.dur>0?Math.max(Math.round(seg.dur*12),per):Infinity);
  const ynew=k=>k===0?y0:Math.max(.5,y0+beta*(env.key(k)-env.kr0));
  const pd=seg.loss>0?Math.min(.99,seg.loss/100/CL_LGD):0,pm=rng&&p.defaults&&pd>0?1-Math.pow(1-pd,1/12):0;
  const px=(t,k)=>{if(t.fl)return 1;const d=t.mat<Infinity?Math.max(0,(t.mat-k)/12):(seg.dur||0);return Math.max(.5,Math.min(1.3,1-d*(ynew(k)-t.y)/100))};
  const tr=[],cap=[],r={cap,deposited:0,deductions:0,taxes:0,notes:[],RF:RF.slice(),back:RF.back,defaults:0};
  let cashInv=0,idle=0,pot=0,incY=0,incTot=0;const useLot=p.lot>1;
  const unreal=k=>{let c=0;for(const t of tr)c+=t.amt*px(t,k)-t.basis;return c};
  /* начисленный, но не удержанный налог: на ИИС — весь доход в год закрытия (ИИС-3 — сверх лимита освобождения) */
  const due=k=>{const c=unreal(k);return ai.iis?clNdfl(ai.exempt?Math.max(0,incTot+c-ai.cap):Math.max(0,incTot+c),sc):clNdfl(Math.max(0,incY+c),sc)};
  const pay=(x,k)=>{if(!(x>0))return;r.taxes+=x;let t;
    t=Math.min(idle,x);idle-=t;x-=t;t=Math.min(cashInv,x);cashInv-=t;x-=t;t=Math.min(pot,x);pot-=t;x-=t;
    if(x>0){let mv=0;for(const z of tr)mv+=z.amt*px(z,k);if(mv>0){const q=Math.max(0,1-x/mv);tr.forEach(z=>{z.amt*=q;z.basis*=q})}}};
  for(let k=0;k<=N;k++){
    if(k>0){
      if(pot>0){const g=pot*env.fundRate(k-1)/1200;pot+=g;incY+=g;incTot+=g}
      let coup=0,prin=0,gr=0;
      for(let i=tr.length-1;i>=0;i--){const t=tr[i];
        if(fx)t.amt*=env.X[k]/env.X[k-1];
        if(pm&&!t.dead&&rng()<pm){t.amt*=1-CL_LGD;t.basis*=1-CL_LGD;t.dead=1;r.defaults++}
        if(!t.dead&&k>t.k0&&k<=t.mat&&(k-t.k0)%per===0)coup+=t.amt*(t.fl?ynew(k):t.y)/100/f;
        if(k===t.mat){prin+=t.amt;gr+=t.amt-t.basis;tr.splice(i,1)}}
      incY+=coup+gr;incTot+=coup+gr;
      if(p.reinvest)cashInv+=coup;else idle+=coup;
      cashInv+=prin;
      if(k===N)pay(due(k),k);else if(!ai.iis&&clYE(env,k)){pay(clNdfl(Math.max(0,incY),sc),k);incY=0}
    }
    if(RF[k]>0){if(p.reinvDed)cashInv+=RF[k];else idle+=RF[k];r.deductions+=RF[k]}
    const c=clContrib(p,k);cashInv+=c;r.deposited+=c;
    const avail=cashInv+pot;
    if(avail>0.005){const amt=useLot?Math.floor(avail/p.lot+1e-9)*p.lot:avail;
      if(amt>0)tr.push({k0:k,amt,basis:amt,y:ynew(k),mat:k+matM,fl});
      const rem=avail-amt;if(p.lotFund){cashInv=0;pot=rem}else{cashInv=rem;pot=0}}
    let v=idle+cashInv+pot;for(const t of tr)v+=t.amt*px(t,k);cap.push(k<N?v-due(k):v-(k===N?RF.back:0));
  }
  r.deductions-=RF.back;r.RF[N]-=RF.back;
  let inc=pot*env.fundRate(Math.max(N-1,0))/100;for(const t of tr)if(!t.dead)inc+=t.amt*(t.fl?ynew(N):t.y)/100;
  r.incGross=inc;r.passive=(inc-(ai.exempt?0:clNdfl(inc,sc)))/12;
  return r;
}
/* какие части входят в стратегию: массив {w — доля, sp — описание: dep / lots / bond}. Один тип стратегии — одна часть с долей 1; «Мой портфель» и «Микс» — смесь */
const clStk=(env)=>({G:env.E,div:env.stDiv});
const clFundA=(env)=>({G:env.G,div:0,fund:true,pY:k=>env.fundRate(k)});
function clSegBond(id,P){const s=P.segments[id]||P.segments.ofz;return{yield:s.yield,dur:s.dur,beta:CL_BETA[id]!=null?CL_BETA[id]:.7,loss:s.loss,fl:id==='flt'}}
function clFxSeg(P,F){const f=P.fx_bonds||{yield:6,fx:5};return{yield:f.yield,dur:3,beta:0,loss:P.segments.a?P.segments.a.loss:.6,fx:F.fxWeak!==''&&F.fxWeak!=null?+F.fxWeak:f.fx}}
function clParts(id,P,F){
  if(id==='dep')return[{w:1,sp:{t:'dep'}}];
  if(id==='fund')return[{w:1,sp:{t:'lots',A:clFundA}}];
  if(id==='stk')return[{w:1,sp:{t:'lots',A:clStk}}];
  if(id==='fxb')return[{w:1,sp:{t:'bond',seg:clFxSeg(P,F)}}];
  if(id==='own')return[{w:1,sp:{t:'bond',seg:{yield:+F.ownRate||0,dur:0,beta:0,loss:0}}}];
  if(id==='mix'){const ws=Math.max(0,Math.min(100,+F.mixStk>=0?+F.mixStk:50))/100,bid=P.segments[F.mixBond]?F.mixBond:'ofz',out=[];
    if(ws>0)out.push({w:ws,sp:{t:'lots',A:clStk}});if(ws<1)out.push({w:1-ws,sp:{t:'bond',seg:clSegBond(bid,P)}});return out}
  if(id==='pf'){
    const pf=P.portfolio||{},sh=pf.shares,seg={yield:pf.irr!=null?pf.irr:10,dur:pf.dur_bonds>0?pf.dur_bonds:3,beta:.7,loss:(P.segments.aa||{loss:.15}).loss};
    if(!sh)return[{w:1,sp:{t:'bond',seg}}];
    const parts=[],add=(w,sp)=>{if(w>0)parts.push({w,sp})};
    add(sh.bonds,{t:'bond',seg});add((sh.stocks||0)+(sh.funds||0),{t:'lots',A:clStk});add(sh.lqdt,{t:'lots',A:clFundA});
    add((sh.cash||0)+(sh.other||0),{t:'lots',A:()=>({G:CL_FLAT,div:0})});
    const tw=parts.reduce((a,x)=>a+x.w,0)||1;parts.forEach(x=>{x.w/=tw});return parts.length?parts:[{w:1,sp:{t:'bond',seg}}];
  }
  return[{w:1,sp:{t:'bond',seg:clSegBond(id,P)}}];
}
const CL_FLAT=new Array(721).fill(1);
function clSimPart(sp,p,env,rng){
  if(sp.t==='dep')return clSimDep(p,env);
  if(sp.t==='lots')return clSimLots(p,env,sp.A(env));
  return clSimBond(p,env,sp.seg,rng);
}
/* сборка итога из частей: суммы денежных величин, XIRR по потокам всего счёта */
function clCombine(rs,p,env,id){
  const N=p.months,r={cap:new Array(N+1).fill(0),deposited:0,deductions:0,taxes:0,passive:0,incGross:0,defaults:0,RF:new Array(N+1).fill(0),notes:[]};
  rs.forEach(x=>{for(let k=0;k<=N;k++){r.cap[k]+=x.cap[k];r.RF[k]+=x.RF[k]||0}
    r.deposited+=x.deposited;r.deductions+=x.deductions;r.taxes+=x.taxes;r.passive+=x.passive;r.incGross+=x.incGross||0;r.defaults+=x.defaults||0});
  const capN=r.cap[N];r.final=capN;r.finalReal=capN/env.D[N];r.passiveReal=r.passive/env.D[N];r.income=capN-r.deposited-r.deductions;
  const fl=new Array(N+1).fill(0);for(let k=0;k<=N;k++)fl[k]-=clContrib(p,k);fl[N]+=capN;r.xirr=clIrr(fl);
  r.taxLog=[].concat(...rs.map(x=>x.taxLog||[]));r.id=id;return r;
}
function clSim(id,p,P,env,F,rng){
  const parts=clParts(id,P,F),rs=parts.map(pt=>{const w=pt.w,ps=w===1?p:Object.assign({},p,{start:p.start*w,monthly:p.monthly*w,sc:w});return clSimPart(pt.sp,ps,env,rng)});
  return clCombine(rs,p,env,id);
}
function clParams(F,months,y0){
  return{start:+F.start||0,monthly:+F.monthly||0,idx:+F.idx||0,months:months||Math.round((+F.years||1)*12),acct:(F.acct==='iisA'||F.acct==='iisB')?'iis3':F.acct,reinvest:!!F.reinvest,freq:+F.freq||12,
    lot:+F.lot||0,lotFund:F.lotFund==='fund',reinvDed:!!F.reinvDed,ldv:!!F.ldv,defaults:!!F.defaults,iisYear:+F.iisYear||0,salRate:F.salRate!=null?+F.salRate:13,salary:+F.salary||0,y0:y0||new Date().getFullYear()};
}
/* Цель: нужное ежемесячное пополнение при заданном сроке или нужный срок при заданном пополнении (бисекция) */
function clGoal(F,P,env,sid,real){
  const T=+F.goalAmt||0,pas=(months,monthly)=>{const p=clParams(F,months,env.y0);p.monthly=monthly;const r=clSim(sid,p,P,env,F);return real===false?r.passive:r.passiveReal};
  if(F.goalMode==='years'){
    const m=clParams(F,0,env.y0).monthly;let lo=1,hi=600;
    if(pas(hi,m)<T)return{ok:false};
    if(pas(lo,m)>=T)return{ok:true,months:1};
    while(hi-lo>1){const mid=(lo+hi)>>1;if(pas(mid,m)>=T)hi=mid;else lo=mid}
    return{ok:true,months:hi};
  }
  const N=clParams(F,0,env.y0).months;let lo=0,hi=1000;
  if(pas(N,0)>=T)return{ok:true,monthly:0};
  while(pas(N,hi)<T&&hi<1e9)hi*=2;
  if(pas(N,hi)<T)return{ok:false};
  for(let i=0;i<40;i++){const mid=(lo+hi)/2;if(pas(N,mid)>=T)hi=mid;else lo=mid}
  return{ok:true,monthly:hi};
}
/* Монте-Карло: дефолты по траншам, шоки ключевой ставки и рынка акций. Возвращает квантили капитала по месяцам и разброс итога */
function clQuant(sorted,q){const n=sorted.length;if(!n)return 0;const x=q*(n-1),i=Math.floor(x),f=x-i;return i+1<n?sorted[i]*(1-f)+sorted[i+1]*f:sorted[i]}
function clMC(F,P,id,runs,seed,startDate){
  const p=clParams(F,0,(startDate||new Date()).getFullYear()),N=p.months,qs=[.1,.5,.9],cols=[],fin=[];let dfl=0;
  for(let i=0;i<N+1;i++)cols.push(new Float64Array(runs));
  const out={p10:[],p50:[],p90:[],finals:null,defaults:0,runs};
  for(let j=0;j<runs;j++){const rng=clRng((seed||1)*1000003+j*7919+1),env=clEnv(P,F,startDate,rng),r=clSim(id,p,P,env,F,rng);
    for(let k=0;k<=N;k++)cols[k][j]=r.cap[k];fin.push(r.cap[N]);dfl+=r.defaults}
  for(let k=0;k<=N;k++){const a=Array.from(cols[k]).sort((x,y)=>x-y);out.p10.push(clQuant(a,.1));out.p50.push(clQuant(a,.5));out.p90.push(clQuant(a,.9))}
  out.finals=fin.sort((x,y)=>x-y);out.defaults=dfl/runs;return out;
}
