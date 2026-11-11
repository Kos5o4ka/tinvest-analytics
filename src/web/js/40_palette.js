/* ── инкогнито и палитра команд (Ctrl+K / Cmd+K) ── */
function setIncog(on){
  INCOG.on=!!on;lsSet('ta_incog',on?'1':'0');
  const e=$('#eye');e.classList.toggle('on',INCOG.on);e.title=INCOG.on?'Показать суммы':'Скрыть суммы в деньгах';
  renderAccounts();renderNav();
  if(S.data||['set','imp'].includes(S.page))renderNow();
  toast(INCOG.on?'Суммы скрыты':'Суммы показаны');
}
$('#eye').onclick=()=>setIncog(!INCOG.on);
$('#eye').classList.toggle('on',INCOG.on);
$('#srch').onclick=()=>kpOpen();

const KP={open:false,items:[],sel:0};
const kpNorm=s=>String(s||'').toLowerCase().replace(/ё/g,'е');
/* слова запроса должны встретиться в тексте целиком или (для коротких заголовков) как подпоследовательность */
function kpScore(text,q){
  const t=kpNorm(text);if(!q)return 1;
  let sc=0;
  for(const w of q.split(/\s+/).filter(Boolean)){
    const i=t.indexOf(w);
    if(i>=0){sc+=i===0?3:(t[i-1]===' '?2:1);continue}
    let j=0;for(const ch of t){if(ch===w[j])j++;if(j===w.length)break}
    if(w.length>=3&&j===w.length)sc+=0.3;else return 0;
  }
  return sc;
}
function kpCommands(){
  return[
    {g:'Команды',t:'Обновить данные',k:'обновить данные перезагрузить refresh',run:()=>load(true)},
    {g:'Команды',t:'Экспорт PDF (печать)',k:'экспорт pdf печать',run:()=>window.print()},
    {g:'Команды',t:INCOG.on?'Показать суммы':'Скрыть суммы (инкогнито)',k:'инкогнито скрыть суммы показать',run:()=>setIncog(!INCOG.on)},
    {g:'Команды',t:'Сменить тему',k:'тема оформление светлая тёмная',run:()=>$('#thm').click()}];
}
function kpSecurities(q){
  const out=[],seen=new Set();
  const add=(name,ticker,isin,sub,run)=>{
    const key=isin||ticker||name;if(seen.has(key))return;
    const sc=Math.max(kpScore(name,q),kpScore(ticker,q),kpScore(isin,q));if(!sc)return;
    seen.add(key);out.push({g:'Бумаги',t:name||ticker||isin,s:[ticker,isin,sub].filter(Boolean).join(' · '),sc,run});
  };
  const openB=isin=>()=>{if(typeof openBond==='function')openBond(isin)};
  if(S.bonds&&S.bonds.rows)S.bonds.rows.forEach(r=>add(r.name,r.ticker,r.isin,'в портфеле',r.isin?openB(r.isin):()=>go('bonds')));
  const ps=S.data&&S.data.portfolio&&S.data.portfolio.positions;
  if(ps)ps.forEach(p=>{if(p.type==='currency')return;add(p.name,p.ticker,p.isin||'', 'в портфеле',p.type==='bond'&&p.isin?openB(p.isin):()=>go(p.type==='bond'?'bonds':'pos'))});
  if(q.length>=2&&S.scr&&S.scr.rows){
    let n=0;for(const r of S.scr.rows){if(n>=8)break;const i=r.isin||r.id;if(seen.has(i))continue;
      const before=out.length;add(r.name,r.id,i,'каталог',openB(i));if(out.length>before)n++}
  }
  return out.sort((a,b)=>b.sc-a.sc).slice(0,12);
}
function kpBuild(raw){
  const q=kpNorm(raw).trim(),res=[];
  kpCommands().forEach(c=>{const sc=kpScore(c.t+' '+c.k,q);if(sc)res.push(Object.assign({sc},c))});
  PAGES.filter(Boolean).forEach(p=>{const sc=kpScore(p[1],q);if(sc)res.push({g:'Разделы',t:p[1],sc,s:S.navHidden.includes(p[0])&&!NAV_PINNED.includes(p[0])?'скрыт в меню':'',run:()=>go(p[0])})});
  if(q)KB.forEach((a,i)=>{const tk=kpNorm(a.t+' '+a.k),sc=q.split(/\s+/).filter(Boolean).every(w=>tk.includes(w))?kpScore(a.t+' '+a.k,q):0;if(sc)res.push({g:'База знаний',t:a.t,s:a.c,sc,run:()=>kbOpen(a.id)})});
  if(q)res.push(...kpSecurities(q));
  const order={'Команды':q?1:0,'Разделы':q?0:1,'База знаний':2,'Бумаги':3};
  res.sort((a,b)=>order[a.g]-order[b.g]||(q?b.sc-a.sc:0));
  return res.slice(0,40);
}
function kpDraw(){
  const l=$('#kp-l');let g='',h='';
  KP.items.forEach((it,i)=>{
    if(it.g!==g){g=it.g;h+=`<div class="kp-h">${esc(g)}</div>`}
    h+=`<button data-i="${i}" class="${i===KP.sel?'on':''}"><span>${esc(it.t)}</span>${it.s?`<small>${esc(it.s)}</small>`:''}</button>`;
  });
  l.innerHTML=h||'<div class="kp-e">Ничего не найдено</div>';
  const on=l.querySelector('button.on');if(on)on.scrollIntoView({block:'nearest'});
}
function kpOpen(){
  if(KP.open)return;KP.open=true;
  const o=document.createElement('div');o.id='kp-ov';
  o.innerHTML='<div id="kp" role="dialog" aria-label="Поиск"><input id="kp-q" placeholder="Раздел, бумага, ISIN или команда…" autocomplete="off" spellcheck="false"><div id="kp-l"></div><div id="kp-f">↑↓ выбор · Enter открыть · Esc закрыть</div></div>';
  document.body.appendChild(o);
  o.addEventListener('mousedown',e=>{if(e.target===o)kpClose()});
  o.querySelector('#kp-l').addEventListener('click',e=>{const b=e.target.closest('[data-i]');if(b)kpRun(+b.dataset.i)});
  const q=$('#kp-q');
  q.oninput=()=>{KP.items=kpBuild(q.value);KP.sel=0;kpDraw()};
  KP.items=kpBuild('');KP.sel=0;kpDraw();q.focus();
}
function kpClose(){KP.open=false;const o=$('#kp-ov');if(o)o.remove()}
function kpRun(i){const it=KP.items[i];if(!it)return;kpClose();it.run()}
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&!e.altKey&&(e.key==='k'||e.key==='K'||e.code==='KeyK')){e.preventDefault();KP.open?kpClose():kpOpen();return}
  if(!KP.open)return;
  if(e.key==='Escape'){e.preventDefault();e.stopPropagation();kpClose()}
  else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const n=KP.items.length;if(n){KP.sel=(KP.sel+(e.key==='ArrowDown'?1:n-1))%n;kpDraw()}}
  else if(e.key==='Enter'){e.preventDefault();kpRun(KP.sel)}
},true);
