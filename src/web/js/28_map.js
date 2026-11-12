/* ── Карта рынка: доходность и дюрация, спреды по рейтингам ── */
const MP_COL={'AAA':'#199e70','AA':'#3ecf8e','A':'#3987e5','BBB':'#e3a21a','BB и ниже':'#ff6b6b','нет рейтинга':'#8a90a0'};
const MP_BK=['AAA','AA','A','BBB','BB и ниже','нет рейтинга'];
S.mp={rb:{'AAA':true,'AA':true,'A':true,'BBB':true,'BB и ниже':true,'нет рейтинга':true},sector:'',dmax:'5',liquid:true,mine:false,all:false};
function mpMine(){const s=new Set();((S.bonds&&S.bonds.rows)||[]).forEach(b=>{if(b.isin)s.add(b.isin);if(b.ticker)s.add(b.ticker)});return s}
function mpRows(){
  const f=S.mp,mine=mpMine(),dm=f.dmax==='all'?1e9:+f.dmax;
  return S.scr.rows.filter(r=>{
    if(r.cur!=='RUB'||r.kind!=='corp'||!(r.yield>0))return false;
    const d=r.dur||r.years;if(!(d>0)||d>dm)return false;
    if(!f.rb[rBucket(r.rating)])return false;
    if(f.sector&&r.sector!==f.sector)return false;
    if(f.liquid&&r.turn<1e6)return false;
    if(f.mine&&!(mine.has(r.isin)||mine.has(r.id)))return false;
    return true;
  });
}
function mpScatter(el){
  const W=el.clientWidth,H=W<560?340:460,pl=W<560?38:46,pr=12,pt=12,pb=30;
  const f=S.mp,mine=mpMine(),dm=f.dmax==='all'?null:+f.dmax;
  let rs=mpRows().map(r=>({r,x:r.dur||r.years}));
  const cap=f.all?Infinity:40,hidden=rs.filter(p=>p.r.yield>cap).length;
  rs=rs.filter(p=>p.r.yield<=cap);
  if(W<50)return;
  if(!rs.length){emptyChart(el,H,'Нет выпусков под выбранные фильтры');return mpCnt(0,hidden)}
  const xmax=dm||nice(0,Math.max(...rs.map(p=>p.x)),6).hi,ymax=f.all?nice(0,Math.max(...rs.map(p=>p.r.yield)),5).hi:40;
  const nx=nice(0,xmax,Math.min(10,Math.max(2,Math.round(W/90)))),ny=nice(0,ymax,5);
  const X0=0,X1=dm||nx.hi,Y1=ny.hi,pw=W-pl-pr,ph=H-pt-pb,X=v=>pl+(v-X0)/(X1-X0)*pw,Y=v=>pt+ph-v/Y1*ph;
  let s='';
  for(let v=0;v<=Y1+ny.step/2;v+=ny.step)s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax num" x="${pl-8}" y="${Y(v)+4}" text-anchor="end">${v}%</text>`;
  for(let v=0;v<=X1+nx.step/2;v+=nx.step){if(v>X1+1e-9)break;s+=`<line class="grid-l" x1="${X(v)}" x2="${X(v)}" y1="${pt}" y2="${pt+ph}"/><text class="ax num" x="${X(v)}" y="${H-8}" text-anchor="middle">${+v.toFixed(2)}</text>`}
  const kb=((S.scr.kbd)||[]).filter(p=>p[0]<=X1+1);
  if(kb.length>1)s+=`<polyline class="mp-kbd" fill="none" points="${kb.map(p=>X(Math.min(p[0],X1)).toFixed(1)+','+Y(Math.min(p[1],Y1)).toFixed(1)).join(' ')}"/>`;
  const fl=S.scr.floor&&S.scr.floor.lqdt;
  if(fl>0&&fl<=Y1)s+=`<line class="mp-fl" x1="${pl}" x2="${W-pr}" y1="${Y(fl).toFixed(1)}" y2="${Y(fl).toFixed(1)}"/><text class="ax mp-flt" x="${W-pr-4}" y="${(Y(fl)-5).toFixed(1)}" text-anchor="end">Фонд ликвидности LQDT ≈ ${f2(fl)} %</text>`;
  const rad=t=>t>0?Math.max(2.5,Math.min(9,2.5+(Math.log10(t)-5)*1.6)):2.5;
  rs.sort((a,b)=>b.r.turn-a.r.turn);
  let dots='',rings='';
  rs.forEach(p=>{const r=p.r,c=MP_COL[rBucket(r.rating)],rd=rad(r.turn),cx=X(p.x).toFixed(1),cy=Y(r.yield).toFixed(1),id=r.isin||r.id;
    dots+=`<circle class="mp-d" data-isin="${esc(id)}" data-k="${esc(r.id)}" cx="${cx}" cy="${cy}" r="${rd.toFixed(1)}" fill="${c}" fill-opacity=".72" stroke="${c}"/>`;
    if(mine.has(r.isin)||mine.has(r.id))rings+=`<circle class="mp-ring" cx="${cx}" cy="${cy}" r="${(rd+4.5).toFixed(1)}"/>`});
  el.innerHTML=`<div class="legend">${MP_BK.map(b=>`<span><i style="background:${MP_COL[b]}"></i>${b}</span>`).join('')}<span><i class="mp-lk"></i>КБД</span>${fl>0?'<span><i class="mp-lf"></i>фонд ликвидности</span>':''}<span class="mu">ось X — дюрация, лет; ось Y — доходность</span>${mine.size?'<span><i class="mp-lr"></i>мой портфель</span>':''}</div><svg width="${W}" height="${H}">${s}<g>${dots}</g><g style="pointer-events:none">${rings}</g></svg>`;
  const byK={};rs.forEach(p=>byK[p.r.id]=p);
  el.onmousemove=e=>{const t=e.target.closest('circle[data-k]');if(!t||!el.contains(t)){hideTip();return}
    const p=byK[t.dataset.k];if(!p)return;const r=p.r,c=MP_COL[rBucket(r.rating)];
    showTip(`<b>${esc(r.name)}</b><div style="color:var(--mu)">${esc(r.isin||r.id)}${r.sector?' · '+esc(SECT[r.sector]||r.sector):''}</div>`+
      tipRow(c,'Рейтинг',esc(r.rating||'нет'))+tipRow(c,'Доходность',pctp(r.yield,2))+tipRow(c,'Спред к КБД',r.spread!=null?(r.spread>0?'+':'')+f2(r.spread)+' п.п.':'—')+
      tipRow(c,'Дюрация',f2(p.x)+' г')+tipRow(c,'Оборот за день',r.turn?short(r.turn)+' ₽':'—')+(mine.has(r.isin)||mine.has(r.id)?'<div style="color:var(--ac)">в вашем портфеле</div>':'')+'<div style="color:var(--mu);margin-top:5px">нажмите — карточка выпуска</div>',e)};
  el.onmouseleave=hideTip;
  mpCnt(rs.length,hidden);
}
function mpCnt(n,h){const e=$('#mp-cnt');if(e)e.textContent=`Выпусков на графике: ${n}`+(h?` · выше 40 % скрыто: ${h}`:'')}
function mpHeat(){
  const st=S.scr.stats;if(!st||!st.grid)return'<div class="empty">Статистика недоступна</div>';
  const vals=[];st.grid.forEach(g=>g.cells.forEach(c=>{if(c.spread!=null)vals.push(Math.abs(c.spread))}));const mx=Math.max(1,...vals);
  const cell=c=>{if(!c||!c.n)return'<td class="mu">—</td>';const a=c.spread==null?0:Math.min(1,Math.abs(c.spread)/mx);
    return`<td style="background:rgba(57,135,229,${(0.06+a*0.42).toFixed(2)})"><b class="num">${c.spread==null?'—':(c.spread>0?'+':'')+f2(c.spread)}</b><small>${c.n} шт · ${pctp(c.yield,1)}</small></td>`};
  return`<div class="tbl"><table class="mp-hm"><thead><tr><th class="l">Рейтинг</th>${st.dur.map(d=>`<th>${d} г</th>`).join('')}<th>Все сроки</th></tr></thead><tbody>${
    st.grid.map(g=>`<tr><td class="l"><span class="tag rt rt-${g.bucket.split(' ')[0]}">${esc(g.bucket)}</span></td>${g.cells.map(cell).join('')}${cell(g.all)}</tr>`).join('')}</tbody></table></div>`;
}
function mpSectors(){
  const sc=(S.scr.stats&&S.scr.stats.sectors)||[];
  if(!sc.length)return'<div class="empty">Сектора выпусков появятся после загрузки каталога T-Invest</div>';
  return`<div class="tbl"><table><thead><tr><th class="l">Сектор</th><th>Выпусков</th><th>Медианная доходность</th><th>Медианный спред к КБД</th></tr></thead><tbody>${
    sc.map(x=>`<tr><td class="l">${esc(SECT[x.sector]||x.sector)}</td><td class="num">${x.n}</td><td class="num">${pctp(x.yield,2)}</td><td class="num">${x.spread==null?'—':(x.spread>0?'+':'')+f2(x.spread)+' п.п.'}</td></tr>`).join('')}</tbody></table></div>`;
}
function mpHist(el){
  const h=S.scr.stats_hist||{},days=Object.keys(h).sort();
  if(days.length<2)return el.innerHTML=`<div class="empty" style="min-height:120px;padding:18px">История копится ежедневно, начиная с дня установки приложения: сейчас накоплено дней — ${days.length}. График появится, когда их будет хотя бы два.</div>`;
  const ser=['AAA','AA','A','BBB','BB и ниже'].map(b=>({n:b,c:MP_COL[b],v:days.map(d=>h[d][b]??null)})).filter(s=>s.v.some(v=>v!=null));
  line(el,{labels:days.map(d=>ddm(d).slice(0,5)+'.'+d.slice(2,4)),tipLabels:days.map(ddm),series:ser,h:260,zero:false,fa:v=>(+v.toFixed(1))+'',ft:v=>f2(v)+' п.п.',empty:'Недостаточно данных'});
}
function pMap(){
  const d=S.scr;
  if(!d){loadScr();return`<div class="card">${waitBox('Загружаю торги облигациями с Мосбиржи…')}</div>`}
  if(d.error)return`<div class="msg err">${esc(d.error)} <button class="btn ghost" id="scr-r">Повторить</button></div>`;
  const f=S.mp,sectors=[...new Set(d.rows.map(r=>r.sector).filter(Boolean))].sort((a,b)=>(SECT[a]||a).localeCompare(SECT[b]||b));
  const opt=(v,t,cur)=>`<option value="${v}" ${String(cur)===String(v)?'selected':''}>${t}</option>`;
  const hasP=mpMine().size>0;
  chart('map-sc',mpScatter);chart('map-hist',mpHist);chart('map-root',bindMap);
  return`<div id="map-root"><div class="card"><h2>Карта рынка: доходность и дюрация<span class="sp" id="mp-cnt"></span></h2>
    <div class="mp-chips" id="mp-chips">${MP_BK.map(b=>`<button type="button" data-b="${esc(b)}" class="${f.rb[b]?'on':''}"><i style="background:${MP_COL[b]}"></i>${b}</button>`).join('')}</div>
    <div class="flt">
      ${sectors.length?`<label class="field"><span>Сектор</span><select class="in" id="mp-sec"><option value="">любой</option>${sectors.map(x=>opt(x,SECT[x]||x,f.sector)).join('')}</select></label>`:''}
      <label class="field"><span>Дюрация не более</span><select class="in" id="mp-dmax">${[['2','2 лет'],['3','3 лет'],['5','5 лет'],['7','7 лет'],['10','10 лет'],['all','любая']].map(([v,t])=>opt(v,t,f.dmax)).join('')}</select></label>
      <label class="sw"><input type="checkbox" id="mp-liq" ${f.liquid?'checked':''}><i></i><div><b>Скрыть неликвид</b><small>оборот за день &lt; 1 млн ₽</small></div></label>
      <label class="sw"><input type="checkbox" id="mp-mine" ${f.mine?'checked':''} ${hasP?'':'disabled'}><i></i><div><b>Только мой портфель</b><small>${hasP?'выпуски из ваших позиций':'портфель облигаций не загружен'}</small></div></label>
      <label class="sw"><input type="checkbox" id="mp-all" ${f.all?'checked':''}><i></i><div><b>Показать всё</b><small>без отсечки доходности 40 %</small></div></label>
    </div>
    <div class="chart" id="map-sc"></div></div>
  <div class="g c-2-1 mp-g"><div class="card"><h2>Спреды по рейтингам<span class="sp">медиана, п.п. к КБД</span></h2>${mpHeat()}
    <p class="note" style="margin-top:10px">В ячейке: медианный спред к КБД, число выпусков и медианная доходность. Учтены рублёвые корпоративные облигации с известным рейтингом, доходностью до 60 % и сроком более 0,1 года (${(d.stats&&d.stats.n)||0} выпусков).</p></div>
  <div class="card"><h2>По секторам</h2>${mpSectors()}</div></div>
  <div class="card"><h2>История медианных спредов<span class="sp">п.п. к КБД, по рейтингам</span></h2><div class="chart" id="map-hist"></div>
    <p class="note" style="margin-top:8px">История копится ежедневно, начиная с дня установки приложения: снимок сохраняется при открытии скринера или карты.</p></div></div>
  <p class="note">По горизонтали — дюрация (лет), по вертикали — доходность к погашению. Размер точки — дневной оборот, цвет — рейтинг, пунктир — кривая КБД, кольцо — выпуск из вашего портфеля. Рейтинги сопоставлены по названию эмитента, у части выпусков их нет. Рассматриваются рублёвые корпоративные облигации. </p>${NIR_NOTE}`;
}
function bindMap(){
  const f=S.mp,redraw=()=>{const e=$('#map-sc');if(e)mpScatter(e)};
  $('#mp-chips').onclick=e=>{const b=e.target.closest('[data-b]');if(!b)return;f.rb[b.dataset.b]=!f.rb[b.dataset.b];b.classList.toggle('on',f.rb[b.dataset.b]);redraw()};
  const sec=$('#mp-sec');if(sec)sec.onchange=()=>{f.sector=sec.value;redraw()};
  $('#mp-dmax').onchange=e=>{f.dmax=e.target.value;redraw()};
  $('#mp-liq').onchange=e=>{f.liquid=e.target.checked;redraw()};
  $('#mp-mine').onchange=e=>{f.mine=e.target.checked;redraw()};
  $('#mp-all').onchange=e=>{f.all=e.target.checked;redraw()};
  const r=$('#scr-r');if(r)r.onclick=()=>{S.scr=null;render()};
  if(!window._mpRs){window._mpRs=1;let t;addEventListener('resize',()=>{clearTimeout(t);t=setTimeout(()=>{if(S.page==='map'){const e=$('#map-sc');if(e&&S.scr&&!S.scr.error)mpScatter(e);const h=$('#map-hist');if(h&&S.scr&&!S.scr.error)mpHist(h)}},200)})}
}
