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

for required in (
    "اتصال به Karing",
    "باز کردن در برنامه",
    "کپی لینک",
    "دانلود کانفیگ",
    "دانلود ",
    "برنامه اتصال",
):
    assert required in v31, required
assert "کپی کانفیگ" not in v31

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

assert "data-v13-platform" in v31
assert "currentClientLink" in v31
assert "protocolClientCard" in v31
assert "panel.querySelectorAll('.v13-app,.v13-client-only')" in v31
assert "panel.querySelector('.v30-subscription-card')" in v31
assert "node.removeAttribute('data-tp-copy-target')" in v31
assert 'SUPPORTED_PROTOCOLS = ("v2ray", "hysteria2", "tuic", "anytls")' in v30
assert "public_connection_unified_actions_v31" in v26
assert "source = refine_public_connection_protocol_subscriptions_v30(source)" in v26
assert "return refine_public_connection_unified_actions_v31(source)" in v26

print("PUBLIC_CONNECTION_UNIFIED_ACTIONS_V31_SMOKE=PASS")
