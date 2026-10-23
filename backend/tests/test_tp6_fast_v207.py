from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def tp6_source() -> str:
    return "\n".join(
        read(path)
        for path in (
            "backend/app/transport_candidates/tp6_fast_contract.py",
            "backend/app/transport_candidates/tp6_fast_ipv6.py",
            "backend/app/transport_candidates/tp6_fast_kernel.py",
            "backend/app/transport_candidates/tp6_fast.py",
        )
    )


def test_tp6_fast_is_active_but_explicit_install_only():
    registry = read("backend/app/transport_candidates/__init__.py")
    policy = read("backend/app/spoof_candidate_policy_v202.py")

    assert '"tp6_fast"] = TP6_FAST_SPEC' in registry
    assert '"tp6_fast"] = tp6_fast.install' in registry
    assert 'octet=249' in registry
    assert 'interface_prefix="tp6"' in registry
    assert 'table = 34000 +' in registry
    assert 'smart.AUTO_INSTALL_NAMES = ("tp27_fast",)' in policy
    assert '"tp6_fast"' in policy
    assert 'tp6_install=explicit-only' in policy


def test_tp6_fast_is_ipv6_outer_and_kernel_only():
    source = tp6_source()

    for token in (
        'NAME = "tp6_fast"',
        'DISCOVERY_TARGET = "2606:4700:4700::1111"',
        'PROFILE_ORDER = ("ip6gre", "ipip6")',
        "type ip6gre",
        "mode ipip6",
        "ip -6 route get",
        "ping -6",
        '"outer_family": "ipv6"',
        '"ipv6_discovery": "automatic"',
        "common.probe(",
        "tp6_all_profiles_failed",
    ):
        assert token in source, token

    # No userspace carrier/download and no mutation of Node.public_ip.
    assert "curl -L" not in source
    assert "wget " not in source
    assert "public_ip =" not in source


def test_tp6_fast_preserves_existing_production_paths():
    source = tp6_source()
    registry = read("backend/app/transport_candidates/__init__.py")
    base = read("backend/app/transport_candidates/registry_v206.py")

    # TP6 owns a distinct inner network/table; TP27 and Spoof base contracts remain intact.
    assert 'octet=249' in registry
    assert 'table = 34000 +' in registry
    assert 'octet=253' in base
    assert 'table = 29000 +' in base
    assert 'octet=250' in base
    assert 'table = 33000 +' in base

    # Installer only marks its own candidate; manager/API retains switching authority.
    assert "common.mark(" in source
    assert "active_transport" not in source
    assert "preferred_transport" not in source
    assert "uninstall_transport" not in source


def test_tp6_fast_fails_closed_on_ipv6_prerequisites_and_has_two_profiles():
    source = tp6_source()

    assert "tp6_global_ipv6_missing" in source
    assert "tp6_peer_ipv6_route_missing" in source
    assert "for profile in PROFILE_ORDER:" in source
    assert "await reset_pair(ci, ce, rt)" in source
    assert 'status="failed"' in source
    assert "raise RuntimeError(msg) from exc" in source
