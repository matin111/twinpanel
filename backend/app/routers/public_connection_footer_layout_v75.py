from __future__ import annotations

# Final approved desktop / Android / iOS / Windows / macOS presentation order.
# Preserve real action nodes, links and protocol-specific file handlers in place.
_MARKER = "TWINPANEL_PUBLIC_CONNECT_FOOTER_LAYOUT_V75"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_FOOTER_LAYOUT_V75 */
body.tp75-footer .protocol-panel{
  display:flex!important;
  flex-direction:column!important;
  align-items:stretch!important;
  gap:0!important;
}
/* First choose protocol/server and view the actual per-node connections.
   Only then show the existing, fully functional app/download/copy actions. */
body.tp75-footer .protocol-panel > .panel-head{order:0!important;flex:0 0 auto}
body.tp75-footer .protocol-panel > .ref67-tabs,
body.tp75-footer .protocol-panel > .tp74-country-bar,
body.tp75-footer .protocol-panel > .server-tabs{order:1!important;flex:0 0 auto}
body.tp75-footer .protocol-panel > .ref67-list,
body.tp75-footer .protocol-panel > .v54-v2ray-groups,
body.tp75-footer .protocol-panel > .server-views,
body.tp75-footer .protocol-panel > .v34-mobile-servers,
body.tp75-footer .protocol-panel > .v34-single-label,
body.tp75-footer .protocol-panel > .v54-v2ray-server-list{order:3!important;flex:0 0 auto}
body.tp75-footer .protocol-panel > .v51-multi-card,
body.tp75-footer .protocol-panel > .v52-multi-card,
body.tp75-footer .protocol-panel > .v34-subscription-card,
body.tp75-footer .protocol-panel > .v37-multi-card,
body.tp75-footer .protocol-panel > .v38-all-card{order:20!important;flex:0 0 auto}
body.tp75-footer .protocol-panel > .ref67-footer{order:21!important;flex:0 0 auto}
body.tp75-footer .protocol-panel > .ref70-app-card,
body.tp75-footer .protocol-panel > .v34-client-card{order:22!important;flex:0 0 auto}
body.tp75-footer .protocol-panel > .v13-client-only{order:23!important;flex:0 0 auto}
body.tp75-footer .protocol-panel > .advanced,
body.tp75-footer .protocol-panel > .v34-advanced{order:24!important;flex:0 0 auto}
/* Don't show fake duplicate proxy copies of the same buttons. Real original
   add/copy/download actions remain inside the V51/V52/V34 action cards. */
body.tp75-footer .protocol-panel:has(> .v52-multi-card) > .ref67-footer,
body.tp75-footer .protocol-panel:has(> .v51-multi-card) > .ref67-footer{display:none!important}
body.tp75-footer .protocol-panel > .v51-multi-card,
body.tp75-footer .protocol-panel > .v52-multi-card{
  width:auto!important;margin:10px 15px 0!important;padding:11px!important;
  border-radius:14px!important;border:1px solid #36466e!important;
  background:linear-gradient(135deg,#18233e,#141e38)!important;
}
body.tp75-footer .protocol-panel > .v51-multi-card .v51-multi-head,
body.tp75-footer .protocol-panel > .v52-multi-card .v51-multi-head{display:none!important}
body.tp75-footer .protocol-panel > .v51-multi-card .v51-multi-actions,
body.tp75-footer .protocol-panel > .v52-multi-card .v51-multi-actions{
  display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:8px!important;width:100%!important;direction:rtl!important;
}
body.tp75-footer .protocol-panel > .v34-subscription-card{
  margin:10px 15px 0!important;border-radius:14px!important;
}
body.tp75-footer .protocol-panel > .v34-subscription-card .v34-actions{
  display:flex!important;flex-wrap:wrap!important;gap:8px!important;
}
body.tp75-footer .protocol-panel > .v51-multi-card .v51-multi-actions>a,
body.tp75-footer .protocol-panel > .v51-multi-card .v51-multi-actions>button,
body.tp75-footer .protocol-panel > .v52-multi-card .v51-multi-actions>a,
body.tp75-footer .protocol-panel > .v52-multi-card .v51-multi-actions>button,
body.tp75-footer .protocol-panel > .v34-subscription-card .v34-actions>*{
  display:flex!important;align-items:center!important;justify-content:center!important;
  min-height:49px!important;font-size:12px!important;padding:10px 12px!important;
  border-radius:12px!important;min-width:0!important;white-space:normal!important;
  text-align:center!important;
}
body.tp75-footer .protocol-panel > .ref70-app-card,
body.tp75-footer .protocol-panel > .v34-client-card{
  margin:9px 15px 17px!important;padding:12px 14px!important;
  border:1px solid #424d77!important;border-radius:14px!important;
  background:linear-gradient(135deg,#192642,#151e38)!important;
  min-height:62px!important;box-shadow:none!important;
}
body.tp75-footer .protocol-panel > .ref70-app-card .ref69-download-cta,
body.tp75-footer .protocol-panel > .v34-client-card>a{
  min-height:41px!important;padding:9px 16px!important;
  border-radius:11px!important;font-size:12px!important;
  background:linear-gradient(115deg,var(--p),var(--s))!important;
  border:1px solid var(--p)!important;color:#fff!important;
}
/* A file remains a file: native OpenVPN/WireGuard download links and QR
   remain in their original server views. Never promote file copies to import. */
body.tp75-footer .protocol-panel[data-ref67-native-protocol="openvpn"] .server-views,
body.tp75-footer .protocol-panel[data-ref67-native-protocol="wireguard"] .server-views,
body.tp75-footer .protocol-panel[data-ref67-native-protocol="amneziawg"] .server-views{
  display:block!important;
}
body.tp75-footer .protocol-panel > .ref70-app-card .ref69-protocol-os{display:none!important}
@media(max-width:720px){
 body.tp75-footer .protocol-panel > .v51-multi-card,
 body.tp75-footer .protocol-panel > .v52-multi-card,
 body.tp75-footer .protocol-panel > .v34-subscription-card{
   margin:8px 8px 0!important;padding:8px!important;border-radius:12px!important;
 }
 body.tp75-footer .protocol-panel > .v51-multi-card .v51-multi-actions,
 body.tp75-footer .protocol-panel > .v52-multi-card .v51-multi-actions{
   grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:6px!important;
 }
 body.tp75-footer .protocol-panel > .v51-multi-card .v51-multi-actions>*,
 body.tp75-footer .protocol-panel > .v52-multi-card .v51-multi-actions>*,
 body.tp75-footer .protocol-panel > .v34-subscription-card .v34-actions>*{
   min-height:43px!important;font-size:10px!important;padding:7px 8px!important;
 }
 body.tp75-footer .protocol-panel > .v51-multi-card .v51-multi-actions>*:first-child,
 body.tp75-footer .protocol-panel > .v52-multi-card .v51-multi-actions>*:first-child{
   grid-column:span 2!important;
 }
 body.tp75-footer .protocol-panel > .ref70-app-card,
 body.tp75-footer .protocol-panel > .v34-client-card{
   flex-direction:row!important;align-items:center!important;
   margin:7px 8px 12px!important;padding:8px 10px!important;gap:8px!important;
   border-radius:12px!important;min-height:51px!important;
 }
 body.tp75-footer .protocol-panel > .ref70-app-card strong,
 body.tp75-footer .protocol-panel > .v34-client-card .v34-client-label{
   font-size:11px!important;white-space:normal!important;
 }
 body.tp75-footer .protocol-panel > .ref70-app-card .ref69-download-cta,
 body.tp75-footer .protocol-panel > .v34-client-card>a{
   min-height:37px!important;width:auto!important;min-width:92px!important;
   flex:0 0 auto!important;padding:8px!important;font-size:10px!important;
 }
 body.tp75-footer .protocol-panel > .v34-subscription-card .v34-actions{
   display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
 }
}
"""
_SCRIPT = r"""
<script id="twinpanelPublicConnectFooterLayoutV75">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 // The existing download/copy/import controls are NOT reimplemented, moved or
 // cloned. CSS order only; all event listeners, native file downloads and
 // multi-link target URLs remain intact.
 document.body.classList.add('tp75-footer');
})();
</script>
"""

def refine_public_connection_footer_layout_v75(source: str) -> str:
    if _MARKER in source:
        return source
    source=source.replace("</style>",_CSS+"\n</style>",1)
    return source.replace("</body>",_SCRIPT+"\n<!-- "+_MARKER+" -->\n</body>",1)
