# Register support live-chat extension routes before the shared routers are
# included by app.main. Importing this module attaches the delta endpoint to
# the existing support admin router without changing its public prefix.
from . import support_live_delta as _support_live_delta  # noqa: F401

# TWINPANEL_DESTRUCTIVE_PREFLIGHT_REGISTER_V1
# Register guarded DELETE routes before app.main includes nodes/tunnels.
# The guard performs bounded SSH preflight and rollback so an unreachable node
# cannot leave a healthy tunnel inactive or hang until nginx returns 504.
from . import destructive_safety as _destructive_safety  # noqa: F401
