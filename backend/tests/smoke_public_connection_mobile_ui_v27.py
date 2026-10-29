from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"
V27 = ROOT / "app" / "routers" / "public_connection_mobile_ui_v27.py"
V28 = ROOT / "app" / "routers" / "public_connection_mobile_refine_v28.py"
V29 = ROOT / "app" / "routers" / "public_connection_presentation_v29.py"
V30_MOUNT = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_mount_v30.py"
V31 = ROOT / "app" / "routers" / "public_connection_unified_actions_v31.py"
V32 = ROOT / "app" / "routers" / "public_connection_platform_guard_v32.py"


v26 = V26.read_text(encoding="utf-8")
v27 = V27.read_text(encoding="utf-8")
v28 = V28.read_text(encoding="utf-8")
v29 = V29.read_text(encoding="utf-8")
v30_mount = V30_MOUNT.read_text(encoding="utf-8")
v31 = V31.read_text(encoding="utf-8")
v32 = V32.read_text(encoding="utf-8")


# Historical refiners remain available for rollback/reference, but V33 retires
# them from the final customer composition instead of stacking more DOM layers.
assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_UI_V27" in v27
assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_REFINE_V28" in v28
assert "TWINPANEL_PUBLIC_CONNECT_PRESENTATION_V29" in v29
assert "TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31" in v31
assert "TWINPANEL_PUBLIC_CONNECT_PLATFORM_GUARD_V32" in v32

assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in v26
assert "public_connection_protocol_subscriptions_mount_v30" in v26
assert "isPhone()" in v26
assert "platform==='android'||platform==='ios'" in v26
assert "!isPhone()||!window.matchMedia(MOBILE).matches" in v26

# None of the retired presentation refiners may be imported or invoked from the
# final V26 composition. This is the regression that caused duplicate/blank
# action surfaces on Windows and mobile.
retired_imports = (
    "from .public_connection_mobile_ui_v27 import",
    "from .public_connection_mobile_refine_v28 import",
    "from .public_connection_presentation_v29 import",
    "from .public_connection_unified_actions_v31 import",
    "from .public_connection_platform_guard_v32 import",
)
for value in retired_imports:
    assert value not in v26, value

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

# V30 backend route mounting is deliberately preserved independently from its
# retired presentation refiner.
assert "public_connection_multilink_v7_router.include_router" in v30_mount
assert "public_connection_protocol_subscriptions_v30_router" in v30_mount

print("PUBLIC_CONNECTION_PRESENTATION_RESET_V33_COMPOSITION=PASS")
