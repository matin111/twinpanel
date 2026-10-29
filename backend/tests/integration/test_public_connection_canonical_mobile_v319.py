from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_hub_retires_duplicate_mobile_renderers_but_keeps_v18_endpoint_registration():
    hub = _text("backend/app/routers/public_connection_hub_live_v5.py")

    assert "refine_public_connection_hub_v9" not in hub
    assert "refine_public_connection_mobile_protocols_v17" not in hub
    assert "refine_public_connection_mobile_server_inventory_v18(source)" not in hub
    assert "refine_public_connection_protocol_uri_details_v21" not in hub

    # V18 still registers its read-only inventory route into the V16 router.
    assert "public_connection_mobile_server_inventory_v18 as _public_connection_mobile_server_inventory_v18" in hub

    # Desktop/classic action hygiene remains, while the final mobile presentation
    # is an explicit canonical-only refinement after all data/profile refiners.
    assert "refine_public_connection_protocol_actions_v20(source)" in hub
    assert "refine_public_connection_canonical_mobile_v26(source)" in hub
    assert hub.index("refine_public_connection_xray_profiles_v48(source)") < hub.index(
        "refine_public_connection_canonical_mobile_v26(source)"
    )


def test_canonical_mobile_v26_blocks_legacy_surfaces_and_explanatory_copy():
    source = _text("backend/app/routers/public_connection_canonical_mobile_v26.py")

    assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in source
    assert ".v9-mobile-stack" in source
    assert ".v17-mobile-stack" in source
    assert ".v9-apps-drawer" in source
    assert ".v8-app-launch" in source
    assert "body.v24-ready .section-head" in source
    assert "body.v24-ready .apps .tools" in source
    assert "content:none!important" in source
    assert "data.tpCanonicalMobile" not in source
    assert "document.body.dataset.tpCanonicalMobile='v26'" in source


def test_android_direct_app_assets_are_verified_and_architecture_specific():
    source = _text("backend/app/routers/public_connection_canonical_mobile_v26.py")

    assert (
        "https://github.com/KaringX/karing/releases/download/v1.2.25.2802/"
        "karing_1.2.25.2802_android_arm64-v8a.apk"
    ) in source
    assert "karing_1.2.25.2802_android_arm.apk" not in source
    assert (
        "https://github.com/amnezia-vpn/amneziawg-android/releases/download/"
        "v3.1.20260814/AmneziaWG-3.1.202060814.apk"
    ) in source


if __name__ == "__main__":
    test_public_hub_retires_duplicate_mobile_renderers_but_keeps_v18_endpoint_registration()
    test_canonical_mobile_v26_blocks_legacy_surfaces_and_explanatory_copy()
    test_android_direct_app_assets_are_verified_and_architecture_specific()
    print("PUBLIC_CONNECTION_CANONICAL_MOBILE_V319=PASS")
