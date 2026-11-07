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
/* One navigation bar per native protocol. Legacy tabs stay in DOM for
   their existing per-node handlers, but are not exposed as a second bar. */
html body.tp80-connection .protocol-panel.tp80-native .panel-head .server-tabs,
html body.tp80-connection .protocol-panel.tp80-native .panel-head .tp74-country-bar,
html body.tp80-connection .protocol-panel.tp80-native > .ref67-tabs,
html body.tp80-connection .protocol-panel.tp80-native > .tp74-country-bar{
  display:none!important;visibility:hidden!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp77-native-row[data-tp80-country-hidden="1"]{
  display:none!important;visibility:hidden!important;
}
body.tp80-connection .tp80-country-bar img{
  width:24px!important;height:18px!important;object-fit:cover!important;border-radius:4px!important;
}
body.tp80-connection .tp80-country-flag{font-size:20px!important;line-height:1!important}

/* Manual-style proxy facts use the same node/credential presentation. */
html body.tp80-connection .tp80-modern-detail[hidden]{display:none!important}
html body.tp80-connection .tp80-modern-detail:not([hidden]){
  display:block!important;position:relative!important;
  background:#16233c!important;border-bottom:1px solid #384968!important;
  margin:0!important;padding:10px!important;
}
html body.tp80-connection .tp80-socks5-detail .server-view[hidden]{display:none!important}
html body.tp80-connection .tp80-socks5-detail .facts{
 display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;
 gap:9px!important;align-items:stretch!important;width:100%!important;
}
html body.tp80-connection .tp80-socks5-detail .fact{
 min-width:0!important;max-width:100%!important;width:100%!important;
 text-align:center!important;word-break:break-word!important;padding:11px!important;
}
html body.tp80-connection .tp80-socks5-detail .fact strong{overflow-wrap:anywhere!important}
@media(max-width:720px){
 html body.tp80-connection .tp80-socks5-detail .facts{grid-template-columns:1fr!important}
}

/* Shared native nodes: one compact 62px row for OpenVPN, WireGuard,
   Cisco, L2TP and AmneziaWG. Only the selected node expands directly below. */
html body.tp80-connection .protocol-panel.tp80-native .tp77-native-list{
  display:block!important;align-self:stretch!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp77-native-row{
  display:flex!important;flex-direction:row!important;align-items:center!important;
  justify-content:space-between!important;gap:10px!important;
  min-height:62px!important;max-height:82px!important;height:auto!important;
  padding:8px 12px!important;box-sizing:border-box!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp77-native-label{
  display:flex!important;flex-direction:row!important;align-items:center!important;
  min-width:0!important;flex:1!important;
}
html body.tp80-connection .tp80-country-image{width:25px!important;height:18px!important;
 object-fit:cover!important;flex-shrink:0!important;border-radius:3px!important}
html body.tp80-connection .tp80-inline-native-detail[hidden]{display:none!important}
html body.tp80-connection .protocol-panel.tp80-native .tp80-inline-native-detail:not([hidden]){
  display:block!important;position:relative!important;margin:0!important;padding:12px!important;
  background:#16233c!important;border-bottom:1px solid #384968!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp80-inline-native-detail:not([hidden]) .server-view{
  display:block!important;width:100%!important;max-width:100%!important;
  margin:0!important;padding:0!important;background:transparent!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp80-inline-native-detail .facts{
  display:grid!important;grid-template-columns:repeat(auto-fit,minmax(170px,1fr))!important;
  gap:8px!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp80-inline-native-detail .fact{
  min-height:65px!important;min-width:0!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocol-panel.tp80-native .tp77-native-row{
   min-height:58px!important;max-height:80px!important;padding:8px!important;
 }
 html body.tp80-connection .protocol-panel.tp80-native .tp80-inline-native-detail .facts{
   grid-template-columns:repeat(2,minmax(0,1fr))!important
 }
}

html body.tp80-connection .protocol-panel.tp80-native > .tp80-credentials{
  display:block!important;visibility:visible!important;padding:10px!important;
}
html body.tp80-connection .protocol-panel.tp80-native .tp80-credentials > .v35-manual-credentials{
  display:block!important;visibility:visible!important;
  border:none!important;margin:0!important;padding:4px!important;background:transparent!important;
}
body.tp80-connection .tp80-credentials .v35-manual-head{margin-bottom:10px!important}

/* V69/V34 sometimes regenerate the same client as a separate banner.
   Retain the source link in the footer, suppress repeated UI only. */
html body.tp80-connection .protocol-panel:has(> .tp78-action-footer [data-kind="app"])
  > .v34-client-card,
html body.tp80-connection .protocol-panel:has(> .tp78-action-footer [data-kind="app"])
  > .ref70-app-card,
html body.tp80-connection .protocol-panel:has(> .tp78-action-footer [data-kind="app"])
  > .ref69-download-cta{
    display:none!important;
}
html body.tp80-connection .protocol-panel .tp78-action-footer > [data-kind="app"]{
   display:flex!important;align-items:center!important;justify-content:center!important;
}

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

/* Legacy V36/V38 mobile accordion must never hide the selected active panel. */
@media(max-width:720px){
 html body.tp80-connection.v36-mobile-compact.v38-reference .protocol-panel.active,
 html body.tp80-connection.v36-mobile-compact .protocol-panel.active{
   display:flex!important;flex-direction:column!important;visibility:visible!important;
 }
 html body.tp80-connection.v36-mobile-compact.v38-reference .protocol-panel:not(.active),
 html body.tp80-connection.v36-mobile-compact .protocol-panel:not(.active){display:none!important}
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

/* TWINPANEL_CONNECTION_CLIENT_DOWNLOAD_FIX */
html body.tp80-connection .protocol-panel.tp80-native .tp77-native-row{height:62px!important;min-height:62px!important;max-height:62px!important;padding:7px 12px!important;overflow:hidden!important}
html body.tp80-connection .protocol-panel.tp80-native .tp80-file-actions{display:flex!important;flex-direction:row!important;align-items:center!important;gap:7px!important;flex:0 0 auto!important}
html body.tp80-connection .protocol-panel.tp80-native .tp80-file-actions button,html body.tp80-connection .protocol-panel.tp80-native .tp80-file-actions a{height:36px!important;min-height:36px!important;padding:6px 10px!important}
html body.tp80-connection .protocol-panel > .v34-client-card,html body.tp80-connection .protocol-panel > .ref70-app-card,html body.tp80-connection .protocol-panel > .v13-client-only{display:none!important}
html body.tp80-connection .protocol-panel .tp78-action-footer{grid-template-columns:repeat(var(--tp80-cols,3),minmax(0,1fr))!important}
@media(max-width:720px){html body.tp80-connection .protocol-panel.tp80-native .tp77-native-row{height:58px!important;min-height:58px!important;max-height:58px!important;padding:5px 8px!important}html body.tp80-connection .protocol-panel .tp78-action-footer{grid-template-columns:repeat(2,minmax(0,1fr))!important}}

/* TWINPANEL_CONNECTION_CLIENT_FOOTER_MOBILE_V81 */
html body.tp80-connection .protocol-panel > .v34-client-card,
html body.tp80-connection .protocol-panel > .ref70-app-card,
html body.tp80-connection .protocol-panel > .v13-client-only,
html body.tp80-connection .protocol-panel > .ref69-download-cta{display:none!important}
html body.tp80-connection .protocol-panel .tp78-action-footer{
 display:grid!important;grid-template-columns:repeat(var(--tp80-cols,3),minmax(0,1fr))!important;
 direction:ltr!important;gap:9px!important;
}
html body.tp80-connection .protocol-panel .tp78-action-footer > [data-kind="app"]{
 display:flex!important;align-items:center!important;justify-content:center!important;
 flex:1!important;min-width:0!important;min-height:64px!important;
 color:#fff!important;text-align:center!important;text-decoration:none!important;
 background:#192846!important;border:1px solid #435678!important;border-radius:12px!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocols{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:6px!important}
 html body.tp80-connection .protocols .protocol-choice{
  display:flex!important;flex-direction:column!important;justify-content:center!important;
  align-items:center!important;gap:7px!important;min-width:0!important;
  min-height:92px!important;padding:9px 3px!important;text-align:center!important;
 }
 html body.tp80-connection .protocols .protocol-choice .protocol-icon{
  order:0!important;width:43px!important;height:43px!important;min-height:43px!important;
  flex:0 0 43px!important;margin:0 auto!important;
 }
 html body.tp80-connection .protocols .protocol-choice .protocol-text{
  order:1!important;display:block!important;max-width:100%!important;width:100%!important;
  text-align:center!important;min-width:0!important;
 }
 html body.tp80-connection .protocols .protocol-choice .protocol-text b{
  display:block!important;font-size:10px!important;line-height:1.25!important;
  white-space:normal!important;overflow-wrap:anywhere!important;text-align:center!important;
 }
 html body.tp80-connection .protocols .protocol-choice .protocol-text small{display:none!important}
 html body.tp80-connection .protocol-panel .tp78-action-footer{
  display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px!important;
 }
 html body.tp80-connection .protocol-panel .tp78-action-footer > .tp78-footer-action{
  min-height:47px!important;max-width:100%!important;font-size:11px!important;
 }
}

/* TWINPANEL_CONNECTION_VISUAL_PARITY_V82: uniform cards for every protocol */
html body.tp80-connection .protocol-panel.active{
 display:flex!important;flex-direction:column!important;align-items:stretch!important;
 gap:0!important;overflow:hidden!important;
}
html body.tp80-connection .protocol-panel.active > .panel-head{
 min-height:94px!important;display:flex!important;align-items:center!important;
 box-sizing:border-box!important;margin:0!important;
}
html body.tp80-connection .protocol-panel.active > .tp80-country-bar,
html body.tp80-connection .protocol-panel.active > .ref67-tabs{
 order:2!important;margin:0!important;box-sizing:border-box!important;
}
html body.tp80-connection .protocol-panel.active > .ref67-list,
html body.tp80-connection .protocol-panel.active > .tp77-native-list,
html body.tp80-connection .protocol-panel.active > .v54-v2ray-groups{
 order:4!important;margin:8px 16px 12px!important;border:1px solid #344563!important;
 border-radius:15px!important;overflow:hidden!important;align-self:stretch!important;
 background:#111c33!important;box-sizing:border-box!important;
}
html body.tp80-connection .protocol-panel.active .ref67-row,
html body.tp80-connection .protocol-panel.active .tp77-native-row,
html body.tp80-connection .protocol-panel.active .v54-v2ray-server-head{
 box-sizing:border-box!important;height:62px!important;min-height:62px!important;
 max-height:62px!important;padding:8px 12px!important;margin:0!important;
 display:flex!important;align-items:center!important;justify-content:space-between!important;
 border-radius:0!important;border:0!important;border-bottom:1px solid #344360!important;
 background:#111c33!important;gap:10px!important;
}
html body.tp80-connection .protocol-panel.active .ref67-row-actions,
html body.tp80-connection .protocol-panel.active .tp80-file-actions{
 display:flex!important;align-items:center!important;gap:7px!important;flex-shrink:0!important;
}
html body.tp80-connection .protocol-panel.active .ref67-row-actions button,
html body.tp80-connection .protocol-panel.active .ref67-row-actions a,
html body.tp80-connection .protocol-panel.active .tp80-file-actions button,
html body.tp80-connection .protocol-panel.active .tp80-file-actions a,
html body.tp80-connection .protocol-panel.active .tp80-detail-toggle{
 height:36px!important;min-height:36px!important;max-height:36px!important;
 box-sizing:border-box!important;border-radius:9px!important;padding:6px 11px!important;
 font-size:11px!important;white-space:nowrap!important;
}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer{
 order:30!important;display:grid!important;
 grid-template-columns:repeat(var(--tp80-cols,3),minmax(0,1fr))!important;
 margin:12px 16px 16px!important;padding:0!important;gap:9px!important;
 align-items:stretch!important;direction:ltr!important;
}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp78-footer-action{
 margin:0!important;width:100%!important;min-width:0!important;box-sizing:border-box!important;
 min-height:64px!important;height:auto!important;border-radius:12px!important;
 font-size:12px!important;text-align:center!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocols .protocol-choice{
  display:flex!important;flex-direction:column!important;justify-content:center!important;
  align-items:center!important;gap:7px!important;text-align:center!important;
 }
 html body.tp80-connection .protocols .protocol-choice .protocol-icon{
  order:0!important;margin:0 auto!important;flex:0 0 43px!important;
 }
 html body.tp80-connection .protocols .protocol-choice .protocol-text{
  order:1!important;display:block!important;flex:0 0 auto!important;
  width:100%!important;text-align:center!important;
 }
 html body.tp80-connection .protocols .protocol-choice .protocol-text b{
  display:block!important;text-align:center!important;font-size:10px!important;
  line-height:1.3!important;overflow-wrap:anywhere!important;
 }
 html body.tp80-connection .protocol-panel.active > .panel-head{
  min-height:78px!important;padding:12px!important;
 }
 html body.tp80-connection .protocol-panel.active > .ref67-list,
 html body.tp80-connection .protocol-panel.active > .tp77-native-list,
 html body.tp80-connection .protocol-panel.active > .v54-v2ray-groups{
  margin:7px 8px 10px!important;border-radius:12px!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row,
 html body.tp80-connection .protocol-panel.active .tp77-native-row,
 html body.tp80-connection .protocol-panel.active .v54-v2ray-server-head{
  height:58px!important;min-height:58px!important;max-height:58px!important;
  padding:6px 8px!important;gap:6px!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer{
  grid-template-columns:repeat(2,minmax(0,1fr))!important;
  margin:10px 8px 12px!important;gap:7px!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp78-footer-action{
  min-height:48px!important;font-size:10px!important;padding:7px!important;
 }
}

/* TWINPANEL_CLIENT_FOOTER_ONLY_V83 */
html body.tp80-connection .protocol-panel.active .v34-client-card,
html body.tp80-connection .protocol-panel.active .ref70-app-card,
html body.tp80-connection .protocol-panel.active .v13-client-only,
html body.tp80-connection .protocol-panel.active .ref69-download-cta{
 display:none!important;visibility:hidden!important;height:0!important;
 min-height:0!important;margin:0!important;padding:0!important;
}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer{
 order:99!important;display:grid!important;
 grid-template-columns:repeat(var(--tp80-cols,3),minmax(0,1fr))!important;
 gap:9px!important;margin:14px 16px 16px!important;
}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer > [data-kind="app"]{
 display:flex!important;position:static!important;grid-column:auto!important;
 width:100%!important;min-height:62px!important;min-width:0!important;
 margin:0!important;padding:9px!important;box-sizing:border-box!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer{
 grid-template-columns:repeat(2,minmax(0,1fr))!important;
 gap:7px!important;margin:10px 8px 12px!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > [data-kind="app"]{
 min-height:48px!important;
 }
}

/* TWINPANEL_CONNECTION_MOBILE_ACTIONS_DIALOG_V84 */
@media(max-width:720px){
 html body.tp80-connection .protocol-panel.active .ref67-row,
 html body.tp80-connection .protocol-panel.active .tp77-native-row,
 html body.tp80-connection .protocol-panel.active .v54-v2ray-server-head{
  box-sizing:border-box!important;width:100%!important;min-width:0!important;
  display:flex!important;flex-direction:row!important;justify-content:space-between!important;
  align-items:center!important;gap:5px!important;padding:6px 8px!important;overflow:hidden!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-name,
 html body.tp80-connection .protocol-panel.active .tp77-native-label,
 html body.tp80-connection .protocol-panel.active .v54-v2ray-server-name{
  flex:1 1 auto!important;min-width:0!important;max-width:100%!important;overflow:hidden!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-actions,
 html body.tp80-connection .protocol-panel.active .tp80-file-actions{
  display:flex!important;flex:0 1 auto!important;flex-direction:row!important;
  width:auto!important;max-width:56%!important;min-width:0!important;
  gap:5px!important;margin-inline-start:auto!important;padding:0!important;
  align-items:center!important;justify-content:flex-end!important;overflow:hidden!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-actions > *,
 html body.tp80-connection .protocol-panel.active .tp80-file-actions > *,
 html body.tp80-connection .protocol-panel.active .tp80-detail-toggle{
  box-sizing:border-box!important;position:static!important;flex:0 1 auto!important;
  width:auto!important;min-width:48px!important;max-width:100%!important;
  height:36px!important;min-height:36px!important;max-height:36px!important;
  margin:0!important;padding:5px 8px!important;font-size:10px!important;
  white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer{
  order:99!important;display:grid!important;width:auto!important;
  grid-template-columns:repeat(2,minmax(0,1fr))!important;grid-auto-flow:row!important;
  align-items:stretch!important;gap:7px!important;margin:10px 8px 12px!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > *,
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp78-footer-action,
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > [data-kind="app"]{
  grid-column:auto!important;grid-row:auto!important;order:initial!important;
  box-sizing:border-box!important;min-width:0!important;max-width:100%!important;width:100%!important;
  min-height:48px!important;height:auto!important;padding:8px 5px!important;margin:0!important;
  text-align:center!important;font-size:10px!important;white-space:normal!important;overflow-wrap:anywhere!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp80-extra-actions{
  grid-column:1/-1!important;
 }
}
/* Mounted on body to avoid clipped/hidden protocol containers. */
body .tp84-dialog[hidden]{display:none!important}
body .tp84-dialog{position:fixed!important;inset:0!important;z-index:2147483000!important;
 display:flex!important;align-items:center!important;justify-content:center!important;
 padding:14px!important;box-sizing:border-box!important;background:#030716d9!important}
body .tp84-dialog-card{display:flex!important;flex-direction:column!important;gap:0!important;
 width:min(480px,100%)!important;max-height:min(85dvh,760px)!important;min-height:0!important;
 border:1px solid #7453b7!important;border-radius:18px!important;overflow:hidden!important;
 background:#101b33!important;color:#f8faff!important;box-shadow:0 25px 80px #000a!important}
body .tp84-dialog-head{display:flex!important;align-items:center!important;justify-content:space-between!important;
 padding:12px 15px!important;border-bottom:1px solid #384765!important;font-weight:850!important}
body .tp84-dialog-close{border:1px solid #536080!important;border-radius:9px!important;
 background:#253453!important;color:white!important;padding:7px 12px!important}
body .tp84-dialog-body{overflow:auto!important;overscroll-behavior:contain!important;padding:12px!important;
 direction:rtl!important;min-height:0!important}
body .tp84-dialog-body > .tp80-inline-native-detail,
body .tp84-dialog-body > .tp80-modern-detail,
body .tp84-dialog-body > .v54-v2ray-profiles{
 display:block!important;position:static!important;width:100%!important;max-width:100%!important;
 margin:0!important;padding:0!important;background:transparent!important;
}
body .tp84-dialog-body .server-view{display:block!important;max-width:100%!important;width:100%!important}
body .tp84-dialog-body .facts{display:grid!important;grid-template-columns:1fr!important;gap:9px!important}
body .tp84-dialog-body .fact{min-width:0!important;max-width:100%!important;overflow-wrap:anywhere!important}

/* TWINPANEL_MOBILE_ACTIONS_STABLE_V85 - no cropped buttons at narrow widths */
@media(max-width:720px){
 html body.tp80-connection .protocol-panel.active .ref67-list,
 html body.tp80-connection .protocol-panel.active .tp77-native-list,
 html body.tp80-connection .protocol-panel.active .v54-v2ray-groups{
   width:auto!important;min-width:0!important;max-width:100%!important;
   box-sizing:border-box!important;overflow:hidden!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row,
 html body.tp80-connection .protocol-panel.active .tp77-native-row,
 html body.tp80-connection .protocol-panel.active .v54-v2ray-server-head{
   display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;
   grid-template-rows:1fr!important;column-gap:8px!important;
   width:100%!important;min-width:0!important;max-width:100%!important;
   box-sizing:border-box!important;min-height:60px!important;height:auto!important;
   max-height:none!important;padding:7px 9px!important;overflow:visible!important;
   align-items:center!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-name,
 html body.tp80-connection .protocol-panel.active .tp77-native-label{
   grid-column:1!important;min-width:0!important;max-width:100%!important;
   width:auto!important;overflow:hidden!important;white-space:nowrap!important;
   text-overflow:ellipsis!important;margin:0!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-actions,
 html body.tp80-connection .protocol-panel.active .tp80-file-actions{
   grid-column:2!important;display:flex!important;flex-flow:row nowrap!important;
   align-items:center!important;justify-content:flex-end!important;
   position:static!important;inset:auto!important;transform:none!important;
   min-width:0!important;width:auto!important;max-width:190px!important;
   gap:6px!important;overflow:visible!important;margin:0!important;
   padding:0!important;float:none!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-actions > a,
 html body.tp80-connection .protocol-panel.active .ref67-row-actions > button,
 html body.tp80-connection .protocol-panel.active .tp80-file-actions > a,
 html body.tp80-connection .protocol-panel.active .tp80-file-actions > button{
   display:inline-flex!important;position:static!important;inset:auto!important;
   transform:none!important;float:none!important;vertical-align:middle!important;
   align-items:center!important;justify-content:center!important;
   box-sizing:border-box!important;flex:0 0 auto!important;
   width:auto!important;min-width:51px!important;max-width:100px!important;
   padding:7px 9px!important;margin:0!important;gap:4px!important;
   min-height:36px!important;height:auto!important;max-height:42px!important;
   border-radius:9px!important;font-size:11px!important;line-height:1.2!important;
   white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;
   text-decoration:none!important;z-index:auto!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-actions > button{
   color:#fff!important;background:#253553!important;border:1px solid #536485!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-actions > a.ref67-primary{
   color:#fff!important;background:linear-gradient(120deg,var(--p),var(--s))!important;
   border:1px solid #ac8cff!important;
 }
 html body.tp80-connection .protocol-panel.active .tp80-detail-toggle{
   grid-column:2!important;justify-self:end!important;min-width:70px!important;
   position:static!important;transform:none!important;inset:auto!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer{
   order:99!important;display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
   grid-auto-flow:row!important;align-items:stretch!important;
   width:auto!important;min-width:0!important;margin:10px 8px 12px!important;
   padding:0!important;gap:7px!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp78-footer-action,
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > [data-kind="app"]{
   grid-column:auto!important;grid-row:auto!important;
   min-width:0!important;width:100%!important;max-width:100%!important;
   min-height:48px!important;height:auto!important;max-height:none!important;
   margin:0!important;padding:8px 6px!important;
   box-sizing:border-box!important;order:initial!important;
   text-align:center!important;overflow-wrap:anywhere!important;
   white-space:normal!important;font-size:10px!important;
 }
}
@media(max-width:365px){
 html body.tp80-connection .protocol-panel.active .ref67-row,
 html body.tp80-connection .protocol-panel.active .tp77-native-row{
   column-gap:4px!important;padding:6px!important;
 }
 html body.tp80-connection .protocol-panel.active .ref67-row-actions,
 html body.tp80-connection .protocol-panel.active .tp80-file-actions{gap:4px!important;max-width:155px!important}
 html body.tp80-connection .protocol-panel.active .ref67-row-actions > *,
 html body.tp80-connection .protocol-panel.active .tp80-file-actions > *{
   min-width:44px!important;max-width:83px!important;padding:6px!important;font-size:10px!important;
 }
}

/* TWINPANEL_CONNECTION_BRAND_PALETTE_V86
   Brand colors --p / --s come from the same admin-configured branding
   as the rest of TwinPanel. No hard-coded purple/blue accents. */
html body.tp80-connection{
 --tp-brand-bg:var(--bg,#080a0f);
 --tp-brand-card:var(--surface,#0f1219);
 --tp-brand-raised:var(--surface2,#141821);
 --tp-brand-hover:var(--surface3,#1a1f2a);
 --tp-brand-stroke:var(--line,#252b37);
 --tp-brand-text:var(--text,#f5f6f8);
 --tp-brand-muted:var(--muted,#a6adc0);
 background:var(--tp-brand-bg)!important;
 color:var(--tp-brand-text)!important;
}
html body.tp80-connection .top,
html body.tp80-connection .topin{
 background:var(--tp-brand-card)!important;
 color:var(--tp-brand-text)!important;
 border-color:var(--tp-brand-stroke)!important;
}
html body.tp80-connection .page,
html body.tp80-connection .protocol-panel.active{
 color:var(--tp-brand-text)!important;
}
html body.tp80-connection .traffic,
html body.tp80-connection .ref67-user,
html body.tp80-connection .protocol-choice,
html body.tp80-connection .protocol-panel.active,
html body.tp80-connection .protocol-panel.active .ref67-list,
html body.tp80-connection .protocol-panel.active .tp77-native-list,
html body.tp80-connection .protocol-panel.active .v54-v2ray-groups{
 background:var(--tp-brand-card)!important;
 border-color:var(--tp-brand-stroke)!important;
 color:var(--tp-brand-text)!important;
 box-shadow:none!important;
}
html body.tp80-connection .protocol-choice.active,
html body.tp80-connection .protocol-panel.active{
 border-color:color-mix(in srgb,var(--p) 65%,var(--tp-brand-stroke))!important;
}
html body.tp80-connection .protocol-choice.active{
 box-shadow:0 0 0 1px color-mix(in srgb,var(--p) 50%,transparent)!important;
}
html body.tp80-connection .protocol-panel.active > .panel-head,
html body.tp80-connection .traffic .traffic-head,
html body.tp80-connection .apps .apps-head{
 background:linear-gradient(110deg,
   color-mix(in srgb,var(--p) 12%,var(--tp-brand-card)),
   color-mix(in srgb,var(--s) 15%,var(--tp-brand-card)))!important;
 color:var(--tp-brand-text)!important;
 border-color:var(--tp-brand-stroke)!important;
}
html body.tp80-connection .protocol-panel.active .ref67-row,
html body.tp80-connection .protocol-panel.active .tp77-native-row,
html body.tp80-connection .protocol-panel.active .v54-v2ray-server-head,
html body.tp80-connection .protocol-panel.active .v54-v2ray-profile,
html body.tp80-connection .protocol-panel.active .v54-v2ray-profiles,
html body.tp80-connection .protocol-panel.active .tp80-inline-native-detail:not([hidden]),
html body.tp80-connection .protocol-panel.active .tp80-modern-detail:not([hidden]),
html body.tp80-connection .protocol-panel.active .tp80-credentials,
html body.tp80-connection .protocol-panel.active .fact,
html body.tp80-connection .protocol-panel.active .ref67-row-actions button{
 background:var(--tp-brand-raised)!important;
 color:var(--tp-brand-text)!important;
 border-color:var(--tp-brand-stroke)!important;
}
html body.tp80-connection .protocol-panel.active .ref67-row:hover,
html body.tp80-connection .protocol-panel.active .tp77-native-row:hover{
 background:var(--tp-brand-hover)!important;
}
html body.tp80-connection .protocol-panel.active .tp80-country-bar button,
html body.tp80-connection .protocol-panel.active .ref67-chip,
html body.tp80-connection .protocol-panel.active .tp74-country-chip,
html body.tp80-connection .protocol-panel.active .tp80-file-copy,
html body.tp80-connection .protocol-panel.active .tp80-detail-toggle,
html body.tp80-connection .protocol-panel.active .tp78-footer-action,
html body.tp80-connection .protocol-panel.active .tp78-action-footer > [data-kind="app"],
html body.tp80-connection .protocol-panel.active .ref67-row-actions > button{
 background:var(--tp-brand-raised)!important;
 color:var(--tp-brand-text)!important;
 border-color:var(--tp-brand-stroke)!important;
 box-shadow:none!important;
}
html body.tp80-connection .protocol-panel.active .tp80-country-bar button.active,
html body.tp80-connection .protocol-panel.active .ref67-chip.active,
html body.tp80-connection .protocol-panel.active .tp74-country-chip.active,
html body.tp80-connection .protocol-panel.active .tp80-file-download,
html body.tp80-connection .protocol-panel.active .ref67-row-actions a.ref67-primary,
html body.tp80-connection .protocol-panel.active .tp78-action-footer > [data-kind="add"],
html body.tp80-connection .protocol-panel.active .tp78-action-footer > [data-kind="download"]{
 background:linear-gradient(120deg,var(--p),var(--s))!important;
 color:#fff!important;
 border-color:color-mix(in srgb,var(--p) 70%,white)!important;
 box-shadow:none!important;
}
html body.tp80-connection .protocol-panel.active .tp78-action-footer{
 background:transparent!important;
 border-color:var(--tp-brand-stroke)!important;
}
html body.tp80-connection .protocol-panel.active .ref67-row-name small,
html body.tp80-connection .protocol-panel.active .fact small,
html body.tp80-connection .protocol-choice small{
 color:var(--tp-brand-muted)!important;
}
body .tp84-dialog{
 background:color-mix(in srgb,var(--tp-brand-bg,#080a0f) 83%,transparent)!important;
}
body .tp84-dialog-card{
 background:var(--tp-brand-card,var(--surface))!important;
 color:var(--tp-brand-text,var(--text))!important;
 border-color:color-mix(in srgb,var(--p) 60%,var(--tp-brand-stroke))!important;
}
body .tp84-dialog-head,
body .tp84-dialog-body{
 background:var(--tp-brand-card,var(--surface))!important;
 color:var(--tp-brand-text,var(--text))!important;
 border-color:var(--tp-brand-stroke,var(--line))!important;
}
body .tp84-dialog-close{
 background:var(--tp-brand-raised,var(--surface2))!important;
 border-color:var(--tp-brand-stroke,var(--line))!important;
 color:var(--tp-brand-text,var(--text))!important;
}
/* Keep native app buttons visually in the same footer, without changing links. */
html body.tp80-connection .protocol-panel.active .tp78-action-footer > [data-kind="app"]{
 background:var(--tp-brand-raised)!important;
 border-color:var(--tp-brand-stroke)!important;
 color:var(--tp-brand-text)!important;
}

/* TWINPANEL_CONNECTION_WINDOWS_FOUR_ACTIONS_V87 */
@media(min-width:721px){
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer{
  display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;
  grid-auto-flow:row!important;align-items:stretch!important;
  gap:10px!important;width:auto!important;margin:14px 16px 16px!important;
  direction:ltr!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp78-footer-action,
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > [data-kind="app"]{
  display:flex!important;grid-column:auto!important;grid-row:auto!important;
  width:100%!important;max-width:100%!important;min-width:0!important;
  min-height:64px!important;margin:0!important;padding:10px 7px!important;
  box-sizing:border-box!important;position:static!important;float:none!important;
  justify-content:center!important;align-items:center!important;flex:initial!important;
  white-space:normal!important;overflow-wrap:anywhere!important;
  text-align:center!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp80-extra-actions{
  grid-column:1/-1!important;
 }
}

/* TWINPANEL_CONNECTION_ANDROID_FOUR_ACTION_LAYOUT_V88 */
@media(max-width:720px){
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer{
   display:grid!important;
   grid-template-columns:repeat(3,minmax(0,1fr))!important;
   grid-auto-flow:row!important;
   gap:7px!important;direction:ltr!important;align-items:stretch!important;
   padding:0!important;margin:10px 8px 12px!important;min-width:0!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp78-footer-action{
   grid-column:auto!important;grid-row:auto!important;
   min-width:0!important;width:100%!important;max-width:100%!important;
   min-height:48px!important;height:auto!important;max-height:none!important;
   padding:8px 4px!important;margin:0!important;box-sizing:border-box!important;
   display:flex!important;align-items:center!important;justify-content:center!important;
   flex-direction:column!important;gap:4px!important;
   text-align:center!important;font-size:10px!important;line-height:1.35!important;
   white-space:normal!important;overflow-wrap:anywhere!important;
   order:initial!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="four"] > .tp78-footer-action:first-child{
   grid-column:1/-1!important;grid-row:1!important;
   flex-direction:row!important;gap:8px!important;min-height:51px!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="four"] > .tp78-footer-action:nth-child(2),
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="four"] > .tp78-footer-action:nth-child(3),
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="four"] > .tp78-footer-action:nth-child(4){
   grid-row:2!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="four"] > .tp78-footer-action:nth-child(2){grid-column:1!important}
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="four"] > .tp78-footer-action:nth-child(3){grid-column:2!important}
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="four"] > .tp78-footer-action:nth-child(4){grid-column:3!important}
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="three"]{
   grid-template-columns:repeat(3,minmax(0,1fr))!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp88-layout="two"]{
   grid-template-columns:repeat(2,minmax(0,1fr))!important;
 }
 html body.tp80-connection .protocol-panel.active > .tp78-action-footer > .tp80-extra-actions{
   grid-column:1/-1!important;grid-row:auto!important;
 }
}

/* TWINPANEL_V2RAY_VISIBLE_PROFILES_AND_COPY_V89 */
html body.tp80-connection .protocol-panel.active .v54-v2ray-groups{
 display:grid!important;gap:0!important;overflow:visible!important;
}
html body.tp80-connection .protocol-panel.active .v54-v2ray-server{
 height:auto!important;max-height:none!important;min-height:62px!important;
 overflow:visible!important;margin:0!important;
 border:0!important;border-bottom:1px solid var(--tp-brand-stroke,var(--line))!important;
 border-radius:0!important;background:var(--tp-brand-raised,var(--surface2))!important;
}
html body.tp80-connection .protocol-panel.active .v54-v2ray-server-head{
 height:auto!important;max-height:none!important;min-height:62px!important;
 box-sizing:border-box!important;display:flex!important;align-items:center!important;
 justify-content:space-between!important;flex-wrap:nowrap!important;gap:9px!important;
 padding:8px 12px!important;overflow:visible!important;
}
html body.tp80-connection .protocol-panel.active .v54-v2ray-server.open > .v54-v2ray-profiles{
 display:grid!important;grid-template-columns:minmax(0,1fr)!important;
 height:auto!important;min-height:0!important;max-height:none!important;
 overflow:visible!important;position:static!important;
}
html body.tp80-connection .protocol-panel.active .v54-v2ray-server:not(.open) > .v54-v2ray-profiles{
 display:none!important;
}
html body.tp80-connection .protocol-panel.active .v54-v2ray-profile{
 height:auto!important;max-height:none!important;min-height:52px!important;
 display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;
 align-items:center!important;gap:10px!important;padding:9px 12px!important;
}
html body.tp80-connection .protocol-panel.active .v54-v2ray-profile-actions{
 display:flex!important;gap:7px!important;justify-content:flex-end!important;
}
html body.tp80-connection .protocol-panel.active .tp89-v2ray-copy{
 display:inline-flex!important;align-items:center!important;justify-content:center!important;
 flex:0 0 auto!important;min-width:95px!important;height:37px!important;
 padding:6px 12px!important;border-radius:10px!important;
 border:1px solid var(--tp-brand-stroke,var(--line))!important;
 background:var(--tp-brand-card,var(--surface))!important;
 color:var(--tp-brand-text,var(--text))!important;
 font:800 11px Tahoma,Arial,sans-serif!important;cursor:pointer!important;
}
html body.tp80-connection .protocol-panel.active .tp89-v2ray-copy:focus-visible{
 outline:2px solid var(--p)!important;outline-offset:2px!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocol-panel.active .v54-v2ray-server-head{
  display:flex!important;flex-direction:row!important;min-height:58px!important;
  padding:7px 9px!important;
 }
 html body.tp80-connection .protocol-panel.active .tp89-v2ray-copy{
  min-width:75px!important;padding:5px 8px!important;font-size:10px!important;
 }
 html body.tp80-connection .protocol-panel.active .v54-v2ray-profile{
  grid-template-columns:1fr!important;
 }
}

/* TWINPANEL_VISIBLE_CLIENT_DOWNLOAD_V91 */
html body.tp80-connection .protocol-panel.active > .tp78-action-footer > a.tp91-client-download{
 display:flex!important;visibility:visible!important;opacity:1!important;
 position:relative!important;min-height:58px!important;height:auto!important;
 color:var(--tp-brand-text,var(--text))!important;
 background:var(--tp-brand-raised,var(--surface2))!important;
 border:1px solid var(--tp-brand-stroke,var(--line))!important;
 padding:12px!important;align-items:center!important;justify-content:center!important;
 text-decoration:none!important;font-weight:800!important;
}

/* TWINPANEL_CONNECTION_ALL_PROTOCOL_PARITY_V92 */
html body.tp80-connection .protocol-panel.active .tp92-v2-country-bar{
 display:flex!important;flex-wrap:wrap!important;gap:7px!important;
 padding:10px 15px!important;margin:0!important;align-items:center!important;
}
html body.tp80-connection .protocol-panel.active .tp92-v2-country-bar button{
 display:inline-flex!important;align-items:center!important;gap:5px!important;
 padding:7px 10px!important;min-height:36px!important;border-radius:10px!important;
 border:1px solid var(--tp-brand-stroke,var(--line))!important;
 background:var(--tp-brand-raised,var(--surface2))!important;
 color:var(--tp-brand-text,var(--text))!important;font-weight:800!important;
}
html body.tp80-connection .protocol-panel.active .tp92-v2-country-bar button.active{
 background:linear-gradient(110deg,var(--p),var(--s))!important;color:#fff!important;
}
html body.tp80-connection .protocol-panel.active .tp92-v2-country-bar img,
html body.tp80-connection .protocol-panel.active .tp92-node-flag{
 display:inline-block!important;width:24px!important;height:16px!important;
 object-fit:cover!important;vertical-align:middle!important;margin-inline-end:5px!important;
}
html body.tp80-connection .protocol-panel.active .v54-v2ray-server-head .tp92-country-label{
 display:inline-flex!important;gap:5px!important;align-items:center!important;
 min-width:0!important;white-space:nowrap!important;
}
html body.tp80-connection .protocol-panel.active .v54-v2ray-server[hidden]{display:none!important}
html body.tp80-connection .protocol-panel.active .tp80-native .tp77-native-row .tp92-node-flag{
 width:24px!important;height:16px!important;
}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp92-only-app="1"]{
 grid-template-columns:1fr!important;
}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer[data-tp92-only-app="1"] > a[data-kind="app"]{
 grid-column:1/-1!important;
}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer > a.tp92-v2rayn{
 grid-column:1/-1!important;display:flex!important;justify-content:center!important;
 min-height:45px!important;align-items:center!important;
 border:1px solid var(--tp-brand-stroke,var(--line))!important;
 border-radius:10px!important;background:var(--tp-brand-raised,var(--surface2))!important;
 color:var(--tp-brand-text,var(--text))!important;font-weight:800!important;
 text-decoration:none!important;
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
   const visible=choices.filter(choice=>!choice.hidden&&!choice.classList.contains('ref67-hidden'));
   const eligible=visible.length?visible:choices;
   const chosen=eligible.find(choice=>choice.dataset.protocol===selectedProtocol)
     ||eligible.find(choice=>choice.classList.contains('active'))||eligible[0];
   const panel=panels().find(item=>item.id===chosen?.dataset.protocol);
   if(!panel)return;
   selectedProtocol=chosen.dataset.protocol;
   choices.forEach(choice=>{
     const active=choice===chosen;
     choice.classList.toggle('active',active);
     choice.setAttribute('aria-expanded',active?'true':'false');
   });
   const compact=document.body.classList.contains('v36-mobile-compact');
   panels().forEach(item=>{
     const active=item===panel;
     item.classList.toggle('active',active);
     // Legacy V36/V38 require v36-open AND active on phones. Keep both
     // synchronized; otherwise the selected mobile panel stays display:none.
     if(compact)item.classList.toggle('v36-open',active);
     else item.classList.remove('v36-open');
     item.setAttribute('aria-hidden',active?'false':'true');
   });
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
 // Local vector flags avoid Windows rendering a country code instead of an
 // emoji and still work when flagcdn is inaccessible. Unknown ISO codes retain
 // the existing CDN artwork as a graceful extension.
 function knownFlag(code){
   const bands=(colors,vertical=false)=>colors.map((color,i)=>{
     const d=vertical?{x:i*12,y:0,w:12,h:24}:{x:0,y:i*8,w:36,h:8};
     return '<rect x="'+d.x+'" y="'+d.y+'" width="'+d.w+'" height="'+d.h+'" fill="'+color+'"/>';
   }).join('');
   const star='<polygon points="28,7 29.1,10.2 32.5,10.2 29.8,12.2 30.8,15.7 28,13.7 25.2,15.7 26.2,12.2 23.5,10.2 26.9,10.2" fill="#fff"/>';
   const paths={
     DE:bands(['#171717','#dd1e2d','#ffce00']),
     NL:bands(['#ae1c28','#fff','#21468b']),
     FR:bands(['#0055a4','#fff','#ef4135'],true),
     TR:'<rect width="36" height="24" fill="#e30a17"/><circle cx="15" cy="12" r="7" fill="#fff"/><circle cx="17.5" cy="12" r="5.6" fill="#e30a17"/>'+star,
     US:'<rect width="36" height="24" fill="#fff"/>'+Array.from({length:7},(_,i)=>'<rect y="'+i*3.6923+'" width="36" height="1.85" fill="#b22234"/>').join('')+'<rect width="16" height="13" fill="#3c3b6e"/>'+Array.from({length:15},(_,i)=>'<circle cx="'+(2+i%5*3)+'" cy="'+(2+Math.floor(i/5)*4)+'" r=".7" fill="#fff"/>').join(''),
     GB:'<rect width="36" height="24" fill="#012169"/><path d="M0 0L36 24M36 0L0 24" stroke="#fff" stroke-width="6"/><path d="M0 0L36 24M36 0L0 24" stroke="#c8102e" stroke-width="2.5"/><path d="M18 0V24M0 12H36" stroke="#fff" stroke-width="9"/><path d="M18 0V24M0 12H36" stroke="#c8102e" stroke-width="4.5"/>'
   };
   if(!paths[code])return '';
   const svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 24" width="36" height="24">'+paths[code]+'</svg>';
   return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
 }
 function countryImage(country){
   const img=el('img','tp80-country-image');
   img.alt=country;img.loading='eager';
   img.src=knownFlag(country)||'https://flagcdn.com/w40/'+country.toLowerCase()+'.png';
   img.onerror=()=>{img.replaceWith(el('span','tp80-country-fallback',country))};
   return img;
 }
 function normalizeNative(panel){
   const type=String(panel.dataset.ref67NativeProtocol||panel.dataset.v34Protocol||'').toLowerCase();
   if(!Native.has(type)||!panel.querySelector('.tp77-native-list'))return;
   panel.classList.add('tp80-native');
   const rows=[...panel.querySelectorAll('.tp77-native-row')];
   const tabs=[...panel.querySelectorAll('.server-tab[data-server]')];
   if(!panel.dataset.tp80NativeReady&&tabs.length){
     // The original server-tabs remain only as internal JS controls. The
     // user sees exactly one country selector, deduplicated by ISO country.
     const original=panel.querySelector(':scope > .panel-head .server-tabs');
     if(original){original.hidden=true;original.style.setProperty('display','none','important');}
     const groups=new Map();
     tabs.forEach((tab,index)=>{
       const code=String(tab.dataset.countryCode||'').trim().toUpperCase();
       const country=/^[A-Z]{2}$/.test(code)?code:'OTHER';
       if(!groups.has(country))groups.set(country,{tab,indices:[]});
       groups.get(country).indices.push(index);
       if(rows[index]){
         rows[index].dataset.tp80CountryCode=country;
         rows[index].dataset.tp80ServerId=tab.dataset.server||'';
       }
     });
     const bar=el('nav','tp80-country-bar');
     bar.setAttribute('aria-label','فیلتر کشورها');
     const all=el('button','active','همه');
     all.type='button';all.dataset.tp80Country='ALL';bar.append(all);
     const choices=[all];
     const filterByCountry=country=>{
       rows.forEach(row=>{
         const visible=country==='ALL'||row.dataset.tp80CountryCode===country;
         row.hidden=!visible;
         row.dataset.tp80CountryHidden=visible?'0':'1';
         const detail=row.nextElementSibling;
         if(detail?.classList.contains('tp80-inline-native-detail')){
           detail.hidden=true;
           detail.dataset.tp80Expanded='0';
         }
         row.querySelector('.tp80-detail-toggle')?.setAttribute('aria-expanded','false');
         row.querySelector('.tp80-detail-toggle')?.replaceChildren('نمایش اطلاعات');
       });
       choices.forEach(btn=>btn.classList.toggle('active',btn.dataset.tp80Country===country));
       // Filtering must not invoke tab.click(): older scripts reset the view.
       panel.classList.remove('tp80-detail-open');
     };
     for(const [country,group] of groups){
       const btn=el('button','');btn.type='button';btn.dataset.tp80Country=country;
       // Flags must render as images on Windows too (regional Unicode is often
       // displayed as DE/US/TR letters, not the flag artwork). Prefer the
       // actual icon already in the visible node row.
       const index=group.indices[0];
       if(country!=='OTHER')btn.append(countryImage(country));
       // Use exactly the same artwork inside each node row as the filter.
       for(const index of group.indices){
         const label=rows[index]?.querySelector('.tp77-native-label');
         if(!label)continue;
         const flag=label.querySelector('img');
         const uri=knownFlag(country);
         if(flag&&uri){flag.src=uri;flag.alt=country}
         else if(!flag)label.prepend(countryImage(country));
       }
       btn.append(document.createTextNode(' '+country+(group.indices.length>1?' ('+group.indices.length+')':'')));
       btn.addEventListener('click',()=>filterByCountry(country));
       choices.push(btn);bar.append(btn);
     }
     all.addEventListener('click',()=>filterByCountry('ALL'));
     const head=panel.querySelector(':scope > .panel-head');
     head?.insertAdjacentElement('afterend',bar);
     filterByCountry('ALL');
     const inline=[];
     rows.forEach((row,index)=>{
       const tab=tabs[index];
       const view=tab?panel.querySelector('.server-view[id="'+tab.dataset.server+'"]'):null;
       const show=row.querySelector(':scope > button');
       const isFile=type==='openvpn'||type==='wireguard'||type==='amneziawg';
       const download=isFile&&view?view.querySelector('button.download-config[data-target],a.tp-v16-safe-download[href]'):null;
       if(download){
         if(show)show.remove();
         const tools=el('div','tp80-file-actions');
         download.classList.add('tp80-file-download');
         download.textContent='↓ دانلود فایل';
         tools.append(download);
         // Optional native Share sheet: send the real file with its original
         // extension/MIME. Do not invoke any VPN client or import deep-link.
         // A browser cannot force OpenVPN Connect into the OS Share targets.
         const shareFile=el('button','tp80-file-share','ارسال فایل به برنامه');
         shareFile.type='button';
         shareFile.addEventListener('click',async event=>{
           event.preventDefault();event.stopPropagation();
           const message=text=>{
             const toast=document.getElementById('toast');
             if(toast){toast.textContent=text;toast.classList.add('show')}
           };
           if(!navigator.share||typeof File==='undefined'){
             message('ابتدا فایل را دانلود کنید و از Files یا Downloads گزینه اشتراک‌گذاری را بزنید.');
             return;
           }
           const match=String(download.dataset.target||'')
             .match(/^(?:hub-protocol-\\d+-|cfg-|download-source-)(openvpn|wireguard|amneziawg)-(\\d+)$/);
           const token=location.pathname.split('/')[3]||'';
           if(!match||!token)return;
           const extension=match[1]==='openvpn'?'ovpn':'conf';
           const fallback=match[1]+'-'+(Number(match[2])+1)+'.'+extension;
           const rawName=String(download.dataset.filename||fallback).split(/[\\\\/]/).pop();
           const filename=rawName.toLowerCase().endsWith('.'+extension)?rawName:rawName+'.'+extension;
           const mime=match[1]==='openvpn'?'application/x-openvpn-profile':'application/octet-stream';
           const url='/v1/connect/'+token+'/file/'+match[1]+'/'+match[2];
           try{
             const response=await fetch(url,{cache:'no-store'});
             if(!response.ok)throw new Error('download failed');
             const file=new File([await response.arrayBuffer()],filename,{type:mime});
             if(navigator.canShare&&!navigator.canShare({files:[file]})){
               message('برای ارسال، فایل دانلودشده را از Files یا Downloads انتخاب کنید.');
               return;
             }
             await navigator.share({files:[file]});
           }catch(error){
             if(error?.name==='AbortError')return;
             message('ارسال پشتیبانی نشد؛ فایل را دانلود کنید و از Files یا Downloads ارسال کنید.');
           }
         });
         tools.append(shareFile);
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
       }else if(show&&view){
         // Move the ORIGINAL facts and copy controls directly below this node.
         // We never clone credentials/config or depend on a distant global box.
         const detail=el('section','tp80-inline-native-detail');
         detail.hidden=true;detail.dataset.tp80Expanded='0';
         detail.append(view);
         row.insertAdjacentElement('afterend',detail);
         const toggle=show;
         toggle.classList.add('tp80-detail-toggle');
         toggle.textContent='نمایش اطلاعات';
         toggle.setAttribute('aria-expanded','false');
         inline.push({row,detail,toggle,view,tab});
         toggle.addEventListener('click',event=>{
           // V77's old handler calls tab.click() and reveals the detail at the
           // bottom; intercept it to preserve the inline disclosure contract.
           event.preventDefault();event.stopImmediatePropagation();
           const opening=detail.hidden;
           inline.forEach(entry=>{
             entry.detail.hidden=true;entry.detail.dataset.tp80Expanded='0';
             entry.toggle.textContent='نمایش اطلاعات';
             entry.toggle.setAttribute('aria-expanded','false');
             entry.view.classList.remove('active');
           });
           detail.hidden=!opening;detail.dataset.tp80Expanded=opening?'1':'0';
           toggle.textContent=opening?'بستن':'نمایش اطلاعات';
           toggle.setAttribute('aria-expanded',opening?'true':'false');
           if(opening)view.classList.add('active');
         },true);
       }
     });
     panel.dataset.tp80NativeReady='1';
   }
   // V35 may regenerate shared credentials after page load. Re-home the live
   // copy buttons on every check, keeping them only once and without cloning.
   // Cisco and L2TP credentials are essential, never behind a collapsed
   // accordion. Preserve V35's original real values and native copy handlers.
   const shared=panel.querySelector(':scope > .v35-manual-credentials');
   if(shared){
     let credentials=panel.querySelector(':scope > .tp80-credentials');
     if(!credentials){
       credentials=el('section','tp80-credentials');
       shared.insertAdjacentElement('beforebegin',credentials);
     }
     credentials.append(shared);
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
     // SOCKS5 often carries both a human-readable raw credential block and
     // canonical .facts. Keep the actual copyable facts, not two copies of
     // the same secrets or a large raw text canvas.
     const socks=keyForPanel(panel)==='socks5';
     const realFacts=socks?view.querySelector('.facts'):null;
     if(realFacts){
       holder.classList.add('tp80-socks5-detail');
       view.hidden=true;
       // Some V67/V69 rules forcibly display .server-view with !important;
       // an inline important override keeps the redundant raw SOCKS dump out.
       view.style.setProperty('display','none','important');
       view.setAttribute('aria-hidden','true');
       holder.append(view,realFacts);
       toggle.textContent='نمایش اطلاعات';
     }else{
       // Reuse the ORIGINAL details/buttons. A clone would lose their handlers.
       holder.append(view);
     }
     row.insertAdjacentElement('afterend',holder);
     row.append(toggle);
     sections.push({row,holder,toggle});
     toggle.addEventListener('click',()=>{
       const opening=holder.hidden;
       sections.forEach(section=>{
         section.holder.hidden=true;
         section.toggle.textContent=section.holder.classList.contains('tp80-socks5-detail')?'نمایش اطلاعات':'نمایش کانفیگ';
       });
       holder.hidden=!opening;
       toggle.textContent=opening?'بستن':(holder.classList.contains('tp80-socks5-detail')?'نمایش اطلاعات':'نمایش کانفیگ');
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

 function reconcileV2rayCopyActions(panel){
   if(panel.dataset.v54V2ray!=='1')return;
   panel.querySelectorAll('.v54-v2ray-server').forEach(card=>{
     const head=card.querySelector(':scope > .v54-v2ray-server-head');
     if(!head)return;
     if(!head.querySelector('.tp89-v2ray-copy')){
       const copyButton=el('button','tp89-v2ray-copy','کپی کانفیگ‌ها');
       copyButton.type='button';
       copyButton.title='کپی تمام کانفیگ‌های موجود این سرور';
       copyButton.setAttribute('aria-label','کپی تمام کانفیگ‌های این سرور');
       copyButton.addEventListener('click',async event=>{
         event.preventDefault();event.stopPropagation();
         const urls=[...card.querySelectorAll('.v54-v2ray-profile[data-tp78-uri]')]
           .map(node=>node.dataset.tp78Uri).filter(Boolean);
         const unique=[...new Set(urls)];
         if(!unique.length){
           const toast=document.getElementById('toast');
           if(toast){toast.textContent='کانفیگی برای کپی موجود نیست';toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1600)}
           return;
         }
         let ok=false;
         try{
           if(navigator.clipboard&&window.isSecureContext){
             await navigator.clipboard.writeText(unique.join('\\n'));ok=true;
           }
         }catch(_error){}
         if(!ok){
           const area=document.createElement('textarea');
           area.value=unique.join('\\n');area.style.position='fixed';
           area.style.left='-9999px';document.body.append(area);area.select();
           try{ok=document.execCommand('copy')}catch(_error){}
           area.remove();
         }
         const toast=document.getElementById('toast');
         if(toast){toast.textContent=ok?'کانفیگ‌های سرور کپی شدند':'کپی انجام نشد';toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1600)}
       });
       head.append(copyButton);
     }
     const profiles=card.querySelectorAll(':scope > .v54-v2ray-profiles > .v54-v2ray-profile').length;
     const label=[...head.children].find(node=>node.tagName==='SPAN'&&/اتصال/.test(node.textContent||''));
     if(label)label.textContent=String(profiles)+' اتصال';
   });
 }


 function normalizeClassicFlags(panel){
   if(!panel.classList.contains('tp80-native'))return;
   panel.querySelectorAll('.tp77-native-label').forEach(label=>{
     const country=label.closest('.tp77-native-row')?.dataset.tp80CountryCode||'';
     if(!/^[A-Z]{2}$/.test(country))return;
     const images=[...label.querySelectorAll('img')];
     let first=images[0];
     if(!first){first=countryImage(country);label.prepend(first)}
     first.src=knownFlag(country)||'https://flagcdn.com/w40/'+country.toLowerCase()+'.png';
     first.alt=country;
     first.classList.add('tp92-node-flag');
     images.slice(1).forEach(img=>img.remove());
     // Legacy node label starts with a Unicode flag; remove that duplicate,
     // keeping the server code / name untouched.
     [...label.childNodes].filter(node=>node.nodeType===3).forEach(node=>{
       node.textContent=node.textContent.replace(/[🇦-🇿]{2}/gu,'').replace(/^\s+/,' ');
     });
   });
 }
 function normalizeV2rayCountries(panel){
   if(panel.dataset.v54V2ray!=='1')return;
   const holder=panel.querySelector(':scope > .v54-v2ray-groups');
   const cards=[...holder?.querySelectorAll(':scope > .v54-v2ray-server')||[]];
   if(!cards.length)return;
   const previous=panel.querySelector(':scope > .tp92-v2-country-bar');
   const signature=cards.map(card=>card.dataset.countryCode||'').join('|');
   if(previous?.dataset.signature===signature&&cards.every(card=>card.dataset.tp92Scoped==='1'))return;
   previous?.remove();
   const groups=new Map();
   cards.forEach(card=>{
     const code=String(card.dataset.countryCode||'').toUpperCase();
     const country=/^[A-Z]{2}$/.test(code)?code:'OTHER';
     card.dataset.tp92Country=country;
     card.dataset.tp92Scoped='1';
     if(!groups.has(country))groups.set(country,[]);
     groups.get(country).push(card);
     const head=card.querySelector(':scope > .v54-v2ray-server-head');
     if(!head)return;
     const name=head.querySelector(':scope > span:first-child');
     if(name&&!name.querySelector('.tp92-country-label')){
       const title=el('span','tp92-country-label');
       if(country!=='OTHER')title.append(countryImage(country));
       title.append(document.createTextNode(country==='OTHER'?'سرور':country+' · '+name.textContent.trim()));
       name.replaceWith(title);
     }
   });
   const bar=el('nav','tp92-v2-country-bar');
   bar.dataset.signature=signature;
   bar.setAttribute('aria-label','فیلتر کشورها');
   const buttons=[];
   function filter(code){
     cards.forEach(card=>{card.hidden=code!=='ALL'&&card.dataset.tp92Country!==code});
     buttons.forEach(b=>b.classList.toggle('active',b.dataset.country===code));
   }
   const all=el('button','active','همه');
   all.type='button';all.dataset.country='ALL';all.addEventListener('click',()=>filter('ALL'));
   buttons.push(all);bar.append(all);
   for(const [code,items] of groups){
     const btn=el('button','');
     btn.type='button';btn.dataset.country=code;
     if(code!=='OTHER')btn.append(countryImage(code));
     btn.append(document.createTextNode(' '+code+(items.length>1?' ('+items.length+')':'')));
     btn.addEventListener('click',()=>filter(code));
     buttons.push(btn);bar.append(btn);
   }
   const original=panel.querySelector(':scope > .panel-head .server-tabs,:scope > .protocol-panel-head .server-tabs');
   if(original){original.hidden=true;original.style.setProperty('display','none','important')}
   const head=panel.querySelector(':scope > .panel-head,:scope > .protocol-panel-head');
   if(head)head.insertAdjacentElement('afterend',bar);
   else holder.insertAdjacentElement('beforebegin',bar);
   filter('ALL');
 }

 function keyForPanel(panel){
   const raw=panel.dataset.ref67NativeProtocol||panel.dataset.v34Protocol;
   if(raw)return String(raw).trim().toLowerCase();
   const choice=[...document.querySelectorAll('.protocol-choice[data-protocol]')]
     .find(node=>node.dataset.protocol===panel.id);
   return String(choice?.dataset.protocolKey||'').trim().toLowerCase();
 }
 function createSudokuClientAction(){
   const os=String(document.body.dataset.tpPlatform||'').toLowerCase();
   const mobile=/Android/i.test(navigator.userAgent);
   const ios=/iPhone|iPad|iPod/i.test(navigator.userAgent);
   let target='https://github.com/SUDOKU-ASCII/sudoku-desktop/releases';
   let title='دانلود Sudoku Desktop';
   if(os==='android'||mobile){
     target='https://github.com/SUDOKU-ASCII/sudoku-android/releases';
     title='دانلود Sudodroid';
   }else if(os==='ios'||ios){
     target='https://apps.apple.com/us/app/anywhere-proxy/id6758235178';
     title='دانلود Anywhere Proxy';
   }
   const app=el('a','tp78-footer-action',title);
   app.href=target;app.target='_blank';app.rel='noopener noreferrer';
   app.dataset.kind='app';app.dataset.tp80OfficialSudoku='1';
   return app;
 }
 function ensureCanonicalApp(panel){
   // V69 may mount a real OS app AFTER V78/V80 has finalized the footer.
   // Rehome its original live link; don't display a second download card.
   const footer=panel.querySelector(':scope > .tp78-action-footer');
   if(!footer||footer.querySelector(':scope > [data-kind="app"]'))return;
   const source=panel.querySelector(':scope > .v34-client-card a[href],:scope > .ref70-app-card a[href]');
   const url=source?.getAttribute('href')||'';
   if(!source||!/^(https?:\/\/|\/(?!\/))/i.test(url))return;
   source.dataset.kind='app';source.classList.add('tp78-footer-action');
   footer.append(source);
 }
 function ensureSudokuClient(panel){
   const key=keyForPanel(panel);
   if(key!=='sudoku')return;
   let footer=panel.querySelector(':scope > .tp78-action-footer');
   if(!footer){
     footer=el('nav','tp78-action-footer');footer.setAttribute('aria-label','عملیات اشتراک');
     panel.append(footer);
   }
   const present=footer.querySelector(':scope > [data-kind="app"]');
   if(!present)footer.append(createSudokuClientAction());
 }
 function alignFooter(panel){
   // All protocol families share one footer. V51, V52 and V78 may arrive in
   // different orders. Preserve the ORIGINAL nodes and their click handlers.
   let footer=panel.querySelector(':scope > .tp78-action-footer');
   if(!footer){
     footer=el('nav','tp78-action-footer');
     footer.setAttribute('aria-label','عملیات اشتراک');
     panel.append(footer);
   }
   panel.querySelectorAll(':scope > .tp78-action-footer').forEach(other=>{
     if(other!==footer){[...other.children].forEach(node=>footer.append(node));other.remove()}
   });
   const key=keyForPanel(panel);
   const fileProtocol=['openvpn','wireguard','amneziawg'].includes(key);
   const classify=node=>{
     const declared=String(node.dataset.kind||'').toLowerCase();
     if(['add','download','copy','link','app'].includes(declared))return declared;
     const label=String(node.textContent||'').trim();
     if(/افزودن همه|import all/i.test(label))return'add';
     if(/دانلود همه|download all/i.test(label))return'download';
     if(/کپی لینک|لینک اشتراک|لینک بسته|subscription link/i.test(label))return'link';
     if(/کپی همه|کپی JSON|کپی YAML|copy all/i.test(label))return'copy';
     return'extra';
   };
   const source=panel.querySelector(':scope > .v52-multi-card .v51-multi-actions,:scope > .v51-multi-card .v51-multi-actions');
   if(source){
     [...source.children].filter(node=>node.matches('a,button')).forEach(node=>{
       node.dataset.kind=classify(node);
       node.classList.add('tp78-footer-action');
       footer.append(node);
     });
   }
   const nodes=[...footer.querySelectorAll(':scope > .tp78-footer-action')];
   const find=kind=>nodes.find(node=>node.dataset.kind===kind);
   let primary=find('add')||find('download');
   let link=find('link');
   let copy=find('copy');
   let app=find('app');
   if(fileProtocol&&!copy){
     const files=[...panel.querySelectorAll('.server-view textarea')];
     if(files.some(node=>String(node.value||node.textContent||'').trim())){
       copy=el('button','tp78-footer-action','کپی همه کانفیگ‌ها');copy.type='button';
       copy.dataset.kind='copy';
       copy.addEventListener('click',async event=>{
         event.preventDefault();event.stopPropagation();
         const value=files.map(node=>String(node.value||node.textContent||'').trim()).filter(Boolean).join('\n\n');
         if(!value)return;
         let ok=false;
         try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(value);ok=true}}catch(_e){}
         if(!ok){
           const area=document.createElement('textarea');area.value=value;
           area.style.position='fixed';area.style.left='-9999px';
           document.body.append(area);area.select();
           try{ok=document.execCommand('copy')}catch(_e){}
           area.remove();
         }
         const toast=document.getElementById('toast');
         if(toast){toast.textContent=ok?'کانفیگ‌ها کپی شدند':'کپی انجام نشد';toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),1500)}
       });
     }
   }
   // Preserve existing working download-all from V51. ZIP route is already
   // represented by that real <a> element. Do not replace it with placeholders.
   const ordered=[primary,link,copy,app].filter(Boolean);
   const extra=nodes.filter(node=>!ordered.includes(node)&&node.dataset.kind!=='app');
   const previous=[...footer.querySelectorAll(':scope > .tp80-extra-actions .tp78-footer-action')];
   // Do not discard buttons: keep original source nodes and secondary actions.
   const extras=[...new Set([...extra,...previous])];
   const expected=[...ordered,...extras];
   const current=[...footer.querySelectorAll(':scope > .tp78-footer-action')];
   const same=current.length===ordered.length&&current.every((node,i)=>node===ordered[i]);
   if(!same||footer.querySelector(':scope > .tp80-extra-actions')){
     footer.replaceChildren(...ordered);
     if(extras.length){
       const details=el('details','tp80-extra-actions');
       details.append(el('summary','','سایر فرمت‌های کانفیگ'));
       const holder=el('div','tp80-extra-list');extras.forEach(node=>holder.append(node));
       details.append(holder);footer.append(details);
     }
   }
   footer.dataset.tp80Ready='1';
   footer.dataset.tp88Layout=ordered.length>=4?'four':ordered.length===3?'three':ordered.length===2?'two':'one';
   footer.style.setProperty('--tp80-cols',String(Math.max(1,Math.min(4,ordered.length))));
 }
 function reconcileClientDownload(panel){
   const key=keyForPanel(panel);
   const noApp=/^l2tp(?:[\\/_-]?ipsec)?$/.test(key);
   let footer=panel.querySelector(':scope > .tp78-action-footer');
   if(!footer){
     footer=el('nav','tp78-action-footer');
     footer.setAttribute('aria-label','عملیات اشتراک');
     panel.append(footer);
   }
   const platform=(()=>{
     const os=String(document.body.dataset.tpPlatform||'').toLowerCase();
     if(['windows','android','ios','macos','linux'].includes(os))return os;
     const ua=String(navigator.userAgent||'').toLowerCase();
     if(/android/.test(ua))return'android';
     if(/iphone|ipad|ipod/.test(ua))return'ios';
     if(/macintosh|mac os/.test(ua))return'macos';
     if(/linux/.test(ua))return'linux';
     return'windows';
   })();
   // Reuse actual OS-specific app URLs from earlier Connection layers.
   // Never use the #apps placeholder as a download.
   const candidates=[...panel.querySelectorAll('.v34-client-card a[href],.ref70-app-card a[href],.v13-client-only a[href]')];
   const original=candidates.find(a=>{
     const u=String(a.getAttribute('href')||'');
     return u.startsWith('https://')||u.startsWith('http://')||u.startsWith('/v1/connect/app-download/');
   });
   const appTypes={
     cisco:'openconnect',openconnect:'openconnect',openvpn:'openvpn',
     wireguard:'wireguard',amneziawg:'amneziawg',trusttunnel:'trusttunnel',
     sudoku:'sudoku',v2ray:'karing',hysteria2:'karing',
     tuic:'karing',anytls:'karing',naive:'karing',
     shadowtls:'karing',snell:'karing',mieru:'karing',
     socks5:'karing'
   };
   const appName=appTypes[key];
   const supportedPlatforms={
     openconnect:['windows','android','ios'],
     openvpn:['windows','android','ios'],
     wireguard:['windows','android','ios','macos'],
     amneziawg:['windows','android','ios','macos'],
     trusttunnel:['windows','android','ios','macos'],
     sudoku:['windows','android','ios','macos'],
     karing:['windows','android','ios','macos','linux']
   };
   const canonical=appName&&supportedPlatforms[appName]?.includes(platform)
     ?'/v1/connect/app-download/'+appName+'/'+platform:null;
   const existing=[...footer.querySelectorAll('[data-kind="app"]')];
   const sourceHref=original?.getAttribute('href')||'';
   const validSource=sourceHref.startsWith('https://')||sourceHref.startsWith('http://')||sourceHref.startsWith('/v1/connect/app-download/');
   const href=canonical||(validSource?sourceHref:null);
   if(noApp||!href){
     existing.forEach(node=>node.remove());
   }else{
     // Never move a legacy app anchor from a hidden card into the footer.
     // Legacy classes/inline styles can keep it invisible even after reparenting.
     let app=existing.find(node=>node.dataset.tp91App==='1'&&node.tagName==='A');
     if(!app){
       app=el('a','tp78-footer-action tp91-client-download','دانلود برنامه');
       app.dataset.tp91App='1';
     }
     app.dataset.kind='app';
     app.setAttribute('href',href);
     app.setAttribute('target','_blank');
     app.setAttribute('rel','noopener noreferrer');
     const appLabels={openvpn:'OpenVPN',wireguard:'WireGuard',amneziawg:'AmneziaWG',openconnect:'OpenConnect',trusttunnel:'TrustTunnel',sudoku:'Sudoku',karing:'Karing'};
     app.textContent='دانلود '+(appLabels[appName]||appName);
     app.removeAttribute('hidden');
     app.removeAttribute('style');
     app.setAttribute('aria-label','دانلود برنامه اتصال '+key);
     if(app.parentElement!==footer)footer.append(app);
     existing.filter(node=>node!==app).forEach(node=>node.remove());
   }
   panel.querySelectorAll('.v34-client-card,.ref70-app-card,.v13-client-only').forEach(card=>card.remove());
   panel.querySelectorAll(':scope > .ref69-download-cta').forEach(node=>node.remove());
   // Merge canonical actions first: V80 rebuilds footer children.
   alignFooter(panel);
   // v2rayN is an additional named Windows installer, not a copy/import button.
   // Mount it AFTER alignFooter so the reconciliation does not discard it.
   const oldExtra=footer.querySelector(':scope > .tp92-v2rayn');
   if(key==='v2ray'&&platform==='windows'){
     let extra=oldExtra;
     if(!extra){extra=el('a','tp92-v2rayn','دانلود v2rayN')}
     extra.href='https://github.com/2dust/v2rayN/releases/latest';
     extra.target='_blank';extra.rel='noopener noreferrer';
     extra.dataset.tp92Client='v2rayn';
     if(extra.parentElement!==footer)footer.append(extra);
   }else oldExtra?.remove();
   footer.dataset.tp92OnlyApp=footer.querySelectorAll(':scope > .tp78-footer-action').length===1?'1':'0';
   const actions=[...footer.querySelectorAll(':scope > .tp78-footer-action')];
   const count=actions.length;
   footer.dataset.tp88Layout=count>=4?'four':count===3?'three':count===2?'two':'one';
   footer.style.setProperty('--tp80-cols',String(Math.max(1,Math.min(4,count))));
   footer.dataset.tp80Ready='1';
   panel.querySelectorAll('.tp77-native-label').forEach(label=>{
     [...label.querySelectorAll('img')].slice(1).forEach(img=>img.remove());
   });
 }
 function installMobileDetailsDialog(){
   if(document.getElementById('tp84-dialog'))return;
   const overlay=el('div','tp84-dialog');overlay.id='tp84-dialog';overlay.hidden=true;
   overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');
   const card=el('div','tp84-dialog-card'),head=el('div','tp84-dialog-head');
   const title=el('strong','','اطلاعات سرور'),close=el('button','tp84-dialog-close','بستن');
   close.type='button';const body=el('div','tp84-dialog-body');
   head.append(title,close);card.append(head,body);overlay.append(card);document.body.append(overlay);
   let selected=null,placeholder=null,previousFocus=null,previousOverflow='';
   function shut(){
     if(overlay.hidden)return;
     if(selected&&placeholder?.parentNode){
       placeholder.replaceWith(selected);
       if(selected.classList.contains('tp80-inline-native-detail')||selected.classList.contains('tp80-modern-detail')){
         selected.hidden=true;selected.dataset.tp80Expanded='0';
       }
     }
     body.replaceChildren();selected=null;placeholder=null;overlay.hidden=true;
     document.body.style.overflow=previousOverflow;
     if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});
   }
   function reveal(content,label,trigger){
     if(!content)return;
     shut();previousFocus=trigger;previousOverflow=document.body.style.overflow;
     placeholder=document.createComment('tp84-original-detail');
     content.parentNode.insertBefore(placeholder,content);
     selected=content;content.hidden=false;
     title.textContent=label||'اطلاعات سرور';
     body.append(content);overlay.hidden=false;document.body.style.overflow='hidden';close.focus();
   }
   close.addEventListener('click',shut);
   overlay.addEventListener('click',event=>{if(event.target===overlay)shut()});
   document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!overlay.hidden){event.preventDefault();shut()}});
   document.addEventListener('click',event=>{
     if(!overlay.hidden)return;
     const trigger=event.target.closest('.tp80-detail-toggle,.v54-v2ray-server-head,.tp77-native-row > button');
     if(!trigger||!trigger.closest('.protocol-panel.active'))return;
     const panel=trigger.closest('.protocol-panel'),row=trigger.closest('.tp77-native-row,.ref67-row,.v54-v2ray-server');
     if(!row)return;
     setTimeout(()=>{
       if(!overlay.hidden)return;
       let detail=null;
       if(row.classList.contains('v54-v2ray-server')){
         detail=row.querySelector('.v54-v2ray-profiles');
         if(!row.classList.contains('open'))return;
       }else{
         const following=row.nextElementSibling;
         if(following?.matches('.tp80-inline-native-detail,.tp80-modern-detail')&&!following.hidden)detail=following;
       }
       if(detail)reveal(detail,row.querySelector('.tp77-native-label,.ref67-row-name,.v54-v2ray-server-name')?.textContent.trim(),trigger);
     },0);
   },true);
 }

 function watchAsyncV2rayNodes(){
   if(document.body.dataset.tp90V2rayWatch==='1')return;
   document.body.dataset.tp90V2rayWatch='1';
   const seen=new WeakSet();
   const scan=()=>{
     panels().forEach(panel=>{
       if(panel.dataset.v54V2ray!=='1')return;
       const holder=panel.querySelector(':scope > .v54-v2ray-groups');
       if(!holder||seen.has(holder))return;
       seen.add(holder);
       const observer=new MutationObserver(records=>{
         // Observe newly mounted server cards only. Appending the copy button
         // itself must never cause an endless mutation/reconciliation loop.
         if(!records.some(record=>[...record.addedNodes].some(node=>
           node.nodeType===1&&(node.matches?.('.v54-v2ray-server')||node.querySelector?.('.v54-v2ray-server'))
         )))return;
         reconcileV2rayCopyActions(panel);
         normalizeV2rayCountries(panel);
       });
       observer.observe(holder,{childList:true,subtree:true});
       reconcileV2rayCopyActions(panel);
       normalizeV2rayCountries(panel);
     });
   };
   scan();
   let tries=0;
   const timer=setInterval(()=>{scan();if(++tries>=45)clearInterval(timer)},500);
 }
 function check(){
   reconcileProtocolSelection();
   installMobileDetailsDialog();
   watchAsyncV2rayNodes();
   panels().forEach(panel=>{
     normalizeNative(panel);
     normalizeClassicFlags(panel);
     normalizeV2ray(panel);
     normalizeV2rayCountries(panel);
     reconcileV2rayCopyActions(panel);
     normalizeModern(panel);
     alignFooter(panel);
     ensureCanonicalApp(panel);
     ensureSudokuClient(panel);
     reconcileClientDownload(panel);
   });
 }
 check();
 // Older client-card mount scripts may run after first paint. Keep their
 // single client action reconciled without reloading the whole Connection page.
 let n=0;
 const timer=setInterval(()=>{check();if(++n>=35)clearInterval(timer)},300);
 // No perpetual 1.2s reordering: the bounded startup reconciliation above suffices.
})();
</script>
"""

def refine_public_connection_unified_surface_dates_v80(source: str) -> str:
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + "\n<!-- " + _MARKER + " -->\n</body>", 1)
