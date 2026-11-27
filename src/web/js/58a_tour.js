/* ── Spotlight-тур по интерфейсу (FE-13) + тихий «тик» (Web Audio) ── */
const TOUR_KEY='tour';   /* ключ в ui_seen: версия программы, на которой тур уже показан */
function tourVer(){return String((S.cfg&&S.cfg.version)||'1')}
function tourSeen(){return String(uiGet(TOUR_KEY)||'')===tourVer()}
const TOUR_STEPS=[
  {sel:['#acc-dd'],title:'Все счета в одном месте',text:'Переключайте брокерские счета и смотрите сводку по всем сразу — прямо из верхней панели.'},
  {sel:['#ux-mode','aside'],title:'Режимы «Базовый» и «Профи»',text:'«Базовый» показывает основные разделы без лишнего. «Профи» открывает все инструменты аналитики.'},
  {sel:['#nav button[title="Облигации (рынок)"]','#nav [data-p="scr"]'],title:'Скринер: фиксы и флоатеры',text:'Подбор облигаций по доходности, сроку и надёжности. Нажмите, чтобы открыть скринер.',task:true},
  {sel:['#nav [data-p="dgap"]','#nav button[title="Акции и фонды"]'],title:'Дивиденды',text:'Ближайшие дивиденды по акциям портфеля, их надёжность и поведение цены в день отсечки. Полный анализ любой акции — вкладка «Дивиденды» в её карточке. Раздел для режима «Профи».'},
  {sel:['#srch'],title:'Быстрый поиск '+MOD+'K',text:'Находите бумаги, эмитентов и разделы программы с клавиатуры.'}
];
const TOUR={on:false,i:0,list:[],tgt:null,raf:0,ov:null,pop:null,hole:null,ring:null,bk:[],tm:0,tm2:0,ro:null,loop:0,lr:''};
/* слежение за целью: бегущая строка, догрузка данных и т. п. сдвигают раскладку — подсветка и подсказка едут следом.
   ResizeObserver ловит изменения размеров, а дешёвая проверка getBoundingClientRect раз в кадр — сдвиги без ресайза цели. */
function tourRect(){const t=TOUR.tgt;if(!t)return'';const r=t.getBoundingClientRect();return Math.round(r.left)+','+Math.round(r.top)+','+Math.round(r.width)+','+Math.round(r.height)+','+window.innerWidth+','+window.innerHeight}
function tourLoop(){
  TOUR.loop=0;if(!TOUR.on)return;
  if(TOUR.tgt&&!document.body.contains(TOUR.tgt)){const st=TOUR.list[TOUR.i],t=st&&tourFind(st);if(t){TOUR.tgt=t;tourObserve()}}
  const k=tourRect();if(k!==TOUR.lr){TOUR.lr=k;tourPlace()}
  TOUR.loop=requestAnimationFrame(tourLoop);
}
function tourObserve(){
  if(!TOUR.ro)return;
  TOUR.ro.disconnect();
  [document.body,document.querySelector('main'),document.getElementById('view'),document.getElementById('tkr'),TOUR.tgt].forEach(e=>{if(e)try{TOUR.ro.observe(e)}catch(x){}});
}

function tourFind(st){
  for(const s of st.sel){
    let els;try{els=document.querySelectorAll(s)}catch(e){continue}
    for(const e of els){
      if(!(e.offsetParent||getComputedStyle(e).position==='fixed')||getComputedStyle(e).visibility==='hidden')continue;
      const r=e.getBoundingClientRect();
      if(r.width>0&&r.height>0)return e;
    }
  }
  return null;
}
function tourSetBox(el,l,t,w,h){el.style.left=l+'px';el.style.top=t+'px';el.style.width=Math.max(0,w)+'px';el.style.height=Math.max(0,h)+'px'}
function tourPlace(){
  if(!TOUR.on)return;
  const vw=window.innerWidth,vh=window.innerHeight,pop=TOUR.pop;
  let r=null;
  if(TOUR.tgt&&document.body.contains(TOUR.tgt)){const b=TOUR.tgt.getBoundingClientRect();if(b.width>0&&b.height>0)r=b}
  const H=TOUR.hole,bk=TOUR.bk,ring=TOUR.ring;
  let hx,hy,hw,hh;
  if(r){const p=6;hx=Math.max(0,r.left-p);hy=Math.max(0,r.top-p);hw=Math.min(vw,r.right+p)-hx;hh=Math.min(vh,r.bottom+p)-hy}
  else{hx=vw/2;hy=vh/2;hw=0;hh=0}
  H.style.cssText='x:'+hx+'px;y:'+hy+'px;width:'+hw+'px;height:'+hh+'px';
  H.setAttribute('x',hx);H.setAttribute('y',hy);H.setAttribute('width',hw);H.setAttribute('height',hh);
  tourSetBox(bk[0],0,0,vw,hy);
  tourSetBox(bk[1],0,hy+hh,vw,vh-hy-hh);
  tourSetBox(bk[2],0,hy,hx,hh);
  tourSetBox(bk[3],hx+hw,hy,vw-hx-hw,hh);
  tourSetBox(ring,hx,hy,hw,hh);
  ring.style.opacity=r?'1':'0';
  const pw=pop.offsetWidth,ph=pop.offsetHeight,g=14;
  if(vw<760){
    pop.classList.add('dock');
    const top=r&&(hy+hh)>vh-ph-24&&hy>ph+24;
    pop.style.left='12px';pop.style.right='12px';pop.style.width='auto';
    pop.style.top=top?'12px':'auto';pop.style.bottom=top?'auto':'12px';
    return;
  }
  pop.classList.remove('dock');pop.style.right='auto';pop.style.bottom='auto';pop.style.width='';
  let x,y;
  if(!r){x=(vw-pw)/2;y=(vh-ph)/2}
  else{
    const side=r.right<320?['right','bottom','top']:['bottom','top','right','left'];
    let pl=null;
    for(const s of side){
      if(s==='bottom'&&vh-(hy+hh)>=ph+g)pl=s;
      else if(s==='top'&&hy>=ph+g)pl=s;
      else if(s==='right'&&vw-(hx+hw)>=pw+g)pl=s;
      else if(s==='left'&&hx>=pw+g)pl=s;
      if(pl)break;
    }
    if(pl==='bottom'){x=hx+hw/2-pw/2;y=hy+hh+g}
    else if(pl==='top'){x=hx+hw/2-pw/2;y=hy-ph-g}
    else if(pl==='right'){x=hx+hw+g;y=hy+hh/2-ph/2}
    else if(pl==='left'){x=hx-pw-g;y=hy+hh/2-ph/2}
    else{x=(vw-pw)/2;y=(vh-ph)/2}
  }
  x=Math.max(12,Math.min(vw-pw-12,x));y=Math.max(12,Math.min(vh-ph-12,y));
  pop.style.left=x+'px';pop.style.top=y+'px';
}
function tourSched(){if(!TOUR.on||TOUR.raf)return;TOUR.raf=requestAnimationFrame(()=>{TOUR.raf=0;tourPlace()})}
function tourShow(i,dir){
  if(!TOUR.on)return;
  dir=dir||1;
  while(i>=0&&i<TOUR.list.length){
    const st=TOUR.list[i],t=tourFind(st);
    if(t){TOUR.i=i;TOUR.tgt=t;tourObserve();break}
    i+=dir;
  }
  if(i<0||i>=TOUR.list.length){if(i>=TOUR.list.length)tourStop();return}
  const st=TOUR.list[i],n=TOUR.list.length,last=i===n-1;
  const pop=TOUR.pop;
  pop.innerHTML=`<div class="tour-hd"><span class="tour-badge">Шаг ${i+1} из ${n}</span><button class="tour-x" type="button" data-tour="x" aria-label="Закрыть тур">✕</button></div>
    <h3 class="tour-ti">${esc(st.title)}</h3><p class="tour-tx">${esc(st.text)}</p>
    <div class="tour-ft"><div class="tour-dots">${TOUR.list.map((_,k)=>`<i class="${k===i?'on':''}"></i>`).join('')}</div>
    <div class="tour-btns">${i>0?'<button class="btn ghost" type="button" data-tour="prev">← Назад</button>':''}<button class="btn" type="button" data-tour="next">${last?'Завершить':'Далее →'}</button></div></div>`;
  pop.classList.remove('tour-in');void pop.offsetWidth;pop.classList.add('tour-in');
  try{TOUR.tgt.scrollIntoView({block:'center',inline:'nearest'})}catch(e){}
  tourPlace();
  clearTimeout(TOUR.tm);TOUR.tm=setTimeout(tourPlace,320);
  const nb=pop.querySelector('[data-tour="next"]');if(nb)try{nb.focus({preventScroll:true})}catch(e){}
}
function tourNext(d){
  if(!TOUR.on)return;
  if(d<0&&TOUR.i===0)return;
  if(d>0&&TOUR.i>=TOUR.list.length-1){tourStop();return}
  tourShow(TOUR.i+d,d);
}
function tourStop(){
  if(!TOUR.on)return;
  TOUR.on=false;uiSet(TOUR_KEY,tourVer());
  clearTimeout(TOUR.tm);clearTimeout(TOUR.tm2);
  if(TOUR.raf){cancelAnimationFrame(TOUR.raf);TOUR.raf=0}
  if(TOUR.loop){cancelAnimationFrame(TOUR.loop);TOUR.loop=0}
  if(TOUR.ro){TOUR.ro.disconnect();TOUR.ro=null}
  if(TOUR.ov)TOUR.ov.remove();if(TOUR.pop)TOUR.pop.remove();
  TOUR.ov=TOUR.pop=TOUR.tgt=null;
  window.removeEventListener('resize',tourSched);window.removeEventListener('scroll',tourSched,true);
  document.removeEventListener('keydown',tourKey,true);document.removeEventListener('click',tourClick,true);
}
function tourKey(e){
  if(!TOUR.on)return;
  let a=null;
  if(e.key==='Escape')a=tourStop;
  else if(e.key==='ArrowRight')a=()=>tourNext(1);
  else if(e.key==='ArrowLeft')a=()=>tourNext(-1);
  if(!a)return;
  e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();a();
}
function tourClick(e){
  if(!TOUR.on)return;
  const b=e.target.closest&&e.target.closest('[data-tour]');
  if(b&&TOUR.pop&&TOUR.pop.contains(b)){
    e.preventDefault();e.stopPropagation();
    const k=b.dataset.tour;
    if(k==='x')tourStop();else if(k==='prev')tourNext(-1);else tourNext(1);
    return;
  }
  /* клик по сайдбару не блокируется: тур закрывается, а переход выполняется как обычно */
  if(e.target.closest&&e.target.closest('#nav,#nav-fix,#ux-mode')&&!(TOUR.tgt&&TOUR.tgt.contains(e.target))){tourStop();return}
  /* микро-задача: клик по подсвеченному элементу проходит насквозь и переводит на следующий шаг */
  const st=TOUR.list[TOUR.i];
  if(st&&st.task&&TOUR.tgt&&TOUR.tgt.contains(e.target)){
    clearTimeout(TOUR.tm2);TOUR.tm2=setTimeout(()=>tourNext(1),450);
  }
}
function tourStart(){
  if(TOUR.on)return;
  const list=TOUR_STEPS.filter(st=>tourFind(st));
  if(!list.length)return;
  TOUR.list=list;TOUR.on=true;
  const ov=document.createElement('div');ov.id='tour-ov';ov.className='tour-ov';
  ov.innerHTML=`<svg class="tour-svg" width="100%" height="100%" aria-hidden="true"><defs><mask id="tour-mk" maskUnits="userSpaceOnUse" x="0" y="0" width="100%" height="100%"><rect x="0" y="0" width="100%" height="100%" fill="#fff"/><rect id="tour-hole" rx="10" ry="10" fill="#000"/></mask></defs><rect x="0" y="0" width="100%" height="100%" class="tour-dim" mask="url(#tour-mk)"/></svg><div class="tour-bk"></div><div class="tour-bk"></div><div class="tour-bk"></div><div class="tour-bk"></div><div class="tour-ring"></div>`;
  document.body.appendChild(ov);
  const pop=document.createElement('div');pop.className='tour-pop';pop.setAttribute('role','dialog');pop.setAttribute('aria-label','Тур по интерфейсу');
  document.body.appendChild(pop);
  TOUR.ov=ov;TOUR.pop=pop;TOUR.hole=ov.querySelector('#tour-hole');TOUR.ring=ov.querySelector('.tour-ring');TOUR.bk=[...ov.querySelectorAll('.tour-bk')];
  window.addEventListener('resize',tourSched);window.addEventListener('scroll',tourSched,true);
  document.addEventListener('keydown',tourKey,true);document.addEventListener('click',tourClick,true);
  if(window.ResizeObserver)TOUR.ro=new ResizeObserver(tourSched);
  tourShow(0,1);
  TOUR.lr=tourRect();TOUR.loop=requestAnimationFrame(tourLoop);
}
window.tourStart=tourStart;

/* автозапуск один раз: после первого рендера с данными портфеля и ушедшей заставки */
let _tourAuto=false;
function tourAutoCheck(tries){
  if(_tourAuto||TOUR.on||!S.cfg||tourSeen())return;
  if(!(S.data&&!S.data.empty))return;
  _tourAuto=true;
  const wait=n=>setTimeout(()=>{
    if(TOUR.on||tourSeen())return;
    if(document.getElementById('boot-splash')&&n<20){wait(n+1);return}
    /* бегущая строка появляется над шапкой и сдвигает её — ждём её (до ~4 с), чтобы первый шаг не прыгал */
    if(typeof TKR!=='undefined'&&!TKR.items.length&&!(typeof tkrOff==='function'&&tkrOff())&&n<8){wait(n+1);return}
    tourStart();
  },n?500:1200);
  wait(0);
}
{
  const _rn=renderNow;
  renderNow=function(){const r=_rn.apply(this,arguments);try{tourAutoCheck()}catch(e){}return r};
}
