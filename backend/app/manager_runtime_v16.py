from __future__ import annotations

from .backhaul_multi_exit_v16 import install_backhaul_peer_v16
from .routers import tunnels
from .self_hosted_runtime import apply_self_hosted_runtime
from .transport_policy_v18 import install_transport_policy_v18


# ============================================================
# TWINPANEL MANAGER RUNTIME V18
#
# The standalone transport-manager service does not import app.main. Apply the
# same self-hosted hooks as the API, then activate modern-first health/failover
# with the V18 public-direct multi-exit underlay.
# ============================================================


def install_manager_runtime_v16() -> None:
    # Function name is retained for the existing V11 import contract.
    apply_self_hosted_runtime()
    install_transport_policy_v18()

    if tunnels._install_backhaul_peer is not install_backhaul_peer_v16:
        raise RuntimeError("manager_backhaul_v16_hook_not_active")

    print(
        "TWINPANEL_MANAGER_RUNTIME_V18_ACTIVE "
        "modern_first=1 underlay=public-direct multi_exit=1",
        flush=True,
    )
