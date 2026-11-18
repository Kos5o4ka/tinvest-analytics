/* ── Кривые эмитентов: арбитраж внутри эмитента (#2), инверсия кривой EWS (#3), Рубль vs Валюта (#5) ── */
S.arb={tab:'pairs',fee:'0.05',data:null,loading:false,err:''};
function arbLoad(force){
  const D=S.arb;if(D.loading&&!force)return;D.loading=true;D.err='';
  api('/api/arb?'+new URLSearchParams({fee:D.fee})).then(j=>{D.loading=false;D.data=j;if(S.page==='arb')renderSoon()})
    .catch(e=>{D.loading=false;D.err=e.message||String(e);if(S.page==='arb')renderSoon()});
}
function pArb(){
  const D=S.arb;
  if(!D.data&&!D.loading)arbLoad(false);
  if(D.loading&&!D.data)return`<div class="card">${waitBox('Анализирую кривые корпоративных облигаций и перекосы доходности…')}</div>`;
  if(D.err)return`<div class="msg err">${esc(D.err)} <button class="btn ghost" id="arb-r">Повторить</button></div>`;
  const d=D.data||{};
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="arb-r">Повторить</button></div>`;
  const st=d.stats||{};
  const kpis=`<div class="g g4">${kpi('Эмитентов в анализе',st.issuers_rub||0,'торгуемые рублёвые фиксы')}${kpi('Перекосы внутри кривой',st.pairs||0,'спред ≥ 80 б.п. при близкой дюрации',st.pairs?'pos':'')}
    ${kpi('Инверсии кривой (риск)',st.inversions||0,'короткий выпуск ≥ +250 б.п. к длинному',st.inversions?'neg':'')}${kpi('Рубль vs Валюта',st.fx_pairs||0,'один эмитент в RUB и USD/CNY/EUR')}</div>`;
  const seg=`<div class="row" style="gap:12px;flex-wrap:wrap;align-items:center"><div class="seg" id="arb-tabs">
    <button class="${D.tab==='pairs'?'on':''}" data-t="pairs">Арбитраж внутри эмитента (${(d.pairs||[]).length})</button>
    <button class="${D.tab==='inv'?'on':''}" data-t="inv">Инверсия кривой — риск (${(d.inversions||[]).length})</button>
    <button class="${D.tab==='fx'?'on':''}" data-t="fx">Рубль vs Валюта (${(d.fx_vs_rub||[]).length})</button></div>
    <label class="row" style="margin-left:auto;gap:6px;font-size:12.5px"><span class="mu">Комиссия брокера, %</span><input class="in num" id="arb-fee" style="width:74px;padding:5px 8px" value="${esc(D.fee)}"></label>
    <button class="btn ghost" id="arb-r">Обновить</button></div>`;
  let body='';
  if(D.tab==='pairs'){
    const rs=d.pairs||[];
    body=rs.length?`<div class="tbl"><table><thead><tr><th class="l">Эмитент</th><th class="l">Дешевле (YTM выше)</th><th class="l">Дороже (YTM ниже)</th><th>Разница YTM</th><th>Δ Дюрации</th><th>Окупаемость перекладки</th></tr></thead><tbody>`+
      rs.map(x=>`<tr><td class="l"><b>${esc(x.issuer)}</b><br>${x.rating?ratingTag({v:x.rating}):'<span class="mu">—</span>'}</td>
        <td class="l" data-isin="${esc(x.buy.isin)}" style="cursor:pointer"><b>${esc(x.buy.name)}</b><br><small class="pos num">YTM ${f2(x.buy.yield)} %</small> <small class="mu">· дюр. ${f2(x.buy.dur)} г.</small></td>
        <td class="l" data-isin="${esc(x.sell.isin)}" style="cursor:pointer"><b>${esc(x.sell.name)}</b><br><small class="num">YTM ${f2(x.sell.yield)} %</small> <small class="mu">· дюр. ${f2(x.sell.dur)} г.</small></td>
        <td class="num pos"><b>+${x.spread_bp} б.п.</b></td><td class="num">${f2(x.dur_diff)} г.</td>
        <td class="num">${x.payback_mo!=null?f2(x.payback_mo)+' мес.':'—'}<br><small class="mu">издержки ~${f2(x.switch_cost_pct)} %</small></td></tr>`).join('')+`</tbody></table></div>`
      :'<div class="empty">Явных перекосов ≥ 80 б.п. внутри кривой одного эмитента сейчас не найдено.</div>';
  }else if(D.tab==='inv'){
    const rs=d.inversions||[];
    body=rs.length?`<div class="tbl"><table><thead><tr><th class="l">Эмитент</th><th class="l">Статус</th><th class="l">Короткий выпуск (≤ 1,5 г.)</th><th class="l">Длинный выпуск</th><th>Инверсия</th></tr></thead><tbody>`+
      rs.map(x=>`<tr><td class="l"><b>${esc(x.issuer)}</b><br>${x.rating?ratingTag({v:x.rating}):'<span class="mu">—</span>'}</td>
        <td class="l"><span class="tag ${x.severity==='high'?'dfl-d':'dfl-t'}">${x.severity==='high'?'Высокий стресс':'Внимание'}</span></td>
        <td class="l" data-isin="${esc(x.short.isin)}" style="cursor:pointer"><b>${esc(x.short.name)}</b><br><small class="neg num">YTM ${f2(x.short.yield)} %</small> <small class="mu">· дюр. ${f2(x.short.dur)} г.</small></td>
        <td class="l" data-isin="${esc(x.long.isin)}" style="cursor:pointer"><b>${esc(x.long.name)}</b><br><small class="num">YTM ${f2(x.long.yield)} %</small> <small class="mu">· дюр. ${f2(x.long.dur)} г.</small></td>
        <td class="num neg"><b>+${x.inv_bp} б.п.</b></td></tr>`).join('')+`</tbody></table></div>`
      :'<div class="empty">Инверсий кривой (стрессовых сигналов по коротким выпускам) не обнаружено.</div>';
  }else{
    const rs=d.fx_vs_rub||[];
    body=rs.length?`<div class="tbl"><table><thead><tr><th class="l">Эмитент</th><th class="l">Рублёвый выпуск</th><th class="l">Валютный выпуск</th><th>Безубыт. рост валюты (НДФЛ 13 %)</th><th>С ЛДВ (&gt; 3 лет)</th><th>Целевой курс через год</th></tr></thead><tbody>`+
      rs.map(x=>`<tr><td class="l"><b>${esc(x.issuer)}</b><br>${x.rating?ratingTag({v:x.rating}):'<span class="mu">—</span>'}</td>
        <td class="l" data-isin="${esc(x.rub.isin)}" style="cursor:pointer"><b>${esc(x.rub.name)}</b><br><small class="num">${f2(x.rub.yield)} % RUB · ${f2(x.rub.dur)} г.</small></td>
        <td class="l" data-isin="${esc(x.fx.isin)}" style="cursor:pointer"><b>${esc(x.fx.name)}</b><br><small class="num">${f2(x.fx.yield)} % ${esc(x.cur)} · ${f2(x.fx.dur)} г.</small></td>
        <td class="num"><b>+${f2(x.be_pre_pct)} %/год</b></td>
        <td class="num pos">+${f2(x.be_ldv_pct)} %/год</td>
        <td class="num">${x.fx_breakeven_1y!=null?f2(x.fx_breakeven_1y)+' ₽':'—'}${x.fx_now!=null?`<br><small class="mu">сейчас ${f2(x.fx_now)} ₽</small>`:''}</td></tr>`).join('')+`</tbody></table></div>`
      :'<div class="empty">Эмитентов, одновременно торгующих рублёвые и валютные фиксы близкой дюрации, не найдено.</div>';
  }
  return kpis+`<div class="card">${seg}<div style="margin-top:12px">${body}</div></div>
    <p class="note">Окупаемость перекладки учитывает двойную комиссию брокера + оценку бид-аск спреда 0,20 % и НДФЛ 13 %. Инверсия кривой (короткий выпуск сильно дороже по YTM длинного) — классический ранний индикатор проблем с ликвидностью эмитента. Клик по любой бумаге открывает её карточку. ${NIR_NOTE}</p>`;
}
function bindArb(){
  const r=$('#arb-r');if(r)r.onclick=()=>{S.arb.data=null;arbLoad(true);render()};
  const t=$('#arb-tabs');if(t)t.onclick=e=>{const b=e.target.closest('[data-t]');if(!b)return;S.arb.tab=b.dataset.t;render()};
  const f=$('#arb-fee');if(f)f.onchange=()=>{S.arb.fee=f.value;S.arb.data=null;arbLoad(true);render()};
}
regPage('arb',{title:'Кривые и арбитраж',group:'Рынок',icon:'<path d="M3 17l5-5 4 4 9-10"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="10" r="2"/>',render:pArb,bind:bindArb});
