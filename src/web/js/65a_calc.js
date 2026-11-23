/* ── Мини-калькулятор для палитры команд: собственный разбор выражений (без eval/new Function) ──
   calcEval('150000*0,13') → 19500; '(2+3)*4' → 20; '10%' → 0.1; '100+10%' → 110; мусор / деление на 0 → null */
function calcEval(raw){
  if(typeof raw!=='string')return null;
  let s=raw.trim();
  if(!s||s.length>120||!/^[\d\s  +\-−*/×÷().,%^]+$/.test(s)||!/\d/.test(s))return null;
  if(!/[+\-−*/×÷^%]/.test(s.replace(/^[\s+\-−]+/,'')))return null;       /* одно число — не выражение */
  s=s.replace(/(\d)[   ]+(?=\d{3}(?!\d))/g,'$1').replace(/[\s  ]+/g,'').replace(/−/g,'-').replace(/×/g,'*').replace(/÷/g,'/').replace(/,/g,'.');
  let i=0,depth=0;const bad=new Error('calc');
  /* возвращает {v, p}: p=true, если значение — процентный литерал (нужно для «100+10%» = 110) */
  const num=()=>{
    const m=/^(\d+\.?\d*|\.\d+)/.exec(s.slice(i));
    if(!m)throw bad;i+=m[0].length;return parseFloat(m[0]);
  };
  const primary=()=>{
    if(s[i]==='('){
      if(++depth>40)throw bad;i++;const r=expr();
      if(s[i]!==')')throw bad;i++;depth--;return r;
    }
    return{v:num(),p:false};
  };
  const post=()=>{let r=primary();while(s[i]==='%'){i++;r={v:r.v/100,p:true}}return r};
  const unary=()=>{
    if(s[i]==='-'){i++;const r=unary();return{v:-r.v,p:r.p}}
    if(s[i]==='+'){i++;return unary()}
    const b=post();
    if(s[i]==='^'){i++;const e=unary();const v=Math.pow(b.v,e.v);if(!isFinite(v))throw bad;return{v,p:false}}
    return b;
  };
  const term=()=>{
    let a=unary();
    while(s[i]==='*'||s[i]==='/'){
      const op=s[i++],b=unary();
      if(op==='/'){if(b.v===0)throw bad;a={v:a.v/b.v,p:false}}else a={v:a.v*b.v,p:false};
    }
    return a;
  };
  const expr=()=>{
    let a=term();
    while(s[i]==='+'||s[i]==='-'){
      const op=s[i++],b=term();
      if(b.p&&!a.p)a={v:op==='+'?a.v*(1+b.v):a.v*(1-b.v),p:false};   /* 100+10% → 110, 200−15% → 170 */
      else a={v:op==='+'?a.v+b.v:a.v-b.v,p:false};
    }
    return a;
  };
  try{
    const r=expr();
    if(i!==s.length)return null;
    const v=Math.round(r.v*1e9)/1e9;
    return isFinite(v)&&Math.abs(v)<1e15?v:null;
  }catch(e){return null}
}
const calcFmt=v=>v.toLocaleString('ru-RU',{maximumFractionDigits:6});
const calcRaw=v=>String(Math.round(v*1e8)/1e8).replace('.',',');
