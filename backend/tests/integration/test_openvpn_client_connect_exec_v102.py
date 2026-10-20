from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
RUNTIME_PATH = BACKEND / "app" / "openvpn_fork_headroom_v101.py"


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
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Production root cause V102: the generated hook itself was 0755, but
    # /usr/local/sbin was mode 0700. OpenVPN had already dropped to nobody, so
    # it could not traverse the parent directory and returned AUTH_FAILED after
    # successful TLS/certificate verification.
    for token in (
        '"/etc/openvpn/twinpanel-hooks"',
        '"/client-connect"',
        '"/usr/local/sbin/twinpanel-openvpn-client-connect"',
        "ensure_openvpn_client_connect_exec_v102",
    ):
        assert token in source, token

    ensure_source = _function_source(
        source,
        tree,
        "ensure_openvpn_client_connect_exec_v102",
    )

    for token in (
        'install -d -o root -g root -m 0755 "$HOOK_DIR"',
        'install -o root -g root -m 0755 "$HOOK_TMP" "$HOOK"',
        '$1 == "client-connect"',
        'print "client-connect " hook',
        'runuser -u nobody',
        'env common_name=tp_v102_exec_probe "$HOOK"',
        'systemctl restart "$SERVICE"',
        'config_hook',
        'exec_probe',
    ):
        assert token in ensure_source, token

    # The fix must not weaken the global /usr/local/sbin directory. It moves
    # only the managed hook to a dedicated traversable OpenVPN directory.
    assert 'chmod 755 /usr/local/sbin' not in source
    assert 'chmod 0755 /usr/local/sbin' not in source
    assert 'install -d -m 0755 /usr/local/sbin' not in source

    wrapper_source = _function_source(
        source,
        tree,
        "_provision_protocols_v101",
    )

    headroom_pos = wrapper_source.index(
        "await ensure_openvpn_fork_headroom_v101"
    )
    hook_pos = wrapper_source.index(
        "await ensure_openvpn_client_connect_exec_v102"
    )
    health_pos = wrapper_source.index(
        "provision._protocol_live_health("
    )

    assert headroom_pos < hook_pos < health_pos
    assert 'openvpn_result["client_connect_exec"] = hook_exec' in wrapper_source
    assert 'bool(getattr(p, "install_openvpn", False))' in wrapper_source
    assert "node.node_type == NodeType.EXIT" in wrapper_source

    print("OPENVPN_CLIENT_CONNECT_EXEC_V102_OK")


if __name__ == "__main__":
    main()
