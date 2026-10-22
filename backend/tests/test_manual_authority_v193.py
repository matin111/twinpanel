from __future__ import annotations

import ast
import inspect

from app.routers.manual_authority_v193 import (
    report_tunnel_peer_v193,
    router,
)


def test_canonical_agent_report_route_is_registered():
    paths = {
        route.path
        for route in router.routes
    }
    assert "/v1/tunnels/{tunnel_id}/node/{node_id}/report" in paths


def test_agent_report_never_writes_aggregate_tunnel_authority():
    tree = ast.parse(inspect.getsource(report_tunnel_peer_v193))

    forbidden = {
        "mode",
        "active_transport",
        "preferred_transport",
        "status",
        "latency_ms",
        "last_switch_at",
    }

    aggregate_assignments: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            continue

        targets = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        else:
            targets.append(node.target)

        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "tunnel"
                and target.attr in forbidden
            ):
                aggregate_assignments.append(target.attr)

    assert aggregate_assignments == []


def test_agent_report_keeps_legacy_peer_and_member_telemetry_updates():
    source = inspect.getsource(report_tunnel_peer_v193)

    expected_fragments = (
        "state.selected_transport = payload.selected_transport",
        "state.endpoint_reachable = payload.endpoint_reachable",
        "state.tunnel_reachable = payload.tunnel_reachable",
        "state.latency_ms = payload.latency_ms",
        "state.last_error = payload.last_error",
        "member.status = _status(tunnel.status)",
        "member.latency_ms = tunnel.latency_ms",
        "member.last_error =",
    )

    for fragment in expected_fragments:
        assert fragment in source


def test_mtunnel_controller_authority_contract_is_preserved():
    source = inspect.getsource(report_tunnel_peer_v193)

    assert 'if _effective_transport(tunnel) == "mtunnel":' in source
    assert '"reason": "transport_manager_authoritative"' in source
