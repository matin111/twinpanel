# TWINPANEL_ACCOUNT_ENFORCEMENT_V2
# Install the durable controller-owned account enforcement bridge before routers
# import queue_subscription_enforcement. All 15 canonical account protocols are
# now controller-owned so Classic identities never depend on a node Agent command
# payload which cannot safely carry/reconstruct stored credentials.
from ..services.account_enforcement_v2 import install_account_enforcement_hooks

install_account_enforcement_hooks()

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
# prefix of its own. Keep Classic Protocol Studio and Storefront compatibility
# routes registered here. Modern Protocol Admin V3 is mounted explicitly by
# app.main before the legacy vpn_settings router. Avoid importing protocol
# runtime implementations from this package initializer: they import
# routers.provision and would create a circular import.
from . import runtime_endpoints as _runtime_endpoints
from .classic_protocol_admin_v1 import router as _classic_protocol_admin_v1_router
from .storefront_theme_media import router as _storefront_theme_media_router
from .modern_account_delivery_v1 import router as _modern_account_delivery_v1_router
from .modern_enforcement_runtime_v1 import router as _modern_enforcement_runtime_v1_router
from .subscription_protocol_lifecycle_v2 import router as _subscription_protocol_lifecycle_v2_router
from .dns_emergency import router as _dns_emergency_router
from .dns_emergency_iran import router as _dns_emergency_iran_router

# TWINPANEL_MANUAL_AUTHORITY_REGISTER_V193
# Agent reports arrive on an exact route also retained in the legacy tunnels
# router. Mount the corrected telemetry-only endpoint on runtime_endpoints,
# which app.main includes before tunnels.router, so Manual authority cannot be
# overwritten by a stale Agent selected_transport report.
from .manual_authority_v193 import router as _manual_authority_v193_router

# TWINPANEL_MODERN_ACCOUNT_DELIVERY_V1
# Account Delivery retains a legacy exact route. Mount the canonical lifecycle
# endpoint on runtime_endpoints first, following the same precedence pattern as
# Manual Authority. The implementation imports runtime drivers lazily, keeping
# routers package initialization free of provision/runtime cycles.
#
# TWINPANEL_SUBSCRIPTION_PROTOCOL_LIFECYCLE_V2
# The exact admin-edit route is also mounted here before legacy Account Delivery
# so SubscriptionProtocol can be the final desired-state authority for all 15
# protocols without rewriting the legacy delivery module.
_runtime_endpoints.router.include_router(_modern_enforcement_runtime_v1_router)
_runtime_endpoints.router.include_router(_subscription_protocol_lifecycle_v2_router)
_runtime_endpoints.router.include_router(_modern_account_delivery_v1_router)
_runtime_endpoints.router.include_router(_manual_authority_v193_router)
_runtime_endpoints.router.include_router(_classic_protocol_admin_v1_router)
_runtime_endpoints.router.include_router(_storefront_theme_media_router)
_runtime_endpoints.router.include_router(_dns_emergency_router)
_runtime_endpoints.router.include_router(_dns_emergency_iran_router)
