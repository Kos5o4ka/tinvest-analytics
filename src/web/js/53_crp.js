/* ── Устойчивость эмитентов: банкротные модели, расширенный долг, риск размытия ── */
S.crp={q:'',card:null,loading:false,batch:null,bLoading:false,prog:null,err:null};
const crpN=(v,d=2)=>v==null||isNaN(v)?'—':v.toFixed(d).replace('.',',');
const crpM=v=>v==null?'—':short(v*1000);           /* тыс. ₽ -> ₽ */
const crpX=v=>v==null?'—':crpN(v,1)+'×';
const crpZone=m=>!m||m.na?'<span class="mu" title="Модель не рассчитывается для банков, лизинга, МФО и других финансовых компаний">неприменимо</span>':!m.ok?`<span class="mu" title="${esc(m.reason||'')}">нет данных</span>`:`<span class="tag ${m.key==='high'?'neg':'pos'}">${esc(m.zone)}</span>`;
function crpFmtDate(s){return s?String(s).slice(0,10).split('-').reverse().join('.'):'—'}

function loadCrp(q,force){
  if(S.crp.loading)return;S.crp.loading=true;S.crp.err=null;S.crp.card=null;S.crp.q=q;
  api('/api/crp?q='+encodeURIComponent(q)+(force?'&force=1':'')).then(c=>{S.crp.card=c}).catch(e=>{S.crp.err=e.message||String(e)})
   .then(()=>{S.crp.loading=false;if(S.page==='crp')renderSoon()});
}
function loadCrpBatch(force){
  if(S.crp.bLoading)return;S.crp.bLoading=true;S.crp.prog=null;const acc=S.account;let first=true;
  const tick=async()=>{
    try{
      const p=new URLSearchParams({account:acc});if(force&&first)p.set('force','1');first=false;
      const j=await api('/api/crp/batch?'+p);
      if(j.pending){S.crp.prog=j;const e=document.getElementById('crp-prog');if(e)e.textContent=j.total?`${j.done} из ${j.total}`:'определяю эмитентов…';setTimeout(tick,2500);return}
      S.crp.batch=j;S.crp.bLoading=false;if(S.page==='crp')renderSoon();
    }catch(e){S.crp.batch={error:e.message||String(e)};S.crp.bLoading=false;if(S.page==='crp')renderSoon()}
  };
  tick();
}
function crpModelTable(c){
  const ys=c.years;
  const head=`<tr><th class="l">Показатель</th>${ys.map(y=>`<th>${y.y}</th>`).join('')}</tr>`;
  const sv=(f)=>ys.map(y=>`<td class="num">${f(y)}</td>`).join('');
  const z=y=>y.sav.ok?`<b>${crpN(y.sav.z)}</b>`:'—',r=y=>y.sk.ok?`<b>${crpN(y.sk.r)}</b>`:'—';
  const xs=(m,k)=>y=>m(y).ok?crpN(m(y).x[k]):'—';
  let h=`<div class="tbl"><table><thead>${head}</thead><tbody>
    <tr class="crp-h"><td class="l" colspan="${ys.length+1}">Савицкая: Z = 0,111·X1 + 13,239·X2 + 1,676·X3 + 0,515·X4 + 3,80·X5; Z &lt; 8 — высокий риск</td></tr>
    <tr><td class="l"><b>Z</b></td>${sv(z)}</tr>
    <tr><td class="l">Зона</td>${sv(y=>crpZone(y.sav))}</tr>`;
  [['X1','X1 · (капитал − внеоборотные) / оборотные активы'],['X2','X2 · оборотные / внеоборотные активы'],['X3','X3 · выручка / средние активы'],['X4','X4 · чистая прибыль / активы'],['X5','X5 · капитал / активы']].forEach(([k,t])=>{
    h+=`<tr class="crp-s"><td class="l">${t}</td>${sv(xs(y=>y.sav,k))}</tr>`});
  h+=`<tr class="crp-h"><td class="l" colspan="${ys.length+1}">Сайфуллин–Кадыков: R = 2·K1 + 0,1·K2 + 0,08·K3 + 0,45·K4 + K5; R &lt; 1 — неудовлетворительное состояние</td></tr>
    <tr><td class="l"><b>R</b></td>${sv(r)}</tr><tr><td class="l">Зона</td>${sv(y=>crpZone(y.sk))}</tr>`;
  [['K1','K1 · (капитал − внеоборотные) / оборотные активы'],['K2','K2 · оборотные активы / краткосрочные обязательства'],['K3','K3 · выручка / средние активы'],['K4','K4 · прибыль от продаж / выручка'],['K5','K5 · чистая прибыль / капитал']].forEach(([k,t])=>{
    h+=`<tr class="crp-s"><td class="l">${t}</td>${sv(xs(y=>y.sk,k))}</tr>`});
  return h+'</tbody></table></div>';
}
function crpDebtTable(c){
  const ys=c.years.filter(y=>y.debt&&y.debt.ok);
  if(!ys.length)return'<div class="mu">В отчётности нет строк с обязательствами.</div>';
  const row=(t,f,cl)=>`<tr class="${cl||''}"><td class="l">${t}</td>${ys.map(y=>`<td class="num">${f(y.debt)}</td>`).join('')}</tr>`;
  let h=`<div class="tbl"><table><thead><tr><th class="l">млн ₽ (РСБУ)</th>${ys.map(y=>`<th>${y.y}</th>`).join('')}</tr></thead><tbody>`;
  const comp=(code)=>d=>{const x=d.components.find(z=>z.code===code);return x&&x.value!=null?crpM(x.value):'—'};
  h+=row('1410 Долгосрочные заимствования',comp('1410'))+row('1510 Краткосрочные заимствования',comp('1510'))+row('<b>Отражённый долг</b>',d=>`<b>${crpM(d.reported)}</b>`);
  h+=row('1450 Прочие долгосрочные обязательства (часто аренда)',comp('1450'),'crp-s')+row('1550 Прочие краткосрочные обязательства',comp('1550'),'crp-s')+row('1540 Оценочные обязательства',comp('1540'),'crp-s');
  h+=row('<b>Расширенный долг</b>',d=>`<b>${crpM(d.extended)}</b>`)+row('Превышение над отражённым',d=>d.uplift==null?(d.flag?'есть':'—'):`<span class="${d.flag?'neg':''}">+${crpN(d.uplift*100,0)} %</span>`);
  h+=row('Отражённый долг / EBIT',d=>crpX(d.rep_ebit))+row('Расширенный долг / EBIT',d=>crpX(d.ext_ebit))+row('Отражённый долг / капитал',d=>crpX(d.rep_eq))+row('Расширенный долг / капитал',d=>crpX(d.ext_eq));
  h+=row('EBIT (стр. 2200, прибыль от продаж)',d=>crpM(d.ebit),'crp-s');
  return h+'</tbody></table></div>';
}
function crpDilution(c){
  const d=c.dilution||{},m=d.matches||[],lk=d.links||{};
  let h='';
  if(!d.n_scanned)h+=`<div class="mu">Данных для проверки нет: в приложении нет потока раскрытий по акциям этого эмитента (покрытие — только выпуски облигаций, и то не для всех).</div>`;
  else if(!m.length)h+=`<div class="mu">Проверено заголовков раскрытий: ${d.n_scanned}. Упоминаний допэмиссии, конвертируемых облигаций, опционных программ, выкупа акций и lock-up не найдено.</div>`;
  else h+=`<div class="tbl"><table><thead><tr><th class="l">Дата</th><th class="l">Признак</th><th class="l">Раскрытие</th></tr></thead><tbody>${m.map(x=>`<tr><td class="l">${crpFmtDate(x.date)}</td><td class="l"><span class="tag">${esc(x.label)}</span></td><td class="l">${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a>`:esc(x.title)}</td></tr>`).join('')}</tbody></table></div>`;
  h+=`<p class="note">Поиск по ключевым словам в заголовках — это грубый признак, а не оценка вероятности размытия. `+(lk.edisclosure?`Первоисточник: <a href="${esc(lk.edisclosure)}" target="_blank" rel="noopener">раскрытие информации эмитента</a>.`:'')+`</p>`;
  return h;
}
function crpCard(c){
  if(!c.ok)return`<div class="msg err">${esc(c.error||'Ошибка')}</div>`;
  let h=`<div class="card"><h2>${esc(c.name||'Эмитент')}<span class="sp">ИНН ${esc(c.inn)}${c.is_fin?' · финансовая компания':''}</span></h2>`;
  if(!c.years.length)return h+`<div class="mu">${esc(c.note||'Отчётность по РСБУ не найдена.')}</div></div>`+`<div class="card"><h2>Риск размытия</h2>${crpDilution(c)}</div>`;
  if(c.is_fin)h+=`<div class="msg">Банкротные модели Савицкой и Сайфуллина–Кадыкова не применяются к банкам, лизингу, МФО и прочим финансовым компаниям — вместо чисел показано «неприменимо».</div>`;
  h+=`<h3 style="margin:10px 0 6px">Модели вероятности банкротства по РСБУ</h3>${crpModelTable(c)}
    <p class="note">Модели разработаны для нефинансовых компаний на данных отчётности и дают лишь ориентир. Для расчёта оборотов используется средняя величина активов за год и предыдущий (если отчётность за предыдущий год найдена, иначе — активы на конец года).</p></div>`;
  h+=`<div class="card"><h2>Расширенная долговая нагрузка<span class="sp">приближение по балансу</span></h2>${crpDebtTable(c)}`;
  const l=c.years[c.years.length-1];
  if(l&&l.debt&&l.debt.flag)h+=`<div class="msg err">За ${l.y} г. расширенный долг больше отражённого на ${l.debt.uplift==null?'(отражённого долга нет)':crpN(l.debt.uplift*100,0)+' %'} (порог — 25 %): значительная часть обязательств не названа заимствованиями.</div>`;
  h+=`<p class="note">В расширенный долг входят заимствования (стр. 1410, 1510), прочие долгосрочные и краткосрочные обязательства (1450, 1550) и оценочные обязательства (1540). Выданные гарантии (забалансовый счёт 008) и цифровые финансовые активы (ЦФА) в публичных формах РСБУ не раскрываются и в расчёт НЕ включены; EBIT — прибыль от продаж (стр. 2200) без добавления амортизации, так как её нет в публичных формах 1 и 2. Это оценка по балансу, а не данные эмитента о долге.</p></div>`;
  h+=`<div class="card"><h2>Риск размытия<span class="sp">ключевые слова в раскрытиях</span></h2>${crpDilution(c)}</div>`;
  return h;
}
function crpBatch(){
  const b=S.crp.batch;
  if(S.crp.bLoading)return`<div class="card">${waitBox('Считаю эмитентов портфеля (может занять несколько минут)… <span id="crp-prog">'+(S.crp.prog&&S.crp.prog.total?`${S.crp.prog.done} из ${S.crp.prog.total}`:'')+'</span>')}</div>`;
  if(!b)return'';
  if(b.error)return`<div class="msg err">${esc(b.error)}</div>`;
  if(!b.rows.length)return'<div class="card empty">В портфеле нет эмитентов, для которых можно получить отчётность</div>';
  const zt=(v,k)=>v==null?'<span class="mu">—</span>':`<span class="${k==='high'?'neg':'pos'}">${crpN(v)}</span>`;
  return`<div class="card"><h2>Эмитенты портфеля<span class="sp">нажмите на строку — подробности</span></h2><div class="tbl"><table><thead><tr><th class="l">Эмитент</th><th>Год</th><th>Z Савицкой</th><th>R Сайфуллина–Кадыкова</th><th>Расш. долг / EBIT</th><th>Превышение долга</th><th>Размытие</th></tr></thead><tbody>${b.rows.map(r=>`<tr class="crp-r" data-crp="${esc(r.q||r.inn||'')}"><td class="l"><b>${esc(r.name||'')}</b>${r.note&&!r.year?`<br><small class="mu">${esc(r.note)}</small>`:''}</td><td class="num">${r.year||'—'}</td>
    <td class="num">${r.is_fin?'<span class="mu">неприменимо</span>':zt(r.sav,r.sav_key)}</td><td class="num">${r.is_fin?'<span class="mu">неприменимо</span>':zt(r.sk,r.sk_key)}</td><td class="num">${crpX(r.ext_ebit)}</td>
    <td class="num">${r.uplift==null?'—':`<span class="${r.flag?'neg':''}">+${crpN(r.uplift*100,0)} %</span>`}</td><td class="num">${r.n_dil?`<span class="tag">${r.n_dil}</span>`:'—'}</td></tr>`).join('')}</tbody></table></div>
    <p class="note">Обновлено ${esc(b.updated||'')}. Z &lt; 8 по Савицкой и R &lt; 1 по Сайфуллину–Кадыкову — зоны повышенного риска по этим моделям.</p></div>`;
}
function pCrp(){
  const C=S.crp;
  let h=`<div class="card"><h2>Устойчивость эмитентов<span class="sp">РСБУ из ГИР БО ФНС · модели банкротства, долг, размытие</span></h2>
    <div class="flt"><label class="field"><span>ISIN, тикер или ИНН</span><input class="in" id="crp-q" value="${esc(C.q)}" placeholder="например, RU000A0JX0J2, SBER или 7707083893" autocomplete="off"></label>
    <button class="btn" id="crp-go">Рассчитать</button><button class="btn ghost" id="crp-my">Мои эмитенты</button></div>
    <p class="note">Все модели — приближение по публичной бухгалтерской отчётности отдельной компании (не группы). Результаты зависят от допущений и качества отчётности и не являются прогнозом. Покрытие раскрытий для оценки размытия ограничено.</p></div>`;
  if(C.loading)h+=`<div class="card">${waitBox('Загружаю отчётность…')}</div>`;
  else if(C.err)h+=`<div class="msg err">${esc(C.err)}</div>`;
  else if(C.card)h+=crpCard(C.card);
  h+=crpBatch();
  return h+NIR_NOTE;
}
function bindCrp(){
  const go=()=>{const v=(document.getElementById('crp-q')||{}).value||'';if(v.trim())loadCrp(v.trim(),false);renderSoon()};
  const b=document.getElementById('crp-go');if(b)b.onclick=go;
  const i=document.getElementById('crp-q');if(i){i.onkeydown=e=>{if(e.key==='Enter')go()};i.oninput=()=>{S.crp.q=i.value}}
  const m=document.getElementById('crp-my');if(m)m.onclick=()=>{loadCrpBatch(!!S.crp.batch);renderSoon()};
  document.querySelectorAll('tr[data-crp]').forEach(tr=>{tr.style.cursor='pointer';tr.onclick=()=>{const q=tr.dataset.crp;if(q){loadCrp(q,false);renderSoon();window.scrollTo(0,0)}}});
}
regPage('crp',{title:'Устойчивость эмитентов',group:'Риски и контроль',icon:'<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"/><path d="M9 12l2 2 4-4"/>',render:pCrp,bind:bindCrp,pro:true});
