from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
COMMON = ROOT / "backend/app/transport_candidates/common.py"
REGISTRY = ROOT / "backend/app/unified_l3_candidate_registry_v79.py"
ROLLOUT = ROOT / "backend/app/unified_l3_agent_rollout_v49.py"
CORE = ROOT / "backend/app/unified_l3_core_v49.py"
RUNTIME = ROOT / "backend/app/self_hosted_runtime.py"


def _compile(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    return source


def _load_loss_parser():
    tree = ast.parse(COMMON.read_text(encoding="utf-8"), filename=str(COMMON))
    selected = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name)
                and target.id == "_PACKET_LOSS_RE"
                for target in node.targets
            ):
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "parse_packet_loss_pct":
            selected.append(node)

    if len(selected) != 2:
        raise AssertionError("packet-loss parser AST contract missing")

    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"re": re}
    exec(compile(module, str(COMMON), "exec"), namespace)
    return namespace["parse_packet_loss_pct"]


def test_packet_loss_parser_and_probe_contract() -> None:
    common = _compile(COMMON)
    parser = _load_loss_parser()

    assert parser(
        "3 packets transmitted, 3 received, 0% packet loss, time 2001ms"
    ) == 0.0
    assert parser(
        "3 packets transmitted, 2 received, 33.3333% packet loss, time 2001ms"
    ) == 33.3333
    assert parser("no ping summary") is None

    assert "LC_ALL=C ping" in common
    assert '"packet_loss_pct": packet_loss' in common
    assert '"iran_packet_loss_pct"' in common
    assert '"exit_packet_loss_pct"' in common
    assert "peer_ping_loss_parse_failed" in common


def test_unified_l3_candidate_registry_contract() -> None:
    registry = _compile(REGISTRY)
    core = _compile(CORE)
    runtime = _compile(RUNTIME)

    assert "from .transport_candidates import SPECS" in registry
    assert "managed_candidates.update(" in registry
    assert 'selected == "mtunnel"' in registry
    assert "or selected in" in registry
    assert "unified_l3_carrier_probe" in core
    assert "TWINPANEL_UNIFIED_L3_CANDIDATE_REGISTRY_V79" in registry

    registry_call = runtime.index("apply_unified_l3_candidate_registry_v79()")
    core_call = runtime.index("apply_unified_l3_core_v49()")
    rollout_call = runtime.index("apply_unified_l3_agent_rollout_v49()")
    assert registry_call < core_call < rollout_call


def test_agent_rollout_marker_is_dynamic() -> None:
    rollout = _compile(ROLLOUT)

    assert "def _marker_probe_command" in rollout
    assert "shlex.quote(_AGENT_MARKER)" in rollout
    assert "_marker_probe_command()" in rollout
    assert "_marker_probe_command(verify_service=True)" in rollout
    assert 'marker={_AGENT_MARKER}' in rollout


def main() -> None:
    test_packet_loss_parser_and_probe_contract()
    test_unified_l3_candidate_registry_contract()
    test_agent_rollout_marker_is_dynamic()
    print("TUNNEL_CORE_CANDIDATE_REGISTRY_V79_OK")


if __name__ == "__main__":
    main()
