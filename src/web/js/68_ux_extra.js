/* ── Дополнения интерфейса: колокольчик уведомлений в шапке, клавиатура для кликабельных карточек ── */

/* Enter / пробел на кликабельной карточке показателя открывает раздел */
document.addEventListener('keydown',e=>{
  if(e.key!=='Enter'&&e.key!==' ')return;
  const k=e.target.closest&&e.target.closest('.kpi-go');
  if(!k||e.target!==k)return;
  e.preventDefault();go(k.dataset.go);
});

/* ── Колокольчик: тревоги мониторинга, открытые оферты и ближайшие выплаты ── */
const BELL={open:false,tries:0};
function bellItems(){
  const out=[];
  const m=S.mon&&S.mon.data;
  if(m&&m.alerts)m.alerts.filter(a=>a.severity!=='info').slice(0,6).forEach(a=>out.push({sev:a.severity,html:monAlertHtml(a),go:'mon'}));
  const d=S.today&&S.today.data;
  if(d&&!d.empty){
    if(d.offers&&d.offers.items)d.offers.items.filter(o=>o.status==='open').slice(0,3).forEach(o=>out.push({sev:'medium',html:`<div class="bell-it">${tdOfferText(o)}</div>`,go:'off'}));
    if(d.payments&&d.payments.count)out.push({sev:'info',html:`<div class="bell-it">На ближайшие ${d.payments.days} дн.: <b class="num pos">${M(d.payments.sum,'rub',0)}</b> · ${d.payments.count} ${obPl(d.payments.count,'выплата','выплаты','выплат')}</div>`,go:'pay'});
  }
  return out;
}
function bellCount(){return bellItems().filter(x=>x.sev==='high'||x.sev==='medium').length}
function bellDraw(){
  const w=document.getElementById('bell-wrap');if(!w)return;
  const show=!!(S.data&&S.data.portfolio);
  w.style.display=show?'':'none';
  if(!show)return;
  const n=bellCount(),b=document.getElementById('bell');
  b.classList.toggle('has',n>0);
  b.querySelector('.bell-n').textContent=n>9?'9+':String(n||'');
  b.setAttribute('aria-label',n?`Уведомления: ${n}`:'Уведомления');
  const dd=document.getElementById('bell-dd');
  if(BELL.open){
    const it=bellItems();
    dd.innerHTML=`<div class="bell-h">Уведомления</div>`+(it.length?it.map(x=>`<button type="button" class="bell-row" data-bgo="${x.go}">${x.html}</button>`).join(''):'<div class="bell-empty mu">Новых событий нет: значимых тревог и открытых оферт по портфелю сейчас нет.</div>')
      +`<div class="bell-f"><button type="button" class="btn ghost" data-bgo="mon">Мониторинг</button><button type="button" class="btn ghost" data-bgo="cal">Календарь событий</button></div>`;
    dd.hidden=false;
  }else dd.hidden=true;
  b.setAttribute('aria-expanded',BELL.open?'true':'false');
}
function bellRefresh(){
  if(!(S.data&&S.data.portfolio)){bellDraw();return}
  let busy=false;
  try{todayEnsure();if(S.today&&S.today.loading)busy=true}catch(e){}
  try{if(S.bonds&&S.bonds.rows&&S.bonds.rows.length){monEnsure();if(S.mon&&S.mon.loading)busy=true}}catch(e){}
  bellDraw();
  if(busy&&BELL.tries<6){BELL.tries++;setTimeout(bellRefresh,2000)}
}
(()=>{
  const srch=document.getElementById('srch');if(!srch)return;
  const w=document.createElement('div');w.className='more-wrap bell-wrap';w.id='bell-wrap';w.style.display='none';
  w.innerHTML=`<button class="btn ghost" id="bell" type="button" title="Уведомления: тревоги, оферты, выплаты" aria-label="Уведомления" aria-haspopup="true" aria-expanded="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 16v-5a6 6 0 0 0-12 0v5l-2 3h16z"/><path d="M10 21h4"/></svg><span class="bell-n"></span></button><div class="more-dd bell-dd noprint" id="bell-dd" hidden></div>`;
  srch.parentNode.insertBefore(w,srch);
  w.addEventListener('click',e=>{
    const g=e.target.closest('[data-bgo]');
    if(g){BELL.open=false;bellDraw();go(g.dataset.bgo);return}
    if(e.target.closest('#bell')){BELL.open=!BELL.open;if(BELL.open)bellRefresh();else bellDraw()}
  });
  document.addEventListener('click',e=>{if(BELL.open&&!e.target.closest('#bell-wrap')){BELL.open=false;bellDraw()}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&BELL.open){BELL.open=false;bellDraw()}});
  const _rn=renderNow;
  renderNow=function(){const r=_rn.apply(this,arguments);try{BELL.tries=0;bellRefresh()}catch(e){}return r};
})();
