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
    # reaches guarded V26 after all data/profile refiners. V26 then delegates to
    # the single V34 customer-facing authority.
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
    assert "return refine_public_connection_forward_v34(source)" in source


def test_android_direct_app_assets_are_verified_and_architecture_specific():
    # Direct install assets are centralized in V34 rather than hardcoded inside
    # the phone cleanup layer. This keeps Windows/mobile app delivery in one
    # device-aware resolver and avoids project landing pages.
    source = _text("backend/app/routers/public_connection_app_download_v34.py")

    assert 'GitHubAsset("KaringX/karing", r"_android_arm64-v8a\\.apk$")' in source
    assert "_android_arm\\.apk$" not in source
    assert 'GitHubAsset("amnezia-vpn/amneziawg-android", r"AmneziaWG-.*\\.apk$")' in source
    assert '"/app-download/{app}/{platform}"' in source
    assert "browser_download_url" in source
    assert "karing.app/en/quickstart" not in source
    assert "How-to-install-Hiddify-app" not in source


if __name__ == "__main__":
    test_public_hub_retires_duplicate_mobile_renderers_but_keeps_v18_endpoint_registration()
    test_canonical_mobile_v26_blocks_legacy_surfaces_and_explanatory_copy()
    test_android_direct_app_assets_are_verified_and_architecture_specific()
    print("PUBLIC_CONNECTION_CANONICAL_MOBILE_V319=PASS")
