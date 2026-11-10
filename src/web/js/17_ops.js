/* ── Операции ── */
const KINDS=[['','Все'],['trade','Сделки'],['income','Доходы'],['fees','Комиссии'],['tax','Налоги'],['cash','Пополнения и выводы']];
const KMAP={trade:['buy','sell'],income:['dividends','coupons','repayments','overnight'],fees:['fee_broker','fee_service','fee_other','margin_fee','varmargin'],tax:TAXK,cash:['deposits','withdrawals']};
const OPN={BUY:'Покупка',SELL:'Продажа',BUY_CARD:'Покупка',SELL_CARD:'Продажа',BUY_MARGIN:'Покупка (маржа)',SELL_MARGIN:'Продажа (маржа)',DIVIDEND:'Дивиденды',COUPON:'Купон',
  BOND_REPAYMENT:'Амортизация',BOND_REPAYMENT_FULL:'Погашение',BROKER_FEE:'Комиссия брокера',SERVICE_FEE:'Обслуживание',MARGIN_FEE:'Плата за маржу',TAX:'НДФЛ',
  DIVIDEND_TAX:'Налог с дивидендов',BOND_TAX:'Налог с купона',INPUT:'Пополнение',OUTPUT:'Вывод',INP_MULTI:'Перевод между счетами',OUT_MULTI:'Перевод между счетами',
  OVERNIGHT:'Доход по РЕПО',ACCRUING_VARMARGIN:'Вар. маржа',WRITING_OFF_VARMARGIN:'Вар. маржа',TAX_CORRECTION:'Возврат налога',INPUT_SECURITIES:'Зачисление бумаг',OUTPUT_SECURITIES:'Списание бумаг'};
function opsFiltered(){
  const q=S.opsQ.toLowerCase(),ks=KMAP[S.opsK];
  return S.data.ops.filter(o=>(!ks||ks.includes(o[2]))&&(!q||(o[1]+' '+(OPN[o[1]]||'')+' '+o[3]+' '+o[4]+' '+o[12]).toLowerCase().includes(q)));
}
function pOps(){
  return`<div class="card"><div class="row" style="margin-bottom:14px">
    <input class="in" id="oq" placeholder="Поиск: название, тикер, тип операции…" value="${esc(S.opsQ)}" style="flex:1;min-width:240px">
    <div class="seg" id="ok">${KINDS.map(([k,t])=>`<button class="${k===S.opsK?'on':''}" data-k="${k}">${t}</button>`).join('')}</div>
    <a class="btn ghost" style="text-decoration:none" href="/api/operations.csv?${new URLSearchParams({period:S.period,account:S.account})}">${svgI('<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',2)}CSV</a></div>
    <div id="otab"></div></div>`;
}
function drawOps(){
  const all=opsFiltered(),rows=all.slice(0,S.opsN),el=$('#otab');if(!el)return;
  if(!all.length){el.innerHTML='<div class="empty">Операций не найдено</div>';return}
  const multi=S.account==='all';
  el.innerHTML=`<p class="note" style="margin-bottom:8px">Найдено: ${f0(all.length)}</p><div class="tbl" style="max-height:calc(100vh - 290px)"><table><thead><tr>
    <th>Дата</th><th class="l">Операция</th><th class="l">Инструмент</th>${multi?'<th class="l">Счёт</th>':''}<th>Кол-во</th><th>Цена</th><th>Сумма</th><th>Комиссия</th><th>Результат</th></tr></thead><tbody>`+
    rows.map(o=>`<tr><td class="num t2">${esc(o[0])}</td><td class="l"><span class="tag">${esc(OPN[o[1]]||o[1])}</span></td>
    <td class="l" style="max-width:380px">${o[3]||o[4]?`<div class="tk">${logo({name:o[3],ticker:o[4],logo:o[11]},24)}<div><b style="font-weight:550">${esc(o[3]||o[4])}</b></div></div>`:''}</td>
    ${multi?`<td class="l t2" style="max-width:160px;overflow:hidden;text-overflow:ellipsis">${esc(o[12])}</td>`:''}
    <td class="num">${o[5]||''}</td><td class="num">${o[6]?f2(o[6]):''}</td><td class="num ${cls(o[7])}">${SM(o[7],o[8])}</td><td class="num mu">${o[9]?f2(o[9]):''}</td><td class="num ${cls(o[10])}">${o[10]?SM(o[10],o[8]):''}</td></tr>`).join('')+
    `</tbody></table>${all.length>rows.length?`<div class="more"><button class="btn ghost" id="omore">Показать ещё (${f0(all.length-rows.length)})</button></div>`:''}</div>`;
  const m=$('#omore');if(m)m.onclick=()=>{S.opsN+=500;drawOps()};
}

