from __future__ import annotations

from .manager_runtime_v19 import install_manager_runtime_v19
from .transport_policy_v20 import install_transport_policy_v20


# ============================================================
# TWINPANEL MANAGER RUNTIME V20
#
# Reuse V19's self-hosted + multi-exit Backhaul hooks, then replace only the
# transport selection policy with Performance Auto V20.
# ============================================================


def install_manager_runtime_v20() -> None:
    install_manager_runtime_v19()
    install_transport_policy_v20()

    print(
        "TWINPANEL_MANAGER_RUNTIME_V20_ACTIVE "
        "backhaul_multi_exit=1 performance_auto=1 all_transports=1",
        flush=True,
    )
