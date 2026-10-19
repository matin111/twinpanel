from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "node_bootstrap_control_v66.py"
ROUTERS_INIT = ROOT / "app" / "routers" / "__init__.py"


def function_source(tree: ast.AST, source: str, name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            text = ast.get_source_segment(source, node)
            if text:
                return text
    raise AssertionError(f"function not found: {name}")


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    connect = function_source(tree, source, "_connect_via_authenticated_iran")
    bootstrap = function_source(tree, source, "ssh_connect_saved_v66")
    cleanup = function_source(tree, source, "_close_parent_when_child_closes")

    assert "tunnel=iran_conn" in connect
    assert "proxy_command=" not in connect
    assert "_BASE_EXIT_MANAGEMENT(iran, db)" in connect
    assert "client_keys=[str(node_key)]" in connect
    assert "attempt_" in connect
    assert "iran_conn.close()" in connect

    assert "via_iran_authenticated_" in bootstrap
    assert "existing_management" in bootstrap
    assert "_BASE_EXIT_MANAGEMENT(node, db)" in bootstrap

    assert "await exit_conn.wait_closed()" in cleanup
    assert "await iran_conn.wait_closed()" in cleanup

    routers = ROUTERS_INIT.read_text(encoding="utf-8")
    assert "node_bootstrap_control_v64" in routers
    assert "node_bootstrap_control_v66" in routers
    assert routers.index("node_bootstrap_control_v64") < routers.index("node_bootstrap_control_v66")
    assert routers.index("node_bootstrap_control_v66") < routers.index("destructive_safety")

    print("NODE_BOOTSTRAP_CONTROL_V66_SMOKE=PASS")


if __name__ == "__main__":
    main()
