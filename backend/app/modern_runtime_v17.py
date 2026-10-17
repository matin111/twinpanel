from __future__ import annotations

from . import managed_ops
from . import tp2027_provision
from .routers import tunnel_managed


# ============================================================
# TWINPANEL MODERN MANAGED RUNTIME V17
#
# New managed tunnels must be modern-first:
#   * Backhaul is provisioned as the required TP2027 carrier only.
#   * KCP/ARQ/QUIC/TCP are the selectable primary tunnel transports.
#   * MTunnel/SSH TUN are not provisioned again for new managed tunnels.
#   * SSH Relay remains last-resort emergency fallback.
#
# Existing legacy rows are not deleted here. That would be disruptive and is a
# separate migration concern. This runtime only changes future create/repair
# behavior and selection order.
# ============================================================


MODERN_SELECTION_ORDER = (
    "kcp_2027",
    "arq_2027",
    "quic_2027",
    "tcp_2027",
    "backhaul",
    "ssh_relay",
)

MODERN_EXPECTED_ORDER = MODERN_SELECTION_ORDER


def apply_modern_runtime_v17() -> None:
    # TP2027 artifact provisioning order / persisted priority.
    tp2027_provision.TP2027_PRIORITY.clear()
    tp2027_provision.TP2027_PRIORITY.update(
        {
            "kcp_2027": 10,
            "arq_2027": 20,
            "quic_2027": 30,
            "tcp_2027": 40,
        }
    )

    # create-managed: provision only the required carrier before TP2027.
    # Old MTunnel/SSH TUN are no longer re-added to every new tunnel.
    tunnel_managed._TRANSPORTS = (
        (
            "backhaul",
            100,
            tunnel_managed.core.install_backhaul_transport,
        ),
    )
    tunnel_managed._SELECTION_ORDER = MODERN_SELECTION_ORDER

    # managed repair follows the same model: repair Backhaul carrier + modern
    # TP2027 transports; do not automatically recreate the old MTunnel/SSH TUN.
    managed_ops.DIRECT_BASE_ORDER = (
        "backhaul",
    )
    managed_ops.EXPECTED_ORDER = MODERN_EXPECTED_ORDER

    print(
        "TWINPANEL_MODERN_RUNTIME_V17_ACTIVE "
        "carrier=backhaul primary=kcp_2027 "
        "legacy_base_autoprovision=0",
        flush=True,
    )
