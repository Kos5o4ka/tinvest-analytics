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
  v.innerHTML=`<div class="wrap fade" style="max-width:960px"><div class="card ob-card">
    <div class="ob-hd"><div class="ob-t">Добро пожаловать в TAnalytic 👋</div>
      <p class="t2">Выберите удобный способ начать — это займёт меньше минуты. Все данные хранятся только на вашем компьютере.</p></div>
    <div class="ob-cards">
      <div class="ob-opt ob-opt-main">
        <div class="ob-opt-h"><span class="ob-badge">1</span><div><h3>Подключить Т-Инвестиции</h3><small class="mu">Автозагрузка сделок, портфеля и истории по токену «только чтение»</small></div></div>
        ${tokDone?'<div class="msg ok">Токен сохранён и проверен — загружаю портфель…</div>':`
        <div class="ro-note">${svgI('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>')}<div><b>Токен только для чтения.</b> С ним нельзя торговать или выводить деньги.</div></div>
        <div class="ob-row"><input class="in" type="password" id="ob-tok" placeholder="t.XXXXXXXXXXXXXXXXXXXX" autocomplete="off" spellcheck="false" aria-label="API-токен Т-Инвестиций">
          <button class="btn" id="ob-save">Проверить и подключить</button></div>
        <label class="sw" style="margin:6px 0 4px"><input type="checkbox" id="ob-sb" ${ob.sb?'checked':''}><i></i><div><b>Токен песочницы (Sandbox)</b><small>включите для тестового токена</small></div></label>
        <div id="ob-msg" role="status">${ob.err?`<div class="msg err">${esc(ob.err)}</div>`:''}</div>
        <details class="ob-how" ${ob.help?'open':''}><summary>Где взять токен за 30 секунд</summary><ol>
          <li>Откройте <a href="https://www.tbank.ru/invest/settings/api/" target="_blank" rel="noopener noreferrer">tbank.ru/invest/settings/api</a> (или в приложении: Профиль → Настройки → Токены T-Invest API).</li>
          <li>Нажмите «Создать токен», выберите доступ <b>«Только для чтения»</b> и нужные счета.</li>
          <li>Скопируйте токен и вставьте в поле выше — сначала проверим, потом сохраним.</li></ol></details>`}
      </div>
      <div class="ob-opt-col">
        <div class="ob-opt">
          <div class="ob-opt-h"><span class="ob-badge">2</span><div><h3>Другой брокер</h3><small class="mu">ВТБ · Сбер · Альфа · БКС · Финам</small></div></div>
          <p class="mu" style="margin:6px 0 12px;font-size:13px">Загрузите брокерский отчёт (XLSX / XML / HTML) — программа построит доходность, выплаты и налоги без токена.</p>
          <button class="btn ghost" id="ob-imp">Загрузить отчёт брокера</button>
        </div>
        <div class="ob-opt">
          <div class="ob-opt-h"><span class="ob-badge">3</span><div><h3>Посмотреть демо-портфель</h3><small class="mu">Без токена и ваших данных</small></div></div>
          <p class="mu" style="margin:6px 0 12px;font-size:13px">Готовый живой портфель с облигациями, акциями, офертами и графиками — посмотрите, как всё работает.</p>
          <button class="btn" id="ob-demo">Открыть демо в 1 клик</button>
        </div>
      </div>
    </div>
    <div class="ob-alt">
      <span>Хотите просто изучить рынок без портфеля?</span>
      <button class="lnk" id="ob-mkt">Скринер облигаций →</button>
      <span class="mu"> · </span><button class="lnk" id="ob-calc">Калькулятор →</button>
      <span class="mu"> · </span><button class="lnk" id="ob-all">Все настройки</button>
    </div>
  </div></div>`;
  const dm=$('#ob-demo');if(dm)dm.onclick=()=>demoEnter(dm);
  const imp=$('#ob-imp');if(imp)imp.onclick=()=>go('imp');
  const mkt=$('#ob-mkt');if(mkt)mkt.onclick=()=>go('scr');
  const clc=$('#ob-calc');if(clc)clc.onclick=()=>go('calc');
  const all=$('#ob-all');if(all)all.onclick=()=>{ob.skip=true;renderSettings()};
  const b=$('#ob-save');if(!b)return;
  const input=$('#ob-tok'),sb=$('#ob-sb');
  if(sb)sb.onchange=()=>{ob.sb=sb.checked};
  const save=async()=>{
    const tok=input.value.trim(),sandbox=!!(sb&&sb.checked);
    ob.sb=sandbox;
    if(!tok){ob.err='Вставьте токен в поле.';$('#ob-msg').innerHTML=`<div class="msg err">${esc(ob.err)}</div>`;input.focus();return}
    ob.busy=true;ob.err='';b.disabled=true;b.textContent='Проверяю…';
    try{
      await post('/api/test',{token:tok,sandbox});
      await post('/api/config',{token:tok,sandbox});
      ob.done=true;ob.help=false;
      try{S.cfg=await api('/api/config')}catch(e){}
      const c=S.cfg||{};$('#mode').className='badge'+(c.sandbox?' sb':'');$('#mode').innerHTML=c.token_set?'<b></b>'+(c.sandbox?'Песочница':'Боевой режим'):'';
      obRender();
      S.data=S.bonds=S.hist=S.today=null;S.account='all';S.page='dash';persist();renderNav();load(true);
    }catch(e){
      {const m=e&&e.message?e.message:'Не удалось подключиться';ob.err=/^Программа не отвечает/.test(m)?m:m+'. Проверьте, что токен скопирован целиком и выбран верный режим (боевой / песочница).'}
      ob.help=true;ob.busy=false;obRender();
    }
  };
  b.onclick=save;
  input.onkeydown=e=>{if(e.key==='Enter')save()};
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
    if(d.movers&&d.movers.items&&d.movers.items.length){const x=d.movers;
      lines.push(`<div class="td-grp"><div class="mu td-more" style="margin:2px 0 0">Лидеры падения облигаций · оборот от ${M(x.min_turn,'rub',0)}</div>${x.items.map(o=>o.isin?`<div class="td-it td-mv" data-isin="${esc(o.isin)}" role="button" tabindex="0"><i>${svgI('<path d="M3 7l6 6 4-4 8 8"/><path d="M15 17h6v-6"/>',1.9)}</i><span><b>${esc(o.name||'')}</b> <small class="mu num">${esc(o.isin||'')}</small> · <b class="num neg">${f2(o.chg)} %</b></span><em aria-hidden="true">›</em></div>`:tdLine('scr','<path d="M3 7l6 6 4-4 8 8"/><path d="M15 17h6v-6"/>',`<b>${esc(o.name||'')}</b> · <b class="num neg">${f2(o.chg)} %</b>`,'','td-mv')).join('')}<div class="mu td-more">Полный список — в «Скринере», вкладка «Лидеры»</div></div>`);}
  }else if(t&&t.loading&&!lines.length)return`<div class="card td-card noprint"><h2>Сегодня</h2><div class="sk" style="height:46px;border-radius:10px"></div></div>`;
  if(!lines.length)return'';
  return`<div class="card td-card noprint"><h2>Сегодня<span class="sp">${new Date().toLocaleDateString('ru-RU',{day:'numeric',month:'long'})}</span>${t&&t.loading?'<span class="td-ld">обновляю…</span>':''}</h2>${lines.join('')}</div>`;
}

/* ── 3. Подсказки в пустых состояниях ── */
function emptyHint(text,btns,ico){
  return`<div class="card empty hint">${svgI(ico||'<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>')}<div style="max-width:440px">${text}</div>${btns&&btns.length?`<div class="row" style="justify-content:center">${btns.map(([g,t,primary])=>`<button class="btn ${primary?'':'ghost'}" data-go="${g}">${esc(t)}</button>`).join('')}</div>`:''}</div>`;
}

/* ── 4. Шпаргалка клавиш («?») ── */
/* шпаргалка клавиш («?») — в 65_delight.js */
