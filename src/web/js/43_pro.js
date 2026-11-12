/* ── Тарифы Free / Pro ──
   Тариф приходит из /api/auth/status (plan, pro_until). Без сервера данных, с общим ключом и на старом сервере всё доступно (plan='pro').
   Клиентские блокировки — это UX: код программы открыт и обходится правкой. Принудительно сервер проверяет Pro только для уведомлений в Telegram (402). */
const PRO_PAGES=['scr','cmp','lad','sig','risk','mon','map'];
const PRO_FEATURES={
 scr:{t:'Скринер облигаций',ic:'scr',b:['Фильтры по доходности, сроку, рейтингу и типу выпуска','Поиск выпусков под вашу цель за секунды','Сортировка по любому столбцу','Переход в карточку выпуска в один клик'],pv:'table'},
 cmp:{t:'Сравнение облигаций',ic:'cmp',b:['До нескольких выпусков рядом: доходность, дюрация, рейтинг, купон','Подсветка лучшего и худшего значения по каждому параметру','Оферты PUT и CALL, амортизация, оборот и НКД','Добавление из карточки выпуска кнопкой «Сравнить»'],pv:'table'},
 lad:{t:'Лесенка облигаций',ic:'lad',b:['Куда и когда возвращаются деньги из вашего портфеля','Конструктор новой лесенки под сумму и горизонт','Учёт рейтинга, флоатеров и амортизации','График выплат по месяцам и кварталам'],pv:'chart'},
 sig:{t:'Сигналы',ic:'sig',b:['Бумаги портфеля со спредом выше или ниже медианы аналогов','Похожие выпуски с другой доходностью','Сравнение с выпусками того же рейтинга и срока','Объяснение, почему сработал сигнал'],pv:'cards'},
 risk:{t:'Риски и сценарии',ic:'risk',b:['Что будет с портфелем при росте и снижении ставок','Концентрация по эмитентам, секторам и срокам','Стресс-сценарии и чувствительность цены','Кредитные риски по рейтингам'],pv:'chart'},
 mon:{t:'Мониторинг',ic:'mon',b:['Слежение за рейтингами, дефолтами и резкими движениями цен','Тревоги по вашим бумагам с объяснением','Расширение спреда и ликвидность: сколько дней на продажу','Уведомления в Telegram (тоже Pro)'],pv:'cards'},
 map:{t:'Карта рынка',ic:'map',b:['Все выпуски на одной карте: доходность против срока','Ваши бумаги на фоне рынка','Видно, какие выпуски дают больше при том же сроке','Переход в карточку выпуска с карты'],pv:'chart'},
 offers:{t:'Сравнение по оферте',ic:'off',b:['Сравнение доходности к оферте и к погашению','Сравнение с доходностью похожих выпусков','Сроки и порядок подачи заявки','Кредитные риски эмитента рядом с расчётом'],pv:'cards'},
 taxfc:{t:'Прогноз налога на 31.12',ic:'tax',b:['Сколько налога будет удержано на конец года','Ожидаемые купоны и дивиденды до конца года','Убытки, которые уменьшают налоговую базу','Учёт ЛДВ и ставки 13 / 15 %'],pv:'table'},
 tg:{t:'Уведомления в Telegram',ic:'mon',b:['Тревоги мониторинга и списка наблюдения','Пут-оферты: новый купон, открытие приёма заявок, последние дни','Возможный колл по вашим бумагам','Приходят от @tanalyticbot, ничего настраивать не нужно'],pv:'cards'}
};
const PRO_FREE_LIST=['Портфель, позиции, облигации и доходность','Выплаты, календарь, операции и комиссии','Налоги: факт по годам, ЛДВ, ИИС, данные для декларации','Ребалансировка, калькулятор, ставки, эмитенты, наблюдение','Импорт отчётов, резервные копии, база знаний'];
const proBot=()=>String(AUTH&&AUTH.bot||'tanalyticbot').replace(/^@/,'');
const proUrl=()=>`https://t.me/${proBot()}?start=pro`;
function isPro(){
  const s=AUTH&&AUTH.st;
  if(!s||s.plan!=='free'&&!(s.pro_until&&s.pro_until*1000<=Date.now()))return true;      /* статус ещё не получен или нет данных о тарифе — не блокируем */
  return false;
}
const proDm=ts=>{const d=new Date(ts*1000);return String(d.getDate()).padStart(2,'0')+'.'+String(d.getMonth()+1).padStart(2,'0')};
function proDaysLeft(){const s=AUTH&&AUTH.st;return s&&s.pro_until?Math.ceil((s.pro_until*1000-Date.now())/864e5):null}
const proBadge=()=>'<em class="pro-b">Pro</em>';
/* function (всплывает): renderNav вызывается из загрузчика раньше, чем выполнится этот файл; тогда бейджей ещё нет */
function proNavBadge(k){try{return PRO_PAGES.includes(k)&&!isPro()?proBadge():''}catch(e){return''}}
function proSkel(kind){
  const bar=(w,h=10)=>`<i style="width:${w}%;height:${h}px"></i>`;
  if(kind==='chart')return`<div class="pro-sk"><div class="pro-sk-row">${bar(30,14)}${bar(20,14)}${bar(15,14)}</div><div class="pro-sk-ch">${[40,65,50,80,60,90,55,75,45,70].map(h=>`<b style="height:${h}%"></b>`).join('')}</div></div>`;
  if(kind==='cards')return`<div class="pro-sk"><div class="pro-sk-g">${[1,2,3].map(()=>`<div class="pro-sk-c">${bar(60,12)}${bar(90)}${bar(75)}</div>`).join('')}</div>${[1,2].map(()=>`<div class="pro-sk-c">${bar(40,12)}${bar(95)}${bar(80)}</div>`).join('')}</div>`;
  return`<div class="pro-sk"><div class="pro-sk-row">${bar(18,14)}${bar(14,14)}${bar(14,14)}${bar(14,14)}</div>${Array.from({length:8},()=>`<div class="pro-sk-row">${bar(24)}${bar(12)}${bar(12)}${bar(12)}${bar(10)}</div>`).join('')}</div>`;
}
/* Карточка-заглушка вместо недоступной страницы/блока: feature — ключ из PRO_FEATURES, previewHtml — статичная картинка под размытием */
function proLock(feature,previewHtml){
  const f=PRO_FEATURES[feature]||{t:'Эта функция',ic:'set',b:['Инструменты анализа облигаций','Прогнозы и подсказки','Уведомления в Telegram'],pv:'table'};
  const bot=esc(proBot());
  return`<div class="pro-lock fade"><div class="pro-prev" aria-hidden="true">${previewHtml||proSkel(f.pv)}</div>
    <div class="card pro-card" role="region" aria-label="Доступно в Pro"><span class="pro-tag">Pro</span>
      <h2>Доступно в Pro</h2>
      <div class="pro-ft">${svgI(IC[f.ic]||IC.set)}<b>${esc(f.t)}</b></div>
      <ul class="pro-ul">${f.b.slice(0,4).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>
      <div class="row pro-btns"><a class="btn" href="${esc(proUrl())}" target="_blank" rel="noopener noreferrer">Открыть @${bot}</a><button class="btn ghost" data-pro-about>Что даёт Pro</button></div>
      <p class="note">Новым пользователям бот дарит 7 дней Pro. Токен Т-Инвестиций остаётся на вашем компьютере на любом тарифе.</p></div></div>`;
}
/* Короткая строка вместо блока внутри страницы */
function proTeaser(text){return`<p class="pro-line">${svgI('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>')}<span>${esc(text)}</span><button class="pro-lk" data-pro-about>Что даёт Pro</button></p>`}
/* Плашка в шапке рядом с «Выйти» */
function proPill(){
  const s=AUTH&&AUTH.st;if(!s||s.state!=='ok')return'';
  if(!isPro())return`<span class="pro-pill free" title="Бесплатный тариф">Free</span><button class="pro-try" data-pro-about>Попробовать Pro</button>`;
  if(s.plan==='pro'&&s.pro_until)return`<span class="pro-pill on" title="${s.trial?'Пробный период':'Pro выдан в боте'}">Pro${s.trial?' · пробный':''} до ${proDm(s.pro_until)}</span>`;
  return'';
}
/* Мягкое напоминание за 3 дня до конца (можно закрыть до следующего срока) */
function proBanner(){
  const s=AUTH&&AUTH.st,d=proDaysLeft();
  if(!s||s.plan!=='pro'||!s.pro_until||d==null||d<=0||d>3)return'';
  if(lsGet('ta_pro_ban')===String(s.pro_until))return'';
  return`<div class="msg info pro-ban"><span>Pro действует до ${proDm(s.pro_until)}${d<=1?' (остался день)':''}. Продлить: <a href="${esc(proUrl())}" target="_blank" rel="noopener noreferrer">@${esc(proBot())}</a>, команда /pro.</span><button data-pro-dismiss title="Скрыть">×</button></div>`;
}
function proAbout(){
  if(document.getElementById('pro-ov'))return;
  const ov=document.createElement('div');ov.id='pro-ov';
  const keys=PRO_PAGES.concat(['offers','taxfc','tg']);
  ov.innerHTML=`<div class="pro-box" role="dialog" aria-modal="true" aria-label="Что даёт Pro"><button class="pro-x" data-pro-close aria-label="Закрыть">×</button>
    <h2>Free и Pro</h2><p class="note">Оплата пока не подключена. Pro выдаётся в боте: 7 дней в подарок новым пользователям, дальше по запросу администратору.</p>
    <h3>Pro</h3><div class="pro-grid">${keys.map(k=>{const f=PRO_FEATURES[k];return`<div class="pro-it">${svgI(IC[f.ic]||IC.set)}<div><b>${esc(f.t)}</b><small>${esc(f.b[0])}</small></div></div>`}).join('')}</div>
    <h3>Free</h3><ul class="pro-ul">${PRO_FREE_LIST.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>
    <div class="row pro-btns"><a class="btn" href="${esc(proUrl())}" target="_blank" rel="noopener noreferrer">Открыть @${esc(proBot())}</a><button class="btn ghost" data-pro-kb>Подробнее в базе знаний</button><button class="btn ghost" data-pro-close>Закрыть</button></div>
    <p class="note">Токен Т-Инвестиций не покидает ваш компьютер на любом тарифе.</p></div>`;
  document.body.appendChild(ov);
}
function proClose(){const o=document.getElementById('pro-ov');if(o)o.remove()}
document.addEventListener('click',e=>{
  const t=e.target;if(!t||!t.closest)return;
  if(t.closest('[data-pro-about]')){e.preventDefault();proAbout();return}
  if(t.closest('[data-pro-kb]')){proClose();kbOpen('pro');return}
  if(t.closest('[data-pro-close]')||t.id==='pro-ov'){proClose();return}
  if(t.closest('[data-pro-dismiss]')){const s=AUTH.st;if(s&&s.pro_until)try{localStorage.setItem('ta_pro_ban',String(s.pro_until))}catch(x){}const b=t.closest('.pro-ban');if(b)b.remove()}
});
document.addEventListener('keydown',e=>{if(e.key==='Escape')proClose()});
/* Тариф изменился (вход, выход, выдача Pro) — обновить меню, шапку и текущую страницу */
let _proSig='';
function proAuthChanged(){
  const s=AUTH.st,sig=s?[s.state,s.plan,s.pro_until].join('|'):'';
  if(sig===_proSig)return;
  const first=_proSig==='';_proSig=sig;
  try{renderNav();if(!first)render()}catch(e){}
}
