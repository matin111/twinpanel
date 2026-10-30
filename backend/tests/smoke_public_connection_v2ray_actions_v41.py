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

# Production Xray delivery owns three customer connection profiles in stable order.
assert '"websocket_tls"' in xray_runtime
assert '"xhttp_reality"' in xray_runtime
assert '"tcp_simple"' in xray_runtime
assert "_PUBLIC_PROFILE_ORDER" in xray_runtime
assert "_public_payload_customer_xray" in xray_runtime
assert "profiles.append(tcp_profile)" in xray_runtime

# V43 reuses the single already-policy-applied customer payload from _active().
# Rebuilding it through xray_public_delivery_runtime is intentionally forbidden:
# that duplicate pass regenerated QR SVGs and caused subscription latency/timeouts.
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

# V41 must preserve the real V48 profile container/rows instead of deleting them.
assert "function profileRows(view)" in v41
assert ":scope > .tp-v48-xray-profiles > .tp-v48-xray-profile" in v41
assert "profiles.forEach(simplifyProfile)" in v41
assert "wrapper.dataset.v41ProfileCount=String(profiles.length)" in v41
assert "purgeLegacyInteractiveBlocks" not in v41

# Each real profile keeps only its own Karing import + exact config copy action.
assert "const primary=actions.querySelector('.tp-v48-karing')" in v41
assert "const copy=actions.querySelector('.copy-btn[data-copy]')" in v41
assert "if(node!==primary&&node!==copy)node.remove()" in v41
assert "primary.textContent='ارسال به Karing'" in v41
assert "copy.textContent='کپی کانفیگ'" in v41
assert "ارسال این اتصال به Karing" in v41
assert "کپی کانفیگ این اتصال" in v41
assert "const primary=actions.querySelector('.tp-v48-hiddify')" not in v41

# Once real profiles exist, the generic canonical row is only a duplicate and is hidden.
assert "row.dataset.v41Duplicate='1'" in v41
assert "row.setAttribute('aria-hidden','true')" in v41
assert '.v34-server-actions[data-v41-duplicate="1"]' in v41

# Legacy V2Ray without profiles still keeps the canonical two-action fallback,
# but the primary label is normalized to Karing.
assert "function simplifyCanonicalFallback(view,row)" in v41
assert "const primary=row.querySelector('.v34-primary')" in v41
assert "const copy=row.querySelector('.v34-copy')" in v41
assert "primary.textContent='ارسال به Karing'" in v41
assert "row.dataset.v41Canonical='1'" in v41

# Client download card is preserved; V42 remains final presentation layer.
assert '.v34-client-card' in v41
assert "function preserveClientDownload(panel)" in v41
assert "card.dataset.v41ClientDownload='1'" in v41
assert "preserveClientDownload(panel)" in v41
assert "return refine_public_connection_mobile_sheet_v42(source)" in v41
assert "matchMedia" not in v41

forbidden = ["iptables", "nft", "vxlan", "tp27", "quota", "accounting", "provision"]
for item in forbidden:
    assert item not in v41.lower(), item
    assert item not in v43.lower(), item

print("V41/V43 Xray Karing actions + single-payload all-country multilink smoke OK")
