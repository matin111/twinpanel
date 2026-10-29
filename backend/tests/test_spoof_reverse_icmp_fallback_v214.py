import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v214_module_is_syntax_valid_and_additive_to_v205():
    v214 = read("backend/app/spoof_reverse_icmp_fallback_v214.py")
    core = read("backend/app/transport_candidates/spoof_wg.py")

    ast.parse(v214)
    ast.parse(core)

    assert 'MARKER = "TWINPANEL_SPOOF_REVERSE_ICMP_FALLBACK_V214"' in v214
    assert 'ICMP_TRANSPORT = "icmp"' in v214
    assert 'SEND_TRANSPORT = "tcp"' in core
    assert 'RECV_TRANSPORT = "udp"' in core
    assert 'REVERSE_INGRESS_PORT = 2053' in core


def test_v214_is_outermost_after_v206_v213_policy_hooks():
    policy = read("backend/app/spoof_candidate_policy_v202.py")

    ast.parse(policy)
    assert (
        "from .spoof_reverse_icmp_fallback_v214 "
        "import apply_spoof_reverse_icmp_fallback_v214"
    ) in policy
    v206 = policy.index("apply_spoof_underlay_guard_v206()")
    v213 = policy.index("apply_spoof_last_error_recovery_v212()")
    v214 = policy.index("apply_spoof_reverse_icmp_fallback_v214()")
    assert v206 < v213 < v214


def test_v214_fallback_is_exact_underlay_scoped_and_persisted():
    v214 = read("backend/app/spoof_reverse_icmp_fallback_v214.py")

    assert "guard.classify_spoof_install_failure(text) == guard.UNDERLAY_REASON" in v214
    assert '"spoof_underlay_quarantined:" in text' in v214
    assert "guard.active_underlay_quarantine_for_tunnel" in v214
    assert 'REVERSE_TRANSPORT_META_KEY = "spoof_reverse_transport"' in v214
    assert 'trigger="persisted_icmp_v214"' in v214
    assert 'trigger="active_v206_v213_udp_quarantine"' in v214
    assert 'trigger="fresh_v205_udp_reverse_failure"' in v214
    assert "if not _exact_quarantine(message):" in v214
    assert "raise\n        return await _install_icmp(" in v214


def test_v214_reverse_icmp_keeps_forward_tcp_and_wireguard_l3():
    v214 = read("backend/app/spoof_reverse_icmp_fallback_v214.py")

    assert "f\"--send-transport {spoof_wg.SEND_TRANSPORT} \"" in v214
    assert "f\"--recv-transport {ICMP_TRANSPORT}\"" in v214
    assert "f\"--send-transport {ICMP_TRANSPORT} \"" in v214
    assert "f\"--recv-transport {spoof_wg.SEND_TRANSPORT}\"" in v214
    assert 'ip link add "$IFACE" type wireguard' in v214
    assert "await probe(" in v214
    assert '"qualification": "full-shared-l3-probe+reverse-icmp-v214"' in v214


def test_v214_icmp_mode_removes_v205_nft_authority_and_owns_cleanup():
    v214 = read("backend/app/spoof_reverse_icmp_fallback_v214.py")

    assert "nft delete table ip" in v214
    assert '"v205_nft_required": False' in v214
    assert "--icmp-type echo-request" in v214
    assert 'ICMP_RULE_SUFFIX = "ICMP-V214"' in v214
    assert "spoof_wg._remove_owned_firewall = _remove_owned_firewall_v214" in v214
    assert "nft -f -" not in v214
    assert "udp dport set" not in v214


def test_v214_preserves_and_resolves_exact_historical_guard_only_after_success():
    v214 = read("backend/app/spoof_reverse_icmp_fallback_v214.py")

    assert '"spoof_underlay_guard_v206"' in v214
    assert '"blocked": False' in v214
    assert '"action": "historical_evidence_preserved_icmp_qualified"' in v214
    assert '"resolved_by_version": VERSION' in v214
    assert (
        'str(smart.get("quarantine_reason") or "").strip() '
        "!= guard.UNDERLAY_REASON"
    ) in v214
    assert '"quarantine_reason": ""' in v214
    assert '"quarantine_until_epoch": 0.0' in v214


def test_v214_snapshots_and_restores_upstream_icmp_echo_sysctl():
    v214 = read("backend/app/spoof_reverse_icmp_fallback_v214.py")

    assert "net.ipv4.icmp_echo_ignore_all" in v214
    assert "sysctl -n net.ipv4.icmp_echo_ignore_all" in v214
    assert 'sysctl -w "net.ipv4.icmp_echo_ignore_all=$PREV"' in v214
    assert '"restore": "systemd-helper-restores-preexisting-value"' in v214
    assert "ExecStopPost={helper} down" in v214


def test_v214_does_not_redefine_unrelated_tunnel_dataplanes():
    v214 = read("backend/app/spoof_reverse_icmp_fallback_v214.py")

    assert "kernel_vxlan" not in v214
    assert "tp27_fast" not in v214
    assert "XDP" not in v214
    assert '"xdp": False' in v214
