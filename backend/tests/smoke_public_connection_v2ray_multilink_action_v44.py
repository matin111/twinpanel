from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v44 = (ROOT / "backend/app/routers/public_connection_v2ray_multilink_action_v44.py").read_text()
v42 = (ROOT / "backend/app/routers/public_connection_mobile_sheet_v42.py").read_text()
v38 = (ROOT / "backend/app/routers/public_connection_reference_layout_v38.py").read_text()
v7 = (ROOT / "backend/app/routers/public_connection_multilink_v7.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_ACTION_V44" in v44
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_GROUPS_V49" in v44
assert "refine_public_connection_v2ray_multilink_action_v44" in v42
assert "return refine_public_connection_v2ray_multilink_action_v44(source)" in v42

# V38 keeps generic subscription routing behavior, while V44 now overrides the
# V2Ray card to the neutral all-profile subscription URL. The public action must
# not expose the protocol-named /multi/v2ray path because that pathname is
# externally DPI-sensitive on some networks.
assert "subscription?subscriptionUrl(protocol):multiUrl(protocol)" in v38
assert "+'/sub'" in v44
assert "'/multi/v2ray'" not in v44
assert "'/sub/v2ray'" not in v44
assert ".v38-all-card[data-v38-protocol=\"v2ray\"]" in v44
assert "actions.replaceChildren(send,copyButton)" in v44
assert "card.dataset.v44Endpoint='/sub'" in v44

# Both top-level user actions must use the exact same neutral all-profile URL.
# Karing is the canonical V2Ray client; Hiddify must not be reintroduced here.
assert "send.href=karingUrl(url,'TwinPanel V2Ray')" in v44
assert "copy(url)" in v44
assert "ارسال همه به Karing" in v44
assert "کپی لینک" in v44
assert "karing://install-config?url=" in v44
assert "hiddify://import/" not in v44
assert "ارسال همه به Hiddify" not in v44
assert "۹ کانفیگ" not in v44

# V49 grouped architecture: server -> profiles, populated only from the neutral
# read-only metadata endpoint. Do not parse subscription text in JS.
assert "+'/sub/meta'" in v44
assert "'/subscription/v2ray/meta'" not in v44
assert "async function loadGroups(card)" in v44
assert "Array.isArray(payload?.servers)" in v44
assert "server?.profile_count" in v44
assert "server?.profiles" in v44
assert "v49-v2ray-server" in v44
assert "v49-v2ray-profile" in v44
assert "مشاهده کانفیگ‌ها" in v44
assert '"/{token}/sub/meta"' in v7
assert '"/{token}/subscription/v2ray/meta"' in v7
assert "_v2ray_profile_groups" in v7

# The only browser fetch is the read-only metadata request. Presentation must not
# generate credentials or touch DB/dataplane/provisioning/accounting.
assert "fetch(url,{cache:'no-store',headers:{Accept:'application/json'}})" in v44
for forbidden in [
    "db.", "session", "iptables", "nft", "vxlan", "tp27",
    "quota", "accounting", "provision", "credential", "firewall",
]:
    assert forbidden not in v44.lower(), forbidden

print("V44/V49 V2Ray Karing neutral subscription wiring smoke OK")
