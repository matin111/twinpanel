from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    tunnel = read("components/tunnel-protocol-runtime-v298.tsx")
    routed = read("components/routed-page-client-v2.tsx")

    assert "TWINPANEL_TUNNEL_PROTOCOL_MANAGEMENT_V299" in tunnel
    assert 'useState<ProtocolScope>("installed")' in tunnel
    assert 'useState(false)' in tunnel
    assert 'setProtocolScope("installed")' in tunnel
    assert 'setConnectionsOpen(false)' in tunnel
    assert 'protocolScope==="issues"' in tunnel
    assert 'protocolScope==="all"' in tunnel
    assert 'protocolSearch.trim().toLowerCase()' in tunnel
    assert 'connectionsOpen?<TunnelServiceConnectionsPanel' in tunnel
    assert 'maxHeight:"430px"' in tunnel
    assert 'maxHeight:"520px"' in tunnel

    # The density refine must not merge tunnel management back into Smart Transports.
    assert 'routeKey==="admin/tunnels"' in routed
    assert '<TunnelProtocolRuntimeV298/>' in routed
    assert 'routeKey==="admin/tunnel-transports"' in routed

    print("tunnel page density v299: ok")


if __name__ == "__main__":
    main()
