/* ── Настройки ── */
/* какие разделы показывать в меню (скрытые остаются доступными через поиск Ctrl+K) */
function setMenuHtml(){
  const hid=S.navHidden||[];
  const grp=NAV_GROUPS.map(([g,keys])=>`<div><div class="note" style="margin:8px 0 6px"><b>${esc(g)}</b></div><div class="kmenu">${keys.map(k=>{const t=(PAGES.find(p=>p&&p[0]===k)||[])[1];if(!t)return'';
    const lock=NAV_PINNED.includes(k);return`<label><input type="checkbox" ${hid.includes(k)?'':'checked'} ${lock?'disabled':''} onchange="navToggle('${k}',this.checked)">${esc(t)}${lock?' <span class="mu">(всегда)</span>':''}</label>`}).join('')}</div></div>`).join('');
  return`<div class="card"><h2>Разделы меню<span class="sp">скрывайте то, чем не пользуетесь</span></h2><div style="display:grid;gap:6px">${grp}
    <div class="row" style="margin-top:8px"><button class="btn ghost" onclick="navShowAll()">Показать все</button></div>
    <p class="note">Скрытый раздел по-прежнему открывается через поиск (Ctrl+K / Cmd+K). «Обзор» и «Настройки» скрыть нельзя.</p></div></div>`;
}
function navToggle(k,on){
  if(NAV_PINNED.includes(k))return;
  S.navHidden=S.navHidden.filter(x=>x!==k);if(!on)S.navHidden.push(k);
  lsSet('ta_nav_hidden',JSON.stringify(S.navHidden));renderNav();
}
function navShowAll(){S.navHidden=[];lsSet('ta_nav_hidden','[]');renderNav();renderSettings()}
/* ── Сервер данных ── */
function setDsHtml(c){
  const keySet=c.secret_set&&c.secret_set.data_key;
  return`<div class="card" id="ds-card"><h2>Сервер данных</h2><div style="display:grid;gap:14px">
    <p class="note">Данные рынка (Мосбиржа, ФНС, ЦБ, рейтинги, МСФО) берутся через ваш сервер — быстрее и без лишних запросов к источникам. Портфель и токен Т-Инвестиций идут напрямую в Т-Банк и на сервер не передаются.</p>
    <label class="field"><span>Адрес сервера (пусто — сервер по умолчанию, off — напрямую к источникам)</span><input class="in" id="ds-url" value="${esc(c.data_server||'')}" placeholder="сервер по умолчанию" autocomplete="off" spellcheck="false"></label>
    <label class="field"><span>Ключ доступа (из @${esc(AUTH.bot)}) ${keySet?'<span class="pos">· сохранён. Оставьте пустым, чтобы не менять</span>':''}</span><input class="in" type="password" id="ds-key" autocomplete="off" spellcheck="false"></label>
    <div class="row"><button class="btn" id="ds-save">Сохранить</button><button class="btn ghost" id="ds-test">Проверить</button>${keySet?'<button class="btn danger" id="ds-clr">Удалить ключ</button>':''}</div>
    <p class="note" id="ds-st">Загружаю…</p></div></div>`;
}
async function dsStatus(){
  const el=document.getElementById('ds-st');if(!el)return;
  try{const d=await api('/api/dataserver');
    const cnt=`Ответов с сервера с начала работы: из кэша ${d.hit}, свежих ${d.miss}${d.stale?`, устаревших ${d.stale}`:''}; напрямую: ${d.direct}.`;
    const as=AUTH.st,au=as&&as.state==='offline'?` Вход: сервер недоступен, работаем напрямую (${esc(as.error)}).`:as&&as.state==='ok'&&as.expires?` Ключ действует до ${esc(authTime(as.expires))}.`:'';
    el.innerHTML=d.mode==='direct'?`Режим: <b>напрямую</b> к источникам. ${esc(cnt)}`:d.mode==='server'?`Режим: <b>через сервер</b> ${esc(d.url)}. ${esc(cnt)}`:`Режим: <b>временно напрямую</b> — сервер недоступен (${esc(d.error)}), повтор через ${d.retry_in} с. ${esc(cnt)}`;
    if(au)el.innerHTML+=au}
  catch(e){el.textContent=''}
}
function bindSetDs(c,msg){
  const g=id=>document.getElementById(id);
  dsStatus();
  const save=async()=>{const b={data_server:g('ds-url').value};if(g('ds-key').value)b.data_key=g('ds-key').value;await post('/api/config',b);
    c.data_server=g('ds-url').value.trim();if(g('ds-key').value)c.secret_set=Object.assign({},c.secret_set,{data_key:true});g('ds-key').value=''};
  g('ds-save').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await save();msg('Сохранено. Новые запросы пойдут '+(c.data_server.toLowerCase()==='off'?'напрямую.':'через сервер.'),1);authCheck(true);renderSettings()}catch(x){msg(x.message)}finally{b.disabled=false}};
  g('ds-test').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{const r=await post('/api/dataserver/test',{url:g('ds-url').value,key:g('ds-key').value});
    msg(`Сервер работает: версия ${r.version}, записей в кэше ${r.cache_items}.`,1)}catch(x){msg(x.message)}finally{b.disabled=false}};
  if(g('ds-clr'))g('ds-clr').onclick=async()=>{try{if(!confirm('Удалить сохранённый ключ сервера данных?'))return;await post('/api/config',{clear_data_key:true});authCheck(true);c.secret_set=Object.assign({},c.secret_set,{data_key:false});renderSettings()}catch(x){msg(x.message)}};
}
/* ── Данные на компьютере ── */
function ldBytes(n){
  n=+n||0;
  if(n<1024)return n+' Б';
  if(n<1048576)return Math.max(1,Math.round(n/1024))+' КБ';
  return (n/1048576).toFixed(n<10485760?1:0)+' МБ';
}
function setLocalHtml(c){
  return`<div class="card" id="ld-card"><h2>Данные на компьютере</h2><div style="display:grid;gap:14px">
    <p class="note" style="margin:0">Всё, что программа запоминает — операции, история цен, справочник бумаг, логотипы, настройки, — лежит в одной папке на этом компьютере. В интернет она не отправляется.</p>
    <div><div class="note" style="margin-bottom:4px">Папка с данными</div><div class="mono ld-path" id="ld-dir">${esc(c.data_dir)}</div></div>
    <div id="ld-parts" class="ld-parts"><div class="note">Считаю размер…</div></div>
    <div class="row"><button class="btn ghost" id="ld-open">Открыть папку</button><button class="btn ghost" id="cache" title="Заново загрузить операции и цены из Т-Инвестиций">Перезагрузить всё из API</button><a class="btn ghost" href="/api/backup" download>Скачать резервную копию (zip)</a></div>
    <p class="note" style="margin:0">Простая резервная копия — zip с базой и настройками, токен в неё не входит. Зашифрованные копии по расписанию — в блоке «Резервная копия» ниже.</p>
    <div class="ld-danger"><div class="row"><button class="btn ghost" id="ld-clear">Очистить кэш</button><button class="btn danger" id="ld-wipe">Удалить все данные</button></div>
      <p class="note" style="margin:8px 0 0"><b>Очистить кэш</b> — удаляет логотипы и временные данные рынка (цены, рейтинги, справочники); они скачаются заново. Ваши операции, импорты, список наблюдения, заметки и настройки остаются.<br>
      <b>Удалить все данные</b> — стирает токен, ключ входа, базу и настройки. Вернуть их нельзя.</p></div>
    <p class="note" style="margin:0"><b>Чтобы удалить программу полностью:</b> закройте её, удалите папку <span class="mono">${esc(c.data_dir)}</span> и само приложение (на Mac — из «Программ», на Windows — файл или ярлык программы).</p></div></div>`;
}
async function ldLoad(){
  const el=document.getElementById('ld-parts');if(!el)return;
  try{const d=await api('/api/localdata');
    const mx=Math.max(1,...d.parts.map(p=>p.bytes));
    const desc={db:'база операций и кэш',cache:'кэш',logos:'логотипы бумаг',app:'скачанная программа',window:'данные окна приложения',config:'настройки, токен и ключ',other:'прочие файлы'};
    el.innerHTML=`<div class="ld-tot">Всего: <b>${ldBytes(d.total)}</b></div>`+d.parts.map(p=>`<div class="ld-row"><span class="ld-n"><span class="mono">${esc(p.name)}</span> <span class="mu">${esc(desc[p.key]||p.title)}</span></span><span class="ld-bar"><i style="width:${Math.max(p.bytes?2:0,Math.round(p.bytes/mx*100))}%"></i></span><span class="ld-v num">${ldBytes(p.bytes)}</span></div>`).join('')}
  catch(e){el.innerHTML=`<div class="note neg">${esc(e.message)}</div>`}
}
function bindSetLocal(c,msg,busy,reset){
  const g=id=>document.getElementById(id);
  ldLoad();
  g('ld-open').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/localdata/open')});
  g('ld-clear').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Очистить кэш?\n\nБудут удалены логотипы и временные данные рынка — они скачаются заново. Операции, настройки, токен и список наблюдения останутся.'))return;
    const r=await post('/api/localdata/clear');reset();msg('Кэш очищен, освобождено '+ldBytes(r.freed)+'.',1);ldLoad()});
  g('ld-wipe').onclick=e=>busy(e.currentTarget,async()=>{
    if(!confirm('Удалить ВСЕ данные программы с этого компьютера?\n\nБудут стёрты: токен Т-Инвестиций, ключ входа, база операций (включая импорт из отчётов брокеров), история, список наблюдения, заметки и настройки.\n\nЭто нельзя отменить. Сделайте резервную копию заранее, если она нужна.'))return;
    if(!confirm('Точно удалить всё? Программа вернётся к экрану входа, как при первом запуске.'))return;
    await post('/api/localdata/wipe',{confirm:'delete-all'});
    try{localStorage.clear()}catch(x){}
    location.reload()});
}
/* ── Аккаунт и доступ ── */
function setAccHtml(){
  return`<div class="card" id="acc-card"><h2>Аккаунт и доступ</h2><div style="display:grid;gap:12px">
    <p class="note" style="margin:0">Вход в программу выполняется по ключу из Telegram-бота. Ключ действует сутки, токен Т-Инвестиций боту не передаётся.</p>
    <div id="acc-who" class="ld-path">Проверяю…</div>
    <div class="row"><button class="btn ghost" id="acc-out" style="display:none">Выйти</button><a class="btn ghost" href="https://t.me/${esc(AUTH.bot)}" target="_blank" rel="noopener noreferrer">Открыть @${esc(AUTH.bot)}</a></div></div></div>`;
}
async function bindSetAcc(msg){
  const el=document.getElementById('acc-who');if(!el)return;
  try{AUTH.st=await api('/api/auth/status')}catch(e){}
  const s=AUTH.st;
  if(!s)el.textContent='Нет данных о входе.';
  else if(s.state==='ok'&&(s.username||s.expires))el.innerHTML=`Вы вошли${s.username?' как <b>@'+esc(s.username)+'</b>':''}${s.expires?`, ключ действует до <b>${esc(authTime(s.expires))}</b>`:''}.`;
  else if(s.state==='ok')el.textContent='Вход выполнен.';
  else if(s.state==='offline')el.textContent='Сервер входа недоступен — программа работает напрямую с источниками.';
  else el.textContent=s.server?'Вы не вошли: нужен ключ из бота.':'Сервер данных выключен — вход по ключу не нужен.';
  const out=document.getElementById('acc-out');
  if(out&&s&&s.state==='ok'&&(s.username||s.expires)){out.style.display='';
    out.onclick=async()=>{try{if(!confirm('Выйти и стереть ключ с этого компьютера?'))return;AUTH.st=await post('/api/auth/logout');authApply()}catch(e){msg(e.message)}}}
}
/* ── оглавление ── */
const SET_TOC=[['set-conn','Подключение'],['set-acc','Аккаунт'],['set-look','Внешний вид'],['set-calc','Расчёты'],['set-local','Данные на компьютере'],['set-adv','Для опытных'],['set-news','Что нового']];
function setSec(id,title,hint,body){
  return`<section class="set-sec" id="${id}">${title?`<div class="set-gh">${esc(title)}${hint?`<span>${esc(hint)}</span>`:''}</div>`:''}${body}</section>`;
}
async function renderSettings(){
  S.charts=[];
  try{S.cfg=await api('/api/config')}catch(e){$('#view').innerHTML=`<div class="wrap"><div class="msg err">${esc(e.message)}</div></div>`;return}
  const c=S.cfg;
  const conn=`<div class="card"><h2>Подключение к Т-Инвестициям${c.token_set?'<span class="sp pos">токен сохранён</span>':'<span class="sp">токен не задан</span>'}</h2><div style="display:grid;gap:18px">
    <label class="field"><span>API-токен ${c.token_set?`<span class="pos">· сохранён (…${esc(c.token_hint.slice(1))}). Оставьте пустым, чтобы не менять</span>`:''}</span>
      <input class="in" type="password" id="tok" placeholder="t.XXXXXXXXXXXXXXXXXXXX" autocomplete="off" spellcheck="false"></label>
    <div class="row"><button class="btn" id="save">Сохранить и подключиться</button><button class="btn ghost" id="test">Проверить</button>
      ${c.token_set?'<button class="btn danger" id="clr">Удалить токен</button>':''}</div>
    <div class="note" style="line-height:1.6"><b>Как получить токен</b> (1 минута):<br>
      1. Откройте <a href="https://www.tbank.ru/invest/settings/api/" target="_blank" rel="noopener noreferrer">tbank.ru/invest/settings/api</a> и войдите в Т-Банк (или в приложении Т-Инвестиции: Профиль → Настройки → Токены T-Invest API).<br>
      2. Нажмите «Создать токен», выберите доступ <b>«Только для чтения»</b> и все счета (или только нужные).<br>
      3. Скопируйте токен сразу — второй раз его не покажут — и вставьте в поле выше.<br>
      Торговый токен не нужен: программа ничего не покупает и не продаёт. Отозвать токен можно на той же странице в любой момент.</div>
    <div class="set-sub"><label class="sw"><input type="checkbox" id="sb" ${c.sandbox?'checked':''}><i></i><div><b>Режим песочницы</b><small>Для пробы без реальных денег. Токен песочницы работает только с этим режимом, боевой — только без него. После переключения нажмите «Сохранить и подключиться».</small></div></label>
      ${c.sandbox&&c.token_set?`<div class="row" style="margin-top:12px"><button class="btn ghost" id="sbopen">Открыть новый счёт</button>
      <input class="in num" type="number" id="amt" value="1000000" min="1" step="1000" style="width:160px"><button class="btn ghost" id="sbpay">Пополнить выбранный счёт, ₽</button></div>
      <p class="note" style="margin-top:8px">Песочница — виртуальный счёт без реальных данных: сначала он пуст.</p>`:''}</div></div></div>`;
  const look=`<div class="card"><h2>Оформление и напоминания</h2><div style="display:grid;gap:16px">
    <div class="row"><div class="seg" id="thsel">${[['auto','Авто'],['light','Светлая'],['dark','Тёмная']].map(([k,t])=>`<button data-t="${k}" class="${curTheme()===k?'on':''}">${t}</button>`).join('')}</div></div>
    <div class="row"><label class="field" style="max-width:260px"><span>Напоминать о выплатах за, дней (0 — выключить)</span><input class="in num" id="nd" type="number" min="0" max="60" value="${c.notify_days??7}"></label>
      <button class="btn ghost" id="ndsave" style="align-self:flex-end">Сохранить</button><button class="btn ghost" id="ntf" style="align-self:flex-end">Разрешить системные уведомления</button></div>
    <p class="note">Напоминания показываются на «Обзоре» и «Выплатах», а системные уведомления приходят, пока программа открыта. Печать отчёта: кнопка PDF сверху → «Сохранить как PDF» (печатается текущий раздел и период).</p></div></div>
    ${setMenuHtml()}`;
  const calc=`<div class="card"><h2>Прогноз ключевой ставки<span class="sp">для флоатеров</span></h2><div style="display:grid;gap:14px">
    <div class="row"><label class="field" style="max-width:420px"><span>Источник прогноза</span><select class="in" id="krmode">${[['cbr','Прогноз Банка России (по умолчанию)'],['survey','Опрос аналитиков Банка России'],['market','Рынок: форварды КБД'],['flat','Без изменений (текущая ставка)']].map(([k,t])=>`<option value="${k}" ${(c.keyrate_mode||'cbr')===k?'selected':''}>${t}</option>`).join('')}</select></label>
      <button class="btn ghost" id="krsave" style="align-self:flex-end">Сохранить</button></div>
    <p class="note" id="krinfo">Загружаю…</p>
    <p class="note">Ставка ещё не объявленных купонов флоатера = ключевая ставка на начало купонного периода + спред эмитента (по последним известным купонам). «Прогноз Банка России» — среднесрочный прогноз ЦБ (середина диапазона средней ставки за год), «Опрос» — медиана макроопроса аналитиков, «КБД» — форвардные ставки кривой за вычетом срочной премии (грубо), «Без изменений» — текущая ставка. Если выбранный источник недоступен, берётся следующий по списку.</p></div></div>`;
  const adv=`<details class="set-adv" id="adv-d" ${S.setAdvOpen?'open':''}><summary>Для опытных<span>сервер данных, адреса API, сертификат — обычно трогать не нужно</span></summary><div style="display:grid;gap:16px;margin-top:14px">
    ${setDsHtml(c)}
    <div class="card"><h2>Адреса и сертификаты</h2><div style="display:grid;gap:18px">
    <label class="field"><span>Адреса REST API (боевой), по одному в строке</span><textarea class="in" id="hp" rows="2">${esc(c.hosts_prod.join('\n'))}</textarea></label>
    <label class="field"><span>Адреса REST API (песочница)</span><textarea class="in" id="hs" rows="2">${esc(c.hosts_sandbox.join('\n'))}</textarea></label>
    <label class="field"><span>Дополнительный файл сертификата (обычно не нужен: сертификат Минцифры уже встроен в программу)</span><input class="in" id="ca" value="${esc(c.ca_file)}" placeholder="/path/to/cert.pem"></label>
    <label class="sw"><input type="checkbox" id="vs" ${c.verify_ssl?'checked':''}><i></i><div><b>Проверять SSL-сертификат</b><small>Отключайте только для отладки</small></div></label>
    <div class="row"><button class="btn ghost" id="save2">Сохранить</button></div></div></div></div></details>`;
  $('#view').innerHTML=`<div class="wrap fade" style="max-width:820px">
  ${!c.token_set?`<div class="card hero" style="display:block"><div class="val" style="font-size:24px">Добро пожаловать 👋</div><p class="t2" style="margin-top:8px;position:relative;z-index:1">Вставьте API-токен Т-Инвестиций, чтобы увидеть аналитику, или импортируйте отчёт другого брокера. Всё хранится только на этом компьютере.</p></div>`:''}
  <nav class="set-toc" id="set-toc" aria-label="Разделы настроек">${SET_TOC.map(([id,t])=>`<a href="#${id}" data-to="${id}">${esc(t)}</a>`).join('')}</nav>
  <div id="msg"></div>
  ${setSec('set-conn','Подключение к Т-Инвестициям','',conn)}
  ${setSec('set-acc','Аккаунт и доступ','вход по ключу и Telegram',setAccHtml()+setTgHtml(c))}
  ${setSec('set-look','Внешний вид и меню','',look)}
  ${setSec('set-calc','Данные и расчёты','',calc)}
  ${setSec('set-local','Данные на компьютере','хранение, копии, очистка',setLocalHtml(c)+setBackupHtml(c))}
  ${setSec('set-adv','','',adv)}
  ${setSec('set-news','Что нового и планы','',`<div class="card" id="whatsnew"><h2>Что нового<span class="sp">версия ${esc(c.version||'')}</span></h2>${changelogHtml()}</div>
  <div class="card"><h2>Роадмап<span class="sp">что планируется</span></h2>${roadmapHtml()}</div>`)}</div>`;
  const msg=(t,ok)=>{$('#msg').innerHTML=`<div class="msg ${ok?'ok':'err'}">${esc(t)}</div>`;const m=$('#msg');if(m&&m.scrollIntoView)m.scrollIntoView({block:'nearest'})};
  $('#set-toc').onclick=e=>{const a=e.target.closest('[data-to]');if(!a)return;e.preventDefault();
    if(a.dataset.to==='set-adv'){const d=$('#adv-d');if(d){d.open=true;S.setAdvOpen=true}}
    const t=document.getElementById(a.dataset.to);if(t)t.scrollIntoView({behavior:'smooth',block:'start'})};
  $('#adv-d').addEventListener('toggle',e=>{S.setAdvOpen=e.currentTarget.open});
  $('#thsel').onclick=e=>{const b=e.target.closest('[data-t]');if(!b)return;applyTheme(b.dataset.t);post('/api/config',{theme:b.dataset.t}).catch(()=>{});$('#thsel').querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b))};
  const krShow=async()=>{try{const k=await api('/api/keyrate');$('#krinfo').innerHTML=k.source==='none'?'Прогноз сейчас недоступен: купоны флоатеров считаются по последней известной ставке.':`Сейчас используется: <b>${esc(k.name)}</b>${k.as_of?`, на ${esc(k.as_of)}`:''}${k.mode!==k.source?` (выбранный источник «${esc(k.mode)}» недоступен)`:''}. Ключевая ставка сейчас ${pctp(k.key_rate,2)}; средняя по годам: ${(k.yearly||[]).slice(0,4).map(y=>y.year+' — '+pctp(y.mid,1)).join(', ')}.`}catch(e){$('#krinfo').textContent='Не удалось получить прогноз: '+e.message}};
  krShow();
  $('#krsave').onclick=async()=>{try{$('#krinfo').textContent='Загружаю…';await post('/api/config',{keyrate_mode:$('#krmode').value});S.cfg.keyrate_mode=$('#krmode').value;S.bonds=null;msg('Сохранено. Доходности облигаций пересчитаются при следующем открытии раздела.',1);krShow()}catch(e){msg(e.message)}};
  $('#ndsave').onclick=async()=>{try{await post('/api/config',{notify_days:$('#nd').value});S.cfg.notify_days=+$('#nd').value;msg('Сохранено',1)}catch(e){msg(e.message)}};
  $('#ntf').onclick=async()=>{try{if(!('Notification' in window))return msg('Браузер не поддерживает уведомления');const r=await Notification.requestPermission();msg(r==='granted'?'Уведомления разрешены':'Уведомления не разрешены',r==='granted')}catch(e){msg(e.message)}};
  try{bindSetDs(c,msg)}catch(e){}
  try{bindSetTg(c,msg)}catch(e){}
  try{bindSetBackup(c,msg)}catch(e){}
  try{bindSetAcc(msg)}catch(e){}
  const body=()=>({token:$('#tok').value,sandbox:$('#sb').checked,verify_ssl:$('#vs').checked,ca_file:$('#ca').value,
    hosts_prod:$('#hp').value.split('\n'),hosts_sandbox:$('#hs').value.split('\n')});
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const reset=()=>{S.data=S.bonds=S.hist=null;S.account='all';persist()};
  try{bindSetLocal(c,msg,busy,reset)}catch(e){}
  $('#save').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());const r=await post('/api/test');reset();
    msg(`Подключено. Счетов: ${r.accounts}.`,1);S.page='dash';persist();renderNav();load(true)});
  $('#save2').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());reset();msg('Сохранено.',1);load(true)});
  $('#test').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());const r=await post('/api/test');msg(`Подключение работает. Счетов: ${r.accounts}.`,1)});
  $('#cache').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Заново загрузить все операции и цены из Т-Инвестиций? Это может занять время.'))return;await post('/api/cache/clear');reset();msg('Локальный кэш очищен, данные загрузятся заново.',1);load(true)});
  if($('#clr'))$('#clr').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Удалить сохранённый токен?'))return;await post('/api/config',{clear_token:true});reset();renderSettings()});
  if($('#sbopen'))$('#sbopen').onclick=e=>busy(e.currentTarget,async()=>{const r=await post('/api/sandbox/open');S.account=r.accountId;persist();S.data=null;msg('Открыт счёт '+r.accountId,1);load(true)});
  if($('#sbpay'))$('#sbpay').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/sandbox/payin',{accountId:S.account,amount:$('#amt').value});S.data=S.bonds=S.hist=null;msg('Счёт пополнен на '+M(+$('#amt').value,'rub',0),1);load(true)});
}
