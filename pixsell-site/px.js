/* Pixsell Services — lean behaviour (no preloader, no cursor, no scroll-pinning) */
(function(){
var d=document,h=window.PX||{};
function init(){
var root=d.querySelector('.px');if(!root)return;
var $=function(s,o){return(o||root).querySelector(s)},$$=function(s,o){return Array.prototype.slice.call((o||root).querySelectorAll(s))};
var ss={get:function(k){try{return sessionStorage.getItem(k)}catch(e){return null}},set:function(k,v){try{sessionStorage.setItem(k,v)}catch(e){}}};
var PRICE={horoshop:1500,other:2500,prom:3000},NAME={horoshop:'Покинуті кошики: Хорошоп',other:'Покинуті кошики: інший сайт',prom:'Покинуті кошики: Пром'};
/* pixels (only when ids are configured) */
if(h.meta&&!window.fbq){(function(f,b,e,v,n,t,s){n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)})(window,d,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init',h.meta);fbq('track','PageView')}
if(h.tt&&!window.ttq){(function(w,D,t){w.TiktokAnalyticsObject=t;var q=w[t]=w[t]||[];q.methods=['page','track','identify','instances','debug','on','off','once','ready','alias','group','enableCookie','disableCookie'];q.setAndDefer=function(o,m){o[m]=function(){o.push([m].concat([].slice.call(arguments,0)))}};for(var i=0;i<q.methods.length;i++)q.setAndDefer(q,q.methods[i]);q.instance=function(x){for(var a=q._i[x]||[],j=0;j<q.methods.length;j++)q.setAndDefer(a,q.methods[j]);return a};q.load=function(x,o){var u='https://analytics.tiktok.com/i18n/pixel/events.js';q._i=q._i||{};q._i[x]=[];q._i[x]._u=u;q._t=q._t||{};q._t[x]=+new Date;q._o=q._o||{};q._o[x]=o||{};var s=D.createElement('script');s.async=!0;s.src=u+'?sdkid='+x+'&lib='+t;var f=D.getElementsByTagName('script')[0];f.parentNode.insertBefore(s,f)};q.load(h.tt);q.page()})(window,d,'ttq')}
var EV={ViewContent:['ViewContent','ViewContent'],InitiateCheckout:['InitiateCheckout','InitiateCheckout'],Lead:['Lead','SubmitForm'],Contact:['Contact','Contact'],Purchase:['Purchase','CompletePayment']};
function track(t,o){try{var s=EV[t];window.fbq&&fbq('track',s[0],o||{});window.ttq&&ttq.track(s[1],o||{})}catch(e){}}
/* utm */
var utm={};try{var qp=new URLSearchParams(location.search);['utm_source','utm_medium','utm_campaign','utm_content','utm_term','ttclid','fbclid'].forEach(function(k){qp.get(k)&&(utm[k]=qp.get(k))});if(Object.keys(utm).length)ss.set('px_utm',JSON.stringify(utm));else utm=JSON.parse(ss.get('px_utm')||'{}')}catch(e){}
/* mobile menu */
var bg=$('.mn'),mm=$('.mm');
function closeMenu(){if(mm){mm.classList.remove('open');d.documentElement.classList.remove('mo');bg&&bg.setAttribute('aria-expanded','false')}}
if(bg&&mm){bg.addEventListener('click',function(){var o=mm.classList.toggle('open');d.documentElement.classList.toggle('mo',o);bg.setAttribute('aria-expanded',o)});$$('a',mm).forEach(function(a){a.addEventListener('click',closeMenu)});addEventListener('resize',function(){if(innerWidth>1060)closeMenu()})}
/* dropdown */
var dd=$('.dd'),ddb=dd&&$('button',dd);
if(dd){ddb.addEventListener('click',function(e){e.stopPropagation();var o=dd.classList.toggle('open');ddb.setAttribute('aria-expanded',o)});d.addEventListener('click',function(e){if(!e.target.closest('.dd')){dd.classList.remove('open');ddb.setAttribute('aria-expanded','false')}});$$('a',dd).forEach(function(a){a.addEventListener('click',function(){dd.classList.remove('open')})})}
$$('.nav .dm a').forEach(function(a){a.classList.toggle('on',a.dataset.p===root.dataset.page)});
if(ddb)ddb.classList.toggle('on',!!$('.dm a.on'));
/* reveal */
var rv=$$('.rv');d.documentElement.classList.add('js');
if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{rootMargin:'0px 0px -5% 0px'});rv.forEach(function(el){io.observe(el)})}else rv.forEach(function(el){el.classList.add('in')});
setTimeout(function(){rv.forEach(function(el){el.classList.add('in')})},4000);
/* how-it-works: click/hover to switch step (no scroll pinning) */
$$('.scene').forEach(function(sc){var li=$$('.steps li',sc),pn=$$('.pane>div',sc);function set(i){li.forEach(function(x,j){x.classList.toggle('on',j===i)});pn.forEach(function(x,j){x.classList.toggle('on',j===i)})}li.forEach(function(x,i){x.addEventListener('click',function(){set(i)});x.addEventListener('mouseenter',function(){if(matchMedia('(hover:hover)').matches)set(i)})})});
/* generic tabs */
$$('[data-tabs]').forEach(function(t){var b=$$('.tb',t),p=$$('.tp',t);function set(i){b.forEach(function(x,j){x.classList.toggle('on',j===i)});p.forEach(function(x,j){x.classList.toggle('on',j===i)})}b.forEach(function(x,i){x.addEventListener('click',function(){set(i)})})});
/* lead form = SendPulse pop-up (opened through a hidden proxy element carrying its launch class) */
var SPC='sp_popup_60b075a6-63bc-4406-80fc-c57a649b483f',TGL=h.tg||'https://t.me/Vadim_pixsell';
var px=d.createElement('button');px.type='button';px.hidden=!0;px.className=SPC;px.setAttribute('aria-hidden','true');px.tabIndex=-1;root.appendChild(px);
function openForm(){track('Contact',{content_name:root.dataset.page});if(window.pxSp)px.click();else window.open(TGL,'_blank','noopener')}
d.addEventListener('click',function(e){
var o=e.target.closest('[data-open]');if(o){e.preventDefault();openForm();return}
var by=e.target.closest('[data-buy]');if(by){e.preventDefault();var k=by.dataset.buy;track('InitiateCheckout',{content_name:NAME[k],value:PRICE[k],currency:'UAH'});if(h.pay&&h.pay[k])location.href=h.pay[k];else openForm();return}
if(e.target.closest('a[href^="tel:"],a[href*="t.me"],a[href^="viber:"]'))track('Contact',{content_name:root.dataset.page})});
/* quiz */
var qz=$('.quiz');
if(qz){var A={},qs=$$('.qs',qz),pg=$$('.pg i',qz),res=$('.res',qz),cur=0;
function go(n){cur=n;qs.forEach(function(x,i){x.classList.toggle('on',i===n)});pg.forEach(function(x,i){x.classList.toggle('on',i<=n)})}
function show(){var r=rec(A);try{localStorage.setItem('px_quiz',JSON.stringify({a:A,r:r.t,ts:Date.now()}))}catch(x){}
qs.forEach(function(x){x.classList.remove('on')});$('.pg',qz).style.display='none';$('.rt',res).textContent=r.t;$('.rp',res).textContent=r.p;$('.rd',res).textContent=r.d;$('.rg',res).href=r.h||('/'+r.u);var bb=$('.rb',res);if(r.buy){bb.style.display='';bb.dataset.buy=r.buy}else bb.style.display='none';res.classList.add('on');track('ViewContent',{content_name:'quiz_result'})}
qz.addEventListener('click',function(e){var o=e.target.closest('.opt');if(o){A[o.dataset.k]=o.dataset.v;A[o.dataset.k+'_t']=o.textContent.trim();if(cur+1>=qs.length)show();else go(cur+1);return}if(e.target.closest('.bk')){e.preventDefault();go(Math.max(0,cur-1))}});
var rec=function(c){
if(c.pain==='cart'){if(c.platform==='none')return{t:'Спершу власний сайт',p:'від $450',u:'horoshop',d:'Нагадування про кошик працюють там, де на сайті є кошик. Без власного сайту вони не спрацюють, тому чесно починаємо з сайту на Horoshop. Prom лишається вашим майданчиком.'};
var x={horoshop:['Покинуті кошики для Horoshop','1500 грн','Офіційна інтеграція, найшвидший запуск: 1–3 дні після доступів.'],other:['Покинуті кошики для вашого сайту','2500 грн','Спочатку перевіряємо сайт і підбираємо спосіб підключення. Якщо підключити неможливо, гроші повертаються.'],prom:['Покинуті кошики для Prom','3000 грн','Форма збору контакту в кошику та вікно «не втратьте кошик» перед виходом. Налаштування 1–3 дні.']}[c.platform];return{t:x[0],p:x[1],u:'koshyky',d:x[2],buy:c.platform}}
if(c.pain==='shopping')return c.platform==='none'?{t:'Спершу власний сайт',p:'від $450',u:'horoshop',d:'Google Shopping працює з власним сайтом. Спершу сайт на Horoshop із вашого Prom, потім запуск Shopping за $250.'}:{t:'Запуск Google Shopping',p:'$250',u:'google-shopping',d:'Налаштую Merchant Center, фід, трекінг і кампанії.'+(c.platform==='prom'?' Якщо у вас лише картки на Prom без власного сайту, спершу потрібен сайт на Horoshop.':'')};
if(c.pain==='meta')return{t:'Реклама в Instagram і Facebook',p:'вартість — після розмови',u:'meta-ads',d:'Нова аудиторія й ретаргетинг, заявки у вашу CRM. Бюджет на рекламу оплачуєте Meta напряму.'};
if(c.pain==='dash')return{t:'Дашборд у Power BI',p:'вартість — після розмови',u:'power-bi',d:'Зберу ваші дані в інтерактивний звіт: продажі, географія, канали.'};
if(c.pain==='unsure')return{t:'Безкоштовний розбір магазину',p:'безкоштовно',h:'#contact',d:'Подивлюсь ваш магазин і напишу, що зробити в першу чергу. Залиште контакт нижче на сторінці.'};
if(c.pain==='site')return c.platform==='horoshop'?{t:'Додаткові канали для вашого сайту',p:'Google Shopping — $250',u:'google-shopping',d:'Сайт на Horoshop у вас уже є. Наступні кроки: Google Shopping і повернення покупців із кошика (від 1500 грн).'}:{t:'Сайт на Horoshop із вашого Prom-магазину',p:'від $450',u:'horoshop',d:'Новий канал продажів: ваш магазин на власному сайті. Prom лишається майданчиком, а на сайт можна вести рекламу й підключати кошики та Google Shopping.'};
if(c.pain==='cards')return{t:'SEO і GEO карток товарів',p:'ціна — після аналізу',u:'seo-kartok',d:'Безкоштовно розберу 1–3 ваші картки за чек-листом і скажу, що виправити першим.'};
return{t:'Автоматизації для магазину',p:'вартість — після розмови',u:'avtomatyzatsiya',d:'Повторні продажі в Telegram, заявки в CRM, нагадування. Спочатку розмова про вашу рутину.'}};
go(0)}
if(root.dataset.page==='thanks'){var sp=new URLSearchParams(location.search),pr=sp.get('p'),vv=PRICE[pr];
if(pr){track('Purchase',vv?{value:vv,currency:'UAH',content_name:NAME[pr]}:{currency:'UAH'})}else{
var e1=$('.eyebrow'),t1=$('h1'),l1=$('.lead');e1&&(e1.textContent='Заявку отримано');t1&&(t1.innerHTML='Дякую! Відповім <em>протягом 1–2 днів</em>');l1&&(l1.textContent='Напишу вам у Telegram або зателефоную: подивлюсь магазин і скажу, що зробити в першу чергу. Якщо хочете швидше, напишіть у Telegram.');track('Lead',{content_name:'site_form'})}}
else track('ViewContent',{content_name:root.dataset.page})
}
d.readyState==='loading'?d.addEventListener('DOMContentLoaded',init):init();
})();
