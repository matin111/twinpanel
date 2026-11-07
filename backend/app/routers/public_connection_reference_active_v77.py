from __future__ import annotations

# Visual-only final authority for the approved Connection mockup.
# Does not rewrite, fetch, serialize, or modify any VPN configuration.
_MARKER = "TWINPANEL_PUBLIC_CONNECT_REFERENCE_ACTIVE_V77"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_REFERENCE_ACTIVE_V77 */
html.tp77-reference{--bg:#080e20;--surface:#111b31;--surface2:#14213a;--surface3:#192844;--line:#344263;--text:#f6f8ff;--muted:#b7c4de;--ok:#28f197;color-scheme:dark}
html body.tp77-reference{color:#f6f8ff!important;background:radial-gradient(ellipse at 70% 0%,#34145f55,transparent 38%),#090e20!important;min-height:100vh}
body.tp77-reference .top{background:#0a1020f5!important;border-bottom:1px solid #242e4b!important}
body.tp77-reference .topin{height:78px!important;direction:ltr!important;display:flex!important;align-items:center!important}
body.tp77-reference .brand{direction:ltr!important;display:flex!important;align-items:center!important;width:100%!important;gap:13px!important}
body.tp77-reference .brand .mark{order:0!important;flex-shrink:0}
body.tp77-reference .brand>b{order:1!important;font-size:24px!important;color:#fff!important}
body.tp77-reference .brand .theme{order:2!important;margin-left:auto!important;color:#fff!important}
body.tp77-reference .page{width:min(1280px,95vw)!important;max-width:1280px!important;padding:23px 0 45px!important}
body.tp77-reference .traffic{background:linear-gradient(100deg,#141b35,#151e39 65%,#2b154a)!important;border:1px solid #614099!important;box-shadow:0 12px 30px #090c2060!important;color:#fff!important}
body.tp77-reference .traffic .stats{grid-template-columns:repeat(3,minmax(0,1fr))!important}
body.tp77-reference .traffic .stat:nth-child(n+4){display:flex!important}
body.tp77-reference .traffic .stat strong{color:#fff!important}
body.tp77-reference .traffic .stat small{color:#b8c4dc!important}
body.tp77-reference .ref67-user{background:#111a35!important;border-color:#344265!important}
body.tp77-reference .ref67-categories{direction:ltr!important;justify-content:flex-end!important;border-bottom:0!important;gap:9px!important}
body.tp77-reference .ref67-filter{background:#142039!important;color:#f1f5ff!important;border:1px solid #354367!important}
body.tp77-reference .ref67-filter.active{color:#fff!important;border-color:var(--p)!important;background:linear-gradient(120deg,var(--p),var(--s))!important}
body.tp77-reference .protocols{direction:ltr!important;display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:10px!important;margin:12px 0 24px!important}
body.tp77-reference .protocol-choice{direction:ltr!important;display:flex!important;flex-direction:row!important;justify-content:flex-start!important;align-items:center!important;gap:12px!important;min-height:74px!important;height:auto!important;padding:12px 14px!important;background:linear-gradient(130deg,#16213c,#10192e)!important;color:#fff!important;border:1px solid #364365!important;border-radius:16px!important;text-align:left!important}
body.tp77-reference .protocol-choice .protocol-icon{order:0!important;flex:0 0 48px!important;width:48px!important;height:48px!important;border-radius:50%!important}
body.tp77-reference .protocol-choice .protocol-text{order:1!important;min-width:0!important;text-align:left!important}
body.tp77-reference .protocol-choice .protocol-text b{font-size:14px!important;line-height:1.3!important;color:#fff!important}
body.tp77-reference .protocol-choice .protocol-text small{display:block!important;font-size:11px!important;color:#b6c5e2!important;margin:4px 0 0!important}
body.tp77-reference .protocol-choice em{display:none!important}
body.tp77-reference .protocol-choice.active{border-color:#a97dff!important;box-shadow:0 0 0 1px #9c5bff,0 0 17px #8739f777!important}
body.tp77-reference .protocol-choice.ref67-hidden,
body.tp77-reference .protocol-choice[hidden]{display:none!important}
/* V75 previously made *all* protocol panels visible, overriding HubV5 active. */
html body.tp77-reference .protocol-panel:not(.active){display:none!important}
html body.tp77-reference .protocol-panel.active{display:flex!important;flex-direction:column!important;align-items:stretch!important;background:linear-gradient(155deg,#111a33,#0b1127)!important;border:1px solid #6749ab!important;border-radius:22px!important;overflow:hidden!important;margin:12px 0!important;gap:0!important}
body.tp77-reference .protocol-panel .panel-head{order:0!important;direction:ltr!important;min-height:94px!important;padding:18px 21px!important;display:flex!important;align-items:center!important;justify-content:space-between!important;background:radial-gradient(ellipse at 90% 130%,#9130e866,transparent 45%),linear-gradient(100deg,#1a1647,#121b36)!important;border-bottom:1px solid #39396e!important}
body.tp77-reference .protocol-panel .panel-head h3{font-size:23px!important;color:#fff!important;line-height:1.3!important}
body.tp77-reference .protocol-panel .panel-head>div:first-child{direction:ltr!important}
body.tp77-reference .protocol-panel .panel-head>div:first-child>span{color:#34ef92!important;font-size:12px!important}
body.tp77-reference .protocol-panel .ref67-tabs,
body.tp77-reference .protocol-panel .tp74-country-bar{order:1!important;direction:ltr!important;padding:14px 16px 8px!important;gap:8px!important}
body.tp77-reference .ref67-chip,
body.tp77-reference .tp74-country-chip,
body.tp77-reference .server-tab{background:#17233e!important;border:1px solid #425075!important;color:#fff!important;border-radius:11px!important;min-height:39px!important}
body.tp77-reference .ref67-chip.active,
body.tp77-reference .tp74-country-chip.active,
body.tp77-reference .server-tab.active{background:linear-gradient(125deg,var(--p),var(--s))!important;border-color:#b994ff!important;color:#fff!important}
body.tp77-reference .protocol-panel .ref67-list{order:3!important;background:#111c34!important;border:1px solid #344464!important;margin:8px 16px 12px!important}
body.tp77-reference .ref67-row{direction:ltr!important;display:grid!important;grid-template-columns:145px minmax(0,1fr) auto!important;align-items:center!important;gap:12px!important;min-height:70px!important;border-bottom:1px solid #354263!important;background:#111b33!important}
body.tp77-reference .ref67-row-name{grid-column:2!important;grid-row:1!important;direction:ltr!important;justify-content:flex-start!important}
body.tp77-reference .ref67-status{grid-column:1!important;grid-row:1!important;text-align:left!important}
body.tp77-reference .ref67-row-actions{grid-column:3!important;grid-row:1!important;justify-content:flex-end!important}
body.tp77-reference .ref67-row-name b{color:#fff!important;font-size:13px!important}
body.tp77-reference .ref67-row-name small{color:#b8c6df!important}
body.tp77-reference .ref67-row-actions>*{background:#1b2947!important;color:#fff!important;border:1px solid #435477!important}
body.tp77-reference .ref67-row-actions .ref67-primary{background:linear-gradient(115deg,var(--p),var(--s))!important;color:#fff!important;border:1px solid #aa85ff!important}
body.tp77-reference .protocol-panel .v54-v2ray-groups{order:3!important}
body.tp77-reference .protocol-panel[data-v54-v2ray="1"] .panel-head .server-tabs{display:none!important}
/* File-based protocols: real per-node rows plus ONE active native detail view. */
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .panel-head .server-tabs{display:none!important}
body.tp77-reference .tp77-native-list{order:2!important;margin:8px 16px!important;background:#111d36;border:1px solid #3b4969;border-radius:14px;overflow:hidden}
body.tp77-reference .tp77-native-row{direction:ltr;display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:59px;padding:9px 13px;border-bottom:1px solid #35415c;color:#fff}
body.tp77-reference .tp77-native-row:last-child{border-bottom:0}
body.tp77-reference .tp77-native-row.active{background:#1c2449}
body.tp77-reference .tp77-native-row .tp77-native-label{display:flex;align-items:center;gap:9px;font-weight:850;font-size:13px}
body.tp77-reference .tp77-native-row button{border:1px solid #505e86;border-radius:10px;background:#233152;color:#fff;padding:9px 12px;font-size:11px;font-weight:800;min-height:36px}
body.tp77-reference .protocol-panel[data-ref67-native-protocol] > .server-views{order:3!important;display:block!important;margin:0 16px 10px!important;padding:0!important}
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .server-view{display:none!important;width:100%!important;background:#141d34!important}
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .server-view.active{display:block!important}
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .server-view .tp77-detail-title{color:#fff;font-size:12px;font-weight:850;margin:0 0 8px;direction:ltr}
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .facts{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(190px,1fr))!important;gap:8px!important}
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .fact{background:#1a2843!important;color:#f5f7ff!important;border:1px solid #3c4b6a!important;min-height:65px!important;border-radius:11px!important}
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .fact small{color:#afbed8!important}
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .fact b,
body.tp77-reference .protocol-panel[data-ref67-native-protocol] .fact strong{color:#fff!important}
body.tp77-reference .protocol-panel .v51-multi-card,
body.tp77-reference .protocol-panel .v52-multi-card{order:20!important;margin:10px 16px 0!important;background:#142039!important;border:1px solid #344466!important}
body.tp77-reference .protocol-panel .v51-multi-actions>*,
body.tp77-reference .protocol-panel .v34-actions>*,
body.tp77-reference .protocol-panel .ref67-footer>*{color:#fff!important;background:#1b2946!important;border:1px solid #3e5076!important;border-radius:11px!important;font-weight:850!important}
body.tp77-reference .protocol-panel .v51-multi-actions>*:first-child,
body.tp77-reference .protocol-panel .v34-actions>*:first-child{background:linear-gradient(115deg,var(--p),var(--s))!important;border-color:#b08aff!important}
body.tp77-reference .protocol-panel .ref70-app-card,
body.tp77-reference .protocol-panel .v34-client-card{order:22!important;background:#17213c!important;border:1px solid #3e4e72!important;color:#fff!important}
body.tp77-reference .protocol-panel .ref69-protocol-os{display:none!important}
body.tp77-reference .protocol-panel .ref69-download-cta[hidden]{display:none!important}
body.tp77-reference .protocol-panel .ref69-download-empty:not([hidden]){color:#b4bed2!important}
/* Hide leftover global-app surfaces; keep their source links for the normal client builder. */
body.tp77-reference .apps,
body.tp77-reference .ref69-global-apps{display:none!important}
@media(max-width:720px){
 body.tp77-reference .topin{height:62px!important;width:calc(100% - 22px)!important}
 body.tp77-reference .brand>b{font-size:20px!important}
 body.tp77-reference .page{width:calc(100% - 18px)!important;max-width:480px!important;padding:9px 0 26px!important}
 body.tp77-reference .traffic{margin:0 0 9px!important;padding:9px!important;border-radius:16px!important}
 body.tp77-reference .traffic .stats{grid-template-columns:repeat(3,minmax(0,1fr))!important}
 body.tp77-reference .ref67-categories{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:5px!important;justify-content:stretch!important;padding:4px 0 9px!important}
 body.tp77-reference .ref67-filter{width:100%!important;min-width:0!important;padding:4px 1px!important;font-size:10px!important}
 body.tp77-reference .protocols{grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:6px!important;margin:8px 0 13px!important}
 body.tp77-reference .protocol-choice{min-height:78px!important;height:78px!important;flex-direction:column!important;justify-content:center!important;align-items:center!important;padding:5px 2px!important;gap:5px!important;border-radius:12px!important}
 body.tp77-reference .protocol-choice .protocol-icon{width:38px!important;height:38px!important;flex-basis:38px!important}
 body.tp77-reference .protocol-choice .protocol-text{width:100%!important;text-align:center!important}
 body.tp77-reference .protocol-choice .protocol-text b{font-size:10px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
 body.tp77-reference .protocol-choice .protocol-text small{display:none!important}
 html body.tp77-reference .protocol-panel.active{border-radius:16px!important}
 body.tp77-reference .protocol-panel .panel-head{min-height:70px!important;padding:12px!important}
 body.tp77-reference .protocol-panel .panel-head h3{font-size:17px!important}
 body.tp77-reference .protocol-panel .ref67-tabs,
 body.tp77-reference .protocol-panel .tp74-country-bar{padding:9px 8px 5px!important;gap:5px!important}
 body.tp77-reference .ref67-chip,body.tp77-reference .tp74-country-chip{font-size:10px!important;min-height:34px!important;padding:6px!important}
 body.tp77-reference .protocol-panel .ref67-list{margin:6px 8px 10px!important}
 body.tp77-reference .ref67-row{grid-template-columns:minmax(0,1fr) auto!important;min-height:55px!important;gap:6px!important;padding:7px!important}
 body.tp77-reference .ref67-row-name{grid-column:1!important;grid-row:1!important}
 body.tp77-reference .ref67-status{display:none!important}
 body.tp77-reference .ref67-row-actions{grid-column:2!important;grid-row:1!important}
 body.tp77-reference .ref67-row-actions>*{width:34px!important;height:34px!important;min-height:34px!important;padding:5px!important}
 body.tp77-reference .tp77-native-list{margin:6px 8px!important}
 body.tp77-reference .tp77-native-row{min-height:55px;padding:7px 9px}
 body.tp77-reference .protocol-panel[data-ref67-native-protocol] > .server-views{margin:0 8px 8px!important}
 body.tp77-reference .protocol-panel .v51-multi-card,body.tp77-reference .protocol-panel .v52-multi-card{margin:8px!important}
 body.tp77-reference .protocol-panel .v51-multi-actions{grid-template-columns:repeat(2,minmax(0,1fr))!important}
 body.tp77-reference .protocol-panel .ref70-app-card,body.tp77-reference .protocol-panel .v34-client-card{margin:8px!important}
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicConnectReferenceActiveV77">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 const root=document.documentElement;root.classList.add('tp77-reference');
 document.body.classList.add('tp77-reference');
 // Match the approved dark reference on first visit to the redesign.
 // Thereafter the user's theme switch keeps working and remains persistent.
 try{
   if(!localStorage.getItem('tp77_reference_theme_initialized')){
     if(root.dataset.theme!=='dark')document.getElementById('themeToggle')?.click();
     localStorage.setItem('tp77_reference_theme_initialized','1');
   }
 }catch(_error){}
 const choices=()=>[...document.querySelectorAll('.protocol-choice[data-protocol]')];
 const panels=()=>[...document.querySelectorAll('.protocol-panel')];
 let selection='';
 function selectProtocol(id){
   const target=panels().find(p=>p.id===id);
   if(!target)return;
   selection=id;
   choices().forEach(c=>c.classList.toggle('active',c.dataset.protocol===id));
   panels().forEach(p=>p.classList.toggle('active',p===target));
 }
 function syncProtocol(){
   const candidates=choices();
   const active=candidates.find(c=>c.classList.contains('active'));
   const saved=selection&&candidates.find(c=>c.dataset.protocol===selection);
   const v2ray=candidates.find(c=>c.dataset.protocolKey==='v2ray'&&!c.hidden&&!c.classList.contains('ref67-hidden'));
   const target=saved||active||v2ray||candidates[0];
   if(target)selectProtocol(target.dataset.protocol);
 }
 function identity(tab){
   const source=tab.querySelector(':scope > span')||tab;
   const label=source.querySelector('.tp76-label');
   if(label)return label.cloneNode(true);
   const span=document.createElement('span');span.textContent=String(source.textContent||'').trim();
   return span;
 }
 function nativeList(panel){
   if(!panel.dataset.ref67NativeProtocol||panel.querySelector(':scope > .tp77-native-list'))return;
   const tabs=[...panel.querySelectorAll('.server-tab[data-server]')];
   if(!tabs.length)return;
   const list=document.createElement('div');list.className='tp77-native-list';
   const rows=[];
   tabs.forEach(tab=>{
     const view=panel.querySelector('.server-view[id="'+tab.dataset.server+'"]');
     if(!view)return;
     const row=document.createElement('div');row.className='tp77-native-row';
     const label=document.createElement('div');label.className='tp77-native-label';
     label.appendChild(identity(tab));
     const latency=tab.querySelector('.ref71-rtt');
     if(latency)label.appendChild(latency.cloneNode(true));
     const show=document.createElement('button');show.type='button';
     show.textContent='نمایش کانفیگ';
     show.addEventListener('click',()=>{tab.click();rows.forEach(x=>x.row.classList.toggle('active',x.tab===tab));});
     row.append(label,show);rows.push({tab,row});list.appendChild(row);
     const title=document.createElement('div');title.className='tp77-detail-title';
     title.appendChild(identity(tab));
     view.prepend(title);
   });
   if(!rows.length)return;
   const first=rows.find(x=>x.tab.classList.contains('active'))||rows[0];
   rows.forEach(x=>x.row.classList.toggle('active',x===first));
   const head=panel.querySelector(':scope > .panel-head');
   if(head)head.insertAdjacentElement('afterend',list);
 }
 document.addEventListener('click',event=>{
   const protocol=event.target.closest('.protocol-choice[data-protocol]');
   if(protocol){selectProtocol(protocol.dataset.protocol);return}
 },false);
 syncProtocol();
 let n=0;
 const timer=setInterval(()=>{
   syncProtocol();
   panels().forEach(nativeList);
   if(++n>=24)clearInterval(timer);
 },350);
})();
</script>
"""

def refine_public_connection_reference_active_v77(source: str) -> str:
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + "\n<!-- " + _MARKER + " -->\n</body>", 1)
