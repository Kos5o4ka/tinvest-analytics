/* ── Карточка портфеля для шаринга (PNG 1200×630, строго без сумм в рублях) ── */
const SHR={open:false,theme:'',bench:'both'};
function shareOpen(){
  if(!S.data||!S.data.portfolio){alert('Сначала откройте портфель или демо-режим.');return}
  SHR.open=true;
  if(!SHR.theme)SHR.theme=document.documentElement.dataset.theme==='light'?'light':'dark';
  shareMount();
}
function shareClose(){
  SHR.open=false;
  const el=$('#shr-bg');if(el)el.remove();
}
function shareMount(){
  let bg=$('#shr-bg');
  if(!bg){bg=document.createElement('div');bg.id='shr-bg';bg.className='shr-bg';document.body.appendChild(bg)}
  const hs=typeof histSlice==='function'?histSlice():null;
  const hasB=!!(hs&&hs.bench&&(hs.bench.TMOS||hs.bench.LQDT));
  bg.innerHTML=`<div class="shr-mod" role="dialog" aria-modal="true" aria-label="Поделиться портфелем PNG">
    <div class="shr-hd"><div><b>Поделиться портфелем (PNG)</b><small class="mu"> · 1200×630 · строго без сумм в рублях</small></div>
      <button class="btn ghost" id="shr-x" aria-label="Закрыть">✕</button></div>
    <div class="shr-bar">
      <div class="seg" id="shr-th"><button class="${SHR.theme==='dark'?'on':''}" data-st="dark">Тёмная</button><button class="${SHR.theme==='light'?'on':''}" data-st="light">Светлая</button></div>
      ${hasB?`<div class="seg" id="shr-bn"><button class="${SHR.bench==='both'?'on':''}" data-sb="both">TMOS + LQDT</button><button class="${SHR.bench==='TMOS'?'on':''}" data-sb="TMOS">TMOS</button><button class="${SHR.bench==='LQDT'?'on':''}" data-sb="LQDT">LQDT</button><button class="${SHR.bench==='none'?'on':''}" data-sb="none">Без бенчмарка</button></div>`:''}
    </div>
    <div class="shr-cvw"><canvas id="shr-cv" width="1200" height="630"></canvas></div>
    <div class="shr-ft">
      <span class="mu" id="shr-st">Скрыты все абсолютные суммы и названия счетов — видны только %, график TWR и доли активов.</span>
      <div class="row" style="gap:8px">
        <button class="btn ghost" id="shr-cp">Скопировать картинку</button>
        <button class="btn" id="shr-dl">Скачать PNG</button>
      </div>
    </div>
  </div>`;
  bg.onclick=e=>{if(e.target===bg)shareClose()};
  $('#shr-x').onclick=shareClose;
  bg.querySelectorAll('[data-st]').forEach(b=>b.onclick=()=>{SHR.theme=b.dataset.st;shareMount()});
  bg.querySelectorAll('[data-sb]').forEach(b=>b.onclick=()=>{SHR.bench=b.dataset.sb;shareMount()});
  const cv=$('#shr-cv');
  shareDraw(cv);
  $('#shr-dl').onclick=()=>{
    cv.toBlob(blob=>{
      if(!blob)return;
      const u=URL.createObjectURL(blob),a=document.createElement('a');
      a.href=u;a.download='tanalytic-portfolio-'+new Date().toISOString().slice(0,10)+'.png';
      document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000);
      $('#shr-st').textContent='PNG-карточка сохранена.';
    },'image/png');
  };
  $('#shr-cp').onclick=async()=>{
    const st=$('#shr-st');
    if(!navigator.clipboard||typeof ClipboardItem==='undefined'){st.textContent='Копирование картинки не поддерживается браузером — нажмите «Скачать PNG».';return}
    cv.toBlob(async blob=>{
      if(!blob)return;
      try{await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);st.textContent='Картинка скопирована в буфер обмена — можно вставлять в Telegram (Ctrl+V / ⌘V).'}
      catch(e){st.textContent='Не удалось скопировать в буфер — нажмите «Скачать PNG».'}
    },'image/png');
  };
}
function _shrRR(ctx,x,y,w,h,r){
  ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();
}
function _shrPct(v,d=1){
  if(v==null||isNaN(v))return'—';
  return(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',')+' %';
}
function shareDraw(cv){
  if(!cv)return;
  const ctx=cv.getContext('2d'),W=1200,H=630,dk=SHR.theme!=='light';
  const C=dk
    ?{bg:'#0f131a',card:'#171d28',line:'#263042',tx:'#f2f5fa',tx2:'#9aa6bc',ac:'#3b82f6',pos:'#10b981',neg:'#ff6b6b',s1:'#4da3ff',s2:'#f5a623',s3:'#3ecf8e',grid:'#ffffff10'}
    :{bg:'#f4f6fa',card:'#ffffff',line:'#dde3ee',tx:'#141923',tx2:'#5c677d',ac:'#2563eb',pos:'#128a5a',neg:'#d63c41',s1:'#2474e5',s2:'#d98200',s3:'#128a5a',grid:'#00000010'};
  ctx.fillStyle=C.bg;ctx.fillRect(0,0,W,H);
  // Subtle accent glow
  const gr=ctx.createRadialGradient(180,80,10,180,80,460);
  gr.addColorStop(0,dk?'rgba(77,163,255,0.14)':'rgba(36,116,229,0.09)');
  gr.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle=gr;ctx.fillRect(0,0,W,H);

  const d=S.data||{},p=d.portfolio||{},hs=typeof histSlice==='function'?histSlice():null;
  const F='system-ui,-apple-system,Segoe UI,Roboto,sans-serif';

  // Header brand badge
  ctx.fillStyle=C.ac;_shrRR(ctx,44,36,40,40,10);ctx.fill();
  ctx.strokeStyle='#fff';ctx.lineWidth=3.2;ctx.lineCap='round';ctx.lineJoin='round';
  ctx.beginPath();ctx.moveTo(52,64);ctx.lineTo(60,54);ctx.lineTo(66,59);ctx.lineTo(76,46);ctx.stroke();

  ctx.fillStyle=C.tx;ctx.font='700 24px '+F;ctx.fillText('TAnalytic',96,58);
  ctx.fillStyle=C.tx2;ctx.font='500 13px '+F;ctx.fillText('Итоги портфеля · Инкогнито-режим (без сумм)',96,76);

  // Period + date pill on right
  const pTxt=(typeof periodName==='function'?periodName():'За период')+' · '+new Date().toLocaleDateString('ru-RU');
  ctx.font='600 14px '+F;const pw=ctx.measureText(pTxt).width+28;
  ctx.fillStyle=C.card;_shrRR(ctx,W-44-pw,40,pw,34,17);ctx.fill();
  ctx.strokeStyle=C.line;ctx.lineWidth=1;ctx.stroke();
  ctx.fillStyle=C.tx2;ctx.fillText(pTxt,W-44-pw+14,62);

  // 4 KPI tiles
  const twrV=hs&&hs.total!=null?hs.total*100:null;
  const xirrV=d.xirr!=null?d.xirr*100:null;
  const ddV=hs&&hs.maxdd!=null?hs.maxdd*100:null;
  let alphaV=null,alphaSub='нет бенчмарка';
  if(hs&&hs.bench){
    const bk=SHR.bench==='LQDT'&&hs.bench.LQDT?'LQDT':(hs.bench.TMOS?'TMOS':(hs.bench.LQDT?'LQDT':null));
    if(bk&&hs.bench[bk]&&hs.bench[bk].length){
      const lastB=[...hs.bench[bk]].reverse().find(x=>x!=null);
      if(lastB!=null&&twrV!=null){alphaV=twrV-lastB*100;alphaSub='к '+bk+' ('+_shrPct(lastB*100,1)+')'}
    }
  }
  const kpis=[
    ['Доходность (TWR)',_shrPct(twrV,2),twrV==null?C.tx:twrV>=0?C.pos:C.neg,'без влияния пополнений'],
    ['Годовая (XIRR)',_shrPct(xirrV,1),xirrV==null?C.tx:xirrV>=0?C.pos:C.neg,'с учётом дат и сумм'],
    ['Макс. просадка',_shrPct(ddV,1),ddV!=null&&ddV<0?C.neg:C.tx,'от пика до дна'],
    ['К бенчмарку',_shrPct(alphaV,1),alphaV==null?C.tx:alphaV>=0?C.pos:C.neg,alphaSub]
  ];
  const kw=(W-88-36)/4;
  kpis.forEach(([lbl,val,col,sub],i)=>{
    const x=44+i*(kw+12),y=96;
    ctx.fillStyle=C.card;_shrRR(ctx,x,y,kw,92,14);ctx.fill();
    ctx.strokeStyle=C.line;ctx.lineWidth=1;ctx.stroke();
    ctx.fillStyle=C.tx2;ctx.font='500 13px '+F;ctx.fillText(lbl,x+18,y+26);
    ctx.fillStyle=col;ctx.font='700 28px '+F;ctx.fillText(val,x+18,y+60);
    ctx.fillStyle=C.tx2;ctx.font='400 12px '+F;ctx.fillText(sub,x+18,y+80);
  });

  // Left panel: TWR curve
  const cx=44,cy=206,cw=740,ch=362;
  ctx.fillStyle=C.card;_shrRR(ctx,cx,cy,cw,ch,16);ctx.fill();
  ctx.strokeStyle=C.line;ctx.lineWidth=1;ctx.stroke();
  ctx.fillStyle=C.tx;ctx.font='600 16px '+F;ctx.fillText('Кривая доходности TWR, %',cx+22,cy+32);

  if(hs&&hs.twr&&hs.twr.length>1){
    const sList=[{name:'Портфель',col:C.s1,w:3,dash:[],arr:hs.twr.map(x=>x*100)}];
    if((SHR.bench==='both'||SHR.bench==='TMOS')&&hs.bench&&hs.bench.TMOS)
      sList.push({name:'TMOS',col:C.s2,w:2,dash:[6,5],arr:hs.bench.TMOS.map(x=>x==null?null:x*100)});
    if((SHR.bench==='both'||SHR.bench==='LQDT')&&hs.bench&&hs.bench.LQDT)
      sList.push({name:'LQDT',col:C.s3,w:2,dash:[4,4],arr:hs.bench.LQDT.map(x=>x==null?null:x*100)});
    // Legend
    let lx=cx+cw-22;
    ctx.font='600 12.5px '+F;
    for(let i=sList.length-1;i>=0;i--){
      const it=sList[i],tw=ctx.measureText(it.name).width;
      lx-=tw;ctx.fillStyle=C.tx2;ctx.fillText(it.name,lx,cy+31);
      lx-=18;ctx.fillStyle=it.col;ctx.fillRect(lx,cy+23,12,4);lx-=16;
    }
    const vals=[];sList.forEach(s=>s.arr.forEach(v=>{if(v!=null&&!isNaN(v))vals.push(v)}));
    let mn=Math.min(0,...vals),mx=Math.max(1,...vals);
    if(mx-mn<1){mx+=1;mn-=1}
    const pad=(mx-mn)*0.1;mn-=pad;mx+=pad;
    const px0=cx+58,px1=cx+cw-24,py0=cy+54,py1=cy+ch-38,n=hs.twr.length;
    const X=i=>px0+(px1-px0)*(i/(n-1));
    const Y=v=>py1-(py1-py0)*((v-mn)/(mx-mn));

    // Horizontal grid
    ctx.font='500 11.5px '+F;ctx.textAlign='right';
    for(let g=0;g<=4;g++){
      const v=mn+(mx-mn)*(g/4),yy=Y(v);
      ctx.strokeStyle=C.grid;ctx.lineWidth=1;ctx.setLineDash([]);
      ctx.beginPath();ctx.moveTo(px0,yy);ctx.lineTo(px1,yy);ctx.stroke();
      ctx.fillStyle=C.tx2;ctx.fillText((v>=0?'+':'')+v.toFixed(1).replace('.',',')+'%',px0-8,yy+4);
    }
    ctx.textAlign='left';
    // Zero line
    const y0=Y(0);
    if(y0>=py0&&y0<=py1){
      ctx.strokeStyle=C.line;ctx.lineWidth=1.2;ctx.setLineDash([4,4]);
      ctx.beginPath();ctx.moveTo(px0,y0);ctx.lineTo(px1,y0);ctx.stroke();ctx.setLineDash([]);
    }
    // Area under portfolio line
    const pArr=sList[0].arr;
    const ag=ctx.createLinearGradient(0,py0,0,py1);
    ag.addColorStop(0,dk?'rgba(77,163,255,0.28)':'rgba(36,116,229,0.20)');
    ag.addColorStop(1,'rgba(77,163,255,0.0)');
    ctx.beginPath();ctx.moveTo(X(0),py1);
    for(let i=0;i<n;i++)ctx.lineTo(X(i),Y(pArr[i]));
    ctx.lineTo(X(n-1),py1);ctx.closePath();ctx.fillStyle=ag;ctx.fill();

    // Draw lines (benchmarks first, portfolio last on top)
    for(let si=sList.length-1;si>=0;si--){
      const s=sList[si];
      ctx.strokeStyle=s.col;ctx.lineWidth=s.w;ctx.setLineDash(s.dash);ctx.beginPath();
      let started=false;
      for(let i=0;i<n;i++){
        const v=s.arr[i];if(v==null||isNaN(v)){started=false;continue}
        if(!started){ctx.moveTo(X(i),Y(v));started=true}else ctx.lineTo(X(i),Y(v));
      }
      ctx.stroke();ctx.setLineDash([]);
    }
    // X axis start/mid/end dates
    ctx.fillStyle=C.tx2;ctx.font='500 11.5px '+F;
    const dFmt=s=>s?s.slice(8,10)+'.'+s.slice(5,7)+'.'+s.slice(2,4):'';
    ctx.fillText(dFmt(hs.days[0]),px0,py1+20);
    ctx.textAlign='center';ctx.fillText(dFmt(hs.days[Math.floor(n/2)]),(px0+px1)/2,py1+20);
    ctx.textAlign='right';ctx.fillText(dFmt(hs.days[n-1]),px1,py1+20);ctx.textAlign='left';
  }else{
    ctx.fillStyle=C.tx2;ctx.font='500 15px '+F;
    ctx.fillText('История доходности ещё загружается…',cx+22,cy+185);
  }

  // Right panel: Asset allocation (% ONLY)
  const rx=cx+cw+16,ry=cy,rw=W-44-rx,rh=ch;
  ctx.fillStyle=C.card;_shrRR(ctx,rx,ry,rw,rh,16);ctx.fill();
  ctx.strokeStyle=C.line;ctx.lineWidth=1;ctx.stroke();
  ctx.fillStyle=C.tx;ctx.font='600 16px '+F;ctx.fillText('Структура портфеля, %',rx+22,ry+32);

  const rawAlloc=[
    ['Облигации',p.bonds,'#f5a623'],
    ['Акции',p.shares,'#4da3ff'],
    ['Фонды (ETF)',p.etf,'#3ecf8e'],
    ['Валюта и кэш',p.currencies,'#9b7bff'],
    ['Фьючерсы',p.futures,'#ff8c66'],
    ['Прочее',(p.sp||0)+(p.options||0)+(p.other||0),'#7c879d']
  ].filter(([,v])=>v>0);
  const tot=rawAlloc.reduce((a,[,v])=>a+v,0)||1;
  rawAlloc.sort((a,b)=>b[1]-a[1]);
  let ay=ry+66;
  rawAlloc.forEach(([name,val,col])=>{
    const pctV=val/tot*100;
    ctx.fillStyle=C.tx;ctx.font='500 14px '+F;ctx.fillText(name,rx+22,ay);
    ctx.fillStyle=C.tx;ctx.font='700 14px '+F;ctx.textAlign='right';
    ctx.fillText(pctV.toFixed(1).replace('.',',')+' %',rx+rw-22,ay);ctx.textAlign='left';
    const bw=rw-44;
    ctx.fillStyle=dk?'#ffffff12':'#00000010';_shrRR(ctx,rx+22,ay+8,bw,10,5);ctx.fill();
    ctx.fillStyle=col;_shrRR(ctx,rx+22,ay+8,Math.max(8,bw*Math.min(1,pctV/100)),10,5);ctx.fill();
    ay+=46;
  });
  if(!rawAlloc.length){ctx.fillStyle=C.tx2;ctx.font='500 14px '+F;ctx.fillText('Нет открытых позиций',rx+22,ry+80)}

  // Footer
  ctx.fillStyle=C.tx2;ctx.font='500 12.5px '+F;
  ctx.fillText('Сгенерировано в TAnalytic · Локальная аналитика портфеля без передачи данных',44,H-22);
  ctx.textAlign='right';ctx.fillStyle=C.tx;ctx.font='700 13px '+F;
  ctx.fillText('TAnalytic',W-44,H-22);ctx.textAlign='left';
}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&SHR.open)shareClose()});
document.addEventListener('click',e=>{
  if(e.target.closest('#share')||e.target.closest('[data-share-card]'))shareOpen();
});
