from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.routers.manual_authority_v193 import (
    _MANUAL_REPORT_STALE_SECONDS,
    _manual_report_health_snapshot,
    report_tunnel_peer_v193,
    router,
)


def _tunnel(active: str = "tp27_fast"):
    return SimpleNamespace(active_transport=active)


def _state(
    *,
    selected: str = "tp27_fast",
    reachable: bool = True,
    error: str | None = None,
    latency: int | None = 40,
    updated_at: datetime,
):
    return SimpleNamespace(
        selected_transport=selected,
        tunnel_reachable=reachable,
        last_error=error,
        latency_ms=latency,
        updated_at=updated_at,
    )


def _tunnel_assignments() -> list[str]:
    tree = ast.parse(inspect.getsource(report_tunnel_peer_v193))
    assignments: list[str] = []

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
            ):
                assignments.append(target.attr)

    return assignments


def test_canonical_agent_report_route_is_registered():
    paths = {route.path for route in router.routes}
    assert "/v1/tunnels/{tunnel_id}/node/{node_id}/report" in paths


def test_agent_report_never_writes_manual_selection_authority():
    assignments = _tunnel_assignments()

    forbidden = {
        "mode",
        "active_transport",
        "preferred_transport",
        "last_switch_at",
    }

    assert forbidden.isdisjoint(assignments)
    assert set(assignments) == {"status", "latency_ms"}


def test_manual_health_requires_two_fresh_healthy_active_reports():
    now = datetime.utcnow()

    result = _manual_report_health_snapshot(
        _tunnel(),
        _state(updated_at=now, latency=38),
        _state(updated_at=now - timedelta(seconds=10), latency=41),
        now,
    )

    assert result == {
        "healthy": True,
        "latency_ms": 41,
        "error": None,
    }


def test_manual_health_fails_closed_and_preserves_real_peer_error():
    now = datetime.utcnow()
    real_error = "unified_l3_peer_unreachable:tp276:10.253.0.26"

    result = _manual_report_health_snapshot(
        _tunnel(),
        _state(
            updated_at=now,
            reachable=False,
            error=real_error,
            latency=None,
        ),
        _state(updated_at=now, latency=38),
        now,
    )

    assert result["healthy"] is False
    assert result["latency_ms"] is None
    assert real_error in str(result["error"])
    assert "manual_local_tunnel_unreachable" in str(result["error"])


def test_manual_health_fails_closed_on_transport_mismatch():
    now = datetime.utcnow()

    result = _manual_report_health_snapshot(
        _tunnel("tp27_fast"),
        _state(updated_at=now, selected="tp27_fast"),
        _state(updated_at=now, selected="kernel_vxlan"),
        now,
    )

    assert result["healthy"] is False
    assert result["latency_ms"] is None
    assert (
        "manual_peer_transport_mismatch:kernel_vxlan->tp27_fast"
        in str(result["error"])
    )


def test_manual_health_fails_closed_on_stale_peer_report():
    now = datetime.utcnow()
    stale_age = _MANUAL_REPORT_STALE_SECONDS + 1

    result = _manual_report_health_snapshot(
        _tunnel(),
        _state(updated_at=now),
        _state(updated_at=now - timedelta(seconds=stale_age)),
        now,
    )

    assert result["healthy"] is False
    assert result["latency_ms"] is None
    assert "manual_peer_report_stale" in str(result["error"])


def test_auto_mode_no_longer_mirrors_stale_aggregate_health_to_member():
    source = inspect.getsource(report_tunnel_peer_v193)

    assert 'if mode == "manual":' in source
    assert "member.status = _status(tunnel.status)" not in source
    assert "member.latency_ms = tunnel.latency_ms" not in source
    assert 'member.status = "online" if healthy else "offline"' in source
    assert "if healthy:" in source
    assert "member.last_healthy_at = now" in source


def test_agent_report_keeps_peer_telemetry_updates():
    source = inspect.getsource(report_tunnel_peer_v193)

    expected_fragments = (
        "state.selected_transport = payload.selected_transport",
        "state.endpoint_reachable = payload.endpoint_reachable",
        "state.tunnel_reachable = payload.tunnel_reachable",
        "state.latency_ms = payload.latency_ms",
        "state.last_error = payload.last_error",
    )

    for fragment in expected_fragments:
        assert fragment in source


def test_mtunnel_controller_authority_contract_is_preserved():
    source = inspect.getsource(report_tunnel_peer_v193)

    assert 'if _effective_transport(tunnel) == "mtunnel":' in source
    assert '"reason": "transport_manager_authoritative"' in source
