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


def test_tp6_fast_registry_extension_preserves_v202_source_contract():
    registry = read("backend/app/transport_candidates/__init__.py")
    extension = read("backend/app/tp6_candidate_registry_v208.py")
    policy = read("backend/app/spoof_candidate_policy_v202.py")
    unified = read("backend/app/unified_l3_candidate_registry_v79.py")

    assert '"tp27_fast": TP27_SPEC' in registry
    assert '"spoof_wg": SPOOF_WG_SPEC' in registry
    assert '"tp27_fast": tp27_fast.install' in registry
    assert '"spoof_wg": spoof_wg.install' in registry
    assert "registry_v206" not in registry

    assert 'ACTIVE = frozenset({"tp27_fast", "spoof_wg"})' in policy
    assert 'smart.AUTO_INSTALL_NAMES = ("tp27_fast",)' in policy
    assert "smart.CANDIDATE_NAMES = ACTIVE" in policy
    assert "smart.ALL_AUTO_NAMES = ACTIVE" in policy

    assert 'MARKER = "TWINPANEL_TP6_CANDIDATE_REGISTRY_V208"' in extension
    assert 'candidates.ACTIVE_SPECS["tp6_fast"] = TP6_FAST_SPEC' in extension
    assert 'candidates.INSTALLERS["tp6_fast"] = tp6_fast.install' in extension
    assert 'transport="tp6_fast"' in extension
    assert 'octet=249' in extension
    assert 'interface_prefix="tp6"' in extension
    assert 'table = 34000 +' in extension
    assert "apply_tp6_candidate_registry_v208()" in unified
    assert "apply_tp6_candidate_registry_v208()" in policy
    assert 'smart.CANDIDATE_NAMES = frozenset((*smart.CANDIDATE_NAMES, "tp6_fast"))' in policy
    assert 'smart.ALL_AUTO_NAMES = frozenset((*smart.ALL_AUTO_NAMES, "tp6_fast"))' in policy
    assert "tp6_managed=explicit-install-only" in policy


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

    assert "curl -L" not in source
    assert "wget " not in source
    assert "public_ip =" not in source


def test_tp6_fast_preserves_existing_production_paths():
    source = tp6_source()
    registry = read("backend/app/transport_candidates/__init__.py")
    extension = read("backend/app/tp6_candidate_registry_v208.py")

    assert 'octet=249' in extension
    assert 'table = 34000 +' in extension

    assert 'octet=253' in registry
    assert 'table = 29000 +' in registry
    assert 'octet=250' in registry
    assert 'table = 33000 +' in registry

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
