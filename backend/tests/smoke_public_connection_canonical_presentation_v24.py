from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"

v11 = (ROUTERS / "public_connection_device_actions_v11.py").read_text(encoding="utf-8")
v24 = (ROUTERS / "public_connection_canonical_presentation_v24.py").read_text(encoding="utf-8")


# V24 is the canonical device presentation refinement wired by V11.
assert "public_connection_canonical_presentation_v24" in v11
assert "refine_public_connection_canonical_presentation_v24" in v11
for retired in (
    "refine_public_connection_mobile_protocols_v17",
    "refine_public_connection_mobile_server_inventory_v18",
    "refine_public_connection_protocol_actions_v20",
    "refine_public_connection_protocol_uri_details_v21",
    "refine_public_connection_protocol_action_authority_v22",
    "refine_public_connection_device_data_authority_v23",
):
    assert retired not in v11, retired


# Presentation-only means no second server/config/action model is created here.
for forbidden in (
    "fetch(",
    "mobile-server-inventory-v18",
    "JSON.parse",
    "appendMissingModernServers",
    "v18-not-ready",
    "آماده‌سازی",
    "createElement('button')",
    'createElement("button")',
    "createElement('a')",
    'createElement("a")',
    "actions.replaceChildren",
):
    assert forbidden not in v24, forbidden


# The canonical desktop DOM is reused on mobile.
for required in (
    ".protocol-panel",
    ".server-view",
    ".server-tab",
    "v24-canonical-panel",
    "data-v24-server-label",
    "data-v13-platform",
    "data-tp-platform",
    "MutationObserver",
    "live-online",
):
    assert required in v24, required


# Legacy mobile renderers may still be present for compatibility, but cannot own
# the final mobile DOM once canonical V24 is active.
for required in (
    "retireLegacyMobile",
    "v9-ready",
    "v17-ready",
    ".v9-mobile-stack,.v17-mobile-stack",
    "legacyObserver",
):
    assert required in v24, required


# Device-specific differences are app visibility/presentation only.
assert "syncApps" in v24
assert "dataset.tpPlatform" in v24
assert "link.style.display" in v24


# V24 must never replace audited client URLs with old hardcoded APK/IPA
# strings. Every renderer uses one canonical client download catalog.
catalog = (ROUTERS / "public_connection_client_catalog_v821.py").read_text(encoding="utf-8")
assert "const DIRECT_APPS" not in v24
assert "applyDirectApp" not in v24
assert "Hiddify-iOS.ipa" not in v24
for target in (
    "com.wireguard.android-1.0.20260315.apk",
    "v2rayNG_2.3.15_arm64-v8a.apk",
    "Hiddify-Android-arm64.apk",
    "karing_1.2.26.2929_android_arm64-v8a.apk",
    "SFA-1.14.4-arm64-v8a.apk",
    "AmneziaWG-3.1.202060814.apk",
    "sudodroid-v0.3.4-universal.apk",
    "id6755807890",
):
    assert target in catalog, target

# Mobile helper/tutorial prose is visually retired; protocol names, app names,
# canonical connection facts and functional action labels remain.
for hidden_selector in (
    ".section-head p",
    ".section-head small",
    ".apps-head",
    ".platform-title",
    ".app-card small",
    ".action-copy",
    ".v13-action-copy",
    ".v13-client-only>span",
    ".v13-native-client",
):
    assert hidden_selector in v24, hidden_selector


# Readability: reject the historical 6-9px mobile scale.
assert "font-size:12px!important" in v24
assert "font-size:13px" in v24
assert "font-size:16px!important" in v24
for tiny in ("font-size:6px", "font-size:6.5px", "font-size:7px", "font-size:8px", "font-size:9px"):
    assert tiny not in v24, tiny


# Desktop remains untouched by the presentation overrides.
assert "@media(max-width:720px)" in v24
assert "function deactivateMobile()" in v24


print("V24 canonical presentation smoke: PASS")
