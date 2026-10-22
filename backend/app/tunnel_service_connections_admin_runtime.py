from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_admin
from .models import Node, NodeProtocolConfig, Tunnel, TunnelTransport
from .routers import provision, tunnels
from .xray_modern_admin import _status_remote as _current_xray_status_remote


_runtime_applied = False

_XRAY_PROFILE_TITLES = {
    "legacy": "V2Ray / Xray",
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

_TP2027 = {
    "tcp_2027",
    "arq_2027",
    "kcp_2027",
    "quic_2027",
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


def _public_host(node: Node) -> str:
    """Return the authoritative public ingress identity for the Iran hub."""
    domain = str(getattr(node, "public_domain", None) or "").strip()
    if domain:
        return domain
    return str(node.public_ip or "").strip()


def _connection_health(
    *,
    protocol: str,
    profile: str,
    config_online: bool,
    xray_health: dict[str, Any] | None,
) -> tuple[bool | None, bool, str | None]:
    if protocol != "v2ray":
        return config_online, True, None if config_online else "protocol_not_online"

    if not xray_health:
        return None, True, "xray_health_not_probed"

    listeners = xray_health.get("listeners")
    if not isinstance(listeners, dict):
        listeners = {}

    if profile in {"websocket_tls", "httpupgrade_tls"}:
        if not bool(xray_health.get("tls_enabled")):
            return False, False, "tls_domain_unavailable"

    if profile not in listeners:
        return None, True, "listener_health_unknown"

    listener_ok = bool(listeners.get(profile))
    return listener_ok, True, None if listener_ok else "listener_not_running"


def _capabilities(
    db: Session,
    tunnel_id: int,
    connections: list[dict[str, Any]],
) -> dict[str, bool]:
    has_tp2027 = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport.in_(tuple(_TP2027)),
            TunnelTransport.enabled.is_(True),
        )
        .first()
        is not None
    )
    has_xray = any(
        str(item.get("protocol") or "").strip().lower() == "v2ray"
        for item in connections
    )
    return {
        "repair_real_egress": has_tp2027,
        "xray_reconcile": has_xray,
    }


async def _current_xray_health(conn, base_port: int) -> dict[str, Any]:
    """Normalize the current Xray runtime health to the admin route contract.

    The service-connections inventory probes the base legacy VLESS listener
    explicitly because the customer-safe Xray profile status intentionally
    reports only public TLS profiles.
    """
    runtime = await _current_xray_status_remote(conn, int(base_port))
    profiles = runtime.get("profiles")
    listeners = dict(profiles) if isinstance(profiles, dict) else {}
    listeners["legacy"] = bool(
        await provision.listener(conn, int(base_port), "tcp")
    )

    service_active = bool(runtime.get("service_active"))
    return {
        "ok": bool(service_active and any(bool(value) for value in listeners.values())),
        "service_active": service_active,
        "tls_enabled": bool(runtime.get("tls_enabled")),
        "tls_domain_configured": bool(str(runtime.get("tls_domain") or "").strip()),
        "listeners": listeners,
    }


async def tunnel_service_connections_admin(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """Safe admin inventory of Desired Service Routes for a logical tunnel.

    Route metadata comes from the backend service-routing desired state. No
    UUID, REALITY key, short ID, path, password or other customer credential is
    returned. The UI must render these fields directly and must not derive
    public or target ports on its own.
    """
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    iran_node = db.get(Node, int(tunnel.iran_node_id))
    if iran_node is None:
        raise HTTPException(status_code=409, detail="نود ایران تونل پیدا نشد")

    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if exit_node is None:
        raise HTTPException(status_code=409, detail="نود خروجی تونل پیدا نشد")

    _, _, exit_address = tunnels._tunnel_addresses(int(tunnel.id))
    logical_exit_ip = str(exit_address).split("/", 1)[0]

    routes = list(
        tunnels._service_routes_for_exit(
            db,
            exit_node,
            logical_exit_ip,
        )
    )

    try:
        routes.extend(
            tunnels._l2tp_routes_for_exit(
                db,
                exit_node,
                logical_exit_ip,
            )
        )
    except Exception:
        # Older installations without the L2TP compatibility layer must still
        # be able to inspect all other routed services.
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
                xray_health = await _current_xray_health(conn, base_port)
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
    public_host = _public_host(iran_node)

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
                "public_host": public_host,
                "public_port": raw.get("public_port"),
                "target_ip": raw.get("target_ip"),
                "target_port": raw.get("target_port"),
                "transport": str(raw.get("transport") or "").strip().lower(),
                "route_source": "desired_service_route",
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
        "iran_node": str(iran_node.name),
        "public_host": public_host,
        "exit_node_id": int(tunnel.exit_node_id),
        "exit_node": str(exit_node.name),
        "tunnel_status": status,
        "tunnel_enabled": bool(tunnel.is_active),
        "mode": str(tunnel.mode or "manual"),
        "active_transport": str(tunnel.active_transport or tunnel.transport or ""),
        "preferred_transport": str(tunnel.preferred_transport or ""),
        "route_active": bool(tunnel.is_active and status == "online"),
        "connections": connections,
        "capabilities": _capabilities(db, int(tunnel.id), connections),
        "xray_health": {
            "ok": bool(xray_health.get("ok")) if xray_health else None,
            "service_active": (
                bool(xray_health.get("service_active")) if xray_health else None
            ),
            "tls_enabled": (
                bool(xray_health.get("tls_enabled")) if xray_health else None
            ),
            "tls_domain_configured": (
                bool(xray_health.get("tls_domain_configured"))
                if xray_health
                else None
            ),
            "error": xray_probe_error,
        },
    }


def apply_tunnel_service_connections_admin_runtime() -> None:
    global _runtime_applied
    if _runtime_applied:
        return

    path = "/{tunnel_id}/service-connections"
    for route in tunnels.router.routes:
        if getattr(route, "path", None) == path:
            raise RuntimeError("Tunnel service-connections route already registered")

    tunnels.router.add_api_route(
        path,
        tunnel_service_connections_admin,
        methods=["GET"],
        dependencies=[Depends(require_admin)],
        summary="Tunnel service connections",
    )

    _runtime_applied = True
    print(
        "TWINPANEL_TUNNEL_SERVICE_CONNECTIONS_ADMIN_RUNTIME_V28_ACTIVE "
        "safe_routes=1 route_native=1 capabilities=1 secrets_exposed=0",
        flush=True,
    )
