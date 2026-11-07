from __future__ import annotations

# Final, presentation-only overrides for the user-approved compact phone layout.
# The underlying protocol and client delivery handlers are never modified.
_MARKER = "TWINPANEL_PUBLIC_CONNECT_APPROVED_PHONE_V74"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_APPROVED_PHONE_V74 */
body.tp74-approved .ref69-protocol-os {display:none!important}
body.tp74-approved .ref70-app-card{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:10px!important}
body.tp74-approved .ref70-app-card .ref69-download-cta{margin-inline-start:auto}
body.tp74-approved .ref70-app-card .ref69-download-empty:not([hidden]){display:block}
body.tp74-approved .ref70-app-card .ref69-download-empty[hidden]{display:none!important}
/* One OS-aware download control per protocol, not a duplicate default client. */
body.tp74-approved .protocol-panel:has(.ref70-app-card .ref69-download-cta:not([hidden])) .v34-client-card{
 display:none!important
}
/* The V54 component, not V67's one-URI-per-server approximation, is the
   V2Ray source of truth: every active node has three real inbound profiles. */
body.tp74-approved.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"][data-v54-groups-loaded="1"] .ref67-list,
body.tp74-approved.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"][data-v54-groups-loaded="1"] .ref67-tabs,
body.tp74-approved.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] .server-tabs{
 display:none!important
}
body.tp74-approved.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] .v54-v2ray-groups{
 display:grid!important;gap:9px!important;margin:12px 15px 18px!important;
}
body.tp74-approved .v54-v2ray-server{
 border:1px solid #394767!important;border-radius:14px!important;
 background:linear-gradient(125deg,#14213a,#121a32)!important;overflow:hidden
}
body.tp74-approved .v54-v2ray-server-head{
 min-height:60px!important;display:flex!important;align-items:center!important;
 padding:10px 13px!important;text-align:right!important;justify-content:space-between!important;
 gap:10px!important;cursor:pointer
}
body.tp74-approved .v54-v2ray-server-head .tp74-node-identity{display:flex;align-items:center;gap:10px}
body.tp74-approved .v54-v2ray-server-head .tp74-node-name{display:grid;gap:3px}
body.tp74-approved .v54-v2ray-server-head .tp74-node-name strong{font-size:13px;color:#fff}
body.tp74-approved .v54-v2ray-server-head .tp74-node-name small{font-size:10px;color:#b6c7e1}
body.tp74-approved .v54-v2ray-server.open .v54-v2ray-profiles{
 display:grid!important;grid-template-columns:1fr!important
}
body.tp74-approved .v54-v2ray-profile{min-height:56px!important;border-top:1px solid #31405d!important}
body.tp74-approved .v54-v2ray-profile-title{font-size:12px!important}
body.tp74-approved .v54-v2ray-profile-meta{font-size:10px!important}
body.tp74-approved .tp74-flag{display:inline-block;flex:0 0 auto;width:25px;height:19px;border-radius:4px;overflow:hidden;
 box-shadow:0 1px 6px #0006;vertical-align:middle}
body.tp74-approved .tp74-flag svg,body.tp74-approved .tp74-flag img{display:block!important;width:100%!important;
 height:100%!important;object-fit:cover!important}
body.tp74-approved .tp74-country-chip{display:inline-flex;align-items:center;gap:7px;
 padding:6px 10px;background:#192543;border:1px solid #40517b;border-radius:11px;
 font:800 11px system-ui,Arial,sans-serif;color:#e6eeff}
body.tp74-approved .tp74-country-bar{display:flex;align-items:center;gap:7px;overflow-x:auto;padding:10px 15px 0;
 scrollbar-width:none;direction:rtl}
body.tp74-approved .tp74-country-bar::-webkit-scrollbar{display:none}
body.tp74-approved .tp74-country-chip.active{border-color:var(--p)!important;box-shadow:0 0 12px color-mix(in srgb,var(--p) 35%,transparent)!important}
body.tp74-approved .ref67-chip:has(.tp73-flag) .tp73-flag,
body.tp74-approved .ref67-row .tp73-flag{width:25px!important;height:19px!important}
@media(max-width:720px){
 html body.tp74-approved{background:#080d1d!important}
 body.tp74-approved .page{width:calc(100% - 20px)!important;max-width:500px!important;
  margin-inline:auto!important;padding:10px 0 24px!important}
 body.tp74-approved .topin{height:60px!important;padding:0!important;width:calc(100% - 20px)!important}
 body.tp74-approved .brand b{font-size:20px!important}
 body.tp74-approved .traffic{margin:0 0 10px!important;display:grid!important;gap:8px!important;
  border-radius:15px!important;padding:9px!important;min-height:0!important}
 body.tp74-approved .traffic .ref67-user{min-height:54px!important;padding:9px 11px!important;
  width:100%!important;border-radius:13px!important}
 body.tp74-approved .traffic .ref67-user strong{font-size:15px!important}
 body.tp74-approved .traffic .ref67-user small{font-size:10px!important}
 body.tp74-approved .traffic .ref67-decoration{display:none!important}
 body.tp74-approved .traffic .stats{display:grid!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:0!important}
 body.tp74-approved .traffic .stat{display:flex!important;min-height:65px!important;
  align-items:center!important;justify-content:center!important;gap:6px!important;
  padding:4px 3px!important;text-align:center!important}
 /* Dates are subscription data, never remove on phones. */
 body.tp74-approved .traffic .stat:nth-child(n+4){display:flex!important}
 body.tp74-approved .traffic .stat strong{font-size:15px!important;font-weight:850!important;white-space:nowrap}
 body.tp74-approved .traffic .stat small{font-size:10px!important}
 body.tp74-approved .ref67-categories{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;
  gap:5px!important;margin:4px 0 10px!important;padding:4px 0 8px!important}
 body.tp74-approved .ref67-filter{min-width:0!important;width:100%!important;height:36px!important;
  padding:4px 2px!important;font-size:10px!important;border-radius:10px!important}
 body.tp74-approved .protocols{display:grid!important;
  grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:6px!important;margin:7px 0 12px!important}
 body.tp74-approved .protocol-choice{display:flex!important;flex-direction:column!important;align-items:center!important;
  justify-content:center!important;min-height:78px!important;height:78px!important;padding:7px 3px!important;
  gap:6px!important;text-align:center!important;border-radius:12px!important}
 body.tp74-approved .protocol-choice[hidden],
 body.tp74-approved .protocol-choice.ref67-hidden{display:none!important}
 body.tp74-approved .protocol-choice .protocol-icon{width:38px!important;height:38px!important;
  flex-basis:38px!important;flex-shrink:0!important}
 body.tp74-approved .protocol-choice .protocol-text{width:100%!important;min-width:0!important;text-align:center!important}
 body.tp74-approved .protocol-choice .protocol-text b{font-size:10px!important;line-height:1.2!important;
  white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
 body.tp74-approved .protocol-choice .protocol-text small{display:none!important}
 body.tp74-approved .protocol-panel{margin:9px 0!important;border-radius:16px!important;overflow:visible!important}
 body.tp74-approved .protocol-panel .panel-head{min-height:74px!important;padding:13px!important;border-radius:15px 15px 0 0}
 body.tp74-approved .protocol-panel .panel-head h3{font-size:17px!important}
 body.tp74-approved .ref70-app-card{display:flex!important;flex-direction:row!important;
  align-items:center!important;gap:7px!important;margin:9px!important;padding:9px!important;
  border-radius:12px!important;min-height:47px!important}
 body.tp74-approved .ref70-app-card strong{font-size:11px!important}
 body.tp74-approved .ref70-app-card .ref69-download-cta{width:auto!important;min-width:90px!important;
  min-height:36px!important;flex:0 0 auto!important;padding:7px 10px!important;font-size:10px!important}
 body.tp74-approved .ref67-tabs{gap:6px!important;padding:10px 8px 6px!important}
 body.tp74-approved .ref67-chip{font-size:10px!important;min-height:35px!important;gap:5px!important;padding:7px!important}
 body.tp74-approved .tp74-country-bar{padding:9px 8px 4px!important;gap:6px}
 body.tp74-approved .tp74-country-chip{font-size:10px;padding:7px 8px}
 body.tp74-approved .ref67-list{margin:4px 8px 10px!important}
 body.tp74-approved .ref67-row{min-height:55px!important;padding:7px 8px!important}
 body.tp74-approved .ref67-row-name{gap:8px!important}
 body.tp74-approved .ref67-row-name b{font-size:11px!important}
 body.tp74-approved .ref67-row-actions a,body.tp74-approved .ref67-row-actions button{
  width:35px!important;min-width:35px!important;height:35px!important;min-height:35px!important}
 body.tp74-approved .v54-v2ray-groups{margin:7px 8px 12px!important;gap:7px!important}
 body.tp74-approved .v54-v2ray-server-head{min-height:54px!important;padding:8px!important}
 body.tp74-approved .v54-v2ray-profile{grid-template-columns:minmax(0,1fr) auto!important;
  padding:8px!important;gap:6px!important;min-height:50px!important}
 body.tp74-approved .v54-v2ray-profile-actions{justify-content:flex-end!important}
 body.tp74-approved .v54-v2ray-profile-actions button,
 body.tp74-approved .v54-v2ray-profile-actions a{min-height:33px!important;font-size:10px!important}
 body.tp74-approved .ref67-footer{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:6px!important;margin:9px!important}
 body.tp74-approved .ref67-footer>*{min-width:0!important;min-height:43px!important;font-size:10px!important}
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicConnectApprovedPhoneV74">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 const body=document.body;body.classList.add('tp74-approved');
 // Preserve the OS autodetection already performed by the original delivery
 // system and by V69. No five-OS selector is needed inside each protocol.
 document.querySelectorAll('.ref69-protocol-os').forEach(x=>x.setAttribute('hidden',''));
 const metadata={DE:'Germany',US:'United States',TR:'Türkiye'};
 const ns='http://www.w3.org/2000/svg';
 const regionName=typeof Intl!=='undefined'&&Intl.DisplayNames
   ?new Intl.DisplayNames(['en'],{type:'region'}):null;
 function flag(code){
   const span=document.createElement('span');span.className='tp74-flag';
   const x=String(code||'').toUpperCase();
   span.setAttribute('role','img');span.setAttribute('aria-label',x+' flag');
   if(!/^[A-Z]{2}$/.test(x)){span.textContent='🌐';return span;}
   const svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 32 24');
   if(x==='DE')svg.innerHTML='<path d="M0 0h32v8H0z" fill="#111"/><path d="M0 8h32v8H0z" fill="#dd172c"/><path d="M0 16h32v8H0z" fill="#ffce00"/>';
   else if(x==='TR')svg.innerHTML='<path d="M0 0h32v24H0z" fill="#e30a17"/><circle cx="13" cy="12" r="7" fill="#fff"/><circle cx="15" cy="12" r="5.5" fill="#e30a17"/><path d="m20 7 1.1 3.4h3.6l-2.9 2.1 1.1 3.3-2.9-2.1-2.9 2.1 1.1-3.3-2.9-2.1h3.6z" fill="#fff"/>';
   else if(x==='US'){
     svg.innerHTML='<path d="M0 0h32v24H0z" fill="#fff"/>';
     for(let i=0;i<7;i++){const p=document.createElementNS(ns,'rect');
       p.setAttribute('x','0');p.setAttribute('y',String(i*48/13));p.setAttribute('width','32');
       p.setAttribute('height',String(24/13));p.setAttribute('fill','#b22234');svg.appendChild(p);}
     const canton=document.createElementNS(ns,'rect');canton.setAttribute('width','13');
     canton.setAttribute('height','13');canton.setAttribute('fill','#3c3b6e');svg.appendChild(canton);
   }else{
     const img=document.createElement('img');img.alt=x;img.loading='lazy';
     img.src='https://flagcdn.com/w40/'+x.toLowerCase()+'.png';
     img.addEventListener('error',()=>{span.textContent=x;});
     span.appendChild(img);return span;
   }
   span.appendChild(svg);return span;
 }
 function normalizedName(code){
   return metadata[code]||(regionName?.of(code)||code||'Server');
 }
 function refreshV2Ray(){
   for(const panel of document.querySelectorAll('.protocol-panel[data-v54-v2ray="1"]')){
     const groups=panel.querySelector('.v54-v2ray-groups');
     if(!groups)return;
     const cards=[...groups.querySelectorAll(':scope > .v54-v2ray-server')];
     if(!cards.length)continue;
     const enabled=cards.every(x=>x.querySelectorAll('.v54-v2ray-profile').length>0);
     if(!enabled)continue; // Don't hide fallback controls for an incomplete server.
     panel.dataset.v54GroupsLoaded='1';
     const barId='tp74-country-navigation';
     let bar=panel.querySelector(':scope > .'+barId);
     if(!bar){
       bar=document.createElement('nav');bar.className='tp74-country-bar '+barId;
       bar.setAttribute('aria-label','سرورهای V2Ray');
       groups.insertAdjacentElement('beforebegin',bar);
     }
     cards.forEach((card,index)=>{
       const code=String(card.dataset.countryCode||'').toUpperCase();
       const nodeId=String(card.dataset.nodeId||index+1);
       // Keep the node itself compact like the approved reference. Its three
       // real V2Ray profiles remain available by expanding the server card.
       const head=card.querySelector('.v54-v2ray-server-head');
       if(head&&head.dataset.tp74Styled!=='1'){
         head.dataset.tp74Styled='1';head.setAttribute('aria-expanded',card.classList.contains('open')?'true':'false');
         const name=document.createElement('span');name.className='tp74-node-name';
         const strong=document.createElement('strong');strong.textContent=normalizedName(code)+' - '+nodeId;
         const small=document.createElement('small');small.textContent='V2Ray / Xray · ۳ اتصال';
         name.append(strong,small);
         const identity=document.createElement('span');identity.className='tp74-node-identity';
         identity.append(flag(code),name);
         head.replaceChildren(identity);
         const total=document.createElement('span');total.textContent='۳ اتصال';head.appendChild(total);
       }
       if(!bar.querySelector('[data-tp74-node="'+index+'"]')){
         const button=document.createElement('button');button.type='button';
         button.className='tp74-country-chip';button.dataset.tp74Node=String(index);
         button.append(flag(code),document.createTextNode(' '+(code||'—')+' '+nodeId));
         button.addEventListener('click',()=>{
           bar.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===button));
           cards.forEach((element,j)=>element.hidden=(j!==index));
         });
         bar.appendChild(button);
       }
     });
     if(!bar.querySelector('[data-tp74-all]')){
       const all=document.createElement('button');all.type='button';all.className='tp74-country-chip active';
       all.dataset.tp74All='1';all.textContent='همه';
       all.addEventListener('click',()=>{
         bar.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===all));
         cards.forEach(x=>x.hidden=false);
       });
       bar.prepend(all);
     }
   }
 }
 function apply(){
   document.querySelectorAll('.ref69-protocol-os').forEach(x=>x.hidden=true);
   refreshV2Ray();
 }
 apply();
 const observer=new MutationObserver(()=>{window.requestAnimationFrame(apply)});
 observer.observe(document.body,{childList:true,subtree:true});
 // Stop once the existing asynchronous V54 metadata has been mounted.
 let checks=0;
 const timer=setInterval(()=>{
   apply();
   if(++checks>=22){clearInterval(timer);observer.disconnect();}
 },400);
})();
</script>
"""

def refine_public_connection_approved_phone_v74(source: str) -> str:
    if _MARKER in source:
        return source
    source=source.replace("</style>",_CSS+"\n</style>",1)
    return source.replace("</body>",_SCRIPT+"\n<!-- "+_MARKER+" -->\n</body>",1)
