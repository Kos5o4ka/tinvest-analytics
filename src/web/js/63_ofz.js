/* ── ОФЗ-Спредер: премия за дюрацию, наклон и кривизна КБД, ОФЗ-ПД относительно кривой ── */
S.ofz={data:null,loading:false,err:'',sk:'dur',sd:1};
PRO_FEATURES.ofz={t:'ОФЗ-Спредер',ic:'ofz',b:['Оправдан ли риск длинных ОФЗ: наклон КБД и премия за каждый год срока','Кривизна кривой: что выгоднее, bullet или barbell','Какие ОФЗ-ПД торгуются дешевле или дороже кривой КБД','Простой вывод по текущей форме кривой']};
function ofzLoad(force){
  const O=S.ofz;if(O.loading)return;
  O.loading=true;O.err='';
  api('/api/ofz_spread'+(force?'?force=1':'')).then(j=>{O.loading=false;O.data=j;if(S.page==='ofz')renderSoon()})
   .catch(e=>{O.loading=false;O.err=e.message||String(e);if(S.page==='ofz')renderSoon()});
}
const ofzN=(v,d=2)=>v==null||isNaN(v)?'—':(+v).toFixed(d).replace('.',',');
const ofzSg=(v,d=2)=>v==null||isNaN(v)?'—':(v>0?'+':v<0?'−':'')+ofzN(Math.abs(v),d);
const ofzBp=v=>v==null||isNaN(v)?'—':ofzSg(v,0)+' б.п.';
const ofzRegCls=c=>c==='deep_inv'?'ofz-b-inv2':c==='inv'?'ofz-b-inv':c==='steep'?'ofz-b-steep':'ofz-b-flat';
function ofzCurveChart(el,o){
  const cv=o.curve,bs=o.bonds;if(!cv.length)return emptyChart(el,240,'Нет данных КБД');
  const W=el.clientWidth||600,H=Math.max(260,Math.min(340,W*.5)),pl=44,pr=14,pt=14,pb=32,pw=W-pl-pr,ph=H-pt-pb;
  const xs=cv.map(p=>p.t).concat(bs.map(b=>b.dur)),ys=cv.map(p=>p.y).concat(bs.map(b=>b.yield));
  const xmax=Math.min(30,Math.max(...xs)),nx=nice(0,xmax,5),ny=nice(Math.min(...ys)-.3,Math.max(...ys)+.3,4);
  const X=t=>pl+t/nx.hi*pw,Y=v=>pt+ph-(v-ny.lo)/(ny.hi-ny.lo)*ph;
  let s='';
  for(let v=ny.lo;v<=ny.hi+1e-9;v+=ny.step)s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax num" x="${pl-6}" y="${Y(v)+4}" text-anchor="end">${ofzN(v,1)}%</text>`;
  for(let t=0;t<=nx.hi+1e-9;t+=nx.step)s+=`<text class="ax num" x="${X(t)}" y="${H-10}" text-anchor="middle">${ofzN(t,t%1?1:0)}</text>`;
  s+=`<text class="ax" x="${W-pr}" y="${H-1}" text-anchor="end">дюрация, лет</text>`;
  s+=`<path d="M${cv.filter(p=>p.t<=nx.hi).map(p=>X(p.t).toFixed(1)+','+Y(p.y).toFixed(1)).join('L')}" fill="none" stroke="var(--ac)" stroke-width="2.4" stroke-linejoin="round"/>`;
  const col=b=>b.flag==='cheap'?'var(--pos)':b.flag==='rich'?'var(--neg)':'var(--mu)';
  bs.forEach((b,i)=>{if(b.dur>nx.hi)return;s+=`<circle class="ofz-d" data-i="${i}" data-isin="${esc(b.isin||b.id)}" cx="${X(b.dur).toFixed(1)}" cy="${Y(b.yield).toFixed(1)}" r="5" fill="${col(b)}" fill-opacity=".8" stroke="${col(b)}" style="cursor:pointer"/>`});
  el.innerHTML=`<svg width="${W}" height="${H}" role="img" aria-label="Кривая КБД и доходности ОФЗ по дюрации">${s}</svg>`;
  bindTip(el,i=>{const b=bs[i];return`<b>${esc(b.name||b.id)}</b>`+tipRow(col(b),'Доходность',ofzN(b.yield)+' %')+tipRow('var(--ac)','КБД на сроке '+ofzN(b.dur,1)+' г.',ofzN(b.kbd)+' %')+tipRow(col(b),'Спред к КБД',ofzBp(b.spread_bp))});
}
function ofzTpChart(el,o){
  const tp=o.tp;if(!tp.length)return emptyChart(el,200,'Нет данных');
  const W=el.clientWidth||600,H=220,pl=44,pr=10,pt=14,pb=28,pw=W-pl-pr,ph=H-pt-pb,n=tp.length,bw=pw/n;
  const mx=Math.max(10,...tp.map(x=>x.bp)),mn=Math.min(0,...tp.map(x=>x.bp)),g=nice(mn,mx,4);
  const Y=v=>pt+ph-(v-g.lo)/(g.hi-g.lo)*ph;
  let s='';const G=gradSet();
  for(let v=g.lo;v<=g.hi+1e-9;v+=g.step)s+=`<line class="grid-l" x1="${pl}" x2="${W-pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax num" x="${pl-6}" y="${Y(v)+4}" text-anchor="end">${Math.round(v)}</text>`;
  tp.forEach((x,i)=>{const y0=Y(0),y1=Y(x.bp),bx=pl+i*bw+bw*.15,w=bw*.7,c=x.bp>=0?'var(--ac)':'var(--neg)';
    s+=`<path d="${(x.bp>=0?rtop:rbot)(bx,Math.min(y0,y1),w,Math.max(1.5,Math.abs(y1-y0)),4)}" fill="${G.u(c)}"/>`;
    if(n<=15&&(i%(W<420?2:1)===0))s+=`<text class="ax num" x="${bx+w/2}" y="${H-10}" text-anchor="middle">${x.t}</text>`;
    s+=`<rect data-i="${i}" x="${pl+i*bw}" y="${pt}" width="${bw}" height="${ph}" fill="transparent"/>`});
  el.innerHTML=`<svg width="${W}" height="${H}" role="img" aria-label="Премия за каждый год срока, базисных пунктов">${G.defs()}${s}</svg>`;
  bindTip(el,i=>`<b>${tp[i].t===1?'до 1 года':'год срока '+tp[i].t}</b>`+tipRow(tp[i].bp>=0?'var(--ac)':'var(--neg)','Прирост КБД',ofzBp(tp[i].bp)));
}
function ofzTable(bs){
  const O=S.ofz,k=O.sk,d=O.sd,v=b=>k==='name'?(b.name||''):b[k];
  const rows=bs.slice().sort((a,b)=>{const x=v(a),y=v(b);return(typeof x==='string'?x.localeCompare(y,'ru'):(x||0)-(y||0))*d});
  const th=(key,t,l)=>`<th class="${l?'l ':''}ofz-th" data-ofz-s="${key}">${t}${O.sk===key?(O.sd>0?' ▲':' ▼'):''}</th>`;
  const fl=b=>b.flag==='cheap'?'<span class="pill pos">дешевле кривой</span>':b.flag==='rich'?'<span class="pill neg">дороже кривой</span>':'<span class="mu">около кривой</span>';
  return`<div class="tbl"><table><thead><tr>${th('name','Выпуск',1)}${th('dur','Дюрация, лет')}${th('yield','Доходность, %')}${th('kbd','КБД, %')}${th('spread_bp','Спред, б.п.')}<th class="l">Оценка</th></tr></thead><tbody>`+
    rows.map(b=>`<tr data-isin="${esc(b.isin||b.id)}" style="cursor:pointer" title="Открыть карточку выпуска"><td class="l"><b>${esc(b.name||b.id)}</b><br><small class="mu">${esc(b.id)}</small></td><td class="num">${ofzN(b.dur)}</td><td class="num">${ofzN(b.yield)}</td><td class="num">${ofzN(b.kbd)}</td><td class="num ${b.flag==='cheap'?'pos':b.flag==='rich'?'neg':''}">${ofzSg(b.spread_bp,0)}</td><td class="l">${fl(b)}</td></tr>`).join('')+`</tbody></table></div>`;
}
function pOfz(){
  const O=S.ofz;
  if(!O.data&&!O.loading&&!O.err)ofzLoad();
  if(O.loading&&!O.data)return`<div class="card">${waitBox('Считаю наклон и кривизну КБД, сравниваю выпуски ОФЗ с кривой…')}</div>`;
  if(O.err)return`<div class="msg err">${esc(O.err)} <button class="btn ghost ofz-retry">Повторить</button></div>`;
  const d=O.data;if(!d)return'';
  if(!d.ok)return`<div class="msg err">${esc(d.error||'Нет данных')} <button class="btn ghost ofz-retry">Повторить</button></div>`;
  const bs=d.bonds||[],cheap=bs.filter(b=>b.flag==='cheap').length,rich=bs.filter(b=>b.flag==='rich').length;
  chart('c-ofz-curve',ofzCurveChart,{curve:d.curve||[],bonds:bs});
  chart('c-ofz-tp',ofzTpChart,{tp:d.tp||[]});
  const stName={bullet:'bullet выгоднее',barbell:'barbell выгоднее',neutral:'почти без разницы'};
  const bb=d.bullet!=null&&d.barbell!=null?d.bullet-d.barbell:null;
  return`<div class="g g4">
    <div class="card kpi"><div class="k">Наклон 10 лет − 2 года</div><div class="v num ${d.slope==null?'':d.slope<0?'pos':''}">${d.slope==null?'—':ofzSg(d.slope)+' п.п.'}</div><div class="s">${d.regime?`<span class="ofz-b ${ofzRegCls(d.regime_code)}">${esc(d.regime)}</span>`:'&nbsp;'}</div></div>
    ${kpi('Кривизна кривой',d.curvature==null?'—':ofzSg(d.curvature)+' п.п.',d.structure?esc(stName[d.structure]||''):'')}
    ${kpi('Bullet vs barbell',d.bullet==null?'—':ofzN(d.bullet)+' % / '+ofzN(d.barbell)+' %','bullet 5 лет · barbell 1+10 лет'+(bb==null?'':' ('+ofzSg(bb)+' п.п.)'))}
    ${kpi('Премия за год срока, 3–10 лет',d.tp_3_10_avg==null?'—':ofzBp(d.tp_3_10_avg)+' / год',d.tp_3_10_avg==null?'':d.tp_3_10_avg<10?'удлинение почти не оплачивается':'удлинение оплачивается',d.tp_3_10_avg==null?null:d.tp_3_10_avg<10?'neg':'pos')}</div>
  ${d.note?`<div class="msg info" style="margin-top:12px">${esc(d.note)}</div>`:''}
  <div class="card ofz-verdict"><h2>Вывод по кривой<span class="sp">на ${esc(d.asof||'')}</span></h2><p>${esc(d.verdict||'')}</p>${d.regime_note?`<p class="mu">${esc(d.regime_note)}</p>`:''}${d.barbell_note?`<p class="mu">${esc(d.barbell_note)}</p>`:''}</div>
  <div class="g c-2-1 ofz-mid" style="margin-top:16px">
    <div class="card"><h2>КБД и выпуски ОФЗ<span class="sp">точка = ОФЗ-ПД; зелёная дешевле кривой, красная дороже</span></h2><div id="c-ofz-curve" class="chart"></div></div>
    <div class="card"><h2>Премия за каждый год срока<span class="sp">прирост КБД, б.п.</span></h2><div id="c-ofz-tp" class="chart"></div></div></div>
  <div class="card" style="margin-top:16px"><h2>ОФЗ с постоянным купоном<span class="sp">дешевле кривой: ${cheap} · дороже: ${rich} · всего: ${bs.length}</span></h2>${bs.length?ofzTable(bs):'<div class="empty" style="padding:24px">Список выпусков временно недоступен.</div>'}</div>
  <p class="note">${esc(d.disclaimer||'')} Флоатеры (ОФЗ-ПК), линкеры (ОФЗ-ИН) и выпуски короче 3 месяцев не учитываются. Спред — разница доходности выпуска и КБД на его дюрации; порог «дешевле / дороже» — ±15 б.п.</p>`;
}
function bindOfz(){
  document.querySelectorAll('#view .ofz-retry').forEach(b=>b.onclick=()=>{S.ofz.err='';S.ofz.data=null;ofzLoad(true);render()});
  document.querySelectorAll('#view [data-ofz-s]').forEach(h=>h.onclick=()=>{const O=S.ofz,k=h.dataset.ofzS;if(O.sk===k)O.sd=-O.sd;else{O.sk=k;O.sd=k==='name'?1:-1}render()});
}
regPage('ofz',{title:'ОФЗ-Спредер',group:'Рынок',icon:'<path d="M3 18c4 0 5-9 9-9s5 4 9 4"/><path d="M3 21h18"/><circle cx="8" cy="12" r="1.4"/><circle cx="15" cy="9" r="1.4"/>',render:pOfz,bind:bindOfz,pro:true});
if(typeof renderNav==='function')try{renderNav()}catch(e){}
document.addEventListener('click',e=>{if(e.target.closest&&e.target.closest('.ofz-go'))go('ofz')});
