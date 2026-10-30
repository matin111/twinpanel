from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v44 = (ROOT / "backend/app/routers/public_connection_v2ray_multilink_action_v44.py").read_text()
v42 = (ROOT / "backend/app/routers/public_connection_mobile_sheet_v42.py").read_text()
v38 = (ROOT / "backend/app/routers/public_connection_reference_layout_v38.py").read_text()
v7 = (ROOT / "backend/app/routers/public_connection_multilink_v7.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_ACTION_V44" in v44
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_SUBSCRIPTION_ONLY_V51" in v44
assert "refine_public_connection_v2ray_multilink_action_v44" in v42
assert "return refine_public_connection_v2ray_multilink_action_v44(source)" in v42

# V38 keeps generic subscription routing behavior, while V44 overrides V2Ray
# to the neutral all-profile /sub endpoint only.
assert "subscription?subscriptionUrl(protocol):multiUrl(protocol)" in v38
assert "+'/sub'" in v44
assert "'/multi/v2ray'" not in v44
assert "'/sub/v2ray'" not in v44
assert '.v38-all-card[data-v38-protocol="v2ray"]' in v44
assert "card.dataset.v44Endpoint='/sub'" in v44
assert "card.dataset.v44Presentation='subscription-only'" in v44

# The customer gets one action for the entire subscription, not per-profile
# Karing actions and not an expandable list of individual configs.
assert "copy(url)" in v44
assert "کپی لینک همه کانفیگ‌ها" in v44
assert "همه کانفیگ‌ها" in v44
assert "actions.replaceChildren(copyButton)" in v44
assert "karing://install-config?url=" not in v44
assert "ارسال همه به Karing" not in v44
assert "مشاهده کانفیگ‌ها" not in v44
assert "async function loadGroups(card)" not in v44
assert "function profileRow(profile,index)" not in v44
assert "function serverCard(server,index)" not in v44
assert "+'/sub/meta'" not in v44

# Backend metadata routes remain available for compatibility, but V44 no longer
# fetches or renders them in the customer UI.
assert '"/{token}/sub/meta"' in v7
assert '"/{token}/subscription/v2ray/meta"' in v7
assert "_v2ray_profile_groups" in v7
assert "fetch(" not in v44

for forbidden in [
    "db.", "session", "iptables", "nft", "vxlan", "tp27",
    "quota", "accounting", "provision", "credential", "firewall",
]:
    assert forbidden not in v44.lower(), forbidden

print("V44 V2Ray neutral subscription-only wiring smoke OK")
