from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V26 = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"
V34_MULTI = ROOT / "backend/app/routers/public_connection_all_multilink_v34.py"
V37 = ROOT / "backend/app/routers/public_connection_final_presentation_v37.py"

EXPECTED_MULTI = {
    "openvpn", "wireguard", "v2ray", "hysteria2", "tuic", "anytls", "naive",
    "shadowtls", "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def js_set(source: str, variable: str) -> set[str]:
    match = re.search(rf"const\s+{re.escape(variable)}\s*=\s*new Set\(\[(.*?)\]\);", source, re.S)
    require(match is not None, f"JS set {variable} missing")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def python_tuple(source: str, variable: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value = node.value
        if target == variable and value is not None:
            return tuple(ast.literal_eval(value))
    raise AssertionError(f"{variable} missing")


def main() -> None:
    v26 = V26.read_text(encoding="utf-8")
    v34_multi = V34_MULTI.read_text(encoding="utf-8")
    v37 = V37.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_FINAL_PRESENTATION_V37" in v37, "V37 marker missing")
    require("refine_public_connection_final_presentation_v37" in v26, "V37 not mounted by V26")
    require(
        v26.index("refine_public_connection_forward_v34(source)")
        < v26.index("refine_public_connection_final_presentation_v37(source)"),
        "V37 must run after V34 as final presentation authority",
    )

    ui_multi = js_set(v37, "MULTI")
    backend_multi = set(python_tuple(v34_multi, "MULTI_PROTOCOLS"))
    require(ui_multi == EXPECTED_MULTI, f"V37 customer multilink set drifted: {sorted(ui_multi)}")
    require(backend_multi == EXPECTED_MULTI, f"backend multilink set drifted: {sorted(backend_multi)}")
    require("+'/multi/'+" in v37, "V37 does not use existing all-protocol multilink endpoint")
    require("url+'/meta'" in v37, "V37 does not verify multilink metadata")
    require("v37-multi-card" in v37, "V37 multilink card missing")
    require("کپی لینک همه سرورها" in v37, "multilink copy action missing")
    require("دانلود همه کانفیگ‌ها" in v37, "native all-config bundle action missing")
    require("افزودن همه به " in v37, "compatible-app multi import action missing")

    # The old four-protocol subscription presentation must not compete with restored multilinks.
    require(".v34-subscription-card{display:none!important}" in v37,
            "legacy V34 subscription card is not retired by final presentation")
    require("document.querySelectorAll('.v34-subscription-card').forEach(node=>node.remove())" in v37,
            "legacy V34 subscription DOM cleanup missing")

    # Customer-facing noise cleanup: remove Smart Connect block and helper copy while keeping headings/actions.
    require("heading==='اتصال هوشمند'" in v37, "Smart Connect section cleanup missing")
    require("node.querySelectorAll('small,p').forEach(extra=>extra.remove())" in v37,
            "section helper text cleanup missing")
    require(".panel-head>div>span,.v34-single-label" in v37,
            "panel helper-label cleanup missing")

    # Presentation-only scope guard.
    for forbidden in (
        "db.add(", "db.commit(", "ProtocolCredential(", "Quota", "iptables", "nft", "vxlan", "tp27",
        "provision", "credential_generation", "routing", "firewall",
    ):
        require(forbidden not in v37, f"V37 escaped presentation-only scope: {forbidden}")
    require("MutationObserver" not in v37, "V37 must not install a DOM observer")
    require("setInterval" not in v37, "V37 must not poll")

    print("PUBLIC_CONNECT_FINAL_PRESENTATION_V37_SMOKE=PASS")


if __name__ == "__main__":
    main()
