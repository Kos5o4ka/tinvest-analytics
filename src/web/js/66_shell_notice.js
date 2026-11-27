/* ── устаревшая оболочка приложения: новая иконка и экран запуска приходят только со скачанным .app/.exe ── */
/* Оболочка ревизии 4+ на Windows и macOS умеет обновить себя сама (мост pywebview): скачивает установщик (.exe) или образ (.dmg)
   с GitHub, сверяет сумму и предлагает «Обновить и перезапустить». У старых оболочек, а на macOS ещё и когда приложение
   нельзя заменить на месте (запущено из образа диска или временной копии), остаётся ссылка на скачивание. */
function shellBridge(){
  return new Promise(res=>{
    const ok=()=>{const a=window.pywebview&&pywebview.api;return a&&a.shell_update_prepare&&a.shell_update_run?a:null};
    if(ok())return res(ok());
    if(!window.pywebview)return res(null);                  /* обычный браузер: моста нет */
    const t=setTimeout(()=>res(ok()),3000);
    window.addEventListener('pywebviewready',()=>{clearTimeout(t);res(ok())},{once:true});
  });
}
function shellBar(html){
  let bar=document.getElementById('shell-bar');
  if(!bar){
    const top=document.querySelector('main .top');if(!top)return null;
    bar=document.createElement('div');bar.id='shell-bar';bar.className='noprint';
    top.insertAdjacentElement('afterend',bar);
  }
  bar.innerHTML=html;return bar;
}
function shellLater(bar){const b=bar.querySelector('#shell-later');if(b)b.onclick=()=>{try{sessionStorage.setItem('shell_later','1')}catch(e){}bar.remove()}}
function shellLinkBar(s){
  const win=/Setup/.test(s.asset||''),dmg=/\.dmg$/.test(s.asset||'');
  const href=safeUrl(s.asset?`https://github.com/Kos5o4ka/tinvest-analytics/releases/latest/download/${encodeURIComponent(s.asset)}`:s.url),su=safeUrl(s.url);
  const bar=shellBar(`<span><b>Доступна новая версия приложения.</b> ${win
    ?'Программа обновилась сама, а окно, значок в трее и установка с обновлениями придут с установщиком: скачайте и запустите его, данные и настройки сохранятся.'
    :dmg?'Программа обновилась сама, а новая иконка и экран запуска придут с новым образом: скачайте его, откройте и перетащите «TAnalytic» в «Программы» с заменой, данные и настройки сохранятся.'
    :'Программа обновилась сама, а новая иконка и экран запуска придут, когда вы скачаете приложение заново и замените старое.'}</span>
    <span class="sb-b">${href?`<a class="btn" href="${esc(href)}" target="_blank" rel="noopener noreferrer">Скачать</a>`:''}${su?`<a class="btn ghost" href="${esc(su)}" target="_blank" rel="noopener noreferrer">Что нового</a>`:''}<button class="btn ghost" id="shell-later">Позже</button></span>`);
  if(bar)shellLater(bar);
}
/* Оболочка Tauri — единственный канал обновлений: она сама проверяет latest.json при старте и раз в 6 часов и скачивает
   подписанное обновление в фоне. Здесь только баннер «готово — Перезапустить»; не нажали — обновление поставится при закрытии. */
function tauriUpdateNotice(){
  const br=window.TAURI_BRIDGE;if(!br||!br.updateStatus)return;
  let shown=false;
  const poll=async()=>{
    try{if(sessionStorage.getItem('shell_later'))return}catch(e){}
    let u;try{u=await br.updateStatus()}catch(e){u=null}
    if(!u||!u.version){setTimeout(poll,5*60*1000);return}      /* пока нет скачанного обновления — спросим позже */
    if(shown||document.getElementById('shell-bar'))return;
    const bar=shellBar(`<span><b>Готово обновление до версии ${esc(String(u.version))}.</b> Программа перезапустится; если не нажимать, оно установится при закрытии. Данные и настройки сохранятся.</span>
      <span class="sb-b"><button class="btn" id="shell-go">Перезапустить</button><button class="btn ghost" id="shell-later">Позже</button></span>`);
    if(!bar)return;
    shown=true;shellLater(bar);
    bar.querySelector('#shell-go').onclick=async e=>{
      const b=e.currentTarget;b.disabled=true;b.textContent='Обновляю…';
      try{await br.updateApply()}
      catch(err){b.disabled=false;b.textContent='Перезапустить';
        const sp=bar.querySelector('span');if(sp)sp.insertAdjacentHTML('beforeend',` <span class="neg">Не удалось обновить: ${esc(String(err&&err.message||err))}</span>`)}
    };
  };
  poll();
}
async function shellNotice(){
  let s;try{s=await api('/api/shell')}catch(e){return}
  if(s&&s.tauri){tauriUpdateNotice();return}      /* под Tauri старый канал обновления оболочки не используется */
  if(!s||!s.outdated)return;
  try{if(sessionStorage.getItem('shell_later'))return}catch(e){}
  if(document.getElementById('shell-bar'))return;
  const br=await shellBridge();
  if(!br)return shellLinkBar(s);
  /* установщик скачивает сама программа (не браузер): значит, и метки «из интернета» у файла нет */
  const bar=shellBar('<span><b>Доступна новая версия приложения.</b> Скачиваю обновление и проверяю контрольную сумму…</span>');
  if(!bar)return;
  let r;try{r=await br.shell_update_prepare()}catch(e){r={error:e&&e.message||String(e)}}
  if(!document.getElementById('shell-bar'))return;
  if(!r||!r.ok){shellLinkBar(s);return}
  const tag=String(r.tag||'').replace(/^v/i,'');
  bar.innerHTML=`<span><b>Готова новая версия${tag?' '+esc(tag):''}.</b> Обновление скачано и проверено. Программа закроется, обновится и откроется снова; данные и настройки сохранятся.</span>
    <span class="sb-b"><button class="btn" id="shell-go">Обновить и перезапустить</button><button class="btn ghost" id="shell-later">Позже</button></span>`;
  shellLater(bar);
  bar.querySelector('#shell-go').onclick=async e=>{
    e.currentTarget.disabled=true;e.currentTarget.textContent='Перезапускаю…';
    let x;try{x=await br.shell_update_run()}catch(err){x=null}
    if(x&&x.error){shellLinkBar(s)}
    else setTimeout(()=>{if(document.getElementById('shell-go'))shellLinkBar(s)},20000);   /* программа не закрылась — установщик не запустился */
  };
}
setTimeout(shellNotice,1500);
