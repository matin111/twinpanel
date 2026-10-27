from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    center = read("components/tunnel-control-center-v1.tsx")
    simple = read("components/tunnels-simple-runtime.tsx")
    advanced = read("components/smart-transports-runtime-v25.tsx")
    css = read("components/tunnel-control-center-v1.module.css")

    assert "TWINPANEL_TUNNEL_CONTROL_CENTER_V1" in center
    assert "TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V1" in simple
    assert "TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V1" in advanced

    # Both public admin tunnel entrypoints must converge on exactly one surface.
    assert 'import {TunnelControlCenterV1} from "./tunnel-control-center-v1"' in simple
    assert 'return <TunnelControlCenterV1/>' in simple
    assert 'import {TunnelControlCenterV1} from "./tunnel-control-center-v1"' in advanced
    assert 'return <TunnelControlCenterV1/>' in advanced

    # Creation remains owned by the existing managed backend orchestration.
    assert "legacyControlApi.createManagedTunnel" in center
    assert 'transport:"auto"' in center
    assert "setSelectedId(id)" in center

    # Every operation is data-driven from selectedId/name, never a special tunnel ID.
    forbidden = (
        "selectedId===5",
        "selectedId===6",
        "selectedId===8",
        "selectedId == 5",
        "selectedId == 6",
        "selectedId == 8",
        "tunnel.id===5",
        "tunnel.id===6",
        "tunnel.id===8",
        "tunnel.id == 5",
        "tunnel.id == 6",
        "tunnel.id == 8",
    )
    for token in forbidden:
        assert token not in center, token

    # Manual and Auto controls are generic for every tunnel. Manual is visible
    # even before eligibility and is disabled with a reason instead of hidden.
    assert 'modernTransportApi.setMode(selectedId,"auto")' in center
    assert 'modernTransportApi.setMode(selectedId,"manual",name)' in center
    assert "disabled={Boolean(busy)||isActive||!row.selectable}" in center
    assert "row.selectable&&<button" not in center
    assert 'title={reason}' in center

    # One candidate lane handles install/probe/remove for the selected pair.
    assert "modernTransportApi.install(selectedId,name)" in center
    assert "modernTransportApi.probe(selectedId,name)" in center
    assert "modernTransportApi.remove(selectedId,name)" in center

    # The control center owns the responsive visual system rather than adding
    # per-tunnel CSS fragments.
    assert ".workspace" in css
    assert ".topology" in css
    assert ".candidateGrid" in css
    assert "@media(max-width:780px)" in css

    print("tunnel-control-center-v1 smoke: OK")


if __name__ == "__main__":
    main()
