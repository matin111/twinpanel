from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "backend" / "app" / "unified_l3_core_v49.py"
REGISTRY = ROOT / "backend" / "app" / "unified_l3_candidate_registry_v79.py"
HOSTED = ROOT / "backend" / "app" / "self_hosted_runtime.py"


def _literal_assignment(source: str, name: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"assignment not found: {name}")


def main() -> None:
    core_source = CORE.read_text(encoding="utf-8")
    registry_source = REGISTRY.read_text(encoding="utf-8")
    hosted_source = HOSTED.read_text(encoding="utf-8")

    agent_block = _literal_assignment(core_source, "_AGENT_RECONCILE_V49")
    anchor = _literal_assignment(registry_source, "_ACTIVE_SELECTION_ANCHOR")
    replacement = _literal_assignment(registry_source, "_ACTIVE_SELECTION_REPLACEMENT")
    marker = _literal_assignment(registry_source, "AGENT_MARKER")

    # Reproduce the released rc.257 regression contract: V49 demoted a
    # controller-selected carrier whenever stale transport_candidates omitted it.
    assert anchor in agent_block
    assert "selected not in candidates" in anchor

    patched = agent_block.replace(anchor, replacement, 1)
    compile(patched, "<active-transport-authority-v258>", "exec")

    # A managed active_transport is authoritative. Candidate ordering remains
    # only the fallback for an unknown/unmanaged active value.
    assert anchor not in patched
    assert "if selected not in managed_candidates:" in patched
    assert "selected not in candidates" not in patched
    assert "for name in candidates" in patched
    assert "if name in managed_candidates" in patched
    assert "active_transport is the controller authority" in patched

    # Existing nodes must not keep an older V139/V79 Agent. V79 applies V139
    # first, then restores the newer rollout marker that is embedded in the
    # rendered V49 reconcile source.
    assert marker == "TWINPANEL_ACTIVE_TRANSPORT_AUTHORITY_V258"
    v139_at = registry_source.index("apply_service_routing_stability_v139()")
    marker_at = registry_source.index("rollout._AGENT_MARKER = AGENT_MARKER", v139_at)
    assert v139_at < marker_at
    assert "# {AGENT_MARKER}" in registry_source

    # Startup composition must still patch the candidate registry before V49
    # captures make_agent and before rollout checks the active marker.
    registry_at = hosted_source.index("apply_unified_l3_candidate_registry_v79()")
    core_at = hosted_source.index("apply_unified_l3_core_v49()")
    rollout_at = hosted_source.index("apply_unified_l3_agent_rollout_v49()")
    assert registry_at < core_at < rollout_at

    print("ACTIVE_TRANSPORT_AUTHORITY_V258=PASS")


if __name__ == "__main__":
    main()
