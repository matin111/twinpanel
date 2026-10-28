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


def test_v205_reverse_adapter_is_owned_and_removed_on_reset():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "def _reverse_chain(tunnel_id: int) -> str:" in spoof
    assert 'reverse_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-REV"' in spoof
    assert "iptables -t nat -C PREROUTING" in spoof
    assert "iptables -t nat -D PREROUTING" in spoof
    assert "iptables -t nat -F" in spoof
    assert "iptables -t nat -X" in spoof
    assert spoof.index("await _reset_pair(ci, ce, rt, cfg)") < spoof.index(
        "await _install_firewall("
    )


def test_v205_shared_2053_demux_is_fail_closed_for_tp27():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")
    tp27 = read("backend/app/transport_candidates/tp27_fast.py")

    # TP27 stays on its existing candidate set and keeps FoU source-port auto.
    assert "FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)" in tp27
    assert "encap-sport auto" in tp27

    # Spoof must not redirect all UDP/2053 traffic. The child chain requires the
    # configured Exit IP, selected Spoof source port and a WireGuard message
    # type signature before REDIRECTing to the private per-tunnel receiver.
    assert "WIREGUARD_MESSAGE_TYPES = (1, 2, 3, 4)" in spoof
    assert 'f"-s {shlex.quote(exit_spoof_ip)} "' in spoof
    assert 'f"--sport {int(spoof_source_port)} "' in spoof
    assert '"-m string --algo bm "' in spoof
    assert 'f"--hex-string {shlex.quote(signature)} "' in spoof
    assert 'f"-j REDIRECT --to-ports {int(local_receive_port)}"' in spoof


def test_v205_reverse_metadata_exposes_adapter_contract():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert '"generation": 205' in spoof
    assert '"mode": "shared-public-udp-redirection"' in spoof
    assert '"public_port": REVERSE_INGRESS_PORT' in spoof
    assert '"selector": "exit-ip+spoof-source-port+wireguard-message-type"' in spoof
    assert '"reverse_ingress_port": REVERSE_INGRESS_PORT' in spoof
