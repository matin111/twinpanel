from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPAIR = ROOT / "backend" / "app" / "tp27_self_repair_v265.py"
API = ROOT / "backend" / "app" / "tp27_repair_api_v265.py"
MANAGER = ROOT / "backend" / "app" / "tunnel_transport_manager_v12.py"
HOSTED = ROOT / "backend" / "app" / "self_hosted_runtime.py"
CLIENT = ROOT / "lib" / "tunnel-transport-api.ts"
UI = ROOT / "components" / "tunnel-transport-runtime.tsx"


def _literal_assignment(source: str, name: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = node.value
                    if value is None:
                        raise AssertionError(f"assignment has no value: {name}")
                    return ast.literal_eval(value)
    raise AssertionError(f"assignment not found: {name}")


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(source, node)
            if not segment:
                raise AssertionError(f"source segment missing: {name}")
            return segment
    raise AssertionError(f"function not found: {name}")


def main() -> None:
    repair_source = REPAIR.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")
    manager_source = MANAGER.read_text(encoding="utf-8")
    hosted_source = HOSTED.read_text(encoding="utf-8")
    client_source = CLIENT.read_text(encoding="utf-8")
    ui_source = UI.read_text(encoding="utf-8")

    # Python syntax must stay valid independently of the full application import.
    for path, source in (
        (REPAIR, repair_source),
        (API, api_source),
        (MANAGER, manager_source),
        (HOSTED, hosted_source),
    ):
        compile(source, str(path), "exec")

    # Autonomous repair is deliberately debounced and rate-limited.
    assert _literal_assignment(repair_source, "LOOP_SECONDS") == 30
    assert _literal_assignment(repair_source, "FAILURE_THRESHOLD") == 3
    assert _literal_assignment(repair_source, "REPAIR_COOLDOWN_SECONDS") == 180

    attempt_order = _function_source(repair_source, "_attempt_order")
    assert 'current == "gre-native"' in attempt_order
    assert 'return fou + [("gre-native", None)]' in attempt_order
    assert 'current == "gre-fou"' in attempt_order

    repair = _function_source(repair_source, "_repair_tp27_locked")
    assert 'if bool(before["healthy"]) and not force_rebuild' in repair
    assert "tp27_fast._install_profile" in repair
    assert 'name="tp27_fast"' in repair
    assert "live.mode = original_mode" in repair
    assert "live.active_transport = original_active" in repair
    assert "live.preferred_transport = original_preferred" in repair
    assert "post_repair_carrier_probe_failed" in repair

    lock = _function_source(repair_source, "_repair_lock")
    assert "/tmp/twinpanel-tp27-repair-" in lock
    assert "fcntl.LOCK_EX" in lock

    reconcile = _function_source(repair_source, "reconcile_once")
    assert "count < FAILURE_THRESHOLD" in reconcile
    assert "_cooldown_remaining(row)" in reconcile
    assert 'source="manager"' in reconcile
    assert "force_rebuild=True" in reconcile

    # Transport Manager owns the background loop; API runtime exposes only
    # explicit admin diagnose/repair/rebuild actions.
    assert "tp27_self_repair_v265 import reconciler_loop as tp27_self_repair_loop" in manager_source
    assert 'name="twinpanel-tp27-self-repair-v265"' in manager_source
    assert "tp27_self_repair_task" in manager_source

    assert "tp27_repair_api_v265 import apply_tp27_repair_api_v265" in hosted_source
    assert "apply_tp27_repair_api_v265()" in hosted_source

    for route in (
        '"/{tunnel_id}/tp27/diagnose"',
        '"/{tunnel_id}/tp27/repair"',
        '"/{tunnel_id}/tp27/rebuild"',
    ):
        assert route in api_source

    for method in ("tp27Diagnose", "tp27Repair", "tp27Rebuild"):
        assert method in client_source

    assert 'tp27_fast:"TP27 Fast"' in ui_source
    assert "تشخیص TP27" in ui_source
    assert "تعمیر TP27" in ui_source
    assert "بازسازی Carrier" in ui_source
    assert "Self‑Repair V265" in ui_source

    print("TP27_SELF_REPAIR_V265=PASS")


if __name__ == "__main__":
    main()
