import base64
import json
from types import SimpleNamespace

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.dns_emergency_models import DnsEmergencySetting
from app.routers.netmod_dns import (
    DEFAULT_RESOLVER,
    DNSTT_PORT,
    NAT_SERVICE,
    NETMOD_AES_KEY,
    SSH_PORT,
    SSH_SERVICE,
    SSH_USER,
    _install_script,
    _netmod_encrypt_payload,
    _netmod_link,
    _resolver,
    router,
)


def decrypt_nm_dns(value: str) -> dict[str, str]:
    assert value.startswith("nm-dns://")
    ciphertext = base64.b64decode(value.removeprefix("nm-dns://"))
    cipher = Cipher(algorithms.AES(NETMOD_AES_KEY), modes.ECB())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    raw = unpadder.update(padded) + unpadder.finalize()
    return json.loads(raw.decode("utf-8"))


def test_nm_dns_uses_verified_aes_ecb_envelope_and_schema():
    payload = {
        "ps": "TwinPanel tr",
        "addr": "8.8.8.8",
        "ns": "t.example.com",
        "pubkey": "a" * 64,
        "user": "tpnetmod",
        "pass": "secret-value",
    }
    encoded = _netmod_encrypt_payload(payload)
    assert decrypt_nm_dns(encoded) == payload
    assert len(NETMOD_AES_KEY) == 16


def test_nm_dns_link_maps_dnstt_and_internal_ssh_fields():
    node = SimpleNamespace(id=6, name="tr", public_ip="203.0.113.8")
    setting = DnsEmergencySetting(
        node_id=6,
        tunnel_domain="t.example.com",
        public_key="b" * 64,
        runtime_status="online",
    )
    link, payload = _netmod_link(
        node=node,
        setting=setting,
        resolver=DEFAULT_RESOLVER,
        password="strong-password",
    )
    assert link.startswith("nm-dns://")
    assert payload == {
        "ps": "TwinPanel tr",
        "addr": "8.8.8.8",
        "ns": "t.example.com",
        "pubkey": "b" * 64,
        "user": SSH_USER,
        "pass": "strong-password",
    }
    assert decrypt_nm_dns(link) == payload


def test_resolver_is_fail_closed_and_ipv4_only():
    assert _resolver("8.8.8.8") == "8.8.8.8"
    for value in ("dns.google", "8.8.8.8:53", "2001:4860:4860::8888"):
        try:
            _resolver(value)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 422
        else:
            raise AssertionError(f"resolver unexpectedly accepted: {value}")


def test_install_runtime_is_private_ssh_plus_dnstt_plus_exact_udp53_redirect():
    script = _install_script(public_ip="203.0.113.8", domain="t.example.com")

    assert f"Port {SSH_PORT}" in script
    assert "ListenAddress 127.0.0.1" in script
    assert f"AllowUsers {SSH_USER}" in script
    assert "AllowTcpForwarding yes" in script
    assert "PermitRootLogin no" in script
    assert "GatewayPorts no" in script
    assert f"127.0.0.1:{SSH_PORT}" in script

    assert f"203.0.113.8:{DNSTT_PORT}" in script
    assert "t.example.com" in script
    assert "--dport 53" in script
    assert f"TO_PORT={DNSTT_PORT}" in script
    assert '--to-ports "$TO_PORT"' in script
    assert "-d \"$IP\"" in script
    assert "TwinPanel-NetMod-DNS" in script

    assert SSH_SERVICE in script
    assert NAT_SERVICE in script
    assert "systemctl disable --now twinpanel-dnstt.service" in script
    assert "twinpanel-dnstt-iran.service" in script
    assert "twinpanel-masterdnsvpn.service" in script


def test_router_exposes_single_netmod_lifecycle_and_secret_config():
    paths = {(route.path, ",".join(sorted(route.methods or []))) for route in router.routes}
    assert ("/v1/settings/vpn/netmod-dns", "GET") in paths
    assert ("/v1/settings/vpn/netmod-dns/{node_id}/install", "POST") in paths
    assert ("/v1/settings/vpn/netmod-dns/{node_id}/health", "POST") in paths
    assert ("/v1/settings/vpn/netmod-dns/{node_id}/config", "GET") in paths
    assert ("/v1/settings/vpn/netmod-dns/{node_id}", "DELETE") in paths
