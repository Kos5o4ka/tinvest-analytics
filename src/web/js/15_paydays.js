/* ── Выплаты по дням (столбики с разбивкой по выпускам) ── */
const colAt=i=>i<HEX.length?HEX[i]:`hsl(${(i*137.5)%360},55%,52%)`;
function dayBars(el,o){
  const days=o.days,H=o.h||340,pl=64,pt=26,pb=64,step=62,n=days.length;
  if(!n)return emptyChart(el,H,'Выплат в выбранном периоде нет');
  const mx=Math.max(...days.map(d=>d.total)),{lo,hi,step:ys}=nice(0,mx),ph=H-pt-pb,Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  let ax='',grid='';
  for(let v=lo;v<=hi+ys/2;v+=ys){const y=Y(v);ax+=`<text class="ax num" x="${pl-10}" y="${y+4}" text-anchor="end">${v===0?'0':short(v)}</text>`;grid+=`<line class="grid-l" x1="0" x2="100000" y1="${y}" y2="${y}"/>`}
  ax+=`<text class="ax" transform="translate(14 ${pt+ph/2}) rotate(-90)" text-anchor="middle">Сумма выплат, ₽</text>`;
  const bw=Math.min(40,step*.62);let marks='',lab='',hits='';
  days.forEach((d,i)=>{const cx=step*i+step/2;let acc=0;
    d.items.forEach((it,k)=>{const y1=Y(acc+it.amount),y0=Y(acc),h=Math.max(0,y0-y1-(k?1:0));
      marks+=`<path class="bm" data-g="${i}" d="${k===d.items.length-1?rtop(cx-bw/2,y1,bw,h,4):`M${cx-bw/2},${y1}h${bw}v${h}h${-bw}Z`}" fill="${it.c}"${it.kind==='dividend'?'':''}/>`;acc+=it.amount});
    lab+=`<text class="ax num" x="${cx}" y="${Y(d.total)-7}" text-anchor="middle" style="fill:var(--tx);font-weight:600">${short(d.total)}</text>`;
    lab+=`<text class="ax" transform="translate(${cx+4} ${H-pb+14}) rotate(-45)" text-anchor="end">${d.label}</text>`;
    hits+=`<rect data-i="${i}" x="${step*i}" y="${pt}" width="${step}" height="${ph}" fill="transparent"/>`});
  const W=Math.max(step*n,el.clientWidth-pl-4);
  el.innerHTML=`<div class="dwrap"><svg width="${pl}" height="${H}" style="flex:none">${ax}</svg><div class="dscroll"><svg width="${W}" height="${H}">${grid}<g>${marks}</g>${lab}${hits}</svg></div></div>
    <div class="lg2">${o.legend.map(l=>`<span><i style="background:${l.c}"></i>${esc(l.n)}${l.tag?` <em>${l.tag}</em>`:''}</span>`).join('')}</div>`;
  const mk=el.querySelectorAll('.bm');el._hl=i=>mk.forEach(p=>p.style.opacity=i<0||+p.dataset.g===i?1:.35);
  bindTip(el,i=>{const d=days[i];return`<b>${esc(d.full)}</b>`+d.items.map(it=>tipRow(it.c,it.name+' · '+it.kl,M(it.amount))).join('')+
    `<div style="border-top:1px solid var(--line2);padding-top:5px;margin-top:6px">Итого<span>${M(d.total)}</span></div>`});
}
function payDays(ps,limit){
  const to=new Date(Date.now()+limit*864e5).toISOString().slice(0,10),from=new Date().toISOString().slice(0,10);
  const f=ps.filter(p=>p.date>=from&&p.date<=to);
  const tot={};f.forEach(p=>tot[p.name]=(tot[p.name]||0)+p.amount);
  const names=Object.keys(tot).sort((a,b)=>tot[b]-tot[a]),col={};names.forEach((n,i)=>col[n]=colAt(i));
  const red=new Set(f.filter(p=>p.kind==='redemption').map(p=>p.name));
  const KL={coupon:'купон',dividend:'дивиденд',redemption:'погашение'},by={};
  f.forEach(p=>(by[p.date]=by[p.date]||[]).push(p));
  const days=Object.keys(by).sort().map(dt=>{const items=by[dt].slice().sort((a,b)=>tot[b.name]-tot[a.name]).map(p=>({name:p.name,amount:p.amount,c:col[p.name],kind:p.kind,kl:KL[p.kind]||p.kind}));
    const [y,m,d]=dt.split('-');return{label:`${d}.${m}.${y}`,full:ddm(dt),total:items.reduce((a,x)=>a+x.amount,0),items}});
  return{days,legend:names.map(n=>({n,c:col[n],tag:red.has(n)?'погашение':''}))};
}

