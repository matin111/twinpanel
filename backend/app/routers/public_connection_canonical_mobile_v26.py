from __future__ import annotations

from .public_connection_mobile_refine_v28 import refine_public_connection_mobile_v28
from .public_connection_mobile_ui_v27 import refine_public_connection_mobile_ui_v27
from .public_connection_presentation_v29 import refine_public_connection_presentation_v29


_MARKER = "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26 */
@media(max-width:720px){
  /* V24 canonical panels are the only customer-facing mobile connection surface. */
  body.v24-ready .v9-mobile-stack,
  body.v24-ready .v17-mobile-stack,
  body.v24-ready .v9-apps-drawer,
  body.v24-ready .v9-insecure-note,
  body.v24-ready .v8-app-launch,
  body.v24-ready .v8-http-note,
  body.v24-ready .mobile-send-btn,
  body.v24-ready .section-head,
  body.v24-ready .apps-head,
  body.v24-ready .apps .tools,
  body.v24-ready .platform-title,
  body.v24-ready .app-card small,
  body.v24-ready .protocol-panel .action-copy,
  body.v24-ready .protocol-panel .v13-action-copy,
  body.v24-ready .protocol-panel .v13-client-only>span,
  body.v24-ready .protocol-panel .v13-native-client,
  body.v24-ready .protocol-panel .v13-pending-body,
  body.v24-ready .protocol-panel .v13-pending-apps{
    display:none!important;
  }

  /* Preserve live state as styling only; do not add explanatory status copy. */
  body.v24-ready .protocol-panel.v24-live-online .panel-head:after{
    display:none!important;
    content:none!important;
  }

  /* Canonical buttons remain visible even though older V8 mobile CSS hid them. */
  body.v24-ready .protocol-panel .action-buttons,
  body.v24-ready .protocol-panel .v13-action-buttons,
  body.v24-ready .protocol-panel .v13-client-only>div{
    display:flex!important;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectCanonicalMobileV26">
(function(){
  const MOBILE='(max-width:720px)';
  const KARING_ANDROID='https://github.com/KaringX/karing/releases/download/v1.2.25.2802/karing_1.2.25.2802_android_arm64-v8a.apk';
  const AMNEZIAWG_ANDROID='https://github.com/amnezia-vpn/amneziawg-android/releases/download/v3.1.20260814/AmneziaWG-3.1.202060814.apk';

  function text(el){return String(el?.textContent||'').trim()}

  function retireLegacy(){
    document.body.classList.remove('v9-ready','v17-ready');
    document.querySelectorAll(
      '.v9-mobile-stack,.v17-mobile-stack,.v9-apps-drawer,.v9-insecure-note'
    ).forEach(node=>node.remove());
  }

  function enforceDirectAndroidApps(){
    if(String(document.body.dataset.tpPlatform||'').toLowerCase()!=='android')return;
    document.querySelectorAll('a.v13-app,a.app-card').forEach(link=>{
      const name=text(link.querySelector('b'))||text(link);
      if(name==='Karing'||name==='دانلود Karing'){
        link.href=KARING_ANDROID;
        link.target='_blank';
        link.rel='noopener noreferrer';
        link.dataset.v26DirectInstall='1';
      }else if(name==='AmneziaWG'||name==='دانلود AmneziaWG'){
        link.href=AMNEZIAWG_ANDROID;
        link.target='_blank';
        link.rel='noopener noreferrer';
        link.dataset.v26DirectInstall='1';
      }
    });
  }

  function apply(){
    if(!window.matchMedia(MOBILE).matches)return;
    retireLegacy();
    enforceDirectAndroidApps();
    document.body.dataset.tpCanonicalMobile='v26';
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,140);
})();
</script>
"""


def refine_public_connection_canonical_mobile_v26(source: str) -> str:
    """Keep the phone surface canonical, compact and free of retired mobile renderers."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    source = refine_public_connection_mobile_ui_v27(source)
    source = refine_public_connection_mobile_v28(source)
    return refine_public_connection_presentation_v29(source)
