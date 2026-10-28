from __future__ import annotations

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"

v11 = (ROUTERS / "public_connection_device_actions_v11.py").read_text(encoding="utf-8")
v24_path = ROUTERS / "public_connection_canonical_presentation_v24.py"
v25_path = ROUTERS / "public_connection_mobile_stability_v25.py"

v24 = runpy.run_path(str(v24_path))
v25 = runpy.run_path(str(v25_path))

refine_v24 = v24["refine_public_connection_canonical_presentation_v24"]
refine_v25 = v25["refine_public_connection_mobile_stability_v25"]

# V25 must be wired immediately after canonical V24 presentation refinement.
assert "refine_public_connection_mobile_stability_v25" in v11
assert "source = refine_public_connection_canonical_presentation_v24(source)" in v11
assert "return refine_public_connection_mobile_stability_v25(source)" in v11

# Reproduce the generated V24 HTML, then verify V25 removes only the recursive
# legacy-body observer while preserving the narrow live-status observer.
base = "<!doctype html><html><head><style></style></head><body></body></html>"
v24_html = refine_v24(base)
assert "legacyObserver=new MutationObserver" in v24_html
assert "childList:true,subtree:true" in v24_html

safe_html = refine_v25(v24_html)
assert "TWINPANEL_PUBLIC_CONNECT_MOBILE_STABILITY_V25" in safe_html
assert "legacyObserver=new MutationObserver" not in safe_html
assert "legacyObserver.observe(document.body" not in safe_html
assert "childList:true,subtree:true" not in safe_html

# Online-state observation is safe and must remain intact: it watches only the
# class attribute of protocol-choice nodes and does not rewrite those choices.
assert "liveObserver=new MutationObserver(syncLive)" in safe_html
assert "attributeFilter:['class']" in safe_html

# Cleanup is a single deferred pass.  It runs after later inline legacy
# renderers in the same parser task without keeping a subtree observer alive.
assert "setTimeout(()=>{" in safe_html
assert "retireLegacyMobile();\n      syncApps();\n    },0);" in safe_html
assert "legacyObserver=null;" in safe_html

# Refinement is idempotent.
assert refine_v25(safe_html) == safe_html
assert safe_html.count("TWINPANEL_PUBLIC_CONNECT_MOBILE_STABILITY_V25") == 1

# Preserve the canonical/minimal mobile contract and exact direct destinations.
for required in (
    "v24-canonical-panel",
    ".section-head p",
    ".action-copy",
    "https://github.com/KaringX/karing/releases/download/v1.2.25.2802/karing_1.2.25.2802_android_arm.apk",
    "https://download.wireguard.com/android-client/com.wireguard.android-1.0.20260315.apk",
    "https://github.com/amnezia-vpn/amneziawg-android/releases/download/v3.1.20260814/AmneziaWG-3.1.202060814.apk",
):
    assert required in safe_html, required

print("V25 mobile stability smoke: PASS")
