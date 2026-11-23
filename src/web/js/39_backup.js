/* ── Зашифрованная резервная копия и экспорт ── */
/* постоянная плашка: копия принята, но применится только при следующем запуске */
function restoreBar(on){
  let b=document.getElementById('restore-bar');
  if(!on){if(b)b.remove();return}
  if(b)return;
  b=document.createElement('div');b.id='restore-bar';b.className='msg err';b.setAttribute('role','alert');
  b.innerHTML='<b>Копия будет применена при следующем запуске программы — перезапустите её.</b> До перезапуска на экране показаны прежние данные.';
  const v=document.getElementById('view');v.parentNode.insertBefore(b,v);
}
setTimeout(()=>{api('/api/backup/status').then(s=>restoreBar(!!(s&&s.restore_pending))).catch(()=>{})},2500);
