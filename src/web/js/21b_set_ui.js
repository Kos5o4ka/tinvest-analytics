/* ── Настройки: панель состояния, поиск, журнал изменений и сборка экрана ── */
/* ── панель состояния ── */
function stTile(id,lbl,ico,go){return`<div class="st-tile" id="${id}"><div class="st-tl"><i>${stIco(ico)}</i>${lbl}<span class="st-dot mu" data-d></span></div><div class="st-tv" data-v>…</div><div class="st-ts" data-s>Загружаю</div><button class="btn ghost st-ta" data-to="${go}" data-a>Открыть</button></div>`}
function stTileSet(id,dot,v,s,act){const t=document.getElementById(id);if(!t)return;
  t.querySelector('[data-d]').className='st-dot '+dot;t.querySelector('[data-v]').textContent=v;t.querySelector('[data-s]').textContent=s;if(act)t.querySelector('[data-a]').textContent=act}
function stBadge(sec,cls){const a=document.querySelector(`#set-nav [data-to="${sec}"] .st-nb`);if(a)a.className='st-nb'+(cls?' '+cls:'')}
async function stTiles(c){
  const tz=async p=>{try{return await api(p)}catch(e){return null}};
  /* Т-Инвестиции */
  stTileSet('st-t1',c.token_set?'pos':'warn',c.token_set?'Токен сохранён':'Токен не задан',
    c.token_set?`только чтение · ${c.token_hint}${c.sandbox?' · песочница':''}`:'Добавьте токен, чтобы увидеть портфель',c.token_set?'Изменить':'Добавить');
  stBadge('set-conn',c.token_set?'':'warn');
  const [ds,au,tg,ld,bk]=await Promise.all([tz('/api/dataserver'),tz('/api/auth/status'),isPro()?tz('/api/tg/info'):Promise.resolve(null),tz('/api/localdata'),tz('/api/backup/status')]);
  if(!document.getElementById('st-t2'))return;
  if(au)AUTH.st=au;
  /* сервер данных */
  if(!ds)stTileSet('st-t2','mu','Нет данных','Не удалось получить статус');
  else if(ds.mode==='server')stTileSet('st-t2','pos','Подключён',String(ds.url||'').replace(/^https?:\/\//,''));
  else if(ds.mode==='direct')stTileSet('st-t2','mu','Напрямую',(c.data_server||'').toLowerCase()==='off'?'Сервер отключён вручную':'Прямые запросы к источникам');
  else stTileSet('st-t2','warn','Недоступен','Работаем напрямую, повтор через '+(ds.retry_in||'…')+' с');
  /* Telegram-бот */
  const loggedIn=au&&au.state==='ok'&&(au.username||au.expires);
  const tgOn=!!c.tg_enabled;
  if(!isPro())stTileSet('st-t3','mu','Доступно в Pro','Уведомления в Telegram','Подробнее');
  else if(au&&au.state==='offline')stTileSet('st-t3','warn','Сервер недоступен','Вход проверить не удалось');
  else if(!loggedIn)stTileSet('st-t3','warn','Вход не выполнен','Нужен ключ из бота');
  else stTileSet('st-t3',tgOn?'pos':'mu','Вход выполнен'+(au.username?' · @'+au.username:''),`${au.expires?'ключ до '+authTime(au.expires)+' · ':''}уведомления ${tgOn?'включены':'выключены'}`,'Настроить');
  stBadge('set-acc',isPro()&&!loggedIn&&!(au&&au.state==='ok')?'warn':'');
  /* данные на компьютере */
  const last=bk&&bk.last;
  stTileSet('st-t4',!last?(bk&&bk.dir?'warn':'mu'):last.ok?'pos':'neg',ld?ldBytes(ld.total):'—',
    !last?'Резервных копий ещё не делали':last.ok?'Копия: '+new Date(last.t*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'Последняя копия не удалась','Копии');
  stBadge('set-local',last&&!last.ok?'neg':'');
}
/* ── поиск по настройкам ── */
function stSearch(q){
  q=String(q||'').trim().toLowerCase();
  const root=document.getElementById('st-main');if(!root)return;
  let any=false;
  root.querySelectorAll('.st-sec').forEach(sec=>{
    let vis=0;const secHit=q&&(sec.querySelector('.st-sh').textContent.toLowerCase().includes(q));
    sec.querySelectorAll('.st-card').forEach(card=>{
      const rows=[...card.querySelectorAll('.st-row,.st-more')],cardHit=!q||card.dataset.q.includes(q)||secHit;
      let n=0;
      rows.forEach(r=>{const h=!q||cardHit||(r.dataset.q||'').includes(q);r.classList.toggle('st-nomatch',!h);r.classList.toggle('st-hit',!!q&&h&&(r.dataset.q||'').includes(q));if(h)n++});
      const show=!q||cardHit||n>0;card.hidden=!show;if(show)vis++;
    });
    sec.hidden=!!q&&!vis;if(!sec.hidden)any=true;
    const a=document.querySelector(`#set-nav [data-to="${sec.id}"]`);if(a)a.hidden=!!q&&sec.hidden;
  });
  const tl=document.getElementById('st-tiles');if(tl)tl.hidden=!!q;const wl=document.getElementById('st-welcome');if(wl)wl.hidden=!!q;
  const e=document.getElementById('st-empty');if(e)e.hidden=!q||any;
  if(q){const b=document.getElementById('st-q-clear');if(b)b.hidden=false}else{const b=document.getElementById('st-q-clear');if(b)b.hidden=true}
}
/* scroll-spy: подсвечиваем раздел, который сейчас у верхней границы */
function stSpy(){
  const view=document.getElementById('view'),nav=document.getElementById('set-nav');
  if(!view||!nav){if(window._stSpyH&&view)view.removeEventListener('scroll',window._stSpyH);return}
  const secs=[...view.querySelectorAll('.st-sec')].filter(s=>!s.hidden);if(!secs.length)return;
  const top=view.getBoundingClientRect().top+90;let cur=secs[0];
  for(const s of secs)if(s.getBoundingClientRect().top<=top)cur=s;
  if(view.scrollTop+view.clientHeight>=view.scrollHeight-4)cur=secs[secs.length-1];
  nav.querySelectorAll('[data-to]').forEach(a=>{const on=a.dataset.to===cur.id;a.classList.toggle('on',on);if(on)a.setAttribute('aria-current','true');else a.removeAttribute('aria-current')});
}
function stGoto(id){
  const t=document.getElementById(id),v=document.getElementById('view');if(!t||!v)return;
  const red=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  v.scrollTo({top:Math.max(0,t.getBoundingClientRect().top-v.getBoundingClientRect().top+v.scrollTop-18),behavior:red?'auto':'smooth'});
  document.querySelectorAll('#set-nav [data-to]').forEach(a=>{const on=a.dataset.to===id;a.classList.toggle('on',on);if(on)a.setAttribute('aria-current','true');else a.removeAttribute('aria-current')});
}
/* ── версия и список изменений ── */
function stChangelog(list){return`<div class="cl">${list.map(([v,d,items])=>`<div><div class="vh"><b>Версия ${v}</b><span>${d}</span></div><ul>${items.map(i=>`<li>${i}</li>`).join('')}</ul></div>`).join('')}</div>`}
function setNewsHtml(c){
  const cur=CHANGELOG[0]||['',''];
  return`<div class="st-card" id="whatsnew" data-q="версия что нового изменения журнал"><div class="st-ver"><div class="st-vn mono">v${esc(c.version||'')}</div><div class="st-vt"><b>TAnalytic</b><span>${cur[1]?'Обновление от '+esc(cur[1]):'Текущая версия'}</span></div></div>
    <div class="st-pad">${stChangelog(CHANGELOG.slice(0,1))}</div>
    ${CHANGELOG.length>1?stMore('Предыдущие версии ('+(CHANGELOG.length-1)+')',stChangelog(CHANGELOG.slice(1))):''}</div>`+
    stGroup('Роадмап',`<div class="st-pad">${roadmapHtml()}</div>`,{hint:'что планируется'});
}
async function renderSettings(){
  S.charts=[];
  const view=$('#view'),keep=view.querySelector('.st')?view.scrollTop:0;
  try{S.cfg=await api('/api/config')}catch(e){view.innerHTML=`<div class="wrap"><div class="msg err">${esc(e.message)}</div></div>`;return}
  const c=S.cfg;
  updateModeBadge(c);
  const msg=stMsg;
  /* подключение */
  const conn=stGroup('Т-Инвестиции',
    stRow('API-токен',`Только для чтения — торговать с ним нельзя. Хранится на этом компьютере${c.token_set?` · <span class="pos">сохранён (${esc(c.token_hint)})</span>`:''}`,
      stSecret('tok',c.token_set?'вставьте новый токен, чтобы заменить':'t.XXXXXXXXXXXXXXXXXXXX','autocomplete="off"','API-токен Т-Инвестиций'),{id:'row-tok'})+
    stRow('Действия','',`<button class="btn" id="save" disabled>Сохранить и подключиться</button><button class="btn ghost" id="test">Проверить</button>${c.token_set?'<button class="btn ghost danger" id="clr">Удалить токен</button>':''}`)+
    stRow('Режим песочницы','Виртуальный счёт без реальных денег. Токен песочницы работает только с этим режимом, боевой — только без него',stSw('sb',c.sandbox,'Режим песочницы'))+
    stRow('Новый счёт в песочнице','Песочница сначала пуста — откройте виртуальный счёт',`<button class="btn ghost" id="sbopen">Открыть счёт</button>`,{id:'row-sbo',hidden:!(c.sandbox&&c.token_set),kw:'песочница'})+
    stRow('Пополнить счёт','Виртуальные рубли на выбранный слева счёт',`<input class="in num st-num" type="number" id="amt" value="1000000" min="1" step="1000" aria-label="Сумма пополнения, рублей"><span class="st-unit">₽</span><button class="btn ghost" id="sbpay">Пополнить</button>`,{id:'row-sbp',hidden:!(c.sandbox&&c.token_set),kw:'песочница'})+
    stMore('Как получить токен (1 минута)',`1. Откройте <a href="https://www.tbank.ru/invest/settings/api/" target="_blank" rel="noopener noreferrer">tbank.ru/invest/settings/api</a> и войдите в Т-Банк (или в приложении Т-Инвестиции: Профиль → Настройки → Токены T-Invest API).<br>
      2. Нажмите «Создать токен», выберите доступ <b>«Только для чтения»</b> и все счета (или только нужные).<br>
      3. Скопируйте токен сразу — второй раз его не покажут — и вставьте в поле выше.<br>
      Торговый токен не нужен: программа ничего не покупает и не продаёт. Отозвать токен можно на той же странице в любой момент.`),
    {id:'conn-card',hint:c.token_set?'<span class="pos">токен сохранён</span>':'токен не задан'});
  /* внешний вид */
  const th=curTheme();
  const prev=k=>`<span class="th-prev th-${k}"><i class="s"></i><i class="h"></i><i class="b b1"></i><i class="b b2"></i><i class="b b3"></i></span>`;
  const themes=[['auto','Авто','как в системе'],['light','Светлая',''],['dark','Тёмная','']];
  const perm=('Notification' in window)?Notification.permission:'unsupported';
  const look=stGroup('Тема оформления',
    `<div class="st-pad"><div class="st-themes" id="thsel" role="group" aria-label="Тема оформления">${themes.map(([k,t,d])=>`<button type="button" data-t="${k}" class="${th===k?'on':''}" aria-pressed="${th===k}">${k==='auto'?`<span class="th-prev th-auto">${prev('dark')}${prev('light')}</span>`:prev(k)}<span class="th-n"><b>${t}</b>${d?`<small>${d}</small>`:''}</span><em class="th-c">${stIco('check',2.6)}</em></button>`).join('')}</div></div>`,{hint:'применяется сразу',q:'светлая тёмная авто оформление'})+
    stGroup('Напоминания',
    stRow('Напоминать о выплатах','За сколько дней предупреждать на «Обзоре» и в «Выплатах» (0 — выключить)',`<input class="in num st-num" id="nd" type="number" min="0" max="60" value="${c.notify_days??7}" aria-label="За сколько дней напоминать о выплатах"><span class="st-unit">дн.</span>`)+
    stRow('Системные уведомления','Приходят, пока программа открыта',`<span class="st-who" id="ntf-st">${perm==='granted'?'Разрешены':perm==='denied'?'Запрещены в браузере':perm==='unsupported'?'Не поддерживаются':'Не разрешены'}</span><button class="btn ghost" id="ntf" ${perm==='granted'||perm==='unsupported'?'disabled':''}>Разрешить</button>`)+
    stMore('Печать отчёта','Кнопка PDF сверху → «Сохранить как PDF»: печатается текущий раздел и период.'),{hint:'выплаты и уведомления'})+
    setMenuHtml();
  /* расчёты */
  const calc=stGroup('Прогноз ключевой ставки',
    stRow('Источник прогноза','Для флоатеров: ставка не объявленных купонов = ключевая на начало периода + спред эмитента',`<select class="in st-sel" id="krmode" aria-label="Источник прогноза ключевой ставки">${[['cbr','Прогноз Банка России (по умолчанию)'],['survey','Опрос аналитиков Банка России'],['market','Рынок: форварды КБД'],['flat','Без изменений (текущая ставка)']].map(([k,t])=>`<option value="${k}" ${(c.keyrate_mode||'cbr')===k?'selected':''}>${t}</option>`).join('')}</select>`)+
    `<p class="st-line" id="krinfo">Загружаю…</p>`+
    stMore('Чем отличаются источники','«Прогноз Банка России» — среднесрочный прогноз ЦБ (середина диапазона средней ставки за год), «Опрос» — медиана макроопроса аналитиков, «КБД» — форвардные ставки кривой за вычетом срочной премии (грубо), «Без изменений» — текущая ставка. Если выбранный источник недоступен, берётся следующий по списку.'),
    {hint:'для флоатеров'})+setCrowdHtml(c);
  const sec=(i,body)=>stSec(SET_TOC[i][0],SET_TOC[i][1],SET_TOC[i][3],SET_TOC[i][2],body);
  view.innerHTML=`<div class="st fade">
  <aside class="st-side" aria-label="Навигация по настройкам">
    <label class="st-search">${stIco('search')}<input id="st-q" type="search" placeholder="Найти настройку…" autocomplete="off" spellcheck="false" aria-label="Найти настройку"><button type="button" id="st-q-clear" hidden aria-label="Очистить поиск">Esc</button></label>
    <nav id="set-nav" aria-label="Разделы настроек">${SET_TOC.map(([id,t,ic])=>`<a href="#${id}" data-to="${id}">${stIco(ic)}<span>${esc(t)}</span><i class="st-nb"></i></a>`).join('')}</nav>
    <div class="st-sv"><span class="mono">v${esc(c.version||'')}</span><span>TAnalytic</span></div>
  </aside>
  <div class="st-main" id="st-main">
    ${!c.token_set?`<div class="st-welcome" id="st-welcome"><b>Добро пожаловать</b><span>Вставьте API-токен Т-Инвестиций, чтобы увидеть аналитику, или импортируйте отчёт другого брокера. Всё хранится только на этом компьютере.</span></div>`:''}
    <div class="st-tiles" id="st-tiles">${stTile('st-t1','Т-Инвестиции','conn','set-conn')}${stTile('st-t2','Сервер данных','srv','ds-card')}${stTile('st-t3','Telegram-бот','tg','set-acc')}${stTile('st-t4','Данные','local','set-local')}</div>
    <div class="msg info" id="st-empty" hidden>Ничего не найдено. Попробуйте другое слово, например «токен», «тема» или «копия».</div>
  </div></div>`;
  const main=document.getElementById('st-main');
  const html=[sec(0,conn+setDsHtml(c)),sec(1,setAccHtml()+setTgHtml(c)),sec(2,look),sec(3,calc),sec(4,setLocalHtml(c)+setBackupHtml(c)),
    sec(5,setNewsHtml(c)),sec(6,setDangerHtml(c))];
  main.insertAdjacentHTML('beforeend',html.join(''));
  if(keep){view.scrollTop=keep;const st=view.querySelector('.st');if(st)st.classList.remove('fade')}
  stSecretBind(main);
  /* навигация, поиск, scroll-spy */
  $('#set-nav').onclick=e=>{const a=e.target.closest('[data-to]');if(!a)return;e.preventDefault();stGoto(a.dataset.to)};
  main.querySelector('#st-tiles').onclick=e=>{const b=e.target.closest('[data-to]');if(b)stGoto(b.dataset.to)};
  const q=$('#st-q');
  q.oninput=()=>stSearch(q.value);
  q.onkeydown=e=>{if(e.key==='Escape'&&q.value){e.preventDefault();e.stopPropagation();q.value='';stSearch('');stSpy()}};
  $('#st-q-clear').onclick=()=>{q.value='';stSearch('');q.focus()};
  if(window._stSpyH)view.removeEventListener('scroll',window._stSpyH);
  let raf=0;window._stSpyH=()=>{if(raf)return;raf=requestAnimationFrame(()=>{raf=0;stSpy()})};
  view.addEventListener('scroll',window._stSpyH,{passive:true});stSpy();
  stTiles(c);
  /* тема: сохраняется сразу */
  $('#thsel').onclick=e=>{const b=e.target.closest('[data-t]');if(!b)return;applyTheme(b.dataset.t);post('/api/config',{theme:b.dataset.t}).then(()=>stOk(b)).catch(()=>{});
    $('#thsel').querySelectorAll('button').forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-pressed',on)});stMsg('Тема сохранена',1,true)};
  /* ключевая ставка: сохраняется сразу */
  const krShow=async()=>{try{const k=await api('/api/keyrate');$('#krinfo').innerHTML=k.source==='none'?'Прогноз сейчас недоступен: купоны флоатеров считаются по последней известной ставке.':`Сейчас используется: <b>${esc(k.name)}</b>${k.as_of?`, на ${esc(k.as_of)}`:''}${k.mode!==k.source?` (выбранный источник «${esc(k.mode)}» недоступен)`:''}. Ключевая ставка сейчас ${pctp(k.key_rate,2)}; средняя по годам: ${(k.yearly||[]).slice(0,4).map(y=>y.year+' — '+pctp(y.mid,1)).join(', ')}.`}catch(e){$('#krinfo').textContent='Не удалось получить прогноз: '+e.message}};
  krShow();
  $('#krmode').onchange=async e=>{const el=e.currentTarget;try{$('#krinfo').textContent='Загружаю…';await post('/api/config',{keyrate_mode:el.value});S.cfg.keyrate_mode=el.value;S.bonds=null;stOk(el);krShow()}catch(x){msg(x.message);krShow()}};
  /* напоминания: сохраняются сразу */
  $('#nd').onchange=async e=>{const el=e.currentTarget;try{await post('/api/config',{notify_days:el.value});S.cfg.notify_days=+el.value;stOk(el)}catch(x){msg(x.message)}};
  $('#ntf').onclick=async()=>{try{if(!('Notification' in window))return msg('Браузер не поддерживает уведомления');const r=await Notification.requestPermission();
    $('#ntf-st').textContent=r==='granted'?'Разрешены':r==='denied'?'Запрещены в браузере':'Не разрешены';if(r==='granted')$('#ntf').disabled=true;
    msg(r==='granted'?'Уведомления разрешены':'Уведомления не разрешены',r==='granted')}catch(e){msg(e.message)}};
  try{bindSetDs(c,msg)}catch(e){}
  try{bindSetTg(c,msg)}catch(e){}
  try{bindSetBackup(c,msg)}catch(e){}
  try{bindSetCrowd(c,msg)}catch(e){}
  try{bindSetAcc(msg)}catch(e){}
  /* адреса API, сертификат и проверка SSL больше не редактируются в окне: в настройках остаются как были */
  const body=()=>({token:stSecVal('tok'),sandbox:$('#sb').checked});
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const reset=()=>{S.data=S.bonds=S.hist=null;S.account='all';persist()};
  try{bindSetLocal(c,msg,busy,reset)}catch(e){}
  /* токен: кнопка активна, пока в поле есть новое значение */
  const dTok=stDirty('save',['tok','sb']);stEnter(['tok'],'save');
  $('#save').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await post('/api/config',body());const r=await post('/api/test');reset();
    try{S.cfg=await api('/api/config');updateModeBadge(S.cfg)}catch(_){updateModeBadge({token_set:true,sandbox:$('#sb').checked})}
    msg(`Подключено. Счетов: ${r.accounts}.`,1);S.page='dash';persist();renderNav();load(true)}catch(x){msg(x.message);dTok.upd()}};
  $('#test').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());const r=await post('/api/test');msg(`Подключение работает. Счетов: ${r.accounts}.`,1)});
  /* песочница и SSL — переключатели сохраняются сразу */
  /* песочница меняет и адреса API, и нужный токен — применяется вместе с токеном по «Сохранить и подключиться», а не сразу */
  $('#sb').onchange=e=>{const el=e.currentTarget;if(el.checked===!!c.sandbox)return;
    stMsg(el.checked?'Вставьте токен песочницы и нажмите «Сохранить и подключиться».':'Вставьте боевой токен (только чтение) и нажмите «Сохранить и подключиться».',1)};
  $('#cache').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Заново загрузить все операции и цены из Т-Инвестиций? Это может занять время.'))return;await post('/api/cache/clear');reset();msg('Локальный кэш очищен, данные загрузятся заново.',1);load(true)});
  if($('#clr'))$('#clr').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Удалить сохранённый токен?'))return;await post('/api/config',{clear_token:true});if(S.cfg)S.cfg.token_set=false;updateModeBadge(S.cfg);reset();renderSettings()});
  if($('#sbopen'))$('#sbopen').onclick=e=>busy(e.currentTarget,async()=>{const r=await post('/api/sandbox/open');S.account=r.accountId;persist();S.data=null;msg('Открыт счёт '+r.accountId,1);load(true)});
  if($('#sbpay'))$('#sbpay').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/sandbox/payin',{accountId:S.account,amount:$('#amt').value});S.data=S.bonds=S.hist=null;msg('Счёт пополнен на '+M(+$('#amt').value,'rub',0),1);load(true)});
}
