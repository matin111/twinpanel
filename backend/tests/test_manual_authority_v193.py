from __future__ import annotations

import ast
import inspect

from app.routers.manual_authority_v193 import (
    report_tunnel_peer_v193,
    router,
    should_preserve_manual_authority,
)


def test_stale_auto_object_cannot_overwrite_manual_database_authority():
    assert should_preserve_manual_authority(
        database_mode="manual",
        target_mode="auto",
        explicit_manual_to_auto=False,
    ) is True


def test_explicit_admin_manual_to_auto_transition_remains_allowed():
    assert should_preserve_manual_authority(
        database_mode="manual",
        target_mode="auto",
        explicit_manual_to_auto=True,
    ) is False


def test_manual_writer_remains_allowed_while_database_is_manual():
    assert should_preserve_manual_authority(
        database_mode="manual",
        target_mode="manual",
        explicit_manual_to_auto=False,
    ) is False


def test_auto_database_row_is_not_guarded():
    assert should_preserve_manual_authority(
        database_mode="auto",
        target_mode="auto",
        explicit_manual_to_auto=False,
    ) is False


def test_canonical_agent_report_route_is_registered():
    paths = {
        route.path
        for route in router.routes
    }
    assert "/v1/tunnels/{tunnel_id}/node/{node_id}/report" in paths


def test_agent_report_is_telemetry_only_for_aggregate_authority():
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
