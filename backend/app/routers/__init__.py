# Register support live-chat extension routes before the shared routers are
# included by app.main. Importing this module attaches the delta endpoint to
# the existing support admin router without changing its public prefix.
from . import support_live_delta as _support_live_delta  # noqa: F401

# Register the existing Exit management compatibility layer first.
from .. import ssh_management_fallback_v61 as _ssh_management_fallback_v61  # noqa: F401

# Register the V63 node bootstrap management layer before destructive routes.
from .. import node_bootstrap_control_v63 as _node_bootstrap_control_v63  # noqa: F401

# Register guarded DELETE routes before app.main includes nodes/tunnels.
from . import destructive_safety as _destructive_safety  # noqa: F401
