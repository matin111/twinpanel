from __future__ import annotations

from .manager_runtime_v19 import install_manager_runtime_v19
from .transport_policy_v20 import install_transport_policy_v20
from .kernel_gre_auto_v21 import install_kernel_gre_active_v21
from .auto_eligibility_v24 import install_auto_eligibility_v24
from .kernel_gre_health_sampling_v26 import (
    install_kernel_gre_health_sampling_v26,
)
from .throughput_auto_v27 import install_throughput_auto_v27


# ============================================================
# TWINPANEL MANAGER RUNTIME V20 + KERNEL GRE ACTIVE V21 + V24 + V26 + V27
#
# Reuse V19's self-hosted + multi-exit Backhaul hooks, replace only the
# transport selection policy with Performance Auto V20, then extend that proven
# policy with the TP27 Core-parity kernel_gre member. Manual authority and V20
# anti-flap semantics remain unchanged.
#
# V24 adds a narrow per-member Auto eligibility gate. A transport explicitly
# marked auto_eligible=false remains installed/healthy/manual-selectable but is
# excluded from Auto ranking until its path is performance-qualified.
#
# V26 fixes the GRE health-sample granularity: 20 bounded ICMP samples are used
# for the existing 5% loss limit, so one lost reply is 5% rather than 20%.
#
# V27 adds bounded internal tunnel-IP throughput qualification. Samples are
# cached/persisted and influence Auto ranking only after at least two fresh
# candidates have measurements; health, Manual authority and V20 hysteresis
# remain authoritative.
# ============================================================


def install_manager_runtime_v20() -> None:
    install_manager_runtime_v19()
    install_transport_policy_v20()
    install_kernel_gre_active_v21()
    install_auto_eligibility_v24()
    install_kernel_gre_health_sampling_v26()
    install_throughput_auto_v27()

    print(
        "TWINPANEL_MANAGER_RUNTIME_V20_ACTIVE "
        "backhaul_multi_exit=1 performance_auto=1 all_transports=1 "
        "kernel_gre_active_v21=1 auto_eligibility_v24=1 "
        "kernel_gre_health_sampling_v26=1 throughput_auto_v27=1",
        flush=True,
    )
