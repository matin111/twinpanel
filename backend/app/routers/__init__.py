# Register support live-chat extension routes before the shared routers are
# included by app.main. Importing this module attaches the delta endpoint to
# the existing support admin router without changing its public prefix.
from . import support_live_delta as _support_live_delta  # noqa: F401

# Register the existing Exit management compatibility layer first.
from .. import ssh_management_fallback_v61 as _ssh_management_fallback_v61  # noqa: F401

# Register the V64 tunnel-independent Exit bootstrap/control layer before
# destructive routes. V64 owns the long-lived Agent relay and remains the
# compatibility base for existing installations.
from .. import node_bootstrap_control_v64 as _node_bootstrap_control_v64  # noqa: F401

# V66/V70 keep the direct-outbound Agent preference and legacy compatibility
# bases used by the current control plane.
from .. import node_bootstrap_control_v66 as _node_bootstrap_control_v66  # noqa: F401

# V72 replaces V71's nested AsyncSSH proxy stream completely. When direct
# Controller -> Exit SSH is unavailable, one authenticated Iran management
# session launches native OpenSSH on Iran and executes Exit installer commands
# through a bounded ControlMaster. Iran is bootstrap/fallback only.
from .. import node_bootstrap_control_v72 as _node_bootstrap_control_v72  # noqa: F401

# V73 keeps the V72 architecture unchanged and only hardens failed-open
# lifecycle cleanup so rejected auth/TCP/host-key attempts cannot leave a
# bootstrap workspace or native ControlMaster behind.
from .. import node_bootstrap_control_v73 as _node_bootstrap_control_v73  # noqa: F401

# Register guarded DELETE routes before app.main includes nodes/tunnels.
from . import destructive_safety as _destructive_safety  # noqa: F401

# TWINPANEL_PROTOCOL_CATALOG_V1
# runtime_endpoints is the first APIRouter included by app.main and has no
# prefix of its own. Attach protocol-management routes here so they are
# registered before compatibility routers without removing rollback paths.
from . import runtime_endpoints as _runtime_endpoints
from .classic_protocol_admin_v1 import router as _classic_protocol_admin_v1_router
from .modern_protocol_admin_v2 import router as _modern_protocol_admin_v2_router
from .storefront_theme_media import router as _storefront_theme_media_router

_runtime_endpoints.router.include_router(_classic_protocol_admin_v1_router)
_runtime_endpoints.router.include_router(_modern_protocol_admin_v2_router)
_runtime_endpoints.router.include_router(_storefront_theme_media_router)
