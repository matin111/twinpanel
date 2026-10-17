from __future__ import annotations

import json

from .models import TunnelTransport


# ============================================================
# TWINPANEL ROUTABLE TRANSPORT METADATA V2
#
# TP2027 overlays and the new Iran-path canaries are all controller-owned
# L3 interfaces. Keeping them in one route-metadata surface lets the existing
# Node Agent consume the winning transport without teaching the Agent about
# every installer separately.
#
# Candidate runtime is deterministic and tunnel-id namespaced, so one Iran
# node can safely fan out to many Exit nodes without interface/address/service
# collisions.
# ============================================================

TP2027_BASE_TRANSPORTS = frozenset(
    {
        "quic_2027",
        "arq_2027",
        "kcp_2027",
        "tcp_2027",
    }
)

CANDIDATE_L3_TRANSPORTS = frozenset(
    {
        "kernel_gre",
        "gost_tun",
        "amneziawg",
        "netrix",
    }
)

# Backward-compatible public name used by routers/tunnels.py. Extending this
# set makes the existing desired-state route logic understand every qualified
# controller-owned L3 candidate.
TP2027_TRANSPORTS = frozenset(
    TP2027_BASE_TRANSPORTS
    | CANDIDATE_L3_TRANSPORTS
)


_INTERFACE_PREFIX = {
    "quic_2027": "tp27q",
    "arq_2027": "tp27a",
    "kcp_2027": "tp27k",
    "tcp_2027": "tp27t",
    "kernel_gre": "tpgr",
    "gost_tun": "tpgs",
    "amneziawg": "tpaw",
    "netrix": "tpnx",
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


def _candidate_desired_meta(
    db,
    tunnel,
    node_id: int,
    transport: str,
) -> dict | None:
    """Return desired-state metadata for a qualified modern L3 candidate.

    The installer runtime is deterministic; do not depend on legacy
    config_text formatting (older canary rows used Python repr instead of JSON).
    """

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel.id),
            TunnelTransport.transport == transport,
        )
        .first()
    )

    if (
        row is None
        or not bool(row.enabled)
    ):
        return None

    try:
        from .transport_candidates.common import runtime

        cfg = runtime(
            transport,
            int(tunnel.id),
        )
    except Exception:
        return None

    is_iran = (
        int(node_id)
        == int(tunnel.iran_node_id)
    )

    is_exit = (
        int(node_id)
        == int(tunnel.exit_node_id)
    )

    if not (is_iran or is_exit):
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

    if not interface or not iran_ip or not exit_ip:
        return None

    local_ip = iran_ip if is_iran else exit_ip
    peer_ip = exit_ip if is_iran else iran_ip

    service = str(
        cfg.get(
            "iran_service"
            if is_iran
            else "exit_service"
        )
        or ""
    ).strip()

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
        "health_peer_tunnel_ip": peer_ip,
        "health_service": service,
    }


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

    if transport in CANDIDATE_L3_TRANSPORTS:
        return _candidate_desired_meta(
            db,
            tunnel,
            node_id,
            transport,
        )

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
