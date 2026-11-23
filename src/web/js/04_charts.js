/* ── charts ── */
function nice(mn,mx,ticks=4){
  if(mx===mn){mx=mn+1}
  const raw=(mx-mn)/ticks,p=Math.pow(10,Math.floor(Math.log10(raw))),m=raw/p;
  const s=(m<=1?1:m<=2?2:m<=2.5?2.5:m<=5?5:10)*p;
  return{lo:Math.floor(mn/s+1e-9)*s,hi:Math.ceil(mx/s-1e-9)*s,step:s};
}
const rtop=(x,y,w,h,r)=>{r=Math.min(r,w/2,h);if(h<=0)return'';return`M${x},${y+h}V${y+r}Q${x},${y} ${x+r},${y}H${x+w-r}Q${x+w},${y} ${x+w},${y+r}V${y+h}Z`};
const rbot=(x,y,w,h,r)=>{r=Math.min(r,w/2,h);if(h<=0)return'';return`M${x},${y}H${x+w}V${y+h-r}Q${x+w},${y+h} ${x+w-r},${y+h}H${x+r}Q${x},${y+h} ${x},${y+h-r}Z`};
const legend=ser=>ser.length>1?`<div class="legend">${ser.map(s=>`<span><i style="background:${s.c}"></i>${esc(s.n)}</span>`).join('')}</div>`:'';
function emptyChart(el,h,t){el.innerHTML=`<div class="empty" style="min-height:${h}px;padding:20px">${svgI('<path d="M3 3v18h18M7 15l4-4 3 3 5-6"/>')}<div>${t||'Нет данных за период'}</div></div>`}

/* мини-график цены: цвет по знаку изменения (порог 0,15 %) */
function spark(v,w=64,h=18){
  if(!v||v.length<2)return'';
  const a=Math.min(...v),b=Math.max(...v),k=b>a?(h-2)/(b-a):0,n=v.length-1,f=v[0],l=v[n],c=l>f*1.0015?'pos':l<f*.9985?'neg':'mu';
  return`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${v.map((y,i)=>(1+i*(w-2)/n).toFixed(1)+','+(h-1-(y-a)*k).toFixed(1)).join(' ')}" fill="none" stroke="var(--${c})" stroke-width="1.4"/></svg>`;
}

let _axc;
/* подписи оси X: шаг подбирается по ширине текста, пересекающиеся подписи отбрасываются (первую/последнюю принудительно не добавляем) */
function axisTicks(labels,X,x0,x1,gap=12){
  const n=labels.length;if(!n)return[];
  if(!_axc)_axc=document.createElement('canvas').getContext('2d');
  _axc.font='11px Inter,"SF Pro Text",-apple-system,"Segoe UI",Roboto,system-ui,sans-serif';
  const ws=labels.map(l=>_axc.measureText(String(l)).width),mw=Math.max(...ws);
  const pitch=n>1?Math.abs(X(n-1)-X(0))/(n-1):x1-x0,every=Math.max(1,Math.ceil((mw+gap)/Math.max(pitch,1)));
  const out=[];let last=-1e9;
  for(let i=0;i<n;i+=every){
    const w=ws[i];let c=X(i);c=Math.max(x0+w/2,Math.min(x1-w/2,c));
    if(c-w/2<last+gap)continue;
    out.push([i,c]);last=c+w/2;
  }
  return out;
}

/* «красивая» шкала с запасом ~10 % сверху/снизу, если крайнее значение упирается в край */
function niceP(mn,mx,t){
  let r=nice(mn,mx,t);
  if(mx>0&&r.hi-mx<(r.hi-r.lo)*.05)r=nice(mn,mx+(mx-mn)*.1,t);
  if(mn<0&&mn-r.lo<(r.hi-r.lo)*.05)r=nice(mn-(mx-mn)*.1,mx,t);
  return r;
}
/* градиенты столбиков: сверху цвет серии 100 %, снизу ~70 %; id уникальны на каждую отрисовку */
let _gidN=0;
function gradSet(){
  const m={},defs=[],pre='gb'+(++_gidN)+'_';
  return{u:c=>{if(!m[c]){const id=pre+defs.length;m[c]=id;defs.push(`<linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" style="stop-color:${c}"/><stop offset="1" style="stop-color:${c};stop-opacity:.7"/></linearGradient>`)}return`url(#${m[c]})`},defs:()=>defs.length?`<defs>${defs.join('')}</defs>`:''};
}
/* анимация появления — только при первом показе графика с данным id (перерисовки и resize не анимируются) */
const _animSeen=new Map();
function animOnce(el){
  const k=el.id;if(!k)return false;
  if(window.matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches)return false;
  const t=Date.now(),t0=_animSeen.get(k);
  if(t0==null){_animSeen.set(k,t);return true}
  return t-t0<1300; /* перерисовка сразу после показа (догрузка данных) не обрывает анимацию */
}
const gridLines=(lo,hi,step,pl,x2,Y,fa)=>{let s='';for(let v=lo;v<=hi+step/2;v+=step){const y=Y(v),z=Math.abs(v)<step/1e6;s+=`<line class="grid-l${z?' z':''}" x1="${pl}" x2="${x2}" y1="${y}" y2="${y}"/><text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${fa(z?0:v)}</text>`}return s};

function bars(el,o){
  const W=el.clientWidth,H=o.h||240,pl=58,pr=6,pt=10,pb=26,n=o.labels.length;
  if(!n||W<50)return emptyChart(el,H,o.empty);
  const ser=o.series,k=ser.length,stack=!!o.stack,fa=o.fa||short,ft=o.ft||(v=>M(v));
  let mn=0,mx=0;
  for(let i=0;i<n;i++){if(stack){let p=0,q=0;ser.forEach(s=>{const v=s.v[i]||0;v>0?p+=v:q+=v});mx=Math.max(mx,p);mn=Math.min(mn,q)}
    else ser.forEach(s=>{mx=Math.max(mx,s.v[i]||0);mn=Math.min(mn,s.v[i]||0)})}
  if(mx===0&&mn===0)return emptyChart(el,H,o.empty);
  const{lo,hi,step}=niceP(mn,mx),pw=W-pl-pr,ph=H-pt-pb,gw=pw/n,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  const cols=stack?1:k,gap=3,raw=(gw*.62-(cols-1)*gap)/cols,bw=Math.max(Math.min(6,gw*.8/cols),Math.min(cols>1?44:56,raw)),R=5;
  const G=gradSet(),an=animOnce(el),y0=Y(0);
  let s=gridLines(lo,hi,step,pl,W-pr,Y,fa);
  const bx=i=>pl+gw*i+gw/2,bt=axisTicks(o.labels,bx,pl-4,W-pr+4);
  let marks='',hits='';
  for(let i=0;i<n;i++){
    const gx=pl+gw*i,x0=gx+(gw-(cols*bw+(cols-1)*gap))/2;
    let pp=0,nn=0,gm='';const pos=[],neg=[];
    ser.forEach((se,j)=>{const v=se.v[i]||0;if(!v)return;
      if(stack){if(v>0){pos.push([j,pp,pp+v]);pp+=v}else{neg.push([j,nn+v,nn]);nn+=v}}
      else{const x=x0+j*(bw+gap),y=v>0?Y(v):Y(0),h=Math.abs(Y(v)-Y(0)),c=o.colorOf?o.colorOf(v,i):se.c;
        gm+=`<path class="bm" d="${v>0?rtop(x,y,bw,h,R):rbot(x,y,bw,h,R)}" fill="${G.u(c)}"/>`}});
    if(stack){
      pos.forEach(([j,a,b],q)=>{const y1=Y(b),ya=Y(a),h=Math.max(0,ya-y1-(q?1.5:0));gm+=`<path class="bm" d="${q===pos.length-1?rtop(x0,y1,bw,h,R):`M${x0},${y1}h${bw}v${h}h${-bw}Z`}" fill="${G.u(ser[j].c)}"/>`});
      neg.forEach(([j,a,b],q)=>{const yb=Y(b),h=Math.max(0,Y(a)-yb-(q?1.5:0));gm+=`<path class="bm" d="${q===neg.length-1?rbot(x0,yb+(q?1.5:0),bw,h,R):`M${x0},${yb+(q?1.5:0)}h${bw}v${h}h${-bw}Z`}" fill="${G.u(ser[j].c)}"/>`});
    }
    marks+=`<g class="bg" data-g="${i}" style="transform-origin:0 ${y0}px;animation-delay:${Math.min(i,24)*18}ms">${gm}</g>`;
    if(o.labelsOn){const v=ser[0].v[i];if(v)s+=`<text class="ax num" x="${gx+gw/2}" y="${v>0?Y(v)-5:Y(v)+12}" text-anchor="middle" style="fill:var(--tx2)">${fa(v)}</text>`}
    hits+=`<rect data-i="${i}" x="${gx}" y="${pt}" width="${gw}" height="${ph}" fill="transparent"/>`;
  }
  bt.forEach(([i,x])=>s+=`<text class="ax" x="${x}" y="${H-6}" text-anchor="middle">${esc(o.labels[i])}</text>`);
  el.innerHTML=(o.legend===false?'':legend(ser))+`<svg width="${W}" height="${H}"${an?' class="anim"':''}>${G.defs()}${s}<g>${marks}</g>${hits}</svg>`;
  const mk=el.querySelectorAll('.bg');
  el._hl=i=>mk.forEach(p=>p.style.opacity=i<0||+p.dataset.g===i?'':.45);
  bindTip(el,i=>{let h=`<b>${esc(o.tipLabels?o.tipLabels[i]:o.labels[i])}</b>`;ser.forEach(se=>{const v=se.v[i]||0;if(v||!o.skipZero)h+=tipRow(o.colorOf?o.colorOf(v,i):se.c,se.n,ft(v))});
    if(o.total){const t=ser.reduce((a,se)=>a+(se.v[i]||0),0);h+=`<div class="tot">Итого<span>${ft(t)}</span></div>`}return h});
}

function line(el,o){
  const W=el.clientWidth,H=o.h||240,pl=62,pr=14,pt=12,pb=26;
  let labels=o.labels,ser=o.series,tl=o.tipLabels||labels;
  if(labels.length>420){const k=Math.ceil(labels.length/420),idx=[];for(let i=0;i<labels.length;i+=k)idx.push(i);if(idx[idx.length-1]!==labels.length-1)idx.push(labels.length-1);
    labels=idx.map(i=>labels[i]);tl=idx.map(i=>(o.tipLabels||o.labels)[i]);ser=ser.map(s=>({...s,v:idx.map(i=>s.v[i])}))}
  const n=labels.length;
  if(n<2||W<50)return emptyChart(el,H,o.empty);
  const fa=o.fa||short,ft=o.ft||(v=>M(v));
  let mn=Infinity,mx=-Infinity;
  ser.forEach(s=>s.v.forEach(v=>{if(v==null||isNaN(v))return;mn=Math.min(mn,v);mx=Math.max(mx,v)}));
  if(o.zero!==false)mn=Math.min(mn,0);if(!isFinite(mn))return emptyChart(el,H,o.empty);
  if(mx===mn){if(mx===0)return emptyChart(el,H,o.empty);const d=Math.abs(mx)*.02;mn-=d;mx+=d}
  const{lo,hi,step}=niceP(mn,mx),pw=W-pl-pr,ph=H-pt-pb,X=i=>pl+i/(n-1)*pw,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  const an=animOnce(el);
  let s=gridLines(lo,hi,step,pl,W-pr,Y,fa);
  axisTicks(labels,X,pl-4,W-pr+4).forEach(([i,x])=>s+=`<text class="ax" x="${x}" y="${H-6}" text-anchor="middle">${esc(labels[i])}</text>`);
  const gid='g'+Math.random().toString(36).slice(2,8);
  if(o.band){const A=ser[o.band.a].v,B=ser[o.band.b].v,poly=(pts,up)=>{if(pts.length>2)s+=`<polygon points="${pts.map(q=>q[0].toFixed(1)+','+q[1].toFixed(1)).join(' ')}" fill="${up?'var(--neg)':'var(--pos)'}" fill-opacity=".2"/>`};
    for(let i=0;i<n-1;i++){const a0=A[i],a1=A[i+1],b0=B[i],b1=B[i+1];if([a0,a1,b0,b1].some(v=>v==null||isNaN(v)))continue;
      const d0=a0-b0,d1=a1-b1,x0=X(i),x1=X(i+1);
      if(d0*d1>=0)poly([[x0,Y(a0)],[x1,Y(a1)],[x1,Y(b1)],[x0,Y(b0)]],d0+d1>0);
      else{const t=d0/(d0-d1),xc=x0+(x1-x0)*t,yc=Y(a0+(a1-a0)*t);poly([[x0,Y(a0)],[xc,yc],[x0,Y(b0)]],d0>0);poly([[xc,yc],[x1,Y(a1)],[x1,Y(b1)]],d1>0)}}}
  let ends='';
  ser.forEach((se,j)=>{
    const segs=[];let cur=[],pv=null,last=-1;se.v.forEach((v,i)=>{if(v==null||isNaN(v)){if(cur.length)segs.push(cur);cur=[];pv=null}else{if(se.step&&pv!=null)cur.push(X(i).toFixed(1)+','+Y(pv).toFixed(1));cur.push(X(i).toFixed(1)+','+Y(v).toFixed(1));pv=v;last=i}});if(cur.length)segs.push(cur);
    if(j===0&&o.area){const base=Y(Math.max(lo,Math.min(0,hi)));s+=`<defs><linearGradient id="${gid}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" style="stop-color:${se.c};stop-opacity:${o.area==='neg'?0:.22}"/><stop offset="1" style="stop-color:${se.c};stop-opacity:${o.area==='neg'?.22:0}"/></linearGradient></defs>`;
      segs.forEach(sg=>{const f=sg[0].split(','),l=sg[sg.length-1].split(',');s+=`<polygon class="la" points="${f[0]},${base} ${sg.join(' ')} ${l[0]},${base}" fill="url(#${gid})"/>`})}
    segs.forEach(sg=>s+=`<polyline${se.dash?' class="ls"':' class="ln" pathLength="1"'} points="${sg.join(' ')}" fill="none" stroke="${se.c}" stroke-width="${se.w||2}" stroke-linejoin="round" stroke-linecap="round"${se.dash?' stroke-dasharray="5 4"':''}/>`);
    if(!se.dash&&last>=0)ends+=`<g class="ld"><circle cx="${X(last).toFixed(1)}" cy="${Y(se.v[last]).toFixed(1)}" r="8" fill="${se.c}" fill-opacity=".18"/><circle cx="${X(last).toFixed(1)}" cy="${Y(se.v[last]).toFixed(1)}" r="3.5" fill="${se.c}" stroke="var(--card)" stroke-width="1.5"/></g>`});
  let hits='';const cw=pw/(n-1);
  for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${X(i)-cw/2}" y="${pt}" width="${cw}" height="${ph}" fill="transparent"/>`;
  el.innerHTML=legend(ser)+`<svg width="${W}" height="${H}"${an?' class="anim"':''}>${s}${ends}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{if(i<0){hv.innerHTML='';return}hv.innerHTML=`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph}" stroke="var(--line2)" stroke-width="1" stroke-dasharray="3 3"/>`+
    ser.filter(se=>se.v[i]!=null&&!isNaN(se.v[i])).map(se=>`<circle cx="${X(i)}" cy="${Y(se.v[i])}" r="4.5" fill="${se.c}" stroke="var(--card)" stroke-width="2"/>`).join('')};
  bindTip(el,i=>{o.hover&&o.hover(i);if(o.tip)return o.tip(i);return`<b>${esc(tl[i])}</b>`+ser.filter(se=>se.v[i]!=null&&!isNaN(se.v[i])).map(se=>tipRow(se.c,se.n,ft(se.v[i]))).join('')});
  if(o.leave){const ol=el.onmouseleave;el.onmouseleave=e=>{ol(e);o.leave()}}
}

function donut(el,o){
  const items=o.items.filter(x=>x.v>0.005),tot=items.reduce((a,x)=>a+x.v,0),D=o.size||180,R=D/2,r=R*.62;
  if(!tot)return emptyChart(el,D,'Нет активов');
  const an=animOnce(el);
  let a=-Math.PI/2,arcs='';
  items.forEach((x,i)=>{const da=x.v/tot*Math.PI*2,a0=a,a1=a+da;a+=da;if(a1<=a0)return;
    const big=a1-a0>Math.PI?1:0,p=(t,rr)=>[R+rr*Math.cos(t),R+rr*Math.sin(t)].map(v=>v.toFixed(2)).join(',');
    const d=items.length===1?`M${R},0A${R},${R} 0 1 1 ${R-0.01},0L${R-0.01},${R-r}A${r},${r} 0 1 0 ${R},${R-r}Z`:
      `M${p(a0,R)}A${R},${R} 0 ${big} 1 ${p(a1,R)}L${p(a1,r)}A${r},${r} 0 ${big} 0 ${p(a0,r)}Z`;
    arcs+=`<path data-i="${i}" class="arc" d="${d}" fill="${x.c}" stroke="${items.length>1?'var(--card)':'none'}" stroke-width="2" stroke-linejoin="round" style="transform-origin:${R}px ${R}px;animation-delay:${i*40}ms"/>`});
  const tx=short(tot)+(o.unit===''?'':' ₽'),fs=tx.length>10?16:tx.length>8?18:21;
  el.innerHTML=`<div class="donut-wrap"><svg width="${D}" height="${D}" style="flex:none"${an?' class="anim"':''}>${arcs}
    <text x="${R}" y="${R-3}" text-anchor="middle" class="dn-v num" style="font-size:${fs}px">${tx}</text>
    <text x="${R}" y="${R+16}" text-anchor="middle" class="dn-c">${esc(o.cap||'Всего')}</text></svg>
    <div class="dl">${items.map((x,i)=>`<div data-i="${i}"><i style="background:${x.c}"></i><span>${esc(x.n)}</span><b class="num" style="font-weight:600">${short(x.v)}</b><em class="num">${(x.v/tot*100).toFixed(1).replace('.',',')}%</em></div>`).join('')}</div></div>`;
  const arcsEl=el.querySelectorAll('.arc'),rows=el.querySelectorAll('.dl>div');
  el._hl=i=>{arcsEl.forEach(p=>{const on=+p.dataset.i===i;p.style.opacity=i<0||on?'':.4;p.style.transform=on?'scale(1.035)':''});rows.forEach(d=>d.style.opacity=i<0||+d.dataset.i===i?'':.5)};
  bindTip(el,i=>`<b>${esc(items[i].n)}</b>`+tipRow(items[i].c,'Стоимость',M(items[i].v))+tipRow(items[i].c,'Доля',(items[i].v/tot*100).toFixed(1).replace('.',',')+' %'));
}

function hbars(items,color,fmt,wide){
  if(!items.length)return'<div class="empty" style="padding:24px">Нет данных</div>';
  const mx=Math.max(...items.map(x=>Math.abs(x.v)),1);
  return`<div class="hb${wide?' w':''}">${items.map(x=>`<div class="r"><span class="n" title="${esc(x.n)}">${esc(x.n)}</span><div class="tr"><b style="width:${Math.max(1.5,Math.abs(x.v)/mx*100)}%;background:${x.c||color}"></b></div><span class="vv num">${fmt?fmt(x):M(x.v)}${x.s?`<br><small class="${x.sc||'mu'}">${x.s}</small>`:''}</span></div>`).join('')}</div>`;
}
function chart(id,fn,o){S.charts.push([id,fn,o])}
function mountCharts(){S.charts.forEach(([id,fn,o])=>{const el=document.getElementById(id);if(el)try{fn(el,o)}catch(e){console.error(e);el.innerHTML='<div class="empty">Не удалось построить график</div>'}})}
let rT;addEventListener('resize',()=>{clearTimeout(rT);rT=setTimeout(mountCharts,120)});


/* ── столбцы по месяцам, сложенные по сериям (выпускам); прогнозная часть светлее, CALL — отдельный столбец со штриховкой ──
   o: {h, labels:[...], months:[{segs:[{k,v,est}], call:number}], colors:{k:цвет}, names:{k:имя}, fa, ft, empty,
       vl:true — подписи значений над столбцами (итог месяца; CALL — фиолетовым), fv — формат подписи (по умолчанию short)} */
/* выбор подписей, которые не налезают друг на друга: items [{x,y,w,v}] — центр, базовая линия, ширина; важнее те, что больше */
function barLabelsPick(items,lh){
  const keep=[],ok=(a,b)=>Math.abs(a.x-b.x)<(a.w+b.w)/2+3&&Math.abs(a.y-b.y)<lh;
  items.slice().sort((a,b)=>b.v-a.v).forEach(it=>{if(!keep.some(k=>ok(k,it)))keep.push(it)});
  return keep;
}
function stackedMonths(el,o){
  const W=el.clientWidth,H=o.h||260,pl=58,pr=6,pt=o.vl?22:10,pb=26,n=o.labels.length,fa=o.fa||short,ft=o.ft||(v=>short(v)+' ₽');
  if(!n||W<50)return emptyChart(el,H,o.empty);
  const tot=m=>m.segs.reduce((a,s)=>a+s.v,0);
  let mx=0;o.months.forEach(m=>{mx=Math.max(mx,tot(m),m.call||0)});
  if(!mx)return emptyChart(el,H,o.empty);
  const{lo,hi,step}=niceP(0,mx),pw=W-pl-pr,ph=H-pt-pb,gw=pw/n,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  const hasCall=o.months.some(m=>m.call>0),cols=hasCall?2:1,gap=3,raw=(gw*.62-(cols-1)*gap)/cols,bw=Math.max(Math.min(6,gw*.8/cols),Math.min(cols>1?36:48,raw)),R=5;
  const uid='sm'+Math.random().toString(36).slice(2,7),G=gradSet(),an=animOnce(el),y0=Y(0);
  let s=`<defs><pattern id="${uid}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--card)"/><rect width="2.6" height="6" fill="var(--s4)"/></pattern></defs>`,marks='',hits='';
  s+=gridLines(lo,hi,step,pl,W-pr,Y,fa);
  const bt=axisTicks(o.labels,i=>pl+gw*i+gw/2,pl-4,W-pr+4);
  const vls=[];
  o.months.forEach((m,i)=>{
    const gx=pl+gw*i,x0=gx+(gw-(cols*bw+(cols-1)*gap))/2;let acc=0,gm='';
    const vs=m.segs.filter(sg=>sg.v>0);
    vs.forEach((sg,q)=>{const y1=Y(acc+sg.v),ya=Y(acc),h=Math.max(0,ya-y1-(q?1:0)),c=o.colors[sg.k]||'var(--s1)',last=q===vs.length-1;
      gm+=`<path class="bm" d="${last?rtop(x0,y1,bw,h,R):`M${x0},${y1}h${bw}v${h}h${-bw}Z`}" fill="${G.u(c)}"${sg.est?' opacity=".5"':''}/>`;acc+=sg.v});
    if(m.call>0){const x=x0+(cols-1)*(bw+gap),y=Y(m.call);gm+=`<path class="bm" d="${rtop(x,y,bw,Math.max(0,Y(0)-y),R)}" fill="url(#${uid})" stroke="var(--s4)" stroke-width="1"/>`}
    marks+=`<g class="bg" data-g="${i}" style="transform-origin:0 ${y0}px;animation-delay:${Math.min(i,24)*18}ms">${gm}</g>`;
    hits+=`<rect data-i="${i}" x="${gx}" y="${pt}" width="${gw}" height="${ph}" fill="transparent"/>`;
    if(o.vl){const fv=o.fv||short,cw=11*.56,t=tot(m);
      if(t>0){const tx=fv(t);vls.push({x:x0+bw/2,y:Y(t)-5,w:tx.length*cw,v:t,tx,c:''})}
      if(m.call>0){const tx=fv(m.call);vls.push({x:x0+(cols-1)*(bw+gap)+bw/2,y:Y(m.call)-5,w:tx.length*cw,v:m.call,tx,c:' vl-call'})}}
  });
  bt.forEach(([i,x])=>s+=`<text class="ax" x="${x}" y="${H-6}" text-anchor="middle">${esc(o.labels[i])}</text>`);
  let vt='';
  if(o.vl)barLabelsPick(vls,13).forEach(l=>{const x=Math.max(pl+l.w/2,Math.min(W-pr-l.w/2,l.x));vt+=`<text class="ax num vl${l.c}" x="${x}" y="${l.y}" text-anchor="middle"${l.c?' style="fill:var(--s7)"':''}>${esc(l.tx)}</text>`});
  el.innerHTML=`<svg width="${W}" height="${H}"${an?' class="anim"':''}>${G.defs()}${s}<g>${marks}</g>${vt}${hits}</svg>`;
  const mk=el.querySelectorAll('.bg');
  el._hl=i=>mk.forEach(p=>p.style.opacity=i<0||+p.dataset.g===i?'':.45);
  bindTip(el,i=>{const m=o.months[i];let h=`<b>${esc(o.tipLabels?o.tipLabels[i]:o.labels[i])}</b>`;
    m.segs.filter(x=>x.v>0).forEach(x=>{h+=tipRow(o.colors[x.k]||'var(--s1)',(o.names[x.k]||x.k)+(x.est?' (прогноз)':''),ft(x.v))});
    if(m.call>0)h+=tipRow('var(--s4)','возможный CALL',ft(m.call));
    h+=`<div class="tot">Итого<span>${ft(tot(m))}</span></div>`;return h});
}


/* ── свечной график: candles(id|элемент, data, opts) ──
   data: [{t,o,h,l,c,v}]. opts: {h, volume:false — без объёма, lines:[{v:[…по свечам],c,n,w}], band:{up:[…],low:[…],c}, levels:[{p,kind:'s'|'r'}],
   labelOf(t) — подпись оси X, fmt(v) — формат цены, ft(i) — свой HTML подсказки, hover(i), empty}. Рост — var(--pos), падение — var(--neg). */
function candles(id,data,o){
  o=o||{};const el=typeof id==='string'?document.getElementById(id):id;if(!el)return;
  const W=el.clientWidth,H=o.h||380,pl=58,pr=10,pt=10,pb=24,n=(data||[]).length;
  if(n<2||W<80)return emptyChart(el,H,o.empty);
  const fmt=o.fmt||(v=>(+v).toLocaleString('ru-RU',{maximumFractionDigits:v>=100?2:4})),lab=o.labelOf||(t=>t);
  const vh=o.volume===false?0:Math.round((H-pt-pb)*.2),ph=H-pt-pb-vh-(vh?8:0),pw=W-pl-pr;
  let mn=Infinity,mx=-Infinity;
  data.forEach(c=>{mn=Math.min(mn,c.l);mx=Math.max(mx,c.h)});
  if(o.band){o.band.up.forEach(v=>{if(v!=null)mx=Math.max(mx,v)});o.band.low.forEach(v=>{if(v!=null)mn=Math.min(mn,v)})}
  if(mx===mn){mx=mn*1.01+1e-6}
  const padv=(mx-mn)*.03,{lo,hi,step}=nice(mn-padv,mx+padv,5),Y=v=>pt+ph-(v-lo)/(hi-lo)*ph,X=i=>pl+(i+.5)/n*pw,gw=pw/n,bw=Math.max(1,Math.min(14,gw*.7));
  let s='';
  for(let v=lo;v<=hi+step/2;v+=step){const y=Y(v);s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}"/><text class="ax num" x="${pl-8}" y="${y+4}" text-anchor="end">${fmt(+v.toFixed(6))}</text>`}
  axisTicks(data.map(c=>lab(c.t)),X,pl-4,W-pr+4,18).forEach(([i,x])=>s+=`<text class="ax" x="${x}" y="${H-6}" text-anchor="middle">${esc(lab(data[i].t))}</text>`);
  if(o.band){const pts=[],bt=[];for(let i=0;i<n;i++){const u=o.band.up[i],l=o.band.low[i];if(u==null||l==null)continue;pts.push(X(i).toFixed(1)+','+Y(u).toFixed(1));bt.push(X(i).toFixed(1)+','+Y(l).toFixed(1))}
    if(pts.length>1)s+=`<polygon points="${pts.join(' ')} ${bt.reverse().join(' ')}" fill="${o.band.c||'#7a8cff'}" fill-opacity=".1" stroke="${o.band.c||'#7a8cff'}" stroke-opacity=".5" stroke-width="1"/>`}
  (o.levels||[]).forEach(L=>{if(L.p<lo||L.p>hi)return;const c=L.kind==='r'?'var(--neg)':'var(--pos)',y=Y(L.p);
    s+=`<line x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}" stroke="${c}" stroke-opacity=".6" stroke-dasharray="5 4"/><text class="ax num" x="${W-pr-4}" y="${y-4}" text-anchor="end" style="fill:${c}">${fmt(L.p)}</text>`});
  let marks='',vol='';
  if(vh){const vm=Math.max(...data.map(c=>c.v||0),1),vy=pt+ph+8;
    data.forEach((c,i)=>{const h=Math.max(1,(c.v||0)/vm*vh);vol+=`<rect x="${X(i)-bw/2}" y="${vy+vh-h}" width="${bw}" height="${h}" fill="${c.c>=c.o?'var(--pos)':'var(--neg)'}" opacity=".45"/>`})}
  data.forEach((c,i)=>{const up=c.c>=c.o,col=up?'var(--pos)':'var(--neg)',x=X(i),yo=Y(c.o),yc=Y(c.c);
    marks+=`<line x1="${x}" x2="${x}" y1="${Y(c.h)}" y2="${Y(c.l)}" stroke="${col}" stroke-width="1"/><rect x="${x-bw/2}" y="${Math.min(yo,yc)}" width="${bw}" height="${Math.max(1,Math.abs(yc-yo))}" fill="${col}"/>`});
  (o.lines||[]).forEach(L=>{const pts=[];L.v.forEach((v,i)=>{if(v!=null&&v>=lo&&v<=hi)pts.push(X(i).toFixed(1)+','+Y(v).toFixed(1))});
    if(pts.length>1)s+=`<polyline points="${pts.join(' ')}" fill="none" stroke="${L.c}" stroke-width="${L.w||1.5}" stroke-linejoin="round"/>`});
  let hits='';for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${pl+gw*i}" y="${pt}" width="${gw}" height="${H-pt-pb}" fill="transparent"/>`;
  el.innerHTML=`<svg width="${W}" height="${H}">${s}${vol}${marks}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{if(i<0){hv.innerHTML='';return}hv.innerHTML=`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph+vh+8}" stroke="var(--line2)" stroke-dasharray="3 3"/>`};
  bindTip(el,i=>{o.hover&&o.hover(i);if(o.ft)return o.ft(i);const c=data[i],up=c.c>=c.o;
    let h=`<b>${esc(lab(c.t))}</b>`+tipRow(up?'var(--pos)':'var(--neg)','Закрытие',fmt(c.c))+tipRow('var(--mu)','Открытие',fmt(c.o))+tipRow('var(--mu)','Максимум',fmt(c.h))+tipRow('var(--mu)','Минимум',fmt(c.l));
    if(c.v)h+=tipRow('var(--mu)','Объём',short(c.v));
    (o.lines||[]).forEach(L=>{if(L.v[i]!=null)h+=tipRow(L.c,L.n,fmt(L.v[i]))});return h});
}
