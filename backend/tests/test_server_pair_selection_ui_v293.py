from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_server_pair_client_is_register_only_and_never_provisions():
    client = read("lib/tunnel-server-pair-api.ts")

    assert "TWINPANEL_SERVER_PAIR_SELECTION_NO_INSTALL_V293" in client
    assert 'fetch("/v1/tunnels/register"' in client
    assert 'fetch("/v1/tunnels/create-managed"' not in client
    assert "/modern-transports/" not in client
    assert "/install" not in client
    assert 'is_active:false' in client


def test_unified_control_center_surfaces_server_selection_separately_from_new_tunnel():
    ui = read("components/tunnel-control-center-v1.tsx")

    assert "TWINPANEL_SERVER_PAIR_SELECTION_NO_INSTALL_V293" in ui
    assert "TunnelServerPairSelectorV293" in ui
    assert "onServerPairSelected" in ui
    assert "هیچ Tunnel/Transport نصب یا بازسازی نشد" in ui

    # Full provisioning remains a separate, explicit New Tunnel action.
    assert "legacyControlApi.createManagedTunnel" in ui
    assert "ساخت و آماده‌سازی Tunnel" in ui


def test_server_selector_explains_no_install_contract():
    selector = read("components/tunnel-server-pair-selector-v293.tsx")

    assert "TWINPANEL_SERVER_PAIR_SELECTOR_UI_V293" in selector
    assert "tunnelServerPairApi.select" in selector
    assert "انتخاب سرور بدون نصب مجدد" in selector
    assert "هیچ Tunnel/Transport، Agent، WireGuard، SSH یا Firewall نصب یا بازسازی نمی‌شود" in selector


def test_transport_route_is_only_an_adapter_to_the_same_control_center():
    legacy_route = read("components/smart-transports-runtime-v25.tsx")

    assert "TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V293" in legacy_route
    assert 'import {TunnelControlCenterV1}' in legacy_route
    assert "return <TunnelControlCenterV1/>;" in legacy_route
    assert "modernTransportApi" not in legacy_route
