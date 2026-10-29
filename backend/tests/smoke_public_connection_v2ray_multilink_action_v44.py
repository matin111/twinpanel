from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v44 = (ROOT / "backend/app/routers/public_connection_v2ray_multilink_action_v44.py").read_text()
v42 = (ROOT / "backend/app/routers/public_connection_mobile_sheet_v42.py").read_text()
v38 = (ROOT / "backend/app/routers/public_connection_reference_layout_v38.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_ACTION_V44" in v44
assert "refine_public_connection_v2ray_multilink_action_v44" in v42
assert "return refine_public_connection_v2ray_multilink_action_v44(source)" in v42

# V38 historically routes subscription protocols to /sub. V44 must explicitly
# override only the V2Ray Multi Server card to the all-profile /multi endpoint.
assert "subscription?subscriptionUrl(protocol):multiUrl(protocol)" in v38
assert "'/multi/v2ray'" in v44
assert "'/sub/v2ray'" not in v44
assert ".v38-all-card[data-v38-protocol=\"v2ray\"]" in v44
assert "actions.replaceChildren(send,copyButton)" in v44
assert "card.dataset.v44Endpoint='/multi/v2ray'" in v44

# Both user actions must use the exact same 9-config multilink URL.
assert "send.href=hiddifyUrl(url)" in v44
assert "copy(url)" in v44
assert "ارسال همه به Hiddify" in v44
assert "کپی لینک" in v44
assert "hiddify://import/" in v44

# Presentation-only: do not generate credentials, query DB, or touch dataplane.
for forbidden in [
    "fetch(", "db.", "session", "iptables", "nft", "vxlan", "tp27",
    "quota", "accounting", "provision", "credential", "firewall",
]:
    assert forbidden not in v44.lower(), forbidden

print("V44 V2Ray Multi Server Hiddify wiring smoke OK")
