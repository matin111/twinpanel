from __future__ import annotations

from .backhaul_multi_exit_v16 import install_backhaul_peer_v16
from .routers import tunnels
from .self_hosted_runtime import apply_self_hosted_runtime
from .transport_policy_v16 import install_transport_policy_v16


# ============================================================
# TWINPANEL MANAGER RUNTIME V16
#
# The API process calls apply_self_hosted_runtime() from app.main, but the
# standalone transport-manager service starts app.tunnel_transport_manager_v11
# directly and therefore does not import app.main. Without applying the same
# self-hosted hooks here, autonomous managed repair would still use the legacy
# Backhaul installer and could reintroduce the shared-Iran 18080 collision.
#
# Keep API and Manager repair behavior identical by installing self-hosted
# runtime hooks before the transport policy/manager loop starts. The standalone
# manager must not manage its own systemd lifecycle while doing so.
# ============================================================


def install_manager_runtime_v16() -> None:
    # TWINPANEL_TRANSPORT_MANAGER_SELF_RESTART_GUARD_V56
    # Runtime hooks are required here, service activation is not. The API is
    # the owner of ensure_transport_manager_service_v12(). Disabling that one
    # side effect prevents a manager startup from recursively restarting its
    # own systemd unit before the V12/V46/V51 loops begin.
    apply_self_hosted_runtime(manage_transport_service=False)
    install_transport_policy_v16()

    if tunnels._install_backhaul_peer is not install_backhaul_peer_v16:
        raise RuntimeError("manager_backhaul_v16_hook_not_active")

    print(
        "TWINPANEL_MANAGER_RUNTIME_V16_ACTIVE "
        "backhaul_multi_exit=1 self_service_management=0",
        flush=True,
    )
