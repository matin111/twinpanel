from __future__ import annotations

"""Final consistency contract for the Connection public page.

Presentation only: preserve all original URL/credential/config/OS-download action
DOM elements and their handlers. Only one protocol and one expanded node detail.
"""
_MARKER = "TWINPANEL_CONNECTION_UNIFIED_SURFACE_DATES_V80"

_CSS = r"""
/* TWINPANEL_CONNECTION_UNIFIED_SURFACE_DATES_V80 */
html body.tp80-connection .traffic .stats{display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;align-items:stretch!important;min-width:0}
html body.tp80-connection .traffic .stat,
html body.tp80-connection .traffic .stat:nth-child(n+4){display:flex!important;flex-direction:column-reverse!important;justify-content:center!important;align-items:center!important;gap:7px!important;min-width:0!important;visibility:visible!important;opacity:1!important}
html body.tp80-connection .traffic .stat small{font-size:11px!important;line-height:1.4!important;color:#bcc9e3!important;white-space:normal!important;text-align:center!important}
html body.tp80-connection .traffic .stat strong{font-size:15px!important;font-variant-numeric:tabular-nums!important;color:#fff!important;white-space:nowrap!important;overflow:visible!important}
body.tp80-connection .tp80-country-bar,
body.tp80-connection .protocol-panel .ref67-tabs,
body.tp80-connection .protocol-panel .tp74-country-bar{
  order:2!important;display:flex!important;align-items:center!important;gap:8px!important;
  flex-wrap:nowrap!important;overflow-x:auto!important;direction:ltr!important;
  scrollbar-width:none!important;margin:0!important;padding:13px 16px 8px!important;
}
body.tp80-connection .tp80-country-bar::-webkit-scrollbar{display:none}
body.tp80-connection .tp80-country-bar button,
body.tp80-connection .protocol-panel .ref67-chip,
body.tp80-connection .protocol-panel .tp74-country-chip{
  min-height:38px!important;min-width:56px!important;padding:6px 11px!important;
  display:inline-flex!important;justify-content:center!important;align-items:center!important;
  border-radius:11px!important;white-space:nowrap!important;flex:0 0 auto!important;
  border:1px solid #40517a!important;background:#1a2540!important;color:#f6f7ff!important;
  font:850 11px Arial,Tahoma,sans-serif!important;gap:7px!important;direction:ltr!important;
}
body.tp80-connection .tp80-country-bar button.active,
body.tp80-connection .protocol-panel .ref67-chip.active,
body.tp80-connection .protocol-panel .tp74-country-chip.active{
  background:linear-gradient(120deg,var(--p),var(--s))!important;
  border-color:#b08dff!important;box-shadow:0 0 13px #8b4aff66!important;color:#fff!important;
}
body.tp80-connection .tp80-country-bar .tp76-flag{width:25px;height:19px;flex-basis:25px}
body.tp80-connection .protocol-panel.active{display:flex!important;flex-direction:column!important}
body.tp80-connection .protocol-panel:not(.active){display:none!important}
body.tp80-connection .protocol-panel .panel-head{
  order:0!important;min-height:90px!important;padding:17px 19px!important;
  background:radial-gradient(ellipse at 90% 130%,#a326ee5c,transparent 50%),linear-gradient(110deg,#1b1947,#121a34)!important;
  border-bottom:1px solid #3c3763!important;
}
body.tp80-connection .protocol-panel .panel-head h3{font-size:22px!important}
body.tp80-connection .tp80-native .panel-head .server-tabs{display:none!important}
body.tp80-connection .protocol-panel .ref67-list,
body.tp80-connection .protocol-panel .tp77-native-list,
body.tp80-connection .protocol-panel .v54-v2ray-groups{
  order:4!important;margin:8px 16px 12px!important;min-width:0!important;
  border:1px solid #334563!important;border-radius:16px!important;
  background:#111b33!important;overflow:hidden!important;
}
body.tp80-connection .protocol-panel .v54-v2ray-groups{display:grid!important;gap:0!important}
body.tp80-connection .protocol-panel .v54-v2ray-server,
body.tp80-connection .protocol-panel .ref67-row,
body.tp80-connection .protocol-panel .tp77-native-row{
  min-height:66px!important;border:0!important;border-bottom:1px solid #344360!important;
  background:#111c33!important;border-radius:0!important;color:#fff!important;
  margin:0!important;box-shadow:none!important;
}
body.tp80-connection .protocol-panel .v54-v2ray-server:last-child,
body.tp80-connection .protocol-panel .ref67-row:last-child,
body.tp80-connection .protocol-panel .tp77-native-row:last-child{border-bottom:0!important}
body.tp80-connection .protocol-panel .ref67-row[hidden],
body.tp80-connection .protocol-panel .tp77-native-row[hidden],
body.tp80-connection .protocol-panel .v54-v2ray-server[hidden]{display:none!important}
body.tp80-connection .protocol-panel .v54-v2ray-server-head{min-height:65px!important;padding:12px!important;display:flex!important;align-items:center!important;gap:12px!important;background:transparent!important}
body.tp80-connection .protocol-panel .v54-v2ray-server.open{background:#18243d!important}
body.tp80-connection .protocol-panel .v54-v2ray-profiles{border-top:1px solid #354567!important}
body.tp80-connection .protocol-panel .v54-v2ray-profile{min-height:53px!important;background:#17233b!important;border-bottom:1px solid #35415b!important}
body.tp80-connection .tp80-native .tp77-native-row{direction:ltr!important;padding:8px 13px!important}
body.tp80-connection .tp80-native .tp77-native-label{min-width:0!important;text-align:left!important;direction:ltr!important;gap:9px!important}
body.tp80-connection .tp80-native .tp77-native-row.active{background:#1c2746!important}
body.tp80-connection .tp80-native .tp77-native-row button{min-height:36px!important;border-radius:9px!important}
html body.tp80-connection .protocol-panel.tp80-native[data-ref67-native-protocol] .server-views,
html body.tp80-connection .protocol-panel.tp80-native[data-ref67-native-protocol] details.v34-mobile-servers .server-views{
  display:none!important;grid-template-columns:none!important;order:8!important;
  padding:0!important;margin:6px 16px 10px!important;gap:0!important;background:transparent!important;
}
html body.tp80-connection .protocol-panel.tp80-native.tp80-detail-open[data-ref67-native-protocol] .server-views,
html body.tp80-connection .protocol-panel.tp80-native.tp80-detail-open[data-ref67-native-protocol] details.v34-mobile-servers .server-views{display:block!important}
html body.tp80-connection .protocol-panel.tp80-native[data-ref67-native-protocol] .server-view{display:none!important;max-width:100%!important;width:100%!important}
html body.tp80-connection .protocol-panel.tp80-native.tp80-detail-open[data-ref67-native-protocol] .server-view.active{display:block!important}
body.tp80-connection .tp80-native details.v34-mobile-servers{display:contents!important}
body.tp80-connection .tp80-native details.v34-mobile-servers>summary,
body.tp80-connection .tp80-native .v34-single-label{display:none!important}
body.tp80-connection .tp80-native .server-view .facts{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(180px,1fr))!important;gap:9px!important}
body.tp80-connection .tp80-native .server-view .fact{background:#1a2843!important;border:1px solid #3c4b6a!important;min-height:64px!important}
body.tp80-connection .tp80-credentials{
  order:3!important;margin:9px 16px 4px!important;min-width:0!important;
  border:1px solid #334566!important;border-radius:11px!important;background:#18243d!important;
}
body.tp80-connection .tp80-credentials>summary{
  display:block!important;list-style:none!important;cursor:pointer!important;
  color:#e9f0ff!important;font-size:12px!important;font-weight:850!important;padding:13px 15px!important;
}
body.tp80-connection .tp80-credentials>summary::after{content:"⌄";float:left}
body.tp80-connection .tp80-credentials[open]>summary::after{content:"⌃"}
body.tp80-connection .tp80-credentials>.v35-manual-credentials{margin:0!important;border:0!important;border-top:1px solid #334566!important;background:transparent!important}
body.tp80-connection .protocol-panel .tp78-action-footer{
  order:30!important;display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;
  direction:ltr!important;gap:10px!important;margin:18px 16px 18px!important;
}
body.tp80-connection .tp78-action-footer>.tp78-footer-action{
  min-height:70px!important;display:flex!important;flex-direction:row!important;
  align-items:center!important;justify-content:center!important;gap:8px!important;
  color:#fff!important;background:#172440!important;border:1px solid #405076!important;
  border-radius:13px!important;box-shadow:none!important;padding:9px!important;min-width:0!important;
}
body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="add"],
body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="download"]{
  background:linear-gradient(120deg,var(--p),var(--s))!important;border-color:#a879fa!important;
  box-shadow:0 0 12px #7938ff4f!important;
}
body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="unavailable"],
body.tp80-connection .tp78-action-footer>.tp78-footer-action:disabled{
  cursor:not-allowed!important;background:#131f38!important;color:#798aa9!important;
  border-color:#2d3b5e!important;box-shadow:none!important;
}
body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="extra"]{
  order:9!important;background:#172440!important;
}
body.tp80-connection .tp78-action-footer>.tp78-footer-action .tp78-icon{flex:0 0 auto}
body.tp80-connection .tp78-action-footer>.tp78-footer-action .tp78-action-text{max-width:100%!important;min-width:0!important;white-space:normal!important;text-align:center!important}
body.tp80-connection .protocol-panel .v34-client-card,
body.tp80-connection .protocol-panel .ref70-app-card,
body.tp80-connection .protocol-panel .v51-multi-card,
body.tp80-connection .protocol-panel .v52-multi-card{order:28!important}
@media(max-width:720px){
 html body.tp80-connection .traffic .stats{grid-template-columns:repeat(6,minmax(0,1fr))!important;row-gap:2px!important;overflow:visible!important}
 html body.tp80-connection .traffic .stats>.stat{grid-column:span 2!important;min-height:57px!important;padding:6px 2px!important}
 html body.tp80-connection .traffic .stats>.stat:nth-child(n+4){grid-column:span 3!important;min-height:54px!important;border-top:1px solid #354363!important}
 html body.tp80-connection .traffic .stat small{font-size:9px!important}
 html body.tp80-connection .traffic .stat strong{font-size:12px!important}
 body.tp80-connection .protocol-panel .panel-head{min-height:75px!important;padding:12px 10px!important}
 body.tp80-connection .protocol-panel .panel-head h3{font-size:17px!important}
 body.tp80-connection .tp80-country-bar,
 body.tp80-connection .protocol-panel .ref67-tabs,
 body.tp80-connection .protocol-panel .tp74-country-bar{padding:9px 8px 6px!important;gap:5px!important}
 body.tp80-connection .tp80-country-bar button,
 body.tp80-connection .protocol-panel .ref67-chip,
 body.tp80-connection .protocol-panel .tp74-country-chip{min-height:32px!important;padding:5px 7px!important;font-size:10px!important}
 body.tp80-connection .protocol-panel .ref67-list,
 body.tp80-connection .protocol-panel .tp77-native-list,
 body.tp80-connection .protocol-panel .v54-v2ray-groups{margin:6px 7px 10px!important;border-radius:13px!important}
 body.tp80-connection .protocol-panel .v54-v2ray-server-head,
 body.tp80-connection .protocol-panel .ref67-row,
 body.tp80-connection .protocol-panel .tp77-native-row{min-height:56px!important}
 body.tp80-connection .protocol-panel.tp80-native[data-ref67-native-protocol] .server-views,
 body.tp80-connection .protocol-panel.tp80-native[data-ref67-native-protocol] details.v34-mobile-servers .server-views{margin:6px 7px 8px!important}
 body.tp80-connection .tp80-credentials{margin:8px 7px 3px!important}
 body.tp80-connection .protocol-panel .tp78-action-footer{grid-template-columns:repeat(3,minmax(0,1fr))!important;margin:12px 7px 12px!important;gap:7px!important}
 body.tp80-connection .tp78-action-footer>.tp78-footer-action{min-height:75px!important;flex-direction:column!important;gap:7px!important;font-size:10px!important}
 body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="add"],
 body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="download"],
 body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="unavailable"]:first-child{
   grid-column:1/-1!important;grid-row:1!important;min-height:54px!important;flex-direction:row!important;
 }
 body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="app"]{grid-row:2!important;grid-column:1!important}
 body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="copy"]{grid-row:2!important;grid-column:2!important}
 body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="link"]{grid-row:2!important;grid-column:3!important}
 body.tp80-connection .tp78-action-footer>.tp78-footer-action[data-kind="extra"]{grid-row:auto!important;grid-column:auto!important}
}

/* Shared minimal views: no stale RTT/presence, no extra prepared-file banners. */
html body.tp80-connection .ref71-rtt,
html body.tp80-connection .ref67-status,
html body.tp80-connection .tp78-ping,
html body.tp80-connection .tp78-reach,
html body.tp80-connection .tp77-native-row .tp78-native-meta,
html body.tp80-connection .tp78-node-tools .tp78-ping,
html body.tp80-connection .v34-single-label,
html body.tp80-connection .action-copy,
html body.tp80-connection .ref67-row-name small,
html body.tp80-connection .tp80-native .tp77-detail-title{display:none!important}
html body.tp80-connection .tp80-files-zip{
  background:linear-gradient(115deg,var(--p),var(--s))!important;
  text-decoration:none!important;border-color:#ad7cfa!important;color:#fff!important;
}
/* Nothing in Connection needs the legacy 'ping' cursor or empty ms placeholders. */
html body.tp80-connection .protocol-panel .ref67-list .ref67-row .tp78-ping{display:none!important}

/* Minimal common surface: no RTT indicators, no duplicate descriptions. */
html body.tp80-connection .ref71-rtt,
html body.tp80-connection .tp78-ping,
html body.tp80-connection .tp78-reach,
html body.tp80-connection .ref67-status,
html body.tp80-connection .ref67-latency,
html body.tp80-connection .ref67-footer,
html body.tp80-connection .v34-single-label,
html body.tp80-connection .v51-single-title,
html body.tp80-connection .v38-server-list-title,
html body.tp80-connection .protocol-panel .panel-head >div:first-child>span:not(.tp78-protocol-emblem),
html body.tp80-connection .v54-v2ray-server-head >span:nth-child(2),
html body.tp80-connection .protocol-panel[data-tp78-action-ready="1"] > .v34-client-card,
html body.tp80-connection .protocol-panel[data-tp78-action-ready="1"] > .ref70-app-card,
html body.tp80-connection .protocol-panel[data-tp78-action-ready="1"] > .v51-multi-card,
html body.tp80-connection .protocol-panel[data-tp78-action-ready="1"] > .v52-multi-card,
html body.tp80-connection .protocol-panel[data-tp78-action-ready="1"] > .v34-subscription-card{
  display:none!important;
}
html body.tp80-connection .protocol-panel .ref67-row{
  display:flex!important;align-items:center!important;justify-content:space-between!important;
  gap:12px!important;min-height:65px!important;padding:11px 14px!important;direction:ltr!important;
}
html body.tp80-connection .protocol-panel .ref67-row-name{flex:1 1 auto!important;min-width:0!important}
html body.tp80-connection .protocol-panel .ref67-row-actions{flex:0 0 auto!important}
html body.tp80-connection .protocol-panel .ref67-row-name small{
  display:none!important;
}
html body.tp80-connection .protocol-panel .ref67-row-name b{font-size:13px!important}
html body.tp80-connection .protocol-panel .ref67-flag img,
html body.tp80-connection .protocol-panel .ref67-chip img,
html body.tp80-connection .protocol-panel .ref67-native-flag img,
html body.tp80-connection .protocol-panel .tp76-flag svg,
html body.tp80-connection .protocol-panel .tp74-flag svg,
html body.tp80-connection .protocol-panel .tp74-flag img,
html body.tp80-connection .protocol-panel .tp77-native-label img{
  width:25px!important;height:19px!important;min-width:25px!important;
  flex:0 0 25px!important;object-fit:cover!important;border-radius:4px!important;
}
html body.tp80-connection .protocol-panel .tp80-file-actions{
  margin-inline-start:auto!important;display:flex!important;flex:0 0 auto!important;
  align-items:center!important;gap:8px!important;direction:ltr!important;
}
html body.tp80-connection .protocol-panel .tp80-file-actions .tp80-file-download{
  border-radius:10px!important;min-height:39px!important;padding:8px 13px!important;
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
  background:linear-gradient(125deg,var(--p),var(--s))!important;
  border:1px solid #9c7cfb!important;color:white!important;cursor:pointer!important;
  font-size:11px!important;font-weight:850!important;width:auto!important;
}
html body.tp80-connection .protocol-panel .tp80-file-copy{
  border-radius:10px!important;min-height:39px!important;padding:8px 13px!important;
  border:1px solid #4b5f82!important;background:#25314d!important;
  color:white!important;font-size:11px!important;font-weight:850!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp77-native-row[data-tp80-file-row='1']{
  display:flex!important;align-items:center!important;justify-content:space-between!important;
  gap:10px!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp77-native-row[data-tp80-file-row='1'] .tp77-native-label{
  flex:1!important;min-width:0!important;
}
html body.tp80-connection .protocol-panel .tp78-action-footer{
 grid-template-columns:repeat(var(--tp80-cols,4),minmax(0,1fr))!important;
}
html body.tp80-connection .tp80-extra-actions{
 order:9!important;grid-column:1/-1!important;border-radius:12px!important;
 border:1px solid #405078!important;background:#14213d!important;
}
html body.tp80-connection .tp80-extra-actions>summary{
 cursor:pointer!important;list-style:none!important;padding:12px!important;text-align:center!important;
 color:#e7edff!important;font-size:11px!important;font-weight:800!important;
}
html body.tp80-connection .tp80-extra-list{
 display:flex!important;gap:8px!important;padding:7px!important;flex-wrap:wrap!important;
}
html body.tp80-connection .tp80-extra-list>.tp78-footer-action{
 flex:1 1 130px!important;min-height:42px!important;display:inline-flex!important;
 justify-content:center!important;align-items:center!important;border:1px solid #435779!important;
 background:#1e2e4f!important;border-radius:9px!important;color:white!important;
 font-size:11px!important;padding:8px!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocol-panel .tp78-action-footer{
   grid-template-columns:repeat(var(--tp80-secondary-cols,3),minmax(0,1fr))!important;
 }
 html body.tp80-connection .protocol-panel .tp78-action-footer[data-has-primary='0']{
   grid-template-columns:repeat(var(--tp80-cols,3),minmax(0,1fr))!important;
 }
 html body.tp80-connection .protocol-panel .tp78-action-footer>.tp78-footer-action[data-kind='add'],
 html body.tp80-connection .protocol-panel .tp78-action-footer>.tp78-footer-action[data-kind='download']{
   grid-column:1/-1!important;grid-row:1!important;
 }
 html body.tp80-connection .protocol-panel .tp78-action-footer>.tp78-footer-action[data-kind='app'],
 html body.tp80-connection .protocol-panel .tp78-action-footer>.tp78-footer-action[data-kind='copy'],
 html body.tp80-connection .protocol-panel .tp78-action-footer>.tp78-footer-action[data-kind='link']{
   grid-column:auto!important;grid-row:auto!important;
 }
 html body.tp80-connection .protocol-panel.tp80-native .tp77-native-row[data-tp80-file-row='1']{
   min-height:58px!important;padding:8px!important;
 }
 html body.tp80-connection .protocol-panel .tp80-file-actions{gap:4px!important}
 html body.tp80-connection .protocol-panel .tp80-file-actions .tp80-file-download,
 html body.tp80-connection .protocol-panel .tp80-file-copy{min-height:33px!important;padding:6px 7px!important;font-size:10px!important}
}

html body.tp80-connection .protocol-panel .tp80-modern-detail[hidden]{display:none!important}
html body.tp80-connection .protocol-panel .tp80-modern-detail{
  padding:11px 14px!important;background:#15233e!important;
  border-bottom:1px solid #354869!important;min-width:0!important;
}
html body.tp80-connection .protocol-panel .tp80-modern-detail>.server-view{
  display:block!important;margin:0!important;padding:0!important;background:transparent!important;
}
html body.tp80-connection .protocol-panel .tp80-modern-detail .facts{
  display:grid!important;grid-template-columns:repeat(auto-fit,minmax(170px,1fr))!important;
  gap:8px!important;
}
html body.tp80-connection .protocol-panel .tp80-modern-detail .fact{
  border:1px solid #405072!important;border-radius:10px!important;
  background:#1b2a47!important;color:#eff5ff!important;padding:10px!important;
}
html body.tp80-connection .protocol-panel .tp80-detail-toggle{
  margin-inline-start:auto!important;flex:0 0 auto!important;
  min-height:36px!important;padding:7px 12px!important;border-radius:10px!important;
  background:#28385a!important;color:white!important;border:1px solid #53648c!important;
  font-size:11px!important;font-weight:850!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocol-panel .tp80-modern-detail{padding:8px!important}
 html body.tp80-connection .protocol-panel .tp80-detail-toggle{min-height:32px!important;padding:6px 8px!important;font-size:10px!important}
}
"""

_SCRIPT = r"""
<script id="twinpanelConnectionUnifiedSurfaceDatesV80">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 document.body.classList.add('tp80-connection');
 const statItems=document.querySelectorAll('.traffic .stats > .stat');
 // starts_at is the actual first-use subscription clock, if it has started.
 if(statItems[3]){const label=statItems[3].querySelector('small');if(label)label.textContent='تاریخ اولین اتصال'}
 if(statItems[4]){const label=statItems[4].querySelector('small');if(label)label.textContent='تاریخ انقضا'}
 const panels=()=>[...document.querySelectorAll('.protocol-panel')];
 // Many legacy mobile scripts change the selected card asynchronously. One
 // final selection state owns both the card and the panel on every device.
 let selectedProtocol='';
 function reconcileProtocolSelection(){
   const choices=[...document.querySelectorAll('.protocol-choice[data-protocol]')];
   if(!choices.length)return;
   const chosen=choices.find(choice=>choice.dataset.protocol===selectedProtocol)
     ||choices.find(choice=>choice.classList.contains('active'))||choices[0];
   const panel=panels().find(item=>item.id===chosen?.dataset.protocol);
   if(!panel)return;
   selectedProtocol=chosen.dataset.protocol;
   choices.forEach(choice=>choice.classList.toggle('active',choice===chosen));
   panels().forEach(item=>item.classList.toggle('active',item===panel));
 }
 document.addEventListener('click',event=>{
   const card=event.target.closest('.protocol-choice[data-protocol]');
   if(!card)return;
   selectedProtocol=card.dataset.protocol;
   queueMicrotask(reconcileProtocolSelection);
 },true);
 const Native=new Set(['openvpn','wireguard','amneziawg','cisco','l2tp']);
 function el(type,classes,txt){
   const node=document.createElement(type);
   if(classes)node.className=classes;
   if(txt!==undefined)node.textContent=txt;
   return node;
 }
 function idLabel(tab){
   const label=tab.querySelector('.tp76-label');
   if(label)return label.cloneNode(true);
   const span=el('span','tp80-country-label');
   span.textContent=String(tab.textContent||'').trim();
   return span;
 }
 function normalizeNative(panel){
   const type=String(panel.dataset.ref67NativeProtocol||panel.dataset.v34Protocol||'').toLowerCase();
   if(!Native.has(type)||!panel.querySelector('.tp77-native-list'))return;
   panel.classList.add('tp80-native');
   const rows=[...panel.querySelectorAll('.tp77-native-row')];
   const tabs=[...panel.querySelectorAll('.server-tab[data-server]')];
   if(!panel.dataset.tp80NativeReady&&tabs.length){
     const bar=el('div','tp80-country-bar');
     bar.setAttribute('aria-label','فیلتر کشورها');
     const all=el('button','active','همه');all.type='button';bar.append(all);
     const choices=[];
     tabs.forEach((tab,index)=>{
       const btn=el('button','');btn.type='button';
       btn.append(idLabel(tab));bar.append(btn);choices.push(btn);
       btn.addEventListener('click',()=>{
         rows.forEach((row,i)=>row.hidden=i!==index);
         choices.forEach((b,i)=>b.classList.toggle('active',i===index));
         all.classList.remove('active');
         panel.classList.remove('tp80-detail-open');
         tab.click();
       });
     });
     all.addEventListener('click',()=>{
       rows.forEach(row=>row.hidden=false);
       choices.forEach(btn=>btn.classList.remove('active'));
       all.classList.add('active');
       panel.classList.remove('tp80-detail-open');
     });
     const head=panel.querySelector(':scope > .panel-head');
     head?.insertAdjacentElement('afterend',bar);
     rows.forEach((row,index)=>{
       const tab=tabs[index];
       const view=tab?panel.querySelector('.server-view[id="'+tab.dataset.server+'"]'):null;
       const show=row.querySelector(':scope > button');
       const isFile=type==='openvpn'||type==='wireguard'||type==='amneziawg';
       // Move the real per-node file action; preserve its data-target, filename
       // and original document click handler. Never duplicate a profile card.
       const download=isFile&&view?view.querySelector('button.download-config[data-target],a.tp-v16-safe-download[href]'):null;
       if(download){
         if(show)show.remove();
         const tools=el('div','tp80-file-actions');
         download.classList.add('tp80-file-download');
         download.textContent='↓ دانلود فایل';
         tools.append(download);
         const target=download.dataset.target;
         const source=target?document.getElementById(target):null;
         if(source&&source.value.trim()){
           const copyFile=el('button','tp80-file-copy','کپی فایل');
           copyFile.type='button';
           copyFile.addEventListener('click',async event=>{
             event.stopPropagation();
             const data=source.value;
             if(!data)return;
             let success=false;
             try{
               if(navigator.clipboard&&isSecureContext){
                 await navigator.clipboard.writeText(data);success=true;
               }
             }catch(_error){}
             if(!success){
               const input=el('textarea','');
               input.value=data;input.style.position='fixed';input.style.left='-9999px';
               document.body.append(input);input.select();
               try{success=document.execCommand('copy')}catch(_error){}
               input.remove();
             }
             if(success){
               copyFile.textContent='کپی شد ✓';
               window.setTimeout(()=>{copyFile.textContent='کپی فایل'},1350);
             }
           });
           tools.append(copyFile);
         }
         row.append(tools);
         row.dataset.tp80FileRow='1';
       }else if(show){
         // Cisco/L2TP and non-file material show only this server's details.
         show.textContent='نمایش اطلاعات';
         show.addEventListener('click',()=>{panel.classList.add('tp80-detail-open')});
       }
     });
     panel.dataset.tp80NativeReady='1';
   }
   // V35 may regenerate shared credentials after page load. Re-home the live
   // copy buttons on every check, keeping them only once and without cloning.
   const shared=panel.querySelector(':scope > .v35-manual-credentials');
   if(shared){
     let disclosure=panel.querySelector(':scope > .tp80-credentials');
     if(!disclosure){
       disclosure=el('details','tp80-credentials');
       disclosure.append(el('summary','','اطلاعات ورود مشترک'));
       shared.insertAdjacentElement('beforebegin',disclosure);
     }
     disclosure.append(shared);
   }
   // Restore semantic active-only details even if V67's obsolete grid CSS exists.
   const views=[...panel.querySelectorAll('.server-view')];
   if(views.length>1){
     let active=views.filter(view=>view.classList.contains('active'));
     if(active.length!==1){
       const selected=tabs.find(tab=>tab.classList.contains('active'));
       const target=views.find(view=>view.id===selected?.dataset.server)||views[0];
       views.forEach(view=>view.classList.toggle('active',view===target));
     }
   }
 }
 function normalizeModern(panel){
   if(panel.dataset.tp80ModernReady==='1'||panel.dataset.v54V2ray==='1')return;
   if(panel.classList.contains('tp80-native')||panel.dataset.ref67NativeProtocol)return;
   const list=panel.querySelector(':scope > .ref67-list');
   const tabs=[...panel.querySelectorAll('.server-tab[data-server]')];
   const rows=[...list?.querySelectorAll(':scope > .ref67-row')||[]];
   if(!list||!tabs.length||!rows.length)return;
   const sections=[];
   rows.forEach((row,index)=>{
     const actions=row.querySelector('.ref67-row-actions');
     if(actions&&actions.querySelector('a[href],button'))return;
     const tab=tabs[index];
     const view=tab?panel.querySelector('.server-view[id="'+tab.dataset.server+'"]'):null;
     if(!view||!view.textContent.trim())return;
     const toggle=el('button','tp80-detail-toggle','نمایش کانفیگ');
     toggle.type='button';
     const holder=el('section','tp80-modern-detail');
     holder.hidden=true;
     // Reuse the ORIGINAL details/buttons. A clone would lose their handlers.
     holder.append(view);
     row.insertAdjacentElement('afterend',holder);
     row.append(toggle);
     sections.push({row,holder,toggle});
     toggle.addEventListener('click',()=>{
       const opening=holder.hidden;
       sections.forEach(section=>{
         section.holder.hidden=true;
         section.toggle.textContent='نمایش کانفیگ';
       });
       holder.hidden=!opening;
       toggle.textContent=opening?'بستن':'نمایش کانفیگ';
     });
   });
   if(sections.length){
     panel.querySelector('.ref67-tabs')?.addEventListener('click',()=>{
       sections.forEach(section=>{section.holder.hidden=true;section.toggle.textContent='نمایش کانفیگ'});
     });
   }
   panel.dataset.tp80ModernReady='1';
 }
 function normalizeV2ray(panel){
   if(panel.dataset.v54V2ray!=='1'&&panel.dataset.v54V2ray!==true)return;
   const cards=[...panel.querySelectorAll('.v54-v2ray-server')];
   cards.forEach(card=>{
     if(card.dataset.tp80CardReady==='1')return;
     card.dataset.tp80CardReady='1';
     card.classList.remove('open');
     const head=card.querySelector('.v54-v2ray-server-head');
     if(!head)return;
     head.setAttribute('aria-expanded','false');
     head.addEventListener('click',()=>{
       if(!card.classList.contains('open'))return;
       cards.forEach(other=>{
         if(other!==card){
           other.classList.remove('open');
           other.querySelector('.v54-v2ray-server-head')?.setAttribute('aria-expanded','false');
         }
       });
     });
   });
 }
 function alignFooter(panel){
   const footer=panel.querySelector(':scope > .tp78-action-footer');
   if(!footer||footer.dataset.tp80Ready==='1')return;
   const children=[...footer.querySelectorAll(':scope > .tp78-footer-action')];
   const find=kind=>children.find(node=>node.dataset.kind===kind);
   const key=String(panel.dataset.ref67NativeProtocol||panel.dataset.v34Protocol||'').toLowerCase();
   const fileProtocol=new Set(['openvpn','wireguard','amneziawg']).has(key);
   let primary=find('add')||find('download');
   const previousPrimary=primary;
   if(fileProtocol){
     // A single verified ZIP of the original files. Do not present a vague
     // "download all" button that may download only one selected server.
     const token=location.pathname.match(/^\/v1\/connect\/([^/]+)/)?.[1];
     if(token){
       const zip=el('a','tp78-footer-action tp80-files-zip','دانلود همه فایل‌ها ZIP');
       zip.dataset.kind='download';
       zip.setAttribute('download',key+'-configs.zip');
       zip.href=location.origin+'/v1/connect/'+token+'/multi/'+encodeURIComponent(key);
       if(primary)primary.remove();
       primary=zip;
     }
   }
   const ordered=[primary,find('link'),fileProtocol?null:find('copy'),find('app')].filter(Boolean);
   // Do not render dead placeholders. Every button must perform a real action.
   const extra=children.filter(node=>!ordered.includes(node)&&node!==primary&&node!==previousPrimary&&(!fileProtocol||node.dataset.kind!=='copy'));
   footer.replaceChildren(...ordered);
   if(extra.length){
     const details=el('details','tp80-extra-actions');
     details.append(el('summary','','سایر فرمت‌های کانفیگ'));
     const holder=el('div','tp80-extra-list');
     extra.forEach(node=>holder.append(node));details.append(holder);
     footer.append(details);
   }
   // Layout fills the width for 1,2,3,4 available operations, on any device.
   footer.dataset.hasPrimary=primary?'1':'0';
   footer.style.setProperty('--tp80-cols',String(Math.min(4,Math.max(1,ordered.length))));
   footer.style.setProperty('--tp80-secondary-cols',String(Math.min(3,Math.max(1,ordered.length-(primary?1:0)))));
   if(!ordered.length&&!extra.length)footer.remove();
   else footer.dataset.tp80Ready='1';
 }
 function check(){
   reconcileProtocolSelection();
   panels().forEach(panel=>{
     normalizeNative(panel);
     normalizeV2ray(panel);
     normalizeModern(panel);
     alignFooter(panel);
   });
 }
 check();
 let n=0;
 const timer=setInterval(()=>{check();if(++n>=35)clearInterval(timer)},300);
})();
</script>
"""

def refine_public_connection_unified_surface_dates_v80(source: str) -> str:
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + "\n<!-- " + _MARKER + " -->\n</body>", 1)
