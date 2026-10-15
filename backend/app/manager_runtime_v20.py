from __future__ import annotations

from .manager_runtime_v19 import install_manager_runtime_v19
from .transport_policy_v20 import install_transport_policy_v20
from .kernel_gre_auto_v21 import install_kernel_gre_active_v21
from .auto_eligibility_v24 import install_auto_eligibility_v24
from .auto_ineligible_active_exit_v25 import (
    install_auto_ineligible_active_exit_v25,
)


# ============================================================
# TWINPANEL MANAGER RUNTIME V20 + KERNEL GRE ACTIVE V21 + V24/V25
#
# Reuse V19's self-hosted + multi-exit Backhaul hooks, replace only the
# transport selection policy with Performance Auto V20, then extend that proven
# policy with the TP27 Core-parity kernel_gre member. Manual authority and V20
# anti-flap semantics remain unchanged for ordinary candidate changes.
#
# V24 adds a narrow per-member Auto eligibility gate. A transport explicitly
# marked auto_eligible=false remains installed/healthy/manual-selectable but is
# excluded from Auto ranking until its path is performance-qualified.
#
# V25 gives an explicit Auto exclusion immediate authority when that member is
# already active: the manager selects the best eligible candidate through V20,
# fresh-probes that target, and switches only when the replacement is healthy.
# ============================================================


def install_manager_runtime_v20() -> None:
    install_manager_runtime_v19()
    install_transport_policy_v20()
    install_kernel_gre_active_v21()
    install_auto_eligibility_v24()
    install_auto_ineligible_active_exit_v25()

    print(
        "TWINPANEL_MANAGER_RUNTIME_V20_ACTIVE "
        "backhaul_multi_exit=1 performance_auto=1 all_transports=1 "
        "kernel_gre_active_v21=1 auto_eligibility_v24=1 "
        "auto_ineligible_active_exit_v25=1",
        flush=True,
    )
