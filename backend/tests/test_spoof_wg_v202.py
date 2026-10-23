from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def registry_source() -> str:
    # V207 keeps the immutable rc.206 registry as the base and adds TP6 through
    # a small additive overlay in __init__.py. Validate the complete contract.
    return (
        read("backend/app/transport_candidates/registry_v206.py")
        + "\n"
        + read("backend/app/transport_candidates/__init__.py")
    )


def test_spoof_wg_registry_is_narrow_and_cleanup_compatible():
    registry = registry_source()
    base = read("backend/app/transport_candidates/registry_v206.py")

    assert '"spoof_wg": SPOOF_WG_SPEC' in registry
    assert '"tp27_fast": TP27_SPEC' in registry
    assert '"spoof_wg": spoof_wg.install' in registry

    active_block = base.split("ACTIVE_SPECS = {", 1)[1].split("}", 1)[0]
    assert '"tp27_fast"' in active_block
    assert '"spoof_wg"' in active_block
    assert '"tp27_masque"' not in active_block
    assert '"tp27_tcp_direct"' not in active_block

    installers = base.split("INSTALLERS = {", 1)[1].split("}", 1)[0]
    assert '"tp27_fast"' in installers
    assert '"spoof_wg"' in installers
    assert '"tp27_masque"' not in installers
    assert '"tp27_tcp_direct"' not in installers

    # Retired source handlers remain present for scoped uninstall/cleanup.
    assert 'elif name == "tp27_masque"' in registry
    assert 'elif name == "tp27_tcp_direct"' in registry


def test_spoof_wg_runtime_contract():
    registry = registry_source()
    spoof = read("backend/app/transport_candidates/spoof_wg.py")

    assert 'octet=250' in registry
    assert 'interface_prefix="tpsp"' in registry
    assert 'table = 33000 +' in registry

    for token in (
        'UPSTREAM_VERSION = "v3.1.0-beta.0"',
        'UPSTREAM_SOURCE_SHA = "ba29f0c8e22da5a905a74a8137e01a22f0443e60"',
        'UPSTREAM_ARTIFACT_SHA256 = "4ba5597568607e864fb6d5ba4f13bac91a50456da5696d99463d6375ce2a3697"',
        'SEND_TRANSPORT = "tcp"',
        'RECV_TRANSPORT = "udp"',
        'ip link add "$IFACE" type wireguard',
        '--send-transport {SEND_TRANSPORT}',
        '--recv-transport {RECV_TRANSPORT}',
        '--forward 127.0.0.1:',
        'configuration_required',
        'xdp": False',
    ):
        assert token in spoof, token


def test_spoof_policy_is_final_and_never_auto_installs_spoof():
    manager = read("backend/app/tunnel_transport_manager_v12.py")
    policy = read("backend/app/spoof_candidate_policy_v202.py")

    assert manager.index("apply_stale_candidate_install_recovery_v200()") < manager.index(
        "apply_spoof_candidate_policy_v202()"
    )
    assert 'smart.AUTO_INSTALL_NAMES = ("tp27_fast",)' in policy
    assert 'smart.CANDIDATE_NAMES = ACTIVE' in policy
    assert 'smart.ALL_AUTO_NAMES = ACTIVE' in policy

    for retired in (
        "tp27_masque",
        "tp27_mieru_tcp",
        "tp27_tcp_direct",
    ):
        assert f'"{retired}"' in policy


def test_spoof_configuration_is_backend_authoritative():
    router = read("backend/app/routers/modern_transports.py")
    api = read("lib/modern-transport-api.ts")
    ui = read("components/smart-transports-runtime-v25.tsx")

    assert '@router.put("/{tunnel_id}/modern-transports/spoof_wg/config")' in router
    assert "spoof_wg_configuration_required" in read(
        "backend/app/transport_candidates/spoof_wg.py"
    )
    assert 'configuration_required": True' in router
    assert "configureSpoof" in api
    assert 'spoof_wg' in api
    assert "saveSpoof" in ui
    assert "Iran spoof source IP" in ui
    assert "Exit spoof source IP" in ui
    assert "The active production path cannot be removed here." in ui


def test_publisher_pins_upstream_core_and_license_is_present():
    publisher = read(".github/workflows/publish-prebuilt-release.yml")
    notice = read("third_party/spoof-tunnel/README.md")
    license_text = read("third_party/spoof-tunnel/LICENSE")

    expected = "4ba5597568607e864fb6d5ba4f13bac91a50456da5696d99463d6375ce2a3697"
    assert "Bundle verified Spoof Tunnel core" in publisher
    assert "v3.1.0-beta.0" in publisher
    assert expected in publisher
    assert "spoof-tunnel-linux-x86_64.sha256" in publisher
    assert expected in notice
    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
