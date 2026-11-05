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
/* modal */
var md=$('.md');
function openMd(p,t,s){if(!md)return;var f=$('form',md);if(f){f.dataset.p=p||'';f.dataset.f=p&&PRICE[p]?'order':'lead';f.style.display='';var hh=$('h3',md);hh&&t&&(hh.textContent=t);var ld=$('.lead',md);ld&&s&&(ld.textContent=s);var b=$('button[type=submit]',f);b&&(b.disabled=!1,b.textContent='Надіслати')}var ok=$('.ok2',md);ok&&ok.classList.remove('on');md.classList.add('open');setTimeout(function(){var i=$('input',md);i&&i.focus()},60)}
function closeMd(){md&&md.classList.remove('open')}
if(md){$('.x',md).addEventListener('click',closeMd);md.addEventListener('click',function(e){e.target===md&&closeMd()});addEventListener('keydown',function(e){e.key==='Escape'&&closeMd()})}
d.addEventListener('click',function(e){
var o=e.target.closest('[data-open]');if(o){e.preventDefault();openMd(o.dataset.p,o.dataset.t,o.dataset.s);return}
var by=e.target.closest('[data-buy]');if(by){e.preventDefault();var k=by.dataset.buy;track('InitiateCheckout',{content_name:NAME[k],value:PRICE[k],currency:'UAH'});if(h.pay&&h.pay[k])location.href=h.pay[k];else openMd(k,'Замовити: '+NAME[k].replace('Покинуті кошики: ','кошики, '),'Залиште контакт — зв’яжусь, надішлю рахунок і домовимось про доступи. Ціна: '+PRICE[k]+' грн, разово.');return}
if(e.target.closest('a[href^="tel:"],a[href*="t.me"],a[href^="viber:"]'))track('Contact',{content_name:root.dataset.page})});
/* messenger widget */
(function(){var TG=h.tg||'https://t.me/Vadim_pixsell',w=d.createElement('div')
w.className='mw'
w.innerHTML='<div class="mw-l"><button type="button" class="mw-i mw-c" hidden><i style="background:#16A34A"><svg viewBox="0 0 24 24" width="20" height="20" fill="#fff"><path d="M4 3h16a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/></svg></i>Чат на сайті</button><a class="mw-i" href="'+TG+'" target="_blank" rel="noopener"><i style="background:#2AABEE"><svg viewBox="0 0 24 24" width="20" height="20" fill="#fff"><path d="M21.5 3.2 2.7 10.5c-.9.4-.9 1.1-.2 1.3l4.8 1.5 1.8 5.6c.2.6.4.8.9.8s.6-.2.9-.5l2.3-2.3 4.7 3.5c.9.5 1.5.2 1.7-.8l3.1-14.6c.3-1.2-.5-1.7-1.2-1.4zM8.5 13.2l9.1-5.7c.4-.3.8-.1.5.2l-7.6 6.9-.3 3.2z"/></svg></i>Telegram</a><a class="mw-i" href="viber://chat?number=%2B380635659707"><i style="background:#7360F2"><svg viewBox="0 0 24 24" width="20" height="20" fill="#fff"><path d="M12 2C6.9 2 3.5 3.1 2.6 7.6c-.5 2.6-.5 5.5.1 7.6.4 1.6 1.4 2.5 2.7 3V22l3-2.9c1.2.3 2.4.3 3.6.3 5.1 0 8.5-1.1 9.4-5.6.5-2.6.5-5.5-.1-7.6C20.3 3.1 17.1 2 12 2zm4.4 12.6c-.2.5-1 1-1.6 1.1-.4.1-.9.1-2.9-.7-2.5-1.1-4.2-3.7-4.3-3.9-.1-.2-1-1.3-1-2.5s.6-1.8.9-2c.2-.2.5-.3.7-.3h.5c.2 0 .4 0 .5.4l.8 1.9c.1.2.1.3 0 .5l-.3.4-.3.3c-.1.1-.2.3-.1.5.5.8 1.1 1.5 1.9 2 .3.2.7.4 1.1.6.2.1.3 0 .5-.1l.6-.7c.1-.2.3-.2.5-.1l1.8.9c.2.1.3.2.3.3 0 .2 0 .8-.3 1.4z"/></svg></i>Viber</a><a class="mw-i" href="tel:+380635659707"><i style="background:#16A34A"><svg viewBox="0 0 24 24" width="20" height="20" fill="#fff"><path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z"/></svg></i>Подзвонити</a></div><button type="button" class="mw-b" aria-label="Написати нам" aria-expanded="false"><svg class="mo" viewBox="0 0 24 24" width="26" height="26" fill="#fff"><path d="M4 3h16a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/></svg><svg class="mx" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg></button>'
root.appendChild(w)
var wb=w.querySelector('.mw-b')
function wc(o){w.classList.toggle('open',o)
wb.setAttribute('aria-expanded',o?'true':'false')}
wb.addEventListener('click',function(e){e.stopPropagation()
wc(!w.classList.contains('open'))})
d.addEventListener('click',function(e){if(!w.contains(e.target))wc(!1)})
addEventListener('keydown',function(e){e.key==='Escape'&&wc(!1)})
var cb=w.querySelector('.mw-c'),sr,tries=0
function lc(){var el=d.querySelector('sp-live-chat'),r=el&&el.shadowRoot,f=r&&r.querySelector('.widget-fab'),wr=r&&r.querySelector('.widget-wrapper')
if(!f||!wr){if(++tries<200)setTimeout(lc,150)
return}
sr=r
var st=d.createElement('style')
st.textContent='.widget-fab,.widget-fab-shadow{display:none!important}'
r.appendChild(st)
r.querySelector('main.root').style.setProperty('--theme-color','#16A34A')
function fix(){var c=wr.className
if(c.indexOf('widget-left')>-1)wr.className=c.replace('widget-left','widget-right')}
fix()
new MutationObserver(fix).observe(wr,{attributes:!0,attributeFilter:['class']})
cb.hidden=!1}
lc()
cb.addEventListener('click',function(){wc(!1)
var f=sr&&sr.querySelector('.widget-fab')
if(f)f.click()
track('Contact',{content_name:'livechat'})})})()
/* forms */
var tg=function(t){return(h.tg||'https://t.me/Vadim_pixsell')+'?text='+encodeURIComponent(t)};
function send(p){p.page=root.dataset.page
p.url=location.href
p.utm=utm
p.ts=new Date().toISOString()
if(!h.hook)return Promise.resolve('tg')
var b=new URLSearchParams({k:h.key||'',type:p.type||'',name:p.name||'',phone:p.contact||'',site:p.site||'',page:p.page,url:p.url,utm:typeof p.utm==='string'?p.utm:JSON.stringify(p.utm||''),msg:msg(p)})
return fetch(h.hook,{method:'POST',mode:'no-cors',body:b,keepalive:!0}).then(function(){return'ok'}).catch(function(){return'err'})}
function msg(t){return['Заявка з сайту Pixsell',t.product&&'Послуга: '+t.product,t.name&&'Імʼя: '+t.name,t.contact&&'Контакт: '+t.contact,t.site&&'Сайт: '+t.site,t.platform&&'Платформа: '+t.platform,t.pain&&'Задача: '+t.pain,t.orders&&'Замовлень на місяць: '+t.orders].filter(Boolean).join('\n')}
function done(box,st,p){var ok=$('.ok2',box);if(!ok)return;ok.classList.add('on');var b=$('b',ok),pp=$('p',ok);if(st==='ok'){b.textContent='Готово';pp.textContent='Дякую! Відповім протягом 1–2 днів у Telegram або по телефону.';track('Lead',{content_name:p.product||p.type})}else{b.textContent='Ще один крок';pp.innerHTML='Щоб заявка дійшла, натисніть кнопку нижче — відкриється Telegram з уже заповненим повідомленням.<br><br><a class="b s" href="'+tg(msg(p))+'" target="_blank" rel="noopener">Надіслати в Telegram</a>'}}
$$('form[data-f]').forEach(function(f){f.addEventListener('submit',function(e){e.preventDefault();var v={};new FormData(f).forEach(function(x,k){v[k]=x});var p={type:f.dataset.f,product:NAME[f.dataset.p]||'',name:v.name,contact:v.contact,site:v.site};var b=$('button[type=submit]',f);b&&(b.disabled=!0,b.textContent='Надсилаю…');send(p).then(function(st){var box=f.closest('.bx,.fin,.fcard')||f.parentNode;f.style.display='none';done(box,st,p)})})});
/* quiz */
var qz=$('.quiz');
if(qz){var A={},qs=$$('.qs',qz),pg=$$('.pg i',qz),res=$('.res',qz),cur=0;
function go(n){cur=n;qs.forEach(function(x,i){x.classList.toggle('on',i===n)});pg.forEach(function(x,i){x.classList.toggle('on',i<=n)})}
qz.addEventListener('click',function(e){var o=e.target.closest('.opt');if(o){A[o.dataset.k]=o.dataset.v;A[o.dataset.k+'_t']=o.textContent.trim();go(cur+1);return}if(e.target.closest('.bk')){e.preventDefault();go(Math.max(0,cur-1))}});
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
var qf=$('form',qz);
qf&&qf.addEventListener('submit',function(e){e.preventDefault();var v={};new FormData(qf).forEach(function(x,k){v[k]=x});var r=rec(A),p={type:'quiz',platform:A.platform_t,pain:A.pain_t,orders:A.orders_t,name:v.name,contact:v.contact,site:v.site,product:r.t+' ('+r.p+')'};var b=$('button[type=submit]',qf);b.disabled=!0;b.textContent='Надсилаю…';
send(p).then(function(st){qs.forEach(function(x){x.classList.remove('on')});$('.pg',qz).style.display='none';$('.rt',res).textContent=r.t;$('.rp',res).textContent=r.p;$('.rd',res).textContent=r.d;$('.rg',res).href=r.h||('/'+r.u);var bb=$('.rb',res);if(r.buy){bb.style.display='';bb.dataset.buy=r.buy}else bb.style.display='none';var n=$('.rn',res);if(st==='ok'){n.textContent='Відповіді передано. Напишу вам у Telegram або зателефоную протягом 1–2 днів.';track('Lead',{content_name:'quiz',value:0})}else n.innerHTML='Щоб відповіді дійшли, натисніть: <a class="more" style="border-bottom:1px solid #e30610" href="'+tg(msg(p))+'" target="_blank" rel="noopener">надіслати в Telegram</a>';res.classList.add('on')})});
go(0)}
if(root.dataset.page==='thanks'){var pr=new URLSearchParams(location.search).get('p'),vv=PRICE[pr];track('Purchase',vv?{value:vv,currency:'UAH',content_name:NAME[pr]}:{currency:'UAH'})}else track('ViewContent',{content_name:root.dataset.page})
}
d.readyState==='loading'?d.addEventListener('DOMContentLoaded',init):init();
})();
