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

# Current composition contract: V36 owns responsive accordion state, V34 builds
# canonical actions from existing sources, V37 performs cleanup, and V38 is the
# final customer-facing reference-layout authority.
assert "TWINPANEL_PUBLIC_CONNECT_FORWARD_V34" in v34
assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_COMPACT_V36" in v36
assert "TWINPANEL_PUBLIC_CONNECT_FINAL_PRESENTATION_V37" in v37
assert "TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38" in v38
assert "from .public_connection_forward_v34 import refine_public_connection_forward_v34" in v26
assert "from .public_connection_mobile_compact_v36 import" in v26
assert "from .public_connection_final_presentation_v37 import" in v26
assert "from .public_connection_reference_layout_v38 import" in v26

v36_call = v26.index("source = refine_public_connection_mobile_compact_v36(source)")
v34_call = v26.index("source = refine_public_connection_forward_v34(source)")
v37_call = v26.index("source = refine_public_connection_final_presentation_v37(source)")
v38_return = v26.index("return refine_public_connection_reference_layout_v38(source)")
assert v36_call < v34_call < v37_call < v38_return, (v36_call, v34_call, v37_call, v38_return)
assert v26.rstrip().endswith("return refine_public_connection_reference_layout_v38(source)")

# Responsive accordion is viewport-owned; narrow browser acceptance and real
# mobile share the same collapsed/open behaviour without changing V11 platform
# semantics used by client selection.
assert "function isCompact()" in v36
assert "window.matchMedia(MOBILE).matches" in v36
assert "const PHONE=" not in v36
assert "panel.classList.add('active','v36-open')" in v36
assert "event.stopImmediatePropagation()" in v36
assert ".protocol-panel{display:none!important}" in v38
assert ".protocol-panel.v36-open{display:block!important}" in v38

# Old V30 backend endpoints remain available independently.
assert "public_connection_multilink_v7_router.include_router" in v30_mount
assert "public_connection_protocol_subscriptions_v30_router" in v30_mount

# V37 cleanup may hide/remove competing cards, but final V38 restores the exact
# reference all-servers card from existing /sub and /multi authorities.
assert "+'/sub/'+" in v38
assert "+'/multi/'+" in v38
assert "title.textContent='همه سرورها'" in v38
assert "panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card)" in v38
assert "کپی لینک اشتراک" in v38
assert "کپی لینک همه سرورها" in v38

print("PUBLIC_CONNECTION_V38_COMPOSITION=PASS")
