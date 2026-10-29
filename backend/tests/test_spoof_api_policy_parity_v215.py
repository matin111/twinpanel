import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v215_api_kernel_bootstrap_loads_spoof_policy_first():
    router = read("backend/app/routers/modern_transports.py")
    registry = read("backend/app/kernel_transport_registry_v209.py")

    ast.parse(router)
    ast.parse(registry)

    assert "apply_kernel_transport_registry_v209()" in router
    assert (
        "from .spoof_candidate_policy_v202 import "
        "apply_spoof_candidate_policy_v202"
    ) in registry

    v202 = registry.index("apply_spoof_candidate_policy_v202()")
    v217 = registry.index("apply_spoof_icmp_scoped_echo_v217()", v202)
    tp6 = registry.index("apply_tp6_candidate_registry_v208()", v217)
    membership = registry.index("_ensure_smart_membership()", tp6)
    assert v202 < v217 < tp6 < membership


def test_v215_preserves_v202_v206_v213_v214_ordering():
    policy = read("backend/app/spoof_candidate_policy_v202.py")

    ast.parse(policy)

    v206 = policy.index("apply_spoof_underlay_guard_v206()")
    v213 = policy.index("apply_spoof_last_error_recovery_v212()")
    v214 = policy.index("apply_spoof_reverse_icmp_fallback_v214()")
    assert v206 < v213 < v214


def test_v215_is_bootstrap_only_and_does_not_redefine_dataplane():
    registry = read("backend/app/kernel_transport_registry_v209.py")

    assert '"spoof_policy=v202-v214+v217 "' in registry
    assert "spoof_reverse_icmp_fallback_v214.py" not in registry
    assert "udp dport set" not in registry
    assert "--send-transport" not in registry
    assert "--recv-transport" not in registry
    assert "net.ipv4.icmp_echo_ignore_all" not in registry
