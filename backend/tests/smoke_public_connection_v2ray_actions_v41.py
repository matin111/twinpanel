from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v41 = (ROOT / "backend/app/routers/public_connection_v2ray_actions_v41.py").read_text()
v39 = (ROOT / "backend/app/routers/public_connection_mobile_simplified_v39.py").read_text()
xray_runtime = (ROOT / "backend/app/xray_public_delivery_runtime.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41" in v41
assert "refine_public_connection_v2ray_actions_v41" in v39
assert "source = refine_public_connection_mobile_authority_v40(source)" in v39
assert "return refine_public_connection_v2ray_actions_v41(source)" in v39

# Production Xray delivery owns three customer connection profiles in stable order.
assert '"websocket_tls"' in xray_runtime
assert '"xhttp_reality"' in xray_runtime
assert '"tcp_simple"' in xray_runtime
assert "_PUBLIC_PROFILE_ORDER" in xray_runtime

# V41 must preserve the real V48 profile container/rows instead of deleting them.
assert "function profileRows(view)" in v41
assert ":scope > .tp-v48-xray-profiles > .tp-v48-xray-profile" in v41
assert "profiles.forEach(simplifyProfile)" in v41
assert "wrapper.dataset.v41ProfileCount=String(profiles.length)" in v41
assert "purgeLegacyInteractiveBlocks" not in v41

# Each real profile keeps only its own Hiddify import + exact config copy action.
assert "const primary=actions.querySelector('.tp-v48-hiddify')" in v41
assert "const copy=actions.querySelector('.copy-btn[data-copy]')" in v41
assert "if(node!==primary&&node!==copy)node.remove()" in v41
assert "primary.textContent='ارسال به Hiddify'" in v41
assert "copy.textContent='کپی کانفیگ'" in v41
assert "ارسال این اتصال به Hiddify" in v41
assert "کپی کانفیگ این اتصال" in v41

# Once real profiles exist, the generic canonical row is only a duplicate and is hidden.
assert "row.dataset.v41Duplicate='1'" in v41
assert "row.setAttribute('aria-hidden','true')" in v41
assert '.v34-server-actions[data-v41-duplicate="1"]' in v41

# Legacy V2Ray without profiles still keeps the canonical two-action fallback.
assert "function simplifyCanonicalFallback(view,row)" in v41
assert "const primary=row.querySelector('.v34-primary')" in v41
assert "const copy=row.querySelector('.v34-copy')" in v41
assert "row.dataset.v41Canonical='1'" in v41

# Client download card stays outside server-view cleanup; V42 remains final presentation layer.
assert ".v34-client-card" not in v41
assert "return refine_public_connection_mobile_sheet_v42(source)" in v41
assert "matchMedia" not in v41

forbidden = ["iptables", "nft", "vxlan", "tp27", "quota", "accounting", "provision"]
for item in forbidden:
    assert item not in v41.lower(), item

print("V41 Xray three-profile two-action smoke OK")
