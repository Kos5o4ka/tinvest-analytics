/* ── сравнение 2–4 облигаций: данные берём из карточки выпуска (/api/bond), расчётов не дублируем ── */
S.cmp=(lsJson('ta_cmp',[])||[]).filter(x=>typeof x==='string').slice(0,4);
const CMP={d:{},q:'',max:4};
const cmpHas=i=>S.cmp.includes(String(i||'').toUpperCase());
function cmpSave(){lsSet('ta_cmp',JSON.stringify(S.cmp))}
function cmpAdd(isin){
  isin=String(isin||'').trim().toUpperCase();if(!isin)return false;
  if(S.cmp.includes(isin)){toast('Уже в сравнении');return false}
  if(S.cmp.length>=CMP.max){toast('В сравнении не более '+CMP.max+' облигаций');return false}
  S.cmp.push(isin);cmpSave();toast('Добавлено в сравнение ('+S.cmp.length+' из '+CMP.max+')');return true;
}
function cmpDel(isin){S.cmp=S.cmp.filter(x=>x!==isin);cmpSave()}
function cmpFetch(){
  S.cmp.forEach(i=>{
    if(CMP.d[i])return;
    CMP.d[i]={loading:true};
    api('/api/bond?isin='+encodeURIComponent(i)).then(c=>{CMP.d[i]={c}}).catch(e=>{CMP.d[i]={err:e.message||String(e)}}).then(()=>{if(S.page==='cmp')cmpDraw()});
  });
}
const cmpAvgTurn=c=>{const v=((c.history||{}).v||[]).slice(-30).filter(x=>x>0);return v.length?v.reduce((a,b)=>a+b,0)/v.length:(c.market&&c.market.turn)||null};
const cmpOffer=c=>{const t=new Date().toISOString().slice(0,10);return(c.offers||[]).filter(o=>o.date>=t).sort((a,b)=>a.date<b.date?-1:1)[0]||null};
const cmpKindTag=k=>k==='both'?'<span class="tag of-t-put">PUT</span> <span class="tag of-t-call">CALL</span>':k==='put'?'<span class="tag of-t-put" title="Право держателя продать выпуск эмитенту">PUT</span>':k==='call'?'<span class="tag of-t-call" title="Эмитент может погасить выпуск досрочно">CALL</span>':'<span class="tag of-t-unk" title="Тип оферты не указан в источниках">оферта</span>';
/* доходность выше CMP_ODD % или цена ниже 70 % номинала — признак проблем эмитента, такую бумагу не отмечаем «лучшей» */
const CMP_ODD=40,cmpOdd=c=>!!c.market&&((c.market.yield||0)>CMP_ODD||(c.market.price!=null&&c.market.price<70&&(c.market.yield||0)>25));
/* строки: [название, значение(c)->число/null для подсветки, вывод(c), лучше: 1 — больше, -1 — меньше, 0 — без подсветки] */
function cmpRows(){
  const fmtD=d=>d?ddm(d):'—',N=bcN;
  return[
    ['Цена, % от номинала',c=>null,c=>c.market?N(c.market.price,2)+' %':'—',0],
    ['Доходность (к погашению или оферте)',c=>c.market&&!cmpOdd(c)?c.market.yield:null,c=>c.market?N(c.market.yield,2)+' %'+(cmpOdd(c)?'<br><small class="neg" title="Цена сильно ниже номинала: рынок закладывает серьёзный риск, что эмитент не расплатится полностью">аномально высокая — риск дефолта</small>':''):'—',1],
    ['Считается до',c=>null,c=>c.market?(c.market.offer?'оферты '+fmtD(c.market.offer):'погашения'):'—',0],
    ['Купон и тип',c=>null,c=>{const ci=c.catalog||{},m=c.market;return(m&&m.coupon!=null?N(m.coupon,2)+' %':'—')+' · '+(ci.floating?'флоатер':'фикс')},0],
    ['Дюрация, лет',c=>null,c=>c.market&&c.market.dur!=null?N(c.market.dur,2):'—',0],
    ['Дата погашения',c=>null,c=>fmtD((c.market&&c.market.mat)||(c.catalog||{}).maturity||(c.desc||{}).MATDATE),0],
    ['Ближайшая оферта',c=>null,c=>{const o=cmpOffer(c);return o?fmtD(o.date)+' '+cmpKindTag(o.kind):'нет'},0],
    ['Амортизация',c=>null,c=>((c.catalog||{}).amort||(c.desc||{}).AMORTBOND==='1')?'да':'нет',0],
    ['Рейтинг',c=>c.rating&&!c.rating.approx&&RSC.includes(c.rating.v)?RSC.length-RSC.indexOf(c.rating.v):null,c=>c.rating?ratingTag(c.rating):'<span class="mu">нет</span>',1],
    ['Спред к КБД, п.п.',c=>c.market&&c.market.spread!=null&&!cmpOdd(c)?c.market.spread:null,c=>c.market&&c.market.spread!=null?(c.market.spread>0?'+':'')+N(c.market.spread,2):'—',1],
    ['Средний оборот за 30 дней',c=>cmpAvgTurn(c),c=>{const v=cmpAvgTurn(c);return v==null?'—':short(v)+' ₽/день'},1],
    ['НКД, ₽ на облигацию',c=>null,c=>c.market&&c.market.nkd!=null?N(c.market.nkd,2):'—',0]];
}
function cmpTable(){
  if(!S.cmp.length)return'<div class="mu" style="padding:14px 0;font-size:13px">Добавьте от 2 до 4 облигаций: через поиск выше или кнопкой «Сравнить» в карточке выпуска.</div>';
  const cols=S.cmp.map(i=>CMP.d[i]||{loading:true});
  const head=S.cmp.map((i,k)=>{const x=cols[k],c=x.c;
    return`<th class="cmp-h"><div class="cmp-n">${c?`<a href="#" data-isin="${esc(i)}">${esc(c.short||c.name||i)}</a>`:esc(i)}</div><code>${esc(i)}</code><button class="cmp-x" data-del="${esc(i)}" title="Убрать из сравнения" aria-label="Убрать">✕</button></th>`}).join('');
  const body=cmpRows().map(([t,val,out,dir])=>{
    const vs=cols.map(x=>x.c?val(x.c):null),ok=vs.filter(v=>v!=null),best=dir&&ok.length>1&&Math.max(...ok)!==Math.min(...ok)?(dir>0?Math.max(...ok):Math.min(...ok)):null;
    return`<tr><th class="l">${t}</th>${cols.map((x,k)=>`<td class="${best!=null&&vs[k]===best?'cmp-best':''}">${x.loading?'<span class="mu">…</span>':x.err?'<span class="mu">—</span>':out(x.c)}</td>`).join('')}</tr>`}).join('');
  const errs=cols.map((x,k)=>x.err?`${esc(S.cmp[k])}: ${esc(x.err)}`:(x.c&&!x.c.found?`${esc(S.cmp[k])}: нет торгов на основных режимах Мосбиржи, часть строк пуста`:'')).filter(Boolean);
  return`<div class="cmp-wrap"><table class="cmp"><thead><tr><th class="l"></th>${head}</tr></thead><tbody>${body}</tbody></table></div>`
    +(errs.length?`<div class="bc-warn">${errs.join('<br>')}</div>`:'')
    +(S.cmp.length<2?'<p class="note">Для сравнения нужна хотя бы вторая облигация.</p>':'');
}
function cmpDraw(){
  const t=$('#cmp-tbl');if(!t)return;
  t.innerHTML=cmpTable();
  t.querySelectorAll('[data-del]').forEach(b=>b.onclick=()=>{cmpDel(b.dataset.del);cmpDraw();cmpCount()});
  t.querySelectorAll('a[data-isin]').forEach(a=>a.onclick=e=>{e.preventDefault();openBond(a.dataset.isin)});
  cmpCount();
}
function cmpCount(){const e=$('#cmp-cnt');if(e)e.textContent=S.cmp.length+' из '+CMP.max;const i=$('#cmp-q');if(i)i.disabled=S.cmp.length>=CMP.max}
function cmpFind(q){
  q=kpNorm(q).trim();if(q.length<2)return[];
  const rows=(S.scr&&S.scr.rows)||[],out=[];
  for(const r of rows){
    const isin=(r.isin||r.id||'').toUpperCase();if(S.cmp.includes(isin))continue;
    if(kpNorm(r.name+' '+r.id+' '+isin+' '+(r.full||'')).includes(q)){out.push(r);if(out.length>=8)break}
  }
  return out;
}
function pCmp(){
  if(!S.scr)loadScr();
  return`<div class="card"><h2>Сравнение облигаций<span class="sp" id="cmp-cnt"></span></h2>
    <div class="cmp-add"><input class="in" id="cmp-q" placeholder="Название, тикер или ISIN выпуска" autocomplete="off"><div class="cmp-res" id="cmp-res"></div></div>
    <div id="cmp-tbl"></div>
    <p class="note">Зелёным отмечено лучшее значение в строке: выше доходность, рейтинг, спред и оборот (аномально высокая доходность не отмечается). Но более высокая доходность, как правило, означает более высокий риск: смотрите на рейтинг, срок, оферты и амортизацию вместе. Доходность — к погашению или к ближайшей оферте (как считает Мосбиржа), до налогов. Подробности по каждому выпуску — в карточке (клик по названию). Справочная информация, не инвестиционная рекомендация.</p></div>`;
}
function bindCmp(){
  cmpFetch();cmpDraw();
  const q=$('#cmp-q'),res=$('#cmp-res');if(!q)return;
  const add=i=>{if(cmpAdd(i)){q.value='';res.innerHTML='';cmpFetch();cmpDraw()}};
  q.oninput=()=>{
    const v=q.value.trim(),f=cmpFind(v);
    res.innerHTML=f.map(r=>`<button type="button" data-a="${esc((r.isin||r.id).toUpperCase())}">${esc(r.name)} <small class="mu">${esc(r.id)} · ${esc(r.isin||'')}</small></button>`).join('')
      +(!f.length&&/^[A-Za-z0-9]{10,14}$/.test(v)?`<button type="button" data-a="${esc(v.toUpperCase())}">Добавить по коду ${esc(v.toUpperCase())}</button>`:'')
      +(!f.length&&v.length>=2&&!S.scr?'<span class="mu" style="padding:8px 12px">Загружаю список облигаций…</span>':'');
  };
  q.onkeydown=e=>{if(e.key==='Enter'){const b=res.querySelector('button');if(b)add(b.dataset.a)}};
  res.onclick=e=>{const b=e.target.closest('[data-a]');if(b)add(b.dataset.a)};
}
