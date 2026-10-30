from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v44 = (ROOT / "backend/app/routers/public_connection_v2ray_multilink_action_v44.py").read_text()
v42 = (ROOT / "backend/app/routers/public_connection_mobile_sheet_v42.py").read_text()
v40 = (ROOT / "backend/app/routers/public_connection_mobile_authority_v40.py").read_text()
v41 = (ROOT / "backend/app/routers/public_connection_v2ray_actions_v41.py").read_text()
v38 = (ROOT / "backend/app/routers/public_connection_reference_layout_v38.py").read_text()
v7 = (ROOT / "backend/app/routers/public_connection_multilink_v7.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_ACTION_V44" in v44
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_GROUPS_V49" in v44
assert "refine_public_connection_v2ray_multilink_action_v44" in v42
assert "return refine_public_connection_v2ray_multilink_action_v44(source)" in v42

# V38 keeps generic subscription routing behavior, while V44 overrides the
# V2Ray card to the neutral all-profile subscription URL. The public action must
# not expose the protocol-named /multi/v2ray path because that pathname is
# externally DPI-sensitive on some networks.
assert "subscription?subscriptionUrl(protocol):multiUrl(protocol)" in v38
assert "+'/sub'" in v44
assert "'/multi/v2ray'" not in v44
assert "'/sub/v2ray'" not in v44
assert ".v38-all-card[data-v38-protocol=\"v2ray\"]" in v44
assert "card.dataset.v44Endpoint='/sub'" in v44

# Mobile authority must keep V2Ray visible after V41 removes legacy .server-view
# inventory. Android and iPhone/iPad use this <=720px path, so V40 must accept
# the preserved Multi Server surface as a real renderable protocol.
assert "function hasRenderableSurface(panel)" in v40
assert "if(panel.querySelector('.server-view'))return true" in v40
assert "if(panelKey(panel)==='v2ray')" in v40
assert "panel.querySelector('.v38-all-card[data-v38-protocol=\"v2ray\"]')" in v40
assert "panel.dataset.v41LowerConfigsRemoved==='1'" in v40
assert "panel.dataset.v41V2ray==='1'" in v40
assert "hasRenderableSurface(panel)" in v40

# Device-aware client behavior must stay aligned across V41 download and V44
# import actions: macOS -> v2rayN, Android -> v2rayNG, iPhone/iPad -> V2Box.
assert "macos:{name:'v2rayN'" in v41
assert "android:{name:'v2rayNG'" in v41
assert "ios:{name:'V2Box'" in v41
assert "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690" in v41
assert "if(/iphone|ipad|ipod/i.test(ua))return'ios'" in v41
assert "if(/macintosh|mac os|macintel/i.test(haystack)&&Number(navigator.maxTouchPoints||0)>1)return'ios'" in v41
assert "if(/macintosh|mac os|macintel/i.test(haystack))return'macos'" in v41

assert "function platform()" in v44
assert "if(/android/i.test(ua))return'android'" in v44
assert "if(/iphone|ipad|ipod/i.test(ua))return'ios'" in v44
assert "if(/windows|win32|win64|winarm/i.test(haystack))return'windows'" in v44
assert "if(/macintosh|mac os|macintel/i.test(haystack))return'macos'" in v44
assert "if(/linux|x11|cros/i.test(haystack))return'linux'" in v44
assert "function clientName()" in v44
assert "if(p==='android')return'v2rayNG'" in v44
assert "if(p==='ios')return'V2Box'" in v44
assert "return'v2rayN'" in v44
assert "v2rayng://install-sub?url=" in v44
assert "v2rayng://install-config?url=" in v44
assert "ارسال همه به v2rayNG" in v44
assert "ارسال به v2rayNG" in v44
assert "isSubscription?('کپی لینک برای '+client):('کپی کانفیگ برای '+client)" in v44
assert "card.dataset.v44Client=clientName()" in v44

# Karing/Hiddify-specific customer actions must not return.
assert "karing://" not in v44.lower()
assert "ارسال همه به Karing" not in v44
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

print("V40/V41/V44/V49 V2Ray mobile visibility and Apple client smoke OK")
