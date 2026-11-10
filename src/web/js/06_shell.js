/* ── shell ── */
function renderNav(){
  $('#nav').innerHTML=PAGES.map(p=>p?`<button class="${p[0]===S.page?'on':''}" data-p="${p[0]}">${svgI(IC[p[0]])}${p[1]}</button>`:'<div class="sep"></div>').join('');
  $('#period').innerHTML=PERIODS.map(([k,t])=>`<button class="${k===S.period?'on':''}" data-k="${k}">${t}</button>`).join('');
  $('#period').style.visibility=PERIOD_PAGES.includes(S.page)?'visible':'hidden';
  const a=S.accounts.find(x=>x.id===S.account);
  $('#title').innerHTML=esc(PAGES.find(p=>p&&p[0]===S.page)[1])+(['imp','set'].includes(S.page)?'':` <small>${esc(S.account==='all'?'все счета':a?a.name:'')}</small>`);
}
function renderAccounts(){
  const accs=S.accounts||[];
  const vis=accs.filter(a=>!S.hideEmpty||!a.empty||a.id===S.account);
  const all=accs.filter(a=>!a.empty).reduce((s,a)=>s+(a.total||0),0);
  $('#hideEmpty').checked=S.hideEmpty;
  $('#acl').innerHTML=(accs.length>1?`<button class="all ${S.account==='all'?'on':''}" data-a="all"><b>Все счета</b><span class="num">${short(all)}</span><small>${accs.filter(a=>!a.empty).length} с активами</small></button>`:'')+
    vis.map(a=>`<button class="${a.id===S.account?'on':''}" data-a="${esc(a.id)}"><b title="${esc(a.name)}">${esc(a.name)}</b><span class="num">${a.empty?'пусто':short(a.total)}</span>
      <small>${a.kind==='import'?'<em>импорт</em>':''}${a.type?`<em>${esc(a.type)}</em>`:''}${a.closed?'<em>закрыт</em>':''}</small></button>`).join('')+
    (S.hideEmpty&&vis.length<accs.length?`<div class="note" style="padding:4px 10px">Скрыто пустых: ${accs.length-vis.length}</div>`:'');
}
$('#nav').onclick=e=>{const b=e.target.closest('[data-p]');if(!b)return;go(b.dataset.p)};
$('#period').onclick=e=>{const b=e.target.closest('[data-k]');if(!b||b.dataset.k===S.period)return;S.period=b.dataset.k;persist();renderNav();load(false,true)};
$('#acl').onclick=e=>{const b=e.target.closest('[data-a]');if(!b||b.dataset.a===S.account)return;S.account=b.dataset.a;S.bonds=S.hist=null;persist();renderAccounts();renderNav();load(false)};
$('#hideEmpty').onchange=e=>{S.hideEmpty=e.target.checked;persist();renderAccounts()};
$('#refresh').onclick=()=>load(true);
function go(p){S.page=p;S.opsN=200;persist();renderNav();render()}

let reqId=0;
async function load(force,periodOnly){
  const my=++reqId;S.loading=true;S.err=null;
  $('#refresh').classList.add('spin');$('#refresh').disabled=true;
  if(!S.data&&!['set','imp'].includes(S.page))skeleton();
  try{
    const p=new URLSearchParams({period:S.period,account:S.account});if(force)p.set('force','1');
    const d=await api('/api/summary?'+p);
    if(my!==reqId)return;
    S.data=d;S.accounts=d.accounts;if(S.account!==d.account){S.account=d.account}persist();
    $('#upd').textContent='обновлено в '+d.updated;
    renderAccounts();renderNav();
    if(!periodOnly||force||!S.bonds||!S.hist)loadExtra(force);
  }catch(e){if(my!==reqId)return;S.err=e.message}
  finally{if(my===reqId){S.loading=false;$('#refresh').classList.remove('spin');$('#refresh').disabled=false}}
  if(my===reqId&&!['set','imp'].includes(S.page))render();
}
function loadExtra(force){
  const acc=S.account,p=new URLSearchParams({account:acc});if(force)p.set('force','1');
  if(force){S.bonds=null;S.hist=null}
  if(!S.bonds)api('/api/bonds?'+p).then(b=>{if(S.account!==acc)return;S.bonds=b;notifyUpcoming();if(['dash','bonds','pay'].includes(S.page))render()}).catch(e=>{if(S.account!==acc)return;S.bonds={error:e.message};if(['bonds','pay'].includes(S.page))render()});
  if(!S.hist)api('/api/history?'+p).then(h=>{if(S.account!==acc)return;S.hist=h;if(['dash','ret'].includes(S.page))render()}).catch(e=>{if(S.account!==acc)return;S.hist={error:e.message,days:[]};if(['dash','ret'].includes(S.page))render()});
}
function skeleton(){
  $('#view').innerHTML=`<div class="wrap"><div class="sk" style="height:130px"></div><div class="g g6">${'<div class="sk" style="height:96px"></div>'.repeat(6)}</div>
  <div class="g c-2-1"><div class="sk" style="height:320px"></div><div class="sk" style="height:320px"></div></div></div>`;
}
function render(){
  S.charts=[];hideTip();prInfo();
  const v=$('#view');
  if(S.page==='set')return renderSettings();
  if(S.page==='imp')return renderImport();
  if(S.err&&!S.data){v.innerHTML=`<div class="wrap"><div class="card empty fade">${svgI('<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>')}
    <div style="max-width:640px">${esc(S.err)}</div><div class="row" style="justify-content:center"><button class="btn" id="retry">Повторить</button>
    <button class="btn ghost" data-go="set">Настройки</button><button class="btn ghost" data-go="imp">Импорт отчёта</button></div></div></div>`;
    $('#retry').onclick=()=>load(true);v.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>go(b.dataset.go));return}
  if(!S.data){if(S.loading)skeleton();return}
  const sc=v.scrollTop;
  v.innerHTML=`<div class="wrap fade">${S.err?`<div class="msg err">${esc(S.err)}</div>`:''}${['dash','pay'].includes(S.page)?remindHtml():''}${({dash:pDash,ret:pRet,pos:pPos,bonds:pBonds,pay:pPay,ops:pOps,fees:pFees,tax:pTax,reb:pReb,mkt:pMkt,scr:pScr,map:pMap,pri:pPri})[S.page]()}</div>`;
  v.scrollTop=sc;
  mountCharts();bindPage();
}

