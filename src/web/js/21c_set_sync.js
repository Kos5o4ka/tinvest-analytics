/* ── Настройки: синхронизация между устройствами (выключена по умолчанию, данные шифруются на этом компьютере) ── */
function setSyncHtml(c){
  const enabled=!!c.sync_enabled;
  const what='<b>Что уходит на сервер:</b> счета из отчётов брокеров и ручные счета с их операциями (даты, бумаги, количество, суммы), '+
    'снимки счетов Т-Инвестиций (только операции, без токена), список наблюдения, дневник (вместе с текстом заметок), цели ребалансировки, тарифы брокеров и налоговые настройки. '+
    '<b>Что не уходит никогда:</b> токен Т-Инвестиций, пароль резервной копии, кодовая фраза и рыночный кэш. Ключ из Telegram-бота нужен серверу только для доступа к вашей копии и не позволяет расшифровать данные. Сервер при этом видит размер блока, время обновления и имя устройства.';
  const how='Всё это сжимается и шифруется <b>на вашем компьютере</b> ключом из кодовой фразы (AES-256). На сервере лежит только шифрованный блок: ни администратор сервера, ни бот прочитать его не могут. '+
    'Поэтому бот не показывает ваш портфель. <b>Потеряете кодовую фразу — расшифровать копию не сможет никто</b>: её придётся удалить и создать заново. '+
    'Одно исключение: сделки, которые вы отправили боту командами <code>/buy</code> и <code>/sell</code>, лежат на сервере открытым текстом, пока программа не заберёт их при ближайшей синхронизации.';
  const off=`<div class="st-callout">Синхронизация <b>выключена</b>. Пока вы её не включите, портфель остаётся только на этом компьютере. Если включить, данные ниже будут храниться на сервере в зашифрованном виде.</div>
    <p class="st-line">${what}</p><p class="st-line">${how}</p>
    <div id="sy-need" class="st-line" hidden>Сначала войдите по ключу из Telegram-бота: синхронизация привязана к вашему аккаунту Telegram.</div>
    <div id="sy-found" class="st-callout" hidden></div>
    <div id="sy-create-wrap">${stRow('Первое устройство','Создать облачную копию. Кодовую фразу можно придумать самому (от 12 знаков) или оставить поле пустым: тогда программа создаст случайную',`<input class="in st-wide" id="sy-new" placeholder="своя кодовая фраза (по желанию)" autocomplete="off" spellcheck="false" aria-label="Своя кодовая фраза"><button class="btn" id="sy-create">Включить и создать копию</button>`,{stack:1})}</div>
    <div id="sy-join-wrap">${stRow('Второе устройство','Подключиться к копии, созданной на другом компьютере: нужна её кодовая фраза',`<input class="in st-wide" id="sy-join-ph" placeholder="кодовая фраза с первого устройства" autocomplete="off" spellcheck="false" aria-label="Кодовая фраза"><button class="btn ghost" id="sy-join">Подключить это устройство</button>`,{stack:1})}</div>`;
  const on=`<div class="st-callout"><b>Синхронизация включена.</b> Данные шифруются на этом компьютере; сервер хранит только шифртекст.</div>
    <p class="st-line" id="sy-st">Загружаю…</p>
    ${stRow('Действия','Обмен происходит сам: через несколько секунд после изменений и раз в 10 минут, пока программа открыта',`<button class="btn" id="sy-now">Синхронизировать сейчас</button><button class="btn ghost" id="sy-off">Выключить на этом компьютере</button>`)}
    ${stRow('Данные на сервере','Стирает облачную копию и очередь сделок из бота, выключает синхронизацию. Данные на этом компьютере остаются',`<button class="btn ghost danger" id="sy-del">Удалить мои данные с сервера</button>`)}
    <p class="st-line">${what}</p><p class="st-line">${how}</p>`;
  return stGroup('Синхронизация между устройствами',`<div id="sy-body">${enabled?on:off}</div><div id="sy-phrase"></div>`,{id:'sy-card',hint:'по желанию, выключена'});
}
function bindSetSync(c,msg){
  const g=id=>document.getElementById(id);if(!g('sy-card'))return;
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const redraw=async()=>{try{S.cfg=await api('/api/config');if(typeof renderSettings==='function')renderSettings()}catch(e){}};
  const showSt=async()=>{
    const el=g('sy-st');if(!el)return;
    try{
      const s=await api('/api/sync');
      el.textContent=(s.error?'Ошибка: '+s.error+' ':'')+(s.warning?'Внимание: '+s.warning+' ':'')+(s.at?`Последняя синхронизация: ${authTime(s.at)}, версия ${s.rev}, устройство «${s.device}», записей: ${s.records}.`:'Ещё не синхронизировано.');
      el.classList.toggle('st-err',!!(s.error||s.warning));
    }catch(e){el.textContent=e.message||''}
  };
  const need=g('sy-need');
  if(need)api('/api/sync?force=1').then(s=>{
    need.hidden=!!s.logged_in;
    if(s.logged_in&&s.server&&s.server.exists){
      const cw=g('sy-create-wrap'),fd=g('sy-found'),jb=g('sy-join'),jw=g('sy-join-wrap');
      if(cw)cw.hidden=true;
      if(fd){
        fd.hidden=false;
        const dev=s.server.device?`, устройство «${esc(s.server.device)}»`:'';
        fd.innerHTML=`<b>На сервере уже есть ваша облачная копия</b> (версия ${s.server.rev||1}${dev}). Подключите это устройство к вашей копии, введя кодовую фразу.`;
      }
      if(jb){jb.className='btn';jb.textContent='Подключить к вашей копии'}
      if(jw){const t=jw.querySelector('.st-k');if(t)t.textContent='Подключить к вашей копии'}
    }
  }).catch(()=>{});
  if(g('sy-create'))g('sy-create').onclick=e=>busy(e.currentTarget,async()=>{
    if(!await uiConfirm({title:'Включить синхронизацию?', body:'На сервер будет отправлен зашифрованный на этом компьютере блок: счета и операции, наблюдение, дневник, цели, тарифы и налоговые настройки. Токен Т-Инвестиций не отправляется. Без кодовой фразы расшифровать блок нельзя.', okText:'Включить'}))return;
    const r=await post('/api/sync',{action:'enable',mode:'create',phrase:g('sy-new').value});
    if(r.phrase){
      g('sy-phrase').innerHTML=`<div class="st-callout warn"><b>Запишите кодовую фразу сейчас.</b> Она показывается один раз и нигде не сохраняется; без неё второе устройство не подключить, а копию не восстановить.<div style="margin:8px 0"><code id="sy-ph-val" style="font-size:16px;user-select:all">${esc(r.phrase)}</code></div><button class="btn ghost" id="sy-ph-copy">Скопировать</button> <button class="btn" id="sy-ph-ok">Я записал(а) фразу</button></div>`;
      g('sy-ph-copy').onclick=async()=>{try{await navigator.clipboard.writeText(r.phrase);msg('Фраза скопирована.',1)}catch(x){msg('Выделите фразу и скопируйте вручную.')}};
      g('sy-ph-ok').onclick=()=>redraw();
      g('sy-body').hidden=true;
    }else{msg('Синхронизация включена.',1);redraw()}
  });
  if(g('sy-join'))g('sy-join').onclick=e=>busy(e.currentTarget,async()=>{
    const ph=g('sy-join-ph').value;if(!ph.trim())return msg('Введите кодовую фразу.');
    await post('/api/sync',{action:'enable',mode:'join',phrase:ph});msg('Устройство подключено, данные загружены.',1);
    try{S.data=S.bonds=S.hist=null}catch(x){}redraw();
  });
  if(g('sy-now'))g('sy-now').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/sync',{action:'now'});msg('Синхронизировано.',1);showSt();try{S.data=S.bonds=S.hist=null}catch(x){}});
  if(g('sy-off'))g('sy-off').onclick=e=>busy(e.currentTarget,async()=>{
    if(!await uiConfirm({title:'Выключить синхронизацию?', body:'Данные на этом компьютере и копия на сервере останутся; чтобы вернуться, понадобится кодовая фраза.', okText:'Выключить'}))return;
    await post('/api/sync',{action:'disable'});msg('Синхронизация выключена.',1);redraw()});
  if(g('sy-del'))g('sy-del').onclick=e=>busy(e.currentTarget,async()=>{
    if(!await uiConfirm({title:'Удалить облачную копию с сервера?', body:'Будут стёрты зашифрованный блок и очередь сделок из бота; синхронизация выключится. Данные на этом компьютере останутся. На других устройствах синхронизация остановится сама. Это нельзя отменить.', danger:true, okText:'Удалить с сервера'}))return;
    await post('/api/sync',{action:'delete'});msg('Данные удалены с сервера.',1);redraw()});
  showSt();
}
