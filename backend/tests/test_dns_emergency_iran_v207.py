from types import SimpleNamespace

from app.dnstt_artifact import ARTIFACT_NAMES, _normalize_arch
from app.dns_emergency_iran_models import DnsEmergencyIranSetting
from app.routers import tunnels as tunnel_router
from app.routers.dns_emergency import BINARY_PATH, DNSTT_COMMIT, DNSTT_REPOSITORY, GO_VERSION
from app.routers.dns_emergency_iran import (
    SERVICE_NAME,
    STATE_DIR,
    _client_payload,
    _install_script,
    _tunnel_addresses,
    router,
)


def test_dns_emergency_iran_uses_additive_table():
    assert DnsEmergencyIranSetting.__tablename__ == "dns_emergency_iran_settings"


def test_tunnel_address_mapping_uses_active_l3_runtime(monkeypatch):
    monkeypatch.setattr(
        tunnel_router,
        "_tunnel_addresses",
        lambda _tunnel_id: (
            "10.253.0.24/30",
            "10.253.0.25/30",
            "10.253.0.26/30",
        ),
    )

    network, iran_ip, exit_ip = _tunnel_addresses(6)

    assert network == "10.253.0.24/30"
    assert iran_ip == "10.253.0.25"
    assert exit_ip == "10.253.0.26"


def test_iran_relay_installs_listener_on_iran_and_upstream_on_active_tunnel_ip():
    iran = SimpleNamespace(public_ip="203.0.113.10")
    script = _install_script(iran, "ir-dns.example.com", "10.253.0.26", 443)

    assert DNSTT_COMMIT in script
    assert SERVICE_NAME in script
    assert STATE_DIR in script
    assert BINARY_PATH in script
    assert "-udp 203.0.113.10:53" in script
    assert "ir-dns.example.com 10.253.0.26:443" in script
    assert "ir-dns.example.com 127.0.0.1:443" not in script
    assert "systemctl restart twinpanel-dnstt-iran.service" in script


def test_iran_relay_install_has_no_external_bootstrap_dependency():
    iran = SimpleNamespace(public_ip="203.0.113.10")
    script = _install_script(iran, "ir-dns.example.com", "10.253.0.26", 443)

    assert "go.dev" not in script
    assert "git fetch" not in script
    assert "apt-get" not in script
    assert "GOTOOLCHAIN" not in script
    assert DNSTT_REPOSITORY not in script
    assert f"test -x {BINARY_PATH}" in script


def test_dnstt_release_artifacts_cover_supported_linux_architectures():
    assert _normalize_arch("x86_64") == "amd64"
    assert _normalize_arch("amd64") == "amd64"
    assert _normalize_arch("aarch64") == "arm64"
    assert _normalize_arch("arm64") == "arm64"
    assert ARTIFACT_NAMES == {
        "amd64": "dnstt-server-linux-amd64",
        "arm64": "dnstt-server-linux-arm64",
    }


def test_iran_relay_client_defaults_to_operator_resolver_placeholder():
    setting = SimpleNamespace(
        public_key="0123456789abcdef",
        tunnel_domain="ir-dns.example.com",
    )
    payload = _client_payload(setting)
    assert payload is not None
    assert payload["mode"] == "iran_relay"
    assert "<resolver-ip>:53" in payload["command_example"]
    assert "1.1.1.1" not in payload["command_example"]
    assert "8.8.8.8" not in payload["command_example"]


def test_router_exposes_iran_inventory_install_health_and_remove():
    paths = {(route.path, ",".join(sorted(route.methods or []))) for route in router.routes}
    assert ("/v1/settings/vpn/dns-emergency-iran", "GET") in paths
    assert ("/v1/settings/vpn/dns-emergency-iran/{iran_node_id}/install", "POST") in paths
    assert ("/v1/settings/vpn/dns-emergency-iran/{iran_node_id}/health", "POST") in paths
    assert ("/v1/settings/vpn/dns-emergency-iran/{iran_node_id}", "DELETE") in paths
