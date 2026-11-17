/* ── Скринер облигаций ── */
const SCR_DEF={q:'',cur:'RUB',kind:'all',sector:'',rmin:'',rated:false,ymin:'',ymax:'60',tmax:'',turn:'',spmin:'',noOffer:false,toOffer:false,fl:'all',liq:''};
const SCR_PRESETS=[
  ['ofz3','ОФЗ ≤ 3 лет',{kind:'ofz',cur:'RUB',tmax:'3',fl:'fix',noOffer:false}],
  ['fl_aa','Флоатеры AA+',{cur:'RUB',fl:'float',rmin:'AA-',turn:'1'}],
  ['hy20','ВДО от 20%',{cur:'RUB',kind:'corp',ymin:'20',ymax:'60',turn:'1'}],
  ['fx','Валютные',{cur:'all',kind:'corp',fl:'all',q:''}]
];
S.scr=null;S.sf=Object.assign({},SCR_DEF);S.scrOpen=false;S.scrPreset='';S.ssort={k:'yield',d:-1};S.sn=150;
function loadScr(cb){
  if(S._scrLoading){if(cb)S._scrCbs.push(cb);return}
  S._scrLoading=true;S._scrCbs=cb?[cb]:[];
  api('/api/screener').then(j=>{
    const t=Date.now();
    j.rows.forEach(r=>{
      r.perp=!r.mat||!!r.perpetual;
      r.years=r.perp?null:(new Date(r.mat)-t)/315576e5;
      const yo=r.offer?(new Date(r.offer)-t)/315576e5:null;
      r.yoff=yo!=null&&yo>0&&(r.years==null||yo<r.years)?yo:null;
    });
    S.scr=j;S._scrLoading=false;
    (S._scrCbs||[]).forEach(f=>{try{f()}catch(e){}});S._scrCbs=[];
    if(S.page==='scr'||S.page==='map')renderSoon();
  }).catch(e=>{
    S.scr={error:e.message,rows:[]};S._scrLoading=false;S._scrCbs=[];
    if(S.page==='scr'||S.page==='map')renderSoon();
  });
}
function scrActiveCount(){
  const f=S.sf;let n=0;
  for(const[k,v]of Object.entries(SCR_DEF))if(k!=='q'&&f[k]!==v)n++;
  return n;
}
function scrRows(){
  const f=S.sf,q=f.q.trim().toLowerCase(),ri=f.rmin?RSC.indexOf(f.rmin):-1;
  const nv=x=>{const s=String(x??'').trim().replace(',','.');if(!s)return null;const n=parseFloat(s);return isNaN(n)?null:n};
  const ymin=nv(f.ymin),ymax=nv(f.ymax),tmax=nv(f.tmax),turn=nv(f.turn),spmin=nv(f.spmin);
  let rs=S.scr.rows.filter(r=>{
    if(S.scrPreset==='fx'&&r.cur==='RUB')return false;
    if(f.cur!=='all'&&r.cur!==f.cur)return false;
    if(f.kind!=='all'&&r.kind!==f.kind)return false;
    if(q&&!((r.name||'').toLowerCase().includes(q)||(r.isin||'').toLowerCase().includes(q)||(r.full||'').toLowerCase().includes(q)))return false;
    if(ri>=0&&!(r.rating&&RSC.indexOf(r.rating)<=ri))return false;
    if(f.sector&&r.sector!==f.sector)return false;
    if(f.rated&&!r.rating)return false;
    if(ymin!=null&&r.yield<ymin)return false;if(ymax!=null&&r.yield>ymax)return false;
    if(tmax!=null){const eff=f.toOffer&&r.yoff!=null?r.yoff:r.years;if(eff==null||eff>tmax)return false}     /* «считать до оферты»: ближайшее из оферты и погашения */
    if(f.fl==='fix'&&r.floating)return false;if(f.fl==='float'&&!r.floating)return false;
    if(turn!=null&&r.turn<turn*1e6)return false;
    if(spmin!=null&&!(r.spread!=null&&r.spread>=spmin))return false;
    if(f.noOffer&&r.offer)return false;
    if(f.liq&&!(r.liq==='L1'||(f.liq==='L2'&&r.liq==='L2')))return false;
    return r.perp||(r.years!=null&&r.years>0);
  });
  const{k,d}=S.ssort;
  rs.sort((a,b)=>{let x=a[k==='liq'?'turn':k],y=b[k==='liq'?'turn':k];if(k==='rating'){x=x?RSC.indexOf(x):null;y=y?RSC.indexOf(y):null;return -d*((x??99)-(y??99))}
    if(k==='years'){x=a.perp?999:x;y=b.perp?999:y}
    if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  return rs;
}
function drawScr(){
  const rs=scrRows(),n=Math.min(rs.length,S.sn),fl=S.scr.floor&&S.scr.floor.lqdt;
  const cols=[['_w','★','l'],['name','Выпуск','l'],['rating','Рейтинг','l'],['sector','Сектор','l'],['price','Цена, %'],['yield','Доходность'],['cy','CY, %'],['spread','Спред к КБД'],['coupon','Купон, %'],['floating','Тип'],['years','До погашения'],['macdur','MacDur, лет'],['liq','Ликвидность']];
  const {k,d}=S.ssort;
  $('#scr-head').innerHTML=cols.map(([kk,t,c])=>kk==='_w'?`<th class="wt-sth" title="Список наблюдения">${t}</th>`:`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  $('#scr-body').innerHTML=rs.slice(0,n).map(r=>`<tr${fl>0&&r.yield<fl?' class="scr-low" title="Доходность ниже, чем у фонда ликвидности"':''} data-isin="${esc(r.isin||r.id)}"><td class="wt-std">${watchStar(r.isin||r.id)}</td><td class="l"><b>${esc(r.name)}</b><br><small class="mu num">${isinTxt(r.isin||r.id)}${r.offer?' · оферта '+ddm(r.offer):''}</small></td>
    <td class="l">${r.rating?`<span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}" title="${esc(r.rt_agency||'')}${r.rt_approx?' (приблизительное совпадение названия)':''}">${r.rt_approx?'≈ ':''}${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td>
    <td class="l">${r.sector?esc(SECT[r.sector]||r.sector):'<span class="mu">—</span>'}</td>
    <td class="num">${f2(r.price)}</td><td class="num"><b>${pctp(r.yield,2)}</b></td><td class="num">${r.cy!=null?f2(r.cy):'—'}</td>
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread):'—'}</td>
    <td class="num">${r.coupon!=null?f2(r.coupon):'—'}</td><td class="l">${r.floating?'<span class="tag scr-fl-t" title="'+(r.fl_label&&r.fl_label!=='ФЛОАТЕР'?'Плавающий купон: '+esc(r.fl_label)+' (спред эмитента по последним купонам)':'Плавающий купон (привязан к ключевой ставке или RUONIA)')+'">'+esc(r.fl_label||'ФЛОАТЕР')+'</span>':'<span class="tag" title="Фиксированный купон">ФИКС</span>'}</td><td class="num">${r.perp?'<span class="tag">бессрочная</span>':`${ddm(r.mat)}<br><small class="mu">${(S.sf.toOffer&&r.yoff!=null?r.yoff:r.years).toFixed(1).replace('.',',')} г${S.sf.toOffer&&r.yoff!=null?' до оферты':''}</small>`}</td>
    <td class="num">${r.macdur!=null?r.macdur.toFixed(2).replace('.',','):'—'}</td><td class="l"><span class="tag liq liq-${r.liq||'L3'}" title="Ликвидность по обороту за день: L1 — верхние 20%, L2 — следующие 40%, L3 — остальные">${r.liq||'L3'}</span> <small class="mu num">${r.turn?short(r.turn):'—'}</small></td></tr>`).join('');
  $('#scr-cnt').textContent=`Найдено: ${rs.length}${rs.length>n?' · показано '+n:''}`;
  $('#scr-more').style.display=rs.length>n?'':'none';
  const fb=$('#scr-ftog');if(fb){const ac=scrActiveCount();fb.textContent=(S.scrOpen?'Скрыть фильтры':'Фильтры')+(ac?` (${ac})`:'')}
}
S.scrTab='scr';S.mvDir='down';S.mvSort={k:'chg',d:0};S.mv=null;
function scrTabs(){return`<div class="seg" id="scr-tabs" style="margin-bottom:12px"><button data-t="scr" class="${S.scrTab==='scr'?'on':''}">Скринер</button><button data-t="mv" class="${S.scrTab==='mv'?'on':''}">Лидеры</button></div>`}
function loadMv(){api('/api/movers?n=50').then(j=>{S.mv=j;if(S.page==='scr')renderSoon()}).catch(e=>{S.mv={error:e.message,down:[],up:[]};if(S.page==='scr')renderSoon()})}
function mvRows(){
  const d=S.mv,rs=(S.mvDir==='down'?d.down:d.up).slice(),{k}=S.mvSort,dir=S.mvSort.d||(S.mvDir==='down'?1:-1);
  rs.sort((a,b)=>{let x=a[k],y=b[k];if(k==='rating'){x=x?RSC.indexOf(x):99;y=y?RSC.indexOf(y):99}return dir*((x??-Infinity)-(y??-Infinity))});
  return rs;
}
function drawMv(){
  const d=S.mv,rs=mvRows(),cols=[['name','Инструмент','l'],['chg','За день, %'],['price','Цена, %'],['turnover','Оборот, ₽'],['trades','Сделок'],['rating','Рейтинг','l']],{k}=S.mvSort,dir=S.mvSort.d||(S.mvDir==='down'?1:-1);
  $('#mv-head').innerHTML=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(dir>0?'↑':'↓'):''}</span></th>`).join('');
  $('#mv-body').innerHTML=rs.map(r=>`<tr data-isin="${esc(r.isin)}"><td class="l"><b>${esc(r.name)}</b><br><small class="mu num">${isinTxt(r.isin)}</small></td><td class="num ${r.chg>0?'pos':'neg'}"><b>${r.chg>0?'+':''}${f2(r.chg)}</b></td><td class="num">${f2(r.price)}</td><td class="num">${r.turnover?short(r.turnover):'—'}</td><td class="num">${r.trades||'—'}</td>
    <td class="l">${r.rating?`<span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}">${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td></tr>`).join('');
}
function pMv(){
  if(!S.mv){loadMv();return`<div class="card">${waitBox('Загружаю лидеров роста и падения…')}</div>`}
  if(S.mv.error)return`<div class="msg err">${esc(S.mv.error)}</div>`;
  const d=S.mv;
  return`<div class="card"><h2>Лидеры ${S.mvDir==='down'?'падения':'роста'}<span class="sp">${d.n} из ${d.total}</span></h2>
    <div class="seg" id="mv-dir" style="margin-bottom:10px"><button data-d="down" class="${S.mvDir==='down'?'on':''}">Падение</button><button data-d="up" class="${S.mvDir==='up'?'on':''}">Рост</button></div>
    <div class="tbl" style="max-height:calc(100vh - 300px)"><table><thead><tr id="mv-head"></tr></thead><tbody id="mv-body"></tbody></table></div></div>
  <p class="note">Изменение цены облигации за торговый день по данным Мосбиржи (ISS). «${d.n} из ${d.total}» — показано выпусков из тех, цена которых сегодня изменилась. Не инвестиционная рекомендация.</p>`;
}
function bindMv(){
  if(!S.mv||S.mv.error)return;
  $('#mv-dir').onclick=e=>{const b=e.target.closest('[data-d]');if(!b)return;S.mvDir=b.dataset.d;S.mvSort={k:'chg',d:0};render()};
  $('#mv-head').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s,cur=S.mvSort.d||(S.mvDir==='down'?1:-1);S.mvSort={k,d:S.mvSort.k===k?-cur:(k==='name'||k==='rating'?1:-1)};drawMv()};
  drawMv();
}
function pScr(){
  if(S.scrTab==='mv')return scrTabs()+pMv();
  return scrTabs()+pScr0();
}
function pScr0(){
  const d=S.scr;
  if(!d){loadScr();return`<div class="card">${waitBox('Загружаю торги облигациями с Мосбиржи и сопоставляю рейтинги…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="scr-r">Повторить</button></div>`;
  const f=S.sf,opt=(v,t,cur)=>`<option value="${v}" ${cur===v?'selected':''}>${t}</option>`;
  const fl0=d.floor&&d.floor.lqdt,flN=fl0>0?`<p class="note scr-fl">Фонд ликвидности сейчас даёт ≈ ${f2(fl0)} % годовых — у бумаг ниже этой доходности нет премии за риск (такие строки приглушены). Доходность до налогов; не инвестиционная рекомендация.</p>`:'';
  const rated=d.rows.filter(r=>r.rating).length,sectors=[...new Set(d.rows.map(r=>r.sector).filter(Boolean))].sort((a,b)=>(SECT[a]||a).localeCompare(SECT[b]||b));
  const ac=scrActiveCount();
  return`<div class="card"><h2>Подбор облигаций<span class="sp" id="scr-cnt"></span></h2>
    <div class="scr-bar">
      <input class="in" id="f-q" value="${esc(f.q)}" placeholder="Поиск по названию или ISIN…" aria-label="Поиск облигаций">
      <div class="scr-presets">${SCR_PRESETS.map(([k,t])=>`<button class="scr-chip${S.scrPreset===k?' on':''}" data-pr="${k}">${t}</button>`).join('')}</div>
      <button class="btn ghost" id="scr-ftog">${S.scrOpen?'Скрыть фильтры':'Фильтры'}${ac?` (${ac})`:''}</button>
      ${ac||f.q||S.scrPreset?'<button class="btn ghost" id="f-reset">Сбросить</button>':''}
    </div>
    <div class="flt${S.scrOpen?'':' shut'}" id="scr-flt">
    <label class="field"><span>Валюта</span><select class="in" id="f-cur">${opt('RUB','Рубли',f.cur)}${opt('all','Все',f.cur)}${opt('USD','USD',f.cur)}${opt('CNY','CNY',f.cur)}${opt('EUR','EUR',f.cur)}</select></label>
    <label class="field"><span>Тип</span><select class="in" id="f-kind">${opt('all','Все',f.kind)}${opt('corp','Корпоративные',f.kind)}${opt('ofz','ОФЗ',f.kind)}</select></label>
    ${sectors.length?`<label class="field"><span>Сектор</span><select class="in" id="f-sector"><option value="">любой</option>${sectors.map(x=>opt(x,SECT[x]||x,f.sector)).join('')}</select></label>`:''}
    <label class="field"><span>Рейтинг не ниже</span><select class="in" id="f-rmin"><option value="">любой</option>${RSC.slice(0,10).map(x=>opt(x,x,f.rmin)).join('')}</select></label>
    <label class="field"><span>Доходность от, %</span><input class="in num" id="f-ymin" value="${esc(f.ymin)}" inputmode="decimal"></label>
    <label class="field"><span>Доходность до, %</span><input class="in num" id="f-ymax" value="${esc(f.ymax)}" inputmode="decimal"></label>
    <label class="field"><span>Спред к КБД от, п.п.</span><input class="in num" id="f-spmin" value="${esc(f.spmin)}" inputmode="decimal"></label>
    <label class="field"><span>До погашения, лет не более</span><input class="in num" id="f-tmax" value="${esc(f.tmax)}" inputmode="decimal"></label>
    <label class="field"><span>Ликвидность (оборот за день)</span><select class="in" id="f-turn">${opt('','любая',f.turn)}${opt('1','от 1 млн ₽',f.turn)}${opt('10','от 10 млн ₽',f.turn)}</select></label>
    <label class="field"><span>Ликвидность не ниже</span><select class="in" id="f-liq">${opt('','любая',f.liq)}${opt('L2','L2',f.liq)}${opt('L1','L1',f.liq)}</select></label>
    <label class="field"><span>Купон</span><select class="in" id="f-fl">${opt('all','любой',f.fl)}${opt('fix','фиксированный',f.fl)}${opt('float','флоатер',f.fl)}</select></label>
    <label class="sw"><input type="checkbox" id="f-toff" ${f.toOffer?'checked':''}><i></i><div><b>Считать до оферты</b><small>срок — до ближайшей оферты или погашения</small></div></label>
    <label class="sw"><input type="checkbox" id="f-noffer" ${f.noOffer?'checked':''}><i></i><div><b>Без оферт</b></div></label></div>
    ${flN}
    <div class="tbl" style="max-height:calc(100vh - 280px)"><table><thead><tr id="scr-head"></tr></thead><tbody id="scr-body"></tbody></table></div>
    <div class="row" style="margin-top:12px"><button class="btn ghost" id="scr-more">Показать ещё</button></div></div>
  <p class="note">Данные — Московская биржа (ISS, режимы торгов Т+ для корпоративных облигаций и ОФЗ; с задержкой, как в бесплатном доступе). Доходность — по цене последних торгов, спред — к кривой КБД при той же дюрации. Рейтинг найден у ${rated} из ${d.rows.length} выпусков: эмитенты без рейтинга в базе не обязательно ненадёжны. По умолчанию скрыты выпуски с доходностью выше 60% (обычно это дефолтные или почти не торгуемые бумаги) — поле «Доходность до» можно очистить. </p>${NIR_NOTE}`;
}
function bindScr(){
  const tb=$('#scr-tabs');if(tb)tb.onclick=e=>{const b=e.target.closest('[data-t]');if(!b||b.dataset.t===S.scrTab)return;S.scrTab=b.dataset.t;render()};
  if(S.scrTab==='mv')return bindMv();
  if(!S.scr||S.scr.error){const b=$('#scr-r');if(b)b.onclick=()=>{S.scr=null;render()};return}
  const map={'f-q':'q','f-cur':'cur','f-kind':'kind','f-sector':'sector','f-rmin':'rmin','f-ymin':'ymin','f-ymax':'ymax','f-spmin':'spmin','f-tmax':'tmax','f-turn':'turn','f-fl':'fl','f-liq':'liq'};
  let to;Object.entries(map).forEach(([id,k])=>{const e=$('#'+id);if(!e)return;e.oninput=e.onchange=()=>{if(k!=='q')S.scrPreset='';S.sf[k]=e.value;S.sn=150;clearTimeout(to);to=setTimeout(drawScr,150)}});
  $('#f-toff').onchange=e=>{S.scrPreset='';S.sf.toOffer=e.target.checked;S.sn=150;drawScr()};
  $('#f-noffer').onchange=e=>{S.scrPreset='';S.sf.noOffer=e.target.checked;S.sn=150;drawScr()};
  const ft=$('#scr-ftog');if(ft)ft.onclick=()=>{S.scrOpen=!S.scrOpen;const el=$('#scr-flt');if(el)el.classList.toggle('shut',!S.scrOpen);drawScr()};
  document.querySelectorAll('.scr-chip[data-pr]').forEach(b=>b.onclick=()=>{
    const k=b.dataset.pr;
    if(S.scrPreset===k){S.scrPreset='';S.sf=Object.assign({},SCR_DEF)}
    else{const p=SCR_PRESETS.find(x=>x[0]===k);S.scrPreset=k;S.sf=Object.assign({},SCR_DEF,p?p[2]:{})}
    S.sn=150;render();
  });
  const rs=$('#f-reset');if(rs)rs.onclick=()=>{S.scrPreset='';S.sf=Object.assign({},SCR_DEF);S.sn=150;render()};
  $('#scr-more').onclick=()=>{S.sn+=200;drawScr()};
  $('#scr-head').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;S.ssort={k,d:S.ssort.k===k?-S.ssort.d:(['name'].includes(k)?1:-1)};drawScr()};
  drawScr();
}


(()=>{const st=document.createElement('style');st.textContent=`.tag.liq-L1{background:#3ecf8e26;color:var(--pos)}.tag.liq-L2{background:#ffdd2d26}.tag.liq-L3{opacity:.7}.scr-fl-t{background:#3987e526}`;document.head.appendChild(st)})();
