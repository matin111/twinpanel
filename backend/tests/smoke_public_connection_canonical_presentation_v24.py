from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"

v11 = (ROUTERS / "public_connection_device_actions_v11.py").read_text(encoding="utf-8")
v24 = (ROUTERS / "public_connection_canonical_presentation_v24.py").read_text(encoding="utf-8")


# V24 must be the single active device presentation refinement.
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


# Presentation-only means no second server/config/action model.
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


# Device-specific differences are app visibility and presentation only.
assert "syncApps" in v24
assert "dataset.tpPlatform" in v24
assert "link.style.display" in v24


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
