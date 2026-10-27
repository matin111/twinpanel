from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    center = read("components/tunnel-control-center-v1.tsx")
    simple = read("components/tunnels-simple-runtime.tsx")
    advanced = read("components/smart-transports-runtime-v25.tsx")
    api = read("lib/modern-transport-api.ts")
    css = read("components/tunnel-control-center-v1.module.css")

    assert "TWINPANEL_TUNNEL_CONTROL_CENTER_V1" in center
    assert "TWINPANEL_MANUAL_CUTOVER_ELIGIBILITY_UI_V289" in center
    assert "TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V1" in simple
    assert "TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V1" in advanced

    # Both public admin tunnel entrypoints converge on exactly one surface.
    assert 'import {TunnelControlCenterV1} from "./tunnel-control-center-v1"' in simple
    assert 'return <TunnelControlCenterV1/>' in simple
    assert 'import {TunnelControlCenterV1} from "./tunnel-control-center-v1"' in advanced
    assert 'return <TunnelControlCenterV1/>' in advanced

    # Creation remains owned by the existing managed backend orchestration.
    assert "legacyControlApi.createManagedTunnel" in center
    assert 'transport:"auto"' in center
    assert "setSelectedId(id)" in center

    # Every operation is data-driven from selectedId/name, never a special ID.
    forbidden = (
        "selectedId===5", "selectedId===6", "selectedId===8",
        "selectedId == 5", "selectedId == 6", "selectedId == 8",
        "tunnel.id===5", "tunnel.id===6", "tunnel.id===8",
        "tunnel.id == 5", "tunnel.id == 6", "tunnel.id == 8",
    )
    for token in forbidden:
        assert token not in center, token

    # Manual and Auto are intentionally separate contracts. Manual readiness is
    # based on live health, not SmartAuto's 60-second qualification gate.
    for field in (
        "manual_selectable?:boolean;",
        "manual_block_reason?:string|null;",
        "manual_selection_requires_fresh_probe?:boolean;",
    ):
        assert field in api
    assert 'modernTransportApi.setMode(selectedId,"auto")' in center
    assert 'modernTransportApi.setMode(selectedId,"manual",name)' in center
    assert "const manualSelectable=Boolean(row.manual_selectable);" in center
    assert "disabled={Boolean(busy)||isActive||!manualSelectable}" in center
    assert "row.selectable&&<button" not in center
    assert "شرط ۶۰ ثانیه فقط برای Smart Auto است" in center
    assert "fresh full health probe" in center
    assert "both-Agent acceptance" in center
    assert "row.manual_block_reason" in center

    # One candidate lane handles install/probe/remove for the selected pair.
    assert "modernTransportApi.install(selectedId,name)" in center
    assert "modernTransportApi.probe(selectedId,name)" in center
    assert "modernTransportApi.remove(selectedId,name)" in center

    # Responsive visual system belongs to the shared control center.
    assert ".workspace" in css
    assert ".topology" in css
    assert ".candidateGrid" in css
    assert "@media(max-width:780px)" in css

    print("tunnel-control-center-v1 smoke: OK")


if __name__ == "__main__":
    main()
