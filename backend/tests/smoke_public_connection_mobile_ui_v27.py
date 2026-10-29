from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"
V27 = ROOT / "app" / "routers" / "public_connection_mobile_ui_v27.py"
V28 = ROOT / "app" / "routers" / "public_connection_mobile_refine_v28.py"
V29 = ROOT / "app" / "routers" / "public_connection_presentation_v29.py"
V30_MOUNT = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_mount_v30.py"
V31 = ROOT / "app" / "routers" / "public_connection_unified_actions_v31.py"
V32 = ROOT / "app" / "routers" / "public_connection_platform_guard_v32.py"
V34 = ROOT / "app" / "routers" / "public_connection_forward_v34.py"
V36 = ROOT / "app" / "routers" / "public_connection_mobile_compact_v36.py"
V37 = ROOT / "app" / "routers" / "public_connection_final_presentation_v37.py"
V38 = ROOT / "app" / "routers" / "public_connection_reference_layout_v38.py"
V39 = ROOT / "app" / "routers" / "public_connection_ha_multiserver_v39.py"

v26 = V26.read_text(encoding="utf-8")
v27 = V27.read_text(encoding="utf-8")
v28 = V28.read_text(encoding="utf-8")
v29 = V29.read_text(encoding="utf-8")
v30_mount = V30_MOUNT.read_text(encoding="utf-8")
v31 = V31.read_text(encoding="utf-8")
v32 = V32.read_text(encoding="utf-8")
v34 = V34.read_text(encoding="utf-8")
v36 = V36.read_text(encoding="utf-8")
v37 = V37.read_text(encoding="utf-8")
v38 = V38.read_text(encoding="utf-8")
v39 = V39.read_text(encoding="utf-8")

for marker, source in (
    ("TWINPANEL_PUBLIC_CONNECT_MOBILE_UI_V27", v27),
    ("TWINPANEL_PUBLIC_CONNECT_MOBILE_REFINE_V28", v28),
    ("TWINPANEL_PUBLIC_CONNECT_PRESENTATION_V29", v29),
    ("TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31", v31),
    ("TWINPANEL_PUBLIC_CONNECT_PLATFORM_GUARD_V32", v32),
):
    assert marker in source

assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in v26
assert "TWINPANEL_PUBLIC_CONNECT_FORWARD_V34" in v34
assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_COMPACT_V36" in v36
assert "TWINPANEL_PUBLIC_CONNECT_FINAL_PRESENTATION_V37" in v37
assert "TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38" in v38
assert "TWINPANEL_PUBLIC_CONNECT_HA_MULTISERVER_V39" in v39

retired_calls = (
    "refine_public_connection_mobile_ui_v27(source)",
    "refine_public_connection_mobile_v28(source)",
    "refine_public_connection_presentation_v29(source)",
    "refine_public_connection_protocol_subscriptions_v30(source)",
    "refine_public_connection_unified_actions_v31(source)",
    "refine_public_connection_platform_guard_v32(source)",
)
for value in retired_calls:
    assert value not in v26, value

positions = [
    v26.index("source = refine_public_connection_mobile_compact_v36(source)"),
    v26.index("source = refine_public_connection_forward_v34(source)"),
    v26.index("source = refine_public_connection_final_presentation_v37(source)"),
    v26.index("source = refine_public_connection_reference_layout_v38(source)"),
    v26.index("return refine_public_connection_ha_multiserver_v39(source)"),
]
assert positions == sorted(positions), positions
assert v26.rstrip().endswith("return refine_public_connection_ha_multiserver_v39(source)")

# Responsive accordion remains V36-owned and V39 makes its final state authoritative.
assert "function isCompact()" in v36
assert "window.matchMedia(MOBILE).matches" in v36
assert "const PHONE=" not in v36
assert "panel.classList.add('active','v36-open')" in v36
assert "event.stopImmediatePropagation()" in v36
assert ".protocol-panel{display:none!important}" in v39
assert ".protocol-panel.v36-open{display:block!important}" in v39

# Existing backend routes remain mounted.
assert "public_connection_multilink_v7_router.include_router" in v30_mount
assert "public_connection_protocol_subscriptions_v30_router" in v30_mount

# Final mobile presentation is the requested reference pattern.
assert "+'/multi/'+" in v39
assert "High Availability Config" in v39
assert "Multi Server" in v39
assert "دانلود همه" in v39
assert "افزودن همه" in v39
assert "fetch(" not in v39
assert ".v38-all-card" in v39

print("PUBLIC_CONNECTION_V39_COMPOSITION=PASS")
