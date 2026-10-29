from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V26 = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"
V39 = ROOT / "backend/app/routers/public_connection_mobile_simplified_v39.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v26 = V26.read_text(encoding="utf-8")
    v39 = V39.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_SIMPLIFIED_V39" in v39, "V39 marker missing")
    require("refine_public_connection_mobile_simplified_v39" in v26, "V39 not mounted by V26")
    require(
        v26.index("source = refine_public_connection_reference_layout_v38(source)")
        < v26.index("return refine_public_connection_mobile_simplified_v39(source)"),
        "V39 must be the final presentation authority after V38",
    )

    # Mobile must expose every real protocol choice already present in the canonical payload.
    require("body.v39-mobile-simple .protocols" in v39, "mobile protocol list restore CSS missing")
    require("display:grid!important" in v39, "mobile protocol list is not explicitly restored")
    require("document.querySelectorAll('.protocol-choice').forEach(choice=>" in v39,
            "V39 does not restore all canonical protocol choices")
    require("choice.classList.add('v39-real-protocol')" in v39,
            "real mobile protocol marker missing")
    require("!choice.classList.contains('v13-pending')" in v39,
            "pending protocols must stay hidden")
    require("choice.dataset.v31Hide!=='1'" in v39,
            "internal V31-hidden protocols must stay hidden")

    # V2Ray/Xray only: retain Hiddify client download but retire legacy per-server action surfaces.
    require("if(panelKey(panel)!=='v2ray')return" in v39, "V39 simplification escaped V2Ray scope")
    require(".v34-client-card" in v39 and "display:flex!important" in v39,
            "Hiddify client download card is not preserved")
    require("node.dataset.v39Retired='1'" in v39,
            "legacy V2Ray server actions are not retired")
    require("if(node===row)return" in v39,
            "canonical V34 server action row must be preserved")

    # Exact requested V2Ray customer actions.
    require("primary.textContent='ارسال به Hiddify'" in v39,
            "V2Ray Hiddify action label missing")
    require("copy.textContent='کپی کانفیگ'" in v39,
            "V2Ray copy-config action label missing")
    require("if(node!==primary&&node!==copy)node.remove()" in v39,
            "V2Ray action row is not capped to the requested two actions")
    require("simplifyMulti(panel)" in v39,
            "V2Ray HA/Multi actions are not normalized to the same two-action contract")

    # Presentation-only: no network/API fan-out, provisioning, accounting or dataplane work.
    for forbidden in (
        "fetch(", "XMLHttpRequest", "MutationObserver", "setInterval",
        "db.add(", "db.commit(", "ProtocolCredential(", "Quota", "iptables", "nft",
        "vxlan", "tp27", "provision", "credential_generation", "routing", "firewall",
    ):
        require(forbidden not in v39, f"V39 escaped presentation-only scope: {forbidden}")

    print("PUBLIC_CONNECT_MOBILE_SIMPLIFIED_V39_SMOKE=PASS")


if __name__ == "__main__":
    main()
