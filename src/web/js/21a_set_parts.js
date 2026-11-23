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
    stRow('Проверка','Отправить пробное сообщение или сразу проверить тревоги',`<button class="btn ghost" id="tg-test">Тестовое сообщение</button><button class="btn ghost" id="tg-run" title="Проверить тревоги и отправить новые прямо сейчас">Проверить сейчас</button>`)+
    `<p class="st-line" id="tg-state"></p>`+
    stMore('Что нужно знать','Уведомления приходят от <b id="tg-bot">@tanalyticbot</b> — того же бота, который выдаёт ключ входа. Текст уведомлений (названия бумаг и суммы) проходит через сервер данных и бот и удаляется сразу после отправки; токен Т-Инвестиций никуда не передаётся. Уведомления приходят, <b>только пока программа запущена</b>; проверка выполняется раз в 10–15 минут, одна и та же тревога повторно не отправляется. Нужен вход по ключу из бота.'),
    {id:'tg-card',hint:'по желанию',cls:en?'':'st-dis'});
}
function bindSetTg(c,msg){
  const g=id=>document.getElementById(id);if(!g('tg-card'))return;
  const body=()=>({tg_enabled:g('tg-en').checked,tg_on_mon:g('tg-mon').checked,tg_on_watch:g('tg-wat').checked,
    tg_pay_days:g('tg-pay').value||0,tg_digest:g('tg-dg').checked,tg_digest_time:g('tg-time').value||'10:00'});
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const save=async()=>{const r=await post('/api/tg/save',body());Object.assign(c,r.settings);return r};
  const dim=()=>g('tg-card').classList.toggle('st-dis',!g('tg-en').checked);
  ['tg-en','tg-mon','tg-wat','tg-pay','tg-time','tg-dg'].forEach(id=>g(id).addEventListener('change',async e=>{
    const el=e.currentTarget;dim();
    try{await save();stOk(el)}catch(x){msg(x.message)}}));
  api('/api/tg/info').then(i=>{
    g('tg-bot').textContent='@'+String(i.bot||'tanalyticbot').replace(/^@/,'');
    g('tg-state').textContent=!i.server?'Сервер данных выключен («off»): уведомления работают через него. Включите сервер данных в разделе «Подключение».':
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
    stRow('Папка для копий','Облачный диск или любая папка',`<input class="in st-wide" id="bkdir" placeholder="/Users/имя/Library/CloudStorage/…" spellcheck="false" aria-label="Папка для копий">`,{stack:1})+
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
      $('#bksug').onclick=e=>{const b=e.target.closest('[data-p]');if(b){$('#bkdir').value=b.dataset.p+(b.dataset.p.endsWith('/')?'':'/')+'TInvestBackup';dirty.upd()}}}
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
  $('#bkclr').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Забыть пароль? Автоматические копии отключатся. Сами копии останутся и откроются прежним паролем.'))return;await post('/api/backup/settings',{clear_password:true});$('#bkauto').checked=false;msg('Пароль удалён из настроек.',1);show()});
  $('#bkrun').onclick=e=>busy(e.currentTarget,async()=>{
    const pw=$('#bkpw').value;await post('/api/backup/settings',{backup_dir:$('#bkdir').value,backup_keep:$('#bkkeep').value});
    await post('/api/backup/run',{password:pw});msg('Копия запущена, статус обновится ниже.',1);setTimeout(show,800)});
  $('#bkrest').onclick=e=>busy(e.currentTarget,async()=>{
    const f=$('#bkfile').files[0];if(!f)return msg('Выберите файл копии (.tinvbak).');
    if(!confirm('Восстановить данные из этой копии? Текущая база будет сохранена рядом, замена произойдёт при следующем запуске.'))return;
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
  on.onchange=async()=>{try{await post('/api/crowd/settings',{enabled:on.checked});stOk(on);msg(on.checked?'Спасибо! Программа будет скачивать страницы, пока она открыта.':'Помощь выключена.',1);show()}catch(e){msg(e.message);on.checked=!on.checked}};
  show();
}
