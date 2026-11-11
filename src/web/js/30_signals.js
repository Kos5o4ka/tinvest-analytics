/* ── Сигналы: дешевле/дороже аналогов, история сигналов, возможные замены в портфеле ── */
S.sig={d:null,key:'',err:null,loading:false,f:{rmin:'',sector:'',dmax:'all',turn:'1000000',sort:'z',outl:false,worse:false,more:{c:false,r:false}},fee:'0.3',thr:'1'};
const SG_NOTE='Сравнение с аналогами не учитывает все риски; справочная информация, не инвестиционная рекомендация.';
function sigKey(){const f=S.sig.f;return[S.account,f.turn,S.sig.fee,S.sig.thr].join('|')}
function loadSig(force){
  const k=sigKey();if(S.sig.loading&&!force)return;
  S.sig.loading=true;S.sig.err=null;
  const p=new URLSearchParams({account:S.account,min_turn:S.sig.f.turn,fee:S.sig.fee,threshold:S.sig.thr});if(force)p.set('force','1');
  api('/api/signals?'+p).then(j=>{S.sig.loading=false;S.sig.d=j;S.sig.key=k;if(S.page==='sig')renderSoon()})
    .catch(e=>{S.sig.loading=false;S.sig.err=e.message||String(e);S.sig.key=k;if(S.page==='sig')renderSoon()});
}
const sgN=(v,d=2)=>v==null||isNaN(v)?'—':Number(v).toFixed(d).replace('.',',');
const sgS=(v,d=2)=>v==null||isNaN(v)?'—':(v>0?'+':'')+sgN(v,d);
function sgSpark(h){
  if(!h||h.length<2)return'';
  const w=64,hh=18,mn=Math.min(...h),mx=Math.max(...h),r=(mx-mn)||1;
  const pts=h.map((v,i)=>(i/(h.length-1)*w).toFixed(1)+','+(hh-2-(v-mn)/r*(hh-4)).toFixed(1)).join(' ');
  return`<svg class="sg-sp" width="${w}" height="${hh}" viewBox="0 0 ${w} ${hh}"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
}
function sgRows(side){
  const f=S.sig.f,d=S.sig.d,dm=f.dmax==='all'?1e9:+f.dmax,ri=f.rmin?RSC.indexOf(f.rmin):99;
  const rs=d.rows.filter(r=>(side>0?r.diff>=d.eps:r.diff<=-d.eps)&&(f.outl||!r.outlier)&&RSC.indexOf(r.rating)<=ri&&r.dur<=dm&&(!f.sector||r.sector===f.sector)&&r.turn>=+f.turn);
  const k={z:r=>Math.abs(r.z),diff:r=>Math.abs(r.diff),streak:r=>r.streak*1e3+Math.abs(r.z),turn:r=>r.turn}[f.sort]||(r=>Math.abs(r.z));
  return rs.sort((a,b)=>k(b)-k(a));
}
function sgTable(side){
  const rs=sgRows(side),d=S.sig.d,key=side>0?'c':'r',more=S.sig.f.more[key],lim=more?60:15,hasH=d.meta.hist_days>=2;
  if(!rs.length)return`<div class="empty" style="padding:26px">Нет выпусков под выбранные фильтры</div>`;
  return`<div class="tbl"><table class="sg-t"><thead><tr><th class="l">Выпуск</th><th>Рейтинг</th><th class="l">Сектор</th><th>Дюр., г.</th><th>Дох., %</th><th>Спред</th><th>Медиана аналогов</th><th>Δ п.п.</th><th title="Отклонение в единицах разброса аналогов (MAD)">z</th><th>Оборот</th>${hasH?'<th title="Сколько снимков подряд выпуск был дешевле/дороже аналогов (снимок раз в день)">Дней подряд</th><th>Тренд</th>':''}</tr></thead><tbody>`
    +rs.slice(0,lim).map(r=>`<tr data-isin="${esc(r.isin)}" title="Аналоги: ${esc(r.refs.map(a=>a.name).join(', '))}"><td class="l"><b>${esc(r.name)}</b>${r.outlier?' <span class="tag" title="Отклонение или доходность аномально велики: возможен дефолтный выпуск или некорректные данные">выброс</span>':''}${r.amort?' <span class="tag">аморт</span>':''}${r.sub?' <span class="tag">суборд</span>':''}<small class="mu sg-isin">${esc(r.isin)}</small></td>
      <td><span class="tag rt rt-${esc(rBucket(r.rating).split(' ')[0])}">${esc(r.rating)}</span></td><td class="l">${esc(SECT[r.sector]||r.sector||'—')}</td>
      <td class="num">${sgN(r.dur)}</td><td class="num">${sgN(r.yield)}</td><td class="num">${sgS(r.spread)}</td><td class="num">${sgS(r.med)}</td>
      <td class="num ${side>0?'pos':'neg'}"><b>${sgS(r.diff)}</b></td><td class="num">${sgS(r.z,1)}</td><td class="num">${short(r.turn)}</td>
      ${hasH?`<td class="num">${r.streak?r.streak:'—'}</td><td class="num sg-tr ${r.trend==null?'':r.trend>0.05?'pos':r.trend<-0.05?'neg':''}">${r.hist?sgSpark(r.hist):''}${r.trend==null?'':' '+sgS(r.trend,1)}</td>`:''}</tr>`).join('')
    +`</tbody></table></div>`+(rs.length>lim?`<button class="btn ghost sg-more" data-m="${key}">Показать больше (${rs.length-lim})</button>`:'')
    +(more&&rs.length>60?'':'');
}
function sgOpt(o,pos){
  const w=o.rating_worse;
  return`<tr data-isin="${esc(o.isin)}"><td class="l"><b>${esc(o.name)}</b>${w?' <span class="tag sg-worse" title="Рейтинг ниже, чем у текущей бумаги: более высокая доходность во многом плата за риск">рейтинг ниже</span>':''}<small class="mu sg-isin">${esc(o.isin)}</small></td>
    <td><span class="tag rt rt-${esc(rBucket(o.rating).split(' ')[0])}">${esc(o.rating)}</span></td><td class="num">${sgN(o.dur)}</td><td class="num">${sgN(o.yield)}</td>
    <td class="num ${o.diff>=0.25?'pos':o.diff<=-0.25?'neg':''}">${sgS(o.diff)}</td><td class="num">${short(o.turn)}</td>
    <td class="num">${sgS(o.gain_pp)}</td><td class="num pos"><b>${sgS(o.net_pp)}</b></td><td class="num">${M(o.gain_rub_year,'rub')}</td><td class="num">${o.breakeven_months==null?'—':sgN(o.breakeven_months,1)}</td></tr>`;
}
function sgRepl(){
  const d=S.sig.d,f=S.sig.f;let h='';
  const rep=d.replacements.map(p=>({p,o:f.worse?p.options.concat(p.options_worse):p.options})).filter(x=>x.o.length);
  if(!rep.length)return`<div class="empty" style="padding:26px">${(S.bonds&&S.bonds.rows&&S.bonds.rows.length)||d.skipped.length?'При заданных порогах и издержках явных вариантов для изучения нет.':'В выбранном портфеле нет облигаций.'}</div>`;
  rep.forEach(({p,o})=>{
    h+=`<div class="sg-pos"><div class="sg-ph" data-isin="${esc(p.isin)}"><div><b>${esc(p.name)}</b> <span class="tag rt rt-${esc(rBucket(p.rating).split(' ')[0])}">${esc(p.rating||'—')}</span></div>
      <div class="mu">позиция ${M(p.value,'rub')} · доходность ${sgN(p.yield_)} % · дюрация ${sgN(p.dur)} г. · ${p.diff==null?'':`к аналогам ${sgS(p.diff)} п.п. · `}издержки перехода ≈ ${M(p.cost_rub,'rub')} (${sgN(p.cost_pp)} % позиции: комиссии ${M(p.commission_rub,'rub')}${p.tax_rub?`, налог с прибыли ${M(p.tax_rub,'rub')}`:''})</div></div>
      <div class="tbl"><table class="sg-t"><thead><tr><th class="l">Возможная замена для изучения</th><th>Рейтинг</th><th>Дюр., г.</th><th>Дох., %</th><th>Δ к аналогам</th><th>Оборот</th><th title="Разница доходностей, п.п. в год">Разница, п.п.</th><th title="Разница за вычетом издержек, размазанных на срок до погашения более короткой из бумаг (не более 5 лет)">После издержек, п.п./год</th><th>₽ в год на позицию</th><th title="За сколько месяцев разница в доходности покроет издержки перехода">Окупаемость, мес.</th></tr></thead><tbody>${o.map(sgOpt).join('')}</tbody></table></div></div>`});
  return h;
}
function pSig(){
  const s=S.sig,f=s.f;
  if(s.key!==sigKey()&&!s.loading){s.d=null;s.err=null}
  if(!s.d){
    if(!s.loading&&!s.err)loadSig();
    chart('sg-root',bindSig);
    return`<div id="sg-root"><div class="card">${s.err?`<div class="msg err">${esc(s.err)} <button class="btn ghost" id="sg-ref">Повторить</button></div>`:waitBox('Сравниваю выпуски с аналогами (первый расчёт может занять до минуты: загружается рынок)…')}</div></div>`}
  const d=s.d,k=d.kpis,m=d.meta;
  const sectors=[...new Set(d.rows.map(r=>r.sector).filter(Boolean))].sort((a,b)=>(SECT[a]||a).localeCompare(SECT[b]||b));
  const opt=(v,t,c)=>`<option value="${v}" ${String(c)===String(v)?'selected':''}>${t}</option>`;
  const nrep=d.replacements.length;
  chart('sg-root',bindSig);
  return`<div id="sg-root">${s.err?`<div class="msg err">${esc(s.err)}</div>`:''}
  <div class="g g4 sg-k">${kpi('Выпусков сравнено',k.universe,`ликвидных, оборот от ${short(d.params.min_turn)} ₽`)}
    ${kpi('Дешевле аналогов',k.cheap,`из них заметно (z ≥ 2): ${k.cheap_strong}`,'pos')}
    ${kpi('Дороже аналогов',k.rich,`из них заметно (z ≤ −2): ${k.rich_strong}`,'neg')}
    ${kpi('Возможных замен в портфеле',nrep,`пороги: от ${sgN(d.params.threshold,1)} п.п. после издержек`)}</div>
  <div class="card"><h2>Дешевле и дороже аналогов<span class="sp">спред к КБД против медианы 12 похожих выпусков</span></h2>
    <p class="note" style="margin-bottom:12px">Для каждой рублёвой корпоративной облигации с рейтингом (без флоатеров и бессрочных) подбираются ближайшие аналоги: рейтинг в пределах двух ступеней, сопоставимая дюрация, сектор, тип выпуска — так же, как в карточке облигации. «Дешевле» — спред к КБД выше медианы аналогов (доходность выше при сопоставимом риске), «дороже» — ниже. z — отклонение в единицах разброса аналогов (робастная оценка по MAD): чем больше |z|, тем заметнее выпуск выделяется на фоне аналогов. Расхождение часто объясняется рисками, которых нет в рейтинге.</p>
    <div class="flt">
      <label class="field"><span>Рейтинг не ниже</span><select class="in" id="sg-r"><option value="">любой</option>${RSC.slice(0,16).map(x=>opt(x,x,f.rmin)).join('')}</select></label>
      <label class="field"><span>Сектор</span><select class="in" id="sg-s"><option value="">любой</option>${sectors.map(x=>opt(x,SECT[x]||x,f.sector)).join('')}</select></label>
      <label class="field"><span>Дюрация не более</span><select class="in" id="sg-d">${[['1','1 года'],['2','2 лет'],['3','3 лет'],['5','5 лет'],['all','любая']].map(([v,t])=>opt(v,t,f.dmax)).join('')}</select></label>
      <label class="field"><span>Оборот за день от</span><select class="in" id="sg-t">${[['0','любой'],['300000','0,3 млн ₽'],['1000000','1 млн ₽'],['5000000','5 млн ₽'],['20000000','20 млн ₽']].map(([v,t])=>opt(v,t,f.turn)).join('')}</select></label>
      <label class="field"><span>Сортировать по</span><select class="in" id="sg-o">${[['z','z-оценке'],['diff','отклонению, п.п.'],['streak','дням подряд'],['turn','обороту']].map(([v,t])=>opt(v,t,f.sort)).join('')}</select></label>
      <label class="sw"><input type="checkbox" id="sg-x" ${f.outl?'checked':''}><i></i><div><b>Показывать выбросы</b><small>${k.outliers} выпусков с аномалиями</small></div></label>
    </div>
    <div class="sg-g2">
      <div><h3 class="sg-h pos">Дешевле аналогов</h3>${sgTable(1)}</div>
      <div><h3 class="sg-h neg">Дороже аналогов</h3>${sgTable(-1)}</div></div>
    <p class="note" style="margin-top:12px">${m.hist_days>=2?`История сигналов копится ежедневно по будним дням (снимок при расчёте): накоплено дней — ${m.hist_days}, с ${ddm(m.hist_from)}. «Дней подряд» — число последних снимков подряд, в которых выпуск оставался дешевле/дороже аналогов не менее чем на ${sgN(d.eps,2)} п.п.; «Тренд» — изменение отклонения за ≈ 5 снимков.`:`История сигналов копится ежедневно по будним дням, начиная с сегодняшнего дня: сейчас накоплено дней — ${m.hist_days}. Колонки «Дней подряд» и «Тренд» появятся, когда снимков будет хотя бы два.`}
    Расчёт: ${sgN(m.calc_s,1)} с, выпусков в сравнении ${m.pool}. Выбросы (отклонение более 8 п.п., доходность выше 40 % или спред ниже −6 п.п.) скрыты по умолчанию.</p></div>
  <div class="card sg-rep"><h2>Возможные замены в вашем портфеле<span class="sp">для изучения, не рекомендация</span></h2>
    <p class="note" style="margin-bottom:12px">Для каждой рублёвой корпоративной облигации портфеля ищутся похожие выпуски (близкие рейтинг, срок, сектор) с более высокой рыночной доходностью. Учитываются комиссия за продажу и покупку, налог ${sgN(d.params.tax,0)} % с прибыли при продаже выше цены покупки (НКД не учитывается), ликвидность целевого выпуска. Издержки равномерно относятся на срок до погашения более короткой из двух бумаг (не более 5 лет). Показываются варианты, где разница после издержек не меньше порога; выпуски с более низким рейтингом показываются только по отдельному переключателю. Бóльшая доходность обычно отражает бóльший риск, а не недооценку.</p>
    <div class="flt">
      <label class="field"><span>Комиссия за сделку, %</span><input class="in" id="sg-fee" type="number" min="0" max="5" step="0.05" value="${esc(s.fee)}"></label>
      <label class="field"><span>Порог после издержек, п.п./год</span><input class="in" id="sg-thr" type="number" min="0" max="20" step="0.5" value="${esc(s.thr)}"></label>
      <label class="sw"><input type="checkbox" id="sg-w" ${f.worse?'checked':''}><i></i><div><b>Показывать с более низким рейтингом</b><small>помечаются отдельно</small></div></label>
      <button class="btn ghost" id="sg-ref">Пересчитать</button>
    </div>
    ${sgRepl()}
    ${d.skipped.length?`<p class="note" style="margin-top:10px">Не сравнивались: ${d.skipped.map(x=>esc(x.name)+' ('+esc(x.why)+')').join('; ')}.</p>`:''}</div>
  <p class="note">${SG_NOTE} Данные: Мосбиржа (ISS), каталог T-Invest, публичные рейтинги; КБД — кривая бескупонной доходности Мосбиржи.</p></div>`;
}
function bindSig(){
  const f=S.sig.f,again=()=>render();
  const on=(id,fn)=>{const e=$(id);if(e)e.onchange=fn};
  on('#sg-r',e=>{f.rmin=e.target.value;again()});on('#sg-s',e=>{f.sector=e.target.value;again()});on('#sg-d',e=>{f.dmax=e.target.value;again()});
  on('#sg-o',e=>{f.sort=e.target.value;again()});on('#sg-x',e=>{f.outl=e.target.checked;again()});on('#sg-w',e=>{f.worse=e.target.checked;again()});
  on('#sg-t',e=>{f.turn=e.target.value;S.sig.d=null;again()});
  const fee=$('#sg-fee'),thr=$('#sg-thr');
  const apply=()=>{S.sig.fee=fee.value||'0.3';S.sig.thr=thr.value||'1';S.sig.d=null;render()};
  if(fee)fee.onchange=apply;if(thr)thr.onchange=apply;
  const r=$('#sg-ref');if(r)r.onclick=()=>{S.sig.d=null;S.sig.err=null;S.sig.key=sigKey();loadSig(true);render()};
  document.querySelectorAll('#sg-root .sg-more').forEach(b=>b.onclick=()=>{f.more[b.dataset.m]=true;render()});
}
