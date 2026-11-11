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

function bars(el,o){
  const W=el.clientWidth,H=o.h||240,pl=58,pr=6,pt=8,pb=26,n=o.labels.length;
  if(!n||W<50)return emptyChart(el,H,o.empty);
  const ser=o.series,k=ser.length,stack=!!o.stack,fa=o.fa||short,ft=o.ft||(v=>M(v));
  let mn=0,mx=0;
  for(let i=0;i<n;i++){if(stack){let p=0,q=0;ser.forEach(s=>{const v=s.v[i]||0;v>0?p+=v:q+=v});mx=Math.max(mx,p);mn=Math.min(mn,q)}
    else ser.forEach(s=>{mx=Math.max(mx,s.v[i]||0);mn=Math.min(mn,s.v[i]||0)})}
  if(mx===0&&mn===0)return emptyChart(el,H,o.empty);
  const{lo,hi,step}=nice(mn,mx),pw=W-pl-pr,ph=H-pt-pb,gw=pw/n,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  const cols=stack?1:k,gap=2,bw=Math.max(2,Math.min(30,(gw*.72-(cols-1)*gap)/cols));
  let s='';
  for(let v=lo;v<=hi+step/2;v+=step){const y=Y(v);s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}"${Math.abs(v)<step/1e6?' style="stroke:#ffffff26"':''}/><text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${fa(Math.abs(v)<step/1e6?0:v)}</text>`}
  const bx=i=>pl+gw*i+gw/2,bt=axisTicks(o.labels,bx,pl-4,W-pr+4);
  let marks='',hits='';
  for(let i=0;i<n;i++){
    const gx=pl+gw*i,x0=gx+(gw-(cols*bw+(cols-1)*gap))/2;
    let pp=0,nn=0;const pos=[],neg=[];
    ser.forEach((se,j)=>{const v=se.v[i]||0;if(!v)return;
      if(stack){if(v>0){pos.push([j,pp,pp+v]);pp+=v}else{neg.push([j,nn+v,nn]);nn+=v}}
      else{const x=x0+j*(bw+gap),y=v>0?Y(v):Y(0),h=Math.abs(Y(v)-Y(0)),c=o.colorOf?o.colorOf(v,i):se.c;
        marks+=`<path class="bm" data-g="${i}" d="${v>0?rtop(x,y,bw,h,4):rbot(x,y,bw,h,4)}" fill="${c}"/>`}});
    if(stack){
      pos.forEach(([j,a,b],q)=>{const y1=Y(b),y0=Y(a),h=Math.max(0,y0-y1-(q?gap:0));marks+=`<path class="bm" data-g="${i}" d="${q===pos.length-1?rtop(x0,y1,bw,h,4):`M${x0},${y1}h${bw}v${h}h${-bw}Z`}" fill="${ser[j].c}"/>`});
      neg.forEach(([j,a,b],q)=>{const y0=Y(b),h=Math.max(0,Y(a)-y0-(q?gap:0));marks+=`<path class="bm" data-g="${i}" d="${q===neg.length-1?rbot(x0,y0+(q?gap:0),bw,h,4):`M${x0},${y0+(q?gap:0)}h${bw}v${h}h${-bw}Z`}" fill="${ser[j].c}"/>`});
    }
    if(o.labelsOn){const v=ser[0].v[i];if(v)s+=`<text class="ax num" x="${gx+gw/2}" y="${v>0?Y(v)-5:Y(v)+12}" text-anchor="middle" style="fill:var(--tx2)">${fa(v)}</text>`}
    hits+=`<rect data-i="${i}" x="${gx}" y="${pt}" width="${gw}" height="${ph}" fill="transparent"/>`;
  }
  bt.forEach(([i,x])=>s+=`<text class="ax" x="${x}" y="${H-6}" text-anchor="middle">${esc(o.labels[i])}</text>`);
  el.innerHTML=(o.legend===false?'':legend(ser))+`<svg width="${W}" height="${H}">${s}<g>${marks}</g>${hits}</svg>`;
  const mk=el.querySelectorAll('.bm');
  el._hl=i=>mk.forEach(p=>p.style.opacity=i<0||+p.dataset.g===i?1:.35);
  bindTip(el,i=>{let h=`<b>${esc(o.tipLabels?o.tipLabels[i]:o.labels[i])}</b>`;ser.forEach(se=>{const v=se.v[i]||0;if(v||!o.skipZero)h+=tipRow(o.colorOf?o.colorOf(v,i):se.c,se.n,ft(v))});
    if(o.total){const t=ser.reduce((a,se)=>a+(se.v[i]||0),0);h+=`<div style="border-top:1px solid var(--line2);padding-top:5px;margin-top:6px">Итого<span>${ft(t)}</span></div>`}return h});
}

function line(el,o){
  const W=el.clientWidth,H=o.h||240,pl=62,pr=10,pt=10,pb=26;
  let labels=o.labels,ser=o.series,tl=o.tipLabels||labels;
  if(labels.length>420){const k=Math.ceil(labels.length/420),idx=[];for(let i=0;i<labels.length;i+=k)idx.push(i);if(idx[idx.length-1]!==labels.length-1)idx.push(labels.length-1);
    labels=idx.map(i=>labels[i]);tl=idx.map(i=>(o.tipLabels||o.labels)[i]);ser=ser.map(s=>({...s,v:idx.map(i=>s.v[i])}))}
  const n=labels.length;
  if(n<2||W<50)return emptyChart(el,H,o.empty);
  const fa=o.fa||short,ft=o.ft||(v=>M(v));
  let mn=Infinity,mx=-Infinity;
  ser.forEach(s=>s.v.forEach(v=>{if(v==null||isNaN(v))return;mn=Math.min(mn,v);mx=Math.max(mx,v)}));
  if(o.zero!==false)mn=Math.min(mn,0);if(!isFinite(mn)||mx===mn)return emptyChart(el,H,o.empty);
  const{lo,hi,step}=nice(mn,mx),pw=W-pl-pr,ph=H-pt-pb,X=i=>pl+i/(n-1)*pw,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  let s='';
  for(let v=lo;v<=hi+step/2;v+=step){const y=Y(v);s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}"${Math.abs(v)<step/1e6?' style="stroke:#ffffff26"':''}/><text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${fa(Math.abs(v)<step/1e6?0:v)}</text>`}
  axisTicks(labels,X,pl-4,W-pr+4).forEach(([i,x])=>s+=`<text class="ax" x="${x}" y="${H-6}" text-anchor="middle">${esc(labels[i])}</text>`);
  const gid='g'+Math.random().toString(36).slice(2,8);
  if(o.band){const A=ser[o.band.a].v,B=ser[o.band.b].v,poly=(pts,up)=>{if(pts.length>2)s+=`<polygon points="${pts.map(q=>q[0].toFixed(1)+','+q[1].toFixed(1)).join(' ')}" fill="${up?'#ff6b6b':'#3ecf8e'}" fill-opacity=".22"/>`};
    for(let i=0;i<n-1;i++){const a0=A[i],a1=A[i+1],b0=B[i],b1=B[i+1];if([a0,a1,b0,b1].some(v=>v==null||isNaN(v)))continue;
      const d0=a0-b0,d1=a1-b1,x0=X(i),x1=X(i+1);
      if(d0*d1>=0)poly([[x0,Y(a0)],[x1,Y(a1)],[x1,Y(b1)],[x0,Y(b0)]],d0+d1>0);
      else{const t=d0/(d0-d1),xc=x0+(x1-x0)*t,yc=Y(a0+(a1-a0)*t);poly([[x0,Y(a0)],[xc,yc],[x0,Y(b0)]],d0>0);poly([[xc,yc],[x1,Y(a1)],[x1,Y(b1)]],d1>0)}}}
  ser.forEach((se,j)=>{
    const segs=[];let cur=[],pv=null;se.v.forEach((v,i)=>{if(v==null||isNaN(v)){if(cur.length)segs.push(cur);cur=[];pv=null}else{if(se.step&&pv!=null)cur.push(X(i).toFixed(1)+','+Y(pv).toFixed(1));cur.push(X(i).toFixed(1)+','+Y(v).toFixed(1));pv=v}});if(cur.length)segs.push(cur);
    if(j===0&&o.area){const base=Y(Math.max(lo,Math.min(0,hi)));s+=`<defs><linearGradient id="${gid}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${se.hex||'#3987e5'}" stop-opacity="${o.area==='neg'?0:.28}"/><stop offset="1" stop-color="${se.hex||'#3987e5'}" stop-opacity="${o.area==='neg'?.28:0}"/></linearGradient></defs>`;
      segs.forEach(sg=>{const f=sg[0].split(','),l=sg[sg.length-1].split(',');s+=`<polygon points="${f[0]},${base} ${sg.join(' ')} ${l[0]},${base}" fill="url(#${gid})"/>`})}
    segs.forEach(sg=>s+=`<polyline points="${sg.join(' ')}" fill="none" stroke="${se.c}" stroke-width="${se.w||2}" stroke-linejoin="round" stroke-linecap="round"${se.dash?' stroke-dasharray="5 4"':''}/>`)});
  let hits='';const cw=pw/(n-1);
  for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${X(i)-cw/2}" y="${pt}" width="${cw}" height="${ph}" fill="transparent"/>`;
  el.innerHTML=legend(ser)+`<svg width="${W}" height="${H}">${s}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{if(i<0){hv.innerHTML='';return}hv.innerHTML=`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph}" stroke="var(--mu)" stroke-opacity=".6" stroke-dasharray="3 3"/>`+
    ser.filter(se=>se.v[i]!=null&&!isNaN(se.v[i])).map(se=>`<circle cx="${X(i)}" cy="${Y(se.v[i])}" r="4.5" fill="${se.c}" stroke="var(--card)" stroke-width="2"/>`).join('')};
  bindTip(el,i=>{o.hover&&o.hover(i);if(o.tip)return o.tip(i);return`<b>${esc(tl[i])}</b>`+ser.filter(se=>se.v[i]!=null&&!isNaN(se.v[i])).map(se=>tipRow(se.c,se.n,ft(se.v[i]))).join('')});
  if(o.leave){const ol=el.onmouseleave;el.onmouseleave=e=>{ol(e);o.leave()}}
}

function donut(el,o){
  const items=o.items.filter(x=>x.v>0.005),tot=items.reduce((a,x)=>a+x.v,0),D=o.size||180,R=D/2,r=R-22;
  if(!tot)return emptyChart(el,D,'Нет активов');
  let a=-Math.PI/2,arcs='';const g=items.length>1?0.012:0;
  items.forEach((x,i)=>{const da=x.v/tot*Math.PI*2,a0=a+g,a1=a+da-g;a+=da;if(a1<=a0)return;
    const big=a1-a0>Math.PI?1:0,p=(t,rr)=>[R+rr*Math.cos(t),R+rr*Math.sin(t)].map(v=>v.toFixed(2)).join(',');
    const d=items.length===1?`M${R},0A${R},${R} 0 1 1 ${R-0.01},0L${R-0.01},${R-r}A${r},${r} 0 1 0 ${R},${R-r}Z`:
      `M${p(a0,R)}A${R},${R} 0 ${big} 1 ${p(a1,R)}L${p(a1,r)}A${r},${r} 0 ${big} 0 ${p(a0,r)}Z`;
    arcs+=`<path data-i="${i}" class="arc" d="${d}" fill="${x.c}"/>`});
  el.innerHTML=`<div class="donut-wrap"><svg width="${D}" height="${D}" style="flex:none">${arcs}
    <text x="${R}" y="${R-4}" text-anchor="middle" style="fill:var(--mu);font-size:12px">${esc(o.cap||'Всего')}</text>
    <text x="${R}" y="${R+18}" text-anchor="middle" class="num" style="fill:var(--tx);font-size:17px;font-weight:700">${short(tot)}${o.unit===''?'':' ₽'}</text></svg>
    <div class="dl">${items.map((x,i)=>`<div data-i="${i}"><i style="background:${x.c}"></i><span>${esc(x.n)}</span><b class="num" style="font-weight:600">${short(x.v)}</b><em class="num">${(x.v/tot*100).toFixed(1).replace('.',',')}%</em></div>`).join('')}</div></div>`;
  const arcsEl=el.querySelectorAll('.arc');
  el._hl=i=>arcsEl.forEach(p=>p.style.opacity=i<0||+p.dataset.i===i?1:.35);
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

