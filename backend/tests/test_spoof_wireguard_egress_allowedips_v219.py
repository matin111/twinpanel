import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v219_module_is_syntax_valid_and_scoped_to_iran_spoof():
    v219 = read("backend/app/spoof_wireguard_egress_allowedips_v219.py")

    ast.parse(v219)
    assert 'MARKER = "TWINPANEL_SPOOF_WIREGUARD_EGRESS_ALLOWEDIPS_V219"' in v219
    assert "VERSION = 219" in v219
    assert 'IRAN_EGRESS_ALLOWED_IPS = "0.0.0.0/0"' in v219
    assert 'if role != "iran":' in v219
    assert "tp27=unchanged vxlan=unchanged" in v219
    assert "shared_probe=v179-unchanged" in v219


def test_v219_expands_only_iran_peer_cryptokey_route_for_public_egress():
    v219 = read("backend/app/spoof_wireguard_egress_allowedips_v219.py")

    # V219 must preserve the already-proven V217 writer first, then refine only
    # the Iran peer. Exit returns before any all-destination AllowedIPs mutation.
    original_call = v219.index("await _original_write_peer_runtime_icmp(")
    iran_guard = v219.index('if role != "iran":', original_call)
    live_set = v219.index("wg set {shlex.quote(iface)} peer", iran_guard)

    assert original_call < iran_guard < live_set
    assert 'IRAN_EGRESS_ALLOWED_IPS = "0.0.0.0/0"' in v219
    assert '"exit_peer_allowed_ips": "iran-inner-/32"' in v219
    assert '"scope": "spoof-icmp-iran-peer-only"' in v219


def test_v219_persists_allowedips_across_v217_service_restart():
    v219 = read("backend/app/spoof_wireguard_egress_allowedips_v219.py")

    assert 'HELPER_MARKER = "TWINPANEL_SPOOF_WG_ALLOWED_IPS_V219"' in v219
    assert 'HELPER={shlex.quote(helper)}' in v219
    assert 'cat >> "$HELPER"' in v219
    assert 'wg set "$IFACE" peer {peer} allowed-ips {allowed}' in v219
    assert 'wg show {shlex.quote(iface)} allowed-ips' in v219
    assert "V219_ALLOWED_IPS_MISMATCH" in v219


def test_v219_keeps_v218_linux_rpdb_as_egress_authority():
    v219 = read("backend/app/spoof_wireguard_egress_allowedips_v219.py")
    v218 = read("backend/app/spoof_policy_rule_priority_v218.py")

    assert '"routing_authority": "v218-source-policy-before-main"' in v219
    assert "SPOOF_TABLE_BASE = 33000" in v218
    assert "SPOOF_RULE_BASE = 28000" in v218
    assert "LINUX_MAIN_RULE_PRIORITY = 32766" in v218

    # V219 does not create a host default route or rewrite V179 qualification.
    assert "ip route replace default" not in v219
    assert "ip route add default" not in v219
    assert "def probe_v179" not in v219


def test_v219_persists_generation_and_allowedips_metadata_after_success():
    v219 = read("backend/app/spoof_wireguard_egress_allowedips_v219.py")

    assert "result = await _original_install_icmp(" in v219
    assert 'meta["generation"] = VERSION' in v219
    assert 'meta["qualification"] = "full-shared-l3-probe+reverse-icmp-v219"' in v219
    assert 'meta["spoof_wireguard_egress_allowed_ips"]' in v219
    assert '"iran_peer_allowed_ips": IRAN_EGRESS_ALLOWED_IPS' in v219
    assert "db.commit()" in v219


def test_v219_api_and_manager_registry_apply_after_v218_before_tp6():
    registry = read("backend/app/kernel_transport_registry_v209.py")

    ast.parse(registry)
    assert (
        "from .spoof_wireguard_egress_allowedips_v219 import (\n"
        "    apply_spoof_wireguard_egress_allowedips_v219,\n"
        ")"
    ) in registry

    v202 = registry.index("apply_spoof_candidate_policy_v202()")
    v217 = registry.index("apply_spoof_icmp_scoped_echo_v217()", v202)
    v218 = registry.index("apply_spoof_policy_rule_priority_v218()", v217)
    v219 = registry.index("apply_spoof_wireguard_egress_allowedips_v219()", v218)
    tp6 = registry.index("apply_tp6_candidate_registry_v208()", v219)

    assert v202 < v217 < v218 < v219 < tp6
    assert "spoof_policy=v202-v214+v217+v218+v219" in registry
