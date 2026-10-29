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
    assert "public_connection_mobile_server_inventory_v18 as _public_connection_mobile_server_inventory_v18" in hub
    assert "refine_public_connection_protocol_actions_v20(source)" in hub
    assert "refine_public_connection_canonical_mobile_v26(source)" in hub
    assert hub.index("refine_public_connection_xray_profiles_v48(source)") < hub.index(
        "refine_public_connection_canonical_mobile_v26(source)"
    )


def test_canonical_mobile_v26_composes_v36_v34_v37_v38_v39_without_legacy_stack():
    source = _text("backend/app/routers/public_connection_canonical_mobile_v26.py")
    v36 = _text("backend/app/routers/public_connection_mobile_compact_v36.py")
    v37 = _text("backend/app/routers/public_connection_final_presentation_v37.py")
    v38 = _text("backend/app/routers/public_connection_reference_layout_v38.py")
    v39 = _text("backend/app/routers/public_connection_ha_multiserver_v39.py")

    assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in source
    assert ".v9-mobile-stack" in source
    assert ".v17-mobile-stack" in source
    assert ".v9-apps-drawer" in source
    assert ".v8-app-launch" in source
    assert "body.v24-ready .section-head" in source
    assert "content:none!important" in source
    assert "document.body.dataset.tpCanonicalMobile='v26'" in source

    assert "platform==='android'||platform==='ios'" in source
    assert "function isCompact()" in v36
    assert "window.matchMedia(MOBILE).matches" in v36

    positions = [
        source.index("source = refine_public_connection_mobile_compact_v36(source)"),
        source.index("source = refine_public_connection_forward_v34(source)"),
        source.index("source = refine_public_connection_final_presentation_v37(source)"),
        source.index("source = refine_public_connection_reference_layout_v38(source)"),
        source.index("return refine_public_connection_ha_multiserver_v39(source)"),
    ]
    assert positions == sorted(positions)
    assert source.rstrip().endswith("return refine_public_connection_ha_multiserver_v39(source)")

    assert "TWINPANEL_PUBLIC_CONNECT_FINAL_PRESENTATION_V37" in v37
    assert "TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38" in v38
    assert "TWINPANEL_PUBLIC_CONNECT_HA_MULTISERVER_V39" in v39

    # Final selected-protocol layout matches the requested pattern.
    assert "High Availability Config" in v39
    assert "Multi Server" in v39
    assert "+'/multi/'+" in v39
    assert "fetch(" not in v39
    assert ".protocol-panel.v36-open{display:block!important}" in v39
    assert ".protocol-panel{display:none!important}" in v39
    assert ".v38-all-card" in v39


def test_android_direct_app_assets_are_verified_and_architecture_specific():
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
    test_canonical_mobile_v26_composes_v36_v34_v37_v38_v39_without_legacy_stack()
    test_android_direct_app_assets_are_verified_and_architecture_specific()
    print("PUBLIC_CONNECTION_CANONICAL_MOBILE_V319_V39=PASS")
