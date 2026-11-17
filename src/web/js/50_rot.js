/* ── Флоатеры или фиксы: модельная ротация ── */
S.rot={d:null,err:null,busy:false,gap:null,gapBusy:false,tm:0,
  p:{spread:'2',tax:'1',bond:'',b_long:'0.5',b_mid:'0.7',b_short:'0.9',scn:'',amount:'1000000',n:'6',mode:'equal',goal:'3'}};
const ROT_INFO={fixed:'фикс',float:'флоатер'};
function rotQs(){const p=S.rot.p,o={};['spread','tax','bond','b_long','b_mid','b_short','scn','amount','n','mode'].forEach(k=>{if(p[k]!=='')o[k]=String(p[k]).replace(',','.')});return new URLSearchParams(o).toString()}
function rotLoad(){
  const R=S.rot;clearTimeout(R.tm);R.busy=true;
  api('/api/rot?'+rotQs()).then(j=>{
    if(j.loading){R.tm=setTimeout(()=>{if(S.page==='rot')rotLoad()},2500);if(S.page==='rot')renderSoon();return}
    R.busy=false;R.err=j.error||null;if(!j.error){R.d=j;if(!R.p.bond)R.p.bond=j.bond.id;if(!R.p.scn)R.p.scn=j.lag.scn}
    if(S.page==='rot')renderSoon();
  }).catch(e=>{R.busy=false;R.err=e.message;if(S.page==='rot')renderSoon()});
}
function rotGapLoad(){
  const R=S.rot;R.gapBusy=true;
  api('/api/rot/gap?horizon='+encodeURIComponent(String(R.p.goal).replace(',','.'))).then(j=>{R.gap=j;R.gapBusy=false;if(S.page==='rot')renderSoon()})
    .catch(e=>{R.gap={empty:true,error:e.message};R.gapBusy=false;if(S.page==='rot')renderSoon()});
}
const rotF=(v,d=2)=>v==null||isNaN(v)?'—':(+v).toFixed(d).replace('.',',');
const rotSg=(v,d=2)=>v==null||isNaN(v)?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(d).replace('.',',');
function rotMatrix(d){
  const mx=Math.max(1,...d.matrix.flatMap(r=>r.cells.map(c=>c&&c.diff!=null?Math.abs(c.diff):0)));
  return`<div class="tbl"><table class="hm rot-hm"><thead><tr><th class="l">Сценарий ключевой ставки</th>${d.horizons.map(h=>`<th>${esc(h.label)}</th>`).join('')}</tr></thead><tbody>${d.matrix.map(r=>
    `<tr><td class="y l"><b>${esc(r.name)}</b><br><small class="mu">${esc(r.note)}</small></td>${r.cells.map(c=>{
      if(!c)return`<td class="mu" title="${r.avail?'':'Прогноз недоступен'}">—</td>`;
      const k=c.diff==null?0:Math.round(14+Math.min(1,Math.abs(c.diff)/mx)*36);
      return`<td class="rot-c ${c.win==='fixed'?'rot-fx':c.win==='float'?'rot-fl':''}" style="--k:${k}%" title="${esc(c.win==='fixed'?'фикс выше':'флоатер выше')}: разница ${rotSg(c.diff)} п.п."><b>${rotF(c.fixed,1)}</b> / ${rotF(c.float,1)}</td>`}).join('')}</tr>`).join('')}</tbody></table></div>
  <p class="note"><span class="rot-key rot-fx"></span> выше доходность фикса &nbsp; <span class="rot-key rot-fl"></span> выше доходность флоатера. В ячейке: <b>фикс</b> / флоатер, % годовых (полная доходность${S.rot.d.tax?', после НДФЛ 13%':', до налогов'}).${d.forecast_ok?'':' Источник прогноза ЦБ сейчас недоступен — строка «Прогноз ЦБ» не рассчитана.'}</p>`;
}
function rotBreakeven(d){
  return`<div class="tbl"><table><thead><tr><th class="l">Горизонт</th><th>Снижение ставки за год, п.п.</th><th class="l">Вывод по модели</th></tr></thead><tbody>${d.breakeven.map(b=>{
    const t=b.state==='ok'?`Фикс обгоняет флоатер, если ставка снизится больше чем на <b>${rotF(b.value,1)} п.п.</b>`:b.state==='always'?`Фикс впереди даже при росте ставки на ${rotF(-b.value,0)} п.п.`:b.state==='never'?`Даже при снижении ставки до ${rotF(d.floor,0)} % фикс не догоняет флоатер`:'Не рассчитано';
    return`<tr><td class="l"><b>${esc(b.label)}</b></td><td class="num">${b.state==='ok'?rotF(b.value,1):'—'}</td><td class="l">${t}</td></tr>`}).join('')}</tbody></table></div>
  <p class="note">Снижение — параллельное, равномерно в течение первого года, затем ставка остаётся на достигнутом уровне; нижняя граница ставки — ${rotF(d.floor,0)} %.</p>`;
}
function rotIndicator(d){
  const i=d.indicator;if(!i)return`<p class="mu">Кривая бескупонной доходности (КБД) недоступна — индикатор не рассчитан.</p>`;
  return`<div class="rot-ind"><div class="rot-gauge"><i style="left:${i.score}%"></i></div><div class="rot-sc"><b>${rotF(i.score,0)}</b><small> из 100</small></div></div>
    <p>${esc(i.label)}</p>
    <div class="tbl"><table><tbody><tr><td class="l">Ключевая ставка</td><td class="num">${rotF(i.key)} %</td></tr><tr><td class="l">КБД 1 год</td><td class="num">${rotF(i.kbd1)} %</td></tr><tr><td class="l">КБД 10 лет</td><td class="num">${rotF(i.kbd10)} %</td></tr>
    <tr><td class="l">A = КБД 10 лет − ключевая</td><td class="num">${rotSg(i.a)} п.п.</td></tr><tr><td class="l">S = КБД 10 лет − КБД 1 год</td><td class="num">${rotSg(i.s)} п.п.</td></tr></tbody></table></div>
    <p class="note">Формула: индикатор = 50 + 4 × A + 3 × S, где A ограничено ±8 п.п., S ограничено ±6 п.п.; результат в пределах 0–100. Он описывает форму кривой: насколько длинные ставки выше ключевой и насколько кривая крута. Это справочная характеристика рынка, а не сигнал к сделке.</p>`;
}
function rotLadder(d){
  const L=d.ladder;
  return`<div class="tbl"><table><thead><tr><th class="l">Дата заседания</th><th>Доля транша</th><th>Сумма</th><th>Всего в фиксе</th><th>Дюрация портфеля, лет</th></tr></thead><tbody>${L.rows.map(r=>
    `<tr><td class="l">${ddm(r.date)}${L.approx_dates?' <small class="mu">≈</small>':''}</td><td class="num">${rotF(r.share,1)} %</td><td class="num">${M(r.rub,'rub',0)}</td><td class="num">${rotF(r.cum_share,1)} %</td><td class="num"><b>${rotF(r.duration)}</b></td></tr>`).join('')}</tbody></table></div>
  <p class="note">Модельный план: сумма во флоатерах переводится в выбранную фиксированную ОФЗ траншами в даты заседаний Банка России${L.approx_dates?' (часть дат ориентировочная — календарь ЦБ получен не полностью)':''}. Дюрация фикса ${rotF(L.d_fixed)} лет, флоатера — ${rotF(L.d_float)} года. Это иллюстрация расчёта, а не рекомендация по срокам и долям.</p>`;
}
function rotLag(d){
  const rs=d.lag.rows,nm=(d.scenarios.find(s=>s.key===d.lag.scn)||{}).name||'';
  if(!rs.length)return`<p class="mu">Нет данных по флоатерам.</p>`;
  return`<div class="tbl" style="max-height:480px"><table><thead><tr><th class="l">Выпуск</th><th class="l">Привязка</th><th>Купон сейчас, %</th><th>Следующие купоны по модели, %</th><th>Средний купон 12 мес</th><th>Текущая доходность по купону</th><th>Через 12 мес по модели</th><th>Изменение, п.п.</th></tr></thead><tbody>${rs.map(r=>
    `<tr><td class="l"><b>${esc(r.name)}</b><br><small class="mu num">${esc(r.isin||r.id)}</small></td><td class="l"><small>${esc(r.link)}</small></td><td class="num">${rotF(r.coupon)}</td><td class="num">${r.future.map(x=>rotF(x)).join(' → ')||'—'}</td><td class="num">${rotF(r.avg12)}</td><td class="num">${rotF(r.cy_now)}</td><td class="num">${rotF(r.cy_fwd)}</td><td class="num ${r.delta<0?'neg':'pos'}">${rotSg(r.delta)}</td></tr>`).join('')}</tbody></table></div>
  <p class="note">Сценарий: ${esc(nm)}. Купон КС-флоатера определяется ставкой на начало купонного периода, купон RUONIA-флоатера — средней за период со сдвигом около 7 дней назад, поэтому купоны реагируют на изменение ставки с задержкой. Спред к ставке оценён как текущий купон минус текущая ставка; период купона принят 6 месяцев для ОФЗ и 3 месяца для корпоративных; выпуски с привязкой к инфляции исключены, а если база купона неизвестна, считается по правилу КС.</p>`;
}
function rotGap(){
  const R=S.rot,g=R.gap;
  if(R.gapBusy&&!g)return waitBox('Считаю дюрацию портфеля…');
  if(!g)return`<button class="btn ghost" id="rot-gap-go">Рассчитать по моему портфелю</button>`;
  if(g.empty)return`<p class="mu">${esc(g.error||'В портфеле нет облигаций с данными для расчёта (в демо-режиме или без токена расчёт недоступен).')}</p><button class="btn ghost" id="rot-gap-go">Повторить</button>`;
  return`<div class="row" style="gap:20px;flex-wrap:wrap"><div><small class="mu">Дюрация портфеля облигаций</small><br><b style="font-size:20px">${rotF(g.duration)} лет</b></div>
    <div><small class="mu">Цель</small><br><b style="font-size:20px">${rotF(g.goal,1)} лет</b></div>
    <div><small class="mu">Разрыв</small><br><b style="font-size:20px" class="${Math.abs(g.gap)>0.5?'neg':'pos'}">${rotSg(g.gap)} года</b></div>
    <div><small class="mu">Флоатеры в портфеле</small><br><b style="font-size:20px">${rotF(g.floating_share,0)} %</b></div></div>
    <p>${esc(g.gap_text)}</p>
    <div class="tbl"><table><thead><tr><th class="l">Сценарий сдвига доходностей</th><th>Изменение стоимости</th><th>В рублях</th></tr></thead><tbody>${g.scenarios.map(s=>
      `<tr><td class="l">${esc(s.name)}</td><td class="num ${s.pct<0?'neg':'pos'}">${rotSg(s.pct)} %</td><td class="num">${M(s.rub,'rub',0)}</td></tr>`).join('')}</tbody></table></div>
    <p class="note">Оценка по модифицированной дюрации и выпуклости: ΔV/V ≈ −D·Δy + C·Δy²/2. Флоатеры приняты с дюрацией около 0,25 года. Изменение «длинного конца» применяется с весом от 0 (дюрация до 2 лет) до 1 (дюрация от 10 лет). Кредитный спред и реинвестирование не учитываются.</p>
    <button class="btn ghost" id="rot-gap-go">Пересчитать</button>`;
}
function pRot(){
  const R=S.rot,d=R.d,p=R.p;
  if(!d&&!R.err&&!R.busy)rotLoad();
  if(R.err&&!d)return`<div class="msg err">${esc(R.err)} <button class="btn ghost" id="rot-retry">Повторить</button></div>`;
  if(!d)return`<div class="card">${waitBox('Загружаю торги ОФЗ, кривую КБД и прогноз ключевой ставки…')}</div>`;
  const opt=(v,t,cur)=>`<option value="${esc(v)}" ${String(cur)===String(v)?'selected':''}>${esc(t)}</option>`;
  const b=d.bond;
  return`<div class="card"><h2>Флоатеры или фиксы<span class="sp">${R.busy?'пересчитываю…':'ключевая ставка '+rotF(d.key_rate)+' %'}</span></h2>
    <p class="mu">Модель сравнивает полную доходность флоатера (купон = ставка + спред) и фиксированной ОФЗ при разных траекториях ключевой ставки.</p>
    <div class="flt">
      <label class="field"><span>Спред флоатера к ставке, п.п.</span><input class="in num" id="rot-spread" value="${esc(p.spread)}" inputmode="decimal"></label>
      <label class="field"><span>Фиксированная ОФЗ</span><select class="in" id="rot-bond">${d.bonds.map(x=>opt(x.id,`${x.name} · до ${ddm(x.mat)} · ${rotF(x.yield,1)} %`,p.bond)).join('')}</select></label>
      <label class="field"><span>β: срок больше 5 лет</span><input class="in num" id="rot-bl" value="${esc(p.b_long)}" inputmode="decimal"></label>
      <label class="field"><span>β: 2–5 лет</span><input class="in num" id="rot-bm" value="${esc(p.b_mid)}" inputmode="decimal"></label>
      <label class="field"><span>β: меньше 2 лет</span><input class="in num" id="rot-bs" value="${esc(p.b_short)}" inputmode="decimal"></label>
      <label class="sw"><input type="checkbox" id="rot-tax" ${p.tax==='1'?'checked':''}><i></i><div><b>НДФЛ 13%</b><small>с купонов и положительной переоценки</small></div></label>
      <button class="btn" id="rot-go">Пересчитать</button></div>
    <p class="note">Допущения. Флоатер: купон = ключевая ставка на начало квартала + спред, цена около номинала. Фикс — ${esc(b.name)} (погашение ${ddm(b.mat)}, цена ${rotF(b.price)} %, доходность ${rotF(b.yield)} %): к горизонту доходность сдвигается на β × изменение ключевой ставки (β для этой бумаги — ${rotF(b.beta,1)}), цена пересчитывается полностью по оставшимся потокам. Метод: ${esc(d.method)}. Купоны реинвестируются по средней ставке сценария. Курсовой эффект спреда флоатера и комиссии не учитываются.</p></div>
  <div class="card"><h2>Сценарии и горизонты</h2>${rotMatrix(d)}</div>
  <div class="card"><h2>Точка безубыточности</h2>${rotBreakeven(d)}</div>
  <div class="card"><h2>Индикатор формы кривой</h2>${rotIndicator(d)}</div>
  <div class="card"><h2>Модельный план перекладки</h2>
    <div class="flt"><label class="field"><span>Сумма во флоатерах, ₽</span><input class="in num" id="rot-amt" value="${esc(p.amount)}" inputmode="decimal"></label>
      <label class="field"><span>Число траншей (заседаний)</span><input class="in num" id="rot-n" value="${esc(p.n)}" inputmode="numeric"></label>
      <label class="field"><span>Распределение</span><select class="in" id="rot-mode">${opt('equal','Равными долями',p.mode)}${opt('front','Больше в начале',p.mode)}</select></label>
      <button class="btn ghost" id="rot-go2">Пересчитать</button></div>${rotLadder(d)}</div>
  <div class="card"><h2>Лаг фиксации купонов флоатеров</h2>
    <div class="flt"><label class="field"><span>Сценарий ставки</span><select class="in" id="rot-scn">${d.scenarios.filter(s=>s.key!=='cbr'||d.forecast_ok).map(s=>opt(s.key,s.name,p.scn||d.lag.scn)).join('')}</select></label></div>${rotLag(d)}</div>
  <div class="card"><h2>Дюрационный разрыв портфеля</h2>
    <div class="flt"><label class="field"><span>Горизонт цели, лет</span><input class="in num" id="rot-goal" value="${esc(p.goal)}" inputmode="decimal"></label></div>${rotGap()}</div>
  <p class="note">Все результаты — расчёты по модели при заданных допущениях; реальные траектории ставок, спреды и ликвидность будут другими. Прогноз ключевой ставки: ${esc(d.forecast_src||'нет данных')}. Расчёт не учитывает кредитный риск эмитентов, комиссии и налоговые льготы (ЛДВ, ИИС).${(d.errors||[]).length?' Часть данных получить не удалось: '+esc(d.errors.join('; '))+'.':''}</p>${NIR_NOTE}`;
}
function bindRot(){
  const R=S.rot,p=R.p,$$=id=>document.getElementById(id);
  const rb=$$('rot-retry');if(rb)rb.onclick=()=>{R.err=null;R.d=null;renderSoon()};
  if(!R.d)return;
  const read=()=>{p.spread=$$('rot-spread').value;p.bond=$$('rot-bond').value;p.b_long=$$('rot-bl').value;p.b_mid=$$('rot-bm').value;p.b_short=$$('rot-bs').value;p.tax=$$('rot-tax').checked?'1':'0';
    p.amount=$$('rot-amt').value;p.n=$$('rot-n').value;p.mode=$$('rot-mode').value;p.scn=$$('rot-scn').value;p.goal=$$('rot-goal').value};
  const go=()=>{read();rotLoad();renderSoon()};
  ['rot-go','rot-go2'].forEach(id=>{const e=$$(id);if(e)e.onclick=go});
  ['rot-bond','rot-tax','rot-mode','rot-scn'].forEach(id=>{const e=$$(id);if(e)e.onchange=go});
  ['rot-spread','rot-bl','rot-bm','rot-bs','rot-amt','rot-n'].forEach(id=>{const e=$$(id);if(e)e.onkeydown=ev=>{if(ev.key==='Enter')go()}});
  const g=$$('rot-gap-go');if(g)g.onclick=()=>{read();R.gap=null;rotGapLoad();renderSoon()};
  const gi=$$('rot-goal');if(gi)gi.onkeydown=ev=>{if(ev.key==='Enter'){read();R.gap=null;rotGapLoad();renderSoon()}};
}
regPage('rot',{title:'Флоатеры или фиксы',group:'Рынок',icon:'<path d="M3 17c4 0 4-10 9-10s5 10 9 10"/><path d="M3 12h18"/>',render:pRot,bind:bindRot,pro:true});
