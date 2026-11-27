/* ── Техдефолты: лента неисполненных обязательств эмитентов (сообщения раскрытия, сервер данных) + флаги Мосбиржи (портфель или весь рынок) ── */
S.dfl={days:30,status:'all',scope:(lsGet('dfl_scope')==='market'?'market':'my'),data:null,loading:false,key:null,tm:null};
const DFL_ST={technical:['Технический дефолт','dfl-t'],default:['Дефолт','dfl-d']};
function dflKey(){const D=S.dfl;return D.days+'|'+D.scope+'|'+S.account}
function loadDfl(force,quiet){
  const D=S.dfl,key=dflKey();if(D.loading)return;D.loading=true;clearTimeout(D.tm);
  const p=new URLSearchParams({days:D.days,account:S.account,scope:D.scope});if(force)p.set('force','1');
  api('/api/defaults?'+p).then(j=>{const prev=D.data&&D.data.rows?D.data.rows.length:-1;D.data=j;D.key=key;D.chg=prev!==(j.rows||[]).length||!quiet}).catch(e=>{D.data={error:e.message||String(e),rows:[]};D.key=key;D.chg=true})
   .then(()=>{D.loading=false;if(S.page!=='dfl')return;
     const sc=D.data&&D.data.scan;
     if(sc&&sc.running){
       if(D.chg||!$('#dfl-prog'))render();else dflProg();
       D.tm=setTimeout(()=>{if(S.page==='dfl'&&D.key===dflKey())loadDfl(false,true)},3000);
     }else render()});
}
const dflPl=(n,f)=>{const a=n%10,b=n%100;return a===1&&b!==11?f[0]:a>=2&&a<=4&&(b<10||b>=20)?f[1]:f[2]};
function dflProg(){const e=$('#dfl-prog'),sc=S.dfl.data&&S.dfl.data.scan;if(e&&sc)e.textContent='Проверяю выпуски Мосбиржи: '+sc.done+' из '+sc.total}
function dflRows(rows,since){
  return`<div class="tbl dfl-wrap"><table class="dfl-tab"><thead><tr><th class="l">Дата</th><th class="l">Статус</th><th class="l">Эмитент · бумага</th><th class="l">Обязательство</th><th>Сумма</th><th class="l">Исполнение</th><th class="l">Основание</th></tr></thead><tbody>`
  +rows.map(r=>{const st=DFL_ST[r.status]||DFL_ST.technical;
    const dt=r.date?ddm(r.date)+(r.date_est?` <small class="mu dfl-est" title="Дата оценена по графику выплат Мосбиржи: последняя плановая выплата до сегодняшнего дня. Фактическую дату неисполнения эмитент мог раскрыть иначе.">по графику</small>`:''):'—';
    const ru=safeUrl(r.url);
    return`<tr${r.isin?` data-isin="${esc(r.isin)}" title="Открыть карточку выпуска"`:''}><td class="l">${dt}</td><td class="l"><span class="dfl-b ${st[1]}">${st[0]}</span></td>
      <td class="l dfl-is"><b>${esc(r.issuer||'—')}</b>${r.mine?' <span class="tag">мой</span>':''}<br><small class="mu num">${r.isin?esc(r.isin):''}${r.isin&&r.inn?' · ':''}${r.inn?'ИНН '+esc(r.inn):''}</small></td>
      <td class="l">${esc(r.obligation||'—')}${r.due_date&&!r.date_est?`<br><small class="mu">срок ${ddm(r.due_date)}</small>`:''}</td><td class="num">${r.amount==null?'—':short(r.amount)+' ₽'}</td>
      <td class="l">${r.executed?`<span class="pos">исполнено ${ddm(r.executed)}</span>`:'<span class="mu">нет данных</span>'}</td>
      <td class="l dfl-bs">${ru?`<a href="${esc(ru)}" target="_blank" rel="noopener">${esc(r.basis)} ↗</a>`:esc(r.basis||'')}</td></tr>`}).join('')+`</tbody></table></div>`;
}
function pDfl(){
  const D=S.dfl,key=dflKey();
  let h=`<div class="card"><h2>Техдефолты<span class="sp">неисполненные в срок обязательства по облигациям</span></h2>
    <div class="dfl-bar"><div class="seg" id="dfl-scope">${[['my','Мой портфель'],['market','Весь рынок']].map(([k,t])=>`<button data-sc="${k}" class="${D.scope===k?'on':''}">${t}</button>`).join('')}</div>
    <div class="seg" id="dfl-days">${[[7,'7 дней'],[30,'30 дней'],[90,'90 дней']].map(([n,t])=>`<button data-d="${n}" class="${D.days===n?'on':''}">${t}</button>`).join('')}</div>
    <div class="seg" id="dfl-st">${[['all','Все'],['technical','Технический дефолт'],['default','Дефолт']].map(([k,t])=>`<button data-st="${k}" class="${D.status===k?'on':''}">${t}</button>`).join('')}</div></div>`;
  if(D.key!==key&&!D.loading){D.data=null;loadDfl()}
  if(!D.data||D.key!==key)return h+waitBox('Загружаю ленту…')+`</div>`;
  const d=D.data;
  if(d.error)return h+`<div class="msg err">${esc(d.error)}</div></div>`;
  const all=(d.rows||[]).filter(r=>D.status==='all'||r.status===D.status);
  const since=d.since||'';
  const inP=r=>r.date&&r.date>=since,main=all.filter(inP),old=all.filter(r=>!inP(r));
  const sc=d.scan;
  if(!d.configured)h+=`<div class="msg" style="margin:10px 0">Сервер данных недоступен: сообщения эмитентов не загружены. Ниже только флаги Мосбиржи.</div>`;
  if(sc&&sc.running)h+=`<div class="msg" style="margin:10px 0"><span class="dfl-spin"></span> <span id="dfl-prog">Проверяю выпуски Мосбиржи: ${sc.done} из ${sc.total}</span> — список дополняется по ходу проверки.</div>`;
  else if(sc&&sc.error)h+=`<div class="msg err" style="margin:10px 0">Обход рынка не завершён: ${esc(sc.error)}</div>`;
  const isn=new Set(all.map(r=>r.isin||r.issuer)),iss=new Set(all.map(r=>r.inn||r.issuer));
  h+=`<p class="mu" style="margin:0 0 8px" id="dfl-cnt">Найдено: ${isn.size} ${dflPl(isn.size,['выпуск','выпуска','выпусков'])}, эмитентов: ${iss.size}</p>`;
  if(!all.length)return h+`<div class="empty" style="padding:28px 12px">${d.configured?'Неисполненных обязательств не найдено.':'Нет данных для показа.'}</div></div>`;
  h+=main.length?dflRows(main,since):`<div class="empty" style="padding:18px 12px">За выбранный период новых случаев нет.</div>`;
  if(old.length)h+=`<h3 style="margin:16px 0 6px">Отмечены на Мосбирже, срок вне периода (${old.length})</h3><p class="mu" style="margin:0 0 6px">Выпуски, у которых флаг дефолта на Мосбирже действует сейчас, но последняя плановая выплата раньше выбранного периода или не определена. Они не скрываются фильтром.</p>`+dflRows(old,since);
  return h+`<p class="note" style="margin-top:10px">Технический дефолт — просрочка платежа до 10 рабочих дней, затем дефолт. Для строк «Флаг Мосбиржи» дата, обязательство и сумма оцениваются по графику выплат Мосбиржи (последняя плановая выплата) и могут не совпадать с фактической просрочкой; если по бумаге есть сообщение эмитента, показывается оно. «Исполнение» подбирается по раскрытию о выплате. Справочная информация, не инвестиционная рекомендация. <button class="btn ghost" id="dfl-ref" style="padding:3px 10px;font-size:12px;margin-left:6px">Обновить</button></p></div>`;
}
function bindDfl(){
  const D=S.dfl,d=$('#dfl-days'),s=$('#dfl-st'),r=$('#dfl-ref'),c=$('#dfl-scope');
  if(c)c.onclick=e=>{const b=e.target.closest('[data-sc]');if(!b||b.dataset.sc===D.scope)return;D.scope=b.dataset.sc;lsSet('dfl_scope',D.scope);clearTimeout(D.tm);D.data=null;render()};
  if(d)d.onclick=e=>{const b=e.target.closest('[data-d]');if(!b)return;D.days=+b.dataset.d;clearTimeout(D.tm);D.data=null;render()};
  if(s)s.onclick=e=>{const b=e.target.closest('[data-st]');if(!b)return;D.status=b.dataset.st;render()};
  if(r)r.onclick=()=>{clearTimeout(D.tm);D.data=null;D.key=null;loadDfl(true);render()};
}
