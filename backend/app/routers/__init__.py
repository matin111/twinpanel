# Register support live-chat extension routes before the shared routers are
# included by app.main. Importing this module attaches the delta endpoint to
# the existing support admin router without changing its public prefix.
from . import support_live_delta as _support_live_delta  # noqa: F401

# Register the existing Exit management compatibility layer first.
from .. import ssh_management_fallback_v61 as _ssh_management_fallback_v61  # noqa: F401

# Register the V64 tunnel-independent Exit bootstrap/control layer before
# destructive routes. V64 imports V63 only as a compatibility base, then
# replaces its nc-backed public bootstrap with native OpenSSH stdio forwarding
# and installs the long-lived Agent relay outbound from Exit -> Iran.
from .. import node_bootstrap_control_v64 as _node_bootstrap_control_v64  # noqa: F401

# Register guarded DELETE routes before app.main includes nodes/tunnels.
from . import destructive_safety as _destructive_safety  # noqa: F401
