/* ── Первые минуты и ежедневный визит: онбординг, карточка «Сегодня», подсказки пустых состояний, шпаргалка клавиш ── */
const obPl=(n,a,b,c)=>{const m=Math.abs(n)%100,k=m%10;return m>10&&m<20?c:k===1?a:k>1&&k<5?b:c};
const obDm=d=>d?d.slice(8,10)+'.'+d.slice(5,7):'';
const obIsPro=()=>typeof isPro==='function'?isPro():true;

/* ── 1. Онбординг: вместо голой страницы настроек, пока не задан токен и нет импортов ── */
const ob={busy:false,done:false,err:'',skip:false,help:false};
const _renderSettingsOrig=renderSettings;
renderSettings=async function(){
  let c=S.cfg;
  try{c=await api('/api/config');S.cfg=c}catch(e){}
  if(c&&!c.token_set&&!(c.imports||[]).length&&!ob.skip){ob.done=false;ob.err='';return obRender()}
  return _renderSettingsOrig();
};
function obStep(n,state,title,body){
  return`<div class="ob-step ${state}"><div class="ob-n">${state==='done'?'✓':n}</div><div class="ob-b"><h3>${title}</h3>${body||''}</div></div>`;
}
function obRender(){
  const v=$('#view');if(!v)return;
  const tokDone=ob.done;
  const authOk=typeof AUTH!=='undefined'&&AUTH.st&&AUTH.st.state==='ok';
  v.innerHTML=`<div class="wrap fade" style="max-width:760px"><div class="card ob-card">
    <div class="ob-hd"><div class="ob-t">Добро пожаловать 👋</div><p class="t2">Три шага, и вы увидите свой портфель: доходность, выплаты, оферты и риски по облигациям.</p></div>
    ${obStep(1,'done','Ключ из бота',`<p class="mu">${authOk?'Вход выполнен.':'Готово — можно переходить к следующему шагу.'}</p>`)}
    ${obStep(2,tokDone?'done':'now','Токен Т-Инвестиций «только чтение»',tokDone?'<p class="mu">Токен сохранён и проверен.</p>':`
      <p class="mu">Он нужен, чтобы программа могла прочитать ваши счета. Покупать и продавать с ним нельзя.</p>
      <div class="ob-row"><input class="in" type="password" id="ob-tok" placeholder="t.XXXXXXXXXXXXXXXXXXXX" autocomplete="off" spellcheck="false" aria-label="API-токен Т-Инвестиций">
        <button class="btn" id="ob-save">Сохранить и проверить</button></div>
      <div id="ob-msg" role="status">${ob.err?`<div class="msg err">${esc(ob.err)}</div>`:''}</div>
      <details class="ob-how" ${ob.help?'open':''}><summary>Где взять токен</summary><ol>
        <li>Откройте <a href="https://www.tbank.ru/invest/settings/api/" target="_blank" rel="noopener noreferrer">tbank.ru/invest/settings/api</a> и войдите в Т-Банк (или в приложении: Профиль → Настройки → Токены T-Invest API).</li>
        <li>Нажмите «Создать токен», выберите доступ <b>«Только для чтения»</b> и нужные счета.</li>
        <li>Скопируйте токен сразу (второй раз его не покажут) и вставьте в поле выше.</li></ol></details>
      <p class="ob-priv">${svgI('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>')}Токен хранится только на этом компьютере и никуда не отправляется, кроме Т-Инвестиций.</p>`)}
    ${obStep(3,tokDone?'now':'soon','Первый взгляд на портфель',tokDone?'<div class="wait">Загружаю портфель…</div>':'<p class="mu">Откроется сам, как только токен будет сохранён.</p>')}
    <div class="ob-alt">Нет Т-Инвестиций? <button class="lnk" id="ob-imp">Импортируйте отчёт другого брокера</button>
      <span class="mu"> · </span><button class="lnk" id="ob-all">Все настройки</button></div>
  </div></div>`;
  const b=$('#ob-save');if(!b)return;
  const input=$('#ob-tok');
  const save=async()=>{
    const tok=input.value.trim();
    if(!tok){ob.err='Вставьте токен в поле.';$('#ob-msg').innerHTML=`<div class="msg err">${esc(ob.err)}</div>`;input.focus();return}
    ob.busy=true;ob.err='';b.disabled=true;b.textContent='Проверяю…';
    try{
      await post('/api/config',{token:tok});
      const r=await post('/api/test');
      ob.done=true;ob.help=false;
      try{S.cfg=await api('/api/config')}catch(e){}
      const c=S.cfg||{};$('#mode').className='badge'+(c.sandbox?' sb':'');$('#mode').innerHTML=c.token_set?'<b></b>'+(c.sandbox?'Песочница':'Боевой режим'):'';
      obRender();
      S.data=S.bonds=S.hist=S.today=null;S.account='all';S.page='dash';persist();renderNav();load(true);
    }catch(e){
      {const m=e&&e.message?e.message:'Не удалось подключиться';ob.err=/^Программа не отвечает/.test(m)?m:m+'. Проверьте, что токен скопирован целиком и имеет доступ «только чтение».'}
      ob.help=true;ob.busy=false;obRender();
    }
  };
  b.onclick=save;
  input.onkeydown=e=>{if(e.key==='Enter')save()};
  $('#ob-imp').onclick=()=>go('imp');
  $('#ob-all').onclick=()=>{ob.skip=true;renderSettings()};
  if(!tokDone&&!ob.err)input.focus();
}
/* пока токена нет, а страница «Настройки» открыта при старте: бутстрап вызывает renderSettings() по имени — перехват выше сработает */

/* ── 2. Карточка «Сегодня» на «Обзоре» ── */
const TD_TTL_MS=10*60*1000;
function todayEnsure(){
  const k=S.account||'all',t=S.today;
  if(t&&t.acc===k&&(t.loading||Date.now()-t.at<TD_TTL_MS))return;
  S.today={acc:k,loading:true,at:Date.now(),data:null};
  api('/api/today?account='+encodeURIComponent(k)).then(d=>{
    if(!S.today||S.today.acc!==k)return;
    S.today={acc:k,loading:false,at:Date.now(),data:d};
    if(S.page==='dash')renderSoon();
  }).catch(()=>{if(S.today&&S.today.acc===k){S.today={acc:k,loading:false,at:Date.now(),data:{empty:true}};}});
}
(()=>{const r=$('#refresh');if(r)r.addEventListener('click',()=>{S.today=null})})();
const tdTag=()=>obIsPro()?'':'<span class="td-pro" title="Функция тарифа Pro">Pro</span>';
function tdLine(go,ico,html,tag,cls){
  return`<button class="td-it ${cls||''}" data-go="${go}"><i>${svgI(ico,1.9)}</i><span>${html}</span>${tag||''}<em aria-hidden="true">›</em></button>`;
}
function tdOfferText(o){
  const kind=o.kind==='put'?'PUT':o.kind==='call'?'CALL':'оферта';
  const st=o.status==='open'?`идёт приём заявок${o.period_end?' до '+obDm(o.period_end):''}`:o.status==='upcoming'?`приём заявок с ${obDm(o.period_start)}`:o.kind==='put'?'приём заявок пока не открыт':'решает эмитент';
  return`<span class="td-k ${o.kind}">${kind}</span> <b>${esc(o.name||'')}</b> · ${obDm(o.date)} · ${st}`;
}
function todayCard(){
  if(!(S.data&&S.data.portfolio))return'';
  todayEnsure();
  const t=S.today,d=t&&t.data,p=S.data.portfolio,lines=[];
  if(p.daily!=null&&p.total)lines.push(tdLine('pos','<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    `Сегодня портфель ${p.daily===0?'без изменений':`<b class="num ${cls(p.daily)}">${SM(p.daily)}</b>${p.daily_pct!=null?` <span class="mu">(${pct(p.daily_pct)})</span>`:''}`}`));
  if(d&&!d.empty){
    if(d.payments){const x=d.payments,bk=x.by_kind||{},parts=[];
      if(bk.coupon)parts.push('купоны');if(bk.dividend)parts.push('дивиденды');if(bk.amortization)parts.push('амортизации');
      lines.push(tdLine('pay','<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/>',
        `На ближайшие ${x.days} дней: <b class="num pos">${M(x.sum,'rub',0)}</b> · ${x.count} ${obPl(x.count,'выплата','выплаты','выплат')}${parts.length?' <span class="mu">('+parts.join(', ')+')</span>':''}`));}
    if(d.offers){const x=d.offers;
      lines.push(`<div class="td-grp">${x.items.slice(0,3).map(o=>tdLine('off','<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',tdOfferText(o),tdTag(),o.status==='open'?'hot':'')).join('')}${x.count>3?`<div class="mu td-more">…и ещё ${x.count-3} в «Офертах»</div>`:''}</div>`);}
    if(d.ratings){const x=d.ratings;
      lines.push(tdLine('mon','<path d="M12 3l2.5 5.5L20 9.5l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-1z"/>',
        `Рейтинги за ${x.days} дней: <b>${x.count}</b> ${obPl(x.count,'изменение','изменения','изменений')} у эмитентов портфеля${x.negative?` <span class="neg">· ${x.negative} ${obPl(x.negative,'требует','требуют','требуют')} внимания</span>`:''}`));}
    if(d.alerts){const x=d.alerts;
      lines.push(tdLine('mon','<path d="M18 16v-5a6 6 0 0 0-12 0v5l-2 3h16z"/><path d="M10 21h4"/>',
        `Тревоги мониторинга: <b>${x.count}</b>${x.high?` <span class="neg">· ${x.high} ${obPl(x.high,'высокая','высокие','высоких')}</span>`:''}`,tdTag()));}
  }else if(t&&t.loading&&!lines.length)return`<div class="card td-card noprint"><h2>Сегодня</h2><div class="sk" style="height:46px;border-radius:10px"></div></div>`;
  if(!lines.length)return'';
  return`<div class="card td-card noprint"><h2>Сегодня<span class="sp">${new Date().toLocaleDateString('ru-RU',{day:'numeric',month:'long'})}</span>${t&&t.loading?'<span class="td-ld">обновляю…</span>':''}</h2>${lines.join('')}</div>`;
}

/* ── 3. Подсказки в пустых состояниях ── */
function emptyHint(text,btns,ico){
  return`<div class="card empty hint">${svgI(ico||'<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>')}<div style="max-width:440px">${text}</div>${btns&&btns.length?`<div class="row" style="justify-content:center">${btns.map(([g,t,primary])=>`<button class="btn ${primary?'':'ghost'}" data-go="${g}">${esc(t)}</button>`).join('')}</div>`:''}</div>`;
}

/* ── 4. Шпаргалка клавиш («?») ── */
const KS_ROWS=[['Ctrl + K  /  ⌘ + K','Поиск по разделам, бумагам и командам'],['?','Эта шпаргалка'],['Esc','Закрыть окно, карточку бумаги или поиск'],['↑  ↓  Enter','Выбор в поиске']];
function ksToggle(){
  const o=document.getElementById('ks-ov');
  if(o){o.remove();return}
  const el=document.createElement('div');el.id='ks-ov';
  el.innerHTML=`<div id="ks" role="dialog" aria-label="Горячие клавиши"><h2>Горячие клавиши</h2>${KS_ROWS.map(([k,t])=>`<div class="ks-r"><kbd>${esc(k)}</kbd><span>${esc(t)}</span></div>`).join('')}<div class="mu" style="font-size:12px;margin-top:10px">Esc — закрыть</div></div>`;
  el.addEventListener('mousedown',e=>{if(e.target===el)el.remove()});
  document.body.appendChild(el);
}
document.addEventListener('keydown',e=>{
  const o=document.getElementById('ks-ov');
  if(o&&e.key==='Escape'){e.preventDefault();e.stopPropagation();o.remove();return}
  if(e.key!=='?'||e.ctrlKey||e.metaKey||e.altKey)return;
  const a=document.activeElement,t=a&&a.tagName;
  if(t==='TEXTAREA'||t==='SELECT'||(t==='INPUT'&&!/^(checkbox|radio|button|submit|reset|range|file|color)$/.test(a.type))||(a&&a.isContentEditable))return;
  e.preventDefault();ksToggle();
},true);
