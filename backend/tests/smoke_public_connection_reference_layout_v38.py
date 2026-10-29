from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V26 = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"
V38 = ROOT / "backend/app/routers/public_connection_reference_layout_v38.py"

EXPECTED_MULTI = {
    "openvpn", "wireguard", "v2ray", "hysteria2", "tuic", "anytls", "naive",
    "shadowtls", "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
}
EXPECTED_SUBSCRIPTIONS = {"v2ray", "hysteria2", "tuic", "anytls"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def js_set(source: str, variable: str) -> set[str]:
    match = re.search(rf"const\s+{re.escape(variable)}\s*=\s*new Set\(\[(.*?)\]\);", source, re.S)
    require(match is not None, f"JS set {variable} missing")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def main() -> None:
    v26 = V26.read_text(encoding="utf-8")
    v38 = V38.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38" in v38, "V38 marker missing")
    require("refine_public_connection_reference_layout_v38" in v26, "V38 not mounted by V26")
    require(
        v26.index("refine_public_connection_final_presentation_v37(source)")
        < v26.index("refine_public_connection_reference_layout_v38(source)"),
        "V38 must run after V37",
    )

    require(js_set(v38, "MULTI") == EXPECTED_MULTI, "V38 multilink protocol set drifted")
    require(js_set(v38, "SUBSCRIPTIONS") == EXPECTED_SUBSCRIPTIONS,
            "V38 legacy subscription authority set drifted")

    # Exact reference structure: HA heading -> Multi Server row -> individual servers.
    require("headingText.textContent='High Availability Config'" in v38,
            "reference HA heading missing")
    require("label.textContent='Multi Server'" in v38, "reference Multi Server row missing")
    require("shield.textContent='🛡️'" in v38 and "globe.textContent='🌐'" in v38,
            "reference HA visual markers missing")
    require("badge.textContent=protocolTitle(panel,protocol)" in v38,
            "protocol badge missing from HA card")
    require("title.textContent='همه سرورها'" in v38,
            "accessible Persian all-servers label missing")
    require("panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card)" in v38,
            "HA card must be inserted immediately after the protocol heading")
    require("listTitle.textContent='سرورهای تکی'" in v38,
            "individual-server section label missing")
    require(".v38-all-card" in v38 and ".v38-multi-row" in v38,
            "reference HA card styling missing")
    require(".v37-multi-card" in v38, "V37 duplicate multilink retirement missing")

    # Keep the proven delivery authorities, but do not call them while rendering the page.
    require("+'/sub/'+" in v38, "V38 subscription endpoint missing")
    require("+'/multi/'+" in v38, "V38 all-protocol multilink endpoint missing")
    require("کپی لینک اشتراک" in v38, "subscription copy accessibility contract missing")
    require("افزودن همه به " in v38, "subscription app import accessibility contract missing")
    require("دانلود همه کانفیگ‌ها" in v38, "native multi bundle accessibility contract missing")
    require("کپی لینک همه سرورها" in v38, "multi copy accessibility contract missing")

    # 504 regression: rendering must never fan out into /sub or /multi/meta API requests.
    require("fetch(" not in v38, "V38 must not issue eager API fetches during page render")
    require("multiMeta(" not in v38, "V38 eager multi metadata lookup returned")
    require("subscriptionCount(" not in v38, "V38 eager subscription lookup returned")
    require("url+'/meta'" not in v38, "V38 must not call /multi/.../meta during render")
    require("function serverCount(panel)" in v38, "V38 DOM server counter missing")
    require("panel.querySelectorAll('.server-views .server-view').length" in v38,
            "V38 must derive the display-only count from already-rendered server rows")
    require("const count=serverCount(panel)" in v38,
            "V38 does not use existing server rows for display-only count")

    # Customer-facing labels match the reference screenshot while preserving accessible detail.
    require("link('دانلود همه'" in v38, "reference native bundle label missing")
    require("link('افزودن همه'" in v38, "reference import label missing")
    require("button('کپی لینک'" in v38, "reference copy label missing")
    require("button('کپی مولتی‌لینک'" in v38, "fallback multilink label missing")

    # V36 remains accordion authority; V38 makes the final compact state authoritative.
    require(".protocol-panel.v36-open{display:block!important}" in v38,
            "V38 does not preserve one-open-protocol responsive accordion")
    require(".protocol-panel{display:none!important}" in v38,
            "V38 responsive panels are not collapsed by default")
    require("v36-mobile-compact" in v38,
            "V38 reference compact styling must follow V36 responsive state")

    # Keep existing client and individual-server content; V38 only refines presentation.
    for forbidden_dom in (
        "querySelectorAll('.server-view').forEach(node=>node.remove())",
        "querySelectorAll('.server-views').forEach(node=>node.remove())",
        "querySelectorAll('.v34-client-card').forEach(node=>node.remove())",
    ):
        require(forbidden_dom not in v38, f"V38 deletes required customer content: {forbidden_dom}")

    # Presentation-only scope guard.
    for forbidden in (
        "db.add(", "db.commit(", "ProtocolCredential(", "Quota", "iptables", "nft", "vxlan", "tp27",
        "provision", "credential_generation", "routing", "firewall",
    ):
        require(forbidden not in v38, f"V38 escaped presentation-only scope: {forbidden}")
    require("MutationObserver" not in v38, "V38 must not install a DOM observer")
    require("setInterval" not in v38, "V38 must not poll")

    print("PUBLIC_CONNECT_REFERENCE_HA_V38_SMOKE=PASS")


if __name__ == "__main__":
    main()
