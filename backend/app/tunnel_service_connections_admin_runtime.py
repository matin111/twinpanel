from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_admin
from .models import Node, NodeProtocolConfig, Tunnel
from .routers import provision, tunnels
from .xray_modern_repair_runtime import _modern_health_snapshot


_runtime_applied = False

_XRAY_PROFILE_TITLES = {
    "legacy": "VLESS Legacy",
    "xhttp_reality": "XHTTP Reality",
    "grpc_reality": "gRPC Reality",
    "websocket_tls": "WebSocket TLS",
    "httpupgrade_tls": "HTTPUpgrade TLS",
}

_PROTOCOL_TITLES = {
    "cisco": "Cisco / OpenConnect",
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "l2tp": "L2TP / IPsec",
    "v2ray": "V2Ray / Xray",
}


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _profile_for_route(route: dict[str, Any]) -> str:
    protocol = str(route.get("protocol") or "").strip().lower()
    profile = str(route.get("profile") or "").strip().lower()

    if protocol == "v2ray":
        return profile or "legacy"

    return profile or protocol


def _route_title(protocol: str, profile: str) -> str:
    if protocol == "v2ray":
        return _XRAY_PROFILE_TITLES.get(profile, profile or "V2Ray / Xray")
    return _PROTOCOL_TITLES.get(protocol, protocol or "Service")


def _connection_health(
    *,
    protocol: str,
    profile: str,
    config_online: bool,
    xray_health: dict[str, Any] | None,
) -> tuple[bool | None, bool, str | None]:
    """
    Return (healthy, available, reason).

    `healthy=None` means the live listener could not be probed. This is kept
    distinct from a confirmed DOWN state so the admin UI never invents health.
    """

    if protocol != "v2ray":
        return config_online, True, None if config_online else "protocol_not_online"

    if not xray_health:
        return None, True, "xray_health_not_probed"

    listeners = xray_health.get("listeners")
    if not isinstance(listeners, dict):
        listeners = {}

    if profile in {"websocket_tls", "httpupgrade_tls"}:
        tls_enabled = bool(xray_health.get("tls_enabled"))
        if not tls_enabled:
            return False, False, "tls_domain_unavailable"

    if profile not in listeners:
        return None, True, "listener_health_unknown"

    listener_ok = bool(listeners.get(profile))
    return (
        listener_ok,
        True,
        None if listener_ok else "listener_not_running",
    )


async def tunnel_service_connections_admin(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """
    Safe admin view of customer-service routes carried by one logical tunnel.

    Physical tunnel members (MTunnel/Backhaul/SSH TUN) remain separate. This
    endpoint exposes only service routing metadata and sanitized health; it
    never returns Xray UUIDs, REALITY keys, short IDs, paths, or credentials.
    """

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if exit_node is None:
        raise HTTPException(status_code=409, detail="نود خروجی تونل پیدا نشد")

    # Service-route generation only needs the Exit-side logical address to
    # construct target metadata. The admin response deliberately does not
    # expose this internal address because physical transports can use their
    # own overlay address at runtime.
    _, _, exit_address = tunnels._tunnel_addresses(int(tunnel.id))
    logical_exit_ip = str(exit_address).split("/", 1)[0]

    routes = list(
        tunnels._service_routes_for_exit(
            db,
            exit_node,
            logical_exit_ip,
        )
    )

    # L2TP is generated separately from the generic service routes in the
    # desired-state pipeline. Include it in the admin inventory as well.
    try:
        routes.extend(
            tunnels._l2tp_routes_for_exit(
                db,
                exit_node,
                logical_exit_ip,
            )
        )
    except Exception:
        # The service inventory must stay usable even when an installation has
        # no L2TP runtime/schema compatibility. Other routes remain valid.
        pass

    configs = {
        str(item.protocol or "").strip().lower(): item
        for item in (
            db.query(NodeProtocolConfig)
            .filter(NodeProtocolConfig.node_id == exit_node.id)
            .all()
        )
    }

    xray_health: dict[str, Any] | None = None
    xray_probe_error: str | None = None

    if any(
        str(route.get("protocol") or "").strip().lower() == "v2ray"
        for route in routes
        if isinstance(route, dict)
    ):
        cfg = configs.get("v2ray")
        if cfg is not None:
            base_port = int(cfg.port or 8443)
            conn = None
            try:
                conn = await provision.ssh_connect_saved(exit_node, db)
                xray_health = await _modern_health_snapshot(conn, base_port)
            except Exception as exc:
                xray_probe_error = str(exc)[:500]
            finally:
                if conn is not None:
                    conn.close()
                    try:
                        await conn.wait_closed()
                    except Exception:
                        pass

    connections: list[dict[str, Any]] = []

    for raw in routes:
        if not isinstance(raw, dict):
            continue

        protocol = str(raw.get("protocol") or "").strip().lower()
        if not protocol:
            continue

        profile = _profile_for_route(raw)
        cfg = configs.get(protocol)
        config_online = bool(cfg and _enum_value(cfg.status) == "online")

        healthy, available, reason = _connection_health(
            protocol=protocol,
            profile=profile,
            config_online=config_online,
            xray_health=xray_health,
        )

        connections.append(
            {
                "protocol": protocol,
                "profile": profile,
                "title": _route_title(protocol, profile),
                "public_port": raw.get("public_port"),
                "target_port": raw.get("target_port"),
                "transport": str(raw.get("transport") or "").strip().lower(),
                "available": available,
                "healthy": healthy,
                "health_reason": reason,
            }
        )

    profile_order = {
        "cisco": 10,
        "openvpn": 20,
        "wireguard": 30,
        "l2tp": 40,
        "legacy": 50,
        "xhttp_reality": 51,
        "grpc_reality": 52,
        "websocket_tls": 53,
        "httpupgrade_tls": 54,
    }
    connections.sort(
        key=lambda item: (
            profile_order.get(str(item.get("profile") or ""), 999),
            int(item.get("public_port") or 0),
        )
    )

    status = _enum_value(tunnel.status)

    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "iran_node_id": int(tunnel.iran_node_id),
        "exit_node_id": int(tunnel.exit_node_id),
        "exit_node": str(exit_node.name),
        "tunnel_status": status,
        "tunnel_enabled": bool(tunnel.is_active),
        "mode": str(tunnel.mode or "manual"),
        "active_transport": str(tunnel.active_transport or tunnel.transport or ""),
        "preferred_transport": str(tunnel.preferred_transport or ""),
        "route_active": bool(tunnel.is_active and status == "online"),
        "connections": connections,
        "xray_health": {
            "ok": bool(xray_health.get("ok")) if xray_health else None,
            "service_active": (
                bool(xray_health.get("service_active"))
                if xray_health
                else None
            ),
            "tls_enabled": (
                bool(xray_health.get("tls_enabled"))
                if xray_health
                else None
            ),
            "tls_domain_configured": (
                bool(xray_health.get("tls_domain_configured"))
                if xray_health
                else None
            ),
            "error": (
                str(xray_health.get("error") or "")[:500] or None
                if xray_health
                else xray_probe_error
            ),
        },
    }


def apply_tunnel_service_connections_admin_runtime() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    path = "/{tunnel_id}/service-connections"

    # Fail closed if another implementation already owns the route. Silent
    # duplicates make OpenAPI/UI behavior dependent on registration order.
    for route in tunnels.router.routes:
        if getattr(route, "path", None) == path:
            raise RuntimeError(
                "Tunnel service-connections route already registered"
            )

    tunnels.router.add_api_route(
        path,
        tunnel_service_connections_admin,
        methods=["GET"],
        dependencies=[Depends(require_admin)],
        summary="Tunnel service connections",
    )

    _runtime_applied = True

    print(
        "TWINPANEL_TUNNEL_SERVICE_CONNECTIONS_ADMIN_RUNTIME_V1_ACTIVE "
        "safe_routes=1 xray_profile_health=1 secrets_exposed=0",
        flush=True,
    )
