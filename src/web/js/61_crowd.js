/* ── Помощь в сборе раскрытий эмитентов (включено по умолчанию, можно отключить в «Настройках») ── */
const CROWD={st:null};
function crowdLoad(){return api('/api/crowd/status').then(s=>{CROWD.st=s;return s}).catch(()=>null)}
setTimeout(crowdLoad,3000);
const CROWD_STATE={off:'выключено',idle:'ждёт заданий',working:'работает',backoff:'пауза после ошибки сайта',no_server:'нет связи с сервером данных'};
/* одноразовая карточка-приглашение (в разделе «Раскрытие эмитента» карточки облигации) */
function crowdInviteHtml(){
  const s=CROWD.st;if(!s||s.enabled||s.dismissed)return'';
  return`<div class="msg" id="crowd-inv" style="margin:0 0 10px"><b>Помогите собирать раскрытия эмитентов.</b> Сервер данных не может открыть сайт e-disclosure.azipi.ru, поэтому сообщения о купонах, выкупах и дефолтах собираются с компьютеров пользователей: программа, пока она открыта, скачивает публичные страницы сайта примерно раз в 15 секунд и отправляет их на сервер. Ваши данные (токен, портфель) не передаются; сайт видит только ваш IP-адрес, как при обычном заходе. Включить можно и позже в «Настройках».
    <div class="row" style="margin-top:8px"><button class="btn" onclick="crowdInvite(true)">Включить</button><button class="btn ghost" onclick="crowdInvite(false)">Не сейчас</button></div></div>`;
}
async function crowdInvite(on){
  try{await post('/api/crowd/settings',on?{enabled:true}:{dismissed:true});await crowdLoad();const e=document.getElementById('crowd-inv');if(e)e.remove()}catch(e){}
}
