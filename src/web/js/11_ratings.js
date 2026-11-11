/* ── кредитные рейтинги ── */
const RSC=['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC','CC','C','D'];
const rBucket=v=>{if(!v)return'нет рейтинга';const i=RSC.indexOf(v);return i===0?'AAA':i<=3?'AA':i<=6?'A':i<=9?'BBB':'BB и ниже'};
function ratingTag(r){
  const t=r.all.map(x=>`${x.agency}: ${x.rating} · ${x.issuer}${x.approx?' (приблизительное совпадение названия)':''} · от ${x.date}${x.outlook?' · '+x.outlook:''}`).join('\n');
  return`<span class="tag rt rt-${rBucket(r.v).split(' ')[0]}" title="${esc(t)}">${r.approx?'≈ ':''}${esc(r.v)}</span>`;
}
function ratingsCard(b){
  const info=b.ratings_info||{},tot=(b.ratings||[]).reduce((a,x)=>a+x[1],0)||1;
  const COL={'AAA':S3,'AA':S3,'A':S1,'BBB':S4,'BB и ниже':S8,'нет рейтинга':'#6f7686'};
  const order=['AAA','AA','A','BBB','BB и ниже','нет рейтинга'],m=Object.fromEntries(b.ratings||[]);
  const items=order.filter(k=>m[k]).map(k=>({n:k==='нет рейтинга'?'Нет данных':k,v:m[k],c:COL[k],s:pctp(m[k]/tot*100)}));
  const st=info.running?`Загружаю рейтинги… ${esc(info.progress||'')}`:info.updated?`Обновлено ${new Date(info.updated*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})} · эмитентов в базе: ${info.count}`:'Рейтинги ещё не загружены';
  if(info.running&&!S._rtTimer)S._rtTimer=setTimeout(async()=>{S._rtTimer=null;if(S.page!=='bonds')return;try{S.bonds=await api('/api/bonds?'+new URLSearchParams({account:S.account}));renderSoon()}catch(e){}},5000);
  return`<div class="card"><h2>Кредитные рейтинги эмитентов<span class="sp">${st}</span></h2>
    <div class="g g2"><div>${hbars(items,S1,null,0)}</div>
    <div class="t2" style="font-size:13px;line-height:1.6">Распределение облигаций портфеля по рейтингу по национальной шкале (АКРА, Эксперт РА, НКР, НРА). Если у эмитента несколько оценок, берётся наименьшая.
      Пометка «≈» — название эмитента совпало не полностью, проверьте по подсказке. Нет данных — рейтинг не найден в базе, это не значит, что он низкий.
      <div class="row" style="margin-top:12px"><button class="btn ghost" id="rt-ref" ${info.running?'disabled':''}>Обновить рейтинги</button></div></div></div>
    <p class="note">Источник — публичный канал @issuerRatings (пресс-релизы агентств). Рейтинги обновляются автоматически раз в сутки при открытой программе. Не является инвестиционной рекомендацией.</p></div>`;
}


function bondInsights(b){
  const rows=b.rows.filter(r=>r.value_rub>0),tot=rows.reduce((a,r)=>a+r.value_rub,0)||1,out=[];
  const w=(f)=>rows.filter(f).reduce((a,r)=>a+r.value_rub,0)/tot*100;
  const sp=rows.filter(r=>r.spread!=null),spv=sp.reduce((a,r)=>a+r.value_rub,0);
  if(spv)out.push(['Спред к КБД',`В среднем портфель даёт <b>${(sp.reduce((a,r)=>a+r.spread*r.value_rub,0)/spv).toFixed(2).replace('.',',')} п.п.</b> к безрисковой кривой (КБД) при той же дюрации — это ваша плата за кредитный риск и неликвидность.`]);
  const low=sp.filter(r=>r.spread<0.5).sort((a,c)=>a.spread-c.spread);
  if(low.length)out.push(['Мало платят за риск',`Выше КБД менее чем на 0,5 п.п.: ${low.slice(0,4).map(r=>`${esc(r.name)} (${r.spread>0?'+':''}${r.spread.toFixed(2).replace('.',',')} п.п.)`).join(', ')}${low.length>4?' и ещё '+(low.length-4):''}. Проверьте, оправдан ли риск эмитента или выгоднее ОФЗ.`]);
  const nr=w(r=>!r.rating);if(nr>0.5)out.push(['Без рейтинга',`<b>${nr.toFixed(0)}%</b> облигационной части — выпуски без найденного рейтинга агентств (${rows.filter(r=>!r.rating).slice(0,3).map(r=>esc(r.name)).join(', ')}${rows.filter(r=>!r.rating).length>3?'…':''}). Рейтинга нет в базе — это не значит, что он низкий.`]);
  const weak=rows.filter(r=>r.rating&&RSC.indexOf(r.rating.v)>=7);
  if(weak.length)out.push(['Рейтинг ниже A−',`${weak.map(r=>`${esc(r.name)} (${esc(r.rating.v)})`).join(', ')} — суммарно <b>${w(r=>r.rating&&RSC.indexOf(r.rating.v)>=7).toFixed(0)}%</b> облигаций.`]);
  const hy=sp.filter(r=>r.spread>6);if(hy.length)out.push(['Очень высокая доходность',`Спред больше 6 п.п.: ${hy.map(r=>`${esc(r.name)} (+${r.spread.toFixed(1).replace('.',',')})`).join(', ')}. Рынок закладывает повышенный риск — перепроверьте эмитента.`]);
  const top=rows.slice().sort((a,c)=>c.value_rub-a.value_rub).slice(0,3);
  out.push(['Концентрация',`Три крупнейшие позиции — <b>${(top.reduce((a,r)=>a+r.value_rub,0)/tot*100).toFixed(0)}%</b> облигаций: ${top.map(r=>esc(r.name)).join(', ')}.`]);
  const soon=new Date(Date.now()+90*864e5).toISOString().slice(0,10),today=new Date().toISOString().slice(0,10);
  const ev=rows.filter(r=>(r.call&&r.call>=today&&r.call<=soon)||(r.maturity&&r.maturity>=today&&r.maturity<=soon));
  if(ev.length)out.push(['Ближайшие 90 дней',`Оферта или погашение: ${ev.map(r=>`${esc(r.name)} — ${ddm(r.call&&r.call>=today&&r.call<=soon?r.call:r.maturity)}${r.call&&r.call>=today&&r.call<=soon?' (оферта)':''}`).join('; ')}.`]);
  return out;
}
function insightsCard(b){
  const L=bondInsights(b);if(!L.length)return'';
  return`<div class="card"><h2>Анализ облигаций портфеля</h2><div class="ins">${L.map(([t,h])=>`<div><b>${t}</b><span>${h}</span></div>`).join('')}</div>
    <p class="note">Автоматические наблюдения по данным портфеля, рейтингов и КБД. Это справочная информация, а не инвестиционная рекомендация.</p></div>`;
}

