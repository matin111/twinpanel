import base64
import json
from types import SimpleNamespace

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.dns_emergency_models import DnsEmergencySetting
from app.routers.netmod_dns import NETMOD_AES_KEY, SSH_USER
from app.routers.netmod_dns_performance_v226 import (
    DEFAULT_DNSTT_MTU,
    MAX_DNSTT_MTU,
    MIN_DNSTT_MTU,
    PERFORMANCE_DROPIN_PATH,
    RESOLVER_PRESETS,
    _mtu_apply_script,
    _performance_status_script,
    _profile_payload,
    _validated_mtu,
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


def test_resolver_presets_are_unique_ipv4_client_variants():
    values = [resolver for _, resolver in RESOLVER_PRESETS]
    assert values == ["8.8.8.8", "1.1.1.1", "9.9.9.9", "208.67.222.222"]
    assert len(values) == len(set(values))

    node = SimpleNamespace(id=6, name="tr", public_ip="203.0.113.8")
    setting = DnsEmergencySetting(
        node_id=6,
        tunnel_domain="t.example.com",
        public_key="b" * 64,
        runtime_status="online",
    )
    names = []
    for _, resolver in RESOLVER_PRESETS:
        payload = _profile_payload(
            node=node,
            setting=setting,
            resolver=resolver,
            password="strong-password",
        )
        names.append(payload["ps"])
        assert payload["addr"] == resolver
        assert payload["user"] == SSH_USER
        assert payload["pass"] == "strong-password"
    assert len(names) == len(set(names))


def test_mtu_validation_is_bounded_and_keeps_dnstt_default():
    assert DEFAULT_DNSTT_MTU == 1232
    assert _validated_mtu(MIN_DNSTT_MTU) == 512
    assert _validated_mtu(DEFAULT_DNSTT_MTU) == 1232
    assert _validated_mtu(MAX_DNSTT_MTU) == 1452
    for value in (MIN_DNSTT_MTU - 1, MAX_DNSTT_MTU + 1):
        try:
            _validated_mtu(value)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 422
        else:
            raise AssertionError(f"unsafe MTU unexpectedly accepted: {value}")


def test_mtu_override_is_rollback_safe_and_default_removes_override():
    performance = _mtu_apply_script(
        public_ip="203.0.113.8",
        domain="t.example.com",
        mtu=1400,
    )
    assert PERFORMANCE_DROPIN_PATH in performance
    assert "ExecStart=" in performance
    assert "-mtu 1400" in performance
    assert "203.0.113.8:5353" in performance
    assert "t.example.com 127.0.0.1:2222" in performance
    assert "rollback()" in performance
    assert "MTU_APPLY_RESTART_FAILED" in performance
    assert "MTU_APPLY_SERVICE_INACTIVE" in performance
    assert "MTU_APPLY_LISTENER_MISSING" in performance
    assert "effective MTU" in performance
    assert "FORMERR: requester payload size" in performance

    default = _mtu_apply_script(
        public_ip="203.0.113.8",
        domain="t.example.com",
        mtu=DEFAULT_DNSTT_MTU,
    )
    assert "rm -f \"$DROPIN\"" in default
    assert "-mtu 1232" in default  # rollback-safe candidate command remains deterministic


def test_performance_status_reports_real_dnstt_signals():
    script = _performance_status_script(public_ip="203.0.113.8")
    assert "systemctl is-active" in script
    assert "203.0.113.8:5353" in script
    assert "effective MTU" in script
    assert "FORMERR: requester payload size" in script
    assert "MTU=" in script
    assert "EFFECTIVE_MTU=" in script
    assert "FORMERR_RECENT=" in script


def test_performance_router_exposes_status_profiles_and_safe_mtu_apply():
    paths = {(route.path, ",".join(sorted(route.methods or []))) for route in router.routes}
    assert ("/v1/settings/vpn/netmod-dns/{node_id}/performance", "GET") in paths
    assert ("/v1/settings/vpn/netmod-dns/{node_id}/performance/profiles", "GET") in paths
    assert ("/v1/settings/vpn/netmod-dns/{node_id}/performance/mtu", "POST") in paths
