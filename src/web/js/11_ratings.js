/* ── кредитные рейтинги ── */
const RSC=['AAA','AA+','AA','AA-','A+','A','A-','BBB+','BBB','BBB-','BB+','BB','BB-','B+','B','B-','CCC','CC','C','D'];
const rBucket=v=>{if(!v)return'нет рейтинга';const i=RSC.indexOf(v);return i===0?'AAA':i<=3?'AA':i<=6?'A':i<=9?'BBB':'BB и ниже'};
/* Пресс-релиз по клику на тег рейтинга: только https и хосты агентств/Telegram */
const RT_HOSTS=['acra-ratings.ru','raexpert.ru','ratings.ru','ra-national.ru','t.me'];
function rtSafeUrl(u){
  try{const x=new URL(String(u||''));
    if(x.protocol!=='https:'||x.username||x.password)return'';
    const h=x.hostname.toLowerCase();
    return RT_HOSTS.some(d=>h===d||h.endsWith('.'+d))?x.href:'';
  }catch(e){return''}
}
function ratingTag(r,short){
  if(!r)return'';
  if(typeof r==='string')r={v:r,all:[]};
  const all=Array.isArray(r.all)?r.all:[];
  const links=all.map(x=>({a:x.agency,r:x.rating,o:x.outlook||'',d:x.date||'',u:rtSafeUrl(x.url)}));
  const has=links.some(x=>x.u);
  let t=all.map(x=>`${x.agency}: ${x.rating}${x.outlook?' · '+x.outlook:''} · от ${x.date} · ${x.issuer}${x.approx?' (приблизительное совпадение названия)':''}`).join('\n');
  if(has)t+=(t?'\n':'')+'Нажмите, чтобы открыть пресс-релиз';
  const n=Math.max(0,all.length-1),ag=short||!r.agency?'':` <small class="rt-ag">· ${esc(r.agency)}${n>0?' +'+n:''}</small>`;
  const act=has?` role="button" tabindex="0" data-rt="${esc(JSON.stringify(links))}"`:'';
  return`<span class="tag rt rt-${rBucket(r.v).split(' ')[0]}${has?' rt-click':''}" style="white-space:nowrap" title="${esc(t)}"${act}>${r.approx?'≈ ':''}${esc(r.v)}${ag}</span>`;
}
/* атрибуты кликабельного тега по готовому списку [{a,r,o,d,u}] — для таблиц, которые рисуют тег сами */
function rtClick(L){
  const links=(Array.isArray(L)?L:[]).map(x=>({a:x.a,r:x.r,o:x.o||'',d:x.d||'',u:rtSafeUrl(x.u)}));
  return links.some(x=>x.u)?{cls:' rt-click',attr:` role="button" tabindex="0" data-rt="${esc(JSON.stringify(links))}"`}:{cls:'',attr:''};
}
function rtPopClose(){const p=document.getElementById('rt-pop');if(p)p.remove()}
/* как обычная ссылка target=_blank: окно pywebview отдаёт такие в системный браузер, window.open там ненадёжен */
function rtOpenUrl(u){if(!(u=rtSafeUrl(u)))return;const a=document.createElement('a');a.href=u;a.target='_blank';a.rel='noopener noreferrer';a.style.display='none';document.body.appendChild(a);a.click();a.remove()}
function rtPopOpen(el){
  let L;try{L=JSON.parse(el.dataset.rt||'[]')}catch(e){L=[]}
  rtPopClose();
  const withUrl=L.filter(x=>x.u);
  if(!withUrl.length)return;
  if(L.length===1){rtOpenUrl(withUrl[0].u);return}
  const pop=document.createElement('div');pop.id='rt-pop';pop.setAttribute('role','dialog');
  pop.innerHTML=L.map(x=>{const xu=rtSafeUrl(x.u);return`<div class="rt-pop-r"><b>${esc(x.a)}</b><span>${esc(x.r)}${x.o?' · '+esc(x.o):''}${x.d?' · '+esc(typeof ddm==='function'&&/^\d{4}-/.test(x.d)?ddm(x.d):x.d):''}</span>${xu?`<a href="${esc(xu)}" target="_blank" rel="noopener noreferrer">Пресс-релиз ↗</a>`:'<span class="mu">нет ссылки</span>'}</div>`}).join('');
  document.body.appendChild(pop);
  const b=el.getBoundingClientRect(),w=pop.offsetWidth,h=pop.offsetHeight;
  pop.style.left=Math.max(8,Math.min(b.left,innerWidth-w-8))+'px';
  pop.style.top=(b.bottom+6+h>innerHeight-8?Math.max(8,b.top-h-6):b.bottom+6)+'px';
}
/* делегированные обработчики: рендеры перерисовывают DOM; capture + stopPropagation — клик по тегу не открывает карточку строки */
document.addEventListener('click',e=>{
  const el=e.target.closest&&e.target.closest('[data-rt]');
  if(el){e.preventDefault();e.stopPropagation();const open=document.getElementById('rt-pop');const same=open&&open._for===el;rtPopClose();if(!same){rtPopOpen(el);const p=document.getElementById('rt-pop');if(p)p._for=el}return}
  if(e.target.closest&&e.target.closest('#rt-pop a')){e.stopPropagation();setTimeout(rtPopClose,0);return}
  if(document.getElementById('rt-pop')&&!(e.target.closest&&e.target.closest('#rt-pop')))rtPopClose();
},true);
document.addEventListener('keydown',e=>{
  if(e.key==='Escape')rtPopClose();
  else if((e.key==='Enter'||e.key===' ')&&e.target.closest&&e.target.closest('[data-rt]')){e.preventDefault();e.stopPropagation();e.target.closest('[data-rt]').click()}
},true);
window.addEventListener('scroll',rtPopClose,true);
function ratingsCard(b){
  const info=b.ratings_info||{},tot=(b.ratings||[]).reduce((a,x)=>a+x[1],0)||1;
  const COL={'AAA':S3,'AA':S3,'A':S1,'BBB':S4,'BB и ниже':S8,'нет рейтинга':'#6f7686'};
  const order=['AAA','AA','A','BBB','BB и ниже','нет рейтинга'],m=Object.fromEntries(b.ratings||[]);
  const items=order.filter(k=>m[k]).map(k=>({n:k==='нет рейтинга'?'Нет данных':k,v:m[k],c:COL[k],s:pctp(m[k]/tot*100)}));
  const st=info.running?`Загружаю рейтинги… ${esc(info.progress||'')}`:info.updated?`Обновлено ${new Date(info.updated*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})} · эмитентов в базе: ${info.count}`:'Рейтинги ещё не загружены';
  if(info.running&&!S._rtTimer)S._rtTimer=setTimeout(async()=>{S._rtTimer=null;if(S.page!=='bonds')return;try{S.bonds=await api('/api/bonds?'+new URLSearchParams({account:S.account}));renderSoon()}catch(e){}},5000);
  return`<div class="card"><h2>Кредитные рейтинги эмитентов<span class="sp">${st}</span></h2>
    <div class="g g2"><div>${hbars(items,S1,null,0)}</div>
    <div class="t2" style="font-size:13px;line-height:1.6">Распределение облигаций портфеля по рейтингу по национальной шкале (АКРА, Эксперт РА, НКР, НРА). Если у эмитента несколько оценок, берётся наименьшая.
      Пометка «≈» — название эмитента совпало не полностью, проверьте по подсказке. Нет данных — рейтинг не найден в базе, это не значит, что он низкий.
      <div class="row" style="margin-top:12px"><button class="btn ghost" id="rt-ref" ${info.running?'disabled':''}>Обновить рейтинги</button></div></div></div>
    <p class="note">Источник — публичный канал @issuerRatings (пресс-релизы агентств). Рейтинги обновляются автоматически раз в сутки при открытой программе. Не является инвестиционной рекомендацией.</p></div>`;
}


function bondInsights(b){
  const rows=b.rows.filter(r=>r.value_rub>0),tot=rows.reduce((a,r)=>a+r.value_rub,0)||1,out=[];
  const w=(f)=>rows.filter(f).reduce((a,r)=>a+r.value_rub,0)/tot*100;
  const sp=rows.filter(r=>r.spread!=null),spv=sp.reduce((a,r)=>a+r.value_rub,0);
  if(spv)out.push(['Спред к КБД',`В среднем портфель даёт <b>${(sp.reduce((a,r)=>a+r.spread*r.value_rub,0)/spv).toFixed(2).replace('.',',')} п.п.</b> к безрисковой кривой (КБД) при той же дюрации — это ваша плата за кредитный риск и неликвидность.`]);
  const low=sp.filter(r=>r.spread<0.5).sort((a,c)=>a.spread-c.spread);
  if(low.length)out.push(['Мало платят за риск',`Выше КБД менее чем на 0,5 п.п.: ${low.slice(0,4).map(r=>`${esc(r.name)} (${r.spread>0?'+':''}${r.spread.toFixed(2).replace('.',',')} п.п.)`).join(', ')}${low.length>4?' и ещё '+(low.length-4):''}. Проверьте, оправдан ли риск эмитента или выгоднее ОФЗ.`]);
  const nr=w(r=>!r.rating);if(nr>0.5)out.push(['Без рейтинга',`<b>${nr.toFixed(0)}%</b> облигационной части — выпуски без найденного рейтинга агентств (${rows.filter(r=>!r.rating).slice(0,3).map(r=>esc(r.name)).join(', ')}${rows.filter(r=>!r.rating).length>3?'…':''}). Рейтинга нет в базе — это не значит, что он низкий.`]);
  const weak=rows.filter(r=>r.rating&&RSC.indexOf(r.rating.v)>=7);
  if(weak.length)out.push(['Рейтинг ниже A−',`${weak.map(r=>`${esc(r.name)} (${esc(r.rating.v)})`).join(', ')} — суммарно <b>${w(r=>r.rating&&RSC.indexOf(r.rating.v)>=7).toFixed(0)}%</b> облигаций.`]);
  const hy=sp.filter(r=>r.spread>6);if(hy.length)out.push(['Очень высокая доходность',`Спред больше 6 п.п.: ${hy.map(r=>`${esc(r.name)} (+${r.spread.toFixed(1).replace('.',',')})`).join(', ')}. Рынок закладывает повышенный риск — перепроверьте эмитента.`]);
  const top=rows.slice().sort((a,c)=>c.value_rub-a.value_rub).slice(0,3);
  out.push(['Концентрация',`Три крупнейшие позиции — <b>${(top.reduce((a,r)=>a+r.value_rub,0)/tot*100).toFixed(0)}%</b> облигаций: ${top.map(r=>esc(r.name)).join(', ')}.`]);
  const soon=localIso(new Date(Date.now()+90*864e5)),today=localIso();
  const inW=d=>d&&d>=today&&d<=soon,KN={put:'пут-оферта',call:'колл',both:'пут и колл',unknown:'оферта, тип не указан'};
  const ev=rows.filter(r=>inW(r.call)||inW(r.maturity));
  if(ev.length)out.push(['Ближайшие 90 дней',`Оферта или погашение: ${ev.map(r=>inW(r.call)?`${esc(r.name)} — ${ddm(r.call)} (${KN[r.call_kind]||KN.unknown})`:`${esc(r.name)} — ${ddm(r.maturity)}`).join('; ')}. Это только ближайшие даты: все оферты и их тип — на странице «Оферты». <a href="#" class="kb-a" data-kb="offers">Что такое put и call</a>.`]);
  return out;
}
function insightsCard(b){
  const L=bondInsights(b);if(!L.length)return'';
  return`<div class="card"><h2>Анализ облигаций портфеля</h2><div class="ins">${L.map(([t,h])=>`<div><b>${t}</b><span>${h}</span></div>`).join('')}</div>
    <p class="note">Автоматические наблюдения по данным портфеля, рейтингов и КБД. Это справочная информация, а не инвестиционная рекомендация.</p></div>`;
}

