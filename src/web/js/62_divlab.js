/* ── Дивидендные гэпы: радар по портфелю, статистика закрытия гэпа по истории отсечек, надёжность дивиденда, сравнение «удержать / продать накануне» ── */
S.dl={tab:'port',secid:'',data:null,loading:false,err:'',port:null,ploading:false,perr:'',pacc:null,tax:'13',fee:'0.05'};
function dlQs(extra){return new URLSearchParams(Object.assign({account:S.account,tax:S.dl.tax,fee:S.dl.fee},extra||{}))}
function dlLoadPort(force){
  const D=S.dl,acc=S.account;
  if(D.ploading&&!force&&D.pacc===acc)return;
  D.ploading=true;D.pacc=acc;D.perr='';
  api('/api/divlab?'+dlQs()+(force?'&force=1':'')).then(j=>{
    if(D.pacc!==acc)return;D.ploading=false;D.port=j;if(S.page==='dgap')renderSoon();
  }).catch(e=>{if(D.pacc!==acc)return;D.ploading=false;D.perr=e.message||String(e);if(S.page==='dgap')renderSoon()});
}
function dlLoadStock(force){
  const D=S.dl,sec=D.secid;if(!sec||(D.loading&&!force))return;
  D.loading=true;D.err='';
  api('/api/divlab?'+dlQs({secid:sec})+(force?'&force=1':'')).then(j=>{
    D.loading=false;if(D.secid!==sec){dlLoadStock();return}
    D.data=j;if(S.page==='dgap')renderSoon();
  }).catch(e=>{D.loading=false;if(D.secid!==sec)return;D.err=e.message||String(e);if(S.page==='dgap')renderSoon()});
}
function dlOpen(secid){
  secid=String(secid||'').trim().toUpperCase();if(!secid)return;
  const D=S.dl;D.tab='stock';if(D.secid!==secid){D.secid=secid;D.data=null;D.err=''}
  if(S.page==='dgap')render();else go('dgap');
}
const dlN=(v,d=2)=>stkN(v,d);
const dlRub=(v,d=2)=>v==null||isNaN(v)?'—':dlN(v,d)+' ₽';
const dlSg=(v,d=2)=>v==null||isNaN(v)?'—':(v>0?'+':v<0?'−':'')+dlN(Math.abs(v),d)+' ₽';
const dlPct=v=>v==null?'—':dlN(v,1)+' %';
const dlEv=(n,one,few,many)=>{const a=Math.abs(n)%100,b=a%10;return a>10&&a<20?many:b===1?one:b>=2&&b<=4?few:many};
const dlDays=v=>v==null?'—':(Math.round(v*2)/2).toString().replace('.',',')+' дн.';
function dlZoneCls(z){return z==='pos'?'pos':z==='neg'?'neg':z==='warn'?'dl-warn':'mu'}
function dlSafetyTag(score,label,zone){
  if(score==null)return'<span class="mu" title="Недостаточно данных для оценки">нет данных</span>';
  return`<span class="dl-sc ${dlZoneCls(zone)}" title="Оценка надёжности дивиденда 0–100: ${esc(label)}"><b>${score}</b> <small>${esc(label)}</small></span>`;
}
function dlSearchBox(){
  const D=S.dl;
  return`<div class="dl-top"><div class="stk-sw"><input class="in" id="dl-q" placeholder="Тикер или название: SBER, LKOH…" autocomplete="off" spellcheck="false" value="${esc(D.secid)}"><div id="dl-res" class="stk-res"></div></div>
    <label class="field dl-f"><span>Налог на дивиденды, %</span><input class="in num" id="dl-tax" value="${esc(D.tax)}" inputmode="decimal"></label>
    <label class="field dl-f"><span>Комиссия брокера, %</span><input class="in num" id="dl-fee" value="${esc(D.fee)}" inputmode="decimal"></label>
    ${D.secid?'<button class="btn ghost dl-r">Обновить</button>':''}</div>`;
}
/* ── вкладка «Мой портфель» ── */
function dlPortTab(){
  const D=S.dl;
  if(D.pacc!==S.account&&!D.ploading){D.port=null;dlLoadPort(false)}
  if(!D.port&&!D.ploading&&!D.perr)dlLoadPort(false);
  if(D.ploading&&!D.port)return`<div class="card">${waitBox('Смотрю дивиденды по акциям портфеля и историю отсечек. Первый расчёт может занять до минуты…')}</div>`;
  if(D.perr)return`<div class="msg err">${esc(D.perr)} <button class="btn ghost dl-r">Повторить</button></div>`;
  const d=D.port||{},rows=d.rows||[];
  const note=d.error?`<div class="msg info" style="margin-bottom:12px">${esc(d.error)}</div>`:'';
  if(!rows.length){
    return`<div class="card"><h2>Радар дивидендов портфеля</h2>${note}<div class="empty" style="padding:30px 20px">${d.token===false&&!d.held?'Акций в портфеле не найдено. Подключите счёт или импортируйте отчёт брокера — либо откройте вкладку «Анализ акции» и посмотрите историю гэпов любой бумаги.':'В выбранном счёте нет российских акций.'}
      <div class="row" style="justify-content:center"><button class="btn" id="dl-to-stock">Анализ акции</button></div></div></div>`;
  }
  const up=rows.filter(r=>r.next),no=rows.filter(r=>!r.next);
  const th='<th class="l">Бумага</th><th title="Количество акций в портфеле">Шт.</th><th title="Размер дивиденда на одну акцию">Дивиденд</th><th title="Дата закрытия реестра">Фиксация</th><th title="Последний день, когда покупка ещё даёт право на дивиденд (если биржа не указала — оценка по будням, помечена «≈»)">Посл. день покупки</th><th title="Дивиденд × количество акций за вычетом налога">Получите (после налога)</th><th title="Оценка надёжности дивиденда 0–100">Надёжность</th><th title="Медиана числа торговых дней, за которые цена возвращалась к уровню до отсечки">Медиана закрытия гэпа</th>';
  const tr=(r,x)=>`<tr data-dl="${esc(r.secid)}" style="cursor:pointer" title="Открыть анализ"><td class="l"><b>${esc(r.name||r.secid)}</b><br><small class="mu">${esc(r.secid)}</small></td>
    <td class="num">${dlN(r.qty,0)}</td><td class="num">${x?dlRub(x.value,2):'—'}${x?`<br><small class="mu">${r.price?dlN(x.value/r.price*100,1)+' % к цене':''}</small>`:''}</td>
    <td class="num">${x?ddm(x.record):'—'}</td><td class="num">${x&&x.last_buy?(x.last_buy_est?'≈ ':'')+ddm(x.last_buy):'—'}</td>
    <td class="num">${r.net_total!=null?'<b>'+dlRub(r.net_total,0)+'</b>':'—'}</td>
    <td>${dlSafetyTag(r.safety,r.label,r.zone)}</td>
    <td class="num">${r.median_days!=null?dlDays(r.median_days)+`<br><small class="mu">по ${r.events} ${dlEv(r.events,'событию','событиям','событиям')}</small>`:'<span class="mu">нет истории</span>'}</td></tr>`;
  const tot=up.reduce((a,r)=>a+(r.net_total||0),0);
  return`<div class="card"><h2>Ближайшие дивиденды портфеля<span class="sp">${up.length?`итого к получению: ${M(tot,'rub',0)} после налога ${esc(D.tax)} %`:'объявленных дивидендов нет'}</span></h2>${note}
    ${up.length?`<div class="tbl"><table><thead><tr>${th}</tr></thead><tbody>${up.map(r=>tr(r,r.next)).join('')}</tbody></table></div>`:'<div class="empty" style="padding:24px">По акциям портфеля пока нет объявленных будущих дивидендов.</div>'}</div>
    ${no.length?`<div class="card"><h2>Без объявленного дивиденда<span class="sp">показан последний выплаченный</span></h2><div class="tbl"><table><thead><tr>${th}</tr></thead><tbody>${no.map(r=>tr(r,r.last)).join('')}</tbody></table></div></div>`:''}
    <p class="note">Дата фиксации и размер дивиденда — по данным T-Invest (ближайшие значения могут измениться после решения собрания акционеров). Нажмите на строку, чтобы увидеть историю гэпов бумаги. ${NIR_NOTE}</p>`;
}
/* ── вкладка «Анализ акции» ── */
function dlStockHome(){
  const l=(S.stkList||[]).slice(0,16);
  if(!S.stkList)stkEnsureList(()=>{if(S.page==='dgap'&&S.dl.tab==='stock'&&!S.dl.secid)renderSoon()});
  return`<div class="card"><h2>Выберите акцию<span class="sp">или введите тикер выше</span></h2>${S.stkList?`<div class="stk-chips">${l.map(r=>`<button class="btn ghost" data-dl="${esc(r.secid)}"><b>${esc(r.secid)}</b> <span class="mu">${esc(r.shortname||'')}</span></button>`).join('')}</div>`:waitBox('Загружаю список акций…')}</div>
    <p class="note">В день отсечки (на следующий торговый день после последнего дня покупки) цена акции в среднем снижается примерно на размер дивиденда. Здесь по истории видно, как глубоко и как быстро это снижение отыгрывалось. ${NIR_NOTE}</p>`;
}
function dlStats(st){
  const w=st.within||{};
  const tile=(k,v,s,c)=>kpi(k,v,s,c);
  const wp=n=>{const x=w[n]||{};return x.pct!=null?pctp(x.pct,0):'—'};
  const wsub=n=>{const x=w[n]||{};return x.of?`${x.n} из ${x.of} ${dlEv(x.of,'события','событий','событий')}`:'мало данных'};
  return`<div class="g g4 dl-tiles">${tile('Медиана до закрытия гэпа',st.median_days!=null?dlDays(st.median_days):'—',`торговых дней; закрыто ${st.closed} из ${st.count}`)}
    ${tile('Закрыто за 30 дн.',wp('30'),wsub('30'))}${tile('Закрыто за 60 дн.',wp('60'),wsub('60'))}${tile('Закрыто за 90 дн.',wp('90'),wsub('90'))}
    ${tile('Гэп, медиана',st.median_k!=null?pctp(st.median_k*100,0)+' от дивиденда':'—',st.avg_gap_pct!=null?`в среднем ${dlN(st.avg_gap_pct,1)} % от цены`:'')}
    ${tile('Ещё открыты',String(st.still_open||0),'слишком свежие, чтобы судить')}</div>`;
}
function dlHistChart(el,o){
  const h=o.hist,W=el.clientWidth||600,H=230,pl=30,pr=10,pt=18,pb=52,n=h.length,pw=W-pl-pr,ph=H-pt-pb,bw=pw/n;
  const mx=Math.max(1,...h.map(x=>x.n));
  const col=x=>x.label==='не закрыт'?'var(--neg)':x.label==='ещё открыт'?'var(--mu)':'var(--s3)';
  let s='';const G=gradSet();
  (mx<=2?[0,1]:[0,.5,1]).forEach(f=>{const y=pt+ph-f*ph;s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${y}" y2="${y}"/><text class="ax num" x="${pl-6}" y="${y+4}" text-anchor="end">${Math.round(mx*f)}</text>`});
  h.forEach((x,i)=>{
    const bh=x.n/mx*ph,bx=pl+i*bw+bw*.18,w=bw*.64;
    s+=`<path d="${rtop(bx,pt+ph-Math.max(bh,x.n?1.5:0),w,Math.max(bh,x.n?1.5:0),5)}" fill="${G.u(col(x))}"/>`;
    if(x.n)s+=`<text class="ax num" x="${bx+w/2}" y="${pt+ph-bh-5}" text-anchor="middle">${x.n}</text>`;
    const words=x.label.split(' ');
    s+=`<text class="ax" x="${bx+w/2}" y="${H-pb+16}" text-anchor="middle">${esc(words.slice(0,Math.ceil(words.length/2)).join(' '))}</text>`;
    if(words.length>1)s+=`<text class="ax" x="${bx+w/2}" y="${H-pb+30}" text-anchor="middle">${esc(words.slice(Math.ceil(words.length/2)).join(' '))}</text>`;
  });
  let hits='';h.forEach((x,i)=>hits+=`<rect data-i="${i}" x="${pl+i*bw}" y="${pt}" width="${bw}" height="${ph+pb-8}" fill="transparent"/>`);
  el.innerHTML=`<svg width="${W}" height="${H}" role="img" aria-label="Гистограмма сроков закрытия дивидендных гэпов">${G.defs()}${s}${hits}</svg>`;
  bindTip(el,i=>`<b>${esc(h[i].label)}</b>`+tipRow(col(h[i]),'событий',String(h[i].n)));
}
function dlGapsTable(gs){
  if(!gs.length)return'<div class="empty" style="padding:24px">Нет прошлых отсечек, покрытых историей котировок.</div>';
  const st=g=>g.closed?`<span class="pos">закрыт за ${g.days===0?'тот же день':g.days+' дн.'}</span>`:g.n_after>=90?`<span class="neg" title="Максимальное восстановление цены: ${dlN(g.recovery_pct,0)} % гэпа">не закрыт · вернулось ${dlN(g.recovery_pct,0)} %</span>`:`<span class="mu" title="Прошло ${g.n_after} торговых дней — рано судить">ещё открыт · ${g.n_after} дн.</span>`;
  return`<div class="tbl"><table><thead><tr><th class="l">Фиксация</th><th>Дивиденд</th><th title="Закрытие последнего дня покупки">Цена до</th><th title="Цена открытия следующего торгового дня">Цена после</th><th>Гэп</th><th>Гэп, %</th><th title="Гэп / дивиденд">Гэп к дивиденду</th><th class="l">Закрытие гэпа</th></tr></thead><tbody>`+
    gs.map(g=>`<tr><td class="l num">${ddm(g.record)}<br><small class="mu">посл. покупка ${ddm(g.last_buy)}</small></td><td class="num">${dlRub(g.div)}<br><small class="mu">${dlN(g.div_pct,1)} % к цене</small></td>
      <td class="num">${dlN(g.p_pre)}</td><td class="num">${dlN(g.p_post)}</td><td class="num ${g.gap>0?'neg':'pos'}">${dlSg(-g.gap)}</td><td class="num ${g.gap>0?'neg':'pos'}">${g.gap_pct>0?'−':'+'}${dlN(Math.abs(g.gap_pct),1)} %</td>
      <td class="num">${dlN(g.k*100,0)} %</td><td class="l">${st(g)}</td></tr>`).join('')+`</tbody></table></div>`;
}
function dlSafetyCard(sf){
  if(!sf)return'';
  const z=dlZoneCls(sf.zone);
  const head=sf.score!=null?`<div class="dl-big ${z}">${sf.score}<small>из 100 · ${esc(sf.label)}</small></div><div class="dl-bar"><i style="left:${sf.score}%" class="${z}"></i></div>`
    :`<div class="empty" style="padding:14px">${esc(sf.note||'Недостаточно данных для оценки')}</div>`;
  const comps=(sf.components||[]).map(c=>`<div class="dl-comp${c.available?'':' off'}"><div class="dl-ch"><b>${esc(c.name)}</b><span class="num">${c.available?c.points+' / '+c.weight:'нет данных'}</span></div>
    <div class="dl-cb"><i style="width:${c.available?c.points/c.weight*100:0}%"></i></div><small class="mu">${esc(c.note||'')}</small></div>`).join('');
  return`<div class="card"><h2>Надёжность дивиденда<span class="sp">оценка 0–100 по доступной отчётности</span></h2>${head}
    ${(sf.flags||[]).map(f=>`<div class="msg err" style="margin:10px 0">${esc(f.charAt(0).toUpperCase()+f.slice(1))}</div>`).join('')}
    <div class="dl-comps">${comps}</div>
    <p class="note" style="margin-top:10px">80 и выше — «надёжно», 50–79 — «умеренно», ниже 50 — «высокий риск». Компоненты без данных не учитываются, баллы пересчитываются на доступный вес. Для банков показатель «чистый долг / EBITDA» не применяется. Оценка — по отчётности МСФО и истории выплат, это не прогноз.</p></div>`;
}
function dlPayoffCard(d){
  const p=d.payoff,st=d.stats;
  if(!p)return`<div class="card"><h2>Удержание или продажа накануне</h2><div class="empty" style="padding:24px">Нет известного дивиденда или цены для расчёта.</div></div>`;
  const best=p.diff>0;
  const kTxt=p.k_fallback?'Истории гэпов нет, принято соотношение гэпа к дивиденду 100 %':`По истории гэп в среднем ${dlN(p.k_used*100,0)} % от дивиденда (медиана)`;
  const cnt=p.qty?` На вашу позицию (${dlN(p.qty,0)} шт.): удержание ${dlSg(p.hold*p.qty,0)}, продажа и обратная покупка ${dlSg(p.sell_rebuy*p.qty,0)}.`:'';
  return`<div class="card"><h2>Удержание или продажа накануне<span class="sp">${p.upcoming?'ближайший дивиденд':'последний дивиденд'}: ${dlRub(p.div)}, фиксация ${ddm(p.record)}</span></h2>
    <p class="dl-lead">${kTxt}, то есть ожидаемый гэп около ${dlRub(p.gap)} (${dlN(p.gap_pct,1)} % от цены ${dlN(p.p_pre)} ₽). При продаже накануне и обратной покупке на открытии результат на акцию был бы ${dlSg(p.sell_rebuy)} против ${dlSg(p.hold)} при удержании${p.held?'':' (себестоимость не известна — налог с продажи не учтён)'}.</p>
    <div class="g g3" style="margin:12px 0">${kpi('Удержание, на акцию',dlSg(p.hold),`дивиденд после налога ${dlN(p.tax_rate*100,0)} % минус гэп`,cls(p.hold))}
      ${kpi('Продажа накануне и покупка обратно, на акцию',dlSg(p.sell_rebuy),`комиссии ${dlRub(p.fees)}${p.cost_known?`, налог с продажи ${dlRub(p.tax_sale)}`:''}`,cls(p.sell_rebuy))}
      ${kpi('Разница',dlSg(p.diff),best?'сценарий продажи выше на эту сумму':'сценарий удержания выше на эту сумму')}</div>
    <p class="note">${cnt} Допущения: обратная покупка — на 10 % гэпа выше цены открытия после отсечки; комиссия брокера ${dlN(p.fee_rate*100,2)} % с каждой сделки; налог на прибыль от продажи считается от ${p.cost_known?'средней цены покупки по вашим лотам':'неизвестной себестоимости — не учтён'}. Это оценка по прошлым данным, а не инвестиционная рекомендация: цена в день отсечки может вести себя иначе. Продажа сбрасывает срок владения для льготы ЛДВ (3 года), а повторная покупка начинает его заново.</p></div>`;
}
function dlStockTab(){
  const D=S.dl;
  if(!D.secid)return dlStockHome();
  if(!D.data&&!D.loading&&!D.err)dlLoadStock(false);
  if(D.loading&&!D.data)return`<div class="card">${waitBox('Загружаю свечи за 6 лет, дивиденды и отчётность…')}</div>`;
  if(D.err)return`<div class="msg err">${esc(D.err)} <button class="btn ghost dl-r">Повторить</button></div>`;
  const d=D.data||{},st=d.stats||{count:0};
  const err=d.error?`<div class="msg info" style="margin-bottom:12px">${esc(d.error)}</div>`:'';
  const src=d.div_source==='tinvest'||d.div_source==='tinvest-server'?'T-Invest':'нет источника';
  const nx=d.next;
  const hdr=`<div class="card dl-hd"><div><h2 style="margin:0">${esc(d.name||d.secid)} <span class="mu">${esc(d.secid)}</span></h2><small class="mu">${esc(d.sector||'')}${d.price?' · цена '+dlRub(d.price):''}${d.candles_to?' · свечи до '+ddm(d.candles_to):''} · дивиденды: ${esc(src)}</small></div>
    ${nx?`<div class="dl-nx"><small class="mu">${nx.upcoming?'Ближайший дивиденд':'Последний дивиденд'}</small><b>${dlRub(nx.value)}</b> <small class="mu">фиксация ${ddm(nx.record)}${nx.last_buy?', покупка до '+(nx.last_buy_est?'≈ ':'')+ddm(nx.last_buy):''}</small></div>`:''}</div>`;
  if(!st.count)return hdr+err+`<div class="card"><div class="empty" style="padding:30px">Не удалось найти прошлые рублёвые дивиденды, покрытые историей котировок. Возможно, бумага не платит дивиденды или данные временно недоступны.</div></div>`+(d.safety?dlSafetyCard(d.safety):'');
  chart('c-dl-h',dlHistChart,{hist:st.hist});
  return hdr+err+dlStats(st)+`<div class="g c-2-1 dl-mid" style="margin-top:16px"><div class="card"><h2>За сколько дней закрывался гэп<span class="sp">торговых дней от дня отсечки</span></h2><div id="c-dl-h" class="chart"></div></div>${dlSafetyCard(d.safety)}</div>
    ${dlPayoffCard(d)}
    <div class="card" style="margin-top:16px"><h2>История гэпов<span class="sp">${st.count} ${dlEv(st.count,'событие','события','событий')}</span></h2>${dlGapsTable(d.gaps||[])}</div>
    <p class="note">Гэп — разница между закрытием последнего дня покупки (за один торговый день до даты фиксации) и открытием следующего дня. Гэп считается закрытым, когда максимум дня достигает цены «до». Не закрытые события разделены на «не закрыт» (прошло 90+ торговых дней) и «ещё открыт» (слишком свежие). ${NIR_NOTE}</p>`;
}
function pDgap(){
  const D=S.dl;
  const tabs=`<div class="row" style="gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:16px"><div class="seg" id="dl-tabs"><button data-t="port" class="${D.tab==='port'?'on':''}">Мой портфель</button><button data-t="stock" class="${D.tab==='stock'?'on':''}">Анализ акции</button></div>${D.tab==='port'?'<button class="btn ghost dl-r" style="margin-left:auto">Обновить</button>':''}</div>`;
  return tabs+(D.tab==='port'?dlPortTab():dlSearchBox()+dlStockTab());
}
function bindDgap(){
  const D=S.dl;
  const t=$('#dl-tabs');if(t)t.onclick=e=>{const b=e.target.closest('[data-t]');if(!b||b.dataset.t===D.tab)return;D.tab=b.dataset.t;render()};
  document.querySelectorAll('#view .dl-r').forEach(r=>r.onclick=()=>{
    if(D.tab==='port'){D.port=null;D.perr='';dlLoadPort(true)}else{D.data=null;D.err='';D.loading=false;dlLoadStock(true)}render()});
  const ts=$('#dl-to-stock');if(ts)ts.onclick=()=>{D.tab='stock';render()};
  document.querySelectorAll('#view [data-dl]').forEach(b=>b.onclick=()=>dlOpen(b.dataset.dl));
  const q=$('#dl-q'),res=$('#dl-res');
  if(q){
    const show=()=>{const l=stkSearch(q.value,8);res.innerHTML=q.value.trim()?l.map(r=>`<button data-dl="${esc(r.secid)}"><b>${esc(r.secid)}</b><span>${esc(r.shortname)}</span></button>`).join('')||'<div class="kp-e">Не найдено</div>':''};
    q.oninput=()=>stkEnsureList(show);
    q.onkeydown=e=>{if(e.key==='Enter'){const v=q.value.trim();const l=stkSearch(v,1);dlOpen(l.length?l[0].secid:v)}else if(e.key==='Escape'){q.value='';res.innerHTML=''}};
    res.onclick=e=>{const b=e.target.closest('[data-dl]');if(b)dlOpen(b.dataset.dl)};
    stkEnsureList();
  }
  [['dl-tax','tax'],['dl-fee','fee']].forEach(([id,k])=>{const e=$('#'+id);if(e)e.onchange=()=>{D[k]=e.value;D.data=null;D.port=null;D.loading=false;if(D.secid)dlLoadStock(true);render()}});
}
regPage('dgap',{title:'Дивидендные гэпы',group:'Акции',icon:'<path d="M3 17l5-6 4 3 4-8 5 6"/><path d="M3 21h18"/><path d="M12 14v7" stroke-dasharray="2 2"/>',render:pDgap,bind:bindDgap});
if(typeof renderNav==='function')try{renderNav()}catch(e){}
