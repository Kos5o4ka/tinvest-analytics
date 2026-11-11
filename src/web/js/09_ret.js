/* ── Доходность ── */
function heatBg(v,mx){if(bad(v))return'';const a=Math.min(1,Math.abs(v)/(mx||1));return`background:${v>=0?'rgba(62,207,142,'+(0.08+a*0.42)+')':'rgba(255,107,107,'+(0.08+a*0.42)+')'}`}
/* Обмены бумаг (ГДР -> акции и т.п.), восстановленные по таблице известных и автоматически */
function convNote(list,tax){
  if(!list||!list.length)return'';
  const dm=x=>x.slice(8)+'.'+x.slice(5,7)+'.'+x.slice(0,4);
  const items=list.map(c=>`${esc(c.old||'?')} → ${esc(c.new||'?')} (${c.qty} шт., ${dm(c.date)}${c.source==='auto'?', предположение':''})`).join(', ');
  const auto=list.some(c=>c.source==='auto');
  return`<p class="note">Учтены обмены бумаг: ${items}. ${tax?'Стоимость покупки и даты владения (для ЛДВ) сохранены.':'Брокер не отдаёт такие обмены в операциях, поэтому они восстановлены по таблице известных обменов.'}${auto?' Обмены с пометкой «предположение» найдены автоматически (остаток старой бумаги и продажа новой без покупки на то же количество) — они могут быть неточными.':''}</p>`}
function pRet(){
  const h=S.hist;
  if(!h)return`<div class="card">${waitBox('Восстанавливаю историю стоимости портфеля по дневным ценам закрытия. Первый раз это может занять до минуты — дальше данные берутся из локальной базы.')}</div>`;
  if(h.error)return`<div class="msg err">${esc(h.error)}</div>`;
  if(!h.days.length)returnemptyHint('Доходность считается по операциям: пополнениям, сделкам и выплатам. Подключите Т-Инвестиции или загрузите отчёт брокера.',[['imp','Импорт отчёта',1],['set','Настройки']]);
  const hs=histSlice();
  const ms=Object.keys(h.monthly).sort(),years=[...new Set(ms.map(m=>m.slice(0,4)))].sort().reverse();
  const inP=m=>{const s=periodStart(),e=periodEnd();return(!s||m>=s.slice(0,7))&&(!e||m<=e.slice(0,7))};
  const pm=ms.filter(inP).map(m=>[m,h.monthly[m]]);
  const best=pm.length?pm.reduce((a,b)=>b[1]>a[1]?b:a):null,worst=pm.length?pm.reduce((a,b)=>b[1]<a[1]?b:a):null;
  const lab=m=>{const[y,mm]=m.split('-');return MONF[+mm-1].toLowerCase()+' '+y};
  let out=`<div class="g g6">
    ${kpi('Доходность за период',hs?pct(hs.total*100):'—','метод TWR — без влияния пополнений',hs?cls(hs.total):'',S1)}
    ${kpi('В пересчёте на год',hs&&hs.ann!=null?pct(hs.ann*100):'—',hs&&hs.ann==null?'период короче года':'среднегодовая (TWR)',hs&&hs.ann!=null?cls(hs.ann):'',S7)}
    ${kpi('XIRR',S.data.xirr==null?'—':pct(S.data.xirr*100,1),'с учётом сумм и дат пополнений',cls(S.data.xirr),S3)}
    ${kpi('Макс. просадка',hs?pct(hs.maxdd*100):'—','от пика до дна за период',hs&&hs.maxdd<0?'neg':'',S2)}
    ${kpi('Лучший месяц',best?pct(best[1]*100):'—',best?lab(best[0]):'','pos',S3)}
    ${kpi('Худший месяц',worst?pct(worst[1]*100):'—',worst?lab(worst[0]):'',worst&&worst[1]<0?'neg':'',S8)}</div>`;
  if(hs){
    const labs=hs.days.map(x=>{const[y,m]=x.split('-');return MON[+m-1]+' '+y.slice(2)}),tips=hs.days.map(dlabel);
    const ser=[{n:'Мой портфель',c:S1,hex:'#3987e5',v:hs.twr.map(x=>x*100),w:2.4}];
    if(hs.bench.LQDT)ser.push({n:'Денежный рынок (LQDT)',c:S3,v:hs.bench.LQDT.map(x=>x==null?null:x*100),w:1.6});
    if(hs.bench.TMOS)ser.push({n:'Индекс МосБиржи (фонд TMOS)',c:S2,v:hs.bench.TMOS.map(x=>x==null?null:x*100),w:1.6});
    const fp=v=>(Math.round(v*10)/10).toString().replace('.',',')+'%';
    chart('c-twr',line,{h:300,labels:labs,tipLabels:tips,series:ser,fa:fp,ft:v=>pct(v),zero:false});
    chart('c-dd',line,{h:200,area:'neg',labels:labs,tipLabels:tips,series:[{n:'Просадка',c:S8,hex:'#e66767',v:hs.dd.map(x=>x*100)}],fa:fp,ft:v=>pct(v)});
    chart('c-pl',line,{h:200,area:true,labels:labs,tipLabels:tips,series:[{n:'Прибыль (стоимость − вложено)',c:S3,hex:'#199e70',v:hs.value.map((v,i)=>v-hs.invested[i])}]});
    out+=`<div class="card"><h2>Доходность портфеля и бенчмарков, %<span class="sp">${periodName()}</span></h2><div id="c-twr" class="chart"></div></div>
      <div class="g g2"><div class="card"><h2>Просадка от максимума, %</h2><div id="c-dd" class="chart"></div></div>
      <div class="card"><h2>Прибыль в рублях</h2><div id="c-pl" class="chart"></div></div></div>`;
  }
  const mx=Math.max(0.01,...ms.map(m=>Math.abs(h.monthly[m])));
  out+=`<div class="card" style="padding:14px 16px"><h2 style="padding:4px 4px 0">Доходность по месяцам, %</h2><div class="tbl"><table class="hm"><thead><tr><th class="l">Год</th>${MON.map(m=>`<th>${m}</th>`).join('')}<th>За год</th></tr></thead><tbody>`+
    years.map(y=>{let acc=1;const cells=MON.map((_,i)=>{const k=y+'-'+String(i+1).padStart(2,'0'),v=h.monthly[k];if(v==null)return'<td></td>';acc*=1+v;
      return`<td class="num" style="${heatBg(v,mx)}">${(v*100).toFixed(2).replace('.',',')}</td>`}).join('');
      return`<tr><td class="y">${y}</td>${cells}<td class="num" style="${heatBg(acc-1,mx*4)};font-weight:650">${pct((acc-1)*100)}</td></tr>`}).join('')+
    `</tbody></table></div></div>`;
  const rc=h.recon||{},diff=rc.actual?(rc.calc-rc.actual)/rc.actual*100:null;
  out+=`<p class="note">Стоимость портфеля на каждый день восстановлена по операциям и дневным ценам закрытия (облигации — с НКД по графику купонов). Доходность считается по методу TWR — пополнения и выводы на неё не влияют, поэтому её можно сравнивать с бенчмарками.
    ${diff!=null&&Math.abs(diff)>2?`<b>Расчётная стоимость на сегодня (${M(rc.calc,'rub',0)}) отличается от фактической (${M(rc.actual,'rub',0)}) на ${pct(diff,1)}</b> — вероятно, по части бумаг нет истории цен (внебиржевые, заблокированные, фьючерсы) или переводы бумаг между брокерами.`:''}
    ${h.glitches?`Пропущено дней с некорректными ценами: ${h.glitches}.`:''} Бенчмарки — фонды LQDT (денежный рынок) и TMOS (индекс МосБиржи) с учётом их собственной доходности.</p>`;
  out+=convNote(h.conversions,false);
  return out;
}

