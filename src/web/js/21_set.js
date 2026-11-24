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
    <div class="st-foot"><span>Скрытый раздел по-прежнему открывается через поиск (Ctrl+K / Cmd+K). «Обзор» и «Настройки» скрыть нельзя.</span><button class="btn ghost" onclick="navShowAll()">Показать все</button></div>`,{hint:'скрывайте то, чем не пользуетесь',q:names.join(' ')});
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
    stRow('Адрес сервера','Пусто — сервер по умолчанию, <code>off</code> — напрямую к источникам',`<input class="in mono st-wide" id="ds-url" value="${esc(c.data_server||'')}" placeholder="сервер по умолчанию" autocomplete="off" spellcheck="false" aria-label="Адрес сервера данных">`)+
    stRow('Ключ доступа',`Выдаёт @${esc(AUTH.bot)}${keySet?' · <span class="pos">сохранён</span>, пустое поле ничего не меняет':''}`,stSecret('ds-key',keySet?'••••••••':'вставьте ключ','autocomplete="off"','Ключ доступа к серверу данных'))+
    stRow('Действия','',`<button class="btn" id="ds-save" disabled>Сохранить</button><button class="btn ghost" id="ds-test">Проверить</button>${keySet?'<button class="btn ghost danger" id="ds-clr">Удалить ключ</button>':''}`)+
    `<p class="st-line" id="ds-st">Загружаю…</p>`+
    stMore('Что передаётся на сервер','Данные рынка (Мосбиржа, ФНС, ЦБ, рейтинги, МСФО) берутся через ваш сервер — быстрее и без лишних запросов к источникам. Портфель и токен Т-Инвестиций идут напрямую в Т-Банк и на сервер не передаются.'),
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
  const dirty=stDirty('ds-save',['ds-url','ds-key']);
  stEnter(['ds-url','ds-key'],'ds-save');
  const save=async()=>{const k=stSecVal('ds-key'),b={data_server:g('ds-url').value};if(k)b.data_key=k;await post('/api/config',b);
    c.data_server=g('ds-url').value.trim();if(k)c.secret_set=Object.assign({},c.secret_set,{data_key:true});g('ds-key').value=''};
  g('ds-save').onclick=async e=>{const b=e.currentTarget;b.disabled=true;try{await save();msg('Сохранено. Новые запросы пойдут '+(c.data_server.toLowerCase()==='off'?'напрямую.':'через сервер.'),1);authCheck(true);renderSettings()}catch(x){msg(x.message);dirty.upd()}};
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
  else if(s.state==='ok'&&(s.username||s.expires))el.innerHTML=`Вы вошли${s.username?' как <b>@'+esc(s.username)+'</b>':''}${s.expires?`, ключ действует до <b>${esc(authTime(s.expires))}</b>`:''}.`;
  else if(s.state==='ok')el.textContent='Вход выполнен.';
  else if(s.state==='offline')el.textContent='Сервер входа недоступен — программа работает напрямую с источниками.';
  else el.textContent=s.server?'Вы не вошли: нужен ключ из бота.':'Сервер данных выключен — вход по ключу не нужен.';
  const out=document.getElementById('acc-out');
  if(out&&s&&s.state==='ok'&&(s.username||s.expires)){out.style.display='';
    out.onclick=async()=>{try{if(!confirm('Выйти и стереть ключ с этого компьютера?'))return;AUTH.st=await post('/api/auth/logout');authApply()}catch(e){msg(e.message)}}}
}
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
    msg(`Подключено. Счетов: ${r.accounts}.`,1);S.page='dash';persist();renderNav();load(true)}catch(x){msg(x.message);dTok.upd()}};
  $('#test').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/config',body());const r=await post('/api/test');msg(`Подключение работает. Счетов: ${r.accounts}.`,1)});
  /* песочница и SSL — переключатели сохраняются сразу */
  /* песочница меняет и адреса API, и нужный токен — применяется вместе с токеном по «Сохранить и подключиться», а не сразу */
  $('#sb').onchange=e=>{const el=e.currentTarget;if(el.checked===!!c.sandbox)return;
    stMsg(el.checked?'Вставьте токен песочницы и нажмите «Сохранить и подключиться».':'Вставьте боевой токен (только чтение) и нажмите «Сохранить и подключиться».',1)};
  $('#cache').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Заново загрузить все операции и цены из Т-Инвестиций? Это может занять время.'))return;await post('/api/cache/clear');reset();msg('Локальный кэш очищен, данные загрузятся заново.',1);load(true)});
  if($('#clr'))$('#clr').onclick=e=>busy(e.currentTarget,async()=>{if(!confirm('Удалить сохранённый токен?'))return;await post('/api/config',{clear_token:true});reset();renderSettings()});
  if($('#sbopen'))$('#sbopen').onclick=e=>busy(e.currentTarget,async()=>{const r=await post('/api/sandbox/open');S.account=r.accountId;persist();S.data=null;msg('Открыт счёт '+r.accountId,1);load(true)});
  if($('#sbpay'))$('#sbpay').onclick=e=>busy(e.currentTarget,async()=>{await post('/api/sandbox/payin',{accountId:S.account,amount:$('#amt').value});S.data=S.bonds=S.hist=null;msg('Счёт пополнен на '+M(+$('#amt').value,'rub',0),1);load(true)});
}
