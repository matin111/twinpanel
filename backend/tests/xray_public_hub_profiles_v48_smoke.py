from __future__ import annotations

import html
import importlib.util
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "backend/app/xray_public_hub_profiles_v48.py"
LIVE_PATH = ROOT / "backend/app/routers/public_connection_hub_live_v5.py"

spec = importlib.util.spec_from_file_location("xray_public_hub_profiles_v48_smoke_target", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def profile(profile_id: str, title: str, uri: str, qr: str) -> dict:
    return {
        "id": profile_id,
        "title": title,
        "uri": uri,
        "qr": qr,
        "transport": profile_id.split("_", 1)[0],
        "security": "reality" if "reality" in profile_id else "tls",
    }


uris = [
    "vless://uuid@iran.example:443?security=tls&type=ws#WS",
    "vless://uuid@iran.example:38001?security=reality&type=xhttp&sid=aa#XHTTP",
    "vless://uuid@iran.example:38002?security=reality&type=tcp&sid=bb#TCP",
]
profiles = [
    profile("websocket_tls", "WebSocket TLS", uris[0], "data:image/png;base64,AAA"),
    profile("xhttp_reality", "XHTTP Reality", uris[1], "data:image/png;base64,BBB"),
    profile("tcp_reality", "TCP Reality", uris[2], "data:image/png;base64,CCC"),
]

rendered = module.render_xray_quick_connect_profiles({"profiles": profiles})
assert rendered is not None
assert rendered.count('class="action-row tp-v48-xray-profile"') == 3
assert 'data-tp-xray-profile-count="3"' in rendered
for uri in uris:
    escaped = html.escape(uri, quote=True)
    assert f'data-copy="{escaped}"' in rendered
    assert f'href="{escaped}"' in rendered

for item in profiles:
    title = item["title"]
    uri = item["uri"]
    hiddify = f"hiddify://import/{quote(uri, safe='')}#{quote(title, safe='')}"
    karing = f"karing://install-config?url={quote(uri, safe='')}&name={quote(title, safe='')}"
    assert html.escape(hiddify, quote=True) in rendered
    assert html.escape(karing, quote=True) in rendered
    assert title in rendered
    assert item["qr"] in rendered

# Render only real profiles. Never manufacture a third profile.
two = module.render_xray_quick_connect_profiles({"profiles": profiles[:2]})
assert two is not None
assert two.count('class="action-row tp-v48-xray-profile"') == 2
assert 'data-tp-xray-profile-count="2"' in two
assert uris[2] not in html.unescape(two)
assert module.render_xray_quick_connect_profiles({"profiles": []}) is None
assert module.render_xray_quick_connect_profiles({}) is None

# Escape user/provider supplied labels and URIs before writing HTML.
evil = module.render_xray_quick_connect_profiles(
    {
        "profiles": [
            profile(
                "xhttp_reality",
                '<img src=x onerror="alert(1)">',
                'vless://u@h:443?x=" onclick="alert(1)',
                'data:image/png;base64,DDD" onerror="alert(1)',
            )
        ]
    }
)
assert evil is not None
assert '<img src=x onerror="alert(1)">' not in evil
assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;' in evil
assert 'onclick="alert(1)' not in evil

source = MODULE_PATH.read_text(encoding="utf-8")
live = LIVE_PATH.read_text(encoding="utf-8")

# Hub must resolve V47's final selector dynamically at request time.
assert "delivery._customer_profiles(item)" in source
assert "delivery._profile_delivery_item(item, profile)" in source

# Smart Connect remains canonical/single; only server Quick Connect expands.
assert 'prefix != "smart"' in source
assert "return _original_item_detail(" in source

# Mobile must enumerate every V48 profile, not select only the first URI.
assert "querySelectorAll('.tp-v48-xray-profile')" in source
assert "profiles.forEach" in source
assert "tp-v48-mobile-profiles" in source

# Multilink remains a separate surface; V48 must not import or patch it.
assert "public_connection_multilink" not in source

# The active Hub resolves V48 before base render, applies V48 data refinement,
# then finishes with the canonical-only mobile presentation. Retired URI parsing
# must not run after V24/V48.
assert "apply_xray_public_hub_profiles_v48" in live
assert "refine_public_connection_xray_profiles_v48" in live
assert "refine_public_connection_canonical_mobile_v26" in live
assert "refine_public_connection_protocol_uri_details_v21" not in live
assert live.index("apply_xray_public_hub_profiles_v48()") < live.index("base = public_connection_hub_v5(token, db)")
assert live.index("refine_public_connection_xray_profiles_v48(source)") < live.index("refine_public_connection_canonical_mobile_v26(source)")

print("Xray Public Hub Profiles V48 smoke: PASS")
