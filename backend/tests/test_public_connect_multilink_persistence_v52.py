from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V52 = ROOT / "app" / "routers" / "public_connection_multilink_persistence_v52.py"
CANONICAL = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"


def test_v52_promotes_v51_card_without_refetching_delivery() -> None:
    source = V52.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_MULTILINK_PERSISTENCE_V52" in source
    assert "card.classList.remove('v51-multi-card')" in source
    assert "card.classList.add('v52-multi-card')" in source
    assert "panel.dataset.v52Multilink='1'" in source
    assert "fetch(" not in source


def test_v52_keeps_v2ray_and_retires_competing_legacy_surfaces() -> None:
    source = V52.read_text(encoding="utf-8")

    assert "'openvpn','wireguard','v2ray','hysteria2'" in source
    assert "[data-v44-v2ray-multi=\"1\"]" in source
    assert ".v49-v2ray-summary" in source
    assert ".v49-v2ray-groups" in source
    assert "MutationObserver" in source
    assert "window.setTimeout(reconcileAll,1250)" in source
    assert "window.setTimeout(reconcileAll,1800)" in source


def test_v52_is_composed_after_v51_final_authority() -> None:
    source = CANONICAL.read_text(encoding="utf-8")

    assert "refine_public_connection_multilink_authority_v51" in source
    assert "refine_public_connection_multilink_persistence_v52" in source
    v51_call = source.index("source = refine_public_connection_multilink_authority_v51(source)")
    v52_call = source.index("return refine_public_connection_multilink_persistence_v52(source)")
    assert v51_call < v52_call
