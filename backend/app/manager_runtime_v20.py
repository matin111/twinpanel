from __future__ import annotations

from .manager_runtime_v19 import install_manager_runtime_v19
from .transport_policy_v20 import install_transport_policy_v20
from .kernel_gre_auto_v21 import install_kernel_gre_active_v21
from .auto_eligibility_v24 import install_auto_eligibility_v24
from .kernel_gre_health_sampling_v26 import (
    install_kernel_gre_health_sampling_v26,
)
from .throughput_auto_v27 import install_throughput_auto_v27
from .throughput_receiver_v28 import install_throughput_receiver_v28
from .throughput_meta_v29 import install_throughput_meta_v29
from .throughput_unknown_neutral_v30 import (
    install_throughput_unknown_neutral_v30,
)


# ============================================================
# TWINPANEL MANAGER RUNTIME V20 + KERNEL GRE ACTIVE V21 + V24 + V26 + V27 + V28 + V29 + V30
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
#
# V28 hardens V27's remote receiver lifecycle. Instead of a fixed 0.5 second
# sleep followed by one logfile read, it polls for the receiver's final RX_MBPS
# marker until a bounded deadline. This removes completion/FIN races without
# changing throughput caps, schedule, scoring, routes or services.
#
# V29 fills benchmark metadata for healthy legacy/self-hosted Backhaul and
# generic SSH TUN rows whose config_text is empty. It reuses TwinPanel's existing
# deterministic runtime helpers and changes no provisioning, routes, firewall,
# services, schema, benchmark caps, or scoring weights.
#
# V30 removes the fixed-20 unknown-throughput bonus exposed when a fresh sample
# expires. While throughput scoring is active, unknown candidates inherit at
# least the worst penalty among fresh measured candidates. Benchmark scheduling,
# TTL, V20 quality scoring and anti-flap remain unchanged.
# ============================================================


def install_manager_runtime_v20() -> None:
    install_manager_runtime_v19()
    install_transport_policy_v20()
    install_kernel_gre_active_v21()
    install_auto_eligibility_v24()
    install_kernel_gre_health_sampling_v26()
    install_throughput_auto_v27()
    install_throughput_receiver_v28()
    install_throughput_meta_v29()
    install_throughput_unknown_neutral_v30()

    print(
        "TWINPANEL_MANAGER_RUNTIME_V20_ACTIVE "
        "backhaul_multi_exit=1 performance_auto=1 all_transports=1 "
        "kernel_gre_active_v21=1 auto_eligibility_v24=1 "
        "kernel_gre_health_sampling_v26=1 throughput_auto_v27=1 "
        "throughput_receiver_v28=1 throughput_meta_v29=1 "
        "throughput_unknown_neutral_v30=1",
        flush=True,
    )
