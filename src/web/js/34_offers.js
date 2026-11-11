/* ── Оферты: держать или предъявить ── */
function loadOff(){
  const acc=S.account,o=S.off;
  if(o&&o.acc===acc&&(o.loading||o.data||o.error))return;
  S.off={acc,loading:true};
  api('/api/offers?'+new URLSearchParams({account:acc})).then(d=>{if(S.account!==acc)return;S.off={acc,data:d};if(S.page==='off')renderSoon()})
   .catch(e=>{if(S.account!==acc)return;S.off={acc,error:e.message};if(S.page==='off')renderSoon()});
}
const OF_HINT={sell_market:['Продать на бирже','of-info'],put:['Предъявить','of-warn'],hold:['Держать','of-ok'],wait:['Подождать','of-wait'],call:['Предупреждение','of-warn'],closed:['Поздно','of-wait']};
const ofDays=n=>n===0?'сегодня':n===1?'завтра':'через '+n+' '+(n%10===1&&n%100!==11?'день':n%10>=2&&n%10<=4&&(n%100<10||n%100>=20)?'дня':'дней');
function ofPeriod(x){
  if(x.kind==='call')return'<span class="mu">не применяется</span>';
  if(!x.period_start||!x.period_end)return'<span class="mu">не опубликован</span>';
  const t=`${ddm(x.period_start)} – ${ddm(x.period_end)}`;
  return x.period_status==='open'?`<b class="pos">${t}</b><br><small class="${x.urgent?'neg':'mu'}">открыт, до конца ${x.period_days_left===0?'сегодня':ofDays(x.period_days_left).replace('через ','')}</small>`
    :x.period_status==='closed'?`${t}<br><small class="mu">закончился</small>`:`${t}<br><small class="${x.urgent?'neg':'mu'}">${x.period_days_left!=null?'закроется '+ofDays(x.period_days_left):''}</small>`;
}
function ofCard(x){
  const h=x.hint||{},[lab,hc]=OF_HINT[h.code]||['','of-wait'];
  const yo=x.yield_to_offer!=null&&x.yield_to_offer<=100?pctp(x.yield_to_offer,1):x.yield_to_offer!=null?'&gt; 100 %':'—';
  const cpn=x.kind==='call'?'—':x.coupon_known?`<b>${pctp(x.new_rate,1)}</b> годовых<br><small class="mu">доходность ${x.hold_yield!=null?pctp(x.hold_yield,1):'—'}</small>`:'<span class="mu">не объявлен</span>';
  const peers=x.peer_median!=null?`${pctp(x.peer_median,1)}<br><small class="mu">${x.peers_n} похожих выпусков</small>`:'<span class="mu">нет данных</span>';
  return`<div class="card of-card ${x.urgent?'of-urgent':''}">
    <div class="of-head" data-isin="${esc(x.isin||'')}" title="Открыть карточку выпуска">${logo(x,34)}<div class="of-nm"><b>${esc(x.name)}</b><small class="mu">${esc(x.isin||'')}${x.floating?' · флоатер':''} · ${M(x.value_rub,'rub',0)}</small></div>
      ${x.rating?`<span class="tag rt rt-${esc(rBucket(x.rating).split(' ')[0])}">${esc(x.rating)}</span>`:''}
      <span class="tag ${x.kind==='call'?'of-t-call':'of-t-put'}">${x.kind==='call'?'колл / досрочное погашение':'оферта'}</span>${x.urgent?'<span class="tag of-t-urg">срочно</span>':''}</div>
    <div class="of-grid">
      <div><span class="k">Дата оферты</span><b class="num">${ddm(x.date)}</b><br><small class="mu">${ofDays(x.days)}</small></div>
      <div><span class="k">Период предъявления</span>${ofPeriod(x)}</div>
      <div><span class="k">Цена выкупа / сейчас</span><span class="num">${x.offer_price!=null?f2(x.offer_price)+' %':'—'} / ${x.price!=null?f2(x.price)+' %':'—'}</span>${x.kind==='put'&&x.to_offer_rub?`<br><small class="mu">выкуп ≈ ${M(x.to_offer_rub,'rub',0)}</small>`:''}</div>
      <div><span class="k">Доходность к оферте</span><span class="num">${x.kind==='call'?'—':yo}</span></div>
      <div><span class="k">Купон после оферты</span>${cpn}</div>
      <div><span class="k">Аналоги, доходность</span>${x.kind==='call'?'—':peers}</div></div>
    <div class="of-hint ${hc}"><span class="of-lab">${esc(lab)}</span><div><b>${esc(h.title||'')}</b><p>${esc(h.text||'')}</p>${x.risk_notes&&x.risk_notes.length&&h.code!=='put'?`<p class="neg">Обратите внимание: ${esc(x.risk_notes.join('; '))}.</p>`:''}</div></div></div>`;
}
function pOff(){
  loadOff();
  const o=S.off;
  if(!o||o.loading)return`<div class="card">${waitBox('Читаю графики оферт и купонов по облигациям портфеля…')}</div>`;
  if(o.error)return`<div class="msg err">${esc(o.error)} <button class="btn ghost" id="of-r">Повторить</button></div>`;
  const d=o.data;
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="of-r">Повторить</button></div>`;
  const kp=`<div class="g g4">${kpi('Оферт за 12 месяцев',d.count,`по ${d.bonds_count} облигациям портфеля`,null,S1)}${kpi('С правом предъявить',d.put_count,'держатель может продать эмитенту',null,S3)}
    ${kpi('Срочные',d.urgent_count,'период предъявления открыт или заканчивается за 7 дней',d.urgent_count?'neg':'',S8)}${kpi('Выкуп по номиналу',M(d.to_offer_rub,'rub',0),'если предъявить все бумаги',null,S2)}</div>`;
  const list=d.items.length?d.items.map(ofCard).join(''):`<div class="card empty">${esc(d.empty_text)}</div>`;
  return kp+(d.errors&&d.errors.length?`<div class="msg">Не удалось разобрать часть выпусков: ${esc(d.errors.slice(0,3).join('; '))}</div>`:'')+list+
   `<div class="card"><h2>Как это читать</h2><p class="note">${(d.notes||[]).map(esc).join('<br><br>')}<br><br>Правило подсказки: если на бирже бумага стоит дороже цены выкупа — выгоднее продать на бирже; если новый купон известен и доходность после оферты ниже медианы похожих выпусков (тот же рейтинг ±1 ступень, близкий срок) больше чем на 0,5 п. п. — предъявление выглядит разумнее; если купон ещё не объявлен, показан порог ставки, ниже которого предъявление выглядит разумнее. Подсказки справочные, это не индивидуальная инвестиционная рекомендация: условия оферты проверяйте в документах выпуска и у брокера.</p></div>`;
}
function bindOff(){
  const r=$('#of-r');if(r)r.onclick=()=>{S.off=null;render()};
}
