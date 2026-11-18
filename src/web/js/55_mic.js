/* ── «Стакан: ликвидность»: проскальзывание крупной заявки и эвристика скрытой ликвидности (/api/mic/*) ── */
S.mic=S.mic||{secid:'SBER',side:'buy',rub:5e6,custom:'',inst:null,imp:null,ice:null,err:'',iceErr:'',busyI:false,busyC:false};
let _micTimer=null;
const MIC_SIZES=[[1e6,'1 млн ₽'],[5e6,'5 млн ₽'],[10e6,'10 млн ₽']];
const micRub=n=>bad(n)?'—':Math.round(n).toLocaleString('ru-RU')+' ₽';
const micBp=n=>bad(n)?'—':(n>=0?'':'−')+Math.abs(n).toFixed(1).replace('.',',')+' б.п.';
const micPx=p=>bad(p)?'—':(+p).toLocaleString('ru-RU',{maximumFractionDigits:4});
const micT=ts=>{try{return new Date(ts*1000).toLocaleTimeString('ru-RU',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit',second:'2-digit'})}catch(e){return''}};
function micImpactHtml(){
  const D=S.mic,d=D.imp;
  if(!d)return D.err?`<div class="msg err">${esc(D.err)}</div>`:waitBox('Считаю по стакану…');
  if(!d.ok)return`<div class="empty" style="padding:24px 12px">${esc(d.error||'Стакан недоступен')}</div>`;
  const side=d.side==='buy'?'покупка':'продажа',bandRow=(k,t)=>{const b=(d.depth_band||{})[k]||{};return`<tr><td class="l">${t}</td><td class="num">${micRub(b.bid_rub)}</td><td class="num">${micRub(b.ask_rub)}</td></tr>`};
  return`${d.warning?`<div class="msg err mic-warn">${esc(d.warning)}</div>`:''}
  <div class="mic-grid">
    <div class="card mic-c"><h2>Заявка: ${side} на ${micRub(d.target_rub)}</h2>
      <div class="mic-big">${micBp(d.slip_mid_bp)}<small class="mu"> к середине</small></div>
      <div class="mic-kv"><span>Средневзвешенная цена</span><b>${micPx(d.vwap)}${d.is_bond?' %':''}</b></div>
      <div class="mic-kv"><span>Потери относительно середины</span><b>${micRub(d.slip_mid_rub)}</b></div>
      <div class="mic-kv"><span>К лучшей цене стакана</span><b>${micBp(d.slip_best_bp)}</b></div>
      <div class="mic-kv"><span>Исполнится</span><b>${micRub(d.filled_rub)} (${(d.filled_lots||0).toLocaleString('ru-RU')} лот.)</b></div>
      <div class="mic-kv"><span>Затронуто уровней</span><b>${d.levels_used} из ${d.visible_levels}</b></div>
      <div class="mic-kv"><span>Доля видимой глубины</span><b>${bad(d.depth_share)?'—':pctp(d.depth_share*100,0)}</b></div>
      ${d.is_bond?`<div class="mic-kv"><span>Влияние на доходность (приближённо)</span><b>${bad(d.yield_bp)?'нет дюрации':micBp(d.yield_bp)}</b></div>`:''}</div>
    <div class="card mic-c"><h2>Спред и глубина</h2>
      <div class="mic-kv"><span>Лучшая покупка / продажа</span><b>${micPx(d.best_bid)} / ${micPx(d.best_ask)}</b></div>
      <div class="mic-kv"><span>Спред</span><b>${micPx(d.spread)} (${micBp(d.spread_bp)})</b></div>
      <div class="tbl" style="margin-top:8px"><table><thead><tr><th class="l">Глубина от середины</th><th>Покупка</th><th>Продажа</th></tr></thead><tbody>${bandRow('0.005','±0,5 %')}${bandRow('0.01','±1 %')}</tbody></table></div></div></div>
  <div class="card" style="margin-top:12px"><h2>Типовые размеры<span class="sp">${side}</span></h2><div class="tbl"><table><thead><tr><th class="l">Размер</th><th>Цена исполнения</th><th>Проскальзывание</th><th>Потери</th>${d.is_bond?'<th>Доходность</th>':''}<th>Статус</th></tr></thead><tbody>${(d.presets||[]).map(p=>`<tr><td class="l">${micRub(p.rub)}</td><td class="num">${micPx(p.vwap)}</td><td class="num">${micBp(p.slip_mid_bp)}</td><td class="num">${micRub(p.slip_mid_rub)}</td>${d.is_bond?`<td class="num">${bad(p.yield_bp)?'—':micBp(p.yield_bp)}</td>`:''}<td>${p.complete?'<span class="pos">хватает</span>':'<span class="neg">не хватает</span>'}</td></tr>`).join('')}</tbody></table></div></div>
  <p class="note" style="margin-top:8px">${(d.notes||[]).map(esc).join(' ')}</p>
  <div class="mic-meta"><span class="flw-src live">${esc(d.source_label||'')}</span><span class="mu">обновлено ${micT(d.ts)} МСК</span></div>`;
}
function micIceHtml(){
  const d=S.mic.ice;
  if(!d)return S.mic.iceErr?`<div class="msg err">${esc(S.mic.iceErr)}</div>`:waitBox('Наблюдаю за стаканом…');
  if(!d.ok)return`<div class="empty" style="padding:18px 12px">${esc(d.error||'Недоступно')}</div>`;
  let h='';
  if(d.status==='unavailable')h=`<div class="empty" style="padding:18px 12px">${esc(d.message)}</div>`;
  else if(d.status==='collecting')h=`<div class="empty" style="padding:18px 12px">${esc(d.message||'Накапливаю наблюдения…')} Снимков: ${d.snapshots}, наблюдаю ${d.observed_sec} с.</div>`;
  else if(!d.candidates.length)h=`<div class="empty" style="padding:18px 12px">Признаков скрытой ликвидности на лучших уровнях не найдено (проверено уровней: ${d.levels_checked}, наблюдение ${d.observed_sec} с).</div>`;
  else h=`<div class="tbl"><table><thead><tr><th class="l">Сторона</th><th>Цена</th><th>Исполнено, лот.</th><th>Макс. видимо, лот.</th><th>Видимо сейчас</th><th>Скрыто (оценка), лот.</th><th class="l">Подтверждение</th></tr></thead><tbody>${d.candidates.map(c=>`<tr><td class="l">${c.side==='ask'?'заявки на продажу':'заявки на покупку'}</td><td class="num">${micPx(c.price)}</td><td class="num">${c.executed_lots}</td><td class="num">${c.visible_max_lots}</td><td class="num">${c.visible_now_lots}</td><td class="num"><b>${c.hidden_est_lots}</b> <small class="mu">×${String(c.factor).replace('.',',')}</small></td><td class="l mic-ev"><div>стакан: ${c.evidence.book.map(b=>`${micT(b[0])}→${b[1]}`).join(', ')}</div><div>сделки: ${c.evidence.trades.map(t=>`${micT(t[0])}→${t[1]}`).join(', ')}</div><div>уровень держался в ${Math.round(c.persist*100)} % снимков</div></td></tr>`).join('')}</tbody></table></div>`;
  return h+`<p class="note" style="margin-top:8px">${esc(d.note||'')}</p><div class="mic-meta"><span class="mu">${esc(d.source_label||'')}; снимков ${d.snapshots}, окно до ${Math.round((d.window_sec||600)/60)} мин</span></div>`;
}
function micPaint(){
  if(S.page!=='mic')return;
  const a=$('#mic-imp'),b=$('#mic-ice');
  if(a)a.innerHTML=micImpactHtml();
  if(b)b.innerHTML=micIceHtml();
}
function micLoadImpact(){
  const D=S.mic;const req=(D.reqI=(D.reqI||0)+1),secid=D.secid;
  D.busyI=true;
  api('/api/mic/impact?'+new URLSearchParams({secid,side:D.side,rub:D.rub})).then(j=>{if(req===D.reqI&&secid===D.secid){D.imp=j;D.err=''}}).catch(e=>{if(req===D.reqI)D.err=e.message||String(e)})
    .then(()=>{if(req===D.reqI){D.busyI=false;micPaint()}});
}
function micLoadIce(){
  const D=S.mic;const req=(D.reqC=(D.reqC||0)+1),secid=D.secid;
  D.busyC=true;
  api('/api/mic/iceberg?'+new URLSearchParams({secid})).then(j=>{if(req===D.reqC&&secid===D.secid){D.ice=j;D.iceErr=''}}).catch(e=>{if(req===D.reqC)D.iceErr=e.message||String(e)})
    .then(()=>{if(req===D.reqC){D.busyC=false;micPaint()}});
}
function micStop(){if(_micTimer){clearInterval(_micTimer);_micTimer=null}}
function micStart(){
  micStop();micLoadImpact();micLoadIce();
  /* опрос раз в 7 с только пока открыт этот экран и вкладка видима */
  _micTimer=setInterval(()=>{if(S.page!=='mic'){micStop();return}if(document.hidden)return;micLoadImpact();micLoadIce()},7000);
}
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&S.page==='mic'&&!_micTimer)micStart()});
function micOpts(){
  const D=S.mic,opts=(D.inst||[]).slice();if(!opts.some(r=>r.secid===D.secid))opts.unshift({secid:D.secid,name:''});
  return opts.map(r=>`<option value="${esc(r.secid)}"${r.secid===D.secid?' selected':''}>${esc(r.secid)} ${esc(r.name||'')}</option>`).join('');
}
function pMic(){
  const D=S.mic;
  if(!D.inst){D.inst=[];api('/api/flows_instruments').then(j=>{D.inst=j.rows||[];const s=$('#mic-sec');if(S.page==='mic'&&s)s.innerHTML=micOpts()}).catch(()=>{})}
  return`<div class="card"><h2>Стакан: ликвидность<span class="sp">проскальзывание крупной заявки и скрытый объём</span></h2>
    <div class="flw-bar2"><label class="flw-min">Бумага <select id="mic-sec">${micOpts()}</select></label>
      <input id="mic-q" class="in" placeholder="Тикер, например SU26238RMFS4" style="width:220px;max-width:100%" value="">
      <div class="seg" id="mic-side">${[['buy','Покупка'],['sell','Продажа']].map(([k,t])=>`<button data-s="${k}" class="${D.side===k?'on':''}">${t}</button>`).join('')}</div></div>
    <div class="flw-bar2"><div class="seg" id="mic-size">${MIC_SIZES.map(([v,t])=>`<button data-v="${v}" class="${D.rub===v&&!D.custom?'on':''}">${t}</button>`).join('')}</div>
      <label class="flw-min">своя сумма, ₽ <input id="mic-cus" class="in" inputmode="numeric" placeholder="например 2500000" style="width:150px" value="${esc(D.custom)}"></label></div>
    <div id="mic-imp">${micImpactHtml()}</div></div>
  <div class="card" style="margin-top:14px"><h2>Скрытая ликвидность (айсберг)<span class="sp">эвристика по стакану и ленте сделок</span></h2><div id="mic-ice">${micIceHtml()}</div></div>
  <p class="note" style="margin-top:10px">Стакан берётся из T-Invest: через сервер данных либо по вашему токену (текущие заявки; фактическая задержка зависит от тарифа биржевых данных). Без токена стакан недоступен: бесплатные данные Мосбиржи (ISS) стакана не содержат. Расчёт аналитический и не прогнозирует исполнение реальной заявки.</p>${NIR_NOTE}`;
}
function bindMic(){
  const D=S.mic,on=(id,f)=>{const e=$(id);if(e)e.onclick=f};
  on('#mic-side',e=>{const b=e.target.closest('[data-s]');if(!b)return;D.side=b.dataset.s;D.imp=null;render()});
  on('#mic-size',e=>{const b=e.target.closest('[data-v]');if(!b)return;D.rub=+b.dataset.v;D.custom='';D.imp=null;render()});
  const sec=$('#mic-sec');if(sec)sec.onchange=e=>{D.secid=e.target.value;D.imp=null;D.ice=null;render()};
  const q=$('#mic-q');if(q)q.onkeydown=e=>{if(e.key!=='Enter')return;const v=q.value.trim().toUpperCase();if(/^[A-Z0-9_.\-]{1,24}$/.test(v)){D.secid=v;D.imp=null;D.ice=null;render()}};
  const c=$('#mic-cus');if(c)c.onkeydown=e=>{if(e.key!=='Enter')return;const v=parseFloat(c.value.replace(/\s/g,'').replace(',','.'));if(v>=1000){D.rub=v;D.custom=c.value;D.imp=null;render()}};
  micStart();
}
regPage('mic',{title:'Стакан: ликвидность',group:'Рынок',icon:'<path d="M4 5h16M4 9h12M4 15h12M4 19h16"/><path d="M12 11h8"/>',render:pMic,bind:bindMic,pro:true});
