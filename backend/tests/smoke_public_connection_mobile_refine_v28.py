from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V28 = ROOT / "app" / "routers" / "public_connection_mobile_refine_v28.py"
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"


v28 = V28.read_text(encoding="utf-8")
v26 = V26.read_text(encoding="utf-8")


assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_REFINE_V28" in v28
assert "protocol-panel[data-modern-protocol] .facts" in v28
assert "display:none!important" in v28

# Modern customer actions must remain available; V28 only suppresses generic facts.
for forbidden in (
    ".v13-modern-action{\n    display:none",
    ".v13-action-buttons{\n    display:none",
    "removeChild",
    ".remove()",
):
    assert forbidden not in v28, forbidden

# Horizontal protocol navigation must advertise overflow instead of relying on discovery.
assert "v27-protocol-strip.v28-scrollable" in v28
assert "strip.scrollWidth>strip.clientWidth+2" in v28
assert "v28-scroll-hint" in v28
assert "برای دیدن همه پروتکل‌ها به چپ یا راست بکشید" in v28
assert "↔" in v28

# V28 is phone-only and chained after V27 from the canonical mobile guard.
assert "@media(max-width:720px)" in v28
assert "window.matchMedia(MOBILE).matches" in v28
assert "from .public_connection_mobile_refine_v28 import" in v26
assert "source = refine_public_connection_mobile_ui_v27(source)" in v26
assert "return refine_public_connection_mobile_v28(source)" in v26

print("PUBLIC_CONNECTION_MOBILE_REFINE_V28_SMOKE=PASS")
