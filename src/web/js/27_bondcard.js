// ── карточка облигации (боковая панель): клик по любому элементу с data-isin ──
const BC={stack:[],tok:0,all:false,iss:{},tab:'overview',list:[],cur:null,card:null};
const BC_SEC={financial:'Финансы',industrials:'Промышленность',materials:'Сырьё',energy:'Энергетика',consumer:'Потребительский',government:'Государственные',real_estate:'Недвижимость',telecom:'Телеком',municipal:'Муниципальные',utilities:'Коммунальные',it:'IT',health_care:'Здравоохранение',other:'Прочее'};
const BC_EV={coupon:'Купон',amort:'Амортизация',offer:'Оферта',redemption:'Погашение'};
const BC_OK={put:['PUT — право продать эмитенту','of-t-put','Право держателя: в период предъявления можно подать заявку через брокера, эмитент выкупит бумагу по цене оферты.'],call:['CALL — эмитент может погасить досрочно','of-t-call','Право эмитента: он может досрочно погасить выпуск. Заявку подавать не нужно, но возможен риск реинвестирования.'],unknown:['тип не указан','of-t-unk','Источники не сообщают, чей это выбор — держателя или эмитента. Проверьте документы выпуска.']};
const bcOfKind=k=>{const t=BC_OK[k]||BC_OK.unknown;return`<span class="tag ${t[1]}" title="${esc(t[2])}">${esc(t[0])}</span>`};
const BC_KR_SRC={cbr:'ключевая ставка по прогнозу ЦБ',survey:'ключевая ставка по опросу аналитиков ЦБ',market:'ключевая ставка по ожиданиям рынка (КБД)',flat:'текущая ключевая ставка'};
const BC_RISK={RISK_LEVEL_LOW:'низкий',RISK_LEVEL_MODERATE:'средний',RISK_LEVEL_HIGH:'высокий'};
const BC_TABS=[['overview','Обзор и параметры'],['flows','Денежный поток и оферты'],['issuer','Эмитент и рейтинги'],['analogs','Аналоги и кривая']];

function bcCollectList(){
  const seen=new Set(),out=[];
  document.querySelectorAll('#view table tbody tr[data-isin]').forEach(tr=>{
    if(tr.style.display==='none')return;
    const i=String(tr.dataset.isin||'').trim().toUpperCase();
    if(i&&!seen.has(i)){seen.add(i);out.push(i)}
  });
  return out;
}

document.addEventListener('click',e=>{
  const t=e.target.closest('[data-isin]');
  if(t&&t.dataset.isin&&!e.target.closest('a,button,input,select')){
    const inDrawer=!!t.closest('#bc-ov');
    openBond(t.dataset.isin,inDrawer?{fromDrawer:true}:{});
  }
});
document.addEventListener('keydown',e=>{
  const ov=document.getElementById('bc-ov');
  if(!ov)return;
  if(e.key==='Escape'){closeBond();return}
  if(e.key==='ArrowUp'||e.key==='ArrowDown'){
    const a=document.activeElement,tag=a&&a.tagName;
    if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||(a&&a.isContentEditable))return;
    if(BC.list.length<2)return;
    e.preventDefault();e.stopPropagation();
    const cur=String(BC.stack[BC.stack.length-1]||'').toUpperCase();
    let idx=BC.list.indexOf(cur);
    if(idx<0)idx=0;
    else idx=Math.max(0,Math.min(BC.list.length-1,idx+(e.key==='ArrowDown'?1:-1)));
    const nx=BC.list[idx];
    if(nx&&nx!==cur){
      BC.stack[BC.stack.length-1]=nx;
      openBond(nx,{keepTab:true,fromNav:true});
    }
  }
},true);

/* Плавное закрытие выезжающей панели: id снимаем сразу (для кода панель уже закрыта), узел удаляем после анимации. */
function ovLeave(o){
  if(!o)return;
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){o.remove();return}
  const dr=o.firstElementChild;
  if(dr){const cs=getComputedStyle(dr);dr.style.cssText+=`;width:${dr.offsetWidth}px;height:100%;flex:none;background:${cs.backgroundColor};overflow:hidden;border-left:${cs.borderLeft};box-shadow:${cs.boxShadow}`;dr.removeAttribute('id')}
  o.style.cssText+=';position:fixed;inset:0;z-index:41;display:flex;justify-content:flex-end;background:#03050a99';
  o.removeAttribute('id');
  o.classList.add('ov-leave');o.style.pointerEvents='none';setTimeout(()=>o.remove(),240);
}
function closeBond(){
  BC.stack=[];BC.list=[];BC.card=null;BC.tok++;
  ovLeave(document.getElementById('bc-ov'));
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
  const cur=String(BC.stack[BC.stack.length-1]||'').toUpperCase();
  const idx=BC.list.indexOf(cur);
  const nav=BC.list.length>1&&idx>=0?`<span class="bc-nav-btns"><button type="button" class="btn ghost" id="bc-prev" ${idx<=0?'disabled':''} title="Предыдущая бумага (↑)" aria-label="Предыдущая бумага">↑</button><span class="bc-nav-pos num">${idx+1} / ${BC.list.length}</span><button type="button" class="btn ghost" id="bc-next" ${idx>=BC.list.length-1?'disabled':''} title="Следующая бумага (↓)" aria-label="Следующая бумага">↓</button></span>`:'';
  const wt=typeof watchToggle==='function'?'<button class="btn ghost" id="bc-watch" title="Добавить выпуск в список наблюдения">★ В наблюдение</button>':'';
  const cm=typeof cmpHas==='function'?`<button class="btn ghost" id="bc-cmp" title="Добавить выпуск в сравнение облигаций">${cmpHas(BC.stack[BC.stack.length-1])?'✓ В сравнении':'⇄ Сравнить'}</button>`:'';
  return`<div class="bc-bar">${back}${nav}<span class="sp"></span>${cm}${wt}<button class="btn ghost" id="bc-x" aria-label="Закрыть">✕ Закрыть</button></div>`;
}
function bcRenderCard(dr,c,tok){
  BC.card=c;
  dr.innerHTML=bcBar()+bcBody(c);
  bcBind(dr,c,tok);
  bcCharts(dr,c);
  bcIssuer(dr,c,tok);
}
function bcBind(dr,c,tok){
  const x=dr.querySelector('#bc-x');if(x)x.onclick=closeBond;
  const w=dr.querySelector('#bc-watch');
  if(w)w.onclick=()=>{try{watchToggle(BC.stack[BC.stack.length-1])}catch(e){}};
  const cb=dr.querySelector('#bc-cmp');
  if(cb)cb.onclick=()=>{const i=BC.stack[BC.stack.length-1];if(cmpHas(i)){closeBond();go('cmp')}else if(cmpAdd(i))cb.textContent='✓ В сравнении'};
  const b=dr.querySelector('#bc-back');
  if(b)b.onclick=()=>{BC.stack.pop();const p=BC.stack.pop();openBond(p,{fromNav:true})};
  const pv=dr.querySelector('#bc-prev'),nx=dr.querySelector('#bc-next');
  const step=d=>{const cur=String(BC.stack[BC.stack.length-1]||'').toUpperCase(),i=BC.list.indexOf(cur);if(i<0)return;const ni=i+d;if(ni>=0&&ni<BC.list.length){BC.stack[BC.stack.length-1]=BC.list[ni];openBond(BC.list[ni],{keepTab:true,fromNav:true})}};
  if(pv)pv.onclick=()=>step(-1);
  if(nx)nx.onclick=()=>step(1);
  const cp=dr.querySelector('[data-bc-copy]');
  if(cp)cp.onclick=e=>{
    e.stopPropagation();
    copyText(cp.dataset.bcCopy,'ISIN скопирован');
    const st=cp.querySelector('.bc-cp-st');
    if(st){st.textContent='✓ Скопировано';st.classList.add('done');clearTimeout(cp._t);cp._t=setTimeout(()=>{st.textContent='Копировать';st.classList.remove('done')},1800)}
  };
  const tb=dr.querySelector('#bc-tabs');
  if(tb)tb.onclick=e=>{
    const bt=e.target.closest('[data-bct]');if(!bt||bt.dataset.bct===BC.tab||!c)return;
    BC.tab=bt.dataset.bct;bcRenderCard(dr,c,tok);
  };
  const mr=dr.querySelector('#bc-more');
  if(mr&&c)mr.onclick=()=>{BC.all=true;bcRenderCard(dr,c,tok);BC.all=false};
}
async function openBond(isin,opts){
  isin=String(isin||'').trim().toUpperCase();if(!isin)return;
  if(!opts||(!opts.fromNav&&!opts.fromDrawer)){
    BC.list=bcCollectList();
    BC.stack=[isin];
  }else if(!opts.fromNav){
    if(BC.stack[BC.stack.length-1]!==isin)BC.stack.push(isin);
  }
  if(!opts||!opts.keepTab)BC.tab='overview';
  const tok=++BC.tok,dr=bcMount();
  dr.innerHTML=bcBar()+`<div class="bc-load">Загружаю данные по ${esc(isin)}…</div>`;bcBind(dr,null,tok);dr.scrollTop=0;
  let c;
  try{c=await api('/api/bond?isin='+encodeURIComponent(isin))}
  catch(e){if(tok!==BC.tok)return;dr.innerHTML=bcBar()+`<div class="st-callout warn">Не удалось загрузить карточку: ${esc(e.message||e)}</div>`;bcBind(dr,null,tok);return}
  if(tok!==BC.tok)return;
  bcRenderCard(dr,c,tok);
}
/* Ссылки на документы выпуска (решение о выпуске, проспект, оферты). */
document.addEventListener('click',e=>{
  const a=e.target.closest&&e.target.closest('a[data-copy-open]');
  if(a)copyText(a.dataset.copyOpen,'ИНН '+a.dataset.copyOpen+' скопирован — вставьте его в поиск на e-disclosure');
});
function bcDocLinks(isin,inn,secid){
  isin=String(isin||'').trim().toUpperCase();inn=String(inn||'').replace(/\D/g,'');if(inn.length!==10&&inn.length!==12)inn='';
  const q=inn||isin,code=String(secid||isin||'').trim();
  const a=(u,t,cp)=>`<a class="btn ghost" href="${esc(u)}" target="_blank" rel="noopener"${cp?` data-copy-open="${esc(cp)}" title="Откроет поиск и скопирует ИНН ${esc(cp)}"`:''}>${t} ↗</a>`;
  return`<div class="bc-docs">${inn?a('https://disclosure.skrin.ru/disclosure/'+inn,'Раскрытие информации эмитента (СКРИН)'):''}${q?a('https://www.e-disclosure.ru/poisk-po-kompaniyam?query='+encodeURIComponent(q),inn?'Поиск на e-disclosure (ИНН скопируется)':'Раскрытие информации эмитента (e-disclosure)',inn):''}${code?a('https://www.moex.com/ru/issue.aspx?code='+encodeURIComponent(code),'Страница выпуска на Мосбирже'):''}</div>`
    +`<p class="note" style="margin-top:8px">Условия оферт (put/call), купонов и досрочного погашения — в решении о выпуске и проспекте.${inn?'':' ИНН эмитента не определён — поиск по ISIN может ничего не найти, тогда введите название эмитента на сайте.'}</p>`;
}
const bcN=(v,d=2)=>v==null||isNaN(v)?'—':Number(v).toFixed(d).replace('.',',');
function bcKpi(k,v,s,cls){return`<div class="card"><div class="k">${k}</div><div class="v num ${cls||''}">${v}</div>${s?`<div class="s">${s}</div>`:''}</div>`}
function bcTile(lbl,val,sub,dot,cls){
  return`<div class="st-tile"><div class="st-tl"><span>${lbl}</span><span class="st-dot ${dot||'mu'}"></span></div><div class="st-tv num ${cls||''}">${val}</div><div class="st-ts">${sub||'&nbsp;'}</div></div>`;
}
/* Раскрытие информации: сколько бумаг в рынке (по последнему купону, иначе по объёму выпуска) и последние факты с сервера данных */
const BC_DISC_KIND={coupon_paid:'Купон выплачен',coupon_declared:'Ставка купона',default:'Неисполнение',buyback_result:'Итоги выкупа',placement_result:'Размещение / доразмещение'};
function bcOutLine(o){
  if(!o||o.qty==null)return'';
  const fmt=n=>Number(n).toLocaleString('ru-RU');
  const sh=o.share!=null?` (${Math.round(o.share*100)} % выпуска)`:'';
  const su=safeUrl(o.doc_url),src=su?`<a href="${esc(su)}" target="_blank" rel="noopener">источник ↗</a>`:'';
  const M={coupon_explicit:'купону',coupon_derived:'купону (выведено из суммы выплаты)',declared_derived:'объявлению о купоне (выведено из суммы)'};
  let how;
  if(M[o.method])how=`по ${M[o.method]}${o.coupon_no?' №'+esc(String(o.coupon_no)):''}${o.as_of?' от '+ddm(o.as_of):''}`;
  else how=o.method==='issue_placed'?'по размещённому объёму выпуска (Мосбиржа)':'по объёму выпуска (Мосбиржа)';
  const bb=o.buybacks_after?` · выкупов после купона: ${o.buybacks_after}`:'';
  const over=o.over_issue_size?' <span class="tag">выше ISSUESIZE (допвыпуск)</span>':'';
  const chips=[];
  const msOnly=!M[o.method]&&!(o.buybacks||[]).length&&!(o.placements||[]).length;
  if(o.issue_size!=null)chips.push(msOnly?`<span>Объём выпуска по Мосбирже сейчас: <b class="num">${fmt(o.issue_size)} шт.</b>${o.issue_date?' · в обращении с '+ddm(o.issue_date):''}</span>`
    :`<span>Выпущено: <b class="num">${fmt(o.issue_size)} шт.</b>${o.issue_date?' от '+ddm(o.issue_date):''}</span>`);
  if(o.placed!=null&&o.placed!==o.issue_size)chips.push(`<span>Размещено первично: <b class="num">${fmt(o.placed)} шт.</b></span>`);
  if(o.added_total>0)chips.push(`<span class="pos">Допвыпуск / доразмещение: <b class="num">+${fmt(o.added_total)} шт.</b></span>`);
  if(o.buybacks_total>0)chips.push(`<span class="neg">Выкуплено (оферты/выкупы): <b class="num">−${fmt(o.buybacks_total)} шт.</b></span>`);
  const evs=o.events||[];
  let tl='';
  if(evs.length>1||(evs.length===1&&evs[0].kind!=='issue')){
    const rows=evs.map(e=>{
      const dlt=e.delta==null?'—':(e.kind==='issue'?fmt(e.delta)+' шт.':(e.delta>0?`<span class="pos">+${fmt(e.delta)} шт.</span>`:`<span class="neg">−${fmt(Math.abs(e.delta))} шт.</span>`));
      const eu=safeUrl(e.url);
      return`<tr><td class="l">${e.date?ddm(e.date):'—'}</td><td class="l">${esc(e.label||e.kind)}</td><td class="num">${dlt}</td><td>${eu?`<a href="${esc(eu)}" target="_blank" rel="noopener">↗</a>`:''}</td></tr>`;
    }).join('');
    tl=`<details class="bc-out-det"><summary>История изменения объёма (${evs.length})</summary><div class="tbl"><table><thead><tr><th class="l">Дата</th><th class="l">Событие</th><th>Объём / изменение</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
  }
  const msNote=msOnly?`<div class="note" style="margin-top:6px">Мосбиржа уменьшает объём выпуска после выкупа на оферте, поэтому первоначальный объём и выкупы видны только по сообщениям эмитента — их разбирает сервер данных.</div>`:'';
  return`<div class="bc-out"><div><b>В рынке сейчас:</b> <span class="num">${fmt(o.qty)} шт.</span>${msOnly?'':sh}${over} · <span class="mu">${how}${bb}</span>${src?' · '+src:''}</div>`
    +(chips.length?`<div class="bc-out-meta">${chips.join('')}</div>`:'')+tl+msNote+`</div>`;
}
function bcDisclosure(dc){
  if(!dc)return'';
  const o=bcOutLine(dc.outstanding),fs=dc.facts||[];
  const inv=typeof crowdInviteHtml==='function'?crowdInviteHtml():'';
  if(!o&&!fs.length&&!inv)return'';
  let h=`<div class="card bc-sec"><h2>Раскрытие эмитента<span class="sp">сообщения на e-disclosure, разбор сервера данных</span></h2>${inv}${o}`;
  if(fs.length)h+=`<div class="tbl"><table><thead><tr><th class="l">Дата</th><th class="l">Тип</th><th class="l">Данные</th><th></th></tr></thead><tbody>`
    +fs.map(f=>{const fu=safeUrl(f.url);return`<tr><td class="l">${f.date?ddm(f.date):'—'}</td><td class="l">${esc(BC_DISC_KIND[f.kind]||f.label||f.kind)}</td><td class="l">${esc(f.text||'')}</td><td>${fu?`<a href="${esc(fu)}" target="_blank" rel="noopener">↗</a>`:''}</td></tr>`}).join('')+`</tbody></table></div>`;
  else h+=`<div class="mu" style="font-size:13px">Раскрытий по выпуску пока нет (сервер данных не подключён или сообщений не найдено).</div>`;
  return h+`</div>`;
}
function bcBody(c){
  const m=c.market,ci=c.catalog||{},d=c.desc||{},cur=(m&&m.cur||ci.currency||'RUB').toLowerCase();
  const sec=ci.sector?BC_SEC[ci.sector]||ci.sector:null;
  let h=`<div class="bc-h st-ver"><h1>${esc(c.name||c.isin)}</h1><div class="row2">
    <button type="button" class="bc-isin-cp" data-bc-copy="${esc(c.isin)}" title="Нажмите, чтобы скопировать ISIN"><code>${esc(c.isin)}</code><span class="bc-cp-st">Копировать</span></button>`
    +(c.rating?ratingTag(c.rating):'<span class="tag">нет рейтинга</span>')
    +(sec?`<span class="tag">${esc(sec)}</span>`:'')
    +(ci.floating?`<span class="tag"${c.fl_label&&c.fl_label!=='ФЛОАТЕР'?' title="Спред эмитента к базе по последним купонам"':''}>${c.fl_label&&c.fl_label!=='ФЛОАТЕР'?'флоатер · '+esc(c.fl_label):'флоатер'}</span>`:'')+(ci.amort||(d.AMORTBOND==='1')?'<span class="tag">амортизация</span>':'')
    +(ci.subordinated?'<span class="tag">субординированная</span>':'')+(ci.perpetual?'<span class="tag">бессрочная</span>':'')
    +`<a href="https://www.moex.com/ru/issue.aspx?code=${encodeURIComponent(c.isin)}" target="_blank" rel="noopener" style="margin-left:auto">Страница на Мосбирже ↗</a></div></div>`;
  if(c.errors&&c.errors.length)h+=`<div class="st-callout warn">${c.errors.map(esc).join('<br>')}</div>`;
  if(m){
    const sp=m.spread,_q=(id,t)=>typeof uxTip==='function'?uxTip(id,t):'';
    h+=`<div class="bc-kpis st-tiles">`
      +bcTile('Цена',bcN(m.price,2)+' %',m.nominal?`номинал ${bcN(m.nominal,0)}`:'','mu')
      +bcTile('Доходность '+_q('yield','Доходность к погашению или ближайшей оферте (YTM)'),bcN(m.yield,2)+' %','к погашению/оферте','pos')
      +bcTile('Спред к КБД '+_q('spread','Премия доходности выпуска над безрисковой кривой ОФЗ (КБД)'),sp==null?'—':(sp>0?'+':'')+bcN(sp,2)+' п.п.',c.kbd!=null?`КБД ${bcN(c.kbd,2)} % на ${bcN(m.dur,2)} г.`:'',sp==null?'mu':sp>0?'pos':'neg',sp==null?'':sp>0?'pos':'neg')
      +bcTile('Дюрация '+_q('duration','Чувствительность цены облигации к изменению ставок'),m.dur==null?'—':bcN(m.dur,2)+' г.',`оборот ${short(m.turn||0)}`,'mu')
      +`</div>`;
  }
  const vBits=[];let vWarn=false;
  if(d.HASDEFAULT==='1'){vBits.push('<b class="neg">Допущен дефолт</b>');vWarn=true}
  else if(d.HASTECHNICALDEFAULT==='1'){vBits.push('<b class="neg">Технический дефолт</b>');vWarn=true}
  else if(c.rating&&c.rating.v){
    const bk=rBucket(c.rating.v).split(' ')[0];
    const lvl={AAA:'Надёжность максимальная',AA:'Надёжность высокая',A:'Надёжность выше средней',BBB:'Надёжность умеренная',BB:'Повышенный риск (ВДО)',B:'Высокий риск (ВДО)'}[bk]||'Спекулятивный риск';
    vBits.push(`${lvl} (<b>${esc(c.rating.v)}</b>)`);
  }else if(ci.ofz||String(c.isin||'').startsWith('SU'))vBits.push('Государственный выпуск (<b>ОФЗ</b>)');
  if(m&&m.spread!=null)vBits.push(`спред к КБД <b class="${m.spread>=0?'pos':'neg'}">${m.spread>0?'+':''}${bcN(m.spread,2)} п.п.</b>`);
  if(c.offers&&c.offers.length){
    const o0=c.offers[0];
    vBits.push(`ближайшая оферта <b>${ddm(o0.date)}</b> (${o0.kind==='put'?'PUT — право продать':o0.kind==='call'?'CALL — право эмитента погасить':'оферта'})`);
  }else if(m&&m.mat)vBits.push(`без оферт до погашения ${ddm(m.mat)}`);
  if(vBits.length)h+=`<div class="bc-verdict st-callout${vWarn?' warn':''}">${vBits.join(' · ')}</div>`;
  const tab=BC_TABS.some(x=>x[0]===BC.tab)?BC.tab:'overview';
  h+=`<div class="seg bc-tabs" id="bc-tabs" role="tablist">${BC_TABS.map(([k,t])=>`<button type="button" role="tab" aria-selected="${k===tab}" data-bct="${k}" class="${k===tab?'on':''}">${t}</button>`).join('')}</div>`;
  if(tab==='overview'){
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
    const hs=c.history||{d:[]};
    h+=`<div class="card bc-sec"><h2>История за год<span class="sp">Мосбиржа, основной режим торгов</span></h2>`;
    if(hs.d&&hs.d.length>1)h+=`<div class="mu" style="font-size:12px;margin-bottom:4px">Цена, % от номинала</div><div class="bc-ch" id="bc-ch-p"></div>
        <div class="mu" style="font-size:12px;margin:12px 0 4px">Доходность, % годовых</div><div class="bc-ch" id="bc-ch-y"></div>`;
    else h+=`<div class="mu" style="font-size:13px">История торгов недоступна.</div>`;
    h+=`</div>`;
    h+=`<div class="card bc-sec"><h2>Документы выпуска</h2>${bcDocLinks(c.isin,(c.docs||{}).inn||d.EMITTER_INN,(m&&m.id)||c.isin)}</div>`;
  }else if(tab==='flows'){
    const ofs=c.offers||[];
    if(ofs.length||(m&&m.offer)){
      h+=`<div class="card bc-sec"><h2>График оферт<span class="sp">условия досрочного выкупа или погашения</span></h2><div class="bc-offers-box">`
        +(ofs.length?ofs.map(o=>`<div class="bc-offer-row"><div><b>${ddm(o.date)}</b> ${bcOfKind(o.kind)}</div><div class="mu">${o.period_start&&o.period_end?`Предъявление: ${ddm(o.period_start)} – ${ddm(o.period_end)}`:'Сроки предъявления уточняйте в документах'}</div></div>`).join('')
          :`<div class="bc-offer-row"><div><b>${ddm(m.offer)}</b> ${bcOfKind('put')}</div><div class="mu">Ближайшая дата оферты</div></div>`)
        +`</div><a href="#" class="kb-a" data-kb="offers">Что такое put и call →</a></div>`;
    }
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
  }else if(tab==='issuer'){
    const rk=x=>{const i=RSC.indexOf(x.rating);return i<0?99:i},ra=(c.rating&&c.rating.all||[]).slice().sort((x,y)=>rk(x)-rk(y)||String(x.agency).localeCompare(String(y.agency)));
    h+=`<div class="card bc-sec"><h2>Кредитные рейтинги эмитента</h2>`+(ra.length?`<div class="tbl bc-rt"><table><thead><tr><th>Агентство</th><th>Рейтинг</th><th>Прогноз</th><th>Дата</th><th>Источник</th></tr></thead><tbody>`
      +ra.map(x=>{const u=rtSafeUrl(x.url),tg=`<span class="tag rt rt-${esc(rBucket(x.rating).split(' ')[0])}${u?' rt-click':''}">${esc(x.rating)}</span>`;
        return`<tr><td>${esc(x.agency)}${x.approx?`<div class="mu" style="font-size:11px" title="${esc(x.issuer||'')}">по названию, приблизительно</div>`:''}</td><td>${u?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer" class="bc-rt-a" title="Открыть пресс-релиз">${tg}</a>`:tg}</td><td>${x.outlook?esc(x.outlook):'<span class="mu">—</span>'}</td><td>${x.date?ddm(x.date):'<span class="mu">—</span>'}</td><td>${u?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">Пресс-релиз ↗</a>`:''}</td></tr>`}).join('')
      +`</tbody></table></div>`:'<div class="mu" style="font-size:13px">Рейтинги кредитных агентств не найдены</div>')+`</div>`;
    h+=bcDisclosure(c.disclosure);
    h+=`<div class="card bc-sec" id="bc-iss"><h2>Финансы эмитента<span class="sp">отчётность РСБУ, ГИР БО ФНС</span></h2><div class="mu" style="font-size:13px">Загружаю отчётность эмитента…</div></div>`;
  }else if(tab==='analogs'){
    const ic=c.issuer_curve;
    if(ic&&ic.points&&ic.points.length>1)h+=`<div class="card bc-sec"><h2>Кривая эмитента<span class="sp">${ic.points.length} выпусков в обращении: доходность по сроку</span></h2><div class="bc-ic" id="bc-ic"></div>
      <div class="bc-ic-lg"><span><i class="lg-me"></i>этот выпуск</span><span><i class="lg-ot"></i>другие выпуски эмитента</span><span><i class="lg-fl"></i>флоатер (полая точка)</span><span><i class="lg-ln"></i>линия: выпуски с фиксированным купоном по сроку</span><span><i class="lg-kbd"></i>КБД (бескупонная доходность)</span><em>Клик по точке открывает карточку выпуска.</em></div></div>`;
    const an=c.analogs||[];
    h+=`<div class="card bc-sec"><h2>Аналоги<span class="sp">похожий рейтинг, срок и тип</span></h2>`;
    if(c.rel&&c.rel.text){const ok=c.rel.diff>=0.25,bad_=c.rel.diff<=-0.25;
      h+=`<div class="st-callout${bad_?' warn':''}"><b class="${ok?'pos':bad_?'neg':''}">${esc(c.rel.text)}.</b> Медианный спред аналогов: ${bcN(c.rel.median_spread,2)} п.п. «Дешевле» — выше доходность при сопоставимом риске, но это может отражать и риски, которых нет в рейтинге.</div>`}
    if(an.length){
      h+=`<div class="tbl"><table><thead><tr><th>Выпуск</th><th>Рейтинг</th><th>Сектор</th><th>Дюр., г.</th><th>Доходность</th><th>Спред</th><th>Δ дох.</th><th>Оборот</th></tr></thead><tbody>`
        +an.map(a=>`<tr data-isin="${esc(a.isin)}" title="Открыть карточку"><td class="l">${esc(a.name)}${a.floating?' <span class="tag">флоат</span>':''}${a.amort?' <span class="tag">аморт</span>':''}</td>
          <td>${a.rating?`<span class="tag rt rt-${esc(rBucket(a.rating).split(' ')[0])}">${esc(a.rating)}</span>`:'<span class="mu">—</span>'}</td>
          <td>${esc(BC_SEC[a.sector]||a.sector||'—')}</td><td class="num">${bcN(a.dur,2)}</td><td class="num">${bcN(a.yield,2)} %</td>
          <td class="num">${a.spread==null?'—':(a.spread>0?'+':'')+bcN(a.spread,2)}</td>
          <td class="num ${a.dy>0?'pos':a.dy<0?'neg':''}">${a.dy==null?'—':(a.dy>0?'+':'')+bcN(a.dy,2)}</td><td class="num">${short(a.turn||0)}</td></tr>`).join('')
        +`</tbody></table></div>`;
    }else h+=`<div class="mu" style="font-size:13px">Подходящих аналогов не найдено${m?'':' (нет рыночных данных по выпуску)'}.</div>`;
    h+=`</div>`;
  }
  h+=`<p class="note" style="margin-top:14px">Справочная информация на основе открытых данных Мосбиржи, каталога T-Invest и публичных рейтингов. Аналоги подобраны автоматически по рейтингу, сроку, сектору и типу выпуска; сравнение спреда не учитывает всех различий в риске и ликвидности.</p>${NIR_NOTE}`;
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
  /* сплошная линия — выпуски с фиксированным купоном по возрастанию срока (флоатеры не соединяются: их доходность от срока не зависит) */
  const fl=P.filter(p=>!p.floating).sort((a,b)=>a.dur-b.dur);
  if(fl.length>1)g+=`<polyline class="ic-ln" points="${fl.map(p=>X(p.dur).toFixed(1)+','+Y(p.yield).toFixed(1)).join(' ')}"/>`;
  P.slice().sort((a,b)=>a.me-b.me).forEach(p=>{
    g+=`<circle class="ic-pt${p.me?' ic-me':p.floating?' ic-fl':''}" data-isin="${esc(p.isin)}" cx="${X(p.dur)}" cy="${Y(p.yield)}" r="${p.me?8:5}"><title>${esc(p.name)} · дох. ${bcN(p.yield,2)} % · дюр. ${bcN(p.dur,2)} г.${p.spread==null?'':' · спред '+(p.spread>0?'+':'')+bcN(p.spread,2)}${p.rating?' · '+esc(p.rating):''}${p.floating?' · флоатер':''}</title></circle>`});
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
  if(m.key)h+=`<div class="st-callout"><b class="${m.key==='mkt_higher'?'neg':m.key==='mkt_lower'?'':'pos'}">${esc(m.text)}</b></div>`;
  if(j.history&&(j.history.defaults||j.history.tech))h+=`<div class="st-callout warn">${esc(j.history.verdict)}</div>`;
  const bu=safeUrl(b.url);
  h+=`<div class="mu" style="font-size:12.5px;margin-top:6px">${rs?'Для сравнения, РСБУ отдельной компании: '+rs.score+' ('+esc(rs.label)+'). ':''}${bu?`<a href="${esc(bu)}" target="_blank" rel="noopener">Источник: smart-lab ↗</a>`:'Источник: smart-lab'}</div>
    <button class="btn ghost bc-more" id="bc-iss-more">Подробнее об эмитенте →</button><p class="note" style="margin-top:8px">Скоринг от 0 до 100 по консолидированной отчётности группы (МСФО). Данные агрегатора smart-lab, могут отличаться от официальной отчётности. Не инвестиционная рекомендация.</p>`;
  return h;
}
function bcIssHtml(j,isin){
  const s=j.score||{},f=j.fin||{years:[]},m=j.market||{},is=j.issuer||{};
  if(!j.ok)return`<div class="mu" style="font-size:13px">${esc((j.errors||['Не удалось загрузить данные об эмитенте.'])[0])}</div>`;
  if(j.ifrs&&j.ifrs.score&&j.ifrs.score.ok&&j.ifrs.fin&&j.ifrs.fin.years&&j.ifrs.fin.years.length)return bcIssIfrs(j);
  if(!s.ok)return`<div class="mu" style="font-size:13px">${esc(s.reason||f.note||'Нет данных по РСБУ.')}</div>${j.history?`<div class="st-callout" style="margin-top:8px">${esc(j.history.verdict)}</div>`:''}<button class="btn ghost bc-more" id="bc-iss-more">Подробнее об эмитенте →</button>`;
  const y=f.years[f.years.length-1]||{},fm=s.fin_mode,X=(v,d)=>v==null?'—':bcN(v,d)+'×';
  const nd=y.net_debt!=null&&y.net_debt<=0?'нет':X(y.nd_ebit,1);
  let h=`<div class="bc-iss-top"><span class="iss-sc iss-${esc(s.key)}"><b>${s.score}</b> ${esc(s.label)}</span><span class="mu" style="font-size:12.5px">${esc(is.short||'')} · по отчётности за ${s.year} г.</span></div>
    <div class="bc-kpis">${bcKpi('Покрытие процентов',X(y.cover,1),'EBIT / проценты; норма от 3–4')}
    ${fm?bcKpi('Долг / капитал',X(y.debt_eq,1),'для лизинга до 5–8'):bcKpi('Чистый долг / EBIT',nd,'норма до 2–3 лет')}
    ${bcKpi('Капитал / активы',y.eq_ratio==null?'—':bcN(y.eq_ratio*100,0)+' %','норма от 20–30 %')}
    ${fm?bcKpi('Рентабельность EBIT',y.margin==null||y.margin>1?'—':bcN(y.margin*100,1)+' %','доля прибыли в выручке'):bcKpi('Текущая ликвидность',X(y.cur_liq,2),'норма от 1,2')}</div>`;
  if(m.key)h+=`<div class="st-callout"><b class="${m.key==='mkt_higher'?'neg':m.key==='mkt_lower'?'':'pos'}">${esc(m.text)}</b></div>`;
  if(j.history&&(j.history.defaults||j.history.tech))h+=`<div class="st-callout warn">${esc(j.history.verdict)}</div>`;
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
  const labels=hs.d.map(ddm),p=dr.querySelector('#bc-ch-p'),y=dr.querySelector('#bc-ch-y');
  {
    try{
      if(p)line(p,{h:190,labels,zero:false,fa:v=>bcN(v,1),ft:v=>bcN(v,2)+' %',series:[{n:'Цена',c:'var(--s1)',v:hs.p,w:2}]});
      if(y)line(y,{h:190,labels,zero:false,fa:v=>bcN(v,1),ft:v=>bcN(v,2)+' %',series:[{n:'Доходность',c:'var(--s4)',v:hs.y,w:2}]});
    }catch(e){}
  }
}
