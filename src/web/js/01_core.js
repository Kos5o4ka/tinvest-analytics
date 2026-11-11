"use strict";
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const NF2=new Intl.NumberFormat('ru-RU',{minimumFractionDigits:2,maximumFractionDigits:2});
const NF0=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0});
const NFQ=new Intl.NumberFormat('ru-RU',{maximumFractionDigits:6});
const CUR={rub:'₽',usd:'$',eur:'€',cny:'¥',hkd:'HK$',gbp:'£',chf:'₣',jpy:'¥',try:'₺',kzt:'₸',byn:'Br',amd:'֏'};
const sym=c=>CUR[c]||(c||'').toUpperCase();
const bad=n=>n==null||isNaN(n)||!isFinite(n);
const f2=n=>bad(n)?'—':NF2.format(n);
const f0=n=>bad(n)?'—':NF0.format(n);
/* режим «инкогнито»: суммы в деньгах скрыты, проценты, количества и рейтинги остаются */
const INCOG={on:(()=>{try{return localStorage.getItem('ta_incog')==='1'}catch(e){return false}})()};
const MASK='••••';
const M=(n,c='rub',d=2)=>bad(n)?'—':INCOG.on?MASK+' '+sym(c):(d?NF2:NF0).format(n)+' '+sym(c);
const SM=(n,c='rub')=>bad(n)?'—':INCOG.on?MASK+' '+sym(c):(n>0?'+':'')+M(n,c);
const f2m=n=>bad(n)?'—':INCOG.on?MASK:NF2.format(n);
const pct=(n,d=2)=>bad(n)?'—':(n>0?'+':'')+n.toFixed(d).replace('.',',')+' %';
const pctp=(n,d=1)=>bad(n)?'—':n.toFixed(d).replace('.',',')+' %';
const cls=n=>n>0?'pos':n<0?'neg':'';
const short=n=>{if(bad(n))return'—';if(INCOG.on)return MASK;const a=Math.abs(n),t=(x,s)=>(x.toFixed(x>=100||Number.isInteger(x)?0:1).replace('.',',')+s),sg=n<0?'−':'';
  if(a>=1e9)return sg+t(a/1e9,' млрд');if(a>=1e6)return sg+t(a/1e6,' млн');if(a>=1e3)return sg+t(a/1e3,' тыс');return sg+f0(a)};
const MON=['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];
const MONF=['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
const mlabel=m=>{const[y,mm]=m.split('-');return MON[+mm-1]+' '+y.slice(2)};
const dlabel=d=>{const[y,m,dd]=d.split('-');return +dd+' '+MON[+m-1]+' '+y};
const ddm=d=>{const[y,m,dd]=d.split('-');return dd+'.'+m+'.'+y.slice(2)};
const S1='var(--s1)',S2='var(--s2)',S3='var(--s3)',S4='var(--s4)',S5='var(--s5)',S6='var(--s6)',S7='var(--s7)',S8='var(--s8)';
const PAL=[S1,S2,S3,S4,S5,S6,S7,S8];
const HEX=['#3987e5','#d95926','#199e70','#c98500','#d55181','#008300','#9085e9','#e66767'];


/* ── уведомление-«тост» и копирование в буфер ── */
function toast(msg,ms){
  let t=document.getElementById('toast');
  if(!t){t=document.createElement('div');t.id='toast';t.setAttribute('role','status');document.body.appendChild(t)}
  t.textContent=msg;t.className='show';clearTimeout(toast._t);toast._t=setTimeout(()=>{t.className=''},ms||2200);
}
function copyText(txt,msg){
  const done=()=>toast(msg||'Скопировано');
  const fb=()=>{try{const a=document.createElement('textarea');a.value=txt;a.style.cssText='position:fixed;opacity:0;top:0;left:0';document.body.appendChild(a);a.select();document.execCommand('copy');a.remove();done()}catch(e){toast('Не удалось скопировать')}};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done,fb)}else fb();
}
const isinTxt=i=>i?`<span class="cp" data-copy="${esc(i)}" title="Нажмите, чтобы скопировать ISIN">${esc(i)}</span>`:'';
document.addEventListener('click',e=>{
  const c=e.target.closest&&e.target.closest('[data-copy]');
  if(c){e.stopPropagation();e.preventDefault();copyText(c.dataset.copy,'ISIN скопирован')}
},true);
