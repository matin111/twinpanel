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
from .transport_manager_service_v12 import ensure_transport_manager_service_v12
from . import xray_modern_runtime
from .xray_modern_repair_runtime import (
    apply_xray_modern_repair_runtime,
)
from .xray_node_domain_runtime import (
    apply_xray_node_domain_runtime,
)
from .xray_public_delivery_runtime import (
    apply_xray_public_delivery_runtime,
)
from .xray_profile_reconcile_v36 import (
    apply_xray_profile_reconcile_v36,
)
from .xray_tcp_tls_v39 import (
    apply_xray_tcp_tls_v39,
)
from .xray_tcp_tls_compat_v44 import (
    apply_xray_tcp_tls_compat_v44,
)
from .xray_reconcile_infra_v41 import (
    apply_xray_reconcile_infra_v41,
)
from .xray_customer_profile_policy_v30 import (
    apply_xray_customer_profile_policy_v30,
)
from .tunnel_service_connections_admin_runtime import (
    apply_tunnel_service_connections_admin_runtime,
)
from .tp2027_egress_v28 import (
    apply_tp2027_egress_v28,
)
from .service_connections_jobs_v28 import (
    apply_service_connections_jobs_v28,
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
    # Smart Auto V12 production activation
    # ------------------------------------------------------------

    ensure_transport_manager_service_v12()

    # ------------------------------------------------------------
    # Node Agent
    # ------------------------------------------------------------

    tunnels._install_or_upgrade_agent = (
        _self_hosted_install_or_upgrade_agent
    )

    # ------------------------------------------------------------
    # Logical tunnel lifecycle V21
    # ------------------------------------------------------------

    tunnels.cleanup_tunnel_runtime = (
        cleanup_tunnel_runtime_v21
    )

    # ------------------------------------------------------------
    # Backhaul V16
    # ------------------------------------------------------------

    tunnels._install_backhaul_peer = (
        install_backhaul_peer_v16
    )

    # ------------------------------------------------------------
    # Modern TP2027 V18
    # ------------------------------------------------------------

    apply_modern_runtime_v18()

    # ------------------------------------------------------------
    # Public-direct stability V19
    # ------------------------------------------------------------

    apply_public_direct_tuning_v19()

    # ------------------------------------------------------------
    # Managed Relay Recovery V20
    # ------------------------------------------------------------

    apply_managed_relay_recovery_v20()

    # ------------------------------------------------------------
    # Xray Modern Runtime V2 + collision-free service port plan.
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
    # Xray production composition
    #
    # Keep the old Reality listeners internally for diagnostics/rollback, but
    # restore the validated customer policy:
    #   WebSocket TLS -> HTTPUpgrade TLS -> VLESS TCP TLS
    #
    # The dedicated Xray domain remains independent from the general Node
    # domain. V44 keeps TCP TLS config validation compatible with Xray 26.3.x.
    # ------------------------------------------------------------

    apply_xray_modern_repair_runtime()
    apply_xray_node_domain_runtime()
    apply_xray_public_delivery_runtime()
    apply_xray_profile_reconcile_v36()
    apply_xray_tcp_tls_v39()
    apply_xray_tcp_tls_compat_v44()
    apply_xray_reconcile_infra_v41()
    apply_xray_customer_profile_policy_v30()

    # ------------------------------------------------------------
    # Service Connections V30
    #
    # Register the route only after the final Xray policy has wrapped the
    # endpoint. This prevents Legacy/XHTTP/gRPC from leaking back into the
    # normal customer/admin service cards while preserving them internally.
    # ------------------------------------------------------------

    apply_tunnel_service_connections_admin_runtime()
    apply_tp2027_egress_v28()
    apply_service_connections_jobs_v28()

    # ------------------------------------------------------------
    # SSH TUN
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
