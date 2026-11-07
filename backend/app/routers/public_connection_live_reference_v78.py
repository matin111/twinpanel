from __future__ import annotations

"""Final reference-only overlay. Uses existing *real* copy/import/download links."""
_MARKER = "TWINPANEL_PUBLIC_CONNECTION_LIVE_REFERENCE_V78"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECTION_LIVE_REFERENCE_V78 */
body.tp78-ui .ref67-user{position:relative!important}
body.tp78-ui .ref67-user small.tp78-active-account{color:#28f59b!important;font-size:12px!important;font-weight:850!important}
body.tp78-ui .ref67-user small.tp78-inactive-account{color:#ff9b9b!important;font-size:12px!important;font-weight:850!important}
body.tp78-ui .protocol-panel.active .panel-head{position:relative!important;isolation:isolate!important;overflow:hidden!important}
body.tp78-ui .protocol-panel.active .panel-head::after{content:"";position:absolute;inset:auto -5% -45px 40%;height:115px;pointer-events:none;background:radial-gradient(ellipse at 80% 50%,#8a32f6a0,transparent 70%);filter:blur(17px);z-index:-1}
body.tp78-ui .protocol-panel.active .panel-head>div:first-child{display:flex!important;align-items:center!important;gap:17px!important}
body.tp78-ui .tp78-protocol-emblem{display:grid;place-items:center;flex:0 0 60px;width:60px;height:60px;border-radius:20px;background:linear-gradient(135deg,#a336fa,#6824ea);font:900 30px Arial,sans-serif;color:white;box-shadow:0 0 24px #8a32f552}
body.tp78-ui .tp78-protocol-info{display:flex;flex-direction:column!important;justify-content:center!important;gap:5px!important}
body.tp78-ui .tp78-protocol-info>h3{margin:0!important}
body.tp78-ui .tp78-protocol-info>.tp78-protocol-state{color:#29f492!important;font-weight:850!important;font-size:13px!important;display:block!important}
body.tp78-ui .tp78-protocol-info>.tp78-protocol-count{color:#b8c7e4!important;font-size:11px!important;display:block!important}
body.tp78-ui .protocol-panel .tp78-ping{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:5px!important;border:1px solid #365f59!important;background:#132b34!important;color:#b7d7d2!important;border-radius:9px!important;padding:5px 7px!important;font:850 11px Arial,sans-serif!important;direction:ltr!important;white-space:nowrap!important;cursor:pointer!important;min-height:32px!important;min-width:69px!important;line-height:1.2!important}
body.tp78-ui .protocol-panel .tp78-ping[data-live="up"]{color:#b9ffe1!important;border-color:#276f53!important;background:#113e35!important}
body.tp78-ui .protocol-panel .tp78-ping[data-live="down"]{color:#bdc3d6!important;border-color:#52617a!important;background:#1a2440!important}
body.tp78-ui .protocol-panel .tp78-ping[aria-busy="true"]{opacity:.8!important}
body.tp78-ui .tp78-bars{display:inline-flex;align-items:flex-end;gap:2px;height:13px}
body.tp78-ui .tp78-bars i{display:block;width:3px;border-radius:1px;background:#20db70;height:6px}
body.tp78-ui .tp78-bars i:nth-child(2){height:9px}
body.tp78-ui .tp78-bars i:nth-child(3){height:12px}
body.tp78-ui .tp78-ping[data-live="down"] .tp78-bars i,
body.tp78-ui .tp78-ping[data-live="pending"] .tp78-bars i{background:#8491a8!important}
body.tp78-ui .tp78-reach{display:inline-flex;align-items:center;color:#25ef87;font-size:11px;font-weight:900;white-space:nowrap}
body.tp78-ui .tp78-reach[data-live="down"]{color:#aebad2}
body.tp78-ui .tp78-ping-cell{display:flex;align-items:center;gap:9px;justify-content:flex-start;direction:ltr}
body.tp78-ui .ref67-status{display:flex!important;align-items:center!important;gap:6px!important;direction:ltr!important}
body.tp78-ui .ref67-status.tp78-ready{font-size:0!important}
body.tp78-ui .ref67-status.tp78-ready .tp78-reach{font-size:11px!important}
body.tp78-ui .ref67-chip .ref71-rtt,body.tp78-ui .server-tab .ref71-rtt{display:none!important}
/* The original buttons, not recreated links: one uniform four-action footer. */
body.tp78-ui .protocol-panel[data-tp78-action-ready="1"] > .v52-multi-card,
body.tp78-ui .protocol-panel[data-tp78-action-ready="1"] > .v51-multi-card,
body.tp78-ui .protocol-panel[data-tp78-action-ready="1"] > .v34-subscription-card,
body.tp78-ui .protocol-panel[data-tp78-action-ready="1"] > .ref70-app-card,
body.tp78-ui .protocol-panel[data-tp78-action-ready="1"] > .v34-client-card{display:none!important}
body.tp78-ui .protocol-panel .tp78-action-footer{order:29!important;display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:10px!important;margin:24px 17px 26px!important;direction:ltr!important}
body.tp78-ui .tp78-action-footer>.tp78-footer-action{display:flex!important;align-items:center!important;justify-content:center!important;gap:12px!important;flex-direction:row!important;min-height:71px!important;padding:13px 8px!important;border:1px solid #384b72!important;border-radius:14px!important;color:#f9faff!important;background:linear-gradient(130deg,#192642,#111b34)!important;box-shadow:0 7px 17px #0003!important;text-align:center!important;text-decoration:none!important;cursor:pointer!important;font:850 12px Tahoma,Arial,sans-serif!important;direction:rtl!important}
body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="add"]{background:linear-gradient(120deg,var(--p),var(--s))!important;border-color:#b078ff!important;box-shadow:0 0 19px #8f3ffb75!important}
body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="app"]{order:1!important}
body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="copy"]{order:2!important}
body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="link"]{order:3!important}
body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="add"]{order:4!important}
body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="download"]{order:4!important}
body.tp78-ui .tp78-action-footer .tp78-icon{display:flex!important;align-items:center;justify-content:center;flex:0 0 auto}
body.tp78-ui .tp78-action-footer .tp78-icon svg{width:25px;height:25px;display:block;color:currentColor}
body.tp78-ui .tp78-action-footer .tp78-action-text{font-weight:850}
body.tp78-ui .protocol-panel .v54-v2ray-server-head{min-height:67px!important;gap:8px!important}
body.tp78-ui .tp78-node-tools{display:inline-flex!important;align-items:center!important;gap:7px!important;flex:0 0 auto!important;direction:ltr!important}
body.tp78-ui .tp78-node-tools button:not(.tp78-ping){display:inline-grid!important;place-items:center!important;border:1px solid #4b5d83!important;background:#243453!important;color:#fff!important;min-height:38px!important;min-width:39px!important;border-radius:10px!important;padding:5px!important;font-size:18px!important;cursor:pointer}
body.tp78-ui .tp78-node-tools button.tp78-add{background:linear-gradient(125deg,var(--p),var(--s))!important;border-color:#a86aff!important;box-shadow:0 0 12px #6735ff77!important;font-size:24px!important}
body.tp78-ui .tp78-node-tools button:disabled{opacity:.45!important;cursor:not-allowed!important}
body.tp78-ui .v54-v2ray-server-head > span:last-child:not(.tp74-node-identity){display:none!important}
body.tp78-ui .v54-v2ray-server-head .tp74-node-identity{direction:ltr!important;text-align:left!important}
body.tp78-ui .v54-v2ray-server-head .tp74-node-name{direction:ltr!important;text-align:left!important}
body.tp78-ui .tp77-native-row .tp78-native-meta{display:flex;align-items:center;gap:10px;direction:ltr}
body.tp78-ui .tp77-native-row button.tp78-ping{font-size:11px!important}
body.tp78-ui .ref67-row-actions{gap:7px!important}
body.tp78-ui .ref67-row-actions a.ref67-primary{background:linear-gradient(120deg,var(--p),var(--s))!important;border:1px solid #ac7eff!important;box-shadow:0 0 15px #7e40f34a!important}
body.tp78-ui .ref67-row-actions button{background:#26334e!important;color:#fff!important;border-color:#445677!important}
@media(max-width:720px){
 body.tp78-ui .protocols{grid-template-columns:repeat(4,minmax(0,1fr))!important;direction:ltr!important}
 body.tp78-ui .protocol-choice{display:flex!important;flex-direction:column!important;align-items:center!important;justify-content:center!important}
 body.tp78-ui .protocol-choice .protocol-icon{order:0!important}
 body.tp78-ui .protocol-choice .protocol-text{order:1!important;width:100%!important;display:block!important;text-align:center!important}
 body.tp78-ui .protocol-choice .protocol-text b{display:block!important;font-size:clamp(8px,2.4vw,11px)!important;line-height:1.25!important;color:#fff!important;white-space:nowrap!important;text-align:center!important;text-overflow:ellipsis!important;overflow:hidden!important}
 body.tp78-ui .protocol-choice .protocol-text small{display:none!important}
 body.tp78-ui .tp78-protocol-emblem{width:44px;height:44px;flex:0 0 44px;font-size:24px;border-radius:14px}
 body.tp78-ui .tp78-protocol-info>h3{font-size:17px!important}
 body.tp78-ui .protocol-panel .tp78-ping{min-width:54px!important;min-height:30px!important;padding:4px!important;font-size:10px!important}
 body.tp78-ui .ref67-row{display:grid!important;grid-template-columns:minmax(0,1fr) auto auto!important;gap:4px!important}
 body.tp78-ui .ref67-row-name{grid-column:1!important}
 body.tp78-ui .ref67-status{grid-column:2!important;grid-row:1!important;display:flex!important;justify-content:center!important}
 body.tp78-ui .ref67-row-actions{grid-column:3!important;grid-row:1!important;gap:4px!important}
 body.tp78-ui .ref67-row-actions a,body.tp78-ui .ref67-row-actions button{min-height:33px!important;min-width:32px!important;width:33px!important}
 body.tp78-ui .ref67-row .tp78-reach{display:none!important}
 body.tp78-ui .v54-v2ray-server-head{padding:8px!important;min-height:57px!important}
 body.tp78-ui .v54-v2ray-server-head .tp74-node-name strong{font-size:11px!important;white-space:nowrap!important}
 body.tp78-ui .v54-v2ray-server-head .tp74-node-name small{font-size:9px!important}
 body.tp78-ui .tp78-node-tools{gap:4px!important}
 body.tp78-ui .tp78-node-tools button:not(.tp78-ping){min-height:32px!important;min-width:30px!important;width:31px!important;font-size:16px!important}
 body.tp78-ui .tp78-node-tools button.tp78-add{font-size:20px!important}
 body.tp78-ui .tp77-native-row{gap:5px!important}
 body.tp78-ui .tp78-native-meta{gap:5px!important}
 body.tp78-ui .protocol-panel .tp78-action-footer{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:7px!important;margin:13px 8px 12px!important}
 body.tp78-ui .tp78-action-footer>.tp78-footer-action{min-height:82px!important;padding:9px 4px!important;flex-direction:column!important;gap:7px!important;font-size:10px!important;border-radius:12px!important}
 body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="add"]{grid-column:1 / -1!important;grid-row:1!important;min-height:58px!important;flex-direction:row!important;font-size:12px!important}
 body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="app"]{grid-row:2!important;grid-column:1!important}
 body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="copy"]{grid-row:2!important;grid-column:2!important}
 body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="link"]{grid-row:2!important;grid-column:3!important}
 body.tp78-ui .tp78-action-footer>.tp78-footer-action[data-kind="download"]{grid-column:1 / -1!important}
 body.tp78-ui .tp78-action-footer .tp78-icon svg{width:23px;height:23px}
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicConnectionLiveReferenceV78">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 document.body.classList.add('tp78-ui');
 const root=document.documentElement;root.classList.add('tp78-ui');
 const panels=()=>[...document.querySelectorAll('.protocol-panel')];
 const account=document.querySelector('.traffic .ref67-user small');
 const status=document.querySelector('.top .profile .status');
 if(account&&status){
   const valid=status.classList.contains('on');
   account.textContent=valid?'● اشتراک فعال':'● اشتراک غیرفعال';
   account.classList.toggle('tp78-active-account',valid);
   account.classList.toggle('tp78-inactive-account',!valid);
 }
 const markup={
  app:'<path d="M12 3v13m-5-5 5 5 5-5M4 18v3h16v-3"/>',
  copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  link:'<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2"/>',
  add:'<path d="m4 8 8-4 8 4-8 4-8-4zm0 5 8 4 8-4M4 17l8 4 8-4"/>',
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 18v3h16v-3"/>'
 };
 function icon(kind){
   const span=document.createElement('span');span.className='tp78-icon';
   span.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(markup[kind]||markup.copy)+'</svg>';
   return span;
 }
 function titlePanel(panel){
   if(panel.dataset.tp78Title)return;
   const group=panel.querySelector(':scope > .panel-head > div:first-child');
   const h3=group?.querySelector('h3');
   if(!group||!h3)return;
   panel.dataset.tp78Title='1';
   const name=h3.textContent.trim();
   const k=document.querySelector('.protocol-choice[data-protocol="'+panel.id+'"]');
   const symbol=k?.querySelector('.protocol-icon')?.textContent?.trim()?.slice(0,2)||name.slice(0,1);
   const emblem=document.createElement('span');emblem.className='tp78-protocol-emblem';
   emblem.textContent=symbol;
   const info=document.createElement('div');info.className='tp78-protocol-info';
   const state=document.createElement('span');state.className='tp78-protocol-state';state.textContent='● آماده';
   const count=document.createElement('span');count.className='tp78-protocol-count';
   const number=k?.querySelector('.protocol-text small')?.textContent?.trim()||'';
   count.textContent=number;
   group.replaceChildren(emblem,info);info.append(h3,state,count);
 }
 function actionKind(node){
   const label=String(node.textContent||'').trim();
   if(/افزودن همه|import all/i.test(label))return'add';
   if(/دانلود همه کانفیگ|download all/i.test(label))return'download';
   if(/کپی همه کانفیگ|کپی JSON|کپی YAML|copy all/i.test(label))return'copy';
   if(/کپی لینک|subscription link|مولتی.?لینک/i.test(label))return'link';
   return '';
 }
 function actionFooter(panel){
   if(panel.dataset.tp78ActionReady==='1')return;
   const multi=panel.querySelector(':scope > .v52-multi-card, :scope > .v51-multi-card');
   const sub=panel.querySelector(':scope > .v34-subscription-card');
   const actionRoot=multi?.querySelector('.v51-multi-actions')||sub?.querySelector('.v34-actions');
   if(!actionRoot||!actionRoot.children.length)return;
   const candidates=[...actionRoot.children].filter(el=>el.matches('a,button'));
   const seen={};const selected=[];
   candidates.forEach(el=>{
     const kind=actionKind(el);
     if(!kind||seen[kind])return;
     seen[kind]=true;selected.push({kind,el});
   });
   const download=panel.querySelector(':scope > .ref70-app-card a.ref69-download-cta[href]:not([hidden])')
      ||panel.querySelector(':scope > .v34-client-card a[href]');
   if(download&&download.getAttribute('href'))selected.push({kind:'app',el:download});
   if(!selected.length)return;
   const footer=document.createElement('nav');footer.className='tp78-action-footer';
   footer.setAttribute('aria-label','عملیات اشتراک');
   selected.forEach(item=>{
     const el=item.el;
     // Moving the ORIGINAL element preserves its actual href, click handlers,
     // generated config formats and OS-aware app source. No fake proxy button.
     el.classList.add('tp78-footer-action');
     el.dataset.kind=item.kind;
     if(item.kind==='app')el.textContent='دانلود برنامه';
     else if(item.kind==='copy')el.textContent='کپی همه کانفیگ‌ها';
     else if(item.kind==='link')el.textContent='کپی لینک اشتراک';
     else if(item.kind==='add')el.textContent='افزودن همه به برنامه';
     el.prepend(icon(item.kind));
     const text=document.createElement('span');text.className='tp78-action-text';
     // Wrap only the button's known text node; do not replace the live action.
     [...el.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).forEach(n=>text.append(n));
     el.append(text);
     footer.append(el);
   });
   panel.append(footer);
   panel.dataset.tp78ActionReady='1';
 }
 const tokenPart=location.pathname.match(/^\/v1\/connect\/([^/]+)/);
 const pingURL=id=>location.origin+'/v1/connect/'+(tokenPart?tokenPart[1]:'')+'/node-ping/'+encodeURIComponent(id);
 const values=new Map(),inflight=new Map(),last=new Map();
 function pingButton(nodeId){
   if(!/^[1-9]\d*$/.test(String(nodeId||'')))return null;
   const button=document.createElement('button');button.type='button';
   button.className='tp78-ping';button.dataset.tp78Node=String(nodeId);
   button.dataset.live='pending';button.title='تأخیر واقعی از سرور پنل تا نود؛ برای سنجش مجدد کلیک کنید';
   button.setAttribute('aria-label','سنجش پینگ واقعی نود '+nodeId);
   const number=document.createElement('span');number.className='tp78-ping-value';number.textContent='— ms';
   const bars=document.createElement('span');bars.className='tp78-bars';bars.setAttribute('aria-hidden','true');bars.innerHTML='<i></i><i></i><i></i>';
   button.append(number,bars);
   button.addEventListener('click',event=>{
     event.stopPropagation();event.preventDefault();void probe(String(nodeId),true);
   });
   return button;
 }
 function paint(id,value){
   document.querySelectorAll('.tp78-ping[data-tp78-node="'+id+'"]').forEach(button=>{
     const up=value&&typeof value.ms==='number'&&Number.isFinite(value.ms);
     button.dataset.live=up?'up':value?'down':'pending';
     button.querySelector('.tp78-ping-value').textContent=up?(Math.round(value.ms*10)/10)+' ms':'— ms';
     button.title=up?'سنجش زنده '+(value.method==='icmp'?'ICMP':'TCP')+' از سرور پنل تا نود؛ برای تست مجدد بزنید':'پاسخ معتبر دریافت نشد؛ برای تست مجدد بزنید';
   });
   document.querySelectorAll('.tp78-reach[data-tp78-node="'+id+'"]').forEach(label=>{
     const up=value&&typeof value.ms==='number'&&Number.isFinite(value.ms);
     label.dataset.live=up?'up':'down';label.textContent=up?'● آنلاین':'● پاسخ ندارد';
   });
 }
 async function probe(id,manual){
   if(!tokenPart||inflight.has(id))return;
   if(Date.now()-(last.get(id)||0)<3100){
     if(manual)toast('برای تست مجدد چند ثانیه صبر کنید');
     return;
   }
   last.set(id,Date.now());
   document.querySelectorAll('.tp78-ping[data-tp78-node="'+id+'"]').forEach(el=>el.setAttribute('aria-busy','true'));
   const task=(async()=>{
     try{
       const response=await fetch(pingURL(id),{cache:'no-store',headers:{Accept:'application/json'}});
       if(!response.ok)throw new Error(String(response.status));
       const data=await response.json();
       const valid=data.scope==='panel_to_node'&&data.node_id===Number(id)&&typeof data.ms==='number'&&Number.isFinite(data.ms)&&data.ms>=0;
       values.set(id,valid?data:{ms:null});
     }catch(_error){values.set(id,{ms:null});}
     finally{
       paint(id,values.get(id));
       document.querySelectorAll('.tp78-ping[data-tp78-node="'+id+'"]').forEach(el=>el.removeAttribute('aria-busy'));
       inflight.delete(id);
     }
   })();
   inflight.set(id,task);await task;
 }
 function toast(message){
   const el=document.getElementById('toast');
   if(el){el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),1400)}
 }
 function addReach(host,id){
   const label=document.createElement('span');label.className='tp78-reach';label.dataset.tp78Node=String(id);
   label.textContent='● در حال بررسی';host.append(label);return label;
 }
 function modernPings(panel){
   const tabs=[...panel.querySelectorAll('.server-tab[data-server][data-node-id]')];
   const rows=[...panel.querySelectorAll('.ref67-list .ref67-row')];
   tabs.forEach((tab,index)=>{
     const id=tab.dataset.nodeId;
     const row=rows[index];
     if(!row||!id||row.dataset.tp78PingMounted)return;
     row.dataset.tp78PingMounted='1';
     let cell=row.querySelector('.ref67-status');
     if(!cell){cell=document.createElement('div');cell.className='ref67-status';row.append(cell)}
     cell.classList.add('tp78-ready');cell.replaceChildren();
     const button=pingButton(id);
     if(!button)return;
     const wrapper=document.createElement('div');wrapper.className='tp78-ping-cell';
     wrapper.append(button);addReach(wrapper,id);cell.append(wrapper);
     if(values.has(id))paint(id,values.get(id));
   });
 }
 function nativePings(panel){
   const tabs=[...panel.querySelectorAll('.server-tab[data-server][data-node-id]')];
   const rows=[...panel.querySelectorAll('.tp77-native-list .tp77-native-row')];
   tabs.forEach((tab,index)=>{
     const row=rows[index],id=tab.dataset.nodeId;
     if(!id||!row||row.dataset.tp78PingMounted)return;
     row.dataset.tp78PingMounted='1';
     const label=row.querySelector('.tp77-native-label');
     if(!label)return;
     const meta=document.createElement('div');meta.className='tp78-native-meta';
     const ping=pingButton(id);
     if(!ping)return;
     meta.append(ping);row.insertBefore(meta,row.lastElementChild);
     if(values.has(id))paint(id,values.get(id));
   });
 }
 async function copy(text){
   if(!text)return false;
   try{if(navigator.clipboard&&isSecureContext){await navigator.clipboard.writeText(text);return true}}catch(_e){}
   const area=document.createElement('textarea');area.value=text;
   area.style.position='fixed';area.style.left='-9999px';document.body.append(area);
   area.select();let ok=false;try{ok=document.execCommand('copy')}catch(_e){}area.remove();return ok;
 }
 function v2rayPings(panel){
   panel.querySelectorAll('.v54-v2ray-server[data-node-id],.v54-v2ray-server[data-country-code]').forEach(card=>{
     const id=card.dataset.nodeId;
     if(!id||card.dataset.tp78PingMounted)return;
     const head=card.querySelector('.v54-v2ray-server-head');
     if(!head)return;
     card.dataset.tp78PingMounted='1';
     const tools=document.createElement('div');tools.className='tp78-node-tools';
     const ping=pingButton(id);if(ping)tools.append(ping);
     const copyNode=document.createElement('button');copyNode.type='button';copyNode.className='tp78-copy';copyNode.textContent='⧉';
     copyNode.title='کپی تمام کانفیگ‌های واقعی این نود';
     const uris=[...card.querySelectorAll('.v54-v2ray-profile[data-tp78-uri]')].map(x=>x.dataset.tp78Uri).filter(Boolean);
     copyNode.disabled=uris.length===0;
     copyNode.addEventListener('click',async event=>{
       event.preventDefault();event.stopPropagation();
       toast((await copy(uris.join('\n')))?'کانفیگ‌های این نود کپی شدند':'کپی انجام نشد');
     });
     const add=document.createElement('button');add.className='tp78-add';add.type='button';add.textContent='+';
     add.title='نمایش سه اتصال واقعی همین نود برای افزودن به برنامه';
     add.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();head.click()});
     tools.append(copyNode,add);head.append(tools);
     if(values.has(id))paint(id,values.get(id));
   });
 }
 let ticks=0;
 const timer=setInterval(()=>{
   panels().forEach(panel=>{
     titlePanel(panel);
     modernPings(panel);nativePings(panel);v2rayPings(panel);
     actionFooter(panel);
   });
   const current=document.querySelector('.protocol-panel.active');
   const ids=new Set([...current?.querySelectorAll('.tp78-ping[data-tp78-node]')||[]].map(b=>b.dataset.tp78Node));
   ids.forEach(id=>{if(!values.has(id)&&!inflight.has(id))void probe(id,false)});
   if(++ticks>=32)clearInterval(timer);
 },350);
})();
</script>
"""

def refine_public_connection_live_reference_v78(source: str) -> str:
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + "\n<!-- " + _MARKER + " -->\n</body>", 1)
