# Register support live-chat extension routes before the shared routers are
# included by app.main. Importing this module attaches the delta endpoint to
# the existing support admin router without changing its public prefix.
from . import support_live_delta as _support_live_delta  # noqa: F401

# TWINPANEL_EXIT_SSH_MANAGEMENT_FALLBACK_V61
# Install the Exit-node management SSH fallback before destructive_safety or
# lifecycle_cleanup imports ssh_connect_saved. This preserves direct public SSH
# as the normal path and allows controller management through the paired Iran
# node + existing private L3 carrier when the Exit public route is unreachable.
from .. import ssh_management_fallback_v61 as _ssh_management_fallback_v61  # noqa: F401

# TWINPANEL_DESTRUCTIVE_PREFLIGHT_REGISTER_V1
# Register guarded DELETE routes before app.main includes nodes/tunnels.
# The guard performs bounded SSH preflight and rollback so an unreachable node
# cannot leave a healthy tunnel inactive or hang until nginx returns 504.
from . import destructive_safety as _destructive_safety  # noqa: F401
