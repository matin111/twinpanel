from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"

v11 = (ROUTERS / "public_connection_device_actions_v11.py").read_text(encoding="utf-8")
v23 = (ROUTERS / "public_connection_device_presentation_v23.py").read_text(encoding="utf-8")


# V11 must have exactly one device-presentation refinement path.
assert "public_connection_device_presentation_v23" in v11
assert "refine_public_connection_device_presentation_v23" in v11
for retired in (
    "refine_public_connection_mobile_protocols_v17",
    "refine_public_connection_mobile_server_inventory_v18",
    "refine_public_connection_protocol_actions_v20",
    "refine_public_connection_protocol_uri_details_v21",
    "refine_public_connection_protocol_action_authority_v22",
):
    assert retired not in v11, retired


# V23 is presentation-only. It must never create a second server/config data path.
for forbidden in (
    "fetch(",
    "mobile-server-inventory-v18",
    "JSON.parse",
    "v18-not-ready",
    "آماده‌سازی",
    "createElement('div')",
    'createElement("div")',
):
    assert forbidden not in v23, forbidden


# Canonical DOM is the authority on every device.
for required in (
    ".protocol-panel",
    ".server-view",
    ".server-tab",
    "v23-canonical-panel",
    "data-v23-server-label",
    "data-v13-platform",
    "data-tp-platform",
    "MutationObserver",
    "live-online",
):
    assert required in v23, required


# Device-specific behavior is limited to presentation/app recommendations.
assert "syncApps" in v23
assert "dataset.tpPlatform" in v23
assert "link.style.display" in v23


# Readability regression: key mobile copy/actions must be 12px or larger.
assert "font-size:12px!important" in v23
assert "font-size:13px" in v23
assert "font-size:16px!important" in v23
assert "font-size:7px" not in v23
assert "font-size:8px" not in v23
assert "font-size:9px" not in v23


# Desktop remains untouched by presentation overrides.
assert "@media(max-width:720px)" in v23
assert "function deactivateMobile()" in v23


print("V23 canonical device presentation smoke: PASS")
