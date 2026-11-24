/* ── устаревшая оболочка приложения: новая иконка и экран запуска приходят только со скачанным .app/.exe ── */
async function shellNotice(){
  let s;try{s=await api('/api/shell')}catch(e){return}
  if(!s||!s.outdated)return;
  try{if(sessionStorage.getItem('shell_later'))return}catch(e){}
  if(document.getElementById('shell-bar'))return;
  const bar=document.createElement('div');bar.id='shell-bar';bar.className='noprint';
  const href=s.asset?`https://github.com/Kos5o4ka/tinvest-analytics/releases/latest/download/${encodeURIComponent(s.asset)}`:s.url;
  bar.innerHTML=`<span><b>Доступна новая версия приложения.</b> Программа обновилась сама, а новая иконка и экран запуска придут, когда вы скачаете приложение заново и замените старое.</span>
    <span class="sb-b"><a class="btn" href="${esc(href)}" target="_blank" rel="noopener noreferrer">Скачать</a><a class="btn ghost" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">Что нового</a><button class="btn ghost" id="shell-later">Позже</button></span>`;
  const top=document.querySelector('main .top');if(!top)return;
  top.insertAdjacentElement('afterend',bar);
  bar.querySelector('#shell-later').onclick=()=>{try{sessionStorage.setItem('shell_later','1')}catch(e){}bar.remove()};
}
setTimeout(shellNotice,1500);
