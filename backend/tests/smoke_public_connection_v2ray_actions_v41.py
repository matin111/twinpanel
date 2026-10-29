from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v41 = (ROOT / "backend/app/routers/public_connection_v2ray_actions_v41.py").read_text()
v39 = (ROOT / "backend/app/routers/public_connection_mobile_simplified_v39.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ACTIONS_V41" in v41
assert "refine_public_connection_v2ray_actions_v41" in v39
assert "source = refine_public_connection_mobile_authority_v40(source)" in v39
assert "return refine_public_connection_v2ray_actions_v41(source)" in v39

# V41 owns action cleanup on every viewport/platform, not only mobile.
assert "matchMedia" not in v41
assert "purgeLegacyInteractiveBlocks" in v41
assert "if(child===row)return" in v41
assert "if(interactive)child.remove()" in v41
assert "if(row.contains(node))return" in v41
assert "node.remove()" in v41

# Exactly the canonical V34 primary + copy controls survive.
assert "const primary=row.querySelector('.v34-primary')" in v41
assert "const copy=row.querySelector('.v34-copy')" in v41
assert "if(node!==primary&&node!==copy)node.remove()" in v41
assert "primary.textContent='ارسال به Hiddify'" in v41
assert "copy.textContent='کپی کانفیگ'" in v41

# Client download card is outside server-view cleanup and must not be retired here.
assert ".v34-client-card" not in v41
assert "Karing" not in v41
assert "v2rayN" not in v41

forbidden = ["iptables", "nft", "vxlan", "tp27", "quota", "accounting", "provision"]
for item in forbidden:
    assert item not in v41.lower(), item

print("V41 V2Ray two-action smoke OK")
