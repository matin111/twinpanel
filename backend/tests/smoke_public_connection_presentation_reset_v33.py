from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "app" / "routers"

v11 = (ROUTERS / "public_connection_device_actions_v11.py").read_text(encoding="utf-8")
v26 = (ROUTERS / "public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
v36 = (ROUTERS / "public_connection_mobile_compact_v36.py").read_text(encoding="utf-8")
v37 = (ROUTERS / "public_connection_final_presentation_v37.py").read_text(encoding="utf-8")
v38 = (ROUTERS / "public_connection_reference_layout_v38.py").read_text(encoding="utf-8")
hub = (ROUTERS / "public_connection_hub_live_v5.py").read_text(encoding="utf-8")
mount = (ROUTERS / "public_connection_protocol_subscriptions_mount_v30.py").read_text(encoding="utf-8")
v30 = (ROUTERS / "public_connection_protocol_subscriptions_v30.py").read_text(encoding="utf-8")


# Device detection stays owned by the established upstream authority for app/client semantics.
for platform in ("windows", "macos", "android", "ios", "linux"):
    assert platform in v11, platform
assert "function detectPlatform()" in v11
assert "body.dataset.tpPlatform=platform" in v11
assert "body.classList.toggle('tp-phone-actions',phoneActions)" in v11
assert "body.classList.toggle('tp-desktop-device',!phoneActions)" in v11


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


# V26 keeps the legacy real-phone cleanup guard; V36 owns the responsive
# accordion, V37 performs cleanup, and V38 is final reference presentation.
assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in v26
assert "function isPhone()" in v26
assert "platform==='android'||platform==='ios'" in v26
assert "!isPhone()||!window.matchMedia(MOBILE).matches" in v26
assert "refine_public_connection_forward_v34" in v26
assert "refine_public_connection_mobile_compact_v36" in v26
assert "refine_public_connection_final_presentation_v37" in v26
assert "refine_public_connection_reference_layout_v38" in v26

v36_call = v26.index("source = refine_public_connection_mobile_compact_v36(source)")
v34_call = v26.index("source = refine_public_connection_forward_v34(source)")
v37_call = v26.index("source = refine_public_connection_final_presentation_v37(source)")
v38_return = v26.index("return refine_public_connection_reference_layout_v38(source)")
assert v36_call < v34_call < v37_call < v38_return
assert v26.rstrip().endswith("return refine_public_connection_reference_layout_v38(source)")
assert "function isCompact()" in v36
assert "window.matchMedia(MOBILE).matches" in v36
assert "+'/multi/'+" in v38
assert "+'/sub/'+" in v38
assert "title.textContent='همه سرورها'" in v38

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


# Preserve V30 endpoint compatibility while V38 restores the proven /sub card
# and keeps V34 all-protocol /multi for the remaining multi-capable protocols.
assert "public_connection_protocol_subscriptions_mount_v30" in v26
assert "public_connection_forward_mount_v34" in v26
assert "public_connection_multilink_v7_router.include_router" in mount
assert "public_connection_protocol_subscriptions_v30_router" in mount
assert '@router.get(' in v30
assert '"/{token}/sub/{protocol}"' in v30
assert 'SUPPORTED_PROTOCOLS = ("v2ray", "hysteria2", "tuic", "anytls")' in v30
assert "v38-all-card" in v38
assert "کپی لینک اشتراک" in v38
assert "کپی لینک همه سرورها" in v38
assert "panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card)" in v38


print("PUBLIC_CONNECTION_PRESENTATION_RESET_V33_V38_SMOKE=PASS")
