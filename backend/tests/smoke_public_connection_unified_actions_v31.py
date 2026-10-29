from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V31 = ROOT / "app" / "routers" / "public_connection_unified_actions_v31.py"
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"
V30 = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_v30.py"

v31 = V31.read_text(encoding="utf-8")
v26 = V26.read_text(encoding="utf-8")
v30 = V30.read_text(encoding="utf-8")

assert "TWINPANEL_PUBLIC_CONNECT_UNIFIED_ACTIONS_V31" in v31
assert "v31-ready" in v31
assert "v31-client-card" in v31
assert "v31-canonical-actions" in v31

# Beginner vocabulary: no raw-config copy and no vague per-server copy action.
for required in (
    "اتصال به ",
    "کپی لینک اتصال",
    "کپی لینک اشتراک",
    "دانلود کانفیگ",
    "برنامه مناسب دستگاه شما",
):
    assert required in (v31 + v30), required
assert "کپی کانفیگ" not in v31

# V31 remains presentation-only; it must never reconstruct credentials.
for forbidden in (
    "server_ip=",
    "username=",
    "password=",
    "JSON.parse(",
    "atob(",
    "fetch(",
    "/sub/",
):
    assert forbidden not in v31, forbidden

# Strict device awareness: never fall back to the first client from another OS.
assert "currentClientLink" in v31
assert "data-v13-platform" in v31
assert "return links.find" in v31
assert "||null" in v31
assert "return links[0]" not in v31
assert "detectPlatform" in v31

# Old cross-device/duplicated action surfaces are retired from customer UI.
assert ".mobile-send-btn" in v31
assert ".v9-icon-btn.mobile" in v31
assert "data-v31-legacy-actions" in v31
assert "candidateControls" in v31
assert "canonicalServerActions" in v31
assert "cleanCopyButton" in v31

# One app download belongs to the protocol, never to each country/server.
assert "protocolClientCard" in v31
assert "panel.querySelectorAll('.v13-app,.v13-client-only,.mobile-send-btn,.v9-icon-btn.mobile')" in v31
assert ".v30-subscription-card .v30-client-downloads" in v31

# Regression lock: V29 removed the legacy multi-link; V30 must still be allowed
# to create its canonical per-protocol subscription card on desktop too.
assert "primeSubscriptionPanels" in v31
assert "document.querySelectorAll('.protocol-panel')" in v31
assert "panel.classList.add('v24-canonical-panel')" in v31
assert "v30-subscription-card" in v31
assert "normalizeSubscriptionCard" in v31
assert "افزودن همه به Hiddify" in v31
assert "افزودن همه به Karing" in v31

# Backend subscription scope stays intentionally fail-closed.
assert 'SUPPORTED_PROTOCOLS = ("v2ray", "hysteria2", "tuic", "anytls")' in v30

# V31 remains the final presentation layer after V30 in the canonical chain.
assert "public_connection_unified_actions_v31" in v26
assert "source = refine_public_connection_protocol_subscriptions_v30(source)" in v26
assert "return refine_public_connection_unified_actions_v31(source)" in v26

# Dependency-free composition contract: the refiner must inject both CSS and JS
# before the closing tags and must be idempotent by marker.
assert 'source.replace("</style>", _CSS + "\\n</style>", 1)' in v31
assert 'source.replace("</body>", _SCRIPT + f"\\n<!-- {_MARKER} -->\\n</body>", 1)' in v31
assert 'if _MARKER in source:' in v31
assert 'return source' in v31

print("PUBLIC_CONNECTION_UNIFIED_ACTIONS_V31_SMOKE=PASS")
