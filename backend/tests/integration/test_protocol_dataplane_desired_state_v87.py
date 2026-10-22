from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
POLICY_PATH = BACKEND / "app" / "protocol_dataplane_desired_state_v87.py"
SELF_HOSTED_PATH = BACKEND / "app" / "self_hosted_runtime.py"
MANAGER_PATH = BACKEND / "app" / "tunnel_transport_manager_v12.py"
XRAY_POLICY_PATH = BACKEND / "app" / "xray_customer_profile_policy_v30.py"


def _function_source(source: str, tree: ast.AST, name: str) -> str:
    node = next(
        item
        for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    segment = ast.get_source_segment(source, node)
    assert segment is not None, name
    return segment


def main() -> None:
    policy = POLICY_PATH.read_text(encoding="utf-8")
    self_hosted = SELF_HOSTED_PATH.read_text(encoding="utf-8")
    manager = MANAGER_PATH.read_text(encoding="utf-8")
    xray_policy = XRAY_POLICY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(policy)

    # Desired state must be explicit at the Node level. A stale telemetry row
    # is not permission to remove ingress or VPN-client WAN egress.
    for token in (
        '"cisco": "enable_cisco"',
        '"openvpn": "enable_openvpn"',
        '"wireguard": "enable_wireguard"',
        '"l2tp": "enable_l2tp"',
        '"v2ray": "enable_v2ray"',
    ):
        assert token in policy, token

    for function_name in (
        "_service_routes_for_exit_v87",
        "_xray_public_profile_routes_v109",
        "_l2tp_routes_for_exit_v87",
        "_enabled_access_protocols_v87",
    ):
        function_source = _function_source(policy, tree, function_name)
        assert ".status" not in function_source, function_name
        assert "_status_text" not in function_source, function_name

    l2tp_primary = _function_source(
        policy,
        tree,
        "_l2tp_primary_tunnel_id_v87",
    )
    assert "cfg.status" not in l2tp_primary
    assert "NodeProtocolConfig.status" not in l2tp_primary
    assert "Tunnel.status == TunnelStatus.ONLINE" in l2tp_primary

    # Preserve the existing protocol-specific ingress behavior, including the
    # historical generic V2Ray route used by old links/rollback.
    service_routes = _function_source(
        policy,
        tree,
        "_service_routes_for_exit_v87",
    )
    for token in (
        '"cisco"',
        '"openvpn"',
        '"wireguard"',
        '"v2ray"',
        'transport = "tcp+udp"',
        'transport = "udp"',
        'transport = "tcp"',
        "_service_public_port",
        "_SERVICE_CLIENT_SUBNET",
        "_xray_public_profile_routes_v109",
        "output.extend",
    ):
        assert token in service_routes, token

    # Root-cause regression: V87 must not collapse Xray to only the generic
    # legacy route. Reuse the final customer policy as the single source of
    # truth and materialize its three approved public profiles with their
    # dedicated Iran public ports and Exit target ports.
    xray_routes = _function_source(
        policy,
        tree,
        "_xray_public_profile_routes_v109",
    )
    for token in (
        "TWINPANEL_XRAY_PUBLIC_PROFILE_ROUTE_RESTORE_V109",
        "xray_customer_profile_policy_v30._required_profiles_v30",
        "xray_customer_profile_policy_v30.PUBLIC_PROFILE_ORDER",
        "xray_modern_runtime.PROFILE_META",
        "xray_modern_runtime._public_port",
        "xray_modern_runtime._target_port",
        '"protocol": "v2ray"',
        '"profile": profile',
        '"transport": "tcp"',
        '"client_subnet": None',
    ):
        assert token in policy or token in xray_routes, token

    for token in (
        '"websocket_tls"',
        '"httpupgrade_tls"',
        "PROFILE_TCP_TLS",
    ):
        assert token in xray_policy, token

    assert "HIDDEN_ROUTED_PROFILES" in xray_policy
    assert '"legacy"' in xray_policy
    assert "if profile not in ADMIN_ROUTE_PROFILE_IDS" in xray_policy

    l2tp_routes = _function_source(
        policy,
        tree,
        "_l2tp_routes_for_exit_v87",
    )
    for token in (
        "_L2TP_PUBLIC_PORTS",
        '"transport": "udp"',
        '"transport": "esp"',
        "_L2TP_CLIENT_SUBNET",
    ):
        assert token in l2tp_routes, token

    apply_source = _function_source(
        policy,
        tree,
        "apply_protocol_dataplane_desired_state_v87",
    )
    for token in (
        "tunnels._service_routes_for_exit = _service_routes_for_exit_v87",
        "tunnels._l2tp_routes_for_exit = _l2tp_routes_for_exit_v87",
        "tunnels._l2tp_primary_tunnel_id = _l2tp_primary_tunnel_id_v87",
        "vpn_access_dataplane_v46._enabled_access_protocols",
    ):
        assert token in apply_source, token

    # V49 captures the route builders when apply_unified_l3_core_v49() runs,
    # so V87 (including the V109 Xray refinement) must be activated before that
    # capture in both API and manager processes through apply_self_hosted_runtime().
    v87_pos = self_hosted.index("apply_protocol_dataplane_desired_state_v87()")
    v49_pos = self_hosted.index("apply_unified_l3_core_v49()")
    assert v87_pos < v49_pos

    # The single standalone manager remains the V46 network writer.
    assert "vpn_access_dataplane_v46" in manager
    assert "vpn_access_dataplane_loop()" in manager
    assert "twinpanel-vpn-access-dataplane-v46" in manager

    print("PROTOCOL_DATAPLANE_DESIRED_STATE_V87_XRAY_V109_OK")


if __name__ == "__main__":
    main()
