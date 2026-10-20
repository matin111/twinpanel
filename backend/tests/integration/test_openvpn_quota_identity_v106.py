from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
SYNC_PATH = BACKEND / "app" / "services" / "quota_node_sync.py"


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
    source = SYNC_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    runtime_source = _function_source(
        source,
        tree,
        "_runtime_identity",
    )

    # Production proof on Node #5 / Subscription #11:
    # credential identity was mv-11@twinpanel while OpenVPN management used
    # certificate CN mv11n5. Telemetry must use the runtime CN, not username.
    for token in (
        'protocol != "openvpn"',
        'f"mv-sub-{int(subscription_id)}"',
        'f"mv{int(subscription_id)}n{int(node_id)}"',
    ):
        assert token in runtime_source, token

    build_source = _function_source(
        source,
        tree,
        "build_node_devices",
    )

    assert "is_openvpn_central_pki_enabled(db)" in build_source
    assert '"identity": identity' in build_source
    assert '"telemetry_identity": _runtime_identity(' in build_source

    sync_source = _function_source(
        source,
        tree,
        "sync_node_config",
    )
    assert '"version": 3' in sync_source

    print("OPENVPN_QUOTA_IDENTITY_V106_OK")


if __name__ == "__main__":
    main()
