/* ── Скачать CSV у любой таблицы данных, локальный переключатель периода, запоминание вкладки карточки ──
   taCsvText: разделитель «;», перевод строки CRLF, в начале BOM (UTF-8), чтобы Excel на Windows открыл кириллицу. Без DOM — проверяется через jsc. */
function taCsvText(headers,rows){
  const escCell=v=>{let s=v==null?'':String(v);if(/^[=@\t\r]/.test(s))s="'"+s;return/[;"\r\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s};
  return'﻿'+[headers].concat(rows).map(r=>r.map(escCell).join(';')).join('\r\n');
}
/* текст ячейки для выгрузки: без неразрывных пробелов и значков, минус как «-» */
function taCsvCell(td){
  const c=td.cloneNode(true);
  c.querySelectorAll('svg,script,style,button,.noprint,[hidden]').forEach(x=>x.remove());
  return(c.textContent||'').replace(/[   ]/g,' ').replace(/−/g,'-').replace(/\s+/g,' ').trim();
}
function taTableCsvData(table){
  const head=[...table.querySelectorAll('thead tr:last-child th')].map(taCsvCell);
  const rows=[...table.querySelectorAll('tbody tr')].filter(tr=>tr.style.display!=='none'&&!tr.hidden&&!tr.querySelector('td[colspan]'))
    .map(tr=>[...tr.children].map(taCsvCell));
  return{head:head.length?head:(rows[0]||[]).map((_,i)=>'Колонка '+(i+1)),rows};
}
function taTableCsvDownload(table,name){
  const d=taTableCsvData(table);
  taCsvDownload((name||'table')+'.csv',d.head,d.rows);
}
function taCsvFileName(card){
  const h=card&&card.querySelector('h2'),t=h?(h.firstChild&&h.firstChild.textContent||h.textContent):'';
  const s=String(t||'').trim().replace(/[\\/:*?"<>|]+/g,' ').replace(/\s+/g,'_').slice(0,50);
  return(s||'tanalytic')+'_'+localIso();
}
/* кнопка «Скачать CSV» над каждой таблицей данных (от 3 строк), если в карточке её ещё нет */
function taCsvAttach(root){
  root.querySelectorAll('table').forEach(t=>{
    if(t.closest('[data-nocsv],.noprint,.tbl-auto'))return;
    if(!t.querySelector('thead th')||t.querySelectorAll('tbody tr').length<3)return;
    const box=t.closest('.tbl')||t,card=t.closest('.card')||box.parentElement;
    if(!card||card.querySelector('.tbl-csv'))return;
    if(box.previousElementSibling&&box.previousElementSibling.classList.contains('tbl-auto'))return;
    const hd=document.createElement('div');hd.className='tbl-head tbl-auto noprint';
    hd.innerHTML=taCsvBtn('tbl-auto-'+(++_csvN),'Скачать таблицу в CSV (разделитель «;», кодировка UTF-8)');
    box.parentNode.insertBefore(hd,box);
  });
}
let _csvN=0,_csvT=0;
if(typeof document!=='undefined'&&typeof MutationObserver!=='undefined'){
  document.addEventListener('click',e=>{
    const b=e.target.closest&&e.target.closest('.tbl-auto .tbl-csv');if(!b)return;
    const hd=b.closest('.tbl-auto'),nx=hd.nextElementSibling,t=nx&&(nx.tagName==='TABLE'?nx:nx.querySelector('table'));
    if(t)taTableCsvDownload(t,taCsvFileName(hd.closest('.card')));
  });
  const csvScan=()=>{_csvT=0;['#view','#bc-ov'].forEach(s=>{const r=document.querySelector(s);if(r)try{taCsvAttach(r)}catch(e){}})};
  new MutationObserver(()=>{if(!_csvT)_csvT=setTimeout(csvScan,250)}).observe(document.body,{childList:true,subtree:true});
}
/* локальный переключатель периода в карточке графика: меняет тот же период, что и верхний (одно состояние, две кнопки) */
function periodSegLocal(){
  if(!PERIOD_PAGES.includes(S.page)||!S.data)return'';
  return`<span class="seg per-local noprint" role="group" aria-label="Период графика">${PERIODS.map(([k,t])=>`<button type="button" class="${k===S.period?'on':''}" data-k="${k}">${t}</button>`).join('')}</span>`;
}
if(typeof document!=='undefined')document.addEventListener('click',e=>{
  const b=e.target.closest&&e.target.closest('.per-local [data-k]');if(!b||b.dataset.k===S.period)return;
  S.period=b.dataset.k;persist();renderNav();load(false,true);
});
/* вкладка карточки облигации запоминается между открытиями */
function bcSavedTab(){const t=typeof lsGet==='function'?lsGet('ta_bc_tab'):null;return typeof BC_TABS!=='undefined'&&BC_TABS.some(x=>x[0]===t)?t:'overview'}
