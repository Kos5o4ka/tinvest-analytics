/* ── Деньги и базис: фонды ликвидности (доходность, отставание от ставки, после налога) и базис фьючерсов (cash & carry) ── */
S.mm={tab:'funds',f:null,b:null,fl:0,bl:0,fseq:0,q:{amount:'1000000',days:'365',fee:'0',save:'',fund:'LQDT',win:'3m'}};
const MM_WINS=[['1m','Месяц'],['3m','3 мес'],['6m','6 мес'],['1y','Год']];
const mmPc=(v,d=2)=>bad(v)?'—':v.toFixed(d).replace('.',',')+' %';
const mmPp=v=>bad(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(2).replace('.',',')+' п.п.';
const mmCls=v=>bad(v)?'':v>0?'pos':v<0?'neg':'';
const mmNum=(v,d=2)=>bad(v)?'—':v.toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
function mmQs(){return Object.entries(S.mm.q).filter(([k,v])=>String(v).trim()!=='').map(([k,v])=>k+'='+encodeURIComponent(String(v).replace(',','.'))).join('&')}
function loadMmF(){
  const m=S.mm,seq=++m.fseq;m.fl=1;
  api('/api/mm/funds?'+mmQs()).then(j=>{if(seq===m.fseq)m.f=j}).catch(e=>{if(seq===m.fseq)m.f={error:e.message||String(e),funds:[]}})
   .then(()=>{if(seq!==m.fseq)return;m.fl=0;if(S.page==='mm')renderSoon()});
}
function loadMmB(force){
  const m=S.mm;if(m.bl)return;m.bl=1;
  api('/api/mm/basis'+(force?'?force=1':'')).then(j=>{m.b=j}).catch(e=>{m.b={error:e.message||String(e),rows:[]}})
   .then(()=>{m.bl=0;if(S.page==='mm')renderSoon()});
}
function mmFundsTable(d){
  const sel=d.selected;
  const cell=w=>!w||bad(w.ret)?'<td class="num"><span class="mu">—</span></td>'
    :`<td class="num"><b>${mmPc(w.ret)}</b><br><small class="${mmCls(w.gap)}" title="${w.bench_name?'Отставание от ставки ('+esc(w.bench_name)+') за то же окно':''}">${mmPp(w.gap)}</small></td>`;
  return`<div class="tbl"><table><thead><tr><th class="l">Фонд</th><th>Цена пая, ₽</th>${MM_WINS.map(([k,t])=>`<th>${t}</th>`).join('')}</tr></thead><tbody>${
    d.funds.map(f=>`<tr data-mmf="${esc(f.secid)}" style="cursor:pointer" class="${f.secid===sel?'mm-sel':''}" title="Выбрать для сравнения ниже"><td class="l"><b>${esc(f.secid)}</b><br><small class="mu">${esc(f.name)}</small></td>
      <td class="num">${mmNum(f.last,4)}<br><small class="mu">${esc(dlabel(f.last_date))}</small></td>${MM_WINS.map(([k])=>cell(f.wins[k])).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function mmCompare(d){
  const fld=(id,t,v,hint)=>`<label class="field"><span>${t}</span><input class="in num" id="${id}" value="${esc(v)}" inputmode="decimal" ${hint?`title="${esc(hint)}"`:''}></label>`;
  const q=S.mm.q;
  const rows=d.compare.map(r=>{const a=r.after;
    return`<tr><td class="l">${esc(r.title)}<br><small class="mu">${esc(r.note||'')}</small></td><td class="num">${mmPc(r.gross)}</td>
      <td class="num">${a&&a.net_ann!=null?'<b>'+mmPc(a.net_ann)+'</b>':'<span class="mu">—</span>'}</td>
      <td class="num">${a?M(a.net_gain,'rub',0):'—'}</td><td class="num">${a?M(a.tax,'rub',0):'—'}</td></tr>`}).join('');
  const l=d.compare.find(r=>r.after&&r.after.ldv);
  return`<div class="flt"><label class="field"><span>Фонд</span><select class="in" id="mm-fund">${d.funds.map(f=>`<option value="${esc(f.secid)}" ${f.secid===d.selected?'selected':''}>${esc(f.secid)}</option>`).join('')}</select></label>
    <div class="field"><span>Окно доходности фонда</span><div class="seg" id="mm-win">${MM_WINS.map(([k,t])=>`<button data-w="${k}" class="${d.win===k?'on':''}">${t}</button>`).join('')}</div></div>
    ${fld('mm-amount','Сумма, ₽',q.amount)}${fld('mm-days','Срок, дней',q.days)}${fld('mm-fee','Комиссия брокера, % с оборота',q.fee,'Берётся с покупки и с продажи; для фонда и ОФЗ')}
    ${fld('mm-save','Ставка накопительного счёта, % год.',q.save||(d.save==null?'':d.save.toFixed(1).replace('.',',')),'Эффективная годовая ставка; по умолчанию ключевая минус 2 п.п. — только для примера')}</div>
    <div class="tbl"><table><thead><tr><th class="l">Инструмент</th><th>До налога, % год.</th><th>После налога и комиссии, % год.</th><th>Итого за срок, ₽</th><th>Налог, ₽</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="note">${l?'Срок больше трёх лет: учтена льгота долгосрочного владения (до 3 млн ₽ дохода за каждый полный год). ':''}${esc(d.ldv_note)} Налог рассчитан по ставке 13 % (15 % с превышения порога) на доход после вычета комиссий; другие доходы за год не учитываются. Доходность ОФЗ и фонда за срок принята равной показанной (допущение).</p>`;
}
function pMmFunds(){
  const m=S.mm,d=m.f;
  if(!d){if(!m.fl)loadMmF();return waitBox('Загружаю цены фондов с Мосбиржи… первый расчёт занимает до полуминуты.')}
  if(d.error&&!d.funds.length)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="mm-r">Повторить</button></div>`;
  const rf=d.rusfar,kr=d.key;
  return`<div class="card"><h2>Фонды ликвидности<span class="sp">реализованная доходность в годовом выражении; под ней — отставание от ставки</span></h2>
    <div class="mm-ref"><span>RUSFAR: <b>${mmPc(rf)}</b>${d.rusfar_date?` <small class="mu">на ${esc(dlabel(d.rusfar_date))}</small>`:''}</span><span>Ключевая ставка: <b>${mmPc(kr)}</b></span>
      <button class="btn ghost" id="mm-r" style="margin-left:auto">Обновить</button></div>
    ${mmFundsTable(d)}
    <p class="note">«Отставание от ставки» — доходность фонда минус накопленная ставка RUSFAR за то же окно (при её отсутствии — ключевая): это неявные издержки фонда (комиссия, проскальзывание, разница с реальным портфелем). ${esc(d.note)}</p></div>
  <div class="card"><h2>Сравнение после налога<span class="sp">фонд, накопительный счёт, короткие ОФЗ и ставки денежного рынка</span></h2>${mmCompare(d)}</div>`;
}
function mmBasisTable(d){
  const sign=v=>bad(v)?'—':(v>0?'+':v<0?'−':'')+NF2.format(Math.abs(+v.toFixed(2)));
  const rows=d.rows.map(r=>{
    const dv=r.divs&&r.divs.length?r.divs.map(x=>`${mmNum(x.value,2)} ₽ · ${esc(dlabel(x.record))}`).join('<br>'):(r.kind==='share'?(r.divs_known?'<span class="mu">нет до экспирации</span>':'<span class="mu" title="Источники не вернули данных о дивидендах: ожидаемую отсечку программа не видит">нет данных</span>'):'<span class="mu">—</span>');
    const warn=r.kind==='share'&&r.basis_pct<0&&!(r.divs&&r.divs.length)?' <span class="tag" title="Отрицательный базис по акции часто означает ожидаемые дивиденды, которых нет в источниках">дивиденды?</span>':'';
    return`<tr><td class="l"><b>${esc(r.asset)}</b>${warn}<br><small class="mu">${esc(r.short)} · лот ${NF2.format(r.lot)} ${esc(r.unit)}</small></td>
      <td class="num">${esc(dlabel(r.expiry))}<br><small class="mu">${r.days} дн.</small></td>
      <td class="num">${mmNum(r.f_unit,r.f_unit<100?3:2)}<br><small class="mu" title="${esc(r.price_src)}">за ${esc(r.unit)}</small></td><td class="num">${mmNum(r.spot_unit,r.spot_unit<100?3:2)}</td>
      <td class="num ${mmCls(r.basis)}">${sign(r.basis)} ₽<br><small>${mmPc(r.basis_pct)}</small></td><td class="num">${mmPc(r.ann_raw,1)}</td>
      <td class="num l"><small>${dv}</small></td><td class="num"><b>${mmPc(r.ann_adj,1)}</b></td>
      <td class="num">${r.ann_roc==null?'—':mmPc(r.ann_roc,1)}<br><small class="mu">ГО ${r.margin?M(r.margin,'rub',0):'—'}</small></td>
      <td class="num ${mmCls(r.excess)}">${mmPp(r.excess)}</td></tr>`}).join('');
  return`<div class="tbl"><table><thead><tr><th class="l">Актив / контракт</th><th>Экспирация</th><th>Фьючерс</th><th>Спот</th><th>Базис за контракт</th><th>Годовых, простая</th><th class="l">Дивиденды до экспирации</th><th>Годовых с дивидендами</th><th>На капитал с ГО</th><th>К ставке ${esc(d.ref_name||'')}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function pMmBasis(){
  const m=S.mm,d=m.b;
  if(!d){loadMmB();return waitBox('Загружаю срочный рынок Мосбиржи…')}
  if(d.error&&!d.rows.length)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="mm-br">Повторить</button></div>`;
  return`<div class="card"><h2>Базис фьючерсов<span class="sp">два ближайших контракта; данные на ${esc(d.asof||'')}</span></h2>
    <div class="mm-ref"><span>RUSFAR: <b>${mmPc(d.rusfar)}</b></span><span>Ключевая ставка: <b>${mmPc(d.key)}</b></span><button class="btn ghost" id="mm-br" style="margin-left:auto">Обновить</button></div>
    ${mmBasisTable(d)}
    <p class="note">Базис = цена фьючерса − цена базового актива × размер контракта. «Годовых» = (F/S − 1) · 365 / дни до экспирации; «с дивидендами» добавляет объявленные дивиденды с датой отсечки до экспирации; «на капитал с ГО» — прибыль, делённая на стоимость актива плюс гарантийное обеспечение. Золото пересчитано из ₽/г в ₽/унцию, стоимость контракта — через курс, заложенный биржей в шаг цены.</p>
    ${(d.skipped||[]).length?`<p class="note">Пропущено: ${d.skipped.map(esc).join('; ')}.</p>`:''}
    <p class="note">${esc(d.note)}</p></div>`;
}
function pMm(){
  const m=S.mm;
  return`<div class="seg" id="mm-tabs" style="margin-bottom:12px"><button data-t="funds" class="${m.tab==='funds'?'on':''}">Фонды ликвидности</button><button data-t="basis" class="${m.tab==='basis'?'on':''}">Базис фьючерсов (cash &amp; carry)</button></div>`
    +(m.tab==='funds'?pMmFunds():pMmBasis())+NIR_NOTE;
}
function bindMm(){
  const m=S.mm,$$=id=>document.getElementById(id);
  const t=$$('mm-tabs');if(t)t.onclick=e=>{const b=e.target.closest('[data-t]');if(!b||b.dataset.t===m.tab)return;m.tab=b.dataset.t;render()};
  const r=$$('mm-r');if(r)r.onclick=()=>{m.f=null;loadMmF();render()};
  const br=$$('mm-br');if(br)br.onclick=()=>{m.b=null;m.bl=0;loadMmB(true);render()};
  document.querySelectorAll('[data-mmf]').forEach(tr=>tr.onclick=()=>{m.q.fund=tr.dataset.mmf;loadMmF();renderSoon()});
  const win=$$('mm-win');if(win)win.onclick=e=>{const b=e.target.closest('[data-w]');if(!b)return;m.q.win=b.dataset.w;loadMmF()};
  const fs=$$('mm-fund');if(fs)fs.onchange=()=>{m.q.fund=fs.value;loadMmF()};
  for(const[id,k]of[['mm-amount','amount'],['mm-days','days'],['mm-fee','fee'],['mm-save','save']]){const e=$$(id);if(e)e.onchange=()=>{m.q[k]=e.value;loadMmF()}}
}
regPage('mm',{title:'Деньги и базис',group:'Рынок',icon:'<circle cx="9" cy="9" r="6"/><path d="M15.5 9.5A6 6 0 1 1 9.5 15.5"/><path d="M9 7v4M7.5 9h3"/>',render:pMm,bind:bindMm,pro:true});
