from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V27 = ROOT / "app" / "routers" / "public_connection_mobile_ui_v27.py"
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"


v27 = V27.read_text(encoding="utf-8")
v26 = V26.read_text(encoding="utf-8")


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

# Mobile must collapse the canonical surface to one protocol and one server.
assert "protocol-panel.v24-canonical-panel.v27-active-protocol" in v27
assert "server-view.v27-active-server" in v27
assert "protocol-panel.v24-canonical-panel{\n    display:none!important" in v27
assert "protocol-panel .server-view{\n    display:none!important" in v27

# V27 is presentation only. It must not invent or parse credentials/configs.
for forbidden in (
    "JSON.parse(",
    "atob(",
    "server_ip",
    "username=",
    "password=",
    "protocolDetails",
):
    assert forbidden not in v27, forbidden

# Per-protocol actions remain canonical while the old global app catalog is hidden.
assert "body.v27-mobile-ui .apps" in v27
assert "v13-action-buttons" in v27
assert "tp-v48-profile-actions" in v27

# V26 remains the canonical guard, applies V27, then delegates to V28.
assert "TWINPANEL_PUBLIC_CONNECT_CANONICAL_MOBILE_V26" in v26
assert "from .public_connection_mobile_ui_v27 import" in v26
assert "from .public_connection_mobile_refine_v28 import" in v26
assert "source = refine_public_connection_mobile_ui_v27(source)" in v26
assert "return refine_public_connection_mobile_v28(source)" in v26

print("PUBLIC_CONNECTION_MOBILE_UI_V27_SMOKE=PASS")
