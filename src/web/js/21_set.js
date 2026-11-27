/* ── Настройки: двухпанельный экран (навигация слева, панель состояния, строки-настройки) ── */
/* ── кирпичики разметки ── */
const ST_ICO={
 conn:'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
 acc:'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
 look:'<circle cx="12" cy="12" r="9"/><path d="M12 3v18"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none" opacity=".35"/>',
 calc:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2M12 11h2M8 15h2M12 15h2M8 18h2M12 18h4"/>',
 local:'<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
 news:'<path d="M12 3l2.4 5.6 6.1.6-4.6 4 1.4 6-5.3-3.2L6.7 19.2l1.4-6-4.6-4 6.1-.6z"/>',
 danger:'<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
 eye:'<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
 eyeoff:'<path d="M3 3l18 18M10.6 5.1A9.7 9.7 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4M6.5 6.6A17 17 0 0 0 2 12s3.6 7 10 7a9.6 9.6 0 0 0 4-.9M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
 copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
 check:'<path d="M5 12.5l4.5 4.5L19 7.5"/>',
 srv:'<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
 tg:'<path d="M21 4L3 11l6 2.5L11.5 20l3-4.5L19 19z"/><path d="M9 13.5L21 4"/>',
 search:'<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>'};
const stIco=(k,sw)=>svgI(ST_ICO[k],sw||1.8);
const SET_TOC=[['set-conn','Подключение','conn','Токен Т-Инвестиций и сервер данных'],
  ['set-acc','Аккаунт','acc','Вход по ключу и уведомления в Telegram'],
  ['set-look','Внешний вид','look','Тема, напоминания и разделы меню'],
  ['set-calc','Расчёты','calc','Прогноз ключевой ставки и сбор раскрытий'],
  ['set-local','Данные','local','Хранилище, резервные копии и экспорт'],
  ['set-news','Что нового','news','Версия программы, изменения и планы'],
  ['set-danger','Опасная зона','danger','Очистка и удаление данных']];
const stTxt=h=>String(h==null?'':h).replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
/* строка настройки: слева название и описание, справа контрол */
function stRow(t,d,ctl,o){o=o||{};
  const q=(stTxt(t)+' '+stTxt(d)+' '+(o.kw||'')).toLowerCase();
  return`<div class="st-row${o.stack?' stack':''}${o.cls?' '+o.cls:''}" data-q="${esc(q)}"${o.id?` id="${o.id}"`:''}${o.hidden?' hidden':''}><div class="st-t"><b>${t}</b>${d?`<small>${d}</small>`:''}</div><div class="st-c">${ctl||''}</div></div>`}
function stSw(id,on,label){return`<label class="st-sw"><input type="checkbox" id="${id}" ${on?'checked':''} aria-label="${esc(label)}"><i></i></label>`}
/* поле с секретом: моноширинный текст, показать/скрыть, скопировать */
function stSecret(id,ph,attrs,label){return`<div class="st-secret"><input class="in mono" type="password" id="${id}" placeholder="${esc(ph||'')}" ${attrs||'autocomplete="off"'} spellcheck="false" aria-label="${esc(label||'')}"><button type="button" class="st-ib" data-eye="${id}" aria-label="Показать" title="Показать/скрыть">${stIco('eye')}</button><button type="button" class="st-ib" data-cp="${id}" aria-label="Скопировать" title="Скопировать">${stIco('copy')}</button></div>`}
function stGroup(t,body,o){o=o||{};
  return`<section class="st-card${o.cls?' '+o.cls:''}"${o.id?` id="${o.id}"`:''} data-q="${esc((stTxt(t)+' '+stTxt(o.hint)+' '+(o.q||'')).toLowerCase())}"><header class="st-gh"><h3>${t}</h3>${o.hint!=null?`<span${o.hintId?` id="${o.hintId}"`:''}>${o.hint}</span>`:''}</header>${body}</section>`}
function stMore(t,html){return`<details class="st-more" data-q="${esc((stTxt(t)+' '+stTxt(html)).toLowerCase())}"><summary>${t}</summary><div>${html}</div></details>`}
function stSec(id,title,hint,ico,body){
  return`<section class="st-sec" id="${id}" aria-labelledby="${id}-h"><div class="st-sh"><i>${stIco(ico)}</i><div><h2 id="${id}-h">${esc(title)}</h2><p>${esc(hint)}</p></div></div>${body}</section>`}
/* подтверждение «Сохранено ✓»: у строки или маленьким тостом */
function stOk(el){
  const row=el&&el.closest&&el.closest('.st-row');
  if(!row){stMsg('Сохранено',1,true);return}
  const c=row.querySelector('.st-c');if(!c)return;
  let o=c.querySelector('.st-ok');
  if(!o){o=document.createElement('span');o.className='st-ok';o.setAttribute('role','status');c.insertBefore(o,c.firstChild)}
  o.innerHTML=stIco('check',2.4)+'Сохранено';o.classList.remove('out');
  clearTimeout(o._t);o._t=setTimeout(()=>{o.classList.add('out');o._t=setTimeout(()=>o.remove(),300)},1800);
}
/* тост-сообщение (ошибки остаются дольше) */
function stMsg(t,ok,mini){
  if(typeof toast==='function')return toast(t,ok?'ok':'err',mini?1600:ok?4500:9000);
  let h=document.getElementById('st-toast');
  if(!h){h=document.createElement('div');h.id='st-toast';h.className='st-toast';h.setAttribute('aria-live','polite');h.onclick=()=>{h.innerHTML=''};document.body.appendChild(h)}
  h.innerHTML=`<div class="msg ${ok?'ok':'err'}${mini?' mini':''}" role="${ok?'status':'alert'}">${esc(t)}</div>`;
  clearTimeout(h._t);h._t=setTimeout(()=>{h.innerHTML=''},mini?1600:ok?4500:9000);
}
/* кнопка «Сохранить» активна, только когда поля изменились */
function stDirty(btn,ids){
  const g=id=>document.getElementById(id),b=typeof btn==='string'?g(btn):btn;
  const els=ids.map(g).filter(Boolean);if(!b)return{rebase(){},upd(){}};
  const snap=()=>els.map(e=>e.type==='checkbox'?e.checked:stSecVal(e)).join('\u0001');
  let base=snap();const upd=()=>{b.disabled=snap()===base};
  els.forEach(e=>{e.addEventListener('input',upd);e.addEventListener('change',upd)});b.disabled=true;
  return{rebase(){base=snap();upd()},upd};
}
function stEnter(ids,btn){ids.forEach(id=>{const e=document.getElementById(id);if(e)e.addEventListener('keydown',ev=>{if(ev.key!=='Enter'||ev.isComposing)return;const b=document.getElementById(btn);if(b&&!b.disabled){ev.preventDefault();b.click()}})})}
/* показать/скрыть и скопировать для полей с секретом.
   Сохранённый секрет в поле не лежит (видны только точки-подсказка): «глаз» и «копировать» берут его у локального сервера.
   Показанное, но не изменённое значение считается «без изменений» (stSecVal) — повторно не сохраняется. */
const ST_SECRET_NAME={tok:'token','ds-key':'data_key',bkpw:'backup_password'};
function stSecVal(i){if(typeof i==='string')i=document.getElementById(i);if(!i)return'';return i._stRev!=null&&i.value===i._stRev?'':i.value}
async function stSecFetch(id){
  const n=ST_SECRET_NAME[id];if(!n)return'';
  const r=await api('/api/config/secret?name='+encodeURIComponent(n),{headers:{'X-TA-Secret':'1'}});
  return String((r&&r.value)||'');
}
function stEyeSet(b,sh){b.innerHTML=stIco(sh?'eyeoff':'eye');b.setAttribute('aria-label',sh?'Скрыть':'Показать')}
function stSecretBind(root){
  (root||document).querySelectorAll('[data-eye]').forEach(b=>b.onclick=async()=>{const i=document.getElementById(b.dataset.eye);if(!i)return;
    if(i.type==='password'){
      if(!i.value&&ST_SECRET_NAME[i.id]){
        let v='';try{v=await stSecFetch(i.id)}catch(e){return stMsg(e.message)}
        if(!v)return stMsg('Сохранённого значения нет — поле пустое.',1,true);
        if(i.value)return;                       /* пока ждали ответ, пользователь начал вводить */
        i._stRev=v;i.value=v;
      }
      i.type='text';stEyeSet(b,true);
    }else{
      if(i._stRev!=null){if(i.value===i._stRev)i.value='';i._stRev=null}
      i.type='password';stEyeSet(b,false);
    }});
  (root||document).querySelectorAll('[data-cp]').forEach(b=>b.onclick=async()=>{const i=document.getElementById(b.dataset.cp);if(!i)return;
    let v=i.value;
    if(!v&&ST_SECRET_NAME[i.id]){try{v=await stSecFetch(i.id)}catch(e){return stMsg(e.message)}}
    if(!v)return stMsg('Нечего копировать: поле пустое.');
    let ok=false;try{await navigator.clipboard.writeText(v);ok=true}catch(e){}
    if(!ok){const t=document.createElement('textarea');t.value=v;t.setAttribute('readonly','');t.style.cssText='position:fixed;left:-9999px;top:0;opacity:0';document.body.appendChild(t);t.select();try{ok=document.execCommand('copy')}catch(x){}t.remove()}
    if(!ok)return stMsg('Не удалось скопировать.');
    b.classList.add('done');b.innerHTML=stIco('check',2.4);setTimeout(()=>{b.classList.remove('done');b.innerHTML=stIco('copy')},1200);stMsg('Скопировано',1,true)});
}
/* ── разделы меню ── */
function setMenuHtml(){
  const hid=S.navHidden||[];
  const names=[];
  const grp=NAV_GROUPS.map(([g,keys])=>`<div class="st-mg"><div class="st-ml">${esc(g)}</div><div class="st-chips">${keys.map(k=>{const t=(PAGES.find(p=>p&&p[0]===k)||[])[1];if(!t)return'';names.push(t);
    const lock=NAV_PINNED.includes(k);return`<label class="st-chip${lock?' lock':''}"><input type="checkbox" ${hid.includes(k)?'':'checked'} ${lock?'disabled':''} onchange="navToggle('${k}',this.checked,this)"><span>${esc(t)}</span></label>`}).join('')}</div></div>`).join('');
  return stGroup('Разделы меню',`<div class="st-pad st-menu">${grp}</div>
    <div class="st-foot"><span>Скрытый раздел по-прежнему открывается через поиск (${MOD}K). «Обзор» и «Настройки» скрыть нельзя.</span><button class="btn ghost" onclick="navShowAll()">Показать все</button></div>`,{hint:'скрывайте то, чем не пользуетесь',q:names.join(' ')});
}
function navToggle(k,on,el){
  if(NAV_PINNED.includes(k))return;
  S.navHidden=S.navHidden.filter(x=>x!==k);if(!on)S.navHidden.push(k);
  lsSet('ta_nav_hidden',JSON.stringify(S.navHidden));renderNav();if(el)stOk(el);
}
function navShowAll(){S.navHidden=[];lsSet('ta_nav_hidden','[]');renderNav();renderSettings()}
/* ── Сервер данных ── */
function setDsHtml(c){
  const keySet=c.secret_set&&c.secret_set.data_key;
  return stGroup('Сервер данных',
    stRow('Ключ доступа',`Выдаёт @${esc(AUTH.bot)}${keySet?' · <span class="pos">сохранён</span>, пустое поле ничего не меняет':''}`,stSecret('ds-key',keySet?'••••••••':'вставьте ключ','autocomplete="off"','Ключ доступа к серверу данных'))+
    stRow('Действия','',`<button class="btn" id="ds-save" disabled>Сохранить</button><button class="btn ghost" id="ds-test">Проверить</button>${keySet?'<button class="btn ghost danger" id="ds-clr">Удалить ключ</button>':''}`)+
    `<p class="st-line" id="ds-st">Загружаю…</p>`+
    stMore('Что передаётся на сервер','Данные рынка (Мосбиржа, ФНС, ЦБ, рейтинги, МСФО) берутся через сервер TAnalytic: он сам обновляет их раз в час, поэтому экраны открываются без ожидания источников. Портфель и токен Т-Инвестиций идут напрямую в Т-Банк и на сервер не передаются.'),
    {id:'ds-card',hint:'данные рынка'});
}
async function dsStatus(){
  const el=document.getElementById('ds-st');if(!el)return;
  try{const d=await api('/api/dataserver');
    const cnt=`Ответов с начала работы: из кэша ${d.hit}, свежих ${d.miss}${d.stale?`, устаревших ${d.stale}`:''}; напрямую: ${d.direct}.`;
    const as=AUTH.st,au=as&&as.state==='offline'?` Вход: сервер недоступен, работаем напрямую (${esc(as.error)}).`:as&&as.state==='ok'&&as.expires?` Ключ действует до ${esc(authTime(as.expires))}.`:'';
    el.innerHTML=d.mode==='direct'?`Режим: <b>напрямую</b> к источникам. ${esc(cnt)}`:d.mode==='server'?`Режим: <b>через сервер</b> ${esc(d.url)}. ${esc(cnt)}`:`Режим: <b>временно напрямую</b> — сервер недоступен (${esc(d.error)}), повтор через ${d.retry_in} с. ${esc(cnt)}`;
    if(au)el.innerHTML+=au}
  catch(e){el.textContent=''}
}
function bindSetDs(c,msg){
  const g=id=>document.getElementById(id);
  dsStatus();
  const dirty=stDirty('ds-save',['ds-key']);
  stEnter(['ds-key'],'ds-save');
  const save=async()=>{const k=stSecVal('ds-key');if(!k)return;await post('/api/config',{data_key:k});
    c.secret_set=Object.assign({},c.secret_set,{data_key:true});g('ds-key').value=''};
  g('ds-save').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await save();msg('Ключ сохранён.',1);authCheck(true);renderSettings()}catch(x){msg(x.message);dirty.upd()}};
  g('ds-test').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{const r=await post('/api/dataserver/test',{key:g('ds-key').value});
    msg(`Сервер работает: версия ${r.version}, записей в кэше ${r.cache_items}.`,1)}catch(x){msg(x.message)}finally{b.disabled=false}};
  if(g('ds-clr'))g('ds-clr').onclick=async()=>{try{if(!await uiConfirm({title:'Удалить ключ сервера данных?', body:'Сохранённый ключ будет стёрт с этого компьютера.', danger:true, okText:'Удалить'}))return;await post('/api/config',{clear_data_key:true});authCheck(true);c.secret_set=Object.assign({},c.secret_set,{data_key:false});renderSettings()}catch(x){msg(x.message)}};
}
/* ── Данные на компьютере ── */
function ldBytes(n){
  n=+n||0;
  if(n<1024)return n+' Б';
  if(n<1048576)return Math.max(1,Math.round(n/1024))+' КБ';
  return (n/1048576).toFixed(n<10485760?1:0)+' МБ';
}
function setLocalHtml(c){
  return stGroup('Хранилище',
    stRow('Папка с данными','Операции, история цен, справочник бумаг, логотипы и настройки — всё лежит здесь и в интернет не отправляется',`<span class="mono ld-path" id="ld-dir">${esc(c.data_dir)}</span><button class="btn ghost" id="ld-open">Открыть папку</button>`,{stack:1})+
    `<div class="st-pad"><div id="ld-parts" class="ld-parts"><div class="note">Считаю размер…</div></div></div>`+
    stRow('Перезагрузить данные из API','Заново загрузить операции и цены из Т-Инвестиций (может занять время)',`<button class="btn ghost" id="cache">Перезагрузить</button>`)+
    stRow('Простая копия (zip)','База и настройки, токен в неё не входит. Копии по расписанию — ниже',`<a class="btn ghost" href="/api/backup" download>Скачать zip</a>`),
    {id:'ld-card',hint:'на этом компьютере'});
}
async function ldLoad(){
  const el=document.getElementById('ld-parts');if(!el)return;
  try{const d=await api('/api/localdata');
    const mx=Math.max(1,...d.parts.map(p=>p.bytes));
    const desc={db:'база операций и кэш',cache:'кэш',logos:'логотипы бумаг',app:'скачанная программа',window:'данные окна приложения',config:'настройки, токен и ключ',other:'прочие файлы'};
    el.innerHTML=`<div class="ld-tot">Всего: <b>${ldBytes(d.total)}</b></div>`+d.parts.map(p=>`<div class="ld-row"><span class="ld-n"><span class="mono">${esc(p.name)}</span> <span class="mu">${esc(desc[p.key]||p.title)}</span></span><span class="ld-bar"><i style="width:${Math.max(p.bytes?2:0,Math.round(p.bytes/mx*100))}%"></i></span><span class="ld-v num">${ldBytes(p.bytes)}</span></div>`).join('')}
  catch(e){el.innerHTML=`<div class="msg err">${esc(e.message)}</div>`}
}
function setDangerHtml(c){
  return stGroup('Очистка и удаление',
    stRow('Очистить кэш','Удаляет логотипы и временные данные рынка — они скачаются заново. Операции, импорты, список наблюдения, заметки и настройки остаются',`<button class="btn ghost" id="ld-clear">Очистить кэш</button>`)+
    stRow('Удалить все данные','Стирает токен, ключ входа, базу и настройки. Вернуть их нельзя — сделайте копию заранее',`<button class="btn danger" id="ld-wipe">Удалить все данные</button>`)+
    stMore('Как удалить программу полностью',`Закройте программу, удалите папку <span class="mono">${esc(c.data_dir)}</span> и само приложение (на Mac — из «Программ», на Windows — файл или ярлык программы).`),
    {cls:'danger',hint:'необратимые действия'});
}
function bindSetLocal(c,msg,busy,reset){
  const g=id=>document.getElementById(id);
  ldLoad();
  g('ld-open').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/localdata/open')});
  g('ld-clear').onclick=e=>busy(e.currentTarget,async()=>{if(!await uiConfirm({title:'Очистить кэш?', body:'Будут удалены логотипы и временные данные рынка — они скачаются заново. Операции, настройки, токен и список наблюдения останутся.', okText:'Очистить'}))return;
    const r=await post('/api/localdata/clear');reset();msg('Кэш очищен, освобождено '+ldBytes(r.freed)+'.',1);ldLoad()});
  g('ld-wipe').onclick=e=>busy(e.currentTarget,async()=>{
    if(!await uiConfirm({title:'Удалить все данные программы?', body:'Будут стёрты: токен Т-Инвестиций, ключ входа, база операций (включая импорт из отчётов брокеров), история, список наблюдения, заметки и настройки.\n\nЭто нельзя отменить. Сделайте резервную копию заранее, если она нужна.', danger:true, okText:'Продолжить'}))return;
    if(!await uiConfirm({title:'Точно удалить всё?', body:'Программа вернётся к экрану входа, как при первом запуске.', danger:true, okText:'Да, удалить всё'}))return;
    await post('/api/localdata/wipe',{confirm:'delete-all'});
    try{localStorage.clear()}catch(x){}
    location.reload()});
}
/* ── Аккаунт и доступ ── */
function setAccHtml(){
  return stGroup('Вход в программу',
    stRow('Статус входа','Вход выполняется по ключу из Telegram-бота. Ключ действует 7 дней, токен Т-Инвестиций боту не передаётся',`<span class="st-who" id="acc-who">Проверяю…</span><button class="btn ghost" id="acc-out" style="display:none">Выйти</button>`,{stack:1})+
    stRow('Telegram-бот','Новый ключ — командой <code>/key</code>',`<a class="btn ghost" href="https://t.me/${esc(AUTH.bot)}" target="_blank" rel="noopener noreferrer">Открыть @${esc(AUTH.bot)}</a>`),
    {id:'acc-card',hint:'ключ из бота'});
}
async function bindSetAcc(msg){
  const el=document.getElementById('acc-who');if(!el)return;
  try{AUTH.st=await api('/api/auth/status')}catch(e){}
  const s=AUTH.st;
  if(!s)el.textContent='Нет данных о входе.';
  else if(s.state==='ok'&&!s.server&&!s.username&&!s.expires)el.textContent='Сервер данных выключен — вход по ключу не нужен.';
  else if(s.state==='ok'&&(s.username||s.expires))el.innerHTML=`Вы вошли${s.username?' как <b>@'+esc(s.username)+'</b>':''}${s.expires?`, ключ действует до <b>${esc(authTime(s.expires))}</b>`:''}.`;
  else if(s.state==='ok')el.textContent='Вход выполнен.';
  else if(s.state==='offline')el.textContent='Сервер входа недоступен — программа работает напрямую с источниками.';
  else el.textContent=s.server?'Вы не вошли: нужен ключ из бота.':'Сервер данных выключен — вход по ключу не нужен.';
  const out=document.getElementById('acc-out');
  if(out&&s&&s.state==='ok'&&(s.username||s.expires)){out.style.display='';
    out.onclick=async()=>{try{if(!await uiConfirm({title:'Выйти и стереть ключ?', body:'Ключ будет удалён с этого компьютера, для нового входа понадобится ключ из бота.', danger:true, okText:'Выйти'}))return;AUTH.st=await post('/api/auth/logout');authApply()}catch(e){msg(e.message)}}}
}
