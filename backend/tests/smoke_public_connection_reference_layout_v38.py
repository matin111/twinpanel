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

    # Restore exactly the reference pattern: all-servers first, then app/single-server content.
    require("title.textContent='همه سرورها'" in v38, "all-servers title missing")
    require("panel.querySelector('.panel-head')?.insertAdjacentElement('afterend',card)" in v38,
            "all-servers card must be inserted immediately after the protocol heading")
    require(".v38-all-card" in v38, "V38 all-servers card styling missing")
    require(".v37-multi-card" in v38, "V37 duplicate multilink retirement missing")

    # The four proven subscription protocols must use their existing /sub authority, not V37's replacement.
    require("+'/sub/'+" in v38, "V38 does not restore existing subscription endpoint")
    require("subscriptionCount(protocol)" in v38, "V38 does not validate existing subscription content")
    require("کپی لینک اشتراک" in v38, "subscription copy action missing")
    require("افزودن همه به " in v38, "subscription app import action missing")

    # Remaining multi-capable protocols keep the V34 all-protocol endpoint.
    require("+'/multi/'+" in v38, "V38 all-protocol multilink endpoint missing")
    require("url+'/meta'" in v38, "V38 must verify all-protocol multilink metadata")
    require("دانلود همه کانفیگ‌ها" in v38, "native multi bundle action missing")
    require("کپی لینک همه سرورها" in v38, "multi copy action missing")

    # V36 remains the accordion authority; V38 only makes its final state visually authoritative.
    require(".protocol-panel.v36-open{display:block!important}" in v38,
            "V38 does not preserve one-open-protocol mobile accordion")
    require(".protocol-panel{display:none!important}" in v38,
            "V38 mobile panels are not collapsed by default")

    # Never delete the actual per-server or client content while restoring the reference card.
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

    print("PUBLIC_CONNECT_REFERENCE_LAYOUT_V38_SMOKE=PASS")


if __name__ == "__main__":
    main()
