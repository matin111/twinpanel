from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V27 = ROOT / "backend/app/routers/public_connection_mobile_ui_v27.py"
V36 = ROOT / "backend/app/routers/public_connection_mobile_compact_v36.py"
V39 = ROOT / "backend/app/routers/public_connection_mobile_simplified_v39.py"
V40 = ROOT / "backend/app/routers/public_connection_mobile_authority_v40.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v27 = V27.read_text(encoding="utf-8")
    v36 = V36.read_text(encoding="utf-8")
    v39 = V39.read_text(encoding="utf-8")
    v40 = V40.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_AUTHORITY_V40" in v40, "V40 marker missing")
    require("refine_public_connection_mobile_authority_v40" in v39, "V40 is not imported by V39")
    require("return refine_public_connection_mobile_authority_v40(source)" in v39,
            "V40 must be the final refinement after V39")

    # Root-cause evidence: V27 owns an online-first active protocol while V36 owns v36-open.
    require("activePanelId=(online||panels[0]).id" in v27, "V27 online-first selector evidence drifted")
    require("v27-active-protocol" in v27, "V27 active protocol class evidence missing")
    require("panel.classList.add('active','v36-open')" in v36, "V36 accordion open contract drifted")

    # V40 must explicitly retire V27 and its parallel nav/state.
    require("document.body.classList.remove('v27-mobile-ui')" in v40, "V27 body authority is not retired")
    require("document.querySelector('.v27-connect-nav')?.remove()" in v40, "V27 navigation is not retired")
    require(".v27-active-protocol" in v40 and "remove('v27-active-protocol')" in v40,
            "V27 active protocol state is not removed")
    require(".v27-active-server" in v40 and "remove('v27-active-server')" in v40,
            "V27 active server state is not removed")

    # CSS must win even during V27's delayed rebuild window.
    require("body.v40-mobile-final.v27-mobile-ui .protocol-panel.v24-canonical-panel" in v40,
            "V40 lacks the specificity guard against delayed V27 state")
    require(".protocol-panel.v24-canonical-panel.v36-open" in v40,
            "V36-open is not the final visible-panel condition")
    require("body.v40-mobile-final .v27-connect-nav" in v40 and "display:none!important" in v40,
            "V27 nav is not hard-retired in final CSS")

    # Real mobile protocol inventory comes from panels that actually have server views.
    require("function realPanels()" in v40, "real panel inventory helper missing")
    require(".protocol-panel.v24-canonical-panel" in v40, "canonical panel authority missing")
    require("Boolean(panel.querySelector('.server-view'))" in v40, "real server evidence is not required")
    require("choice.classList.add('v40-real-protocol')" in v40, "real protocol choice marker missing")
    require("choice.removeAttribute('data-v31-hide')" in v40,
            "stale presentation hide flag is not cleared for proven real protocols")
    require(".protocol-choice:not(.v40-real-protocol)" in v40,
            "non-real mobile protocol choices are not excluded")

    # Initial state is collapsed and V36 remains the only user-driven accordion.
    require("panel.classList.remove('active','v36-open','v27-active-protocol')" in v40,
            "initial mobile panels are not explicitly collapsed")
    require("choice.setAttribute('aria-expanded','false')" in v40,
            "initial protocol choices are not collapsed")
    require("initialized=true" in v40, "initial collapse guard missing")

    # V2Ray/Xray keeps data but retires only legacy action surfaces.
    require("if(panelKey(panel)!=='v2ray')return" in v40, "V2Ray simplification escaped protocol scope")
    require("[data-v39-retired=\"1\"]" in v40, "V39 over-hide cleanup missing")
    require(":scope > .action-row" in v40 and ":scope > .v31-canonical-actions" in v40,
            "legacy V2Ray action surfaces are not explicitly retired")
    require("data-v40-retired-actions" in v40, "V40 action retirement marker missing")
    require(".v34-client-card" in v40 and "display:flex!important" in v40,
            "Hiddify download card is not preserved")
    require(".v31-client-card" in v40 and "display:none!important" in v40,
            "duplicate client download surface is not retired")
    require("primary.textContent='ارسال به Hiddify'" in v40, "Hiddify send action label missing")
    require("copy.textContent='کپی کانفیگ'" in v40, "copy config action label missing")
    require("if(node!==primary&&node!==copy)node.remove()" in v40,
            "V2Ray canonical rows are not capped at two actions")
    require("simplifyMulti(panel)" in v40, "V2Ray HA/Multi Server actions are not simplified")

    # V40 must remain presentation-only and must not create API fan-out.
    for forbidden in (
        "fetch(", "XMLHttpRequest", "MutationObserver", "setInterval",
        "db.add(", "db.commit(", "ProtocolCredential(", "QuotaDevice(",
        "iptables", "nft ", "subprocess", "asyncssh",
    ):
        require(forbidden not in v40, f"V40 escaped presentation-only scope: {forbidden}")

    print("PUBLIC_CONNECT_MOBILE_AUTHORITY_V40_SMOKE=PASS")


if __name__ == "__main__":
    main()
