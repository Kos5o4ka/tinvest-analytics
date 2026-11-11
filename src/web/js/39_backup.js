/* ── Зашифрованная резервная копия и экспорт ── */
/* постоянная плашка: копия принята, но применится только при следующем запуске */
function restoreBar(on){
  let b=document.getElementById('restore-bar');
  if(!on){if(b)b.remove();return}
  if(b)return;
  b=document.createElement('div');b.id='restore-bar';b.className='msg err';b.setAttribute('role','alert');
  b.innerHTML='<b>Копия будет применена при следующем запуске программы — перезапустите её.</b> До перезапуска на экране показаны прежние данные.';
  const v=document.getElementById('view');v.parentNode.insertBefore(b,v);
}
setTimeout(()=>{api('/api/backup/status').then(s=>restoreBar(!!(s&&s.restore_pending))).catch(()=>{})},2500);
function setBackupHtml(c){
  const ex=(w,t)=>`<div class="bk-ex"><span>${t}</span><a class="btn ghost" href="/api/export?what=${w}&fmt=csv&account=${encodeURIComponent(S.account||'all')}" download>CSV</a><a class="btn ghost" href="/api/export?what=${w}&fmt=xlsx&account=${encodeURIComponent(S.account||'all')}" download>Excel</a></div>`;
  return`<div class="card" id="bkcard"><h2>Резервная копия<span class="sp">зашифрована паролем</span></h2><div style="display:grid;gap:14px">
    <div class="bk-warn">Без пароля копию открыть нельзя, а пароль восстановить невозможно. Запишите его и храните отдельно от копии. Токен API и пароль в копию не входят.</div>
    <label class="field"><span>Папка для копий (облачный диск или любая папка)</span><input class="in" id="bkdir" placeholder="/Users/имя/Library/CloudStorage/… или C:\\Users\\имя\\Yandex.Disk" spellcheck="false"></label>
    <div id="bksug" class="bk-sug"></div>
    <div class="row"><label class="field" style="flex:1;min-width:200px"><span>Пароль копии <span id="bkpwst"></span></span><input class="in" type="password" id="bkpw" autocomplete="new-password" placeholder="не короче 6 символов"></label>
      <label class="field" style="width:150px"><span>Хранить копий</span><input class="in num" type="number" id="bkkeep" min="1" max="365" value="14"></label></div>
    <label class="sw"><input type="checkbox" id="bkauto"><i></i><div><b>Автоматически раз в день</b><small>Работает, пока программа запущена, и только если пароль сохранён. Старые копии сверх лимита удаляются.</small></div></label>
    <div class="row"><button class="btn" id="bksave">Сохранить настройки</button><button class="btn ghost" id="bkrun">Сделать копию сейчас</button>
      <button class="btn ghost danger" id="bkclr" style="display:none">Забыть сохранённый пароль</button></div>
    <p class="note" id="bkinfo">Загружаю…</p><div id="bkfiles"></div>
    <h3 style="margin:6px 0 0;font-size:14px">Восстановление</h3>
    <div class="row"><input type="file" id="bkfile" accept=".tinvbak" class="in" style="flex:1;min-width:200px"><input class="in" type="password" id="bkrpw" placeholder="пароль этой копии" autocomplete="off" style="width:200px"><button class="btn ghost" id="bkrest">Восстановить</button></div>
    <p class="note">Копия будет применена при следующем запуске программы — перезапустите её (до этого на экране прежние данные). Текущая база сохранится рядом как data.db.before-restore. Токен не меняется.</p></div></div>
  <div class="card"><h2>Экспорт данных<span class="sp">для Excel</span></h2><div style="display:grid;gap:8px">
    ${ex('positions','Позиции')}${ex('bonds','Облигации')}${ex('payments','Выплаты на год вперёд')}${ex('ops','Операции')}${ex('screener','Скринер облигаций')}
    <p class="note">CSV — в UTF-8 с разделителем «;» (открывается в Excel без настройки), Excel — файл .xlsx с числами и датами. Данные берутся по выбранному слева счёту.</p></div></div>`}
function bindSetBackup(c,msg){
  if(!$('#bkcard'))return;
  const kb=n=>n>=1048576?(n/1048576).toFixed(1)+' МБ':Math.max(1,Math.round(n/1024))+' КБ';
  const dt=t=>new Date(t*1000).toLocaleString('ru-RU');
  let timer=null,first=true;
  const show=async()=>{
    let s;try{s=await api('/api/backup/status')}catch(e){return}
    if(first){first=false;$('#bkdir').value=s.dir||'';$('#bkkeep').value=s.keep;$('#bkauto').checked=s.auto;
      $('#bksug').innerHTML=s.suggest.length?'Найдены папки: '+s.suggest.map(x=>`<button class="btn ghost bk-chip" data-p="${esc(x.path)}">${esc(x.label)}</button>`).join(' '):
      `Подсказки: Яндекс Диск — ${s.windows?'C:\\Users\\имя\\Yandex.Disk':'~/Yandex.Disk'}; iCloud Drive — ${s.windows?'C:\\Users\\имя\\iCloudDrive':'~/Library/Mobile Documents/com~apple~CloudDocs'}; Google Drive — ${s.windows?'G:\\Мой диск':'~/Library/CloudStorage/GoogleDrive-…'}`;
      $('#bksug').onclick=e=>{const b=e.target.closest('[data-p]');if(b)$('#bkdir').value=b.dataset.p+(b.dataset.p.endsWith('/')?'':'/')+'TInvestBackup'}}
    $('#bkpwst').innerHTML=s.pw_set?'<span class="pos">· сохранён</span>':'<span class="mu">· не сохранён</span>';
    $('#bkclr').style.display=s.pw_set?'':'none';
    restoreBar(!!s.restore_pending);
    const l=s.last;
    $('#bkinfo').innerHTML=s.running?'Делаю копию (шифрование занимает до минуты)…':l?(l.ok?`Последняя копия: ${esc(dt(l.t))}, ${esc(l.file)}, ${kb(l.size)}, ${l.sec} с${l.removed?`; удалено старых: ${l.removed}`:''}.`:`<span class="neg">Последняя попытка (${esc(dt(l.t))}) не удалась: ${esc(l.error)}</span>`):'Копий ещё не делали.';
    $('#bkfiles').innerHTML=s.dir_ok&&s.files.length?`<div class="note">В папке (${s.files.length}): ${s.files.slice(0,5).map(f=>esc(f.name)+' · '+kb(f.size)).join('; ')}${s.files.length>5?'…':''}</div>`:(s.dir&&!s.dir_ok?`<div class="note neg">${esc(s.dir_msg)}</div>`:'');
    clearTimeout(timer);if(s.running)timer=setTimeout(show,2500);
    return s;
  };
  show();
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const save=async()=>{await post('/api/backup/settings',{backup_dir:$('#bkdir').value,backup_auto:$('#bkauto').checked,backup_keep:$('#bkkeep').value,backup_password:$('#bkpw').value});$('#bkpw').value=''};
  $('#bksave').onclick=e=>busy(e.currentTarget,async()=>{await save();msg('Настройки резервной копии сохранены.',1);show()});
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
