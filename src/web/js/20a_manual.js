/* ── Ручной учёт: добавить сделку, позицию или внебиржевой актив (вклад / наличные / недвижимость) ── */
const MAN={rows:[],accounts:[],pick:null};
const MAN_KINDS=[['buy','Покупка'],['sell','Продажа'],['coupon','Купон'],['dividend','Дивиденд'],['deposit','Пополнение'],['withdraw','Вывод'],['fee','Комиссия, обслуживание']];
const MAN_TYPE={buy:'buy',sell:'sell',coupons:'coupon',dividends:'dividend',deposits:'deposit',withdrawals:'withdraw',fee_service:'fee',fee_broker:'fee'};
const MAN_EXT_KINDS=[['deposit','Вклад'],['cash','Наличные'],['realty','Недвижимость']];
function manNum(v){const x=parseFloat(String(v==null?'':v).replace(/\s/g,'').replace(',','.'));return isFinite(x)?x:0}
function manClose(){const o=document.getElementById('man-ov');if(o)o.remove()}
async function manualOpen(row){
  manClose();
  let accs=[];
  try{accs=(await api('/api/ops/manual')).accounts}catch(e){toast(e.message,'err');return}
  const ed=row||null;MAN.pick=ed?{ident:ed.ident,ticker:'',name:ed.name}:null;
  const isExt=!!(ed&&ed.ident&&/^EXT:/i.test(ed.ident));
  const extKindInit=isExt?(String(ed.ident).split(':')[1]||'DEPOSIT').toLowerCase():'deposit';
  const kind=ed?(MAN_TYPE[ed.type]||'buy'):'buy';
  const ov=document.createElement('div');ov.id='man-ov';ov.className='shr-bg';
  ov.innerHTML=`<div class="card" role="dialog" aria-modal="true" aria-label="Ручная запись" style="width:min(660px,100%);max-height:92vh;overflow:auto">
    <h2>${ed?'Изменить запись':'Добавить сделку или актив'}<span class="sp"><button class="btn ghost" id="man-x" aria-label="Закрыть">Закрыть</button></span></h2>
    <p class="note">Запись становится обычной операцией счёта: доходность, налоги и графики считаются как по отчёту. Внебиржевые активы (вклады, наличные, недвижимость) учитываются в общем капитале.</p>${typeof DEMO!=='undefined'&&DEMO.on&&!ed?'<p class="note" style="color:var(--warn,#b7791f)">Сейчас включён демо-режим: первая ваша запись уберёт модельный портфель, останутся только ваши данные.</p>':''}
    <div class="seg" id="man-mode" style="margin:10px 0">
      <button data-m="op" class="${ed&&(ed.position||isExt)?'':'on'}">Операция</button>
      <button data-m="position" class="${ed&&ed.position&&!isExt?'on':''}">Позиция без истории</button>
      <button data-m="asset_ext" class="${isExt?'on':''}">Вклад / Наличные / Недвижимость</button>
    </div>
    <div class="g g3" style="gap:12px">
      <label class="field"><span>Счёт</span><select class="in" id="man-acc">${ed?'':'<option value="">Новый ручной счёт</option>'}${accs.map(a=>`<option value="${esc(a.id)}"${ed&&ed.acc===a.id?' selected':''}>${esc(a.name)}</option>`).join('')}</select></label>
      <label class="field" id="man-newname"><span>Название нового счёта</span><input class="in" id="man-accname" placeholder="Например: Другой брокер" value="Ручной счёт"></label>
      <label class="field" id="man-kindf"><span>Тип операции</span><select class="in" id="man-kind">${MAN_KINDS.map(([k,t])=>`<option value="${k}"${k===kind?' selected':''}>${t}</option>`).join('')}</select></label>
    </div>
    <div id="man-extbox" class="g g3" style="gap:12px;margin-top:12px;display:none">
      <label class="field"><span>Вид актива</span><select class="in" id="man-ext-kind">${MAN_EXT_KINDS.map(([k,t])=>`<option value="${k}"${k===extKindInit?' selected':''}>${t}</option>`).join('')}</select></label>
      <label class="field"><span>Название</span><input class="in" id="man-ext-name" placeholder="Например: Вклад в Сбере" value="${esc(isExt?ed.name:'')}"></label>
      <label class="field"><span>Валюта</span><select class="in" id="man-ext-cur">${['rub','usd','eur','cny'].map(c=>`<option value="${c}"${ed&&String(ed.currency||'rub').toLowerCase()===c?' selected':''}>${c.toUpperCase()}</option>`).join('')}</select></label>
    </div>
    <div id="man-secbox"><label class="field" style="margin-top:12px"><span>Бумага: тикер, ISIN или название</span><input class="in" id="man-q" placeholder="Например: SBER или ОФЗ 26238" autocomplete="off" value="${esc(ed&&!isExt?ed.name:'')}"></label>
      <div id="man-found" class="li" style="margin-top:6px"></div></div>
    <div class="g g3" style="gap:12px;margin-top:12px">
      <label class="field"><span>Дата</span><input class="in" type="date" id="man-date" value="${esc(ed?ed.date:localIso(new Date()))}"></label>
      <label class="field" id="man-qtyf"><span>Количество, шт.</span><input class="in" id="man-qty" inputmode="decimal" value="${ed&&ed.qty?esc(ed.qty):''}"></label>
      <label class="field" id="man-pricef"><span id="man-pricel">Цена за штуку, ₽</span><input class="in" id="man-price" inputmode="decimal" value="${ed&&ed.qty?esc(+(ed.amount/ed.qty).toFixed(4)):''}"></label>
      <label class="field" id="man-nkdf"><span>НКД, ₽ (облигации)</span><input class="in" id="man-nkd" inputmode="decimal"></label>
      <label class="field"><span id="man-amountl">Сумма, ₽</span><input class="in" id="man-amount" inputmode="decimal" value="${ed?esc(ed.amount):''}"></label>
      <label class="field" id="man-commf"><span>Комиссия, ₽</span><input class="in" id="man-comm" inputmode="decimal" value="${ed&&ed.commission?esc(ed.commission):''}"></label>
    </div>
    <label class="row" id="man-cashf" style="margin-top:12px;gap:8px;align-items:center"><input type="checkbox" id="man-cash"${!ed||ed.autocash?' checked':''}><span>Учесть пополнение под покупку: деньги на счёте не уйдут в минус</span></label>
    <div class="msg err" id="man-err" style="display:none;margin-top:10px"></div>
    <div class="row" style="margin-top:14px"><button class="btn" id="man-save">Сохранить</button><button class="btn ghost" id="man-cancel">Отмена</button></div></div>`;
  document.body.appendChild(ov);
  const g=id=>document.getElementById(id),mode=()=>g('man-mode').querySelector('.on').dataset.m;
  const showHide=()=>{
    const md=mode(),ext=md==='asset_ext',pos=md==='position',k=(pos||ext)?'buy':g('man-kind').value,trade=!ext&&(k==='buy'||k==='sell'),sec=!ext&&['buy','sell','coupon','dividend'].includes(k);
    g('man-newname').style.display=g('man-acc').value===''?'':'none';
    g('man-kindf').style.display=(pos||ext)?'none':'';
    g('man-extbox').style.display=ext?'':'none';
    g('man-secbox').style.display=sec?'':'none';
    g('man-qtyf').style.display=trade?'':'none';g('man-pricef').style.display=trade?'':'none';g('man-nkdf').style.display=k==='buy'&&!pos&&!ext?'':'none';
    g('man-commf').style.display=trade&&!pos?'':'none';g('man-cashf').style.display=!ext&&k==='buy'?'':'none';
    g('man-pricel').textContent=MAN.pick&&MAN.pick.pct?'Цена, % от номинала':'Цена за штуку, ₽';
    g('man-amountl').textContent=ext?'Текущая стоимость / остаток':trade?'Сумма сделки, ₽ (считается сама)':'Сумма, ₽';
    g('man-date').previousElementSibling.textContent=ext?'Дата оценки':pos?'Дата покупки (по желанию)':'Дата';
  };
  const calc=()=>{
    if(mode()==='asset_ext')return;
    const q=manNum(g('man-qty').value),p=manNum(g('man-price').value),n=manNum(g('man-nkd').value);
    const unit=MAN.pick&&MAN.pick.pct?p*(MAN.pick.nominal||1000)/100:p;
    if(q&&p)g('man-amount').value=(+(q*unit+n).toFixed(2)).toString();
  };
  g('man-acc').onchange=showHide;g('man-kind').onchange=showHide;
  g('man-mode').onclick=e=>{const b=e.target.closest('[data-m]');if(!b)return;g('man-mode').querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));showHide()};
  ['man-qty','man-price','man-nkd'].forEach(id=>g(id).oninput=calc);
  let to;
  g('man-q').oninput=()=>{clearTimeout(to);MAN.pick=null;to=setTimeout(async()=>{
    if(!g('man-q'))return;                                  /* окно закрыли, пока шла пауза */
    const q=g('man-q').value.trim();if(q.length<2){g('man-found').innerHTML='';return}
    try{const r=await api('/api/ops/manual/search?q='+encodeURIComponent(q));
      if(!g('man-found'))return;                            /* окно закрыли, пока шёл поиск */
      g('man-found').innerHTML=r.rows.length?r.rows.map((x,i)=>`<div class="it" data-i="${i}" style="cursor:pointer"><div><b>${esc(x.name)}</b><small>${esc(x.ticker)}${x.ident&&x.ident!==x.ticker?' · '+esc(x.ident):''} · ${x.kind==='bond'?'облигация':x.kind==='fund'?'фонд':'акция'}${x.price?' · '+(x.price_pct?x.price+' %':f2(x.price)+' ₽'):''}</small></div></div>`).join(''):'<div class="note">Ничего не найдено: можно ввести тикер или ISIN вручную.</div>';
      g('man-found').onclick=e=>{const it=e.target.closest('[data-i]');if(!it)return;const x=r.rows[+it.dataset.i];
        MAN.pick={ident:x.ident,ticker:x.ticker,name:x.name,pct:!!x.price_pct,nominal:+x.nominal||1000};
        g('man-q').value=x.name;g('man-found').innerHTML='';
        if(x.price&&!g('man-price').value)g('man-price').value=x.price;
        if(x.price_pct&&x.nkd&&!g('man-nkd').value)g('man-nkd').value=x.nkd;
        showHide();calc()}}
    catch(e){const f=g('man-found');if(f)f.innerHTML=''}},250)};
  g('man-x').onclick=g('man-cancel').onclick=manClose;
  ov.addEventListener('mousedown',e=>{if(e.target===ov)manClose()});
  g('man-save').onclick=async e=>{
    const b=e.currentTarget,er=g('man-err');er.style.display='none';
    const md=mode(),ext=md==='asset_ext',pos=md==='position';
    let body;
    if(ext){
      const ek=g('man-ext-kind').value,ekLab=(MAN_EXT_KINDS.find(x=>x[0]===ek)||['','Актив'])[1];
      const enm=g('man-ext-name').value.trim()||ekLab;
      const amt=manNum(g('man-amount').value);
      const ident=(ed&&ed.ident&&/^EXT:/i.test(ed.ident))?ed.ident:('EXT:'+ek.toUpperCase()+':'+Date.now().toString(36).slice(-6).toUpperCase());
      body={acc:g('man-acc').value,acc_name:g('man-accname').value||'Внебиржевые активы',group:ed?ed.group:'',mode:'position',kind:'buy',
        date:g('man-date').value||undefined,ident,ticker:'',name:enm,qty:'1',price:amt||'',amount:amt||'',currency:g('man-ext-cur').value||'rub',autocash:true};
    }else{
      const k=pos?'buy':g('man-kind').value,typed=g('man-q').value.trim();
      const pk=MAN.pick||{ident:typed.toUpperCase().replace(/\s+/g,''),ticker:'',name:typed};
      const unit=MAN.pick&&MAN.pick.pct?manNum(g('man-price').value)*(MAN.pick.nominal||1000)/100:manNum(g('man-price').value);
      body={acc:g('man-acc').value,acc_name:g('man-accname').value,group:ed?ed.group:'',mode:pos?'position':'op',kind:k,date:g('man-date').value||undefined,
        ident:pk.ident,ticker:pk.ticker,name:pk.name,qty:g('man-qty').value,price:unit||'',amount:g('man-amount').value,nkd:manNum(g('man-nkd').value)||'',
        commission:g('man-comm').value,autocash:g('man-cash').checked};
    }
    b.disabled=true;
    try{await post('/api/ops/manual',body);manClose();S.data=S.bonds=S.hist=null;toast('Запись сохранена.','ok');
      if(typeof DEMO!=='undefined'&&DEMO.on){DEMO.at=0;demoSync()}      /* сервер убрал демо: плашка уходит сразу */
      if(S.page==='ops'||S.page==='imp'){S.page==='imp'?renderImport():manualDrawList()}load(true)}
    catch(x){er.textContent=x.message;er.style.display=''}finally{b.disabled=false}
  };
  showHide();
}
async function manualDrawList(){
  const box=document.getElementById('man-list');if(!box)return;
  try{const r=await api('/api/ops/manual');MAN.rows=r.rows;
    if(!r.rows.length){box.innerHTML='';return}
    const T={buy:'Покупка',sell:'Продажа',coupons:'Купон',dividends:'Дивиденд',deposits:'Пополнение',withdrawals:'Вывод',fee_service:'Комиссия',fee_broker:'Комиссия'};
    box.innerHTML=`<div class="card"><h2>Ручные записи<span class="sp">${r.rows.length}</span></h2><div class="tbl"><table><thead><tr><th class="l">Дата</th><th class="l">Операция</th><th class="l">Бумага / актив</th><th class="l">Счёт</th><th>Кол-во</th><th>Сумма</th><th></th></tr></thead><tbody>${
      r.rows.slice(0,100).map((x,i)=>{const isExt=/^EXT:/i.test(x.ident||'');return`<tr><td class="l num t2">${esc(x.date)}</td><td class="l"><span class="tag">${esc(isExt?'Внебиржевой актив':x.position?'Позиция':T[x.type]||x.type)}</span></td><td class="l">${esc(x.name)}</td><td class="l t2">${esc(x.acc_name||'')}</td><td class="num">${isExt?'—':(x.qty||'')}</td><td class="num">${f2(x.amount)}</td><td class="num"><button class="btn ghost" data-me="${i}">Изменить</button> <button class="btn ghost danger" data-md="${i}">Удалить</button></td></tr>`}).join('')}</tbody></table></div></div>`;
    box.onclick=async e=>{
      const be=e.target.closest('[data-me]'),bd=e.target.closest('[data-md]');
      if(be)return manualOpen(MAN.rows[+be.dataset.me]);
      if(bd){const x=MAN.rows[+bd.dataset.md];if(!await uiConfirm({title:'Удалить ручную запись?', body:'Запись «'+x.name+'» от '+x.date+' будет удалена; вместе с ней уйдут её комиссия и пополнение под покупку.', danger:true, okText:'Удалить'}))return;
        try{await post('/api/ops/manual/delete',{acc:x.acc,group:x.group});S.data=S.bonds=S.hist=null;toast('Запись удалена.','ok');manualDrawList();load(true)}catch(err){toast(err.message,'err')}}};
  }catch(e){box.innerHTML=''}
}
function manualBindOps(){
  const b=document.getElementById('man-add');if(b)b.onclick=()=>manualOpen();
  manualDrawList();
}
