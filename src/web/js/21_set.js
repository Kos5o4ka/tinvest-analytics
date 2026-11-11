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
async function renderSettings(){
  S.charts=[];
  try{S.cfg=await api('/api/config')}catch(e){$('#view').innerHTML=`<div class="wrap"><div class="msg err">${esc(e.message)}</div></div>`;return}
  const c=S.cfg;
  $('#view').innerHTML=`<div class="wrap fade" style="max-width:820px">
  ${!c.token_set?`<div class="card hero" style="display:block"><div class="val" style="font-size:24px">Добро пожаловать 👋</div><p class="t2" style="margin-top:8px;position:relative;z-index:1">Вставьте API-токен Т-Инвестиций, чтобы увидеть аналитику, или импортируйте отчёт другого брокера. Всё хранится только на этом компьютере.</p></div>`:''}
  <div id="msg"></div>
  <div class="card"><h2>Подключение к Т-Инвестициям</h2><div style="display:grid;gap:18px">
    <label class="field"><span>API-токен ${c.token_set?`<span class="pos">· сохранён (…${esc(c.token_hint.slice(1))}). Оставьте пустым, чтобы не менять</span>`:''}</span>
      <input class="in" type="password" id="tok" placeholder="t.XXXXXXXXXXXXXXXXXXXX" autocomplete="off" spellcheck="false"></label>
    <label class="sw"><input type="checkbox" id="sb" ${c.sandbox?'checked':''}><i></i><div><b>Режим песочницы</b><small>Токен песочницы работает только с этим режимом, боевой — только без него</small></div></label>
    <div class="row"><button class="btn" id="save">Сохранить и подключиться</button><button class="btn ghost" id="test">Проверить</button>
      ${c.token_set?'<button class="btn danger" id="clr">Удалить токен</button>':''}</div>
    <div class="note" style="line-height:1.6"><b>Как получить токен</b> (1 минута):<br>
      1. Откройте <a href="https://www.tbank.ru/invest/settings/api/" target="_blank" rel="noopener noreferrer">tbank.ru/invest/settings/api</a> и войдите в Т-Банк (или в приложении Т-Инвестиции: Профиль → Настройки → Токены T-Invest API).<br>
      2. Нажмите «Создать токен», выберите доступ <b>«Только для чтения»</b> и все счета (или только нужные).<br>
      3. Скопируйте токен сразу — второй раз его не покажут — и вставьте в поле выше.<br>
      Торговый токен не нужен: программа ничего не покупает и не продаёт. Отозвать токен можно на той же странице в любой момент.</div></div></div>
  ${c.sandbox&&c.token_set?`<div class="card"><h2>Песочница</h2><div style="display:grid;gap:14px"><div class="row"><button class="btn ghost" id="sbopen">Открыть новый счёт</button>
    <input class="in num" type="number" id="amt" value="1000000" min="1" step="1000" style="width:160px"><button class="btn ghost" id="sbpay">Пополнить выбранный счёт, ₽</button></div>
    <p class="note">Песочница — виртуальный счёт без реальных данных: сначала он пуст.</p></div></div>`:''}
  <div class="card"><h2>Локальные данные</h2><p class="note" style="margin-bottom:12px">Операции, история цен, справочник бумаг и логотипы хранятся в базе на этом компьютере: <span class="mono">${esc(c.data_dir)}</span>. При обновлении догружаются только новые данные.</p>
    <div class="row"><button class="btn ghost" id="cache">Перезагрузить всё из API</button><a class="btn ghost" href="/api/backup" download>Скачать резервную копию</a></div>
    <p class="note" style="margin-top:10px">Резервная копия — zip с базой и настройками. Токен в неё не входит.</p></div>
  <div class="card"><h2>Оформление и напоминания</h2><div style="display:grid;gap:16px">
    <div class="row"><div class="seg" id="thsel">${[['auto','Авто'],['light','Светлая'],['dark','Тёмная']].map(([k,t])=>`<button data-t="${k}" class="${curTheme()===k?'on':''}">${t}</button>`).join('')}</div></div>
    <div class="row"><label class="field" style="max-width:260px"><span>Напоминать о выплатах за, дней (0 — выключить)</span><input class="in num" id="nd" type="number" min="0" max="60" value="${c.notify_days??7}"></label>
      <button class="btn ghost" id="ndsave" style="align-self:flex-end">Сохранить</button><button class="btn ghost" id="ntf" style="align-self:flex-end">Разрешить системные уведомления</button></div>
    <p class="note">Напоминания показываются на «Обзоре» и «Выплатах», а системные уведомления приходят, пока программа открыта. Печать отчёта: кнопка PDF сверху → «Сохранить как PDF» (печатается текущий раздел и период).</p></div></div>
  ${setMenuHtml()}
  <div class="card"><h2>Прогноз ключевой ставки<span class="sp">для флоатеров</span></h2><div style="display:grid;gap:14px">
    <div class="row"><label class="field" style="max-width:420px"><span>Источник прогноза</span><select class="in" id="krmode">${[['cbr','Прогноз Банка России (по умолчанию)'],['survey','Опрос аналитиков Банка России'],['market','Рынок: форварды КБД'],['flat','Без изменений (текущая ставка)']].map(([k,t])=>`<option value="${k}" ${(c.keyrate_mode||'cbr')===k?'selected':''}>${t}</option>`).join('')}</select></label>
      <button class="btn ghost" id="krsave" style="align-self:flex-end">Сохранить</button></div>
    <p class="note" id="krinfo">Загружаю…</p>
    <p class="note">Ставка ещё не объявленных купонов флоатера = ключевая ставка на начало купонного периода + спред эмитента (по последним известным купонам). «Прогноз Банка России» — среднесрочный прогноз ЦБ (середина диапазона средней ставки за год), «Опрос» — медиана макроопроса аналитиков, «КБД» — форвардные ставки кривой за вычетом срочной премии (грубо), «Без изменений» — текущая ставка. Если выбранный источник недоступен, берётся следующий по списку.</p></div></div>
  ${setDsHtml(c)}
  ${setTgHtml(c)}${setBackupHtml(c)}
  <div class="card" id="whatsnew"><h2>Что нового<span class="sp">версия ${esc(c.version||'')}</span></h2>${changelogHtml()}</div>
  <div class="card"><h2>Роадмап<span class="sp">что планируется</span></h2>${roadmapHtml()}</div>
  <details class="card"><summary style="cursor:pointer;font-weight:600;color:var(--tx2)">Дополнительно</summary><div style="display:grid;gap:18px;margin-top:16px">
    <label class="field"><span>Адреса REST API (боевой), по одному в строке</span><textarea class="in" id="hp" rows="2">${esc(c.hosts_prod.join('\n'))}</textarea></label>
    <label class="field"><span>Адреса REST API (песочница)</span><textarea class="in" id="hs" rows="2">${esc(c.hosts_sandbox.join('\n'))}</textarea></label>
    <label class="field"><span>Дополнительный файл сертификата (обычно не нужен: сертификат Минцифры уже встроен в программу)</span><input class="in" id="ca" value="${esc(c.ca_file)}" placeholder="/path/to/cert.pem"></label>
    <label class="sw"><input type="checkbox" id="vs" ${c.verify_ssl?'checked':''}><i></i><div><b>Проверять SSL-сертификат</b><small>Отключайте только для отладки</small></div></label>
    <div class="row"><button class="btn ghost" id="save2">Сохранить</button></div></div></details></div>`;
  const msg=(t,ok)=>{$('#msg').innerHTML=`<div class="msg ${ok?'ok':'err'}">${esc(t)}</div>`};
  $('#thsel').onclick=e=>{const b=e.target.closest('[data-t]');if(!b)return;applyTheme(b.dataset.t);post('/api/config',{theme:b.dataset.t}).catch(()=>{});$('#thsel').querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b))};
  const krShow=async()=>{try{const k=await api('/api/keyrate');$('#krinfo').innerHTML=k.source==='none'?'Прогноз сейчас недоступен: купоны флоатеров считаются по последней известной ставке.':`Сейчас используется: <b>${esc(k.name)}</b>${k.as_of?`, на ${esc(k.as_of)}`:''}${k.mode!==k.source?` (выбранный источник «${esc(k.mode)}» недоступен)`:''}. Ключевая ставка сейчас ${pctp(k.key_rate,2)}; средняя по годам: ${(k.yearly||[]).slice(0,4).map(y=>y.year+' — '+pctp(y.mid,1)).join(', ')}.`}catch(e){$('#krinfo').textContent='Не удалось получить прогноз: '+e.message}};
  krShow();
  $('#krsave').onclick=async()=>{try{$('#krinfo').textContent='Загружаю…';await post('/api/config',{keyrate_mode:$('#krmode').value});S.cfg.keyrate_mode=$('#krmode').value;S.bonds=null;msg('Сохранено. Доходности облигаций пересчитаются при следующем открытии раздела.',1);krShow()}catch(e){msg(e.message)}};
  $('#ndsave').onclick=async()=>{try{await post('/api/config',{notify_days:$('#nd').value});S.cfg.notify_days=+$('#nd').value;msg('Сохранено',1)}catch(e){msg(e.message)}};
  $('#ntf').onclick=async()=>{try{if(!('Notification' in window))return msg('Браузер не поддерживает уведомления');const r=await Notification.requestPermission();msg(r==='granted'?'Уведомления разрешены':'Уведомления не разрешены',r==='granted')}catch(e){msg(e.message)}};
  try{bindSetDs(c,msg)}catch(e){}
  try{bindSetTg(c,msg)}catch(e){}
  try{bindSetBackup(c,msg)}catch(e){}
  const body=()=>({token:$('#tok').value,sandbox:$('#sb').checked,verify_ssl:$('#vs').checked,ca_file:$('#ca').value,
    hosts_prod:$('#hp').value.split('\n'),hosts_sandbox:$('#hs').value.split('\n')});
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const reset=()=>{S.data=S.bonds=S.hist=null;S.account='all';persist()};
  $('#save').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());const r=await post('/api/test');reset();
    msg(`Подключено. Счетов: ${r.accounts}.`,1);S.page='dash';persist();renderNav();load(true)});
  $('#save2').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());reset();msg('Сохранено.',1);load(true)});
  $('#test').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());const r=await post('/api/test');msg(`Подключение работает. Счетов: ${r.accounts}.`,1)});
  $('#cache').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/cache/clear');reset();msg('Локальный кэш очищен, данные загрузятся заново.',1);load(true)});
  if($('#clr'))$('#clr').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Удалить сохранённый токен?'))return;await post('/api/config',{clear_token:true});reset();renderSettings()});
  if($('#sbopen'))$('#sbopen').onclick=e=>busy(e.currentTarget,async()=>{const r=await post('/api/sandbox/open');S.account=r.accountId;persist();S.data=null;msg('Открыт счёт '+r.accountId,1);load(true)});
  if($('#sbpay'))$('#sbpay').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/sandbox/payin',{accountId:S.account,amount:$('#amt').value});S.data=S.bonds=S.hist=null;msg('Счёт пополнен на '+M(+$('#amt').value,'rub',0),1);load(true)});
}



