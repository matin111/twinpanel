import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v205_reverse_ingress_uses_production_qualified_udp_2053():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    ast.parse(spoof)
    assert "REVERSE_INGRESS_PORT = 2053" in spoof
    assert '"iran_reverse_public_port": REVERSE_INGRESS_PORT' in spoof
    assert "f\"--client-port {ports['iran_reverse_public_port']} \"" in spoof
    assert "f\"--recv-port {ports['iran_raw_receive_port']} \"" in spoof
    assert '"qualification": "full-shared-l3-probe+reverse-ingress-v205"' in spoof


def test_v205_reverse_adapter_is_stateless_owned_and_removed_on_reset():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "def _ingress_table(tunnel_id: int) -> str:" in spoof
    assert 'return f"tpsp_ingress_{int(tunnel_id)}"' in spoof
    assert "nft delete table ip" in spoof
    assert "type filter hook prerouting priority raw; policy accept;" in spoof
    assert "udp dport set {ports['iran_raw_receive_port']}" in spoof
    assert "udp checksum set 0" in spoof
    assert "iptables -t nat -C PREROUTING" not in spoof
    assert "REDIRECT --to-ports" not in spoof
    assert spoof.index("await _reset_pair(ci, ce, rt, cfg)") < spoof.index(
        "await _install_firewall("
    )


def test_v205_shared_2053_demux_is_fail_closed_for_tp27():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")
    tp27 = read("backend/app/transport_candidates/tp27_fast.py")

    assert "FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)" in tp27
    assert "encap-sport auto" in tp27

    assert 'WIREGUARD_MESSAGE_PREFIXES = (' in spoof
    for prefix in ("0x01000000", "0x02000000", "0x03000000", "0x04000000"):
        assert f'"{prefix}"' in spoof
    assert "ip saddr {cfg['exit_spoof_ip']}" in spoof
    assert "ip daddr {iran_public}" in spoof
    assert "udp sport {ports['spoof_source_port']}" in spoof
    assert "udp dport {ports['iran_reverse_public_port']}" in spoof
    assert "@th,64,32" in spoof
    assert "udp dport set {ports['iran_raw_receive_port']}" in spoof
    assert "iran_public=str(iran.public_ip)" in spoof


def test_v205_reverse_metadata_exposes_stateless_adapter_contract():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert '"generation": 205' in spoof
    assert '"mode": "shared-public-udp-stateless-nft"' in spoof
    assert '"public_port": REVERSE_INGRESS_PORT' in spoof
    assert '"selector": "exit-ip+iran-public-ip+spoof-source-port+wireguard-message-prefix"' in spoof
    assert '"hook": "prerouting"' in spoof
    assert '"priority": "raw"' in spoof
    assert '"reverse_ingress_port": REVERSE_INGRESS_PORT' in spoof


def test_v205_nftables_dependency_is_explicit_and_iran_only():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "async def _ensure_nftables(conn) -> None:" in spoof
    assert 'apt-get update -qq; apt-get install -y -qq nftables' in spoof
    assert spoof.count("await _ensure_nftables(ci)") == 1
    assert "await _ensure_nftables(ce)" not in spoof


def test_v205_failure_diagnostics_include_owned_nft_counters():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "async def _ingress_diag(conn, tunnel_id: int) -> str:" in spoof
    assert "nft -a list table ip" in spoof
    assert "c = await _ingress_diag(ci, int(tunnel_id)) if ci else" in spoof
    assert "reverse_ingress={c[-1500:]}" in spoof


def test_v206_underlay_guard_is_syntax_valid_and_spoof_only():
    guard = read("backend/app/spoof_underlay_guard_v206.py")
    policy = read("backend/app/spoof_candidate_policy_v202.py")

    ast.parse(guard)
    ast.parse(policy)

    assert 'UNDERLAY_REASON = "underlay_incompatible:reverse_carrier_not_reaching_iran"' in guard
    assert "UNDERLAY_QUARANTINE_SECONDS = 24 * 60 * 60" in guard
    assert 'candidates.INSTALLERS[spoof_wg.NAME] = _guarded_spoof_install' in guard
    assert "spoof_wg.install = _guarded_spoof_install" in guard
    assert "tp27_fast" not in guard
    assert "kernel_vxlan" not in guard
    assert "apply_spoof_underlay_guard_v206()" in policy
    assert 'smart.AUTO_INSTALL_NAMES = ("tp27_fast",)' in policy


def test_v206_underlay_guard_requires_three_independent_failure_signals():
    guard = read("backend/app/spoof_underlay_guard_v206.py")

    assert 'if "peer_ping_failed:" not in text:' in guard
    assert "_exit_reverse_progress(text)" in guard
    assert "_ZERO_INGRESS_RE.search(text)" in guard
    assert "shutting down \\(up=\\d+ down=([1-9]\\d*)\\)" in guard
    assert "counter packets 0 bytes 0" in guard


def test_v206_underlay_guard_persists_fail_closed_quarantine_evidence():
    guard = read("backend/app/spoof_underlay_guard_v206.py")

    for token in (
        '"quarantine_reason": reason',
        '"quarantine_until_epoch": now + float(UNDERLAY_QUARANTINE_SECONDS)',
        '"last_probe_ok": False',
        '"exit_reverse_bytes_nonzero": True',
        '"iran_reverse_ingress_packets": 0',
        '"action": "fail_closed_keep_existing_authority"',
        'status="failed"',
        'enabled=True',
    ):
        assert token in guard, token


def test_v206_guard_does_not_execute_dataplane_or_port_mutations():
    guard = read("backend/app/spoof_underlay_guard_v206.py")

    for forbidden in (
        "conn.run(",
        "subprocess.",
        "nft -f",
        "iptables -",
        "REVERSE_INGRESS_PORT",
        "WIREGUARD_MESSAGE_PREFIXES",
        "--spoof-port",
        "--client-port",
        "udp dport set",
    ):
        assert forbidden not in guard, forbidden


def test_v207_repeated_install_is_rejected_before_original_installer():
    guard = read("backend/app/spoof_underlay_guard_v206.py")

    ast.parse(guard)
    assert 'FAILFAST_MARKER = "TWINPANEL_SPOOF_QUARANTINE_FAILFAST_V207"' in guard
    assert "def active_underlay_quarantine(" in guard
    assert "def active_underlay_quarantine_for_tunnel(" in guard
    assert "active_block = active_underlay_quarantine_for_tunnel" in guard
    assert '"action": "fail_fast_before_node_mutation"' in guard
    assert '"authority_unchanged": True' in guard

    check = guard.index("active_block = active_underlay_quarantine_for_tunnel")
    call_original = guard.index("return await _original_install")
    assert check < call_original


def test_v207_failfast_is_exact_reason_and_expiry_scoped():
    guard = read("backend/app/spoof_underlay_guard_v206.py")

    for token in (
        'if reason != UNDERLAY_REASON:',
        'remaining = max(0, int(until - now))',
        'if remaining <= 0:',
        'guard.get("blocked") is True',
        'str(guard.get("reason") or "") == reason',
        '"retry_after_seconds": remaining',
        '"spoof_underlay_quarantined:"',
        '"authority_unchanged=true"',
    ):
        assert token in guard, token


def test_v208_recovers_only_exact_failed_active_legacy_quarantine():
    guard = read("backend/app/spoof_underlay_guard_v206.py")

    for token in (
        'RECOVERY_MARKER = "TWINPANEL_SPOOF_QUARANTINE_RECOVERY_V208"',
        'legacy_guard_missing = not isinstance(guard, dict) or not guard',
        'if not legacy_guard_missing:',
        'if not bool(row.enabled):',
        'if _row_status(row) != "failed":',
        'if smart.get("last_probe_ok") is not False:',
        '"metadata_source": (',
        '"smart_auto_v21_recovery_v208"',
        '"repair_guard_metadata": not guard_valid',
        '"version": 208',
    ):
        assert token in guard, token


def test_v208_rehydrates_missing_guard_in_db_before_failfast():
    guard = read("backend/app/spoof_underlay_guard_v206.py")

    assert "def _restore_recovered_guard_metadata(" in guard
    assert 'if active_block.get("repair_guard_metadata") is not True:' in guard
    assert '"recovered_from": "smart_auto_v21"' in guard
    assert '"original_v206_guard_metadata_was_missing": True' in guard
    assert '"recovered_at_epoch": now' in guard
    assert "row.config_text = json.dumps(" in guard
    assert "db.commit()" in guard
    assert "db.refresh(row)" in guard

    restore = guard.index("_restore_recovered_guard_metadata(db, int(tunnel_id), active_block)")
    fail = guard.index('raise RuntimeError(\n            "spoof_underlay_quarantined:"')
    call_original = guard.index("return await _original_install")
    assert restore < fail < call_original


def test_v208_failfast_adds_no_network_or_dataplane_mutation():
    guard = read("backend/app/spoof_underlay_guard_v206.py")

    assert "active_underlay_quarantine_for_tunnel(db, int(tunnel_id))" in guard
    for forbidden in (
        "ssh_connect",
        "conn.run(",
        "subprocess.",
        "nft -f",
        "iptables -",
        "ip route ",
        "ip link ",
        "systemctl ",
    ):
        assert forbidden not in guard, forbidden
