/* ── UX-реворкинг: 9 разделов + вкладки .seg, Базовый/Профи, счёт в шапке, сворачиваемый сайдбар, подсказки, чек-лист, мини-тур ── */
const UX_SECTIONS=[
  {id:'home',title:'Главная',icon:'dash',basic:true,tabs:['dash']},
  {id:'pf',title:'Портфель',icon:'pos',basic:true,tabs:['pos','bonds','ret','bench','ops','fees','reb'],basicTabs:['pos','bonds','ret','ops','reb']},
  {id:'pay_ev',title:'Выплаты и события',icon:'pay',basic:true,tabs:['pay','off','cal']},
  {id:'bonds_mkt',title:'Облигации (рынок)',icon:'scr',basic:true,tabs:['scr','cmp','rot','dbx','lad','pri','map'],basicTabs:['scr','cmp','rot','lad','pri']},
  {id:'stocks_mkt',title:'Акции и фонды',icon:'hm',basic:false,tabs:['sst','hm','stk','mm']},
  {id:'pulse',title:'Пульс рынка',icon:'mkt',basic:false,tabs:['mkt','fng','flw','mic','sig']},
  {id:'risk_ctrl',title:'Надёжность и риски',icon:'risk',basic:false,tabs:['risk','mon','iss','crp','dfl','watch']},
  {id:'taxes',title:'Налоги',icon:'tax',basic:true,tabs:['tax','txo']},
  {id:'calc_sec',title:'Калькулятор',icon:'calc',basic:true,tabs:['calc']}
];
const UX_TAB_SHORT={
  dash:'Главная',pos:'Позиции',bonds:'Облигации',ret:'Доходность',bench:'Бенчмарки',ops:'Операции',fees:'Комиссии',reb:'Ребалансировка',
  pay:'Выплаты',off:'Оферты',cal:'Календарь',
  scr:'Скринер',cmp:'Сравнение',rot:'Флоатеры или фиксы',dbx:'Линкеры и валютные',lad:'Лесенка',pri:'Первичка',map:'Карта рынка',
  sst:'Скринер акций',hm:'Тепловая карта',stk:'Карточка акции',mm:'Деньги и базис',
  mkt:'Ставки и КБД',fng:'Страх и жадность',flw:'Кто покупает',mic:'Стакан и ликвидность',sig:'Сигналы',
  risk:'Риски портфеля',mon:'Мониторинг',iss:'Эмитенты',crp:'Устойчивость',dfl:'Техдефолты',watch:'Наблюдение',
  tax:'Итоги года и ЛДВ',txo:'Оптимизация и ИИС-3',calc:'Калькулятор'
};
const UX_WHY={
  scr:'Подберите облигации по надёжности, доходности, сроку и купону. Нажмите на любую строку — откроется карточка бумаги.',
  cmp:'Сравните 2–5 облигаций лицом к лицу: доходность, спред к КБД, дюрацию, оферты и денежный поток.',
  rot:'Помогает выбрать между флоатерами и фиксами при разных сценариях ключевой ставки ЦБ.',
  dbx:'Оценка инфляционных ОФЗ-ИН (линкеров), радар покрытия ближайших оферт и налог на валютные облигации.',
  lad:'Соберите «лесенку» облигаций с равномерными выплатами и погашениями без риска реинвестирования.',
  pri:'Новые размещения облигаций: премия первички (NIP) к рынку, стоимость заморозки кэша и статистика первых 30 дней.',
  map:'Карта всех корпоративных облигаций «доходность vs дюрация» относительно кривой ОФЗ (КБД).',
  mm:'Сравнение фондов ликвидности (LQDT и др.) с накопительным счётом после налогов и базис фьючерсов.',
  crp:'Финансовая устойчивость эмитента по РСБУ: модели банкротства, скрытый долг и риск размытия акций.',
  txo:'Сбор убытков по FIFO для снижения НДФЛ и сравнение ИИС-3 с обычным брокерским счётом.',
  mic:'Оценка проскальзывания крупной заявки в стакане и поиск скрытых («айсберг») заявок.',
  risk:'Стресс-тест портфеля на изменение ставок, концентрацию по эмитентам и валютный риск.',
  reb:'Расчёт покупок и продаж для приведения долей портфеля к вашей целевой структуре.',
  flw:'Агрессия покупателей и продавцов в ленте сделок и дисбаланс стакана в реальном времени.',
  fng:'Сводный индекс настроений российского рынка на основе волатильности, ширины рынка и потоков.',
  dfl:'Лента технических и фактических дефолтов по облигациям с e-disclosure и флагами Мосбиржи.',
  bench:'Честное сравнение доходности вашего портфеля с индексами акций, облигаций и денежного рынка.'
};

const UX={
  mode:lsGet('ta_ux_mode')==='pro'?'pro':'basic',
  mini:lsGet('ta_side_mini')==='1',
  lastTab:lsJson('ta_ux_last',{}),
  whyOff:lsJson('ta_ux_why_off',{}),
  checks:lsJson('ta_ux_checks',{}),
  checkOff:lsGet('ta_ux_chk_off')==='1',
  ddOpen:false
};
function uxSyncMode(){
  document.documentElement.dataset.uxMode=UX.mode;
  document.body.classList.toggle('side-mini',UX.mini);
  const tg=$('#side-tog');if(tg)tg.textContent=UX.mini?'»':'«';
}
uxSyncMode();

function uxSetMode(m){
  UX.mode=m==='pro'?'pro':'basic';
  lsSet('ta_ux_mode',UX.mode);
  uxSyncMode();renderNav();render();
}
function uxMarkCheck(k){
  if(UX.checks[k])return;
  UX.checks[k]=1;lsSet('ta_ux_checks',JSON.stringify(UX.checks));
}
function uxSectionOf(page){
  return UX_SECTIONS.find(s=>s.tabs.includes(page))||null;
}
function uxVisTabs(sec){
  if(!sec)return[];
  const raw=(UX.mode==='basic'&&sec.basicTabs&&!sec.tabs.filter(t=>!sec.basicTabs.includes(t)).includes(S.page))?sec.basicTabs:sec.tabs;
  return raw.filter(k=>PAGES.some(p=>p&&p[0]===k)&&!navHid(k));
}

/* ── Инлайн ?-подсказки, ведущие в Базу знаний (42_kb.js) ── */
function uxTip(kbId,shortTxt){
  return`<button type="button" class="ux-q" data-kb-jump="${esc(kbId)}" title="${esc(shortTxt||'Открыть справку в Базе знаний')}" aria-label="${esc(shortTxt||'Справка')}">?</button>`;
}

/* ── Плашка гостевого режима ── */
function uxGuestBar(){
  return`<div class="ux-guest"><span><b>Гостевой режим</b> — рыночные разделы и калькулятор открыты без токена.</span>
    <span class="ux-guest-b"><button class="btn" data-go="set">Подключить счёт</button><button class="btn ghost" id="ux-g-demo">Демо-портфель</button></span></div>`;
}

/* ── Верхние вкладки внутри раздела (.seg) ── */
function uxSubTabs(){
  const sec=uxSectionOf(S.page);
  if(!sec)return'';
  const tabs=uxVisTabs(sec);
  if(tabs.length<=1)return'';
  const pgName=k=>UX_TAB_SHORT[k]||(PAGES.find(p=>p&&p[0]===k)||[k,k])[1];
  return`<div class="ux-subwrap"><div class="seg ux-sub" id="ux-sub">${tabs.map(k=>`<button class="${k===S.page?'on':''}" data-p="${esc(k)}">${esc(pgName(k))}${typeof proNavBadge==='function'?proNavBadge(k):''}</button>`).join('')}</div></div>`;
}

/* ── 1-строчная подсказка «Зачем этот экран» ── */
function uxWhyBanner(page){
  const t=UX_WHY[page];
  if(!t||UX.whyOff[page])return'';
  return`<div class="ux-why"><span>${esc(t)}</span><button type="button" class="ux-why-x" data-why-off="${esc(page)}" title="Скрыть подсказку">Понятно ×</button></div>`;
}

/* ── Блоки Главной: «Быстрые задачи» и Чек-лист «С чего начать» ── */
function uxDashBlocks(){
  if(S.data)uxMarkCheck('acc');
  const tasks=`<div class="ux-tasks">
    <button class="ux-tcard" data-ux-task="ofz"><b>Подобрать надёжные облигации</b><small>ОФЗ и корпоративные с высоким рейтингом</small></button>
    <button class="ux-tcard" data-ux-task="rot"><b>Флоатеры или фиксы?</b><small>Сравнить доходность при изменении ставки ЦБ</small></button>
    <button class="ux-tcard" data-ux-task="calc"><b>Посчитать, сколько накоплю</b><small>Капитал и пассивный доход с учётом инфляции</small></button>
    <button class="ux-tcard" data-ux-task="tax"><b>Проверить налоги за год</b><small>НДФЛ, льгота ЛДВ и вычет по ИИС-3</small></button>
  </div>`;
  const steps=[
    ['acc','Подключите счёт или откройте демо-портфель','set'],
    ['pay','Проверьте ближайшие выплаты и оферты','pay'],
    ['bond','Откройте карточку любой облигации в портфеле или скринере','scr'],
    ['srch','Попробуйте быстрый поиск по тикерам и экранам (⌘K / Ctrl+K)','__srch']
  ];
  const doneCnt=steps.filter(([k])=>UX.checks[k]).length;
  let chk='';
  if(!UX.checkOff&&doneCnt<steps.length){
    chk=`<div class="card ux-chk"><div class="ux-chk-h"><div><b>С чего начать</b> <span class="mu">· выполнено ${doneCnt} из ${steps.length}</span></div>
      <div class="row" style="gap:8px"><button class="btn ghost" id="ux-tour-go" style="padding:5px 10px;font-size:12px">Мини-тур (4 шага)</button>
      <button class="lnk" id="ux-chk-hide" style="font-size:12px">Скрыть</button></div></div>
      <div class="ux-chk-l">${steps.map(([k,t,act])=>`<button class="ux-chk-i${UX.checks[k]?' done':''}" data-ux-step="${esc(act)}"><i>${UX.checks[k]?'✓':'○'}</i><span>${esc(t)}</span></button>`).join('')}</div></div>`;
  }
  return chk+tasks;
}

/* ── Переопределяем renderNav: 9 сжатых разделов + переключатель «Базовый / Профи» ── */
const _renderNavPrev=renderNav;
renderNav=function(){
  const modeEl=$('#ux-mode');
  if(modeEl){
    modeEl.innerHTML=`<div class="seg ux-mseg"><button class="${UX.mode==='basic'?'on':''}" data-um="basic" title="6 основных разделов без перегруза">Базовый</button><button class="${UX.mode==='pro'?'on':''}" data-um="pro" title="Все 9 разделов и продвинутая аналитика">Профи</button></div>`;
  }
  const curSec=uxSectionOf(S.page);
  if(curSec){UX.lastTab[curSec.id]=S.page;lsSet('ta_ux_last',JSON.stringify(UX.lastTab))}
  const secs=UX_SECTIONS.filter(s=>UX.mode==='pro'||s.basic||(curSec&&curSec.id===s.id));
  const used=new Set(NAV_FIXED.concat(...UX_SECTIONS.flatMap(s=>s.tabs)));
  const extra=PAGES.filter(p=>p&&!used.has(p[0])&&!navHid(p[0]));
  let h=secs.map(s=>{
    const tabs=uxVisTabs(s);if(!tabs.length)return'';
    const act=curSec&&curSec.id===s.id;
    const target=(UX.lastTab[s.id]&&tabs.includes(UX.lastTab[s.id]))?UX.lastTab[s.id]:tabs[0];
    const cnt=tabs.length>1?`<span class="ux-cnt">${tabs.length}</span>`:'';
    return`<button class="${act?'on':''}" data-p="${esc(target)}" title="${esc(s.title)}">${svgI(IC[s.icon]||IC.dash)}<span class="nav-t">${esc(s.title)}</span>${cnt}</button>`;
  }).join('');
  if(extra.length){
    h+='<div class="sep"></div>'+extra.map(p=>`<button class="${p[0]===S.page?'on':''}" data-p="${esc(p[0])}" title="${esc(p[1])}">${svgI(IC[p[0]]||IC.dash)}<span class="nav-t">${esc(p[1])}</span></button>`).join('');
  }
  h+='<div class="sep"></div>'+NAV_FIXED.map(k=>PAGES.find(p=>p&&p[0]===k)).filter(Boolean).map(p=>`<button class="${p[0]===S.page?'on':''}" data-p="${esc(p[0])}" title="${esc(p[1])}">${svgI(IC[p[0]]||IC.set)}<span class="nav-t">${esc(p[1])}</span></button>`).join('');
  $('#nav').innerHTML=h;
  $('#period').innerHTML=PERIODS.map(([k,t])=>`<button class="${k===S.period?'on':''}" data-k="${k}">${t}</button>`).join('');
  $('#period').style.visibility=PERIOD_PAGES.includes(S.page)&&S.data?'visible':'hidden';
  const a=S.accounts.find(x=>x.id===S.account);
  const pgCur=PAGES.find(p=>p&&p[0]===S.page)||PAGES[0];
  if(pgCur&&S.page!==pgCur[0]){S.page=pgCur[0];persist()}
  $('#title').innerHTML=esc(pgCur[1])+(['imp','set','kb'].includes(S.page)||!S.data?'':` <small>${esc(S.account==='all'?'все счета':a?a.name:'')}</small>`);
  if(typeof demoBar==='function')try{demoBar();if(typeof demoSync==='function')demoSync()}catch(e){}
  uxRenderAccDropdown();
};

/* ── Дропдаун выбора счёта в шапке .top (синхронизирован с renderAccounts) ── */
function uxRenderAccDropdown(){
  const wrap=$('#acc-dd');if(!wrap)return;
  const accs=S.accounts||[];
  if(!accs.length||!S.data){wrap.innerHTML='';wrap.style.display='none';return}
  wrap.style.display='';
  const cur=accs.find(a=>a.id===S.account);
  const allTot=accs.filter(a=>!a.empty).reduce((s,a)=>s+(a.total||0),0);
  const label=S.account==='all'?'Все счета':(cur?cur.name:'Счёт');
  const sumTxt=S.account==='all'?short(allTot):(cur&&!cur.empty?short(cur.total):'пусто');
  const vis=accs.filter(a=>!S.hideEmpty||!a.empty||a.id===S.account);
  wrap.innerHTML=`<button type="button" class="btn ghost acc-dd-btn" id="acc-dd-btn" aria-expanded="${UX.ddOpen}">
    <span class="acc-dd-nm">${esc(label)}</span><span class="mu num">${esc(sumTxt)}</span><span class="acc-dd-ch">▾</span></button>
    ${UX.ddOpen?`<div class="acc-dd-menu" id="acc-dd-menu">
      <div class="acc-dd-h"><span>Выбор счёта</span><label class="msw"><input type="checkbox" id="acc-dd-he" ${S.hideEmpty?'checked':''}><i></i>скрыть пустые</label></div>
      <div class="acc-dd-list">
        ${accs.length>1?`<button class="${S.account==='all'?'on':''}" data-a="all"><b>Все счета</b><span class="num">${short(allTot)}</span></button>`:''}
        ${vis.map(a=>`<button class="${a.id===S.account?'on':''}" data-a="${esc(a.id)}"><b>${esc(a.name)}</b><span class="num">${a.empty?'пусто':short(a.total)}</span></button>`).join('')}
      </div></div>`:''}`;
}
const _renderAccPrev=renderAccounts;
renderAccounts=function(){_renderAccPrev.apply(this,arguments);uxRenderAccDropdown()};

/* ── Трекинг шагов чек-листа и 4-шаговый мини-тур ── */
const _goPrev=go;
go=function(p){
  if(p==='pay'||p==='off')uxMarkCheck('pay');
  _goPrev(p);
};
if(typeof openBond==='function'){
  const _obPrev=openBond;
  openBond=function(){uxMarkCheck('bond');return _obPrev.apply(this,arguments)};
}
if(typeof kpOpen==='function'){
  const _kpPrev=kpOpen;
  kpOpen=function(){uxMarkCheck('srch');return _kpPrev.apply(this,arguments)};
}

const UX_TOUR_STEPS=[
  {sel:'aside',title:'Умное меню и режим «Базовый / Профи»',text:'В «Базовом» режиме показаны 6 главных разделов без лишнего шума. Переключатель «Профи» вверху меню открывает все квантовые инструменты.'},
  {sel:'#acc-dd,#period',title:'Счёт и период всегда под рукой',text:'Переключайте брокерские счета и период доходности прямо в верхней панели — не нужно прокручивать боковое меню.'},
  {sel:'#srch',title:'Быстрый поиск ⌘K / Ctrl+K',text:'Мгновенно находите любую облигацию, акцию, эмитента или экран программы с клавиатуры.'},
  {sel:'#eye',title:'Режим инкогнито и PNG-карточка',text:'Глаз скрывает все суммы в рублях на экране, а кнопка PNG делает красивую карточку доходности для Telegram без абсолютных сумм.'}
];
let _uxTourI=-1;
function uxTourStop(){
  _uxTourI=-1;lsSet('ta_ux_tour_done','1');
  const el=$('#ux-tour');if(el)el.remove();
  document.querySelectorAll('.ux-hl').forEach(x=>x.classList.remove('ux-hl'));
}
function uxTourShow(i){
  document.querySelectorAll('.ux-hl').forEach(x=>x.classList.remove('ux-hl'));
  if(i>=UX_TOUR_STEPS.length){uxTourStop();return}
  _uxTourI=i;
  const st=UX_TOUR_STEPS[i];
  const tgt=document.querySelector(st.sel);
  if(tgt)tgt.classList.add('ux-hl');
  let box=$('#ux-tour');
  if(!box){box=document.createElement('div');box.id='ux-tour';box.className='ux-tour';document.body.appendChild(box)}
  box.innerHTML=`<div class="ux-tour-hd"><b>${esc(st.title)}</b><span class="mu">${i+1} / ${UX_TOUR_STEPS.length}</span></div>
    <p>${esc(st.text)}</p>
    <div class="ux-tour-ft"><button class="lnk" id="uxt-skip">Пропустить</button>
    <button class="btn" id="uxt-next">${i+1===UX_TOUR_STEPS.length?'Готово':'Далее →'}</button></div>`;
  $('#uxt-skip').onclick=uxTourStop;
  $('#uxt-next').onclick=()=>uxTourShow(i+1);
}
function uxTourStart(){uxTourShow(0)}

/* ── Единые делегированные обработчики UX ── */
document.addEventListener('click',e=>{
  const t=e.target;
  const um=t.closest('[data-um]');if(um){uxSetMode(um.dataset.um);return}
  if(t.closest('#side-tog')){UX.mini=!UX.mini;lsSet('ta_side_mini',UX.mini?'1':'0');uxSyncMode();return}
  const sub=t.closest('#ux-sub [data-p]');if(sub){go(sub.dataset.p);return}
  const wh=t.closest('[data-why-off]');if(wh){UX.whyOff[wh.dataset.whyOff]=1;lsSet('ta_ux_why_off',JSON.stringify(UX.whyOff));const el=wh.closest('.ux-why');if(el)el.remove();return}
  const kb=t.closest('[data-kb-jump]');if(kb){e.stopPropagation();S.kbArticle=kb.dataset.kbJump;go('kb');return}
  if(t.closest('#ux-g-demo')&&typeof demoEnter==='function'){demoEnter(t.closest('#ux-g-demo'));return}
  if(t.closest('#ux-tour-go')){uxTourStart();return}
  if(t.closest('#ux-chk-hide')){UX.checkOff=true;lsSet('ta_ux_chk_off','1');const c=t.closest('.ux-chk');if(c)c.remove();return}
  const step=t.closest('[data-ux-step]');
  if(step){const a=step.dataset.uxStep;if(a==='__srch'){if(typeof kpOpen==='function')kpOpen();else $('#srch').click()}else go(a);return}
  const task=t.closest('[data-ux-task]');
  if(task){
    const k=task.dataset.uxTask;
    if(k==='ofz'){S.scrPreset='ofz3';S.sf=Object.assign({},SCR_DEF,{kind:'ofz',cur:'RUB',tmax:'3',fl:'fix'});go('scr');return}
    go(k);return;
  }
  if(t.closest('#acc-dd-btn')){UX.ddOpen=!UX.ddOpen;uxRenderAccDropdown();return}
  const accBtn=t.closest('#acc-dd-menu [data-a]');
  if(accBtn){
    UX.ddOpen=false;
    if(accBtn.dataset.a!==S.account){S.account=accBtn.dataset.a;S.bonds=S.hist=null;persist();renderAccounts();renderNav();load(false)}
    else uxRenderAccDropdown();
    return;
  }
  if(UX.ddOpen&&!t.closest('#acc-dd')){UX.ddOpen=false;uxRenderAccDropdown()}
});
document.addEventListener('change',e=>{
  if(e.target&&e.target.id==='acc-dd-he'){S.hideEmpty=e.target.checked;persist();renderAccounts();return}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&_uxTourI>=0)uxTourStop()});
/* Обновляем уже отрисованную навигацию после загрузки этого файла */
if(typeof renderNav==='function')try{renderNav()}catch(e){}
