import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_spoof_wg_v203_source_port_fallback_is_bounded_and_syntax_valid():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    ast.parse(spoof)

    assert "TWINPANEL SPOOF + WIREGUARD L3 V203" in spoof
    assert "SPOOF_SOURCE_PORT = 443" in spoof
    assert "SPOOF_SOURCE_PORT_CANDIDATES = (SPOOF_SOURCE_PORT, 44443)" in spoof
    assert 'SPOOF_SOURCE_PORT_META_KEY = "spoof_source_port"' in spoof
    assert '"generation": 203' in spoof


def test_spoof_wg_v203_prefers_last_successful_source_port():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "def _persisted_source_port(raw: str | None) -> int | None:" in spoof
    assert "if port not in SPOOF_SOURCE_PORT_CANDIDATES:" in spoof
    assert "def _source_port_candidates(raw: str | None) -> tuple[int, ...]:" in spoof
    assert "return SPOOF_SOURCE_PORT_CANDIDATES" in spoof
    assert "return (persisted, *remaining)" in spoof
    assert "source_port_candidates = _source_port_candidates(raw_config)" in spoof


def test_spoof_wg_v203_retries_only_peer_ping_failures():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "for index, source_port in enumerate(source_port_candidates):" in spoof
    assert "has_fallback = index + 1 < len(source_port_candidates)" in spoof
    assert 'if not str(exc).startswith("peer_ping_failed:") or not has_fallback:' in spoof
    assert "raise\n                continue" in spoof

    # The source-port lane must not turn arbitrary runtime, TCP, UDP, or
    # dependency failures into retries. Only the peer-ping RuntimeError is
    # intercepted inside the bounded candidate loop.
    assert 'startswith("tcp_egress_probe_failed")' not in spoof
    assert 'startswith("udp_egress_probe_failed")' not in spoof


def test_spoof_wg_v203_persists_only_the_qualified_port():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "selected_source_port = source_port" in spoof
    assert 'raise RuntimeError("spoof_wg_source_port_qualification_failed")' in spoof
    assert "SPOOF_SOURCE_PORT_META_KEY: selected_source_port" in spoof
    assert '"spoof_source_port_attempts": source_port_attempts' in spoof
    assert '"spoof_source_port": selected_source_port' in spoof
    assert '"ports": _ports(tunnel_id, selected_source_port)' in spoof


def test_spoof_wg_v203_threads_one_candidate_into_both_peer_services():
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert "spoof_source_port: int," in spoof
    assert "ports = _ports(tunnel_id, spoof_source_port)" in spoof
    assert spoof.count("spoof_source_port=source_port,") == 2
    assert "f\"--spoof-port {ports['spoof_source_port']} \"" in spoof
