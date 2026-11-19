/* ── Помощь в сборе раскрытий эмитентов (по желанию, по умолчанию выключено) ── */
const CROWD={st:null};
function crowdLoad(){return api('/api/crowd/status').then(s=>{CROWD.st=s;return s}).catch(()=>null)}
setTimeout(crowdLoad,3000);
const CROWD_STATE={off:'выключено',idle:'ждёт заданий',working:'работает',backoff:'пауза после ошибки сайта',no_server:'нет связи с сервером данных'};
function setCrowdHtml(c){
  return`<div class="card" id="crowd-card"><h2>Помогать собирать раскрытия эмитентов<span class="sp" id="crowd-sp"></span></h2><div style="display:grid;gap:12px">
    <p class="note" style="margin:0">Включено по умолчанию. Сообщения эмитентов о купонах, выкупах и дефолтах лежат на сайте e-disclosure.azipi.ru, а наш сервер данных его открыть не может. <b>Пока программа открыта</b>, она скачивает публичные страницы этого сайта <b>с вашего интернет-подключения — примерно одну страницу раз в 15 секунд</b> — и отправляет их на сервер данных. Так все пользователи видят купоны, выкупы и дефолты по своим облигациям. Токен, портфель и другие ваши данные не отправляются; в страницах только то, что видно любому посетителю сайта. Сайт видит ваш IP-адрес, как при обычном заходе в браузере. При ошибках сайта программа делает паузу на 30 минут. Выключить можно в любой момент.</p>
    <label class="sw"><input type="checkbox" id="crowd-on"><i></i><div><b>Помогать собирать раскрытия</b><small>Работает только пока программа запущена и подключён сервер данных.</small></div></label>
    <p class="note" id="crowd-info">Загружаю…</p></div></div>`;
}
async function bindSetCrowd(c,msg){
  const on=document.getElementById('crowd-on');if(!on)return;
  const show=async()=>{const s=await crowdLoad();if(!s||!document.getElementById('crowd-info'))return;
    on.checked=!!s.enabled;
    const stt=s.enabled&&s.state==='off'?'запускается…':(CROWD_STATE[s.state]||s.state);   // включили, а поток ещё не проснулся
    document.getElementById('crowd-sp').textContent=s.enabled?stt:'выключено';
    document.getElementById('crowd-info').innerHTML=`Отправлено страниц, принятых сервером: <b>${s.accepted}</b>${s.fetched?` (скачано ${s.fetched})`:''}.${s.enabled?` Состояние: ${esc(stt)}${s.message?' — '+esc(s.message):''}.`:''}${!s.available?' Подключите сервер данных и войдите по ключу — без этого помощь не работает.':''}`;
    clearTimeout(CROWD.t);if(s.enabled)CROWD.t=setTimeout(show,5000)};
  on.onchange=async()=>{try{await post('/api/crowd/settings',{enabled:on.checked});msg(on.checked?'Спасибо! Программа будет скачивать страницы, пока она открыта.':'Помощь выключена.',1);show()}catch(e){msg(e.message);on.checked=!on.checked}};
  show();
}
/* одноразовая карточка-приглашение (в разделе «Раскрытие эмитента» карточки облигации) */
function crowdInviteHtml(){
  const s=CROWD.st;if(!s||s.enabled||s.dismissed)return'';
  return`<div class="msg" id="crowd-inv" style="margin:0 0 10px"><b>Помогите собирать раскрытия эмитентов.</b> Сервер данных не может открыть сайт e-disclosure.azipi.ru, поэтому сообщения о купонах, выкупах и дефолтах собираются с компьютеров пользователей: программа, пока она открыта, скачивает публичные страницы сайта примерно раз в 15 секунд и отправляет их на сервер. Ваши данные (токен, портфель) не передаются; сайт видит только ваш IP-адрес, как при обычном заходе. Включить можно и позже в «Настройках».
    <div class="row" style="margin-top:8px"><button class="btn" onclick="crowdInvite(true)">Включить</button><button class="btn ghost" onclick="crowdInvite(false)">Не сейчас</button></div></div>`;
}
async function crowdInvite(on){
  try{await post('/api/crowd/settings',on?{enabled:true}:{dismissed:true});await crowdLoad();const e=document.getElementById('crowd-inv');if(e)e.remove()}catch(e){}
}
