/* ── Блокировка экрана, индикатор связи, глобальный перенос файлов и расширение кривой эмитента ── */

/* 1. Индикатор связи в нижней части сайдбара */
function connSet(state,detail){
  const el=document.getElementById('conn-st');
  if(!el)return;
  el.classList.remove('ok','busy','err');
  el.classList.add(state==='err'?'err':state==='busy'?'busy':'ok');
  const tx=el.querySelector('.conn-tx');
  if(tx)tx.textContent=state==='err'?'Нет связи':state==='busy'?'Обновляется…':'Подключено';
  el.title=detail||(state==='err'?'Нет связи с локальным сервером':state==='busy'?'Обновляются данные…':'Связь с локальным сервером установлена');
}

/* 2. Экран блокировки (Touch ID / Windows Hello / PIN) */
const LOCK_UI={open:false,busy:false};
function lockBioLabel(){
  return IS_MAC?'Войти по Touch ID':IS_WIN?'Войти через Windows Hello':'Войти по биометрии';
}
function lockHide(){
  LOCK_UI.open=false;
  const ov=document.getElementById('lock-ov');
  if(ov)ov.remove();
  document.body.classList.remove('lock-open');
}
function lockShow(info){
  info=info||{};
  if(typeof dropHide==='function')dropHide();
  let ov=document.getElementById('lock-ov');
  if(ov){
    const bio=document.getElementById('lock-bio');
    if(bio)bio.hidden=info.bio_enabled===false;
    return;
  }
  LOCK_UI.open=true;
  document.body.classList.add('lock-open');
  ov=document.createElement('div');
  ov.id='lock-ov';
  const showBio=info.bio_enabled!==false;
  ov.innerHTML=`<div class="lock-box" role="dialog" aria-modal="true" aria-label="Доступ заблокирован">
    <div class="logo"><i>${typeof LOGO_SVG==='function'?LOGO_SVG(30):''}</i>
      <div>TAnalytic<small>доступ защищён</small></div></div>
    <p class="lock-sub">Введите PIN-код или используйте биометрию, чтобы открыть портфель.</p>
    ${showBio?`<button type="button" class="btn lock-bio" id="lock-bio">${svgI('<path d="M12 11c1.1 0 2 .9 2 2v3c0 1.1-.9 2-2 2s-2-.9-2-2v-3c0-1.1.9-2 2-2z"/><path d="M8 10a4 4 0 0 1 8 0"/><path d="M5.5 11.5a6.5 6.5 0 0 1 13 0"/>',1.8)}<span>${esc(lockBioLabel())}</span></button>`:''}
    <form id="lock-form" autocomplete="off">
      <input class="in mono" id="lock-pin" type="password" inputmode="numeric" maxlength="12" placeholder="Введите PIN-код" autocomplete="current-password" autofocus aria-label="PIN-код">
      <div class="lock-err" id="lock-err" role="alert" hidden></div>
      <button type="submit" class="btn ghost lock-go" id="lock-pin-go">Разблокировать</button>
    </form>
  </div>`;
  document.body.appendChild(ov);
  const errEl=document.getElementById('lock-err'),pinEl=document.getElementById('lock-pin'),goBtn=document.getElementById('lock-pin-go'),bioBtn=document.getElementById('lock-bio');
  const showErr=t=>{if(!errEl)return;errEl.textContent=t||'';errEl.hidden=!t};
  const onUnlocked=()=>{
    lockHide();
    S.err=null;
    connSet('ok');
    if(!S.cfg&&typeof boot==='function'){boot();return}
    if(S.page==='set'&&typeof renderSettings==='function'){renderSettings();return}
    if(typeof load==='function')load(false);
  };
  const tryUnlock=async(body,btn)=>{
    if(LOCK_UI.busy)return;
    LOCK_UI.busy=true;if(btn)btn.disabled=true;showErr('');
    try{
      const r=await fetch('/api/lock/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      let j={};try{j=await r.json()}catch(e){}
      if(!r.ok||j.unlocked===false||j.ok===false)throw new Error(j.error||'Не удалось разблокировать');
      onUnlocked();
    }catch(e){showErr(e.message||'Не удалось разблокировать');if(pinEl&&body.method==='pin')pinEl.select()}
    finally{LOCK_UI.busy=false;if(btn)btn.disabled=false}
  };
  document.getElementById('lock-form').onsubmit=e=>{
    e.preventDefault();
    const pin=(pinEl.value||'').trim();
    if(!pin){showErr('Введите PIN-код.');pinEl.focus();return}
    tryUnlock({method:'pin',pin},goBtn);
  };
  if(bioBtn)bioBtn.onclick=()=>tryUnlock({method:'bio'},bioBtn);
  setTimeout(()=>{try{pinEl.focus()}catch(e){}},30);
}
async function lockCheckOnBoot(){
  try{
    const r=await fetch('/api/lock/status');
    if(!r.ok)return;
    const j=await r.json();
    if(j&&j.enabled&&!j.unlocked)lockShow(j);
  }catch(e){}
}
lockCheckOnBoot();

/* 3. Глобальный перенос файла отчёта (.xlsx / .xls / .csv / .html) в любое место окна */
let _dropDepth=0;
function dropHide(){
  _dropDepth=0;
  const ov=document.getElementById('drop-ov');
  if(ov)ov.remove();
}
function dropShow(){
  if(LOCK_UI.open)return;
  if(document.getElementById('drop-ov'))return;
  const ov=document.createElement('div');
  ov.id='drop-ov';
  ov.innerHTML=`<div class="drop-box">${svgI('<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>',1.8)}
    <b>Отпустите файл, чтобы импортировать отчёт брокера</b>
    <span>Поддерживаются .xlsx, .xls, .csv и .html</span></div>`;
  document.body.appendChild(ov);
}
function handleGlobalDropFile(file){
  if(!file)return;
  if(!/\.(xlsx|xlsm|xls|csv|txt|html|htm)$/i.test(file.name||'')){
    if(typeof toast==='function')toast('Поддерживаются отчёты в форматах .xlsx, .xls, .csv и .html','err',4500);
    return;
  }
  S._pendingDropFile=file;
  if(typeof window.impDropFile==='function'){window.impDropFile(file);return}
  if(S.page!=='imp')go('imp');
  let tries=0;
  const feed=()=>{
    if(S.page!=='imp'||!S._pendingDropFile)return;
    const inp=document.getElementById('ifile');
    if(inp){
      const f=S._pendingDropFile;S._pendingDropFile=null;
      try{
        const dt=new DataTransfer();dt.items.add(f);inp.files=dt.files;
        inp.dispatchEvent(new Event('change',{bubbles:true}));
      }catch(e){
        const dz=document.getElementById('drop');
        if(dz&&typeof dz.ondrop==='function')dz.ondrop({preventDefault(){},dataTransfer:{files:[f]}});
      }
      return;
    }
    if(++tries<60)setTimeout(feed,50);
  };
  setTimeout(feed,20);
}
(function(){
  const hasFiles=e=>{
    const dt=e&&e.dataTransfer;if(!dt||!dt.types)return false;
    for(let i=0;i<dt.types.length;i++)if(dt.types[i]==='Files')return true;
    return false;
  };
  window.addEventListener('dragenter',e=>{
    if(!hasFiles(e)||LOCK_UI.open)return;
    e.preventDefault();
    _dropDepth++;
    dropShow();
  });
  window.addEventListener('dragover',e=>{
    if(!hasFiles(e)||LOCK_UI.open)return;
    e.preventDefault();
    if(e.dataTransfer)e.dataTransfer.dropEffect='copy';
  });
  window.addEventListener('dragleave',e=>{
    if(!_dropDepth)return;
    _dropDepth=Math.max(0,_dropDepth-1);
    if(_dropDepth===0)dropHide();
  });
  window.addEventListener('dragend',dropHide);
  window.addEventListener('drop',e=>{
    const f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];
    if(!hasFiles(e)&&!f)return;
    e.preventDefault();
    dropHide();
    if(!LOCK_UI.open&&f)handleGlobalDropFile(f);
  });
})();

/* 4. Подключаем crosshair и всплывающую подсказку к кривой эмитента в карточке облигации */
if(typeof bcIssuerCurve==='function'&&typeof chartEnhanceIssuerCurve==='function'){
  const _origBcIc=bcIssuerCurve;
  bcIssuerCurve=function(el,ic){
    _origBcIc(el,ic);
    try{chartEnhanceIssuerCurve(el,ic)}catch(e){}
  };
}
