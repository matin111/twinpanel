from __future__ import annotations

# Final presentation-only cleanup for public Connection. Never change the app
# download URL list, native VPN credentials, generated subscription payload,
# hostnames, ports, TLS, SNI or client configurations.
_MARKER = "TWINPANEL_PUBLIC_CONNECT_APPS_INLINE_V2RAY_V69"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_APPS_INLINE_V2RAY_V69 */
body.ref69-inline .v42-sheet-backdrop,
body.ref69-inline .protocol-panel .v42-sheet-toolbar,
body.ref69-inline .protocol-panel .v42-sheet-close{display:none!important}
body.ref69-inline.v42-sheet-active{overflow:auto!important}
body.ref69-inline .protocol-panel.v42-sheet-open,
body.ref69-inline .protocol-panel.active{
  position:relative!important;inset:auto!important;left:auto!important;right:auto!important;
  top:auto!important;bottom:auto!important;width:auto!important;max-width:none!important;
  max-height:none!important;overflow:visible!important;overscroll-behavior:auto!important;
  margin-top:12px!important;box-shadow:none!important;
}
body.ref69-inline.ref67.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] > .panel-head,
body.ref69-inline.ref67 .protocol-panel > .panel-head{display:flex!important}
body.ref69-inline.ref67 .protocol-panel .server-tabs,
body.ref69-inline.ref67.v54-v2ray-restore .protocol-panel[data-v54-v2ray="1"] .panel-head .server-tabs,
body.ref69-inline.ref67 .protocol-panel .v57-v2ray-server-tabs{display:none!important}
body.ref69-inline.ref67 .protocol-panel .ref67-tabs{display:flex!important}

/* Native/manual protocols need the original per-node server tabs and widgets:
   Cisco/L2TP = real server/user/password facts; OpenVPN/WireGuard/AWG =
   original downloadable files, not URI-copy placeholders. */
body.ref69-inline.ref67 .protocol-panel[data-ref67-native-protocol] .panel-head .server-tabs{
 display:flex!important;overflow-x:auto!important;flex-wrap:nowrap!important;gap:7px!important;
}
body.ref69-inline.ref67 .protocol-panel[data-ref67-native-protocol] .server-views,
body.ref69-inline.ref67 .protocol-panel[data-ref67-native-protocol] details.v34-mobile-servers .server-views{
 display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
}
body.ref69-inline.ref67 .protocol-panel[data-ref67-native-protocol] .server-view{
 display:block!important;min-width:0!important;
}
body.ref69-inline.ref67 .protocol-panel .v34-client-card,
body.ref69-inline.ref67 .protocol-panel .ref70-app-card{
 display:flex!important;align-items:center!important;justify-content:space-between!important;
 gap:10px!important;min-height:62px!important;margin:12px 17px!important;
 padding:12px 15px!important;border:1px solid #56447d!important;
 border-radius:14px!important;background:linear-gradient(120deg,#241d4d,#141f3c)!important;
 color:#f3f4ff!important;
}
body.ref69-inline.ref67 .protocol-panel .v34-client-card>a,
body.ref69-inline.ref67 .protocol-panel .ref70-app-card>a{
 display:inline-flex!important;align-items:center!important;justify-content:center!important;
 min-height:42px!important;padding:9px 13px!important;border-radius:11px!important;
 background:linear-gradient(115deg,#6b2cef,#8b3bf1)!important;border:1px solid #aa77ff!important;
 font-size:12px!important;font-weight:850!important;color:white!important;text-decoration:none!important;
}
body.ref69-inline.ref67 .protocol-panel .ref70-app-note{
 color:#bcc8ec;font-size:11px;line-height:1.6;
}
@media(max-width:720px){
 body.ref69-inline.ref67 .protocol-panel[data-ref67-native-protocol] .server-views,
 body.ref69-inline.ref67 .protocol-panel[data-ref67-native-protocol] details.v34-mobile-servers .server-views{
  grid-template-columns:1fr!important;
 }
 body.ref69-inline.ref67 .protocol-panel .v34-client-card,
 body.ref69-inline.ref67 .protocol-panel .ref70-app-card{
  margin:9px!important;padding:10px!important;gap:8px!important;flex-wrap:wrap!important;
 }
 body.ref69-inline.ref67 .protocol-panel .v34-client-card>a,
 body.ref69-inline.ref67 .protocol-panel .ref70-app-card>a{
  min-height:40px!important;font-size:11px!important;
 }
}

body.ref69-inline .apps{
  display:block!important;visibility:visible!important;opacity:1!important;
  margin:18px 0 22px!important;border:1px solid #62409b!important;
  border-radius:19px!important;background:linear-gradient(145deg,#152041,#10192e)!important;
  overflow:hidden!important;
}
body.ref69-inline .apps .apps-head{
  display:flex!important;align-items:center!important;justify-content:space-between!important;
  flex-wrap:wrap;gap:10px;padding:17px 19px!important;
  background:linear-gradient(95deg,#221b53,#121d36)!important;border-bottom:1px solid #3e3c70!important;
}
body.ref69-inline .apps .apps-head small{display:block!important;font-size:10px!important;color:#bda3ff!important}
body.ref69-inline .apps .apps-head h2{display:block!important;font-size:18px!important;color:#fff!important}
body.ref69-inline .apps .tools{display:flex!important;align-items:center;gap:8px}
body.ref69-inline .apps .device,
body.ref69-inline .apps .allbtn{min-height:36px!important;font-size:11px!important;border-radius:10px!important}
body.ref69-inline .apps .platforms{display:block!important;padding:15px 18px!important}
body.ref69-inline .apps .platform-group{display:none!important}
body.ref69-inline .apps .platform-group.ref69-picked{display:block!important}
body.ref69-inline .apps.ref69-show-all .platform-group{display:block!important;margin-bottom:17px!important}
body.ref69-inline .apps .platform-title{display:flex!important;align-items:center!important;gap:10px!important;margin:5px 0 12px!important}
body.ref69-inline .apps .platform-title>span{background:#242e53!important;color:#d9d3ff!important}
body.ref69-inline .apps .platform-title b{font-size:13px!important;color:#fff!important}
body.ref69-inline .apps .platform-title small{display:block!important;font-size:10px!important;color:#afbad9!important}
body.ref69-inline .apps .app-grid{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:9px!important}
body.ref69-inline .apps .app-card{
  min-height:75px!important;padding:11px!important;
  background:linear-gradient(135deg,#1d2b4b,#16213b)!important;
  border:1px solid #35476c!important;border-radius:13px!important;
  text-align:right;min-width:0
}
body.ref69-inline .apps .app-card b{display:block;font-size:12px!important;color:#fff!important;overflow-wrap:anywhere}
body.ref69-inline .apps .app-card small{display:block!important;font-size:10px!important;color:#b8c5e3!important;line-height:1.5}
body.ref69-inline .apps .app-card>span{color:#bdb0ff!important;font-size:19px}
body.ref69-inline .ref69-app-platforms{
  display:flex;align-items:center;gap:7px;flex-wrap:wrap;
  margin:0 0 12px;direction:rtl
}
body.ref69-inline .ref69-app-platforms button{
  min-height:39px;padding:8px 12px;background:#1c2846;color:#d8e1fb;
  border:1px solid #394b75;border-radius:11px;font:800 11px Tahoma,Arial,sans-serif
}
body.ref69-inline .ref69-app-platforms button.active{
  background:linear-gradient(110deg,#5727d5,#9e41ec);color:#fff;border-color:#ad77ff
}
body.ref69-inline .ref69-app-jump{
  display:inline-flex;align-items:center;justify-content:center;gap:7px;
  min-height:38px;padding:8px 13px;border:1px solid #8063c9;
  background:#251f4b;color:#f3edff!important;border-radius:11px;
  font-size:11px;font-weight:850;white-space:nowrap
}
@media(max-width:960px){
 body.ref69-inline .apps .app-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
}
@media(max-width:720px){
 body.ref69-inline .protocol-panel.active{max-height:none!important;overflow:visible!important;border-radius:17px!important}
 body.ref69-inline .apps{margin:12px 0 18px!important;border-radius:16px!important}
 body.ref69-inline .apps .apps-head{padding:12px!important}
 body.ref69-inline .apps .apps-head h2{font-size:15px!important}
 body.ref69-inline .apps .platforms{padding:10px!important}
 body.ref69-inline .apps .app-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px!important}
 body.ref69-inline .apps .app-card{min-height:67px!important;padding:9px!important;gap:7px}
 body.ref69-inline .apps .app-card b{font-size:11px!important}
 body.ref69-inline .apps .app-card small{font-size:9px!important}
 body.ref69-inline .apps .platform-title{display:flex!important}
 body.ref69-inline .ref69-app-platforms{gap:5px}
 body.ref69-inline .ref69-app-platforms button{font-size:10px;min-height:36px;padding:7px 9px}
 body.ref69-inline .ref69-app-jump{min-height:37px;padding:7px 10px}
 body.ref69-inline .ref69-app-jump{margin:8px 0 0}
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicConnectAppsInlineV69">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 const body=document.body;
 body.classList.add('ref69-inline');
 // V42 legacy sheet must not suppress the full approved inline Connection UI.
 document.querySelectorAll('.v42-sheet-backdrop').forEach(node=>node.remove());
 body.classList.remove('v42-mobile-sheet','v42-sheet-active');
 document.querySelectorAll('.protocol-panel.v42-sheet-open').forEach(panel=>{
   panel.classList.remove('v42-sheet-open');
   panel.style.removeProperty('max-height');
   panel.style.removeProperty('overflow');
 });
 // Existing server-rendered download URLs (including previously uploaded
 // direct-download links) are never reconstructed, normalized or overwritten.
 const apps=document.getElementById('apps');
 if(!apps)return;
 const platforms=['android','windows','ios','macos','linux'];
 const names={android:'اندروید',windows:'ویندوز',ios:'آیفون / آیپد',macos:'مک',linux:'لینوکس'};
 const icon={android:'◉',windows:'⊞',ios:'●',macos:'⌘',linux:'⌂'};
 const platform=()=>{
   const explicit=String(body.dataset.tpPlatform||'').toLowerCase();
   if(platforms.includes(explicit))return explicit;
   const ua=String(navigator.userAgent||'').toLowerCase();
   const device=String(navigator.platform||'').toLowerCase();
   if(/android/.test(ua))return'android';
   if(/iphone|ipad|ipod/.test(ua)||(/macintel/.test(device)&&navigator.maxTouchPoints>1))return'ios';
   if(/windows|win32|win64/.test(ua+' '+device))return'windows';
   if(/macintosh|mac os|macintel/.test(ua+' '+device))return'macos';
   if(/linux|x11|cros/.test(ua+' '+device))return'linux';
   return'unknown';
 };
 const groups=[...apps.querySelectorAll('.platform-group[data-platform]')];
 const available=platforms.filter(key=>groups.some(group=>group.dataset.platform===key&&group.querySelector('a.app-card[href]')));
 let selected=available.includes(platform())?platform():available[0]||'unknown';
 const nav=document.createElement('nav');nav.className='ref69-app-platforms';
 nav.setAttribute('aria-label','دانلود برنامه بر اساس دستگاه');
 for(const key of available){
   const button=document.createElement('button');
   button.type='button';button.dataset.ref69Device=key;
   button.textContent=(icon[key]||'')+' '+names[key];
   button.addEventListener('click',()=>choose(key));
   nav.appendChild(button);
 }
 const platformHolder=apps.querySelector('.platforms');
 if(platformHolder)platformHolder.insertAdjacentElement('beforebegin',nav);
 const allButton=apps.querySelector('#all');
 function choose(key){
   if(!available.includes(key))return;
   selected=key;apps.classList.remove('ref69-show-all');
   body.classList.remove('tp-show-all-platforms');
   groups.forEach(group=>group.classList.toggle('ref69-picked',group.dataset.platform===key));
   nav.querySelectorAll('button').forEach(button=>button.classList.toggle('active',button.dataset.ref69Device===key));
   const detected=apps.querySelector('#device');
   if(detected)detected.textContent=names[key];
   if(allButton)allButton.textContent='همه سیستم‌ها';
 }
 // Interact only with presentation. Base and V11 scripts still own the real
 // links and share controls; do not alter their URLs.
 if(allButton){
   allButton.addEventListener('click',()=>{
     window.setTimeout(()=>{
       const all=groups.some(group=>group.classList.contains('show-all'));
       apps.classList.toggle('ref69-show-all',all);
       if(!all)choose(selected);
     },0);
   });
 }
 choose(selected);
 const target=apps;
 const protocolSection=document.querySelector('.protocols');
 if(protocolSection){
   const panels=[...document.querySelectorAll('.protocol-panel')];
   const last=panels[panels.length-1];
   if(last&&last.parentNode===target.parentNode){
     last.insertAdjacentElement('afterend',apps);
   }else{
     const advanced=document.querySelector('.advanced');
     if(advanced&&advanced.parentNode===apps.parentNode)advanced.insertAdjacentElement('beforebegin',apps);
   }
 }
 // Keep protocol-specific download actions alongside the selected protocol.
 // Prefer the existing V34 client link for the detected OS; when V13 has no
 // mapping (notably Linux), reuse ONLY links actually present in the existing
 // server-rendered device downloads. Never invent an application URL.
 const patterns={
   cisco:/openconnect|cisco|anyconnect/i,
   openvpn:/openvpn/i,
   wireguard:/wireguard/i,
   amneziawg:/amnezia/i,
   v2ray:/hiddify|v2ray|karing|nekoray/i,
   hysteria2:/karing|hiddify|sing-box/i,
   tuic:/karing|hiddify|sing-box/i,
   anytls:/karing|hiddify|sing-box/i,
   naive:/karing|hiddify|sing-box/i,
   shadowtls:/karing|hiddify|sing-box/i,
   snell:/sing-box|karing/i,
   mieru:/karing|mieru/i,
   trusttunnel:/trusttunnel/i,
   sudoku:/sudoku|anywhere proxy/i,
   socks5:/sing-box|karing|hiddify/i
 };
 function showPerProtocolDownloadLinks(){
   for(const choice of document.querySelectorAll('.protocol-choice[data-protocol]')){
     const panel=document.getElementById(choice.dataset.protocol);
     if(!panel)continue;
     const key=String(choice.dataset.protocolKey||panel.dataset.v34Protocol||'').toLowerCase();
     const head=panel.querySelector('.panel-head');
     if(!head)continue;
     const existing=panel.querySelector('.v34-client-card a[href]');
     if(existing){
       const clientCard=existing.closest('.v34-client-card');
       if(clientCard&&clientCard.previousElementSibling!==head)
         head.insertAdjacentElement('afterend',clientCard);
       // V34 owns the exact matching download URL for the detected OS.
       continue;
     }
     if(panel.querySelector('.ref70-app-card'))continue;
     const card=document.createElement('div');
     card.className='ref70-app-card';
     const label=document.createElement('span');label.textContent='برنامه اتصال '+(choice.querySelector('.protocol-text b')?.textContent||key);
     card.appendChild(label);
     const group=groups.find(row=>row.dataset.platform===selected);
     const appsList=group?[...group.querySelectorAll('a.app-card[href]')]:[];
     // For direct uploads, prefer the user's existing download URL to the
     // default project listing, but only when the app name matches protocol.
     const rx=patterns[key];
     const applicable=rx?appsList.filter(row=>rx.test(row.querySelector('b')?.textContent||'')):[];
     const source=applicable.find(row=>row.classList.contains('uploaded'))||applicable[0]||null;
     const link=document.createElement('a');
     link.href=source?.getAttribute('href')||'#apps';
     if(source){
       link.textContent='↓ دانلود '+(source.querySelector('b')?.textContent||'برنامه');
       if(/^https?:\/\//i.test(link.href)){link.target='_blank';link.rel='noopener noreferrer'}
     }else if(key==='l2tp'){
       link.textContent='راهنمای اتصال دستگاه';
       const note=document.createElement('small');note.className='ref70-app-note';
       note.textContent='L2TP / IPsec معمولاً از تنظیمات VPN داخلی سیستم استفاده می‌کند.';
       card.appendChild(note);
     }else{
       link.textContent='↓ مشاهده برنامه‌های '+(names[selected]||'اتصال');
     }
     if(!source)link.addEventListener('click',event=>{
       event.preventDefault();apps.scrollIntoView({behavior:'smooth',block:'start'});
     });
     card.appendChild(link);
     head.insertAdjacentElement('afterend',card);
   }
 }
 showPerProtocolDownloadLinks();
 let perProtocolAttempts=0;
 const appTimer=setInterval(()=>{
   showPerProtocolDownloadLinks();
   if(++perProtocolAttempts>=9)clearInterval(appTimer);
 },250);
 // A visible affordance above the long list, rather than another fake app link.
 if(!document.querySelector('.ref69-app-jump')){
   const jump=document.createElement('a');
   jump.href='#apps';jump.className='ref69-app-jump';
   jump.textContent='↓ دانلود برنامه‌های اتصال';
   jump.addEventListener('click',event=>{
     event.preventDefault();
     target.scrollIntoView({behavior:'smooth',block:'start'});
   });
   const categories=document.querySelector('.ref67-categories');
   if(categories)categories.insertAdjacentElement('afterend',jump);
 }
})();
</script>
"""

def refine_public_connection_apps_inline_v69(source: str) -> str:
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
