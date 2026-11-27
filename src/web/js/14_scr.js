/* ── Скринер облигаций ── */
const SCR_DEF={q:'',cur:'RUB',kind:'all',sector:'',rmin:'',rated:false,ymin:'',ymax:'60',tmax:'',turn:'',spmin:'',noOffer:false,toOffer:false,fl:'all',liq:''};
const SCR_PRESETS=[
  ['ofz3','ОФЗ ≤ 3 лет',{kind:'ofz',cur:'RUB',tmax:'3',fl:'fix',noOffer:false}],
  ['fl_aa','Флоатеры от AA-',{cur:'RUB',fl:'float',rmin:'AA-',turn:'1'}],
  ['hy20','ВДО от 20%',{cur:'RUB',kind:'corp',ymin:'20',ymax:'60',turn:'1'}],
  ['fx','Валютные',{cur:'all',kind:'corp',fl:'all',q:''}]
];
const SCR_QUICK=[
  ['ofz','ОФЗ',f=>f.kind==='ofz',f=>{f.kind=f.kind==='ofz'?'all':'ofz'}],
  ['corp','Корпоративные',f=>f.kind==='corp',f=>{f.kind=f.kind==='corp'?'all':'corp'}],
  ['ra','Рейтинг A+',f=>f.rmin==='A+',f=>{f.rmin=f.rmin==='A+'?'':'A+'}],
  ['t3','До 3 лет',f=>String(f.tmax)==='3',f=>{f.tmax=String(f.tmax)==='3'?'':'3'}],
  ['flt','Флоатеры',f=>f.fl==='float',f=>{f.fl=f.fl==='float'?'all':'float'}],
  ['noof','Без оферты',f=>!!f.noOffer,f=>{f.noOffer=!f.noOffer}]
];
S.scr=null;S.sf=Object.assign({},SCR_DEF);S.scrOpen=false;S.scrPreset='';S.ssort={k:'yield',d:-1};S.sn=150;
const SCR_DENS=[['comfort','Комфорт'],['compact','Компакт'],['scatter','Точечная']];
S.scrDens=(d=>SCR_DENS.some(x=>x[0]===d)?d:'comfort')(lsGet('scr_dens'));      /* плотность таблицы: сохраняется в localStorage */
S.scrReal=lsGet('scr_real')==='1';S.scrBox=null;S.scrScCol=false;
const SCR_TAX_TIP='Купоны зачисляются брутто (100%): налог брокер удерживает при выводе денег или по итогам года, его можно уменьшить сальдированием с убытками. Дивиденды приходят уже за вычетом налога.';
const scrX=r=>r.macdur!=null?r.macdur:r.years;             /* ось X скаттера и рамки выделения: дюрация, лет */
function scrY(r){const i=S.scr&&S.scr.infl_exp;return S.scrReal&&i!=null&&!r.linker?r.yield-i:r.yield}   /* реальная = номинальная − ожидаемая инфляция; у линкеров MOEX уже даёт реальную */
const scrTyp=r=>r.linker?'lnk':r.floating?'fl':'fix';
function loadScr(cb){
  if(S._scrLoading){if(cb)S._scrCbs.push(cb);return}
  S._scrLoading=true;S._scrCbs=cb?[cb]:[];
  api('/api/screener').then(j=>{
    const t=Date.now();
    j.rows.forEach(r=>{
      r.perp=!r.mat||!!r.perpetual;
      r.years=r.perp?null:(new Date(r.mat)-t)/315576e5;
      const yo=r.offer?(new Date(r.offer)-t)/315576e5:null;
      r.yoff=yo!=null&&yo>0&&(r.years==null||yo<r.years)?yo:null;
    });
    S.scr=j;S._scrLoading=false;
    (S._scrCbs||[]).forEach(f=>{try{f()}catch(e){}});S._scrCbs=[];
    if(S.page==='scr'||S.page==='map')renderSoon();
  }).catch(e=>{
    S.scr={error:e.message,rows:[]};S._scrLoading=false;S._scrCbs=[];
    if(S.page==='scr'||S.page==='map')renderSoon();
  });
}
function scrActiveCount(){
  const f=S.sf;let n=0;
  for(const[k,v]of Object.entries(SCR_DEF))if(k!=='q'&&f[k]!==v)n++;
  return n;
}
function scrRows(noBox){
  const f=S.sf,q=f.q.trim().toLowerCase(),ri=f.rmin?RSC.indexOf(f.rmin):-1;
  const nv=x=>{const s=String(x??'').trim().replace(',','.');if(!s)return null;const n=parseFloat(s);return isNaN(n)?null:n};
  const isIsin=/^[A-Z]{2}[0-9A-Z]{10}$/i.test(q);
  const ymin=nv(f.ymin),ymax=(q&&(isIsin||String(f.ymax).trim()===SCR_DEF.ymax))?null:nv(f.ymax),tmax=nv(f.tmax),turn=nv(f.turn),spmin=nv(f.spmin);
  let rs=S.scr.rows.filter(r=>{
    if(S.scrPreset==='fx'&&r.cur==='RUB')return false;
    if(f.cur!=='all'&&r.cur!==f.cur)return false;
    if(f.kind!=='all'&&r.kind!==f.kind)return false;
    if(q&&!((r.name||'').toLowerCase().includes(q)||(r.isin||'').toLowerCase().includes(q)||(r.full||'').toLowerCase().includes(q)||(r.issuer||'').toLowerCase().includes(q)))return false;
    if(ri>=0&&!(r.rating&&RSC.indexOf(r.rating)<=ri))return false;
    if(f.sector&&r.sector!==f.sector)return false;
    if(f.rated&&!r.rating)return false;
    if(ymin!=null&&r.yield<ymin)return false;if(ymax!=null&&r.yield>ymax)return false;
    if(tmax!=null){const eff=f.toOffer&&r.yoff!=null?r.yoff:r.years;if(eff==null||eff>tmax)return false}     /* «считать до оферты»: ближайшее из оферты и погашения */
    if(f.fl==='fix'&&r.floating)return false;if(f.fl==='float'&&!r.floating)return false;
    if(turn!=null&&r.turn<turn*1e6)return false;
    if(spmin!=null&&!(r.spread!=null&&r.spread>=spmin))return false;
    if(f.noOffer&&r.offer)return false;
    if(f.liq&&!(r.liq==='L1'||(f.liq==='L2'&&r.liq==='L2')))return false;
    if(!noBox&&S.scrBox){const b=S.scrBox,x=scrX(r);if(x==null||x<b.x0||x>b.x1||r.yield<b.y0||r.yield>b.y1)return false}
    return r.perp||(r.years!=null&&r.years>0);
  });
  const{k,d}=S.ssort;
  rs.sort((a,b)=>{let x=a[k==='liq'?'turn':k],y=b[k==='liq'?'turn':k];if(k==='rating'){x=x?RSC.indexOf(x):null;y=y?RSC.indexOf(y):null;return -d*((x??99)-(y??99))}
    if(k==='years'){x=a.perp?999:x;y=b.perp?999:y}
    if(k==='yield'){x=scrY(a);y=scrY(b)}
    if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  return rs;
}
function scrCpn(r){
  const q=r.coupon!=null?f2(r.coupon):null,n=r.yoff!=null?r.yoff:r.years;
  let cap,sub,tt;
  if(r.linker){cap='<span class="cap cap-lnk">ЛИНКЕР</span>';sub=`ИПЦ + ${q!=null?q+'%':'?'}`;tt='Купон привязан к индексу потребительских цен: номинал растёт с инфляцией'}
  else if(r.floating){const fm=r.fl_label&&r.fl_label!=='ФЛОАТЕР'?r.fl_label:null;cap='<span class="cap cap-fl">ФЛОАТЕР</span>';sub=`${fm?esc(fm):'формула н/д'}${q!=null?` (${q}%)`:''}`;tt=fm?'Плавающий купон: '+fm+' (спред эмитента по последним купонам), в скобках — текущий купон':'Плавающий купон (привязан к ключевой ставке или RUONIA); формула пока не определена'}
  else{const t=r.perp&&r.yoff==null?'бессрочный':n!=null?'фикс на '+(n<1?Math.max(1,Math.round(n*12))+' мес.':n.toFixed(1).replace('.',',')+' г.'):'';cap='<span class="cap cap-fix">ФИКС</span>';sub=`${q!=null?q+'%':'—'}${t?' · '+t:''}`;tt='Фиксированный купон'+(r.yoff!=null?' (до ближайшей оферты)':'')}
  const ex=(/суборд/i.test(r.sub||'')?'<span class="cap cap-w" title="Субординированная облигация: при проблемах эмитента требования погашаются в последнюю очередь, купон могут не выплатить">⚠ СУБОРД</span>':'')+(r.perp?'<span class="cap cap-w" title="Бессрочная облигация: срока погашения нет">∞ ВЕЧНЫЙ</span>':'');
  return`<div class="cell-stack" title="${esc(tt)}"><span class="cap-row">${cap}${ex}<span class="cmp-only mu">${r.linker?sub:q!=null?q+'%':''}</span></span><span class="cell-sub">${sub}</span></div>`;
}
function scrYld(r){
  const d=r.days_to_offer,dt=d==null?'':d>=365?(d/365).toFixed(1).replace('.',',')+' г.':d+' дн.',off=!r.linker&&r.ytm_kind==='offer';
  const sub=r.linker?'реальная, над ИПЦ':off?`<span class="y-warn">к оферте ⚠${dt?' через '+dt:''}</span>`:'к погашению';
  return`<div class="cell-stack r" title="${esc(SCR_TAX_TIP)}"><b class="y-big">${pctp(scrY(r),2)}${off?'<i class="ofw" title="Доходность посчитана к оферте'+(dt?' (через '+dt+')':'')+'">⚠</i>':''}</b><span class="cell-sub">${sub}</span></div>`;
}
/* бумаги, которые уже есть на выбранном счёте: ISIN и тикер -> количество */
function scrMine(){
  const b=S.bonds&&S.bonds.rows;if(!b)return null;
  if(S._scrMineSrc!==b){S._scrMineSrc=b;const m=new Map();b.forEach(x=>{if(x.isin)m.set(x.isin,x.qty||0);if(x.ticker)m.set(x.ticker,x.qty||0)});S._scrMine=m}
  return S._scrMine;
}
function scrOwn(id){
  const m=scrMine();if(!m||!m.has(id))return'';
  const q=m.get(id);
  return` <span class="tag scr-own" title="Эта бумага уже есть на выбранном счёте">в портфеле${q?' · '+f0(q)+' шт.':''}</span>`;
}
/* сохранённые пользовательские наборы фильтров */
function scrSavedLoad(){
  let a=null;try{a=JSON.parse(lsGet('scr_saved')||'null')}catch(e){}
  if(!Array.isArray(a))a=[];
  return a.filter(x=>x&&x.id&&x.name&&x.f&&typeof x.f==='object');
}
function scrSavedStore(a){S.scrSaved=a;lsSet('scr_saved',JSON.stringify(a))}
S.scrSaved=scrSavedLoad();S.scrSaving=false;
function scrRowHtml(r,fl){
  const id=r.isin||r.id,cls=[];
  if(fl>0&&r.yield<fl)cls.push('scr-low');
  if(typeof KB!=='undefined'&&KB.key===id)cls.push('kb-row');
  const rt=r.rating?`<div class="cell-stack"><span class="cell-sub">${esc(r.rt_agency||'')}</span><span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}${rtClick(r.rt_links).cls}" title="${esc(r.rt_agency||'')}${r.rt_approx?' (приблизительное совпадение названия)':''}${r.rt_links?'\nНажмите, чтобы открыть пресс-релиз':''}"${rtClick(r.rt_links).attr}>${r.rt_approx?'≈ ':''}${esc(r.rating)}</span></div>`:'<span class="mu">—</span>';
  const yrs=r.perp?'<span class="tag">бессрочная</span>':`<div class="cell-stack r"><span>${ddm(r.mat)}</span><span class="cell-sub">${(S.sf.toOffer&&r.yoff!=null?r.yoff:r.years).toFixed(1).replace('.',',')} г${S.sf.toOffer&&r.yoff!=null?' до оферты':''}</span></div>`;
  return`<tr${cls.length?` class="${cls.join(' ')}"`:''}${fl>0&&r.yield<fl?' title="Доходность ниже, чем у фонда ликвидности"':''} data-isin="${esc(id)}"><td class="wt-std">${watchStar(id)}</td>
    <td class="l"><div class="cell-stack"><b>${esc(r.name)}${scrOwn(id)}</b><small class="cell-sub mu num">${isinTxt(id)}${r.offer?' · оферта '+ddm(r.offer):''}</small></div></td>
    <td class="l">${rt}</td><td class="l">${r.sector?esc(SECT[r.sector]||r.sector):'<span class="mu">—</span>'}</td>
    <td class="num"><div class="cell-stack r"><span>${f2(r.price)}</span><span class="spk" data-spark="${esc(r.id||id)}"></span></div></td><td class="num">${scrYld(r)}</td><td class="num">${r.cy!=null?f2(r.cy):'—'}</td>
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread):'—'}</td>
    <td class="l">${scrCpn(r)}</td><td class="num">${yrs}</td>
    <td class="num">${r.macdur!=null?r.macdur.toFixed(2).replace('.',','):'—'}</td><td class="num"><div class="cell-stack r"><span class="num">${r.turn?short(r.turn):'—'}</span><span class="tag liq liq-${r.liq||'L3'}" title="Ликвидность по обороту за день: L1 — верхние 20%, L2 — следующие 40%, L3 — остальные">${r.liq||'L3'}</span></div></td></tr>`;
}
function scrSyncQuick(){
  document.querySelectorAll('.scr-quick [data-qk]').forEach(b=>{
    const q=SCR_QUICK.find(x=>x[0]===b.dataset.qk);
    if(q)b.classList.toggle('on',!!q[2](S.sf));
  });
}
function drawScr(){
  const rs=scrRows(),n=Math.min(rs.length,S.sn),fl=S.scr.floor&&S.scr.floor.lqdt;
  const cols=[['_w','★','l'],['name','Выпуск','l'],['rating','Рейтинг','l'],['sector','Сектор','l'],['price','Цена, %'],['yield',S.scrReal?'Реальная доходность':'Доходность'],['cy','Тек. доходн., %'],['spread','Спред к КБД'],['coupon','Купон & формула','l'],['years','До погашения'],['macdur','Дюрация, лет'],['liq','Ликвидность']];
  const {k,d}=S.ssort;
  $('#scr-head').innerHTML=cols.map(([kk,t,c])=>kk==='_w'?`<th class="wt-sth" title="Список наблюдения">${t}</th>`:`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  $('#scr-body').innerHTML=rs.slice(0,n).map(r=>scrRowHtml(r,fl)).join('');
  const tl=(typeof scrTypeLabel==='function')?scrTypeLabel():'';
  $('#scr-cnt').textContent=`Найдено: ${rs.length}${rs.length>n?' · показано '+n:''}${tl?' · '+tl:''}${S.scrBox?' · в выделении':''}`;
  $('#scr-more').style.display=rs.length>n?'':'none';
  const fb=$('#scr-ftog');if(fb){const ac=scrActiveCount();fb.textContent=(S.scrOpen?'Скрыть фильтры':'Фильтры')+(ac?` (${ac})`:'')}
  scrSyncQuick();scrScatter();scrSparkWatch();
}
/* ── спарклайны: грузим только видимые строки, пачками, результат кэшируется на сессию ── */
const SPK={map:new Map(),pend:new Set(),to:0,io:null,bad:0};
function scrSparkFill(el){const v=SPK.map.get(el.dataset.spark);if(v&&v.length>1&&!el.firstChild)el.innerHTML=spark(v)}
function scrSparkFlush(){
  const ids=[...SPK.pend].filter(i=>!SPK.map.has(i));SPK.pend.clear();
  if(!ids.length||Date.now()<SPK.bad)return;
  const go=a=>{if(!a.length)return;
    api('/api/spark?ids='+encodeURIComponent(a.join(','))).then(j=>{
      a.forEach(i=>{if(j&&Array.isArray(j[i]))SPK.map.set(i,j[i])});      /* сервер не успел или ошибся — не запоминаем, попросим при следующей отрисовке */
      document.querySelectorAll('#scr-body [data-spark]').forEach(scrSparkFill);
    }).catch(()=>{SPK.bad=Date.now()+30000})};
  for(let i=0;i<ids.length;i+=60)go(ids.slice(i,i+60));
}
function scrSparkWatch(){
  const els=document.querySelectorAll('#scr-body [data-spark]');
  els.forEach(scrSparkFill);
  if(SPK.io){SPK.io.disconnect();SPK.io=null}
  const queue=id=>{if(!SPK.map.has(id)){SPK.pend.add(id);clearTimeout(SPK.to);SPK.to=setTimeout(scrSparkFlush,250)}};
  if(typeof IntersectionObserver!=='function'){[...els].slice(0,40).forEach(e=>queue(e.dataset.spark));return}
  SPK.io=new IntersectionObserver(es=>es.forEach(en=>{if(en.isIntersecting){SPK.io.unobserve(en.target);queue(en.target.dataset.spark)}}),{rootMargin:'120px 0px'});
  els.forEach(e=>{if(!SPK.map.has(e.dataset.spark))SPK.io.observe(e)});
}
/* ── Диаграмма: дюрация × доходность, выделение рамкой фильтрует таблицу ── */
const SC={pts:[],drag:null};
function scrScatter(){
  const box=$('#scr-sc');if(!box)return;
  if(S.scrDens!=='scatter'){box.classList.add('hide');box.innerHTML='';return}
  box.classList.remove('hide');
  const boxBtns=S.scrBox?`<button class="scr-chip on" id="sc-cmp" title="Открыть сравнение по выбранным бумагам (до 4)">Сравнить выбранные</button><button class="scr-chip on" id="sc-clr">сбросить выделение ✕</button>`:'';
  const head=`<div class="sc-h"><b>Дюрация × доходность</b><span class="mu">рамкой выделите область, клик по точке открывает выпуск</span>${boxBtns}<span class="sc-lg"><i class="t-fl"></i>флоатер<i class="t-fix"></i>фикс<i class="t-lnk"></i>линкер</span><button class="scr-chip" id="sc-col">${S.scrScCol?'Показать':'Свернуть'}</button></div>`;
  if(S.scrScCol){box.innerHTML=head;scrScBind(box);return}
  const rs=scrRows(true).filter(r=>scrX(r)!=null&&isFinite(scrX(r))&&isFinite(r.yield)&&r.yield>0).slice(0,2500);
  const W=Math.max(280,box.clientWidth||700),H=W<760?240:300,L=42,R=12,T=10,B=28;
  if(!rs.length){box.innerHTML=head+'<div class="mu" style="padding:18px">Нет выпусков под текущие фильтры.</div>';scrScBind(box);return}
  const q=(a,p)=>a[Math.min(a.length-1,Math.max(0,Math.round(p*(a.length-1))))];
  const ys=rs.map(r=>r.yield).sort((a,b)=>a-b),xs=rs.map(scrX).sort((a,b)=>a-b);
  const ny=nice(Math.max(0,q(ys,.01)),q(ys,.99),5),nx=nice(0,Math.max(1,q(xs,.99)),6);
  const X=v=>L+Math.max(0,Math.min(1,(v-nx.lo)/(nx.hi-nx.lo)))*(W-L-R),Y=v=>T+(1-Math.max(0,Math.min(1,(v-ny.lo)/(ny.hi-ny.lo))))*(H-T-B);
  let g='';
  for(let v=ny.lo;v<=ny.hi+1e-9;v+=ny.step)g+=`<line class="sc-g" x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}"/><text class="sc-t" x="${L-6}" y="${Y(v)+3.5}" text-anchor="end">${(+v.toFixed(2)).toString().replace('.',',')}</text>`;
  for(let v=nx.lo;v<=nx.hi+1e-9;v+=nx.step)g+=`<line class="sc-g" x1="${X(v)}" x2="${X(v)}" y1="${T}" y2="${H-B}"/><text class="sc-t" x="${X(v)}" y="${H-B+15}" text-anchor="middle">${(+v.toFixed(2)).toString().replace('.',',')}</text>`;
  SC.pts=rs.map(r=>({r,x:X(scrX(r)),y:Y(r.yield)}));SC.W=W;SC.H=H;SC.X=X;SC.Y=Y;SC.nx=nx;SC.ny=ny;SC.L=L;SC.R=R;SC.T=T;SC.B=B;
  const b=S.scrBox;
  box.innerHTML=head+`<div class="sc-wrap"><svg id="sc-svg" viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="Диаграмма: дюрация и доходность облигаций">${g}
    <text class="sc-t" x="${W-R}" y="${H-3}" text-anchor="end">дюрация, лет</text><text class="sc-t" x="${L+2}" y="${T+8}">доходность, %</text>
    ${SC.pts.map(p=>`<circle class="sc-p t-${scrTyp(p.r)}" cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3.4"/>`).join('')}
    ${b?`<rect class="sc-sel" x="${X(b.x0)}" y="${Y(b.y1)}" width="${Math.max(1,X(b.x1)-X(b.x0))}" height="${Math.max(1,Y(b.y0)-Y(b.y1))}"/>`:''}<rect id="sc-drag" class="sc-sel" style="display:none"/></svg><div class="sc-tip" id="sc-tip" style="display:none"></div></div>`;
  scrScBind(box);
}
function scrScBind(box){
  const c=$('#sc-col');if(c)c.onclick=()=>{S.scrScCol=!S.scrScCol;scrScatter()};
  const x=$('#sc-clr');if(x)x.onclick=()=>{S.scrBox=null;S.sn=150;drawScr()};
  const cm=$('#sc-cmp');if(cm)cm.onclick=()=>{
    const picks=scrRows().slice(0,typeof CMP!=='undefined'?CMP.max:4).map(r=>String(r.isin||r.id||'').toUpperCase()).filter(Boolean);
    if(!picks.length){toast('В выделении нет облигаций');return}
    S.cmp=picks;if(typeof cmpSave==='function')cmpSave();
    if(scrRows().length>picks.length)toast('Для сравнения взяты первые '+picks.length+' бумаги из выделения');
    go('cmp');
  };
  const svg=$('#sc-svg'),tip=$('#sc-tip');if(!svg)return;
  const pos=e=>{const r=svg.getBoundingClientRect(),k=SC.W/(r.width||SC.W);return[(e.clientX-r.left)*k,(e.clientY-r.top)*k]};
  const near=(px,py)=>{let best=null,bd=100;for(const p of SC.pts){const d=(p.x-px)*(p.x-px)+(p.y-py)*(p.y-py);if(d<bd){bd=d;best=p}}return best};
  svg.onpointerdown=e=>{if(e.button)return;const[px,py]=pos(e);SC.drag={x:px,y:py,m:false};try{svg.setPointerCapture(e.pointerId)}catch(er){}};
  svg.onpointermove=e=>{
    const[px,py]=pos(e),dr=SC.drag;
    if(dr){
      if(Math.abs(px-dr.x)+Math.abs(py-dr.y)>6)dr.m=true;
      if(dr.m){const el=$('#sc-drag');el.style.display='';el.setAttribute('x',Math.min(px,dr.x));el.setAttribute('y',Math.min(py,dr.y));el.setAttribute('width',Math.abs(px-dr.x));el.setAttribute('height',Math.abs(py-dr.y));tip.style.display='none';return}
    }
    const p=near(px,py);
    if(!p){tip.style.display='none';return}
    const r=p.r;tip.innerHTML=`<b>${esc(r.name)}</b><br>доходность ${pctp(r.yield,2)} · дюрация ${f2(scrX(r))} г.<br>${r.linker?'линкер':r.floating?'флоатер':'фикс'}${r.rating?' · '+esc(r.rating):''}`;
    tip.style.display='';const k=svg.getBoundingClientRect().width/SC.W,tx=p.x*k;
    tip.style.left=Math.min(Math.max(4,tx+12),Math.max(4,svg.getBoundingClientRect().width-190))+'px';tip.style.top=Math.max(2,p.y*k-44)+'px';
  };
  svg.onpointerleave=()=>{tip.style.display='none'};
  svg.onpointerup=e=>{
    const dr=SC.drag;SC.drag=null;if(!dr)return;const[px,py]=pos(e);
    const inv=(v,a,b,n)=>n.lo+(v-a)/(b-a)*(n.hi-n.lo);
    if(dr.m){
      const xa=Math.min(px,dr.x),xb=Math.max(px,dr.x),ya=Math.min(py,dr.y),yb=Math.max(py,dr.y),w=SC.W-SC.L-SC.R,h=SC.H-SC.T-SC.B;
      S.scrBox={x0:inv(xa,SC.L,SC.L+w,SC.nx),x1:inv(xb,SC.L,SC.L+w,SC.nx),y0:SC.ny.lo+(1-(yb-SC.T)/h)*(SC.ny.hi-SC.ny.lo),y1:SC.ny.lo+(1-(ya-SC.T)/h)*(SC.ny.hi-SC.ny.lo)};
      S.sn=150;drawScr();
    }else{const p=near(px,py);if(p)openBond(p.r.isin||p.r.id)}
  };
  svg.onpointercancel=()=>{SC.drag=null;const el=$('#sc-drag');if(el)el.style.display='none'};
}
function scrSetDens(m){
  if(!SCR_DENS.some(x=>x[0]===m))return;
  S.scrDens=m;lsSet('scr_dens',m);
  const tw=$('#scr-tw');if(tw)tw.className='tbl scr-tbl dn-'+m;
  document.querySelectorAll('#scr-dens [data-dn]').forEach(b=>b.classList.toggle('on',b.dataset.dn===m));
  if(S.scr&&$('#scr-body'))drawScr();
}
/* быстрый тип (клавиша f): Все → Флоатеры → Фиксы → ОФЗ поверх обычных фильтров «Тип» и «Купон» */
const SCR_TYPES=[['Все',{kind:'all',fl:'all'}],['Флоатеры',{kind:'all',fl:'float'}],['Фиксы',{kind:'all',fl:'fix'}],['ОФЗ',{kind:'ofz',fl:'all'}]];
function scrTypeIdx(){const f=S.sf;return f.kind==='ofz'?3:f.fl==='float'?1:f.fl==='fix'?2:0}
function scrTypeLabel(){const i=scrTypeIdx();return i?SCR_TYPES[i][0]:''}
function scrCycleType(){
  const nx=SCR_TYPES[(scrTypeIdx()+1)%SCR_TYPES.length][1];
  S.scrPreset='';Object.assign(S.sf,nx);S.sn=150;
  [['f-kind','kind'],['f-fl','fl']].forEach(([id,kk])=>{const e=$('#'+id);if(e)e.value=S.sf[kk]});
  drawScr();
}
S.scrTab='scr';S.mvDir='down';S.mvSort={k:'chg',d:0};S.mv=null;
function scrTabs(){return`<div class="seg" id="scr-tabs" style="margin-bottom:12px"><button data-t="scr" class="${S.scrTab==='scr'?'on':''}">Скринер</button><button data-t="mv" class="${S.scrTab==='mv'?'on':''}">Лидеры</button></div>`}
function loadMv(){api('/api/movers?n=50').then(j=>{S.mv=j;if(S.page==='scr')renderSoon()}).catch(e=>{S.mv={error:e.message,down:[],up:[]};if(S.page==='scr')renderSoon()})}
function mvRows(){
  const d=S.mv,rs=(S.mvDir==='down'?d.down:d.up).slice(),{k}=S.mvSort,dir=S.mvSort.d||(S.mvDir==='down'?1:-1);
  rs.sort((a,b)=>{let x=a[k],y=b[k];if(k==='rating'){x=x?RSC.indexOf(x):99;y=y?RSC.indexOf(y):99}return dir*((x??-Infinity)-(y??-Infinity))});
  return rs;
}
function drawMv(){
  const d=S.mv,rs=mvRows(),cols=[['name','Инструмент','l'],['chg','За день, %'],['price','Цена, %'],['turnover','Оборот, ₽'],['trades','Сделок'],['rating','Рейтинг','l']],{k}=S.mvSort,dir=S.mvSort.d||(S.mvDir==='down'?1:-1);
  $('#mv-head').innerHTML=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(dir>0?'↑':'↓'):''}</span></th>`).join('');
  $('#mv-body').innerHTML=rs.map(r=>`<tr data-isin="${esc(r.isin)}"><td class="l"><b>${esc(r.name)}</b><br><small class="mu num">${isinTxt(r.isin)}</small></td><td class="num ${r.chg>0?'pos':'neg'}"><b>${r.chg>0?'+':''}${f2(r.chg)}</b></td><td class="num">${f2(r.price)}</td><td class="num">${r.turnover?short(r.turnover):'—'}</td><td class="num">${r.trades||'—'}</td>
    <td class="l">${r.rating?`<span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}">${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td></tr>`).join('');
}
function pMv(){
  if(!S.mv){loadMv();return`<div class="card">${waitBox('Загружаю лидеров роста и падения…')}</div>`}
  if(S.mv.error)return`<div class="msg err">${esc(S.mv.error)}</div>`;
  const d=S.mv;
  return`<div class="card"><h2>Лидеры ${S.mvDir==='down'?'падения':'роста'}<span class="sp">${d.n} из ${d.total}</span></h2>
    <div class="seg" id="mv-dir" style="margin-bottom:10px"><button data-d="down" class="${S.mvDir==='down'?'on':''}">Падение</button><button data-d="up" class="${S.mvDir==='up'?'on':''}">Рост</button></div>
    <div class="tbl" style="max-height:calc(100vh - 300px)"><table><thead><tr id="mv-head"></tr></thead><tbody id="mv-body"></tbody></table></div></div>
  <p class="note">Изменение цены облигации за торговый день по данным Мосбиржи (ISS). «${d.n} из ${d.total}» — показано выпусков из тех, цена которых сегодня изменилась. Не инвестиционная рекомендация.</p>`;
}
function bindMv(){
  if(!S.mv||S.mv.error)return;
  $('#mv-dir').onclick=e=>{const b=e.target.closest('[data-d]');if(!b)return;S.mvDir=b.dataset.d;S.mvSort={k:'chg',d:0};render()};
  $('#mv-head').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s,cur=S.mvSort.d||(S.mvDir==='down'?1:-1);S.mvSort={k,d:S.mvSort.k===k?-cur:(k==='name'||k==='rating'?1:-1)};drawMv()};
  drawMv();
}
function pScr(){
  if(S.scrTab==='mv')return scrTabs()+pMv();
  return scrTabs()+pScr0();
}
function pScr0(){
  const d=S.scr;
  if(!d){loadScr();return`<div class="card">${waitBox('Загружаю торги облигациями с Мосбиржи и сопоставляю рейтинги…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="scr-r">Повторить</button></div>`;
  const f=S.sf,opt=(v,t,cur)=>`<option value="${v}" ${cur===v?'selected':''}>${t}</option>`;
  const fl0=d.floor&&d.floor.lqdt,flN=fl0>0?`<p class="note scr-fl">Фонд ликвидности сейчас даёт ≈ ${f2(fl0)} % годовых — у бумаг ниже этой доходности нет премии за риск (такие строки приглушены). Доходность до налогов; не инвестиционная рекомендация.</p>`:'';
  const rated=d.rows.filter(r=>r.rating).length,sectors=[...new Set(d.rows.map(r=>r.sector).filter(Boolean))].sort((a,b)=>(SECT[a]||a).localeCompare(SECT[b]||b));
  const ac=scrActiveCount();
  const quickRow=`<div class="scr-quick" role="group" aria-label="Быстрые фильтры"><span class="scr-quick-lbl">Быстро:</span>${SCR_QUICK.map(([k,t,on])=>`<button type="button" class="scr-chip${on(f)?' on':''}" data-qk="${k}">${t}</button>`).join('')}</div>`;
  return`<div class="card"><div class="tbl-head" style="padding:0 0 12px"><h2 style="margin:0">Подбор облигаций<span class="sp" id="scr-cnt"></span></h2>${typeof taCsvBtn==='function'?taCsvBtn('scr-csv','Выгрузить подборку в CSV'):''}</div>
    ${quickRow}
    <div class="scr-bar">
      <input class="in" id="f-q" value="${esc(f.q)}" placeholder="Поиск по названию или ISIN…" aria-label="Поиск облигаций">
      <div class="scr-presets">${SCR_PRESETS.map(([k,t])=>`<button class="scr-chip${S.scrPreset===k?' on':''}" data-pr="${k}">${t}</button>`).join('')}${S.scrSaved.map(x=>`<span class="scr-chip scr-sv${S.scrPreset==='sv:'+x.id?' on':''}"><button class="scr-sv-b" data-sv="${esc(x.id)}" title="Мой сохранённый фильтр">${esc(x.name)}</button><button class="scr-sv-x" data-svx="${esc(x.id)}" aria-label="Удалить фильтр ${esc(x.name)}" title="Удалить">×</button></span>`).join('')}${S.scrSaving?`<span class="scr-sv-new"><input class="in" id="scr-sv-name" maxlength="40" placeholder="Название фильтра" aria-label="Название фильтра"><button class="btn" id="scr-sv-ok">Сохранить</button><button class="btn ghost" id="scr-sv-no">Отмена</button></span>`:(ac||f.q?`<button class="scr-chip" id="scr-sv-add" title="Запомнить текущие настройки фильтра">+ Сохранить фильтр</button>`:'')}</div>
      <div class="seg scr-dens" id="scr-dens" role="group" aria-label="Плотность таблицы (клавиша V)">${SCR_DENS.map(([k,t])=>`<button data-dn="${k}" class="${S.scrDens===k?'on':''}">${t}</button>`).join('')}</div>
      <div class="seg scr-real" id="scr-real" title="${esc(d.infl_exp!=null?`Реальная доходность = номинальная − ожидаемая инфляция ${f2(d.infl_exp)} % (${d.infl_src||'прогноз'}). У линкеров ОФЗ-ИН биржа и так показывает реальную доходность.`:'Нет прогноза инфляции — реальная доходность недоступна')}"><button data-rl="0" class="${S.scrReal&&d.infl_exp!=null?'':'on'}">Номинальная</button><button data-rl="1" class="${S.scrReal&&d.infl_exp!=null?'on':''}"${d.infl_exp==null?' disabled':''}>Реальная</button></div>
      <button class="btn ghost" id="scr-ftog">${S.scrOpen?'Скрыть фильтры':'Фильтры'}${ac?` (${ac})`:''}</button>
      ${ac||f.q||S.scrPreset?'<button class="btn ghost" id="f-reset">Сбросить</button>':''}
    </div>
    <div class="flt${S.scrOpen?'':' shut'}" id="scr-flt">
    <label class="field"><span>Валюта</span><select class="in" id="f-cur">${opt('RUB','Рубли',f.cur)}${opt('all','Все',f.cur)}${opt('USD','USD',f.cur)}${opt('CNY','CNY',f.cur)}${opt('EUR','EUR',f.cur)}</select></label>
    <label class="field"><span>Тип</span><select class="in" id="f-kind">${opt('all','Все',f.kind)}${opt('corp','Корпоративные',f.kind)}${opt('ofz','ОФЗ',f.kind)}</select></label>
    ${sectors.length?`<label class="field"><span>Сектор</span><select class="in" id="f-sector"><option value="">любой</option>${sectors.map(x=>opt(x,SECT[x]||x,f.sector)).join('')}</select></label>`:''}
    <label class="field"><span>Рейтинг не ниже</span><select class="in" id="f-rmin"><option value="">любой</option>${RSC.slice(0,10).map(x=>opt(x,x,f.rmin)).join('')}</select></label>
    <label class="field"><span>Доходность от, %</span><input class="in num" id="f-ymin" value="${esc(f.ymin)}" inputmode="decimal"></label>
    <label class="field"><span>Доходность до, %</span><input class="in num" id="f-ymax" value="${esc(f.ymax)}" inputmode="decimal"></label>
    <label class="field"><span>Спред к КБД от, п.п.</span><input class="in num" id="f-spmin" value="${esc(f.spmin)}" inputmode="decimal"></label>
    <label class="field"><span>До погашения, лет не более</span><input class="in num" id="f-tmax" value="${esc(f.tmax)}" inputmode="decimal"></label>
    <label class="field"><span>Ликвидность (оборот за день)</span><select class="in" id="f-turn">${opt('','любая',f.turn)}${opt('1','от 1 млн ₽',f.turn)}${opt('10','от 10 млн ₽',f.turn)}</select></label>
    <label class="field"><span>Ликвидность не ниже</span><select class="in" id="f-liq">${opt('','любая',f.liq)}${opt('L2','L2',f.liq)}${opt('L1','L1',f.liq)}</select></label>
    <label class="field"><span>Купон</span><select class="in" id="f-fl">${opt('all','любой',f.fl)}${opt('fix','фиксированный',f.fl)}${opt('float','флоатер',f.fl)}</select></label>
    <label class="sw"><input type="checkbox" id="f-toff" ${f.toOffer?'checked':''}><i></i><div><b>Считать до оферты</b><small>срок — до ближайшей оферты или погашения</small></div></label>
    <label class="sw"><input type="checkbox" id="f-noffer" ${f.noOffer?'checked':''}><i></i><div><b>Без оферт</b></div></label></div>
    ${flN}
    <div class="sc-panel hide" id="scr-sc"></div>
    <div class="tbl scr-tbl dn-${S.scrDens}" id="scr-tw" style="max-height:calc(100vh - 280px)"><table><thead><tr id="scr-head"></tr></thead><tbody id="scr-body"></tbody></table></div>
    <div class="row" style="margin-top:12px"><button class="btn ghost" id="scr-more">Показать ещё</button></div></div>
  <p class="note">Данные — Московская биржа (ISS, режимы торгов Т+ для корпоративных облигаций и ОФЗ; с задержкой, как в бесплатном доступе). Доходность — по цене последних торгов, спред — к кривой КБД при той же дюрации. Рейтинг найден у ${rated} из ${d.rows.length} выпусков: эмитенты без рейтинга в базе не обязательно ненадёжны. По умолчанию скрыты выпуски с доходностью выше 60% (обычно это дефолтные или почти не торгуемые бумаги) — поле «Доходность до» можно очистить. </p>${NIR_NOTE}`;
}
function bindScr(){
  const tb=$('#scr-tabs');if(tb)tb.onclick=e=>{const b=e.target.closest('[data-t]');if(!b||b.dataset.t===S.scrTab)return;S.scrTab=b.dataset.t;render()};
  if(S.scrTab==='mv')return bindMv();
  if(!S.scr||S.scr.error){const b=$('#scr-r');if(b)b.onclick=()=>{S.scr=null;render()};return}
  const csv=$('#scr-csv');
  if(csv)csv.onclick=()=>{
    const rs=scrRows();
    if(typeof taCsvDownload==='function')taCsvDownload('screener.csv',['Название','ISIN','Рейтинг','Сектор','Цена, %','Доходность, %','Тек. доходность, %','Спред к КБД, п.п.','Купон, %','Погашение','Дюрация, лет','Оборот, ₽','Ликвидность'],
      rs.map(r=>[r.name||'',r.isin||r.id||'',r.rating||'',r.sector?(SECT[r.sector]||r.sector):'',r.price!=null?r.price.toFixed(2):'',scrY(r)!=null?scrY(r).toFixed(2):'',r.cy!=null?r.cy.toFixed(2):'',r.spread!=null?r.spread.toFixed(2):'',r.coupon!=null?r.coupon.toFixed(2):'',r.mat||'',r.macdur!=null?r.macdur.toFixed(2):'',r.turn!=null?Math.round(r.turn):'',r.liq||'L3']));
  };
  document.querySelectorAll('.scr-quick [data-qk]').forEach(b=>b.onclick=()=>{
    const q=SCR_QUICK.find(x=>x[0]===b.dataset.qk);if(!q)return;
    S.scrPreset='';q[3](S.sf);S.sn=150;render();
  });
  const map={'f-q':'q','f-cur':'cur','f-kind':'kind','f-sector':'sector','f-rmin':'rmin','f-ymin':'ymin','f-ymax':'ymax','f-spmin':'spmin','f-tmax':'tmax','f-turn':'turn','f-fl':'fl','f-liq':'liq'};
  let to;Object.entries(map).forEach(([id,k])=>{const e=$('#'+id);if(!e)return;e.oninput=e.onchange=()=>{if(k!=='q')S.scrPreset='';S.sf[k]=e.value;S.sn=150;clearTimeout(to);to=setTimeout(drawScr,150)}});
  $('#f-toff').onchange=e=>{S.scrPreset='';S.sf.toOffer=e.target.checked;S.sn=150;drawScr()};
  $('#f-noffer').onchange=e=>{S.scrPreset='';S.sf.noOffer=e.target.checked;S.sn=150;drawScr()};
  const ft=$('#scr-ftog');if(ft)ft.onclick=()=>{S.scrOpen=!S.scrOpen;const el=$('#scr-flt');if(el)el.classList.toggle('shut',!S.scrOpen);drawScr()};
  document.querySelectorAll('.scr-chip[data-pr]').forEach(b=>b.onclick=()=>{
    const k=b.dataset.pr;
    if(S.scrPreset===k){S.scrPreset='';S.sf=Object.assign({},SCR_DEF)}
    else{const p=SCR_PRESETS.find(x=>x[0]===k);S.scrPreset=k;S.sf=Object.assign({},SCR_DEF,p?p[2]:{})}
    S.sn=150;S.scrBox=null;render();
  });
  document.querySelectorAll('.scr-sv-b[data-sv]').forEach(b=>b.onclick=()=>{
    const k='sv:'+b.dataset.sv;
    if(S.scrPreset===k){S.scrPreset='';S.sf=Object.assign({},SCR_DEF)}
    else{const p=S.scrSaved.find(x=>x.id===b.dataset.sv);if(!p)return;S.scrPreset=k;S.sf=Object.assign({},SCR_DEF,p.f)}
    S.sn=150;S.scrBox=null;render();
  });
  document.querySelectorAll('.scr-sv-x[data-svx]').forEach(b=>b.onclick=e=>{
    e.stopPropagation();scrSavedStore(S.scrSaved.filter(x=>x.id!==b.dataset.svx));
    if(S.scrPreset==='sv:'+b.dataset.svx)S.scrPreset='';
    render();
  });
  const sva=$('#scr-sv-add');if(sva)sva.onclick=()=>{S.scrSaving=true;render()};
  const svn=$('#scr-sv-name');
  if(svn){
    svn.focus();
    const ok=()=>{
      const nm=svn.value.trim();if(!nm){svn.focus();return}
      const id='u'+Date.now().toString(36);
      scrSavedStore(S.scrSaved.concat([{id,name:nm.slice(0,40),f:Object.assign({},S.sf)}]));
      S.scrSaving=false;S.scrPreset='sv:'+id;render();
    };
    $('#scr-sv-ok').onclick=ok;
    svn.onkeydown=e=>{if(e.key==='Enter')ok();else if(e.key==='Escape'){S.scrSaving=false;render()}};
    $('#scr-sv-no').onclick=()=>{S.scrSaving=false;render()};
  }
  const rs=$('#f-reset');if(rs)rs.onclick=()=>{S.scrBox=null;S.scrPreset='';S.sf=Object.assign({},SCR_DEF);S.sn=150;render()};
  const dn=$('#scr-dens');if(dn)dn.onclick=e=>{const b=e.target.closest('[data-dn]');if(b)scrSetDens(b.dataset.dn)};
  const rl=$('#scr-real');if(rl)rl.onclick=e=>{const b=e.target.closest('[data-rl]');if(!b||b.disabled)return;S.scrReal=b.dataset.rl==='1';lsSet('scr_real',S.scrReal?'1':'0');
    rl.querySelectorAll('[data-rl]').forEach(x=>x.classList.toggle('on',x===b));drawScr()};
  $('#scr-more').onclick=()=>{S.sn+=200;drawScr()};
  $('#scr-head').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;S.ssort={k,d:S.ssort.k===k?-S.ssort.d:(['name'].includes(k)?1:-1)};drawScr()};
  drawScr();
}


(()=>{const st=document.createElement('style');st.textContent=`.tag.liq-L1{background:#3ecf8e26;color:var(--pos)}.tag.liq-L2{background:#d9770626}.tag.liq-L3{opacity:.7}.scr-fl-t{background:#3987e526}`;document.head.appendChild(st)})();
