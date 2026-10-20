from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
RUNTIME_PATH = BACKEND / "app" / "services" / "openvpn_quota_runtime_v106.py"
SYNC_PATH = BACKEND / "app" / "services" / "quota_node_sync.py"
MAINTENANCE_PATH = BACKEND / "app" / "services" / "customer_maintenance.py"


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


def _load_parser():
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    namespace = {"csv": __import__("csv")}

    for name in ("_int_counter", "_parse_openvpn_status"):
        segment = _function_source(source, tree, name)
        exec(compile(segment, f"<{name}>", "exec"), namespace)

    return namespace["_parse_openvpn_status"]


def main() -> None:
    runtime = RUNTIME_PATH.read_text(encoding="utf-8")
    runtime_tree = ast.parse(runtime)
    sync = SYNC_PATH.read_text(encoding="utf-8")
    maintenance = MAINTENANCE_PATH.read_text(encoding="utf-8")

    parser = _load_parser()
    sample = "\n".join(
        [
            "TITLE,OpenVPN 2.6.0 x86_64-pc-linux-gnu",
            "TIME,2026-10-20 08:00:00,1792483200",
            (
                "CLIENT_LIST,mv11n5,10.253.0.21:4235,10.92.0.2,,"
                "5471307,41405170,2026-10-20 07:37:16,1792481836,"
                "UNDEF,0,0,AES-256-GCM"
            ),
            "END",
        ]
    )

    rows = parser(sample)
    assert rows == [
        {
            "identity": "mv11n5",
            "session_identity": "mv11n5:1792481836:0",
            "uplink": 5471307,
            "downlink": 41405170,
        }
    ]

    device_map = _function_source(
        runtime,
        runtime_tree,
        "_openvpn_device_map",
    )
    assert 'item.get("telemetry_identity")' in device_map
    assert 'item.get("identity")' not in device_map

    apply_source = _function_source(
        runtime,
        runtime_tree,
        "_apply_openvpn_sessions",
    )

    for token in (
        'protocol="openvpn"',
        'counter_mode="cumulative"',
        "open_session(",
        "apply_usage_event(",
        "close_session(",
        'reason="vpn_session_ended"',
    ):
        assert token in apply_source, token

    collect_source = _function_source(
        runtime,
        runtime_tree,
        "_collect_openvpn_sessions",
    )
    assert "_query_openvpn_management_remote" in collect_source
    assert "_query_openvpn_management_local" in collect_source

    reconcile_source = _function_source(
        runtime,
        runtime_tree,
        "reconcile_openvpn_quota_runtime_once",
    )
    assert "Node.enable_openvpn.is_(True)" in reconcile_source
    assert "db.commit()" in reconcile_source
    assert "db.rollback()" in reconcile_source

    # OpenVPN availability must not depend on telemetry. No HTTP work is added
    # to the client-connect hook and this reconciler never restarts OpenVPN.
    lowered = runtime.lower()
    assert "client-connect" not in lowered
    assert "systemctl restart" not in lowered
    assert "systemctl stop" not in lowered

    assert "telemetry_identity" in sync
    assert "reconcile_openvpn_quota_runtime_once" in maintenance
    assert "openvpn quota runtime reconcile failed" in maintenance

    print("OPENVPN_QUOTA_RUNTIME_V106_OK")


if __name__ == "__main__":
    main()
