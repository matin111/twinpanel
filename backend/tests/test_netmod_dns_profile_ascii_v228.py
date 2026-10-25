from types import SimpleNamespace

from app.dns_emergency_models import DnsEmergencySetting
from app.routers.netmod_dns import SSH_USER
from app.routers.netmod_dns_performance_v226 import RESOLVER_PRESETS, _profile_payload


def test_netmod_performance_profile_names_are_ascii_safe():
    node = SimpleNamespace(id=6, name="ترکیه · tr", public_ip="203.0.113.8")
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
        assert payload["ps"] == f"TwinPanel-6-{resolver}"
        assert payload["ps"].isascii()
        assert payload["addr"] == resolver
        assert payload["user"] == SSH_USER
        assert payload["pass"] == "strong-password"

    assert len(names) == len(set(names))
