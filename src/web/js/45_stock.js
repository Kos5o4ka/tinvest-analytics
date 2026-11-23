/* ── Акция: карточка с графиком, техническим анализом, мультипликаторами и дивидендами ──
   Регистрация экранов stk и sst (меню, Pro, иконки) — здесь, чтобы не трогать общие списки. openStock(secid) — вход для других экранов. */
IC.stk='<path d="M7 4v3M7 17v3M17 8v3M17 18v2"/><rect x="5" y="7" width="4" height="10" rx="1"/><rect x="15" y="11" width="4" height="7" rx="1"/>';
IC.sst='<path d="M3 5h18l-7 8v6l-4-2v-4z"/>';
PAGES.push(['stk','Акция'],['sst','Скринер акций']);
NAV_GROUPS.splice(Math.max(0,NAV_GROUPS.findIndex(g=>g[0]==='Рынок')+1),0,['Акции',['stk','sst']]);
PRO_PAGES.push('sst');
document.addEventListener('click',e=>{
  const t=e.target.closest&&e.target.closest('.it[data-stk],tr[data-stk]');   /* строки дашборда; кнопки и таблицы акций вешают свои обработчики */
  if(t&&t.dataset.stk&&!e.target.closest('a,input,select,button,textarea'))openStock(t.dataset.stk);
});
PRO_FEATURES.sst={t:'Скринер акций',ic:'sst',b:['Акции Мосбиржи с P/E, P/B, EV/EBITDA, дивидендной доходностью и ростом','Готовые подборки: дешёвые по P/E, высокие дивиденды, быстрый рост','Фильтры по сектору, капитализации и показателям','Переход в карточку акции в один клик'],pv:'table'};

S.stk={secid:null,tf:'D',card:null,cardTf:null,err:null,loading:false,ind:{s50:true,s200:true,bb:false,lv:true}};
S.stkList=null;
const stkN=(v,d=2)=>v==null||isNaN(v)?'—':(+v).toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
const stkPrice=v=>v==null?'—':stkN(v,v>=100?2:v>=1?3:4);
const stkPc=(v,d=2)=>v==null||isNaN(v)?'<span class="mu">—</span>':`<span class="${v>0?'pos':v<0?'neg':''}">${v>0?'+':v<0?'−':''}${stkN(Math.abs(v),d)} %</span>`;
const stkCap=v=>{if(v==null||!isFinite(v))return'—';const a=Math.abs(v);return a>=1e12?stkN(v/1e12,2)+' трлн ₽':a>=1e9?stkN(v/1e9,1)+' млрд ₽':a>=1e6?stkN(v/1e6,1)+' млн ₽':stkN(v,0)+' ₽'};
function stkEnsureList(cb){
  if(S.stkList){cb&&cb();return}
  if(S._stkListL){if(cb)(S._stkListCb=S._stkListCb||[]).push(cb);return}
  S._stkListL=1;if(cb)S._stkListCb=[cb];
  api('/api/stocks').then(j=>{S.stkList=(j.rows||[]).slice().sort((a,b)=>(b.value_today||0)-(a.value_today||0))}).catch(e=>{S.stkList=[]})
   .then(()=>{S._stkListL=0;(S._stkListCb||[]).forEach(f=>{try{f()}catch(e){}});S._stkListCb=[]});
}
/* поиск по тикеру и названию: для строки поиска экрана и палитры Ctrl+K */
function stkSearch(q,n){
  const l=S.stkList||[];q=kpNorm(q).trim();if(!q)return l.slice(0,n||8);
  const out=[];
  for(const r of l){const sc=Math.max(r.secid.toLowerCase()===q?9:kpScore(r.secid,q),kpScore(r.shortname,q),kpScore(r.name,q)*.8);if(sc)out.push([sc,r])}
  return out.sort((a,b)=>b[0]-a[0]).slice(0,n||8).map(x=>x[1]);
}
function openStock(secid,opts){
  secid=String(secid||'').trim().toUpperCase();if(!secid)return;
  if(/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(secid)){         /* ISIN (так приходят бумаги из отчётов брокера) -> тикер Мосбиржи по списку акций */
    if(!S.stkList){stkEnsureList(()=>{const r=(S.stkList||[]).find(x=>x.isin===secid);openStock(r?r.secid:secid+'#',opts)});return}
    const r=S.stkList.find(x=>x.isin===secid);if(r)secid=r.secid;
  }
  secid=secid.replace(/#$/,'');
  const st=S.stk;if(st.secid!==secid){st.secid=secid;st.card=null;st.err=null;st.cardTf=null}
  if(S.page==='stk'||(opts&&opts.page)){skClose();if(S.page==='stk')render();else go('stk');return}
  skOpen();
}
function loadStk(force){
  const st=S.stk,sec=st.secid,tf=st.tf;if(!sec||(st.loading&&!force))return;st.loading=true;st.err=null;
  api('/api/stock?'+new URLSearchParams({secid:sec,tf})+(force?'&force=1':'')).then(j=>{
    st.loading=false;if(st.secid!==sec||st.tf!==tf){loadStk();return}
    st.card=j;st.cardTf=tf;if(S.page==='stk')renderSoon();skRender();
  }).catch(e=>{st.loading=false;if(st.secid!==sec)return;st.err=e.message;if(S.page==='stk')renderSoon();skRender()});
}
function stkSearchBox(){
  const tfs=[['D','День'],['W','Неделя'],['H','Час']];
  return`<div class="card stk-top"><div class="stk-sw"><input class="in" id="stk-q" placeholder="Тикер или название: SBER, Сбербанк…" autocomplete="off" spellcheck="false" value=""><div id="stk-res" class="stk-res"></div></div>
    ${S.stk.secid?`<div class="seg" id="stk-tf" title="Таймфрейм свечей">${tfs.map(([k,t])=>`<button data-t="${k}" class="${S.stk.tf===k?'on':''}">${t}</button>`).join('')}</div>`:''}</div>`;
}
function stkHome(){
  const l=(S.stkList||[]).slice(0,16);
  if(!S.stkList)stkEnsureList(()=>{if(S.page==='stk'&&!S.stk.secid)renderSoon()});
  return`<div class="card"><h2>Самые торгуемые акции<span class="sp">по обороту за день</span></h2>${S.stkList?`<div class="stk-chips">${l.map(r=>`<button class="btn ghost" data-stk="${esc(r.secid)}"><b>${esc(r.secid)}</b> <span class="mu">${esc(r.shortname)}</span> ${stkPc(r.chg_d,1)}</button>`).join('')}</div>`:waitBox('Загружаю список акций…')}</div>
    <p class="note">Введите тикер или название в поле выше (или нажмите Ctrl+K) — откроется карточка с графиком, техническим анализом, мультипликаторами и дивидендами.</p>`;
}
function stkLabel(tf){return tf==='H'?(t=>{const[d,h]=t.split(' ');return d.slice(8)+'.'+d.slice(5,7)+' '+(h||'')}):ddm}
/* вспомогательные панели RSI и MACD под свечным графиком (та же сетка по X, что у candles) */
function stkSub(el,o){
  const W=el.clientWidth,H=o.h||110,pl=58,pr=10,pt=8,pb=18,n=o.labels.length;
  if(n<2||W<80)return emptyChart(el,H,'');
  const ph=H-pt-pb,pw=W-pl-pr,gw=pw/n,X=i=>pl+(i+.5)/n*pw;
  let lo,hi,s='';
  if(o.kind==='rsi'){lo=0;hi=100}
  else{let mn=0,mx=0;[o.macd,o.sig,o.hist].forEach(a=>a.forEach(v=>{if(v!=null){mn=Math.min(mn,v);mx=Math.max(mx,v)}}));const p=Math.max(Math.abs(mn),Math.abs(mx),1e-9)*1.1;lo=-p;hi=p}
  const Y=v=>pt+ph-(v-lo)/(hi-lo)*ph;
  const ticks=o.kind==='rsi'?[30,50,70]:[lo/1.1,0,hi/1.1];
  ticks.forEach(v=>{s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${Y(v)}" y2="${Y(v)}"${o.kind==='rsi'&&v!==50?' stroke-dasharray="4 4"':''}/><text class="ax num" x="${pl-8}" y="${Y(v)+4}" text-anchor="end">${o.kind==='rsi'?v:stkN(v,Math.abs(v)<1?3:2)}</text>`});
  const poly=(a,c,w)=>{const p=[];a.forEach((v,i)=>{if(v!=null)p.push(X(i).toFixed(1)+','+Y(v).toFixed(1))});return p.length>1?`<polyline points="${p.join(' ')}" fill="none" stroke="${c}" stroke-width="${w||1.5}" stroke-linejoin="round"/>`:''};
  if(o.kind==='rsi')s+=poly(o.rsi,'var(--s7)',1.6);
  else{const bw=Math.max(1,Math.min(10,gw*.6));o.hist.forEach((v,i)=>{if(v==null)return;const y0=Y(0),y1=Y(v);s+=`<rect x="${X(i)-bw/2}" y="${Math.min(y0,y1)}" width="${bw}" height="${Math.max(1,Math.abs(y1-y0))}" fill="${v>=0?'var(--pos)':'var(--neg)'}" opacity=".55"/>`});
    s+=poly(o.macd,'var(--s1)',1.5)+poly(o.sig,'var(--s8)',1.3)}
  s+=`<text class="ax" x="${pl+4}" y="${pt+9}" style="fill:var(--tx2)">${o.kind==='rsi'?'RSI (14)':'MACD (12, 26, 9)'}</text>`;
  let hits='';for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${pl+gw*i}" y="${pt}" width="${gw}" height="${ph}" fill="transparent"/>`;
  el.innerHTML=`<svg width="${W}" height="${H}">${s}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{hv.innerHTML=i<0?'':`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph}" stroke="var(--line2)" stroke-dasharray="3 3"/>`};
  bindTip(el,i=>`<b>${esc(o.labels[i])}</b>`+(o.kind==='rsi'?tipRow('var(--s7)','RSI',stkN(o.rsi[i],1)):tipRow('var(--s1)','MACD',stkN(o.macd[i],3))+tipRow('var(--s8)','Сигнальная',stkN(o.sig[i],3))+tipRow('var(--mu)','Гистограмма',stkN(o.hist[i],3))));
}
function stkTaCard(c){
  const ta=c.ta||{},cls={'покупать':'pos','продавать':'neg'}[ta.signal]||'mu';
  if(!ta.signal)return`<div class="card"><h2>Технический анализ</h2><div class="empty" style="padding:24px">${esc(ta.note||'Мало истории для расчёта индикаторов.')}</div></div>`;
  const ic=v=>v>0?'<span class="pos">▲</span>':v<0?'<span class="neg">▼</span>':'<span class="mu">●</span>';
  const lv=c.levels||{support:[],resistance:[]},L=(a,k)=>a.length?a.map(x=>`<span class="tag ${k}" title="касаний: ${x.touches}">${stkPrice(x.price)}</span>`).join(' '):'<span class="mu">—</span>';
  return`<div class="card"><h2>Технический анализ<span class="sp">сводка по ${ta.votes.length} индикаторам</span></h2>
    <div class="stk-verdict"><span class="stk-sig ${cls}">${esc(ta.signal)}</span><span class="mu">баланс голосов: ${ta.score>0?'+':''}${ta.score}</span></div>
    <div class="stk-votes">${ta.votes.map(v=>`<div>${ic(v.vote)}<b>${esc(v.name)}</b><span class="mu">${esc(v.text)}</span></div>`).join('')}</div>
    <div class="stk-lv"><div><span class="mu">Сопротивление</span> ${L(lv.resistance,'neg')}</div><div><span class="mu">Поддержка</span> ${L(lv.support,'pos')}</div></div>
    <p class="note">Голосование: цена против SMA50 и SMA200, RSI (&lt; 30 — покупать, &gt; 70 — продавать), пересечение MACD, выход за полосы Боллинджера. Сумма ≥ +2 — «покупать», ≤ −2 — «продавать». Это формальный расчёт, а не рекомендация.</p></div>`;
}
function stkMulCard(c){
  const m=c.multiples||{},x=(v,d=2,u='')=>v==null?'<span class="mu">—</span>':stkN(v,d)+u;
  const src=m.source==='tinvest-server'?'T-Invest через сервер (TTM)':m.source==='tinvest'?'T-Invest (TTM)':'МСФО, smart-lab'+(m.period?' ('+(m.period==='LTM'?'последние 12 мес.':m.period+' год')+')':'');
  const rows=[['P/E',x(m.pe,1),'цена к прибыли'],['P/B',x(m.pb),'цена к балансовой стоимости'],['EV/EBITDA',x(m.ev_ebitda,1),'стоимость бизнеса к EBITDA'],['ROE',x(m.roe,1,' %'),'рентабельность капитала'],
    ['Чистый долг / EBITDA',x(m.nd_ebitda,2),''],['Рост выручки',m.rev_growth==null?'<span class="mu">—</span>':stkPc(m.rev_growth,1),'за год'],['Рост прибыли',m.ni_growth==null?'<span class="mu">—</span>':stkPc(m.ni_growth,1),'за год'],
    ['Дивидендная доходность',x(m.div_yield==null?(c.dividends||{}).yield_ttm:m.div_yield,2,' %'),'за последние 12 месяцев']];
  return`<div class="card"><h2>Мультипликаторы<span class="sp">${esc(src)}</span></h2><div class="tbl"><table><tbody>${rows.map(r=>`<tr><td class="l">${r[0]}${r[2]?`<br><small class="mu">${r[2]}</small>`:''}</td><td class="num"><b>${r[1]}</b></td></tr>`).join('')}</tbody></table></div>
    ${c.token||m.source==='tinvest-server'?'':'<p class="note">Без токена T-Invest мультипликаторы считаются по отчётности МСФО с smart-lab; дивиденды и даты отчётности могут быть недоступны.</p>'}</div>`;
}
function stkDivCard(c){
  const d=c.dividends||{items:[]};
  const body=d.items.map(r=>`<tr class="${r.future?'pnew':''}"><td class="l">${ddm(r.record)}${r.future?' <small class="pos">будущая</small>':''}</td><td class="num">${r.payment?ddm(r.payment):'—'}</td><td class="num"><b>${stkN(r.value,r.value<1?4:2)} ${r.cur==='RUB'?'₽':esc(r.cur)}</b></td><td class="num">${r.yield_pct==null?'—':stkN(r.yield_pct,2)+' %'}</td></tr>`).join('');
  return`<div class="card"><h2>Дивиденды<span class="sp">${d.yield_ttm!=null?'доходность за 12 мес.: '+stkN(d.yield_ttm,2)+' %':''}</span></h2>
    ${d.items.length?`<div class="tbl" style="max-height:340px"><table><thead><tr><th class="l">Закрытие реестра</th><th>Выплата</th><th>На акцию</th><th>Доходность к цене</th></tr></thead><tbody>${body}</tbody></table></div>`
      :`<div class="empty" style="padding:24px">Нет данных о дивидендах.${c.token?'':'<br><small class="mu">Мосбиржа не отдаёт историю бесплатно — подключите токен T-Invest.</small>'}</div>`}</div>`;
}
function stkRepCard(c){
  const r=c.report||{};let v;
  if(r.date){const dd=Math.ceil((new Date(r.date)-new Date(new Date().toISOString().slice(0,10)))/864e5);
    v=`<div class="v num" style="font-size:22px;font-weight:700">${ddm(r.date)}</div><div class="s mu">${dd>0?'через '+dd+' дн.':dd===0?'сегодня':''}${r.year?' · отчёт за '+(r.num?r.num+' кв. ':'')+r.year:''}</div>`}
  else v=`<div class="mu" style="padding:6px 0">${esc(r.note||'Дата неизвестна')}</div>`;
  return`<div class="card"><h2>Следующая отчётность</h2>${v}</div>`;
}
function pStk(){
  const head=stkSearchBox();
  return S.stk.secid?head+stkCardHtml('stk-'):head+stkHome();
}
/* Карточка акции без строки поиска. prefix даёт ids: 'stk-' на странице, 'skd-' в панели — они не пересекаются. */
function stkCardHtml(p){
  const st=S.stk,drw=p!=='stk-';
  if(st.err)return`<div class="msg err">${esc(st.err)} <button class="btn ghost" id="${p}r">Повторить</button></div>`;
  const c=st.card;
  if(!c||c.secid!==st.secid||st.cardTf!==st.tf){loadStk();return`<div class="card">${waitBox('Загружаю '+esc(st.secid)+'…')}</div>`}
  const q=c.quote,cs=c.candles,sr=c.series||{},ind=st.ind,lab=stkLabel(st.tf);
  const lines=[];
  if(ind.s50)lines.push({v:sr.sma50||[],c:'#f0b429',n:'SMA 50',w:1.5});
  if(ind.s200)lines.push({v:sr.sma200||[],c:'#7a8cff',n:'SMA 200',w:1.5});
  const lv=[];if(ind.lv&&c.levels)c.levels.resistance.forEach(x=>lv.push({p:x.price,kind:'r'})),c.levels.support.forEach(x=>lv.push({p:x.price,kind:'s'}));
  chart('c-'+p+'chart',(el,o)=>candles(el,cs,o),{h:380,lines,band:ind.bb?{up:sr.bb_up||[],low:sr.bb_low||[],c:'#7a8cff'}:null,levels:lv,labelOf:lab,fmt:stkPrice});
  chart('c-'+p+'rsi',stkSub,{kind:'rsi',h:100,labels:cs.map(x=>lab(x.t)),rsi:sr.rsi||[]});
  chart('c-'+p+'macd',stkSub,{kind:'macd',h:120,labels:cs.map(x=>lab(x.t)),macd:sr.macd||[],sig:sr.macd_signal||[],hist:sr.macd_hist||[]});
  const tg=(id,t,on)=>`<label class="sw"><input type="checkbox" id="${p}${id}" ${on?'checked':''}><i></i><div><b>${t}</b></div></label>`;
  const tfs=[['D','День'],['W','Неделя'],['H','Час']];
  const tfSeg=drw?`<div class="seg" id="${p}tf" title="Таймфрейм свечей">${tfs.map(([k,t])=>`<button data-t="${k}" class="${st.tf===k?'on':''}">${t}</button>`).join('')}</div>`:'';
  return`<div class="card stk-hd"><div><h1 class="stk-nm">${esc(q.shortname)} <span class="mu">${esc(q.secid)}</span></h1><div class="note">${esc(q.name)} · ${esc(q.sector)} · ${esc(q.isin)}</div></div>
      <div class="stk-px"><span class="num">${stkPrice(q.price)} ₽</span> <span class="num">${stkPc(q.chg_d)}</span></div></div>
    <div class="g g4">${kpi('За неделю',stkPc(q.chg_w,1),'5 торговых дней')}${kpi('За месяц',stkPc(q.chg_m,1),'21 торговый день')}${kpi('Капитализация',stkCap(q.cap),'лот: '+q.lot+' шт.')}${kpi('Оборот за день',stkCap(q.value_today),'Мосбиржа, TQBR')}</div>
    <div class="card" style="margin-top:16px"><div class="row" style="margin-bottom:8px">${tfSeg}${tg('s50','SMA 50',ind.s50)}${tg('s200','SMA 200',ind.s200)}${tg('bb','Боллинджер',ind.bb)}${tg('lv','Уровни',ind.lv)}
        <button class="btn ghost" id="${p}r" style="margin-left:auto">Обновить</button></div>
      <div id="c-${p}chart" class="chart"></div><div id="c-${p}rsi" class="chart"></div><div id="c-${p}macd" class="chart"></div></div>
    <div class="g g2" style="margin-top:16px">${stkTaCard(c)}${stkMulCard(c)}</div>
    <div class="g c-2-1" style="margin-top:16px">${stkDivCard(c)}${stkRepCard(c)}</div>
    <p class="note">Котировки — Московская биржа (ISS, с задержкой). Индикаторы считаются по ${esc(({D:'дневным',W:'недельным',H:'часовым'})[st.tf])} свечам. ${NIR_NOTE}</p>`;
}
function bindStk(){
  const st=S.stk,q=$('#stk-q'),res=$('#stk-res');
  const show=()=>{const l=stkSearch(q.value,8);res.innerHTML=q.value.trim()?l.map(r=>`<button data-stk="${esc(r.secid)}"><b>${esc(r.secid)}</b><span>${esc(r.shortname)}</span>${stkPc(r.chg_d,1)}</button>`).join('')||'<div class="kp-e">Не найдено</div>':''};
  q.oninput=()=>stkEnsureList(show);
  q.onkeydown=e=>{if(e.key==='Enter'){const v=q.value.trim();const l=stkSearch(v,1);openStock(l.length?l[0].secid:v)}else if(e.key==='Escape'){q.value='';res.innerHTML=''}};
  stkEnsureList();
  res.onclick=e=>{const b=e.target.closest('[data-stk]');if(b)openStock(b.dataset.stk)};
  document.querySelectorAll('#view [data-stk]').forEach(b=>b.onclick=()=>openStock(b.dataset.stk));
  bindStkCard(document,'stk-');
}
/* обработчики карточки: таймфрейм, «Обновить», переключатели индикаторов; перерисовывается страница или панель по префиксу */
function bindStkCard(root,p){
  const st=S.stk,rr=p==='stk-'?render:skRender,g=id=>root.querySelector('#'+p+id);
  const tf=g('tf');if(tf)tf.onclick=e=>{const b=e.target.closest('[data-t]');if(!b||b.dataset.t===st.tf)return;st.tf=b.dataset.t;st.card=null;rr()};
  const r=g('r');if(r)r.onclick=()=>{st.err=null;st.card=null;st.loading=false;loadStk(true);rr()};
  ['s50','s200','bb','lv'].forEach(k=>{const e=g(k);if(e)e.onchange=()=>{st.ind[k]=e.checked;rr()}});
}
/* ── панель «Акция» поверх текущего экрана (как карточка облигации) ── */
const SK={charts:[]};
function skClose(){
  const o=document.getElementById('sk-ov');if(!o)return;
  ovLeave(o);document.body.classList.remove('sk-open');SK.charts=[];hideTip();
}
function skOpen(){
  let o=document.getElementById('sk-ov');
  if(!o){
    o=document.createElement('div');o.id='sk-ov';
    o.innerHTML='<div class="sk-dr" id="sk-dr" role="dialog" aria-modal="true" aria-label="Карточка акции"><div class="sk-bar" id="sk-bar"></div><div class="sk-body" id="sk-body"></div></div>';
    o.addEventListener('mousedown',ev=>{if(ev.target===o)skClose()});
    document.body.appendChild(o);document.body.classList.add('sk-open');
  }
  const b=document.getElementById('sk-body');if(b)b.scrollTop=0;
  skRender();
}
function skRender(){
  const o=document.getElementById('sk-ov');if(!o)return;
  const st=S.stk,bar=o.querySelector('#sk-bar'),body=o.querySelector('#sk-body'),c=st.card,q=c&&c.secid===st.secid?c.quote:null;
  const n0=S.charts.length,html=stkCardHtml('skd-');
  SK.charts=S.charts.splice(n0);   /* графики панели держим отдельно: renderNow страницы обнуляет S.charts */
  const sc=body.scrollTop;
  bar.innerHTML=`<div class="sk-t"><b>${esc(q?q.shortname:st.secid)}</b> <span class="mu">${esc(st.secid)}</span></div><span class="sp"></span>
    <button class="btn ghost" id="sk-page">Открыть страницей</button>${typeof dlOpen==='function'?'<button class="btn ghost" id="sk-dgap" title="Дивидендные гэпы и стратегии по этой акции">Дивидендные гэпы</button>':''}<button class="btn ghost" id="sk-x" aria-label="Закрыть">✕ Закрыть</button>`;
  body.innerHTML=html;
  bar.querySelector('#sk-x').onclick=skClose;
  bar.querySelector('#sk-page').onclick=()=>{const s=st.secid;skClose();openStock(s,{page:true})};
  const dg=bar.querySelector('#sk-dgap');if(dg)dg.onclick=()=>{const s=st.secid;skClose();dlOpen(s)};
  bindStkCard(body,'skd-');skMount();body.scrollTop=sc;
}
function skMount(){SK.charts.forEach(([id,fn,o])=>{const el=document.getElementById(id);if(el)try{fn(el,o)}catch(e){console.error(e);el.innerHTML='<div class="empty">Не удалось построить график</div>'}})}
addEventListener('resize',()=>{clearTimeout(SK._t);SK._t=setTimeout(()=>{if(document.getElementById('sk-ov'))skMount()},140)});
/* Esc: в capture-фазе, чтобы карточка облигации (поверх панели) закрывалась первой */
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('sk-ov')&&!document.getElementById('bc-ov')){e.preventDefault();skClose()}},true);
