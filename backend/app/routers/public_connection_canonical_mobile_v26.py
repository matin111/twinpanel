from __future__ import annotations

# Preserve legacy V30 endpoints for backward compatibility, and mount V34's
# all-protocol multi-server/direct-download routes before the public router is
# included by Hub Live. V34 remains the data/action builder; V36 owns responsive
# accordion state, V37 performs cleanup, V38 restores the reference HA layout,
# and V39 is the final mobile visibility/action simplification authority.
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
    refine_public_connection_reference_layout_v38,
)
from .public_connection_mobile_simplified_v39 import (
    refine_public_connection_mobile_simplified_v39,
)


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
    source = refine_public_connection_final_presentation_v37(source)
    source = refine_public_connection_reference_layout_v38(source)
    return refine_public_connection_mobile_simplified_v39(source)
