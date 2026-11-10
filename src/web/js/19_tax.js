/* ── Налоги ── */
function pTax(){
  const d=S.data,lf=d.life,rows=d.tax,cy=new Date().getFullYear(),cur=rows.find(r=>r.year===cy);
  const withheld=sumK(lf,TAXK);
  let out=`<div class="g g4">${kpi('Удержано налогов за всё время',M(withheld),'НДФЛ, удержанный брокером',null,S4)}
    ${kpi(`Оценка НДФЛ за ${cy}`,cur?M(cur.estimate):'—',cur?`база ${short(Math.max(0,cur.trade)+cur.income)} ₽`:'нет дохода',null,S1)}
    ${kpi(`Удержано в ${cy}`,cur?M(cur.withheld):'—','по операциям этого года',null,S3)}
    ${kpi('Ожидается к удержанию',cur?M(Math.max(0,cur.diff)):'—',cur&&cur.diff<0?'удержано больше оценки':'при выводе или в конце года',cur&&cur.diff>0?'neg':'',S2)}</div>`;
  chart('c-tax',bars,{labels:rows.map(r=>String(r.year)),series:[{n:'Оценка НДФЛ',c:S1,v:rows.map(r=>r.estimate)},{n:'Удержано брокером',c:S2,v:rows.map(r=>r.withheld)}]});
  out+=`<div class="g c-1-2"><div class="card"><h2>Удержанные налоги по видам</h2>${withheld?hbars(TAXK.filter(k=>lf[k]).map((k,i)=>({n:L[k],v:lf[k],c:PAL[i]})),S1,null,1):'<div class="empty">Налоги не удерживались</div>'}</div>
    <div class="card"><h2>Оценка и факт по годам, ₽</h2><div id="c-tax" class="chart"></div></div></div>`;
  out+=`<div class="card" style="padding:6px 8px"><div class="tbl"><table><thead><tr><th>Год</th><th>Результат сделок</th><th>Дивиденды, купоны, РЕПО</th><th>Налоговая база</th><th>Оценка НДФЛ</th><th>Удержано</th><th>Разница</th></tr></thead><tbody>`+
    (rows.length?rows.slice().reverse().map(r=>`<tr><td><b>${r.year}</b></td><td class="num ${cls(r.trade)}">${SM(r.trade)}</td><td class="num">${M(r.income)}</td><td class="num">${M(Math.max(0,r.trade)+r.income)}</td>
    <td class="num">${M(r.estimate)}</td><td class="num">${M(r.withheld)}</td><td class="num ${r.diff>0.5?'neg':r.diff<-0.5?'pos':''}">${SM(r.diff)}</td></tr>`).join(''):'<tr><td colspan="7" class="l mu">Нет данных</td></tr>')+
    `</tbody></table></div></div><p class="note"><b>Это оценка, а не декларация.</b> Ставка: 13 %; с 2021 по 2024 — 15 % с части базы свыше 5 млн ₽; с 2025 — 15 % свыше 2,4 млн ₽.
    База: положительный результат продаж + дивиденды + купоны + доход по РЕПО в рублях. Не учтены убытки прошлых лет, льгота долгосрочного владения, ИИС, иностранные дивиденды и курсовые разницы. Точные суммы рассчитывает брокер как налоговый агент.</p>`;
  return out;
}

