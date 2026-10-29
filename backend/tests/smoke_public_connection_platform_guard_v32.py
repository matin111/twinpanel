from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V13 = ROOT / "app" / "routers" / "public_connection_modern_delivery_v13.py"
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"
V30 = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_v30.py"
V31 = ROOT / "app" / "routers" / "public_connection_unified_actions_v31.py"
V32 = ROOT / "app" / "routers" / "public_connection_platform_guard_v32.py"

v13 = V13.read_text(encoding="utf-8")
v26 = V26.read_text(encoding="utf-8")
v30 = V30.read_text(encoding="utf-8")
v31 = V31.read_text(encoding="utf-8")
v32 = V32.read_text(encoding="utf-8")

# Public Connect has one canonical 15-protocol surface. V32 must guard the whole
# surface rather than special-casing the four protocols that also support V30
# common subscriptions.
canonical_protocols = (
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
)
assert "CANONICAL_PROTOCOLS = CLASSIC_PROTOCOLS + MODERN_PROTOCOLS" in v13
for protocol in canonical_protocols:
    assert f'"{protocol}"' in v13, protocol

# V31 remains generic across every rendered protocol panel.
assert "document.querySelectorAll('.protocol-panel').forEach(normalizePanel)" in v31

# V32 is final and platform-aware. Narrow desktop windows must not retain the
# phone-only V24/V27/V30 DOM state.
assert "TWINPANEL_PUBLIC_CONNECT_PLATFORM_GUARD_V32" in v32
assert "DESKTOP=new Set(['windows','macos','linux'])" in v32
assert "restoreDesktopPresentation" in v32
assert "'v24-ready','v27-mobile-ui'" in v32
assert "details.v30-single-servers" in v32
assert "MutationObserver" in v32

# Old mobile CSS uses more-specific display:* !important selectors. The final
# authority therefore needs inline !important hiding, not another weak selector.
assert "style.setProperty('display','none','important')" in v32
assert "[data-v31-legacy-actions=\"1\"]" in v32
assert ".server-view .v13-app" in v32
assert ".v13-client-only" in v32

# Explanatory client-card copy is removed; the customer sees the actual app
# download action, not another helper paragraph.
assert "document.querySelectorAll('.v31-client-card>span').forEach(node=>node.remove())" in v32

# V26 itself now refuses phone-only cleanup on desktop and chains V32 after V31.
assert "function isPhone()" in v26
assert "if(!isPhone()||!window.matchMedia(MOBILE).matches)return;" in v26
assert "source = refine_public_connection_unified_actions_v31(source)" in v26
assert "return refine_public_connection_platform_guard_v32(source)" in v26

# V30 common subscription feeds intentionally remain the proven four-protocol
# cohort. This must not be confused with the 15-protocol presentation authority.
assert 'SUPPORTED_PROTOCOLS = ("v2ray", "hysteria2", "tuic", "anytls")' in v30

# Presentation guards must never synthesize credentials or fetch replacement
# connection data.
for forbidden in (
    "server_ip=",
    "username=",
    "password=",
    "JSON.parse(",
    "atob(",
    "fetch(",
):
    assert forbidden not in v32, forbidden

print("PUBLIC_CONNECTION_PLATFORM_GUARD_V32_SMOKE=PASS")
