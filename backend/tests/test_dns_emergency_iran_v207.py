from types import SimpleNamespace

from app.dns_emergency_iran_models import DnsEmergencyIranSetting
from app.routers.dns_emergency import DNSTT_COMMIT, DNSTT_REPOSITORY, GO_VERSION
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


def test_tunnel_address_mapping_matches_twinpanel_core():
    network, iran_ip, exit_ip = _tunnel_addresses(5)
    assert network == "10.64.0.20/30"
    assert iran_ip == "10.64.0.21"
    assert exit_ip == "10.64.0.22"


def test_iran_relay_installs_listener_on_iran_and_upstream_on_tunnel_ip():
    iran = SimpleNamespace(public_ip="203.0.113.10")
    script = _install_script(iran, "ir-dns.example.com", "10.64.0.22", 443)
    assert DNSTT_REPOSITORY in script
    assert DNSTT_COMMIT in script
    assert GO_VERSION in script
    assert SERVICE_NAME in script
    assert STATE_DIR in script
    assert "-udp 203.0.113.10:53" in script
    assert "ir-dns.example.com 10.64.0.22:443" in script
    assert "ir-dns.example.com 127.0.0.1:443" not in script
    assert "systemctl restart twinpanel-dnstt-iran.service" in script


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
