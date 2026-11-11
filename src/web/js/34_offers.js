/* ── Оферты: держать или предъявить ── */
function loadOff(){
  const acc=S.account,o=S.off;
  if(o&&o.acc===acc&&(o.loading||o.data||o.error))return;
  S.off={acc,loading:true};
  api('/api/offers?'+new URLSearchParams({account:acc})).then(d=>{if(S.account!==acc)return;S.off={acc,data:d};if(S.page==='off')renderSoon()})
   .catch(e=>{if(S.account!==acc)return;S.off={acc,error:e.message};if(S.page==='off')renderSoon()});
}
const OF_HINT={sell_market:['Продать на бирже','of-info'],put:['Предъявить','of-warn'],hold:['Держать','of-ok'],wait:['Подождать','of-wait'],call:['Знать','of-info'],unknown:['Проверить','of-wait'],closed:['Поздно','of-wait']};
const OF_KIND={put:['PUT — право продать эмитенту','of-t-put','Право ДЕРЖАТЕЛЯ: в период предъявления вы можете подать заявку через брокера, и эмитент выкупит бумагу по цене оферты (обычно 100 % номинала). Не хотите — ничего не делайте.'],call:['CALL — эмитент может погасить досрочно','of-t-call','Право ЭМИТЕНТА: он может досрочно погасить или выкупить выпуск по заранее известной цене. Заявку подавать не нужно; для вас это риск реинвестирования — деньги вернутся, когда ставки могут быть ниже.'],unknown:['тип не указан','of-t-unk','Источники не сообщают, кто вправе решать: держатель (put) или эмитент (call). Проверьте условия в документах выпуска, пока не принято решение.']};
const OF_HOR=[['all','все'],['92','3 мес'],['366','1 год']],OF_TYP=[['all','все типы'],['put','PUT'],['call','CALL']];
S.offH=S.offH||'all';S.offT=S.offT||'all';
const ofKbLink=()=>'<a href="#" class="kb-a" data-kb="offers">Что такое put и call</a>';
const ofDays=n=>n===0?'сегодня':n===1?'завтра':'через '+n+' '+(n%10===1&&n%100!==11?'день':n%10>=2&&n%10<=4&&(n%100<10||n%100>=20)?'дня':'дней');
function ofPeriod(x){
  if(x.kind!=='put')return'<span class="mu">не применяется</span>';
  if(!x.period_start||!x.period_end)return'<span class="mu">не опубликован</span>';
  const t=`${ddm(x.period_start)} – ${ddm(x.period_end)}`;
  return x.period_status==='open'?`<b class="pos">${t}</b><br><small class="${x.urgent?'neg':'mu'}">открыт, до конца ${x.period_days_left===0?'сегодня':ofDays(x.period_days_left).replace('через ','')}</small>`
    :x.period_status==='closed'?`${t}<br><small class="mu">закончился</small>`:`${t}<br><small class="${x.urgent?'neg':'mu'}">${x.period_days_left!=null?'закроется '+ofDays(x.period_days_left):''}</small>`;
}
const OF_HELP_CHIP={pending:['Подождать','of-wait'],formula:['По формуле','of-wait'],closed:['Поздно','of-wait'],below:['Предъявить','of-warn'],fair:['Оставить','of-ok'],above:['Оставить','of-ok'],none:['Оценить','of-wait']};
function ofHelper(x){
  const p=x.helper;if(!p)return null;
  const chip=(x.hint&&x.hint.code==='sell_market')?OF_HINT.sell_market:OF_HELP_CHIP[p.outcome||p.status]||OF_HELP_CHIP.none;
  const body=`<b>${esc(p.title)}</b><p>${esc(p.text)}</p>${p.numbers?`<p class="mu">${esc(p.numbers)}.</p>`:''}
    ${p.apply?`<p class="of-do"><b>Когда подавать.</b> ${esc(p.apply)} ${kbLink('offers','Как подать заявку на оферту')}</p>`:''}
    ${p.risk_notes&&p.risk_notes.length?`<p class="neg">Кредитные риски: ${esc(p.risk_notes.join('; '))}.</p>`:''}
    <p class="mu"><small>${esc(p.disclaimer)}</small></p>`;
  return{chip,body};
}
function ofCard(x){
  const hp=x.kind==='put'?ofHelper(x):null;
  const h=x.hint||{},[lab,hc]=hp?hp.chip:(OF_HINT[h.code]||['','of-wait']),k=OF_KIND[x.kind]||OF_KIND.unknown,put=x.kind==='put';
  const yo=x.yield_to_offer!=null&&x.yield_to_offer<=100?pctp(x.yield_to_offer,1):x.yield_to_offer!=null?'&gt; 100 %':'—';
  const cpn=!put?'—':x.coupon_known?`<b>${pctp(x.new_rate,1)}</b> годовых<br><small class="mu">доходность ${x.hold_yield!=null?pctp(x.hold_yield,1):'—'}</small>`:'<span class="mu">не объявлен</span>';
  const peers=x.peer_median!=null?`${pctp(x.peer_median,1)}<br><small class="mu">${x.peers_n} похожих выпусков</small>`:'<span class="mu">нет данных</span>';
  const dl=put?'Дата оферты':x.kind==='call'?'Дата колл':'Дата оферты';
  const priceTxt=x.offer_price!=null&&(put||x.price_known)?f2(x.offer_price)+' %':put?'—':'номинал?';
  const what=put?`<p class="of-do"><b>Что делать.</b> Хотите вернуть деньги по цене оферты — подайте заявку через брокера в период предъявления (обычно за несколько дней до его конца). Не хотите — бумага останется у вас.</p>`
    :x.kind==='call'?`<p class="of-do"><b>Что это значит для вас.</b> Решает эмитент, заявку подавать не нужно. Если выпуск погасят досрочно, вы получите номинал и купон на дату погашения, но дальше придётся искать новое вложение; смотрите «доходность к колл».</p>`:'';
  return`<div class="card of-card ${x.urgent?'of-urgent':''}">
    <div class="of-head" data-isin="${esc(x.isin||'')}" title="Открыть карточку выпуска">${logo(x,34)}<div class="of-nm"><b>${esc(x.name)}</b><small class="mu">${esc(x.isin||'')}${x.floating?' · флоатер':''} · ${M(x.value_rub,'rub',0)}</small></div>
      ${x.rating?`<span class="tag rt rt-${esc(rBucket(x.rating).split(' ')[0])}">${esc(x.rating)}</span>`:''}
      <span class="tag ${k[1]}" title="${esc(k[2])}">${esc(k[0])}</span>${x.urgent?'<span class="tag of-t-urg">срочно</span>':''}</div>
    <div class="of-grid">
      <div><span class="k">${dl}</span><b class="num">${ddm(x.date)}</b><br><small class="mu">${ofDays(x.days)}</small></div>
      <div><span class="k">Период предъявления</span>${ofPeriod(x)}</div>
      <div><span class="k">Цена выкупа / сейчас</span><span class="num">${priceTxt} / ${x.price!=null?f2(x.price)+' %':'—'}</span>${put&&x.to_offer_rub?`<br><small class="mu">выкуп ≈ ${M(x.to_offer_rub,'rub',0)}</small>`:''}</div>
      <div><span class="k">${put?'Доходность к оферте':x.kind==='call'?'Доходность к колл':'Доходность к дате'}</span><span class="num">${yo}</span></div>
      <div><span class="k">Купон после оферты</span>${cpn}</div>
      <div><span class="k">Аналоги, доходность</span>${put?peers:'—'}</div></div>
    <div class="of-hint ${hc}"><span class="of-lab">${esc(lab)}</span>${hp?`<div><span class="mu"><small>Помощник по оферте</small></span><br>${hp.body}${x.inferred?'<p class="mu"><small>Тип определён по формулировке Мосбиржи («Оферта» = право держателя); отдельного подтверждения даты нет.</small></p>':''}</div>`:`<div><b>${esc(h.title||'')}</b><p>${esc(h.text||'')}</p>${what}${x.risk_notes&&x.risk_notes.length&&h.code!=='put'?`<p class="neg">Обратите внимание: ${esc(x.risk_notes.join('; '))}.</p>`:''}${x.inferred?'<p class="mu"><small>Тип определён по формулировке Мосбиржи («Оферта» = право держателя); отдельного подтверждения даты нет.</small></p>':''}</div>`}</div></div>`;
}
function ofFiltered(d){
  const hz=S.offH==='all'?null:+S.offH;
  return d.items.filter(x=>(hz==null||x.days<=hz)&&(S.offT==='all'||x.kind===S.offT));
}
function pOff(){
  loadOff();
  const o=S.off;
  if(!o||o.loading)return`<div class="card">${waitBox('Читаю графики оферт и купонов по облигациям портфеля…')}</div>`;
  if(o.error)return`<div class="msg err">${esc(o.error)} <button class="btn ghost" id="of-r">Повторить</button></div>`;
  const d=o.data;
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="of-r">Повторить</button></div>`;
  const L=ofFiltered(d),pu=L.filter(x=>x.kind==='put'),ca=L.filter(x=>x.kind==='call'),un=L.length-pu.length-ca.length;
  const hl=(OF_HOR.find(h=>h[0]===S.offH)||OF_HOR[0])[1];
  const kp=`<div class="g g4">${kpi('Всего оферт',L.length,`${S.offH==='all'?'за всё время до погашения':'за период: '+hl} · ${d.bonds_count} облигаций${un?' · тип не указан: '+un:''}`,null,S1)}${kpi('PUT: можно предъявить',pu.length,'держатель может продать эмитенту',null,S3)}
    ${kpi('CALL: эмитент может погасить',ca.length,d.both_count?`${d.both_count} вып. имеют и put, и call`:'заявку подавать не нужно',null,S8)}${kpi('Выкуп по put',M(pu.reduce((a,x)=>a+(x.to_offer_rub||0),0),'rub',0),`срочных: ${pu.filter(x=>x.urgent).length}`,pu.some(x=>x.urgent)?'neg':'',S2)}</div>`;
  const seg=(id,arr,cur)=>`<div class="seg" id="${id}">${arr.map(([v,t])=>`<button data-v="${v}" class="${cur===v?'on':''}">${t}</button>`).join('')}</div>`;
  const bar=`<div class="row" style="padding:0 0 10px;gap:12px;flex-wrap:wrap;align-items:center"><span class="mu">Горизонт</span>${seg('of-h',OF_HOR,S.offH)}<span class="mu">Тип</span>${seg('of-t',OF_TYP,S.offT)}<span style="margin-left:auto">${ofKbLink()}</span></div>`;
  const list=L.length?L.map(ofCard).join(''):`<div class="card empty">${esc(d.items.length?'В выбранном горизонте и типе оферт нет: расширьте горизонт или смените тип.':d.empty_text)}</div>`;
  return kp+bar+(d.errors&&d.errors.length?`<div class="msg">Не удалось разобрать часть выпусков: ${esc(d.errors.slice(0,3).join('; '))}</div>`:'')+list+
   `<div class="card"><h2>Как это читать</h2><p class="note">${(d.notes||[]).map(esc).join('<br><br>')}<br><br>Правило подсказки для put: если на бирже бумага стоит дороже цены выкупа — выгоднее продать на бирже; подсказка появляется только после того, как эмитент объявил купон на период после оферты (обычно за день до открытия приёма заявок). Тогда доходность бумаги при текущей цене с новым купоном сравнивается с медианой похожих выпусков (тот же рейтинг ±1 ступень, близкий срок): ниже больше чем на 0,5 п. п. — предъявление выглядит разумнее; выше больше чем на 0,5 п. п. — оставить выгоднее; иначе купон в рынке. У плавающего купона размер считается по формуле, сравнение не строится. Подсказки справочные, это не индивидуальная инвестиционная рекомендация: условия оферты проверяйте в документах выпуска и у брокера. ${ofKbLink()}.</p></div>`;
}
function bindOff(){
  const r=$('#of-r');if(r)r.onclick=()=>{S.off=null;render()};
  const h=$('#of-h');if(h)h.onclick=e=>{const b=e.target.closest('button[data-v]');if(b){S.offH=b.dataset.v;render()}};
  const t=$('#of-t');if(t)t.onclick=e=>{const b=e.target.closest('button[data-v]');if(b){S.offT=b.dataset.v;render()}};
}
