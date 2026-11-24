/* ── Плавное закрытие выезжающих панелей ──
   drawerClose(ov, cb): ov — затемнение (#sk-ov, #bc-ov…), первый дочерний элемент — сама панель.
   Панель уезжает вправо за DRAWER_OUT мс, фон гаснет, затем ov удаляется и вызывается cb.
   Стили, заданные через #id, на время анимации копируются в style: id сразу снимается, поэтому повторное открытие
   (getElementById) создаёт новую панель и не подхватывает закрывающуюся. При prefers-reduced-motion — мгновенно. */
const DRAWER_OUT=180;
function drawerClose(ov,cb){
  const done=()=>{try{cb&&cb()}catch(e){console.error(e)}};
  if(!ov||!ov.isConnected){done();return}
  if(ov.classList.contains('closing'))return;
  const quick=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(quick){ov.remove();done();return}
  const freeze=(el,props)=>{if(!el)return;const cs=getComputedStyle(el),r=el.getBoundingClientRect();
    props.forEach(p=>el.style.setProperty(p,cs.getPropertyValue(p)));
    if(el!==ov){el.style.width=r.width+'px';el.style.height=r.height+'px';el.style.flex='none'}};
  const dr=ov.firstElementChild;
  freeze(ov,['position','top','right','bottom','left','z-index','display','justify-content','align-items','background-color','backdrop-filter']);
  freeze(dr,['display','flex-direction','background-color','border-left','box-shadow','overflow']);
  [ov,dr].forEach(el=>{if(el&&el.id){el.dataset.closingId=el.id;el.removeAttribute('id')}});
  ov.classList.add('closing');ov.setAttribute('aria-hidden','true');
  let fin=false;const end=()=>{if(fin)return;fin=true;ov.remove();done()};
  (dr||ov).addEventListener('animationend',e=>{if(e.target===(dr||ov))end()});
  setTimeout(end,DRAWER_OUT+80);     /* страховка: animationend может не прийти (вкладка в фоне) */
}
