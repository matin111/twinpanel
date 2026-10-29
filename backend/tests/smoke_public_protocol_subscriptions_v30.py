from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V30 = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_v30.py"
MOUNT = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_mount_v30.py"
V26 = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"
V7 = ROOT / "app" / "routers" / "public_connection_multilink_v7.py"


v30 = V30.read_text(encoding="utf-8")
mount = MOUNT.read_text(encoding="utf-8")
v26 = V26.read_text(encoding="utf-8")
v7 = V7.read_text(encoding="utf-8")


# Endpoint contract: one protocol, all real nodes, standard Base64 feed.
assert 'SUPPORTED_PROTOCOLS = ("v2ray", "hysteria2", "tuic", "anytls")' in v30
assert '@router.get(\n    "/{token}/sub/{protocol}"' in v30
assert "base64.b64encode(raw).decode(\"ascii\")" in v30
assert "standard_share_uri(protocol, item, profile_name)" in v30
assert 'item.get("uri")' in v30
assert "seen: set[str] = set()" in v30
assert "if not uri or uri in seen" in v30
assert '"Cache-Control": "no-store"' in v30
assert '"Profile-Update-Interval": "12"' in v30

# Fail closed for formats that are not yet a proven common subscription contract.
for protocol in ("snell", "trusttunnel", "sudoku", "amneziawg", "mieru"):
    assert f'"{protocol}"' not in v30.split("SUPPORTED_PROTOCOLS =", 1)[1].split(")", 1)[0]

# Do not synthesize username/password/server fields inside the subscription layer.
subscription_logic = v30.split("_CSS =", 1)[0]
for forbidden in (
    'item.get("username")',
    'item.get("password")',
    'item.get("server_ip")',
    'item.get("server_address")',
):
    assert forbidden not in subscription_logic, forbidden

# Existing V2Ray endpoint remains intact for backward compatibility.
assert '"/{token}/subscription/v2ray"' in v7
assert "public_v2ray_subscription_v7" in v7

# Router is mounted through the already included V7 router, not a second top-level hub.
assert "public_connection_multilink_v7_router.include_router" in mount
assert "_public_protocol_subscriptions_v30_mounted" in mount
assert "decodeURIComponent(pathParts[connectIndex+1]||'')" in mount

# V30 is final presentation composition after V29.
assert "refine_public_connection_protocol_subscriptions_v30" in v26
assert "source = refine_public_connection_presentation_v29(source)" in v26
assert "return refine_public_connection_protocol_subscriptions_v30(source)" in v26

# Beginner-facing UI has explicit semantics; no bare app-name controls.
for required in (
    "همه سرورها",
    "افزودن همه به Karing",
    "کپی لینک اشتراک",
    "دانلود Karing",
    "دانلود Hiddify",
    "دانلود v2rayN",
    "سرورهای تکی",
    "کپی لینک",
    "کپی کانفیگ",
    "دانلود کانفیگ",
    "اتصال به Karing",
):
    assert required in v30, required

# Mobile individual-server section is secondary/collapsible.
assert "v30-single-servers" in v30
assert "details.className='v30-single-servers'" in v30
assert "details.appendChild(views)" in v30

print("PUBLIC_PROTOCOL_SUBSCRIPTIONS_V30_SMOKE=PASS")
