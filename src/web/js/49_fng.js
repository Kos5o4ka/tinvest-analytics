/* ── Страх и жадность: индекс настроений российского рынка (0 — крайний страх, 100 — крайняя жадность) ── */
S.fng={data:null,loading:false,t:0};
const FNG_ZONES=[[0,25,'Крайний страх','#e5484d'],[25,45,'Страх','#f08a4b'],[45,56,'Нейтрально','#9aa1ae'],[56,76,'Жадность','#7cc36e'],[76,100,'Крайняя жадность','#2fb36e']];
const fngColor=v=>{const z=FNG_ZONES.find(z=>v<z[1])||FNG_ZONES[4];return z[3]};
const fngNum=v=>bad(v)?'—':String(Math.round(v));
function loadFng(force){
  const F=S.fng;if(F.loading)return;F.loading=true;
  api('/api/fng'+(force?'?force=1':'')).then(j=>{F.data=j}).catch(e=>{F.data={error:e.message||String(e),components:[],history:[]}})
   .then(()=>{F.loading=false;F.t=Date.now();if(S.page==='fng'){renderSoon();if(F.data&&F.data.loading)setTimeout(()=>{if(S.page==='fng')loadFng()},8000)}});
}
/* полукруг: 0 слева, 100 справа; дуга с градиентом красный → серый → зелёный и стрелка */
function fngGauge(v){
  const cx=150,cy=140,r=112,pt=(a,rr)=>[cx+rr*Math.cos(Math.PI*(1-a/100)),cy-rr*Math.sin(Math.PI*(1-a/100))];
  const arc=(a0,a1,rr)=>{const p0=pt(a0,rr),p1=pt(a1,rr);return`M${p0[0].toFixed(1)} ${p0[1].toFixed(1)}A${rr} ${rr} 0 0 1 ${p1[0].toFixed(1)} ${p1[1].toFixed(1)}`};
  const has=!bad(v),ang=has?v:50,n=pt(ang,r-16),b1=pt(ang+50,6),b2=pt(ang-50,6);
  const ticks=[0,25,50,75,100].map(a=>{const p=pt(a,r+13);return`<text class="fg-tk" x="${p[0].toFixed(1)}" y="${(p[1]+4).toFixed(1)}" text-anchor="middle">${a}</text>`}).join('');
  return`<svg class="fg-gauge" viewBox="0 0 300 172" role="img" aria-label="Индекс страха и жадности ${has?Math.round(v):'нет данных'}">
    <defs><linearGradient id="fg-gr" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#e5484d"/><stop offset=".3" stop-color="#f08a4b"/><stop offset=".5" stop-color="#9aa1ae"/><stop offset=".7" stop-color="#7cc36e"/><stop offset="1" stop-color="#2fb36e"/></linearGradient></defs>
    <path d="${arc(0,100,r)}" fill="none" stroke="url(#fg-gr)" stroke-width="22" stroke-linecap="butt"/>${ticks}
    ${has?`<g class="fg-needle"><polygon points="${n[0].toFixed(1)},${n[1].toFixed(1)} ${b1[0].toFixed(1)},${b1[1].toFixed(1)} ${b2[0].toFixed(1)},${b2[1].toFixed(1)}" fill="var(--tx)"/><circle cx="${cx}" cy="${cy}" r="7" fill="var(--tx)"/></g>`:''}
    <text class="fg-big" x="${cx}" y="${cy-30}" text-anchor="middle" fill="${has?fngColor(v):'var(--mu)'}">${fngNum(v)}</text></svg>`;
}
function fngChips(d){
  const P=[['day','Вчера'],['week','Неделю назад'],['month','Месяц назад'],['year','Год назад']];
  return`<div class="fg-chips">${P.map(([k,t])=>{const p=d.prev&&d.prev[k];
    return p?`<div class="fg-chip" title="${esc(dlabel(p.d))}"><small>${t}</small><b style="color:${fngColor(p.v)}">${fngNum(p.v)}</b><span>${esc(fngLabel(p.v))}</span></div>`
      :`<div class="fg-chip"><small>${t}</small><b class="mu">—</b><span>нет данных</span></div>`}).join('')}</div>`;
}
function fngLabel(v){return(FNG_ZONES.find(z=>Math.round(v)<z[1])||FNG_ZONES[4])[2]}
function fngCards(d){
  return`<div class="fg-cards">${d.components.map(c=>`<div class="fg-cc"><div class="fg-ch"><b>${esc(c.name)}</b>${c.conf==='low'?`<em title="Истории пока мало (${c.pts} точек из 120): оценка приблизительная">мало истории</em>`:''}<span style="color:${fngColor(c.score)}">${fngNum(c.score)}</span></div>
    <div class="fg-bar"><i style="left:${Math.max(0,Math.min(100,c.score))}%;background:${fngColor(c.score)}"></i></div>
    <p>${esc(c.note)}</p></div>`).join('')}</div>`;
}
function fngChart(el){
  const d=S.fng.data,h=(d&&d.history||[]).filter(x=>x.d>=new Date(Date.now()-366*864e5).toISOString().slice(0,10));
  if(h.length<2){emptyChart(el,260,'История индекса пока накапливается');return}
  const W=el.clientWidth,H=260,pl=34,pr=10,pt=10,pb=26,n=h.length,pw=W-pl-pr,ph=H-pt-pb,X=i=>pl+i/(n-1)*pw,Y=v=>pt+ph-v/100*ph;
  let s=FNG_ZONES.map(z=>`<rect x="${pl}" y="${Y(z[1])}" width="${pw}" height="${Y(z[0])-Y(z[1])}" fill="${z[3]}" fill-opacity=".13"/>`).join('');
  [0,25,50,75,100].forEach(v=>s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax num" x="${pl-8}" y="${Y(v)+4}" text-anchor="end">${v}</text>`);
  let last=-99;h.forEach((x,i)=>{const m=x.d.slice(0,7);if(m!==last&&X(i)>pl+14&&X(i)<W-pr-20){const[y,mm]=m.split('-');s+=`<text class="ax" x="${X(i)}" y="${H-6}" text-anchor="middle">${MON[+mm-1]} ${y.slice(2)}</text>`}last=m});
  s+=`<polyline points="${h.map((x,i)=>X(i).toFixed(1)+','+Y(x.v).toFixed(1)).join(' ')}" fill="none" stroke="var(--tx)" stroke-width="1.8" stroke-linejoin="round"/>`;
  let hits='';const cw=pw/(n-1);for(let i=0;i<n;i++)hits+=`<rect data-i="${i}" x="${X(i)-cw/2}" y="${pt}" width="${cw}" height="${ph}" fill="transparent"/>`;
  el.innerHTML=`<svg width="${W}" height="${H}">${s}<g class="hv"></g>${hits}</svg>`;
  const hv=el.querySelector('.hv');
  el._hl=i=>{hv.innerHTML=i<0?'':`<line x1="${X(i)}" x2="${X(i)}" y1="${pt}" y2="${pt+ph}" stroke="var(--mu)" stroke-dasharray="3 3"/><circle cx="${X(i)}" cy="${Y(h[i].v)}" r="4.5" fill="${fngColor(h[i].v)}" stroke="var(--card)" stroke-width="2"/>`};
  bindTip(el,i=>`<b>${esc(dlabel(h[i].d))}</b>`+tipRow(fngColor(h[i].v),fngLabel(h[i].v),fngNum(h[i].v)));
}
function pFng(){
  const F=S.fng;
  if(!F.data||Date.now()-F.t>10*60*1000){if(!F.loading)loadFng()}
  const d=F.data;
  let h=`<div class="card"><h2>Страх и жадность<span class="sp">настроения российского рынка акций и облигаций</span></h2>`;
  if(!d)return h+waitBox('Считаю индекс…')+`</div>`;
  if(d.error)return h+`<div class="msg err">${esc(d.error)}</div></div>`;
  const pr=d.progress||{};
  if(d.value==null)return h+waitBox(d.loading?'Загружаю историю рынка с Мосбиржи… это займёт несколько минут, страница обновится сама.':'Нет данных для расчёта индекса.')+`</div>`;
  h+=`<div class="fg-top"><div class="fg-g">${fngGauge(d.value)}<div class="fg-lbl" style="color:${fngColor(d.value)}">${esc(d.label)}</div><div class="fg-ts">по закрытию ${esc(dlabel(d.ts))}</div></div>${fngChips(d)}</div>`;
  if(d.loading)h+=`<div class="msg" style="margin:12px 0">Идёт загрузка истории акций (${pr.have||0} из ~${pr.need||'?'} торговых дней): значения уточняются по мере загрузки.</div>`;
  else if(d.low_conf)h+=`<div class="msg" style="margin:12px 0">Часть компонентов считается по короткой истории или недоступна, поэтому индекс приблизительный. Значение уточняется по мере накопления данных.</div>`;
  h+=`</div><div class="card"><h2>Из чего складывается<span class="sp">оценка каждого компонента: 0 — страх, 100 — жадность; индекс — их среднее</span></h2>${fngCards(d)}</div>
    <div class="card"><h2>История за год<span class="sp">зоны: страх (красные), нейтрально (серая), жадность (зелёные)</span></h2><div class="chart" id="fg-chart"></div></div>
    <div class="card fg-note"><h2>Как считается</h2><p>Для каждого компонента берётся сегодняшнее значение и сравнивается с его историей за последние два года: оценка — процент дней, когда значение было ниже сегодняшнего (для волатильности, спроса на защитные активы и спредов шкала перевёрнута: рост означает страх). Индекс — среднее оценок доступных компонентов. Компоненты: отклонение IMOEX от 125-дневной средней; доля акций выше 50-дневной средней; новые годовые максимумы минус минимумы; индекс волатильности RVI к 50-дневной средней; доходность ОФЗ минус акций за 20 дней; спред высокодоходных облигаций к кривой ОФЗ; поток денег в акции против фондов денежного рынка (если доступен).</p>
    <p class="mu">Индекс отражает настроения участников рынка и не является инвестиционной рекомендацией. Крайний страх не гарантирует разворот вверх, а крайняя жадность — падение.</p></div>`;
  chart('fg-chart',fngChart);
  return h;
}
