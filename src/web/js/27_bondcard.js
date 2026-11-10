// ── карточка облигации (боковая панель): клик по любому элементу с data-isin ──
const BC={stack:[],tok:0,all:false};
const BC_SEC={financial:'Финансы',industrials:'Промышленность',materials:'Сырьё',energy:'Энергетика',consumer:'Потребительский',government:'Государственные',real_estate:'Недвижимость',telecom:'Телеком',municipal:'Муниципальные',utilities:'Коммунальные',it:'IT',health_care:'Здравоохранение',other:'Прочее'};
const BC_EV={coupon:'Купон',amort:'Амортизация',offer:'Оферта',redemption:'Погашение'};
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
  return`<div class="bc-bar">${back}<span class="sp"></span><button class="btn ghost" id="bc-x" aria-label="Закрыть">✕ Закрыть</button></div>`;
}
function bcBind(dr){
  const x=dr.querySelector('#bc-x');if(x)x.onclick=closeBond;
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
  dr.innerHTML=bcBar()+bcBody(c);bcBind(dr);bcCharts(dr,c);
  const mr=dr.querySelector('#bc-more');
  if(mr)mr.onclick=()=>{BC.all=true;dr.innerHTML=bcBar()+bcBody(c);bcBind(dr);bcCharts(dr,c);BC.all=false};
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
  add('Оферта',m&&m.offer?ddm(m.offer):'');
  add('Размещена',d.ISSUEDATE?ddm(d.ISSUEDATE):'');
  add('Объём выпуска',d.ISSUESIZE?short(+d.ISSUESIZE)+' шт.':'');
  add('Номинал',d.FACEVALUE?bcN(+d.FACEVALUE,2)+' '+esc(cur.toUpperCase())+(d.INITIALFACEVALUE&&d.INITIALFACEVALUE!==d.FACEVALUE?` (первоначально ${esc(d.INITIALFACEVALUE)})`:''):'');
  add('Уровень листинга',m&&m.level?esc(m.level):esc(d.LISTLEVEL||''));
  add('Уровень риска (T-Invest)',ci.risk?esc(BC_RISK[ci.risk]||ci.risk):'');
  add('Для квалифицированных',d.ISQUALIFIEDINVESTORS==='1'?'да':d.ISQUALIFIEDINVESTORS==='0'?'нет':'');
  add('Дефолт',d.HASDEFAULT==='1'?'<b class="neg">допущен</b>':d.HASTECHNICALDEFAULT==='1'?'<b class="neg">технический</b>':(d.HASDEFAULT==='0'?'нет':''));
  add('Госномер выпуска',esc(d.REGNUMBER||''));
  h+=`<div class="card bc-sec"><h2>Ключевые параметры</h2><div class="bc-par">${rows.join('')||'<span class="mu">Нет данных</span>'}</div></div>`;
  // денежный поток
  const fl=c.flows||[],lim=BC.all?fl.length:12;
  h+=`<div class="card bc-sec"><h2>Денежный поток<span class="sp">ближайшие выплаты на 1 облигацию</span></h2>`;
  if(fl.length){
    h+=`<div class="tbl"><table><thead><tr><th>Дата</th><th>Событие</th><th>Сумма</th><th>% номинала / ставка</th></tr></thead><tbody>`
      +fl.slice(0,lim).map(e=>`<tr><td>${ddm(e.d)}</td><td>${BC_EV[e.t]||esc(e.t)}</td><td class="num">${e.amt==null?'<span class="mu">по ставке</span>':M(e.amt,cur)}</td><td class="num">${e.pct==null?'—':bcN(e.pct,2)+' %'}</td></tr>`).join('')
      +`</tbody></table></div>`;
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
function bcCharts(dr,c){
  const hs=c.history;if(!hs||!hs.d||hs.d.length<2)return;
  const labels=hs.d.map(ddm),p=document.getElementById('bc-ch-p'),y=document.getElementById('bc-ch-y');
  {
    try{
      if(p)line(p,{h:190,labels,zero:false,fa:v=>bcN(v,1),ft:v=>bcN(v,2)+' %',series:[{n:'Цена',c:'#3987e5',v:hs.p,w:2}]});
      if(y)line(y,{h:190,labels,zero:false,fa:v=>bcN(v,1),ft:v=>bcN(v,2)+' %',series:[{n:'Доходность',c:'#c98500',v:hs.y,w:2}]});
    }catch(e){}
  }
}
