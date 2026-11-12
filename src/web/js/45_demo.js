/* ── Демо-режим: модельный портфель без токена. Плашка на каждой странице + вход/выход ── */
const DEMO={on:false,at:0,busy:false};
function demoReset(){S.data=S.bonds=S.hist=S.today=null;S.account='all';persist()}
async function demoEnter(btn){
  if(DEMO.busy)return;DEMO.busy=true;if(btn){btn.disabled=true;btn.textContent='Готовлю демо…'}
  try{
    await post('/api/demo/enable');
    DEMO.on=true;DEMO.at=Date.now();demoReset();S.page='dash';persist();
    try{S.cfg=await api('/api/config')}catch(e){}
    renderNav();demoBar();load(true);
  }catch(e){if(btn){btn.disabled=false;btn.textContent='Посмотреть демо-портфель'}alert('Не удалось включить демо: '+(e&&e.message||e))}
  finally{DEMO.busy=false}
}
async function demoExit(){
  if(DEMO.busy)return;DEMO.busy=true;
  try{
    await post('/api/demo/disable');
    DEMO.on=false;demoReset();ob.skip=false;ob.done=false;
    try{S.cfg=await api('/api/config')}catch(e){}
    S.accounts=[];S.page='set';persist();demoBar();renderAccounts();renderNav();renderSettings();
  }catch(e){alert('Не удалось выйти из демо: '+(e&&e.message||e))}
  finally{DEMO.busy=false}
}
function demoBar(){
  let el=document.getElementById('demo-bar');
  if(!DEMO.on){if(el)el.remove();return}
  if(!el){
    el=document.createElement('div');el.id='demo-bar';el.className='noprint';el.setAttribute('role','status');
    const v=document.getElementById('view');v.parentNode.insertBefore(el,v);
    el.onclick=e=>{
      const b=e.target.closest('button[data-d]');if(!b)return;
      if(b.dataset.d==='exit')demoExit();
      else if(b.dataset.d==='tok'){go('set')}
    };
  }
  el.innerHTML=`<span class="dm-t"><b>Демо-режим:</b> модельный портфель, не ваши данные</span><span class="dm-b"><button class="btn ghost" data-d="tok">Ввести токен</button><button class="btn" data-d="exit">Выйти из демо</button></span>`;
}
/* состояние демо подтягиваем при каждой перерисовке навигации (не чаще раза в 4 секунды) */
function demoSync(){
  if(Date.now()-DEMO.at<4000)return;DEMO.at=Date.now();
  api('/api/demo/status').then(r=>{
    const on=!!(r&&r.active);
    if(on!==DEMO.on){
      const was=DEMO.on;DEMO.on=on;demoBar();
      if(was&&!on){demoReset();load(true)}   /* демо убрано сервером (реальный токен или отчёт) */
    }
  }).catch(()=>{});
}
const _renderNavDemo=renderNav;
renderNav=function(){_renderNavDemo.apply(this,arguments);demoBar();demoSync()};
