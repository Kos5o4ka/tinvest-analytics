/* ── Клавиатура для таблиц: j/k, Пробел (★), Enter, f, v, / ── */
const SKB={key:null};
function kbBlocked(e){
  if(e.ctrlKey||e.metaKey||e.altKey||e.defaultPrevented)return true;
  const a=document.activeElement,t=a&&a.tagName;
  if(t==='TEXTAREA'||t==='SELECT'||(t==='INPUT'&&!/^(checkbox|radio|button|submit|reset|range|file|color)$/.test(a.type))||(a&&a.isContentEditable))return true;
  if(document.querySelector('#bc-ov,#kp-ov,#ks-ov,#login-ov,#pro-ov,[aria-modal="true"]'))return true;
  return false;
}
const kbRows=()=>[...document.querySelectorAll('#view table tbody tr[data-isin], #view table tbody tr[data-stk]')];
const kbId=tr=>tr.dataset.isin||tr.dataset.stk;
function kbSet(tr){
  document.querySelectorAll('.kb-row').forEach(x=>x.classList.remove('kb-row'));
  SKB.key=tr?kbId(tr):null;
  if(tr){tr.classList.add('kb-row');tr.scrollIntoView({block:'nearest'})}
}
document.addEventListener('keydown',e=>{
  if(kbBlocked(e))return;
  const k=e.key,onScr=S.page==='scr'&&S.scrTab==='scr'&&S.scr&&!S.scr.error&&$('#scr-body');
  if(k==='/'){if(typeof kpOpen==='function'){e.preventDefault();kpOpen()}return}
  if(onScr&&(k==='v'||k==='V')){e.preventDefault();const m=SCR_DENS.map(x=>x[0]);scrSetDens(m[(m.indexOf(S.scrDens)+1)%m.length]);return}
  if(onScr&&(k==='f'||k==='F')){e.preventDefault();scrCycleType();return}
  const rows=kbRows();if(!rows.length)return;
  const cur=rows.findIndex(r=>kbId(r)===SKB.key);
  if(k==='j'||k==='J'||k==='k'||k==='K'||((k==='ArrowDown'||k==='ArrowUp')&&cur>=0)){
    e.preventDefault();
    const dn=k==='j'||k==='J'||k==='ArrowDown';
    kbSet(rows[cur<0?(dn?0:rows.length-1):Math.max(0,Math.min(rows.length-1,cur+(dn?1:-1)))]);return;
  }
  if(cur<0)return;
  if(k===' '||k==='Spacebar'){const st=rows[cur].querySelector('[data-wstar]');if(st){e.preventDefault();st.click()}return}
  if(k==='Enter'){e.preventDefault();rows[cur].click()}
});
