/* ── Настройки: Telegram, резервная копия, экспорт, помощь с раскрытиями (строки-настройки, мгновенное сохранение) ── */
/* ── Telegram: уведомления идут через сервер данных и общего бота ── */
function setTgHtml(c){
  if(!isPro())return stGroup('Уведомления в Telegram',`<div class="st-pad">${proTeaser('Уведомления в Telegram — в Pro: тревоги, выплаты и сводка прямо в мессенджере')}</div>`,{id:'tg-lock',hint:'Pro'});
  const on=(k,d)=>c[k]==null?d:!!c[k];
  const en=on('tg_enabled',false);
  return stGroup('Уведомления в Telegram',
    stRow('Присылать уведомления','Главный выключатель. Отключить можно и в боте командой <code>/notify_off</code>',stSw('tg-en',en,'Присылать уведомления в Telegram'))+
    stRow('Тревоги мониторинга','Только высокой важности: дефолт, понижение рейтинга, сильное падение цены',stSw('tg-mon',on('tg_on_mon',true),'Тревоги мониторинга'),{cls:'sub'})+
    stRow('Наблюдение и цели','Тревоги по списку наблюдения, достигнутые цели, напоминания из дневника',stSw('tg-wat',on('tg_on_watch',true),'Наблюдение и цели'),{cls:'sub'})+
    stRow('Ближайшие выплаты','За сколько дней сообщать о выплатах (0 — выключить)',`<input class="in num st-num" id="tg-pay" type="number" min="0" max="60" value="${+c.tg_pay_days||0}" aria-label="За сколько дней сообщать о выплатах"><span class="st-unit">дн.</span>`,{cls:'sub'})+
    stRow('Ежедневная сводка','Портфель, выплаты на неделю, тревоги',`<input class="in num st-time" id="tg-time" type="time" value="${esc(c.tg_digest_time||'10:00')}" aria-label="Время сводки">${stSw('tg-dg',on('tg_digest',false),'Ежедневная сводка')}`,{cls:'sub'})+
    stRow('Недельная сводка','По понедельникам утром от бота: итоги недели по целям и ближайшим событиям. Работает при включённой проверке на сервере',stSw('tg-wd',on('tg_weekly_digest',false),'Недельная сводка'),{cls:'sub'})+
    stRow('Проверять на сервере, когда программа закрыта','Цели по наблюдению, напоминания дневника, оферты и выплаты по портфелю проверяет сервер данных — раз в 15 минут, кроме ночи (22:00–08:00 МСК)',stSw('tg-srv',on('tg_server',false),'Проверять тревоги на сервере, когда программа закрыта'),{cls:'sub'})+
    `<p class="st-line" id="tg-srv-state"></p>`+
    stRow('Данные на сервере','Подписка удаляется и сама — когда истекает ключ из бота',`<button class="btn ghost danger" id="tg-srv-del">Удалить данные с сервера</button>`,{cls:'sub',id:'tg-srv-row',hidden:!on('tg_server',false)})+
    stRow('Проверка','Отправить пробное сообщение или сразу проверить тревоги',`<button class="btn ghost" id="tg-test">Тестовое сообщение</button><button class="btn ghost" id="tg-run" title="Проверить тревоги и отправить новые прямо сейчас">Проверить сейчас</button>`)+
    `<p class="st-line" id="tg-state"></p>`+
    stMore('Что нужно знать','Уведомления приходят от <b id="tg-bot">@tanalyticbot</b> — того же бота, который выдаёт ключ входа. Текст уведомлений (названия бумаг и суммы) проходит через сервер данных и бот и удаляется сразу после отправки; токен Т-Инвестиций никуда не передаётся. Пока программа запущена, она проверяет тревоги раз в 10–15 минут; одна и та же тревога повторно не отправляется. Нужен вход по ключу из бота.'+
      '<br><br><b>Проверка на сервере</b> (выключена, пока вы её не включите) нужна, чтобы уведомления приходили и при закрытой программе. На сервер данных уходит только «подписка»: ISIN и названия бумаг из списка наблюдения с вашими целями по доходности/цене; ISIN, название и даты напоминаний дневника (<b>без текста заметок</b>); ISIN, название и даты ближайших оферт облигаций портфеля; даты, названия и суммы ближайших выплат (если включены «Ближайшие выплаты»); ключи уже отправленных уведомлений, чтобы не было повторов. '+
      '<b>Токен Т-Инвестиций, номера счетов, стоимость портфеля и остатки денег не передаются.</b> Подписка обновляется при изменениях и при запуске программы; когда режим включён, эти уведомления отправляет только сервер, без дублей. '+
      'Данные удаляются кнопкой «Удалить данные с сервера», при выключении режима, кнопкой в боте (<code>/alerts</code>) и автоматически, когда истекает ключ из бота (7 дней). '+
      'Только при запущенной программе работают: тревоги мониторинга портфеля и наблюдения (падение цены, спред, рейтинг, дефолты, остановка торгов, ликвидность), крупные сделки и всплески объёма, ежедневная сводка.'),
    {id:'tg-card',hint:'по желанию',cls:en?'':'st-dis'});
}
function bindSetTg(c,msg){
  const g=id=>document.getElementById(id);if(!g('tg-card'))return;
  const body=()=>({tg_enabled:g('tg-en').checked,tg_on_mon:g('tg-mon').checked,tg_on_watch:g('tg-wat').checked,
    tg_pay_days:g('tg-pay').value||0,tg_digest:g('tg-dg').checked,tg_digest_time:g('tg-time').value||'10:00',tg_weekly_digest:g('tg-wd').checked,tg_server:g('tg-srv').checked});
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const save=async()=>{const r=await post('/api/tg/save',body());Object.assign(c,r.settings);return r};
  const dim=()=>g('tg-card').classList.toggle('st-dis',!g('tg-en').checked);
  const srvShow=()=>api('/api/tg/server').then(s=>{
    g('tg-srv-row').hidden=!(s.enabled||s.ok);const n=s.counts||{};
    g('tg-srv-state').textContent=!s.enabled?'':s.error?s.error:s.active?`Сервер проверяет: целей — ${n.goals||0}, напоминаний — ${n.reminders||0}, оферт — ${n.offers||0}, выплат — ${n.pays||0}. Обновлено ${new Date(s.ok*1000).toLocaleString('ru-RU')}.`:'Подписка ещё не отправлена на сервер.';
  }).catch(()=>{});
  ['tg-en','tg-mon','tg-wat','tg-pay','tg-time','tg-dg','tg-wd'].forEach(id=>g(id).addEventListener('change',async e=>{
    const el=e.currentTarget;dim();
    try{const r=await save();stOk(el);if(r.warning)msg(r.warning);setTimeout(srvShow,4500)}catch(x){msg(x.message)}}));
  g('tg-srv').addEventListener('change',async e=>{
    const el=e.currentTarget;
    if(el.checked&&!await uiConfirm({title:'Включить проверку на сервере?', body:'На сервер данных будут отправлены: ISIN и названия бумаг из списка наблюдения с целями, даты напоминаний дневника (без текста), даты ближайших оферт и выплат по облигациям портфеля (с суммами выплат). Токен, счета и стоимость портфеля не передаются.\n\nУдалить данные можно в любой момент кнопкой «Удалить данные с сервера» или в боте командой /alerts.', okText:'Включить'})){el.checked=false;return}
    try{const r=await save();
      if(el.checked){const s=await post('/api/tg/server',{action:'sync'});const n=s.counts||{};msg(`Сервер будет проверять: целей — ${n.goals||0}, напоминаний — ${n.reminders||0}, оферт — ${n.offers||0}, выплат — ${n.pays||0}.`,1)}
      else msg(r.warning||'Проверка на сервере выключена, данные удалены с сервера.',!r.warning);
    }catch(x){msg(x.message)}finally{srvShow()}});
  g('tg-srv-del').onclick=e=>busy(e.currentTarget,async()=>{
    if(!await uiConfirm({title:'Удалить подписку с сервера?', body:'Подписка на тревоги будет удалена с сервера, проверка на сервере выключится.', danger:true, okText:'Удалить'}))return;
    await post('/api/tg/server',{action:'delete'});g('tg-srv').checked=false;c.tg_server=false;msg('Данные удалены с сервера.',1);srvShow()});
  srvShow();
  api('/api/tg/info').then(i=>{
    g('tg-bot').textContent='@'+String(i.bot||'tanalyticbot').replace(/^@/,'');
    g('tg-state').textContent=!i.server?'Сервер данных недоступен: уведомления работают через него.':
      i.state==='need_login'?'Войдите по ключу из бота — иначе уведомления отправить нельзя.':i.state==='offline'?'Сервер недоступен.':'';
  }).catch(()=>{});
  g('tg-test').onclick=e=>busy(e.currentTarget,async()=>{await save();await post('/api/tg/test');msg('Тестовое сообщение отправлено — проверьте Telegram.',1)});
  g('tg-run').onclick=e=>busy(e.currentTarget,async()=>{await save();const r=await post('/api/tg/run');msg(r.sent?'Отправлено новых пунктов: '+r.sent+'.':'Новых тревог для отправки нет.',1)});
}

/* ── Зашифрованная резервная копия и экспорт ── */
function setBackupHtml(c){
  const q=encodeURIComponent(S.account||'all');
  const ex=(w,t)=>stRow(t,'',`<a class="btn ghost" href="/api/export?what=${w}&fmt=csv&account=${q}" download>CSV</a><a class="btn ghost" href="/api/export?what=${w}&fmt=xlsx&account=${q}" download>Excel</a>`);
  return stGroup('Резервная копия',
    `<div class="st-callout warn">Без пароля копию открыть нельзя, а пароль восстановить невозможно. Запишите его и храните отдельно от копии. Токен API и пароль в копию не входят.</div>`+
    stRow('Папка для копий','Облачный диск или любая папка',`<input class="in st-wide" id="bkdir" placeholder="${IS_WIN?'C:\\Users\\имя\\YandexDisk\\TInvestBackup':IS_MAC?'/Users/имя/Library/CloudStorage/…':'/home/имя/Yandex.Disk/TInvestBackup'}" spellcheck="false" aria-label="Папка для копий">`,{stack:1})+
    `<div id="bksug" class="bk-sug st-sug"></div>`+
    stRow('Пароль копии','<span id="bkpwst"></span>',stSecret('bkpw','не короче 6 символов','autocomplete="new-password"','Пароль копии'))+
    stRow('Хранить копий','Старые сверх лимита удаляются',`<input class="in num st-num" type="number" id="bkkeep" min="1" max="365" value="14" aria-label="Сколько копий хранить">`)+
    stRow('Автоматически раз в день','Работает, пока программа запущена и сохранён пароль',stSw('bkauto',false,'Автоматическая резервная копия раз в день'))+
    stRow('Действия','',`<button class="btn" id="bksave" disabled>Сохранить настройки</button><button class="btn ghost" id="bkrun">Сделать копию сейчас</button><button class="btn ghost danger" id="bkclr" style="display:none">Забыть пароль</button>`)+
    `<p class="st-line" id="bkinfo">Загружаю…</p><div id="bkfiles" class="st-line"></div>`+
    stMore('Восстановить из копии',`<div class="st-restore"><input type="file" id="bkfile" accept=".tinvbak" class="in" aria-label="Файл копии"><input class="in" type="password" id="bkrpw" placeholder="пароль этой копии" autocomplete="off" aria-label="Пароль копии для восстановления"><button class="btn ghost" id="bkrest">Восстановить</button></div><p>Копия будет применена при следующем запуске программы — перезапустите её (до этого на экране прежние данные). Текущая база сохранится рядом как data.db.before-restore. Токен не меняется.</p>`),
    {id:'bkcard',hint:'зашифрована паролем'})+
  stGroup('Экспорт данных',
    ex('positions','Позиции')+ex('bonds','Облигации')+ex('payments','Выплаты на год вперёд')+ex('ops','Операции')+ex('screener','Скринер облигаций')+
    stMore('О форматах','CSV — в UTF-8 с разделителем «;» (открывается в Excel без настройки), Excel — файл .xlsx с числами и датами. Данные берутся по выбранному слева счёту.'),
    {hint:'для Excel'});
}
function bindSetBackup(c,msg){
  if(!$('#bkcard'))return;
  const kb=n=>n>=1048576?(n/1048576).toFixed(1)+' МБ':Math.max(1,Math.round(n/1024))+' КБ';
  const dt=t=>new Date(t*1000).toLocaleString('ru-RU');
  let timer=null,first=true;
  const dirty=stDirty('bksave',['bkdir','bkpw','bkkeep']);
  const show=async()=>{
    let s;try{s=await api('/api/backup/status')}catch(e){return}
    if(first){first=false;$('#bkdir').value=s.dir||'';$('#bkkeep').value=s.keep;$('#bkauto').checked=s.auto;dirty.rebase();
      $('#bksug').innerHTML=s.suggest.length?'Найдены папки: '+s.suggest.map(x=>`<button class="btn ghost bk-chip" data-p="${esc(x.path)}">${esc(x.label)}</button>`).join(' '):
      `Подсказки: Яндекс Диск — ${s.windows?'C:\\Users\\имя\\Yandex.Disk':'~/Yandex.Disk'}; iCloud Drive — ${s.windows?'C:\\Users\\имя\\iCloudDrive':'~/Library/Mobile Documents/com~apple~CloudDocs'}; Google Drive — ${s.windows?'G:\\Мой диск':'~/Library/CloudStorage/GoogleDrive-…'}`;
      $('#bksug').onclick=e=>{const b=e.target.closest('[data-p]');if(b){const p=b.dataset.p,sp=s.windows||/^[A-Za-z]:\\/.test(p)?'\\':'/';$('#bkdir').value=p+(/[\\/]$/.test(p)?'':sp)+'TInvestBackup';dirty.upd()}}}
    $('#bkpwst').innerHTML=s.pw_set?'<span class="pos">Пароль сохранён</span>':'<span class="mu">Пароль не сохранён</span>';
    $('#bkclr').style.display=s.pw_set?'':'none';
    restoreBar(!!s.restore_pending);
    const l=s.last;
    $('#bkinfo').innerHTML=s.running?'Делаю копию (шифрование занимает до минуты)…':l?(l.ok?`Последняя копия: ${esc(dt(l.t))}, ${esc(l.file)}, ${kb(l.size)}, ${l.sec} с${l.removed?`; удалено старых: ${l.removed}`:''}.`:`<span class="neg">Последняя попытка (${esc(dt(l.t))}) не удалась: ${esc(l.error)}</span>`):'Копий ещё не делали.';
    $('#bkfiles').innerHTML=s.dir_ok&&s.files.length?`В папке (${s.files.length}): ${s.files.slice(0,5).map(f=>esc(f.name)+' · '+kb(f.size)).join('; ')}${s.files.length>5?'…':''}`:(s.dir&&!s.dir_ok?`<span class="neg">${esc(s.dir_msg)}</span>`:'');
    clearTimeout(timer);if(s.running)timer=setTimeout(show,2500);
    return s;
  };
  show();
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const save=async()=>{await post('/api/backup/settings',{backup_dir:$('#bkdir').value,backup_auto:$('#bkauto').checked,backup_keep:$('#bkkeep').value,backup_password:$('#bkpw').value});$('#bkpw').value=''};
  stEnter(['bkdir','bkpw','bkkeep'],'bksave');
  $('#bksave').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await save();dirty.rebase();stOk(b);show()}catch(x){msg(x.message);dirty.upd()}};
  $('#bkauto').onchange=async e=>{const el=e.currentTarget;try{await save();dirty.rebase();stOk(el);show()}catch(x){el.checked=!el.checked;msg(x.message)}};
  $('#bkclr').onclick=e=>busy(e.currentTarget,async()=>{if(!await uiConfirm({title:'Забыть пароль копий?', body:'Автоматические копии отключатся. Сами копии останутся и откроются прежним паролем.', danger:true, okText:'Забыть'}))return;await post('/api/backup/settings',{clear_password:true});$('#bkauto').checked=false;msg('Пароль удалён из настроек.',1);show()});
  $('#bkrun').onclick=e=>busy(e.currentTarget,async()=>{
    const pw=$('#bkpw').value;await post('/api/backup/settings',{backup_dir:$('#bkdir').value,backup_keep:$('#bkkeep').value});
    await post('/api/backup/run',{password:pw});msg('Копия запущена, статус обновится ниже.',1);setTimeout(show,800)});
  $('#bkrest').onclick=e=>busy(e.currentTarget,async()=>{
    const f=$('#bkfile').files[0];if(!f)return msg('Выберите файл копии (.tinvbak).');
    if(!await uiConfirm({title:'Восстановить данные из копии?', body:'Текущая база будет сохранена рядом, замена произойдёт при следующем запуске.', okText:'Восстановить'}))return;
    msg('Расшифровываю и проверяю копию…',1);
    const b64=await new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>no(new Error('Не удалось прочитать файл'));r.readAsDataURL(f)});
    await post('/api/backup/restore',{data:b64,password:$('#bkrpw').value});$('#bkrpw').value='';
    restoreBar(true);
    msg('Копия проверена и принята. Копия будет применена при следующем запуске программы — перезапустите её. До перезапуска на экране остаются прежние данные.',1)});
}

/* ── Помощь в сборе раскрытий эмитентов ── */
function setCrowdHtml(c){
  return stGroup('Помощь в сборе раскрытий',
    stRow('Помогать собирать раскрытия эмитентов','Работает только пока программа открыта и подключён сервер данных',stSw('crowd-on',false,'Помогать собирать раскрытия эмитентов'))+
    `<p class="st-line" id="crowd-info">Загружаю…</p>`+
    `<details class="st-more" id="crowd-log-det" data-q="журнал сбор раскрытия лог"><summary>Журнал сбора раскрытий</summary><div id="crowd-log-body"><span class="mu">Откройте, чтобы загрузить последние записи…</span></div></details>`+
    stMore('Как это работает','Включено по умолчанию. Сообщения эмитентов о купонах, выкупах и дефолтах лежат на сайте e-disclosure.azipi.ru, а наш сервер данных его открыть не может. <b>Пока программа открыта</b>, она скачивает публичные страницы этого сайта <b>с вашего интернет-подключения — примерно одну страницу раз в 15 секунд</b> — и отправляет их на сервер данных. Так все пользователи видят купоны, выкупы и дефолты по своим облигациям. Токен, портфель и другие ваши данные не отправляются; в страницах только то, что видно любому посетителю сайта. Сайт видит ваш IP-адрес, как при обычном заходе в браузере. При ошибках сайта программа делает паузу на 30 минут. Выключить можно в любой момент.'),
    {id:'crowd-card',hint:'',hintId:'crowd-sp'});
}
async function bindSetCrowd(c,msg){
  const on=document.getElementById('crowd-on');if(!on)return;
  const show=async()=>{const s=await crowdLoad();if(!s||!document.getElementById('crowd-info'))return;
    on.checked=!!s.enabled;
    const stt=s.enabled&&s.state==='off'?'запускается…':(CROWD_STATE[s.state]||s.state);   // включили, а поток ещё не проснулся
    document.getElementById('crowd-sp').textContent=s.enabled?stt:'выключено';
    document.getElementById('crowd-info').innerHTML=`Отправлено страниц, принятых сервером: <b>${s.accepted}</b>${s.fetched?` (скачано ${s.fetched})`:''}.${s.enabled?` Состояние: ${esc(stt)}${s.message?' — '+esc(s.message):''}.`:''}${!s.available?' Подключите сервер данных и войдите по ключу — без этого помощь не работает.':''}`;
    clearTimeout(CROWD.t);if(s.enabled)CROWD.t=setTimeout(show,5000)};
  const loadLog=async()=>{
    const body=document.getElementById('crowd-log-body');if(!body)return;
    body.innerHTML='<span class="mu">Загружаю журнал…</span>';
    try{
      const r=await api('/api/crowd/log');
      const rows=Array.isArray(r)?r:(r&&Array.isArray(r.items)?r.items:(r&&Array.isArray(r.log)?r.log:[]));
      if(!rows.length){body.innerHTML='<span class="mu">Записей пока нет.</span>';return}
      body.innerHTML=`<div class="crowd-log">${rows.slice(0,40).map(x=>{
        const ts=x.ts||x.at||x.time;const tm=typeof ts==='number'?new Date(ts*1000).toLocaleTimeString('ru-RU'):esc(String(ts||''));
        const ok=x.ok!==false&&x.status!=='err'&&x.status!=='error';
        const txt=x.message||x.msg||x.url||x.kind||x.status||'Принято';
        return`<div class="crowd-log-r"><span class="mono mu">${tm}</span><span class="${ok?'pos':'neg'}">${esc(String(x.status||(ok?'Готово':'Ошибка')))}</span><span>${esc(String(txt))}</span></div>`;
      }).join('')}</div>`;
    }catch(e){body.innerHTML=`<span class="neg">${esc(e.message)}</span>`}
  };
  const det=document.getElementById('crowd-log-det');
  if(det)det.addEventListener('toggle',()=>{if(det.open)loadLog()});
  on.onchange=async()=>{try{await post('/api/crowd/settings',{enabled:on.checked});stOk(on);msg(on.checked?'Спасибо! Программа будет скачивать страницы, пока она открыта.':'Помощь выключена.',1);show()}catch(e){msg(e.message);on.checked=!on.checked}};
  show();
}
/* ── Окно программы: трей и автозапуск (только установленная версия для Windows; на macOS карточки нет) ── */
async function bindSetShell(msg){
  let s;try{s=await api("/api/shell")}catch(e){return}
  const sec=document.getElementById("set-look");
  if(s&&s.tauri){                                   /* оболочка Tauri: только автозапуск, через её собственные команды */
    const br=window.TAURI_BRIDGE;
    if(!br||!sec||document.getElementById("shell-card"))return;
    let on;try{on=!!(await br.autostartGet())}catch(e){return}
    sec.insertAdjacentHTML("beforeend",stGroup("Окно программы",
      stRow("Запускать вместе с системой","После входа в систему программа запускается автоматически",stSw("tray-auto",on,"Запускать вместе с системой")),
      {id:"shell-card"}));
    const el=document.getElementById("tray-auto");
    if(el)el.onchange=async()=>{try{const r=await br.autostartSet(el.checked);stOk(el);el.checked=!!r;msg("Сохранено",1,true)}catch(e){msg(e&&e.message||String(e));el.checked=!el.checked}};
    return;
  }
  if(!s||!s.tray||!sec||document.getElementById("shell-card"))return;
  sec.insertAdjacentHTML("beforeend",stGroup("Окно программы",
    stRow("При закрытии окна сворачивать в трей","Программа продолжает работать в фоне: резервные копии, проверка тревог. Выйти можно из меню значка в трее",stSw("tray-close",!!s.tray_close,"При закрытии окна сворачивать в трей"))+
    stRow("Запускать вместе с Windows","После входа в систему программа открывается сразу в трее, без окна",stSw("tray-auto",!!s.autostart,"Запускать вместе с Windows")),
    {id:"shell-card",hint:"Windows"}));
  const bind=(id,key)=>{const el=document.getElementById(id);if(!el)return;
    el.onchange=async()=>{try{const r=await post("/api/shell/tray",{[key]:el.checked});stOk(el);
      el.checked=!!r[key];msg("Сохранено",1,true)}catch(e){msg(e.message);el.checked=!el.checked}}};
  bind("tray-close","tray_close");bind("tray-auto","autostart");
}
