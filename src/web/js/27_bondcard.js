// ── карточка облигации (боковая панель): клик по любому элементу с data-isin ──
const BC={stack:[],tok:0,all:false,iss:{}};
const BC_SEC={financial:'Финансы',industrials:'Промышленность',materials:'Сырьё',energy:'Энергетика',consumer:'Потребительский',government:'Государственные',real_estate:'Недвижимость',telecom:'Телеком',municipal:'Муниципальные',utilities:'Коммунальные',it:'IT',health_care:'Здравоохранение',other:'Прочее'};
const BC_EV={coupon:'Купон',amort:'Амортизация',offer:'Оферта',redemption:'Погашение'};
const BC_OK={put:['PUT — право продать эмитенту','of-t-put','Право держателя: в период предъявления можно подать заявку через брокера, эмитент выкупит бумагу по цене оферты.'],call:['CALL — эмитент может погасить досрочно','of-t-call','Право эмитента: он может досрочно погасить выпуск. Заявку подавать не нужно, но возможен риск реинвестирования.'],unknown:['тип не указан','of-t-unk','Источники не сообщают, чей это выбор — держателя или эмитента. Проверьте документы выпуска.']};
const bcOfKind=k=>{const t=BC_OK[k]||BC_OK.unknown;return`<span class="tag ${t[1]}" title="${esc(t[2])}">${esc(t[0])}</span>`};
const BC_KR_SRC={cbr:'ключевая ставка по прогнозу ЦБ',survey:'ключевая ставка по опросу аналитиков ЦБ',market:'ключевая ставка по ожиданиям рынка (КБД)',flat:'текущая ключевая ставка'};
const BC_RISK={RISK_LEVEL_LOW:'низкий',RISK_LEVEL_MODERATE:'средний',RISK_LEVEL_HIGH:'высокий'};

document.addEventListener('click',e=>{
  const t=e.target.closest('[data-isin]');
  if(t&&t.dataset.isin&&!e.target.closest('a,button,input,select'))openBond(t.dataset.isin);
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('bc-ov'))closeBond()});

function closeBond(){
  BC.stack=[];BC.tok++;
  const o=document.getElementById('bc-ov');if(o)o.remove();
  document.body.classList.remove('bc-open');
}
function bcMount(){
  let o=document.getElementById('bc-ov');
  if(!o){
    o=document.createElement('div');o.id='bc-ov';
    o.innerHTML='<div class="bc-dr" id="bc-dr" role="dialog" aria-modal="true"></div>';
    o.addEventListener('mousedown',ev=>{if(ev.target===o)closeBond()});
    document.body.appendChild(o);document.body.classList.add('bc-open');
  }
  return document.getElementById('bc-dr');
}
function bcBar(){
  const back=BC.stack.length>1?'<button class="btn ghost" id="bc-back">← Назад</button>':'';
  const wt=typeof watchToggle==='function'?'<button class="btn ghost" id="bc-watch" title="Добавить выпуск в список наблюдения">★ В наблюдение</button>':'';
  return`<div class="bc-bar">${back}<span class="sp"></span>${wt}<button class="btn ghost" id="bc-x" aria-label="Закрыть">✕ Закрыть</button></div>`;
}
function bcBind(dr){
  const x=dr.querySelector('#bc-x');if(x)x.onclick=closeBond;
  const w=dr.querySelector('#bc-watch');
  if(w)w.onclick=()=>{try{watchToggle(BC.stack[BC.stack.length-1])}catch(e){}};
  const b=dr.querySelector('#bc-back');
  if(b)b.onclick=()=>{BC.stack.pop();const p=BC.stack.pop();openBond(p)};
}
async function openBond(isin){
  isin=String(isin||'').trim();if(!isin)return;
  if(BC.stack[BC.stack.length-1]!==isin)BC.stack.push(isin);
  const tok=++BC.tok,dr=bcMount();
  dr.innerHTML=bcBar()+`<div class="bc-load">Загружаю данные по ${esc(isin)}…</div>`;bcBind(dr);dr.scrollTop=0;
  let c;
  try{c=await api('/api/bond?isin='+encodeURIComponent(isin))}
  catch(e){if(tok!==BC.tok)return;dr.innerHTML=bcBar()+`<div class="bc-warn">Не удалось загрузить карточку: ${esc(e.message||e)}</div>`;bcBind(dr);return}
  if(tok!==BC.tok)return;
  dr.innerHTML=bcBar()+bcBody(c);bcBind(dr);bcCharts(dr,c);bcIssuer(dr,c,tok);
  const mr=dr.querySelector('#bc-more');
  if(mr)mr.onclick=()=>{BC.all=true;dr.innerHTML=bcBar()+bcBody(c);bcBind(dr);bcCharts(dr,c);bcIssuer(dr,c,tok);BC.all=false};
}
const bcN=(v,d=2)=>v==null||isNaN(v)?'—':Number(v).toFixed(d).replace('.',',');
function bcKpi(k,v,s,cls){return`<div class="card"><div class="k">${k}</div><div class="v num ${cls||''}">${v}</div>${s?`<div class="s">${s}</div>`:''}</div>`}
function bcBody(c){
  const m=c.market,ci=c.catalog||{},d=c.desc||{},cur=(m&&m.cur||ci.currency||'RUB').toLowerCase();
  const sec=ci.sector?BC_SEC[ci.sector]||ci.sector:null;
  let h=`<div class="bc-h"><h1>${esc(c.name||c.isin)}</h1><div class="row2"><code>${esc(c.isin)}</code>`
    +(c.rating?ratingTag(c.rating):'<span class="tag">нет рейтинга</span>')
    +(sec?`<span class="tag">${esc(sec)}</span>`:'')
    +(ci.floating?'<span class="tag">флоатер</span>':'')+(ci.amort||(d.AMORTBOND==='1')?'<span class="tag">амортизация</span>':'')
    +(ci.subordinated?'<span class="tag">субординированная</span>':'')+(ci.perpetual?'<span class="tag">бессрочная</span>':'')
    +`<a href="https://www.moex.com/ru/issue.aspx?code=${encodeURIComponent(c.isin)}" target="_blank" rel="noopener" style="margin-left:auto">Страница на Мосбирже ↗</a></div></div>`;
  if(c.errors&&c.errors.length)h+=`<div class="bc-warn">${c.errors.map(esc).join('<br>')}</div>`;
  if(m){
    const sp=m.spread;
    h+=`<div class="bc-kpis">`
      +bcKpi('Цена',bcN(m.price,2)+' %',m.nominal?`номинал ${bcN(m.nominal,0)}`:'')
      +bcKpi('Доходность',bcN(m.yield,2)+' %','к погашению/оферте')
      +bcKpi('Спред к КБД',sp==null?'—':(sp>0?'+':'')+bcN(sp,2)+' п.п.',c.kbd!=null?`КБД ${bcN(c.kbd,2)} % на ${bcN(m.dur,2)} г.`:'',sp==null?'':sp>0?'pos':'neg')
      +bcKpi('Дюрация',m.dur==null?'—':bcN(m.dur,2)+' г.',`оборот ${short(m.turn||0)}`)
      +`</div>`;
  }
  const rows=[];const add=(k,v)=>{if(v!=null&&v!=='')rows.push(`<div><span>${k}</span><span>${v}</span></div>`)};
  add('Эмитент',esc(d.EMITTER||''));
  add('Вид',esc(d.BOND_TYPE||d.TYPENAME||''));
  add('Купон',m&&m.coupon!=null?bcN(m.coupon,2)+' %'+(d.COUPONFREQUENCY?` · ${esc(d.COUPONFREQUENCY)} р/год`:''):(d.COUPONFREQUENCY?`${esc(d.COUPONFREQUENCY)} р/год`:''));
  add('Следующий купон',m&&m.next?ddm(m.next):'');
  add('Погашение',m&&m.mat?ddm(m.mat):(ci.maturity?ddm(ci.maturity):(d.MATDATE?ddm(d.MATDATE):'')));
  add('Оферты',(c.offers||[]).length?c.offers.map(o=>`${ddm(o.date)} ${bcOfKind(o.kind)}${o.period_start&&o.period_end?` <small class="mu">предъявление ${ddm(o.period_start)} – ${ddm(o.period_end)}</small>`:''}`).join('<br>')+' <a href="#" class="kb-a" data-kb="offers">Что такое put и call</a>':(m&&m.offer?ddm(m.offer)+' '+bcOfKind('put'):''));
  add('Размещена',d.ISSUEDATE?ddm(d.ISSUEDATE):'');
  add('Объём выпуска',d.ISSUESIZE?short(+d.ISSUESIZE)+' шт.':'');
  add('Номинал',d.FACEVALUE?bcN(+d.FACEVALUE,2)+' '+esc(cur.toUpperCase())+(d.INITIALFACEVALUE&&d.INITIALFACEVALUE!==d.FACEVALUE?` (первоначально ${esc(d.INITIALFACEVALUE)})`:''):'');
  add('Уровень листинга',m&&m.level?esc(m.level):esc(d.LISTLEVEL||''));
  add('Уровень риска (T-Invest)',ci.risk?esc(BC_RISK[ci.risk]||ci.risk):'');
  add('Для квалифицированных',d.ISQUALIFIEDINVESTORS==='1'?'да':d.ISQUALIFIEDINVESTORS==='0'?'нет':'');
  add('Дефолт',d.HASDEFAULT==='1'?'<b class="neg">допущен</b>':d.HASTECHNICALDEFAULT==='1'?'<b class="neg">технический</b>':(d.HASDEFAULT==='0'?'нет':''));
  add('Госномер выпуска',esc(d.REGNUMBER||''));
  h+=`<div class="card bc-sec"><h2>Ключевые параметры</h2><div class="bc-par">${rows.join('')||'<span class="mu">Нет данных</span>'}</div></div>`;
  h+=`<div class="card bc-sec" id="bc-iss"><h2>Финансы эмитента<span class="sp">отчётность РСБУ, ГИР БО ФНС</span></h2><div class="mu" style="font-size:13px">Загружаю отчётность эмитента…</div></div>`;
  // денежный поток
  const fl=c.flows||[],lim=BC.all?fl.length:12;
  h+=`<div class="card bc-sec"><h2>Денежный поток<span class="sp">ближайшие выплаты на 1 облигацию</span></h2>`;
  if(fl.length){
    h+=`<div class="tbl"><table><thead><tr><th>Дата</th><th>Событие</th><th>Сумма</th><th>% номинала / ставка</th></tr></thead><tbody>`
      +fl.slice(0,lim).map(e=>`<tr><td>${ddm(e.d)}</td><td>${BC_EV[e.t]||esc(e.t)}${e.t==='offer'&&e.kind&&e.kind!=='both'?' '+bcOfKind(e.kind):e.t==='offer'&&e.kind==='both'?' '+bcOfKind('put')+' '+bcOfKind('call'):''}</td><td class="num">${e.amt==null?'<span class="mu">по ставке</span>':e.est?`<span class="est" title="${esc(BC_KR_SRC[(c.keyrate||{}).source]||'ключевая ставка по прогнозу')} ${bcN(e.base,2)}% + спред ${bcN(e.spread,2)} п.п.">≈ ${M(e.amt,cur)}</span>`:M(e.amt,cur)}</td><td class="num">${e.pct==null?'—':(e.est?'≈ ':'')+bcN(e.pct,2)+' %'}</td></tr>`).join('')
      +`</tbody></table></div>`;
    if(c.keyrate)h+=`<p class="note" style="margin-top:8px">≈ — прогноз: ставка купона флоатера ещё не объявлена, принята равной ключевой ставке на начало купонного периода + спред эмитента к ключевой на прошлых купонах. Прогноз ключевой ставки: ${esc(c.keyrate.name)}${c.keyrate.as_of?`, на ${esc(c.keyrate.as_of)}`:''}.</p>`;
    if(fl.length>lim)h+=`<button class="btn ghost bc-more" id="bc-more">Показать все (${fl.length})</button>`;
  }else h+=`<div class="mu" style="font-size:13px">Данных о будущих выплатах нет.</div>`;
  h+=`</div>`;
  // история
  const hs=c.history||{d:[]};
  h+=`<div class="card bc-sec"><h2>История за год<span class="sp">Мосбиржа, основной режим торгов</span></h2>`;
  if(hs.d&&hs.d.length>1)h+=`<div class="mu" style="font-size:12px;margin-bottom:4px">Цена, % от номинала</div><div class="bc-ch" id="bc-ch-p"></div>
      <div class="mu" style="font-size:12px;margin:12px 0 4px">Доходность, % годовых</div><div class="bc-ch" id="bc-ch-y"></div>`;
  else h+=`<div class="mu" style="font-size:13px">История торгов недоступна.</div>`;
  h+=`</div>`;
  // кривая эмитента
  const ic=c.issuer_curve;
  if(ic&&ic.points&&ic.points.length>1)h+=`<div class="card bc-sec"><h2>Кривая эмитента<span class="sp">${ic.points.length} выпусков в обращении: доходность по сроку</span></h2><div class="bc-ic" id="bc-ic"></div>
    <div class="mu" style="font-size:12px;margin-top:6px"><span style="color:var(--ac)">●</span> этот выпуск · <span style="color:#3987e5">●</span> другие выпуски эмитента · пунктир — кривая бескупонной доходности (КБД). Клик по точке открывает карточку выпуска.</div></div>`;
  // аналоги
  const an=c.analogs||[];
  h+=`<div class="card bc-sec"><h2>Аналоги<span class="sp">похожий рейтинг, срок и тип</span></h2>`;
  if(c.rel&&c.rel.text){const ok=c.rel.diff>=0.25,bad_=c.rel.diff<=-0.25;
    h+=`<div class="bc-rel"><b class="${ok?'pos':bad_?'neg':''}">${esc(c.rel.text)}.</b> Медианный спред аналогов: ${bcN(c.rel.median_spread,2)} п.п. «Дешевле» — выше доходность при сопоставимом риске, но это может отражать и риски, которых нет в рейтинге.</div>`}
  if(an.length){
    h+=`<div class="tbl"><table><thead><tr><th>Выпуск</th><th>Рейтинг</th><th>Сектор</th><th>Дюр., г.</th><th>Доходность</th><th>Спред</th><th>Δ дох.</th><th>Оборот</th></tr></thead><tbody>`
      +an.map(a=>`<tr data-isin="${esc(a.isin)}" title="Открыть карточку"><td class="l">${esc(a.name)}${a.floating?' <span class="tag">флоат</span>':''}${a.amort?' <span class="tag">аморт</span>':''}</td>
        <td>${a.rating?`<span class="tag rt rt-${esc(rBucket(a.rating).split(' ')[0])}">${esc(a.rating)}</span>`:'<span class="mu">—</span>'}</td>
        <td>${esc(BC_SEC[a.sector]||a.sector||'—')}</td><td class="num">${bcN(a.dur,2)}</td><td class="num">${bcN(a.yield,2)} %</td>
        <td class="num">${a.spread==null?'—':(a.spread>0?'+':'')+bcN(a.spread,2)}</td>
        <td class="num ${a.dy>0?'pos':a.dy<0?'neg':''}">${a.dy==null?'—':(a.dy>0?'+':'')+bcN(a.dy,2)}</td><td class="num">${short(a.turn||0)}</td></tr>`).join('')
      +`</tbody></table></div>`;
  }else h+=`<div class="mu" style="font-size:13px">Подходящих аналогов не найдено${m?'':' (нет рыночных данных по выпуску)'}.</div>`;
  h+=`</div><p class="note" style="margin-top:14px">Справочная информация на основе открытых данных Мосбиржи, каталога T-Invest и публичных рейтингов. Не является инвестиционной рекомендацией. Аналоги подобраны автоматически по рейтингу, сроку, сектору и типу выпуска; сравнение спреда не учитывает всех различий в риске и ликвидности.</p>`;
  return h;
}
function bcIssuerCurve(el,ic){
  const W=el.clientWidth||560,H=250,pl=44,pr=14,pt=12,pb=30,P=ic.points,K=ic.kbd||[];
  const xs=P.map(p=>p.dur).concat(K.map(k=>k[0])),ys=P.map(p=>p.yield).concat(K.map(k=>k[1]));
  const x0=0,x1=Math.max(...xs)*1.05||1,ny=nice(Math.min(...ys)*0.9,Math.max(...ys)*1.05,5),y0=ny.lo,y1=ny.hi,pw=W-pl-pr,ph=H-pt-pb;
  const X=v=>pl+(v-x0)/(x1-x0)*pw,Y=v=>pt+ph-(v-y0)/(y1-y0)*ph;
  let g='';
  for(let v=y0;v<=y1+ny.step/2;v+=ny.step)g+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax num" x="${pl-6}" y="${Y(v)+4}" text-anchor="end">${+v.toFixed(1)}%</text>`;
  const nx=Math.max(2,Math.min(8,Math.round(pw/80))),st=x1/nx;
  for(let i=0;i<=nx;i++){const v=i*st;g+=`<text class="ax num" x="${X(v)}" y="${H-8}" text-anchor="middle">${bcN(v,1)} г.</text>`}
  if(K.length>1)g+=`<polyline class="ic-kbd" points="${K.map(k=>X(k[0]).toFixed(1)+','+Y(k[1]).toFixed(1)).join(' ')}"/>`;
  const fl=P.filter(p=>!p.floating);
  if(fl.length>1)g+=`<polyline class="ic-ln" points="${fl.map(p=>X(p.dur).toFixed(1)+','+Y(p.yield).toFixed(1)).join(' ')}"/>`;
  P.slice().sort((a,b)=>a.me-b.me).forEach(p=>{
    g+=`<circle class="ic-pt${p.me?' ic-me':''}" data-isin="${esc(p.isin)}" cx="${X(p.dur)}" cy="${Y(p.yield)}" r="${p.me?7:5}" fill="${p.me?'var(--ac)':'#3987e5'}"><title>${esc(p.name)} · дох. ${bcN(p.yield,2)} % · дюр. ${bcN(p.dur,2)} г.${p.spread==null?'':' · спред '+(p.spread>0?'+':'')+bcN(p.spread,2)}${p.rating?' · '+esc(p.rating):''}${p.floating?' · флоатер':''}</title></circle>`});
  el.innerHTML=`<svg width="${W}" height="${H}">${g}</svg>`;
}
function bcIssIfrs(j){
  const b=j.ifrs,s=b.score,f=b.fin,m=j.market||{},c=f.ltm||f.years[f.years.length-1]||{},X=(v,d)=>v==null?'—':bcN(v,d)+'×',Pc=v=>v==null?'—':bcN(v*100,1)+' %';
  const rs=j.score&&j.score.ok?j.score:null;
  let h=`<div class="bc-iss-top"><span class="iss-sc iss-${esc(s.key)}"><b>${s.score}</b> ${esc(s.label)}</span><span class="mu" style="font-size:12.5px">МСФО группы (${esc(b.ticker)}) · ${esc(s.period||'')}</span></div>
    <div class="mu" style="font-size:12.5px;margin-bottom:8px">${esc(b.how)}</div>`;
  h+=s.bank?`<div class="bc-kpis">${bcKpi('ROE',Pc(c.roe),'рентабельность капитала')}${bcKpi('Капитал / активы',Pc(c.eq_ratio),'норма от 8–10 %')}${bcKpi('Неработающие кредиты',Pc(c.npl),'норма до 4–5 %')}${bcKpi('Достаточность капитала',Pc(c.car),'норма от 12 %')}</div>`
    :`<div class="bc-kpis">${bcKpi('Покрытие процентов',X(c.cover,1),'EBITDA / проценты; норма от 4–6')}${bcKpi('Чистый долг / EBITDA',c.net_debt!=null&&c.net_debt<=0?'нет':X(c.nd_ebitda,1),'норма до 2–3')}
    ${bcKpi('Капитал / активы',c.eq_ratio==null?'—':bcN(c.eq_ratio*100,0)+' %','норма от 25–40 %')}${bcKpi('Рентабельность EBITDA',Pc(c.margin_ebitda),'доля EBITDA в выручке')}</div>`;
  if(m.key)h+=`<div class="bc-rel"><b class="${m.key==='mkt_higher'?'neg':m.key==='mkt_lower'?'':'pos'}">${esc(m.text)}</b></div>`;
  if(j.history&&(j.history.defaults||j.history.tech))h+=`<div class="bc-warn">${esc(j.history.verdict)}</div>`;
  h+=`<div class="mu" style="font-size:12.5px;margin-top:6px">${rs?'Для сравнения, РСБУ отдельной компании: '+rs.score+' ('+esc(rs.label)+'). ':''}<a href="${esc(b.url)}" target="_blank" rel="noopener">Источник: smart-lab ↗</a></div>
    <button class="btn ghost bc-more" id="bc-iss-more">Подробнее об эмитенте →</button><p class="note" style="margin-top:8px">Скоринг от 0 до 100 по консолидированной отчётности группы (МСФО). Данные агрегатора smart-lab, могут отличаться от официальной отчётности. Не инвестиционная рекомендация.</p>`;
  return h;
}
function bcIssHtml(j,isin){
  const s=j.score||{},f=j.fin||{years:[]},m=j.market||{},is=j.issuer||{};
  if(!j.ok)return`<div class="mu" style="font-size:13px">${esc((j.errors||['Не удалось загрузить данные об эмитенте.'])[0])}</div>`;
  if(j.ifrs&&j.ifrs.score&&j.ifrs.score.ok&&j.ifrs.fin&&j.ifrs.fin.years&&j.ifrs.fin.years.length)return bcIssIfrs(j);
  if(!s.ok)return`<div class="mu" style="font-size:13px">${esc(s.reason||f.note||'Нет данных по РСБУ.')}</div>${j.history?`<div class="bc-rel" style="margin-top:8px">${esc(j.history.verdict)}</div>`:''}<button class="btn ghost bc-more" id="bc-iss-more">Подробнее об эмитенте →</button>`;
  const y=f.years[f.years.length-1]||{},fm=s.fin_mode,X=(v,d)=>v==null?'—':bcN(v,d)+'×';
  const nd=y.net_debt!=null&&y.net_debt<=0?'нет':X(y.nd_ebit,1);
  let h=`<div class="bc-iss-top"><span class="iss-sc iss-${esc(s.key)}"><b>${s.score}</b> ${esc(s.label)}</span><span class="mu" style="font-size:12.5px">${esc(is.short||'')} · по отчётности за ${s.year} г.</span></div>
    <div class="bc-kpis">${bcKpi('Покрытие процентов',X(y.cover,1),'EBIT / проценты; норма от 3–4')}
    ${fm?bcKpi('Долг / капитал',X(y.debt_eq,1),'для лизинга до 5–8'):bcKpi('Чистый долг / EBIT',nd,'норма до 2–3 лет')}
    ${bcKpi('Капитал / активы',y.eq_ratio==null?'—':bcN(y.eq_ratio*100,0)+' %','норма от 20–30 %')}
    ${fm?bcKpi('Рентабельность EBIT',y.margin==null||y.margin>1?'—':bcN(y.margin*100,1)+' %','доля прибыли в выручке'):bcKpi('Текущая ликвидность',X(y.cur_liq,2),'норма от 1,2')}</div>`;
  if(m.key)h+=`<div class="bc-rel"><b class="${m.key==='mkt_higher'?'neg':m.key==='mkt_lower'?'':'pos'}">${esc(m.text)}</b></div>`;
  if(j.history&&(j.history.defaults||j.history.tech))h+=`<div class="bc-warn">${esc(j.history.verdict)}</div>`;
  h+=`<button class="btn ghost bc-more" id="bc-iss-more">Подробнее об эмитенте →</button><p class="note" style="margin-top:8px">Скоринг от 0 до 100 по открытой отчётности отдельной компании (РСБУ): может не отражать положение группы. Не инвестиционная рекомендация.</p>`;
  return h;
}
function bcIssuer(dr,c,tok){
  const box=dr.querySelector('#bc-iss');if(!box)return;
  const isin=c.isin,put=j=>{if(tok!==BC.tok||!document.body.contains(box))return;
    box.innerHTML=`<h2>Финансы эмитента<span class="sp">${j.ifrs&&j.ifrs.score&&j.ifrs.score.ok?`МСФО группы, smart-lab`:`отчётность РСБУ, ГИР БО ФНС`}</span></h2>`+bcIssHtml(j,isin);
    const mb=box.querySelector('#bc-iss-more');if(mb)mb.onclick=()=>issOpen(isin)};
  if(c.market&&c.market.kind==='ofz'){box.innerHTML=`<h2>Финансы эмитента</h2><div class="mu" style="font-size:13px">Государственная облигация: оценка по отчётности не применяется.</div>`;return}
  if(BC.iss[isin]){put(BC.iss[isin]);return}
  api('/api/issuer?isin='+encodeURIComponent(isin)).then(j=>{BC.iss[isin]=j;put(j)}).catch(e=>put({ok:false,errors:['Не удалось загрузить данные: '+(e.message||e)]}));
}
function bcCharts(dr,c){
  const ice=dr.querySelector('#bc-ic');if(ice&&c.issuer_curve)try{bcIssuerCurve(ice,c.issuer_curve)}catch(e){}
  const hs=c.history;if(!hs||!hs.d||hs.d.length<2)return;
  const labels=hs.d.map(ddm),p=document.getElementById('bc-ch-p'),y=document.getElementById('bc-ch-y');
  {
    try{
      if(p)line(p,{h:190,labels,zero:false,fa:v=>bcN(v,1),ft:v=>bcN(v,2)+' %',series:[{n:'Цена',c:'#3987e5',v:hs.p,w:2}]});
      if(y)line(y,{h:190,labels,zero:false,fa:v=>bcN(v,1),ft:v=>bcN(v,2)+' %',series:[{n:'Доходность',c:'#c98500',v:hs.y,w:2}]});
    }catch(e){}
  }
}
