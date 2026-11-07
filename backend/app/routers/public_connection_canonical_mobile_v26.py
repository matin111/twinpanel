from __future__ import annotations

# Preserve legacy V30 endpoints for backward compatibility, and mount V34's
# all-protocol multi-server/direct-download routes before the public router is
# included by Hub Live. V34 remains the data/action builder; V36 owns responsive
# accordion state, V37 performs cleanup, and V38 restores the exact customer
# reference layout with an all-servers card before individual servers.
from . import public_connection_protocol_subscriptions_mount_v30 as _public_connection_protocol_subscriptions_mount_v30  # noqa: F401
from . import public_connection_forward_mount_v34 as _public_connection_forward_mount_v34  # noqa: F401
from .public_connection_forward_v34 import refine_public_connection_forward_v34
from .public_connection_manual_credentials_v35 import (
    refine_public_connection_manual_credentials_v35,
)
from .public_connection_mobile_compact_v36 import (
    refine_public_connection_mobile_compact_v36,
)
from .public_connection_final_presentation_v37 import (
    refine_public_connection_final_presentation_v37,
)
from .public_connection_reference_layout_v38 import (
    refine_public_connection_reference_layout_v38 as _v38_refiner,
)
from .public_connection_karing_remarks_v40 import (
    refine_public_connection_karing_remarks_v40,
)
from .public_connection_multilink_authority_v51 import (
    refine_public_connection_multilink_authority_v51,
)
from .public_connection_multilink_persistence_v52 import (
    refine_public_connection_multilink_persistence_v52,
)
from .public_connection_mobile_modern_surface_v53 import (
    refine_public_connection_mobile_modern_surface_v53,
)
from .public_connection_v2ray_mobile_restore_v54 import (
    refine_public_connection_v2ray_mobile_restore_v54,
)
from .public_connection_approved_responsive_ui_v65 import (
    refine_public_connection_approved_responsive_ui_v65,
)
from .public_connection_reference_desktop_mobile_v67 import (
    refine_public_connection_reference_desktop_mobile_v67,
)
from .public_connection_apps_inline_v69 import (
    refine_public_connection_apps_inline_v69,
)
from .public_connection_protocol_icons_flags_v73 import (
    refine_public_connection_protocol_icons_flags_v73,
)
from .public_connection_approved_phone_v74 import (
    refine_public_connection_approved_phone_v74,
)


def refine_public_connection_reference_layout_v38(source: str) -> str:
    """Run legacy presentation, then final Multi-Link and mobile modern cleanup authorities."""
    source = refine_public_connection_karing_remarks_v40(_v38_refiner(source))
    source = refine_public_connection_multilink_authority_v51(source)
    source = refine_public_connection_multilink_persistence_v52(source)
    source = refine_public_connection_mobile_modern_surface_v53(source)
    source = refine_public_connection_v2ray_mobile_restore_v54(source)
    source = refine_public_connection_approved_responsive_ui_v65(source)
    source = refine_public_connection_reference_desktop_mobile_v67(source)
    source = refine_public_connection_apps_inline_v69(source)
    source = refine_public_connection_protocol_icons_flags_v73(source)
    return refine_public_connection_approved_phone_v74(source)


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

  function isPhone(){
    const platform=String(document.body.dataset.tpPlatform||'').toLowerCase();
    return platform==='android'||platform==='ios';
  }

  function retireLegacy(){
    document.body.classList.remove('v9-ready','v17-ready');
    document.querySelectorAll(
      '.v9-mobile-stack,.v17-mobile-stack,.v9-apps-drawer,.v9-insecure-note'
    ).forEach(node=>node.remove());
  }

  function apply(){
    if(!isPhone()||!window.matchMedia(MOBILE).matches)return;
    retireLegacy();
    document.body.dataset.tpCanonicalMobile='v26';
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,140);
})();
</script>
"""


def refine_public_connection_canonical_mobile_v26(source: str) -> str:
    """Compose canonical Public Connect presentation without changing delivery state."""
    if _MARKER not in source:
        source = source.replace("</style>", _CSS + "\n</style>", 1)
        source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    source = refine_public_connection_manual_credentials_v35(source)
    # V36 binds the responsive accordion before V34 builds customer actions.
    source = refine_public_connection_mobile_compact_v36(source)
    source = refine_public_connection_forward_v34(source)
    # V37 cleanup remains intact; V38/V39/V40/V41/V44 execute first, V51 builds
    # the all-protocol card, V52 keeps it stable, V53 removes misleading raw
    # credential facts from modern mobile protocol sheets only, and V54 restores
    # the preserved V2Ray per-server profile container plus dedicated /sub Multi-Link.
    source = refine_public_connection_final_presentation_v37(source)
    return refine_public_connection_reference_layout_v38(source)
