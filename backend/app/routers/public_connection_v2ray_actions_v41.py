from __future__ import annotations

from . import public_connection_all_multilink_v34 as multilink
from . import public_connection_modern_delivery_v13 as modern_delivery
from .public_connection_mobile_sheet_v42 import refine_public_connection_mobile_sheet_v42
from .public_connection_v2ray_multilink_v43 import apply_v2ray_multilink_v43


apply_v2ray_multilink_v43()
# Keep backend compatibility metadata unchanged. The final customer-facing
# client card below is rewritten per device to the V2Ray/Xray client family.
modern_delivery.CLIENTS["v2ray"] = modern_delivery._KARING
multilink.PROTOCOL_CLIENT["v2ray"] = "karing"

_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41 */
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v34-client-card{
  display:flex!important;
  visibility:visible!important;
  opacity:1!important;
}
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .v38-server-list-title,
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .server-views,
body.v41-v2ray-two-actions .protocol-panel[data-v41-v2ray="1"] .tp-v41-profile-toggle{
  display:none!important;
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectV2rayActionsV41">
(function(){
  let timer=null;

  const CLIENTS={
    windows:{name:'v2rayN',url:'https://github.com/2dust/v2rayN/releases/latest'},
    macos:{name:'v2rayN',url:'https://github.com/2dust/v2rayN/releases/latest'},
    linux:{name:'v2rayN',url:'https://github.com/2dust/v2rayN/releases/latest'},
    android:{name:'v2rayNG',url:'https://github.com/2dust/v2rayNG/releases/latest'},
    ios:{name:'V2Box',url:'https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690'},
    unknown:{name:'v2rayN / v2rayNG / V2Box',url:'https://github.com/2dust/v2rayN/releases/latest'}
  };

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='xray')return'v2ray';
    return key;
  }

  function panelKey(panel){
    const direct=normalize(panel?.dataset?.v34Protocol||panel?.dataset?.modernProtocol||'');
    if(direct)return direct;
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||panel?.id||'');
  }

  function platform(){
    const explicit=String(document.body?.dataset?.tpPlatform||document.documentElement?.dataset?.tpPlatform||'').trim().toLowerCase();
    if(CLIENTS[explicit])return explicit;
    const ua=String(navigator.userAgent||'');
    const navPlatform=String(navigator.platform||'');
    const haystack=(ua+' '+navPlatform).toLowerCase();
    if(/android/i.test(ua))return'android';
    if(/iphone|ipad|ipod/i.test(ua))return'ios';
    if(/macintosh|mac os|macintel/i.test(haystack)&&Number(navigator.maxTouchPoints||0)>1)return'ios';
    if(/windows|win32|win64|winarm/i.test(haystack))return'windows';
    if(/macintosh|mac os|macintel/i.test(haystack))return'macos';
    if(/linux|x11|cros/i.test(haystack))return'linux';
    return'unknown';
  }

  function rewriteClientDownload(panel){
    const card=panel.querySelector('.v34-client-card');
    if(!card)return;
    const client=CLIENTS[platform()]||CLIENTS.unknown;
    card.hidden=false;
    card.removeAttribute('aria-hidden');
    card.style.removeProperty('display');
    card.dataset.v41ClientDownload='1';
    card.dataset.v41V2rayClient=client.name;

    const links=[...card.querySelectorAll('a')];
    const link=links[0]||null;
    links.slice(1).forEach(node=>node.remove());
    if(link){
      link.href=client.url;
      link.target='_blank';
      link.rel='noopener noreferrer';
      link.textContent='دانلود '+client.name;
      link.setAttribute('aria-label','دانلود '+client.name+' برای V2Ray / Xray');
      link.dataset.client=client.name.toLowerCase();
    }
  }

  function removeLowerConfigSection(panel){
    panel.querySelectorAll('.v38-server-list-title,.tp-v41-profile-toggle,.server-views').forEach(node=>node.remove());
    panel.dataset.v41LowerConfigsRemoved='1';
  }

  function apply(){
    document.body.classList.add('v41-v2ray-two-actions');
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      if(panelKey(panel)!=='v2ray')return;
      panel.dataset.v41V2ray='1';
      rewriteClientDownload(panel);
      removeLowerConfigSection(panel);
    });
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,250);
  window.setTimeout(apply,850);
  window.setTimeout(apply,1600);
  window.addEventListener('resize',()=>{
    clearTimeout(timer);
    timer=window.setTimeout(apply,220);
  },{passive:true});
  window.addEventListener('pagehide',()=>clearTimeout(timer),{once:true});
})();
</script>
"""


def refine_public_connection_v2ray_actions_v41(source: str) -> str:
    """Hide the lower V2Ray/Xray config inventory and show one device-appropriate client."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return refine_public_connection_mobile_sheet_v42(source)
