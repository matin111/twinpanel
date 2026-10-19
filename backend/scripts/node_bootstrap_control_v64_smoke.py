from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "node_bootstrap_control_v64.py"
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

    proxy = function_source(tree, source, "_public_jump_proxy_command")
    connect = function_source(tree, source, "_connect_via_iran_public")
    relay_unit = function_source(tree, source, "_exit_relay_unit")
    relay_setup = function_source(tree, source, "_ensure_exit_outbound_control_relay")
    installer = function_source(tree, source, "_install_or_upgrade_agent_v64")

    assert '"-W"' in proxy, "public jump must use OpenSSH native stdio forwarding"
    assert '"nc"' not in proxy, "public jump must not depend on remote nc"
    assert "_PUBLIC_JUMP_ATTEMPTS = 2" in source
    assert "attempt_" in connect

    assert "-L 127.0.0.1:" in relay_unit, "Agent relay must originate from Exit"
    assert "-R 127.0.0.1:" not in relay_unit, "V64 must not depend on inbound Exit reverse forwarding"
    assert "Exit Outbound Control Relay" in relay_unit

    assert "exit_control_relay_public_key_missing" in relay_setup
    assert "outbound_control_relay_health_failed" in relay_setup
    assert "exit_outbound_via_iran_ssh" in relay_setup
    assert 'command="/usr/bin/true"' in source
    assert "permitopen=" in source

    assert "standby_relay_error" in installer, "direct API must remain a safe fallback"
    assert "_BASE_INSTALL_AGENT" in installer

    routers = ROUTERS_INIT.read_text(encoding="utf-8")
    assert "node_bootstrap_control_v64" in routers
    assert "node_bootstrap_control_v63 as _node_bootstrap_control_v63" not in routers

    print("NODE_BOOTSTRAP_CONTROL_V64_SMOKE=PASS")


if __name__ == "__main__":
    main()
