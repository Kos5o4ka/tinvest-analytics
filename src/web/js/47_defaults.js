/* ── Техдефолты: лента неисполненных обязательств эмитентов (сообщения раскрытия, сервер данных) + флаги Мосбиржи по бумагам портфеля ── */
S.dfl={days:30,status:'all',data:null,loading:false,key:null};
const DFL_ST={technical:['Технический дефолт','dfl-t'],default:['Дефолт','dfl-d']};
function loadDfl(force){
  const D=S.dfl,key=D.days+'|'+S.account;if(D.loading)return;D.loading=true;
  const p=new URLSearchParams({days:D.days,account:S.account});if(force)p.set('force','1');
  api('/api/defaults?'+p).then(j=>{D.data=j;D.key=key}).catch(e=>{D.data={error:e.message||String(e),rows:[]};D.key=key})
   .then(()=>{D.loading=false;if(S.page==='dfl')render()});
}
function pDfl(){
  const D=S.dfl,key=D.days+'|'+S.account;
  let h=`<div class="card"><h2>Техдефолты<span class="sp">неисполненные в срок обязательства по облигациям</span></h2>
    <div class="dfl-bar"><div class="seg" id="dfl-days">${[[7,'7 дней'],[30,'30 дней'],[90,'90 дней']].map(([n,t])=>`<button data-d="${n}" class="${D.days===n?'on':''}">${t}</button>`).join('')}</div>
    <div class="seg" id="dfl-st">${[['all','Все'],['technical','Технический дефолт'],['default','Дефолт']].map(([k,t])=>`<button data-st="${k}" class="${D.status===k?'on':''}">${t}</button>`).join('')}</div></div>`;
  if(D.key!==key&&!D.loading){D.data=null;loadDfl()}
  if(!D.data||D.key!==key)return h+waitBox('Загружаю ленту…')+`</div>`;
  const d=D.data;
  if(d.error)return h+`<div class="msg err">${esc(d.error)}</div></div>`;
  const rows=(d.rows||[]).filter(r=>D.status==='all'||r.status===D.status);
  if(!d.configured)h+=`<div class="msg" style="margin:10px 0">Сервер данных не подключён: сообщения эмитентов недоступны. Ниже только флаги Мосбиржи по бумагам портфеля и списка наблюдения. Подключить сервер можно в настройках.</div>`;
  if(!rows.length)return h+`<div class="empty" style="padding:28px 12px">${d.configured?'За выбранный период неисполненных обязательств не найдено.':'Нет данных для показа.'}</div></div>`;
  h+=`<div class="tbl dfl-wrap"><table id="dfl-tab"><thead><tr><th class="l">Дата</th><th class="l">Статус</th><th class="l">Эмитент · бумага</th><th class="l">Обязательство</th><th>Сумма</th><th class="l">Исполнение</th><th class="l">Основание</th></tr></thead><tbody>`
    +rows.map(r=>{const st=DFL_ST[r.status]||DFL_ST.technical;
      return`<tr${r.isin?` data-isin="${esc(r.isin)}"`:''}><td class="l">${r.date?ddm(r.date):'—'}</td><td class="l"><span class="dfl-b ${st[1]}">${st[0]}</span></td>
        <td class="l dfl-is"><b>${esc(r.issuer||'—')}</b><br><small class="mu num">${r.isin?esc(r.isin):''}${r.isin&&r.inn?' · ':''}${r.inn?'ИНН '+esc(r.inn):''}</small></td>
        <td class="l">${esc(r.obligation||'—')}${r.due_date?`<br><small class="mu">срок ${ddm(r.due_date)}</small>`:''}</td><td class="num">${r.amount==null?'—':short(r.amount)+' ₽'}</td>
        <td class="l">${r.executed?`<span class="pos">исполнено ${ddm(r.executed)}</span>`:'<span class="mu">нет данных</span>'}</td>
        <td class="l dfl-bs">${r.url?`<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.basis)} ↗</a>`:esc(r.basis||'')}</td></tr>`}).join('')+`</tbody></table></div>`;
  return h+`<p class="note" style="margin-top:10px">Технический дефолт — просрочка платежа до 10 рабочих дней, затем дефолт. «Исполнение» подбирается по раскрытию о выплате: для купона — с тем же номером, для амортизации и погашения — по выплате того же вида после срока. Справочная информация, не инвестиционная рекомендация. <button class="btn ghost" id="dfl-ref" style="padding:3px 10px;font-size:12px;margin-left:6px">Обновить</button></p></div>`;
}
function bindDfl(){
  const D=S.dfl,d=$('#dfl-days'),s=$('#dfl-st'),r=$('#dfl-ref');
  if(d)d.onclick=e=>{const b=e.target.closest('[data-d]');if(!b)return;D.days=+b.dataset.d;D.data=null;render()};
  if(s)s.onclick=e=>{const b=e.target.closest('[data-st]');if(!b)return;D.status=b.dataset.st;render()};
  if(r)r.onclick=()=>{D.data=null;D.key=null;loadDfl(true);render()};
}
