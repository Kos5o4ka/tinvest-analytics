/* ── Скринер акций: подборки, фильтры, сортируемая таблица; клик по строке открывает карточку акции ── */
S.sst=null;S.ssf={q:'',preset:'',sector:'',pemax:'',pbmax:'',dymin:'',gmin:'',capmin:''};S.sssort={k:'cap',d:-1};S.ssn=200;
function loadSst(force){
  if(S._sstL&&!force)return;S._sstL=1;
  api('/api/stock_screener'+(force?'?force=1':'')).then(j=>{S._sstL=0;S.sst=j;if(S.page==='sst'){renderSoon();if(j.loading)setTimeout(()=>{if(S.page==='sst')loadSst(false)},4000)}})
   .catch(e=>{S._sstL=0;S.sst={error:e.message,rows:[],presets:[]};if(S.page==='sst')renderSoon()});
}
function sstRows(){
  const f=S.ssf,q=f.q.trim().toLowerCase(),nv=x=>x===''||isNaN(parseFloat(String(x).replace(',','.')))?null:parseFloat(String(x).replace(',','.'));
  const pemax=nv(f.pemax),pbmax=nv(f.pbmax),dymin=nv(f.dymin),gmin=nv(f.gmin),capmin=nv(f.capmin);
  const rs=S.sst.rows.filter(r=>{
    if(f.preset&&!(r.tags||[]).includes(f.preset))return false;
    if(f.sector&&r.sector!==f.sector)return false;
    if(q&&!(r.secid.toLowerCase().includes(q)||(r.name||'').toLowerCase().includes(q)||(r.shortname||'').toLowerCase().includes(q)))return false;
    if(pemax!=null&&!(r.pe!=null&&r.pe>0&&r.pe<=pemax))return false;
    if(pbmax!=null&&!(r.pb!=null&&r.pb>0&&r.pb<=pbmax))return false;
    if(dymin!=null&&!(r.div_yield!=null&&r.div_yield>=dymin))return false;
    if(gmin!=null&&!(r.rev_growth!=null&&r.rev_growth>=gmin))return false;
    if(capmin!=null&&!(r.cap!=null&&r.cap>=capmin*1e9))return false;
    return true;
  });
  const{k,d}=S.sssort;
  rs.sort((a,b)=>{const x=a[k],y=b[k];if(typeof x==='string'||typeof y==='string')return d*String(x||'').localeCompare(String(y||''));return d*((x??-Infinity)-(y??-Infinity))});
  return rs;
}
function drawSst(){
  const rs=sstRows(),n=Math.min(rs.length,S.ssn),{k,d}=S.sssort;
  const cols=[['secid','Акция','l'],['sector','Сектор','l'],['price','Цена, ₽'],['chg_d','День'],['chg_w','Неделя'],['chg_m','Месяц'],['cap','Капитализация'],['pe','P/E'],['pb','P/B'],['ev_ebitda','EV/EBITDA'],['div_yield','Дивиденды'],['rev_growth','Рост выручки'],['roe','ROE']];
  $('#sst-head').innerHTML=cols.map(([kk,t,c])=>`<th class="s ${c||''}" data-s="${kk}">${t} <span>${k===kk?(d>0?'↑':'↓'):''}</span></th>`).join('');
  const x=(v,dg=1)=>v==null?'<span class="mu">—</span>':stkN(v,dg),pc=(v)=>v==null?'<span class="mu">—</span>':stkPc(v,1);
  const dv=S.ssf.preset==='high_div'||k==='div_yield'||!!S.ssf.dymin;   /* дивидендная подборка — сразу на вкладку «Дивиденды» */
  $('#sst-body').innerHTML=rs.slice(0,n).map(r=>`<tr${stkAttr(r.secid,dv?'div':'')}><td class="l"><b>${esc(r.shortname||r.secid)}</b><br><small class="mu">${esc(r.shortname?r.secid:'')}</small></td><td class="l"><small>${esc(r.sector)}</small></td>
    <td class="num">${stkPrice(r.price)}</td><td class="num">${pc(r.chg_d)}</td><td class="num">${pc(r.chg_w)}</td><td class="num">${pc(r.chg_m)}</td><td class="num">${stkCap(r.cap)}</td>
    <td class="num ${r.pe!=null&&r.pe_sector&&r.pe>0&&r.pe<r.pe_sector?'pos':''}" title="${r.pe_sector?'медиана сектора: '+stkN(r.pe_sector,1):''}">${r.pe!=null&&r.pe>0?stkN(r.pe,1):'<span class="mu">—</span>'}</td>
    <td class="num">${r.pb!=null&&r.pb>0?stkN(r.pb,2):'<span class="mu">—</span>'}</td><td class="num">${r.ev_ebitda!=null&&r.ev_ebitda>0?stkN(r.ev_ebitda,1):'<span class="mu">—</span>'}</td>
    <td class="num"${r.div_yield==null?'':stkAttr(r.secid,'div')}>${r.div_yield==null?'<span class="mu">—</span>':'<b>'+stkN(r.div_yield,1)+' %</b>'}</td><td class="num">${pc(r.rev_growth)}</td><td class="num">${r.roe==null?'<span class="mu">—</span>':stkN(r.roe,1)+' %'}</td></tr>`).join('')||`<tr><td colspan="13" class="empty">Ничего не найдено — ослабьте фильтры</td></tr>`;
  $('#sst-cnt').textContent=`Найдено: ${rs.length}${rs.length>n?' · показано '+n:''}`;
  $('#sst-more').style.display=rs.length>n?'':'none';
}
function pSst(){
  const d=S.sst;
  if(!d){loadSst();return`<div class="card">${waitBox('Загружаю акции Мосбиржи и показатели…')}</div>`}
  if(d.error&&!d.rows.length&&!d.loading)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="sst-r">Повторить</button></div>`;
  if(!d.rows.length){
    const p=d.progress||{};
    return`<div class="card">${waitBox('Считаю мультипликаторы по отчётности МСФО'+(p.total?` — ${p.done} из ${p.total}`:'')+'. Первый расчёт без токена T-Invest занимает несколько минут, потом результат хранится сутки.')}</div>`;
  }
  const f=S.ssf,fld=(id,t,v)=>`<label class="field"><span>${t}</span><input class="in num" id="${id}" value="${esc(v)}" inputmode="decimal"></label>`;
  const presets=[{id:'',name:'Все акции',hint:''}].concat(d.presets||[]);
  const src=d.source==='tinvest-server'?'Данные T-Invest (через сервер), TTM.':d.source==='tinvest'?'Показатели — T-Invest API (TTM).':'Показатели рассчитаны по отчётности МСФО (smart-lab) и капитализации Мосбиржи; дивидендная доходность без токена T-Invest недоступна.';
  return`<div class="card"><h2>Подбор акций<span class="sp" id="sst-cnt"></span></h2>
    <div class="seg" id="sst-pre" style="margin-bottom:12px">${presets.map(p=>`<button data-p="${esc(p.id)}" class="${f.preset===p.id?'on':''}" title="${esc(p.hint||'')}">${esc(p.name)}</button>`).join('')}</div>
    <div class="flt"><label class="field"><span>Поиск</span><input class="in" id="ss-q" value="${esc(f.q)}" placeholder="тикер или название"></label>
      <label class="field"><span>Сектор</span><select class="in" id="ss-sector"><option value="">любой</option>${(d.sectors||[]).map(x=>`<option value="${esc(x)}" ${f.sector===x?'selected':''}>${esc(x)}</option>`).join('')}</select></label>
      ${fld('ss-pemax','P/E не больше',f.pemax)}${fld('ss-pbmax','P/B не больше',f.pbmax)}${fld('ss-dymin','Дивиденды от, %',f.dymin)}${fld('ss-gmin','Рост выручки от, %',f.gmin)}${fld('ss-capmin','Капитализация от, млрд ₽',f.capmin)}
      <button class="btn ghost" id="ss-reset">Сбросить</button><button class="btn ghost" id="sst-r">Обновить</button></div>
    ${d.loading?`<p class="note">Показатели обновляются в фоне…</p>`:''}
    <div class="tbl" style="max-height:calc(100vh - 340px)"><table><thead><tr id="sst-head"></tr></thead><tbody id="sst-body"></tbody></table></div>
    <div class="row" style="margin-top:12px"><button class="btn ghost" id="sst-more">Показать ещё</button></div></div>
  <p class="note">${esc(src)} «Дешёвые по P/E» — P/E больше 0 и ниже медианы сектора. Сектор — по справочнику программы и T-Invest. ${NIR_NOTE}</p>`;
}
function bindSst(){
  const r=$('#sst-r');if(r)r.onclick=()=>{S.sst=null;S._sstL=0;loadSst(true);render()};
  if(!S.sst||!S.sst.rows.length)return;
  const map={'ss-q':'q','ss-sector':'sector','ss-pemax':'pemax','ss-pbmax':'pbmax','ss-dymin':'dymin','ss-gmin':'gmin','ss-capmin':'capmin'};
  let to;for(const[id,k]of Object.entries(map)){const e=$('#'+id);if(e)e.oninput=e.onchange=()=>{S.ssf[k]=e.value;S.ssn=200;clearTimeout(to);to=setTimeout(drawSst,120)}}
  $('#sst-pre').onclick=e=>{const b=e.target.closest('[data-p]');if(!b)return;S.ssf.preset=b.dataset.p;S.ssn=200;$('#sst-pre').querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));drawSst()};
  $('#ss-reset').onclick=()=>{S.ssf={q:'',preset:'',sector:'',pemax:'',pbmax:'',dymin:'',gmin:'',capmin:''};render()};
  $('#sst-head').onclick=e=>{const h=e.target.closest('[data-s]');if(!h)return;const k=h.dataset.s;S.sssort={k,d:S.sssort.k===k?-S.sssort.d:(['secid','sector'].includes(k)?1:-1)};drawSst()};
  /* клик по строке ([data-stk]) — общий обработчик в 45_stock.js */
  $('#sst-more').onclick=()=>{S.ssn+=200;drawSst()};
  drawSst();
}
