from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    routed = read("components/routed-page-client-v2.tsx")
    tunnel = read("components/tunnel-protocol-runtime-v298.tsx")
    smart = read("components/smart-transports-runtime-v27.tsx")

    assert 'routeKey==="admin/tunnels"' in routed
    assert '<TunnelProtocolRuntimeV298/>' in routed
    assert 'routeKey==="admin/tunnel-transports"' in routed
    assert '<SmartTransportsRuntimeV27/>' in routed

    assert "TWINPANEL_TUNNEL_PROTOCOL_MANAGEMENT_V298" in tunnel
    assert "legacyAdminApi.classicProtocols()" in tunnel
    assert "modernTransportApi.protocolInventory()" in tunnel
    assert "ensureClassicProtocol" in tunnel
    assert "/v1/settings/vpn/modern-protocols/" in tunnel
    assert 'method:"DELETE"' in tunnel
    assert "TunnelServiceConnectionsPanel" in tunnel
    assert 'window.location.href="/admin/tunnel-transports"' in tunnel

    # Tunnel and Smart Transports must remain separate route authorities.
    assert "TunnelProtocolRuntimeV298" not in smart

    print("tunnel protocol page separation v298: ok")


if __name__ == "__main__":
    main()
