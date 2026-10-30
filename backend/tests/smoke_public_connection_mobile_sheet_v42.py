from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
v42 = (ROOT / "backend/app/routers/public_connection_mobile_sheet_v42.py").read_text()
v41 = (ROOT / "backend/app/routers/public_connection_v2ray_actions_v41.py").read_text()
v44 = (ROOT / "backend/app/routers/public_connection_v2ray_multilink_action_v44.py").read_text()
backpressure = (ROOT / "backend/app/routers/public_connection_request_backpressure_v1.py").read_text()

assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_SHEET_V42" in v42
assert "refine_public_connection_mobile_sheet_v42" in v41
assert "source = refine_public_connection_mobile_sheet_v42(source)" in v41
assert "return refine_public_connection_request_backpressure_v1(source)" in v41
assert "TWINPANEL_PUBLIC_CONNECT_REQUEST_BACKPRESSURE_V1" in backpressure
assert "refine_public_connection_v2ray_multilink_action_v44" in v42
assert "return refine_public_connection_v2ray_multilink_action_v44(source)" in v42
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_ACTION_V44" in v44

# Mobile protocol tap must be owned before V36 target listeners and open a fixed sheet.
assert "document.addEventListener('click',handleProtocolTap,true)" in v42
assert "event.stopImmediatePropagation()" in v42
assert "panel.classList.add('active','v36-open','v42-sheet-open')" in v42
assert "position:fixed!important" in v42
assert "bottom:8px!important" in v42
assert "max-height:min(82dvh,760px)!important" in v42
assert "v42-sheet-backdrop" in v42
assert "v42-sheet-close" in v42

# Same real panel is presented; no cloning/copying of server actions.
assert "cloneNode" not in v42
assert "innerHTML=panel" not in v42
assert "panel.querySelector('.server-view')" in v42

# Sheet remains mobile-only and desktop restores normal presentation.
assert "const MOBILE='(max-width:720px)'" in v42
assert "if(!isMobile())" in v42
assert "closeSheet()" in v42
assert "document.body.classList.remove('v42-mobile-sheet')" in v42

forbidden = ["iptables", "nft", "vxlan", "tp27", "quota", "accounting", "provision"]
for item in forbidden:
    assert item not in v42.lower(), item
    assert item not in backpressure.lower(), item

print("V42 mobile bottom-sheet + request backpressure chain smoke OK")
