/* ── напоминания о выплатах ── */
function upcoming(){
  const n=S.cfg&&S.cfg.notify_days!=null?+S.cfg.notify_days:7,b=S.bonds;if(!n||!b||b.error)return[];
  const from=new Date().toISOString().slice(0,10),to=new Date(Date.now()+n*864e5).toISOString().slice(0,10);
  const ev=(b.payments||[]).filter(p=>p.date>=from&&p.date<=to).map(p=>({date:p.date,name:p.name,kind:p.kind,amount:p.amount}));
  (b.rows||[]).forEach(r=>{if(r.call&&r.call>=from&&r.call<=to)ev.push({date:r.call,name:r.name,kind:'offer',amount:null})});
  return ev.sort((a,c)=>a.date.localeCompare(c.date));
}
const EVK={coupon:'купон',dividend:'дивиденд',redemption:'погашение',offer:'оферта'};
function remindHtml(){
  const ev=upcoming();if(!ev.length)return'';
  return`<div class="card remind noprint"><div>${svgI(IC.pay,1.8).replace('<svg','<svg width="22" height="22"')}</div><div><b>Ближайшие события (${ev.length})</b>
    ${ev.slice(0,6).map(e=>`<small>${ddm(e.date)} · ${EVK[e.kind]||e.kind} · ${esc(e.name)}${e.amount!=null?' · '+M(e.amount):''}</small>`).join('')}
    ${ev.length>6?`<small>…и ещё ${ev.length-6}</small>`:''}</div></div>`;
}
function notifyUpcoming(){
  try{monEnsure()}catch(e){}
  try{
    if(!('Notification' in window)||Notification.permission!=='granted')return;
    const seen=new Set(JSON.parse(lsGet('ta_notified')||'[]'));
    upcoming().forEach(e=>{const k=e.date+'|'+e.kind+'|'+e.name;if(seen.has(k))return;seen.add(k);
      new Notification('T-Invest: '+(EVK[e.kind]||e.kind)+' '+ddm(e.date),{body:e.name+(e.amount!=null?' · '+M(e.amount):'')})});
    localStorage.setItem('ta_notified',JSON.stringify([...seen].slice(-300)));
  }catch(e){}
}


function notifyMon(d){
  try{
    if(!('Notification' in window)||Notification.permission!=='granted')return;
    const seen=new Set(JSON.parse(lsGet('ta_notified')||'[]'));
    (d.alerts||[]).filter(a=>a.severity==='high').forEach(a=>{const k='mon|'+a.id;if(seen.has(k))return;seen.add(k);
      new Notification('T-Invest: тревога по '+(a.name||'облигации'),{body:a.message})});
    localStorage.setItem('ta_notified',JSON.stringify([...seen].slice(-300)));
  }catch(e){}
}
