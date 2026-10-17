from __future__ import annotations

from pathlib import Path

from .backhaul_multi_exit_v16 import install_backhaul_peer_v16
from .candidate_lifecycle_v21 import cleanup_tunnel_runtime_v21
from .config import settings
from .database import SessionLocal
from .managed_relay_recovery_v20 import apply_managed_relay_recovery_v20
from .modern_runtime_v18 import apply_modern_runtime_v18
from .public_direct_tuning_v19 import apply_public_direct_tuning_v19
from .services.public_urls import api_base_url
from .routers import nodes, provision, tunnels
from .ssh_tunnel_self_hosted_v3 import provision_ssh_tunnel_self_hosted_v3
from . import xray_modern_runtime
from .xray_modern_repair_runtime import (
    apply_xray_modern_repair_runtime,
)


_original_install_or_upgrade_agent = provision._install_or_upgrade_agent


def _resolved_public_api_base() -> str:
    db = SessionLocal()

    try:
        value = str(
            api_base_url(db)
            or ""
        ).strip().rstrip("/")
    finally:
        db.close()

    if value:
        return value

    value = str(
        settings.public_api_fallback
        or ""
    ).strip().rstrip("/")

    if value:
        return value

    raise RuntimeError(
        "PUBLIC_API_FALLBACK is not configured "
        "and no active API domain exists"
    )


async def _self_hosted_install_or_upgrade_agent(
    conn,
    node_id: int,
    api_base: str,
):
    """
    Self-hosted TwinPanel always renders Node Agent
    with this installation's configured API endpoint.

    Domain/API address is resolved centrally from:
      1. active API domain
      2. PUBLIC_API_FALLBACK

    Caller-supplied legacy controller URLs are ignored.
    """

    requested = _resolved_public_api_base()

    return await _original_install_or_upgrade_agent(
        conn,
        node_id,
        requested,
    )


def apply_self_hosted_runtime() -> None:
    # ------------------------------------------------------------
    # Node Agent
    # ------------------------------------------------------------

    tunnels._install_or_upgrade_agent = (
        _self_hosted_install_or_upgrade_agent
    )

    # ------------------------------------------------------------
    # Logical tunnel lifecycle V21
    #
    # Modern candidate runtimes are now first-class members of one logical
    # tunnel. Remove their exact owned services/interfaces/rules before the
    # logical tunnel row is deleted so no GRE/GOST/AWG/Netrix orphan remains.
    # ------------------------------------------------------------

    tunnels.cleanup_tunnel_runtime = (
        cleanup_tunnel_runtime_v21
    )

    # ------------------------------------------------------------
    # Backhaul V16
    #
    # Keep the collision-free Backhaul installer available for
    # explicit legacy/manual use.
    # ------------------------------------------------------------

    tunnels._install_backhaul_peer = (
        install_backhaul_peer_v16
    )

    # ------------------------------------------------------------
    # Modern TP2027 V18
    #
    # KCP / ARQ / QUIC / TCP have independent public underlays.
    # One Iran node can therefore fan out to multiple Exit nodes.
    # ------------------------------------------------------------

    apply_modern_runtime_v18()

    # ------------------------------------------------------------
    # Public-direct stability V19
    #
    # TCP and QUIC use the production-proven stable single-lane
    # profile. KCP and ARQ behavior remains unchanged.
    # ------------------------------------------------------------

    apply_public_direct_tuning_v19()

    # ------------------------------------------------------------
    # Managed Relay Recovery V20
    #
    # Managed repair understands that V18 modern transports are
    # public-direct and independent from Backhaul.
    #
    # SSH Relay V2 / split-hop is used only after every direct
    # data-plane candidate remains unavailable.
    # ------------------------------------------------------------

    apply_managed_relay_recovery_v20()

    # ------------------------------------------------------------
    # Xray Modern Runtime V2 + collision-free service port plan.
    #
    # Existing service ranges each reserve a full 1000-port block:
    #   Cisco      20001..20999
    #   OpenVPN    21001..21999
    #   WireGuard  22001..22999
    #   Xray old   23001..23999
    #
    # Keep every modern Xray profile in its own full block as well;
    # using 23100/23200-style bases would collide as Exit IDs grow.
    # ------------------------------------------------------------

    xray_modern_runtime.PROFILE_META[
        xray_modern_runtime.PROFILE_XHTTP
    ]["public_base"] = 24000

    xray_modern_runtime.PROFILE_META[
        xray_modern_runtime.PROFILE_GRPC
    ]["public_base"] = 25000

    xray_modern_runtime.PROFILE_META[
        xray_modern_runtime.PROFILE_WS
    ]["public_base"] = 26000

    xray_modern_runtime.PROFILE_META[
        xray_modern_runtime.PROFILE_HTTPUPGRADE
    ]["public_base"] = 27000

    xray_modern_runtime.apply_xray_modern_runtime()

    # ------------------------------------------------------------
    # Xray Modern Repair Runtime V1
    #
    # Legacy managed Xray nodes already own their base TCP port. If
    # modern listeners are missing, generic repair used to fail its
    # port preflight before the modern reconciler could run. Reconcile
    # those existing Xray listeners first, then let the normal repair
    # flow verify and persist protocol status.
    # ------------------------------------------------------------

    apply_xray_modern_repair_runtime()

    # ------------------------------------------------------------
    # SSH TUN
    #
    # Keep the controller-owned self-hosted V3 implementation.
    # ------------------------------------------------------------

    tunnels.provision_ssh_tunnel = (
        provision_ssh_tunnel_self_hosted_v3
    )

    # ------------------------------------------------------------
    # Historical nodes.py compatibility
    # ------------------------------------------------------------

    if not hasattr(
        nodes,
        "Path",
    ):
        nodes.Path = Path
