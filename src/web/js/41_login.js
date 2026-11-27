/* ── Вход по ключу из Telegram-бота (ключ действует 7 дней; токен Т-Инвестиций остаётся на компьютере) ── */
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
  el.innerHTML=proPill()+`<span title="Вход по ключу из @${esc(AUTH.bot)}">${s.username?'@'+esc(s.username):'ключ'}${s.expires?' · до '+esc(authTime(s.expires)):''}</span><button id="who-out" title="Выйти и стереть ключ с этого компьютера">Выйти</button>`;
  $('#who-out').onclick=async()=>{try{AUTH.st=await post('/api/auth/logout');authApply()}catch(e){}};
}
function authOverlay(show,err){
  let ov=$('#login-ov');
  if(!show){if(ov)ov.remove();return}
  const bot=esc(AUTH.bot);
  if(ov){const e=$('#lg-err');if(e&&err!==undefined){e.textContent=err;e.style.display=err?'':'none'}return}
  ov=document.createElement('div');ov.id='login-ov';
  ov.innerHTML=`<div class="lg-box" role="dialog" aria-modal="true" aria-label="Вход">
    <div class="logo"><i>${typeof LOGO_SVG==='function'?LOGO_SVG(28):''}</i>
      <div>TAnalytic<small>аналитика портфеля</small></div></div>
    <p class="lg-t">Вход по ключу из Telegram-бота. Ключ действует 7 дней.</p>
    <button class="btn" id="lg-one" type="button">Войти через Telegram</button>
    <div class="lg-n" id="lg-one-st" style="display:none" role="status"></div>
    <a class="btn ghost" id="lg-bot" href="https://t.me/${bot}?start=app" target="_blank" rel="noopener noreferrer">Открыть @${bot} и взять ключ</a>
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
  $('#lg-one').onclick=authOneClick;
  setTimeout(()=>inp.focus(),30);
}
/* Вход в один клик: ссылка в бота, подтверждение в Telegram, ключ приходит сам (без копирования) */
let authLinkTimer=0;
async function authOneClick(){
  const st=$('#lg-one-st'),b=$('#lg-one'),er=$('#lg-err');if(!st||!b||AUTH.busy)return;
  const say=t=>{st.textContent=t;st.style.display=t?'':'none'};
  clearTimeout(authLinkTimer);er.style.display='none';b.disabled=true;
  try{
    const r=await post('/api/auth/link/start');
    const a=document.createElement('a');a.href=r.url;a.target='_blank';a.rel='noopener noreferrer';document.body.appendChild(a);a.click();a.remove();
    say('Откройте Telegram и нажмите «Подтвердить вход» в чате с ботом. Жду подтверждения…');
    const until=Date.now()+(r.ttl+20)*1000;
    const poll=async()=>{
      if(!$('#lg-one-st'))return;
      try{
        const p=await post('/api/auth/link/poll');
        if(p.state==='approved'){AUTH.st=p.auth;authApply();try{load(false)}catch(x){}return}
        if(p.state==='expired'||Date.now()>until){say('Время подтверждения вышло. Нажмите кнопку ещё раз или вставьте ключ вручную.');b.disabled=false;return}
      }catch(x){say(x.message||'Не удалось проверить подтверждение.');b.disabled=false;return}
      authLinkTimer=setTimeout(poll,2000);
    };
    authLinkTimer=setTimeout(poll,2000);
  }catch(x){say('');er.textContent=x.message||'Не удалось начать вход';er.style.display='';b.disabled=false}
}
function authApply(){
  const s=AUTH.st;if(!s)return;
  if(s.bot)AUTH.bot=s.bot;
  const expired=s.state==='ok'&&s.expires&&s.expires*1000<=Date.now();
  if(s.state==='need_login'||expired)authOverlay(true,s.state==='need_login'?authMsg(s.error==='nokey'?'':s.error):authMsg('expired'));
  else authOverlay(false);
  authWho();
  proAuthChanged();
}
async function authCheck(force){
  try{AUTH.st=await api('/api/auth/status'+(force?'?force=1':''));authApply()}catch(e){}
}
function authStart(){
  authCheck(true);
  setInterval(()=>{AUTH.tick++;authCheck(AUTH.tick%5===0)},60000);
}
authStart();
