from __future__ import annotations

from .models import Node, NodeProtocolConfig, Tunnel, TunnelStatus
from .routers import tunnels
from . import vpn_access_dataplane_v46
from .l2tp_ppp_convergence_v111 import (
    apply_l2tp_ppp_convergence_v111,
)


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
#
# TWINPANEL_XRAY_PUBLIC_PROFILE_ROUTE_RESTORE_V109
# V87 originally rebuilt the service-route list from scratch and reduced Xray
# to one generic legacy V2Ray route. The customer Xray policy later filters that
# legacy row from normal admin/customer cards, so all three approved public
# profiles disappeared from the tunnel dialog and Unified L3 no longer received
# their dedicated Iran ingress routes. Keep the generic legacy route for old
# clients/rollback, then add the exact customer-policy profiles as desired-state
# routes without consulting transient protocol health.
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


def _xray_public_profile_routes_v109(
    exit_node: Node,
    exit_tunnel_ip: str,
    cfg: NodeProtocolConfig,
) -> list[dict]:
    """Restore the current customer-safe Xray routes after the V87 rebuild.

    Imports are intentionally lazy so the historical V87 module does not alter
    Xray runtime import ordering. By the time this route builder is executed,
    self_hosted_runtime has already registered TCP-TLS in PROFILE_META and
    applied the final customer policy.
    """

    from . import xray_customer_profile_policy_v30, xray_modern_runtime

    required_profiles = set(
        xray_customer_profile_policy_v30._required_profiles_v30(exit_node)
    )
    if not required_profiles:
        return []

    base_port = int(
        cfg.port
        or tunnels._SERVICE_DEFAULT_PORT["v2ray"]
    )

    output: list[dict] = []
    for profile in xray_customer_profile_policy_v30.PUBLIC_PROFILE_ORDER:
        if profile not in required_profiles:
            continue
        if profile not in xray_modern_runtime.PROFILE_META:
            # Keep legacy ingress available rather than breaking every service
            # route if a future Xray composition is only partially applied.
            continue

        output.append({
            "protocol": "v2ray",
            "profile": profile,
            "exit_node_id": int(exit_node.id),
            "public_port": xray_modern_runtime._public_port(
                int(exit_node.id),
                profile,
            ),
            "target_ip": exit_tunnel_ip,
            "target_port": xray_modern_runtime._target_port(
                base_port,
                profile,
            ),
            "transport": "tcp",
            "client_subnet": None,
        })

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

        if protocol == "v2ray":
            output.extend(
                _xray_public_profile_routes_v109(
                    exit_node,
                    exit_tunnel_ip,
                    cfg,
                )
            )

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

    # L2TP V111 refines provisioning/repair health before V87 publishes the
    # protocol as desired. It does not mutate a node on import/startup; it only
    # changes how explicit install/repair operations validate and converge the
    # managed L2TP runtime.
    apply_l2tp_ppp_convergence_v111()

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

    # V251 extends the final V87 service-route authority additively with the
    # ten modern protocols and live Iran-ingress delivery. It must execute here
    # (after V87 owns the route builder) and before Unified L3 V49 captures the
    # composite builder in self_hosted_runtime.
    from .modern_protocol_tunnel_binding_v251 import (
        apply_modern_protocol_tunnel_binding_v251,
    )

    apply_modern_protocol_tunnel_binding_v251()

    _RUNTIME_APPLIED = True

    print(
        "TWINPANEL_PROTOCOL_DATAPLANE_DESIRED_STATE_V87_ACTIVE "
        "ingress_authority=config+node_enable "
        "egress_authority=config+node_enable "
        "telemetry_status_authority=0 "
        "xray_public_profiles=restored_v109 "
        "l2tp_ppp_convergence=v111 "
        "modern_tunnel_binding=v251 "
        "protocols=cisco,openvpn,wireguard,l2tp,v2ray",
        flush=True,
    )
