from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v289_backend_separates_auto_qualification_from_manual_eligibility():
    source = read("backend/app/routers/modern_transports.py")
    ast.parse(source)

    assert "TWINPANEL_MANUAL_CUTOVER_ELIGIBILITY_V289" in source
    assert "manual_selectable = bool(" in source
    assert "online\n        and not block" in source

    # Auto promotion keeps the existing 60-second stability gate.
    assert "stable_seconds >= float(CANDIDATE_STABLE_SECONDS)" in source
    assert '"qualified": qualified' in source
    assert '"selectable": qualified' in source

    # Manual authority has a separate capability signal.
    assert '"manual_selectable": manual_selectable' in source
    assert '"manual_block_reason": manual_block_reason' in source
    assert '"manual_selection_requires_fresh_probe": True' in source


def test_v289_manual_endpoint_uses_manual_preflight_not_auto_stability_gate():
    source = read("backend/app/routers/modern_transports.py")

    assert 'if not bool(view.get("manual_selectable")):' in source
    assert 'not bool(fresh_view.get("manual_selectable"))' in source

    # The old auto-only selector must not gate explicit manual authority.
    select_manual = source.split(
        'async def select_modern_transport_manual(', 1
    )[1].split(
        '@router.post("/{tunnel_id}/modern-transports/{transport}/install")', 1
    )[0]
    assert 'view.get("selectable")' not in select_manual
    assert 'fresh_view.get("selectable")' not in select_manual


def test_v289_preserves_fresh_probe_agent_acceptance_and_rollback():
    source = read("backend/app/routers/modern_transports.py")

    select_manual = source.split(
        'async def select_modern_transport_manual(', 1
    )[1].split(
        '@router.post("/{tunnel_id}/modern-transports/{transport}/install")', 1
    )[0]

    assert "await _fresh_manual_candidate_health_v257(" in select_manual
    assert "await _wait_manual_cutover_acceptance_v257(" in select_manual
    assert "_rollback_manual_cutover_v257(" in select_manual
    assert '"authority_unchanged": True' in select_manual
    assert '"manual_stability_gate_bypassed": True' in select_manual
    assert '"manual_acceptance": "fresh_probe_plus_agent_confirmation"' in select_manual


def test_v289_ui_uses_manual_selectable_and_keeps_one_visible_control_surface():
    ui = read("components/smart-transports-runtime-v25.tsx")

    assert "TWINPANEL_UNIFIED_MANUAL_TRANSPORT_CONTROL_V287" in ui
    assert "TWINPANEL_MANUAL_CUTOVER_ELIGIBILITY_UI_V289" in ui
    assert "const manualSelectable=Boolean(row.manual_selectable);" in ui
    assert "disabled={Boolean(busy)||isActive||!manualSelectable}" in ui
    assert "!row.selectable" not in ui
    assert "row.selectable&&<button" not in ui
    assert 'pick("آماده انتخاب دستی","Manual ready")' in ui
    assert 'pick("تأیید Auto","Auto qualified")' in ui
    assert "شرط ۶۰ ثانیه فقط برای Smart Auto است" in ui


def test_v289_types_expose_manual_cutover_contract():
    api = read("lib/modern-transport-api.ts")

    assert "manual_selectable?:boolean;" in api
    assert "manual_block_reason?:string|null;" in api
    assert "manual_selection_requires_fresh_probe?:boolean;" in api
