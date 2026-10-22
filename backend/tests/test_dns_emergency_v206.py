from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dns_emergency_models import DnsEmergencySetting
from app.routers.dns_emergency import (
    BINARY_PATH,
    DNSTT_COMMIT,
    DNSTT_REPOSITORY,
    GO_ROOT,
    GO_SHA256,
    GO_VERSION,
    SERVICE_NAME,
    _install_script,
    _listen_addr,
    _normalize_domain,
    _tcp_capable,
    router,
)


def test_dns_emergency_uses_additive_table():
    assert DnsEmergencySetting.__tablename__ == "dns_emergency_settings"


def test_domain_validation_is_fail_closed():
    assert _normalize_domain("T.Example.COM.", field_name="Tunnel Domain") == "t.example.com"
    for value in ("example", "-t.example.com", "t..example.com", "t example.com"):
        with pytest.raises(HTTPException) as exc:
            _normalize_domain(value, field_name="Tunnel Domain")
        assert exc.value.status_code == 422


def test_tcp_candidate_detection_excludes_udp_only_transports():
    assert _tcp_capable("TCP + DTLS")
    assert _tcp_capable("WebSocket / TLS")
    assert _tcp_capable("gRPC REALITY")
    assert not _tcp_capable("UDP")
    assert not _tcp_capable("QUIC / UDP")


def test_listener_formats_ipv4_and_ipv6():
    assert _listen_addr("203.0.113.8") == "203.0.113.8:53"
    assert _listen_addr("2001:db8::8") == "[2001:db8::8]:53"


def test_install_script_is_pinned_and_keeps_upstream_local():
    node = SimpleNamespace(public_ip="203.0.113.8")
    script = _install_script(node, "t.example.com", 443)
    assert DNSTT_REPOSITORY in script
    assert DNSTT_COMMIT in script
    assert "@latest" not in script
    assert BINARY_PATH in script
    assert SERVICE_NAME in script
    assert "-udp 203.0.113.8:53" in script
    assert "t.example.com 127.0.0.1:443" in script
    assert "systemctl restart twinpanel-dnstt.service" in script


def test_install_script_pins_verified_go_toolchain():
    node = SimpleNamespace(public_ip="203.0.113.8")
    script = _install_script(node, "t.example.com", 443)
    assert GO_VERSION == "1.23.12"
    assert GO_ROOT in script
    assert f"go{GO_VERSION}.linux-${{go_arch}}.tar.gz" in script
    assert GO_SHA256["amd64"] in script
    assert GO_SHA256["arm64"] in script
    assert "sha256sum -c -" in script
    assert '"$GO_BIN" build' in script
    assert "apt-get install -y --no-install-recommends ca-certificates curl git tar" in script
    assert "golang-go" not in script


def test_router_exposes_inventory_install_health_and_remove():
    paths = {(route.path, ",".join(sorted(route.methods or []))) for route in router.routes}
    assert ("/v1/settings/vpn/dns-emergency", "GET") in paths
    assert ("/v1/settings/vpn/dns-emergency/{node_id}/install", "POST") in paths
    assert ("/v1/settings/vpn/dns-emergency/{node_id}/health", "POST") in paths
    assert ("/v1/settings/vpn/dns-emergency/{node_id}", "DELETE") in paths
