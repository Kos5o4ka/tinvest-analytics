/* ── logos ── */
const LOGO_BAD=new Set();
function colorFor(t){return HEX[(t||'?').split('').reduce((a,ch)=>a+ch.charCodeAt(0),0)%8]}
function logo(r,size=30){
  const t=(r.ticker&&!/^[A-Z]{2}[A-Z0-9]{9}\d$/.test(r.ticker)&&r.ticker.length<=6?r.ticker:(r.name||r.ticker||'?')).replace(/^(ПАО|АО|ООО|МФК|ПКО|ОФЗ)\s+/i,''),w=t.split(/[\s\-«»"]+/).filter(x=>/[A-Za-zА-Яа-яЁё0-9]/.test(x)),init=esc((w.length>1&&!(r.ticker&&r.ticker.length<=6&&t===r.ticker)?w[0][0]+w[1][0]:(t.replace(/[^A-Za-zА-Яа-яЁё0-9]/g,'')||'?').slice(0,2)).toUpperCase());
  return`<span class="av" style="width:${size}px;height:${size}px;background:${esc(r.color||colorFor(t))};font-size:${Math.round(size*.36)}px"><b>${init}</b>${r.logo&&!LOGO_BAD.has(r.logo)?`<img src="/logo/${encodeURIComponent(r.logo)}" alt="" loading="lazy" data-l="${esc(r.logo)}" onerror="LOGO_BAD.add(this.dataset.l);this.remove()">`:''}</span>`;
}
const ident=(r,sub)=>`<div class="tk">${logo(r)}<div><b title="${esc(r.name)}">${esc(r.name||r.ticker)}</b><small>${esc(sub!=null?sub:(r.ticker&&r.ticker!==r.name?r.ticker:''))}</small></div></div>`;

