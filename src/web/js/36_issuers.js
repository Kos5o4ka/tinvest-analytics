/* ── Эмитенты: отчётность и скоринг ── */
S.iss={data:null,acc:null,loading:false,prog:null,sel:null,cards:{},cardLoad:{},tab:{},sort:{k:'share',d:-1}};
const ISS_KEY={strong:'Устойчивое',mid:'Среднее',weak:'Слабое',alarm:'Тревожное'};
const ISS_SIG={mkt_higher:['Рынок строже','Рынок оценивает риск выше, чем следует из отчётности'],mkt_lower:['Рынок мягче','Рынок оценивает риск ниже, чем следует из отчётности'],match:['Совпадает','Оценка рынка соответствует отчётности']};
const ISS_HINT={
  cover:'Во сколько раз прибыль до процентов и налогов (EBIT) больше процентов по долгам. Ниже 1,5 — опасно: прибыли хватает впритык; выше 4 — спокойно.',
  lev:'Чистый долг (долг минус деньги и краткосрочные вложения) в годовых EBIT: за сколько лет операционная прибыль «закрыла» бы долг. До 2 — комфортно, больше 4 — тяжело. Для лизинга и финансовых компаний вместо этого берётся долг к капиталу: до 3 — консервативно, больше 8 — рискованно.',
  eq:'Какая часть активов оплачена собственными, а не заёмными деньгами. Выше 30 % — прочная основа, ниже 5 % — запаса прочности почти нет (у финансовых компаний нормой считается от 15 %).',
  liq:'Оборотные активы / краткосрочные обязательства: хватит ли ближайших ресурсов на ближайшие долги. Выше 1,5 — хорошо, ниже 0,8 — риск нехватки денег.',
  margin:'EBIT / выручка: сколько операционной прибыли остаётся с рубля продаж. Зависит от отрасли; от 12 % — хорошо, около 0 — бизнес едва зарабатывает.',
  growth:'Изменение выручки к прошлому году. Рост — хорошо, падение более чем на 15 % — тревожный знак.'};
const ISS_HINT_I={
  cover:'Во сколько раз EBITDA группы больше процентов по долгам. Ниже 2 — опасно; выше 6 — спокойно.',
  lev:'Чистый долг (долг минус деньги) в годовых EBITDA группы. До 1,5 — комфортно, больше 4,5 — тяжело.',
  eq:'Доля собственного капитала в активах группы. Выше 40 % — прочная основа, ниже 10 % — запаса прочности почти нет.',
  margin:'EBITDA / выручка. Зависит от отрасли; от 25 % — хорошо, около 5 % и ниже — бизнес едва зарабатывает.',
  fcf:'Операционный денежный поток минус капитальные затраты. Положительный — группа сама оплачивает инвестиции, отрицательный — растёт за счёт долга.',
  growth:'Изменение выручки к прошлому году (по годовой отчётности). Падение более чем на 15 % — тревожный знак.',
  roe:'Чистая прибыль / капитал банка. От 15 % — хорошо, около 0 — банк не зарабатывает.',
  crisk:'Резервы под кредитные потери в процентах от кредитов за год. До 1 % — спокойно, от 3 % — высокий риск.',
  npl:'Доля неработающих (просроченных) кредитов. До 4 % — норма, от 10 % — тревожно.',
  car:'Общая достаточность капитала по нормативам Банка России. От 14 % — запас есть, ниже 10,5 % — близко к минимуму.'};
const issX=(v,d=1)=>v==null||isNaN(v)?'—':v.toFixed(d).replace('.',',')+'×';
const issP=(v,d=0)=>v==null||isNaN(v)?'—':(v*100).toFixed(d).replace('.',',')+' %';
const issR=v=>v==null?'—':short(v*1e6);
const issNd=y=>y.net_debt!=null&&y.net_debt<=0?'нет чистого долга':y.nd_ebit!=null?issX(y.nd_ebit):(y.net_debt!=null&&y.ebit!=null&&y.ebit<=0?'EBIT ≤ 0':'—');
const issBasis=r=>r.basis==='ifrs'?`<small class="mu" title="${esc(r.ifrs_how||'')}">МСФО группы (${esc(r.ifrs_ticker||'')}) · ${esc(r.period||'')}</small>`:`<small class="mu">РСБУ · за ${r.year} г.</small>`;
const issTag=(key,score,label)=>score==null?'<span class="mu">—</span>':`<span class="iss-sc iss-${esc(key)}"><b>${score}</b> ${esc(label||ISS_KEY[key]||'')}</span>`;
const issSig=m=>{const s=m&&m.key&&ISS_SIG[m.key];return s?`<span class="iss-sg iss-sg-${esc(m.key)}" title="${esc(m.text||s[1])}">${s[0]}</span>`:'<span class="mu">—</span>'};

function loadIss(force){
  if(S.iss.loading)return;S.iss.loading=true;S.iss.prog=null;const acc=S.account;let first=true;
  const tick=async()=>{
    try{
      const p=new URLSearchParams({account:acc});if(force&&first)p.set('force','1');first=false;
      const j=await api('/api/issuers?'+p);
      if(S.account!==acc){S.iss.loading=false;if(S.page==='iss')render();return}
      if(j.pending){S.iss.prog=j;const e=document.getElementById('iss-prog');if(e)e.textContent=j.total?`${j.done} из ${j.total}`:'определяю эмитентов…';setTimeout(tick,2500);return}
      S.iss.data=j.error?{error:j.error}:j;S.iss.acc=acc;S.iss.loading=false;
      if(S.page==='iss')render();
    }catch(e){S.iss.data={error:e.message||String(e)};S.iss.acc=acc;S.iss.loading=false;if(S.page==='iss')render()}
  };
  tick();
}
function loadIssCard(isin,force){
  if(S.iss.cardLoad[isin])return;S.iss.cardLoad[isin]=1;
  api('/api/issuer?isin='+encodeURIComponent(isin)+(force?'&force=1':'')).then(c=>{S.iss.cards[isin]=c}).catch(e=>{S.iss.cards[isin]={ok:false,errors:[e.message||String(e)]}})
   .then(()=>{S.iss.cardLoad[isin]=0;if(S.page==='iss'&&S.iss.sel===isin)render()});
}
/* открыть страницу «Эмитенты» сразу с подробностями по эмитенту этой облигации (вызывается из карточки облигации) */
function issOpen(isin){
  if(typeof closeBond==='function')closeBond();
  S.iss.sel=isin;S.iss.scroll=1;go('iss');
}
function issRows(d){
  const k=S.iss.sort.k,g={name:r=>r.title,share:r=>r.share,rating:r=>r.rating?RSC.indexOf(r.rating):null,score:r=>r.score,nd_ebit:r=>r.nd_ebit,cover:r=>r.cover,eq_ratio:r=>r.eq_ratio,
    signal:r=>r.market&&r.market.key?['mkt_lower','match','mkt_higher'].indexOf(r.market.key):null}[k]||(r=>r.share);
  return d.rows.slice().sort((a,b)=>{const x=g(a),y=g(b);if(typeof x==='string'||typeof y==='string')return S.iss.sort.d*String(x||'').localeCompare(String(y||''));
    if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;return S.iss.sort.d*(x-y)});
}
function pIss(){
  const I=S.iss;
  if(I.data&&I.acc!==S.account)I.data=null;
  const disc=`<p class="note" style="margin-top:12px">Справочная информация на основе открытой бухгалтерской отчётности по РСБУ (ГИР БО ФНС) и данных Мосбиржи. Не является инвестиционной рекомендацией. Если эмитент — листинговая компания или входит в такую группу, скоринг считается по консолидированной отчётности группы (МСФО, данные агрегатора smart-lab — они могут отличаться от официальной отчётности); иначе — по РСБУ отдельной компании, которая может не отражать положение группы. Банки и страховые без МСФО-данных не оцениваются: их РСБУ в ГИР БО нет.</p>`;
  if(!I.data){loadIss();return`<div class="card">${waitBox('Собираю отчётность эмитентов портфеля (первый раз может занять около минуты)… <span id="iss-prog">'+(I.prog&&I.prog.total?`${I.prog.done} из ${I.prog.total}`:'')+'</span>')}</div>`}
  const d=I.data;
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="iss-retry">Повторить</button></div>`;
  let h='';
  if(!d.rows.length)h+=`<div class="card empty">В портфеле нет облигаций корпоративных эмитентов</div>`;
  else{
    const sc=d.avg_score,k=sc==null?null:sc>=70?'strong':sc>=50?'mid':sc>=30?'weak':'alarm';
    h+=`<div class="g g4">${kpi('Эмитентов в портфеле',String(d.n),`отчётность найдена у ${d.n_scored}`+(d.gov_n?` · ещё ${d.gov_n} гос. выпусков не оцениваются`:''),null,S1)}
      ${kpi('Средневзвешенный скоринг',sc==null?'—':Math.round(sc)+' из 100',sc==null?'нет данных':ISS_KEY[k]+' · взвешено по долям в облигациях',k==='weak'||k==='alarm'?'neg':k==='strong'?'pos':'',S3)}
      ${kpi('Слабые и тревожные',pctp(d.share_bad,1),'доля облигаций портфеля у эмитентов со скорингом ниже 50',d.share_bad>=20?'neg':'',S8)}
      ${kpi('Покрыто отчётностью',pctp(d.share_scored,0),'доля облигаций портфеля, по которым скоринг посчитан',null,S4)}</div>`;
    const ds=d.dist||{};
    h+=`<div class="card"><h2>Эмитенты портфеля<span class="sp">нажмите на строку — подробности по отчётности, скоринг и кредитная история</span></h2>
      <div class="iss-dist">${['strong','mid','weak','alarm'].map(x=>`<span class="iss-sc iss-${x}"><b>${ds[x]||0}</b> ${ISS_KEY[x].toLowerCase()}</span>`).join('')}<span class="mu" style="font-size:12px">скоринг от 0 до 100: ≥ 70 устойчивое · 50–69 среднее · 30–49 слабое · &lt; 30 тревожное</span></div>`;
    const cols=[['name','Эмитент','l'],['share','Доля в облигациях'],['rating','Рейтинг','l'],['score','Скоринг','l'],['nd_ebit','Чистый долг / EBIT(DA)'],['cover','Покрытие процентов'],['eq_ratio','Капитал / активы'],['signal','Рынок и отчётность','l']];
    const th=cols.map(([k,t,c])=>`<th class="s ${c||''}" data-s="${k}">${t} <span>${I.sort.k===k?(I.sort.d>0?'↑':'↓'):''}</span></th>`).join('');
    const body=issRows(d).map(r=>{
      const has=r.score!=null,stale=has&&r.year<new Date().getFullYear()-2;
      const lv=has?(r.basis==='ifrs'?(r.bank?'<span class="mu">—</span>':(r.net_debt!=null&&r.net_debt<=0?'<span class="pos">нет чист. долга</span>':issX(r.nd_ebit))):r.fin_mode?`<span class="mu" title="Для лизинга и финансовых компаний долг — основа бизнеса, оценивается долг к капиталу">долг/кап. ${issX(r.debt_eq)}</span>`:(r.net_debt!=null&&r.net_debt<=0?'<span class="pos">нет чист. долга</span>':issX(r.nd_ebit))):'<span class="mu">—</span>';
      return`<tr class="iss-r${I.sel===r.isin?' on':''}" data-iss="${esc(r.isin)}"><td class="l"><div class="tk">${logo({name:r.title,ticker:'',logo:r.logo,color:r.color})}<div><b title="${esc(r.full||r.title)}">${esc(r.title)}</b><small>${r.inn?'ИНН '+esc(r.inn):'ИНН неизвестен'} · выпусков: ${r.n_bonds}</small></div></div></td>
        <td class="num">${pctp(r.share,1)}</td><td class="l">${r.rating?`<span class="tag rt rt-${esc(rBucket(r.rating).split(' ')[0])}">${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td>
        <td class="l">${has?issTag(r.key,r.score,r.label)+`<br>${issBasis(r)}<small class="mu">${stale?' · <span class="neg">устарела</span>':''}${r.holding?' · холдинг (РСБУ отражает группу плохо)':''}</small>`:`<span class="mu" title="${esc(r.note||'')}">нет данных${r.ifrs_ticker?'':' по РСБУ'}</span>`}</td>
        <td class="num">${lv}</td><td class="num">${has?issX(r.cover):'—'}</td><td class="num">${has?issP(r.eq_ratio):'—'}</td><td class="l">${has?issSig(r.market):'<span class="mu">—</span>'}</td></tr>`}).join('');
    h+=`<div class="tbl iss-tbl"><table id="iss-tab"><thead><tr>${th}</tr></thead><tbody>${body}</tbody></table></div>
      <p class="note" style="margin-top:10px">Обновлено ${esc(d.updated||'')}. В колонке «Скоринг» указана основа расчёта: МСФО группы (тикер) или РСБУ компании. Эмитенты без отчётности: страховые и банки без МСФО, компании, не раскрывающие отчётность, новые компании. «Рынок строже» — спред облигаций к кривой доходности ОФЗ и рейтинг указывают на больший риск, чем видно из отчётности; «рынок мягче» — наоборот. <button class="btn ghost" id="iss-ref" style="padding:3px 10px;font-size:12px;margin-left:6px">Пересчитать</button></p></div>`;
  }
  if(I.sel)h+=issDetail(I.sel);
  return h+disc;
}
function issPartsHtml(s,hints){
  hints=hints||ISS_HINT;
  if(!s||!s.ok)return`<div class="mu" style="font-size:13px">${esc((s&&s.reason)||'Скоринг не рассчитан.')}</div>`;
  const rows=s.parts.map(p=>`<tr><td class="l"><b>${esc(p.name)}</b><br><small class="mu">${esc(p.text)}</small></td>
    <td><div class="iss-bar"><i class="g-${p.grade}" style="width:${Math.round(p.pts/p.max*100)}%"></i></div></td><td class="num">${p.pts.toFixed(1).replace('.',',')} из ${p.max}</td>
    <td class="l iss-hint">${esc(hints[p.id]||'')}</td></tr>`).join('');
  const pen=(s.penalties||[]).map(p=>`<tr><td class="l neg">${esc(p.name)}</td><td></td><td class="num neg">${p.pts}</td><td class="l iss-hint">Штраф: вычитается из итогового результата.</td></tr>`).join('');
  return`<div class="tbl"><table><thead><tr><th class="l">Показатель</th><th></th><th>Баллы</th><th class="l">Что значит и какой уровень нормальный</th></tr></thead><tbody>${rows}${pen}</tbody></table></div>
    <p class="note" style="margin-top:8px">Баллы по доступным показателям пересчитываются на 100 (${s.base!=null?'до штрафов — '+Math.round(s.base):''}), затем применяются штрафы. ${s.holding?'':esc(s.note||'')}</p>`;
}
function issChart(el,fin,ifrs){
  const ys=fin.years;
  if(ifrs){const bk=fin.bank;return bars(el,{h:260,labels:ys.map(y=>String(y.y)),series:bk?[{n:'Чистые операц. доходы',c:S1,v:ys.map(y=>(y.rev||0)*1e6)},{n:'Чистая прибыль',c:S3,v:ys.map(y=>(y.net||0)*1e6)}]
    :[{n:'Выручка',c:S1,v:ys.map(y=>(y.rev||0)*1e6)},{n:'EBITDA',c:S3,v:ys.map(y=>(y.ebitda||0)*1e6)},{n:'Чистый долг',c:S8,v:ys.map(y=>(y.net_debt||0)*1e6)}],fa:short,ft:v=>short(v)+' ₽',empty:'Нет данных'})}bars(el,{h:260,labels:ys.map(y=>String(y.y)),series:[{n:'Выручка',c:S1,v:ys.map(y=>(y.rev||0)*1e6)},{n:'EBIT',c:S3,v:ys.map(y=>(y.ebit||0)*1e6)},
    {n:'Чистый долг',c:S8,v:ys.map(y=>(y.net_debt||0)*1e6)}],fa:short,ft:v=>short(v)+' ₽',empty:'Нет данных'});
}
function issFinTable(fin){
  const ys=fin.years,th=ys.map(y=>`<th>${y.y}</th>`).join('');
  const row=(n,f,hint)=>`<tr><td class="l">${n}</td>${ys.map(y=>`<td class="num">${f(y)}</td>`).join('')}<td class="l iss-hint">${hint||''}</td></tr>`;
  const a=[['Выручка',y=>issR(y.rev)],['EBIT (прибыль до налогов и процентов)',y=>issR(y.ebit),'Прибыль до налога плюс проценты к уплате: сколько бизнес зарабатывает до обслуживания долга.'],
    ['Проценты к уплате',y=>issR(y.interest)],['Чистая прибыль',y=>issR(y.net)],['Долг (кредиты и займы)',y=>issR(y.debt)],['Деньги и краткосрочные вложения',y=>issR(y.cash)],
    ['Чистый долг',y=>issR(y.net_debt),'Долг минус деньги. Отрицательный — денег больше, чем долга.'],['Капитал',y=>issR(y.equity)],['Активы',y=>issR(y.assets)]];
  const b=[['Чистый долг / EBIT',y=>`<b>${issNd(y)}</b>`,ISS_HINT.lev],['Покрытие процентов',y=>`<b>${issX(y.cover)}</b>`,ISS_HINT.cover],['Текущая ликвидность',y=>`<b>${issX(y.cur_liq,2)}</b>`,ISS_HINT.liq],
    ['Доля капитала в активах',y=>`<b>${issP(y.eq_ratio)}</b>`,ISS_HINT.eq],['Рентабельность по EBIT',y=>`<b>${issP(y.margin,1)}</b>`,ISS_HINT.margin],['Рост выручки',y=>`<b class="${y.growth<0?'neg':y.growth>0?'pos':''}">${y.growth==null?'—':(y.growth>0?'+':'')+issP(y.growth)}</b>`,ISS_HINT.growth]];
  return`<div class="tbl"><table><thead><tr><th class="l">Абсолютные показатели, ₽</th>${th}<th class="l">Пояснение</th></tr></thead><tbody>${a.map(x=>row(x[0],x[1],x[2])).join('')}</tbody></table></div>
    <div class="tbl" style="margin-top:14px"><table><thead><tr><th class="l">Коэффициенты</th>${th}<th class="l">Что значит и какой уровень нормальный</th></tr></thead><tbody>${b.map(x=>row(x[0],x[1],x[2])).join('')}</tbody></table></div>`;
}
function issIfrsTable(fin){
  const ys=fin.years.concat(fin.ltm?[fin.ltm]:[]),th=ys.map(y=>`<th>${y.y==='LTM'?'LTM':y.y}</th>`).join('');
  const row=(n,f,hint)=>`<tr><td class="l">${n}</td>${ys.map(y=>`<td class="num">${f(y)}</td>`).join('')}<td class="l iss-hint">${hint||''}</td></tr>`;
  const nd=y=>y.net_debt!=null&&y.net_debt<=0?'нет чистого долга':y.nd_ebitda!=null?issX(y.nd_ebitda):(y.net_debt!=null&&y.ebitda!=null&&y.ebitda<=0?'EBITDA ≤ 0':'—');
  const g=y=>y.growth==null?'—':`<span class="${y.growth<0?'neg':'pos'}">${(y.growth>0?'+':'')+issP(y.growth)}</span>`;
  const a=fin.bank?[['Чистые операционные доходы',y=>issR(y.rev)],['Чистая прибыль',y=>issR(y.net)],['Капитал',y=>issR(y.equity)],['Активы',y=>issR(y.assets)]]
    :[['Выручка',y=>issR(y.rev)],['EBITDA',y=>issR(y.ebitda),'Прибыль до процентов, налогов и амортизации.'],['Чистая прибыль',y=>issR(y.net)],['Проценты к уплате',y=>issR(y.interest)],
      ['Чистый долг',y=>issR(y.net_debt),'Долг минус деньги. Отрицательный — денег больше, чем долга.'],['Операционный денежный поток',y=>issR(y.ocf)],['Капитальные затраты',y=>issR(y.capex)],
      ['Свободный денежный поток',y=>issR(y.fcf),'Операционный поток минус капзатраты.'],['Капитал',y=>issR(y.equity)],['Активы',y=>issR(y.assets)]];
  const b=fin.bank?[['ROE',y=>`<b>${issP(y.roe,1)}</b>`,ISS_HINT_I.roe],['Капитал / активы',y=>`<b>${issP(y.eq_ratio,1)}</b>`,ISS_HINT_I.eq],['Стоимость риска',y=>`<b>${issP(y.cost_risk,1)}</b>`,ISS_HINT_I.crisk],
      ['Неработающие кредиты',y=>`<b>${issP(y.npl,1)}</b>`,ISS_HINT_I.npl],['Достаточность капитала',y=>`<b>${issP(y.car,1)}</b>`,ISS_HINT_I.car],['Рост доходов',y=>`<b>${g(y)}</b>`,ISS_HINT_I.growth]]
    :[['Чистый долг / EBITDA',y=>`<b>${nd(y)}</b>`,ISS_HINT_I.lev],['Покрытие процентов (EBITDA)',y=>`<b>${issX(y.cover)}</b>`,ISS_HINT_I.cover],['Доля капитала в активах',y=>`<b>${issP(y.eq_ratio)}</b>`,ISS_HINT_I.eq],
      ['Рентабельность по EBITDA',y=>`<b>${issP(y.margin_ebitda,1)}</b>`,ISS_HINT_I.margin],['Рост выручки',y=>`<b>${g(y)}</b>`,ISS_HINT_I.growth]];
  return`<div class="tbl"><table><thead><tr><th class="l">Абсолютные показатели, ₽</th>${th}<th class="l">Пояснение</th></tr></thead><tbody>${a.map(x=>row(x[0],x[1],x[2])).join('')}</tbody></table></div>
    <div class="tbl" style="margin-top:14px"><table><thead><tr><th class="l">Коэффициенты</th>${th}<th class="l">Что значит и какой уровень нормальный</th></tr></thead><tbody>${b.map(x=>row(x[0],x[1],x[2])).join('')}</tbody></table></div>`;
}
function issIfrsBlock(ib){
  const s=ib.score,f=ib.fin;let h='';
  if(s.ok){
    h+=`<div class="iss-top"><div class="iss-big iss-${esc(s.key)}"><b>${s.score}</b><span>из 100</span></div><div><div style="font-size:16px;font-weight:650">Финансовое состояние группы: ${esc(s.label)}</div>
      <div class="mu" style="font-size:13px;margin-top:3px">По консолидированной отчётности МСФО (${esc(ib.group||ib.ticker)}, ${esc(ib.ticker)}), ${esc(s.period)}. Лет в таблице: ${s.n_years}. Шкала: ≥ 70 устойчивое · 50–69 среднее · 30–49 слабое · &lt; 30 тревожное.</div>
      <div class="mu" style="font-size:13px;margin-top:3px">${esc(ib.how)}.</div></div></div>`;
    if(s.year<new Date().getFullYear()-2)h+=`<div class="bc-warn">Последний годовой отчёт — за ${s.year} г.: оценка устарела.</div>`;
    h+=`<h3 class="iss-h">За что баллы</h3>${issPartsHtml(s,ISS_HINT_I)}`;
  }else h+=`<div class="msg" style="margin:6px 0 12px">${esc(s.reason||f.note||'Нет данных МСФО.')}</div>`;
  if(f.years&&f.years.length)h+=`<h3 class="iss-h">Динамика по годам</h3><div id="iss-ch" class="bc-ch"></div>${issIfrsTable(f)}
    <p class="note" style="margin-top:8px">Суммы в миллионах рублей, показаны в сокращённом виде. LTM — последние 12 месяцев по квартальной отчётности (если новее годовой). Рост выручки считается по годовым данным. <a href="${esc(ib.url)}" target="_blank" rel="noopener">Источник: smart-lab ↗</a> — данные агрегатора, могут отличаться от официальной отчётности.</p>`;
  return h;
}
function issDetail(isin){
  const I=S.iss,c=I.cards[isin];
  const bar=`<div class="row" style="justify-content:flex-end"><button class="btn ghost" id="iss-close" style="padding:4px 12px;font-size:12px">Свернуть ✕</button></div>`;
  if(!c){loadIssCard(isin);return`<div class="card" id="iss-det">${bar}${waitBox('Загружаю отчётность эмитента (ФНС, Мосбиржа)…')}</div>`}
  if(!c.ok)return`<div class="card" id="iss-det">${bar}<div class="msg err">${(c.errors||['Не удалось загрузить эмитента']).map(esc).join('<br>')}</div></div>`;
  const is=c.issuer||{},f=c.fin||{years:[]},s=c.score||{},m=c.market||{},hs=c.history;
  let h=`<div class="card" id="iss-det">${bar}<h2 style="margin-top:-6px">${esc(is.short||is.title||isin)}<span class="sp">${is.inn?'ИНН '+esc(is.inn)+' · ':''}${esc(is.title||'')}</span></h2>`;
  if(c.errors&&c.errors.length)h+=`<div class="bc-warn">${c.errors.map(esc).join('<br>')}</div>`;
  const ib=c.ifrs,hasI=!!(ib&&ib.fin&&ib.fin.status==='ok'&&ib.fin.years&&ib.fin.years.length),tab=hasI?(I.tab[isin]||c.basis):'rsbu',useI=hasI&&tab==='ifrs';
  if(ib&&!hasI)h+=`<div class="mu" style="font-size:12px;margin-bottom:8px">Для группы ${esc(ib.group||'')} (${esc(ib.ticker)}) данных МСФО на smart-lab нет: ${esc((ib.fin&&ib.fin.note)||'')}</div>`;
  if(hasI)h+=`<div class="seg" id="iss-tabs" style="margin:2px 0 12px;display:inline-flex"><button data-tab="ifrs" class="${tab==='ifrs'?'on':''}">МСФО группы (${esc(ib.ticker)})${c.basis==='ifrs'?' · основа скоринга':''}</button>
    <button data-tab="rsbu" class="${tab==='rsbu'?'on':''}">РСБУ компании${c.basis==='rsbu'?' · основа скоринга':''}</button></div>`;
  if(useI)h+=issIfrsBlock(ib);
  else{
  if(f.org_id)h+=`<div class="mu" style="font-size:12px;margin-bottom:8px"><a href="https://bo.nalog.gov.ru/organizations-card/${esc(String(f.org_id))}" target="_blank" rel="noopener">Отчётность на сайте ФНС ↗</a></div>`;
  if(s.ok){
    h+=`<div class="iss-top"><div class="iss-big iss-${esc(s.key)}"><b>${s.score}</b><span>из 100</span></div><div><div style="font-size:16px;font-weight:650">Финансовое состояние: ${esc(s.label)}</div>
      <div class="mu" style="font-size:13px;margin-top:3px">По отчётности РСБУ за ${s.year} г. (доступно лет: ${s.n_years}). Шкала: ≥ 70 устойчивое · 50–69 среднее · 30–49 слабое · &lt; 30 тревожное.</div>
      ${s.holding?`<div class="bc-warn">${esc(s.note)}</div>`:''}</div></div>`;
    if(s.year<new Date().getFullYear()-2)h+=`<div class="bc-warn">Последняя доступная отчётность — за ${s.year} г.: эмитент мог перестать раскрывать данные. Оценка устарела.</div>`;
    h+=`<h3 class="iss-h">За что баллы</h3>${issPartsHtml(s)}`;
  }else h+=`<div class="msg" style="margin:6px 0 12px">${esc(s.reason||f.note||'Нет данных по РСБУ.')}</div>`;
  if(f.years&&f.years.length){
    h+=`<h3 class="iss-h">Динамика по годам</h3><div id="iss-ch" class="bc-ch"></div>${issFinTable(f)}
      <p class="note" style="margin-top:8px">Суммы в миллионах рублей, показаны в сокращённом виде. EBIT здесь — прибыль до налогообложения плюс проценты к уплате (если строки нет — прибыль от продаж). Источник: бухгалтерская отчётность по РСБУ, ГИР БО ФНС (отчётность отдельной компании, не группы).</p>`;
  }
  }
  h+=`<h3 class="iss-h">Рынок и отчётность</h3><div class="bc-rel">`;
  if(m.key)h+=`<b class="${m.key==='mkt_higher'?'neg':m.key==='mkt_lower'?'':'pos'}">${esc(m.text)}</b><br>`;else h+=esc(m.text||'');
  const ms=c.basis==='ifrs'?ib.score:s;
  h+=`<span class="mu">Скоринг по отчётности (${c.basis==='ifrs'?'МСФО':'РСБУ'}): ${ms.ok?ms.score:'—'} · по спреду к КБД: ${m.market_score==null?'—':m.market_score}${m.spread==null?'':' (спред '+bcN(m.spread,1)+' п.п.)'} · по рейтингу: ${m.rating_score==null?'—':m.rating_score}${m.rating?' ('+esc(m.rating)+')':''}. Оценки рынка и рейтинга переведены в ту же шкалу 0–100: чем выше спред и ниже рейтинг, тем меньше баллов.</span></div>`;
  if(c.bonds&&c.bonds.length){
    h+=`<div class="tbl" style="margin-top:10px;max-height:300px"><table><thead><tr><th class="l">Выпуск</th><th>Рейтинг</th><th>Дюрация, г.</th><th>Доходность</th><th>Спред к КБД</th></tr></thead><tbody>`
      +c.bonds.map(b=>`<tr data-isin="${esc(b.isin)}" title="Открыть карточку выпуска"><td class="l">${esc(b.name)}${b.me?' <span class="tag">этот выпуск</span>':''}</td><td>${b.rating?`<span class="tag rt rt-${esc(rBucket(b.rating).split(' ')[0])}">${esc(b.rating)}</span>`:'<span class="mu">—</span>'}</td>
        <td class="num">${bcN(b.dur,2)}</td><td class="num">${b.yield==null?'—':bcN(b.yield,2)+' %'}</td><td class="num">${b.spread==null?'—':(b.spread>0?'+':'')+bcN(b.spread,2)+' п.п.'}</td></tr>`).join('')+`</tbody></table></div>`;
  }
  if(hs){
    const bad_=hs.items.filter(x=>x.default||x.tech);
    h+=`<h3 class="iss-h">Кредитная история</h3><div class="bc-rel"><b class="${hs.defaults?'neg':hs.tech?'':'pos'}">${esc(hs.verdict)}</b><br><span class="mu">Выпусков эмитента на Мосбирже: ${hs.total} (торгуется сейчас: ${hs.traded}). Проверено на дефолт: ${hs.checked}${hs.total>hs.checked?' (сначала торгуемые)':''}. Флаги берутся из описания выпуска на Мосбирже.</span></div>`;
    if(bad_.length)h+=`<div class="tbl" style="margin-top:8px;max-height:260px"><table><thead><tr><th class="l">Выпуск</th><th class="l">Статус</th></tr></thead><tbody>`+bad_.map(x=>`<tr data-isin="${esc(x.isin)}"><td class="l">${esc(x.name)} <small class="mu">${esc(x.isin)}</small></td><td class="l neg">${x.default?'дефолт':'технический дефолт'}${x.traded?'':' · не торгуется'}</td></tr>`).join('')+`</tbody></table></div>`;
  }
  return h+`<p class="note" style="margin-top:12px">Не является инвестиционной рекомендацией. Скоринг — упрощённая модель по открытой отчётности (МСФО группы по данным smart-lab, если эмитент входит в листинговую группу; иначе РСБУ отдельной компании); она может не отражать поддержку владельца и события после отчётной даты.</p></div>`;
}
function bindIss(){
  const I=S.iss;
  const t=$('#iss-tab');
  if(t){
    t.querySelector('thead').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;I.sort={k,d:I.sort.k===k?-I.sort.d:(k==='name'?1:-1)};render()};
    t.querySelector('tbody').onclick=e=>{const r=e.target.closest('[data-iss]');if(!r)return;I.sel=I.sel===r.dataset.iss?null:r.dataset.iss;I.scroll=I.sel?1:0;render()};
  }
  const rt=$('#iss-retry');if(rt)rt.onclick=()=>{I.data=null;render()};
  const rf=$('#iss-ref');if(rf)rf.onclick=()=>{I.data=null;I.cards={};loadIss(true);render()};
  const cl=$('#iss-close');if(cl)cl.onclick=()=>{I.sel=null;render()};
  const det=document.getElementById('iss-det');
  if(det&&I.sel){
    const c=I.cards[I.sel],ch=document.getElementById('iss-ch');
    const useI=c&&c.ifrs&&c.ifrs.fin&&c.ifrs.fin.years&&c.ifrs.fin.years.length&&(I.tab[I.sel]||c.basis)==='ifrs';
    const fin=useI?c.ifrs.fin:c&&c.fin;
    if(fin&&fin.years&&fin.years.length&&ch)try{issChart(ch,fin,useI)}catch(e){ch.innerHTML='<div class="empty">Не удалось построить график</div>'}
    const tb=document.getElementById('iss-tabs');if(tb)tb.onclick=e=>{const b=e.target.closest('[data-tab]');if(!b)return;I.tab[I.sel]=b.dataset.tab;render()};
    if(I.scroll&&c){I.scroll=0;det.scrollIntoView({behavior:'smooth',block:'start'})}
  }
}
