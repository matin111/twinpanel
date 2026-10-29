import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v217_module_is_syntax_valid_and_scoped_to_v214_icmp_runtime():
    v217 = read("backend/app/spoof_icmp_scoped_echo_v217.py")

    ast.parse(v217)
    assert 'MARKER = "TWINPANEL_SPOOF_ICMP_SCOPED_ECHO_V217"' in v217
    assert "VERSION = 217" in v217
    assert "from . import spoof_reverse_icmp_fallback_v214 as v214" in v217
    assert "v214._write_peer_runtime_icmp = _write_peer_runtime_icmp_v217" in v217
    assert "v214._install_icmp = _install_icmp_v217" in v217


def test_v217_replaces_host_global_echo_side_effect_with_scoped_outer_drop():
    v217 = read("backend/app/spoof_icmp_scoped_echo_v217.py")

    assert 'RULE_SUFFIX = "ICMP-SCOPED-V217"' in v217
    assert "iptables -C OUTPUT" in v217
    assert "--icmp-type echo-reply" in v217
    assert "-d {shlex.quote(cfg['exit_spoof_ip'])}" in v217
    assert "-j DROP" in v217
    assert "iptables -D OUTPUT" in v217


def test_v217_service_local_sysctl_shim_noops_only_global_echo_writes():
    v217 = read("backend/app/spoof_icmp_scoped_echo_v217.py")

    assert "net.ipv4.icmp_echo_ignore_all=0|net.ipv4.icmp_echo_ignore_all=1" in v217
    assert "Environment=PATH={shlex.quote(shim_dir)}:" in v217
    assert "exec \"$REAL\" \"$@\"" in v217
    assert "service-local-shim-noop" in v217
    assert '"host_sysctl_authority": "preexisting-value-preserved"' in v217


def test_v217_helper_preserves_original_host_echo_policy_and_cleanup():
    v217 = read("backend/app/spoof_icmp_scoped_echo_v217.py")

    assert "v214._echo_state_path(tunnel_id)" in v217
    assert '"$REAL_SYSCTL" -n net.ipv4.icmp_echo_ignore_all' in v217
    assert '"$REAL_SYSCTL" -w "net.ipv4.icmp_echo_ignore_all=$PREV"' in v217
    assert "rm -f \"$ECHO_STATE\"" in v217
    assert "rm -rf {shlex.quote(_shim_dir(tunnel_id))}" in v217


def test_v217_keeps_shared_probe_and_persists_new_generation_only_after_success():
    v217 = read("backend/app/spoof_icmp_scoped_echo_v217.py")

    assert 'meta["generation"] = VERSION' in v217
    assert 'meta["qualification"] = "full-shared-l3-probe+reverse-icmp-v217"' in v217
    assert "result = await _original_install_icmp(" in v217
    assert "row.config_text = _updated_meta(row.config_text)" in v217
    assert "db.commit()" in v217
    assert "shared_probe=v179-unchanged" in v217


def test_v217_api_and_manager_registry_apply_after_v202_chain():
    registry = read("backend/app/kernel_transport_registry_v209.py")

    ast.parse(registry)
    assert (
        "from .spoof_icmp_scoped_echo_v217 import "
        "apply_spoof_icmp_scoped_echo_v217"
    ) in registry
    v202 = registry.index("apply_spoof_candidate_policy_v202()")
    v217 = registry.index("apply_spoof_icmp_scoped_echo_v217()", v202)
    tp6 = registry.index("apply_tp6_candidate_registry_v208()", v217)
    assert v202 < v217 < tp6


def test_v217_does_not_redefine_tp27_vxlan_or_shared_probe_code():
    v217 = read("backend/app/spoof_icmp_scoped_echo_v217.py")

    assert "from .transport_candidates import tp27_fast" not in v217
    assert "from .transport_candidates import kernel_vxlan" not in v217
    assert "def probe_v179" not in v217
    assert "candidate_common.probe" not in v217
