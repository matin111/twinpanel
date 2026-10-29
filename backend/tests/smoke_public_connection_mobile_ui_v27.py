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


v26 = V26.read_text(encoding="utf-8")
v27 = V27.read_text(encoding="utf-8")
v28 = V28.read_text(encoding="utf-8")
v29 = V29.read_text(encoding="utf-8")
v30_mount = V30_MOUNT.read_text(encoding="utf-8")
v31 = V31.read_text(encoding="utf-8")
v32 = V32.read_text(encoding="utf-8")
v34 = V34.read_text(encoding="utf-8")


# Historical refiners remain available for rollback/reference, but none may be
# re-stacked into customer composition.
assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_UI_V27" in v27
assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_REFINE_V28" in v28
assert "TWINPANEL_PUBLIC_CONNECT_PRESENTATION_V29" in v29
assert "TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31" in v31
assert "TWINPANEL_PUBLIC_CONNECT_PLATFORM_GUARD_V32" in v32

assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in v26
assert "public_connection_protocol_subscriptions_mount_v30" in v26
assert "public_connection_forward_mount_v34" in v26
assert "isPhone()" in v26
assert "platform==='android'||platform==='ios'" in v26
assert "!isPhone()||!window.matchMedia(MOBILE).matches" in v26

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

# Only one new final authority is permitted after guarded V26 cleanup.
assert "TWINPANEL_PUBLIC_CONNECT_FORWARD_V34" in v34
assert "from .public_connection_forward_v34 import refine_public_connection_forward_v34" in v26
assert "return refine_public_connection_forward_v34(source)" in v26

# Old V30 backend endpoints remain available independently.
assert "public_connection_multilink_v7_router.include_router" in v30_mount
assert "public_connection_protocol_subscriptions_v30_router" in v30_mount

print("PUBLIC_CONNECTION_SINGLE_V34_COMPOSITION=PASS")
