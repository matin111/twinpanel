from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "app" / "routers"

v11 = (ROUTERS / "public_connection_device_actions_v11.py").read_text(encoding="utf-8")
v26 = (ROUTERS / "public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
hub = (ROUTERS / "public_connection_hub_live_v5.py").read_text(encoding="utf-8")
mount = (ROUTERS / "public_connection_protocol_subscriptions_mount_v30.py").read_text(encoding="utf-8")
v30 = (ROUTERS / "public_connection_protocol_subscriptions_v30.py").read_text(encoding="utf-8")


# Device detection stays owned by the established upstream authority.
for platform in ("windows", "macos", "android", "ios", "linux"):
    assert platform in v11, platform
assert "function detectPlatform()" in v11
assert "body.dataset.tpPlatform=platform" in v11
assert "body.classList.toggle('tp-phone-actions',phoneActions)" in v11
assert "body.classList.toggle('tp-desktop-device',!phoneActions)" in v11


# The live route still executes the real delivery/device pipeline and reaches
# V26. V34 is composed inside V26 so the hub never regains a stacked chain.
required_hub_calls = (
    "refine_public_connection_device_actions_v11(source)",
    "refine_public_connection_windows_v12(source)",
    "refine_public_connection_modern_delivery_v13(source, token, db)",
    "refine_public_connection_modern_names_v14(source, token, db)",
    "refine_public_connection_modern_import_v15(source, token, db)",
    "refine_public_connection_modern_delivery_v16(source, token, db)",
    "refine_public_connection_protocol_actions_v20(source)",
    "refine_public_connection_xray_profiles_v48(source)",
    "refine_public_connection_canonical_mobile_v26(source)",
)
for call in required_hub_calls:
    assert call in hub, call
positions = [hub.index(call) for call in required_hub_calls]
assert positions == sorted(positions), positions


# V26 remains phone-gated. Narrow Windows must not enter its cleanup, then one
# explicit V34 authority owns the final customer presentation.
assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in v26
assert "function isPhone()" in v26
assert "platform==='android'||platform==='ios'" in v26
assert "!isPhone()||!window.matchMedia(MOBILE).matches" in v26
assert "refine_public_connection_forward_v34" in v26
assert "return refine_public_connection_forward_v34(source)" in v26

retired_presentation_symbols = (
    "refine_public_connection_mobile_ui_v27",
    "refine_public_connection_mobile_v28",
    "refine_public_connection_presentation_v29",
    "refine_public_connection_protocol_subscriptions_v30(source)",
    "refine_public_connection_unified_actions_v31",
    "refine_public_connection_platform_guard_v32",
)
for symbol in retired_presentation_symbols:
    assert symbol not in v26, symbol


# Preserve old V30 endpoint compatibility while V34 adds the new all-protocol
# route surface separately.
assert "public_connection_protocol_subscriptions_mount_v30" in v26
assert "public_connection_forward_mount_v34" in v26
assert "public_connection_multilink_v7_router.include_router" in mount
assert "public_connection_protocol_subscriptions_v30_router" in mount
assert '@router.get(' in v30
assert '"/{token}/sub/{protocol}"' in v30
assert 'SUPPORTED_PROTOCOLS = ("v2ray", "hysteria2", "tuic", "anytls")' in v30


print("PUBLIC_CONNECTION_PRESENTATION_RESET_V33_SMOKE=PASS")
