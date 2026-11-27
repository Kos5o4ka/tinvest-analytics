/* калькулятор инвестиций: глубина аналитики — коридор исходов, сравнение двух стратегий, матрица чувствительности, цена промедления, переходы в скринер и лесенку.
   Тяжёлые блоки (случайные траектории, матрица, цена промедления) считаются в фоне после первой отрисовки и кэшируются. */
let CL_DEEP={key:'',v:{}},CL_DT=0;
const clDeepKey=(F,P,id)=>clMedKey(F,P)+'|'+id+'|'+clMode();
function clDeepGet(F,P,id,k){return CL_DEEP.key===clDeepKey(F,P,id)?CL_DEEP.v[k]:undefined}
function clDeepPut(F,P,id,k,v){const key=clDeepKey(F,P,id);if(CL_DEEP.key!==key)CL_DEEP={key,v:{}};CL_DEEP.v[k]=v}
/* коридор между стрессом и оптимизмом (серая полоса) вокруг медианы */
function clFan(el,o){
  const W=el.clientWidth,H=o.h||300,pl=62,pr=10,pt=10,pb=26,n=o.labels.length,tl=o.tipLabels||o.labels;
  if(n<2||W<50)return emptyChart(el,H,o.empty);
  const fa=o.fa||short,ft=o.ft||(v=>M(v));let mn=0,mx=0;
  [o.p10,o.p50,o.p90,o.det||[]].forEach(a=>a.forEach(v=>{mn=Math.min(mn,v);mx=Math.max(mx,v)}));
  if(mx===mn)return emptyChart(el,H,o.empty);
  const{lo,hi,step}=nice(mn,mx),pw=W-pl-pr,ph=H-pt-pb,X=i=>pl+i/(n-1)*pw,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph,P2=(v,i)=>X(i).toFixed(1)+','+Y(v).toFixed(1);
  let s='';
  for(let v=lo;v<=hi+step/2;v+=step){const y=Y(v);s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}"/><text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${fa(Math.abs(v)<step/1e6?0:v)}</text>`}
  axisTicks(o.labels,X,pl-4,W-pr+4).forEach(([i,x])=>s+=`<text class="ax" x="${x}" y="${H-6}" text-anchor="middle">${esc(o.labels[i])}</text>`);
  const up=o.p90.map(P2),dn=o.p10.map(P2).reverse();
  s+=`<polygon points="${up.concat(dn).join(' ')}" fill="var(--s3)" fill-opacity=".2"/>`;
  s+=`<polyline points="${o.p10.map(P2).join(' ')}" fill="none" stroke="var(--s8)" stroke-width="1.2" stroke-dasharray="4 3"/><polyline points="${o.p90.map(P2).join(' ')}" fill="none" stroke="var(--s1)" stroke-width="1.2" stroke-dasharray="4 3"/>`;
  if(o.det)s+=`<polyline points="${o.det.map(P2).join(' ')}" fill="none" stroke="#9aa3b5" stroke-width="1.4" stroke-dasharray="2 3"/>`;
  s+=`<polyline points="${o.p50.map(P2).join(' ')}" fill="none" stroke="var(--s3)" stroke-width="2.2" stroke-linejoin="round"/>`;
  let hits='';const cw=pw/(n-1);
  for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${X(i)-cw/2}" y="${pt}" width="${cw}" height="${ph}" fill="transparent"/>`;
  const ser=[{n:'Оптимистично (90 %)',c:'var(--s1)'},{n:'Медиана',c:'var(--s3)'},{n:'Стресс (10 %)',c:'var(--s8)'}];if(o.det)ser.push({n:'Без случайных событий',c:'#9aa3b5'});
  el.innerHTML=legend(ser)+`<svg width="${W}" height="${H}">${s}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{if(i<0){hv.innerHTML='';return}hv.innerHTML=`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph}" stroke="var(--line2)" stroke-dasharray="3 3"/>`+
    [[o.p90,'var(--s1)'],[o.p50,'var(--s3)'],[o.p10,'var(--s8)']].map(([a,c])=>`<circle cx="${X(i)}" cy="${Y(a[i])}" r="4" fill="${c}" stroke="var(--card)" stroke-width="2"/>`).join('')};
  bindTip(el,i=>`<b>${esc(tl[i])}</b>`+tipRow('var(--s1)','Оптимистично (90 %)',ft(o.p90[i]))+tipRow('var(--s3)','Медиана',ft(o.p50[i]))+tipRow('var(--s8)','Стресс (10 %)',ft(o.p10[i])));
}
/* блоки правой части вкладки «Накопить капитал» */
function clDeepHtml(F,P,run,cur){
  const {env,N,res,p}=run,real=F.real,dv=real?env.D[N]:1;
  const opts=sel=>clAvail(P).map(s=>`<option value="${s[0]}" ${s[0]===sel?'selected':''}>${s[1]}</option>`).join('');
  const aId=clAvail(P).some(s=>s[0]===F.cmpA)?F.cmpA:cur.id,bId=clAvail(P).some(s=>s[0]===F.cmpB)&&F.cmpB!==aId?F.cmpB:(clAvail(P).map(s=>s[0]).find(x=>x!==aId)||aId);
  const ra=clSim(aId,p,P,env,F),rb=clSim(bId,p,P,env,F),na=CL_STR.find(x=>x[0]===aId)[1],nb=CL_STR.find(x=>x[0]===bId)[1];
  const d=(x,y,f,lowerBetter)=>{const v=y-x,c=v===0?'':((v>0)!==!!lowerBetter?'pos':'neg');return`<td class="num ${c}">${v>0?'+':''}${f(v)}</td>`};
  const pc=v=>v==null?'—':pctp(v,2),fm=v=>clRub(v);
  const rowsC=[['Итоговый капитал',real?ra.finalReal:ra.final,real?rb.finalReal:rb.final,fm,0],['Уплачено налогов',ra.taxes,rb.taxes,fm,1],['Пассивный доход в месяц, после налога',real?ra.passiveReal:ra.passive,real?rb.passiveReal:rb.passive,fm,0],
    ['Реальная доходность после налогов, % в год',ra.xirrReal,rb.xirrReal,pc,0]];
  const cmp=`<div class="card"><h2>Сравнение двух стратегий<span class="sp">${real?'в сегодняшних деньгах':'номинал'}</span></h2>
   <div class="cl-grid cl-g2" style="margin-bottom:10px"><label class="field"><span>Стратегия А</span><select class="in" id="cl-cmpA">${opts(aId)}</select></label><label class="field"><span>Стратегия Б</span><select class="in" id="cl-cmpB">${opts(bId)}</select></label></div>
   <div class="tbl"><table><thead><tr><th class="l">Показатель</th><th>${esc(na)}</th><th>${esc(nb)}</th><th>Разница (Б − А)</th></tr></thead><tbody>${
     rowsC.map(r=>`<tr><td class="l">${r[0]}</td><td class="num">${r[3](r[1])}</td><td class="num">${r[3](r[2])}</td>${r[1]==null||r[2]==null?'<td class="num">—</td>':d(r[1],r[2],r[3],r[4])}</tr>`).join('')}</tbody></table></div>
   <div class="note" style="margin-top:8px">Зелёным отмечено, где Б лучше А. Оба расчёта идут при одинаковых счёте, сроке и взносах, без случайных событий.</div></div>`;
  const id=cur.id,box=(k,t)=>`<div id="cl-deep-${k}" data-deep="${id}">${t}</div>`;
  const fan=`<div class="card"><h2>Коридор исходов<span class="sp">${esc(cur.name)} · ${real?'в сегодняшних деньгах':'номинал'}</span></h2>${box('fan','<div class="chart"><div class="empty" style="min-height:120px;padding:20px">Считаю случайные траектории…</div></div>')}</div>`;
  const mat=`<div class="card"><h2>Чувствительность итога<span class="sp">ключевая ставка × инфляция</span></h2>${box('mat','<small class="mu">Считаю…</small>')}</div>`;
  const wait=`<div class="card"><h2>Цена промедления<span class="sp">${esc(cur.name)}</span></h2>${box('wait','<small class="mu">Считаю…</small>')}</div>`;
  return fan+cmp+`<div class="g g2">${mat}${wait}</div>`+clGoToHtml(F,{sid:cur.id,env,p});
}
/* бонус: сегмент для перехода в скринер */
function clSegFor(sid,F){return sid==='mix'?(F.mixBond||'ofz'):sid}
function clGoToHtml(F,c){
  const sid=clSegFor(c.sid,F),s=(clMkt().segments||{})[sid],bondish=['ofz','aaa','aa','a','hy','flt','pf','mix'].includes(c.sid);
  if(!bondish)return`<div class="card"><h2>Что делать сейчас</h2><div class="note">Для этой стратегии подбор облигаций не нужен. Лесенку погашений можно собрать для облигационной части капитала.</div><div class="row" style="margin-top:8px"><button type="button" class="btn ghost" data-clgo="lad">Собрать лестницу погашений</button></div></div>`;
  const name=s?s.name:(CL_STR.find(x=>x[0]===sid)||[0,'облигации'])[1],m=F.monthly>0?clRub(F.monthly)+' в месяц':'свободные деньги';
  return`<div class="card"><h2>Что делать сейчас</h2><div class="cl-ans">Чтобы пойти по этому сценарию, ${F.acct==='iis3'?'откройте ИИС-3 и ':''}пополняйте счёт на <b>${m}</b> и докупайте <b>«${esc(name)}»</b>.</div>
   <div class="row" style="margin-top:10px"><button type="button" class="btn" data-clgo="scr" data-sid="${sid}">Подобрать бумаги в скринере</button><button type="button" class="btn ghost" data-clgo="lad" data-sid="${sid}">Собрать лестницу погашений</button></div>
   <div class="note" style="margin-top:8px">Фильтры скринера подставятся под выбранный сегмент (рейтинг, срок около медианной дюрации); лесенка — на ваш стартовый капитал.</div></div>`;
}
const CL_GO_SCR={ofz:{kind:'ofz',cur:'RUB',fl:'fix'},aaa:{kind:'corp',cur:'RUB',fl:'fix',rmin:'AAA'},aa:{kind:'corp',cur:'RUB',fl:'fix',rmin:'AA-'},a:{kind:'corp',cur:'RUB',fl:'fix',rmin:'A-'},
  hy:{kind:'corp',cur:'RUB',fl:'fix',ymin:'20',ymax:'60'},flt:{cur:'RUB',fl:'float',rmin:'AA-'},pf:{cur:'RUB',fl:'fix'}};
const CL_GO_LAD={ofz:'A',aaa:'AAA',aa:'AA',a:'A',hy:'BB',flt:'AA',pf:'A'};
function clGoScr(sid){
  const seg=(clMkt().segments||{})[sid],f=Object.assign({},SCR_DEF,CL_GO_SCR[sid]||CL_GO_SCR.ofz);
  if(seg&&seg.dur>0&&sid!=='flt')f.tmax=String(Math.max(1,Math.ceil(seg.dur+1)));
  S.sf=f;S.scrPreset='';S.scrOpen=true;go('scr');
}
function clGoLad(sid){
  const F=clLoadF(),pf=clMkt().portfolio,sum=F.start>0?F.start:(pf&&pf.value)||500000;
  Object.assign(S.ladQ,{sum:String(Math.round(sum)),years:String(Math.max(1,Math.min(10,F.years))),rating:CL_GO_LAD[sid]||'A'});
  S.ladTab='build';lsSet('ta_ladtab','build');go('lad');
}
function clDeepClick(e){
  const b=e.target.closest('[data-clgo]');if(!b)return;
  if(b.dataset.clgo==='scr')clGoScr(b.dataset.sid||'ofz');else clGoLad(b.dataset.sid||'ofz');
}
function clDeepChange(e){
  const F=clLoadF();
  if(e.target.id==='cl-cmpA'||e.target.id==='cl-cmpB'){F[e.target.id==='cl-cmpA'?'cmpA':'cmpB']=e.target.value;clSave();clUpdate()}
}
/* ── фоновые расчёты ── */
function clMatrix(F,P,id){
  const DK=[-4,-2,0,2,4],DI=[-2,-1,0,1,2],out={DK,DI,v:[]};
  for(const di of DI){const row=[];for(const dk of DK){const G=Object.assign({},F,{keyShift:dk,inflShift:di}),env=clEnv(P,G),p=clParams(G,0,env.y0,P),r=clSim(id,p,P,env,G);row.push(F.real?r.finalReal:r.final)}out.v.push(row)}
  return out;
}
function clMatrixHtml(m,F,P){
  const base=m.v[2][2],kr=P.key_rate.current,sg=v=>(v>0?'+':v<0?'−':'')+Math.abs(v);
  const cell=v=>{const q=base>0?(v-base)/base:0,a=Math.min(.55,Math.abs(q)*2.2).toFixed(2);return`<td class="num" style="background:${q>=0?'rgba(52,168,114,':'rgba(224,85,85,'}${a})">${short(v)}</td>`};
  return`<div class="tbl"><table class="cl-mx"><thead><tr><th class="l">Инфляция \\ ключевая</th>${m.DK.map(k=>`<th>${sg(k)} п.п.</th>`).join('')}</tr></thead><tbody>${
    m.DI.map((di,i)=>`<tr><td class="l">${sg(di)} п.п. к прогнозу</td>${m.v[i].map((v,j)=>i===2&&j===2?`<td class="num"><b>${short(v)}</b></td>`:cell(v)).join('')}</tr>`).join('')}</tbody></table></div>
   <div class="note" style="margin-top:8px">Итоговый капитал ${F.real?'в сегодняшних деньгах':'в номинальных рублях'} при сдвиге всего пути ключевой ставки (сейчас ${pctp(kr,1)}) и годовой инфляции от прогноза. Центр — выбранный сценарий; цвет — отклонение от него.</div>`;
}
function clWaiting(F,P,id,D){
  const env=clEnv(P,F),p=clParams(F,0,env.y0,P),N=p.months;if(N<=D+11)return null;
  const base=clSim(id,p,P,env,F),target=base.finalReal,q=Object.assign({},p,{months:N-D}),r2=clSim(id,q,P,env,F),lost=target-r2.final/env.D[N-D];
  const fin=m=>clSim(id,Object.assign({},q,{monthly:m}),P,env,F).final/env.D[N-D];
  let lo=p.monthly,hi=Math.max(p.monthly*2,1000),need=null;
  if(fin(lo)>=target)need=lo;else{let g=0;while(fin(hi)<target&&g++<30)hi*=2;if(fin(hi)>=target){for(let i=0;i<40;i++){const mid=(lo+hi)/2;if(fin(mid)>=target)hi=mid;else lo=mid}need=hi}}
  return{D,target,lost,need,monthly:p.monthly};
}
function clWaitHtml(w,F){
  if(!w)return'<div class="note">Срок слишком короткий для оценки.</div>';
  const pct=w.need!=null&&w.monthly>0?(w.need/w.monthly-1)*100:null;
  return`<div class="cl-ans">Если начать на <b>${clYM(w.D)}</b> позже, то при тех же взносах итог будет меньше на <b>${clRub(w.lost)}</b> (в сегодняшних деньгах), а чтобы прийти к той же сумме, придётся пополнять ${w.need==null?'на недостижимо большие суммы':'на <b>'+clRub(w.need)+' в месяц</b>'+(pct!=null?' — на <b>'+f2(pct)+' %</b> больше':'')}.</div>
   <div class="note" style="margin-top:8px">Сравнение при том же конечном сроке: накопление идёт на ${clYM(w.D)} короче, ставки и инфляция — по тому же сценарию. Итог — в сегодняшних деньгах.</div>`;
}
function clFanHtmlParts(F,P,run,cur,q){
  const {env,N}=run,real=F.real,dv=k=>real?env.D[k]:1,{labels,tips}=clDates(env,N);
  chart('cl-fan-ch',clFan,{h:300,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных',
    p10:q.p10.map((v,k)=>v/dv(k)),p50:q.p50.map((v,k)=>v/dv(k)),p90:q.p90.map((v,k)=>v/dv(k)),det:cur.cap.map((v,k)=>v/dv(k))});
  const k=N,t=(a,l,c)=>`<div><small class="mu">${l}</small><div class="num ${c||''}"><b>${clRub(a[k]/dv(k))}</b></div></div>`;
  return`<div id="cl-fan-ch" class="chart"></div><div class="cl-fan3">${t(q.p10,'Стресс (10 %)','neg')}${t(q.p50,'Медиана')}${t(q.p90,'Оптимистично (90 %)','pos')}</div>
   <div class="note" style="margin-top:8px">${q.runs} случайных траекторий: дефолты выпусков по вероятностям сегмента${F.defaults?'':' (выключены в параметрах)'}, шоки ключевой ставки и рынка акций. Полоса — от 10 % худших до 10 % лучших исходов; в среднем дефолтов на траекторию: ${f2(q.defaults)}. Широкий хвост вниз у ВДО и акций — плата за высокую медиану.</div>`;
}
function clDeepFill(){
  clearTimeout(CL_DT);CL_DT=0;
  const F=clLoadF(),P=clMkt(),m=clMode(),tick=(fn,ms)=>{CL_DT=setTimeout(fn,ms)};
  if(m==='life'){
    const box=$('#cl-lifemc');if(!box)return;const id=box.dataset.deep;
    const put=q=>{if(!box.isConnected)return;S.charts=S.charts.filter(c=>c[0]!=='cl-lifemc-ch');
      const real=F.real,env=clEnv(P,F),N=clParams(F,0,env.y0,P).months,dv=k=>real?env.D[k]:1,{labels,tips}=clDates(env,q.p50.length-1);
      chart('cl-lifemc-ch',clFan,{h:300,labels,tipLabels:tips,fa:short,ft:v=>clRub(v),empty:'Нет данных',p10:q.p10.map((v,k)=>v/dv(k)),p50:q.p50.map((v,k)=>v/dv(k)),p90:q.p90.map((v,k)=>v/dv(k))});
      box.innerHTML=`<div id="cl-lifemc-ch" class="chart"></div><div class="cl-ans" style="margin-top:8px">Капитала хватает на весь срок в <b>${f2(q.success*100)} %</b> из ${q.runs} случайных сценариев${q.depMedian!=null?'; в остальных он обычно заканчивается через '+clYM(q.depMedian)+' после выхода':''}.</div>
       <div class="note" style="margin-top:6px">Риск последовательности доходностей: если плохие годы приходятся на начало снятия, капитал тает быстрее, чем при средней доходности.</div>`;mountCharts()};
    const hit=clDeepGet(F,P,id,'lifemc');if(hit){put(hit);return}
    tick(()=>{if(!box.isConnected)return;const q=clLifeMC(F,P,id,120,1);clDeepPut(F,P,id,'lifemc',q);put(q)},250);
    return;
  }
  if(m!=='inv')return;
  const fanBox=$('#cl-deep-fan');if(!fanBox)return;const id=fanBox.dataset.deep;
  const run=clRun(F,P),cur=run.res.find(r=>r.id===id);if(!cur)return;
  const fanPut=q=>{const b=$('#cl-deep-fan');if(!b)return;b.innerHTML=clFanHtmlParts(F,P,run,cur,q);mountCharts()};
  const matPut=mx=>{const b=$('#cl-deep-mat');if(b)b.innerHTML=clMatrixHtml(mx,F,P)};
  const waitPut=w=>{const b=$('#cl-deep-wait');if(b)b.innerHTML=clWaitHtml(w,F)};
  const steps=[['fan',()=>clMC(F,P,id,150,2),fanPut],['mat',()=>clMatrix(F,P,id),matPut],['wait',()=>({w:clWaiting(F,P,id,F.years>=5?24:12)}),x=>waitPut(x.w)]];
  const go2=i=>{
    if(i>=steps.length)return;const [k,calc,put]=steps[i];
    let v=clDeepGet(F,P,id,k);
    if(v===undefined){
      tick(()=>{if(!$('#cl-deep-'+k))return;v=calc();clDeepPut(F,P,id,k,v);put(v);go2(i+1)},i===0?300:0)}
    else{put(v);go2(i+1)}};
  go2(0);
}
/* вкладка «Жизнь с капитала»: место для коридора исходов */
function clLifeMcHtml(F,P,cur){
  return`<div class="card"><h2>Вероятность дожить<span class="sp">${esc(cur.name)}</span></h2><div id="cl-lifemc" data-deep="${cur.id}"><div class="empty" style="min-height:120px;padding:20px">Считаю случайные траектории…</div></div></div>`;
}
