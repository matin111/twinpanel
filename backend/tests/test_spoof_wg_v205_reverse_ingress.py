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

    # TP27 stays on its existing candidate set and keeps FoU source-port auto.
    assert "FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)" in tp27
    assert "encap-sport auto" in tp27

    # Spoof must not rewrite all UDP/2053 traffic. The stateless raw/prerouting
    # rule requires the configured Exit IP, selected Spoof source port and one
    # of the four real WireGuard message prefixes before changing dport.
    assert 'WIREGUARD_MESSAGE_PREFIXES = (' in spoof
    for prefix in ("0x01000000", "0x02000000", "0x03000000", "0x04000000"):
        assert f'"{prefix}"' in spoof
    assert "ip saddr {cfg['exit_spoof_ip']}" in spoof
    assert "udp sport {ports['spoof_source_port']}" in spoof
    assert "udp dport {ports['iran_reverse_public_port']}" in spoof
    assert "@th,64,32" in spoof
    assert "udp dport set {ports['iran_raw_receive_port']}" in spoof


def test_v205_reverse_metadata_exposes_stateless_adapter_contract():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert '"generation": 205' in spoof
    assert '"mode": "shared-public-udp-stateless-nft"' in spoof
    assert '"public_port": REVERSE_INGRESS_PORT' in spoof
    assert '"selector": "exit-ip+spoof-source-port+wireguard-message-prefix"' in spoof
    assert '"hook": "prerouting"' in spoof
    assert '"priority": "raw"' in spoof
    assert '"reverse_ingress_port": REVERSE_INGRESS_PORT' in spoof


def test_v205_nftables_dependency_is_explicit_and_iran_only():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "async def _ensure_nftables(conn) -> None:" in spoof
    assert 'apt-get update -qq; apt-get install -y -qq nftables' in spoof
    assert spoof.count("await _ensure_nftables(ci)") == 1
    assert "await _ensure_nftables(ce)" not in spoof
