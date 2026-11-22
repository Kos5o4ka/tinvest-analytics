/* ── tooltip ── */
const tip=$('#tip');
function showTip(html,e){tip.innerHTML=html;tip.style.opacity=1;moveTip(e)}
function moveTip(e){const w=tip.offsetWidth,h=tip.offsetHeight;let x=e.clientX+14,y=e.clientY+14;
  if(x+w>innerWidth-8)x=e.clientX-w-14;if(y+h>innerHeight-8)y=e.clientY-h-14;
  tip.style.left=Math.max(8,x)+'px';tip.style.top=Math.max(8,y)+'px'}
function hideTip(){tip.style.opacity=0}
const tipRow=(c,n,v)=>`<div><i style="background:${c}"></i>${esc(n)}<span>${v}</span></div>`;
document.addEventListener('touchstart',e=>{if(!e.target.closest('[data-i],circle[data-k]'))hideTip()},{passive:true});
window.addEventListener('scroll',()=>hideTip(),true);
let _tipT;function tipTouchHide(e){if(e.pointerType==='touch'){clearTimeout(_tipT);_tipT=setTimeout(hideTip,2500)}}
function bindTip(el,fn){
  el.onpointerup=tipTouchHide;
  el.onmousemove=e=>{const t=e.target.closest('[data-i]');if(!t||!el.contains(t)){hideTip();el._hl&&el._hl(-1);return}
    const i=+t.dataset.i;showTip(fn(i),e);el._hl&&el._hl(i)};
  el.onmouseleave=()=>{hideTip();el._hl&&el._hl(-1)};
}

