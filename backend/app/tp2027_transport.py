from __future__ import annotations

import json

from .models import TunnelTransport


TP2027_TRANSPORTS = frozenset(
    {
        "quic_2027",
        "arq_2027",
        "kcp_2027",
        "tcp_2027",
    }
)


_INTERFACE_PREFIX = {
    "quic_2027": "tp27q",
    "arq_2027": "tp27a",
    "kcp_2027": "tp27k",
    "tcp_2027": "tp27t",
}


def tp2027_interface_name(
    transport: str,
    tunnel_id: int,
) -> str:

    name = str(
        transport or ""
    ).strip().lower()

    prefix = _INTERFACE_PREFIX.get(
        name
    )

    if not prefix:
        return ""

    return (
        f"{prefix}{int(tunnel_id)}"
    )[:15]


def _cidr(
    address: str,
    network: str,
) -> str:

    value = str(
        address or ""
    ).strip()

    if not value:
        return ""

    if "/" in value:
        return value

    prefix = "30"

    network = str(
        network or ""
    ).strip()

    if "/" in network:
        prefix = (
            network
            .rsplit("/", 1)[1]
            .strip()
            or "30"
        )

    return f"{value}/{prefix}"


def tp2027_desired_meta(
    db,
    tunnel,
    node_id: int,
) -> dict | None:

    transport = str(
        tunnel.active_transport
        or ""
    ).strip().lower()

    if transport not in TP2027_TRANSPORTS:
        return None

    row = (
        db.query(
            TunnelTransport
        )
        .filter(
            TunnelTransport.tunnel_id
            == int(tunnel.id),
            TunnelTransport.transport
            == transport,
        )
        .first()
    )

    if (
        not row
        or not row.enabled
        or not row.config_text
    ):
        return None

    try:
        cfg = json.loads(
            row.config_text
        )
    except Exception:
        return None

    if not isinstance(
        cfg,
        dict,
    ):
        return None

    is_iran = (
        int(node_id)
        == int(tunnel.iran_node_id)
    )

    is_exit = (
        int(node_id)
        == int(tunnel.exit_node_id)
    )

    if not (
        is_iran
        or is_exit
    ):
        return None

    interface = str(
        cfg.get("interface")
        or tp2027_interface_name(
            transport,
            int(tunnel.id),
        )
    ).strip()

    network = str(
        cfg.get("network")
        or ""
    ).strip()

    iran_ip = str(
        cfg.get("iran_ip")
        or ""
    ).strip()

    exit_ip = str(
        cfg.get("exit_ip")
        or ""
    ).strip()

    if (
        not interface
        or not iran_ip
        or not exit_ip
    ):
        return None

    iran_service = str(
        cfg.get("iran_service")
        or ""
    ).strip()

    exit_service = str(
        cfg.get("exit_service")
        or iran_service
    ).strip()

    local_ip = (
        iran_ip
        if is_iran
        else exit_ip
    )

    peer_ip = (
        exit_ip
        if is_iran
        else iran_ip
    )

    service = (
        iran_service
        if is_iran
        else exit_service
    )

    return {
        "transport": transport,
        "interface": interface,
        "network": network,
        "local_address": _cidr(
            local_ip,
            network,
        ),
        "peer_tunnel_ip": peer_ip,
        "exit_tunnel_ip": exit_ip,
        "health_interface": interface,
        "health_peer_tunnel_ip":
            peer_ip,
        "health_service": service,
    }
