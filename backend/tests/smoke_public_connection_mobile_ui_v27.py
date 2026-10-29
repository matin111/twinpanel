from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V27 = ROOT / "app" / "routers" / "public_connection_mobile_ui_v27.py"
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"
V29 = ROOT / "app" / "routers" / "public_connection_presentation_v29.py"


v27 = V27.read_text(encoding="utf-8")
v26 = V26.read_text(encoding="utf-8")
v29 = V29.read_text(encoding="utf-8")


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

# V27 remains available as the compact fallback layer and is presentation-only.
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

# V26 remains the canonical guard. It applies V27 and V28, then V29 is the
# final customer-facing presentation refinement for both phone and desktop.
assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in v26
assert "from .public_connection_mobile_ui_v27 import" in v26
assert "from .public_connection_mobile_refine_v28 import" in v26
assert "from .public_connection_presentation_v29 import" in v26
assert "source = refine_public_connection_mobile_ui_v27(source)" in v26
assert "source = refine_public_connection_mobile_v28(source)" in v26
assert "return refine_public_connection_presentation_v29(source)" in v26

# V29 intentionally overrides V27's one-active-panel phone UX with the accepted
# vertical protocol/server-card presentation, without removing canonical data.
assert "TWINPANEL_PUBLIC_CONNECT_PRESENTATION_V29" in v29
assert "body.v29-ready.v27-mobile-ui .v27-connect-nav" in v29
assert "body.v29-ready.v27-mobile-ui .protocol-panel.v24-canonical-panel" in v29
assert "body.v29-ready.v27-mobile-ui .protocol-panel .server-view" in v29
assert "content:attr(data-v24-server-label)!important" in v29
assert "protocol-panel[data-modern-protocol] .facts" in v29

print("PUBLIC_CONNECTION_MOBILE_UI_V27_V29_SMOKE=PASS")
