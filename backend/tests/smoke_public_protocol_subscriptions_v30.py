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


# Backend subscription delivery remains unchanged and intentionally limited to
# the proven portable cohort.
assert 'SUPPORTED_PROTOCOLS = ("v2ray", "hysteria2", "tuic", "anytls")' in v30
assert '@router.get(\n    "/{token}/sub/{protocol}"' in v30
assert "base64.b64encode(raw).decode(\"ascii\")" in v30
assert "standard_share_uri(protocol, item, profile_name)" in v30
assert 'item.get("uri")' in v30
assert "seen: set[str] = set()" in v30
assert "if not uri or uri in seen" in v30
assert '"Cache-Control": "no-store"' in v30
assert '"Profile-Update-Interval": "12"' in v30

for protocol in ("snell", "trusttunnel", "sudoku", "amneziawg", "mieru"):
    cohort = v30.split("SUPPORTED_PROTOCOLS =", 1)[1].split(")", 1)[0]
    assert f'"{protocol}"' not in cohort

subscription_logic = v30.split("_CSS =", 1)[0]
for forbidden in (
    'item.get("username")',
    'item.get("password")',
    'item.get("server_ip")',
    'item.get("server_address")',
):
    assert forbidden not in subscription_logic, forbidden


# Legacy V2Ray subscription stays available and V30 is mounted into the same
# public router by import side effect.
assert '"/{token}/subscription/v2ray"' in v7
assert "public_v2ray_subscription_v7" in v7
assert "public_connection_multilink_v7_router.include_router" in mount
assert "public_connection_protocol_subscriptions_v30_router" in mount
assert "_public_protocol_subscriptions_v30_mounted" in mount


# V33 deliberately preserves the backend mount but retires V30's DOM renderer
# from final customer composition. This prevents the subscription UI from
# stacking with V11/V12/V13/V16 presentation layers again.
assert "public_connection_protocol_subscriptions_mount_v30" in v26
assert "refine_public_connection_protocol_subscriptions_v30(source)" not in v26
assert "refine_public_connection_unified_actions_v31" not in v26
assert "refine_public_connection_platform_guard_v32" not in v26


print("PUBLIC_PROTOCOL_SUBSCRIPTIONS_V30_BACKEND_PRESERVED_V33=PASS")
