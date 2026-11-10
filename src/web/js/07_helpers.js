/* ── helpers ── */
const T=()=>S.data.totals.rub||{};
const sumK=(o,ks)=>ks.reduce((a,k)=>a+(o[k]||0),0);
const TAXK=['tax_trade','tax_dividend','tax_coupon','tax_repo','tax_other'];
const FEEK=['fee_broker','fee_service','fee_other','margin_fee'];
const L={tax_trade:'Налог с прибыли по сделкам',tax_dividend:'Налог с дивидендов',tax_coupon:'Налог с купонов',tax_repo:'Налог по РЕПО',tax_other:'Прочие налоги',
  fee_broker:'Комиссия брокера',fee_service:'Обслуживание счёта',fee_other:'Прочие комиссии',margin_fee:'Плата за маржу (шорт / плечо)'};
const TYPES={share:'Акции',bond:'Облигации',etf:'Фонды',currency:'Валюта',futures:'Фьючерсы',option:'Опционы',sp:'Структурные'};
const SECT={financial:'Финансы',it:'IT',telecom:'Телеком',energy:'Энергетика',utilities:'Электроэнергетика',materials:'Сырьё и материалы',industrials:'Промышленность',
  consumer:'Потребительский',health_care:'Здравоохранение',real_estate:'Недвижимость',government:'Государство',municipal:'Муниципальные',ecomaterials:'Экология',
  green_energy:'Зелёная энергетика',green_buildings:'Зелёное строительство',electrocars:'Электромобили',other:'Прочее'};
function kpi(k,v,s,c,dot){return`<div class="card kpi"><div class="k">${dot?`<i style="background:${dot}"></i>`:''}${k}</div><div class="v num ${c||''}">${v}</div><div class="s">${s||'&nbsp;'}</div></div>`}
const periodName=()=>PERIODS.find(p=>p[0]===S.period)[1].toLowerCase();
const waitBox=t=>`<div class="wait">${t||'Считаю…'}</div>`;
function monthsSeries(n=36){
  let ms=S.data.months;if(ms.length>n)ms=ms.slice(-n);
  return{labels:ms.map(m=>mlabel(m[0])),tips:ms.map(m=>{const[y,mm]=m[0].split('-');return MONF[+mm-1]+' '+y}),rows:ms.map(m=>m[1])};
}
function periodStart(){const d=new Date();const iso=x=>x.toISOString().slice(0,10);
  switch(S.period){case'1m':d.setDate(d.getDate()-30);return iso(d);case'3m':d.setDate(d.getDate()-91);return iso(d);
  case'12m':d.setDate(d.getDate()-365);return iso(d);case'ytd':return d.getFullYear()+'-01-01';case'py':return(d.getFullYear()-1)+'-01-01';default:return null}}
function periodEnd(){return S.period==='py'?(new Date().getFullYear()-1)+'-12-31':null}
function histSlice(){
  const h=S.hist;if(!h||!h.days||!h.days.length)return null;
  const s=periodStart(),e=periodEnd();let i0=0,i1=h.days.length-1;
  if(s){i0=h.days.findIndex(d=>d>=s);if(i0<0)return null;i0=Math.max(0,i0-1)}
  if(e){while(i1>0&&h.days[i1]>e)i1--}
  if(i1<=i0)return null;
  const days=h.days.slice(i0,i1+1),base=h.twr[i0],twr=h.twr.slice(i0,i1+1).map(x=>x/base-1);
  const bench={};for(const[k,v]of Object.entries(h.bench||{})){const sl=v.slice(i0,i1+1);const b0=sl.find(x=>x!=null);bench[k]=sl.map(x=>x==null||!b0?null:x/b0-1)}
  let peak=-Infinity;const dd=twr.map(x=>{peak=Math.max(peak,1+x);return(1+x)/peak-1});
  const rets=[];for(let i=1;i<twr.length;i++)rets.push((1+twr[i])/(1+twr[i-1])-1);
  const mean=rets.reduce((a,b)=>a+b,0)/(rets.length||1),vol=Math.sqrt(rets.reduce((a,b)=>a+(b-mean)**2,0)/Math.max(1,rets.length-1))*Math.sqrt(365);
  const years=(new Date(days[days.length-1])-new Date(days[0]))/(365.25*864e5);
  const total=twr[twr.length-1],ann=years>=1?Math.pow(1+total,1/years)-1:null;
  return{days,twr,dd,bench,value:h.value.slice(i0,i1+1),invested:h.invested.slice(i0,i1+1),total,ann,vol,maxdd:Math.min(...dd),years};
}

