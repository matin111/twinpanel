from __future__ import annotations


_V11_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_DEVICE_ACTIONS_V11 */
body[data-public-connect-mobile="v7"] .mobile-send-btn{
  display:none;
}
body[data-public-connect-mobile="v7"].tp-mobile-device .mobile-send-btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
}
"""


_V11_SCRIPT = r"""
<script id="twinpanelPublicConnectDeviceActionsV11">
(function(){
  const body=document.body;
  function isActualMobileDevice(){
    const uaData=navigator.userAgentData;
    if(uaData&&typeof uaData.mobile==='boolean')return uaData.mobile;
    const ua=String(navigator.userAgent||'');
    if(/Android|iPhone|iPad|iPod|IEMobile|Opera Mini|Mobile/i.test(ua))return true;
    if(/Macintosh/i.test(ua)&&Number(navigator.maxTouchPoints||0)>1)return true;
    return false;
  }
  body.classList.toggle('tp-mobile-device',isActualMobileDevice());
  body.classList.toggle('tp-desktop-device',!isActualMobileDevice());
})();
</script>
"""


def refine_public_connection_device_actions_v11(source: str) -> str:
    """Show phone-transfer actions only on actual mobile devices, never desktop browsers."""
    if "TWINPANEL_PUBLIC_CONNECT_DEVICE_ACTIONS_V11" in source:
        return source
    source = source.replace("</style>", _V11_CSS + "\n</style>", 1)
    source = source.replace("</body>", _V11_SCRIPT + "\n</body>", 1)
    return source
