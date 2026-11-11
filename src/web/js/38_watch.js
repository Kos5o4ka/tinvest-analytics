/* ── Наблюдение: список бумаг с целями и тревогами, дневник, уведомления в Telegram ── */
S.wset=null;S.watch=null;S.wnotes=null;S.wfilter='';S.wsug=[];
const WT_REMIND=[['','без напоминания'],['7','через 7 дней'],['30','через 30 дней'],['90','через 3 месяца'],['180','через полгода'],['365','через год']];
const WT_TPL=[['Почему купил: ','Почему купил'],['Продать, если: ','Что должно случиться, чтобы продать']];

/* множество ISIN из списка (для звёздочек в скринере и карточке) */
function watchLoadSet(){
  if(S.wset&&S.wset.loading)return;
  const old=S.wset;S.wset=Object.assign(new Set(old||[]),{loading:true});
  api('/api/watch/isins').then(j=>{S.wset=new Set(j.isins||[]);watchRefreshView()}).catch(()=>{S.wset=new Set(old||[])});
}
function watchHas(isin){
  if(!S.wset||!(S.wset instanceof Set))watchLoadSet();
  return !!(S.wset&&S.wset.has(isin));
}
function watchRefreshView(){
  if(S.page==='scr'&&S.scr&&!S.scr.error&&$('#scr-body'))drawScr();
  else if(['watch','mon'].includes(S.page))renderSoon();
}
/* добавить/убрать бумагу; вызывается карточкой облигации и скринером */
async function watchToggle(isin){
  if(!isin)return false;
  const r=await post('/api/watch',{action:'toggle',isin});
  S.wset=new Set(r.isins||[]);S.watch=null;
  try{document.dispatchEvent(new CustomEvent('watchchange',{detail:{isin,on:!!r.in_watch}}))}catch(e){}
  watchRefreshView();
  return !!r.in_watch;
}
function watchStar(isin){
  const on=watchHas(isin);
  return`<button class="wt-star${on?' on':''}" data-wstar="${esc(isin)}" title="${on?'Убрать из наблюдения':'Добавить в наблюдение'}" aria-label="Наблюдение">${on?'★':'☆'}</button>`;
}

function watchEnsure(){
  const w=S.watch;
  if(w&&(w.loading||w.error||(w.data&&Date.now()-w.t<3e5)))return;
  S.watch={loading:true,t:Date.now()};
  api('/api/watch').then(d=>{S.watch={data:d,t:Date.now()};S.wset=new Set(d.items.map(x=>x.isin));
    if(['watch','mon'].includes(S.page))renderSoon()}).catch(e=>{S.watch={error:e.message,t:Date.now()};if(['watch','mon'].includes(S.page))renderSoon()});
}
function notesEnsure(){
  const n=S.wnotes;
  if(n&&(n.loading||n.error||n.data))return;
  S.wnotes={loading:true};
  api('/api/notes').then(d=>{S.wnotes={data:d.rows};if(S.page==='watch')renderSoon()}).catch(e=>{S.wnotes={error:e.message};if(S.page==='watch')renderSoon()});
}

/* группа «Наблюдение» на странице «Мониторинг» */
function watchMonGroup(){
  if(!S.wset||!(S.wset instanceof Set)){watchLoadSet();return''}
  if(!S.wset.size)return'';
  watchEnsure();
  const w=S.watch;
  if(!w||w.loading)return`<div class="card"><h2>Наблюдение<span class="sp">загружаю…</span></h2></div>`;
  if(w.error||!w.data)return'';
  const al=w.data.alerts;
  return`<div class="card"><h2>Наблюдение<span class="sp">${w.data.items.length} бумаг · ${al.length?al.length+' тревог':'тревог нет'}</span>
    <button class="btn ghost" data-go="watch" style="margin-left:auto;padding:4px 12px;font-size:12px">Открыть список</button></h2>
    ${al.length?al.slice(0,8).map(monAlertHtml).join('')+(al.length>8?`<div class="mu" style="font-size:12px;margin-top:6px">…и ещё ${al.length-8}</div>`:''):'<div class="mon-ok">По бумагам из списка наблюдения тревог нет</div>'}</div>`;
}

function wtRow(r){
  const th=v=>v!=null?String(v).replace('.',','):'';
  const sp=r.spark&&r.spark.length>2?monSpark(r.spark,70,22):'';
  return`<tr data-isin="${esc(r.isin)}" title="Открыть карточку"><td class="l"><b style="font-weight:600">${esc(r.name)}</b>${r.n_high?` <span class="tag" style="color:var(--neg)">!</span>`:''}<br><small class="mu num">${isinTxt(r.isin)}${r.offer?' · оферта '+ddm(r.offer):''}${r.mat?' · до '+ddm(r.mat):''}</small></td>
    <td class="l">${r.rating?`<span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}">${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td>
    <td class="num">${r.price!=null?f2(r.price):'—'}</td><td class="num"><b>${r.yield_!=null?pctp(r.yield_,2):'—'}</b></td>
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread):'—'}</td>
    <td class="num ${cls(r.chg30)}">${r.chg30!=null?pct(r.chg30,1):'—'}</td><td>${sp}</td>
    <td class="num">${r.dur!=null?f2(r.dur):'—'}</td><td class="num">${r.turn?short(r.turn):'—'}</td>
    <td><input class="in num wt-in" data-k="target_yield" data-isin="${esc(r.isin)}" value="${esc(th(r.target_yield))}" placeholder="от, %" inputmode="decimal" title="Сообщить, когда доходность станет не ниже"></td>
    <td><input class="in num wt-in" data-k="target_price" data-isin="${esc(r.isin)}" value="${esc(th(r.target_price))}" placeholder="до, %" inputmode="decimal" title="Сообщить, когда цена станет не выше"></td>
    <td><input class="in wt-in wt-note" data-k="note" data-isin="${esc(r.isin)}" value="${esc(r.note||'')}" placeholder="заметка" maxlength="300"></td>
    <td class="l">${(r.flags||[]).map(f=>`<span class="tag" style="color:var(--neg)">${esc(f)}</span>`).join(' ')}</td>
    <td><button class="btn ghost wt-del" data-wdel="${esc(r.isin)}" title="Убрать из наблюдения">×</button></td></tr>`;
}
function wtNoteHtml(n){
  const due=n.remind_on&&n.remind_on<=new Date().toISOString().slice(0,10);
  return`<div class="wt-note-i" data-isin="${esc(n.isin)}"><div class="wt-nh"><b>${esc(n.name||n.isin)}</b><small class="mu num">${ddm(n.date)}</small>
    ${n.remind_on?`<span class="tag ${due?'wt-due':''}" title="Напоминание">${due?'пора пересмотреть':'напомнить '+ddm(n.remind_on)}</span>`:''}
    <span style="margin-left:auto;display:flex;gap:6px">${n.remind_on?`<button class="btn ghost wt-sm" data-ndone="${esc(n.id)}">Пересмотрено</button>`:''}<button class="btn ghost wt-sm" data-ndel="${esc(n.id)}" title="Удалить заметку">Удалить</button></span></div>
    <div class="wt-nt">${esc(n.text)}</div></div>`;
}
function pWatch(){
  watchEnsure();notesEnsure();
  const w=S.watch,nt=S.wnotes;
  if(!w||w.loading)return`<div class="card">${waitBox('Проверяю бумаги из списка: цены, рейтинги, спреды и цели…')}</div>`;
  if(w.error)return`<div class="msg err">${esc(w.error)} <button class="btn ghost" id="wt-r">Повторить</button></div>`;
  const d=w.data,sm=d.summary,goals=d.alerts.filter(a=>a.kind==='goal').length;
  const hold=(S.bonds&&S.bonds.rows||[]).filter(r=>r.isin).map(r=>[r.isin,r.name,'в портфеле']);
  const opts=[...d.items.map(r=>[r.isin,r.name,'наблюдение']),...hold.filter(h=>!d.items.some(r=>r.isin===h[0]))];
  const notes=((nt&&nt.data)||[]).filter(n=>!S.wfilter||n.isin===S.wfilter);
  const nIsins=[...new Map(((nt&&nt.data)||[]).map(n=>[n.isin,n.name||n.isin])).entries()];
  return`<div class="g g4">${kpi('Бумаг в списке',d.items.length,'облигации, за которыми вы следите',null,S1)}${kpi('Высокие тревоги',sm.high,'дефолт, понижение рейтинга, сильное падение','neg',S8)}
    ${kpi('Средние тревоги',sm.medium,'наблюдение, оферты, напоминания','',S3)}${kpi('Цели достигнуты',goals,'доходность или цена дошли до заданной',goals?'pos':'',S2)}</div>
  ${(d.notes||[]).filter(n=>d.items.length).map(n=>`<div class="msg">${esc(n)}</div>`).join('')}
  <div class="card"><h2>Добавить бумагу<span class="sp">по названию или ISIN, из облигаций Мосбиржи</span></h2>
    <div class="wt-add"><input class="in" id="wt-q" placeholder="например, Самолет или RU000A0JQAM6" autocomplete="off"><div id="wt-sug" class="wt-sug"></div></div>
    <p class="note" style="margin-top:8px">Можно также нажать ☆ в строке скринера или в карточке облигации. Цели задаются прямо в таблице ниже.</p></div>
  ${d.alerts.length?`<div class="card"><h2>Тревоги по списку<span class="sp">рейтинги, цена, спред, оферты, цели и напоминания</span></h2>${d.alerts.slice(0,S.wtAll?999:10).map(monAlertHtml).join('')}${d.alerts.length>10?`<button class="btn ghost" id="wt-all" style="margin-top:6px">${S.wtAll?'Свернуть':'Показать все ('+d.alerts.length+')'}</button>`:''}</div>`:''}
  <div class="card"><h2>Список наблюдения<span class="sp">клик по строке — карточка выпуска</span><button class="btn ghost" id="wt-r" style="margin-left:auto;padding:4px 12px;font-size:12px">Обновить</button></h2>
    ${d.items.length?`<div class="tbl"><table id="wt-tab"><thead><tr><th class="l">Выпуск</th><th class="l">Рейтинг</th><th>Цена, %</th><th>Доходность</th><th>Спред, п.п.</th><th>Δ 30 дн.</th><th>Спред 90 дн.</th><th>Дюрация</th><th>Оборот</th>
      <th title="Тревога, когда доходность станет не ниже этого значения">Цель: доходность ≥</th><th title="Тревога, когда цена станет не выше этого значения">Цель: цена ≤</th><th class="l">Заметка</th><th class="l">Флаги</th><th></th></tr></thead><tbody>${d.items.map(wtRow).join('')}</tbody></table></div>
      <p class="note" style="margin-top:10px">Цены и доходность — по данным Мосбиржи с задержкой. Тревоги считаются теми же правилами и порогами, что и в «Мониторинге» (пороги меняются там). Справочная информация, не инвестиционная рекомендация.</p>`
      :'<div class="empty" style="padding:18px 0">Список пуст. Найдите бумагу выше или нажмите ☆ в скринере.</div>'}</div>
  <div class="card"><h2>Дневник<span class="sp">заметки по любым бумагам, в том числе из портфеля</span></h2>
    <div class="wt-form"><label class="field"><span>Бумага</span><select class="in" id="nt-sel"><option value="">— выберите —</option>${opts.map(o=>`<option value="${esc(o[0])}">${esc(o[1])} · ${o[2]}</option>`).join('')}<option value="_other">другая (ввести ISIN)…</option></select>
      <input class="in" id="nt-isin" placeholder="ISIN" style="display:none;margin-top:6px"></label>
      <label class="field"><span>Напомнить пересмотреть</span><select class="in" id="nt-rem">${WT_REMIND.map(o=>`<option value="${o[0]}">${o[1]}</option>`).join('')}</select></label></div>
    <label class="field" style="margin-top:12px"><span>Заметка</span><textarea class="in wt-ta" id="nt-text" rows="3" maxlength="2000" placeholder="Почему купил, на что рассчитываю, что должно случиться, чтобы продать…"></textarea></label>
    <div class="row" style="margin-top:10px">${WT_TPL.map(t=>`<button class="btn ghost wt-sm" data-tpl="${esc(t[0])}">${t[1]}</button>`).join('')}<button class="btn" id="nt-add" style="margin-left:auto">Добавить заметку</button></div>
    <div id="nt-msg"></div>
    <div class="row" style="margin:18px 0 6px"><label class="field" style="max-width:320px"><span>Показывать</span><select class="in" id="nt-flt"><option value="">все заметки</option>${nIsins.map(([i,n])=>`<option value="${esc(i)}" ${S.wfilter===i?'selected':''}>${esc(n)}</option>`).join('')}</select></label></div>
    ${!nt||nt.loading?waitBox('Загружаю заметки…'):nt.error?`<div class="msg err">${esc(nt.error)}</div>`:notes.length?notes.map(wtNoteHtml).join(''):'<div class="mu" style="font-size:13px;padding:6px 0">Заметок пока нет.</div>'}</div>`;
}
function bindWatch(){
  const rl=()=>{S.watch=null;render()};
  const r=$('#wt-r');if(r)r.onclick=rl;
  const al=$('#wt-all');if(al)al.onclick=()=>{S.wtAll=!S.wtAll;render()};
  let to,seq=0;
  const q=$('#wt-q');
  if(q){
    const draw=()=>{const box=$('#wt-sug');if(!box)return;
      box.innerHTML=S.wsug.length?S.wsug.map(x=>`<div class="wt-s" data-isin="${esc(x.isin)}"><div><b>${esc(x.name)}</b><small class="mu num"> ${isinTxt(x.isin)}${x.mat?' · до '+ddm(x.mat):''}</small></div><span class="num">${x.yield!=null?pctp(x.yield,1):''}</span>
        <button class="btn ${x.in_watch?'ghost':''} wt-sm" data-wadd="${esc(x.isin)}" ${x.in_watch?'disabled':''}>${x.in_watch?'в списке':'Добавить'}</button></div>`).join(''):(q.value.trim().length>=2?'<div class="mu" style="padding:8px 2px;font-size:13px">Ничего не найдено среди облигаций, торгуемых на Мосбирже.</div>':'')};
    draw();
    q.oninput=()=>{clearTimeout(to);const v=q.value.trim(),my=++seq;
      if(v.length<2){S.wsug=[];draw();return}
      to=setTimeout(()=>api('/api/watch/search?'+new URLSearchParams({q:v})).then(j=>{if(my!==seq)return;S.wsug=j.rows||[];draw()}).catch(()=>{}),200)};
    q.onkeydown=e=>{if(e.key==='Enter'&&S.wsug.length){const x=S.wsug.find(s=>!s.in_watch);if(x)watchToggle(x.isin)}};
  }
  const sug=$('#wt-sug');
  if(sug)sug.onclick=async e=>{const b=e.target.closest('[data-wadd]');if(!b)return;e.stopPropagation();b.disabled=true;
    try{await watchToggle(b.dataset.wadd);S.wsug=[]}catch(er){alert(er.message)}};
  const tab=$('#wt-tab');
  if(tab){
    tab.onclick=async e=>{const b=e.target.closest('[data-wdel]');if(!b)return;e.stopPropagation();
      try{await post('/api/watch',{action:'remove',isin:b.dataset.wdel});S.wset.delete(b.dataset.wdel);S.watch=null;render()}catch(er){alert(er.message)}};
    tab.onchange=async e=>{const i=e.target.closest('.wt-in');if(!i)return;
      try{await post('/api/watch',{action:'update',isin:i.dataset.isin,[i.dataset.k]:i.value});if(i.dataset.k!=='note'){S.watch=null;render()}}catch(er){alert(er.message)}};
  }
  const sel=$('#nt-sel');
  if(sel)sel.onchange=()=>{$('#nt-isin').style.display=sel.value==='_other'?'':'none'};
  document.querySelectorAll('[data-tpl]').forEach(b=>b.onclick=()=>{const t=$('#nt-text');t.value=(t.value?t.value+'\n':'')+b.dataset.tpl;t.focus()});
  const add=$('#nt-add');
  if(add)add.onclick=async()=>{
    const m=(t,ok)=>{$('#nt-msg').innerHTML=`<div class="msg ${ok?'ok':'err'}">${esc(t)}</div>`};
    let isin=sel.value==='_other'?$('#nt-isin').value.trim().toUpperCase():sel.value;
    if(!isin)return m('Выберите бумагу или введите ISIN.');
    if(!$('#nt-text').value.trim())return m('Напишите текст заметки.');
    add.disabled=true;
    try{await post('/api/notes',{action:'add',isin,text:$('#nt-text').value,remind_days:$('#nt-rem').value});S.wnotes=null;S.watch=null;render()}
    catch(er){m(er.message);add.disabled=false}};
  const fl=$('#nt-flt');if(fl)fl.onchange=()=>{S.wfilter=fl.value;render()};
  const view=$('#view');
  if(view)view.querySelectorAll('[data-ndel]').forEach(b=>b.onclick=async e=>{e.stopPropagation();if(!confirm('Удалить заметку?'))return;
    try{await post('/api/notes',{action:'delete',id:b.dataset.ndel});S.wnotes=null;S.watch=null;render()}catch(er){alert(er.message)}});
  if(view)view.querySelectorAll('[data-ndone]').forEach(b=>b.onclick=async e=>{e.stopPropagation();
    try{await post('/api/notes',{action:'done',id:b.dataset.ndone});S.wnotes=null;S.watch=null;render()}catch(er){alert(er.message)}});
}
/* звёздочки (скринер, карточка и др.): клик не открывает карточку выпуска */
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-wstar]');if(!b)return;
  e.stopPropagation();b.disabled=true;
  try{await watchToggle(b.dataset.wstar)}catch(er){alert(er.message)}finally{b.disabled=false}
},true);

/* ── Telegram: карточка в «Настройках» (уведомления идут через сервер данных и общего бота) ── */
function setTgHtml(c){
  if(!isPro())return`<div class="card" id="tg-lock"><h2>Уведомления в Telegram<span class="sp">Pro</span></h2>${proTeaser('Уведомления в Telegram — в Pro: тревоги, выплаты и сводка прямо в мессенджере')}</div>`;
  const on=(k,d)=>c[k]==null?d:!!c[k];
  return`<div class="card" id="tg-card"><h2>Уведомления в Telegram<span class="sp">по желанию</span></h2>
    <div style="display:grid;gap:16px">
    <p class="note" style="margin:0">Уведомления приходят от <b id="tg-bot">@tanalyticbot</b> — того же бота, который выдаёт ключ входа. Ничего настраивать не нужно.</p>
    <p class="note" id="tg-state" style="margin:0"></p>
    <label class="sw"><input type="checkbox" id="tg-en" ${on('tg_enabled',false)?'checked':''}><i></i><div><b>Присылать уведомления</b><small>Главный выключатель; отключить можно и в самом боте командой <code>/notify_off</code></small></div></label>
    <label class="sw"><input type="checkbox" id="tg-mon" ${on('tg_on_mon',true)?'checked':''}><i></i><div><b>Тревоги мониторинга</b><small>Только высокой важности: дефолт, понижение рейтинга, сильное падение цены</small></div></label>
    <label class="sw"><input type="checkbox" id="tg-wat" ${on('tg_on_watch',true)?'checked':''}><i></i><div><b>Наблюдение и цели</b><small>Тревоги по списку наблюдения, достигнутые цели и напоминания из дневника</small></div></label>
    <div class="row"><label class="field" style="max-width:300px"><span>Ближайшие выплаты: за сколько дней сообщать (0 — выключить)</span><input class="in num" id="tg-pay" type="number" min="0" max="60" value="${+c.tg_pay_days||0}"></label></div>
    <div class="row"><label class="sw"><input type="checkbox" id="tg-dg" ${on('tg_digest',false)?'checked':''}><i></i><div><b>Ежедневная сводка</b><small>Портфель, выплаты на неделю, тревоги</small></div></label>
      <label class="field" style="max-width:130px"><span>Время</span><input class="in num" id="tg-time" type="time" value="${esc(c.tg_digest_time||'10:00')}"></label></div>
    <div class="row"><button class="btn" id="tg-save">Сохранить</button><button class="btn ghost" id="tg-test">Отправить тестовое сообщение</button><button class="btn ghost" id="tg-run" title="Проверить тревоги и отправить новые прямо сейчас">Проверить сейчас</button></div>
    <p class="note"><b>Что нужно знать.</b> Текст уведомлений (названия бумаг и суммы) проходит через сервер данных и бот @tanalyticbot и удаляется сразу после отправки; токен Т-Инвестиций никуда не передаётся. Уведомления приходят, <b>только пока программа запущена</b>; проверка выполняется раз в 10–15 минут, одна и та же тревога повторно не отправляется. Нужен вход по ключу из бота (раздел «Сервер данных»).</p></div></div>`;
}
function bindSetTg(c,msg){
  const g=id=>document.getElementById(id);if(!g('tg-card'))return;
  const body=()=>({tg_enabled:g('tg-en').checked,tg_on_mon:g('tg-mon').checked,tg_on_watch:g('tg-wat').checked,
    tg_pay_days:g('tg-pay').value||0,tg_digest:g('tg-dg').checked,tg_digest_time:g('tg-time').value||'10:00'});
  const busy=async(b,fn)=>{b.disabled=true;try{await fn()}catch(e){msg(e.message)}finally{b.disabled=false}};
  const save=async()=>{const r=await post('/api/tg/save',body());Object.assign(c,r.settings);return r};
  api('/api/tg/info').then(i=>{
    g('tg-bot').textContent='@'+String(i.bot||'tanalyticbot').replace(/^@/,'');
    g('tg-state').textContent=!i.server?'Сервер данных выключен («off»): уведомления работают через него. Включите сервер данных в настройках.':
      i.state==='need_login'?'Войдите по ключу из бота — иначе уведомления отправить нельзя.':i.state==='offline'?'Сервер недоступен.':'';
  }).catch(()=>{});
  g('tg-save').onclick=e=>busy(e.currentTarget,async()=>{await save();msg('Настройки уведомлений сохранены.',1)});
  g('tg-test').onclick=e=>busy(e.currentTarget,async()=>{await save();await post('/api/tg/test');msg('Тестовое сообщение отправлено — проверьте Telegram.',1)});
  g('tg-run').onclick=e=>busy(e.currentTarget,async()=>{await save();const r=await post('/api/tg/run');msg(r.sent?'Отправлено новых пунктов: '+r.sent+'.':'Новых тревог для отправки нет.',1)});
}
