from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "routers" / "public_connection_presentation_v29.py"
spec = importlib.util.spec_from_file_location("public_connection_presentation_v29", MODULE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
refine_public_connection_presentation_v29 = module.refine_public_connection_presentation_v29


FIXTURE = """<!doctype html>
<html><head><style>.base{display:block}</style></head><body class="v27-mobile-ui">
<div class="section-head"><div><small>SMART CONNECT</small><h2>اتصال هوشمند</h2></div><p>noise</p></div>
<div class="smart-card">smart</div>
<div class="section-head"><div><small>QUICK CONNECT</small><h2>اتصال سریع</h2></div><p>noise</p></div>
<section class="protocols">choices</section>
<section class="v27-connect-nav"><div class="v27-protocol-strip"></div></section>
<div class="v28-scroll-hint">swipe</div>
<section class="protocol-panel v24-canonical-panel" data-modern-protocol="hysteria2">
  <div class="panel-head"><div><span>اتصال سریع</span><h3>Hysteria2</h3></div><div class="server-tabs"></div></div>
  <div class="server-views">
    <div class="server-view" data-v24-server-label="usa">
      <div class="facts"><div class="fact"><small>Server</small><strong>example</strong></div></div>
      <div class="v13-modern-action"><div class="v13-action-buttons">
        <button class="primary-btn v13-karing-import" data-config-path="/cfg">افزودن مستقیم به Karing</button>
        <a class="v13-secondary" href="/cfg">دانلود فایل</a>
        <a class="v13-app" href="https://example.invalid/karing">دانلود Karing</a>
      </div></div>
    </div>
  </div>
</section>
<div class="multi-link-card">multilink</div>
<div class="tp-win-v2ray-note">tutorial</div>
</body></html>"""


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> None:
    output = refine_public_connection_presentation_v29(FIXTURE)

    require("TWINPANEL_PUBLIC_CONNECT_PRESENTATION_V29" in output, "V29 marker missing")
    require("twinpanelPublicConnectPresentationV29" in output, "V29 script missing")

    # Mobile authority: no horizontal chooser is required; canonical protocol
    # panels and every server view are forced into a vertical card layout.
    require(".v27-connect-nav" in output, "V27 nav retirement selector missing")
    require(".v28-scroll-hint" in output, "V28 hint retirement selector missing")
    require(".protocol-panel.v24-canonical-panel" in output, "canonical panel selector missing")
    require("flex-direction:column!important" in output, "vertical server stack missing")
    require("content:attr(data-v24-server-label)!important" in output, "server card label missing")

    # Modern connection methods stay action-based. Generic facts are presentation-only hidden.
    require(".protocol-panel[data-modern-protocol] .facts" in output, "modern facts guard missing")

    # Fake/duplicate presentation surfaces are retired, while their source data/endpoints
    # remain untouched by this refiner.
    require(".smart-card" in output, "smart UI retirement missing")
    require(".multi-link-card" in output, "multilink UI retirement missing")
    require("document.querySelectorAll('.smart-card,.smart-empty,.multi-link-card,.tp-win-v2ray-note')" in output, "noise cleanup missing")

    # Readability/action simplification contract.
    require("font-size:12px!important" in output, "readable action typography missing")
    require("node.textContent='دانلود'" in output, "download label normalization missing")
    require("node.textContent='اتصال'" in output, "connect label normalization missing")
    require("node.textContent='کپی'" in output, "copy label normalization missing")

    # The refiner must be idempotent.
    require(refine_public_connection_presentation_v29(output) == output, "V29 is not idempotent")

    print("PUBLIC_CONNECTION_PRESENTATION_V29_SMOKE=PASS")


if __name__ == "__main__":
    main()
