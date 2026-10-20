from __future__ import annotations

from .models import Node, NodeProtocolConfig, Tunnel, TunnelStatus
from .routers import tunnels
from . import vpn_access_dataplane_v46


# ============================================================
# TWINPANEL PROTOCOL DATAPLANE DESIRED STATE V87
#
# Service telemetry is observational state. It must never be the authority for
# whether the controller publishes ingress or keeps Exit-side VPN client egress
# rules installed.
#
# A protocol is desired when:
#   * the Exit node explicitly enables it; and
#   * a NodeProtocolConfig exists for it.
#
# NodeProtocolConfig.status remains useful for UI/health reporting, but stale or
# temporarily-offline telemetry cannot tear down the data plane. This mirrors
# the proven TP27 model where configured port mappings remain installed while
# transport/service health is measured independently.
# ============================================================

_RUNTIME_APPLIED = False

_PROTOCOL_ENABLE_ATTR = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}

_ACCESS_PROTOCOLS = frozenset({
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
})


def _normalise_protocol(value) -> str:
    return str(value or "").strip().lower()


def _protocol_enabled(node: Node, protocol: str) -> bool:
    attr = _PROTOCOL_ENABLE_ATTR.get(_normalise_protocol(protocol))
    return bool(attr and getattr(node, attr, False))


def _configured_protocols(db, node_id: int) -> dict[str, NodeProtocolConfig]:
    rows = (
        db.query(NodeProtocolConfig)
        .filter(NodeProtocolConfig.node_id == int(node_id))
        .all()
    )

    output: dict[str, NodeProtocolConfig] = {}
    for row in rows:
        protocol = _normalise_protocol(row.protocol)
        if protocol:
            output[protocol] = row
    return output


def _service_routes_for_exit_v87(
    db,
    exit_node: Node,
    exit_tunnel_ip: str,
) -> list[dict]:
    """Build Iran ingress routes from desired configuration, not telemetry."""

    configs = _configured_protocols(db, int(exit_node.id))
    output: list[dict] = []

    for protocol in (
        "cisco",
        "openvpn",
        "wireguard",
        "v2ray",
    ):
        cfg = configs.get(protocol)

        if not cfg or not _protocol_enabled(exit_node, protocol):
            continue

        target_port = int(
            cfg.port
            or tunnels._SERVICE_DEFAULT_PORT[protocol]
        )

        transport = str(
            cfg.transport
            or tunnels._SERVICE_DEFAULT_TRANSPORT[protocol]
        ).strip().lower()

        if protocol == "cisco":
            # CSTP TCP + DTLS UDP share the same public ingress port.
            transport = "tcp+udp"
        elif protocol == "wireguard":
            transport = "udp"
        elif protocol == "v2ray":
            transport = "tcp"
        elif protocol == "openvpn" and transport not in {"tcp", "udp"}:
            transport = "udp"

        output.append({
            "protocol": protocol,
            "exit_node_id": int(exit_node.id),
            "public_port": tunnels._service_public_port(
                int(exit_node.id),
                protocol,
            ),
            "target_ip": exit_tunnel_ip,
            "target_port": target_port,
            "transport": transport,
            "client_subnet": tunnels._SERVICE_CLIENT_SUBNET[protocol],
        })

    return output


def _l2tp_routes_for_exit_v87(
    db,
    exit_node: Node,
    exit_tunnel_ip: str,
) -> list[dict]:
    """Keep L2TP/IPsec ingress present while L2TP remains configured."""

    configs = _configured_protocols(db, int(exit_node.id))

    if (
        not _protocol_enabled(exit_node, "l2tp")
        or "l2tp" not in configs
    ):
        return []

    output = [
        {
            "protocol": "l2tp",
            "exit_node_id": int(exit_node.id),
            "public_port": int(port),
            "target_ip": exit_tunnel_ip,
            "target_port": int(port),
            "transport": "udp",
            "client_subnet": tunnels._L2TP_CLIENT_SUBNET,
        }
        for port in tunnels._L2TP_PUBLIC_PORTS
    ]

    # IPsec ESP = IP protocol 50. Port fields are intentionally unused by the
    # Node Agent; UDP/1701 remains inside the protected L2TP/IPsec session.
    output.append({
        "protocol": "l2tp",
        "exit_node_id": int(exit_node.id),
        "public_port": None,
        "target_ip": exit_tunnel_ip,
        "target_port": None,
        "transport": "esp",
        "client_subnet": tunnels._L2TP_CLIENT_SUBNET,
    })

    return output


def _l2tp_primary_tunnel_id_v87(
    db,
    iran_node_id: int,
) -> int | None:
    """Legacy compatibility election using desired state instead of status."""

    rows = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id == int(iran_node_id),
            Tunnel.is_active.is_(True),
            Tunnel.status == TunnelStatus.ONLINE,
        )
        .order_by(
            Tunnel.priority.asc(),
            Tunnel.id.asc(),
        )
        .all()
    )

    for tunnel in rows:
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if not exit_node or not _protocol_enabled(exit_node, "l2tp"):
            continue

        configs = _configured_protocols(db, int(exit_node.id))
        if "l2tp" in configs:
            return int(tunnel.id)

    return None


def _enabled_access_protocols_v87(db, node_id: int) -> set[str]:
    """Return configured+enabled VPN pools without consulting status telemetry."""

    node = db.get(Node, int(node_id))
    if node is None:
        return set()

    configs = _configured_protocols(db, int(node_id))

    return {
        protocol
        for protocol in _ACCESS_PROTOCOLS
        if protocol in configs and _protocol_enabled(node, protocol)
    }


def apply_protocol_dataplane_desired_state_v87() -> None:
    """Install desired-state route and Exit egress policy before Unified L3."""

    global _RUNTIME_APPLIED

    if _RUNTIME_APPLIED:
        return

    # Unified L3 V49 captures these two route builders when it is applied.
    # self_hosted_runtime intentionally invokes V87 first.
    tunnels._service_routes_for_exit = _service_routes_for_exit_v87
    tunnels._l2tp_routes_for_exit = _l2tp_routes_for_exit_v87
    tunnels._l2tp_primary_tunnel_id = _l2tp_primary_tunnel_id_v87

    # V46 runs in the standalone transport manager. Its loop resolves this
    # module global at execution time, so replacing the helper here keeps its
    # dedicated NAT/FORWARD/MSS chains stable across stale health telemetry.
    vpn_access_dataplane_v46._enabled_access_protocols = (
        _enabled_access_protocols_v87
    )

    _RUNTIME_APPLIED = True

    print(
        "TWINPANEL_PROTOCOL_DATAPLANE_DESIRED_STATE_V87_ACTIVE "
        "ingress_authority=config+node_enable "
        "egress_authority=config+node_enable "
        "telemetry_status_authority=0 "
        "protocols=cisco,openvpn,wireguard,l2tp,v2ray",
        flush=True,
    )
