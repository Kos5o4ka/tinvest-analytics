/* ── Импорт ── */
const IMP_BROKER={tbank:'Т-Инвестиции',vtb:'ВТБ'};   // распознанные отчёты брокеров (format из /api/import/preview)
const ROLE_RU={date:'Дата',type:'Тип операции',isin:'ISIN',ticker:'Тикер',name:'Название / описание',qty:'Количество',price:'Цена',amount:'Сумма',currency:'Валюта',commission:'Комиссия',nkd:'НКД'};
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
      <p class="note" style="margin:10px 0">${pv.repo_skipped?`Сделки РЕПО (${pv.repo_skipped} строк) и строки`:'Строки'} отчёта, дублирующие сделки (${pv.mirror_skipped}), не считаются: деньги и бумаги берутся из сделок, выплат и налогов. Входящие остатки на начало периода (бумаг: ${pv.opening_sec}) добавляются служебными операциями и снимаются сами, когда загружен более ранний отчёт${pv.xfer?`; движений бумаг без сделок: ${pv.xfer}`:''}.</p>
      <div class="msg ${pv.cash_ok&&!pv.pos_bad?'ok':'err'}">Сверка с итогами отчёта: деньги ${pv.cash_ok?'сходятся':'не сходятся ('+cash.map(([c,v])=>`${c.toUpperCase()}: по отчёту ${f0(v[0])}, по операциям ${f0(v[1])}`).join('; ')+')'}; бумаги — ${pv.pos_bad?`расхождений: ${pv.pos_bad} из ${pv.pos_total}`:`все ${pv.pos_total} сходятся`}.</div>
      <div class="tbl" style="margin-top:10px;border:1px solid var(--line)"><table><thead><tr><th class="l">Дата</th><th class="l">Тип</th><th class="l">Инструмент</th><th>Кол-во</th><th>Сумма</th></tr></thead><tbody>${pv.sample.map(x=>`<tr><td class="l">${ddm(x[0])}</td><td class="l"><span class="tag">${esc(OPN[x[1]]||x[1])}</span></td><td class="l">${esc(x[2])}</td><td class="num">${x[3]||''}</td><td class="num ${cls(x[4])}">${SM(x[4],x[5])}</td></tr>`).join('')}</tbody></table></div>
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
  $('#view').innerHTML=`<div class="wrap fade" style="max-width:1100px">
    <div id="imsg"></div>
    <div class="card"><h2>1. Загрузите отчёт другого брокера</h2>
      <div class="drop" id="drop"><input type="file" id="ifile" accept=".csv,.txt,.xlsx,.xlsm,.html,.htm,.xls" style="display:none">
        ${svgI('<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>',1.6).replace('<svg','<svg style="width:34px;height:34px;opacity:.7"')}
        <div style="margin-top:8px;font-weight:600">Перетащите файл сюда или нажмите, чтобы выбрать</div>
        <div class="note" style="margin-top:4px">CSV, Excel (.xlsx) или HTML-отчёт брокера — Сбер, ВТБ, Альфа, БКС, Финам и др.</div></div>
      <div class="g g3" style="margin-top:16px;gap:12px">
        <label class="field"><span>Куда загрузить</span><select class="in" id="itarget"><option value="">Новый счёт</option>${imps.map(x=>`<option value="${esc(x.id)}"${im&&im.target===x.id?' selected':''}>${esc(x.name)}</option>`).join('')}</select></label>
        <label class="field"><span>Название счёта</span><input class="in" id="iname" placeholder="Например: Сбер ИИС" value="${esc(im&&im.name||'')}"></label>
        <label class="field"><span>Брокер</span><input class="in" id="ibroker" placeholder="Сбер, ВТБ, БКС…" value="${esc(im&&im.broker||'')}"></label></div>
      <p class="note" style="margin-top:12px">Лучше всего подходит выгрузка всех операций (сделки + движение денег) за всё время. Если формат не распознаётся — заполните <a href="/api/import/template.csv" style="color:var(--ac)">шаблон CSV</a>. Бумаги находятся по ISIN или тикеру через API Т-Инвестиций, чтобы подтянуть текущие цены, названия, логотипы и купоны. Данные сохраняются только в локальной базе.</p></div>
    ${step}
    <div class="card"><h2>Импортированные счета</h2>${imps.length?`<div class="li">${imps.map(x=>`<div class="it">${logo({name:x.name,ticker:x.name},34)}<div><b>${esc(x.name)}</b><small>${esc(x.broker||'')}${x.broker?' · ':''}файлов: ${x.files.length} · операций: ${f0(x.ops||x.files.reduce((a,f)=>a+f.count,0))}</small></div>
      <div class="row"><select class="in" data-brk="${esc(x.id)}" title="Брокер счёта: тарифы Т-Инвестиций считаются только для счетов Т-Инвестиций" style="width:auto">${Object.entries(cfg.brokers||{}).map(([k,v])=>`<option value="${k}"${k===x.broker_id?' selected':''}>${esc(v)}</option>`).join('')}</select><button class="btn ghost" data-open="${esc(x.id)}">Открыть</button><button class="btn danger" data-del="${esc(x.id)}">Удалить</button></div></div>`).join('')}</div>`:'<div class="empty" style="padding:20px">Пока ничего не импортировано</div>'}</div></div>`;
  const msg=(t,k)=>{$('#imsg').innerHTML=t?`<div class="msg ${k||'err'}">${t}</div>`:''};
  const drop=$('#drop'),inp=$('#ifile');
  drop.onclick=()=>inp.click();
  drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};drop.ondragleave=()=>drop.classList.remove('over');
  drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');if(e.dataTransfer.files[0])pick(e.dataTransfer.files[0])};
  inp.onchange=()=>{if(inp.files[0])pick(inp.files[0])};
  async function pick(f){
    if(f.size>60*1024*1024)return msg('Файл больше 60 МБ.');
    msg('Читаю файл…','info');
    const data=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]||'');r.onerror=rej;r.readAsDataURL(f)});
    try{const pv=await post('/api/import/preview',{filename:f.name,data});
      const t=!!pv.format,bn=IMP_BROKER[pv.format]||(pv.broker_id&&pv.broker_id!=='other'?pv.broker_name:'')||'';
      S.imp={filename:f.name,data,preview:pv,mapping:pv.mapping,name:$('#iname').value||(t?bn||pv.title:f.name.replace(/\.[^.]+$/,'')),broker:$('#ibroker').value||bn,
        target:t&&pv.targets&&pv.targets.length?pv.targets[0].id:$('#itarget').value};msg('');renderImport()}
    catch(e){msg(esc(e.message))}
  }
  $('#itarget').onchange=e=>{if(S.imp)S.imp.target=e.target.value};
  if(tb){
    document.querySelectorAll('[data-tbc]').forEach(b=>b.onclick=async()=>{
      document.querySelectorAll('[data-tbc]').forEach(x=>x.disabled=true);b.textContent='Импортирую…';
      try{const res=await post('/api/import/commit',{filename:im.filename,data:im.data,name:$('#iname').value||im.name,broker:$('#ibroker').value,target:b.dataset.tbc});
        S.imp=null;S.account=res.id;S.data=S.bonds=S.hist=null;persist();
        await renderImport();msg(`Импортировано операций: ${res.count}${res.total!==res.count?` (всего в портфеле: ${res.total})`:''}. Бумаг найдено на бирже: ${res.resolved} из ${res.idents}.`,'ok');load(true)}
      catch(err){document.querySelectorAll('[data-tbc]').forEach(x=>x.disabled=false);await renderImport();msg(esc(err.message))}})
  }
  if(im&&im.preview&&!tb){
    document.querySelectorAll('[data-role]').forEach(s=>{const v=im.mapping[s.dataset.role];s.value=v==null?'':String(v);s.onchange=()=>{im.mapping[s.dataset.role]=s.value===''?null:+s.value}});
    const req=()=>({filename:im.filename,data:im.data,table:im.preview.table,header_row:im.preview.header_row,mapping:im.mapping});
    $('#iparse').onclick=async e=>{const b=e.currentTarget;b.disabled=true;
      try{const r=await post('/api/import/parse',req());const K={buy:'покупок',sell:'продаж',coupons:'купонов',dividends:'дивидендов',deposits:'пополнений',withdrawals:'выводов',fee_broker:'комиссий',tax_trade:'налогов',repayments:'погашений',fee_service:'обслуживание',margin_fee:'маржа'};
        $('#iresult').innerHTML=`<div class="msg ${r.count?'ok':'err'}">Распознано операций: <b>${r.count}</b>${r.skipped?`, пропущено строк: ${r.skipped}`:''}${r.from?` · с ${ddm(r.from)} по ${ddm(r.to)}`:''}<br>${Object.entries(r.kinds).map(([k,v])=>`${K[k]||k}: ${v}`).join(' · ')}</div>
          <div class="tbl" style="margin-top:10px;border:1px solid var(--line)"><table><thead><tr><th class="l">Дата</th><th class="l">Тип</th><th class="l">Инструмент</th><th>Кол-во</th><th>Сумма</th></tr></thead><tbody>${r.sample.map(x=>`<tr><td class="l">${ddm(x[0])}</td><td class="l"><span class="tag">${esc(OPN[x[1]]||x[1])}</span></td><td class="l">${esc(x[2])}</td><td class="num">${x[3]||''}</td><td class="num ${cls(x[4])}">${SM(x[4],x[5])}</td></tr>`).join('')}</tbody></table></div>
          ${r.count?'<div class="row" style="margin-top:14px"><button class="btn" id="icommit">Импортировать</button><span class="note">Бумаги будут найдены через API Т-Инвестиций — это займёт несколько секунд.</span></div>':''}`;
        const c=$('#icommit');if(c)c.onclick=async ev=>{const bb=ev.currentTarget;bb.disabled=true;bb.textContent='Импортирую…';
          try{const res=await post('/api/import/commit',{...req(),name:$('#iname').value||im.name,broker:$('#ibroker').value,target:$('#itarget').value});
            S.imp=null;S.account=res.id;S.data=S.bonds=S.hist=null;persist();
            await renderImport();msg(`Импортировано операций: ${res.count}. Бумаг найдено на бирже: ${res.resolved} из ${res.idents}.`,'ok');load(true)}
          catch(err){bb.disabled=false;bb.textContent='Импортировать';msg(esc(err.message))}}}
      catch(err){$('#iresult').innerHTML=`<div class="msg err">${esc(err.message)}</div>`}finally{b.disabled=false}};
  }
  document.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{if(!confirm('Удалить импортированный счёт и его операции из локальной базы?'))return;
    await post('/api/import/delete',{id:b.dataset.del});if(S.account===b.dataset.del)S.account='all';S.data=S.bonds=S.hist=null;persist();renderImport();load(true)});
  document.querySelectorAll('[data-brk]').forEach(s=>s.onchange=async()=>{
    try{await post('/api/import/broker',{id:s.dataset.brk,broker_id:s.value});S.data=null;msg('Брокер счёта сохранён.','ok');load(true)}catch(e){msg(esc(e.message))}});
  document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{S.account=b.dataset.open;S.bonds=S.hist=null;persist();S.page='dash';renderNav();load(false)});
}

