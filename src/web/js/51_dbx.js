/* ── Линкеры, оферты, валютные и замещающие облигации ── */
S.dbx={tab:'lnk',lnk:null,lnkLoad:false,off:null,offLoad:false,offGrade:'',offTimer:0,fxb:null,fxbLoad:false,fxRes:null,fxLoad:false,fxErr:null,
  f:{cur:'USD',nominal:'1000',price:'100',coupon:'5',freq:'2',mat:'',buy_fx:'',qty:'10',nkd:'0',other:'0',scenarios:'-20, -10, 0, 10, 20, 40'}};
const DBX_GR={high:['pos','покрытие высокое'],mid:['','покрытие среднее'],low:['neg','покрытие низкое'],nodata:['mu','нет данных'],na:['mu','показатель неприменим'],loading:['mu','считаю…']};
const dbxN=(v,d=2)=>bad(v)?'—':v.toFixed(d).replace('.',',');
const dbxM=v=>bad(v)?'—':short(v);
const dbxMl=v=>bad(v)?'—':Math.round(v).toLocaleString('ru-RU');
function dbxLoadJ(key,flag,url){
  const D=S.dbx;if(D[flag])return;D[flag]=true;
  api(url).then(j=>{D[key]=j}).catch(e=>{D[key]={error:e.message||String(e),rows:[]}}).then(()=>{D[flag]=false;if(S.page==='dbx'){renderSoon();dbxPoll()}});
}
function dbxLinkers(){
  const D=S.dbx;
  if(!D.lnk){dbxLoadJ('lnk','lnkLoad','/api/dbx/linkers');return waitBox('Загружаю ОФЗ-ИН с Мосбиржи…')}
  const d=D.lnk;if(d.error)return`<div class="msg err">${esc(d.error)}</div>`;
  const fc=d.forecast||{},fy=(fc.yearly||[]).map(y=>`${y.year}: ${dbxN(y.mid,1)} %`).join(' · ');
  let h=`<div class="card"><h2>Линкеры (ОФЗ-ИН): какую инфляцию закладывает рынок<span class="sp">модельный расчёт по данным Мосбиржи и КБД</span></h2>`;
  if(!d.rows.length)return h+`<div class="empty">Выпуски ОФЗ-ИН на Мосбирже не найдены.</div></div>`;
  h+=`<div class="tbl-w"><table class="tbl"><thead><tr><th class="l">Выпуск</th><th>Погашение</th><th>Дюрация, лет</th><th>Реальная доходность</th><th>Номинальная (КБД) на той же дюрации</th><th>Разница</th><th>Безубыточная инфляция (Фишер)</th><th>Прогноз инфляции</th><th>Безубыточная − прогноз</th></tr></thead><tbody>`;
  h+=d.rows.map(r=>`<tr><td class="l"><b>${esc(r.name)}</b> <small class="mu">${esc(r.id)}</small></td><td>${esc(dlabel(r.mat))}</td><td class="num">${dbxN(r.dur)}</td><td class="num">${pctp(r.real,2)}</td><td class="num">${pctp(r.nominal,2)}</td><td class="num">${dbxN(r.diff)} п.п.</td><td class="num"><b>${pctp(r.be,2)}</b></td><td class="num" title="${r.fc_src==='cbr'?'среднее по прогнозу Банка России на горизонте дюрации':'допущение 4 % — прогноз недоступен'}">${pctp(r.fc,2)}${r.fc_src==='cbr'?'':' *'}</td><td class="num ${r.gap>0.3?'pos':r.gap<-0.3?'neg':''}">${r.gap>0?'+':''}${dbxN(r.gap)} п.п.</td></tr>`).join('')+`</tbody></table></div>`;
  h+=`<p class="note" style="margin-top:12px">Как читать. Безубыточная инфляция по Фишеру: (1 + номинальная) / (1 + реальная) − 1; простая разница — номинальная минус реальная. Если инфляция в среднем окажется выше этого уровня, линкер при прочих равных даст больше обычной ОФЗ с той же дюрацией, ниже — меньше. «Безубыточная − прогноз» больше нуля означает, что рынок закладывает инфляцию выше прогноза.</p>
    <p class="note">Ограничения: индексация номинала идёт с лагом около трёх месяцев к ИПЦ, поэтому на коротких выпусках результат чувствителен к недавней инфляции. Реальная доходность линкера и КБД рассчитываются по-разному, в безубыточной инфляции есть премия за ликвидность и за риск инфляции; ликвидность ОФЗ-ИН ниже, чем у обычных ОФЗ. Прогноз — Банка России${fc.as_of?' от '+esc(dlabel(fc.as_of)):''}${fy?` (середина диапазона, декабрь к декабрю: ${esc(fy)})`:' (недоступен, использовано допущение 4 %, отмечено звёздочкой)'}; за пределами горизонта прогноза берётся последнее значение.</p></div>`;
  return h;
}
function dbxOffers(){
  const D=S.dbx;
  if(!D.off){dbxLoadJ('off','offLoad','/api/dbx/offers');return waitBox('Ищу облигации с офертой в ближайшие 12 месяцев…')}
  const d=D.off;if(d.error&&!(d.rows||[]).length)return`<div class="msg err">${esc(d.error)}</div>`;
  const rows=(d.rows||[]).filter(r=>!D.offGrade||r.grade===D.offGrade);
  let h=`<div class="card"><h2>Радар оферт: хватит ли денег у эмитента<span class="sp">корпоративные рублёвые выпуски с put-офертой в ближайшие 12 месяцев</span></h2>`;
  if(d.pending)h+=`<div class="msg" style="margin-bottom:12px">Загружаю отчётность эмитентов: ${d.total?`${d.done} из ${d.total}`:'определяю эмитентов…'}. Страница обновится сама.</div>`;
  if(d.capped)h+=`<div class="msg" style="margin-bottom:12px">За один запуск запрашивается отчётность не более 60 эмитентов; ещё ${d.capped} остались без данных.</div>`;
  h+=`<div class="flt"><label class="field"><span>Оценка покрытия</span><select class="in" id="dbx-gr"><option value="">все</option>${['low','mid','high','nodata','na'].map(k=>`<option value="${k}" ${D.offGrade===k?'selected':''}>${DBX_GR[k][1]}</option>`).join('')}</select></label>
    <button class="btn ghost" id="dbx-off-re">Обновить</button></div>`;
  if(!rows.length)return h+`<div class="empty">Подходящих выпусков нет.</div></div>`;
  h+=`<div class="tbl-w"><table class="tbl"><thead><tr><th class="l">Выпуск / эмитент</th><th>Дата оферты</th><th>Доходность</th><th>Объём выпуска, млн ₽</th><th>Деньги и вложения, млн ₽</th><th>Покрытие выпуска</th><th>Покрытие по эмитенту</th><th class="l">Оценка</th></tr></thead><tbody>`;
  h+=rows.map(r=>{const g=DBX_GR[r.grade]||DBX_GR.nodata;
    return`<tr><td class="l"><b>${esc(r.name)}</b><br><small class="mu">${esc(r.issuer||'')}</small></td><td>${esc(dlabel(r.offer))}</td><td class="num">${pctp(r.yield,2)}</td>
    <td class="num" title="${esc(r.vol_how||'')}">${r.volume?dbxMl(r.volume/1e6):'—'}</td><td class="num">${r.is_fin?'—':dbxMl(r.cash)}${r.fin_year?` <small class="mu">${r.fin_year}</small>`:''}</td>
    <td class="num">${r.is_fin||bad(r.cover)?'—':dbxN(r.cover)+'×'}</td><td class="num" title="${r.issuer_total?'суммарный объём оферт эмитента: '+dbxMl(r.issuer_total/1e6)+' млн ₽':''}">${r.is_fin||bad(r.cover_all)?'—':dbxN(r.cover_all)+'×'}</td>
    <td class="l"><span class="tag ${g[0]}" ${r.fin_note?`title="${esc(r.fin_note)}"`:''}>${g[1]}</span></td></tr>`}).join('')+`</tbody></table></div>`;
  h+=`<p class="note" style="margin-top:12px">Покрытие = (денежные средства 1250 + краткосрочные финансовые вложения 1240 по балансу РСБУ за последний год) / объём выпуска в обращении; оценка берётся по эмитенту целиком: деньги одни на все его оферты в горизонте. Градация: от 1× — высокое, от 0,4× — среднее, ниже — низкое. Это модельная оценка, а не прогноз события.</p>
    <p class="note">Ограничения. РСБУ — отчётность отдельной компании, не группы, и может быть старше года; на дату оферты денег может быть больше или меньше. Данных о денежных потоках от операционной деятельности в используемом источнике нет, поэтому они не показаны. Держатели не обязаны предъявлять облигации к оферте, фактический выкуп обычно меньше объёма выпуска. Для банков, лизинга, МФО и прочих финансовых компаний показатель неприменим: деньги и долг — часть их бизнеса.</p></div>`;
  return h;
}
function dbxPoll(){
  const D=S.dbx;
  if(D.offTimer||!D.off||!D.off.pending||S.page!=='dbx'||D.tab!=='off')return;
  D.offTimer=setTimeout(()=>{D.offTimer=0;if(S.page!=='dbx')return;
    api('/api/dbx/offers').then(j=>{D.off=j}).catch(()=>{}).then(()=>{if(S.page==='dbx'){renderSoon();dbxPoll()}})},3000);
}
function dbxFx(){
  const D=S.dbx,f=D.f;
  if(!D.fxb)dbxLoadJ('fxb','fxbLoad','/api/dbx/fxbonds');
  const bs=D.fxb&&D.fxb.rows||[];
  const fld=(id,t,v,ph)=>`<label class="field"><span>${t}</span><input class="in num" id="dbx-${id}" value="${esc(v)}" ${ph?`placeholder="${esc(ph)}"`:''} inputmode="decimal"></label>`;
  let h=`<div class="card"><h2>Валютные и замещающие облигации: доходность после налога<span class="sp">налог считается в рублях по курсам ЦБ на даты операций (ст. 214.1, 212 НК РФ)</span></h2>
   <div class="flt"><label class="field"><span>Выпуск (подставит данные)</span><select class="in" id="dbx-bond"><option value="">— вручную —</option>${bs.map(b=>`<option value="${esc(b.id)}">${esc(b.name)} · ${esc(b.cur)} · до ${esc(b.mat)}</option>`).join('')}</select></label>
   <label class="field"><span>Валюта</span><select class="in" id="dbx-cur">${['USD','EUR','CNY','AED','HKD','KZT'].map(c=>`<option ${f.cur===c?'selected':''}>${c}</option>`).join('')}</select></label>
   ${fld('nominal','Номинал, в валюте',f.nominal)}${fld('price','Цена, % номинала',f.price)}${fld('nkd','НКД при покупке, в валюте',f.nkd)}</div>
   <div class="flt">${fld('coupon','Купон, % годовых',f.coupon)}${fld('freq','Купонов в год',f.freq)}${fld('mat','Погашение (ГГГГ-ММ-ДД)',f.mat,'2028-06-15')}${fld('buy_fx','Курс ЦБ на покупку, ₽',f.buy_fx,'по умолчанию — текущий')}${fld('qty','Количество бумаг',f.qty)}</div>
   <div class="flt">${fld('other','Прочий налоговый доход года, ₽',f.other)}<label class="field" style="flex:2;min-width:240px"><span>Изменение курса к погашению, % (через запятую)</span><input class="in num" id="dbx-scenarios" value="${esc(f.scenarios)}"></label>
   <button class="btn" id="dbx-run">${D.fxLoad?'Считаю…':'Рассчитать'}</button></div>`;
  if(D.fxErr)h+=`<div class="msg err" style="margin-top:12px">${esc(D.fxErr)}</div>`;
  const r=D.fxRes;
  if(r){
    h+=`<p class="note" style="margin:12px 0 6px">Вложения: ${dbxN(r.cost_cur)} ${esc(r.cur)} = ${dbxM(r.cost_rub)} ₽ по курсу ${dbxN(r.buy_fx,4)}; купонов до погашения: ${r.n_coupons}, по ${dbxN(r.coupon_cur)} ${esc(r.cur)}. Налоговый год погашения: ${r.year}.</p>
    <div class="tbl-w"><table class="tbl"><thead><tr><th>Курс к погашению</th><th>Курс, ₽</th><th>Доход в валюте</th><th>До налога, ${esc(r.cur)}</th><th>После налога, ${esc(r.cur)}</th><th>До налога, ₽</th><th>После налога, ₽</th><th>Налоговая база, ₽</th><th>Налог, ₽</th></tr></thead><tbody>`;
    h+=r.scenarios.map(s=>`<tr class="${s.trap?'dbx-trap':''}"><td class="num">${s.scenario>0?'+':''}${dbxN(s.scenario,0)} %</td><td class="num">${dbxN(s.fx_mat)}</td><td class="num">${dbxN(s.profit_cur)} ${esc(r.cur)}</td>
      <td class="num">${pctp(s.pre_cur,2)}</td><td class="num"><b>${pctp(s.post_cur,2)}</b></td><td class="num">${pctp(s.pre_rub,2)}</td><td class="num"><b>${pctp(s.post_rub,2)}</b></td><td class="num">${dbxM(s.base_rub)}</td>
      <td class="num ${s.tax_rub>0?'neg':''}">${dbxM(s.tax_rub)}${s.tax_rub>0?` <small class="mu">${dbxN(s.tax_rate*100,1)} %</small>`:''}${s.trap?' <span class="tag neg" title="Доход в валюте около нуля, но налог начислен из-за ослабления рубля">налог без дохода</span>':''}</td></tr>`).join('')+`</tbody></table></div>`;
    if(r.scenarios.some(s=>s.trap))h+=`<div class="msg" style="margin-top:12px">Выделенные сценарии показывают налоговую ловушку: в валюте дохода почти нет, но рубль ослабел, и разница курсов при погашении облагается налогом как доход в рублях.</div>`;
  }
  h+=`<p class="note" style="margin-top:12px">Модель: налоговая база в рублях = купоны по курсу ЦБ на дату выплаты + погашение по курсу на дату погашения − (цена покупки + НКД) по курсу на дату покупки. Курс до сценарного значения движется линейно от курса покупки; купоны приближённо распределены равными долями назад от даты погашения. Ставка — 13 % до порога и 15 % с превышения (2,4 млн ₽ с 2025 года) с учётом введённого «прочего дохода»; налог условно удержан при погашении и пересчитан в валюту по курсу погашения. Не учтены: ЛДВ, убытки прошлых лет, комиссии, налоги иностранных источников, реальная схема выплаты купонов, выплата в рублях вместо валюты.</p></div>`;
  return h;
}
function pDbx(){
  const D=S.dbx;
  const tabs=[['lnk','Линкеры'],['off','Оферты'],['fx','Валютные и замещающие']];
  const body=D.tab==='lnk'?dbxLinkers():D.tab==='off'?dbxOffers():dbxFx();
  return`<div class="seg" id="dbx-tabs" style="margin-bottom:14px">${tabs.map(([k,t])=>`<button data-t="${k}" class="${D.tab===k?'on':''}">${t}</button>`).join('')}</div>${body}${NIR_NOTE}`;
}
function dbxRun(){
  const D=S.dbx,f=D.f;D.fxLoad=true;D.fxErr=null;renderSoon();
  const p=new URLSearchParams({cur:f.cur,nominal:f.nominal,price:f.price,coupon:f.coupon,freq:f.freq,mat:f.mat,qty:f.qty,nkd:f.nkd,other:f.other,scenarios:f.scenarios});
  if(f.buy_fx)p.set('buy_fx',f.buy_fx);
  api('/api/dbx/fx?'+p).then(j=>{if(j.error){D.fxErr=j.error;D.fxRes=null}else D.fxRes=j}).catch(e=>{D.fxErr=e.message||String(e)}).then(()=>{D.fxLoad=false;if(S.page==='dbx')renderSoon()});
}
function bindDbx(){
  const D=S.dbx,el=id=>document.getElementById(id);
  document.querySelectorAll('#dbx-tabs button').forEach(b=>b.onclick=()=>{D.tab=b.dataset.t;renderSoon()});
  const g=el('dbx-gr');if(g)g.onchange=()=>{D.offGrade=g.value;renderSoon()};
  const re=el('dbx-off-re');if(re)re.onclick=()=>{api('/api/dbx/offers?force=1').then(j=>{D.off=j}).catch(()=>{}).then(()=>{renderSoon();dbxPoll()})};
  ['nominal','price','nkd','coupon','freq','mat','buy_fx','qty','other','scenarios'].forEach(k=>{const e=el('dbx-'+k);if(e)e.oninput=()=>{D.f[k]=e.value}});
  const cu=el('dbx-cur');if(cu)cu.onchange=()=>{D.f.cur=cu.value};
  const bo=el('dbx-bond');
  if(bo)bo.onchange=()=>{const b=((D.fxb&&D.fxb.rows)||[]).find(x=>x.id===bo.value);if(!b)return;
    Object.assign(D.f,{cur:b.cur,nominal:String(b.nominal||1000),price:String(b.price),coupon:String(b.coupon||0),mat:b.mat,buy_fx:''});renderSoon()};
  const run=el('dbx-run');if(run)run.onclick=dbxRun;
  dbxPoll();
}
regPage('dbx',{title:'Линкеры, оферты, валютные',group:'Рынок',icon:'<path d="M3 17l5-5 4 4 8-9"/><path d="M15 7h5v5"/>',render:pDbx,bind:bindDbx,pro:true});
