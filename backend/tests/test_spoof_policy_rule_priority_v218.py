import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v218_module_is_syntax_valid_and_scoped_to_spoof():
    v218 = read("backend/app/spoof_policy_rule_priority_v218.py")

    ast.parse(v218)
    assert 'MARKER = "TWINPANEL_SPOOF_POLICY_RULE_PRIORITY_V218"' in v218
    assert "VERSION = 218" in v218
    assert 'if value == "spoof_wg":' in v218
    assert "from . import spoof_reverse_icmp_fallback_v214 as v214" in v218
    assert "from . import transport_candidates as candidates" in v218


def test_v218_keeps_historical_table_but_moves_rule_before_linux_main():
    v218 = read("backend/app/spoof_policy_rule_priority_v218.py")

    assert "SPOOF_POLICY_SPAN = 900" in v218
    assert "SPOOF_TABLE_BASE = 33000" in v218
    assert "SPOOF_RULE_BASE = 28000" in v218
    assert "LINUX_MAIN_RULE_PRIORITY = 32766" in v218
    assert "table = SPOOF_TABLE_BASE + offset" in v218
    assert "priority = SPOOF_RULE_BASE + offset" in v218
    assert "if priority >= LINUX_MAIN_RULE_PRIORITY" in v218

    # Whole V218 Spoof band must stay ahead of Linux's built-in main rule.
    assert 28000 + 899 < 32766


def test_v218_does_not_change_tp27_policy_band():
    candidates = read("backend/app/transport_candidates/__init__.py")
    v218 = read("backend/app/spoof_policy_rule_priority_v218.py")

    assert 'if value == "tp27_fast":' in candidates
    assert "table = 29000 + (int(tunnel_id) % 900)" in candidates
    assert "tp27_fast" not in v218
    assert "tp27=unchanged" in v218


def test_v218_patches_both_policy_id_authorities_without_rewriting_v179():
    v218 = read("backend/app/spoof_policy_rule_priority_v218.py")

    assert "candidates.policy_ids = _policy_ids_v218" in v218
    assert "candidate_common.policy_ids = _policy_ids_v218" in v218
    assert "v214.probe = _probe_v218" in v218
    assert "def probe_v179" not in v218
    assert "shared_probe=v179-unchanged" in v218


def test_v218_removes_legacy_330xx_rule_before_spoof_probe():
    v218 = read("backend/app/spoof_policy_rule_priority_v218.py")

    assert "legacy_priority = SPOOF_TABLE_BASE + offset" in v218
    assert "while ip rule del priority {int(legacy_priority)}" in v218
    assert "result = await _original_probe(" in v218
    assert '"legacy_rule_cleanup": "before-spoof-icmp-probe"' in v218


def test_v218_persists_generation_and_policy_metadata_only_after_success():
    v218 = read("backend/app/spoof_policy_rule_priority_v218.py")

    assert "result = await _original_install_icmp(" in v218
    assert 'meta["generation"] = VERSION' in v218
    assert 'meta["qualification"] = "full-shared-l3-probe+reverse-icmp-v218"' in v218
    assert 'meta["spoof_policy_routing"]' in v218
    assert "row.config_text = _updated_meta(row.config_text, int(tunnel_id))" in v218
    assert "db.commit()" in v218


def test_v218_api_and_manager_registry_apply_after_v217_before_tp6():
    registry = read("backend/app/kernel_transport_registry_v209.py")

    ast.parse(registry)
    assert (
        "from .spoof_policy_rule_priority_v218 import "
        "apply_spoof_policy_rule_priority_v218"
    ) in registry

    v202 = registry.index("apply_spoof_candidate_policy_v202()")
    v217 = registry.index("apply_spoof_icmp_scoped_echo_v217()", v202)
    v218 = registry.index("apply_spoof_policy_rule_priority_v218()", v217)
    tp6 = registry.index("apply_tp6_candidate_registry_v208()", v218)

    assert v202 < v217 < v218 < tp6
    assert "spoof_policy=v202-v214+v217+v218" in registry
