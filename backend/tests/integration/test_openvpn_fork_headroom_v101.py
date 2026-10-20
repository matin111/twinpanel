from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
RUNTIME_PATH = BACKEND / "app" / "openvpn_fork_headroom_v101.py"
SELF_HOSTED_PATH = BACKEND / "app" / "self_hosted_runtime.py"


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
    self_hosted = SELF_HOSTED_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Production root cause: the vendor OpenVPN template imposed the
    # UID-global RLIMIT_NPROC=10 while OpenVPN and Xray shared UID nobody.
    # The fix must be instance-specific and must not replace TasksMax/cgroup
    # protection or change unrelated protocol identities.
    for token in (
        '"openvpn-server@twinpanel.service.d"',
        '"/10-twinpanel-fork-headroom.conf"',
        "LimitNPROC=infinity",
        "systemctl daemon-reload",
        "systemctl is-active --quiet",
        'systemctl restart "$SERVICE"',
    ):
        assert token in source, token

    assert "TasksMax=" not in source
    assert "user nobody" not in source
    assert "group nogroup" not in source

    ensure_source = _function_source(
        source,
        tree,
        "ensure_openvpn_fork_headroom_v101",
    )
    assert 'cmp -s "$TMP" "$DROPIN"' in ensure_source
    assert 'CHANGED=1' in ensure_source
    assert 'RESTARTED=1' in ensure_source
    assert 'state != "active"' in ensure_source

    wrapper_source = _function_source(
        source,
        tree,
        "_provision_protocols_v101",
    )

    # Preserve existing provisioning first, then converge only a healthy
    # selected Exit OpenVPN result. This keeps Cisco/WireGuard/L2TP/Xray
    # provisioning behavior untouched.
    original_pos = wrapper_source.index(
        "await _original_provision_protocols"
    )
    headroom_pos = wrapper_source.index(
        "await ensure_openvpn_fork_headroom_v101"
    )
    assert original_pos < headroom_pos

    for token in (
        'getattr(p, "install_openvpn", False)',
        "node.node_type == NodeType.EXIT",
        '!= "local://core"',
        'bool(openvpn_result.get("ok"))',
        'provision._protocol_live_health(',
        'provision._save_live_health(',
    ):
        assert token in wrapper_source, token

    apply_source = _function_source(
        source,
        tree,
        "apply_openvpn_fork_headroom_v101",
    )
    assert (
        "provision.provision_protocols = _provision_protocols_v101"
        in apply_source
    )

    assert (
        "from .openvpn_fork_headroom_v101 import ("
        in self_hosted
    )
    assert "apply_openvpn_fork_headroom_v101()" in self_hosted

    print("OPENVPN_FORK_HEADROOM_V101_OK")


if __name__ == "__main__":
    main()
