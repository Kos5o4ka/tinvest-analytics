/* ── Импорт ── */
const IMP_BROKER={tbank:'Т-Инвестиции',vtb:'ВТБ'};   // распознанные отчёты брокеров (format из /api/import/preview)
const ROLE_RU={date:'Дата',type:'Тип операции',isin:'ISIN',ticker:'Тикер',name:'Название / описание',qty:'Количество',price:'Цена',amount:'Сумма',currency:'Валюта',commission:'Комиссия',nkd:'НКД'};
const IMP_GUIDES=[
  ['Т-Инвестиции','Приложение или ЛК → Настройки / Ещё → Отчёты → Брокерский отчёт (XLSX или XML) за весь период.'],
  ['Сбер Инвестиции','СберБанк Онлайн → Инвестиции → Отчёты брокера → Ежемесячный или за период (HTML / XLSX).'],
  ['ВТБ Мои Инвестиции','ЛК ВТБ или приложение → Профиль → Отчёты и налоги → Брокерский отчёт (XLSX / XML).'],
  ['Альфа, БКС, Финам','Личный кабинет брокера → Отчёты по сделкам и движению денег → Выгрузка в XLSX или CSV.']
];
async function renderImport(){
  S.charts=[];
  let cfg;try{cfg=await api('/api/config');S.cfg=cfg}catch(e){$('#view').innerHTML=`<div class="wrap"><div class="msg err">${esc(e.message)}</div></div>`;return}
  const im=S.imp;
  const imps=cfg.imports||[];
  let step='';
  const tb=!!(im&&im.preview&&im.preview.format);   // любой распознанный отчёт брокера: своя карточка со сверкой
  if(tb){
    const pv=im.preview,bd=pv.kinds||{},ru=pv.kinds_ru||{},tg=pv.targets||[];
    const cash=Object.entries(pv.cash_bad||{});
    step=`<div class="card fade"><h2>2. ${esc(pv.title)}<span class="sp">${esc(im.filename)} · ${ddm(pv.period.from)} — ${ddm(pv.period.to)}</span></h2>
      <div class="msg ok">Распознан формат «${esc(pv.title)}». Операций: <b>${pv.count}</b><br>${Object.entries(bd).filter(e=>e[1]).map(([k,v])=>`${ru[k]||k}: ${v}`).join(' · ')}</div>
      ${pv.manual_matches&&pv.manual_matches.count?`<div class="st-callout">Найдено ручных сделок, уже попавших в этот отчёт: <b>${pv.manual_matches.count}</b>. При загрузке они будут заменены строками отчёта, а не задвоятся.${pv.manual_matches.sample.map(m=>`<br>${ddm(m.date)} · ${esc(m.name)} · ${m.qty} шт. · ${f2(m.amount)}`).join('')}</div>`:''}
      <p class="note" style="margin:10px 0">${pv.repo_skipped?`Сделки РЕПО (${pv.repo_skipped} строк) и строки`:'Строки'} отчёта, дублирующие сделки (${pv.mirror_skipped}), не считаются: деньги и бумаги берутся из сделок, выплат и налогов. Входящие остатки на начало периода (бумаг: ${pv.opening_sec}) добавляются служебными операциями и снимаются сами, когда загружен более ранний отчёт${pv.xfer?`; движений бумаг без сделок: ${pv.xfer}`:''}.</p>
      <div class="msg ${pv.cash_ok&&!pv.pos_bad?'ok':'err'}">Сверка с итогами отчёта: деньги ${pv.cash_ok?'сходятся':'не сходятся ('+cash.map(([c,v])=>`${c.toUpperCase()}: по отчёту ${f0(v[0])}, по операциям ${f0(v[1])}`).join('; ')+')'}; бумаги — ${pv.pos_bad?`расхождений: ${pv.pos_bad} из ${pv.pos_total}`:`все ${pv.pos_total} сходятся`}.</div>
      <div class="tbl" style="margin-top:10px;border:1px solid var(--line)"><table><thead><tr><th class="l">Дата</th><th class="l">Тип</th><th class="l">Инструмент</th><th>Кол-во</th><th>Сумма</th></tr></thead><tbody>${pv.sample.map(x=>`<tr><td class="l">${ddm(x[0])}</td><td class="l"><span class="tag">${esc(OPN[x[1]]||x[1])}</span></td><td class="l">${esc(x[2])}</td><td class="num">${x[3]||''}</td><td class="num ${cls(x[4])}">${SM(x[4],x[5])}</td></tr>`).join('')}</tbody></table></div>
      <div id="imp-prog"></div>
      <div class="row" style="margin-top:14px">${tg.map(t=>`<button class="btn" data-tbc="${esc(t.id)}">Добавить к портфелю «${esc(t.name)}»</button>`).join('')}<button class="btn ${tg.length?'ghost':''}" data-tbc="">${tg.length?'Создать новый счёт':'Импортировать'}</button>
      <span class="note">Бумаги будут найдены через API Т-Инвестиций — это займёт несколько секунд.</span></div></div>`;
  }else if(im&&im.preview){
    const pv=im.preview,opts=['<option value="">—</option>'].concat(pv.header.map((h,i)=>`<option value="${i}">${esc(h||('Колонка '+(i+1)))}</option>`)).join('');
    step=`<div class="card fade"><h2>2. Проверьте колонки<span class="sp">${esc(im.filename)} · строк: ${f0(pv.rows)}</span></h2>
      <div class="map">${Object.keys(ROLE_RU).map(r=>`<label class="field"><span>${ROLE_RU[r]}${['date','amount'].includes(r)?' *':''}</span><select class="in" data-role="${r}">${opts}</select></label>`).join('')}</div>
      <p class="note" style="margin:10px 0">Обязательны дата и сумма (или количество и цена). Тип операции определяется по словам: «покупка», «продажа», «купон», «дивиденд», «погашение», «комиссия», «НДФЛ», «пополнение», «вывод». Если колонки «Тип» нет — по описанию и знаку суммы.</p>
      <div class="tbl" style="max-height:260px;border:1px solid var(--line)"><table><thead><tr>${pv.header.map(h=>`<th class="l">${esc(h)}</th>`).join('')}</tr></thead><tbody>${pv.sample.slice(0,8).map(r=>`<tr>${pv.header.map((_,i)=>`<td class="l t2">${esc(r[i]??'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <div class="row" style="margin-top:14px"><button class="btn ghost" id="iparse">Проверить разбор</button></div><div id="iresult" style="margin-top:14px"></div></div>`;
  }
  const resDone=S.impDone;
  const resProgHtml=resDone?`<div class="imp-prog"><div class="row" style="justify-content:space-between"><b>Результат сопоставления бумаг на бирже</b><span class="num">${resDone.resolved} из ${resDone.idents} (${resDone.idents?Math.round(resDone.resolved/resDone.idents*100):100}%)</span></div><div class="imp-prog-bar"><i style="width:${resDone.idents?Math.round(resDone.resolved/resDone.idents*100):100}%"></i></div></div>`:'';
  const guidesHtml=`<div class="card"><h2>Где взять файл в ЛК брокера<span class="sp">поддерживаются XLSX, XLS, HTML и CSV</span></h2>
    <div class="imp-guides">${IMP_GUIDES.map(([b,tx])=>`<div class="imp-gcard"><b>${esc(b)}</b><small>${esc(tx)}</small></div>`).join('')}</div></div>`;
  $('#view').innerHTML=`<div class="wrap fade" style="max-width:1100px">
    <div id="imsg"></div>
    ${resProgHtml}
    <div class="card"><h2>1. Загрузите отчёт другого брокера</h2>
      <div class="drop" id="drop"><input type="file" id="ifile" accept=".csv,.txt,.xlsx,.xlsm,.html,.htm,.xls" style="display:none">
        ${svgI('<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>',1.6).replace('<svg','<svg style="width:34px;height:34px;opacity:.7"')}
        <div style="margin-top:8px;font-weight:600">Перетащите файл сюда или нажмите, чтобы выбрать</div>
        <div class="note" style="margin-top:4px">CSV, Excel (.xlsx) или HTML-отчёт брокера — Сбер, ВТБ, Альфа, БКС, Финам и др.</div></div>
      <div class="g g3" style="margin-top:16px;gap:12px">
        <label class="field"><span>Куда загрузить</span><select class="in" id="itarget"><option value="">Новый счёт</option>${imps.filter(x=>!x.sync_src).map(x=>`<option value="${esc(x.id)}"${im&&im.target===x.id?' selected':''}>${esc(x.name)}</option>`).join('')}</select></label>
        <label class="field"><span>Название счёта</span><input class="in" id="iname" placeholder="Например: Сбер ИИС" value="${esc(im&&im.name||'')}"></label>
        <label class="field"><span>Брокер</span><input class="in" id="ibroker" placeholder="Сбер, ВТБ, БКС…" value="${esc(im&&im.broker||'')}"></label></div>
      <p class="note" style="margin-top:12px">Лучше всего подходит выгрузка всех операций (сделки + движение денег) за всё время. Если формат не распознаётся — заполните <a href="/api/import/template.csv" download="tanalytic-template.csv" style="color:var(--ac)">шаблон CSV</a>. Бумаги находятся по ISIN или тикеру через API Т-Инвестиций, чтобы подтянуть текущие цены, названия, логотипы и купоны. Данные сохраняются только в локальной базе.</p></div>
    ${guidesHtml}
    ${step}
    <div class="card"><h2>Импортированные счета</h2>${imps.length?`<div class="li">${imps.map(x=>{const ps=(x.files||[]).map(f=>f.from&&f.to?[f.from,f.to]:null).filter(Boolean);const span=ps.length?` · ${ddm(ps.map(p=>p[0]).sort()[0])} — ${ddm(ps.map(p=>p[1]).sort().slice(-1)[0])}`:'';return`<div class="it">${logo({name:x.name,ticker:x.name},34)}<div><b>${esc(x.name)}</b><small>${esc(x.broker||'')}${x.broker?' · ':''}файлов: ${x.files.length} · операций: ${f0(x.ops||x.files.reduce((a,f)=>a+f.count,0))}${span}</small></div>
      <div class="row"><select class="in" data-brk="${esc(x.id)}" title="Брокер счёта: тарифы Т-Инвестиций считаются только для счетов Т-Инвестиций" style="width:auto">${Object.entries(cfg.brokers||{}).map(([k,v])=>`<option value="${k}"${k===x.broker_id?' selected':''}>${esc(v)}</option>`).join('')}</select><button class="btn ghost" data-open="${esc(x.id)}">Открыть</button><button class="btn danger" data-del="${esc(x.id)}">Удалить</button></div></div>`}).join('')}</div>`:'<div class="empty" style="padding:20px">Пока ничего не импортировано</div>'}</div>
    <div class="card"><h2>Ручной учёт</h2><p class="note">Купили бумаги у другого брокера или хотите быстро внести текущую позицию, вклад, наличные или недвижимость? Добавьте запись вручную: загружать отчёт не нужно.</p><div class="row" style="margin-top:10px"><button class="btn" id="man-add2">Добавить сделку или актив</button></div></div><div id="man-list"></div></div>`;
  const msg=(t,k)=>{$('#imsg').innerHTML=t?`<div class="msg ${k||'err'}">${t}</div>`:'';if(t)$('#imsg').scrollIntoView({block:'nearest'})};
  const showBusyProg=(containerId,label)=>{const el=document.getElementById(containerId);if(el)el.innerHTML=`<div class="imp-prog" style="margin-top:12px"><div><b>${esc(label||'Импортирую операции и сопоставляю бумаги…')}</b></div><div class="imp-prog-bar indet"><i></i></div></div>`};
  const drop=$('#drop'),inp=$('#ifile');
  // в окне программы — системный диалог (надёжнее скрытого <input type=file> в WebView2), в браузере — обычный выбор файла
  drop.onclick=async()=>{const a=window.pywebview&&pywebview.api;
    if(a&&a.pick_file){try{const r=await a.pick_file();if(r&&r.error)return msg(esc(r.error));if(r&&r.b64)return pickData(r.name,r.b64);if(r===null)return}catch(e){}}
    inp.click()};
  drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};drop.ondragleave=()=>drop.classList.remove('over');
  drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');if(e.dataTransfer.files[0])pick(e.dataTransfer.files[0])};
  inp.onchange=()=>{if(inp.files[0])pick(inp.files[0])};
  async function pick(f){
    if(f.size>60*1024*1024)return msg('Файл больше 60 МБ.');
    S.impDone=null;
    msg('Читаю файл…','info');
    const data=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]||'');r.onerror=rej;r.readAsDataURL(f)});
    return pickData(f.name,data);
  }
  async function pickData(fname,data){const f={name:fname};
    try{const pv=await post('/api/import/preview',{filename:f.name,data});
      const t=!!pv.format,bn=IMP_BROKER[pv.format]||(pv.broker_id&&pv.broker_id!=='other'?pv.broker_name:'')||'';
      S.imp={filename:f.name,data,preview:pv,mapping:pv.mapping,name:$('#iname').value||(t?bn||pv.title:f.name.replace(/\.[^.]+$/,'')),broker:$('#ibroker').value||bn,
        target:t&&pv.targets&&pv.targets.length?pv.targets[0].id:$('#itarget').value};
      await renderImport();
      if(pv.duplicate_of)msg(`Этот отчёт уже загружен в счёт «${esc(pv.duplicate_of.name)}»${pv.duplicate_of.file?` (файл «${esc(pv.duplicate_of.file)}»)`:''}. Повторный импорт будет отклонён, чтобы не дублировать сделки.`);
      else msg('')}
    catch(e){msg(esc(e.message))}
  }
  if(S._pendingDropFile){const pf=S._pendingDropFile;S._pendingDropFile=null;pick(pf)}
  $('#itarget').onchange=e=>{if(S.imp)S.imp.target=e.target.value};
  if(tb){
    document.querySelectorAll('[data-tbc]').forEach(b=>b.onclick=async()=>{
      document.querySelectorAll('[data-tbc]').forEach(x=>x.disabled=true);b.textContent='Импортирую…';
      showBusyProg('imp-prog','Сохраняю операции и ищу бумаги на бирже…');
      try{const res=await post('/api/import/commit',{filename:im.filename,data:im.data,name:$('#iname').value||im.name,broker:$('#ibroker').value,target:b.dataset.tbc});
        S.imp=null;S.impDone=res;S.account=res.id;S.data=S.bonds=S.hist=null;persist();
        await renderImport();msg(`Импортировано операций: ${res.count}${res.total!==res.count?` (всего в портфеле: ${res.total})`:''}. Бумаг найдено на бирже: ${res.resolved} из ${res.idents}.${res.reconciled?` Ручных записей заменено строками отчёта: ${res.reconciled}.`:''}`,'ok');load(true)}
      catch(err){document.querySelectorAll('[data-tbc]').forEach(x=>x.disabled=false);await renderImport();msg(esc(err.message))}})
  }
  if(im&&im.preview&&!tb){
    document.querySelectorAll('[data-role]').forEach(s=>{const v=im.mapping[s.dataset.role];s.value=v==null?'':String(v);s.onchange=()=>{im.mapping[s.dataset.role]=s.value===''?null:+s.value}});
    const req=()=>({filename:im.filename,data:im.data,table:im.preview.table,header_row:im.preview.header_row,mapping:im.mapping});
    $('#iparse').onclick=async e=>{const b=e.currentTarget;b.disabled=true;
      try{const r=await post('/api/import/parse',req());const K={buy:'покупок',sell:'продаж',coupons:'купонов',dividends:'дивидендов',deposits:'пополнений',withdrawals:'выводов',fee_broker:'комиссий',tax_trade:'налогов',repayments:'погашений',fee_service:'обслуживание',margin_fee:'маржа'};
        let ovNote='';
        if(!$('#itarget').value&&r.overlap_account){$('#itarget').value=r.overlap_account.id;S.imp.target=r.overlap_account.id;ovNote=`<div class="msg info" style="margin-top:10px">Найдены пересекающиеся операции со счётом «${esc(r.overlap_account.name)}» (${r.overlap_account.matches} шт.) — выбран этот счёт, чтобы сделки за общий период не продублировались.</div>`}
        if(r.duplicate_of)msg('');      // то же предупреждение уже есть ниже, рядом с результатом разбора
        const mmNote=r.manual_matches&&r.manual_matches.count?`<div class="msg info" style="margin-top:10px">Найдено ручных сделок, уже попавших в этот отчёт: <b>${r.manual_matches.count}</b>. При загрузке они будут заменены строками отчёта, а не задвоятся.${r.manual_matches.sample.map(m=>`<br>${ddm(m.date)} · ${esc(m.name)} · ${m.qty} шт. · ${f2(m.amount)}`).join('')}</div>`:'';
        const dupMsg=r.duplicate_of?`<div class="msg err" style="margin-top:10px">Этот отчёт уже загружен в счёт «${esc(r.duplicate_of.name)}». Повторная загрузка запрещена, чтобы сделки не задвоились.</div>`:'';
        $('#iresult').innerHTML=`<div class="msg ${r.count?'ok':'err'}">Распознано операций: <b>${r.count}</b>${r.skipped?`, пропущено строк: ${r.skipped}`:''}${r.from?` · с ${ddm(r.from)} по ${ddm(r.to)}`:''}<br>${Object.entries(r.kinds).map(([k,v])=>`${K[k]||k}: ${v}`).join(' · ')}</div>${dupMsg}${ovNote}
          <div class="tbl" style="margin-top:10px;border:1px solid var(--line)"><table><thead><tr><th class="l">Дата</th><th class="l">Тип</th><th class="l">Инструмент</th><th>Кол-во</th><th>Сумма</th></tr></thead><tbody>${r.sample.map(x=>`<tr><td class="l">${ddm(x[0])}</td><td class="l"><span class="tag">${esc(OPN[x[1]]||x[1])}</span></td><td class="l">${esc(x[2])}</td><td class="num">${x[3]||''}</td><td class="num ${cls(x[4])}">${SM(x[4],x[5])}</td></tr>`).join('')}</tbody></table></div>${mmNote}
          <div id="imp-prog2"></div>
          ${r.count&&!r.duplicate_of?'<div class="row" style="margin-top:14px"><button class="btn" id="icommit">Импортировать</button><span class="note">Бумаги будут найдены через API Т-Инвестиций — это займёт несколько секунд.</span></div>':''}`;
        const c=$('#icommit');if(c)c.onclick=async ev=>{const bb=ev.currentTarget;bb.disabled=true;bb.textContent='Импортирую…';
          showBusyProg('imp-prog2','Сохраняю операции и ищу бумаги на бирже…');
          try{const res=await post('/api/import/commit',{...req(),name:$('#iname').value||im.name,broker:$('#ibroker').value,target:$('#itarget').value});
            S.imp=null;S.impDone=res;S.account=res.id;S.data=S.bonds=S.hist=null;persist();
            await renderImport();msg(`Импортировано операций: ${res.count}${res.total!==res.count?` (всего в портфеле: ${res.total})`:''}. Бумаг найдено на бирже: ${res.resolved} из ${res.idents}.${res.reconciled?` Ручных записей заменено строками отчёта: ${res.reconciled}.`:''}`,'ok');load(true)}
          catch(err){bb.disabled=false;bb.textContent='Импортировать';msg(esc(err.message))}}}
      catch(err){$('#iresult').innerHTML=`<div class="msg err">${esc(err.message)}</div>`}finally{b.disabled=false}};
  }
  try{const mb=$('#man-add2');if(mb)mb.onclick=()=>manualOpen();manualDrawList()}catch(e){}
  document.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{if(!await uiConfirm({title:'Удалить импортированный счёт?', body:'Счёт и его операции будут удалены из локальной базы. Исходный файл отчёта можно загрузить снова.', danger:true, okText:'Удалить'}))return;
    await post('/api/import/delete',{id:b.dataset.del});if(S.account===b.dataset.del)S.account='all';S.data=S.bonds=S.hist=null;persist();renderImport();load(true)});
  document.querySelectorAll('[data-brk]').forEach(s=>s.onchange=async()=>{
    try{await post('/api/import/broker',{id:s.dataset.brk,broker_id:s.value});S.data=null;msg('Брокер счёта сохранён.','ok');load(true)}catch(e){msg(esc(e.message))}});
  document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{S.account=b.dataset.open;S.bonds=S.hist=null;persist();S.page='dash';renderNav();load(false)});
}
