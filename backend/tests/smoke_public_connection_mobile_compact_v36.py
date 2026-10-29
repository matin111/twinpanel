from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V26 = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"
V36 = ROOT / "backend/app/routers/public_connection_mobile_compact_v36.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v26 = V26.read_text(encoding="utf-8")
    v36 = V36.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_COMPACT_V36" in v36, "V36 marker missing")
    require("refine_public_connection_mobile_compact_v36" in v26, "V36 not mounted by V26")
    require(
        v26.index("refine_public_connection_mobile_compact_v36(source)")
        < v26.index("refine_public_connection_forward_v34(source)"),
        "V36 accordion binding must be inserted before V34 action rendering",
    )

    # Smart Connect is retired, including its heading container.
    require(".smart-card{display:none!important}" in v36, "Smart Connect CSS retirement missing")
    require(".smart-card,.smart-empty" in v36, "Smart Connect DOM cleanup missing")
    require("heading==='اتصال هوشمند'" in v36, "Smart Connect heading cleanup missing")

    # Responsive/mobile preview is viewport-owned. Real phones and narrow browser
    # acceptance must use exactly the same accordion behaviour.
    require("const MOBILE='(max-width:720px)'" in v36, "responsive mobile breakpoint missing")
    require("function isCompact()" in v36, "responsive compact authority missing")
    require("window.matchMedia(MOBILE).matches" in v36, "viewport guard missing")
    require("const PHONE=" not in v36, "obsolete Android/iOS-only gate returned")
    require('data-tp-platform="android"' not in v36, "accordion must not depend on Android platform marker")
    require('data-tp-platform="ios"' not in v36, "accordion must not depend on iOS platform marker")

    # Initial state is collapsed; protocol tap is the single accordion authority.
    require("closeAll();" in v36, "initial collapsed state missing")
    require("panel.classList.add('active','v36-open')" in v36, "selected protocol open state missing")
    require("const wasOpen=panel.classList.contains('v36-open')" in v36,
            "same-protocol toggle-close state missing")
    require("event.stopImmediatePropagation()" in v36,
            "legacy protocol click handler is not isolated in compact view")
    require("},true);" in v36, "capture-phase protocol accordion binding missing")
    require(".protocol-panel.v36-open" in v36, "open-panel CSS authority missing")
    require("body.v36-mobile-compact .protocol-panel" in v36,
            "closed-panel compact CSS authority missing")

    # V34's nested long-list fold is removed so one protocol tap reveals servers directly.
    require("v34-mobile-servers" in v36, "V34 nested fold cleanup missing")
    require("insertAdjacentElement('beforebegin',views)" in v36, "V34 server-view unwrap missing")
    require(".v34-single-label" in v36, "nested single-server label cleanup missing")

    # Presentation-only scope guard.
    for forbidden in (
        "db.add(", "db.commit(", "ProtocolCredential(", "Quota", "iptables", "nft", "vxlan", "tp27",
        "provision", "credential_generation", "routing", "firewall",
    ):
        require(forbidden not in v36, f"V36 escaped presentation-only scope: {forbidden}")
    require("MutationObserver" not in v36, "V36 must not install a DOM observer")
    require("setInterval" not in v36, "V36 must not add polling")
    require("navigator.userAgent" not in v36, "V36 must not add UA sniffing")

    print("PUBLIC_CONNECT_MOBILE_COMPACT_V36_SMOKE=PASS")


if __name__ == "__main__":
    main()
