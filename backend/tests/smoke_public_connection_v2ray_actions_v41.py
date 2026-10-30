from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v41 = (ROOT / "backend/app/routers/public_connection_v2ray_actions_v41.py").read_text()
v43 = (ROOT / "backend/app/routers/public_connection_v2ray_multilink_v43.py").read_text()
v39 = (ROOT / "backend/app/routers/public_connection_mobile_simplified_v39.py").read_text()
xray_runtime = (ROOT / "backend/app/xray_public_delivery_runtime.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41" in v41
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_V43" in v43
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_SINGLE_PAYLOAD_V50" in v43
assert "refine_public_connection_v2ray_actions_v41" in v39
assert "source = refine_public_connection_mobile_authority_v40(source)" in v39
assert "return refine_public_connection_v2ray_actions_v41(source)" in v39

assert '"websocket_tls"' in xray_runtime
assert '"xhttp_reality"' in xray_runtime
assert '"tcp_simple"' in xray_runtime
assert "_PUBLIC_PROFILE_ORDER" in xray_runtime
assert "_public_payload_customer_xray" in xray_runtime
assert "profiles.append(tcp_profile)" in xray_runtime

assert "from .public_connection_v2ray_multilink_v43 import apply_v2ray_multilink_v43" in v41
assert "apply_v2ray_multilink_v43()" in v41
assert "sub, payload = multilink._active(token, db)" in v43
assert "payload = delivery._public_payload_customer_xray(db, sub)" not in v43
assert 'items = multilink._protocol_items(payload, "v2ray")' in v43
assert "delivery._customer_profiles(item)" in v43
assert "for profile in delivery._customer_profiles(item):" in v43
assert 'uri = str(profile.get("uri") or "").strip()' in v43
assert "for item in items:" in v43
assert "legacy = multilink._share_uri(sub, \"v2ray\", item)" in v43
assert "multilink._all_share_uris = _all_share_uris_v43" in v43
assert "multilink._delivery = _delivery_v43" in v43
assert 'return "uri", len(items), sub, items, uris' in v43
assert 'if protocol_key != "v2ray":' in v43
assert "return _original_all_share_uris(sub, protocol, items)" in v43
assert "return _original_delivery(token, protocol, db)" in v43

# The lower per-server config inventory must not exist in the customer UI.
assert "function removeLowerConfigSection(panel)" in v41
assert "panel.querySelectorAll('.v38-server-list-title,.tp-v41-profile-toggle,.server-views').forEach(node=>node.remove())" in v41
assert "panel.dataset.v41LowerConfigsRemoved='1'" in v41
assert '.server-views' in v41
assert 'display:none!important' in v41
assert "profileRows" not in v41
assert "simplifyProfile" not in v41
assert "simplifyCanonicalFallback" not in v41
assert "useOuterConfigToggle" not in v41
assert "بستن کانفیگ‌ها" not in v41
assert "ارسال به Karing" not in v41
assert "کپی کانفیگ" not in v41

# Smart customer-facing app card remains device-aware.
assert "const CLIENTS={" in v41
assert "windows:{name:'v2rayN'" in v41
assert "macos:{name:'v2rayN'" in v41
assert "linux:{name:'v2rayN'" in v41
assert "android:{name:'v2rayNG'" in v41
assert "ios:{name:'V2Box'" in v41
assert "function platform()" in v41
assert "function rewriteClientDownload(panel)" in v41
assert "const links=[...card.querySelectorAll('a')]" in v41
assert "links.slice(1).forEach(node=>node.remove())" in v41
assert "card.dataset.v41V2rayClient=client.name" in v41
assert "link.textContent='دانلود '+client.name" in v41
assert "rewriteClientDownload(panel)" in v41
assert "removeLowerConfigSection(panel)" in v41

assert '.v34-client-card' in v41
assert "return refine_public_connection_mobile_sheet_v42(source)" in v41
assert "matchMedia" not in v41

forbidden = ["iptables", "nft", "vxlan", "tp27", "quota", "accounting", "provision"]
for item in forbidden:
    assert item not in v41.lower(), item
    assert item not in v43.lower(), item

print("V41/V43 Xray lower config inventory removed + smart client smoke OK")
