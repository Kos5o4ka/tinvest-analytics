/* ── Скринер облигаций ── */
S.scr=null;S.sf={q:'',cur:'RUB',kind:'all',sector:'',rmin:'',rated:false,ymin:'',ymax:'60',tmax:'',turn:'',spmin:'',noOffer:false};S.ssort={k:'yield',d:-1};S.sn=150;
function loadScr(){api('/api/screener').then(j=>{const t=Date.now();j.rows.forEach(r=>{r.years=(new Date(r.mat)-t)/315576e5});S.scr=j;if(S.page==='scr'||S.page==='map')render()}).catch(e=>{S.scr={error:e.message,rows:[]};if(S.page==='scr'||S.page==='map')render()})}
function scrRows(){
  const f=S.sf,q=f.q.trim().toLowerCase(),ri=f.rmin?RSC.indexOf(f.rmin):-1;
  const nv=x=>x===''||isNaN(parseFloat(x))?null:parseFloat(String(x).replace(',','.'));
  const ymin=nv(f.ymin),ymax=nv(f.ymax),tmax=nv(f.tmax),turn=nv(f.turn),spmin=nv(f.spmin);
  let rs=S.scr.rows.filter(r=>{
    if(f.cur!=='all'&&r.cur!==f.cur)return false;
    if(f.kind!=='all'&&r.kind!==f.kind)return false;
    if(q&&!((r.name||'').toLowerCase().includes(q)||(r.isin||'').toLowerCase().includes(q)||(r.full||'').toLowerCase().includes(q)))return false;
    if(ri>=0&&!(r.rating&&RSC.indexOf(r.rating)<=ri))return false;
    if(f.sector&&r.sector!==f.sector)return false;
    if(f.rated&&!r.rating)return false;
    if(ymin!=null&&r.yield<ymin)return false;if(ymax!=null&&r.yield>ymax)return false;
    if(tmax!=null&&r.years>tmax)return false;
    if(turn!=null&&r.turn<turn*1e6)return false;
    if(spmin!=null&&!(r.spread!=null&&r.spread>=spmin))return false;
    if(f.noOffer&&r.offer)return false;
    return r.years>0;
  });
  const{k,d}=S.ssort;
  rs.sort((a,b)=>{let x=a[k],y=b[k];if(k==='rating'){x=x?RSC.indexOf(x):null;y=y?RSC.indexOf(y):null;return -d*((x??99)-(y??99))}
    if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  return rs;
}
function drawScr(){
  const rs=scrRows(),n=Math.min(rs.length,S.sn),fl=S.scr.floor&&S.scr.floor.lqdt;
  const cols=[['name','Выпуск','l'],['rating','Рейтинг','l'],['sector','Сектор','l'],['price','Цена, %'],['yield','Доходность'],['spread','Спред к КБД'],['coupon','Купон, %'],['years','До погашения'],['dur','Дюрация'],['turn','Оборот сегодня']];
  const {k,d}=S.ssort;
  $('#scr-head').innerHTML=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  $('#scr-body').innerHTML=rs.slice(0,n).map(r=>`<tr${fl>0&&r.yield<fl?' class="scr-low" title="Доходность ниже, чем у фонда ликвидности"':''} data-isin="${esc(r.isin||r.id)}"><td class="l"><b>${esc(r.name)}</b><br><small class="mu num">${esc(r.isin||r.id)}${r.offer?' · оферта '+ddm(r.offer):''}</small></td>
    <td class="l">${r.rating?`<span class="tag rt rt-${rBucket(r.rating).split(' ')[0]}" title="${esc(r.rt_agency||'')}${r.rt_approx?' (приблизительное совпадение названия)':''}">${r.rt_approx?'≈ ':''}${esc(r.rating)}</span>`:'<span class="mu">—</span>'}</td>
    <td class="l">${r.sector?esc(SECT[r.sector]||r.sector):'<span class="mu">—</span>'}</td>
    <td class="num">${f2(r.price)}</td><td class="num"><b>${pctp(r.yield,2)}</b></td>
    <td class="num ${r.spread!=null?(r.spread>=0?'pos':'neg'):'mu'}">${r.spread!=null?(r.spread>0?'+':'')+f2(r.spread):'—'}</td>
    <td class="num">${r.coupon!=null?f2(r.coupon):'—'}</td><td class="num">${ddm(r.mat)}<br><small class="mu">${r.years.toFixed(1).replace('.',',')} г</small></td>
    <td class="num">${r.dur!=null?r.dur.toFixed(2).replace('.',','):'—'}</td><td class="num">${r.turn?short(r.turn):'—'}</td></tr>`).join('');
  $('#scr-cnt').textContent=`Найдено: ${rs.length}${rs.length>n?' · показано '+n:''}`;
  $('#scr-more').style.display=rs.length>n?'':'none';
}
function pScr(){
  const d=S.scr;
  if(!d){loadScr();return`<div class="card">${waitBox('Загружаю торги облигациями с Мосбиржи и сопоставляю рейтинги…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="scr-r">Повторить</button></div>`;
  const f=S.sf,opt=(v,t,cur)=>`<option value="${v}" ${cur===v?'selected':''}>${t}</option>`;
  const fl0=d.floor&&d.floor.lqdt,flN=fl0>0?`<p class="note scr-fl">Фонд ликвидности сейчас даёт ≈ ${f2(fl0)} % годовых — у бумаг ниже этой доходности нет премии за риск (такие строки приглушены). Доходность до налогов; не инвестиционная рекомендация.</p>`:'';
  const rated=d.rows.filter(r=>r.rating).length,sectors=[...new Set(d.rows.map(r=>r.sector).filter(Boolean))].sort((a,b)=>(SECT[a]||a).localeCompare(SECT[b]||b));
  return`<div class="card"><h2>Подбор облигаций<span class="sp" id="scr-cnt"></span></h2>
    <div class="flt">
    <label class="field"><span>Поиск</span><input class="in" id="f-q" value="${esc(f.q)}" placeholder="название или ISIN"></label>
    <label class="field"><span>Валюта</span><select class="in" id="f-cur">${opt('RUB','Рубли',f.cur)}${opt('all','Все',f.cur)}${opt('USD','USD',f.cur)}${opt('CNY','CNY',f.cur)}${opt('EUR','EUR',f.cur)}</select></label>
    <label class="field"><span>Тип</span><select class="in" id="f-kind">${opt('all','Все',f.kind)}${opt('corp','Корпоративные',f.kind)}${opt('ofz','ОФЗ',f.kind)}</select></label>
    ${sectors.length?`<label class="field"><span>Сектор</span><select class="in" id="f-sector"><option value="">любой</option>${sectors.map(x=>opt(x,SECT[x]||x,f.sector)).join('')}</select></label>`:''}
    <label class="field"><span>Рейтинг не ниже</span><select class="in" id="f-rmin"><option value="">любой</option>${RSC.slice(0,10).map(x=>opt(x,x,f.rmin)).join('')}</select></label>
    <label class="field"><span>Доходность от, %</span><input class="in num" id="f-ymin" value="${esc(f.ymin)}" inputmode="decimal"></label>
    <label class="field"><span>Доходность до, %</span><input class="in num" id="f-ymax" value="${esc(f.ymax)}" inputmode="decimal"></label>
    <label class="field"><span>Спред к КБД от, п.п.</span><input class="in num" id="f-spmin" value="${esc(f.spmin)}" inputmode="decimal"></label>
    <label class="field"><span>До погашения, лет не более</span><input class="in num" id="f-tmax" value="${esc(f.tmax)}" inputmode="decimal"></label>
    <label class="field"><span>Оборот за день от, млн ₽</span><input class="in num" id="f-turn" value="${esc(f.turn)}" inputmode="decimal"></label>
    <label class="sw"><input type="checkbox" id="f-noffer" ${f.noOffer?'checked':''}><i></i><div><b>Без оферт</b></div></label>
    <button class="btn ghost" id="f-reset">Сбросить</button></div>
    ${flN}
    <div class="tbl" style="max-height:calc(100vh - 300px)"><table><thead><tr id="scr-head"></tr></thead><tbody id="scr-body"></tbody></table></div>
    <div class="row" style="margin-top:12px"><button class="btn ghost" id="scr-more">Показать ещё</button></div></div>
  <p class="note">Данные — Московская биржа (ISS, режимы торгов Т+ для корпоративных облигаций и ОФЗ; с задержкой, как в бесплатном доступе). Доходность — по цене последних торгов, спред — к кривой КБД при той же дюрации. Рейтинг найден у ${rated} из ${d.rows.length} выпусков: эмитенты без рейтинга в базе не обязательно ненадёжны. По умолчанию скрыты выпуски с доходностью выше 60% (обычно это дефолтные или почти не торгуемые бумаги) — поле «Доходность до» можно очистить. Справочная информация, не инвестиционная рекомендация.</p>`;
}
function bindScr(){
  if(!S.scr||S.scr.error){const b=$('#scr-r');if(b)b.onclick=()=>{S.scr=null;render()};return}
  const map={'f-q':'q','f-cur':'cur','f-kind':'kind','f-sector':'sector','f-rmin':'rmin','f-ymin':'ymin','f-ymax':'ymax','f-spmin':'spmin','f-tmax':'tmax','f-turn':'turn'};
  let to;Object.entries(map).forEach(([id,k])=>{const e=$('#'+id);if(!e)return;e.oninput=e.onchange=()=>{S.sf[k]=e.value;S.sn=150;clearTimeout(to);to=setTimeout(drawScr,150)}});
  $('#f-noffer').onchange=e=>{S.sf.noOffer=e.target.checked;S.sn=150;drawScr()};
  $('#f-reset').onclick=()=>{S.sf={q:'',cur:'RUB',kind:'all',sector:'',rmin:'',rated:false,ymin:'',ymax:'60',tmax:'',turn:'',spmin:'',noOffer:false};render()};
  $('#scr-more').onclick=()=>{S.sn+=200;drawScr()};
  $('#scr-head').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;S.ssort={k,d:S.ssort.k===k?-S.ssort.d:(['name'].includes(k)?1:-1)};drawScr()};
  drawScr();
}

