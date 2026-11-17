/* ── Тепловая карта рынка: squarified treemap (акции / облигации / фонды) ── */
const HM_KINDS=[['stocks','Акции'],['bonds','Облигации'],['funds','Фонды']],HM_PER=[['d','День'],['w','Неделя'],['m','Месяц']],HM_SZ=[['cap','Капитализация'],['value','Оборот']];
const HM_LIM={d:3,w:7,m:15};
S.hm={kind:'stocks',period:'d',size:'cap',d:null,loading:'',err:null};
/* Раскладка squarified — зеркало Python treemap_layout (13u_heatmap.py); менять обе реализации синхронно. */
function hmSquarify(vals,x,y,w,h){
  const n=vals.length,out=vals.map(()=>[x,y,0,0]);
  const idx=[];vals.forEach((v,i)=>{if(v>0)idx.push(i)});idx.sort((a,b)=>vals[b]-vals[a]);
  const tot=idx.reduce((a,i)=>a+vals[i],0);if(!idx.length||tot<=0||w<=0||h<=0)return out;
  const k=w*h/tot,ar=idx.map(i=>vals[i]*k),sum=r=>r.reduce((a,b)=>a+b,0);
  const worst=(r,s)=>{const t=sum(r);return Math.max(s*s*Math.max(...r)/(t*t),t*t/(s*s*Math.min(...r)))};
  let cx=x,cy=y,cw=w,ch=h,pos=0;
  while(pos<ar.length){
    const side=Math.min(cw,ch),row=[ar[pos]];let j=pos+1;
    while(j<ar.length&&worst(row.concat(ar[j]),side)<=worst(row,side)){row.push(ar[j]);j++}
    const s=sum(row);
    if(cw>=ch){const colw=s/ch;let yy=cy;row.forEach((a,t)=>{const hh=a/colw;out[idx[pos+t]]=[cx,yy,colw,hh];yy+=hh});cx+=colw;cw-=colw}
    else{const rh=s/cw;let xx=cx;row.forEach((a,t)=>{const ww=a/rh;out[idx[pos+t]]=[xx,cy,ww,rh];xx+=ww});cy+=rh;ch-=rh}
    pos=j;
  }
  return out;
}
function hmKey(){const f=S.hm;return f.kind+'|'+f.period+'|'+f.size}
function hmTrading(){const d=new Date(Date.now()+3*36e5),w=d.getUTCDay(),h=d.getUTCHours();return w>=1&&w<=5&&h>=7&&h<24}
function hmLoad(){
  const f=S.hm,key=hmKey();if(f.loading===key)return;f.loading=key;
  api('/api/heatmap?'+new URLSearchParams({kind:f.kind,period:f.period,size:f.size})).then(j=>{
    if(f.loading===key)f.loading='';if(hmKey()!==key)return;j._k=key;f.d=j;f.err=null;if(S.page==='hm')renderSoon()
  }).catch(e=>{if(f.loading===key)f.loading='';f.err=e.message;if(S.page==='hm')renderSoon()});
}
function hmColor(chg,lim){
  const t=Math.max(-1,Math.min(1,(chg||0)/lim)),lt=document.documentElement.dataset.theme==='light';
  const n=lt?[226,229,236]:[52,58,71],g=lt?[46,170,112]:[31,160,104],r=lt?[222,84,84]:[214,68,68],e=t>=0?g:r,a=Math.abs(t);
  return`rgb(${n.map((c,i)=>Math.round(c+(e[i]-c)*a)).join(',')})`;
}
function hmFmt(c){return c==null?'—':(c>0?'+':c<0?'−':'')+Math.abs(c).toFixed(2).replace('.',',')+' %'}
function drawHm(el){
  const f=S.hm,d=f.d;if(!d||d._k!==hmKey())return;
  const W=Math.floor(el.clientWidth);if(W<50)return;
  if(d.error||!d.groups||!d.groups.length){el.innerHTML=`<div class="empty" style="padding:40px">${esc(d.error||'Нет данных для карты')}</div>`;return}
  const H=W<560?Math.round(W*1.35):Math.max(460,Math.min(720,Math.round(W*.52))),lim=HM_LIM[d.period]||3,tiles=[];
  const gr=hmSquarify(d.groups.map(g=>g.size),0,0,W,H);let s='';
  d.groups.forEach((g,gi)=>{
    const [gx,gy,gw,gh]=gr[gi];if(gw<1||gh<1)return;
    const hd=gw>=56&&gh>=44?16:0,ix=gx+1,iy=gy+1+hd,iw=gw-2,ih=gh-2-hd;
    s+=`<rect class="hm-g" x="${gx.toFixed(1)}" y="${gy.toFixed(1)}" width="${gw.toFixed(1)}" height="${gh.toFixed(1)}"/>`;
    if(hd){const mc=Math.max(3,Math.floor((gw-8)/6.4));s+=`<text class="hm-gl" x="${(gx+5).toFixed(1)}" y="${(gy+12).toFixed(1)}">${esc(g.name.length>mc?g.name.slice(0,mc-1)+'…':g.name)}</text>`}
    if(iw<2||ih<2)return;
    const ir=hmSquarify(g.items.map(i=>i.size),ix,iy,iw,ih);
    g.items.forEach((it,k)=>{
      const [x,y,w,h]=ir[k];if(w<.8||h<.8)return;
      const ti=tiles.length;tiles.push(it);
      let txt='';
      if(w>=30&&h>=20){
        const lb=String(it.label||it.id),fs=Math.max(8,Math.min(24,w/(lb.length*.62+.6),h*.38));
        if(fs>=8.5){const two=h>=fs*2.5&&w>=40;
          txt=`<text class="hm-l" x="${(x+w/2).toFixed(1)}" y="${(y+h/2+(two?-fs*.1:fs*.35)).toFixed(1)}" font-size="${fs.toFixed(1)}" text-anchor="middle">${esc(lb.length*fs*.62>w?lb.slice(0,Math.max(2,Math.floor(w/(fs*.62))-1))+'…':lb)}</text>`;
          if(two){const fp=Math.max(8,fs*.75);txt+=`<text class="hm-p" x="${(x+w/2).toFixed(1)}" y="${(y+h/2+fs*.1+fp).toFixed(1)}" font-size="${fp.toFixed(1)}" text-anchor="middle">${hmFmt(it.chg).replace(' %','%')}</text>`}}
      }
      s+=`<g data-i="${ti}" class="hm-t"><rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(0,w-1).toFixed(1)}" height="${Math.max(0,h-1).toFixed(1)}" fill="${hmColor(it.chg,lim)}"/>${txt}</g>`;
    });
  });
  el.innerHTML=`<svg class="hm-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${s}</svg>`;
  el.onmousemove=e=>{const t=e.target.closest('[data-i]');if(!t||!el.contains(t)){hideTip();return}
    const it=tiles[+t.dataset.i];if(!it)return;const c=hmColor(it.chg,lim),bd=d.kind==='bonds';
    showTip(`<b>${esc(it.name||it.label)}</b><div style="color:var(--mu)">${esc(bd?(it.rating||'без рейтинга'):it.id)}</div>`+
      tipRow(c,'Цена',it.price!=null?(f2(it.price)+(bd?' %':' ₽')):'—')+tipRow(c,d.period==='d'?'За день':d.period==='w'?'За неделю':'За месяц',hmFmt(it.chg))+
      (bd&&it.yield!=null?tipRow(c,'Доходность',pctp(it.yield,2)):'')+tipRow(c,'Оборот за день',it.value?short(it.value)+' ₽':'—')+(it.cap?tipRow(c,'Капитализация',short(it.cap)+' ₽'):'')+
      '<div style="color:var(--mu);margin-top:5px">нажмите — карточка</div>',e)};
  el.onmouseleave=hideTip;
  el.onclick=e=>{const t=e.target.closest('[data-i]');if(!t)return;const it=tiles[+t.dataset.i];if(!it)return;
    if(d.kind==='bonds'){if(typeof openBond==='function')openBond(it.id)}else if(typeof openStock==='function')openStock(it.id)};
}
function pHeatmap(){
  const f=S.hm,d=f.d,ok=d&&d._k===hmKey(),bd=f.kind==='bonds',lim=HM_LIM[bd?'d':f.period];
  if(!ok)hmLoad();
  chart('hm-map',drawHm);chart('hm-root',bindHm);
  const seg=(arr,cur,attr)=>arr.map(([k,t])=>`<button type="button" data-${attr}="${k}" class="${k===cur?'on':''}">${t}</button>`).join('');
  const st=ok&&d.stats,leg=[-lim,-lim/2,0,lim/2,lim];
  return`<div id="hm-root"><div class="card"><h2>Тепловая карта рынка<span class="sp">${bd?'размер — оборот за день, цвет — изменение цены за день':'размер и цвет плиток — по выбранным параметрам'}</span></h2>
    <div class="hm-bar"><div class="mp-chips" id="hm-kind">${seg(HM_KINDS,f.kind,'k')}</div>
    ${bd?'':`<div class="mp-chips" id="hm-per">${seg(HM_PER,f.period,'p')}</div><div class="mp-chips" id="hm-sz">${seg(HM_SZ,f.size,'s')}</div>`}</div>
    ${st?`<div class="hm-st"><span>Растут: <b class="pos">${st.up}</b></span><span>Падают: <b class="neg">${st.down}</b></span><span>Без изм.: <b>${st.flat}</b></span><span>Оборот: <b>${short(st.turnover)} ₽</b></span><span>Взвешенное изменение: <b class="${st.wchg>0?'pos':st.wchg<0?'neg':''}">${hmFmt(st.wchg)}</b></span></div>`:''}
    ${f.err&&!ok?`<div class="msg err">${esc(f.err)} <button class="btn ghost" id="hm-r">Повторить</button></div>`:ok?'<div class="hm-wrap" id="hm-map"></div>':waitBox('Загружаю данные Мосбиржи…')}
    <div class="legend hm-leg">${leg.map(v=>`<span><i style="background:${hmColor(v,lim)}"></i>${v>0?'+':v<0?'−':''}${(+Math.abs(v).toFixed(1))}%</span>`).join('')}<span class="mu">цвет ограничен значением ±${lim}%${ok&&d.updated?' · обновлено '+new Date(d.updated*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}):''}</span></div></div></div>`;
}
function bindHm(){
  const f=S.hm,pick=(id,attr,key)=>{const e=$(id);if(e)e.onclick=ev=>{const b=ev.target.closest('[data-'+attr+']');if(!b||b.dataset[attr]===f[key])return;f[key]=b.dataset[attr];f.d=null;f.err=null;render()}};
  pick('#hm-kind','k','kind');pick('#hm-per','p','period');pick('#hm-sz','s','size');
  const r=$('#hm-r');if(r)r.onclick=()=>{f.err=null;render()};
  if(!window._hmTm){window._hmTm=setInterval(()=>{if(S.page==='hm'&&!document.hidden&&hmTrading())hmLoad()},60000)}
}
