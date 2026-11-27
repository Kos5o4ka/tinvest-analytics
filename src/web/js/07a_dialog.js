/* ── Свои диалоги вместо alert/confirm: uiConfirm({title,body,danger,okText,cancelText}) → Promise<bool>, uiAlert({title,body,okText,kind}) → Promise<void> ──
   Тёмная и светлая тема (через токены), Esc и клик по фону — отмена, при опасном действии фокус на безопасной кнопке,
   Tab не выходит за окно, после закрытия фокус возвращается. Несколько вызовов подряд показываются по очереди. */
var UI_DLG_Q=[];var UI_DLG_BUSY=false;
function uiDlgNorm(o,def){if(typeof o==='string')o={body:o};return Object.assign({},def,o||{})}
function uiDlgOpen(o){
  return new Promise(resolve=>{UI_DLG_Q.push({o,resolve});if(!UI_DLG_BUSY)uiDlgNext()});
}
function uiDlgNext(){
  const it=UI_DLG_Q.shift();
  if(!it){UI_DLG_BUSY=false;return}
  UI_DLG_BUSY=true;
  const o=it.o,prev=document.activeElement;
  const ov=document.createElement('div');ov.id='ui-dlg-ov';
  const ic=o.danger?'<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/>':o.kind==='err'?'<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16h.01"/>':'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>';
  const paras=String(o.body==null?'':o.body).split(/\n{2,}/).map(t=>'<p>'+esc(t).replace(/\n/g,'<br>')+'</p>').join('');
  const id='ui-dlg-t'+Date.now();
  ov.innerHTML=`<div class="ui-dlg${o.danger?' danger':''}${o.kind==='err'?' err':''}" role="${o.confirm?'alertdialog':'dialog'}" aria-modal="true" aria-labelledby="${id}">
    <div class="ui-dlg-h"><i class="ui-dlg-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ic}</svg></i>
    <h3 id="${id}">${esc(o.title||'')}</h3></div>${paras?`<div class="ui-dlg-b">${paras}</div>`:''}
    <div class="ui-dlg-f">${o.confirm?`<button class="btn ghost" data-r="0">${esc(o.cancelText||'Отмена')}</button>`:''}<button class="btn${o.danger?' danger solid':''}" data-r="1">${esc(o.okText||(o.confirm?'Подтвердить':'Понятно'))}</button></div></div>`;
  document.body.appendChild(ov);
  let done=false;
  const close=r=>{if(done)return;done=true;window.removeEventListener('keydown',key,true);ov.classList.remove('is-in');
    setTimeout(()=>{ov.remove();try{if(prev&&prev.focus&&document.contains(prev))prev.focus()}catch(e){}it.resolve(o.confirm?!!r:undefined);uiDlgNext()},140)};
  const btns=[...ov.querySelectorAll('button[data-r]')];
  btns.forEach(b=>b.onclick=()=>close(b.dataset.r==='1'));
  ov.addEventListener('mousedown',e=>{if(e.target===ov)close(false)});
  function key(e){
    if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close(false);return}
    if(e.key==='Tab'){e.preventDefault();e.stopPropagation();const i=btns.indexOf(document.activeElement);btns[(i+(e.shiftKey?btns.length-1:1))%btns.length].focus()}
  }
  window.addEventListener('keydown',key,true);
  requestAnimationFrame(()=>{ov.classList.add('is-in');(o.danger&&o.confirm?btns[0]:btns[btns.length-1]).focus()});
}
function uiConfirm(o){return uiDlgOpen(uiDlgNorm(o,{confirm:true,title:'Подтвердите действие'}))}
function uiAlert(o){return uiDlgOpen(uiDlgNorm(o,{confirm:false,title:'Сообщение'}))}
/* ошибка запроса одним вызовом: uiErr(e) или uiErr(e,'Не удалось удалить') */
function uiErr(e,title){return uiAlert({title:title||'Ошибка',body:(e&&e.message)||String(e||''),kind:'err'})}
