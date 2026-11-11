/* ── Вход по ключу из Telegram-бота (ключ действует сутки; токен Т-Инвестиций остаётся на компьютере) ── */
const AUTH={st:null,bot:'tanalyticbot',busy:false,tick:0};
function authTime(ts){
  const d=new Date(ts*1000),t=d.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
  return d.toDateString()===new Date().toDateString()?t:d.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit'})+' '+t;
}
function authMsg(code){
  return code==='expired'?'Ключ истёк — получите новый в боте':code==='banned'?'Доступ ограничен':code==='invalid'?'Неверный ключ':'';
}
function authWho(){
  const el=$('#who');if(!el)return;
  const s=AUTH.st;
  if(!s||s.state!=='ok'||(!s.username&&!s.expires)){el.innerHTML='';el.style.display='none';return}
  el.style.display='';
  el.innerHTML=`<span title="Вход по ключу из @${esc(AUTH.bot)}">${s.username?'@'+esc(s.username):'ключ'}${s.expires?' · до '+esc(authTime(s.expires)):''}</span><button id="who-out" title="Выйти и стереть ключ с этого компьютера">Выйти</button>`;
  $('#who-out').onclick=async()=>{try{AUTH.st=await post('/api/auth/logout');authApply()}catch(e){}};
}
function authOverlay(show,err){
  let ov=$('#login-ov');
  if(!show){if(ov)ov.remove();return}
  const bot=esc(AUTH.bot);
  if(ov){const e=$('#lg-err');if(e&&err!==undefined){e.textContent=err;e.style.display=err?'':'none'}return}
  ov=document.createElement('div');ov.id='login-ov';
  ov.innerHTML=`<div class="lg-box" role="dialog" aria-modal="true" aria-label="Вход">
    <div class="logo"><i><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#111" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16l5-6 4 3 7-8"/></svg></i>
      <div>T-Invest Analytics<small>аналитика портфеля</small></div></div>
    <p class="lg-t">Вход по ключу из Telegram-бота. Ключ действует сутки.</p>
    <a class="btn" id="lg-bot" href="https://t.me/${bot}?start=app" target="_blank" rel="noopener noreferrer">Открыть @${bot}</a>
    <form id="lg-form" autocomplete="off">
      <input class="in" id="lg-key" placeholder="TIA-XXXX-XXXX-XXXX" autocomplete="off" autocapitalize="characters" spellcheck="false" autofocus>
      <div class="lg-err" id="lg-err" style="display:${err?'':'none'}">${esc(err||'')}</div>
      <button class="btn ghost" id="lg-go" type="submit">Войти</button>
    </form>
    <p class="lg-n">Токен Т-Инвестиций остаётся только на этом компьютере и боту не передаётся.</p></div>`;
  document.body.appendChild(ov);
  const inp=$('#lg-key');
  inp.addEventListener('input',()=>{const v=inp.value.toUpperCase().replace(/\s+/g,'');if(v!==inp.value)inp.value=v});
  $('#lg-form').onsubmit=async e=>{
    e.preventDefault();const k=inp.value.trim();if(!k||AUTH.busy)return;
    AUTH.busy=true;const b=$('#lg-go');b.disabled=true;const er=$('#lg-err');er.style.display='none';
    try{AUTH.st=await post('/api/auth/login',{key:k});authApply();try{load(false)}catch(x){}}
    catch(x){er.textContent=x.message||'Не удалось войти';er.style.display=''}
    finally{AUTH.busy=false;b.disabled=false}
  };
  setTimeout(()=>inp.focus(),30);
}
function authApply(){
  const s=AUTH.st;if(!s)return;
  if(s.bot)AUTH.bot=s.bot;
  const expired=s.state==='ok'&&s.expires&&s.expires*1000<=Date.now();
  if(s.state==='need_login'||expired)authOverlay(true,s.state==='need_login'?authMsg(s.error==='nokey'?'':s.error):authMsg('expired'));
  else authOverlay(false);
  authWho();
}
async function authCheck(force){
  try{AUTH.st=await api('/api/auth/status'+(force?'?force=1':''));authApply()}catch(e){}
}
function authStart(){
  authCheck(true);
  setInterval(()=>{AUTH.tick++;authCheck(AUTH.tick%5===0)},60000);
}
authStart();
