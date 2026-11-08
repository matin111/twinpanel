from __future__ import annotations

"""Final consistency contract for the Connection public page.

Presentation only: preserve all original URL/credential/config/OS-download action
DOM elements and their handlers. Only one protocol and one expanded node detail.
"""
_MARKER = "TWINPANEL_CONNECTION_UNIFIED_SURFACE_DATES_V80"

_CSS = r"""
/* TWINPANEL_CONNECTION_UNIFIED_SURFACE_DATES_V80 */
html body.tp80-connection .traffic .stats{display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;align-items:stretch!important;min-width:0}
/* Four meaningful stats: devices, connections, used / total quota, expiry. */
html body.tp80-connection .traffic .stats:has(>.stat[data-tp80-quota-merged="1"]){grid-template-columns:repeat(4,minmax(0,1fr))!important}
html body.tp80-connection .traffic .stats>.stat[data-tp80-quota-merged="1"]{display:none!important}
html body.tp80-connection .traffic .stats>.stat[data-tp80-quota-merged="1"]:nth-child(n+4){display:none!important}
html body.tp80-connection .traffic .stats>.stat strong[dir="ltr"]{white-space:nowrap!important}
/* Keep the Persian quota caption centered directly beneath its LTR numeric value. */
html body.tp80-connection .traffic .stats>.stat:nth-child(3){
 align-items:center!important;text-align:center!important;
}
html body.tp80-connection .traffic .stats>.stat:nth-child(3)>small,
html body.tp80-connection .traffic .stats>.stat:nth-child(3)>strong{
 display:block!important;width:100%!important;max-width:100%!important;
 margin-inline:0!important;padding-inline:0!important;text-align:center!important;
 align-self:center!important;
}
html body.tp80-connection .traffic .stats>.stat:nth-child(3)>small{direction:rtl!important;unicode-bidi:plaintext!important}
html body.tp80-connection .traffic .stats>.stat:nth-child(3)>strong{direction:ltr!important;unicode-bidi:isolate!important}

@media(max-width:720px){
 html body.tp80-connection .traffic .stats:has(>.stat[data-tp80-quota-merged="1"]){grid-template-columns:repeat(2,minmax(0,1fr))!important}
 html body.tp80-connection .traffic .stats:has(>.stat[data-tp80-quota-merged="1"])>.stat{grid-column:auto!important}
 html body.tp80-connection .traffic .stats>.stat[data-tp80-quota-merged="1"]{display:none!important}
}

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


/* Compact contextual help, isolated from protocol download/connection buttons. */
html body.tp80-connection .protocol-panel .tp-help-launch{
  margin-inline-start:auto!important;flex:0 0 auto!important;
  width:36px!important;height:36px!important;min-height:36px!important;
  border:1px solid var(--tp-brand-stroke,#4a5c81)!important;border-radius:11px!important;
  background:var(--tp-brand-raised,#263450)!important;color:var(--tp-brand-text,#fff)!important;
  font-size:17px!important;font-weight:800!important;cursor:pointer!important;
  display:inline-flex!important;align-items:center!important;justify-content:center!important;
}
body .tp-help-overlay[hidden]{display:none!important}
body .tp-help-overlay{
  position:fixed!important;inset:0!important;z-index:2147483300!important;
  background:#030817d9!important;display:flex!important;align-items:center!important;
  justify-content:center!important;padding:16px!important;box-sizing:border-box!important;
}
body .tp-help-card{
  width:min(440px,100%)!important;max-height:85dvh!important;overflow:auto!important;
  border-radius:17px!important;border:1px solid var(--tp-brand-stroke,#52688b)!important;
  background:var(--tp-brand-card,#121e36)!important;color:var(--tp-brand-text,#fff)!important;
  padding:18px!important;direction:rtl!important;text-align:right!important;
  box-shadow:0 20px 75px #0009!important;
}
body .tp-help-head{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;margin-bottom:12px!important}
body .tp-help-title{font-size:17px!important;font-weight:850!important}
body .tp-help-close{border:1px solid #4b5c79!important;border-radius:9px!important;padding:6px 12px!important;color:inherit!important;background:transparent!important;cursor:pointer!important}
body .tp-help-step{font-size:13px!important;line-height:2!important;color:inherit!important;margin:7px 0!important}
body .tp-help-foot{font-size:12px!important;opacity:.76!important;margin-top:12px!important;line-height:1.9!important}

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

/* TWINPANEL_CONNECTION_SINGLE_COUNTRY_MODAL_FOOTER_V93 */
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .ref67-tabs,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .tp74-country-bar,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .tp80-country-bar,
html body.tp80-connection .protocol-panel[data-v54-v2ray="1"] > .server-tabs{
 display:none!important;
}
html body.tp80-connection .protocol-panel.active > .tp92-v2-country-bar{order:2!important;flex-wrap:nowrap!important;overflow-x:auto!important;direction:ltr!important}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer > a.tp92-v2rayn{
 grid-column:auto!important;min-width:0!important;min-height:54px!important;
}
html body.tp80-connection .protocol-panel.active > .tp78-action-footer:has(> a.tp92-v2rayn){
 grid-template-columns:repeat(4,minmax(0,1fr))!important;
}
html body.tp80-connection .protocol-panel.active > .tp93-country-bar{order:2!important}
html body.tp80-connection .protocol-panel.active .tp93-country-bar .active{
 background:linear-gradient(110deg,var(--p),var(--s))!important;color:white!important;
}
html body.tp80-connection .protocol-panel .tp93-country-bar + .ref67-list .ref67-row[hidden],
html body.tp80-connection .protocol-panel .tp93-country-bar + .ref67-list .tp80-modern-detail[hidden]{display:none!important}
/* Modern country selection overrides legacy display:grid!important on rows. */
html body.tp80-connection .protocol-panel .ref67-list > .ref67-row[data-tp93-country-hidden="1"],
html body.tp80-connection .protocol-panel .ref67-list > .ref67-row[hidden],
html body.tp80-connection .protocol-panel .ref67-list > .tp80-modern-detail[hidden]{
 display:none!important;
}
html body.tp80-connection #tp84-dialog:not([hidden]){
 display:flex!important;position:fixed!important;inset:0!important;z-index:2147483000!important;
 background:#070b19cc!important;align-items:center!important;justify-content:center!important;padding:16px!important;
}
html body.tp80-connection #tp84-dialog[hidden]{display:none!important}
html body.tp80-connection #tp84-dialog .tp84-dialog-card{
 width:min(660px,96vw)!important;max-height:86dvh!important;overflow:hidden!important;
 display:flex!important;flex-direction:column!important;position:relative!important;
}
html body.tp80-connection #tp84-dialog .tp84-dialog-body{overflow:auto!important;min-height:0!important}
html body.tp80-connection #tp84-dialog .tp84-dialog-body > .tp80-inline-native-detail,
html body.tp80-connection #tp84-dialog .tp84-dialog-body > .tp80-modern-detail,
html body.tp80-connection #tp84-dialog .tp84-dialog-body > .v54-v2ray-profiles{
 display:block!important;visibility:visible!important;position:static!important;
 max-height:none!important;opacity:1!important;
}

/* TWINPANEL_MOBILE_PROTOCOL_CATEGORY_FILTER_V94 */
html body.tp80-connection .protocols .protocol-choice[data-tp94-filtered="1"],
html body.tp80-connection .protocols .protocol-choice.ref67-hidden,
html body.tp80-connection .protocols .protocol-choice[hidden]{
  display:none!important;visibility:hidden!important;
}
html body.tp80-connection .ref67-categories .ref67-filter.active{
  color:#fff!important;border-color:var(--p)!important;
  background:linear-gradient(110deg,var(--p),var(--s))!important;
}

/* TWINPANEL_PROTOCOL_CARD_OPENS_MODAL_V96 */
html body.tp80-connection .protocol-panel:not(.tp96-in-modal){
 display:none!important;
}
html body.tp80-connection #tp96-protocol-modal[hidden]{display:none!important}
html body.tp80-connection #tp96-protocol-modal:not([hidden]){
 position:fixed!important;inset:0!important;display:flex!important;
 align-items:center!important;justify-content:center!important;z-index:2147482000!important;
 padding:clamp(8px,2vw,22px)!important;background:#050919d9!important;
 backdrop-filter:blur(7px)!important;
}
html body.tp80-connection #tp96-protocol-modal .tp96-protocol-shell{
 display:flex!important;flex-direction:column!important;width:min(1140px,100%)!important;
 max-height:min(92dvh,100%)!important;overflow:hidden!important;
 background:var(--tp-brand-bg,#10192e)!important;
 border:1px solid var(--tp-brand-stroke,#42577e)!important;
 border-radius:18px!important;box-shadow:0 24px 80px #0009!important;
}
html body.tp80-connection #tp96-protocol-modal .tp96-protocol-top{
 flex:0 0 auto!important;display:flex!important;align-items:center!important;
 justify-content:space-between!important;padding:10px 14px!important;
 border-bottom:1px solid var(--tp-brand-stroke,#42577e)!important;
 background:var(--tp-brand-raised,#172440)!important;
}
html body.tp80-connection #tp96-protocol-modal .tp96-protocol-title{
 color:var(--tp-brand-text,#fff)!important;font-weight:800!important;
}
html body.tp80-connection #tp96-protocol-modal .tp96-protocol-close{
 color:var(--tp-brand-text,#fff)!important;background:#26395c!important;
 border:1px solid #537097!important;border-radius:10px!important;
 padding:8px 14px!important;cursor:pointer!important;
}
html body.tp80-connection #tp96-protocol-modal .tp96-protocol-content{
 min-height:0!important;flex:1 1 auto!important;overflow:auto!important;
 overscroll-behavior:contain!important;scrollbar-gutter:stable!important;
}
html body.tp80-connection #tp96-protocol-modal .protocol-panel.tp96-in-modal{
 display:flex!important;flex-direction:column!important;position:relative!important;
 width:100%!important;max-width:none!important;min-height:0!important;
 margin:0!important;border:0!important;border-radius:0!important;box-shadow:none!important;
}
@media(max-width:720px){
 html body.tp80-connection #tp96-protocol-modal:not([hidden]){padding:7px!important;align-items:center!important}
 html body.tp80-connection #tp96-protocol-modal .tp96-protocol-shell{max-height:94dvh!important;border-radius:14px!important}
 html body.tp80-connection #tp96-protocol-modal .tp96-protocol-content{overflow:auto!important}
 html body.tp80-connection #tp96-protocol-modal .protocol-panel.tp96-in-modal{display:flex!important}
}

/* TWINPANEL_PROTOCOL_POPUP_ONLY_AND_TYPE_V97 */
/* Legacy mobile classes force .active display:flex; no protocol content
   may render in the document when it is not mounted in our modal. */
html body.tp80-connection .page .protocol-panel:not(.tp96-in-modal),
html body.tp80-connection .page .protocol-panel.active:not(.tp96-in-modal),
html body.tp80-connection .page .protocol-panel.v36-open:not(.tp96-in-modal),
html body.tp80-connection .protocol-panel.active:not(.tp96-in-modal),
html body.tp80-connection .protocol-panel.v36-open:not(.tp96-in-modal){
 display:none!important;visibility:hidden!important;max-height:0!important;
 overflow:hidden!important;pointer-events:none!important;
}
html body.tp80-connection #tp96-protocol-modal .protocol-panel.tp96-in-modal{
 display:flex!important;visibility:visible!important;max-height:none!important;
 overflow:visible!important;pointer-events:auto!important;
}
html body.tp80-connection .protocol-choice .protocol-text,
html body.tp80-connection .protocol-choice .protocol-text b{
 font-family:Inter,"Segoe UI",Arial,Tahoma,sans-serif!important;
 font-kerning:normal!important;font-synthesis:none!important;
 -webkit-font-smoothing:antialiased!important;
}
html body.tp80-connection .protocol-choice .protocol-text b{
 display:block!important;color:var(--tp-brand-text,var(--text))!important;
 font-size:clamp(11px,1.05vw,13px)!important;font-weight:800!important;
 line-height:1.45!important;letter-spacing:.1px!important;
 text-shadow:0 1px 1px #0002!important;overflow-wrap:anywhere!important;
 text-overflow:clip!important;white-space:normal!important;text-wrap:balance!important;
}
html body.tp80-connection .protocol-choice .protocol-text small{
 font-family:Inter,"Segoe UI",Tahoma,Arial,sans-serif!important;
 font-size:10px!important;font-weight:600!important;line-height:1.4!important;
 opacity:.8!important;letter-spacing:0!important;
}
html body.tp80-connection .protocol-choice{
 transition:border-color .18s ease,box-shadow .18s ease,background .18s ease!important;
}
html body.tp80-connection .protocol-choice:hover{
 border-color:var(--p)!important;
 background:color-mix(in srgb,var(--p) 6%,var(--tp-brand-raised,var(--surface)))!important;
}
@media(max-width:720px){
 html body.tp80-connection .protocol-choice .protocol-text b{
  font-size:clamp(10px,2.55vw,12px)!important;
  font-weight:800!important;line-height:1.3!important;
  letter-spacing:.05px!important;text-align:center!important;
 }
 html body.tp80-connection .protocol-choice .protocol-text small{display:none!important}
 html body.tp80-connection .protocol-choice[data-protocol-key="cisco"] .protocol-text b{
  font-size:10px!important;letter-spacing:-.15px!important;
 }
}

/* TWINPANEL_CONNECTION_PANEL_THEME_SYNC_V98
   Surface colors follow the same theme switch and branding vars (--p/--s)
   as the public hub. Overrides legacy V67 hard-coded blue/purple in BOTH
   modes; preserve all protocol interaction/layout styles. */
html[data-theme="light"]{
 color-scheme:light;
 --bg:#f3f6fc;--surface:#ffffff;--surface2:#f5f8fd;--surface3:#eaf0f8;
 --line:#dbe4f1;--text:#182438;--muted:#617087;
 --shadow:0 12px 32px rgba(27,47,79,.055);
}
html[data-theme="dark"]{
 color-scheme:dark;
 --bg:#0b1120;--surface:#111b2c;--surface2:#172337;--surface3:#1e2d44;
 --line:#34455e;--text:#eef4ff;--muted:#a7b7ce;
 --shadow:0 16px 40px rgba(0,0,0,.16);
}
html[data-theme] body.tp80-connection.ref67{
 --tp-brand-bg:var(--bg);--tp-brand-card:var(--surface);
 --tp-brand-raised:var(--surface2);--tp-brand-hover:var(--surface3);
 --tp-brand-stroke:var(--line);--tp-brand-text:var(--text);
 --tp-brand-muted:var(--muted);
 background:var(--bg)!important;color:var(--text)!important;
 background-image:none!important;
 transition:background-color .16s ease,color .16s ease;
}
html[data-theme] body.tp80-connection.ref67 .top,
html[data-theme] body.tp80-connection.ref67 .topin{
 background:var(--surface)!important;color:var(--text)!important;
 border-color:var(--line)!important;background-image:none!important;
}
html[data-theme] body.tp80-connection.ref67 .top .brand b{
 color:var(--text)!important;
}
html[data-theme] body.tp80-connection.ref67 .top .mark{
 background:linear-gradient(125deg,var(--p),var(--s))!important;
 box-shadow:0 7px 18px color-mix(in srgb,var(--p) 20%,transparent)!important;
}
html[data-theme] body.tp80-connection.ref67 .top .theme{
 background:var(--surface2)!important;color:var(--text)!important;
 border:1px solid var(--line)!important;border-radius:12px!important;
 opacity:1!important;cursor:pointer!important;
}
html[data-theme] body.tp80-connection.ref67 .top .theme:hover{
 border-color:var(--p)!important;
}
html[data-theme] body.tp80-connection.ref67 .traffic,
html[data-theme] body.tp80-connection.ref67 .ref67-user,
html[data-theme] body.tp80-connection.ref67 .protocol-choice,
html[data-theme] body.tp80-connection.ref67 .protocol-panel,
html[data-theme] body.tp80-connection.ref67 .apps,
html[data-theme] body.tp80-connection.ref67 .advanced,
html[data-theme] body.tp80-connection.ref67 .smart-card{
 background:var(--surface)!important;background-image:none!important;
 border-color:var(--line)!important;color:var(--text)!important;
 box-shadow:var(--shadow)!important;
}
html[data-theme] body.tp80-connection.ref67 .traffic{
 background:linear-gradient(110deg,color-mix(in srgb,var(--p) 5%,var(--surface)),
 var(--surface) 38%,color-mix(in srgb,var(--s) 5%,var(--surface)))!important;
}
html[data-theme] body.tp80-connection.ref67 .traffic .stat{
 border-color:var(--line)!important;background:transparent!important;
}
html[data-theme] body.tp80-connection.ref67 .traffic .stat strong,
html[data-theme] body.tp80-connection.ref67 .ref67-user strong,
html[data-theme] body.tp80-connection.ref67 .protocol-choice .protocol-text b{
 color:var(--text)!important;
}
/* Connected/valid account label takes precedence over neutral theme text. */
html[data-theme] body.tp80-connection.ref67 .traffic .ref67-user small.tp78-active-account,
html[data-theme="light"] body.tp80-connection.ref67 .traffic .ref67-user small.tp78-active-account{
 color:#32f5a2!important;font-weight:900!important;
 text-shadow:0 0 10px rgba(50,245,162,.14)!important;
}
html[data-theme] body.tp80-connection.ref67 .traffic .ref67-user:has(.tp78-active-account){
 border-color:#1f9f68!important;box-shadow:0 0 0 1px rgba(50,245,162,.2)!important;
}
html[data-theme] body.tp80-connection.ref67 .traffic .stat small,
html[data-theme] body.tp80-connection.ref67 .protocol-choice .protocol-text small,
html[data-theme] body.tp80-connection.ref67 .ref67-user .service,
html[data-theme] body.tp80-connection.ref67 .ref67-user small:not(.status){
 color:var(--muted)!important;
}
html[data-theme] body.tp80-connection.ref67 .ref67-decoration i{
 background:linear-gradient(110deg,var(--p),var(--s))!important;
 border-color:color-mix(in srgb,var(--p) 50%,var(--line))!important;
 box-shadow:4px 4px 0 color-mix(in srgb,var(--p) 18%,var(--surface3))!important;
}
html[data-theme] body.tp80-connection.ref67 .ref67-filter,
html[data-theme] body.tp80-connection.ref67 .ref67-categories .ref67-filter{
 background:var(--surface2)!important;background-image:none!important;
 border-color:var(--line)!important;color:var(--text)!important;
 box-shadow:none!important;
}
html[data-theme] body.tp80-connection.ref67 .ref67-filter.active,
html[data-theme] body.tp80-connection.ref67 .ref67-categories .ref67-filter.active{
 background:linear-gradient(115deg,var(--p),var(--s))!important;
 border-color:var(--p)!important;color:#fff!important;
 box-shadow:0 3px 12px color-mix(in srgb,var(--p) 16%,transparent)!important;
}
html[data-theme] body.tp80-connection.ref67 .ref67-categories{
 border-color:var(--line)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-choice.active{
 border-color:var(--p)!important;
 box-shadow:0 0 0 1px color-mix(in srgb,var(--p) 45%,transparent)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-choice:hover{
 background:color-mix(in srgb,var(--p) 5%,var(--surface))!important;
 border-color:var(--p)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-choice .protocol-icon{
 background:linear-gradient(135deg,var(--ref67-icon,var(--pc,var(--p))),
 color-mix(in srgb,var(--ref67-icon,var(--pc,var(--p))) 55%,var(--surface3)))!important;
}
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal{
 color:var(--text)!important;
}
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .tp96-protocol-shell,
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .tp96-protocol-content{
 background:var(--surface)!important;color:var(--text)!important;
 border-color:var(--line)!important;
}
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .tp96-protocol-top,
html[data-theme] body.tp80-connection.ref67 #tp84-dialog .tp84-dialog-head,
html[data-theme] body.tp80-connection.ref67 #tp84-dialog .tp84-dialog-body,
html[data-theme] body.tp80-connection.ref67 #tp-help-overlay .tp-help-head,
html[data-theme] body.tp80-connection.ref67 #tp-help-overlay .tp-help-body{
 background:var(--surface2)!important;color:var(--text)!important;
 border-color:var(--line)!important;
}
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .tp96-protocol-title,
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .tp96-protocol-close{
 color:var(--text)!important;
}
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .tp96-protocol-close{
 background:var(--surface3)!important;border-color:var(--line)!important;
}
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .protocol-panel.tp96-in-modal,
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .protocol-panel.tp96-in-modal .panel-head,
html[data-theme] body.tp80-connection.ref67 .protocol-panel.active > .panel-head{
 background:var(--surface)!important;
 color:var(--text)!important;border-color:var(--line)!important;
}
html[data-theme] body.tp80-connection.ref67 #tp96-protocol-modal .protocol-panel.tp96-in-modal .panel-head{
 background:linear-gradient(100deg,color-mix(in srgb,var(--p) 10%,var(--surface)),
 color-mix(in srgb,var(--s) 9%,var(--surface)))!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-panel .ref67-list,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp77-native-list,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-groups,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-server{
 background:var(--surface)!important;border-color:var(--line)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-panel .ref67-row,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp77-native-row,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-server-head,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-profile,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp80-credentials,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .fact,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp80-inline-native-detail,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp80-modern-detail{
 background:var(--surface2)!important;color:var(--text)!important;
 border-color:var(--line)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-panel .server-tab,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .ref67-chip,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp74-country-chip,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp78-footer-action,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp92-v2-country-bar button,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp93-country-bar button{
 background:var(--surface2)!important;color:var(--text)!important;
 border-color:var(--line)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-panel .server-tab.active,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .ref67-chip.active,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp74-country-chip.active,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp92-v2-country-bar button.active,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp93-country-bar button.active,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp78-footer-action[data-kind="add"],
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp78-footer-action[data-kind="download"]{
 background:linear-gradient(115deg,var(--p),var(--s))!important;
 color:#fff!important;border-color:var(--p)!important;
}
html[data-theme="light"] body.tp80-connection.ref67 .traffic .ref67-user small{
 color:var(--muted)!important;
}
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .ref67-row-name,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .tp77-native-label,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-server-head{
 color:var(--text)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp78-action-footer,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp80-extra-actions,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp80-extra-actions > summary{
 background:var(--surface)!important;color:var(--text)!important;
 border-color:var(--line)!important;
}
/* Show file actions in two compact rows, never clip Share on small touch screens. */
@media(max-width:820px),(pointer:coarse){
 html body.tp80-connection .protocol-panel.active.tp80-native .tp77-native-row[data-tp80-file-row='1']{
  display:flex!important;flex-wrap:wrap!important;align-content:center!important;
  height:auto!important;max-height:none!important;min-height:96px!important;
  overflow:visible!important;gap:7px!important;padding:9px!important;
 }
 html body.tp80-connection .protocol-panel.active.tp80-native .tp77-native-row[data-tp80-file-row='1'] .tp77-native-label{
  flex:1 1 100%!important;width:100%!important;max-width:100%!important;
  min-width:0!important;overflow:hidden!important;
 }
 html body.tp80-connection .protocol-panel.active.tp80-native .tp77-native-row[data-tp80-file-row='1'] .tp80-file-actions{
  display:flex!important;flex-flow:row wrap!important;justify-content:stretch!important;
  align-items:stretch!important;flex:1 1 100%!important;
  width:100%!important;max-width:100%!important;min-width:0!important;
  overflow:visible!important;gap:6px!important;margin:0!important;
 }
 html body.tp80-connection .protocol-panel.active.tp80-native .tp77-native-row[data-tp80-file-row='1'] .tp80-file-actions > button,
 html body.tp80-connection .protocol-panel.active.tp80-native .tp77-native-row[data-tp80-file-row='1'] .tp80-file-actions > a{
  display:inline-flex!important;flex:1 1 88px!important;width:auto!important;
  min-width:0!important;max-width:none!important;min-height:36px!important;
  height:auto!important;padding:7px 6px!important;overflow:visible!important;
  white-space:normal!important;text-overflow:clip!important;line-height:1.3!important;
 }
 html body.tp80-connection .protocol-panel.active.tp80-native .tp77-native-row[data-tp80-file-row='1'] .tp80-file-share{
  border:1px solid var(--p,#7455e8)!important;border-radius:9px!important;
  color:var(--tp-brand-text,#fff)!important;
  background:var(--tp-brand-raised,#263450)!important;font-weight:750!important;
  cursor:pointer!important;
 }
}


/* TWINPANEL_CONNECTION_EMPTY_STRIP_AND_LIGHT_CONTRAST_V99 */
html body.tp80-connection .protocol-panel > .v52-multi-card:has(.v51-multi-actions:empty),
html body.tp80-connection .protocol-panel > .v51-multi-card:has(.v51-multi-actions:empty),
html body.tp80-connection .protocol-panel > .v52-multi-card:empty,
html body.tp80-connection .protocol-panel > .v51-multi-card:empty,
html body.tp80-connection .protocol-panel > .ref67-footer:empty{
 display:none!important;min-height:0!important;height:0!important;
 margin:0!important;padding:0!important;border:0!important;
 background:transparent!important;
}
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .panel-head h3,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .panel-head h2,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .panel-head strong,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .ref67-row-name b,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .ref67-row-name strong,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .tp77-native-label,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-server-name,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-server-head,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-profile,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .ref67-row-name{
 color:var(--text,#182438)!important;text-shadow:none!important;
}
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .ref67-row-name small,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .panel-head .service,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .panel-head small,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .v54-v2ray-server-head small{
 color:var(--muted,#617087)!important;text-shadow:none!important;
}
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .tp80-modern-detail,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .tp80-credentials,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .tp80-credentials b,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .fact b,
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .fact strong{
 color:var(--text,#182438)!important;
}
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .tp78-action-footer > .tp78-footer-action:not([data-kind="add"]):not([data-kind="download"]),
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .tp80-extra-actions .tp78-footer-action{
 background:var(--surface2,#f5f8fd)!important;
 border-color:var(--line,#dbe4f1)!important;
 color:var(--text,#182438)!important;
}
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .ref67-row-actions button:not(.ref67-primary),
html[data-theme="light"] body.tp80-connection.ref67 .protocol-panel .tp80-file-copy{
 background:var(--surface2,#f5f8fd)!important;color:var(--text,#182438)!important;
 border-color:var(--line,#dbe4f1)!important;
}

/* TWINPANEL_TRUE_LIVE_COUNTRY_HIGHLIGHT_V100 */
/* Green means the quota ledger confirms a real live session/recent traffic
   from that actual country, not just a protocol being installed or selected. */
html[data-theme] body.tp80-connection.ref67 .protocol-choice.live-online,
html[data-theme] body.tp80-connection.ref67 .protocol-choice.live-online.active{
 border-color:var(--ok,#10b981)!important;
 box-shadow:0 0 0 2px color-mix(in srgb,var(--ok,#10b981) 25%,transparent)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp80-country-bar button.live-online,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp93-country-bar button.live-online,
html[data-theme] body.tp80-connection.ref67 .protocol-panel .tp92-v2-country-bar button.live-online{
 color:#fff!important;
 background:linear-gradient(125deg,#059669,#10b981)!important;
 border-color:#10b981!important;
 box-shadow:0 0 0 1px color-mix(in srgb,#10b981 25%,transparent)!important;
}
/* TWINPANEL_CISCO_COUNTRY_LIVE_STATE_V104
   Original Cisco / OpenConnect UI uses .server-tabs[data-country-code]
   rather than the newer country filter controls. Both must reflect the same
   actual per-node Cisco presence reported by /live. */
html[data-theme] body.tp80-connection.ref67 .protocol-panel .server-tabs button.server-tab.live-online{
 background:linear-gradient(120deg,#047857,#10b981)!important;
 color:#fff!important;
 border-color:#10b981!important;
 box-shadow:0 0 0 2px color-mix(in srgb,#10b981 22%,transparent)!important;
}
html[data-theme] body.tp80-connection.ref67 .protocol-choice.live-online{
 background:color-mix(in srgb,#10b981 8%,var(--surface,#fff))!important;
 border-color:#10b981!important;
}
/* TWINPANEL_CONNECTION_ENGLISH_UI_DIGITS_V101 */
html body.tp80-connection .traffic,
html body.tp80-connection .protocol-panel,
html body.tp80-connection .protocols,
html body.tp80-connection .tp96-protocol-modal{
 font-variant-numeric:lining-nums tabular-nums;
}
/* Share status stays inside its own server row; no toast that disappears. */
html body.tp80-connection .tp80-file-share-status{
 flex:1 1 100%!important;width:100%!important;max-width:100%!important;
 margin:2px 0 0!important;padding:7px 9px!important;
 border-radius:8px!important;background:var(--tp-brand-raised,#273853)!important;
 color:var(--tp-brand-text,#fff)!important;font-size:12px!important;
 font-weight:650!important;line-height:1.7!important;text-align:right!important;
 white-space:normal!important;overflow-wrap:anywhere!important;
}
html body.tp80-connection .tp80-file-share-status[hidden]{display:none!important}

/* Compact country-filtered native file servers. Hidden rows must not reserve
   their old vertical slots; the list grows only with the displayed rows. */
html body.tp80-connection .protocol-panel.active.tp80-native[data-ref67-native-protocol="openvpn"] > .tp77-native-list,
html body.tp80-connection .protocol-panel.active.tp80-native[data-ref67-native-protocol="wireguard"] > .tp77-native-list,
html body.tp80-connection .protocol-panel.active.tp80-native[data-ref67-native-protocol="amneziawg"] > .tp77-native-list{
 display:block!important;height:auto!important;min-height:0!important;
 max-height:none!important;align-content:start!important;
 grid-auto-rows:auto!important;grid-template-rows:none!important;
 overflow:hidden!important;
}
html body.tp80-connection .protocol-panel.active.tp80-native[data-ref67-native-protocol="openvpn"] .tp77-native-row[data-tp80-country-hidden="1"],
html body.tp80-connection .protocol-panel.active.tp80-native[data-ref67-native-protocol="wireguard"] .tp77-native-row[data-tp80-country-hidden="1"],
html body.tp80-connection .protocol-panel.active.tp80-native[data-ref67-native-protocol="amneziawg"] .tp77-native-row[data-tp80-country-hidden="1"]{
 display:none!important;height:0!important;min-height:0!important;
 max-height:0!important;margin:0!important;padding:0!important;
 border:0!important;visibility:hidden!important;
}

"""


_SCRIPT = r"""
<script id="twinpanelConnectionUnifiedSurfaceDatesV80">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 document.body.classList.add('tp80-connection');
 const statItems=document.querySelectorAll('.traffic .stats > .stat');
 // Index 3 is remaining quota, NOT total quota. The live refresh supplies
 // used / total from actual used_bytes / total_bytes every three seconds.
 if(statItems[2]){
   const label=statItems[2].querySelector('small');
   if(label){
     // Explicit LTR visual order of two RTL labels around a slash.
     // A plain RTL string reverses the visual order under the English quota.
     label.textContent='';
     label.setAttribute('dir','ltr');
     label.style.setProperty('display','flex','important');
     label.style.setProperty('justify-content','center','important');
     label.style.setProperty('align-items','center','important');
     label.style.setProperty('gap','4px','important');
     const usedCaption=document.createElement('span');
     usedCaption.dir='rtl';
     usedCaption.textContent='حجم مصرفی';
     const separator=document.createElement('span');
     separator.dir='ltr';
     separator.textContent='/';
     const totalCaption=document.createElement('span');
     totalCaption.dir='rtl';
     totalCaption.textContent='کل';
     label.append(usedCaption,separator,totalCaption);
   }
   const value=statItems[2].querySelector('strong');
   if(value)value.setAttribute('dir','ltr');
 }
 if(statItems[3])statItems[3].setAttribute('data-tp80-quota-merged','1');
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
 // Capture SHARE at window level BEFORE legacy document listeners.
 // A visible row-local diagnostic proves whether the tap reached the handler.
 const tpNativeSharePayloads=new WeakMap();
 window.addEventListener('click',event=>{
   const button=event.target?.closest?.('.tp80-file-share');
   if(!button||!button.isConnected)return;
   const data=tpNativeSharePayloads.get(button);
   if(!data)return;
   event.preventDefault();
   event.stopImmediatePropagation();
   const note=data.note;
   const report=message=>{if(note){note.textContent=message;note.hidden=false}};
   report('لمس دکمه دریافت شد؛ درخواست منوی ارسال…');
   let payload;
   try{payload=data.build()}catch(error){
     report('خطا هنگام آماده‌سازی فایل ('+String(error?.name||'Error')+').');
     return;
   }
   if(!payload){
     report('این مرورگر نوع فایل را برای اشتراک‌گذاری نمی‌پذیرد. گزینه دانلود فایل موجود است.');
     return;
   }
   const ua=String(navigator.userAgent||'');
   const inApp=/telegram|instagram|fbav|fban|; wv\)|webview/i.test(ua);
   const info=inApp?' در Chrome یا Safari اصلی باز کنید.':'';
   const explain=error=>{
     const name=String(error?.name||'UnknownError');
     let message=name==='AbortError'
       ?'اشتراک‌گذاری لغو شد یا برنامه دریافت‌کننده‌ای وجود ندارد'
       :name==='NotAllowedError'
         ?'مرورگر مجوز باز کردن منوی اشتراک‌گذاری را نداده'
         :name==='TypeError'?'مرورگر فایل VPN را برای Share نپذیرفته'
         :name==='InvalidStateError'?'مرورگر در حال انجام عملیات Share دیگری است'
         :'مرورگر نتوانست منوی اشتراک‌گذاری را اجرا کند';
     report(message+' ('+name+').'+info);
   };
   try{
     // No async work before this call; keep transient user activation.
     const task=navigator.share(payload);
     Promise.resolve(task).then(()=>{
       report('فایل به برنامه انتخاب‌شده تحویل داده شد.');
     }).catch(explain);
   }catch(error){explain(error)}
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
         // Legacy Connection styles can override [hidden] with display:flex !important.
         // Ensure filtered-out native rows are removed from layout, not merely invisible.
         if(visible)row.style.removeProperty('display');
         else row.style.setProperty('display','none','important');
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
         const existingVector=label.querySelector('.tp76-flag svg');
         const flag=label.querySelector('img');
         const uri=knownFlag(country);
         if(existingVector){
           // V76 already provides the country as SVG: a second image is wrong.
           [...label.querySelectorAll('img')].forEach(img=>img.remove());
         }else if(flag&&uri){flag.src=uri;flag.alt=country}
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
         // Native sharing is offered ONLY when this browser can actually share
         // a real .ovpn/.conf File. Otherwise the genuine Download button is
         // the only action; never show a dead Share button or a help popup.
         const target=String(download.dataset.target||'');
         const match=target.match(/^(?:hub-protocol-\d+-|cfg-|download-source-)(openvpn|wireguard|amneziawg)-(\d+)$/);
         const source=target?document.getElementById(target):null;
         const supported=!!(match&&source?.value?.trim()&&window.isSecureContext
           &&typeof File==='function'&&typeof navigator.share==='function'
           &&typeof navigator.canShare==='function');
         const buildSharePayload=()=>{
           if(!supported)return null;
           const config=source.value;
           if(!config||!config.trim())return null;
           if(match[1]==='openvpn'&&!/^[ \t]*remote[ \t]+\S+[ \t]+[0-9]{1,5}(?:[ \t]+(?:udp|tcp|tcp-client))?[ \t]*$/im.test(config)){
             // Fail closed: never send a truncated profile to OpenVPN Connect.
             return null;
           }
           const extension=match[1]==='openvpn'?'ovpn':'conf';
           const fallback=match[1]+'-'+(Number(match[2])+1)+'.'+extension;
           const rawName=String(download.dataset.filename||fallback);
           const filename=rawName.toLowerCase().endsWith('.'+extension)?rawName:rawName+'.'+extension;
           const preferred=match[1]==='openvpn'?'application/x-openvpn-profile':'application/octet-stream';
           for(const mime of [...new Set(['application/octet-stream',preferred,'text/plain'])]){
             const file=new File([config],filename,{type:mime});
             const payload={files:[file]};
             try{if(navigator.canShare(payload))return payload}catch(_error){}
           }
           return null;
         };
         const payload=buildSharePayload();
         if(payload){
           const shareFile=el('button','tp80-file-share','ارسال فایل به برنامه');
           shareFile.type='button';
           // Store the actual prepared File for the top-level capture handler.
           // This avoids old document handlers swallowing the mobile click.
           const note=el('span','tp80-file-share-status','');
           note.hidden=true;note.setAttribute('role','status');
           note.setAttribute('aria-live','polite');
           tpNativeSharePayloads.set(shareFile,{build:buildSharePayload,note});
           tools.append(shareFile,note);
         }

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
     // Identity V76 already contains a complete vector flag. It must be the
     // ONLY visible flag. V80 used to prepend an unnecessary PNG beside it.
     const vector=label.querySelector('.tp76-flag svg');
     if(vector){
       [...label.querySelectorAll('img')].forEach(img=>img.remove());
     }else{
       const images=[...label.querySelectorAll('img')];
       let first=images[0];
       if(!first){first=countryImage(country);label.prepend(first)}
       first.src=knownFlag(country)||'https://flagcdn.com/w40/'+country.toLowerCase()+'.png';
       first.alt=country;
       first.classList.add('tp92-node-flag');
       images.slice(1).forEach(img=>img.remove());
     }
     // Remove duplicate legacy Unicode flag text, but retain the node label.
     const textNodes=[...label.childNodes];
     const strip=node=>{
       if(node.nodeType===3){node.textContent=node.textContent.replace(/[🇦-🇿]{2}/gu,'')}
       else if(node.nodeType===1&&!node.matches('svg'))[...node.childNodes].forEach(strip);
     };
     textNodes.forEach(strip);
   });
 }

 function installProtocolCategoryFilters(){
   if(document.body.dataset.tp94CategoriesReady==='1')return;
   document.body.dataset.tp94CategoriesReady='1';
   const classic=new Set(['openvpn','wireguard','cisco','l2tp','amneziawg']);
   const recommended=new Set(['v2ray','wireguard','openvpn','hysteria2','tuic']);
   function applyCategory(category,container){
     const choices=[...document.querySelectorAll('.protocol-choice[data-protocol]')];
     if(!choices.length)return;
     const selected=String(category||'all').toLowerCase();
     const visible=[];
     choices.forEach(choice=>{
       const key=String(choice.dataset.protocolKey||'').trim().toLowerCase().replace(/[\s_]/g,'');
       const allow=selected==='all'||(selected==='classic'&&classic.has(key))
         ||(selected==='modern'&&!classic.has(key))
         ||(selected==='recommended'&&recommended.has(key));
       choice.dataset.tp94Filtered=allow?'0':'1';
       choice.classList.toggle('ref67-hidden',!allow);
       choice.hidden=!allow;
       if(allow){choice.style.removeProperty('display');visible.push(choice)}
       else choice.style.setProperty('display','none','important');
     });
     container?.querySelectorAll('.ref67-filter[data-ref67-filter]').forEach(btn=>{
       const active=btn.dataset.ref67Filter===selected;
       btn.classList.toggle('active',active);
       btn.setAttribute('aria-pressed',active?'true':'false');
     });
     if(!visible.some(choice=>choice.dataset.protocol===selectedProtocol)){
       selectedProtocol=visible[0]?.dataset.protocol||'';
     }
     reconcileProtocolSelection();
   }
   document.addEventListener('click',event=>{
     const button=event.target.closest('.ref67-categories .ref67-filter[data-ref67-filter]');
     if(!button)return;
     // V67 handlers can be overwritten by newer mobile CSS. Make exactly
     // one controller own both protocol-card visibility and selected panel.
     event.preventDefault();
     event.stopPropagation();
     applyCategory(button.dataset.ref67Filter,button.closest('.ref67-categories'));
   },true);
 }

 function normalizeRef67CountryFilters(panel){
   if(panel.dataset.v54V2ray==='1'||panel.classList.contains('tp80-native'))return;
   const source=panel.querySelector(':scope > .ref67-tabs');
   const rows=[...panel.querySelectorAll(':scope > .ref67-list > .ref67-row')];
   const originals=[...panel.querySelectorAll('.server-tab[data-server]')];
   if(!source||!rows.length||!originals.length)return;
   const key=originals.map(tab=>String(tab.dataset.countryCode||'').toUpperCase()).join(',');
   const existing=panel.querySelector(':scope > .tp93-country-bar');
   if(existing?.dataset.signature===key&&rows.length===Number(existing.dataset.rowCount)){
     const selected=panel.dataset.tp93Selected||'ALL';
     rows.forEach(row=>{
       const visible=selected==='ALL'||row.dataset.tp93Country===selected;
       row.hidden=!visible;
       row.dataset.tp93CountryHidden=visible?'0':'1';
       if(visible)row.style.removeProperty('display');
       else row.style.setProperty('display','none','important');
     });
     return;
   }
   existing?.remove();
   const bar=el('nav','tp80-country-bar tp93-country-bar');
   bar.dataset.signature=key;bar.dataset.rowCount=String(rows.length);
   bar.setAttribute('aria-label','فیلتر کشورها');
   const groups=new Map();
   rows.forEach((row,i)=>{
     const t=originals[i];let country=String(t?.dataset.countryCode||'').toUpperCase();
     if(!/^[A-Z]{2}$/.test(country)){
       const raw=t?.textContent||'';
       const flag=raw.match(/[\u{1F1E6}-\u{1F1FF}]{2}/u)?.[0];
       const fromFlag=flag?Array.from(flag).map(ch=>String.fromCharCode(ch.codePointAt(0)-0x1F1E6+65)).join(''):'';
       const fromLetters=(raw.match(/(?:^|[^A-Z])(TR|DE|US|NL|FR|GB|CA|IT|SE|FI|CH|AT|JP|SG|AE)(?=[^A-Z]|$)/i)||[])[1]?.toUpperCase()||'';
       const flagSrc=row.querySelector('.ref67-flag img')?.getAttribute('src')||'';
       const fromImage=(flagSrc.match(/\/([a-z]{2})\.(?:png|svg|webp)/i)||[])[1]?.toUpperCase()||'';
       country=fromFlag||fromLetters||fromImage||'OTHER';
     }
     row.dataset.tp93Country=country;
     if(!groups.has(country))groups.set(country,[]);
     groups.get(country).push(row);
   });
   const buttons=[];
   const filter=code=>{
     rows.forEach(row=>{
       const visible=code==='ALL'||row.dataset.tp93Country===code;
       row.hidden=!visible;
       row.dataset.tp93CountryHidden=visible?'0':'1';
       // Legacy TP78 styles force grid display with !important.
       if(visible)row.style.removeProperty('display');
       else row.style.setProperty('display','none','important');
       const details=row.nextElementSibling;
       if(details?.classList.contains('tp80-modern-detail'))details.hidden=true;
     });
     buttons.forEach(btn=>btn.classList.toggle('active',btn.dataset.country===code));
     panel.dataset.tp93Selected=code;
   };
   const all=el('button','active','همه');all.type='button';all.dataset.country='ALL';
   all.addEventListener('click',()=>filter('ALL'));buttons.push(all);bar.append(all);
   for(const [country,items] of groups){
     const btn=el('button','');btn.type='button';btn.dataset.country=country;
     if(country!=='OTHER')btn.append(countryImage(country));
     btn.append(document.createTextNode(' '+country+(items.length>1?' ('+items.length+')':'')));
     btn.addEventListener('click',()=>filter(country));buttons.push(btn);bar.append(btn);
   }
   source.style.setProperty('display','none','important');source.hidden=true;
   panel.querySelector(':scope > .panel-head')?.insertAdjacentElement('afterend',bar);
   filter(panel.dataset.tp93Selected&&buttons.some(btn=>btn.dataset.country===panel.dataset.tp93Selected)?panel.dataset.tp93Selected:'ALL');
 }
 function normalizeV2rayCountries(panel){
   if(panel.dataset.v54V2ray!=='1')return;
   const holder=panel.querySelector(':scope > .v54-v2ray-groups');
   const cards=[...holder?.querySelectorAll(':scope > .v54-v2ray-server')||[]];
   if(!cards.length)return;
   const previous=panel.querySelector(':scope > .tp92-v2-country-bar');
   panel.querySelectorAll(':scope > .ref67-tabs,:scope > .tp74-country-bar,:scope > .tp80-country-bar').forEach(node=>{
     node.hidden=true;node.style.setProperty('display','none','important');
   });
   const signature=cards.map(card=>card.dataset.countryCode||'').join('|');
   if(previous?.dataset.signature===signature&&cards.every(card=>card.dataset.tp92Scoped==='1'))return;
   const selected=panel.dataset.tp93V2Selected||'ALL';
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
     panel.dataset.tp93V2Selected=code;
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
   filter(buttons.some(btn=>btn.dataset.country===selected)?selected:'ALL');
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
   // Include secondary actions too: earlier reconciliation may have parked
   // copy-all or import-all inside the expandable extras container.
   // Remove only inert legacy containers left empty after their buttons
   // were MOVED to the canonical footer. Never delete a live action.
   panel.querySelectorAll(':scope > .v51-multi-card,:scope > .v52-multi-card').forEach(card=>{
     const actions=card.querySelector('.v51-multi-actions');
     if(actions&&actions.querySelector('a,button,input,textarea'))return;
     if(card.querySelector('a,button,input,textarea,select'))return;
     if(card.textContent.trim())return;
     card.remove();
   });
   const nodes=[...footer.querySelectorAll(':scope > .tp78-footer-action,:scope > .tp80-extra-actions .tp78-footer-action')];
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
   const client=key==='v2ray'?nodes.find(node=>node.dataset.kind==='client'&&node.classList.contains('tp92-v2rayn')):null;
   // Windows V2Ray: copy ALL configs, copy subscription link, Karing and
   // v2rayN are the four visible footer actions. Import-all remains available
   // inside secondary actions; never discard its real deep-link handler.
   const fourClients=key==='v2ray'&&client&&app&&copy;
   const ordered=(fourClients?[copy,link,app,client]:[primary,link,copy,app]).filter(Boolean);
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
     if(!extra){extra=el('a','tp92-v2rayn tp78-footer-action','دانلود v2rayN')}
     extra.href='https://github.com/2dust/v2rayN/releases/latest';
     extra.target='_blank';extra.rel='noopener noreferrer';
     extra.dataset.tp92Client='v2rayn';
     extra.dataset.kind='client';
     extra.classList.add('tp78-footer-action');
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

 function installProtocolCardModal(){
   if(document.getElementById('tp96-protocol-modal'))return;
   const overlay=el('div','tp96-protocol-modal');
   overlay.id='tp96-protocol-modal';overlay.hidden=true;
   overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');
   overlay.setAttribute('aria-label','جزئیات پروتکل');
   const shell=el('div','tp96-protocol-shell');
   const top=el('div','tp96-protocol-top');
   const title=el('strong','tp96-protocol-title','پروتکل');
   const close=el('button','tp96-protocol-close','بستن ×');close.type='button';
   close.setAttribute('aria-label','بستن پنجره پروتکل');
   const content=el('div','tp96-protocol-content');
   top.append(title,close);shell.append(top,content);overlay.append(shell);
   document.body.append(overlay);
   let current=null,anchor=null,lastFocus=null,oldOverflow='';
   function shut(){
     if(overlay.hidden)return;
     // Restore the ORIGINAL panel; cloning it would break copy/download handlers.
     if(current&&anchor?.parentNode){
       current.classList.remove('tp96-in-modal');
       anchor.replaceWith(current);
     }
     current=null;anchor=null;content.replaceChildren();overlay.hidden=true;
     document.body.style.overflow=oldOverflow;
     if(lastFocus?.isConnected)lastFocus.focus({preventScroll:true});
   }
   function open(card){
     const panel=document.getElementById(card.dataset.protocol);
     if(!panel||!panel.classList.contains('protocol-panel'))return;
     shut();
     lastFocus=card;oldOverflow=document.body.style.overflow;
     selectedProtocol=card.dataset.protocol;
     reconcileProtocolSelection();
     anchor=document.createComment('tp96-protocol-return');
     panel.parentNode.insertBefore(anchor,panel);
     current=panel;
     current.classList.add('tp96-in-modal');
     title.textContent=card.querySelector('.protocol-text b,.protocol-name,.protocol-text')?.textContent.trim()
       ||panel.querySelector('.panel-head h3')?.textContent.trim()||'پروتکل';
     content.append(panel);overlay.hidden=false;
     document.body.style.overflow='hidden';
     close.focus();
   }
   close.addEventListener('click',shut);
   overlay.addEventListener('click',event=>{if(event.target===overlay)shut()});
   document.addEventListener('keydown',event=>{
     if(event.key==='Escape'&&!overlay.hidden&&document.getElementById('tp84-dialog')?.hidden!==false){
       event.preventDefault();shut();
     }
   });
   // Window capture precedes every old document/card handler. Those legacy
   // handlers used to reveal the clicked protocol inline on mobile.
   // Stop that activation entirely and open only our dedicated popup.
   window.addEventListener('click',event=>{
     const card=event.target.closest?.('.protocol-choice[data-protocol]');
     if(!card||!document.body.contains(card)||card.hidden)return;
     event.preventDefault();event.stopImmediatePropagation();
     open(card);
   },true);
   // Keyboard activation on non-button cards.
   window.addEventListener('keydown',event=>{
     if(event.key!=='Enter'&&event.key!==' ')return;
     const card=event.target.closest?.('.protocol-choice[data-protocol]');
     if(!card||card.hidden)return;
     event.preventDefault();event.stopImmediatePropagation();open(card);
   },true);
 }

 function installMobileDetailsDialog(){
   if(document.getElementById('tp84-dialog'))return;
   const overlay=el('div','tp84-dialog');overlay.id='tp84-dialog';overlay.hidden=true;
   overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');
   const card=el('div','tp84-dialog-card'),head=el('div','tp84-dialog-head');
   const title=el('strong','','اطلاعات اتصال'),close=el('button','tp84-dialog-close','بستن');
   close.type='button';const body=el('div','tp84-dialog-body');
   head.append(title,close);card.append(head,body);overlay.append(card);document.body.append(overlay);
   let selected=null,placeholder=null,previousFocus=null,previousOverflow='';
   function shut(){
     if(overlay.hidden)return;
     if(selected&&placeholder?.parentNode){
       placeholder.replaceWith(selected);
       selected.hidden=true;
       selected.classList.remove('active');
     }
     body.replaceChildren();selected=null;placeholder=null;overlay.hidden=true;
     document.body.style.overflow=previousOverflow;
     if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});
   }
   function reveal(content,label,trigger){
     if(!content||!content.parentNode)return;
     shut();previousFocus=trigger;previousOverflow=document.body.style.overflow;
     placeholder=document.createComment('tp84-original-detail');
     content.parentNode.insertBefore(placeholder,content);
     selected=content;content.hidden=false;
     content.classList.add('active');
     title.textContent=label||'اطلاعات اتصال';
     body.append(content);overlay.hidden=false;document.body.style.overflow='hidden';close.focus();
   }
   close.addEventListener('click',shut);
   overlay.addEventListener('click',event=>{if(event.target===overlay)shut()});
   document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!overlay.hidden){event.preventDefault();shut()}});
   // Capture the click BEFORE V77/V80 inline-expansion listeners run.
   // Move the genuine view node; cloning would lose its copy handlers.
   document.addEventListener('click',event=>{
     const target=event.target.closest('.tp80-detail-toggle,.v54-v2ray-server-head');
     if(!target||!target.closest('.protocol-panel.active'))return;
     if(target.closest('.v54-v2ray-server-head')&&event.target.closest('button,a'))return;
     const row=target.closest('.tp77-native-row,.ref67-row,.v54-v2ray-server');
     if(!row)return;
     let detail=null;
     if(row.classList.contains('v54-v2ray-server')){
       detail=row.querySelector(':scope > .v54-v2ray-profiles');
     }else{
       const next=row.nextElementSibling;
       if(next?.matches('.tp80-inline-native-detail,.tp80-modern-detail'))detail=next;
     }
     if(!detail)return;
     event.preventDefault();event.stopImmediatePropagation();
     const label=row.querySelector('.tp77-native-label,.ref67-row-name,.tp92-country-label')?.textContent.trim()||'اطلاعات اتصال';
     reveal(detail,label,target);
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

 function installProtocolHelp(panel){
   const head=panel.querySelector(':scope > .panel-head,:scope > .protocol-panel-head');
   if(!head||head.querySelector(':scope > .tp-help-launch'))return;
   const btn=el('button','tp-help-launch','?');
   btn.type='button';btn.title='راهنمای اتصال';btn.setAttribute('aria-label','راهنمای این پروتکل');
   btn.addEventListener('click',event=>{
     event.preventDefault();event.stopPropagation();
     const key=keyForPanel(panel);
     const label=panel.querySelector('.panel-head h3,.protocol-panel-head h3')?.textContent.trim()||key||'پروتکل';
     const file=['openvpn','wireguard','amneziawg'].includes(key);
     const manual=['cisco','l2tp','l2tp/ipsec','openconnect'].some(x=>key.includes(x));
     const v2ray=['v2ray','xray'].includes(key);
     const instructions=file?[
       'کشور و سرور دلخواه را انتخاب کنید، سپس «دانلود فایل» را بزنید.',
       'در اندروید فایل در Downloads و در آیفون در Downloads مرورگر یا Files قابل دسترسی است.',
       'در برنامه مربوطه، گزینه Import from file را انتخاب و فایل .'+(key==='openvpn'?'ovpn': 'conf')+' دانلودشده را باز کنید.',
       'روی گوشی، در صورت پشتیبانی مرورگر، «ارسال فایل به برنامه» منوی اشتراک‌گذاری را باز می‌کند.'
     ]:manual?[
       'کشور و سرور را انتخاب کنید و نام کاربری، رمز عبور و آدرس سرور را از بخش اطلاعات اتصال دریافت کنید.',
       'برنامه سازگار را نصب کنید و اطلاعات همان سرور را در برنامه وارد کنید.',
       'اگر اتصال برقرار نشد، آدرس و اطلاعات همان سرور را دوباره بررسی کنید.'
     ]:v2ray?[
       'برای هر کشور، پروفایل‌های آماده V2Ray را باز کنید.',
       'کانفیگ موردنظر را کپی کنید یا لینک اشتراک را در v2rayN یا v2rayNG وارد کنید.',
       'پس از بروزرسانی اشتراک، یکی از اتصال‌های آماده را انتخاب کنید.'
     ]:[
       'کشور و سرور دلخواه را انتخاب کنید.',
       'از دکمه دانلود فایل، کپی کانفیگ یا لینک اشتراک همان پروتکل استفاده کنید.',
       'فایل یا لینک را در برنامه سازگار با این پروتکل اضافه کنید و اتصال را بررسی کنید.'
     ];
     const overlay=document.getElementById('tp-help-overlay');
     if(!overlay)return;
     overlay.querySelector('.tp-help-title').textContent='راهنمای '+label;
     const body=overlay.querySelector('.tp-help-body');
     body.replaceChildren(...instructions.map((line,i)=>el('p','tp-help-step',(i+1)+'- '+line)));
     overlay.hidden=false;
     overlay.querySelector('.tp-help-close').focus();
   });
   head.append(btn);
 }
 function installHelpOverlay(){
   if(document.getElementById('tp-help-overlay'))return;
   const overlay=el('div','tp-help-overlay');overlay.id='tp-help-overlay';overlay.hidden=true;
   overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');
   const card=el('div','tp-help-card');
   const head=el('div','tp-help-head'),title=el('strong','tp-help-title','راهنما');
   const close=el('button','tp-help-close','بستن');close.type='button';
   head.append(title,close);
   const body=el('div','tp-help-body');
   const note=el('p','tp-help-foot','برنامه مقصد باید از فرمت فایل یا لینک پشتیبانی کند. مسیر ذخیره فایل را مرورگر و سیستم‌عامل تعیین می‌کنند.');
   card.append(head,body,note);overlay.append(card);document.body.append(overlay);
   const shut=()=>{overlay.hidden=true};
   close.addEventListener('click',shut);
   overlay.addEventListener('click',event=>{if(event.target===overlay)shut()});
   document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!overlay.hidden)shut()});
 }

 // Visible interface digits are English on mobile and desktop. Do not
 // mutate raw configuration text, input values, URLs, scripts, or source data.
 function installEnglishInterfaceDigits(){
   if(document.body.dataset.tp101EnglishDigits==='1')return;
   document.body.dataset.tp101EnglishDigits='1';
   const persian='۰۱۲۳۴۵۶۷۸۹';
   const arabic='٠١٢٣٤٥٦٧٨٩';
   const nonAscii=/[۰-۹٠-٩]/;
   const digits=/[۰-۹٠-٩]/g;
   const skip='script,style,noscript,textarea,input,pre,code,samp,kbd,svg,[contenteditable="true"],[data-raw-config]';
   function updateText(node){
     if(node.nodeType!==3 || !node.nodeValue || !nonAscii.test(node.nodeValue))return;
     const el=node.parentElement;
     if(!el || el.closest(skip))return;
     // Never rewrite a URI or embedded configuration that an import/copy
     // handler might need byte-for-byte unchanged.
     if(/(?:vless|vmess|trojan|hysteria2|wireguard|ss):\/\//i.test(node.nodeValue))return;
     node.nodeValue=node.nodeValue.replace(digits,ch=>{
       const n=persian.indexOf(ch);
       return String(n>=0?n:arabic.indexOf(ch));
     });
   }
   function scan(root){
     if(!root)return;
     if(root.nodeType===3){updateText(root);return}
     if(root.nodeType!==1 || root.matches(skip))return;
     const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
     let textNode;
     while((textNode=walker.nextNode()))updateText(textNode);
   }
   scan(document.body);
   const observer=new MutationObserver(records=>{
     for(const record of records){
       if(record.type==='characterData'){updateText(record.target);continue}
       for(const node of record.addedNodes)scan(node);
     }
   });
   observer.observe(document.body,{childList:true,subtree:true,characterData:true});
 }

 function check(){
   installHelpOverlay();
   installProtocolCategoryFilters();
   reconcileProtocolSelection();
   installMobileDetailsDialog();
   installProtocolCardModal();
   watchAsyncV2rayNodes();
   panels().forEach(panel=>{
     installProtocolHelp(panel);
     normalizeNative(panel);
     normalizeClassicFlags(panel);
     normalizeV2ray(panel);
     normalizeV2rayCountries(panel);
     reconcileV2rayCopyActions(panel);
     normalizeModern(panel);
     normalizeRef67CountryFilters(panel);
     alignFooter(panel);
     ensureCanonicalApp(panel);
     ensureSudokuClient(panel);
     reconcileClientDownload(panel);
   });
 }
 check();
 installEnglishInterfaceDigits();
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
