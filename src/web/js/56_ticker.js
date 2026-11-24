/* ── бегущая строка котировок: сверху приложения, обновляется только своя разметка (render() не трогаем) ── */
const TKR={items:[],sig:'',timer:null,busy:false};
function tkrFmt(it){
  const p=it.price,d=it.kind==='fx'||it.kind==='stock'?(p<100?(p<10?4:3):2):2;
  const s=p.toLocaleString('ru-RU',{minimumFractionDigits:it.kind==='index'||p>=1000?2:Math.min(d,2),maximumFractionDigits:d});
  return it.unit==='$'?'$'+s:s+(it.unit?' '+it.unit:'');
}
function tkrChg(c){
  if(c==null||isNaN(c))return['z','—'];
  const k=c>0.004?'pos':c<-0.004?'neg':'z';
  return[k,(c>0?'+':c<0?'−':'')+Math.abs(c).toFixed(2).replace('.',',')+' %'];
}
function tkrItemHtml(it){
  const [k,t]=tkrChg(it.chg),st=it.kind==='stock'?` data-stk="${esc(it.id)}" title="Открыть карточку ${esc(it.id)}"`:'';
  return`<span class="tk-it" data-id="${esc(it.id)}"${st}><b>${esc(it.label)}</b><span class="tk-p">${esc(tkrFmt(it))}</span><span class="tk-ch ${k}">${t}</span></span>`;
}
function tkrOff(){return lsGet('ta_ticker_off')==='1'}
function tkrBuild(){
  const el=document.getElementById('tkr');if(!el)return;
  if(tkrOff()){
    el.hidden=false;el.className='tkr off';el.innerHTML='<button class="tk-x" id="tkrx" title="Показать бегущую строку котировок">Котировки ▾</button>';
    el.querySelector('#tkrx').onclick=()=>{lsSet('ta_ticker_off','0');TKR.sig='';tkrBuild();tkrLoad()};
    TKR.sig='';return;
  }
  if(!TKR.items.length){el.hidden=true;return}
  el.hidden=false;el.className='tkr';
  const g=TKR.items.map(tkrItemHtml).join('');
  el.innerHTML=`<div class="tk-vp"><div class="tk-track"><div class="tk-grp">${g}</div><div class="tk-grp" aria-hidden="true">${g}</div></div></div><button class="tk-x" id="tkrx" title="Скрыть строку котировок" aria-label="Скрыть">×</button>`;
  el.querySelector('#tkrx').onclick=()=>{lsSet('ta_ticker_off','1');tkrBuild()};
  /* клик по бумаге ([data-stk]) открывает карточку через общий обработчик в 45_stock.js */
  const w=el.querySelector('.tk-grp').scrollWidth||1000;
  el.querySelector('.tk-track').style.setProperty('--tk-dur',Math.max(40,Math.round(w/45))+'s'); /* ~45 px/с */
}
function tkrApply(items){
  const sig=items.map(i=>i.id).join(',');
  TKR.items=items;
  const el=document.getElementById('tkr');if(!el||tkrOff()){tkrBuild();return}
  if(sig===TKR.sig&&el.querySelector('.tk-track')){
    for(const it of items){ /* набор тот же — меняем только текст, анимация не сбрасывается */
      const [k,t]=tkrChg(it.chg);
      el.querySelectorAll('.tk-it[data-id="'+(window.CSS&&CSS.escape?CSS.escape(it.id):it.id)+'"]').forEach(n=>{
        {const pe=n.querySelector('.tk-p'),nt=tkrFmt(it);if(pe.textContent!==nt){if(typeof tickNum==='function')tickNum(pe,nt);else pe.textContent=nt}}
        const c=n.querySelector('.tk-ch');c.textContent=t;c.className='tk-ch '+k;
      });
    }
    return;
  }
  TKR.sig=sig;tkrBuild();
}
function tkrLoad(){
  if(TKR.busy||tkrOff())return;TKR.busy=true;
  api('/api/ticker').then(j=>{TKR.busy=false;if(j&&j.items&&j.items.length)tkrApply(j.items)}).catch(()=>{TKR.busy=false});
}
(function(){
  if(tkrOff())tkrBuild();
  else setTimeout(tkrLoad,600);
  setInterval(()=>{if(!document.hidden)tkrLoad()},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)tkrLoad()});
})();
