from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPAIR = ROOT / "backend" / "app" / "tp27_self_repair_v265.py"
OWNER = ROOT / "backend" / "app" / "tp27_repair_owner_guard.py"
API = ROOT / "backend" / "app" / "tp27_repair_api_v265.py"
MANAGER = ROOT / "backend" / "app" / "tunnel_transport_manager_v12.py"
UI = ROOT / "components" / "smart-transports-runtime-v26.tsx"


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
    owner_source = OWNER.read_text(encoding="utf-8")
    api_source = API.read_text(encoding="utf-8")
    manager_source = MANAGER.read_text(encoding="utf-8")
    ui_source = UI.read_text(encoding="utf-8")

    for path, source in (
        (REPAIR, repair_source),
        (OWNER, owner_source),
        (API, api_source),
        (MANAGER, manager_source),
    ):
        compile(source, str(path), "exec")

    # Dedicated TP27 owner must fence both normal scheduling and a stale worker
    # that was queued immediately before TP27 became enabled.
    owner_apply = _function_source(owner_source, "apply_tp27_repair_owner_guard")
    assert 'TunnelTransport.transport == "tp27_fast"' in owner_source
    assert "TunnelTransport.enabled.is_(True)" in owner_source
    assert "managed_tunnel_ids_without_tp27" in owner_apply
    assert "run_self_heal_without_tp27" in owner_apply
    assert "tp27_repair_owns_tunnel" in owner_apply
    assert "v8._managed_tunnel_ids = managed_tunnel_ids_without_tp27" in owner_apply
    assert "v9._run_self_heal_authoritative = run_self_heal_without_tp27" in owner_apply
    assert "owner=tp27_self_repair_v265" in owner_apply

    assert "apply_tp27_repair_owner_guard()" in manager_source
    assert "tp27_repair_owner_guard=active" in manager_source

    # The historical managed-repair API uses a separate lock domain and must
    # fail closed instead of racing TP27 repair or silently redirecting it.
    api_guard = _function_source(api_source, "_legacy_managed_repair_owner_guard")
    assert "_tp27_owns_repair" in api_guard
    assert "status_code=409" in api_guard
    assert '"repair_owner": "tp27_self_repair_v265"' in api_guard
    assert "/tp27/repair" in api_guard
    assert "/tp27/rebuild" in api_guard
    apply_api = _function_source(api_source, "apply_tp27_repair_api_v265")
    assert (
        "tunnel_managed.repair_managed_tunnel = "
        "_legacy_managed_repair_owner_guard"
    ) in apply_api
    assert "legacy-managed-repair-fenced=1" in apply_api

    # Every repair failure, including SSH/prerequisite failures that happen
    # before profile iteration, must create durable cooldown/error telemetry.
    failed_meta = _function_source(repair_source, "_failed_repair_meta")
    for token in (
        '"last_repair_epoch"',
        '"last_result": "failed"',
        '"last_error"',
        '"source"',
        '"attempts"',
    ):
        assert token in failed_meta

    repair = _function_source(repair_source, "_repair_tp27_locked")
    assert "failure_recorded = False" in repair
    assert "tp27_repair_exception:" in repair
    assert repair.count("_failed_repair_meta(") >= 2
    assert 'status="failed"' in repair

    # ONLINE is published only after the post-repair bidirectional snapshot.
    verify_pos = repair.index("post_repair_carrier_probe_failed")
    online_mark_pos = repair.index('status="online"', verify_pos)
    assert verify_pos < online_mark_pos

    diagnose = _function_source(repair_source, "diagnose_tp27")
    for field in (
        '"repair_attempts"',
        '"last_repair_at"',
        '"last_repair_result"',
        '"last_repair_error"',
        '"repaired_profile"',
        '"cooldown_remaining_seconds"',
    ):
        assert field in diagnose

    # Primary transport card must expose the three TP27 operations and the
    # carrier/repair telemetry needed for production diagnosis.
    for token in (
        "تشخیص TP27",
        "تعمیر TP27",
        "بازسازی Carrier",
        "Iran → Exit",
        "Exit → Iran",
        "سرویس ایران",
        "سرویس خارج",
        "Interface ایران",
        "Interface خارج",
        "آخرین Repair",
        "Repair attempts",
        "Cooldown",
        "آخرین خطای Repair",
    ):
        assert token in ui_source

    print("TP27_REPAIR_OWNER_COOLDOWN=PASS")


if __name__ == "__main__":
    main()
