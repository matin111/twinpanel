from __future__ import annotations

from .backhaul_multi_exit_v16 import install_backhaul_peer_v16
from .routers import tunnels
from .self_hosted_runtime import apply_self_hosted_runtime
from .transport_policy_v19 import install_transport_policy_v19


# ============================================================
# TWINPANEL MANAGER RUNTIME V19
#
# Keep the proven self-hosted/multi-exit Backhaul hooks from Runtime V16 and
# replace only the automatic transport-selection policy with Smart Auto V19.
# Manual mode remains owned by the existing API/manager manual guard.
# ============================================================


def install_manager_runtime_v19() -> None:
    apply_self_hosted_runtime()
    install_transport_policy_v19()

    if tunnels._install_backhaul_peer is not install_backhaul_peer_v16:
        raise RuntimeError("manager_backhaul_v16_hook_not_active")

    print(
        "TWINPANEL_MANAGER_RUNTIME_V19_ACTIVE "
        "backhaul_multi_exit=1 smart_auto=1",
        flush=True,
    )
