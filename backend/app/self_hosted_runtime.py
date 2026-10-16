from __future__ import annotations

import sys
from pathlib import Path

from .backhaul_multi_exit_v16 import install_backhaul_peer_v16
from .config import settings
from .database import SessionLocal
from .services.public_urls import api_base_url
from .routers import modern_transports, nodes, provision, tunnels
from .ssh_tunnel_self_hosted_v3 import provision_ssh_tunnel_self_hosted_v3
from . import xray_modern_admin, xray_modern_runtime
from .xray_modern_repair_runtime import (
    apply_xray_modern_repair_runtime,
)
from .xray_modern_temp_config_runtime import (
    apply_xray_modern_temp_config_runtime,
)
from .xray_node_domain_runtime import (
    apply_xray_node_domain_runtime,
)
from .xray_profile_reconcile_v36 import (
    apply_xray_profile_reconcile_v36,
)
from .xray_public_delivery_runtime import (
    apply_xray_public_delivery_runtime,
)
from .tunnel_service_connections_admin_runtime import (
    apply_tunnel_service_connections_admin_runtime,
)
from .service_speed_recovery_v36 import (
    apply_service_speed_recovery_v36,
)
from .tp2027_egress_v37 import (
    apply_tp2027_egress_v37,
)
from .manual_transport_report_guard_v22 import (
    apply_manual_transport_report_guard_v22,
)
from .manual_transport_api_v23 import (
    apply_manual_transport_api_v23,
)


_original_install_or_upgrade_agent = provision._install_or_upgrade_agent


def _resolved_public_api_base() -> str:
    db = SessionLocal()
    try:
        value = str(api_base_url(db) or "").strip().rstrip("/")
    finally:
        db.close()

    if value:
        return value

    value = str(settings.public_api_fallback or "").strip().rstrip("/")
    if value:
        return value

    raise RuntimeError(
        "PUBLIC_API_FALLBACK is not configured and no active API domain exists"
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


def _route_key(route) -> tuple[str, tuple[str, ...]]:
    path = str(getattr(route, "path", "") or "")
    methods = tuple(
        sorted(
            str(method)
            for method in (getattr(route, "methods", None) or ())
        )
    )
    return path, methods


def _register_xray_routes_for_drifted_main() -> int:
    """
    Production compatibility for installations whose local ``app/main.py``
    intentionally removed the direct Xray router imports/includes while keeping
    ``modern_transports_router`` registered.

    On the canonical source tree ``app.main`` already imports both Xray routers,
    so this shim is a no-op and cannot create duplicate canonical routes.

    On a drifted production ``main.py`` where those symbols are absent, append
    the already-built APIRoute objects to the modern-transports router. Their
    paths are already absolute (``/v1/xray-modern...``), so when the target
    router is later included by FastAPI the public URLs remain unchanged.
    """
    main_module = sys.modules.get("app.main")

    canonical_registration_present = bool(
        main_module is not None
        and hasattr(main_module, "xray_modern_router")
        and hasattr(main_module, "xray_modern_admin_router")
    )

    if canonical_registration_present:
        return 0

    target_router = modern_transports.router
    existing = {
        _route_key(route)
        for route in target_router.routes
    }

    added = 0

    for source_router in (
        xray_modern_runtime.router,
        xray_modern_admin.router,
    ):
        for route in source_router.routes:
            key = _route_key(route)

            if not key[0].startswith("/v1/xray-modern"):
                continue

            if key in existing:
                continue

            target_router.routes.append(route)
            existing.add(key)
            added += 1

    print(
        "TWINPANEL_XRAY_ROUTER_COMPAT_V1_ACTIVE "
        f"canonical_main_registration=0 routes_added={added}",
        flush=True,
    )

    return added


def apply_self_hosted_runtime() -> None:
    apply_manual_transport_report_guard_v22()
    apply_manual_transport_api_v23()
    tunnels._install_or_upgrade_agent = _self_hosted_install_or_upgrade_agent
    tunnels._install_backhaul_peer = install_backhaul_peer_v16

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

    apply_xray_modern_temp_config_runtime()
    xray_modern_runtime.apply_xray_modern_runtime()
    apply_xray_modern_repair_runtime()
    apply_xray_node_domain_runtime()
    apply_xray_profile_reconcile_v36()
    apply_xray_public_delivery_runtime()
    _register_xray_routes_for_drifted_main()
    apply_tunnel_service_connections_admin_runtime()
    apply_tp2027_egress_v37()
    apply_service_speed_recovery_v36()

    tunnels.provision_ssh_tunnel = provision_ssh_tunnel_self_hosted_v3

    if not hasattr(nodes, "Path"):
        nodes.Path = Path
