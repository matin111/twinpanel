from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    routed = read("components/routed-page-client-v2.tsx")
    tunnel = read("components/tunnel-protocol-runtime-v307.tsx")
    styles = read("components/tunnel-protocol-runtime-v307.module.css")
    smart = read("components/smart-transports-runtime-v27.tsx")

    assert 'routeKey==="admin/tunnels"' in routed
    assert '<TunnelProtocolRuntimeV307/>' in routed
    assert 'routeKey==="admin/tunnel-transports"' in routed
    assert '<SmartTransportsRuntimeV27/>' in routed

    assert "TWINPANEL_TUNNEL_MANAGEMENT_POPUP_V307" in tunnel
    assert "legacyAdminApi.classicProtocols()" in tunnel
    assert "modernTransportApi.protocolInventory()" in tunnel
    assert "ensureClassicProtocol" in tunnel
    assert "/v1/settings/vpn/modern-protocols/" in tunnel
    assert 'method:"DELETE"' in tunnel
    assert "TunnelServiceConnectionsPanel" in tunnel
    assert 'window.location.href="/admin/tunnel-transports"' in tunnel

    # Detailed management must live behind the modal, not as a long inline
    # protocol/service section below the tunnel list.
    assert "manageOpen" in tunnel
    assert "openManage" in tunnel
    assert "<Modal wide" in tunnel
    assert "styles.tunnelGrid" in tunnel
    assert "styles.modalCard" in tunnel
    assert ".tunnelGrid" in styles
    assert ".modalCard" in styles

    # Tunnel and Smart Transports remain separate route authorities.
    assert "TunnelProtocolRuntimeV307" not in smart

    print("tunnel protocol page separation/popup v307: ok")


if __name__ == "__main__":
    main()
