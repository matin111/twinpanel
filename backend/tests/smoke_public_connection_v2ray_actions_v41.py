from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v41 = (ROOT / "backend/app/routers/public_connection_v2ray_actions_v41.py").read_text()
v43 = (ROOT / "backend/app/routers/public_connection_v2ray_multilink_v43.py").read_text()
v39 = (ROOT / "backend/app/routers/public_connection_mobile_simplified_v39.py").read_text()
xray_runtime = (ROOT / "backend/app/xray_public_delivery_runtime.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41" in v41
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_SUBSCRIPTION_ONLY_V51" in v41
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_V43" in v43
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_SINGLE_PAYLOAD_V50" in v43
assert "refine_public_connection_v2ray_actions_v41" in v39
assert "return refine_public_connection_v2ray_actions_v41(source)" in v39

# Production still owns all real Xray profiles; presentation must not delete or
# rewrite generation semantics just because individual rows are hidden.
assert '"websocket_tls"' in xray_runtime
assert '"xhttp_reality"' in xray_runtime
assert '"tcp_simple"' in xray_runtime
assert "_PUBLIC_PROFILE_ORDER" in xray_runtime
assert "_public_payload_customer_xray" in xray_runtime
assert "profiles.append(tcp_profile)" in xray_runtime

# V43 still preserves the single all-profile payload used by /sub.
assert "from .public_connection_v2ray_multilink_v43 import apply_v2ray_multilink_v43" in v41
assert "apply_v2ray_multilink_v43()" in v41
assert "sub, payload = multilink._active(token, db)" in v43
assert "payload = delivery._public_payload_customer_xray(db, sub)" not in v43
assert 'items = multilink._protocol_items(payload, "v2ray")' in v43
assert "delivery._customer_profiles(item)" in v43
assert "for profile in delivery._customer_profiles(item):" in v43
assert 'uri = str(profile.get("uri") or "").strip()' in v43
assert "multilink._all_share_uris = _all_share_uris_v43" in v43
assert "multilink._delivery = _delivery_v43" in v43

# Customer presentation is subscription-only: hide all per-server/profile rows.
assert '.v38-server-list-title' in v41
assert '.server-views' in v41
assert "views.dataset.v41SingleProfiles='hidden'" in v41
assert "views.hidden=true" in v41
assert "views.setAttribute('aria-hidden','true')" in v41
assert "panel.querySelectorAll('.v49-v2ray-summary,.v49-v2ray-groups')" in v41
assert "v41-v2ray-subscription-only" in v41

# Device-aware XHTTP-capable client downloads replace visible Karing guidance.
assert "name:'v2rayN'" in v41
assert "https://github.com/2dust/v2rayN/releases/latest" in v41
assert "name:'v2rayNG'" in v41
assert "https://github.com/2dust/v2rayNG/releases/latest" in v41
assert "name:'V2Box'" in v41
assert "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690" in v41
assert "link.textContent='دانلود '+client.name" in v41

# No visible per-profile Karing/copy actions remain in V41.
assert "function simplifyProfile(profile)" not in v41
assert "primary.textContent='ارسال به Karing'" not in v41
assert "copy.textContent='کپی کانفیگ'" not in v41
assert "profiles.forEach(simplifyProfile)" not in v41

# Client card stays visible; V42 remains final presentation layer.
assert '.v34-client-card' in v41
assert "function rewriteClientDownload(panel)" in v41
assert "card.dataset.v41ClientDownload='1'" in v41
assert "rewriteClientDownload(panel)" in v41
assert "return refine_public_connection_mobile_sheet_v42(source)" in v41

forbidden = ["iptables", "nft", "vxlan", "tp27", "quota", "accounting", "provision"]
for item in forbidden:
    assert item not in v41.lower(), item
    assert item not in v43.lower(), item

print("V41/V43 Xray subscription-only presentation smoke OK")
