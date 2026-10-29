from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V27 = ROOT / "app" / "routers" / "public_connection_mobile_ui_v27.py"
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"
V29 = ROOT / "app" / "routers" / "public_connection_presentation_v29.py"
V30 = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_v30.py"
V31 = ROOT / "app" / "routers" / "public_connection_unified_actions_v31.py"
V32 = ROOT / "app" / "routers" / "public_connection_platform_guard_v32.py"


v27 = V27.read_text(encoding="utf-8")
v26 = V26.read_text(encoding="utf-8")
v29 = V29.read_text(encoding="utf-8")
v30 = V30.read_text(encoding="utf-8")
v31 = V31.read_text(encoding="utf-8")
v32 = V32.read_text(encoding="utf-8")


assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_UI_V27" in v27
assert "v27-connect-nav" in v27
assert "v27-protocol-strip" in v27
assert "v27-server-strip" in v27
assert "v27-active-protocol" in v27
assert "v27-active-server" in v27
assert "visiblePanels" in v27
assert "originalChoice" in v27
assert "selectProtocol" in v27
assert "selectServer" in v27

for forbidden in (
    "JSON.parse(",
    "atob(",
    "server_ip",
    "username=",
    "password=",
    "protocolDetails",
):
    assert forbidden not in v27, forbidden

assert "body.v27-mobile-ui .apps" in v27
assert "v13-action-buttons" in v27
assert "tp-v48-profile-actions" in v27

assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in v26
assert "from .public_connection_mobile_ui_v27 import" in v26
assert "from .public_connection_mobile_refine_v28 import" in v26
assert "from .public_connection_presentation_v29 import" in v26
assert "public_connection_protocol_subscriptions_mount_v30" in v26
assert "public_connection_unified_actions_v31" in v26
assert "public_connection_platform_guard_v32" in v26
v27_call = "source = refine_public_connection_mobile_ui_v27(source)"
v28_call = "source = refine_public_connection_mobile_v28(source)"
v29_call = "source = refine_public_connection_presentation_v29(source)"
v30_call = "source = refine_public_connection_protocol_subscriptions_v30(source)"
v31_call = "source = refine_public_connection_unified_actions_v31(source)"
v32_call = "return refine_public_connection_platform_guard_v32(source)"
for call in (v27_call, v28_call, v29_call, v30_call, v31_call, v32_call):
    assert call in v26, call
positions = [v26.index(call) for call in (v27_call, v28_call, v29_call, v30_call, v31_call, v32_call)]
assert positions == sorted(positions), positions

assert "TWINPANEL_PUBLIC_CONNECT_PRESENTATION_V29" in v29
assert "body.v29-ready.v27-mobile-ui .v27-connect-nav" in v29
assert "body.v29-ready.v27-mobile-ui .protocol-panel.v24-canonical-panel" in v29
assert "body.v29-ready.v27-mobile-ui .protocol-panel .server-view" in v29
assert "content:attr(data-v24-server-label)!important" in v29
assert "protocol-panel[data-modern-protocol] .facts" in v29

assert "TWINPANEL_PUBLIC_PROTOCOL_SUBSCRIPTIONS_V30" in v30
assert "v30-subscription-card" in v30
assert "v30-single-servers" in v30
assert "سرورهای تکی" in v30
assert "کپی لینک اشتراک" in v30

# V31 owns canonical actions across every protocol. V32 is the final authority
# for platform boundaries and CSS precedence so narrow desktop stays desktop.
assert "TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31" in v31
assert "detectPlatform" in v31
assert "currentClientLink" in v31
assert "return links[0]" not in v31
assert "برنامه مناسب دستگاه شما" in v31
assert "'اتصال به '+" in v31
assert "کپی لینک اتصال" in v31
assert "دانلود کانفیگ" in v31
assert "v31-client-card" in v31
assert "v31-canonical-actions" in v31
assert "data-v13-platform" in v31
assert ".mobile-send-btn" in v31
assert "primeSubscriptionPanels" in v31
assert "panel.classList.add('v24-canonical-panel')" in v31
assert "normalizeSubscriptionCard" in v31
assert "panel.querySelectorAll('.v13-app,.v13-client-only,.mobile-send-btn,.v9-icon-btn.mobile')" in v31
assert "کپی کانفیگ" not in v31

assert "TWINPANEL_PUBLIC_CONNECT_PLATFORM_GUARD_V32" in v32
assert "DESKTOP=new Set(['windows','macos','linux'])" in v32
assert "restoreDesktopPresentation" in v32
assert "style.setProperty('display','none','important')" in v32
assert "document.querySelectorAll('.v31-client-card>span').forEach(node=>node.remove())" in v32

print("PUBLIC_CONNECTION_MOBILE_UI_V27_V32_SMOKE=PASS")
